"""Blender sidebar for interactive ALICE-EVE scene editing and portable export."""
import copy, json, math, subprocess, time
from pathlib import Path
import bpy
from bpy.props import BoolProperty, CollectionProperty, EnumProperty, FloatProperty, FloatVectorProperty, IntProperty, StringProperty
from alice_renderer.model import RenderSettings, COLOR_FIELDS, capabilities
from alice_renderer.object_selection import parse_track_ids,selected_tracks,selected_clusters,enabled_detectors,event_counts
from alice_renderer.palettes import names as palette_names
from alice_renderer.scene_config import recipe, save_config, recommended_quality

JOB=None
EVENT=None
DEVICES=None
RECOMMENDATION=None
PALETTES={}
PALETTE_ITEMS=[(n,n,'') for n in palette_names()]


def hex_color(linear):
    vals=[12.92*c if c<=.0031308 else 1.055*max(c,0)**(1/2.4)-.055 for c in linear[:3]]
    return '#'+''.join(f'{round(max(0,min(1,c))*255):02x}' for c in vals)

def current_settings():
    cfg=copy.deepcopy(JOB['settings']);scene=bpy.context.scene;ui=scene.alice_eve
    camera=scene.camera
    cfg['camera']='orthographic' if camera.data.type=='ORTHO' else 'perspective'
    cfg['camera_pose']={'matrix_world':[list(row) for row in camera.matrix_world], 'lens':camera.data.lens,'ortho_scale':camera.data.ortho_scale}
    cfg['frame_aspect']=scene.render.resolution_x/scene.render.resolution_y
    cfg['width']=scene.render.resolution_x;cfg['height']=scene.render.resolution_y
    cfg['geometry']=[];cfg['magnet']=False;cfg['detectors']=[]
    cfg['detector_modes']={};cfg['geometry_display']={};cfg['geometry_openings']={};cfg['geometry_opacities']={};cfg['colors_linear']={}
    for item in ui.detectors:
        if item.data and item.data_available:cfg['detectors'].append(item.name)
        if item.visible and item.geometry_available:
            if item.name=='L3':cfg['magnet']=True
            else:cfg['geometry'].append(item.name)
        if item.name!='L3':cfg['detector_modes'][item.name]=item.mode
        cfg['geometry_display'][item.name]=item.display
        cfg['geometry_openings'][item.name]=item.opening
        cfg['geometry_opacities'][item.name]=item.opacity
        cfg['colors']['magnet' if item.name=='L3' else item.name]=hex_color(item.color)
        cfg['colors_linear']['magnet' if item.name=='L3' else item.name]=list(item.color)
    cfg['colors']['background']=hex_color(ui.background)
    cfg['colors']['tracks']=hex_color(ui.track_color);cfg['colors']['clusters']=hex_color(ui.cluster_color)
    cfg['colors_linear'].update(background=list(ui.background),tracks=list(ui.track_color),clusters=list(ui.cluster_color))
    cfg['track_radius_cm']=ui.track_width_cm/2;cfg['cluster_radius_cm']=ui.cluster_radius_cm;cfg['clip_tracks']=ui.clip_tracks
    cfg['highlight_track_ids']=parse_track_ids(ui.highlight_ids);cfg['highlight_track_radius_cm']=ui.highlight_width_cm/2;cfg['highlight_cluster_radius_cm']=ui.highlight_cluster_radius_cm;cfg['highlight_override_color']=ui.highlight_override;cfg['highlight_track_color']=hex_color(ui.highlight_track_color);cfg['highlight_cluster_color']=hex_color(ui.highlight_cluster_color)
    cfg['geometry_lod']=ui.geometry_lod
    cfg['geometry_lods']={i.name:i.detail for i in ui.detectors if i.detail!='inherit'}
    cfg['world_strength']=ui.world_strength;cfg['roughness']=ui.roughness;cfg['metallic']=ui.metallic;cfg['shading']=ui.shading
    cfg['mode']=ui.mode;cfg['track_color_mode']=ui.track_mode;cfg['cluster_color_mode']=ui.cluster_mode;cfg['palette']=ui.palette;cfg['palette_lut']=PALETTES.get(ui.palette,JOB['settings'].get('palette_lut',[]))
    cfg['color_ranges']={'tracks':[ui.track_min,ui.track_max],'clusters':[ui.cluster_min,ui.cluster_max]}
    cfg['scale_min']=None;cfg['scale_max']=None
    cfg['lights']=[{'position_m':list(o.location),'rotation':list(o.rotation_euler),'energy':o.data.energy,'size_m':o.data.size,'color':hex_color(o.data.color),'color_linear':list(o.data.color)} for o in scene.objects if o.type=='LIGHT' and o.data.type=='AREA']
    return RenderSettings(**cfg).validate()

