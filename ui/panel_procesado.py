# -*- coding: utf-8 -*-
"""Panel de procesado espectral (Fase 3) — no destructivo.

Se construye SOLO a partir del registro de `jenway67.procesado`: los grupos, las
operaciones y los controles de cada parametro salen de ahi, asi que anadir una
operacion al motor la hace aparecer aqui sin tocar este archivo.

El panel no toca los datos: mantiene la cadena de pasos y avisa con la señal
`cambio` para que la ventana vuelva a dibujar.  El espectro original nunca se
modifica, asi que "deshacer" es solo quitar el ultimo paso.
"""
from __future__ import annotations

from typing import Dict, List, Optional

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (QComboBox, QDoubleSpinBox, QFormLayout, QGroupBox,
                               QHBoxLayout, QLabel, QLineEdit, QListWidget,
                               QListWidgetItem, QPushButton, QSpinBox,
                               QVBoxLayout, QWidget)

from jenway67 import procesado as pr


# --------------------------------------------------------------------------
# Creacion / lectura / escritura de controles a partir de un Parametro
# --------------------------------------------------------------------------
def crear_widget(parametro: pr.Parametro) -> QWidget:
    """Widget de edicion adecuado al tipo declarado del parametro."""
    if parametro.tipo == "int":
        widget = QSpinBox()
        minimo = int(parametro.minimo) if parametro.minimo is not None else 0
        maximo = int(parametro.maximo) if parametro.maximo is not None else 10 ** 6
        widget.setRange(minimo, maximo)
        widget.setValue(int(parametro.defecto))
        widget.setSingleStep(2 if "ventana" in parametro.nombre else 1)
        return widget
    if parametro.tipo == "float":
        widget = QDoubleSpinBox()
        widget.setDecimals(4)
        widget.setRange(float(parametro.minimo) if parametro.minimo is not None else -1e9,
                        float(parametro.maximo) if parametro.maximo is not None else 1e9)
        widget.setValue(float(parametro.defecto))
        widget.setSingleStep(0.1)
        return widget
    if parametro.tipo == "opcional_float":
        widget = QLineEdit("")
        widget.setPlaceholderText("vacío = sin límite")
        return widget
    if parametro.tipo == "lista":
        widget = QComboBox()
        widget.addItems([str(opcion) for opcion in parametro.opciones])
        if parametro.defecto is not None:
            indice = widget.findText(str(parametro.defecto))
            if indice >= 0:
                widget.setCurrentIndex(indice)
        return widget
    widget = QLineEdit("" if parametro.defecto is None else str(parametro.defecto))
    return widget


def leer_widget(widget: QWidget, parametro: pr.Parametro):
    """Valor del widget convertido al tipo declarado.

    Lanza ``ValueError`` con un texto entendible si lo escrito no es valido.
    """
    if parametro.tipo == "int":
        return int(widget.value())
    if parametro.tipo == "float":
        return float(widget.value())
    if parametro.tipo == "opcional_float":
        texto = widget.text().strip().replace(",", ".")
        if not texto:
            return None
        try:
            return float(texto)
        except ValueError:
            raise ValueError("%s: '%s' no es un número." % (parametro.etiqueta, texto))
    if parametro.tipo == "lista":
        return widget.currentText()
    return widget.text()


def escribir_widget(widget: QWidget, parametro: pr.Parametro, valor) -> None:
    """Vuelca un valor en el widget (se usa al restaurar una cadena)."""
    if parametro.tipo == "int":
        widget.setValue(int(valor))
    elif parametro.tipo == "float":
        widget.setValue(float(valor))
    elif parametro.tipo == "opcional_float":
        widget.setText("" if valor is None else ("%g" % float(valor)))
    elif parametro.tipo == "lista":
        indice = widget.findText(str(valor))
        if indice >= 0:
            widget.setCurrentIndex(indice)
    else:
        widget.setText("" if valor is None else str(valor))


