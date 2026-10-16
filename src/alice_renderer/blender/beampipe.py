"""Lightweight central beampipe display tube, not an aligned engineering model."""
import json,math
import bpy

def update_beampipe(settings):
    from worker import collection,materials,rgb,remove_owned_collection
    coll=bpy.data.collections.get('Beampipe')
    if not settings.get('beampipe',False):
        if coll:coll.hide_render=True;coll.hide_viewport=True
        return {'enabled':False}
    values=[settings.get('beampipe_radius_cm',1.8),settings.get('beampipe_wall_cm',.08),settings.get('beampipe_z_cm',[-450,450]),settings.get('beampipe_color','#0700b5')]
    signature=json.dumps(values[:3])
    if coll and coll.get('alice_pipe_signature')!=signature:remove_owned_collection(coll);coll=None
    if not coll:
        coll=collection('Beampipe');coll['alice_pipe_signature']=signature
        radius,wall,limits,color=values;n=128;vertices=[];faces=[]
        for r,z in ((radius,limits[0]),(radius,limits[1]),(radius-wall,limits[0]),(radius-wall,limits[1])):
            vertices.extend((r*.01*math.cos(math.tau*i/n),r*.01*math.sin(math.tau*i/n),z*.01) for i in range(n))
        for i in range(n):
            j=(i+1)%n
            faces.extend([(i,j,n+j,n+i),(2*n+j,2*n+i,3*n+i,3*n+j),(j,i,2*n+i,2*n+j),(n+i,n+j,3*n+j,3*n+i)])
        mesh=bpy.data.meshes.new('Central beampipe tube');mesh.from_pydata(vertices,[],faces);mesh.update()
        obj=bpy.data.objects.new('Central beampipe (display approximation)',mesh);coll.objects.link(obj);obj['alice_preserve_face_normals']=True
        mat=bpy.data.materials.get('ALICE central beampipe')
        if mat is None:
            mat=materials('Beampipe',rgb(color),settings=settings);mat.name='ALICE central beampipe'
        mesh.materials.append(mat)
        for i,poly in enumerate(mesh.polygons):poly.use_smooth=i%4<2
    mat=next(iter(coll.objects)).data.materials[0];rgba=(*rgb(values[3]),1)
    socket=mat.node_tree.nodes['Principled BSDF'].inputs['Base Color']
    if any(abs(a-b)>1.e-7 for a,b in zip(socket.default_value,rgba)):socket.default_value=rgba
    if any(abs(a-b)>1.e-7 for a,b in zip(mat.diffuse_color,rgba)):mat.diffuse_color=rgba
    if coll.hide_render:coll.hide_render=False
    if coll.hide_viewport:coll.hide_viewport=False
    return dict(enabled=True,basis='Configurable hollow central tube along global Z; display approximation, not an aligned beamline assembly',radius_cm=values[0],wall_cm=values[1],z_cm=values[2],faces=512)
