# -*- coding: utf-8 -*-
"""Pruebas del clasificador de lecturas: respuesta real vs eco vs ARTEFACTO.

Motivo: la primera corrida real contra el 6705 (23/09 10:35) anuncio "el equipo
habla" con 88 lecturas.  84 de ellas eran el MISMO byte -- 0xFF cuando el puerto
iba a 8 bits de datos y 0x7F cuando iba a 7 -- que es la linea en reposo leida
como si fuera un bit de arranque: un artefacto de recepcion, no contenido del
equipo.  El banco no puede volver a llamar "respuesta" a eso.
"""
import os
import sys
import unittest

MAESTRO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, MAESTRO)

from jenway67 import escaner_serie as es  # noqa: E402


def fila(config="9600 8N1", sonda="X", enviado="05", recibido="", eco=False, error=""):
    return es.Resultado(
        config=config,
        sonda=sonda,
        enviado_hex=enviado,
        recibido_hex=recibido,
        texto="",
        n_bytes=len(recibido.split()),
        eco=eco,
        error=error,
    )


class TestBitsDeEtiqueta(unittest.TestCase):
    def test_lee_los_bits_de_datos(self):
        self.assertEqual(es.bits_de_etiqueta("9600 8N1"), 8)
        self.assertEqual(es.bits_de_etiqueta("9600 7E1"), 7)
        self.assertEqual(es.bits_de_etiqueta("115200 8N1"), 8)

    def test_si_no_lo_entiende_devuelve_cero(self):
        for mala in ("", "9600", "9600 XX", "sin-formato", None):
            self.assertEqual(es.bits_de_etiqueta(mala), 0, msg=mala)


class TestTodoAUno(unittest.TestCase):
    """FF con 8 bits, 7F con 7: el valor lo decide NUESTRA configuracion."""

    def test_ff_es_artefacto_a_8_bits(self):
        self.assertTrue(es.es_todo_a_uno("FF", 8))
        self.assertTrue(es.es_todo_a_uno("FF FF FF", 8))

    def test_7f_es_artefacto_a_7_bits(self):
        self.assertTrue(es.es_todo_a_uno("7F", 7))
        self.assertTrue(es.es_todo_a_uno("7F 7F", 7))

    def test_la_misma_lectura_cambia_con_nuestros_bits(self):
        # Este es EL argumento: el instrumento no puede saber como tenemos el puerto.
        self.assertFalse(es.es_todo_a_uno("7F", 8))
        self.assertFalse(es.es_todo_a_uno("FF", 7))

    def test_cualquier_otro_valor_no_es_artefacto(self):
        for valor in ("00", "E6", "36 37 58 58 20 0D", "FF 00"):
            self.assertFalse(es.es_todo_a_uno(valor, 8), msg=valor)

    def test_vacio_no_es_artefacto(self):
        self.assertFalse(es.es_todo_a_uno("", 8))


class TestClasificar(unittest.TestCase):
    def test_separa_los_cuatro_grupos(self):
        filas = [
            fila(recibido="FF", enviado="05"),                      # artefacto 8 bits
            fila(recibido="FF FF", enviado="2A 49 44 4E 3F 0D"),    # artefacto
            fila(config="9600 7E1", recibido="7F", enviado="0D"),   # artefacto 7 bits
            fila(recibido="05", enviado="05", eco=True),            # eco
            fila(recibido="36 37 58 58 20 0D", enviado="2A 49 44 4E 3F 0D"),  # real
        ]
        partes = es.clasificar(filas)
        self.assertEqual(len(partes["artefactos"]), 3)
        self.assertEqual(len(partes["ecos"]), 1)
        self.assertEqual(len(partes["reales"]), 1)
        self.assertEqual(partes["reales"][0].recibido_hex, "36 37 58 58 20 0D")

    def test_la_misma_respuesta_a_preguntas_distintas_no_es_respuesta(self):
        filas = [fila(sonda="S%d" % i, enviado="%02X" % i, recibido="41 42")
                 for i in range(3)]
        partes = es.clasificar(filas)
        self.assertEqual(len(partes["reales"]), 0)
        self.assertEqual(len(partes["repetidos"]), 3)

    def test_dos_veces_el_mismo_valor_aun_se_tolera(self):
        """Con dos no basta: una consulta y su variante pueden dar lo mismo."""
        filas = [
            fila(sonda="A", enviado="2A 49 44 4E 3F 0D", recibido="36 37"),
            fila(sonda="B", enviado="02 2A 49 44 4E 3F 03", recibido="36 37"),
        ]
        partes = es.clasificar(filas)
        self.assertEqual(len(partes["reales"]), 2)
        self.assertEqual(len(partes["repetidos"]), 0)

    def test_los_vacios_y_los_errores_no_cuentan(self):
        filas = [fila(recibido=""), fila(recibido="FF", error="se cayo el puerto")]
        partes = es.clasificar(filas)
        for grupo in ("reales", "repetidos", "artefactos", "ecos"):
            self.assertEqual(len(partes[grupo]), 0, msg=grupo)


