"""Executed by Blender, never imported by the desktop application."""
import argparse, colorsys, gzip, json, math, sys
from pathlib import Path
import bpy
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
sys.path.insert(0,str(Path(__file__).resolve().parent))
from mathutils import Vector
BOUND_CACHE={}

def probe(path):
    prefs=bpy.context.preferences.addons['cycles'].preferences
    result={'version':list(bpy.app.version),'version_string':bpy.app.version_string,'devices':[],'errors':{}}
    for backend in ('CPU','METAL','HIP','CUDA','OPTIX'):
        try:
            prefs.compute_device_type='NONE' if backend=='CPU' else backend
            prefs.get_devices()
            for device in prefs.devices:
                if device.type==backend:
                    value={'name':device.name,'type':device.type,'id':device.id}
                    if value not in result['devices']:result['devices'].append(value)
        except Exception as exc: result['errors'][backend]=str(exc)
    # Cycles always provides CPU rendering, including builds where devices aren't enumerated in NONE mode.
    if not any(d['type']=='CPU' for d in result['devices']):
        result['devices'].append({'name':'CPU','type':'CPU','id':'CPU'})
    Path(path).write_text(json.dumps(result,indent=2))

def rgb(value):
    value=value.lstrip('#')
    if len(value)!=6:raise ValueError('Expected RGB colour #rrggbb')
    # UI colours are sRGB; Blender node input values are scene-linear.
    srgb=[int(value[i:i+2],16)/255 for i in (0,2,4)]
    return tuple(c/12.92 if c<=.04045 else ((c+.055)/1.055)**2.4 for c in srgb)

VIRIDIS=[(0.267,0.005,0.329),(0.254,0.265,0.530),(0.164,0.471,0.558),(0.135,0.659,0.518),(0.478,0.821,0.318),(0.993,0.906,0.144)]

def scale_color(value,low,high,palette):
    t=max(0.,min(1.,(value-low)/(high-low))) if high>low else .5
    if palette=='hsv': return colorsys.hsv_to_rgb((1-t)*.7,.85,1)
    if palette=='coolwarm':
        return ((.2+.8*t,.35+.5*(1-abs(2*t-1)),1-.8*t))
    pos=t*(len(VIRIDIS)-1);i=min(len(VIRIDIS)-2,int(pos));fraction=pos-i
    return tuple(VIRIDIS[i][j]*(1-fraction)+VIRIDIS[i+1][j]*fraction for j in range(3))

def value(obj,mode):
    if mode in ('x','y','z'):
        pos=obj.get('position',obj.get('points',[[0,0,0]])[0])
        return pos[('x','y','z').index(mode)]
    if mode in ('primaries','secondaries'):
        if obj.get('classification') not in ('primary','secondary'):return None
        return float(obj['classification']==('primary' if mode=='primaries' else 'secondary'))
    return obj.get('kinematics',{}).get(mode)

def materials(name,color,opacity=1.,emission=0.,cutaway=False,settings=None):
    mat=bpy.data.materials.new(name);mat.use_nodes=True
    bsdf=mat.node_tree.nodes.get('Principled BSDF')
    bsdf.inputs['Base Color'].default_value=(*color,1)
    bsdf.inputs['Roughness'].default_value=(settings or {}).get('roughness',.38)
    bsdf.inputs['Metallic'].default_value=(settings or {}).get('metallic',.15)
    bsdf.inputs['Emission Color'].default_value=(*color,1)
    bsdf.inputs['Emission Strength'].default_value=emission
    if opacity<1 or settings and name in settings.get('geometry_openings',{}):
        nodes,links=mat.node_tree.nodes,mat.node_tree.links
        transparent=nodes.new('ShaderNodeBsdfTransparent')
        mix=nodes.new('ShaderNodeMixShader');mix.inputs[0].default_value=opacity
        links.new(transparent.outputs[0],mix.inputs[1]);links.new(bsdf.outputs[0],mix.inputs[2])
        links.new(mix.outputs[0],nodes.get('Material Output').inputs['Surface'])
    if cutaway:
        # World-space shading also clips instanced geometry correctly. Cutting
        # prototype meshes would instead cut every instance in its local frame.
        nodes,links=mat.node_tree.nodes,mat.node_tree.links
        output=nodes.get('Material Output');surface=output.inputs['Surface'].links[0].from_socket
        geometry=nodes.new('ShaderNodeNewGeometry');separate=nodes.new('ShaderNodeSeparateXYZ')
        negative=nodes.new('ShaderNodeMath');negative.operation='LESS_THAN';negative.inputs[1].default_value=0
        transparent=nodes.new('ShaderNodeBsdfTransparent');clip=nodes.new('ShaderNodeMixShader')
        links.new(geometry.outputs['Position'],separate.inputs[0]);links.new(separate.outputs['Y'],negative.inputs[0])
        links.new(negative.outputs[0],clip.inputs[0]);links.new(surface,clip.inputs[1]);links.new(transparent.outputs[0],clip.inputs[2])
        links.new(clip.outputs[0],output.inputs['Surface'])
    if settings and name in settings.get('geometry_openings',{}):
        angular_cut(mat,settings['geometry_openings'][name])
    mat.diffuse_color=(*color,opacity)
    if hasattr(mat,'surface_render_method'):mat.surface_render_method='BLENDED' if (settings or {}).get('_interactive') else 'DITHERED'
    return mat

