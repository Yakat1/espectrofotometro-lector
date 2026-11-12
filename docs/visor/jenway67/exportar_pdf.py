# -*- coding: utf-8 -*-
"""Exportación de reportes científicos en PDF vectorial para el Jenway 6705.

Genera documentos PDF de tamaño A4 vertical usando ``matplotlib.backends.backend_pdf.PdfPages``
sin requerir librerías externas adicionales. Incluye:
  * Encabezado institucional del instrumento (Jenway 6705 UV/Vis), método, modo,
    usuario y fecha.
  * Gráfico vectorial de alta resolución (espectro, cinética, calibración,
    multi-longitud o fotometría).
  * Tabla de métricas analíticas (picos, AUC, tasa cinética, R², etc.).
  * Extracto de la tabla de puntos de datos.
"""
from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional, Sequence

import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.figure import Figure

from . import analisis as an
from .exportar import filas_para
from .informe import _agrupar, _analisis_por_modo
from .models import Tarjeta
from .utilidades import clamp_saturacion

ETIQUETAS_MODO = {
    "spectrum": "Espectro (Barrido λ)",
    "kinetics": "Cinética (Abs vs Tiempo)",
    "quantitation": "Cuantificación (Curva de Calibración)",
    "multi": "Multi-longitud de onda",
    "photometrics": "Fotometría Simple",
}


def _dibujar_grafico_en_eje(ax, modo: str, resultados: Sequence[Dict], etiquetas: Sequence[str]) -> None:
    paleta = ("#1f6feb", "#d97706", "#059669", "#dc2626", "#7c3aed", "#0891b2")
    if modo == "spectrum":
        for idx, (r, etq) in enumerate(zip(resultados, etiquetas)):
            pts = r.get("puntos") or []
            if not pts:
                continue
            xs = [p[0] for p in pts]
            ys = [clamp_saturacion(p[2]) for p in pts]
            ax.plot(xs, ys, label=etq, color=paleta[idx % len(paleta)], linewidth=1.3)
        ax.set_xlabel("Longitud de onda (nm)")
        ax.set_ylabel("Absorbancia (A)")
        if len(resultados) > 1:
            ax.legend(fontsize=8, loc="best")
    elif modo == "kinetics":
        for idx, (r, etq) in enumerate(zip(resultados, etiquetas)):
            serie = r.get("serie") or []
            if not serie:
                continue
            xs = an.tiempos_de(r)
            ys = [clamp_saturacion(s[2]) for s in serie]
            ax.plot(xs, ys, marker="o", markersize=3, label=etq,
                    color=paleta[idx % len(paleta)], linewidth=1.3)
        ax.set_xlabel("Tiempo (s)")
        ax.set_ylabel("Absorbancia (A)")
        if len(resultados) > 1:
            ax.legend(fontsize=8, loc="best")
    elif modo == "quantitation" and resultados:
        r0 = resultados[0]
        stds = r0.get("estandares") or []
        if stds:
            cs = [c for c, _a in stds]
            as_ = [clamp_saturacion(a) for _c, a in stds]
            ax.scatter(cs, as_, color="#1f6feb", zorder=3, label="Estándares")
            ax.plot(cs, as_, color="#1f6feb", linestyle="--", linewidth=1.1)
        abs_m = r0.get("abs_muestra")
        if abs_m is not None:
            c_interp = r0.get("conc_muestra")
            if c_interp is None and stds:
                c_interp = an.cuantificacion(stds, abs_m).get("conc_interp")
            if c_interp is not None:
                ax.scatter([c_interp], [clamp_saturacion(abs_m)],
                           color="#dc2626", s=55, zorder=4, label="Muestra")
        ax.set_xlabel("Concentración")
        ax.set_ylabel("Absorbancia (A)")
        ax.legend(fontsize=8, loc="best")
    elif modo == "multi" and resultados:
        r0 = resultados[0]
        celdas = r0.get("celdas") or []
        etqs = [f"{c.get('etiqueta', '')} ({c.get('wl', '')} nm)" for c in celdas]
        vals = [clamp_saturacion(c.get("abs")) or 0.0 for c in celdas]
        if etqs:
            ax.bar(etqs, vals, color="#1f6feb", width=0.5)
        ax.set_ylabel("Absorbancia (A)")
    elif modo == "photometrics" and resultados:
        vals = [clamp_saturacion(r.get("abs")) or 0.0 for r in resultados]
        nombres = [str(e) for e in etiquetas]
        ax.bar(nombres, vals, color="#059669", width=0.45)
        ax.set_ylabel("Absorbancia (A)")

    ax.grid(True, linestyle=":", alpha=0.5, color="#94a3b8")


