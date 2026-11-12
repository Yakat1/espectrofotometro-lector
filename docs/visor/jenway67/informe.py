# -*- coding: utf-8 -*-
"""Orquestador de informe: decodifica una tarjeta, analiza, dibuja y exporta
Excel + figuras en subcarpetas Xlsx/ y Figures/."""
from __future__ import annotations

import math
import os
from typing import Dict, List, Optional, Tuple

import numpy as np

from . import analisis as an
from . import graficos as gr
from .exportar import filas_para, sanitizar
from .excel import crear_informe
from .models import Tarjeta
from .reader import decodificar_archivo


def _decodificar_muestra(tarjeta, loc, modo):
    try:
        modo_r, r = decodificar_archivo(tarjeta, loc, modo)
        return modo_r, r
    except Exception:
        return None, None


def _agrupar(tarjeta: Tarjeta):
    """(metodo, [(muestra, modo, r), ...]) por método decodificable."""
    grupos = []
    for m in sorted(tarjeta.metodos, key=lambda x: x.fecha):
        dec = []
        for s in m.muestras:
            modo, r = _decodificar_muestra(tarjeta, s.loc, m.modo)
            if r is not None:
                dec.append((s, modo, r))
        if not dec:  # el propio método puede ser el resultado
            self_modo, self_r = _decodificar_muestra(tarjeta, m.filename, m.modo)
            if self_r is not None:
                dec.append((None, self_modo, self_r))
        grupos.append((m, dec))
    return grupos


# --------------------------------------------------------------------------
# agregación de métricas (sobre todas las muestras del método)
# --------------------------------------------------------------------------

def _numeros(valores) -> List[float]:
    """Sólo valores finitos (descarta None, nan e inf de saturación)."""
    return [float(x) for x in valores
            if isinstance(x, (int, float)) and math.isfinite(x)]


def _media(valores) -> Optional[float]:
    v = _numeros(valores)
    return sum(v) / len(v) if v else None


def _desv(valores) -> Optional[float]:
    """Desviación estándar muestral (ddof=1) si hay 2 o más valores."""
    v = _numeros(valores)
    return float(np.std(v, ddof=1)) if len(v) > 1 else None


def _extremo(valores, fn) -> Optional[float]:
    v = _numeros(valores)
    return fn(v) if v else None


def _red(valor, dec: int = 4):
    return round(valor, dec) if valor is not None else None


def _analisis_por_modo(modo: str, dec: List[Tuple]) -> Dict:
    """Métricas del método agregadas sobre TODAS sus muestras decodificadas
    (no sólo la primera). Con una sola muestra el resultado coincide con el
    valor de esa muestra, de modo que la vista de una muestra no cambia."""
    rs = [r for _, _, r in dec]
    n = len(rs)
    if not n:
        return {}

    if modo == "spectrum":
        detalles: List[str] = []
        areas: List[float] = []
        fwhms: List[float] = []
        picos_total = 0
        vals_abs: List[float] = []
        vals_d1: List[float] = []
        for r in rs:
            puntos = r["puntos"]
            pk = an.picos(puntos)
            picos_total += len(pk)
            if pk:
                detalles.append("; ".join(f"{p['wl']:g}nm({p['tipo']})" for p in pk[:8]))
                max_pks = [p for p in pk if p.get("tipo") == "max" and p.get("fwhm") is not None]
                if max_pks:
                    principal = max(max_pks, key=lambda p: float(p.get("abs", -1e9)))
                    fwhms.append(float(principal["fwhm"]))
            areas.append(an.area_bajo_curva(puntos))
            vals_abs += _numeros([p[2] for p in puntos])
            vals_d1 += _numeros([d for _, d in an.derivada(puntos, 1)])
        return {"n_muestras": n,
                "n_puntos": len(rs[0]["puntos"]),
                "picos": picos_total,
                "picos_detalle": " | ".join(detalles),
                "fwhm_nm": _red(_media(fwhms), 2),
                "area_total": _red(sum(_numeros(areas))),
                "area_media": _red(_media(areas)),
                "abs_max": _red(max(vals_abs) if vals_abs else None),
                "d1_max": _red(max(vals_d1) if vals_d1 else None)}

    if modo == "kinetics":
        cs = [an.cinetica(r["serie"]) for r in rs]
        rates = [c.get("rate") for c in cs]
        return {"n_muestras": n,
                "n": cs[0].get("n"),
                "rate": _red(_media(rates), 6),
                "rate_sd": _red(_desv(rates), 6),
                "min": _red(_extremo([c.get("min") for c in cs], min)),
                "max": _red(_extremo([c.get("max") for c in cs], max)),
                "delta": _red(_media([c.get("delta_total") for c in cs]))}

    if modo == "quantitation":
        qs = [an.cuantificacion(r["estandares"], r["abs_muestra"]) for r in rs]
        interps = [q.get("conc_interp") for q in qs]
        return {"n_muestras": n,
                "conc_interp": _red(_media(interps)),
                "conc_interp_min": _red(_extremo(interps, min)),
                "conc_interp_max": _red(_extremo(interps, max)),
                "lineal_r2": _red(_media([q.get("lineal_r2") for q in qs])),
                "lineal_pred": _red(_media([q.get("lineal_pred") for q in qs]))}

    if modo == "photometrics":
        f = an.fotometria(rs)
        return {"n_muestras": n,
                "n": f.get("n"),
                "media": _red(f.get("media")),
                "min": _red(f.get("min")),
                "max": _red(f.get("max")),
                "saturados": f.get("saturados")}

    if modo == "multi":
        cs = [an.multi_calculos(r["celdas"]) for r in rs]
        return {"n_muestras": n,
                "A1": _red(_media([c.get("A1") for c in cs])),
                "A2": _red(_media([c.get("A2") for c in cs])),
                "A1/A2": _red(_media([c.get("A1_A2_ratio") for c in cs])),
                "A1-A2": _red(_media([c.get("A1_A2_diff") for c in cs]))}

    return {}


