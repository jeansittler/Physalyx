"""Lecteur vidéo avec navigation exacte parmi les images décodées."""

from pathlib import Path
from math import hypot

from PySide6.QtCore import QElapsedTimer, QThread, QTimer, Qt, Signal
from PySide6.QtGui import QKeySequence, QPixmap, QShortcut
from PySide6.QtWidgets import (
    QDialog, QFileDialog, QFrame, QHBoxLayout, QLabel, QPushButton,
    QDialogButtonBox, QSizePolicy, QSlider, QVBoxLayout, QWidget,
)

from physalix.video import prepare_video
from physalix.ui.data_tab import MeasurementsModel
from physalix.ui.video_canvas import Magnifier, VideoCanvas
from physalix.ui.video_tracking import CalibrationDialog, TrackingSession
from physalix.ui.automatic_tracking import AutomaticTracker
from physalix.ui.components import (ResponsiveCards, WheelSafeComboBox,
                                    compact_width, label, page_header, panel,
                                    role, workspace_layout)
from physalix.ui.graph_series import PopupComboBox, configure_popup, update_popup_height
from physalix.ui.theme import LIGHT


class VideoLoader(QThread):
    progress = Signal(int)

    def __init__(self, path, parent):
        super().__init__(parent)
        self.path = path
        self.cache = None
        self.error = None

    def run(self):
        try:
            self.cache = prepare_video(self.path, self.isInterruptionRequested, self.progress.emit)
        except Exception as error:
            self.error = str(error)


