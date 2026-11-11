# -*- coding: utf-8 -*-
"""Pruebas del banco de pruebas serie.  NO necesitan hardware: el puerto se
inyecta (:class:`jenway67.escaner_serie.PuertoSimulado`)."""
import json
import os
import sys
import tempfile
import unittest

MAESTRO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, MAESTRO)

from jenway67 import escaner_serie as es  # noqa: E402

# Listas minimas para que las pruebas corran en milisegundos.
CONFIGS = [es.Config(9600, 8, "N", 1), es.Config(9600, 7, "E", 1)]
SONDAS = [("ENQ", b"\x05", "peticion de atencion"), ("IDN", b"*IDN?\r", "identificacion")]
VENTANA = 0.02


def abridor(modo):
    """Abridor falso: cada llamada da un puerto simulado del modo pedido."""
    creados = []

    def abrir(_puerto, _config):
        puerto = es.PuertoSimulado(modo)
        creados.append(puerto)
        return puerto

    return abrir, creados


def escanear_simulado(modo, **extra):
    abrir, creados = abridor(modo)
    info = es.escanear(
        puerto="COM3",
        abrir=abrir,
        configs=extra.pop("configs", CONFIGS),
        sondas=extra.pop("sondas", SONDAS),
        ventana=extra.pop("ventana", VENTANA),
        simulado=modo,
        **extra
    )
    return info, creados


class TestConfiguraciones(unittest.TestCase):
    def test_etiqueta(self):
        self.assertEqual(es.Config(9600, 7, "E", 1).etiqueta, "9600 7E1")
        self.assertEqual(es.Config(115200, 8, "N", 2).etiqueta, "115200 8N2")

    def test_probables_no_vacio_y_unicas(self):
        configs = es.configuraciones()
        self.assertGreaterEqual(len(configs), 10)
        etiquetas = [c.etiqueta for c in configs]
        self.assertEqual(len(etiquetas), len(set(etiquetas)))

    def test_completas_incluyen_las_probables(self):
        probables = set(c.etiqueta for c in es.configuraciones())
        completas = es.configuraciones(completo=True)
        self.assertGreater(len(completas), len(probables))
        self.assertTrue(probables.issubset(set(c.etiqueta for c in completas)))

    def test_kwargs_lleva_la_velocidad(self):
        self.assertEqual(es.Config(4800, 8, "N", 1).kwargs()["baudrate"], 4800)
        if es.HAY_PYSERIAL:
            self.assertIn("bytesize", es.Config(9600, 7, "E", 1).kwargs())


class TestSeguridadDeLasSondas(unittest.TestCase):
    def test_sondas_benignas(self):
        """Ninguna sonda debe llevar ordenes destructivas."""
        self.assertTrue(es.sondas_benignas())
        for _nombre, carga, _desc in es.SONDAS:
            self.assertIsInstance(carga, bytes)
            self.assertGreater(len(carga), 0)

    def test_nombres_unicos(self):
        nombres = [n for n, _c, _d in es.SONDAS]
        self.assertEqual(len(nombres), len(set(nombres)))

    def test_hay_sondas_de_handshake_e_identificacion(self):
        cargas = [c for _n, c, _d in es.SONDAS]
        self.assertIn(b"\x05", cargas)          # ENQ
        self.assertTrue(any(b"*IDN?" in c for c in cargas))


class TestVolcados(unittest.TestCase):
    def test_hex(self):
        self.assertEqual(es.volcado_hex(b"\x05A"), "05 41")
        self.assertEqual(es.volcado_hex(b""), "")

    def test_legible(self):
        self.assertEqual(es.volcado_legible(b"AB\x00C"), "AB.C")
        self.assertEqual(es.volcado_legible(b"\r\n"), "..")


