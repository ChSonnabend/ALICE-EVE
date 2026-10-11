"""Native proxy loading/selection and aligned track-bound parity checks."""
import argparse,copy,gzip,json,sys,tempfile,time
from pathlib import Path
sys.path[:0]=[str(Path(__file__).resolve().parents[1]/'src'),str(Path(__file__).resolve().parents[1]/'src/alice_renderer/blender')]
import bpy,bmesh,numpy as np
from worker import imported_geometry,remove_owned_collection
from alice_renderer.model import RenderSettings
from alice_renderer.geometry_components import load_components
from alice_renderer.scene_presets import tpc_sectors_and_inner_wall
from alice_renderer.structural_geometry import load,sidecar_path
from alice_renderer.geometry_components import sidecar_path as component_path
from alice_renderer.scene_config import recipe,save_config,resolve_settings,sha256

p=argparse.ArgumentParser();p.add_argument('--geometry-root',type=Path,required=True);p.add_argument('--report',type=Path,required=True)
a=p.parse_args(sys.argv[sys.argv.index('--')+1:])
assets={name:str((a.geometry_root/(name+'.blend')).resolve()) for name in ('ITS','TPC')}
choices=tpc_sectors_and_inner_wall(load_components(assets['TPC']))
for part in ('parts/TPC_OCV','parts/TPC_OHVH','parts/TPC_TOFC'):choices[part]=True
cfg=RenderSettings(detectors=['ITS','TPC'],geometry=['ITS','TPC'],geometry_assets=assets,geometry_units='m',geometry_components={'TPC':choices},geometry_openings={'ITS':90,'TPC':90},cutaway=False)
cfg.palette_lut=[[0.,0.,0.],[1.,1.,1.]] # Solid-colour native QA needs no host Matplotlib.
report={}
for name in ('ITS','TPC'):
    start=time.monotonic();full=imported_geometry(name,assets[name],cfg.to_dict());full_seconds=time.monotonic()-start
    remove_owned_collection(bpy.data.collections[name])
    values=cfg.to_dict();values['geometry_lods']={name:'structural'};values['_interactive']=True
    start=time.monotonic();fast=imported_geometry(name,assets[name],values);fast_seconds=time.monotonic()-start
    assert not fast['source_asset_loaded']
    assert np.allclose(full['track_region']['planes'],fast['track_region']['planes'],atol=1.e-7,rtol=0)
    assert all('num_instances' not in o for o in bpy.data.collections[name].objects)
    if name=='ITS':
        for obj in bpy.data.collections[name].objects:
            bm=bmesh.new();bm.from_mesh(obj.data)
            assert bm.calc_volume(signed=True)>0,'ITS panel normals must face outward'
            bm.free()
    expected=192 if name=='ITS' else 257
    assert fast['surface_elements']==expected,fast
    report[name]=dict(full_seconds=full_seconds,fast_seconds=fast_seconds,full_meshes=full['meshes'],fast_meshes=fast['meshes'],fast_elements=fast['surface_elements'],fast_faces=fast['faces'],track_bound_max_error_cm=float(np.max(abs(np.array(full['track_region']['planes'])-np.array(fast['track_region']['planes'])))))
    remove_owned_collection(bpy.data.collections[name])
    values['geometry_components'][name]=dict(values['geometry_components'].get(name,{}),**({'layers/layer_2':False} if name=='ITS' else {'structures/outer_wall':False}))
    masked=imported_geometry(name,assets[name],values)
    assert masked['surface_elements']==(172 if name=='ITS' else 254)
    assert masked['track_region']==fast['track_region']
    remove_owned_collection(bpy.data.collections[name])
    if name=='ITS':
        values['geometry_components'][name]={};values['geometry_exclusions']={name:['ITSUChip0-*']}
        excluded=imported_geometry(name,assets[name],values)
        assert excluded['surface_elements']==144 # Hide all three inner layers, not the outer layers.
        remove_owned_collection(bpy.data.collections[name])
cfg.geometry_lods={'ITS':'structural','TPC':'structural'}
data=recipe(cfg);config=a.report.with_suffix('.scene.json');save_config(config,data)
assert all('structural' in data['geometry'][name] for name in ('ITS','TPC'))
restored=resolve_settings(data,config,a.geometry_root);assert restored.geometry_lods==cfg.geometry_lods
# A non-Blender source container would fail immediately if fast loading tried
# bpy.data.libraries.load. This synthetic binding tests only that loading route.
with tempfile.TemporaryDirectory(prefix='alice-fast-import-qa-') as tmp:
    fake=Path(tmp)/'TPC.blend';fake.write_bytes(b'SYNTHETIC: deliberately not a Blender file')
    cache=copy.deepcopy(load(assets['TPC']))
    meta={'schema':'alice-geometry-components','version':1,'asset_sha256':sha256(fake)}
    with gzip.open(component_path(fake),'wt') as stream:json.dump(meta,stream)
    cache['asset_sha256']=sha256(fake);cache['components_sha256']=sha256(component_path(fake))
    with gzip.open(sidecar_path(fake),'wt') as stream:json.dump(cache,stream)
    fast=imported_geometry('TPC',str(fake),cfg.to_dict())
    assert not fast['source_asset_loaded'] and fast['surface_elements']==257
    remove_owned_collection(bpy.data.collections['TPC'])
# Exercise the actual editor switch/export, not just direct geometry loading.
with tempfile.TemporaryDirectory(prefix='alice-fast-editor-qa-') as tmp:
    root=Path(tmp);event=root/'event.json'
    event.write_text(json.dumps({'id':'SYNTHETIC-FAST-EDITOR-QA','kind':'synthetic','tracks':[],'clusters':[]}))
    job=root/'job.json';job.write_text(json.dumps({'event':str(event),'output':str(root),'settings':cfg.to_dict(),'blender':{'version':list(bpy.app.version),'devices':[{'type':'CPU'}]}}))
    from worker import render
    render(job,True)
    import editor
    pose=bpy.context.scene.camera.matrix_world.copy()
    assert bpy.ops.alice_eve.fast_surfaces()=={'FINISHED'}
    assert bpy.context.scene.camera.matrix_world==pose
    assert editor.current_settings().geometry_lods=={'ITS':'structural','TPC':'structural'}
    ui=bpy.context.scene.alice_eve;ui.export_path=str(root/'export.json')
    assert bpy.ops.alice_eve.export()=={'FINISHED'}
    assert all('structural' in json.loads(Path(ui.export_path).read_text())['geometry'][name] for name in ('ITS','TPC'))
a.report.write_text(json.dumps(report,indent=2)+'\n')
print('Native large surfaces, layer/wall toggles, full aligned clipping parity and portable cache binding passed.',flush=True)
print(json.dumps(report),flush=True)
