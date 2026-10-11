"""Bake lightweight surfaces once; normal scene loading never imports full meshes."""
import argparse,gzip,io,json,math,os,sys,tempfile,time
from pathlib import Path
sys.path[:0]=[str(Path(__file__).resolve().parents[2]),str(Path(__file__).resolve().parent)]
import bpy,numpy as np
from mathutils import Euler,Vector
from alice_renderer.geometry_components import load_components,sidecar_path as component_path
from alice_renderer.structural_geometry import sidecar_path,SUPPORTED
from alice_renderer.scene_config import sha256
from track_bounds import bounds


def placements(obj):
    node=next(n for n in obj.modifiers['GeometryNodes'].node_group.nodes if n.bl_idname=='GeometryNodeInstanceOnPoints')
    points=node.inputs['Points'].links[0].from_node.inputs['Object'].default_value.data
    prototype=node.inputs['Instance'].links[0].from_node.inputs['Object'].default_value
    p=np.empty(len(points.vertices)*3,dtype=np.float32);points.vertices.foreach_get('co',p)
    a=np.empty(len(p),dtype=np.float32);points.attributes['rot_euler'].data.foreach_get('vector',a)
    s=np.empty(len(p),dtype=np.float32);points.attributes['instance_scale'].data.foreach_get('vector',s)
    return prototype,p.reshape(-1,3),a.reshape(-1,3),s.reshape(-1,3)


def rotation(angle,scale,world):
    return np.array(world)[:3,:3] @ np.array(Euler(angle,'XYZ').to_matrix()) @ np.diag(scale)


def merge(group,vertices,faces):
    offset=len(group['vertices']);group['vertices'].extend(np.asarray(vertices).tolist())
    group['faces'].extend([[offset+i for i in f] for f in faces])


def stave_panels(samples):
    """One rectangular active-area panel per native sensor-plane orientation.

    Corners come from aligned sensor bounds. Tiny alignment differences and
    module/chip gaps are intentionally collapsed into broad display surfaces.
    """
    angles=sorted(((float(phi)%math.tau,xyz) for phi,xyz in samples),key=lambda item:item[0])
    gaps=[(angles[(i+1)%len(angles)][0]-angles[i][0])%math.tau for i in range(len(angles))]
    start=(int(np.argmax(gaps))+1)%len(angles);ordered=angles[start:]+angles[:start]
    clusters=[];previous=None
    for phi,xyz in ordered:
        if previous is None or (phi-previous)%math.tau>.02:clusters.append([])
        clusters[-1].append((phi,xyz));previous=phi
    vertices=[];faces=[]
    box_faces=[[0,2,3,1],[4,5,7,6],[0,1,5,4],[2,6,7,3],[0,4,6,2],[1,3,7,5]]
    for cluster in clusters:
        phi=math.atan2(sum(math.sin(p) for p,_ in cluster),sum(math.cos(p) for p,_ in cluster))
        # Local axes: tangent, radial normal, global beam.
        frame=np.array([[math.sin(phi),-math.cos(phi),0],[math.cos(phi),math.sin(phi),0],[0,0,1]]).T
        points=np.concatenate([xyz for _,xyz in cluster]) @ frame
        low,high=points.min(axis=0),points.max(axis=0)
        panel=np.array([(x,y,z) for z in (low[2],high[2]) for y in (low[1],high[1]) for x in (low[0],high[0])]) @ frame.T
        offset=len(vertices);vertices.extend(panel.tolist());faces.extend([[offset+i for i in f] for f in box_faces])
    return vertices,faces,len(clusters)


