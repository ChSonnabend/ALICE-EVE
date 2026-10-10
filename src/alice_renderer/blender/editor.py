"""Blender sidebar for interactive ALICE-EVE scene editing and portable export."""
import copy, json, math, subprocess
from pathlib import Path
import bpy
from bpy.props import BoolProperty, CollectionProperty, EnumProperty, FloatProperty, FloatVectorProperty, IntProperty, StringProperty
from alice_renderer.model import RenderSettings, COLOR_FIELDS, capabilities
from alice_renderer.scene_config import recipe, save_config, recommended_quality

JOB=None
EVENT=None
DEVICES=None
RECOMMENDATION=None


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
    cfg['geometry_openings']={};cfg['geometry_opacities']={};cfg['colors_linear']={}
    for item in ui.detectors:
        if item.data and item.data_available:cfg['detectors'].append(item.name)
        if item.visible and item.geometry_available:
            if item.name=='L3':cfg['magnet']=True
            else:cfg['geometry'].append(item.name)
        cfg['geometry_openings'][item.name]=item.opening
        cfg['geometry_opacities'][item.name]=item.opacity
        cfg['colors']['magnet' if item.name=='L3' else item.name]=hex_color(item.color)
        cfg['colors_linear']['magnet' if item.name=='L3' else item.name]=list(item.color)
    cfg['colors']['background']=hex_color(ui.background)
    cfg['colors']['tracks']=hex_color(ui.track_color);cfg['colors']['clusters']=hex_color(ui.cluster_color)
    cfg['colors_linear'].update(background=list(ui.background),tracks=list(ui.track_color),clusters=list(ui.cluster_color))
    cfg['world_strength']=ui.world_strength;cfg['roughness']=ui.roughness;cfg['metallic']=ui.metallic;cfg['shading']=ui.shading
    cfg['mode']=ui.mode;cfg['track_color_mode']=ui.track_mode;cfg['cluster_color_mode']=ui.cluster_mode;cfg['palette']=ui.palette
    cfg['color_ranges']={'tracks':[ui.track_min,ui.track_max],'clusters':[ui.cluster_min,ui.cluster_max]}
    cfg['scale_min']=None;cfg['scale_max']=None
    cfg['lights']=[{'position_m':list(o.location),'rotation':list(o.rotation_euler),'energy':o.data.energy,'size_m':o.data.size,'color':hex_color(o.data.color),'color_linear':list(o.data.color)} for o in scene.objects if o.type=='LIGHT' and o.data.type=='AREA']
    return RenderSettings(**cfg).validate()

def appearance_update(self,context):
    if not JOB or not hasattr(context.scene,'alice_eve'):return
    ui=context.scene.alice_eve
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
        mats={m for obj in coll.all_objects if obj.type=='MESH' for m in obj.data.materials if m} if coll else set()
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
        if (ui.track_mode if kind=='Tracks' else ui.cluster_mode)=='solid':
            for mat in bpy.data.materials:
                if mat.name.startswith('Track solid' if kind=='Tracks' else 'Cluster solid') and mat.use_nodes:
                    color=ui.track_color if kind=='Tracks' else ui.cluster_color
                    bsdf=mat.node_tree.nodes.get('Principled BSDF');bsdf.inputs['Base Color'].default_value=(*color,1);bsdf.inputs['Emission Color'].default_value=(*color,1)

        coll=bpy.data.collections.get(kind)
        if coll:coll.hide_render=coll.hide_viewport=(ui.mode=='clusters' if kind=='Tracks' else ui.mode=='tracks')

class DetectorSettings(bpy.types.PropertyGroup):
    data_available: BoolProperty(default=False)
    geometry_available: BoolProperty(default=False)
    data: BoolProperty(name='Event data',default=True)
    visible: BoolProperty(name='Surface',default=True,update=appearance_update)
    opening: FloatProperty(name='Opening (degrees)',min=0,max=360,default=180,update=appearance_update)
    opacity: FloatProperty(name='Opacity',min=0,max=1,default=.18,update=appearance_update)
    color: FloatVectorProperty(name='Colour',subtype='COLOR',size=3,min=0,max=1,default=(.02,.04,.2),update=appearance_update)

COLOR_ITEMS=[(name,name,'') for name in COLOR_FIELDS]
class SceneSettings(bpy.types.PropertyGroup):
    detectors: CollectionProperty(type=DetectorSettings)
    mode: EnumProperty(name='Objects',items=[(v,v,'') for v in ('tracks','clusters','both')],update=appearance_update)
    track_mode: EnumProperty(name='Track coding',items=COLOR_ITEMS)
    cluster_mode: EnumProperty(name='Cluster coding',items=COLOR_ITEMS)
    palette: EnumProperty(name='Palette',items=[(v,v,'') for v in ('viridis','coolwarm','hsv')])
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
            from worker import tracks,clusters
            cfg=current_settings().to_dict();selected=set(cfg['detectors'])
            ts=[t for t in EVENT['tracks'] if selected.intersection(t['detectors'])];cs=[c for c in EVENT['clusters'] if c['detector'] in selected]
            for kind,mode,objects in [('tracks',cfg['track_color_mode'],ts),('clusters',cfg['cluster_color_mode'],cs)]:
                if mode not in capabilities(objects):raise ValueError(f'{mode} is unavailable for {kind} in selected data')
            for name in ('Tracks','Clusters'):
                old=bpy.data.collections.get(name)
                if old:
                    for obj in list(old.objects):bpy.data.objects.remove(obj,do_unlink=True)
                    bpy.data.collections.remove(old)
            tracks(ts,cfg);clusters(cs,cfg);appearance_update(self,context)
            self.report({'INFO'},'Data selection and fixed colour ranges applied')
            return {'FINISHED'}
        except Exception as exc:self.report({'ERROR'},str(exc));return {'CANCELLED'}

