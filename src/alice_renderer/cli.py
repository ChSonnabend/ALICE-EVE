import argparse, json
from pathlib import Path
from .catalogue import Catalogue
from .converters import convert
from .demo import generate
from .inputs import inspect_input, run_ingest_profile
from .model import RenderSettings
from .runtime import find_blender, probe, render_events, launch_editor
from .scene_config import load_config, resolve_settings, quality_settings, choose_event, recommended_quality

def main():
    parser=argparse.ArgumentParser(description='ALICE event catalogue and Blender rendering')
    sub=parser.add_subparsers(dest='command',required=True)
    inspect=sub.add_parser('inspect');inspect.add_argument('input',type=Path)
    demo=sub.add_parser('demo');demo.add_argument('--output',type=Path,default=Path('examples/synthetic-events.jsonl'))
    index=sub.add_parser('index');index.add_argument('input',type=Path);index.add_argument('--profile',type=Path);index.add_argument('--cache',type=Path,default=Path('cache'))
    devices=sub.add_parser('devices');devices.add_argument('--blender',default=find_blender())
    render=sub.add_parser('render');render.add_argument('catalogue',type=Path);render.add_argument('--events',default='all');render.add_argument('--settings',type=Path);render.add_argument('--blender',default=find_blender());render.add_argument('--output',type=Path,default=Path('renders'));render.add_argument('--preview',action='store_true')
    for name in ('render-config','edit-config'):
        command=sub.add_parser(name,help='Render or interactively edit a portable scene')
        command.add_argument('config',type=Path);command.add_argument('--input',type=Path);command.add_argument('--event',help='Event ID or ordinal:N; overrides config default')
        command.add_argument('--profile',type=Path);command.add_argument('--geometry-root',type=Path);command.add_argument('--assets',type=Path,help='Local detector-to-asset mapping; hashes still verified')
        command.add_argument('--cache',type=Path,default=Path('cache'));command.add_argument('--output',type=Path,default=Path('renders'))
        command.add_argument('--blender',default=find_blender());command.add_argument('--backend',default='AUTO',choices=['AUTO','CPU','METAL','HIP','CUDA','OPTIX']);command.add_argument('--device',default='')
        command.add_argument('--quality',default='balanced',choices=['draft','balanced','final','publication']);command.add_argument('--width',type=int);command.add_argument('--height',type=int);command.add_argument('--samples',type=int)
    args=parser.parse_args()
    try:
        if args.command=='inspect':print(json.dumps(inspect_input(args.input).__dict__,indent=2))
        elif args.command=='demo':print(generate(args.output))
        elif args.command=='devices':print(json.dumps(probe(args.blender),indent=2))
        elif args.command=='index':
            info=inspect_input(args.input);source=args.input
            if info.format!='events':
                if not args.profile:raise ValueError('TF/CTF requires a configured O2 ingestion profile before collision events can be listed; see docs/O2-INTEGRATION.md')
                source=run_ingest_profile(source,args.profile,args.cache,progress=print)
            cat=Catalogue.build(source,args.cache,convert=convert,progress=print)
            print(cat.folder)
            for row in cat.rows():print(json.dumps(row))
        elif args.command in ('render-config','edit-config'):
            data=load_config(args.config)
            source=args.input or (Path(data['defaults']['input']) if data.get('defaults',{}).get('input') else None)
            if source is None:raise ValueError('Provide --input; this portable scene has no default input')
            if args.input is None and not source.is_absolute():source=args.config.resolve().parent/source
            selector=args.event if args.event is not None else data.get('defaults',{}).get('event')
            cfg=resolve_settings(data,args.config,args.geometry_root,json.loads(args.assets.read_text()) if args.assets else None)
            devices_info=probe(args.blender);recommendation=recommended_quality(devices_info)
            backend=recommendation['backend'] if args.backend=='AUTO' else args.backend
            cfg=quality_settings(cfg,args.quality,backend=backend,device=args.device,width=args.width,height=args.height,samples=args.samples)
            info=inspect_input(source)
            if info.format!='events':
                if not args.profile:raise ValueError('Raw TF/CTF requires --profile for O2 collision extraction; exported events render directly')
                source=run_ingest_profile(source,args.profile,args.cache,progress=print)
            cat=Catalogue.build(source,args.cache,convert=convert,progress=print)
            event_path=choose_event(cat,selector)
            print('Recommended: '+recommendation['reason'])
            if args.command=='edit-config':print(launch_editor(args.blender,event_path,cfg,args.output)[0])
            else:print(render_events(args.blender,[event_path],cfg,args.output,progress=print))
        elif args.command=='render':
            cat=Catalogue(args.catalogue)
            ids=[row['ordinal'] for row in cat.rows()] if args.events=='all' else [int(v) for v in args.events.split(',')]
            settings=RenderSettings(**json.loads(args.settings.read_text())) if args.settings else RenderSettings()
            print(render_events(args.blender,[cat.event_path(i) for i in ids],settings,args.output,preview=args.preview,progress=print))
    except (ValueError,OSError,RuntimeError) as exc:parser.exit(1,str(exc)+'\n')

if __name__=='__main__':main()
