# -*- coding: utf-8 -*-
"""
Utilidades del núcleo `jenway67`: conversión Abs<->%T, redondeo/clamp del
instrumento, normalización de unidades, detección de codificación y lectura
robusta del XML del firmware (.JWX / .JWU).
"""
from __future__ import annotations

import html
import math
import re
from typing import Optional, Tuple

# El 6705 mide en %Transmitancia (0..~200). La absorbancia derivada es:
#   A = -log10(T/100). El display la muestra a 3 decimales y la CLAMPA a 3.000
# cuando se satura (el .JWB guarda el %T real, sin recortar).
SATURADO = 3.0
SENTINELA_CELDA_VACIA = -1.0          # aparece en arrays de espectro con menos batches


def t_a(porcentaje_t: float) -> float:
    """%Transmitancia -> Absorbancia derivada (sin recortar). T<=0 -> inf."""
    if porcentaje_t and porcentaje_t > 0:
        return -math.log10(porcentaje_t / 100.0)
    return float("inf") if (porcentaje_t is not None and porcentaje_t <= 0) else float("nan")


def a_t(absorbancia: float) -> Optional[float]:
    """Absorbancia -> %Transmitancia (inversa). None si no es válida."""
    if absorbancia is None or math.isnan(absorbancia) or math.isinf(absorbancia):
        return None
    return 100.0 * 10.0 ** (-absorbancia)


def clamp_saturacion(absorbancia: float) -> float:
    """Reproduce el display del 6705: clampa a 3.000 la absorbancia saturada."""
    if absorbancia is None or math.isnan(absorbancia):
        return absorbancia
    return SATURADO if (math.isinf(absorbancia) or absorbancia > SATURADO) else absorbancia


def redondear_display(absorbancia: float, decimales: int = 3) -> float:
    """Redondea como lo muestra el instrumento (3 decimales) tras clamp."""
    return round(clamp_saturacion(absorbancia), decimales)


def normalizar_concentracion(texto: str) -> Tuple[Optional[float], str]:
    """'0.09mM' / '30.00ppm' / '4.93 ppm' -> (numero, unidad)."""
    m = re.match(r"^\s*(-?[0-9]*\.?[0-9]+)\s*([a-zA-Zµ%]*)\s*$", str(texto))
    if not m:
        return None, ""
    try:
        return float(m.group(1)), m.group(2)
    except ValueError:
        return None, ""


def detectar_codificacion(datos: bytes) -> str:
    """Intenta CP1252 primero y cae a latin-1."""
    for cod in ("cp1252", "latin-1"):
        try:
            datos.decode(cod)
            return cod
        except UnicodeDecodeError:
            continue
    return "cp1252"


# --------------------------------------------------------------------------
# XML del firmware (.JWX / .JWU)
# --------------------------------------------------------------------------
# Los XML del 6705 van en CP1252 y SIN declaración de encoding. Se parsean con
# `xml.etree.ElementTree` (robusto ante reordenamientos de etiquetas/atributos y
# ante cambios de formato del firmware) en vez de con expresiones regulares.
# ElementTree sólo conoce las 5 entidades propias de XML, así que antes de
# parsear se traducen las entidades HTML que el firmware pudiera escribir
# (&nbsp;, &deg;, ...) y se escapan los '&' sueltos.
_PROLOGO_XML = re.compile(r"^\s*<\?xml[^>]*\?>\s*", re.IGNORECASE)
_ENTIDAD = re.compile(r"&([A-Za-z][A-Za-z0-9]*);")
_AMP_SUELTO = re.compile(r"&(?![A-Za-z#][A-Za-z0-9]*;)")
_ENTIDADES_XML = {"amp", "lt", "gt", "quot", "apos"}


def _traducir_entidad(m: "re.Match") -> str:
    """Deja las 5 entidades de XML y traduce las demás como entidades HTML."""
    if m.group(1) in _ENTIDADES_XML:
        return m.group(0)
    return html.unescape(m.group(0))


def texto_xml(datos: bytes) -> str:
    """Normaliza un XML del firmware a `str` listo para ElementTree."""
    texto = datos.decode("cp1252", errors="replace")
    texto = _PROLOGO_XML.sub("", texto)
    texto = _ENTIDAD.sub(_traducir_entidad, texto)
    return _AMP_SUELTO.sub("&amp;", texto)


def raiz_xml(datos: bytes):
    """Raíz ElementTree de un XML del firmware, o None si no es XML válido."""
    from xml.etree import ElementTree as ET
    try:
        return ET.fromstring(texto_xml(datos))
    except ET.ParseError:
        return None


def texto_de(elemento, etiqueta: str) -> str:
    """Texto del primer hijo `<etiqueta>` de `elemento` ('' si falta)."""
    if elemento is None:
        return ""
    hijo = elemento.find(etiqueta)
    return (hijo.text or "") if hijo is not None else ""