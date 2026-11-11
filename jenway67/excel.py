# -*- coding: utf-8 -*-
"""Exportación a Excel (.xlsx) del Informe del Programa Maestro — Jenway 6705."""
from __future__ import annotations

import os
from typing import Dict, List, Optional

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

try:
    from openpyxl.drawing.image import Image as XLImage
    _HAS_PIL = True
except Exception:                      # pragma: no cover
    _HAS_PIL = False

_FUENTE = Font(bold=True, color="FFFFFF")
_RELLENO = PatternFill("solid", fgColor="4472C4")
_RELLENO2 = PatternFill("solid", fgColor="D9E1F2")


def _pinta_cabecera(ws, fila, cols):
    for c, v in enumerate(cols, 1):
        cell = ws.cell(row=fila, column=c, value=v)
        cell.font = _FUENTE
        cell.fill = _RELLENO
        cell.alignment = Alignment(horizontal="center")


def _ancho(ws, ncols, factor=1.6):
    for c in range(1, ncols + 1):
        ws.column_dimensions[get_column_letter(c)].width = max(10, int(12 * factor))


def crear_informe(ruta: str, resumen_metodos: List[Dict]):
    """Construye el .xlsx. `resumen_metodos`: lista de dicts con las claves:
    modo, nombre, usuario, fecha, filename, n_muestras, fiabilidad(str),
    tabla(cabecera,filas), analisis(cab/fil), figura(path o None)."""
    wb = Workbook()

    # ---- Hoja resumen ----
    ws = wb.active
    ws.title = "Resumen"
    cols = ["Modo", "Método", "Usuario", "Fecha", "#Muestras", "Archivo", "Estado"]
    _pinta_cabecera(ws, 1, cols)
    for i, m in enumerate(resumen_metodos, start=2):
        ws.cell(row=i, column=1, value=m.get("modo", ""))
        ws.cell(row=i, column=2, value=m.get("nombre", ""))
        ws.cell(row=i, column=3, value=m.get("usuario", ""))
        ws.cell(row=i, column=4, value=m.get("fecha", ""))
        ws.cell(row=i, column=5, value=m.get("n_muestras", ""))
        ws.cell(row=i, column=6, value=m.get("filename", ""))
        ws.cell(row=i, column=7, value=m.get("estado", "ok"))
    _ancho(ws, len(cols))

    # ---- Hoja por método ----
    titulos_usados: set = set()
    for m in resumen_metodos:
        titulo = _titulo_unico(m, titulos_usados)
        sh = wb.create_sheet(titulo)
        sh["A1"] = f"{m.get('modo','').upper()} — {m.get('nombre','')}"
        sh["A1"].font = Font(bold=True, size=12)
        meta = [
            ("Usuario", m.get("usuario", "")),
            ("Fecha", m.get("fecha", "")),
            ("Archivo .JWB", m.get("filename", "")),
            ("# muestras", m.get("n_muestras", "")),
            ("Estado", m.get("estado", "ok")),
        ]
        fila = 3
        for k, v in meta:
            sh.cell(row=fila, column=1, value=k).font = Font(bold=True)
            sh.cell(row=fila, column=2, value=v)
            fila += 1

        # tabla de datos
        t = m.get("tabla") or {}
        if t:
            fila += 1
            sh.cell(row=fila, column=1, value="Resultados decodificados").font = Font(bold=True)
            fila += 1
            cab = t.get("cabecera", [])
            _pinta_cabecera(sh, fila, cab)
            fila += 1
            for row in t.get("filas", [])[:40000]:
                for c, v in enumerate(row, 1):
                    sh.cell(row=fila, column=c, value=v)
                fila += 1
            _ancho(sh, max(len(cab), 1))

        # análisis
        a = m.get("analisis") or {}
        if a:
            fila += 2
            sh.cell(row=fila, column=1, value="Análisis").font = Font(bold=True)
            fila += 1
            for k, v in a.items():
                sh.cell(row=fila, column=1, value=str(k)).fill = _RELLENO2
                sh.cell(row=fila, column=2, value=v)
                fila += 1

        # figura incrustada
        fig = m.get("figura")
        if fig and _HAS_PIL and os.path.exists(fig):
            try:
                img = XLImage(fig)
                img.width, img.height = 620, 360
                sh.add_image(img, f"A{fila + 1}")
            except Exception:                 # pragma: no cover
                pass

    wb.save(ruta)
    return ruta


def _titulo_hoja(m):
    base = f"{m.get('modo','')}_{(m.get('nombre') or '')[:14]}_{(m.get('filename') or '')[:8]}"
    s = "".join(c if c.isalnum() or c in "_-" else "_" for c in base)
    return s[:31] or "hoja"


def _titulo_unico(m, usados: set):
    """Título de hoja único y de 31 caracteres como máximo (límite de Excel).

    Recortar a 31 caracteres puede hacer que dos métodos distintos colisionen
    (p. ej. dos .JWB que sólo difieren en los últimos dígitos del nombre); si se
    dejan repetidos, openpyxl añade un sufijo por su cuenta y el título se pasa
    del límite, con el consiguiente aviso. Aquí se desambigua explícitamente."""
    s = _titulo_hoja(m)
    if s not in usados:
        usados.add(s)
        return s
    for n in range(2, 1000):
        suf = f"_{n}"
        cand = s[:31 - len(suf)] + suf
        if cand not in usados:
            usados.add(cand)
            return cand
    return s