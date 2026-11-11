# -*- coding: utf-8 -*-
"""Pruebas de la Fase 0 (corrección de bugs y robustez del parseo).

Cubre:
  * Migración de .JWX / .JWU a ElementTree (incluye XML reordenado y con
    entidades HTML, que el parser por expresiones regulares toleraba).
  * Bug 1: la muestra de cuantificación se dibuja en (Abs, Conc interpolada).
  * Bug 2: el modo multi-longitud ya genera figura.
  * Bug 3: el directorio de salida es Xlsx/ (no Xslx/).
  * Bug 4: las métricas se agregan sobre TODAS las muestras del método.
"""
import math
import os
import sys
import tempfile
import unittest

MAESTRO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, MAESTRO)

from jenway67 import analisis as an                  # noqa: E402
from jenway67 import graficos as gr                  # noqa: E402
from jenway67 import informe as inf                  # noqa: E402
from jenway67.informe import analizar_carpeta        # noqa: E402
from jenway67.parser_jwb import decodificar          # noqa: E402
from jenway67.parser_jwu import parsear_jwu_bytes    # noqa: E402
from jenway67.parser_jwx import parsear_jwx_bytes    # noqa: E402
from jenway67.reader import leer_carpeta             # noqa: E402
from jenway67 import utilidades as u                 # noqa: E402
from jenway67.utilidades import raiz_xml             # noqa: E402

TARJETA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "tarjeta")
JWB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "jwb")

# XML deliberadamente hostil: atributos y etiquetas reordenados, y entidades
# HTML (&deg;) que XML no define -- el normalizador debe traducirlas.
JWX_RARO = (b'<summary>'
            b'<element type="1" id="7">'
            b'<method_name>Caf\xe9 &amp; agua a&deg;C</method_name>'
            b'<user>Alumnos</user>'
            b'<filename>abc123.JWB</filename>'
            b'<method_date>1/1/26 0:0:0</method_date>'
            b'<lock>0</lock>'
            b'<samples><s_data loc="abc123.JWB" val="Muestra 1" date="1/1/26" index="1"/></samples>'
            b'</element></summary>')


def lee_jwb(nombre):
    with open(os.path.join(JWB, nombre), "rb") as fh:
        return fh.read()


class TestXmlElementTree(unittest.TestCase):
    def test_jwx_todos_los_metodos(self):
        total = 0
        for fn in os.listdir(TARJETA):
            if fn.lower().endswith(".jwx"):
                with open(os.path.join(TARJETA, fn), "rb") as fh:
                    total += len(parsear_jwx_bytes(fh.read()))
        self.assertEqual(total, 18)

    def test_jwx_reordenado_y_entidades(self):
        metodos = parsear_jwx_bytes(JWX_RARO)
        self.assertEqual(len(metodos), 1)
        m = metodos[0]
        self.assertEqual(m.id, 7)
        self.assertEqual(m.modo, "spectrum")
        self.assertEqual(m.nombre, "Café & agua a°C")
        self.assertEqual(m.filename, "abc123.JWB")
        self.assertEqual(m.usuario, "Alumnos")
        self.assertEqual(len(m.muestras), 1)
        self.assertEqual(m.muestras[0].nombre, "Muestra 1")
        self.assertEqual(m.muestras[0].loc, "abc123.JWB")

    def test_jwu_usuarios(self):
        with open(os.path.join(TARJETA, "USERSINF.JWU"), "rb") as fh:
            usrs = parsear_jwu_bytes(fh.read())
        self.assertEqual(len(usrs), 3)
        d = {x.nombre: x.passcode for x in usrs}
        self.assertEqual(d.get("Generic"), "1234")
        self.assertEqual(d.get("Supervisor"), "1234")
        self.assertEqual(d.get("Alumnos"), "0000")

    def test_xml_invalido_no_revienta(self):
        self.assertIsNone(raiz_xml(b"esto no es xml"))
        self.assertEqual(parsear_jwx_bytes(b"esto no es xml"), [])
        self.assertEqual(parsear_jwu_bytes(b"<UserTable><User>"), [])   # truncado


