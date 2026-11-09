"""Tableau de mesures : une grandeur par colonne, une mesure par ligne."""

import csv
import io
import re
import math
import json

from PySide6.QtCore import QAbstractTableModel, QEvent, QItemSelection, QItemSelectionModel, QMimeData, QModelIndex, QPersistentModelIndex, Qt, Signal
from PySide6.QtGui import QKeySequence, QPainter, QRegularExpressionValidator, QColor, QBrush, QPen, QUndoCommand, QUndoStack
from PySide6.QtCore import QRegularExpression
from PySide6.QtWidgets import (
    QAbstractItemDelegate, QAbstractItemView, QApplication, QComboBox, QHeaderView,
    QHBoxLayout, QLabel, QLineEdit, QMenu, QMessageBox, QPushButton, QStyle, QStyleOptionViewItem,
    QStackedWidget, QStyledItemDelegate, QVBoxLayout, QWidget,
)

from physalix.ui.fill_table import FillTableView
from physalix.ui.units import unit_combo
from physalix.ui.theme import LIGHT
from physalix.ui.components import ask_yes_no, help_toggle, page_layout, panel, role
from physalix.ui.icons import icon
from physalix.ui.math_help import math_help_button
from physalix.ui.scientific_symbols import replace_name, scientific_symbol_button
from physalix.calculations import Formula
from physalix.spreadsheet import (CellFormula, CellError, REFERENCES, cell_position,
                                 calculation_expression_from_cell, column_label,
                                 display_formula, remove_formula_column, translate_formula)


def spreadsheet_formula_error_message(error):
    """Ajouter une aide courte aux erreurs de saisie, sans modifier le moteur."""
    message = str(error)
    if message.startswith("La grandeur «") and "n'existe pas dans le tableau" in message:
        return message + " Vérifiez son nom ou utilisez une grandeur existante."
    if "Fonction inconnue" in message:
        return message + " Utilisez une fonction proposée dans l’aide mathématique."
    if "plusieurs grandeurs" in message:
        return message + " Renommez-la ou utilisez une référence A1 explicite."
    if message.startswith("Formule incorrecte"):
        return message + " Vérifiez les parenthèses, les opérateurs et les noms utilisés."
    return message


class CellEdit(QUndoCommand):
    def __init__(self, model, values, title):
        super().__init__(title)
        self.model = model
        self.after = values
        self.before = {key: model.data(model.index(*key), Qt.ItemDataRole.EditRole) for key in values}

    def apply(self, values):
        self.model._editing = True
        try:
            for (row, column), text in values.items():
                self.model.setData(self.model.index(row, column), text)
        finally:
            self.model._editing = False
        self.model.recalculate_cells()

    def undo(self):
        self.apply(self.before)

    def redo(self):
        self.apply(self.after)


class AdoptCalculatedColumn(QUndoCommand):
    """Adopter une colonne existante en conservant son contenu pour l'annulation."""

    def __init__(self, model, column, expression):
        super().__init__("Appliquer une formule à toute une grandeur")
        self.model, self.column, self.expression = model, column, expression
        self.values = [row[column] for row in model.rows]
        self.formulas = {key: text for key, text in model.formulas.items() if key[1] == column}
        self.errors = {key: text for key, text in model.formula_errors.items() if key[1] == column}

    def redo(self):
        self.model.calculation_engine.adopt_existing_formula(self.column, self.expression)

    def undo(self):
        self.model.calculation_engine.release_existing_formula(self.column)
        for row, value in zip(self.model.rows, self.values):
            row[self.column] = value
        self.model.formulas.update(self.formulas)
        self.model.formula_errors.update(self.errors)
        self.model.dataChanged.emit(
            self.model.index(self.model.first_data_row, self.column),
            self.model.index(self.model.rowCount() - 1, self.column),
            [Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.EditRole],
        )
        self.model.recalculate_cells()


class MoveColumn(QUndoCommand):
    def __init__(self, table, old, new):
        super().__init__("Déplacer une colonne")
        self.table, self.old, self.new = table, old, new
        self.first = True

    def move(self, source, target):
        header = self.table.horizontalHeader()
        header.blockSignals(True)
        header.moveSection(source, target)
        header.blockSignals(False)

    def undo(self):
        self.move(self.new, self.old)

    def redo(self):
        if self.first:
            self.first = False
        else:
            self.move(self.old, self.new)


