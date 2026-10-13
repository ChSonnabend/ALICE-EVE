"""Geometry-node collision playback shared by viewport and movie rendering."""
import json,math,time,gzip,shutil,subprocess
from pathlib import Path
import numpy as np
import bpy
from alice_renderer.video import prepare_event,schedule,event_at
from alice_renderer.track_clipping import prepare_regions,clip_polyline,selected_track_detectors

def attribute(mesh,name,values,kind='FLOAT'):
    data=mesh.attributes.new(name,kind,'POINT').data
    data.foreach_set('vector' if kind=='FLOAT_VECTOR' else 'value',np.asarray(values,dtype=np.float32).ravel())

def named(nodes,name,kind='FLOAT'):
    node=nodes.new('GeometryNodeInputNamedAttribute');node.data_type=kind;node.inputs['Name'].default_value=name;return node.outputs['Attribute']

def clock(nodes):
    node=nodes.new('ShaderNodeValue');node.name='ALICE video seconds';node.outputs[0].default_value=0.;return node.outputs[0]

def math_node(nodes,links,operation,a,b):
    node=nodes.new('ShaderNodeMath');node.operation=operation
    for socket,value in zip(node.inputs,(a,b)):
        if isinstance(value,(int,float)):socket.default_value=value
        else:links.new(value,socket)
    return node.outputs[0]

def animate_spheres(mesh,nodes,links,instance,items):
    attribute(mesh,'alice_arrival_s',[c['_video_arrival_s'] for c in items])
    visible=math_node(nodes,links,'GREATER_THAN',clock(nodes),named(nodes,'alice_arrival_s'))
    links.new(visible,instance.inputs['Selection'])

def animate_towers(obj,arrivals,rise_s):
    mesh=obj.data;coordinates=np.asarray([v.co[:] for v in mesh.vertices]);base=coordinates.reshape(-1,8,3)[:,:4,:]
    base=np.concatenate((base,base),axis=1).reshape(-1,3)
    attribute(mesh,'alice_tower_base',base,'FLOAT_VECTOR');attribute(mesh,'alice_tower_offset',coordinates-base,'FLOAT_VECTOR')
    attribute(mesh,'alice_arrival_s',np.repeat(arrivals,8))
    tree=bpy.data.node_groups.new('Video tower growth','GeometryNodeTree')
    tree.interface.new_socket(name='Geometry',in_out='INPUT',socket_type='NodeSocketGeometry');tree.interface.new_socket(name='Geometry',in_out='OUTPUT',socket_type='NodeSocketGeometry')
    n,l=tree.nodes,tree.links;input_=n.new('NodeGroupInput');output=n.new('NodeGroupOutput');now=clock(n);arrival=named(n,'alice_arrival_s')
    elapsed=math_node(n,l,'SUBTRACT',now,arrival);growth=math_node(n,l,'DIVIDE',elapsed,rise_s)
    growth=math_node(n,l,'MINIMUM',math_node(n,l,'MAXIMUM',growth,0.),1.)
    scale=n.new('ShaderNodeVectorMath');scale.operation='SCALE';l.new(named(n,'alice_tower_offset','FLOAT_VECTOR'),scale.inputs[0]);l.new(growth,scale.inputs['Scale'])
    position=n.new('ShaderNodeVectorMath');position.operation='ADD';l.new(named(n,'alice_tower_base','FLOAT_VECTOR'),position.inputs[0]);l.new(scale.outputs['Vector'],position.inputs[1])
    setpos=n.new('GeometryNodeSetPosition');l.new(input_.outputs['Geometry'],setpos.inputs['Geometry']);l.new(position.outputs['Vector'],setpos.inputs['Position'])
    delete=n.new('GeometryNodeDeleteGeometry');delete.domain='FACE';l.new(setpos.outputs['Geometry'],delete.inputs['Geometry'])
    invisible=math_node(n,l,'LESS_THAN',elapsed,1e-8);l.new(invisible,delete.inputs['Selection']);l.new(delete.outputs['Geometry'],output.inputs['Geometry'])
    obj.modifiers.new('Video tower growth','NODES').node_group=tree

