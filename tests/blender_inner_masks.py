"""Optional native QA; supply --asset TPC.blend. Never renders an image."""
import argparse,bpy,math,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src/alice_renderer/blender'))
import worker
from alice_renderer.model import RenderSettings
p=argparse.ArgumentParser();p.add_argument('--asset',type=Path,required=True)
args=p.parse_args(sys.argv[sys.argv.index('--')+1:])
cfg=RenderSettings(detectors=['TPC'],geometry=['TPC'],geometry_units='m',geometry_openings={'TPC':0},geometry_opening_directions={'TPC':28},geometry_inner_masks={'TPC':{'radius_m':1.,'patterns':['TPC_mrod*','TPC_rod*','TPC_ring*','TPC_bcon*'],'front_only':True}})
info=worker.imported_geometry('TPC',args.asset,cfg.to_dict());assert sum(info['inner_masked_instances'].values())>0
outer=inner=0
for obj in bpy.data.collections['TPC'].objects:
    if 'num_instances' not in obj or obj.name not in info['inner_masked_instances']:continue
    group=obj.modifiers['GeometryNodes'].node_group
    inst=next(n for n in group.nodes if n.bl_idname=='GeometryNodeInstanceOnPoints')
    points=inst.inputs['Points'].links[0].from_node.inputs['Object'].default_value.data
    for i,v in enumerate(points.vertices):
        q=obj.matrix_world@v.co;keep=points.attributes['alice_inner_mask_keep'].data[i].value
        if math.hypot(q.x,q.y)>1:assert keep;outer+=1
        elif q.x*math.cos(math.radians(28))+q.y*math.sin(math.radians(28))>0:assert not keep;inner+=1
assert outer and inner
original_bounds=info['track_region'];worker.remove_owned_collection(bpy.data.collections['TPC'])
cfg.geometry_lod='simplified';coarse=worker.imported_geometry('TPC',args.asset,cfg.to_dict())
assert coarse['track_region']==original_bounds and coarse['surface_cells']>0
print('Inner masks retained outer placements, removed front inner placements and preserved clipping bounds in full/simplified modes')