def track_signature(ui):
    return (tuple((i.name,i.mode) for i in ui.detectors if i.data and i.data_available),tuple(i.name for i in ui.detectors if i.visible and i.geometry_available and i.name!='L3'),ui.track_width_cm,ui.cluster_radius_cm,ui.clip_tracks,ui.highlight_ids,ui.highlight_width_cm,ui.highlight_cluster_radius_cm,ui.highlight_override,tuple(ui.highlight_track_color),tuple(ui.highlight_cluster_color))

def set_all_modes(self,context):
    if not JOB:return
    for item in context.scene.alice_eve.detectors:item.mode=self.mode
    selection_update(self,context)

def selection_update(self,context):
    if not JOB or not hasattr(context.scene,'alice_eve'):return
    ui=context.scene.alice_eve
    if JOB.get('applied_track_signature')==track_signature(ui):return
    JOB['track_update_time']=time.monotonic()
    if JOB.get('track_update_pending'):return
    JOB['track_update_pending']=True
    def update():
        if time.monotonic()-JOB['track_update_time']<.2:return .2
        JOB['track_update_pending']=False
        if JOB.get('applied_track_signature')!=track_signature(bpy.context.scene.alice_eve):bpy.ops.alice_eve.apply_data()
        return None
    bpy.app.timers.register(update,first_interval=.2)

def appearance_update(self,context):
    if not JOB or not hasattr(context.scene,'alice_eve'):return
    ui=context.scene.alice_eve
    selection_update(self,context)
    coll=bpy.data.collections.get('Tracks')
    if coll:
        for obj in coll.objects:
            if obj.type=='CURVE':obj.data.bevel_depth=(ui.highlight_width_cm if obj.get('alice_highlighted') else ui.track_width_cm)*.005
    world=context.scene.world.node_tree.nodes['Background'];world.inputs[0].default_value=(*ui.background,1);world.inputs[1].default_value=ui.world_strength
    for mat in bpy.data.materials:
        if not mat.use_nodes:continue
        bsdf=mat.node_tree.nodes.get('Principled BSDF')
        if bsdf:bsdf.inputs['Roughness'].default_value=ui.roughness;bsdf.inputs['Metallic'].default_value=ui.metallic
    for obj in context.scene.objects:
        if obj.type=='MESH':
            for p in obj.data.polygons:p.use_smooth=ui.shading=='smooth' and 'alice_lod' not in obj
    for item in ui.detectors:
        coll=bpy.data.collections.get(item.name)
        if coll:
            coll.hide_render=not item.visible;coll.hide_viewport=not item.visible
        mats={m for obj in coll.all_objects if obj.type in ('MESH','CURVE') for m in obj.data.materials if m} if coll else set()
        for mat in mats:
            if not mat.use_nodes:continue
            bsdf=mat.node_tree.nodes.get('Principled BSDF')
            if not bsdf:continue
            bsdf.inputs['Base Color'].default_value=(*item.color,1)
            opening=mat.node_tree.nodes.get('ALICE opening')
            if opening:opening.inputs[1].default_value=math.radians(item.opening)/2
            for node in mat.node_tree.nodes:
                if node.bl_idname=='ShaderNodeMixShader' and not node.inputs[0].is_linked:node.inputs[0].default_value=item.opacity
            mat.diffuse_color=(*item.color,item.opacity)
    for kind in ('Tracks','Clusters'):
        coll=bpy.data.collections.get(kind)
        if not coll:continue
        # Object selection is already per detector; no global hide masks.
        coll.hide_render=coll.hide_viewport=False
        for obj in coll.objects:
            emphasis=obj.get('alice_highlighted',False)
            base=ui.track_color if kind=='Tracks' else ui.cluster_color
            special=ui.highlight_track_color if kind=='Tracks' else ui.highlight_cluster_color
            mode=ui.track_mode if kind=='Tracks' else ui.cluster_mode
            if not (emphasis and ui.highlight_override) and mode!='solid':continue
            mats=list(obj.data.materials)
            for modifier in obj.modifiers:
                if modifier.type=='NODES':
                    for node in modifier.node_group.nodes:
                        if node.bl_idname=='GeometryNodeSetMaterial' and node.inputs['Material'].default_value:mats.append(node.inputs['Material'].default_value)
            color=special if emphasis and ui.highlight_override else base
            for mat in mats:
                bsdf=mat.node_tree.nodes.get('Principled BSDF')
                if bsdf:bsdf.inputs['Base Color'].default_value=(*color,1);bsdf.inputs['Emission Color'].default_value=(*color,1)

