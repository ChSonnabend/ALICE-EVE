# Commissioning camera reference trial

Five renders were compared with `Camera.002_frame_001.png`, each independently
reviewed by a critic. Attempts 1–4 used 960 × 540; attempt 5 used 1920 × 1080.
All used Blender 5.0, Cycles, Metal, 32 samples and denoising. No sixth render
was made. Scene inspection and tests did not produce additional render images.

The ninth listed collision in the run-560067 raw export was used: event ID
`560067:2619419:212036032:8`, zero-based ordinal 8. Ordinal 9 is a different,
much denser collision. ITS/TPC selection supplies 190 fitted records and 6,672
clusters; these are source records, not deduplicated physical tracks.

| Attempt | Critic similarity / 10 | Main finding |
|---|---:|---|
| 1 | 1 | Camera blocked by actual ITS services; geometry too bright. |
| 2 | 2 | Vertex ray clear, but services hide almost all TPC clusters. |
| 3 | 3 | Transparent nested surfaces remain obstructive and ghosted. |
| 4 | **4** | Explicit half cutaway produces solid blue structures and visible pink clusters; framing remains too oblique. |
| 5 | 3 | More axial camera and smaller points leave half the frame empty and a large off-centre cage. |

## Best tested scene and defaults

Attempt 4 is reference-inspired rather than a faithful reproduction. The
reference's clear central radial event pattern has not been reproduced. Its
original camera matrix, selected geometry components and event provenance are
unknown; detector-era differences have not been established.

The portable recipe is
[`commissioning-interior.json`](../src/alice_renderer/presets/commissioning-interior.json).
It has no local data paths, event defaults or hardware/quality settings.
Exact use of this recipe requires the hash-checked ITS/TPC alignment assets.

| Setting | Tested value |
|---|---|
| Camera position, ALICE global metres | `[0.10, -1.20, -2.30]` |
| Aim point, global centimetres | `[-0.04729613, -0.03511476, -7.11026287]` |
| Projection, sensor, lens, roll | Perspective, 36 mm horizontal sensor, 36 mm lens, −12° roll |
| Data | ITS/TPC, tracks and clusters, solid colours, source-detector track clipping |
| Geometry | Full aligned surfaces, ITS/TPC, opacity 1, 180° openings removing −Y half, L3 off |
| Geometry / cluster / track / background colours | `#0700b5` / `#d58bdd` / `#60746d` / `#000012` |
| Track diameter / cluster radius | 0.05 cm / 0.40 cm |
| Colour transform / exposure | Standard / 0 stops |
| Track / cluster emission | 0.35 / 0.80 |
| Material | Smooth, roughness 0.58, metallic 0 |
| World strength | 0.01 |
| Area lights | 15 W at `[0.1,-1,-2]` m; 10 W at `[-0.6,-0.2,1.7]` m; 1.5 m size, white |

The recipe saves the actual rendered camera matrix and light rotations, not
only orbit estimates. Its orbit controls are consistent with the saved position.
Light rotations remain fixed when another camera target is supplied.

The desktop application starts with this style on a fresh installation; saved
local preferences take priority. **Appearance → Use commissioning defaults**
restores it while retaining the current input, selected events, local geometry
assets/units and hardware choices. This button clones the style onto the current
alignment bundle; loading the portable recipe normally enforces its asset
hashes. Missing aligned assets are reported before rendering. Programmatic
`RenderSettings()` retains its general tracks-only defaults.

## Framework improvement plan from the critic

1. **Visibility diagnostics:** cast rays to the primary vertex and a reproducible
   sample of selected clusters before rendering. Report blocking geometry names
   and visible fractions, respecting instancing, openings and transparency.
   A clear vertex alone was an inadequate predictor in this trial.
2. **Structural group controls:** expose independent visibility and opacity for
   services, shells and supports. Persist every exclusion in the recipe and
   render metadata. Keep detector alignment and source data untouched.
3. **Camera and cutaway guidance:** provide interior presets, visible wedge
   guides and projected cage/vertex framing aids. The named startup preset and
   desktop opening summary are implemented; live guides and framing aids remain.
4. **Cluster glyphs:** provide configurable sphere subdivisions and optional
   foreground size control. Attempt 4's nearby clusters appear too large and
   faceted. Physical radii should remain the default, with any screen-space
   alternative explicitly recorded.
5. **Portable colour controls:** Standard/AgX, exposure, lens length and separate
   track/cluster emission are implemented in scene recipes and both interfaces.
   Their native Blender updates and portable round trips are covered by QA.

The remaining items are a plan, not completed features. A further visual trial
should begin with component visibility diagnostics and the original reference
scene, if available, rather than another blind camera sweep.
