import json,math
from pathlib import Path
import numpy as np
import pytest
from alice_renderer.model import RenderSettings,validate_event
from alice_renderer.video import schedule,event_at,relative_times,prepare_event,ORBIT_US,BUNCH_NS
from alice_renderer.track_clipping import prepare_regions,clip_polyline
from alice_renderer.scene_config import recipe,resolve_settings
from alice_renderer.runtime import check_encoder,prepare_video

def event(identity='A',**kw):return {**dict(id=identity,kind='collision',vertex=[0,0,0],run=560067,timeframe=1,tracks=[],clusters=[]),**kw}

def test_fixed_intervals_replacement_and_last_hold():
    plan=schedule([event(),event('B')],RenderSettings(video_enabled=True,video_interval_s=5,video_fps=10).to_dict())
    assert [e['frame_start'] for e in plan['entries']]==[0,50] and plan['frames']==100
    assert event_at(plan,49)==(0,4.9) and event_at(plan,50)==(1,0.)

def test_auto_source_timing_is_chronological_and_averages_one_event_per_second():
    events=[event('late',orbit=100,vertex_time_us=3),event('early',orbit=100,vertex_time_us=1),event('middle',orbit=100,vertex_time_us=2)]
    plan=schedule(events,RenderSettings(video_timing='realtime').to_dict())
    assert [e['event_id'] for e in plan['entries']]==['early','middle','late']
    assert [e['start_s'] for e in plan['entries']]==[0,1,2]
    assert plan['time_scale']==pytest.approx(1e6) and plan['duration_s']==3

def test_fine_time_combines_tf_orbits_or_aod_bc_with_collision_offsets():
    values,basis=relative_times([event(orbit=100,vertex_time_us=1),event('B',orbit=101,vertex_time_us=2)])
    assert values[1]==pytest.approx((ORBIT_US+1)*1e-6)
    values,basis=relative_times([event(global_bc=500,collision_time_ns=1),event('B',global_bc=501,collision_time_ns=2)])
    assert values[1]==pytest.approx((BUNCH_NS+1)*1e-9)
    with pytest.raises(ValueError,match='timestamps'):relative_times([event(calibration_timestamp_ms=0),event('B',calibration_timestamp_ms=1)])
    with pytest.raises(ValueError,match='timestamp'):relative_times([event(timeframe=None,vertex_time_us=1),event('B',timeframe=None,vertex_time_us=2)])

def test_coincident_subframe_events_each_get_a_frame():
    events=[event(str(i),orbit=100,vertex_time_us=1) for i in range(3)]
    plan=schedule(events,RenderSettings(video_timing='realtime',video_time_scale=1).to_dict())
    assert [e['frame_start'] for e in plan['entries']]==[0,1,2]
    assert plan['quantized_collisions']==2
    with pytest.raises(ValueError,match='Identical'):schedule(events,RenderSettings(video_timing='realtime').to_dict())

def test_linked_hits_follow_the_path_even_with_tracks_hidden_and_unlinked_hits_use_pv_wave():
    raw=event();raw['tracks']=[dict(id='T',detectors=['TPC'],points=[[0,0,0],[100,0,0],[100,100,0]])]
    raw['clusters']=[dict(detector='TPC',position=[100,100,0],track_id='T'),dict(detector='TPC',position=[100,100,0])]
    cfg=RenderSettings(detectors=['TPC'],mode='clusters',video_speed_m_s=1).to_dict();result=prepare_event(raw,cfg)
    assert result['tracks']==[] and result['linked_clusters']==1 and result['unlinked_clusters']==1
    assert result['cluster_arrival_s']==pytest.approx([2,math.sqrt(2)])

