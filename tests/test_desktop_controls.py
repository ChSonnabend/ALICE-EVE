import os,time,json
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from pathlib import Path
import pytest
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QPixmap
from alice_renderer import app as app_module
from alice_renderer.demo import generate
from alice_renderer.model import RenderSettings

@pytest.fixture
def window(tmp_path,monkeypatch):
    application=QApplication.instance() or QApplication([])
    monkeypatch.setattr(app_module,'ROOT',tmp_path)
    w=app_module.Window();w.show();application.processEvents()
    yield w,application,tmp_path
    if w.task and w.task.isRunning():
        w.task.cancel.set();w.task.wait(5000)
    w.close();application.processEvents()


def settle(w,application):
    end=time.monotonic()+10
    while w.task and w.task.isRunning() and time.monotonic()<end:application.processEvents();time.sleep(.01)
    application.processEvents()
    assert not (w.task and w.task.isRunning())


def test_pasted_folder_loaded_by_enter_action_without_file_dialog(window,monkeypatch):
    w,application,root=window;folder=root/'events';generate(folder/'events.jsonl')
    def unexpected(*args):raise AssertionError('Typed path should not open a file chooser')
    monkeypatch.setattr(app_module.QFileDialog,'getOpenFileName',unexpected)
    w.source.setText(str(folder));w.source.returnPressed.emit();settle(w,application)
    assert len(w.model.rows)==3
    assert Path(w.source.text())==folder


def test_preview_and_long_status_do_not_resize_window(window):
    w,application,root=window
    before=w.size();image=root/'render.png';pixmap=QPixmap(3840,2160);pixmap.fill();pixmap.save(str(image))
    (root/'metadata.json').write_text(json.dumps({'event_id':'E','kind':'synthetic','rendered_tracks':1,'rendered_clusters':0,'geometry':{}}))
    w.show_image(image);w.message('Completed: /'+('very-long-folder-name/'*40)+'render.png')
    for _ in range(4):application.processEvents()
    assert w.size()==before


def test_per_detector_modes_special_ids_roll_and_config_controls(window):
    w,application,root=window
    cfg=RenderSettings(detector_modes={'ITS':'clusters','TPC':'both'},highlight_track_ids=['3','7'],highlight_track_radius_cm=.5,palette='plasma',roll=91.)
    w.apply_scene(cfg)
    assert w.detector_modes['ITS'].currentText()=='clusters'
    actual=w.settings();assert actual.highlight_track_ids==['3','7'] and actual.roll==91
    assert actual.highlight_track_radius_cm==.5
    assert actual.detector_modes['TPC']=='both'
    w.mode.setCurrentText('clusters')
    assert all(combo.currentText()=='clusters' for combo in w.detector_modes.values())


def test_imported_custom_palette_table_is_preserved(window):
    w,application,root=window
    cfg=RenderSettings(palette='custom_remote',palette_lut=[[0,0,1],[1,0,0]])
    w.apply_scene(cfg)
    assert w.settings().palette=='custom_remote'
    assert w.settings().palette_lut==cfg.palette_lut
    w.palette.setCurrentText('viridis')
    assert w.settings().palette_lut==[]


def test_render_dialog_chooses_detail_per_surface_and_magnet(window,monkeypatch):
    from PySide6.QtWidgets import QDialog,QComboBox
    w,application,root=window
    cfg=RenderSettings(geometry=['ITS','TPC'],magnet=True,geometry_lod='simplified',geometry_lods={'TPC':'full'})
    def accept(dialog):
        form=dialog.layout()
        choices={form.labelForField(c).text():c for c in dialog.findChildren(QComboBox) if form.labelForField(c)}
        assert choices['ITS geometry detail'].currentData()=='simplified'
        assert choices['TPC geometry detail'].currentData()=='full'
        assert choices['L3 geometry detail'].currentData()=='simplified'
        choices['TPC geometry detail'].setCurrentIndex(choices['TPC geometry detail'].findData('simplified'))
        choices['L3 geometry detail'].setCurrentIndex(choices['L3 geometry detail'].findData('full'))
        return QDialog.Accepted
    monkeypatch.setattr(QDialog,'exec',accept)
    chosen=w.render_quality_dialog(cfg,{'devices':[{'type':'CPU'}]})
    assert chosen.geometry_lods=={'ITS':'simplified','TPC':'simplified','L3':'full'}
    assert cfg.geometry_lods=={'TPC':'full'} # render-only choices do not mutate editor settings
