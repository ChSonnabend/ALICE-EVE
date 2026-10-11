from dataclasses import replace
from pathlib import Path
import numpy as np
import pytest
from alice_renderer.model import RenderSettings,validate_event,color_value,capabilities
from alice_renderer.object_selection import selected_tracks,selected_clusters,parse_track_ids,highlighted
from alice_renderer.palettes import names,sample,materialize
from alice_renderer.picking import projected_hit
from alice_renderer.scene_config import recipe,save_config,load_config,resolve_settings
from alice_renderer.track_clipping import selected_track_detectors


def event():
    return {'schema_version':1,'units':'cm','kind':'synthetic','id':'E','tracks':[
        {'id':'1','source':'ITS','detectors':['ITS'],'points':[[0,0,0],[1,0,0]]},
        {'id':'2','source':'TPC','detectors':['TPC'],'points':[[0,0,0],[2,0,0]]},
        {'id':'3','source':'ITS-TPC','detectors':['ITS','TPC'],'points':[[0,0,0],[3,0,0]]}],
        'clusters':[{'id':'c1','detector':'ITS','position':[1,0,0],'track_id':'3'},{'id':'c2','detector':'TPC','position':[2,0,0],'track_id':'3'}]}


def test_per_detector_modes_select_objects_and_track_extents():
    data=validate_event(event());cfg=RenderSettings(detectors=['ITS','TPC'],detector_modes={'ITS':'clusters','TPC':'tracks'}).to_dict()
    assert [t['id'] for t in selected_tracks(data,cfg)]==['2','3']
    assert [c['id'] for c in selected_clusters(data,cfg)]==['c1']
    assert selected_track_detectors(cfg,data['tracks'][2])=={'TPC'}
    cfg['detector_modes']['TPC']='both'
    assert len(selected_clusters(data,cfg))==2


def test_matching_is_proven_by_source_or_explicit_provenance():
    data=validate_event(event())
    assert color_value(data['tracks'][0],'matching')==0
    assert color_value(data['tracks'][2],'matching')==1
    assert color_value(data['clusters'][0],'matching')==1
    unknown={'detectors':['ITS','TPC'],'points':[[0,0,0],[1,1,1]]}
    assert color_value(unknown,'matching') is None
    assert 'matching' not in capabilities([unknown])
    bad=event();bad['tracks'][0]['matching']=True
    with pytest.raises(ValueError,match='matching_basis'):validate_event(bad)


def test_special_ids_style_tracks_and_only_linked_clusters():
    ids=parse_track_ids('3, 1, 3, , ');assert ids==['3','1']
    cfg=RenderSettings(highlight_track_ids=ids).to_dict();data=validate_event(event())
    assert highlighted(data['tracks'][2],cfg,'tracks')
    assert highlighted(data['clusters'][0],cfg,'clusters')
    assert not highlighted({'track_id':'unknown'},cfg,'clusters')
    assert not highlighted({'id':'3'},cfg,'clusters')


def test_all_registry_maps_and_reverses_sample_without_blender_dependency():
    assert len(names())>150
    assert 'plasma' in names() and 'plasma_r' in names() and 'tab20' in names()
    forward=sample('plasma');reverse=sample('plasma_r')
    np.testing.assert_allclose(forward[0],reverse[-1])
    assert len(forward)==256


def test_scene_roundtrip_preserves_emphasis_modes_palette_and_roll(tmp_path):
    cfg=RenderSettings(detectors=['ITS','TPC'],detector_modes={'ITS':'clusters','TPC':'both'},palette='plasma_r',roll=93.,highlight_track_ids=['3'],highlight_track_radius_cm=.8,highlight_cluster_radius_cm=2.)
    path=tmp_path/'scene.json';save_config(path,recipe(cfg))
    restored=resolve_settings(load_config(path),path)
    assert restored.roll==93 and restored.detector_modes==cfg.detector_modes
    assert restored.highlight_track_ids==['3'] and restored.highlight_track_radius_cm==.8
    assert restored.palette_lut==sample('plasma_r')
    restored.palette='custom_transferred';restored.validate() # LUT is self-contained on another installation.


def test_mouse_picking_uses_displayed_segments_and_camera_depth():
    identity=np.eye(4)
    hit=projected_hit((50,50),[[-.5,0,0],[.5,0,0]],identity,100,100)
    assert hit==(0.,0.)
    assert projected_hit((50,80),[[-.5,0,0],[.5,0,0]],identity,100,100) is None
    assert projected_hit((50,50),[[-.5,0,2],[.5,0,2]],identity,100,100) is None
    matrix=np.eye(4);matrix[3,3]=-1
    assert projected_hit((50,50),[[-.5,0,0],[.5,0,0]],matrix,100,100) is None


def test_invalid_per_detector_modes_and_highlight_sizes_rejected():
    with pytest.raises(ValueError):RenderSettings(detector_modes={'TPC':'invalid'}).validate()
    with pytest.raises(ValueError):RenderSettings(highlight_cluster_radius_cm=0).validate()
    with pytest.raises(ValueError):RenderSettings(roll=float('nan')).validate()


def test_per_detector_and_magnet_geometry_detail_roundtrip(tmp_path):
    cfg=RenderSettings(geometry_lod='simplified',geometry_lods={'TPC':'full','L3':'simplified'})
    path=tmp_path/'scene.json';save_config(path,recipe(cfg))
    restored=resolve_settings(load_config(path),path)
    assert restored.geometry_lods==cfg.geometry_lods
    assert restored.geometry_lod=='simplified'
    with pytest.raises(ValueError):RenderSettings(geometry_lods={'TPC':'unknown'}).validate()
    with pytest.raises(ValueError):RenderSettings(geometry_lods={'NOPE':'full'}).validate()