def angular_cut(mat,opening):
    # Remove a wedge centred on -Y around the beam (global Z). Shader clipping
    # keeps every instance in global axes and is editable without rebuilding.
    nodes,links=mat.node_tree.nodes,mat.node_tree.links
    output=nodes.get('Material Output');surface=output.inputs['Surface'].links[0].from_socket
    geom=nodes.new('ShaderNodeNewGeometry');sep=nodes.new('ShaderNodeSeparateXYZ')
    atan=nodes.new('ShaderNodeMath');atan.operation='ARCTAN2'
    add=nodes.new('ShaderNodeMath');add.operation='ADD';add.inputs[1].default_value=math.pi/2
    cos=nodes.new('ShaderNodeMath');cos.operation='COSINE'
    acos=nodes.new('ShaderNodeMath');acos.operation='ARCCOSINE'
    less=nodes.new('ShaderNodeMath');less.name='ALICE opening';less.operation='LESS_THAN';less.inputs[1].default_value=math.radians(opening)/2
    transparent=nodes.new('ShaderNodeBsdfTransparent');mix=nodes.new('ShaderNodeMixShader')
    links.new(geom.outputs['Position'],sep.inputs[0]);links.new(sep.outputs['Y'],atan.inputs[0]);links.new(sep.outputs['X'],atan.inputs[1])
    links.new(atan.outputs[0],add.inputs[0]);links.new(add.outputs[0],cos.inputs[0]);links.new(cos.outputs[0],acos.inputs[0]);links.new(acos.outputs[0],less.inputs[0])
    links.new(less.outputs[0],mix.inputs[0]);links.new(surface,mix.inputs[1]);links.new(transparent.outputs[0],mix.inputs[2]);links.new(mix.outputs[0],output.inputs['Surface'])

def collection(name):
    coll=bpy.data.collections.new(name);bpy.context.scene.collection.children.link(coll);return coll

def remove_owned_collection(coll):
    """Release scene buffers during interactive redraws, including orphan node groups."""
    objects=list(coll.objects)
    data={o.data for o in objects if o.type in ('MESH','CURVE')}
    groups={m.node_group for o in objects for m in o.modifiers if m.type=='NODES' and m.node_group}
    for obj in objects:bpy.data.objects.remove(obj,do_unlink=True)
    bpy.data.collections.remove(coll)
    for group in groups:
        if not group.users:bpy.data.node_groups.remove(group)
    for block in data:
        if not block.users:
            if isinstance(block,bpy.types.Mesh):bpy.data.meshes.remove(block)
            elif isinstance(block,bpy.types.Curve):bpy.data.curves.remove(block)
    for mat in list(bpy.data.materials):
        if not mat.users and mat.name.startswith(('Track ','Cluster ')):bpy.data.materials.remove(mat)

