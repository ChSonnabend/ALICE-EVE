"""Blender sidebar for interactive ALICE-EVE scene editing and portable export."""
import copy, json, math, subprocess, time
from pathlib import Path
import bpy
from bpy.props import BoolProperty, CollectionProperty, EnumProperty, FloatProperty, FloatVectorProperty, IntProperty, StringProperty
from alice_renderer.model import RenderSettings, COLOR_FIELDS, capabilities
from alice_renderer.cluster_colors import CLUSTER_COLOR_FIELDS, DESCRIPTIONS
from alice_renderer.object_selection import parse_track_ids,selected_tracks,selected_clusters,enabled_detectors,event_counts
from alice_renderer.palettes import names as palette_names
from alice_renderer.geometry_selection import is_schematic,final_render_choices,render_geometry_preset,description as geometry_description
from alice_renderer.scene_config import recipe, save_config, recommended_quality
from alice_renderer.resolution import PRESET_PERCENT, percentage_size

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
    cfg['camera_lens_mm']=camera.data.lens
    for key in ('video_enabled','video_timing','video_interval_s','video_time_scale','video_speed_m_s','video_tower_rise_s','video_fps'):cfg[key]=getattr(ui,key)
    from camera_pose import snapshot
    cfg['camera_pose']=snapshot(camera)
    cfg['frame_aspect']=scene.render.resolution_x/scene.render.resolution_y
    cfg['width']=scene.render.resolution_x;cfg['height']=scene.render.resolution_y
    cfg['geometry']=[];cfg['magnet']=False;cfg['detectors']=[]
    cfg['detector_modes']={};cfg['geometry_display']={};cfg['geometry_openings']={};cfg['geometry_opacities']={};cfg['colors_linear']={};cfg['geometry_assets']={}
    cfg['geometry_opening_directions']={};cfg['geometry_exclusions']={}
    cfg['geometry_inner_masks']={};cfg['geometry_components']={}
    for key in ('cluster_size_scales','tower_width_scales','tower_fixed_heights_cm','tower_max_heights_cm','tower_height_mappings','tower_log_references'):cfg[key]={}
    for item in ui.detectors:
        if item.asset_path:cfg['geometry_assets'][item.name]=bpy.path.abspath(item.asset_path)
        if item.data and item.data_available:cfg['detectors'].append(item.name)
        if item.visible and item.geometry_available:
            if item.name=='L3':cfg['magnet']=True
            else:cfg['geometry'].append(item.name)
        if item.name!='L3':cfg['detector_modes'][item.name]=item.mode
        if item.name!='L3' and item.cluster_size_scale!=1.:cfg['cluster_size_scales'][item.name]=item.cluster_size_scale
        if item.name in ('EMC','PHS','CPV'):
            cfg.setdefault('calorimeter_display',{})[item.name]=item.cell_display
            cfg.setdefault('tower_height_scales',{})[item.name]=item.tower_height_scale
            if item.tower_width_factor!=1.:cfg['tower_width_scales'][item.name]=item.tower_width_factor
            if item.tower_fixed_height_cm>0:cfg['tower_fixed_heights_cm'][item.name]=item.tower_fixed_height_cm
            if item.tower_max_height_cm>0:cfg['tower_max_heights_cm'][item.name]=item.tower_max_height_cm
            if item.tower_mapping!='inherit':cfg['tower_height_mappings'][item.name]=item.tower_mapping
            if item.tower_log_reference!=1.:cfg['tower_log_references'][item.name]=item.tower_log_reference
        cfg['geometry_display'][item.name]=item.display
        cfg['geometry_openings'][item.name]=item.opening
        cfg['geometry_opening_directions'][item.name]=item.opening_direction
        cfg['geometry_exclusions'][item.name]=[p.strip() for p in item.exclusions.split(',') if p.strip()]
        choices={c.identifier:c.enabled for c in item.components if c.explicit}
        if choices:cfg['geometry_components'][item.name]=choices
        if item.inner_mask_radius>0:
            cfg['geometry_inner_masks'][item.name]={'radius_m':item.inner_mask_radius,'patterns':[p.strip() for p in item.inner_mask_patterns.split(',') if p.strip()],'front_only':item.inner_mask_front}
        cfg['geometry_opacities'][item.name]=item.opacity
        cfg['colors']['magnet' if item.name=='L3' else item.name]=hex_color(item.color)
        cfg['colors_linear']['magnet' if item.name=='L3' else item.name]=list(item.color)
    cfg['colors']['background']=hex_color(ui.background)
    cfg['colors']['tracks']=hex_color(ui.track_color);cfg['colors']['clusters']=hex_color(ui.cluster_color)
    cfg['colors_linear'].update(background=list(ui.background),tracks=list(ui.track_color),clusters=list(ui.cluster_color))
    cfg['tpc_cluster_profile']=ui.tpc_cluster_profile;cfg['tpc_profile_scale']=ui.tpc_profile_scale;cfg['tpc_profile_thickness_cm']=ui.tpc_profile_thickness_cm
    for key in ('tower_fixed_height_cm','tower_max_height_cm','tower_width_scale','tower_direction','tower_height_mapping'):cfg[key]=getattr(ui,key)
    cfg['track_radius_cm']=ui.track_width_cm/2;cfg['cluster_radius_cm']=ui.cluster_radius_cm;cfg['clip_tracks']=ui.clip_tracks;cfg['include_ambiguous_tracks']=ui.include_ambiguous_tracks
    cfg['highlight_track_ids']=parse_track_ids(ui.highlight_ids);cfg['highlight_track_radius_cm']=ui.highlight_width_cm/2;cfg['highlight_cluster_radius_cm']=ui.highlight_cluster_radius_cm;cfg['highlight_override_color']=ui.highlight_override;cfg['highlight_track_color']=hex_color(ui.highlight_track_color);cfg['highlight_cluster_color']=hex_color(ui.highlight_cluster_color)
    cfg['geometry_lod']=ui.geometry_lod
    cfg['geometry_lods']={i.name:i.detail for i in ui.detectors if i.detail!='inherit'}
    cfg['geometry_schematics']={**cfg.get('geometry_schematics',{}),**{i.name:False for i in ui.detectors if i.detail!='inherit'}}
    cfg['world_strength']=ui.world_strength;cfg['roughness']=ui.roughness;cfg['metallic']=ui.metallic;cfg['shading']=ui.shading
    cfg['view_transform']=ui.view_transform;cfg['exposure']=ui.exposure;cfg['track_emission']=ui.track_emission;cfg['cluster_emission']=ui.cluster_emission
    cfg['data_glow_lighting']=ui.data_glow_lighting
    cfg['mode']=ui.mode;cfg['track_color_mode']=ui.track_mode;cfg['cluster_color_mode']=ui.cluster_mode;cfg['palette']=ui.palette;cfg['palette_lut']=PALETTES.get(ui.palette,JOB['settings'].get('palette_lut',[]))
    cfg['color_ranges']={'tracks':[ui.track_min,ui.track_max],'clusters':[ui.cluster_min,ui.cluster_max]}
    cfg['scale_min']=None;cfg['scale_max']=None
    cfg['lights']=[{'name':o.name,'position_m':list(o.location),'rotation':list(o.rotation_euler),'energy':o.data.energy,'size_m':o.data.size,'color':hex_color(o.data.color),'color_linear':list(o.data.color)} for o in scene.objects if o.type=='LIGHT' and o.data.type=='AREA']
    if cfg['video_enabled']:cfg['clip_tracks']=True
    return RenderSettings(**cfg).validate()

def track_signature(ui):
    detector_sizes=tuple((i.name,i.cluster_size_scale,i.tower_width_factor,i.tower_fixed_height_cm,i.tower_max_height_cm,i.tower_mapping,i.tower_log_reference) for i in ui.detectors if i.data and i.data_available)
    detector_sizes+=(('video',ui.video_timing,ui.video_interval_s,ui.video_time_scale,ui.video_speed_m_s,ui.video_tower_rise_s,ui.video_fps),)
    return (tuple((i.name,i.mode,i.cell_display,i.tower_height_scale) for i in ui.detectors if i.data and i.data_available),tuple(i.name for i in ui.detectors if i.visible and i.geometry_available and i.name!='L3'),ui.track_width_cm,ui.cluster_radius_cm,ui.tpc_cluster_profile,ui.tpc_profile_scale,ui.tpc_profile_thickness_cm,ui.clip_tracks,ui.include_ambiguous_tracks,ui.highlight_ids,ui.highlight_width_cm,ui.highlight_cluster_radius_cm,ui.highlight_override,tuple(ui.highlight_track_color),tuple(ui.highlight_cluster_color),ui.tower_fixed_height_cm,ui.tower_max_height_cm,ui.tower_width_scale,ui.tower_direction,ui.tower_height_mapping,detector_sizes)

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

def surface_update(self,context):
    if not JOB:return
    self.geometry_available=bool(self.asset_path and Path(bpy.path.abspath(self.asset_path)).is_file()) or is_schematic(JOB['settings'],self.name)
    appearance_update(self,context)
    if self.visible and self.geometry_available:
        if JOB.get('geometry_update_pending'):return
        JOB['geometry_update_pending']=True
        def update():
            JOB['geometry_update_pending']=False
            bpy.ops.alice_eve.apply_geometry()
        bpy.app.timers.register(update,first_interval=.2)


def record_scene(path,kind='interactive',cfg=None):
    if not JOB.get('library_path'):return
    from alice_renderer.scene_library import SceneLibrary
    cfg=cfg or current_settings()
    SceneLibrary(JOB['library_path']).register(path,kind=kind,input_path=JOB['event'],event=EVENT['id'],assets=cfg.geometry_assets)


def save_session():
    if not JOB or not JOB.get('library_path'):return None
    try:
        cfg=current_settings();data=recipe(cfg)
        signature=json.dumps(data,sort_keys=True)
        if JOB.get('session_signature')!=signature:
            path=Path(JOB['output'])/'scene-session.json';save_config(path,data);record_scene(path,cfg=cfg)
            JOB['session_signature']=signature
    except Exception as exc:
        if JOB.get('session_error')!=str(exc):print('Scene history: '+str(exc));JOB['session_error']=str(exc)
    return 2.


