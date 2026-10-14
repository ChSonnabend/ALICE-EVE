#!/usr/bin/env python3
"""Select SUEP ancestry in O2 Kine; never equate MC indices with reconstructed IDs."""
import argparse,csv,json
from collections import defaultdict,deque
from pathlib import Path


def select(tracks,hepmc_ids,parent_pdgs,policy='motherless'):
    """Track rows are (PDG, first mother, second mother); IDs are array indices."""
    n=len(tracks);members=set(hepmc_ids)
    if any(not isinstance(i,int) or not 0<=i<n for i in members):raise ValueError('HepMC membership index out of range')
    children=defaultdict(list)
    for i,(_,mother,second) in enumerate(tracks):
        for parent in set((mother,second)):
            if parent<-1 or parent>=n or parent==i:raise ValueError(f'Invalid ancestry at MC track {i}')
            if parent>=0:children[parent].append(i)
    roots=[i for i,(pdg,mother,_) in enumerate(tracks) if i in members and abs(pdg)!=2212
           and abs(pdg) in {abs(p) for p in parent_pdgs} and (policy=='pdg' or mother==-1)]
    selected=set(roots);queue=deque(roots)
    while queue:
        for child in children[queue.popleft()]:
            if child not in selected:selected.add(child);queue.append(child)
    # Transport descendants need not have generator-origin tags themselves.
    return roots,sorted(selected)


def burst_members(tracks,pion_pdgs,minimum=20):
    """Heuristic: many direct sibling pions with an explicitly selected PDG."""
    groups=defaultdict(set)
    allowed={abs(p) for p in pion_pdgs}
    for i,(pdg,mother,second) in enumerate(tracks):
        if any(parent < -1 or parent >= len(tracks) or parent == i for parent in (mother,second)):
            raise ValueError(f'Invalid ancestry at MC track {i}')
        if abs(pdg) not in allowed:continue
        for parent in set((mother,second)):
            if parent>=0:groups[parent].add(i)
    bursts=[dict(parent_id=p,parent_pdg=tracks[p][0],multiplicity=len(ids),pion_ids=sorted(ids))
            for p,ids in sorted(groups.items()) if len(ids)>=minimum]
    return set(i for b in bursts for i in b['pion_ids']),bursts