class TestPuertos(unittest.TestCase):
    def test_inventario_es_lista(self):
        self.assertIsInstance(es.puertos_disponibles(), list)

    def test_elegir_puerto_prefiere_ftdi(self):
        inventario = [
            {"puerto": "COM7", "vid_pid": "1234:5678"},
            {"puerto": "COM3", "vid_pid": "0403:6001"},
        ]
        self.assertEqual(es.elegir_puerto(inventario), "COM3")

    def test_elegir_puerto_respeta_el_pedido(self):
        inventario = [{"puerto": "COM3", "vid_pid": "0403:6001"}]
        self.assertEqual(es.elegir_puerto(inventario, "COM9"), "COM9")

    def test_elegir_puerto_sin_inventario(self):
        self.assertEqual(es.elegir_puerto([]), "")

    def test_pyserial_es_bandera_booleana(self):
        self.assertIsInstance(es.HAY_PYSERIAL, bool)


class TestLecturaYLineas(unittest.TestCase):
    def test_leer_hasta_recoge_lo_que_llega(self):
        puerto = es.PuertoSimulado("eco")
        puerto.write(b"HOLA")
        self.assertEqual(es.leer_hasta(puerto, 0.05), b"HOLA")

    def test_leer_hasta_sin_datos(self):
        self.assertEqual(es.leer_hasta(es.PuertoSimulado("silencio"), 0.05), b"")

    def test_estado_lineas(self):
        lineas = es.estado_lineas(es.PuertoSimulado("silencio"))
        self.assertTrue(lineas["dtr"])
        self.assertFalse(lineas["cts"])

    def test_estado_lineas_tolera_objetos_raros(self):
        class Pelado(object):
            pass

        lineas = es.estado_lineas(Pelado())
        self.assertIsNone(lineas["cts"])


class TestSondeo(unittest.TestCase):
    def test_silencio_no_recibe_nada(self):
        resultados = es.sondear_config(es.PuertoSimulado("silencio"), CONFIGS[0], SONDAS, VENTANA)
        self.assertEqual(len(resultados), len(SONDAS))
        self.assertTrue(all(r.n_bytes == 0 for r in resultados))
        self.assertTrue(all(not r.eco for r in resultados))
        # Lo enviado si queda registrado, aunque no haya respuesta.
        self.assertEqual(resultados[0].enviado_hex, "05")

    def test_eco_detectado_y_marcado(self):
        resultados = es.sondear_config(es.PuertoSimulado("eco"), CONFIGS[0], SONDAS, VENTANA)
        self.assertTrue(all(r.eco for r in resultados))
        self.assertEqual(resultados[1].recibido_hex, es.volcado_hex(b"*IDN?\r"))

    def test_respuesta_real_no_es_eco(self):
        resultados = es.sondear_config(es.PuertoSimulado("idn"), CONFIGS[0], SONDAS, VENTANA)
        con_datos = [r for r in resultados if r.n_bytes]
        self.assertEqual(len(con_datos), 1)
        self.assertFalse(con_datos[0].eco)
        self.assertEqual(con_datos[0].sonda, "IDN")
        self.assertIn("JENWAY", con_datos[0].texto)


class TestVeredicto(unittest.TestCase):
    def test_reconoce_respuesta(self):
        info, _ = escanear_simulado("idn")
        self.assertTrue(info["veredicto"].startswith("RESPUESTA"))
        self.assertEqual(info["bytes_recibidos"] > 0, True)

    def test_reconoce_solo_eco(self):
        info, _ = escanear_simulado("eco")
        self.assertTrue(info["veredicto"].startswith("SOLO ECO"))

    def test_reconoce_silencio_total(self):
        info, _ = escanear_simulado("silencio")
        self.assertTrue(info["veredicto"].startswith("SILENCIO TOTAL"))
        self.assertEqual(info["bytes_recibidos"], 0)


