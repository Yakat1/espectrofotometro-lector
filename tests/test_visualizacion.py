# -*- coding: utf-8 -*-
"""Pruebas de la Fase 1 (visualización interactiva).

Comprueba la parte pura de la presentación (unidades, apilado) y el
comportamiento del panel y de la ventana sin necesidad de un ratón real:
el cursor se ejercita invocando el manejador con un evento simulado.

Se ejecuta en plataforma offscreen (sin ventanas visibles).
"""
import os
import sys
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QPA_FONTDIR", r"C:\Windows\Fonts")

MAESTRO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, MAESTRO)

import numpy as np                                            # noqa: E402
from PySide6.QtWidgets import QApplication, QListWidgetItem    # noqa: E402

_app = QApplication.instance() or QApplication(sys.argv[:1])

from jenway67.parser_jwb import decodificar                   # noqa: E402
from jenway67.reader import decodificar_archivo, leer_carpeta  # noqa: E402
from ui.toolbar_plot import (PanelGrafico, desplazamientos,    # noqa: E402
                             serie_para)
from ui.ventana import VentanaMaestro                         # noqa: E402

TARJETA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "tarjeta")
JWB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "jwb")


class Evento:
    """Evento de matplotlib simulado (sólo lo que usa el panel)."""

    def __init__(self, inaxes=None, xdata=None):
        self.inaxes = inaxes
        self.xdata = xdata


def decodifica(nombre, modo):
    with open(os.path.join(JWB, nombre), "rb") as fh:
        return decodificar(fh.read(), modo)[1]


class TestSeriePara(unittest.TestCase):
    """`serie_para`: qué se dibuja en cada unidad (lógica pura, sin widgets)."""

    @classmethod
    def setUpClass(cls):
        cls.esp = decodifica("323BE947_spectrum.JWB", "spectrum")
        cls.multi = decodifica("323BEA26_multi.JWB", "multi")
        cls.photo = decodifica("323BE7BA_photo_sat.JWB", "photometrics")

    def test_unidades_espectro(self):
        x1, y1, xl, yl = serie_para("spectrum", self.esp, "abs")
        x2, y2, _, yl2 = serie_para("spectrum", self.esp, "t")
        self.assertEqual(xl, "Longitud de onda (nm)")
        self.assertEqual(yl, "Absorbancia")
        self.assertEqual(yl2, "Transmitancia (%)")
        self.assertEqual(x1.size, y1.size)
        np.testing.assert_allclose(x1, x2)
        # coherencia A = -log10(T/100) en un punto no saturado
        i = int(np.argmax(np.isfinite(y1)))
        self.assertAlmostEqual(y1[i], -np.log10(y2[i] / 100.0), places=4)

    def test_multi_clampa_la_absorcion_saturada(self):
        x, y, _, yl = serie_para("multi", self.multi, "abs")
        self.assertEqual(x.size, 4)
        self.assertEqual(yl, "Absorbancia")
        self.assertTrue(np.all(np.isnan(y) | (y <= 3.0 + 1e-9)))
        self.assertAlmostEqual(y[0], 3.0, places=3)      # celda saturada -> display 3.000
        _, yt, _, ylt = serie_para("multi", self.multi, "t")
        self.assertEqual(ylt, "Transmitancia (%)")
        self.assertEqual(yt[0], 0.0)                     # %T real del .JWB

    def test_photometrics_saturada(self):
        _, y, _, _ = serie_para("photometrics", self.photo, "abs")
        self.assertAlmostEqual(y[0], 3.0, places=3)

    def test_modo_desconocido(self):
        x, y, _, _ = serie_para("quantitation", {}, "abs")
        self.assertEqual(x.size, 0)

    def test_desplazamientos(self):
        self.assertEqual(desplazamientos(3, 2.0), [0.0, 2.0, 4.0])
        self.assertEqual(desplazamientos(0), [])


