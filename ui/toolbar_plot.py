# -*- coding: utf-8 -*-
"""Panel de gráfico interactivo del Programa Maestro — Jenway 6705.

Encapsula en un solo widget reutilizable:

  * el lienzo de matplotlib,
  * la barra de herramientas nativa (zoom rectangular, desplazar, vista inicial,
    guardar imagen) con las etiquetas en español,
  * los controles de unidades (%Transmitancia <-> Absorbancia), de vista
    (series superpuestas o apiladas) y de marcado de picos,
  * una cruz (crosshair) que se ENGANCHA al punto de medida más cercano y marca
    ese punto en cada serie, con la lectura de todas las series a la vez en la
    barra de estado (multi-cursor, estilo Spectragryph),
  * menú contextual en el lienzo (vista inicial, ajustar a los datos, guardar y
    copiar imagen).

Sobre el cursor: se actualiza la cruz y se pide un redibujado (`draw_idle`), que
matplotlib agrupa. NO se usa blitting manual: `FigureCanvasQTAgg` hereda un
`blit()` vacío, de modo que guardar y re-pegar el fondo con `restore_region`
dejaba en pantalla la imagen ANTERIOR al zoom (las barras "desaparecían" al mover
el ratón). Un redibujado completo tarda ~15-20 ms incluso con 2 espectros de
7.101 puntos, así que no hace falta.

La parte "pura" (qué se dibuja) vive en `serie_para()` y `desplazamientos()`,
para poder probarla sin crear widgets.
"""
from __future__ import annotations

import io
import math
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

from PySide6.QtCore import QMimeData, Qt, Signal
from PySide6.QtGui import QImage
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QCheckBox,
                               QComboBox, QDoubleSpinBox, QFileDialog,
                               QGroupBox, QHBoxLayout, QLabel, QLineEdit,
                               QMenu, QPushButton, QSizePolicy, QSpinBox,
                               QTableWidget, QTableWidgetItem, QVBoxLayout,
                               QWidget)

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qtagg import NavigationToolbar2QT
from matplotlib.figure import Figure

from jenway67 import analisis as an
from jenway67.utilidades import clamp_saturacion
from ui import estilos

# Etiquetas en español de las acciones de la barra. Las claves son los nombres
# de los callbacks con que NavigationToolbar2QT indexa `_actions`.
_TOOLBAR_ES = {
    "home": "Vista inicial",
    "back": "Atrás",
    "forward": "Adelante",
    "pan": "Desplazar (arrastrar; botón derecho = zoom)",
    "zoom": "Zoom rectangular (arrastrar)",
    "save_figure": "Guardar imagen…",
}
# Acciones que no aportan aquí (edición de ejes / márgenes).
_TOOLBAR_QUITAR = ("configure_subplots", "edit_parameters")

UNIDADES = ("abs", "t")
_ETIQUETA_Y = {"abs": "Absorbancia", "t": "Transmitancia (%)"}
_ABREV_X = {"Longitud de onda (nm)": "nm", "Tiempo (s)": "s", "Lectura": ""}
COLOR_CURSOR = "#f39c12"
MAX_SERIES_CURSOR = 6

# Paleta fija: cada serie conserva su color entre redibujados y entre gráficos.
_PALETA = ("#3d8bfd", "#e67e22", "#2ecc71", "#e74c3c", "#9b59b6",
           "#16a085", "#f1c40f", "#e84393", "#00b894", "#636e72")


def color_serie(indice: int) -> str:
    return _PALETA[indice % len(_PALETA)]


def _valor(v) -> float:
    """Valor representable: la absorbancia saturada se muestra clampada a 3.000
    (igual que el display del 6705) y lo no finito queda como nan."""
    a = clamp_saturacion(v)
    return float(a) if isinstance(a, (int, float)) and np.isfinite(a) else float("nan")


def serie_para(modo: str, r: dict, unidad: str = "abs") -> Tuple[np.ndarray, np.ndarray, str, str]:
    """(x, y, xlabel, ylabel) de un resultado decodificado en la unidad pedida.

    Cubre los modos con eje X natural (espectro, cinética, multi-longitud y
    fotometría). La cuantificación (Absorbancia vs Concentración) se dibuja
    aparte, en `_dibujar_calibracion`."""
    u = unidad if unidad in UNIDADES else "abs"
    if modo == "spectrum":
        x = np.array([p[0] for p in r["puntos"]], dtype=float)
        y = np.array([(p[2] if u == "abs" else p[1]) for p in r["puntos"]], dtype=float)
        return x, y, "Longitud de onda (nm)", _ETIQUETA_Y[u]
    if modo == "kinetics":
        x = an.tiempos_de(r)
        y = np.array([(s[2] if u == "abs" else s[1]) for s in r["serie"]], dtype=float)
        return x, y, "Tiempo (s)", _ETIQUETA_Y[u]
    if modo == "multi":
        x = np.array([float(c.get("wl", 0)) for c in r["celdas"]], dtype=float)
        if u == "abs":
            y = np.array([_valor(c.get("abs")) for c in r["celdas"]], dtype=float)
        else:
            y = np.array([c.get("t") for c in r["celdas"]], dtype=float)
        return x, y, "Longitud de onda (nm)", _ETIQUETA_Y[u]
    if modo == "photometrics":
        y = _valor(r.get("abs")) if u == "abs" else r.get("t")
        return np.array([0.0]), np.array([y], dtype=float), "Lectura", _ETIQUETA_Y[u]
    return np.array([]), np.array([]), "", ""


def desplazamientos(n: int, paso: float = 1.0) -> List[float]:
    """Desplazamiento vertical de cada serie en la vista apilada (0, paso, 2·paso…)."""
    return [i * float(paso) for i in range(max(int(n), 0))]