def growing_tracks(data,settings):
    from worker import collection,buckets,materials
    coll=collection('Tracks');groups,legend=buckets(data['tracks'],settings['track_color_mode'],settings['colors']['tracks'],settings,'tracks')
    regions=prepare_regions(settings.get('_track_regions',{}));pieces_for_picking=[];visible=0
    for key,group in groups.items():
        radius=settings['highlight_track_radius_cm'] if group['highlighted'] else settings['track_radius_cm']
        vertices=[];edges=[];starts=[]
        for track in group['items']:
            points,distances=data['paths'][str(track['id'])];names=selected_track_detectors(settings,track)
            pieces=clip_polyline(points,[regions[d] for d in names if d in regions],margin_cm=radius,distances=distances)
            visible+=bool(pieces)
            for piece in pieces:
                offset=len(vertices);p=np.asarray(piece['points'])*.01;vertices.extend(p.tolist());edges.extend((offset+i,offset+i+1) for i in range(len(p)-1));starts.extend([piece['distances'][0]*.01]*len(p))
                pieces_for_picking.append((str(track['id']),np.asarray(piece['points']),np.asarray(piece['distances'])))
        if not edges:continue
        mesh=bpy.data.meshes.new('Video tracks '+key);mesh.from_pydata(vertices,edges,[]);mesh.update();attribute(mesh,'alice_start_m',starts)
        obj=bpy.data.objects.new('Tracks '+key,mesh);coll.objects.link(obj);obj['alice_highlighted']=group['highlighted'];obj['alice_video_tracks']=True
        mat=materials('Track '+key,group['color'],emission=settings.get('track_emission',.7),settings=settings)
        tree=bpy.data.node_groups.new('Video tracks '+key,'GeometryNodeTree');tree.interface.new_socket(name='Geometry',in_out='INPUT',socket_type='NodeSocketGeometry');tree.interface.new_socket(name='Geometry',in_out='OUTPUT',socket_type='NodeSocketGeometry')
        n,l=tree.nodes,tree.links;input_=n.new('NodeGroupInput');output=n.new('NodeGroupOutput');curve=n.new('GeometryNodeMeshToCurve');l.new(input_.outputs['Geometry'],curve.inputs['Mesh'])
        front=math_node(n,l,'MULTIPLY',clock(n),settings['video_speed_m_s']);length=math_node(n,l,'SUBTRACT',front,named(n,'alice_start_m'))
        delete=n.new('GeometryNodeDeleteGeometry');delete.domain='CURVE';l.new(curve.outputs['Curve'],delete.inputs['Geometry']);l.new(math_node(n,l,'LESS_THAN',length,1e-8),delete.inputs['Selection'])
        trim=n.new('GeometryNodeTrimCurve');trim.mode='LENGTH';l.new(delete.outputs['Geometry'],trim.inputs['Curve']);l.new(math_node(n,l,'MAXIMUM',length,0.),next(s for s in trim.inputs if s.name=='End' and s.enabled))
        circle=n.new('GeometryNodeCurvePrimitiveCircle');circle.inputs['Resolution'].default_value=8;circle.inputs['Radius'].default_value=radius*.01
        tube=n.new('GeometryNodeCurveToMesh');l.new(trim.outputs['Curve'],tube.inputs['Curve']);l.new(circle.outputs['Curve'],tube.inputs['Profile Curve']);tube.inputs['Fill Caps'].default_value=True
        material=n.new('GeometryNodeSetMaterial');material.inputs['Material'].default_value=mat;l.new(tube.outputs['Mesh'],material.inputs['Geometry']);l.new(material.outputs['Geometry'],output.inputs['Geometry'])
        obj.modifiers.new('Video propagation','NODES').node_group=tree
    legend.update(visible_tracks=visible,clipped_away_tracks=len(data['tracks'])-visible)
    return legend,pieces_for_picking

