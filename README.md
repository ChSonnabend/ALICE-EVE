# ALICE Event Renderer

Native Python/Qt application and headless Blender Cycles renderer. Each selected record is rendered in a separate Blender process and output directory. The repository contains code, tests and configuration examples. Data, geometry bundles, generated outputs and the old framework are excluded.

## Working framework

The renderer, event catalogue, GUI and prerequisite checks are runnable. CPU and Apple Metal rendering were verified on the original Mac. Linux CPU and NVIDIA RTX 3090 OptiX rendering are also verified. HIP and CUDA device discovery are implemented but their render paths still need hardware validation. First-use Metal kernel compilation took about ten minutes here; subsequent events rendered normally.

The configurable remote O2 integration decodes and reconstructs full TF/CTF inputs, exports every reconstructed primary vertex, checks them against an independent O2 inventory, and retrieves compressed event data and aligned geometry. Its locally configured instance was validated for **run 560067** in the user-provided O2 environment; generic setup profiles are in `profiles/example-*.json`. Real-data checks retained **55 collisions from the raw TF** and **56 from a full-detector CTF generated from that TF**. These are two separately checked reconstructions; their vertex sets differ. See [validation and limits](docs/STATUS.md).

On the original workstation, ready-to-open real exports are in `data/validated/run560067-raw-v14` and `data/validated/run560067-ctf-v16`. Old TF exports with coordinate version below 3 are rejected for TPC tracks/clusters because their TPC time hypotheses need correction; use these re-exported inputs. Aligned assets for all 15 detector systems and L3 are in `geometry/run-560067`; loading an export automatically fills their paths and units in Setup.

## Run

On this machine double-click `Launch ALICE Renderer.command`, or:

```sh
cd /Users/jarvis/alice/Other/ALICE-event-renderer
.venv/bin/alice-renderer
```

For another supported machine:

```sh
python3.12 -m venv .venv
.venv/bin/python -m pip install -e .
.venv/bin/alice-renderer
```

Python 3.11 or newer is required. If using an existing Conda environment, no
additional virtual environment is needed:

```sh
conda activate py312
python -m pip install -e .
alice-renderer
```

Check `python --version` (or `.venv/bin/python --version`) if installation reports
an incompatible Python. Creating a venv over an old venv can retain its old
interpreter symlink; move the old directory aside and create a fresh one.

Install Blender 4.5+ (this machine has 5.0). Choose its executable in Setup if it is not detected. CPU rendering works without GPU drivers. GPU choices are verified against the actual Blender build; unavailable backends stop before scene construction. AMD uses HIP/ROCm, Apple uses Metal, and NVIDIA uses CUDA/OptiX. The application never silently switches backends.

## Use

