#!/usr/bin/env python3
"""Build every detector listed by the strict aligned TGeo surface exporter."""
import argparse,os,hashlib,json,subprocess,sys
from pathlib import Path

def main():
    p=argparse.ArgumentParser();p.add_argument('--surfaces',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--blender',required=True)
    p.add_argument('--converter',type=Path,default=Path(os.environ.get('ALICE_GEOMETRY_CONVERTER',str(Path(__file__).resolve().parents[1]/'old/aliceBlender-master/root2blend'))))
    a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True)
    manifest=json.loads((a.surfaces/'geometry-manifest.json').read_text());assets={}
    for detector,expected in manifest['detectors'].items():
        source=a.surfaces/expected['json'];target=a.output/(detector+'.blend');qa=target.with_suffix('.qa.json')
        digest=hashlib.sha256(source.read_bytes()).hexdigest()
        expected['json_sha256']=digest
        old=json.loads(qa.read_text()) if target.exists() and qa.exists() else {}
        generator=Path(__file__).with_name('build_geometry_asset.py')
        if old.get('source_sha256')!=digest or old.get('generator_sha256')!=hashlib.sha256(generator.read_bytes()).hexdigest():
            with (a.output/(detector+'.build.log')).open('w') as log:
                subprocess.run([a.blender,'--background','--factory-startup','--python-exit-code','1',
                    '--python',str(Path(__file__).with_name('build_geometry_asset.py').resolve()),'--',
                    '--input',str(source.resolve()),'--output',str(target.resolve()),'--detector',detector,
                    '--converter',str(a.converter.resolve())],stdout=log,stderr=subprocess.STDOUT,check=True)
        report=json.loads(qa.read_text())
        if any(report[k]!=expected[k] for k in ('shapes','instances')):raise ValueError('Geometry coverage differs: '+detector)
        assets[detector]=str(target.resolve());print(detector,report['shapes'],report['instances'],flush=True)
    manifest['assets']=assets;manifest['asset_units']='m'
    (a.output/'geometry-manifest.json').write_text(json.dumps(manifest,indent=2))
    (a.output/'render-settings.json').write_text(json.dumps(dict(geometry_assets=assets,geometry_units='m'),indent=2))

if __name__=='__main__':main()