class TestPanelGrafico(unittest.TestCase):
    def setUp(self):
        self.panel = PanelGrafico(tema="dark")
        self.esp1 = decodifica("323BE947_spectrum.JWB", "spectrum")
        self.esp2 = decodifica("323BD8FF_spectrum.JWB", "spectrum")

    def test_superposicion_de_dos_series(self):
        self.panel.dibujar("spectrum", [self.esp1, self.esp2], ["A", "B"], titulo="t")
        self.assertEqual(len(self.panel._series), 2)
        self.assertEqual(len(self.panel._lineas), 2)
        self.assertIsNotNone(self.panel.ax.get_legend())

    def test_barra_herramientas_en_espanol(self):
        acciones = self.panel.toolbar._actions
        self.assertEqual(acciones["home"].toolTip(), "Vista inicial")
        self.assertEqual(acciones["save_figure"].toolTip(), "Guardar imagen…")
        self.assertIn("Zoom", acciones["zoom"].toolTip())
        # las acciones de edición de ejes se retiran de la barra
        visibles = set(self.panel.toolbar.actions())
        self.assertNotIn(acciones["configure_subplots"], visibles)
        self.assertNotIn(acciones["edit_parameters"], visibles)

    def test_cambio_de_unidades_redibuja(self):
        self.panel.dibujar("spectrum", [self.esp1], ["A"])
        self.assertEqual(self.panel.ax.get_ylabel(), "Absorbancia")
        self.panel.combo_unidad.setCurrentIndex(1)
        self.assertEqual(self.panel.ax.get_ylabel(), "Transmitancia (%)")
        self.assertEqual(self.panel.unidad, "t")

    def test_vista_apilada_desplaza_solo_las_siguientes(self):
        self.panel.dibujar("spectrum", [self.esp1, self.esp2], ["A", "B"])
        y_super = [np.array(ln.get_ydata(), dtype=float) for ln in self.panel._lineas]
        self.panel.btn_vista.setChecked(True)
        y_api = [np.array(ln.get_ydata(), dtype=float) for ln in self.panel._lineas]
        self.assertEqual(len(y_api), 2)
        np.testing.assert_allclose(y_super[0], y_api[0])            # la 1.ª no se mueve
        self.assertFalse(np.allclose(y_super[1], y_api[1]))         # la 2.ª sí
        self.assertIn("apilado", self.panel.ax.get_ylabel())

    def test_cursor_lee_todas_las_series(self):
        self.panel.dibujar("spectrum", [self.esp1, self.esp2], ["A", "B"])
        textos = []
        self.panel.coordenadas.connect(textos.append)
        self.panel._al_mover(Evento(self.panel.ax, 450.0))
        self.assertTrue(textos, "el panel debe emitir la lectura del cursor")
        self.assertIn("A:", textos[-1])
        self.assertIn("B:", textos[-1])
        self.assertIn("nm", textos[-1])

    def test_paso_apilado_usa_la_mediana(self):
        # un blanco plano junto a un espectro con un pico enorme no debe quedar
        # empujado al borde superior: el paso se calcula con la mediana.
        y_plano = np.zeros(10)
        y_pico = np.linspace(0.0, 10.0, 10)
        paso = PanelGrafico._paso_apilado([("Blanco", y_plano, "", ""),
                                           ("Muestra", y_pico, "", "")])
        self.assertAlmostEqual(paso, 5.75, places=2)      # 1.15 × mediana(0, 10)

    def test_cursor_sale_del_grafico(self):
        self.panel.dibujar("spectrum", [self.esp1], ["A"])
        textos = []
        self.panel.coordenadas.connect(textos.append)
        self.panel._al_mover(Evento(self.panel.ax, 450.0))
        self.panel._al_salir(None)
        self.assertEqual(textos[-1], "")
        self.assertFalse(self.panel._cursor.get_visible())

    def test_sin_datos_limpia(self):
        self.panel.dibujar("spectrum", [self.esp1], ["A"])
        self.panel.limpiar()
        self.assertEqual(self.panel._resultados, [])
        self.assertEqual(self.panel._series, [])

    def test_calibracion_marca_la_muestra_interpolada(self):
        quant = decodifica("323BFC6F_quant.JWB", "quantitation")
        self.panel.dibujar("quantitation", [quant], ["Q"])
        marcador = [ln for ln in self.panel.ax.lines
                    if ln.get_marker() == "s" and ln.get_visible()]
        self.assertTrue(marcador, "debe dibujarse el marcador de la muestra")
        ya = float(marcador[0].get_ydata()[0])
        self.assertLess(ya, float(marcador[0].get_xdata()[0]))     # Conc < Abs (ya no (A,A))


