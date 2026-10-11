"""Bind named geometry choices to verified aligned instance placements."""
import hashlib
import numpy as np
import bpy
from alice_renderer.geometry_components import load_components,component_state


def points_for(obj):
    group=obj.modifiers['GeometryNodes'].node_group
    instance=next(n for n in group.nodes if n.bl_idname=='GeometryNodeInstanceOnPoints')
    points=instance.inputs['Points'].links[0].from_node.inputs['Object'].default_value.data
    return group,instance,points


def verify_group(obj,entry):
    group,instance,points=points_for(obj)
    coordinates=np.empty(len(points.vertices)*3,dtype=np.float32)
    points.vertices.foreach_get('co',coordinates)
    if len(points.vertices)!=len(entry['ids']) or hashlib.sha256(coordinates.astype('<f4').tobytes()).hexdigest()!=entry['positions_sha256']:
        raise ValueError('Component placement binding differs from aligned asset: '+obj.name)
    return group,instance,points


def apply_components(objects,asset,choices):
    metadata=load_components(asset)
    if not metadata:
        if choices:raise ValueError('This asset has no component metadata. Export its aligned geometry hierarchy first: '+str(asset))
        return {},{},{}
    unknown=set(choices)-set(metadata['components'])
    if unknown:raise ValueError('Unknown detector components: '+', '.join(sorted(unknown)))
    masks={};overrides={};removed={}
    for obj in objects:
        if 'num_instances' not in obj:continue
        entry=metadata['groups'].get(obj.get('alice_source_name',obj.name))
        if not entry:raise ValueError('Instancer is absent from component metadata: '+obj.name)
        group,instance,points=verify_group(obj,entry)
        states=[component_state(tags,choices) for tags in entry['classes']]
        keep=[states[i][0] and (not obj.get('alice_geometry_excluded') or states[i][1]) for i in entry['ids']]
        explicit=[states[i][0] and states[i][1] for i in entry['ids']]
        masks[obj.name]=keep;overrides[obj.name]=explicit;removed[obj.name]=len(keep)-sum(keep)
        if obj.get('alice_geometry_excluded') and any(keep):
            obj['alice_geometry_excluded']=False;obj.hide_render=False;obj.hide_set(False)
    return masks,overrides,{'available':metadata['components'],'choices':choices,'removed_instances':removed}


def set_selection(obj,keep):
    group,instance,points=points_for(obj)
    attr=points.attributes.get('alice_inner_mask_keep') or points.attributes.new('alice_inner_mask_keep','BOOLEAN','POINT')
    attr.data.foreach_set('value',keep)
    selection=group.nodes.new('GeometryNodeInputNamedAttribute');selection.data_type='BOOLEAN';selection.inputs['Name'].default_value=attr.name
    group.links.new(selection.outputs['Attribute'],instance.inputs['Selection'])
