# -*- coding: utf-8 -*-
"""
Motor de análisis del Programa Maestro Mimético — Jenway 6705.

Opera sobre los resultados decodificados por `parser_jwb` (dicts) y produce
tablas, estadísticas y cálculos replicando / extendiendo lo que hace el 6705.

Funciones puras (numpy): no dibujan ni escriben; para gráficos y Excel ver
`graficos.py` y `excel.py`.
"""
from __future__ import annotations

import math
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

# numpy 2.0 renombró trapz -> trapezoid; soportamos ambas versiones.
_trapz = getattr(np, "trapezoid", None) or getattr(np, "trapz", None)


def _fin(a) -> bool:
    """True si a es un número finito (descarta inf de saturación y nan)."""
    return not (isinstance(a, float) and (math.isinf(a) or math.isnan(a)))


def estadisticas(valores: Sequence[float]) -> Dict:
    """Media, SD, min, max, n de una lista de valores finitos."""
    v = np.asarray([float(x) for x in valores if _fin(x)], dtype=float)
    if v.size == 0:
        return {"n": 0}
    return {"n": int(v.size),
            "media": float(np.mean(v)),
            "desv": float(np.std(v, ddof=1)) if v.size > 1 else 0.0,
            "min": float(np.min(v)),
            "max": float(np.max(v))}


# --------------------------------------------------------------------------
# Espectro
# --------------------------------------------------------------------------

def espectro_series(puntos: Sequence[Tuple]) -> Tuple[np.ndarray, np.ndarray]:
    """(wl, abs) válidos de un dict de espectro decodificado (mask finita)."""
    wl = np.array([p[0] for p in puntos], dtype=float)
    A = np.array([p[2] for p in puntos], dtype=float)
    ok = np.isfinite(A) & np.isfinite(wl)
    return wl[ok], A[ok]


def fwhm_pico(wl: np.ndarray, A: np.ndarray, idx_pico: int) -> Optional[float]:
    """Calcula la anchura a media altura (FWHM, en unidades de ``wl``) del pico en ``idx_pico``.

    Determina la base local del pico como el mayor entre el mínimo a la izquierda
    (antes de superar la altura del pico) y el mínimo a la derecha, e interpola
    linealmente los dos puntos de cruce a media altura.
    """
    n = A.size
    if n < 3 or idx_pico <= 0 or idx_pico >= n - 1:
        return None
    y_pico = float(A[idx_pico])
    if not math.isfinite(y_pico):
        return None

    # Buscar el límite izquierdo (hasta borde o hasta un punto más alto que el pico)
    i_izq = idx_pico
    min_izq = y_pico
    pos_min_izq = idx_pico
    while i_izq > 0:
        i_izq -= 1
        if A[i_izq] > y_pico:
            break
        if A[i_izq] <= min_izq:
            min_izq = float(A[i_izq])
            pos_min_izq = i_izq

    # Buscar el límite derecho (hasta borde o hasta un punto más alto que el pico)
    i_der = idx_pico
    min_der = y_pico
    pos_min_der = idx_pico
    while i_der < n - 1:
        i_der += 1
        if A[i_der] > y_pico:
            break
        if A[i_der] <= min_der:
            min_der = float(A[i_der])
            pos_min_der = i_der

    base = max(min_izq, min_der)
    altura = y_pico - base
    if altura <= 0:
        return None
    mitad = base + 0.5 * altura

    # Cruce izquierdo entre pos_min_izq y idx_pico
    x_izq: Optional[float] = None
    for k in range(idx_pico - 1, pos_min_izq - 1, -1):
        if A[k] <= mitad <= A[k + 1]:
            dy = float(A[k + 1] - A[k])
            frac = (mitad - float(A[k])) / dy if dy != 0 else 0.0
            x_izq = float(wl[k]) + frac * float(wl[k + 1] - wl[k])
            break

    # Cruce derecho entre idx_pico y pos_min_der
    x_der: Optional[float] = None
    for k in range(idx_pico, pos_min_der):
        if A[k + 1] <= mitad <= A[k]:
            dy = float(A[k + 1] - A[k])
            frac = (mitad - float(A[k])) / dy if dy != 0 else 0.0
            x_der = float(wl[k]) + frac * float(wl[k + 1] - wl[k])
            break

    if x_izq is None or x_der is None:
        return None
    fwhm = abs(x_der - x_izq)
    return float(fwhm) if fwhm > 0 else None


