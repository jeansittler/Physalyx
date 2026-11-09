"""Fenêtre principale et navigation de Physalyx."""

from PySide6.QtCore import Qt, QSize, QTimer
from PySide6.QtGui import QFont, QFontMetrics
from PySide6.QtWidgets import (
    QButtonGroup, QFrame, QHBoxLayout, QMainWindow, QMenu, QStackedWidget, QTabWidget,
    QToolButton, QVBoxLayout, QWidget,
)
from physalix.ui.components import role
from physalix.ui.branding import BrandLogo, application_icon
from physalix.ui.icons import icon
from physalix.ui.home_page import HomePage

from physalix.ui.data_tab import DataTab
from physalix.ui.graph_tab import GraphTab
from physalix.ui.modeling_tab import ModelingTab
from physalix.ui.video_tab import VideoTab
from physalix.ui.calculations_tab import CalculationsTab
from physalix.ui.statistics_tab import StatisticsTab
from physalix.ui.graph_digitizer_tab import GraphDigitizerTab
from physalix.ui.acquisition_tab import AcquisitionTab
from physalix.ui.spectrophotometry_tab import SpectrophotometryTab
from physalix.ui.image_analysis_tab import ImageAnalysisTab
from physalix.ui.graph_workspace import GraphWorkspace, ModelingWorkspace
from physalix.ui.project_files import ProjectFiles
from physalix.ui.updates import UpdateController
from physalix import __development__, __version__


NAVIGATION_LABELS = (
    "Données", "Graphique", "Modélisation", "Pointage", "Calculs",
    "Statistiques", "Numérisation", "Acquisition", "Spectrophotométrie", "Analyse d'images",
)
NAVIGATION_TOOLTIPS = (
    "Données", "Graphique", "Modélisation", "Pointage vidéo", "Calculs",
    "Statistiques", "Numérisation", "Acquisition", "Spectrophotométrie", "Analyse d'images",
)
NAVIGATION_LOGO_SIZES = {
    "normal": (100, 28), "compact": (86, 26), "icon": (70, 24),
}
NAVIGATION_CARTOUCHE_SIZES = {
    "normal": (112, 34), "compact": (96, 34), "icon": (80, 34),
}
NAVIGATION_GAP = 8