class TestEscanear(unittest.TestCase):
    def test_reabre_el_puerto_por_configuracion_y_no_lo_deja_abierto(self):
        info, creados = escanear_simulado("silencio")
        self.assertEqual(len(info["resultados"]), len(CONFIGS) * len(SONDAS))
        self.assertEqual(len(creados), len(CONFIGS))
        self.assertTrue(all(p.cerrado for p in creados))

    def test_las_filas_llevan_el_estado_de_lineas(self):
        info, _ = escanear_simulado("silencio")
        self.assertIn("lineas", info["resultados"][0])
        self.assertIn("cts", info["resultados"][0]["lineas"])

    def test_progreso_y_avisos_se_invocan(self):
        eventos, avisos = [], []
        escanear_simulado(
            "idn",
            progreso=lambda i, t, e, m: eventos.append((i, t, e, m)),
            al_recibir=lambda fila: avisos.append(fila["sonda"]),
        )
        self.assertEqual(len(eventos), len(CONFIGS))
        self.assertEqual(eventos[0][0], 1)
        self.assertEqual(eventos[0][1], len(CONFIGS))
        self.assertEqual(avisos, ["IDN", "IDN"])

    def test_escucha_pasiva_sin_datos(self):
        info, _ = escanear_simulado("silencio", escuchar_segundos=0.05)
        self.assertIsNotNone(info["pasiva"])
        self.assertEqual(info["bytes_pasivos"], 0)
        self.assertEqual(info["pasiva"]["datos_hex"], "")

    def test_sin_puerto_no_revienta(self):
        info = es.escanear(puerto="", abrir=abridor("silencio")[0], configs=CONFIGS, sondas=SONDAS)
        self.assertTrue(info["veredicto"].startswith("NO HAY PUERTO"))
        self.assertEqual(info["resultados"], [])

    def test_sin_configuraciones_no_revienta(self):
        info = es.escanear(puerto="COM3", abrir=abridor("silencio")[0], configs=[], sondas=SONDAS)
        self.assertTrue(info["veredicto"].startswith("NADA QUE PROBAR"))

    def test_puerto_que_no_abre_lo_dice(self):
        def abrir_mal(_puerto, _config):
            raise OSError("Acceso denegado (COM3 ocupado)")

        info = es.escanear(puerto="COM3", abrir=abrir_mal, configs=CONFIGS, sondas=SONDAS)
        self.assertTrue(info["veredicto"].startswith("NO SE PUDO ABRIR"))
        self.assertIn("Acceso denegado", info["error"])

    def test_apertura_fallida_a_mitad_no_tumba_el_barrido(self):
        estado = {"n": 0}

        def abrir_a_veces(_puerto, _config):
            estado["n"] += 1
            if estado["n"] == 2:
                raise OSError("se solto el cable")
            return es.PuertoSimulado("silencio")

        info = es.escanear(
            puerto="COM3", abrir=abrir_a_veces, configs=CONFIGS, sondas=SONDAS, ventana=VENTANA
        )
        filas_error = [f for f in info["resultados"] if f.get("error")]
        self.assertEqual(len(filas_error), 1)
        self.assertIn("se solto el cable", filas_error[0]["error"])


class TestInformeYGuardado(unittest.TestCase):
    def test_informe_texto_tiene_secciones(self):
        info, _ = escanear_simulado("idn")
        texto = es.informe_texto(info)
        for esperado in ("BANCO DE PRUEBAS SERIE", "Configuraciones", "Barrido", "VEREDICTO"):
            self.assertIn(esperado, texto)
        self.assertIn("JENWAY", texto)

    def test_informe_marca_las_corridas_simuladas(self):
        info, _ = escanear_simulado("idn")
        self.assertIn("SIMULADO", es.informe_texto(info))

    def test_guardar_escribe_txt_y_json(self):
        info, _ = escanear_simulado("silencio")
        with tempfile.TemporaryDirectory() as carpeta:
            rutas = es.guardar(info, carpeta)
            self.assertTrue(os.path.isfile(rutas["txt"]))
            self.assertTrue(os.path.isfile(rutas["json"]))
            with open(rutas["json"], "r", encoding="utf-8") as manejador:
                cargado = json.load(manejador)
            self.assertEqual(cargado["puerto"], "COM3")
            self.assertEqual(len(cargado["resultados"]), len(CONFIGS) * len(SONDAS))
            self.assertTrue(os.path.basename(rutas["txt"]).endswith("_SIMULADO.txt"))

    def test_guardar_crea_la_carpeta(self):
        info, _ = escanear_simulado("silencio")
        with tempfile.TemporaryDirectory() as carpeta:
            destino = os.path.join(carpeta, "nueva", "sub")
            rutas = es.guardar(info, destino)
            self.assertTrue(os.path.isfile(rutas["txt"]))

    def test_envolver_texto(self):
        lineas = es._envolver("palabra " * 40, 40)
        self.assertTrue(all(len(linea) <= 42 for linea in lineas))


