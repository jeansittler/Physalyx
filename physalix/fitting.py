"""Ajustements par moindres carrés et expressions numériques sans eval."""

import ast
from dataclasses import dataclass
import keyword
import operator
import re

import numpy as np
from scipy.optimize import least_squares


MODELS = {
    "constant": ("Constante", "c"),
    "linear": ("Linéaire", "a*x"),
    "affine": ("Affine", "a*x + b"),
    "square": ("Carrée", "a*x^2"),
    "quadratic": ("Polynôme du second degré (parabole)", "a*x^2 + b*x + c"),
    "exponential": ("Exponentielle", "A*exp(k*(x-x0)) + c"),
    "exponential_growth": (
        "Croissance exponentielle", "y_inf - (y_inf-y0)*exp(-k*(x-x0))"),
    "exponential_decay": (
        "Décroissance exponentielle", "y_inf + (y0-y_inf)*exp(-k*(x-x0))"),
    "charge": ("Charge de condensateur", "c + A*(1-exp(-(x-x0)/tau))"),
    "discharge": ("Décharge de condensateur", "c + A*exp(-(x-x0)/tau)"),
    "sine": ("Sinusoïdale", "A*sin(omega*(x-x0)+phi) + c"),
    "custom": ("Modèle utilisateur", ""),
}
FUNCTIONS = {name: getattr(np, name) for name in
             ("sin", "cos", "tan", "exp", "sqrt", "log", "log10", "abs")}
CONSTANTS = {"pi": np.pi, "e": np.e}
OPERATORS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
             ast.Div: operator.truediv, ast.Pow: operator.pow}


def parse_parameters(text, axis_name="x"):
    values = {}
    for entry in text.split(";"):
        try:
            name, raw = entry.split("=")
            name = name.strip()
            value = float(raw.strip().replace(",", "."))
        except ValueError:
            raise ValueError("Paramètres : utilisez a=1 ; b=0 ; c=0.") from None
        if (not name.isidentifier() or keyword.iskeyword(name) or name.startswith("_")
                or name in {"x", axis_name, *FUNCTIONS, *CONSTANTS} or name in values):
            raise ValueError(f"Nom de paramètre réservé, invalide ou répété : {name}.")
        if not np.isfinite(value):
            raise ValueError("Les valeurs initiales doivent être finies.")
        values[name] = value
    if not 1 <= len(values) <= 8:
        raise ValueError("Déclarez entre 1 et 8 paramètres à ajuster.")
    return values


class Expression:
    def __init__(self, text, parameters, axis_name="x"):
        if not text.strip() or len(text) > 1000:
            raise ValueError("Saisissez une expression de 1 à 1 000 caractères.")
        text = text.replace("^", "**").replace("²", "**2").replace("−", "-").replace("×", "*")
        text = re.sub(r"(?<=\d),(?=\d)", ".", text)
        try:
            self.tree = ast.parse(text, mode="eval").body
        except (SyntaxError, RecursionError):
            raise ValueError("Expression incorrecte. Exemple : a*x^2+b*x+c.") from None
        self.axis_name = axis_name
        self.parameters = list(parameters)
        allowed = {"x", axis_name, *parameters, *CONSTANTS}
        used = set()
        if len(list(ast.walk(self.tree))) > 160:
            raise ValueError("Expression trop complexe.")

        def validate(node, depth=0):
            if depth > 25:
                raise ValueError("Expression trop imbriquée.")
            if isinstance(node, ast.Constant) and type(node.value) in (int, float):
                if not np.isfinite(float(node.value)):
                    raise ValueError("Constante non finie.")
            elif isinstance(node, ast.Name) and node.id in allowed:
                used.add(node.id)
            elif isinstance(node, ast.BinOp) and type(node.op) in OPERATORS:
                validate(node.left, depth + 1)
                validate(node.right, depth + 1)
            elif isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
                validate(node.operand, depth + 1)
            elif (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                  and node.func.id in FUNCTIONS and len(node.args) == 1 and not node.keywords):
                validate(node.args[0], depth + 1)
            else:
                raise ValueError("Nom inconnu ou opération interdite : utilisez l’abscisse, les paramètres déclarés et les fonctions proposées.")
        validate(self.tree)
        if set(parameters) - used:
            raise ValueError("Paramètres absents de la formule : " + ", ".join(sorted(set(parameters) - used)))

    def __call__(self, x, *params):
        values = {**CONSTANTS, **dict(zip(self.parameters, params)), self.axis_name: x, "x": x}

        def visit(node):
            if isinstance(node, ast.Constant):
                return float(node.value)
            if isinstance(node, ast.Name):
                return values[node.id]
            if isinstance(node, ast.Call):
                return FUNCTIONS[node.func.id](visit(node.args[0]))
            if isinstance(node, ast.UnaryOp):
                result = visit(node.operand)
                return -result if isinstance(node.op, ast.USub) else result
            return OPERATORS[type(node.op)](visit(node.left), visit(node.right))
        with np.errstate(all="ignore"):
            result = np.broadcast_to(np.asarray(visit(self.tree), dtype=float), np.shape(x))
        if not np.all(np.isfinite(result)):
            raise ValueError("Le modèle est indéfini sur cet intervalle ou pour ces paramètres (log, racine, exponentielle…).")
        return result


