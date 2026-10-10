#!/usr/bin/env python3
"""Export actual aligned TGeo surfaces with full parent transformations.

Reuses the MIT reference's primitive/CSG conversion. Default detail retains the
first solid material surface in each branch; interiors can be exported as leaves.
No radius-derived or schematic detector envelopes are generated.
"""
import argparse,hashlib,json,re,sys
from collections import defaultdict
from dataclasses import asdict
from pathlib import Path

PATTERNS={
 'L3':r'L3MO_', 'ITS':r'ITSV_|ITSServicesCarbon|Cage', 'TPC':r'TPC_M_',
 'TRD':r'BTRD\d+_', 'TOF':r'BTOF\d+_', 'HMP':r'Hmp\d+_|Hcradle_',
 'EMC':r'SMOD_|SM3rd_|DCSM_|DCEXT_', 'PHS':r'PHOS_|PHOH_',
 'CPV':r'CPV_', 'MFT':r'MFT_|MFTRail', 'MCH':r'SC(?:0[1-9]|10)[IO]_',
 'MID':r'SC1[1-4]_', 'FT0':r'FT0[AC]_', 'FV0':r'FV0_',
 'FDD':r'FD[AC]_', 'ZDC':r'ZNENV_|ZPENV_|ZEM_'}

def main():
    p=argparse.ArgumentParser();p.add_argument('--input',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--converter',type=Path,required=True);p.add_argument('--detail',choices=['surfaces','leaves'],default='surfaces');p.add_argument('--run',type=int,required=True)
    a=p.parse_args();sys.path.insert(0,str(a.converter.resolve()))
    import ROOT
    from ROOTshapes import convertTGeo2Param
    from ROOThelpers import from_tgeomatrix
    from root2json import validate_matrix
    f=ROOT.TFile.Open(str(a.input));geo=f.Get('ccdb_object') if f and not f.IsZombie() else None
    if not geo or geo.ClassName()!='TGeoManager':raise ValueError('Aligned TGeoManager is missing')
    groups=defaultdict(dict);roots=defaultdict(list);counts=defaultdict(int);volume_cache={}
    def emit(detector,node,matrix,path):
        volume=node.GetVolume();shape=volume.GetShape();material=volume.GetMaterial()
        solid=not volume.IsAssembly() and shape and material and material.GetDensity()>.05
        terminal=solid and (a.detail=='surfaces' or not volume.GetNdaughters())
        if terminal:
            validate_matrix(matrix,path)
            volume_id=int(ROOT.addressof(volume))
            if volume_id not in volume_cache:
                param=convertTGeo2Param(shape)
                if param is None:raise ValueError('Unsupported shape at '+path)
                serialized=asdict(param);serialized['_type']=shape.ClassName()
                key=hashlib.sha256(json.dumps(serialized,sort_keys=True,allow_nan=False).encode()).hexdigest()
                volume_cache[volume_id]=(key,serialized)
            key,serialized=volume_cache[volume_id]
            if key not in groups[detector]:
                groups[detector][key]=dict(shape=serialized,positions=[],name=volume.GetName())
            position=from_tgeomatrix(matrix)
            groups[detector][key]['positions'].append(dict(translation=asdict(position.tra),rotation=asdict(position.rot)))
            counts[detector]+=1
            return
        if volume.GetNodes():
            for child in volume.GetNodes():
                child_matrix=ROOT.TGeoHMatrix(matrix);child_matrix.Multiply(child.GetMatrix())
                emit(detector,child,child_matrix,path+'/'+child.GetName())
    def locate(node,path,depth):
        name=node.GetName()
        matches=[detector for detector,pattern in PATTERNS.items() if re.match(pattern,name)]
        if len(matches)>1:raise ValueError('Ambiguous geometry ownership: '+path)
        if matches:
            if not geo.cd(path):raise ValueError('Invalid aligned geometry path '+path)
            detector=matches[0];roots[detector].append(path)
            emit(detector,node,ROOT.TGeoHMatrix(geo.GetCurrentMatrix()),path);return
        if depth<6 and node.GetVolume().GetNodes():
            for child in node.GetVolume().GetNodes():locate(child,path+'/'+child.GetName(),depth+1)
    locate(geo.GetTopNode(),'/'+geo.GetTopNode().GetName(),0)
    missing=sorted(set(PATTERNS)-set(groups))
    if missing:raise ValueError('Detector geometry roots/surfaces not found: '+', '.join(missing))
    a.output.mkdir(parents=True,exist_ok=True)
    digest=hashlib.sha256(a.input.read_bytes()).hexdigest()
    manifest=dict(schema_version=1,run=a.run,source=str(a.input),source_sha256=digest,
                  coordinates='ALICE global XYZ',units='cm',detail=a.detail,detectors={})
    for detector,items in groups.items():
        data={f'{item["name"]}-{i}':dict(shape=item['shape'],positions=item['positions'],num_instances=len(item['positions'])) for i,item in enumerate(items.values())}
        path=a.output/(detector+'.json');path.write_text(json.dumps(data,separators=(',',':'),allow_nan=False))
        digest_json=hashlib.sha256()
        with path.open('rb') as stream:
            while block:=stream.read(4<<20):digest_json.update(block)
        manifest['detectors'][detector]=dict(json=path.name,json_sha256=digest_json.hexdigest(),roots=roots[detector],shapes=len(data),instances=counts[detector])
        print(f'{detector}: {len(data)} shapes, {counts[detector]} aligned surfaces',flush=True)
    (a.output/'geometry-manifest.json').write_text(json.dumps(manifest,indent=2))

if __name__=='__main__':main()
