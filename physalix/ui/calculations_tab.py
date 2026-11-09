"""Création de dérivées et de colonnes calculées depuis les mesures."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView, QFormLayout, QHBoxLayout, QHeaderView,
    QLabel, QLineEdit, QPushButton, QScrollArea, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget, QDialog, QDialogButtonBox, QMenu, QFrame, QSizePolicy,
    QMessageBox,
)

from physalix.calculations import (CalculationEngine, FormulaError,
                                   derivative_unit, quantity_reference)
from physalix.ui.graph_series import PopupComboBox, configure_popup, update_popup_height
from physalix.ui.math_help import math_help_button
from physalix.ui.units import unit_combo
from physalix.ui.components import (ResponsiveCards, label as section_label, page_header,
                                    page_layout, panel, role)
from physalix.ui.theme import LIGHT


def quantity_label(model, column, *, insertion=False):
    name = model.names[column] or f"Grandeur {column + 1}"
    label = name + (f" ({model.units[column]})" if model.units[column] else "")
    if model.names.count(model.names[column]) > 1:
        label += f" — colonne {column + 1}"
    token = quantity_reference(model.names, column)
    if insertion and token != model.names[column]:
        label += f" — insérée comme {token}"
    return label


def formula_error_message(error):
    message = str(error)
    if isinstance(error, FormulaError):
        guidance = {
            "unknown_quantity": "Vérifiez son nom ou utilisez la liste des grandeurs disponibles.",
            "unknown_function": "Utilisez une fonction proposée dans l’aide mathématique.",
            "syntax": "Vérifiez les parenthèses, les opérateurs et les noms utilisés.",
            "ambiguous": "Choisissez explicitement la grandeur dans la liste d’insertion.",
            "circular": "Conservez une chaîne de calcul allant des mesures vers les résultats.",
            "math": "Vérifiez le domaine des fonctions, les divisions et les valeurs du tableau.",
        }.get(error.kind)
        if guidance:
            message += "\n\n" + guidance
    return message


class FormulaEditDialog(QDialog):
    """Modifier le calcul en place ; Annuler conserve intégralement la grandeur."""

    def __init__(self, engine, item, parent=None):
        super().__init__(parent)
        self.engine, self.item = engine, item
        self.setWindowTitle("Modifier la formule")
        self.resize(600, 280)
        layout = page_layout(QVBoxLayout(self))
        title = section_label(f"Formule de {engine.model.names[item.column]}")
        title.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(title)
        self.expression = QLineEdit(item.formula.editable_expression(engine.model.names))
        caption = QLabel("Formule :")
        caption.setBuddy(self.expression)
        layout.addWidget(caption)
        layout.addWidget(self.expression)
        unit_caption = QLabel("Unité du résultat :")
        self.unit = unit_combo()
        self.unit.setCurrentText(engine.model.units[item.column])
        self.unit.setMaximumWidth(LIGHT.field_medium)
        unit_caption.setBuddy(self.unit)
        layout.addWidget(unit_caption)
        layout.addWidget(self.unit)
        layout.addWidget(math_help_button(self))
        columns = PopupComboBox()
        configure_popup(columns, LIGHT.field_wide)
        for column, name in enumerate(engine.model.names):
            columns.addItem(quantity_label(engine.model, column, insertion=True), column)
        update_popup_height(columns)
        insert = QPushButton("Insérer la grandeur")
        insert.clicked.connect(lambda: self.expression.insert(
            quantity_reference(engine.model.names, columns.currentData())))
        row = QHBoxLayout()
        row.addWidget(columns, 1)
        row.addWidget(insert)
        layout.addLayout(row)
        layout.addWidget(section_label(
            "Saisissez les noms des grandeurs. Une référence de colonne n’est proposée que si "
            "un nom ne peut pas être utilisé sans ambiguïté. Les calculs dépendants seront mis à jour.", "muted"))
        self.error = QLabel()
        self.error.setTextFormat(Qt.TextFormat.PlainText)
        self.error.setWordWrap(True)
        layout.addWidget(self.error)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        role(buttons.button(QDialogButtonBox.StandardButton.Save), "primary").setText("Enregistrer")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Annuler")
        buttons.accepted.connect(self.save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.expression.setFocus()

    def save(self):
        try:
            if not any(item is self.item for item in self.engine.items):
                raise ValueError("Cette grandeur a été supprimée.")
            self.engine.update_formula(self.item.column, self.expression.text())
            self.engine.model.setData(
                self.engine.model.index(1, self.item.column), self.unit.currentText())
        except ValueError as error:
            message = formula_error_message(error)
            self.error.setText(message)
            QMessageBox.warning(self, "Impossible de calculer la formule", message)
            self.expression.setFocus()
            return
        self.accept()


class DerivativeEditDialog(QDialog):
    """Modifier une dérivée sans changer sa nature ni sa colonne."""

    def __init__(self, engine, item, parent=None):
        super().__init__(parent)
        self.engine, self.item = engine, item
        self.setWindowTitle("Modifier la dérivée")
        layout = page_layout(QVBoxLayout(self))
        layout.addWidget(section_label(f"Dérivée {engine.model.names[item.column]}"))
        form = QFormLayout()
        self.source, self.axis = PopupComboBox(), PopupComboBox()
        for combo in (self.source, self.axis):
            configure_popup(combo, LIGHT.field_wide)
            for column in range(engine.model.columnCount()):
                combo.addItem(quantity_label(engine.model, column), column)
            update_popup_height(combo)
        self.source.setCurrentIndex(self.source.findData(item.source))
        self.axis.setCurrentIndex(self.axis.findData(item.axis))
        self.name = QLineEdit(engine.model.names[item.column])
        self.unit = QLineEdit(engine.model.units[item.column])
        form.addRow("Grandeur à dériver :", self.source)
        form.addRow("Par rapport à :", self.axis)
        form.addRow("Nom du résultat :", self.name)
        form.addRow("Unité du résultat :", self.unit)
        layout.addLayout(form)
        self.error = QLabel()
        self.error.setWordWrap(True)
        layout.addWidget(self.error)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        role(buttons.button(QDialogButtonBox.StandardButton.Save), "primary").setText("Enregistrer")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Annuler")
        buttons.accepted.connect(self.save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.name.setFocus()

    def save(self):
        try:
            self.engine.update_derivative(
                self.item.column, self.name.text(), self.unit.text(),
                self.source.currentData(), self.axis.currentData(),
            )
        except ValueError as error:
            self.error.setText(str(error))
            return
        self.accept()


class CalculationsTab(QWidget):
    def __init__(self, model):
        super().__init__()
        self.model = model
        self.engine = CalculationEngine(model)
        outer = page_layout(QVBoxLayout(self))
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        outer.addWidget(scroll)
        content = QWidget()
        scroll.setWidget(content)
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(LIGHT.section)
        layout.addWidget(page_header(
            "Calculs",
            "Créez des dérivées et des grandeurs par formule, disponibles dans Données et Graphique.",
        ))

        derivative, derivative_layout = panel("Calcul de dérivée")
        form = QFormLayout()
        form.setVerticalSpacing(LIGHT.related)
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        derivative_layout.addLayout(form)
        self.source = PopupComboBox()
        self.axis = PopupComboBox()
        self.derivative_name = QLineEdit()
        self.derivative_name.setPlaceholderText("Exemple : Vx, Vy ou ax")
        self.derivative_unit = QLineEdit()
        for control in (self.source, self.axis):
            control.setMaximumWidth(LIGHT.field_wide)
            configure_popup(control, LIGHT.field_wide)
        for control in (self.derivative_name, self.derivative_unit):
            control.setMaximumWidth(LIGHT.field_medium)
        form.addRow("Grandeur à dériver :", self.source)
        form.addRow("Par rapport à :", self.axis)
        form.addRow("Nom du résultat :", self.derivative_name)
        form.addRow("Unité du résultat :", self.derivative_unit)
        rule = QLabel("Dᵢ = (fᵢ₊₁ − fᵢ₋₁) / (uᵢ₊₁ − uᵢ₋₁)\n"
                      "Premier et dernier points : vides. Aucun calcul à travers une donnée manquante. "
                      "Avec un pas variable, cette formule donne la pente entre les deux voisins.")
        rule.setWordWrap(True)
        role(rule, "muted")
        form.addRow(rule)
        self.derive_button = role(QPushButton("Créer la dérivée"), "primary")
        self.derive_button.clicked.connect(self.create_derivative)
        form.addRow(self.derive_button)

        formula, formula_layout = panel("Nouvelle grandeur par formule")
        form = QFormLayout()
        form.setVerticalSpacing(LIGHT.related)
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        formula_layout.addLayout(form)
        self.formula_name = QLineEdit()
        self.formula_name.setPlaceholderText("Exemple : v")
        self.formula_unit = unit_combo()
        self.formula_unit.lineEdit().setPlaceholderText("Exemple : cm/s si Vx et Vy sont en cm/s")
        self.expression = QLineEdit()
        self.formula_name.setMaximumWidth(LIGHT.field_medium)
        self.formula_unit.setMaximumWidth(LIGHT.field_medium)
        self.expression.setMaximumWidth(LIGHT.field_wide)
        self.expression.setPlaceholderText("SQRT(Vx^2 + Vy^2)")
        self.expression.returnPressed.connect(self.create_formula)
        form.addRow("Nom du résultat :", self.formula_name)
        form.addRow("Unité du résultat :", self.formula_unit)
        form.addRow("Formule :", self.expression)
        self.quantity = PopupComboBox()
        self.quantity.setMaximumWidth(LIGHT.field_wide)
        configure_popup(self.quantity, LIGHT.field_wide)
        keypad = role(QFrame(), "keypad")
        keys = QHBoxLayout(keypad)
        keys.setContentsMargins(6, 4, 6, 4)
        keys.setSpacing(4)
        for label, value in (("SQRT(…)", "SQRT("), ("²", "²"), ("^", "^"),
                             ("(", "("), (")", ")"), ("+", "+"), ("−", "-"), ("×", "*"), ("/", "/")):
            button = QPushButton(label)
            button.clicked.connect(lambda checked=False, text=value: self.insert_text(text))
            keys.addWidget(button)
        form.addRow(keypad)
        self.math_help_button = math_help_button(self)
        form.addRow(self.math_help_button)
        self.formula_button = role(QPushButton("Créer la grandeur"), "primary")
        self.formula_button.clicked.connect(self.create_formula)
        form.addRow(self.formula_button)
        self.quantity_toggle = QPushButton(
            "Insérer une grandeur existante (facultatif) ▸"
        )
        self.quantity_toggle.setCheckable(True)
        self.quantity_toggle.setChecked(False)
        role(self.quantity_toggle, "quiet")
        form.addRow(self.quantity_toggle)
        self.quantity_options = role(QFrame(), "optionArea")
        insert_row = QHBoxLayout(self.quantity_options)
        insert_row.setContentsMargins(LIGHT.group, LIGHT.small, 0, LIGHT.small)
        insert_row.setSpacing(LIGHT.related)
        insert_row.addWidget(self.quantity, 1)
        self.quantity_insert_button = QPushButton("Insérer la grandeur")
        self.quantity_insert_button.clicked.connect(self.insert_quantity)
        insert_row.addWidget(self.quantity_insert_button)
        self.quantity_options.hide()
        form.addRow(self.quantity_options)
        self.quantity_toggle.toggled.connect(self.toggle_quantity_options)
        self.tools = ResponsiveCards(derivative, formula)
        layout.addWidget(self.tools)
        self.feedback = QLabel("Les cellules calculées sont protégées ; renommez leur en-tête dans Données à tout moment.")
        self.feedback.setWordWrap(True)
        self.feedback.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(self.feedback)
        role(self.feedback, "context")
        history_panel, history_layout = panel("Grandeurs calculées")
        history_layout.setSpacing(LIGHT.related)
        history_actions = QHBoxLayout()
        history_actions.setSpacing(LIGHT.related)
        history_actions.addWidget(section_label(
            "Double-cliquez sur une grandeur pour modifier son calcul.", "muted"), 1)
        self.edit_formula_button = QPushButton("Modifier…")
        self.edit_formula_button.clicked.connect(lambda: self.edit_calculation(self.history.currentRow()))
        self.edit_formula_button.setEnabled(False)
        history_actions.addWidget(self.edit_formula_button, 0, Qt.AlignmentFlag.AlignRight)
        history_layout.addLayout(history_actions)
        self.history = QTableWidget(0, 4)
        self.history.setHorizontalHeaderLabels(["Grandeur", "Unité", "Calcul lié", "Bilan"])
        self.history.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.history.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.history.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.history.cellDoubleClicked.connect(self.edit_calculation)
        self.history.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.history.customContextMenuRequested.connect(self.calculation_menu)
        self.history.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.history.horizontalHeader().setStretchLastSection(True)
        self.history.setMinimumHeight(120)
        self.history.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.history.verticalHeader().setDefaultSectionSize(32)
        history_layout.addWidget(self.history)
        self.history.itemSelectionChanged.connect(self.update_edit_button)
        layout.addWidget(history_panel, 1)
        self.engine.changed.connect(self.refresh)
        self.source.currentIndexChanged.connect(self.suggest_derivative)
        self.axis.currentIndexChanged.connect(self.suggest_derivative)
        self.refresh()
        time_column = next((i for i, name in enumerate(model.names) if name == "t"), min(1, model.columnCount() - 1))
        self.axis.setCurrentIndex(time_column)
        self.suggest_derivative()

    def toggle_quantity_options(self, visible):
        self.quantity_options.setVisible(visible)
        self.quantity_toggle.setText(
            "Insérer une grandeur existante (facultatif) " + ("▾" if visible else "▸")
        )

    def refresh(self):
        for combo in (self.source, self.axis, self.quantity):
            previous = combo.currentData()
            combo.blockSignals(True)
            combo.clear()
            for i, (name, unit) in enumerate(zip(self.model.names, self.model.units)):
                combo.addItem(quantity_label(self.model, i, insertion=combo is self.quantity), i)
            update_popup_height(combo)
            combo.setCurrentIndex(max(0, combo.findData(previous)))
            combo.blockSignals(False)
        self.history.setRowCount(len(self.engine.items))
        for row, item in enumerate(self.engine.items):
            description = (item.formula.description(self.model.names) if item.formula else
                           f"d({self.model.names[item.source]}) / d({self.model.names[item.axis]})")
            for col, text in enumerate((self.model.names[item.column], self.model.units[item.column], description, item.status)):
                cell = QTableWidgetItem(text)
                cell.setToolTip(text)
                self.history.setItem(row, col, cell)
        self.update_edit_button()

    def item_at(self, row):
        if 0 <= row < len(self.engine.items):
            return self.engine.items[row]

    def update_edit_button(self):
        self.edit_formula_button.setEnabled(self.item_at(self.history.currentRow()) is not None)

    def edit_calculation(self, row, column=0):
        item = self.item_at(row)
        if item is not None:
            dialog = (FormulaEditDialog(self.engine, item, self) if item.formula is not None
                      else DerivativeEditDialog(self.engine, item, self))
            if dialog.exec() == QDialog.DialogCode.Accepted:
                self.feedback.setText(
                    f"Calcul de {self.model.names[item.column]} modifié. Les résultats ont été recalculés.")

    def edit_calculation_column(self, column):
        """Ouvrir l'éditeur existant à partir d'une colonne logique de Données."""
        row = next((row for row, item in enumerate(self.engine.items)
                    if item.column == column), -1)
        if row >= 0:
            self.history.selectRow(row)
            self.edit_calculation(row)

    def calculation_menu(self, position):
        row = self.history.rowAt(position.y())
        item = self.item_at(row)
        if item is None:
            return
        self.history.selectRow(row)
        menu = QMenu(self)
        menu.addAction("Modifier…", lambda: self.edit_calculation(row))
        menu.addAction("Supprimer…", lambda: self.delete_calculation(row))
        menu.exec(self.history.viewport().mapToGlobal(position))

    def delete_calculation(self, row):
        item = self.item_at(row)
        if item is None:
            return
        columns = self.model.quantities_to_remove(item.column)
        message = f"Supprimer « {self.model.names[item.column]} » ?"
        if len(columns) > 1:
            message += "\n\nLes grandeurs qui en dépendent seront également supprimées :\n" + "\n".join(
                f"• {self.model.names[column]}" for column in columns if column != item.column)
        if QMessageBox.question(
                self, "Supprimer une grandeur calculée", message,
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes:
            self.model.remove_quantity(item.column)
            self.refresh()

    def suggest_derivative(self):
        source, axis = self.source.currentData(), self.axis.currentData()
        if source is None or axis is None:
            return
        self.derivative_name.setText(f"d{self.model.names[source]}/d{self.model.names[axis]}")
        self.derivative_unit.setText(derivative_unit(self.model.units[source], self.model.units[axis]))

    def insert_text(self, text):
        self.expression.insert(text)
        self.expression.setFocus()

    def insert_quantity(self):
        column = self.quantity.currentData()
        if column is not None:
            self.insert_text(quantity_reference(self.model.names, column))

    def create_derivative(self):
        self._create(self.derivative_name.text(), self.derivative_unit.text(),
                     source=self.source.currentData(), axis=self.axis.currentData())

    def create_formula(self):
        self._create(self.formula_name.text(), self.formula_unit.currentText(), expression=self.expression.text())

    def _create(self, name, unit, **definition):
        try:
            column = self.engine.add(name, unit, **definition)
        except ValueError as error:
            message = formula_error_message(error)
            self.feedback.setText(message)
            if "expression" in definition:
                QMessageBox.warning(self, "Impossible de calculer la formule", message)
                self.expression.setFocus()
            return
        self.feedback.setText(f"{self.model.names[column]} créée dans Données (C{column + 1}). "
                              "Vous pouvez y modifier son nom et son unité. " + self.engine.items[-1].status)
        if "expression" in definition:
            self.formula_name.clear()
            self.formula_unit.setCurrentText("")
            self.expression.clear()
            self.formula_name.setFocus()
