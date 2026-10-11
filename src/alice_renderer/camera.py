"""Camera orbit positions in ALICE coordinates; Y is vertical, Z is the beam."""
import math

def upgrade_local_camera(values):
    """Upgrade untouched old UI defaults; preserve explicitly positioned views."""
    values=dict(values)
    if 'camera_orbit_axis' not in values:
        untouched=(not values.get('camera_pose') and values.get('azimuth',-55)==-55
                   and values.get('elevation',22)==22 and values.get('roll',0)==0)
        values['camera_orbit_axis']='Y' if untouched else 'Z'
        if untouched:values['elevation']=0.
    return values

def orbit_position(azimuth,elevation,distance,target,axis='Y'):
    az,el=math.radians(azimuth),math.radians(elevation)
    a=distance*math.cos(el)*math.cos(az)
    b=distance*math.cos(el)*math.sin(az)
    h=distance*math.sin(el)
    offset=(a,h,b) if axis=='Y' else (a,b,h)
    return [t+v for t,v in zip(target,offset)]
