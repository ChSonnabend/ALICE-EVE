# Validation status — 12 October 2026

## Collision video update

Interactive playback now has independent collision and viewport pause/resume
controls. Sidebar hover holds the playback clock while dropdowns are being edited;
track picking pauses the collision. Object modes, enabled detectors and feature
menus remain available across the selected sequence, with missing values coloured
as unknown. Detector object/mesh identities remain unchanged across repeated
collision loops, and movie renders enable Cycles persistent render data. Both
Cycles preview pause and Eevee solid-inspection pause were checked natively.
245 Python tests pass; native QA also exercises the sidebar hold/release and a
detector absent from the second collision. A 16-frame real run-560067 CPU movie
renders and decodes with geometry reuse enabled. Detector pixels are still shaded
per frame to retain depth, transparency and shadows.

Multi-collision playback and H.264 MP4 export use the same geometry-node growth
for tracks, delayed cluster instancing and gradually rising towers. Fixed intervals
and fine collision-clock schedules are portable settings; automatic scaling averages
one arrival per video second. Event files remain an instance-level selection.
Viewport playback loops and Stop unregisters its timer immediately. Geometry and
camera remain fixed between collisions; only the active collision's particle
buffers are loaded. Colour ranges cover the selected collisions.

244 Python tests pass, including UI selections/config round trips, timestamp clocks,
AO2D clock-field import, encoder prerequisites and command-line selection. Native
Blender checks verify clipped growth, hidden/revealed clusters, half/full tower
heights, collision replacement, repeated loops without node-group accumulation,
Play/Stop and the full-render button's all-event handoff. Existing per-detector
controls, sizes and calorimeter tower QA also pass. Two run-560067 collisions
(ordinals 8 and 36) exported and decoded successfully on CPU at 640 × 360,
8 FPS, 16 frames, 2 seconds. The measured timestamp scale was
606.7887116633854 video seconds per source second, with collision replacement at
frame 8. Video hardware validation on other platforms remains outstanding.

Unlinked measurements use an explicitly labelled primary-vertex distance wave;
linked hits use their sampled associated path. Animation speeds are visual controls,
not measured flight times. Detector clipping retains the aligned outer extent masks
used by still rendering. See [video controls and limits](VIDEO.md).

## Implemented

Track rendering now clips to aligned detector outer envelopes and preserves original fitted quantities. Linewidth is adjustable in both interfaces. Detector reset and complete-geometry controls are implemented; complete geometry is the new default. Default cameras now orbit around Y at zero elevation, with XZ horizontal. Older recipe cameras retain their framing. The sidebar camera-capture operator handles the WINDOW region and existing camera views without a traceback; Level camera removes roll. PV contributors and per-detector input counts expose collision multiplicity.

The native desktop application lists individual collisions and supports detector selection, tracks/clusters/both, scalar and solid colours, independent geometry and L3, preview and full Blender renders. Tracks-only is the default. Each detector has its own object mode. Comma-separated track IDs and mouse picking control separate track/associated-cluster emphasis. Matching colours use explicit O2 fitted-source records, and all host Matplotlib colormaps (182 here) travel as RGB tables in portable configs. Typed file/folder paths load through Enter/Load input; the preview and long output paths no longer enlarge the window. Camera trackball navigation, direct rotation and roll allow arbitrary orientations. Data, truth labels and colours that are unavailable remain disabled or explicitly unknown.

The Virgo integration now reconstructs raw TFs and full-detector CTFs, exports every primary vertex without display quotas, retains failed propagation and invalid coordinate diagnostics, and checks every event against an independent O2 inventory. Original PV-reference IDs and cluster associations are audited separately. Component fits are retained instead of being consumed by O2's display iterator; MCH–MID matches are handled as matches rather than standalone track storage.

## Real-data evidence

A subsequent native-coordinate audit found an incorrect standalone TPC Z-shift sign and a double-counted drift offset in the earlier exporter. Original reference checks established enumeration completeness, not spatial correctness. Version 3 uses the per-TF map’s delta-time conversion before propagation/sampling; constrained two-side standalone fits and their hits retain their fitted T0. Native A/C samples (153 measured clusters) agreed within 0.8 micrometres with exported cluster coordinates, and all 15 ITS measurements for vertex index 5 agreed exactly with a separate ROOT conversion. The corrected two sampled TPC fits had median absolute longitudinal residuals of about 1.5 and 2.0 mm. These spot checks do not certify every reconstructed fit or a physics production pass.

