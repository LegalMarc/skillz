# pill_organizer_10bay

A gravity-fed bench organizer for ten supplement pills. Pour a bulk charge into
each hopper at the back; it feeds forward into an open pick tray at the front.
Lift one lid and all ten types are exposed.

**Two lids total.** Both fill ports at the back under one flat lid, both pick
rows at the front under one sloped lid.

**Revision 6.** Six revisions, twenty-five recorded decisions — `plan.md` has
the table. Revision 3 took the envelope from 9.45 L to 5.54 L with a 40-degree
ramp and a shallow *porch* under tray B; revision 4 fixed reach and pour,
dropping the front wall to a scalloped 30 mm and leaning the hopper divider to
even the two fill mouths; revision 5 turned the dead wedge under the chute into
an accessory cubby and added tape labels; revision 6 is what an independent
review found wrong with revision 5 (a joining groove that could not be entered,
a snap catch 0.7 mm thick, label recesses 9 mm tall for a 12 mm tape, a cubby
ceiling past the overhang limit) plus the porch at 25 degrees, finger notches
on the pick lid, a pull lip on the fill lid, and foot pads. `INCIDENTS.md`
has each one with the probe that found it.

## What it is

| | |
|---|---|
| Overall | 235 x 170.8 x 141 mm (the 235 includes the 5 mm joining rail) |
| Bays | 10, two rows of 5, 42.96 mm clear each |
| Capacity | **290.2 mL/bay front row, 182.4 mL/bay back row** — 2.36 L total, geometric maximum |
| Printed parts | **3 designs, 3 pieces**, no hardware |
| Validation | **13 passed, 0 failed, 4 n/a, 0 inconclusive, 1 advisory** |
| Confidence | Tier 2 — geometry verified, fit uncalibrated |

A 90-day once-daily size-00 charge is 147.4 mL, so the front row carries 177
days and the back row 111.

## The one thing to understand before printing

Grouping both ports at the back and both trays at the front **forces one feed to
cross the other**, and the space under that crossing chute can never hold pills.
It is a third of the printed section and no geometry removes it: the floor has
to fall toward its outlet at the angle of repose or steeper at every point, so
it can never sit below a straight line drawn at that angle from tray A. A
curved floor was considered and rejected — it gains volume that fills once and
never discharges.

What revisions 3–5 do instead is shrink the box around the wedge, then put
the wedge to work.

## How it works

- **Row B** is the simple one. Its mouth is directly behind its tray; a plain
  40-degree ramp feeds it.
- **Row A** is the crossing. Its mouth is at the *back* but its tray is at the
  *front*, so its chute ducks under tray B and under hopper B's ramp — 105 mm
  enclosed. That chute is not wasted: it *is* row A's storage, which is why the
  front row holds half as much again as the back row.
- **The porch.** Under tray B, and only there, the chute floor runs at 25
  degrees instead of 40. The 40-degree climb then starts 30 mm further back, so
  hopper A's floor and hopper B's floor both drop about 22 mm, and tray B's
  floor lands just above tray A's rim.
- **The porch is shallower than the angle of repose**, so it carries a stagnant
  wedge — about 2 mL per bay, 1.5% of a charge, that fills once and stays. Pills
  reach the tray by flowing over that wedge, whose surface is at repose, so the
  last 30 mm feeds the way any pile discharges: at the repose angle, not with
  the ramp's 10 degree margin. The channel over the wedge is 32.6 mm with the
  30-degree estimate and still 28.9 — over one capsule length — if the real
  figure is 35. Revision 5's 20-degree porch closed that to 25.8 at 35, which
  is why it moved.
- **The front tray is a parts bin, not a well.** Pills pile to 39 mm at the
  chute mouth and slope forward to about 23 mm at the front wall. The lid plane
  has to stay at 42 mm — its back end is pinned to tray B's rim, and a lower
  front end cuts the wall between the trays below what stops tray B spilling
  forward. So the front WALL drops instead: scalloped to 30 mm across each bay,
  leaving the dividers and both side walls at the plane to carry the lid. The
  reach over that wall is **7.2 mm**. With the lid off, tray A is open at the
  top and open at the front; with it on, the lid's 19 mm skirt hangs down the
  outside and the scallops are invisible. Two rounded finger notches in the
  skirt, under bays 2 and 4, are what you lift the lid by — straight up.
