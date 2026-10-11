"""Portable interchange schema. Coordinates are ALICE global centimetres."""
from __future__ import annotations
import math, re
from dataclasses import asdict, dataclass, field
from typing import Any

DETECTORS = ("ITS", "TPC", "TRD", "TOF", "HMP", "EMC", "PHS", "CPV", "MCH", "MFT", "MID", "FT0", "FV0", "FDD", "ZDC")
ALIASES = {"HMPID":"HMP", "EMCAL":"EMC", "PHOS":"PHS", "V0":"FV0"}
COLOR_FIELDS = ("solid", "eta", "tan_lambda", "phi", "p", "pt", "x", "y", "z", "dca", "primaries", "secondaries", "matching")

def detector(value: str) -> str:
    value = ALIASES.get(str(value).upper(), str(value).upper())
    if value not in DETECTORS: raise ValueError(f"Unknown ALICE detector: {value}")
    return value

def xyz(value: Any) -> list[float]:
    if not isinstance(value, (list,tuple)) or len(value)!=3:
        raise ValueError("Position must contain three global coordinates")
    result = [float(v) for v in value]
    if not all(math.isfinite(v) for v in result): raise ValueError("Non-finite coordinate")
    return result

def kinematics(data: dict) -> dict[str,float]:
    result = {}
    for key,val in data.items():
        if key not in COLOR_FIELDS or key in ("solid","primaries","secondaries","matching"): continue
        if val is not None and math.isfinite(float(val)): result[key] = float(val)
    # Only derive quantities from momentum, never from sampled track geometry.
    if all(key in result for key in ("pt","p")) and result['p'] < result['pt']:
        raise ValueError("Momentum magnitude cannot be smaller than transverse momentum")
    if 'tan_lambda' in result: result.setdefault('eta', math.asinh(result['tan_lambda']))
    if 'eta' in result and 'tan_lambda' not in result:
        if abs(result['eta'])>700:raise ValueError('Eta outside finite tan(lambda) range')
        result['tan_lambda']=math.sinh(result['eta'])
    return result

def validate_event(raw: dict) -> dict:
    if raw.get('schema_version') != 1: raise ValueError("Expected ALICE interchange schema_version=1")
    if raw.get('units') != 'cm': raise ValueError("Event positions must be ALICE global centimetres (units=cm)")
    if raw.get('kind') not in ('collision','timeframe','rof','synthetic'):
        raise ValueError("Event kind must declare collision/timeframe/rof/synthetic")
    if not str(raw.get('id','')).strip(): raise ValueError("Event identifier is required")
    event = dict(raw)
    if event.get('vertex') is not None: event['vertex'] = xyz(event['vertex'])
    event['tracks'],event['clusters'] = [],[]
    track_ids=set()
    for index,original in enumerate(raw.get('tracks',[])):
        track = dict(original)
        track['id'] = str(track.get('id',index))
        if track['id'] in track_ids:raise ValueError('Duplicate track identifier: '+track['id'])
        track_ids.add(track['id'])
        track['detectors'] = sorted({detector(v) for v in track['detectors']})
        if not track['detectors']: raise ValueError("Track detector/source association is required")
        track['points'] = [xyz(p) for p in track['points']]
        if len(track['points'])<2: raise ValueError("A track needs at least two sampled points")
        if 'matching' in track and (not isinstance(track['matching'],bool) or not track.get('matching_basis')):raise ValueError('Matching status requires a boolean and matching_basis')
        track['kinematics'] = kinematics(track.get('kinematics',{}))
        if 'features' in track:
            if not isinstance(track['features'],dict):raise ValueError('Track features must be a numeric mapping')
            track['features']={str(k):v for k,v in track['features'].items() if isinstance(v,(int,float)) and math.isfinite(v)}
        if 'classification' in track and track['classification'] not in ('primary','secondary','unknown'):
            raise ValueError("Unsupported track classification")
        if track.get('classification') in ('primary','secondary') and not track.get('classification_basis'):
            raise ValueError("Primary/secondary labels require classification_basis (MC truth or reconstruction rule)")
        if 'dca' in track['kinematics'] and (event.get('vertex') is None or not track.get('dca_basis')):
            raise ValueError("DCA needs a primary vertex and an explicit propagation/convention basis")
        event['tracks'].append(track)
    for index,original in enumerate(raw.get('clusters',[])):
        cluster = dict(original)
        cluster['id'] = str(cluster.get('id',index))
        cluster['detector'] = detector(cluster['detector'])
        cluster['position'] = xyz(cluster['position'])
        if 'matching' in cluster and (not isinstance(cluster['matching'],bool) or not cluster.get('matching_basis')):raise ValueError('Cluster matching requires a boolean and matching_basis')
        cluster['kinematics'] = kinematics(cluster.get('kinematics',{}))
        if any(k in cluster['kinematics'] for k in ('eta','tan_lambda','phi','p','pt','dca')) and not cluster.get('kinematics_basis'):
            raise ValueError('Cluster kinematics require an explicit measurement or track-association basis')
        if cluster.get('classification') in ('primary','secondary') and not cluster.get('classification_basis'):
            raise ValueError('Cluster primary/secondary labels require classification_basis')
        event['clusters'].append(cluster)
    event['available_detectors'] = sorted({detector(d) for d in raw.get('data_detectors',[])} |
                                        {d for t in event['tracks'] for d in t['detectors']} |
                                        {c['detector'] for c in event['clusters']})
    from .object_selection import annotate_matching
    return annotate_matching(event)