class DetectorSettings(bpy.types.PropertyGroup):
    data_available: BoolProperty(default=False)
    geometry_available: BoolProperty(default=False)
    event_track_count: IntProperty(default=0)
    event_cluster_count: IntProperty(default=0)
    data: BoolProperty(name='Event data',default=True,update=selection_update)
    mode: EnumProperty(name='Objects',items=[(v,v,'') for v in ('tracks','clusters','both')],update=selection_update)
    visible: BoolProperty(name='Surface',default=True,update=appearance_update)
    detail: EnumProperty(name='Geometry detail',items=[('inherit','Use scene detail','Use the Geometry detail control above'),('full','Full geometry','Keep aligned detector surfaces'),('simplified','Simplified geometry','Use approximate coarse spatial cells')],default='inherit')
    opening: FloatProperty(name='Opening (degrees)',min=0,max=360,default=0,update=appearance_update)
    opacity: FloatProperty(name='Opacity',min=0,max=1,default=.18,update=appearance_update)
    display: EnumProperty(name='Appearance',items=[('surfaces','Existing surfaces','Keep the current aligned surfaces or simplified cells'),('shell','Outer shell','Approximate outer hull; removes internal structures and openings'),('outline','Outline','Edges of the approximate outer hull')])
    color: FloatVectorProperty(name='Colour',subtype='COLOR',size=3,min=0,max=1,default=(.02,.04,.2),update=appearance_update)

COLOR_ITEMS=[(name,name,'0 = standalone fitted source; 1 = composite matched source (e.g. ITS-TPC); grey = unknown' if name=='matching' else '') for name in COLOR_FIELDS]
class SceneSettings(bpy.types.PropertyGroup):
    detectors: CollectionProperty(type=DetectorSettings)
    geometry_lod: EnumProperty(name='Geometry detail',items=[('full','Full aligned surfaces','Preserve the actual detector geometry'),('simplified','Coarse cells','Reduce complexity; approximate bounding cells')])
    mode: EnumProperty(name='Set all object modes',items=[(v,v,'') for v in ('tracks','clusters','both')],update=set_all_modes)
    track_width_cm: FloatProperty(name='Track linewidth (cm)',min=.002,max=20,default=.24,precision=3,update=appearance_update)
    cluster_radius_cm: FloatProperty(name='Cluster radius (cm)',min=.001,max=20,default=.35,update=selection_update)
    highlight_ids: StringProperty(name='Special track IDs',description='Comma-separated event track IDs; Ctrl-click adds, Shift-click toggles',update=selection_update)
    highlight_width_cm: FloatProperty(name='Special track linewidth (cm)',min=.002,max=20,default=.7,update=appearance_update)
    highlight_cluster_radius_cm: FloatProperty(name='Linked cluster radius (cm)',min=.001,max=20,default=1.,update=selection_update)
    highlight_override: BoolProperty(name='Use special colours',default=True,update=appearance_update)
    highlight_track_color: FloatVectorProperty(name='Special tracks',subtype='COLOR',size=3,min=0,max=1,update=appearance_update)
    highlight_cluster_color: FloatVectorProperty(name='Linked clusters',subtype='COLOR',size=3,min=0,max=1,update=appearance_update)
    picking_active: BoolProperty(default=False)
    clip_tracks: BoolProperty(name='Clip tracks to selected detectors',default=True,update=selection_update)
    track_mode: EnumProperty(name='Track coding',items=COLOR_ITEMS)
    cluster_mode: EnumProperty(name='Cluster coding',items=COLOR_ITEMS)
    palette: EnumProperty(name='Palette',items=lambda self,context:PALETTE_ITEMS)
    track_min: FloatProperty(name='Minimum');track_max: FloatProperty(name='Maximum',default=1)
    cluster_min: FloatProperty(name='Minimum');cluster_max: FloatProperty(name='Maximum',default=1)
    track_color: FloatVectorProperty(name='Tracks',subtype='COLOR',size=3,min=0,max=1,update=appearance_update)
    cluster_color: FloatVectorProperty(name='Clusters',subtype='COLOR',size=3,min=0,max=1,update=appearance_update)
    background: FloatVectorProperty(name='Background',subtype='COLOR',size=3,min=0,max=1,update=appearance_update)
    world_strength: FloatProperty(name='Background light',min=0,max=20,default=.45,update=appearance_update)
    roughness: FloatProperty(name='Roughness',min=0,max=1,default=.38,update=appearance_update)
    metallic: FloatProperty(name='Metallic',min=0,max=1,default=.15,update=appearance_update)
    shading: EnumProperty(name='Shading',items=[('smooth','Smooth',''),('flat','Flat','')],update=appearance_update)
    export_path: StringProperty(name='Config',subtype='FILE_PATH')
    include_defaults: BoolProperty(name='Include local input/event defaults',default=False)

