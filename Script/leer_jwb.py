#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Visor de archivos .JWB del Jenway 6705 (los 5 modos).

Uso:
    python leer_jwb.py "ruta/al/archivo.JWB" [modo]
    (modo opcional: photometrics|spectrum|multi|kinetics|quantitation;
     si se omite, se intenta detectar automáticamente)

Requiere estar en la carpeta maestro/ (importa jenway67).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from jenway67.parser_jwb import decodificar


def resumir(r):
    m = r["modo"]
    if m == "spectrum":
        pts = r["puntos"]
        nsat = sum(1 for _, _, a in pts if a == float("inf"))
        return (f"espectro {r['wl0']:.1f}..{r['wl1']:.1f} nm, {r['n']} pts "
                f"({nsat} saturados), 1º=λ{r['puntos'][0][0]} Abs {r['puntos'][0][2]:.3f}")
    if m == "multi":
        return (f"multi λ={r['wls']} | celdas={[round(c['abs'],3) for c in r['celdas']]} "
                f"| A1/A2={r['A1/A2']:.3f} A1-A2={r['A1-A2']:.3f}")
    if m == "photometrics":
        return f"fotometría λ={r['wl']:.1f} | %T={r['t']:.3f} | Abs={r['abs'] if not float('inf')==r['abs'] else 'SATURADO(3.0)'}"
    if m == "kinetics":
        vals = [round(_, 3) for _, _, _ in r["serie"]]
        return f"cinética λ={r['wl']:.1f} | {r['n']} pts | 1º Abs {vals[0] if vals else '?'} | último {vals[-1] if vals else '?'}"
    if m == "quantitation":
        return (f"cuantif. λ={r['wl']:.1f} | estándares {[(c, round(a,2)) for c, a in r['estandares']]} "
                f"| muestra Abs {round(r['abs_muestra'],3)}")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    ruta = sys.argv[1]
    modo = sys.argv[2] if len(sys.argv) > 2 else None
    with open(ruta, "rb") as fh:
        datos = fh.read()
    modo_res, r = decodificar(datos, modo)
    print(f"=== {os.path.basename(ruta)}  (modo={modo_res}) ===")
    print("  ", resumir(r))


if __name__ == "__main__":
    main()