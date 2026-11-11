# -*- coding: utf-8 -*-
"""Punto de entrada de la aplicación de escritorio del Programa Maestro."""
from __future__ import annotations

import argparse
import sys

from PySide6.QtWidgets import QApplication

from . import diagnostico, estilos
from .ventana import VentanaMaestro


def main(argv=None) -> int:
    desc = "Programa Maestro — Jenway 6705 (lector/analizador propio)"
    p = argparse.ArgumentParser(description=desc)
    p.add_argument("carpeta", nargs="?", help="carpeta de tarjeta copiada (.JWB/.JWX/.JWU)")
    p.add_argument("--tema", default="dark", choices=["dark", "light"],
                   help="tema inicial (por defecto: dark)")
    args = p.parse_args(argv)

    # Red de errores sin destinatario todavía: así un fallo al CONSTRUIR la
    # ventana también queda registrado en vez de morir en silencio.
    diagnostico.instalar_red()

    app = QApplication(sys.argv[:1])
    app.setApplicationName("Programa Maestro 6705")
    app.setStyleSheet(estilos.qss(args.tema))

    w = VentanaMaestro(carpeta=args.carpeta, tema=args.tema)

    # Ya con ventana: los errores inesperados se ven en su barra de estado.
    diagnostico.instalar_red(avisar=w._actualizar_status)

    # El sello de compilación en el título: sirve para saber si lo que se está
    # ejecutando es el código que hay en disco o una instancia anterior.
    w.setWindowTitle("Programa Maestro — Jenway 6705   ·   código del %s"
                     % diagnostico.sello())

    w.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())