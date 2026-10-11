"""Lazy AO2D collision import. No ROOT/O2 installation is required to read tables.

Display curves are explicitly fitted-state projections, not measured clusters.
Barrel/MFT curves use a supplied, provenance-labelled constant solenoid Bz;
MCH/MID use a labelled linear projection, never a fictitious solenoid helix.
"""
from __future__ import annotations
import gzip,json,math,os,re,shutil,sqlite3,tempfile
from pathlib import Path
import numpy as np
import uproot
from .catalogue import fingerprint
from .model import validate_event,capabilities

VERSION=2
TABLE_PATTERNS={
 'collisions':r'O2collision(?:_\d+)?', 'bc':r'O2bc(?:_\d+)?',
 'barrel':r'O2track_iu(?:_\d+)?', 'barrel_pv':r'O2track(?:_\d+)?',
 'extra':r'O2trackextra(?:_\d+)?', 'cov':r'O2trackcov_iu(?:_\d+)?',
 'cov_pv':r'O2trackcov(?:_\d+)?', 'fwd':r'O2fwdtrack(?:_\d+)?',
 'mft':r'O2mfttrack(?:_\d+)?', 'fwd_cov':r'O2fwdtrackcov(?:_\d+)?',
 'mft_cov':r'O2mfttrackcov(?:_\d+)?'}
CORE=('eta','tan_lambda','phi','p','pt','x','y','z','matching')

def tables(directory):
    keys=directory.keys(cycle=False,recursive=False);result={}
    for kind,pattern in TABLE_PATTERNS.items():
        matches=[k for k in keys if re.fullmatch(pattern,k)]
        if matches:result[kind]=max(matches,key=lambda k:int(k.rsplit('_',1)[1]) if k.rsplit('_',1)[-1].isdigit() else 0)
    if 'barrel' not in result and 'barrel_pv' in result:
        result['barrel']=result['barrel_pv']
        if 'cov_pv' in result:result['cov']=result['cov_pv']
    return result

def frames(file):
    return [k for k in file.keys(cycle=False,recursive=False) if k.startswith('DF_') and hasattr(file[k],'keys')]

def inspect(path):
    with uproot.open(path,object_cache=None,array_cache=None) as file:
        result=[]
        for name in frames(file):
            mapping=tables(file[name])
            if 'collisions' not in mapping:continue
            result.append({'dataframe':name,'collisions':int(file[name][mapping['collisions']].num_entries),
                           'tracks':sum(int(file[name][mapping[k]].num_entries) for k in ('barrel','fwd','mft') if k in mapping),'tables':mapping})
        if not result:raise ValueError('No AO2D collision tables found')
        return result

def feature_name(branch):
    name=branch[1:] if branch.startswith('f') else branch
    return re.sub(r'([a-z0-9])([A-Z])',r'\1_\2',re.sub(r'([A-Z]+)([A-Z][a-z])',r'\1_\2',name)).lower()

def detector_lists(extra,count):
    """O2 AnalysisDataModel DetectorMap expressions, not TrackType guesses."""
    sizes=extra.get('fITSClusterSizes',extra.get('fITSClusterMap',np.zeros(count)))
    tpc=extra.get('fTPCNClsFindable',np.zeros(count))
    trd=extra.get('fTRDPattern',np.zeros(count))
    tof=(extra.get('fTOFChi2',np.full(count,-1))>=0)&(extra.get('fTOFExpMom',np.zeros(count))>0)
    return [(name,mask) for name,mask in [('ITS',sizes>0),('TPC',tpc>0),('TRD',trd>0),('TOF',tof)]]

def forward_detectors(data,count):
    # O2 ForwardTrackType: GlobalMuon=0/1, GlobalForward=2,
    # MuonStandalone=3, MCHStandalone=4. MFT-only has its own table.
    types=data.get('fTrackType',np.full(count,-1))
    return [('MFT',(data.get('fIndexMFTTracks',np.full(count,-1))>=0)|np.isin(types,[0,1,2])),
            ('MCH',(data.get('fMCHBitMap',np.zeros(count))!=0)|np.isin(types,[0,1,2,3,4])),
            ('MID',(data.get('fMIDBitMap',np.zeros(count))!=0)|np.isin(types,[0,1,3]))]

def options_for(path,options=None):
    options=dict(options or {});conditions=options.pop('conditions',None)
    if options.get('bz_kG') is None:options.pop('bz_kG',None)
    candidate=Path(conditions) if conditions else Path(str(path)+'.renderer.json')
    if candidate.is_file():
        options['fields']=json.loads(candidate.read_text()).get('fields',{})
    options.setdefault('fields',{});return options

