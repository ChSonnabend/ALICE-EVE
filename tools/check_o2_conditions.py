#!/usr/bin/env python3
"""Prefetch and validate the conditions requested by the actual O2 graph.

No reconstruction starts here. The downloaded files retain CCDB metadata.
"""
import argparse,json,re,sys,time,math,shutil,urllib.parse
from pathlib import Path
from ccdb_http_cache import fetch_public_blob

def read_dump(path):
    raw=Path(path).read_text()
    for match in re.finditer(r'(?m)^\{',raw):
        try:item=json.JSONDecoder().raw_decode(raw[match.start():])[0]
        except json.JSONDecodeError:continue
        if isinstance(item,dict) and 'workflow' in item:return item
    raise ValueError('Invalid O2 workflow dump')

def main():
    p=argparse.ArgumentParser();p.add_argument('--workflow',type=Path,required=True);p.add_argument('--config',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();config=json.loads(a.config.read_text());workflow=read_dump(a.workflow)
    import ROOT
    ROOT.gInterpreter.Declare('#include "CommonConstants/LHCConstants.h"')
    orbit_ms=float(ROOT.o2.constants.lhc.LHCOrbitMUS)*.001
    requests={}
    for device in workflow['workflow']:
        for input_ in device.get('inputs',[]):
            meta={m['name']:m.get('defaultValue') for m in input_.get('metadata',[])}
            path=meta.get('ccdb-path')
            if path:requests.setdefault(path,{}).update(meta)
    a.output.mkdir(parents=True,exist_ok=True);report=[]
    timestamp=config['timestamp_ms']
    # Orbit reset establishes the detector time, independently of the dump's
    # file-write timestamp. The actual first-TF orbit is supplied in the profile.
    for ordinal,path in enumerate(sorted(requests,key=lambda s:(s!='CTP/Calib/OrbitReset',s))):
        meta={}
        dependence=int(requests[path].get('ccdb-run-dependent','0'))
        if dependence==1:meta['runNumber']=str(config['run'])
        query_timestamp=config['run'] if dependence==2 else timestamp
        for name,value in requests[path].items():
            if name.startswith('ccdb-metadata-'):meta[name.removeprefix('ccdb-metadata-')]=value
        url=config['condition_backend'].rstrip('/')+'/'+path+'/'+str(query_timestamp)+'/'
        url+=''.join(urllib.parse.quote(str(key)+'='+str(value),safe='=')+'/' for key,value in meta.items())
        headers=[];failure=None
        try:
            blob,headers=fetch_public_blob(url,a.output/'http-blobs')
            target=a.output/path/'snapshot.root';target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(blob,target)
            success=True
        except (OSError,ValueError,urllib.error.URLError) as error:success=False;failure=str(error)
        file=a.output/path/'snapshot.root';entry=dict(path=path,download=success,timestamp_ms=query_timestamp)
        if success and file.is_file():
            f=ROOT.TFile.Open(str(file),'READ')
            key=f.GetKey('ccdb_object') if f and not f.IsZombie() else None
            entry['valid_root_object']=bool(key)
            if key:entry['class_name']=key.GetClassName();entry['bytes']=file.stat().st_size
            if key and path=='CTP/Calib/OrbitReset' and config.get('first_orbit') is not None:
                reset=f.Get('ccdb_object');derived=math.ceil(reset[0]/1000+config['first_orbit']*orbit_ms)
                timestamp=derived if abs(derived-config['timestamp_ms'])<=config.get('timestamp_tolerance_ms',5000) else config['timestamp_ms']
            if f:f.Close()
            entry['headers']={name:value for name,value in headers if name.lower() in ('etag','valid-from','valid-until','created','runnumber')}
        else:entry['valid_root_object']=False
        if failure:entry['error']=failure
        report.append(entry);(a.output/'preflight.json').write_text(json.dumps(dict(complete=False,conditions=report),indent=2))
        print(f"Condition {ordinal+1}/{len(requests)}: {path}: {'OK' if entry['valid_root_object'] else 'MISSING'}",flush=True)
    missing=[entry['path'] for entry in report if not entry['valid_root_object']]
    result=dict(complete=not missing,run=config['run'],timestamp_ms=timestamp,conditions=report,missing=missing)
    (a.output/'preflight.json').write_text(json.dumps(result,indent=2))
    if missing:raise SystemExit('Required CCDB objects are missing: '+', '.join(missing))

if __name__=='__main__':main()