class ApplyData(bpy.types.Operator):
    bl_idname='alice_eve.apply_data';bl_label='Apply data selection / colour coding'
    def execute(self,context):
        try:
            from worker import tracks,clusters,remove_owned_collection
            cfg=current_settings().to_dict();selected=set(cfg['detectors'])
            cfg['_track_regions']=JOB.get('track_regions',{})
            from alice_renderer.track_clipping import selected_track_detectors
            missing={d for t in EVENT['tracks'] for d in selected_track_detectors(cfg,t) if d not in cfg['_track_regions']} if cfg['clip_tracks'] and bool(enabled_detectors(cfg,'tracks')) else set()
            if missing:
                from worker import imported_geometry
                for name in missing:
                    asset=cfg['geometry_assets'].get(name)
                    if not asset:raise ValueError(name+': provide its aligned geometry before selecting clipped tracks')
                    cfg['_track_regions'][name]=imported_geometry(name,asset,cfg,bounds_only=True)
                JOB['track_regions']=cfg['_track_regions']
            ts=selected_tracks(EVENT,cfg);cs=selected_clusters(EVENT,cfg)
            for kind,mode,objects,active in [('tracks',cfg['track_color_mode'],ts,bool(enabled_detectors(cfg,'tracks'))),('clusters',cfg['cluster_color_mode'],cs,bool(enabled_detectors(cfg,'clusters')))]:
                if active and selected and mode not in capabilities(objects):raise ValueError(f'{mode} is unavailable for {kind} in selected data')
            for name in ('Tracks','Clusters'):
                old=bpy.data.collections.get(name)
                if old:remove_owned_collection(old)
            if bool(enabled_detectors(cfg,'tracks')):tracks(ts,cfg)
            else:
                from worker import collection
                collection('Tracks')
            clusters(cs,cfg);JOB['applied_track_signature']=track_signature(context.scene.alice_eve);appearance_update(self,context)
            self.report({'INFO'},'Data selection and fixed colour ranges applied')
            return {'FINISHED'}
        except Exception as exc:self.report({'ERROR'},str(exc));return {'CANCELLED'}

class ApplyGeometry(bpy.types.Operator):
    bl_idname='alice_eve.apply_geometry';bl_label='Apply geometry appearance'
    def execute(self,context):
        try:
            from worker import imported_geometry,envelope,remove_owned_collection
            cfg=current_settings().to_dict();cfg['_interactive']=True
            for item in context.scene.alice_eve.detectors:
                if not item.geometry_available:continue
                old=bpy.data.collections.get(item.name)
                if old and old.get('alice_display')==item.display and old.get('alice_geometry_lod')==cfg['geometry_lods'].get(item.name,cfg['geometry_lod']):continue
                if old:remove_owned_collection(old)
                if cfg['schematic']:envelope(item.name,cfg)
                else:imported_geometry(item.name,cfg['geometry_assets'][item.name],cfg)
            appearance_update(self,context)
            self.report({'INFO'},'Geometry appearance applied; shell/outline are approximate outer hulls')
            return {'FINISHED'}
        except Exception as exc:self.report({'ERROR'},str(exc));return {'CANCELLED'}

class SelectNoDetectors(bpy.types.Operator):
    bl_idname='alice_eve.select_no_detectors';bl_label='Select no detectors'
    def execute(self,context):
        for item in context.scene.alice_eve.detectors:item.data=False;item.visible=False
        return bpy.ops.alice_eve.apply_data()

class CompleteGeometry(bpy.types.Operator):
    bl_idname='alice_eve.complete_geometry';bl_label='Show complete detectors'
    def execute(self,context):
        for item in context.scene.alice_eve.detectors:item.opening=0
        return {'FINISHED'}

class FullAlignedGeometry(bpy.types.Operator):
    bl_idname='alice_eve.full_geometry';bl_label='Full aligned surfaces'
    def execute(self,context):
        ui=context.scene.alice_eve;ui.geometry_lod='full'
        for item in ui.detectors:item.display='surfaces';item.detail='inherit'
        return bpy.ops.alice_eve.apply_geometry()

class OpaqueGeometry(bpy.types.Operator):
    bl_idname='alice_eve.opaque_geometry';bl_label='Make geometry opaque'
    def execute(self,context):
        for item in context.scene.alice_eve.detectors:
            if item.geometry_available:item.opacity=1.
        return {'FINISHED'}

class CameraFromView(bpy.types.Operator):
    bl_idname='alice_eve.camera_from_view';bl_label='Use current view as camera'
    bl_description='Capture this viewport as the render camera; an existing camera view is already captured'
    def execute(self,context):
        area=context.area
        if not area or area.type!='VIEW_3D':
            self.report({'ERROR'},'Use this button in a 3D viewport');return {'CANCELLED'}
        region=next((r for r in area.regions if r.type=='WINDOW'),None)
        if region is None or not context.scene.camera:
            self.report({'ERROR'},'A 3D viewport and a scene camera are required');return {'CANCELLED'}
        if area.spaces.active.region_3d.view_perspective=='CAMERA':
            self.report({'INFO'},'Already viewing the render camera');return {'FINISHED'}
        with context.temp_override(area=area,region=region):
            if not bpy.ops.view3d.camera_to_view.poll():
                self.report({'ERROR'},'This viewport cannot be captured as the camera');return {'CANCELLED'}
            bpy.ops.view3d.camera_to_view()
        return {'FINISHED'}

