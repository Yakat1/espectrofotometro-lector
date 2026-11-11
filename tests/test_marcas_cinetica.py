# -*- coding: utf-8 -*-
"""Pruebas de las marcas de cinética y su bitácora (PanelGrafico).

Cubre la interacción pedida: clic para marcar/quitar puntos de interés y
marcas automáticas cada N segundos, con la bitácora de absorbancias.
"""
import os
import sys
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QPA_FONTDIR", r"C:\Windows\Fonts")

MAESTRO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, MAESTRO)

from PySide6.QtWidgets import QApplication  # noqa: E402

_app = QApplication.instance() or QApplication(sys.argv[:1])

from ui.toolbar_plot import PanelGrafico  # noqa: E402
from ui.ventana import VentanaMaestro     # noqa: E402

TARJETA = os.path.join(MAESTRO, "tests", "data", "tarjeta")


class TestMarcasCinetica(unittest.TestCase):
    def setUp(self):
        self.p = PanelGrafico(tema="dark")
        self.mensajes = []
        self.p.mensaje.connect(self.mensajes.append)
        # Cinética sintética: índice 0..300 (≈ s), absorbancia creciente.
        self.r = {"serie": [(float(i), 50.0, 0.05 + 0.001 * i) for i in range(0, 301)]}
        self.p.dibujar("kinetics", [self.r], ["Muestra"])

    def _clic(self, x):
        ev = type("Ev", (), {})()
        ev.button = 1
        ev.inaxes = self.p.ax
        ev.xdata = x
        self.p._al_click(ev)

    def test_clic_anade_marca(self):
        self._clic(60.0)
        self.assertIn(60.0, self.p._marcas)

    def test_clic_en_la_misma_marca_la_quita(self):
        self._clic(60.0)
        self._clic(60.0)
        self.assertEqual(self.p._marcas, [])

    def test_marcar_intervalo(self):
        self.p.spin_intervalo.setValue(30)
        self.p._marcar_intervalo()
        # 0, 30, ..., 300 → 11 marcas.
        self.assertEqual(len(self.p._marcas), 11)
        self.assertIn(30.0, self.p._marcas)
        self.assertIn(90.0, self.p._marcas)

    def test_bitacora_refleja_las_marcas(self):
        self.p.spin_intervalo.setValue(90)
        self.p._marcar_intervalo()
        # Columnas = Tiempo + 1 serie.
        self.assertEqual(self.p.tabla_marcas.columnCount(), 2)
        self.assertEqual(self.p.tabla_marcas.rowCount(), len(self.p._marcas))
        self.assertEqual(self.p.tabla_marcas.item(0, 0).text(), "0.0")
        self.assertEqual(self.p.tabla_marcas.item(1, 0).text(), "90.0")

    def test_desglose_automatico_carriles_en_panel_grafico(self):
        serie_combinada = (
            [(float(i), 50.0, 1.8 - 0.005 * i) for i in range(0, 301, 60)] +
            [(float(i), 50.0, 0.1 + 0.003 * i) for i in range(0, 301, 60)]
        )
        tiempos_comb = [0.0, 60.0, 120.0, 180.0, 240.0, 300.0, 0.0, 60.0, 120.0, 180.0, 240.0, 300.0]
        r_comb = {"serie": serie_combinada, "tiempos": tiempos_comb}
        self.p.dibujar("kinetics", [r_comb], ["Muestra #1"])
        self.assertEqual(len(self.p._series), 2)
        self.assertIn("Carril 1", self.p._series[0][0])
        self.assertIn("Carril 2", self.p._series[1][0])
        self.p.spin_intervalo.setValue(60)
        self.p._marcar_intervalo()
        self.assertEqual(self.p.tabla_marcas.columnCount(), 3)

    def test_bitacora_muestra_absorbancia_aunque_el_grafico_sea_transmitancia(self):
        self.p.spin_intervalo.setValue(90)
        self.p._marcar_intervalo()
        self.p.combo_unidad.setCurrentIndex(1)          # %T en el gráfico
        # La bitácora sigue en absorbancia: en t=0 vale 0.050.
        self.assertEqual(self.p.tabla_marcas.item(0, 1).text(), "0.050")

    def test_borrar_marcas(self):
        self._clic(30.0)
        self.p._borrar_marcas()
        self.assertEqual(self.p._marcas, [])
        self.assertEqual(self.p.tabla_marcas.rowCount(), 0)

    def test_clic_en_espectro_no_marca(self):
        r = {"puntos": [(float(w), 50.0, 0.5) for w in range(190, 900, 10)]}
        self.p.dibujar("spectrum", [r], ["Esp"])
        self._clic(500.0)
        self.assertEqual(self.p._marcas, [])

    # ------------------------------------------------- graficar los marcados
    def test_resultados_marcados_coge_solo_las_marcas(self):
        self.p.spin_intervalo.setValue(60)
        self.p._marcar_intervalo()            # 0, 60, ..., 300 -> 6 marcas
        reducidos, etiquetas = self.p.resultados_marcados()
        self.assertEqual(etiquetas, ["Muestra"])
        self.assertEqual(reducidos[0]["tiempos"], [0.0, 60.0, 120.0, 180.0, 240.0, 300.0])
        # abs en t=60 es 0.05 + 0.001·60 = 0.11
        self.assertAlmostEqual(reducidos[0]["serie"][1][2], 0.11, places=6)

    def test_resultados_marcados_usa_las_filas_elegidas(self):
        self.p.spin_intervalo.setValue(90)
        self.p._marcar_intervalo()            # 0, 90, 180, 270
        self.p.tabla_marcas.selectRow(1)      # solo t=90
        reducidos, _etq = self.p.resultados_marcados()
        self.assertEqual(reducidos[0]["tiempos"], [90.0])

    def test_sin_marcas_no_hay_nada_que_graficar(self):
        self.assertEqual(self.p.resultados_marcados(), ([], []))

    def test_el_boton_de_graficar_se_activa_con_marcas(self):
        self.assertFalse(self.p.btn_graficar_marcados.isEnabled())
        self._clic(60.0)
        self.assertTrue(self.p.btn_graficar_marcados.isEnabled())

    def test_los_botones_de_copiar_y_exportar_se_activan_con_marcas(self):
        self.assertFalse(self.p.btn_copiar_bitacora.isEnabled())
        self.assertFalse(self.p.btn_exportar_bitacora_xlsx.isEnabled())
        self._clic(60.0)
        self.assertTrue(self.p.btn_copiar_bitacora.isEnabled())
        self.assertTrue(self.p.btn_exportar_bitacora_xlsx.isEnabled())
        self.p._borrar_marcas()
        self.assertFalse(self.p.btn_copiar_bitacora.isEnabled())
        self.assertFalse(self.p.btn_exportar_bitacora_xlsx.isEnabled())

    def test_copiar_bitacora_clipboard(self):
        self.p.spin_intervalo.setValue(60)
        self.p._marcar_intervalo()
        self.p._copiar_bitacora_clipboard()
        cb = QApplication.clipboard()
        mime = cb.mimeData()
        self.assertTrue(mime.hasText())
        self.assertTrue(mime.hasHtml())
        tsv = mime.text()
        self.assertIn("Tiempo (s)\tMuestra", tsv)
        self.assertIn("60.0\t", tsv)
        html = mime.html()
        self.assertIn("<table", html)
        self.assertIn("Tiempo (s)", html)

    def test_copiar_bitacora_filas_seleccionadas(self):
        self.p.spin_intervalo.setValue(60)
        self.p._marcar_intervalo()
        self.p.tabla_marcas.selectRow(1)  # t=60
        self.p._copiar_bitacora_clipboard(solo_seleccionadas=True)
        tsv = QApplication.clipboard().text()
        lineas = tsv.strip().splitlines()
        self.assertEqual(len(lineas), 2)  # cabecera + fila seleccionada
        self.assertTrue(lineas[1].startswith("60.0\t"))

    def test_exportar_bitacora_xlsx(self):
        import tempfile
        import openpyxl
        self.p.spin_intervalo.setValue(60)
        self.p._marcar_intervalo()
        with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tf:
            temp_path = tf.name
        try:
            self.p._exportar_bitacora_xlsx(ruta_destino=temp_path)
            self.assertTrue(os.path.exists(temp_path))
            self.assertGreater(os.path.getsize(temp_path), 0)
            wb = openpyxl.load_workbook(temp_path)
            self.assertIn("Bitácora Cinética", wb.sheetnames)
            ws = wb["Bitácora Cinética"]
            cabecera_fila = [ws.cell(row=1, column=c).value for c in range(1, 3)]
            self.assertEqual(cabecera_fila, ["Tiempo (s)", "Muestra"])
            t0 = ws.cell(row=2, column=1).value
            abs0 = ws.cell(row=2, column=2).value
            self.assertIsInstance(t0, (int, float))
            self.assertIsInstance(abs0, (int, float))
            self.assertEqual(t0, 0.0)
            self.assertAlmostEqual(abs0, 0.050, places=3)
            self.assertEqual(ws.cell(row=2, column=1).number_format, "0.0")
            self.assertEqual(ws.cell(row=2, column=2).number_format, "0.000")
            wb.close()
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    def test_menu_contextual_bitacora(self):
        from PySide6.QtCore import QPoint
        self.p._borrar_marcas()
        self.p._menu_contextual_bitacora(QPoint(10, 10))
        self.p.spin_intervalo.setValue(60)
        self.p._marcar_intervalo()
        cab, filas = self.p._datos_bitacora(solo_seleccionadas=False)
        self.assertEqual(cab, ["Tiempo (s)", "Muestra"])
        self.assertEqual(len(filas), 6)
        self.p.tabla_marcas.selectRow(0)
        cab_sel, filas_sel = self.p._datos_bitacora(solo_seleccionadas=True)
        self.assertEqual(len(filas_sel), 1)

    def test_un_panel_sin_marcas_no_deja_marcar(self):
        p = PanelGrafico(tema="dark", con_marcas=False)
        p.dibujar("kinetics", [self.r], ["Muestra"])
        ev = type("Ev", (), {})()
        ev.button, ev.inaxes, ev.xdata = 1, p.ax, 60.0
        p._al_click(ev)
        self.assertEqual(p._marcas, [])


