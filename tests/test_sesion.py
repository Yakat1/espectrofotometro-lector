# -*- coding: utf-8 -*-
"""Pruebas de guardado y carga de sesiones persistentes (.jws / .json)."""
import os
import sys
import tempfile
import unittest
import zipfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QPA_FONTDIR", r"C:\Windows\Fonts")

MAESTRO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, MAESTRO)

from PySide6.QtWidgets import QApplication  # noqa: E402

_app = QApplication.instance() or QApplication(sys.argv[:1])

from jenway67.sesion import (  # noqa: E402
    cargar_sesion_archivo,
    dict_a_tarjeta,
    guardar_sesion_archivo,
    tarjeta_a_dict,
)
from ui.ventana import VentanaMaestro  # noqa: E402

TARJETA = os.path.join(MAESTRO, "tests", "data", "tarjeta")


class TestSesionPersistente(unittest.TestCase):
    def setUp(self):
        self.w = VentanaMaestro(tema="dark")
        self.temp_files = []

    def tearDown(self):
        for f in self.temp_files:
            if os.path.exists(f):
                try:
                    os.remove(f)
                except Exception:
                    pass

    def _temp_file(self, suffix=".jws") -> str:
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tf:
            path = tf.name
        self.temp_files.append(path)
        return path

    def test_guardar_sin_datos_avisa(self):
        self.w.guardar_sesion(ruta_destino=self._temp_file(".jws"))
        self.assertIn("No hay datos", self.w.statusBar().currentMessage())

    def test_guardar_y_cargar_sesion_completa_jws(self):
        self.w.cargar_carpeta(TARJETA)
        self.assertGreater(len(self.w.tarjeta.metodos), 0)

        # Seleccionar método de cinética
        idx_kin = -1
        for i in range(len(self.w.items_de_metodos())):
            m = self.w.metodo_en_fila(i)
            if m and m.modo == "kinetics":
                idx_kin = i
                break
        self.assertGreaterEqual(idx_kin, 0)
        self.w.seleccionar_metodo(idx_kin)

        # Añadir marcas y configurar gráfico
        self.w.panel.spin_intervalo.setValue(45)
        self.w.panel._marcar_intervalo()
        marcas_orig = list(self.w.panel._marcas)
        self.assertTrue(len(marcas_orig) > 0)

        # Añadir un paso de procesado en la muestra 0
        self.w._cadena_de(0).agregar("suavizar_savgol", ventana=5, orden=2)
        n_pasos_orig = len(self.w._cadena_de(0))

        # Modificar límites Y
        self.w.panel.txt_y_min.setText("0.05")
        self.w.panel.txt_y_max.setText("1.95")

        ruta_jws = self._temp_file(".jws")
        self.w.guardar_sesion(ruta_destino=ruta_jws)

        # Verificar que el archivo existe y es un zip válido con manifest.json y files/
        self.assertTrue(os.path.isfile(ruta_jws))
        self.assertTrue(zipfile.is_zipfile(ruta_jws))
        with zipfile.ZipFile(ruta_jws, "r") as zf:
            nombres = zf.namelist()
            self.assertIn("manifest.json", nombres)
            archivos_files = [n for n in nombres if n.startswith("files/")]
            self.assertGreater(len(archivos_files), 0)

        # Abrir en una ventana nueva y limpia
        w2 = VentanaMaestro(tema="light")
        w2.abrir_sesion(ruta_jws)

        # Verificar restauraciones
        self.assertEqual(w2.tema, "dark")
        self.assertIsNotNone(w2.tarjeta)
        self.assertEqual(len(w2.tarjeta.metodos), len(self.w.tarjeta.metodos))
        self.assertIsNotNone(w2.metodo_actual)
        self.assertEqual(w2.metodo_actual.id, self.w.metodo_actual.id)
        self.assertEqual(w2.metodo_actual.modo, "kinetics")

        # Marcas y bitácora
        self.assertEqual(w2.panel._marcas, marcas_orig)
        self.assertEqual(w2.panel.spin_intervalo.value(), 45)
        self.assertEqual(w2.panel.txt_y_min.text(), "0.05")
        self.assertEqual(w2.panel.txt_y_max.text(), "1.95")

        # Cadenas de procesado
        self.assertEqual(len(w2._cadena_de(0)), n_pasos_orig)
        self.assertEqual(w2._cadena_de(0).pasos[0]["clave"], "suavizar_savgol")

        # Estado de sesión y título
        self.assertEqual(w2._ruta_sesion_actual, ruta_jws)
        self.assertIn(os.path.basename(ruta_jws), w2.windowTitle())

    def test_guardar_y_cargar_sesion_json(self):
        self.w.cargar_carpeta(TARJETA)
        self.w.seleccionar_metodo(0)
        self.w.panel.txt_y_min.setText("0.10")

        ruta_json = self._temp_file(".json")
        self.w.guardar_sesion(ruta_destino=ruta_json)

        self.assertTrue(os.path.isfile(ruta_json))
        w2 = VentanaMaestro()
        w2.abrir_sesion(ruta_json)

        self.assertEqual(w2.metodo_actual.id, self.w.metodo_actual.id)
        self.assertEqual(w2.panel.txt_y_min.text(), "0.10")
        self.assertEqual(w2._ruta_sesion_actual, ruta_json)

    def test_guardar_y_cargar_documento_suelto(self):
        # Simular apertura de documento suelto
        r = {"serie": [(float(t), 50.0, 0.2 + 0.002 * t) for t in range(0, 181, 10)]}
        self.w._limpiar_seleccion()
        self.w._mostrar("kinetics", [r], ["Curva Suelta"], titulo="Mi Cinética Suelta")
        self.w.panel._marcas = [20.0, 40.0, 60.0]
        self.w.panel._render()

        ruta_jws = self._temp_file(".jws")
        self.w.guardar_sesion(ruta_destino=ruta_jws)

        w2 = VentanaMaestro()
        w2.abrir_sesion(ruta_jws)

        self.assertIsNone(w2.metodo_actual)
        self.assertEqual(w2.panel._modo, "kinetics")
        self.assertEqual(w2.panel._marcas, [20.0, 40.0, 60.0])
        self.assertEqual(w2.panel._titulo, "Mi Cinética Suelta")

    def test_arrastrar_y_soltar_sesion_jws(self):
        self.w.cargar_carpeta(TARJETA)
        self.w.seleccionar_metodo(0)
        ruta_jws = self._temp_file(".jws")
        self.w.guardar_sesion(ruta_destino=ruta_jws)

        w2 = VentanaMaestro()
        w2._abrir_rutas([ruta_jws])
        self.assertIsNotNone(w2.metodo_actual)
        self.assertEqual(w2.metodo_actual.id, self.w.metodo_actual.id)
        self.assertEqual(w2._ruta_sesion_actual, ruta_jws)


if __name__ == "__main__":
    unittest.main(verbosity=2)