class LevelCamera(bpy.types.Operator):
    bl_idname='alice_eve.level_camera';bl_label='Level camera (Y up)'
    bl_description='Remove camera roll using ALICE Y as vertical and XZ as the horizontal plane; retain camera position and viewing direction'
    def execute(self,context):
        from mathutils import Vector,Matrix
        camera=context.scene.camera
        if not camera:return {'CANCELLED'}
        direction=camera.rotation_euler.to_matrix() @ Vector((0,0,-1))
        vertical=Vector((0,1,0))
        if abs(direction.dot(vertical))>.999:vertical=Vector((0,0,1))
        right=direction.cross(vertical).normalized();up=right.cross(direction)
        camera.rotation_euler=Matrix(((right.x,up.x,-direction.x),(right.y,up.y,-direction.y),(right.z,up.z,-direction.z))).to_euler()
        if context.area:context.area.tag_redraw()
        return {'FINISHED'}

class ExportConfig(bpy.types.Operator):
    bl_idname='alice_eve.export';bl_label='Export config'
    def execute(self,context):
        try:
            ui=context.scene.alice_eve;cfg=current_settings()
            selected=set(cfg.detectors)
            for kind,mode,active in [('tracks',cfg.track_color_mode,bool(enabled_detectors(cfg.to_dict(),'tracks'))),('clusters',cfg.cluster_color_mode,bool(enabled_detectors(cfg.to_dict(),'clusters')))]:
                objects=selected_tracks(EVENT,cfg.to_dict()) if kind=='tracks' else selected_clusters(EVENT,cfg.to_dict())
                if active and selected and mode not in capabilities(objects):raise ValueError(f'{mode} is unavailable for selected {kind}')
            if bpy.ops.alice_eve.apply_data()!={'FINISHED'}:return {'CANCELLED'}
            if bpy.ops.alice_eve.apply_geometry()!={'FINISHED'}:return {'CANCELLED'}
            data=recipe(cfg)
            if ui.include_defaults:data['defaults']={'input':JOB['event'],'event':str(EVENT['id'])}
            save_config(bpy.path.abspath(ui.export_path),data)
            self.report({'INFO'},'Portable scene exported');return {'FINISHED'}
        except Exception as exc:self.report({'ERROR'},str(exc));return {'CANCELLED'}

DETAIL_ITEMS=[('full','Full geometry','Keep the aligned detector surfaces'),('simplified','Simplified geometry','Approximate coarse spatial cells; less geometry to render')]

class RenderGeometryDetail(bpy.types.PropertyGroup):
    detail: EnumProperty(name='Geometry detail',items=DETAIL_ITEMS,default='full')

def initialize_render_geometry(operator,cfg):
    operator.geometry_details.clear()
    for name in cfg.geometry+(['L3'] if cfg.magnet else []):
        item=operator.geometry_details.add();item.name=name;item.detail=cfg.geometry_lods.get(name,cfg.geometry_lod)

def render_geometry_settings(cfg,items):
    from dataclasses import replace
    selected=set(cfg.geometry+(['L3'] if cfg.magnet else []))
    overrides={**cfg.geometry_lods,**{i.name:i.detail for i in items if i.name in selected}}
    return replace(cfg,geometry_lods=overrides).validate()

