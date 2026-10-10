#!/usr/bin/env python3
"""Execute an argv list in a separate step of a user-selected O2 allocation.

No interactive shell injection, no new allocation, no changes to the original step.
"""
import argparse, json, os, shlex, signal, subprocess, tempfile, uuid
from pathlib import Path

def cancellable_step(record,job,request):
    value=str(record.get('step',''))
    if str(record.get('job',''))!=str(job) or record.get('request')!=request or not value.isdigit():return None
    number=int(value)
    return f'{job}.{number}' if number>0 else None

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--config',type=Path,required=True);parser.add_argument('--argv',required=True);parser.add_argument('--cwd');parser.add_argument('--log',type=Path,required=True);parser.add_argument('--cpus',type=int)
    args=parser.parse_args();config=json.loads(args.config.read_text());argv=json.loads(args.argv)
    if not isinstance(argv,list) or not argv or not all(isinstance(a,str) for a in argv):parser.error('--argv must be a JSON string array')
    host=config['host'];job=str(int(config['job']));cpu_count=args.cpus or int(config.get('cpus',4))
    if cpu_count<1:parser.error('CPU count must be positive')
    cpus=str(cpu_count);root=config['work_directory'].rstrip('/')
    token=uuid.uuid4().hex;remote_request=f'{root}/runs/request-{token}.json'
    remote_worker=f'{root}/src/o2_remote_worker.py'
    data={'environment':root+'/environment.json','argv':argv,'cwd':args.cwd or f'{root}/runs/job-{token}'}
    args.log.parent.mkdir(parents=True,exist_ok=True)
    args.log.unlink(missing_ok=True)
    connection=['ssh','-o','BatchMode=yes',host]
    with tempfile.TemporaryDirectory(prefix='alice-o2-request-') as tmp:
        request=Path(tmp)/'request.json';request.write_text(json.dumps(data));request.chmod(0o600)
        subprocess.run(['scp','-q',str(Path(__file__).with_name('o2_remote_worker.py')),f'{host}:{remote_worker}'],check=True)
        subprocess.run(['scp','-q',str(request),f'{host}:{remote_request}'],check=True)
        command=['srun','--overlap','--jobid',job,'--ntasks=1','--cpus-per-task='+cpus,'apptainer','exec','--bind','/lustre:/lustre,/scratch:/scratch',config['image'],'/usr/bin/python3',remote_worker,remote_request]
        process=subprocess.Popen(connection+[shlex.join(command)],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        interrupted=False
        def terminate(signum,frame):
            nonlocal interrupted
            interrupted=True
            process.terminate()
        signal.signal(signal.SIGTERM,terminate);signal.signal(signal.SIGINT,terminate)
        stdout,stderr=process.communicate()
        if interrupted:
            # Only cancel the uniquely recorded new step. Never cancel the user-supplied .0 step.
            step_file=Path(tmp)/'step.json'
            if subprocess.run(['scp','-q',f'{host}:{remote_request[:-5]}.step.json',str(step_file)],capture_output=True).returncode==0:
                step=json.loads(step_file.read_text())
                identity=cancellable_step(step,job,Path(remote_request).name)
                if identity:subprocess.run(connection+[shlex.join(['scancel',identity])],capture_output=True)
        subprocess.run(['scp','-q',f'{host}:{remote_request[:-5]}.log',str(args.log)],capture_output=True)
        if not args.log.exists():args.log.write_text(stdout+'\n'+stderr)
        print(json.dumps({'returncode':process.returncode,'log':str(args.log),'remote_request':remote_request,'cancelled':interrupted}))
        if process.returncode:raise SystemExit(130 if interrupted else process.returncode)

if __name__=='__main__':main()