class MeasurementsModel(QAbstractTableModel):
    """Conserver les noms et les valeurs, y compris les mesures incomplètes."""

    name_row = 0
    unit_row = 1
    first_data_row = 2

    def __init__(self, parent=None):
        super().__init__(parent)
        self.names = ["x", "y"]
        self.units = ["", ""]
        self.rows = [["", ""] for _ in range(20)]
        self.calculated_columns = set()
        self.column_dependencies = {}
        self.formulas = {}
        self.formula_errors = {}
        self.undo_stack = QUndoStack(self)
        self.undo_stack.setUndoLimit(100)
        self._editing = False
        self._recalculating = False
        self.calculation_engine = None
        self.dataChanged.connect(self.recalculate_cells)
        self.columnsInserted.connect(self.recalculate_cells)
        self.rowsInserted.connect(self.recalculate_cells)

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.rows) + self.first_data_row

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.names)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        if role in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.EditRole):
            if index.row() == self.name_row:
                return self.names[index.column()]
            if index.row() == self.unit_row:
                return self.units[index.column()]
            key = (index.row() - self.first_data_row, index.column())
            if role == Qt.ItemDataRole.EditRole and key in self.formulas:
                return display_formula(self.formulas[key], self.names, key[0])
            return self.rows[index.row() - self.first_data_row][index.column()]
        key = (index.row() - self.first_data_row, index.column())
        if role == Qt.ItemDataRole.ToolTipRole and key in self.formulas:
            return display_formula(self.formulas[key], self.names, key[0]) + (
                "\n" + self.formula_errors[key] if key in self.formula_errors else "")
        if role == Qt.ItemDataRole.ForegroundRole and key in self.formulas:
            return QBrush(QColor(LIGHT.error if key in self.formula_errors else LIGHT.primary))
        if role == Qt.ItemDataRole.BackgroundRole:
            if index.row() < self.first_data_row:
                return QBrush(QColor(LIGHT.table_metadata))
            if index.column() in self.calculated_columns:
                return QBrush(QColor(LIGHT.primary_soft))
        if role == Qt.ItemDataRole.TextAlignmentRole:
            return int(Qt.AlignmentFlag.AlignVCenter | (
                Qt.AlignmentFlag.AlignLeft if index.row() < self.first_data_row
                else Qt.AlignmentFlag.AlignRight))
        return None

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if role == Qt.ItemDataRole.DisplayRole:
            if orientation == Qt.Orientation.Horizontal:
                return f"{column_label(section)} · Grandeur {section + 1}"
            if section == self.name_row:
                return "Grandeur"
            if section == self.unit_row:
                return "Unité"
            return str(section - self.first_data_row + 1)
        return None

    def flags(self, index):
        if index.column() in self.calculated_columns and index.row() >= self.first_data_row:
            return super().flags(index) & ~Qt.ItemFlag.ItemIsEditable
        return super().flags(index) | Qt.ItemFlag.ItemIsEditable

    def setData(self, index, value, role=Qt.ItemDataRole.EditRole):
        if not index.isValid() or role != Qt.ItemDataRole.EditRole:
            return False
        if index.column() in self.calculated_columns and index.row() >= self.first_data_row:
            return False
        text = str(value).strip()
        if index.row() == self.name_row:
            self.names[index.column()] = text
        elif index.row() == self.unit_row:
            self.units[index.column()] = text
        else:
            key = (index.row() - self.first_data_row, index.column())
            if text.startswith("="):
                try:
                    self.formulas[key] = CellFormula(text, self.names, key[0]).canonical_text
                except (ValueError, ArithmeticError):
                    self.formulas[key] = text
            else:
                self.formulas.pop(key, None)
                self.formula_errors.pop(key, None)
            self.rows[key[0]][key[1]] = text
        self.dataChanged.emit(index, index, [Qt.ItemDataRole.DisplayRole, role])
        if text and index.row() == self.rowCount() - 1:
            self.add_row()
        return True

    def edit_cells(self, values, title="Modifier les cellules"):
        values = {key: str(value).strip() for key, value in values.items()
                  if self.flags(self.index(*key)) & Qt.ItemFlag.ItemIsEditable
                  and self.data(self.index(*key), Qt.ItemDataRole.EditRole) != str(value).strip()}
        if values:
            self.undo_stack.push(CellEdit(self, values, title))

    def recalculate_cells(self, *args):
        if self._recalculating or self._editing or not self.formulas:
            return
        self._recalculating = True
        cache, visiting, errors = {}, set(), {}
        engine = self.calculation_engine
        calculated = {item.column: item for item in engine.items} if engine else {}
        def resolve(row, column):
            key = row, column
            if key in cache:
                if isinstance(cache[key], CellError):
                    raise cache[key]
                return cache[key]
            if key in visiting:
                raise CellError("#CYCLE!", "Dépendance circulaire entre cellules ou colonnes calculées.")
            if len(visiting) > 150:
                raise CellError("#LIMITE!", "Chaîne de dépendances trop longue.")
            if not 0 <= column < self.columnCount() or row < 0:
                raise CellError("#REF!", "La colonne ou la ligne référencée n'existe pas.")
            if row >= len(self.rows):
                return 0.0
            visiting.add(key)
            try:
                if key in self.formulas:
                    result = CellFormula(self.formulas[key], self.names, row).evaluate(resolve)
                elif column in calculated:
                    item = calculated[column]
                    if item.formula:
                        values = [""] * self.columnCount()
                        for ref in set(item.formula.references.values()):
                            values[ref] = str(resolve(row, ref))
                        result = item.formula.evaluate(values)
                    elif 0 < row < len(self.rows) - 1:
                        t0, t1, t2 = [resolve(r, item.axis) for r in (row - 1, row, row + 1)]
                        if not (t0 < t1 < t2 or t0 > t1 > t2):
                            raise ValueError("Intervalle de dérivation invalide.")
                        result = (resolve(row + 1, item.source) - resolve(row - 1, item.source)) / (t2 - t0)
                    else:
                        raise ValueError("Dérivée indisponible à cette extrémité.")
                else:
                    result = float(self.rows[row][column].replace(",", ".") or "0")
                if not math.isfinite(result):
                    raise ValueError("Résultat non fini.")
                cache[key] = result
                return result
            except CellError as error:
                cache[key] = error
                raise
            except ZeroDivisionError:
                error = CellError("#DIV/0!", "Division par zéro.")
                cache[key] = error
                raise error from None
            except (ValueError, TypeError, ArithmeticError, RecursionError) as cause:
                error = CellError("#ERREUR!", str(cause))
                cache[key] = error
                raise error from None
            finally:
                visiting.remove(key)
        resolve.is_blank = lambda r, c: (0 <= c < self.columnCount() and (r, c) not in self.formulas
                                         and c not in calculated and (r >= len(self.rows) or not self.rows[r][c]))
        changed = []
        try:
            for key in self.formulas:
                try:
                    value = format(resolve(*key), ".12g")
                except CellError as error:
                    value, errors[key] = error.code, str(error)
                row, column = key
                if self.rows[row][column] != value or self.formula_errors.get(key) != errors.get(key):
                    self.rows[row][column] = value
                    changed.append(key)
            self.formula_errors = errors
            if changed:
                self.dataChanged.emit(self.index(min(r for r, c in changed) + 2, min(c for r, c in changed)),
                                      self.index(max(r for r, c in changed) + 2, max(c for r, c in changed)), [])
        finally:
            self._recalculating = False

    def add_row(self):
        position = self.rowCount()
        self.beginInsertRows(QModelIndex(), position, position)
        self.rows.append([""] * len(self.names))
        self.endInsertRows()

    def add_quantity(self):
        position = self.columnCount()
        self.beginInsertColumns(QModelIndex(), position, position)
        self.names.append(f"Grandeur {position + 1}")
        self.units.append("")
        for row in self.rows:
            row.append("")
        self.endInsertColumns()

    def append_measurements(self, names, units, rows):
        """Ajouter des colonnes de valeurs validées et retourner leurs indices."""
        names, units, rows = list(names), list(units), [list(row) for row in rows]
        if not names or len(names) != len(units) or any(len(row) != len(names) for row in rows):
            raise ValueError("Structure de mesures incorrecte.")
        if any(not isinstance(value, str) for value in names + units + [value for row in rows for value in row]):
            raise ValueError("Les noms, unités et valeurs doivent être du texte.")
        first = self.columnCount()
        for _ in names:
            self.add_quantity()
        used = set(self.names[:first])
        unique_names = []
        for original in names:
            base = original.strip() or f"Grandeur {first + len(unique_names) + 1}"
            candidate, suffix = base, 2
            while candidate in used:
                candidate, suffix = f"{base}_{suffix}", suffix + 1
            used.add(candidate)
            unique_names.append(candidate)
        while len(self.rows) <= len(rows):
            self.add_row()
        for offset, (name, unit) in enumerate(zip(unique_names, units)):
            column = first + offset
            self.names[column] = name
            self.units[column] = unit.strip()
            for row, values in enumerate(rows):
                self.rows[row][column] = values[offset].strip()
        self.headerDataChanged.emit(Qt.Orientation.Horizontal, first, first + len(names) - 1)
        if rows:
            self.dataChanged.emit(self.index(self.first_data_row, first),
                                  self.index(self.first_data_row + len(rows) - 1,
                                             first + len(names) - 1),
                                  [Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.EditRole])
        # Les commandes de cellules mémorisent des coordonnées de colonnes antérieures.
        self.undo_stack.clear()
        return tuple(range(first, first + len(names)))

    def quantities_to_remove(self, column):
        if not 0 <= column < self.columnCount():
            return []
        removed = {column}
        while True:
            dependents = {c for c, refs in self.column_dependencies.items() if refs & removed}
            if dependents <= removed:
                return sorted(removed)
            removed.update(dependents)

    def remove_quantity(self, column):
        columns = self.quantities_to_remove(column)
        if columns:
            self.undo_stack.clear()
        for column in reversed(columns):
            self.beginRemoveColumns(QModelIndex(), column, column)
            del self.names[column]
            del self.units[column]
            for row in self.rows:
                del row[column]
            self.calculated_columns = {c - (c > column) for c in self.calculated_columns if c != column}
            self.column_dependencies = {
                c - (c > column): {ref - (ref > column) for ref in refs}
                for c, refs in self.column_dependencies.items() if c != column
            }
            self.formulas = {(r, c - (c > column)): remove_formula_column(text, column)
                             for (r, c), text in self.formulas.items() if c != column}
            self.formula_errors = {}
            self.endRemoveColumns()
        if columns and self.columnCount():
            self.headerDataChanged.emit(Qt.Orientation.Horizontal, 0, self.columnCount() - 1)
        self.recalculate_cells()
        return bool(columns)


