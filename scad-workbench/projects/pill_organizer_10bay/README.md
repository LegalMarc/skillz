# pill_organizer_10bay

A gravity-fed bench organizer for ten supplement pills. Pour a bulk charge into
each hopper at the back; it feeds forward into an open pick tray at the front.
Lift one lid and all ten types are exposed.

**Two lids total.** Both fill ports at the back under one flat lid, both pick
rows at the front under one sloped lid.

**Revision 10.** Ten revisions, forty recorded decisions (`plan.md`). Revision 10
is test print 2, the first full-size print. It found four things wrong and one
thing unproven: the pick lid slid straight off its slope (nothing had ever
retained it); the front row filled once and did not refill as pills were taken;
the bins felt small; the groove corner tore again; and the coupon had been read
off a brim-fused print. Revision 10 tilts tray A's floor 35 degrees toward the
front wall and makes the porch 40 degrees (D36), deepens the trays 28 -> 40 mm
and widens the bays to 44.96 mm (D37), holds the lid on with lugs that stop
against pillars of the front wall (D38), thickens the groove corner (D39) and
sets `rail_clear` to 0.20 pending a new coupon (D40). `INCIDENTS.md` has the
lid error and why no check caught it. The earlier history: revision 3 took the
envelope from 9.45 L to 5.54 L with a 40-degree ramp; revision 4 scalloped the
front wall and leaned the hopper divider; revision 5 made the dead wedge a
cubby and added tape labels; revision 6 and 7 were independent reviews;
revision 8 was test print 1 (flat porch ceiling, nesting fill lid, lugs);
revision 9 fixed tray B's pile.

## What it is

| | |
|---|---|
| Overall | 245 x 194.8 x 189 mm (the 245 includes the 5 mm joining rail; the plate allows 246 x 246 x 250) |
| Bays | 10, two rows of 5, 44.96 mm clear each, trays 40 mm deep |
| Capacity, middle bay | **428 mL front row, 200 mL back row**; end bays 410 / 193. About 3.1 L total, geometric maximum |
| Printed parts | **3 designs, 3 pieces**, no hardware |
| Validation | **13 passed, 0 failed, 4 n/a, 0 inconclusive, 1 advisory** (the advisory is `check_printability.py`; its overhang half fails every real FDM part on area, but its THIN-WALL half caught a real 0.2 mm wall in revision 7 that everyone had stopped reading it for — read both halves) |
| Confidence | Tier 2 — geometry verified, fit uncalibrated |

A 90-day once-daily size-00 charge is 147.4 mL, so the front row carries 261
days and the back row 122.

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
- **The chute is one 40-degree floor** (D36). Test print 2 showed the 25-degree
  porch of revisions 3 to 9 stalling: row A filled once and did not refill as
  pills were taken, while row B, on a plain 40-degree ramp, fed well. The
  porch is now the ramp's own angle, so there is no stagnant wedge.
- **Tray A's floor tilts 35 degrees toward the front wall** (D36): 3.0 mm high
  at the front wall, 31.0 at the chute foot. 35 is the top of the plausible
  repose range (25 to 35, estimate 30), so every pill on that floor can slide
  forward at any repose in it; as the front of the pile is picked, the rest
  follows. It costs 28 mm of height, which is why the module is 189 mm tall
  now (141 before) and tray B sits 105.6 mm up. `calculations.md` has the
  numbers.
- **The front tray is a parts bin, not a well.** The pile crests at 43.9 mm at
  the front wall (40.9 mm deep), sloping up to 67 mm at the chute mouth. The lid
  plane stays under 45 degrees, which pins its front end at 77 mm; the front
  WALL is scalloped down to 52, so the reach over it is **8.1 mm** (3.6 at a
  25-degree repose). With the lid off, tray A is open at the top and front.
  With it on, the lid's skirt hangs down the outside and the scallops are
  invisible. Two rounded finger notches in the skirt, under bays 2 and 4, are
  what you lift the lid by, straight up. In each END bay the scallop stops 5 mm
  short of the side wall: a pillar of the front wall stays at full height there
  and is what holds the lid on (below).
- **The wedge under the chute is an accessory cubby.** It can never hold pills,
  so it holds everything else — a splitter, a funnel, a bottle of the next
  refill. One void the full inner width, 70 mm deep, 83 mm tall at its shallow
  end and 153 mm at the back, opening through the **back face only** so both
  side walls stay full. Its ceiling is a 45-degree plane, the conservative FDM
  overhang limit, and a 30 mm lip across the opening — level with the shallow
  end — keeps the contents in when you slide the module about; 123 mm of clear
  opening remains above it. About 1.8 L of what was solid infill is usable
  space. (The pick lid does not fit in it: it is 144 mm long.)
