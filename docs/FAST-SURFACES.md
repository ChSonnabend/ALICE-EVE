# Cached approximate surfaces

`Fast interactive` now prefers `proxy` geometry: pre-baked approximate native surfaces for all 15 detectors in `geometry/run-560067` plus the L3 magnet. It preserves the source alignment, beam apertures and large detector shapes while omitting small repeated hardware and reducing polygon complexity. It does not subsample event tracks or clusters.

The cache is `<asset>.surface.json.gz`. It contains mesh groups, original component tags/source names, original-source clipping bounds, source asset/component hashes and the selected simplification parameters. Loading verifies hashes and units. Visible groups are filtered by component/exclusion choices before being batched into one mesh per detector, or two for the TPC's curved and planar surfaces. The complete setup uses 17 meshes. Openings, colours and opacity remain editable. Inner-placement masks and non-surface display modes keep their existing geometry instead of silently changing their semantics.

All installed caches contain exact 64-azimuth plus two longitudinal clipping planes derived from the full source assets. Track clipping never uses the approximate display meshes. Full geometry remains available through the per-detector detail selector and full-render dialog. `structural` retains its older ITS/TPC-only meaning; `proxy` is the new general cached approximation.

## Review

Each detector/magnet received a dedicated critic and five 1920×1080 candidate renders alongside a full-asset reference, with fixed lighting, camera, colour and opacity. Critics selected the lightest acceptable shape. The five ITS candidates inherited the old sensor-only cache; its critic rejected the missing service silhouette. The selected candidate was completed with decimated native service/cage/support surfaces and passed a separate final validation render. The candidate records remain unchanged as review evidence.

FDD and ZDC's widely separated stations occupy few pixels in their global views, so their review supports global placement and distant silhouettes rather than close-up detail. Some intrinsically simple assets produce identical candidates. Full geometry should be used for detailed mechanical inspection. Approximate surfaces can change perceived transparency because overlapping microscopic surfaces are omitted.

The review directory contains each reference, five candidates, metrics and critic JSON. Candidate timings are isolated renders in a warmed Blender process, not unbiased end-to-end speedup measurements. A separate combined geometry-only editor test verifies cache-only loading; GUI launch, shader compilation, and event-data loading add time.

## Rebuild

Use Blender 4.5+ and the same repository Python module environment used by the renderer. For a detector, generate the five review candidates:

```sh
blender --background --factory-startup --python-exit-code 1 \
  --python tools/review_surface_proxies.py -- \
  --asset geometry/run-560067/TRD.blend --output /path/to/review/TRD
```

After reviewing, install the chosen candidate (the finalizer also restores ITS's broad service/support shells):

```sh
blender --background --factory-startup --python-exit-code 1 \
  --python tools/finalize_surface_proxy.py -- \
  --asset geometry/run-560067/TRD.blend \
  --candidate /path/to/review/TRD/candidate-1.json.gz
blender --background --factory-startup --python-exit-code 1 \
  --python tools/bake_proxy_track_bounds.py -- --geometry-root geometry/run-560067
```

`geometry/run-560067/surface-proxy-selection.json` records the selected candidate per detector and the review scope. These caches apply to the current aligned ALICE2 bundle. ITS3/ALICE3-specific assets require their own bake/review; their existing geometry remains in use.
