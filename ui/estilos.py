# -*- coding: utf-8 -*-
"""Temas (QSS + estilo matplotlib) del Programa Maestro — Jenway 6705."""
from __future__ import annotations

from typing import Optional
import matplotlib as mpl

# --- paleta base ---
AZUL = "#3b82f6"
AZUL_HOVER = "#2563eb"
VERDE = "#10b981"
VERDE_HOVER = "#34d399"

_OSCURO = f"""
* {{
    font-family: 'Segoe UI', 'Inter', Arial, sans-serif;
    font-size: 12px;
}}
QMainWindow, QWidget {{
    background: #11161d;
    color: #e2e8f0;
}}
QLabel, QCheckBox {{
    background: transparent;
}}
QMenuBar {{
    background: #0b0f14;
    color: #cbd5e1;
    border-bottom: 1px solid #1e293b;
    padding: 2px 6px;
}}
QMenuBar::item {{
    padding: 4px 10px;
    border-radius: 4px;
}}
QMenuBar::item:selected {{
    background: {AZUL};
    color: #ffffff;
}}
QMenu {{
    background: #161d26;
    color: #e2e8f0;
    border: 1px solid #2a3646;
    border-radius: 6px;
    padding: 4px;
}}
QMenu::item {{
    padding: 6px 24px 6px 12px;
    border-radius: 4px;
}}
QMenu::item:selected {{
    background: {AZUL};
    color: #ffffff;
}}
QMenu::separator {{
    height: 1px;
    background: #263140;
    margin: 4px 6px;
}}
QToolBar {{
    background: #161d26;
    border: 1px solid #263140;
    border-radius: 6px;
    spacing: 4px;
    padding: 2px 4px;
}}
QToolBar QToolButton {{
    background: transparent;
    border-radius: 4px;
    padding: 3px;
}}
QToolBar QToolButton:hover {{
    background: #263140;
}}
QToolBar QToolButton:checked {{
    background: #1e3a5f;
    border: 1px solid {AZUL};
}}
QSplitter::handle {{
    background: #1e293b;
}}
QSplitter::handle:horizontal {{
    width: 3px;
}}
QSplitter::handle:hover {{
    background: {AZUL};
}}

/* Barra superior de navegación y acciones rápidas */
#Sidebar {{
    background: #0d1218;
    border-bottom: 1px solid #1e293b;
}}
#Sidebar QPushButton {{
    background: #161d26;
    color: #cbd5e1;
    padding: 6px 12px;
    border: 1px solid #263140;
    border-radius: 6px;
    font-weight: 500;
}}
#Sidebar QPushButton:hover {{
    background: #1f2937;
    color: #ffffff;
    border-color: #3b495e;
}}
#Sidebar QPushButton:checked {{
    background: #1e3a5f;
    color: #ffffff;
    border: 1px solid {AZUL};
    font-weight: 600;
}}
QLabel#Titulo {{
    font-size: 15px;
    font-weight: 700;
    color: #f8fafc;
    letter-spacing: 0.3px;
}}
QLabel#SubtituloMarca {{
    background: #162234;
    color: #60a5fa;
    border: 1px solid #233854;
    border-radius: 9px;
    padding: 2px 8px;
    font-size: 11px;
    font-weight: 600;
}}
QLabel#BadgeCursor {{
    background: #161d26;
    color: #fbbf24;
    border: 1px solid #2a3646;
    border-radius: 5px;
    padding: 3px 8px;
    font-family: 'Consolas', monospace;
    font-size: 11px;
}}

/* Tarjetas QGroupBox */
QGroupBox {{
    background: #151b23;
    border: 1px solid #242f3d;
    border-radius: 8px;
    margin-top: 12px;
    padding: 10px 8px 8px 8px;
    font-weight: 600;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 6px;
    color: #94a3b8;
    font-size: 11px;
    font-weight: 600;
}}

/* Listas, Árboles y Tablas */
QListWidget, QTableWidget, QTableView, QTreeWidget {{
    background: #0f141a;
    border: 1px solid #242f3d;
    border-radius: 6px;
    gridline-color: #1e293b;
    outline: none;
    selection-background-color: {AZUL};
    selection-color: #ffffff;
}}
QTabWidget::pane {{
    background: #151b23;
    border: 1px solid #242f3d;
    border-radius: 6px;
    top: -1px;
}}
QListWidget::item, QTreeWidget::item {{
    padding: 4px 6px;
    border-radius: 4px;
}}
QListWidget::item:selected, QTableWidget::item:selected, QTableView::item:selected,
QTreeWidget::item:selected {{
    background: {AZUL};
    color: #ffffff;
}}
QListWidget::item:hover, QTreeWidget::item:hover {{
    background: #1c2532;
}}

/* Entradas y Combos */
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QPlainTextEdit {{
    background: #0f141a;
    color: #f1f5f9;
    border: 1px solid #2a3646;
    border-radius: 5px;
    padding: 4px 8px;
}}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus, QPlainTextEdit:focus {{
    border: 1px solid {AZUL};
    background: #131a22;
}}
QComboBox::drop-down {{
    border: none;
    width: 20px;
}}
QComboBox QAbstractItemView {{
    background: #161d26;
    color: #f1f5f9;
    border: 1px solid #2a3646;
    selection-background-color: {AZUL};
    selection-color: #ffffff;
}}

/* Cabeceras de Tabla */
QHeaderView::section {{
    background: #19212c;
    color: #cbd5e1;
    padding: 5px 8px;
    border: none;
    border-right: 1px solid #242f3d;
    border-bottom: 1px solid #242f3d;
    font-weight: 600;
}}

/* Pestañas */
QTabBar::tab {{
    background: #161d26;
    color: #94a3b8;
    padding: 7px 14px;
    border: 1px solid #242f3d;
    border-bottom: none;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    margin-right: 3px;
    font-weight: 500;
}}
QTabBar::tab:hover {{
    background: #1e2734;
    color: #e2e8f0;
}}
QTabBar::tab:selected {{
    background: {AZUL};
    color: #ffffff;
    border-color: {AZUL};
    font-weight: 600;
}}

/* Botones */
QPushButton {{
    background: #1c2532;
    color: #e2e8f0;
    border: 1px solid #2d3b4e;
    border-radius: 6px;
    padding: 6px 11px;
    font-weight: 500;
}}
QPushButton:hover {{
    background: #263244;
    border-color: #3d4f68;
}}
QPushButton:pressed {{
    background: #161f2b;
}}
QPushButton:checked {{
    background: #1e3a5f;
    color: #ffffff;
    border-color: {AZUL};
}}
QPushButton:disabled {{
    background: #141920;
    color: #4b5563;
    border-color: #1f2733;
}}
#BtnExportar {{
    background: {VERDE};
    color: #042f1e;
    font-weight: 700;
    border: none;
}}
#BtnExportar:hover {{
    background: {VERDE_HOVER};
}}
#BtnExportar:disabled {{
    background: #163029;
    color: #4b6b60;
}}
#BtnPrimario {{
    background: {AZUL};
    color: #ffffff;
    font-weight: 600;
    border: none;
}}
#BtnPrimario:hover {{
    background: {AZUL_HOVER};
}}

/* Estados y Avisos */
#EstadoConectado {{
    color: {VERDE_HOVER};
    font-weight: 700;
}}
QLabel#BadgeEstadoSerie {{
    background: #161d26;
    color: #94a3b8;
    border: 1px solid #263140;
    border-radius: 10px;
    padding: 3px 10px;
    font-size: 11px;
    font-weight: 600;
}}
QLabel#BadgeEstadoSerieConectado {{
    background: #063928;
    color: #34d399;
    border: 1px solid #10b981;
    border-radius: 10px;
    padding: 3px 10px;
    font-size: 11px;
    font-weight: 700;
}}
QLabel#ayudaOperacion, QLabel#resumenCadena, QLabel#EstadoSerieDesconectado {{
    color: #94a3b8;
    font-size: 11px;
}}
QLabel#resumenBanda {{
    background: #0f141a;
    color: #60a5fa;
    border: 1px solid #233854;
    border-radius: 5px;
    padding: 5px 7px;
    font-size: 11px;
}}
QLabel#avisoProcesado {{
    background: #2b1f0e;
    color: #fbbf24;
    border: 1px solid #78350f;
    border-radius: 5px;
    padding: 5px 8px;
    font-size: 11px;
}}

/* Barras de desplazamiento modernas */
QScrollBar:vertical {{
    background: #0f141a;
    width: 8px;
    margin: 0px;
    border: none;
    border-radius: 4px;
}}
QScrollBar::handle:vertical {{
    background: #2d3b4e;
    min-height: 24px;
    border-radius: 4px;
}}
QScrollBar::handle:vertical:hover {{
    background: #475569;
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0px;
    width: 0px;
    background: none;
    border: none;
}}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
    background: none;
}}
QScrollBar:horizontal {{
    background: #0f141a;
    height: 8px;
    margin: 0px;
    border: none;
    border-radius: 4px;
}}
QScrollBar::handle:horizontal {{
    background: #2d3b4e;
    min-width: 24px;
    border-radius: 4px;
}}
QScrollBar::handle:horizontal:hover {{
    background: #475569;
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    height: 0px;
    width: 0px;
    background: none;
    border: none;
}}
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{
    background: none;
}}
QScrollArea {{
    border: none;
    background: transparent;
}}
QDockWidget {{
    background: #151b23;
}}
QDockWidget::title {{
    background: #0d1218;
    color: #94a3b8;
    padding: 6px 8px;
    font-weight: 600;
}}
QStatusBar {{
    background: #0b0f14;
    color: #94a3b8;
    border-top: 1px solid #1e293b;
    font-size: 11.5px;
}}
"""

