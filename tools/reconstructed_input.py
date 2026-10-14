"""Inspect and export an O2 reconstructed-product folder without rerunning tracking."""
import json,shlex,uuid
from pathlib import Path

# Conventional filenames are discovery hints; the installed DPL graph is authoritative.
TRACKS={'ITS':'o2trac_its.root','TPC':'tpctracks.root','ITS-TPC':'o2match_itstpc.root',
        'MFT':'mfttracks.root','MCH':'mchtracks.root','MID':'mid-reco.root',
        'TPC-TRD':'trdmatches_tpc.root','ITS-TPC-TRD':'trdmatches_itstpc.root'}
CLUSTERS={'ITS':'o2clus_its.root','TPC':'tpc-native-clusters.root','MFT':'mftclusters.root',
          'MCH':'mchclusters.root','MID':'mid-reco.root','TRD':'trdtracklets.root',
          'TOF':'tofclusters.root','HMP':'hmpidclusters.root','EMC':'emccells.root',
          'PHS':'phoscells.root','CPV':'cpvclusters.root','FT0':'o2reco_ft0.root',
          'FV0':'o2reco_fv0.root','FDD':'o2reco_fdd.root','ZDC':'zdcreco.root'}
VERTICES=('o2_primary_vertex.root',)


def inspect(folder):
    folder=Path(folder).resolve()
    if not folder.is_dir():raise ValueError('Reconstructed input must be a directory')
    names={p.name for p in folder.glob('*.root') if p.is_file()}
    known=set(TRACKS.values())|set(CLUSTERS.values())|set(VERTICES)|{'tpctriggers.root','trdcalibratedtracklets.root','tfidinfo.root','o2_tfidinfo.root','o2_pvertex_track_matches.root'}
    return dict(input=str(folder),track_candidates=[k for k,v in TRACKS.items() if v in names],
                cluster_candidates=[k for k,v in CLUSTERS.items() if v in names],
                missing_vertex_files=[v for v in VERTICES if v not in names],
                timing_candidate=next((n for n in ('o2_tfidinfo.root','tfidinfo.root') if n in names),None),
                other_root_files=sorted(names-known),
                notes=['Filename discovery only; ROOT contents and matching TF order are not certified.',
                       'Keep all files from the same reconstruction, including ROF/index/pattern branches.',
                       'Supply original TF identity/timing metadata and run-specific conditions.',
                       'Missing measurements cannot be inferred; use original TF/CTF or digits to reconstruct them.'])


def input_requirements(workflow):
    """Use actual installed reader options, rather than assuming dependency names."""
    result=[]
    for device in workflow['workflow']:
        name=device['name']
        if not any(word in name.lower() for word in ('reader','publisher')):continue
        for option in device.get('options',[]):
            # Current O2 stores these branches in the vertex ROOT file. This
            # obsolete reader option is advertised but never read by init().
            if name=='primary-vertex-reader' and option['name']=='vertex-track-matches-infile':continue
            value=option.get('defaultValue',option.get('default'))
            if not isinstance(value,str) or not value.lower().endswith('.root'):continue
            if any(word in option['name'].lower() for word in ('output','outfile')):continue
            result.append(dict(reader=name,option=option['name'],file=value))
    return result


def check_inputs(workflow,directory,expected=()):
    requirements=input_requirements(workflow)
    missing=[r for r in requirements if not (Path(directory)/r['file']).is_file() and r['file'] not in expected]
    report=dict(requirements=requirements,missing=missing,expected_from_vertexing=list(expected))
    (Path(directory)/'input-requirements.json').write_text(json.dumps(report,indent=2))
    if missing:raise ValueError('Missing O2 reader inputs: '+', '.join(f"{r['file']} ({r['reader']})" for r in missing)+'. See input-requirements.json. Supply these products, reduce the selected sources, or reconstruct the original TF/CTF.')
    return report