def color_value(obj: dict, mode: str, position: list[float] | None = None) -> float | None:
    if mode.startswith('feature:'):return obj.get('features',{}).get(mode.removeprefix('feature:'))
    if mode == 'matching':
        from .object_selection import matching_value
        return matching_value(obj)
    if mode == 'solid': return None
    if mode in ('x','y','z'):
        p = position or obj.get('position')
        # For a track this is its first sampled position; documented in the UI.
        if p is None: p = obj.get('points',[None])[0]
        return None if p is None else float(p[('x','y','z').index(mode)])
    if mode in ('primaries','secondaries'):
        if obj.get('classification') not in ('primary','secondary'): return None
        return float(obj['classification'] == ('primary' if mode=='primaries' else 'secondary'))
    return obj.get('kinematics',{}).get(mode)

def capabilities(objects: list[dict]) -> list[str]:
    extra=sorted({'feature:'+k for o in objects for k,v in o.get('features',{}).items() if isinstance(v,(int,float)) and math.isfinite(v)})
    return ['solid'] + [m for m in COLOR_FIELDS[1:] if any(color_value(o,m) is not None for o in objects)]+extra

@dataclass
class RenderSettings:
    detectors: list[str] = field(default_factory=lambda: list(DETECTORS))
    geometry: list[str] = field(default_factory=list)
    magnet: bool = False
    mode: str = 'tracks'
    detector_modes: dict = field(default_factory=dict)
    track_color_mode: str = 'solid'
    cluster_color_mode: str = 'solid'
    colors: dict = field(default_factory=lambda: {'tracks':'#ee8ff5','clusters':'#94e5ff','background':'#070b20','magnet':'#315285', **{d:'#243a82' for d in DETECTORS}})
    scale_min: float | None = None
    scale_max: float | None = None
    palette: str = 'viridis'
    palette_lut: list = field(default_factory=list)
    missing_color: str = '#808080'
    geometry_assets: dict[str,str] = field(default_factory=dict)
    geometry_units: str = 'cm'
    geometry_opacity: float = 0.18
    cutaway: bool = False
    schematic: bool = False
    width: int = 1920
    height: int = 1080
    samples: int = 128
    denoise: bool = True
    backend: str = 'CPU'
    device: str = ''
    threads: int = 0
    track_radius_cm: float = 0.12
    clip_tracks: bool = True
    highlight_track_ids: list = field(default_factory=list)
    highlight_track_radius_cm: float = .35
    highlight_cluster_radius_cm: float = 1.
    highlight_override_color: bool = True
    highlight_track_color: str = '#ffcc33'
    highlight_cluster_color: str = '#ff6633'
    cluster_radius_cm: float = 0.35
    camera: str = 'perspective'
    camera_lens_mm: float = 48.
    camera_orbit_axis: str = 'Y'
    azimuth: float = -55.0
    elevation: float = 0.0
    roll: float = 0.
    distance_cm: float = 1600.0
    target_cm: list[float] = field(default_factory=lambda:[0.,0.,0.])
    save_blend: bool = True
    output_format: str = 'PNG'
    frame_aspect: float = 16/9
    camera_pose: dict = field(default_factory=dict)
    color_ranges: dict = field(default_factory=dict)
    colors_linear: dict = field(default_factory=dict)
    geometry_lod: str = 'full'
    geometry_lods: dict = field(default_factory=dict)
    geometry_schematics: dict = field(default_factory=dict)
    geometry_display: dict = field(default_factory=dict)
    geometry_openings: dict = field(default_factory=dict)
    geometry_opening_directions: dict = field(default_factory=dict)
    geometry_exclusions: dict = field(default_factory=dict)
    geometry_components: dict = field(default_factory=dict)
    geometry_inner_masks: dict = field(default_factory=dict)
    geometry_opacities: dict = field(default_factory=dict)
    roughness: float = .38
    metallic: float = .15
    shading: str = 'smooth'
    world_strength: float = .45
    view_transform: str = 'AgX'
    exposure: float = 0.
    track_emission: float = .7
    cluster_emission: float = 1.
    lights: list = field(default_factory=lambda:[
        {'position_m':[5.,-5.,10.], 'energy':1800., 'size_m':8., 'color':'#ffffff'},
        {'position_m':[-8.,3.,4.], 'energy':1200., 'size_m':10., 'color':'#ffffff'},
        {'position_m':[0.,0.,-10.], 'energy':1000., 'size_m':8., 'color':'#ffffff'}])

    def validate(self):
        if not isinstance(self.clip_tracks,bool):raise ValueError('Track clipping must be a boolean')
        if self.mode not in ('tracks','clusters','both'): raise ValueError('Invalid rendering mode')
        for name,mode in self.detector_modes.items():
            detector(name)
            if mode not in ('tracks','clusters','both'):raise ValueError('Invalid per-detector object mode')
        from .object_selection import parse_track_ids
        self.highlight_track_ids=parse_track_ids(self.highlight_track_ids)
        for v in self.detectors+self.geometry: detector(v)
        if self.backend not in ('CPU','METAL','HIP','CUDA','OPTIX'): raise ValueError('Invalid Cycles backend')
        if not 64<=self.width<=16384 or not 64<=self.height<=16384: raise ValueError('Resolution must be 64–16384 pixels')
        if not 1<=self.samples<=8192: raise ValueError('Samples must be 1–8192')
        if not 0<=self.geometry_opacity<=1: raise ValueError('Opacity must be between zero and one')
        if any(m not in COLOR_FIELDS and not re.fullmatch(r'feature:[a-z][a-z0-9_]*',m) for m in (self.track_color_mode,self.cluster_color_mode)): raise ValueError('Invalid colour mode')
        if self.scale_min is not None and self.scale_max is not None and self.scale_min>=self.scale_max: raise ValueError('Colour minimum must be less than maximum')
        if self.geometry_units not in ('cm','m'): raise ValueError('Geometry units must be cm or m')
        if self.camera not in ('perspective','orthographic'):raise ValueError('Invalid camera type')
        if not math.isfinite(self.camera_lens_mm) or not .1<=self.camera_lens_mm<=5000:raise ValueError('Invalid camera focal length')
        if self.camera_orbit_axis not in ('Y','Z'):raise ValueError('Invalid camera orbit axis')
        if self.palette_lut:
            if len(self.palette_lut)<2 or any(len(c)!=3 or any(not math.isfinite(v) or not 0<=v<=1 for v in c) for c in self.palette_lut):raise ValueError('Invalid colormap RGB table')
        else:
            from .palettes import names
            if self.palette not in names():raise ValueError('Invalid colour scale')
        if self.output_format!='PNG':raise ValueError('This version renders 16-bit PNG')
        for key in ('tracks','clusters','background','magnet',*self.geometry):
            if not re.fullmatch(r'#[0-9a-fA-F]{6}',self.colors.get(key,'')):raise ValueError(f'{key}: expected a colour in #rrggbb format')
        if not re.fullmatch(r'#[0-9a-fA-F]{6}',self.missing_color):raise ValueError('Invalid missing-value colour')
        if self.threads<0:raise ValueError('CPU thread count must be nonnegative')
        xyz(self.target_cm)
        for name in ('azimuth','elevation','roll','distance_cm','track_radius_cm','cluster_radius_cm','highlight_track_radius_cm','highlight_cluster_radius_cm'):
            if not math.isfinite(getattr(self,name)):raise ValueError(f'{name} must be finite')
        if self.track_radius_cm<=0 or self.cluster_radius_cm<=0 or self.distance_cm<=0: raise ValueError('Radii and camera distance must be positive')
        if self.highlight_track_radius_cm<=0 or self.highlight_cluster_radius_cm<=0:raise ValueError('Highlight sizes must be positive')
        for color in (self.highlight_track_color,self.highlight_cluster_color):
            if not re.fullmatch(r'#[0-9a-fA-F]{6}',color):raise ValueError('Invalid highlight colour')
        if not isinstance(self.highlight_override_color,bool):raise ValueError('Highlight colour override must be boolean')
        if self.geometry_lod not in ('full','simplified'):raise ValueError('Invalid geometry detail')
        for name,lod in self.geometry_lods.items():
            if name!='L3':detector(name)
            if lod not in ('full','simplified'):raise ValueError('Invalid per-detector geometry detail')
        for name,approximate in self.geometry_schematics.items():
            if name!='L3':detector(name)
            if not isinstance(approximate,bool):raise ValueError('Per-detector schematic choice must be boolean')
        if self.shading not in ('smooth','flat'):raise ValueError('Invalid shading')
        for key in ('roughness','metallic'):
            if not math.isfinite(getattr(self,key)) or not 0<=getattr(self,key)<=1:raise ValueError('Invalid '+key)
        if not math.isfinite(self.frame_aspect) or not .05<=self.frame_aspect<=20:raise ValueError('Invalid frame aspect ratio')
        if not math.isfinite(self.world_strength) or self.world_strength<0:raise ValueError('Invalid background strength')
        if self.view_transform not in ('AgX','Standard'):raise ValueError('Invalid display colour transform')
        if not math.isfinite(self.exposure) or not -20<=self.exposure<=20:raise ValueError('Exposure must be between -20 and 20 stops')
        for name in ('track_emission','cluster_emission'):
            if not math.isfinite(getattr(self,name)) or not 0<=getattr(self,name)<=100:raise ValueError('Invalid '+name)
        for name,style in self.geometry_display.items():
            if name!='L3':detector(name)
            if style not in ('surfaces','shell','outline'):raise ValueError('Invalid detector display style')
        for name,angle in self.geometry_openings.items():
            if name!='L3':detector(name)
            if not math.isfinite(angle) or not 0<=angle<=360:raise ValueError('Opening must be 0–360 degrees')
        for name,angle in self.geometry_opening_directions.items():
            if name!='L3':detector(name)
            if not math.isfinite(angle) or not -360<=angle<=360:raise ValueError('Opening direction must be between −360 and 360 degrees')
        for name,patterns in self.geometry_exclusions.items():
            if name!='L3':detector(name)
            if not isinstance(patterns,list) or any(not isinstance(p,str) or not p.strip() or len(p)>1024 for p in patterns):raise ValueError('Geometry exclusions must be a list of nonempty name patterns')
        for name,choices in self.geometry_components.items():
            if name!='L3':detector(name)
            if not isinstance(choices,dict) or any(not isinstance(k,str) or not k or not isinstance(v,bool) for k,v in choices.items()):raise ValueError('Invalid detector component visibility choices')
        for name,rule in self.geometry_inner_masks.items():
            if name!='L3':detector(name)
            if not isinstance(rule,dict) or set(rule)-{'patterns','radius_m','front_only'}:raise ValueError('Invalid inner geometry mask')
            patterns=rule.get('patterns',[]);radius=rule.get('radius_m',0)
            if not isinstance(patterns,list) or any(not isinstance(p,str) or not p.strip() for p in patterns):raise ValueError('Invalid inner component patterns')
            if not math.isfinite(radius) or radius<=0 or not isinstance(rule.get('front_only',True),bool):raise ValueError('Invalid inner component mask radius or side')
        for name,opacity in self.geometry_opacities.items():
            if name!='L3':detector(name)
            if not math.isfinite(opacity) or not 0<=opacity<=1:raise ValueError('Invalid detector opacity')
        for pair in self.color_ranges.values():
            if len(pair)!=2 or not all(math.isfinite(v) for v in pair) or pair[0]>pair[1]:raise ValueError('Invalid fixed colour range')
        if self.camera_pose:
            matrix=self.camera_pose.get('matrix_world',[])
            if len(matrix)!=4 or any(len(row)!=4 or any(not math.isfinite(v) for v in row) for row in matrix):raise ValueError('Invalid camera matrix')
            for key in ('lens','ortho_scale'):
                if not math.isfinite(self.camera_pose.get(key,0)) or self.camera_pose.get(key,0)<=0:raise ValueError('Invalid camera '+key)
            for key in ('sensor_width','sensor_height','clip_start','clip_end'):
                if key in self.camera_pose and (not math.isfinite(self.camera_pose[key]) or self.camera_pose[key]<=0):raise ValueError('Invalid camera '+key)
            for key in ('shift_x','shift_y'):
                if key in self.camera_pose and not math.isfinite(self.camera_pose[key]):raise ValueError('Invalid camera '+key)
            if self.camera_pose.get('sensor_fit','HORIZONTAL') not in ('AUTO','HORIZONTAL','VERTICAL'):raise ValueError('Invalid camera sensor fit')
        for color in self.colors_linear.values():
            if len(color)!=3 or any(not math.isfinite(v) or not 0<=v<=1 for v in color):raise ValueError('Invalid linear colour')
        if not self.lights:raise ValueError('Add at least one light')
        for light in self.lights:
            xyz(light['position_m'])
            if 'rotation' in light:xyz(light['rotation'])
            if not math.isfinite(light['energy']) or light['energy']<0 or not math.isfinite(light['size_m']) or light['size_m']<=0:raise ValueError('Invalid light energy/size')
            if 'color_linear' in light and (len(light['color_linear'])!=3 or any(not math.isfinite(v) or not 0<=v<=1 for v in light['color_linear'])):raise ValueError('Invalid linear light colour')
            if not re.fullmatch(r'#[0-9a-fA-F]{6}',light['color']):raise ValueError('Invalid light colour')
        return self

    def to_dict(self): return asdict(self.validate())
