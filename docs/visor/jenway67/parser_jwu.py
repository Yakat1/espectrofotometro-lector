# -*- coding: utf-8 -*-
"""Parser de usuarios .JWU del Jenway 6705 (PIN en claro en el XML).

El .JWU es XML en CP1252 y sin declaración de encoding. Se parsea con
`xml.etree.ElementTree` (vía `utilidades.raiz_xml`) en lugar de con expresiones
regulares, para tolerar reordenamientos de etiquetas y campos extra del firmware.

Estructura observada (USERSINF.JWU):

    <UserTable>
      <User index="0">
        <Level>0</Level>
        <Status>1</Status>
        ... (Language, Brightness, DisplayTimeDate, DateFormat, BypassLogin,
             TouchScreenClick, ShowAllMethods, MyMethods, ShowReadOnlyMethods,
             ShowPublicMethods, Offset)
        <Name>Generic</Name>
        <Passcode>1234</Passcode>
        <Settings>00000926</Settings>
      </User>
      ...
    </UserTable>
"""
from __future__ import annotations

import os
from typing import List

from .models import Usuario
from .utilidades import raiz_xml, texto_de

NIVEL = {"0": "Supervisor", "1": "Usuario"}


def parsear_jwu(ruta) -> List[Usuario]:
    with open(ruta, "rb") as fh:
        return parsear_jwu_bytes(fh.read())


def parsear_jwu_bytes(datos: bytes) -> List[Usuario]:
    raiz = raiz_xml(datos)
    if raiz is None:
        return []
    usuarios: List[Usuario] = []
    for u in raiz.iter("User"):
        nivel = texto_de(u, "Level").strip()
        usuarios.append(Usuario(
            nivel=int(nivel) if nivel.lstrip("-").isdigit() else 0,
            nombre=texto_de(u, "Name"),
            passcode=texto_de(u, "Passcode"),
            settings=texto_de(u, "Settings"),
        ))
    return usuarios


def buscar_jwu(carpeta: str):
    for raiz, _, ficheros in os.walk(carpeta):
        for fn in ficheros:
            if fn.lower() == "usersinf.jwu":
                return os.path.join(raiz, fn)
    return None