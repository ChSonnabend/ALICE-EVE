"""Validated, pre-baked low-complexity aligned surfaces for interactive scenes."""
import gzip,json,math
from pathlib import Path
from functools import lru_cache
from .scene_config import sha256
from .geometry_components import sidecar_path as component_path


def sidecar_path(asset):return Path(str(asset)+'.surface.json.gz')

@lru_cache(maxsize=64)
def _read(path,mtime,size):
    with gzip.open(path,'rt') as stream:return json.load(stream)


def load(asset,units='m'):
    path=sidecar_path(asset)
    if not path.is_file():raise ValueError('Fast surface cache is missing; prepare this detector geometry first')
    stat=path.stat()
    return _validated(str(path.resolve()),stat.st_mtime_ns,stat.st_size,sha256(asset),sha256(component_path(asset)),units)

@lru_cache(maxsize=64)
def _validated(path,mtime,size,asset_hash,components_hash,units):
    data=_read(path,mtime,size)
    if data.get('schema')!='alice-surface-proxy' or data.get('version')!=1:raise ValueError('Unsupported fast surface cache')
    if data.get('source_units')!=units:raise ValueError('Fast surface cache units differ from geometry units')
    if data.get('asset_sha256')!=asset_hash or data.get('components_sha256')!=components_hash:raise ValueError('Fast surfaces differ from their aligned source; rebuild the cache')
    if not data.get('groups'):raise ValueError('Empty fast surface cache')
    for group in data['groups']:
        vertices=group.get('vertices',[])
        if not vertices or any(len(v)!=3 or not all(isinstance(x,(int,float)) and math.isfinite(x) for x in v) for v in vertices):raise ValueError('Invalid fast surface vertices')
        if not group.get('faces') or any(len(f)<3 or any(type(i)!=int or i<0 or i>=len(vertices) for i in f) for f in group['faces']):raise ValueError('Invalid fast surface faces')
    region=data.get('track_region')
    if region is not None:
        planes=region.get('planes',[])
        if region.get('units')!='cm' or len(planes)!=66 or any(len(p)!=4 or any(not isinstance(x,(int,float)) or not math.isfinite(x) for x in p) or sum(x*x for x in p[:3])<=0 for p in planes):raise ValueError('Invalid original-geometry clipping bounds')
    return data