class TestEjeYManual(unittest.TestCase):
    """El eje Y se puede fijar a mano (vacío = automático)."""

    def setUp(self):
        self.panel = PanelGrafico(tema="dark")
        self.esp = decodifica("323BE947_spectrum.JWB", "spectrum")

    def test_sin_rango_el_eje_es_automatico(self):
        self.panel.dibujar("spectrum", [self.esp], ["A"])
        lo, hi = self.panel.ax.get_ylim()
        self.assertLess(lo, hi)

    def test_fijar_el_rango_y_lo_aplica(self):
        self.panel.dibujar("spectrum", [self.esp], ["A"])
        self.panel.txt_y_min.setText("0")
        self.panel.txt_y_max.setText("1")
        self.panel._al_editar_y()
        lo, hi = self.panel.ax.get_ylim()
        self.assertAlmostEqual(lo, 0.0, places=6)
        self.assertAlmostEqual(hi, 1.0, places=6)

    def test_solo_el_minimo_deja_el_maximo_automatico(self):
        self.panel.dibujar("spectrum", [self.esp], ["A"])
        auto_hi = self.panel.ax.get_ylim()[1]
        self.panel.txt_y_min.setText("0")
        self.panel._al_editar_y()
        lo, hi = self.panel.ax.get_ylim()
        self.assertAlmostEqual(lo, 0.0, places=6)
        self.assertAlmostEqual(hi, auto_hi, places=6)

    def test_auto_vuelve_al_rango_automatico(self):
        self.panel.dibujar("spectrum", [self.esp], ["A"])
        self.panel.txt_y_min.setText("0")
        self.panel.txt_y_max.setText("1")
        self.panel._al_editar_y()
        self.panel._y_automatico()
        self.assertEqual(self.panel.txt_y_min.text(), "")
        self.assertEqual(self.panel.txt_y_max.text(), "")
        lo, hi = self.panel.ax.get_ylim()
        self.assertLess(lo, hi)

    def test_cambiar_de_unidad_suelta_el_rango_manual(self):
        self.panel.dibujar("spectrum", [self.esp], ["A"])
        self.panel.txt_y_min.setText("0")
        self.panel.txt_y_max.setText("1")
        self.panel._al_editar_y()
        self.panel.combo_unidad.setCurrentIndex(1)          # %T
        self.assertEqual(self.panel.txt_y_min.text(), "")
        self.assertEqual(self.panel.txt_y_max.text(), "")

    def test_cambiar_de_modo_suelta_el_rango_manual(self):
        self.panel.dibujar("spectrum", [self.esp], ["A"])
        self.panel.txt_y_min.setText("0")
        self.panel.txt_y_max.setText("1")
        self.panel._al_editar_y()
        with open(os.path.join(JWB, "323BFE3F_kinetics.JWB"), "rb") as fh:
            kin = decodificar(fh.read(), "kinetics")[1]
        self.panel.dibujar("kinetics", [kin], ["A"])
        self.assertEqual(self.panel.txt_y_min.text(), "")
        self.assertEqual(self.panel.txt_y_max.text(), "")

    def test_rango_invalido_no_rompe(self):
        self.panel.dibujar("spectrum", [self.esp], ["A"])
        self.panel.txt_y_min.setText("cuatro")
        self.panel.txt_y_max.setText("1")
        self.panel._al_editar_y()                          # no debe lanzar
        self.assertTrue(np.isfinite(self.panel.ax.get_ylim()[0]))


