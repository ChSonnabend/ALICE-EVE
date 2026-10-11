"""Outer hulls and outlines of coarse aligned surfaces (explicit approximations)."""
import bpy
import bmesh
from mathutils import Vector


def display_geometry(objects, collection, name, style):
    if style=='surfaces':return objects,{}
    # Inputs are already reduced aligned cells; never expand millions of instances.
    vertices=[obj.matrix_world@v.co for obj in objects for v in obj.data.vertices]
    if len(vertices)<4:raise ValueError(name+': not enough vertices for an outer shell')
    bm=bmesh.new()
    for point in vertices:bm.verts.new(point)
    result=bmesh.ops.convex_hull(bm,input=list(bm.verts),use_existing_faces=False)
    unused=[v for v in bm.verts if not v.link_faces]
    if unused:bmesh.ops.delete(bm,geom=unused,context='VERTS')
    bmesh.ops.dissolve_limit(bm,angle_limit=1.e-5,verts=list(bm.verts),edges=list(bm.edges),delimit={'NORMAL'})
    bmesh.ops.recalc_face_normals(bm,faces=list(bm.faces))
    mesh=bpy.data.meshes.new(name+' outer shell');bm.to_mesh(mesh);bm.free();mesh.update()
    obj=bpy.data.objects.new(name+' '+style,mesh);collection.objects.link(obj)
    obj['alice_lod']='outer hull';obj['alice_display']=style
    for original in objects:bpy.data.objects.remove(original,do_unlink=True)
    if style=='outline':
        curve=bpy.data.curves.new(name+' outline','CURVE');curve.dimensions='3D'
        bpy.context.view_layer.update()
        bounds=[Vector(c) for c in obj.bound_box]
        diameter=(max((p-q).length for p in bounds for q in bounds))
        curve.bevel_depth=max(.001,diameter*.0008);curve.bevel_resolution=1;curve.resolution_u=1
        for edge in mesh.edges:
            spline=curve.splines.new('POLY');spline.points.add(1)
            for point,index in zip(spline.points,edge.vertices):point.co=(*mesh.vertices[index].co,1.)
        outlined=bpy.data.objects.new(name+' outline',curve);collection.objects.link(outlined)
        outlined['alice_lod']='outer hull';outlined['alice_display']='outline'
        bpy.data.objects.remove(obj,do_unlink=True);obj=outlined
    return [obj],{'display':style,'display_algorithm':'aligned coarse bounds convex hull v1','display_approximate':True,'outer_vertices':len(mesh.vertices),'outer_faces':len(mesh.polygons),'outline_edges':len(mesh.edges) if style=='outline' else 0}
