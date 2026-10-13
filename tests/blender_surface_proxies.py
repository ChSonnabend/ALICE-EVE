"""Native Blender integration: all ALICE2 cached surfaces, no source instancers.

blender -b --factory-startup --python-exit-code 1 --python tests/blender_surface_proxies.py -- --assets geometry/run-560067
"""
import sys,json,tempfile,argparse,time
from pathlib import Path
sys.path[:0]=[str(Path(__file__).resolve().parents[1]/'src'),str(Path(__file__).resolve().parents[1]/'src/alice_renderer/blender')]
import bpy,worker
from alice_renderer.model import RenderSettings
from alice_renderer.runtime import fast_editor_settings,geometry_only_input
p=argparse.ArgumentParser();p.add_argument('--assets',type=Path,required=True);a=p.parse_args(sys.argv[sys.argv.index('--')+1:])
assets={path.stem:str(path.resolve()) for path in a.assets.glob('*.blend')}
with tempfile.TemporaryDirectory(prefix='alice-proxy-qa-') as tmp:
 root=Path(tmp);cfg=RenderSettings(detectors=[],geometry=[n for n in assets if n!='L3'],magnet=True,geometry_assets=assets,geometry_units='m')
 cfg=fast_editor_settings(cfg);assert set(cfg.geometry_lods.values())=={'proxy'}
 job={'fast_interactive':True,'event':str(geometry_only_input(root)),'output':str(root),'settings':cfg.to_dict(),'blender':{'version':list(bpy.app.version),'devices':[{'type':'CPU','id':'cpu'}]},'library_path':str(root/'library.sqlite')}
 path=root/'job.json';path.write_text(json.dumps(job));start=time.monotonic();worker.render(path,True)
 meta=json.loads((root/'metadata.json').read_text())
 assert len(meta['geometry'])==16 and sum(v['meshes'] for v in meta['geometry'].values())<=17
 assert all(v['source_asset_loaded'] is False and v['lod']=='proxy' for v in meta['geometry'].values())
 assert not any('num_instances' in o for o in bpy.data.objects)
 assert bpy.context.scene.render.engine=='BLENDER_EEVEE'
 assert bpy.context.scene.alice_eve.viewport_samples==32
 assert bpy.ops.alice_eve.fast_surfaces()=={'FINISHED'}
 assert all(m.surface_render_method=='BLENDED' for m in bpy.data.materials if m.get('alice_proxy'))
 ui=bpy.context.scene.alice_eve;ui.stable_transparency=False
 assert all(m.surface_render_method=='DITHERED' for m in bpy.data.materials if m.get('alice_proxy'))
 ui.stable_transparency=True
 assert all(m.surface_render_method=='BLENDED' for m in bpy.data.materials if m.get('alice_proxy'))
 # Appearance changes and unchanged Apply geometry calls retain mesh datablock identities.
 def buffers():return {(n,o.name):(o.as_pointer(),o.data.as_pointer()) for n in assets for o in bpy.data.collections[n].objects}
 identities=buffers()
 ui=bpy.context.scene.alice_eve
 from unittest.mock import patch
 with patch.object(worker,'imported_geometry',side_effect=AssertionError('Unchanged geometry must not reload')):
  for name in assets:
   item=ui.detectors[name];item.opacity=.25;item.color=(.2,.3,.6);item.opening=120;item.opening_direction=45
   assert bpy.ops.alice_eve.apply_geometry()=={'FINISHED'}
   assert buffers()==identities
 # A no-op appearance refresh must not dirty any detector datablock.
 import editor
 detector_ids=set()
 for name in assets:
  for obj in bpy.data.collections[name].objects:
   detector_ids.update((obj.as_pointer(),obj.data.as_pointer()))
   for mat in obj.data.materials:
    detector_ids.update((mat.as_pointer(),mat.node_tree.as_pointer()))
 bpy.context.view_layer.update()
 for _ in range(3):
  editor.appearance_update(ui,bpy.context)
  bpy.context.view_layer.update()
  dirty={u.id.original.as_pointer() for u in bpy.context.evaluated_depsgraph_get().updates}
  assert not dirty&detector_ids, 'An unchanged appearance refresh dirtied detector data'
 ui.track_color=(.3,.6,.9);ui.cluster_color=(.9,.6,.3)
 bpy.context.view_layer.update()
 dirty={u.id.original.as_pointer() for u in bpy.context.evaluated_depsgraph_get().updates}
 assert not dirty&detector_ids, 'Event-only appearance changes dirtied detector data'
 # Playback advances only event data. All 16 detector/magnet buffers persist.
 from alice_renderer.video import schedule,header
 from video_player import VideoPlayer
 events=[];paths=[]
 for i in range(2):
  event=dict(schema_version=1,units='cm',kind='synthetic',id=str(i),vertex=[0,0,0],tracks=[dict(id=str(i),detectors=['TPC'],points=[[0,0,0],[100,i,0],[200,i,0]])],clusters=[])
  event_path=root/f'collision-{i}.json';event_path.write_text(json.dumps(event));paths.append(str(event_path));events.append(event)
 settings=cfg.to_dict();settings.update(detectors=['TPC'],video_enabled=True,video_interval_s=1.,video_fps=4)
 playback=dict(job,events=paths,video_headers=[header(e) for e in events],video_plan=schedule(events,settings))
 player=VideoPlayer(playback,settings,editor.JOB['track_regions'])
 with patch.object(worker,'imported_geometry',side_effect=AssertionError('Playback must reuse detector geometry and bounds')):
  for frame in (0,1,1,3,4,5,7,0):
   player.set_frame(frame)
   assert buffers()==identities
   assert all(m.surface_render_method=='BLENDED' for m in bpy.data.materials if m.get('alice_proxy'))
  bpy.context.view_layer.update();player.set_frame(0)
  assert not list(bpy.context.evaluated_depsgraph_get().updates), 'Same-frame playback dirtied the dependency graph'
 # Final render settings always restore accurate transparency, independent of preview.
 for mat in [m for m in bpy.data.materials if m.get('alice_proxy')]:
  worker.configure_surface_material(mat,.25,False);assert mat.surface_render_method=='DITHERED'
 editor.preview_transparency_update(ui,bpy.context)
 assert all(m.surface_render_method=='BLENDED' for m in bpy.data.materials if m.get('alice_proxy'))
 # Cache clipping bounds bypass mesh import, even for non-ITS/TPC tracks.
 region=worker.imported_geometry('HMP',assets['HMP'],cfg.to_dict(),bounds_only=True)
 assert region['units']=='cm' and len(region['planes'])==66
 print('NATIVE_PROXY_QA_PASSED',round(time.monotonic()-start,3),flush=True)
