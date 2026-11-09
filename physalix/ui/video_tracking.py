"""Étalonnage et transfert des points vidéo vers le tableau de mesures."""

from math import hypot, isfinite
import weakref

from PySide6.QtCore import QLocale, Qt
from PySide6.QtGui import QValidator
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QDoubleSpinBox, QFormLayout,
)


class CalibrationLengthSpinBox(QDoubleSpinBox):
    """Accept either decimal separator, keeping Qt's French display and bounds."""

    def _number_text(self, text):
        value = text.strip()
        if self.prefix() and value.startswith(self.prefix().strip()):
            value = value[len(self.prefix().strip()):].strip()
        if self.suffix() and value.endswith(self.suffix().strip()):
            value = value[:-len(self.suffix().strip())].strip()
        return value

    def validate(self, text, pos):
        # Do not interpret grouping or mixed separators as a different length.
        value = self._number_text(text)
        if (any(char not in "0123456789.,+" for char in value)
                or value.count(".") + value.count(",") > 1):
            return QValidator.State.Invalid, text, pos
        state, _, _ = super().validate(value.replace(".", ","), min(pos, len(value)))
        return state, text, pos

    def valueFromText(self, text):
        if self.validate(text, len(text))[0] != QValidator.State.Acceptable:
            raise ValueError("Saisissez une longueur positive valide.")
        return super().valueFromText(self._number_text(text).replace(".", ","))


class CalibrationDialog(QDialog):
    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle("Définir l'étalon")
        layout = QFormLayout(self)
        self.length = CalibrationLengthSpinBox()
        self.length.setLocale(QLocale(QLocale.Language.French))
        self.length.setDecimals(6)
        self.length.setRange(.000001, 1e9)
        self.length.setValue(.1)
        self.length.selectAll()
        layout.addRow("Longueur réelle (m) :", self.length)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Annuler")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)


class TrackingSession:
    def __init__(self, model):
        self.model = model
        self.origin = None
        self.x_direction = 1
        self.y_direction = 1
        self.ruler = None
        self.scale = None
        self.unit = "m"
        self.length = None
        self.columns = None
        self.points = {}
        self.history = []
        self.written_rows = 0
        session = weakref.ref(self)
        def columns_removed(parent, first, last):
            current = session()
            if current is not None and current.columns is not None:
                current.columns = tuple(
                    None if c is None or first <= c <= last else c - (last - first + 1 if c > last else 0)
                    for c in current.columns)
        model.columnsRemoved.connect(columns_removed)

    def calibrate(self, start, end, length, unit):
        distance = hypot(end.x() - start.x(), end.y() - start.y())
        if distance < 1 or not isfinite(length) or length <= 0 or unit not in ("mm", "cm", "m"):
            raise ValueError("Choisissez deux points distants d'au moins un pixel et une longueur positive.")
        self.ruler = (start, end)
        self.scale, self.unit, self.length = length / distance, unit, length
        self.sync()

    def normalize_legacy_unit(self):
        """Convertir une calibration historique en mètres sans changer sa dimension."""
        factor = {"mm": .001, "cm": .01, "m": 1}.get(self.unit)
        if factor is None or self.unit == "m":
            return
        if self.scale is not None:
            self.scale *= factor
        if self.length is not None:
            self.length *= factor
        self.unit = "m"
        self.sync()

    def set_axes(self, x_direction, y_direction):
        if x_direction not in (-1, 1) or y_direction not in (-1, 1):
            raise ValueError("Le sens d'un axe doit valoir −1 ou 1.")
        self.x_direction, self.y_direction = x_direction, y_direction
        self.sync()

    def set_origin(self, point):
        self.origin = point
        if self.columns is None:
            # Réutiliser uniquement le tableau initial entièrement vierge.
            pristine = (self.model.names == ["x", "y"] and self.model.units == ["", ""]
                        and not any(any(row) for row in self.model.rows))
            if pristine:
                self.model.add_quantity()
                self.columns = (0, 1, 2)
            else:
                first = self.model.columnCount()
                for _ in range(3):
                    self.model.add_quantity()
                self.columns = (first, first + 1, first + 2)
            existing = [name for i, name in enumerate(self.model.names) if i not in self.columns]
            suffix = ""
            number = 2
            while any(name + suffix in existing for name in ("x", "y", "t")):
                suffix = f"_{number}"
                number += 1
            for column, name in zip(self.columns, ("x", "y", "t")):
                self.model.setData(self.model.index(0, column), name + suffix)
        self.sync()

    def record(self, index, point, timestamp):
        if self.origin is None or self.scale is None:
            raise ValueError("Définissez l'étalon et l'origine avant de pointer.")
        self.history.append((index, self.points.get(index)))
        self.points[index] = (point, timestamp)
        self.sync()

    def undo(self):
        if not self.history:
            return None
        index, previous = self.history.pop()
        if previous is None:
            del self.points[index]
        else:
            self.points[index] = previous
        self.sync()
        return index

    def sync(self):
        if self.columns is None:
            return
        model = self.model
        for column, unit in zip(self.columns, (self.unit, self.unit, "s")):
            if column is not None:
                model.setData(model.index(model.unit_row, column), unit)
        count = max(self.written_rows, len(self.points))
        while len(model.rows) <= count:
            model.add_row()
        for row in range(count):
            for column in self.columns:
                if column is not None:
                    model.rows[row][column] = ""
        if self.scale is not None:
            for row, (_, (point, timestamp)) in enumerate(sorted(self.points.items())):
                values = (self.x_direction * (point.x() - self.origin.x()) * self.scale,
                          self.y_direction * (self.origin.y() - point.y()) * self.scale, timestamp)
                for column, value in zip(self.columns, values):
                    if column is not None:
                        model.rows[row][column] = format(value, ".12g")
        self.written_rows = len(self.points)
        remaining = [c for c in self.columns if c is not None]
        if count and remaining:
            model.dataChanged.emit(model.index(model.first_data_row, min(remaining)),
                                   model.index(model.first_data_row + count - 1, max(remaining)),
                                   [Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.EditRole])
