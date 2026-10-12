"""Blender batch QA: full reference and five 1920x1080 native-surface candidates."""
import sys,json,gzip,time,math,argparse
from pathlib import Path
sys.path[:0]=[str(Path(__file__).resolve().parents[1]/'src'),str(Path(__file__).resolve().parents[1]/'src/alice_renderer/blender')]
import bpy
from mathutils import Vector
from surface_builder import bake
from worker import materials,rgb

p=argparse.ArgumentParser();p.add_argument('--asset',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--selected-only',action='store_true');a=p.parse_args(sys.argv[sys.argv.index('--')+1:]);name=a.asset.stem
bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
objects=[] if a.selected_only else bake(a.asset,a.output)
meta=json.loads((a.output/'source.json').read_text());low,high=map(Vector,meta['bounds_m']);target=(low+high)/2;span=high-low;size=max(span)
# Frame an isolated detector with beam Z diagonal. Far-forward separated modules
# retain their true positions; the report includes numeric source bounds.
scene=bpy.context.scene;scene.render.engine='BLENDER_EEVEE';scene.eevee.taa_render_samples=16;scene.eevee.use_raytracing=False
scene.render.resolution_x=1920;scene.render.resolution_y=1080;scene.render.resolution_percentage=100
scene.render.image_settings.file_format='PNG';scene.render.image_settings.color_mode='RGB';scene.render.image_settings.color_depth='8'
scene.world.use_nodes=True;scene.world.node_tree.nodes['Background'].inputs[0].default_value=(.025,.025,.025,1);scene.world.node_tree.nodes['Background'].inputs[1].default_value=.5
scene.view_settings.view_transform='Standard';scene.view_settings.look='None'
bpy.ops.object.camera_add(location=target+Vector((.95,.65,1.2))*size);camera=bpy.context.object;camera.rotation_euler=(target-camera.location).to_track_quat('-Z','Y').to_euler();camera.data.type='ORTHO';camera.data.clip_end=max(2000,size*10)
camera.data.ortho_scale=max(size*1.45,1.e-3);scene.camera=camera
# Fit all projected bounds, including long forward assemblies.
bpy.context.view_layer.update();inv=camera.matrix_world.inverted();corners=[inv@Vector((x,y,z)) for x in (low.x,high.x) for y in (low.y,high.y) for z in (low.z,high.z)]
camera.data.ortho_scale=max(max(v.x for v in corners)-min(v.x for v in corners),(max(v.y for v in corners)-min(v.y for v in corners))*1920/1080)*1.15
for pos,energy in [((1,2,2),180),((-1,1,-1),100)]:
 bpy.ops.object.light_add(type='AREA',location=target+Vector(pos)*size);light=bpy.context.object;light.data.energy=energy*size*size;light.data.shape='DISK';light.data.size=size;light.rotation_euler=(target-light.location).to_track_quat('-Z','Y').to_euler()
openings={name:100} if name in ('ITS','TPC','TRD','TOF','L3') else {}
settings={'roughness':.6,'metallic':0,'geometry_openings':openings,'geometry_opening_directions':{name:25}}
mat=materials(name,rgb('#45b9cf'),.65,settings=settings)
for obj in objects:
 if obj.type=='MESH':obj.data.materials.clear();obj.data.materials.append(mat)
start=time.monotonic();scene.render.filepath=str(a.output/'reference.png')
if not a.selected_only:bpy.ops.render.render(write_still=True)
report={'detector':name,'resolution':[1920,1080],'reference_seconds':round(time.monotonic()-start,3),'source_instances':meta['source_instances'],'bounds_m':meta['bounds_m'],'opening_degrees':openings.get(name,0),'opacity':.65,'candidates':[]}
for obj in objects:bpy.data.objects.remove(obj,do_unlink=True)
for attempt in ([0] if a.selected_only else range(1,6)):
 data=json.load(gzip.open(Path(str(a.asset)+'.surface.json.gz') if a.selected_only else a.output/f'candidate-{attempt}.json.gz','rt'));built=[];start=time.monotonic()
 for group in data['groups']:
  mesh=bpy.data.meshes.new(group['name']);mesh.from_pydata(group['vertices'],[],group['faces']);mesh.update();mesh.materials.append(mat)
  obj=bpy.data.objects.new(group['name'],mesh);scene.collection.objects.link(obj);built.append(obj)
 load_seconds=time.monotonic()-start;scene.render.filepath=str(a.output/('selected-validation.png' if a.selected_only else f'try-{attempt}.png'));start=time.monotonic();bpy.ops.render.render(write_still=True)
 report['candidates'].append({'attempt':attempt,'faces':data['faces'],'vertices':data['vertices'],'meshes':len(data['groups']),'retained_instances':data['retained_instances'],'load_seconds':round(load_seconds,4),'render_seconds':round(time.monotonic()-start,3)})
 for obj in built:
  mesh=obj.data;bpy.data.objects.remove(obj,do_unlink=True);bpy.data.meshes.remove(mesh)
 (a.output/('selected-validation-metrics.json' if a.selected_only else 'review-metrics.json')).write_text(json.dumps(report,indent=2))
 print('CANDIDATE_COMPLETE',name,attempt,flush=True)
