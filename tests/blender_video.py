"""Native QA: clipped propagation, delayed hits, growing towers, replacement, stop."""
import json,sys,tempfile,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src/alice_renderer/blender'))
import bpy,worker,editor
from alice_renderer.model import RenderSettings,validate_event
from alice_renderer.video import schedule,header

def mesh_vertices(obj):
    evaluated=obj.evaluated_get(bpy.context.evaluated_depsgraph_get());mesh=evaluated.to_mesh()
    result=[v.co.copy() for v in mesh.vertices];evaluated.to_mesh_clear();return result

def realized_vertices(obj):
    tree=obj.modifiers[0].node_group;out=next(n for n in tree.nodes if n.bl_idname=='NodeGroupOutput')
    source=out.inputs['Geometry'].links[0].from_socket
    node=tree.nodes.new('GeometryNodeRealizeInstances');tree.links.new(source,node.inputs['Geometry']);tree.links.new(node.outputs['Geometry'],out.inputs['Geometry'])
    bpy.context.view_layer.update();result=mesh_vertices(obj)
    tree.nodes.remove(node);tree.links.new(source,out.inputs['Geometry']);bpy.context.view_layer.update();return result

with tempfile.TemporaryDirectory(prefix='alice-video-qa-') as tmp:
    root=Path(tmp);paths=[];events=[]
    for i in range(2):
        event=dict(schema_version=1,units='cm',kind='synthetic',id='VIDEO-QA-'+str(i),vertex=[0,i,0],tracks=[dict(id=str(i),detectors=['TPC'],points=[[0,i,0],[100,i,0],[200,i,0]])],clusters=[dict(id='hit',detector='TPC',position=[100,i,0],track_id=str(i)),dict(id='cell',detector='EMC',position=[200,i,0],energy=2,cell_geometry=dict(u_cm=[0,6,0],v_cm=[0,0,6],basis='aligned test face'))])
        if i==1:event['tracks'][0]['features']={'late_feature':7};event['clusters']=event['clusters'][:1]
        event=validate_event(event);events.append(event);path=root/(str(i)+'.json');path.write_text(json.dumps(event));paths.append(str(path))
    cfg=RenderSettings(video_enabled=True,video_interval_s=4,video_fps=8,video_speed_m_s=1,video_tower_rise_s=1,detectors=['TPC','EMC'],geometry=['TPC','EMC'],mode='both',schematic=True,calorimeter_display={'EMC':'signal towers'})
    plan=schedule(events,cfg.to_dict());payload=dict(event=paths[0],events=paths,video_headers=[header(e) for e in events],video_plan=plan,output=str(root),settings=cfg.to_dict(),required_track_detectors=['TPC'],library_path=str(root/'history.sqlite'),blender={'version':list(bpy.app.version),'devices':[{'type':'CPU'}]})
    job=root/'job.json';job.write_text(json.dumps(payload));worker.render(job,True)
    player=editor.JOB['video_player'];assert player.playing
    ui=bpy.context.scene.alice_eve;assert bpy.context.scene.render.use_persistent_data
    detector_buffers={(name,o.name):(o.as_pointer(),o.data.as_pointer()) for name in cfg.geometry for o in bpy.data.collections[name].objects}
    assert 'feature:late_feature' in {x[0] for x in editor.COLOR_ITEMS}
    bpy.ops.alice_eve.pause_viewport();assert ui.viewport_paused and bpy.context.scene.cycles.preview_pause and player.playing
    bpy.ops.alice_eve.pause_viewport();assert not ui.viewport_paused and not bpy.context.scene.cycles.preview_pause
    ui.viewport_renderer='BLENDER_EEVEE';bpy.ops.alice_eve.pause_viewport()
    views=[a.spaces.active for s in bpy.data.screens for a in s.areas if a.type=='VIEW_3D']
    assert views and all(s.shading.type=='SOLID' for s in views)
    bpy.ops.alice_eve.pause_viewport();assert all(s.shading.type=='RENDERED' for s in views)
    ui.viewport_renderer='CYCLES'
    from unittest.mock import patch
    with patch('video_player.time.monotonic',return_value=100.):player.hold_controls(True);f=player.frame
    with patch('video_player.time.monotonic',return_value=110.):player.timer();assert player.frame==f;old_anchor=player.anchor;player.hold_controls(False)
    assert player.held_at is None and abs(player.anchor-old_anchor-10)<1e-5
    from types import SimpleNamespace
    sidebar=SimpleNamespace(type='UI',x=750,y=0,width=250,height=700)
    area=SimpleNamespace(type='VIEW_3D',spaces=SimpleNamespace(active=SimpleNamespace(show_region_ui=True)),regions=[sidebar])
    screen=SimpleNamespace(areas=[area]);context=SimpleNamespace(scene=bpy.context.scene,window=SimpleNamespace(screen=screen))
    watcher=SimpleNamespace(job=editor.JOB)
    assert editor.WatchPlaybackControls.modal(watcher,context,SimpleNamespace(type='MOUSEMOVE',mouse_x=800,mouse_y=100))=={'PASS_THROUGH'}
    assert player.held_at is None
    editor.WatchPlaybackControls.modal(watcher,context,SimpleNamespace(type='LEFTMOUSE',value='PRESS',mouse_x=800,mouse_y=100))
    assert player.held_at is not None
    player.timer();assert player.frame==f
    bpy.ops.alice_eve.play_video();assert player.playing and player.held_at is None
    editor.WatchPlaybackControls.modal(watcher,context,SimpleNamespace(type='MOUSEMOVE',mouse_x=100,mouse_y=100));assert player.held_at is None
    bpy.ops.alice_eve.stop_video();assert not player.playing and not bpy.context.scene.alice_eve.video_playing
    player.regions={'TPC':dict(planes=[[1,0,0,150],[-1,0,0,-50],[0,1,0,10],[0,-1,0,10],[0,0,1,10],[0,0,-1,10]],units='cm')}
    player.index=-1;player.set_frame(2)
    assert sum(len(mesh_vertices(o)) for o in bpy.data.collections['Tracks'].objects)==0
    spheres=next(o for o in bpy.data.collections['Clusters'].objects if not o.get('alice_towers'))
    assert not realized_vertices(spheres)
    player.set_frame(8)
    verts=[v for o in bpy.data.collections['Tracks'].objects for v in mesh_vertices(o)]
    assert verts and min(v.x for v in verts)>=.50 and max(v.x for v in verts)<=1.001
    tower=next(o for o in bpy.data.collections['Clusters'].objects if o.get('alice_towers'))
    assert not mesh_vertices(tower)
    player.set_frame(9);assert realized_vertices(spheres)
    player.set_frame(20);tower=next(o for o in bpy.data.collections['Clusters'].objects if o.get('alice_towers'));verts=mesh_vertices(tower)
    assert verts and abs((max(v.x for v in verts)-min(v.x for v in verts))-.2)<.001
    player.set_frame(25);verts=mesh_vertices(tower)
    assert abs((max(v.x for v in verts)-min(v.x for v in verts))-.4)<.001
    player.set_frame(32);assert player.event['id']=='VIDEO-QA-1'
    assert ui.detectors['EMC'].data_available and ui.detectors['EMC'].data and ui.detectors['EMC'].mode=='both'
    assert ui.detectors['EMC'].event_cluster_count==0 and ui.detectors['EMC'].cell_display=='signal towers'
    assert 'feature:late_feature' in {x[0] for x in editor.COLOR_ITEMS}
    assert sum(len(mesh_vertices(o)) for o in bpy.data.collections['Tracks'].objects)==0
    assert all(c.get('track_id','1')=='1' for c in editor.EVENT['clusters'])
    bpy.ops.alice_eve.play_video();assert player.playing
    player.set_frame(63);player.anchor=time.monotonic()-plan['duration_s']-.001
    player.timer();assert player.index==0 and player.frame==0
    bpy.ops.alice_eve.stop_video();f=player.frame;assert not player.playing and player.frame==f
    group_count=len(bpy.data.node_groups)
    for frame in (32,0)*3:player.set_frame(frame)
    assert len(bpy.data.node_groups)==group_count
    assert detector_buffers=={(name,o.name):(o.as_pointer(),o.data.as_pointer()) for name in cfg.geometry for o in bpy.data.collections[name].objects}
    assert editor.current_settings().video_enabled
    # Native button handoff preserves all input paths outside the portable recipe.
    from unittest.mock import patch
    editor.JOB['python']=sys.executable;editor.JOB['ffmpeg']='/portable/encoder'
    with patch('alice_renderer.runtime.check_encoder',return_value='/portable/encoder'),patch.object(editor.subprocess,'Popen') as spawn:
        assert bpy.ops.alice_eve.render_full(quality='draft',resolution_percent=1,backend='CPU',output=str(root/'movies'),geometry_details=[{'name':d,'detail':'current'} for d in cfg.geometry])=={'FINISHED'}
        command=spawn.call_args.args[0]
        assert json.loads(Path(command[command.index('--event-files')+1]).read_text())==paths
        assert command[command.index('--ffmpeg')+1]=='/portable/encoder'
        config=json.loads(Path(command[command.index('render-config')+1]).read_text())
        assert config['scene']['video_enabled'] and not config['defaults']
        assert 'events' not in config
    print('COLLISION VIDEO BLENDER QA PASSED')
