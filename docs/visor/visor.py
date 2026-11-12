# -*- coding: utf-8 -*-
"""Visor web (Pyodide) del Programa Maestro — Jenway 6705.

Este archivo corre DENTRO del navegador (CPython en WebAssembly via Pyodide).
Usa los parsers del proyecto SIN modificarlos: jenway67/ (leidos desde el
mismo sitio) contra una tarjeta montada en el sistema de archivos virtual
/card. Nada sale de la maquina; matplotlib pinta las figuras a PNG en memoria.

Entradas esperadas: tarjeta montada en /card (carpeta copiada del instrumento:
.JWB/.JWX/.JWU/.TXT) y jenway67/ en /lib/jenway67/ (sys.path ya preparado por la
pagina). API usada desde JavaScript:

    visor.indice_json()          -> {usuarios:[...], metodos:[{modo,nombre,usuario,
                                    fecha,filename,muestras:[{loc,resumen|error}]}]}
    visor.grafica_json(loc, modo) -> {"png": "<base64>"} | {"error": "..."}
"""
from __future__ import annotations

import base64
import io
import json
import sys

# ---------------------------------------------------------------------------
# Configuracion del backend de matplotlib (en Pyodide ya viene Agg por defecto;
# se fuerza por si acaso y antes de que nadie importe pyplot).
# ---------------------------------------------------------------------------
import matplotlib  # noqa: E402

matplotlib.use("Agg")


def resumen(modo: str, r: dict) -> str:
    """Resumen compacto de un resultado decodificado (misma filosofia que
    Script/leer_carpeta.py, sin clamp para no esconder datos)."""
    if modo == "spectrum":
        pts = r["puntos"]
        nsat = sum(1 for _, _, a in pts if a == float("inf"))
        return f"espectro {r['wl0']:.1f}..{r['wl1']:.1f} nm, {len(pts)} pts ({nsat} saturados)"
    if modo == "multi":
        celdas = ", ".join(f"{c['etiqueta']}={c['abs']:.3f}" for c in r["celdas"])
        return f"multi λ={r['wls']} | {celdas} | A1/A2={r['A1/A2']:.3f} A1−A2={r['A1-A2']:.3f}"
    if modo == "photometrics":
        a = r["abs"]
        return f"fotometría λ={r['wl']:.1f} | %T={r['t']:.3f} | Abs={'SATURADO' if a == float('inf') else f'{a:.3f}'}"
    if modo == "kinetics":
        s = r["serie"]
        if s:
            return (f"cinética λ={r['wl']:.1f} | {r['n']} pts | "
                    f"1º={s[0][2]:.3f} último={s[-1][2]:.3f} | {r['saturados']} sat")
        return f"cinética λ={r['wl']:.1f} | sin lecturas ({r['saturados']} sat)"
    if modo == "quantitation":
        a = r["abs_muestra"]
        return (f"cuantif. λ={r['wl']:.1f} | muestra Abs="
                f"{'SAT' if a == float('inf') else f'{a:.3f}'}")
    return str(r)


def _solo_finitos(v):
    import math

    if v is None:
        return None
    if isinstance(v, float) and not math.isfinite(v):
        return None
    return v


def _serie_plot(v):
    """Valor para el eje Y de una figura: None -> nan (hueco en la línea)."""
    import math

    if v is None or (isinstance(v, float) and not math.isfinite(v)):
        return float("nan")
    return v


