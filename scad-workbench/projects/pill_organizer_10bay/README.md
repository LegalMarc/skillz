# pill_organizer_10bay

A gravity-fed bench organizer for ten supplement pills. Pour a bulk charge into
each hopper at the back; it feeds forward into an open pick tray at the front.
Lift one lid and all ten types are exposed.

**Two lids total.** Both fill ports at the back under one flat lid, both pick
rows at the front under one sloped lid.

**Revision 13.** Thirteen revisions, fifty-four recorded decisions (`plan.md`). Revision 13
answers test print 4, which was printed after all (the revision 11 section, PETG, 2026-10-04):
the arches over the openings drooped a little, the pick lid looked like two rectangles welded
together, and every stub of the slim-rail coupon was too large for the slot. D52: the opening
from the chute into tray A and the opening from hopper B into tray B are half octagons now:
each divider face carries a 45 degree facet and the crown is a short flat, 10 mm on tray A's
mouth (facets 17.48 mm) and 20 mm on outlet B (facets 12.48), against 29 before. The crowns do
not move, so the throat at the bay centre and tray B's pile margin (D33) are as they were; the
price is the corners. A first cut gave outlet B a 10 mm crown, and the review found a capsule
against a divider blocked by 2.47 mm; D54 raised it to 20 and the probe now sweeps a capsule over
the mesh (worst pose +4.43 mm on tray A's mouth, +1.37 on outlet B). D53: the pick lid's plate and
skirt are one profile, extruded once, 3.0 mm thick all the way round, with a 3.0 mm fillet inside
the bend and a 1.5 mm round outside it, and the 1.0 mm end chamfer runs on round the bend. D51
(`rail_clear` 0.40) is a best guess: **read the new coupon before printing the body** (see "Print
the final unit"). Nothing here has been printed.

**Revision 12.** Twelve revisions, forty-nine recorded decisions (`plan.md`). Revision
12 is the final full-size print: the user skipped test print 4 and went straight to the unit (they printed it afterwards; see revision 13).
It is an edge pass (D48): every edge of the three parts was audited (`calculations.md`,
"Revision 12: the edge pass", 39 rows) and the ones a hand, a pill or the bed touches are
chamfered or rounded: a 0.5 mm bed chamfer on the base and the foot-pad mouths, r 1.5 on the
side faces' perimeter, chamfers on the scallop floors, the fill mouth's rim and the cubby's
mouth, 2 mm fillets in the cubby and in tray B's divider corners, and chamfers on the pick
lid's skirt and underside ends and the fill lid's lip. The lid's seat, the dovetail, the
stop blocks and lugs, the labels and the ribs stay sharp on purpose. Capacities move by 0.1
mL. D49 writes the three plates to print (`build/final/`, see "Print the final unit").

**Revision 11.** Eleven revisions, forty-seven recorded decisions (`plan.md`).
Revision 11 is test print 3 (the revision 10 section, in Generic PETG): row A
refills now, the lid and its lug work, and what was left was small. Three small
half-round ribs per bay in the corner where tray A's floor meets the front wall
give a lodged capsule's end something to push against (D41); hopper A's back wall flares 30 degrees so the narrow back
mouth is easier to pour into (D42, mouth 39 -> 57 mm); the rail, groove and
buttress are slimmed to about a divider, the buttress protruding 3 mm into the bay
instead of 7 (D43); the pick lid has no finger notches, you pinch it (D44); both
labels sit on the front face, stacked (D45); the section is cut at a full divider
(D46); and `rail_clear` is 0.215, from the PETG coupon (D47). Tray A's divider
joints also get a fillet.

**Revision 10.** Ten revisions, forty recorded decisions (`plan.md`). Revision 10
is test print 2, the first full-size print. It found four things wrong and one
thing unproven: the pick lid slid straight off its slope (nothing had ever
retained it); the front row filled once and did not refill as pills were taken;
the bins felt small; the groove corner tore again; and the coupon had been read
off a brim-fused print. Revision 10 tilts tray A's floor 35 degrees toward the
front wall and makes the porch 40 degrees (D36), deepens the trays 28 -> 40 mm
and widens the bays to 44.96 mm (D37), holds the lid on with lugs that stop
against stop blocks in tray A's front corners (D38), thickens the groove corner (D39) and
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
| Overall | 243 x 213.0 x 189 mm (the 243 includes the 3 mm joining rail; 194.8 deep below z 155, the back wall leans out above; the plate allows 246 x 246 x 250) |
| Bays | 10, two rows of 5, 44.96 mm clear each, trays 40 mm deep |
| Capacity, middle bay | **438 mL front row, 200 mL back row** (437.7 / 200.0 after the D52 and D54 facets); end bays 428 / 198. About 3.2 L total, geometric maximum |
| Printed parts | **3 designs, 3 pieces**, no hardware |
| Validation | **14 passed, 0 failed, 3 n/a, 0 inconclusive, 1 advisory** (the advisory is `check_printability.py`; its overhang half fails every real FDM part on area, but its THIN-WALL half caught a real 0.2 mm wall in revision 7 that everyone had stopped reading it for — read both halves) |
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
  WALL is scalloped down to 55, so the reach over it is **11.1 mm** (6.6 at a
  25-degree repose, a pill radius or more). With the lid off, tray A is open at the top and front.
  With it on, the lid's skirt hangs down the outside and the scallops are
  invisible. The lid has no notches or handles: you pinch the skirt and the plate
  edge between thumb and forefinger (it tilts about its back edge, or lifts
  straight, then forward). In each END bay the scallop stops 6 mm
  short of the side wall: the front wall stays at full height there, with a stop
  block behind it in the corner, and that is what holds the lid on (below).
- **The wedge under the chute is an accessory cubby.** It can never hold pills,
  so it holds everything else — a splitter, a funnel, a bottle of the next
  refill. One void the full inner width, 70 mm deep, 83 mm tall at its shallow
  end and 153 mm at the back, opening through the **back face only** so both
  side walls stay full. Its ceiling is a 45-degree plane, the conservative FDM
  overhang limit, and a 76 mm lip across the opening (D50: a deep back pocket
  for upright things like lip balm and a pill cutter; the front of the cubby is
  a well) keeps the contents in when you slide the module about; 79.5 mm of
  clear opening remains above it. About 1.8 L of what was solid infill is usable
  space. (The pick lid does not fit in it: it is 144 mm long.)
- **Corner beads** (D41). The floor meets the front wall in a 55 degree wedge, and
  the last, larger capsules lodged in it on test print 3. Three small ribs per bay,
  each a half-round of 2.5 mm radius (5 mm across) running 13 mm out from the front
  wall along the floor and ending in a hemisphere, at a quarter, half and three
  quarters of the bay, with 6.2 mm clear between them (a capsule is 11). They are
  for pushing a capsule's end against: on the mesh, a capsule slid toward the wall
  along the floor stops with its tip 4.8 mm out (0.7 without) against a rib end, which
  touches it 3.9 mm below its axis, so the push lifts that end; between two ribs it
  nests in the channel and lifts straight out. A capsule lying along the wall rests
  on the ribs 2.25 mm up. (The first try, overlapping 8 mm spheres, was a ramp; the
  user asked for small discrete beads.) Nothing is behind a rib, and they print without
  support.
- **Hopper A's mouth flares** (D42). The back wall of the module leans out at 30
  degrees from vertical from the chute floor's end up to the rim, so the opening
  you pour into widens toward the top: 57 mm front to back under the lid (39
  before), 60 at the rim, 49 between the seat ledges (33 before). The chute floor
  is untouched. The fill lid's recess follows the flare, so the lid is 121 mm long
  (104) and still drops in with 0.3 mm all round. The module is 213 mm deep at the
  rim; the back wall's outer face leans 30 degrees, an overhang inside the 45
  degree rule.
- **The fill mouths are 63 and 57 mm now (about 1.1:1; 63 and 39 before D42).** The wall between them leans
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
- **Half-octagon openings** (D52; D29's 8 mm chamfers before). The opening into
  each front bin (under the wall between the rows) and into each back-row
  hopper (under hopper B's front wall) has vertical sides, a 45-degree facet
  climbing from each divider, and a flat at the crown: 10 mm on tray A's mouth
  (facets 17.48 mm) and 20 mm on outlet B (facets 12.48; D54), so the unsupported span
  across the top is 10 and 20 mm, not 29 (and 43 before D29).
  The crowns stay where they were, 67.0 and 137.0 mm up, so the throat at the bay
  centre and the pile heights are unchanged; the facets fill the corners. A capsule against
  a divider clears both: the throat a pill radius from the divider is 16.9 mm on tray A's
  mouth and 13.8 on outlet B (a capsule needs 11, and the asserts want 12). The mesh
  sweep (`probes/outlet_arch.py`) gives a worst pose of +4.43 and +1.37 mm. At a 10 mm
  crown outlet B blocked a capsule by 2.47 mm, which is why it is 20. The porch
  ceiling under tray B is not one of these arches and is still a flat 45 x 40 mm bridge.
- **The fill lid nests.** It drops into the recess above the seat ledges with
  0.3 mm all round, rests on them, and stays put by gravity. A chamfer on its
  underside edge leads it in. A 30 mm pull lip on its front edge stands out
  over tray B, through a notch in the wall in front of the mouth, so there is
  something to lift by. The notch stops at the seat plane: with the lid on,
  nothing below it is open. (Revisions 5 to 7 had snap tabs; test print 1
  broke every one, because a tab printed standing up bends across its layers.)
- **The pick lid is held by its lugs, against stop blocks** (D38). Two lugs
  under its ends (4 mm thick) drop into the end bays of tray A, against the
  side walls, each directly behind a stop block fused into the front corner. The
  lid is on a 43.8-degree slope; PLA on PLA holds to about 17. Both stop faces,
  the lug's and the block's, are **perpendicular to the pick plane**: slide the
  lid down the slope and the faces meet flat after 0.5 mm and overlap by 6.9
  mm. Pinch it by the skirt and lift the front, which pivots it about its back edge, and the
  lug swings along the plane's normal, along the faces, not into them; lift it
  straight up or along the normal and nothing touches either. Turn it round and
  the skirt lands in the wall behind tray B, so it cannot sit. (The first
  version had a vertical stop face; the lug drove into it at 0.5 to 2 degrees
  of tilt and jammed. The review of revision 10 found it.) A 45-degree filler
  closes the slot between each block and the rail buttress so nothing can lodge
  there. "FRONT" is embossed on the skirt. Test print 3 confirmed the lug keeps the
  lid seated; the finger notches of revisions 6 to 10 are gone (D44).
- **The pick lid is one piece** (D53). Until revision 12 the plate and the skirt
  were two polygons, unioned, with a seam at the bend. Now one profile is
  extruded once: 3.0 mm thick through plate, bend and skirt, a 3.0 mm fillet on
  the inside of the bend, a 1.5 mm round on the outside, and the 1.0 mm
  end chamfer is one bevel from the plate's top, round the bend and down the
  skirt. In print the outside round sits on the bed and climbs only 0.46 mm
  before it meets the skirt's own 46 degree face (worst overhang step 0.36 mm
  per 0.2 mm layer). The inside fillet brings the skirt / fillet to 0.10 mm from the body's
  front top edge at the nominal pose (0.14 before; 0.141 on the stops), and the fillet is the
  first thing to meet the body 0.36 mm up-slope of nominal (the skirt was, at 0.485). The lid
  probes and sweeps pass.
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
  covers the opening in use. Since D43 the rail is 3 mm out of the wall (5 before)
  and 3.6 mm at the root, the groove 3.4 deep, and the buttress behind the front
  groove protrudes 3 mm into the bay (7 before) and is 14 mm long; the skin between
  the groove and tray A is 2.4 mm, a divider, and the groove's front lip is bevelled
  1 mm where it meets the sloped plane (D39's lesson: no thin blade, no knife edge).
  The plane rises toward the back, which would have left the skin standing up to
  6.4 mm (2.6 times its own thickness) above the front lip beside it, so the skin's top
  is trimmed flat to one skin thickness above that lip: it stands 2.3, 1.7 and 1.3 mm
  above it at the groove's tip, middle and mouth. `probes/corner_thickness.py` checks
  that, the edge angles, and every thin region in the break-out zone (all named
  features, listed in `calculations.md`). Test print 3 found the old rail overbuilt;
  the dovetail slope is unchanged.

## Two things that were forced, not chosen

**Neither lid is hinged.** The two tray rims are 82 mm apart, so a lid
bridging them as an L has its mass centre well below any back-top pivot and
falls shut every time; a front pivot runs the far corner into the benchtop. The
pick lid lifts off: lift it (straight up, along the plane's normal, or tilted about its back edge), then draw it forward. A straight lift alone meets the fill lid's pull lip after 26 mm; every lift-then-forward path clears. What keeps it on the slope is its two lugs against
the stop blocks in tray A's front corners (D38), not its skirt: the skirt hangs outside the front
face, and sliding down the slope takes it further from that face. Revisions 4 to
9 said the skirt did it; test print 2 slid the lid straight off.
`probes/lid_retention.py` now moves the lid and fails if nothing stops it, if it
jams on the way off, or if it can be fitted turned round. It lifts by its front
edge, tilted about its back edge, which is 1.2 mm from the wall behind tray B
(0.35 until the review of revision 10: the top-back corner met that wall after 9
degrees of tilt); it is swept clear to 15 degrees, with 0.10 mm of clearance at
the nominal pose (0.141 on the stops) and more as it tilts, and the whole removal is declared in `joints.json` so
`motion_sweep.py` runs it.

**The pick surface is one sloped plane, not two steps.** A lid spanning two
steps is a Z in section, and a Z cannot be printed without support whichever way
it is laid. Every wall over both trays dies on that plane.

- **Two label strips per bay, sized for 1/2 inch TZe tape (D45).** Both are on
  the module's own flat front face, below the lid skirt, so they read with the
  lid on: the row A (front tray) strip low, the row B (back tray) strip above it,
  4 mm apart, as the bins rise from the front-bottom up and back. (The upper strip
  used to sit on the wall between the trays, reached over tray A; test print 3
  found it awkward and half hidden by the rail.) They are 0.5 mm deep, so the tape
  sits below flush and cannot be caught. Neither is on a lid — lids come off and
  go back the other way round.

## Print the final unit

Revision 13 is the full unit (revision 12's plus D51 to D54); test print 4 (the revision 11 section) was printed after revision 12 was designed and drove D51 to D53. Three
plates, one part each, plain core-spec 3MFs that Elegoo Slicer opens as a single named
object, already centred on the 256 x 256 plate at z = 0 (`python3 build/maquette/make_plate.py
final --export` rebuilds them from the sources and checks each against its STL):

| Plate | File | Part | Size on the plate | Spans |
|---|---|---|---|---|
| 1 | `build/final/final_body_256.3mf` | `pill_organizer_body` | 243.0 x 213.0 x 189.0 mm, 2.31 L of solid | x 6.5-249.5, y 21.5-234.5 |
| 2 | `build/final/final_pick_lid_256.3mf` | `pill_organizer_pick_lid` | 239.0 x 139.5 x 22.7 mm, 105.5 cm3 | x 8.5-247.5, y 58.2-197.8 |
| 3 | `build/final/final_fill_lid_256.3mf` | `pill_organizer_fill_lid` | 233.8 x 129.0 x 3.0 mm, 85 cm3 | x 11.1-244.9, y 63.5-192.5 |

- **Before the body: read the D51 coupon.** The body bakes in `rail_clear` 0.40 (D51), a best guess
  after every stub of the slim rail's coupon (0.265 .. 0.165) was too large for the slot on test print 4.
  The new coupon (`build/coupon/rail_coupon_256.3mf`, 0.50 .. 0.30) is printing. Read it first: the stub
  that goes down by hand and comes back out, snug but free. If that is not the "0" stub, set `rail_clear`
  in `params.scad` to the read value (0.40 + the label / 1000) and run
  `python3 build/maquette/make_plate.py final --export` **before** printing the body; the groove is in
  the body, so a wrong value is a reprint. The lids do not depend on it.
- **Filament: PETG**, the same as the tests; in another filament run the coupon again. **Dry it first**:
  the tests strung heavily (groove, bins, lid).
- **No brim.** Elegoo Slicer: Others, Skirt and brim, Brim type, No-brim (a brim fused into
  the walls on test print 1). **No supports.** 10% cubic infill, 2 wall loops (the 2.4-2.8 mm walls are already near solid at 2 loops; a third added about 150 g), 0.2 mm layers. Bridge detection on.
- The body's base and the foot-pad recesses carry a 0.5 mm bevel against elephant foot; the
  lids' bed faces carry 1.0.
- Purchased: four stick-on rubber feet, 10 mm (they drop into the recesses); 1/2 inch TZe label tape.
- Print the body first; it is the long one (Elegoo Slicer, revision 12 with D50: 899 g of PETG, 1 d 3 h at 10% cubic infill and 2 wall loops, so it fits one full 1 kg spool; at 15% it was 1.02 kg) and the lids are
  checked against it. The lid plates are 239 and 234 mm wide: nothing else goes on those plates.
- Features printed for the first time in this unit: the D52 half-octagon openings, the D53 one-piece lid, the D41 ribs, the D42 flare, the D43 slim
  rail and groove, the K1 skin cap, the D45 labels, the divider fillets. `TEST_PRINTS.md`,
  "Final print", lists what to look at on each.

## Bill of materials

| Part | Qty | Print orientation |
|---|---|---|
| `body` | 1 | as modelled, flat on its base, no supports. 243 x 213.0 x 189 mm |
| `pick_lid` | 1 | plate TOP face on the bed, skirt rising at about 46 degrees (`rotate([180 - pick_lid_slope, 0, 0])` — revision 5's export had the sign wrong and stood the lid on its skirt) |
| `fill_lid` | 1 | flipped, plate top face on the bed; the pull lip is in the plate's plane |

Print-ready STLs are in `build/print_ready/`, exported by `print_export.scad`,
already rotated and dropped to z = 0. Each was scanned face by face in that
orientation (`probes/overhang_scan.py`): the body's downward faces past 45
degrees from vertical are the flat bridges (the chute ceiling under tray B,
now 45 x 40 mm per bay, and the 10 mm and 20 mm crown flats of the two outlet openings), the foot-pad
and label recess ceilings, the 1 mm lips at the ends of each vault ridge, and
the seat ledge's underside along the leaning divider; the pick lid has a 1 mm
strip at the tip of its skirt, its plate chamfers and the bend's round on the bed (the round's
first 1.2 mm, 0.36 mm worst step), and the edges of
the "FRONT" relief (0.6 mm, 45.3 to 46.2 degrees); the fill lid has only its 1
mm top chamfer, which lies on the bed. The lugs' front faces, perpendicular to the plane, stand
vertical in print; the stop blocks' contact faces print facing up and back.

Slicer: **no brim** (Elegoo Slicer: Others, Skirt and brim, Brim type,
No-brim). Test print 1 used one and it fused into the walls. Enable bridge
detection, which is on by default in Orca-based slicers.

Purchased: four stick-on rubber feet, 10 mm; 1/2 inch TZe label tape.

Test print: `build/section/test_print_section_256.3mf` -- full size, on one
256 mm plate: the right-hand end bay of the body, cut at the left face of divider
4 so its left wall is a whole divider, the full height and depth (50.2 x 213 x
189 mm, hopper A and its flare included), the matching end of the pick lid and of
the fill lid, and the coupon turned 90 degrees. About 580 cm3 of solid (test print
3: 503), so roughly 8 hours in PETG. `python3 build/maquette/make_plate.py section
--export` rebuilds it from the sources. This is the one to print; see "The
full-size section" below. The 0.42 maquette plate
(`build/maquette/test_print_plate_256.3mf`) judges shape only.
`TEST_PRINTS.md` records what each test print showed.

## Print this first

`calibration_coupon.scad`. One fit depends on your printer rather than the
geometry: the joining rail in its groove. Test print 1's coupon read 0.50 mm per
side, but it was printed with a brim that fused into the walls; test print 2
(no brim) found the block loose on every stub down to 0.30; test print 3 (Generic
PETG, no brim) found the "0" stub (0.20) best but slightly tight, and the user
wants it a little looser. `rail_clear` became 0.215 (D47), but the slim rail's coupon
(0.265 .. 0.165) was too tight on every stub, so it is 0.40 now (D51), a best guess and a
one-number change in `params.scad`. The coupon brackets it: five male
rail stubs labelled -100, -50, 0, +50, +100 (clearances 0.50, 0.45, 0.40, 0.35,
0.30, relative to the default; `build/coupon/rail_coupon_256.3mf`) and a loose groove block cut exactly as the body
cuts its grooves. A step under about 0.025 mm is at the printer's resolution
limit. Turn the block over so the face
that was on the bed is UP, and drop it over each stub; the one that goes down with
hand pressure and does not rock, and comes back out by hand, is your fit. If it
is not "0", that label moves `rail_clear`. **The reading holds for the filament it
was printed in:** PETG reads differently from PLA, so print the unit in the same
filament, or run the coupon again. Two islands, 124 x 30 mm, no supports, no brim.

## The full-size section

`fit_section.scad` (`PART` = body, pick_lid, fill_lid) cuts the real
parts, so every clearance, wall and bridge is the real one. What to do with it:

1. **Filling tray A from the back (D42).** Pour real capsules into hopper A's
   flared mouth from a bottle, then take them from the front a few at a time: the
   pile should follow, and the last ones should not lodge in the corner (D41).
2. **Tray B's pile (D33).** Pour into hopper B: the pile stays below the wall in
   front of it.
3. **Pick lid (D38, D44).** Lay the lid end on the section: the lug drops in
   against the side wall directly behind the stop block and the lid does not
   slide down the slope. Pinch it and lift it off tilted about its back edge, and
   lower it back hinged from the back: neither may jam. Try it turned round.
4. **Groove (D43).** Lower a spare rail into the front groove; nothing tears at
   the break-out, and the buttress is no longer in the way in the front bin.
5. **Labels (D45).** Stick 1/2 inch tape on both strips on the front face.
6. **Fill lid.** Drop the lid end into the mouth: it goes in without forcing,
   sits flat without rocking, and lifts out cleanly.
7. **The left wall** (D46) is a whole divider now: handle it.
8. **The coupon** as above.

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

- **The pick lid is the one moving part**, if only on removal, and the review
  of revision 10 found that treating it as static had hidden a stop face that
  jammed. `probes/lid_retention.py` moves it: rest, 1/2/5 mm down-slope, a 30 mm
  straight lift and a lift along the plane's normal, a tilt about the back edge
  (0 to 15 degrees in 0.25 degree steps, back edge raised 0/1/3 mm) and a
  180-degree reversal, with exact boolean overlaps; `joints.json` declares the
  removal motions for `motion_sweep.py`. Run both.
- **The new heights.** Everything behind tray A rose: tray B's floor 105.6,
  hopper_rim 189, tray A's rim 77. The plane is 43.8 degrees (limit 45); the
  wall between the trays holds 14.7 over tray B's floor and tray B's pile is 6.4
  mm under it at repose 30, 1.95 at 25.
- **Tray A's floor angle** is a judgement from the repose estimate, not a
  measurement. If real capsules need more than 35 degrees, the one plane (40,
  with the chute) is the limit.
- **The chute mouth is 36 mm vertical; its true minimum is 26.0 mm**,
  perpendicular to the 40-degree floor from the back-bottom corner of the wall
  between the trays (the front-bottom corner gives 27.6): 1.0x a pill length (row B's outlet, which fed well in test print 2, measures 19.2 the same way; near a divider the D52 / D54 facets cut the throat to 12.6 at the divider face on row A and 9.6 on row B, which were 19.9 and 13.0 with the old 8 mm chamfers; a pill radius out they are 16.9 and 13.8),
  asserted. It matters only to a capsule standing on end. Row B's outlet is tighter (27 vertical) and fed
  well in test print 2.
- **The hanging wall between the trays** is now 35 mm tall below tray B's floor
  (it was 14), 2.4 mm thick, carried by the dividers and the outlet facets.
- **The porch ceiling is a flat 45 x 40 mm bridge in every bay** (D29). Check it
  on the first print for sag: it is now the longest flat in the part (the openings'
  crowns are 10 and 20 mm, D52, D54).
- **D52 / D54's corner trade.** The openings' crowns stayed put so the centre throat and the
  pile margins (D33) did not move; the corners paid. At outlet B's 20 mm crown the worst
  capsule pose clears its throat by +1.37 mm on the mesh sweep (+4.43 on tray A's mouth); at 10 mm
  it was -2.47. Watch the last capsules in hopper B, and the 20 mm crown for droop.
- **D53's clearance.** The lid's inside fillet leaves 0.10 mm to the body's front top
  edge at the nominal pose (0.141 on the stops, 0.046 at +0.2 mm up-slope, 0.010 at +0.3; it
  touches at about +0.36). By calculation only; the lid has about 0.86 mm of up-slope room from
  the stops against the 0.19 mm the tilt needs.
- The ~2 L of solid wedge under the chute is infill. The body is 2.3 L of
  solid; sliced at 899 g with 10% cubic infill and 2 wall loops (2.31 L solid).
- Bay width is **1.73x the longest pill** against a 2-3x mass-flow rule of
  thumb. Mitigated, not eliminated.
- The two `NEAR MISS` notes (0.150 mm, 0.100 mm since D53's fillet) are both lids' intended
  clearance, explained in `joints.json`.
- The rail clearance (0.40, D51) is a best guess for PETG and pending the new coupon. The fill lid's
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
feeds, that the new lugs hold and do not jam on a real print, and the rail fit at 0.215 then (0.40 now, D51); the
revision 10 section print is built to check all three. The `probes/` directory
holds the scripts behind every revision 10 number (`lid_retention.py`,
`corner_thickness.py`, `capacity.py`, `overhang_scan.py`).
