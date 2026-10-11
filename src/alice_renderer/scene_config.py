"""Versioned, hardware-independent scene recipes. Inputs and quality are overrides."""
from __future__ import annotations
import copy, hashlib, json, math, os, tempfile
from pathlib import Path
from dataclasses import fields, replace
from .model import RenderSettings, color_value

SCHEMA='alice-eve-scene'
VERSION=1
LOCAL_FIELDS={'geometry_assets','backend','device','threads','width','height','samples','denoise','save_blend','output_format'}
SCENE_FIELDS={f.name for f in fields(RenderSettings)}-LOCAL_FIELDS
QUALITY={'draft':(640,16),'balanced':(1920,128),'final':(3840,512),'publication':(7680,1024)}

def sha256(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as stream:
        while block:=stream.read(4<<20):h.update(block)
    return h.hexdigest()

def recommended_quality(devices):
    types={d['type'] for d in devices.get('devices',[])}
    backend=next((b for b in ('OPTIX','METAL','HIP','CUDA','CPU') if b in types),'CPU')
    return {'backend':backend,'quality':'balanced' if backend!='CPU' else 'draft',
            'reason':'GPU detected; start at 1080p / 128 samples.' if backend!='CPU' else 'CPU detected; start at 640px / 16 samples. Increase quality after checking memory and timing.'}

def quality_settings(settings, quality='balanced', *, backend='CPU', device='', width=None, height=None, samples=None):
    if quality not in QUALITY:raise ValueError('Unknown quality preset')
    default_width,default_samples=QUALITY[quality]
    w=width or default_width
    h=height or max(64,round(w/settings.frame_aspect))
    return replace(settings,width=w,height=h,samples=samples or default_samples,backend=backend,device=device).validate()

def recipe(settings, event=None, *, default_input=None, default_event=None):
    from .palettes import materialize
    settings=materialize(copy.deepcopy(settings));settings.validate();values=settings.to_dict()
    scene={k:copy.deepcopy(values[k]) for k in SCENE_FIELDS}
    scene['frame_aspect']=settings.width/settings.height
    # Lock scalar ranges from the chosen event so another event/machine keeps the same legend.
    if event is not None:
        for kind in ('tracks','clusters'):
            mode=values[kind[:-1]+'_color_mode']
            from .object_selection import selected_tracks,selected_clusters
            objects=selected_tracks(event,values) if kind=='tracks' else selected_clusters(event,values)
            finite=[v for o in objects if (v:=color_value(o,mode)) is not None and math.isfinite(v)] if mode!='solid' else []
            lo,hi=(0.,1.) if mode in ('primaries','secondaries','matching') else (-math.pi,math.pi) if mode=='phi' else (min(finite),max(finite)) if finite else (0.,1.)
            if settings.scale_min is not None:lo=settings.scale_min
            if settings.scale_max is not None:hi=settings.scale_max
            scene['color_ranges'][kind]=[lo,hi]
    refs={}
    required=settings.geometry+(['L3'] if settings.magnet else [])
    from .object_selection import enabled_detectors
    clipping=[d for d in enabled_detectors(values,'tracks') if d in settings.geometry_assets and (not settings.geometry or d in settings.geometry)] if settings.clip_tracks else []
    for name in dict.fromkeys(required+clipping):
        if settings.schematic:continue
        value=settings.geometry_assets.get(name)
        if not value or not Path(value).is_file():raise ValueError(f'{name}: provide geometry before exporting a portable scene')
        refs[name]={'file':Path(value).name,'sha256':sha256(value)}
    defaults={}
    if default_input is not None:defaults['input']=str(default_input)
    if default_event is not None:defaults['event']=str(default_event)
    return {'schema':SCHEMA,'version':VERSION,'scene':scene,'geometry':refs,'defaults':defaults}

def validate_recipe(data):
    if not isinstance(data,dict) or data.get('schema')!=SCHEMA or data.get('version')!=VERSION:raise ValueError('Unsupported ALICE-EVE scene config version')
    scene=data.get('scene')
    if not isinstance(scene,dict) or set(scene)-SCENE_FIELDS:raise ValueError('Config contains unknown or machine-specific scene settings')
    RenderSettings(**scene).validate()
    refs=data.get('geometry',{})
    if not isinstance(refs,dict):raise ValueError('Invalid geometry references')
    for name,ref in refs.items():
        if not isinstance(ref,dict) or Path(ref.get('file','')).name!=ref.get('file') or not ref.get('file') or not isinstance(ref.get('sha256'),str) or len(ref['sha256'])!=64:raise ValueError(f'{name}: invalid geometry reference')
    defaults=data.get('defaults',{})
    if not isinstance(defaults,dict) or set(defaults)-{'input','event'}:raise ValueError('Invalid input defaults')
    return data

def save_config(path,data):
    validate_recipe(data);path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    fd,tmp=tempfile.mkstemp(prefix='.'+path.name,dir=path.parent)
    try:
        with os.fdopen(fd,'w') as stream:json.dump(data,stream,indent=2,sort_keys=True,allow_nan=False);stream.write('\n')
        os.replace(tmp,path)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)
    return path

def load_config(path):return validate_recipe(json.loads(Path(path).read_text()))

def resolve_settings(data,config_path,geometry_root=None,asset_overrides=None):
    validate_recipe(data);assets={};overrides=asset_overrides or {}
    roots=[Path(geometry_root)] if geometry_root else [Path(config_path).resolve().parent]
    for name,ref in data.get('geometry',{}).items():
        path=Path(overrides[name]) if name in overrides else roots[0]/ref['file']
        if not path.is_file():raise ValueError(f'{name}: geometry {ref["file"]} missing. Copy the geometry bundle or supply --geometry-root.')
        if sha256(path)!=ref['sha256']:raise ValueError(f'{name}: geometry hash differs from exported scene; use the identical alignment/surfaces bundle')
        assets[name]=str(path.resolve())
    cfg=RenderSettings(**data['scene'],geometry_assets=assets)
    required=cfg.geometry+(['L3'] if cfg.magnet else [])
    if not cfg.schematic and any(name not in assets for name in required):raise ValueError('Scene is missing selected geometry references')
    return cfg.validate()

def choose_event(cat,selector):
    if selector is None:raise ValueError('Specify --event EVENT_ID (or ordinal:N); event selection belongs to this instance')
    rows=cat.rows();matches=[r['ordinal'] for r in rows if str(r['event_id'])==str(selector)]
    if str(selector).startswith('ordinal:'):
        try:ordinal=int(str(selector).split(':',1)[1])
        except ValueError:raise ValueError('Invalid event ordinal')
        matches=[r['ordinal'] for r in rows if r['ordinal']==ordinal]
    if len(matches)!=1:raise ValueError(f'Event {selector!r} does not identify exactly one event in this input')
    return cat.event_path(matches[0])
