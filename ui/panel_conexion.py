# -*- coding: utf-8 -*-
"""Panel de conexión serie segura en vivo y visor de consola de 40 columnas.

Conecta la interfaz PySide6 con :class:`jenway67.puerto_jenway.Jenway6705Serial`
respetando las 7 Reglas de Oro de Seguridad de Hardware:
  * Velocidad y trama fijas a ``57600 8N1`` (``DTR=True``, ``RTS=True``, sin flujo).
  * Bloqueo de botones (exclusión mutua) durante el handshake ``b'*'`` y la
    lectura ``b'#'`` para impedir doble clic o colisión de comandos.
  * Escucha periódica no bloqueante para capturar impresiones iniciadas desde
    el botón físico ``PRINT`` del espectrofotómetro.
"""
from __future__ import annotations

import time
from datetime import datetime
from typing import Callable, Optional

from PySide6.QtCore import QTimer, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from jenway67.puerto_jenway import (
    PUERTO_SIMULADOR,
    Jenway6705Serial,
    LecturaSerie,
    SimuladorJenway6705,
    _abridor_por_defecto,
    listar_puertos_serie,
)


class PanelConexionSerie(QGroupBox):
    """Controles de conexión RS-232 en vivo para el panel derecho de la ventana."""

    estado_cambiado = Signal(bool, str)   # (conectado, texto_estado)
    lectura_recibida = Signal(object)     # LecturaSerie
    mensaje = Signal(str)                 # texto para la barra de estado

    def __init__(
        self,
        parent: Optional[QWidget] = None,
        abridor: Optional[Callable[[str], object]] = None,
    ):
        super().__init__("Instrumento en vivo (RS-232)", parent)
        self._abridor_custom = abridor
        self.driver = self._crear_driver(PUERTO_SIMULADOR)
        self._ocupado = False

        self._timer_auto = QTimer(self)
        self._timer_auto.setInterval(450)
        self._timer_auto.timeout.connect(self._sondear_impresion_espontanea)

        self._construir_ui()
        self.refrescar_puertos()

    def _crear_driver(self, puerto: str) -> Jenway6705Serial:
        """Usa esperas reales de hardware para puertos COM físicos y reloj rápido en simulador."""
        es_sim = puerto.upper().startswith(PUERTO_SIMULADOR)
        if self._abridor_custom is not None:
            return Jenway6705Serial(
                abridor=self._abridor_custom,
                dormir=(lambda _s: None),
            )
        if es_sim:
            reloj_virtual = [0.0]

            def _reloj_sim() -> float:
                return reloj_virtual[0]

            def _dormir_sim(seg: float) -> None:
                reloj_virtual[0] += float(seg)

            return Jenway6705Serial(
                abridor=_abridor_por_defecto,
                reloj=_reloj_sim,
                dormir=_dormir_sim,
            )
        return Jenway6705Serial(
            abridor=_abridor_por_defecto,
            reloj=time.monotonic,
            dormir=time.sleep,
        )

    def _construir_ui(self) -> None:
        v = QVBoxLayout(self)
        v.setSpacing(6)

        fila_puerto = QHBoxLayout()
        self.combo_puerto = QComboBox()
        self.combo_puerto.setToolTip(
            "Puerto serie del Jenway 6705 (57600 8N1 fijo) o Simulador virtual"
        )
        self.btn_refrescar = QPushButton("↻")
        self.btn_refrescar.setFixedWidth(32)
        self.btn_refrescar.setToolTip("Actualizar lista de puertos COM")
        self.btn_refrescar.clicked.connect(self.refrescar_puertos)
        fila_puerto.addWidget(self.combo_puerto, 1)
        fila_puerto.addWidget(self.btn_refrescar)
        v.addLayout(fila_puerto)

        self.lbl_estado = QLabel("Desconectado · 57600 8N1")
        self.lbl_estado.setWordWrap(True)
        self.lbl_estado.setObjectName("EstadoSerieDesconectado")
        v.addWidget(self.lbl_estado)

        fila_btns = QHBoxLayout()
        self.btn_conectar = QPushButton("Conectar (*)")
        self.btn_conectar.setToolTip(
            "Abre el puerto a 57600 8N1, espera 100 ms y envía 1 byte '*' para verificar '67XX'"
        )
        self.btn_conectar.clicked.connect(self.alternar_conexion)

        self.btn_leer = QPushButton("Capturar lectura (#)")
        self.btn_leer.setObjectName("BtnExportar")
        self.btn_leer.setEnabled(False)
        self.btn_leer.setToolTip(
            "Envía 1 byte '#' al Jenway 6705 y recibe el ticket completo de la medición actual"
        )
        self.btn_leer.clicked.connect(self.capturar_lectura)
        fila_btns.addWidget(self.btn_conectar, 2)
        fila_btns.addWidget(self.btn_leer, 3)
        v.addLayout(fila_btns)

        self.chk_auto_print = QCheckBox("Auto-capturar al pulsar PRINT en el equipo")
        self.chk_auto_print.setChecked(True)
        self.chk_auto_print.setToolTip(
            "Detecta automáticamente si pulsas el botón físico PRINT en el espectrofotómetro"
        )
        v.addWidget(self.chk_auto_print)

    def _refrescar_estilo_estado(self, nombre_obj: str) -> None:
        self.lbl_estado.setObjectName(nombre_obj)
        st = self.lbl_estado.style()
        if st is not None:
            st.unpolish(self.lbl_estado)
            st.polish(self.lbl_estado)

    # --------------------------------------------------------- gestión puertos
    def refrescar_puertos(self) -> None:
        actual = self.puerto_seleccionado()
        self.combo_puerto.blockSignals(True)
        self.combo_puerto.clear()
        for info in listar_puertos_serie(incluir_simulador=True):
            codigo = info["puerto"]
            desc = info["descripcion"]
            tag = " [FTDI]" if info.get("es_ftdi") else ""
            etiqueta = f"{codigo} — {desc}{tag}" if desc and desc != codigo else f"{codigo}{tag}"
            self.combo_puerto.addItem(etiqueta, codigo)
        if actual:
            idx = self.combo_puerto.findData(actual)
            if idx >= 0:
                self.combo_puerto.setCurrentIndex(idx)
        self.combo_puerto.blockSignals(False)

    def puerto_seleccionado(self) -> str:
        dato = self.combo_puerto.currentData()
        if dato:
            return str(dato)
        return self.combo_puerto.currentText().split("—")[0].strip()

    def seleccionar_puerto(self, puerto: str) -> bool:
        idx = self.combo_puerto.findData(puerto)
        if idx < 0:
            self.combo_puerto.addItem(puerto, puerto)
            idx = self.combo_puerto.count() - 1
        self.combo_puerto.setCurrentIndex(idx)
        return True

    # --------------------------------------------------- acciones de conexión
    def _bloquear_controles(self, ocupado: bool) -> None:
        self._ocupado = ocupado
        conectado = self.driver.conectado
        self.combo_puerto.setEnabled(not ocupado and not conectado)
        self.btn_refrescar.setEnabled(not ocupado and not conectado)
        self.btn_conectar.setEnabled(not ocupado)
        self.btn_leer.setEnabled(not ocupado and conectado)
        QApplication.processEvents()

    def alternar_conexion(self) -> bool:
        if self.driver.conectado:
            self.desconectar()
            return False
        return self.conectar()

    def conectar(self, puerto: Optional[str] = None) -> bool:
        if self._ocupado:
            return False
        if puerto is not None:
            self.seleccionar_puerto(puerto)
        elegido = self.puerto_seleccionado()
        self.driver = self._crear_driver(elegido)

        self._bloquear_controles(True)
        self.lbl_estado.setText(f"Conectando con {elegido} (57600 8N1)…")
        self.mensaje.emit(f"Enviando handshake seguro '*' a {elegido} (57600 8N1)…")
        try:
            ok, detalle = self.driver.conectar(elegido)
        finally:
            self._bloquear_controles(False)

        if ok:
            self.btn_conectar.setText("Desconectar")
            self.lbl_estado.setText(f"● Conectado: {self.driver.identificacion} ({elegido})")
            self._refrescar_estilo_estado("EstadoConectado")
            self._timer_auto.start()
            self.estado_cambiado.emit(True, self.lbl_estado.text())
            self.mensaje.emit(detalle)
            return True

        self.btn_conectar.setText("Conectar (*)")
        self.lbl_estado.setText("Sin conexión · 57600 8N1")
        self._refrescar_estilo_estado("EstadoSerieDesconectado")
        self.estado_cambiado.emit(False, detalle)
        self.mensaje.emit(detalle)
        return False

    def desconectar(self) -> None:
        self._timer_auto.stop()
        puerto_prev = self.driver.puerto
        self.driver.desconectar()
        self._bloquear_controles(False)
        self.btn_conectar.setText("Conectar (*)")
        self.lbl_estado.setText("Desconectado · 57600 8N1")
        self._refrescar_estilo_estado("EstadoSerieDesconectado")
        aviso = f"Puerto {puerto_prev} desconectado de forma segura." if puerto_prev else "Desconectado."
        self.estado_cambiado.emit(False, self.lbl_estado.text())
        self.mensaje.emit(aviso)

    def capturar_lectura(self) -> Optional[LecturaSerie]:
        """Solicita una lectura con ``b'#'`` bloqueando el botón hasta drenar el ticket."""
        if self._ocupado or not self.driver.conectado:
            self.mensaje.emit("Conecta primero el espectrofotómetro antes de pedir una lectura.")
            return None

        self._bloquear_controles(True)
        self.lbl_estado.setText(f"Recibiendo datos de {self.driver.puerto}…")
        self.mensaje.emit(f"Solicitud '#' enviada a {self.driver.puerto}; esperando ticket completo…")
        try:
            lectura = self.driver.solicitar_lectura()
        except Exception as error:
            self._bloquear_controles(False)
            self.lbl_estado.setText(f"Conectado: {self.driver.identificacion} ({self.driver.puerto})")
            self.mensaje.emit(f"Error durante la lectura serie: {error}")
            return None

        self._bloquear_controles(False)
        self.lbl_estado.setText(f"Conectado: {self.driver.identificacion} ({self.driver.puerto})")

        if not lectura.bytes_recibidos:
            self.mensaje.emit(
                "El equipo no envió datos tras '#'. Verifica que haya una medición en pantalla."
            )
            return lectura

        self.lectura_recibida.emit(lectura)
        return lectura

    def _sondear_impresion_espontanea(self) -> None:
        if self._ocupado or not self.driver.conectado or not self.chk_auto_print.isChecked():
            return
        lectura = self.driver.leer_impresion_espontanea()
        if lectura is not None and lectura.bytes_recibidos > 0:
            self.lectura_recibida.emit(lectura)


