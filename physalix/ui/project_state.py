"""Conversion explicite de l'espace de travail en données portables."""
from dataclasses import asdict
from pathlib import Path
from tempfile import TemporaryDirectory
import zipfile

import numpy as np
from PySide6.QtCore import QPointF
from PySide6.QtWidgets import QComboBox, QLineEdit, QAbstractButton, QSpinBox, QDoubleSpinBox, QSlider
from physalix.calculations import Calculation, Formula
from physalix.fitting import FitResult
from physalix.spectrophotometry_project import (
    restore_spectrophotometry,
    snapshot_spectrophotometry,
)
from physalix.video import VideoCache
from physalix.project import IMAGE_ANALYSIS_ENTRY, MAX_IMAGE_ANALYSIS_SIZE, read_project_asset


def controls(owner):
    result = {}
    for name, widget in vars(owner).items():
        if isinstance(widget, QComboBox):
            result[name] = widget.currentIndex()
        elif isinstance(widget, QLineEdit):
            result[name] = widget.text()
        elif isinstance(widget, QAbstractButton) and widget.isCheckable():
            result[name] = widget.isChecked()
        elif isinstance(widget, (QSpinBox, QDoubleSpinBox, QSlider)):
            result[name] = widget.value()
    return result


def restore_controls(owner, values):
    # Les clés du fichier ne peuvent viser que les contrôles connus de cette page.
    for name in controls(owner):
        if name not in values:
            continue
        widget, value = vars(owner)[name], values[name]
        if isinstance(widget, QComboBox):
            if type(value) is int:
                widget.setCurrentIndex(value)
            elif isinstance(value, str):
                index = widget.findText(value)
                if index >= 0:
                    widget.setCurrentIndex(index)
                elif widget.isEditable():
                    widget.setEditText(value)
                else:
                    raise ValueError(f"Option inconnue pour {name}: {value!r}")
            else:
                raise ValueError(f"Selection invalide pour {name}: {value!r}")
        elif isinstance(widget, QLineEdit):
            widget.setText(value)
        elif isinstance(widget, QAbstractButton):
            widget.setChecked(value)
        else:
            widget.setValue(value)


def point(value):
    return [value.x(), value.y()] if value is not None else None


def snapshot(window):
    model = window.data_tab.model
    engine = window.calculations_tab.engine
    model.recalculate_cells()
    engine.recalculate()
    model.recalculate_cells()
    graphs = []
    for subwindow in window.graph_tab.windows:
        graph = subwindow.graph
        if graph._refresh_timer.isActive():
            graph._refresh_timer.stop()
            graph.sync_columns()
        entries = []
        for series in graph.series:
            fits = []
            for fit in series.fits:
                result = asdict(fit.result)
                result['x'], result['y'] = result['x'].tolist(), result['y'].tolist()
                fits.append(dict(number=fit.number, result=result, kind=fit.kind, settings=fit.settings))
            entries.append(dict(number=series.number, controls=controls(series), color=series.color.name(),
                                styles=[[list(k), list(v)] for k, v in series._styles.items()],
                                next_fit_number=series.next_fit_number, fits=fits))
        tools = {}
        for name in ('tangent_tool', 'conductimetry_tool', 'curve_guides_tool'):
            tool = getattr(graph, name)
            regions = [tool.region] if hasattr(tool, 'region') else getattr(tool, 'regions', [])
            tools[name] = dict(active=tool.active, controls=controls(tool),
                               regions=[list(r.getRegion()) for r in regions],
                               plateau_linked=getattr(tool, 'plateau_linked', False))
        graphs.append(dict(identifier=subwindow.identifier, title=subwindow.windowTitle(),
                           series=entries, controls=controls(graph),
                           modeling=controls(window.modeling_tab.pages[graph]), tools=tools,
                           view=graph.plot.viewRange(), right_view=graph.right_view.viewRange(),
                           mouse_mode=graph.plot.getViewBox().state['mouseMode'],
                           reticle=graph.reticle_action.isChecked(),
                           legend=point(graph.legend.pos()) if graph.legend.manual else None,
                           interval=list(graph.fit_region.getRegion()),
                           geometry=[subwindow.x(), subwindow.y(), subwindow.width(), subwindow.height()]))
    tracking = window.video_tab.tracking
    video = dict(tracking={name: getattr(tracking, name) for name in
                           ('x_direction', 'y_direction', 'scale', 'unit', 'length', 'columns', 'written_rows')},
                 origin=point(tracking.origin), ruler=[point(p) for p in tracking.ruler] if tracking.ruler else None,
                 points=[[i, point(p), t] for i, (p, t) in sorted(tracking.points.items())],
                 index=window.video_tab.index, controls=controls(window.video_tab))
    cache = window.video_tab.cache
    if cache:
        video['cache'] = dict(times=cache.times, width=cache.width, height=cache.height, estimated_times=cache.estimated_times)
    header = window.data_tab.table.horizontalHeader()
    return dict(table=dict(names=list(model.names), units=list(model.units), rows=[list(r) for r in model.rows],
                           formulas=[[r, c, text] for (r, c), text in sorted(model.formulas.items())],
                           order=[header.logicalIndex(i) for i in range(model.columnCount())]),
                calculations=[dict(column=c.column, kind=c.kind, source=c.source, axis=c.axis,
                                   expression=c.formula.editable_expression() if c.formula else None,
                                   automatic_unit=c.automatic_unit, previous_unit=c.previous_unit) for c in engine.items],
                graphs=graphs, arrangement=window.graph_tab.arrangement.currentIndex(),
                active_graph=next(i for i, w in enumerate(window.graph_tab.windows)
                                  if w.graph is window.graph_tab.active_graph),
                active_graph_id=next(w.identifier for w in window.graph_tab.windows
                                     if w.graph is window.graph_tab.active_graph),
                calculations_controls=controls(window.calculations_tab), statistics=controls(window.statistics_tab),
                video=video,
                spectrophotometry=snapshot_spectrophotometry(window.spectrophotometry_tab),
                image_analysis=window.image_analysis_tab.snapshot_state(),
                tab=(0 if window.tabs.currentWidget() is getattr(window, 'digitizer_tab', None)
                                  else window.tabs.currentIndex()))


