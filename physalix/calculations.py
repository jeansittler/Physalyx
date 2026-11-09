"""Calculs liés aux colonnes : expressions limitées et différences centrées."""

import ast
import copy
from dataclasses import dataclass
import keyword
import math
import re

from PySide6.QtCore import QObject, QTimer, Qt, Signal


FUNCTIONS = {name: getattr(math, name) for name in ("sqrt", "sin", "cos", "tan", "exp", "log", "log10")}
FUNCTIONS["abs"] = abs
FUNCTIONS.update(ln=math.log, log=math.log10, racine=math.sqrt)
CONSTANTS = {"pi": math.pi, "e": math.e}


class FormulaError(ValueError):
    """Erreur de formule classée, destinée à un message pédagogique."""

    def __init__(self, kind, message):
        super().__init__(message)
        self.kind = kind


def quantity_reference(names, column):
    """Nom saisissable sans ambiguïté, sinon référence de compatibilité stable."""
    name = names[column]
    if (name and name.isidentifier() and not keyword.iskeyword(name)
            and names.count(name) == 1 and not re.fullmatch(r"C[1-9][0-9]*", name)):
        return name
    return f"C{column + 1}"


def number(text):
    try:
        value = float(text.replace(",", "."))
        return value if math.isfinite(value) else None
    except (ValueError, TypeError):
        return None


