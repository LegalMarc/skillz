# pill_organizer_10bay

A gravity-fed bench organizer for ten supplement pills. Pour a bulk charge into
each hopper at the back; it feeds forward into an open pick tray at the front.
Lift one lid and all ten types are exposed.

**Two lids total.** Both fill ports at the back under one flat lid, both pick
rows at the front under one sloped lid.

**Revision 3.** Same topology as revision 2, with a 40-degree ramp instead of
48 and a 20-degree *porch* under tray B, which take the envelope from 9.45 L to
5.54 L. Tray A's rim then drops to 42 mm, steepening the single pick plane to
38.7 degrees so the front tray is a 21 mm reach rather than a 32 mm one, and the
wall between the two fill mouths leans forward so you pour into openings of
roughly the same size.

## What it is

| | |
|---|---|
| Overall | 235 x 170.8 x 141 mm (the 235 includes the 5 mm joining rail) |
| Bays | 10, two rows of 5, 42.96 mm clear each |
| Capacity | **293.0 mL/bay front row, 191.6 mL/bay back row** — 2.42 L total |
| Printed parts | **3 designs, 3 pieces**, no hardware |
| Validation | **13 passed, 0 failed, 4 n/a, 0 inconclusive, 1 advisory** |
| Confidence | Tier 2 — geometry verified, fit uncalibrated |

A 90-day once-daily size-00 charge is 147.4 mL, so the front row carries 179
days and the back row 117.

## The one thing to understand before printing

Grouping both ports at the back and both trays at the front **forces one feed to
cross the other**, and the space under that crossing chute can never hold pills.
It is a third of the printed section and no geometry removes it: the floor has
to fall toward its outlet at the angle of repose or steeper at every point, so
it can never sit below a straight line drawn at that angle from tray A. A
curved floor was considered and rejected — it gains volume that fills once and
never discharges.

What revision 3 does instead is shrink the box around the wedge.

## How it works

- **Row B** is the simple one. Its mouth is directly behind its tray; a plain
  40-degree ramp feeds it.
- **Row A** is the crossing. Its mouth is at the *back* but its tray is at the
  *front*, so its chute ducks under tray B and under hopper B's ramp — 105 mm
  enclosed. That chute is not wasted: it *is* row A's storage, which is why the
  front row holds half as much again as the back row.
- **The porch.** Under tray B, and only there, the chute floor runs at 20
  degrees instead of 40. The 40-degree climb then starts 30 mm further back, so
  hopper A's floor and hopper B's floor both drop about 25 mm, and tray B's
  floor lands on tray A's rim.
- **The porch is shallower than the angle of repose**, so it carries a stagnant
  wedge — about 4 mL per bay, 2.8% of a charge, that fills once and stays. The
  flow channel over it is 29.5 mm, which is 1.1x a capsule's length and 2.7x its
  diameter, so nothing bridges. That is the whole price of the flush line.
- **The front tray is a parts bin, not a well.** Pills pile to 39 mm at the
  chute mouth and slope forward to about 23 mm at the front wall. The lid plane
  has to stay at 42 mm — its back end is pinned to tray B's rim, and a lower
  front end cuts the wall between the trays below what stops tray B spilling
  forward. So the front WALL drops instead: scalloped to 30 mm across each bay,
  leaving the dividers and both side walls at the plane to carry the lid. The
  reach over that wall is **7.2 mm**. With the lid off, tray A is open at the
  top and open at the front; with it on, the lid's 18 mm skirt hangs down the
  outside and the scallops are invisible.
- **The wedge under the chute is an accessory cubby.** It can never hold pills,
  so it holds everything else — a splitter, a funnel, the spare lids. One void
  the full inner width, 70 mm deep, 42 mm tall at its shallow end and 103 mm at
  the back, opening through the **back face only** so both side walls stay full.
  Its ceiling runs parallel to the chute floor above it, so it self-supports
  instead of bridging, and a 28 mm lip across the opening keeps the contents in
  when you slide the module about — 72 mm of clear opening remains above it.
  1.1 L of what was solid infill is now usable space.
