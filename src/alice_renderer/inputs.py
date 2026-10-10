"""Inspect timeframes without interpreting timeframe entries as collisions."""
from __future__ import annotations
import gzip, hashlib, json, os, re, subprocess, sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from .model import DETECTORS
from .catalogue import fingerprint

@dataclass
class InputInfo:
    path: str
    format: str
    timeframes: int | None = None
    detectors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    records: list[dict] = field(default_factory=list)

def inspect_input(path: Path, *, cancelled=lambda:False) -> InputInfo:
    path=Path(path)
    if not path.exists(): raise ValueError(f'Input does not exist: {path}')
    if path.is_dir() or path.suffix in ('.json','.jsonl') or path.name.endswith(('.json.gz','.jsonl.gz')):
        return InputInfo(str(path),'events')
    before=path.stat()
    if before.st_size==0: raise ValueError('Input file is empty')
    if path.suffix.lower() in ('.tf','.rawtf'):
        from .tf import inspect_tf
        metadata=inspect_tf(path,cancelled=cancelled)
        detectors=sorted({d for record in metadata['records'] for d,origin in record['origins'].items()
                          if d in DETECTORS and origin['payload_bytes']>0})
        return InputInfo(str(path),'raw_tf',metadata['timeframes'],detectors,
                         ['TF records are timeframes; reconstructed primary vertices define collision events.'],
                         metadata['records'])
    if path.suffix.lower() not in ('.root','.ctf'): raise ValueError('Choose a raw TF, ROOT CTF or exported event JSON/JSONL')
    try:
        import uproot
        with uproot.open(path,object_cache=None,array_cache=None) as file:
            matches=[k for k in file.keys(cycle=False) if k.lower()=='ctf']
            if not matches: raise ValueError('ROOT file does not contain a CTF tree; export reconstructed data to event JSON instead')
            tree=file[matches[0]]
            branches=tree.keys(recursive=False)
            detectors=sorted({d for d in DETECTORS if any(k.startswith(d+'_') or k.rstrip('.')==d for k in branches)})
            result=InputInfo(str(path),'ctf',int(tree.num_entries),detectors)
            if 'CTFHeader' in tree:
                header=tree['CTFHeader'];fields=('run','tfCounter','firstTForbit','creationTime')
                if all(name in header for name in fields):
                    arrays=[header[name].array(library='np') for name in fields]
                    result.records=[dict(run=int(run),tf_counter=int(tf),orbit=int(orbit),timestamp_ms=int(created))
                                    for run,tf,orbit,created in zip(*arrays)]
                    unique={(r['run'],r['tf_counter'],r['orbit']) for r in result.records}
                    if len(unique)!=result.timeframes:
                        result.warnings.append(f'{result.timeframes} CTF entries contain only {len(unique)} distinct TF identities; repeated headers must be resolved before collision extraction.')
            result.warnings.append('CTF entries are timeframes; reconstructed primary vertices define collision events.')
            if not detectors: result.warnings.append('Detector branches not recognized; O2 must inspect the detector mask.')
    except Exception as exc:
        raise ValueError(f'Cannot read CTF header. File may be incomplete, corrupt or unsupported: {exc}') from exc
    after=path.stat()
    if (before.st_size,before.st_mtime_ns)!=(after.st_size,after.st_mtime_ns): raise ValueError('Input is still changing; wait for the download/copy to finish')
    return result

