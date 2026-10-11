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
    cfg=RenderSettings(detectors=['TPC'],geometry=['TPC'],geometry_assets={'TPC':str(a.asset.resolve())},geometry_units='m',geometry_lod='full',geometry_openings={'TPC':180},cutaway=False)
    job=root/'job.json';job.write_text(json.dumps({'event':str(event),'output':str(root),'settings':cfg.to_dict(),'blender':{'version':list(bpy.app.version),'devices':[{'type':'CPU'}]}}))
    worker.render(job,True);ui=bpy.context.scene.alice_eve;item=ui.detectors.get('TPC')
    assert ui.geometry_lod=='full'
    assert any('num_instances' in o for o in bpy.data.collections['TPC'].objects)
    assert all(o.hide_get() for o in bpy.data.collections['TPC'].objects if o.hide_render)
    assert all(m.surface_render_method=='BLENDED' for o in bpy.data.collections['TPC'].objects if o.type=='MESH' for m in o.data.materials)
    assert bpy.ops.alice_eve.apply_data()=={'FINISHED'}
    for style,kind in [('outline','CURVE'),('shell','MESH')]:
        item.display=style;assert bpy.ops.alice_eve.apply_geometry()=={'FINISHED'}
        assert any(o.type==kind for o in bpy.data.collections['TPC'].objects)
        ui.export_path=str(root/(style+'.json'));assert bpy.ops.alice_eve.export()=={'FINISHED'}
        assert json.loads(Path(ui.export_path).read_text())['scene']['geometry_display']['TPC']==style
    assert bpy.ops.alice_eve.opaque_geometry()=={'FINISHED'} and item.opacity==1
    assert bpy.ops.alice_eve.full_geometry()=={'FINISHED'}
    assert ui.geometry_lod=='full' and item.display=='surfaces'
    assert all(o.hide_get() for o in bpy.data.collections['TPC'].objects if o.hide_render)
print('Blender geometry visibility, styles, opacity, data and export QA passed')
