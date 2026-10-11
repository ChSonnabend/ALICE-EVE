"""Derive compact outer-envelope planes from actual aligned prototype vertices.

No radius constants or event-hit extents are used for real aligned assets.
64 azimuth support planes and +/-Z bound the physical detector exterior.
"""
import math
import bpy
import numpy as np

DIRECTIONS=np.array([(math.cos(i*math.tau/64),math.sin(i*math.tau/64),0.) for i in range(64)]+[(0.,0.,1.),(0.,0.,-1.)])


def bounds(objects,name):
    maxima=np.full(len(DIRECTIONS),-np.inf);count=0
    for obj in objects:
        if obj.type!='MESH' or obj.hide_render:continue
        world=np.array(obj.matrix_world)
        if 'num_instances' not in obj:
            vertices=np.array([tuple(v.co) for v in obj.data.vertices])
            if len(vertices):maxima=np.maximum(maxima,((vertices@world[:3,:3].T+world[:3,3])@DIRECTIONS.T).max(axis=0));count+=len(vertices)
            continue
        group=obj.modifiers['GeometryNodes'].node_group
        node=next(n for n in group.nodes if n.bl_idname=='GeometryNodeInstanceOnPoints')
        po=node.inputs['Points'].links[0].from_node.inputs['Object'].default_value
        prototype=node.inputs['Instance'].links[0].from_node.inputs['Object'].default_value
        size=len(po.data.vertices);v=np.empty(len(prototype.data.vertices)*3,dtype=np.float32);prototype.data.vertices.foreach_get('co',v);v=v.reshape(-1,3)
        if not len(v):continue
        positions=np.empty(size*3,dtype=np.float32);po.data.vertices.foreach_get('co',positions);positions=positions.reshape(-1,3)
        angles=np.empty(size*3,dtype=np.float32);po.data.attributes['rot_euler'].data.foreach_get('vector',angles);angles=angles.reshape(-1,3)
        scales=np.empty(size*3,dtype=np.float32);po.data.attributes['instance_scale'].data.foreach_get('vector',scales);scales=scales.reshape(-1,3)
        # Bound temporary arrays, including small detectors with millions of repeated shapes.
        step=max(1,100000//len(v))
        for start in range(0,size,step):
            a=angles[start:start+step];scale=scales[start:start+step];p=positions[start:start+step]
            cx,cy,cz=np.cos(a).T;sx,sy,sz=np.sin(a).T
            r=np.stack([cy*cz,cz*sx*sy-cx*sz,sx*sz+cx*cz*sy,cy*sz,cx*cz+sx*sy*sz,cx*sy*sz-cz*sx,-sy,cy*sx,cx*cy],axis=1).reshape(-1,3,3)
            r*=scale[:,None,:]
            xyz=np.einsum('nij,vj->nvi',r,v)+p[:,None,:]
            xyz=xyz.reshape(-1,3)@world[:3,:3].T+world[:3,3]
            maxima=np.maximum(maxima,(xyz@DIRECTIONS.T).max(axis=0));count+=len(xyz)
    if not count or not np.isfinite(maxima).all():raise ValueError(name+': cannot derive track extent from aligned geometry')
    return {'planes':np.column_stack((DIRECTIONS,maxima*100.)).tolist(),'units':'cm','basis':'aligned prototype vertices; 64 azimuth support planes and global Z bounds','transformed_vertices':count}