_CLARO = f"""
* {{
    font-family: 'Segoe UI', 'Inter', Arial, sans-serif;
    font-size: 12px;
}}
QMainWindow, QWidget {{
    background: #f1f5f9;
    color: #0f172a;
}}
QLabel, QCheckBox {{
    background: transparent;
}}
QMenuBar {{
    background: #ffffff;
    color: #1e293b;
    border-bottom: 1px solid #cbd5e1;
    padding: 2px 6px;
}}
QMenuBar::item {{
    padding: 4px 10px;
    border-radius: 4px;
}}
QMenuBar::item:selected {{
    background: {AZUL};
    color: #ffffff;
}}
QMenu {{
    background: #ffffff;
    color: #0f172a;
    border: 1px solid #cbd5e1;
    border-radius: 6px;
    padding: 4px;
}}
QMenu::item {{
    padding: 6px 24px 6px 12px;
    border-radius: 4px;
}}
QMenu::item:selected {{
    background: {AZUL};
    color: #ffffff;
}}
QMenu::separator {{
    height: 1px;
    background: #e2e8f0;
    margin: 4px 6px;
}}
QToolBar {{
    background: #ffffff;
    border: 1px solid #cbd5e1;
    border-radius: 6px;
    spacing: 4px;
    padding: 2px 4px;
}}
QToolBar QToolButton {{
    background: transparent;
    border-radius: 4px;
    padding: 3px;
}}
QToolBar QToolButton:hover {{
    background: #e2e8f0;
}}
QToolBar QToolButton:checked {{
    background: #dbeafe;
    border: 1px solid {AZUL};
}}
QSplitter::handle {{
    background: #cbd5e1;
}}
QSplitter::handle:horizontal {{
    width: 3px;
}}
QSplitter::handle:hover {{
    background: {AZUL};
}}

/* Barra superior */
#Sidebar {{
    background: #ffffff;
    border-bottom: 1px solid #cbd5e1;
}}
#Sidebar QPushButton {{
    background: #f8fafc;
    color: #334155;
    padding: 6px 12px;
    border: 1px solid #cbd5e1;
    border-radius: 6px;
    font-weight: 500;
}}
#Sidebar QPushButton:hover {{
    background: #e2e8f0;
    color: #0f172a;
}}
#Sidebar QPushButton:checked {{
    background: #dbeafe;
    color: #1d4ed8;
    border: 1px solid {AZUL};
    font-weight: 600;
}}
QLabel#Titulo {{
    font-size: 15px;
    font-weight: 700;
    color: #0f172a;
}}
QLabel#SubtituloMarca {{
    background: #eff6ff;
    color: #1d4ed8;
    border: 1px solid #bfdbfe;
    border-radius: 9px;
    padding: 2px 8px;
    font-size: 11px;
    font-weight: 600;
}}
QLabel#BadgeCursor {{
    background: #f8fafc;
    color: #b45309;
    border: 1px solid #cbd5e1;
    border-radius: 5px;
    padding: 3px 8px;
    font-family: 'Consolas', monospace;
    font-size: 11px;
}}

/* Tarjetas QGroupBox */
QGroupBox {{
    background: #ffffff;
    border: 1px solid #cbd5e1;
    border-radius: 8px;
    margin-top: 12px;
    padding: 10px 8px 8px 8px;
    font-weight: 600;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 6px;
    color: #475569;
    font-size: 11px;
    font-weight: 600;
}}

/* Listas, Árboles y Tablas */
QListWidget, QTableWidget, QTableView, QTreeWidget {{
    background: #ffffff;
    border: 1px solid #cbd5e1;
    border-radius: 6px;
    gridline-color: #e2e8f0;
    outline: none;
    selection-background-color: {AZUL};
    selection-color: #ffffff;
}}
QTabWidget::pane {{
    background: #ffffff;
    border: 1px solid #cbd5e1;
    border-radius: 6px;
    top: -1px;
}}
QListWidget::item, QTreeWidget::item {{
    padding: 4px 6px;
    border-radius: 4px;
}}
QListWidget::item:selected, QTableWidget::item:selected, QTableView::item:selected,
QTreeWidget::item:selected {{
    background: {AZUL};
    color: #ffffff;
}}
QListWidget::item:hover, QTreeWidget::item:hover {{
    background: #f1f5f9;
}}

/* Entradas y Combos */
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QPlainTextEdit {{
    background: #ffffff;
    color: #0f172a;
    border: 1px solid #cbd5e1;
    border-radius: 5px;
    padding: 4px 8px;
}}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus, QPlainTextEdit:focus {{
    border: 1px solid {AZUL};
}}
QComboBox::drop-down {{
    border: none;
    width: 20px;
}}
QComboBox QAbstractItemView {{
    background: #ffffff;
    color: #0f172a;
    border: 1px solid #cbd5e1;
    selection-background-color: {AZUL};
    selection-color: #ffffff;
}}

/* Cabeceras de Tabla */
QHeaderView::section {{
    background: #f8fafc;
    color: #334155;
    padding: 5px 8px;
    border: none;
    border-right: 1px solid #cbd5e1;
    border-bottom: 1px solid #cbd5e1;
    font-weight: 600;
}}

/* Pestañas */
QTabBar::tab {{
    background: #e2e8f0;
    color: #475569;
    padding: 7px 14px;
    border: 1px solid #cbd5e1;
    border-bottom: none;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    margin-right: 3px;
    font-weight: 500;
}}
QTabBar::tab:hover {{
    background: #f1f5f9;
    color: #0f172a;
}}
QTabBar::tab:selected {{
    background: {AZUL};
    color: #ffffff;
    border-color: {AZUL};
    font-weight: 600;
}}

/* Botones */
QPushButton {{
    background: #ffffff;
    color: #1e293b;
    border: 1px solid #cbd5e1;
    border-radius: 6px;
    padding: 6px 11px;
    font-weight: 500;
}}
QPushButton:hover {{
    background: #f1f5f9;
    border-color: #94a3b8;
}}
QPushButton:pressed {{
    background: #e2e8f0;
}}
QPushButton:checked {{
    background: #dbeafe;
    color: #1d4ed8;
    border-color: {AZUL};
}}
QPushButton:disabled {{
    background: #f8fafc;
    color: #94a3b8;
    border-color: #e2e8f0;
}}
#BtnExportar {{
    background: {VERDE};
    color: #042f1e;
    font-weight: 700;
    border: none;
}}
#BtnExportar:hover {{
    background: #059669;
    color: #ffffff;
}}
#BtnExportar:disabled {{
    background: #d1fae5;
    color: #6ee7b7;
}}
#BtnPrimario {{
    background: {AZUL};
    color: #ffffff;
    font-weight: 600;
    border: none;
}}
#BtnPrimario:hover {{
    background: {AZUL_HOVER};
}}

/* Estados y Avisos */
#EstadoConectado {{
    color: #059669;
    font-weight: 700;
}}
QLabel#BadgeEstadoSerie {{
    background: #f1f5f9;
    color: #475569;
    border: 1px solid #cbd5e1;
    border-radius: 10px;
    padding: 3px 10px;
    font-size: 11px;
    font-weight: 600;
}}
QLabel#BadgeEstadoSerieConectado {{
    background: #d1fae5;
    color: #065f46;
    border: 1px solid #10b981;
    border-radius: 10px;
    padding: 3px 10px;
    font-size: 11px;
    font-weight: 700;
}}
QLabel#ayudaOperacion, QLabel#resumenCadena, QLabel#EstadoSerieDesconectado {{
    color: #64748b;
    font-size: 11px;
}}
QLabel#resumenBanda {{
    background: #eff6ff;
    color: #1d4ed8;
    border: 1px solid #bfdbfe;
    border-radius: 5px;
    padding: 5px 7px;
    font-size: 11px;
}}
QLabel#avisoProcesado {{
    background: #fef3c7;
    color: #92400e;
    border: 1px solid #fde68a;
    border-radius: 5px;
    padding: 5px 8px;
    font-size: 11px;
}}
/* Barras de desplazamiento modernas */
QScrollBar:vertical {{
    background: #f1f5f9;
    width: 8px;
    margin: 0px;
    border: none;
    border-radius: 4px;
}}
QScrollBar::handle:vertical {{
    background: #cbd5e1;
    min-height: 24px;
    border-radius: 4px;
}}
QScrollBar::handle:vertical:hover {{
    background: #94a3b8;
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0px;
    width: 0px;
    background: none;
    border: none;
}}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
    background: none;
}}
QScrollBar:horizontal {{
    background: #f1f5f9;
    height: 8px;
    margin: 0px;
    border: none;
    border-radius: 4px;
}}
QScrollBar::handle:horizontal {{
    background: #cbd5e1;
    min-width: 24px;
    border-radius: 4px;
}}
QScrollBar::handle:horizontal:hover {{
    background: #94a3b8;
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    height: 0px;
    width: 0px;
    background: none;
    border: none;
}}
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{
    background: none;
}}
QScrollArea {{
    border: none;
    background: transparent;
}}
QDockWidget {{
    background: #f1f5f9;
}}
QDockWidget::title {{
    background: #ffffff;
    color: #475569;
    padding: 6px 8px;
    font-weight: 600;
}}
QStatusBar {{
    background: #ffffff;
    color: #475569;
    border-top: 1px solid #cbd5e1;
    font-size: 11.5px;
}}
"""