class TestVeredictoConArtefactos(unittest.TestCase):
    def test_solo_artefactos_no_es_respuesta(self):
        filas = [fila(recibido="FF", enviado="05"), fila(config="9600 7E1", recibido="7F", enviado="0D")]
        texto = es.veredicto(filas)
        self.assertIn("POSIBLE ARTEFACTO", texto)
        self.assertNotIn("El equipo habla", texto)
        self.assertIn("--sondas control", texto)

    def test_respuesta_real_sigue_siendo_respuesta(self):
        filas = [fila(recibido="36 37 58 58 20 0D", enviado="2A 49 44 4E 3F 0D")]
        self.assertIn("RESPUESTA: 1", es.veredicto(filas))

    def test_la_corrida_real_del_6705_ya_no_se_llama_respuesta(self):
        """Reproduce el patron medido: FF/7F por todas partes."""
        filas = [fila(config=c, enviado="05", recibido=v) for c, v in (
            ("9600 8N1", "FF"), ("9600 8N2", "FF"), ("9600 8E1", "FF"),
            ("19200 8N1", "FF"), ("9600 7E1", "7F"), ("9600 7O1", "7F"),
        )]
        texto = es.veredicto(filas)
        self.assertIn("POSIBLE ARTEFACTO: 6", texto)
        self.assertNotIn("El equipo habla", texto)

    def test_cuando_hay_respuesta_y_artefactos_avisa_de_los_descartados(self):
        filas = [
            fila(recibido="36 37 58 58 20 0D", enviado="2A 49 44 4E 3F 0D"),
            fila(recibido="FF", enviado="05"), fila(recibido="FF FF", enviado="00"),
        ]
        texto = es.veredicto(filas)
        self.assertIn("RESPUESTA: 1", texto)
        self.assertIn("2 artefacto(s)", texto)


class TestSondasDeControl(unittest.TestCase):
    def test_el_juego_de_control_existe_y_es_corto(self):
        juego = es.juego_de_sondas("control")
        self.assertEqual(len(juego), 6)
        self.assertIn("CTL-INERTE", [n for n, _c, _d in juego])

    def test_control_trae_las_dos_comparaciones_que_deciden(self):
        cargas = {n: c for n, c, _d in es.juego_de_sondas("control")}
        # mismo TAMANO, distinto CONTENIDO
        a, b, c = cargas["CTL-TAM-A"], cargas["CTL-TAM-B"], cargas["CTL-TAM-C"]
        self.assertEqual(len(a), len(b))
        self.assertEqual(len(a), len(c))
        self.assertNotEqual(a, b)
        self.assertNotEqual(a, c)
        # mismo CONTENIDO, distinto TAMANO
        self.assertTrue(cargas["CTL-LARGO"].startswith(b"A"))
        self.assertTrue(cargas["CTL-CORTO"].startswith(b"A"))
        self.assertGreater(len(cargas["CTL-LARGO"]), len(cargas["CTL-CORTO"]))

    def test_el_juego_de_control_no_lleva_estado_ni_barrido(self):
        juego = es.juego_de_sondas("control", permitir_estado=True, barrido_bytes=True)
        self.assertEqual(len(juego), 6)

    def test_nivel_invalido_lo_dice(self):
        with self.assertRaises(ValueError):
            es.juego_de_sondas("inventado")


class TestMarcaDeAmpliacion(unittest.TestCase):
    """El marcador no puede decir "espera ampliada" en una fila vacia."""

    CONFIG = [es.Config(9600, 8, "N", 1)]
    SONDA = [("A", b"*IDN?", "identificacion")]

    def test_silencio_no_marca_ampliacion(self):
        puerto = es.PuertoSimulado("silencio")
        filas = es.sondear_config(puerto, self.CONFIG[0], sondas=self.SONDA,
                                  ventana=0.05, ventana_larga=2.0)
        self.assertEqual(filas[0].n_bytes, 0)
        self.assertFalse(filas[0].ampliada)

    def test_con_respuesta_si_marca(self):
        puerto = es.PuertoSimulado("idn")
        filas = es.sondear_config(puerto, self.CONFIG[0], sondas=self.SONDA,
                                  ventana=0.05, ventana_larga=2.0)
        self.assertGreater(filas[0].n_bytes, 0)
        self.assertTrue(filas[0].ampliada)

    def test_el_informe_no_marca_la_fila_vacia(self):
        abrir = lambda _p, _c: es.PuertoSimulado("silencio")  # noqa: E731
        info = es.escanear(puerto="COM3", abrir=abrir, configs=self.CONFIG,
                           sondas=self.SONDA, ventana=0.05, ventana_larga=2.0,
                           simulado="silencio")
        self.assertNotIn("ESPERA AMPLIADA", es.informe_texto(info))

    def test_el_informe_marca_el_artefacto(self):
        abrir = lambda _p, _c: es.PuertoSimulado("idn")  # noqa: E731
        info = es.escanear(puerto="COM3", abrir=abrir, configs=self.CONFIG,
                           sondas=[("ART", b"*IDN?", "forzado")],
                           ventana=0.05, simulado="idn")
        # El simulador contesta texto real: no debe marcarse como artefacto.
        self.assertNotIn("ARTEFACTO", es.informe_texto(info))


if __name__ == "__main__":
    unittest.main()