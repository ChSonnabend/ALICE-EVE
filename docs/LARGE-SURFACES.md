# Fast ITS and TPC surfaces

Choose **Large surfaces (cached, fast)** in each detector's Geometry detail
control, or click **Use fast ITS/TPC surfaces** in the Blender sidebar for
currently selected ITS/TPC surfaces. In the desktop app, `structural` is the
corresponding detail value. Full-render dialogs offer this mode separately from
full aligned geometry, coarse cells and schematic envelopes.

This is a display approximation intended for interactive composition. It keeps
large physical structures without loading thousands of detailed instanced
parts. It does not change reconstructed tracks, measured clusters or their
calibration. It is inspired by the broad surfaces in the commissioning images,
not an exact reproduction of their old detector meshes or camera.

- ITS uses 192 broad stave panels in seven meshes for the supplied run-560067
  alignment. Panels span aligned sensor bounds and collapse chip/module gaps
  and tiny alignment differences. Layer switches remain available.
- TPC uses reduced native inner-wall, outer-wall and readout-sector meshes:
  257 large elements in 21 meshes. Holes and aligned placements are retained;
  coplanar and small surface details are reduced. Wall/sector component choices
  remain available. Rods, supports, electronics and fine services are omitted.
- Original part/layer choices and source-name filters apply to represented
  components. Fine components absent from this model are disabled in the
  component browser; choose full detail to display them. Browser counts refer
  to placements in the full aligned source. Merged proxies cannot apply an
  inner-placement radius mask; the fast-surface button clears that mask.
- Colours, transparency, material shading, lighting and angular openings use
  the same scene settings as full geometry. The tested user scene keeps both
  90° openings, the TPC outer wall and twelve area lights.
- Track clipping uses cached support planes from **all** full aligned source
  surfaces, before display masks. It does not use proxy panel bounds. Native
  comparisons found zero difference in all 66 clipping planes for both assets.

## Prepare once

With the matching full `.blend` assets and their component sidecars present:

```sh
alice-render prepare-geometry --geometry-root /local/geometry --detectors ITS,TPC --units m
```

Use the source assets' actual units (`m` for this run-560067 bundle). Blender is
needed for preparation. This creates `ITS.blend.structural.json.gz` and
`TPC.blend.structural.json.gz` beside the source assets. Normal fast loading
does not import the full Blender asset or expand its instance tree. Preparation
is separate from ordinary rendering; missing, stale or incompatible caches
stop at preflight with instructions rather than silently loading full geometry.

Portable recipes record each cache's hash alongside source-asset and component
hashes. Copy these caches with the identical geometry bundle to another
machine. Rebuilding after a geometry/component update requires exporting a new
recipe. Cache JSON contains vertices in metres, original component/source-name
bindings and aligned clipping planes; it contains no local machine paths.

## Measured checks on this Mac

The geometry-only comparison loaded ITS/TPC full surfaces and computed their
clipping bounds in about **2.92 seconds**. Cached large surfaces took about
**0.047 seconds** after source hash checks were warm. A separate fresh Blender
process measured about **0.12 seconds** for cached geometry loading, excluding
Blender startup and event parsing. These are local timings, not cross-hardware
performance guarantees.

The final real CTF event-6 preview used 640 × 360 pixels, 64 samples and CPU
rendering, completing in about **17.5 seconds**. It displays 11 fitted references
and 919 cluster associations with the existing ambiguity filter. Native QA
also checks layer/wall switching, source-name exclusions, outward ITS normals,
the registered editor switch/export, cache relocation/hash checks, and a
synthetic invalid Blender container proving the fast path never parses the
source `.blend`. No event data or alignment assets are included in Git.
