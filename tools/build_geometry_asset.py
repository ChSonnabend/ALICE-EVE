"""Blender entry point: strictly convert aligned surfaces into compact assets.

Run with Blender --background --python-exit-code 1 --python this-file -- ...
The reference converter remains read-only. Every surface placement is checked.
"""
import argparse, gzip, hashlib, json, logging, math, sys
from pathlib import Path

def main():
    p=argparse.ArgumentParser();p.add_argument('--input',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--detector',required=True)
    p.add_argument('--converter',type=Path,required=True)
    a=p.parse_args(sys.argv[sys.argv.index('--')+1:])
    sys.path.insert(0,str(a.converter.resolve()))
    import bpy
    from mathutils import Euler, Matrix, Vector
    import json2blender as reference
    import Blendershapes
    import bmesh
    from shapes import ParamShapeRegistry
    def repair(obj):
        bm=bmesh.new();bm.from_mesh(obj.data)
        bmesh.ops.recalc_face_normals(bm,faces=list(bm.faces));bm.to_mesh(obj.data);bm.free();obj.data.update()
        return obj
    for kind,creator in list(Blendershapes.BlenderShapeCreators.items()):
        if kind!='TGeoCompositeShape':
            Blendershapes.BlenderShapeCreators[kind]=lambda shape,fn=creator:repair(fn(shape))
    def bake(obj,rotation,translation):
        matrix=(Matrix(rotation) if rotation else Matrix.Identity(3)).to_4x4()
        matrix.translation=Vector(translation or (0,0,0))*.01
        obj.data.transform(matrix @ obj.matrix_local);obj.matrix_local=Matrix.Identity(4);repair(obj)
    def composite(shape):
        # ROOT Contains uses dot(point-plane, normal)<=0. The reference's
        # finite half-space box uses the opposite side and can erase TPC solids.
        # Clip the finite operand by the actual plane, then close the cut face.
        left=Blendershapes.BlenderShapeCreators[shape.left_shape_info](ParamShapeRegistry[shape.left_shape_info](**shape.left_shape))
        bake(left,shape.left_matrix,shape.left_translation)
        if shape.right_shape_info!='TGeoHalfSpace' or shape.operation not in ('subtraction','intersection'):
            right=Blendershapes.BlenderShapeCreators[shape.right_shape_info](ParamShapeRegistry[shape.right_shape_info](**shape.right_shape))
            bake(right,shape.right_matrix,shape.right_translation)
            for operand in (left,right):
                if not operand.users_collection:bpy.context.collection.objects.link(operand)
            bpy.context.view_layer.update()
            modifier=left.modifiers.new('ROOT boolean','BOOLEAN');modifier.solver='EXACT'
            modifier.operation={'union':'UNION','subtraction':'DIFFERENCE','intersection':'INTERSECT'}[shape.operation]
            modifier.object=right;modifier.use_self=False;modifier.use_hole_tolerant=True
            bpy.context.view_layer.objects.active=left;bpy.context.view_layer.update()
            bpy.ops.object.modifier_apply(modifier=modifier.name)
            bpy.data.objects.remove(right,do_unlink=True)
            return repair(left)
        half=shape.right_shape
        right_rotation=Matrix(shape.right_matrix) if shape.right_matrix else Matrix.Identity(3)
        normal=right_rotation @ Vector(tuple(half[k] for k in ('nx','ny','nz')))
        plane=right_rotation @ (Vector(tuple(half[k] for k in ('px','py','pz')))*.01)+Vector(shape.right_translation or (0,0,0))*.01
        bm=bmesh.new();bm.from_mesh(left.data)
        cut=bmesh.ops.bisect_plane(bm,geom=[*bm.verts,*bm.edges,*bm.faces],dist=1.e-8,
            plane_co=plane,plane_no=normal,clear_inner=shape.operation=='subtraction',clear_outer=shape.operation=='intersection')
        edges=[e for e in cut['geom_cut'] if isinstance(e,bmesh.types.BMEdge) and e.is_valid and e.is_boundary]
        if edges:bmesh.ops.holes_fill(bm,edges=edges,sides=0)
        bmesh.ops.recalc_face_normals(bm,faces=list(bm.faces));bm.to_mesh(left.data);bm.free();left.data.update()
        return left
    Blendershapes.BlenderShapeCreators['TGeoCompositeShape']=composite
    logging.basicConfig(level=logging.WARNING)
    opener=gzip.open if a.input.suffix=='.gz' else open
    with opener(a.input,'rt') as source:data=json.load(source)
    if not data:raise ValueError('Geometry has no surfaces')
    reference.clear_scene();Blendershapes.MATERIAL_NAME=a.detector
    collection=reference.create_collection(a.detector)
    total=0;max_position_error=0.;max_rotation_error=0.
    for name,item in data.items():
        print(a.detector,name,'building',flush=True)
        obj=reference.create_instanced_shape(name,item['shape'],item['positions'],collection)
        if obj is None:raise RuntimeError('Geometry conversion failed: '+name)
        if obj['num_instances']!=item['num_instances']:raise RuntimeError('Lost geometry instances: '+name)
        group=obj.modifiers['GeometryNodes'].node_group
        nodes,links=group.nodes,group.links
        instance=next(n for n in nodes if n.bl_idname=='GeometryNodeInstanceOnPoints')
        output=next(n for n in nodes if n.bl_idname=='NodeGroupOutput')
        links.new(instance.outputs['Instances'],output.inputs['Geometry'])
        for node in list(nodes):
            if node.bl_idname=='GeometryNodeRealizeInstances':nodes.remove(node)
        points=bpy.data.objects[name+'_points'].data
        prototype=bpy.data.objects[name+'_base']
        if not prototype.data.vertices:raise RuntimeError('Empty geometry prototype: '+name)
        for i,placement in enumerate(item['positions']):
            tra=placement['translation'];expected=Vector(tuple(tra[k]*.01 for k in ('x','y','z')))
            error=(points.vertices[i].co-expected).length
            max_position_error=max(max_position_error,error)
            if error>max(1.e-5,expected.length*2.e-7):raise RuntimeError('Global translation changed: '+name)
            scale=points.attributes['instance_scale'].data[i].vector
            expected_matrix=placement['rotation']['matrix']
            pure=[[expected_matrix[r][c]*scale[c] for c in range(3)] for r in range(3)]
            cosine=math.hypot(pure[0][0],pure[1][0])
            # Avoid mathutils' early Euler gimbal-lock approximation: alignment
            # rotations close to 90 degrees still carry measurable corrections.
            if cosine>1.e-12:
                angles=(math.atan2(pure[2][1],pure[2][2]),math.atan2(-pure[2][0],cosine),math.atan2(pure[1][0],pure[0][0]))
            else:angles=(0.,math.atan2(-pure[2][0],cosine),math.atan2(-pure[0][1],pure[1][1]))
            points.attributes['rot_euler'].data[i].vector=angles
            angles=points.attributes['rot_euler'].data[i].vector
            actual=Euler(angles,'XYZ').to_matrix() @ Matrix.Diagonal(scale)
            rotation_error=max(abs(actual[r][c]-expected_matrix[r][c]) for r in range(3) for c in range(3))
            max_rotation_error=max(max_rotation_error,rotation_error)
            if rotation_error>2.e-5:raise RuntimeError(f'Global rotation/reflection changed: {name}, instance {i}, error {rotation_error}, expected {expected_matrix}, actual {list(map(list,actual))}')
        total+=len(item['positions'])
    bpy.context.scene['alice_geometry_units']='m'
    bpy.context.scene['alice_geometry_axes']='ALICE global XYZ'
    bpy.context.scene['alice_geometry_detector']=a.detector
    a.output.parent.mkdir(parents=True,exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(a.output.resolve()),compress=True)
    report=dict(detector=a.detector,asset=a.output.name,units='m',axes='ALICE global XYZ',
                shapes=len(data),instances=total,max_translation_error_m=max_position_error,
                max_rotation_error=max_rotation_error,source_sha256=hashlib.sha256(a.input.read_bytes()).hexdigest(),
                generator_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    a.output.with_suffix('.qa.json').write_text(json.dumps(report,indent=2))
    print(json.dumps(report))

if __name__=='__main__':main()
