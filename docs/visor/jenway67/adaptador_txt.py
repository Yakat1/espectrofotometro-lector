# -*- coding: utf-8 -*-
"""Adapta los reportes `.TXT` a la MISMA forma que los resultados decodificados
de `.JWB`, para poder verlos con el panel, la tabla y el análisis sin duplicar
código (apartado 2.5: abrir un reporte sin necesidad de su `.JWX`).

Diferencia que salva este módulo: el reporte imprime SÓLO la absorbancia,
redondeada a 3 decimales y clampada a 3.000 en saturación; NO guarda el %T. Por
eso el %T se reconstruye como `T = 100·10^(-A)`.

Consecuencia importante (honestidad del dato): un resultado reconstruido desde el
reporte tiene MENOS resolución que el `.JWB` nativo (que guarda el %T real). Sirve
para consultar lo impreso, no para sustituir al dato nativo.
"""
from __future__ import annotations

import math
from typing import Dict, List, Optional, Tuple

from .parser_txt import Registro, _numero, parsear_bytes, parsear_reporte, parsear_texto

MODOS_CONOCIDOS = ("photometrics", "spectrum", "multi", "kinetics", "quantitation")


def t_de_abs(absorbancia: Optional[float]) -> float:
    """%Transmitancia reconstruida desde una absorbancia del reporte."""
    if absorbancia is None or not isinstance(absorbancia, (int, float)) or not math.isfinite(absorbancia):
        return float("nan")
    try:
        return 100.0 * 10.0 ** (-absorbancia)
    except OverflowError:                                # pragma: no cover
        return 0.0


def resultado_de_registro(reg: Registro) -> Tuple[str, List[Dict], List[str]]:
    """(modo, [resultados], [etiquetas]) con la forma que espera la interfaz."""
    modo = reg.modo
    cuerpo = reg.cuerpo or {}
    etiqueta = f"reporte #{reg.numero + 1}"
    wl_cabecera = reg.longitud_onda
    meta_extra = {
        "metodo": reg.nombre_metodo or "",
        "usuario": reg.usuario or "",
        "fecha": reg.fecha or "",
    }

    if modo == "spectrum":
        puntos = []
        for par in cuerpo.get("puntos", []):
            wl, a = par[0], par[1]
            puntos.append((float(wl), t_de_abs(a), float(a)))
        res = {"modo": modo, "puntos": puntos, "n": len(puntos),
               "wl0": puntos[0][0] if puntos else 0.0,
               "wl1": puntos[-1][0] if puntos else 0.0,
               "intervalo_nm": None, "origen": "reporte", **meta_extra}
        return modo, [res], [etiqueta]

    if modo == "kinetics":
        series_info = list(cuerpo.get("series") or [])
        if not series_info:
            crudo = list(cuerpo.get("serie", []))
            if crudo:
                series_info = [{"celda": cuerpo.get("celda", 1), "serie": crudo}]

        # Fallback de seguridad: si de algún modo 'crudo' no se separó en parser_txt
        # pero tiene reinicios de tiempo (t < t_prev o t == 0 tras avanzar), separarlo aquí.
        if len(series_info) == 1 and len(series_info[0].get("serie", [])) >= 3:
            s_unica = series_info[0]["serie"]
            bloques_separados = []
            bloque_actual = [s_unica[0]]
            for pt in s_unica[1:]:
                if pt[0] < bloque_actual[-1][0] or (pt[0] == 0.0 and bloque_actual[-1][0] > 0.0):
                    bloques_separados.append(bloque_actual)
                    bloque_actual = [pt]
                else:
                    bloque_actual.append(pt)
            if bloque_actual:
                bloques_separados.append(bloque_actual)
            if len(bloques_separados) > 1:
                series_info = [
                    {"celda": idx + 1, "serie": blk}
                    for idx, blk in enumerate(bloques_separados)
                ]

        if not series_info:
            res = {"modo": modo, "serie": [], "n": 0, "wl": wl_cabecera,
                   "tiempos": [], "origen": "reporte", **meta_extra}
            return modo, [res], [etiqueta]

        resultados, etiquetas = [], []
        es_multi = len(series_info) > 1
        for i, s_item in enumerate(series_info):
            crudo = list(s_item.get("serie", []))
            c_num = s_item.get("celda", i + 1)
            serie = [(j, t_de_abs(a), float(a)) for j, (_t, a) in enumerate(crudo)]
            res = {
                "modo": modo,
                "serie": serie,
                "n": len(serie),
                "wl": wl_cabecera,
                "tiempos": [t for t, _a in crudo],
                "celda": c_num,
                "origen": "reporte",
                **meta_extra,
            }
            resultados.append(res)
            if es_multi:
                tag = f"Carril {c_num}" if c_num is not None else f"Carril #{i + 1}"
                etiquetas.append(f"{etiqueta} ({tag})")
            else:
                etiquetas.append(etiqueta)

        return modo, resultados, etiquetas

    if modo == "multi":
        celdas = []
        for i, celda in enumerate(cuerpo.get("celdas", [])):
            a = _numero(celda.get("valor"))
            celdas.append({"wl": celda.get("wl"), "etiqueta": celda.get("etiqueta") or f"A{i + 1}",
                           "t": t_de_abs(a), "abs": a})
        calculos = cuerpo.get("calculos") or {}
        res = {"modo": modo, "celdas": celdas, "wls": [c["wl"] for c in celdas],
               "A1/A2": calculos.get("A1/A2"), "A1-A2": calculos.get("A1-A2"),
               "origen": "reporte", **meta_extra}
        return modo, [res], [etiqueta]

    if modo == "photometrics":
        resultados, etiquetas = [], []
        for i, fila in enumerate(cuerpo.get("filas", [])):
            a = _numero(fila.get("abs"))
            t_val = _numero(fila.get("t"))
            if t_val is None and a is not None:
                t_val = t_de_abs(a)
            resultados.append({"modo": modo, "wl": wl_cabecera,
                               "t": t_val, "abs": a,
                               "hora": fila.get("hora", ""),
                               "origen": "reporte", **meta_extra})
            etiquetas.append(f"#{fila.get('id', i + 1)}")
        return modo, resultados, etiquetas

    if modo == "quantitation":
        estandares = [(float(c), float(a))
                      for c, a in (reg.meta.get("__estandares__") or [])]
        muestras = list(cuerpo.get("muestras", []))
        if not muestras:
            res = {"modo": modo, "wl": wl_cabecera, "estandares": estandares,
                   "t_muestra": None, "abs_muestra": None,
                   "conc_muestra": None, "origen": "reporte", **meta_extra}
            return modo, [res], [etiqueta]
        resultados, etiquetas = [], []
        for m in muestras:
            resultados.append({
                "modo": modo,
                "wl": wl_cabecera,
                "estandares": list(estandares),
                "t_muestra": t_de_abs(m.get("abs")),
                "abs_muestra": m.get("abs"),
                "conc_muestra": m.get("conc"),
                "unidades": m.get("unidades", ""),
                "hora": m.get("fecha", ""),
                "origen": "reporte",
                **meta_extra,
            })
            etiquetas.append(str(m.get("id") or etiqueta))
        return modo, resultados, etiquetas

    return modo, [], []