class PanelGrafico(QWidget):
    """Lienzo + barra de herramientas + controles + lectura de coordenadas.

    Señales:
      * `coordenadas(str)`: texto a mostrar en la barra de estado mientras el
        cursor está sobre el gráfico (cadena vacía al salir).
      * `mensaje(str)`: avisos puntuales (imagen guardada/copiada, errores)."""

    coordenadas = Signal(str)
    mensaje = Signal(str)
    marcados = Signal()          # peticion de graficar los puntos marcados aparte

    def __init__(self, parent=None, tema: str = "dark", con_marcas: bool = True):
        super().__init__(parent)
        self.tema = tema
        #: `con_marcas=False` = panel de solo lectura (p. ej. el gráfico reducido
        #: de puntos marcados): no deja marcar ni muestra los controles de cinética.
        self.con_marcas = con_marcas
        self._modo = ""
        self._resultados: List[dict] = []
        self._etiquetas: List[str] = []
        self._titulo = ""
        self._series: List[Tuple[str, np.ndarray, np.ndarray]] = []
        self._offsets: List[float] = []
        self._lineas: List = []
        self._marcas: List[float] = []
        self._banda: Optional[Tuple[float, float]] = None
        self._apilable = False
        self._cursor = None
        self._cursor_puntos = None
        self._ultimo = ""
        self._etq_x = ""
        self._etq_y = "Abs"

        v = QVBoxLayout(self)
        v.setContentsMargins(4, 4, 4, 4)
        v.setSpacing(4)

        self.fig = Figure(figsize=(6, 3.6))
        self.canvas = FigureCanvas(self.fig)
        self.ax = self.fig.add_subplot(111)
        self.toolbar = NavigationToolbar2QT(self.canvas, self, coordinates=False)
        from PySide6.QtCore import QSize
        self.toolbar.setIconSize(QSize(18, 18))
        self.toolbar.setMinimumWidth(225)
        self._traducir_toolbar()

        ctl = QHBoxLayout()
        ctl.setContentsMargins(2, 2, 2, 2)
        ctl.setSpacing(4)
        ctl.addWidget(self.toolbar)
        self.lbl_unidad = QLabel("Unid.:")
        ctl.addWidget(self.lbl_unidad)
        self.combo_unidad = QComboBox()
        self.combo_unidad.addItems(["Absorbancia", "Transmitancia (%T)"])
        self.combo_unidad.setToolTip("Unidad del eje Y")
        self.combo_unidad.currentIndexChanged.connect(self._al_unidad_cambiada)
        ctl.addWidget(self.combo_unidad)
        self.btn_vista = QPushButton("Superpuesta")
        self.btn_vista.setCheckable(True)
        self.btn_vista.setToolTip("Alternar entre series superpuestas y apiladas (desplazadas)")
        self.btn_vista.toggled.connect(self._al_alternar_vista)
        ctl.addWidget(self.btn_vista)
        self.chk_picos = QCheckBox("Picos")
        self.chk_picos.setChecked(True)
        self.chk_picos.setToolTip("Señala los máximos locales del espectro y su longitud de onda")
        self.chk_picos.toggled.connect(self._al_cambiar_unidad)
        ctl.addWidget(self.chk_picos)
        self.lbl_prom = QLabel("Prom.:")
        ctl.addWidget(self.lbl_prom)
        self.spin_prominencia = QDoubleSpinBox()
        self.spin_prominencia.setDecimals(3)
        self.spin_prominencia.setRange(0.001, 1.0)
        self.spin_prominencia.setSingleStep(0.005)
        self.spin_prominencia.setValue(0.020)
        self.spin_prominencia.setFixedWidth(72)
        self.spin_prominencia.setToolTip(
            "Umbral de prominencia relativa (fracción del rango de absorbancia; p. ej. 0.020 = 2 %)"
        )
        self.spin_prominencia.valueChanged.connect(self._al_cambiar_unidad)
        ctl.addWidget(self.spin_prominencia)
        self.chk_fwhm = QCheckBox("FWHM")
        self.chk_fwhm.setChecked(False)
        self.chk_fwhm.setToolTip("Mostrar anchura a media altura (FWHM en nm) junto a los picos")
        self.chk_fwhm.toggled.connect(self._al_cambiar_unidad)
        ctl.addWidget(self.chk_fwhm)
        # --- rango manual del eje Y (vacío = automático)
        self.lbl_y = QLabel("Y:")
        ctl.addWidget(self.lbl_y)
        self.txt_y_min = QLineEdit("")
        self.txt_y_min.setPlaceholderText("mín")
        self.txt_y_min.setFixedWidth(44)
        self.txt_y_min.setToolTip("Mínimo del eje Y (vacío = automático)")
        self.txt_y_min.editingFinished.connect(self._al_editar_y)
        ctl.addWidget(self.txt_y_min)
        self.txt_y_max = QLineEdit("")
        self.txt_y_max.setPlaceholderText("máx")
        self.txt_y_max.setFixedWidth(44)
        self.txt_y_max.setToolTip("Máximo del eje Y (vacío = automático)")
        self.txt_y_max.editingFinished.connect(self._al_editar_y)
        ctl.addWidget(self.txt_y_max)
        self.btn_y_auto = QPushButton("Auto")
        self.btn_y_auto.setToolTip("Volver al rango Y automático")
        self.btn_y_auto.clicked.connect(self._y_automatico)
        ctl.addWidget(self.btn_y_auto)
        ctl.addStretch(1)
        self.lbl_coord_live = QLabel("")
        self.lbl_coord_live.setObjectName("BadgeCursor")
        self.lbl_coord_live.setMinimumWidth(0)
        self.lbl_coord_live.setMaximumWidth(260)
        self.lbl_coord_live.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        self.lbl_coord_live.setVisible(False)
        ctl.addWidget(self.lbl_coord_live)
        v.addLayout(ctl)
        v.addWidget(self.canvas, 1)

        # --- cinética: marcas de puntos de interés + bitácora de absorbancias
        self.ctl_cinetica = QWidget()
        fila_kin = QHBoxLayout(self.ctl_cinetica)
        fila_kin.setContentsMargins(4, 2, 4, 0)
        fila_kin.addWidget(QLabel("Cinética:"))
        self.spin_intervalo = QSpinBox()
        self.spin_intervalo.setRange(1, 100000)
        self.spin_intervalo.setValue(30)
        self.spin_intervalo.setSuffix(" s")
        self.spin_intervalo.setToolTip("Intervalo entre marcas automáticas "
                                       "(p. ej. 30, 60, 90 s)")
        fila_kin.addWidget(self.spin_intervalo)
        self.btn_marcar_cada = QPushButton("Marcar cada")
        self.btn_marcar_cada.setToolTip("Añade una marca cada N segundos "
                                        "(30, 60, 90…) dentro del rango medido")
        self.btn_marcar_cada.clicked.connect(self._marcar_intervalo)
        fila_kin.addWidget(self.btn_marcar_cada)
        self.btn_borrar_marcas = QPushButton("Borrar marcas")
        self.btn_borrar_marcas.clicked.connect(self._borrar_marcas)
        fila_kin.addWidget(self.btn_borrar_marcas)
        self.btn_graficar_marcados = QPushButton("Graficar marcados")
        self.btn_graficar_marcados.setToolTip(
            "Dibuja un gráfico X-Y solo con los puntos marcados (tiempo vs "
            "absorbancia). Si eliges filas en la bitácora, dibuja solo esas.")
        self.btn_graficar_marcados.clicked.connect(self._pedir_graficar_marcados)
        fila_kin.addWidget(self.btn_graficar_marcados)
        self.btn_copiar_bitacora = QPushButton("📋 Copiar tabla")
        self.btn_copiar_bitacora.setToolTip(
            "Copia la bitácora al portapapeles con formato tabular (listo para pegar en Excel o Google Sheets con Ctrl+V). "
            "Si hay filas seleccionadas, copia solo esas.")
        self.btn_copiar_bitacora.clicked.connect(lambda: self._copiar_bitacora_clipboard())
        fila_kin.addWidget(self.btn_copiar_bitacora)
        self.btn_exportar_bitacora_xlsx = QPushButton("📊 Exportar .xlsx")
        self.btn_exportar_bitacora_xlsx.setToolTip(
            "Guarda la tabla de marcas de la bitácora en un archivo de Excel (.xlsx) con valores numéricos y formato.")
        self.btn_exportar_bitacora_xlsx.clicked.connect(lambda: self._exportar_bitacora_xlsx())
        fila_kin.addWidget(self.btn_exportar_bitacora_xlsx)
        self.btn_graficar_marcados.setEnabled(False)
        self.btn_copiar_bitacora.setEnabled(False)
        self.btn_exportar_bitacora_xlsx.setEnabled(False)
        fila_kin.addStretch(1)
        v.addWidget(self.ctl_cinetica)

        self.grupo_bitacora = QGroupBox("Bitácora de cinética (clic para marcar puntos)")
        vb = QVBoxLayout(self.grupo_bitacora)
        vb.setContentsMargins(4, 4, 4, 4)
        self.tabla_marcas = QTableWidget(0, 1)
        self.tabla_marcas.setMaximumHeight(130)
        self.tabla_marcas.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tabla_marcas.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tabla_marcas.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.tabla_marcas.horizontalHeader().setStretchLastSection(True)
        self.tabla_marcas.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tabla_marcas.customContextMenuRequested.connect(self._menu_contextual_bitacora)
        vb.addWidget(self.tabla_marcas)
        v.addWidget(self.grupo_bitacora)

        self.canvas.mpl_connect("motion_notify_event", self._al_mover)
        self.canvas.mpl_connect("axes_leave_event", self._al_salir)
        self.canvas.mpl_connect("button_press_event", self._al_click)
        self.canvas.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.canvas.customContextMenuRequested.connect(self._menu_contextual)
        self.limpiar()

    # ------------------------------------------------------------- API pública
    @property
    def unidad(self) -> str:
        return "t" if self.combo_unidad.currentIndex() == 1 else "abs"

    @property
    def marcar_picos(self) -> bool:
        return self.chk_picos.isChecked()

    def dibujar(self, modo: str, resultados: Sequence[dict],
                etiquetas: Optional[Sequence[str]] = None, titulo: str = ""):
        """Dibuja los resultados decodificados (varias muestras = varias series)."""
        modo = modo or ""
        if modo != self._modo:
            # Cambia el tipo de gráfico: el rango Y manual ya no tiene sentido.
            self.txt_y_min.setText("")
            self.txt_y_max.setText("")
            self._banda = None
        self._modo = modo
        res_desplegados = []
        etq_desplegadas = []
        for i, r in enumerate(resultados):
            etq = (etiquetas[i] if etiquetas and i < len(etiquetas) else f"#{i + 1}")
            if modo == "kinetics" and r and r.get("serie"):
                puntos = r.get("serie", [])
                tiempos = an.tiempos_de(r)
                if len(tiempos) >= 4 and len(tiempos) == len(puntos):
                    cortes = [0]
                    for k in range(1, len(tiempos)):
                        if tiempos[k] < tiempos[k - 1] or (tiempos[k] == 0.0 and tiempos[k - 1] > 0.0):
                            cortes.append(k)
                    if len(cortes) > 1:
                        cortes.append(len(tiempos))
                        for sub_idx in range(len(cortes) - 1):
                            ini = cortes[sub_idx]
                            fin = cortes[sub_idx + 1]
                            sub_serie = puntos[ini:fin]
                            sub_tiempos = list(tiempos[ini:fin])
                            r_sub = dict(r)
                            r_sub["serie"] = sub_serie
                            r_sub["tiempos"] = sub_tiempos
                            r_sub["n"] = len(sub_serie)
                            r_sub["celda"] = sub_idx + 1
                            res_desplegados.append(r_sub)
                            etq_desplegadas.append(f"{etq} (Carril {sub_idx + 1})")
                        continue
            res_desplegados.append(r)
            etq_desplegadas.append(etq)
        self._resultados = res_desplegados
        self._etiquetas = etq_desplegadas
        self._titulo = titulo or ""
        self._apilable = self._modo in ("spectrum", "kinetics")
        self._marcas = []
        self.btn_vista.setVisible(self._apilable)
        con_unidades = self._modo not in ("quantitation", "")
        self.combo_unidad.setVisible(con_unidades)
        self.lbl_unidad.setVisible(con_unidades)
        es_espectro = self._modo == "spectrum"
        self.chk_picos.setVisible(es_espectro)
        self.lbl_prom.setVisible(es_espectro)
        self.spin_prominencia.setVisible(es_espectro)
        self.chk_fwhm.setVisible(es_espectro)
        es_cinetica = self._modo == "kinetics" and self.con_marcas
        self.ctl_cinetica.setVisible(es_cinetica)
        self.grupo_bitacora.setVisible(es_cinetica)
        self._render()

    def limpiar(self):
        self._modo = ""
        self._resultados = []
        self._etiquetas = []
        self._series = []
        self._marcas = []
        self._banda = None
        self._render()
        self._emitir("")

    def sombrear_banda(self, x_a: float, x_b: float):
        """Sombrea en el gráfico la banda integrada entre `x_a` y `x_b`."""
        self._banda = (min(float(x_a), float(x_b)), max(float(x_a), float(x_b)))
        self._render()

    def limpiar_banda(self):
        """Elimina el sombreado de integración de banda."""
        self._banda = None
        self._render()

    def set_tema(self, tema: str):
        self.tema = tema
        self._colorear_iconos_toolbar()
        self._render()

    def ajustar_a_datos(self):
        """Reencuadra la vista a los datos (cómodo después de un zoom)."""
        self._render()

    # -------------------------------------------------------------- imagen
    def guardar_imagen(self):
        ruta, _ = QFileDialog.getSaveFileName(self, "Guardar imagen", "grafico.png",
                                              "PNG (*.png);;SVG (*.svg);;PDF (*.pdf)")
        if not ruta:
            return
        try:
            self.fig.savefig(ruta, dpi=150, bbox_inches="tight")
            self.mensaje.emit(f"Imagen guardada: {ruta}")
        except Exception as e:                                # pragma: no cover
            self.mensaje.emit(f"No se pudo guardar la imagen: {e}")

    def copiar_imagen(self):
        """Copia el gráfico al portapapeles como imagen."""
        try:
            buf = io.BytesIO()
            self.fig.savefig(buf, format="png", dpi=150, bbox_inches="tight")
            QApplication.clipboard().setImage(QImage.fromData(buf.getvalue(), "PNG"))
            self.mensaje.emit("Gráfico copiado al portapapeles.")
        except Exception as e:                                # pragma: no cover
            self.mensaje.emit(f"No se pudo copiar el gráfico: {e}")

    def _menu_contextual(self, pos):
        menu = QMenu(self)
        menu.addAction("Vista inicial", self.toolbar.home)
        menu.addAction("Ajustar a los datos", self.ajustar_a_datos)
        menu.addSeparator()
        menu.addAction("Guardar imagen…", self.guardar_imagen)
        menu.addAction("Copiar imagen", self.copiar_imagen)
        if self._apilable:
            menu.addSeparator()
            a = menu.addAction("Vista apilada")
            a.setCheckable(True)
            a.setChecked(self.btn_vista.isChecked())
            a.toggled.connect(self.btn_vista.setChecked)
        menu.exec(self.canvas.mapToGlobal(pos))

    # ----------------------------------------------------------------- lienzo
    def _traducir_toolbar(self):
        self.toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        acciones = getattr(self.toolbar, "_actions", None) or {}
        for clave, texto in _TOOLBAR_ES.items():
            a = acciones.get(clave)
            if a is not None:
                a.setText(texto)
                a.setToolTip(texto)
        for clave in _TOOLBAR_QUITAR:
            a = acciones.get(clave)
            if a is not None:
                self.toolbar.removeAction(a)
        self._colorear_iconos_toolbar()

    def _colorear_iconos_toolbar(self):
        """Recolorea los iconos de NavigationToolbar2QT para alto contraste según el tema."""
        from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
        color = QColor("#e2e8f0" if self.tema == "dark" else "#1e293b")
        acciones = getattr(self.toolbar, "_actions", None) or {}
        for a in acciones.values():
            if a is None:
                continue
            ico_base = getattr(a, "_icono_base", None)
            if ico_base is None:
                ico_base = a.icon()
                setattr(a, "_icono_base", ico_base)
            if ico_base.isNull():
                continue
            pm_src = ico_base.pixmap(24, 24)
            if pm_src.isNull():
                continue
            pm_dst = QPixmap(pm_src.size())
            pm_dst.setDevicePixelRatio(pm_src.devicePixelRatio())
            pm_dst.fill(Qt.GlobalColor.transparent)
            p = QPainter(pm_dst)
            p.drawPixmap(0, 0, pm_src)
            p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
            p.fillRect(pm_dst.rect(), color)
            p.end()
            a.setIcon(QIcon(pm_dst))

    def _al_cambiar_unidad(self, _indice: int = 0):
        self._render()

    def _al_unidad_cambiada(self, _indice: int):
        """Cambio de unidad (Abs ↔ %T): la escala del eje Y cambia, así que se
        suelta el rango manual para no dejar un rango sin sentido."""
        self._y_automatico()

    def _al_editar_y(self):
        self._render()

    def _y_automatico(self):
        """Suelta el rango manual del eje Y y vuelve al autoescalado."""
        self.txt_y_min.setText("")
        self.txt_y_max.setText("")
        self._render()

    def _rango_y_manual(self):
        def _leer(widget):
            texto = widget.text().strip().replace(",", ".")
            if not texto:
                return None
            try:
                return float(texto)
            except ValueError:
                return None
        return _leer(self.txt_y_min), _leer(self.txt_y_max)

    def _aplicar_ylim_manual(self):
        ymin, ymax = self._rango_y_manual()
        if ymin is None and ymax is None:
            return
        actual = self.ax.get_ylim()
        lo = ymin if ymin is not None else actual[0]
        hi = ymax if ymax is not None else actual[1]
        if np.isfinite(lo) and np.isfinite(hi) and lo < hi:
            self.ax.set_ylim(lo, hi)

    def _al_alternar_vista(self, apilada: bool):
        self.btn_vista.setText("Apilada" if apilada else "Superpuesta")
        self._render()

    def _render(self):
        self.ax.clear()
        self._cursor = None
        self._cursor_puntos = None
        self._series = []
        self._offsets = []
        self._lineas = []
        if not self._resultados:
            self.ax.set_title(self._titulo or "Sin datos")
            self.ax.set_xticks([])
            self.ax.set_yticks([])
            estilos.aplicar_mpl(self.fig, self.ax, self.tema)
            self._refrescar_bitacora()
            self.canvas.draw_idle()
            return
        if self._modo == "quantitation":
            self._dibujar_calibracion()
        elif self._modo == "multi":
            self._dibujar_barras_multi()
        elif self._modo == "photometrics":
            self._dibujar_barras_fotometria()
        else:
            self._dibujar_lineas()
            self._dibujar_banda()
        self.ax.set_title(self._titulo)
        if len(self._series) > 1:
            self.ax.legend(fontsize=8)
        estilos.aplicar_mpl(self.fig, self.ax, self.tema, grid_axis=self._eje_rejilla())
        self._aplicar_ylim_manual()
        self.fig.tight_layout()
        self._dibujar_marcas()
        self._refrescar_bitacora()
        self._crear_cursor()
        self.canvas.draw_idle()

    def _dibujar_banda(self):
        """Sombrea el área integrada y su cuerda base lineal sobre la primera serie."""
        if self._banda is None or not self._series or self._modo not in ("spectrum", "kinetics"):
            return
        lo, hi = self._banda
        _etq, xs, ys = self._series[0]
        offset = self._offsets[0] if self._offsets else 0.0
        m = (xs >= lo) & (xs <= hi) & np.isfinite(ys)
        if int(m.sum()) < 2:
            return
        xs_s = xs[m]
        ys_s = ys[m] + offset
        base = np.linspace(float(ys_s[0]), float(ys_s[-1]), ys_s.size)
        self.ax.fill_between(xs_s, base, ys_s, color=color_serie(0), alpha=0.22, zorder=2)
        self.ax.plot([float(xs_s[0]), float(xs_s[-1])],
                     [float(ys_s[0]), float(ys_s[-1])],
                     ls="--", lw=0.9, color=COLOR_CURSOR, zorder=3)

    def _eje_rejilla(self) -> Optional[str]:
        """Rejilla sólo horizontal en los gráficos de barras."""
        return "y" if self._modo in ("multi", "photometrics") else None

    # ------------------------------------------------------------- series
    def _dibujar_lineas(self):
        unidad = self.unidad
        datos = [serie_para(self._modo, r, unidad) for r in self._resultados]
        xlabel = next((d[2] for d in datos if d[2]), "")
        ylabel = next((d[3] for d in datos if d[3]), "")
        self._etq_x = _ABREV_X.get(xlabel, "")
        self._etq_y = "Abs" if unidad == "abs" else "%T"
        apilada = self._apilable and self.btn_vista.isChecked()
        pasos = (desplazamientos(len(datos), self._paso_apilado(datos))
                 if apilada else [0.0] * len(datos))
        for i, (x, y, _, _) in enumerate(datos):
            if x.size == 0:
                continue
            etq = self._etiquetas[i] if i < len(self._etiquetas) else f"#{i + 1}"
            # En el panel de puntos marcados (con_marcas=False) los puntos son
            # pocos: se resaltan con marcador para que se vean uno a uno.
            extra = ({} if self.con_marcas
                     else dict(marker="o", ms=5, mec="white", mew=0.6))
            (ln,) = self.ax.plot(x, y + pasos[i], lw=1.0, label=etq,
                                 color=color_serie(i), **extra)
            self._lineas.append(ln)
            self._series.append((etq, x, y))
            self._offsets.append(pasos[i])
            self._marcar_picos(x, y, i, pasos[i])
        y_todos = [y + pasos[i] for i, (_, y, _, _) in enumerate(datos) if isinstance(y, np.ndarray) and y.size]
        if y_todos:
            y_cat = np.concatenate(y_todos)
            fin_y = y_cat[np.isfinite(y_cat)]
            if fin_y.size and fin_y.min() < 0.0 < fin_y.max():
                self._linea_cero()
        if not self.con_marcas:
            self.ax.margins(x=0.04, y=0.06)
        if xlabel:
            self.ax.set_xlabel(xlabel)
        if ylabel:
            self.ax.set_ylabel(f"{ylabel} (apilado)" if apilada else ylabel)

    def _marcar_picos(self, x: np.ndarray, y: np.ndarray, indice: int, offset: float = 0.0):
        """Señala los máximos locales del espectro (y su λ si hay una sola serie).

        Los picos se detectan sobre ABSORBANCIA (es el concepto físico) y se
        marcan sobre la curva tal y como está dibujada, aunque la unidad sea %T.
        `offset` es el desplazamiento vertical de la vista apilada, que hay que
        aplicar para que las marcas no se despeguen de la curva."""
        if self._modo != "spectrum" or not self.marcar_picos:
            return
        crudo = self._resultados[indice].get("puntos", [])
        fin = np.isfinite(y)
        if not crudo or fin.sum() < 5:
            return
        # La prominencia se mide sobre ABSORBANCIA, no sobre la unidad mostrada:
        # si no, al ver el espectro en %T (rango ~0..46) ningún pico de
        # absorbancia pasaría el umbral y no se marcaría ninguno.
        abs_ = np.array([p[2] for p in crudo], dtype=float)
        fin_a = np.isfinite(abs_)
        if fin_a.sum() < 5:
            return
        rango_a = float(abs_[fin_a].max() - abs_[fin_a].min())
        if rango_a < 0.01:                       # blanco o espectro plano
            return
        factor_prom = float(self.spin_prominencia.value()) if hasattr(self, "spin_prominencia") else 0.02
        picos = an.picos(crudo, prominencia=max(1e-4, factor_prom * rango_a))
        picos = sorted(picos, key=lambda p: -float(p.get("prominencia") or 0.0))[:8]
        if not picos:
            return
        xs, ys, fwhms = [], [], []
        for p in picos:
            j = int(np.argmin(np.abs(x - p["wl"])))
            if np.isfinite(y[j]):
                xs.append(float(x[j]))
                ys.append(float(y[j]))
                fwhms.append(p.get("fwhm"))
        if not xs:
            return
        self.ax.plot(xs, [v + offset for v in ys], "o", ms=4.5, color=color_serie(indice),
                     markeredgecolor="white", markeredgewidth=0.6, zorder=5)
        if len(self._resultados) != 1:            # no saturar de texto con varias series
            return
        # Etiquetas separadas: si dos picos están muy juntos sus λ se solaparían y
        # quedarían ilegibles. La referencia es el rango del ESPECTRO completo (no
        # el de los picos, que suelen estar agrupados), y se alternan arriba/abajo.
        parejas = sorted(zip(xs, ys, fwhms), key=lambda p: p[0])
        rango_x = float(x.max() - x.min()) if x.size else 1.0
        rango_x = rango_x or 1.0
        ultimo, n = None, 0
        con_fwhm = hasattr(self, "chk_fwhm") and self.chk_fwhm.isChecked()
        for xv, yv, fw in parejas:
            if ultimo is not None and abs(xv - ultimo) < 0.05 * rango_x:
                continue
            ultimo = xv
            etq_pico = f"{xv:g} (FWHM {fw:.1f})" if (con_fwhm and fw is not None) else f"{xv:g}"
            self.ax.annotate(etq_pico, (xv, yv + offset), textcoords="offset points",
                             xytext=(0, 8 if n % 2 == 0 else 17), ha="center",
                             fontsize=6.5)
            n += 1

    def _dibujar_barras_multi(self):
        unidad = self.unidad
        datos = [serie_para("multi", r, unidad) for r in self._resultados]
        wls = datos[0][0] if datos else np.array([])
        n = max(len(datos), 1)
        ancho = 0.8 / n
        con_valores = n * len(wls) <= 8          # no saturar de números
        for i, (x, y, _, _) in enumerate(datos):
            etq = self._etiquetas[i] if i < len(self._etiquetas) else f"#{i + 1}"
            pos = x + (i - (n - 1) / 2.0) * ancho
            self.ax.bar(pos, y, ancho, label=etq, color=color_serie(i),
                        edgecolor=color_serie(i), linewidth=0.6)
            self._series.append((etq, x, y))
            self._offsets.append(0.0)
            if con_valores:
                for yv, pv in zip(y, pos):
                    if np.isfinite(yv):
                        self._etiquetar_barra(pv, yv)
        self.ax.set_xticks(wls)
        self.ax.set_xticklabels([f"{v:g}" for v in wls])
        self._girar_etiquetas_si_se_solapan(wls)
        self.ax.set_xlabel("Longitud de onda (nm)")
        self.ax.set_ylabel(_ETIQUETA_Y[unidad])
        self._etq_x, self._etq_y = "nm", ("Abs" if unidad == "abs" else "%T")
        self._linea_cero()
        self._anotar_calculos_multi()

    def _dibujar_barras_fotometria(self):
        unidad = self.unidad
        vals, etiquetas = [], []
        for i, r in enumerate(self._resultados):
            _x, y, _, _ = serie_para("photometrics", r, unidad)
            vals.append(float(y[0]) if y.size else float("nan"))
            etiquetas.append(self._etiquetas[i] if i < len(self._etiquetas) else f"#{i + 1}")
        una_serie = len(vals) == 1
        for k, (v, e) in enumerate(zip(vals, etiquetas)):
            color = color_serie(0 if una_serie else k)
            self.ax.bar([float(k)], [v], 0.55, color=color, edgecolor=color,
                        linewidth=0.6, label=e)      # etiquetada: la leyenda la usa
            if np.isfinite(v):
                self._etiquetar_barra(float(k), v, 8)
            self._series.append((e, np.array([float(k)]), np.array([v])))
            self._offsets.append(0.0)
        self.ax.set_xticks(np.arange(len(vals), dtype=float))
        self.ax.set_xticklabels(etiquetas)
        self.ax.set_xlabel("Lectura")
        self.ax.set_ylabel(_ETIQUETA_Y[unidad])
        self._etq_x, self._etq_y = "", ("Abs" if unidad == "abs" else "%T")
        self._linea_cero()

    def _etiquetar_barra(self, x: float, y: float, tam: int = 7):
        arriba = y >= 0
        self.ax.annotate(f"{y:.3f}", (x, y), textcoords="offset points",
                         xytext=(0, 4 if arriba else -11), ha="center",
                         va="bottom" if arriba else "top", fontsize=tam)

    def _girar_etiquetas_si_se_solapan(self, valores: Sequence[float]):
        """Con longitudes de onda muy juntas las etiquetas del eje X se solapan
        (300 y 330 se leían como '300330'): se giran para que se lean."""
        vals = [float(v) for v in valores if np.isfinite(v)]
        if len(vals) < 2:
            return
        ordenados = sorted(vals)
        paso = min(b - a for a, b in zip(ordenados, ordenados[1:]))
        rango = (ordenados[-1] - ordenados[0]) or 1.0
        if paso / rango < 0.12:
            for t in self.ax.get_xticklabels():
                t.set_rotation(30)
                t.set_ha("right")
                t.set_fontsize(8)

    def _linea_cero(self):
        """Las barras cuelgan del cero: señalarlo para que se entienda la escala
        (con absorbancias negativas la barra baja en vez de subir)."""
        self.ax.axhline(0.0, color=estilos.colores(self.tema)[3], lw=0.9, zorder=1)

    def _anotar_calculos_multi(self):
        if len(self._resultados) != 1:
            return
        ratio = self._resultados[0].get("A1/A2")
        dif = self._resultados[0].get("A1-A2")
        lineas = []
        if isinstance(ratio, (int, float)) and np.isfinite(ratio):
            lineas.append(f"A1/A2 = {ratio:.3f}")
        if isinstance(dif, (int, float)) and np.isfinite(dif):
            lineas.append(f"A1-A2 = {dif:.3f}")
        if lineas:
            self.ax.text(0.99, 0.97, "\n".join(lineas), transform=self.ax.transAxes,
                         ha="right", va="top", fontsize=8,
                         bbox=dict(boxstyle="round", fc="white", ec="0.7", alpha=0.85))

    @staticmethod
    def _paso_apilado(datos) -> float:
        """Separación vertical entre series en la vista apilada.

        Se usa la MEDIANA de las amplitudes (no el máximo): si un espectro tiene
        un pico muy alto o saturado, tomar el máximo empujaría las demás series
        al borde superior del gráfico."""
        amplitudes = []
        for _, y, _, _ in datos:
            fin = y[np.isfinite(y)]
            if fin.size:
                amplitudes.append(float(fin.max() - fin.min()))
        if not amplitudes:
            return 1.0
        base = float(np.median(amplitudes))
        if base <= 0:
            base = float(np.max(amplitudes))
        return base * 1.15 if base > 0 else 1.0

    def _dibujar_calibracion(self):
        r0 = self._resultados[0]
        estandares = [(float(c), float(a)) for c, a in r0.get("estandares", [])]
        std = sorted(estandares, key=lambda e: e[1])
        xs = np.array([s[1] for s in std], dtype=float)   # absorbancia
        ys = np.array([s[0] for s in std], dtype=float)   # concentración
        color = color_serie(0)
        rango_std = float(xs.max() - xs.min()) if xs.size >= 2 else 0.0
        abs_muestras = [
            float(r["abs_muestra"])
            for r in self._resultados
            if isinstance(r.get("abs_muestra"), (int, float)) and math.isfinite(r["abs_muestra"])
        ]
        x_min_global = min([float(xs.min())] + abs_muestras) if xs.size else (min(abs_muestras) if abs_muestras else 0.0)
        x_max_global = max([float(xs.max())] + abs_muestras) if xs.size else (max(abs_muestras) if abs_muestras else 1.0)
        if xs.size:
            self.ax.plot(xs, ys, "o-", lw=1.2, ms=5.5, label="Estándares", color=color)
            self._series.append(("Estándares", xs, ys))
            self._offsets.append(0.0)
            if xs.size >= 2 and rango_std > 0:
                coef = np.polyfit(xs, ys, 1)
                xx = np.linspace(x_min_global, x_max_global, 60)
                q_meta = an.cuantificacion(std, abs_muestras[0] if abs_muestras else float(xs.mean()))
                r2 = q_meta.get("lineal_r2")
                etq_fit = f"Ajuste lineal (R² = {r2:.4f})" if isinstance(r2, float) and math.isfinite(r2) else "Ajuste lineal"
                self.ax.plot(xx, np.polyval(coef, xx), "--", lw=1.1,
                             color=color, alpha=0.85, label=etq_fit)
        una_muestra = len(self._resultados) == 1
        span_x = (x_max_global - x_min_global) or 1.0
        for i, r in enumerate(self._resultados):
            stds_r = r.get("estandares") or r0.get("estandares") or []
            ma = r.get("abs_muestra")
            if not (isinstance(ma, (int, float)) and math.isfinite(ma)):
                continue
            c_interp = (
                an.cuantificacion(stds_r, ma).get("conc_interp")
                if stds_r
                else None
            )
            c_rep = r.get("conc_muestra")
            if (c_interp is None or rango_std == 0.0) and isinstance(c_rep, (int, float)) and math.isfinite(c_rep):
                c_val = float(c_rep)
            else:
                c_val = c_interp
            color_m = "#ef4444" if una_muestra else color_serie(i + 1)
            etq_m = (
                "Muestra"
                if una_muestra
                else (self._etiquetas[i] if i < len(self._etiquetas) else f"Muestra #{i + 1}")
            )
            self.ax.axvline(ma, color="#f59e0b" if una_muestra else color_m, ls=":", lw=1.1, alpha=0.85)
            if c_val is not None:
                self.ax.plot(ma, c_val, "s", color=color_m, ms=7.5,
                             markeredgecolor="white", markeredgewidth=0.8, label=etq_m, zorder=5)
                self._series.append((etq_m, np.array([float(ma)]), np.array([float(c_val)])))
                self._offsets.append(0.0)
                unid = str(r.get("unidades") or "").strip()
                suf_u = f" {unid}" if unid else ""
                a_derecha = (float(ma) - x_min_global) > 0.65 * span_x
                dx = -10 if a_derecha else 10
                ha_align = "right" if a_derecha else "left"
                ann = self.ax.annotate(
                    f"Conc. = {c_val:.4g}{suf_u}",
                    (ma, c_val),
                    textcoords="offset points",
                    xytext=(dx, 6 + (i % 2) * 12),
                    ha=ha_align,
                    fontsize=8.5,
                    fontweight="600",
                    bbox=dict(boxstyle="round,pad=0.3", fc="#151b23", ec=color_m, lw=0.9, alpha=0.92),
                    zorder=6,
                )
                ann._borde_personalizado = True
        self.ax.set_xlabel("Absorbancia")
        self.ax.set_ylabel("Concentración")
        self._etq_x, self._etq_y = "Abs", "Conc"

    # ----------------------------------------------------------------- cursor
    def _crear_cursor(self):
        """Cruz vertical + un punto por serie en el punto de medida."""
        color = COLOR_CURSOR
        xlim_orig = self.ax.get_xlim()
        ylim_orig = self.ax.get_ylim()
        x_ini = (xlim_orig[0] + xlim_orig[1]) / 2.0 if np.isfinite(xlim_orig[0]) and np.isfinite(xlim_orig[1]) else 0.0
        self._cursor = self.ax.axvline(x_ini, color=color, ls="--", lw=0.8,
                                       alpha=0.85, visible=False, zorder=4)
        (self._cursor_puntos,) = self.ax.plot([], [], "o", ms=5.5, mfc="none",
                                              mec=color, mew=1.4, zorder=6,
                                              label="_cursor", visible=False)
        self.ax.set_xlim(xlim_orig)
        self.ax.set_ylim(ylim_orig)

    def _punto_mas_cercano(self, x_mouse: float) -> Optional[float]:
        """Engancha la cruz al valor de x más cercano de cualquier serie."""
        mejor = None
        for _etq, xs, _ys in self._series:
            if xs.size == 0:
                continue
            j = int(np.argmin(np.abs(xs - x_mouse)))
            xv = float(xs[j])
            if mejor is None or abs(xv - x_mouse) < abs(mejor - x_mouse):
                mejor = xv
        return mejor

    def _al_mover(self, event):
        if (event is None or event.inaxes is not self.ax
                or not self._series or event.xdata is None):
            self._al_salir(None)
            return
        x_snap = self._punto_mas_cercano(float(event.xdata))
        if x_snap is None:
            return
        sufijo_x = f" {self._etq_x}" if self._etq_x else ""
        partes, px, py = [], [], []
        for i, (etq, xs, ys) in enumerate(self._series):
            if xs.size == 0:
                continue
            j = int(np.argmin(np.abs(xs - x_snap)))
            yv = ys[j]
            if not np.isfinite(yv):
                continue
            partes.append(f"{etq}: {xs[j]:.1f}{sufijo_x} · {yv:.3f} {self._etq_y}".rstrip())
            px.append(float(xs[j]))
            py.append(float(yv) + (self._offsets[i] if i < len(self._offsets) else 0.0))
        self._mover_cursor(x_snap, px, py)
        texto = "   |   ".join(partes[:MAX_SERIES_CURSOR])
        if len(partes) > MAX_SERIES_CURSOR:
            texto += f"   (+{len(partes) - MAX_SERIES_CURSOR} más)"
        if len(partes) <= 1:
            texto_badge = partes[0] if partes else ""
        else:
            coord0 = partes[0].split(": ", 1)[-1] if ": " in partes[0] else partes[0]
            texto_badge = f"{coord0}  ({len(partes)} series)"
        self._emitir(texto, texto_badge=texto_badge)

    def _al_salir(self, _event):
        cambio = False
        for artista in (self._cursor, self._cursor_puntos):
            if artista is not None and artista.get_visible():
                artista.set_visible(False)
                cambio = True
        if cambio:
            self.canvas.draw_idle()
        self._emitir("")

    def _mover_cursor(self, x: float, px: List[float], py: List[float]):
        if self._cursor is None:
            return
        self._cursor.set_xdata([x, x])
        self._cursor.set_visible(True)
        if self._cursor_puntos is not None:
            self._cursor_puntos.set_data(px, py)
            self._cursor_puntos.set_visible(bool(px))
        self.canvas.draw_idle()

    def _emitir(self, texto: str, texto_badge: Optional[str] = None):
        if hasattr(self, "lbl_coord_live"):
            mostrar = texto_badge if texto_badge is not None else texto
            self.lbl_coord_live.setText(mostrar)
            self.lbl_coord_live.setVisible(bool(mostrar))
        if texto != self._ultimo:
            self._ultimo = texto
            self.coordenadas.emit(texto)

    # ---------------------------------------------------------- marcas (cinética)
    def _al_click(self, event):
        """Clic izquierdo (sin herramienta de zoom activa) = marcar/quitar un punto.

        La marca se engancha al punto de medida más cercano del eje X (tiempo).
        Si se vuelve a clicar sobre una marca existente, se quita.
        """
        if (not self.con_marcas or self._modo != "kinetics" or event is None
                or getattr(event, "button", None) != 1
                or getattr(event, "inaxes", None) is not self.ax
                or event.xdata is None or not self._series
                or getattr(self.toolbar, "mode", "") != ""):
            return
        x = self._punto_mas_cercano(float(event.xdata))
        if x is None:
            return
        tolerancia = self._tolerancia_marca()
        for marca in self._marcas:
            if abs(marca - x) <= tolerancia:
                self._marcas.remove(marca)
                self.mensaje.emit("Marca quitada en %.1f %s"
                                  % (x, (self._etq_x or "").strip()))
                self._render()
                return
        self._marcas.append(x)
        self._marcas.sort()
        self.mensaje.emit("Marca añadida en %.1f %s" % (x, (self._etq_x or "").strip()))
        self._render()

    def _tolerancia_marca(self) -> float:
        """Mitad del paso mínimo de X entre series (para quitar una marca clicando cerca)."""
        pasos = []
        for _etq, xs, _ys in self._series:
            if xs.size > 1:
                d = np.diff(xs)
                d = d[np.isfinite(d) & (d > 0)]
                if d.size:
                    pasos.append(float(d.min()))
        return 0.5 * min(pasos) if pasos else 0.0

    def _marcar_intervalo(self):
        """Añade una marca cada N segundos (30, 60, 90…) dentro del rango medido."""
        if self._modo != "kinetics" or not self._series:
            self.mensaje.emit("Las marcas por intervalo valen solo para cinéticas.")
            return
        paso = self.spin_intervalo.value()
        series = [xs for _etq, xs, _ys in self._series if xs.size]
        if not series:
            return
        minimo = min(float(xs.min()) for xs in series)
        maximo = max(float(xs.max()) for xs in series)
        t = float(math.ceil(minimo / paso)) * paso
        nuevos = []
        while t <= maximo:
            ajustado = self._punto_mas_cercano(t)
            if ajustado is not None and ajustado not in self._marcas:
                nuevos.append(ajustado)
            t += paso
        if nuevos:
            self._marcas.extend(nuevos)
            self._marcas.sort()
            self._render()
            self.mensaje.emit("%d marcas añadidas cada %d s." % (len(nuevos), paso))
        else:
            self.mensaje.emit("No hay puntos nuevos para marcar cada %d s." % paso)

    def _borrar_marcas(self):
        self._marcas = []
        self._render()
        self.mensaje.emit("Marcas borradas.")

    def _pedir_graficar_marcados(self):
        """Pide a la ventana que dibuje los puntos marcados en su propio gráfico."""
        if not self._marcas:
            self.mensaje.emit("No hay marcas: marca puntos (clic o «Marcar cada») "
                              "para poder graficarlos.")
            return
        self.marcados.emit()

    def resultados_marcados(self):
        """Resultados de cinética reducidos a los puntos marcados.

        Si en la bitácora hay filas elegidas se usan SOLO esas marcas; si no,
        todas.  Devuelve ``(resultados, etiquetas)`` —uno por muestra— listos
        para dibujarse con otro :class:`PanelGrafico` como un X-Y tiempo/Abs.
        """
        try:
            filas = sorted({i.row() for i in
                            self.tabla_marcas.selectionModel().selectedRows()})
        except Exception:
            filas = []
        elegidas = [self._marcas[f] for f in filas if 0 <= f < len(self._marcas)]
        xs = sorted(elegidas) if elegidas else sorted(self._marcas)

        reducidos, etiquetas = [], []
        for i, r in enumerate(self._resultados):
            serie = r.get("serie") or []
            if not serie:
                continue
            tiempos = an.tiempos_de(r)
            pts, vistos = [], set()
            for x in xs:
                j = int(np.argmin(np.abs(tiempos - x))) if tiempos.size else -1
                if j < 0 or j >= len(serie):
                    continue
                t = float(tiempos[j])
                if t in vistos:
                    continue
                vistos.add(t)
                _idx, T, A = serie[j]
                if not np.isfinite(A):
                    continue
                pts.append((t, T, A))
            if not pts:
                continue
            nuevo = dict(r)
            nuevo["serie"] = [(k, T, A) for k, (_t, T, A) in enumerate(pts)]
            nuevo["tiempos"] = [t for (t, _T, _A) in pts]
            nuevo["n"] = len(pts)
            nuevo.pop("saturados", None)
            reducidos.append(nuevo)
            etiquetas.append(self._etiquetas[i] if i < len(self._etiquetas)
                             else "#%d" % (i + 1))
        return reducidos, etiquetas

    def _dibujar_marcas(self):
        """Marca cada punto señalado: línea vertical + un punto por serie."""
        if self._modo != "kinetics" or not self._marcas or not self._series:
            return
        for x in self._marcas:
            self.ax.axvline(x, color=COLOR_CURSOR, ls=":", lw=0.8, alpha=0.7, zorder=3)
            for i, (etq, xs, ys) in enumerate(self._series):
                if xs.size == 0:
                    continue
                j = int(np.argmin(np.abs(xs - x)))
                if j < ys.size and np.isfinite(ys[j]):
                    offset = self._offsets[i] if i < len(self._offsets) else 0.0
                    self.ax.plot(xs[j], ys[j] + offset, "o", ms=4,
                                 color=color_serie(i), mfc=color_serie(i),
                                 mec="white", mew=0.5, zorder=6)

    def _refrescar_bitacora(self):
        """Vuelca las marcas en la tabla: Tiempo + una columna de Abs por serie.

        Muestra SIEMPRE absorbancia (no la unidad del gráfico), que es lo que se
        quiere anotar; se recalcula del resultado crudo de cada serie.
        """
        self.tabla_marcas.clearContents()
        series = []
        for i, r in enumerate(self._resultados):
            etq = self._etiquetas[i] if i < len(self._etiquetas) else "#%d" % (i + 1)
            puntos = r.get("serie") or []
            xs = an.tiempos_de(r)
            ys = np.array([p[2] for p in puntos], dtype=float)
            series.append((etq, xs, ys))
        self.tabla_marcas.setColumnCount(1 + len(series))
        eje = self._etq_x or "s"
        cabecera = ["Tiempo (%s)" % eje] + [etq for etq, _xs, _ys in series]
        self.tabla_marcas.setHorizontalHeaderLabels(cabecera)
        self.tabla_marcas.setRowCount(len(self._marcas))
        for fila, x in enumerate(sorted(self._marcas)):
            self.tabla_marcas.setItem(fila, 0, QTableWidgetItem("%.1f" % x))
            for columna, (_etq, xs, ys) in enumerate(series, start=1):
                if xs.size == 0:
                    continue
                j = int(np.argmin(np.abs(xs - x)))
                if j < ys.size and np.isfinite(ys[j]):
                    self.tabla_marcas.setItem(fila, columna,
                                              QTableWidgetItem("%.3f" % ys[j]))
        hay_marcas = bool(self._marcas)
        self.btn_graficar_marcados.setEnabled(hay_marcas)
        self.btn_copiar_bitacora.setEnabled(hay_marcas)
        self.btn_exportar_bitacora_xlsx.setEnabled(hay_marcas)

    def _menu_contextual_bitacora(self, pos):
        """Menú contextual al hacer clic derecho en la tabla de la bitácora."""
        if not self._marcas:
            return
        menu = QMenu(self)
        try:
            filas_sel = self.tabla_marcas.selectionModel().selectedRows()
        except Exception:
            filas_sel = []
        if filas_sel:
            n_sel = len(filas_sel)
            act_sel = menu.addAction(f"📋 Copiar {n_sel} fila{'s' if n_sel != 1 else ''} seleccionada{'s' if n_sel != 1 else ''} (para Excel)")
            act_sel.triggered.connect(lambda: self._copiar_bitacora_clipboard(solo_seleccionadas=True))
        act_todas = menu.addAction("📋 Copiar toda la tabla (para Excel / Sheets)")
        act_todas.triggered.connect(lambda: self._copiar_bitacora_clipboard(solo_seleccionadas=False))
        menu.addSeparator()
        act_xlsx = menu.addAction("📊 Exportar bitácora a Excel (.xlsx)…")
        act_xlsx.triggered.connect(lambda: self._exportar_bitacora_xlsx())
        menu.exec(self.tabla_marcas.viewport().mapToGlobal(pos))

    def _datos_bitacora(self, solo_seleccionadas: Optional[bool] = None) -> Tuple[List[str], List[List[str]]]:
        """Devuelve (cabecera, filas) con el contenido actual de la tabla de la bitácora.

        Si solo_seleccionadas es True, devuelve únicamente las filas seleccionadas.
        Si solo_seleccionadas es None, usa las filas seleccionadas si las hay, o todas.
        """
        cols = self.tabla_marcas.columnCount()
        rows = self.tabla_marcas.rowCount()
        if cols == 0 or rows == 0:
            return [], []

        cabecera = []
        for c in range(cols):
            item = self.tabla_marcas.horizontalHeaderItem(c)
            cabecera.append(item.text() if item else f"Col {c + 1}")

        if solo_seleccionadas is True:
            try:
                filas_indices = sorted({idx.row() for idx in self.tabla_marcas.selectionModel().selectedRows()})
            except Exception:
                filas_indices = []
        elif solo_seleccionadas is None:
            try:
                sel = sorted({idx.row() for idx in self.tabla_marcas.selectionModel().selectedRows()})
                filas_indices = sel if sel else list(range(rows))
            except Exception:
                filas_indices = list(range(rows))
        else:
            filas_indices = list(range(rows))

        filas = []
        for r in filas_indices:
            fila_vals = []
            for c in range(cols):
                it = self.tabla_marcas.item(r, c)
                fila_vals.append(it.text() if it else "")
            filas.append(fila_vals)
        return cabecera, filas

    def _copiar_bitacora_clipboard(self, solo_seleccionadas: Optional[bool] = None):
        """Copia la bitácora al portapapeles en formato TSV y HTML (ideal para pegar en Excel)."""
        cabecera, filas = self._datos_bitacora(solo_seleccionadas=solo_seleccionadas)
        if not cabecera or not filas:
            self.mensaje.emit("No hay datos en la bitácora para copiar.")
            return

        # TSV (Tab-Separated Values)
        lineas_tsv = ["\t".join(cabecera)]
        for f in filas:
            lineas_tsv.append("\t".join(f))
        texto_tsv = "\r\n".join(lineas_tsv)

        # HTML Table
        th_html = "".join(f"<th style='border:1px solid #d0d7de;padding:6px;background-color:#2b579a;color:#ffffff;text-align:center;'>{c}</th>" for c in cabecera)
        tr_html = []
        for f in filas:
            tds = "".join(f"<td style='border:1px solid #d0d7de;padding:4px;text-align:right;'>{val}</td>" for val in f)
            tr_html.append(f"<tr>{tds}</tr>")
        tabla_html = (
            "<table style='border-collapse:collapse;font-family:Segoe UI,Helvetica,Arial,sans-serif;font-size:10pt;'>"
            f"<thead><tr>{th_html}</tr></thead>"
            f"<tbody>{''.join(tr_html)}</tbody>"
            "</table>"
        )

        mime = QMimeData()
        mime.setText(texto_tsv)
        mime.setHtml(tabla_html)
        QApplication.clipboard().setMimeData(mime)

        cant = len(filas)
        sel_txt = " seleccionada" if (solo_seleccionadas or (solo_seleccionadas is None and cant < self.tabla_marcas.rowCount())) else ""
        self.mensaje.emit(f"Bitácora copiada al portapapeles ({cant} fila{sel_txt}{'s' if cant != 1 else ''}, lista para pegar en Excel).")

    def _exportar_bitacora_xlsx(self, ruta_destino: Optional[str] = None):
        """Guarda la tabla de marcas de la bitácora en un archivo Excel (.xlsx) con valores numéricos y formato."""
        cabecera, filas = self._datos_bitacora(solo_seleccionadas=False)
        if not cabecera or not filas:
            self.mensaje.emit("No hay datos en la bitácora para exportar.")
            return

        if not ruta_destino:
            sug = "bitacora_cinetica.xlsx"
            if self._titulo:
                sug_limpio = "".join(c for c in self._titulo if c.isalnum() or c in (" ", "-", "_")).strip()
                if sug_limpio:
                    sug = f"bitacora_{sug_limpio.replace(' ', '_')}.xlsx"
            ruta, _ = QFileDialog.getSaveFileName(
                self, "Exportar bitácora a Excel", sug, "Libro de Excel (*.xlsx)"
            )
            if not ruta:
                return
            ruta_destino = ruta

        try:
            from openpyxl import Workbook
            from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
            from openpyxl.utils import get_column_letter

            wb = Workbook()
            ws = wb.active
            ws.title = "Bitácora Cinética"

            fuente_cab = Font(bold=True, color="FFFFFF", size=11)
            relleno_cab = PatternFill("solid", fgColor="2B579A")
            align_center = Alignment(horizontal="center", vertical="center")
            align_right = Alignment(horizontal="right", vertical="center")
            borde_fino = Border(
                left=Side(style="thin", color="D9D9D9"),
                right=Side(style="thin", color="D9D9D9"),
                top=Side(style="thin", color="D9D9D9"),
                bottom=Side(style="thin", color="D9D9D9"),
            )

            fila_inicio = 1
            if self._titulo:
                ws.cell(row=1, column=1, value=f"{self._titulo} — Bitácora de Cinética").font = Font(bold=True, size=12)
                fila_inicio = 3

            for col_idx, col_name in enumerate(cabecera, start=1):
                c = ws.cell(row=fila_inicio, column=col_idx, value=col_name)
                c.font = fuente_cab
                c.fill = relleno_cab
                c.alignment = align_center

            for r_idx, fila in enumerate(filas, start=fila_inicio + 1):
                for c_idx, val_str in enumerate(fila, start=1):
                    cell = ws.cell(row=r_idx, column=c_idx)
                    cell.border = borde_fino
                    try:
                        val_num = float(val_str.replace(",", "."))
                        cell.value = val_num
                        if c_idx == 1:
                            cell.number_format = "0.0"
                        else:
                            cell.number_format = "0.000"
                        cell.alignment = align_right
                    except (ValueError, AttributeError):
                        cell.value = val_str
                        cell.alignment = align_center

            for col_idx, col_name in enumerate(cabecera, start=1):
                max_len = max(len(str(col_name)), 12)
                for fila in filas:
                    if col_idx - 1 < len(fila):
                        max_len = max(max_len, len(str(fila[col_idx - 1])))
                ws.column_dimensions[get_column_letter(col_idx)].width = min(max_len + 4, 60)

            wb.save(ruta_destino)
            self.mensaje.emit(f"Bitácora exportada a Excel: {ruta_destino}")
        except Exception as e:
            self.mensaje.emit(f"Error al exportar a Excel: {e}")

