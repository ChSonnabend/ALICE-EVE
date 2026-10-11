# Commissioning camera reference reproduction

The best result is **second-batch attempt 5**, reviewed at **6.5/10 qualitative
similarity**, compared with 4/10 for the best first-batch result. It captures the
interior view, leftward barrel, surrounding TPC walls and blue/pink style. It
remains an approximate recreation: the foreground cage is larger/brighter and
the central event pattern differs from `Camera.002_frame_001.png`.

Ten renders were made: five initially, then five more explicitly authorised by
the user. In each batch attempts 1–4 were 960×540 and attempt 5 was 1920×1080.
The critic inspected every image. The final image uses Blender 5.0, Cycles,
Metal, 64 samples and denoising; earlier images used 32 samples. Scene inspection
and native QA did not produce additional render images.

The ninth listed collision was retained throughout: run 560067, event ID
`560067:2619419:212036032:8`, zero-based ordinal 8. Its ITS/TPC selection supplies
190 fitted records and 6,672 clusters, including 46 ITS clusters. These are
source records, not deduplicated physical tracks. No tracks or hits were invented
to fill the reference's central cloud.

| Attempt | First-batch score / 10 | Second-batch score / 10 | Second-batch change |
|---|---:|---:|---|
| 1 | 1 | 4.5 | Side-on camera, directional cut and explicit ITS service exclusions |
| 2 | 2 | 3.5 | Inside-TPC camera, 16 mm lens, complete outer TPC context |
| 3 | 3 | 5 | Ray-identified central drum/inner shield exclusions |
| 4 | 4 | 5.5 | Lights moved inside the drift volume |
| 5 | 3 | **6.5** | Opposite-end camera and front-only inner placement mask |

These are subjective critic ratings, not measured reconstruction accuracy.

## Exact tested settings

[`commissioning-interior.json`](../src/alice_renderer/presets/commissioning-interior.json)
is the portable tested recipe. It includes the actual rendered camera matrix,
complete structural rules and hash-checked alignment assets, with no local
input/event or hardware/quality defaults. Its settings supersede the withdrawn
first-batch preset. Fresh desktop installations use this reviewed second-batch
style. Saved local preferences take priority; **Appearance → Use commissioning
defaults** applies it for the current input/event and local assets. Exact recipe
loading enforces the original asset hashes; the defaults button clones the style
onto the current local alignment bundle. General programmatic `RenderSettings()`
continues to default to tracks only.

| Setting | Value |
|---|---|
| Camera position, ALICE global metres | `[1.7, 0.9, 1.8]` |
| Aim point, global centimetres | `[-0.04729613, -0.03511476, -7.11026287]` |
| Projection / sensor / lens / roll | Perspective / 36 mm horizontal sensor / 16 mm / +13.3° |
| Orbit controls, Y axis | Azimuth 47.735188°, elevation 19.600817°, distance 268.389 cm |
| Data | ITS/TPC, both tracks and clusters, solid colouring, source-detector track clipping |
| Geometry | Full aligned ITS/TPC surfaces, opacity 1; L3 off |
| Openings | ITS 180° toward 27.897271° in XY; TPC 0° |
| Geometry / cluster / track / background | `#0700b5` / `#d58bdd` / `#60746d` / `#000012` |
| Track diameter / cluster radius | 0.05 cm / 0.40 cm |
| Display / exposure | Standard / 0 stops |
| Track / cluster emission | 0.35 / 0.80 |
| Material | Smooth, roughness 0.58, metallic 0 |
| World strength | 0.01 |
| Key area light | `[1.3,0.7,1.4]` m, 25 W, size 2 m, white, aimed at the target |
| Fill area light | `[-1.2,-0.6,-1.1]` m, 12 W, size 2 m, white, aimed at the target |
| Final output | 25% of 8K = 1920×1080, 64 samples, denoise, Metal |

The saved camera matrix is authoritative; manually rounded orbit values are
only convenient editing controls. Changing quality or hardware is independent
of scene settings.

