"""Portable startup appearance; local inputs, alignment and hardware stay separate."""
from pathlib import Path
from .model import RenderSettings
from .scene_config import load_config

COMMISSIONING_PRESET=Path(__file__).with_name('presets')/'commissioning-interior.json'

def local_geometry_asset(value, manifest_path, project_root):
    """Resolve exported paths after moving a dataset between machines."""
    path=Path(value).expanduser()
    source=Path(manifest_path).parent
    candidates=[path if path.is_absolute() else source/path]
    # Keep the bundle name (e.g. run-560067); never substitute another run.
    if path.parent.name:
        candidates.extend([source/'geometry'/path.parent.name/path.name,
                           Path(project_root)/'geometry'/path.parent.name/path.name])
    candidates.append(source/path.name)
    return next((str(p.resolve()) for p in candidates if p.is_file()),None)

def commissioning_settings(assets=None,geometry_units=None):
    # This is a style clone. Exact reproduction through render-config still
    # requires the hash-checked original geometry bundle in the portable recipe.
    scene=dict(load_config(COMMISSIONING_PRESET)['scene'])
    if geometry_units is not None:scene['geometry_units']=geometry_units
    return RenderSettings(**scene,geometry_assets=dict(assets or {})).validate()

def startup_settings():
    # The second batch's reviewed, tested scene supersedes the withdrawn trial.
    return detector_settings('ALICE2')


SETUP_PRESETS={'ALICE2':'alice2.json','ALICE2 + ITS3':'alice2-its3.json','ALICE3':'alice3.json'}

def detector_settings(setup, project_root=None):
    from .scene_config import resolve_settings
    root=Path(project_root) if project_root else Path(__file__).resolve().parents[2]
    preset=Path(__file__).with_name('presets')/SETUP_PRESETS[setup]
    data=load_config(preset)
    bundle={'ALICE2':'run-560067','ALICE2 + ITS3':'alice2-its3','ALICE3':'alice3'}[setup]
    assets={}
    for name,ref in data['geometry'].items():
        target=root/'geometry'/bundle/ref['file']
        if setup=='ALICE2 + ITS3' and name!='ITS':target=root/'geometry/run-560067'/ref['file']
        if target.is_file():assets[name]=str(target)
    # Make optional detector surfaces available in Setup without changing which
    # surfaces the saved camera recipe initially shows.
    from .model import DETECTORS
    folders=[root/'geometry/run-560067',root/'geometry'/bundle] if setup=='ALICE2 + ITS3' else [root/'geometry'/bundle]
    for folder in folders:
        for asset in folder.glob('*.blend'):
            if asset.stem in (*DETECTORS,'L3') and asset.stem not in data['geometry']:
                assets[asset.stem]=str(asset.resolve())
    if all(name in assets for name in data['geometry']):return resolve_settings(data,preset,asset_overrides=assets)
    # Packaged installs can open before downloading the geometry bundle.
    return RenderSettings(**data['scene'],geometry_assets=assets).validate()
