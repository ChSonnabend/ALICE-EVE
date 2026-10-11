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
        assert all(choices[name+' geometry detail'].currentData()=='current' for name in ('ITS','TPC','L3'))
        assert 'simplified aligned' in choices['ITS geometry detail'].currentText()
        assert 'full aligned' in choices['TPC geometry detail'].currentText()
        choices['TPC geometry detail'].setCurrentIndex(choices['TPC geometry detail'].findData('simplified'))
        choices['L3 geometry detail'].setCurrentIndex(choices['L3 geometry detail'].findData('full'))
        return QDialog.Accepted
    monkeypatch.setattr(QDialog,'exec',accept)
    chosen=w.render_quality_dialog(cfg,{'devices':[{'type':'CPU'}]})
    assert chosen.geometry_lods=={'TPC':'simplified','L3':'full'}
    assert chosen.geometry_schematics=={'TPC':False,'L3':False}
    assert cfg.geometry_lods=={'TPC':'full'} # render-only choices do not mutate editor settings


def test_camera_orbit_axis_preserved_in_desktop_controls(window):
    w,application,root=window
    from alice_renderer.defaults import startup_settings
    assert w.settings().camera_orbit_axis=='Y'
    assert w.settings().elevation==pytest.approx(startup_settings().elevation,abs=.051)
    cfg=RenderSettings(camera_orbit_axis='Z',elevation=22)
    w.apply_scene(cfg)
    assert w.settings().camera_orbit_axis=='Z' and w.settings().elevation==22
    w.camera_orbit_axis.setCurrentText('Y')
    assert w.settings().camera_orbit_axis=='Y'


def test_commissioning_defaults_clone_style_keep_input_events_assets_and_hardware(window):
    w,application,root=window;generate(root/'events.jsonl');w.load_input(root/'events.jsonl');settle(w,application)
    w.model.select_all(False);w.model.selected={1};w.update_availability()
    source=w.source.text();w.backend.setCurrentText('CPU');w.samples.setValue(17)
    w.asset_fields['ITS'].setText('/local/aligned/ITS.blend');w.geometry_units.setCurrentText('cm')
    w.roll.setValue(0);w.view_transform.setCurrentText('AgX');w.use_commissioning_defaults()
    cfg=w.settings()
    assert w.source.text()==source and w.model.selected=={1}
    assert cfg.geometry_assets['ITS']=='/local/aligned/ITS.blend' and cfg.geometry_units=='cm'
    assert cfg.backend=='CPU' and cfg.samples==17 and cfg.view_transform=='Standard'
    assert cfg.camera_pose and cfg.geometry_openings=={'ITS':180.,'TPC':180.}
    saved=json.loads(w.settings_file.read_text())['render']
    assert saved['detectors']==['ITS','TPC']


def test_recent_clone_retains_new_input_and_event_and_favourites_picker(window):
    from alice_renderer.scene_config import recipe,save_config
    w,application,root=window;generate(root/'events.jsonl');w.load_input(root/'events.jsonl');settle(w,application)
    w.model.select_all(False);w.model.selected={1};w.update_availability()
    cfg=RenderSettings(schematic=True,geometry=['TPC'],roll=39,highlight_track_ids=['old-id'],geometry_openings={'TPC':215})
    path=root/'saved.json';save_config(path,recipe(cfg));w.library.register(path,input_path='missing-old-file',event='old-event')
    entry=w.library.entries()[0];w.library.favourite(entry,title='Reference view');w.refresh_library()
    assert w.recent_picker.count()==2 and w.favourite_picker.count()==2
    assert w.library_lists[True].count()==1
    original_path=w.source.text();original_selected=w.model.selected.copy()
    w.use_library_entry(w.favourite_picker.itemData(1),True)
    assert w.source.text()==original_path and w.model.selected==original_selected
    assert w.settings().roll==39 and w.settings().geometry_openings['TPC']==215
    assert w.settings().highlight_track_ids==[]


def test_recent_reload_selects_only_original_event(window):
    from alice_renderer.scene_config import recipe,save_config
    w,application,root=window;generate(root/'events.jsonl');w.load_input(root/'events.jsonl');settle(w,application)
    event_id=w.model.rows[1]['event_id'];path=root/'saved.json';save_config(path,recipe(RenderSettings(schematic=True,roll=19)))
    w.library.register(path,input_path=str(root/'events.jsonl'),event=event_id)
    w.use_library_entry(w.library.entries()[0],False);settle(w,application)
    assert w.model.selected=={1} and w.settings().roll==19


