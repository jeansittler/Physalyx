"""Formules de cellules : analyse limitée, références A1 et recopie relative."""

import ast
import keyword
import math
import re

from physalix.calculations import CONSTANTS, FUNCTIONS


REFERENCE = r"\$?[A-Za-z]{1,5}\$?[1-9][0-9]*"
REFERENCES = re.compile(rf"(?<![\w$])({REFERENCE})(?:\s*:\s*({REFERENCE}))?(?![\w$]|\s*\()")
QUANTITY_REFERENCE = re.compile(r"\[\[Q([0-9]+)\]\]")
IDENTIFIER = re.compile(r"(?<![\w$])([^\W\d]\w*)(?![\w$])", re.UNICODE)
AGGREGATES = {"somme", "sum", "moyenne", "average", "min", "max"}


def column_label(column):
    label = ""
    while column >= 0:
        column, remainder = divmod(column, 26)
        label = chr(65 + remainder) + label
        column -= 1
    return label


def cell_position(reference):
    match = re.fullmatch(r"(\$?)([A-Za-z]+)(\$?)([1-9][0-9]*)", reference)
    column = 0
    for char in match[2].upper():
        column = column * 26 + ord(char) - 64
    return int(match[4]) - 1, column - 1


def quantity_name(names, column):
    """Nom utilisable sans ambiguïté, sinon None pour imposer le repli A1."""
    name = names[column]
    reserved = set(FUNCTIONS) | set(CONSTANTS) | AGGREGATES
    if (name and name.isidentifier() and not keyword.iskeyword(name)
            and names.count(name) == 1 and name.lower() not in reserved
            and not re.fullmatch(REFERENCE, name)):
        return name
    return None


def canonicalize_formula(expression, names):
    """Remplacer les noms scientifiques par des références de colonnes stables."""
    expression = expression.replace("²", "^2").replace("³", "^3")
    def replace_identifier(match):
        name = match[1]
        if expression[max(0, match.start() - 2):match.start()] == "[[" and expression[match.end():match.end() + 2] == "]]":
            return name
        if re.fullmatch(REFERENCE, name):
            return name
        tail = expression[match.end():]
        if tail.lstrip().startswith("("):
            return name
        matches = [column for column, candidate in enumerate(names) if candidate == name]
        if len(matches) > 1:
            raise ValueError(
                f"Le nom « {name} » correspond à plusieurs grandeurs. Utilisez une référence A1.")
        if len(matches) == 1:
            if quantity_name(names, matches[0]) is None:
                raise ValueError(
                    f"Le nom « {name} » est réservé ou ambigu. Utilisez une référence A1.")
            return f"[[Q{matches[0]}]]"
        if name.lower() in CONSTANTS:
            return name
        return name
    return IDENTIFIER.sub(replace_identifier, expression)


def display_formula(expression, names, row):
    """Afficher les noms actuels, avec une adresse A1 sûre comme solution de repli."""
    def replace(match):
        column = int(match[1])
        if not 0 <= column < len(names):
            return "#REF!"
        return quantity_name(names, column) or f"{column_label(column)}{row + 1}"
    return QUANTITY_REFERENCE.sub(replace, expression)


def translate_formula(expression, rows=0, columns=0):
    def translate(reference):
        match = re.fullmatch(r"(\$?)([A-Za-z]+)(\$?)([1-9][0-9]*)", reference)
        row, column = cell_position(reference)
        row += 0 if match[3] else rows
        column += 0 if match[1] else columns
        if min(row, column) < 0:
            return "#REF!"
        return f"{match[1]}{column_label(column)}{match[3]}{row + 1}"
    return REFERENCES.sub(lambda m: translate(m[1]) + (":" + translate(m[2]) if m[2] else ""), expression)


def remove_formula_column(expression, removed):
    def replace(match):
        def shift(reference):
            row, column = cell_position(reference)
            if column == removed:
                return "#REF!"
            parts = re.fullmatch(r"(\$?)([A-Za-z]+)(\$?)([1-9][0-9]*)", reference)
            return f"{parts[1]}{column_label(column - (column > removed))}{parts[3]}{row + 1}"
        return shift(match[1]) + (":" + shift(match[2]) if match[2] else "")
    expression = REFERENCES.sub(replace, expression)
    def remove_quantity(match):
        column = int(match[1])
        if column == removed:
            return "#REF!"
        return f"[[Q{column - (column > removed)}]]"
    return QUANTITY_REFERENCE.sub(remove_quantity, expression)


