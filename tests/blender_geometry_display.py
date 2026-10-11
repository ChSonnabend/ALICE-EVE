"""Optional Blender integration QA using an externally supplied aligned TPC asset.

blender --background --factory-startup --python-exit-code 1 \
  --python tests/blender_geometry_display.py -- --asset /path/TPC.blend
No data/geometry fixture is stored in Git and the supplied asset is read-only.
"""
import argparse,json,sys,tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src/alice_renderer/blender'))
import bpy,worker
from alice_renderer.model import RenderSettings

p=argparse.ArgumentParser();p.add_argument('--asset',type=Path,required=True)
a=p.parse_args(sys.argv[sys.argv.index('--')+1:])
with tempfile.TemporaryDirectory(prefix='alice-geometry-qa-') as tmp:
    root=Path(tmp);event=root/'event.json'
    event.write_text(json.dumps({'id':'SYNTHETIC-QA','kind':'synthetic','tracks':[{'id':'1','detectors':['TPC'],'points':[[0,0,0],[20,20,30]],'kinematics':{}}],'clusters':[]}))
    cfg=RenderSettings(detectors=['TPC'],geometry=[],geometry_assets={'TPC':str(a.asset.resolve())},geometry_units='m',geometry_opacity=1.,geometry_lod='full',geometry_openings={'TPC':180},cutaway=False)
    job=root/'job.json';job.write_text(json.dumps({'event':str(event),'output':str(root),'settings':cfg.to_dict(),'blender':{'version':list(bpy.app.version),'devices':[{'type':'CPU'}]}}))
    worker.render(job,True);ui=bpy.context.scene.alice_eve;item=ui.detectors.get('TPC')
    recorded=json.loads((root/'metadata.json').read_text())['camera']['matrix_world']
    actual=bpy.context.scene.camera.matrix_world
    assert max(abs(recorded[r][c]-actual[r][c]) for r in range(4) for c in range(4))<1.e-6
    assert abs(recorded[0][2])+abs(recorded[1][2])>0.1
    assert ui.viewport_renderer=='CYCLES' and bpy.context.scene.cycles.preview_samples==128
    assert item.geometry_available and not item.visible
    assert bpy.data.collections.get('TPC') is None
    assert not ui.detectors['TRD'].geometry_available
    item.visible=True;assert bpy.ops.alice_eve.apply_geometry()=={'FINISHED'}
    assert 'TPC' in __import__('editor').current_settings().geometry
    assert ui.geometry_lod=='full'
    assert any('num_instances' in o for o in bpy.data.collections['TPC'].objects)
    assert all(o.hide_get() for o in bpy.data.collections['TPC'].objects if o.hide_render)
    assert all(m.surface_render_method=='DITHERED' for o in bpy.data.collections['TPC'].objects if o.type=='MESH' for m in o.data.materials)
    item.opacity=.25
    assert all(m.surface_render_method=='BLENDED' and not m.use_transparency_overlap for o in bpy.data.collections['TPC'].objects if o.type=='MESH' for m in o.data.materials)
    assert bpy.ops.alice_eve.solid_surfaces()=={'FINISHED'} and item.opacity==1
    assert all(m.surface_render_method=='DITHERED' for o in bpy.data.collections['TPC'].objects if o.type=='MESH' for m in o.data.materials)
    camera=bpy.context.scene.camera;camera_pose=camera.matrix_world.copy()
    assert bpy.ops.alice_eve.light_transparent_surfaces()=={'FINISHED'}
    assert abs(item.opacity-.035)<1.e-6 and item.detail=='full' and item.display=='surfaces'
    assert camera.matrix_world==camera_pose
    item.exclusions='TPC_IFC*';item.inner_mask_radius=1.
    assert bpy.ops.alice_eve.restore_surface_exclusions()=={'FINISHED'}
    assert item.exclusions=='' and item.inner_mask_radius==0 and camera.matrix_world==camera_pose
    assert bpy.ops.alice_eve.tpc_sectors_inner_wall()=={'FINISHED'}
    from editor import current_settings
    choices=current_settings().geometry_components['TPC']
    assert choices['parts/TPC_ICVM'] and choices['parts/TPC_IROCB']
    assert not choices['parts/TPC_OCV'] and not choices['parts/TPC_ring']
    assert camera.matrix_world==camera_pose
    light_count=len([o for o in bpy.context.scene.objects if o.type=='LIGHT'])
    assert bpy.ops.alice_eve.surround_lighting()=={'FINISHED'}
    assert bpy.ops.alice_eve.surround_lighting()=={'FINISHED'}
    assert len([o for o in bpy.context.scene.objects if o.type=='LIGHT'])==light_count+10
    from alice_renderer.scene_presets import SURROUND_LIGHT_PREFIX
    from mathutils import Vector
    target=Vector(tuple(v*.01 for v in cfg.target_cm))
    rig=[o for o in bpy.context.scene.objects if o.name.startswith(SURROUND_LIGHT_PREFIX)]
    assert len(rig)==10 and camera.matrix_world==camera_pose
    for light in rig:
        direction=light.rotation_euler.to_matrix() @ Vector((0,0,-1))
        assert direction.dot((target-light.location).normalized())>.99999
    ui.export_path=str(root/'surround.json');assert bpy.ops.alice_eve.export()=={'FINISHED'}
    exported=json.loads(Path(ui.export_path).read_text())['scene']
    assert sum(light.get('name','').startswith(SURROUND_LIGHT_PREFIX) for light in exported['lights'])==10
    assert exported['geometry_components']['TPC']==choices
    ui.viewport_samples=192
    assert bpy.context.scene.cycles.preview_samples==192 and bpy.context.scene.cycles.use_preview_denoising
    assert bpy.context.scene.eevee.taa_samples==192
    ui.viewport_renderer='CYCLES';assert bpy.context.scene.render.engine=='CYCLES'
    ui.viewport_renderer='BLENDER_EEVEE';assert bpy.context.scene.render.engine=='BLENDER_EEVEE'
    ui.track_width_cm=.5
    assert all(abs(o.data.bevel_depth-.0025)<1.e-8 for o in bpy.data.collections['Tracks'].objects)
    assert bpy.ops.alice_eve.apply_data()=={'FINISHED'}
    curve_count=len(bpy.data.curves)
    for _ in range(3):assert bpy.ops.alice_eve.apply_data()=={'FINISHED'}
    assert len(bpy.data.curves)==curve_count
    for style,kind in [('outline','CURVE'),('shell','MESH')]:
        item.display=style;assert bpy.ops.alice_eve.apply_geometry()=={'FINISHED'}
        assert any(o.type==kind for o in bpy.data.collections['TPC'].objects)
        ui.export_path=str(root/(style+'.json'));assert bpy.ops.alice_eve.export()=={'FINISHED'}
        assert json.loads(Path(ui.export_path).read_text())['scene']['geometry_display']['TPC']==style
    assert bpy.ops.alice_eve.opaque_geometry()=={'FINISHED'} and item.opacity==1
    assert bpy.ops.alice_eve.full_geometry()=={'FINISHED'}
    assert ui.geometry_lod=='full' and item.display=='surfaces'
    assert all(o.hide_get() for o in bpy.data.collections['TPC'].objects if o.hide_render)
    assert bpy.ops.alice_eve.complete_geometry()=={'FINISHED'}
    assert item.opening==0
    for o in bpy.data.collections['TPC'].objects:
        if o.type=='MESH':
            for material in o.data.materials:
                node=material.node_tree.nodes.get('ALICE opening')
                if node:assert node.inputs[1].default_value==0
    assert bpy.ops.alice_eve.select_no_detectors()=={'FINISHED'}
    assert not any(i.data or i.visible for i in ui.detectors)
    assert not bpy.data.collections['Tracks'].objects
    ui.export_path=str(root/'none.json');assert bpy.ops.alice_eve.export()=={'FINISHED'}
    data=json.loads(Path(ui.export_path).read_text());assert data['scene']['detectors']==[] and data['scene']['geometry']==[]
    assert data['scene']['track_radius_cm']==.25
    # Overrides reach actual aligned asset processing in both directions.
    from worker import imported_geometry,remove_owned_collection
    for global_lod,override in [('full','simplified'),('simplified','full')]:
        old=bpy.data.collections.get('TPC')
        if old:remove_owned_collection(old)
        settings=cfg.to_dict();settings['geometry_lod']=global_lod;settings['geometry_lods']={'TPC':override}
        imported_geometry('TPC',str(a.asset.resolve()),settings)
        coll=bpy.data.collections['TPC'];assert coll['alice_geometry_lod']==override
        if override=='simplified':assert any(o.get('alice_lod')=='simplified' for o in coll.objects)
        else:assert any('num_instances' in o for o in coll.objects)
print('Blender geometry visibility, styles, opacity, data and export QA passed')