class Formula:
    """Valider chaque nœud ; ne jamais exécuter du code saisi par l'utilisateur."""

    def __init__(self, expression, names):
        if not expression.strip() or len(expression) > 2000:
            raise FormulaError("syntax", "Saisissez une formule de 1 à 2 000 caractères.")
        expression = expression.replace("^", "**").replace("²", "**2").replace("³", "**3")
        expression = expression.replace("×", "*").replace("÷", "/").replace("−", "-")
        expression = re.sub(r"(?<=\d),(?=\d)", ".", expression)
        try:
            self.tree = ast.parse(expression, mode="eval").body
        except (SyntaxError, RecursionError):
            raise FormulaError("syntax", "La syntaxe de la formule est incorrecte. Exemple : sqrt(vx^2 + vy^2).") from None
        if len(list(ast.walk(self.tree))) > 200:
            raise ValueError("Cette formule est trop longue.")
        self.references = {}

        def validate(node, depth=0):
            if depth > 30:
                raise ValueError("Trop de parenthèses imbriquées.")
            if isinstance(node, ast.Constant) and type(node.value) in (int, float):
                try:
                    valid = math.isfinite(float(node.value))
                except OverflowError:
                    valid = False
                if not valid:
                    raise ValueError("Les constantes doivent être des nombres finis.")
            elif isinstance(node, ast.Name):
                alias = re.fullmatch(r"C([1-9][0-9]*)", node.id)
                matches = [i for i, name in enumerate(names) if name == node.id]
                if alias:
                    column = int(alias[1]) - 1
                    if column >= len(names):
                        raise FormulaError("unknown_quantity", f"La référence {node.id} n’existe pas dans le tableau.")
                    self.references[node.id] = column
                elif len(matches) == 1:
                    self.references[node.id] = matches[0]
                elif len(matches) > 1:
                    raise FormulaError("ambiguous", f"Le nom « {node.id} » correspond à plusieurs grandeurs. Utilisez la liste d’insertion pour choisir la bonne.")
                elif node.id.lower() not in CONSTANTS:
                    raise FormulaError("unknown_quantity", f"La grandeur « {node.id} » n’existe pas dans le tableau.")
            elif isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Pow)):
                validate(node.left, depth + 1)
                validate(node.right, depth + 1)
            elif isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
                validate(node.operand, depth + 1)
            elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                if node.func.id.lower() not in FUNCTIONS:
                    raise FormulaError("unknown_function", f"La fonction « {node.func.id} » n’est pas reconnue.")
                if len(node.args) != 1 or node.keywords:
                    raise FormulaError("syntax", f"La fonction « {node.func.id} » attend une seule valeur entre parenthèses.")
                validate(node.args[0], depth + 1)
            else:
                raise ValueError("Opération non autorisée. Utilisez +, −, *, /, ^ et les fonctions proposées.")

        validate(self.tree)

    def evaluate(self, row):
        def visit(node):
            if isinstance(node, ast.Constant):
                return float(node.value)
            if isinstance(node, ast.Name):
                if node.id not in self.references:
                    return CONSTANTS[node.id.lower()]
                value = number(row[self.references[node.id]])
                if value is None:
                    raise ValueError("donnée absente ou non numérique")
                return value
            if isinstance(node, ast.UnaryOp):
                value = visit(node.operand)
                return -value if isinstance(node.op, ast.USub) else value
            if isinstance(node, ast.Call):
                return FUNCTIONS[node.func.id.lower()](visit(node.args[0]))
            left, right = visit(node.left), visit(node.right)
            if isinstance(node.op, ast.Add):
                return left + right
            if isinstance(node.op, ast.Sub):
                return left - right
            if isinstance(node.op, ast.Mult):
                return left * right
            if isinstance(node.op, ast.Div):
                return left / right
            if abs(right) > 100:
                raise ValueError("exposant hors limite (−100 à 100)")
            return math.pow(left, right)

        result = visit(self.tree)
        if not math.isfinite(result):
            raise ValueError("résultat non fini")
        return result

    def description(self, names):
        references = self.references
        placeholders = {}

        class DisplayNames(ast.NodeTransformer):
            def visit_Name(self, node):
                if node.id in references:
                    placeholder = f"__physalix_quantity_{references[node.id]}"
                    placeholders[placeholder] = names[references[node.id]] or f"C{references[node.id] + 1}"
                    return ast.copy_location(ast.Name(id=placeholder, ctx=ast.Load()), node)
                return node

            def visit_Call(self, node):
                node.args = [self.visit(arg) for arg in node.args]
                return node

        expression = ast.unparse(DisplayNames().visit(copy.deepcopy(self.tree)))
        for placeholder, name in placeholders.items():
            expression = expression.replace(placeholder, name)
        return expression.replace("**", "^")

    def editable_expression(self, names=None):
        """Afficher les noms actuels ; sans noms, produire les références stables du projet."""
        references = self.references

        class ColumnAliases(ast.NodeTransformer):
            def visit_Name(self, node):
                if node.id in references:
                    column = references[node.id]
                    token = quantity_reference(names, column) if names is not None else f"C{column + 1}"
                    return ast.copy_location(ast.Name(id=token, ctx=ast.Load()), node)
                return node

            def visit_Call(self, node):
                # Le nom d'une fonction peut aussi être celui d'une grandeur.
                node.args = [self.visit(arg) for arg in node.args]
                return node

        tree = ColumnAliases().visit(copy.deepcopy(self.tree))
        return ast.unparse(tree).replace("**", "^")


def derivative_unit(numerator, denominator):
    if not numerator or not denominator:
        return ""
    if numerator == denominator:
        return "Sans unité"
    if numerator.endswith("/" + denominator):
        return numerator + "²"
    if "/" in numerator:
        return f"({numerator})/{denominator}"
    return f"{numerator}/{denominator}"


@dataclass
class Calculation:
    column: int
    kind: str
    source: int | None = None
    axis: int | None = None
    formula: Formula | None = None
    status: str = ""
    automatic_unit: bool = False
    previous_unit: str = ""


