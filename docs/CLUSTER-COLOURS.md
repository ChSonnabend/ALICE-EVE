# Cluster measurement colours

The desktop Cluster colouring menu and Blender scene editor support `sigma_pad`, `sigma_time`, `qTot`, `qMax`, `qTot/qMax`, `error_y`, `error_z`, `residual_y`, `residual_z`, `residual_y/error_y`, and `residual_z/error_z`. These use the existing palette, automatic/manual range, and missing-value colour controls. Unavailable quantities are disabled in the desktop; partially missing values use the missing-value colour. Nonfinite values and ratios with nonpositive denominators are unavailable.

Canonical clusters can supply this mapping (values below are illustrative):

```json
"measurements": {
  "sigma_pad": 0.8,
  "sigma_time_bins": 1.2,
  "q_tot": 120,
  "q_max": 30,
  "error_y_cm": 0.1,
  "error_z_cm": 0.2,
  "residual_y_cm": -0.15,
  "residual_z_cm": 0.3
}
```

Sigma values also resolve from `tpc_profile`; numeric `features` and top-level cluster fields are accepted. `qTot`, `qMax`, `sigma_time`, `error_y`, `error_z`, `residual_y`, and `residual_z` are accepted aliases. Errors and residuals must use the same local tracking frame and centimetres. Residuals are signed **cluster minus associated fitted track** at the cluster measurement surface. Shared clusters require association-specific records. Producers should retain the error-model, coordinate-frame, fit and residual convention as provenance in the cluster record.

The ratios are calculated from the underlying values. Residual/error divides by cluster centroid uncertainty alone: it is not a combined track-plus-cluster covariance pull. RMS charge widths are not centroid uncertainties and are never used as their substitute. No residual is inferred from the rendered track polyline.

New O2 collision exports retain native TPC sigma pad/time and qTot/qMax. Previously exported data needs re-exporting to gain missing values. The current O2 display-helper exporter does not produce reconstruction cluster errors or fitted-track residuals: these modes require an upstream reconstruction/QA export containing the explicit measurements above. AO2D track-only inputs cannot supply these cluster measurements.

After adding fields to an existing dataset, rebuild its catalogue to refresh the available colour quantities.
