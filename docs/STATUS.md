# Validation status — 11 October 2026

## Implemented

The native desktop application lists individual collisions and supports detector selection, tracks/clusters/both, scalar and solid colours, independent geometry and L3, preview and full Blender renders. Tracks-only is the default. Data, truth labels and colours that are unavailable remain disabled or explicitly unknown.

The Virgo integration now reconstructs raw TFs and full-detector CTFs, exports every primary vertex without display quotas, retains failed propagation and invalid coordinate diagnostics, and checks every event against an independent O2 inventory. Original PV-reference IDs and cluster associations are audited separately. Component fits are retained instead of being consumed by O2's display iterator; MCH–MID matches are handled as matches rather than standalone track storage.

## Real-data evidence

All checks use run **560067**, TF counter **2619419**, first orbit **212036032**. The raw input is 696,782,440 bytes. A 137,517,804-byte full-detector CTF was generated from that real raw TF and used to validate the CTF route.

- Final raw-TF export: **55 collisions**, **399,127 drawable tracks**, **4,568 preserved propagation failures**, **19,360,314 cluster associations**. Full schema validation and original-track-reference checks passed for every event. No fitted-track reference is missing or extra. The remaining reference types are timing/calorimeter/CPV signals retained by the independent inventory and whole-TF archive.
- Final CTF export: **56 collisions**; independent TF/PV enumeration and both end-of-stream markers agree. **333,156 drawable tracks**, **451 preserved propagation failures**, **18,524,219 cluster associations**; complete object/reference audit passed. Thirteen nonfinite HMP measurements are retained in the whole-TF archive as non-renderable diagnostics.
- Earlier reconstruction attempts produced 54–57 vertices. Raw and CTF reconstruction vertex sets differ; this project verifies each export against its own reconstruction rather than asserting physics equivalence between routes.
- The desktop-to-Virgo bridge completed a separate real CTF import end to end, including condition checks, reconstruction, compression, retrieval, inventory reconciliation and geometry reuse.
- All **15 detector systems plus L3** were built as aligned assets, covering **1,418,318 physical surface instances**. Every translation passed at stored precision; maximum rotation-matrix entry error was **2.07 × 10⁻⁷**. All surface hashes match the exact geometry manager captured during the final raw and CTF reconstructions.
- Actual real-data CPU preview and Apple Metal renders passed. Separate selected events have independent PNG/configuration/log/Blender outputs. A global-Y cutaway clips geometry rather than relying on long transparent ray chains. The camera uses ALICE +Y as up.
- Actual GUI import, selection, geometry auto-fill, scalar availability and Preview-button execution passed. No MC truth is fabricated.
- **59 automated tests passed**, including atomic caches, complete enumeration, flow control and private socket namespaces. Python source compilation and native exporter compilation passed.

The verified datasets are `data/validated/run560067-raw-v9` and `data/validated/run560067-ctf-v11`. Their manifests, enumeration reports, object audits and geometry reports retain the evidence. Earlier exports remain available for comparison. Current assets are under `geometry/run-560067`; real render evidence is under `renders/qa/real-data`.

## Portable scenes and editor

Versioned portable scene export/import, local input/event overrides, geometry hash verification, hardware quality presets and the `render-config` command are implemented. Blender's interactive ALICE EVE sidebar supports camera capture, lights, detector openings, colour coding, transparency, materials and background, with separate Export config and Render full buttons. The editor now preserves the requested geometry detail. Full aligned surfaces match the physical structures used in the reference renders; hidden Geometry Nodes helpers stay hidden in the viewport, and blended transparency avoids hashed speckles. Optional shell/outline and opaque controls persist in configs. The optional simplified geometry uses at most 256 coarse spatial cells per detector. These cells are approximate bounds, not full physical surfaces.

A real TPC asset was reduced from 10,316 instances to one 256-cell mesh. Headless Blender editor registration, live property updates, camera/light export and scene reload passed. The exported scene rendered on CPU and Apple Metal with a different selected event; the scene settings remained intact. The desktop config-load controls and the editor's Render full operator passed; the latter completed a separate CPU render. A portable config also rendered a validated real collision with simplified ITS, TPC and L3 on Metal. Blender QA also checks hidden instancing helpers, blended viewport materials, switching full/shell/outline modes, opacity and config export. Real CPU renders verify full and outline display modes. Cross-platform config relocation/hash checks and event selection are automated tests. Linux/NVIDIA/AMD rendering remains a hardware-validation limit.

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

O2 runs inside the user-provided Virgo allocation **16999956**, on **ccwks0001**, with ROOT **6.36.10** and the installed `nn_momentum_vector-local1` O2 suite. Commands use unique positively numbered steps; the original **16999956.0** is preserved. DPL socket namespaces are also unique because session/shm IDs alone do not isolate the allocation-wide metric-feedback socket.

Only the project and its isolated remote work directory are modified. Original TF/CTF inputs, the old renderer and O2 checkouts remain unchanged. Conditions are checked from the generated workflow and pinned through the public CCDB HTTP cache. This is rendering validation, not certification of a production reconstruction pass.

The user authorized dropping the unreliable helper. Current source inspection and QA are performed directly, without helper-session dependence.
