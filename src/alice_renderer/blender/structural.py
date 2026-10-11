"""Load prebuilt large surfaces, without loading aligned instance/prototype meshes."""
import json,time
from fnmatch import fnmatchcase
import bpy
from alice_renderer.structural_geometry import load,supported_components
from alice_renderer.geometry_components import component_state


def imported(name,asset,settings,bounds_only=False):
    start=time.monotonic();data=load(asset,settings['geometry_units'])
    if data['detector']!=name:raise ValueError('Large-surface cache detector differs from the selected asset')
    if bounds_only:return data['track_region']
    if settings.get('geometry_inner_masks',{}).get(name):
        raise ValueError(name+': clear inner-placement masks before using merged large surfaces; use component choices and angular openings')
    from worker import collection,materials,rgb
    coll=collection(name);choices=settings.get('geometry_components',{}).get(name,{})
    patterns=settings.get('geometry_exclusions',{}).get(name,[])
    if patterns and any('source_names' not in g for g in data['groups']):raise ValueError('Rebuild large-surface cache to retain source-name exclusion masks')
    coll['alice_components']=json.dumps(choices,sort_keys=True);coll['alice_exclusions']=json.dumps(patterns)
    coll['alice_inner_mask']='{}';coll['alice_display']='surfaces';coll['alice_geometry_lod']='structural'
    coll['alice_asset_path']=str(__import__('pathlib').Path(asset).resolve());coll['alice_schematic']=False
    coll['alice_structural_components']=json.dumps(sorted(supported_components(data)))
    key='magnet' if name=='L3' else name
    mat=materials(name,settings.get('colors_linear',{}).get(key,rgb(settings['colors'][key])),settings.get('geometry_opacities',{}).get(name,settings['geometry_opacity']),settings=settings)
    count=0;faces=0;elements=0
    for group in data['groups']:
        keep,explicit=component_state(group['tags'],choices)
        if not keep or (not explicit and any(fnmatchcase(source,p) for p in patterns for source in [group['name'],*group.get('source_names',[])])):continue
        mesh=bpy.data.meshes.new(group['name']+' large surfaces');mesh.from_pydata(group['vertices'],[],group['faces']);mesh.update()
        obj=bpy.data.objects.new(group['name'],mesh);coll.objects.link(obj)
        obj['alice_lod']='structural';obj['alice_source_name']=group['name'];obj['alice_component_tags']=json.dumps(group['tags'])
        obj['alice_structural_smooth']=name=='TPC' and bool(set(group['tags'])&{'structures/inner_wall','structures/outer_wall'})
        mesh.materials.append(mat)
        # Flat faces keep stave panels square. Smooth circumferential walls
        # retain their native curved normals; endcap normals stay planar.
        for poly in mesh.polygons:poly.use_smooth=settings.get('shading','smooth')=='smooth' and obj['alice_structural_smooth']
        count+=1;faces+=len(mesh.polygons);elements+=group['elements']
    return dict(lod='structural',display='surfaces',approximate=True,basis=data['basis'],meshes=count,
                surface_elements=elements,faces=faces,source_instances=data['source_instances'],
                source_asset_loaded=False,load_seconds=round(time.monotonic()-start,4),
                track_region=data['track_region'])
