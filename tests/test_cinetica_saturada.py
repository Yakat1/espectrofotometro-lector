# -*- coding: utf-8 -*-
"""Cinética con TODAS las lecturas saturadas: la ventana no debe quedarse muda.

Caso real: `323BE85F.JWB` (cinética a 330 nm) guarda 15 lecturas con %T = 0
—muestra opaca— emparejadas con el marcador -99999.  El parser hace bien en
descartarlas (no hay transmitancia utilizable), pero la pantalla se quedaba en
"Sin datos" sin explicar nada, que es justo lo que no queremos: parece un fallo
de la aplicación cuando en realidad es una medida saturada.
"""
import os
import sys
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QPA_FONTDIR", r"C:\Windows\Fonts")

MAESTRO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, MAESTRO)

from PySide6.QtWidgets import QApplication                       # noqa: E402

_app = QApplication.instance() or QApplication(sys.argv[:1])

from jenway67.parser_jwb import _serie_y_saturados, decodificar  # noqa: E402
from jenway67.reader import leer_carpeta                         # noqa: E402
from ui.ventana import VentanaMaestro                            # noqa: E402

RAIZ = os.path.dirname(os.path.abspath(__file__))
TARJETA = os.path.join(RAIZ, "data", "tarjeta")

SATURADA = "323BE85F.JWB"
NORMAL = "323BFDC8.JWB"


def lee(nombre):
    with open(os.path.join(TARJETA, nombre), "rb") as manejador:
        return manejador.read()


class TestElParserLoCuenta(unittest.TestCase):
    def test_la_cinetica_saturada_declara_sus_15_lecturas(self):
        validos, saturados = _serie_y_saturados(lee(SATURADA))
        self.assertEqual(validos, [])
        self.assertEqual(saturados, 15)

    def test_el_resultado_expone_el_numero_de_saturadas(self):
        _modo, r = decodificar(lee(SATURADA), "kinetics")
        self.assertEqual(r["n"], 0)
        self.assertEqual(r["serie"], [])
        self.assertEqual(r["saturados"], 15)

    def test_una_cinetica_normal_no_tiene_saturadas(self):
        _modo, r = decodificar(lee(NORMAL), "kinetics")
        self.assertEqual(r["n"], 15)
        self.assertEqual(r["saturados"], 0)
        self.assertEqual(len(r["serie"]), 15)


class TestLaVentanaSeExplica(unittest.TestCase):
    def setUp(self):
        self.w = VentanaMaestro(tema="dark")
        self.w.cargar_carpeta(TARJETA)

    def _indice_del_metodo_saturado(self):
        for i in range(len(self.w.items_de_metodos())):
            metodo = self.w.metodo_en_fila(i)
            if not metodo or metodo.modo != "kinetics":
                continue
            if any(SATURADA.lower() in (s.loc or "").lower() for s in metodo.muestras):
                return i
        self.skipTest("la tarjeta no trae la cinética saturada")

    def _indice_de_una_cinetica_con_datos(self):
        for i in range(len(self.w.items_de_metodos())):
            metodo = self.w.metodo_en_fila(i)
            if not metodo or metodo.modo != "kinetics":
                continue
            if any(NORMAL.lower() in (s.loc or "").lower() for s in metodo.muestras):
                return i
        self.skipTest("la tarjeta no trae la cinética normal")

    def test_la_cinetica_saturada_avisa_en_vez_de_quedarse_en_sin_datos(self):
        indice = self._indice_del_metodo_saturado()
        self.w.seleccionar_metodo(indice)
        mensaje = self.w.statusBar().currentMessage()
        self.assertIn("saturadas", mensaje)
        self.assertIn("15 lectura", mensaje)
        # Y efectivamente no hay nada que dibujar: la tabla queda vacía.
        self.assertEqual(self.w.modelo_datos.rowCount(), 0)

    def test_una_cinetica_con_datos_no_avisa_de_saturacion(self):
        indice = self._indice_de_una_cinetica_con_datos()
        self.w.seleccionar_metodo(indice)
        self.assertNotIn("saturadas", self.w.statusBar().currentMessage())
        self.assertGreater(self.w.modelo_datos.rowCount(), 0)

    def test_aviso_generico_cuando_no_hay_puntos_ni_saturadas(self):
        self.w._avisar_si_vacio("kinetics", [{"serie": [], "n": 0}], ["muestra X"])
        self.assertIn("no contiene puntos utilizables",
                      self.w.statusBar().currentMessage())

    def test_un_aviso_para_espectro_vacio(self):
        self.w._avisar_si_vacio("spectrum", [{"puntos": []}], ["blanco"])
        self.assertIn("no contiene puntos utilizables",
                      self.w.statusBar().currentMessage())

    def test_no_avisa_cuando_si_hay_datos(self):
        self.w._actualizar_status("estado previo")
        self.w._avisar_si_vacio("kinetics", [{"serie": [(0, 50.0, 0.301)], "n": 1}],
                                ["ok"])
        self.assertEqual(self.w.statusBar().currentMessage(), "estado previo")


if __name__ == "__main__":
    unittest.main(verbosity=2)
