# -*- coding: utf-8 -*-
"""Pruebas del parser de reportes .TXT del Jenway 6705 (casos dorados reales)."""
import os
import sys
import unittest

MAESTRO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, MAESTRO)

from jenway67 import parser_txt
from jenway67.parser_txt import parsear_reporte, parsear_texto, Registro  # noqa: E402

DATOS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "reportes")


def lee(nombre):
    return parsear_reporte(os.path.join(DATOS, nombre))


def unico(nombre):
    regs = lee(nombre)
    assert len(regs) == 1, f"{nombre}: esperado 1 registro, hay {len(regs)}"
    return regs[0]


class TestModo(unittest.TestCase):
    def test_modos(self):
        casos = {
            "1_LEC.TXT": ("photometrics", 1),
            "3_LEC.TXT": ("spectrum", 1),
            "4_LEC.TXT": ("multi", 1),
            "TEST1.TXT": ("quantitation", 1),
            "TEST2.TXT": ("kinetics", 4),   # varios registros de cinética
        }
        for nombre, (modo, n) in casos.items():
            regs = lee(nombre)
            with self.subTest(nombre):
                self.assertEqual(len(regs), n)
                self.assertTrue(all(r.modo == modo for r in regs))


class TestFotometria(unittest.TestCase):
    def test_cabecera_longitud_onda(self):
        r = unico("1_LEC.TXT")
        self.assertIn("330.0", r.meta.get("Longitud de onda", ""))

    def test_filas(self):
        r = unico("1_LEC.TXT")
        filas = r.cuerpo["filas"]
        self.assertEqual(filas[0]["id"], "002")
        self.assertIn(filas[0]["abs"], ("3.000", "3.0"))


class TestEspectro(unittest.TestCase):
    def test_puntos(self):
        r = unico("3_LEC.TXT")
        puntos = r.cuerpo["puntos"]
        self.assertEqual(len(puntos), 711)
        self.assertEqual(puntos[0], (190.0, 2.457))
        self.assertEqual(puntos[-1], (900.0, 1.313))

    def test_cabecera_rango(self):
        r = unico("3_LEC.TXT")
        self.assertIn("190.0nm", r.meta["WRango de longitud de onda"])


class TestMulti(unittest.TestCase):
    def test_celdas(self):
        r = unico("4_LEC.TXT")
        celdas = r.cuerpo["celdas"]
        self.assertEqual(len(celdas), 4)
        self.assertEqual([c["wl"] for c in celdas], [300.0, 330.0, 400.0, 600.0])
        self.assertEqual(celdas[0]["etiqueta"], "A1")
        self.assertAlmostEqual(celdas[1]["valor"], -0.301, places=3)

    def test_calculos(self):
        r = unico("4_LEC.TXT")
        calc = r.cuerpo["calculos"]
        self.assertAlmostEqual(calc["A1-A2"], 3.301, places=3)
        self.assertAlmostEqual(calc["A1/A2"], -9.973, places=3)