def test_clipping_preserves_distance_to_detector_entry_without_drawing_gaps():
    regions=prepare_regions({'TPC':dict(planes=[[1,0,0,150],[-1,0,0,-50],[0,1,0,10],[0,-1,0,10],[0,0,1,10],[0,0,-1,10]])})
    pieces=clip_polyline([[0,0,0],[100,0,0],[200,0,0]],list(regions.values()),distances=[0,100,200])
    assert len(pieces)==1 and np.asarray(pieces[0]['points'])[:,0].tolist()==[50,100,150]
    assert pieces[0]['distances']==[50,100,150]

@pytest.mark.parametrize('values',[{'video_fps':0},{'video_speed_m_s':0},{'video_tower_rise_s':float('nan')},{'video_interval_s':-1},{'video_time_scale':-1},{'video_timing':'guess'}])
def test_invalid_controls_fail_before_render(values):
    with pytest.raises(ValueError):RenderSettings(**values).validate()

def test_video_config_keeps_controls_without_event_list():
    cfg=RenderSettings(video_enabled=True,video_timing='realtime',video_interval_s=5,video_speed_m_s=20,video_fps=30)
    data=recipe(cfg);assert 'events' not in data and not data['defaults']
    restored=resolve_settings(data,'unused.json');assert restored.video_enabled and restored.video_interval_s==5 and restored.video_fps==30

def test_missing_encoder_and_missing_vertices_are_caught_before_scene_render(tmp_path):
    with pytest.raises(ValueError,match='FFmpeg'):check_encoder(str(tmp_path/'missing-ffmpeg'))
    e=event();e['vertex']=None
    with pytest.raises(ValueError,match='vertex'):schedule([e,event('B')],RenderSettings().to_dict())

def test_encoder_startup_failure_is_distinguished_from_missing_codec(tmp_path,monkeypatch):
    import subprocess
    encoder=tmp_path/'ffmpeg';encoder.touch()
    monkeypatch.setattr('alice_renderer.runtime.subprocess.run',lambda *a,**k:subprocess.CompletedProcess(a,134,'','Library not loaded: x265'))
    with pytest.raises(ValueError,match='Library not loaded'):check_encoder(str(encoder))
    monkeypatch.setattr('alice_renderer.runtime.subprocess.run',lambda *a,**k:subprocess.CompletedProcess(a,0,' V..... mpeg4 MPEG-4',''))
    with pytest.raises(ValueError,match='lacks libx264'):check_encoder(str(encoder))

def test_preparation_locks_colour_ranges_across_all_events_and_checks_selected_detectors(tmp_path):
    paths=[]
    for i,pt in enumerate((1.,4.)):
        e=event(str(i));e.update(schema_version=1,units='cm');e['tracks']=[dict(id='T',detectors=['TPC'],points=[[100,0,0],[150,0,0]],kinematics={'pt':pt})]
        p=tmp_path/(str(i)+'.json');p.write_text(json.dumps(e));paths.append(p)
    cfg=RenderSettings(video_enabled=True,schematic=True,detectors=['TPC'],track_color_mode='pt')
    ready,payload=prepare_video(cfg,paths,{'version':[5,0],'devices':[{'type':'CPU','id':'CPU'}]},tmp_path/'output')
    assert ready.color_ranges['tracks']==[1,4] and payload['required_track_detectors']==['TPC']
    assert len(payload['events'])==2 and payload['video_plan']['duration_s']==2

def test_collisions_without_selected_data_still_replace_previous_data(tmp_path):
    paths=[]
    for i in range(2):
        e=event(str(i));e.update(schema_version=1,units='cm')
        if i==0:e['tracks']=[dict(id='T',detectors=['TPC'],points=[[100,0,0],[150,0,0]],kinematics={'pt':2})]
        p=tmp_path/(str(i)+'.json');p.write_text(json.dumps(e));paths.append(p)
    cfg=RenderSettings(video_enabled=True,schematic=True,detectors=['TPC'],track_color_mode='pt')
    ready,payload=prepare_video(cfg,paths,{'version':[5,0],'devices':[{'type':'CPU','id':'CPU'}]},tmp_path/'output')
    assert len(payload['video_plan']['entries'])==2 and ready.color_ranges['tracks']==[2,2]
