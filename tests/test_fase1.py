# -*- coding: utf-8 -*-
"""Pruebas de la Fase 1: utilidades, parsers de índice/usuarios, reader, export."""
import math
import os
import sys
import tempfile
import unittest

MAESTRO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, MAESTRO)

from jenway67 import utilidades as u                       # noqa: E402
from jenway67.parser_jwx import parsear_jwx_bytes, MODO    # noqa: E402
from jenway67.parser_jwu import parsear_jwu_bytes          # noqa: E402
from jenway67.reader import leer_carpeta, decodificar_archivo  # noqa: E402
from jenway67.exportar import exportar_carpeta             # noqa: E402

TARJETA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "tarjeta")


class TestUtilidades(unittest.TestCase):
    def test_t_a(self):
        self.assertAlmostEqual(u.t_a(100.0), 0.0, places=5)
        self.assertAlmostEqual(u.t_a(10.0), 1.0, places=5)
        self.assertTrue(math.isinf(u.t_a(0.0)))
        self.assertAlmostEqual(u.a_t(1.0), 10.0, places=5)

    def test_clamp(self):
        self.assertEqual(u.clamp_saturacion(float("inf")), 3.0)
        self.assertEqual(u.clamp_saturacion(5.0), 3.0)
        self.assertAlmostEqual(u.clamp_saturacion(0.5), 0.5)

    def test_normalizar(self):
        self.assertEqual(u.normalizar_concentracion("0.09mM"), (0.09, "mM"))
        self.assertEqual(u.normalizar_concentracion("30.00 ppm"), (30.0, "ppm"))
        self.assertEqual(u.normalizar_concentracion("4.93ppm"), (4.93, "ppm"))


class TestJwx(unittest.TestCase):
    def test_parse(self):
        with open(os.path.join(TARJETA, "SUMMARYQ.JWX"), "rb") as fh:
            metodos = parsear_jwx_bytes(fh.read())
        self.assertTrue(len(metodos) >= 2)
        nombres = {m.nombre for m in metodos}
        self.assertIn("Test1", nombres)
        self.assertTrue(all(m.modo == "quantitation" for m in metodos))

    def test_muestras(self):
        with open(os.path.join(TARJETA, "SUMMARYS.JWX"), "rb") as fh:
            metodos = parsear_jwx_bytes(fh.read())
        m = [x for x in metodos if x.modo == "spectrum"][0]
        self.assertEqual(m.nombre, "Método por defecto")
        self.assertEqual(m.muestras[0].loc.lower(), "323be947.jwb")


class TestJwu(unittest.TestCase):
    def test_usuarios(self):
        with open(os.path.join(TARJETA, "USERSINF.JWU"), "rb") as fh:
            usrs = parsear_jwu_bytes(fh.read())
        nombres = {x.nombre for x in usrs}
        self.assertIn("Alumnos", nombres)
        # Generic y Supervisor tienen PIN 1234
        g = [x for x in usrs if x.nombre == "Generic"]
        self.assertEqual(g[0].passcode, "1234")


class TestReader(unittest.TestCase):
    def test_leer_carpeta(self):
        tarjeta = leer_carpeta(TARJETA)
        self.assertGreaterEqual(len(tarjeta.metodos), 8)
        self.assertEqual({x.nombre for x in tarjeta.usuarios} & {"Alumnos"}, {"Alumnos"})

    def test_decodificar_por_indice(self):
        tarjeta = leer_carpeta(TARJETA)
        # el .JWB 323BE947 es spectrum (190-900)
        modo, r = decodificar_archivo(tarjeta, "323BE947.JWB")
        self.assertEqual(modo, "spectrum")
        self.assertEqual(r["n"], 7101)
        # 323BEA26 es multi
        modo2, r2 = decodificar_archivo(tarjeta, "323BEA26.JWB")
        self.assertEqual(modo2, "multi")
        self.assertEqual(r2["wls"], [300.0, 330.0, 400.0, 600.0])


class TestExportar(unittest.TestCase):
    def test_export(self):
        tarjeta = leer_carpeta(TARJETA)
        with tempfile.TemporaryDirectory() as tmp:
            escritos = exportar_carpeta(tarjeta, tmp)
            self.assertTrue(any(os.path.basename(x) == "_indice_metodos.csv" for x in escritos))
            # el espectro 190-900 debe tener 7101+1 filas
            esp = [x for x in escritos if "323be947" in os.path.basename(x).lower()]
            self.assertTrue(esp, "debe exportar el espectro 323BE947")
            with open(esp[0], encoding="utf-8") as fh:
                n = sum(1 for _ in fh)
            self.assertEqual(n, 7102)  # cabecera + 7101


if __name__ == "__main__":
    unittest.main(verbosity=2)