import json, math
from pathlib import Path
import pytest
from alice_renderer.model import RenderSettings,validate_event,capabilities
from alice_renderer.catalogue import Catalogue,fingerprint
from alice_renderer.inputs import inspect_input,run_ingest_profile
from alice_renderer.converters import convert,gid_detectors
from alice_renderer.runtime import preflight

def event(id='event-1'):
    return {'schema_version':1,'units':'cm','id':id,'kind':'collision','vertex':[0,0,0],'tracks':[{'id':'1','detectors':['TPC'],'points':[[0,0,0],[100,0,20]],'kinematics':{'pt':1.,'eta':.2}}],'clusters':[{'id':'c1','detector':'TPC','position':[100,0,20]}]}

def test_indexes_all_events_without_top15(tmp_path):
    source=tmp_path/'events.jsonl'
    source.write_text('\n'.join(json.dumps(event(str(i))) for i in range(31)))
    catalogue=Catalogue.build(source,tmp_path/'cache')
    assert len(catalogue.rows())==31
    assert catalogue.load(30)['id']=='30'

def test_streams_wrapped_event_array(tmp_path):
    source=tmp_path/'events.json';source.write_text(json.dumps({'events':[event('a'),event('b')]}))
    cat=Catalogue.build(source,tmp_path/'cache');assert len(cat.rows())==2

def test_directory_cache_invalidates_changed_file(tmp_path):
    folder=tmp_path/'input';folder.mkdir();file=folder/'one.json';file.write_text(json.dumps(event('a')))
    first=fingerprint(folder);file.write_text(json.dumps(event('changed')))
    assert fingerprint(folder)!=first

def test_failed_import_is_atomic(tmp_path):
    source=tmp_path/'events.jsonl';source.write_text(json.dumps(event())+'\n'+json.dumps({'schema_version':1}))
    with pytest.raises(ValueError):Catalogue.build(source,tmp_path/'cache')
    assert not list((tmp_path/'cache').glob('*/catalogue.sqlite'))

def test_physics_unavailable_is_not_fabricated():
    data=validate_event(event());assert 'dca' not in capabilities(data['tracks']);assert 'p' not in capabilities(data['tracks'])
    assert 'eta' not in capabilities(data['clusters']);assert 'tan_lambda' in capabilities(data['tracks'])

def test_dca_requires_vertex_and_convention():
    data=event();data['tracks'][0]['kinematics']['dca']=1
    with pytest.raises(ValueError,match='DCA'):validate_event(data)
    data['tracks'][0]['dca_basis']='O2 helix transverse signed DCA at PV';assert validate_event(data)

def test_truth_requires_basis():
    data=event();data['tracks'][0]['classification']='primary'
    with pytest.raises(ValueError,match='classification_basis'):validate_event(data)

def test_nonfinite_coordinate_rejected():
    data=event();data['tracks'][0]['points'][0][0]=float('nan')
    with pytest.raises(ValueError,match='Non-finite'):validate_event(data)

def test_o2_gid_mapping():
    assert gid_detectors((23<<25)|123)==['ITS','TPC','TRD','TOF']
    assert gid_detectors((24<<25)|1)==['ITS']
    with pytest.raises(ValueError):gid_detectors(31<<25)

def test_o2_ambiguous_cluster_detector_is_not_guessed():
    raw={'runNumber':560067,'tfCounter':2,'primaryVertex':0,'mTracks':[{'bgid':15<<25,'mPolyX':[0,1],'mPolyY':[0,1],'mPolyZ':[0,1],'mClusters':[{'X':10,'Y':20,'Z':30}]}]}
    converted=validate_event(convert(raw));assert converted['tracks'][0]['detectors']==['ITS','TPC'];assert converted['clusters']==[]
    assert any('unambiguous' in warning for warning in converted['warnings'])

def test_ctf_header_is_not_collision_count(tmp_path):
    import uproot,numpy as np
    source=tmp_path/'ctf.root'
    with uproot.recreate(source) as root:
        root.mktree('ctf',{'TPC_wrapper.':'int32','CTFHeader/run':'int32'})
        root['ctf'].extend({'TPC_wrapper.':np.array([1,2]),'CTFHeader/run':np.array([560067,560067])})
    info=inspect_input(source);assert info.timeframes==2;assert info.detectors==['TPC'];assert 'timeframes' in info.warnings[0]

def test_unreadable_root_fails_before_processing(tmp_path):
    path=tmp_path/'bad.root';path.write_bytes(b'incomplete')
    with pytest.raises(ValueError,match='Cannot read CTF header'):inspect_input(path)

