#!/usr/bin/env python3
"""Build official installed O2 upgrade design geometries and Blender assets."""
import argparse,json,os,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def main():
 p=argparse.ArgumentParser();p.add_argument('--setup',choices=['ALICE2.1','ALICE3'],required=True);p.add_argument('--work',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--blender',required=True);a=p.parse_args()
 if not os.environ.get('O2_ROOT'):p.error('Activate the O2 suite first')
 work=a.work.resolve()
 if work.exists() and any(work.iterdir()):p.error('Use a fresh work directory')
 work.mkdir(parents=True,exist_ok=True)
 command=['o2-sim','--detectorList',a.setup,'-n','0','-e','TGeant3','-o','o2sim']
 with (work/'simulation.log').open('w') as log:subprocess.run(command,cwd=work,stdout=log,stderr=subprocess.STDOUT,check=True)
 surfaces=work/'surfaces.json.gz'
 subprocess.run([sys.executable,str(ROOT/'tools/export_o2_variant_geometry.py'),'--variant',a.setup,'--input',str(work/'o2sim_geometry.root'),'--output',str(surfaces)],check=True)
 subprocess.run([a.blender,'--background','--factory-startup','--python-exit-code','1','--python',str(ROOT/'tools/build_o2_variant_assets.py'),'--','--input',str(surfaces),'--output',str(a.output.resolve())],check=True)
 (a.output/'generation.json').write_text(json.dumps({'command':command,'o2_root':os.environ['O2_ROOT'],'basis':'Nominal installed O2 simulation design; not aligned real-data geometry'},indent=2))
 print(a.output)
if __name__=='__main__':main()
