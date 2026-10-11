import numpy as np
import pytest
from alice_renderer.track_clipping import prepare_regions,clip_polyline
from alice_renderer.model import RenderSettings
from alice_renderer.runtime import preflight
from alice_renderer.scene_config import recipe,resolve_settings


def box(low,high):
    return {'planes':[[1,0,0,high[0]],[-1,0,0,-low[0]],[0,1,0,high[1]],[0,-1,0,-low[1]],[0,0,1,high[2]],[0,0,-1,-low[2]]]}


def region(low=(-1,-1,-1),high=(1,1,1)):
    return prepare_regions({'TPC':box(low,high)})['TPC']


def test_segment_crossing_with_both_endpoints_outside_is_trimmed():
    pieces=clip_polyline([[-5,0,0],[5,0,0]],[region()])
    np.testing.assert_allclose(pieces,[[[-1,0,0],[1,0,0]]])


def test_disconnected_regions_do_not_join_through_unselected_detector():
    pieces=clip_polyline([[-5,0,0],[5,0,0]],[region((-3,-1,-1),(-2,1,1)),region((2,-1,-1),(3,1,1))])
    np.testing.assert_allclose(pieces,[[[-3,0,0],[-2,0,0]],[[2,0,0],[3,0,0]]])


def test_overlapping_regions_and_reentry_keep_continuous_paths():
    pieces=clip_polyline([[-2,0,0],[0,0,0],[2,0,0],[0,0,0]],[region(),region((0,-1,-1),(1.5,1,1))])
    assert len(pieces)==2
    np.testing.assert_allclose(pieces[0],[[-1,0,0],[0,0,0],[1.5,0,0]])
    np.testing.assert_allclose(pieces[1],[[1.5,0,0],[0,0,0]])


def test_parallel_outside_segments_and_empty_selection():
    assert clip_polyline([[-2,2,0],[2,2,0]],[region()])==[]
    assert clip_polyline([[-2,0,0],[2,0,0]],[])==[]
    assert clip_polyline([[0,0,0]],[region()])==[]


def test_linewidth_margin_keeps_tube_inside_outer_extent():
    pieces=clip_polyline([[-2,0,0],[2,0,0]],[region()],margin_cm=.2)
    np.testing.assert_allclose(pieces,[[[-.8,0,0],[.8,0,0]]])


def test_clipping_preserves_source_coordinates():
    points=[[-2,0,0],[2,0,0]]
    clip_polyline(points,[region()])
    assert points==[[-2,0,0],[2,0,0]]


def test_no_data_selection_allows_geometry_only_and_blank_scene(tmp_path):
    cfg=RenderSettings(detectors=[],track_color_mode='pt')
    event={'id':'1','kind':'collision','tracks':[],'clusters':[]}
    devices={'version':[5,0,0],'devices':[{'type':'CPU','id':'CPU'}]}
    assert preflight(cfg,[event],devices,tmp_path)==[]


def test_real_tracks_need_aligned_asset_before_render(tmp_path):
    event={'id':'1','kind':'collision','tracks':[{'detectors':['TPC'],'points':[[0,0,0],[1,0,0]]}],'clusters':[]}
    cfg=RenderSettings(detectors=['TPC'])
    devices={'version':[5,0,0],'devices':[{'type':'CPU','id':'CPU'}]}
    assert any('required for track clipping' in message for message in preflight(cfg,[event],devices,tmp_path))
    cfg.clip_tracks=False
    assert preflight(cfg,[event],devices,tmp_path)==[]


def test_clipping_assets_export_even_when_surface_hidden(tmp_path):
    asset=tmp_path/'TPC.blend';asset.write_bytes(b'fixture')
    cfg=RenderSettings(detectors=['TPC'],geometry=[],geometry_assets={'TPC':str(asset)},track_radius_cm=.025)
    data=recipe(cfg)
    assert 'TPC' in data['geometry'] and data['scene']['clip_tracks'] is True
    restored=resolve_settings(data,tmp_path/'scene.json',tmp_path)
    assert restored.geometry==[] and restored.geometry_assets['TPC']==str(asset.resolve())
    assert restored.track_radius_cm==.025 and restored.cutaway is False


def test_shown_detectors_restrict_source_selection_with_data_only_fallback():
    from alice_renderer.track_clipping import selected_track_detectors
    cfg={'detectors':['ITS','TPC','MCH'],'geometry':['TPC']}
    assert selected_track_detectors(cfg,{'detectors':['TPC','TOF']})=={'TPC'}
    assert selected_track_detectors(cfg,{'detectors':['MCH']})==set()
    cfg['geometry']=[]
    assert selected_track_detectors(cfg,{'detectors':['MCH']})=={'MCH'}


def test_hidden_other_source_does_not_require_exporting_its_asset(tmp_path):
    for name in ('TPC','MCH'):(tmp_path/(name+'.blend')).write_bytes(name.encode())
    cfg=RenderSettings(detectors=['TPC','MCH'],geometry=['TPC'],geometry_assets={d:str(tmp_path/(d+'.blend')) for d in ('TPC','MCH')})
    assert set(recipe(cfg)['geometry'])=={'TPC'}