def set_if_changed(owner,name,value):
    """Avoid tagging Blender datablocks dirty when an RNA value is unchanged."""
    current=getattr(owner,name)
    def equal(a,b):
        if isinstance(a,(int,float)) and isinstance(b,(int,float)):
            return math.isclose(a,b,rel_tol=1.e-7,abs_tol=1.e-7)
        return a==b
    if isinstance(value,(tuple,list)):
        same=len(current)==len(value) and all(equal(a,b) for a,b in zip(current,value))
    else:same=equal(current,value)
    if not same:setattr(owner,name,value)
    return not same


def appearance_update(self,context):
    if not JOB or not hasattr(context.scene,'alice_eve'):return
    ui=context.scene.alice_eve
    selection_update(self,context)
    coll=bpy.data.collections.get('Tracks')
    if coll:
        for obj in coll.objects:
            if obj.type=='CURVE':set_if_changed(obj.data,'bevel_depth',(ui.highlight_width_cm if obj.get('alice_highlighted') else ui.track_width_cm)*.005)
    world=context.scene.world.node_tree.nodes['Background'];set_if_changed(world.inputs[0],'default_value',(*ui.background,1));set_if_changed(world.inputs[1],'default_value',ui.world_strength)
    set_if_changed(context.scene.view_settings,'view_transform',ui.view_transform);set_if_changed(context.scene.view_settings,'look','None');set_if_changed(context.scene.view_settings,'exposure',ui.exposure)
    for mat in bpy.data.materials:
        if not mat.use_nodes:continue
        bsdf=mat.node_tree.nodes.get('Principled BSDF')
        if bsdf:set_if_changed(bsdf.inputs['Roughness'],'default_value',ui.roughness);set_if_changed(bsdf.inputs['Metallic'],'default_value',ui.metallic)
    for obj in context.scene.objects:
        if obj.type=='MESH':
            smooth=not obj.get('alice_towers',False) and ui.shading=='smooth' and ('alice_lod' not in obj or obj.get('alice_structural_smooth',False))
            if obj.get('alice_applied_smooth')!=smooth:
                for p in obj.data.polygons:p.use_smooth=smooth
                obj['alice_applied_smooth']=smooth
    for item in ui.detectors:
        coll=bpy.data.collections.get(item.name)
        if coll:
            set_if_changed(coll,'hide_render',not (item.visible and item.geometry_available));set_if_changed(coll,'hide_viewport',coll.hide_render)
        signature=json.dumps([list(item.color),item.opacity,item.opening,item.opening_direction])
        if coll and coll.get('alice_material_signature')==signature:continue
        if coll:coll['alice_material_signature']=signature
        mats={m for obj in coll.all_objects if obj.type in ('MESH','CURVE') for m in obj.data.materials if m} if coll else set()
        for mat in mats:
            if not mat.use_nodes:continue
            bsdf=mat.node_tree.nodes.get('Principled BSDF')
            if not bsdf:continue
            set_if_changed(bsdf.inputs['Base Color'],'default_value',(*item.color,1))
            opening=mat.node_tree.nodes.get('ALICE opening')
            if opening:set_if_changed(opening.inputs[1],'default_value',math.radians(item.opening)/2)
            direction=mat.node_tree.nodes.get('ALICE opening direction')
            if direction:set_if_changed(direction.inputs[1],'default_value',-math.radians(item.opening_direction))
            for node in mat.node_tree.nodes:
                if node.bl_idname=='ShaderNodeMixShader' and not node.inputs[0].is_linked:set_if_changed(node.inputs[0],'default_value',item.opacity)
            set_if_changed(mat,'diffuse_color',(*item.color,item.opacity))
            from worker import configure_surface_material
            configure_surface_material(mat,item.opacity,True)
    for kind in ('Tracks','Clusters'):
        coll=bpy.data.collections.get(kind)
        if not coll:continue
        # Object selection is already per detector; no global hide masks.
        set_if_changed(coll,'hide_render',False);set_if_changed(coll,'hide_viewport',False)
        for obj in coll.objects:
            emphasis=obj.get('alice_highlighted',False)
            base=ui.track_color if kind=='Tracks' else ui.cluster_color
            special=ui.highlight_track_color if kind=='Tracks' else ui.highlight_cluster_color
            mode=ui.track_mode if kind=='Tracks' else ui.cluster_mode
            mats=list(obj.data.materials)
            for modifier in obj.modifiers:
                if modifier.type=='NODES':
                    for node in modifier.node_group.nodes:
                        if node.bl_idname=='GeometryNodeSetMaterial' and node.inputs['Material'].default_value:mats.append(node.inputs['Material'].default_value)
            color=special if emphasis and ui.highlight_override else base
            for mat in mats:
                set_if_changed(mat.cycles,'emission_sampling','AUTO' if ui.data_glow_lighting else 'NONE')
                bsdf=mat.node_tree.nodes.get('Principled BSDF')
                if bsdf:
                    set_if_changed(bsdf.inputs['Emission Strength'],'default_value',ui.track_emission if kind=='Tracks' else ui.cluster_emission)
                    if emphasis and ui.highlight_override or mode=='solid':
                        set_if_changed(bsdf.inputs['Base Color'],'default_value',(*color,1));set_if_changed(bsdf.inputs['Emission Color'],'default_value',(*color,1))

def populate_components(item,requested=None):
    from alice_renderer.geometry_components import load_components,component_visibility
    data=load_components(bpy.path.abspath(item.asset_path),verify=False) if item.asset_path else None
    if not data:return
    if requested is None:requested={c.identifier:c.enabled for c in item.components if c.explicit} if item.components else (JOB or {}).get('settings',{}).get('geometry_components',{}).get(item.name,{})
    visibility=component_visibility(data,requested,[p.strip() for p in item.exclusions.split(',') if p.strip()])
    item.components.clear()
    for identifier,entry in sorted(data['components'].items()):
        component=item.components.add();component.identifier=identifier;component.label=entry['label']+(' (mixed)' if visibility[identifier] is None else '');component.count=entry['count']
        component.enabled=requested.get(identifier,visibility[identifier] is True)
        component.explicit=identifier in requested

class GeometryComponent(bpy.types.PropertyGroup):
    identifier: StringProperty()
    label: StringProperty()
    count: IntProperty()
    enabled: BoolProperty(default=True)
    explicit: BoolProperty(default=False)

class ToggleComponent(bpy.types.Operator):
    bl_idname='alice_eve.toggle_component';bl_label='Toggle detector component'
    bl_description='Show or hide this aligned geometry component; apply geometry to update the scene'
    detector: StringProperty()
    identifier: StringProperty()
    def execute(self,context):
        item=context.scene.alice_eve.detectors[self.detector];component=next(c for c in item.components if c.identifier==self.identifier)
        component.enabled=not component.enabled;component.explicit=True
        for child in item.components:
            if child.identifier.startswith(self.identifier+'/'):child.enabled=component.enabled;child.explicit=False
        return bpy.ops.alice_eve.apply_geometry()

class RefreshComponents(bpy.types.Operator):
    bl_idname='alice_eve.refresh_components';bl_label='Refresh components'
    bl_description='Read layer, wall, support and named element choices from the selected aligned asset'
    detector: StringProperty()
    def execute(self,context):
        try:populate_components(context.scene.alice_eve.detectors[self.detector]);return {'FINISHED'}
        except Exception as exc:self.report({'ERROR'},str(exc));return {'CANCELLED'}

