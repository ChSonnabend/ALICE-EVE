# SUEP selections and MC/reconstructed rendering

Scripts in this directory identify candidate SUEP pion showers, follow both mother
links through all descendants, and join saved MC labels to renderer track IDs.
MC indices, native reconstructed GlobalTrackIDs, and AO2D row IDs are different
namespaces. Never paste MC indices as reconstructed IDs.

## Supplied dataset and selection policy

The supplied 042/tf1 sample has event-level SubgenId 0 for a mixed Pythia+HepMC
cocktail. All 255,131 generator particles have zero in the proposed three cocktail
source bits. Their generator of origin therefore cannot be recovered from those
bits. In all 211 generator events, motherID=-1 selects only protons. Transport
adds motherless electrons/positrons, but no motherless pions.

The user-authorized alternative is an explicitly labelled **burst heuristic**:
select at least 20 sibling PDG 999999 pions from one parent, then all descendants.
The observed parents have PDG 25. The pions, not the scalar or incoming protons,
are the selected roots. This is a topology-based inference, not proven HepMC
provenance. Reports record the parent, multiplicity and individual root IDs.
The threshold and pion PDG are configurable; no generic high-PDG-number rule is
used (large PDGs can also denote nuclei or transport pseudo-particles).

## AO2D: ready-to-load reconstructed highlights

Run with the renderer's Python environment; no O2 is required:

    python3 projects/SUEP/select_ao2d.py --input /path/AO2D.root \
      --subgen-id 0 --pion-pdg 999999 --burst-min 20 --output /path/new-selection

Outputs:

- event-highlights.json: exact renderer collision IDs mapped to fitted track IDs.
- renderer_tracks.csv: event ID, renderer ID and matched MC row/collision.
- mc_particles.csv: selected truth rows, PDGs and root flags.
- selection-report.json: reproducible criteria, bursts and omissions.

Fake/noise MC labels and unassociated reconstructed tracks are excluded. The
exporter uses the renderer's AO2D table resolution and ID formats. Reconstructed
parents that do not exist as fitted tracks cannot be highlighted; their fitted
daughters can. AO2D trajectories still require the run's signed magnetic-field
conditions, as described in docs/AO2D.md.

## Native Kine selection

Activate matching O2/PyROOT, for example:

    cd ~/alice/MyO2
    alienv enter O2PDPSuite/latest-o2
    cd /path/to/ALICE-EVE

Audit generator headers and ancestry:

    python3 projects/SUEP/select_tracks.py --kine /path/genevents_Kine.root \
      --inspect --root-pdg 999999 --output /path/new-audit

Select the supplied sample's pion bursts in the transported stack:

    python3 projects/SUEP/select_tracks.py --kine /path/sgn_Kine.root \
      --subgen-id 0 --root-pdg 999999 --root-policy burst --burst-min 20 \
      --output /path/new-selection

The default root policy remains motherless; burst and pdg explicitly relax it.
Non-heuristic selection requires a per-particle HepMC membership JSON (MC event
index -> root-candidate track indices), a verified cocktail source tag, or an
explicit --pure-hepmc-events assertion. Never use the pure-event assertion for a
mixed cocktail. --cocktail-source-id reads hybridCode's encoded status bits 19–21
only when the encoding marker is valid. It is separate from --mc-source-id, the
embedding source namespace. Untagged old files cannot distinguish source zero
from the first tagged generator. Transport secondaries are selected by ancestry.

mc_tracks.csv contains (MC source, MC event, MC track), PDG, both mother indices,
root flag and SubgenId. Use sgn_Kine.root for reconstructed label joins; do not
assume pre-transport genevents indices survive stack filtering unchanged.

Export PV-associated native reconstructed labels for one TF:

    python3 projects/SUEP/export_reco_labels.py --input /path/tf1 \
      --output /path/reco-labels.csv

