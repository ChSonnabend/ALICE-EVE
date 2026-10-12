"""Blender device discovery, preflight and separately reproducible event jobs."""
from __future__ import annotations
import dataclasses, json, os, shutil, subprocess, sys, tempfile, time
from pathlib import Path
from .model import RenderSettings, capabilities
from .catalogue import load_event
from .object_selection import selected_tracks,selected_clusters,enabled_detectors
from .palettes import materialize,sample,names

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
    from .geometry_selection import is_schematic,detail
    values=settings.to_dict()
    errors=[]
    if tuple(devices.get('version',[0,0])[:2])<(4,5): errors.append('Blender 4.5 or newer is required')
    available=[d for d in devices.get('devices',[]) if d['type']==settings.backend]
    if settings.device: available=[d for d in available if d['id']==settings.device]
    if settings.render_engine=='CYCLES' and not available:
        if settings.device:errors.append(f'Selected device {settings.device!r} is not available for {settings.backend}. Check devices and choose a current device ID.')
        else:errors.append(f'No usable {settings.backend} device found in this Blender build. Select CPU or install a compatible backend/driver.')
    count=0;peak_points=0;peak_clusters=0;clip_assets=set()
    for event in events:
        count+=1
        tracks=selected_tracks(event,settings.to_dict())
        clusters=selected_clusters(event,settings.to_dict())
        if event.get('calibration_timestamp_ms') is not None and event.get('coordinate_export_version',0)<3 and (any(t.get('source')=='TPC' for t in tracks) or any(c['detector']=='TPC' for c in clusters)):
            errors.append('Legacy TF export has unsupported TPC time hypotheses that can misplace tracks or clusters. Re-export with coordinate exporter version 3 or load the corrected dataset; no render was started.')
        if settings.clip_tracks and bool(enabled_detectors(values,'tracks')) and event['kind']!='synthetic':
            from .track_clipping import selected_track_detectors
            clip_assets.update(d for t in tracks for d in selected_track_detectors(values,t) if not is_schematic(values,d))
        peak_points=max(peak_points,sum(len(t['points']) for t in tracks));peak_clusters=max(peak_clusters,len(clusters))
        for name,mode,objects,active in [('tracks',settings.track_color_mode,tracks,bool(enabled_detectors(settings.to_dict(),'tracks'))),('clusters',settings.cluster_color_mode,clusters,bool(enabled_detectors(settings.to_dict(),'clusters')))]:
            if active and settings.detectors and mode not in capabilities(objects): errors.append(f'Event {event["id"]}: {mode} is unavailable for selected {name}')
        if settings.detectors and not tracks and not clusters:errors.append(f'Event {event["id"]}: no selected tracks or clusters')
    for name in sorted(clip_assets):
        asset=settings.geometry_assets.get(name,'')
        if not asset or not Path(asset).is_file():errors.append(f'{name}: aligned geometry is required for track clipping. Provide its asset in Setup or explicitly disable Clip tracks to selected detectors.')
        elif Path(asset).suffix.lower() not in ('.glb','.gltf','.obj','.blend'):errors.append(f'{name}: unsupported track-clipping geometry format')
    if not count:errors.append('Select at least one event')
    # Conservative scene-buffer estimate; geometry, Blender and driver allocations add overhead.
    estimated=peak_points*768+peak_clusters*1536+settings.width*settings.height*128
    for name in settings.geometry+(['L3'] if settings.magnet else []):
        if not is_schematic(values,name):
            value=settings.geometry_assets.get(name,'')
            if not value:continue
            asset=Path(value)
            qa=asset.with_suffix('.qa.json')
            if qa.is_file():
                try:
                    geometry=json.loads(qa.read_text())
                    estimated+=int(geometry['instances'])*512+int(geometry['shapes'])*65536 if detail(values,name)=='full' else 256*65536
                except (OSError,ValueError,KeyError,TypeError):pass
    try:
        import psutil
        if estimated>psutil.virtual_memory().available*.8:
            errors.append(f'Estimated scene/image buffers need at least {estimated/1024**3:.1f} GiB, exceeding the safe available RAM budget. Reduce selected objects or resolution.')
    except ImportError:pass
    for name in settings.geometry+(['L3'] if settings.magnet else []):
        if not is_schematic(values,name):
            asset=settings.geometry_assets.get(name,'')
            if not asset or not Path(asset).is_file(): errors.append(f'{name}: provide detector geometry (.glb, .gltf, .obj, .blend), or explicitly select schematic envelopes')
            elif Path(asset).suffix.lower() not in ('.glb','.gltf','.obj','.blend'): errors.append(f'{name}: unsupported geometry format')
    for name in set(settings.geometry+(['L3'] if settings.magnet else []))|clip_assets:
        if not is_schematic(values,name) and detail(values,name)=='proxy':
            try:
                from .surface_proxy import load
                cache=load(settings.geometry_assets.get(name,''),settings.geometry_units)
                if cache['detector']!=name:raise ValueError('Fast surface cache detector differs from selected asset')
                if settings.geometry_inner_masks.get(name):raise ValueError('Clear inner-placement masks before using approximate surfaces')
                if settings.geometry_display.get(name,'surfaces')!='surfaces':raise ValueError('Choose Existing surfaces for cached approximate surfaces')
            except (OSError,ValueError,KeyError) as exc:errors.append(name+': '+str(exc))
        if not is_schematic(values,name) and detail(values,name)=='structural':
            try:
                from .structural_geometry import load,SUPPORTED
                if name not in SUPPORTED:raise ValueError('Large surfaces support ITS/TPC; choose full or coarse-cell geometry for this detector')
                cache=load(settings.geometry_assets.get(name,''),settings.geometry_units)
                if cache['detector']!=name:raise ValueError('Large-surface cache detector differs from selected asset')
                if settings.geometry_inner_masks.get(name):raise ValueError('Clear inner-placement masks; merged large surfaces use component choices/openings')
                if settings.geometry_display.get(name,'surfaces')!='surfaces':raise ValueError('Choose Existing surfaces for cached large surfaces')
            except (OSError,ValueError,KeyError) as exc:errors.append(name+': '+str(exc))
    from .geometry_components import load_components
    for name,choices in settings.geometry_components.items():
        if not choices or name not in settings.geometry+(['L3'] if settings.magnet else []):continue
        try:
            if is_schematic(values,name):raise ValueError('Component choices require aligned full/simplified geometry')
            metadata=load_components(settings.geometry_assets.get(name,''))
            if not metadata:raise ValueError('Detector hierarchy metadata is missing')
            unknown=set(choices)-set(metadata['components'])
            if unknown:raise ValueError('Unknown components: '+', '.join(sorted(unknown)))
        except (OSError,ValueError) as exc:errors.append(name+': '+str(exc))
    output=Path(output)
    try:
        output.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryFile(dir=output): pass
    except OSError as exc: errors.append(f'Output directory is not writable: {exc}')
    return list(dict.fromkeys(errors))

