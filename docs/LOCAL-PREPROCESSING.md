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

## Reconstructed detector ROOT files and partial datasets

The desktop does not open an arbitrary ROOT-product directory directly. The
`reconstructed` command converts it to the event format the desktop accepts.
It reads existing fitted tracks and measured clusters/cells, and can rerun
primary vertexing plus track-to-vertex association. It does **not** automatically
rerun detector tracking, cross-detector matching, clusterization, or recover
missing measurements. Use TF/CTF reconstruction when those products are absent.

First inspect a folder; this needs only Python, not O2:

```sh
python3 tools/preprocess_local.py inspect-reco --input /path/reconstructed
```

This reports conventional filenames and missing vertex/timing products. It does
not certify file contents. Then copy `profiles/example-reconstructed.json`,
supply run/timing/conditions and exporter/inventory paths, and explicitly select
`track_sources` and `cluster_sources`. Use `none` for an empty selection.
The example selects ITS only; it is not an all-detector configuration.
Build the exporters with the earlier `build` command if needed.

In O2PDPSuite, prepare a graph without running reconstruction:

```sh
python3 tools/preprocess_local.py reconstructed \
  --input /path/reconstructed --config /path/reco.json \
  --vertices reuse --work /path/new-check
```

Inspect `exporting/input-requirements.json` for **the exact files requested by
your installed O2 readers**. Missing dependencies stop preparation with their
filenames and reader names. To run, repeat with a fresh work directory and
`--execute`. If the primary vertices or their association branches are missing, use:

```sh
python3 tools/preprocess_local.py reconstructed \
  --input /path/reconstructed --config /path/reco.json \
  --vertices rebuild --work /path/new-revertex-job --execute
```

Set `vertexing_sources` explicitly (for example `ITS`), and optionally
`vertex_matching_sources`. This runs O2 primary vertexing/association first,
then exports using the new vertex file. Rebuilt collisions can differ from the
original production: preserve its vertex files when exact grouping matters.
TPC-only tracks are not a supported primary-vertexing source in the installed
workflow; use suitable ITS-based fits or provide existing vertices/associations.
Revertexing does not generate ITS–TPC or other matched-track products.

### Files to retain

All products must belong to the **same run, production, TF sequence and order**.
Keep the complete ROOT files, including ROF records, indices, cluster patterns
and track–cluster references; copying just XYZ or fitted track parameters is
not sufficient for the native readers.

| Data you want | Conventional files / prerequisites |
|---|---|
| Original collision grouping | `o2_primary_vertex.root`, with `PrimaryVertex`, `PVTrackIndices` and `PV2TrackRefs` branches |
| Original TF identities and timestamps | Usually `o2_tfidinfo.root`, containing O2's `tfidinfo` vector; set `timing_file` to its actual path |
| ITS | `o2trac_its.root`, `o2clus_its.root` |
| TPC | `tpctracks.root`, `tpc-native-clusters.root`, and `tpctriggers.root` when requested by the reader |
| ITS–TPC matched tracks | `o2match_itstpc.root`, plus the constituent products requested by the graph |
| MFT | `mfttracks.root`, `mftclusters.root` |
| MCH | `mchtracks.root`, `mchclusters.root` where requested |
| MID | `mid-reco.root` |
| TRD | `trdtracklets.root`, `trdcalibratedtracklets.root`; selected matches use `trdmatches_tpc.root` / `trdmatches_itstpc.root` |
| TOF / HMP | `tofclusters.root` / `hmpidclusters.root`, plus selected match files |
| EMC / PHOS / CPV | `emccells.root` / `phoscells.root` / `cpvclusters.root` |
| FT0 / FV0 / FDD / ZDC | `o2reco_ft0.root` / `o2reco_fv0.root` / `o2reco_fdd.root` / `zdcreco.root` |
| Conditions | Matching O2 version, run, timestamp, TF orbit count, magnetic field, alignment, topology dictionaries and calibration/correction maps |

The installed O2 reader loads vertices and associations from the same
`o2_primary_vertex.root`. Its advertised `vertex-track-matches-infile` option
is unused; this adapter excludes it from required files and checks the combined
file's branches before execution. If your production uses a separate association
file, keep it, but regenerate a combined vertex file with compatible O2 rather
than renaming the separate file.

These are naming hints, not a universal mandatory list. Choose only the sources
you have. O2 may need companion products even for a tracks-only view; the graph
report is authoritative for file dependencies. Conditions are checked from the
actual graph before execution. Additional production-specific parameters can be
supplied in `config_key_values`; their scientific suitability is your run
configuration's responsibility.

For nonstandard filenames, map canonical names to existing paths in the config:

```json
"input_files": {"o2clus_its.root": "my-its-clusters.root"}
```

Files are staged as symlinks in fresh work directories; originals are not renamed.
Vertex rebuilding stages fresh vertex outputs instead of linking the originals.
Execution validates the TF identity vector's count/run, checks CCDB prerequisites,
and reconciles the export against an independent PV inventory before publishing
`export/manifest.json`. Open `export/` in the renderer.

If you have only clusters, retain the originals but obtain fitted tracks and
vertex associations, or reconstruct the original TF/CTF. Missing TPC collision
time prevents a unique calibrated global Z. If you only have AO2D, direct loading
provides fitted tracks, not detector cluster measurements. Neither route invents
missing signals or associations.

**Validation:** reuse and revertex workflow graphs have been generated against
the locally installed O2PDPSuite using test fixtures; dependency checks have
automated coverage. A complete export/revertex run on a real reconstructed-product
folder has not yet been validated. Graph generation is not a physics validation.
