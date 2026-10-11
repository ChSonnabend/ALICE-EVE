import copy,gzip,json,math,shutil
import pytest
from alice_renderer.model import RenderSettings
from alice_renderer.scene_config import recipe,resolve_settings,sha256
from alice_renderer.structural_geometry import load,sidecar_path,supported_components
from alice_renderer.geometry_components import sidecar_path as component_path
from alice_renderer.geometry_selection import render_choices,description
from alice_renderer.runtime import preflight


def bundle(root):
    root.mkdir(exist_ok=True);asset=root/'TPC.blend';asset.write_bytes(b'aligned-native-source')
    components={'schema':'alice-geometry-components','version':1,'asset_sha256':sha256(asset),'groups':{},'components':{'structures/outer_wall':{}}}
    with gzip.open(component_path(asset),'wt') as f:json.dump(components,f)
    data={'schema':'alice-structural-geometry','version':1,'detector':'TPC','source_units':'m',
          'asset_sha256':sha256(asset),'components_sha256':sha256(component_path(asset)),
          'groups':[{'tags':['structures/outer_wall'],'vertices':[[0,0,0],[1,0,0],[0,1,0]],'faces':[[0,1,2]]}]}
    data['track_region']={'units':'cm','planes':[[math.cos(i*math.tau/64),math.sin(i*math.tau/64),0,100] for i in range(64)]+[[0,0,1,100],[0,0,-1,100]]}
    with gzip.open(sidecar_path(asset),'wt') as f:json.dump(data,f)
    return asset,data


def test_cached_recipe_relocates_and_requires_identical_source_and_proxy(tmp_path):
    asset,data=bundle(tmp_path/'mac')
    cfg=RenderSettings(detectors=[],geometry=['TPC'],geometry_assets={'TPC':str(asset)},geometry_units='m',geometry_lods={'TPC':'structural'})
    scene=recipe(cfg);assert 'structural' in scene['geometry']['TPC']
    linux=tmp_path/'linux';shutil.copytree(asset.parent,linux)
    other=resolve_settings(scene,tmp_path/'scene.json',linux)
    assert other.geometry_lods=={'TPC':'structural'} and load(linux/'TPC.blend')['asset_sha256']==sha256(asset)
    assert supported_components(data)=={'structures','structures/outer_wall'}
    missing=copy.deepcopy(scene);del missing['geometry']['TPC']['structural']
    with pytest.raises(ValueError,match='cache reference'):resolve_settings(missing,tmp_path/'scene.json',linux)
    with gzip.open(sidecar_path(linux/'TPC.blend'),'wt') as f:json.dump({**data,'version':2},f)
    with pytest.raises(ValueError,match='identical large-surface cache'):resolve_settings(scene,tmp_path/'scene.json',linux)
    asset.write_bytes(b'changed-alignment')
    with pytest.raises(ValueError,match='differs'):load(asset)


def test_cache_missing_units_and_invalid_vertices_are_actionable(tmp_path):
    asset,data=bundle(tmp_path)
    with pytest.raises(ValueError,match='units differ'):load(asset,'cm')
    data['groups'][0]['vertices'][0][0]=float('nan')
    with gzip.open(sidecar_path(asset),'wt') as f:json.dump(data,f)
    with pytest.raises(ValueError,match='vertices'):load(asset)
    sidecar_path(asset).unlink()
    with pytest.raises(ValueError,match='prepare-geometry'):load(asset)


def test_structural_render_override_and_preflight_stop_before_missing_cache(tmp_path):
    asset,_=bundle(tmp_path)
    cfg=RenderSettings(detectors=[],geometry=['TPC'],geometry_assets={'TPC':str(asset)},geometry_units='m')
    changed=render_choices(cfg,{'TPC':'structural'})
    assert cfg.geometry_lods=={} and changed.geometry_lods=={'TPC':'structural'}
    assert 'cached' in description(changed.to_dict(),'TPC')
    sidecar_path(asset).unlink()
    errors=preflight(changed,[{'id':'empty','kind':'synthetic','tracks':[],'clusters':[]}],{'version':[5,0,0],'devices':[{'type':'CPU','id':'CPU'}]},tmp_path/'renders')
    assert any('prepare-geometry' in e for e in errors)
