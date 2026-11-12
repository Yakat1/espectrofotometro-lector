# -*- coding: utf-8 -*-
"""Exportador al formato universal JCAMP-DX (.jdx / .dx) versión 4.24 (IUPAC).

Permite abrir espectros y cinéticas del Jenway 6705 directamente en Spectragryph,
OMNIC, Origin, ChemStation o cualquier software de espectroscopía estándar.
"""
from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Sequence

from .utilidades import clamp_saturacion


def generar_jcamp_dx(
    modo: str,
    resultado: Dict,
    titulo: str = "Espectro Jenway 6705",
    usuario: str = "",
    fecha: str = "",
) -> str:
    """Devuelve el texto JCAMP-DX (XYDATA=(X,Y)) de un espectro o cinética."""
    if modo == "spectrum":
        pts = resultado.get("puntos") or []
        pares = [(float(p[0]), float(clamp_saturacion(p[2]))) for p in pts if p[2] is not None]
        tipo_dato = "UV/VIS SPECTRUM"
        unidades_x = "NANOMETERS"
        unidades_y = "ABSORBANCE"
    elif modo == "kinetics":
        serie = resultado.get("serie") or []
        tiempos = resultado.get("tiempos") or [float(s[0]) for s in serie]
        pares = [
            (float(tiempos[i] if i < len(tiempos) else s[0]), float(clamp_saturacion(s[2])))
            for i, s in enumerate(serie)
            if s[2] is not None
        ]
        tipo_dato = "KINETICS"
        unidades_x = "SECONDS"
        unidades_y = "ABSORBANCE"
    else:
        raise ValueError(f"JCAMP-DX requiere un espectro o cinética (modo recibido: {modo!r}).")

    if not pares:
        raise ValueError("No hay puntos numéricos para exportar a JCAMP-DX.")

    xs = [x for x, _y in pares]
    ys = [y for _x, y in pares]
    deltax = (xs[-1] - xs[0]) / (len(xs) - 1) if len(xs) > 1 else 0.0
    fecha_iso = datetime.now().strftime("%Y/%m/%d")

    lineas: List[str] = [
        f"##TITLE= {titulo}",
        "##JCAMP-DX= 4.24",
        f"##DATA TYPE= {tipo_dato}",
        "##ORIGIN= Programa Maestro - Jenway 6705",
        f"##OWNER= {usuario or 'Laboratorio'}",
        "##SPECTROMETER/DATA SYSTEM= Jenway 6705 UV/Vis Spectrophotometer",
        f"##DATE= {fecha or fecha_iso}",
        f"##XUNITS= {unidades_x}",
        f"##YUNITS= {unidades_y}",
        f"##FIRSTX= {xs[0]:.4f}",
        f"##LASTX= {xs[-1]:.4f}",
        f"##MINX= {min(xs):.4f}",
        f"##MAXX= {max(xs):.4f}",
        f"##MINY= {min(ys):.6f}",
        f"##MAXY= {max(ys):.6f}",
        f"##DELTAX= {deltax:.4f}",
        "##XFACTOR= 1.0",
        "##YFACTOR= 1.0",
        f"##FIRSTY= {ys[0]:.6f}",
        f"##NPOINTS= {len(pares)}",
        "##XYDATA= (X,Y)",
    ]
    for x, y in pares:
        lineas.append(f"{x:.2f}, {y:.6f}")
    lineas.append("##END=")
    return "\n".join(lineas) + "\n"


def exportar_jcamp_dx(
    ruta: str,
    modo: str,
    resultado: Dict,
    titulo: str = "Espectro Jenway 6705",
    usuario: str = "",
    fecha: str = "",
) -> int:
    """Escribe el archivo ``.jdx`` en disco y devuelve el número de puntos exportados."""
    contenido = generar_jcamp_dx(modo, resultado, titulo=titulo, usuario=usuario, fecha=fecha)
    with open(ruta, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(contenido)
    pts = resultado.get("puntos") if modo == "spectrum" else resultado.get("serie")
    return len(pts or [])