- **The wedge under the chute is an accessory cubby.** It can never hold pills,
  so it holds everything else — a splitter, a funnel, a bottle of the next
  refill. One void the full inner width, 70 mm deep, 33 mm tall at its shallow
  end and 103 mm at the back, opening through the **back face only** so both
  side walls stay full. Its ceiling is a 45-degree plane, the conservative FDM
  overhang limit, and a 30 mm lip across the opening — level with the shallow
  end — keeps the contents in when you slide the module about; 73 mm of clear
  opening remains above it. About 1.1 L of what was solid infill is usable
  space. (The lids do not fit in it: the fill lid is 113 mm deep.)
- **The fill mouths are 62 and 40 mm, about 3:2.** The wall between them leans
  8.8 mm forward at the rim (17.3 degrees from vertical), pivoting where it
  springs off the chute ceiling so hopper B's ramp is untouched. Left vertical
  the split was 70 : 32, which is what you get from equalising the two rows'
  volumes rather than the openings you actually pour into.
- **The splitter rib.** Tray B's floor is carried on the bay dividers alone —
  the chute runs underneath, so the tray's own walls never reach it. At 25
  degrees that underside is a shallow ceiling bridging the whole bay, so a
  2.4 mm fin runs down the middle of each porch and halves the span to 20.3 mm.
  Its upstream edge is knife-tapered. Pills run single file through the porch.
- **The fill lid snaps in and pulls out.** Two cantilever tabs latch behind a
  2.7 mm catch in the front and back walls. Their barbs have a 35-degree return
  face, so a deliberate pull releases the lid every refill instead of breaking
  the catch, and a knock does not. A 30 mm pull lip on the lid's front edge
  stands out over tray B, through a notch in the wall in front of the mouth,
  so there is something to pull. The notch stops at the seat plane: with the
  lid on, nothing below it is open.
- **Foot pads.** Four 10 mm recesses in the base take stick-on rubber feet, so
  a unit that is bumped while pouring does not skate.
- **Ganging.** Two dovetail rails on the left face, two grooves on the right.
  Lift the pick lid off the left-hand unit, lower the right-hand unit's rails
  in from above. Revisions 3 to 5 had the front groove capped by the side wall,
  so this could not be done; it is open through the pick plane now, and the lid
  covers the opening in use.

## Two things that were forced, not chosen

**Neither lid is hinged.** The two tray rims are 51 mm apart, so a lid
bridging them as an L has its mass centre well below any back-top pivot and
falls shut every time; a front pivot runs the far corner into the benchtop. The
pick lid lifts straight off — its skirt hangs down the module's front face and
stops it sliding down its own slope: PLA on PLA grips to about 17 degrees and
the pick plane is 40. It lifts straight, not tilted: its back edge is 0.35 mm
from the wall behind tray B and the top-back corner meets that wall after 5
degrees of tilt.

**The pick surface is one sloped plane, not two steps.** A lid spanning two
steps is a Z in section, and a Z cannot be printed without support whichever way
it is laid. Every wall over both trays dies on that plane.

- **Two label strips per bay, sized for 1/2 inch TZe tape.** The lower one is
  on the module's own front face, below the lid skirt, so it reads with the lid
  on; the upper one is on the wall between the trays, facing forward over tray
  A. They are 0.5 mm deep, so the tape sits below flush and cannot be caught.
  Neither is on a lid — lids come off and go back the other way round.

## Bill of materials

