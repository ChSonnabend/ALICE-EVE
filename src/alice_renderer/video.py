"""Collision schedules and display propagation, independent of render hardware.

Speeds and tower rise times are video-time controls, not particle flight times.
LHC clock constants follow CommonConstants/LHCConstants.h in ALICE O2.
"""
from __future__ import annotations
import math
import numpy as np
from .object_selection import selected_tracks,selected_clusters

BUNCH_NS=10e9/400.789e6
ORBIT_US=3564*BUNCH_NS*.001

def header(event):
    fields=('id','kind','vertex','run','timeframe','orbit','vertex_time_us','global_bc','collision_time_ns','collision_timestamp_ns','available_detectors')
    return {k:event[k] for k in fields if k in event}

def relative_times(events):
    """Return fine collision times in seconds relative to the first collision."""
    first=events[0]
    if all(isinstance(e.get('collision_timestamp_ns'),(int,float)) for e in events):
        base=first['collision_timestamp_ns'];return [(e['collision_timestamp_ns']-base)*1e-9 for e in events],'explicit absolute collision timestamps'
    if len({str(e.get('run','')) for e in events})!=1:raise ValueError('Real-time video across different runs needs a common absolute collision clock. Choose fixed intervals.')
    if all(isinstance(e.get('global_bc'),int) and isinstance(e.get('collision_time_ns'),(int,float)) for e in events):
        return [((e['global_bc']-first['global_bc'])*BUNCH_NS+e['collision_time_ns']-first['collision_time_ns'])*1e-9 for e in events],'AO2D global BC plus collision time offset'
    if all(isinstance(e.get('vertex_time_us'),(int,float)) and isinstance(e.get('orbit'),int) for e in events):
        return [((e['orbit']-first['orbit'])*ORBIT_US+e['vertex_time_us']-first['vertex_time_us'])*1e-6 for e in events],'O2 first-TF orbit plus primary-vertex time'
    if all(isinstance(e.get('vertex_time_us'),(int,float)) and e.get('timeframe') is not None for e in events) and len({str(e['timeframe']) for e in events})==1:
        return [(e['vertex_time_us']-first['vertex_time_us'])*1e-6 for e in events],'primary-vertex times in a common timeframe'
    raise ValueError('Selected collisions lack a common fine timestamp. Choose fixed intervals, or export PV/BC timing. Calibration timestamps are not collision times.')

def schedule(events,settings):
    if len(events)<2:raise ValueError('Video needs at least two selected collisions')
    for event in events:
        if event.get('kind') not in ('collision','synthetic') or event.get('vertex') is None:raise ValueError(f'Event {event["id"]}: video requires a primary collision vertex; whole-TF/geometry views cannot be animated as collisions')
    fps=settings.get('video_fps',24);interval=settings.get('video_interval_s',1.)
    order=list(range(len(events)));starts=[i*interval for i in order];scale=None;basis='fixed video intervals'
    if settings.get('video_timing','fixed')=='realtime':
        times,basis=relative_times(events)
        if not all(math.isfinite(t) for t in times):raise ValueError('Collision timestamps must be finite')
        order.sort(key=lambda i:times[i]);span=times[order[-1]]-times[order[0]]
        scale=settings.get('video_time_scale',0.)
        if scale==0:
            if span<=0:raise ValueError('Identical collision timestamps cannot define an automatic time scale. Choose fixed intervals or set a positive time scale.')
            scale=(len(events)-1)/span
        starts=[(times[i]-times[order[0]])*scale for i in order]
    entries=[];previous=-1;shifted=0
    for i,start in zip(order,starts):
        tick=max(round(start*fps),previous+1);shifted+=int(tick!=round(start*fps));previous=tick
        entries.append(dict(source_index=i,event_id=events[i]['id'],frame_start=tick,requested_start_s=start,start_s=tick/fps))
    frames=entries[-1]['frame_start']+max(1,math.ceil(interval*fps))
    for i,entry in enumerate(entries):entry['frame_end']=entries[i+1]['frame_start'] if i+1<len(entries) else frames
    return dict(entries=entries,fps=fps,frames=frames,duration_s=frames/fps,time_scale=scale,timing_basis=basis,
                quantized_collisions=shifted,propagation_basis='display speed in metres per video second; not particle flight time')

def event_at(plan,frame):
    import bisect
    index=bisect.bisect_right([e['frame_start'] for e in plan['entries']],frame)-1
    index=max(0,min(index,len(plan['entries'])-1));entry=plan['entries'][index]
    return index,(frame-entry['frame_start'])/plan['fps']

def trajectory(track,vertex):
    points=np.asarray(track['points'],dtype=float)
    if np.linalg.norm(points[-1]-vertex)<np.linalg.norm(points[0]-vertex):points=points[::-1].copy()
    distances=np.r_[0.,np.cumsum(np.linalg.norm(np.diff(points,axis=0),axis=1))]
    distances+=np.linalg.norm(points[0]-vertex)
    return points,distances

def arrival_distances(points,distances,positions):
    """Closest sampled segment on an explicitly associated track, plus residual."""
    positions=np.asarray(positions,dtype=float);a=points[:-1];delta=np.diff(points,axis=0);length2=np.sum(delta*delta,axis=1)
    output=[]
    for start in range(0,len(positions),512):
        p=positions[start:start+512];diff=p[:,None,:]-a
        ratio=np.zeros(diff.shape[:2]);np.divide(np.einsum('ijk,jk->ij',diff,delta),length2,out=ratio,where=length2>0);ratio=np.clip(ratio,0,1)
        residual=np.linalg.norm(diff-ratio[:,:,None]*delta,axis=2);choice=np.argmin(residual,axis=1);rows=np.arange(len(p))
        output.extend((distances[choice]+ratio[rows,choice]*(distances[choice+1]-distances[choice])+residual[rows,choice]).tolist())
    return np.asarray(output)

def prepare_event(event,settings):
    """Precompute arrivals once; unlinked cells follow a PV-centred wave."""
    vertex=np.asarray(event['vertex'],dtype=float);paths={str(t['id']):trajectory(t,vertex) for t in event['tracks']}
    clusters=selected_clusters(event,settings);arrivals=np.asarray([np.linalg.norm(np.asarray(c['position'])-vertex) for c in clusters])
    linked={};count=0
    for i,c in enumerate(clusters):
        if str(c.get('track_id','')) in paths:linked.setdefault(str(c['track_id']),[]).append(i)
    for identity,indices in linked.items():
        points,distances=paths[identity];arrivals[indices]=arrival_distances(points,distances,[clusters[i]['position'] for i in indices]);count+=len(indices)
    return dict(tracks=selected_tracks(event,settings),paths=paths,clusters=clusters,cluster_arrival_s=arrivals/(100*settings.get('video_speed_m_s',10.)),
                linked_clusters=count,unlinked_clusters=len(clusters)-count,
                cluster_timing_basis='explicit track_id: closest sampled path point plus residual; unlinked objects: primary-vertex distance wave')
