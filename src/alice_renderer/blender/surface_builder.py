"""Bake five reviewable native-surface approximations without changing sources."""
import sys,json,gzip,math,time,copy
from pathlib import Path
sys.path[:0]=[str(Path(__file__).resolve().parents[2]),str(Path(__file__).resolve().parent)]
import bpy,numpy as np
from structural_builder import placements,rotation,merge
from alice_renderer.geometry_components import load_components,sidecar_path as component_path
from alice_renderer.scene_config import sha256

TIERS=[(.025,24),(.015,48),(.008,96),(.004,192),(.0015,384)]


def write(path,data):
    with gzip.open(path,'wt') as stream:json.dump(data,stream,separators=(',',':'))


def reduce_mesh(mesh,budget):
    obj=bpy.data.objects.new('temporary proxy reduction',mesh.copy());bpy.context.scene.collection.objects.link(obj)
    bpy.context.view_layer.objects.active=obj;obj.select_set(True)
    mod=obj.modifiers.new('Coplanar reduction','DECIMATE');mod.decimate_type='DISSOLVE';mod.angle_limit=math.radians(3)
    bpy.ops.object.modifier_apply(modifier=mod.name)
    if len(obj.data.polygons)>budget:
        mod=obj.modifiers.new('Surface reduction','DECIMATE');mod.ratio=max(.001,budget/len(obj.data.polygons));bpy.ops.object.modifier_apply(modifier=mod.name)
    v=np.array([tuple(p.co) for p in obj.data.vertices]);f=[list(p.vertices) for p in obj.data.polygons]
    data=obj.data;bpy.data.objects.remove(obj,do_unlink=True);bpy.data.meshes.remove(data)
    return v,f


def bake(asset,out,units='m'):
    out.mkdir(parents=True,exist_ok=True);name=asset.stem
    metadata=load_components(asset)
    with bpy.data.libraries.load(str(asset),link=False) as (source,target):target.objects=source.objects
    objects=[o for o in target.objects if o]
    for obj in objects:bpy.context.scene.collection.objects.link(obj)
    if units=='cm':
        for obj in objects:
            if obj.parent not in objects:obj.location*=.01;obj.scale*=.01
    bpy.context.view_layer.update()
    originals=[];lows=[];highs=[];source_count=0
    for obj in objects:
        if 'num_instances' not in obj:continue
        proto,p,a,s=placements(obj);entry=metadata['groups'][obj.name]
        # Source bounds, in batches, without realizing instanced geometry.
        world=np.array(obj.matrix_world);bbox=np.array(proto.bound_box)
        extent=np.ptp(bbox,axis=0);feature=float(sorted(extent)[-2]);source_count+=len(p)
        for start in range(0,len(p),20000):
            angle=a[start:start+20000];scale=s[start:start+20000];pos=p[start:start+20000]
            cx,cy,cz=np.cos(angle).T;sx,sy,sz=np.sin(angle).T
            r=np.stack([cy*cz,cz*sx*sy-cx*sz,sx*sz+cx*cz*sy,cy*sz,cx*cz+sx*sy*sz,cx*sy*sz-cz*sx,-sy,cy*sx,cx*cy],axis=1).reshape(-1,3,3)*scale[:,None,:]
            r=np.einsum('ij,njk->nik',world[:3,:3],r)
            xyz=np.einsum('nij,vj->nvi',r,bbox)+ (pos@world[:3,:3].T+world[:3,3])[:,None,:]
            lows.append(xyz.min(axis=(0,1)));highs.append(xyz.max(axis=(0,1)))
        originals.append((obj,proto,p,a,s,entry,feature))
    low=np.min(lows,axis=0);high=np.max(highs,axis=0);diameter=max(high[0]-low[0],high[1]-low[1]);common=dict(schema='alice-surface-proxy',version=1,detector=name,source_units=units,asset_sha256=sha256(asset),components_sha256=sha256(component_path(asset)),source_instances=source_count,bounds_m=[low.tolist(),high.tolist()],track_region=None)
    oldcache=Path(str(asset)+'.structural.json.gz');structural=json.load(gzip.open(oldcache,'rt')) if oldcache.exists() else None
    if structural:common['track_region']=structural['track_region']
    for attempt,(cutoff,budget) in enumerate(TIERS,1):
        groups={};kept=0
        if structural:
            for index,original in enumerate(structural['groups']):
                group=copy.deepcopy(original)
                if name=='ITS':
                    # Thin panel surfaces retain all seven layers and native stave gaps.
                    if attempt<=2:
                        f=group['faces'];v=np.array(group['vertices']);chosen=[]
                        for start in range(0,len(f),6):
                            block=f[start:start+6]
                            area=lambda face:np.linalg.norm(np.cross(v[face[1]]-v[face[0]],v[face[2]]-v[face[0]]))
                            ranked=sorted(block,key=area,reverse=True);chosen.extend(ranked[:attempt])
                        group['faces']=chosen
                    elif attempt in (3,4):
                        # Full stave panels with/without thin side faces.
                        if attempt==3:group['faces']=[f for j,f in enumerate(group['faces']) if j%6 not in (0,1)]
                else:
                    mesh=bpy.data.meshes.new('source cached surface');mesh.from_pydata(group['vertices'],[],group['faces']);mesh.update()
                    v,f=reduce_mesh(mesh,budget);bpy.data.meshes.remove(mesh);group['vertices']=v.tolist();group['faces']=f
                groups[index]=group;kept+=group['elements']
        else:
            usable=[o for o in originals if o[-1]>=diameter*cutoff and len(o[2])<=5000]
            if not usable:usable=[max(originals,key=lambda o:o[-1])]
            for obj,proto,p,a,s,entry,feature in usable:
                v,f=reduce_mesh(proto.data,budget)
                if not len(v) or not f:continue
                world=np.array(obj.matrix_world)
                for i,(pos,angle,scale) in enumerate(zip(p,a,s)):
                    tags=entry['classes'][entry['ids'][i]];key=(obj.name,tuple(tags))
                    group=groups.setdefault(key,dict(name=obj.name,source_names=[obj.name],tags=list(tags),vertices=[],faces=[],elements=0))
                    r=rotation(angle,scale,obj.matrix_world);xyz=v@r.T+world[:3,:3]@pos+world[:3,3]
                    merge(group,xyz,[face[::-1] for face in f] if np.linalg.det(r)<0 else f);group['elements']+=1;kept+=1
        data=dict(common,groups=list(groups.values()),attempt=attempt,basis='Approximate aligned native surfaces: small repeated parts omitted, native placement retained; ITS thin stave panels / TPC cached walls where available',parameters={'minimum_secondary_extent_fraction':cutoff,'prototype_face_budget':budget},retained_instances=kept)
        data['faces']=sum(len(g['faces']) for g in data['groups']);data['vertices']=sum(len(g['vertices']) for g in data['groups'])
        write(out/f'candidate-{attempt}.json.gz',data)
        print(name,attempt,'faces',data['faces'],'placements',kept,flush=True)
    (out/'source.json').write_text(json.dumps(common,indent=2))
    return objects

if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--asset',type=Path,required=True);parser.add_argument('--output',type=Path,required=True);parser.add_argument('--units',default='m');args=parser.parse_args(sys.argv[sys.argv.index('--')+1:]);bake(args.asset,args.output,args.units)
