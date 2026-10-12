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
 assert all(m.surface_render_method=='DITHERED' for m in bpy.data.materials if m.get('alice_proxy'))
 # Cache clipping bounds bypass mesh import, even for non-ITS/TPC tracks.
 region=worker.imported_geometry('HMP',assets['HMP'],cfg.to_dict(),bounds_only=True)
 assert region['units']=='cm' and len(region['planes'])==66
 print('NATIVE_PROXY_QA_PASSED',round(time.monotonic()-start,3),flush=True)
