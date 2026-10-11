# ALICE Event Renderer

Native Python/Qt application and headless Blender Cycles renderer. Each selected record is rendered in a separate Blender process and output directory. The repository contains code, tests and configuration examples. Data, geometry bundles, generated outputs and the old framework are excluded.

## Working framework

The renderer, event catalogue, GUI and prerequisite checks are runnable. CPU and Apple Metal rendering are verified on this Mac, including separate images for multiple events. HIP, CUDA and OptiX are implemented through Cycles device discovery but need hardware validation. First-use Metal kernel compilation took about ten minutes here; subsequent events rendered normally.

The configurable remote O2 integration decodes and reconstructs full TF/CTF inputs, exports every reconstructed primary vertex, checks them against an independent O2 inventory, and retrieves compressed event data and aligned geometry. Its locally configured instance was validated for **run 560067** in the user-provided O2 environment; generic setup profiles are in `profiles/example-*.json`. Real-data checks retained **55 collisions from the raw TF** and **56 from a full-detector CTF generated from that TF**. These are two separately checked reconstructions; their vertex sets differ. See [validation and limits](docs/STATUS.md).

On the original workstation, ready-to-open real exports are in `data/validated/run560067-raw-v9` and `data/validated/run560067-ctf-v11`. Aligned assets for all 15 detector systems and L3 are in `geometry/run-560067`; loading an export automatically fills their paths and units in Setup.

## Run

On this machine double-click `Launch ALICE Renderer.command`, or:

```sh
cd /Users/jarvis/alice/Other/ALICE-event-renderer
.venv/bin/alice-renderer
```

