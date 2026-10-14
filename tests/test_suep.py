import importlib.util
from pathlib import Path
import pytest
from alice_renderer.object_selection import parse_event_highlights,highlighted,event_highlight_ids
from alice_renderer.model import RenderSettings

spec=importlib.util.spec_from_file_location('suep',Path(__file__).resolve().parents[1]/'projects/SUEP/select_tracks.py')
suep=importlib.util.module_from_spec(spec);spec.loader.exec_module(suep)


def test_hepmc_gate_proton_exclusion_and_recursive_second_mother():
    tracks=[(2212,-1,-1),(25,-1,-1),(999999,1,-1),(211,2,-1),(22,-1,3),(25,-1,-1)]
    roots,ids=suep.select(tracks,{0,1,2,3},[25,2212])
    assert roots==[1] and ids==[1,2,3,4]
    assert 5 not in ids


def test_requested_motherless_policy_is_not_silently_relaxed():
    tracks=[(2212,-1,-1),(25,0,-1),(999999,1,-1)]
    assert suep.select(tracks,{0,1,2},[25])==([],[])
    assert suep.select(tracks,{0,1,2},[25],'pdg')==([1],[1,2])


def test_truth_join_checks_source_event_fake_and_renderer_scope():
    selected={(0,2,3)}
    rows=[dict(primary_vertex=4,renderer_track_id=100,mc_source_id=0,mc_event_id=2,mc_track_id=3,fake=False),
          dict(primary_vertex=4,renderer_track_id=101,mc_source_id=1,mc_event_id=2,mc_track_id=3,fake=False),
          dict(primary_vertex=4,renderer_track_id=102,mc_source_id=0,mc_event_id=2,mc_track_id=3,fake=True)]
    result,_=suep.map_reconstructed(selected,rows,{'4':'event-A'})
    assert result=={'event-A':['100']}
    with pytest.raises(ValueError,match='Missing renderer event'):suep.map_reconstructed(selected,rows,{})


def test_event_highlights_do_not_leak_between_collisions():
    cfg=RenderSettings(highlight_tracks_by_event={'A':[1],'B':['2']},highlight_track_ids=['global'])
    cfg.validate();settings=cfg.to_dict()
    assert event_highlight_ids(settings,'A')==['global','1']
    assert highlighted({'id':'1'},dict(settings,_highlight_event_id='A'),'tracks')
    assert not highlighted({'id':'1'},dict(settings,_highlight_event_id='B'),'tracks')
    assert highlighted({'track_id':'2'},dict(settings,_highlight_event_id='B'),'clusters')
    assert event_highlight_ids(settings,'unknown')==['global']
    with pytest.raises(ValueError):parse_event_highlights('{"A":"1,2"}')


def test_burst_selects_sibling_pions_not_scalar_or_beam():
    tracks=[(2212,-1,-1),(25,0,-1),(999999,1,-1),(999999,1,-1),(211,2,-1)]
    members,report=suep.burst_members(tracks,[999999],2)
    assert members=={2,3} and report[0]['parent_id']==1
    assert suep.select(tracks,members,[999999],'pdg')==([2,3],[2,3,4])
    with pytest.raises(ValueError,match='Invalid ancestry'):
        suep.burst_members([(999999,7,-1)],[999999],2)


def test_track_representation_and_missing_truth_are_explicit():
    from alice_renderer.object_selection import selected_tracks
    event={'id':'A','kind':'collision','tracks':[{'id':'reco','detectors':['TPC']}],
           'mc_tracks':[{'id':'mc:0:0:1','detectors':['TPC']}]}
    cfg=RenderSettings(detectors=['TPC']).to_dict()
    assert selected_tracks(event,cfg)[0]['id']=='reco'
    cfg['track_representation']='mc'
    assert selected_tracks(event,cfg)[0]['id']=='mc:0:0:1'
    del event['mc_tracks']
    with pytest.raises(ValueError,match='no mc tracks'):selected_tracks(event,cfg)
