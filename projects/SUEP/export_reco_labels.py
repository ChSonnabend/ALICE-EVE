#!/usr/bin/env python3
"""Export PV-associated reconstructed IDs and their MC labels for one O2 TF."""
import argparse,csv,json
from collections import Counter
from pathlib import Path

READERS={
 'ITS':('o2trac_its.root','o2sim','ITSTrackMCTruth'),
 'TPC':('tpctracks.root','tpcrec','TPCTracksMCTruth'),
 'ITS-TPC':('o2match_itstpc.root','matchTPCITS','MatchMCTruth'),
 'ITSAB':('o2match_itstpc.root','matchTPCITS','MatchABMCTruth'),
 'MFT':('mfttracks.root','o2sim','MFTTrackMCTruth'),
 'TPC-TRD':('trdmatches_tpc.root','tracksTRD','labels'),
 'ITS-TPC-TRD':('trdmatches_itstpc.root','tracksTRD','labels'),
 'TPC-TOF':('o2match_tof_tpc.root','matchTOF','MatchTOFMCTruth'),
 'ITS-TPC-TOF':('o2match_tof_itstpc.root','matchTOF','MatchTOFMCTruth'),
 'TPC-TRD-TOF':('o2match_tof_tpctrd.root','matchTOF','MatchTOFMCTruth'),
 'ITS-TPC-TRD-TOF':('o2match_tof_itstpctrd.root','matchTOF','MatchTOFMCTruth'),
}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--input',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--entry',type=int,default=0)
    p.add_argument('--readers',type=Path,help='Optional JSON source -> [ROOT filename, tree, label branch] overrides')
    a=p.parse_args()
    if a.output.exists():p.error('Output already exists')
    import ROOT
    readers=dict(READERS)
    if a.readers:readers.update(json.loads(a.readers.read_text()))
    handles=[];trees={};missing=Counter();counts=Counter()
    pvfile=ROOT.TFile.Open(str(a.input/'o2_primary_vertex.root'));handles.append(pvfile)
    pv=pvfile.Get('o2sim')
    if a.entry<0 or a.entry>=pv.GetEntries():raise ValueError('PV entry out of range')
    pv.GetEntry(a.entry)
    a.output.parent.mkdir(parents=True,exist_ok=True)
    with a.output.open('w',newline='') as stream:
        writer=csv.writer(stream);writer.writerow(['primary_vertex','renderer_track_id','reco_source','mc_source_id','mc_event_id','mc_track_id','fake'])
        for vertex in range(len(pv.PrimaryVertex)):
            ref=pv.PV2TrackRefs[vertex]
            for index in range(ref.getFirstEntry(),ref.getFirstEntry()+ref.getEntries()):
                gid=pv.PVTrackIndices[index];source=str(gid.getSourceName())
                if source not in readers:missing[source]+=1;continue
                if source not in trees:
                    name,tree,branch=readers[source];path=a.input/name
                    f=ROOT.TFile.Open(str(path)) if path.is_file() else None
                    t=f.Get(tree) if f and not f.IsZombie() else None
                    if f:handles.append(f)
                    if not t or not t.GetBranch(branch) or a.entry>=t.GetEntries():trees[source]=None
                    else:t.GetEntry(a.entry);trees[source]=(t,branch)
                if trees[source] is None:missing[source]+=1;continue
                t,branch=trees[source];labels=getattr(t,branch);i=int(gid.getIndex())
                if i>=len(labels):raise ValueError(f'{source} MC label index {i} out of bounds')
                label=labels[i]
                if not label.isValid():counts['invalid_labels']+=1;continue
                if label.isFake():counts['fake_labels']+=1;continue
                writer.writerow([vertex,int(gid.getRawWOFlags()),source,label.getSourceID(),label.getEventID(),label.getTrackID(),False])
                counts[source]+=1
    for f in handles:
        if f:f.Close()
    report=dict(input=str(a.input.resolve()),entry=a.entry,mapped=dict(counts),unmapped_sources=dict(missing),
                note='PV-associated fitted IDs only; absent/fake labels are omitted, never guessed. MC source IDs must match collisioncontext.root.')
    a.output.with_suffix('.report.json').write_text(json.dumps(report,indent=2))
    print(json.dumps(report,indent=2))


if __name__=='__main__':main()
