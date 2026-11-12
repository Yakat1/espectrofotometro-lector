# -*- coding: utf-8 -*-
"""
Decoders de archivos binarios .JWB del espectrofotómetro Jenway 6705.

Formatos validados experimentalmente (15/09) contra los reportes .TXT que
imprime el propio instrumento (decode(JWB) == reporte):

  - Cabecera común: float32 en offset 0x34 = longitud de onda 1 (nm).
      - Spectrum   : 0x34 = λ inicio, 0x38 = λ fin, escala Y en 0x5c/0x60.
      - Multi-Long : 0x34,0x38,0x3c,0x40 = las 4 longitudes de onda.
      - Quantitation: 0x34 = λ; estándares de concentración en 0x110.. y
                      absorbancia de estándares en 0x15c.. (guardadas ya como
                      absorbancia); lectura de muestra en %T al final.
      - Photometrics: 0x34 = λ; lectura en %T al final.
      - Kinetics    : 0x34 = λ; serie de %T al final.

  - Las LECTURAS se guardan como %TRANSMITANCIA (0..~200), salvo los estándares
    de Quantitation que se guardan como absorbancia ya calculada.
  - El reporte .TXT imprime Absorbancia a 3 decimales y RECORTA (clampa) a
    3.000 en saturación; el .JWB conserva el %T real. Aquí entregamos ambos
    (%T y Absorbancia derivada sin recortar) para que la capa de presentación
    decida cómo representar la saturación.

  - El "tipo" de cada .JWB (photometrics|spectrum|multi|kinetics|quantitation)
    lo da el índice .JWX. También se ofrece una detección heurística para leer
    un .JWB suelto.

Uso:
    from jenway67.parser_jwb import decodificar
    with open("x.JWB","rb") as f: b = f.read()
    res = decodificar(b, modo="spectrum")      # modo explícito
    modo, res = decodificar(b)                  # o auto-detección
"""
from __future__ import annotations

import math
import struct
from typing import Dict, List, Optional, Tuple, Union

# --------------------------------------------------------------------------
# primitivas
# --------------------------------------------------------------------------

def _le(b: bytes, o: int) -> float:
    """float32 little-endian en offset o; fuera de rango -> 0.0 (tolerante)."""
    if o < 0 or o + 4 > len(b):
        return 0.0
    return struct.unpack("<f", b[o:o + 4])[0]


def _t_a(T: float) -> float:
    """%Transmitancia -> Absorbancia derivada (sin recortar). T<=0 -> inf (saturado)."""
    if T and T > 0:
        return -math.log10(T / 100.0)
    return float("inf") if T <= 0 else float("nan")


def _bloque_tail(b: bytes) -> bytes:
    """Devuelve el bloque final de datos: desde el final, todo valor que sea
    %T (0<v<=200) o la marca sentinela -99999. Es donde acaban las lecturas."""
    i = len(b)
    while i >= 4:
        v = _le(b, i - 4)
        if (0.0 < v <= 200.0) or (v == -99999.0):
            i -= 4
        else:
            break
    return b[i:]


def _porcentajes_de(bloque: bytes) -> List[float]:
    """Todos los %T válidos (0<v<=200) dentro de un bloque de datos."""
    out = []
    for o in range(0, len(bloque) - 3, 4):
        v = _le(bloque, o)
        if 0.0 < v <= 200.0:
            out.append(v)
    return out


def _serie_marcada(b: bytes) -> List[float]:
    """Serie de cinética: %T adyacentes a la marca sentinela -99999 (robusto al
    orden del par y a valores sueltos del método)."""
    return _serie_y_saturados(b)[0]


def _serie_y_saturados(b: bytes) -> Tuple[List[float], int]:
    """Serie de cinética y cuántas lecturas se descartaron por saturación.

    Devuelve ``(validos, saturados)``.  Un par ``(0.0, -99999.0)`` es una
    lectura con **%T = 0**, es decir muestra saturada (opaca): el equipo guardó
    el par pero no hay transmitancia utilizable.  Contarlas permite avisar en la
    interfaz en vez de dejar la pantalla en "Sin datos" sin explicar nada.
    (Caso real: ``323be85f.JWB``, cinética a 330 nm con las 15 lecturas a 0.)
    """
    validos, saturados = [], 0
    for o in range(4, len(b) - 3, 4):
        v = _le(b, o)
        prec, sig = _le(b, o - 4), _le(b, o + 4)
        if prec != -99999.0 and sig != -99999.0:
            continue                      # no es una lectura de la serie
        if 1e-6 < v <= 200.0:             # %T válido
            validos.append(v)
        elif -1e-6 <= v <= 1e-6:          # %T = 0 -> saturada
            saturados += 1
    return validos, saturados


