"""Measured pad/time RMS profiles; independent errors, locally linear transform."""
import math
import numpy as np


def profile_axes(cluster, thickness_cm):
    profile=cluster.get('tpc_profile')
    if cluster.get('detector')!='TPC' or profile is None:return None
    if not profile.get('basis'):raise ValueError('TPC profile requires its transformation basis')
    values=[profile.get('sigma_pad'),profile.get('sigma_time_bins')]
    if any(not isinstance(v,(int,float)) or not math.isfinite(v) or v<0 for v in values):
        raise ValueError('TPC sigma values must be finite nonnegative RMS widths')
    vectors=np.asarray(profile.get('sigma_vectors_cm'),dtype=float)
    if vectors.shape!=(2,3) or not np.isfinite(vectors).all():raise ValueError('TPC profile needs two finite global one-sigma vectors')
    # Zero/saturated widths are unavailable, not a point-like measured profile.
    if min(values)<=0:return None
    u,s,_=np.linalg.svd(vectors.T,full_matrices=True)
    if min(s)<=0:return None
    if np.linalg.det(u)<0:u[:,2]*=-1
    return [float(s[0]),float(s[1]),thickness_cm],u.tolist()