def test_backend_and_geometry_preflight(tmp_path):
    cfg=RenderSettings(detectors=['TPC'],backend='HIP',geometry=['TPC'])
    errors=preflight(cfg,[validate_event(event())],{'version':[5,0,0],'devices':[{'type':'CPU','id':'CPU'}]},tmp_path)
    assert any('HIP' in x for x in errors);assert any('geometry' in x for x in errors)

def test_missing_colour_stops_render(tmp_path):
    cfg=RenderSettings(detectors=['TPC'],track_color_mode='dca')
    errors=preflight(cfg,[validate_event(event())],{'version':[5,0,0],'devices':[{'type':'CPU','id':'CPU'}]},tmp_path)
    assert any('dca' in x for x in errors)

def test_default_is_tracks_only():assert RenderSettings().mode=='tracks'

def test_payload_availability_includes_nonspatial_detector_data():
    data=event();data['data_detectors']=['TPC','FT0','CPV']
    validated=validate_event(data)
    assert validated['available_detectors']==['CPV','FT0','TPC']
    assert not any(c['detector']=='FT0' for c in validated['clusters'])

def test_duplicate_track_identity_is_rejected():
    data=event();data['tracks'].append(dict(data['tracks'][0]))
    with pytest.raises(ValueError,match='Duplicate track'):validate_event(data)

def test_compressed_dataset_ignores_inventory_and_manifest_records(tmp_path):
    import gzip
    dataset=tmp_path/'dataset';dataset.mkdir()
    with gzip.open(dataset/'events.jsonl.gz','wt') as file:
        file.write(json.dumps(event('first'))+'\n'+json.dumps(event('second'))+'\n')
    (dataset/'manifest.json').write_text(json.dumps(dict(complete=True,events_file='events.jsonl.gz')))
    (dataset/'pv-inventory.jsonl').write_text('{"not_an_event":true}\n')
    assert inspect_input(dataset/'events.jsonl.gz').format=='events'
    cat=Catalogue.build(dataset,tmp_path/'cache')
    assert len(cat.rows())==2 and cat.load(1)['id']=='second'
    assert cat.event_path(0).name.endswith('.json.gz')
    assert Catalogue.build(dataset/'events.jsonl.gz',tmp_path/'cache').folder==cat.folder

def test_profile_needs_prerequisite_check(tmp_path):
    source=tmp_path/'source.tf';source.write_bytes(b'123')
    profile=tmp_path/'profile.json';profile.write_text(json.dumps({'argv':['echo','bad']}))
    with pytest.raises(ValueError,match='preflight_argv'):run_ingest_profile(source,profile,tmp_path/'cache')

def test_incomplete_ingest_cache_can_be_retried(tmp_path):
    import sys
    source=tmp_path/'source.tf';source.write_bytes(b'123')
    driver=tmp_path/'driver.py'
    driver.write_text("import json,sys\nfrom pathlib import Path\nfrom alice_renderer.catalogue import fingerprint\nsrc,out=map(Path,sys.argv[1:]);out.mkdir(exist_ok=True)\n(out/'events.jsonl').write_text(json.dumps({'schema_version':1,'units':'cm','id':'pv0','kind':'collision','tracks':[],'clusters':[]})+'\\n')\n(out/'manifest.json').write_text(json.dumps({'schema_version':1,'complete':True,'event_grouping':'primary_vertex','event_count':1,'input_fingerprint':fingerprint(src)}))\n")
    profile=tmp_path/'profile.json';profile.write_text(json.dumps({'preflight_argv':[sys.executable,'-c','pass'],'argv':[sys.executable,str(driver),'{input}','{output}']}))
    cache=tmp_path/'cache';directory=cache/'processed'/(fingerprint(source)+'-'+fingerprint(profile));directory.mkdir(parents=True)
    (directory/'events.jsonl').write_text('partial')
    (directory/'manifest.json').write_text('{"complete": false}')
    output=run_ingest_profile(source,profile,cache)
    assert json.loads(output.read_text())['id']=='pv0'

def test_preflight_can_be_cancelled_before_launch(tmp_path):
    import sys
    source=tmp_path/'source.tf';source.write_bytes(b'123')
    profile=tmp_path/'profile.json';profile.write_text(json.dumps({'preflight_argv':[sys.executable,'-c','import time;time.sleep(30)'],'argv':[sys.executable,'-c','pass']}))
    with pytest.raises(InterruptedError):run_ingest_profile(source,profile,tmp_path/'cache',cancelled=lambda:True)

def test_bad_device_id_has_specific_message(tmp_path):
    cfg=RenderSettings(detectors=['TPC'],device='not-a-device')
    errors=preflight(cfg,[validate_event(event())],{'version':[5,0,0],'devices':[{'type':'CPU','id':'CPU'}]},tmp_path)
    assert any('Selected device' in e for e in errors)
