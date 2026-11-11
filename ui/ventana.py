# -*- coding: utf-8 -*-
"""Ventana principal del Programa Maestro Mimético — Jenway 6705 (PySide6).

Mímesis del flujo del software original: cargar una carpeta de tarjeta copiada
(*login source*) → explorar los métodos agrupados por modo → ver espectro/curva +
datos → exportar (CSV / Excel).

Incluye: temas oscuro/claro, superposición de muestras, unidades %T <-> Abs, vista
apilada, árbol de métodos por modo con búsqueda y filtro por usuario, arrastrar y
soltar, apertura de archivos sueltos (.JWB sin índice, reportes .TXT) y tabla de
datos virtualizada sin tope de filas.
"""
from __future__ import annotations

import os
import unicodedata
from typing import Dict, List, Optional, Sequence, Tuple

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QComboBox,
                               QDockWidget, QFileDialog, QGroupBox, QHBoxLayout,
                               QLabel, QLineEdit, QListWidget, QListWidgetItem,
                               QMainWindow, QMessageBox, QPushButton,
                               QScrollArea, QSplitter, QStackedWidget,
                               QStatusBar, QStyle, QTabWidget, QTableView,
                               QTableWidget, QTableWidgetItem, QTreeWidget,
                               QTreeWidgetItem, QVBoxLayout, QWidget)

from jenway67 import procesado as pr
from jenway67.adaptador_txt import cargar_reporte, parsear_stream_serie
from jenway67.exportar import exportar_carpeta, filas_para
from jenway67.exportar_jcamp import exportar_jcamp_dx
from jenway67.exportar_pdf import exportar_tarjeta_pdf, exportar_vista_pdf
from jenway67.informe import _analisis_por_modo, analizar_carpeta
from jenway67.models import Metodo, Muestra, Tarjeta
from jenway67.parser_jwb import decodificar as decodificar_jwb
from jenway67.puerto_jenway import LecturaSerie
from jenway67.reader import decodificar_archivo, leer_carpeta, registrar_virtual
from ui import diagnostico, estilos
from ui.modelo_tabla import ModeloTablaDatos
from ui.panel_conexion import PanelConexionSerie, VisorConsolaSerie
from ui.panel_procesado import PanelProcesado
from ui.toolbar_plot import PanelGrafico

# Etiqueta en español de cada modo y orden en el que se muestran los grupos.
ETIQUETA_MODO: Dict[str, str] = {
    "spectrum": "Espectro",
    "kinetics": "Cinética",
    "multi": "Multi-longitud",
    "quantitation": "Cuantificación",
    "photometrics": "Fotometría",
}
ORDEN_MODOS = tuple(ETIQUETA_MODO.keys())

_TITULO = Qt.ItemDataRole.UserRole


def etiqueta_modo(modo: str) -> str:
    return ETIQUETA_MODO.get(modo, modo or "(sin modo)")


def _normaliza(texto) -> str:
    """Minúsculas y sin tildes, para que 'metodo' encuentre 'Método'."""
    t = unicodedata.normalize("NFD", str("" if texto is None else texto)).lower()
    return "".join(c for c in t if unicodedata.category(c) != "Mn")


