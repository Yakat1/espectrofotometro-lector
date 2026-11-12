# -*- coding: utf-8 -*-
"""
`reader.py` — lee una carpeta de "tarjeta copiada" (.JWX/.JWU/.JWB) y unifica
el índice con los decoders, replicando el *login source* del software original.

Uso:
    from jenway67.reader import leer_carpeta, decodificar_archivo
    tarjeta = leer_carpeta("c:/ruta/tarjeta")
    for metodo in tarjeta.metodos: print(metodo.modo, metodo.nombre)
    res = decodificar_archivo(tarjeta, metodo.muestras[0].loc)

SOBRE LAS SUBCARPETAS
---------------------
El índice (`SUMMARY*.JWX` / `USERSINF.JWU`) se busca **recursivamente**, porque
una copia de la tarjeta puede venir dentro de su propia carpeta.  Pero los `.JWB`
referenciados son nombres sueltos (`323BFDC8.JWB`), así que resolverlos sin más
contra la carpeta elegida fallaba cuando el índice estaba en una subcarpeta:
aparecían TODOS los métodos y NINGUNO daba datos ("Sin datos" en todo).
Aquí se resuelven por nombre en toda la tarjeta, que es lo que corresponde.
"""
from __future__ import annotations

import os
from typing import Dict, Optional, Tuple

from .models import Tarjeta
from .parser_jwx import parsear_todas_jwx
from .parser_jwu import buscar_jwu, parsear_jwu
from .parser_jwb import decodificar as decodificar_jwb

#: basename en minúsculas -> ruta completa, por carpeta de tarjeta (se cachea
#: porque una misma tarjeta se decodifica muchas veces seguidas).
_MAPA_ARCHIVOS: Dict[str, Dict[str, str]] = {}

#: lecturas en vivo (puerto serie RS-232) o reportes en memoria indexadas por ``loc``
#: (p. ej. ``"serie://lectura_001"``) -> ``(modo, resultado_dict)``.
_ARCHIVOS_VIRTUALES: Dict[str, Tuple[str, dict]] = {}


def registrar_virtual(loc: str, modo: str, resultado: dict) -> str:
    """Registra un resultado en memoria para que ``decodificar_archivo`` lo sirva."""
    _ARCHIVOS_VIRTUALES[loc] = (modo, resultado)
    return loc


def obtener_virtual(loc: str) -> Optional[Tuple[str, dict]]:
    """Devuelve ``(modo, resultado)`` si ``loc`` es una lectura en memoria."""
    return _ARCHIVOS_VIRTUALES.get(loc)


def limpiar_virtuales() -> None:
    """Limpia el almacén de lecturas virtuales en memoria."""
    _ARCHIVOS_VIRTUALES.clear()


def _mapa_de_archivos(carpeta: str) -> Dict[str, str]:
    """Índice ``nombre_en_minúsculas -> ruta completa`` de toda la tarjeta."""
    mapa: Dict[str, str] = {}
    for raiz, _subcarpetas, ficheros in os.walk(carpeta):
        for nombre in ficheros:
            mapa.setdefault(nombre.lower(), os.path.join(raiz, nombre))
    return mapa


def _mapa(carpeta: str) -> Dict[str, str]:
    if carpeta not in _MAPA_ARCHIVOS:
        _MAPA_ARCHIVOS[carpeta] = _mapa_de_archivos(carpeta)
    return _MAPA_ARCHIVOS[carpeta]


def olvidar_mapa(carpeta: Optional[str] = None) -> None:
    """Vacía la caché de archivos (para pruebas o si cambia la tarjeta)."""
    if carpeta is None:
        _MAPA_ARCHIVOS.clear()
    else:
        _MAPA_ARCHIVOS.pop(carpeta, None)


def leer_carpeta(carpeta: str) -> Tarjeta:
    """Construye el Tarjeta (usuarios + métodos) a partir de una carpeta."""
    if not os.path.isdir(carpeta):
        raise NotADirectoryError(f"no es carpeta: {carpeta}")
    olvidar_mapa(carpeta)          # por si la tarjeta cambió desde la última vez
    usuarios = []
    wu = buscar_jwu(carpeta)
    if wu:
        usuarios = parsear_jwu(wu)
    metodos = parsear_todas_jwx(carpeta)
    return Tarjeta(carpeta=carpeta, usuarios=usuarios, metodos=metodos)


def _modo_de(tarjeta: Tarjeta, filename: str) -> Optional[str]:
    """Modo de un .JWB según el índice (por método o por muestra)."""
    f = filename.lower()
    for m in tarjeta.metodos:
        if m.filename.lower() == f:
            return m.modo
        if any(s.loc.lower() == f for s in m.muestras):
            return m.modo
    return None


def resolver_ruta(tarjeta: Tarjeta, filename: str) -> str:
    """Ruta real de un archivo de la tarjeta.

    Orden: ruta absoluta tal cual; ``carpeta/archivo``; y, si no existe ahí, se
    busca el nombre en toda la tarjeta (subcarpetas incluidas).
    """
    if os.path.isabs(filename):
        return filename
    directa = os.path.join(tarjeta.carpeta, filename)
    if os.path.isfile(directa):
        return directa
    return _mapa(tarjeta.carpeta).get(os.path.basename(filename).lower(), directa)


def decodificar_archivo(tarjeta: Tarjeta, filename: str, modo: Optional[str] = None):
    """Lee y decodifica un .JWB de la tarjeta o una lectura virtual en vivo.

    Devuelve ``(modo, {datos})``. Usa el modo del índice si está disponible; si
    no, detección automática.
    """
    if filename in _ARCHIVOS_VIRTUALES:
        return _ARCHIVOS_VIRTUALES[filename]
    ruta = resolver_ruta(tarjeta, filename)
    if not os.path.isfile(ruta):
        raise FileNotFoundError(
            "el archivo %s no está en la tarjeta (%s)"
            % (os.path.basename(filename), tarjeta.carpeta))
    with open(ruta, "rb") as manejador:
        datos = manejador.read()
    if modo is None:
        modo = _modo_de(tarjeta, os.path.basename(filename))
    return decodificar_jwb(datos, modo)


def modo_de_archivo(tarjeta: Tarjeta, filename: str) -> Optional[str]:
    if filename in _ARCHIVOS_VIRTUALES:
        return _ARCHIVOS_VIRTUALES[filename][0]
    return _modo_de(tarjeta, filename)