class TestFiguraCuantificacion(unittest.TestCase):
    """Bug 1: la muestra debe ubicarse en (Absorbancia, Concentración interpolada)."""

    def test_muestra_usa_conc_interp(self):
        objetivo = None
        for m, dec in inf._agrupar(leer_carpeta(TARJETA)):
            if dec and dec[0][1] == "quantitation":
                objetivo = (m, dec)
                break
        self.assertIsNotNone(objetivo, "la tarjeta debe tener un método de cuantificación")
        m, dec = objetivo
        r0 = dec[0][2]
        esperada = an.cuantificacion(r0["estandares"], r0["abs_muestra"])["conc_interp"]

        capturado = {}
        original = gr.graficar_calibracion

        def falso(estandares, muestra_abs, salida, titulo="", conc_muestra=None):
            capturado["muestra_abs"] = muestra_abs
            capturado["conc_muestra"] = conc_muestra
            return salida + ".png"

        gr.graficar_calibracion = falso
        try:
            with tempfile.TemporaryDirectory() as tmp:
                inf._figura_por_modo("quantitation", dec, m, tmp)
        finally:
            gr.graficar_calibracion = original

        self.assertIsNotNone(capturado.get("conc_muestra"))
        self.assertAlmostEqual(capturado["conc_muestra"], esperada, places=4)
        # el bug original pasaba la absorbancia de la muestra como concentración
        self.assertNotAlmostEqual(capturado["conc_muestra"], capturado["muestra_abs"], places=2)

    def test_muestra_no_saturada_no_es_none(self):
        # con la absorbancia de la muestra como "concentración" el gráfico quedaba
        # en (A, A); verificamos además que el valor interpolado es pequeño y
        # distinto de la absorbancia (~0.09 vs ~0.77 en el fixture real).
        with open(os.path.join(JWB, "323BFC6F_quant.JWB"), "rb") as fh:
            _, r = decodificar(fh.read(), "quantitation")
        c = an.cuantificacion(r["estandares"], r["abs_muestra"])["conc_interp"]
        self.assertLess(c, r["abs_muestra"])


class TestFiguraMulti(unittest.TestCase):
    """Bug 2: el modo multi-longitud debe generar figura en la exportación."""

    def test_figura_multi(self):
        for m, dec in inf._agrupar(leer_carpeta(TARJETA)):
            if dec and dec[0][1] == "multi":
                with tempfile.TemporaryDirectory() as tmp:
                    p = inf._figura_por_modo("multi", dec, m, tmp)
                    self.assertIsNotNone(p, "multi debe generar figura")
                    self.assertTrue(os.path.exists(p))
                return
        self.fail("la tarjeta debe tener un método multi-longitud")


class TestDirectorioSalida(unittest.TestCase):
    """Bug 3: el directorio de salida es Xlsx/ (no Xslx/)."""

    def test_directorio_xlsx(self):
        with tempfile.TemporaryDirectory() as tmp:
            res = analizar_carpeta(leer_carpeta(TARJETA), tmp)
            self.assertTrue(os.path.exists(res["xlsx"]))
            self.assertIn("Xlsx", res["xlsx"])
            self.assertNotIn("Xslx", res["xlsx"])
            self.assertTrue(os.path.isdir(os.path.join(tmp, "Xlsx")))
            self.assertFalse(os.path.exists(os.path.join(tmp, "Xslx")))


