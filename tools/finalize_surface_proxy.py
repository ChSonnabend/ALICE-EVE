"""Install a reviewed cache; complete ITS service shells omitted by legacy cache.

Run inside Blender. The five candidate images remain unchanged as review evidence.
"""
import sys,json,gzip,copy,argparse
from pathlib import Path
sys.path[:0]=[str(Path(__file__).resolve().parents[1]/'src'),str(Path(__file__).resolve().parents[1]/'src/alice_renderer/blender')]
import bpy,numpy as np
from surface_builder import reduce_mesh,write
from structural_builder import placements,rotation,merge
from alice_renderer.geometry_components import load_components
from alice_renderer.surface_proxy import sidecar_path
p=argparse.ArgumentParser();p.add_argument('--asset',type=Path,required=True);p.add_argument('--candidate',type=Path,required=True);a=p.parse_args(sys.argv[sys.argv.index('--')+1:])
data=json.load(gzip.open(a.candidate,'rt'))
if a.asset.stem=='ITS':
 metadata=load_components(a.asset)
 with bpy.data.libraries.load(str(a.asset),link=False) as (source,target):target.objects=source.objects
 objects=[o for o in target.objects if o]
 for obj in objects:bpy.context.scene.collection.objects.link(obj)
 bpy.context.view_layer.update();groups={}
 for obj in objects:
  if 'num_instances' not in obj:continue
  entry=metadata['groups'][obj.name];prototype,p,angles,scales=placements(obj)
  # Preserve the broad support/cage/service silhouette, not duplicated stave
  # electronics or microscopic fasteners. Source tags and placements retained.
  eligible=[not any(t.startswith('layers/') for t in tags) and bool(set(tags)&{'structures/supports','structures/cage','structures/services'}) for tags in entry['classes']]
  if not any(eligible):continue
  extent=np.ptp(np.array(prototype.bound_box),axis=0)
  if sorted(extent)[-2]<.035:continue
  v,f=reduce_mesh(prototype.data,384);world=np.array(obj.matrix_world)
  for i,(pos,angle,scale) in enumerate(zip(p,angles,scales)):
   tags=entry['classes'][entry['ids'][i]]
   if not eligible[entry['ids'][i]]:continue
   key=(obj.name,tuple(tags));group=groups.setdefault(key,dict(name=obj.name,source_names=[obj.name],tags=tags,vertices=[],faces=[],elements=0))
   r=rotation(angle,scale,obj.matrix_world);xyz=v@r.T+world[:3,:3]@pos+world[:3,3]
   merge(group,xyz,[face[::-1] for face in f] if np.linalg.det(r)<0 else f);group['elements']+=1
 data['groups'].extend(groups.values());data['post_review_correction']='Added broad native ITS support/cage/service shells missing from legacy structural cache; validate in combined scene'
 data['faces']=sum(len(g['faces']) for g in data['groups']);data['vertices']=sum(len(g['vertices']) for g in data['groups'])
 data['retained_instances']=sum(g['elements'] for g in data['groups'])
write(sidecar_path(a.asset),data)
print(json.dumps({'cache':str(sidecar_path(a.asset)),'faces':data['faces'],'meshes':len(data['groups'])}))
