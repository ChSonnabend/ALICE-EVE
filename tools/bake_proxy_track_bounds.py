"""Bake exact full-source clipping bounds once, never from approximate meshes."""
import sys,argparse,gzip,json
from pathlib import Path
sys.path[:0]=[str(Path(__file__).resolve().parents[1]/'src'),str(Path(__file__).resolve().parents[1]/'src/alice_renderer/blender')]
import bpy
from track_bounds import bounds
from surface_builder import write
from alice_renderer.surface_proxy import sidecar_path
p=argparse.ArgumentParser();p.add_argument('--geometry-root',type=Path,required=True);a=p.parse_args(sys.argv[sys.argv.index('--')+1:])
for asset in sorted(a.geometry_root.glob('*.blend')):
 path=sidecar_path(asset)
 if not path.exists():continue
 data=json.load(gzip.open(path,'rt'))
 if data.get('track_region'):continue
 with bpy.data.libraries.load(str(asset),link=False) as (source,target):target.objects=source.objects
 objects=[o for o in target.objects if o]
 for obj in objects:bpy.context.scene.collection.objects.link(obj)
 if data['source_units']=='cm':
  for obj in objects:
   if obj.parent not in objects:obj.location*=.01;obj.scale*=.01
 bpy.context.view_layer.update();data['track_region']=bounds(objects,asset.stem);write(path,data)
 print('BOUNDS_COMPLETE',asset.stem,flush=True)
 for obj in objects:bpy.data.objects.remove(obj,do_unlink=True)
 bpy.data.orphans_purge(do_recursive=True)