class TestControlDeFlujoYLineas(unittest.TestCase):
    """Ejes anadidos para no dar un "silencio" falso: handshake y DTR/RTS."""

    def test_etiqueta_con_flujo_y_lineas(self):
        self.assertEqual(es.Config(9600, 8, "N", 1, flujo="rtscts").etiqueta, "9600 8N1 rtscts")
        self.assertEqual(es.Config(9600, 8, "N", 1, lineas="off").etiqueta, "9600 8N1 sin-DTR/RTS")
        self.assertEqual(
            es.Config(9600, 7, "E", 1, flujo="xonxoff", lineas="off").etiqueta,
            "9600 7E1 xonxoff sin-DTR/RTS",
        )

    def test_kwargs_llevan_el_flujo(self):
        if not es.HAY_PYSERIAL:
            self.skipTest("sin pyserial")
        self.assertFalse(es.Config(9600, 8, "N", 1).kwargs()["rtscts"])
        self.assertTrue(es.Config(9600, 8, "N", 1, flujo="rtscts").kwargs()["rtscts"])
        self.assertTrue(es.Config(9600, 8, "N", 1, flujo="xonxoff").kwargs()["xonxoff"])
        self.assertTrue(es.Config(9600, 8, "N", 1, flujo="dsrdtr").kwargs()["dsrdtr"])

    def test_configuraciones_globales_con_flujo(self):
        configs = es.configuraciones(flujo="rtscts")
        self.assertTrue(all(c.flujo == "rtscts" for c in configs))
        self.assertGreaterEqual(len(configs), 10)

    def test_completas_incluyen_handshake_y_sin_lineas(self):
        etiquetas = [c.etiqueta for c in es.configuraciones(completo=True)]
        self.assertTrue(any("rtscts" in e for e in etiquetas))
        self.assertTrue(any("sin-DTR/RTS" in e for e in etiquetas))

    def test_lineas_off_baja_dtr_y_rts_de_verdad(self):
        abrir, creados = abridor("silencio")
        config = es.Config(9600, 8, "N", 1, lineas="off")
        es.escanear(puerto="COM3", abrir=abrir, configs=[config], sondas=SONDAS, ventana=VENTANA)
        self.assertTrue(creados)
        self.assertTrue(all(not p.dtr and not p.rts for p in creados))

    def test_lineas_on_las_deja_activas(self):
        abrir, creados = abridor("silencio")
        es.escanear(puerto="COM3", abrir=abrir, configs=[CONFIGS[0]], sondas=SONDAS, ventana=VENTANA)
        self.assertTrue(all(p.dtr and p.rts for p in creados))

    def test_el_informe_muestra_las_lineas_bajadas(self):
        abrir, _ = abridor("silencio")
        config = es.Config(9600, 8, "N", 1, lineas="off")
        info = es.escanear(
            puerto="COM3", abrir=abrir, configs=[config], sondas=SONDAS[:1], ventana=VENTANA
        )
        self.assertFalse(info["resultados"][0]["lineas"]["dtr"])
        self.assertIn("sin-DTR/RTS", es.informe_texto(info))


