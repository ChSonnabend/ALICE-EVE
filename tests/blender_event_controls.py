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
        {'id':'2','source':'TPC','detectors':['TPC'],'association':{'ambiguous':True,'pv_contributor':False},'points':[[-20,40,0],[20,40,0]]},
        {'id':'3','source':'ITS-TPC','detectors':['ITS','TPC'],'points':[[-20,0,0],[20,0,0]]}],
        'clusters':[{'id':'a','detector':'ITS','position':[0,0,0],'track_id':'3'},
                    {'id':'b','detector':'TPC','position':[0,40,0],'track_id':'2'}]}))
    cfg=RenderSettings(detectors=['ITS','TPC'],detector_modes={'ITS':'clusters','TPC':'tracks'},schematic=True,
        include_ambiguous_tracks=True,track_color_mode='matching',cluster_color_mode='matching',palette='transferred',palette_lut=[[0,0,1],[1,0,0]],
        highlight_track_ids=['3'],highlight_track_radius_cm=.6,highlight_cluster_radius_cm=1.5,
        highlight_override_color=False,elevation=90,roll=73)
    job=root/'job.json';job.write_text(json.dumps({'event':str(event),'output':str(root),'settings':cfg.to_dict(),
        'library_path':str(root/'history.sqlite'),'blender':{'version':list(bpy.app.version),'devices':[{'type':'CPU'}]}}))
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
    ui.include_ambiguous_tracks=False;assert bpy.ops.alice_eve.apply_data()=={'FINISHED'}
    assert {i for o in bpy.data.collections['Tracks'].objects for i in json.loads(o['alice_track_ids_json'])}=={'3'}
    assert sum(len(o.data.vertices) for o in bpy.data.collections['Clusters'].objects)==1
    assert not editor.current_settings().include_ambiguous_tracks
    ui.include_ambiguous_tracks=True;assert bpy.ops.alice_eve.apply_data()=={'FINISHED'}
    ui.export_path=str(root/'scene.json');assert bpy.ops.alice_eve.export()=={'FINISHED'}
    saved=json.loads(Path(ui.export_path).read_text())['scene']
    assert saved['detector_modes']['ITS']=='clusters' and saved['detector_modes']['TPC']=='both'
    assert saved['highlight_track_ids']==['3'] and saved['palette_lut']==cfg.palette_lut
    assert saved['camera_pose']['matrix_world']==[list(row) for row in camera.matrix_world]
    editor.save_session()
    from alice_renderer.scene_library import SceneLibrary
    library=SceneLibrary(root/'history.sqlite')
    assert library.entries()[0]['event']=='SYNTHETIC-CONTROLS-QA'
    assert library.settings(library.entries()[0]).camera_pose['matrix_world']==saved['camera_pose']['matrix_world']
    assert saved['color_ranges']['tracks']==[0.,1.]
    ui.view_transform='Standard';ui.exposure=-.5;ui.track_emission=.2;ui.cluster_emission=.8
    assert bpy.context.scene.view_settings.view_transform=='Standard'
    assert bpy.context.scene.view_settings.exposure==-.5
    for name,expected in (('Tracks',.2),('Clusters',.8)):
        for obj in bpy.data.collections[name].objects:
            materials=list(obj.data.materials)
            for modifier in obj.modifiers:
                if modifier.type=='NODES':materials.extend(n.inputs['Material'].default_value for n in modifier.node_group.nodes if n.bl_idname=='GeometryNodeSetMaterial')
            assert materials
            assert all(abs(m.node_tree.nodes['Principled BSDF'].inputs['Emission Strength'].default_value-expected)<1.e-6 for m in materials)
            assert all(m.cycles.emission_sampling=='NONE' for m in materials)
    ui.data_glow_lighting=True
    assert all(m.cycles.emission_sampling=='AUTO' for m in bpy.data.materials if m.name.startswith(('Track ','Cluster ')))
    assert editor.current_settings().data_glow_lighting
    assert editor.current_settings().view_transform=='Standard'
    ui.view_transform='AgX';ui.exposure=0

    assert bpy.context.preferences.inputs.view_rotate_method=='TRACKBALL'
    assert 'stop' in bpy.ops.alice_eve.pick_tracks.get_rna_type().description.lower()
    ui.picking_active=True
    # The sidebar overlays WINDOW. A click on Stop must reach the UI handler.
    window=SimpleNamespace(type='WINDOW',x=0,y=0,width=1000,height=700)
    sidebar=SimpleNamespace(type='UI',x=750,y=0,width=250,height=700)
    picking_area=SimpleNamespace(regions=[window,sidebar],spaces=SimpleNamespace(active=SimpleNamespace(show_region_ui=True)))
    click=SimpleNamespace(type='LEFTMOUSE',value='PRESS',mouse_x=900,mouse_y=100)
    picker=SimpleNamespace(area=picking_area,region=window)
    assert editor.PickTracks.modal(picker,bpy.context,click)=={'PASS_THROUGH'}
    assert editor.PickTracks.description(bpy.context,None).startswith('Stop selecting')
    assert 'stop' in bpy.ops.alice_eve.stop_picking.get_rna_type().description.lower()
    assert bpy.ops.alice_eve.stop_picking()=={'FINISHED'}
    assert not ui.picking_active
    assert editor.PickTracks.description(bpy.context,None).startswith('Click a displayed')
    # Exercise the full-render choices and exact config passed to the subprocess.
    from unittest.mock import patch
    bpy.types.Scene.alice_render_detail_qa=bpy.props.CollectionProperty(type=editor.RenderGeometryDetail)
    for name in ('TPC','L3'):
        ui.detectors[name].geometry_available=True;ui.detectors[name].visible=True
    operator=SimpleNamespace(geometry_details=bpy.context.scene.alice_render_detail_qa,quality='draft',backend='CPU',output=str(root/'render-output'),report=lambda *args:None)
    editor.initialize_render_geometry(operator,editor.current_settings())
    assert {i.name:i.detail for i in operator.geometry_details}=={'TPC':'full','L3':'full'}
    operator.geometry_details['TPC'].detail='simplified'
    operator.geometry_details['L3'].detail='full'
    # Config/launch contract fixtures; actual aligned assets are covered separately.
    for name in ('TPC','L3'):
        asset=root/(name+'.blend');asset.write_bytes(b'config-contract-only')
        editor.JOB['settings']['geometry_assets'][name]=str(asset)
        ui.detectors[name].asset_path=str(asset)
    editor.JOB['python']=sys.executable
    original=editor.current_settings().geometry_lods
    operator.geometry_preset='simplified';editor.render_geometry_preset_update(operator,bpy.context)
    assert {i.name:i.detail for i in operator.geometry_details}=={'TPC':'simplified','L3':'simplified'}
    operator.geometry_preset='current';editor.render_geometry_preset_update(operator,bpy.context)
    assert {i.name:i.detail for i in operator.geometry_details}=={'TPC':'current','L3':'current'}
    operator.geometry_details['TPC'].detail='simplified';operator.geometry_details['L3'].detail='full'
    assert editor.render_geometry_settings(editor.current_settings(),[],preset='simplified').geometry_lods=={'TPC':'simplified','L3':'simplified'}
    with patch('alice_renderer.render_jobs.submit',return_value='test-job') as spawn:
        assert bpy.ops.alice_eve.render_full(quality='draft',resolution_percent=50,backend='CPU',output=operator.output,
            geometry_details=[{'name':i.name,'detail':i.detail} for i in operator.geometry_details])=={'FINISHED'}
        command=spawn.call_args.args[0]
        assert float(command[command.index('--resolution-percent')+1])==50
        assert command[command.index('--geometry-detail')+1]=='current'
        rendered=json.loads(Path(command[command.index('render-config')+1]).read_text())['scene']
    assert rendered['geometry_lods']=={'TPC':'simplified','L3':'full'}
    assert rendered['geometry_schematics']=={'TPC':False,'L3':False}
    assert rendered['geometry_display']['TPC']=='surfaces'
    assert editor.current_settings().geometry_lods==original
    del bpy.types.Scene.alice_render_detail_qa
    assert ui.detectors['ITS'].event_track_count==2
    assert ui.detectors['TPC'].event_cluster_count==1
    # Sidebar is a UI region; capture must override to the WINDOW region.
    viewport=next(a for a in bpy.context.screen.areas if a.type=='VIEW_3D')
    sidebar=next(r for r in viewport.regions if r.type=='UI');view=viewport.spaces.active.region_3d
    view.view_perspective='CAMERA';before=camera.matrix_world.copy()
    with bpy.context.temp_override(area=viewport,region=sidebar):
        assert bpy.ops.alice_eve.camera_from_view()=={'FINISHED'}
    assert camera.matrix_world==before
    from mathutils import Euler,Vector
    view.view_perspective='PERSP';view.view_rotation=Euler((.3,.4,.5)).to_quaternion();view.view_distance=12
    with bpy.context.temp_override(area=viewport,region=sidebar):
        assert bpy.ops.alice_eve.camera_from_view()=={'FINISHED'}
    bpy.context.view_layer.update()
    assert abs(camera.matrix_world.to_quaternion().dot(view.view_rotation))>1-1.e-6
    direction=camera.rotation_euler.to_matrix() @ Vector((0,0,-1));position=camera.location.copy()
    assert bpy.ops.alice_eve.level_camera()=={'FINISHED'}
    assert camera.location==position
    matrix=camera.rotation_euler.to_matrix()
    assert (matrix @ Vector((0,0,-1))-direction).length<1.e-6
    assert abs((matrix @ Vector((1,0,0))).y)<1.e-6
    # Wheel-style zoom in camera view must change the render camera, not frame inspection.
    window_region=next(r for r in viewport.regions if r.type=='WINDOW')
    viewport.spaces.active.lock_camera=True;view.view_perspective='CAMERA'
    bpy.ops.ed.undo_push(message='Camera navigation QA baseline')
    before=camera.matrix_world.copy();frame_zoom=view.view_camera_zoom
    def span(matrix):
        projection=camera.calc_matrix_camera(bpy.context.evaluated_depsgraph_get(),x=1920,y=1080) @ matrix.inverted()
        points=[projection @ Vector((x,0,0,1)) for x in (-1,1)]
        return ((points[0]/points[0].w)-(points[1]/points[1].w)).length
    original_span=span(before)
    with bpy.context.temp_override(area=viewport,region=window_region):
        assert bpy.ops.view3d.zoom(delta=2)=={'FINISHED'}
    bpy.context.view_layer.update()
    assert camera.matrix_world!=before
    assert span(camera.matrix_world)>original_span
    assert view.view_camera_zoom==frame_zoom
    assert editor.current_settings().camera_pose['matrix_world']==[list(row) for row in camera.matrix_world]
    # Preserve all projection parameters across export and a fresh render camera.
    from camera_pose import snapshot,restore
    camera.data.lens=94;camera.data.sensor_width=43;camera.data.sensor_height=29;camera.data.sensor_fit='VERTICAL'
    camera.data.shift_x=.12;camera.data.shift_y=-.09
    clone=bpy.data.objects.new('Camera framing QA',bpy.data.cameras.new('Camera framing QA'))
    for projection in ('PERSP','ORTHO'):
        camera.data.type=projection;clone.data.type=projection;restore(clone,snapshot(camera))
        a=camera.calc_matrix_camera(bpy.context.evaluated_depsgraph_get(),x=1920,y=1080)
        b=clone.calc_matrix_camera(bpy.context.evaluated_depsgraph_get(),x=7680,y=4320)
        assert max(abs(a[r][c]-b[r][c]) for r in range(4) for c in range(4))<1.e-6
        assert clone.matrix_world==camera.matrix_world
print('Blender per-detector objects, matching, emphasis, picking, roll and portable export QA passed')
