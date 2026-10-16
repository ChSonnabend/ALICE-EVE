import json
from pathlib import Path
from dataclasses import replace
from alice_renderer.model import RenderSettings
from alice_renderer.scene_config import recipe,save_config,load_config
from alice_renderer.scene_library import SceneLibrary

def test_default_favourites_seed_once_preserve_edits_and_removals(tmp_path):
    lib=SceneLibrary(tmp_path/'history.sqlite')
    assert set(lib.ensure_default_favourites())=={'ITS-TPC','ALICE general'}
    entries={e['title']:e for e in lib.entries(True)}
    assert len(entries)==2 and not lib.entries()
    for entry in entries.values():
        assert entry['input']==entry['event']==''
        assert load_config(entry['config'])['defaults']=={}
    closeup=entries['ITS-TPC'];data=load_config(closeup['config'])
    data['scene']['roll']=57;save_config(closeup['config'],data)
    lib.unfavourite(entries['ALICE general'])
    # A restart never restores a removed starter or overwrites a local snapshot.
    lib=SceneLibrary(tmp_path/'history.sqlite')
    assert lib.ensure_default_favourites()==[]
    assert [e['title'] for e in lib.entries(True)]==['ITS-TPC']
    assert lib.settings(lib.entries(True)[0],reuse=True).roll==57

def test_default_favourites_geometry_installed_later_uses_local_paths(tmp_path):
    lib=SceneLibrary(tmp_path/'history.sqlite');lib.ensure_default_favourites()
    assert all(e['assets']=={} for e in lib.entries(True))
    asset=tmp_path/'geometry/run-560067/ITS.blend';asset.parent.mkdir(parents=True);asset.touch()
    lib.ensure_default_favourites()
    assert all(e['assets']=={'ITS':str(asset)} for e in lib.entries(True))

def test_default_favourites_do_not_replace_same_named_user_favourite(tmp_path):
    lib=SceneLibrary(tmp_path/'history.sqlite');path=tmp_path/'custom.json'
    save_config(path,recipe(RenderSettings(roll=83)))
    lib.register(path);lib.favourite(lib.entries()[0],title='ITS-TPC')
    assert lib.ensure_default_favourites()==['ALICE general']
    entries={e['title']:e for e in lib.entries(True)}
    assert len(entries)==2
    assert lib.settings(entries['ITS-TPC']).roll==83

def test_builtin_revision_updates_only_unmodified_snapshot(tmp_path):
    from alice_renderer.scene_library import recipe_digest
    lib=SceneLibrary(tmp_path/'history.sqlite');lib.ensure_default_favourites()
    entry=next(e for e in lib.entries(True) if e['title']=='ITS-TPC')
    current=load_config(entry['config']);old=json.loads(json.dumps(current))
    old['scene']['roll']=-42;save_config(entry['config'],old)
    with lib.connect() as db:
        db.execute('UPDATE builtin_revisions SET digest=? WHERE id=?',(recipe_digest(old),entry['id']))
    lib.ensure_default_favourites()
    assert load_config(entry['config'])==current
    old['scene']['roll']=-43;save_config(entry['config'],old)
    lib.ensure_default_favourites()
    assert load_config(entry['config'])==old

def test_builtin_its_tpc_uses_chamber_asset_without_changing_general(tmp_path):
    root=tmp_path/'geometry/run-560067';root.mkdir(parents=True)
    for filename in ('TRD.blend','TRD-chambers.blend'):(root/filename).touch()
    lib=SceneLibrary(tmp_path/'history.sqlite');lib.ensure_default_favourites()
    entries={e['title']:e for e in lib.entries(True)}
    assert entries['ITS-TPC']['assets']['TRD']==str(root/'TRD-chambers.blend')
    assert entries['ALICE general']['assets']['TRD']==str(root/'TRD.blend')
    data=load_config(entries['ITS-TPC']['config'])
    assert data['defaults']=={} and data['scene']['beampipe']
    assert data['scene']['geometry_lods']['TRD']=='full'
    assert data['scene']['geometry_opening_z_intervals_cm']['TRD']

