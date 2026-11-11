# -*- coding: utf-8 -*-
"""Prueba de humo de la GUI: construye la ventana, carga una tarjeta, selecciona
una muestra y RENDERIZA la ventana a PNG (plataforma offscreen) para verla.

Importante: crear el QApplication ANTES de importar los módulos de UI.
"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QPA_FONTDIR", r"C:\Windows\Fonts")   # fuentes para el render offscreen
RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # carpeta maestro/
sys.path.insert(0, RAIZ)
print("[1] path ok", flush=True)

from PySide6.QtWidgets import QApplication  # noqa: E402
print("[2] pyside ok", flush=True)

app = QApplication(sys.argv[:1])            # <- primero la app
print("[3] qapp ok", flush=True)

from ui import estilos                       # noqa: E402
from ui.ventana import VentanaMaestro        # noqa: E402
print("[4] ui importada", flush=True)

TARJETA = os.path.join(RAIZ, "tests", "data", "tarjeta")
salida = os.path.join(RAIZ, "_ui_preview")
os.makedirs(salida, exist_ok=True)

app.setStyleSheet(estilos.qss("dark"))
print("[5] construyendo ventana", flush=True)
w = VentanaMaestro(carpeta=TARJETA, tema="dark")
print("[6] ventana construida", flush=True)
w.resize(1280, 760)
w.show()
app.processEvents()
print("[7] mostrada", flush=True)

# seleccionar un método de espectro y su muestra
for i in range(len(w.items_de_metodos())):
    m = w.metodo_en_fila(i)
    if getattr(m, "modo", "") == "spectrum":
        w.seleccionar_metodo(i)
        break
app.processEvents()
w.lista_muestras.setCurrentRow(0)
app.processEvents()

p_dark = os.path.join(salida, "ventana_oscuro.png")
w.grab().save(p_dark)
print("guardado:", p_dark, flush=True)

w.set_tema("light")
app.processEvents()
p_light = os.path.join(salida, "ventana_claro.png")
w.grab().save(p_light)
print("guardado:", p_light, flush=True)

# --- Fase 1: superposición de las 4 muestras REALES del método cinética "Test2" ---
fila_kin = None
for i in range(len(w.items_de_metodos())):
    met = w.metodo_en_fila(i)
    if getattr(met, "modo", "") == "kinetics" and len(met.muestras) >= 4:
        fila_kin = i
        break
if fila_kin is None:
    print("AVISO: no se encontró el método cinética con 4 muestras", flush=True)
else:
    w.seleccionar_metodo(fila_kin)
    app.processEvents()
    w._seleccionar_todas()                              # las 4 muestras superpuestas
    app.processEvents()
    print("series superpuestas (datos reales):", len(w.panel._series), flush=True)
    p_over = os.path.join(salida, "ventana_overlay.png")
    w.grab().save(p_over)
    print("guardado:", p_over, flush=True)

    _ev = type("Ev", (), {})()
    _ev.inaxes = w.panel.ax
    _ev.xdata = 5.0
    w.panel._al_mover(_ev)
    print("coordenadas cursor:", w.statusBar().currentMessage(), flush=True)

    w.panel.btn_vista.setChecked(True)                  # vista apilada
    app.processEvents()
    p_api = os.path.join(salida, "ventana_apilada.png")
    w.grab().save(p_api)
    print("guardado:", p_api, flush=True)

    w.panel.combo_unidad.setCurrentIndex(1)             # Transmitancia
    app.processEvents()
    print("eje Y con %T:", w.panel.ax.get_ylabel(), flush=True)

# --- Fase 2: árbol por modo, búsqueda, filtro por usuario, archivos sueltos ---
grupos = [w.arbol_metodos.topLevelItem(i).text(0) for i in range(w.arbol_metodos.topLevelItemCount())]
print("grupos por modo:", grupos, flush=True)

w.busqueda.setText("test1")                     # búsqueda insensible a tildes/mayúsculas
app.processEvents()
print("filtro 'test1' ->", len(w.items_de_metodos()), "métodos", flush=True)
w.busqueda.clear()

for i in range(w.combo_usuario.count()):
    if w.combo_usuario.itemData(i) == "Supervisor":
        w.combo_usuario.setCurrentIndex(i)
        break
app.processEvents()
print("filtro usuario Supervisor ->", len(w.items_de_metodos()), "métodos", flush=True)
w.combo_usuario.setCurrentIndex(0)
app.processEvents()

w._abrir_rutas([os.path.join(RAIZ, "tests", "data", "jwb", "323BE947_spectrum.JWB")])
app.processEvents()
print("JWB suelto -> filas de tabla:", w.modelo_datos.rowCount(),
      "| series:", len(w.panel._series), flush=True)
p_suelto = os.path.join(salida, "ventana_fase2.png")
w.grab().save(p_suelto)
print("guardado:", p_suelto, flush=True)

w._abrir_rutas([os.path.join(RAIZ, "tests", "data", "reportes", "4A.TXT")])
app.processEvents()
print("reporte 4A.TXT -> filas:", w.modelo_datos.rowCount(),
      "| titulo:", w.panel.ax.get_title(), flush=True)

# --- Pulido del panel: barras con valores, zoom, picos, fotometría ---
from jenway67.parser_jwb import decodificar as _decodificar      # noqa: E402
from PySide6.QtGui import QImage                                 # noqa: E402
import numpy as _np                                              # noqa: E402


def _jwb(nombre, modo):
    with open(os.path.join(RAIZ, "tests", "data", "jwb", nombre), "rb") as fh:
        return _decodificar(fh.read(), modo)[1]


def _png_del_lienzo(panel, ruta):
    """Lo que hay pintado AHORA en el lienzo (no re-renderizado)."""
    crudo = _np.frombuffer(panel.canvas.buffer_rgba(), dtype=_np.uint8)
    w_, h_ = panel.canvas.get_width_height()
    if crudo.size != w_ * h_ * 4:
        w_ = crudo.size // 4 // max(h_, 1)
    QImage(crudo.tobytes(), w_, h_, 4 * w_, QImage.Format.Format_RGBA8888).save(ruta)


def _png_del_modelo(panel, ruta):
    panel.fig.savefig(ruta, dpi=110, bbox_inches="tight")


w.panel.combo_unidad.setCurrentIndex(0)          # volver a absorbancia (por defecto)
w.panel.btn_vista.setChecked(False)              # y a la vista superpuesta
app.processEvents()
w.panel.dibujar("multi", [_jwb("323BEA26_multi.JWB", "multi")], ["Muestra"],
                titulo="Multi-longitud — barras con su valor")
app.processEvents()
_png_del_modelo(w.panel, os.path.join(salida, "panel_multi_barras.png"))
print("multi: barras + anotaciones =", len(w.panel.ax.texts), flush=True)

# zoom sobre las barras y movimiento del ratón (el fallo reportado)
w.panel.ax.set_xlim(305.0, 415.0)
w.panel.ax.set_ylim(-0.5, 0.25)
w.panel.canvas.draw()
app.processEvents()
_ev = type("Ev", (), {})()
_ev.inaxes = w.panel.ax
_ev.xdata = 340.0
w.panel._al_mover(_ev)
app.processEvents()
_png_del_lienzo(w.panel, os.path.join(salida, "panel_zoom_barras.png"))
print("zoom + ratón ->", w.statusBar().currentMessage(), flush=True)
w.panel.ajustar_a_datos()
app.processEvents()

w.panel.dibujar("spectrum", [_jwb("323BE947_spectrum.JWB", "spectrum")],
                ["Espectro 190-900"], titulo="Espectro — picos marcados con su λ")
app.processEvents()
_png_del_modelo(w.panel, os.path.join(salida, "panel_picos.png"))
print("espectro: picos etiquetados =", len(w.panel.ax.texts), flush=True)

w.panel.dibujar("photometrics",
                [_jwb("323BCBA4_photo_lowry.JWB", "photometrics"),
                 _jwb("323BE7BA_photo_sat.JWB", "photometrics")],
                ["Lowry", "Saturada (3.000)"], titulo="Fotometría — barras por réplica")
app.processEvents()
_png_del_modelo(w.panel, os.path.join(salida, "panel_fotometria.png"))
print("fotometría: barras =", len(w.panel.ax.patches), flush=True)

print("metodos en arbol:", len(w.items_de_metodos()), "| muestras metodo sel:", w.lista_muestras.count(), flush=True)
print("estado:", w.lbl_estado.text(), flush=True)

# --- Vista en vivo RS-232 Cuantificación (comparativa Fase 4) ---
w_quant = VentanaMaestro(tema="dark")
w_quant.resize(1280, 760)
w_quant.show()
w_quant.panel_serie.conectar("SIMULADOR")
ticket_quant = (
    "========================================\r\n"
    "MODO FOTOMETRíA.....\r\n"
    "ID INSTRUMENTO:             67XX V1.64.5\r\n"
    "NOMBRE DE USUARIO:               ALUMNOS\r\n"
    "MéTODO:               MéTODO POR DEFECTO\r\n"
    "ID DE LOTE:             LOTE POR DEFECTO\r\n"
    "LONGITUD DE ONDA:                584.0NM\r\n"
    "NúMERO DE ESTáND. USADOS:              5\r\n"
    "STD 1:    0.00      RESULTADO 1:    0.00\r\n"
    "STD 2:    1.00      RESULTADO 2:    0.10\r\n"
    "STD 3:    2.00      RESULTADO 3:    0.20\r\n"
    "STD 4:    3.00      RESULTADO 4:    0.30\r\n"
    "STD 5:    4.00      RESULTADO 5:    0.40\r\n"
    "AJUSTE DE CURVA:           INTERPOLACIóN\r\n"
    "úLTIMA CALIBRACIóN:    00:00:00 00/00/00\r\n"
    "========================================\r\n"
    "001  3.000ABS   30.00PPM 13:10:00\r\n"
)
w_quant.importar_stream_serie(ticket_quant, origen="COM3")
app.processEvents()
p_quant = os.path.join(salida, "ventana_cuantificacion.png")
w_quant.grab().save(p_quant)
print("guardado:", p_quant, flush=True)
w_quant.close()
print("OK smokescreen", flush=True)