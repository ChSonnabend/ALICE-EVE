#!/usr/bin/env python3
"""Export sparse MC transport-reference polylines as renderer events (no fitted paths)."""
import argparse,csv,gzip,json,math
from collections import defaultdict
from pathlib import Path

DETECTORS={'ITS','TPC','TRD','TOF','HMP','PHS','CPV','EMC','MFT','MCH','MID','FT0','FV0','FDD','ZDC'}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--kine',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--selection',type=Path,help='MC CSV from select_tracks.py; highlights selected truth tracks')
    p.add_argument('--events',type=int,nargs='+',help='MC event indices; default all');p.add_argument('--mc-source-id',type=int,default=0)
    a=p.parse_args()
    if a.output.exists() and any(a.output.iterdir()):p.error('Use an empty output directory')
    import ROOT
    ROOT.gInterpreter.Declare('#include "DetectorsCommonDataFormats/DetID.h"')
    selected=defaultdict(set)
    if a.selection:
        with a.selection.open() as stream:
            for row in csv.DictReader(stream):
                if int(row['mc_source_id'])==a.mc_source_id and (a.events is None or int(row['mc_event_id']) in a.events):selected[int(row['mc_event_id'])].add(int(row['mc_track_id']))
    f=ROOT.TFile.Open(str(a.kine));tree=f.Get('o2sim') if f else None
    if not tree or not tree.GetBranch('TrackRefs'):raise ValueError('Kine file lacks saved TrackRefs; no MC paths can be exported')
    indices=a.events if a.events is not None else range(tree.GetEntries())
    if any(i<0 or i>=tree.GetEntries() for i in indices):raise ValueError('MC event index out of bounds')
    a.output.mkdir(parents=True,exist_ok=True);highlights={};report=[]
    for event_id in indices:
        tree.GetEntry(event_id);tracks=tree.MCTrack;bytrack=defaultdict(list)
        for ref in tree.TrackRefs:
            i=int(ref.getTrackID());det=int(ref.getDetectorId())
            if not 0<=i<len(tracks) or not 0<=det<int(ROOT.o2.detectors.DetID.nDetectors):continue
            name=str(ROOT.o2.detectors.DetID.getName(det))
            if name in DETECTORS:bytrack[i].append((float(ref.getLength()),name,[float(ref.X()),float(ref.Y()),float(ref.Z())]))
        h=getattr(tree,'MCEventHeader.');identity=f'MC:{a.mc_source_id}:{event_id}'
        event=dict(schema_version=1,units='cm',kind='collision',id=identity,track_representation='mc',
                   vertex=[float(h.GetX()),float(h.GetY()),float(h.GetZ())],tracks=[],clusters=[],
                   mc_source_id=a.mc_source_id,mc_event_id=event_id,
                   warnings=['MC truth polylines connect saved transport references; these are sparse samples, not reconstructed fits or exact continuous transport steps.'])
        drawable=set()
        for i,refs in bytrack.items():
            t=tracks[i];points=[[float(t.GetStartVertexCoordinatesX()),float(t.GetStartVertexCoordinatesY()),float(t.GetStartVertexCoordinatesZ())]]
            for _,_,point in sorted(refs,key=lambda r:r[0]):
                if point!=points[-1] and all(math.isfinite(x) for x in point):points.append(point)
            if len(points)<2:continue
            px,py,pz=float(t.GetStartVertexMomentumX()),float(t.GetStartVertexMomentumY()),float(t.GetStartVertexMomentumZ());pt=math.hypot(px,py)
            kin=dict(p=math.sqrt(pt*pt+pz*pz),pt=pt,phi=math.atan2(py,px))
            if pt:kin.update(eta=math.asinh(pz/pt),tan_lambda=pz/pt)
            event['tracks'].append(dict(id=f'mc:{a.mc_source_id}:{event_id}:{i}',source='MC',detectors=sorted({r[1] for r in refs}),points=points,
                kinematics=kin,features=dict(pdg=int(t.GetPdgCode()),mother_id=int(t.getMotherTrackId())),
                trajectory_basis='Sparse saved O2 TrackRefs in transport-length order, joined with straight segments',
                mc_truth=dict(source_id=a.mc_source_id,event_id=event_id,track_id=i)))
            drawable.add(i)
        highlights[identity]=[f'mc:{a.mc_source_id}:{event_id}:{i}' for i in sorted(selected[event_id]&drawable)]
        info=dict(mc_event_id=event_id,drawable_tracks=len(drawable),selected_drawable=len(selected[event_id]&drawable),
                  selected_without_path=len(selected[event_id]-drawable))
        report.append(info);event['mc_path_report']=info
        with gzip.open(a.output/f'event-{event_id:06d}.json.gz','wt') as out:json.dump(event,out)
        print(json.dumps(info),flush=True)
    # Sidecars outside the event directory, so folder loading only sees event payloads.
    a.output.with_name(a.output.name+'-highlights.json').write_text(json.dumps(highlights,indent=2))
    a.output.with_name(a.output.name+'-report.json').write_text(json.dumps(report,indent=2))
    f.Close()


if __name__=='__main__':main()
