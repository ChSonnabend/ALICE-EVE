"""Shared per-detector visibility and event-local emphasis, independent of Blender."""

def event_counts(event):
    from collections import Counter
    return {'tracks_by_detector':dict(Counter(d for t in event['tracks'] for d in t['detectors'])),
            'clusters_by_detector':dict(Counter(c['detector'] for c in event['clusters'])),
            'tracks_by_source':dict(Counter(t.get('source','unknown') for t in event['tracks'])),
            'primary_vertex_contributors':event.get('contributors'),
            'unsampled_tracks':len(event.get('unrendered_tracks',[]))}

def detector_mode(settings,name):return settings.get('detector_modes',{}).get(name,settings.get('mode','tracks'))

def enabled_detectors(settings,kind):
    return {d for d in settings['detectors'] if detector_mode(settings,d) in (kind,'both')}

def selected_tracks(event,settings):
    active=enabled_detectors(settings,'tracks')
    return [t for t in event['tracks'] if active.intersection(t['detectors'])]

def selected_clusters(event,settings):
    active=enabled_detectors(settings,'clusters')
    return [c for c in event['clusters'] if c['detector'] in active]

def parse_track_ids(value):
    values=value.split(',') if isinstance(value,str) else value
    if not isinstance(values,(list,tuple)):raise ValueError('Track IDs must be comma-separated text or a list')
    result=[]
    for item in values:
        text=str(item).strip()
        if not text:continue
        if ',' in text or any(ord(c)<32 for c in text):raise ValueError('Invalid track ID')
        if text not in result:result.append(text)
    return result

def highlighted(obj,settings,kind):
    return str(obj.get('id') if kind=='tracks' else obj.get('track_id','')) in set(settings.get('highlight_track_ids',[]))

# These are O2 fitted-source names, not an inference from detector sets or momentum.
SINGLE_SOURCES={'ITS','ITSAB','TPC','TRD','TOF','PHS','PHOS','CPV','EMC','EMCAL','HMP','HMPID','MFT','MCH','MID','ZDC','FT0','FV0','FDD'}
MATCHED_SOURCES={'ITSTPC','TPCTOF','TPCTRD','MFTMCH','ITSTPCTRD','ITSTPCTOF','TPCTRDTOF','MFTMCHMID','ITSTPCTRDTOF','MCHMID'}

def matching_value(obj):
    if isinstance(obj.get('matching'),bool) and obj.get('matching_basis'):return float(obj['matching'])
    source=str(obj.get('source','')).upper().replace('-','').replace('_','').replace(' ','')
    if source in MATCHED_SOURCES:return 1.
    if source in SINGLE_SOURCES:return 0.
    return None

def annotate_matching(event):
    parents={};bases={}
    for t in event['tracks']:
        value=matching_value(t)
        if value is not None:
            if 'matching' not in t:t['matching']=bool(value);t['matching_basis']='O2 fitted-source record: composite matched source versus standalone source; component membership in other matches is not asserted'
            parents[str(t['id'])]=t
    for c in event['clusters']:
        parent=parents.get(str(c.get('track_id','')))
        if parent is not None and 'matching' not in c:
            basis=parent['matching_basis']
            if basis not in bases:bases[basis]='explicit track_id association to '+basis
            c['matching']=parent['matching'];c['matching_basis']=bases[basis]
    return event
