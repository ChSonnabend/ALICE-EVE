"""Measured cluster scalars. Widths are never substituted for centroid errors."""
import math

CLUSTER_COLOR_FIELDS = (
    'sigma_pad', 'sigma_time', 'qTot', 'qMax', 'qTot/qMax',
    'error_y', 'error_z', 'residual_y', 'residual_z',
    'residual_y/error_y', 'residual_z/error_z',
)
DESCRIPTIONS = {
    'sigma_pad': 'TPC charge RMS width in pads; not centroid uncertainty',
    'sigma_time': 'TPC charge RMS width in time bins; not centroid uncertainty',
    'qTot': 'Integrated cluster charge in native ADC units',
    'qMax': 'Peak cluster charge in native ADC units',
    'qTot/qMax': 'Integrated / peak charge; requires positive qMax',
    'error_y': 'Cluster centroid uncertainty in local tracking y, cm; not charge width',
    'error_z': 'Cluster centroid uncertainty in local tracking z, cm; not charge width',
    'residual_y': 'Signed cluster minus associated fitted track in local tracking y, cm',
    'residual_z': 'Signed cluster minus associated fitted track in local tracking z, cm',
    'residual_y/error_y': 'Local y residual / cluster uncertainty; excludes track covariance',
    'residual_z/error_z': 'Local z residual / cluster uncertainty; excludes track covariance',
}
ALIASES = {'sigma_pad': ('sigma_pad',), 'sigma_time': ('sigma_time_bins','sigma_time'),
           'qTot': ('q_tot','qTot'), 'qMax': ('q_max','qMax'),
           'error_y': ('error_y_cm','error_y'), 'error_z': ('error_z_cm','error_z'),
           'residual_y': ('residual_y_cm','residual_y'), 'residual_z': ('residual_z_cm','residual_z')}


def value(cluster, mode):
    if 'detector' not in cluster:return None
    if '/' in mode:
        numerator,denominator=mode.split('/')
        a,b=value(cluster,numerator),value(cluster,denominator)
        if a is None or b is None or b<=0:return None
        result=a/b
        return result if math.isfinite(result) else None
    for source in (cluster.get('measurements',{}),cluster.get('features',{}),cluster.get('tpc_profile',{}),cluster):
        for key in ALIASES.get(mode,()):
            v=source.get(key)
            if isinstance(v,(int,float)) and not isinstance(v,bool) and math.isfinite(v):
                if not mode.startswith('residual_') and v<0:continue
                return float(v)
    return None
