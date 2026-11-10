"""Sauvegardes réelles, liens recalculables et échanges CSV."""
import gc
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import tempfile
import json
from pathlib import Path
import unittest
from unittest.mock import MagicMock, patch
import zipfile

from PySide6.QtCore import QEvent, QPointF, QTimer
from PySide6.QtWidgets import QApplication, QMessageBox, QFileDialog
from physalix.app import main as app_main, project_path_from_arguments
from physalix.acquisition import AcquisitionConfig, DigitalStepConfig
from physalix.fitting import fit_model
from physalix.project import read_project, write_project, read_csv, write_csv, atomic_write
from physalix.ui.main_window import MainWindow
from physalix.ui.project_state import snapshot, restore


class ProjectTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.window = MainWindow()
        self.windows = [self.window]
        self.directory = tempfile.TemporaryDirectory()
        self.path = Path(self.directory.name) / 'expérience.physalix'

    def tearDown(self):
        for window in self.windows:
            window._discard_on_close = True
            window.close()
            window.deleteLater()
        QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.app.processEvents()
        gc.collect()
        self.directory.cleanup()

    def populated(self):
        w = self.window
        m = w.data_tab.model
        for r, row in enumerate([['0', '1'], ['1', '3'], ['2', '5'], ['3', '7']]):
            for c, value in enumerate(row):
                m.setData(m.index(r+2, c), value)
        w.calculations_tab.engine.add('double', 'V', expression='C2*2')
        w.calculations_tab.engine.add('pente', 'V/s', source=1, axis=0)
        m.add_quantity()
        m.setData(m.index(2, 4), '=B1+1')
        g = w.graph_tab.active_graph
        g.set_model(g.series[0], fit_model([0,1,2,3], [1,3,5,7], 'affine'), 'affine', {'extend': True})
        second_fit = g.set_model(
            g.series[0], fit_model([0,1,2,3], [1,3,5,7], 'linear'), 'linear',
            {'interval': [0, 3]},
        )
        w.modeling_tab.sync_fits(selected=second_fit.number)
        second = w.graph_tab.add_graph()
        second.series[0].y_choice.setCurrentIndex(2)
        second.series[0].y_axis.setCurrentIndex(1)
        second.series[0].connect_points.setChecked(True)
        second.series[0].set_curve_color('#123456')
        w.graph_tab.windows[1].setWindowTitle('Tension doublée')
        w.data_tab.table.horizontalHeader().moveSection(2, 0)
        self.app.processEvents()
        return w

    def test_roundtrip_and_live_calculations(self):
        w = self.populated()
        state = snapshot(w)
        write_project(self.path, state)
        v = MainWindow()
        self.windows.append(v)
        restore(v, read_project(self.path), self.path)
        self.app.processEvents()
        self.assertEqual(len(v.graph_tab.windows), 2)
        self.assertEqual(v.graph_tab.windows[1].windowTitle(), 'Tension doublée')
        self.assertEqual(v.data_tab.model.rows, w.data_tab.model.rows)
        self.assertEqual(v.data_tab.model.formulas, {(0, 4): '=B1+1'})
        calculations = v.calculations_tab.engine.items
        self.assertEqual(calculations[0].formula.editable_expression(), "C2 * 2")
        self.assertEqual(calculations[0].formula.editable_expression(v.data_tab.model.names), "y * 2")
        self.assertEqual((calculations[1].kind, calculations[1].source, calculations[1].axis),
                         ('derivative', 1, 0))
        first = v.graph_tab.windows[0].graph
        self.assertEqual(len(first.series[0].fits), 2)
        self.assertAlmostEqual(first.series[0].fits[0].result.parameters['a'], 2)
        self.assertEqual(first.series[0].fits[1].kind, 'linear')
        restored_modeling = v.modeling_tab.pages[first]
        self.assertEqual(restored_modeling.fits_list.count(), 2)
        self.assertEqual(restored_modeling.current_fit().number, first.series[0].fits[1].number)
        second = v.graph_tab.windows[1].graph
        self.assertEqual(second.series[0].color.name(), '#123456')
        self.assertEqual(second.series[0].y_axis.currentIndex(), 1)
        self.assertTrue(second.series[0].connect_points.isChecked())
        self.assertEqual(v.data_tab.table.horizontalHeader().logicalIndex(0), 2)
        m = v.data_tab.model
        m.setData(m.index(2, 1), '10')
        self.app.processEvents()
        self.assertEqual(m.rows[0][2], '20')
        self.assertEqual(m.rows[0][4], '11')
        self.assertFalse(first.series[0].fits)  # Invalidation normale après modification des mesures.

    def test_active_graph_is_restored_by_stable_identifier_after_reopening(self):
        source = self.populated()
        active = next(window for window in source.graph_tab.windows
                      if window.graph is source.graph_tab.active_graph)
        self.assertEqual(active.windowTitle(), 'Tension doublée')
        write_project(self.path, snapshot(source))

        reopened = MainWindow()
        self.windows.append(reopened)
        self.assertTrue(reopened.open_project_path(self.path))
        self.app.processEvents()

        restored = next(window for window in reopened.graph_tab.windows
                        if window.graph is reopened.graph_tab.active_graph)
        self.assertEqual(restored.identifier, active.identifier)
        self.assertEqual(restored.windowTitle(), 'Tension doublée')

    def test_old_project_restores_active_graph_from_legacy_index(self):
        state = snapshot(self.populated())
        state.pop('active_graph_id')
        for graph in state['graphs']:
            graph.pop('identifier')
        state['active_graph'] = 1

        restored = MainWindow()
        self.windows.append(restored)
        restore(restored, state)
        self.app.processEvents()

        self.assertIs(restored.graph_tab.active_graph, restored.graph_tab.windows[1].graph)

    def test_missing_active_graph_falls_back_to_first_available_graph(self):
        state = snapshot(self.populated())
        state['active_graph_id'] = 'graphique-supprime'
        state.pop('active_graph')

        restored = MainWindow()
        self.windows.append(restored)
        restore(restored, state)
        self.app.processEvents()

        self.assertIs(restored.graph_tab.active_graph, restored.graph_tab.windows[0].graph)

    def test_switching_active_graph_does_not_mark_project_as_modified(self):
        self.populated()
        signature = self.window.document_signature()

        self.window.graph_tab.area.setActiveSubWindow(self.window.graph_tab.windows[0])
        self.app.processEvents()

        self.assertEqual(self.window.document_signature(), signature)

    def test_new_project_has_a_persistent_identifier_for_its_first_graph(self):
        state = snapshot(self.window)

        self.assertTrue(state['graphs'][0]['identifier'])
        self.assertEqual(state['active_graph_id'], state['graphs'][0]['identifier'])

    def test_plateau_exponential_model_roundtrip(self):
        import math
        model = self.window.data_tab.model
        xs = list(range(4, 12))
        ys = [6-(6-1.25)*math.exp(-0.65*(x-4)) for x in xs]
        for row, (x, y) in enumerate(zip(xs, ys), start=2):
            model.setData(model.index(row, 0), str(x))
            model.setData(model.index(row, 1), str(y))
        graph = self.window.graph_tab.active_graph
        result = fit_model(xs, ys, 'exponential_growth')
        graph.set_model(graph.series[0], result, 'exponential_growth', {'interval': [4, 11]})
        write_project(self.path, snapshot(self.window))
        restored = MainWindow()
        self.windows.append(restored)
        restore(restored, read_project(self.path), self.path)
        fit = restored.graph_tab.active_graph.series[0].fits[0]
        self.assertEqual(fit.kind, 'exponential_growth')
        self.assertEqual(fit.result.x0, 4)
        self.assertAlmostEqual(fit.result.parameters['y_inf'], 6, places=6)
        self.assertAlmostEqual(fit.result.parameters['y0'], 1.25, places=6)
        self.assertAlmostEqual(fit.result.parameters['k'], 0.65, places=6)
        self.assertEqual((fit.curve.getData()[0][0], fit.curve.getData()[0][-1]), (4, 11))

    def test_unicode_quantity_names_roundtrip(self):
        model = self.window.data_tab.model
        model.setData(model.index(0, 0), 'σ')
        model.setData(model.index(0, 1), 'λ')
        write_project(self.path, snapshot(self.window))
        restored = MainWindow()
        self.windows.append(restored)
        restore(restored, read_project(self.path), self.path)
        self.assertEqual(restored.data_tab.model.names[:2], ['σ', 'λ'])

    def test_series_display_numbers_are_rebuilt_without_changing_saved_ids(self):
        graph = self.window.graph_tab.active_graph
        removed = graph.add_series()
        kept = graph.add_series()
        kept.set_curve_color('#123456')
        graph.remove_series(removed)
        state = snapshot(self.window)

        self.assertEqual([entry['number'] for entry in state['graphs'][0]['series']], [1, 3])
        restored = MainWindow()
        self.windows.append(restored)
        restore(restored, state)
        restored_graph = restored.graph_tab.active_graph
        self.assertEqual([series.number for series in restored_graph.series], [1, 3])
        self.assertEqual([series.display_number for series in restored_graph.series], [1, 2])
        self.assertEqual(restored_graph.series[1].color.name(), '#123456')

    def test_default_graph_titles_stay_contiguous_after_roundtrip(self):
        workspace = self.window.graph_tab
        second = workspace.add_graph()
        workspace.add_graph()
        next(window for window in workspace.windows if window.graph is second).close()
        self.app.processEvents()
        state = snapshot(self.window)
        self.assertEqual([graph['title'] for graph in state['graphs']],
                         ['Graphique 1', 'Graphique 2'])

        restored = MainWindow()
        self.windows.append(restored)
        restore(restored, state)
        restored.graph_tab.add_graph()
        self.assertEqual([window.windowTitle() for window in restored.graph_tab.windows],
                         ['Graphique 1', 'Graphique 2', 'Graphique 3'])

    def legacy_project(self):
        """Build an authentic version-1 legacy archive, independent of the writer."""
        path = self.path.with_suffix('.physalyx')
        with zipfile.ZipFile(path, 'w') as archive:
            archive.writestr('project.json', json.dumps({
                'format': 'Physalyx', 'version': 1, 'state': snapshot(self.window)}))
        return path

    def test_legacy_open_and_save_migrates_without_changing_original(self):
        legacy = self.legacy_project()
        original = legacy.read_bytes()
        with patch.object(QFileDialog, 'getOpenFileName', return_value=(str(legacy), '')) as dialog:
            self.window.open_project()
        self.assertIn('*.physalix', dialog.call_args.args[3])
        self.assertIn('*.physalyx', dialog.call_args.args[3])
        self.assertEqual(self.window.project_path, legacy)
        with patch.object(QFileDialog, 'getSaveFileName', return_value=(str(self.path), '')) as dialog:
            self.assertTrue(self.window.save_project())
        self.assertEqual(dialog.call_args.args[2], str(self.path))
        self.assertEqual(self.window.project_path, self.path)
        self.assertEqual(legacy.read_bytes(), original)
        with zipfile.ZipFile(self.path) as archive:
            document = json.loads(archive.read('project.json'))
        self.assertEqual(document['format'], 'Physalix')
        self.assertEqual(document['version'], 2)
        self.assertEqual(read_project(self.path), read_project(legacy))
        with patch.object(QFileDialog, 'getSaveFileName') as dialog:
            self.assertTrue(self.window.save_project())
            dialog.assert_not_called()

    def test_version_one_without_image_analysis_restores_a_blank_module(self):
        state = snapshot(self.window)
        state.pop('image_analysis')
        with zipfile.ZipFile(self.path, 'w') as archive:
            archive.writestr('project.json', json.dumps({
                'format': 'Physalix', 'version': 1, 'state': state,
            }))
        restored = MainWindow()
        self.windows.append(restored)
        restore(restored, read_project(self.path), self.path)
        self.assertTrue(restored.image_analysis_tab.image.isNull())
        self.assertEqual(restored.image_analysis_tab.profiles, [])

    def test_version_one_text_formula_unit_restores_editable_combo(self):
        state = snapshot(self.window)
        state['calculations_controls']['formula_unit'] = 'm/s'
        with zipfile.ZipFile(self.path, 'w') as archive:
            archive.writestr('project.json', json.dumps({
                'format': 'Physalix', 'version': 1, 'state': state,
            }))

        restored = MainWindow()
        self.windows.append(restored)
        restore(restored, read_project(self.path), self.path)
        self.assertEqual(restored.calculations_tab.formula_unit.currentText(), 'm/s')

        roundtrip = self.path.with_name('legacy-unit-roundtrip.physalix')
        write_project(roundtrip, snapshot(restored))
        reopened = MainWindow()
        self.windows.append(reopened)
        restore(reopened, read_project(roundtrip), roundtrip)
        self.assertEqual(reopened.calculations_tab.formula_unit.currentText(), 'm/s')

    def test_save_dialog_proposes_name_without_extension(self):
        with patch.object(QFileDialog, 'getSaveFileName', return_value=('', '')) as dialog:
            self.assertFalse(self.window.save_project(save_as=True))
        self.assertEqual(dialog.call_args.args[2], 'Sans titre')
        self.assertEqual(dialog.call_args.args[3], 'Projet Physalyx (*.physalix)')

    def test_cancel_legacy_migration_preserves_path_and_file(self):
        legacy = self.legacy_project()
        self.window.replace_project(read_project(legacy), legacy)
        with patch.object(QFileDialog, 'getSaveFileName', return_value=('', '')):
            self.assertFalse(self.window.save_project())
        self.assertEqual(self.window.project_path, legacy)
        self.assertFalse(self.path.exists())

    def test_save_suffixes_and_reopen(self):
        for suffix in ('', '.physalix', '.PHYSALIX', '.physalyx', '.PHYSALYX'):
            with self.subTest(suffix=suffix):
                selected = self.path.with_suffix(suffix)
                with patch.object(QFileDialog, 'getSaveFileName', return_value=(str(selected), '')):
                    self.assertTrue(self.window.save_project(save_as=True))
                self.assertEqual(self.window.project_path, self.path)
                self.assertEqual(read_project(self.path), snapshot(self.window))
                self.path.unlink()

    def test_startup_argument_detection_supports_spaces_accents_and_missing_files(self):
        path = Path(r'C:\Users\Jean\Documents\TP Physique\Cinématique.physalix')
        self.assertEqual(project_path_from_arguments(['Physalix.exe', str(path)]), path)
        self.assertIsNone(project_path_from_arguments(['Physalix.exe']))
        self.assertIsNone(project_path_from_arguments(['Physalix.exe', '--unknown']))

    def test_application_opens_startup_project_with_shared_loader(self):
        path = Path(r'C:\Users\Jean\Documents\TP Physique\Cinématique.physalix')
        application = MagicMock()
        application.arguments.return_value = ['Physalix.exe', str(path)]
        application.exec.return_value = 0
        window = MagicMock()
        splash = MagicMock()
        guard = MagicMock()
        with patch('physalix.app.QApplication', return_value=application), \
                patch('physalix.app._load_main_window', return_value=MagicMock(return_value=window)), \
                patch('physalix.app.StartupSplash', return_value=splash), \
                patch('physalix.app.set_windows_app_id'), \
                patch('physalix.app.application_icon'), \
                patch('physalix.app.apply_theme'):
            self.assertEqual(app_main(guard), 0)
        window.open_project_path.assert_called_once_with(path)
        window.show.assert_called_once_with()
        guard.tag_window.assert_any_call(splash)
        guard.tag_window.assert_any_call(window)
        guard.untag_window.assert_called_once_with(splash)
        splash.finish.assert_called_once_with(window)

    def test_manual_open_delegates_to_shared_path_loader(self):
        with patch.object(QFileDialog, 'getOpenFileName', return_value=(str(self.path), '')), \
                patch.object(self.window, 'open_project_path', return_value=True) as loader:
            self.assertTrue(self.window.open_project())
        loader.assert_called_once_with(str(self.path))

    def test_path_loader_restores_project_title_path_and_clean_state(self):
        state = snapshot(self.populated())
        write_project(self.path, state)
        window = MainWindow()
        self.windows.append(window)
        self.assertTrue(window.open_project_path(self.path))
        self.app.processEvents()
        self.assertEqual(window.project_path, self.path)
        self.assertEqual(window.windowTitle(), f'{self.path.name} — Physalyx')
        self.assertEqual(window.document_signature(), window._saved_state)
        self.assertEqual(window.data_tab.model.rows, self.window.data_tab.model.rows)

    def test_path_loader_reports_invalid_project_without_replacing_current_work(self):
        self.window.data_tab.model.setData(self.window.data_tab.model.index(2, 0), '42')
        signature = self.window.document_signature()
        self.path.write_text('not a Physalix project', encoding='utf-8')
        with patch.object(QMessageBox, 'critical') as error:
            self.assertFalse(self.window.open_project_path(self.path))
        error.assert_called_once()
        self.assertIsNone(self.window.project_path)
        self.assertEqual(self.window.document_signature(), signature)

    def test_normalized_destination_does_not_overwrite_without_confirmation(self):
        self.path.write_bytes(b'keep me')
        with patch.object(QFileDialog, 'getSaveFileName', return_value=(str(self.path.with_suffix('')), '')), \
                patch.object(QMessageBox, 'question', return_value=QMessageBox.StandardButton.No):
            self.assertFalse(self.window.save_project())
        self.assertEqual(self.path.read_bytes(), b'keep me')

    def test_unknown_format_and_future_version_are_rejected(self):
        for name, version in [('unknown', 1), ('Physalix', 3), ('Physalyx', 3)]:
            with self.subTest(name=name, version=version):
                with zipfile.ZipFile(self.path, 'w') as archive:
                    archive.writestr('project.json', json.dumps({'format': name, 'version': version, 'state': {}}))
                with self.assertRaises(ValueError):
                    read_project(self.path)

    def test_atomic_failure_keeps_previous_file(self):
        self.path.write_text('original', encoding='utf-8')
        def fail(path):
            Path(path).write_text('partial')
            raise OSError('disk full')
        with self.assertRaises(OSError):
            atomic_write(self.path, fail)
        self.assertEqual(self.path.read_text(), 'original')

    def test_invalid_project_does_not_replace_current_work(self):
        w = self.populated()
        old = w.data_tab.model
        state = snapshot(w)
        state['graphs'][0]['series'][0]['controls']['x_choice'] = 999
        with self.assertRaises(ValueError):
            w.replace_project(state)
        self.assertIs(w.data_tab.model, old)

    def test_save_cancel_and_discard(self):
        w = self.window
        w.data_tab.model.setData(w.data_tab.model.index(2, 0), '3')
        with patch.object(QMessageBox, 'exec', return_value=QMessageBox.StandardButton.Cancel):
            self.assertFalse(w.confirm_save())
        with patch.object(QMessageBox, 'exec', return_value=QMessageBox.StandardButton.Save), patch.object(
                QFileDialog, 'getSaveFileName', return_value=('', '')):
            self.assertFalse(w.confirm_save())
        with patch.object(QFileDialog, 'getSaveFileName', return_value=(str(self.path), '')):
            self.assertTrue(w.save_project())
        self.assertTrue(w.confirm_save())

    def test_replace_project(self):
        state = snapshot(self.populated())
        with patch.object(QMessageBox, 'exec', return_value=QMessageBox.StandardButton.Discard):
            self.assertTrue(self.window.replace_project(state))
        self.app.processEvents()
        self.assertEqual(len(self.window.graph_tab.windows), 2)
        self.assertEqual(len(self.window.calculations_tab.engine.items), 2)
        self.assertEqual(self.window.document_signature(), self.window._saved_state)

    def test_acquisition_transfer_after_replace_navigates_current_window(self):
        state = snapshot(self.window)
        self.assertTrue(self.window.replace_project(state))
        acquisition = self.window.acquisition_tab
        acquisition.controller.config = AcquisitionConfig(
            2500, 2, 0, DigitalStepConfig(8, False, True, 0))
        acquisition.controller.samples[:] = [0, 1023]
        acquisition._store_result(True, "Acquisition terminée.")
        self.window.tabs.setCurrentWidget(self.window.data_tab)

        acquisition.transfer_result()

        self.assertIs(self.window.tabs.currentWidget(), self.window.graph_tab)

    def french_confirmation(self, choice):
        """Click the real standard button through the modal Qt event loop."""
        original_exec = QMessageBox.exec

        def execute(dialog):
            self.assertEqual(dialog.windowTitle(), 'Enregistrer le projet ?')
            self.assertEqual(dialog.text(), 'Le projet contient des modifications non enregistrées.')
            self.assertEqual(dialog.icon(), QMessageBox.Icon.Question)
            labels = {
                QMessageBox.StandardButton.Save: 'Enregistrer',
                QMessageBox.StandardButton.Discard: 'Ne pas enregistrer',
                QMessageBox.StandardButton.Cancel: 'Annuler',
            }
            self.assertEqual(dialog.standardButtons(),
                             QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard |
                             QMessageBox.StandardButton.Cancel)
            for button, label in labels.items():
                self.assertEqual(dialog.button(button).text(), label)
                self.assertEqual(dialog.standardButton(dialog.button(button)), button)
            self.assertIs(dialog.defaultButton(), dialog.button(QMessageBox.StandardButton.Save))
            if choice == 'close':
                QTimer.singleShot(0, dialog.close)
            else:
                QTimer.singleShot(0, dialog.button(choice).click)
            result = original_exec(dialog)
            self.assertEqual(result, QMessageBox.StandardButton.Cancel if choice == 'close' else choice)
            return result

        return patch.object(QMessageBox, 'exec', execute)

    def test_french_confirmation_close_and_replace_paths(self):
        for action in ('close', 'replace'):
            for choice in (QMessageBox.StandardButton.Save, QMessageBox.StandardButton.Discard,
                           QMessageBox.StandardButton.Cancel, 'close'):
                with self.subTest(action=action, choice=choice):
                    w = MainWindow()
                    self.windows.append(w)
                    model = w.data_tab.model
                    model.setData(model.index(2, 0), '42')
                    signature = w.document_signature()
                    path = Path(self.directory.name) / f'{action}-{choice}.physalix'
                    with self.french_confirmation(choice), patch.object(
                            QFileDialog, 'getSaveFileName', return_value=(str(path), '')) as destination:
                        result = w.close() if action == 'close' else w.replace_project()
                    accepted = choice in (QMessageBox.StandardButton.Save, QMessageBox.StandardButton.Discard)
                    self.assertEqual(result, accepted)
                    self.assertEqual(path.exists(), choice == QMessageBox.StandardButton.Save)
                    if choice == QMessageBox.StandardButton.Save:
                        destination.assert_called_once()
                        self.assertEqual(read_project(path)['table']['rows'][0][0], '42')
                    else:
                        destination.assert_not_called()
                    if not accepted:
                        self.assertIs(w.data_tab.model, model)
                        self.assertEqual(w.document_signature(), signature)
                    elif action == 'replace':
                        self.assertIsNot(w.data_tab.model, model)

    def test_french_save_failure_or_cancel_prevents_close_and_replace(self):
        for action in ('close', 'replace'):
            for failure in ('cancel', 'write_error', 'video_loading', 'overwrite_declined'):
                with self.subTest(action=action, failure=failure):
                    w = MainWindow()
                    self.windows.append(w)
                    model = w.data_tab.model
                    model.setData(model.index(2, 0), '42')
                    signature = w.document_signature()
                    self.path.write_bytes(b'previous file')
                    selected = '' if failure == 'cancel' else str(
                        self.path.with_suffix('') if failure == 'overwrite_declined' else self.path)
                    if failure == 'video_loading':
                        w.video_tab.loader = object()
                    try:
                        with self.french_confirmation(QMessageBox.StandardButton.Save), patch.object(
                                QFileDialog, 'getSaveFileName', return_value=(selected, '')), patch(
                                'physalix.ui.project_files.write_project', side_effect=OSError('disk full')) as write, \
                                patch.object(QMessageBox, 'critical') as error, \
                                patch.object(QMessageBox, 'information') as info, \
                                patch.object(QMessageBox, 'question', return_value=QMessageBox.StandardButton.No):
                            self.assertFalse(w.close() if action == 'close' else w.replace_project())
                        self.assertEqual(write.call_count, int(failure == 'write_error'))
                        self.assertEqual(error.call_count, int(failure == 'write_error'))
                        self.assertEqual(info.call_count, int(failure == 'video_loading'))
                    finally:
                        if failure == 'video_loading':
                            w.video_tab.loader = None
                    self.assertIs(w.data_tab.model, model)
                    self.assertEqual(w.document_signature(), signature)
                    self.assertEqual(self.path.read_bytes(), b'previous file')
                    self.assertIsNone(w.project_path)

    def test_clean_or_explicitly_discarded_project_needs_no_confirmation(self):
        with patch.object(QMessageBox, 'exec') as dialog:
            self.assertTrue(self.window.confirm_save())
            model = self.window.data_tab.model
            model.setData(model.index(2, 0), '42')
            self.window._discard_on_close = True
            self.assertTrue(self.window.confirm_save())
        dialog.assert_not_called()

    def test_csv_decimal_quotes_headers_blanks_and_append(self):
        path = Path(self.directory.name) / 'mesures.csv'
        path.write_text('Temps [s];Tension [V]\n0;1,25\n1;\n2;"texte; cité"\n', encoding='utf-8-sig')
        data = read_csv(path)
        self.assertEqual(data['units'], ['s', 'V'])
        self.assertEqual(data['rows'][2][1], 'texte; cité')
        w = self.window
        w.append_csv(data)
        w.calculations_tab.engine.add('double', 'V', expression='C2*2')
        self.app.processEvents()
        write_csv(path, w.data_tab.model)
        values = read_csv(path)
        self.assertEqual(values['rows'][0], ['0', '1,25', '2,5'])
        w.append_csv(data)
        self.assertEqual(w.data_tab.model.names, ['Temps', 'Tension', 'double', 'Temps_2', 'Tension_2'])
        self.assertEqual(w.data_tab.model.rows[0][:3], ['0', '1,25', '2.5'])

    def test_csv_no_headers_and_literal_formulas(self):
        path = Path(self.directory.name) / 'mesures.csv'
        path.write_text('0,1.5\n1,2.5\n', encoding='utf-8')
        self.assertEqual(read_csv(path, header=False)['rows'][0], ['0', '1.5'])
        self.window.append_csv({'names': ['a','b'], 'units': ['', ''], 'rows': [['=1+2', '-2']]})
        self.assertFalse(self.window.data_tab.model.formulas)
        write_csv(path, self.window.data_tab.model)
        self.assertEqual(read_csv(path)['rows'][0], ["'=1+2", '-2'])

    def test_video_embedded_with_calibration(self):
        from physalix.video import VideoCache
        from PySide6.QtGui import QImage
        video = self.window.video_tab
        video.cache = VideoCache(tempfile.TemporaryDirectory(), [0.0], 20, 20, False)
        image = QImage(20,20,QImage.Format.Format_RGB32)
        image.fill(0)
        image.save(video.cache.path(0))
        video.tracking.origin = QPointF(3,4)
        video.tracking.scale = .1
        video.tracking.length = 1.0
        video.tracking.points = {0: (QPointF(5,6), 0.0)}
        write_project(self.path, snapshot(self.window), video.cache)
        v = MainWindow()
        self.windows.append(v)
        restore(v, read_project(self.path), self.path)
        self.assertEqual(v.video_tab.tracking.origin, QPointF(3,4))
        self.assertEqual(v.video_tab.tracking.points[0][0], QPointF(5,6))
        self.assertFalse(v.video_tab.pixmap.isNull())

    def test_curve_tools_and_zoom_roundtrip(self):
        w = self.populated()
        graph = w.graph_tab.windows[0].graph
        graph.curve_guides_tool.open_tool('tangent')
        graph.curve_guides_tool.source.setCurrentIndex(1)
        graph.curve_guides_tool.x.setValue(1.5)
        graph.curve_guides_tool.asymptote_on.setChecked(True)
        graph.curve_guides_tool.level.setValue(9)
        graph.plot.setRange(xRange=(1,2), yRange=(2,7), padding=0)
        state = snapshot(w)
        v = MainWindow()
        self.windows.append(v)
        restore(v, state)
        self.app.processEvents()
        tool = v.graph_tab.windows[0].graph.curve_guides_tool
        self.assertTrue(tool.active)
        self.assertTrue(tool.asymptote_on.isChecked())
        self.assertEqual(tool.source.currentIndex(), 1)
        self.assertEqual(tool.x.value(), 1.5)
        self.assertEqual(tool.level.value(), 9)
        self.assertEqual(v.graph_tab.windows[0].graph.plot.viewRange(), state['graphs'][0]['view'])

    def test_empty_table_roundtrip(self):
        model = self.window.data_tab.model
        model.remove_quantity(1)
        model.remove_quantity(0)
        v = MainWindow()
        self.windows.append(v)
        restore(v, snapshot(self.window))
        self.assertEqual(v.data_tab.model.columnCount(), 0)


if __name__ == '__main__':
    unittest.main()
