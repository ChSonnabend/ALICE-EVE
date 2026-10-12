# TPC pad/time profiles

Appearance and the Blender sidebar offer **sphere**, **ellipse**, and
**gaussian** for TPC clusters. Other detectors retain their existing glyphs.
`TPC profile sigma scale` magnifies the profile; `display thickness` gives the
otherwise two-dimensional pad/time ellipse a thin third axis. This thickness
is a display parameter, not a measured radial uncertainty.

The ellipse uses native O2 ClusterNative pad and time RMS widths. The exporter
propagates them through a central-difference Jacobian (step 0.25 native units) of
the same per-TF correction map and track/PV time hypothesis used for the cluster
position, then applies the sector-to-global rotation. Native pad-time covariance
is unavailable; the two native coordinates are treated as uncorrelated. SVD of
the two global one-sigma vectors preserves their covariance even when the
calibration Jacobian makes them nonorthogonal.

The Gaussian option is a **display approximation**, using six translucent
ellipsoidal shells at 0.5–3 sigma weighted by exp(-r²/2). It is not a reconstructed
charge density, a volumetric Gaussian fit, or centroid-position uncertainty.
Profiled glyphs use their measured sizes; the fixed/special cluster radius does
not replace those widths. Color and track-linked highlighting still apply.

Existing exports and standard AO2D do not contain these widths. Missing, zero,
or saturated widths retain spherical glyphs; `cluster_legend` in metadata records
`profiled_clusters` and `missing_tpc_profiles`. Re-export TF/CTF with the updated
native exporter to obtain measured profiles. No widths are fabricated for old
data. The example profile renders use an explicitly synthetic validation event.

Interchange extension (global coordinates in cm):

```json
{"tpc_profile":{"sigma_pad":1.2,"sigma_time_bins":0.8,
 "sigma_vectors_cm":[[0,0.5,0],[0,0,0.2]],
 "basis":"Measured widths and calibrated Jacobian provenance"}}
```
