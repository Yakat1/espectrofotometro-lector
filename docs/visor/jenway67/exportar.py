# -*- coding: utf-8 -*-
"""Exportación a CSV de los .JWB decodificados (una tabla por modo)."""
from __future__ import annotations

import csv
import math
import os
import re
from typing import List, Tuple

from .models import Tarjeta
from .utilidades import redondear_display


def _f(v) -> str:
    """Formatea un valor NORMAL: longitud de onda, %T o concentración.

    A propósito NO aplica el recorte de saturación: el instrumento recorta sus
    LECTURAS de absorbancia en 3.000, pero una longitud de onda de 600 nm, una
    transmitancia del 99 % o una concentración de 10 mM no son absorbancias y no
    deben recortarse.  (Hacerlo mostraba "3.000" en la columna de longitud de
    onda de multi-longitud y de fotometría, y en las concentraciones.)
    """
    if v is None:
        return ""
    if isinstance(v, float):
        if math.isnan(v):
            return ""
        return f"{v:.3f}"
    return str(v)


def _abs(v) -> str:
    """Formatea una ABSORBANCIA: 3 decimales y recorte en 3.000.

    Es lo que hace el propio equipo con sus lecturas, así que la tabla cuadra
    con el reporte .TXT.  Solo para absorbancias (y las celdas de
    multi-longitud), nunca para longitudes de onda, transmitancias,
    concentraciones ni cocientes.
    """
    if v is None:
        return ""
    if isinstance(v, float):
        if math.isnan(v):
            return ""
        if math.isinf(v):
            return "Saturado(>3.0)"
        return f"{redondear_display(v):.3f}"
    return str(v)


def filas_para(modo: str, r: dict) -> Tuple[List[str], List[List[str]]]:
    """Devuelve (cabecera, filas) para un resultado decodificado de `.JWB`."""
    if modo == "spectrum":
        return (["Longitud_onda_nm", "Transmitancia_pct", "Absorbancia"],
                [[f"{wl:.1f}", _f(T), _abs(A)] for wl, T, A in r["puntos"]])
    if modo == "photometrics":
        return (["Columna", "Valor"],
                [["Longitud_onda_nm", _f(r["wl"])],
                 ["Transmitancia_pct", _f(r["t"])],
                 ["Absorbancia", _abs(r["abs"])]])
    if modo == "multi":
        filas = [["Celda", "Longitud_onda_nm", "Etiqueta", "Absorbancia"]]
        for c in r["celdas"]:
            filas.append([c["etiqueta"], _f(c["wl"]), c["etiqueta"], _abs(c["abs"])])
        # A1/A2 es un cociente y A1-A2 una diferencia: no se recortan.
        filas.append(["A1/A2", "", "", _f(r["A1/A2"])])
        filas.append(["A1-A2", "", "", _f(r["A1-A2"])])
        return (filas[0], filas[1:])
    if modo == "kinetics":
        serie = r["serie"]
        tiempos = r.get("tiempos")
        usa = bool(tiempos) and len(tiempos) == len(serie)
        filas = [["%g" % float(tiempos[k] if usa else _i), _f(T), _abs(A)]
                 for k, (_i, T, A) in enumerate(serie)]
        return (["Tiempo_s", "Transmitancia_pct", "Absorbancia"], filas)
    if modo == "quantitation":
        filas = [["Tipo", "Concentracion", "Absorbancia"]]
        for c, a in r["estandares"]:
            filas.append(["Estandar", _f(c), _abs(a)])
        conc_m = r.get("conc_muestra")
        filas.append(["Muestra", _f(conc_m) if conc_m is not None else "", _abs(r["abs_muestra"])])
        return (filas[0], filas[1:])
    raise ValueError(f"modo sin export definido: {modo}")


def sanitizar(nombre: str) -> str:
    """Nombre de archivo seguro (quita caracteres no válidos en Windows)."""
    return re.sub(r'[\\/:*?"<>| ]+', "_", nombre)


def exportar_carpeta(tarjeta: Tarjeta, salida_dir: str) -> List[str]:
    """Escribe un CSV por decodificable y un índice general. Devuelve rutas."""
    os.makedirs(salida_dir, exist_ok=True)
    muestras_dir = os.path.join(salida_dir, "muestras")
    os.makedirs(muestras_dir, exist_ok=True)
    escritos = []

    # índice de métodos
    indice = os.path.join(salida_dir, "_indice_metodos.csv")
    with open(indice, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["modo", "nombre", "usuario", "fecha", "filename", "n_muestras"])
        for m in sorted(tarjeta.metodos, key=lambda x: x.fecha):
            w.writerow([m.modo, m.nombre, m.usuario, m.fecha, m.filename, len(m.muestras)])
    escritos.append(indice)

    # CSVs de decodificables (archivos físicos .JWB y lecturas virtuales en vivo)
    from .reader import decodificar_archivo as _dec_arch

    for m in tarjeta.metodos:
        locs = sorted({mm.loc for mm in m.muestras if mm.loc} | ({m.filename} if m.filename else set()))
        for loc in locs:
            try:
                modo, r = _dec_arch(tarjeta, loc, m.modo)
            except Exception:
                continue
            base_loc = sanitizar(os.path.splitext(os.path.basename(loc))[0] or "muestra")
            nombre = f"{modo}_{sanitizar(m.nombre)}_{base_loc}"
            out = os.path.join(muestras_dir, nombre + ".csv")
            cab, filas = filas_para(modo, r)
            with open(out, "w", newline="", encoding="utf-8") as fh:
                wr = csv.writer(fh)
                wr.writerow(cab)
                wr.writerows(filas)
            escritos.append(out)
    return escritos