"""Portable startup appearance; local inputs, alignment and hardware stay separate."""
from pathlib import Path
from .model import RenderSettings
from .scene_config import load_config

COMMISSIONING_PRESET=Path(__file__).with_name('presets')/'commissioning-interior.json'

def startup_settings(assets=None,geometry_units=None):
    # This is a style clone. Exact reproduction through render-config still
    # requires the hash-checked original geometry bundle in the portable recipe.
    scene=dict(load_config(COMMISSIONING_PRESET)['scene'])
    if geometry_units is not None:scene['geometry_units']=geometry_units
    return RenderSettings(**scene,geometry_assets=dict(assets or {})).validate()
