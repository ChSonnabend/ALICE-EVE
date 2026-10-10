#!/usr/bin/env python3
"""Generate a reviewable local-file reconstruction pipeline from installed O2.

The upstream script's token guard is retained for execution. A copied generator
skips that guard only in print mode, which does not fetch conditions or run O2.
Reconstruction is executed separately after a validated condition preflight.
"""
import argparse,hashlib,json,os,shlex,subprocess,uuid
from pathlib import Path

def generate(configuration, directory):
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
    root=Path(os.environ['O2_ROOT']);original=root/'prodtests/full-system-test/dpl-workflow.sh'
    source=original.read_text()
    guard='if [[ $EPNSYNCMODE == 0 && ${DPL_CONDITION_BACKEND:-}'
    if source.count(guard)!=1:raise RuntimeError('Unrecognized installed workflow token guard')
    source=source.replace(guard,'if [[ $WORKFLOWMODE != "print" && $EPNSYNCMODE == 0 && ${DPL_CONDITION_BACKEND:-}',1)
    copied=directory/'workflow-generator.sh';copied.write_text(source)
    detectors=configuration['detectors']
    if not detectors or any(d not in 'ITS,TPC,TRD,TOF,HMP,EMC,PHS,CPV,MCH,MFT,MID,FT0,FV0,FDD,ZDC,CTP'.split(',') for d in detectors):
        raise ValueError('Invalid reconstruction detector list')
    input_file=Path(configuration['input']).resolve()
    staging=directory/'input';staging.mkdir(exist_ok=True)
    mode=configuration['format']
    target=staging/('o2_rawtf_input.tf' if mode=='raw_tf' else 'o2_ctf_input.root')
    if not target.exists():target.symlink_to(input_file)
    if mode not in ('raw_tf','ctf'):raise ValueError('Expected raw_tf or ctf')
    env=dict(os.environ)
    vmc=Path(env.get('VMCWORKDIR',str(root/'share')))
    if not (vmc/'Common/maps/mfchebKGI_sym.root').is_file():
        raise RuntimeError('O2 measured magnetic-field map is missing: '+str(vmc))
    env.update(GEN_TOPO_MYDIR=str(original.parent),WORKFLOWMODE='print',
        VMCWORKDIR=str(vmc),
        RAWINPUTDIR=str(staging),FILEWORKDIR=str(directory),FILEWORKDIRRUN=str(directory),
        RAWTFINPUT=str(int(mode=='raw_tf')),CTFINPUT=str(int(mode=='ctf')),EXTINPUT='0',DIGITINPUT='0',
        WORKFLOW_DETECTORS=','.join(detectors),WORKFLOW_DETECTORS_MATCHING='ALL',
        WORKFLOW_PARAMETERS='CTF' if configuration.get('write_ctf') else '',
        RUNTYPE='PHYSICS',IS_SIMULATED_DATA='0',BEAMTYPE=configuration['beam_type'],
        NHBPERTF=str(configuration['orbits_per_tf']),NTIMEFRAMES='-1',TFLOOP='0',
        GPUTYPE='CPU',NGPURECOTHREADS=str(configuration.get('threads',4)),
        NTRDTRKTHREADS='1',ITSTPC_THREADS='1',OMP_NUM_THREADS=str(configuration.get('threads',4)),
        GEN_TOPO_AUTOSCALE_PROCESSES='0',EPNPIPELINES='0',RECO_NUM_NODES_WORKFLOW='1',
        SHMSIZE=str(configuration.get('shared_memory_bytes',24<<30)),DISABLE_ROOT_OUTPUT='0',
        ALICEO2_CCDB_LOCALCACHE=str(directory/'ccdb'),DPL_CONDITION_BACKEND=configuration['condition_backend'],
        SETENV_NO_ULIMIT='1',TIMEFRAME_RATE_LIMIT='1',GLOBALDPLOPT='-b',
        OVERRIDE_SESSION='alice-'+uuid.uuid4().hex[:16],O2JOBSHMID=str(10000+int(uuid.uuid4().hex[:4],16)%50000),
        CTF_DIR=str(directory/'ctf'),CTF_MINSIZE='0',CTF_MAX_PER_FILE='1')
    # DPL's abstract metric-feedback socket otherwise uses SLURM_JOB_ID,
    # shared by every overlapping step, even with different session/shm IDs.
    # Its supported ALIEN_PROC_ID namespace isolates this private pipeline.
    env['ALIEN_PROC_ID']=env['OVERRIDE_SESSION']
    if configuration.get('tpc_lumi_type') is not None:
        kind=configuration['tpc_lumi_type']
        if kind not in (1,2):raise ValueError('TPC correction scaling requires CTP (1) or IDC (2)')
        env['TPC_CORR_SCALING']='--lumi-type '+str(kind)+' --corrmap-lumi-mode '+str(configuration.get('tpc_corrmap_mode',1))
    if configuration.get('write_ctf'):
        env['WORKFLOW_EXTRA_PROCESSING_STEPS']='ENTROPY_ENCODER'
        env['WORKFLOW_DETECTORS_CTF']=','.join(detectors)
        (directory/'ctf').mkdir(exist_ok=True)
    if mode=='ctf':
        # FileFetcher otherwise treats valid ROOT inputs with arbitrary names
        # (including our staged symlink) as text file lists and reads zero TFs.
        env['ARGS_EXTRA_PROCESS_o2_ctf_reader_workflow']=shlex.join(['--ctf-file-regex',r'.*\.root$'])
    if configuration.get('exporter'):
        output=directory/'export';output.mkdir(exist_ok=True)
        common=['--session',env['OVERRIDE_SESSION'],'--shm-segment-id',env['O2JOBSHMID'],
                '--shm-segment-size',env['SHMSIZE'],'--early-forward-policy','noraw',
                '--timeframes-rate-limit',env['TIMEFRAME_RATE_LIMIT'],'--timeframes-rate-limit-ipcid','0',
                '--monitoring-backend','no-op://','--fairmq-rate-logging','0']
        extra=[shlex.join([configuration['exporter'],'--disable-root-input','--disable-mc',
                          '--display-tracks',configuration.get('track_sources','all'),'--display-clusters',','.join(detectors),'--jsons-folder',str(output),*common])]
        if configuration.get('inventory'):
            extra.append(shlex.join([configuration['inventory'],'--disable-root-input','--inventory-output',str(output/'pv-inventory.jsonl'),*common]))
        env['EXTRA_WORKFLOW']=' | '.join(extra)+' | '
    result=subprocess.run(['bash',str(copied)],env=env,cwd=directory,capture_output=True,text=True,timeout=60)
    (directory/'generation.log').write_text(result.stdout+'\n'+result.stderr)
    if result.returncode:raise RuntimeError('Workflow generation failed; see generation.log')
    marker='#Workflow command:'
    if marker not in result.stdout:raise RuntimeError('Workflow generator produced no pipeline')
    command=result.stdout.split(marker,1)[1].strip()
    if not command.startswith('o2-'):raise RuntimeError('Unexpected workflow command')
    (directory/'reconstruct.sh').write_text('#!/bin/bash\nset -euo pipefail\n'+command+'\n')
    # Persist only the explicit overrides, never the user's full environment.
    changes={key:value for key,value in env.items() if value!=os.environ.get(key)}
    (directory/'workflow-environment.json').write_text(json.dumps(changes,indent=2))
    (directory/'workflow-provenance.json').write_text(json.dumps(dict(source=str(original),source_sha256=hashlib.sha256(original.read_bytes()).hexdigest(),configuration=configuration),indent=2))
    return directory/'reconstruct.sh'

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--config',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();print(generate(json.loads(args.config.read_text()),args.output.resolve()))

if __name__=='__main__':main()