class TestJuegosDeSondas(unittest.TestCase):
    """Las sondas se separan por lo que HACEN: preguntar o cambiar estado.

    El juego por defecto tiene que poder seguir describiéndose como "solo
    pregunta", y eso se comprueba aquí.
    """

    def test_rapidas_es_el_juego_de_siempre(self):
        self.assertEqual(es.juego_de_sondas("rapidas"), es.SONDAS_RAPIDAS)
        self.assertEqual(len(es.SONDAS_RAPIDAS), 11)

    def test_ampliadas_es_mas_grande_que_rapidas(self):
        self.assertEqual(es.juego_de_sondas("ampliadas"), es.SONDAS_AMPLIADAS)
        self.assertGreater(len(es.SONDAS_AMPLIADAS), len(es.SONDAS_RAPIDAS))

    def test_las_nuevas_consultas_estan_todas(self):
        nombres = [n for n, _c, _d in es.SONDAS_AMPLIADAS]
        esperadas = ("STA", "RDG", "TYP", "MOD", "WAV", "DAT",
                     "SYS", "OPC", "STB", "ESE",
                     "HELLO", "STAT2",
                     "JNWY", "CONN", "HELO", "LIST", "DIR", "READY",
                     "2CR", "3CR")
        for esperado in esperadas:
            self.assertIn(esperado, nombres)
        self.assertEqual(len(es.SONDAS_AMPLIADAS), len(es.SONDAS_RAPIDAS) + 20)

    def test_los_nombres_del_juego_ampliado_no_se_repiten(self):
        nombres = [n for n, _c, _d in es.SONDAS_AMPLIADAS]
        self.assertEqual(len(nombres), len(set(nombres)))

    def test_las_consultas_no_incluyen_las_de_estado(self):
        for nivel in ("rapidas", "ampliadas"):
            nombres = [n for n, _c, _d in es.juego_de_sondas(nivel)]
            for nombre, _carga, _desc in es.SONDAS_ESTADO:
                with self.subTest(nivel=nivel, sonda=nombre):
                    self.assertNotIn(nombre, nombres)

    def test_las_sondas_de_estado_solo_entran_si_se_piden(self):
        sin_estado = es.juego_de_sondas("ampliadas")
        con_estado = es.juego_de_sondas("ampliadas", permitir_estado=True)
        self.assertEqual(len(con_estado), len(sin_estado) + len(es.SONDAS_ESTADO))
        nombres = [n for n, _c, _d in con_estado]
        for nombre, _carga, _desc in es.SONDAS_ESTADO:
            self.assertIn(nombre, nombres)

    def test_por_que_las_de_estado_estan_aparte(self):
        """Documenta el motivo: no son consultas puras."""
        cargas = {n: c for n, c, _d in es.SONDAS_ESTADO}
        self.assertIn(b"\x15", cargas["NAK3"])              # XMODEM: pedir bloque
        self.assertTrue(cargas["CRCC"].startswith(b"C"))    # XMODEM-CRC
        self.assertEqual(cargas["CLS"], b"*CLS\r")          # limpia banderas
        self.assertEqual(cargas["ATT"], b"AT\r")
        # Ninguna de ellas puede estar además entre las consultas.
        consultas = {c for _n, c, _d in es.SONDAS_AMPLIADAS}
        for carga in cargas.values():
            self.assertNotIn(carga, consultas)

    def test_barrido_de_bytes_cubre_los_256_valores(self):
        barrido = es.sondas_de_bytes()
        self.assertEqual(len(barrido), 256)
        cargas = [c for _n, c, _d in barrido]
        self.assertEqual(len(set(cargas)), 256)
        self.assertIn(b"\x00", cargas)
        self.assertIn(b"\x7f", cargas)
        self.assertIn(b"\xff", cargas)

    def test_el_barrido_se_anade_aparte(self):
        sondas = es.juego_de_sondas("rapidas", barrido_bytes=True)
        self.assertEqual(len(sondas), len(es.SONDAS_RAPIDAS) + 256)

    def test_el_barrido_conserva_el_formato_de_tres_campos(self):
        for fila in es.sondas_de_bytes()[:5]:
            self.assertEqual(len(fila), 3)
            self.assertIsInstance(fila[1], bytes)
            self.assertIsInstance(fila[2], str)

    def test_nivel_invalido(self):
        with self.assertRaises(ValueError):
            es.juego_de_sondas("inventado")

    def test_todos_los_juegos_de_consulta_siguen_siendo_benignos(self):
        self.assertTrue(es.sondas_benignas())


if __name__ == "__main__":
    unittest.main(verbosity=2)