def parsear_stream_serie(datos_o_texto) -> List[Tuple[Registro, str, List[Dict], List[str]]]:
    """Convierte un ticket o stream del puerto serie (bytes o str) en registros listos para la GUI.

    Devuelve una lista de tuplas ``(registro, modo, resultados, etiquetas)`` por cada
    bloque válido encontrado en la captura, conservando todos los modos presentes.
    """
    if isinstance(datos_o_texto, (bytes, bytearray)):
        registros = parsear_bytes(bytes(datos_o_texto))
    else:
        registros = parsear_texto(str(datos_o_texto))

    salida: List[Tuple[Registro, str, List[Dict], List[str]]] = []
    for reg in registros:
        if reg.modo not in MODOS_CONOCIDOS:
            continue
        modo, res, etqs = resultado_de_registro(reg)
        if res:
            salida.append((reg, modo, res, etqs))
    return salida


def cargar_reporte(ruta) -> Tuple[str, List[Dict], List[str], str]:
    """Lee un `.TXT` y devuelve `(modo, resultados, etiquetas, aviso)`.

    Un mismo archivo puede traer VARIOS modos (p. ej. el consolidado
    INTRODUZ.TXT): en ese caso se muestran los registros del primer modo y se
    avisa de cuántos modos contiene."""
    registros = parsear_reporte(ruta)
    if not registros:
        return "", [], [], ("El archivo no contiene registros de reporte "
                            "reconocibles (¿seguro que es un .TXT impreso por el 6705?).")

    modos: List[str] = []
    for reg in registros:
        if reg.modo in MODOS_CONOCIDOS and reg.modo not in modos:
            modos.append(reg.modo)
    if not modos:
        return "", [], [], "No se reconoció el modo de ningún registro del reporte."

    modo = modos[0]
    resultados: List[Dict] = []
    etiquetas: List[str] = []
    for reg in registros:
        if reg.modo != modo:
            continue
        _m, res, etqs = resultado_de_registro(reg)
        resultados += res
        etiquetas += etqs

    aviso = ""
    if len(modos) > 1:
        aviso = (f"El reporte contiene {len(modos)} modos ({', '.join(modos)}); "
                 f"se muestran los registros de «{modo}».")
    return modo, resultados, etiquetas, aviso