class MeasurementDelegate(QStyledItemDelegate):
    """Accepter les nombres français et valider la saisie avec Entrée."""

    advance = Signal()
    formula_requested = Signal(QModelIndex, str, int)

    def createEditor(self, parent, option, index):
        if index.row() == index.model().unit_row:
            return unit_combo(parent)
        editor = QLineEdit(parent)
        editor.setTextMargins(2, 0, 2, 0)
        editor.setAlignment((Qt.AlignmentFlag.AlignLeft if index.row() < index.model().first_data_row
                             else Qt.AlignmentFlag.AlignRight) |
                            Qt.AlignmentFlag.AlignVCenter)
        if index.row() >= index.model().first_data_row:
            editor._physalix_index = QPersistentModelIndex(index)
            expression = QRegularExpression(
                r"(?:=[^\n]*|(?:[+-]?(?:\d+(?:[.,]\d*)?|[.,]\d+)(?:[eE][+-]?\d+)?)?)"
            )
            editor.setValidator(QRegularExpressionValidator(expression, editor))
        return editor

    def setEditorData(self, editor, index):
        if isinstance(editor, QComboBox):
            editor.setEditText(index.data(Qt.ItemDataRole.EditRole))
        else:
            super().setEditorData(editor, index)

    def setModelData(self, editor, model, index):
        value = editor.currentText() if isinstance(editor, QComboBox) else editor.text()
        model.edit_cells({(index.row(), index.column()): value}, "Modifier une cellule")

    def paint(self, painter, option, index):
        option = QStyleOptionViewItem(option)
        self.initStyleOption(option, index)
        if index.row() < index.model().first_data_row:
            option.backgroundBrush = QBrush(QColor(LIGHT.secondary))
            option.font.setBold(index.row() == index.model().name_row)
        if index.row() == index.model().unit_row:
            option.text = (index.data() or "Choisir ou saisir…") + "   ▾"
        option.widget.style().drawControl(
            QStyle.ControlElement.CE_ItemViewItem, option, painter, option.widget)
        if option.state & QStyle.StateFlag.State_HasFocus:
            painter.save()
            painter.setPen(QPen(QColor(LIGHT.primary), 2))
            painter.drawRect(option.rect.adjusted(1, 1, -1, -1))
            painter.restore()

    def eventFilter(self, editor, event):
        if (isinstance(editor, QLineEdit) and event.type() == QEvent.Type.KeyPress
                and event.text() == "=" and hasattr(editor, "_physalix_index")):
            start = editor.selectionStart()
            cursor = editor.cursorPosition()
            before = editor.text()
            if start >= 0:
                after = before[:start] + "=" + before[start + len(editor.selectedText()):]
                cursor = start + 1
            else:
                after = before[:cursor] + "=" + before[cursor:]
                cursor += 1
            if after.startswith("="):
                index = QModelIndex(editor._physalix_index)
                self.closeEditor.emit(editor, QAbstractItemDelegate.EndEditHint.RevertModelCache)
                self.formula_requested.emit(index, after, cursor)
                return True
        if event.type() == QEvent.Type.KeyPress and event.key() in (
            Qt.Key.Key_Return, Qt.Key.Key_Enter,
        ):
            if isinstance(editor, QComboBox) or editor.hasAcceptableInput():
                self.commitData.emit(editor)
                self.closeEditor.emit(editor, QAbstractItemDelegate.EndEditHint.NoHint)
                self.advance.emit()
            return True
        return super().eventFilter(editor, event)


