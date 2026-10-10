"""Stream detector-wide views without pretending unassigned hits are collisions."""
from __future__ import annotations
import gzip,json,math,shutil,tempfile
from pathlib import Path
import ijson

def export_views(source: Path, output: Path) -> dict:
    source,output=Path(source),Path(output);output.parent.mkdir(parents=True,exist_ok=True)
    reports=[];identities=set();files={};metadata={};obj=None
    with tempfile.TemporaryDirectory(prefix='tf-views-',dir=output.parent) as temporary:
        temporary=Path(temporary);parts=[]
        def finish():
            for name,(stream,count,invalid,path) in files.items():
                stream.write('],"unrendered_spatial_count":'+str(invalid)+'}\n');stream.close()
                if count:
                    parts.append(path);reports.append(dict(detector=name,objects=count,invalid=invalid,run=metadata['run'],timeframe=metadata['timeframe'],orbit=metadata['orbit']))
            files.clear()
        try:
            with gzip.open(source,'rb') if source.suffix=='.gz' else source.open('rb') as input_:
                for prefix,event,value in ijson.parse(input_,multiple_values=True,use_float=True):
                    if prefix=='' and event=='start_map':metadata={}
                    elif prefix in ('schema_version','units','kind','run','timeframe','orbit'):metadata[prefix]=value
                    elif prefix=='spatial_objects' and event=='start_array':
                        if metadata.get('kind')!='timeframe_objects' or metadata.get('units')!='cm':raise ValueError('Expected native whole-TF spatial archive')
                        identity=tuple(metadata[k] for k in ('run','timeframe','orbit'))
                        if identity in identities:raise ValueError('Duplicate timeframe in spatial archive')
                        identities.add(identity)
                    elif prefix=='spatial_objects.item' and event=='start_map':obj={}
                    elif prefix.startswith('spatial_objects.item.'):
                        key=prefix.removeprefix('spatial_objects.item.')
                        if key=='position' and event=='start_array':obj['position']=[]
                        elif key=='position.item' and event in ('number','null'):obj['position'].append(value)
                        elif '.' not in key and event in ('string','number','boolean','null'):obj[key]=value
                    elif prefix=='spatial_objects.item' and event=='end_map':
                        detector=obj['detector']
                        if detector not in files:
                            path=temporary/f'{len(identities):08d}-{detector}.jsonl.gz';stream=gzip.open(path,'wt',compresslevel=1)
                            header=dict(schema_version=1,units='cm',kind='timeframe',id=':'.join(map(str,identity))+':'+detector+'-whole-TF',run=metadata['run'],timeframe=metadata['timeframe'],orbit=metadata['orbit'],data_detectors=[detector],source_archive=str(source.resolve()),association_basis='All detector measurements in this TF; not assigned to one primary vertex',warnings=['Whole-TF detector view, not a collision. Select clusters; fitted-track momentum/DCA/truth colouring is unavailable. Unassociated TPC native pad/time/charge remains in the archive because global Z needs a time hypothesis.'])
                            stream.write(json.dumps(header,separators=(',',':'))[:-1]+',"tracks":[],"clusters":[')
                            files[detector]=[stream,0,0,path]
                        state=files[detector];position=obj.get('position',[])
                        if len(position)!=3 or any(v is None or not math.isfinite(v) for v in position):state[2]+=1;continue
                        obj['id']=detector+':'+str(obj['index']);obj['kinematics']={}
                        obj.setdefault('measurement_kind','calibrated_tracklet' if detector=='TRD' else 'calorimeter_cell' if detector in ('PHS','EMC') else 'cluster')
                        if state[1]:state[0].write(',')
                        state[0].write(json.dumps(obj,allow_nan=False,separators=(',',':')));state[1]+=1
                    elif prefix=='spatial_objects' and event=='end_array':finish()
            if files:raise ValueError('Incomplete spatial archive')
            staging=output.with_name(output.name+'.part')
            with staging.open('wb') as target:
                for part in parts:
                    with part.open('rb') as member:shutil.copyfileobj(member,target)
            staging.replace(output)
        finally:
            for stream,*_ in files.values():stream.close()
    return dict(timeframes=len(identities),views=len(reports),records=reports)