@dataclass
class FitResult:
    parameters: dict
    formula: str
    x: np.ndarray
    y: np.ndarray
    count: int
    r_squared: float | None
    rmse: float
    residual_std: float | None
    warning: str
    x0: float | None = None


def evaluate_fit(result, x, axis_name="x"):
    """Évaluer un résultat ajusté sans relancer ni modifier l'ajustement."""
    parameters = dict(result.parameters)
    if result.x0 is not None:
        parameters["x0"] = result.x0
    expression_axis = "x" if axis_name in parameters else axis_name
    expression = Expression(result.formula, parameters, expression_axis)
    return expression(np.asarray(x, dtype=float), *parameters.values())


def fit_model(xs, ys, kind, *, expression="", initial="", axis_name="x", interval=None):
    x, y = np.asarray(xs, dtype=float), np.asarray(ys, dtype=float)
    if x.shape != y.shape or x.ndim != 1 or not np.all(np.isfinite(x)) or not np.all(np.isfinite(y)):
        raise ValueError("Les couples de mesures doivent être finis.")
    if interval is not None:
        low, high = interval
        if not np.isfinite([low, high]).all() or low >= high:
            raise ValueError("La borne minimale doit être inférieure à la borne maximale.")
        mask = (x >= low) & (x <= high)
        x, y = x[mask], y[mask]
    if not len(x):
        raise ValueError("Aucun couple de mesures dans la sélection.")
    if kind not in MODELS:
        raise ValueError("Modèle inconnu.")
    x0 = None
    warning = ""
    formula = MODELS[kind][1]
    powers = {"constant": ([0], ["c"]), "linear": ([1], ["a"]),
              "affine": ([1, 0], ["a", "b"]), "square": ([2], ["a"]),
              "quadratic": ([2, 1, 0], ["a", "b", "c"])}
    if kind in powers:
        degrees, names = powers[kind]
        if len(x) < len(names):
            raise ValueError(f"Il faut au moins {len(names)} points pour ce modèle.")
        scale = max(float(np.max(np.abs(x))), 1e-100)
        matrix = np.column_stack([(x / scale)**d for d in degrees])
        p, _, rank, _ = np.linalg.lstsq(matrix, y, rcond=None)
        if rank < len(names):
            raise ValueError("Abscisses insuffisamment distinctes : paramètres indéterminés.")
        p = p / np.array([scale**d for d in degrees])
        function = lambda xx, *pp: sum(v * xx**d for v, d in zip(pp, degrees))
    else:
        span = float(np.ptp(x))
        if span <= 0:
            raise ValueError("Il faut des abscisses distinctes.")
        x0 = float(np.min(x)) if kind != "custom" else None
        offset, amplitude = float(np.mean(y)), max(float(np.ptp(y)), 1e-6)
        bounds = (-np.inf, np.inf)
        parameter_transform = lambda values: np.asarray(values, dtype=float)
        optimizer_function = None
        if kind == "custom":
            parameters = parse_parameters(initial, axis_name)
            names = list(parameters)
            function = Expression(expression, parameters, axis_name)
            starts = [list(parameters.values())]
            formula = expression
        elif kind == "sine":
            names = ["A", "omega", "phi", "c"]
            function = lambda xx, A, omega, phi, c: A*np.sin(omega*(xx-x0)+phi)+c
            # Recherche fréquentielle avec projection linéaire, également sur un échantillonnage irrégulier.
            step = float(np.median(np.diff(np.unique(x))))
            frequencies = np.linspace(0.25/span, min(0.5/step, 30/span), 400)
            candidates = []
            for f in frequencies:
                w = 2*np.pi*f
                matrix = np.column_stack([np.sin(w*(x-x0)), np.cos(w*(x-x0)), np.ones(len(x))])
                coefficients = np.linalg.lstsq(matrix, y, rcond=None)[0]
                candidates.append((np.sum((matrix@coefficients-y)**2),
                                   [np.hypot(*coefficients[:2]), w,
                                    np.arctan2(coefficients[1], coefficients[0]), coefficients[2]]))
            starts = [p for _, p in sorted(candidates, key=lambda entry: entry[0])[:6]]
            bounds = ([-np.inf, 1e-12/span, -np.inf, -np.inf], [np.inf]*4)
        elif kind in ("exponential_growth", "exponential_decay"):
            if float(np.ptp(y)) <= np.finfo(float).eps * max(float(np.max(np.abs(y))), 1.0) * 16:
                raise ValueError("La variation des ordonnées est insuffisante pour déterminer un plateau exponentiel.")
            names = ["y_inf", "y0", "k"]
            order = np.argsort(x)
            first = float(y[order[0]])
            rates = (0.2, 0.7, 2.0, 5.0)
            deltas = (0.8*amplitude, amplitude, 1.5*amplitude, 3*amplitude)
            if kind == "exponential_growth":
                function = lambda xx, y_inf, y0, k: y_inf-(y_inf-y0)*np.exp(-k*(xx-x0))
                optimizer_function = lambda xx, y0, delta, k: y0+delta*(1-np.exp(-k*(xx-x0)))
                parameter_transform = lambda values: np.array(
                    [values[0]+values[1], values[0], values[2]], dtype=float)
                starts = [[first, delta, rate/span] for delta, rate in zip(deltas, rates)]
            else:
                function = lambda xx, y_inf, y0, k: y_inf+(y0-y_inf)*np.exp(-k*(xx-x0))
                optimizer_function = lambda xx, y_inf, delta, k: y_inf+delta*np.exp(-k*(xx-x0))
                parameter_transform = lambda values: np.array(
                    [values[0], values[0]+values[1], values[2]], dtype=float)
                starts = [[first-delta, delta, rate/span] for delta, rate in zip(deltas, rates)]
            # delta > 0 impose le sens du modèle ; k > 0 impose l'approche du plateau.
            bounds = ([-np.inf, amplitude*1e-12, 1e-12/span], [np.inf]*3)
        elif kind in ("charge", "discharge"):
            names = ["A", "tau", "c"]
            function = (lambda xx, A, tau, c: c+A*(1-np.exp(-(xx-x0)/tau))) if kind == "charge" else (
                lambda xx, A, tau, c: c+A*np.exp(-(xx-x0)/tau))
            order = np.argsort(x)
            first, last = y[order[0]], y[order[-1]]
            starts = [[last-first if kind == "charge" else first-last, span*f,
                       first if kind == "charge" else last] for f in (0.1, 0.5, 2, 10)]
            bounds = ([-np.inf, span*1e-10, -np.inf], [np.inf]*3)
        else:
            names = ["A", "k", "c"]
            function = lambda xx, A, k, c: A*np.exp(k*(xx-x0))+c
            starts = [[amplitude, k/span, offset] for k in (-5, -1, 1, 5)]
        if len(x) < len(names) or len(np.unique(x)) < len(names):
            raise ValueError(f"Il faut au moins {len(names)} abscisses distinctes pour ce modèle.")
        if optimizer_function is None:
            optimizer_function = function

        def residual(p):
            with np.errstate(all="ignore"):
                predicted = optimizer_function(x, *p)
            if not np.all(np.isfinite(predicted)):
                raise ValueError("Valeurs non finies : modifiez les paramètres initiaux ou l’intervalle.")
            return (predicted-y) / max(amplitude, abs(offset), 1e-100)

        solutions = []
        for start in starts:
            try:
                solution = least_squares(residual, start, bounds=bounds, x_scale="jac", max_nfev=2500,
                                         ftol=1e-11, xtol=1e-11, gtol=1e-11)
                if solution.success and np.isfinite(solution.cost):
                    solutions.append(solution)
            except (ValueError, ArithmeticError, np.linalg.LinAlgError):
                continue
        if not solutions:
            raise ValueError("L’ajustement n’a pas convergé. Vérifiez le domaine de la formule et les valeurs initiales.")
        best = min(solutions, key=lambda s: s.cost)
        p = parameter_transform(best.x)
        warning = "Ajustement non linéaire : un minimum local reste possible."
        if np.linalg.matrix_rank(best.jac) < len(names) or np.linalg.cond(best.jac) > 1e10:
            warning += " Paramètres mal déterminés : interprétez les coefficients avec prudence."
        if kind == "sine":
            if p[0] < 0:
                p[0], p[2] = -p[0], p[2]+np.pi
            p[2] = (p[2]+np.pi) % (2*np.pi)-np.pi
    grid = np.linspace(float(np.min(x)), float(np.max(x)), 600)
    with np.errstate(all="ignore"):
        curve = function(grid, *p)
        residuals = y-function(x, *p)
        sse = float(np.sum(residuals**2))
        total = float(np.sum((y-np.mean(y))**2))
    if not np.isfinite(p).all() or not np.isfinite(curve).all() or not np.isfinite(sse):
        raise ValueError("Résultat non fini : vérifiez l’échelle des données et le domaine du modèle.")
    n, k = len(x), len(names)
    return FitResult(dict(zip(names, map(float, p))), formula, grid, curve, n,
                     None if total == 0 else 1-sse/total, np.sqrt(sse/n),
                     np.sqrt(sse/(n-k)) if n > k else None, warning, x0)