class VideoPlayer:
    def __init__(self,job,settings,regions):
        self.job=job;self.settings=dict(settings);self.regions=regions;self.plan=job['video_plan'];self.index=-1;self.frame=0;self.age=0.;self.playing=False;self.anchor=0.;self.timer=None;self.pieces=[];self.reports={};self.held_at=None
    def hold_controls(self,hold):
        now=time.monotonic()
        if hold and self.held_at is None:self.held_at=now
        elif not hold and self.held_at is not None:self.anchor+=now-self.held_at;self.held_at=None
    def set_frame(self,frame):
        self.frame=max(0,min(int(frame),self.plan['frames']-1));index,age=event_at(self.plan,self.frame)
        if index!=self.index:self.load(index)
        self.age=age
        for collname in ('Tracks','Clusters'):
            coll=bpy.data.collections.get(collname)
            if coll:
                for obj in coll.objects:
                    for modifier in obj.modifiers:
                        if modifier.type=='NODES':
                            node=modifier.node_group.nodes.get('ALICE video seconds')
                            if node:node.outputs[0].default_value=age
        bpy.context.view_layer.update()
    def load(self,index):
        from worker import remove_owned_collection,clusters,imported_geometry,is_schematic,schematic_region
        entry=self.plan['entries'][index];path=self.job['events'][entry['source_index']]
        with gzip.open(path,'rt') if path.endswith('.gz') else open(path) as stream:self.event=json.load(stream)
        self.index=index;cfg=dict(self.settings);cfg['_video_active']=True;cfg['_track_regions']=dict(self.regions)
        data=prepare_event(self.event,cfg)
        for track in data['tracks']:
            for name in selected_track_detectors(cfg,track):
                if name not in cfg['_track_regions'] or not is_schematic(cfg,name) and cfg['_track_regions'][name].get('basis')=='explicit schematic/demo outer envelope':
                    cfg['_track_regions'][name]=schematic_region(name) if is_schematic(cfg,name) else imported_geometry(name,cfg['geometry_assets'][name],cfg,bounds_only=True)
        self.regions=cfg['_track_regions'];self.job['track_regions']=self.regions
        for collname in ('Tracks','Clusters'):
            old=bpy.data.collections.get(collname)
            if old:remove_owned_collection(old)
        track_legend,self.pieces=growing_tracks(data,cfg)
        for c,arrival in zip(data['clusters'],data['cluster_arrival_s']):c['_video_arrival_s']=float(arrival)
        cluster_legend=clusters(data['clusters'],cfg)
        self.reports[str(self.event['id'])]=dict(linked_clusters=data['linked_clusters'],unlinked_clusters=data['unlinked_clusters'],cluster_timing_basis=data['cluster_timing_basis'])
        self.job['event']=path
        if hasattr(bpy.context.scene,'alice_eve'):
            import editor
            editor.EVENT=self.event;ui=bpy.context.scene.alice_eve;ui.displayed_tracks=track_legend['visible_tracks'];ui.displayed_clusters=len(data['clusters']);ui.video_status=f'Collision {index+1}/{len(self.plan["entries"])}: {self.event["id"]}'
            from alice_renderer.object_selection import event_counts
            counts=event_counts(self.event)
            self.job['input_counts']=counts
            for item in ui.detectors:
                item.event_track_count=counts['tracks_by_detector'].get(item.name,0);item.event_cluster_count=counts['clusters_by_detector'].get(item.name,0)
                info=cluster_legend.get('calorimeter_towers',{}).get(item.name,{})
                item.tower_count=info.get('towers',0);item.tower_point_fallbacks=info.get('point_fallbacks',0);item.tower_nominal_footprints=info.get('approximate_footprints',0)
    def reconfigure(self,settings):
        self.settings=settings.to_dict() if hasattr(settings,'to_dict') else dict(settings);self.settings['clip_tracks']=True
        self.plan=schedule(self.job['video_headers'],self.settings);self.index=-1;self.set_frame(min(self.frame,self.plan['frames']-1));self.anchor=time.monotonic()-self.frame/self.plan['fps']
        if self.held_at is not None:self.held_at=time.monotonic()
    def play(self):
        self.playing=True;self.anchor=time.monotonic()-self.frame/self.plan['fps'];bpy.context.scene.alice_eve.video_playing=True
        if self.held_at is not None:self.held_at=time.monotonic()
        if self.timer:return
        def tick():
            if not self.playing:self.timer=None;return None
            if self.held_at is not None:return 1/self.plan['fps']
            try:
                frame=int((time.monotonic()-self.anchor)*self.plan['fps'])%self.plan['frames'];target,_=event_at(self.plan,frame)
                # Slow disk/scene loads must not skip selected collisions.
                if target!=self.index and target!=(self.index+1)%len(self.plan['entries']):frame=self.plan['entries'][(self.index+1)%len(self.plan['entries'])]['frame_start']
                before=time.monotonic();self.set_frame(frame);self.anchor+=time.monotonic()-before
                for screen in bpy.data.screens:
                    for area in screen.areas:
                        if area.type=='VIEW_3D':area.tag_redraw()
                return 1/self.plan['fps']
            except Exception as exc:
                self.stop();bpy.context.scene.alice_eve.video_status='Playback stopped: '+str(exc);self.timer=None;return None
        self.timer=tick;bpy.app.timers.register(tick,first_interval=1/self.plan['fps'])
    def stop(self):
        self.playing=False
        if self.timer and bpy.app.timers.is_registered(self.timer):bpy.app.timers.unregister(self.timer)
        self.timer=None
        if hasattr(bpy.context.scene,'alice_eve'):bpy.context.scene.alice_eve.video_playing=False
    def visible_paths(self):
        front=self.age*self.settings['video_speed_m_s']*100
        for identity,points,distances in self.pieces:
            if front<=distances[0]:continue
            count=int(np.searchsorted(distances,front,side='right'));p=points[:count]
            if count<len(points):
                lo=distances[count-1];hi=distances[count]
                if hi>lo:p=np.vstack((p,points[count-1]+(points[count]-points[count-1])*(front-lo)/(hi-lo)))
            if len(p)>=2:yield identity,p