def buckets(objects,mode,base,settings,kind):
    values=[value(o,mode) for o in objects] if mode!='solid' else []
    usable=[v for v in values if v is not None and math.isfinite(v)]
    if mode in ('primaries','secondaries'):low,high=0.,1.
    elif mode=='phi':low,high=-math.pi,math.pi
    else:low,high=(min(usable),max(usable)) if usable else (0.,1.)
    if settings.get('scale_min') is not None:low=settings['scale_min']
    if settings.get('scale_max') is not None:high=settings['scale_max']
    fixed=settings.get('color_ranges',{}).get(kind)
    if fixed is not None:low,high=fixed
    groups={};missing=0
    for obj in objects:
        val=value(obj,mode) if mode!='solid' else None
        if mode=='solid':color=settings.get('colors_linear',{}).get(kind,rgb(base));key='solid'
        elif val is None or not math.isfinite(val):color=rgb(settings['missing_color']);key='missing';missing+=1
        else:
            bucket=round(max(0.,min(1.,(val-low)/(high-low) if high>low else .5))*63)
            key=str(bucket);srgb=scale_color(low+(high-low)*bucket/63,low,high,settings['palette'])
            color=tuple(c/12.92 if c<=.04045 else ((c+.055)/1.055)**2.4 for c in srgb)
        if key not in groups:groups[key]={'color':color,'items':[]}
        groups[key]['items'].append(obj)
    return groups,{'mode':mode,'min':low,'max':high,'missing':missing,'palette':settings['palette']}

def tracks(objects,settings):
    from alice_renderer.track_clipping import prepare_regions,clip_polyline,selected_track_detectors
    coll=collection('Tracks')
    groups,legend=buckets(objects,settings['track_color_mode'],settings['colors']['tracks'],settings,'tracks')
    regions=prepare_regions(settings.get('_track_regions',{}))
    clipped=0;splines=0
    for key,group in groups.items():
        curve=bpy.data.curves.new('Tracks '+key,'CURVE');curve.dimensions='3D'
        curve.bevel_depth=settings['track_radius_cm']*.01;curve.bevel_resolution=2;curve.resolution_u=2
        curve.materials.append(materials('Track '+key,group['color'],emission=.7,settings=settings))
        for track in group['items']:
            if settings.get('clip_tracks',True):
                names=selected_track_detectors(settings,track)
                pieces=clip_polyline(track['points'],[regions[d] for d in names if d in regions],margin_cm=settings['track_radius_cm'])
            else:pieces=[track['points']]
            if not pieces:clipped+=1
            for points in pieces:
                spline=curve.splines.new('POLY');spline.points.add(len(points)-1)
                coordinates=[c for p in points for c in (p[0]*.01,p[1]*.01,p[2]*.01,1.)]
                spline.points.foreach_set('co',coordinates);splines+=1
        if curve.splines:
            obj=bpy.data.objects.new('Tracks '+key,curve);coll.objects.link(obj)
        else:bpy.data.curves.remove(curve)
    legend.update(clipped_away_tracks=clipped,visible_tracks=len(objects)-clipped,trajectory_pieces=splines)
    return legend

def clusters(objects,settings):
    coll=collection('Clusters')
    groups,legend=buckets(objects,settings['cluster_color_mode'],settings['colors']['clusters'],settings,'clusters')
    for key,group in groups.items():
        mesh=bpy.data.meshes.new('Cluster positions '+key)
        mesh.from_pydata([tuple(v*.01 for v in c['position']) for c in group['items']],[],[]);mesh.update()
        obj=bpy.data.objects.new('Clusters '+key,mesh);coll.objects.link(obj)
        mat=materials('Cluster '+key,group['color'],emission=1.,settings=settings)
        # Instanced spheres keep even large cluster clouds compact in memory.
        nodes=bpy.data.node_groups.new('Cluster spheres '+key,'GeometryNodeTree')
        nodes.interface.new_socket(name='Geometry',in_out='INPUT',socket_type='NodeSocketGeometry')
        nodes.interface.new_socket(name='Geometry',in_out='OUTPUT',socket_type='NodeSocketGeometry')
        n,l=nodes.nodes,nodes.links
        input_=n.new('NodeGroupInput');output=n.new('NodeGroupOutput')
        ico=n.new('GeometryNodeMeshIcoSphere');ico.inputs['Radius'].default_value=settings['cluster_radius_cm']*.01;ico.inputs['Subdivisions'].default_value=1
        material=n.new('GeometryNodeSetMaterial');material.inputs['Material'].default_value=mat
        instance=n.new('GeometryNodeInstanceOnPoints')
        l.new(input_.outputs['Geometry'],instance.inputs['Points']);l.new(ico.outputs['Mesh'],material.inputs['Geometry'])
        l.new(material.outputs['Geometry'],instance.inputs['Instance']);l.new(instance.outputs['Instances'],output.inputs['Geometry'])
        obj.modifiers.new('Cluster instancing','NODES').node_group=nodes
    return legend

