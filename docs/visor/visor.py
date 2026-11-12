# -*- coding: utf-8 -*-
"""Programa Maestro — edición web (Pyodide). Motor completo dentro del navegador.

Igual que el escritorio: decodifica los 5 modos de la tarjeta (.JWB/.JWX/.JWU),
analiza (estadisticas, picos, areas, cinetica, cuantificacion), procesa espectros
con la cadena no destructiva de jenway67.procesado, y exporta CSV / informe
Excel con figuras. Lo unico que NO existe aqui es la conexion fisica RS-232
(eso es del .exe de escritorio).

Todo corre en el navegador (CPython via Pyodide); los datos no salen del equipo.

API (JSON en / JSON out, llamada con runPythonAsync):

    catalogo_json()        -> registro de operaciones de procesado (para la UI)
    indice_json()          -> {usuarios, metodos:[{modo,nombre,usuario,fecha,
                               filename,muestras:[locs...]}]}
    vista_json(payload)    -> {modo, loc, resumen, tabla:{columnas,filas},
                               analisis:{...}, avisos:[...], figura_b64}
                               payload = json {loc, modo, locs:[...], reglas:[...]}
    informe_xlsx_json()    -> {xlsx_b64} de la tarjeta completa (figuras incrustadas)
"""
from __future__ import annotations

import base64
import io
import json
import os
import sys

import matplotlib  # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402


# ---------------------------------------------------------------------------
# serializacion segura (sin tipos numpy en el JSON)
# ---------------------------------------------------------------------------
def _sano(v):
    if isinstance(v, dict):
        return {k: _sano(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_sano(x) for x in v]
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.floating,)):
        return float(v)
    if isinstance(v, float) and (v != v):
        return None
    return v


def _json(obj) -> str:
    return json.dumps(_sano(obj), ensure_ascii=False)


def _leer_tarjeta():
    from jenway67.reader import leer_carpeta

    return leer_carpeta("/card")


# ---------------------------------------------------------------------------
# indice
# ---------------------------------------------------------------------------
def indice_json() -> str:
    tarjeta = _leer_tarjeta()
    out = {
        "usuarios": [u.nombre for u in tarjeta.usuarios],
        "metodos": [],
    }
    for m in sorted(tarjeta.metodos, key=lambda x: x.fecha):
        muestras = sorted({mm.loc for mm in m.muestras if mm.loc} | {m.filename})
        out["metodos"].append({
            "modo": m.modo, "nombre": m.nombre, "usuario": m.usuario,
            "fecha": m.fecha, "filename": m.filename, "muestras": muestras,
        })
    return _json(out)


# ---------------------------------------------------------------------------
# catalogo de operaciones de procesado (la UI se genera sola desde el)
# ---------------------------------------------------------------------------
def catalogo_json() -> str:
    from jenway67.procesado import OPERACIONES, grupos

    catalogo = {"grupos": grupos(), "operaciones": {}}
    for clave, op in OPERACIONES.items():
        parametros = [{
            "nombre": p.nombre, "etiqueta": p.etiqueta, "tipo": p.tipo,
            "defecto": p.defecto if p.defecto is not None else "",
            "minimo": p.minimo, "maximo": p.maximo,
            "opciones": list(p.opciones), "ayuda": p.ayuda,
        } for p in op.parametros]
        catalogo["operaciones"][clave] = {
            "clave": clave, "etiqueta": op.etiqueta, "grupo": op.grupo,
            "ayuda": op.ayuda, "parametros": parametros,
        }
    return _json(catalogo)


# ---------------------------------------------------------------------------
# decodificacion + cadena de procesado (no destructiva)
# ---------------------------------------------------------------------------
def _decodificar(loc, modo):
    tarjeta = _leer_tarjeta()
    from jenway67.reader import decodificar_archivo

    _modo, r = decodificar_archivo(tarjeta, loc, modo)
    return r