1. Paste a file/folder path and press **Enter** or **Load input**; **Browse file…** and **Browse folder…** open separate choosers. Both validated event folders, event JSON/JSONL (including gzip), and TF/CTF inputs are accepted. Configure the O2 ingestion profile in Setup; it requires the existing allocation and a matching reconstruction configuration. Prerequisites and run conditions are checked before reconstruction starts. Other runs require their own configuration.
2. Select individual records or all records; **PV contributors** helps distinguish low- and high-multiplicity vertices. The grouping column distinguishes collisions, timeframes, ROFs and synthetic examples.
3. Select detector data and choose **tracks**, **clusters** or **both** for each detector. **Set all object modes** changes every detector together; the commissioning desktop preset starts with both, while programmatic general settings default to tracks only. Trajectories are clipped to the selected track-source detector outer bounds; shown detector surfaces limit that selection when present. Matched sources keep their fitted kinematics and are drawn once. Unavailable data controls are disabled. Clipping uses the shown detector selection, or the data selection when no detector surfaces are shown. **Select no detectors** clears data, surfaces and L3.
4. Choose geometry independently, with a separate L3 checkbox. **Show complete detectors** resets all openings to 0°. Supply a detector-specific asset in Setup, or explicitly opt into approximate schematic envelopes. Geometry assets must use ALICE global XYZ and a declared cm/m scale.
5. Choose solid or available scalar colouring, including **matching** for known O2 sources (0 = standalone fitted source, 1 = composite matched source). All installed Matplotlib colormaps are offered, including reversed maps (182 in the validated installation); sampled RGB tables travel with exported configs. Missing per-object values are grey. DCA and primary/secondary classification require explicit scientific provenance. Cluster momentum/angle colouring requires measured or associated-track quantities; it is not inferred from cluster position. Under Appearance, enter comma-separated **Special track IDs** to give those tracks a separate linewidth and their explicitly associated clusters a separate radius. Optional special colours override the colormap; turn them off to keep scalar/matching colours while changing sizes.
6. Click **Interactive scene…** to adjust the scene in Blender using full aligned surfaces or optional simplified geometry. **Pick tracks with mouse** selects a displayed trajectory; Ctrl-click adds, Shift-click toggles; **Stop picking (Esc)** or Esc stops picking. Add any available detector surface later using its Surface checkbox; choose an aligned asset in the sidebar when one was not supplied at launch. The general orbit uses Y up with a horizontal XZ plane; the commissioning preset uses its tested interior camera and +13.3° roll. **Navigate render camera** is enabled by default so zoom/pan/orbit adjust final framing. Trackball navigation, direct camera rotation and roll buttons allow arbitrary camera orientation; **Level camera (Y up)** restores a level horizon. The sidebar shows input track/cluster counts per detector. **Include ambiguous vertex matches** controls possible multi-vertex time-window associations and their linked clusters; new scenes exclude them. Hidden instancing helpers remain hidden; per-detector shell/outline and opacity controls are available. **Use real solid detector surfaces** loads full opaque aligned meshes; the viewport defaults to denoised Cycles with 128 preview samples; fast Eevee remains selectable. **Light transparent detector surfaces** loads full meshes at 0.035 opacity per surface, avoiding heavy attenuation through overlapping layers. Cluster dots remain separate event data. **Export config** creates a portable recipe; **Render full** asks for quality, recommends available hardware, and offers current-scene, full aligned surfaces, simplified aligned cells, or schematic envelopes independently for each selected detector and L3. Full aligned surfaces overrides a schematic preview and requires the aligned assets. See [portable scenes and editing](docs/SCENE-CONFIG.md).
7. Preview the first selected event (maximum 640 px, 128 samples and denoising), then render every selected event. Full-render resolution is a linear percentage of the 8K canvas: **25% = 1080p**, **50% = 4K**, **100% = 8K** for 16:9; other aspect ratios keep their framing inside the canvas. Sampling presets and per-detector geometry detail are chosen separately. Adjust camera position and target, opacity, cutaway, samples, CPU threads, denoising, track linewidth and colours.

**Recent scenes** lists completed renders and automatically saved interactive sessions. Use the recent/favourite pickers above the event list to reuse settings for the current input and selected event. The **Favourites** tab keeps named, fixed snapshots. **Reload scene and original event** restores the original event when its local data is available; **Use for current input / event** retains your new file/event selection and clears event-specific highlighted track IDs. History and favourites are local and excluded from Git.

Final-render dialogs and command-line final renders default to **full aligned
geometry**, independently of fast preview surfaces. Detector parts, exclusions,
openings, camera and colours remain as selected. Reduced detail is an explicit
render choice; `--geometry-detail current` keeps the recipe's exact detail. Missing
full assets produce a prerequisite message rather than a simplified fallback.

New installations include **ITS-TPC** and **ALICE general** in Favourites. These preserve the camera, detector parts, colours, transparency and lighting of the saved private-linux “TPC-ITS closeup” and “ALICE global” scenes. Choose your local input and event, select a favourite, then click **Use favourite**. Prepared geometry is resolved from the local `geometry/run-560067` bundle; input paths, events and hardware choices are not bundled. Existing favourites are preserved, and removing a starter favourite keeps it removed on restart. The portable starter recipes are included in the package under `presets/favourite-*.json`.