- **The fill mouths are 63 and 39 mm, about 3:2.** The wall between them leans
  8.8 mm forward at the rim (26 degrees from vertical), pivoting at the end
  of hopper B's ramp so the ramp is untouched and the wall below the pivot is
  full thickness. (The revision 7 review found the pivot 7 mm below the ramp's
  end, which thinned that wall to 0.2 mm at its foot; see D28.) Left vertical
  the split was 70 : 32, which is what you get from equalising the two rows'
  volumes rather than the openings you actually pour into.
- **The vault.** The crossing chute's ceiling on its 40-degree leg is a
  shallow gable across each bay: 4.4 mm higher at the centre, 8 mm lower at the
  dividers. A face sloping two ways at once is steeper on the diagonal, and
  this one is 44.8 degrees from vertical where the plain ceiling was 50 —
  inside the 45-degree no-support rule instead of past it. Hopper B's ramp
  rides one deck above the ridge, so it starts 4.4 mm above tray B's floor with
  a riser pills drop off (filleted at its foot; its top edge is sharp). The
  chute is 40 mm clear at the ridge and 28 at the dividers.
- **A flat ceiling under the back row.** Tray B's floor is carried on the bay
  dividers alone; the chute runs underneath it. That ceiling is flat, one
  deck under tray B's floor: a 45 mm bridge, which slicers print with bridge
  settings. Until revision 8 it sloped at 25 degrees and needed a fin down the
  middle of each porch to hold it up; test print 1 showed the slope printing
  ragged anyway and the fin reading as an unexplained divider in every front
  bin, so both are gone. The wall between the rows still forms the opening
  into each front bin at 39 mm, so the pile height there is unchanged.
- **Chamfered openings.** The top corners of the opening into each front bin
  and into each back-row hopper are 45-degree chamfers, so the unsupported
  span across the top of each opening is 27 mm, not 43.
- **The fill lid nests.** It drops into the recess above the seat ledges with
  0.3 mm all round, rests on them, and stays put by gravity. A chamfer on its
  underside edge leads it in. A 30 mm pull lip on its front edge stands out
  over tray B, through a notch in the wall in front of the mouth, so there is
  something to lift by. The notch stops at the seat plane: with the lid on,
  nothing below it is open. (Revisions 5 to 7 had snap tabs; test print 1
  broke every one, because a tab printed standing up bends across its layers.)
- **The pick lid is held by its lugs, against the pillars** (D38). Two lugs
  under its ends drop into the end bays of tray A, against the side walls and
  directly behind the front wall's pillars, 0.5 mm clear. The lid is on a
  43.8-degree slope; PLA on PLA holds to about 17. Slide it down the slope and
  each lug's front face meets the pillar's back face after 0.7 mm and engages it
  over 7.3 mm. Lift it straight up and nothing touches. Turn it round and the
  skirt lands in the wall behind tray B, so it cannot sit. "FRONT" is embossed
  on the skirt. The two notches in the skirt are finger grips.
- **Foot pads.** Four 10 mm recesses in the base take stick-on rubber feet, so
  a unit that is bumped while pouring does not skate.
