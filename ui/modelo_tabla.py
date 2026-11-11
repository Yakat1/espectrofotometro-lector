# -*- coding: utf-8 -*-
"""Modelo de tabla virtualizado para los puntos de datos (QAbstractTableModel).

Sustituye al `QTableWidget`, que creaba un objeto por celda y obligaba a recortar
la tabla a 1.500 filas. Con un modelo, la vista sólo pide las celdas visibles: un
espectro de 7.101 puntos (o de 40.000) se muestra fluido y **sin tope**.

La ordenación por columna es tolerante: los valores numéricos ordenan como
números (así "190.0" < "1.000.0"... es decir, 1000 va después de 190) y el texto
alfabéticamente.
"""
from __future__ import annotations

from typing import List, Optional, Sequence, Tuple

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt

FILAS_MUESTRA_NUMERICA = 20


def clave_orden(valor) -> Tuple[int, float, str]:
    """Clave de ordenación tolerante.

    (0, número, "") si el valor es numérico -> ordena como número;
    (1, 0.0, texto) si no -> ordena alfabéticamente y siempre después de los
    números (p. ej. "Saturado(>3.0)" queda al final)."""
    s = str("" if valor is None else valor).strip()
    try:
        return (0, float(s.replace(",", ".")), "")
    except ValueError:
        return (1, 0.0, s.lower())


class ModeloTablaDatos(QAbstractTableModel):
    """Tabla de sólo lectura sobre una cabecera + lista de filas."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._cabecera: List[str] = []
        self._filas: List[List[str]] = []
        self._numerica: List[bool] = []

    # ------------------------------------------------------------------ API
    def set_datos(self, cabecera: Sequence[str], filas: Sequence[Sequence]) -> None:
        """Reemplaza el contenido (sin límite de filas)."""
        self.beginResetModel()
        self._cabecera = [str(c) for c in (cabecera or [])]
        self._filas = [[("" if v is None else str(v)) for v in fila] for fila in (filas or [])]
        self._numerica = self._detectar_numericas()
        self.endResetModel()

    def cabecera(self) -> List[str]:
        return list(self._cabecera)

    def filas(self) -> List[List[str]]:
        return self._filas

    def es_numerica(self, columna: int) -> bool:
        return 0 <= columna < len(self._numerica) and self._numerica[columna]

    # ------------------------------------------------- QAbstractTableModel
    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._filas)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._cabecera)

    def data(self, index: QModelIndex, rol: int = Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        if rol in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.ToolTipRole):
            fila = self._filas[index.row()] if 0 <= index.row() < len(self._filas) else None
            if fila is None or not (0 <= index.column() < len(fila)):
                return None
            return fila[index.column()]
        if rol == Qt.ItemDataRole.TextAlignmentRole and self.es_numerica(index.column()):
            return Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        return None

    def headerData(self, seccion: int, orientacion: Qt.Orientation,
                   rol: int = Qt.ItemDataRole.DisplayRole):
        if rol != Qt.ItemDataRole.DisplayRole or orientacion != Qt.Orientation.Horizontal:
            return None
        return self._cabecera[seccion] if 0 <= seccion < len(self._cabecera) else None

    def sort(self, columna: int, orden: Qt.SortOrder = Qt.SortOrder.AscendingOrder) -> None:
        """Ordena por columna (lo invoca la cabecera al hacer clic)."""
        if not (0 <= columna < len(self._cabecera)):
            return
        reverso = orden == Qt.SortOrder.DescendingOrder
        self.layoutAboutToBeChanged.emit()
        try:
            self._filas.sort(
                key=lambda f: clave_orden(f[columna] if columna < len(f) else ""),
                reverse=reverso)
        finally:
            self.layoutChanged.emit()

    # -------------------------------------------------------------- interno
    def _detectar_numericas(self) -> List[bool]:
        """Una columna es numérica si todas las primeras filas no vacías lo son
        (se usa para alinear a la derecha)."""
        columnas = len(self._cabecera)
        res: List[bool] = []
        for c in range(columnas):
            muestra: List[Optional[str]] = [f[c] for f in self._filas[:FILAS_MUESTRA_NUMERICA]
                                            if c < len(f) and str(f[c]).strip()]
            res.append(bool(muestra) and all(clave_orden(v)[0] == 0 for v in muestra))
        return res
