"""Run with Blender --background --python this.py -- --input ... --output ..."""
import argparse,gzip,json,sys,hashlib
from pathlib import Path
import bpy,bmesh
from mathutils import Matrix
p=argparse.ArgumentParser();p.add_argument('--input',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args(sys.argv[sys.argv.index('--')+1:])
with gzip.open(a.input,'rt') as f:data=json.load(f)
a.output.mkdir(parents=True,exist_ok=True)
bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
cache={}
def transform(rows):
    m=Matrix(rows);m.translation*=.01;return m

def mesh_for(key):
    if key in cache:return cache[key]
    s=data['shapes'][key]
    if s['kind']=='mesh':
        mesh=bpy.data.meshes.new(key);mesh.from_pydata([[v*.01 for v in xyz] for xyz in s['vertices']],[],s['faces']);mesh.update()
        bm=bmesh.new();bm.from_mesh(mesh);bmesh.ops.recalc_face_normals(bm,faces=list(bm.faces));bm.to_mesh(mesh);bm.free()
    else:
        left=bpy.data.objects.new('boolean-left',mesh_for(s['left']).copy());right=bpy.data.objects.new('boolean-right',mesh_for(s['right']).copy())
        bpy.context.scene.collection.objects.link(left);bpy.context.scene.collection.objects.link(right)
        left.matrix_world=transform(s['left_matrix']);right.matrix_world=transform(s['right_matrix'])
        mod=left.modifiers.new('O2 boolean','BOOLEAN');mod.solver='EXACT';mod.operation={'TGeoUnion':'UNION','TGeoSubtraction':'DIFFERENCE','TGeoIntersection':'INTERSECT'}[s['operation']];mod.object=right
        bpy.context.view_layer.objects.active=left;bpy.ops.object.modifier_apply(modifier=mod.name)
        mesh=left.data.copy();mesh.transform(left.matrix_world)
        bpy.data.objects.remove(left,do_unlink=True);bpy.data.objects.remove(right,do_unlink=True)
    if not mesh.vertices:raise ValueError('Empty tessellated shape '+key)
    cache[key]=mesh;return mesh
manifest={'variant':data['variant'],'basis':data['basis'],'source_sha256':data['source_sha256'],'units':'m','assets':{}}
for detector,groups in data['detectors'].items():
    coll=bpy.data.collections.new(detector);bpy.context.scene.collection.children.link(coll)
    for key,group in groups.items():
        prototype=bpy.data.objects.new(group['name']+'_base',mesh_for(key));coll.objects.link(prototype);prototype.hide_render=True;prototype.hide_set(True)
        matrices=[transform(m) for m in group['matrices']]
        mesh=bpy.data.meshes.new(group['name']+'_points');mesh.from_pydata([m.translation for m in matrices],[],[])
        rotations=mesh.attributes.new('rot_euler','FLOAT_VECTOR','POINT');scales=mesh.attributes.new('instance_scale','FLOAT_VECTOR','POINT')
        for i,m in enumerate(matrices):
            loc,rot,scale=m.decompose();rotations.data[i].vector=rot.to_euler();scales.data[i].vector=scale
        points=bpy.data.objects.new(group['name']+'_points',mesh);coll.objects.link(points);points.hide_render=True;points.hide_set(True)
        obj=bpy.data.objects.new(group['name'],bpy.data.meshes.new(group['name']));coll.objects.link(obj);obj['num_instances']=len(matrices)
        nodes=bpy.data.node_groups.new(group['name'],'GeometryNodeTree');nodes.interface.new_socket(name='Geometry',in_out='INPUT',socket_type='NodeSocketGeometry');nodes.interface.new_socket(name='Geometry',in_out='OUTPUT',socket_type='NodeSocketGeometry')
        n,l=nodes.nodes,nodes.links;inp=n.new('NodeGroupInput');out=n.new('NodeGroupOutput');inst=n.new('GeometryNodeInstanceOnPoints');info=n.new('GeometryNodeObjectInfo');info.inputs['Object'].default_value=prototype
        point_info=n.new('GeometryNodeObjectInfo');point_info.inputs['Object'].default_value=points
        l.new(point_info.outputs['Geometry'],inst.inputs['Points']);l.new(info.outputs['Geometry'],inst.inputs['Instance']);l.new(inst.outputs['Instances'],out.inputs['Geometry'])
        for name,socket in [('rot_euler','Rotation'),('instance_scale','Scale')]:
            attr=n.new('GeometryNodeInputNamedAttribute');attr.data_type='FLOAT_VECTOR';attr.inputs['Name'].default_value=name;l.new(attr.outputs['Attribute'],inst.inputs[socket])
        obj.modifiers.new('GeometryNodes','NODES').node_group=nodes
    target=a.output/(detector+'.blend');bpy.data.libraries.write(str(target),{coll},compress=True)
    manifest['assets'][detector]={'file':target.name,'sha256':hashlib.sha256(target.read_bytes()).hexdigest(),'shapes':len(groups),'instances':sum(len(g['matrices']) for g in groups.values())}
    print(detector,manifest['assets'][detector],flush=True)
(a.output/'design-manifest.json').write_text(json.dumps(manifest,indent=2))
