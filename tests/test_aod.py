import json,math,sqlite3
import numpy as np
import pytest,uproot
from alice_renderer.inputs import inspect_input
from alice_renderer.catalogue import Catalogue,load_event
from alice_renderer.aod import at_arc,dca_to_vertex,helix_state
from alice_renderer.model import color_value,RenderSettings,capabilities

def fixture_file(path,*,bad_index=False,bad_extra=False):
    with uproot.recreate(path) as f:
        for df,n in [('DF_1',2),('DF_2',1)]:
            f.mktree(df+'/O2collision_001',{'fPosX':np.zeros(n,dtype='f4'),'fPosY':np.zeros(n,dtype='f4'),'fPosZ':np.zeros(n,dtype='f4'),'fIndexBCs':np.zeros(n,dtype='i4'),'fNumContrib':np.ones(n,dtype='u2')})
            f.mktree(df+'/O2bc_001',{'fRunNumber':np.array([99],dtype='i4'),'fGlobalBC':np.array([123],dtype='u8')})
            ids=np.array([0,(8 if bad_index else n-1),-1],dtype='i4');count=len(ids)
            f.mktree(df+'/O2track_iu',{'fIndexCollisions':ids,'fX':np.array([2,83,90],dtype='f4'),'fY':np.zeros(count,dtype='f4'),'fZ':np.ones(count,dtype='f4'),'fAlpha':np.zeros(count,dtype='f4'),'fSnp':np.zeros(count,dtype='f4'),'fTgl':np.ones(count,dtype='f4')*.5,'fSigned1Pt':np.array([1,-2,3],dtype='f4'),'fTrackType':np.zeros(count,dtype='u1')})
            count=count-1 if bad_extra else count
            f.mktree(df+'/O2trackextra_002',{'fITSClusterSizes':np.ones(count,dtype='u4')*0x1111,'fTPCNClsFindable':np.ones(count,dtype='u1')*100,'fTPCNClsFindableMinusFound':np.ones(count,dtype='i1')*3,'fTPCNClsFindableMinusCrossedRows':np.ones(count,dtype='i1')*8,'fTRDPattern':np.zeros(count,dtype='u1'),'fTOFChi2':np.ones(count,dtype='f4')*-1,'fTOFExpMom':np.ones(count,dtype='f4'),'fFlags':np.ones(count,dtype='u4')*0x20000002,'fTPCSignal':np.ones(count,dtype='f4')*45})
    return path

def test_aod_lazy_collision_index_and_selected_fitted_features(tmp_path):
    source=fixture_file(tmp_path/'AO2D.root')
    info=inspect_input(source);assert info.format=='aod' and info.timeframes is None
    cat=Catalogue.build(source,tmp_path/'cache',aod_options={'bz_kG':5})
    rows=cat.rows();assert len(rows)==3 and [r['ntracks'] for r in rows]==[1,1,2]
    assert not list(cat.folder.glob('event-*.json.gz'))
    event=load_event(cat.event_path(1));assert len(event['tracks'])==1 and event['clusters']==[]
    track=event['tracks'][0];assert track['detectors']==['ITS','TPC'] and track['matching']
    assert track['associations']['index_collisions']==1
    assert track['id']=='DF_1:barrel:1';assert track['kinematics']['pt']==.5
    assert track['features']['tpc_nclusters']==97 and track['features']['its_nclusters']==4
    assert track['features']['pv_contributor']==1 and track['features']['pid_for_tracking']==2
    assert color_value(track,'feature:tpc_signal')==45
    assert 'feature:tpc_signal' in capabilities(event['tracks'])
    assert 'dca_basis' in track and 'classification' not in track
    assert len(list(cat.folder.glob('event-*.json.gz')))==1
    with sqlite3.connect(cat.db) as db:assert db.execute("SELECT value FROM metadata WHERE key='unassociated_track_records'").fetchone()[0]=='2'

def test_aod_indexes_without_field_but_stops_before_trajectory_or_render(tmp_path):
    source=fixture_file(tmp_path/'AO2D.root');cat=Catalogue.build(source,tmp_path/'cache')
    assert len(cat.rows())==3
    with pytest.raises(ValueError,match='magnetic-field conditions are missing'):cat.event_path(0)
    assert not list(cat.folder.glob('event-*.json.gz'))

@pytest.mark.parametrize('kwargs,reason',[({'bad_index':True},'collision index'),({'bad_extra':True},'row counts')])
def test_aod_rejects_broken_association_or_extra_alignment(tmp_path,kwargs,reason):
    source=fixture_file(tmp_path/'AO2D.root',**kwargs)
    with pytest.raises(ValueError,match=reason):Catalogue.build(source,tmp_path/'cache')