def picos(puntos: Sequence[Tuple], prominencia: float = 0.02,
          tipos=("max", "min")) -> List[Dict]:
    """Picos y valles (máximos/mínimos locales) con prominencia mínima y FWHM."""
    wl, A = espectro_series(puntos)
    if A.size < 3:
        return []
    res = []
    for i in range(1, A.size - 1):
        for tipo in tipos:
            if tipo == "max" and A[i] > A[i - 1] and A[i] >= A[i + 1]:
                prom = A[i] - min(A[i - 1], A[i + 1])
            elif tipo == "min" and A[i] < A[i - 1] and A[i] <= A[i + 1]:
                prom = min(A[i - 1], A[i + 1]) - A[i]
            else:
                continue
            if prom >= prominencia:
                fwhm = fwhm_pico(wl, A, i) if tipo == "max" else None
                res.append({"wl": float(wl[i]), "abs": float(A[i]),
                            "tipo": tipo, "prominencia": float(prom),
                            "fwhm": fwhm})
    return res


def area_bajo_curva(puntos: Sequence[Tuple],
                    wl_a: Optional[float] = None,
                    wl_b: Optional[float] = None) -> float:
    """Área bajo la curva (trapezoidal) sobre Absorbancia en [wl_a, wl_b]."""
    wl, A = espectro_series(puntos)
    if A.size < 2:
        return 0.0
    if wl_a is not None:
        m = wl >= wl_a
        wl, A = wl[m], A[m]
    if wl_b is not None:
        m = wl <= wl_b
        wl, A = wl[m], A[m]
    if A.size < 2:
        return 0.0
    return float(_trapz(A, wl))


def integrar_banda(puntos: Sequence[Tuple],
                   wl_a: Optional[float] = None,
                   wl_b: Optional[float] = None) -> Dict[str, float]:
    r"""Integración estilo Spectragryph de una banda en ``[wl_a, wl_b]``.

    Devuelve:
      * ``area_bruta``: integral trapezoidal bajo la curva $A(\lambda)$.
      * ``area_base``: integral del trapecio formado por la cuerda lineal que
        une $(\lambda_a, A(\lambda_a))$ con $(\lambda_b, A(\lambda_b))$.
      * ``area_neta``: ``area_bruta - area_base`` (área neta del pico sobre su base).
      * ``wl_a``, ``wl_b``, ``max_wl``, ``max_abs``.
    """
    wl, A = espectro_series(puntos)
    if A.size < 2:
        return {"wl_a": 0.0, "wl_b": 0.0, "area_bruta": 0.0,
                "area_base": 0.0, "area_neta": 0.0, "max_wl": 0.0, "max_abs": 0.0}
    lo = float(wl.min()) if wl_a is None else float(min(wl_a, wl_b if wl_b is not None else wl_a))
    hi = float(wl.max()) if wl_b is None else float(max(wl_b, wl_a if wl_a is not None else wl_b))
    m = (wl >= lo) & (wl <= hi)
    wl_s, A_s = wl[m], A[m]
    if A_s.size < 2:
        return {"wl_a": lo, "wl_b": hi, "area_bruta": 0.0,
                "area_base": 0.0, "area_neta": 0.0, "max_wl": lo, "max_abs": 0.0}
    bruta = float(_trapz(A_s, wl_s))
    base_recta = np.linspace(float(A_s[0]), float(A_s[-1]), A_s.size)
    area_base = float(_trapz(base_recta, wl_s))
    idx_max = int(np.argmax(A_s))
    return {
        "wl_a": float(wl_s[0]),
        "wl_b": float(wl_s[-1]),
        "area_bruta": bruta,
        "area_base": area_base,
        "area_neta": bruta - area_base,
        "max_wl": float(wl_s[idx_max]),
        "max_abs": float(A_s[idx_max]),
    }


def derivada(puntos: Sequence[Tuple], orden: int = 1) -> List[Tuple]:
    """1.ª o 2.ª derivada (np.gradient) sobre Absorbancia vs longitud de onda."""
    wl, A = espectro_series(puntos)
    d = np.gradient(A, wl)
    for _ in range(orden - 1):
        d = np.gradient(d, wl)
    return [(float(wl[i]), float(d[i])) for i in range(A.size)]


# --------------------------------------------------------------------------
# Fotometría
# --------------------------------------------------------------------------

def fotometria(lecturas: Sequence[Dict]) -> Dict:
    """Estadística de réplicas fotométricas (cada dict: wl/t/abs)."""
    abss = [L.get("abs") for L in lecturas]
    t_list = [L.get("t") for L in lecturas]
    wl = lecturas[0].get("wl") if lecturas else None
    res = {"wl": wl, "n": len(lecturas)}
    res.update(estadisticas(abss))
    res["t_media"] = estadisticas(t_list).get("media")
    # recuento de saturados (Abs > 3.0 o inf)
    res["saturados"] = sum(1 for a in abss
                           if not _fin(a) or (isinstance(a, float) and a > 3.0))
    return res


# --------------------------------------------------------------------------
# Cinética
# --------------------------------------------------------------------------

