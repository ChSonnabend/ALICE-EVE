"""Blender device discovery, preflight and separately reproducible event jobs."""
from __future__ import annotations
import dataclasses, json, os, shutil, subprocess, sys, tempfile, time
from pathlib import Path
from .model import RenderSettings, capabilities
from .catalogue import load_event

WORKER=Path(__file__).parent/'blender'/'worker.py'

def find_blender() -> str:
    value=shutil.which('blender')
    if value: return value
    for p in ('/Applications/Blender.app/Contents/MacOS/Blender','C:/Program Files/Blender Foundation/Blender 5.0/blender.exe'):
        if Path(p).is_file(): return p
    return ''

def probe(blender: str) -> dict:
    if not blender or not Path(blender).is_file(): raise ValueError('Select an installed Blender executable')
    with tempfile.TemporaryDirectory(prefix='alice-device-check-') as tmp:
        output=Path(tmp)/'devices.json'
        command=[blender,'--background','--factory-startup','--python-exit-code','1','--python',str(WORKER),'--','--probe',str(output)]
        result=subprocess.run(command,capture_output=True,text=True,timeout=60)
        if result.returncode or not output.exists(): raise ValueError('Blender device discovery failed:\n'+result.stdout[-2000:]+result.stderr[-1000:])
        return json.loads(output.read_text())

def preflight(settings: RenderSettings, events, devices: dict, output: Path) -> list[str]:
    settings.validate()
    errors=[]
    if tuple(devices.get('version',[0,0])[:2])<(4,5): errors.append('Blender 4.5 or newer is required')
    available=[d for d in devices.get('devices',[]) if d['type']==settings.backend]
    if settings.device: available=[d for d in available if d['id']==settings.device]
    if not available:
        if settings.device:errors.append(f'Selected device {settings.device!r} is not available for {settings.backend}. Check devices and choose a current device ID.')
        else:errors.append(f'No usable {settings.backend} device found in this Blender build. Select CPU or install a compatible backend/driver.')
    if not settings.detectors:errors.append('Select at least one detector with event data')
    count=0;peak_points=0;peak_clusters=0
    for event in events:
        count+=1
        tracks=[t for t in event['tracks'] if set(t['detectors'])&set(settings.detectors)]
        clusters=[c for c in event['clusters'] if c['detector'] in settings.detectors]
        peak_points=max(peak_points,sum(len(t['points']) for t in tracks));peak_clusters=max(peak_clusters,len(clusters))
        for name,mode,objects,active in [('tracks',settings.track_color_mode,tracks,settings.mode!='clusters'),('clusters',settings.cluster_color_mode,clusters,settings.mode!='tracks')]:
            if active and mode not in capabilities(objects): errors.append(f'Event {event["id"]}: {mode} is unavailable for selected {name}')
        if (settings.mode=='tracks' and not tracks) or (settings.mode=='clusters' and not clusters) or (settings.mode=='both' and not tracks and not clusters):
            errors.append(f'Event {event["id"]}: no selected objects for {settings.mode}')
    if not count:errors.append('Select at least one event')
    # Conservative scene-buffer estimate; geometry, Blender and driver allocations add overhead.
    estimated=peak_points*768+peak_clusters*1536+settings.width*settings.height*128
    if not settings.schematic:
        for name in settings.geometry+(['L3'] if settings.magnet else []):
            value=settings.geometry_assets.get(name,'')
            if not value:continue
            asset=Path(value)
            qa=asset.with_suffix('.qa.json')
            if qa.is_file():
                try:
                    geometry=json.loads(qa.read_text())
                    estimated+=int(geometry['instances'])*512+int(geometry['shapes'])*65536 if settings.geometry_lod=='full' else 256*65536
                except (OSError,ValueError,KeyError,TypeError):pass
    try:
        import psutil
        if estimated>psutil.virtual_memory().available*.8:
            errors.append(f'Estimated scene/image buffers need at least {estimated/1024**3:.1f} GiB, exceeding the safe available RAM budget. Reduce selected objects or resolution.')
    except ImportError:pass
    if not settings.schematic:
        for name in settings.geometry+(['L3'] if settings.magnet else []):
            asset=settings.geometry_assets.get(name,'')
            if not asset or not Path(asset).is_file(): errors.append(f'{name}: provide detector geometry (.glb, .gltf, .obj, .blend), or explicitly select schematic envelopes')
            elif Path(asset).suffix.lower() not in ('.glb','.gltf','.obj','.blend'): errors.append(f'{name}: unsupported geometry format')
    output=Path(output)
    try:
        output.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryFile(dir=output): pass
    except OSError as exc: errors.append(f'Output directory is not writable: {exc}')
    return list(dict.fromkeys(errors))