def indice_json() -> str:
    from jenway67.reader import leer_carpeta, decodificar_archivo

    tarjeta = leer_carpeta("/card")
    out = {
        "usuarios": [u.nombre for u in tarjeta.usuarios],
        "metodos": [],
    }
    for m in sorted(tarjeta.metodos, key=lambda x: x.fecha):
        info = {
            "modo": m.modo, "nombre": m.nombre, "usuario": m.usuario,
            "fecha": m.fecha, "filename": m.filename, "muestras": [],
        }
        locs = sorted({mm.loc for mm in m.muestras if mm.loc} | {m.filename})
        for loc in locs:
            try:
                _modo2, r = decodificar_archivo(tarjeta, loc, m.modo)
                info["muestras"].append({"loc": loc, "resumen": resumen(_modo2, r)})
            except Exception as e:  # noqa: BLE001  (el visor no debe morir)
                info["muestras"].append({"loc": loc, "error": "(%s) %s" % (type(e).__name__, e)})
        out["metodos"].append(info)
    return json.dumps(out, ensure_ascii=False)


def grafica_json(loc: str, modo: str) -> str:
    """Grafica una muestra y devuelve {png: base64} (o {error: ...})."""
    try:
        from jenway67.reader import leer_carpeta, decodificar_archivo

        tarjeta = leer_carpeta("/card")
        modo2, r = decodificar_archivo(tarjeta, loc, modo)
        fig = _figura(modo2, r, loc)
        return json.dumps({"png": _png_base64(fig)})
    except Exception as e:  # noqa: BLE001
        return json.dumps({"error": "(%s) %s" % (type(e).__name__, e)})


def _png_base64(fig) -> str:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=92)
    return base64.b64encode(buf.getvalue()).decode("ascii")


def _figura(modo: str, r: dict, titulo: str):
    import matplotlib.pyplot as plt
    from matplotlib.figure import Figure
    import numpy as np

    fig = Figure(figsize=(6.2, 3.5))
    ax = fig.add_subplot(111)
    ax.set_title(titulo, fontsize=9)
    ax.grid(alpha=0.3)
    if modo == "spectrum":
        xs = [p[0] for p in r["puntos"]]
        ys = [_serie_plot(p[2]) for p in r["puntos"]]
        ax.plot(xs, ys, lw=1.1, color="#e08a2e")
        ax.set_xlabel("Longitud de onda (nm)"); ax.set_ylabel("Absorbancia")
    elif modo == "kinetics":
        ts = r["tiempos"] or list(range(r["n"]))
        ys = [_serie_plot(p[2]) for p in r["serie"]]
        ax.plot(ts, ys, lw=1.2, color="#e08a2e")
        ax.set_xlabel("Tiempo (s)"); ax.set_ylabel("Absorbancia")
    elif modo == "multi":
        etq = [c["etiqueta"] for c in r["celdas"]]
        vs = [_serie_plot(c["abs"]) or 0.0 for c in r["celdas"]]
        ax.bar(etq, vs, color="#e08a2e", alpha=0.85)
        ax.set_ylabel("Absorbancia")
        ax.text(0.02, 0.96, f"A1/A2={r['A1/A2']:.3f}   A1−A2={r['A1-A2']:.3f}",
                transform=ax.transAxes, fontsize=8, va="top")
    elif modo == "quantitation":
        cons = [c for c, _ in r["estandares"]]
        abss = [_serie_plot(a) for _, a in r["estandares"]]
        ax.scatter(cons, abss, color="#e08a2e", label="estándares")
        # unir por segmentos como el instrumento (interpolación), rechazando nan
        ok = [(c, a) for c, a in zip(cons, abss) if a == a and a is not None]
        if len(ok) >= 2:
            xs, ys = zip(*ok)
            ax.plot(xs, ys, "--", color="#7a8ca0", lw=0.8)
        am = _serie_plot(r.get("abs_muestra"))
        if am == am:  # no es nan
            ax.axhline(am, color="#4b8bb4", lw=0.8, ls=":")
            ax.scatter([], [], color="#4b8bb4", label="muestra")  # leyenda simple
        ax.set_xlabel("Concentración"); ax.set_ylabel("Absorbancia")
        ax.legend(fontsize=8)
    else:  # photometrics y cualquier cosa rara: barra simple
        ax.bar(["Abs"], [float(_serie_plot(r.get("abs")) or 0.0)], color="#e08a2e")
    fig.tight_layout()
    return fig