Explicit O2 ambiguity and PV-contributor flags are retained and compared with the independent inventory. New scenes omit ambiguous time-window associations and linked clusters; they remain selectable. Unambiguous association is still not MC truth or proof of primary origin. Old recipes preserve their all-reference appearance until the new control is changed. The selected vertex’s original 4,502 displayed fits must not be interpreted as 4,502 uniquely identified particles from that collision.

All checks use run **560067**, TF counter **2619419**, first orbit **212036032**. The raw input is 696,782,440 bytes. A 137,517,804-byte full-detector CTF was generated from that real raw TF and used to validate the CTF route.

- Current coordinate-version-3 raw export: `data/validated/run560067-raw-v14`, **54 collisions**, **392,756 drawable fitted references**, **5,327 preserved unsampled fits**, **19,094,220 cluster associations**. Enumeration, schema, reference IDs, ambiguity/contributor flags and TPC time-basis audits passed for every event. All 41 constrained two-side TPC time records retain native fit T0 for their measured clusters.
- Current coordinate-version-3 CTF export: `data/validated/run560067-ctf-v16`, **57 collisions**, **336,579 drawable fitted references**, **1,338 preserved unsampled fits**, **18,773,277 cluster associations**. The same complete audits passed; both constrained two-side TPC records retain fit T0. Both routes also provide 10 separately labelled whole-TF detector views. Local and remote event/archive SHA256 values agree; all 16 detector/L3 surface hashes match the captured aligned geometry.
- The corrected raw vertex at index 5 has **4,489 drawable fitted references**, including **4,462 explicitly ambiguous references** and **3 PV contributors**. Selecting ITS/TPC and excluding ambiguous associations displays **10 fitted references and 884 cluster associations**. Component fits remain separate references, so these counts are not unique-particle multiplicities.
- Earlier raw-TF enumeration: **55 collisions**, **399,127 drawable tracks**, **4,568 preserved propagation failures**, **19,360,314 cluster associations**. Full schema validation and original-track-reference checks passed for every event. No fitted-track reference is missing or extra. The remaining reference types are timing/calorimeter/CPV signals retained by the independent inventory and whole-TF archive.
- Earlier CTF enumeration: **56 collisions**; independent TF/PV enumeration and both end-of-stream markers agree. **333,156 drawable tracks**, **451 preserved propagation failures**, **18,524,219 cluster associations**; complete object/reference audit passed. Thirteen nonfinite HMP measurements are retained in the whole-TF archive as non-renderable diagnostics.
- Earlier reconstruction attempts produced 54–57 vertices. Raw and CTF reconstruction vertex sets differ; this project verifies each export against its own reconstruction rather than asserting physics equivalence between routes.
- The desktop-to-Virgo bridge completed a separate real CTF import end to end, including condition checks, reconstruction, compression, retrieval, inventory reconciliation and geometry reuse.
- All **15 detector systems plus L3** were built as aligned assets, covering **1,418,318 physical surface instances**. Every translation passed at stored precision; maximum rotation-matrix entry error was **2.07 × 10⁻⁷**. All surface hashes match the exact geometry manager captured during the final raw and CTF reconstructions.
- Actual real-data CPU preview and Apple Metal renders passed. Separate selected events have independent PNG/configuration/log/Blender outputs. A global-Y cutaway clips geometry rather than relying on long transparent ray chains. The camera uses ALICE +Y as up.
- Actual GUI import, selection, geometry auto-fill, scalar availability and Preview-button execution passed. No MC truth is fabricated.
- **155 automated tests passed**, including atomic caches, complete enumeration, flow control, private socket namespaces, the native-component TPC preset, portable large-surface caches and desktop config import of disabled parts/lights with matching or mismatched Setup geometry. Python source compilation and native exporter compilation passed.