class FormulaEditSession:
    """Composer une formule dans la barre tout en conservant sa cellule cible."""

    def __init__(self, tab):
        self.tab = tab
        self.target = QPersistentModelIndex()
        self.active = False
        self.cursor = 0
        self.selection = None

    def begin(self, index, text=None, cursor=None):
        model = self.tab.model
        if (not index.isValid() or index.row() < model.first_data_row
                or not model.flags(index) & Qt.ItemFlag.ItemIsEditable):
            return False
        self.target = QPersistentModelIndex(index)
        self.active = True
        self.clear_error()
        bar = self.tab.formula_bar
        value = index.data(Qt.ItemDataRole.EditRole) if text is None else text
        bar.setText(value if str(value).startswith("=") else "=")
        bar.setCursorPosition(len(bar.text()) if cursor is None else cursor)
        self.remember_position()
        self.tab.table.setCurrentIndex(index)
        if hasattr(self.tab, "apply_quantity_button"):
            self.tab.apply_quantity_button.hide()
        bar.setFocus()
        self.tab.table.viewport().update()
        return True

    def insert_reference(self, index):
        if not self.active or not self.target.isValid():
            return False
        if not index.isValid() or index.row() < self.tab.model.first_data_row:
            return True
        bar = self.tab.formula_bar
        if self.selection:
            bar.setSelection(*self.selection)
        else:
            bar.setCursorPosition(min(self.cursor, len(bar.text())))
        reference = f"{column_label(index.column())}{index.row() - self.tab.model.first_data_row + 1}"
        bar.insert(reference)
        bar.setFocus()
        self.remember_position()
        self.clear_error()
        self.tab.table.viewport().update()
        return True

    def remember_position(self):
        if not self.active:
            return
        bar = self.tab.formula_bar
        self.cursor = bar.cursorPosition()
        start = bar.selectionStart()
        self.selection = ((start, len(bar.selectedText())) if start >= 0 else None)

    def referenced_indexes(self):
        indexes = []
        model = self.tab.model
        if not self.active:
            return indexes
        for match in REFERENCES.finditer(self.tab.formula_bar.text()):
            for reference in (match[1], match[2]):
                if not reference:
                    continue
                row, column = cell_position(reference)
                row += model.first_data_row
                if 0 <= row < model.rowCount() and 0 <= column < model.columnCount():
                    indexes.append(model.index(row, column))
        return indexes

    def validate(self):
        if not self.active or not self.target.isValid():
            self.cancel()
            return False
        text = self.tab.formula_bar.text().strip()
        try:
            target = QModelIndex(self.target)
            CellFormula(text, self.tab.model.names,
                        target.row() - self.tab.model.first_data_row)
        except (ValueError, ArithmeticError) as error:
            message = spreadsheet_formula_error_message(error)
            self.show_error(message)
            self.remember_position()
            QMessageBox.warning(
                self.tab, "Impossible de calculer la formule", message)
            if self.active and self.target.isValid():
                bar = self.tab.formula_bar
                bar.setFocus()
                if self.selection:
                    bar.setSelection(*self.selection)
                else:
                    bar.setCursorPosition(min(self.cursor, len(bar.text())))
            return False
        self.tab.model.edit_cells({(target.row(), target.column()): text}, "Modifier une cellule")
        self.finish(target)
        return True

    def cancel(self):
        target = QModelIndex(self.target) if self.target.isValid() else QModelIndex()
        self.finish(target)

    def finish(self, target):
        self.active = False
        self.target = QPersistentModelIndex()
        self.clear_error()
        if target.isValid():
            self.tab.table.setCurrentIndex(target)
        self.tab.update_formula_bar()
        self.tab.table.setFocus()
        self.tab.table.viewport().update()

    def target_changed(self, *args):
        if self.active and not self.target.isValid():
            self.cancel()

    def show_error(self, message):
        bar = self.tab.formula_bar
        bar.setToolTip(message)
        bar.setStyleSheet(f"QLineEdit {{ border: 2px solid {LIGHT.error}; }}")

    def clear_error(self):
        self.tab.formula_bar.setToolTip("")
        self.tab.formula_bar.setStyleSheet("")