ITS excluded name patterns:
`ITSServices*`, `Cage*`, `BPSupport*`, `OBCone*`, `ConeA*`.

TPC excluded name patterns:
`TPC_IFC*`, `TPC_IFEPOX*`, `TPC_HSM*`, `TPC_HSS*`, `TPC_HV-*`, `TPC_CDR-*`, `TPC_ICV*`.

The TPC inner-placement mask uses radius 1 m, front-only toward the opening
direction, for `TPC_mrod*`, `TPC_rod*`, `TPC_ring*`, `TPC_bcon*`. It removes 450
front inner placements while retaining outer structures. Native QA verified
1,204 outer placements remained enabled. Whole name-group deletion would have
removed both inner and outer placements, since they share instancers. All rules
and matched names/counts are recorded in render metadata. Complete original
aligned bounds still govern track clipping. The input and asset files are not
modified.

## Local result and reproduction

On the working installation, the final files are `renders/reference-camera002/`:
`event-9.png`, `scene.json`, `assets.local.json` and `metadata.json`. The favourite
**Commissioning interior — improved reference view** points to this scene and
its ninth-listed collision. Restart the desktop app, then load `scene.json`,
load the event input, and select the event ID above. The favourite can also
reload the scene and original event directly.

From the project root, this single command reproduces the tested setup:

```sh
.venv/bin/alice-render render-config renders/reference-camera002/scene.json --input cache/efa037ab480ab19c5d5bc02b/event-00000008.json.gz --event 560067:2619419:212036032:8 --assets renders/reference-camera002/assets.local.json --backend AUTO --resolution-percent 25 --samples 64 --output renders/reference-camera002/reproductions
```

On another machine, copy the portable JSON and identical geometry bundle, then
supply its local input/event and geometry root or asset mapping. AUTO checks
available backends. Match Blender version and quality for the closest pixels.

## What corrected the search

The first batch guessed an almost axial view from the combined barrel
silhouette, instead of fitting distinct rails and end-wheel rings. Its 32–36 mm
lens range was also too narrow. Opaque intact services, then globally
transparent nested shells, both obscured the event. The fixed −Y opening
unnecessarily constrained camera placement.

PNG metadata names `/home/fschlepp/blender/ALICE_CUT.blend`, camera `Camera.002`,
rendered on 2025-10-08. The old example README links a public CERNBox base world.
That 2,111,087,529-byte file was downloaded into the ignored local cache and
inspected with script execution disabled, without rendering. It contains only
`Camera`, not `Camera.002`, and must not be claimed as the exact reference scene.
The old workflow maps event `(X,Y,Z)` to Blender `(X,Z,Y)` in centimetres; our
assets use ALICE global XYZ in metres. Its raw camera matrix is therefore not
interchangeable with the current framework.

The base scene's ITS `IB`/`OB` extents differ from our full ITS structural
selection: our service cones and cage panels extend beyond 250 cm along the
beam. Explicit component selection made the barrel readable. Straight-ray
inspection then identified `TPC_CDR-78` at the primary vertex and `TPC_ICVM-71`
blocking clusters. Removing those named display components clarified the view.
Lights inside the TPC avoided shielding by its outer structures. The final
opposite-end camera placed foreground structures on the correct side, and a
radial mask preserved outer context while opening the inner cage.

## Remaining improvement plan

1. Fit camera/component framing against separately identified 3D/2D landmarks;
   use the actual `Camera.002` scene if it becomes available.
2. Add independent shading/opacity for inner and outer structural groups; the
   current foreground cage remains too prominent.
3. Offer smoother cluster glyphs and explicit foreground size control; nearby
   clusters remain too large/faceted. Keep physical radii as the standard.
4. Turn the read-only ray diagnostics used here into a user-facing visibility
   check for the primary vertex and sampled selected clusters.

Directional openings, recorded component masks, selective inner-instance masks,
portable colour/lens/glow controls and the improved default are implemented.
The remaining plan items above are not completed features.
