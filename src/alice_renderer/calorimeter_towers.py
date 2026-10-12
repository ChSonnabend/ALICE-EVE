"""Signal glyphs anchored at measured global positions, never inferred energies.

Exported cell_geometry gives aligned footprint vectors. Older exports use a
nominal rectangular footprint in the local transverse tangent/Z plane; this
display approximation is counted in metadata. CPV clusters remain clusters.
"""
import math

CALORIMETERS=('EMC','PHS','CPV')
DISPLAY_MODES=('points','signal towers','fixed towers')
# Nominal display footprints, cm (EMCAL tile ~6 cm; PHOS crystal 2.2 cm;
# CPV pad 1.13 x 2.1093 cm). Exported aligned vectors take precedence.
FOOTPRINTS={'EMC':(6.,6.),'PHS':(2.2,2.2),'CPV':(1.13,2.1093)}
DEFAULT_SCALES={'EMC':20.,'PHS':.2,'CPV':.2}

def dot(a,b):return sum(x*y for x,y in zip(a,b))
def cross(a,b):return (a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0])

def validate_cell_geometry(data):
    if not isinstance(data,dict) or not isinstance(data.get('basis'),str) or not data['basis'].strip():raise ValueError('Cell footprint requires an explicit geometry basis')
    vectors=[]
    for key in ('u_cm','v_cm'):
        value=data.get(key)
        if not isinstance(value,(list,tuple)) or len(value)!=3 or any(not isinstance(v,(int,float)) or isinstance(v,bool) or not math.isfinite(v) for v in value):raise ValueError('Invalid cell footprint vector '+key)
        if dot(value,value)<=0:raise ValueError('Cell footprint vectors must be nonzero')
        vectors.append(value)
    normal=cross(*vectors)
    if dot(normal,normal)<1e-12:raise ValueError('Cell footprint vectors must be independent')
    return vectors

def tower(cluster,settings):
    """Return base-centred vertices in metres, or None to retain a point glyph."""
    name=cluster['detector'];mode=settings.get('calorimeter_display',{}).get(name,'points')
    if name not in CALORIMETERS or mode=='points':return None
    from .cluster_colors import value,phos_adc
    field='amplitude' if name=='CPV' or name=='PHS' and (phos_adc(cluster) or value(cluster,'amplitude') is not None) else 'energy'
    signal=value(cluster,field)
    if mode=='fixed towers':height=settings.get('tower_fixed_height_cm',10.)
    elif signal is None:return None
    else:height=signal*settings.get('tower_height_scales',{}).get(name,DEFAULT_SCALES[name])
    if height<=0:return None
    limit=settings.get('tower_max_height_cm',100.);clipped=height>limit;height=min(height,limit)
    position=cluster['position'];geometry=cluster.get('cell_geometry')
    if geometry:
        u,v=validate_cell_geometry(geometry);basis=geometry['basis'];approximate=False
    else:
        radius=math.hypot(*position[:2])
        if radius==0:return None
        width,depth=FOOTPRINTS[name]
        u=(-position[1]/radius*width,position[0]/radius*width,0.)
        v=(0.,0.,depth);approximate=True
        basis='Nominal footprint; transverse tangent/Z plane at measured position (display approximation)'
    normal=cross(u,v);length=math.sqrt(dot(normal,normal));normal=tuple(x/length for x in normal)
    if dot(normal,(position[0],position[1],0.))<0:normal=tuple(-x for x in normal)
    direction=-1 if settings.get('tower_direction','inward')=='inward' else 1
    offset=tuple(direction*height*x for x in normal)
    width_scale=settings.get('tower_width_scale',.95)
    vertices=[]
    for layer in (0,1):
        for a,b in ((-1,-1),(1,-1),(1,1),(-1,1)):
            vertices.append(tuple((position[i]+.5*width_scale*(a*u[i]+b*v[i])+layer*offset[i])*.01 for i in range(3)))
    # Cross(u,v) is the polygon normal; choose winding for either extrusion.
    forward=dot(cross(u,v),offset)>0
    faces=[(3,2,1,0),(4,5,6,7),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7)]
    if not forward:faces=[tuple(reversed(f)) for f in faces]
    return dict(vertices=vertices,faces=faces,detector=name,height_cm=height,signal_field=field,
                signal_unit='fixed display height (cm)' if mode=='fixed towers' else 'GeV' if field=='energy' else 'ADC' if name=='PHS' else 'native amplitude',
                signal=signal,clipped=clipped,approximate=approximate,basis=basis,
                measurement_kind=cluster.get('measurement_kind','cluster'))

def report_entry():
    return dict(towers=0,point_fallbacks=0,approximate_footprints=0,clipped_heights=0,measurement_kinds={})