class TestGraficarMarcadosEnLaVentana(unittest.TestCase):
    def setUp(self):
        self.w = VentanaMaestro(tema="dark")
        self.w.cargar_carpeta(TARJETA)
        for i in range(len(self.w.items_de_metodos())):
            m = self.w.metodo_en_fila(i)
            if m and m.modo == "kinetics":
                self.w.seleccionar_metodo(i)
                return
        self.skipTest("la tarjeta no tiene cinéticas")

    def _marcar(self):
        self.w._seleccionar_todas()
        self.w.panel.spin_intervalo.setValue(5)
        self.w.panel._marcar_intervalo()

    def test_graficar_marcados_crea_la_pestana(self):
        self._marcar()
        self.assertTrue(self.w.panel._marcas)
        self.assertEqual(self.w.tabs.indexOf(self.w.panel_marcados), -1)
        self.w._graficar_marcados()
        idx = self.w.tabs.indexOf(self.w.panel_marcados)
        self.assertGreaterEqual(idx, 0)
        self.assertEqual(self.w.tabs.tabText(idx), "Puntos marcados")
        self.assertEqual(self.w.tabs.currentIndex(), idx)
        self.assertEqual(len(self.w.panel_marcados._series), len(self.w.panel._series))

    def test_cambiar_de_datos_quita_la_pestana(self):
        self._marcar()
        self.w._graficar_marcados()
        self.assertGreaterEqual(self.w.tabs.indexOf(self.w.panel_marcados), 0)
        self.w._reprocesar()                  # -> _mostrar -> invalida las marcas
        self.assertEqual(self.w.tabs.indexOf(self.w.panel_marcados), -1)

    def test_sin_marcas_avisa_y_no_crea_pestana(self):
        self.w.panel._borrar_marcas()
        self.w._graficar_marcados()
        self.assertEqual(self.w.tabs.indexOf(self.w.panel_marcados), -1)
        self.assertIn("no tienen", self.w.statusBar().currentMessage())


if __name__ == "__main__":
    unittest.main(verbosity=2)