class VideoTab(QWidget):
    MODE_HINTS = {
        "scale": "Cliquez sur le début de l'étalon, déplacez la flèche puis cliquez sur son extrémité. Direction horizontale par défaut ; choisissez Vertical ou Libre si besoin. Échap pour annuler.",
        "origin": "Cliquez à l'emplacement de x = 0 et y = 0. Échap pour annuler.",
        "track": "Cliquez sur l'objet : le point est enregistré et l'image suivante apparaît. Échap pour arrêter.",
        "select": "Choisissez une marque sur la vidéo ou un point dans la liste. Son image s'affichera pour le corriger.",
        "edit": "Cliquez à la position corrigée. Seul ce point sera modifié. Échap pour annuler la sélection.",
        "auto_select": "Encadrez l’objet à suivre.",
        "auto_ready": "Sélection prête. Lancez le pointage automatique ou redéfinissez l’objet.",
        "auto_running": "Pointage automatique en cours, image par image.",
        "auto_paused": "Pointage automatique arrêté. Corrigez si nécessaire, puis reprenez.",
        "auto_recover": "Objet non identifié avec suffisamment de fiabilité. Cliquez sur sa bonne position ou redéfinissez l’objet.",
        None: "Commencez le pointage ou utilisez « Corriger un point » pour modifier une mesure existante.",
    }
    TRACKING_INFO_RESERVE = (
        "Étalon : 1000000000 mm · Origine définie · 999999 point(s) · "
        "x vers la gauche, y vers le bas"
    )

    def __init__(self, model=None):
        super().__init__()
        self.model = model if model is not None else MeasurementsModel(self)
        self.tracking = TrackingSession(self.model)
        self.mode = None
        self.correction_return = None
        self.cache = None
        self.loader = None
        self.index = 0
        self.playing = False
        self.pixmap = QPixmap()
        self.clock = QElapsedTimer()
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self._tick)
        self.automatic_timer = QTimer(self)
        self.automatic_timer.setSingleShot(True)
        self.automatic_timer.timeout.connect(self._automatic_tick)
        self.automatic_tracker = None
        self.automatic_anchor_pending = False
        layout = workspace_layout(self, 760, 560)
        layout.setContentsMargins(LIGHT.section, LIGHT.related,
                                  LIGHT.section, LIGHT.related)
        layout.setSpacing(LIGHT.related)
        layout.addWidget(page_header(
            "Pointage vidéo",
            "1 · Ouvrir   2 · Étalonner   3 · Placer l’origine   4 · Pointer   5 · Corriger",
        ))
        toolbar_panel, toolbar = panel(kind="toolbar", horizontal=True)
        self.open_button = compact_width(role(QPushButton("Ouvrir une vidéo…"), "primary"),
                                         LIGHT.action_compact)
        self.open_button.clicked.connect(self.choose_video)
        self.cancel_button = QPushButton("Annuler la préparation")
        self.cancel_button.clicked.connect(self.cancel_loading)
        self.cancel_button.hide()
        toolbar.addWidget(label("Fichier", "caption"))
        toolbar.addWidget(self.open_button, 0, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        toolbar.addWidget(self.cancel_button, 0, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        toolbar.addStretch()
        axes_label = QLabel("Sens des axes")
        self.axes_choice = WheelSafeComboBox()
        axes_label.setBuddy(self.axes_choice)
        self.axes_choice.setAccessibleName("Sens des axes X et Y")
        for title, directions in (("X droite · Y haut", (1, 1)), ("X droite · Y bas", (1, -1)),
                                   ("X gauche · Y haut", (-1, 1)), ("X gauche · Y bas", (-1, -1))):
            self.axes_choice.addItem(title, directions)
        compact_width(self.axes_choice, LIGHT.field_compact)
        self.axes_choice.setToolTip("Les coordonnées des points déjà acquis sont recalculées dans le nouveau repère.")
        self.axes_choice.currentIndexChanged.connect(self.change_axes)
        toolbar.addWidget(axes_label)
        toolbar.addWidget(self.axes_choice, 0, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(toolbar_panel)
        self.status = QLabel("Ouvrez une vidéo pour commencer. Lecture sans son.")
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        self.status.setWordWrap(True)
        role(self.status, "context")
        # Le fond contextuel garde son retrait horizontal et sa bordure, mais son
        # padding vertical ne doit pas épaissir toute la ligne d'informations.
        self.status.setStyleSheet("padding-top: 0; padding-bottom: 0;")
        self.calibrate_button = QPushButton("Étalon")
        self.origin_button = QPushButton("Origine")
        self.track_button = role(QPushButton("Pointer"), "primary")
        self.undo_button = role(QPushButton("Annuler"), "danger")
        self.calibrate_button.clicked.connect(lambda: self.set_mode("scale"))
        self.origin_button.clicked.connect(lambda: self.set_mode("origin"))
        self.track_button.clicked.connect(lambda: self.set_mode(None if self.mode == "track" else "track"))
        self.undo_button.clicked.connect(self.undo_point)
        calibration_group, calibration_layout = panel(kind="toolbar", horizontal=True)
        calibration_layout.addWidget(label("Étalonnage", "caption"), 0,
                                     Qt.AlignmentFlag.AlignVCenter)
        calibration_layout.addWidget(self.calibrate_button, 0, Qt.AlignmentFlag.AlignVCenter)
        calibration_layout.addWidget(self.origin_button, 0, Qt.AlignmentFlag.AlignVCenter)
        tracking_group, tracking_layout = panel(kind="toolbar", horizontal=True)
        tracking_layout.addWidget(label("Pointage", "caption"), 0,
                                  Qt.AlignmentFlag.AlignVCenter)
        tracking_layout.addWidget(self.track_button, 0, Qt.AlignmentFlag.AlignVCenter)
        self.automatic_button = QPushButton("Pointage automatique…")
        self.automatic_button.clicked.connect(self.automatic_action)
        tracking_layout.addWidget(self.automatic_button, 0, Qt.AlignmentFlag.AlignVCenter)
        self.redefine_button = QPushButton("Redéfinir l’objet")
        self.redefine_button.clicked.connect(self.redefine_automatic_object)
        self.redefine_button.hide()
        tracking_layout.addWidget(self.redefine_button, 0, Qt.AlignmentFlag.AlignVCenter)
        tracking_layout.addWidget(self.undo_button, 0, Qt.AlignmentFlag.AlignVCenter)
        self.correct_button = QPushButton("Corriger")
        self.correct_button.clicked.connect(self.toggle_correction)
        self.point_choice = WheelSafeComboBox()
        self.point_choice.setMinimumContentsLength(25)
        self.point_choice.setMaximumWidth(LIGHT.field_compact)
        self.point_choice.setAccessibleName("Point à corriger")
        self.point_choice.activated.connect(self.choose_point)
        tracking_layout.addWidget(self.correct_button, 0, Qt.AlignmentFlag.AlignVCenter)
        tracking_layout.addWidget(self.point_choice, 0, Qt.AlignmentFlag.AlignVCenter)
        self.direction_label = QLabel("Direction de l'étalon")
        self.calibration_direction = PopupComboBox()
        self.calibration_direction.setMaximumWidth(180)
        self.calibration_direction.setAccessibleName("Direction de l'étalon")
        self.direction_label.setBuddy(self.calibration_direction)
        for title, direction in (("Horizontal", "horizontal"), ("Vertical", "vertical"), ("Libre (diagonale)", "free")):
            self.calibration_direction.addItem(title, direction)
        configure_popup(self.calibration_direction, 180)
        update_popup_height(self.calibration_direction)
        self.calibration_direction.currentIndexChanged.connect(self.change_calibration_direction)
        calibration_layout.addWidget(self.direction_label, 0, Qt.AlignmentFlag.AlignVCenter)
        calibration_layout.addWidget(self.calibration_direction, 0,
                                     Qt.AlignmentFlag.AlignVCenter)
        calibration_layout.addStretch()
        self.workflow_cards = ResponsiveCards(calibration_group, tracking_group)
        self.workflow_cards.setSizePolicy(QSizePolicy.Policy.Expanding,
                                          QSizePolicy.Policy.Maximum)
        layout.addWidget(self.workflow_cards)
        self.tracking_info = QLabel()
        self.tracking_info.setWordWrap(True)
        self.hint = QLabel("Définissez l'étalon puis l'origine sur l'image de votre choix.")
        self.hint.setWordWrap(True)
        self.messages = QHBoxLayout()
        self.messages.setSpacing(LIGHT.related)
        self.messages.addWidget(self.status, 1)
        self.messages.addWidget(self.tracking_info, 1)
        self.messages.addWidget(self.hint, 2)
        layout.addLayout(self.messages)
        self._stabilize_message_height()
        self.screen = VideoCanvas()
        self.screen.clicked.connect(self.image_clicked)
        self.screen.point_selected.connect(self.select_point)
        self.screen.rectangle_selected.connect(self.automatic_rectangle_selected)
        stage = role(QFrame(), "videoStage")
        stage.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        view = QHBoxLayout(stage)
        view.setContentsMargins(LIGHT.related, LIGHT.related,
                                LIGHT.related, LIGHT.related)
        view.setSpacing(LIGHT.related)
        view.addWidget(self.screen, 1)
        self.magnifier = Magnifier(self.screen)
        magnifier_panel, magnifier_layout = panel("Loupe ×6")
        role(magnifier_panel, "videoTool")
        magnifier_layout.addWidget(self.magnifier)
        magnifier_layout.addWidget(label("Survolez la vidéo pour viser.", "muted"))
        magnifier_panel.setFixedWidth(154)
        view.addWidget(magnifier_panel, 0, Qt.AlignmentFlag.AlignTop)
        layout.addWidget(stage, 1)
        player = role(QFrame(), "playerBar")
        player.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        player_layout = QVBoxLayout(player)
        player_layout.setContentsMargins(LIGHT.related, LIGHT.small,
                                         LIGHT.related, LIGHT.small)
        player_layout.setSpacing(LIGHT.small)
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.valueChanged.connect(self.seek)
        player_layout.addWidget(self.slider)
        controls = QHBoxLayout()
        self.restart_button = QPushButton("Retour au début")
        self.restart_button.setToolTip("Revenir à la première image et mettre la vidéo en pause, en conservant l'étalonnage et les points.")
        self.restart_button.clicked.connect(self.restart_video)
        controls.addWidget(self.restart_button)
        self.previous = QPushButton("Image précédente")
        self.play_button = QPushButton("Lire")
        self.next = QPushButton("Image suivante")
        self.previous.clicked.connect(lambda: self.seek(self.index - 1))
        self.next.clicked.connect(lambda: self.seek(self.index + 1))
        self.play_button.clicked.connect(self.toggle_play)
        for button in (self.previous, self.play_button, self.next):
            controls.addWidget(button)
        self.position = QLabel("Image — · t = — s")
        controls.addStretch()
        controls.addWidget(self.position)
        player_layout.addLayout(controls)
        layout.addWidget(player)
        compact_controls = (
            self.open_button, self.cancel_button, self.axes_choice,
            self.calibrate_button, self.origin_button, self.track_button,
            self.automatic_button, self.redefine_button, self.undo_button,
            self.correct_button, self.point_choice,
            self.calibration_direction, self.restart_button, self.previous,
            self.play_button, self.next,
        )
        for control in compact_controls:
            control.setMaximumHeight(LIGHT.button_height - LIGHT.small)
        workflow_controls = (
            self.calibrate_button, self.origin_button, self.calibration_direction,
            self.track_button, self.automatic_button, self.redefine_button,
            self.undo_button, self.correct_button, self.point_choice,
        )
        for control in workflow_controls:
            control.setMaximumHeight(LIGHT.button_height)
        # Le style rend ces contrôles à 32 px : 2 px de marge dans le contenu,
        # plus la bordure de la carte, les centre dans les 38 px réservés.
        for workflow_layout in (calibration_layout, tracking_layout):
            margins = workflow_layout.contentsMargins()
            workflow_layout.setContentsMargins(
                margins.left(), LIGHT.small // 2, margins.right(), LIGHT.small // 2)
        workflow_height = LIGHT.button_height - LIGHT.small + 2 * LIGHT.toolbar_vertical
        calibration_group.setFixedHeight(workflow_height)
        tracking_group.setFixedHeight(workflow_height)
        for message in (self.hint, self.position):
            role(message, "muted")
        role(self.tracking_info, "caption")
        for key, action in (("Left", lambda: self.seek(self.index - 1)),
                            ("Right", lambda: self.seek(self.index + 1)),
                            ("Space", self.toggle_play), ("Escape", self.escape_mode)):
            shortcut = QShortcut(QKeySequence(key), self)
            shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
            shortcut.activated.connect(action)
        self._controls()

    def _controls(self):
        ready = self.cache is not None and self.loader is None
        automatic_running = self.mode == "auto_running"
        interactive = ready and not automatic_running
        self.slider.setEnabled(interactive)
        self.restart_button.setEnabled(interactive)
        self.axes_choice.setEnabled(interactive)
        self.axes_choice.blockSignals(True)
        directions = (self.tracking.x_direction, self.tracking.y_direction)
        self.axes_choice.setCurrentIndex(next(i for i in range(self.axes_choice.count())
                                              if tuple(self.axes_choice.itemData(i)) == directions))
        self.axes_choice.blockSignals(False)
        self.play_button.setEnabled(interactive and len(self.cache.times) > 1)
        self.previous.setEnabled(interactive and self.index > 0)
        self.next.setEnabled(interactive and self.index < len(self.cache.times) - 1)
        self.calibrate_button.setEnabled(interactive)
        self.direction_label.setVisible(self.mode == "scale")
        self.calibration_direction.setVisible(self.mode == "scale")
        self.calibration_direction.setEnabled(interactive)
        self.origin_button.setEnabled(interactive)
        calibrated = self.tracking.scale is not None and self.tracking.origin is not None
        self.track_button.setEnabled(interactive and calibrated)
        self.automatic_button.setEnabled(ready and calibrated and self.mode != "auto_recover")
        automatic_labels = {
            "auto_select": "Annuler la sélection",
            "auto_ready": "Lancer le pointage automatique",
            "auto_running": "Arrêter",
            "auto_paused": "Reprendre le pointage automatique",
            "auto_recover": "Reprendre le pointage automatique",
        }
        self.automatic_button.setText(automatic_labels.get(
            self.mode, "Pointage automatique…"))
        self.redefine_button.setVisible(self.mode in (
            "auto_ready", "auto_paused", "auto_recover"))
        self.redefine_button.setEnabled(interactive)
        self.undo_button.setEnabled(interactive and bool(self.tracking.history))
        correcting = self.mode in ("select", "edit")
        self.correct_button.setEnabled(interactive and bool(self.tracking.points))
        self.correct_button.setText("Retour au pointage" if correcting else "Corriger")
        self.point_choice.setVisible(correcting)
        self.point_choice.setEnabled(ready and correcting)
        self.point_choice.blockSignals(True)
        self.point_choice.clear()
        self.point_choice.addItem("Choisir un point…", None)
        for index, (_, timestamp) in sorted(self.tracking.points.items()):
            self.point_choice.addItem(f"Image {index + 1} · t = {timestamp:.6g} s", index)
        if self.mode == "edit":
            self.point_choice.setCurrentIndex(self.point_choice.findData(self.index))
        self.point_choice.blockSignals(False)
        self.screen.active = interactive and self.mode is not None
        self.screen.selecting = self.mode == "select"
        self.screen.selecting_rectangle = self.mode == "auto_select"
        self.screen.setCursor(Qt.CursorShape.PointingHandCursor if self.screen.selecting else
                              Qt.CursorShape.CrossCursor if self.screen.active else Qt.CursorShape.ArrowCursor)
        self.track_button.setText("Arrêter" if self.mode == "track" else "Pointer")
        self.screen.origin = self.tracking.origin
        self.screen.x_direction = self.tracking.x_direction
        self.screen.y_direction = self.tracking.y_direction
        self.screen.ruler = self.tracking.ruler
        self.screen.points = {i: value[0] for i, value in self.tracking.points.items()}
        # L'avance automatique conserve le dernier point bien visible.
        highlight = self.index if self.index in self.tracking.points else next(
            (i for i, _ in reversed(self.tracking.history) if i in self.tracking.points), None)
        self.screen.highlight_index = highlight
        stored = self.tracking.points.get(highlight)
        self.screen.point = stored[0] if stored else None
        if self.automatic_tracker is not None and self.mode in (
                "auto_ready", "auto_running", "auto_paused", "auto_recover"):
            self.screen.selection_rect = self.automatic_tracker.rectangle
            self.screen.selection_reference = self.automatic_tracker.point
        elif self.mode != "auto_select":
            self.screen.selection_rect = None
            self.screen.selection_reference = None
        self.screen.update()
        scale = (f"Étalon : {format(self.tracking.length, 'g').replace('.', ',')} {self.tracking.unit}"
                 if self.tracking.scale is not None else "Étalon : à définir")
        origin = "Origine définie" if self.tracking.origin is not None else "Origine : à définir"
        horizontal = "droite" if self.tracking.x_direction == 1 else "gauche"
        vertical = "haut" if self.tracking.y_direction == 1 else "bas"
        self.tracking_info.setText(f"{scale} · {origin} · {len(self.tracking.points)} point(s) · x vers la {horizontal}, y vers le {vertical}")
        self._balance_message_widths()

    def restart_video(self):
        if self.cache is None or self.loader is not None:
            return
        self.set_mode(None)
        self.seek(0)

    def change_axes(self, *args):
        if self.cache is None or self.loader is not None:
            return
        self.tracking.set_axes(*self.axes_choice.currentData())
        self._controls()

    def set_mode(self, mode):
        if mode is not None and (self.cache is None or self.loader is not None):
            return
        if mode == "track" and (self.tracking.origin is None or self.tracking.scale is None):
            return
        self.pause()
        if mode not in ("select", "edit"):
            self.correction_return = None
        self.mode = mode
        self.screen.anchor = None
        hint = self.MODE_HINTS[mode]
        if mode == "edit":
            hint = f"Image {self.index + 1} : {hint}"
        self._set_hint(hint)
        self._controls()

    def _set_hint(self, text):
        self.hint.setText(text)
        self._balance_message_widths()

    def _balance_message_widths(self):
        """Réserver au conseil sa largeur utile et rendre le reste aux informations."""
        available = max(1, self.width() - 2 * LIGHT.section - 2 * LIGHT.related)
        flags = Qt.TextFlag.TextWordWrap

        def wrapped_height(widget, text, width):
            margins = widget.contentsMargins()
            return (widget.fontMetrics().boundingRect(
                0, 0, max(1, width), 10000, flags, text).height()
                + margins.top() + margins.bottom())

        low, high = 1, max(1, available // 2)
        while low < high:
            middle = (low + high) // 2
            if wrapped_height(self.hint, self.hint.text(), middle) <= self.hint.height():
                high = middle
            else:
                low = middle + 1
        hint_width = min(available // 2, max(available // 8, low))

        def natural_width(widget, text):
            margins = widget.contentsMargins()
            return (widget.fontMetrics().horizontalAdvance(text)
                    + margins.left() + margins.right())

        status_width = natural_width(self.status, self.status.text())
        tracking_width = natural_width(
            self.tracking_info, self.tracking_info.text() or self.TRACKING_INFO_RESERVE)
        hint_natural_width = natural_width(self.hint, self.hint.text())
        if status_width + tracking_width + hint_natural_width <= available:
            hint_width = hint_natural_width
        info_width = max(2, available - hint_width)
        total = max(1, status_width + tracking_width)
        status_share = max(1, round(info_width * status_width / total))
        tracking_share = max(1, info_width - status_share)
        self.messages.setStretch(0, status_share)
        self.messages.setStretch(1, tracking_share)
        self.messages.setStretch(2, hint_width)

    def _stabilize_message_height(self):
        """Réserver une hauteur stable en donnant plus de largeur aux consignes."""
        available = max(1, self.width() - 2 * LIGHT.section - 2 * LIGHT.related)
        narrow_width = max(1, available // 4)
        hint_width = max(1, available - 2 * narrow_width)
        flags = Qt.TextFlag.TextWordWrap

        def text_height(widget, text, width):
            margins = widget.contentsMargins()
            return (widget.fontMetrics().boundingRect(
                0, 0, width, 10000, flags, text).height()
                + margins.top() + margins.bottom())

        height = max(
            max(text_height(self.hint, text, hint_width)
                for text in self.MODE_HINTS.values()),
            text_height(self.tracking_info, self.TRACKING_INFO_RESERVE, narrow_width),
            text_height(self.status, self.status.text(), narrow_width),
        )
        for message in (self.status, self.tracking_info, self.hint):
            message.setFixedHeight(height)
        self._balance_message_widths()

    def change_calibration_direction(self, *args):
        self.screen.calibration_direction = self.calibration_direction.currentData()
        self.screen.hovered.emit(self.screen.calibration_point(self.screen.pointer))
        self.screen.update()

    def toggle_correction(self):
        if self.mode in ("select", "edit"):
            target = self.correction_return
            self.set_mode(None)
            if target is not None:
                index, mode = target
                self.seek(index)
                self.set_mode(mode)
        elif self.tracking.points:
            return_mode = "track" if self.mode == "track" else (
                "auto_paused" if self.mode == "auto_paused" else None)
            target = (self.index, return_mode)
            self.set_mode("select")
            self.correction_return = target

    def escape_mode(self):
        if self.mode == "edit":
            self.set_mode("select")
        elif self.mode == "select":
            self.toggle_correction()
        elif self.mode == "auto_running":
            self.stop_automatic()
        elif self.mode in ("auto_select", "auto_ready"):
            self.automatic_tracker = None
            self.automatic_anchor_pending = False
            self.set_mode(None)
        else:
            self.set_mode(None)

    def choose_point(self, choice):
        index = self.point_choice.itemData(choice)
        if index is not None:
            self.select_point(index)

    def select_point(self, index):
        if self.mode not in ("select", "edit") or index not in self.tracking.points:
            return
        self.seek(index)
        self.set_mode("edit")

    def image_clicked(self, point):
        if self.cache is None or self.loader is not None:
            return
        if self.mode == "scale":
            if self.screen.anchor is None:
                self.screen.anchor = point
                self._set_hint("Cliquez sur la seconde extrémité de l'étalon. Échap pour annuler.")
                self.screen.update()
                return
            start = self.screen.anchor
            point = self.screen.calibration_point(point)
            if hypot(point.x() - start.x(), point.y() - start.y()) < 1:
                self._set_hint("La longueur doit couvrir au moins un pixel dans la direction choisie. Cliquez plus loin ou changez de direction.")
                return
            dialog = CalibrationDialog(self)
            if dialog.exec() == QDialog.DialogCode.Accepted:
                self.tracking.calibrate(start, point, dialog.length.value(), "m")
            self.set_mode(None)
        elif self.mode == "origin":
            self.tracking.set_origin(point)
            self.set_mode(None)
        elif self.mode == "edit":
            if self.index not in self.tracking.points:
                return
            self.tracking.record(self.index, point, self.tracking.points[self.index][1])
            if (self.correction_return is not None
                    and self.correction_return[1] == "auto_paused"
                    and self.automatic_tracker is not None):
                self.automatic_tracker.reanchor(self.pixmap.toImage(), point)
                self.correction_return = (self.index, "auto_paused")
            self.set_mode("select")
            self._set_hint(f"Point de l'image {self.index + 1} corrigé. Choisissez un autre point ou revenez au pointage. Vous pouvez annuler la dernière action.")
        elif self.mode == "track":
            self.tracking.record(self.index, point, self.cache.times[self.index])
            if self.index < len(self.cache.times) - 1:
                self._show_frame(self.index + 1)
            else:
                self.set_mode(None)
                self._set_hint("Dernière image pointée. Les mesures x, y et t sont disponibles dans Données et Graphique.")
        elif self.mode == "auto_recover" and self.automatic_tracker is not None:
            self.tracking.record(self.index, point, self.cache.times[self.index])
            self.automatic_tracker.reanchor(self.pixmap.toImage(), point)
            self.automatic_anchor_pending = False
            self.set_mode("auto_paused")
            self._set_hint("Position corrigée. Vous pouvez reprendre le pointage automatique à l’image suivante.")

    def automatic_action(self):
        if self.mode == "auto_running":
            self.stop_automatic()
        elif self.mode == "auto_select":
            self.automatic_tracker = None
            self.automatic_anchor_pending = False
            self.set_mode(None)
        elif self.mode in ("auto_ready", "auto_paused"):
            self.start_automatic()
        else:
            dialog = QDialog(self)
            dialog.setWindowTitle("Pointage automatique")
            layout = QVBoxLayout(dialog)
            message = QLabel(
                "Le pointage automatique est plus rapide, mais moins précis.\n"
                "Pour un pointage plus précis, privilégiez le pointage manuel.\n\n"
                "Encadrez ensuite l’objet à suivre.")
            message.setWordWrap(True)
            layout.addWidget(message)
            buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                       QDialogButtonBox.StandardButton.Cancel)
            buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Continuer")
            buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Annuler")
            buttons.accepted.connect(dialog.accept)
            buttons.rejected.connect(dialog.reject)
            layout.addWidget(buttons)
            if dialog.exec() == QDialog.DialogCode.Accepted:
                self.automatic_tracker = None
                self.automatic_anchor_pending = False
                self.set_mode("auto_select")

    def redefine_automatic_object(self):
        if self.cache is None or self.mode == "auto_running":
            return
        self.set_mode("auto_select")
        self.screen.selection_rect = None
        self.screen.selection_reference = None
        self.screen.update()

    def automatic_rectangle_selected(self, rectangle):
        if self.mode != "auto_select":
            return
        try:
            self.automatic_tracker = AutomaticTracker(self.pixmap.toImage(), rectangle)
        except ValueError as error:
            self._set_hint(str(error) + " Recommencez la sélection.")
            return
        self.automatic_anchor_pending = True
        self.set_mode("auto_ready")

    def start_automatic(self):
        if self.automatic_tracker is None or self.mode not in ("auto_ready", "auto_paused"):
            return
        if self.automatic_anchor_pending:
            self.tracking.record(self.index, self.automatic_tracker.point,
                                 self.cache.times[self.index])
            self.automatic_anchor_pending = False
        elif self.mode == "auto_paused":
            stored = self.tracking.points.get(self.index)
            if stored is None:
                self.set_mode("auto_recover")
                self._set_hint(
                    "Aucun point fiable n’existe sur cette image. Cliquez sur l’objet "
                    "ou redéfinissez-le avant de reprendre.")
                return
            self.automatic_tracker.reanchor(self.pixmap.toImage(), stored[0])
        if self.index >= len(self.cache.times) - 1:
            self.finish_automatic()
            return
        self.set_mode("auto_running")
        self.automatic_timer.start(0)

    def _automatic_tick(self):
        if self.mode != "auto_running" or self.automatic_tracker is None:
            return
        next_index = self.index + 1
        if next_index >= len(self.cache.times):
            self.finish_automatic()
            return
        self._show_frame(next_index)
        match = self.automatic_tracker.locate(self.pixmap.toImage())
        if match is None:
            self.set_mode("auto_recover")
            self._set_hint(
                "L’objet n’a pas pu être identifié avec suffisamment de fiabilité. "
                "Aucun point douteux n’a été ajouté sur cette image.")
            return
        self.tracking.record(self.index, match.point, self.cache.times[self.index])
        self._controls()
        if self.index >= len(self.cache.times) - 1:
            self.finish_automatic()
        else:
            self.automatic_timer.start(0)

    def stop_automatic(self):
        if self.mode != "auto_running":
            return
        self.automatic_timer.stop()
        self.set_mode("auto_paused")
        self._set_hint("Pointage automatique arrêté. Les points obtenus sont conservés.")

    def finish_automatic(self):
        self.automatic_timer.stop()
        self.automatic_tracker = None
        self.automatic_anchor_pending = False
        self.set_mode(None)
        self._set_hint("Pointage automatique terminé.")

    def undo_point(self):
        automatic = (self.mode in ("auto_paused", "auto_recover")
                     and self.automatic_tracker is not None)
        self.set_mode(None)
        index = self.tracking.undo()
        if index is not None:
            self.seek(index)
        if automatic and index is not None:
            reference_index = index if index in self.tracking.points else next(
                (candidate for candidate in sorted(self.tracking.points, reverse=True)
                 if candidate < index), None)
            if reference_index is not None:
                self.seek(reference_index)
                self.automatic_tracker.reanchor(
                    self.pixmap.toImage(), self.tracking.points[reference_index][0])
                self.set_mode("auto_paused")
        self._controls()

    def choose_video(self):
        path, _ = QFileDialog.getOpenFileName(self, "Ouvrir une vidéo", "",
            "Vidéos (*.avi *.mp4 *.m4v *.mov *.mkv *.mpg *.mpeg *.wmv *.webm *.flv *.mts *.m2ts *.ogv);;Tous les fichiers (*)")
        if path:
            self.open_video(path)

    def open_video(self, path):
        if self.loader is not None:
            return
        self.pause()
        self.automatic_timer.stop()
        self.automatic_tracker = None
        self.set_mode(None)
        self.status.setText(f"Préparation de {Path(path).name}… Cache temporaire limité à 4 Go.")
        self.open_button.setEnabled(False)
        self.cancel_button.setEnabled(True)
        self.cancel_button.show()
        self.loader = VideoLoader(path, self)
        self.loader.progress.connect(lambda count: self.status.setText(
            f"Préparation de {Path(path).name} : {count} images décodées…"))
        self.loader.finished.connect(self._loaded)
        self._controls()
        self.loader.start()

    def cancel_loading(self):
        if self.loader:
            self.loader.requestInterruption()
            self.cancel_button.setEnabled(False)

    def _loaded(self):
        worker = self.loader
        if worker is None:
            return
        self.loader = None
        self.open_button.setEnabled(True)
        self.cancel_button.hide()
        if worker.isInterruptionRequested():
            if worker.cache:
                worker.cache.close()
            self.status.setText("Préparation annulée.")
        elif worker.error:
            self.status.setText(f"Impossible d'ouvrir la vidéo : {worker.error}")
        elif worker.cache:
            if self.cache:
                self.cache.close()
            self.cache = worker.cache
            self.tracking = TrackingSession(self.model)
            self.mode = None
            self.screen.anchor = None
            self.calibration_direction.setCurrentIndex(0)
            self._set_hint("Définissez l'étalon puis l'origine sur l'image de votre choix.")
            self.slider.blockSignals(True)
            self.slider.setRange(0, len(self.cache.times) - 1)
            self.slider.blockSignals(False)
            warning = " · Temps estimés : horodatages manquants." if self.cache.estimated_times else ""
            self.status.setText(f"{Path(worker.path).name} · {self.cache.width} × {self.cache.height} · Lecture sans son.{warning}")
            self._show_frame(0)
        worker.deleteLater()
        self._controls()

    def seek(self, index):
        if self.cache is None or self.loader is not None:
            return
        self.pause()
        if self.mode == "auto_running":
            self.stop_automatic()
        if self.mode in ("scale", "origin"):
            self.set_mode(None)
        elif self.mode == "edit":
            self.set_mode("select")
        self._show_frame(max(0, min(index, len(self.cache.times) - 1)))

    def _show_frame(self, index):
        self.index = index
        self.pixmap = QPixmap(self.cache.path(index))
        self._scale_image()
        self.slider.blockSignals(True)
        self.slider.setValue(index)
        self.slider.blockSignals(False)
        self.position.setText(f"Image {index + 1} / {len(self.cache.times)} · t = {self.cache.times[index]:.6f} s")
        self._controls()

    def _scale_image(self):
        if not self.pixmap.isNull():
            self.screen.setPixmap(self.pixmap)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._stabilize_message_height()
        self._scale_image()

    def toggle_play(self):
        if self.cache is None or self.loader is not None or len(self.cache.times) < 2:
            return
        if self.playing:
            self.pause()
            return
        self.set_mode(None)
        if self.index == len(self.cache.times) - 1:
            self._show_frame(0)
        self.playing = True
        self.play_button.setText("Pause")
        self.start_time = self.cache.times[self.index]
        self.clock.start()
        self._schedule()

    def _schedule(self):
        if self.index >= len(self.cache.times) - 1:
            self.pause()
            return
        delay = (self.cache.times[self.index + 1] - self.start_time) * 1000 - self.clock.elapsed()
        self.timer.start(max(1, min(round(delay), 2147483647)))

    def _tick(self):
        if self.playing:
            self._show_frame(self.index + 1)
            self._schedule()

    def pause(self):
        self.timer.stop()
        self.playing = False
        self.play_button.setText("Lire")

    def shutdown(self):
        self.pause()
        self.automatic_timer.stop()
        if self.loader:
            self.loader.requestInterruption()
            self.loader.wait()
            if self.loader.cache:
                self.loader.cache.close()
            self.loader.deleteLater()
            self.loader = None
        if self.cache:
            self.cache.close()
            self.cache = None
