#!/usr/bin/env python3
"""Export first-solid O2 design surfaces using ROOT tessellation (centimetres)."""
import argparse,json,gzip,hashlib
from pathlib import Path


def main():
    p=argparse.ArgumentParser();p.add_argument('--input',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--variant',choices=['ALICE2.1','ALICE3'],required=True);a=p.parse_args()
    import ROOT
    f=ROOT.TFile.Open(str(a.input));geo=f.Get('ccdb_object')
    if not geo:raise ValueError('Missing ccdb_object TGeoManager')
    geo.SetNsegments(64)
    shapes={};groups={};cache={}
    def matrix(m):
        r=m.GetRotationMatrix();t=m.GetTranslation()
        return [[float(r[3*i+j]) for j in range(3)]+[float(t[i])] for i in range(3)]+[[0,0,0,1]]
    def shape_data(shape):
        ptr=int(ROOT.addressof(shape))
        if ptr in cache:return cache[ptr]
        if shape.IsA().GetName()=='TGeoCompositeShape':
            b=shape.GetBoolNode()
            data={'kind':'boolean','operation':str(b.ClassName()),'left':shape_data(b.GetLeftShape()),'right':shape_data(b.GetRightShape()),'left_matrix':matrix(b.GetLeftMatrix()),'right_matrix':matrix(b.GetRightMatrix())}
        else:
            b=shape.GetBuffer3D(ROOT.TBuffer3D.kCore|ROOT.TBuffer3D.kRawSizes|ROOT.TBuffer3D.kRaw,True)
            if b.NbPnts()==0:raise ValueError('ROOT cannot tessellate '+str(shape.ClassName())+': '+shape.GetName())
            vertices=[[float(b.fPnts[3*i+j]) for j in range(3)] for i in range(b.NbPnts())]
            segments=[(int(b.fSegs[3*i+1]),int(b.fSegs[3*i+2])) for i in range(b.NbSegs())]
            faces=[];pos=0
            for i in range(b.NbPols()):
                n=int(b.fPols[pos+1]);edges=[segments[int(b.fPols[pos+2+j])] for j in range(n)];pos+=2+n
                chain=list(edges.pop(0))
                while edges:
                    for j,(u,v) in enumerate(edges):
                        if chain[-1] in (u,v):chain.append(v if u==chain[-1] else u);edges.pop(j);break
                    else:raise ValueError('Disconnected ROOT polygon')
                if chain[-1]==chain[0]:chain.pop()
                faces.append(chain)
            data={'kind':'mesh','vertices':vertices,'faces':faces,'root_class':str(shape.ClassName())}
        key=hashlib.sha256(json.dumps(data,sort_keys=True).encode()).hexdigest();shapes[key]=data;cache[ptr]=key;return key
    modules={'ALICE2.1':{'ITSV':'ITS','IT3':'ITS','ITS3':'ITS'},'ALICE3':{'TRKV':'TRK','FT3V':'FT3','FCTV':'FCT','IOTOFV':'TF3','RICHV':'RCH','ECALV':'ECL','MIDV':'MI3','FD3A':'FD3','FD3C':'FD3','magnet':'MAG3','Absorber':'ABS3','A3IP':'PIPE3'}}[a.variant]
    def emit(node,m,path,det):
        v=node.GetVolume();material=v.GetMaterial()
        if not v.IsAssembly() and material and material.GetDensity()>.05:
            key=shape_data(v.GetShape());group=groups.setdefault(det,{}).setdefault(key,{'name':str(v.GetName()),'matrices':[]})
            group['matrices'].append(matrix(m));return
        if v.GetNodes():
            for c in v.GetNodes():
                cm=ROOT.TGeoHMatrix(m);cm.Multiply(c.GetMatrix());emit(c,cm,path+'/'+c.GetName(),det)
    def locate(node,m,path):
        name=str(node.GetName()).rsplit('_',1)[0]
        if name in modules:emit(node,m,path,modules[name]);return
        if node.GetVolume().GetNodes():
            for c in node.GetVolume().GetNodes():
                cm=ROOT.TGeoHMatrix(m);cm.Multiply(c.GetMatrix());locate(c,cm,path+'/'+c.GetName())
    locate(geo.GetTopNode(),ROOT.TGeoHMatrix(),geo.GetTopNode().GetName())
    if not groups:raise ValueError('No selected design modules found')
    a.output.parent.mkdir(parents=True,exist_ok=True)
    data={'variant':a.variant,'units':'cm','basis':'Official installed O2 design geometry, first-solid material surfaces; nominal simulation geometry, not run alignment','source_sha256':hashlib.sha256(a.input.read_bytes()).hexdigest(),'shapes':shapes,'detectors':groups}
    with gzip.open(a.output,'wt') as stream:json.dump(data,stream,separators=(',',':'),allow_nan=False)
    print({d:sum(len(g['matrices']) for g in groups[d].values()) for d in groups},flush=True)

if __name__=='__main__':main()
