# Portable scenes and interactive editing

A scene recipe is a JSON file with schema `alice-eve-scene`, version 1. It contains camera projection and pose, aspect ratio, colours and fixed colour scales, detector/data selections, geometry detail, per-detector openings and opacity, track/cluster sizes, materials, lighting and background. It contains no backend, GPU ID, CPU thread count, render resolution or sample count. Input and event defaults are optional; exported scenes omit them unless explicitly requested.

## Desktop workflow

1. Load data and select an event. Select detector surfaces and L3 independently; supply the corresponding geometry assets.
2. Click **Interactive scene…**. Blender preserves the selected Geometry detail (full aligned surfaces or coarse cells) and opens an Eevee rendered viewport. Hidden placement/prototype helpers remain hidden, and blended transparency avoids hashed speckles. Open the **ALICE EVE** tab in the right sidebar (N toggles the sidebar).
3. Orbit, pan and zoom; click **Use current view as camera** to make that view the render camera. Camera lens/projection can be edited directly. Change light positions/rotations, power, size and colour in the sidebar.
4. Click **Full aligned surfaces** for the natural detector structures used in the reference renders. **Make geometry opaque** sets opacity to 1; lower each detector's Opacity for a translucent view. Choose **Existing surfaces**, **Outer shell** or **Outline** per detector and click **Apply geometry appearance**. Shell/outline use an approximate convex hull and may fill beam holes or bridge disconnected structures; keep Existing surfaces for physical geometry. Set detector opening angles, colours, opacity, shading and background. Openings remove an angular wedge around global Z, centred on −Y: 0° keeps the full surface; 180° opens the −Y half; 360° hides the surface. These live openings use a global-position shader mask, including instanced geometry.
5. Select event data and colour quantities. Click **Apply data selection / colour coding** after changing those controls. Unavailable detector data is disabled; unsupported colour quantities produce a diagnostic. Fixed scalar ranges keep identical colour coding when another event is rendered.
6. Click **Export config** to save the current scene without choosing quality. Optionally include a default input/event. **Render full** opens the quality dialog, recommends an available backend/preset and checks prerequisites before starting a separate render process. Progress and any failure details are in the displayed `full-render.log` location.

The Qt application also has **Export config…** and **Load config…**. A loaded config keeps its exact camera matrix until you edit the camera position controls. Geometry detail can be selected as full or simplified. Quality is chosen by the full-render dialog; preview is capped at 640px/16 samples.

Full aligned surfaces preserve the native detector structures and can be heavier to navigate. For a look similar to the run-560067 reference images, use full ITS/TPC geometry, an approximately 180° opening and opacity around 0.035 (or increase opacity to make surfaces more solid).

The optional simplified mode derives spatial cell bounds from the actual aligned surfaces. It reduces each detector to one mesh with at most 256 coarse cells, rather than millions of repeated small shapes. It is explicitly an approximation: small structures and curved surface detail are lost. Exported scenes retain that detail choice so the final render has the same surfaces. Choose full geometry and export another recipe when physical surface detail is needed. Simplifying geometry does not reduce the number of event objects; dense cluster displays can still need substantial memory.

## Move to another computer

Copy the scene JSON and the selected detector geometry files. Data can be copied separately, or select a different local input/event. Geometry references contain basenames and SHA-256 hashes, not the originating computer's absolute paths. `--geometry-root` locates a geometry bundle on the destination; hashes enforce the same alignment and surfaces. A local `--assets` JSON mapping can point individual detectors to different folders; it cannot bypass the hash check.

After installing this project and Blender, one command starts the full render:

```sh
alice-render render-config scene.json --input /local/events.jsonl.gz --event RUN-TF-PV-ID --geometry-root /local/geometry --quality final --backend AUTO --output renders
```

Use the event ID listed in the catalogue, or explicitly use `--event ordinal:0`. Command-line input/event values override optional config defaults. Relative default input paths are resolved beside the config. An omitted input/event without a default is an error. Raw TF/CTF inputs additionally require `--profile /local/ingest.json` for a configured O2 environment; exported event data renders without O2.

```sh
alice-render edit-config scene.json --input /local/events.jsonl.gz --event ordinal:0 --geometry-root /local/geometry
```

This reopens the interactive scene from its recipe, rather than relying on saved Blender UI state.

| Preset | Width | Cycles samples |
|---|---:|---:|
| draft | 640 | 16 |
| balanced | 1920 | 128 |
| final | 3840 | 512 |
| publication | 7680 | 1024 |

Height follows the stored aspect ratio. Override with `--width`, `--height`, `--samples`; changing aspect ratio deliberately changes framing. GUI custom quality provides the same controls. Recommendations start CPUs at draft and detected GPUs at balanced, rather than predicting timings or VRAM capacity. AUTO selects an actually discovered OptiX, Metal, HIP, CUDA or CPU backend, in that order. Explicit unavailable backends produce an error without fallback.

The same recipe reproduces camera, scene geometry, lights, materials and scalar ranges. CPU/GPU numerical differences, stochastic sampling, denoising and Blender-version colour management can change pixels; bit-identical PNGs across backends are not promised. Use the same Blender version for closest matching output. Recipe schema/geometry mismatches stop before rendering.
