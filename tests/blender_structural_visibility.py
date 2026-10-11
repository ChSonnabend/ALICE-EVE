"""Native geometry QA with tiny synthetic assets; never renders an image."""
import sys,tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src/alice_renderer/blender'))
import bpy,worker
from alice_renderer.model import RenderSettings

with tempfile.TemporaryDirectory(prefix='alice-structures-qa-') as tmp:
    bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
    for name,position in [('plus',(1,0,0)),('minus',(-1,0,0)),('service',(0,2,0))]:
        bpy.ops.mesh.primitive_cube_add(size=.4,location=position);bpy.context.object.name=name
    path=Path(tmp)/'TPC.blend';bpy.data.libraries.write(str(path),set(bpy.context.scene.objects))
    bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
    cfg=RenderSettings(detectors=['TPC'],geometry=['TPC'],geometry_units='m',geometry_openings={'TPC':180},geometry_opening_directions={'TPC':0},geometry_exclusions={'TPC':['service*']})
    original=worker.imported_geometry('TPC',path,cfg.to_dict(),bounds_only=True)
    info=worker.imported_geometry('TPC',path,cfg.to_dict())
    assert info['track_region']==original
    assert info['exclusion_patterns']==['service*'] and info['excluded_objects']
    assert info['cutaway_method']=='ALICE global oriented plane clipping'
    coll=bpy.data.collections['TPC']
    assert all(o.hide_render for o in coll.objects if o.name.startswith('service'))
    remaining=[o for o in coll.objects if not o.hide_render and len(o.data.vertices)]
    assert remaining and all((o.matrix_world@v.co).x<=1.e-6 for o in remaining for v in o.data.vertices)
    mat=next(o.data.materials[0] for o in remaining)
    assert mat.node_tree.nodes['ALICE opening direction'].inputs[1].default_value==0
print('Structural visibility and oriented cut QA passed without rendering')