class VisorConsolaSerie(QWidget):
    """Pestaña con el ticket crudo de 40 columnas (estilo impresora térmica del 6705)."""

    cargar_texto_solicitado = Signal(str, str)   # (texto, nombre_origen)
    simular_print_solicitado = Signal()
    mensaje = Signal(str)

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        v = QVBoxLayout(self)
        v.setContentsMargins(6, 6, 6, 6)
        v.setSpacing(6)

        barra = QHBoxLayout()
        lbl = QLabel(
            "Stream crudo RS-232 (tickets de 40 columnas recibidos del Jenway 6705):"
        )
        barra.addWidget(lbl)
        barra.addStretch(1)

        self.btn_cargar_captura = QPushButton("Importar captura .TXT…")
        self.btn_cargar_captura.setToolTip(
            "Carga un archivo de captura de consola (p. ej. consoladataway.txt) con todos sus modos"
        )
        self.btn_cargar_captura.clicked.connect(self._dialogo_importar)

        self.btn_guardar = QPushButton("Guardar consola (.TXT)…")
        self.btn_guardar.setToolTip("Guarda todo el texto recibido en la sesión como archivo .TXT")
        self.btn_guardar.clicked.connect(self._dialogo_guardar)

        self.btn_limpiar = QPushButton("Limpiar")
        self.btn_limpiar.clicked.connect(self.limpiar)

        for b in (self.btn_cargar_captura, self.btn_guardar, self.btn_limpiar):
            barra.addWidget(b)
        v.addLayout(barra)

        self.editor = QPlainTextEdit()
        self.editor.setReadOnly(True)
        fuente = QFont("Consolas", 10)
        fuente.setStyleHint(QFont.StyleHint.Monospace)
        self.editor.setFont(fuente)
        self.editor.setPlaceholderText(
            "Aquí aparecerán los tickets de 40 columnas recibidos por el puerto serie "
            "(MODO FOTOMETRÍA, MODO CINÉTICA, MODO ESPECTRO, etc.)."
        )
        v.addWidget(self.editor, 1)

    def agregar_bloque(self, texto: str, origen: str = "RS-232") -> None:
        marca = datetime.now().strftime("%H:%M:%S")
        cab = f"--- [{marca} · {origen}] ---"
        actual = self.editor.toPlainText()
        bloque = f"{cab}\n{texto.strip()}\n"
        self.editor.setPlainText(f"{actual}\n{bloque}".lstrip() if actual else bloque)
        cursor = self.editor.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        self.editor.setTextCursor(cursor)

    def texto(self) -> str:
        return self.editor.toPlainText()

    def limpiar(self) -> None:
        self.editor.clear()

    def _dialogo_guardar(self) -> None:
        contenido = self.texto().strip()
        if not contenido:
            self.mensaje.emit("La consola serie está vacía; no hay nada que guardar.")
            return
        ruta, _ = QFileDialog.getSaveFileName(
            self, "Guardar consola serie", "captura_6705.txt", "Texto (*.txt *.TXT)"
        )
        if not ruta:
            return
        try:
            with open(ruta, "w", encoding="utf-8") as fh:
                fh.write(contenido + "\n")
            self.mensaje.emit(f"Consola serie guardada en: {ruta}")
        except Exception as error:
            self.mensaje.emit(f"No se pudo guardar la consola: {error}")

    def _dialogo_importar(self) -> None:
        ruta, _ = QFileDialog.getOpenFileName(
            self,
            "Importar captura serie o reporte .TXT",
            "",
            "Capturas de texto (*.txt *.TXT);;Todos los archivos (*)",
        )
        if not ruta:
            return
        try:
            with open(ruta, "rb") as fh:
                crudo = fh.read()
            from jenway67.parser_txt import _decodificar

            texto = _decodificar(crudo)
        except Exception as error:
            self.mensaje.emit(f"No se pudo leer {ruta}: {error}")
            return
        self.cargar_texto_solicitado.emit(texto, ruta)
