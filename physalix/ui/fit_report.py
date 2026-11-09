"""Présentation lisible des résultats, indépendante du calcul d’ajustement."""

from html import escape
import re


def number(value):
    return format(value, '.6g').replace('.', ',').replace('-', '−')


def math_text(expression):
    text = escape(expression).replace('**', '^')
    text = re.sub(r'\^(\d+)', r'<sup>\1</sup>', text)
    text = re.sub(r'\b(y_inf|y0|tau|omega|phi|x0)\b',
                  lambda m: {'y_inf': 'y<sub>∞</sub>', 'y0': 'y<sub>0</sub>',
                             'tau': 'τ', 'omega': 'ω', 'phi': 'φ',
                             'x0': 'x<sub>0</sub>'}[m[0]], text)
    return text.replace('*', ' · ').replace('-', '−')


def fitted_equation(result, x_symbol="x"):
    """Return the fitted right-hand side in a compact, plain-text form."""
    polynomials = {'c': [('c', '')], 'a*x': [('a', x_symbol)],
                   'a*x + b': [('a', x_symbol), ('b', '')],
                   'a*x^2': [('a', x_symbol + '²')],
                   'a*x^2 + b*x + c': [('a', x_symbol + '²'), ('b', x_symbol), ('c', '')]}
    if result.formula in polynomials:
        terms = []
        for key, factor in polynomials[result.formula]:
            value = result.parameters[key]
            sign = ('− ' if value < 0 else '') if not terms else (' − ' if value < 0 else ' + ')
            terms.append(sign + number(abs(value)) + (' · ' + factor if factor else ''))
        return ''.join(terms)
    fitted = re.sub(r'\b[^\W\d]\w*\b', lambda match: (
        '(' + number(result.parameters[match[0]]) + ')' if match[0] in result.parameters
        else match[0]), result.formula)
    return re.sub(r'\bx\b', x_symbol, fitted).replace('**', '^').replace('*', ' · ').replace('-', '−')


def report_html(result, series_title, x_name, x_label, y_name, unit):
    """Échapper tous les noms et formules issus du tableau utilisateur."""
    unit = '' if unit == 'Sans unité' else unit
    suffix = (' ' + escape(unit)) if unit else ''
    x_symbol = x_name or 'x'
    fitted = fitted_equation(result, x_symbol)
    display_formula = re.sub(r'\bx\b', x_symbol, result.formula)
    rows = ''.join(
        f'<tr><td width="100"><b>{math_text(name)}</b></td><td>{number(value)}</td></tr>'
        for name, value in result.parameters.items())
    r2 = 'Non défini' if result.r_squared is None else number(result.r_squared)
    r2_help = ('Les ordonnées sont toutes identiques : R² ne permet pas de comparer les écarts.'
               if result.r_squared is None else
               'Le modèle fait moins bien qu’une droite horizontale placée à la moyenne des mesures.'
               if result.r_squared < 0 else
               'Plus R² est proche de 1, mieux la courbe reproduit les variations des mesures. '
               'Ce nombre n’est pas un pourcentage de précision.')
    std = 'Non défini' if result.residual_std is None else number(result.residual_std) + suffix
    std_help = ('Il faut davantage de points que de paramètres pour calculer cet indicateur.'
                if result.residual_std is None else
                'Dispersion des écarts, corrigée pour tenir compte du nombre de paramètres ajustés.')
    metrics = [
        ('Accord avec les mesures', 'R² = ' + r2, r2_help),
        ('Écart aux mesures · RMSE', number(result.rmse) + suffix,
         'Taille typique de l’écart vertical entre un point mesuré et la courbe. Plus cette valeur est petite, plus les points sont proches de la courbe.'),
        ('Écart type résiduel', std, std_help),
    ]
    metric_cells = ''.join(f'<td width="33%" class="metric-card"><b>{title}</b><br>'
                           f'<span class="metric">{value}</span></td>'
                           for title, value, explanation in metrics)
    metric_notes = ' '.join(
        explanation for title, value, explanation in metrics
        if value == 'Non défini' or (title == 'Accord avec les mesures'
                                     and result.r_squared is not None and result.r_squared < 0)
    )
    origin = (f'<p>Origine fixée : x<sub>0</sub> = {number(result.x0)} '
              '(première abscisse utilisée, non ajustée).</p>' if result.x0 is not None else '')
    warning = f'<p>{escape(result.warning)}</p>' if result.warning else ''
    return f'''<html><body>
        <div class="summary"><b>{escape(series_title)}</b><br>{result.count} points utilisés ·
        intervalle de {number(result.x[0])} à {number(result.x[-1])}</div>
        <div class="equation-card"><span class="eyebrow">ÉQUATION OBTENUE</span><br>
        <span class="equation"><b>{escape(y_name or 'Y')} = {math_text(fitted)}</b></span><br>
        <span>Forme du modèle : {math_text(display_formula)} · Abscisse : {escape(x_label)}</span></div>
        <h3>Coefficients</h3>
        <table class="coefficients" width="100%" cellpadding="5" cellspacing="0">{rows}</table>
        <p>Valeurs arrondies à 6 chiffres significatifs ; le calcul conserve toute sa précision.
        Les unités des coefficients dépendent des unités des axes.</p>
        {origin}
        <h3>Qualité de la modélisation</h3>
        <table width="100%" cellpadding="0" cellspacing="6"><tr>{metric_cells}</tr></table>
        <p>{metric_notes}</p>
        <p>Ces indicateurs décrivent les écarts aux mesures. Le choix du modèle doit aussi être cohérent avec le phénomène étudié.</p>
        {warning}
        <p>La courbe obtenue est visible en pointillés dans l’onglet Graphique.</p>
        </body></html>'''


DETAILS_HTML = '''<h3>Comment sont calculés ces indicateurs ?</h3>
<p><b>Un résidu</b> est l’écart vertical entre une mesure et le modèle :<br>
résidu = valeur mesurée − valeur prédite, pour la même abscisse.</p>
<p><b>R² : comparer le modèle à la moyenne</b><br>
1. On additionne les carrés des résidus du modèle : on obtient E.<br>
2. On remplace le modèle par la moyenne des ordonnées et on refait le calcul : on obtient E<sub>0</sub>.<br>
3. R² = 1 − E / E<sub>0</sub>.<br>
R² = 1 : aucun écart. R² = 0 : même somme des écarts au carré que la moyenne.
R² &lt; 0 : le modèle fait moins bien que la moyenne. Si E<sub>0</sub> = 0, R² est indéfini.</p>
<p><b>RMSE : mesurer la taille des écarts</b><br>
On prend la moyenne des carrés des résidus, puis sa racine carrée : RMSE = √(E / n).</p>
<p><b>Écart type résiduel : tenir compte des paramètres ajustés</b><br>
On divise E par n − p, puis on prend la racine carrée : s = √(E / (n − p)).<br>
n est le nombre de points utilisés et p le nombre de paramètres ajustés. Il faut n &gt; p.</p>
<p>La RMSE et l’écart type résiduel sont exprimés dans l’unité de l’ordonnée.
Toutes les mesures ont le même poids dans cette modélisation.</p>'''