class TestVentanaFase1(unittest.TestCase):
    def setUp(self):
        self.w = VentanaMaestro(carpeta=TARJETA, tema="dark")

    def test_seleccion_multiple_superpone_y_agrega(self):
        w = self.w
        fila = None
        for i in range(len(w.items_de_metodos())):
            m = w.metodo_en_fila(i)
            if m is not None and m.modo == "spectrum":
                fila = i
                break
        self.assertIsNotNone(fila, "debe haber un método de espectro")
        self.assertTrue(w.seleccionar_metodo(fila))
        # dos espectros reales de la tarjeta (Ctrl+clic equivalente)
        w._muestras_actuales = [("Esp A", "323BE947.JWB"), ("Esp B", "323BDC04.JWB")]
        w.lista_muestras.clear()
        for etq, _ in w._muestras_actuales:
            w.lista_muestras.addItem(QListWidgetItem(etq))
        w._seleccionar_todas()
        self.assertEqual(len(w.panel._series), 2, "deben superponerse las dos muestras")
        self.assertEqual(w.tabla_analisis.item(0, 0).text(), "n_muestras")
        self.assertEqual(w.tabla_analisis.item(0, 1).text(), "2")

    def test_deseleccionar_limpia_el_panel(self):
        self.w.lista_muestras.clearSelection()
        self.assertEqual(self.w.panel._resultados, [])

    def test_coordenadas_van_a_la_barra_de_estado(self):
        w = self.w
        _, r1 = decodificar_archivo(w.tarjeta, "323BE947.JWB", "spectrum")
        _, r2 = decodificar_archivo(w.tarjeta, "323BDC04.JWB", "spectrum")
        w._mostrar("spectrum", [r1, r2], ["Esp A", "Esp B"])
        w.panel._al_mover(Evento(w.panel.ax, 450.0))
        msg = w.statusBar().currentMessage()
        self.assertIn("Esp A:", msg)
        self.assertIn("Esp B:", msg)
        w.panel._al_salir(None)
        self.assertNotIn("Esp A:", w.statusBar().currentMessage())


# --------------------------------------------------------------------------
# pulido profesional del panel: zoom, barras, picos, imagen
# --------------------------------------------------------------------------

class TestZoomNoPierdeLoDibujado(unittest.TestCase):
    """Regresión del fallo reportado: al hacer zoom y luego mover el ratón, las
    barras desaparecían.

    Causa: `FigureCanvasQTAgg` hereda un `blit()` VACÍO de `FigureCanvasBase`, así
    que el cursor "re-pegaba" con `restore_region` un fondo capturado ANTES del
    zoom y en el lienzo volvía la imagen previa. Ahora no hay blitting: se
    actualiza la cruz y se pide un redibujado (matplotlib lo agrupa)."""

    def setUp(self):
        self.panel = PanelGrafico(tema="dark")
        self.panel.resize(820, 520)
        with open(os.path.join(JWB, "323BEA26_multi.JWB"), "rb") as fh:
            self.multi = decodificar(fh.read(), "multi")[1]

    def _buffer(self) -> np.ndarray:
        self.panel.canvas.draw()
        crudo = np.frombuffer(self.panel.canvas.buffer_rgba(), dtype=np.uint8)
        w, h = self.panel.canvas.get_width_height()
        if crudo.size != w * h * 4:
            w = crudo.size // 4 // max(h, 1)
        return np.array(crudo, dtype=np.int16).reshape(h, w, 4)

    def _color_en(self, x_dato: float, y_dato: float):
        """Color RGB del píxel donde cae un punto de datos (el buffer empieza
        arriba-izquierda; transData usa origen abajo-izquierda)."""
        buf = self._buffer()
        h = buf.shape[0]
        mx, my = self.panel.ax.transData.transform((x_dato, y_dato))
        return tuple(int(v) for v in buf[h - 1 - int(round(my)), int(round(mx)), :3])

    @staticmethod
    def _cerca(obtenido, esperado, tol=40):
        return all(abs(a - b) <= tol for a, b in zip(obtenido, esperado))

    def test_zoom_y_raton_conservan_las_barras(self):
        p = self.panel
        p.dibujar("multi", [self.multi], ["Muestra"], titulo="zoom")
        p.show()
        _app.processEvents()
        barra = (61, 139, 253)                     # #3d8bfd, color de la 1.ª serie
        # se muestrea el cuerpo de la barra de 400 nm: tras mover el ratón la cruz
        # queda en 330 nm y taparía el píxel si muestreásemos esa barra
        punto = (400.0, -0.1)

        self.assertTrue(self._cerca(self._color_en(*punto), barra),
                        "sin zoom, el cuerpo de la barra de 400 nm debe estar pintado")

        # zoom rectangular equivalente al de la barra de herramientas
        p.ax.set_xlim(305.0, 415.0)
        p.ax.set_ylim(-0.5, 0.25)
        p.canvas.draw()
        _app.processEvents()
        self.assertTrue(self._cerca(self._color_en(*punto), barra),
                        "tras el zoom la barra sigue pintada")

        # mover el ratón: aquí es donde antes volvía la imagen previa al zoom
        p._al_mover(Evento(p.ax, 330.0))
        _app.processEvents()
        self.assertTrue(self._cerca(self._color_en(*punto), barra),
                        "al mover el ratón la barra NO debe desaparecer")

    def test_mover_el_raton_apenas_cambia_los_pixeles(self):
        p = self.panel
        p.dibujar("multi", [self.multi], ["Muestra"], titulo="zoom")
        p.ax.set_xlim(305.0, 415.0)
        p.ax.set_ylim(-0.5, 0.25)
        tras_zoom = self._buffer()
        p._al_mover(Evento(p.ax, 330.0))
        tras_hover = self._buffer()
        dif = np.abs(tras_zoom - tras_hover)[:, :, :3].max(axis=2)
        self.assertLess(float((dif > 10).mean()), 0.05,
                        "sólo deben cambiar la cruz y los marcadores del cursor")

    def test_ajustar_a_los_datos_deshace_el_zoom(self):
        p = self.panel
        p.dibujar("multi", [self.multi], ["Muestra"], titulo="zoom")
        completo = p.ax.get_xlim()
        p.ax.set_xlim(305.0, 415.0)
        p.ajustar_a_datos()
        self.assertAlmostEqual(p.ax.get_xlim()[0], completo[0], places=6)
        self.assertAlmostEqual(p.ax.get_xlim()[1], completo[1], places=6)


