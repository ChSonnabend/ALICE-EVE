# AO2D collision and track import

Open an `AO2D.root` directly with **Load input**. This route reads ROOT tables with
Uproot and needs no local ROOT or O2 installation. It indexes collision headers
and associated fitted-record counts, then generates trajectories only for selected
collisions. Opening the input selects the first collision rather than all records.
An AO2D `DF_*` directory is a data container, not a hardware timeframe. Collision
row indices are local to their dataframe; displayed track IDs include dataframe,
track family and source row. Negative collision indices remain unassociated and
are never assigned to an invented event.

The reader accepts the standard versioned collision/BC, barrel TracksIU (or
Tracks at the PV), TrackExtra, packed track covariance, MFT and forward-track
tables. Contributing barrel detectors follow O2 DetectorMap expressions. Forward
associations follow the stored links/bitmaps and O2 ForwardTrackType. Sparse MFT
covariance is joined by its explicit MFT track index, not row position; identical
repeated rows are accepted and conflicting rows stop with a diagnostic.

## Magnetic-field conditions

The input can be indexed without field conditions, but selected trajectories
cannot be generated until the signed field is supplied. Put a conditions file
beside the input, named `AO2D.root.renderer.json`, or choose a conditions file in
**Setup → AO2D field conditions**. **Explicit AO2D Bz (kG)** is an override for a
known field; the application does not silently assume +5 kG. Missing/invalid
conditions stop before Blender starts. Conditions belong to the dataset, not the
portable scene's camera/style settings; carry the sidecar with the AO2D file.

```json
{"fields":{"572669":{"bz_kG":-5,"basis":"Run-specific nominal GRPMagField from CCDB"}}}
```

In a loaded O2/PyROOT environment, the bundled helper retrieves official public
CCDB HTTP blob alternatives, avoiding an AliEn dependency for public conditions:

```sh
python3 tools/ao2d_field_conditions.py --runs 572669 \
  --cache /local/ccdb-cache --output /local/AO2D.root.renderer.json
```

CLI indexing and portable editing/rendering accept `--aod-conditions /path/file.json`
and `--aod-bz-kG -5`; an adjacent sidecar is automatic. For example:

```sh
alice-render index /local/AO2D.root
alice-render edit-config scene.json --input /local/AO2D.root --event ordinal:68 \
  --geometry-root /local/geometry
alice-render render-config scene.json --input /local/AO2D.root --event ordinal:68 \
  --geometry-root /local/geometry --quality final --resolution-percent 50
```

## Features and scientific meaning

Track colour choices include momentum, transverse momentum, eta, tan(lambda),
phi, positions, matching and a projected DCA for barrel fits. Additional numeric
stored columns appear as `feature:<column>`: TPC signal, fit chi-squared, ITS/TPC
cluster counts, timing, packed covariance sigmas/correlations, detector flags and
other available quantities. Derived `its_nclusters`, `tpc_nclusters`,
`tpc_crossed_rows`, `pid_for_tracking`, `pv_contributor`, `charge`, `dca_xy` and
`dca_z` are also available. Track payloads retain fitted parameters and source
association indices. Sentinel/missing values are omitted rather than coloured as
measurements. Numeric covariance columns retain O2's packed representation;
rho values are packed correlations, not automatically decoded covariance matrices.
Unavailable features fail preflight, and records missing a chosen quantity use the
existing missing-value colour.

Barrel and MFT curves are projections of the stored fitted states in a constant
solenoid Bz, without energy loss, material corrections or a spatial field map.
They start at the fitted reference point; a TPC-only fit does not acquire invented
ITS measurements. MCH/MID paths are **linear forward fit projections** and do not
model dipole transport. Barrel DCA is the transverse helix closest approach to the
AO2D collision PV, with the corresponding longitudinal offset; it is explicitly
labelled as a display projection, not a full O2 propagation-with-material result. Its longitudinal
offset uses the helix arc; O2 short-step propagation can use a chord approximation,
so projected DCA_z values are not asserted to be numerically identical.
PV-contributor flags do not establish physical-primary/secondary classification;
that classification remains unavailable when MC truth is not imported.

AO2D does not contain measured track-attached space-point arrays, so this route
provides **tracks only**, with no fabricated clusters. Raw TF/CTF reconstruction
exports remain the route for calibrated clusters. Barrel, MFT and composite
forward records may describe overlapping physical particles; counts are fitted
source records, not a deduplicated particle count.

Choose geometry aligned to the input run when physical alignment matters. Geometry
is an independent scene asset; opening an AO2D does not claim that an existing
geometry bundle was calibrated for its run.

## Checked example on the original workstation

The supplied Virgo file was copied to `cache/ao2d-example/AO2D.root` and contains
**run 572669**, 90 dataframes and **30,957 collision rows**. Its nominal CCDB field
is −5 kG. Collision ordinal 0 materialized all 5,248 associated fits; ordinal 68
materialized all 10. O2 on Virgo was used to cross-check 100 real barrel states:
origins and pT agreed to numerical precision, eta within 2.4e−7, curvature within
1.8e−10 cm⁻¹, and constant-field propagation over a 5 cm local-X step within
3.3 micrometres. This checks the solenoid projection, not full material/field-map
transport. Qt and Blender checks covered feature colouring and scene export.

`configs/ao2d-example.json` is a local convenience recipe for ordinal 68. It uses
existing **run-560067 geometry as display illustration**, not run-572669 aligned
geometry. Start it with:

```sh
.venv/bin/alice-render edit-config configs/ao2d-example.json --geometry-root geometry/run-560067
```
 This recipe, input, conditions and QA outputs
are private local artifacts and are excluded from Git.
