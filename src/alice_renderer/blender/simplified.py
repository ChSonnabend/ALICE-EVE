"""Deterministic coarse surfaces from aligned instance bounds, never detector guesses.

Each detector is reduced to one mesh of at most 256 spatial cells. These are
explicit approximations; the full aligned assets remain untouched.
"""
import math
import bpy
import numpy as np
from mathutils import Matrix

VERSION=1

def simplify(objects,collection,name):
    cells={}
    meshes=[o for o in objects if o.type=='MESH' and not o.hide_render]
    positions=[];placement_masks={}
    for obj in meshes:
        if 'num_instances' in obj:
            group=obj.modifiers['GeometryNodes'].node_group
            inst=next(n for n in group.nodes if n.bl_idname=='GeometryNodeInstanceOnPoints')
            po=inst.inputs['Points'].links[0].from_node.inputs['Object'].default_value
            a=np.empty(len(po.data.vertices)*3,dtype=np.float32);po.data.vertices.foreach_get('co',a)
            a=a.reshape(-1,3)
            if 'alice_inner_mask_keep' in po.data.attributes:
                keep=np.empty(len(a),dtype=bool);po.data.attributes['alice_inner_mask_keep'].data.foreach_get('value',keep);placement_masks[po.name]=keep;a=a[keep]
            if len(a):positions.append((obj,po,a,inst.inputs['Instance'].links[0].from_node.inputs['Object'].default_value))
        else:
            corners=np.array([tuple(obj.matrix_world@__import__('mathutils').Vector(c)) for c in obj.bound_box])
            positions.append((obj,None,corners,None))
    if not positions:
        for obj in objects:obj.hide_render=True;obj.hide_set(True)
        return [],{'approximate':True,'cells':0,'source_instances':0}
    global_positions=[a@np.array(o.matrix_world)[:3,:3].T+np.array(o.matrix_world)[:3,3] if po is not None else a for o,po,a,_ in positions]
    zmin=min(float(a[:,2].min()) for a in global_positions);zmax=max(float(a[:,2].max()) for a in global_positions)
    rmax=max(float(np.hypot(a[:,0],a[:,1]).max()) for a in global_positions)
    del global_positions
    original=0
    for obj,po,points,prototype in positions:
        if po is None:bounds=[(points.min(axis=0),points.max(axis=0))]
        else:
            count=len(points);original+=count
            angles=np.empty(len(po.data.vertices)*3,dtype=np.float32);po.data.attributes['rot_euler'].data.foreach_get('vector',angles);angles=angles.reshape(-1,3)
            scales=np.empty(len(po.data.vertices)*3,dtype=np.float32);po.data.attributes['instance_scale'].data.foreach_get('vector',scales);scales=scales.reshape(-1,3)
            if po.name in placement_masks:angles=angles[placement_masks[po.name]];scales=scales[placement_masks[po.name]]
            bbox=np.array(prototype.bound_box);center=(bbox.min(axis=0)+bbox.max(axis=0))/2;half=(bbox.max(axis=0)-bbox.min(axis=0))/2
            world=np.array(obj.matrix_world);bounds=[]
            # Batches avoid a huge expanded instance mesh, including HMP's million cells.
            for start in range(0,count,100000):
                a=angles[start:start+100000];scale=scales[start:start+100000];p=points[start:start+100000]
                cx,cy,cz=np.cos(a).T;sx,sy,sz=np.sin(a).T
                r=np.stack([cy*cz,cz*sx*sy-cx*sz,sx*sz+cx*cz*sy,cy*sz,cx*cz+sx*sy*sz,cx*sy*sz-cz*sx,-sy,cy*sx,cx*cy],axis=1).reshape(-1,3,3)
                r*=scale[:,None,:];r=np.einsum('ij,njk->nik',world[:3,:3],r)
                centers=p@world[:3,:3].T+world[:3,3]+np.einsum('nij,j->ni',r,center)
                extents=np.einsum('nij,j->ni',abs(r),half)
                accumulate(cells,centers,centers-extents,centers+extents,zmin,zmax,rmax)
            continue
        for low,high in bounds:accumulate(cells,((low+high)/2)[None,:],low[None,:],high[None,:],zmin,zmax,rmax)
    vertices=[];faces=[]
    for key,(low,high) in sorted(cells.items()):
        offset=len(vertices)
        vertices.extend([(x,y,z) for z in (low[2],high[2]) for y in (low[1],high[1]) for x in (low[0],high[0])])
        faces.extend([tuple(offset+i for i in face) for face in ((0,2,3,1),(4,5,7,6),(0,1,5,4),(2,6,7,3),(0,4,6,2),(1,3,7,5))])
    for obj in objects:bpy.data.objects.remove(obj,do_unlink=True)
    for mesh in list(bpy.data.meshes):
        if mesh.users==0:bpy.data.meshes.remove(mesh)
    mesh=bpy.data.meshes.new(name+' simplified aligned bounds');mesh.from_pydata(vertices,[],faces);mesh.update()
    obj=bpy.data.objects.new(name+' simplified',mesh);collection.objects.link(obj)
    obj['alice_lod']='simplified';obj['alice_lod_version']=VERSION
    return [obj],{'lod':'simplified','algorithm':'aligned spatial cell bounds v1','original_instances':original,'surface_cells':len(cells),'meshes':1}

def accumulate(cells,centers,low,high,zmin,zmax,rmax):
    phi=((np.arctan2(centers[:,1],centers[:,0])+math.pi)/(2*math.pi)*16).astype(int).clip(0,15)
    z=((centers[:,2]-zmin)/max(1.e-6,zmax-zmin)*8).astype(int).clip(0,7)
    rad=(np.hypot(centers[:,0],centers[:,1])/max(rmax,1.e-6)*2).astype(int).clip(0,1)
    key=phi+16*z+128*rad
    for k in np.unique(key):
        sel=key==k;lo=low[sel].min(axis=0);hi=high[sel].max(axis=0)
        if int(k) in cells:
            oldlo,oldhi=cells[int(k)];lo=np.minimum(lo,oldlo);hi=np.maximum(hi,oldhi)
        cells[int(k)]=(lo,hi)
