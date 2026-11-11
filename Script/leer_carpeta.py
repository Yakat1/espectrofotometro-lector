#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CLI del Programa Maestro — Jenway 6705. Lee una carpeta de tarjeta copiada.

Uso:
    python leer_carpeta.py CARPETA listar
    python leer_carpeta.py CARPETA ver [loc]
    python leer_carpeta.py CARPETA exportar [CARPETA_SALIDA]

  listar    : lista métodos (modo, nombre, usuario, fecha, n muestras)
  ver       : decodifica y resume todos los .JWB de la carpeta (o uno por loc)
  exportar  : escribe un CSV por decodificable + índice general
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from jenway67.reader import leer_carpeta, decodificar_archivo, modo_de_archivo
from jenway67.exportar import exportar_carpeta
from jenway67.utilidades import clamp_saturacion


def _abs_mostrable(v):
    """Absorbancia como la muestra el 6705: clampada a 3.000 en saturación."""
    if v is None or (isinstance(v, float) and v != v):  # None o nan
        return "?"
    return f"{clamp_saturacion(v):.3f}"


def _resumen(modo, r):
    if modo == "spectrum":
        nsat = sum(1 for _, _, a in r["puntos"] if a == float("inf"))
        return f"espectro {r['wl0']:.1f}..{r['wl1']:.1f}nm {len(r['puntos'])}pts ({nsat} sat)"
    if modo == "multi":
        return f"λ={r['wls']} A1/A2={r['A1/A2']:.3f} A1-A2={r['A1-A2']:.3f}"
    if modo == "photometrics":
        return f"λ={r['wl']:.1f} Abs={_abs_mostrable(r.get('abs'))}"
    if modo == "kinetics":
        s = r["serie"]
        if not s:
            extra = f"{r['saturados']} sat" if r.get("saturados") else "sin lecturas"
            return f"λ={r['wl']:.1f} 0pts (sin lecturas; {extra})"
        return f"λ={r['wl']:.1f} {r['n']}pts 1º={s[0][2]:.3f} último={s[-1][2]:.3f}"
    if modo == "quantitation":
        return f"λ={r['wl']:.1f} muestra Abs={_abs_mostrable(r.get('abs_muestra'))}"
    return str(r)


def cmd_listar(tarjeta):
    print(f"{'MODO':12s} {'MÉTODO':22s} {'USUARIO':10s} {'FECHA':16s} #MUES")
    for m in sorted(tarjeta.metodos, key=lambda x: x.fecha):
        print(f"{m.modo:12s} {m.nombre:22s} {m.usuario:10s} {m.fecha:16s} {len(m.muestras)}")


def cmd_ver(tarjeta, loc=None):
    objetivos = []
    for m in tarjeta.metodos:
        locs = sorted({mm.loc for mm in m.muestras if mm.loc} | {m.filename})
        for l in locs:
            if loc is None or l.lower() == loc.lower():
                objetivos.append((l, m.modo, m.nombre))
    for l, modo, nombre in objetivos:
        try:
            modo2, r = decodificar_archivo(tarjeta, l, modo)
            print(f"• {l}  [{modo2}] {nombre}  ->  {_resumen(modo2, r)}")
        except Exception as e:
            print(f"• {l}  ERROR: {e}")


def cmd_exportar(tarjeta, salida):
    escritos = exportar_carpeta(tarjeta, salida)
    print(f"Exportados {len(escritos)} archivos a:\n  {salida}")
    for r in escritos:
        print("  +", os.path.basename(r))


def main():
    if len(sys.argv) < 3:
        print(__doc__); sys.exit(1)
    carpeta = sys.argv[1]
    comando = sys.argv[2]
    tarjeta = leer_carpeta(carpeta)
    print(f"· Tarjeta: {carpeta}")
    print(f"· Usuarios: {[u.nombre for u in tarjeta.usuarios] or '(ninguno)'}")
    print(f"· Métodos: {len(tarjeta.metodos)}\n")
    if comando == "listar":
        cmd_listar(tarjeta)
    elif comando == "ver":
        cmd_ver(tarjeta, sys.argv[3] if len(sys.argv) > 3 else None)
    elif comando == "exportar":
        cmd_exportar(tarjeta, sys.argv[3] if len(sys.argv) > 3 else os.path.join(carpeta, "_exportado"))
    else:
        print(f"comando desconocido: {comando}"); print(__doc__); sys.exit(1)


if __name__ == "__main__":
    main()