Those earlier datasets passed enumeration checks but have superseded TPC coordinates; do not use them for new TPC renders. Coordinate-version-3 exports and their full audits replace them. Their manifests, enumeration reports, object audits and geometry reports retain the evidence. Earlier exports remain available for comparison. Current assets are under `geometry/run-560067`; real render evidence is under `renders/qa/real-data`.

Three CPU diagnostic images compared the corrected event, transparent materials and restored detector walls. The final image is `renders/qa/cluster-correction/render-20261011-194645-f58d4a/event-00000/render.png` (640 × 360, 32 samples, denoised). Its portable recipe is copied to `configs/corrected-event-5-restored-surfaces.json`. It preserves the user's camera and colours, loads full aligned ITS/TPC/TRD/TOF surfaces, restores name/inner-radius exclusions, keeps TPC rod component exclusions, uses 0.035 opacity per face, +1.5 exposure, 0.2 cm track linewidth, and excludes ambiguous associations. Explicit data-emitter mesh-light sampling is disabled while visible glow and scene lights remain. The result is deliberately transparent rather than an opaque detector, and preview-size image quality does not establish high-resolution convergence. A critic reviewed each image; numerical native checks, not the image, establish the sampled coordinate agreement.

## Portable scenes and editor

Versioned portable scene export/import, local input/event overrides, geometry hash verification, hardware quality presets and the `render-config` command are implemented. Blender's interactive ALICE EVE sidebar supports camera capture, lights, detector openings, colour coding, transparency, materials and background, with separate Export config and Render full buttons. Picking now has documented start/stop tooltips. Both full-render dialogs distinguish current-scene, full aligned, simplified aligned and schematic geometry independently for selected detectors and L3. Explicit full/simplified choices override the schematic flag and outer-hull appearance; missing assets stop at preflight. Render-camera navigation is enabled by default; camera export now includes sensor fit/dimensions, shifts and clipping distances as well as pose/lens/orthographic scale. Each subprocess receives an immutable config snapshot. Per-detector detail persists in portable recipes; render-only choices leave the editor view unchanged. Native QA checks the registered stop operator, the actual Render full operator and its subprocess config, and both directions of detail overrides on the aligned TPC asset. The editor now preserves the requested geometry detail. Full aligned surfaces match the physical structures used in the reference renders; hidden Geometry Nodes helpers stay hidden in the viewport, and blended Eevee transparency reduces hashed speckles; accurate Cycles now defaults to 128 preview samples and denoising. Opacity is labelled per surface, and the light-transparency action loads full meshes at 3.5% per face. The data-glow lighting checkbox makes explicit mesh-light sampling optional while retaining visible emission and the scene lights. Optional shell/outline and opaque controls persist in configs. The optional simplified geometry uses at most 256 coarse spatial cells per detector. These cells are approximate bounds, not full physical surfaces.

A real TPC asset was reduced from 10,316 instances to one 256-cell mesh. Headless Blender editor registration, live property updates, camera/light export and scene reload passed. The exported scene rendered on CPU and Apple Metal with a different selected event; the scene settings remained intact. The desktop config-load controls and the editor's Render full operator passed; the latter completed a separate CPU render. A portable config also rendered a validated real collision with simplified ITS, TPC and L3 on Metal. Blender QA also checks hidden instancing helpers, blended viewport materials, switching full/shell/outline modes, opacity and config export. Real CPU renders verify full and outline display modes. A real run-560067 collision passed clipping QA for all 2,260 displayed trajectory vertices, with complete ITS/TPC geometry and adjusted linewidth. Both desktop and Blender detector-reset/full-geometry/linewidth controls passed. New native Blender QA checks per-detector object counts, selected-track widths and linked-cluster radii, projected picking of displayed curves, beam-axis camera roll and config export. A real run-560067 event rendered 189 selected TPC tracks and 6,672 ITS/TPC clusters with matching colours and special track IDs on Metal. The 101 cluster associations whose nondrawable fitted-track records lack a source label retain unknown matching (grey); no source is guessed. Pasting the real export folder loaded all 55 collisions with matching available. Native Blender QA also captures a perspective viewport from its sidebar context, handles an existing camera view, levels without moving/changing view direction, and checks detector counts. A real event-5 Metal render verified exact +Y camera up; all 3 ITS-associated trajectories survive ITS-only clipping. Its 64 unsampled tracks are TPC-only, and the event has 3 PV contributors. Event 4 in the same raw export contains 4,926 ITS-associated drawable fitted records, demonstrating that sparse ITS membership depends on collision selection. Additional native QA executes Blender’s camera-lock zoom operator, verifies increased projected scene size and a changed render-camera matrix with unchanged inspection zoom, and checks equal projection matrices at 1080p and 4K for perspective/orthographic cameras with custom sensor fit and shifts. A config-command Metal render upgraded the user’s schematic event-5 scene to full aligned ITS/TPC (543/243 meshes) and restored the test’s 96mm lens, camera shifts and matrix exactly within float tolerance. Cross-platform config relocation/hash checks and event selection are automated tests. Linux/NVIDIA/AMD rendering remains a hardware-validation limit.

