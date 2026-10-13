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