class CameraFromView(bpy.types.Operator):
    bl_idname='alice_eve.camera_from_view';bl_label='Use current view as camera'
    def execute(self,context):
        bpy.ops.view3d.camera_to_view();return {'FINISHED'}

class ExportConfig(bpy.types.Operator):
    bl_idname='alice_eve.export';bl_label='Export config'
    def execute(self,context):
        try:
            ui=context.scene.alice_eve;cfg=current_settings()
            selected=set(cfg.detectors)
            for kind,mode,active in [('tracks',cfg.track_color_mode,cfg.mode!='clusters'),('clusters',cfg.cluster_color_mode,cfg.mode!='tracks')]:
                objects=[o for o in EVENT[kind] if selected.intersection(o['detectors'])] if kind=='tracks' else [o for o in EVENT[kind] if o['detector'] in selected]
                if active and mode not in capabilities(objects):raise ValueError(f'{mode} is unavailable for selected {kind}')
            data=recipe(cfg)
            if ui.include_defaults:data['defaults']={'input':JOB['event'],'event':str(EVENT['id'])}
            save_config(bpy.path.abspath(ui.export_path),data)
            self.report({'INFO'},'Portable scene exported');return {'FINISHED'}
        except Exception as exc:self.report({'ERROR'},str(exc));return {'CANCELLED'}