def _crear_pagina_pdf(
    pdf: PdfPages,
    modo: str,
    titulo: str,
    subtitulo: str,
    resultados: Sequence[Dict],
    etiquetas: Sequence[str],
    cabecera_tabla: Sequence[str],
    filas_tabla: Sequence[Sequence[str]],
    analisis_dict: Dict,
) -> None:
    fig = Figure(figsize=(8.27, 11.69), dpi=150)  # A4 vertical
    fig.patch.set_facecolor("#ffffff")

    # 1. Encabezado
    fig.text(0.06, 0.955, "Programa Maestro — Espectrofotómetro Jenway 6705",
             fontsize=13, fontweight="bold", color="#0f172a")
    fig.text(0.06, 0.935, titulo, fontsize=11, fontweight="bold", color="#1e40af")
    fig.text(0.06, 0.918, subtitulo, fontsize=8.5, color="#475569")

    # 2. Gráfico principal
    ax_plot = fig.add_axes([0.10, 0.56, 0.84, 0.32])
    _dibujar_grafico_en_eje(ax_plot, modo, resultados, etiquetas)
    ax_plot.set_title(f"{titulo} — {ETIQUETAS_MODO.get(modo, modo)}", fontsize=10)

    # 3. Resumen analítico y extracto de datos
    ax_info = fig.add_axes([0.06, 0.05, 0.88, 0.44])
    ax_info.axis("off")

    lineas_txt: List[str] = ["MÉTRICAS ANALÍTICAS:"]
    if analisis_dict:
        for k, v in analisis_dict.items():
            lineas_txt.append(f"  • {k}: {v}")
    else:
        lineas_txt.append("  (Sin métricas adicionales)")

    lineas_txt.append("")
    total_filas = len(filas_tabla)
    max_mostrar = 22
    lineas_txt.append(
        f"PUNTOS DE DATOS (mostrando {min(total_filas, max_mostrar)} de {total_filas} filas):"
    )
    if cabecera_tabla:
        lineas_txt.append("  " + " | ".join(f"{str(c):<16}" for c in cabecera_tabla[:5]))
        lineas_txt.append("  " + "-" * min(85, 19 * len(cabecera_tabla[:5])))
    for fila in filas_tabla[:max_mostrar]:
        lineas_txt.append("  " + " | ".join(f"{str(c):<16}" for c in fila[:5]))
    if total_filas > max_mostrar:
        lineas_txt.append(f"  ... ({total_filas - max_mostrar} filas adicionales omitidas en el resumen impreso)")

    ax_info.text(
        0.0, 0.98, "\n".join(lineas_txt),
        va="top", ha="left", fontsize=8, family="monospace", color="#1e293b",
    )

    pie = f"Generado el {datetime.now().strftime('%d/%m/%Y %H:%M:%S')} · Jenway 6705"
    fig.text(0.06, 0.02, pie, fontsize=7.5, color="#64748b")

    pdf.savefig(fig)
    plt.close(fig)


def exportar_vista_pdf(
    ruta_pdf: str,
    modo: str,
    resultados: Sequence[Dict],
    etiquetas: Sequence[str],
    titulo: str = "Reporte Espectral",
    usuario: str = "",
    fecha: str = "",
) -> str:
    """Exporta la vista activa (una o varias muestras superpuestas) a un archivo PDF."""
    if not resultados:
        raise ValueError("No hay resultados cargados para exportar a PDF.")

    try:
        cab, filas = filas_para(modo, resultados[0])
    except Exception:
        cab, filas = ["Columna", "Valor"], []

    analisis_dict = _analisis_por_modo(modo, [(None, modo, r) for r in resultados])
    subtitulo = (
        f"Modo: {ETIQUETAS_MODO.get(modo, modo)}   |   "
        f"Usuario: {usuario or '—'}   |   "
        f"Fecha: {fecha or '—'}   |   "
        f"Muestras: {len(resultados)}"
    )
    with PdfPages(ruta_pdf) as pdf:
        _crear_pagina_pdf(
            pdf=pdf,
            modo=modo,
            titulo=titulo,
            subtitulo=subtitulo,
            resultados=resultados,
            etiquetas=etiquetas,
            cabecera_tabla=cab,
            filas_tabla=filas,
            analisis_dict=analisis_dict,
        )
    return ruta_pdf


def exportar_tarjeta_pdf(tarjeta: Tarjeta, ruta_pdf: str) -> int:
    """Exporta todos los métodos decodificables de una tarjeta o sesión serie a un PDF consolidado."""
    grupos = [(m, dec) for m, dec in _agrupar(tarjeta) if dec]
    if not grupos:
        raise ValueError("La tarjeta no contiene métodos con datos decodificables.")

    paginas = 0
    with PdfPages(ruta_pdf) as pdf:
        for m, dec in grupos:
            modo = dec[0][1] or m.modo
            rs = [r for _, _, r in dec]
            etqs = [(s.nombre if s and s.nombre else f"#{i + 1}") for i, (s, _, _) in enumerate(dec)]
            try:
                cab, filas = filas_para(modo, rs[0])
            except Exception:
                cab, filas = [], []
            analisis_dict = _analisis_por_modo(modo, dec)
            subtitulo = (
                f"Modo: {ETIQUETAS_MODO.get(modo, modo)}   |   "
                f"Usuario: {m.usuario or '—'}   |   "
                f"Fecha: {m.fecha or '—'}   |   "
                f"Archivo: {m.filename or 'Sesión en vivo'}"
            )
            _crear_pagina_pdf(
                pdf=pdf,
                modo=modo,
                titulo=m.nombre or "Método",
                subtitulo=subtitulo,
                resultados=rs,
                etiquetas=etqs,
                cabecera_tabla=cab,
                filas_tabla=filas,
                analisis_dict=analisis_dict,
            )
            paginas += 1
    return paginas
