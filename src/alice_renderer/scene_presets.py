"""Small, portable scene adjustments shared by recipes and the editor."""
import math

SURROUND_LIGHT_PREFIX = 'ALICE surround light '


def tpc_sectors_and_inner_wall(metadata):
    """Keep native readout-sector and inner-wall surfaces; veto all other parts."""
    if not metadata or metadata.get('detector') != 'TPC':
        raise ValueError('Select a TPC aligned asset with component metadata')
    keep = set()
    for group in metadata['groups'].values():
        for tags in group['classes']:
            if any(tag in ('structures/readout', 'structures/inner_wall') for tag in tags):
                keep.update(tag for tag in tags if tag.startswith('parts/'))
    if not keep:
        raise ValueError('TPC asset has no labelled sectors or inner wall')
    return {key: key in keep for key in metadata['components'] if key.startswith('parts/')}


def surround_lights(target_m=(0., 0., 0.)):
    """Eight broad side lights and two end lights, aimed at the detector centre."""
    lights = []
    for z in (-3., 3.):
        for degrees in (45, 135, 225, 315):
            angle = math.radians(degrees)
            offset = (6.*math.cos(angle), 6.*math.sin(angle), z)
            lights.append(dict(position_m=[a+b for a,b in zip(target_m, offset)],
                               energy=200., size_m=4., color='#ffffff'))
    for z in (-8., 8.):
        lights.append(dict(position_m=[target_m[0], target_m[1], target_m[2]+z],
                           energy=150., size_m=4., color='#ffffff'))
    for index, light in enumerate(lights, 1):
        light['name'] = SURROUND_LIGHT_PREFIX + str(index)
    return lights
