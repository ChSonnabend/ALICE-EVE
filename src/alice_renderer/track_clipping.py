"""Clip sampled trajectories to a union of aligned detector outer envelopes.

Planes use ALICE global centimetres: dot(normal, point) <= limit_cm.
This is a display extent mask, not an active-volume or hit-association test.
"""
from __future__ import annotations
import numpy as np


def selected_track_detectors(settings,track):
    from .object_selection import enabled_detectors
    selected=enabled_detectors(settings,'tracks')
    if settings.get('geometry'):selected&=set(settings['geometry'])
    return set(track['detectors'])&selected


def prepare_regions(regions):
    result={}
    for name,region in regions.items():
        planes=np.asarray(region['planes'],dtype=float)
        if planes.ndim!=2 or planes.shape[1]!=4 or len(planes)<4 or not np.isfinite(planes).all():raise ValueError(name+': invalid track clipping planes')
        result[name]=(planes[:,:3].T,planes[:,3])
    return result


def clip_polyline(points, regions, *, margin_cm=0.):
    """Return disconnected pieces, interpolating intersections even if both endpoints are outside."""
    if len(points)<2 or not regions:return []
    p=np.asarray(points,dtype=float);a,b=p[:-1],p[1:];intervals=[[] for _ in a]
    for normals,limits in regions:
        lengths=np.linalg.norm(normals,axis=0);bound=limits-margin_cm*lengths
        q=a@normals;delta=(b-a)@normals
        parallel=abs(delta)<1.e-12
        bad=np.any(parallel & (q>bound+1.e-8),axis=1)
        ratio=np.zeros_like(delta);np.divide(bound-q,delta,out=ratio,where=~parallel)
        lo=np.maximum(0.,np.max(np.where(delta< -1.e-12,ratio,-np.inf),axis=1))
        hi=np.minimum(1.,np.min(np.where(delta>1.e-12,ratio,np.inf),axis=1))
        for i in np.flatnonzero(~bad & (hi-lo>1.e-10)):intervals[i].append((float(lo[i]),float(hi[i])))
    pieces=[];current=[]
    for i,values in enumerate(intervals):
        merged=[]
        for lo,hi in sorted(values):
            if merged and lo<=merged[-1][1]+1.e-9:merged[-1]=(merged[-1][0],max(hi,merged[-1][1]))
            else:merged.append((lo,hi))
        for lo,hi in merged:
            start=a[i]+lo*(b[i]-a[i]);end=a[i]+hi*(b[i]-a[i])
            if current and np.linalg.norm(np.asarray(current[-1])-start)<=1.e-7:current.append(end.tolist())
            else:
                if len(current)>1:pieces.append(current)
                current=[start.tolist(),end.tolist()]
            if hi<1.-1.e-9:
                pieces.append(current);current=[]
        if not merged and current:
            pieces.append(current);current=[]
    if len(current)>1:pieces.append(current)
    return pieces
