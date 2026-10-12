"""Blender QA: optional towers, live controls, and portable exports."""
import json,sys,tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src/alice_renderer/blender'))
import bpy,worker,editor
from alice_renderer.model import RenderSettings
from alice_renderer.scene_config import load_config,quality_settings,recipe

with tempfile.TemporaryDirectory(prefix='alice-tower-qa-') as tmp:
    root=Path(tmp)
    frame={'u_cm':[0,6,0],'v_cm':[0,0,6],'basis':'aligned QA module'}
    objects=[dict(id='emc',detector='EMC',position=[440,0,0],energy=2,measurement_kind='calorimeter_cell',cell_geometry=frame),
             dict(id='phos',detector='PHS',position=[0,-460,0],energy=1,measurement_kind='calorimeter_cell'),
             dict(id='cpv',detector='CPV',position=[0,-445,30],amplitude=10,measurement_kind='cpv_cluster'),
             dict(id='cpv-missing',detector='CPV',position=[0,-445,60],measurement_kind='cpv_cluster')]
    event=root/'event.json';event.write_text(json.dumps(dict(schema_version=1,units='cm',kind='synthetic',id='TOWERS-QA',tracks=[],clusters=objects)))
    cfg=RenderSettings(detectors=['EMC','PHS','CPV'],mode='clusters',clip_tracks=False,
        calorimeter_display={name:'signal towers' for name in ('EMC','PHS','CPV')},cluster_color_mode='solid')
    job=root/'job.json';job.write_text(json.dumps(dict(event=str(event),output=str(root),settings=cfg.to_dict(),
        library_path=str(root/'history.sqlite'),blender={'version':list(bpy.app.version),'devices':[{'type':'CPU'}]})))
    worker.render(job,True);ui=bpy.context.scene.alice_eve
    legend=json.loads((root/'metadata.json').read_text())['cluster_legend']['calorimeter_towers']
    assert legend['EMC']['towers']==1 and legend['EMC']['approximate_footprints']==0
    assert legend['PHS']['towers']==1 and legend['PHS']['approximate_footprints']==1
    assert legend['CPV']['towers']==1 and legend['CPV']['point_fallbacks']==1
    meshes=[o for o in bpy.data.collections['Clusters'].objects if o.get('alice_towers')]
    assert sum(len(o.data.vertices) for o in meshes)==24 and sum(len(o.data.polygons) for o in meshes)==18
    assert all(not p.use_smooth for o in meshes for p in o.data.polygons)
    actual=editor.current_settings();assert actual.calorimeter_display==cfg.calorimeter_display
    assert quality_settings(actual,resolution_percent=50).calorimeter_display==cfg.calorimeter_display
    detectors={i.name:i for i in ui.detectors}
    assert detectors['CPV'].tower_count==1 and detectors['CPV'].tower_point_fallbacks==1
    detectors['EMC'].cell_display='points';detectors['CPV'].cell_display='fixed towers';ui.tower_fixed_height_cm=14;ui.tower_direction='outward'
    bpy.ops.alice_eve.apply_data()
    # PHOS plus both CPV clusters; EMC now remains a point.
    meshes=[o for o in bpy.data.collections['Clusters'].objects if o.get('alice_towers')]
    assert sum(len(o.data.vertices) for o in meshes)==24
    assert detectors['EMC'].tower_count==0 and detectors['CPV'].tower_count==2 and detectors['CPV'].tower_point_fallbacks==0
    bpy.ops.alice_eve.export()
    saved=load_config(ui.export_path)['scene']
    assert saved['calorimeter_display']=={'EMC':'points','PHS':'signal towers','CPV':'fixed towers'}
    assert saved['tower_fixed_height_cm']==14 and saved['tower_direction']=='outward'
    print('CALORIMETER TOWER BLENDER QA PASSED')