For another supported machine:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -e .
.venv/bin/alice-renderer
```

Install Blender 4.5+ (this machine has 5.0). Choose its executable in Setup if it is not detected. CPU rendering works without GPU drivers. GPU choices are verified against the actual Blender build; unavailable backends stop before scene construction. AMD uses HIP/ROCm, Apple uses Metal, and NVIDIA uses CUDA/OptiX. The application never silently switches backends.

## Use

1. Paste a file/folder path and press **Enter** or **Load input**; **Browse file…** and **Browse folder…** open separate choosers. Both validated event folders, event JSON/JSONL (including gzip), and TF/CTF inputs are accepted. Configure the O2 ingestion profile in Setup; it requires the existing allocation and a matching reconstruction configuration. Prerequisites and run conditions are checked before reconstruction starts. Other runs require their own configuration.
2. Select individual records or all records. The grouping column distinguishes collisions, timeframes, ROFs and synthetic examples.
3. Select detector data and choose **tracks**, **clusters** or **both** for each detector. **Set all object modes** changes every detector together; tracks-only is the default. Trajectories are clipped to the selected track-source detector outer bounds; shown detector surfaces limit that selection when present. Matched sources keep their fitted kinematics and are drawn once. Unavailable data controls are disabled. Clipping uses the shown detector selection, or the data selection when no detector surfaces are shown. **Select no detectors** clears data, surfaces and L3.
4. Choose geometry independently, with a separate L3 checkbox. Complete detector geometry is the default; **Show complete detectors** resets existing openings to 0°. Supply a detector-specific asset in Setup, or explicitly opt into approximate schematic envelopes. Geometry assets must use ALICE global XYZ and a declared cm/m scale.
5. Choose solid or available scalar colouring, including **matching** for known O2 sources (0 = standalone fitted source, 1 = composite matched source). All installed Matplotlib colormaps are offered, including reversed maps (182 in the validated installation); sampled RGB tables travel with exported configs. Missing per-object values are grey. DCA and primary/secondary classification require explicit scientific provenance. Cluster momentum/angle colouring requires measured or associated-track quantities; it is not inferred from cluster position. Under Appearance, enter comma-separated **Special track IDs** to give those tracks a separate linewidth and their explicitly associated clusters a separate radius. Optional special colours override the colormap; turn them off to keep scalar/matching colours while changing sizes.
6. Click **Interactive scene…** to adjust the scene in Blender using full aligned surfaces or optional simplified geometry. **Pick tracks with mouse** selects a displayed trajectory; Ctrl-click adds, Shift-click toggles, Esc stops picking. Trackball navigation, direct camera rotation and roll buttons allow arbitrary camera orientation. Hidden instancing helpers remain hidden; per-detector shell/outline and opacity controls are available. **Export config** creates a portable recipe; **Render full** asks for quality, recommends available hardware, and offers full or simplified geometry independently for each selected detector and L3. See [portable scenes and editing](docs/SCENE-CONFIG.md).
7. Preview the first selected event (maximum 640 px and 16 samples), then render every selected event at the requested resolution. Adjust camera position and target, opacity, cutaway, samples, CPU threads, denoising, track linewidth and colours.

Each output contains a 16-bit PNG, the job configuration, Blender log, metadata (including colour ranges, omissions and geometry provenance), and optionally an editable `.blend` scene. A cancelled job retains diagnostic files.

## Data and scientific limits

- Canonical interchange coordinates are global centimetres. Momenta are GeV/c; angles are radians.
- TF entries are not individual collisions. Collision grouping needs primary-vertex reconstruction/association.
- The old `make_PVClusters.C` selects only 15 highest-multiplicity PVs and uses ideal TPC cluster transforms. It is not used as a complete or calibrated event exporter.
- The native exporter removes display quotas and uses the per-TF TPC correction map delivered to reconstruction. ITS/MFT use topology dictionaries and aligned transforms. Other spatial detectors use their O2 converters. Calorimeter cells and TRD tracklets are labelled explicitly.
- Whole-TF objects and unassigned references are retained separately. TPC clusters without a collision time retain native pad/time/charge measurements; assigning them calibrated global Z requires a time hypothesis. Cluster counts in collisions count associations, including shared clusters, rather than unique detector hits.
- Real data without MC truth leaves primary/secondary colouring unavailable. Cluster momentum colouring uses explicitly associated fitted tracks. Forward sources without a supported DCA propagation keep DCA unavailable.
- Official O2 display JSON contains eta/phi but lacks momentum magnitude, DCA and vertex XYZ. Associated clusters of composite-source tracks can lack detector identity; the adapter reports and omits those ambiguous clusters instead of assigning detector IDs by radius.
- Legacy JSON without proven grouping is labelled `timeframe`, not a reconstructed collision. This importer currently retains `RecoTracks` and their associated clusters; unused clusters/MC hit payloads are not interpreted as reconstructed data.
- Colour ranges are automatic per event, or fixed manually for comparable batch images. XYZ track colouring uses the first sampled track point, not momentum direction.
- Detector-envelope dimensions are illustrative. Real aligned geometry and calibration provenance are required for scientific detector images.

See [O2 integration](docs/O2-INTEGRATION.md), [interchange format](docs/INTERCHANGE.md), and [development status](docs/STATUS.md).

## Command line

```sh
.venv/bin/alice-render inspect data/low_density/FILE.root
.venv/bin/alice-render demo
.venv/bin/alice-render index examples/synthetic-events.jsonl
.venv/bin/alice-render index data/validated/run560067-raw-v9
.venv/bin/alice-render index data/low_density/reconstructed-ctf-run560067.root --profile profiles/virgo4-ingest.json
.venv/bin/alice-render devices
.venv/bin/alice-render render cache/CATALOGUE_ID --events 0,2 --preview
```

A portable scene starts a full render with one command (input and event override optional defaults):

```sh
alice-render render-config scene.json --input /local/events.jsonl.gz --event ordinal:0 --geometry-root /local/geometry --quality final --backend AUTO
```

An initial portable recipe is provided in `examples/portable-scene.json`; export an edited scene from the application to include geometry references and fixed colour ranges.

Use `--settings settings.json` for the headless render options. A saved GUI `settings.local.json` wraps those options under `render`; extract that object for headless use.

## Reference and attribution

The track-curve approach and geometry conversion are informed by Felix Schlepper's MIT-licensed aliceBlender reference. Geometry conversion corrects half-space boolean handling and preserves aligned global placements. Reference files remain unchanged and are not shipped. Building new TGeo geometry assets requires that separately installed MIT converter; set `ALICE_GEOMETRY_CONVERTER` or pass `--converter`. Rendering existing geometry assets does not require it. The native exporter derives from O2's GPL-licensed EventVisualisation workflow in an isolated generated build; its upstream license and exact source revision are retained there. No O2 checkout is modified.

The native exporter derivative retains the O2 GPL license. Project code is distributed under GPL-3.0; see [COPYING](COPYING).
