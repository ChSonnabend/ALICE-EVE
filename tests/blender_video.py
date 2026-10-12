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
        event=validate_event(event);events.append(event);path=root/(str(i)+'.json');path.write_text(json.dumps(event));paths.append(str(path))
    cfg=RenderSettings(video_enabled=True,video_interval_s=4,video_fps=8,video_speed_m_s=1,video_tower_rise_s=1,detectors=['TPC','EMC'],mode='both',schematic=True,calorimeter_display={'EMC':'signal towers'})
    plan=schedule(events,cfg.to_dict());payload=dict(event=paths[0],events=paths,video_headers=[header(e) for e in events],video_plan=plan,output=str(root),settings=cfg.to_dict(),required_track_detectors=['TPC'],library_path=str(root/'history.sqlite'),blender={'version':list(bpy.app.version),'devices':[{'type':'CPU'}]})
    job=root/'job.json';job.write_text(json.dumps(payload));worker.render(job,True)
    player=editor.JOB['video_player'];assert player.playing
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
    assert sum(len(mesh_vertices(o)) for o in bpy.data.collections['Tracks'].objects)==0
    assert all(c.get('track_id','1')=='1' for c in editor.EVENT['clusters'])
    bpy.ops.alice_eve.play_video();assert player.playing
    player.set_frame(63);player.anchor=time.monotonic()-plan['duration_s']-.001
    player.timer();assert player.index==0 and player.frame==0
    bpy.ops.alice_eve.stop_video();f=player.frame;assert not player.playing and player.frame==f
    group_count=len(bpy.data.node_groups)
    for frame in (0,32)*3:player.set_frame(frame)
    assert len(bpy.data.node_groups)==group_count
    assert editor.current_settings().video_enabled
    # Native button handoff preserves all input paths outside the portable recipe.
    from unittest.mock import patch
    editor.JOB['python']=sys.executable;editor.JOB['ffmpeg']='/portable/encoder'
    with patch('alice_renderer.runtime.check_encoder',return_value='/portable/encoder'),patch.object(editor.subprocess,'Popen') as spawn:
        assert bpy.ops.alice_eve.render_full(quality='draft',resolution_percent=1,backend='CPU',output=str(root/'movies'))=={'FINISHED'}
        command=spawn.call_args.args[0]
        assert json.loads(Path(command[command.index('--event-files')+1]).read_text())==paths
        assert command[command.index('--ffmpeg')+1]=='/portable/encoder'
        config=json.loads(Path(command[command.index('render-config')+1]).read_text())
        assert config['scene']['video_enabled'] and not config['defaults']
        assert 'events' not in config
    print('COLLISION VIDEO BLENDER QA PASSED')
