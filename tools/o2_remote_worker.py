#!/usr/bin/env python3
"""Run inside the existing Slurm allocation's Apptainer environment."""
import json, os, subprocess, sys
from pathlib import Path

request=Path(sys.argv[1]);data=json.loads(request.read_text())
environment=json.loads(Path(data['environment']).read_text())
env=dict(os.environ,**environment)
if os.environ.get('SLURM_STEP_ID') in (None,'0','batch','extern'):
    raise RuntimeError('Refusing to run outside a new, isolated Slurm step')
record=request.with_suffix('.step.json')
record.write_text(json.dumps({'job':os.environ['SLURM_JOB_ID'],'step':os.environ['SLURM_STEP_ID'],'pid':os.getpid(),'request':request.name}))
record.chmod(0o600)
cwd=Path(data['cwd']);cwd.mkdir(parents=True,exist_ok=True)
with request.with_suffix('.log').open('w') as log:
    result=subprocess.run(data['argv'],cwd=cwd,env=env,stdout=log,stderr=subprocess.STDOUT)
raise SystemExit(result.returncode)
