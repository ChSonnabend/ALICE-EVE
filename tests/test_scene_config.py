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
