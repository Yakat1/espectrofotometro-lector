# -*- coding: utf-8 -*-
"""Pruebas de la Fase 2: motor de análisis (analisis, graficos, informe)."""
import math
import os
import sys
import tempfile
import unittest

MAESTRO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, MAESTRO)

from jenway67 import analisis as an            # noqa: E402
from jenway67.reader import leer_carpeta        # noqa: E402
from jenway67.parser_jwb import decodificar     # noqa: E402
from jenway67.informe import _analisis_por_modo, _tabla_por_modo  # noqa: E402
from jenway67.informe import analizar_carpeta   # noqa: E402

TARJETA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "tarjeta")
JWB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "jwb")


def lee(nombre):
    with open(os.path.join(JWB, nombre), "rb") as fh:
        return fh.read()


class TestEstadisticas(unittest.TestCase):
    def test_basica(self):
        e = an.estadisticas([1.0, 2.0, 3.0])
        self.assertEqual(e["n"], 3)
        self.assertAlmostEqual(e["media"], 2.0)

    def test_ignora_inf(self):
        e = an.estadisticas([float("inf"), 1.0, 2.0])
        self.assertEqual(e["n"], 2)


class TestEspectro(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _, cls.r = decodificar(lee("323BE947_spectrum.JWB"), "spectrum")
        cls.puntos = cls.r["puntos"]

    def test_picos(self):
        pk = an.picos(self.puntos, prominencia=0.2)
        # en 190-900 hay varios máximos/mínimos con prominencia
        self.assertTrue(len(pk) >= 2)
        # el pico alto cerca de 258 nm aprox (región 3.0, pero saturado -> no finito)
        self.assertTrue(all(p["prominencia"] >= 0.2 for p in pk))

    def test_area(self):
        a = an.area_bajo_curva(self.puntos)
        self.assertGreater(a, 0)

    def test_derivada(self):
        d = an.derivada(self.puntos, 1)
        self.assertEqual(len(d), len(self.puntos))


class TestCinetica(unittest.TestCase):
    def test_rate(self):
        _, r = decodificar(lee("323BFE3F_kinetics.JWB"), "kinetics")
        c = an.cinetica(r["serie"])
        self.assertEqual(c["n"], 15)
        self.assertAlmostEqual(c["inicial"], 2.909, places=2)
        self.assertAlmostEqual(c["final"], 2.909, places=2)


class TestCuantificacion(unittest.TestCase):
    def test_interp(self):
        stds = [(0.0, 0.0), (1.0, 0.10), (2.0, 0.20), (3.0, 0.30)]
        q = an.cuantificacion(stds, 0.15)
        self.assertAlmostEqual(q["conc_interp"], 1.5, places=4)
        self.assertIn("lineal_r2", q)

    def test_real(self):
        _, r = decodificar(lee("323BFC6F_quant.JWB"), "quantitation")
        q = an.cuantificacion(r["estandares"], r["abs_muestra"])
        self.assertAlmostEqual(q["conc_interp"], 0.09, places=2)


class TestInformeIgnoraNoFinito(unittest.TestCase):
    def test_agrupar_y_analizar(self):
        tarjeta = leer_carpeta(TARJETA)
        with tempfile.TemporaryDirectory() as tmp:
            res = analizar_carpeta(tarjeta, tmp)
            self.assertTrue(os.path.exists(res["xlsx"]))
            # debe haber algún espectro y algún kinetics decodificados
            modos = {m["modo"] for m in res["metodos"] if m.get("estado") == "ok"}
            self.assertIn("spectrum", modos)
            self.assertIn("kinetics", modos)
            self.assertGreater(len(res["figuras"]), 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)