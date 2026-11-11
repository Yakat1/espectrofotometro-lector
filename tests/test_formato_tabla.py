# -*- coding: utf-8 -*-
"""Pruebas del formato de la tabla y de los CSV exportados.

Motivo: el recorte de saturación (que el instrumento aplica a sus LECTURAS de
absorbancia, 3.000) se estaba aplicando a TODAS las columnas, de modo que la
columna de longitud de onda del modo multi-longitud y de fotometría salía como
"3.000", las concentraciones > 3 se recortaban y A1-A2 = 3.301 se mostraba como
3.000.
"""
import math
import os
import sys
import unittest

MAESTRO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, MAESTRO)

from jenway67 import exportar as ex                # noqa: E402
from jenway67.reader import decodificar_archivo, leer_carpeta  # noqa: E402

RAIZ = os.path.dirname(os.path.abspath(__file__))
TARJETA = os.path.join(RAIZ, "data", "tarjeta")


class TestFormateo(unittest.TestCase):
    def test_un_valor_normal_no_se_recorta(self):
        """Longitudes de onda, %T, concentraciones y cocientes: tal cual."""
        self.assertEqual(ex._f(330.0), "330.000")
        self.assertEqual(ex._f(600.0), "600.000")
        self.assertEqual(ex._f(99.5), "99.500")
        self.assertEqual(ex._f(36.88), "36.880")
        self.assertEqual(ex._f(10.0), "10.000")
        self.assertEqual(ex._f(-9.973), "-9.973")
        self.assertEqual(ex._f(3.301), "3.301")

    def test_la_absorbancia_si_se_recorta(self):
        """El equipo recorta sus lecturas en 3.000: la tabla lo imita."""
        self.assertEqual(ex._abs(0.433), "0.433")
        self.assertEqual(ex._abs(-0.301), "-0.301")
        self.assertEqual(ex._abs(3.301), "3.000")
        self.assertEqual(ex._abs(float("inf")), "Saturado(>3.0)")

    def test_none_nan_y_texto(self):
        for funcion in (ex._f, ex._abs):
            self.assertEqual(funcion(None), "")
            self.assertEqual(funcion(float("nan")), "")
            self.assertEqual(funcion("texto"), "texto")


