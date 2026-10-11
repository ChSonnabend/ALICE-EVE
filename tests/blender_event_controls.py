"""Optional native Blender QA: blender -b --factory-startup --python-exit-code 1 --python tests/blender_event_controls.py."""
import json,sys,tempfile
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src/alice_renderer/blender'))
import bpy,worker,editor
from mathutils import Matrix
from alice_renderer.model import RenderSettings

with tempfile.TemporaryDirectory(prefix='alice-controls-qa-') as tmp:
    root=Path(tmp);event=root/'event.json'
    event.write_text(json.dumps({'id':'SYNTHETIC-CONTROLS-QA','kind':'synthetic','tracks':[
        {'id':'1','source':'ITS','detectors':['ITS'],'points':[[-20,-40,0],[20,-40,0]]},
        {'id':'2','source':'TPC','detectors':['TPC'],'points':[[-20,40,0],[20,40,0]]},
        {'id':'3','source':'ITS-TPC','detectors':['ITS','TPC'],'points':[[-20,0,0],[20,0,0]]}],
        'clusters':[{'id':'a','detector':'ITS','position':[0,0,0],'track_id':'3'},
                    {'id':'b','detector':'TPC','position':[0,40,0],'track_id':'2'}]}))
    cfg=RenderSettings(detectors=['ITS','TPC'],detector_modes={'ITS':'clusters','TPC':'tracks'},schematic=True,
        track_color_mode='matching',cluster_color_mode='matching',palette='transferred',palette_lut=[[0,0,1],[1,0,0]],
        highlight_track_ids=['3'],highlight_track_radius_cm=.6,highlight_cluster_radius_cm=1.5,
        highlight_override_color=False,elevation=90,roll=73)
    job=root/'job.json';job.write_text(json.dumps({'event':str(event),'output':str(root),'settings':cfg.to_dict(),
        'blender':{'version':list(bpy.app.version),'devices':[{'type':'CPU'}]}}))
    worker.render(job,True);ui=bpy.context.scene.alice_eve
    tracks=bpy.data.collections['Tracks'].objects
    assert {i for o in tracks for i in json.loads(o['alice_track_ids_json'])}=={'2','3'}
    assert all(abs(o.data.bevel_depth-(.006 if o['alice_highlighted'] else .0012))<1.e-7 for o in tracks)
    clusters=bpy.data.collections['Clusters'].objects
    assert sum(len(o.data.vertices) for o in clusters)==1
    assert all(o['alice_highlighted'] for o in clusters)
    radii=[n.inputs['Radius'].default_value for o in clusters for n in o.modifiers[0].node_group.nodes if n.bl_idname=='GeometryNodeMeshIcoSphere']
    assert radii and all(abs(r-.015)<1.e-7 for r in radii)
    # Project the actual displayed curve through a simple known viewport.
    area=SimpleNamespace(spaces=SimpleNamespace(active=SimpleNamespace(region_3d=SimpleNamespace(perspective_matrix=Matrix.Identity(4)))))
    region=SimpleNamespace(width=100,height=100)
    assert editor.pick_displayed_track(area,region,(50,50))=='3'
    assert editor.pick_displayed_track(area,region,(50,70))=='2'
    for obj in tracks:
        bsdf=obj.data.materials[0].node_tree.nodes['Principled BSDF']
        expected=(1,0,0) if obj['alice_highlighted'] else (0,0,1)
        assert tuple(bsdf.inputs['Base Color'].default_value[:3])==expected
    ui.highlight_override=True;assert bpy.ops.alice_eve.apply_data()=={'FINISHED'}
    special=next(o for o in bpy.data.collections['Tracks'].objects if o['alice_highlighted'])
    assert max(abs(a-b) for a,b in zip(special.data.materials[0].node_tree.nodes['Principled BSDF'].inputs['Base Color'].default_value[:3],worker.rgb(cfg.highlight_track_color)))<1.e-6
    camera=bpy.context.scene.camera;before=camera.matrix_world.copy()
    assert bpy.ops.alice_eve.roll_camera(angle=31)=={'FINISHED'}
    bpy.context.view_layer.update();expected=before @ Matrix.Rotation(__import__('math').radians(31),4,'Z')
    assert max(abs(camera.matrix_world[r][c]-expected[r][c]) for r in range(4) for c in range(4))<1.e-6
    ui.detectors['TPC'].mode='both';assert bpy.ops.alice_eve.apply_data()=={'FINISHED'}
    assert sum(len(o.data.vertices) for o in bpy.data.collections['Clusters'].objects)==2
    ui.export_path=str(root/'scene.json');assert bpy.ops.alice_eve.export()=={'FINISHED'}
    saved=json.loads(Path(ui.export_path).read_text())['scene']
    assert saved['detector_modes']['ITS']=='clusters' and saved['detector_modes']['TPC']=='both'
    assert saved['highlight_track_ids']==['3'] and saved['palette_lut']==cfg.palette_lut
    assert saved['camera_pose']['matrix_world']==[list(row) for row in camera.matrix_world]
    assert saved['color_ranges']['tracks']==[0.,1.]
    assert bpy.context.preferences.inputs.view_rotate_method=='TRACKBALL'
print('Blender per-detector objects, matching, emphasis, picking, roll and portable export QA passed')
