"""Adapters for documented legacy and O2 event-display JSON schemas."""
import math, re
from .model import DETECTORS

SOURCES=[['ITS'],['TPC'],['TRD'],['TOF'],['PHS'],['CPV'],['EMC'],['HMP'],['MFT'],['MCH'],['MID'],['ZDC'],['FT0'],['FV0'],['FDD'],['ITS','TPC'],['TPC','TOF'],['TPC','TRD'],['MFT','MCH'],['ITS','TPC','TRD'],['ITS','TPC','TOF'],['TPC','TRD','TOF'],['MFT','MCH','MID'],['ITS','TPC','TRD','TOF'],['ITS'],[],['MCH','MID']]

def gid_detectors(gid):
    source=(int(gid)>>25)&31
    if source>=len(SOURCES):raise ValueError('Unsupported O2 GlobalTrackID source; update source mapping for this O2 version')
    return SOURCES[source]

def base(id_,kind,**extra):return {'schema_version':1,'units':'cm','id':str(id_),'kind':kind,'tracks':[],'clusters':[],**extra}

def legacy(raw):
    if 'EventID' not in raw:raise ValueError('Not an aliceBlender event JSON')
    event=base(raw['EventID'],'timeframe',warnings=['Legacy JSON has no vertex coordinates and does not prove complete collision enumeration. Units interpreted as O2 global cm; confirm exporter provenance.'])
    seen=set()
    for index,t in enumerate(raw.get('RecoTracks',[])):
        axes=[t.get('Track'+a,[]) for a in 'XYZ']
        if len(set(map(len,axes)))!=1:raise ValueError('Legacy track coordinate arrays have different lengths')
        clusters=t.get('TrackClusters',[])
        names=[d for d in DETECTORS if d in t.get('TrackType','').split('-')]
        if not names:names=sorted({c['ClusterDetector'] for c in clusters if c.get('ClusterDetector') in DETECTORS})
        points=[list(p) for p in zip(*axes)]
        if len(points)>=2 and names:
            kin={}
            if t.get('TrackPt',-1)>=0:kin['pt']=t['TrackPt']
            event['tracks'].append({'id':str(t.get('TrackID',index)), 'detectors':names,'points':points,'kinematics':kin})
        for c in clusters:
            if c.get('ClusterDetector') not in DETECTORS:continue
            pos=c['ClusterXYZ'];key=(c['ClusterDetector'],*pos)
            if key not in seen:
                seen.add(key);event['clusters'].append({'id':str(len(seen)),'detector':c['ClusterDetector'],'position':pos,'size':c.get('ClusterSize')})
    return event

def o2_display(raw):
    if 'mTracks' not in raw:raise ValueError('Not an O2 event-display JSON')
    pv=raw.get('primaryVertex',-1)
    # A numeric primaryVertex field alone does not prove the producer was in PV mode.
    # Only a lossless exporter/provenance annotation may assert collision grouping.
    is_collision=raw.get('event_grouping')=='primary_vertex' and isinstance(pv,int) and 0<=pv<0xFFFFFFFF
    id_=f'{raw.get("runNumber",0)}:{raw.get("tfCounter",0)}:{pv}'
    event=base(id_,'collision' if is_collision else 'timeframe',run=raw.get('runNumber'),timeframe=raw.get('tfCounter'),primary_vertex_index=pv,orbit=raw.get('firstTForbit'),warnings=['O2 display JSON lacks momentum magnitude, DCA and primary-vertex XYZ. Input may have been subsampled by its producer.'])
    seen=set();ambiguous=0
    def add_cluster(c,names):
        nonlocal ambiguous
        if len(names)!=1:ambiguous+=1;return
        pos=[c[a] for a in 'XYZ'];key=(names[0],*pos)
        if key in seen:return
        seen.add(key);event['clusters'].append({'id':str(len(seen)),'detector':names[0],'position':pos})
    for index,t in enumerate(raw['mTracks']):
        if 'bgid' not in t:raise ValueError('O2 JSON needs binary bgid to identify track detector source')
        names=gid_detectors(t['bgid'])
        axes=[t.get('mPoly'+a,[]) for a in 'XYZ']
        if len(set(map(len,axes)))!=1:raise ValueError('O2 polyline coordinate arrays have different lengths')
        points=[list(p) for p in zip(*axes)]
        kin={k:t[k] for k in ('eta','phi') if k in t and math.isfinite(t[k])}
        if len(points)>=2 and names:event['tracks'].append({'id':str(t['bgid']),'source':'-'.join(names),'source_basis':'O2 GlobalTrackID source enum','detectors':names,'points':points,'kinematics':kin})
        for c in t.get('mClusters',[]):add_cluster(c,gid_detectors(c['bgid']) if 'bgid' in c else names)
    for c in raw.get('mClusters',[]):
        if 'bgid' in c:add_cluster(c,gid_detectors(c['bgid']))
        else:ambiguous+=1
    if ambiguous:event['warnings'].append(f'{ambiguous} clusters omitted: O2 JSON lacks an unambiguous detector ID for composite-source clusters. Use the lossless exporter for full cluster rendering.')
    return event

def convert(raw):
    if raw.get('schema_version')==1:return raw
    if 'EventID' in raw:return legacy(raw)
    if 'mTracks' in raw:return o2_display(raw)
    raise ValueError('Unknown event schema. Expected canonical, aliceBlender or O2 display JSON.')
