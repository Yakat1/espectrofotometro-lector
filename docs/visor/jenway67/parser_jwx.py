# -*- coding: utf-8 -*-
"""Parser del índice .JWX del Jenway 6705 (métodos y sus muestras).

El .JWX es XML en CP1252 y sin declaración de encoding. Se parsea con
`xml.etree.ElementTree` (vía `utilidades.raiz_xml`), lo que lo hace robusto ante
reordenamientos de etiquetas/atributos y ante cambios de formato del firmware;
el parser anterior usaba expresiones regulares.

Estructura observada (SUMMARY*.JWX):

    <summary>
      <element id="0" type="1">
        <user>Alumnos</user>
        <method_name>Método por defecto</method_name>
        <method_date>15/9/26 11:32:24</method_date>
        <filename>323be947.JWB</filename>
        <lock>0</lock>
        <samples>
          <s_data index="1" val="Lote por defecto 001"
                  date="15/9/26 11:32:26" loc="323be947.JWB"/>
        </samples>
      </element>
      ...
    </summary>
"""
from __future__ import annotations

import os
from typing import List

from .models import Metodo, Muestra
from .utilidades import raiz_xml, texto_de

# tipo=0..4 en el .JWX
MODO = {
    "0": "photometrics",
    "1": "spectrum",
    "2": "multi",
    "3": "kinetics",
    "4": "quantitation",
}


def parsear_jwx(ruta) -> List[Metodo]:
    """Lee un archivo SUMMARY*.JWX y devuelve la lista de métodos."""
    with open(ruta, "rb") as fh:
        return parsear_jwx_bytes(fh.read())


def parsear_jwx_bytes(datos: bytes) -> List[Metodo]:
    raiz = raiz_xml(datos)
    if raiz is None:
        return []
    metodos: List[Metodo] = []
    for el in raiz.iter("element"):
        eid = el.get("id") or ""
        tipo = el.get("type") or ""
        muestras = [
            Muestra(indice=i + 1,
                    nombre=sd.get("val") or "",
                    fecha=sd.get("date") or "",
                    loc=sd.get("loc") or "")
            for i, sd in enumerate(el.iter("s_data"))
        ]
        metodos.append(Metodo(
            id=int(eid) if eid.isdigit() else 0,
            modo=MODO.get(tipo, tipo),
            usuario=texto_de(el, "user"),
            nombre=texto_de(el, "method_name"),
            fecha=texto_de(el, "method_date"),
            filename=texto_de(el, "filename"),
            bloqueado=texto_de(el, "lock") != "0",
            muestras=muestras,
        ))
    return metodos


def parsear_todas_jwx(carpeta: str) -> List[Metodo]:
    """Fusiona todos los SUMMARY*.JWX de una carpeta (y subcarpetas)."""
    metodos: List[Metodo] = []
    for raiz, _, ficheros in os.walk(carpeta):
        for fn in ficheros:
            if fn.lower().endswith(".jwx"):
                try:
                    metodos.extend(parsear_jwx(os.path.join(raiz, fn)))
                except Exception:  # pragma: no cover
                    continue
    return metodos