**Calorimeter towers:** enable **clusters** or **both** for EMC, PHOS (`PHS`) or CPV. In the appearance controls, choose **signal towers** or **fixed towers** separately for each detector; points remain the default. The Blender editor exposes the same choices under each detector. Height scale, maximum height, footprint scale, fixed height and inward/outward direction are saved in portable configs and favourites, and apply to previews and full renders. Signal heights use the available measurement: EMC energy in GeV; PHOS raw O2 cells in ADC counts, or explicitly calibrated input energies in GeV; CPV in native amplitude units. Select `energy` or `amplitude` for colour coding. Missing/nonpositive signals retain point glyphs; the render legend reports these fallbacks and capped heights. Fixed towers carry no signal-height interpretation.

The **Data sizes** tab sets cluster-size factors for every detector, and tower footprint factors, fixed heights and height limits for EMC/PHOS/CPV. Cluster factors multiply ordinary and linked-cluster radii, and TPC measured-profile display dimensions. Footprint factors multiply the scene footprint scale. A factor of **1** keeps the scene size; a detector fixed height or height limit of **0 / Use scene** inherits the scene setting. Blender offers these controls in each detector's panel. Returning to inheritance clears the override in the exported config.

**Collision videos:** select at least two collisions, enable video in the **Video** tab, then choose **Play collisions…**, **Preview video** or **Render video**. Choose a fixed interval or scaled collision timestamps (scale **0** automatically averages one arrival per second), display propagation in metres per video second, tower rise time and FPS. Tracks grow outward; clusters appear on arrival and towers rise gradually. Each new collision replaces the previous one. Blender loops the selection and provides **Pause collisions** and independent **Pause viewport / Resume viewport** controls. Sidebar editing holds playback so dropdowns remain available; data/object/colour choices persist across the selected sequence. Detector meshes stay loaded and movie renders reuse persistent render data. Full rendering writes MP4; scene/video settings export in portable configs. See [video playback, timing and export](docs/VIDEO.md).

Choose **Appearance → Tower height mapping → Logarithmic**, or override the mapping for one calorimeter in **Data sizes**. Linear remains the default. Logarithmic height is `height_scale × reference × ln(1 + signal/reference)`, followed by the chosen height limit. The positive reference is in that detector's signal units; smaller references compress large signals sooner. Near zero this preserves the linear scale's slope. Fixed-height towers keep their chosen height. Colour values, positions, measured profile widths and signals retain their original data values. Size factors, mapping and reference values are exported with configs and favourites for rendering on another machine.

New O2 exports include aligned module footprint vectors and cell/module identifiers for EMC/PHOS. Rectangular EMC footprints omit cell taper. PHOS trigger-summary channels are excluded. Existing exports use nominal tangent-plane footprints, explicitly counted in render metadata; older O2 PHOS values named `energy` are recognised as ADC amplitude from their provenance. CPV ROOT inputs currently provide reconstructed clusters: their towers represent those clusters with a one-pad display footprint, not resolved individual pad measurements. New whole-TF exports retain their measured amplitude and aligned plane. Whole-TF views may contain several trigger measurements of one cell; each measurement remains separate, with no implicit energy summation. AO2D track-only inputs have no cell signals to display.

For a cleaner TPC view, the Blender sidebar's **TPC sectors + inner wall** keeps only readout-sector chambers and inner wall/shields. **Add lights around detector** supplies adjustable side/end lights without changing the camera or background. Both choices export with the scene.

**Use fast ITS/TPC surfaces** loads prebuilt broad ITS stave panels and TPC walls/sectors, keeping the existing camera, opening angles, colours and lighting. This display approximation uses full aligned track-clipping bounds. Prepare its small caches once with `alice-render prepare-geometry --geometry-root /local/geometry --detectors ITS,TPC --units m`; then choose **Large surfaces (cached, fast)** / `structural` detail. See [large surfaces](docs/LARGE-SURFACES.md).

Fresh desktop installations use the saved ALICE2 scene exported from `editor-20261012-130704-860001`. Appearance → Detector setup offers ALICE2, ALICE2 + ITS3, and ALICE3 defaults with shared camera and lighting. Saved local preferences take priority. The earlier commissioning style remains available through **Use commissioning defaults**. See [detector setups](docs/DETECTOR-SETUPS.md).