class RenderFull(bpy.types.Operator):
    bl_idname='alice_eve.render_full';bl_label='Render full'
    bl_description='Choose image quality and geometry detail for each selected detector and L3, then start a full render'
    geometry_details: CollectionProperty(type=RenderGeometryDetail)
    quality: EnumProperty(name='Quality',items=[(v,v.title(),'') for v in ('draft','balanced','final','publication','custom')])
    backend: EnumProperty(name='Backend',items=[('AUTO','Recommended','')]+[(v,v,'') for v in ('CPU','METAL','HIP','CUDA','OPTIX')])
    width: IntProperty(name='Width',default=1920,min=64,max=16384)
    samples: IntProperty(name='Samples',default=128,min=1,max=8192)
    output: StringProperty(name='Output folder',subtype='DIR_PATH')
    def invoke(self,context,event):
        self.quality=RECOMMENDATION['quality'];self.output=JOB['render_output']
        initialize_render_geometry(self,current_settings())
        return context.window_manager.invoke_props_dialog(self,width=480)
    def draw(self,context):
        layout=self.layout;layout.label(text=RECOMMENDATION['reason']);layout.prop(self,'quality');layout.prop(self,'backend')
        if self.quality=='custom':layout.prop(self,'width');layout.prop(self,'samples')
        box=layout.box();box.label(text='Geometry detail for this render')
        for item in self.geometry_details:box.prop(item,'detail',text=item.name)
        if not self.geometry_details:box.label(text='No detector surfaces or magnet selected')
        box.label(text='Full preserves surfaces; simplified uses coarse cells.')
        box.label(text='Chosen shell/outline appearance is preserved.')
        layout.prop(self,'output')
    def execute(self,context):
        try:
            ui=context.scene.alice_eve
            if ExportConfig.execute(self,context)!={'FINISHED'}:return {'CANCELLED'}
            backend=RECOMMENDATION['backend'] if self.backend=='AUTO' else self.backend
            if not any(d['type']==backend for d in DEVICES['devices']):raise ValueError(f'{backend} is unavailable. Choose an available backend before rendering.')
            from alice_renderer.runtime import preflight
            from alice_renderer.scene_config import quality_settings
            check=quality_settings(current_settings(),'balanced' if self.quality=='custom' else self.quality,backend=backend,width=self.width if self.quality=='custom' else None,samples=self.samples if self.quality=='custom' else None)
            check=render_geometry_settings(check,self.geometry_details)
            errors=preflight(check,[EVENT],DEVICES,Path(bpy.path.abspath(self.output)))
            if errors:raise ValueError('\n'.join(errors))
            root=Path(JOB['output']);path=root/'full-render-config.json'
            data=recipe(check)
            if ui.include_defaults:data['defaults']={'input':JOB['event'],'event':str(EVENT['id'])}
            save_config(path,data)
            asset_map=root/'render-assets.local.json';asset_map.write_text(json.dumps(JOB['settings']['geometry_assets']))
            command=[JOB['python'],'-m','alice_renderer.cli','render-config',str(path),'--input',JOB['event'],'--event',str(EVENT['id']),'--assets',str(asset_map),'--blender',bpy.app.binary_path,'--backend',backend,'--quality','balanced' if self.quality=='custom' else self.quality,'--output',bpy.path.abspath(self.output)]
            if self.quality=='custom':command+=['--width',str(self.width),'--samples',str(self.samples)]
            with (root/'full-render.log').open('w') as log:subprocess.Popen(command,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
            self.report({'INFO'},'Full render started; progress in '+str(root/'full-render.log'));return {'FINISHED'}
        except Exception as exc:self.report({'ERROR'},str(exc));return {'CANCELLED'}

class RollCamera(bpy.types.Operator):
    bl_idname='alice_eve.roll_camera';bl_label='Roll camera'
    angle: FloatProperty(name='Roll (degrees)',default=15.)
    def execute(self,context):
        from mathutils import Matrix
        context.scene.camera.matrix_world=context.scene.camera.matrix_world @ Matrix.Rotation(math.radians(self.angle),4,'Z')
        if context.area:context.area.tag_redraw()
        return {'FINISHED'}


def pick_displayed_track(area,region,mouse):
    import numpy as np
    from alice_renderer.picking import projected_hit
    coll=bpy.data.collections.get('Tracks')
    if not coll:return None
    best=None
    for obj in coll.objects:
        if obj.type!='CURVE' or obj.hide_get() or obj.hide_render:continue
        ids=json.loads(obj.get('alice_track_ids_json','[]'))
        matrix=np.array(area.spaces.active.region_3d.perspective_matrix @ obj.matrix_world)
        for index,spline in enumerate(obj.data.splines):
            if index>=len(ids):continue
            coords=np.empty(len(spline.points)*4,dtype=np.float32);spline.points.foreach_get('co',coords)
            hit=projected_hit(mouse,coords.reshape(-1,4),matrix,region.width,region.height)
            if hit is not None:
                rank=(round(hit[0],6),hit[1])
                if best is None or rank<best[0]:best=(rank,ids[index])
    return None if best is None else best[1]

class PickTracks(bpy.types.Operator):
    bl_idname='alice_eve.pick_tracks';bl_label='Pick tracks with mouse'
    bl_description='Start or stop mouse picking of displayed tracks; Ctrl-click adds, Shift-click toggles, and Esc stops'
    @classmethod
    def description(cls,context,properties):
        if hasattr(context.scene,'alice_eve') and context.scene.alice_eve.picking_active:
            return 'Stop selecting tracks with the mouse and return to normal viewport controls (Esc also stops)'
        return 'Click a displayed track to select its ID; Ctrl-click adds, Shift-click toggles, and Esc stops'
    def invoke(self,context,event):
        ui=context.scene.alice_eve
        if ui.picking_active:ui.picking_active=False;return {'FINISHED'}
        if not context.area or context.area.type!='VIEW_3D':self.report({'ERROR'},'Use picking from a 3D view');return {'CANCELLED'}
        self.area=context.area;self.region=next(r for r in context.area.regions if r.type=='WINDOW')
        ui.picking_active=True;context.window.cursor_modal_set('CROSSHAIR');context.window_manager.modal_handler_add(self)
        self.report({'INFO'},'Click a track. Ctrl-click adds; Shift-click toggles. Esc stops picking.')
        return {'RUNNING_MODAL'}
    def finish(self,context):
        context.scene.alice_eve.picking_active=False;context.window.cursor_modal_restore();self.area.tag_redraw()
        return {'FINISHED'}
    def modal(self,context,event):
        ui=context.scene.alice_eve
        if not ui.picking_active or event.type=='ESC':return self.finish(context)
        if event.type=='LEFTMOUSE' and event.value=='PRESS':
            x=event.mouse_x-self.region.x;y=event.mouse_y-self.region.y
            if not 0<=x<self.region.width or not 0<=y<self.region.height:return {'PASS_THROUGH'}
            id_=pick_displayed_track(self.area,self.region,(x,y))
            if id_ is None:self.report({'INFO'},'No displayed track near that point');return {'RUNNING_MODAL'}
            ids=parse_track_ids(ui.highlight_ids) if event.ctrl or event.shift else []
            if event.shift and id_ in ids:ids.remove(id_)
            elif id_ not in ids:ids.append(id_)
            ui.highlight_ids=', '.join(ids);self.report({'INFO'},'Track ID '+id_);self.area.tag_redraw()
            return {'RUNNING_MODAL'}
        return {'PASS_THROUGH'}

class StopPicking(bpy.types.Operator):
    bl_idname='alice_eve.stop_picking';bl_label='Stop picking'
    bl_description='Stop mouse selection of tracks and restore normal viewport controls; Esc also stops picking'
    def execute(self,context):
        context.scene.alice_eve.picking_active=False
        if context.window:context.window.cursor_modal_restore()
        if context.area:context.area.tag_redraw()
        return {'FINISHED'}

class EVEPanel(bpy.types.Panel):
    bl_label='ALICE-EVE scene';bl_idname='ALICE_PT_scene';bl_space_type='VIEW_3D';bl_region_type='UI';bl_category='ALICE EVE'
    def draw(self,context):
        layout=self.layout;ui=context.scene.alice_eve
        layout.label(text='Aligned detector geometry')
        layout.prop(ui,'geometry_lod');layout.operator('alice_eve.full_geometry')
        layout.operator('alice_eve.select_no_detectors');layout.operator('alice_eve.complete_geometry')
        layout.label(text='Outer shell / outline are approximate hulls.')
        layout.label(text='Orbit/pan/zoom, then use view as camera.')
        layout.operator('alice_eve.camera_from_view');layout.operator('alice_eve.level_camera');layout.prop(context.scene.camera,'rotation_euler')
        row=layout.row();row.operator('alice_eve.roll_camera',text='Roll −15°').angle=-15;row.operator('alice_eve.roll_camera',text='Roll +15°').angle=15
        layout.label(text='Trackball navigation permits arbitrary orientation.')
        if EVENT.get('contributors') is not None:layout.label(text='Primary vertex contributors: '+str(EVENT['contributors']))
        layout.label(text='Detector counts refer to input fitted records.')
        layout.prop(context.scene.camera.data,'type');layout.prop(context.scene.camera.data,'lens');layout.prop(context.scene.camera.data,'ortho_scale')
        layout.operator('alice_eve.opaque_geometry');layout.operator('alice_eve.apply_geometry')
        layout.prop(ui,'mode');layout.prop(ui,'track_width_cm');layout.prop(ui,'cluster_radius_cm');layout.prop(ui,'clip_tracks');layout.prop(ui,'track_color');layout.prop(ui,'cluster_color')
        box=layout.box();box.label(text='Track emphasis / decay chain');box.prop(ui,'highlight_ids')
        if ui.picking_active:box.operator('alice_eve.stop_picking',text='Stop picking (Esc)')
        else:box.operator('alice_eve.pick_tracks')
        box.prop(ui,'highlight_width_cm');box.prop(ui,'highlight_cluster_radius_cm');box.prop(ui,'highlight_override');box.prop(ui,'highlight_track_color');box.prop(ui,'highlight_cluster_color')
        for kind in ('track','cluster'):
            box=layout.box();box.prop(ui,kind+'_mode');row=box.row();row.prop(ui,kind+'_min');row.prop(ui,kind+'_max')
        layout.prop(ui,'palette');layout.operator('alice_eve.apply_data')
        for item in ui.detectors:
            box=layout.box();box.label(text=f'{item.name}: {item.event_track_count} tracks / {item.event_cluster_count} clusters' if item.data_available else item.name)
            row=box.row();row.enabled=item.data_available;row.prop(item,'data');row.prop(item,'mode')
            row=box.row();row.enabled=item.geometry_available;row.prop(item,'visible')
            if item.geometry_available:
                box.prop(item,'detail');box.prop(item,'display');box.prop(item,'opening');box.prop(item,'color');box.prop(item,'opacity')
        layout.prop(ui,'background');layout.prop(ui,'world_strength');layout.prop(ui,'roughness');layout.prop(ui,'metallic');layout.prop(ui,'shading')
        for lamp in (o for o in context.scene.objects if o.type=='LIGHT'):
            box=layout.box();box.label(text=lamp.name);box.prop(lamp,'location');box.prop(lamp,'rotation_euler');box.prop(lamp.data,'energy');box.prop(lamp.data,'size');box.prop(lamp.data,'color')
        layout.prop(ui,'export_path');layout.prop(ui,'include_defaults')
        row=layout.row();row.operator('alice_eve.export');row.operator('alice_eve.render_full')

CLASSES=(DetectorSettings,SceneSettings,RenderGeometryDetail,ApplyData,ApplyGeometry,SelectNoDetectors,CompleteGeometry,FullAlignedGeometry,OpaqueGeometry,CameraFromView,LevelCamera,RollCamera,PickTracks,StopPicking,ExportConfig,RenderFull,EVEPanel)

def start_editor(job,event,metadata):
    global JOB,EVENT,DEVICES,RECOMMENDATION,PALETTES
    PALETTES=job.get('palettes',{})
    if not PALETTES:
        from worker import scale_color
        PALETTES={name:[list(scale_color(i/255,0,1,name)) for i in range(256)] for name in ('viridis','coolwarm','hsv')}
    if job['settings'].get('palette_lut'):PALETTES[job['settings']['palette']]=job['settings']['palette_lut']
    PALETTE_ITEMS[:]=[(name,name,'') for name in sorted(PALETTES)]
    EVENT=event;DEVICES=job['blender'];RECOMMENDATION=recommended_quality(DEVICES)
    for cls in CLASSES:bpy.utils.register_class(cls)
    bpy.types.Scene.alice_eve=bpy.props.PointerProperty(type=SceneSettings)
    scene=bpy.context.scene;ui=scene.alice_eve;settings=job['settings']
    # Suppress updates during property initialization.
    from worker import rgb
    ui.cluster_radius_cm=settings['cluster_radius_cm'];ui.highlight_ids=', '.join(settings.get('highlight_track_ids',[]));ui.highlight_width_cm=settings.get('highlight_track_radius_cm',.35)*2;ui.highlight_cluster_radius_cm=settings.get('highlight_cluster_radius_cm',1.);ui.highlight_override=settings.get('highlight_override_color',True);ui.highlight_track_color=rgb(settings.get('highlight_track_color','#ffcc33'));ui.highlight_cluster_color=rgb(settings.get('highlight_cluster_color','#ff6633'))
    ui.track_width_cm=settings['track_radius_cm']*2;ui.clip_tracks=settings.get('clip_tracks',True)
    ui.geometry_lod=settings.get('geometry_lod','full')
    ui.mode=settings['mode'];ui.track_mode=settings['track_color_mode'];ui.cluster_mode=settings['cluster_color_mode'];ui.palette=settings['palette']
    ui.background=settings.get('colors_linear',{}).get('background',rgb(settings['colors']['background']));ui.track_color=settings.get('colors_linear',{}).get('tracks',rgb(settings['colors']['tracks']));ui.cluster_color=settings.get('colors_linear',{}).get('clusters',rgb(settings['colors']['clusters']))
    ui.world_strength=settings['world_strength'];ui.roughness=settings['roughness'];ui.metallic=settings['metallic'];ui.shading=settings['shading']
    available=set(event.get('data_detectors',[]))|{d for t in event['tracks'] for d in t['detectors']}|{c['detector'] for c in event['clusters']}
    counts=event_counts(event);track_counts=counts['tracks_by_detector'];cluster_counts=counts['clusters_by_detector']
    from alice_renderer.model import DETECTORS
    for name in (*DETECTORS,'L3'):
        item=ui.detectors.add();item.name=name;item.data_available=name in available;item.data=name in settings['detectors'];item.mode=settings.get('detector_modes',{}).get(name,settings['mode']);item.geometry_available=name in settings['geometry'] or name=='L3' and settings['magnet'];item.visible=item.geometry_available
        item.display=settings.get('geometry_display',{}).get(name,'surfaces')
        item.detail=settings.get('geometry_lods',{}).get(name,'inherit')
        item.event_track_count=track_counts.get(name,0);item.event_cluster_count=cluster_counts.get(name,0)
        item.opening=settings['geometry_openings'].get(name,180 if settings['cutaway'] else 0);item.opacity=settings['geometry_opacities'].get(name,settings['geometry_opacity']);item.color=settings.get('colors_linear',{}).get('magnet' if name=='L3' else name,rgb(settings['colors'].get('magnet' if name=='L3' else name,'#243a82')))
    settings['palette_lut']=PALETTES[settings['palette']]
    locked=recipe(RenderSettings(**settings),event)['scene']['color_ranges']
    ui.track_min,ui.track_max=locked['tracks'];ui.cluster_min,ui.cluster_max=locked['clusters']
    ui.export_path=str(Path(job['output'])/'scene-config.json')
    JOB=job;JOB['applied_track_signature']=track_signature(ui);appearance_update(ui,bpy.context)
    bpy.context.preferences.inputs.view_rotate_method='TRACKBALL'
    scene.render.engine='BLENDER_EEVEE';scene.render.resolution_percentage=100
    for screen in bpy.data.screens:
        for area in screen.areas:
            if area.type=='VIEW_3D':
                area.spaces.active.show_region_ui=True;area.spaces.active.shading.type='RENDERED';area.spaces.active.region_3d.view_perspective='CAMERA'
    bpy.context.view_layer.objects.active=scene.camera
    for obj in scene.objects:obj.select_set(False)
    scene.camera.select_set(True)
    bpy.ops.wm.save_as_mainfile(filepath=str(Path(job['output'])/'interactive.blend'))