# --------------------------------------------------------------------------
# decoders por modo
# --------------------------------------------------------------------------

def _dec_spectrum(b: bytes) -> Dict:
    wl0, wl1 = _le(b, 0x34), _le(b, 0x38)
    n = int(round((wl1 - wl0) / 0.1)) + 1
    data_off = len(b) - 4 * n
    puntos = []
    for i in range(n):
        T = _le(b, data_off + 4 * i)
        if not (0.0 <= T <= 200.0):          # 0.0 = saturado (se conserva)
            T = float("nan")
        wl = round(wl0 + i * 0.1, 1)
        puntos.append((wl, T, _t_a(T)))
    return {
        "modo": "spectrum", "wl0": wl0, "wl1": wl1, "intervalo_nm": 0.1,
        "ymin": _le(b, 0x5C), "ymax": _le(b, 0x60),
        "n": n, "puntos": puntos,
    }


def _dec_multi(b: bytes) -> Dict:
    wls = [round(_le(b, 0x34 + 4 * i), 1) for i in range(4)]
    # las 4 lecturas son los ÚLTIMOS 4 floats (el %T puede ser 0.0 = saturado)
    off = len(b) - 16
    Ts = [_le(b, off + 4 * i) for i in range(4)]
    celdas = []
    for i, wl in enumerate(wls):
        T = Ts[i]
        celdas.append({"wl": wl, "etiqueta": f"A{i+1}", "t": T, "abs": _t_a(T)})
    # Para reproducir el display del instrumento: la absorbancia se clampa a 3.000
    # antes de calcular los índices (el .JWB guarda %T real; el 6705 muestra/clampa 3.0).
    def _display(a: float) -> float:
        return 3.0 if (math.isinf(a) or a > 3.0) else a
    d1, d2 = _display(celdas[0]["abs"]), _display(celdas[1]["abs"])
    return {
        "modo": "multi", "wls": wls, "celdas": celdas,
        "A1/A2": d1 / d2 if d2 else float("nan"),
        "A1-A2": d1 - d2,
    }


def _dec_photometrics(b: bytes) -> Dict:
    wl = _le(b, 0x34)
    T = _le(b, len(b) - 4)          # lectura = último float (%T, puede ser 0= saturado)
    return {"modo": "photometrics", "wl": wl, "t": T, "abs": _t_a(T)}


def _intervalo_kinetics(t_final: float, n: int) -> float:
    """Paso medio entre lecturas (s) = tiempo final / (n − 1).

    OJO: el paso NO es un 2.000 s exacto. El cronómetro del instrumento avanza
    de 2 en 2 s pero a veces salta a 3 (el informe impreso de una cinética de
    30 s da 0, 2, 4, …, 24, 27, 29). Por eso 146 lecturas cubren ~298 s y no
    290: el paso medio real es ~2.06 s.
    """
    if n <= 1 or not math.isfinite(t_final) or t_final <= 0:
        return 1.0
    paso = t_final / (n - 1)
    if not math.isfinite(paso) or paso <= 0:
        return 1.0
    return float(paso)


def _tiempos_kinetics(t_final: float, n: int) -> List[float]:
    """Rejilla de tiempos (s) de una cinética: de 0 al tiempo FINAL guardado.

    El .JWB trae en 0x38 el tiempo de la última lectura, así que los tiempos se
    reparten de 0 a ese valor.  Como el instrumento imprime segundos enteros
    (con algún salto), con paso ≥ 1 s se redondea a entero; así la última
    lectura cae en el tiempo final del archivo (298 ≈ 300 s) en vez de quedarse
    corta aplicando un 2 s fijo.
    """
    if n <= 0:
        return []
    if n == 1:
        return [0.0]
    paso = _intervalo_kinetics(t_final, n)
    if paso >= 1.0:
        tiempos = [float(round(i * paso)) for i in range(n)]
    else:
        tiempos = [float(i * paso) for i in range(n)]
    for i in range(1, len(tiempos)):            # redondeo: garantizar monotonía
        if tiempos[i] <= tiempos[i - 1]:
            tiempos[i] = tiempos[i - 1] + 1.0
    return tiempos