# --------------------------------------------------------------------------
# Panel
# --------------------------------------------------------------------------
class PanelProcesado(QWidget):
    """Controles de procesado: elegir operacion, aplicarla y ver la cadena."""

    cambio = Signal()                   # la cadena cambio -> la ventana debe repintar
    mensaje = Signal(str)               # aviso para la barra de estado
    operar = Signal(str)                # peticion de operar DOS espectros seleccionados
    aplicar_a_todas = Signal()          # copiar cadena activa a todas las muestras del método
    integrar_banda = Signal(float, float)  # integrar banda en [x_a, x_b]
    limpiar_banda = Signal()            # quitar sombreado de banda

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._cadena = pr.Cadena()
        self._widgets: Dict[str, QWidget] = {}
        self._operacion_actual: Optional[pr.Operacion] = None
        self._eje = "nm"            # "nm" (espectro) o "s" (cinética)
        self._construir()
        self._poblar_grupos()

    # ------------------------------------------------------------- montaje
    def _construir(self) -> None:
        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(8, 8, 8, 8)
        raiz.setSpacing(8)

        # --- aviso (p. ej. "solo espectros y cinéticas"); oculto si está vacío
        self.lbl_aviso = QLabel("")
        self.lbl_aviso.setWordWrap(True)
        self.lbl_aviso.setObjectName("avisoProcesado")
        self.lbl_aviso.setVisible(False)
        raiz.addWidget(self.lbl_aviso)

        # --- operacion a aplicar
        caja = QGroupBox("Operación")
        forma = QVBoxLayout(caja)
        fila = QHBoxLayout()
        self.combo_grupo = QComboBox()
        self.combo_grupo.currentTextChanged.connect(self._poblar_operaciones)
        self.combo_operacion = QComboBox()
        self.combo_operacion.currentTextChanged.connect(self._reconstruir_formulario)
        fila.addWidget(self.combo_grupo, 1)
        fila.addWidget(self.combo_operacion, 2)
        forma.addLayout(fila)
        self.formulario = QFormLayout()
        self.formulario.setContentsMargins(0, 4, 0, 4)
        forma.addLayout(self.formulario)
        self.lbl_ayuda = QLabel("")
        self.lbl_ayuda.setWordWrap(True)
        self.lbl_ayuda.setObjectName("ayudaOperacion")
        forma.addWidget(self.lbl_ayuda)
        self.btn_aplicar = QPushButton("Aplicar a lo seleccionado")
        self.btn_aplicar.clicked.connect(self._aplicar)
        forma.addWidget(self.btn_aplicar)
        raiz.addWidget(caja)

        # --- cadena aplicada
        caja_cadena = QGroupBox("Cadena de procesado")
        vertical = QVBoxLayout(caja_cadena)
        self.lista_pasos = QListWidget()
        self.lista_pasos.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        self.lista_pasos.setMaximumHeight(140)
        vertical.addWidget(self.lista_pasos)
        botones = QHBoxLayout()
        self.btn_quitar = QPushButton("Quitar elegido")
        self.btn_quitar.clicked.connect(self._quitar)
        self.btn_deshacer = QPushButton("Deshacer")
        self.btn_deshacer.clicked.connect(self._deshacer)
        self.btn_limpiar = QPushButton("Limpiar")
        self.btn_limpiar.clicked.connect(self._limpiar)
        for boton in (self.btn_quitar, self.btn_deshacer, self.btn_limpiar):
            botones.addWidget(boton)
        vertical.addLayout(botones)
        self.btn_aplicar_todas = QPushButton("Copiar cadena a todo el método")
        self.btn_aplicar_todas.setToolTip(
            "Copia la cadena de procesado actual a todas las muestras del método activo"
        )
        self.btn_aplicar_todas.clicked.connect(lambda: self.aplicar_a_todas.emit())
        vertical.addWidget(self.btn_aplicar_todas)
        self.lbl_cadena = QLabel("(sin procesar)")
        self.lbl_cadena.setWordWrap(True)
        self.lbl_cadena.setObjectName("resumenCadena")
        vertical.addWidget(self.lbl_cadena)
        raiz.addWidget(caja_cadena)

        # --- entre espectros
        caja_entre = QGroupBox("Entre dos espectros")
        entre = QVBoxLayout(caja_entre)
        self.combo_entre = QComboBox()
        self.combo_entre.addItems(list(pr.OPERACIONES_ENTRE))
        entre.addWidget(self.combo_entre)
        self.btn_operar = QPushButton("Operar las 2 seleccionadas")
        self.btn_operar.clicked.connect(
            lambda: self.operar.emit(self.combo_entre.currentText()))
        entre.addWidget(self.btn_operar)
        raiz.addWidget(caja_entre)

        # --- integración de banda (AUC estilo Spectragryph)
        caja_banda = QGroupBox("Integración de banda (AUC)")
        banda = QVBoxLayout(caja_banda)
        fila_rango = QHBoxLayout()
        self.txt_banda_min = QLineEdit("")
        self.txt_banda_min.setPlaceholderText("Desde (nm)")
        self.txt_banda_max = QLineEdit("")
        self.txt_banda_max.setPlaceholderText("Hasta (nm)")
        fila_rango.addWidget(self.txt_banda_min)
        fila_rango.addWidget(self.txt_banda_max)
        banda.addLayout(fila_rango)
        fila_btn_b = QHBoxLayout()
        self.btn_integrar_banda = QPushButton("Integrar banda")
        self.btn_integrar_banda.setToolTip(
            "Calcula el área bruta, el área de base lineal y el área neta de la banda y la sombrea en el gráfico"
        )
        self.btn_integrar_banda.clicked.connect(self._pedir_integrar_banda)
        self.btn_limpiar_banda = QPushButton("Quitar banda")
        self.btn_limpiar_banda.clicked.connect(self._pedir_limpiar_banda)
        fila_btn_b.addWidget(self.btn_integrar_banda)
        fila_btn_b.addWidget(self.btn_limpiar_banda)
        banda.addLayout(fila_btn_b)
        self.lbl_banda = QLabel("")
        self.lbl_banda.setWordWrap(True)
        self.lbl_banda.setObjectName("resumenBanda")
        banda.addWidget(self.lbl_banda)
        raiz.addWidget(caja_banda)

        raiz.addStretch(1)
        self._refrescar_cadena()

    def _poblar_grupos(self) -> None:
        self.combo_grupo.clear()
        self.combo_grupo.addItems(pr.grupos())

    def _poblar_operaciones(self, grupo: str) -> None:
        self.combo_operacion.blockSignals(True)
        self.combo_operacion.clear()
        for operacion in pr.operaciones_de(grupo):
            self.combo_operacion.addItem(self._etiqueta(operacion.etiqueta), operacion.clave)
        self.combo_operacion.blockSignals(False)
        self._reconstruir_formulario()

    def _reconstruir_formulario(self, _texto: str = "") -> None:
        """Rehace los controles de parametros de la operacion elegida."""
        while self.formulario.count():
            elemento = self.formulario.takeAt(0)
            widget = elemento.widget()
            if widget is not None:
                widget.deleteLater()
        self._widgets.clear()
        operacion = self.operacion_actual()
        if operacion is None:
            self._operacion_actual = None
            self.lbl_ayuda.setText("")
            return
        self._operacion_actual = operacion
        for parametro in operacion.parametros:
            widget = crear_widget(parametro)
            if parametro.ayuda:
                widget.setToolTip(self._etiqueta(parametro.ayuda))
            self.formulario.addRow(self._etiqueta(parametro.etiqueta) + ":", widget)
            self._widgets[parametro.nombre] = widget
        self.lbl_ayuda.setText(self._etiqueta(operacion.ayuda))

    def _etiqueta(self, texto: str) -> str:
        """Reescribe la unidad del eje en las etiquetas ('nm' -> 's' en cinéticas)."""
        return (texto or "").replace("nm", self._eje)

    def poner_eje(self, unidad: Optional[str]) -> None:
        """Cambia la unidad del eje mostrada en las etiquetas ('nm' o 's')."""
        eje = unidad if unidad in ("nm", "s") else "nm"
        self.txt_banda_min.setPlaceholderText(f"Desde ({eje})")
        self.txt_banda_max.setPlaceholderText(f"Hasta ({eje})")
        if eje == self._eje:
            return
        self._eje = eje
        grupo = self.combo_grupo.currentText()
        if grupo:
            self._poblar_operaciones(grupo)

    def mostrar_aviso(self, texto: str) -> None:
        """Aviso visible en lo alto del panel (vacío = oculto)."""
        self.lbl_aviso.setText(texto)
        self.lbl_aviso.setVisible(bool(texto))

    # ----------------------------------------------------------------- API
    def operacion_actual(self) -> Optional[pr.Operacion]:
        clave = self.combo_operacion.currentData()
        return pr.OPERACIONES.get(clave) if clave else None

    def parametros_actuales(self) -> Dict:
        """Lee los controles.  Lanza ``ValueError`` si algo no es válido."""
        operacion = self._operacion_actual
        if operacion is None:
            raise ValueError("No hay operación elegida.")
        valores = {}
        for parametro in operacion.parametros:
            widget = self._widgets.get(parametro.nombre)
            if widget is None:
                continue
            valores[parametro.nombre] = leer_widget(widget, parametro)
        return valores

    def cadena(self) -> pr.Cadena:
        return self._cadena

    def poner_cadena(self, cadena: Optional[pr.Cadena]) -> None:
        """Muestra una cadena ajena (p. ej. la de la muestra seleccionada)."""
        self._cadena = cadena if cadena is not None else pr.Cadena()
        self._refrescar_cadena()

    def resumen(self) -> str:
        return self._cadena.descripcion()

    def mostrar_resultado_banda(self, info: Dict[str, float]) -> None:
        """Muestra las métricas de integración de banda en el panel."""
        u = self._eje
        self.lbl_banda.setText(
            f"Rango: {info['wl_a']:.1f}–{info['wl_b']:.1f} {u}\n"
            f"Área bruta: {info['area_bruta']:.4f}  |  Base: {info['area_base']:.4f}\n"
            f"Área neta: {info['area_neta']:.4f}  (Máx: {info['max_abs']:.3f} en {info['max_wl']:.1f} {u})"
        )

    # ------------------------------------------------------------- acciones
    def _pedir_integrar_banda(self) -> None:
        t_min = self.txt_banda_min.text().strip().replace(",", ".")
        t_max = self.txt_banda_max.text().strip().replace(",", ".")
        if not t_min or not t_max:
            self.mensaje.emit("Indica el rango numérico Desde / Hasta para integrar la banda.")
            return
        try:
            a, b = float(t_min), float(t_max)
        except ValueError:
            self.mensaje.emit("El rango de la banda debe contener números válidos.")
            return
        self.integrar_banda.emit(a, b)

    def _pedir_limpiar_banda(self) -> None:
        self.lbl_banda.setText("")
        self.limpiar_banda.emit()

    def _aplicar(self) -> None:
        operacion = self._operacion_actual
        if operacion is None:
            self.mensaje.emit("Elige una operación.")
            return
        try:
            valores = self.parametros_actuales()
        except ValueError as error:
            self.mensaje.emit(str(error))
            return
        try:
            self._cadena.agregar(operacion.clave, **valores)
        except ValueError as error:
            self.mensaje.emit(str(error))
            return
        self._refrescar_cadena()
        self.mensaje.emit("Procesado: %s" % self._cadena.etiquetas()[-1])
        self.cambio.emit()

    def _quitar(self) -> None:
        fila = self.lista_pasos.currentRow()
        if fila < 0:
            self.mensaje.emit("Elige un paso de la lista para quitarlo.")
            return
        self._cadena.quitar(fila)
        self._refrescar_cadena()
        self.cambio.emit()

    def _deshacer(self) -> None:
        if not self._cadena.deshacer():
            self.mensaje.emit("No hay nada que deshacer.")
            return
        self._refrescar_cadena()
        self.mensaje.emit("Paso deshecho. Cadena: %s" % self._cadena.descripcion())
        self.cambio.emit()

    def _limpiar(self) -> None:
        if not len(self._cadena):
            self.mensaje.emit("La cadena ya está vacía.")
            return
        self._cadena.limpiar()
        self._refrescar_cadena()
        self.mensaje.emit("Procesado borrado: se ve el espectro original.")
        self.cambio.emit()

    def _refrescar_cadena(self) -> None:
        self.lista_pasos.clear()
        for indice, etiqueta in enumerate(self._cadena.etiquetas(), start=1):
            self.lista_pasos.addItem(QListWidgetItem("%d. %s" % (indice, etiqueta)))
        self.lbl_cadena.setText(self._cadena.descripcion())
        hay = bool(len(self._cadena))
        self.btn_deshacer.setEnabled(hay)
        self.btn_quitar.setEnabled(hay)
        self.btn_limpiar.setEnabled(hay)
        self.btn_aplicar_todas.setEnabled(hay)
