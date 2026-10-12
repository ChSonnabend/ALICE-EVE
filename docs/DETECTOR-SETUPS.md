# Detector setups and rendering progress

In **Appearance → Detector setup**, select ALICE2, ALICE2 + ITS3, or ALICE3 and
press **Apply detector setup defaults**. ALICE2 is the fresh-install default.
Existing saved settings still take priority until a setup is applied.

The ALICE2 recipe comes from `renders/editor-20261012-130704-860001/scene-config.json`:
camera pose, lights, 90-degree ITS/TPC openings, detector colors and appearance are
preserved. The packaged recipe has no event or machine-specific path defaults.
The upgrade recipes copy that camera and lighting; TRK inherits the ITS color
and opening, and other systems inherit corresponding detector color roles.

ALICE2 uses the existing run-560067 aligned geometry. ALICE2 + ITS3 replaces the
ITS asset with the nominal installed O2 **ALICE2.1** geometry, including its outer
tracker, and retains the other ALICE2 assets. ALICE3 assets are generated from the
installed official O2 **ALICE3** detector list. These are tessellated first-solid
material surfaces from nominal simulation geometry, not a promise that this
particular O2 revision is the final engineering design or real-data alignment.
Each bundle records the source ROOT hash. All generated placements are retained.

ALICE3 has its own detector identifiers and contains no TPC. The ALICE3 preset
selects geometry only: loading ALICE2 data does not invent ALICE3 hits. The ITS3
comparison with ALICE2 tracks is a visualization, not a new reconstruction.
Component selections specific to ITS2 are cleared for the replacement ITS3 asset.

Regenerate upgrade assets in the loaded O2 environment:

```sh
python3 tools/prepare_detector_geometry.py --setup ALICE2.1 \
  --work /local/new-its3-build --output geometry/alice2-its3 --blender /path/to/blender
python3 tools/prepare_detector_geometry.py --setup ALICE3 \
  --work /local/new-alice3-build --output geometry/alice3 --blender /path/to/blender
python3 tools/update_detector_presets.py --source /local/exported-scene-config.json
```

These commands use O2's `o2-sim --detectorList ... -n 0`, ROOT tessellation, and
Blender instancing. No external converter is required for the upgrade assets.
The installed O2 must include the upgrade detector modules.

Rendering remains Cycles ray tracing. **Structural** geometry is an explicit,
fixed LOD approximation. There is no automatic pixel-footprint LOD or rasterizer
that removes fine ITS details based on output resolution. Upgrade assets currently
use full tessellated design surfaces.

The desktop has a progress bar; the CLI emits stage messages and integer render
percentages, and the Blender sidebar monitors the separate full-render process.
Progress is based on Cycles sample reports and logged when its integer value
advances. Blender may skip percentages for fast renders or adaptive sampling.
Scene preparation/indexing remain indeterminate stages. 100% is emitted only
after successful process exit and verification that the output PNG exists.
`blender.log` preserves the detailed statistics; interactive full renders use
individual `full-render-<timestamp>.log` files.