class TestBarrasYFotometria(unittest.TestCase):
    def setUp(self):
        self.panel = PanelGrafico(tema="dark")
        self.panel.resize(820, 520)

    def _buffer(self) -> np.ndarray:
        self.panel.canvas.draw()
        crudo = np.frombuffer(self.panel.canvas.buffer_rgba(), dtype=np.uint8)
        w, h = self.panel.canvas.get_width_height()
        if crudo.size != w * h * 4:
            w = crudo.size // 4 // max(h, 1)
        return np.array(crudo, dtype=np.int16).reshape(h, w, 4)

    def test_fotometria_se_dibuja_como_barras(self):
        # antes se dibujaba como una línea de UN solo punto -> invisible
        with open(os.path.join(JWB, "323BCBA4_photo_lowry.JWB"), "rb") as fh:
            foto = decodificar(fh.read(), "photometrics")[1]
        self.panel.dibujar("photometrics", [foto], ["Lowry"], titulo="fotometría")
        self.panel.show()
        _app.processEvents()
        self.assertTrue(self.panel.ax.patches, "debe haber barras dibujadas")
        buf = self._buffer()
        h = buf.shape[0]
        mx, my = self.panel.ax.transData.transform((0.0, foto["abs"] / 2.0))
        color = tuple(int(v) for v in buf[h - 1 - int(round(my)), int(round(mx)), :3])
        self.assertTrue(all(abs(a - b) <= 40 for a, b in zip(color, (61, 139, 253))),
                        f"el cuerpo de la barra debe estar pintado (color={color})")

    def test_barras_etiquetan_su_valor(self):
        with open(os.path.join(JWB, "323BEA26_multi.JWB"), "rb") as fh:
            multi = decodificar(fh.read(), "multi")[1]
        self.panel.dibujar("multi", [multi], ["Muestra"], titulo="multi")
        textos = [t.get_text() for t in self.panel.ax.texts]
        self.assertTrue(any(t.startswith("-0.30") for t in textos), textos)
        self.assertTrue(any(t.startswith("3.000") for t in textos), textos)

    def test_multi_anota_los_calculos_del_instrumento(self):
        with open(os.path.join(JWB, "323BEA26_multi.JWB"), "rb") as fh:
            multi = decodificar(fh.read(), "multi")[1]
        self.panel.dibujar("multi", [multi], ["Muestra"], titulo="multi")
        textos = " ".join(t.get_text() for t in self.panel.ax.texts)
        self.assertIn("A1/A2", textos)
        self.assertIn("A1-A2", textos)

    def test_fotometria_con_varias_replicas_etiqueta_las_barras(self):
        """Cada réplica es una barra con su etiqueta: así la leyenda tiene sentido
        y no salta el aviso de 'no artists with labels'."""
        with open(os.path.join(JWB, "323BCBA4_photo_lowry.JWB"), "rb") as fh:
            foto1 = decodificar(fh.read(), "photometrics")[1]
        with open(os.path.join(JWB, "323BE7BA_photo_sat.JWB"), "rb") as fh:
            foto2 = decodificar(fh.read(), "photometrics")[1]
        self.panel.dibujar("photometrics", [foto1, foto2], ["Lowry", "Saturada"],
                           titulo="fotometría")
        leyenda = self.panel.ax.get_legend()
        self.assertIsNotNone(leyenda, "con varias réplicas debe haber leyenda")
        self.assertEqual([t.get_text() for t in leyenda.get_texts()],
                         ["Lowry", "Saturada"])
        self.assertEqual(len(self.panel.ax.patches), 2)

    def test_barras_multi_giran_las_etiquetas_juntas(self):
        """300 y 330 nm juntos se leían como '300330': deben girarse."""
        with open(os.path.join(JWB, "323BEA26_multi.JWB"), "rb") as fh:
            multi = decodificar(fh.read(), "multi")[1]
        self.panel.dibujar("multi", [multi], ["Muestra"], titulo="multi")
        rotaciones = [t.get_rotation() for t in self.panel.ax.get_xticklabels()]
        self.assertTrue(rotaciones and all(r > 0 for r in rotaciones), rotaciones)

    def test_barras_multi_no_gira_si_estan_separadas(self):
        falso = {"modo": "multi", "wls": [400.0, 500.0, 600.0, 700.0],
                 "A1/A2": None, "A1-A2": None,
                 "celdas": [{"wl": float(w), "etiqueta": f"A{i + 1}", "t": 50.0, "abs": 0.3}
                            for i, w in enumerate((400.0, 500.0, 600.0, 700.0))]}
        self.panel.dibujar("multi", [falso], ["Muestra"], titulo="multi")
        rotaciones = [t.get_rotation() for t in self.panel.ax.get_xticklabels()]
        self.assertTrue(all(r == 0 for r in rotaciones), rotaciones)


