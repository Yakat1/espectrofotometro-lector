#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Genera el informe (Excel + figuras) para una carpeta de tarjeta Jenway 6705.

Uso:
    python analizar.py CARPETA [CARPETA_SALIDA]

Genera:
    <SALIDA>/Xlsx/informe.xlsx     (hoja Resumen + una por método)
    <SALIDA>/Figures/*.png,*.svg   (espectros, cinéticas, calibraciones, boxplots)
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from jenway67.reader import leer_carpeta
from jenway67.informe import analizar_carpeta


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    tarjeta = leer_carpeta(sys.argv[1])
    salida = sys.argv[2] if len(sys.argv) > 2 else os.path.join(sys.argv[1], "_informe")
    print(f"Tarjeta: {sys.argv[1]}  ({len(tarjeta.metodos)} métodos)")
    res = analizar_carpeta(tarjeta, salida)
    print(f"\nExcel : {res['xlsx']}")
    print(f"Figuras: {len(res['figuras'])}")
    for m in res["metodos"]:
        estado = m.get("estado", "?")
        print(f"  [{m['modo']:12s}] {m['nombre']:22s} {estado}")
    print("\nHecho.")


if __name__ == "__main__":
    main()