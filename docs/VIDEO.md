# Collision videos

Load an input and select at least two **collision** events. In the **Video** tab,
enable **Play / render selected collisions as a video**. **Play collisions…**
opens a looping Blender session; **Preview video** exports a small MP4;
**Render video** asks for resolution, samples, geometry detail and hardware,
then writes `video.mp4` in the reported output folder.

The Blender **ALICE EVE → Collision video** box contains **Play collisions** and
**Stop video**. Stop pauses immediately at the current frame. Play resumes;
reaching the end loops to the first selected collision. Camera, lights, colours,
detector surfaces and data choices can be edited during playback or while paused.
**Export config** saves these settings, including video controls. **Render full**
renders all selected collisions with the exported camera and chosen quality.

## Timing and growth

| Control | Meaning |
| --- | --- |
| One collision per fixed interval | Selected collisions appear in catalogue order, spaced by the chosen interval, such as 1 or 5 seconds. |
| Scaled collision timestamps | Collisions are sorted chronologically; measured collision time gaps are multiplied by the scale. |
| Time scale = 0 | Automatically fit the first-to-last gap to `N − 1` video seconds: about one arrival per second on average. Uneven real gaps remain uneven. |
| Positive time scale | Video seconds per source second. For example, 1,000 maps a 1 ms collision gap to 1 video second. |
| Event interval / final hold | Fixed-mode spacing; in either mode, how long the final collision stays before the movie ends or playback loops. |
| Propagation | Metres travelled along a fitted trajectory per **video second**. Default: 10 m/s. Try 5 m/s for slower ITS/TPC growth. |
| Tower rise time | Seconds after arrival to grow from the anchored cell footprint to the configured tower height. Default: 0.2 s. |
| Video FPS | Encoded frames per second, default 24. Also controls viewport playback updates. |

Each new collision replaces the preceding collision's tracks, clusters and towers.
Geometry and camera stay fixed. Track geometry grows outward from the endpoint
nearest the primary vertex, including the vertex-to-first-sample distance in its
clock. No unmeasured vertex connector is drawn. Only selected track sources and
detector extent masks are used; clipping remains enabled in video mode. These
aligned outer envelopes are display bounds, not an active-volume reconstruction
or an individual sensor-hit test, just as in still renders.

Clusters with an explicit `track_id` appear when propagation reaches the nearest
point of their associated sampled path, plus the residual distance to the cluster.
This also works when that parent track's display is disabled. Calorimeter cells
and other clusters without a track association use a primary-vertex distance
wave at the same display speed; the framework does not invent a track match.
Towers then grow gradually, using their selected linear/logarithmic signal mapping,
size, direction and height limits. These are visual timing choices, **not measured
particle time of flight**. The movie metadata records both timing bases and the
numbers of linked and unlinked objects for each collision.

Timestamp mode uses native O2 first-TF orbit plus PV time, AO2D global BC plus
collision time offset, or explicit absolute collision timestamps. AO2D inputs
are re-cached with the extra clock fields. Calibration validity timestamps are
not substituted for collision timestamps. Missing clocks, incompatible runs
without absolute timing, or coincident timestamps with automatic scaling produce
a prerequisite message; use fixed intervals or an explicit positive scale.
The orbit/BC conversions follow the official
[O2 LHC clock constants](https://github.com/AliceO2Group/AliceO2/blob/dev/Common/Constants/include/CommonConstants/LHCConstants.h).

Arrival times are quantised to frames. If collisions would share a frame, they
are assigned successive frames so none is skipped; `video-timeline.json` records
requested and rendered arrival times. Very short holds may end before all
trajectories or towers finish growing. Increase the interval/scale or propagation
speed as appropriate. Slow viewport scene loads may lengthen wall-clock playback;
the exported movie follows its exact frame schedule. Colour ranges are fixed
across the selected collisions unless explicitly set in the config.

## Portable movie render

The event selection stays outside the portable scene recipe. Export a video-enabled
config and run a single command on the rendering machine:

```sh
alice-render render-config scene.json --input /local/events.jsonl.gz --events ordinal:8,ordinal:36 --geometry-root /local/geometry --quality final --resolution-percent 25 --backend AUTO
```

Use `edit-config` with the same input and selections for looping playback.
`--events` also accepts full collision IDs. Ordinals are zero-based. For raw
TF/CTF inputs, provide the reconstruction `--profile`; AO2D needs its magnetic-field
conditions as for still rendering. A local `--event-files selection.local.json`
can instead supply a JSON array of materialized event paths (relative paths are
resolved beside that list). The Blender Render full button supplies this local
selection automatically; it is not exported into the portable recipe.

Encoding uses H.264 MP4, CRF 18, without audio. Odd pixel dimensions are padded to
even dimensions. `imageio-ffmpeg` is installed with the framework and supplies a
portable encoder on [supported wheel platforms](https://github.com/imageio/imageio-ffmpeg#installation); otherwise a working system
FFmpeg is required. `--ffmpeg /local/ffmpeg` selects one explicitly. Encoder startup
and H.264 support are checked **before rendering frames**. CPU/Metal/HIP/CUDA/OptiX
are still selected through the existing Blender render-device checks; video
encoding is independent of that choice.

The output includes `video.mp4`, a first-collision poster `render.png`, portable
`scene-config.json`, `video-timeline.json`, metadata and logs. Optional `scene.blend`
is a snapshot of the poster frame; re-open the movie through the framework to
rebuild playback. Frames stream into the encoder; they are not all retained as
large PNGs. Desktop cancellation stops both Blender and its encoder.