class RenderFull(bpy.types.Operator):
    bl_idname='alice_eve.render_full';bl_label='Render full'
    quality: EnumProperty(name='Quality',items=[(v,v.title(),'') for v in ('draft','balanced','final','publication','custom')])
    backend: EnumProperty(name='Backend',items=[('AUTO','Recommended','')]+[(v,v,'') for v in ('CPU','METAL','HIP','CUDA','OPTIX')])
    width: IntProperty(name='Width',default=1920,min=64,max=16384)
    samples: IntProperty(name='Samples',default=128,min=1,max=8192)
    output: StringProperty(name='Output folder',subtype='DIR_PATH')
    def invoke(self,context,event):
        self.quality=RECOMMENDATION['quality'];self.output=JOB['render_output']
        return context.window_manager.invoke_props_dialog(self,width=480)
    def draw(self,context):
        layout=self.layout;layout.label(text=RECOMMENDATION['reason']);layout.prop(self,'quality');layout.prop(self,'backend')
        if self.quality=='custom':layout.prop(self,'width');layout.prop(self,'samples')
        layout.prop(self,'output');layout.label(text='Same scene surfaces; quality changes only image size and samples.')
    def execute(self,context):
        try:
            ui=context.scene.alice_eve;path=Path(bpy.path.abspath(ui.export_path)).resolve()
            if ExportConfig.execute(self,context)!={'FINISHED'}:return {'CANCELLED'}
            backend=RECOMMENDATION['backend'] if self.backend=='AUTO' else self.backend
            if not any(d['type']==backend for d in DEVICES['devices']):raise ValueError(f'{backend} is unavailable. Choose an available backend before rendering.')
            from alice_renderer.runtime import preflight
            from alice_renderer.scene_config import quality_settings
            check=quality_settings(current_settings(),'balanced' if self.quality=='custom' else self.quality,backend=backend,width=self.width if self.quality=='custom' else None,samples=self.samples if self.quality=='custom' else None)
            errors=preflight(check,[EVENT],DEVICES,Path(bpy.path.abspath(self.output)))
            if errors:raise ValueError('\n'.join(errors))
            root=Path(JOB['output']);asset_map=root/'render-assets.local.json';asset_map.write_text(json.dumps(JOB['settings']['geometry_assets']))
            command=[JOB['python'],'-m','alice_renderer.cli','render-config',str(path),'--input',JOB['event'],'--event',str(EVENT['id']),'--assets',str(asset_map),'--blender',bpy.app.binary_path,'--backend',backend,'--quality','balanced' if self.quality=='custom' else self.quality,'--output',bpy.path.abspath(self.output)]
            if self.quality=='custom':command+=['--width',str(self.width),'--samples',str(self.samples)]
            with (root/'full-render.log').open('w') as log:subprocess.Popen(command,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
            self.report({'INFO'},'Full render started; progress in '+str(root/'full-render.log'));return {'FINISHED'}
        except Exception as exc:self.report({'ERROR'},str(exc));return {'CANCELLED'}

class EVEPanel(bpy.types.Panel):
    bl_label='ALICE-EVE scene';bl_idname='ALICE_PT_scene';bl_space_type='VIEW_3D';bl_region_type='UI';bl_category='ALICE EVE'
    def draw(self,context):
        layout=self.layout;ui=context.scene.alice_eve
        layout.label(text='Simplified aligned surfaces (approximation)')
        layout.label(text='Orbit/pan/zoom, then use view as camera.')
        layout.operator('alice_eve.camera_from_view');layout.prop(context.scene.camera.data,'type');layout.prop(context.scene.camera.data,'lens');layout.prop(context.scene.camera.data,'ortho_scale')
        layout.prop(ui,'mode');layout.prop(ui,'track_color');layout.prop(ui,'cluster_color')
        for kind in ('track','cluster'):
            box=layout.box();box.prop(ui,kind+'_mode');row=box.row();row.prop(ui,kind+'_min');row.prop(ui,kind+'_max')
        layout.prop(ui,'palette');layout.operator('alice_eve.apply_data')
        for item in ui.detectors:
            box=layout.box();box.label(text=item.name)
            row=box.row();row.enabled=item.data_available;row.prop(item,'data')
            row=box.row();row.enabled=item.geometry_available;row.prop(item,'visible')
            if item.geometry_available:
                box.prop(item,'opening');box.prop(item,'color');box.prop(item,'opacity')
        layout.prop(ui,'background');layout.prop(ui,'world_strength');layout.prop(ui,'roughness');layout.prop(ui,'metallic');layout.prop(ui,'shading')
        for lamp in (o for o in context.scene.objects if o.type=='LIGHT'):
            box=layout.box();box.label(text=lamp.name);box.prop(lamp,'location');box.prop(lamp,'rotation_euler');box.prop(lamp.data,'energy');box.prop(lamp.data,'size');box.prop(lamp.data,'color')
        layout.prop(ui,'export_path');layout.prop(ui,'include_defaults')
        row=layout.row();row.operator('alice_eve.export');row.operator('alice_eve.render_full')

CLASSES=(DetectorSettings,SceneSettings,ApplyData,CameraFromView,ExportConfig,RenderFull,EVEPanel)

def start_editor(job,event,metadata):
    global JOB,EVENT,DEVICES,RECOMMENDATION
    EVENT=event;DEVICES=job['blender'];RECOMMENDATION=recommended_quality(DEVICES)
    for cls in CLASSES:bpy.utils.register_class(cls)
    bpy.types.Scene.alice_eve=bpy.props.PointerProperty(type=SceneSettings)
    scene=bpy.context.scene;ui=scene.alice_eve;settings=job['settings']
    # Suppress updates during property initialization.
    from worker import rgb
    ui.mode=settings['mode'];ui.track_mode=settings['track_color_mode'];ui.cluster_mode=settings['cluster_color_mode'];ui.palette=settings['palette']
    ui.background=settings.get('colors_linear',{}).get('background',rgb(settings['colors']['background']));ui.track_color=settings.get('colors_linear',{}).get('tracks',rgb(settings['colors']['tracks']));ui.cluster_color=settings.get('colors_linear',{}).get('clusters',rgb(settings['colors']['clusters']))
    ui.world_strength=settings['world_strength'];ui.roughness=settings['roughness'];ui.metallic=settings['metallic'];ui.shading=settings['shading']
    available=set(event.get('data_detectors',[]))|{d for t in event['tracks'] for d in t['detectors']}|{c['detector'] for c in event['clusters']}
    from alice_renderer.model import DETECTORS
    for name in (*DETECTORS,'L3'):
        item=ui.detectors.add();item.name=name;item.data_available=name in available;item.data=name in settings['detectors'];item.geometry_available=name in settings['geometry'] or name=='L3' and settings['magnet'];item.visible=item.geometry_available
        item.opening=settings['geometry_openings'].get(name,180 if settings['cutaway'] else 0);item.opacity=settings['geometry_opacities'].get(name,settings['geometry_opacity']);item.color=settings.get('colors_linear',{}).get('magnet' if name=='L3' else name,rgb(settings['colors'].get('magnet' if name=='L3' else name,'#243a82')))
    locked=recipe(RenderSettings(**settings),event)['scene']['color_ranges']
    ui.track_min,ui.track_max=locked['tracks'];ui.cluster_min,ui.cluster_max=locked['clusters']
    ui.export_path=str(Path(job['output'])/'scene-config.json')
    JOB=job;appearance_update(ui,bpy.context)
    scene.render.engine='BLENDER_EEVEE';scene.render.resolution_percentage=100
    for screen in bpy.data.screens:
        for area in screen.areas:
            if area.type=='VIEW_3D':
                area.spaces.active.show_region_ui=True;area.spaces.active.shading.type='RENDERED';area.spaces.active.region_3d.view_perspective='CAMERA'
    bpy.context.view_layer.objects.active=scene.camera
    for obj in scene.objects:obj.select_set(False)
    scene.camera.select_set(True)
    bpy.ops.wm.save_as_mainfile(filepath=str(Path(job['output'])/'interactive.blend'))