def test_aod_conditions_sidecar_and_changed_source(tmp_path):
    source=fixture_file(tmp_path/'AO2D.root');(tmp_path/'AO2D.root.renderer.json').write_text(json.dumps({'fields':{'99':{'bz_kG':-5,'basis':'fixture'}}}))
    cat=Catalogue.build(source,tmp_path/'cache')
    equivalent=Catalogue.build(source,tmp_path/'cache',aod_options={'conditions':'','bz_kG':None});assert equivalent.folder==cat.folder
    assert load_event(cat.event_path(0))['trajectory_conditions']['bz_kG']==-5
    source.touch()
    with pytest.raises(ValueError,match='changed'):cat.event_path(1)

def test_helix_tangent_and_transverse_closest_approach():
    origin=[5.,2.,0.];phi=.7;tgl=.3;k=.01;s=1.e-4;p=at_arc(origin,phi,tgl,k,s)
    assert [(a-b)/s for a,b in zip(p,origin)]==pytest.approx([math.cos(phi),math.sin(phi),tgl],abs=1.e-5)
    origin,phi,tgl,qpt=helix_state({'fX':4,'fY':3,'fZ':1,'fAlpha':math.pi/2,'fSnp':0,'fTgl':.5,'fSigned1Pt':-2})
    assert origin==pytest.approx([-3,4,1]) and phi==pytest.approx(math.pi/2)
    distance,xy,z=dca_to_vertex([0,2,3],0,.5,0,5,[10,0,8]);assert xy==2 and z==0 and distance==2
    RenderSettings(track_color_mode='feature:tpc_signal').validate()

def test_forward_types_and_sparse_mft_covariance(tmp_path):
    source=fixture_file(tmp_path/'AO2D.root')
    with uproot.update(source) as f:
        for df in ('DF_1','DF_2'):
            f.mktree(df+'/O2fwdtrack',{'fIndexCollisions':np.array([0],dtype='i4'),'fX':np.array([10],dtype='f4'),'fY':np.array([2],dtype='f4'),'fZ':np.array([-700],dtype='f4'),'fPhi':np.array([.2],dtype='f4'),'fTgl':np.array([-10],dtype='f4'),'fSigned1Pt':np.array([1],dtype='f4'),'fTrackType':np.array([0],dtype='u1'),'fMIDBitMap':np.array([0],dtype='u2'),'fMCHBitMap':np.array([0],dtype='u2')})
            f.mktree(df+'/O2mfttrack_001',{'fIndexCollisions':np.array([0,0],dtype='i4'),'fX':np.array([1,2],dtype='f4'),'fY':np.array([0,0],dtype='f4'),'fZ':np.array([-50,-50],dtype='f4'),'fPhi':np.array([.1,.2],dtype='f4'),'fTgl':np.array([-5,-6],dtype='f4'),'fSigned1Pt':np.array([1,-1],dtype='f4')})
            f.mktree(df+'/O2mfttrackcov',{'fIndexMFTTracks':np.array([1,1],dtype='i4'),'fSigmaX':np.array([.125,.125],dtype='f4')})
    cat=Catalogue.build(source,tmp_path/'cache',aod_options={'bz_kG':-5});event=load_event(cat.event_path(0))
    forward=next(t for t in event['tracks'] if ':fwd:' in t['id']);assert forward['detectors']==['MCH','MFT','MID']
    mft=[t for t in event['tracks'] if ':mft:' in t['id']];assert 'covariance_parameters' not in mft[0] and mft[1]['features']['sigma_x']==.125
    assert 'feature:sigma_x' in cat.rows()[0]['track_fields']


def test_incomplete_schema_stops_during_indexing(tmp_path):
    source=fixture_file(tmp_path/'AO2D.root')
    with uproot.update(source) as file:file.mktree('DF_1/O2track_iu',{'fIndexCollisions':np.array([0],dtype='i4')})
    with pytest.raises(ValueError,match='unsupported/incomplete AO2D table'):Catalogue.build(source,tmp_path/'cache')

def test_conflicting_mft_covariance_is_not_arbitrarily_chosen(tmp_path):
    from alice_renderer.aod import covariance_rows
    source=tmp_path/'cov.root'
    with uproot.recreate(source) as file:file.mktree('O2mfttrackcov',{'fIndexMFTTracks':np.array([1,1],dtype='i4'),'fSigmaX':np.array([.1,.2],dtype='f4')})
    with uproot.open(source) as file:
        with pytest.raises(ValueError,match='Conflicting MFT covariance'):covariance_rows(file,{'mft_cov':'O2mfttrackcov'},'mft',np.array([1]),2)