class TestFilasPara(unittest.TestCase):
    def test_multi_conserva_las_longitudes_de_onda(self):
        r = {"celdas": [{"etiqueta": "A1", "wl": 300.0, "abs": float("inf")},
                        {"etiqueta": "A2", "wl": 330.0, "abs": -0.301},
                        {"etiqueta": "A3", "wl": 400.0, "abs": -0.228},
                        {"etiqueta": "A4", "wl": 600.0, "abs": -0.222}],
             "A1/A2": -9.973, "A1-A2": 3.301}
        _cab, filas = ex.filas_para("multi", r)
        self.assertEqual([fila[1] for fila in filas[:4]],
                         ["300.000", "330.000", "400.000", "600.000"])
        self.assertEqual(filas[0][3], "Saturado(>3.0)")
        self.assertEqual(filas[4][3], "-9.973")
        self.assertEqual(filas[5][3], "3.301")

    def test_fotometria_conserva_la_longitud_de_onda(self):
        _cab, filas = ex.filas_para("photometrics",
                                    {"wl": 330.0, "t": 0.0, "abs": float("inf")})
        self.assertEqual(filas[0], ["Longitud_onda_nm", "330.000"])
        self.assertEqual(filas[1], ["Transmitancia_pct", "0.000"])
        self.assertEqual(filas[2], ["Absorbancia", "Saturado(>3.0)"])

    def test_espectro_no_recorta_la_transmitancia(self):
        _cab, filas = ex.filas_para("spectrum",
                                    {"puntos": [(400.0, 36.88, 0.433),
                                                (400.1, 99.5, 0.002)]})
        self.assertEqual(filas[0], ["400.0", "36.880", "0.433"])
        self.assertEqual(filas[1], ["400.1", "99.500", "0.002"])

    def test_espectro_cumple_la_identidad_del_instrumento(self):
        """Lo mostrado debe cumplir A = -log10(T/100)."""
        puntos = [(400.0 + 0.1 * i, 100.0 * 10 ** -a, a)
                  for i, a in enumerate([0.0, 0.3, 1.0, 2.0, 2.9])]
        _cab, filas = ex.filas_para("spectrum", {"puntos": puntos})
        for fila in filas:
            transmitancia, absorbancia = float(fila[1]), float(fila[2])
            self.assertAlmostEqual(-math.log10(transmitancia / 100.0), absorbancia,
                                   places=3)

    def test_cuantificacion_no_recorta_la_concentracion(self):
        r = {"estandares": [(0.0, 0.001), (10.0, 1.2), (25.0, 2.9)],
             "abs_muestra": 0.774}
        _cab, filas = ex.filas_para("quantitation", r)
        self.assertEqual(filas[1], ["Estandar", "10.000", "1.200"])
        self.assertEqual(filas[2], ["Estandar", "25.000", "2.900"])
        self.assertEqual(filas[3], ["Muestra", "", "0.774"])

    def test_cinetica_no_recorta_la_transmitancia(self):
        _cab, filas = ex.filas_para("kinetics",
                                    {"serie": [(0, 50.0, 0.301),
                                               (1, 0.0, float("inf"))]})
        self.assertEqual(filas[0], ["0", "50.000", "0.301"])
        self.assertEqual(filas[1], ["1", "0.000", "Saturado(>3.0)"])

    def test_modo_desconocido_falla(self):
        with self.assertRaises(ValueError):
            ex.filas_para("inventado", {})


class TestConDatosReales(unittest.TestCase):
    """Con .JWB de la tarjeta: los casos que destaparon el fallo."""

    @classmethod
    def setUpClass(cls):
        cls.tarjeta = leer_carpeta(TARJETA)

    def test_multi_real_conserva_sus_longitudes_de_onda(self):
        _modo, r = decodificar_archivo(self.tarjeta, "323BEA26.JWB")
        _cab, filas = ex.filas_para("multi", r)
        self.assertEqual([fila[1] for fila in filas[:4]],
                         ["300.000", "330.000", "400.000", "600.000"])
        diferencia = [fila for fila in filas if fila[0] == "A1-A2"][0]
        self.assertEqual(diferencia[3], "3.301")

    def test_fotometria_real_conserva_su_longitud_de_onda(self):
        _modo, r = decodificar_archivo(self.tarjeta, "323BE7BA.JWB")
        _cab, filas = ex.filas_para("photometrics", r)
        self.assertEqual(filas[0][1], "330.000")

    def test_el_espectro_real_cumple_la_identidad(self):
        _modo, r = decodificar_archivo(self.tarjeta, "323BE947.JWB")
        _cab, filas = ex.filas_para("spectrum", r)
        self.assertGreater(len(filas), 1000)
        # La tabla muestra el %T y la absorbancia con 3 decimales, así que la
        # identidad solo puede comprobarse dentro de la resolución de lo que se
        # MUESTRA: 0,0005 por el redondeo de A, más 0,434·0,0005/T porque un
        # error de 0,0005 en el %T se amplifica al reconstruir A (dA = 0,434·dT/T).
        for fila in filas[:200] + filas[-200:]:
            transmitancia, absorbancia = float(fila[1]), float(fila[2])
            if transmitancia <= 0 or absorbancia >= 3.0:
                continue          # recortado por saturación: no aplica
            tolerancia = 0.0005 + 0.434 * 0.0005 / transmitancia
            self.assertLessEqual(
                abs(-math.log10(transmitancia / 100.0) - absorbancia), tolerancia,
                "la fila %s no cuadra dentro de la resolución de la tabla" % fila)


if __name__ == "__main__":
    unittest.main(verbosity=2)