class TestMarcadoDePicos(unittest.TestCase):
    def setUp(self):
        self.panel = PanelGrafico(tema="dark")
        # 190-900 nm: tiene picos reales (el otro fixture es un blanco)
        self.esp = decodifica("323BE947_spectrum.JWB", "spectrum")

    def _marcadores_de_picos(self):
        return [ln for ln in self.panel.ax.lines
                if ln.get_marker() == "o" and ln.get_color() == "#3d8bfd"]

    def test_marca_picos_por_defecto(self):
        self.panel.dibujar("spectrum", [self.esp], ["A"], titulo="espectro")
        self.assertTrue(self.panel.marcar_picos)
        self.assertTrue(self._marcadores_de_picos(), "debe marcar los picos del espectro")
        etiquetas = [t.get_text() for t in self.panel.ax.texts]
        self.assertTrue(etiquetas, "y etiquetarlos con su longitud de onda")

    def test_se_pueden_desactivar(self):
        self.panel.chk_picos.setChecked(False)
        self.panel.dibujar("spectrum", [self.esp], ["A"], titulo="espectro")
        self.assertFalse(self._marcadores_de_picos())

    def test_un_blanco_no_marca_picos(self):
        """Un espectro plano (blanco) no tiene máximos significativos que marcar."""
        blanco = decodifica("323BD8FF_spectrum.JWB", "spectrum")
        self.panel.dibujar("spectrum", [blanco], ["Blanco"], titulo="blanco")
        self.assertFalse(self._marcadores_de_picos())
        self.assertFalse([t.get_text() for t in self.panel.ax.texts])

    def test_marca_picos_tambien_en_transmitancia(self):
        """La prominencia se calcula sobre absorbancia, así que ver el espectro en
        %T (rango 0..46) no debe impedir marcar los picos."""
        self.panel.combo_unidad.setCurrentIndex(1)          # Transmitancia
        self.panel.dibujar("spectrum", [self.esp], ["A"], titulo="espectro en %T")
        self.assertEqual(self.panel.ax.get_ylabel(), "Transmitancia (%)")
        self.assertTrue(self._marcadores_de_picos(),
                        "debe marcar picos también con el eje en %T")

    def test_las_etiquetas_de_picos_no_se_solapan(self):
        self.panel.dibujar("spectrum", [self.esp], ["A"], titulo="espectro")
        # OJO: en annotate(get_position) devuelve el DESPLAZAMIENTO, no el punto
        # anotado; el punto está en `.xy`.
        xs = sorted(t.xy[0] for t in self.panel.ax.texts)
        self.assertGreaterEqual(len(xs), 2, "este espectro tiene varios picos")
        # la separación garantizada es el 5 % del rango de longitudes de onda
        wls = [p[0] for p in self.esp["puntos"]]
        rango = max(wls) - min(wls)
        for a, b in zip(xs, xs[1:]):
            self.assertGreaterEqual(b - a, 0.049 * rango,
                                    f"etiquetas de picos demasiado juntas: {a} y {b}")

    def test_los_marcadores_siguen_la_curva_en_vista_apilada(self):
        """En la vista apilada cada serie va desplazada: sus marcas de picos deben
        llevar el MISMO desplazamiento o se despegan de la curva."""
        self.panel.dibujar("spectrum", [self.esp, self.esp], ["A", "B"], titulo="dos")
        self.panel.btn_vista.setChecked(True)
        marcadores = [ln for ln in self.panel.ax.lines
                      if ln.get_marker() == "o" and len(ln.get_xdata()) > 0]
        self.assertGreaterEqual(len(marcadores), 2, "cada serie con picos lleva sus marcas")
        curva = self.panel._lineas[1]                 # 2.ª serie: va desplazada
        xs_c = np.asarray(curva.get_xdata(), dtype=float)
        ys_c = np.asarray(curva.get_ydata(), dtype=float)
        xs_m = np.asarray(marcadores[1].get_xdata(), dtype=float)
        ys_m = np.asarray(marcadores[1].get_ydata(), dtype=float)
        self.assertTrue(xs_m.size)
        for xm, ym in zip(xs_m, ys_m):
            j = int(np.argmin(np.abs(xs_c - xm)))
            self.assertAlmostEqual(float(ym), float(ys_c[j]), places=6,
                                   msg="la marca del pico se despegó de la curva apilada")

    def test_en_cinetica_no_marca_picos(self):
        with open(os.path.join(JWB, "323BFE3F_kinetics.JWB"), "rb") as fh:
            kin = decodificar(fh.read(), "kinetics")[1]
        self.panel.dibujar("kinetics", [kin], ["A"], titulo="cinética")
        self.assertFalse(self._marcadores_de_picos(), "los picos son sólo del espectro")


class TestImagenDelGrafico(unittest.TestCase):
    def setUp(self):
        self.panel = PanelGrafico(tema="dark")
        self.esp = decodifica("323BE947_spectrum.JWB", "spectrum")

    def test_copiar_imagen_al_portapapeles(self):
        self.panel.dibujar("spectrum", [self.esp], ["A"], titulo="t")
        avisos = []
        self.panel.mensaje.connect(avisos.append)
        self.panel.copiar_imagen()
        self.assertTrue(avisos and "portapapeles" in avisos[-1], avisos)
        self.assertFalse(QApplication.clipboard().image().isNull())


if __name__ == "__main__":
    unittest.main(verbosity=2)