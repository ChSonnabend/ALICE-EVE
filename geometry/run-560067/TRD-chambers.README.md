# TRD chamber cutaway asset

This alternate display asset exposes all six radial TRD chamber layers. The original `TRD.blend` remains available and unchanged. The ITS-TPC favourite selects this alternate asset; ALICE general continues to use the original.

It contains 521 actual chamber assemblies and 3,647 aligned external chamber-component placements, shared across 150 meshes. The aluminium supermodule skin and internal electronics are omitted for visibility. These are geometry-derived chamber surfaces, not schematic concentric shells. Units are metres, in ALICE global XYZ coordinates.

The source is the aligned ROOT geometry supplied with run560067-ctf-v16. Its SHA-256 is recorded in `TRD-chambers.provenance.json`; it differs from the ROOT snapshot used for the original bundle. Do not treat the alternate display asset as an identical replacement alignment for the original snapshot. Component bindings and transform checks are recorded in the accompanying metadata and QA file. The six layer centres span approximately 2.96–3.61 m radius.