Detector surfaces can now be loaded after editor launch; geometry availability depends on supplied assets (or explicit schematic mode), independently of initial visibility and event-data availability. Assets can also be chosen in the sidebar. Picking yields overlapping sidebar/toolbar clicks so Stop picking receives its click. Full render resolution uses an 8K-percentage slider with 1080p/4K/8K milestones, preserving camera aspect. Desktop recent/favourite pickers and tabs support original-event reload and cloning scene style onto another file/event. Favourites are fixed snapshots; interactive sessions autosave every two seconds. Completed renders record the actual camera and legends in their portable recipes. Local history/favourites remain excluded from Git.

Native Blender checks loaded the real aligned TPC after starting with no surfaces selected and passed sidebar picking/stop and percentage subprocess handoff. A real run-560067 event-5 editor check started with all surfaces hidden, then added ITS/TPC coarse surfaces without loading the other available assets; its favourite replay retained detector choices and the 96mm camera. A separate config-command Metal render at 8⅓% (640 × 360) used full ITS/TPC (543/243 meshes), and its history recipe exactly matched the emitted camera metadata. Desktop tests click the actual reuse/favourite/remove buttons, retain new input/event selections when cloning, select only the original event when reloading, and prevent rendering stale data after an unloaded path change.

## Scientific and operational limits

- Configured and validated for this run and installed O2 suite; other runs need matching reconstruction settings. Real validation is one TF per route, not a multi-TF campaign. The code has no top-N/file/time quotas.
- TPC global coordinates use the reconstruction's per-TF correction map and a track/PV time. TPC measurements without a collision-time hypothesis retain native pad/time/charge rather than an invented global Z.
- Whole-TF spatial objects, unassigned references, timing channels and ZDC energies are retained separately. Their archive is not a collision catalogue. Separately labelled whole-TF detector views expose valid spatial objects, including HMP and CPV, without inventing collision associations. HMP/CPV whole-TF objects are not assigned to arbitrary vertices.
- PHOS/EMCAL measurements are cells, TRD measurements are calibrated tracklets. Those types and association bases are explicit. Invalid coordinate conversions remain non-renderable diagnostics.
- DCA is available for supported barrel propagation with nominal Bz and no material correction; unsupported sources or failed propagation remain unknown. MC primary/secondary truth does not exist in this real data.
- Geometry represents the first solid material boundary in each branch, with all global parent transforms. It is a detector-exterior representation, not every nested gas/material volume. The first TF's manager is captured; changing alignment validity across a file needs separate snapshots.
- The supplied large TPC-only CTF repeats the same identity 101 times and lacks ITS. It is diagnosed before reconstruction. Other detector-only inputs require an appropriate vertexing strategy or existing vertices.
- CPU and Apple Metal were exercised on this Mac. Intel CPU, NVIDIA CUDA/OptiX and AMD HIP/ROCm rendering paths use Cycles device discovery and are implemented, but those specific hardware configurations remain unverified. There is no silent backend fallback.

## Environment and isolation

O2 runs inside the user-provided Virgo allocation **17012652**, with ROOT **6.36.10** and the installed `nn_momentum_vector-local1` O2 suite. Commands use unique positively numbered steps; the original **17012652.0** is preserved. DPL socket namespaces are also unique because session/shm IDs alone do not isolate the allocation-wide metric-feedback socket.

