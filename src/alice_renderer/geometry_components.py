"""Named display components from TGeo ancestry, independent of source mesh reuse."""
from __future__ import annotations
import gzip,json,re
from pathlib import Path

LABELS={'layers':'Layers','structures':'Structures','modules':'Modules / sectors / chambers','parts':'Named elements',
 'structures/sensors':'Sensors / sensitive elements','structures/supports':'Support structures',
 'structures/services':'Services','structures/cooling':'Cooling','structures/electronics':'Electronics / readout',
 'structures/cage':'ITS cage','structures/inner_wall':'TPC inner wall / shields','structures/outer_wall':'TPC outer wall / shields',
 'structures/inner_rods':'Inner field-cage rods / rings','structures/outer_rods':'Outer field-cage rods / rings',
 'structures/readout':'Readout chambers','structures/membrane':'Central electrode','structures/other':'Other structures'}

def label(identifier):
    if identifier in LABELS:return LABELS[identifier]
    text=identifier.rsplit('/',1)[-1]
    if text.startswith('layer_'):return 'Layer '+text.removeprefix('layer_')
    return text.replace('_',' ')

def tags_for(detector,path,name,translation):
    """Ancestry is authoritative for layers/modules; radius only splits TPC cages."""
    tags={'parts/'+name};lower=name.lower();path=str(path)
    if detector=='ITS':
        match=re.search(r'(?:ITSU?Layer|ITSULayer)([0-6])(?:_|/)',path)
        if match:tags.add('layers/layer_'+match[1])
        if 'itsservices' in lower:tags.add('structures/services')
        elif lower.startswith('cage'):tags.update(('structures/cage','structures/supports'))
        elif any(k in lower for k in ('chip','sensor')):tags.add('structures/sensors')
        elif any(k in lower for k in ('water','pipe','thermasol','cool')):tags.add('structures/cooling')
        elif any(k in lower for k in ('power','capacitor','fpc','bus')):tags.add('structures/electronics')
        else:tags.add('structures/supports')
    elif detector=='TPC':
        if name.startswith(('TPC_IFC','TPC_IFEPOX','TPC_ICV','TPC_HSM','TPC_HSS')):tags.add('structures/inner_wall')
        elif name.startswith(('TPC_OCV','TPC_OHVH','TPC_TOFC')):tags.add('structures/outer_wall')
        elif name.startswith(('TPC_mrod','TPC_rod','TPC_ring','TPC_bcon')):
            import math
            radius=math.hypot(translation['x'],translation['y']) # exported cm
            tags.add('structures/inner_rods' if radius<100 else 'structures/outer_rods')
        elif name=='TPC_HV':tags.add('structures/membrane')
        elif name.startswith(('TPC_IROC','TPC_OROC','TPC_ICGEM','TPC_OCGEM','TPC_IRC','TPC_ORC')):tags.add('structures/readout')
        else:tags.add('structures/supports')
    else:
        if any(k in lower for k in ('support','cradle','rail','frame','plate','screw','bolt','carbon')):tags.add('structures/supports')
        elif any(k in lower for k in ('cable','service','pipe','water')):tags.add('structures/services')
        elif any(k in lower for k in ('readout','electronics','pcb','board','connector')):tags.add('structures/electronics')
        else:tags.add('structures/other')
        pattern={'TRD':r'/(BTRD\d+_\d+)', 'TOF':r'/(BTOF\d+_\d+)', 'EMC':r'/(SMOD_\d+|SM3rd_\d+|DCSM_\d+|DCEXT_\d+)',
                 'PHS':r'/(PHOS_\d+|PHOH_\d+)', 'CPV':r'/(CPV_\d+)', 'MCH':r'/(SC\d+[IO]_\d+)', 'MID':r'/(SC1[1-4]_\d+)',
                 'FT0':r'/(FT0[AC]_\d+)', 'FDD':r'/(FD[AC]_\d+)', 'ZDC':r'/(ZNENV_\d+|ZPENV_\d+|ZEM_\d+)'}
        match=re.search(pattern.get(detector,r'(?!)'),path)
        if match:tags.add('modules/'+match[1])
        if detector=='MFT':
            match=re.search(r'/MFT_D_[01]_([0-4])_\d+(?:/|$)',path) or re.search(r'(?:Disk|disk)_?([0-4])(?:_|/)',path)
            if match:tags.add('layers/layer_'+match[1])
    return sorted(tags)

def component_state(tags,settings):
    """False is a veto; explicit true opts back into legacy hidden components."""
    applicable={key:value for key,value in settings.items() if any(tag==key or tag.startswith(key+'/') for tag in tags)}
    return not any(v is False for v in applicable.values()),any(v is True for v in applicable.values())

def sidecar_path(asset):return Path(str(asset)+'.components.json.gz')

def load_components(asset,*,verify=True):
    path=sidecar_path(asset)
    if not path.is_file():return None
    with gzip.open(path,'rt') as stream:data=json.load(stream)
    if data.get('schema')!='alice-geometry-components' or data.get('version')!=1:raise ValueError('Unsupported detector component metadata')
    if verify:
        from .scene_config import sha256
        if sha256(asset)!=data.get('asset_sha256'):raise ValueError('Component metadata does not match the selected geometry asset: '+str(asset))
    return data


def component_visibility(metadata,choices,exclusions=()):
    """Aggregate named masks and placement choices for truthful mixed-state controls."""
    from collections import Counter
    from fnmatch import fnmatchcase
    counts={key:[0,0] for key in metadata['components']}
    for name,group in metadata['groups'].items():
        hidden=any(fnmatchcase(name,p) for p in exclusions)
        for index,count in Counter(group['ids']).items():
            tags=group['classes'][index];allowed,explicit=component_state(tags,choices);on=allowed and (explicit or not hidden)
            ancestors=set()
            for tag in tags:
                fields=tag.split('/');ancestors.update('/'.join(fields[:n]) for n in range(1,len(fields)+1))
            for key in ancestors:counts[key][int(on)]+=count
    return {key:True if off==0 else False if on==0 else None for key,(off,on) in counts.items()}


def index_from_export(data,detector,source_sha256):
    """Build a placement index from aligned JSON carrying original TGeo tags."""
    import hashlib,struct
    catalogue={};bindings={}
    for name,item in data.items():
        classes=[];lookup={};ids=[];digest=hashlib.sha256();placements=item['positions']
        for placement in placements:
            if 'component_tags' not in placement:raise ValueError('Original TGeo component tags missing; re-export aligned geometry')
            tags=tuple(placement['component_tags'])
            if tags not in lookup:lookup[tags]=len(classes);classes.append(list(tags))
            ids.append(lookup[tags]);translation=placement['translation'];digest.update(struct.pack('<fff',*(translation[axis]*.01 for axis in ('x','y','z'))))
            ancestors=set()
            for tag in tags:
                fields=tag.split('/');ancestors.update('/'.join(fields[:n]) for n in range(1,len(fields)+1))
            for key in ancestors:
                entry=catalogue.setdefault(key,dict(label=label(key),count=0,parent=key.rsplit('/',1)[0] if '/' in key else ''));entry['count']+=1
        bindings[name+'_instancer']=dict(ids=ids,classes=classes,positions_sha256=digest.hexdigest(),source_examples=[placements[0].get('source_path',''),placements[-1].get('source_path','')])
    return dict(schema='alice-geometry-components',version=1,detector=detector,source_sha256=source_sha256,groups=bindings,components=catalogue)