def bake(asset,units):
    start=time.monotonic();metadata=load_components(asset);name=metadata['detector']
    if name not in SUPPORTED:raise ValueError('Large surfaces currently support ITS and TPC')
    with bpy.data.libraries.load(str(asset),link=False) as (source,target):target.objects=source.objects
    objects=[o for o in target.objects if o]
    for obj in objects:bpy.context.scene.collection.objects.link(obj)
    roots=[o for o in objects if o.parent not in objects]
    if units=='cm':
        for obj in roots:obj.location*=.01;obj.scale*=.01
    bpy.context.view_layer.update()
    region=bounds(objects,name) # All source surfaces; never the display subset.
    groups={};layers={};source_count=0
    for obj in objects:
        if 'num_instances' not in obj:continue
        entry=metadata['groups'][obj.name];prototype,positions,angles,scales=placements(obj)
        world=np.array(obj.matrix_world);corners=np.array(prototype.bound_box)
        if name=='ITS':
            for i,(p,angle,scale) in enumerate(zip(positions,angles,scales)):
                tags=entry['classes'][entry['ids'][i]]
                if 'structures/sensors' not in tags:continue
                layer=next((t for t in tags if t.startswith('layers/')),None)
                if not layer:continue
                r=rotation(angle,scale,obj.matrix_world)
                xyz=corners @ r.T + (world[:3,:3]@p+world[:3,3])
                normal=r[:,1];phi=math.atan2(normal[1],normal[0])
                center=xyz.mean(axis=0)
                if np.dot(normal[:2],center[:2])<0:phi+=math.pi
                key=(tuple(tags),obj.name);layers.setdefault(key,[]).append((phi,xyz));source_count+=1
        else:
            tags_by_class=entry['classes']
            wanted=[bool(set(tags)&{'structures/inner_wall','structures/outer_wall','structures/readout'}) for tags in tags_by_class]
            if not any(wanted):continue
            # Dissolve coplanar details, then reduce curved/CSG surfaces. Keep holes
            # and the original aligned placement rather than a convex hull.
            temp=bpy.data.objects.new('Bake proxy',prototype.data.copy());bpy.context.scene.collection.objects.link(temp)
            bpy.context.view_layer.objects.active=temp;temp.select_set(True)
            modifier=temp.modifiers.new('Remove coplanar details','DECIMATE');modifier.decimate_type='DISSOLVE';modifier.angle_limit=math.radians(4)
            bpy.ops.object.modifier_apply(modifier=modifier.name)
            if len(temp.data.polygons)>512:
                modifier=temp.modifiers.new('Reduce surface detail','DECIMATE');modifier.ratio=512/len(temp.data.polygons)
                bpy.ops.object.modifier_apply(modifier=modifier.name)
            local=np.array([tuple(v.co) for v in temp.data.vertices]);faces=[list(p.vertices) for p in temp.data.polygons]
            for i,(p,angle,scale) in enumerate(zip(positions,angles,scales)):
                tags=tags_by_class[entry['ids'][i]]
                if not wanted[entry['ids'][i]]:continue
                key=(tuple(tags),obj.name);group=groups.setdefault(key,dict(name=obj.name,source_names=[obj.name],tags=list(tags),vertices=[],faces=[],elements=0))
                r=rotation(angle,scale,obj.matrix_world)
                xyz=local @ r.T + (world[:3,:3]@p+world[:3,3])
                merge(group,xyz,[f[::-1] for f in faces] if np.linalg.det(r)<0 else faces);group['elements']+=1;source_count+=1
            mesh=temp.data;bpy.data.objects.remove(temp,do_unlink=True);bpy.data.meshes.remove(mesh)
    for (tags,source_name),samples in sorted(layers.items()):
        v,f,count=stave_panels(samples)
        groups[(tags,source_name)]=dict(name='ITS '+next(t for t in tags if t.startswith('layers/')).split('/')[-1]+' staves',source_names=[source_name],tags=list(tags),vertices=v,faces=f,elements=count)
    data=dict(schema='alice-structural-geometry',version=1,detector=name,units='m',source_units=units,
              asset_sha256=sha256(asset),components_sha256=sha256(component_path(asset)),
              basis='ITS sensor-bound stave panels; TPC reduced native wall/readout meshes. Display approximation, not full material geometry.',
              track_region=region,source_instances=source_count,groups=list(groups.values()))
    path=sidecar_path(asset);fd,tmp=tempfile.mkstemp(dir=path.parent,prefix='.'+path.name);os.close(fd)
    try:
        with open(tmp,'wb') as binary:
            with gzip.GzipFile(filename='',fileobj=binary,mode='wb',mtime=0) as compressed:
                with io.TextIOWrapper(compressed,encoding='utf-8') as stream:json.dump(data,stream,separators=(',',':'),allow_nan=False)
        os.replace(tmp,path)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)
    print(json.dumps(dict(detector=name,cache=str(path),bytes=path.stat().st_size,meshes=len(groups),elements=sum(g['elements'] for g in groups.values()),faces=sum(len(g['faces']) for g in groups.values()),bake_seconds=round(time.monotonic()-start,3))),flush=True)
    for obj in objects:bpy.data.objects.remove(obj,do_unlink=True)
    bpy.data.orphans_purge(do_recursive=True)


def main():
    p=argparse.ArgumentParser();p.add_argument('--geometry-root',type=Path,required=True);p.add_argument('--detectors',default='ITS,TPC');p.add_argument('--units',choices=['m','cm'],default='m')
    args=p.parse_args(sys.argv[sys.argv.index('--')+1:])
    for name in args.detectors.split(','):
        name=name.strip()
        if name not in SUPPORTED:raise ValueError('Large surfaces currently support ITS and TPC')
        bake(args.geometry_root/(name+'.blend'),args.units)
if __name__=='__main__':main()