Direct AO2D import lists collision rows and lazily reads barrel, MFT and forward fitted tracks, with numeric track-feature colour choices. It needs run-specific field conditions and no local O2 installation. See [AO2D usage and projection limits](docs/AO2D.md). Detector **Components** controls expose ITS layers, TPC walls/cages/readout, supports and named elements; recipes preserve per-placement choices. See [component categories](docs/SCENE-CONFIG.md#detector-component-categories).

Each still-render output contains a portable scene recipe, a 16-bit PNG, the job configuration, Blender log, metadata (including colour ranges, omissions and geometry provenance), and optionally an editable `.blend` scene. Video outputs contain MP4 and a poster PNG. A cancelled job retains diagnostic files.

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
.venv/bin/alice-render index data/validated/run560067-raw-v14
.venv/bin/alice-render index data/low_density/reconstructed-ctf-run560067.root --profile profiles/virgo4-ingest.json
.venv/bin/alice-render devices
.venv/bin/alice-render render cache/CATALOGUE_ID --events 0,2 --preview
```

A portable scene starts a full render with one command (input and event override optional defaults):

```sh
alice-render render-config scene.json --input /local/events.jsonl.gz --event ordinal:0 --geometry-root /local/geometry --quality final --resolution-percent 50 --backend AUTO
```

An initial portable recipe is provided in `examples/portable-scene.json`; export an edited scene from the application to include geometry references and fixed colour ranges.

Use `--settings settings.json` for the headless render options. A saved GUI `settings.local.json` wraps those options under `render`; extract that object for headless use.

## Reference and attribution

The track-curve approach and geometry conversion are informed by Felix Schlepper's MIT-licensed aliceBlender reference. Geometry conversion corrects half-space boolean handling and preserves aligned global placements. Reference files remain unchanged and are not shipped. Building new TGeo geometry assets requires that separately installed MIT converter; set `ALICE_GEOMETRY_CONVERTER` or pass `--converter`. Rendering existing geometry assets does not require it. The native exporter derives from O2's GPL-licensed EventVisualisation workflow in an isolated generated build; its upstream license and exact source revision are retained there. No O2 checkout is modified.

The native exporter derivative retains the O2 GPL license. Project code is distributed under GPL-3.0; see [COPYING](COPYING).

## Local preprocessing, detector setups and profiles

See [local TF/CTF and AO2D preprocessing](docs/LOCAL-PREPROCESSING.md), [TPC pad/time profiles](docs/TPC-PROFILES.md), and [ALICE2 / ITS3 / ALICE3 presets and render progress](docs/DETECTOR-SETUPS.md).

Portable scene recipes can select `"render_engine": "BLENDER_EEVEE"` for GPU rasterization, or `"CYCLES"` (the default) for path tracing. Eevee uses the recipe’s materials, openings and geometry detail settings; rasterization itself does not remove subpixel geometry. ITS/TPC `structural` detail reduces geometry before rendering. The sample setting controls Eevee temporal antialiasing; Cycles backend/device selections do not apply to Eevee.

Interactive loading defaults to **Fast interactive**: reviewed cached approximate surfaces for all 15 ALICE2 detectors and the L3 magnet, plus a 32-sample Eevee viewport. Caches are baked from aligned native geometry and batched into 17 mesh objects for the complete setup. Compatible ITS/TPC structural caches remain a fallback for bundles without the new caches. Missing caches or incompatible masks keep the existing geometry. Turn this option off to retain the original editor startup path; full aligned surfaces remain selectable in the editor/render dialog. This does not decimate or subsample event data.

With no event selected, the desktop preview, render and interactive-scene actions show **geometry only**. No input dataset is required. Select detector geometry first; use **Select none** to clear event selection after loading data. Geometry-only jobs explicitly record `kind: geometry` and contain zero tracks/clusters.

See [cached interactive surfaces and review workflow](docs/FAST-SURFACES.md) for geometry scope, quality limitations and rebuild commands.
