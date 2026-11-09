"""Petits composants de présentation sans logique scientifique."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QApplication, QBoxLayout, QComboBox, QFrame,
                               QHBoxLayout, QLabel, QPushButton, QScrollArea,
                               QSizePolicy, QVBoxLayout, QWidget, QMessageBox)

from physalix.ui.theme import LIGHT


class WheelSafeComboBox(QComboBox):
    """Ignore the wheel while closed so a surrounding panel keeps scrolling."""

    def wheelEvent(self, event):
        if self.view().isVisible():
            delta = event.pixelDelta().y()
            if not delta:
                row_height = max(1, self.view().sizeHintForRow(0))
                delta = (event.angleDelta().y() / 120
                         * QApplication.wheelScrollLines() * row_height)
            scrollbar = self.view().verticalScrollBar()
            scrollbar.setValue(scrollbar.value() - round(delta))
            event.accept()
        else:
            event.ignore()


def role(widget, name):
    widget.setProperty("role", name)
    return widget


def refresh_style(widget):
    """Réappliquer les sélecteurs QSS après changement d’une propriété dynamique."""
    widget.style().unpolish(widget)
    widget.style().polish(widget)


def compact_width(widget, maximum_width):
    """Conserver la largeur utile d’un contrôle dans un layout horizontal."""
    widget.setFixedWidth(min(maximum_width, max(widget.sizeHint().width(),
                                               widget.minimumSizeHint().width())))
    return widget


def label(text, kind="sectionTitle"):
    widget = role(QLabel(text), kind)
    widget.setWordWrap(True)
    return widget


def ask_yes_no(parent, title, text):
    """Afficher une confirmation avec des libellés français explicites."""
    dialog = QMessageBox(parent)
    dialog.setIcon(QMessageBox.Icon.Question)
    dialog.setWindowTitle(title)
    dialog.setText(text)
    yes_button = role(
        dialog.addButton("Oui", QMessageBox.ButtonRole.AcceptRole), "primary"
    )
    no_button = dialog.addButton("Non", QMessageBox.ButtonRole.RejectRole)
    dialog.setDefaultButton(no_button)
    dialog.setEscapeButton(no_button)
    dialog.exec()
    return dialog.clickedButton() is yes_button


def page_layout(layout):
    layout.setContentsMargins(LIGHT.page, LIGHT.section, LIGHT.page, LIGHT.section)
    layout.setSpacing(LIGHT.group)
    return layout


def page_header(title, description):
    widget = role(QWidget(), "pageHeader")
    row = QHBoxLayout(widget)
    row.setContentsMargins(0, 0, 0, 0)
    row.setSpacing(LIGHT.group)
    accent = role(QFrame(), "pageAccent")
    accent.setFixedSize(5, 38)
    row.addWidget(accent)
    text = QVBoxLayout()
    text.setSpacing(1)
    text.addWidget(label(title, "pageTitle"))
    text.addWidget(label(description, "pageSubtitle"))
    row.addLayout(text, 1)
    return widget


def panel(title=None, kind="card", horizontal=False):
    widget = role(QFrame(), kind)
    if kind in ("help", "toolbar"):
        widget.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
    outer = QVBoxLayout(widget)
    outer.setContentsMargins(0, 0, 0, 0)
    outer.setSpacing(0)
    if title:
        header = role(QWidget(), "cardHeader")
        heading = QHBoxLayout(header)
        heading.setContentsMargins(LIGHT.section, LIGHT.header_vertical,
                                   LIGHT.section, LIGHT.header_vertical)
        heading.setSpacing(LIGHT.related)
        accent = role(QFrame(), "cardAccent")
        accent.setFixedSize(4, 20)
        heading.addWidget(accent)
        heading.addWidget(label(title, "cardTitle"), 1)
        outer.addWidget(header)
        divider = role(QFrame(), "cardDivider")
        divider.setFixedHeight(1)
        outer.addWidget(divider)
    content = QWidget()
    layout = QHBoxLayout(content) if horizontal else QVBoxLayout(content)
    vertical = LIGHT.toolbar_vertical if kind in ("help", "toolbar") else LIGHT.card_vertical
    layout.setContentsMargins(LIGHT.section, vertical, LIGHT.section, vertical)
    layout.setSpacing(vertical)
    outer.addWidget(content, 1)
    return widget, layout


def workspace_layout(owner, minimum_width, minimum_height):
    """Préserver l'accès aux outils par défilement sous la taille confortable."""
    outer = QVBoxLayout(owner)
    outer.setContentsMargins(0, 0, 0, 0)
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    content = QWidget()
    content.setMinimumSize(minimum_width, minimum_height)
    scroll.setWidget(content)
    outer.addWidget(scroll)
    return page_layout(QVBoxLayout(content))