Only the project and its isolated remote work directory are modified. Original TF/CTF inputs, the old renderer and O2 checkouts remain unchanged. Conditions are checked from the generated workflow and pinned through the public CCDB HTTP cache. This is rendering validation, not certification of a production reconstruction pass.

The user authorized dropping the unreliable helper. Current source inspection and QA are performed directly, without helper-session dependence.

## AO2D and geometry component update

The supplied AO2D on Virgo (job 17012652) was checked directly with loaded O2.
Its 90 dataframes contain 30,957 collision rows, run 572669. The importer recovered
all 5,248 associated source fits for collision 0 and all 10 for collision 68; no
orphan fit was assigned to a collision. Field conditions were retrieved through
CCDB's official HTTP alternatives (nominal −5 kG). Native O2 numeric checks covered
100 real barrel states; constant-field propagation agreed within 3.3 micrometres
over a 5 cm local-X step. AO2D paths remain explicitly approximate fit projections
without material corrections, measured clusters or forward dipole transport.

Component indices were verified against every original placement in all 16
run-560067 aligned assets (including L3), without modifying any `.blend`. Qt and
Blender checks exercise shared ITS layer prototypes, TPC inner walls, mask
restoration, simplified geometry, AO2D feature colouring and portable export.
These geometry assets are not presented as run-572669 alignment. See
[AO2D](AO2D.md) and [components](SCENE-CONFIG.md#detector-component-categories).

The TPC sectors/inner-wall preset retains exactly 254 native placements (216
readout-sector chambers and 38 inner-wall/shield placements), removing 10,062
other placements without changing data or clipping bounds. A surround-light rig
adds eight side and two end area lights while retaining existing lights. Native
Blender QA verifies light aim, repeated-button idempotence, camera preservation
and component/light export. It also verifies that newly orbit-built cameras
record their updated world transform, avoiding stale identity rotation in render
history. A separate exterior CPU render confirms coherent, illuminated blue TPC
surfaces against a black background; this is visual validation, not a physics
check.

The same corrected raw vertex at index 5 rendered with the user's original
camera, this reduced TPC selection and twelve area lights (two existing plus
the surround rig). The 640 × 360, 64-sample CPU result is
`renders/qa/tpc-sectors-surround/render-20261011-204313-6961c3/event-00000/render.png`;
the tested portable settings are in
`configs/event-5-tpc-sectors-inner-wall-surround.json`. Camera matrix, component
choices and lights match the render metadata exactly. The interior is brighter
but still translucent; other selected detector surfaces retain layered patterns.
This is not a claim of an exact match to the commissioning reference.

The subsequent interactive-session check found that the last launched job still
used the earlier startup preset (two lights, no explicit TPC part selection).
The shipped startup preset now contains the reduced TPC selection and surround
rig, and the TPC browser opens on Parts. Native QA counts exactly 254 evaluated
TPC instances in the interactive dependency graph, verifies restoring scene
lights/world after intentionally choosing studio lighting, and checks the
sidebar's Show scene lighting operator. An additional opaque-default exterior
CPU image confirms illuminated surfaces at the default exposure, independent
of the earlier transparent material example.

Cached [large surfaces](LARGE-SURFACES.md) now offer 192 ITS stave panels in seven
meshes and 257 reduced TPC wall/sector elements in 21 meshes. Native checks
verify exact full aligned clipping-plane parity, layer/wall and original-name
masks, outward ITS normals, no full Blender-container parsing, and the actual
editor switch/export. A separate cold geometry-only load took 0.12 seconds on
this Mac. The final corrected-cache real-event preview is
`renders/qa/large-surfaces/render-20261011-223851-e78058/event-00000/render.png`
(640 × 360, 64 samples, CPU, 17.5 seconds). The user's portable scene is
`configs/fast-its-tpc-large-surfaces.json`, also registered as the local favourite
**Fast ITS/TPC · 90° · outer wall + lights**. These broad surfaces are a display
approximation; they do not reproduce the reference's fine lattice structures.