def run_ingest_profile(source: Path, profile: Path, cache: Path, *, progress=lambda s:None, cancelled=lambda:False) -> Path:
    """Run an explicitly configured O2 adapter in a fresh cache directory.

    Profile argv is a list, never shell-expanded. Placeholders: {input}, {output}, {python}, {project}, {profile_dir}.
    A preflight_argv is mandatory and runs before costly reconstruction.
    Adapter writes events.jsonl and manifest.json and must declare complete enumeration.
    """
    source,profile,cache=map(Path,(source,profile,cache))
    data=json.loads(profile.read_text())
    for field in ('argv','preflight_argv'):
        if not isinstance(data.get(field),list) or not data[field] or not all(isinstance(x,str) for x in data[field]):
            raise ValueError(f'O2 profile needs a nonempty {field} argument list')
    profile_key=fingerprint(profile)
    dependencies=data.get('configuration_files',[])
    if not isinstance(dependencies,list) or not all(isinstance(x,str) for x in dependencies):
        raise ValueError('configuration_files must be a list of configuration paths')
    if dependencies:
        digest=hashlib.sha256(profile_key.encode())
        for name in dependencies:
            path=Path(name)
            if not path.is_absolute():path=profile.parent/path
            digest.update(fingerprint(path).encode())
        profile_key=digest.hexdigest()[:24]
    key=fingerprint(source)+'-'+profile_key
    directory=cache/'processed'/key
    directory.mkdir(parents=True,exist_ok=True)
    output=directory/'events.jsonl'
    marker=directory/'manifest.json'
    def command(field): return [v.replace('{input}',str(source.resolve())).replace('{output}',str(directory.resolve())).replace('{python}',sys.executable).replace('{project}',str(Path(__file__).resolve().parents[2])).replace('{profile_dir}',str(profile.resolve().parent)) for v in data[field]]
    def validate_outputs():
        nonlocal output
        if not marker.is_file():return False
        manifest=json.loads(marker.read_text())
        name=manifest.get('events_file','events.jsonl')
        if name not in ('events.jsonl','events.jsonl.gz'):raise ValueError('Unsupported export events_file')
        output=directory/name
        if not output.is_file():return False
        if manifest.get('schema_version')!=1 or manifest.get('complete') is not True:
            raise ValueError('O2 exporter must certify complete event enumeration in manifest.json')
        if manifest.get('event_grouping')!='primary_vertex':
            raise ValueError('TF/CTF collision rendering requires an exporter grouped by primary_vertex')
        if manifest.get('input_fingerprint')!=fingerprint(source): raise ValueError('O2 export cache does not match the current input')
        if not isinstance(manifest.get('event_count'),int) or manifest['event_count']<1: raise ValueError('O2 manifest has no collision event count')
        count=0
        with (gzip.open(output,'rt') if output.suffix=='.gz' else output.open()) as stream:
            for line in stream:
                if not line.strip():continue
                from .enumeration import event_header
                item=event_header(line)
                if item.get('kind')!='collision':raise ValueError('Primary-vertex export contains a non-collision record; export unassigned data separately')
                count+=1
        if count!=manifest['event_count']:raise ValueError('O2 manifest event_count does not match exported collision records')
        if manifest.get('enumeration_inventory'):
            from .enumeration import reconcile_export
            if manifest['enumeration_inventory']!='pv-inventory.jsonl':raise ValueError('Unsupported enumeration inventory filename')
            info=inspect_input(source,cancelled=cancelled)
            identities={(r['run'],r['tf_counter'],r['orbit']) for r in info.records} if info.records else None
            checked=reconcile_export(output,directory/'pv-inventory.jsonl',expected_timeframes=info.timeframes,
                                     expected_identities=identities,cancelled=cancelled)
            for name,value in checked.items():
                if manifest.get(name)!=value:raise ValueError(f'O2 manifest {name} does not match the independent inventory')
        return True
    try:
        if validate_outputs():return output
    except (ValueError,OSError):
        progress('Incomplete or invalid export cache; it will be rebuilt after prerequisite checks')
    import time,signal
    def execute(field,logname,timeout=None):
        if cancelled():raise InterruptedError('O2 processing cancelled')
        start=time.monotonic()
        with (directory/logname).open('w') as log:
            process=subprocess.Popen(command(field),cwd=directory,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
            def stop():
                try:os.killpg(process.pid,signal.SIGTERM)
                except ProcessLookupError:return
                try:process.wait(timeout=5)
                except subprocess.TimeoutExpired:os.killpg(process.pid,signal.SIGKILL);process.wait()
            while process.poll() is None:
                if cancelled():stop();raise InterruptedError('O2 processing cancelled')
                if timeout is not None and time.monotonic()-start>timeout:
                    stop();raise ValueError('O2 prerequisite check timed out; see preflight.log')
                time.sleep(.1)
        return process.returncode
    def clear_partial():
        output.unlink(missing_ok=True);marker.unlink(missing_ok=True)
        (directory/'events.jsonl').unlink(missing_ok=True);(directory/'events.jsonl.gz').unlink(missing_ok=True)
        (directory/'pv-inventory.jsonl').unlink(missing_ok=True)
        (directory/'pv-inventory.jsonl.complete.json').unlink(missing_ok=True)
    timeout=data.get('preflight_timeout_seconds',60)
    if not isinstance(timeout,(int,float)) or isinstance(timeout,bool) or not 1<=timeout<=3600:
        raise ValueError('preflight_timeout_seconds must be 1–3600')
    result=execute('preflight_argv','preflight.log',timeout)
    if result:
        with (directory/'preflight.log').open('rb') as log:
            log.seek(max(0,(directory/'preflight.log').stat().st_size-3000));tail=log.read().decode(errors='replace')
        raise ValueError('O2 prerequisites are not satisfied:\n'+tail)
    clear_partial()
    progress('O2 prerequisites checked; starting decoding/reconstruction and complete collision export')
    try:
        result=execute('argv','ingest.log')
        if result:raise ValueError(f'O2 processing failed ({result}). See {directory / "ingest.log"}')
        if not validate_outputs():raise ValueError('O2 adapter did not produce events.jsonl and manifest.json')
    except BaseException:
        clear_partial();raise
    return output
