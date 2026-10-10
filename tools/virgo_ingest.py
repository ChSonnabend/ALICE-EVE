#!/usr/bin/env python3
"""GUI/CLI bridge to the explicitly selected Virgo O2 allocation.

Prerequisites, staging and condition checks precede reconstruction. A completion
manifest is published only after independent TF/PV reconciliation succeeds.
"""
import argparse,hashlib,json,shlex,shutil,subprocess,sys,uuid,tarfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from alice_renderer.inputs import inspect_input
from alice_renderer.catalogue import fingerprint
from alice_renderer.enumeration import reconcile_export
from alice_renderer.model import validate_event
from alice_renderer.runtime import find_blender
from alice_renderer.timeframe_views import export_views

def digest(path):
    value=hashlib.sha256()
    with path.open('rb') as stream:
        while block:=stream.read(4<<20):value.update(block)
    return value.hexdigest()

def main():
    p=argparse.ArgumentParser();p.add_argument('--input',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--runtime',type=Path,default=ROOT/'profiles/virgo4-runtime.json')
    p.add_argument('--configuration',type=Path,default=ROOT/'profiles/run-560067-raw.json')
    p.add_argument('--check',action='store_true');a=p.parse_args()
    source=a.input.resolve();out=a.output.resolve();out.mkdir(parents=True,exist_ok=True)
    runtime=json.loads(a.runtime.read_text());configuration=json.loads(a.configuration.read_text())
    host=runtime['host'];remote_root=runtime['work_directory'].rstrip('/')
    state_file=out/'remote-preparation.json'
    def remote(argv,log,cpus=None):
        command=[sys.executable,str(ROOT/'tools/o2_remote_exec.py'),'--config',str(a.runtime.resolve()),
                 '--argv',json.dumps(argv),'--log',str(out/log)]
        if cpus:command+=['--cpus',str(cpus)]
        result=subprocess.run(command)
        if result.returncode:
            path=out/log
            message=path.read_text(errors='replace')[-3000:] if path.exists() else 'No remote log returned'
            raise RuntimeError('Virgo prerequisite/reconstruction failed:\n'+message)
    if a.check:
        blender=find_blender()
        if not blender or not Path(blender).is_file():raise ValueError('Blender is required locally to prepare the aligned detector assets')
        info=inspect_input(source)
        if info.format not in ('raw_tf','ctf') or not info.records:raise ValueError('A TF/CTF with readable TF identities and calibration timestamps is required')
        identities={(r['run'],r['tf_counter'],r['orbit']) for r in info.records}
        if len(identities)!=info.timeframes:raise ValueError('Repeated TF identities in this input must be resolved before collision extraction; refusing to invent distinct collision identities')
        runs={r['run'] for r in info.records}
        if runs!={configuration['run']}:raise ValueError('The selected reconstruction configuration is for run '+str(configuration['run'])+'; choose a matching run configuration')
        if 'ITS' not in info.detectors:raise ValueError('The installed O2 collision workflow skips vertex reconstruction without ITS. Supply ITS payloads or reconstructed primary vertices. This input contains '+', '.join(info.detectors))
        if shutil.disk_usage(out).free<max(8<<30,source.stat().st_size*2):raise ValueError('Insufficient local disk for complete event and cluster export')
        state_file.unlink(missing_ok=True)
        for name in ('o2_workflow_driver.py','run_o2_workflow.py','check_o2_conditions.py','ccdb_http_cache.py','export_aligned_geometry.py','compress_export.py'):
            subprocess.run(['scp','-q',str(ROOT/'tools'/name),host+':'+remote_root+'/src/'+name],check=True)
        sha=digest(source);remote_input=remote_root+'/input/'+sha+source.suffix
        # A fresh staged file avoids altering any original input on Virgo.
        subprocess.run(['scp','-q',str(source),host+':'+remote_input],check=True)
        config=dict(configuration,input=remote_input,format=info.format,detectors=info.detectors.copy(),write_ctf=False)
        if info.format=='raw_tf' and any('CTP' in r['origins'] for r in info.records):config['detectors'].append('CTP')
        if info.format=='ctf':
            import uproot
            with uproot.open(source,object_cache=None,array_cache=None) as file:
                if any(k.startswith('CTP_') for k in file['ctf'].keys(recursive=False)):config['detectors'].append('CTP')
        first=info.records[0];config.update(timestamp_ms=first.get('timestamp_ms',first.get('creation_ms')),first_orbit=first['orbit'])
        sources=['ITS','TPC','MFT','MCH','MID','ITS-TPC','TPC-TOF','TPC-TRD','ITS-TPC-TOF',
                 'ITS-TPC-TRD','TPC-TRD-TOF','ITS-TPC-TRD-TOF','MFT-MCH','MCH-MID','MFT-MCH-MID']
        config['track_sources']=','.join(name for name in sources if set(name.split('-'))<=set(info.detectors))
        session=remote_root+'/runs/ingest-'+uuid.uuid4().hex
        local_config=out/'reconstruction-config.json';local_config.write_text(json.dumps(config,indent=2))
        remote_config=remote_root+'/src/config-'+uuid.uuid4().hex+'.json'
        subprocess.run(['scp','-q',str(local_config),host+':'+remote_config],check=True)
        code='''import hashlib,json,os,shutil,subprocess
from pathlib import Path
config=Path(CONFIG);directory=Path(DIRECTORY);data=json.loads(config.read_text());source=Path(data['input'])
h=hashlib.sha256()
with source.open('rb') as f:
 while block:=f.read(4<<20):h.update(block)
if h.hexdigest()!=SHA:raise RuntimeError('Staged input checksum differs')
for name in [data['exporter'],data['inventory']]:
 if not os.access(name,os.X_OK):raise RuntimeError('Native O2 exporter is not installed: '+name)
if shutil.disk_usage(source.parent).free<max(8<<30,source.stat().st_size*3):raise RuntimeError('Insufficient reconstruction disk')
subprocess.run(['python3',TOOLS+'/o2_workflow_driver.py','--config',str(config),'--output',str(directory)],check=True)
subprocess.run(['python3',TOOLS+'/run_o2_workflow.py',str(directory),'--dump'],check=True)
subprocess.run(['python3',TOOLS+'/check_o2_conditions.py','--workflow',str(directory/'workflow.json'),'--config',str(config),'--output',str(directory/'preflight-ccdb')],check=True)
'''
        values=dict(CONFIG=remote_config,DIRECTORY=session,SHA=sha,TOOLS=remote_root+'/src')
        declarations='\n'.join(k+'='+repr(v) for k,v in values.items())+'\n'
        remote(['python3','-c',declarations+code],'preparation.log',16)
        state_file.write_text(json.dumps(dict(input_fingerprint=fingerprint(source),input_sha256=sha,session=session,timeframes=info.timeframes,identities=sorted(identities),runtime_fingerprint=fingerprint(a.runtime),configuration_fingerprint=fingerprint(a.configuration))))
        print('Input, O2 workflows, field map and run conditions checked.',flush=True)
        return
    state=json.loads(state_file.read_text())
    if state['input_fingerprint']!=fingerprint(source) or state['runtime_fingerprint']!=fingerprint(a.runtime) or state['configuration_fingerprint']!=fingerprint(a.configuration):raise ValueError('Input or configuration changed since prerequisite checks')
    session=state['session'];remote(['python3',remote_root+'/src/run_o2_workflow.py',session],'reconstruction.log',16)
    remote(['python3',remote_root+'/src/compress_export.py',session+'/export'],'compression.log',8)
    for name in ('events.jsonl.gz','events.jsonl.complete.json','pv-inventory.jsonl','pv-inventory.jsonl.complete.json','timeframe-objects.jsonl.gz','aligned-geometry.root'):
        subprocess.run(['scp','-q',host+':'+session+'/export/'+name,str(out/name)],check=True)
    events=out/'events.jsonl.gz'
    checked=reconcile_export(events,out/'pv-inventory.jsonl',expected_timeframes=state['timeframes'],expected_identities={tuple(i) for i in state['identities']})
    completion=json.loads((out/'events.jsonl.complete.json').read_text())
    if completion.get('timeframes')!=checked['timeframes_processed'] or completion.get('vertices')!=checked['event_count']:raise ValueError('Exporter completion counts differ from independent inventory')
    # The saved manager is the exact geometry used for this reconstruction.
    # Reuse existing assets only after comparing every shape and global placement.
    surfaces=session+'/aligned-surfaces'
    remote(['python3',remote_root+'/src/export_aligned_geometry.py','--input',session+'/export/aligned-geometry.root',
            '--output',surfaces,'--converter',remote_root+'/src/reference-root2blend','--run',str(configuration['run'])],'geometry-export.log')
    geometry_report=out/'geometry-manifest.json'
    subprocess.run(['scp','-q',host+':'+surfaces+'/geometry-manifest.json',str(geometry_report)],check=True)
    desired=json.loads(geometry_report.read_text());asset_directory=ROOT/'geometry'/('run-'+str(configuration['run']))
    existing=json.loads((asset_directory/'geometry-manifest.json').read_text()) if (asset_directory/'geometry-manifest.json').exists() else {}
    same=bool(existing.get('assets')) and all(existing.get('detectors',{}).get(d,{}).get('json_sha256')==values['json_sha256']
         and Path(existing['assets'].get(d,'')).is_file() for d,values in desired['detectors'].items())
    if not same:
        archive=session+'/aligned-surfaces.tar.gz'
        code='import tarfile;from pathlib import Path\nwith tarfile.open('+repr(archive)+',"w:gz") as f:\n for p in Path('+repr(surfaces)+').glob("*.json"):f.add(p,arcname=p.name)\n'
        remote(['python3','-c',code],'geometry-pack.log')
        compressed=out/'aligned-surfaces.tar.gz';subprocess.run(['scp','-q',host+':'+archive,str(compressed)],check=True)
        folder=out/'aligned-surfaces'
        with tarfile.open(compressed) as files:files.extractall(folder,filter='data')
        asset_directory=out/'geometry'
        subprocess.run([sys.executable,str(ROOT/'tools/build_aligned_assets.py'),'--surfaces',str(folder),
                        '--output',str(asset_directory),'--blender',find_blender()],check=True)
        existing=json.loads((asset_directory/'geometry-manifest.json').read_text())
    geometry_assets=existing['assets']
    manifest=dict(schema_version=1,complete=True,event_grouping='primary_vertex',events_file='events.jsonl.gz',input_fingerprint=fingerprint(source),input_sha256=state['input_sha256'],enumeration_inventory='pv-inventory.jsonl',remote_session=session,unassigned_objects='timeframe-objects.jsonl.gz',aligned_geometry='aligned-geometry.root',**checked)
    manifest.update(geometry_assets=geometry_assets,geometry_units='m',geometry_reconstruction_sha256=desired['source_sha256'])
    print('Preparing separately labelled whole-TF detector views.',flush=True)
    views=export_views(out/'timeframe-objects.jsonl.gz',out/'timeframe-events.jsonl.gz')
    (out/'timeframe-views-qa.json').write_text(json.dumps(views,indent=2))
    if views['views']:manifest['timeframe_events_file']='timeframe-events.jsonl.gz'
    temporary=out/'manifest.tmp';temporary.write_text(json.dumps(manifest,indent=2));temporary.replace(out/'manifest.json')
    print('Verified '+str(checked['event_count'])+' collisions in every input timeframe.',flush=True)

if __name__=='__main__':
    try:main()
    except (ValueError,OSError,RuntimeError,subprocess.CalledProcessError) as error:raise SystemExit(str(error))