def _procesar(r, reglas):
    """(wl, A) procesados del espectro segun la cadena; sin tocar el original."""
    from jenway67.procesado import Cadena

    wl = np.array([p[0] for p in r["puntos"]], dtype=float)
    A = np.array([p[2] for p in r["puntos"]], dtype=float)
    cadena = Cadena()
    for paso in reglas or []:
        cadena.agregar(paso["clave"], **paso.get("parametros", {}))
    if cadena:
        return cadena.aplicar(wl, A)
    return wl, A


def _figura_png(fig) -> str:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=100, bbox_inches="tight")
    return base64.b64encode(buf.getvalue()).decode("ascii")


def _figura_espectro(wl, A, titulo, picos_marcados=None):
    fig, ax = plt.subplots(figsize=(7.2, 3.9))
    fin = np.isfinite(A)
    ax.plot(wl[fin], A[fin], lw=1.1, color="#e08a2e")
    for p in picos_marcados or []:
        ax.plot(p["wl"], p["abs"], "o", ms=5, color="#c94f4f")
    ax.set_xlabel("Longitud de onda (nm)"); ax.set_ylabel("Absorbancia")
    ax.set_title(titulo, fontsize=10); ax.grid(alpha=0.3)
    fig.tight_layout()
    return fig


def _figura_cinetica(r, titulo):
    from jenway67.analisis import tiempos_de

    t = tiempos_de(r)
    abs_ = np.array([s[2] for s in r["serie"]], dtype=float)
    fin = np.isfinite(abs_)
    fig, ax = plt.subplots(figsize=(7.2, 3.9))
    ax.plot(np.asarray(t)[fin], abs_[fin], lw=1.2, color="#e08a2e")
    ax.set_xlabel("Tiempo (s)"); ax.set_ylabel("Absorbancia")
    ax.set_title(titulo, fontsize=10); ax.grid(alpha=0.3)
    fig.tight_layout()
    return fig


def _figura_cuantif(r, titulo):
    fig, ax = plt.subplots(figsize=(7.2, 3.9))
    std = [(c, a) for c, a in r["estandares"] if np.isfinite(a)]
    if std:
        xs, ys = zip(*std)
        ax.scatter(xs, ys, color="#e08a2e", label="estándares")
        ax.plot(xs, ys, "--", color="#7a8ca0", lw=0.8)
    am = r.get("abs_muestra")
    if am is not None and np.isfinite(am):
        ax.axhline(am, color="#4b8bb4", lw=0.8, ls=":")
    ax.set_xlabel("Concentración"); ax.set_ylabel("Absorbancia")
    ax.set_title(titulo, fontsize=10); ax.grid(alpha=0.3)
    ax.legend(fontsize=8)
    fig.tight_layout()
    return fig


def _figura_multi(r, titulo):
    etq = [c["etiqueta"] for c in r["celdas"]]
    vs = [float(c["abs"]) if np.isfinite(c["abs"]) else 0.0 for c in r["celdas"]]
    fig, ax = plt.subplots(figsize=(7.2, 3.9))
    ax.bar(etq, vs, color="#e08a2e", alpha=0.85)
    ax.set_ylabel("Absorbancia"); ax.set_title(titulo, fontsize=10)
    ax.grid(alpha=0.3, axis="y")
    ax.text(0.02, 0.96, f"A1/A2={r['A1/A2']:.3f}   A1−A2={r['A1-A2']:.3f}",
            transform=ax.transAxes, fontsize=9, va="top")
    fig.tight_layout()
    return fig


def _figura_foto(valores, titulo):
    fig, ax = plt.subplots(figsize=(7.2, 3.9))
    ax.bar([f"#{i + 1}" for i in range(len(valores))], valores,
           color="#e08a2e", alpha=0.85)
    ax.set_ylabel("Absorbancia"); ax.set_title(titulo, fontsize=10)
    ax.grid(alpha=0.3, axis="y")
    fig.tight_layout()
    return fig