# Approximate envelopes are explicitly labelled and never presented as calibrated detector geometry.
ENVELOPES={'ITS':(4,44,75),'TPC':(85,250,500),'TRD':(290,368,700),'TOF':(370,400,750),'HMP':(430,460,450),'EMC':(430,460,700),'PHS':(450,480,160),'CPV':(445,449,160),'MFT':(4,28,35),'MCH':(40,240,150),'MID':(80,280,100),'FT0':(4,18,8),'FV0':(4,75,8),'FDD':(10,50,8),'ZDC':(10,35,50),'L3':(500,590,1200)}
ZPOSITIONS={'MFT':-65,'MCH':-1200,'MID':-1700,'FT0':320,'FV0':330,'FDD':-1700,'ZDC':11000}

def envelope(name,settings):
    inner,outer,length=ENVELOPES[name];inner*=.01;outer*=.01;length*=.01
    center=ZPOSITIONS.get(name,0)*.01
    vertices=[];faces=[];segments=72
    span=math.pi if settings['cutaway'] and name not in settings.get('geometry_openings',{}) else math.tau
    for z in (-length/2+center,length/2+center):
        for radius in (inner,outer):
            vertices += [(radius*math.cos(span*i/segments),radius*math.sin(span*i/segments),z) for i in range(segments+1)]
    n=segments+1
    for i in range(segments):
        faces += [(i,i+1,n+i+1,n+i),(2*n+i,3*n+i,3*n+i+1,2*n+i+1),(i,2*n+i,2*n+i+1,i+1),(n+i,n+i+1,3*n+i+1,3*n+i)]
    for i in (0,segments):faces.append((i,n+i,3*n+i,2*n+i))
    mesh=bpy.data.meshes.new(name+' schematic');mesh.from_pydata(vertices,[],faces);mesh.update()
    obj=bpy.data.objects.new(name+' — schematic envelope',mesh);collection(name).objects.link(obj)
    key='magnet' if name=='L3' else name
    style=settings.get('geometry_display',{}).get(name,'surfaces')
    if style!='surfaces':
        from geometry_display import display_geometry
        objects,_=display_geometry([obj],obj.users_collection[0],name,style);obj=objects[0]
    obj.data.materials.append(materials(name, settings.get('colors_linear',{}).get(key,rgb(settings['colors'][key])),settings.get('geometry_opacities',{}).get(name,settings['geometry_opacity']),settings=settings))

