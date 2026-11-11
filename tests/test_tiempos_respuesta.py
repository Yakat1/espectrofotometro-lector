# -*- coding: utf-8 -*-
"""Pruebas de los TIEMPOS DE ESPERA del banco serie.  Sin hardware.

Motivo: el banco esperaba 0,4 s por sonda (SEGUNDOS, no minutos, aunque un
numero suelto se pueda leer de las dos formas).  La duda era razonable -- un
equipo de esta epoca puede tardar minuto y medio en volcar un espectro -- pero
subir la espera GLOBAL a 90 s convertiria la corrida exhaustiva en 110 horas.
La solucion es la ventana ADAPTATIVA: corta si nadie contesta, larga solo
cuando algo empieza a llegar.  Y una pausa de ASENTAMIENTO tras abrir el
puerto, para que la primera sonda no caiga al vacio.
"""
import os
import sys
import time
import unittest

MAESTRO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, MAESTRO)

from jenway67 import escaner_serie as es  # noqa: E402

SONDAS = [("A", b"*IDN?", "identificacion"), ("B", b"PING", "saludo")]
CONFIGS = [es.Config(9600, 8, "N", 1)]


# ---------------------------------------------------------------------------
# El simulador que contesta DESPACIO
# ---------------------------------------------------------------------------
class PuertoTardio:
    """Puerto de mentira que contesta en trozos repartidos en el tiempo.

    Imita lo que de verdad hace un instrumento al volcar un espectro: los bytes
    llegan a cuentagotas durante decenas de segundos, no de golpe.
    """

    def __init__(self, retardo=0.10, pausa=0.15, trozos=(b"JEN", b"WAY,6", b"705")):
        self.retardo = retardo
        self.pausa = pausa
        self.trozos = list(trozos)
        self._cola = bytearray()
        self._inicio = None
        self._momento = 0.0
        self.escrito = bytearray()
        self.timeout = 0.0
        self.dtr = True
        self.rts = True
        self.cts = False
        self.dsr = False
        self.ri = False
        self.cd = False

    @property
    def in_waiting(self):
        self._servir()
        return len(self._cola)

    def _servir(self):
        if self._inicio is None:
            return
        ahora = time.monotonic()
        while self.trozos and ahora - self._inicio >= self._momento:
            self._cola += self.trozos.pop(0)
            self._momento += self.pausa

    def write(self, datos):
        self.escrito += bytes(datos)
        self._inicio = time.monotonic()
        self._momento = self.retardo
        return len(datos)

    def read(self, n=1):
        self._servir()
        if not self._cola:
            time.sleep(0.002)
            return b""
        datos = bytes(self._cola[:n])
        del self._cola[:n]
        return datos

    def reset_input_buffer(self):
        self._cola.clear()

    def reset_output_buffer(self):
        pass

    def flush(self):
        pass

    def close(self):
        pass


class PuertoConReloj(es.PuertoSimulado):
    """Simulado que apunta cuando se abrio y cuando se envio lo primero."""

    def __init__(self, modo="silencio"):
        super().__init__(modo)
        self.abierto_en = time.monotonic()
        self.primer_envio_en = None

    def write(self, datos):
        if self.primer_envio_en is None:
            self.primer_envio_en = time.monotonic()
        return super().write(datos)


