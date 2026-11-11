# -*- coding: utf-8 -*-
"""Tarjeta con los archivos dentro de SU PROPIA SUBCARPETA.

Fallo real encontrado por el usuario: al cargar `tests/data` (que tiene la
tarjeta dentro de `tests/data/tarjeta/`) aparecían los 18 métodos pero TODOS
daban "Sin datos".  Causa: el índice se buscaba recursivamente (`os.walk`), pero
los `.JWB` se resolvían contra la carpeta elegida, no contra la que contiene el
índice, así que no se encontraba ninguno.
"""
import os
import sys
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QPA_FONTDIR", r"C:\Windows\Fonts")

MAESTRO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, MAESTRO)

from PySide6.QtWidgets import QApplication                        # noqa: E402

_app = QApplication.instance() or QApplication(sys.argv[:1])

from jenway67.reader import (decodificar_archivo, leer_carpeta,   # noqa: E402
                             olvidar_mapa, resolver_ruta)
from ui.ventana import VentanaMaestro                             # noqa: E402

RAIZ = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(RAIZ, "data")             # la tarjeta vive en data/tarjeta/
TARJETA = os.path.join(DATA, "tarjeta")


class TestResolucionDeArchivos(unittest.TestCase):
    def test_la_carpeta_padre_encuentra_los_jwb_de_la_subcarpeta(self):
        tarjeta = leer_carpeta(DATA)
        self.assertEqual(len(tarjeta.metodos), 18)
        metodo = tarjeta.metodos[0]
        _modo, resultado = decodificar_archivo(tarjeta, metodo.muestras[0].loc,
                                               metodo.modo)
        self.assertTrue(resultado)
        self.assertIn("n", resultado)

    def test_la_carpeta_normal_sigue_igual(self):
        tarjeta = leer_carpeta(TARJETA)
        _modo, resultado = decodificar_archivo(tarjeta, "323be947.JWB")
        self.assertEqual(resultado["n"], 7101)

    def test_las_dos_formas_de_cargar_dan_los_mismos_metodos(self):
        desde_padre = leer_carpeta(DATA)
        desde_tarjeta = leer_carpeta(TARJETA)
        self.assertEqual(len(desde_padre.metodos), len(desde_tarjeta.metodos))
        self.assertEqual([m.nombre for m in desde_padre.metodos],
                         [m.nombre for m in desde_tarjeta.metodos])

    def test_resolver_ruta_baja_a_la_subcarpeta(self):
        tarjeta = leer_carpeta(DATA)
        ruta = resolver_ruta(tarjeta, "323be947.JWB")
        self.assertTrue(os.path.isfile(ruta))
        self.assertIn("tarjeta", ruta.lower().replace("/", os.sep))

    def test_resolver_ruta_respeta_una_ruta_absoluta(self):
        tarjeta = leer_carpeta(TARJETA)
        absoluta = os.path.join(TARJETA, "323BE947.JWB")
        self.assertEqual(resolver_ruta(tarjeta, absoluta), absoluta)

    def test_un_archivo_ausente_da_un_error_claro(self):
        tarjeta = leer_carpeta(TARJETA)
        with self.assertRaises(FileNotFoundError) as contexto:
            decodificar_archivo(tarjeta, "NOEXISTE.JWB")
        self.assertIn("no está en la tarjeta", str(contexto.exception))

    def test_la_cache_se_puede_olvidar_y_sigue_resolviendo(self):
        tarjeta = leer_carpeta(DATA)
        resolver_ruta(tarjeta, "323be947.JWB")
        olvidar_mapa(DATA)
        self.assertTrue(os.path.isfile(resolver_ruta(tarjeta, "323be947.JWB")))
        olvidar_mapa()                      # sin argumento vacía todo
        self.assertTrue(os.path.isfile(resolver_ruta(tarjeta, "323be947.JWB")))


class TestLaVentanaConLaCarpetaPadre(unittest.TestCase):
    def test_los_18_metodos_ya_dan_datos(self):
        ventana = VentanaMaestro(tema="dark")
        ventana.cargar_carpeta(DATA)
        filas = []
        for indice in range(len(ventana.items_de_metodos())):
            ventana.seleccionar_metodo(indice)
            QApplication.processEvents()
            filas.append(ventana.modelo_datos.rowCount())
        self.assertEqual(len(filas), 18)
        # La única vacía es la cinética saturada, y esa ya se explica sola.
        self.assertEqual(sum(1 for f in filas if f == 0), 1)
        self.assertIn("saturadas", ventana.statusBar().currentMessage())

    def test_la_carpeta_padre_y_la_tarjeta_dan_las_mismas_filas(self):
        resultados = {}
        for carpeta in (DATA, TARJETA):
            ventana = VentanaMaestro(tema="dark")
            ventana.cargar_carpeta(carpeta)
            filas = []
            for indice in range(len(ventana.items_de_metodos())):
                ventana.seleccionar_metodo(indice)
                QApplication.processEvents()
                filas.append(ventana.modelo_datos.rowCount())
            resultados[carpeta] = filas
        self.assertEqual(resultados[DATA], resultados[TARJETA])


if __name__ == "__main__":
    unittest.main(verbosity=2)
