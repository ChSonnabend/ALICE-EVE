"""Optional native QA with supplied assets and a real or synthetic event; no image renders.

blender -b --factory-startup --python-exit-code 1 --python tests/blender_components.py --
 --assets geometry/run-560067 --event /path/event.json.gz
"""
import argparse,gzip,json,sys,tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src/alice_renderer/blender'))
import bpy,worker,editor
from alice_renderer.model import RenderSettings
from alice_renderer.geometry_components import load_components
from alice_renderer.scene_config import resolve_settings
from components import points_for
p=argparse.ArgumentParser();p.add_argument('--assets',type=Path,required=True);p.add_argument('--event',type=Path,required=True);a=p.parse_args(sys.argv[sys.argv.index('--')+1:])
assets={d:str((a.assets/(d+'.blend')).resolve()) for d in ('ITS','TPC')}
with tempfile.TemporaryDirectory(prefix='alice-component-qa-') as tmp:
    root=Path(tmp)
    cfg=RenderSettings(detectors=['ITS','TPC'],geometry=['ITS','TPC'],geometry_assets=assets,geometry_units='m',cutaway=False,geometry_lod='full',track_color_mode='feature:tpc_signal',geometry_components={'ITS':{'layers/layer_4':False},'TPC':{'structures/inner_wall':False}})
    job=root/'job.json';job.write_text(json.dumps({'event':str(a.event.resolve()),'output':str(root),'settings':cfg.to_dict(),'blender':{'version':list(bpy.app.version),'devices':[{'type':'CPU'}]}}))
    worker.render(job,True);ui=bpy.context.scene.alice_eve
    assert ui.track_mode=='feature:tpc_signal'
    assert any(c.identifier=='layers/layer_6' for c in ui.detectors['ITS'].components)
    assert not next(c for c in ui.detectors['ITS'].components if c.identifier=='layers/layer_4').enabled
    def verify(detector,identifier,wanted):
        meta=load_components(assets[detector]);found=0
        for obj in bpy.data.collections[detector].objects:
            if 'num_instances' not in obj:continue
            group,inst,points=points_for(obj);binding=meta['groups'][obj['alice_source_name']];mask=points.attributes['alice_inner_mask_keep']
            for i,cls in enumerate(binding['ids']):
                if identifier in binding['classes'][cls]:assert mask.data[i].value==wanted;found+=1
        assert found>0
    verify('ITS','layers/layer_4',False);verify('ITS','layers/layer_3',True);verify('ITS','layers/layer_6',True);verify('TPC','structures/inner_wall',False)
    assert bpy.ops.alice_eve.toggle_component(detector='ITS',identifier='layers/layer_4')=={'FINISHED'};verify('ITS','layers/layer_4',True)
    assert bpy.ops.alice_eve.toggle_component(detector='TPC',identifier='structures/inner_wall')=={'FINISHED'};verify('TPC','structures/inner_wall',True)
    # Explicit enable must restore objects suppressed by legacy masks.
    ui.detectors['TPC'].exclusions='TPC_IFC*';assert bpy.ops.alice_eve.apply_geometry()=={'FINISHED'};verify('TPC','structures/inner_wall',True)
    ui.export_path=str(root/'scene.json');assert bpy.ops.alice_eve.export()=={'FINISHED'}
    exported=json.loads(Path(ui.export_path).read_text());restored=resolve_settings(exported,ui.export_path,a.assets)
    assert restored.geometry_components['ITS']['layers/layer_4'] is True and restored.track_color_mode=='feature:tpc_signal'
    assert 'components' in exported['geometry']['TPC']
    # Simplification respects the very same per-placement masks.
    assert bpy.ops.alice_eve.toggle_component(detector='ITS',identifier='layers/layer_4')=={'FINISHED'}
    ui.detectors['ITS'].detail='simplified';assert bpy.ops.alice_eve.apply_geometry()=={'FINISHED'}
    assert any(o.get('alice_lod')=='simplified' for o in bpy.data.collections['ITS'].objects)
    assert bpy.ops.alice_eve.toggle_component(detector='ITS',identifier='layers')=={'FINISHED'}
    assert editor.current_settings().geometry_components['ITS']['layers'] is True
    assert bpy.ops.alice_eve.toggle_component(detector='ITS',identifier='layers')=={'FINISHED'}
    assert editor.current_settings().geometry_components['ITS']['layers'] is False
print('Native component placement, interactive toggle, simplified geometry, AO2D feature colour and portable recipe QA passed')