The built-in readers cover ITS, TPC, MFT, ITS–TPC, TRD and TOF matched sources.
Other/missing sources, invalid labels and fake labels are reported. Optional
--readers JSON maps a source name to [filename, tree, label branch]. --entry
selects the ROOT TF entry. MC source IDs must agree with collisioncontext.root.

Add --reco-labels and --event-map to select_tracks.py to produce native renderer
CSV and JSON highlights. The event map is a JSON object mapping that TF's PV
indices to the exact exported collision IDs, for example:

    {"0": "RUN:TF:ORBIT:0", "1": "RUN:TF:ORBIT:1"}

Do not use native reconstructed IDs with AO2D scenes, or MC event indices as PV
indices. Process each TF separately; merge mappings only with unique event IDs.

## MC transport paths

    python3 projects/SUEP/export_mc_tracks.py --kine /path/sgn_Kine.root \
      --selection /path/new-selection/mc_tracks.csv --events 0 1 \
      --output /path/new-mc-events

Omit --events to export all MC events. The script exports all drawable tracks as
background context and marks the selected descendants for emphasis. It writes
compressed event files plus adjacent -highlights.json and -report.json sidecars.
Open the event folder and choose **MC truth** under Track representation.

MC paths connect saved TrackRefs in transport-length order, starting at the
production vertex. These are sparse polylines, not reconstructed fits or exact
continuous transport paths. Particles with no drawable references, including
many already-decayed parent pions, are counted as omitted rather than given
invented trajectories. This route cannot recreate missing transport history.

For reconstructed data choose **Reconstructed tracks**. Both desktop Appearance
and the Blender sidebar expose this choice. A dataset containing both collections
can switch in place: its main tracks collection is identified by
track_representation; optional mc_tracks/reconstructed_tracks hold the other
representation. Selecting an absent representation gives an explicit error.
The standalone MC event export and AO2D input are separate datasets; load the
appropriate input before switching. MC events and reconstructed PVs need not
have a one-to-one correspondence.

## Event-specific highlighting, including video

Desktop Appearance and Blender's Track emphasis / decay chain offer a JSON text
field and **Load event highlights JSON**. The format is:

    {"exact-event-id": ["track-id", "another-track-id"]}

Lists are resolved independently at each collision, including playback and final
video/still renders. They are embedded in saved scene configs. The old Special
track IDs field is global and adds IDs to every event; leave it empty for purely
event-specific selection. Associated clusters follow their explicit track_id;
MC truth-only exports do not invent clusters.

## SoftBombs scene

`SoftBombs.json` is the portable visual recipe based on the reviewed
`video-20261013-125740-7c5a44` geometry, camera, detector presentation and lighting.
TRD and TOF show both tracks and clusters. Normal track linewidth is **2 cm**;
selected SUEP pions and their descendants use **5 cm** (stored radii 1 and 2.5 cm).
Cluster scale factors and detector colours follow the reference scene.

For the supplied simulation, use the reconstructed TF export
`data/SUEP/042/renderer-tf1`, not its AO2D: this preserves TRD tracklet points and
TOF clusters. The export reuses the saved primary vertices and reconstructed
products, with the original simulation HBFUtils timing. The local **SoftBombs**
favourite includes the matching event-highlight map. The portable recipe does
not embed this dataset's IDs; load its TF-specific event-highlights JSON when
using the portable file. AO2D highlight IDs do not match native TF tracks.

Load the TF export folder, select **SoftBombs → Use favourite**, and begin with
one collision for an interactive scene or a small selection for playback.
The ALICE general favourite shares the updated reference scene settings.

## Validation

Unit tests exercise ancestry, proton-root exclusion, burst selection, label
namespace joins, and event-specific ID isolation. Native Blender QA checks
highlight changes during collision playback. The supplied TF was used for a
full-stack burst selection and native label extraction; its merged AO2D was used
for renderer-ready highlights. Two transport-reference MC events were exported
for a real rendering check. These checks do not establish physics purity of the
burst heuristic; use generator provenance for that when available.