class DetectorSettings(bpy.types.PropertyGroup):
    cluster_size_scale: FloatProperty(name='Cluster size factor',description='Multiplies scene/linked-cluster radii and measured TPC profile display sizes; 1 keeps normal size',min=.001,max=1000,default=1.,update=selection_update)
    tower_width_factor: FloatProperty(name='Tower footprint factor',description='Multiplies the scene footprint scale for this detector',min=.001,max=1000,default=1.,update=selection_update)
    tower_fixed_height_cm: FloatProperty(name='Detector fixed height (cm)',description='0 uses the scene fixed height',min=0,max=10000,default=0,update=selection_update)
    tower_max_height_cm: FloatProperty(name='Detector maximum height (cm)',description='0 uses the scene height limit',min=0,max=10000,default=0,update=selection_update)
    tower_mapping: EnumProperty(name='Detector height mapping',items=[('inherit','Use scene mapping','Use the scene tower height mapping'),('linear','Linear','Height proportional to measured signal'),('log','Logarithmic','Compress large signals with a reference signal in input units')],default='inherit',update=selection_update)
    tower_log_reference: FloatProperty(name='Log reference signal',description='Input signal units; h = height scale × reference × ln(1 + signal/reference)',min=.000001,max=1000000,default=1.,precision=6,update=selection_update)
    tower_count: IntProperty(default=0)
    tower_point_fallbacks: IntProperty(default=0)
    tower_nominal_footprints: IntProperty(default=0)
    cell_display: EnumProperty(name='Cells / clusters',items=[('points','Points','Default point glyphs'),('signal towers','Signal towers','Height from measured EMC/PHOS energy or CPV amplitude; missing/nonpositive signals remain points'),('fixed towers','Fixed-height towers','Display glyphs with a fixed height; no implied signal magnitude')],default='points',update=selection_update)
    tower_height_scale: FloatProperty(name='Tower height scale',description='cm per GeV for EMC; PHOS: per input unit (raw ADC or calibrated GeV); CPV: per native amplitude',min=.0001,max=10000,default=20.,update=selection_update)
    components: CollectionProperty(type=GeometryComponent)
    show_components: BoolProperty(name='Detector components',default=False)
    component_filter: StringProperty(name='Filter components')
    component_category: EnumProperty(name='Category',items=[(k,k.title(),'') for k in ('layers','structures','modules','parts')],default='structures')
    data_available: BoolProperty(default=False)
    geometry_available: BoolProperty(default=False)
    asset_path: StringProperty(name='Aligned geometry asset',subtype='FILE_PATH',update=surface_update)
    event_track_count: IntProperty(default=0)
    event_cluster_count: IntProperty(default=0)
    data: BoolProperty(name='Event data',default=True,update=selection_update)
    mode: EnumProperty(name='Objects',items=[(v,v,'') for v in ('tracks','clusters','both')],update=selection_update)
    visible: BoolProperty(name='Surface',default=True,update=surface_update)
    detail: EnumProperty(name='Geometry detail',items=[('inherit','Use scene detail','Use the Geometry detail control above'),('full','Full geometry','Keep aligned detector surfaces'),('proxy','Cached approximate surfaces','Reviewed low-complexity detector surfaces; no source mesh import'),('structural','Large surfaces (cached, fast)','ITS stave panels and TPC walls/sectors; fine details omitted'),('simplified','Simplified geometry','Use approximate coarse spatial cells')],default='inherit')
    opening: FloatProperty(name='Opening (degrees)',min=0,max=360,default=0,update=appearance_update)
    opening_direction: FloatProperty(name='Opening direction (degrees)',description='Wedge centre in ALICE XY: 0 is +X, 90 is +Y, −90 is −Y',min=-360,max=360,default=-90,update=appearance_update)
    exclusions: StringProperty(name='Hide component names',description='Comma-separated object-name patterns, e.g. ITSServices*, CageCover*. Apply geometry appearance to update. Recorded in the recipe; data and clipping bounds remain unchanged')
    inner_mask_radius: FloatProperty(name='Inner placement mask radius (m)',description='0 disables; hide matching placements inside this radius, retaining outer placements. Apply geometry appearance',min=0,max=100,default=0)
    inner_mask_patterns: StringProperty(name='Inner component names',description='Comma-separated patterns of instancer groups to mask inside the chosen radius')
    inner_mask_front: BoolProperty(name='Only opening-facing inner placements',description='Use the opening direction to retain the back half of the inner structure',default=True)
    opacity: FloatProperty(name='Opacity per surface',min=0,max=1,default=.18,precision=3,update=appearance_update)
    display: EnumProperty(name='Appearance',items=[('surfaces','Existing surfaces','Keep the current aligned surfaces or simplified cells'),('shell','Outer shell','Approximate outer hull; removes internal structures and openings'),('outline','Outline','Edges of the approximate outer hull')])
    color: FloatVectorProperty(name='Colour',subtype='COLOR',size=3,min=0,max=1,default=(.02,.04,.2),update=appearance_update)

COLOR_ITEMS=[(name,name,'0 = standalone fitted source; 1 = composite matched source (e.g. ITS-TPC); grey = unknown' if name=='matching' else '') for name in COLOR_FIELDS] + [(name,name,DESCRIPTIONS[name]) for name in CLUSTER_COLOR_FIELDS]
def use_scene_lighting():
    for screen in bpy.data.screens:
        for area in screen.areas:
            if area.type=='VIEW_3D':
                shading=area.spaces.active.shading
                ui=getattr(bpy.context.scene,'alice_eve',None)
                shading.type='SOLID' if ui and ui.viewport_paused and bpy.context.scene.render.engine!='CYCLES' else 'RENDERED'
                shading.use_scene_lights=True;shading.use_scene_world=True
                shading.use_scene_lights_render=True;shading.use_scene_world_render=True

def viewport_renderer_update(self,context):
    if not JOB:return
    scene=context.scene;scene.render.engine=self.viewport_renderer
    # Progressive Cycles uses the same materials and geometry as the full
    # render; Eevee remains the fast choice. This is an editor-only preference.
    scene.cycles.preview_samples=self.viewport_samples;scene.cycles.use_preview_adaptive_sampling=True;scene.cycles.preview_adaptive_threshold=.025;scene.cycles.use_preview_denoising=True
    scene.eevee.taa_samples=self.viewport_samples;scene.eevee.use_shadow_jitter_viewport=False
    use_scene_lighting()
    if self.viewport_paused:pause_viewport(context.scene,True)

def pause_viewport(scene,paused):
    """Cycles freezes its preview; Eevee uses an inexpensive solid inspection view."""
    scene.cycles.preview_pause=paused
    if not JOB:return
    if paused:
        saved=JOB.setdefault('paused_viewports',[])
        for screen in bpy.data.screens:
            for area in screen.areas:
                if area.type!='VIEW_3D':continue
                space=area.spaces.active
                if not any(s.as_pointer()==space.as_pointer() for s,mode in saved):saved.append((space,space.shading.type))
                if scene.render.engine!='CYCLES' and space.shading.type=='RENDERED':space.shading.type='SOLID'
                area.tag_redraw()
    else:
        for space,mode in JOB.pop('paused_viewports',[]):
            try:space.shading.type=mode
            except ReferenceError:pass

def viewport_pause_update(self,context):pause_viewport(context.scene,self.viewport_paused)

def sidebar_contains(screen,x,y):
    return any(area.type=='VIEW_3D' and area.spaces.active.show_region_ui and
               region.type in ('UI','TOOLS') and region.width>1 and
               region.x<=x<region.x+region.width and region.y<=y<region.y+region.height
               for area in screen.areas for region in area.regions)

class WatchPlaybackControls(bpy.types.Operator):
    bl_idname='alice_eve.watch_playback_controls';bl_label='Keep collision controls available'
    bl_description='Hold playback while editing the sidebar, without consuming mouse or keyboard input'
    def invoke(self,context,event):
        if JOB.get('controls_watcher'):return {'CANCELLED'}
        self.job=JOB;JOB['controls_watcher']=True;context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}
    def modal(self,context,event):
        if JOB is not self.job or not JOB.get('video_player'):return {'FINISHED'}
        if event.type in ('MOUSEMOVE','LEFTMOUSE','RIGHTMOUSE','WHEELUPMOUSE','WHEELDOWNMOUSE'):
            ui=context.scene.alice_eve
            inside=sidebar_contains(context.window.screen,event.mouse_x,event.mouse_y)
            if not ui.pause_while_editing or not inside:JOB['video_player'].hold_controls(False)
            elif event.type=='LEFTMOUSE' and event.value=='PRESS' or event.type in ('WHEELUPMOUSE','WHEELDOWNMOUSE'):JOB['video_player'].hold_controls(True)
        return {'PASS_THROUGH'}

class ToggleViewportPause(bpy.types.Operator):
    bl_idname='alice_eve.pause_viewport';bl_label='Pause viewport'
    bl_description='Pause or resume live viewport rendering independently of collision playback; Eevee pauses into solid inspection mode'
    def execute(self,context):
        ui=context.scene.alice_eve;ui.viewport_paused=not ui.viewport_paused
        if ui.viewport_paused and context.scene.render.engine!='CYCLES':self.report({'INFO'},'Viewport rendering paused; solid inspection is active until Resume viewport')
        return {'FINISHED'}

