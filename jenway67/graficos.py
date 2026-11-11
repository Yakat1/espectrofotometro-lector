# -*- coding: utf-8 -*-
"""Gráficos del Programa Maestro (matplotlib, backend Agg: apto para scripts)."""
from __future__ import annotations

import os
from typing import Dict, List, Optional, Sequence, Tuple

import matplotlib
matplotlib.use("Agg")  # noqa: E402  (sin ventana)

import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

from .analisis import espectro_series, picos as detectar_picos, tiempos_de  # noqa: E402


def _par(wl, A):
    ok = np.isfinite(A)
    return np.asarray(wl)[ok], A[ok]


def guardar(fig, salida, ext=("png", "svg")):
    for e in ext:
        p = os.path.splitext(salida)[0] + "." + e
        fig.savefig(p, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return os.path.splitext(salida)[0] + "." + ext[0]


def graficar_espectro(espectros: Sequence[Dict], salida: str,
                      titulo: str = "Espectros",
                      etiquetas: Optional[Sequence[str]] = None,
                      marcar_picos: bool = True) -> str:
    """Overplot de varios espectros decodificados (dict con `puntos`)."""
    fig, ax = plt.subplots(figsize=(8, 4.5))
    for i, esp in enumerate(espectros):
        wl, A = espectro_series(esp["puntos"])
        if A.size == 0:
            continue
        label = (etiquetas[i] if etiquetas else f"#{i + 1}") or f"#{i + 1}"
        ax.plot(wl, A, lw=1.0, label=label)
        if marcar_picos and len(wl) > 2:
            for p in detectar_picos(esp["puntos"])[:6]:
                ax.plot(p["wl"], p["abs"], "o", ms=4, color="tab:red")
    ax.set_xlabel("Longitud de onda (nm)")
    ax.set_ylabel("Absorbancia")
    ax.set_title(titulo)
    if len(espectros) > 1:
        ax.legend(fontsize=8)
    ax.grid(alpha=.3)
    fig.tight_layout()
    return guardar(fig, salida)


def graficar_cinetica(series: Sequence[Dict], salida: str,
                      titulo: str = "Cinética",
                      etiquetas: Optional[Sequence[str]] = None) -> str:
    fig, ax = plt.subplots(figsize=(8, 4.5))
    for i, r in enumerate(series):
        idx = tiempos_de(r)
        A = np.array([s[2] for s in r.get("serie", [])], dtype=float)
        idx, A = _par(idx, A)
        if A.size == 0:
            continue
        ax.plot(idx, A, ".-", lw=1.0, label=(etiquetas[i] if etiquetas else f"#{i + 1}"))
    ax.set_xlabel("Tiempo (s)")
    ax.set_ylabel("Absorbancia")
    ax.set_title(titulo)
    if len(series) > 1:
        ax.legend(fontsize=8)
    ax.grid(alpha=.3)
    fig.tight_layout()
    return guardar(fig, salida)


def graficar_calibracion(estandares: Sequence[Tuple[float, float]],
                         muestra_abs: float, salida: str,
                         titulo: str = "Curva de calibración",
                         conc_muestra: Optional[float] = None) -> str:
    std = sorted(((float(c), float(a)) for c, a in estandares), key=lambda e: e[1])
    fig, ax = plt.subplots(figsize=(6.5, 4.5))
    if std:
        ca = np.array([s[0] for s in std]); xa = np.array([s[1] for s in std])
        ax.plot(xa, ca, "o-", color="tab:blue", label="Estándares")
        if len(xa) >= 2:
            coef = np.polyfit(xa, ca, 1)
            xx = np.linspace(xa.min(), xa.max(), 50)
            ax.plot(xx, np.polyval(coef, xx), "--", color="tab:blue", lw=1, label="Ajuste lineal")
    if muestra_abs is not None and conc_muestra is not None:
        ax.axvline(muestra_abs, color="tab:orange", ls=":", lw=1)
        ax.plot(muestra_abs, conc_muestra, "s", color="tab:red", ms=7, label="Muestra")
    ax.set_xlabel("Absorbancia")
    ax.set_ylabel("Concentración")
    ax.set_title(titulo)
    ax.legend(fontsize=8)
    ax.grid(alpha=.3)
    fig.tight_layout()
    return guardar(fig, salida)


def graficar_multi(resultados: Sequence[Dict], salida: str,
                   titulo: str = "Multi-longitud",
                   etiquetas: Optional[Sequence[str]] = None) -> str:
    """Barras de Absorbancia por longitud de onda (agrupadas si hay varias
    muestras). La absorbancia se representa clampada a 3.000, igual que el
    display del 6705, y se anotan A1/A2 y A1-A2 de la primera muestra."""
    from .utilidades import clamp_saturacion
    res = list(resultados)
    n = max(len(res), 1)
    celdas0 = res[0].get("celdas", []) if res else []
    xlabels = [f"{c.get('wl', 0):g}" for c in celdas0]
    xs = np.arange(len(xlabels), dtype=float)
    fig, ax = plt.subplots(figsize=(max(6.5, 1.15 * len(xlabels) + 2.5), 4.5))
    ancho = 0.8 / n
    for i, r in enumerate(res):
        vals = []
        for c in r.get("celdas", []):
            a = clamp_saturacion(c.get("abs"))
            vals.append(float(a) if isinstance(a, (int, float)) and np.isfinite(a) else np.nan)
        etq = (etiquetas[i] if etiquetas else f"#{i + 1}") or f"#{i + 1}"
        ax.bar(xs + (i - (n - 1) / 2.0) * ancho, vals, ancho, label=etq)
    if xlabels:
        ax.set_xticks(xs)
        ax.set_xticklabels(xlabels)
    ax.set_xlabel("Longitud de onda (nm)")
    ax.set_ylabel("Absorbancia")
    ax.set_title(titulo)
    if n > 1:
        ax.legend(fontsize=8)
    if res:
        lineas = []
        ratio, dif = res[0].get("A1/A2"), res[0].get("A1-A2")
        if isinstance(ratio, (int, float)) and np.isfinite(ratio):
            lineas.append(f"A1/A2 = {ratio:.3f}")
        if isinstance(dif, (int, float)) and np.isfinite(dif):
            lineas.append(f"A1-A2 = {dif:.3f}")
        if lineas:
            ax.text(0.99, 0.97, "\n".join(lineas), transform=ax.transAxes,
                    ha="right", va="top", fontsize=8,
                    bbox=dict(boxstyle="round", fc="white", ec="0.7", alpha=0.85))
    ax.grid(alpha=.3, axis="y")
    fig.tight_layout()
    return guardar(fig, salida)


def _boxplot_kwargs(nombres: Sequence[str]) -> Dict:
    """Compatibilidad de matplotlib: en 3.9 se renombró 'labels' -> 'tick_labels'
    y en 3.10 'vert' -> 'orientation' (se eliminarán en 3.11)."""
    try:
        mayor, menor = (int(x) for x in matplotlib.__version__.split(".")[:2])
    except Exception:                                    # pragma: no cover
        mayor, menor = 3, 8
    if (mayor, menor) >= (3, 10):
        return {"tick_labels": nombres, "orientation": "vertical"}
    if (mayor, menor) >= (3, 9):
        return {"tick_labels": nombres, "vert": True}
    return {"labels": nombres, "vert": True}


def graficar_boxplot_fotometria(grupos: Dict[str, List[float]], salida: str,
                                titulo: str = "Fotometría (réplicas)") -> str:
    """Boxplot de absorbancia por grupo/muestra.

    La absorbancia se representa clampada a 3.000, igual que el display del
    6705: una lectura saturada (%T = 0 -> Abs infinita) entraba antes en el
    boxplot como `inf`, lo que producía un aviso de numpy y una caja inválida."""
    from .utilidades import clamp_saturacion
    nombres = list(grupos.keys())
    datas = []
    for v in grupos.values():
        d = np.array([clamp_saturacion(float(x)) for x in v], dtype=float)
        datas.append(d[np.isfinite(d)])                  # quita nan e inf
    fig, ax = plt.subplots(figsize=(max(5, 1.2 * len(nombres)), 4.5))
    ax.boxplot(datas, **_boxplot_kwargs(nombres))
    for i, d in enumerate(datas):
        if d.size:
            ax.scatter(np.full(d.size, i + 1), d, alpha=.6, s=18)
    ax.set_ylabel("Absorbancia")
    ax.set_title(titulo)
    ax.grid(alpha=.3, axis="y")
    fig.tight_layout()
    return guardar(fig, salida)