def render_events(blender: str, paths: list[Path], settings: RenderSettings, output: Path, *, preview=False, progress=lambda s:None, cancelled=lambda:False):
    output=Path(output)
    settings.validate()
    effective=dataclasses.replace(settings)
    if preview:
        factor=min(1.,640/max(effective.width,effective.height))
        effective.width=max(64,int(effective.width*factor));effective.height=max(64,int(effective.height*factor))
        effective.samples=min(16,effective.samples);effective.save_blend=False
    # Re-check at execution, not only in the UI. Never silently switch the selected backend.
    devices=probe(blender)
    events=(load_event(p) for p in paths)
    errors=preflight(effective,events,devices,output)
    if errors: raise ValueError('\n'.join(errors))
    batch=output/(('preview-' if preview else 'render-')+time.strftime('%Y%m%d-%H%M%S')+'-'+os.urandom(3).hex())
    batch.mkdir()
    for index,path in enumerate(paths):
        if cancelled(): raise InterruptedError('Render cancelled')
        cfg=dataclasses.replace(effective)
        folder=batch/f'event-{index:05d}'
        folder.mkdir()
        job=folder/'job.json'
        payload={'event':str(Path(path).resolve()),'output':str(folder.resolve()),'settings':cfg.to_dict(),'preview':preview,'blender':devices}
        job.write_text(json.dumps(payload,indent=2))
        command=[blender,'--background','--factory-startup','--python-exit-code','1','--python',str(WORKER),'--','--job',str(job)]
        event_id=load_event(path)['id']
        progress(f'{index+1}/{len(paths)} — event {event_id}')
        with (folder/'blender.log').open('w') as log:
            process=subprocess.Popen(command,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
            while process.poll() is None:
                if cancelled():
                    import signal
                    os.killpg(process.pid,signal.SIGTERM)
                    try: process.wait(timeout=5)
                    except subprocess.TimeoutExpired: os.killpg(process.pid,signal.SIGKILL); process.wait()
                    raise InterruptedError('Render cancelled')
                time.sleep(.1)
        if process.returncode or not (folder/'render.png').exists(): raise ValueError(f'Blender failed for event {event_id}. See {folder/"blender.log"}')
        # Worker output contains display ranges, counts and geometry provenance.
        progress(str(folder/'render.png'))
    return batch

def launch_editor(blender, event_path, settings, output):
    """Launch native Blender editing; quality is chosen only by Render full."""
    import copy
    cfg=copy.deepcopy(settings)
    for name in cfg.geometry+(['L3'] if cfg.magnet else []):
        cfg.geometry_openings.setdefault(name,180. if cfg.cutaway else 0.)
    cfg.cutaway=False
    devices=probe(blender)
    errors=preflight(cfg,[load_event(event_path)],devices,Path(output))
    if errors:raise ValueError('\n'.join(errors))
    folder=Path(output)/('editor-'+time.strftime('%Y%m%d-%H%M%S')+'-'+os.urandom(3).hex());folder.mkdir()
    job=folder/'job.json'
    payload={'event':str(Path(event_path).resolve()),'output':str(folder.resolve()),'settings':cfg.to_dict(),'preview':True,'blender':devices,'python':sys.executable,'render_output':str(Path(output).resolve())}
    job.write_text(json.dumps(payload,indent=2))
    log=(folder/'editor.log').open('w')
    try:
        process=subprocess.Popen([blender,'--factory-startup','--python-exit-code','1','--python',str(WORKER),'--','--job',str(job),'--interactive'],stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
    finally:log.close()
    return folder,process.pid