def help_toggle(title, text, description=None):
    """Aide au clavier comme à la souris, repliée au lancement."""
    box, layout = panel(kind="help")
    heading = QHBoxLayout()
    if description is not None:
        heading.addWidget(label(title, "pageTitle"))
        if description:
            heading.addWidget(label(description, "pageSubtitle"), 1)
        else:
            heading.addStretch(1)
    else:
        heading.addWidget(label(title, "caption"), 1)
    toggle = QPushButton("Afficher l’aide")
    toggle.setCheckable(True)
    heading.addWidget(toggle)
    layout.addLayout(heading)
    details = label(text, "muted")
    details.hide()
    layout.addWidget(details)
    def expand(checked):
        details.setVisible(checked)
        toggle.setText("Masquer l’aide" if checked else "Afficher l’aide")
    toggle.toggled.connect(expand)
    return box


class ResponsiveCards(QWidget):
    """Deux cartes côte à côte, empilées lorsque la fenêtre est étroite."""

    def __init__(self, first, second, first_stretch=1, second_stretch=1):
        super().__init__()
        self.horizontal_stretch = first_stretch, second_stretch
        self.cards = QBoxLayout(QBoxLayout.Direction.TopToBottom, self)
        self.cards.setContentsMargins(0, 0, 0, 0)
        self.cards.setSpacing(LIGHT.section)
        self.cards.addWidget(first, 1)
        self.cards.addWidget(second, 1)
        self._set_direction(self.width())

    def _set_direction(self, width):
        direction = (QBoxLayout.Direction.LeftToRight if width >= LIGHT.wide_layout
                     else QBoxLayout.Direction.TopToBottom)
        if self.cards.direction() != direction:
            self.cards.setDirection(direction)
        for index, stretch in enumerate(self.horizontal_stretch):
            self.cards.setStretch(index, stretch if direction == QBoxLayout.Direction.LeftToRight else 0)

    def resizeEvent(self, event):
        self._set_direction(event.size().width())
        super().resizeEvent(event)


class ResponsiveActions(QWidget):
    """Aligner les actions sur une ligne, puis les empiler sans débordement."""

    def __init__(self, primary, secondary, tertiary=None):
        super().__init__()
        self.widgets = tuple(widget for widget in (primary, secondary, tertiary) if widget is not None)
        self.actions = QBoxLayout(QBoxLayout.Direction.TopToBottom, self)
        self.actions.setContentsMargins(0, 0, 0, 0)
        self.actions.setSpacing(LIGHT.related)
        self._horizontal = None
        self._arrange(self.width() >= 1000)

    def _arrange(self, horizontal):
        if self._horizontal == horizontal:
            return
        while self.actions.count():
            self.actions.takeAt(0)
        self.actions.setDirection(QBoxLayout.Direction.LeftToRight if horizontal
                                  else QBoxLayout.Direction.TopToBottom)
        self.actions.addWidget(self.widgets[0], 0, Qt.AlignmentFlag.AlignLeft)
        if len(self.widgets) > 1:
            self.actions.addWidget(self.widgets[1], 0, Qt.AlignmentFlag.AlignLeft)
        if len(self.widgets) > 2:
            if horizontal:
                self.actions.addStretch()
            self.actions.addWidget(self.widgets[2], 0, Qt.AlignmentFlag.AlignLeft)
        self._horizontal = horizontal

    def resizeEvent(self, event):
        self._arrange(event.size().width() >= 1000)
        super().resizeEvent(event)
