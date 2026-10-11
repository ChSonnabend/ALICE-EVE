"""Matplotlib registry on the host; sampled RGB tables travel with scene recipes."""
import json
from pathlib import Path

NAMES_FILE=Path(__file__).with_name('palette_names.json')

def names():
    try:
        import matplotlib
        return sorted(matplotlib.colormaps)
    except ImportError:return json.loads(NAMES_FILE.read_text()) if NAMES_FILE.exists() else ['viridis','coolwarm','hsv']

def sample(name,count=256):
    import matplotlib
    if name not in matplotlib.colormaps:raise ValueError('Unknown colormap: '+name)
    cmap=matplotlib.colormaps[name]
    return [[float(c) for c in cmap(i/(count-1))[:3]] for i in range(count)]

def materialize(settings):
    if not settings.palette_lut:settings.palette_lut=sample(settings.palette)
    return settings

def interpolate(lut,value):
    t=max(0.,min(1.,value));p=t*(len(lut)-1);i=min(len(lut)-2,int(p));f=p-i
    return tuple(lut[i][k]*(1-f)+lut[i+1][k]*f for k in range(3))