def imported_geometry(name,path,settings,bounds_only=False):
    path=Path(path);before=set(bpy.data.objects)
    if path.suffix=='.blend':
        with bpy.data.libraries.load(str(path),link=False) as (source,target):target.objects=source.objects
        coll=collection(name)
        for obj in target.objects:
            if obj:coll.objects.link(obj)
        objects=[o for o in target.objects if o]
    else:
        if path.suffix in ('.glb','.gltf'):bpy.ops.import_scene.gltf(filepath=str(path))
        elif path.suffix=='.obj':bpy.ops.wm.obj_import(filepath=str(path))
        else:raise ValueError('Unsupported geometry asset')
        objects=list(set(bpy.data.objects)-before)
        coll=collection(name)
        for obj in objects:
            for old in list(obj.users_collection):old.objects.unlink(obj)
            coll.objects.link(obj)
    meshes=[o for o in objects if o.type=='MESH']
    if not meshes:raise ValueError(f'{name} geometry asset contains no meshes')
    # Imported assets must be ALICE global axes, in the declared unit. Root2blend may swap axes;
    # export aligned assets in the documented global convention before using them.
    factor=.01 if settings['geometry_units']=='cm' else 1.
    roots=[o for o in objects if o.parent not in objects]
    for obj in roots:obj.location*=factor;obj.scale*=factor
    bpy.context.view_layer.update()
    # hide_set is local to a view layer and is lost when library objects are
    # linked into this scene. Keep Geometry Nodes helpers hidden in the viewport
    # while retaining their data for the visible instancer.
    for obj in objects:
        if obj.hide_render:obj.hide_set(True)
    track_region=None
    if settings.get('clip_tracks',True) and name in settings['detectors']:
        from track_bounds import bounds
        stat=path.stat();cache_key=(str(path.resolve()),stat.st_size,stat.st_mtime_ns,settings['geometry_units'])
        if cache_key not in BOUND_CACHE:BOUND_CACHE[cache_key]=bounds(objects,name)
        track_region=BOUND_CACHE[cache_key]
    if bounds_only:
        remove_owned_collection(coll)
        return track_region
    lod={}
    style=settings.get('geometry_display',{}).get(name,'surfaces')
    coll['alice_display']=style;coll['alice_geometry_lod']=settings.get('geometry_lod','full')
    if style=='outline' and settings['cutaway'] and name not in settings.get('geometry_openings',{}):
        settings=dict(settings,geometry_openings={**settings.get('geometry_openings',{}),name:180})
    if settings.get('geometry_lod')=='simplified' or style!='surfaces':
        from simplified import simplify
        objects,lod=simplify(objects,coll,name);meshes=objects
    if style!='surfaces':
        from geometry_display import display_geometry
        objects,display_info=display_geometry(objects,coll,name,style);lod.update(display_info);meshes=objects
    mat=materials(name,settings.get('colors_linear',{}).get('magnet' if name=='L3' else name,rgb(settings['colors']['magnet' if name=='L3' else name])),settings.get('geometry_opacities',{}).get(name,settings['geometry_opacity']),settings=settings)
    physical_cut=settings['cutaway'] and name not in settings.get('geometry_openings',{})
    # A 180-degree opening has an exact plane cut. Final Cycles renders use
    # that physical cut for full surfaces, as in the reference images, avoiding
    # long chains of invisible negative-Y geometry. Editing retains the shader
    # wedge so opening angles can change without losing the other half.
    if not settings.get('_interactive') and style=='surfaces' and settings.get('geometry_lod','full')=='full' and settings.get('geometry_openings',{}).get(name)==180:
        physical_cut=True
    for obj in meshes:
        for poly in getattr(obj.data,'polygons',[]):poly.use_smooth=settings.get('shading','smooth')=='smooth' and not lod
    crossing_count=0;discarded_count=0
    def clip_mesh(mesh,matrix):
        import bmesh
        mesh.materials.clear();mesh.materials.append(mat)
        mesh.transform(matrix)
        bm=bmesh.new();bm.from_mesh(mesh)
        bmesh.ops.bisect_plane(bm,geom=[*bm.verts,*bm.edges,*bm.faces],dist=1.e-7,
            plane_co=(0,0,0),plane_no=(0,1,0),clear_inner=True)
        bm.to_mesh(mesh);bm.free();mesh.update()
    for obj in meshes:
        obj.data.materials.clear();obj.data.materials.append(mat)
        if physical_cut and 'num_instances' in obj:
            # Keep compact instances wholly behind the cut. Only crossing
            # instances need separate meshes, clipped in ALICE global Y.
            from mathutils import Euler, Matrix
            group=obj.modifiers['GeometryNodes'].node_group
            instance=next(n for n in group.nodes if n.bl_idname=='GeometryNodeInstanceOnPoints')
            points_node=instance.inputs['Points'].links[0].from_node
            shape_node=instance.inputs['Instance'].links[0].from_node
            points_object=points_node.inputs['Object'].default_value
            prototype=shape_node.inputs['Object'].default_value
            points=points_object.data
            corners=[Vector(c) for c in prototype.bound_box]
            rotations=points.attributes['rot_euler'].data;scales=points.attributes['instance_scale'].data
            keep=[]
            for i,point in enumerate(points.vertices):
                matrix=Euler(rotations[i].vector,'XYZ').to_matrix() @ Matrix.Diagonal(scales[i].vector)
                pose=matrix.to_4x4();pose.translation=point.co
                pose=obj.matrix_world@pose
                ys=[(pose@c).y for c in corners]
                positive=min(ys)>=-1.e-6;negative=max(ys)<-1.e-6
                keep.append(positive)
                if negative:discarded_count+=1
                elif not positive:
                    mesh=prototype.data.copy();clip_mesh(mesh,pose)
                    clipped=bpy.data.objects.new(obj.name+' cut '+str(i),mesh);coll.objects.link(clipped)
                    crossing_count+=1
            attribute=points.attributes.new('alice_cutaway_keep','BOOLEAN','POINT')
            attribute.data.foreach_set('value',keep)
            selection=group.nodes.new('GeometryNodeInputNamedAttribute');selection.data_type='BOOLEAN'
            selection.inputs['Name'].default_value='alice_cutaway_keep'
            group.links.new(selection.outputs['Attribute'],instance.inputs['Selection'])
        elif physical_cut and not obj.hide_render:
            from mathutils import Matrix
            mesh=obj.data.copy();clip_mesh(mesh,obj.matrix_world)
            obj.data=mesh;obj.parent=None;obj.matrix_world=Matrix.Identity(4)
    return {**lod,'track_region':track_region,'meshes':len(meshes),'cutaway_crossing_instances':crossing_count,
            'cutaway_discarded_instances':discarded_count,
            'cutaway_method':'ALICE global Y>=0 mesh clipping' if physical_cut else 'shader wedge' if name in settings.get('geometry_openings',{}) else 'none'}