def test_favourites_are_frozen_while_interactive_history_updates(tmp_path):
    lib=SceneLibrary(tmp_path/'history.sqlite');path=tmp_path/'scene.json'
    cfg=RenderSettings(schematic=True,geometry=['TPC'],roll=31)
    save_config(path,recipe(cfg));lib.register(path,kind='interactive',input_path='original.json',event='E')
    original=lib.entries()[0];lib.favourite(original,title='My view')
    save_config(path,recipe(replace(cfg,roll=72)));lib.register(path,kind='interactive',input_path='original.json',event='E')
    assert lib.settings(lib.entries()[0]).roll==72
    favourite=lib.entries(True)[0];assert lib.settings(favourite).roll==31 and favourite['title']=='My view'
    assert lib.entries()[0]['favourite']
    lib.unfavourite(favourite);assert not lib.entries(True) and not lib.entries()[0]['favourite']

def test_clone_uses_new_alignment_and_clears_event_specific_ids(tmp_path):
    old=tmp_path/'old.blend';old.write_bytes(b'old-alignment');new=tmp_path/'new.blend';new.write_bytes(b'new-alignment')
    cfg=RenderSettings(geometry=['TPC'],geometry_assets={'TPC':str(old)},highlight_track_ids=['17'],roll=17,geometry_openings={'TPC':125},color_ranges={'tracks':[0,20]})
    path=tmp_path/'scene.json';save_config(path,recipe(cfg));lib=SceneLibrary(tmp_path/'history.sqlite');lib.register(path,assets=cfg.geometry_assets,input_path='old-events',event='old-event')
    entry=lib.entries()[0];old.unlink()
    cloned=lib.settings(entry,reuse=True,assets={'TPC':str(new)},geometry_units='m')
    assert cloned.geometry_assets=={'TPC':str(new)} and cloned.geometry_units=='m'
    assert cloned.roll==17 and cloned.geometry_openings==cfg.geometry_openings and cloned.color_ranges==cfg.color_ranges
    assert cloned.highlight_track_ids==[] and lib.entries()[0]['input']==str(Path('old-events').resolve())
    assert recipe(cloned)['geometry']['TPC']['file']=='new.blend'

def test_history_records_actual_render_camera_and_legend_and_discovers_once(tmp_path):
    folder=tmp_path/'renders'/'render-test'/'event-00000';folder.mkdir(parents=True)
    cfg=RenderSettings();pose={'matrix_world':[[1,0,0,3],[0,1,0,2],[0,0,1,1],[0,0,0,1]],'lens':76,'ortho_scale':4}
    (folder/'job.json').write_text(json.dumps({'settings':cfg.to_dict(),'event':'event.json','preview':False}))
    (folder/'metadata.json').write_text(json.dumps({'event_id':'RUN-PV','camera':pose,'track_legend':{'min':3,'max':29}}));(folder/'render.png').touch()
    lib=SceneLibrary(tmp_path/'history.sqlite');lib.discover(tmp_path/'renders');lib.discover(tmp_path/'renders')
    entries=lib.entries();assert len(entries)==1 and entries[0]['event']=='RUN-PV'
    restored=lib.settings(entries[0]);assert restored.camera_pose==pose and restored.color_ranges['tracks']==[3,29]
    assert load_config(entries[0]['config'])['defaults']=={}

def test_legacy_history_and_clone_preserve_ambiguous_reference_visibility(tmp_path):
    folder=tmp_path/'render-old'/'event-00000';folder.mkdir(parents=True)
    values=RenderSettings().to_dict();values.pop('include_ambiguous_tracks');values.pop('data_glow_lighting')
    (folder/'job.json').write_text(json.dumps({'settings':values,'event':'old.json'}))
    lib=SceneLibrary(tmp_path/'history.sqlite');lib.record_job(folder)
    entry=lib.entries()[0]
    assert lib.settings(entry).include_ambiguous_tracks
    assert lib.settings(entry,reuse=True).include_ambiguous_tracks
    assert lib.settings(entry,reuse=True).data_glow_lighting
    # Recipes written before the option existed follow the same migration.
    path=Path(entry['config']);data=load_config(path);data['scene'].pop('include_ambiguous_tracks');save_config(path,data)
    assert lib.settings(entry).include_ambiguous_tracks
    assert lib.settings(entry,reuse=True).include_ambiguous_tracks