| Part | Qty | Print orientation |
|---|---|---|
| `body` | 1 | as modelled, flat on its base, no supports |
| `pick_lid` | 1 | plate TOP face on the bed, skirt rising at 50 degrees (`rotate([180 - pick_lid_slope, 0, 0])` — revision 5's export had the sign wrong and stood the lid on its skirt) |
| `fill_lid` | 1 | flipped, plate top face on the bed, tabs up; the pull lip is in the plate's plane |

Print-ready STLs are in `build/print_ready/`, exported by `print_export.scad`,
already rotated and dropped to z = 0. Each was scanned face by face in that
orientation: the body's only downward faces past 45 degrees from vertical are
the chute ceiling (the advisory) and the porch ceiling the rib carries; the
pick lid has none; the fill lid has the two barbs' 1.1 mm return faces, which
bridge.

Purchased: four stick-on rubber feet, 10 mm; 1/2 inch TZe label tape.

## Print this first

`calibration_coupon.scad`. `doctor.py` reports no calibration profile on this
machine, so the snap and rail fits are geometry-only.

## The bench maquette

`test_model.scad` renders the whole module at `TEST_SCALE = 0.42`, about
97 x 72 x 59 mm — roughly a coffee mug's footprint. STLs are in
`build/maquette/`, one part per file, in print orientation.

It is a **form model, not a function model**. Proportions, the flush
rim-to-floor line, the crossing chute and both lid planes all read true, but a
size-00 capsule does not fit any bay and the fill lid's snap tabs come out
around 0.5 mm thick. Print it to judge the shape and to see whether the porch
ceiling and the 50-degree chute ceiling come out clean; do not judge the flow
from it.

## Reviewer's attention

- **Nothing in this revision moves**, so there is no motion sweep.
- The chute ceiling on the 40-degree leg is a **50-degree-from-vertical
  overhang**, past the conservative 45-degree rule — 30,900 mm² of it, in
  43 mm bays. It is internal and non-cosmetic, and `chute_clear` carries a sag
  allowance. It is the one print risk left in the body; the cubby ceiling,
  which was the same overhang across 224 mm, is at 45 now. If the test print
  shows droop, the fallback is a gabled ceiling.
- **The porch feeds at the repose angle**, as any pile does; the number that
  matters is the throat over the stagnant wedge, 32.6 mm at the 30-degree
  estimate and 28.9 at 35. Below about 38 degrees of repose it stays over one
  pill length.
- **Porch lanes are 20.3 mm.** Pills run single file. The rib's knife edge is
  what keeps a capsule arriving crosswise from stopping at it.
- Bay width is **1.65x the longest pill** against a 2–3x mass-flow rule of
  thumb. Mitigated, not eliminated; an occasional tap may be needed.
- The two `NEAR MISS` notes (0.150 mm, 0.153 mm) are both lids' intended
  clearance, explained in `joints.json`.
- The snap's 35-degree return, the 0.8 mm engagement and both rail clearances
  are geometry only (Tier 2). Print `calibration_coupon.scad` first.

## Build and verify

```sh
source ~/.local/opt/openscad/env.sh
cd scad-workbench/projects/pill_organizer_10bay
~/.local/src/openscad-cad-skills/scad-modeler/scripts/validate_scad.sh --all
python3 ~/.local/src/openscad-cad-skills/scad-modeler/scripts/check_rules.py --project-dir .
../../render.sh assembly.scad build/prev_asm
scad -D 'PART="pick_lid"' -o build/print_ready/pick_lid.stl print_export.scad   # per part
scad -D 'PART="pick_lid"' -o build/maquette/pick_lid.stl test_model.scad        # scaled
```

## Confidence

Tier 2 — geometry verified, fit uncalibrated. Every assert in `params.scad`
passes, all three parts render as single watertight bodies at their declared
bounding boxes, both chute legs are walked end to end by `bores.json` in both
end bays, the front groove is walked out through the top of its wall, and the
static assembly is collision-free. Beyond the suite, revision 6 was probed by
hand: `trimesh.contains()` lines through the groove, the label recesses and the
snap catch, and a face-normal scan of every part in its print orientation. What
is *not* verified: any clearance as a real printed fit, and any claim about how
pills actually flow.