def _dec_kinetics(b: bytes) -> Dict:
    wl = _le(b, 0x34)
    # 0x38 = TIEMPO de la última lectura (el .JWB no guarda el intervalo).
    t_final = _le(b, 0x38)
    Ts, saturados = _serie_y_saturados(b)
    n = len(Ts)
    intervalo = _intervalo_kinetics(t_final, n)
    serie = [(i, T, _t_a(T)) for i, T in enumerate(Ts)]
    # 'tiempos': eje X real en segundos (0 … tiempo final). El .TXT del
    # instrumento los imprime; aquí se reconstruyen del tiempo final.  Así la
    # cinética no se dibuja "a la mitad" cuando el intervalo no es 1 s.
    tiempos = _tiempos_kinetics(t_final, n)
    # 'saturados': lecturas descartadas por %T = 0 (muestra opaca).  Se expone
    # para que la interfaz pueda decir POR QUE una cinética sale vacía en vez de
    # dejar la pantalla en "Sin datos".
    return {"modo": "kinetics", "wl": wl, "n": n, "serie": serie,
            "tiempos": tiempos, "intervalo_s": intervalo,
            "tiempo_total": t_final, "saturados": saturados}


def _dec_quantitation(b: bytes) -> Dict:
    wl = _le(b, 0x34)
    # estándares: concentraciones (0x110..) y absorbancias (0x15c..)
    cons = [_le(b, 0x110 + 4 * i) for i in range(3)]          # std 2,3,4 (std1=0)
    abss = [_le(b, 0x15C + 4 * i) for i in range(4)]          # abs de estándares
    estandares = [(0.0, abss[0]), (cons[0], abss[1]),
                  (cons[1], abss[2]), (cons[2], abss[3])]
    bloque = _bloque_tail(b)
    Ts = _porcentajes_de(bloque)
    T_muestra = _le(b, len(b) - 4) if Ts else float("nan")
    return {
        "modo": "quantitation", "wl": wl, "estandares": estandares,
        "t_muestra": T_muestra, "abs_muestra": _t_a(T_muestra),
    }


_DECODERS = {
    "photometrics": _dec_photometrics,
    "spectrum": _dec_spectrum,
    "multi": _dec_multi,
    "kinetics": _dec_kinetics,
    "quantitation": _dec_quantitation,
}


def decodificar(b: bytes, modo: Optional[str] = None) -> Tuple[str, Dict]:
    """Decodifica un .JWB. Devuelve (modo, dict con datos).
    Si `modo` es None, intenta detectarlo (heurístico, mejor usar el .JWX)."""
    if modo is None:
        modo = _detectar_modo(b)
    f = _DECODERS.get(modo)
    if f is None:
        raise ValueError(f"modo desconocido: {modo}")
    return modo, f(b)


# --------------------------------------------------------------------------
# detección heurística de modo (cuando no hay .JWX)
# --------------------------------------------------------------------------

def _detectar_modo(b: bytes) -> str:
    w0, w1 = _le(b, 0x34), _le(b, 0x38)
    w2, w3 = _le(b, 0x3C), _le(b, 0x40)
    n_esp = int(round((w1 - w0) / 0.1)) + 1 if w1 > w0 else 0
    # multi: 4 longitudes de onda distintas y plausibles
    if all(100 < v < 1200 for v in (w0, w1, w2, w3)) and len({w0, w1, w2, w3}) == 4:
        return "multi"
    # spectrum: rango grande con muchos puntos
    if n_esp >= 100 and (len(b) - 4 * n_esp) > 0:
        return "spectrum"
    # photometrics vs kinetics vs quantitation: tamaño y campos
    if n_esp == 0:
        # ¿quantitation? estándares de conc en 0x110
        if _le(b, 0x110) > 0 or _le(b, 0x11C) > 0:
            return "quantitation"
        # kinetics: serie larga al final
        if len(_porcentajes_de(_bloque_tail(b))) >= 5:
            return "kinetics"
        return "photometrics"
    return "photometrics"