# ---------------------------------------------------------------------------
# Leer los tiempos que escribe el usuario
# ---------------------------------------------------------------------------
class TestParsearTiempo(unittest.TestCase):
    """Un numero suelto no dice nada: hay que poder escribir la unidad."""

    def test_numero_suelto_son_segundos(self):
        self.assertAlmostEqual(es.parsear_tiempo("0.4"), 0.4)
        self.assertAlmostEqual(es.parsear_tiempo("90"), 90.0)
        self.assertAlmostEqual(es.parsear_tiempo(0.4), 0.4)

    def test_con_unidad(self):
        casos = {
            "90s": 90.0,
            "0.5s": 0.5,
            "500ms": 0.5,
            "2m": 120.0,
            "1.5min": 90.0,
            "1m30s": 90.0,
            "1 h": 3600.0,
            "0,4": 0.4,
            "1M30S": 90.0,
            " 90 s ": 90.0,
        }
        for texto, esperado in casos.items():
            self.assertAlmostEqual(es.parsear_tiempo(texto), esperado, msg=texto)

    def test_lo_que_no_entiende_lo_dice(self):
        for malo in ("", "   ", "abc", "90x", "1m30", "-5s"):
            with self.assertRaises(ValueError, msg=malo):
                es.parsear_tiempo(malo)

    def test_el_minuto_y_el_segundo_no_son_lo_mismo(self):
        # El malentendido que motivo todo esto: 0.4 leido como minutos = 24 s.
        self.assertAlmostEqual(es.parsear_tiempo("0.4min"), 24.0)
        self.assertNotAlmostEqual(es.parsear_tiempo("0.4"), es.parsear_tiempo("0.4min"))

    def test_los_valores_por_defecto(self):
        # Los que anuncia el CLI y documenta la guia.
        self.assertAlmostEqual(es.VENTANA_POR_DEFECTO, 0.4)
        self.assertAlmostEqual(es.VENTANA_LARGA_POR_DEFECTO, 90.0)  # minuto y medio
        self.assertAlmostEqual(es.ASENTAMIENTO_POR_DEFECTO, 1.5)


# ---------------------------------------------------------------------------
# La ventana adaptativa
# ---------------------------------------------------------------------------
class TestVentanaAdaptativa(unittest.TestCase):
    def test_sin_ventana_larga_la_respuesta_lenta_se_corta(self):
        """Con la ventana corta y nada mas, solo se captura el primer trozo."""
        puerto = PuertoTardio()
        inicio = time.monotonic()
        filas = es.sondear_config(puerto, CONFIGS[0], sondas=SONDAS[:1], ventana=0.15)
        tardanza = time.monotonic() - inicio
        self.assertEqual(filas[0].n_bytes, 3)  # b"JEN", lo demas llega despues
        self.assertLess(tardanza, 0.5)

    def test_con_ventana_larga_se_captura_entera(self):
        """Con ventana adaptativa, la respuesta lenta se recibe completa."""
        puerto = PuertoTardio()
        filas = es.sondear_config(
            puerto, CONFIGS[0], sondas=SONDAS[:1], ventana=0.15, ventana_larga=2.0
        )
        self.assertEqual(filas[0].n_bytes, 11)  # los tres trozos: 3 + 5 + 3
        self.assertGreater(filas[0].espera_s, 0.15)  # espero de mas, a proposito
        self.assertLess(filas[0].espera_s, 2.0)  # pero no se quedo pegado

    def test_el_silencio_no_paga_la_ventana_larga(self):
        """La razon de que la ventana larga sea adaptativa y no fija.

        Con 90 s fijos, la corrida agotadora (4410 sondas) serian 110 horas.
        """
        puerto = es.PuertoSimulado("silencio")
        inicio = time.monotonic()
        filas = es.sondear_config(
            puerto, CONFIGS[0], sondas=SONDAS, ventana=0.1, ventana_larga=5.0
        )
        tardanza = time.monotonic() - inicio
        self.assertEqual([f.n_bytes for f in filas], [0, 0])
        self.assertLess(tardanza, 1.0)  # 2 sondas x 0,1 s... NO 2 x 5 s

    def test_la_ventana_larga_tiene_tope(self):
        """Si el equipo no calla nunca, el tope evita que la corrida se cuelgue."""
        puerto = PuertoTardio(retardo=0.05, pausa=0.05, trozos=(b"a",) * 200)
        puerto.write(b"X")  # el puerto mide los tiempos desde su primer envio
        inicio = time.monotonic()
        datos = es.leer_hasta_que_calle(puerto, 0.1, 1.0, silencio=0.2)
        tardanza = time.monotonic() - inicio
        self.assertGreater(len(datos), 0)
        self.assertLessEqual(tardanza, 1.4)

    def test_una_consulta_rapida_cuesta_la_ventana_corta(self):
        """El caso normal (un idn): la ventana larga no se nota."""
        puerto = es.PuertoSimulado("idn")
        inicio = time.monotonic()  # SONDA="*IDN?" es la que este modo contesta
        filas = es.sondear_config(
            puerto, CONFIGS[0], sondas=SONDAS[:1], ventana=0.05, ventana_larga=90.0
        )
        tardanza = time.monotonic() - inicio
        self.assertGreater(filas[0].n_bytes, 0)
        self.assertLess(tardanza, 1.0)  # no espera los 90 s