class SceneSettings(bpy.types.PropertyGroup):
    viewport_paused: BoolProperty(name='Viewport rendering paused',default=False,update=viewport_pause_update)
    pause_while_editing: BoolProperty(name='Pause collisions while editing sidebar',default=True)
    video_enabled: BoolProperty(name='Render selected collisions as video',default=False)
    video_timing: EnumProperty(name='Collision timing',items=[('fixed','Fixed interval','Keep selected collision order'),('realtime','Scaled collision timestamps','Automatic scale averages one collision per second')],default='fixed',update=selection_update)
    video_interval_s: FloatProperty(name='Event interval / final hold (s)',min=.001,max=3600,default=1.,update=selection_update)
    video_time_scale: FloatProperty(name='Source-time scale (0 = auto)',description='Video seconds per source second; 0 averages one collision per second',min=0,max=1e12,default=0,update=selection_update)
    video_speed_m_s: FloatProperty(name='Display propagation (m/s)',description='Metres per VIDEO second; not particle time of flight',min=.001,max=100000,default=10.,update=selection_update)
    video_tower_rise_s: FloatProperty(name='Tower rise time (s)',min=.001,max=3600,default=.2,update=selection_update)
    video_fps: IntProperty(name='Video FPS',min=1,max=120,default=24,update=selection_update)
    video_playing: BoolProperty(default=False)
    video_status: StringProperty(default='Ready')
    tower_height_mapping: EnumProperty(name='Tower height mapping',items=[('linear','Linear','Height proportional to measured signal'),('log','Logarithmic','Compress large signals; reference configurable per detector')],default='linear',update=selection_update)
    tower_fixed_height_cm: FloatProperty(name='Fixed tower height (cm)',min=.001,max=10000,default=10.,update=selection_update)
    tower_max_height_cm: FloatProperty(name='Maximum tower height (cm)',min=.001,max=10000,default=100.,update=selection_update)
    tower_width_scale: FloatProperty(name='Tower footprint scale',min=.001,max=10,default=.95,update=selection_update)
    tower_direction: EnumProperty(name='Tower direction',items=[('inward','Towards beam','Extend from the measured position towards the beam'),('outward','Away from beam','Extend from the measured position away from the beam')],default='inward',update=selection_update)
    viewport_renderer: EnumProperty(name='Viewport renderer',items=[('BLENDER_EEVEE','Fast (Eevee)','Responsive preview; transparency and lighting are approximate'),('CYCLES','Accurate (Cycles)','Progressive preview using the final renderer; slower on CPU')],default='CYCLES',update=viewport_renderer_update)
    detectors: CollectionProperty(type=DetectorSettings)
    geometry_lod: EnumProperty(name='Geometry detail',items=[('full','Full aligned surfaces','Preserve the actual detector geometry'),('proxy','Cached approximate surfaces','Reviewed low-complexity detector surfaces; no source mesh import'),('structural','Large surfaces (cached, fast)','Prebuilt ITS/TPC display surfaces; no heavy source import'),('simplified','Coarse cells','Reduce complexity; approximate bounding cells')])
    mode: EnumProperty(name='Set all object modes',items=[(v,v,'') for v in ('tracks','clusters','both')],update=set_all_modes)
    track_width_cm: FloatProperty(name='Track linewidth (cm)',min=.002,max=20,default=.24,precision=3,update=appearance_update)
    tpc_cluster_profile: EnumProperty(name='TPC cluster profile',items=[('sphere','Spheres','Fixed radius'),('ellipse','Measured ellipse','Pad/time RMS profile'),('gaussian','Gaussian shells','Gaussian-weighted translucent shells; display approximation')],default='sphere',update=selection_update)
    tpc_profile_scale: FloatProperty(name='Sigma scale',min=.01,max=100,default=1.,update=selection_update)
    tpc_profile_thickness_cm: FloatProperty(name='Display thickness (cm)',min=.001,max=10,default=.03,update=selection_update)
    render_status: StringProperty(name='Render status',default='Ready')
    render_percent: IntProperty(name='Render progress %',min=0,max=100,default=0)
    cluster_radius_cm: FloatProperty(name='Cluster radius (cm)',min=.001,max=20,default=.35,update=selection_update)
    highlight_ids: StringProperty(name='Special track IDs',description='Comma-separated event track IDs; Ctrl-click adds, Shift-click toggles',update=selection_update)
    highlight_width_cm: FloatProperty(name='Special track linewidth (cm)',min=.002,max=20,default=.7,update=appearance_update)
    highlight_cluster_radius_cm: FloatProperty(name='Linked cluster radius (cm)',min=.001,max=20,default=1.,update=selection_update)
    highlight_override: BoolProperty(name='Use special colours',default=True,update=appearance_update)
    highlight_track_color: FloatVectorProperty(name='Special tracks',subtype='COLOR',size=3,min=0,max=1,update=appearance_update)
    highlight_cluster_color: FloatVectorProperty(name='Linked clusters',subtype='COLOR',size=3,min=0,max=1,update=appearance_update)
    picking_active: BoolProperty(default=False)
    displayed_tracks: IntProperty(default=0)
    displayed_clusters: IntProperty(default=0)
    include_ambiguous_tracks: BoolProperty(name='Include ambiguous vertex matches',description='Show possible time-window matches to multiple vertices and their clusters. They are not uniquely assigned collision particles',default=False,update=selection_update)
    viewport_samples: IntProperty(name='Preview samples',default=128,min=16,max=4096,update=viewport_renderer_update)
    clip_tracks: BoolProperty(name='Clip tracks to selected detectors',default=True,update=selection_update)
    track_mode: EnumProperty(name='Track coding',items=lambda self,context:COLOR_ITEMS)
    cluster_mode: EnumProperty(name='Cluster coding',items=lambda self,context:COLOR_ITEMS)
    palette: EnumProperty(name='Palette',items=lambda self,context:PALETTE_ITEMS)
    track_min: FloatProperty(name='Minimum');track_max: FloatProperty(name='Maximum',default=1)
    cluster_min: FloatProperty(name='Minimum');cluster_max: FloatProperty(name='Maximum',default=1)
    track_color: FloatVectorProperty(name='Tracks',subtype='COLOR',size=3,min=0,max=1,update=appearance_update)
    cluster_color: FloatVectorProperty(name='Clusters',subtype='COLOR',size=3,min=0,max=1,update=appearance_update)
    background: FloatVectorProperty(name='Background',subtype='COLOR',size=3,min=0,max=1,update=appearance_update)
    world_strength: FloatProperty(name='Background light',min=0,max=20,default=.45,update=appearance_update)
    view_transform: EnumProperty(name='Display colours',items=[('AgX','AgX','Highlight compression'),('Standard','Standard','Keep saturated colours')],default='AgX',update=appearance_update)
    exposure: FloatProperty(name='Exposure (stops)',min=-20,max=20,default=0,update=appearance_update)
    track_emission: FloatProperty(name='Track glow',min=0,max=100,default=.7,update=appearance_update)
    cluster_emission: FloatProperty(name='Cluster glow',min=0,max=100,default=1.,update=appearance_update)
    data_glow_lighting: BoolProperty(name='Data glow lights geometry',description='Sample tracks and clusters as mesh lights. Keep off for faster, cleaner preview lighting; glyph glow stays visible',default=False,update=appearance_update)
    roughness: FloatProperty(name='Roughness',min=0,max=1,default=.38,update=appearance_update)
    metallic: FloatProperty(name='Metallic',min=0,max=1,default=.15,update=appearance_update)
    shading: EnumProperty(name='Shading',items=[('smooth','Smooth',''),('flat','Flat','')],update=appearance_update)
    export_path: StringProperty(name='Config',subtype='FILE_PATH')
    include_defaults: BoolProperty(name='Include local input/event defaults',default=False)

class ApplyData(bpy.types.Operator):
    bl_idname='alice_eve.apply_data';bl_label='Apply data selection / colour coding'
    def execute(self,context):
        try:
            if JOB.get('video_player'):
                JOB['video_player'].reconfigure(current_settings());JOB['applied_track_signature']=track_signature(context.scene.alice_eve);appearance_update(self,context);return {'FINISHED'}
            from worker import tracks,clusters,remove_owned_collection
            cfg=current_settings().to_dict();selected=set(cfg['detectors'])
            cfg['_track_regions']=JOB.get('track_regions',{})
            from alice_renderer.track_clipping import selected_track_detectors
            needed={d for t in EVENT['tracks'] for d in selected_track_detectors(cfg,t)} if cfg['clip_tracks'] and bool(enabled_detectors(cfg,'tracks')) else set()
            from worker import schematic_region
            for name in needed:
                if is_schematic(cfg,name):cfg['_track_regions'][name]=schematic_region(name)
            missing={d for d in needed if d not in cfg['_track_regions'] or not is_schematic(cfg,d) and cfg['_track_regions'][d].get('basis')=='explicit schematic/demo outer envelope'}
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
            if bool(enabled_detectors(cfg,'tracks')):context.scene.alice_eve.displayed_tracks=tracks(ts,cfg)['visible_tracks']
            else:
                from worker import collection
                collection('Tracks')
                context.scene.alice_eve.displayed_tracks=0
            cluster_legend=clusters(cs,cfg)
            for item in context.scene.alice_eve.detectors:
                info=cluster_legend.get('calorimeter_towers',{}).get(item.name,{})
                item.tower_count=info.get('towers',0);item.tower_point_fallbacks=info.get('point_fallbacks',0);item.tower_nominal_footprints=info.get('approximate_footprints',0)
            JOB['applied_track_signature']=track_signature(context.scene.alice_eve);appearance_update(self,context)
            context.scene.alice_eve.displayed_clusters=len(cs)
            self.report({'INFO'},'Data selection and fixed colour ranges applied')
            return {'FINISHED'}
        except Exception as exc:self.report({'ERROR'},str(exc));return {'CANCELLED'}

class ApplyGeometry(bpy.types.Operator):
    bl_idname='alice_eve.apply_geometry';bl_label='Apply geometry appearance'
    def execute(self,context):
        try:
            from worker import imported_geometry,envelope,remove_owned_collection
            cfg=current_settings().to_dict();cfg['_interactive']=True
            changed_regions=False
            for item in context.scene.alice_eve.detectors:
                if not item.geometry_available:continue
                old=bpy.data.collections.get(item.name)
                if not item.visible and not old:continue
                same_asset=is_schematic(cfg,item.name) or old and old.get('alice_asset_path')==str(Path(cfg['geometry_assets'].get(item.name,'')).resolve())
                same_exclusions=old and old.get('alice_exclusions','[]')==json.dumps(cfg['geometry_exclusions'].get(item.name,[]))
                inner_rule=cfg['geometry_inner_masks'].get(item.name,{})
                same_direction=not inner_rule or not inner_rule.get('front_only',True) or old and abs(old.get('alice_inner_direction',-90.)-item.opening_direction)<1.e-5
                same_components=old and old.get('alice_components','{}')==json.dumps(cfg.get('geometry_components',{}).get(item.name,{}),sort_keys=True)
                same_inner=old and old.get('alice_inner_mask','{}')==json.dumps(inner_rule,sort_keys=True) and same_direction
                if old and same_asset and same_exclusions and same_components and same_inner and old.get('alice_display')==item.display and old.get('alice_geometry_lod')==cfg['geometry_lods'].get(item.name,cfg['geometry_lod']) and old.get('alice_schematic',False)==is_schematic(cfg,item.name):continue
                changed_regions|=bool(old and (not same_asset or old.get('alice_schematic',False)!=is_schematic(cfg,item.name)))
                print('ALICE_STAGE Rebuilding detector geometry: '+item.name,flush=True)
                if old:remove_owned_collection(old)
                if is_schematic(cfg,item.name):envelope(item.name,cfg)
                else:
                    asset=cfg['geometry_assets'].get(item.name)
                    if not asset:raise ValueError(item.name+': provide aligned geometry before selecting full/simplified surfaces')
                    info=imported_geometry(item.name,asset,cfg)
                    if info.get('track_region'):JOB['track_regions'][item.name]=info['track_region']
                    populate_components(item,cfg.get('geometry_components',{}).get(item.name,{}))
            if changed_regions and bpy.ops.alice_eve.apply_data()!={'FINISHED'}:return {'CANCELLED'}
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
    bl_description='Load original aligned detector meshes, overriding schematic envelopes, coarse cells and outlines'
    def execute(self,context):
        ui=context.scene.alice_eve;ui.geometry_lod='full'
        for item in ui.detectors:
            if item.geometry_available and item.visible:item.display='surfaces';item.detail='full'
        return bpy.ops.alice_eve.apply_geometry()

class OpaqueGeometry(bpy.types.Operator):
    bl_idname='alice_eve.opaque_geometry';bl_label='Make geometry opaque'
    def execute(self,context):
        for item in context.scene.alice_eve.detectors:
            if item.geometry_available:item.opacity=1.
        return {'FINISHED'}