def field_for(run,options):
    if options.get('bz_kG') is not None:
        bz=float(options['bz_kG']);basis='Explicit user-provided constant solenoid Bz'
    else:
        field=options.get('fields',{}).get(str(run),{})
        if 'bz_kG' not in field:raise ValueError(f'AO2D run {run}: magnetic-field conditions are missing. Supply its .renderer.json conditions file or an explicit signed AO2D Bz in kG in Setup; reload the input. No render was started.')
        bz=float(field['bz_kG']);basis=field.get('basis','Supplied AO2D field conditions')
    if not math.isfinite(bz) or abs(bz)>100:raise ValueError('Invalid AO2D Bz in kG')
    return bz,basis

def require_columns(tree,names):
    missing=set(names)-set(tree.keys())
    if missing:raise ValueError(tree.object_path+': unsupported/incomplete AO2D table; missing '+', '.join(sorted(missing)))

def arrays(tree,branches=None,**kwargs):
    return tree.arrays(filter_name=branches,library='np',**kwargs)

def build_catalogue(path,cache,*,options=None,progress=lambda s:None,cancelled=lambda:False):
    from .catalogue import Catalogue
    path,cache=Path(path),Path(cache);options=options_for(path,options);source_key=fingerprint(path)
    import hashlib
    key=hashlib.sha256((source_key+json.dumps(options,sort_keys=True)+str(VERSION)).encode()).hexdigest()[:24]
    destination=cache/key
    if (destination/'catalogue.sqlite').exists():return Catalogue(destination)
    cache.mkdir(parents=True,exist_ok=True);staging=Path(tempfile.mkdtemp(prefix='aod-index-',dir=cache));db=None
    try:
        db=sqlite3.connect(staging/'catalogue.sqlite')
        db.execute('CREATE TABLE events (ordinal INTEGER PRIMARY KEY,event_id TEXT,kind TEXT,run TEXT,timeframe TEXT,ntracks INTEGER,nclusters INTEGER,detectors TEXT,track_fields TEXT,cluster_fields TEXT,filename TEXT,contributors INTEGER)')
        db.execute('CREATE TABLE metadata (key TEXT PRIMARY KEY,value TEXT)')
        db.execute('CREATE TABLE aod_events (ordinal INTEGER PRIMARY KEY,dataframe TEXT,collision INTEGER)')
        ordinal=0;orphans=0
        with uproot.open(path,object_cache=None,array_cache=None) as file:
            names=frames(file)
            for n,name in enumerate(names):
                if cancelled():raise InterruptedError('AO2D indexing cancelled')
                directory=file[name];mapping=tables(directory)
                if 'collisions' not in mapping:raise ValueError(name+': collision table missing')
                require_columns(directory[mapping['collisions']],('fPosX','fPosY','fPosZ'))
                col=arrays(directory[mapping['collisions']]);count=len(col['fPosX'])
                bc=arrays(directory[mapping['bc']],['fRunNumber']) if 'bc' in mapping else {}
                totals=np.zeros(count,dtype=np.int64);detcounts={d:np.zeros(count,dtype=np.int64) for d in ('ITS','TPC','TRD','TOF','MFT','MCH','MID')};features=set()
                for family in ('barrel','fwd','mft'):
                    if family not in mapping:continue
                    tree=directory[mapping[family]]
                    require_columns(tree,('fIndexCollisions','fX','fY','fZ','fTgl','fSigned1Pt',*(['fAlpha','fSnp'] if family=='barrel' else ['fPhi'])))
                    ids=tree['fIndexCollisions'].array(library='np')
                    valid=ids>=0;orphans+=int((~valid).sum())
                    if valid.any() and ids[valid].max()>=count:raise ValueError(f'{name}/{mapping[family]}: collision index exceeds table size')
                    totals+=np.bincount(ids[valid],minlength=count)
                    features.update(feature_name(b) for b in tree.keys() if not b.startswith('fIndex'))
                    covkey='cov' if family=='barrel' else family+'_cov'
                    if covkey in mapping:features.update(feature_name(b) for b in directory[mapping[covkey]].keys() if not b.startswith('fIndex'))
                    features.add('charge')
                    if family=='barrel':
                        if 'extra' not in mapping:raise ValueError(name+': TrackExtra is required to identify contributing detectors')
                        extra_tree=directory[mapping['extra']]
                        require_columns(extra_tree,('fTPCNClsFindable',))
                        if not {'fITSClusterSizes','fITSClusterMap'}&set(extra_tree.keys()):raise ValueError(name+': unsupported TrackExtra ITS cluster encoding')
                        if extra_tree.num_entries!=tree.num_entries:raise ValueError(name+': track/extra table row counts differ')
                        extra=arrays(extra_tree,['fITSClusterSizes','fITSClusterMap','fTPCNClsFindable','fTRDPattern','fTOFChi2','fTOFExpMom'])
                        for detector,mask in detector_lists(extra,len(ids)):detcounts[detector]+=np.bincount(ids[valid&mask],minlength=count)
                        features.update(feature_name(b) for b in extra_tree.keys());features.update(('its_nclusters','tpc_nclusters','tpc_crossed_rows','pid_for_tracking','pv_contributor','dca_xy','dca_z'))
                    elif family=='mft':detcounts['MFT']+=np.bincount(ids[valid],minlength=count)
                    else:
                        extra=arrays(tree,['fMCHBitMap','fMIDBitMap','fIndexMFTTracks','fTrackType'])
                        for detector,mask in forward_detectors(extra,len(ids)):detcounts[detector]+=np.bincount(ids[valid&mask],minlength=count)
                fields=['solid',*CORE,'dca',*sorted('feature:'+f for f in features)]
                for i in range(count):
                    index=int(col.get('fIndexBCs',np.full(count,-1))[i]);run=int(bc['fRunNumber'][index]) if 'fRunNumber' in bc and 0<=index<len(bc['fRunNumber']) else 0
                    event_id=f'AO2D:{run}:{name}:{i}';filename=f'event-{ordinal:08d}.json.gz'
                    db.execute('INSERT INTO events VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',(ordinal,event_id,'collision',str(run),name,int(totals[i]),0,json.dumps([d for d,a in detcounts.items() if a[i]]),json.dumps(fields),json.dumps(['solid']),filename,int(col['fNumContrib'][i]) if 'fNumContrib' in col else None))
                    db.execute('INSERT INTO aod_events VALUES (?,?,?)',(ordinal,name,i));ordinal+=1
                progress(f'AO2D frame {n+1}/{len(names)}: {ordinal} collisions indexed; trajectories load on selection')
        if not ordinal:raise ValueError('AO2D contains no reconstructed collisions; unassociated tracks are not collision events')
        if fingerprint(path)!=source_key:raise ValueError('AO2D changed during indexing; wait for copying to finish')
        for k,v in {'source':str(path.resolve()),'source_fingerprint':source_key,'aod_options':json.dumps(options),'aod_version':str(VERSION),'unassociated_track_records':str(orphans)}.items():db.execute('INSERT INTO metadata VALUES (?,?)',(k,v))
        db.commit();db.close();db=None
        if destination.exists():shutil.rmtree(staging)
        else:staging.rename(destination)
        return Catalogue(destination)
    except BaseException:
        if db:db.close()
        shutil.rmtree(staging,ignore_errors=True);raise

