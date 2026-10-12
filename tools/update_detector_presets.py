#!/usr/bin/env python3
"""Derive upgrade scenes from an ALICE2 recipe and generated design assets."""
import argparse,copy,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def main():
 p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);a=p.parse_args()
 base=json.loads(a.source.read_text());base['defaults']={}
 presets=ROOT/'src/alice_renderer/presets';(presets/'alice2.json').write_text(json.dumps(base,indent=2)+'\n')
 for variant,bundle in [('alice2-its3','alice2-its3'),('alice3','alice3')]:
  manifest=json.loads((ROOT/'geometry'/bundle/'design-manifest.json').read_text())
  data=copy.deepcopy(base);s=data['scene'];s['detector_setup']='ALICE2 + ITS3' if variant=='alice2-its3' else 'ALICE3'
  if variant=='alice2-its3':
   data['geometry']['ITS']={k:manifest['assets']['ITS'][k] for k in ['file','sha256']}
   s.setdefault('geometry_lods',{})['ITS']='full'
   for key in ['geometry_components','geometry_exclusions','geometry_inner_masks']:s.get(key,{}).pop('ITS',None)
  else:
   mapping={'TRK':'ITS','FT3':'MFT','FCT':'MFT','TF3':'TOF','RCH':'HMP','ECL':'EMC','MI3':'MID','FD3':'FDD','MAG3':'magnet','ABS3':'TPC','PIPE3':'TPC'}
   data['geometry']={name:{k:item[k] for k in ['file','sha256']} for name,item in manifest['assets'].items()}
   s['geometry']=list(data['geometry']);s['detectors']=[];s['magnet']=False
   for key in ['geometry_lods','geometry_components','geometry_exclusions','geometry_inner_masks','geometry_schematics','geometry_display']:s[key]={}
   s['geometry_lod']='full'
   for key in ['colors','colors_linear']:
    for name,source in mapping.items():s[key][name]=copy.deepcopy(s[key].get(source,s[key]['TPC']))
   for key in ['geometry_openings','geometry_opening_directions','geometry_opacities']:
    s[key]={name:copy.deepcopy(base['scene'].get(key,{}).get('ITS' if name=='TRK' else 'TPC',0 if key=='geometry_openings' else 1 if key=='geometry_opacities' else 0)) for name in mapping}
  (presets/(variant+'.json')).write_text(json.dumps(data,indent=2)+'\n')

if __name__=='__main__':main()
