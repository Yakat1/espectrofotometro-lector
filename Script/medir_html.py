# -*- coding: utf-8 -*-
"""Mide un HTML con SVG: ¿algun texto se sale de su caja o del lienzo? ¿se
solapa con otro?  Uso:  py -3.12 medir_html.py <archivo.html> [ancho]

Sin .show() la vista no hace layout y todo mide 0, asi que se muestra.
"""
import os
import sys

os.environ.setdefault("QTWEBENGINE_CHROMIUM_FLAGS", "--disable-gpu --no-sandbox")
os.environ.setdefault("QT_QPA_FONTDIR", r"C:\Windows\Fonts")

from PySide6.QtCore import QTimer, QUrl  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402
from PySide6.QtWebEngineWidgets import QWebEngineView  # noqa: E402

entrada = sys.argv[1]
ancho = int(sys.argv[2]) if len(sys.argv) > 2 else 900

JS = r"""
(function(){
  var svg = document.querySelector('svg');
  if(!svg) return 'NO HAY SVG';
  var VB = svg.viewBox.baseVal;
  var rects = [].slice.call(svg.querySelectorAll('rect')).map(function(r){
    return {x:r.x.baseVal.value, y:r.y.baseVal.value,
            w:r.width.baseVal.value, h:r.height.baseVal.value,
            id:(r.getAttribute('class')||'caja')+'@y'+Math.round(r.y.baseVal.value)};
  });
  var textos = [].slice.call(svg.querySelectorAll('text')).map(function(t){
    var b = t.getBBox();
    return {b:b, txt:t.textContent.trim(), x:b.x, y:b.y, w:b.width, h:b.height};
  });
  var problemas = [];
  textos.forEach(function(t){
    var p = [];
    if (t.x + t.w > VB.width - 4) p.push('SALE-DEL-LIENZO(derecha)');
    if (t.x < 4) p.push('SALE-DEL-LIENZO(izquierda)');
    var dueno = null;
    rects.forEach(function(r){
      if (t.x >= r.x - 1 && t.x <= r.x + r.w && t.y >= r.y - 1 && t.y <= r.y + r.h){
        if (!dueno || r.w*r.h < dueno.w*dueno.h) dueno = r;
      }
    });
    if (dueno){
      if (t.x + t.w > dueno.x + dueno.w - 3) p.push('SALE-DE-LA-CAJA ' + dueno.id);
      if (t.y + t.h > dueno.y + dueno.h - 1) p.push('TOCA-EL-BORDE-DE-ABAJO ' + dueno.id);
    } else if (t.y > VB.height - 30) {
      p.push('PIE-MUY-ABAJO');
    }
    if (p.length) problemas.push(p.join(',') + ' :: "' + t.txt.substring(0,56) + '" [x=' + Math.round(t.x) + ' w=' + Math.round(t.w) + ']');
  });
  // Solapes entre textos
  for (var i=0;i<textos.length;i++){
    for (var j=i+1;j<textos.length;j++){
      var a=textos[i].b, b=textos[j].b;
      var ancho = Math.min(a.x+a.width,b.x+b.width) - Math.max(a.x,b.x);
      var alto  = Math.min(a.y+a.height,b.y+b.height) - Math.max(a.y,b.y);
      if (ancho > 2 && alto > 3){
        problemas.push('SOLAPE :: "' + textos[i].txt.substring(0,26) + '" <> "' + textos[j].txt.substring(0,26) + '"');
      }
    }
  }
  // Margen real usado en la caja mas ancha (para saber si sobra espacio)
  var peor = 0, quien = '';
  textos.forEach(function(t){
    if (t.x + t.w > peor){ peor = t.x + t.w; quien = t.txt.substring(0,40); }
  });
  var fin = 'LIMITE-DERECHO-USADO: ' + Math.round(peor) + '/760  ("' + quien + '")';
  return problemas.length ? problemas.join('\n') + '\n' + fin : 'TODO DENTRO\n' + fin;
})()
"""

app = QApplication(sys.argv)
vista = QWebEngineView()
vista.resize(ancho, 1000)
vista.show()  # imprescindible: sin mostrar, no hay layout
vista.load(QUrl.fromLocalFile(os.path.abspath(entrada)))


def al_cargar(ok):
    if not ok:
        print("CARGA FALLIDA")
        app.quit()
        return
    QTimer.singleShot(900, medir)


def medir():
    vista.page().runJavaScript(
        "document.documentElement.scrollWidth;", lambda _w: QTimer.singleShot(300, medir2)
    )


def medir2():
    vista.page().runJavaScript(JS, reportar)


def reportar(resultado):
    print(resultado)
    app.quit()


vista.loadFinished.connect(al_cargar)
QTimer.singleShot(25000, app.quit)
app.exec()
