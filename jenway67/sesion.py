# -*- coding: utf-8 -*-
"""Gestión y persistencia de sesiones de trabajo — Jenway 6705 (.jws / .json).

Permite guardar la sesión completa tal cual (datos crudos, métodos, usuarios,
selección activa, cadenas de procesado no destructivas, marcas de cinética,
integración de banda, rango de ejes y configuración de visualización) en un
archivo autocontenido y portable (.jws).
"""
from __future__ import annotations

import datetime
import json
import os
import tempfile
import zipfile
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from .models import Metodo, Muestra, Tarjeta, Usuario


def json_serializable(obj: Any) -> Any:
    """Convierte recursivamente estructuras de datos complejas (incluyendo numpy)
    a tipos estándar de Python serializables a JSON."""
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, (np.floating, np.float32, np.float64)):
        return float(obj)
    if isinstance(obj, (np.integer, np.int32, np.int64)):
        return int(obj)
    if isinstance(obj, (np.bool_, bool)):
        return bool(obj)
    if isinstance(obj, tuple):
        return [json_serializable(x) for x in obj]
    if isinstance(obj, list):
        return [json_serializable(x) for x in obj]
    if isinstance(obj, dict):
        return {str(k): json_serializable(v) for k, v in obj.items()}
    return obj


def tarjeta_a_dict(tarjeta: Tarjeta) -> dict:
    return {
        "carpeta": tarjeta.carpeta,
        "usuarios": [
            {
                "nivel": u.nivel,
                "nombre": u.nombre,
                "passcode": u.passcode,
                "settings": u.settings,
            }
            for u in tarjeta.usuarios
        ],
        "metodos": [
            {
                "id": m.id,
                "modo": m.modo,
                "usuario": m.usuario,
                "nombre": m.nombre,
                "fecha": m.fecha,
                "filename": m.filename,
                "bloqueado": m.bloqueado,
                "muestras": [
                    {
                        "indice": s.indice,
                        "nombre": s.nombre,
                        "fecha": s.fecha,
                        "loc": s.loc,
                    }
                    for s in m.muestras
                ],
            }
            for m in tarjeta.metodos
        ],
    }


def dict_a_tarjeta(d: dict, carpeta_override: Optional[str] = None) -> Tarjeta:
    carpeta = carpeta_override if carpeta_override is not None else d.get("carpeta", "")
    usuarios = [
        Usuario(
            nivel=u.get("nivel", 0),
            nombre=u.get("nombre", ""),
            passcode=u.get("passcode", ""),
            settings=u.get("settings", ""),
        )
        for u in d.get("usuarios", [])
    ]
    metodos = []
    for m in d.get("metodos", []):
        muestras = [
            Muestra(
                indice=s.get("indice", 0),
                nombre=s.get("nombre", ""),
                fecha=s.get("fecha", ""),
                loc=s.get("loc", ""),
            )
            for s in m.get("muestras", [])
        ]
        metodos.append(
            Metodo(
                id=m.get("id", 0),
                modo=m.get("modo", ""),
                usuario=m.get("usuario", ""),
                nombre=m.get("nombre", ""),
                fecha=m.get("fecha", ""),
                filename=m.get("filename", ""),
                bloqueado=m.get("bloqueado", False),
                muestras=muestras,
            )
        )
    return Tarjeta(carpeta=carpeta, usuarios=usuarios, metodos=metodos)


def guardar_sesion_archivo(
    datos_sesion: dict,
    ruta_destino: str,
    archivos_binarios: Optional[Dict[str, bytes]] = None,
) -> None:
    """Guarda la sesión en un archivo (.jws = zip comprimido, o .json = texto).

    Si es .jws, empaqueta el manifest.json junto con todos los archivos crudos en files/.
    """
    datos_limpios = json_serializable(datos_sesion)
    datos_limpios["timestamp_guardado"] = datetime.datetime.now().isoformat()
    datos_limpios["version_programa"] = "Programa Maestro — Jenway 6705 v2.0"

    ext = os.path.splitext(ruta_destino)[1].lower()
    if ext == ".json":
        with open(ruta_destino, "w", encoding="utf-8") as f:
            json.dump(datos_limpios, f, indent=2, ensure_ascii=False)
        return

    # Por defecto .jws (archivo zip)
    with zipfile.ZipFile(ruta_destino, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        manifest_str = json.dumps(datos_limpios, indent=2, ensure_ascii=False)
        zf.writestr("manifest.json", manifest_str.encode("utf-8"))

        if archivos_binarios:
            vistos = set()
            for rel_name, data in archivos_binarios.items():
                base = os.path.basename(rel_name)
                if base.lower() in vistos:
                    continue
                vistos.add(base.lower())
                zf.writestr(f"files/{base}", data)


def cargar_sesion_archivo(
    ruta_origen: str,
    directorio_extraccion: Optional[str] = None,
) -> Tuple[dict, Optional[str]]:
    """Carga una sesión guardada desde un archivo .jws o .json.

    Devuelve (manifest_dict, carpeta_con_archivos).
    Si se proporcionó un .jws, descomprime los archivos en un directorio temporal
    o el directorio_extraccion indicado y devuelve su ruta.
    """
    if not os.path.isfile(ruta_origen):
        raise FileNotFoundError(f"No existe el archivo de sesión: {ruta_origen}")

    if zipfile.is_zipfile(ruta_origen):
        if not directorio_extraccion:
            session_name = os.path.splitext(os.path.basename(ruta_origen))[0]
            directorio_extraccion = os.path.join(
                tempfile.gettempdir(), "jenway_maestro_sessions", session_name
            )
        os.makedirs(directorio_extraccion, exist_ok=True)

        with zipfile.ZipFile(ruta_origen, "r") as zf:
            try:
                manifest_data = zf.read("manifest.json")
            except KeyError:
                raise ValueError("El archivo .jws no contiene un 'manifest.json' válido.")
            manifest = json.loads(manifest_data.decode("utf-8"))

            for member in zf.namelist():
                if member.startswith("files/") and len(member) > len("files/"):
                    base = os.path.basename(member)
                    if base:
                        dest_file = os.path.join(directorio_extraccion, base)
                        with open(dest_file, "wb") as f_out:
                            f_out.write(zf.read(member))

        return manifest, directorio_extraccion

    # Archivo JSON plano
    with open(ruta_origen, "r", encoding="utf-8") as f:
        manifest = json.load(f)
    return manifest, None
