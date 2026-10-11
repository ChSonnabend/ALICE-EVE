from pathlib import Path
import pytest
from alice_renderer.model import RenderSettings
from alice_renderer.geometry_selection import render_choices,is_schematic
from alice_renderer.scene_config import recipe,resolve_settings,save_config,load_config
from alice_renderer.runtime import preflight

def test_full_choice_overrides_schematic_and_outline_without_changing_preview(tmp_path):
    asset=tmp_path/'TPC.blend';asset.write_bytes(b'geometry-contract-fixture')
    preview=RenderSettings(geometry=['TPC'],schematic=True,geometry_lod='simplified',geometry_display={'TPC':'outline'},geometry_assets={'TPC':str(asset)})
    final=render_choices(preview,{'TPC':'full'})
    assert not is_schematic(final.to_dict(),'TPC')
    assert final.geometry_lods['TPC']=='full' and final.geometry_display['TPC']=='surfaces'
    assert preview.schematic and preview.geometry_display['TPC']=='outline' and preview.geometry_lods=={}
    data=recipe(final);assert 'TPC' in data['geometry']
    path=tmp_path/'final.json';save_config(path,data)
    restored=resolve_settings(load_config(path),path)
    assert not is_schematic(restored.to_dict(),'TPC') and restored.geometry_lods['TPC']=='full'

def test_mixed_detector_and_magnet_modes_and_current_are_unambiguous(tmp_path):
    cfg=RenderSettings(geometry=['ITS','TPC'],magnet=True,schematic=True,geometry_display={'TPC':'outline'})
    unchanged=render_choices(cfg,{'ITS':'current','TPC':'current','L3':'current'})
    assert unchanged.to_dict()==cfg.to_dict()
    final=render_choices(cfg,{'ITS':'schematic','TPC':'simplified','L3':'full'})
    assert is_schematic(final.to_dict(),'ITS')
    assert not is_schematic(final.to_dict(),'TPC') and not is_schematic(final.to_dict(),'L3')
    assert final.geometry_lods=={'TPC':'simplified','L3':'full'}
    assert final.geometry_display['TPC']=='surfaces'
    with pytest.raises(ValueError):RenderSettings(geometry_schematics={'TPC':'false'}).validate()

def test_full_choice_missing_aligned_geometry_stops_at_preflight(tmp_path):
    cfg=render_choices(RenderSettings(detectors=[],geometry=['TPC'],schematic=True),{'TPC':'full'})
    errors=preflight(cfg,[{'id':'E','kind':'collision','tracks':[],'clusters':[]}],{'version':[5,0,0],'devices':[{'type':'CPU'}]},tmp_path)
    assert any('TPC: provide detector geometry' in e for e in errors)

def test_camera_projection_parameters_are_portable(tmp_path):
    pose={'matrix_world':[[1,0,0,4],[0,1,0,5],[0,0,1,6],[0,0,0,1]],'lens':92.,'ortho_scale':7.,'sensor_width':43.,'sensor_height':29.,'sensor_fit':'VERTICAL','shift_x':.1,'shift_y':-.2,'clip_start':.05,'clip_end':1234.}
    cfg=RenderSettings(camera_pose=pose);path=tmp_path/'scene.json';save_config(path,recipe(cfg))
    assert resolve_settings(load_config(path),path).camera_pose==pose
    with pytest.raises(ValueError):RenderSettings(camera_pose={**pose,'sensor_fit':'bad'}).validate()

def test_schematic_recipe_retains_supplied_assets_for_later_full_render(tmp_path):
    asset=tmp_path/'TPC.blend';asset.write_bytes(b'geometry-contract-fixture')
    cfg=RenderSettings(geometry=['TPC'],schematic=True)
    restored=resolve_settings(recipe(cfg),tmp_path/'scene.json',asset_overrides={'TPC':str(asset)})
    assert restored.geometry_assets['TPC']==str(asset)
    assert recipe(render_choices(restored,{'TPC':'full'}))['geometry']['TPC']['file']=='TPC.blend'
    invalid=recipe(cfg);invalid['scene']['schematic']=False
    with pytest.raises(ValueError,match='geometry references'):
        resolve_settings(invalid,tmp_path/'scene.json',asset_overrides={'TPC':str(asset)})
