#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Mini-visor de reportes .TXT del Jenway 6705.

Uso:
    python leer_reporte.py "ruta/al/archivo.TXT"

Imprime la estructura parseada (modo, metadatos y datos por modo).
Requiere estar en la carpeta maestro/ (importa jenway67).
"""
import sys, os, json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from jenway67.parser_txt import parsear_reporte


def resumir(reg):
    c = reg.cuerpo
    if reg.modo == "spectrum":
        pts = c.get("puntos", [])
        extra = f"{len(pts)} puntos ({pts[0] if pts else '?'} … {pts[-1] if pts else '?'})"
    elif reg.modo == "photometrics":
        extra = f"filas={c.get('filas')}"
    elif reg.modo == "multi":
        extra = f"celdas={len(c.get('celdas', []))} | calc={c.get('calculos')}"
    elif reg.modo == "kinetics":
        s = c.get("serie", [])
        extra = f"serie {len(s)} pts, 1º={s[0] if s else '?'}, último={s[-1] if s else '?'}"
    elif reg.modo == "quantitation":
        extra = f"estándares={reg.meta.get('__estandares__')} | muestras={c.get('muestras')}"
    else:
        extra = f"cuerpo={str(c)[:80]}"
    return f"{reg.modo.upper():12s} | {reg.nombre_metodo or '?':20s} | {extra}"


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    for ruta in sys.argv[1:]:
        print(f"\n=== {os.path.basename(ruta)} ===")
        try:
            regs = parsear_reporte(ruta)
        except Exception as e:  # pragma: no cover
            print(f"  ERROR: {e}")
            continue
        if not regs:
            print("  (sin registros parseables)")
            continue
        for reg in regs:
            print("  •", resumir(reg))
            # metadatos clave
            claves = ["ID instrumento", "Método", "Longitud de onda",
                      "WRango de longitud de onda", "Ajuste de curva",
                      "Intervalo de gráfico", "Mínimo eje Y", "Máximo eje Y"]
            for k in claves:
                if k in reg.meta:
                    print(f"      {k}: {reg.meta[k]}")


if __name__ == "__main__":
    main()