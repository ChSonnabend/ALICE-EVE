# Local O2 preprocessing

Run these commands from the repository in an activated **O2PDPSuite** environment.
The scripts inherit its AliEn credentials and CCDB configuration; they do not
save the token-bearing environment. From another terminal on Linux, use
`python tools/run_in_o2.py --pid PID -- python3 tools/preprocess_local.py ...`.
The helper searches the named shell and its children for the loaded O2 environment.

| Input | Read directly? | What is needed |
|---|---|---|
| Exported event JSON/JSONL | Yes | Blender for rendering; no O2 |
| AO2D | Yes, for fitted tracks | Run-specific signed magnetic field; no individual TPC cluster pad/time widths in standard AO2D |
| Raw TF | No | Matching O2 decoding, reconstruction, calibration and PV associations |
| CTF | No | Matching dictionaries, O2 decoding/reconstruction, calibration and PV associations |

CTF compression does not turn a timeframe into a collision catalogue. A TPC
cluster's native time is not a unique global Z without a track/collision time
hypothesis. Reconstruction settings must match the run and production campaign;
the run-560067 example is not a universal configuration.

## Build the exporters

```sh
python3 tools/preprocess_local.py build \
  --o2-source /path/to/matching/O2/source --work /local/new-exporter-build
```

This builds an isolated derivative of O2 EventVisualisation and an independent
PV inventory workflow. It does not edit the O2 source tree. The cluster exporter
now includes native pad/time RMS widths and calibrated global one-sigma vectors.

## Reconstruct TF or CTF

Copy `profiles/example-local-run560067.json` and fill in the matching run,
conditions, detector list, TF count, exporter and inventory executable paths.
The explicit expected TF count is checked against the independent inventory.

```sh
python3 tools/preprocess_local.py reconstruct --format tf \
  --input /local/input.tf --config /local/run.json --work /local/tf-job --execute
python3 tools/preprocess_local.py reconstruct --format ctf \
  --input /local/input.root --config /local/run.json --work /local/ctf-job --execute
```

Each work directory must be new. Omit `--execute` to generate and inspect the
DPL workflow graph only. Execution runs the existing CCDB condition preflight,
then reconstruction, enumeration reconciliation and lossless compression. Only
successful reconciliation publishes `export/manifest.json`. Open `export/` in
the renderer. Logs and `aligned-geometry.root` stay with the export. Existing
Blender assets may be used only if appropriate for that alignment; geometry
conversion helpers are documented in O2-INTEGRATION.md.

The previous raw TF/CTF validation was run 560067. The new native exporter and
inventory compile against the local O2 build; a fresh full TF/CTF reconstruction
with the new width fields has not yet been validated. Do not interpret successful
compilation or workflow generation as a calibration validation for another run.

## AO2D

```sh
python3 tools/preprocess_local.py ao2d --input /local/AO2D.root \
  --runs 560067 --cache /local/ccdb-cache
```

This creates the adjacent field-conditions sidecar; it does not reconstruct raw
clusters or rewrite AO2D. Open AO2D directly in the renderer. Use the actual run
numbers in the file, not the example number. See AO2D.md for projection limits.