def prepare_stage(directory,commands,config,files,timing):
    directory.mkdir()
    for name,path in files.items():(directory/name).symlink_to(path)
    session='alice-reco-'+uuid.uuid4().hex[:12]
    common=['-b','--session',session,'--shm-segment-id',str(10000+int(uuid.uuid4().hex[:4],16)%50000),
            '--shm-segment-size',str(config.get('shared_memory_bytes',24<<30)),
            '--timeframes-rate-limit','1','--timeframes-rate-limit-ipcid','0',
            '--monitoring-backend','no-op://','--fairmq-rate-logging','0',
            '--configKeyValues','NameConf.mCCDBServer='+config['condition_backend']+';HBFUtils.nHBFPerTF='+str(config['orbits_per_tf'])+';'+config.get('config_key_values','')]
    command=' | '.join(shlex.join([*c,*common]) for c in commands)
    (directory/'reconstruct.sh').write_text('#!/bin/bash\nset -euo pipefail\n'+command+'\n')
    env=dict(DPL_CONDITION_BACKEND=config['condition_backend'],ALIEN_PROC_ID=session,
             ALICEO2_CCDB_LOCALCACHE=str(directory/'ccdb'))
    (directory/'workflow-environment.json').write_text(json.dumps(env,indent=2))
    (directory/'workflow-provenance.json').write_text(json.dumps(dict(configuration=config,timing_file=str(timing),inputs={k:str(v) for k,v in files.items()}),indent=2))


def validate_vertices(path,count):
    import ROOT
    handle=ROOT.TFile.Open(str(path))
    if not handle or handle.IsZombie():raise ValueError('Cannot read primary vertex file: '+str(path))
    try:
        tree=handle.Get('o2sim')
        if not tree:raise ValueError('Primary vertex file lacks o2sim tree')
        missing=[name for name in ('PrimaryVertex','PVTrackIndices','PV2TrackRefs') if not tree.GetBranch(name)]
        if missing:raise ValueError('Primary vertex file lacks branches: '+', '.join(missing)+'. Rebuild vertices/associations with this O2 version.')
        if tree.GetEntries()!=count:raise ValueError('Primary vertex TF entry count differs from timing file')
    finally:handle.Close()


