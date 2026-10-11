import gzip,json
import pytest
from alice_renderer.geometry_components import tags_for,component_state,load_components,sidecar_path
from alice_renderer.model import RenderSettings
from alice_renderer.scene_config import recipe,resolve_settings,sha256

def test_shared_its_prototype_and_mft_disk_ancestry():
    for layer in range(3,7):
        tags=tags_for('ITS',f'/barrel/ITSULayer{layer}_1/Stave_1','ITSUChip3',{'x':0,'y':0})
        assert f'layers/layer_{layer}' in tags
        assert component_state(tags,{'layers/layer_4':False})[0]==(layer!=4)
    assert 'layers/layer_4' in tags_for('MFT','/MFT_0/MFT_H_1_1/MFT_D_1_4_4/Chip_1','chip',{'x':0,'y':0})

def test_tpc_shared_inner_outer_rod_and_ancestor_veto():
    for radius,kind in [(81.5,'inner_rods'),(254,'outer_rods')]:
        tags=tags_for('TPC','/TPC/TPC_rod_1','TPC_rod',{'x':radius,'y':0})
        assert 'structures/'+kind in tags
    assert component_state(['structures/inner_wall'],{'structures/inner_wall':True})==(True,True)
    assert component_state(['structures/inner_wall'],{'structures':False,'structures/inner_wall':True})==(False,True)
    with pytest.raises(ValueError,match='component'):RenderSettings(geometry_components={'ITS':{'layers/layer_0':1}}).validate()

def test_portable_component_binding_and_missing_bundle(tmp_path):
    asset=tmp_path/'ITS.blend';asset.write_bytes(b'fixture')
    metadata={'schema':'alice-geometry-components','version':1,'asset_sha256':sha256(asset),'components':{'layers/layer_0':{}},'groups':{}}
    with gzip.open(sidecar_path(asset),'wt') as f:json.dump(metadata,f)
    cfg=RenderSettings(detectors=[],geometry=['ITS'],geometry_assets={'ITS':str(asset)},geometry_components={'ITS':{'layers/layer_0':False}})
    config=recipe(cfg);assert config['geometry']['ITS']['components']['sha256']==sha256(sidecar_path(asset))
    restored=resolve_settings(config,tmp_path/'scene.json');assert restored.geometry_components==cfg.geometry_components
    cfg.geometry_components={'ITS':{'nonexistent':False}}
    with pytest.raises(ValueError,match='unknown'):recipe(cfg)
    asset.write_bytes(b'changed')
    with pytest.raises(ValueError,match='does not match'):load_components(asset)
    asset.write_bytes(b'fixture');sidecar_path(asset).unlink()
    with pytest.raises(ValueError,match='metadata'):resolve_settings(config,tmp_path/'scene.json')

def test_default_legacy_masks_and_shared_layer_mixed_state():
    from alice_renderer.geometry_components import component_visibility
    meta={'components':{k:{} for k in ['layers','layers/layer_3','layers/layer_4','structures','structures/inner_wall']},'groups':{'Chip_instancer':{'ids':[0,1],'classes':[['layers/layer_3'],['layers/layer_4']]},'TPC_IFC_instancer':{'ids':[0],'classes':[['structures/inner_wall']]}}}
    states=component_visibility(meta,{'layers/layer_4':False},['TPC_IFC*']);assert states['layers'] is None and states['layers/layer_3'] is True and states['structures/inner_wall'] is False
    states=component_visibility(meta,{'structures/inner_wall':True},['TPC_IFC*']);assert states['structures/inner_wall'] is True

def test_index_counts_overlapping_facets_once_per_placement():
    from alice_renderer.geometry_components import index_from_export
    data={'Cage-0':{'positions':[{'component_tags':['structures/supports','structures/cage'],'translation':{'x':1,'y':2,'z':3},'source_path':'/barrel/ITS/Cage_0'}]}}
    index=index_from_export(data,'ITS','root-digest');assert index['components']['structures']['count']==1
    assert index['components']['structures/cage']['count']==1
    assert index['groups']['Cage-0_instancer']['ids']==[0]
