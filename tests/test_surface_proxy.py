import gzip,json
from pathlib import Path
import pytest
from alice_renderer.surface_proxy import load,sidecar_path
from alice_renderer.scene_config import sha256,recipe,resolve_settings
from alice_renderer.model import RenderSettings
from alice_renderer.runtime import fast_editor_settings


def fixture_cache(tmp_path,name='TRD'):
    asset=tmp_path/(name+'.blend');asset.write_bytes(b'test asset')
    metadata=Path(str(asset)+'.components.json.gz');metadata.write_bytes(b'component source')
    data=dict(schema='alice-surface-proxy',version=1,detector=name,source_units='m',asset_sha256=sha256(asset),components_sha256=sha256(metadata),groups=[dict(name='panel',vertices=[[0,0,0],[1,0,0],[0,1,0]],faces=[[0,1,2]],tags=[],source_names=['panel'],elements=1)],track_region=None)
    with gzip.open(sidecar_path(asset),'wt') as stream:json.dump(data,stream)
    return asset,data


def test_cached_proxy_validation_and_stale_source(tmp_path):
    asset,data=fixture_cache(tmp_path)
    assert load(asset)['detector']=='TRD'
    assert load(asset) is load(asset)
    with pytest.raises(ValueError,match='units'):load(asset,'cm')
    asset.write_bytes(b'changed source')
    with pytest.raises(ValueError,match='differ'):load(asset)


def test_bad_faces_rejected(tmp_path):
    asset,data=fixture_cache(tmp_path);data['groups'][0]['faces']=[[0,1,99]]
    with gzip.open(sidecar_path(asset),'wt') as stream:json.dump(data,stream)
    with pytest.raises(ValueError,match='faces'):load(asset)


def test_fast_editor_includes_magnet_and_preserves_masks(tmp_path):
    trd,_=fixture_cache(tmp_path,'TRD');magnet,_=fixture_cache(tmp_path,'L3')
    cfg=RenderSettings(geometry=['TRD'],magnet=True,geometry_units='m',geometry_assets={'TRD':str(trd),'L3':str(magnet)})
    assert fast_editor_settings(cfg).geometry_lods=={'TRD':'proxy','L3':'proxy'}
    assert cfg.geometry_lods=={}
    cfg.geometry_inner_masks={'TRD':{'radius_m':1}}
    assert fast_editor_settings(cfg).geometry_lods=={'L3':'proxy'}


def test_all_reviewed_assets_resolve_and_roundtrip():
    root=Path(__file__).resolve().parents[1]/'geometry/run-560067'
    if not (root/'TRD.blend.surface.json.gz').exists():pytest.skip('prepared geometry not installed')
    assets={p.stem:str(p) for p in root.glob('*.blend')}
    cfg=RenderSettings(detectors=[],geometry=[n for n in assets if n!='L3'],magnet=True,geometry_assets=assets,geometry_units='m')
    fast=fast_editor_settings(cfg)
    assert set(fast.geometry_lods)==set(assets)
    assert set(fast.geometry_lods.values())=={'proxy'}
    data=recipe(fast)
    assert all('surface' in ref for ref in data['geometry'].values())
    restored=resolve_settings(data,root/'unused-config.json',root)
    assert restored.geometry_lods==fast.geometry_lods
    for asset in assets.values():assert load(asset)['track_region']['units']=='cm'
