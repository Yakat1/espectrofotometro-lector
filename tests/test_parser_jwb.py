# -*- coding: utf-8 -*-
"""Pruebas de los decoders de .JWB del Jenway 6705 (casos dorados reales)."""
import os
import sys
import unittest

MAESTRO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, MAESTRO)

from jenway67.parser_jwb import decodificar  # noqa: E402

JWB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "jwb")


def lee(nombre):
    with open(os.path.join(JWB, nombre), "rb") as fh:
        return fh.read()


def cerca(a, b, tol=0.005):
    if a is None or b is None:
        return False
    try:
        return abs(a - b) <= tol
    except TypeError:
        return False


class TestEspectro(unittest.TestCase):
    def test_190_900(self):
        modo, r = decodificar(lee("323BE947_spectrum.JWB"), "spectrum")
        self.assertEqual(modo, "spectrum")
        self.assertEqual(r["n"], 7101)
        self.assertEqual(len(r["puntos"]), 7101)
        self.assertAlmostEqual(r["puntos"][0][2], 2.457, places=3)   # 190 nm, Abs (reporte 3 LEC)
        self.assertAlmostEqual(r["puntos"][-1][2], 1.313, places=3)  # 900 nm
        p250 = next(p for p in r["puntos"] if p[0] == 250.0)
        self.assertAlmostEqual(p250[2], 2.230, places=3)             # reporte 3 LEC

    def test_400_500_vacio(self):
        _, r = decodificar(lee("323BD8FF_spectrum.JWB"), "spectrum")
        self.assertEqual(r["n"], 1001)
        self.assertEqual((r["wl0"], r["wl1"]), (400.0, 500.0))


class TestMulti(unittest.TestCase):
    def test_wls_y_celdas(self):
        modo, r = decodificar(lee("323BEA26_multi.JWB"), "multi")
        self.assertEqual(r["wls"], [300.0, 330.0, 400.0, 600.0])
        self.assertAlmostEqual(r["celdas"][1]["abs"], -0.301, places=3)  # A2(330)
        self.assertAlmostEqual(r["celdas"][2]["abs"], -0.228, places=3)  # A3(400)
        self.assertAlmostEqual(r["celdas"][3]["abs"], -0.222, places=3)  # A4(600)

    def test_calculos_replicados(self):
        _, r = decodificar(lee("323BEA26_multi.JWB"), "multi")
        # el display clampa A1=3.000 (saturada); A1-A2=3.301 coincide con reporte 4 LEC
        self.assertTrue(cerca(r["A1-A2"], 3.301, tol=0.01))
        self.assertTrue(cerca(r["A1/A2"], -9.973, tol=0.05))


class TestFotometria(unittest.TestCase):
    def test_lowry_100(self):
        _, r = decodificar(lee("323BCBA4_photo_lowry.JWB"), "photometrics")
        self.assertAlmostEqual(r["wl"], 550.0, places=1)
        self.assertAlmostEqual(r["abs"], 0.0, places=2)     # %T=100 -> Abs 0.0

    def test_saturado(self):
        _, r = decodificar(lee("323BE7BA_photo_sat.JWB"), "photometrics")
        self.assertAlmostEqual(r["wl"], 330.0, places=1)
        import math
        self.assertTrue(math.isinf(r["abs"]))               # %T=0 -> saturado


class TestCinética(unittest.TestCase):
    def test_serie_coincide(self):
        # valores de la 1ª lectura de cada corrida de TEST2 (reporte)
        casos = [
            ("323BFDC8_kinetics.JWB", 2.367),
            ("323BFDF4_kinetics.JWB", 0.397),
            ("323BFE19_kinetics.JWB", 0.570),
            ("323BFE3F_kinetics.JWB", 2.909),
        ]
        for nombre, esperado in casos:
            with self.subTest(nombre):
                _, r = decodificar(lee(nombre), "kinetics")
                self.assertEqual(r["n"], 15)
                self.assertTrue(cerca(r["serie"][0][2], esperado))


class TestCuantificacion(unittest.TestCase):
    def test_estandares(self):
        _, r = decodificar(lee("323BFC6F_quant.JWB"), "quantitation")
        conc = [e[0] for e in r["estandares"]]
        abs_ = [e[1] for e in r["estandares"]]
        self.assertTrue(cerca(conc[1], 0.05) and cerca(conc[2], 0.5) and cerca(conc[3], 1.0))
        self.assertTrue(cerca(abs_[1], 0.61) and cerca(abs_[2], 2.49) and cerca(abs_[3], 2.95))

    def test_muestra(self):
        _, r = decodificar(lee("323BFC6F_quant.JWB"), "quantitation")
        self.assertAlmostEqual(r["wl"], 450.0, places=1)
        self.assertTrue(cerca(r["abs_muestra"], 0.774, tol=0.01))  # %T=16.8452 -> Abs 0.774


class TestAutoDeteccion(unittest.TestCase):
    def test_deteccion(self):
        casos = [
            ("323BE947_spectrum.JWB", "spectrum"),
            ("323BEA26_multi.JWB", "multi"),
            ("323BCBA4_photo_lowry.JWB", "photometrics"),
            ("323BFE3F_kinetics.JWB", "kinetics"),
            ("323BFC6F_quant.JWB", "quantitation"),
        ]
        for nombre, modo in casos:
            with self.subTest(nombre):
                m, _ = decodificar(lee(nombre))
                self.assertEqual(m, modo)


if __name__ == "__main__":
    unittest.main(verbosity=2)