def geometry_only_input(output):
    """Explicit empty scene input; never impersonates a collision or demo event."""
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    path=output/'geometry-only.json'
    path.write_text(json.dumps({'schema_version':1,'units':'cm','kind':'geometry','id':'Geometry only','tracks':[],'clusters':[]}))
    return path


def fast_editor_settings(settings):
    """Use validated cached surfaces where compatible; preserve other detectors."""
    import copy
    from .geometry_selection import is_schematic
    from .structural_geometry import load
    cfg=copy.deepcopy(settings)
    values=cfg.to_dict()
    for name in cfg.geometry+(['L3'] if cfg.magnet else []):
        if name not in ('ITS','TPC') and cfg.geometry_lods.get(name,cfg.geometry_lod)=='structural':cfg.geometry_lods[name]='full'
    for name in cfg.geometry+(['L3'] if cfg.magnet else []):
        if is_schematic(values,name) or cfg.geometry_inner_masks.get(name) or cfg.geometry_display.get(name,'surfaces')!='surfaces':continue
        try:
            from .surface_proxy import load as load_proxy
            data=load_proxy(cfg.geometry_assets.get(name,''),cfg.geometry_units)
            if data['detector']!=name:continue
            cfg.geometry_lods[name]='proxy';continue
        except (OSError,ValueError,KeyError):pass
        if name not in ('ITS','TPC'):continue
        try:load(cfg.geometry_assets.get(name,''),cfg.geometry_units)
        except (OSError,ValueError,KeyError):continue
        cfg.geometry_lods[name]='structural'
    return cfg


