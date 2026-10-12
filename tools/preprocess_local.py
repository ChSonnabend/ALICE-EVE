#!/usr/bin/env python3
"""Local O2 preprocessing: build exporters, reconstruct TF/CTF, or prepare AO2D conditions."""
import argparse,json,os,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))


def run(tool,*args):
    subprocess.run([sys.executable,str(ROOT/'tools'/tool),*map(str,args)],check=True)


def main():
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='action',required=True)
    b=sub.add_parser('build');b.add_argument('--o2-source',type=Path,required=True);b.add_argument('--work',type=Path,required=True)
    r=sub.add_parser('reconstruct');r.add_argument('--input',type=Path,required=True);r.add_argument('--format',choices=['tf','ctf'],required=True);r.add_argument('--config',type=Path,required=True);r.add_argument('--work',type=Path,required=True);r.add_argument('--execute',action='store_true',help='Run after workflow and CCDB preflight; otherwise only prepare the graph')
    a=sub.add_parser('ao2d');a.add_argument('--input',type=Path,required=True);a.add_argument('--runs',type=int,nargs='+',required=True);a.add_argument('--cache',type=Path,required=True)
    args=p.parse_args()
    if not os.environ.get('O2_ROOT'):p.error('Activate O2PDPSuite first (or use run_in_o2.py --pid PID -- python3 ...)')
    if args.action=='build':
        work=args.work.resolve();work.mkdir(parents=True,exist_ok=True);source=work/'exporter-source'
        if source.exists():p.error('Use a fresh work directory; exporter-source already exists')
        run('prepare_o2_exporter.py','--reference',args.o2_source.resolve(),'--output',source,'--templates',ROOT/'native')
        run('build_o2_exporter.py',source,work/'alice-complete-export-workflow')
        run('build_pv_inventory.py',ROOT/'native/pv_inventory.cxx',work/'alice-pv-inventory-workflow')
        return
    if not args.input.is_file():p.error('Input file does not exist')
    if args.action=='ao2d':
        run('ao2d_field_conditions.py','--runs',*args.runs,'--cache',args.cache.resolve(),'--output',str(args.input.resolve())+'.renderer.json');return
    config=json.loads(args.config.read_text());config.update(input=str(args.input.resolve()),format='raw_tf' if args.format=='tf' else 'ctf')
    required=['run','timestamp_ms','first_orbit','orbits_per_tf','beam_type','detectors','condition_backend','exporter','inventory','expected_timeframes']
    missing=[key for key in required if key not in config]
    if missing:p.error('Supply run-specific configuration fields: '+', '.join(missing))
    for key in ['exporter','inventory']:
        if not Path(config[key]).is_file():p.error(key+' executable does not exist')
    work=args.work.resolve()
    if work.exists() and any(work.iterdir()):p.error('Use an empty work directory to avoid mixing reconstruction products')
    work.mkdir(parents=True,exist_ok=True);cfg=work/'configuration.json';cfg.write_text(json.dumps(config,indent=2))
    run('o2_workflow_driver.py','--config',cfg,'--output',work)
    run('run_o2_workflow.py',work,'--dump')
    if not args.execute:
        print('Workflow prepared. To execute, rerun with --execute and a fresh --work directory.');return
    run('check_o2_conditions.py','--workflow',work/'workflow.json','--config',cfg,'--output',work/'preflight-ccdb')
    run('run_o2_workflow.py',work)
    from alice_renderer.enumeration import reconcile_export
    export=work/'export'
    checked=reconcile_export(export/'events.jsonl',export/'pv-inventory.jsonl',expected_timeframes=config['expected_timeframes'])
    run('compress_export.py',export)
    manifest=dict(schema_version=1,complete=True,events_file='events.jsonl.gz',event_grouping='primary_vertex',enumeration_inventory='pv-inventory.jsonl',unassigned_objects='timeframe-objects.jsonl.gz',aligned_geometry='aligned-geometry.root',**checked)
    (export/'enumeration-qa.json').write_text(json.dumps(checked,indent=2))
    temporary=export/'manifest.tmp';temporary.write_text(json.dumps(manifest,indent=2));temporary.replace(export/'manifest.json')
    print(export)

if __name__=='__main__':main()