# ---------------------------------------------------------------------------
# vista completa de una muestra (o de un metodo fotometrico)
# ---------------------------------------------------------------------------
def vista_json(payload: str) -> str:
    datos = json.loads(payload)
    loc, modo = datos["loc"], datos["modo"]
    reglas = datos.get("reglas") or []
    locs = datos.get("locs") or []

    if modo == "photometrics":
        return _vista_fotometria(locs or [loc])

    r = _decodificar(loc, modo)

    if modo == "spectrum":
        return _vista_espectro(r, loc, reglas)
    if modo == "kinetics":
        return _vista_cinetica(r, loc)
    if modo == "quantitation":
        return _vista_cuantif(r, loc)
    if modo == "multi":
        return _vista_multi(r, loc)
    return _json({"modo": modo, "loc": loc, "resumen": "modo sin vista",
                  "tabla": {"columnas": [], "filas": []},
                  "analisis": {}, "avisos": [], "figura_b64": ""})


def _vista_espectro(r, loc, reglas):
    from jenway67 import analisis as an

    avisos = []
    if any(not np.isfinite(p[2]) for p in r["puntos"]):
        avisos.append("El espectro contiene lecturas saturadas (Abs>3).")
    wl, A = _procesar(r, reglas)
    fin = np.isfinite(A)
    wl_f, A_f = wl[fin], A[fin]
    puntos3 = list(zip(wl_f.tolist(), [0.0] * len(wl_f), A_f.tolist()))
    picos = an.picos(puntos3, prominencia=0.02)[:10]
    analisis = {
        "picos": picos,
        "area_total": an.area_bajo_curva(puntos3),
        "stats": an.estadisticas(A_f.tolist()),
        "procesado": _desc_cadena(reglas),
    }
    tabla = {
        "columnas": ["Longitud_onda_nm", "Absorbancia"],
        "filas": [[f"{wl_f[i]:.1f}", f"{A_f[i]:.3f}"] for i in range(len(wl_f))],
    }
    fig = _figura_espectro(wl, A, "%s · espectro" % loc, picos)
    return _json({
        "modo": "spectrum", "loc": loc,
        "resumen": f"espectro {wl_f[0]:.1f}..{wl_f[-1]:.1f} nm · {len(wl_f)} pts",
        "tabla": tabla, "analisis": analisis, "avisos": avisos,
        "figura_b64": _figura_png(fig),
    })


def _desc_cadena(reglas):
    from jenway67.procesado import _texto_paso

    pasos = [{"clave": p["clave"], "parametros": p.get("parametros", {})}
             for p in (reglas or [])]
    if not pasos:
        return "(sin procesar)"
    return " -> ".join(_texto_paso(p) for p in pasos)


def _vista_cinetica(r, loc):
    from jenway67 import analisis as an

    avisos = []
    if r["saturados"]:
        avisos.append(f"{r['saturados']} lectura(s) saturadas (%T=0) descartadas.")
    analisis = {"cinetica": an.cinetica(r["serie"])}
    serie = r["serie"]
    if not serie:
        avisos.append("Sin lecturas válidas.")
    tiempos = r.get("tiempos") or list(range(r["n"]))
    tabla = {"columnas": ["Tiempo_s", "Transmitancia_pct", "Absorbancia"], "filas": []}
    for k, (_i, T, A) in enumerate(serie):
        tabla["filas"].append([f"{tiempos[k]:.1f}", f"{T:.3f}",
                               "—" if not np.isfinite(A) else f"{A:.3f}"])
    fig = _figura_cinetica(r, "%s · cinética" % loc) if serie else None
    return _json({
        "modo": "kinetics", "loc": loc,
        "resumen": f"cinética λ={r['wl']:.1f} · {r['n']} pts · {r['saturados']} sat",
        "tabla": tabla, "analisis": analisis, "avisos": avisos,
        "figura_b64": _figura_png(fig) if fig else "",
    })


