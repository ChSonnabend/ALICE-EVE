# Interchange schema v1

For large exports, write one complete event per line in `events.jsonl` or gzip-compressed `events.jsonl.gz`. Arrays of events and `{"events": [...]}` are also accepted. The catalogue reads one complete event at a time and stores compressed payloads separately; the GUI loads only the catalogue metadata.

```json
{
  "schema_version": 1,
  "units": "cm",
  "id": "560067:2619419:primary-vertex-0",
  "kind": "collision",
  "run": 560067,
  "timeframe": 2619419,
  "vertex": [0.0, 0.0, 1.2],
  "tracks": [
    {
      "id": "ITS-TPC:123",
      "detectors": ["ITS", "TPC"],
      "points": [[0.0, 0.0, 1.2], [20.0, 5.0, 10.0]],
      "kinematics": {"eta": 0.2, "phi": 0.4, "p": 2.0, "pt": 1.96}
    }
  ],
  "clusters": [
    {"id": "TPC:456", "detector": "TPC", "position": [100.0, 20.0, 80.0]}
  ]
}
```

`kind` is `collision`, `timeframe`, `rof` or `synthetic`. Include all reconstructed primary vertices, including empty ones; put genuinely unassigned objects in separately labelled timeframe/ROF records rather than assigning them to an arbitrary vertex. Keep run/TF/PV identifiers stable. Track source detector sets distinguish matched tracks from standalone tracks.

Track `kinematics` may contain `eta`, `tan_lambda`, `phi`, `p`, `pt`, `dca`. Missing fields remain unavailable. `eta` and `tan_lambda` may be derived from one another; momentum is never derived from displayed polyline curvature. DCA requires event `vertex` and track `dca_basis`, specifying the propagation and distance convention. Do not mix signed transverse DCA and 3D distance under the same convention.

For a track or cluster, `classification` can be `primary`, `secondary`, `unknown`; known classifications need `classification_basis`. State whether this is MC truth or a documented reconstruction rule. Real data without MC labels does not supply truth classifications.

Cluster `kinematics` require `kinematics_basis` describing the measurement or associated track. For track association also include `track_id`; ambiguity needs an explicit rule or unavailable values. XYZ comes directly from the cluster position. Detector IDs must be explicit; a detector cannot be inferred reliably from the radius of a composite-source cluster.

The exporter must document its cluster-to-event association window, time-overlap ambiguities, unassigned clusters, propagation failures, calibration timestamp and geometry alignment. Carry these as additional event metadata and `warnings`; the renderer preserves them.

## O2 profile completion manifest

An ingestion adapter writes `events.jsonl` (or `events.jsonl.gz`) and `manifest.json` in its requested output directory:

```json
{
  "schema_version": 1,
  "complete": true,
  "event_grouping": "primary_vertex",
  "events_file": "events.jsonl.gz",
  "event_count": 123,
  "input_fingerprint": "from alice_renderer.catalogue.fingerprint(input_path)",
  "o2_version": "installed-version-or-commit",
  "run": 560067,
  "timeframes_processed": 101,
  "primary_vertices_seen": 123,
  "primary_vertices_exported": 123,
  "enumeration_inventory": "pv-inventory.jsonl",
  "inventory_sha256": "SHA-256 of the independent inventory",
  "calibration_timestamp": "run-specific",
  "geometry": "aligned-geometry-identifier"
}
```

Write the manifest atomically only after successful, complete export. When `enumeration_inventory` is present, the renderer verifies `pv-inventory.jsonl` and its `pv-inventory.jsonl.complete.json` end-of-stream marker. It checks the input TF count, raw-TF identities where available, every PV index and position, duplicate identifiers, and the manifest counts/hash. Collision records must then also include integer `orbit` and `primary_vertex` fields. Empty reconstructed vertices need empty collision records; empty timeframes need inventory records with zero vertices.

`native/pv_inventory.cxx` generates the independent inventory from O2's actual primary-vertex collection without display selection. `alice_renderer.enumeration.reconcile_export` performs the comparison using temporary SQLite storage. Enumeration checks do not certify calibration or track/cluster association. Legacy external profiles without an inventory retain exporter-asserted completeness. The shipped Virgo adapter always supplies an independent inventory and validates both end-of-stream markers before publishing its manifest.


## Native export details

`data_detectors` records detector payload availability, including timing/energy detectors with no spatial object for that collision. Object detector associations remain explicit. A payload may exist while that event has no selected track/cluster to render.

A track `id` is its accepted GID without transient flags; `input_gid` preserves the original primary-vertex reference before source aliases. `source`, `time_us`, fitted kinematics, `dca_status`, signed DCA components and propagation basis are retained. Tracks with fewer than two propagated points remain in `unrendered_tracks` with fitted kinematics and a reason. They do not become fabricated display curves.

Clusters carry `coordinate_basis` and `association_basis`. Shared clusters can have multiple association records. PHOS/EMCAL objects use `measurement_kind: calorimeter_cell`, with energy and trigger time; TRD uses `calibrated_tracklet`. Their displayed coordinates do not imply a fitted momentum. Associated-track colouring carries `track_id` and `kinematics_basis`.

`timeframe-objects.jsonl.gz` is a separate archival sidecar with kind `timeframe_objects`, not a collision input to the renderer. It retains unassigned reference IDs, all detector spatial objects, native TPC sector/row/pad/time/charge measurements, timing channels and ZDC energies. Native TPC measurements have no claimed global Z without a collision t0. Missing truth classifications remain unknown.

The manifest can carry `geometry_assets`, `geometry_units`, `geometry_reconstruction_sha256`, `aligned_geometry` and `unassigned_objects`. These refer to the captured run-aligned manager and detector-specific assets; the GUI loads asset paths and units automatically. The application uses centimetres for event positions and converts them to metres for Blender. Geometry and data selection are independent.

Nonfinite converted positions are retained as diagnostics, never accepted as drawable coordinates. Native collision records use `unrendered_clusters`; sidecar spatial records retain nullable position components and `coordinate_status`. The per-TF invalid count is copied into collision metadata and warnings. This distinguishes a failed coordinate conversion from a detector being absent.

## Matching and event-local emphasis

Known O2 `source` labels establish matching for the fitted record: composite sources such as `ITS-TPC` are matched; standalone sources such as `TPC` are standalone. The loader adds boolean `matching` and `matching_basis`; explicitly linked clusters inherit these through `track_id`. Exporters may also supply these fields directly, with a boolean and a nonempty provenance basis. Unknown sources remain unknown, and detector sets alone never establish a match. Standalone classification does not exclude component membership in a different composite record.

Scene `highlight_track_ids` must contain exact canonical track IDs (without transient flags for native O2 exports). The associated cluster emphasis requires an explicit `track_id`; spatial proximity is insufficient. IDs absent from a new event are reported in render metadata. `detector_modes` overrides the global `mode` per detector; older configurations without overrides keep their global mode.