def _figura_por_modo(modo, dec, m, fig_dir) -> Optional[str]:
    rs = [r for _, _, r in dec]
    uniq = (m.filename or "0")[:8]
    base = os.path.join(fig_dir, sanitizar(f"{modo}_{m.nombre}_{uniq}"))
    try:
        if modo == "spectrum":
            return gr.graficar_espectro(rs, base, titulo=f"{m.nombre} — espectros",
                                        etiquetas=[f"#{i+1}" for i in range(len(rs))])
        if modo == "kinetics":
            return gr.graficar_cinetica(rs, base, titulo=f"{m.nombre} — cinética",
                                        etiquetas=[f"#{i+1}" for i in range(len(rs))])
        if modo == "quantitation":
            r0 = rs[0]
            # La muestra va en (Absorbancia, Concentración INTERPOLADA); antes se
            # le pasaba su propia absorbancia y quedaba dibujada en (A, A).
            c_interp = an.cuantificacion(r0["estandares"], r0["abs_muestra"]).get("conc_interp")
            return gr.graficar_calibracion(r0["estandares"], r0["abs_muestra"], base,
                                           titulo=f"{m.nombre} — calibración",
                                           conc_muestra=c_interp)
        if modo == "photometrics":
            return gr.graficar_boxplot_fotometria(
                {f"#{i+1}": [rs[i].get("abs")] for i in range(len(rs))}, base,
                titulo=f"{m.nombre}")
        if modo == "multi":
            return gr.graficar_multi(rs, base, titulo=f"{m.nombre} — multi-longitud",
                                     etiquetas=[f"#{i+1}" for i in range(len(rs))])
    except Exception:
        return None
    return None  # otros modos: sin figura


def _tabla_por_modo(modo, dec) -> Dict:
    """Tabla combinada (con columna Muestra si hay varias muestras)."""
    if len(dec) == 1:
        _, _, r = dec[0]
        cab, filas = filas_para(modo, r)
        return {"cabecera": cab, "filas": filas}
    cab0, _ = filas_para(modo, dec[0][2])
    cab = ["Muestra"] + cab0
    filas = []
    for s, _, r in dec:
        _, f = filas_para(modo, r)
        label = s.nombre if s is not None else "?"
        for row in f:
            filas.append([label] + row)
    return {"cabecera": cab, "filas": filas}


def analizar_carpeta(tarjeta: Tarjeta, salida_dir: str) -> Dict:
    fig_dir = os.path.join(salida_dir, "Figures")
    xlsx_dir = os.path.join(salida_dir, "Xlsx")
    os.makedirs(fig_dir, exist_ok=True)
    os.makedirs(xlsx_dir, exist_ok=True)

    resumen_metodos: List[Dict] = []
    for m, dec in _agrupar(tarjeta):
        entry = {"modo": m.modo, "nombre": m.nombre, "usuario": m.usuario,
                 "fecha": m.fecha, "filename": m.filename, "n_muestras": len(m.muestras)}
        if not dec:
            entry["estado"] = "sin datos decodificables"
            resumen_metodos.append(entry)
            continue
        modo = dec[0][1] or m.modo
        entry["estado"] = "ok"
        entry["figura"] = _figura_por_modo(modo, dec, m, fig_dir)
        entry["tabla"] = _tabla_por_modo(modo, dec)
        entry["analisis"] = _analisis_por_modo(modo, dec)
        resumen_metodos.append(entry)

    xlsx = os.path.join(xlsx_dir, "informe.xlsx")
    crear_informe(xlsx, resumen_metodos)
    return {"xlsx": xlsx, "figuras": [m.get("figura") for m in resumen_metodos if m.get("figura")],
            "metodos": resumen_metodos}