class CellError(ValueError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


class CellFormula:
    def __init__(self, text, names=None, current_row=None):
        if len(text) > 2000:
            raise ValueError("Formule trop longue (2 000 caractères maximum).")
        self.canonical_text = canonicalize_formula(text, names) if names is not None else text
        text = self.canonical_text
        if "#REF!" in text:
            raise CellError("#REF!", "La formule désigne une cellule supprimée ou une référence hors tableau.")
        self.references = {}
        def reference(match):
            start = cell_position(match[1])
            end = cell_position(match[2]) if match[2] else None
            if end and (abs(end[0] - start[0]) + 1) * (abs(end[1] - start[1]) + 1) > 10000:
                raise ValueError("Une plage est limitée à 10 000 cellules.")
            name = f"ref_{len(self.references)}"
            self.references[name] = (start, end)
            return name
        if re.search(r"(?<!\w)ref_[0-9]+(?!\w)", text):
            raise ValueError("Identifiant non autorisé.")
        def quantity_reference(match):
            column = int(match[1])
            if names is not None and not 0 <= column < len(names):
                raise CellError("#REF!", "La grandeur référencée n'existe plus dans le tableau.")
            if current_row is None:
                raise ValueError("La ligne de la formule est nécessaire pour résoudre une grandeur.")
            name = f"ref_{len(self.references)}"
            self.references[name] = ((current_row, column), None)
            return name
        expression = QUANTITY_REFERENCE.sub(quantity_reference, text[1:])
        expression = REFERENCES.sub(reference, expression)
        expression = expression.replace("^", "**").replace("²", "**2").replace("³", "**3")
        expression = expression.replace("×", "*").replace("÷", "/").replace("−", "-")
        expression = re.sub(r"(?<=\d),(?=\d)", ".", expression).replace(";", ",")
        try:
            self.tree = ast.parse(expression.strip(), mode="eval").body
        except (SyntaxError, RecursionError):
            raise ValueError("Formule incorrecte. Exemple : =A1*2 ou =SOMME(A1:A5).") from None
        if len(list(ast.walk(self.tree))) > 200:
            raise ValueError("Formule trop complexe.")
        self.functions = dict(FUNCTIONS, racine=math.sqrt, ln=math.log)
        self.aggregates = AGGREGATES
        def validate(node, depth=0):
            if depth > 30:
                raise ValueError("Trop de parenthèses imbriquées.")
            if isinstance(node, ast.Constant) and type(node.value) in (int, float):
                if not math.isfinite(float(node.value)):
                    raise ValueError("Nombre non fini.")
            elif isinstance(node, ast.Name):
                if node.id in self.references or node.id.lower() in CONSTANTS:
                    pass
                else:
                    raise ValueError(f"La grandeur « {node.id} » n'existe pas dans le tableau.")
            elif isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Pow)):
                validate(node.left, depth + 1)
                validate(node.right, depth + 1)
            elif isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
                validate(node.operand, depth + 1)
            elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and not node.keywords:
                name = node.func.id.lower()
                if not ((name in self.functions and len(node.args) == 1) or (name in self.aggregates and node.args)):
                    raise ValueError("Fonction inconnue ou nombre d'arguments incorrect.")
                for arg in node.args:
                    validate(arg, depth + 1)
            else:
                raise ValueError("Utilisez les références A1, +, −, *, /, ^ et les fonctions mathématiques.")
        validate(self.tree)

    def evaluate(self, resolve):
        def visit(node):
            if isinstance(node, ast.Constant):
                return float(node.value)
            if isinstance(node, ast.Name):
                if node.id not in self.references:
                    return math.pi if node.id.lower() == "pi" else math.e
                start, end = self.references[node.id]
                if end is None:
                    return resolve(*start)
                return [resolve(r, c) for r in range(min(start[0], end[0]), max(start[0], end[0]) + 1)
                        for c in range(min(start[1], end[1]), max(start[1], end[1]) + 1)
                        if not getattr(resolve, "is_blank", lambda r, c: False)(r, c)]
            if isinstance(node, ast.UnaryOp):
                value = visit(node.operand)
                return -value if isinstance(node.op, ast.USub) else +value
            if isinstance(node, ast.Call):
                name = node.func.id.lower()
                args = [visit(arg) for arg in node.args]
                if name in self.functions:
                    return self.functions[name](*args)
                values = [v for arg in args for v in (arg if isinstance(arg, list) else [arg])]
                if name in ("somme", "sum"):
                    return sum(values)
                if name in ("moyenne", "average"):
                    return sum(values) / len(values)
                return min(values) if name == "min" else max(values)
            left, right = visit(node.left), visit(node.right)
            if isinstance(node.op, ast.Add): return left + right
            if isinstance(node.op, ast.Sub): return left - right
            if isinstance(node.op, ast.Mult): return left * right
            if isinstance(node.op, ast.Div): return left / right
            if abs(right) > 100:
                raise ValueError("Exposant limité à −100…100.")
            return math.pow(left, right)
        value = visit(self.tree)
        if not isinstance(value, (float, int)) or not math.isfinite(value):
            raise ValueError("Le résultat doit être un nombre fini.")
        return value


def calculation_expression_from_cell(text, names, current_row):
    """Traduire une formule strictement mono-ligne vers les références de Calculs."""
    canonical = CellFormula(text, names, current_row).canonical_text
    quantities = []

    def mask_quantity(match):
        placeholder = f"__physalix_quantity_{len(quantities)}__"
        quantities.append((placeholder, int(match[1])))
        return placeholder

    canonical = QUANTITY_REFERENCE.sub(mask_quantity, canonical)

    def explicit_reference(match):
        if match[2] is not None:
            raise ValueError(
                "Cette formule utilise une plage de cellules. Elle peut être recopiée, "
                "mais pas appliquée directement à toute la grandeur.")
        parts = re.fullmatch(r"(\$?)([A-Za-z]+)(\$?)([1-9][0-9]*)", match[1])
        row, column = cell_position(match[1])
        if parts[3] or row != current_row:
            raise ValueError(
                "Cette formule utilise des valeurs de plusieurs lignes. Elle peut être "
                "recopiée dans le tableur, mais pas appliquée directement à toute la grandeur.")
        return f"C{column + 1}"

    expression = REFERENCES.sub(explicit_reference, canonical)
    for placeholder, column in quantities:
        expression = expression.replace(placeholder, f"C{column + 1}")
    return expression[1:]
