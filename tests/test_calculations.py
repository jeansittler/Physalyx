"""Dérivées physiques, expressions et recalcul des chaînes de grandeurs."""

import os
import math
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLabel, QMessageBox

from physalix.calculations import (CalculationEngine, Formula, FormulaError,
                                   derivative_unit)
from physalix.ui.data_tab import MeasurementsModel
from physalix.ui.main_window import MainWindow
from physalix.ui.graph_series import PopupComboBox
from physalix.ui.theme import LIGHT


class FormulaTests(unittest.TestCase):
    def test_notations_and_functions(self):
        for expression in ("SQRT(Vx^2 + Vy^2)", "sqrt(Vx² + Vy²)", "sqrt(C1**2 + C2**2)"):
            self.assertEqual(Formula(expression, ["Vx", "Vy"]).evaluate(["3", "4"]), 5)
        self.assertAlmostEqual(Formula("SIN(pi/2) + LN(e) + 1,5", []).evaluate([]), 3.5)
        self.assertEqual(Formula("-2^2", []).evaluate([]), -4)
        self.assertEqual(Formula("2^3^2", []).evaluate([]), 512)
        self.assertEqual(Formula("ABS(-3) + 2×4", []).evaluate([]), 11)
        self.assertEqual(Formula("σ*2", ["σ"]).evaluate(["3"]), 6)

    def test_invalid_and_unsafe_formulas(self):
        for expression in ("__import__('os')", "C1.real", "C1[0]", "[x for x in C1]",
                           "lambda: 1", "sqrt(1, 2)", "unknown + 1", "True", "1e999", "sqrt("):
            with self.subTest(expression=expression), self.assertRaises(ValueError):
                Formula(expression, ["X"])
        with self.assertRaises(ValueError):
            Formula("X + 1", ["X", "X"])
        self.assertEqual(Formula("C2", ["X", "X"]).evaluate(["1", "2"]), 2)
        for expression in ("1/0", "sqrt(-1)", "2^101", "exp(1000)"):
            with self.subTest(expression=expression), self.assertRaises((ArithmeticError, ValueError)):
                Formula(expression, []).evaluate([])

    def test_formula_errors_are_classified_for_students(self):
        for expression, kind, text in (
                ("missing + 1", "unknown_quantity", "n’existe pas"),
                ("mystery(X)", "unknown_function", "fonction"),
                ("sqrt(", "syntax", "syntaxe"),
                ("X + 1", "ambiguous", "plusieurs")):
            names = ["X", "X"] if kind == "ambiguous" else ["X"]
            with self.subTest(expression=expression), self.assertRaises(FormulaError) as caught:
                Formula(expression, names)
            self.assertEqual(caught.exception.kind, kind)
            self.assertIn(text, str(caught.exception))


class CalculationsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def make_model(self):
        model = MeasurementsModel()
        model.add_quantity()
        model.names = ["X", "Y", "t"]
        model.units = ["m", "m", "s"]
        for i in range(7):
            model.rows[i] = [str(i*i), str(3*i), str(i)]
        return model

    def test_derivative_speed_acceleration_and_rename(self):
        model = self.make_model()
        engine = CalculationEngine(model)
        vx = engine.add("Vx", "m/s", source=0, axis=2)
        vy = engine.add("Vy", "m/s", source=1, axis=2)
        speed = engine.add("v", "m/s", expression="SQRT(Vx² + Vy²)")
        accel = engine.add("ax", "m/s²", source=vx, axis=2)
        self.assertEqual([row[vx] for row in model.rows[:7]], ["", "2", "4", "6", "8", "10", ""])
        self.assertEqual([row[accel] for row in model.rows[:7]], ["", "", "2", "2", "2", "", ""])
        self.assertEqual(model.rows[2][speed], "5")
        self.assertEqual(model.rows[0][speed], "")
        model.setData(model.index(0, vx), "vitesse horizontale")
        model.setData(model.index(5, 0), "15")  # X à t=3, au lieu de 9.
        QTest.qWait(10)
        self.assertEqual(model.rows[2][vx], "7")
        self.assertAlmostEqual(float(model.rows[2][speed]), 58**.5)
        self.assertIn("vitesse horizontale", engine.items[2].formula.description(model.names))
        self.assertFalse(model.setData(model.index(4, vx), "999"))
        self.assertFalse(model.flags(model.index(4, vx)) & Qt.ItemFlag.ItemIsEditable)
        self.assertTrue(model.flags(model.index(0, vx)) & Qt.ItemFlag.ItemIsEditable)

    def test_missing_nonmonotonic_and_variable_intervals(self):
        model = self.make_model()
        engine = CalculationEngine(model)
        column = engine.add("D", "m/s", source=0, axis=2)
        model.rows[2][0] = ""
        engine.recalculate()
        self.assertEqual([model.rows[i][column] for i in (1, 2, 3)], ["", "", ""])
        self.assertEqual(model.rows[4][column], "8")
        model.rows[2][0] = "4"
        model.rows[2][2] = "1"  # Temps répété.
        engine.recalculate()
        self.assertEqual(model.rows[1][column], "")
        self.assertEqual(model.rows[2][column], "")
        model.rows[2][2] = "1.5"
        engine.recalculate()
        self.assertAlmostEqual(float(model.rows[1][column]), 4/1.5)
        self.assertIn("pas variable", engine.items[0].status)

    def test_formula_domain_errors_keep_row_alignment(self):
        model = self.make_model()
        engine = CalculationEngine(model)
        column = engine.add("ratio", "", expression="1/(t-2)")
        self.assertEqual(model.rows[1][column], "-1")
        self.assertEqual(model.rows[2][column], "")
        self.assertEqual(model.rows[3][column], "1")
        self.assertIn("1 erreur", engine.items[0].status)
        before = model.columnCount()
        with self.assertRaises(ValueError):
            engine.add("bad", "", expression="sqrt(X")
        self.assertEqual(model.columnCount(), before)
        with self.assertRaisesRegex(FormulaError, "mathématiquement impossible") as caught:
            engine.add("impossible", "", expression="sqrt(-X-1)")
        self.assertEqual(caught.exception.kind, "math")
        self.assertEqual(model.columnCount(), before)
        constant = engine.add("g", "m/s²", expression="9,81")
        self.assertEqual(model.rows[6][constant], "9.81")
        self.assertEqual(model.rows[7][constant], "")
        self.assertEqual(derivative_unit("m/s", "s"), "m/s²")
        self.assertEqual(derivative_unit("cm", "s"), "cm/s")

    def test_manual_logarithmic_linearization_preserves_measurements_and_can_be_graphed(self):
        window = MainWindow()
        try:
            model = window.data_tab.model
            model.names[:2] = ["Absorbance", "Temps"]
            model.units[:2] = ["", "s"]
            source_rows = [["0.5", "0"], ["1", "1"], ["1.5", "2"], ["2", "3"]]
            model.rows = [row[:] for row in source_rows]
            column = window.calculations_tab.engine.add(
                "Linéarisation choisie", "", expression="ln(1,5-Absorbance)")
            self.assertEqual(model.rows[0][column], "0")
            self.assertAlmostEqual(float(model.rows[1][column]), math.log(0.5), places=11)
            self.assertEqual([model.rows[i][column] for i in (2, 3)], ["", ""])
            self.assertIn("2 erreur(s) de calcul", window.calculations_tab.engine.items[0].status)
            self.assertEqual([row[:2] for row in model.rows], source_rows)

            graph = window.graph_tab
            graph.sync_columns()
            series = graph.series[0]
            series.x_choice.setCurrentIndex(series.x_choice.findData(1))
            series.y_choice.setCurrentIndex(series.y_choice.findData(column))
            graph.refresh_plot()
            self.assertEqual(len(series.points.getData()[0]), 2)
            tab = window.modeling_tab
            tab.model_choice.setCurrentIndex(tab.model_choice.findData("affine"))
            self.assertFalse(series.fits)
            tab.calculate()
            self.assertEqual(series.fits[0].kind, "affine")
        finally:
            window._discard_on_close = True
            window.close()

    def test_suggested_units_follow_sources_and_manual_unit_is_preserved(self):
        model = self.make_model()
        engine = CalculationEngine(model)
        velocity = engine.add("Vx", "m/s", source=0, axis=2)
        acceleration = engine.add("ax", "m/s²", source=velocity, axis=2)
        model.setData(model.index(1, 0), "cm")
        QTest.qWait(10)
        self.assertEqual(model.units[velocity], "cm/s")
        self.assertEqual(model.units[acceleration], "cm/s²")
        model.setData(model.index(1, velocity), "unité personnalisée")
        QTest.qWait(10)
        model.setData(model.index(1, 0), "mm")
        QTest.qWait(10)
        self.assertEqual(model.units[velocity], "unité personnalisée")

    def test_ui_creation_and_graph_available(self):
        window = MainWindow()
        try:
            window.show()
            tab = window.calculations_tab
            model = window.data_tab.model
            model.add_quantity()
            for i, name in enumerate(("X", "Y", "t")):
                model.setData(model.index(0, i), name)
            for row in range(5):
                for col, value in enumerate((row*row, 3*row, row)):
                    model.setData(model.index(row+2, col), str(value))
            QTest.qWait(10)
            window.tabs.setCurrentWidget(tab)
            tab.source.setCurrentIndex(0)
            tab.axis.setCurrentIndex(2)
            tab.derivative_name.setText("Vx")
            tab.derive_button.click()
            tab.source.setCurrentIndex(1)
            tab.derivative_name.setText("Vy")
            tab.derive_button.click()
            tab.formula_name.setText("v")
            tab.expression.setText("SQRT(Vx^2 + Vy^2)")
            tab.formula_button.click()
            QTest.qWait(10)
            self.assertEqual(model.names[-3:], ["Vx", "Vy", "v"])
            self.assertEqual(model.rows[2][-1], "5")
            self.assertEqual(tab.history.rowCount(), 3)
            self.assertEqual(window.graph_tab.series[0].x_choice.count(), 6)
        finally:
            window._discard_on_close = True
            window.close()

    def test_formula_primary_action_precedes_optional_quantity_insertion(self):
        window = MainWindow()
        try:
            window.resize(900, 650)
            window.show()
            tab = window.calculations_tab
            window.show_module(window.tabs.indexOf(tab))
            self.app.processEvents()

            self.assertFalse(tab.quantity_toggle.isChecked())
            self.assertFalse(tab.quantity_options.isVisible())
            self.assertIn("facultatif", tab.quantity_toggle.text())
            self.assertLess(tab.formula_button.mapTo(tab, tab.formula_button.rect().topLeft()).y(),
                            tab.quantity_toggle.mapTo(tab, tab.quantity_toggle.rect().topLeft()).y())

            tab.quantity_toggle.click()
            self.app.processEvents()
            self.assertTrue(tab.quantity_options.isVisible())
            self.assertTrue(tab.quantity.isVisible())
            self.assertTrue(tab.quantity_insert_button.isVisible())
            self.assertTrue(tab.quantity_toggle.text().endswith("▾"))
            self.assertEqual(tab.quantity.itemText(0), "x")
            self.assertEqual(tab.quantity.itemText(1), "y")

            tab.expression.setText("AB")
            tab.expression.setCursorPosition(1)
            tab.quantity.setCurrentIndex(1)
            tab.quantity_insert_button.click()
            self.assertEqual(tab.expression.text(), "AyB")
            self.assertEqual(tab.expression.cursorPosition(), 2)
            self.assertTrue(tab.expression.hasFocus())

            tab.quantity_toggle.click()
            self.assertFalse(tab.quantity_options.isVisible())
            self.assertEqual(tab.expression.text(), "AyB")
        finally:
            window._discard_on_close = True
            window.close()

    def test_quantity_selectors_use_bounded_reference_popups(self):
        window = MainWindow()
        try:
            tab = window.calculations_tab
            window.show()
            window.tabs.setCurrentWidget(tab)
            self.app.processEvents()
            model = window.data_tab.model
            for _ in range(13):
                model.add_quantity()
            tab.refresh()
            for combo in (tab.source, tab.axis, tab.quantity):
                with self.subTest(combo=combo):
                    self.assertIsInstance(combo, PopupComboBox)
                    self.assertEqual(combo.maxVisibleItems(), 8)
                    combo.showPopup()
                    self.app.processEvents()
                    self.assertEqual(combo.view().height(),
                                     8 * combo.view().sizeHintForRow(0) +
                                     2 * (LIGHT.small + combo.view().frameWidth()))
                    self.assertEqual(combo.view().verticalScrollBarPolicy(),
                                     Qt.ScrollBarPolicy.ScrollBarAsNeeded)
                    scrollbar = combo.view().verticalScrollBar()
                    scrollbar.setValue(scrollbar.maximum())
                    self.app.processEvents()
                    last = combo.view().visualRect(
                        combo.model().index(combo.count() - 1, 0))
                    self.assertTrue(combo.view().viewport().rect().contains(last))
                    container = combo.view().parentWidget()
                    self.assertTrue(container.rect().contains(
                        combo.view().viewport().mapTo(container, last.bottomRight())))
                    combo.hidePopup()
        finally:
            window._discard_on_close = True
            window.close()

    def test_unicode_names_derivative_and_formula(self):
        window = MainWindow()
        try:
            window.show()
            tab = window.calculations_tab
            model = window.data_tab.model
            model.setData(model.index(0, 0), "σ")
            model.setData(model.index(0, 1), "t")
            for row in range(5):
                model.setData(model.index(row + 2, 0), str(row * row))
                model.setData(model.index(row + 2, 1), str(row))
            tab.refresh()
            tab.source.setCurrentIndex(0)
            tab.axis.setCurrentIndex(1)
            tab.derivative_name.setText("Δ")
            tab.derive_button.click()
            tab.formula_name.setText("ω")
            tab.expression.setText("σ*2")
            tab.formula_button.click()
            self.assertEqual(model.names[-2:], ["Δ", "ω"])
            self.assertEqual(model.rows[2][-1], "8")
        finally:
            window._discard_on_close = True
            window.close()

    def test_derivative_wording_name_history_and_formula_error_dialog(self):
        window = MainWindow()
        tab = window.calculations_tab
        try:
            window.show()
            window.show_module(window.tabs.indexOf(tab))
            self.app.processEvents()
            # Utiliser le modèle partagé par l'onglet réellement construit.
            actual = window.data_tab.model
            actual.add_quantity()
            actual.names = ["x", "y", "t"]
            actual.units = ["m", "m", "s"]
            for row in range(5):
                actual.rows[row] = [str(row * row), str(2 * row), str(row)]
            tab.refresh()
            tab.source.setCurrentIndex(1)
            tab.axis.setCurrentIndex(2)
            self.assertEqual(tab.derivative_name.text(), "dy/dt")
            self.assertIn("Calcul de dérivée", [label.text() for label in tab.findChildren(QLabel)])
            tab.derive_button.click()
            self.assertEqual(actual.names[-1], "dy/dt")
            self.assertEqual(tab.history.item(0, 2).text(), "d(y) / d(t)")
            self.assertNotIn("centrée", tab.history.item(0, 2).text())

            tab.formula_name.setText("invalide")
            with patch.object(QMessageBox, "warning", return_value=QMessageBox.StandardButton.Ok) as warning:
                tab.expression.setText("XY + 1")
                warning.assert_not_called()
                tab.formula_button.click()
                warning.assert_called_once()
                self.assertEqual(warning.call_args.args[1], "Impossible de calculer la formule")
                self.assertIn("La grandeur « XY » n’existe pas", warning.call_args.args[2])
                self.assertIn("liste des grandeurs", warning.call_args.args[2])
                self.assertEqual(tab.formula_name.text(), "invalide")
                self.assertEqual(tab.expression.text(), "XY + 1")
                tab.formula_name.setText("valide")
                self.assertGreater(tab.formula_unit.findText("m/s"), -1)
                tab.formula_unit.setCurrentText("unité personnalisée")
                # Le nom visible contient '/', mais la référence stable C4 reste utilisable.
                tab.expression.setText("C4 * 2")
                tab.formula_button.click()
                self.assertEqual(warning.call_count, 1)
                self.assertEqual(actual.names[-1], "valide")
                self.assertEqual(actual.units[-1], "unité personnalisée")
                self.assertEqual(tab.formula_name.text(), "")
                self.assertEqual(tab.formula_unit.currentText(), "")
                self.assertEqual(tab.expression.text(), "")
                self.assertTrue(tab.formula_name.hasFocus())
        finally:
            window._discard_on_close = True
            window.close()