def test_resolution_slider_changes_output_and_retains_camera_aspect(window,monkeypatch):
    from PySide6.QtWidgets import QDialog,QSlider
    w,application,root=window
    def accept(dialog):
        slider=dialog.findChild(QSlider,'resolutionPercent');assert slider is not None
        slider.setValue(500);return QDialog.Accepted
    monkeypatch.setattr(QDialog,'exec',accept)
    cfg=RenderSettings(frame_aspect=4/3)
    chosen=w.render_quality_dialog(cfg,{'devices':[{'type':'CPU'}]})
    assert (chosen.width,chosen.height)==(2880,2160) and chosen.samples==16


def test_library_tab_buttons_accept_qt_clicked_argument(window,monkeypatch):
    from PySide6.QtWidgets import QPushButton,QInputDialog
    from alice_renderer.scene_config import recipe,save_config
    w,application,root=window;path=root/'scene.json';save_config(path,recipe(RenderSettings(roll=28)))
    w.library.register(path);w.refresh_library();listing=w.library_lists[False];listing.setCurrentRow(0)
    recent_tab=listing.parentWidget()
    use=next(b for b in recent_tab.findChildren(QPushButton) if b.text()=='Use for current input / event')
    use.click();assert w.settings().roll==28
    monkeypatch.setattr(QInputDialog,'getText',lambda *args,**kwargs:('Pinned scene',True))
    add=next(b for b in recent_tab.findChildren(QPushButton) if b.text()=='Add to favourites…')
    add.click();assert w.favourite_picker.count()==2 and w.library.entries(True)[0]['title']=='Pinned scene'
    w.library_lists[True].setCurrentRow(0)
    remove=next(b for b in w.library_lists[True].parentWidget().findChildren(QPushButton) if b.text()=='Remove favourite')
    remove.click();assert w.favourite_picker.count()==1


def test_changed_unloaded_input_does_not_render_previous_event(window,monkeypatch):
    w,application,root=window;generate(root/'events.jsonl');w.load_input(root/'events.jsonl');settle(w,application)
    messages=[];monkeypatch.setattr(w,'failure',messages.append)
    w.source.setText(str(root/'new-data.jsonl'));w.start_render(True);w.open_editor()
    assert len(messages)==2 and all('Load input' in m for m in messages)
    assert not w.task or not w.task.isRunning()


def test_original_scene_alignment_retained_but_new_input_can_supply_new_alignment(window):
    from alice_renderer.scene_config import recipe,save_config
    w,application,root=window;folder=root/'events';generate(folder/'events.jsonl')
    old=root/'old.blend';old.write_bytes(b'original-alignment');new=root/'new.blend';new.write_bytes(b'new-alignment')
    (folder/'manifest.json').write_text(json.dumps({'complete':True,'events_file':'events.jsonl','geometry_assets':{'TPC':str(new)},'geometry_units':'m'}))
    w.load_input(folder);settle(w,application)
    event=w.model.rows[0]['event_id'];cfg=RenderSettings(geometry=['TPC'],geometry_assets={'TPC':str(old)},geometry_units='cm')
    path=root/'scene.json';save_config(path,recipe(cfg));w.library.register(path,input_path=str(folder),event=event,assets=cfg.geometry_assets)
    w.use_library_entry(w.library.entries()[0],False);settle(w,application)
    assert w.asset_fields['TPC'].text()==str(old) and w.geometry_units.currentText()=='cm'
    w.load_input(folder);settle(w,application)
    assert w.asset_fields['TPC'].text()==str(new) and w.geometry_units.currentText()=='m'


def test_display_glow_and_lens_controls_roundtrip_preserve_camera_pose(window):
    w,application,root=window
    pose={'matrix_world':[[1,0,0,4],[0,1,0,5],[0,0,1,6],[0,0,0,1]],'lens':36,'ortho_scale':4}
    cfg=RenderSettings(camera_pose=pose,view_transform='Standard',exposure=-.5,track_emission=.25,cluster_emission=.8)
    w.apply_scene(cfg);actual=w.settings()
    assert actual.view_transform=='Standard' and actual.exposure==-.5
    assert actual.track_emission==.25 and actual.cluster_emission==.8
    assert actual.camera_pose==pose and actual.camera_lens_mm==36
    w.camera_lens.setValue(42);actual=w.settings()
    assert actual.camera_pose['lens']==42 and actual.camera_pose['matrix_world']==pose['matrix_world']
    assert pose['lens']==36
    w.azimuth.setValue(5)
    assert w.settings().camera_pose=={} and w.settings().camera_lens_mm==42
