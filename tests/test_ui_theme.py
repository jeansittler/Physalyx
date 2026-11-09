"""Accès aux outils lors du redimensionnement de l'interface thémée."""
import os
import sys
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import QSize, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import (
    QApplication, QBoxLayout, QFrame, QLabel, QPushButton, QScrollArea, QSizePolicy, QTabBar,
)
from physalix.ui.components import ResponsiveCards
from physalix.ui.main_window import MainWindow
from physalix.ui.project_state import snapshot
from physalix.ui.theme import LIGHT, apply_theme, stylesheet


class ThemeLayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        apply_theme(cls.app)

    def setUp(self):
        self.window = MainWindow()
        self.window.show()
        self.window.show_module(0)

    def tearDown(self):
        self.window._discard_on_close = True
        self.window.close()
        self.app.processEvents()

    def test_tools_remain_reachable_in_small_window(self):
        self.window.resize(640, 420)
        for tab, button in ((self.window.video_tab, self.window.video_tab.next),
                            (self.window.graph_tab, self.window.graph_tab.series[0].remove_button),
                            (self.window.modeling_tab, self.window.modeling_tab.fit_button),
                            (self.window.calculations_tab, self.window.calculations_tab.formula_button),
                            (self.window.statistics_tab, self.window.statistics_tab.copy_button)):
            with self.subTest(tab=type(tab).__name__):
                self.window.tabs.setCurrentWidget(tab)
                QTest.qWait(20)
                scroll = tab.findChild(QScrollArea)
                ancestor = button.parentWidget()
                while ancestor is not None and ancestor is not tab:
                    if isinstance(ancestor, QScrollArea):
                        ancestor.ensureWidgetVisible(button)
                    ancestor = ancestor.parentWidget()
                scroll.ensureWidgetVisible(button)
                self.app.processEvents()
                center = button.mapTo(scroll.viewport(), button.rect().center())
                self.assertTrue(scroll.viewport().rect().contains(center))
                self.assertGreaterEqual(button.height(), 30)

    def test_corrected_modeling_and_calculations_panels_do_not_clip_actions(self):
        callback_errors = []
        previous_hook = sys.excepthook
        self.addCleanup(setattr, sys, "excepthook", previous_hook)
        sys.excepthook = lambda *args: callback_errors.append(args)
        for width, height in ((1366, 768), (1600, 900), (1100, 700)):
            with self.subTest(size=(width, height)):
                self.window.resize(width, height)
                self.window.show_module(self.window.tabs.indexOf(self.window.modeling_tab))
                self.app.processEvents()
                modeling = self.window.modeling_tab.currentWidget()
                self.assertIn("Modélisations de la série sélectionnée", [
                    label.text() for label in modeling.fits_panel.findChildren(QLabel)])
                for button in (modeling.new_fit_button, modeling.remove_button):
                    bottom = button.mapTo(modeling.fits_panel, button.rect().bottomLeft())
                    self.assertTrue(modeling.fits_panel.rect().contains(bottom))
                self.assertIs(modeling.new_fit_button.parentWidget(),
                              modeling.remove_button.parentWidget())
                self.assertFalse(modeling.new_fit_button.geometry().intersects(
                    modeling.remove_button.geometry()))

                calculations = self.window.calculations_tab
                self.window.show_module(self.window.tabs.indexOf(calculations))
                targets = (1, 2, 3, 8) if not calculations.engine.items else (8,)
                for target in targets:
                    for index in range(len(calculations.engine.items), target):
                        calculations.engine.add(f"calcul_{index}", "", expression=str(index + 1))
                    self.app.processEvents()
                    self.assertEqual(calculations.history.rowCount(), target)
                    button_bottom = calculations.edit_formula_button.mapTo(
                        calculations, calculations.edit_formula_button.rect().bottomLeft()).y()
                    table_top = calculations.history.mapTo(
                        calculations, calculations.history.rect().topLeft()).y()
                    self.assertLess(button_bottom, table_top)
                last = calculations.history.item(7, 0)
                calculations.history.scrollToItem(last)
                self.app.processEvents()
                self.assertTrue(calculations.history.viewport().rect().intersects(
                    calculations.history.visualItemRect(last)))
        sys.excepthook = previous_hook
        self.assertEqual(callback_errors, [])

    def test_design_tokens_and_interaction_states_are_centralized(self):
        self.assertNotEqual(LIGHT.background, LIGHT.surface)
        self.assertNotEqual(LIGHT.border, LIGHT.border_strong)
        self.assertGreaterEqual(LIGHT.control_height, 32)
        self.assertGreaterEqual(LIGHT.wide_layout, 1100)
        self.assertNotEqual(LIGHT.navy, LIGHT.primary)
        self.assertNotEqual(LIGHT.table_header, LIGHT.table_metadata)
        qss = stylesheet()
        for state in (":hover", ":focus", ":pressed", ":selected", ":disabled"):
            self.assertIn(state, qss)
        for role in ('role="primary"', 'role="danger"', 'role="card"'):
            self.assertIn(role, qss)
        self.assertIn(f"QScrollBar:vertical {{ background: {LIGHT.border}; width: 14px", qss)
        self.assertIn(f"QScrollBar::handle {{ background: {LIGHT.muted}", qss)

    def test_reference_views_use_cards_and_clear_action_hierarchy(self):
        data = self.window.data_tab
        modeling = self.window.modeling_tab
        self.assertTrue(data.table.alternatingRowColors())
        data_roles = {w.property("role") for w in data.findChildren(QFrame)}
        self.assertTrue({"help", "toolbar"}.issubset(data_roles))
        self.assertEqual(modeling.fit_button.property("role"), "primary")
        self.assertEqual(modeling.remove_button.property("role"), "quiet")
        self.assertEqual(modeling.result_panel.property("role"), "card")
        responsive = modeling.findChild(ResponsiveCards)
        scroll = modeling.findChild(QScrollArea)
        for size, direction in (((1280, 800), QBoxLayout.Direction.LeftToRight),
                                ((1920, 1080), QBoxLayout.Direction.LeftToRight),
                                ((900, 700), QBoxLayout.Direction.TopToBottom)):
            self.window.resize(*size)
            self.window.tabs.setCurrentWidget(modeling)
            QTest.qWait(20)
            self.assertEqual(responsive.cards.direction(), direction)
            self.assertEqual(scroll.horizontalScrollBar().maximum(), 0)

    def test_focus_and_modeling_disabled_states_remain_explicit(self):
        data = self.window.data_tab
        modeling = self.window.modeling_tab
        self.window.tabs.setCurrentWidget(data)
        data.table.setCurrentIndex(data.model.index(data.model.first_data_row, 0))
        data.formula_bar.setFocus()
        self.app.processEvents()
        self.assertTrue(data.formula_bar.hasFocus())
        self.assertGreater(data.table.verticalScrollBar().maximum(), 0)
        self.assertFalse(modeling.minimum.isEnabled())
        self.assertFalse(modeling.range_fields.property("active"))
        modeling.range_check.setChecked(True)
        self.assertTrue(modeling.minimum.isEnabled())
        self.assertTrue(modeling.range_fields.property("active"))
        model = data.model
        metadata = model.data(model.index(0, 0), Qt.ItemDataRole.BackgroundRole)
        model.calculated_columns.add(1)
        calculated = model.data(model.index(2, 1), Qt.ItemDataRole.BackgroundRole)
        self.assertEqual(metadata.color().name(), LIGHT.table_metadata.lower())
        self.assertEqual(calculated.color().name(), LIGHT.primary_soft.lower())

    def test_navigation_and_plot_after_resize(self):
        for size in ((1366, 700), (1920, 1000), (900, 620), (1366, 700)):
            self.window.resize(*size)
            for index in range(self.window.tabs.count()):
                self.window.tabs.setCurrentIndex(index)
                self.app.processEvents()
                self.assertEqual(self.window.tabs.currentIndex(), index)
                self.assertFalse(self.window.navigation_buttons[index].icon().isNull())
            self.window.tabs.setCurrentWidget(self.window.graph_tab)
            QTest.qWait(20)
            self.assertGreaterEqual(self.window.graph_tab.plot.height(), 220)

    def test_main_navigation_labels_density_and_three_modes(self):
        tabs = self.window.tabs
        navigation = self.window.navigation
        buttons = self.window.navigation_buttons
        labels = ["Données", "Graphique", "Modélisation", "Pointage", "Calculs",
                  "Statistiques", "Numérisation", "Acquisition", "Spectrophotométrie", "Analyse d'images"]
        tooltips = ["Données", "Graphique", "Modélisation", "Pointage vidéo", "Calculs",
                    "Statistiques", "Numérisation", "Acquisition", "Spectrophotométrie", "Analyse d'images"]
        self.window.resize(self.window._navigation_required_width("normal") + 100, 800)
        QTest.qWait(20)
        self.assertEqual([button.text() for button in buttons], labels)
        self.assertEqual([button.toolTip() for button in buttons], tooltips)
        self.assertTrue(all(button.iconSize() == QSize(18, 18) for button in buttons))
        self.assertFalse(tabs.tabBar().isVisible())

        for width in (1280, 1366, 1600, 1920):
            with self.subTest(width=width):
                self.window._set_navigation_mode("normal")
                self.window.resize(width, 800)
                QTest.qWait(20)
                self.assertEqual(navigation.height(), 44)
                available = navigation.width()
                expected_mode = (
                    "normal"
                    if available >= self.window._navigation_required_width("normal")
                    else "compact"
                    if available >= self.window._navigation_required_width("compact")
                    else "icon"
                )
                self.assertEqual(navigation.property("navigationMode"), expected_mode)
                self.assertTrue(all(button.isVisible() for button in buttons))

        self.window.resize(900, 700)
        QTest.qWait(20)
        expected = ("compact" if 900 >= self.window._navigation_required_width("compact")
                    else "icon")
        self.assertEqual(navigation.property("navigationMode"), expected)
        if QApplication.platformName() == "windows":
            self.assertEqual(expected, "compact")
        self.assertTrue(all(button.isVisible() for button in buttons))

        self.window.resize(640, 420)
        QTest.qWait(20)
        self.assertEqual(navigation.property("navigationMode"), "icon")
        self.assertTrue(all(
            button.toolButtonStyle() == Qt.ToolButtonStyle.ToolButtonIconOnly for button in buttons))
        self.assertEqual([button.toolTip() for button in buttons], tooltips)
        self.assertTrue(all(not button.icon().isNull() for button in buttons))
        self.assertTrue(all(button.isVisible() for button in buttons))
        widths = [button.width() for button in buttons]
        self.assertEqual(len(set(widths)), 1)
        self.assertLessEqual(buttons[-1].geometry().right(), navigation.width())
        self.assertEqual(self.window.brand_logo.size().toTuple(), (70, 24))
        for index, button in enumerate(buttons):
            QTest.mouseClick(button, Qt.MouseButton.LeftButton)
            self.app.processEvents()
            self.assertEqual(tabs.currentIndex(), index)

    def test_navigation_density_is_stable_and_internal_tabs_are_unchanged(self):
        tabs = self.window.tabs
        graph_tabs = self.window.graph_tab.area.findChild(QTabBar, "graphTabs")
        self.assertIsNotNone(graph_tabs)
        internal_height = graph_tabs.sizeHint().height()
        normal_width = self.window._navigation_required_width("normal")
        compact_width = self.window._navigation_required_width("compact")
        states = []
        for width in (normal_width + 100, normal_width - 10, compact_width - 10,
                      compact_width + 10, compact_width + 30, normal_width + 10,
                      normal_width + 30):
            self.window.resize(width, 700)
            QTest.qWait(20)
            states.append(self.window.navigation.property("navigationMode"))
            self.assertEqual(graph_tabs.sizeHint().height(), internal_height)
        self.assertEqual(states, ["normal", "compact", "icon", "icon", "compact",
                                  "compact", "normal"])

    def test_navigation_density_is_recomputed_after_project_replacement(self):
        # Reproduire la boucle d'événements ouverte par la confirmation de
        # sauvegarde : elle laisse la fenêtre de staging calculer sa géométrie cachée.
        self.window.confirm_save = lambda: (self.app.processEvents() or True)
        wide = self.window._navigation_required_width("normal") + 100
        for width in (wide, 640, wide):
            with self.subTest(width=width):
                self.window.showNormal()
                self.window.resize(width, 700)
                self.app.processEvents()
                expected = self.window.navigation.property("navigationMode")
                self.window.new_project()
                self.app.processEvents()
                self.assertEqual(
                    self.window.navigation.property("navigationMode"), expected)

        state = snapshot(self.window)
        expected = self.window.navigation.property("navigationMode")
        self.assertTrue(self.window.replace_project(state))
        self.app.processEvents()
        self.assertEqual(self.window.navigation.property("navigationMode"), expected)

        self.window.showMaximized()
        self.app.processEvents()
        expected = self.window.navigation.property("navigationMode")
        self.window.new_project()
        self.app.processEvents()
        self.assertEqual(self.window.navigation.property("navigationMode"), expected)

    def test_brand_cartouche_is_centered_on_continuous_navigation_background(self):
        for mode, width, cartouche_size, logo_size in (
                ("normal", self.window._navigation_required_width("normal") + 100, (112, 34), (100, 28)),
                ("compact", self.window._navigation_required_width("normal") - 10, (96, 34), (86, 26)),
                ("icon", 640, (80, 34), (70, 24))):
            with self.subTest(mode=mode):
                self.window.resize(width, 700)
                QTest.qWait(20)
                self.assertEqual(self.window.navigation.property("navigationMode"), mode)
                navigation = self.window.navigation
                cartouche = self.window.brand_cartouche
                logo = self.window.brand_logo
                self.assertEqual(navigation.height(), 44)
                self.assertEqual(cartouche.size().toTuple(), cartouche_size)
                self.assertEqual(logo.size().toTuple(), logo_size)
                self.assertEqual(cartouche.x(), 8)
                self.assertEqual(cartouche.y(), 5)
                self.assertEqual(cartouche.y() + cartouche.height() + 5, navigation.height())
                self.assertEqual(logo.y() * 2 + logo.height(), cartouche.height())
                self.assertIs(cartouche.parentWidget(), navigation)
                for button in self.window.navigation_buttons:
                    self.assertIs(button.parentWidget(), navigation)
                    self.assertEqual((button.y(), button.height()), (5, 34))
                rendered = navigation.grab().toImage()
                # Logical samples converted to device pixels for HiDPI displays.
                ratio = rendered.devicePixelRatio()
                for x, y in ((0, 0), (0, 22), (navigation.width() - 1, 22)):
                    self.assertEqual(rendered.pixelColor(int(x * ratio), int(y * ratio)).name(), LIGHT.navy.lower())

    def test_main_navigation_mouse_and_keyboard_focus_keep_geometry(self):
        self.window.resize(self.window._navigation_required_width("normal") + 100, 700)
        QTest.qWait(20)
        buttons = self.window.navigation_buttons
        self.assertEqual(buttons[0].focusPolicy(), Qt.FocusPolicy.TabFocus)
        before = [button.geometry() for button in buttons]

        buttons[1].clearFocus()
        QTest.mouseClick(buttons[1], Qt.MouseButton.LeftButton)
        self.app.processEvents()
        self.assertEqual(self.window.tabs.currentIndex(), 1)
        self.assertFalse(buttons[1].hasFocus())
        self.assertTrue(buttons[1].isChecked())
        self.assertEqual([button.geometry() for button in buttons], before)

        self.assertEqual(buttons[1].focusPolicy(), Qt.FocusPolicy.TabFocus)
        buttons[1].setFocus(Qt.FocusReason.TabFocusReason)
        self.app.processEvents()
        self.assertTrue(buttons[1].hasFocus())
        QTest.keyClick(buttons[1], Qt.Key.Key_Right)
        self.app.processEvents()
        self.assertEqual(self.window.tabs.currentIndex(), 2)
        self.assertTrue(buttons[2].hasFocus())
        self.assertTrue(buttons[2].isChecked())
        self.assertEqual([button.geometry() for button in buttons], before)

        self.window.tabs.setCurrentIndex(4)
        self.app.processEvents()
        self.assertTrue(buttons[4].isChecked())
        self.assertEqual(sum(button.isChecked() for button in buttons), 1)

        self.window.graph_tab.modeling_requested.emit()
        self.app.processEvents()
        self.assertIs(self.window.tabs.currentWidget(), self.window.modeling_tab)
        self.assertTrue(buttons[2].isChecked())
        self.window.modeling_tab.graph_requested.emit()
        self.app.processEvents()
        self.assertIs(self.window.tabs.currentWidget(), self.window.graph_tab)
        self.assertTrue(buttons[1].isChecked())

    def test_graph_workspace_prioritizes_plot_height(self):
        workspace = self.window.graph_tab
        self.window.tabs.setCurrentWidget(workspace)
        management = workspace.layout().itemAt(0).widget()
        for width, height, minimum_plot_height in (
                (1366, 768, 350), (1600, 900, 480), (1920, 1080, 650)):
            with self.subTest(size=(width, height)):
                self.window.resize(width, height)
                QTest.qWait(20)
                graph_tabs = workspace.area.findChild(QTabBar, "graphTabs")
                self.assertIsNotNone(graph_tabs)
                self.assertLessEqual(management.height(), 42)
                self.assertLessEqual(graph_tabs.height(), 44)
                self.assertGreaterEqual(workspace.plot.height(), minimum_plot_height)
                self.assertEqual(workspace.plot.sizePolicy().verticalPolicy(),
                                 QSizePolicy.Policy.Expanding)
                scroll = workspace.active_graph.findChild(QScrollArea)
                self.assertEqual(scroll.verticalScrollBar().maximum(), 0)

    def test_video_workspace_prioritizes_canvas_height(self):
        video = self.window.video_tab
        self.window.tabs.setCurrentWidget(video)
        heights = []
        for width, height, minimum_canvas_height in (
                (1280, 720, 325), (1366, 768, 370),
                (1600, 900, 500), (1920, 1080, 680)):
            with self.subTest(size=(width, height)):
                self.window.resize(width, height)
                QTest.qWait(20)
                scroll = video.findChild(QScrollArea)
                heights.append(video.screen.height())
                self.assertEqual(scroll.verticalScrollBar().maximum(), 0)
                self.assertGreaterEqual(video.screen.height(), minimum_canvas_height)
                self.assertEqual(video.screen.sizePolicy().verticalPolicy(),
                                 QSizePolicy.Policy.Expanding)
        self.assertGreater(heights[-1], heights[0] + 350)

    def test_hidden_graph_settings_leave_only_compact_restore_control(self):
        graph = self.window.graph_tab.active_graph
        self.window.tabs.setCurrentWidget(self.window.graph_tab)
        self.window.resize(1366, 768)
        QTest.qWait(20)
        visible_height = graph.plot.height()
        graph.settings_button.setChecked(False)
        QTest.qWait(20)
        self.assertFalse(graph.series_label.isVisible())
        self.assertFalse(graph.series_choice.isVisible())
        self.assertFalse(graph.series_stack.isVisible())
        self.assertTrue(graph.settings_button.isVisible())
        self.assertGreater(graph.plot.height(), visible_height)

    def test_all_tabs_fit_reference_resolutions(self):
        for width, height in ((1280, 800), (1920, 1080)):
            self.window.resize(width, height)
            for index in range(self.window.tabs.count()):
                with self.subTest(size=(width, height), tab=self.window.tabs.tabText(index)):
                    page = self.window.tabs.widget(index)
                    self.window.tabs.setCurrentIndex(index)
                    QTest.qWait(20)
                    for scroll in page.findChildren(QScrollArea):
                        self.assertEqual(scroll.horizontalScrollBar().maximum(), 0)
            self.assertEqual(self.window.calculations_tab.tools.cards.direction(),
                             QBoxLayout.Direction.LeftToRight)
            self.assertEqual(self.window.video_tab.workflow_cards.cards.direction(),
                             QBoxLayout.Direction.LeftToRight)
            self.assertLessEqual(self.window.graph_tab.add_button.width(), LIGHT.action_compact)
            self.assertLessEqual(self.window.graph_tab.arrangement.width(), LIGHT.field_compact)
            self.assertLessEqual(self.window.graph_tab.rename_button.width(), LIGHT.action_compact)
            self.assertLessEqual(self.window.video_tab.open_button.width(), LIGHT.action_compact)
            self.assertLessEqual(self.window.video_tab.axes_choice.width(), LIGHT.field_compact)
            if width == 1280:
                self.assertGreaterEqual(self.window.graph_tab.plot.height(), 320)
                self.assertGreaterEqual(self.window.video_tab.screen.height(), 320)
                self.assertLessEqual(self.window.video_tab.screen.mapTo(
                    self.window.video_tab, self.window.video_tab.screen.rect().topLeft()).y(), 270)
                modeling = self.window.modeling_tab.currentWidget()
                self.assertLessEqual(modeling.result_panel.y(), 370)
                self.assertLessEqual(self.window.calculations_tab.history.mapTo(
                    self.window.calculations_tab,
                    self.window.calculations_tab.history.rect().topLeft()).y(), 580)
                self.assertGreaterEqual(self.window.statistics_tab.table.height(), 320)
            else:
                self.assertGreaterEqual(self.window.graph_tab.plot.height(), 600)
                self.assertGreaterEqual(self.window.video_tab.screen.height(), 600)
                self.assertGreaterEqual(self.window.statistics_tab.table.height(), 600)

        self.window.resize(900, 700)
        for index in range(self.window.tabs.count()):
            page = self.window.tabs.widget(index)
            self.window.tabs.setCurrentIndex(index)
            QTest.qWait(20)
            for scroll in page.findChildren(QScrollArea):
                self.assertEqual(scroll.horizontalScrollBar().maximum(), 0)
        self.assertEqual(self.window.calculations_tab.tools.cards.direction(),
                         QBoxLayout.Direction.TopToBottom)
        self.assertEqual(self.window.video_tab.workflow_cards.cards.direction(),
                         QBoxLayout.Direction.TopToBottom)

    def test_data_help_preserves_table_access(self):
        self.window.resize(900, 620)
        tab = self.window.data_tab
        texts = [widget.text() for widget in tab.findChildren(QLabel)]
        self.assertIn("Données / Tableur", texts)
        self.assertNotIn("Une grandeur par colonne · une mesure par ligne", texts)
        toggle = next(b for b in tab.findChildren(QPushButton) if b.isCheckable())
        toggle.click()
        QTest.qWait(20)
        self.assertTrue(toggle.isChecked())
        self.assertGreater(tab.table.viewport().height(), 80)
        toggle.click()
        QTest.qWait(20)
        self.assertGreater(tab.table.viewport().height(), 200)


if __name__ == "__main__":
    unittest.main()