def helix_state(values):
    x,y,z,alpha,snp,tgl,qpt=(float(values[k]) for k in ('fX','fY','fZ','fAlpha','fSnp','fTgl','fSigned1Pt'))
    if not all(math.isfinite(v) for v in (x,y,z,alpha,snp,tgl,qpt)) or abs(snp)>1:raise ValueError('Invalid AO2D barrel fit parameters')
    return [x*math.cos(alpha)-y*math.sin(alpha),x*math.sin(alpha)+y*math.cos(alpha),z],alpha+math.asin(snp),tgl,qpt

def at_arc(origin,phi,tgl,k,s):
    if abs(k)<1.e-12:return [origin[0]+s*math.cos(phi),origin[1]+s*math.sin(phi),origin[2]+s*tgl]
    return [origin[0]+(math.sin(phi+k*s)-math.sin(phi))/k,origin[1]-(math.cos(phi+k*s)-math.cos(phi))/k,origin[2]+s*tgl]

def projected_points(origin,phi,tgl,qpt,bz,*,family):
    k=-.000299792458*bz*qpt if family!='fwd' else 0.
    limit=min(700.,math.tau/abs(k)) if k else 700.
    if family=='mft':limit=min(limit,150./max(abs(tgl),.01))
    if family=='fwd':limit=min(limit,1800./max(abs(tgl),.01))
    step=min(3.,.04/max(abs(k),1.e-9));s=0.;points=[list(origin)]
    while s<limit:
        s=min(limit,s+step);point=at_arc(origin,phi,tgl,k,s);points.append(point)
        if math.hypot(point[0],point[1])>450 or abs(point[2])>(1800 if family=='fwd' else 600):break
    return points

