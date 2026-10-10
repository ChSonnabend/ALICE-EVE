#!/usr/bin/env python3
"""Run or dump the generated pipeline with its saved explicit environment."""
import argparse,json,os,re,subprocess,sys,time
from pathlib import Path

def validate_common_options(workflow):
    # DPL regenerates each child's graph. Different flow-control IPC values
    # change its SUMMARY outputs and therefore its input forwarding channels.
    devices=[item for item in workflow.get('metadata',[]) if not item['name'].startswith('internal-')]
    for name,default in (('session','default'),('shm-segment-id','0'),('timeframes-rate-limit-ipcid','-1')):
        values={}
        for device in devices:
            args=device.get('cmdLineArgs',[]);flag='--'+name
            value=args[args.index(flag)+1] if flag in args else default
            values.setdefault(value,[]).append(device['name'])
        if len(values)>1:raise ValueError('Inconsistent O2 '+name+' between processes: '+str(values))

def main():
    p=argparse.ArgumentParser();p.add_argument('directory',type=Path);p.add_argument('--dump',action='store_true');a=p.parse_args()
    directory=a.directory.resolve();env=dict(os.environ,**json.loads((directory/'workflow-environment.json').read_text()))
    command=(directory/'reconstruct.sh').read_text().split('set -euo pipefail\n',1)[1].strip()
    command+=' --dump' if a.dump else ' --run'
    proxy=None;proxy_log=None
    try:
        if not a.dump:
            report=directory/'preflight-ccdb/preflight.json'
            if not report.exists() or not json.loads(report.read_text()).get('complete'):raise RuntimeError('Reconstruction conditions have not passed preflight')
            port_file=directory/'ccdb-proxy-port.json';port_file.unlink(missing_ok=True)
            proxy_log=(directory/'ccdb-proxy.log').open('w')
            proxy=subprocess.Popen([sys.executable,str(Path(__file__).with_name('ccdb_http_cache.py')),'--backend',env['DPL_CONDITION_BACKEND'],'--cache',str(directory/'preflight-ccdb/http-blobs'),'--port-file',str(port_file)],stdout=proxy_log,stderr=subprocess.STDOUT)
            address=None
            for _ in range(100):
                try:address=json.loads(port_file.read_text())['url']
                except (FileNotFoundError,json.JSONDecodeError,KeyError):pass
                if address:break
                if proxy.poll() is not None:raise RuntimeError('CCDB cache backend failed to start')
                time.sleep(.1)
            if not address:raise RuntimeError('CCDB cache backend did not start')
            env['DPL_CONDITION_BACKEND']=address
            command=re.sub(r'(--configKeyValues ["\'])',lambda match:match[1]+'NameConf.mCCDBServer='+env['DPL_CONDITION_BACKEND']+';',command)
        with (directory/('workflow.json' if a.dump else 'reconstruction.log')).open('w') as stdout:
            with (directory/('dump.log' if a.dump else 'reconstruction-errors.log')).open('w') as stderr:
                result=subprocess.run(['bash','-o','pipefail','-c',command],cwd=directory,env=env,stdout=stdout,stderr=stderr)
    finally:
        if proxy:
            proxy.terminate()
            try:proxy.wait(timeout=5)
            except subprocess.TimeoutExpired:proxy.kill();proxy.wait()
        if proxy_log:proxy_log.close()
    if result.returncode:raise SystemExit(result.returncode)
    if a.dump:
        file=directory/'workflow.json';raw=file.read_text()
        for match in re.finditer(r'(?m)^\{',raw):
            try:workflow=json.JSONDecoder().raw_decode(raw[match.start():])[0]
            except json.JSONDecodeError:continue
            if isinstance(workflow,dict) and isinstance(workflow.get('workflow'),list):
                validate_common_options(workflow)
                (directory/'workflow.dump.log').write_text(raw[:match.start()]);file.write_text(json.dumps(workflow,indent=2));break
        else:raise RuntimeError('No valid workflow JSON found in O2 dump')
    print(directory/('workflow.json' if a.dump else 'reconstruction.log'))

if __name__=='__main__':main()