- **The fill mouths are 62 and 40 mm, about 3:2.** The wall between them leans
  8.8 mm forward at the rim (17.3 degrees from vertical), pivoting where it
  springs off the chute ceiling so hopper B's ramp is untouched. Left vertical
  the split was 70 : 32, which is what you get from equalising the two rows'
  volumes rather than the openings you actually pour into.
- **The splitter rib.** Tray B's floor is carried on the bay dividers alone —
  the chute runs underneath, so the tray's own walls never reach it. At 20
  degrees that underside is a near-flat ceiling bridging the whole bay, so a
  2.4 mm fin runs down the middle of each porch and halves the span to 20.3 mm.
  Its upstream edge is knife-tapered. Pills run single file through the porch.

## Two things that were forced, not chosen

**Neither lid is hinged.** The two tray rims are 49 mm apart, so a lid
bridging them as an L has its mass centre well below any back-top pivot and
falls shut every time; a front pivot runs the far corner into the benchtop. The
pick lid lifts off, hung on a lip that hooks over the module's front top edge:
PLA on PLA grips to about 17 degrees and the pick plane is 32.

**The pick surface is one sloped plane, not two steps.** A lid spanning two
steps is a Z in section, and a Z cannot be printed without support whichever way
it is laid. Every wall over both trays dies on that plane.

## Bill of materials

| Part | Qty | Print orientation |
|---|---|---|
| `body` | 1 | as modelled, flat on its base, no supports |
| `pick_lid` | 1 | rotated 38.7 deg so the plate lies flat, skirt upward |
| `fill_lid` | 1 | flipped, plate top face on the bed, tabs up |

Print-ready STLs are in `build/print_ready/`, already rotated and dropped to
z = 0.

## Print this first

`calibration_coupon.scad`. `doctor.py` reports no calibration profile on this
machine, so the snap and rail fits are geometry-only.

## The bench maquette

`test_model.scad` renders the whole module at `TEST_SCALE = 0.42`, about
99 x 72 x 59 mm — roughly a coffee mug's footprint. STLs are in
`build/maquette/`.

It is a **form model, not a function model**. Proportions, the flush
rim-to-floor line, the crossing chute and both lid planes all read true, but a
size-00 capsule does not fit any bay and the fill lid's snap tabs come out
around 0.5 mm thick. Print it to judge the shape and to see whether the porch
ceiling and the 50-degree chute ceiling come out clean; do not judge the flow
from it.

## Reviewer's attention

- **Nothing in this revision moves**, so there is no motion sweep.
- The chute ceiling on the 40-degree leg is a **50-degree-from-vertical
  overhang**, past the conservative 45-degree rule. It is internal and
  non-cosmetic, and `chute_clear` carries a sag allowance. If the test print
  shows droop, the fallback is a gabled ceiling.
- **Porch lanes are 20.3 mm.** Pills run single file. The rib's knife edge is
  what keeps a capsule arriving crosswise from stopping at it.
- Bay width is **1.65x the longest pill** against a 2–3x mass-flow rule of
  thumb. Mitigated, not eliminated; an occasional tap may be needed.
- The two `NEAR MISS` notes (0.150 mm, 0.170 mm) are both lids' intended
  clearance, explained in `joints.json`.

## Build and verify

```sh
source ~/.local/opt/openscad/env.sh
cd scad-workbench/projects/pill_organizer_10bay
~/.local/src/openscad-cad-skills/scad-modeler/scripts/validate_scad.sh --all
python3 ~/.local/src/openscad-cad-skills/scad-modeler/scripts/check_rules.py --project-dir .
../../render.sh assembly.scad build/prev_asm
```

## Confidence

Tier 2 — geometry verified, fit uncalibrated. Every assert in `params.scad`
passes, all three parts render as single watertight bodies at their declared
bounding boxes, both chute legs are walked end to end by `bores.json` in both
end bays, and the static assembly is collision-free. What is *not* verified: any
clearance as a real printed fit, and any claim about how pills actually flow.