def tiempos_de(r: Dict) -> np.ndarray:
    """Eje X (segundos) de una cinética.

    Usa los tiempos reales si el archivo los trae — el reporte .TXT del
    instrumento los imprime y el .JWB los reconstruye del tiempo final—; si no,
    cae al índice de lectura (1 s por punto), que es la antigua suposición.
    """
    serie = r.get("serie") or []
    tiempos = r.get("tiempos")
    if tiempos and len(tiempos) == len(serie):
        return np.array(tiempos, dtype=float)
    return np.array([float(s[0]) for s in serie], dtype=float)


def cinetica(serie: Sequence[Tuple]) -> Dict:
    """Sobre la serie [(idx, %T, Abs), ...]: pendiente (rate), min/max, Δ."""
    abs_ = np.array([s[2] for s in serie if _fin(s[2])], dtype=float)
    if abs_.size < 2:
        return {"n": len(serie)}
    x = np.arange(abs_.size, dtype=float)
    pend, _ = np.polyfit(x, abs_, 1)
    return {
        "n": int(abs_.size),
        **estadisticas(abs_.tolist()),
        "rate": float(pend),                     # Abs por índice (≈ por intervalo)
        "delta_total": float(abs_[-1] - abs_[0]),
        "inicial": float(abs_[0]),
        "final": float(abs_[-1]),
    }


# --------------------------------------------------------------------------
# Cuantificación
# --------------------------------------------------------------------------

def cuantificacion(estandares: Sequence[Tuple[float, float]],
                   muestra_abs: float) -> Dict:
    """Curva de calibración (estándares (conc, abs)) + C° de una muestra.

    `conc_interp` = interpolación por segmentos + extrapolación del último tramo
    (replica el display del 6705). También ajustes lineal y cuadrático con r².
    """
    std = sorted(((float(c), float(a)) for c, a in estandares if _fin(a)),
                 key=lambda e: e[1])
    xa = np.array([s[1] for s in std], dtype=float)   # abs
    ca = np.array([s[0] for s in std], dtype=float)   # conc
    res: Dict = {"estandares": list(std)}

    def interp(absv: float) -> float:
        if absv <= xa[0]:
            return ca[0]
        for i in range(len(xa) - 1):
            if xa[i] <= absv <= xa[i + 1]:
                dx = xa[i + 1] - xa[i]
                if dx == 0:                      # estándares con la misma absorción
                    return ca[i + 1]
                return ca[i] + (absv - xa[i]) * (ca[i + 1] - ca[i]) / dx
        if len(xa) >= 2 and xa[-1] != xa[-2]:
            return ca[-1] + (absv - xa[-1]) * (ca[-1] - ca[-2]) / (xa[-1] - xa[-2])
        return ca[-1]

    res["conc_interp"] = float(interp(muestra_abs)) if _fin(muestra_abs) else None

    if len(xa) >= 2:
        rango = float(xa.max() - xa.min())
        for nombre, grado in (("lineal", 1), ("cuadratico", 2)):
            if grado + 1 > len(xa) or rango == 0.0:
                # sin rango de absorbancias no hay recta (ni parábola) que ajustar:
                # p. ej. una calibración medida en blanco. Antes esto reventaba con
                # LinAlgError de numpy y tumbaba el informe completo.
                continue
            try:
                coef = np.polyfit(xa, ca, grado)
            except (np.linalg.LinAlgError, ValueError, FloatingPointError):
                continue
            pred = np.polyval(coef, xa)
            ss_res = float(np.sum((ca - pred) ** 2))
            ss_tot = float(np.sum((ca - ca.mean()) ** 2))
            r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else 1.0
            res[f"{nombre}_coef"] = [float(c) for c in coef]
            res[f"{nombre}_r2"] = float(r2)
            if _fin(muestra_abs):
                res[f"{nombre}_pred"] = float(np.polyval(coef, muestra_abs))
    return res


# --------------------------------------------------------------------------
# Multi-longitud
# --------------------------------------------------------------------------

def multi_calculos(celdas: Sequence[Dict]) -> Dict:
    """A1..A4 (display clampado), relación, diferencia y suma de las fórmulas."""
    from .utilidades import clamp_saturacion
    fs = [clamp_saturacion(c.get("abs")) for c in celdas]
    a1, a2 = fs[0], fs[1] if len(fs) > 1 else None
    res = {"A1": a1, "A2": a2,
           "A3": fs[2] if len(fs) > 2 else None,
           "A4": fs[3] if len(fs) > 3 else None}
    res["A1_A2_ratio"] = a1 / a2 if a2 not in (None, 0) else None
    res["A1_A2_diff"] = a1 - a2 if a2 is not None else None
    res["sumaAr"] = (a1 + (fs[2] if len(fs) > 2 and fs[2] else 0)) \
        if a1 is not None else None
    return res