class SolidDetectorSurfaces(bpy.types.Operator):
    bl_idname='alice_eve.solid_surfaces';bl_label='Use real solid detector surfaces'
    bl_description='Load full aligned meshes and set selected detector surfaces opaque; preserve colours, openings, camera and data selection'
    def execute(self,context):
        if not any(i.visible and i.geometry_available for i in context.scene.alice_eve.detectors):
            self.report({'ERROR'},'Select a detector Surface first');return {'CANCELLED'}
        result=bpy.ops.alice_eve.full_geometry()
        if result!={'FINISHED'}:return result
        for item in context.scene.alice_eve.detectors:
            if item.visible and item.geometry_available:item.opacity=1.
        appearance_update(self,context)
        self.report({'INFO'},'Full aligned opaque surfaces loaded; event clusters remain separate data')
        return {'FINISHED'}

class LightTransparentSurfaces(bpy.types.Operator):
    bl_idname='alice_eve.light_transparent_surfaces';bl_label='Light transparent detector surfaces'
    bl_description='Load full aligned meshes at 3.5% opacity per face, avoiding the heavy darkening of many overlapping 50% surfaces'
    def execute(self,context):
        if not any(i.visible and i.geometry_available for i in context.scene.alice_eve.detectors):
            self.report({'ERROR'},'Select a detector Surface first');return {'CANCELLED'}
        result=bpy.ops.alice_eve.full_geometry()
        if result!={'FINISHED'}:return result
        for item in context.scene.alice_eve.detectors:
            if item.visible and item.geometry_available:item.opacity=.035
        context.scene.alice_eve.data_glow_lighting=False
        appearance_update(self,context)
        return {'FINISHED'}

class RestoreSurfaceExclusions(bpy.types.Operator):
    bl_idname='alice_eve.restore_surface_exclusions';bl_label='Restore excluded detector surfaces'
    bl_description='Restore selected detectors\' walls and services hidden by name or inner-radius filters; retain component checkboxes, camera, openings and colours'
    def execute(self,context):
        for item in context.scene.alice_eve.detectors:
            if item.visible and item.geometry_available:
                item.exclusions='';item.inner_mask_radius=0
        return bpy.ops.alice_eve.apply_geometry()

class TPCSectorsInnerWall(bpy.types.Operator):
    bl_idname='alice_eve.tpc_sectors_inner_wall';bl_label='TPC sectors + inner wall'
    bl_description='Keep only aligned TPC readout-sector chambers and inner wall/shields; hide rods, supports, outer wall and central electrode; retain camera, materials and event data'
    def execute(self,context):
        from alice_renderer.geometry_components import load_components
        from alice_renderer.scene_presets import tpc_sectors_and_inner_wall
        item=context.scene.alice_eve.detectors.get('TPC')
        try:
            if item is None or not item.asset_path:raise ValueError('Choose the aligned TPC asset first')
            choices=tpc_sectors_and_inner_wall(load_components(bpy.path.abspath(item.asset_path)))
            populate_components(item)
            for component in item.components:
                component.explicit=component.identifier in choices
                component.enabled=choices.get(component.identifier,True)
            item.detail='full';item.display='surfaces';item.exclusions='';item.inner_mask_radius=0;item.visible=True
            item.component_category='parts';item.show_components=True
            return bpy.ops.alice_eve.apply_geometry()
        except Exception as exc:self.report({'ERROR'},str(exc));return {'CANCELLED'}

class SurroundLighting(bpy.types.Operator):
    bl_idname='alice_eve.surround_lighting';bl_label='Add lights around detector'
    bl_description='Add eight broad side lights and two end lights; retain existing lights, camera and colours. Repeating replaces only this light rig'
    def execute(self,context):
        from alice_renderer.scene_presets import surround_lights,SURROUND_LIGHT_PREFIX
        from mathutils import Vector
        for lamp in list(context.scene.objects):
            if lamp.type=='LIGHT' and lamp.name.startswith(SURROUND_LIGHT_PREFIX):
                data=lamp.data;bpy.data.objects.remove(lamp,do_unlink=True)
                if data.users==0:bpy.data.lights.remove(data)
        target=Vector(tuple(v*.01 for v in JOB['settings']['target_cm']))
        for light in surround_lights(target):
            data=bpy.data.lights.new(light['name'],'AREA');data.energy=light['energy'];data.shape='DISK';data.size=light['size_m']
            lamp=bpy.data.objects.new(light['name'],data);context.scene.collection.objects.link(lamp)
            lamp.location=light['position_m'];lamp.rotation_euler=(target-lamp.location).to_track_quat('-Z','Y').to_euler()
        self.report({'INFO'},'Surround lighting added; each light remains adjustable and exports with the scene')
        use_scene_lighting()
        return {'FINISHED'}

class FastStructuralSurfaces(bpy.types.Operator):
    bl_idname='alice_eve.fast_surfaces';bl_label='Use cached approximate surfaces'
    bl_description='Use reviewed low-complexity surfaces for visible detectors and magnet; retain camera, colours, openings and component choices'
    def execute(self,context):
        from alice_renderer.surface_proxy import load
        selected=[i for i in context.scene.alice_eve.detectors if i.visible and i.geometry_available]
        try:
            if not selected:raise ValueError('Select detector surfaces first')
            # Validate every cache before changing any editor choices.
            for item in selected:
                data=load(bpy.path.abspath(item.asset_path),JOB['settings']['geometry_units'])
                if data['detector']!=item.name:raise ValueError('Cache detector differs from '+item.name)
            for item in selected:item.detail='proxy';item.display='surfaces';item.inner_mask_radius=0
            return bpy.ops.alice_eve.apply_geometry()
        except Exception as exc:self.report({'ERROR'},str(exc));return {'CANCELLED'}

class ShowSceneLighting(bpy.types.Operator):
    bl_idname='alice_eve.show_scene_lighting';bl_label='Show scene lighting'
    bl_description='Use rendered shading and the exported scene lights/world instead of Solid or studio/HDRI preview lighting'
    def execute(self,context):
        viewport_renderer_update(context.scene.alice_eve,context)
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
        area.spaces.active.lock_camera=True
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
            if context.area and context.area.type=='VIEW_3D' and context.area.spaces.active.region_3d.view_perspective!='CAMERA':
                if bpy.ops.alice_eve.camera_from_view()!={'FINISHED'}:return {'CANCELLED'}
                cfg=current_settings()
            selected=set(cfg.detectors)
            for kind,mode,active in [('tracks',cfg.track_color_mode,bool(enabled_detectors(cfg.to_dict(),'tracks'))),('clusters',cfg.cluster_color_mode,bool(enabled_detectors(cfg.to_dict(),'clusters')))]:
                objects=selected_tracks(EVENT,cfg.to_dict()) if kind=='tracks' else selected_clusters(EVENT,cfg.to_dict())
                if active and selected and not cfg.video_enabled and mode not in capabilities(objects):raise ValueError(f'{mode} is unavailable for selected {kind}')
            if bpy.ops.alice_eve.apply_data()!={'FINISHED'}:return {'CANCELLED'}
            if bpy.ops.alice_eve.apply_geometry()!={'FINISHED'}:return {'CANCELLED'}
            data=recipe(cfg)
            if ui.include_defaults:data['defaults']={'input':JOB['event'],'event':str(EVENT['id'])}
            save_config(bpy.path.abspath(ui.export_path),data)
            record_scene(bpy.path.abspath(ui.export_path),kind='export',cfg=cfg)
            self.report({'INFO'},'Portable scene exported');return {'FINISHED'}
        except Exception as exc:self.report({'ERROR'},str(exc));return {'CANCELLED'}

DETAIL_ITEMS=[('current','Keep current scene','Preserve the current geometry type, detail and appearance'),('full','Full aligned surfaces','Load the actual aligned geometry; overrides schematic/outline/coarse-cell modes'),('proxy','Cached approximate surfaces','Reviewed low-complexity detector surfaces; no source mesh import'),('structural','Large surfaces (cached, fast)','ITS/TPC display approximation; requires its prebuilt cache'),('simplified','Simplified aligned cells','Coarse cells derived from actual aligned geometry; requires its asset'),('schematic','Schematic envelope','Approximate detector envelope; does not load aligned geometry')]

class RenderGeometryDetail(bpy.types.PropertyGroup):
    detail: EnumProperty(name='Geometry detail',items=DETAIL_ITEMS,default='full')

def initialize_render_geometry(operator,cfg):
    operator.geometry_details.clear()
    for name in cfg.geometry+(['L3'] if cfg.magnet else []):
        item=operator.geometry_details.add();item.name=name;item.detail='full'

def render_geometry_settings(cfg,items,preset='full'):
    return final_render_choices(cfg,{i.name:i.detail for i in items}) if items else render_geometry_preset(cfg,preset)

def render_geometry_preset_update(self,context):
    if not JOB or not self.geometry_details:return
    cfg=render_geometry_preset(current_settings(),self.geometry_preset);values=cfg.to_dict()
    from alice_renderer.geometry_selection import detail
    for item in self.geometry_details:item.detail='current' if self.geometry_preset=='current' else 'schematic' if is_schematic(values,item.name) else detail(values,item.name)

def render_preset_update(self,context):
    self.resolution_percent=PRESET_PERCENT[self.quality]

