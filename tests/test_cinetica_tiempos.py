# -*- coding: utf-8 -*-
"""Tiempos reales de las cinéticas: el .JWB guarda el tiempo final, no el índice.

El eje X de una cinética debe ser el TIEMPO (s), no el número de lectura. El
informe .TXT del instrumento imprime los tiempos; el .JWB sólo guarda el tiempo
de la ÚLTIMA lectura (0x38) y el número de lecturas, así que el intervalo se
deduce.

OJO con el paso: NO es un 2.000 s exacto. El cronómetro del instrumento avanza
de 2 en 2 s pero a veces salta a 3 (una cinética de 30 s imprime 0, 2, 4, …,
24, 27, 29). Por eso 146 lecturas cubren ~298 s (no 290) y el paso medio es
~2.06 s. Sin esto, una cinética de 300 s se dibujaba a la MITAD (150 s).
"""
import os
import sys
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QPA_FONTDIR", r"C:\Windows\Fonts")

MAESTRO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, MAESTRO)

import numpy as np                                              # noqa: E402

from jenway67 import analisis as an                             # noqa: E402
from jenway67 import exportar as ex                             # noqa: E402
from jenway67.parser_jwb import (decodificar, _intervalo_kinetics,  # noqa: E402
                                 _tiempos_kinetics)
from ui.toolbar_plot import serie_para                          # noqa: E402

JWB = os.path.join(MAESTRO, "tests", "data", "jwb")


def lee(nombre):
    with open(os.path.join(JWB, nombre), "rb") as fh:
        return fh.read()


class TestIntervalo(unittest.TestCase):
    def test_el_paso_es_el_medio_hasta_el_tiempo_final(self):
        # 29 s con 15 lecturas -> paso medio 29/14 ≈ 2.07 s (no 2.000).
        self.assertAlmostEqual(_intervalo_kinetics(29.0, 15), 29.0 / 14, places=9)
        self.assertAlmostEqual(_intervalo_kinetics(298.0, 146), 298.0 / 145, places=9)

    def test_paso_de_1_s_exacto(self):
        self.assertAlmostEqual(_intervalo_kinetics(599.0, 600), 1.0, places=9)

    def test_sin_datos_cae_a_1_s(self):
        self.assertEqual(_intervalo_kinetics(29.0, 1), 1.0)
        self.assertEqual(_intervalo_kinetics(0.0, 15), 1.0)
        self.assertEqual(_intervalo_kinetics(float("nan"), 15), 1.0)


class TestRejillaDeTiempos(unittest.TestCase):
    def test_los_tiempos_acaban_en_el_tiempo_final_guardado(self):
        t = _tiempos_kinetics(298.0, 146)
        self.assertEqual(len(t), 146)
        self.assertEqual(t[0], 0.0)
        self.assertEqual(t[-1], 298.0)          # NO 290
        self.assertEqual(t, sorted(t))          # monótonos
        self.assertTrue(all(float(v).is_integer() for v in t))

    def test_cinetica_corta_de_30_s(self):
        # Réplica del informe impreso (0, 2, 4, …, 29) -> acaba en 29.
        t = _tiempos_kinetics(29.0, 15)
        self.assertEqual(len(t), 15)
        self.assertEqual(t[0], 0.0)
        self.assertEqual(t[-1], 29.0)

    def test_un_solo_punto(self):
        self.assertEqual(_tiempos_kinetics(10.0, 1), [0.0])


class TestTiemposDeLaSerie(unittest.TestCase):
    def test_usa_los_tiempos_reales_si_estan(self):
        r = {"serie": [(0, 50.0, 0.1), (1, 50.0, 0.2)], "tiempos": [0.0, 5.0]}
        np.testing.assert_allclose(an.tiempos_de(r), [0.0, 5.0])

    def test_cae_al_indice_sin_tiempos(self):
        r = {"serie": [(0, 50.0, 0.1), (1, 50.0, 0.2), (2, 50.0, 0.3)]}
        np.testing.assert_allclose(an.tiempos_de(r), [0.0, 1.0, 2.0])

    def test_tiempos_de_longitud_distinta_se_ignoran(self):
        r = {"serie": [(0, 50.0, 0.1), (1, 50.0, 0.2)], "tiempos": [0.0]}
        np.testing.assert_allclose(an.tiempos_de(r), [0.0, 1.0])


class TestCineticaDelJWB(unittest.TestCase):
    """Un .JWB real de cinética: tiempos reconstruidos del tiempo final."""

    @classmethod
    def setUpClass(cls):
        _, cls.r = decodificar(lee("323BFDC8_kinetics.JWB"), "kinetics")

    def test_el_decoder_entrega_tiempos_e_intervalo(self):
        self.assertEqual(self.r["n"], 15)
        self.assertAlmostEqual(self.r["intervalo_s"], 29.0 / 14, places=9)
        self.assertAlmostEqual(self.r["tiempo_total"], 29.0, places=9)
        self.assertEqual(len(self.r["tiempos"]), self.r["n"])
        self.assertEqual(self.r["tiempos"][0], 0.0)
        self.assertEqual(self.r["tiempos"][-1], 29.0)

    def test_los_tiempos_son_enteros_y_terminan_en_el_final(self):
        t = self.r["tiempos"]
        self.assertTrue(all(float(v).is_integer() for v in t))
        self.assertEqual(t, sorted(t))
        pasos = {int(b - a) for a, b in zip(t, t[1:])}
        self.assertTrue(pasos <= {2, 3}, pasos)     # 2 s con algún salto a 3

    def test_serie_para_usa_los_tiempos_y_etiqueta_tiempo(self):
        x, _y, xlabel, _ylabel = serie_para("kinetics", self.r, "abs")
        np.testing.assert_allclose(x, self.r["tiempos"])
        self.assertEqual(xlabel, "Tiempo (s)")

    def test_la_tabla_exportada_lleva_el_tiempo(self):
        cab, filas = ex.filas_para("kinetics", self.r)
        self.assertEqual(cab[0], "Tiempo_s")
        self.assertEqual(filas[0][0], "0")
        self.assertEqual(filas[1][0], "2")
        self.assertEqual(filas[-1][0], "29")

    def test_sin_tiempos_la_tabla_cae_al_indice(self):
        _cab, filas = ex.filas_para("kinetics",
                                    {"serie": [(0, 50.0, 0.301), (1, 0.0, float("inf"))]})
        self.assertEqual(filas[0], ["0", "50.000", "0.301"])
        self.assertEqual(filas[1], ["1", "0.000", "Saturado(>3.0)"])


if __name__ == "__main__":
    unittest.main(verbosity=2)