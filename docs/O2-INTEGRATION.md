# O2 integration

TF/CTF payloads require O2 decoding and reconstruction before collisions can be listed. The old framework also runs O2 and ROOT before Blender. This framework runs O2 on Virgo and keeps the desktop application and rendering independent of that installation.

## Selected environment

The validated workstation uses a private profile for the user-provided Virgo allocation and installed O2PDPSuite environment. Machine-specific profiles are excluded from Git. Configure a new instance by copying `profiles/example-remote-runtime.json` to `profiles/remote-runtime.local.json`, and `profiles/example-run560067.json` to `profiles/run-reconstruction.local.json`. Fill in host, existing positive allocation ID, container/work paths and installed exporter/inventory locations. Select `profiles/example-remote-ingest.json` in Setup. Its `{python}`, `{project}` and `{profile_dir}` placeholders resolve on the current instance.

The remote isolated work directory must already contain the environment snapshot used by `tools/o2_remote_worker.py`, the installed native exporters, and the separate MIT ROOT-to-Blender converter at `src/reference-root2blend`. Build these against the exact selected O2 suite using the preparation/build tools; the examples are configuration templates, not automatic O2/container installers. Use `ALICE_GEOMETRY_CONVERTER` for the local converter when geometry assets must be built. Existing exported data and assets render without these dependencies.

Commands use separate positively numbered steps. Cancellation checks the job and unique request identity and never targets step 0, batch or extern. No new allocation is submitted. The example reconstruction is run 560067, Pb–Pb, 32 orbits per TF. The loaded TPC correction-map mean is in IDC/TPC scaler units; its checked configuration uses scaler type 2 and derivative correction mode 1. Other runs/campaigns need matching configuration and O2 versions.

## Desktop and command-line use

Setup selects the explicitly configured ingestion profile. Opening a raw TF or ROOT CTF invokes `tools/virgo_ingest.py` through that profile:

1. Inspect every TF header and detector payload mask. Check distinct TF identities, matching run configuration, local Blender and disk space.
2. Stage the input under its SHA-256, generate a private pipeline and validate consistent DPL flow-control settings.
3. Check native executables, the magnetic-field map, remote disk and every CCDB condition advertised by the pipeline before reconstruction. Public CCDB downloads are cached atomically with ROOT object and validity checks. Missing conditions produce a diagnostic.
4. Reconstruct using the raw-TF or CTF reader and available detector sources. Export every primary vertex, including empty ones, without display time/track/PV/file quotas.
5. Compress and retrieve events, whole-TF objects, an independent vertex inventory and the exact aligned geometry manager captured during reconstruction.
6. Reconcile every TF/PV identity and vertex position against the inventory and both end-of-stream markers. Convert aligned assets; reuse existing assets only if every surface JSON hash matches.
7. Publish a completion manifest atomically. Build a fully validated catalogue with a separate compressed payload per event.

```sh
.venv/bin/alice-render index data/low_density/reconstructed-ctf-run560067.root --profile profiles/example-remote-ingest.json
.venv/bin/alice-render index data/validated/run560067-raw-v9
```

Opening an existing validated export needs neither O2 nor an active Virgo job. Input and profile/configuration fingerprints invalidate processed caches. Preflight and reconstruction logs remain in the cache. The profile uses argument arrays, not shell strings. A failed prerequisite stops before expensive reconstruction.

## Native exporter and independent checks

`tools/prepare_o2_exporter.py` creates an isolated derivative of the exact installed O2 EventVisualisation source; its upstream GPL license is retained. `tools/build_o2_exporter.py` compiles against installed suite headers and public FairMQ definitions. `native/canonical_export.h`, `native/export_run.inc` and `native/timeframe_export.h` supply collision and whole-TF output. The original checkout is unchanged.

Tracks preserve source GID, original PV-reference GID, fitted kinematics and sampled trajectories. Failed sampling remains in `unrendered_tracks`. Barrel DCA is `sqrt(DCAxy²+DCAz²)` in cm, using O2 propagation with nominal Bz and no material correction; status and signed components are retained. Unsupported forward DCA and real-data MC classifications remain unavailable.

Associated TPC clusters use the same per-TF `TPCCORRMAP` POD transform supplied to GPU reconstruction, with track/PV time and sector-to-global rotation. ITS/MFT use topology dictionaries and aligned transforms; TRD uses calibrated tracklets; TOF, MCH, MID and HMP use their O2 converters. PHOS/EMCAL cells are labelled as cells. CPV whole-TF positions use the aligned module transform of local `(x,0,z)`; this is the module-plane convention.

The sidecar retains all spatial detector objects, every native TPC pad/time/charge measurement, unassigned PV references, FT0/FV0/FDD timing channels and ZDC energies. It is separate from collision selection: those objects are not copied into every vertex. Unassociated TPC global Z is unavailable without a collision-time hypothesis. Timing channels currently have no collision association, and the sidecar is an archive rather than a collision catalogue. A separate `timeframe-events.jsonl.gz` provides selectable, explicitly labelled whole-TF spatial detector views; native TPC measurements and timing channels have no invented global positions.

`native/pv_inventory.cxx` independently observes reconstructed vertices and references without display selection. `alice_renderer.enumeration.reconcile_export` checks all identities and coordinates using disk-backed SQLite. `tools/audit_catalogue.py` also checks original track references and cluster associations in every canonical collision. Enumeration QA establishes completeness relative to that reconstruction, not equality between raw and CTF reconstructions.

## Aligned detector geometry

`tools/export_aligned_geometry.py` exports full global parent transforms from the captured TGeo manager. Its material-boundary traversal retains the first solid surface in each branch, avoiding redundant gas/air volumes. These are physical detector exteriors rather than schematic envelopes or every nested material constituent.

`tools/build_aligned_assets.py` builds one compact, instanced `.blend` per detector and a separate L3 asset. It verifies every instance count, translation, rotation and reflection, rejects empty/unsupported shapes, and records source/generator hashes. Assets use ALICE global XYZ in metres; collision coordinates use centimetres. All 16 assets for run 560067 match the surface exports from the actual reconstructed geometry manager.

## Input and validation limits

The supplied large TPC-only CTF has 101 entries with the **same** TF identity. Those are not 101 distinct collision groups. The profile rejects repeated identities; it also rejects inputs without ITS because this installed primary-vertex workflow skips them. A full-detector CTF generated from the real raw TF was used for CTF validation. Detector-only inputs need an appropriate vertexing strategy or externally reconstructed vertices; the application reports that prerequisite rather than inventing events.

Real validation covers one full TF per input route. The workflow and inventory accept multiple TFs without quotas, but real multi-TF and cross-run campaigns remain unvalidated. Preflight condition checks use the first TF; O2 requests conditions as later TFs advance. The geometry manager is captured at the first TF, so changing alignment validity across a file needs separate snapshots before claiming per-event alignment.

Invalid converted spatial measurements remain in the sidecar with nullable components and a coordinate-status flag. Associated invalid clusters remain in `unrendered_clusters`; a TF quality count and warning accompany its collisions. They are never replaced with fabricated coordinates or used to abort otherwise valid events.