def restore(window, state, path=None):
    """Restaurer dans une fenêtre de préparation ; l'original reste intact en cas d'erreur."""
    table = state['table']
    names, units, rows = table['names'], table['units'], table['rows']
    if (len(names) > 10000 or len(names) != len(units) or not rows
            or len(rows)*len(names) > 2000000
            or any(len(row) != len(names) for row in rows)
            or any(not isinstance(s, str) for s in names + units + [s for row in rows for s in row])):
        raise ValueError('Structure du tableur incorrecte.')
    model = window.data_tab.model
    model.beginResetModel()
    model.names, model.units, model.rows = list(names), list(units), [list(r) for r in rows]
    model.formulas = {}
    for r, c, expression in table.get('formulas', []):
        if not (0 <= r < len(rows) and 0 <= c < len(names)) or not isinstance(expression, str):
            raise ValueError('Référence de cellule incorrecte.')
        model.formulas[r, c] = expression
    model.endResetModel()
    engine = window.calculations_tab.engine
    for entry in state.get('calculations', []):
        entry = dict(entry)
        expression = entry.pop('expression')
        item = Calculation(**entry, formula=Formula(expression, names) if expression is not None else None)
        refs = set(item.formula.references.values()) if item.formula else {item.source, item.axis}
        if (item.kind not in ('formula', 'derivative') or item.column in model.calculated_columns
                or any(type(c) is not int or not 0 <= c < len(names) for c in refs | {item.column})):
            raise ValueError('Référence de calcul incorrecte.')
        engine.items.append(item)
        model.calculated_columns.add(item.column)
        model.column_dependencies[item.column] = refs
    engine.recalculate()
    model.recalculate_cells()
    window.calculations_tab.refresh()
    header = window.data_tab.table.horizontalHeader()
    order = table.get('order', list(range(len(names))))
    if sorted(order) != list(range(len(names))):
        raise ValueError('Ordre des colonnes incorrect.')
    for visual, logical in enumerate(order):
        header.moveSection(header.visualIndex(logical), visual)
    graphs = state.get('graphs', [])
    if not 1 <= len(graphs) <= 100:
        raise ValueError('Nombre de graphiques incorrect.')
    graph_identifiers = set()
    for index, saved in enumerate(graphs):
        identifier = saved.get('identifier')
        if identifier is not None:
            if (not isinstance(identifier, str) or not identifier or len(identifier) > 128
                    or identifier in graph_identifiers):
                raise ValueError('Identifiant de graphique incorrect.')
            graph_identifiers.add(identifier)
        if index == 0:
            subwindow = window.graph_tab.windows[0]
            if identifier is not None:
                subwindow.identifier = identifier
            graph = subwindow.graph
        else:
            graph = window.graph_tab.add_graph(identifier=identifier)
        graph.sync_columns()
        window.graph_tab.set_graph_title(window.graph_tab.windows[index], saved['title'])
        if not 1 <= len(saved['series']) <= 100:
            raise ValueError('Nombre de séries incorrect.')
        for j, entry in enumerate(saved['series']):
            series = graph.series[0] if j == 0 else graph.add_series()
            series.number = entry['number']
            for axis in ('x_choice', 'y_choice'):
                if not -1 <= entry['controls'][axis] < len(names):
                    raise ValueError('Colonne du graphique introuvable.')
            restore_controls(series, entry['controls'])
            series._styles = {tuple(k): tuple(v) for k, v in entry.get('styles', [])}
            series.set_curve_color(entry['color'])
            for fit in entry['fits']:
                result = dict(fit['result'])
                result['x'], result['y'] = np.asarray(result['x'], float), np.asarray(result['y'], float)
                if (not result['x'].size or result['x'].ndim != 1 or result['x'].shape != result['y'].shape
                        or not np.isfinite(result['x']).all() or not np.isfinite(result['y']).all()):
                    raise ValueError('Résultat de modélisation incorrect.')
                series.next_fit_number = fit['number']
                graph.set_model(series, FitResult(**result), fit['kind'], fit['settings'])
            series.next_fit_number = entry['next_fit_number']
        graph._next_number = max(s.number for s in graph.series) + 1
        graph.update_series_display_numbers()
        graph.refresh_plot()
        page = window.modeling_tab.pages[graph]
        page.sync_series()
        restore_controls(page, saved['modeling'])
        page.show_result()
        graph.fit_region.setRegion(saved['interval'])
        for name, entry in saved['tools'].items():
            if name not in ('tangent_tool', 'conductimetry_tool', 'curve_guides_tool'):
                continue
            tool = getattr(graph, name)
            if entry['active']:
                tool.open_tool('tangent') if name == 'curve_guides_tool' else tool.open_tool()
                restore_controls(tool, entry['controls'])
                regions = [tool.region] if hasattr(tool, 'region') else getattr(tool, 'regions', [])
                for region, bounds in zip(regions, entry['regions']):
                    region.setRegion(bounds)
                if entry.get('plateau_linked'):
                    tool.use_plateau()
                tool.calculate()
        restore_controls(graph, saved['controls'])
        graph.reticle_action.setChecked(saved['reticle'])
        graph.plot.getViewBox().setMouseMode(saved['mouse_mode'])
        graph._refresh_timer.stop()
    window.graph_tab.update_graph_display_numbers()
    window.graph_tab.arrangement.setCurrentIndex(state['arrangement'])
    restore_controls(window.calculations_tab, state.get('calculations_controls', {}))
    window.statistics_tab.sync()
    restore_controls(window.statistics_tab, state.get('statistics', {}))
    window.statistics_tab.calculate()
    if 'spectrophotometry' in state:
        restore_spectrophotometry(
            window.spectrophotometry_tab,
            state['spectrophotometry'],
            model.columnCount(),
        )
    if 'image_analysis' in state:
        image_state = state['image_analysis']
        image_asset = None
        if isinstance(image_state, dict) and image_state.get('image') is not None:
            if not path:
                raise ValueError("Image integree au projet manquante.")
            image_asset = read_project_asset(path, IMAGE_ANALYSIS_ENTRY, MAX_IMAGE_ANALYSIS_SIZE)
        window.image_analysis_tab.restore_state(image_state, image_asset)
    video = state.get('video', {})
    tracking = window.video_tab.tracking
    for name in ('x_direction', 'y_direction', 'scale', 'unit', 'length', 'columns', 'written_rows'):
        if name in video.get('tracking', {}):
            setattr(tracking, name, video['tracking'][name])
    tracking.origin = QPointF(*video['origin']) if video.get('origin') else None
    tracking.ruler = tuple(QPointF(*p) for p in video['ruler']) if video.get('ruler') else None
    tracking.points = {i: (QPointF(*p), t) for i, p, t in video.get('points', [])}
    tracking.normalize_legacy_unit()
    if video.get('cache'):
        metadata = video['cache']
        if not path or not metadata['times']:
            raise ValueError('Vidéo du projet manquante.')
        cache = VideoCache(TemporaryDirectory(prefix='Physalix-project-'), **metadata)
        window.video_tab.cache = cache
        with zipfile.ZipFile(path) as archive:
            size = sum(archive.getinfo(f'video/{i:09d}.png').file_size for i in range(len(cache.times)))
            if size > 4 * 1024**3:
                raise ValueError('La vidéo du projet dépasse 4 Go.')
            for i in range(len(cache.times)):
                Path(cache.path(i)).write_bytes(archive.read(f'video/{i:09d}.png'))
        window.video_tab.slider.setRange(0, len(cache.times)-1)
        window.video_tab._show_frame(min(video['index'], len(cache.times)-1))
        window.video_tab.status.setText('Vidéo intégrée au projet · Lecture sans son.')
    tab = state.get('tab', 0)
    window.tabs.setCurrentIndex(tab if type(tab) is int and 0 <= tab < window.tabs.count() else 0)
    restore_views(window, graphs, state.get('active_graph_id'), state.get('active_graph'))
    model.undo_stack.clear()


def restore_views(window, graphs, active_graph_id=None, active_graph_index=None):
    for subwindow, saved in zip(window.graph_tab.windows, graphs):
        graph = subwindow.graph
        graph._refresh_timer.stop()
        graph.plot.setRange(xRange=saved['view'][0], yRange=saved['view'][1], padding=0)
        graph.right_view.setYRange(*saved['right_view'][1], padding=0)
        if saved['legend']:
            graph.legend.manual = True
            graph.legend.setPos(*saved['legend'])
        if window.graph_tab.arrangement.currentIndex() == 3:
            subwindow.setGeometry(*saved['geometry'])
    windows = window.graph_tab.windows
    if not windows:
        return
    target = None
    if isinstance(active_graph_id, str):
        target = next((item for item in windows if item.identifier == active_graph_id), None)
    if target is None and type(active_graph_index) is int and 0 <= active_graph_index < len(windows):
        target = windows[active_graph_index]
    target = target or windows[0]
    if window.graph_tab.area.activeSubWindow() is not target:
        window.graph_tab.area.setActiveSubWindow(target)
