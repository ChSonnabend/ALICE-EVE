import json
from dataclasses import replace
from pathlib import Path
import pytest
from alice_renderer.model import RenderSettings
from alice_renderer.scene_config import recipe,save_config,load_config,resolve_settings,quality_settings,choose_event,recommended_quality


def test_portable_scene_roundtrip_and_geometry_relocation(tmp_path):
    first=tmp_path/'mac';first.mkdir();asset=first/'TPC.blend';asset.write_bytes(b'aligned fixture')
    cfg=RenderSettings(detectors=['TPC'],geometry=['TPC'],geometry_assets={'TPC':str(asset)},geometry_units='m',backend='METAL',device='local-device',width=800,height=600,geometry_openings={'TPC':137},geometry_opacities={'TPC':.22},camera_pose={'matrix_world':[[1.,0,0,4],[0,1.,0,5],[0,0,1.,6],[0,0,0,1.]],'lens':52.,'ortho_scale':10.})
    event={'tracks':[{'detectors':['TPC'],'kinematics':{'pt':1.2}},{'detectors':['TPC'],'kinematics':{'pt':8.4}}],'clusters':[]}
    cfg.track_color_mode='pt'
    data=recipe(cfg,event);path=tmp_path/'scene.json';save_config(path,data)
    serialized=path.read_text();assert str(first) not in serialized;assert 'METAL' not in serialized;assert 'local-device' not in serialized
    assert data['defaults']=={};assert data['scene']['color_ranges']['tracks']==[1.2,8.4]
    linux=tmp_path/'linux';linux.mkdir();(linux/'TPC.blend').write_bytes(asset.read_bytes())
    other=resolve_settings(load_config(path),path,linux)
    assert other.camera_pose==cfg.camera_pose;assert other.geometry_openings==cfg.geometry_openings;assert other.backend=='CPU'
    rendered=quality_settings(other,'final',backend='HIP')
    assert rendered.width==3840 and rendered.height==2880 and rendered.samples==512
    assert rendered.camera_pose==cfg.camera_pose and rendered.colors==cfg.colors
    (linux/'TPC.blend').write_bytes(b'different alignment')
    with pytest.raises(ValueError,match='hash differs'):resolve_settings(data,path,linux)


def test_reject_unknown_machine_settings_and_nonfinite(tmp_path):
    data=recipe(RenderSettings())
    data['scene']['backend']='CPU'
    with pytest.raises(ValueError,match='machine-specific'):save_config(tmp_path/'bad.json',data)
    with pytest.raises(ValueError):RenderSettings(lights=[{'position_m':[0,0,0],'energy':float('nan'),'size_m':1,'color':'#ffffff'}]).validate()
    with pytest.raises(ValueError):RenderSettings(geometry_openings={'TPC':361}).validate()


def test_event_selection_requires_instance_choice_and_id_wins():
    class Cat:
        def rows(self):return [{'ordinal':0,'event_id':'1'},{'ordinal':1,'event_id':'RUN-TF-PV2'}]
        def event_path(self,i):return Path(str(i))
    with pytest.raises(ValueError,match='Specify'):choose_event(Cat(),None)
    assert choose_event(Cat(),'1')==Path('0')
    assert choose_event(Cat(),'ordinal:1')==Path('1')
    with pytest.raises(ValueError):choose_event(Cat(),'missing')


def test_quality_backend_recommendations_and_fixed_ranges():
    assert recommended_quality({'devices':[{'type':'CPU'}]})['quality']=='draft'
    assert recommended_quality({'devices':[{'type':'METAL'},{'type':'CPU'}]})['backend']=='METAL'
    cfg=RenderSettings(color_ranges={'tracks':[2,2]})
    assert recipe(cfg)['scene']['color_ranges']['tracks']==[2,2]
    assert quality_settings(cfg,'draft').width==640