class TestAgregacionTodasLasMuestras(unittest.TestCase):
    """Bug 4: las métricas se agregan sobre todas las muestras del método."""

    @classmethod
    def setUpClass(cls):
        _, cls.esp = decodificar(lee_jwb("323BE947_spectrum.JWB"), "spectrum")

    def test_una_muestra_coincide_con_el_valor_previo(self):
        a = inf._analisis_por_modo("spectrum", [(None, "spectrum", self.esp)])
        self.assertEqual(a["n_muestras"], 1)
        self.assertAlmostEqual(a["area_total"], an.area_bajo_curva(self.esp["puntos"]), places=3)
        self.assertEqual(a["picos"], len(an.picos(self.esp["puntos"])))

    def test_dos_muestras_se_agregan(self):
        dec = [(None, "spectrum", self.esp), (None, "spectrum", self.esp)]
        a = inf._analisis_por_modo("spectrum", dec)
        self.assertEqual(a["n_muestras"], 2)
        self.assertAlmostEqual(a["area_total"], 2 * a["area_media"], places=3)

    def test_kinetics_dos_muestras(self):
        _, kin = decodificar(lee_jwb("323BFE3F_kinetics.JWB"), "kinetics")
        dec = [(None, "kinetics", kin), (None, "kinetics", kin)]
        a = inf._analisis_por_modo("kinetics", dec)
        self.assertEqual(a["n_muestras"], 2)
        self.assertAlmostEqual(a["rate"], an.cinetica(kin["serie"])["rate"], places=6)
        self.assertEqual(a["rate_sd"], 0.0)

    def test_quantitation_una_muestra(self):
        _, q = decodificar(lee_jwb("323BFC6F_quant.JWB"), "quantitation")
        a = inf._analisis_por_modo("quantitation", [(None, "quantitation", q)])
        self.assertEqual(a["n_muestras"], 1)
        self.assertAlmostEqual(a["conc_interp"], 0.09, places=2)

    def test_multi_una_muestra(self):
        _, mu = decodificar(lee_jwb("323BEA26_multi.JWB"), "multi")
        a = inf._analisis_por_modo("multi", [(None, "multi", mu)])
        self.assertEqual(a["n_muestras"], 1)
        self.assertIsNotNone(a["A1"])
        self.assertIsNotNone(a["A1-A2"])

    def test_vacio(self):
        self.assertEqual(inf._analisis_por_modo("spectrum", []), {})


class TestHojasExcel(unittest.TestCase):
    """Los títulos de hoja deben ser únicos y de <= 31 caracteres (límite de
    Excel): al recortar a 31, dos métodos distintos colisionaban y openpyxl los
    renombraba por su cuenta, pasándose del límite."""

    def test_titulos_unicos_y_cortos(self):
        with tempfile.TemporaryDirectory() as tmp:
            res = analizar_carpeta(leer_carpeta(TARJETA), tmp)
            from openpyxl import load_workbook
            titulos = load_workbook(res["xlsx"]).sheetnames
        self.assertEqual(len(titulos), len(set(titulos)), "hay títulos repetidos")
        largos = [t for t in titulos if len(t) > 31]
        self.assertFalse(largos, f"títulos de más de 31 caracteres: {largos}")
        self.assertIn("Resumen", titulos)


class TestBoxplotSaturado(unittest.TestCase):
    """Una lectura saturada (Abs infinita) debe representarse como el display
    del instrumento (3.000), no llegar al boxplot como `inf`."""

    def test_usa_el_display_clampado(self):
        _, r_sat = decodificar(lee_jwb("323BE7BA_photo_sat.JWB"), "photometrics")
        _, r_ok = decodificar(lee_jwb("323BCBA4_photo_lowry.JWB"), "photometrics")
        self.assertTrue(math.isinf(r_sat["abs"]), "el fixture debe estar saturado")
        self.assertEqual(u.clamp_saturacion(r_sat["abs"]), 3.0)
        grupos = {"#1 (saturada)": [r_sat["abs"]], "#2": [r_ok["abs"]]}
        with tempfile.TemporaryDirectory() as tmp:
            p = gr.graficar_boxplot_fotometria(grupos, os.path.join(tmp, "box"))
            self.assertTrue(os.path.exists(p))


if __name__ == "__main__":
    unittest.main(verbosity=2)