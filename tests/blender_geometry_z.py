"""Native Blender QA: world Z material cuts and persistent live scene buffers."""
import json,sys,tempfile,math
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src/alice_renderer/blender'))
import bpy,worker,editor
from alice_renderer.model import RenderSettings
from alice_renderer.runtime import geometry_only_input
with tempfile.TemporaryDirectory(prefix='alice-z-qa-') as tmp:
    root=Path(tmp);event=geometry_only_input(root)
    cfg=RenderSettings(detectors=[],geometry=['ITS','TPC'],schematic=True,geometry_openings={'ITS':90,'TPC':120},geometry_z_intervals_cm={'ITS':[-20,40]},beampipe=True)
    payload=dict(event=str(event),output=str(root),settings=cfg.to_dict(),library_path=str(root/'history.sqlite'),blender={'version':list(bpy.app.version),'devices':[{'type':'CPU'}]})
    job=root/'job.json';job.write_text(json.dumps(payload));worker.render(job,True)
    ui=bpy.context.scene.alice_eve
    def buffers():return {(c,o.name):(o.as_pointer(),o.data.as_pointer()) for c in ['ITS','TPC','Beampipe'] for o in bpy.data.collections[c].objects}
    before=buffers();item=next(d for d in ui.detectors if d.name=='TPC');item.z_clip=True;item.z_min_cm=-85;item.z_max_cm=35;item.opening=145
    editor.appearance_update(ui,bpy.context)
    item.opening_z_clip=True;item.opening_z_min_cm=-27.11;item.opening_z_max_cm=12.89
    assert buffers()==before
    mat=next(o.data.materials[0] for o in bpy.data.collections['TPC'].objects)
    nodes=mat.node_tree.nodes
    assert abs(nodes['ALICE z minimum'].inputs[1].default_value+.85)<1.e-6
    assert abs(nodes['ALICE z maximum'].inputs[1].default_value-.35)<1.e-6
    assert abs(nodes['ALICE opening'].inputs[1].default_value-math.radians(145)/2)<1.e-6
    assert abs(nodes['ALICE opening z minimum'].inputs[1].default_value+.2711)<1.e-6
    assert abs(nodes['ALICE opening z maximum'].inputs[1].default_value-.1289)<1.e-6
    geom=next(n for n in nodes if n.type=='NEW_GEOMETRY');assert geom.outputs['Position'].is_linked
    saved=editor.current_settings();assert saved.geometry_z_intervals_cm['TPC']==[-85,35] and saved.beampipe
    item.z_clip=False;assert nodes['ALICE z minimum'].inputs[1].default_value<-1.e9
    ui.beampipe_color=(.001,0,.2);assert buffers()==before
    ui.beampipe=False;assert bpy.data.collections['Beampipe'].hide_render
    ui.beampipe=True;assert buffers()==before
    pipe=next(iter(bpy.data.collections['Beampipe'].objects));assert len(pipe.data.polygons)==512
    assert {round(v.co.z,3) for v in pipe.data.vertices}=={-4.5,4.5}
    assert len([p for p in pipe.data.polygons if p.use_smooth])==256
    assert abs(editor.current_settings().geometry_opening_z_intervals_cm['TPC'][0]+27.11)<1.e-4
    bpy.ops.mesh.primitive_cube_add(size=2);cube=bpy.context.object
    asset=root/'native.blend';bpy.data.libraries.write(str(asset),{cube});bpy.data.objects.remove(cube,do_unlink=True)
    native=RenderSettings(detectors=[],geometry=['FDD'],geometry_units='m',geometry_openings={'FDD':180},geometry_opening_z_intervals_cm={'FDD':[-20,20]})
    info=worker.imported_geometry('FDD',asset,native.to_dict())
    assert 'mesh clipping' in info['cutaway_method']
    obj=next(iter(bpy.data.collections['FDD'].objects))
    assert min(v.co.y for v in obj.data.vertices)<-.99 and max(v.co.y for v in obj.data.vertices)>.99
    # The removed half is present outside the window, absent within it.
    for face in obj.data.polygons:
        center=face.center
        assert not (-.19<center.z<.19 and center.y<-.01)
    assert any(v.co.y<-.99 and v.co.z>.99 for v in obj.data.vertices)
    print('World Z + angular cut, config serialization, hollow pipe and live mesh persistence QA passed')