def render_movie(job,settings,regions,metadata):
    output=Path(job['output']);player=VideoPlayer(job,settings,regions);plan=player.plan
    if job.get('video_frame') is not None:
        frame=job['video_frame']
        if not 0<=frame<plan['frames']:raise ValueError('Playback frame is outside the video timeline')
        player.set_frame(frame)
        scene=bpy.context.scene;scene.render.filepath=str(output/'render.png')
        if settings.get('save_blend'):bpy.ops.wm.save_as_mainfile(filepath=str(output/'scene.blend'))
        print(f'ALICE_STAGE Rendering stopped frame {frame+1}/{plan["frames"]}',flush=True)
        bpy.ops.render.render(write_still=True)
        metadata['video_frame']={'frame':frame,'fps':plan['fps'],'event':player.event['id'],'age_s':player.age}
        (output/'metadata.json').write_text(json.dumps(metadata,indent=2))
        print('ALICE_FRAME 1/1',flush=True)
        return
    command=[job['ffmpeg'],'-hide_banner','-loglevel','error','-y','-f','image2pipe','-framerate',str(plan['fps']),'-vcodec','png','-i','pipe:0','-an','-vf','pad=ceil(iw/2)*2:ceil(ih/2)*2','-c:v','libx264','-crf','18','-preset','medium','-pix_fmt','yuv420p','-movflags','+faststart',str(output/'video.part.mp4')]
    scene=bpy.context.scene;framefile=output/'frame-current.png';scene.render.image_settings.file_format='PNG';scene.render.image_settings.color_mode='RGBA';scene.render.image_settings.color_depth='8';scene.render.filepath=str(framefile)
    poster=plan['entries'][0]['frame_end']-1
    with (output/'encoder.log').open('w') as log:
        encoder=subprocess.Popen(command,stdin=subprocess.PIPE,stderr=log)
        try:
            for frame in range(plan['frames']):
                player.set_frame(frame);print(f'ALICE_STAGE Rendering video frame {frame+1}/{plan["frames"]}',flush=True);bpy.ops.render.render(write_still=True)
                if frame==poster:shutil.copy2(framefile,output/'render.png')
                if frame==poster and settings.get('save_blend'):bpy.ops.wm.save_as_mainfile(filepath=str(output/'scene.blend'))
                encoder.stdin.write(framefile.read_bytes());encoder.stdin.flush()
                print(f'ALICE_FRAME {frame+1}/{plan["frames"]}',flush=True)
            encoder.stdin.close();code=encoder.wait(timeout=120)
            if code:raise RuntimeError('MP4 encoding failed; see encoder.log')
        except BaseException:
            encoder.terminate()
            try:encoder.wait(timeout=5)
            except subprocess.TimeoutExpired:encoder.kill();encoder.wait()
            raise
    (output/'video.part.mp4').replace(output/'video.mp4');framefile.unlink(missing_ok=True)
    metadata['video']={**plan,'collision_reports':player.reports,'codec':'H.264','crf':18,'static_geometry_reused':True,'persistent_render_data':scene.render.use_persistent_data};(output/'metadata.json').write_text(json.dumps(metadata,indent=2))
    (output/'video-timeline.json').write_text(json.dumps(metadata['video'],indent=2))
    print('ALICE_STAGE Video saved: '+str(output/'video.mp4'),flush=True)