class MeasurementsTable(FillTableView):
    """Déplacer la sélection vers le bas après validation."""

    add_quantity_requested = Signal()
    edit_calculation_requested = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.formula_session = None
        header = self.horizontalHeader()
        header.setSectionsMovable(True)
        header.setFirstSectionMovable(True)
        header.setToolTip("Glissez un en-tête pour déplacer la colonne. Sa lettre et ses références restent attachées à la grandeur.")
        header.sectionMoved.connect(lambda logical, old, new: self.model().undo_stack.push(MoveColumn(self, old, new)))
        header.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        header.customContextMenuRequested.connect(self.header_context_menu)

    def header_context_menu(self, position):
        header = self.horizontalHeader()
        column = header.logicalIndexAt(position)
        menu = QMenu(self)
        if column >= 0:
            self.add_edit_calculation_action(menu, column)
            menu.addAction("Supprimer la grandeur…", lambda: self.delete_quantity(column))
            menu.addSeparator()
        menu.addAction("Nouvelle grandeur", self.add_quantity_requested.emit)
        menu.exec(header.viewport().mapToGlobal(position))

    def delete_quantity(self, column):
        model = self.model()
        columns = model.quantities_to_remove(column)
        if not columns:
            return
        message = f"Supprimer « {model.names[column] or f'Grandeur {column + 1}'} » et ses valeurs ?"
        if len(columns) > 1:
            message += "\n\nLes grandeurs calculées qui en dépendent seront aussi supprimées :\n" + "\n".join(
                f"• {model.names[c]}" for c in columns if c != column)
        if QMessageBox.question(self, "Supprimer une grandeur", message,
                                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes:
            model.remove_quantity(column)

    def copy_selection(self):
        indexes = self.selectedIndexes()
        if not indexes:
            return
        selected = {(index.row(), index.column()) for index in indexes}
        top, bottom = min(r for r, c in selected), max(r for r, c in selected)
        header = self.horizontalHeader()
        left, right = min(header.visualIndex(c) for r, c in selected), max(header.visualIndex(c) for r, c in selected)
        columns = [header.logicalIndex(v) for v in range(left, right + 1)]
        output = io.StringIO(newline="")
        writer = csv.writer(output, delimiter="\t", lineterminator="\n")
        payload = []
        for row in range(top, bottom + 1):
            writer.writerow([
                self.model().index(row, column).data() if (row, column) in selected else ""
                for column in columns
            ])
            payload.append([[row, column, self.model().index(row, column).data(Qt.ItemDataRole.EditRole)
                             if (row, column) in selected else ""] for column in columns])
        mime = QMimeData()
        mime.setText(output.getvalue())
        mime.setData("application/x-physalix-cells", json.dumps(payload).encode("utf-8"))
        QApplication.clipboard().setMimeData(mime)

    def paste_clipboard(self):
        text = QApplication.clipboard().text()
        if not text:
            return
        model = self.model()
        ranges = list(self.selectionModel().selection())
        header = self.horizontalHeader()
        start = (model.index(min(area.top() for area in ranges),
                             min((index.column() for index in self.selectedIndexes()), key=header.visualIndex))
                 if ranges else self.currentIndex())
        if not start.isValid():
            return
        try:
            # La virgule reste un séparateur décimal, jamais un séparateur de colonnes.
            delimiter = "\t" if "\t" in text or text.lstrip().startswith("=") else ";"
            rows = list(csv.reader(io.StringIO(text, newline=""), delimiter=delimiter, strict=True))
            if not rows:
                return
            width = max(1, max(map(len, rows)))
            rows = [[value.strip() for value in row] + [""] * (width - len(row)) for row in rows]
            first_visual = header.visualIndex(start.column())
            columns = [header.logicalIndex(v) if v < header.count() else model.columnCount() + v - header.count()
                       for v in range(first_visual, first_visual + width)]
            mime = QApplication.clipboard().mimeData()
            if mime.hasFormat("application/x-physalix-cells"):
                try:
                    payload = json.loads(bytes(mime.data("application/x-physalix-cells")))
                    if len(payload) == len(rows) and all(len(row) == width for row in payload):
                        for r, entries in enumerate(payload):
                            for c, (source_row, source_column, value) in enumerate(entries):
                                if isinstance(value, str) and value.startswith("="):
                                    rows[r][c] = translate_formula(value, start.row() + r - source_row, columns[c] - source_column)
                except (ValueError, TypeError, IndexError):
                    pass
            for offset, row in enumerate(rows):
                target_row = start.row() + offset
                for column_offset, value in enumerate(row):
                    column = columns[column_offset]
                    if target_row >= model.first_data_row:
                        if column in model.calculated_columns:
                            raise ValueError("La zone de collage contient une colonne calculée, non modifiable.")
                        if not value.startswith("=") and not re.fullmatch(r"(?:[+-]?(?:\d+(?:[.,]\d*)?|[.,]\d+)(?:[eE][+-]?\d+)?)?", value):
                            raise ValueError(
                                f"Valeur non numérique à la mesure {target_row - model.first_data_row + 1}, "
                                f"grandeur {column + 1} : {value[:60]!r}.\n"
                                "Pour coller des noms et unités, sélectionnez la ligne Grandeur ou Unité.")
        except (csv.Error, ValueError) as error:
            QMessageBox.warning(self, "Collage impossible", str(error))
            return
        while model.columnCount() <= max(columns):
            model.add_quantity()
        while model.rowCount() < start.row() + len(rows):
            model.add_row()
        model.edit_cells({(start.row() + r, columns[c]): value for r, row in enumerate(rows)
                          for c, value in enumerate(row)}, "Coller des cellules")
        selection = QItemSelection()
        for column in columns:
            selection.select(model.index(start.row(), column), model.index(start.row() + len(rows) - 1, column))
        self.selectionModel().setCurrentIndex(start, QItemSelectionModel.SelectionFlag.NoUpdate)
        self.selectionModel().select(selection, QItemSelectionModel.SelectionFlag.ClearAndSelect)

    def contextMenuEvent(self, event):
        index = self.indexAt(event.pos())
        if index.isValid() and not self.selectionModel().isSelected(index):
            self.setCurrentIndex(index)
        menu = QMenu(self)
        undo = menu.addAction("Annuler\tCtrl+Z", self.model().undo_stack.undo)
        undo.setEnabled(self.model().undo_stack.canUndo())
        redo = menu.addAction("Rétablir\tCtrl+Y", self.model().undo_stack.redo)
        redo.setEnabled(self.model().undo_stack.canRedo())
        menu.addSeparator()
        copy = menu.addAction("Copier\tCtrl+C", self.copy_selection)
        copy.setEnabled(bool(self.selectedIndexes()))
        paste = menu.addAction("Coller\tCtrl+V", self.paste_clipboard)
        paste.setEnabled(self.currentIndex().isValid() and bool(QApplication.clipboard().text()))
        self.add_edit_calculation_action(menu, index.column() if index.isValid() else -1)
        self.add_apply_formula_action(menu, index)
        if index.isValid() and index.row() == self.model().name_row:
            menu.addSeparator()
            menu.addAction("Supprimer la grandeur…", lambda: self.delete_quantity(index.column()))
        menu.addSeparator()
        menu.addAction("Nouvelle grandeur", self.add_quantity_requested.emit)
        menu.exec(event.globalPos())

    def add_edit_calculation_action(self, menu, column):
        if column not in self.model().calculated_columns:
            return None
        menu.addSeparator()
        return menu.addAction(
            "Modifier le calcul…",
            lambda: self.edit_calculation_requested.emit(column),
        )

    def add_apply_formula_action(self, menu, index):
        if not self.can_apply_formula(index):
            return None
        menu.addSeparator()
        return menu.addAction(
            "Appliquer à toute la grandeur…",
            lambda: self.apply_formula_to_quantity(index),
        )

    def can_apply_formula(self, index):
        key = (index.row() - self.model().first_data_row, index.column()) if index.isValid() else None
        return bool(
            key in self.model().formulas
            and self.model().calculation_engine is not None
            and index.column() not in self.model().calculated_columns
        )

    def apply_formula_to_quantity(self, index):
        model = self.model()
        key = (index.row() - model.first_data_row, index.column())
        if key not in model.formulas or model.calculation_engine is None:
            return
        try:
            definitions = {
                Formula(
                    calculation_expression_from_cell(text, model.names, row),
                    model.names,
                ).editable_expression(model.names)
                for (row, column), text in model.formulas.items() if column == index.column()
            }
            if len(definitions) != 1:
                raise ValueError(
                    "Cette grandeur contient plusieurs formules différentes. "
                    "Harmonisez-les avant de l’appliquer à toute la grandeur.")
            expression = definitions.pop()
            model.calculation_engine.prepare_existing_formula(index.column(), expression)
        except ValueError as error:
            QMessageBox.warning(
                self, "Application impossible", str(error))
            return

        formulas = sum(column == index.column() for row, column in model.formulas)
        manual = sum(
            bool(row[index.column()]) and (number, index.column()) not in model.formulas
            for number, row in enumerate(model.rows)
        )
        replacements = []
        if formulas == 1:
            replacements.append("La formule ponctuelle existante sera remplacée par les résultats calculés.")
        elif formulas > 1:
            replacements.append(
                f"Les {formulas} formules ponctuelles existantes seront remplacées par les résultats calculés.")
        if manual == 1:
            replacements.append("La valeur saisie existante sera remplacée.")
        elif manual > 1:
            replacements.append(f"Les {manual} valeurs saisies existantes seront remplacées.")
        name = model.names[index.column()] or f"Grandeur {index.column() + 1}"
        message = (
            f"Souhaitez-vous appliquer cette formule à toutes les lignes de la grandeur « {name} » ?\n\n"
            f"Formule : {expression}\n\n"
            "Les valeurs de cette colonne seront calculées automatiquement. "
            "Vous pourrez modifier cette formule à tout moment, directement depuis le tableau "
            "ou dans l’onglet Calculs.\n\n"
            + ("\n".join(replacements) if replacements
               else "Les cellules de la colonne seront remplies automatiquement.")
        )
        if not ask_yes_no(
                self, "Créer une grandeur calculée", message,
                "Créer la grandeur calculée", "Annuler"):
            return
        model.undo_stack.push(AdoptCalculatedColumn(model, index.column(), expression))

    def mousePressEvent(self, event):
        if self.formula_session and self.formula_session.active and event.button() == Qt.MouseButton.LeftButton:
            self.formula_session.insert_reference(self.indexAt(event.position().toPoint()))
            event.accept()
            return
        super().mousePressEvent(event)
        index = self.indexAt(event.position().toPoint())
        if (event.button() == Qt.MouseButton.LeftButton and index.isValid()
                and index.row() == self.model().unit_row
                and self.state() != QAbstractItemView.State.EditingState):
            self.edit(index)

    def mouseDoubleClickEvent(self, event):
        index = self.indexAt(event.position().toPoint())
        if (index.isValid() and index.row() >= self.model().first_data_row
                and index.column() in self.model().calculated_columns):
            self.edit_calculation_requested.emit(index.column())
            event.accept()
            return
        value = index.data(Qt.ItemDataRole.EditRole) if index.isValid() else ""
        if (self.formula_session and isinstance(value, str) and value.startswith("=")
                and self.formula_session.begin(index)):
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def paintEvent(self, event):
        super().paintEvent(event)
        session = self.formula_session
        if not session or not session.active or not session.target.isValid():
            return
        painter = QPainter(self.viewport())
        for index in session.referenced_indexes():
            painter.setPen(QPen(QColor(LIGHT.primary_pressed), 2, Qt.PenStyle.DashLine))
            painter.drawRect(self.visualRect(index).adjusted(2, 2, -2, -2))
        painter.setPen(QPen(QColor(LIGHT.warning), 2))
        painter.drawRect(self.visualRect(QModelIndex(session.target)).adjusted(1, 1, -1, -1))
        painter.end()

    def advance_down(self):
        current = self.currentIndex()
        if not current.isValid():
            return
        if current.row() + 1 == self.model().rowCount():
            self.model().add_row()
        target = self.model().index(current.row() + 1, current.column())
        self.setCurrentIndex(target)
        self.scrollTo(target)

    def keyPressEvent(self, event):
        if self._source:
            super().keyPressEvent(event)
            return
        if event.matches(QKeySequence.StandardKey.Copy):
            self.copy_selection()
            event.accept()
            return
        if event.matches(QKeySequence.StandardKey.Undo):
            self.model().undo_stack.undo()
            event.accept()
            return
        if event.matches(QKeySequence.StandardKey.Redo):
            self.model().undo_stack.redo()
            event.accept()
            return
        if event.matches(QKeySequence.StandardKey.Paste):
            self.paste_clipboard()
            event.accept()
            return
        current = self.currentIndex()
        if (event.key() == Qt.Key.Key_Equal and not event.modifiers()
                and self.formula_session and self.formula_session.begin(current, "=")):
            event.accept()
            return
        if event.key() == Qt.Key.Key_F2 and self.formula_session:
            value = current.data(Qt.ItemDataRole.EditRole) if current.isValid() else ""
            if isinstance(value, str) and value.startswith("=") and self.formula_session.begin(current):
                event.accept()
                return
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.advance_down()
            return
        if event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            self.model().edit_cells({(index.row(), index.column()): "" for index in self.selectedIndexes()},
                                    "Effacer des cellules")
            return
        super().keyPressEvent(event)


class DataTab(QWidget):
    """Saisir et nommer les colonnes de mesures expérimentales."""

    def __init__(self):
        super().__init__()
        layout = page_layout(QVBoxLayout(self))
        instructions = help_toggle("Données / Tableur",
            "Grandeur et Unité : nommez les colonnes. Entrée : descendre · Tab : aller à droite.\n"
            "Ctrl+C / Ctrl+V : copier / coller · Ctrl+Z / Ctrl+Y : annuler / rétablir les modifications de cellules.\n"
            "Glissez un en-tête pour déplacer sa colonne. Clic droit : supprimer une grandeur.\n"
            "Formules : =A1*2 ou =SOMME(A1:A5). A1 = première mesure de A ; $A$1 reste fixe.\n"
            "Tirez le carré de sélection vers le bas pour recopier une formule ou prolonger deux valeurs.\n"
            "Décimales : virgule ou point. Les données restent en mémoire pendant cette session.",
            "",
        )
        layout.addWidget(instructions)

        self.model = MeasurementsModel(self)
        self.table = MeasurementsTable(self)
        self.table.setModel(self.model)
        self.table.horizontalHeader().setObjectName("quantityHeader")
        self.table.verticalHeader().setObjectName("rowHeader")
        self.table.add_quantity_requested.connect(self.add_quantity)
        delegate = MeasurementDelegate(self.table)
        delegate.advance.connect(self.table.advance_down)
        delegate.formula_requested.connect(self.begin_formula_from_cell_editor)
        self.table.setItemDelegate(delegate)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setDefaultSectionSize(32)
        self.table.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked
            | QAbstractItemView.EditTrigger.EditKeyPressed
            | QAbstractItemView.EditTrigger.AnyKeyPressed
        )
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.table.horizontalHeader().setDefaultSectionSize(240)
        self.table.setCurrentIndex(self.model.index(0, 0))

        self.add_quantity_button = role(QPushButton("Ajouter une grandeur"), "primary")
        self.add_quantity_button.setIcon(icon("add", active=True))
        self.add_quantity_button.setToolTip("Ajouter une colonne vide et saisir son nom")
        self.add_quantity_button.setMinimumHeight(34)
        self.add_quantity_button.clicked.connect(self.add_quantity)
        toolbar, toolbar_layout = panel(kind="toolbar")
        actions = QHBoxLayout()
        actions.setSpacing(LIGHT.related)
        actions.addWidget(role(QLabel("Grandeurs"), "toolbarLabel"))
        actions.addWidget(self.add_quantity_button)
        self.undo_button = QPushButton("Annuler")
        self.redo_button = QPushButton("Rétablir")
        for button, action, signal in ((self.undo_button, self.model.undo_stack.undo, self.model.undo_stack.canUndoChanged),
                                       (self.redo_button, self.model.undo_stack.redo, self.model.undo_stack.canRedoChanged)):
            button.setEnabled(False)
            button.clicked.connect(action)
            signal.connect(button.setEnabled)
            actions.addWidget(button)
        self.undo_button.setToolTip("Ctrl+Z · Annuler la dernière modification du tableau")
        self.redo_button.setToolTip("Ctrl+Y · Rétablir la dernière modification annulée")
        actions.addStretch()
        toolbar_layout.addLayout(actions)
        self.editor_stack = QStackedWidget()

        self.name_context = QWidget()
        name_row = QHBoxLayout(self.name_context)
        name_row.setContentsMargins(0, 0, 0, 0)
        name_row.setSpacing(LIGHT.related)
        self.name_context_label = role(QLabel("Nom de la grandeur :"), "toolbarLabel")
        self.name_editor = QLineEdit()
        self.name_editor.setAccessibleName("Nom de la grandeur")
        self.name_editor.setPlaceholderText("Saisir un nom")
        self.name_editor.setMaximumWidth(LIGHT.field_medium)
        self.symbol_button = scientific_symbol_button(self.set_quantity_symbol)
        name_row.addWidget(self.name_context_label)
        name_row.addWidget(self.name_editor)
        name_row.addWidget(self.symbol_button)
        name_row.addStretch()

        self.unit_context = QWidget()
        unit_row = QHBoxLayout(self.unit_context)
        unit_row.setContentsMargins(0, 0, 0, 0)
        unit_row.setSpacing(LIGHT.related)
        self.unit_context_label = role(QLabel("Unité de la grandeur :"), "toolbarLabel")
        self.unit_editor = unit_combo()
        self.unit_editor.setAccessibleName("Unité de la grandeur")
        self.unit_editor.setMaximumWidth(LIGHT.field_medium)
        unit_row.addWidget(self.unit_context_label)
        unit_row.addWidget(self.unit_editor)
        unit_row.addStretch()

        self.data_context = QWidget()
        formula_row = QHBoxLayout(self.data_context)
        formula_row.setContentsMargins(0, 0, 0, 0)
        formula_row.setSpacing(LIGHT.related)
        self.edit_context_label = role(QLabel("Cellule"), "toolbarLabel")
        formula_row.addWidget(self.edit_context_label)
        self.cell_address = role(QLabel("—"), "cellAddress")
        self.cell_address.setMinimumWidth(70)
        self.formula_bar = QLineEdit()
        self.formula_bar.setAccessibleName("Valeur ou formule de la cellule")
        self.formula_bar.setPlaceholderText("Valeur ou formule, par exemple =A1*2")
        self.formula_bar.setMaximumWidth(LIGHT.formula_wide)
        self.formula_session = FormulaEditSession(self)
        self.table.formula_session = self.formula_session
        formula_row.addWidget(self.cell_address)
        self.formula_mark = role(QLabel("fx"), "formulaMark")
        formula_row.addWidget(self.formula_mark)
        formula_row.addWidget(self.formula_bar, 1)
        self.apply_quantity_button = QPushButton("Appliquer à toute la grandeur…")
        self.apply_quantity_button.setMaximumWidth(LIGHT.action_wide)
        self.apply_quantity_button.setMinimumWidth(0)
        self.apply_quantity_button.setToolTip(
            "Transformer la formule de cette cellule en calcul automatique pour toute la grandeur")
        self.apply_quantity_button.clicked.connect(
            lambda: self.table.apply_formula_to_quantity(self.table.currentIndex()))
        self.apply_quantity_button.hide()
        formula_row.addWidget(self.apply_quantity_button)
        self.math_help_button = math_help_button(self, spreadsheet=True)
        formula_row.addWidget(self.math_help_button)
        for context in (self.name_context, self.unit_context, self.data_context):
            self.editor_stack.addWidget(context)
        toolbar_layout.addWidget(self.editor_stack)
        layout.addWidget(toolbar)
        self.table.selectionModel().currentChanged.connect(self.update_formula_bar)
        self.model.dataChanged.connect(self.update_formula_bar)
        self.model.columnsRemoved.connect(self.update_formula_bar)
        self.model.columnsRemoved.connect(self.formula_session.target_changed)
        self.name_editor.returnPressed.connect(self.apply_name_editor)
        self.formula_bar.returnPressed.connect(self.apply_formula_bar)
        self.formula_bar.textEdited.connect(self.formula_text_edited)
        self.formula_bar.installEventFilter(self)
        self._unit_editor_column = None
        self._unit_editor_dirty = False
        self.unit_editor.lineEdit().textEdited.connect(self.unit_editor_changed)
        self.unit_editor.lineEdit().editingFinished.connect(self.apply_unit_editor)
        self.unit_editor.activated.connect(self.apply_unit_editor)
        self.update_formula_bar()
        layout.addWidget(self.table)

    def update_formula_bar(self, *args):
        if self.formula_session.active:
            return
        index = self.table.currentIndex()
        valid = index.isValid() and index.column() < self.model.columnCount()
        naming = valid and index.row() == self.model.name_row
        unit = valid and index.row() == self.model.unit_row
        self.editor_stack.setCurrentWidget(
            self.name_context if naming else self.unit_context if unit else self.data_context)
        self.symbol_button.setEnabled(naming)
        self.name_editor.setEnabled(naming)
        if naming and not self.name_editor.hasFocus():
            self.name_editor.setText(index.data(Qt.ItemDataRole.EditRole) or "")
        if unit:
            column_changed = self._unit_editor_column != index.column()
            self._unit_editor_column = index.column()
            if column_changed or not self._unit_editor_dirty:
                self._unit_editor_dirty = False
                self.unit_editor.setEditText(index.data(Qt.ItemDataRole.EditRole) or "")
        self.formula_bar.setEnabled(
            valid and not naming and not unit
            and bool(self.model.flags(index) & Qt.ItemFlag.ItemIsEditable))
        can_apply = self.table.can_apply_formula(index)
        self.apply_quantity_button.setEnabled(can_apply)
        self.apply_quantity_button.setVisible(can_apply)
        self.cell_address.setText((column_label(index.column()) +
                                  (str(index.row() - 1) if index.row() >= 2 else " · " + ("Nom" if index.row() == 0 else "Unité")))
                                 if valid else "—")
        if not naming and not unit and not self.formula_bar.hasFocus():
            self.formula_bar.setText(index.data(Qt.ItemDataRole.EditRole) or "" if valid else "")

    def apply_name_editor(self):
        index = self.table.currentIndex()
        if index.isValid() and index.row() == self.model.name_row:
            self.model.edit_cells(
                {(self.model.name_row, index.column()): self.name_editor.text()},
                "Renommer une grandeur")
            self.table.setFocus()

    def unit_editor_changed(self, *args):
        self._unit_editor_dirty = True

    def apply_unit_editor(self, *args):
        column = self._unit_editor_column
        if column is None or not 0 <= column < self.model.columnCount():
            return
        self._unit_editor_dirty = False
        self.model.edit_cells(
            {(self.model.unit_row, column): self.unit_editor.currentText()},
            "Modifier une unité")

    def apply_formula_bar(self):
        if self.formula_session.active:
            self.formula_session.validate()
            return
        index = self.table.currentIndex()
        if index.isValid():
            self.model.edit_cells({(index.row(), index.column()): self.formula_bar.text()}, "Modifier une cellule")
            self.table.setFocus()
            self.update_formula_bar()

    def formula_text_edited(self, text):
        if self.formula_session.active:
            self.formula_session.remember_position()
            self.formula_session.clear_error()
            self.table.viewport().update()
            return
        index = self.table.currentIndex()
        if text.startswith("="):
            self.formula_session.begin(index, text, self.formula_bar.cursorPosition())

    def begin_formula_from_cell_editor(self, index, text, cursor):
        self.formula_session.begin(index, text, cursor)

    def eventFilter(self, watched, event):
        if (watched is self.formula_bar and self.formula_session.active
                and event.type() == QEvent.Type.FocusOut):
            self.formula_session.remember_position()
        if (watched is self.formula_bar and self.formula_session.active
                and event.type() == QEvent.Type.KeyPress and event.key() == Qt.Key.Key_Escape):
            self.formula_session.cancel()
            event.accept()
            return True
        return super().eventFilter(watched, event)

    def set_quantity_symbol(self, symbol):
        index = self.table.currentIndex()
        if not index.isValid() or index.row() != self.model.name_row:
            return
        self.model.edit_cells(
            {(self.model.name_row, index.column()): symbol}, "Renommer une grandeur")
        replace_name(self.name_editor, symbol)

    def add_quantity(self):
        self.model.add_quantity()
        index = self.model.index(0, self.model.columnCount() - 1)
        self.table.setCurrentIndex(index)
        self.table.scrollTo(index)
        self.table.setFocus()
        self.table.edit(index)

    def append_measurements(self, names, units, rows):
        """API publique utilisée par les outils d'acquisition de données."""
        return self.model.append_measurements(names, units, rows)