class TestKinetics(unittest.TestCase):
    def test_varias_series(self):
        regs = lee("TEST2.TXT")
        self.assertEqual(len(regs), 4)
        self.assertTrue(all(reg.modo == "kinetics" for reg in regs))

    def test_serie(self):
        regs = lee("TEST2.TXT")
        s1 = regs[0].cuerpo["serie"]
        self.assertEqual(len(s1), 15)
        self.assertEqual(s1[0][1], 2.367)
        s4 = regs[3].cuerpo["serie"]
        self.assertEqual(s4[0][1], 2.909)

    def test_cinetica_multi_celda_carriles(self):
        texto = (
            "========================================\r\n"
            "MODO CINÉTICA.....\r\n"
            "MÉTODO: MÉTODO POR DEFECTO\r\n"
            "LONGITUD DE ONDA: 405.0NM\r\n"
            "========================================\r\n"
            "Hora (  segundos),Celda,1\r\n"
            "0, 1.872\r\n"
            "59, 3.000\r\n"
            "118, 3.000\r\n"
            "Hora (  segundos),Celda,2\r\n"
            "0, 0.150\r\n"
            "59, 0.050\r\n"
            "118, 2.500\r\n"
            "========================================\r\n"
        )
        regs = parser_txt.parsear_texto(texto)
        self.assertEqual(len(regs), 1)
        cuerpo = regs[0].cuerpo
        self.assertEqual(len(cuerpo["series"]), 2)
        self.assertEqual(cuerpo["series"][0]["celda"], 1)
        self.assertEqual(cuerpo["series"][0]["serie"], [(0.0, 1.872), (59.0, 3.0), (118.0, 3.0)])
        self.assertEqual(cuerpo["series"][1]["celda"], 2)
        self.assertEqual(cuerpo["series"][1]["serie"], [(0.0, 0.15), (59.0, 0.05), (118.0, 2.5)])

    def test_cinetica_multi_celda_reinicio_tiempo(self):
        texto = (
            "========================================\r\n"
            "MODO CINÉTICA.....\r\n"
            "========================================\r\n"
            "HORA ABS\r\n"
            "0 1.872\r\n"
            "59 3.000\r\n"
            "118 3.000\r\n"
            "0 0.150\r\n"
            "59 0.050\r\n"
            "118 2.500\r\n"
            "========================================\r\n"
        )
        regs = parser_txt.parsear_texto(texto)
        self.assertEqual(len(regs), 1)
        cuerpo = regs[0].cuerpo
        self.assertEqual(len(cuerpo["series"]), 2)
        self.assertEqual(len(cuerpo["series"][0]["serie"]), 3)
        self.assertEqual(len(cuerpo["series"][1]["serie"]), 3)

    def test_cinetica_multi_celda_adaptador_carriles(self):
        from jenway67 import adaptador_txt
        texto = (
            "========================================\r\n"
            "MODO CINÉTICA.....\r\n"
            "MÉTODO: MÉTODO POR DEFECTO\r\n"
            "LONGITUD DE ONDA: 405.0NM\r\n"
            "========================================\r\n"
            "Hora (  segundos),Celda,1\r\n"
            "0, 1.872\r\n"
            "59, 3.000\r\n"
            "Hora (  segundos),Celda,2\r\n"
            "0, 0.150\r\n"
            "59, 0.050\r\n"
            "========================================\r\n"
        )
        bloques = adaptador_txt.parsear_stream_serie(texto)
        self.assertEqual(len(bloques), 1)
        _reg, modo, res, etqs = bloques[0]
        self.assertEqual(modo, "kinetics")
        self.assertEqual(len(res), 2)
        self.assertIn("Carril 1", etqs[0])
        self.assertIn("Carril 2", etqs[1])
        self.assertEqual(res[0]["tiempos"], [0.0, 59.0])
        self.assertEqual(res[1]["tiempos"], [0.0, 59.0])
        self.assertAlmostEqual(res[0]["serie"][0][2], 1.872, places=3)
        self.assertAlmostEqual(res[1]["serie"][0][2], 0.150, places=3)


class TestQuantitation(unittest.TestCase):
    def test_estandares(self):
        r = unico("TEST1.TXT")
        stds = r.meta["__estandares__"]
        self.assertEqual(len(stds), 4)
        self.assertAlmostEqual(stds[0][0], 0.00, places=2)
        self.assertAlmostEqual(stds[1][0], 0.05, places=2)
        self.assertAlmostEqual(stds[2][1], 2.49, places=2)
        self.assertAlmostEqual(stds[3][1], 2.95, places=2)

    def test_muestra(self):
        r = unico("TEST1.TXT")
        m = r.cuerpo["muestras"][0]
        self.assertAlmostEqual(m["abs"], 0.774, places=3)
        self.assertAlmostEqual(m["conc"], 0.09, places=2)
        self.assertEqual(m["unidades"], "mM")

    def test_unidades_varias(self):
        r = unico("5_LEC.TXT")          # medida real (11:42): muestra Abs 3.000 -> 30.00ppm
        m = r.cuerpo["muestras"][0]
        self.assertEqual(m["unidades"], "ppm")
        self.assertAlmostEqual(m["conc"], 30.0, places=2)


class TestMultiRegistro(unittest.TestCase):
    def test_introduz_varios(self):
        regs = lee("INTRODUZ.TXT")
        self.assertGreaterEqual(len(regs), 3)
        modos = [r.modo for r in regs]
        self.assertIn("photometrics", modos)
        self.assertIn("spectrum", modos)
        self.assertIn("multi", modos)


class TestCodificacion(unittest.TestCase):
    def test_acentos(self):
        # 'Método' y 'Cinética' con tilde deben decodificarse bien (primer registro de TEST2)
        regs = lee("TEST2.TXT")
        self.assertEqual(regs[0].meta.get("Método"), "Test2")


if __name__ == "__main__":
    unittest.main(verbosity=2)