def map_reconstructed(selected,rows,event_map):
    """Join explicit MC labels using (source,event,track), keeping renderer IDs scoped."""
    output=defaultdict(set);matched=[]
    for row in rows:
        if str(row.get('fake','')).lower() in ('true','1'):continue
        key=tuple(int(row[k]) for k in ('mc_source_id','mc_event_id','mc_track_id'))
        if key not in selected:continue
        event=event_map.get(str(row['primary_vertex']))
        if event is None:raise ValueError('Missing renderer event ID for primary vertex '+str(row['primary_vertex']))
        output[event].add(str(row['renderer_track_id']));matched.append(dict(row,event_id=event))
    return {k:sorted(v) for k,v in output.items()},matched


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--kine',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--inspect',action='store_true',help='Audit event SubgenId and motherless PDGs without selecting')
    p.add_argument('--subgen-id',type=int,action='append',help='Allowed event-level SubgenId; repeat if needed')
    p.add_argument('--root-pdg',type=int,action='append',help='Explicit BSM parent PDG; never infer BSM from a numeric threshold')
    p.add_argument('--root-policy',choices=['motherless','pdg','burst'],default='motherless',help='pdg explicitly relaxes the motherID=-1 requirement')
    p.add_argument('--cocktail-source-id',type=int,help='Per-particle source bits 19..21 from hybridCode; distinct from embedding MC source ID')
    p.add_argument('--burst-min',type=int,default=20,help='Minimum same-parent pion multiplicity for explicit burst heuristic')
    p.add_argument('--hepmc-membership',type=Path,help='JSON: MC event index -> list of HepMC-origin MC track indices; required for mixed cocktails')
    p.add_argument('--pure-hepmc-events',action='store_true',help='Explicitly certify selected SubgenIds contain only HepMC, not mixed cocktails')
    p.add_argument('--mc-source-id',type=int,default=0,help='Source ID in the saved MC labels/context')
    p.add_argument('--reco-labels',type=Path,help='CSV from export_reco_labels.py')
    p.add_argument('--event-map',type=Path,help='JSON: PV index -> exact renderer event ID for this TF')
    a=p.parse_args()
    if not a.inspect and (not a.subgen_id or not a.root_pdg):p.error('Selection needs --subgen-id and --root-pdg; use --inspect first')
    if bool(a.reco_labels)!=bool(a.event_map):p.error('--reco-labels and --event-map must be supplied together')
    if a.output.exists() and any(a.output.iterdir()):p.error('Use a new/empty output directory')
    if a.cocktail_source_id is not None and not 0<=a.cocktail_source_id<=7:p.error('Cocktail source ID must be 0..7')
    if a.burst_min<2:p.error('--burst-min must be at least 2')
    import ROOT
    ROOT.gInterpreter.Declare("""
#include "SimulationDataFormat/MCEventHeader.h"
int suepSubId(const o2::dataformats::MCEventHeader& h) {
 bool valid=false;auto value=h.getInfo<int>("subgenerator_id",valid);
 if(!valid)throw std::runtime_error("Missing subgenerator_id");return value;
}
""")
    file=ROOT.TFile.Open(str(a.kine));tree=file.Get('o2sim') if file else None
    if not tree or not tree.GetBranch('MCTrack') or not tree.GetBranch('MCEventHeader.'):raise ValueError('Need o2sim with MCTrack and MCEventHeader')
    membership=json.loads(a.hepmc_membership.read_text()) if a.hepmc_membership else {}
    a.output.mkdir(parents=True,exist_ok=True)
    report=dict(input=str(a.kine.resolve()),policy=a.root_policy,origin_basis='inferred sibling-pion burst, not a generator-origin tag' if a.root_policy=='burst' else 'explicit generator provenance',burst_min=a.burst_min,cocktail_source_id=a.cocktail_source_id,events=[],selected_tracks=0,selected_roots=0)
    selected_keys=set()
    with (a.output/'mc_tracks.csv').open('w',newline='') as stream:
        writer=csv.writer(stream);writer.writerow(['mc_source_id','mc_event_id','mc_track_id','pdg','mother_id','second_mother_id','is_root','subgen_id'])
        for event in range(tree.GetEntries()):
            tree.GetEntry(event);subgen=int(ROOT.suepSubId(getattr(tree,'MCEventHeader.')))
            rows=[(int(t.GetPdgCode()),int(t.getMotherTrackId()),int(t.getSecondMotherTrackId())) for t in tree.MCTrack]
            motherless=defaultdict(int)
            for pdg,mother,_ in rows:
                if mother==-1:motherless[str(pdg)]+=1
            parents=defaultdict(int)
            for pdg,mother,_ in rows:
                if abs(pdg) in {abs(v) for v in (a.root_pdg or [])}:
                    parents[f'{pdg} <- {rows[mother][0] if mother>=0 else "no mother"}']+=1
            tagged=None
            if a.cocktail_source_id is not None:
                tagged={i for i,t in enumerate(tree.MCTrack) if ((int(t.getStatusCode().fullEncoding)&0xffffffff)>>29)==5 and ((int(t.getStatusCode().fullEncoding)>>19)&7)==a.cocktail_source_id}
            roots=[];ids=[];bursts=[]
            if not a.inspect and subgen in a.subgen_id:
                if a.root_policy=='burst':
                    members,bursts=burst_members(rows,a.root_pdg,a.burst_min)
                    roots,ids=select(rows,members if tagged is None else members&tagged,a.root_pdg,'pdg')
                else:
                    candidates,_=select(rows,range(len(rows)),a.root_pdg,a.root_policy)
                    if candidates and tagged is None and not a.pure_hepmc_events and str(event) not in membership:
                        raise ValueError(f'Missing HepMC membership for event {event}; SubgenId alone does not separate a mixed cocktail')
                    roots,ids=select(rows,tagged if tagged is not None else range(len(rows)) if a.pure_hepmc_events else membership.get(str(event),[]),a.root_pdg,a.root_policy)
            for i in ids:
                writer.writerow([a.mc_source_id,event,i,*rows[i],i in roots,subgen])
                if a.reco_labels:selected_keys.add((a.mc_source_id,event,i))
            report['events'].append(dict(mc_event_id=event,subgen_id=subgen,motherless_pdgs=dict(motherless),requested_parent_mothers=dict(parents),roots=roots,bursts=bursts,selected=len(ids)))
            report['selected_tracks']+=len(ids);report['selected_roots']+=len(roots)
            if event%10==0:print(f'Inspected {event+1}/{tree.GetEntries()} MC events',flush=True)
    file.Close()
    if a.reco_labels:
        with a.reco_labels.open() as stream:labels=list(csv.DictReader(stream))
        mapping,matched=map_reconstructed(selected_keys,labels,json.loads(a.event_map.read_text()))
        (a.output/'event-highlights.json').write_text(json.dumps(mapping,indent=2))
        with (a.output/'renderer_tracks.csv').open('w',newline='') as stream:
            writer=csv.writer(stream);writer.writerow(['event_id','renderer_track_id'])
            for event,ids in mapping.items():
                for track in ids:writer.writerow([event,track])
        report['matched_reconstructed_records']=len(matched)
    (a.output/'selection-report.json').write_text(json.dumps(report,indent=2))
    print(f"Selected {report['selected_roots']} roots and {report['selected_tracks']} MC tracks; MC IDs require a label join before renderer highlighting.")


if __name__=='__main__':main()
