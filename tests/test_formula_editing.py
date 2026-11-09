"""Modification en place, dépendances et accès à l'éditeur de formule."""
import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import QPointF
from PySide6.QtWidgets import QApplication, QDialog, QDialogButtonBox, QMessageBox
from PySide6.QtTest import QTest
from physalix.calculations import CalculationEngine, Formula
from physalix.ui.data_tab import MeasurementsModel
from physalix.ui.calculations_tab import (CalculationsTab, DerivativeEditDialog,
                                          FormulaEditDialog)
from physalix.ui.video_tracking import TrackingSession


class FormulaEditingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.model = MeasurementsModel()
        self.model.rows = [["1", "2"], ["2", "4"], ["3", "6"]]
        self.engine = CalculationEngine(self.model)

    def test_edit_recalculates_chain_and_preserves_column(self):
        a = self.engine.add("a", "m", expression="x*2")
        b = self.engine.add("b", "m", expression="a+1")
        self.engine.update_formula(a, "y*3")
        self.assertEqual(self.model.rows[0], ["1", "2", "6", "7"])
        self.assertEqual(self.model.names, ["x", "y", "a", "b"])
        self.assertEqual(self.model.units[a], "m")
        self.assertEqual(self.model.column_dependencies[a], {1})
        self.assertEqual(self.model.quantities_to_remove(0), [0])
        self.assertEqual(self.model.quantities_to_remove(1), [1, a, b])

    def test_new_reference_to_later_column_reorders_calculation(self):
        a = self.engine.add("a", "", expression="x")
        b = self.engine.add("b", "", expression="y*2")
        d = self.engine.add("d", "", source=a, axis=0)
        self.engine.update_formula(a, "b*3")
        self.assertEqual([item.column for item in self.engine.items], [a, b, d])
        self.assertEqual(self.model.rows[1][a], "24")
        self.assertEqual(self.model.rows[1][d], "12")
        self.model.setData(self.model.index(3, 1), "5")
        QTest.qWait(10)
        self.assertEqual(self.model.rows[1][a], "30")

    def test_invalid_and_circular_edits_are_atomic(self):
        a = self.engine.add("a", "", expression="x*2")
        b = self.engine.add("b", "", expression="a+1")
        original = self.engine.items[0].formula
        rows = [row[:] for row in self.model.rows]
        for expression in ("sqrt(", "a+1", "b*2", "C3", "missing"):
            with self.subTest(expression=expression), self.assertRaises(ValueError):
                self.engine.update_formula(a, expression)
            self.assertIs(self.engine.items[0].formula, original)
            self.assertEqual(self.model.rows, rows)
            self.assertEqual(self.model.column_dependencies[a], {0})

    def test_editable_expression_survives_rename_and_column_removal(self):
        a = self.engine.add("a", "", expression="y^2 + SQRT(y)")
        self.model.setData(self.model.index(0, 1), "position mesurée")
        self.model.remove_quantity(0)
        QTest.qWait(10)
        item = self.engine.items[0]
        expression = item.formula.editable_expression()
        self.assertIn("C1", expression)
        self.engine.update_formula(item.column, expression)
        self.assertAlmostEqual(float(self.model.rows[0][item.column]), 4 + 2 ** .5)
        # Une fonction et une grandeur peuvent partager leur nom.
        f = Formula("sqrt + sqrt(4)", ["sqrt"])
        self.assertEqual(Formula(f.editable_expression(), ["renamed"]).evaluate(["3"]), 5)

    def test_dialog_cancel_error_and_save(self):
        a = self.engine.add("a", "", expression="x*2")
        item = self.engine.items[0]
        dialog = FormulaEditDialog(self.engine, item)
        self.assertIn("x", dialog.expression.text())
        self.assertNotIn("C1", dialog.expression.text())
        dialog.expression.setText("x*5")
        dialog.reject()
        self.assertEqual(self.model.rows[0][a], "2")
        dialog = FormulaEditDialog(self.engine, item)
        dialog.expression.setText("a+1")
        with patch.object(QMessageBox, "warning") as warning:
            dialog.save()
            warning.assert_called_once()
        self.assertTrue(dialog.error.text())
        self.assertNotEqual(dialog.result(), QDialog.DialogCode.Accepted)
        self.assertEqual(self.model.rows[0][a], "2")
        dialog.expression.setText("x*5")
        dialog.unit.setCurrentText("m/s")
        dialog.save()
        self.assertEqual(dialog.result(), QDialog.DialogCode.Accepted)
        self.assertEqual(self.model.rows[0][a], "5")
        self.assertEqual(self.model.units[a], "m/s")

    def test_derivative_dialog_cancel_is_translated(self):
        self.engine.add("d", "", source=1, axis=0)
        dialog = DerivativeEditDialog(self.engine, self.engine.items[0])
        buttons = dialog.findChild(QDialogButtonBox)
        self.assertEqual(
            buttons.button(QDialogButtonBox.StandardButton.Cancel).text(), "Annuler")
        dialog.close()

    def test_table_double_click_and_button_open_formula_and_derivative(self):
        tab = CalculationsTab(self.model)
        tab.engine.add("a", "", expression="x*2")
        tab.engine.add("d", "", source=1, axis=0)
        tab.history.selectRow(0)
        self.assertTrue(tab.edit_formula_button.isEnabled())
        with (patch.object(FormulaEditDialog, "exec", return_value=QDialog.DialogCode.Rejected) as formulas,
              patch.object(DerivativeEditDialog, "exec", return_value=QDialog.DialogCode.Rejected) as derivatives):
            tab.history.cellDoubleClicked.emit(0, 2)
            tab.edit_formula_button.click()
            self.assertEqual(formulas.call_count, 2)
            tab.history.selectRow(1)
            self.assertTrue(tab.edit_formula_button.isEnabled())
            tab.history.cellDoubleClicked.emit(1, 2)
            self.assertEqual(derivatives.call_count, 1)
        tab.close()

    def test_derivative_edit_is_atomic_and_preserves_dependents(self):
        derivative = self.engine.add("d", "", source=1, axis=0)
        dependent = self.engine.add("double", "", expression="d*2")
        self.engine.update_derivative(derivative, "dx/dy", "s", 0, 1)
        item = self.engine.items[0]
        self.assertEqual(item.kind, "derivative")
        self.assertIsNone(item.formula)
        self.assertEqual((item.source, item.axis), (0, 1))
        self.assertEqual(self.model.names[derivative], "dx/dy")
        self.assertEqual(self.model.column_dependencies[derivative], {0, 1})
        self.assertEqual(float(self.model.rows[1][dependent]), 1.0)
        before = (item.source, item.axis, self.model.names[derivative])
        with self.assertRaisesRegex(ValueError, "circulaire"):
            self.engine.update_derivative(derivative, "cycle", "", dependent, 0)
        self.assertEqual((item.source, item.axis, self.model.names[derivative]), before)

    def test_delete_calculation_confirms_dependent_removal(self):
        tab = CalculationsTab(self.model)
        derivative = tab.engine.add("d", "", source=1, axis=0)
        tab.engine.add("double", "", expression="d*2")
        with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes) as question:
            tab.delete_calculation(0)
        self.assertIn("double", question.call_args.args[2])
        self.assertEqual(self.model.names, ["x", "y"])
        self.assertEqual(tab.engine.items, [])
        tab.close()

    def test_lowercase_defaults_and_video_suffixes(self):
        model = MeasurementsModel()
        self.assertEqual(model.names, ["x", "y"])
        TrackingSession(model).set_origin(QPointF(0, 0))
        self.assertEqual(model.names, ["x", "y", "t"])
        TrackingSession(model).set_origin(QPointF(0, 0))
        self.assertEqual(model.names[-3:], ["x_2", "y_2", "t_2"])