class MainWindow(QMainWindow, ProjectFiles):
    """Accueillir les espaces de travail de l'application."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(f"Physalyx — {__version__}" if __development__ else "Physalyx")
        self.setWindowIcon(application_icon())
        self.resize(1280, 760)
        self.setMinimumSize(640, 420)

        self.tabs = QTabWidget()
        self.tabs.setObjectName("mainPages")
        self.tabs.setDocumentMode(True)
        self._navigation_mode = None
        self.data_tab = DataTab()
        self.graph_tab = GraphWorkspace(self.data_tab.model)
        self.tabs.addTab(self.data_tab, "Données")
        self.tabs.addTab(self.graph_tab, "Graphique")
        self.modeling_tab = ModelingWorkspace(self.graph_tab)
        self.tabs.addTab(self.modeling_tab, "Modélisation")
        self.graph_tab.modeling_requested.connect(lambda: self.tabs.setCurrentWidget(self.modeling_tab))
        self.modeling_tab.graph_requested.connect(lambda: self.tabs.setCurrentWidget(self.graph_tab))
        self.video_tab = VideoTab(self.data_tab.model)
        video_index = self.tabs.addTab(self.video_tab, "Pointage")
        self.tabs.setTabToolTip(video_index, "Pointage vidéo")
        self.calculations_tab = CalculationsTab(self.data_tab.model)
        self.data_tab.table.edit_calculation_requested.connect(
            self.calculations_tab.edit_calculation_column)
        self.tabs.addTab(self.calculations_tab, "Calculs")
        self.statistics_tab = StatisticsTab(self.data_tab)
        self.tabs.addTab(self.statistics_tab, "Statistiques")
        self.digitizer_tab = GraphDigitizerTab(self.data_tab, self.graph_tab)
        self.tabs.addTab(self.digitizer_tab, "Numérisation")
        self.acquisition_tab = AcquisitionTab(
            data_tab=self.data_tab,
            graph_workspace=self.graph_tab,
            show_graph=lambda: self.tabs.setCurrentWidget(self.graph_tab),
        )
        self.tabs.addTab(self.acquisition_tab, "Acquisition")
        self.spectrophotometry_tab = SpectrophotometryTab(
            data_tab=self.data_tab,
            graph_workspace=self.graph_tab,
            show_graph=lambda: self.tabs.setCurrentWidget(self.graph_tab),
        )
        self.tabs.addTab(self.spectrophotometry_tab, "Spectrophotométrie")
        self.image_analysis_tab = ImageAnalysisTab(
            data_tab=self.data_tab,
            graph_workspace=self.graph_tab,
            show_graph=lambda: self.tabs.setCurrentWidget(self.graph_tab),
        )
        self.tabs.addTab(self.image_analysis_tab, "Analyse d'images")
        for index, tooltip in enumerate(NAVIGATION_TOOLTIPS):
            self.tabs.setTabToolTip(index, tooltip)
            self.tabs.setTabWhatsThis(index, tooltip)
        self.tabs.tabBar().hide()

        self.home_page = HomePage()
        self.workspace_stack = QStackedWidget()
        self.workspace_stack.addWidget(self.home_page)
        self.workspace_stack.addWidget(self.tabs)
        self.home_page.module_requested.connect(self.show_module)
        self.home_page.new_project_requested.connect(self.new_project)
        self.home_page.open_project_requested.connect(self.open_project)

        self.navigation = role(QWidget(), "mainNavigation")
        self.navigation.setObjectName("mainNavigation")
        self.navigation.setFixedHeight(44)
        self.navigation.setProperty("navigationMode", "normal")
        self.navigation_layout = QHBoxLayout(self.navigation)
        self.navigation_layout.setContentsMargins(8, 5, 8, 5)
        self.navigation_layout.setSpacing(0)
        self.brand_cartouche = role(QFrame(), "brandCartouche")
        self.brand_cartouche.setFixedSize(*NAVIGATION_CARTOUCHE_SIZES["normal"])
        cartouche_layout = QVBoxLayout(self.brand_cartouche)
        cartouche_layout.setContentsMargins(0, 0, 0, 0)
        self.brand_logo = BrandLogo()
        self.brand_logo.setDisplaySize(*NAVIGATION_LOGO_SIZES["normal"])
        cartouche_layout.addWidget(self.brand_logo, 0, Qt.AlignmentFlag.AlignCenter)
        self.navigation_layout.addWidget(self.brand_cartouche)
        self.navigation_layout.addSpacing(NAVIGATION_GAP)

        self.home_button = role(QToolButton(), "mainNavigationButton")
        self.home_button.setObjectName("homeNavigationButton")
        self.home_button.setIcon(icon("home", navigation=True))
        self.home_button.setIconSize(QSize(18, 18))
        self.home_button.setFixedSize(34, 34)
        self.home_button.setToolTip("Accueil")
        self.home_button.setAccessibleName("Accueil")
        self.home_button.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        self.home_button.clicked.connect(self.show_home)
        self.navigation_layout.addWidget(self.home_button)
        self.navigation_layout.addSpacing(4)

        self.navigation_group = QButtonGroup(self.navigation)
        self.navigation_group.setExclusive(True)
        self.navigation_buttons = []
        for index, (label, tooltip) in enumerate(zip(NAVIGATION_LABELS, NAVIGATION_TOOLTIPS)):
            button = role(QToolButton(), "mainNavigationButton")
            button.setObjectName(f"mainNavigationButton{index}")
            button.setText(label)
            button.setToolTip(tooltip)
            button.setAccessibleName(tooltip)
            button.setCheckable(True)
            button.setFocusPolicy(Qt.FocusPolicy.TabFocus)
            button.setIconSize(QSize(18, 18))
            button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
            button.setFixedHeight(34)
            button.clicked.connect(lambda checked=False, chosen=index: self.show_module(chosen))
            self.navigation_group.addButton(button, index)
            self.navigation_buttons.append(button)
            self.navigation_layout.addWidget(button)
        self.navigation_layout.addStretch(1)

        self.main_container = QWidget()
        main_layout = QVBoxLayout(self.main_container)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        main_layout.addWidget(self.navigation)
        main_layout.addWidget(self.workspace_stack, 1)
        self._set_navigation_mode("normal")
        self.tabs.currentChanged.connect(self.update_navigation)
        self.update_navigation()
        self.setCentralWidget(self.main_container)

        self.statusBar().showMessage(
            f"Version de développement {__version__} · mises à jour désactivées"
            if __development__ else "Prêt"
        )
        self.setup_files()
        self.updater = UpdateController(self)
        self._setup_diagnostic_menu()
        # Un vrai timer enfant est annulé avec la fenêtre. Un singleShot sans
        # contexte pouvait rappeler la méthode après destruction du widget central.
        self._navigation_density_timer = QTimer(self)
        self._navigation_density_timer.setSingleShot(True)
        self._navigation_density_timer.timeout.connect(self._update_navigation_density)
        self._navigation_density_timer.start(0)

    def show_home(self):
        """Afficher l'accueil sans modifier le projet ni l'onglet actif."""
        self.workspace_stack.setCurrentWidget(self.home_page)
        self.update_navigation()

    def show_module(self, index):
        """Ouvrir directement un module depuis l'accueil ou la navigation."""
        if 0 <= index < self.tabs.count():
            self.tabs.setCurrentIndex(index)
            self.workspace_stack.setCurrentWidget(self.tabs)
            self.update_navigation()

    def _setup_diagnostic_menu(self):
        help_menu = self.updater.about_action.parent()
        self.diagnostic_tools_menu = QMenu("Outils de diagnostic", self)
        self.kinetic_diagnostic_export_action = (
            self.diagnostic_tools_menu.addAction(
                "Exporter le diagnostic cinétique…",
                lambda: self.spectrophotometry_tab.export_kinetic_diagnostic(),
            )
        )
        help_menu.insertMenu(self.updater.about_action, self.diagnostic_tools_menu)
        self._bind_spectrophotometry_diagnostic_action()

    def _bind_spectrophotometry_diagnostic_action(self):
        self.spectrophotometry_tab.diagnostic_export_availability_changed.connect(
            self.kinetic_diagnostic_export_action.setEnabled
        )
        self.kinetic_diagnostic_export_action.setEnabled(
            self.spectrophotometry_tab.kinetic_diagnostic_export_available()
        )

    def update_navigation(self, *args):
        current = self.tabs.currentIndex()
        on_home = self.workspace_stack.currentWidget() is self.home_page
        self.home_button.setProperty("homeActive", on_home)
        self.home_button.style().unpolish(self.home_button)
        self.home_button.style().polish(self.home_button)
        self.navigation_group.setExclusive(False)
        try:
            for index, name in enumerate(("data", "graph", "model", "video", "calculations", "statistics", "digitizer", "acquisition", "spectrophotometry", "image_analysis")):
                active = not on_home and index == current
                self.navigation_buttons[index].setChecked(active)
                self.navigation_buttons[index].setIcon(icon(name, active, navigation=True))
        finally:
            self.navigation_group.setExclusive(True)
        for index, button in enumerate(self.navigation_buttons):
            button.setFocusPolicy(
                Qt.FocusPolicy.TabFocus if index == current else Qt.FocusPolicy.NoFocus)

    def _navigation_required_width(self, mode):
        """Estimer la largeur naturelle avec les métriques Qt courantes."""
        font = self.navigation_buttons[0].font()
        font.setWeight(QFont.Weight.DemiBold)
        metrics = QFontMetrics(font)
        horizontal_padding = 10 if mode == "normal" else 4
        tab_chrome = 2 * horizontal_padding + 16
        if mode == "icon":
            tabs_width = len(self.navigation_buttons) * (18 + 4 + tab_chrome)
        else:
            icon_and_gap = 18 + 4
            tabs_width = sum(
                metrics.horizontalAdvance(label) + icon_and_gap + tab_chrome
                for label in NAVIGATION_LABELS
            )
        return 16 + NAVIGATION_CARTOUCHE_SIZES[mode][0] + NAVIGATION_GAP + 38 + tabs_width

    def _set_navigation_mode(self, mode):
        if mode == self._navigation_mode:
            return
        self._navigation_mode = mode
        self.navigation.setProperty("navigationMode", mode)
        self.brand_cartouche.setFixedSize(*NAVIGATION_CARTOUCHE_SIZES[mode])
        self.brand_logo.setDisplaySize(*NAVIGATION_LOGO_SIZES[mode])
        self.brand_logo.setSymbolOnly(mode != "normal")
        font = self.navigation_buttons[0].font()
        font.setWeight(QFont.Weight.DemiBold)
        metrics = QFontMetrics(font)
        horizontal_padding = 10 if mode == "normal" else 4
        tab_chrome = 2 * horizontal_padding + 16
        for button, label in zip(self.navigation_buttons, NAVIGATION_LABELS):
            if mode == "icon":
                width = 18 + 4 + tab_chrome
                button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
            else:
                width = metrics.horizontalAdvance(label) + 18 + 4 + tab_chrome
                button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
            button.setFixedWidth(width)
        for widget in (self.navigation, *self.navigation_buttons):
            widget.style().unpolish(widget)
            widget.style().polish(widget)
            widget.updateGeometry()

    def _update_navigation_density(self, available_width=None):
        if not hasattr(self, "tabs"):
            return
        available = self.navigation.width() if available_width is None else available_width
        normal_width = self._navigation_required_width("normal")
        compact_width = self._navigation_required_width("compact")
        hysteresis = 24
        if self._navigation_mode == "normal":
            mode = ("normal" if available >= normal_width else
                    "compact" if available >= compact_width else "icon")
        elif self._navigation_mode == "compact":
            if available >= normal_width + hysteresis:
                mode = "normal"
            else:
                mode = "compact" if available >= compact_width else "icon"
        else:
            if available >= normal_width + hysteresis:
                mode = "normal"
            elif available >= compact_width + hysteresis:
                mode = "compact"
            else:
                mode = "icon"
        self._set_navigation_mode(mode)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_navigation_density()

    def closeEvent(self, event):
        if not self.confirm_save():
            event.ignore()
            return
        self.updater.stop()
        self.spectrophotometry_tab.shutdown()
        self.acquisition_tab.shutdown()
        self.video_tab.shutdown()
        super().closeEvent(event)