class VentanaMaestro(QMainWindow):
    def __init__(self, carpeta: Optional[str] = None, tema: str = "dark"):
        super().__init__()
        self.setWindowTitle("Programa Maestro — Jenway 6705")
        self.resize(1280, 760)
        self.setAcceptDrops(True)
        self.tema = tema
        self.tarjeta: Optional[Tarjeta] = None
        self.metodo_actual: Optional[Metodo] = None
        self._muestras_actuales: List[Tuple[str, str]] = []
        self._status_base = "Listo."
        self._contador_serie = 0
        self._ultimo_contexto_foto: Dict[str, object] = {}
        self._ultimo_contexto_quant: Dict[str, object] = {}
        self._ruta_sesion_actual: Optional[str] = None
        #: Cadena de procesado (Fase 3) por índice de muestra.  No destructiva:
        #: el .JWB original se vuelve a decodificar intacto cada vez.
        self.cadenas: Dict[int, pr.Cadena] = {}

        self._construir_menu()
        central = QWidget()
        self.setCentralWidget(central)
        raiz = QVBoxLayout(central)
        raiz.setContentsMargins(0, 0, 0, 0)
        raiz.setSpacing(0)

        raiz.addWidget(self._construir_sidebar())
        self.stack = QStackedWidget()
        self.stack.addWidget(self._construir_pagina_datos())
        self.stack.addWidget(self._construir_pagina_config())
        raiz.addWidget(self.stack, 1)

        self.setStatusBar(QStatusBar())
        self._construir_dock_procesado()
        app = QApplication.instance()
        if app and app.property("_tema_actual") != self.tema:
            app.setProperty("_tema_actual", self.tema)
            app.setStyleSheet(estilos.qss(self.tema))
        self._actualizar_status("Listo. Abre una carpeta de tarjeta (Archivo → Abrir tarjeta…), "
                                "suelta una carpeta aquí o conecta el Jenway 6705 por RS-232.")

        if carpeta:
            self.cargar_carpeta(carpeta)

    # -------------------------------------------------- procesado (Fase 3)
    def _construir_dock_procesado(self):
        """Integra el panel de procesado espectral en la pestaña derecha sin robar ancho extra."""
        self.panel_proc = PanelProcesado(self)
        scroll_proc = QScrollArea()
        scroll_proc.setWidgetResizable(True)
        scroll_proc.setWidget(self.panel_proc)
        self.tabs_derecha.addTab(scroll_proc, "Procesado")

        # El interruptor del panel va en el menú "Ver" que YA existe.
        self.menu_ver.addSeparator()
        self.accion_ver_procesado = QAction("Procesado espectral", self)
        self.accion_ver_procesado.triggered.connect(self._ir_a_procesado)
        self.menu_ver.addAction(self.accion_ver_procesado)

        self.panel_proc.cambio.connect(self._reprocesar)
        self.panel_proc.mensaje.connect(self._actualizar_status)
        self.panel_proc.operar.connect(self._operar_seleccionadas)
        self.panel_proc.aplicar_a_todas.connect(self._aplicar_cadena_a_todas)
        self.panel_proc.integrar_banda.connect(self._integrar_banda_activa)
        self.panel_proc.limpiar_banda.connect(self._limpiar_banda_activa)
        self.panel_proc.setEnabled(False)
        self.panel_proc.mostrar_aviso("Selecciona un espectro o una cinética para procesar.")
        self.panel_proc.setToolTip("El procesado no toca el archivo original: "
                                   "siempre se puede deshacer.")

    def _ir_a_procesado(self):
        """Muestra la página principal y activa la pestaña de Procesado espectral."""
        self.stack.setCurrentIndex(0)
        self.btn_datos.setChecked(True)
        if hasattr(self, "tabs_derecha") and self.tabs_derecha.count() > 1:
            self.tabs_derecha.setCurrentIndex(1)

    # ------------------------------------------- sacar de aqui lo que se ve
    def _escribir_vista_csv(self, ruta: str) -> int:
        """Escribe la tabla visible en ``ruta``.  Devuelve el número de filas.

        Separador ';' y BOM: es lo que Excel espera en configuración española.
        """
        import csv

        with open(ruta, "w", newline="", encoding="utf-8-sig") as manejador:
            escritor = csv.writer(manejador, delimiter=";")
            escritor.writerow(list(self.modelo_datos.cabecera()))
            filas = self.modelo_datos.filas()
            escritor.writerows(filas)
        return len(filas)

    def _exportar_vista_csv(self):
        """Exporta a CSV EXACTAMENTE lo que se ve, con el procesado aplicado.

        A diferencia de "Exportar CSV…" (que vuelca la tarjeta entera), esto
        guarda la tabla actual: la muestra o muestras seleccionadas con su
        cadena de procesado.
        """
        if not self.modelo_datos.filas():
            self._actualizar_status("No hay nada que exportar: selecciona un método.")
            return
        ruta, _ = QFileDialog.getSaveFileName(self, "Guardar la vista como CSV",
                                              "vista.csv", "CSV (*.csv)")
        if not ruta:
            return
        try:
            escritas = self._escribir_vista_csv(ruta)
        except Exception as error:
            self._actualizar_status(f"No se pudo escribir el CSV: {error}")
            return
        self._actualizar_status(f"Vista exportada ({escritas} filas) a: {ruta}")

    def _copiar_tabla(self):
        """Copia la tabla visible al portapapeles en TSV (se pega en Excel)."""
        cabecera = list(self.modelo_datos.cabecera())
        filas = self.modelo_datos.filas()
        if not filas:
            self._actualizar_status("No hay nada que copiar: selecciona un método.")
            return
        lineas = ["\t".join(str(c) for c in cabecera)]
        lineas += ["\t".join(str(c) for c in fila) for fila in filas]
        QApplication.clipboard().setText("\n".join(lineas))
        self._actualizar_status(f"Copiadas {len(filas)} filas al portapapeles "
                                "(pégalas directamente en Excel).")

    def _cadena_de(self, indice: int) -> pr.Cadena:
        """Cadena de procesado de una muestra (se crea vacía si no existe)."""
        if indice not in self.cadenas:
            self.cadenas[indice] = pr.Cadena()
        return self.cadenas[indice]

    def _reprocesar(self):
        """La cadena cambió: se vuelve a decodificar y a dibujar."""
        self._sel_muestras()

    def _aplicar_cadena_a_todas(self):
        """Copia la cadena de procesado activa a todas las muestras del método actual."""
        origen = self.panel_proc.cadena()
        if not len(origen) or not self._muestras_actuales:
            self._actualizar_status("No hay pasos en la cadena actual para copiar al método.")
            return
        n_total = len(self._muestras_actuales)
        for idx in range(n_total):
            if self.cadenas.get(idx) is not origen:
                self.cadenas[idx] = origen.copia()
        self._reprocesar()
        self._actualizar_status(
            f"Cadena ({origen.descripcion()}) copiada en lote a las {n_total} muestra(s) del método."
        )

    def _integrar_banda_activa(self, x_a: float, x_b: float):
        """Integra la banda en [x_a, x_b] sobre la primera serie mostrada y la sombrea."""
        from jenway67 import analisis as an

        resultados = getattr(self.panel, "_resultados", None) or []
        modo = getattr(self.panel, "_modo", "") or ""
        if not resultados or modo not in ("spectrum", "kinetics"):
            self._actualizar_status("Selecciona un espectro o cinética para integrar una banda.")
            return
        r0 = resultados[0]
        if modo == "spectrum":
            puntos = r0.get("puntos") or []
        else:
            serie = r0.get("serie") or []
            tiempos = an.tiempos_de(r0)
            puntos = [(float(tiempos[i]), float(s[1]), float(s[2])) for i, s in enumerate(serie)]
        info = an.integrar_banda(puntos, x_a, x_b)
        self.panel_proc.mostrar_resultado_banda(info)
        self.panel.sombrear_banda(info["wl_a"], info["wl_b"])
        self._actualizar_status(
            f"Banda [{info['wl_a']:.1f}–{info['wl_b']:.1f}]: "
            f"área neta = {info['area_neta']:.4f} (bruta = {info['area_bruta']:.4f})."
        )

    def _limpiar_banda_activa(self):
        """Quita el sombreado de banda del gráfico."""
        self.panel.limpiar_banda()
        self._actualizar_status("Banda de integración quitada.")

    def _operar_seleccionadas(self, tipo: str):
        """Crea una traza nueva operando DOS espectros seleccionados."""
        filas = self._filas_seleccionadas()
        if len(filas) != 2:
            self._actualizar_status(
                "Para operar entre espectros hay que seleccionar EXACTAMENTE 2 muestras.")
            return
        if not self.tarjeta or not self.metodo_actual:
            return
        crudos, etiquetas, series = [], [], []
        for indice in filas:
            if indice >= len(self._muestras_actuales):
                return
            etiqueta, loc = self._muestras_actuales[indice]
            try:
                _modo, r = decodificar_archivo(self.tarjeta, loc, self.metodo_actual.modo)
            except Exception as error:
                self._actualizar_status(f"Error al decodificar {loc}: {error}")
                return
            if _modo != "spectrum" or not r or not r.get("puntos"):
                self._actualizar_status(
                    "La operación entre espectros solo vale para espectros "
                    "(ni cinéticas, ni cuantificaciones, ni fotometrías).")
                return
            longitudes, valores = pr.desde_puntos(r["puntos"])
            cadena = self.cadenas.get(indice)
            if cadena and len(cadena):
                longitudes, valores = cadena.aplicar(longitudes, valores)
            crudos.append(r)
            etiquetas.append(etiqueta)
            series.append((longitudes, valores))
        try:
            longitudes, valores = pr.operar(series[0][0], series[0][1],
                                            series[1][0], series[1][1], tipo)
        except ValueError as error:
            self._actualizar_status(f"No se pudo operar: {error}")
            return
        resultado = dict(crudos[0])
        resultado["puntos"] = pr.a_puntos(longitudes, valores)
        resultado["n"] = int(longitudes.size)
        resultado["wl0"] = float(longitudes[0])
        resultado["wl1"] = float(longitudes[-1])
        resultado["intervalo_nm"] = (float(longitudes[1] - longitudes[0])
                                     if longitudes.size > 1 else 0.0)
        resultado["ymin"] = float(min(valores))
        resultado["ymax"] = float(max(valores))
        simbolos = {"resta": "A - B", "suma": "A + B", "media": "(A + B)/2",
                    "cociente": "A / B", "producto": "A x B"}
        nombre = "%s  [%s / %s]" % (simbolos.get(tipo, tipo), etiquetas[0], etiquetas[1])
        aviso = ""
        if not all(valores == valores):  # NaN por división por cero
            aviso = "  (ojo: hay puntos sin valor, la división pasó por cero)"
        self._mostrar("spectrum", [crudos[0], crudos[1], resultado],
                      [etiquetas[0], etiquetas[1], nombre],
                      titulo=f"{self.metodo_actual.nombre} — operación entre espectros")
        self._actualizar_status(f"Añadida la traza {nombre}.{aviso}")

    # ------------------------------------------------------------------ UI
    def _construir_menu(self):
        mb = self.menuBar()
        m_arch = mb.addMenu("Archivo")
        a_abrir = QAction("Abrir tarjeta…", self); a_abrir.triggered.connect(self._dialogo_carpeta)
        a_jwb = QAction("Abrir archivo .JWB…", self); a_jwb.triggered.connect(self._dialogo_jwb)
        a_txt = QAction("Abrir reporte .TXT…", self); a_txt.triggered.connect(self._dialogo_reporte)
        a_ses_abrir = QAction("Abrir sesión (.jws)…", self)
        a_ses_abrir.setShortcut("Ctrl+O")
        a_ses_abrir.triggered.connect(self._dialogo_abrir_sesion)

        a_ses_guardar = QAction("Guardar sesión", self)
        a_ses_guardar.setShortcut("Ctrl+S")
        a_ses_guardar.triggered.connect(self._guardar_sesion_rapido)

        a_ses_guardar_como = QAction("Guardar sesión como…", self)
        a_ses_guardar_como.setShortcut("Ctrl+Shift+S")
        a_ses_guardar_como.triggered.connect(self._dialogo_guardar_sesion_como)

        a_exp = QAction("Exportar Excel…", self); a_exp.triggered.connect(self._exportar_excel)
        a_expc = QAction("Exportar CSV…", self); a_expc.triggered.connect(self._exportar_csv)
        a_pdf = QAction("Exportar PDF…", self); a_pdf.triggered.connect(self._exportar_pdf)
        a_jdx = QAction("Exportar JCAMP-DX (.jdx)…", self); a_jdx.triggered.connect(self._exportar_jcamp)
        a_vista = QAction("Exportar la vista a CSV…", self)
        a_vista.triggered.connect(self._exportar_vista_csv)
        a_vista.setToolTip("Guarda lo que se ve ahora mismo, con el procesado aplicado.")
        a_copiar = QAction("Copiar la tabla", self)
        a_copiar.triggered.connect(self._copiar_tabla)
        a_salir = QAction("Salir", self); a_salir.triggered.connect(self.close)
        for a in (a_abrir, a_jwb, a_txt, a_ses_abrir): m_arch.addAction(a)
        m_arch.addSeparator()
        for a in (a_ses_guardar, a_ses_guardar_como): m_arch.addAction(a)
        m_arch.addSeparator()
        for a in (a_exp, a_expc, a_pdf, a_jdx): m_arch.addAction(a)
        m_arch.addSeparator()
        # Lo que se VE (con el procesado ya aplicado), no la tarjeta entera.
        for a in (a_vista, a_copiar): m_arch.addAction(a)
        m_arch.addSeparator(); m_arch.addAction(a_salir)

        m_ver = mb.addMenu("Ver")
        a_osc = QAction("Tema oscuro", self); a_osc.triggered.connect(lambda: self.set_tema("dark"))
        a_cla = QAction("Tema claro", self); a_cla.triggered.connect(lambda: self.set_tema("light"))
        m_ver.addAction(a_osc); m_ver.addAction(a_cla)
        # El interruptor del panel de procesado se añade aquí cuando se construye
        # el dock; se guarda el menú para no crear un segundo "Ver".
        self.menu_ver = m_ver

        m_ayuda = mb.addMenu("Ayuda")
        a_ac = QAction("Acerca de", self); a_ac.triggered.connect(self._acerca)
        m_ayuda.addAction(a_ac)

    def _construir_sidebar(self) -> QWidget:
        w = QWidget()
        w.setObjectName("Sidebar")
        w.setFixedHeight(48)
        h = QHBoxLayout(w)
        h.setContentsMargins(14, 6, 14, 6)
        h.setSpacing(8)

        titulo = QLabel("Jenway 6705")
        titulo.setObjectName("Titulo")
        sub = QLabel("UV/Vis · 57600 8N1")
        sub.setObjectName("SubtituloMarca")
        h.addWidget(titulo)
        h.addWidget(sub)
        h.addSpacing(10)

        self.btn_datos = QPushButton("Datos y Espectros")
        self.btn_conf = QPushButton("Configuración")
        for b in (self.btn_datos, self.btn_conf):
            b.setCheckable(True)
            b.setAutoExclusive(True)
        self.btn_datos.setChecked(True)
        self.btn_datos.clicked.connect(lambda: self.stack.setCurrentIndex(0))
        self.btn_conf.clicked.connect(lambda: self.stack.setCurrentIndex(1))
        h.addWidget(self.btn_datos)
        h.addWidget(self.btn_conf)
        h.addSpacing(8)

        btn_abrir_rapido = QPushButton("Abrir tarjeta…")
        btn_abrir_rapido.setToolTip("Cargar carpeta de tarjeta SD (.JWX / .JWB)")
        btn_abrir_rapido.clicked.connect(self._dialogo_carpeta)
        btn_txt_rapido = QPushButton("Abrir .TXT…")
        btn_txt_rapido.setToolTip("Abrir un reporte .TXT impreso por el Jenway 6705")
        btn_txt_rapido.clicked.connect(self._dialogo_reporte)
        btn_abrir_ses = QPushButton("Abrir sesión…")
        btn_abrir_ses.setToolTip("Abrir una sesión guardada (.jws) con toda la interfaz, procesado y marcas")
        btn_abrir_ses.clicked.connect(self._dialogo_abrir_sesion)
        btn_guardar_ses = QPushButton("Guardar sesión")
        btn_guardar_ses.setToolTip("Guardar la sesión actual (.jws) con todos los métodos, procesado, bitácora y gráficos (Ctrl+S)")
        btn_guardar_ses.clicked.connect(self._guardar_sesion_rapido)
        btn_proc_rapido = QPushButton("Procesado espectral")
        btn_proc_rapido.setToolTip("Ir al panel de procesado espectral e integración de banda (AUC)")
        btn_proc_rapido.clicked.connect(self._ir_a_procesado)
        h.addWidget(btn_abrir_rapido)
        h.addWidget(btn_txt_rapido)
        h.addWidget(btn_abrir_ses)
        h.addWidget(btn_guardar_ses)
        h.addWidget(btn_proc_rapido)

        h.addStretch(1)

        self.lbl_badge_serie = QLabel("○ RS-232 desconectado")
        self.lbl_badge_serie.setObjectName("BadgeEstadoSerie")
        h.addWidget(self.lbl_badge_serie)

        self.btn_tema_rapido = QPushButton("☀ Tema claro" if self.tema == "dark" else "🌙 Tema oscuro")
        self.btn_tema_rapido.setToolTip("Alternar entre tema oscuro y tema claro")
        self.btn_tema_rapido.clicked.connect(
            lambda: self.set_tema("light" if self.tema == "dark" else "dark")
        )
        h.addWidget(self.btn_tema_rapido)
        return w

    def _construir_pagina_datos(self) -> QWidget:
        split = QSplitter(Qt.Orientation.Horizontal)
        split.setChildrenCollapsible(False)

        # --- izquierda: métodos (árbol por modo + filtros) + muestras ---
        izq = QWidget()
        izq.setMinimumWidth(220)
        vi = QVBoxLayout(izq)
        vi.setContentsMargins(8, 6, 4, 8)
        vi.setSpacing(6)
        g1 = QGroupBox("Métodos")
        v1 = QVBoxLayout(g1)
        v1.setSpacing(6)
        self.busqueda = QLineEdit()
        self.busqueda.setPlaceholderText("Buscar método, usuario o fecha…")
        self.busqueda.setClearButtonEnabled(True)
        self.busqueda.textChanged.connect(self._filtrar)
        v1.addWidget(self.busqueda)
        self.combo_usuario = QComboBox()
        self.combo_usuario.setToolTip("Mostrar sólo los métodos de un usuario")
        self.combo_usuario.currentIndexChanged.connect(self._filtrar)
        v1.addWidget(self.combo_usuario)
        self.arbol_metodos = QTreeWidget()
        self.arbol_metodos.setHeaderHidden(True)
        self.arbol_metodos.setUniformRowHeights(True)
        self.arbol_metodos.setIndentation(14)
        self.arbol_metodos.currentItemChanged.connect(self._sel_item)
        v1.addWidget(self.arbol_metodos)

        g2 = QGroupBox("Muestras (Ctrl/Shift = varias)")
        v2 = QVBoxLayout(g2)
        v2.setSpacing(6)
        self.lista_muestras = QListWidget()
        self.lista_muestras.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self.lista_muestras.itemSelectionChanged.connect(self._sel_muestras)
        v2.addWidget(self.lista_muestras)
        fila_sel = QHBoxLayout()
        b_todas = QPushButton("Todas")
        b_todas.setToolTip("Seleccionar todas las muestras")
        b_todas.clicked.connect(self._seleccionar_todas)
        b_ninguna = QPushButton("Ninguna")
        b_ninguna.setToolTip("Deseleccionar todo")
        b_ninguna.clicked.connect(self.lista_muestras.clearSelection)
        fila_sel.addWidget(b_todas, 1)
        fila_sel.addWidget(b_ninguna, 1)
        v2.addLayout(fila_sel)
        vi.addWidget(g1, 3)
        vi.addWidget(g2, 2)

        # --- centro: pestañas (gráfico interactivo / análisis numérico / datos / consola serie) ---
        centro = QWidget()
        centro.setMinimumWidth(360)
        vc = QVBoxLayout(centro)
        vc.setContentsMargins(4, 6, 4, 8)
        self.tabs = QTabWidget()
        self.panel = PanelGrafico(tema=self.tema)
        self.panel.coordenadas.connect(self._mostrar_coordenadas)
        self.panel.mensaje.connect(self._actualizar_status)
        # Panel extra, en su propia pestaña, para los puntos marcados: se crea al
        # pulsar «Graficar marcados».  Sin controles de marcas (es de sólo lectura).
        self.panel_marcados = PanelGrafico(tema=self.tema, con_marcas=False)
        self.panel_marcados.mensaje.connect(self._actualizar_status)
        self.panel_marcados.coordenadas.connect(self._mostrar_coordenadas)
        self.panel.marcados.connect(self._graficar_marcados)
        self.tabla_analisis = QTableWidget(0, 2)
        self.tabla_analisis.setHorizontalHeaderLabels(["Parámetro / Métrica", "Valor calculado"])
        self.tabla_analisis.horizontalHeader().setStretchLastSection(True)
        self.tabs.addTab(self.panel, "Análisis")
        self.tabs.addTab(self.tabla_analisis, "Análisis numérico")

        # La tabla de puntos de datos va como pestaña aparte: así no le roba
        # altura al gráfico, que es lo importante (sobre todo en cinéticas).
        self.grupo_datos = QWidget()
        vd = QVBoxLayout(self.grupo_datos)
        vd.setContentsMargins(6, 6, 6, 6)
        self.modelo_datos = ModeloTablaDatos(self)
        self.tabla_datos = QTableView()
        self.tabla_datos.setModel(self.modelo_datos)
        self.tabla_datos.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tabla_datos.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tabla_datos.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.tabla_datos.setWordWrap(False)
        self.tabla_datos.setAlternatingRowColors(False)
        # Orden por clic en la cabecera, pero sin reordenar al cargar (indicador -1).
        cab = self.tabla_datos.horizontalHeader()
        cab.setSortIndicator(-1, Qt.SortOrder.AscendingOrder)
        self.tabla_datos.setSortingEnabled(True)
        cab.setDefaultSectionSize(140)
        cab.setStretchLastSection(True)
        self.tabla_datos.verticalHeader().setDefaultSectionSize(24)
        vd.addWidget(self.tabla_datos)
        self.tabs.addTab(self.grupo_datos, "Puntos de datos")

        # Pestaña de Consola Serie (tickets crudos de 40 columnas)
        self.visor_consola = VisorConsolaSerie(self)
        self.visor_consola.mensaje.connect(self._actualizar_status)
        self.visor_consola.cargar_texto_solicitado.connect(self.importar_stream_serie)
        self.tabs.addTab(self.visor_consola, "Consola Serie")

        vc.addWidget(self.tabs, 1)

        # --- derecha: instrumento en vivo fijo arriba + pestañas (Método y Exportar / Procesado) ---
        der = QWidget()
        der.setMinimumWidth(260)
        vdr = QVBoxLayout(der)
        vdr.setContentsMargins(4, 6, 8, 8)
        vdr.setSpacing(6)
        self.panel_serie = PanelConexionSerie(self)
        self.panel_serie.mensaje.connect(self._actualizar_status)
        self.panel_serie.estado_cambiado.connect(self._al_cambiar_estado_serie)
        self.panel_serie.lectura_recibida.connect(self._recibir_lectura_serie)
        vdr.addWidget(self.panel_serie)

        self.tabs_derecha = QTabWidget()
        pag_resumen = QWidget()
        vres = QVBoxLayout(pag_resumen)
        vres.setContentsMargins(2, 2, 2, 2)
        vres.setSpacing(4)

        gdet = QGroupBox("Detalles del método")
        vdet = QVBoxLayout(gdet)
        vdet.setContentsMargins(8, 4, 8, 4)
        self.lbl_detalle = QLabel("—")
        self.lbl_detalle.setWordWrap(True)
        self.lbl_detalle.setMinimumHeight(74)
        vdet.addWidget(self.lbl_detalle)

        gest = QGroupBox("Estado de la sesión")
        vest = QVBoxLayout(gest)
        vest.setContentsMargins(8, 4, 8, 4)
        vest.setSpacing(2)
        self.lbl_estado = QLabel("Sin tarjeta")
        self.lbl_estado.setObjectName("EstadoConectado")
        self.lbl_instr = QLabel("Instrumento en vivo: no conectado")
        self.lbl_instr.setWordWrap(True)
        vest.addWidget(self.lbl_estado)
        vest.addWidget(self.lbl_instr)

        gexp = QGroupBox("Exportar resultados")
        vexp = QVBoxLayout(gexp)
        vexp.setContentsMargins(8, 4, 8, 4)
        vexp.setSpacing(3)
        self.btn_xlsx = QPushButton("Exportar Excel (informe)")
        self.btn_xlsx.setObjectName("BtnExportar")
        self.btn_xlsx.clicked.connect(self._exportar_excel)
        self.btn_csv = QPushButton("Exportar CSV de muestras")
        self.btn_csv.clicked.connect(self._exportar_csv)
        self.btn_pdf = QPushButton("Exportar PDF (reporte)")
        self.btn_pdf.setToolTip("Exporta la vista actual o la sesión completa a un reporte PDF vectorial.")
        self.btn_pdf.clicked.connect(self._exportar_pdf)
        self.btn_jcamp = QPushButton("Exportar JCAMP-DX (.jdx)")
        self.btn_jcamp.setToolTip("Exporta el espectro o cinética activa a formato universal .jdx (Spectragryph).")
        self.btn_jcamp.clicked.connect(self._exportar_jcamp)
        self.btn_copiar_rapido = QPushButton("Copiar tabla al portapapeles")
        self.btn_copiar_rapido.setToolTip("Copia los puntos de datos visibles para pegarlos en Excel")
        self.btn_copiar_rapido.clicked.connect(self._copiar_tabla)
        for b in (self.btn_xlsx, self.btn_csv, self.btn_pdf, self.btn_jcamp, self.btn_copiar_rapido):
            vexp.addWidget(b)

        gses = QGroupBox("Sesión de trabajo")
        vses = QVBoxLayout(gses)
        vses.setContentsMargins(8, 4, 8, 4)
        vses.setSpacing(3)
        self.btn_guardar_sesion = QPushButton("💾 Guardar sesión (.jws)")
        self.btn_guardar_sesion.setToolTip("Guarda la sesión tal cual (métodos, muestras, procesado, bitácora y gráficos) para continuar después.")
        self.btn_guardar_sesion.clicked.connect(self._guardar_sesion_rapido)
        self.btn_abrir_sesion = QPushButton("📂 Abrir sesión guardada…")
        self.btn_abrir_sesion.setToolTip("Abre un archivo de sesión guardado (.jws / .json).")
        self.btn_abrir_sesion.clicked.connect(self._dialogo_abrir_sesion)
        vses.addWidget(self.btn_guardar_sesion)
        vses.addWidget(self.btn_abrir_sesion)

        for w_card in (gdet, gest, gses, gexp):
            vres.addWidget(w_card)
        vres.addStretch(1)
        scroll_resumen = QScrollArea()
        scroll_resumen.setWidgetResizable(True)
        scroll_resumen.setWidget(pag_resumen)
        self.tabs_derecha.addTab(scroll_resumen, "Método y Exportar")
        vdr.addWidget(self.tabs_derecha, 1)

        split.addWidget(izq)
        split.addWidget(centro)
        split.addWidget(der)
        split.setCollapsible(0, False)
        split.setCollapsible(1, False)
        split.setCollapsible(2, False)
        split.setStretchFactor(0, 0)
        split.setStretchFactor(1, 1)
        split.setStretchFactor(2, 0)
        split.setSizes([250, 680, 270])
        self.split = split
        return split

    def _construir_pagina_config(self) -> QWidget:
        w = QWidget(); v = QVBoxLayout(w); v.setContentsMargins(16, 16, 16, 16)
        g = QGroupBox("Apariencia"); vg = QVBoxLayout(g)
        vg.addWidget(QLabel("Tema de la interfaz:"))
        btns = QHBoxLayout()
        b_osc = QPushButton("Oscuro"); b_osc.clicked.connect(lambda: self.set_tema("dark"))
        b_cla = QPushButton("Claro"); b_cla.clicked.connect(lambda: self.set_tema("light"))
        btns.addWidget(b_osc); btns.addWidget(b_cla); btns.addStretch(1)
        vg.addLayout(btns)
        v.addWidget(g)
        g2 = QGroupBox("Fuente de datos"); vg2 = QVBoxLayout(g2)
        vg2.addWidget(QLabel("Carga una carpeta de tarjeta copiada (.JWB/.JWX/.JWU), "
                             "suéltala en la ventana o abre un archivo suelto (.JWB/.TXT)."))
        b_abrir = QPushButton("Abrir tarjeta…"); b_abrir.clicked.connect(self._dialogo_carpeta)
        vg2.addWidget(b_abrir); v.addWidget(g2); v.addStretch(1)
        return w

    # ------------------------------------------------------- carga de tarjeta
    def _dialogo_carpeta(self):
        carpeta = QFileDialog.getExistingDirectory(self, "Selecciona la carpeta de tarjeta")
        if carpeta:
            self.cargar_carpeta(carpeta)

    def _dialogo_jwb(self):
        ruta, _ = QFileDialog.getOpenFileName(self, "Abrir archivo .JWB", "",
                                              "Jenway 6705 (*.JWB *.jwb);;Todos los archivos (*)")
        if ruta:
            self.abrir_jwb(ruta)

    def _dialogo_reporte(self):
        ruta, _ = QFileDialog.getOpenFileName(self, "Abrir reporte .TXT", "",
                                              "Reportes (*.TXT *.txt);;Todos los archivos (*)")
        if ruta:
            self.abrir_reporte(ruta)

    def cargar_carpeta(self, carpeta: str):
        try:
            self.tarjeta = leer_carpeta(carpeta)
        except Exception as e:
            self._avisar_error(f"No se pudo leer la carpeta: {e}")
            return
        self._ruta_sesion_actual = None
        self._actualizar_titulo_sesion()
        self.busqueda.clear()
        self._poblar_usuarios()
        self.lbl_estado.setText(f"Tarjeta cargada — {len(self.tarjeta.metodos)} métodos")
        self._actualizar_status(f"Carpeta: {carpeta}")
        self._poblar_arbol()

    def _poblar_usuarios(self):
        """Combo de filtro por usuario: los del .JWU más los que aparecen en los métodos."""
        self.combo_usuario.blockSignals(True)
        self.combo_usuario.clear()
        self.combo_usuario.addItem("Todos los usuarios", None)
        vistos: List[str] = []
        for u in (self.tarjeta.usuarios if self.tarjeta else []) or []:
            if u.nombre and u.nombre not in vistos:
                vistos.append(u.nombre)
        for m in (self.tarjeta.metodos if self.tarjeta else []) or []:
            if m.usuario and m.usuario not in vistos:
                vistos.append(m.usuario)
        for nombre in vistos:
            self.combo_usuario.addItem(nombre, nombre)
        self.combo_usuario.blockSignals(False)

    # ------------------------------------------------------------ árbol/filtro
    def _metodos_filtrados(self, texto: str, usuario: Optional[str]) -> List[Metodo]:
        """Métodos de la tarjeta que pasan el filtro de usuario y de texto."""
        if not self.tarjeta:
            return []
        res = []
        for m in self.tarjeta.metodos:
            if usuario and (m.usuario or "") != usuario:
                continue
            if texto:
                campos = _normaliza(f"{m.nombre} {m.usuario} {m.fecha} {m.filename} "
                                    f"{m.modo} {etiqueta_modo(m.modo)}")
                if texto not in campos:
                    continue
            res.append(m)
        return res

    def items_de_metodos(self) -> List[QTreeWidgetItem]:
        """Items de método del árbol, en orden de lectura (carpetas primero)."""
        res: List[QTreeWidgetItem] = []
        for i in range(self.arbol_metodos.topLevelItemCount()):
            carpeta = self.arbol_metodos.topLevelItem(i)
            for j in range(carpeta.childCount()):
                res.append(carpeta.child(j))
        return res

    def metodo_en_fila(self, indice: int) -> Optional[Metodo]:
        items = self.items_de_metodos()
        if 0 <= indice < len(items):
            return items[indice].data(0, _TITULO)
        return None

    def seleccionar_metodo(self, indice: int) -> bool:
        items = self.items_de_metodos()
        if 0 <= indice < len(items):
            self.arbol_metodos.setCurrentItem(items[indice])
            return True
        return False

    def _poblar_arbol(self):
        """Agrupa los métodos por modo (con su conteo) aplicando los filtros."""
        anterior = self.metodo_actual
        texto = _normaliza(self.busqueda.text().strip())
        usuario = self.combo_usuario.currentData()

        self.arbol_metodos.blockSignals(True)
        self.arbol_metodos.clear()
        grupos: Dict[str, List[Metodo]] = {}
        for m in self._metodos_filtrados(texto, usuario):
            grupos.setdefault(m.modo, []).append(m)
        for modo in sorted(grupos, key=lambda x: (ORDEN_MODOS.index(x) if x in ORDEN_MODOS else 99, x)):
            metodos = sorted(grupos[modo], key=lambda x: x.fecha)
            carpeta = QTreeWidgetItem([f"{etiqueta_modo(modo)} ({len(metodos)})"])
            carpeta.setIcon(0, self.style().standardIcon(QStyle.StandardPixmap.SP_DirIcon))
            # las carpetas no se seleccionan: sólo agrupan
            carpeta.setFlags(carpeta.flags() & ~Qt.ItemFlag.ItemIsSelectable)
            carpeta.setToolTip(0, f"{etiqueta_modo(modo)}: {len(metodos)} método(s)")
            for m in metodos:
                it = QTreeWidgetItem([f"{m.nombre}  ·  {m.fecha}"])
                it.setData(0, _TITULO, m)
                it.setToolTip(0, f"{m.nombre}\nUsuario: {m.usuario}\nFecha: {m.fecha}\n"
                                 f"Archivo: {m.filename}\nMuestras: {len(m.muestras)}")
                carpeta.addChild(it)
            self.arbol_metodos.addTopLevelItem(carpeta)
            carpeta.setExpanded(True)
        self.arbol_metodos.blockSignals(False)

        items = self.items_de_metodos()
        if not items:
            self.metodo_actual = None
            self._mostrar_sin_metodos("Sin métodos que coincidan con el filtro.")
            return
        # conservar la selección si el método sigue visible; si no, el primero
        it = self._item_de(anterior) if anterior is not None else None
        self.arbol_metodos.setCurrentItem(it or items[0])

    def _item_de(self, metodo: Metodo) -> Optional[QTreeWidgetItem]:
        for it in self.items_de_metodos():
            if it.data(0, _TITULO) is metodo:
                return it
        return None

    def _filtrar(self):
        self._poblar_arbol()

    def _mostrar_sin_metodos(self, mensaje: str):
        self.lista_muestras.blockSignals(True)
        self.lista_muestras.clear()
        self.lista_muestras.blockSignals(False)
        self._muestras_actuales = []
        self.panel.limpiar()
        self.modelo_datos.set_datos([], [])
        self.tabla_analisis.setRowCount(0)
        self._titulo_datos("Puntos de datos")
        self.lbl_detalle.setText("—")
        self._actualizar_status(mensaje)

    def _sel_item(self, actual: Optional[QTreeWidgetItem], _anterior=None):
        if actual is None:
            return
        m = actual.data(0, _TITULO)
        if m is not None:
            self._cargar_metodo(m)

    def _cargar_metodo(self, m: Metodo):
        self.metodo_actual = m
        self.lista_muestras.blockSignals(True)
        self.lista_muestras.clear()
        self.lista_muestras.blockSignals(False)
        self._muestras_actuales = []
        for s in m.muestras:
            self._muestras_actuales.append((s.nombre or "(muestra)", s.loc))
        if not self._muestras_actuales:
            self._muestras_actuales.append(("(método)", m.filename))
        for etq, _loc in self._muestras_actuales:
            self.lista_muestras.addItem(QListWidgetItem(etq))
        self.lbl_detalle.setText(f"Modo: {etiqueta_modo(m.modo)}\nUsuario: {m.usuario}\n"
                                 f"Fecha: {m.fecha}\nArchivo: {m.filename}\n"
                                 f"Muestras: {len(m.muestras)}")
        if self.lista_muestras.count():
            if m.modo in ("photometrics", "quantitation") and m.filename.startswith("serie://"):
                self.lista_muestras.selectAll()
            else:
                self.lista_muestras.setCurrentRow(0)

    # ---------------------------------------------------------------- muestras
    def _filas_seleccionadas(self) -> List[int]:
        return sorted(i.row() for i in self.lista_muestras.selectionModel().selectedRows())

    def _seleccionar_todas(self):
        self.lista_muestras.selectAll()

    def _sel_muestras(self):
        """Decodifica TODAS las muestras seleccionadas (superposición).

        Si una muestra tiene cadena de procesado (Fase 3) se aplica AQUÍ: el
        .JWB se decodifica intacto y el procesado ocurre en memoria, así que
        quitar pasos devuelve siempre el espectro original.
        """
        filas = self._filas_seleccionadas()
        if not filas or not self.metodo_actual or not self.tarjeta:
            if self.metodo_actual is not None:
                self.panel.limpiar()
                self._titulo_datos("Puntos de datos")
                self.modelo_datos.set_datos([], [])
                self.tabla_analisis.setRowCount(0)
            return
        resultados, etiquetas, modo = [], [], None
        primera = None
        fallos = []
        for i in filas:
            if i >= len(self._muestras_actuales):
                continue
            etq, loc = self._muestras_actuales[i]
            try:
                modo_i, r = decodificar_archivo(self.tarjeta, loc, self.metodo_actual.modo)
            except Exception as e:
                fallos.append((loc, str(e)))
                self._actualizar_status(f"Error al decodificar {loc}: {e}")
                continue
            if r is None:
                continue
            modo = modo_i
            r, etq = self._aplicar_cadena(i, modo_i, r, etq)
            if primera is None:
                primera = i
            resultados.append(r)
            etiquetas.append(etq)
        if not resultados:
            self.panel.limpiar()
            if fallos:
                # Ninguna muestra se pudo leer: casi siempre los .JWB no están
                # donde el índice dice.  Hay que decirlo claro, no dejarlo en un
                # aviso discreto que pasa desapercibido.
                self._avisar_error(
                    "No se pudo leer NINGUNA muestra de este método (%d fallo(s)). "
                    "Primero: %s — %s" % (len(fallos), fallos[0][0], fallos[0][1]))
            return
        # El panel edita la cadena de la PRIMERA muestra seleccionada.
        self.panel_proc.poner_cadena(self._cadena_de(
            primera if primera is not None else filas[0]))
        habilitado = modo in ("spectrum", "kinetics")
        self.panel_proc.setEnabled(habilitado)
        self.panel_proc.poner_eje("s" if modo == "kinetics" else "nm")
        self.panel_proc.mostrar_aviso(
            "" if habilitado
            else "El procesado aplica a espectros y cinéticas; este método es de %s."
                 % etiqueta_modo(modo))
        self._mostrar(modo, resultados, etiquetas)

    def _aplicar_cadena(self, indice: int, modo: str, resultado: dict, etiqueta: str):
        """Aplica la cadena de procesado de esa muestra (si tiene alguna).

        Vale para espectros (``puntos``) y cinéticas (``serie``): ambos son listas
        de tuplas (x, %T, Abs), así que el procesado genérico se aplica igual.
        """
        cadena = self.cadenas.get(indice)
        if not cadena or not len(cadena) or modo not in ("spectrum", "kinetics"):
            return resultado, etiqueta
        clave = "puntos" if modo == "spectrum" else "serie"
        puntos = resultado.get(clave)
        if not puntos:
            return resultado, etiqueta
        try:
            longitudes, valores = pr.desde_puntos(puntos)
            longitudes, valores = cadena.aplicar(longitudes, valores)
            procesado = dict(resultado)
            procesado[clave] = pr.a_puntos(longitudes, valores)
            if modo == "spectrum":
                procesado["n"] = int(longitudes.size)
                if longitudes.size:
                    procesado["wl0"] = float(longitudes[0])
                    procesado["wl1"] = float(longitudes[-1])
                    procesado["ymin"] = float(min(valores))
                    procesado["ymax"] = float(max(valores))
            return procesado, f"{etiqueta} · procesado"
        except Exception as error:
            self._actualizar_status(f"No se pudo procesar {etiqueta}: {error}")
            return resultado, etiqueta

    def _titulo_datos(self, texto: str) -> None:
        """Título de la pestaña de puntos de datos (indica qué muestra se ve)."""
        indice = self.tabs.indexOf(self.grupo_datos)
        if indice >= 0:
            self.tabs.setTabText(indice, texto)

    def _graficar_marcados(self):
        """Crea/actualiza la pestaña con el gráfico X-Y de los puntos marcados."""
        reducidos, etiquetas = self.panel.resultados_marcados()
        if not reducidos:
            self._actualizar_status("Los puntos marcados no tienen lecturas utilizables.")
            return
        self.panel_marcados.dibujar(
            "kinetics", reducidos, etiquetas,
            titulo="Puntos marcados — Tiempo vs Absorbancia")
        indice = self.tabs.indexOf(self.panel_marcados)
        if indice < 0:
            self.tabs.addTab(self.panel_marcados, "Puntos marcados")
            indice = self.tabs.count() - 1
        self.tabs.setCurrentIndex(indice)
        self._actualizar_status(
            "Graficados %d punto(s) marcado(s) de %d muestra(s)."
            % (reducidos[0]["n"], len(reducidos)))

    def _quitar_tab_marcados(self):
        """Quita la pestaña de puntos marcados: al cambiar los datos queda obsoleta."""
        indice = self.tabs.indexOf(self.panel_marcados)
        if indice >= 0:
            self.tabs.removeTab(indice)

    # ---------------------------------------------------------- presentación
    def _mostrar(self, modo: str, resultados: List[dict], etiquetas: List[str],
                 titulo: Optional[str] = None):
        self._quitar_tab_marcados()          # los datos nuevos invalidan las marcas
        if titulo is None:
            m = self.metodo_actual
            titulo = f"{m.nombre} — {etiqueta_modo(modo)}" if m else etiqueta_modo(modo)
            if len(resultados) > 1:
                titulo += f"  ({len(resultados)} muestras)"
        self.panel.dibujar(modo, resultados, etiquetas, titulo=titulo)

        # tabla de puntos de datos (sin tope de filas, virtualizada)
        try:
            if modo == "photometrics" and len(resultados) > 1:
                from jenway67.exportar import _abs, _f

                cab = ["Lectura", "Longitud_onda_nm", "Transmitancia_pct", "Absorbancia", "Hora"]
                filas = [
                    [
                        etq,
                        _f(r.get("wl")),
                        _f(r.get("t")),
                        _abs(r.get("abs")),
                        str(r.get("hora") or ""),
                    ]
                    for etq, r in zip(etiquetas, resultados)
                ]
            elif modo == "quantitation" and len(resultados) > 1:
                from jenway67.exportar import _abs, _f

                cab = ["Tipo", "Concentracion", "Absorbancia"]
                filas = [
                    [f"Estandar {i}", _f(c), _abs(a)]
                    for i, (c, a) in enumerate(resultados[0].get("estandares") or [], start=1)
                ]
                for etq, r in zip(etiquetas, resultados):
                    if r.get("abs_muestra") is not None:
                        filas.append([f"Muestra ({etq})", _f(r.get("conc_muestra")), _abs(r.get("abs_muestra"))])
            else:
                cab, filas = filas_para(modo, resultados[0])
        except Exception:
            cab, filas = ["—"], []
        self.modelo_datos.set_datos(cab, filas)
        self._titulo_datos("Puntos de datos" if len(resultados) == 1
                           else f"Puntos de datos — {etiquetas[0]} (de {len(resultados)})")

        # análisis numérico agregado sobre TODO lo seleccionado
        resumen = _analisis_por_modo(modo, [(None, modo, r) for r in resultados])
        self.tabla_analisis.setRowCount(len(resumen))
        for i, (k, v) in enumerate(resumen.items()):
            self.tabla_analisis.setItem(i, 0, QTableWidgetItem(str(k)))
            self.tabla_analisis.setItem(i, 1, QTableWidgetItem(str(v)))
        self.tabla_analisis.resizeColumnsToContents()
        self._avisar_si_vacio(modo, resultados, etiquetas)

    def _avisar_si_vacio(self, modo: str, resultados: List[dict], etiquetas: List[str]):
        """Si lo seleccionado no tiene datos que dibujar, decir POR QUÉ.

        Sin esto la ventana se quedaba en "Sin datos" sin explicación: el caso
        real es una cinética con todas las lecturas saturadas (%T = 0), que el
        parser descarta correctamente y deja la serie con 0 puntos.
        """
        sin_datos = []
        for etiqueta, r in zip(etiquetas, resultados):
            if modo == "spectrum" and not r.get("puntos"):
                sin_datos.append(etiqueta)
            elif modo == "kinetics" and not r.get("serie"):
                sin_datos.append(etiqueta)
        if not sin_datos:
            return
        saturadas = sum(r.get("saturados") or 0 for r in resultados)
        if saturadas:
            self._actualizar_status(
                f"Sin datos que dibujar: {', '.join(sin_datos)} tiene(n) TODAS las "
                f"lecturas saturadas (%T = 0; {saturadas} lectura(s)). "
                "Prueba otra longitud de onda o diluye la muestra.")
        else:
            self._actualizar_status(
                f"Sin datos que dibujar en {', '.join(sin_datos)}: "
                "el archivo no contiene puntos utilizables.")

    def _limpiar_seleccion(self):
        """Suelta la selección del árbol: se está viendo un documento suelto."""
        self.metodo_actual = None
        self._muestras_actuales = []
        # El procesado trabaja sobre muestras de un método (se indexa por
        # muestra), así que con un documento suelto el panel se desactiva.
        self.panel_proc.setEnabled(False)
        self.panel_proc.mostrar_aviso(
            "El procesado trabaja sobre muestras de un método; abre una tarjeta.")
        self.lista_muestras.blockSignals(True)
        self.lista_muestras.clear()
        self.lista_muestras.blockSignals(False)
        self.arbol_metodos.blockSignals(True)
        self.arbol_metodos.setCurrentItem(None)
        self.arbol_metodos.clearSelection()
        self.arbol_metodos.blockSignals(False)

    # --------------------------------------------------- archivos sueltos
    def abrir_jwb(self, ruta: str):
        """Abre un .JWB suelto (sin .JWX): el modo se deduce del contenido."""
        try:
            with open(ruta, "rb") as fh:
                datos = fh.read()
            modo, r = decodificar_jwb(datos, None)
        except Exception as e:
            # Sin modales: el aviso va a la barra de estado (preferencia del usuario).
            self._actualizar_status(f"No se pudo leer el archivo .JWB: {e}")
            return
        self._limpiar_seleccion()
        self._ruta_sesion_actual = None
        self._actualizar_titulo_sesion()
        nombre = os.path.basename(ruta)
        self._mostrar(modo, [r], [nombre], titulo=f"{nombre} — {etiqueta_modo(modo)}")
        self.lbl_detalle.setText(f"Archivo suelto: {nombre}\nModo detectado: {etiqueta_modo(modo)}\n"
                                 "Sin .JWX: el modo se deduce del contenido del .JWB.")
        self._actualizar_status(f"Abierto {nombre} — modo detectado: {etiqueta_modo(modo)}")

    def abrir_reporte(self, ruta: str):
        """Abre un reporte .TXT impreso por el instrumento."""
        try:
            modo, resultados, etiquetas, aviso = cargar_reporte(ruta)
        except Exception as e:
            self._avisar_error(f"No se pudo leer el reporte: {e}")
            return
        nombre = os.path.basename(ruta)
        if not resultados:
            # sin modal: aviso discreto en la barra de estado
            self.lbl_detalle.setText(f"Reporte: {nombre}\nSin datos utilizables.")
            self._actualizar_status(f"{nombre}: {aviso or 'sin datos'}")
            return
        self._limpiar_seleccion()
        self._ruta_sesion_actual = None
        self._actualizar_titulo_sesion()
        self._mostrar(modo, resultados, etiquetas,
                      titulo=f"{nombre} — {etiqueta_modo(modo)} ({len(resultados)} registro/s)")
        self.lbl_detalle.setText(f"Reporte: {nombre}\nModo: {etiqueta_modo(modo)}\n"
                                 f"Registros: {len(resultados)}\n"
                                 "(valores reconstruidos del texto impreso: 3 decimales)")
        self._actualizar_status(f"Reporte {nombre} — {len(resultados)} registro(s) de "
                                f"{etiqueta_modo(modo)}" + (f" — {aviso}" if aviso else ""))

    # -------------------------------------------------------- arrastrar/soltar
    def _acepta_arrastre(self, mime) -> bool:
        return bool(mime and mime.hasUrls()
                    and any(u.toLocalFile() for u in mime.urls()))

    def dragEnterEvent(self, event):
        if self._acepta_arrastre(event.mimeData()):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if self._acepta_arrastre(event.mimeData()):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        if not self._acepta_arrastre(event.mimeData()):
            event.ignore()
            return
        rutas = [u.toLocalFile() for u in event.mimeData().urls() if u.toLocalFile()]
        self._abrir_rutas(rutas)
        event.acceptProposedAction()

    def _abrir_rutas(self, rutas: Sequence[str]):
        """Abre lo que se haya soltado: carpeta = tarjeta; archivo = documento suelto."""
        carpetas = [r for r in rutas if os.path.isdir(r)]
        archivos = [r for r in rutas if os.path.isfile(r)]
        if carpetas:
            self.cargar_carpeta(carpetas[0])
            extra = len(carpetas) - 1 + len(archivos)
            if extra:
                self._actualizar_status(f"Carpeta cargada: {carpetas[0]} "
                                        f"(se ignoraron {extra} ruta/s más)")
            return
        if not archivos:
            self._actualizar_status("No se reconoció ninguna carpeta ni archivo al soltar.")
            return
        self._abrir_archivo(archivos[0])
        if len(archivos) > 1:
            self._actualizar_status(f"Abierto {os.path.basename(archivos[0])} — "
                                    f"se soltaron {len(archivos)} archivos, "
                                    "sólo se abre el primero")

    def _abrir_archivo(self, ruta: str):
        ext = os.path.splitext(ruta)[1].lower()
        if ext in (".jws", ".json"):
            self.abrir_sesion(ruta)
        elif ext == ".jwb":
            self.abrir_jwb(ruta)
        elif ext == ".txt":
            self.abrir_reporte(ruta)
        elif ext in (".jwx", ".jwu"):
            # índice/usuarios sueltos: lo útil es cargar su carpeta como tarjeta
            self.cargar_carpeta(os.path.dirname(ruta))
            self._actualizar_status(f"Cargada la carpeta de {os.path.basename(ruta)}")
        else:
            self._actualizar_status(f"Extensión no soportada: {ext or '(sin extensión)'}")

    # ------------------------------------------------------------------ tema
    def set_tema(self, tema: str):
        self.tema = tema
        app = QApplication.instance()
        if app:
            app.setProperty("_tema_actual", tema)
            app.setStyleSheet(estilos.qss(tema))
        if hasattr(self, "btn_tema_rapido"):
            self.btn_tema_rapido.setText("☀ Tema claro" if tema == "dark" else "🌙 Tema oscuro")
        self.panel.set_tema(tema)
        self.panel_marcados.set_tema(tema)

    # ------------------------------------------------- adquisición serie en vivo
    def _al_cambiar_estado_serie(self, conectado: bool, detalle: str):
        if conectado:
            self.lbl_instr.setText(f"Instrumento en vivo: {detalle}")
            self.lbl_instr.setObjectName("EstadoConectado")
            if hasattr(self, "lbl_badge_serie"):
                self.lbl_badge_serie.setText(detalle)
                self.lbl_badge_serie.setObjectName("BadgeEstadoSerieConectado")
        else:
            self.lbl_instr.setText("Instrumento en vivo: no conectado")
            self.lbl_instr.setObjectName("")
            if hasattr(self, "lbl_badge_serie"):
                self.lbl_badge_serie.setText("○ RS-232 desconectado")
                self.lbl_badge_serie.setObjectName("BadgeEstadoSerie")
        for w_est in (self.lbl_instr, getattr(self, "lbl_badge_serie", None)):
            if w_est is not None and w_est.style() is not None:
                w_est.style().unpolish(w_est)
                w_est.style().polish(w_est)

    def _recibir_lectura_serie(self, lectura: LecturaSerie):
        """Procesa un ticket recibido en vivo por RS-232 y lo integra al árbol."""
        puerto = self.panel_serie.driver.puerto or "RS-232"
        if lectura.texto_crudo:
            self.visor_consola.agregar_bloque(lectura.texto_crudo, origen=puerto)
        n = self._integrar_registros_serie(lectura.registros, origen=puerto)
        if n == 0:
            self._actualizar_status(
                f"Se recibieron {lectura.bytes_recibidos} B de {puerto}, pero sin un ticket reconocible "
                "(revisa la pestaña «Consola Serie»)."
            )

    def importar_stream_serie(self, texto: str, origen: str = "Consola .TXT") -> int:
        """Importa todos los registros y modos de un texto de consola (p. ej. consoladataway.txt)."""
        if texto.strip():
            self.visor_consola.agregar_bloque(texto, origen=os.path.basename(origen) or origen)
        registros = parsear_stream_serie(texto)
        n = self._integrar_registros_serie(registros, origen=os.path.basename(origen) or origen)
        if n == 0:
            self._actualizar_status(f"No se encontraron tickets válidos en {origen}.")
        return n

    def _integrar_registros_serie(self, registros_adaptados, origen: str = "RS-232") -> int:
        if not registros_adaptados:
            return 0
        if self.tarjeta is None:
            self.tarjeta = Tarjeta(carpeta=f"(Sesión en vivo · {origen})")

        ultimo_metodo: Optional[Metodo] = None
        total_muestras = 0

        for reg, modo, resultados, etiquetas in registros_adaptados:
            wl_efectiva = reg.longitud_onda
            fecha_reg = (reg.fecha or "").strip()
            if fecha_reg.startswith("00:00:00"):
                fecha_reg = ""
            if not fecha_reg and resultados and resultados[0].get("hora"):
                fecha_reg = str(resultados[0]["hora"])

            ctx_activo: Dict[str, object] = {}
            if modo == "photometrics":
                if reg.nombre_metodo or reg.usuario or wl_efectiva is not None:
                    self._ultimo_contexto_foto = {
                        "nombre_base": reg.nombre_metodo or f"{etiqueta_modo(modo)} en vivo",
                        "usuario": reg.usuario or "RS-232",
                        "fecha": fecha_reg,
                        "wl": wl_efectiva,
                    }
                elif self._ultimo_contexto_foto:
                    wl_efectiva = self._ultimo_contexto_foto.get("wl")
                ctx_activo = self._ultimo_contexto_foto
            elif modo == "quantitation":
                stds_reg = list(
                    reg.meta.get("__estandares__")
                    or (resultados[0].get("estandares") if resultados else [])
                    or []
                )
                if reg.nombre_metodo or reg.usuario or wl_efectiva is not None or stds_reg:
                    self._ultimo_contexto_quant = {
                        "nombre_base": reg.nombre_metodo or f"{etiqueta_modo(modo)} en vivo",
                        "usuario": reg.usuario or "RS-232",
                        "fecha": fecha_reg,
                        "wl": wl_efectiva,
                        "estandares": stds_reg,
                    }
                elif self._ultimo_contexto_quant:
                    wl_efectiva = self._ultimo_contexto_quant.get("wl")
                ctx_activo = self._ultimo_contexto_quant

            nombre_base = (
                reg.nombre_metodo
                or (ctx_activo.get("nombre_base") if ctx_activo else None)
                or f"{etiqueta_modo(modo)} en vivo"
            )
            nombre_metodo = f"{nombre_base} [RS-232]"
            usuario = (
                reg.usuario
                or (ctx_activo.get("usuario") if ctx_activo else None)
                or "RS-232"
            )
            fecha = (
                fecha_reg
                or (ctx_activo.get("fecha") if ctx_activo else None)
                or ""
            )

            # Buscar si ya existe un método en vivo del mismo modo y nombre
            metodo_dest = None
            for m in self.tarjeta.metodos:
                if m.modo == modo and m.nombre == nombre_metodo and m.filename.startswith("serie://"):
                    metodo_dest = m
                    break
            # Si es una fila fotométrica o de cuantificación sin cabecera y ya hay un método en vivo, anexar a él
            if metodo_dest is None and modo in ("photometrics", "quantitation") and not reg.nombre_metodo:
                for m in reversed(self.tarjeta.metodos):
                    if m.modo == modo and m.filename.startswith("serie://"):
                        metodo_dest = m
                        break

            if metodo_dest is None:
                self._contador_serie += 1
                loc_metodo = f"serie://metodo_{self._contador_serie:04d}"
                metodo_dest = Metodo(
                    id=len(self.tarjeta.metodos) + 1,
                    modo=modo,
                    usuario=str(usuario),
                    nombre=str(nombre_metodo),
                    fecha=str(fecha),
                    filename=loc_metodo,
                    bloqueado=False,
                    muestras=[],
                )
                self.tarjeta.metodos.append(metodo_dest)

            for r, etq in zip(resultados, etiquetas):
                if wl_efectiva is not None and r.get("wl") is None:
                    r["wl"] = wl_efectiva
                if modo == "quantitation" and not r.get("estandares") and ctx_activo.get("estandares"):
                    r["estandares"] = list(ctx_activo["estandares"])
                if not fecha and r.get("hora"):
                    fecha_m = str(r.get("hora"))
                else:
                    fecha_m = str(fecha)

                self._contador_serie += 1
                loc_muestra = f"serie://lectura_{self._contador_serie:04d}"
                registrar_virtual(loc_muestra, modo, r)
                if not metodo_dest.muestras:
                    registrar_virtual(metodo_dest.filename, modo, r)
                num_m = len(metodo_dest.muestras) + 1
                wl_txt = f" ({wl_efectiva:g} nm)" if wl_efectiva else ""
                etiqueta_m = f"#{num_m:03d} · {etq}{wl_txt}"
                metodo_dest.muestras.append(
                    Muestra(
                        indice=num_m,
                        nombre=etiqueta_m,
                        fecha=fecha_m,
                        loc=loc_muestra,
                    )
                )
                total_muestras += 1

            ultimo_metodo = metodo_dest

        self._poblar_usuarios()
        self.lbl_estado.setText(f"Sesión activa — {len(self.tarjeta.metodos)} métodos")
        self._poblar_arbol()

        if ultimo_metodo is not None:
            it = self._item_de(ultimo_metodo)
            if it is not None:
                self.arbol_metodos.setCurrentItem(it)
            if self.lista_muestras.count() > 0:
                if ultimo_metodo.modo in ("photometrics", "quantitation") or total_muestras > 1:
                    self.lista_muestras.selectAll()
                else:
                    self.lista_muestras.setCurrentRow(self.lista_muestras.count() - 1)

        self._actualizar_status(
            f"Capturadas {total_muestras} lectura(s) desde {origen} "
            f"({len(registros_adaptados)} ticket/s procesados)."
        )
        return total_muestras

    # -------------------------------------------------------------- exportar
    def _exportar_excel(self):
        if not self.tarjeta:
            self._actualizar_status("Sin datos: carga una tarjeta primero."); return
        dest = QFileDialog.getExistingDirectory(self, "Carpeta destino del informe")
        if not dest:
            return
        try:
            res = analizar_carpeta(self.tarjeta, dest)
            self._actualizar_status(f"Informe generado: {res['xlsx']} "
                                    f"({len(res['figuras'])} figuras)")
        except Exception as e:
            self._avisar_error(f"No se pudo generar el informe Excel: {e}")

    def _exportar_csv(self):
        if not self.tarjeta:
            self._actualizar_status("Sin datos: carga una tarjeta primero."); return
        dest = QFileDialog.getExistingDirectory(self, "Carpeta destino de los CSV")
        if not dest:
            return
        try:
            escritos = exportar_carpeta(self.tarjeta, dest)
            self._actualizar_status(f"Exportados {len(escritos)} archivos CSV a: {dest}")
        except Exception as e:
            self._avisar_error(f"No se pudieron exportar los CSV: {e}")

    def _exportar_pdf(self, ruta_destino: Optional[str] = None):
        """Exporta la vista activa o la tarjeta completa a un reporte PDF vectorial."""
        resultados_vista = getattr(self.panel, "_resultados", None) or []
        modo_vista = getattr(self.panel, "_modo", "") or ""
        etiquetas_vista = getattr(self.panel, "_etiquetas", None) or []

        if not resultados_vista and not self.tarjeta:
            self._actualizar_status("Sin datos: selecciona una muestra o carga una tarjeta para exportar a PDF.")
            return

        if not ruta_destino:
            sugerido = "reporte_jenway6705.pdf"
            if self.metodo_actual and self.metodo_actual.nombre:
                sugerido = f"reporte_{self.metodo_actual.nombre}.pdf"
            ruta_destino, _ = QFileDialog.getSaveFileName(
                self, "Exportar reporte PDF", sugerido, "PDF (*.pdf)"
            )
            if not ruta_destino:
                return

        try:
            if resultados_vista and modo_vista:
                m = self.metodo_actual
                exportar_vista_pdf(
                    ruta_pdf=ruta_destino,
                    modo=modo_vista,
                    resultados=resultados_vista,
                    etiquetas=etiquetas_vista,
                    titulo=(m.nombre if m else f"Reporte {etiqueta_modo(modo_vista)}"),
                    usuario=(m.usuario if m else ""),
                    fecha=(m.fecha if m else ""),
                )
                self._actualizar_status(f"Reporte PDF exportado a: {ruta_destino}")
            elif self.tarjeta:
                paginas = exportar_tarjeta_pdf(self.tarjeta, ruta_destino)
                self._actualizar_status(f"Reporte PDF consolidado ({paginas} páginas) exportado a: {ruta_destino}")
        except Exception as e:
            self._avisar_error(f"No se pudo generar el PDF: {e}")

    def _exportar_jcamp(self, ruta_destino: Optional[str] = None):
        """Exporta el espectro o cinética activa a formato universal JCAMP-DX (.jdx)."""
        resultados_vista = getattr(self.panel, "_resultados", None) or []
        modo_vista = getattr(self.panel, "_modo", "") or ""
        if not resultados_vista or modo_vista not in ("spectrum", "kinetics"):
            self._actualizar_status(
                "Para exportar a JCAMP-DX (.jdx) selecciona primero un espectro o una cinética."
            )
            return

        if not ruta_destino:
            sugerido = "espectro_6705.jdx"
            if self.metodo_actual and self.metodo_actual.nombre:
                sugerido = f"{self.metodo_actual.nombre}.jdx"
            ruta_destino, _ = QFileDialog.getSaveFileName(
                self, "Exportar JCAMP-DX (.jdx)", sugerido, "JCAMP-DX (*.jdx *.dx)"
            )
            if not ruta_destino:
                return

        try:
            m = self.metodo_actual
            n_pts = exportar_jcamp_dx(
                ruta=ruta_destino,
                modo=modo_vista,
                resultado=resultados_vista[0],
                titulo=(m.nombre if m else "Espectro Jenway 6705"),
                usuario=(m.usuario if m else ""),
                fecha=(m.fecha if m else ""),
            )
            self._actualizar_status(f"Exportado JCAMP-DX ({n_pts} puntos) a: {ruta_destino}")
        except Exception as e:
            self._avisar_error(f"No se pudo exportar JCAMP-DX: {e}")

    # ------------------------------------------------------------- sesiones (.jws)
    def _actualizar_titulo_sesion(self):
        if self._ruta_sesion_actual:
            nombre = os.path.basename(self._ruta_sesion_actual)
            self.setWindowTitle(f"Programa Maestro — Jenway 6705 [{nombre}]")
        else:
            self.setWindowTitle("Programa Maestro — Jenway 6705")

    def _guardar_sesion_rapido(self):
        """Guardar sesión (Ctrl+S): guarda directamente sobre el archivo actual o pregunta si es nueva."""
        self.guardar_sesion(ruta_destino=self._ruta_sesion_actual)

    def _dialogo_guardar_sesion_como(self):
        """Guardar sesión como... (Ctrl+Shift+S): solicita un nuevo nombre de archivo."""
        sug = "sesion_jenway6705.jws"
        if self._ruta_sesion_actual:
            sug = os.path.basename(self._ruta_sesion_actual)
        elif self.metodo_actual and self.metodo_actual.nombre:
            sug_limpio = "".join(c for c in self.metodo_actual.nombre if c.isalnum() or c in (" ", "-", "_")).strip()
            if sug_limpio:
                sug = f"sesion_{sug_limpio.replace(' ', '_')}.jws"
        ruta, _ = QFileDialog.getSaveFileName(
            self, "Guardar sesión como…", sug,
            "Sesión de Maestro (*.jws);;Sesión JSON (*.json);;Todos los archivos (*)"
        )
        if ruta:
            self.guardar_sesion(ruta_destino=ruta)

    def _dialogo_abrir_sesion(self):
        ruta, _ = QFileDialog.getOpenFileName(
            self, "Abrir sesión guardada", "",
            "Sesión de Maestro (*.jws *.json);;Todos los archivos (*)"
        )
        if ruta:
            self.abrir_sesion(ruta)

    def guardar_sesion(self, ruta_destino: Optional[str] = None):
        """Guarda el estado completo de la sesión actual en un archivo .jws o .json."""
        resultados_panel = getattr(self.panel, "_resultados", None) or []
        if not self.tarjeta and not resultados_panel:
            self._actualizar_status("No hay datos cargados en la sesión para guardar.")
            return

        if not ruta_destino:
            if self._ruta_sesion_actual:
                ruta_destino = self._ruta_sesion_actual
            else:
                sug = "sesion_jenway6705.jws"
                if self.metodo_actual and self.metodo_actual.nombre:
                    sug_limpio = "".join(c for c in self.metodo_actual.nombre if c.isalnum() or c in (" ", "-", "_")).strip()
                    if sug_limpio:
                        sug = f"sesion_{sug_limpio.replace(' ', '_')}.jws"
                ruta, _ = QFileDialog.getSaveFileName(
                    self, "Guardar sesión de Maestro", sug,
                    "Sesión de Maestro (*.jws);;Sesión JSON (*.json);;Todos los archivos (*)"
                )
                if not ruta:
                    return
                ruta_destino = ruta

        try:
            from jenway67.reader import _ARCHIVOS_VIRTUALES, resolver_ruta
            from jenway67.sesion import guardar_sesion_archivo, tarjeta_a_dict

            cadenas_dict = {str(k): cad.pasos for k, cad in self.cadenas.items()}
            grafico_dict = {
                "modo": getattr(self.panel, "_modo", "") or "",
                "unidad": self.panel.unidad,
                "vista_apilada": self.panel.btn_vista.isChecked(),
                "picos": self.panel.chk_picos.isChecked(),
                "prominencia": self.panel.spin_prominencia.value(),
                "fwhm": self.panel.chk_fwhm.isChecked(),
                "y_min": self.panel.txt_y_min.text(),
                "y_max": self.panel.txt_y_max.text(),
                "marcas": list(self.panel._marcas),
                "intervalo_marcas": self.panel.spin_intervalo.value(),
                "banda": list(self.panel._banda) if self.panel._banda else None,
            }
            ui_dict = {
                "tab_principal": self.tabs.currentIndex(),
                "tab_derecha": self.tabs_derecha.currentIndex() if hasattr(self, "tabs_derecha") else 0,
                "busqueda": self.busqueda.text(),
                "usuario_filtro": self.combo_usuario.currentData(),
            }

            datos_sesion = {
                "tema": self.tema,
                "cadenas_procesado": cadenas_dict,
                "grafico": grafico_dict,
                "ui": ui_dict,
            }

            if self.tarjeta:
                datos_sesion["origen_carpeta"] = self.tarjeta.carpeta
                datos_sesion["tarjeta"] = tarjeta_a_dict(self.tarjeta)
                if self.metodo_actual:
                    datos_sesion["metodo_actual_id"] = self.metodo_actual.id
                    datos_sesion["metodo_actual_nombre"] = self.metodo_actual.nombre
                    datos_sesion["metodo_actual_filename"] = self.metodo_actual.filename
                datos_sesion["muestras_seleccionadas_indices"] = self._filas_seleccionadas()

            if not self.tarjeta or not self.metodo_actual:
                if resultados_panel:
                    datos_sesion["documento_suelto"] = {
                        "modo": self.panel._modo,
                        "resultados": resultados_panel,
                        "etiquetas": self.panel._etiquetas,
                        "titulo": self.panel._titulo,
                        "detalle": self.lbl_detalle.text(),
                    }

            if _ARCHIVOS_VIRTUALES:
                datos_sesion["archivos_virtuales"] = {
                    k: [v[0], v[1]] for k, v in _ARCHIVOS_VIRTUALES.items()
                }

            # Recolectar archivos binarios para empacar en el .jws
            archivos_bin = {}
            if self.tarjeta:
                for m in self.tarjeta.metodos:
                    if m.filename and not m.filename.startswith("serie://"):
                        try:
                            r_path = resolver_ruta(self.tarjeta, m.filename)
                            if os.path.isfile(r_path):
                                with open(r_path, "rb") as fh:
                                    archivos_bin[os.path.basename(m.filename)] = fh.read()
                        except Exception:
                            pass
                    for s in m.muestras:
                        if s.loc and not s.loc.startswith("serie://"):
                            try:
                                r_path = resolver_ruta(self.tarjeta, s.loc)
                                if os.path.isfile(r_path):
                                    with open(r_path, "rb") as fh:
                                        archivos_bin[os.path.basename(s.loc)] = fh.read()
                            except Exception:
                                pass
                if self.tarjeta.carpeta and os.path.isdir(self.tarjeta.carpeta):
                    try:
                        for raiz, _sub, ficheros in os.walk(self.tarjeta.carpeta):
                            for f in ficheros:
                                ext_f = os.path.splitext(f)[1].lower()
                                if ext_f in (".jwx", ".jwu"):
                                    fp = os.path.join(raiz, f)
                                    if os.path.isfile(fp):
                                        with open(fp, "rb") as fh:
                                            archivos_bin[f] = fh.read()
                    except Exception:
                        pass

            guardar_sesion_archivo(datos_sesion, ruta_destino, archivos_binarios=archivos_bin)
            self._ruta_sesion_actual = ruta_destino
            self._actualizar_titulo_sesion()
            self._actualizar_status(f"Sesión guardada exitosamente en: {ruta_destino}")
        except Exception as e:
            self._avisar_error(f"Error al guardar la sesión: {e}")

    def abrir_sesion(self, ruta_origen: str):
        """Carga y restaura completamente una sesión guardada desde un archivo .jws o .json."""
        try:
            from jenway67 import procesado as pr
            from jenway67.reader import registrar_virtual
            from jenway67.sesion import cargar_sesion_archivo, dict_a_tarjeta

            manifest, dir_ext = cargar_sesion_archivo(ruta_origen)

            # 1. Tema
            if "tema" in manifest and manifest["tema"] != self.tema:
                self.set_tema(manifest["tema"])

            # 2. Registrar archivos virtuales si los hay
            if "archivos_virtuales" in manifest:
                for loc, (modo_v, res_v) in manifest["archivos_virtuales"].items():
                    registrar_virtual(loc, modo_v, res_v)

            # 3. Documento suelto o Tarjeta
            if manifest.get("documento_suelto"):
                doc = manifest["documento_suelto"]
                self._limpiar_seleccion()
                self._mostrar(doc["modo"], doc["resultados"], doc["etiquetas"], titulo=doc.get("titulo"))
                self.lbl_detalle.setText(doc.get("detalle", ""))
            elif manifest.get("tarjeta"):
                carpeta_base = dir_ext or manifest.get("origen_carpeta", "")
                self.tarjeta = dict_a_tarjeta(manifest["tarjeta"], carpeta_override=carpeta_base)

                ui_info = manifest.get("ui", {})
                self.busqueda.blockSignals(True)
                self.busqueda.setText(ui_info.get("busqueda", ""))
                self.busqueda.blockSignals(False)

                self._poblar_usuarios()
                u_filtro = ui_info.get("usuario_filtro")
                if u_filtro:
                    idx_u = self.combo_usuario.findData(u_filtro)
                    if idx_u >= 0:
                        self.combo_usuario.setCurrentIndex(idx_u)

                self.lbl_estado.setText(f"Sesión cargada — {len(self.tarjeta.metodos)} métodos")
                self._poblar_arbol()

                # Restaurar cadenas de procesado
                self.cadenas.clear()
                for k_str, pasos in manifest.get("cadenas_procesado", {}).items():
                    self.cadenas[int(k_str)] = pr.Cadena(pasos=pasos)

                # Seleccionar el método guardado
                metodo_sel = None
                m_id = manifest.get("metodo_actual_id")
                m_fn = manifest.get("metodo_actual_filename")
                m_nom = manifest.get("metodo_actual_nombre")
                for m in self.tarjeta.metodos:
                    if (m_id is not None and m.id == m_id) or (m_fn and m.filename == m_fn) or (m_nom and m.nombre == m_nom):
                        metodo_sel = m
                        break
                if metodo_sel is not None:
                    it = self._item_de(metodo_sel)
                    if it is not None:
                        self.arbol_metodos.setCurrentItem(it)

                # Seleccionar muestras guardadas
                muestras_idx = manifest.get("muestras_seleccionadas_indices", [])
                if muestras_idx and self.lista_muestras.count():
                    self.lista_muestras.blockSignals(True)
                    self.lista_muestras.clearSelection()
                    for idx in muestras_idx:
                        if 0 <= idx < self.lista_muestras.count():
                            item = self.lista_muestras.item(idx)
                            if item:
                                item.setSelected(True)
                    self.lista_muestras.blockSignals(False)
                    self._sel_muestras()

            # 4. Restaurar configuración del gráfico
            graf = manifest.get("grafico", {})
            if graf:
                if "unidad" in graf:
                    self.panel.combo_unidad.setCurrentIndex(1 if graf["unidad"] == "t" else 0)
                if "vista_apilada" in graf:
                    self.panel.btn_vista.setChecked(bool(graf["vista_apilada"]))
                if "picos" in graf:
                    self.panel.chk_picos.setChecked(bool(graf["picos"]))
                if "prominencia" in graf:
                    self.panel.spin_prominencia.setValue(float(graf["prominencia"]))
                if "fwhm" in graf:
                    self.panel.chk_fwhm.setChecked(bool(graf["fwhm"]))
                if "y_min" in graf:
                    self.panel.txt_y_min.setText(str(graf["y_min"]))
                if "y_max" in graf:
                    self.panel.txt_y_max.setText(str(graf["y_max"]))
                if graf.get("banda"):
                    self.panel.sombrear_banda(float(graf["banda"][0]), float(graf["banda"][1]))
                if graf.get("marcas"):
                    self.panel._marcas = [float(x) for x in graf["marcas"]]
                if "intervalo_marcas" in graf:
                    self.panel.spin_intervalo.setValue(int(graf["intervalo_marcas"]))
                self.panel._render()

            # 5. Restaurar pestañas activas
            ui_info = manifest.get("ui", {})
            if "tab_principal" in ui_info and 0 <= ui_info["tab_principal"] < self.tabs.count():
                self.tabs.setCurrentIndex(ui_info["tab_principal"])
            if "tab_derecha" in ui_info and hasattr(self, "tabs_derecha") and 0 <= ui_info["tab_derecha"] < self.tabs_derecha.count():
                self.tabs_derecha.setCurrentIndex(ui_info["tab_derecha"])

            self._ruta_sesion_actual = ruta_origen
            self._actualizar_titulo_sesion()
            self._actualizar_status(f"Sesión restaurada correctamente: {os.path.basename(ruta_origen)}")
        except Exception as e:
            self._avisar_error(f"No se pudo cargar la sesión: {e}")

    def closeEvent(self, event):
        """Garantiza el cierre seguro del puerto serie al cerrar la ventana."""
        try:
            if hasattr(self, "panel_serie") and self.panel_serie is not None:
                self.panel_serie.desconectar()
        except Exception:
            pass
        super().closeEvent(event)

    def _avisar_error(self, texto: str):
        """Avisa de un error SIN abrir un diálogo modal.

        Un modal bloquea TODA la ventana hasta que lo cierres; si además queda
        detrás de la principal, parece que la aplicación se ha colgado y no se
        puede clicar nada.  El aviso va a la barra de estado y el detalle al
        registro de errores.
        """
        diagnostico.registrar(texto)
        self._actualizar_status(texto)

    def _acerca(self):
        QMessageBox.about(self, "Programa Maestro — Jenway 6705",
                          "Lector/analizador propio para el espectrofotómetro Jenway 6705.\n"
                          "Lee .JWB/.JWX/.JWU de la tarjeta, reportes .TXT y puerto serie RS-232 (57600 8N1).\n\n"
                          "Reemplaza a 67-Series Software Suite y DataWay de Jenway.\n\n"
                          + diagnostico.resumen())

    # ------------------------------------------------------------ barra estado
    def _actualizar_status(self, txt: str):
        self._status_base = txt
        self.statusBar().showMessage(txt)

    def _mostrar_coordenadas(self, texto: str):
        """Lectura del cursor (varias series a la vez) en la barra de estado."""
        self.statusBar().showMessage(texto or self._status_base)