def _vista_cuantif(r, loc):
    from jenway67 import analisis as an

    avisos = []
    am = r["abs_muestra"]
    if am is None or not np.isfinite(am):
        avisos.append("La muestra no tiene una lectura válida.")
    analisis = {"curva": an.cuantificacion(r["estandares"],
                                           am if np.isfinite(am) else 0.0)}
    std = [(c, a) for c, a in r["estandares"]]
    filas = [["Estándar", f"{c:g}", f"{a:.3f}"] for c, a in std]
    filas.append(["Muestra", "—",
                  "—" if am is None or not np.isfinite(am) else f"{am:.3f}"])
    tabla = {"columnas": ["Tipo", "Concentración", "Absorbancia"], "filas": filas}
    fig = _figura_cuantif(r, "%s · cuantificación" % loc)
    return _json({
        "modo": "quantitation", "loc": loc,
        "resumen": (f"cuantif. λ={r['wl']:.1f} · muestra Abs={am:.3f}"
                    if np.isfinite(am)
                    else f"cuantif. λ={r['wl']:.1f} · muestra sin lectura"),
        "tabla": tabla, "analisis": analisis, "avisos": avisos,
        "figura_b64": _figura_png(fig),
    })


def _vista_multi(r, loc):
    from jenway67 import analisis as an

    avisos = []
    analisis = {"multi": an.multi_calculos(r["celdas"])}
    celdas = r["celdas"]
    filas = [[c["etiqueta"], f"{c['wl']:.1f}",
              "—" if not np.isfinite(c["abs"]) else f"{c['abs']:.3f}"]
             for c in celdas]
    filas += [["A1/A2", "", f"{r['A1/A2']:.3f}"], ["A1−A2", "", f"{r['A1-A2']:.3f}"]]
    tabla = {"columnas": ["Celda", "Longitud_onda_nm", "Absorbancia"], "filas": filas}
    fig = _figura_multi(r, "%s · multi-longitud" % loc)
    return _json({
        "modo": "multi", "loc": loc, "resumen": f"multi λ={r['wls']}",
        "tabla": tabla, "analisis": analisis, "avisos": avisos,
        "figura_b64": _figura_png(fig),
    })


def _vista_fotometria(locs):
    from jenway67 import analisis as an

    lecturas, errores = [], []
    for loc in locs:
        try:
            r = _decodificar(loc, "photometrics")
            lecturas.append({"wl": r["wl"], "t": r["t"], "abs": r["abs"], "loc": loc})
        except Exception as e:  # noqa: BLE001
            errores.append({"loc": loc, "error": str(e)})
    stats = an.fotometria(lecturas) if lecturas else {}
    filas = [[L["loc"], f"{L['wl']:.1f}", f"{L['t']:.3f}",
              "SAT" if not np.isfinite(L["abs"]) else f"{L['abs']:.3f}"]
             for L in lecturas]
    tabla = {"columnas": ["Archivo", "Longitud_onda_nm", "Transmitancia_pct",
                          "Absorbancia"],
             "filas": filas}
    avisos = []
    if stats.get("saturados"):
        avisos.append("%d muestra(s) saturada(s) (Abs>3.000)." % stats["saturados"])
    if errores:
        avisos.append("%d archivo(s) sin poder leerse." % len(errores))
    valores = [float(L["abs"]) for L in lecturas if np.isfinite(L["abs"])]
    fig = _figura_foto(valores,
                       "Fotometría · %d lectura(s)" % len(valores)) if valores else None
    resumen = "fotometría · %d lecturas" % len(lecturas)
    if stats.get("wl") is not None:
        resumen += f" · λ={stats['wl']:.1f}"
    return _json({
        "modo": "photometrics",
        "loc": ", ".join(locs[:3]) + ("…" if len(locs) > 3 else ""),
        "resumen": resumen,
        "tabla": tabla, "analisis": {"fotometria": stats}, "avisos": avisos,
        "figura_b64": _figura_png(fig) if fig else "",
    })


# ---------------------------------------------------------------------------
# informe Excel de la tarjeta completa (openpyxl + figuras incrustadas)
# ---------------------------------------------------------------------------
def informe_xlsx_json() -> str:
    from jenway67.informe import analizar_carpeta

    tarjeta = _leer_tarjeta()
    salida = "/tmp/informe"
    res = analizar_carpeta(tarjeta, salida)
    ruta = res.get("xlsx") or os.path.join(salida, "Xlsx", "informe.xlsx")
    with open(ruta, "rb") as m:
        contenido = m.read()
    return _json({"xlsx_b64": base64.b64encode(contenido).decode("ascii"),
                  "metodos": len(tarjeta.metodos)})
