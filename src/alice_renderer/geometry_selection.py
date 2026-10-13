"""Explicit render geometry choices override legacy schematic and LOD defaults."""
from dataclasses import replace

def is_schematic(settings,name):
    return settings.get('geometry_schematics',{}).get(name,settings.get('schematic',False))

def detail(settings,name):
    return settings.get('geometry_lods',{}).get(name,settings.get('geometry_lod','full'))

def description(settings,name):
    if is_schematic(settings,name):return 'schematic envelope'
    if detail(settings,name)=='proxy':return 'cached approximate surfaces (fast interactive)'
    if detail(settings,name)=='structural':return 'large surfaces (cached display approximation)'
    style=settings.get('geometry_display',{}).get(name,'surfaces')
    if style!='surfaces':return style+' (approximate aligned outer hull)'
    return 'full aligned surfaces' if detail(settings,name)=='full' else 'simplified aligned cells'

def render_choices(cfg,choices):
    selected=set(cfg.geometry+(['L3'] if cfg.magnet else []))
    lods=dict(cfg.geometry_lods);schematics=dict(cfg.geometry_schematics);styles=dict(cfg.geometry_display)
    for name,choice in choices.items():
        if name not in selected:continue
        if choice=='current':continue
        if choice not in ('full','simplified','structural','proxy','schematic'):raise ValueError('Invalid render geometry choice')
        schematics[name]=choice=='schematic'
        if choice!='schematic':lods[name]=choice
        styles[name]='surfaces'
    return replace(cfg,geometry_lods=lods,geometry_schematics=schematics,geometry_display=styles).validate()

def final_render_choices(cfg,choices=None):
    """Full aligned surfaces by default; explicit per-detector choices still win."""
    names=cfg.geometry+(['L3'] if cfg.magnet else [])
    return render_choices(cfg,{name:(choices or {}).get(name,'full') for name in names})

def render_geometry_preset(cfg,preset):
    """Apply an obvious final-menu choice; preserve per-detector choices in recipes."""
    names=cfg.geometry+(['L3'] if cfg.magnet else [])
    if preset=='full':return final_render_choices(cfg)
    if preset=='current':return render_choices(cfg,{name:'current' for name in names})
    if preset!='simplified':raise ValueError('Invalid render geometry preset')
    # Use the same cache selection as Fast interactive. Detectors without a
    # compatible cache still have the aligned coarse-cell option.
    from .runtime import fast_editor_settings
    fast=fast_editor_settings(final_render_choices(cfg));values=fast.to_dict()
    choices={}
    for name in names:
        choice=detail(values,name)
        if choice not in ('proxy','structural'):choice='simplified'
        elif cfg.geometry_components.get(name):
            from .structural_geometry import supported_components
            from .surface_proxy import load as proxy_load
            from .structural_geometry import load as structural_load
            cache=(proxy_load if choice=='proxy' else structural_load)(cfg.geometry_assets[name],cfg.geometry_units)
            if set(cfg.geometry_components[name])-supported_components(cache):choice='simplified'
        choices[name]=choice
    return render_choices(cfg,choices)
