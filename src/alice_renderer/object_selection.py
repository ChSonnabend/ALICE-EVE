"""Shared per-detector visibility and event-local emphasis, independent of Blender."""

def event_counts(event):
    from collections import Counter
    return {'tracks_by_detector':dict(Counter(d for t in event['tracks'] for d in t['detectors'])),
            'clusters_by_detector':dict(Counter(c['detector'] for c in event['clusters'])),
            'tracks_by_source':dict(Counter(t.get('source','unknown') for t in event['tracks'])),
            'primary_vertex_contributors':event.get('contributors'),
            'unsampled_tracks':len(event.get('unrendered_tracks',[])),
            'ambiguous_drawable_tracks':sum(t.get('association',{}).get('ambiguous',False) for t in event['tracks']),
            'association_flags_available':any('association' in t for t in event['tracks'])}

def detector_mode(settings,name):return settings.get('detector_modes',{}).get(name,settings.get('mode','tracks'))

def enabled_detectors(settings,kind):
    return {d for d in settings['detectors'] if detector_mode(settings,d) in (kind,'both')}

def representation_tracks(event,settings):
    requested=settings.get('track_representation','reconstructed')
    stored=event.get('track_representation','reconstructed')
    if event.get('kind')=='geometry':return []
    if requested==stored:return event['tracks']
    key='mc_tracks' if requested=='mc' else 'reconstructed_tracks'
    if key not in event:raise ValueError(f"Event {event['id']} has no {requested} tracks; load a dataset containing that representation")
    return event[key]


def selected_tracks(event,settings):
    active=enabled_detectors(settings,'tracks')
    return [t for t in representation_tracks(event,settings) if active.intersection(t['detectors']) and (settings.get('include_ambiguous_tracks',True) or not t.get('association',{}).get('ambiguous',False))]

def selected_clusters(event,settings):
    active=enabled_detectors(settings,'clusters')
    excluded={str(t['id']) for t in [*event['tracks'],*event.get('unrendered_tracks',[])] if t.get('association',{}).get('ambiguous',False)} if not settings.get('include_ambiguous_tracks',True) else set()
    return [c for c in event['clusters'] if c['detector'] in active and str(c.get('track_id','')) not in excluded]

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

def parse_event_highlights(value):
    import json
    if isinstance(value,str):value=json.loads(value or '{}')
    if not isinstance(value,dict):raise ValueError('Event highlights must be a JSON object mapping exact event IDs to track-ID lists')
    result={}
    for key,ids in value.items():
        if not isinstance(key,str) or not key or any(ord(c)<32 for c in key):raise ValueError('Invalid event ID')
        if not isinstance(ids,list):raise ValueError('Each event must contain a list of track IDs')
        result[key]=parse_track_ids(ids)
    return result


def event_highlight_ids(settings,event_id):
    return list(dict.fromkeys([*settings.get('highlight_track_ids',[]),
        *settings.get('highlight_tracks_by_event',{}).get(str(event_id),[])]))


def highlighted(obj,settings,kind):
    return str(obj.get('id') if kind=='tracks' else obj.get('track_id','')) in set(event_highlight_ids(settings,settings.get('_highlight_event_id','')))

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
