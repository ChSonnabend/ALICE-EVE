#!/usr/bin/env python3
"""Reuse the reference MIT-licensed TGeo converter without editing its sources."""
import argparse,os, hashlib, json, subprocess, sys
from pathlib import Path

def main():
    parser=argparse.ArgumentParser(description='Export one aligned ALICE detector subtree as a Blender geometry asset')
    parser.add_argument('--input',type=Path,required=True,help='Run-appropriate aligned TGeo ROOT file')
    parser.add_argument('--detector',required=True)
    parser.add_argument('--node-path',required=True,help='Full TGeo detector subtree path')
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--root-python',default=sys.executable,help='Python with working PyROOT and O2 geometry dictionaries')
    parser.add_argument('--blender',required=True)
    parser.add_argument('--converter',type=Path,default=Path(os.environ.get('ALICE_GEOMETRY_CONVERTER',str(Path(__file__).resolve().parents[1]/'old/aliceBlender-master/root2blend'))))
    args=parser.parse_args()
    if not args.input.is_file():parser.error('Geometry ROOT file does not exist')
    for file in ('root2json.py','json2blender.py','LICENSE'):
        if not (args.converter/file).is_file():parser.error(f'Reference converter is missing {file}')
    check=subprocess.run([args.root_python,'-c','import ROOT; print(ROOT.gROOT.GetVersion())'],capture_output=True,text=True)
    if check.returncode:parser.error('PyROOT prerequisite is missing in --root-python: '+check.stderr[-1000:])
    args.output.mkdir(parents=True,exist_ok=True)
    geometry=args.output/'geometry.json';blend=args.output/(args.detector+'.blend')
    commands=[
        [args.root_python,str((args.converter/'root2json.py').resolve()),'-i',str(args.input.resolve()),'-o',str(geometry.resolve()),'-p',args.node_path,'--log','INFO'],
        [args.blender,'--background','--factory-startup','--python-exit-code','1','--python',str((args.converter/'json2blender.py').resolve()),'--','-i',str(geometry.resolve()),'-o',str(blend.resolve()),'-n',args.detector,'--log','INFO']]
    for command in commands:subprocess.run(command,check=True,cwd=args.output)
    digest=hashlib.sha256()
    with args.input.open('rb') as source:
        while chunk:=source.read(1024*1024):digest.update(chunk)
    provenance={'detector':args.detector,'input':str(args.input.resolve()),'input_sha256':digest.hexdigest(),'node_path':args.node_path,'asset':str(blend.resolve()),'units':'m','axes':'Verify converter output remains ALICE global XYZ, including subtree parent transforms','converter':str(args.converter.resolve()),'license':'MIT — Felix Schlepper (2025)'}
    (args.output/'provenance.json').write_text(json.dumps(provenance,indent=2))
    print(blend)

if __name__=='__main__':main()
