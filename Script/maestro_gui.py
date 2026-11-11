#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Lanzador de la aplicación de escritorio del Programa Maestro — Jenway 6705.

Uso:
    python Script/maestro_gui.py [CARPETA] [--tema dark|light]

Sin CARPETA, la app abre y puedes cargar una tarjeta desde Archivo → Abrir tarjeta…
"""
import os
import sys

# Backend de gráficas estable desde el arranque: QtAgg (PySide6) funciona igual
# en el código fuente y en el ejecutable empaquetado; matplotlib auto-detecta
# de todas formas, pero sin variable fija un cambio de entorno lo desbarata.
os.environ.setdefault("MPLBACKEND", "QtAgg")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from ui.app import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())