- **Edges.** The body's vertical corners are rounded at 3 mm and the step and
  back top edges at 1.5 (the front edge of the pick plane is obtuse and gets
  only an easing; the side walls' long top edges are square); both lids have
  rounded corners, the fill lid a chamfered top perimeter and the pick lid
  chamfered plate edges. Inside, every corner a pill meets has carried a 2 mm
  fillet since revision 1.
- **Ganging.** Two dovetail rails on the left face, two grooves on the right,
  the rails' undersides chamfered at 45 degrees so they print without droop.
  Lift the pick lid off the left-hand unit, lower the right-hand unit's rails
  in from above. Revisions 3 to 5 had the front groove capped by the side wall,
  so this could not be done; it is open through the pick plane now, and the lid
  covers the opening in use. Since D39 the buttress behind the front groove is
  7 mm deep and 23 mm long, leaving a 4.4 mm skin between the groove and tray A
  (2.4 before: a blade that tore in both test prints).

## Two things that were forced, not chosen

**Neither lid is hinged.** The two tray rims are 82 mm apart, so a lid
bridging them as an L has its mass centre well below any back-top pivot and
falls shut every time; a front pivot runs the far corner into the benchtop. The
pick lid lifts straight off. What keeps it on the slope is its two lugs against
the front wall's pillars (D38), not its skirt: the skirt hangs outside the front
face, and sliding down the slope takes it further from that face. Revisions 4 to
9 said the skirt did it; test print 2 slid the lid straight off.
`probes/lid_retention.py` now moves the lid and fails if nothing stops it. It
lifts straight, not tilted: its back edge is 0.35 mm from the wall behind tray B
and the top-back corner meets that wall after 5 degrees of tilt.

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
| `body` | 1 | as modelled, flat on its base, no supports. 245 x 194.8 x 189 mm |
| `pick_lid` | 1 | plate TOP face on the bed, skirt rising at about 46 degrees (`rotate([180 - pick_lid_slope, 0, 0])` — revision 5's export had the sign wrong and stood the lid on its skirt) |
| `fill_lid` | 1 | flipped, plate top face on the bed; the pull lip is in the plate's plane |

Print-ready STLs are in `build/print_ready/`, exported by `print_export.scad`,
already rotated and dropped to z = 0. Each was scanned face by face in that
orientation (`probes/overhang_scan.py`): the body's downward faces past 45
degrees from vertical are the flat bridges (the chute ceiling under tray B,
now 45 x 40 mm per bay, and the tops of both outlet openings), the foot-pad
and label recess ceilings, the 1 mm lips at the ends of each vault ridge, and
the seat ledge's underside along the leaning divider; the pick lid has a 1 mm
strip at the tip of its skirt, its plate chamfers on the bed, and the edges of
the "FRONT" relief (0.6 mm, 45.3 to 46.2 degrees); the fill lid has only its 1
mm top chamfer, which lies on the bed. The lugs' vertical front faces lean over
by the plane's 43.8 degrees and are not flagged.

Slicer: **no brim** (Elegoo Slicer: Others, Skirt and brim, Brim type,
No-brim). Test print 1 used one and it fused into the walls. Enable bridge
detection, which is on by default in Orca-based slicers.

Purchased: four stick-on rubber feet, 10 mm; 1/2 inch TZe label tape.

Test print: `build/section/test_print_section_256.3mf` -- full size, on one
256 mm plate: the right-hand end bay of the body (to z 160, back to where
hopper B's ramp leaves the top: 49 x 146 x 160 mm), the matching end of the pick
lid, a corner of the fill mouth and of the fill lid, and the coupon. About 7 to
8 hours. `python3 build/maquette/make_plate.py section --export` rebuilds it
from the sources. This is the one to
print; see "The full-size section" below. The 0.42 maquette plate
(`build/maquette/test_print_plate_256.3mf`) judges shape only.
`TEST_PRINTS.md` records what each test print showed.

## Print this first

`calibration_coupon.scad`. One fit depends on your printer rather than the
geometry: the joining rail in its groove. Test print 1's coupon read 0.50 mm per
side, but it was printed with a brim that fused into the walls; test print 2
(no brim) found the block loose on every stub down to 0.30. `rail_clear` is
0.20 now (D40) and this coupon brackets it: five male rail stubs labelled
-100, -50, 0, +50, +100 (clearances 0.30, 0.25, 0.20, 0.15, 0.10, relative to
the default) and a loose groove block cut exactly as the body cuts its grooves.
Turn the block over so the face that was on the bed is UP, and drop it over each
stub; the one that goes down with hand pressure and does not rock is your fit.
If it is not "0", that label moves `rail_clear`. Two islands, 124 x 30 mm, no
supports, no brim.

## The full-size section

`fit_section.scad` (`PART` = body, pick_lid, mouth, fill_lid) cuts the real
parts, so every clearance, wall and bridge is the real one. What to do with it:

1. **Tray A's feed (D36), the test of this revision.** Drop capsules into the
   chute's open back end: they run down the 40-degree chute onto the tilted
   floor and pile at the front wall. Take them from the front a few at a time;
   the rest should follow without being grabbed at.
2. **Tray B's pile (D33).** Pour real capsules into hopper B through the open
   top. They run down the ramp, out under the outlet and pile in tray B. The
   pile must stay below the wall in front of it, with room to spare.
3. **Pick lid (D38).** Lay the lid end on the section: the lug drops in against
   the side wall directly behind the pillar, the plate sits flat on the plane,
   the skirt covers the scalloped front. It must not slide down the slope (it
   moves under 1 mm). Lift it straight off. Try it turned round.
4. **Groove corner (D39).** Lower a spare rail into the front groove; nothing
   tears at the break-out.
5. **Fill lid.** Drop the lid corner into the mouth corner: it should go in
   without forcing, sit flat on the half divider without rocking, and lift
   out cleanly.
6. **Bridges.** The chute ceiling under tray B (45 x 40 mm) and both outlet tops.
7. **The coupon** as above.

## One plate for the small test print

`build/maquette/test_print_plate_256.3mf` lays the three maquette parts and
the coupon out on a 256 x 256 mm plate, origin at the front-left corner, each
in its print orientation with 15 mm or more between parts. It is a plain
core-spec 3MF (four named objects, positioned), which Elegoo Slicer, Orca,
Bambu Studio and PrusaSlicer all open as a multi-object plate; assign your own
printer and filament profile after opening. Regenerate it with the script in
`build/maquette/make_plate.py` after any re-export.

## The bench maquette

`test_model.scad` renders the whole module at `TEST_SCALE = 0.42`, about
97 x 72 x 59 mm — roughly a coffee mug's footprint. STLs are in
`build/maquette/`, one part per file, in print orientation.

It is a **form model, not a function model**. Proportions, the flush
rim-to-floor line, the crossing chute and both lid planes all read true, but a
size-00 capsule does not fit any bay, and at 0.42 scale every wall is about
1 mm thick and every bridge is printed with a full-size nozzle, so ragged
bridges and thin edges look worse than they will at full size. Print it to
judge the shape and the lid fits; do not judge the flow from it.

## Reviewer's attention

- **Nothing in this revision moves**, but the lid is the thing that came off, so
  `probes/lid_retention.py` moves it: rest, 1/2/5 mm down-slope, a 30 mm lift,
  and a 180-degree reversal, with exact boolean overlaps. Run it.
- **The new heights.** Everything behind tray A rose: tray B's floor 105.6,
  hopper_rim 189, tray A's rim 77. The plane is 43.8 degrees (limit 45); the
  wall between the trays holds 14.7 over tray B's floor and tray B's pile is 6.4
  mm under it at repose 30, 1.95 at 25.
- **Tray A's floor angle** is a judgement from the repose estimate, not a
  measurement. If real capsules need more than 35 degrees, the one plane (40,
  with the chute) is the limit.
- **The chute mouth is 36 mm vertical, 27.6 perpendicular** to the 40-degree
  floor: 1.06x a pill length. Row B's outlet is tighter (27 vertical) and fed
  well in test print 2.
- **The hanging wall between the trays** is now 35 mm tall below tray B's floor
  (it was 14), 2.4 mm thick, carried by the dividers and the outlet chamfers.
- **The porch ceiling is a flat 45 x 40 mm bridge in every bay** (D29). Check it
  on the first print for sag.
- The ~2 L of solid wedge under the chute is infill. The body is 2.0 L of
  solid; plan for about 600 g at 15% infill.
- Bay width is **1.73x the longest pill** against a 2-3x mass-flow rule of
  thumb. Mitigated, not eliminated.
- The two `NEAR MISS` notes (0.150 mm, 0.144 mm) are both lids' intended
  clearance, explained in `joints.json`.
- The rail clearance (0.20) is a default pending the new coupon. The fill lid's
  (0.30) was confirmed by test print 2.

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
static assembly is collision-free. Beyond the suite, every revision since 6
was probed by hand: `trimesh.contains()` lines through each changed feature
and a face-normal scan of every part in its print orientation. Test print 1
(the 0.42 maquette and the coupon, whose brim misled the rail reading) found the
problems revision 8 fixes; its lids were at 0.42 scale, so they confirmed no
fit. The independent review of revision 8 found tray B's pile above its wall,
which revision 9 fixes (D33). Test print 2 (full-size section) found the
lid retention, the row A feed, the bin size, the groove corner and the coupon
reading that revision 10 fixes. What is *not* verified: that the tilted floor
feeds, that the new lugs hold on a real print, and the rail fit at 0.20; the
revision 10 section print is built to check all three. The `probes/` directory
holds the scripts behind every revision 10 number (`lid_retention.py`,
`corner_thickness.py`, `capacity.py`, `overhang_scan.py`).