def dca_to_vertex(origin,phi,tgl,qpt,bz,vertex):
    k=-.000299792458*bz*qpt
    if abs(k)<1.e-12:s=(vertex[0]-origin[0])*math.cos(phi)+(vertex[1]-origin[1])*math.sin(phi)
    else:
        cx=origin[0]-math.sin(phi)/k;cy=origin[1]+math.cos(phi)/k
        theta=math.atan2(k*(vertex[0]-cx),-k*(vertex[1]-cy));delta=(theta-phi+math.pi)%math.tau-math.pi;s=delta/k
    p=at_arc(origin,phi,tgl,k,s);dx,dy,dz=p[0]-vertex[0],p[1]-vertex[1],p[2]-vertex[2]
    return math.hypot(math.hypot(dx,dy),dz),math.hypot(dx,dy),dz

def row_features(row):
    result={}
    for key,value in row.items():
        if key.startswith('fIndex'):continue
        if np.isscalar(value):
            v=float(value)
            if math.isfinite(v) and (v>-990 or key in ('fX','fY','fZ','fCollisionTime','fTrackTime')):result[feature_name(key)]=int(value) if isinstance(value,(int,np.integer)) else v
    return result

def selected_rows(tree,collision):
    ids=tree['fIndexCollisions'].array(library='np');indices=np.flatnonzero(ids==collision)
    return indices

def rows_at(tree,indices):
    """Read parameters from one bounded data frame, then retain selected rows."""
    if not len(indices):return {}
    # ROOT baskets are read only once through a temporary array cache. A few
    # scattered tracks still use bounded parameter memory at the dataframe level.
    all_arrays=arrays(tree)
    return {key:values[indices] for key,values in all_arrays.items()}

def covariance_rows(directory,mapping,family,indices,track_count):
    key='cov' if family=='barrel' else family+'_cov'
    if key not in mapping:return [{} for _ in indices]
    tree=directory[mapping[key]]
    if family=='mft' and 'fIndexMFTTracks' in tree.keys():
        data=arrays(tree);lookup={}
        for i,track in enumerate(data['fIndexMFTTracks']):
            track=int(track)
            if not 0<=track<track_count:raise ValueError('Invalid MFT covariance association')
            if track in lookup:
                previous=lookup[track]
                if not all(np.array_equal(value[i],value[previous],equal_nan=True) for value in data.values()):raise ValueError('Conflicting MFT covariance rows for the same track')
            else:lookup[track]=i
        return [{k:v[lookup[int(index)]] for k,v in data.items()} if int(index) in lookup else {} for index in indices]
    if tree.num_entries!=track_count:raise ValueError(f'{family}: covariance and track row counts differ')
    data=rows_at(tree,indices);return [{k:v[j] for k,v in data.items()} for j in range(len(indices))]

