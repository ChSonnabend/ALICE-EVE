"""Portable, prebuilt large-surface proxies bound to their aligned source assets."""
import gzip,json,math,shlex
from pathlib import Path
from functools import lru_cache
from .scene_config import sha256
from .geometry_components import sidecar_path as component_path

SUPPORTED={'ITS','TPC'}

def sidecar_path(asset):return Path(str(asset)+'.structural.json.gz')

def supported_components(data):
    result=set()
    for group in data['groups']:
        for tag in group['tags']:
            fields=tag.split('/');result.update('/'.join(fields[:i]) for i in range(1,len(fields)+1))
    return result

@lru_cache(maxsize=16)
def _read(path,mtime,size):
    with gzip.open(path,'rt') as stream:return json.load(stream)

def load(asset,units='m'):
    path=sidecar_path(asset)
    if not path.is_file():raise ValueError('Large-surface cache is missing. Run alice-render prepare-geometry --geometry-root '+shlex.quote(str(Path(asset).parent))+' --detectors ITS,TPC --units '+units)
    stat=path.stat();data=_read(str(path.resolve()),stat.st_mtime_ns,stat.st_size)
    if data.get('schema')!='alice-structural-geometry' or data.get('version')!=1:raise ValueError('Unsupported large-surface cache')
    if data.get('detector') not in SUPPORTED:raise ValueError('Large surfaces currently support ITS and TPC')
    if data.get('source_units')!=units:raise ValueError('Large-surface cache units differ from the selected geometry units')
    if sha256(asset)!=data['asset_sha256'] or sha256(component_path(asset))!=data['components_sha256']:
        raise ValueError('Large-surface cache differs from its aligned geometry/component bundle; rebuild it')
    for group in data['groups']:
        if not group['vertices'] or any(len(v)!=3 or not all(math.isfinite(x) for x in v) for v in group['vertices']):raise ValueError('Invalid cached surface vertices')
        if any(len(f)<3 or any(not isinstance(i,int) or i<0 or i>=len(group['vertices']) for i in f) for f in group['faces']):raise ValueError('Invalid cached surface faces')
    region=data.get('track_region',{})
    planes=region.get('planes',[])
    if region.get('units')!='cm' or len(planes)!=66 or any(len(p)!=4 or not all(isinstance(v,(float,int)) and math.isfinite(v) for v in p) or sum(v*v for v in p[:3])<=0 for p in planes):
        raise ValueError('Invalid cached aligned track-clipping planes; rebuild the cache')
    return data
