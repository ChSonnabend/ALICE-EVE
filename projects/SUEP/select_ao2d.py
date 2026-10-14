#!/usr/bin/env python3
"""Create renderer-ready AO2D highlights from an explicitly requested pion-burst heuristic."""
import argparse,csv,json,re,sys
from collections import Counter,defaultdict
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'src'))
from alice_renderer.aod import tables,frames
from select_tracks import burst_members,select


def table(directory,stem):
    keys=[k for k in directory.keys(cycle=False,recursive=False) if re.fullmatch(stem+r'(?:_\d+)?',k)]
    if not keys:raise ValueError('Missing '+stem)
    return directory[max(keys,key=lambda k:int(k.rsplit('_',1)[1]) if k.rsplit('_',1)[-1].isdigit() else 0)]


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--input',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--pion-pdg',type=int,required=True)
    p.add_argument('--subgen-id',type=int,required=True);p.add_argument('--burst-min',type=int,default=20)
    a=p.parse_args()
    if a.burst_min<2:p.error('burst-min must be at least 2')
    if a.output.exists() and any(a.output.iterdir()):p.error('Use an empty output directory')
    import uproot,awkward as ak,numpy as np
    a.output.mkdir(parents=True,exist_ok=True);mapping=defaultdict(set);reports=[]
    with uproot.open(a.input) as f,(a.output/'renderer_tracks.csv').open('w',newline='') as out,(a.output/'mc_particles.csv').open('w',newline='') as mc:
        writer=csv.writer(out);writer.writerow(['event_id','renderer_track_id','dataframe','mc_particle_row','mc_collision'])
        mw=csv.writer(mc);mw.writerow(['dataframe','mc_particle_row','mc_collision','pdg','is_pion_root'])
        for df in frames(f):
            d=f[df];mt=table(d,'O2mcparticle');gen=table(d,'O2mccollision')['fGeneratorsID'].array(library='np')
            pdg=mt['fPdgCode'].array(library='np');mothers=mt['fIndexArray_Mothers'].array(library='ak');col=mt['fIndexMcCollisions'].array(library='np')
            if ak.any(ak.num(mothers)>2):raise ValueError('More than two MC mothers; unsupported ancestry')
            padded=ak.to_numpy(ak.fill_none(ak.pad_none(mothers,2,clip=True),-1))
            rows=[(int(pdg[i]),int(padded[i,0]),int(padded[i,1])) for i in range(len(pdg))]
            members,bursts=burst_members(rows,[a.pion_pdg],a.burst_min)
            members={i for i in members if 0<=col[i]<len(gen) and ((int(gen[col[i]])&0xffff)>>11)-1==a.subgen_id}
            roots,chosen=select(rows,members,[a.pion_pdg],'pdg');chosen=set(chosen);roots=set(roots)
            for i in sorted(chosen):mw.writerow([df,i,int(col[i]),int(pdg[i]),i in roots])
            tm=tables(d);collisions=d[tm['collisions']];bc=d[tm['bc']]['fRunNumber'].array(library='np')
            bcids=collisions['fIndexBCs'].array(library='np');counts=Counter();excluded=0
            for family,labelname in [('barrel','O2mctracklabel'),('mft','O2mcmfttracklabel'),('fwd','O2mcfwdtracklabel')]:
                if family not in tm:continue
                track=d[tm[family]];label=table(d,labelname)
                if label.num_entries!=track.num_entries:raise ValueError('Track/MC-label row counts differ for '+family)
                refs=label['fIndexMcParticles'].array(library='np');mask=label['fMcMask'].array(library='np');coll=track['fIndexCollisions'].array(library='np')
                for i,truth in enumerate(refs):
                    if int(truth) not in chosen:continue
                    if int(mask[i]) & (0xc000 if family=='barrel' else 0xc0):excluded+=1;continue
                    c=int(coll[i])
                    if c<0:continue
                    if c>=len(bcids) or not 0<=bcids[c]<len(bc):raise ValueError('Invalid collision/BC link')
                    event=f'AO2D:{int(bc[bcids[c]])}:{df}:{c}';identity=f'{df}:{family}:{i}'
                    mapping[event].add(identity);writer.writerow([event,identity,df,int(truth),int(col[truth])]);counts[family]+=1
            reports.append(dict(dataframe=df,subgen_id=a.subgen_id,pion_pdg=a.pion_pdg,burst_min=a.burst_min,
                bursts=[b for b in bursts if any(i in roots for i in b['pion_ids'])],roots=len(roots),selected_particles=len(chosen),
                reconstructed_tracks=dict(counts),fake_or_noise_omitted=excluded))
            print(df,len(roots),'pion roots;',sum(counts.values()),'reconstructed tracks',flush=True)
    (a.output/'event-highlights.json').write_text(json.dumps({k:sorted(v) for k,v in mapping.items()},indent=2))
    (a.output/'selection-report.json').write_text(json.dumps(dict(input=str(a.input.resolve()),
        basis='Heuristic: large same-parent pion burst within selected event SubgenId; not proven per-particle HepMC provenance',frames=reports),indent=2))


if __name__=='__main__':main()
