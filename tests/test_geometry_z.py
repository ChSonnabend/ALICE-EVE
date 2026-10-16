from pathlib import Path
import pytest
from alice_renderer.model import RenderSettings
from alice_renderer.scene_config import recipe,resolve_settings


def test_z_and_pipe_portable_roundtrip():
    cfg=RenderSettings(geometry_z_intervals_cm={'ITS':[-20,45],'TPC':[-250,0],'L3':[0,400]},beampipe=True,beampipe_radius_cm=1.8,beampipe_z_cm=[-350,350])
    cfg.validate()
    restored=resolve_settings(recipe(cfg),Path('scene.json'))
    assert restored.geometry_z_intervals_cm==cfg.geometry_z_intervals_cm
    assert restored.beampipe and restored.beampipe_z_cm==[-350,350]
    assert RenderSettings().geometry_z_intervals_cm=={} and not RenderSettings().beampipe

@pytest.mark.parametrize('interval',[[],[0],[1,0],[1,1],[0,float('nan')],[True,2],['0',2]])
def test_bad_z_intervals(interval):
    with pytest.raises(ValueError,match='z interval'):RenderSettings(geometry_z_intervals_cm={'TPC':interval}).validate()

@pytest.mark.parametrize('kw',[{'beampipe_wall_cm':2},{'beampipe_radius_cm':0},{'beampipe_z_cm':[2,1]},{'beampipe_color':None}])
def test_bad_pipe(kw):
    with pytest.raises(ValueError,match='Beampipe|beampipe'):RenderSettings(**kw).validate()


def test_fine_geometry_can_use_fast_viewport_without_proxy_substitution(tmp_path):
    from alice_renderer.runtime import fast_editor_settings
    assets={}
    for name in ('ITS','TPC'):
        path=tmp_path/(name+'.blend');path.write_bytes(b'geometry fixture');assets[name]=str(path)
    cfg=RenderSettings(geometry=['ITS','TPC'],geometry_assets=assets,geometry_lods={'ITS':'full','TPC':'full'},preview_preserve_geometry=True)
    fast=fast_editor_settings(cfg)
    assert fast.geometry_lods==cfg.geometry_lods and fast is not cfg
    assert resolve_settings(recipe(cfg),tmp_path/'scene.json',asset_overrides=assets).preview_preserve_geometry


def test_opening_window_is_separate_from_geometry_trim():
    cfg=RenderSettings(geometry_opening_z_intervals_cm={'TPC':[-27.11,12.89]},geometry_z_intervals_cm={'TPC':[-260,260]})
    restored=resolve_settings(recipe(cfg),Path('scene.json'))
    assert restored.geometry_opening_z_intervals_cm==cfg.geometry_opening_z_intervals_cm
    assert restored.geometry_z_intervals_cm==cfg.geometry_z_intervals_cm
    with pytest.raises(ValueError):RenderSettings(geometry_opening_z_intervals_cm={'TPC':[20,-20]}).validate()
