# -*- coding: utf-8 -*-
"""Modelos de datos tipados del Programa Maestro Mimético — Jenway 6705."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class Muestra:
    indice: int
    nombre: str
    fecha: str
    loc: str                       # archivo .JWB de datos


@dataclass
class Metodo:
    id: int
    modo: str                      # canonico (ver parser_jwx.MODO)
    usuario: str
    nombre: str
    fecha: str
    filename: str                  # archivo .JWB del método
    bloqueado: bool = False
    muestras: List[Muestra] = field(default_factory=list)


@dataclass
class Usuario:
    nivel: int
    nombre: str
    passcode: str = ""
    settings: str = ""


@dataclass
class Tarjeta:
    """Carpeta de tarjeta copiada (login source del software original)."""
    carpeta: str
    usuarios: List[Usuario] = field(default_factory=list)
    metodos: List[Metodo] = field(default_factory=list)

    def metodo_por(self, filename: str) -> Optional[Metodo]:
        f = filename.lower()
        for m in self.metodos:
            if m.filename.lower() == f:
                return m
        return None