def qss(tema: str) -> str:
    if tema == "dark":
        return _OSCURO
    return _CLARO


def colores(tema: str):
    """(fondo_fig, fondo_ejes, texto, rejilla) para matplotlib."""
    if tema == "dark":
        return "#151b23", "#0f141a", "#e2e8f0", "#263140"
    return "#ffffff", "#f8fafc", "#0f172a", "#cbd5e1"


def aplicar_mpl(fig, ax, tema: str, grid_axis: Optional[str] = None):
    """Aplica colores del tema a una figura/eje de matplotlib, incluyendo
    leyenda, anotaciones (`ax.texts`) y cajas de texto."""
    fbg, abg, txt, grid = colores(tema)
    fig.patch.set_facecolor(fbg)
    ax.set_facecolor(abg)
    for nombre_espina, s in ax.spines.items():
        s.set_color(grid)
        if nombre_espina in ("top", "right"):
            s.set_alpha(0.35)
    ax.tick_params(colors=txt, labelsize=9)
    ax.xaxis.label.set_color(txt)
    ax.yaxis.label.set_color(txt)
    ax.title.set_color(txt)
    ax.title.set_fontweight("600")
    if grid_axis in ("x", "y"):
        ax.grid(True, axis=grid_axis, color=grid, linestyle="--", alpha=0.45)
        ax.grid(False, axis=("y" if grid_axis == "x" else "x"))
    else:
        ax.grid(True, color=grid, linestyle="--", alpha=0.45)

    # Leyenda legible tanto en tema oscuro como en tema claro
    leg = ax.get_legend()
    if leg is not None:
        frame = leg.get_frame()
        frame.set_facecolor(fbg)
        frame.set_edgecolor(grid)
        frame.set_alpha(0.94)
        for t in leg.get_texts():
            t.set_color(txt)

    # Todas las anotaciones y etiquetas sobre el lienzo (picos, FWHM, barras, Conc.)
    for t in ax.texts:
        t.set_color(txt)
        caja = t.get_bbox_patch()
        if caja is not None:
            caja.set_facecolor(fbg)
            if not getattr(t, "_borde_personalizado", False):
                caja.set_edgecolor(grid)
            caja.set_alpha(0.92)