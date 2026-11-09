"""Vérifier les ajustements sur des données connues et les cas dégénérés."""

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import numpy as np
from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QWheelEvent
from PySide6.QtWidgets import QApplication

from physalix.fitting import Expression, MODELS, fit_model, parse_parameters
from physalix.ui.main_window import MainWindow
from physalix.ui.graph_series import PopupComboBox
from physalix.ui.theme import LIGHT


class FittingTests(unittest.TestCase):
    def test_polynomial_models(self):
        self.assertEqual(MODELS["quadratic"][0], "Polynôme du second degré (parabole)")
        x = np.linspace(-3, 4, 30)
        for kind, y, expected in (
            ("constant", x*0+7, [7]), ("linear", 3*x, [3]),
            ("affine", -2*x+4, [-2, 4]), ("square", 2*x*x, [2]),
            ("quadratic", -4*x*x+3*x+2, [-4, 3, 2]),
        ):
            with self.subTest(kind=kind):
                result = fit_model(x, y, kind)
                np.testing.assert_allclose(list(result.parameters.values()), expected, atol=1e-10)
                self.assertLess(result.rmse, 1e-10)
                self.assertEqual(result.r_squared is None, kind == "constant")

    def test_nonlinear_models_with_shifted_origin_and_irregular_samples(self):
        x = 4+np.linspace(0, 1, 80)**1.2*5
        for kind, y, expected in (
            ("charge", 0.3+5*(1-np.exp(-(x-4)/1.2)), [5, 1.2, 0.3]),
            ("discharge", 0.3+5*np.exp(-(x-4)/1.2), [5, 1.2, 0.3]),
            ("exponential", 2*np.exp(0.4*(x-4))+1, [2, 0.4, 1]),
            ("exponential_growth", 6.3-(6.3-1.2)*np.exp(-0.8*(x-4)), [6.3, 1.2, 0.8]),
            ("exponential_decay", 0.4+(5.7-0.4)*np.exp(-1.1*(x-4)), [0.4, 5.7, 1.1]),
            ("sine", 3*np.sin(5.3*(x-4)+0.7)+2, [3, 5.3, 0.7, 2]),
        ):
            with self.subTest(kind=kind):
                result = fit_model(x, y, kind)
                np.testing.assert_allclose(list(result.parameters.values()), expected, atol=1e-5)
                self.assertLess(result.rmse, 1e-7)

    def test_plateau_exponentials_enforce_direction_and_reject_degenerate_data(self):
        x = np.linspace(7, 12, 30)
        growth = fit_model(x, 4-(4-1.5)*np.exp(-0.6*(x-7)), "exponential_growth")
        decay = fit_model(x, -0.5+(3.2+0.5)*np.exp(-0.9*(x-7)), "exponential_decay")
        self.assertGreater(growth.parameters["y_inf"], growth.parameters["y0"])
        self.assertGreater(decay.parameters["y0"], decay.parameters["y_inf"])
        self.assertGreater(growth.parameters["k"], 0)
        self.assertGreater(decay.parameters["k"], 0)
        self.assertEqual(growth.x0, 7)
        self.assertEqual(decay.x0, 7)
        for kind in ("exponential_growth", "exponential_decay"):
            with self.subTest(kind=kind), self.assertRaisesRegex(ValueError, "variation"):
                fit_model(x, np.full_like(x, 2.5), kind)
            with self.subTest(kind=kind), self.assertRaisesRegex(ValueError, "3 abscisses"):
                fit_model([0, 1], [1, 2], kind)

    def test_quality_and_interval(self):
        x = np.arange(6.)
        y = np.array([1., 2, 4, 4, 7, 100])
        result = fit_model(x, y, "affine", interval=(0, 4))
        residual = y[:5]-(result.parameters["a"]*x[:5]+result.parameters["b"])
        sse = sum(residual**2)
        self.assertEqual(result.count, 5)
        self.assertAlmostEqual(result.rmse, np.sqrt(sse/5))
        self.assertAlmostEqual(result.residual_std, np.sqrt(sse/3))
        self.assertAlmostEqual(result.r_squared, 1-sse/sum((y[:5]-y[:5].mean())**2))
        self.assertIsNone(fit_model([0, 1], [1, 3], "affine").residual_std)
        self.assertLess(fit_model([1, 2, 3], [4, 4, 4.1], "linear").r_squared, 0)

    def test_custom_named_axis_and_decimal_comma(self):
        x = np.linspace(0, 3, 20)
        result = fit_model(x, 2*x*x+3, "custom", axis_name="Temps",
                           expression="a*Temps²+c", initial="a=0,5 ; c=0")
        np.testing.assert_allclose(list(result.parameters.values()), [2, 3], atol=1e-7)
        result = fit_model(x, x*0+4, "custom", expression="c", initial="c=1")
        self.assertAlmostEqual(result.parameters['c'], 4)

    def test_invalid_data_and_unsafe_expressions(self):
        for expression in ("__import__('os')", "x.__class__", "x[0]", "[a for a in x]", "open(x)", "a*z"):
            with self.subTest(expression=expression), self.assertRaises(ValueError):
                Expression(expression, ["a"])
        for text in ("x=1", "a=nan", "a=1;a=2", "pi=1", "a"):
            with self.assertRaises(ValueError):
                parse_parameters(text)
        for xs, ys, kind in (([], [], "affine"), ([1, 1, 1], [2, 3, 4], "quadratic"),
                             ([0], [2], "linear"), ([0, 1], [2, np.nan], "affine")):
            with self.assertRaises(ValueError):
                fit_model(xs, ys, kind)
        with self.assertRaises(ValueError):
            fit_model([-2, -1, 0], [1, 2, 3], "custom", expression="a*log(x)", initial="a=1")
        with self.assertRaises(ValueError):
            fit_model([0, 1, 2], [1, 2, 3], "affine", interval=(5, 6))


class ModelingInterfaceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_model_lifecycle_selection_and_series_isolation(self):
        window = MainWindow()
        graph, tab, model = window.graph_tab, window.modeling_tab, window.data_tab.model
        try:
            window.resize(1366, 768)
            window.show()
            window.show_module(window.tabs.indexOf(window.modeling_tab))
            self.app.processEvents()
            model.rows = [[str(x), str(2*x+3)] for x in range(8)]
            graph.refresh_plot()
            first = graph.series[0]
            tab.model_choice.setCurrentIndex(tab.model_choice.findData("affine"))
            tab.calculate()
            self.assertTrue(first.fits)
            self.assertEqual(tab.fits_list.count(), 1)
            self.assertFalse(tab.new_fit_button.geometry().intersects(
                tab.remove_button.geometry()))
            curve = first.fits[0].curve
            self.assertEqual(len(first.fits[0].result.x), 600)
            self.assertGreater(len(curve.getData()[0]), 600)
            self.assertIn("R² = 1", tab.result_text.toPlainText())
            first.connect_points.setChecked(True)
            self.assertTrue(first.fits)
            second = graph.add_series()
            self.assertFalse(second.fits)
            first.visible.setChecked(False)
            self.assertFalse(curve.isVisible())
            self.assertTrue(first.fits)
            self.assertIs(tab.current_series(), second)
            self.assertEqual(tab.fits_list.count(), 0)
            first.visible.setChecked(True)
            tab.series_choice.setCurrentIndex(tab.series_choice.findData(first.number))
            self.assertEqual(tab.fits_list.count(), 1)
            tab.range_check.setChecked(True)
            graph.fit_region.setRegion((2, 5))
            tab.calculate()
            self.assertEqual(first.fits[-1].result.count, 4)
            self.assertEqual(first.fits[-1].result.x[0], 2)
            model.rows[0][1] = "42"
            graph.refresh_plot()
            self.assertFalse(first.fits)
            self.assertNotIn(curve, graph.plot.getPlotItem().items)
            tab.calculate()
            self.assertTrue(first.fits)
            first.x_choice.setCurrentIndex(1)
            self.assertFalse(first.fits)
            tab.calculate()
            tab.remove_fit()
            self.assertFalse(first.fits)
            graph.remove_series(first)
            self.assertIs(tab.current_series(), second)
        finally:
            window._discard_on_close = True
            window.close()

    def test_model_selector_starts_on_constant_and_preserves_selection(self):
        window = MainWindow()
        try:
            tab = window.modeling_tab
            self.assertIsInstance(tab.model_choice, PopupComboBox)
            self.assertEqual(tab.model_choice.currentData(), "constant")
            tab.model_choice.showPopup()
            self.assertEqual(tab.model_choice.view().currentIndex().row(), 0)
            tab.model_choice.hidePopup()
            tab.model_choice.setCurrentIndex(tab.model_choice.findData("linear"))
            tab.sync_series()
            self.assertEqual(tab.model_choice.currentData(), "linear")
        finally:
            window._discard_on_close = True
            window.close()

    def test_model_selector_scrolls_to_last_user_model_without_selecting_it(self):
        window = MainWindow()
        try:
            window.show()
            window.tabs.setCurrentWidget(window.modeling_tab)
            self.app.processEvents()
            combo = window.modeling_tab.model_choice
            self.assertEqual(combo.count(), 12)
            self.assertEqual(combo.itemData(combo.count() - 1), "custom")
            self.assertEqual(combo.maxVisibleItems(), 8)
            combo.showPopup()
            self.app.processEvents()
            view = combo.view()
            selected = combo.currentIndex()
            center = combo.rect().center()
            event = QWheelEvent(
                QPointF(center), QPointF(combo.mapToGlobal(center)),
                QPoint(), QPoint(0, -120), Qt.MouseButton.NoButton,
                Qt.KeyboardModifier.NoModifier, Qt.ScrollPhase.ScrollUpdate, False,
            )
            combo.wheelEvent(event)
            last_rect = view.visualRect(combo.model().index(combo.count() - 1, 0))
            self.assertTrue(view.viewport().rect().contains(last_rect.center()))
            self.assertEqual(combo.currentIndex(), selected)
            combo.hidePopup()
        finally:
            window._discard_on_close = True
            window.close()

    def test_interval_editor_closes_after_calculation_and_restores_bounds(self):
        window = MainWindow()
        graph, tab, model = window.graph_tab, window.modeling_tab, window.data_tab.model
        try:
            window.show()
            window.show_module(window.tabs.indexOf(tab))
            model.rows = [[str(x), str(2*x+1)] for x in range(10)]
            graph.refresh_plot()
            tab.range_check.setChecked(True)
            self.assertFalse(graph.fit_region.isVisible())
            tab.select_button.click()
            self.assertIs(window.tabs.currentWidget(), graph)
            self.assertTrue(graph.fit_region.isVisible())
            self.assertTrue(graph.interval_tools.isVisible())
            graph.fit_region.setRegion((2, 6))
            graph.calculate_interval_button.click()
            self.assertIs(window.tabs.currentWidget(), graph)
            self.assertFalse(graph.fit_region.isVisible())
            self.assertFalse(graph.interval_tools.isVisible())
            self.assertEqual(tab.current_fit().settings['interval'], (2, 6))
            self.assertEqual(tab.current_fit().result.count, 5)
            window.tabs.setCurrentWidget(tab)
            tab.select_button.click()
            self.assertTrue(graph.fit_region.isVisible())
            self.assertEqual(graph.fit_region.getRegion(), (2, 6))
            graph.fit_region.setRegion((3, 7))
            window.tabs.setCurrentWidget(tab)
            tab.fit_button.click()
            self.assertFalse(graph.fit_region.isVisible())
            self.assertEqual(tab.current_fit().settings['interval'], (3, 7))
            self.assertEqual(len(graph.series[0].fits), 1)
            tab.select_button.click()
            graph.fit_region.setRegion((20, 30))
            graph.calculate_interval_button.click()
            self.assertTrue(graph.fit_region.isVisible())
            self.assertIn('impossible', graph.interval_hint.text())
            self.assertEqual(tab.current_fit().settings['interval'], (3, 7))
            graph.hide_interval_button.click()
            self.assertFalse(graph.fit_region.isVisible())
        finally:
            window._discard_on_close = True
            window.close()

    def test_linear_drawing_includes_origin_and_report_uses_axis_names(self):
        window = MainWindow()
        graph, tab, model = window.graph_tab, window.modeling_tab, window.data_tab.model
        try:
            model.names[:2] = ["c", "conductivité"]
            model.units[:2] = ["mmol/L", "mS/cm"]
            model.rows = [[str(x), str(3*x)] for x in range(2, 9)]
            graph.refresh_plot()
            tab.model_choice.setCurrentIndex(tab.model_choice.findData("linear"))
            tab.calculate()
            fit = graph.series[0].fits[0]
            self.assertEqual(fit.result.x[0], 2)
            curve_x, curve_y = fit.curve.getData()
            finite_x = curve_x[np.isfinite(curve_x)]
            finite_y = curve_y[np.isfinite(curve_y)]
            self.assertEqual(min(finite_x), 0)
            self.assertIn(0, finite_y)
            self.assertFalse(fit.extension.isVisible())
            pen = fit.curve.opts['pen']
            self.assertTrue(fit.curve.opts['antialias'])
            self.assertEqual(pen.style(), Qt.PenStyle.CustomDashLine)
            self.assertEqual(pen.dashPattern(), [7.0, 3.5])
            self.assertEqual(pen.capStyle(), Qt.PenCapStyle.RoundCap)
            self.assertAlmostEqual(pen.widthF(), 1.8)
            self.assertLessEqual(graph.plot.viewRange()[0][0], 0)
            report = tab.result_text.toPlainText()
            self.assertIn("conductivité = 3 · c", report)
            self.assertIn("Abscisse : c (mmol/L)", report)
            graph.refresh_reticle_menu()
            self.assertEqual(len(graph.reticle_source_actions), 2)
            model_action = next(action for action in graph.reticle_source_actions
                                if "Modélisation 1" in action.text())
            model_action.trigger()
            self.assertAlmostEqual(graph.reticle_curve_value(1)[0], 3)
            self.assertIsNone(graph.reticle_curve_value(-.01))
            self.assertIsNone(graph.reticle_curve_value(max(finite_x) + .01))
            graph.plot.setRange(xRange=(4, 6), yRange=(10, 20), padding=0)
            tab.show_graph_button.click()
            self.assertLessEqual(graph.plot.viewRange()[0][0], 0)
        finally:
            window._discard_on_close = True
            window.close()

    def test_visual_extension_stays_inside_custom_model_domain(self):
        window = MainWindow()
        graph, tab, model = window.graph_tab, window.modeling_tab, window.data_tab.model
        try:
            xs = [1, 4, 7, 10]
            model.rows = [[str(x), str(2*np.log(x)+1)] for x in xs]
            graph.refresh_plot()
            tab.model_choice.setCurrentIndex(tab.model_choice.findData("custom"))
            tab.expression.setText("a*log(x)+b")
            tab.initial.setText("a=1 ; b=0")
            tab.calculate()
            fit = graph.series[0].fits[0]
            curve_x, _ = fit.curve.getData()
            finite_x = curve_x[np.isfinite(curve_x)]
            self.assertGreater(min(finite_x), 0)
            self.assertLessEqual(max(finite_x), 10 + .12*(10-1) + 1e-12)
            self.assertEqual((fit.result.x[0], fit.result.x[-1]), (1, 10))
        finally:
            window._discard_on_close = True
            window.close()

    def test_plateau_models_are_explicit_and_limited_to_selected_domain(self):
        window = MainWindow()
        graph, tab, model = window.graph_tab, window.modeling_tab, window.data_tab.model
        try:
            xs = np.arange(1., 9.)
            ys = 5-(5-1.4)*np.exp(-0.7*(xs-1))
            model.rows = [[str(x), str(y)] for x, y in zip(xs, ys)]
            graph.refresh_plot()
            self.assertFalse(graph.series[0].fits)
            self.assertEqual(MODELS["exponential_growth"][0], "Croissance exponentielle")
            self.assertEqual(MODELS["exponential_decay"][0], "Décroissance exponentielle")
            tab.model_choice.setCurrentIndex(tab.model_choice.findData("exponential_growth"))
            self.assertFalse(graph.series[0].fits)
            tab.range_check.setChecked(True)
            graph.fit_region.setRegion((3, 7))
            tab.calculate()
            fit = graph.series[0].fits[0]
            curve_x, _ = fit.curve.getData()
            point_x, _ = graph.series[0].points.getData()
            self.assertEqual((curve_x[0], curve_x[-1]), (3, 7))
            self.assertEqual((fit.result.x0, fit.result.x[0], fit.result.x[-1]), (3, 3, 7))
            self.assertEqual((point_x[0], point_x[-1]), (1, 8))
            self.assertIn("y∞", tab.result_text.toPlainText())
            self.assertIn("R²", tab.result_text.toPlainText())
        finally:
            window._discard_on_close = True
            window.close()

    def test_two_affine_intervals_and_independent_updates(self):
        window = MainWindow()
        graph, tab, model = window.graph_tab, window.modeling_tab, window.data_tab.model
        try:
            window.resize(1100, 700)
            window.show()
            window.show_module(window.tabs.indexOf(window.modeling_tab))
            self.app.processEvents()
            # Deux branches séparées ; intersection (10, 2) sous tous les points mesurés.
            model.rows = [[str(x), str(12-x if x < 10 else x-8)]
                          for x in [0, 1, 2, 3, 17, 18, 19, 20]]
            graph.refresh_plot()
            series = graph.series[0]
            tab.model_choice.setCurrentIndex(tab.model_choice.findData("affine"))
            tab.range_check.setChecked(True)
            graph.fit_region.setRegion((0, 3))
            tab.calculate()
            first = series.fits[0]
            tab.new_fit_button.click()
            graph.fit_region.setRegion((17, 20))
            tab.calculate()
            second = series.fits[1]
            self.assertEqual(len(series.fits), 2)
            self.assertIsInstance(tab.series_choice, PopupComboBox)
            self.assertIsInstance(tab.fit_choice, PopupComboBox)
            self.assertEqual(tab.fits_list.count(), 2)
            self.assertFalse(tab.new_fit_button.geometry().intersects(
                tab.remove_button.geometry()))
            self.assertIn("S1 ·", tab.fits_list.item(0).text())
            self.assertIn("Affine", tab.fits_list.item(0).text())
            lines = tab.fits_list.item(0).text().splitlines()
            self.assertEqual(len(lines), 3)
            self.assertIn(" = ", lines[1])
            self.assertTrue(lines[2].startswith("R² ="))
            expected_height = 3 * tab.fits_list.fontMetrics().lineSpacing() + 2 * LIGHT.small
            self.assertGreaterEqual(tab.fits_list.item(0).sizeHint().height(), expected_height)
            tab.fits_list.setCurrentRow(0)
            self.assertIs(tab.current_fit(), first)
            self.assertEqual(tab.fits_list.selectedItems(), [tab.fits_list.item(0)])
            self.assertEqual(first.result.count, 4)
            self.assertEqual(second.result.count, 4)
            self.assertNotEqual(first.color, second.color)
            self.assertEqual(len(graph.legend.items), 3)
            for fit in series.fits:
                self.assertFalse(fit.extension.isVisible())
                curve_x, _ = fit.curve.getData()
                finite_x = curve_x[np.isfinite(curve_x)]
                self.assertGreater(min(finite_x), -2.5)
                self.assertLess(min(finite_x), 0)
                self.assertGreater(max(finite_x), 20)
                self.assertLess(max(finite_x), 22.5)
                self.assertAlmostEqual(fit.result.parameters['a']*10+fit.result.parameters['b'], 2)
            self.assertLess(graph.plot.viewRange()[1][0], 2)
            tab.fit_choice.setCurrentIndex(tab.fit_choice.findData(first.number))
            self.assertEqual(tab.interval(), (0, 3))
            graph.fit_region.setRegion((0, 2))
            tab.calculate()
            self.assertEqual(len(series.fits), 2)
            self.assertEqual(first.result.count, 3)
            self.assertEqual(second.result.count, 4)
            tab.extend_check.setChecked(False)
            self.assertFalse(first.extension.isVisible())
            self.assertFalse(second.extension.isVisible())
            self.assertEqual((first.curve.getData()[0][0], first.curve.getData()[0][-1]),
                             (first.result.x[0], first.result.x[-1]))
            self.assertGreater(second.curve.getData()[0][-1], second.result.x[-1])
            series.visible.setChecked(False)
            self.assertFalse(second.curve.isVisible())
            self.assertFalse(second.extension.isVisible())
            series.visible.setChecked(True)
            tab.fit_choice.setCurrentIndex(tab.fit_choice.findData(first.number))
            tab.remove_fit()
            self.assertEqual(series.fits, [second])
            self.assertEqual(tab.fits_list.count(), 1)
            self.assertIs(tab.current_fit(), second)
            self.assertFalse(tab.new_fit_button.geometry().intersects(
                tab.remove_button.geometry()))
            tab.new_fit_button.click()
            tab.calculate()
            self.assertEqual(len(series.fits), 2)
            self.assertEqual(tab.fits_list.count(), 2)
            self.assertFalse(tab.new_fit_button.geometry().intersects(
                tab.remove_button.geometry()))
            tab.new_fit_button.click()
            tab.calculate()
            self.assertEqual(len(series.fits), 3)
            self.assertEqual(tab.fits_list.count(), 3)
            tab.fits_list.setCurrentRow(2)
            tab.fits_list.scrollToItem(tab.fits_list.item(2))
            self.app.processEvents()
            self.assertGreater(tab.fits_list.verticalScrollBar().maximum(), 0)
            self.assertEqual(tab.fits_list.horizontalScrollBarPolicy(),
                             Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            for width, height in ((1100, 700), (1366, 768)):
                window.resize(width, height)
                self.app.processEvents()
                selected = tab.fits_list.visualItemRect(tab.fits_list.item(2))
                self.assertGreaterEqual(selected.height(), expected_height)
                self.assertTrue(tab.fits_list.viewport().rect().contains(selected.topLeft()))
                self.assertTrue(tab.fits_list.viewport().rect().contains(selected.bottomRight()))
                self.assertFalse(tab.new_fit_button.geometry().intersects(
                    tab.remove_button.geometry()))
            self.assertNotIn(first.curve, graph.plot.getPlotItem().items)
            self.assertNotIn(first.extension, graph.plot.getPlotItem().items)
            model.rows[0][1] = '13'
            graph.refresh_plot()
            self.assertFalse(series.fits)
            self.assertNotIn(second.extension, graph.plot.getPlotItem().items)
        finally:
            window._discard_on_close = True
            window.close()


if __name__ == "__main__":
    unittest.main()
