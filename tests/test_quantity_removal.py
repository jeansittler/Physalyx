"""Suppression de colonnes et maintien des références aux grandeurs restantes."""

import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, QPointF, QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMessageBox

from physalix.ui.main_window import MainWindow
from physalix.ui.data_tab import MeasurementsModel
from physalix.ui.video_tracking import TrackingSession


class QuantityRemovalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_calculation_chain_and_graph_references(self):
        window = MainWindow()
        try:
            model = window.data_tab.model
            engine = window.calculations_tab.engine
            model.rows[0] = ["3", "4"]
            engine.add("doubleY", "", expression="C2*2")
            engine.add("square", "", expression="doubleY^2")
            QTest.qWait(10)
            series = window.graph_tab.series[0]
            series.x_choice.setCurrentIndex(1)
            series.y_choice.setCurrentIndex(3)
            model.remove_quantity(0)
            QTest.qWait(10)
            self.assertEqual(model.names, ["y", "doubleY", "square"])
            self.assertEqual(model.rows[0], ["4", "8", "64"])
            self.assertEqual(series.key(), (0, 2))
            model.setData(model.index(2, 0), "5")
            QTest.qWait(10)
            self.assertEqual(model.rows[0], ["5", "10", "100"])
            self.assertEqual(model.calculated_columns, {1, 2})
            self.assertEqual(model.quantities_to_remove(0), [0, 1, 2])
            model.remove_quantity(0)
            QTest.qWait(10)
            self.assertEqual(model.columnCount(), 0)
            window.graph_tab.sync_columns()
            self.assertEqual(len(series.points.data), 0)
            window.modeling_tab.calculate()
            self.assertEqual(engine.items, [])
            self.assertEqual(window.calculations_tab.history.rowCount(), 0)
            model.add_quantity()
            self.assertTrue(model.setData(model.index(2, 0), "7"))
        finally:
            window._discard_on_close = True
            window.close()

    def test_axis_removal_updates_modeling_without_qt_callback_exception(self):
        window = MainWindow()
        try:
            model = window.data_tab.model
            model.rows = [[str(value), str(2 * value + 1)] for value in range(4)]
            window.graph_tab.refresh_plot()
            modeling = window.modeling_tab
            modeling.model_choice.setCurrentIndex(modeling.model_choice.findData("affine"))
            modeling.calculate()
            self.assertEqual(modeling.fits_list.count(), 1)
            with patch("sys.excepthook") as exception_hook:
                model.remove_quantity(0)
                QTest.qWait(10)
                window.graph_tab.sync_columns()
                QTest.qWait(10)
            exception_hook.assert_not_called()
            self.assertEqual(modeling.fits_list.count(), 0)
            self.assertEqual(window.graph_tab.series[0].fits, [])
            self.assertEqual(model.names, ["y"])
        finally:
            window._discard_on_close = True
            window.close()

    def test_confirmation_cancel_and_delete_calculated_column(self):
        window = MainWindow()
        try:
            model = window.data_tab.model
            engine = window.calculations_tab.engine
            engine.add("sum", "", expression="x+y")
            with patch("physalix.ui.data_tab.QMessageBox.question", return_value=QMessageBox.StandardButton.No):
                window.data_tab.table.delete_quantity(0)
            self.assertEqual(model.names, ["x", "y", "sum"])
            with patch("physalix.ui.data_tab.QMessageBox.question", return_value=QMessageBox.StandardButton.Yes):
                window.data_tab.table.delete_quantity(2)
            QTest.qWait(10)
            self.assertEqual(model.names, ["x", "y"])
            self.assertEqual(engine.items, [])
            self.assertFalse(model.remove_quantity(-1))
        finally:
            window._discard_on_close = True
            window.close()

    def test_header_menu_targets_clicked_column(self):
        window = MainWindow()
        try:
            window.show()
            self.app.processEvents()
            table = window.data_tab.table
            header = table.horizontalHeader()
            position = QPoint(header.sectionViewportPosition(1) + 10, 10)
            labels = []
            def choose_delete():
                menu = self.app.activePopupWidget()
                labels.append(menu.actions()[0].text())
                menu.actions()[0].trigger()
                menu.close()
            with patch(
                    "physalix.ui.data_tab.QMessageBox.question", return_value=QMessageBox.StandardButton.Yes):
                QTimer.singleShot(0, choose_delete)
                header.customContextMenuRequested.emit(position)
            self.assertEqual(labels, ["Supprimer la grandeur…"])
            self.assertEqual(window.data_tab.model.names, ["x"])
            QTest.qWait(10)
        finally:
            window._discard_on_close = True
            window.close()

    def test_video_keeps_writing_only_surviving_columns(self):
        model = MeasurementsModel()
        session = TrackingSession(model)
        session.set_origin(QPointF(0, 0))
        session.calibrate(QPointF(0, 0), QPointF(10, 0), 10, "cm")
        session.record(0, QPointF(2, -3), 0)
        model.remove_quantity(0)
        model.add_quantity()
        model.setData(model.index(2, 2), "99")
        session.record(1, QPointF(4, -5), 1)
        self.assertEqual(session.columns, (None, 0, 1))
        self.assertEqual(model.rows[:2], [["3", "0", "99"], ["5", "1", ""]])


if __name__ == "__main__":
    unittest.main()