def process(args,run):
    folder=args.input.resolve();report=inspect(folder)
    config=json.loads(args.config.read_text())
    required=('run','timestamp_ms','first_orbit','orbits_per_tf','expected_timeframes','condition_backend','exporter','inventory','timing_file','track_sources','cluster_sources')
    missing=[k for k in required if k not in config]
    if missing:raise ValueError('Reconstructed-input config needs: '+', '.join(missing))
    if not isinstance(config['expected_timeframes'],int) or config['expected_timeframes']<1:raise ValueError('expected_timeframes must be positive')
    if not isinstance(config['orbits_per_tf'],int) or config['orbits_per_tf']<1:raise ValueError('orbits_per_tf must be positive')
    # Explicit sources prevent accidental use of every detector in a partial dataset.
    for key in ('track_sources','cluster_sources'):
        if not isinstance(config[key],str) or not config[key] or 'all' in config[key].lower():raise ValueError(key+' must be an explicit comma-separated list or none')
    for key in ('exporter','inventory'):
        if not Path(config[key]).is_absolute() or not Path(config[key]).is_file():raise ValueError(key+' must name an existing absolute executable path')
    timing=Path(config['timing_file'])
    if not timing.is_absolute():timing=folder/timing
    timing=timing.resolve()
    if not timing.is_file():raise ValueError('Supply a ROOT tfidinfo vector with the original TF identities and ordering')
    files={p.name:p.resolve() for p in folder.glob('*.root') if p.is_file()}
    for name,value in config.get('input_files',{}).items():
        if Path(name).name!=name or not name.endswith('.root'):raise ValueError('input_files keys must be canonical ROOT basenames')
        source=Path(value);source=source if source.is_absolute() else folder/source
        if not source.is_file():raise ValueError('Mapped input does not exist: '+str(source))
        files[name]=source.resolve()
    work=args.work.resolve()
    if work.exists() and any(work.iterdir()):raise ValueError('Use a fresh work directory')
    work.mkdir(parents=True,exist_ok=True)
    (work/'input-inspection.json').write_text(json.dumps(report,indent=2))
    cfg=work/'configuration.json';cfg.write_text(json.dumps(config,indent=2))
    export=work/'export';export.mkdir()
    if args.execute:
        # O2/PyROOT validates the actual identity vector; never synthesize TF IDs.
        import ROOT
        handle=ROOT.TFile.Open(str(timing))
        if not handle or handle.IsZombie():raise ValueError('Cannot read TF identity file')
        identities=handle.Get('tfidinfo')
        if not identities or len(identities)!=config['expected_timeframes']:raise ValueError('tfidinfo count does not match expected_timeframes')
        expected={(int(i.runNumber),int(i.tfCounter),int(i.firstTForbit)) for i in identities}
        if len(expected)!=len(identities) or any(i[0]!=config['run'] for i in expected):raise ValueError('Duplicate TF identities or wrong run in tfidinfo')
        if int(identities[0].firstTForbit)!=config['first_orbit']:raise ValueError('first_orbit differs from the first TF identity')
        handle.Close()
        if args.vertices=='reuse':validate_vertices(files.get(VERTICES[0],folder/VERTICES[0]),config['expected_timeframes'])
    else:expected=None
    stages=[]
    if args.vertices=='rebuild':
        sources=config.get('vertexing_sources')
        if not sources:raise ValueError('Rebuilding vertices requires explicit vertexing_sources (for example ITS)')
        files={k:v for k,v in files.items() if k not in VERTICES}
        stage=work/'vertexing'
        command=['o2-primary-vertexing-workflow','--disable-mc','--vertexing-sources',sources,
                 '--vertex-track-matching-sources',config.get('vertex_matching_sources',config['track_sources']),
                 '--hbfutils-config',str(timing)]
        prepare_stage(stage,[command],config,files,timing)
        run('run_o2_workflow.py',stage,'--dump')
        check_inputs(json.loads((stage/'workflow.json').read_text()),stage)
        stages.append(stage)
        for name in VERTICES:files[name]=stage/name
    elif any(name not in files for name in VERTICES):
        raise ValueError('Reuse needs '+', '.join(VERTICES)+'. Use --vertices rebuild with suitable fitted tracks, or reconstruct TF/CTF.')
    stage=work/'exporting'
    commands=[[config['exporter'],'--disable-mc','--display-tracks',config['track_sources'],
               '--display-clusters',config['cluster_sources'],'--jsons-folder',str(export),'--hbfutils-config',str(timing)],
              [config['inventory'],'--disable-root-input','--inventory-output',str(export/'pv-inventory.jsonl')]]
    prepare_stage(stage,commands,config,files,timing)
    run('run_o2_workflow.py',stage,'--dump')
    check_inputs(json.loads((stage/'workflow.json').read_text()),stage,VERTICES if args.vertices=='rebuild' else ())
    if not args.execute:
        print('Graphs and input requirements prepared; no reconstruction run. Inspect '+str(work))
        return
    stages.append(stage)
    # Check all conditions before doing expensive work; source files are only read.
    for current in stages:
        run('check_o2_conditions.py','--workflow',current/'workflow.json','--config',cfg,'--output',current/'preflight-ccdb')
    for current in stages:
        if current==stage:validate_vertices(files[VERTICES[0]],config['expected_timeframes'])
        check_inputs(json.loads((current/'workflow.json').read_text()),current)
        run('run_o2_workflow.py',current)
    from alice_renderer.enumeration import reconcile_export
    checked=reconcile_export(export/'events.jsonl',export/'pv-inventory.jsonl',expected_timeframes=config['expected_timeframes'],expected_identities=expected)
    run('compress_export.py',export)
    manifest=dict(schema_version=1,complete=True,events_file='events.jsonl.gz',event_grouping='primary_vertex',
                  enumeration_inventory='pv-inventory.jsonl',unassigned_objects='timeframe-objects.jsonl.gz',
                  aligned_geometry='aligned-geometry.root',input_kind='reconstructed-root',vertices=args.vertices,**checked)
    (export/'enumeration-qa.json').write_text(json.dumps(checked,indent=2))
    (export/'manifest.json').write_text(json.dumps(manifest,indent=2))
    print(export)
