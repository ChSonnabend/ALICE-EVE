"""Native Blender QA for mixed-detector glyph sizes and logarithmic heights."""
import json,math,sys,tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src/alice_renderer/blender'))
import bpy,worker,editor
from alice_renderer.model import RenderSettings
from alice_renderer.cluster_profiles import profile_axes
from alice_renderer.scene_config import load_config,quality_settings

with tempfile.TemporaryDirectory(prefix='alice-size-qa-') as tmp:
    root=Path(tmp)
    tpc=dict(id='tpc',detector='TPC',position=[100,0,0],tpc_profile=dict(sigma_pad=2,sigma_time_bins=3,sigma_vectors_cm=[[.4,0,0],[0,.7,0]],basis='QA measured widths'))
    frame={'u_cm':[0,6,0],'v_cm':[0,0,6],'basis':'aligned QA module'}
    cells=[dict(id=str(i),detector='EMC',position=[440,i*20,0],energy=e,cell_geometry=frame) for i,e in enumerate((1,99))]
    objects=[dict(id='its',detector='ITS',position=[20,0,0]),tpc,*cells]
    event=root/'event.json';event.write_text(json.dumps(dict(schema_version=1,units='cm',kind='synthetic',id='SIZE-QA',tracks=[],clusters=objects)))
    cfg=RenderSettings(detectors=['ITS','TPC','EMC'],mode='clusters',clip_tracks=False,cluster_size_scales={'ITS':2,'TPC':3},tpc_cluster_profile='ellipse',calorimeter_display={'EMC':'signal towers'},tower_height_scales={'EMC':100},tower_width_scales={'EMC':.5},tower_height_mapping='log',tower_max_heights_cm={'EMC':1000})
    job=root/'job.json';job.write_text(json.dumps(dict(event=str(event),output=str(root),settings=cfg.to_dict(),library_path=str(root/'history.sqlite'),blender={'version':list(bpy.app.version),'devices':[{'type':'CPU'}]})))
    worker.render(job,True);ui=bpy.context.scene.alice_eve;coll=bpy.data.collections['Clusters']
    its=next(o for o in bpy.data.collections['Clusters'].objects if o.get('alice_detector')=='ITS')
    ico=next(n for n in its.modifiers[0].node_group.nodes if n.bl_idname=='GeometryNodeMeshIcoSphere')
    assert abs(ico.inputs['Radius'].default_value-.007)<1e-7
    measured=next(o for o in coll.objects if o.get('alice_detector')=='TPC')
    size,basis=profile_axes(tpc,.03)
    assert all(abs(a-b*.03)<1e-7 for a,b in zip(measured.data.attributes['profile_scale'].data[0].vector,size))
    tower=next(o for o in coll.objects if o.get('alice_towers'))
    verts=[v.co for v in tower.data.vertices]
    for offset,signal in ((0,1),(8,99)):
        height=abs(sum(v.x for v in verts[offset:offset+4])/4-sum(v.x for v in verts[offset+4:offset+8])/4)*100
        assert abs(height-100*math.log1p(signal))<1e-3
    assert abs((max(v.y for v in verts[:4])-min(v.y for v in verts[:4]))*100-6*.95*.5)<1e-3
    legend=json.loads((root/'metadata.json').read_text())['cluster_legend']
    assert legend['calorimeter_towers']['EMC']['height_mapping']=='log'
    assert legend['cluster_size_scales']=={'ITS':2,'TPC':3}
    detectors={i.name:i for i in ui.detectors}
    detectors['ITS'].cluster_size_scale=4;detectors['EMC'].tower_mapping='linear';detectors['EMC'].tower_width_factor=2
    bpy.ops.alice_eve.apply_data()
    its=next(o for o in bpy.data.collections['Clusters'].objects if o.get('alice_detector')=='ITS')
    ico=next(n for n in its.modifiers[0].node_group.nodes if n.bl_idname=='GeometryNodeMeshIcoSphere')
    assert abs(ico.inputs['Radius'].default_value-.014)<1e-7
    bpy.ops.alice_eve.export();saved=load_config(ui.export_path)['scene']
    assert saved['cluster_size_scales']=={'ITS':4,'TPC':3} and saved['tower_width_scales']=={'EMC':2}
    assert saved['tower_height_mapping']=='log' and saved['tower_height_mappings']=={'EMC':'linear'}
    actual=editor.current_settings();assert quality_settings(actual,resolution_percent=50).tower_height_mappings=={'EMC':'linear'}
    detectors['EMC'].tower_mapping='inherit';bpy.ops.alice_eve.apply_data()
    assert editor.current_settings().tower_height_mappings=={}
    print('PER-DETECTOR SIZES AND LOG HEIGHTS BLENDER QA PASSED')
