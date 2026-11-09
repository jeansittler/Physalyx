"""Gestes du tableur, historique et formules liées aux mesures."""

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QItemSelection, QItemSelectionModel, QModelIndex, QPoint, QRect, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLineEdit

from physalix.spreadsheet import CellFormula, column_label, translate_formula
from physalix.project import read_project, write_project
from physalix.ui.main_window import MainWindow
from physalix.ui.project_state import restore, snapshot
from physalix.ui.theme import LIGHT


class SpreadsheetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.window = MainWindow()
        self.window.resize(1000, 720)
        self.window.show()
        self.tab = self.window.data_tab
        self.window.show_module(self.window.tabs.indexOf(self.tab))
        self.model, self.table = self.tab.model, self.tab.table
        self.app.processEvents()

    def tearDown(self):
        self.window._discard_on_close = True
        self.window.close()
        self.app.processEvents()

    def select(self, row, column, bottom=None, right=None):
        first = self.model.index(row, column)
        self.table.setCurrentIndex(first)
        self.table.selectionModel().select(QItemSelection(first, self.model.index(
            bottom if bottom is not None else row, right if right is not None else column)),
            QItemSelectionModel.SelectionFlag.ClearAndSelect)

    def put(self, row, column, value):
        self.model.edit_cells({(row + 2, column): value})

    def test_delete_selection_undo_redo_restores_formulas_and_graph(self):
        self.put(0, 0, "3")
        self.put(0, 1, "=A1*2")
        self.put(1, 0, "4")
        self.put(1, 1, "=A2*2")
        self.select(2, 0, 3, 1)
        QTest.keyClick(self.table, Qt.Key.Key_Delete)
        self.assertEqual(self.model.rows[:2], [["", ""], ["", ""]])
        QTest.keyClick(self.table, Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier)
        self.assertEqual(self.model.rows[:2], [["3", "6"], ["4", "8"]])
        self.assertEqual(self.model.index(2, 1).data(Qt.ItemDataRole.EditRole), "=A1*2")
        self.app.processEvents()
        self.assertEqual(list(self.window.graph_tab.series[0].points.getData()[1]), [6, 8])
        QTest.keyClick(self.table, Qt.Key.Key_Y, Qt.KeyboardModifier.ControlModifier)
        self.assertEqual(self.model.rows[:2], [["", ""], ["", ""]])

    def test_formula_bar_and_cell_editor(self):
        self.put(0, 0, "5")
        self.select(2, 1)
        self.tab.formula_bar.setText("=A1+1")
        QTest.keyClick(self.tab.formula_bar, Qt.Key.Key_Return)
        self.assertEqual(self.model.rows[0][1], "6")
        self.assertEqual(self.tab.cell_address.text(), "B1")
        self.table.edit(self.model.index(2, 1))
        editor = self.table.findChild(QLineEdit)
        self.assertEqual(editor.text(), "=A1+1")
        editor.setText("=A1*3")
        QTest.keyClick(editor, Qt.Key.Key_Return)
        self.assertEqual(self.model.rows[0][1], "15")
        self.model.undo_stack.undo()
        self.assertEqual(self.model.rows[0][1], "6")

    def test_formula_session_inserts_clicked_references_and_validates(self):
        self.model.add_quantity()
        self.model.add_quantity()
        self.put(0, 1, "3")
        self.put(0, 2, "4")
        self.select(2, 3)
        QTest.keyClick(self.table, Qt.Key.Key_Equal)
        self.assertTrue(self.tab.formula_session.active)
        QTest.keyClicks(self.tab.formula_bar, "sqrt(")
        QTest.mouseClick(self.table.viewport(), Qt.MouseButton.LeftButton,
                         pos=self.table.visualRect(self.model.index(2, 1)).center())
        QTest.keyClicks(self.tab.formula_bar, "^2+")
        QTest.mouseClick(self.table.viewport(), Qt.MouseButton.LeftButton,
                         pos=self.table.visualRect(self.model.index(2, 2)).center())
        QTest.keyClicks(self.tab.formula_bar, "^2)")
        self.assertEqual(self.tab.formula_bar.text(), "=sqrt(B1^2+C1^2)")
        self.assertEqual({(index.row(), index.column()) for index in self.tab.formula_session.referenced_indexes()},
                         {(2, 1), (2, 2)})
        QTest.keyClick(self.tab.formula_bar, Qt.Key.Key_Return)
        self.assertFalse(self.tab.formula_session.active)
        self.assertEqual(self.model.formulas[0, 3], "=sqrt(B1^2+C1^2)")
        self.assertEqual(self.model.rows[0][3], "5")

    def test_first_blank_cell_double_click_transfers_equals_to_formula_bar(self):
        self.model.add_quantity()
        self.put(1, 0, "2")
        target = self.model.index(3, 2)
        reference = self.model.index(3, 0)

        QTest.mouseClick(self.table.viewport(), Qt.MouseButton.LeftButton,
                         pos=self.table.visualRect(target).center())
        QTest.mouseDClick(self.table.viewport(), Qt.MouseButton.LeftButton,
                          pos=self.table.visualRect(target).center())
        self.app.processEvents()
        editor = self.app.focusWidget()
        self.assertIsInstance(editor, QLineEdit)
        self.assertIsNot(editor, self.tab.formula_bar)
        QTest.keyClick(editor, Qt.Key.Key_Equal)
        self.app.processEvents()

        self.assertTrue(self.tab.formula_session.active)
        self.assertTrue(self.tab.formula_bar.hasFocus())
        self.assertEqual(self.tab.formula_bar.text(), "=")
        self.assertEqual((self.tab.formula_session.target.row(), self.tab.formula_session.target.column()),
                         (3, 2))
        self.assertNotIn((1, 2), self.model.formulas)

        QTest.mouseClick(self.table.viewport(), Qt.MouseButton.LeftButton,
                         pos=self.table.visualRect(reference).center())
        self.assertEqual(self.tab.formula_bar.text(), "=A2")
        self.assertEqual(self.table.currentIndex(), target)
        QTest.keyClicks(self.tab.formula_bar, "+1")
        QTest.keyClick(self.tab.formula_bar, Qt.Key.Key_Return)
        self.assertEqual(self.model.formulas[1, 2], "=A2+1")
        self.assertEqual(self.model.rows[1][2], "3")
        self.assertNotEqual(self.model.rows[1][2], "#ERREUR!")

        second_target = self.model.index(4, 2)
        QTest.mouseClick(self.table.viewport(), Qt.MouseButton.LeftButton,
                         pos=self.table.visualRect(second_target).center())
        QTest.mouseDClick(self.table.viewport(), Qt.MouseButton.LeftButton,
                          pos=self.table.visualRect(second_target).center())
        second_editor = self.app.focusWidget()
        self.assertIsInstance(second_editor, QLineEdit)
        QTest.keyClick(second_editor, Qt.Key.Key_Equal)
        self.assertTrue(self.tab.formula_session.active)
        QTest.keyClick(self.tab.formula_bar, Qt.Key.Key_Escape)
        self.assertNotIn((2, 2), self.model.formulas)

        ordinary = self.model.index(3, 1)
        QTest.mouseClick(self.table.viewport(), Qt.MouseButton.LeftButton,
                         pos=self.table.visualRect(ordinary).center())
        QTest.mouseDClick(self.table.viewport(), Qt.MouseButton.LeftButton,
                          pos=self.table.visualRect(ordinary).center())
        ordinary_editor = self.app.focusWidget()
        self.assertIsInstance(ordinary_editor, QLineEdit)
        QTest.keyClicks(ordinary_editor, "7")
        QTest.keyClick(ordinary_editor, Qt.Key.Key_Return)
        self.assertEqual(self.model.rows[1][1], "7")

    def test_formula_session_cursor_selection_escape_and_f2(self):
        self.put(0, 0, "2")
        self.put(0, 1, "=A1+1")
        self.select(2, 1)
        QTest.keyClick(self.table, Qt.Key.Key_F2)
        self.assertTrue(self.tab.formula_session.active)
        self.tab.formula_bar.setSelection(1, 2)
        QTest.mouseClick(self.table.viewport(), Qt.MouseButton.LeftButton,
                         pos=self.table.visualRect(self.model.index(3, 0)).center())
        self.assertEqual(self.tab.formula_bar.text(), "=A2+1")
        QTest.keyClick(self.tab.formula_bar, Qt.Key.Key_Escape)
        self.assertFalse(self.tab.formula_session.active)
        self.assertEqual(self.model.formulas[0, 1], "=A1+1")
        self.assertEqual(self.model.undo_stack.count(), 2)
        QTest.mouseDClick(self.table.viewport(), Qt.MouseButton.LeftButton,
                          pos=self.table.visualRect(self.model.index(2, 1)).center())
        self.assertTrue(self.tab.formula_session.active)
        self.assertEqual(self.tab.formula_bar.text(), "=A1+1")
        QTest.keyClick(self.tab.formula_bar, Qt.Key.Key_Escape)
        self.assertTrue(self.table.hasFocus())
        QTest.keyClick(self.table, Qt.Key.Key_Down)
        self.assertEqual(self.table.currentIndex().row(), 3)

    def test_formula_session_rejects_invalid_text_and_stops_if_target_is_removed(self):
        self.select(2, 1)
        QTest.keyClick(self.table, Qt.Key.Key_Equal)
        QTest.keyClicks(self.tab.formula_bar, "unknown(A1)")
        with patch("physalix.ui.data_tab.QMessageBox.warning") as warning:
            QTest.keyClick(self.tab.formula_bar, Qt.Key.Key_Return)
            self.assertEqual(warning.call_count, 1)
        self.assertTrue(self.tab.formula_session.active)
        self.assertNotEqual(self.tab.formula_bar.toolTip(), "")
        self.assertNotIn((0, 1), self.model.formulas)
        self.model.remove_quantity(1)
        self.assertFalse(self.tab.formula_session.active)
        self.assertEqual(self.model.columnCount(), 1)

    def test_clicked_formula_project_roundtrip_and_portable_geometry(self):
        self.model.add_quantity()
        self.model.add_quantity()
        self.put(0, 1, "3")
        self.put(0, 2, "4")
        self.select(2, 3)
        QTest.keyClick(self.table, Qt.Key.Key_Equal)
        QTest.keyClicks(self.tab.formula_bar, "sqrt(")
        for column, suffix in ((1, "^2+"), (2, "^2)")):
            QTest.mouseClick(self.table.viewport(), Qt.MouseButton.LeftButton,
                             pos=self.table.visualRect(self.model.index(2, column)).center())
            QTest.keyClicks(self.tab.formula_bar, suffix)
        QTest.keyClick(self.tab.formula_bar, Qt.Key.Key_Return)

        with tempfile.TemporaryDirectory(dir=os.environ.get("TEMP")) as directory:
            path = Path(directory) / "formule-par-clic.physalix"
            write_project(path, snapshot(self.window))
            reopened = MainWindow()
            try:
                restore(reopened, read_project(path), path)
                reopened_model = reopened.data_tab.model
                self.assertEqual(reopened_model.formulas[0, 3], "=sqrt(B1^2+C1^2)")
                self.assertEqual(reopened_model.rows[0][3], "5")
                reopened_model.edit_cells({(2, 1): "6"})
                self.assertAlmostEqual(float(reopened_model.rows[0][3]), 52 ** 0.5)
            finally:
                reopened._discard_on_close = True
                reopened.close()
                self.app.processEvents()

        for width, height in ((1366, 768), (1100, 700)):
            self.window.resize(width, height)
            self.app.processEvents()
            self.assertTrue(self.tab.formula_bar.isVisible())
            self.assertTrue(self.table.isVisible())
            bar = QRect(self.tab.formula_bar.mapTo(self.tab, QPoint()), self.tab.formula_bar.size())
            help_button = QRect(self.tab.math_help_button.mapTo(self.tab, QPoint()),
                                self.tab.math_help_button.size())
            table = QRect(self.table.mapTo(self.tab, QPoint()), self.table.size())
            self.assertFalse(bar.intersects(help_button))
            self.assertFalse(bar.intersects(table))
            self.assertGreater(self.table.viewport().height(), 250)

    def test_scientific_symbol_renames_quantity_with_undo_and_updates_graph(self):
        self.select(self.model.name_row, 0)
        self.app.processEvents()
        self.assertIs(self.tab.editor_stack.currentWidget(), self.tab.name_context)
        self.assertEqual(self.tab.name_context_label.text(), "Nom de la grandeur :")
        self.assertIs(self.tab.name_context.layout().itemAt(1).widget(), self.tab.name_editor)
        self.assertIs(self.tab.name_context.layout().itemAt(2).widget(), self.tab.symbol_button)
        self.assertTrue(self.tab.symbol_button.isVisible())
        self.assertTrue(self.tab.symbol_button.isEnabled())
        self.assertEqual(self.tab.name_editor.maximumWidth(), LIGHT.field_medium)
        next(action for action in self.tab.symbol_button.menu().actions()
             if action.text() == "σ").trigger()
        self.app.processEvents()
        self.assertEqual(self.model.names[0], "σ")
        self.assertEqual(self.tab.name_editor.text(), "σ")
        self.assertIn("σ", self.window.graph_tab.series[0].x_choice.itemText(0))
        self.model.undo_stack.undo()
        self.assertEqual(self.model.names[0], "x")
        self.model.undo_stack.redo()
        self.assertEqual(self.model.names[0], "σ")

        self.select(self.model.unit_row, 0)
        self.app.processEvents()
        self.assertIs(self.tab.editor_stack.currentWidget(), self.tab.unit_context)
        self.assertEqual(self.tab.unit_context_label.text(), "Unité de la grandeur :")
        unit_index = self.tab.unit_editor.findText("mL")
        self.tab.unit_editor.setCurrentIndex(unit_index)
        self.tab.unit_editor.activated.emit(unit_index)
        self.assertEqual(self.model.units[0], "mL")
        self.tab.unit_editor.lineEdit().setText("unité personnalisée")
        self.tab.unit_editor_changed()
        self.tab.apply_unit_editor()
        self.assertEqual(self.model.units[0], "unité personnalisée")
        self.model.undo_stack.undo()
        self.assertEqual(self.model.units[0], "mL")
        self.assertEqual(self.tab.unit_editor.currentText(), "mL")
        self.model.undo_stack.redo()
        self.assertEqual(self.model.units[0], "unité personnalisée")
        self.assertEqual(self.tab.unit_editor.currentText(), "unité personnalisée")

        self.select(self.model.first_data_row, 0)
        self.app.processEvents()
        self.assertIs(self.tab.editor_stack.currentWidget(), self.tab.data_context)
        self.assertEqual(self.tab.edit_context_label.text(), "Cellule")
        self.assertTrue(self.tab.cell_address.isVisible())
        self.assertTrue(self.tab.formula_mark.isVisible())
        self.assertTrue(self.tab.math_help_button.isVisible())
        self.assertFalse(self.tab.symbol_button.isVisible())
        self.assertFalse(self.tab.symbol_button.isEnabled())
        self.assertEqual(self.tab.formula_bar.maximumWidth(), LIGHT.formula_wide)

    def test_formula_fill_is_relative_and_one_undo(self):
        for row in range(5):
            self.put(row, 0, str(row + 1))
        self.put(0, 1, "=A1+$A$1")
        self.select(2, 1)
        self.app.processEvents()
        viewport = self.table.viewport()
        QTest.mousePress(viewport, Qt.MouseButton.LeftButton, pos=self.table.fill_handle_rect().center())
        target = self.table.visualRect(self.model.index(6, 1)).center()
        QTest.mouseMove(viewport, target)
        QTest.mouseRelease(viewport, Qt.MouseButton.LeftButton, pos=target)
        self.assertEqual([row[1] for row in self.model.rows[:5]], ["2", "3", "4", "5", "6"])
        self.assertEqual(self.model.formulas[4, 1], "=A5+$A$1")
        self.model.undo_stack.undo()
        self.assertEqual([row[1] for row in self.model.rows[:5]], ["2", "", "", "", ""])
        self.model.undo_stack.redo()
        self.put(0, 0, "10")
        self.assertEqual(self.model.rows[4][1], "15")

    def test_column_move_preserves_formulas_graph_and_visual_clipboard(self):
        self.model.add_quantity()
        self.put(0, 0, "2")
        self.put(0, 1, "=A1*3")
        self.put(0, 2, "9")
        self.app.processEvents()
        key = self.window.graph_tab.series[0].key()
        header = self.table.horizontalHeader()
        header.moveSection(0, 2)
        self.assertEqual([header.logicalIndex(v) for v in range(3)], [1, 2, 0])
        self.assertEqual(self.model.rows[0], ["2", "6", "9"])
        self.assertEqual(self.window.graph_tab.series[0].key(), key)
        self.select(2, 0, 2, 2)
        self.table.copy_selection()
        self.assertEqual(self.app.clipboard().text(), "6\t9\t2\n")
        self.select(3, 1)
        self.app.clipboard().setText("10\t11\t12")
        self.table.paste_clipboard()
        self.assertEqual(self.model.rows[1], ["12", "10", "11"])
        self.model.undo_stack.undo()
        self.assertEqual(self.model.rows[1], ["", "", ""])
        self.model.undo_stack.undo()
        self.assertEqual([header.logicalIndex(v) for v in range(3)], [0, 1, 2])

    def test_internal_formula_copy_and_external_formula_paste(self):
        self.put(0, 0, "2")
        self.put(1, 0, "4")
        self.put(0, 1, "=A1*2")
        self.select(2, 1)
        self.table.copy_selection()
        self.select(3, 1)
        self.table.paste_clipboard()
        self.assertEqual(self.model.formulas[1, 1], "=A2*2")
        self.assertEqual(self.model.rows[1][1], "8")
        self.select(4, 1)
        self.app.clipboard().setText("=SOMME(A1:A2;3)")
        self.table.paste_clipboard()
        self.assertEqual(self.model.rows[2][1], "9")

    def test_errors_recovery_and_cross_calculation_cycles(self):
        self.put(0, 0, "=1/0")
        self.assertEqual(self.model.rows[0][0], "#DIV/0!")
        self.put(0, 0, "=B1")
        self.put(0, 1, "=A1")
        self.assertEqual(self.model.rows[0], ["#CYCLE!", "#CYCLE!"])
        self.put(0, 1, "2")
        self.assertEqual(self.model.rows[0], ["2", "2"])
        self.window.calculations_tab.engine.add("double", "", expression="C1*2")
        self.put(0, 1, "=C1+1")
        self.assertEqual(self.model.rows[0][1], "#CYCLE!")
        self.put(0, 0, "3")
        self.app.processEvents()
        self.assertEqual(self.model.rows[0], ["3", "7", "6"])
        self.put(0, 0, "=Z1")
        self.assertEqual(self.model.rows[0][0], "#REF!")

    def test_deleted_column_adjusts_formula_references(self):
        self.model.add_quantity()
        self.put(0, 1, "4")
        self.put(0, 2, "=$B$1*2")
        self.model.remove_quantity(0)
        self.assertEqual(self.model.formulas[0, 1], "=$A$1*2")
        self.assertEqual(self.model.rows[0], ["4", "8"])
        self.model.remove_quantity(0)
        self.assertEqual(self.model.rows[0], ["#REF!"])

    def test_blank_ranges_new_column_and_redo_branch(self):
        self.put(0, 0, "2")
        self.put(2, 0, "4")
        self.put(0, 1, "=MOYENNE(A1:A3)")
        self.assertEqual(self.model.rows[0][1], "3")
        self.put(0, 1, "=C1+1")
        self.assertEqual(self.model.rows[0][1], "#REF!")
        self.model.add_quantity()
        self.assertEqual(self.model.rows[0][1], "1")
        self.model.undo_stack.undo()
        self.assertEqual(self.model.rows[0][1], "3")
        self.put(0, 0, "6")
        self.assertEqual(self.model.rows[0][1], "5")
        self.assertFalse(self.model.undo_stack.canRedo())

    def test_quantity_names_follow_rows_recopy_updates_and_mixed_references(self):
        self.model.add_quantity()
        self.model.edit_cells({(self.model.name_row, 2): "z"})
        for row, values in enumerate((("1", "2"), ("2", "4"), ("3", "6"))):
            for column, value in enumerate(values):
                self.put(row, column, value)
        self.put(0, 2, "=x+y")
        self.assertEqual(self.model.rows[0][2], "3")
        self.assertEqual(self.model.index(2, 2).data(Qt.ItemDataRole.EditRole), "=x+y")
        self.assertIn("[[Q0]]", self.model.formulas[0, 2])

        self.select(2, 2)
        QTest.mousePress(self.table.viewport(), Qt.MouseButton.LeftButton,
                         pos=self.table.fill_handle_rect().center())
        QTest.mouseMove(self.table.viewport(), self.table.visualRect(self.model.index(4, 2)).center())
        QTest.mouseRelease(self.table.viewport(), Qt.MouseButton.LeftButton,
                           pos=self.table.visualRect(self.model.index(4, 2)).center())
        self.assertEqual([row[2] for row in self.model.rows[:3]], ["3", "6", "9"])
        self.put(1, 0, "10")
        self.assertEqual(self.model.rows[1][2], "14")

        self.model.add_quantity()
        self.model.edit_cells({(self.model.name_row, 3): "mixte"})
        self.put(1, 3, "=x+B1")
        self.assertEqual(self.model.rows[1][3], "12")

    def test_quantity_name_rename_ambiguity_unicode_deletion_and_cycles(self):
        for name in ("z", "vx", "vy", "ω", "norme"):
            self.model.add_quantity()
            self.model.edit_cells({(self.model.name_row, self.model.columnCount() - 1): name})
        for column, value in ((0, "1"), (1, "2"), (3, "3"), (4, "4"), (5, "12")):
            self.put(0, column, value)
        self.put(0, 6, "=sqrt(vx^2+vy^2)+ω")
        self.assertEqual(self.model.rows[0][6], "17")

        self.put(0, 2, "=x+y")
        self.model.edit_cells({(self.model.name_row, 0): "distance"})
        self.assertEqual(self.model.index(2, 2).data(Qt.ItemDataRole.EditRole), "=distance+y")
        self.assertEqual(self.model.rows[0][2], "3")
        self.model.edit_cells({(self.model.name_row, 0): "y"})
        self.assertEqual(self.model.index(2, 2).data(Qt.ItemDataRole.EditRole), "=A1+B1")
        self.assertEqual(self.model.rows[0][2], "3")
        with self.assertRaisesRegex(ValueError, "plusieurs grandeurs"):
            CellFormula("=y+1", self.model.names, 0)
        with self.assertRaisesRegex(ValueError, "n'existe pas"):
            CellFormula("=vitesseX+vy", self.model.names, 0)

        self.model.edit_cells({(self.model.name_row, 0): "x"})
        self.put(1, 2, "=z+1")
        self.assertEqual(self.model.rows[1][2], "#CYCLE!")
        self.model.remove_quantity(0)
        self.assertIn("#REF!", self.model.formulas[0, 1])
        self.assertEqual(self.model.rows[0][1], "#REF!")

        with self.assertRaisesRegex(ValueError, "réservé"):
            CellFormula("=pi+1", ["pi"], 0)
        self.assertEqual(CellFormula("=sqrt(A1^2)", ["sqrt"], 0).evaluate(lambda r, c: 3), 3)

    def test_quantity_name_formula_project_roundtrip(self):
        self.model.add_quantity()
        self.model.edit_cells({(self.model.name_row, 2): "z"})
        self.put(0, 0, "2")
        self.put(0, 1, "5")
        self.put(0, 2, "=x+y")
        with tempfile.TemporaryDirectory(dir=os.environ.get("TEMP")) as directory:
            path = Path(directory) / "formule-noms.physalix"
            write_project(path, snapshot(self.window))
            reopened = MainWindow()
            try:
                restore(reopened, read_project(path), path)
                model = reopened.data_tab.model
                self.assertEqual(model.index(2, 2).data(Qt.ItemDataRole.EditRole), "=x+y")
                self.assertEqual(model.rows[0][2], "7")
                model.edit_cells({(model.name_row, 0): "temps"})
                self.assertEqual(model.index(2, 2).data(Qt.ItemDataRole.EditRole), "=temps+y")
                model.edit_cells({(2, 1): "8"})
                self.assertEqual(model.rows[0][2], "10")
            finally:
                reopened._discard_on_close = True
                reopened.close()
                self.app.processEvents()

    def test_quantity_names_from_formula_bar_and_double_clicked_cell(self):
        self.model.add_quantity()
        for column, name in enumerate(("vx", "vy", "norme")):
            self.model.edit_cells({(self.model.name_row, column): name})
        for row, values in enumerate((("3", "4"), ("5", "12"))):
            for column, value in enumerate(values):
                self.put(row, column, value)

        self.select(2, 2)
        QTest.keyClick(self.table, Qt.Key.Key_Equal)
        QTest.keyClicks(self.tab.formula_bar, "sqrt(vx^2+vy^2)")
        QTest.keyClick(self.tab.formula_bar, Qt.Key.Key_Return)
        self.assertEqual(self.model.rows[0][2], "5")
        self.assertEqual(self.model.index(2, 2).data(Qt.ItemDataRole.EditRole),
                         "=sqrt(vx^2+vy^2)")

        target = self.model.index(3, 2)
        QTest.mouseClick(self.table.viewport(), Qt.MouseButton.LeftButton,
                         pos=self.table.visualRect(target).center())
        QTest.mouseDClick(self.table.viewport(), Qt.MouseButton.LeftButton,
                          pos=self.table.visualRect(target).center())
        editor = self.app.focusWidget()
        self.assertIsInstance(editor, QLineEdit)
        QTest.keyClick(editor, Qt.Key.Key_Equal)
        QTest.keyClicks(self.tab.formula_bar, "vx+vy")
        self.tab.formula_bar.setCursorPosition(3)
        self.assertEqual(self.tab.formula_bar.cursorPosition(), 3)
        QTest.keyClick(self.tab.formula_bar, Qt.Key.Key_Return)
        self.assertEqual(self.model.rows[1][2], "17")

        QTest.keyClick(self.table, Qt.Key.Key_F2)
        self.tab.formula_bar.selectAll()
        QTest.keyClicks(self.tab.formula_bar, "=vitesseX+vy")
        with patch("physalix.ui.data_tab.QMessageBox.warning") as warning:
            QTest.keyClick(self.tab.formula_bar, Qt.Key.Key_Return)
            self.assertEqual(warning.call_count, 1)
        self.assertTrue(self.tab.formula_session.active)
        self.assertIn("n'existe pas", self.tab.formula_bar.toolTip())
        self.assertEqual(self.model.rows[1][2], "17")
        QTest.keyClick(self.tab.formula_bar, Qt.Key.Key_Escape)

    def test_formula_error_dialog_preserves_text_target_and_existing_formula(self):
        self.model.add_quantity()
        self.model.edit_cells({(self.model.name_row, 2): "z"})
        self.put(0, 0, "2")
        self.put(0, 1, "3")
        self.put(0, 2, "=x+y")
        previous = self.model.formulas[0, 2]
        target = self.model.index(2, 2)
        self.select(2, 2)
        QTest.keyClick(self.table, Qt.Key.Key_F2)
        self.tab.formula_bar.selectAll()
        QTest.keyClicks(self.tab.formula_bar, "=T+y")
        self.tab.formula_bar.setCursorPosition(2)

        with patch("physalix.ui.data_tab.QMessageBox.warning") as warning:
            QTest.keyClick(self.tab.formula_bar, Qt.Key.Key_Return)
            warning.assert_called_once_with(
                self.tab,
                "Impossible de calculer la formule",
                "La grandeur « T » n'existe pas dans le tableau. "
                "Vérifiez son nom ou utilisez une grandeur existante.",
            )
            self.assertTrue(self.tab.formula_session.active)
            self.assertEqual(self.tab.formula_bar.text(), "=T+y")
            self.assertEqual(self.tab.formula_bar.cursorPosition(), 2)
            self.assertEqual(QModelIndex(self.tab.formula_session.target), target)
            self.assertEqual(self.model.formulas[0, 2], previous)
            self.assertEqual(self.model.rows[0][2], "5")

            self.tab.formula_bar.selectAll()
            QTest.keyClicks(self.tab.formula_bar, "=x+y")
            QTest.keyClick(self.tab.formula_bar, Qt.Key.Key_Return)
            self.assertFalse(self.tab.formula_session.active)
            self.assertEqual(warning.call_count, 1)

            self.model.edit_cells({(2, 0): "4"})
            state = snapshot(self.window)
            reopened = MainWindow()
            try:
                restore(reopened, state)
                self.app.processEvents()
                self.assertEqual(reopened.data_tab.model.rows[0][2], "7")
                self.assertEqual(warning.call_count, 1)
            finally:
                reopened._discard_on_close = True
                reopened.close()
                self.app.processEvents()


class FormulaSyntaxTests(unittest.TestCase):
    def test_safe_functions_french_decimals_and_references(self):
        self.assertEqual(CellFormula("=RACINE(A1^2)+1,5").evaluate(lambda r, c: 3), 4.5)
        self.assertEqual(CellFormula("=LOG10(100)").evaluate(lambda r, c: 0), 2)
        self.assertEqual(column_label(26), "AA")
        self.assertEqual(translate_formula("=A1+$B1+C$1+$D$1+LOG10(A1)", 2, 1),
                         "=B3+$B3+D$1+$D$1+LOG10(B3)")
        self.assertEqual(translate_formula("=A1", -1), "=#REF!")
        for text in ("=__import__('os')", "=A1.real", "=[1,2]", "=open(1)", "=2**1000"):
            with self.subTest(text=text), self.assertRaises((ValueError, ArithmeticError)):
                CellFormula(text).evaluate(lambda r, c: 0)
