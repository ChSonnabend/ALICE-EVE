#!/usr/bin/env python3
"""Audit every collision against the independent O2 reference inventory."""
import argparse, collections, json, sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from alice_renderer.catalogue import Catalogue

class EventAudit:
  def __init__(self,path):
    inventory={}
    for line in path.read_text().splitlines():
        tf=json.loads(line)
        for vertex in tf['vertices']:
            inventory[(tf['run'],tf['tf_counter'],tf['orbit'],vertex['index'])]=vertex
    self.inventory=inventory
    self.report=dict(events=0,tracks=0,clusters=0,unrendered_tracks=0,unrendered_clusters=0,invalid_spatial_by_timeframe={},tracks_with_dca=0,detector_clusters=collections.Counter(),track_sources=collections.Counter(),missing_reference_sources=collections.Counter(),extra_reference_sources=collections.Counter())
  def observe(self,event):
        inventory=self.inventory;report=self.report
        key=(event['run'],event['timeframe'],event['orbit'],event['primary_vertex'])
        native=inventory.pop(key)
        expected={int(g)&((1<<30)-1) for g in native['matched_track_ids']}
        fitted=event['tracks']+event.get('unrendered_tracks',[])
        actual={int(t['input_gid']) for t in fitted}
        for g in expected-actual:report['missing_reference_sources'][str(g>>25)]+=1
        for g in actual-expected:report['extra_reference_sources'][str(g>>25)]+=1
        track_ids={t['id'] for t in fitted}
        tf=':'.join(map(str,key[:3]));invalid=event.get('timeframe_invalid_spatial_objects',0)
        if tf in report['invalid_spatial_by_timeframe'] and report['invalid_spatial_by_timeframe'][tf]!=invalid:raise ValueError('Inconsistent TF quality count')
        report['invalid_spatial_by_timeframe'][tf]=invalid
        for cluster in event.get('unrendered_clusters',[]):
            if cluster.get('track_id') is not None and cluster['track_id'] not in track_ids:raise ValueError('Dangling unrendered cluster association')
        report['unrendered_clusters']+=len(event.get('unrendered_clusters',[]))
        for cluster in event['clusters']:
            if cluster.get('track_id') is not None and cluster['track_id'] not in track_ids:raise ValueError('Dangling cluster association in '+event['id'])
            if not cluster.get('coordinate_basis'):raise ValueError('Missing cluster coordinate basis')
            report['detector_clusters'][cluster['detector']]+=1
        report['events']+=1;report['tracks']+=len(event['tracks']);report['clusters']+=len(event['clusters']);report['unrendered_tracks']+=len(event.get('unrendered_tracks',[]))
        report['tracks_with_dca']+=sum('dca' in t.get('kinematics',{}) for t in event['tracks'])
        report['track_sources'].update(t['source'] for t in event['tracks'])
        return event
  def finish(self):
    inventory=self.inventory;report=self.report
    if inventory:raise ValueError('Catalogue omits inventory vertices')
    if report['extra_reference_sources']:raise ValueError('Export contains track references outside independent inventory')
    track_sources={0,1,8,9,10,15,16,17,18,19,20,21,22,23,24,26}
    missing_tracks={k:v for k,v in report['missing_reference_sources'].items() if int(k) in track_sources}
    if missing_tracks:raise ValueError('PV track references were not preserved: '+str(missing_tracks))
    return report

def main():
    p=argparse.ArgumentParser();p.add_argument('catalogue',type=Path);p.add_argument('inventory',type=Path);p.add_argument('--output',type=Path,required=True);p.add_argument('--index',action='store_true');p.add_argument('--cache',type=Path,default=Path('cache'));a=p.parse_args()
    audit=EventAudit(a.inventory)
    if a.index:
        cat=Catalogue.build(a.catalogue,a.cache,convert=audit.observe,progress=lambda s:print(s,flush=True))
    else:cat=Catalogue(a.catalogue)
    if not audit.report['events']:
        for row in cat.rows():audit.observe(cat.load(row['ordinal']))
    report=audit.finish();report['catalogue']=str(cat.folder.resolve())
    a.output.write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2),flush=True)

if __name__=='__main__':main()
