# -*- coding: utf-8 -*-
"""Renderiza un HTML local a PNG con QtWebEngine (sin Playwright).

Uso:  py -3.12 render_html.py <entrada.html> <salida.png> [ancho]
"""
import os
import sys

os.environ.setdefault("QTWEBENGINE_CHROMIUM_FLAGS", "--disable-gpu --no-sandbox")
os.environ.setdefault("QT_QPA_FONTDIR", r"C:\Windows\Fonts")

from PySide6.QtCore import QTimer, QUrl  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402
from PySide6.QtWebEngineWidgets import QWebEngineView  # noqa: E402

entrada, salida = sys.argv[1], sys.argv[2]
ancho = int(sys.argv[3]) if len(sys.argv) > 3 else 900
fondo = sys.argv[4] if len(sys.argv) > 4 else "#101418"

app = QApplication(sys.argv)
vista = QWebEngineView()
vista.setWindowTitle("render_html (temporal)")
vista.resize(ancho, 900)
# Sin show() la vista no hace layout y todo mide 0: hay que mostrarla.
vista.show()
vista.load(QUrl.fromLocalFile(os.path.abspath(entrada)))

estado = {}


def al_cargar(ok):
    if not ok:
        print("CARGA FALLIDA")
        app.quit()
        return
    QTimer.singleShot(600, medir)


def medir():
    pagina = vista.page()
    pagina.runJavaScript(
        "document.body.style.background='%s'; document.body.style.margin='18px';"
        " (function(){"
        "  var s=document.querySelector('svg');"
        "  var d=document.body.getBoundingClientRect();"
        "  var e=document.documentElement;"
        "  console.log('DIAG body='+d.width+'x'+d.height+' svg='+(s?s.getBoundingClientRect().width+'x'+s.getBoundingClientRect().height:'SIN-SVG')"
        "    +' scroll='+e.scrollWidth+'x'+e.scrollHeight+' viewBox='+(s?s.getAttribute('viewBox'):'-'));"
        "  return Math.ceil(Math.max(d.height, e.scrollHeight)) + 36;"
        " })()" % fondo,
        aplicar,
    )


def aplicar(alto):
    alto = int(alto or 800)
    vista.resize(ancho, alto)
    estado["alto"] = alto
    QTimer.singleShot(1200, capturar)


def capturar():
    vista.grab().save(salida)
    print("OK %s  %dx%d" % (salida, ancho, estado.get("alto", 0)))
    app.quit()


vista.loadFinished.connect(al_cargar)
QTimer.singleShot(20000, app.quit)  # red de seguridad
app.exec()