# ---------------------------------------------------------------------------
# El asentamiento tras abrir el puerto
# ---------------------------------------------------------------------------
class TestAsentamiento(unittest.TestCase):
    """Sin esta pausa la primera sonda puede caer al vacio y ensuciar la config."""

    def _correr(self, asentar):
        creados = []

        def abrir(_puerto, _config):
            puerto = PuertoConReloj()
            creados.append(puerto)
            return puerto

        info = es.escanear(
            puerto="COM3",
            abrir=abrir,
            configs=CONFIGS,
            sondas=SONDAS,
            ventana=0.05,
            asentar=asentar,
            simulado="silencio",
        )
        return info, creados

    def test_espera_antes_de_la_primera_sonda(self):
        info, creados = self._correr(0.3)
        puerto = creados[0]
        self.assertIsNotNone(puerto.primer_envio_en)
        self.assertGreaterEqual(puerto.primer_envio_en - puerto.abierto_en, 0.28)
        self.assertAlmostEqual(info["asentar_s"], 0.3)

    def test_se_puede_desactivar(self):
        _info, creados = self._correr(0.0)
        puerto = creados[0]
        self.assertIsNotNone(puerto.primer_envio_en)
        self.assertLess(puerto.primer_envio_en - puerto.abierto_en, 0.15)


# ---------------------------------------------------------------------------
# Que el informe lo diga (nada de promesas invisibles)
# ---------------------------------------------------------------------------
class TestInformeDeTiempos(unittest.TestCase):
    @staticmethod
    def _abridor():
        return lambda _puerto, _config: es.PuertoSimulado("silencio")

    def test_el_informe_declara_los_tiempos(self):
        info = es.escanear(
            puerto="COM3",
            abrir=self._abridor(),
            configs=CONFIGS,
            sondas=SONDAS,
            ventana=0.05,
            ventana_larga=90.0,
            asentar=0.05,
            simulado="silencio",
        )
        texto = es.informe_texto(info)
        self.assertIn("ampliable a 90.0 s", texto)
        self.assertIn("Asentamiento", texto)
        self.assertAlmostEqual(info["ventana_larga_s"], 90.0)

    def test_sin_ventana_larga_no_promete_nada(self):
        info = es.escanear(
            puerto="COM3",
            abrir=self._abridor(),
            configs=CONFIGS,
            sondas=SONDAS,
            ventana=0.05,
            simulado="silencio",
        )
        texto = es.informe_texto(info)
        self.assertNotIn("ampliable", texto)
        self.assertNotIn("Asentamiento", texto)

    def test_la_espera_real_queda_en_el_informe(self):
        """El dato que dice si el equipo se quedo a medias: cuanto se escucho."""
        info = es.escanear(
            puerto="COM3",
            abrir=self._abridor(),
            configs=CONFIGS,
            sondas=SONDAS,
            ventana=0.05,
            ventana_larga=2.0,
            simulado="silencio",
        )
        for fila in info["resultados"]:
            self.assertIn("espera_s", fila)
            self.assertGreaterEqual(fila["espera_s"], 0.0)
            self.assertLess(fila["espera_s"], 1.0)  # silencio = ventana corta


if __name__ == "__main__":
    unittest.main()