def render(job_path,interactive=False):
    job=json.loads(Path(job_path).read_text());settings=job['settings'];output=Path(job['output'])
    if interactive:settings['_interactive']=True
    path=Path(job['event'])
    with (gzip.open(path,'rt') if path.suffix=='.gz' else path.open()) as stream:event=json.load(stream)
    bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
    scene=bpy.context.scene;scene.render.engine='CYCLES'
    scene.cycles.samples=settings['samples'];scene.cycles.use_denoising=settings['denoise']
    # Aligned detectors contain many nested surfaces. Cycles' default eight
    # transparent bounces turn cutaway/opacity rays black before they reach data.
    scene.cycles.transparent_max_bounces=128
    backend=settings['backend'];prefs=bpy.context.preferences.addons['cycles'].preferences
    if backend=='CPU':scene.cycles.device='CPU'
    else:
        prefs.compute_device_type=backend;prefs.get_devices();selected=[]
        for d in prefs.devices:
            d.use=d.type==backend and (not settings['device'] or d.id==settings['device'])
            if d.use:selected.append(d.name)
        if not selected:raise RuntimeError(f'No selected {backend} device is available')
        scene.cycles.device='GPU'
    if settings['threads']>0:scene.render.threads_mode='FIXED';scene.render.threads=settings['threads']
    scene.render.resolution_x=settings['width'];scene.render.resolution_y=settings['height'];scene.render.resolution_percentage=100
    scene.render.image_settings.file_format='PNG';scene.render.image_settings.color_mode='RGBA';scene.render.image_settings.color_depth='16'
    scene.render.filepath=str(output/'render.png')
    scene.world.use_nodes=True
    scene.world.node_tree.nodes['Background'].inputs[0].default_value=(*settings.get('colors_linear',{}).get('background',rgb(settings['colors']['background'])),1)
    scene.world.node_tree.nodes['Background'].inputs[1].default_value=settings.get('world_strength',.45)
    selected=set(settings['detectors'])
    ts=[t for t in event['tracks'] if selected.intersection(t['detectors'])]
    cs=[c for c in event['clusters'] if c['detector'] in selected]
    metadata={'event_id':event['id'],'kind':event['kind'],'source_warnings':event.get('warnings',[]),'rendered_tracks':0,'rendered_clusters':0,'geometry':{},'coordinates':'ALICE global XYZ, converted from centimetres to metres'}
    regions={}
    from alice_renderer.track_clipping import selected_track_detectors
    required={d for t in ts for d in selected_track_detectors(settings,t)} if settings.get('clip_tracks',True) and settings['mode']!='clusters' else set()
    for name in settings['geometry']+(['L3'] if settings['magnet'] else []):
        if settings['schematic']:
            envelope(name,settings);metadata['geometry'][name]={'type':'schematic'}
        else:
            info=imported_geometry(name,settings['geometry_assets'][name],settings)
            region=info.pop('track_region',None)
            if region:regions[name]=region
            metadata['geometry'][name]={'type':'asset','path':settings['geometry_assets'][name],**info}
    for name in required-set(regions):
        asset=settings['geometry_assets'].get(name)
        if asset and not settings['schematic']:regions[name]=imported_geometry(name,asset,settings,bounds_only=True)
        elif settings['schematic'] or event['kind']=='synthetic':
            # Explicitly approximate demo/envelope bounds; real data never falls back to them.
            inner,outer,length=ENVELOPES[name];z=ZPOSITIONS.get(name,0.)
            from track_bounds import DIRECTIONS
            planes=[[*n,outer if i<64 else z+length/2 if i==64 else -z+length/2] for i,n in enumerate(DIRECTIONS.tolist())]
            regions[name]={'planes':planes,'units':'cm','basis':'explicit schematic/demo outer envelope'}
        else:raise ValueError(name+': aligned geometry is required to clip tracks to the selected detector')
    settings['_track_regions']=regions
    metadata['track_clipping']={'enabled':settings.get('clip_tracks',True),'regions':regions,'basis':'selected source detectors; outer extent mask, not active-volume selection'}
    if settings['mode']!='clusters':
        metadata['track_legend']=tracks(ts,settings);metadata['rendered_tracks']=metadata['track_legend']['visible_tracks']
    if interactive or settings['mode']!='tracks':metadata['cluster_legend']=clusters(cs,settings);metadata['rendered_clusters']=len(cs)
    az,el=map(math.radians,(settings['azimuth'],settings['elevation']))
    target=Vector([v*.01 for v in settings['target_cm']]);distance=settings['distance_cm']*.01
    position=target+Vector((distance*math.cos(el)*math.cos(az),distance*math.cos(el)*math.sin(az),distance*math.sin(el)))
    bpy.ops.object.camera_add(location=position);camera=bpy.context.object;camera.name='Event camera'
    # ALICE's vertical axis is Y and its beam axis is Z. Use global Y as
    # camera up so detector/event views have the expected physical orientation.
    from mathutils import Matrix
    direction=(target-position).normalized();vertical=Vector((0,1,0))
    if abs(direction.dot(vertical))>.999:vertical=Vector((0,0,1))
    right=direction.cross(vertical).normalized();up=right.cross(direction)
    camera.rotation_euler=Matrix(((right.x,up.x,-direction.x),(right.y,up.y,-direction.y),(right.z,up.z,-direction.z))).to_euler()
    camera.data.lens=48;camera.data.clip_end=2000
    metadata['camera_up']='ALICE global +Y'
    if settings['camera']=='orthographic':camera.data.type='ORTHO';camera.data.ortho_scale=distance*.65
    if settings.get('camera_pose'):
        pose=settings['camera_pose'];camera.matrix_world=Matrix(pose['matrix_world'])
        camera.data.type='ORTHO' if settings['camera']=='orthographic' else 'PERSP'
        camera.data.lens=pose['lens'];camera.data.ortho_scale=pose['ortho_scale']
    camera.data.sensor_fit='HORIZONTAL'
    scene.camera=camera
    for i,light in enumerate(settings['lights']):
        bpy.ops.object.light_add(type='AREA',location=light['position_m']);lamp=bpy.context.object;lamp.name='ALICE light '+str(i+1)
        lamp.data.energy=light['energy'];lamp.data.shape='DISK';lamp.data.size=light['size_m'];lamp.data.color=light.get('color_linear',rgb(light['color']))
        lamp.rotation_euler=light.get('rotation') or (target-lamp.location).to_track_quat('-Z','Y').to_euler()
    scene.view_settings.view_transform='AgX'
    metadata['settings']={k:v for k,v in settings.items() if not k.startswith('_')};metadata['source']=job['event'];metadata['blender_version']=bpy.app.version_string
    (output/'metadata.json').write_text(json.dumps(metadata,indent=2))
    if interactive:
        from editor import start_editor
        settings.pop('_interactive',None)
        settings.pop('_track_regions',None)
        job['track_regions']=regions
        start_editor(job,event,metadata)
        return
    if settings['save_blend']:bpy.ops.wm.save_as_mainfile(filepath=str(output/'scene.blend'))
    bpy.ops.render.render(write_still=True)

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--probe');parser.add_argument('--job');parser.add_argument('--interactive',action='store_true')
    args=parser.parse_args(sys.argv[sys.argv.index('--')+1:])
    if args.probe:probe(args.probe)
    elif args.job:render(args.job,args.interactive)
    else:parser.error('Specify --probe or --job')

if __name__=='__main__':main()