def render_events(blender: str, paths: list[Path], settings: RenderSettings, output: Path, *, preview=False, progress=lambda s:None, cancelled=lambda:False, library_path=None):
    output=Path(output)
    if not paths:
        if not settings.geometry and not settings.magnet:raise ValueError('Select detector geometry for a geometry-only render')
        paths=[geometry_only_input(output)]
        settings=dataclasses.replace(settings,detectors=[],highlight_track_ids=[])
    settings.validate()
    effective=materialize(dataclasses.replace(settings))
    if preview:
        factor=min(1.,640/max(effective.width,effective.height))
        effective.width=max(64,int(effective.width*factor));effective.height=max(64,int(effective.height*factor))
        # Nested transparent detector surfaces need enough samples to converge;
        # keep resolution low while letting translucent surfaces converge.
        effective.samples=128;effective.denoise=True;effective.save_blend=False
    # Re-check at execution, not only in the UI. Never silently switch the selected backend.
    progress('Checking Blender devices and render prerequisites')
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
        progress('Building scene and loading detector geometry')
        from .render_progress import sample_percent
        last_percent=-1
        def report(line):
            nonlocal last_percent
            if 'ALICE_STAGE ' in line:progress(line.split('ALICE_STAGE ',1)[1].strip())
            percent=sample_percent(line)
            if percent is not None and percent>last_percent:
                last_percent=percent
                overall=int((index+percent/100)*100/len(paths))
                progress(f'Render progress: {overall}% — event {index+1}/{len(paths)}: {percent}%')
        with (folder/'blender.log').open('w') as log, (folder/'blender.log').open() as status:

            process=subprocess.Popen(command,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
            while process.poll() is None:
                for line in status:report(line)
                if cancelled():
                    import signal
                    os.killpg(process.pid,signal.SIGTERM)
                    try: process.wait(timeout=5)
                    except subprocess.TimeoutExpired: os.killpg(process.pid,signal.SIGKILL); process.wait()
                    raise InterruptedError('Render cancelled')
                time.sleep(.1)
            for line in status:report(line)
        if process.returncode or not (folder/'render.png').exists(): raise ValueError(f'Blender failed for event {event_id}. See {folder/"blender.log"}')
        # Worker output contains display ranges, counts and geometry provenance.
        from .scene_library import SceneLibrary
        SceneLibrary(library_path).record_job(folder)
        progress(f'Render progress: {int((index+1)*100/len(paths))}% — event {index+1}/{len(paths)} saved')
        progress(str(folder/'render.png'))
    return batch

def launch_editor(blender, event_path, settings, output, *, library_path=None, fast=True):
    """Launch native Blender editing; quality is chosen only by Render full."""
    import copy
    cfg=materialize(fast_editor_settings(settings) if fast else copy.deepcopy(settings))
    if event_path is None:
        if not cfg.geometry and not cfg.magnet:raise ValueError('Select detector geometry for a geometry-only scene')
        event_path=geometry_only_input(output)
        cfg=dataclasses.replace(cfg,detectors=[],highlight_track_ids=[])
    for name in cfg.geometry+(['L3'] if cfg.magnet else []):
        cfg.geometry_openings.setdefault(name,180. if cfg.cutaway else 0.)
    cfg.cutaway=False
    devices=probe(blender)
    errors=preflight(cfg,[load_event(event_path)],devices,Path(output))
    if errors:raise ValueError('\n'.join(errors))
    folder=Path(output)/('editor-'+time.strftime('%Y%m%d-%H%M%S')+'-'+os.urandom(3).hex());folder.mkdir()
    job=folder/'job.json'
    payload={'fast_interactive':fast,'event':str(Path(event_path).resolve()),'output':str(folder.resolve()),'settings':cfg.to_dict(),'preview':True,'blender':devices,'python':sys.executable,'render_output':str(Path(output).resolve()),'palettes':{name:sample(name) for name in names()}}
    from .scene_library import SceneLibrary
    library=SceneLibrary(library_path);payload['library_path']=str(library.path.resolve())
    job.write_text(json.dumps(payload,indent=2))
    log=(folder/'editor.log').open('w')
    try:
        process=subprocess.Popen([blender,'--factory-startup','--python-exit-code','1','--python',str(WORKER),'--','--job',str(job),'--interactive'],stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
    finally:log.close()
    return folder,process.pid