def test_detector_display_styles_are_portable():
    cfg=RenderSettings(geometry_display={'TPC':'shell','ITS':'outline'})
    data=recipe(cfg)
    assert data['scene']['geometry_display']==cfg.geometry_display
    assert resolve_settings(data,Path('scene.json')).geometry_display==cfg.geometry_display
    with pytest.raises(ValueError,match='display style'):RenderSettings(geometry_display={'TPC':'dots'}).validate()


def test_interactive_launch_keeps_full_aligned_geometry(tmp_path,monkeypatch):
    from alice_renderer import runtime
    class Process:pid=42
    monkeypatch.setattr(runtime,'probe',lambda _: {'version':[5,0,0],'devices':[{'type':'CPU'}]})
    monkeypatch.setattr(runtime,'preflight',lambda *args: [])
    monkeypatch.setattr(runtime.subprocess,'Popen',lambda *args,**kwargs:Process())
    event=tmp_path/'event.json';event.write_text(json.dumps({'id':'fixture','tracks':[],'clusters':[]}))
    (tmp_path/'outputs').mkdir()
    folder,pid=runtime.launch_editor('blender',event,RenderSettings(geometry_lod='full'),tmp_path/'outputs')
    assert pid==42
    assert json.loads((folder/'job.json').read_text())['settings']['geometry_lod']=='full'


def test_portable_display_colours_glow_and_lens(tmp_path):
    cfg=RenderSettings(view_transform='Standard',exposure=-.5,track_emission=.2,cluster_emission=.8,camera_lens_mm=36)
    path=tmp_path/'scene.json';save_config(path,recipe(cfg));restored=resolve_settings(load_config(path),path)
    assert (restored.view_transform,restored.exposure,restored.track_emission,restored.cluster_emission,restored.camera_lens_mm)==('Standard',-.5,.2,.8,36)
    for kwargs in ({'view_transform':'bad'},{'exposure':float('nan')},{'cluster_emission':-1},{'track_emission':float('inf')},{'camera_lens_mm':0}):
        with pytest.raises(ValueError):RenderSettings(**kwargs).validate()
def test_component_masks_and_opening_direction_roundtrip():
    from alice_renderer.model import RenderSettings
    from alice_renderer.scene_config import recipe,validate_recipe
    cfg=RenderSettings(geometry_opening_directions={'ITS':29.},geometry_exclusions={'ITS':['ITSServices*','Cage*']},geometry_inner_masks={'TPC':{'radius_m':1.,'patterns':['TPC_ring*'],'front_only':True}})
    data=recipe(cfg)
    actual=RenderSettings(**validate_recipe(data)['scene'])
    assert actual.geometry_opening_directions==cfg.geometry_opening_directions
    assert actual.geometry_exclusions==cfg.geometry_exclusions
    assert actual.geometry_inner_masks==cfg.geometry_inner_masks


@pytest.mark.parametrize('values',[{'geometry_opening_directions':{'TPC':float('nan')}},{'geometry_exclusions':{'ITS':'Cage*'}},{'geometry_exclusions':{'ITS':['']}},{'geometry_inner_masks':{'TPC':{'radius_m':-1,'patterns':['*']}}},{'geometry_inner_masks':{'TPC':{'radius_m':1,'patterns':'*'}}},{'geometry_inner_masks':{'TPC':{'radius_m':1,'patterns':['*'],'front_only':'yes'}}}])
def test_invalid_structural_visibility_settings(values):
    from alice_renderer.model import RenderSettings
    with pytest.raises(ValueError):RenderSettings(**values).validate()


def test_raster_engine_survives_portable_recipe(tmp_path):
    settings=RenderSettings(render_engine='BLENDER_EEVEE')
    path=tmp_path/'raster.json'
    save_config(path,recipe(settings))
    restored=resolve_settings(load_config(path),path)
    assert restored.render_engine=='BLENDER_EEVEE'
    assert quality_settings(restored,'balanced').render_engine=='BLENDER_EEVEE'
    with pytest.raises(ValueError,match='render engine'):
        RenderSettings(render_engine='unsupported').validate()
