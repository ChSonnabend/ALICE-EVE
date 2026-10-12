import json,sqlite3
import numpy as np
import pytest
from alice_renderer.calorimeter_towers import tower,validate_cell_geometry
from alice_renderer.model import RenderSettings,validate_event,color_value,capabilities
from alice_renderer.scene_config import recipe,resolve_settings
from alice_renderer.catalogue import Catalogue

def cell(name='EMC',energy=2.):
    return dict(id='cell',detector=name,position=[440.,0.,30.],energy=energy,
                measurement_kind='calorimeter_cell',cell_geometry={'u_cm':[0,6.,0],'v_cm':[0,0,6.],'basis':'aligned test module'})

def settings(**kwargs):return RenderSettings(calorimeter_display={'EMC':'signal towers','PHS':'signal towers','CPV':'signal towers'},**kwargs).to_dict()

def test_aligned_tower_base_height_direction_and_cap():
    c=cell();s=settings();g=tower(c,s);v=np.array(g['vertices'])*100
    assert np.mean(v[:4],axis=0)==pytest.approx(c['position'])
    assert np.mean(v[4:],axis=0)==pytest.approx([400,0,30])
    assert g['height_cm']==40 and not g['approximate']
    assert np.ptp(v[:4,1])==pytest.approx(6*.95)
    # Every face has outward winding, for either extrusion direction.
    for direction in ('inward','outward'):
        g=tower(c,{**s,'tower_direction':direction});v=np.array(g['vertices'])
        centre=np.mean(v,axis=0)
        for face in g['faces']:
            p=v[list(face)];assert np.dot(np.cross(p[1]-p[0],p[2]-p[0]),p.mean(axis=0)-centre)>0
    assert tower(cell(energy=100),s)['height_cm']==100
    assert tower(cell(energy=100),s)['clipped']

def test_nominal_footprint_fixed_height_and_missing_signal_fallbacks():
    c=cell();del c['cell_geometry'];g=tower(c,settings())
    assert g['approximate'] and 'approximation' in g['basis']
    for energy in (None,0,-1,float('nan')):
        assert tower(cell(energy=energy),settings()) is None
    s=settings();s['calorimeter_display']['EMC']='fixed towers';s['tower_fixed_height_cm']=17
    assert tower(cell(energy=None),s)['height_cm']==17
    assert tower(cell(),RenderSettings().to_dict()) is None
    assert tower({**cell(),'detector':'TPC'},settings()) is None

def test_phos_alias_and_cpv_amplitude_are_distinct_from_energy():
    raw=dict(schema_version=1,units='cm',kind='timeframe',id='QA',tracks=[],clusters=[cell('PHOS')])
    c=validate_event(raw)['clusters'][0]
    assert c['detector']=='PHS' and tower(c,settings())['height_cm']==pytest.approx(.4)
    c=cell('CPV');c.update(amplitude=30,measurement_kind='cpv_cluster')
    g=tower(c,settings());assert g['height_cm']==6 and g['signal_field']=='amplitude'
    assert g['measurement_kind']=='cpv_cluster'
    assert color_value(c,'energy') is None and color_value(c,'amplitude')==30
    assert 'energy' in capabilities([cell()]) and 'amplitude' in capabilities([c])
    del c['amplitude'];assert tower(c,settings()) is None

def test_old_o2_phos_adc_is_never_labeled_gev():
    c=cell('PHS',energy=50);c['coordinate_basis']='O2 detector converter and aligned geometry'
    assert color_value(c,'energy') is None and color_value(c,'amplitude')==50
    g=tower(c,settings());assert g['height_cm']==10 and g['signal_unit']=='ADC'
    c['energy_unit']='GeV'
    assert color_value(c,'energy')==50 and color_value(c,'amplitude') is None
    c.pop('energy');c['amplitude']=60;c['amplitude_unit']='ADC'
    assert tower(c,settings())['signal_unit']=='ADC'

def test_unsupported_energy_unit_is_not_silently_labeled_gev():
    c=cell();c['energy_unit']='MeV'
    assert color_value(c,'energy') is None and tower(c,settings()) is None

@pytest.mark.parametrize('change',[{'u_cm':[0,0,0]},{'v_cm':[0,12,0]},{'basis':''},{'u_cm':[0,float('nan'),0]}])
def test_invalid_cell_frames_rejected(change):
    with pytest.raises(ValueError):validate_cell_geometry({**cell()['cell_geometry'],**change})

@pytest.mark.parametrize('change',[{'calorimeter_display':{'ITS':'signal towers'}},{'calorimeter_display':{'EMC':'unknown'}},{'tower_height_scales':{'EMC':-1}},{'tower_width_scale':0},{'tower_max_height_cm':float('nan')},{'tower_direction':'unknown'}])
def test_invalid_display_settings_rejected(change):
    with pytest.raises(ValueError):RenderSettings(**change).validate()

def test_portable_tower_recipe_round_trip():
    cfg=RenderSettings(calorimeter_display={'EMC':'signal towers','PHS':'fixed towers','CPV':'points'},tower_height_scales={'EMC':3.,'CPV':.5},tower_direction='outward',tower_max_height_cm=200,tower_width_scale=.8)
    data=recipe(cfg);restored=resolve_settings(data,'unused.json')
    for key in ('calorimeter_display','tower_height_scales','tower_direction','tower_max_height_cm','tower_width_scale'):
        assert getattr(restored,key)==getattr(cfg,key)

def test_existing_catalogue_gains_cell_scalars_without_reimport(tmp_path):
    source=tmp_path/'cells.json';source.write_text(json.dumps(dict(schema_version=1,units='cm',kind='timeframe',id='QA',tracks=[],clusters=[cell()])))
    cat=Catalogue.build(source,tmp_path/'cache');path=cat.event_path(0);before=path.stat().st_mtime_ns
    with sqlite3.connect(cat.db) as db:
        db.execute("DELETE FROM metadata WHERE key='calorimeter_capabilities'")
        db.execute("UPDATE events SET cluster_fields='[\"solid\"]'")
    restored=Catalogue.build(source,tmp_path/'cache')
    assert restored.folder==cat.folder and path.stat().st_mtime_ns==before
    assert 'energy' in json.loads(restored.rows()[0]['cluster_fields'])