def materialize(catalogue,ordinal,*,progress=lambda s:None,cancelled=lambda:False):
    with sqlite3.connect(catalogue.db) as db:
        db.row_factory=sqlite3.Row;record=dict(db.execute('SELECT * FROM events WHERE ordinal=?',(ordinal,)).fetchone());ref=db.execute('SELECT dataframe,collision FROM aod_events WHERE ordinal=?',(ordinal,)).fetchone();meta=dict(db.execute('SELECT key,value FROM metadata'))
    source=Path(meta['source'])
    if fingerprint(source)!=meta['source_fingerprint']:raise ValueError('AO2D changed; reload it before generating tracks')
    options=json.loads(meta['aod_options']);bz,basis=field_for(record['run'],options)
    target=catalogue.folder/record['filename']
    if target.is_file():return target
    event={'schema_version':1,'units':'cm','id':record['event_id'],'kind':'collision','run':int(record['run']),'aod_dataframe':ref[0],'primary_vertex_index':int(ref[1]),'contributors':record['contributors'],'tracks':[],'clusters':[],
           'source_format':'AO2D','source':str(source),'trajectory_conditions':{'bz_kG':bz,'basis':basis},'warnings':['AO2D does not contain the measured track-attached space-point arrays; clusters are unavailable.','Barrel/MFT paths are constant-Bz projections of stored fits without material corrections.','Forward MCH/MID paths are linear fitted-state projections, not transport through the dipole field.']}
    omitted=0
    with uproot.open(source,object_cache=None,array_cache=None) as file:
        directory=file[ref[0]];mapping=tables(directory);collision=int(ref[1]);col=arrays(directory[mapping['collisions']],entry_start=collision,entry_stop=collision+1)
        event['vertex']=[float(col['fPos'+axis][0]) for axis in 'XYZ'];event['collision_features']=row_features({k:v[0] for k,v in col.items()})
        for family in ('barrel','mft','fwd'):
            if cancelled():raise InterruptedError('AO2D trajectory generation cancelled')
            if family not in mapping:continue
            tree=directory[mapping[family]];indices=selected_rows(tree,collision);data=rows_at(tree,indices)
            extras=rows_at(directory[mapping['extra']],indices) if family=='barrel' and 'extra' in mapping else {}
            cov=covariance_rows(directory,mapping,family,indices,tree.num_entries)
            detector_masks=detector_lists(extras,len(indices)) if family=='barrel' else forward_detectors(data,len(indices)) if family=='fwd' else []
            for j,index in enumerate(indices):
                if j%100==0 and cancelled():raise InterruptedError('AO2D trajectory generation cancelled')
                raw={k:v[j] for k,v in data.items()};extra={k:v[j] for k,v in extras.items()};features=row_features({**raw,**extra})
                try:
                    if family=='barrel':origin,phi,tgl,qpt=helix_state(raw);detectors=[d for d,mask in detector_masks if mask[j]]
                    else:
                        origin=[float(raw['f'+a]) for a in 'XYZ'];phi,tgl,qpt=(float(raw[k]) for k in ('fPhi','fTgl','fSigned1Pt'))
                        detectors=['MFT'] if family=='mft' else [d for d,mask in detector_masks if mask[j]]
                    if not detectors or not all(math.isfinite(v) for v in [*origin,phi,tgl,qpt]):raise ValueError('Missing or invalid track detector/fit information')
                    kin={'phi':(phi+math.pi)%math.tau-math.pi,'eta':math.asinh(tgl),'tan_lambda':tgl}
                    if qpt:kin.update(pt=abs(1/qpt),p=abs(1/qpt)*math.sqrt(1+tgl*tgl))
                    track={'id':f'{ref[0]}:{family}:{int(index)}','source':'-'.join(detectors),'source_basis':'AO2D DetectorMap expressions / explicit forward detector associations','detectors':detectors,'points':projected_points(origin,phi,tgl,qpt,bz,family=family),'kinematics':kin,'features':features,'fit_parameters':{k:float(raw[k]) for k in raw if k in ('fX','fY','fZ','fAlpha','fSnp','fPhi','fTgl','fSigned1Pt')},'trajectory_basis':'Linear forward fit projection' if family=='fwd' else 'Constant-solenoid helix from AO2D fitted parameters; no material corrections','matching':len(detectors)>1,'matching_basis':'Contributing detectors/explicit forward match links in AO2D'}
                    track['associations']={feature_name(k):int(v) for k,v in raw.items() if k.startswith('fIndex') and np.isscalar(v)}
                    features['charge']=int(np.sign(qpt))
                    if cov[j]:track['covariance_parameters']=row_features(cov[j]);features.update(track['covariance_parameters'])
                    if family=='barrel':
                        sizes=int(extra.get('fITSClusterSizes',0));features['its_nclusters']=sum(bool((sizes>>(4*k))&15) for k in range(7)) if 'fITSClusterSizes' in extra else int(extra.get('fITSClusterMap',0)).bit_count()
                        features['tpc_nclusters']=int(extra.get('fTPCNClsFindable',0))-int(extra.get('fTPCNClsFindableMinusFound',0));features['tpc_crossed_rows']=int(extra.get('fTPCNClsFindable',0))-int(extra.get('fTPCNClsFindableMinusCrossedRows',0));features['pid_for_tracking']=int(extra.get('fFlags',0))>>28;features['pv_contributor']=int(bool(int(extra.get('fFlags',0))&2))
                        dca,xy,z=dca_to_vertex(origin,phi,tgl,qpt,bz,event['vertex']);kin['dca']=dca;features.update(dca_xy=xy,dca_z=z);track['dca_basis']='Constant-Bz transverse closest approach of stored fit to AO2D collision PV; no material corrections'
                    event['tracks'].append(track)
                except (ValueError,OverflowError,ZeroDivisionError):omitted+=1
            progress(f'AO2D {family}: {len(indices)} associated fitted records read')
    if omitted:event['warnings'].append(f'{omitted} invalid/unsupported fitted records omitted; indexed counts include source records.')
    event=validate_event(event);fd,tmp=tempfile.mkstemp(prefix='aod-event-',suffix='.json.gz',dir=catalogue.folder);os.close(fd)
    try:
        with gzip.open(tmp,'wt',compresslevel=3) as stream:json.dump(event,stream,separators=(',',':'),allow_nan=False)
        os.replace(tmp,target)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)
    return target