class RenderFull(bpy.types.Operator):
    bl_idname='alice_eve.render_full';bl_label='Render full'
    bl_description='Choose image quality and geometry detail for each selected detector and L3, then start a full render'
    render_kind: EnumProperty(name='Output',items=[('still','Still image (current frame)','Render the exact paused playback frame, or the current event'),('video','Video (all selected collisions)','Render the complete collision timeline as MP4')],default='still')
    playback_frame: IntProperty(default=0,min=0,options={'HIDDEN'})
    render_engine: EnumProperty(name='Renderer',items=[('BLENDER_EEVEE','Eevee (rasterized)','Fast rasterized rendering; requires a working graphics context'),('CYCLES','Cycles','Ray-traced rendering using the selected compute backend')],default='CYCLES')
    show_geometry_details: BoolProperty(name='Override individual detector detail',default=False)
    geometry_details: CollectionProperty(type=RenderGeometryDetail)
    geometry_preset: EnumProperty(name='Geometry to render',items=[('full','Full geometry','Full aligned surfaces for all selected detectors and L3'),('simplified','Simplified geometry (fast surfaces)','Use compatible fast interactive caches; otherwise aligned coarse cells'),('current','Use interactive geometry','Use exactly the surface detail currently displayed in the interactive scene')],default='full',update=render_geometry_preset_update)
    quality: EnumProperty(name='Sampling preset',items=[(v,v.title(),'') for v in ('draft','balanced','final','publication','custom')],update=render_preset_update)
    resolution_percent: FloatProperty(name='Resolution (% of 8K)',min=1,max=100,default=25,precision=2,subtype='PERCENTAGE')
    backend: EnumProperty(name='Backend',items=[('AUTO','Recommended','')]+[(v,v,'') for v in ('CPU','METAL','HIP','CUDA','OPTIX')])
    samples: IntProperty(name='Samples',default=128,min=1,max=8192)
    output: StringProperty(name='Output folder',subtype='DIR_PATH')
    def invoke(self,context,event):
        self.quality=RECOMMENDATION['quality'];self.resolution_percent=PRESET_PERCENT[self.quality];self.output=JOB['render_output']
        player=JOB.get('video_player')
        self.render_kind='video' if player and player.playing else 'still'
        if player:self.playback_frame=player.frame;player.stop()
        self.render_engine=current_settings().render_engine
        initialize_render_geometry(self,current_settings())
        return context.window_manager.invoke_props_dialog(self,width=480)
    def draw(self,context):
        layout=self.layout;layout.prop(self,'render_kind');layout.prop(self,'render_engine')
        if self.render_kind=='still' and JOB.get('video_player'):layout.label(text=f'Paused playback frame: {self.playback_frame+1}')
        layout.label(text=RECOMMENDATION['reason']);layout.prop(self,'quality')
        if self.render_engine=='CYCLES':layout.prop(self,'backend')
        layout.prop(self,'geometry_preset')
        layout.prop(self,'resolution_percent',slider=True)
        layout.label(text='25% = 1080p · 50% = 4K · 100% = 8K (16:9)')
        w,h=percentage_size(self.resolution_percent or PRESET_PERCENT[self.quality],current_settings().frame_aspect)
        layout.label(text=f'{w} × {h} px; retains camera aspect')
        if self.quality=='custom':layout.prop(self,'samples')
        layout.prop(self,'show_geometry_details')
        if self.show_geometry_details:
            box=layout.box();box.label(text='Geometry detail for this render')
            box.label(text='Preset applies to all surfaces; override individual detectors below.')
            cfg=current_settings().to_dict()
            for item in self.geometry_details:
                box.prop(item,'detail',text=item.name);box.label(text='Current: '+geometry_description(cfg,item.name))
            if not self.geometry_details:box.label(text='No detector surfaces or magnet selected')
            box.label(text='Full loads aligned surfaces, including from schematic previews.')
        layout.prop(self,'output')
    def execute(self,context):
        try:
            ui=context.scene.alice_eve
            if ExportConfig.execute(self,context)!={'FINISHED'}:return {'CANCELLED'}
            backend=RECOMMENDATION['backend'] if self.backend=='AUTO' else self.backend
            if self.render_engine=='CYCLES' and not any(d['type']==backend for d in DEVICES['devices']):raise ValueError(f'{backend} is unavailable. Choose an available backend before rendering.')
            from alice_renderer.runtime import preflight
            from alice_renderer.scene_config import quality_settings
            check=quality_settings(current_settings(),'balanced' if self.quality=='custom' else self.quality,backend=backend,samples=self.samples if self.quality=='custom' else None,resolution_percent=self.resolution_percent or PRESET_PERCENT[self.quality])
            check.render_engine=self.render_engine
            player=JOB.get('video_player')
            check.video_enabled=self.render_kind=='video' or player is not None
            check=render_geometry_settings(check,self.geometry_details,self.geometry_preset)
            if check.video_enabled:
                from alice_renderer.runtime import prepare_video,check_encoder
                encoder=check_encoder(JOB.get('ffmpeg')) if self.render_kind=='video' else None;check,_=prepare_video(check,[Path(p) for p in JOB.get('events',[])],DEVICES,Path(bpy.path.abspath(self.output)))
            errors=preflight(check,[EVENT],DEVICES,Path(bpy.path.abspath(self.output)))
            if errors:raise ValueError('\n'.join(errors))
            root=Path(JOB['output']);path=root/'full-render-config.json'
            data=recipe(check)
            if ui.include_defaults:data['defaults']={'input':JOB['event'],'event':str(EVENT['id'])}
            save_config(path,data)
            # Each subprocess gets an immutable snapshot even if another render
            # starts before it has opened its config. Keep the usual last-config copy.
            path=root/('full-render-config-'+str(time.time_ns())+'.json');save_config(path,data)
            record_scene(path,kind='render settings',cfg=check)
            asset_map=root/('render-assets-'+str(time.time_ns())+'.local.json');asset_map.write_text(json.dumps(check.geometry_assets))
            command=[JOB['python'],'-m','alice_renderer.cli','render-config',str(path),'--geometry-detail','current','--input',JOB['event'],'--event',str(EVENT['id']),'--assets',str(asset_map),'--blender',bpy.app.binary_path,'--backend',backend,'--quality','balanced' if self.quality=='custom' else self.quality,'--output',bpy.path.abspath(self.output)]
            command+=['--resolution-percent',str(self.resolution_percent or PRESET_PERCENT[self.quality])]
            if check.video_enabled:
                event_list=root/('video-events-'+str(time.time_ns())+'.local.json');event_list.write_text(json.dumps(JOB['events']));command+=['--event-files',str(event_list)]
                if self.render_kind=='video':command+=['--ffmpeg',encoder]
                else:command+=['--video-frame',str(self.playback_frame)]
            if self.quality=='custom':command+=['--samples',str(self.samples)]
            log_path=root/('full-render-'+str(time.time_ns())+'.log')
            with log_path.open('w') as log:process=subprocess.Popen(command,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
            ui.render_status='Starting render';ui.render_percent=0
            offset=0
            def monitor():
                nonlocal offset
                import re
                try:
                    with log_path.open() as stream:
                        stream.seek(offset)
                        for line in stream:
                            match=re.search(r'Render progress: (\d+)%',line)
                            if match:ui.render_percent=int(match[1])
                            if line.strip():ui.render_status=line.strip()[-160:]
                        offset=stream.tell()
                    for screen in bpy.data.screens:
                        for area in screen.areas:
                            if area.type=='VIEW_3D':area.tag_redraw()
                    if process.poll() is not None:
                        ui.render_status='Render completed' if process.returncode==0 else 'Render failed: '+str(log_path)
                        return None
                    return .5
                except ReferenceError:return None
            bpy.app.timers.register(monitor,first_interval=.5)
            self.report({'INFO'},'Full render started; progress in '+str(log_path));return {'FINISHED'}
        except Exception as exc:self.report({'ERROR'},str(exc));return {'CANCELLED'}

class PlayVideo(bpy.types.Operator):
    bl_idname='alice_eve.play_video';bl_label='Play collisions';bl_description='Loop selected collisions using the current timing and propagation controls'
    def execute(self,context):
        try:
            player=JOB.get('video_player')
            if player is None:
                import dataclasses
                from alice_renderer.runtime import prepare_video
                from video_player import VideoPlayer
                if any(not Path(p).is_file() for p in JOB.get('events',[])):raise ValueError('Selected events need track preparation. Use Play collisions in the desktop GUI to prepare and open the selected AO2D events.')
                cfg,payload=prepare_video(dataclasses.replace(current_settings(),video_enabled=True),[Path(p) for p in JOB.get('events',[])],DEVICES,Path(JOB['output']))
                JOB.update(payload);context.scene.alice_eve.video_enabled=True;context.scene.render.use_persistent_data=True
                player=VideoPlayer(JOB,cfg.to_dict(),JOB.get('track_regions',{}));JOB['video_player']=player;player.set_frame(0)
                if not bpy.app.background and not JOB.get('controls_watcher'):bpy.ops.alice_eve.watch_playback_controls('INVOKE_DEFAULT')
            else:player.reconfigure(current_settings())
            player.hold_controls(False);player.play();return {'FINISHED'}
        except Exception as exc:self.report({'ERROR'},str(exc));return {'CANCELLED'}

class StopVideo(bpy.types.Operator):
    bl_idname='alice_eve.stop_video';bl_label='Pause collisions';bl_description='Pause collision playback immediately at the current frame; Play collisions resumes'
    def execute(self,context):
        player=JOB.get('video_player')
        if player:player.stop()
        return {'FINISHED'}

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
    player=JOB.get('video_player') if JOB else None
    if player:
        matrix=np.array(area.spaces.active.region_3d.perspective_matrix)
        for identity,points in player.visible_paths():
            coordinates=np.c_[points*.01,np.ones(len(points))]
            hit=projected_hit(mouse,coordinates,matrix,region.width,region.height)
            if hit is not None:
                rank=(round(hit[0],6),hit[1])
                if best is None or rank<best[0]:best=(rank,identity)
        return None if best is None else best[1]
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
        if JOB.get('video_player'):JOB['video_player'].stop()
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
            from alice_renderer.picking import inside_viewport
            if not inside_viewport(self.area,self.region,event.mouse_x,event.mouse_y):return {'PASS_THROUGH'}
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
        root=self.layout;layout=root;ui=context.scene.alice_eve
        row=layout.row();row.operator('alice_eve.render_full',text='Render…');row.operator('alice_eve.export',text='Save config')
        layout.label(text=ui.render_status)
        if 0<ui.render_percent<100:
            row=layout.row();row.enabled=False;row.prop(ui,'render_percent',slider=True)
        layout.operator('alice_eve.pause_viewport',text='Resume viewport' if ui.viewport_paused else 'Pause viewport',icon='PLAY' if ui.viewport_paused else 'PAUSE')
        header,body=root.panel('alice_playback',default_closed=False)
        header.label(text='Collision playback')
        if body is not None:
            layout=body
            if len(JOB.get('events',[]))>=2:
                box=layout.box();box.label(text='Collision video');box.label(text=ui.video_status)
                row=box.row();row.operator('alice_eve.play_video');row.operator('alice_eve.stop_video')
                box.prop(ui,'pause_while_editing')
                box.label(text='Playback waiting for sidebar editing' if JOB.get('video_player') and JOB['video_player'].held_at is not None else 'Play starts immediately; editing holds playback')
                for key in ('video_enabled','video_timing','video_interval_s','video_time_scale','video_speed_m_s','video_tower_rise_s','video_fps'):box.prop(ui,key)
        header,body=root.panel('alice_camera',default_closed=True)
        header.label(text='Camera')
        if body is not None:
            layout=body
            layout.label(text='Orbit/pan/zoom, then use view as camera.')
            layout.operator('alice_eve.camera_from_view');layout.operator('alice_eve.level_camera');layout.prop(context.scene.camera,'rotation_euler')
            layout.prop(context.space_data,'lock_camera',text='Navigate render camera')
            row=layout.row();row.operator('alice_eve.roll_camera',text='Roll −15°').angle=-15;row.operator('alice_eve.roll_camera',text='Roll +15°').angle=15
            layout.label(text='Trackball navigation permits arbitrary orientation.')
            layout.prop(context.scene.camera.data,'type');layout.prop(context.scene.camera.data,'lens');layout.prop(context.scene.camera.data,'ortho_scale')
        header,body=root.panel('alice_surfaces',default_closed=True)
        header.label(text='Geometry and viewport')
        if body is not None:
            layout=body
            layout.operator('alice_eve.solid_surfaces');layout.operator('alice_eve.light_transparent_surfaces');layout.operator('alice_eve.restore_surface_exclusions');layout.operator('alice_eve.tpc_sectors_inner_wall');layout.operator('alice_eve.fast_surfaces');layout.operator('alice_eve.surround_lighting');layout.prop(ui,'viewport_renderer');layout.prop(ui,'viewport_samples')
            layout.prop(ui,'geometry_lod');layout.operator('alice_eve.full_geometry')
            layout.operator('alice_eve.select_no_detectors');layout.operator('alice_eve.complete_geometry')
            layout.label(text='Outer shell / outline are approximate hulls.')
            layout.operator('alice_eve.opaque_geometry');layout.operator('alice_eve.apply_geometry')
        header,body=root.panel('alice_data',default_closed=True)
        header.label(text='Tracks and clusters')
        if body is not None:
            layout=body
            if EVENT.get('contributors') is not None or JOB.get('video_player'):layout.label(text='Primary vertex contributors: '+str(EVENT.get('contributors','unavailable')))
            layout.label(text='Detector counts refer to input fitted records.')
            counts=JOB['input_counts']
            layout.label(text=f'Displayed: {ui.displayed_tracks} tracks / {ui.displayed_clusters} clusters')
            flags=counts['association_flags_available'] or any(h.get('association_flags_available') for h in JOB.get('video_headers',[]))
            if flags:layout.label(text=str(counts['ambiguous_drawable_tracks'])+' input tracks have ambiguous vertex matches')
            row=layout.row();row.enabled=flags;row.prop(ui,'include_ambiguous_tracks')
            layout.prop(ui,'tpc_cluster_profile');layout.prop(ui,'tpc_profile_scale');layout.prop(ui,'tpc_profile_thickness_cm')
            tower_box=layout.box();tower_box.label(text='Calorimeter towers (per detector below)')
            for key in ('tower_fixed_height_cm','tower_max_height_cm','tower_width_scale','tower_direction','tower_height_mapping'):tower_box.prop(ui,key)
            layout.prop(ui,'mode');layout.prop(ui,'track_width_cm');layout.prop(ui,'cluster_radius_cm');layout.prop(ui,'clip_tracks');layout.prop(ui,'track_color');layout.prop(ui,'cluster_color')
            box=layout.box();box.label(text='Track emphasis / decay chain');box.prop(ui,'highlight_ids')
            if ui.picking_active:box.operator('alice_eve.stop_picking',text='Stop picking (Esc)')
            else:box.operator('alice_eve.pick_tracks')
            box.prop(ui,'highlight_width_cm');box.prop(ui,'highlight_cluster_radius_cm');box.prop(ui,'highlight_override');box.prop(ui,'highlight_track_color');box.prop(ui,'highlight_cluster_color')
            for kind in ('track','cluster'):
                box=layout.box();box.prop(ui,kind+'_mode');row=box.row();row.prop(ui,kind+'_min');row.prop(ui,kind+'_max')
            layout.prop(ui,'palette');layout.operator('alice_eve.apply_data')
        header,body=root.panel('alice_detectors',default_closed=True)
        header.label(text='Detector settings')
        if body is not None:
            layout=body;cfg=current_settings().to_dict()
            for item in ui.detectors:
                header,box=layout.panel('alice_detector_'+item.name,default_closed=True)
                header.label(text=f'{item.name}: {item.event_track_count} tracks / {item.event_cluster_count} clusters' if item.data_available else item.name)
                if box is None:continue
                row=box.row();row.enabled=item.data_available;row.prop(item,'data');row.prop(item,'mode')
                if item.name!='L3':box.prop(item,'cluster_size_scale')
                if item.name in ('EMC','PHS','CPV'):
                    row=box.row();row.enabled=item.data_available;row.prop(item,'cell_display')
                    if item.cell_display=='signal towers':box.prop(item,'tower_height_scale',text='Height (cm / input unit)' if item.name=='PHS' else 'Height (cm / amplitude)' if item.name=='CPV' else 'Height (cm / GeV)')
                    if item.cell_display!='points':
                        box.prop(item,'tower_width_factor');box.prop(item,'tower_max_height_cm')
                        if item.cell_display=='fixed towers':box.prop(item,'tower_fixed_height_cm')
                        else:
                            box.prop(item,'tower_mapping')
                            if item.tower_mapping=='log' or item.tower_mapping=='inherit' and ui.tower_height_mapping=='log':box.prop(item,'tower_log_reference')
                        box.label(text=f'{item.tower_count} towers / {item.tower_point_fallbacks} point fallbacks')
                        if item.tower_nominal_footprints:box.label(text=f'{item.tower_nominal_footprints} nominal footprints (older export)')
                    if item.name=='CPV':box.label(text='CPV reconstructed clusters remain cluster glyphs')
                row=box.row();row.enabled=item.geometry_available;row.prop(item,'visible')
                box.prop(item,'asset_path')
                if not item.geometry_available:box.label(text='Choose an aligned asset to add this surface')
                if item.geometry_available:
                    kind=geometry_description(cfg,item.name)
                    box.label(text='Geometry source: '+kind)
                    if cfg['geometry_lods'].get(item.name,cfg['geometry_lod']) in ('structural','proxy'):box.label(text='Fine parts omitted; layers / walls / sectors retained')
                    box.prop(item,'detail');box.prop(item,'display');box.prop(item,'opening');box.prop(item,'opening_direction');box.prop(item,'exclusions');box.prop(item,'color');box.prop(item,'opacity')
                    box.prop(item,'show_components')
                    if item.show_components:
                        box.operator('alice_eve.refresh_components').detector=item.name;box.prop(item,'component_category');box.prop(item,'component_filter')
                        displayed=0;component_enabled=not is_schematic(current_settings().to_dict(),item.name)
                        coll=bpy.data.collections.get(item.name)
                        supported=set(json.loads(coll.get('alice_structural_components','[]'))) if coll else set()
                        large=cfg['geometry_lods'].get(item.name,cfg['geometry_lod']) in ('structural','proxy')
                        for component in item.components:
                            if component.identifier.split('/')[0]!=item.component_category:continue
                            if item.component_filter and item.component_filter.lower() not in (component.identifier+' '+component.label).lower():continue
                            displayed+=1
                            if displayed>200:box.label(text='Filter to show more than 200 named elements');break
                            row=box.row();row.enabled=component_enabled and (not large or component.identifier in supported)
                            op=row.operator('alice_eve.toggle_component',text=('  '*component.identifier.count('/'))+component.label+' ('+str(component.count)+')',icon='CHECKBOX_HLT' if component.enabled else 'CHECKBOX_DEHLT',depress=component.enabled);op.detector=item.name;op.identifier=component.identifier
                        if not item.components:box.label(text='No hierarchy metadata for this asset')
                    box.prop(item,'inner_mask_radius')
                    if item.inner_mask_radius>0:box.prop(item,'inner_mask_patterns');box.prop(item,'inner_mask_front')
        header,body=root.panel('alice_lighting',default_closed=True)
        header.label(text='Lighting and materials')
        if body is not None:
            layout=body
            layout.prop(ui,'background');layout.prop(ui,'world_strength');layout.prop(ui,'view_transform');layout.prop(ui,'exposure');layout.prop(ui,'track_emission');layout.prop(ui,'cluster_emission');layout.prop(ui,'data_glow_lighting');layout.prop(ui,'roughness');layout.prop(ui,'metallic');layout.prop(ui,'shading')
            layout.operator('alice_eve.show_scene_lighting')
            layout.label(text='Scene area lights: '+str(sum(o.type=='LIGHT' and o.data.type=='AREA' for o in context.scene.objects)))
            for lamp in (o for o in context.scene.objects if o.type=='LIGHT'):
                box=layout.box();box.label(text=lamp.name);box.prop(lamp,'location');box.prop(lamp,'rotation_euler');box.prop(lamp.data,'energy');box.prop(lamp.data,'size');box.prop(lamp.data,'color')
        header,body=root.panel('alice_export',default_closed=True)
        header.label(text='Save options')
        if body is not None:
            layout=body
            layout.prop(ui,'export_path');layout.prop(ui,'include_defaults')


CLASSES=(GeometryComponent,ToggleComponent,RefreshComponents,DetectorSettings,SceneSettings,RenderGeometryDetail,ApplyData,ApplyGeometry,SelectNoDetectors,CompleteGeometry,FullAlignedGeometry,OpaqueGeometry,SolidDetectorSurfaces,LightTransparentSurfaces,RestoreSurfaceExclusions,TPCSectorsInnerWall,SurroundLighting,FastStructuralSurfaces,ShowSceneLighting,CameraFromView,LevelCamera,RollCamera,PickTracks,StopPicking,PlayVideo,StopVideo,ToggleViewportPause,WatchPlaybackControls,ExportConfig,RenderFull,EVEPanel)

def start_editor(job,event,metadata):
    global JOB,EVENT,DEVICES,RECOMMENDATION,PALETTES
    PALETTES=job.get('palettes',{})
    if not PALETTES:
        from worker import scale_color
        PALETTES={name:[list(scale_color(i/255,0,1,name)) for i in range(256)] for name in ('viridis','coolwarm','hsv')}
    if job['settings'].get('palette_lut'):PALETTES[job['settings']['palette']]=job['settings']['palette_lut']
    PALETTE_ITEMS[:]=[(name,name,'') for name in sorted(PALETTES)]
    JOB=None;EVENT=event;DEVICES=job['blender'];RECOMMENDATION=recommended_quality(DEVICES)
    from alice_renderer.model import capabilities
    extra=set(capabilities(event['tracks']))|set(capabilities(event['clusters']))
    for header in job.get('video_headers',[]):extra.update(header.get('track_fields',[]));extra.update(header.get('cluster_fields',[]))
    extra|={job['settings']['track_color_mode'],job['settings']['cluster_color_mode']}
    for name in sorted(extra):
        if not any(i[0]==name for i in COLOR_ITEMS):COLOR_ITEMS.append((name,name,'Numeric input track feature'))
    for cls in CLASSES:bpy.utils.register_class(cls)
    bpy.types.Scene.alice_eve=bpy.props.PointerProperty(type=SceneSettings)
    scene=bpy.context.scene;ui=scene.alice_eve;settings=job['settings']
    for key,default in (('video_enabled',False),('video_timing','fixed'),('video_interval_s',1.),('video_time_scale',0.),('video_speed_m_s',10.),('video_tower_rise_s',.2),('video_fps',24)):setattr(ui,key,settings.get(key,default))
    # Suppress updates during property initialization.
    from worker import rgb
    ui.tpc_cluster_profile=settings.get('tpc_cluster_profile','sphere');ui.tpc_profile_scale=settings.get('tpc_profile_scale',1.);ui.tpc_profile_thickness_cm=settings.get('tpc_profile_thickness_cm',.03)
    for key,default in (('tower_fixed_height_cm',10.),('tower_max_height_cm',100.),('tower_width_scale',.95),('tower_direction','inward'),('tower_height_mapping','linear')):setattr(ui,key,settings.get(key,default))
    ui.cluster_radius_cm=settings['cluster_radius_cm'];ui.highlight_ids=', '.join(settings.get('highlight_track_ids',[]));ui.highlight_width_cm=settings.get('highlight_track_radius_cm',.35)*2;ui.highlight_cluster_radius_cm=settings.get('highlight_cluster_radius_cm',1.);ui.highlight_override=settings.get('highlight_override_color',True);ui.highlight_track_color=rgb(settings.get('highlight_track_color','#ffcc33'));ui.highlight_cluster_color=rgb(settings.get('highlight_cluster_color','#ff6633'))
    ui.track_width_cm=settings['track_radius_cm']*2;ui.clip_tracks=settings.get('clip_tracks',True);ui.include_ambiguous_tracks=settings.get('include_ambiguous_tracks',True)
    ui.geometry_lod=settings.get('geometry_lod','full')
    ui.mode=settings['mode'];ui.track_mode=settings['track_color_mode'];ui.cluster_mode=settings['cluster_color_mode'];ui.palette=settings['palette']
    ui.background=settings.get('colors_linear',{}).get('background',rgb(settings['colors']['background']));ui.track_color=settings.get('colors_linear',{}).get('tracks',rgb(settings['colors']['tracks']));ui.cluster_color=settings.get('colors_linear',{}).get('clusters',rgb(settings['colors']['clusters']))
    ui.world_strength=settings['world_strength'];ui.roughness=settings['roughness'];ui.metallic=settings['metallic'];ui.shading=settings['shading']
    ui.view_transform=settings.get('view_transform','AgX');ui.exposure=settings.get('exposure',0.);ui.track_emission=settings.get('track_emission',.7);ui.cluster_emission=settings.get('cluster_emission',1.)
    ui.data_glow_lighting=settings.get('data_glow_lighting',True)
    available=set(event.get('data_detectors',[]))|{d for t in event['tracks'] for d in t['detectors']}|{c['detector'] for c in event['clusters']}
    for header in job.get('video_headers',[]):available.update(header.get('available_detectors',[]))
    counts=event_counts(event);track_counts=counts['tracks_by_detector'];cluster_counts=counts['clusters_by_detector']
    from alice_renderer.model import DETECTORS
    for name in (*DETECTORS,'L3'):
        item=ui.detectors.add();item.name=name;item.data_available=name in available;item.data=name in settings['detectors'];item.mode=settings.get('detector_modes',{}).get(name,settings['mode']);item.asset_path=settings.get('geometry_assets',{}).get(name,'');item.geometry_available=bool(item.asset_path and Path(item.asset_path).is_file()) or is_schematic(settings,name);item.visible=name in settings['geometry'] or name=='L3' and settings['magnet']
        item.display=settings.get('geometry_display',{}).get(name,'surfaces')
        item.detail='inherit' if is_schematic(settings,name) else settings.get('geometry_lods',{}).get(name,'inherit')
        item.event_track_count=track_counts.get(name,0);item.event_cluster_count=cluster_counts.get(name,0)
        item.cluster_size_scale=settings.get('cluster_size_scales',{}).get(name,1.)
        if name in ('EMC','PHS','CPV'):
            item.cell_display=settings.get('calorimeter_display',{}).get(name,'points')
            item.tower_height_scale=settings.get('tower_height_scales',{}).get(name,20. if name=='EMC' else .2)
            item.tower_width_factor=settings.get('tower_width_scales',{}).get(name,1.)
            item.tower_fixed_height_cm=settings.get('tower_fixed_heights_cm',{}).get(name,0.)
            item.tower_max_height_cm=settings.get('tower_max_heights_cm',{}).get(name,0.)
            item.tower_mapping=settings.get('tower_height_mappings',{}).get(name,'inherit')
            item.tower_log_reference=settings.get('tower_log_references',{}).get(name,1.)
            info=metadata.get('cluster_legend',{}).get('calorimeter_towers',{}).get(name,{})
            item.tower_count=info.get('towers',0);item.tower_point_fallbacks=info.get('point_fallbacks',0);item.tower_nominal_footprints=info.get('approximate_footprints',0)
        item.opening=settings['geometry_openings'].get(name,180 if settings['cutaway'] else 0);item.opacity=settings['geometry_opacities'].get(name,settings['geometry_opacity']);item.color=settings.get('colors_linear',{}).get('magnet' if name=='L3' else name,rgb(settings['colors'].get('magnet' if name=='L3' else name,'#243a82')))
        item.opening_direction=settings.get('geometry_opening_directions',{}).get(name,-90.);item.exclusions=', '.join(settings.get('geometry_exclusions',{}).get(name,[]))
        populate_components(item,settings.get('geometry_components',{}).get(name,{}))
        if name=='TPC':item.component_category='parts';item.show_components=True
        inner=settings.get('geometry_inner_masks',{}).get(name,{});item.inner_mask_radius=inner.get('radius_m',0);item.inner_mask_patterns=', '.join(inner.get('patterns',[]));item.inner_mask_front=inner.get('front_only',True)
    settings['palette_lut']=PALETTES[settings['palette']]
    locked=recipe(RenderSettings(**settings),event)['scene']['color_ranges']
    if settings.get('video_enabled'):locked.update(settings.get('color_ranges',{}))
    ui.track_min,ui.track_max=locked['tracks'];ui.cluster_min,ui.cluster_max=locked['clusters']
    ui.export_path=str(Path(job['output'])/'scene-config.json')
    JOB=job;JOB['input_counts']=metadata.get('input_counts') or event_counts(event)
    ui.displayed_tracks=metadata['rendered_tracks'];ui.displayed_clusters=metadata['rendered_clusters']
    JOB['applied_track_signature']=track_signature(ui);appearance_update(ui,bpy.context)
    bpy.context.preferences.inputs.view_rotate_method='TRACKBALL'
    if job.get('fast_interactive'):
        ui.viewport_renderer='BLENDER_EEVEE';ui.viewport_samples=32
    viewport_renderer_update(ui,bpy.context);scene.render.resolution_percentage=100
    for screen in bpy.data.screens:
        for area in screen.areas:
            if area.type=='VIEW_3D':
                area.spaces.active.show_region_ui=True;area.spaces.active.shading.type='RENDERED';area.spaces.active.region_3d.view_perspective='CAMERA';area.spaces.active.lock_camera=True
    bpy.context.view_layer.objects.active=scene.camera
    for obj in scene.objects:obj.select_set(False)
    scene.camera.select_set(True)
    if settings.get('video_enabled') and job.get('events'):
        from video_player import VideoPlayer
        player=VideoPlayer(job,settings,job.get('track_regions',{}));JOB['video_player']=player;player.set_frame(0);player.play()
        if not bpy.app.background:bpy.ops.alice_eve.watch_playback_controls('INVOKE_DEFAULT')
    bpy.ops.wm.save_as_mainfile(filepath=str(Path(job['output'])/'interactive.blend'))
    if job.get('library_path'):
        save_session();bpy.app.timers.register(save_session,first_interval=2.)
