# -*- coding: utf-8 -*-
"""Sello de compilación y red de seguridad contra errores silenciosos.

Resuelve dos problemas reales encontrados al probar la aplicación:

1. **No saber qué compilación se está ejecutando.**  Al tocar varios archivos
   seguidos es fácil dejar abierta una instancia anterior y creer que el
   programa está roto.  :func:`sello` devuelve la fecha del código MÁS RECIENTE
   de ``ui/`` y ``jenway67/``, que es justo lo que distingue "tengo código viejo
   cargado en memoria" de "mi código nuevo en disco no hace esto".

2. **Fallar en silencio.**  Si una excepción revienta dentro de un manejador de
   Qt, la ventana se queda a medias (gráfico vacío, controles inertes) sin decir
   nada.  :func:`instalar_red` engancha ``sys.excepthook`` para que TODO error
   acabe en un archivo de registro y en la barra de estado.
"""
from __future__ import annotations

import datetime
import os
import sys
import traceback

#: Subcarpetas de las que se vigila la fecha (el código propio de la app).
VIGILADAS = ("ui", "jenway67")

NOMBRE_REGISTRO = "maestro_errores.log"


def carpeta_raiz() -> str:
    """Carpeta del proyecto (la que contiene ``ui/`` y ``jenway67/``).

    En el ejecutable empaquetado (PyInstaller) no existe árbol fuente: el sello
    se toma del propio .exe y el registro se escribe junto a él (portable).
    """
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def mtime_mas_reciente() -> float:
    """Momento del último cambio en el código de la aplicación (0 si no hay)."""
    if getattr(sys, "frozen", False):
        try:
            return os.path.getmtime(sys.executable)
        except OSError:
            return 0.0
    ultimo = 0.0
    raiz = carpeta_raiz()
    for subcarpeta in VIGILADAS:
        ruta = os.path.join(raiz, subcarpeta)
        if not os.path.isdir(ruta):
            continue
        for nombre in os.listdir(ruta):
            if nombre.endswith(".py"):
                try:
                    ultimo = max(ultimo, os.path.getmtime(os.path.join(ruta, nombre)))
                except OSError:
                    pass
    return ultimo


def sello() -> str:
    """Texto corto que identifica la compilación en disco (dd/mm/aaaa hh:mm)."""
    momento = mtime_mas_reciente()
    if not momento:
        return "sin fecha"
    return datetime.datetime.fromtimestamp(momento).strftime("%d/%m/%Y %H:%M")


def ruta_registro() -> str:
    return os.path.join(carpeta_raiz(), NOMBRE_REGISTRO)


def registrar(texto: str) -> None:
    """Añade una línea fechada al registro.  Nunca lanza (no puede tumbar nada)."""
    try:
        with open(ruta_registro(), "a", encoding="utf-8") as manejador:
            manejador.write("[%s] %s\n"
                            % (datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                               texto))
    except Exception:
        pass


def instalar_red(avisar=None) -> None:
    """Engancha las excepciones no controladas.

    ``avisar(texto)`` recibe cada error inesperado para mostrarlo donde se vea
    (p. ej. la barra de estado).  El detalle completo va siempre al registro.
    """
    def _manejador(tipo, valor, rastro):
        detalle = "".join(traceback.format_exception(tipo, valor, rastro))
        registrar(detalle)
        if avisar is not None:
            try:
                avisar("Error inesperado: %s: %s   (detalle en %s)"
                       % (tipo.__name__, valor, os.path.basename(ruta_registro())))
            except Exception:
                pass

    sys.excepthook = _manejador
    registrar("=== Arranque · código del %s ===" % sello())


def resumen() -> str:
    """Texto para el diálogo "Acerca de"."""
    return ("Compilación en disco: %s\n"
            "Registro de errores: %s" % (sello(), ruta_registro()))