class CalculationEngine(QObject):
    changed = Signal()

    def __init__(self, model):
        super().__init__(model)
        self.model = model
        self.items = []
        model.calculation_engine = self
        self.busy = False
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.recalculate)
        for signal in (model.dataChanged, model.rowsInserted, model.columnsInserted):
            signal.connect(self.schedule)
        model.columnsRemoved.connect(self.columns_removed)

    def columns_removed(self, parent, first, last):
        count = last - first + 1
        self.items = [item for item in self.items if not first <= item.column <= last]
        for item in self.items:
            item.column -= count if item.column > last else 0
            if item.formula:
                item.formula.references = {name: c - (count if c > last else 0)
                                           for name, c in item.formula.references.items()}
            else:
                item.source -= count if item.source > last else 0
                item.axis -= count if item.axis > last else 0
        self.schedule()

    def schedule(self, *args):
        if not self.busy:
            self.timer.start(0)

    def add(self, name, unit, *, source=None, axis=None, expression=None):
        name = name.strip()
        if not name:
            raise ValueError("Donnez un nom à la nouvelle grandeur.")
        if name in self.model.names:
            raise ValueError("Ce nom existe déjà. Choisissez un autre nom pour la nouvelle grandeur.")
        formula = Formula(expression, self.model.names) if expression is not None else None
        if formula is not None:
            references = set(formula.references.values())
            base_columns = set(range(self.model.columnCount())) - self.model.calculated_columns
            candidates = valid = 0
            for row in self.model.rows:
                if references:
                    if any(number(row[column]) is None for column in references):
                        continue
                elif not any(row[column] for column in base_columns):
                    continue
                candidates += 1
                try:
                    formula.evaluate(row)
                    valid += 1
                except (ArithmeticError, ValueError):
                    pass
            if candidates and not valid:
                raise FormulaError(
                    "math",
                    "La formule est mathématiquement impossible pour toutes les lignes numériques du tableau.",
                )
        if formula is None and (source is None or axis is None or source == axis
                                or not 0 <= source < self.model.columnCount()
                                or not 0 <= axis < self.model.columnCount()):
            raise ValueError("Choisissez deux grandeurs distinctes à dériver et en abscisse.")
        self.busy = True
        try:
            column = self.model.columnCount()
            self.model.add_quantity()
            self.model.calculated_columns.add(column)
            self.model.setData(self.model.index(0, column), name)
            self.model.setData(self.model.index(1, column), unit)
            item = Calculation(column, "formula" if formula else "derivative", source, axis, formula)
            item.previous_unit = unit.strip()
            item.automatic_unit = formula is None and unit.strip() == derivative_unit(self.model.units[source], self.model.units[axis])
            self.items.append(item)
            self.model.column_dependencies[column] = (set(formula.references.values()) if formula
                                                       else {source, axis})
        finally:
            self.busy = False
        self.recalculate()
        return column

    def ordered_items(self, dependencies=None):
        """Calculer les sources avant leurs dépendants, sans changer l'ordre affiché."""
        dependencies = self.model.column_dependencies if dependencies is None else dependencies
        pending = list(self.items)
        ordered = []
        while pending:
            columns = {item.column for item in pending}
            ready = [item for item in pending if not dependencies.get(item.column, set()) & columns]
            if not ready:
                raise FormulaError("circular", "Cette formule crée une dépendance circulaire : une grandeur ne peut pas dépendre d’elle-même, directement ou indirectement.")
            ordered.extend(ready)
            ready_columns = {item.column for item in ready}
            pending = [item for item in pending if item.column not in ready_columns]
        return ordered

    def update_formula(self, column, expression):
        item = next((item for item in self.items if item.column == column and item.formula is not None), None)
        if item is None:
            raise ValueError("Cette grandeur n’est plus disponible ou n’est pas définie par une formule.")
        formula = Formula(expression, self.model.names)
        dependencies = dict(self.model.column_dependencies)
        dependencies[column] = set(formula.references.values())
        self.ordered_items(dependencies)  # Tout valider avant de remplacer le calcul.
        item.formula = formula
        self.model.column_dependencies[column] = dependencies[column]
        self.recalculate()

    def update_derivative(self, column, name, unit, source, axis):
        item = next((entry for entry in self.items
                     if entry.column == column and entry.formula is None), None)
        if item is None:
            raise ValueError("Cette grandeur dérivée n’est plus disponible.")
        name = name.strip()
        if not name:
            raise ValueError("Donnez un nom à la grandeur dérivée.")
        if any(i != column and existing == name for i, existing in enumerate(self.model.names)):
            raise ValueError("Ce nom existe déjà. Choisissez un autre nom.")
        if (source is None or axis is None or source == axis
                or not 0 <= source < self.model.columnCount()
                or not 0 <= axis < self.model.columnCount()):
            raise ValueError("Choisissez deux grandeurs distinctes à dériver et en abscisse.")
        dependencies = dict(self.model.column_dependencies)
        dependencies[column] = {source, axis}
        self.ordered_items(dependencies)
        self.busy = True
        try:
            self.model.setData(self.model.index(0, column), name)
            self.model.setData(self.model.index(1, column), unit)
            item.source, item.axis = source, axis
            item.previous_unit = unit.strip()
            item.automatic_unit = unit.strip() == derivative_unit(
                self.model.units[source], self.model.units[axis])
            self.model.column_dependencies[column] = dependencies[column]
        finally:
            self.busy = False
        self.recalculate()

    def recalculate(self):
        self.timer.stop()
        if self.busy:
            return
        self.busy = True
        try:
            rows = self.model.rows
            for item in self.ordered_items():
                if item.automatic_unit:
                    if self.model.units[item.column] != item.previous_unit:
                        item.automatic_unit = False
                    else:
                        unit = derivative_unit(self.model.units[item.source], self.model.units[item.axis])
                        if unit != item.previous_unit:
                            self.model.setData(self.model.index(1, item.column), unit)
                            item.previous_unit = unit
                values = [""] * len(rows)
                valid = missing = invalid = variable = 0
                if item.formula:
                    refs = set(item.formula.references.values())
                    # Une constante s'applique seulement aux lignes de données existantes.
                    relevant = refs or (set(range(self.model.columnCount())) - self.model.calculated_columns)
                    for i, row in enumerate(rows):
                        if not any(row[c] for c in relevant):
                            continue
                        if any(number(row[c]) is None for c in refs):
                            missing += 1
                            continue
                        try:
                            result = item.formula.evaluate(row)
                            values[i] = format(result, ".12g")
                            valid += 1
                        except (ArithmeticError, ValueError):
                            invalid += 1
                    item.status = f"{valid} valeur(s) · {missing} incomplète(s) · {invalid} erreur(s) de calcul"
                else:
                    for i in range(1, len(rows) - 1):
                        triplet = [(number(rows[j][item.source]), number(rows[j][item.axis]))
                                   for j in (i - 1, i, i + 1)]
                        if any(a is None or b is None for a, b in triplet):
                            continue
                        (left, t0), (_, t1), (right, t2) = triplet
                        dt1, dt2 = t1 - t0, t2 - t1
                        if not (dt1 > 0 and dt2 > 0 or dt1 < 0 and dt2 < 0):
                            invalid += 1
                            continue
                        result = (right - left) / (t2 - t0)
                        if not math.isfinite(result):
                            invalid += 1
                            continue
                        if not math.isclose(dt1, dt2, rel_tol=1e-6, abs_tol=1e-12):
                            variable += 1
                        values[i] = format(result, ".12g")
                        valid += 1
                    item.status = f"{valid} valeur(s) · extrémités et voisinages incomplets vides · {invalid} intervalle(s) invalide(s)"
                    if variable:
                        item.status += f" · {variable} pas variable(s) : pente entre voisins"
                if any(row[item.column] != value for row, value in zip(rows, values)):
                    for row, value in zip(rows, values):
                        row[item.column] = value
                    self.model.dataChanged.emit(self.model.index(2, item.column),
                                                self.model.index(len(rows) + 1, item.column),
                                                [Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.EditRole])
        finally:
            self.busy = False
        self.changed.emit()
