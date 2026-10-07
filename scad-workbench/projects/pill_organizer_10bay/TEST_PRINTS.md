# Test prints — pill_organizer_10bay

What each physical print showed, and what changed because of it. Photos are
kept off the repository; the findings are what matter.

## Test print 1 — 2026-10-03

**Printer:** Elegoo Centauri Carbon 2, PLA, slicer defaults with a brim.
**Printed:** `build/maquette/test_print_plate_256.3mf` at revision 7 plus the
review fixes (PR #43, #44): the 0.42-scale maquette body, pick lid and fill
lid, and the revision 7 calibration coupon.

| What | Result | Change, revision 8 |
|---|---|---|
| Rail coupon | The −150 stub fit best: the leftmost, the end of the range | `rail_clear` 0.35 → 0.50 (D31); coupon re-centred on 0.50 |
| Snap coupon | −150 "maybe a tiny bit too large, maybe okay" — but the tabs broke off all ten mini lids | Snap tabs removed (D30) |
| Fill lid (maquette) | "A pretty good fit" in its recess; its snap tabs broke off too | Fit kept at 0.30; lid now nests by gravity (D30) |
| Pick lid (maquette) | No way to tell how it goes on; the skirt notches line up with nothing | Locating lugs under its ends (D32); notches documented as grips |
| Front bins | A vertical fin halfway across each bin, with no apparent purpose | It was the porch splitter rib; removed, porch ceiling made flat (D29) |
| Back of every front bin | Ragged, stringy top edge | The 25° porch ceiling printing as an overhang; now a flat bridge (D29) |
| Top of every back-row bin | Ragged, stringy top edge | The 43 mm bridge over the hopper B outlet; corners chamfered (D29) |
| Brim | Fused into the walls, annoying to remove | Print with no brim (README, coupon header) |
| Right front corner | Torn where the rail groove breaks out through the top | At 0.42 scale the walls beside the groove are 1.5 mm; check at full size |

**Why the tabs broke:** every snap tab printed standing up, 1.2 mm thick and
12 mm tall. Flexing it bends it across its layer lines, the weakest direction
of any FDM print. That is an orientation problem no engagement value fixes,
which is also why the snap coupon's reading could not be used.

**Scale caveat:** at 0.42 every wall is about 1 mm and every bridge is printed
with a full-size 0.4 mm nozzle, so ragged edges and thin features look worse
than they will at full size. The rib, the tabs and the pick lid's lack of
location do not depend on scale.

## Test print 2 — 2026-10-03, revision 9

**Printer:** Elegoo Centauri Carbon 2, 0.4 nozzle, Elegoo PLA, 0.20 mm
Standard, 15% infill, **no brim**, no supports. Slicer estimate 3 h 7 min,
114 g.
**Printed:** `build/section/test_print_section_256.3mf` — full size: the right
end bay of the body to z 100, the matching pick-lid end, a fill-mouth corner
and a fill-lid corner, and the coupon.

| Check | Result | Change, revision 10 |
|---|---|---|
| Tray B fed from hopper B | Fed well, pile stayed in its tray. "A much better job of gravity feeding" than row A | None |
| Tray A fed through the chute | Filled at first, but as pills were taken out the next ones did not slide in; they had to be grabbed at | Porch 25° → 40° and tray A floor tilted toward the front (D36) |
| Bay size | "A little bit small" | Deeper trays, slightly wider bays, same 10 bays, still on one 256 mm plate (D37) |
| Pick lid | Slides straight off the slope. Placed reversed it also rides up on its own lug | Retention redesigned (D38), see below |
| Fill-lid corner | Drops in, sits, lifts out cleanly at 0.30 | Fit confirmed, `fill_lid_clear` stays 0.30 |
| Porch ceiling, outlet tops | Bridged. Light stringing across the top of tray B's opening | Cosmetic, none |
| Rail groove corner | Torn again at full size where the front groove breaks out through the top of the front wall; a thin flap inside tray A there cracked | Corner reinforced (D39) |
| Coupon, block bed-face up | Loose on every stub, including +200 (0.30 per side) | New coupon 0.30 → 0.10 (D40) |
| Pick-lid top face | A diagonal travel scar across the last layer | Cosmetic; slicer setting, none |

**Why the pick lid slides off.** The plate lies on a 44° plane and PLA on PLA
holds to about 17°, so something has to bear against a body face that faces
*back*. The skirt hangs outside the front face, 0.35 mm clear. Sliding down
the plane moves the lid forward and down, which takes the skirt *away* from
the face, so it never touches anything. The design note that it "cannot pass
the front face" was true and irrelevant: that only stops it sliding backward,
up the slope. The locating lug, in tray A, clears the scalloped front wall by
about 19 mm, so it slides over that too. Nothing in the suite tested the
direction of the stop; revision 10 adds a probe that does.

**Why the coupon read loose.** Test print 1 read 0.50 per side as the best
fit, on a coupon printed with a brim that fused into the walls. The brim and
its elephant foot narrowed the groove, so the loosest stub felt right. With
no brim the true fit is below 0.30.

## Test print 3 — 2026-10-04, revision 10

**Printer:** Elegoo Centauri Carbon 2, **Generic PETG** profile, no brim, no
supports, about 7 hours. Stringing was heavy in the groove, the bins and the lid:
a filament-drying and retraction matter (dry the PETG, tune retraction), not a
design change.
**Printed:** `build/section/test_print_section_256.3mf`: the right-hand end bay
of the body to z 165 (49 x 152 x 165 mm), the matching pick-lid end (91 x 139
mm, cut back far enough to include the right finger notch, so its left part
overhangs air), the fill mouth and lid corners, and the coupon. No brim, no
supports. About 500 cm3 of solid against test print 2's 191: expect about 8
hours. Slicer settings as test print 2. The section reaches 6.4 mm above tray
B's rim, so the wall behind the lid's back edge is present; it is not the full
wall (27 mm above the rim on the real body).

| Check | What to do | Pass |
|---|---|---|
| Row A refills (D36) | Pour capsules into the chute's open back end. When tray A is full, take capsules from the front, a few at a time | The pile follows the front: capsules slide forward from the chute and from the back of the tray without being grabbed at. Note any that rest on the floor |
| Row A pile depth | Look at tray A full | About 41 mm deep at the front wall, 11 mm under the wall's top; no capsule over it at rest |
| Row B (D33) | Pour into hopper B | Pile stays in tray B, below the wall in front of it |
| Pick lid stays on (D38) | Lay the lid end on the section, lugs dropping behind the stop blocks. Tip the section so the plane is up the slope | Lugs go in without forcing; the lid does not slide down the slope; it moves 0.5 mm and stops against the block |
| Lift by the front edge | The lid piece is 91 mm wide on a 49 mm body section, so its centre of mass is 2-3 mm inside the cut half-divider and lifting at the notch (x 167) rolls it about the right side wall: that tests nothing. **Hold the overhanging left end level with your other hand (or prop it on a spacer at plane height), then lift by the skirt directly over the section** and let the lid tilt about its back edge | A pass: the lug leaves the stop block after about 3.6 to 4 degrees of tilt (about 7 mm of rise at the front), with no catch or drag at any point; the lid may need to creep up the slope by a fifth of a millimetre as it starts, which is expected (the lugs touch the stops at rest) |
| Lower it hinged from the back | Same support. Rest the back edge on the plane and lower the front | The lugs find the gap behind the blocks and the lid settles 0.5 mm from the stops without catching |
| Lift straight up, then draw forward | Lift it vertically 8 mm or more, then pull it toward you | Comes off clean. (On the full body a straight lift beyond 26 mm meets the fill lid's pull lip; lift-then-forward never does)  |
| Pick lid reversed | Try to fit it turned round | It cannot sit flat; the skirt hits the wall behind tray B |
| "FRONT" | Look at the skirt | Legible, no stringing, printed without support |
| Groove corner (D39) | Lower a spare rail into the front groove from above, handle the section | Nothing tears or cracks at the break-out; no flap inside tray A |
| Groove fit (D40) | Coupon: turn the block over, drop it over each stub | Report the label that goes down by hand without rocking (0.20 default = "0") |
| Fill-lid corner | As test print 2 | Unchanged at 0.30 |
| Bridges | Chute ceiling under tray B (now 45 x 40 mm), both outlet tops | No sag over 1 mm |
| Tray A floor | Look at the 35 degree floor | Clean, no layer artefacts that hold capsules |

The pick lid rows are **provisional for the full lid**: the section's lid piece
is a 91 mm end with one lug and one notch, on a body section 49 mm wide, so it
tests the stop faces, the clearances and the back-edge swing, not how the whole
229 mm lid balances in one hand.

### Results

| Check | Result | Change, revision 11 |
|---|---|---|
| Row A refills (D36) | **Yes, appropriately.** The 35 degree floor and the 40 degree chute work. The last couple of (larger) capsules lodged in the pocket at the front-bottom corner of tray A, where the floor meets the front wall, standing or lying there, hard to grab | Corner beads (D41) |
| Filling tray B from hopper B | Very easy | None |
| Filling tray A from the back | "A little harder" (on the section, the chute's cut-open back end; on the full module hopper A's mouth is the narrow one, about 41 against B's 61) | Hopper A flares for pouring (D42) |
| Bin size | Not raised again | None |
| Pick lid on | Fits on nicely; **the lug ("nub") keeps it properly seated: pass** | Lug and stop block unchanged |
| Pick lid off | Lifts off fine. The user does not want finger notches or anything hung from it: they pinch it between thumb and forefinger | Notches removed (D44) |
| Section lid piece | The big overhang (widened in revision 10 to include a notch) was confusing | Back to the section's width (D46) |
| Rail and groove | Look overbuilt ("lock and key"); the buttress protrudes too far into the front bin. The user suggested the rail match the vertical dividers | Slim rail, groove and buttress (D43) |
| Section left wall | The thin LEFT wall cracked easily: the 1.2 mm half-divider split away from the front wall, a vertical separation up from the base at the divider/front-wall junction. Not a full-module defect | Cut at a full divider (D46); fillets at every divider/front-wall junction in the full module |
| Labels | The upper strip, on the wall between the trays and reached over tray A, is awkward and partly hidden by the rail and groove | Both labels on the front face (D45) |
| Back cubby | The back pocket with a low retaining wall is wanted (it holds a chapstick or two). It exists in the full design (`cubby_lip_h` 30 then, 73 since D50); the section just did not include it | No change; the revision 11 section shows its opening |
| Coupon, block bed-face up (Generic PETG) | The "0" stub (0.20 per side) fit best but slightly tight; wanted a little looser, around -10 to -15 (0.21 to 0.215), still snug but able to move back out | `rail_clear` 0.215 and a finer coupon (D47). **The reading is for PETG:** the final unit should be printed in the same filament, or the coupon re-run |
| Fill-lid corner | Drops in and fits nicely at 0.30, again | None |
| Groove corner (D39) | Not reported as torn | Bevel kept, slimmed with the rail (D43) |
| Bridges, tray A floor | Not reported | None |
| Stringing | Heavy in the groove, the bins and the lid | Slicer/filament: dry the PETG, tune retraction |

Watch items from the final review of revision 10 (no change made; act only if
the print shows a problem):

| Where | What to look for | If it fails |
|---|---|---|
| Rail-1 buttress, back-top edge inside tray A (about x 234, y 37, z 112) | A 46 degree edge, 7 mm long, under the lid. Chipping or a ragged edge | Add a 1 mm chamfer there |
| Groove mouth in the side-wall top | The D39 chamfer widens it to about 17 mm. A capsule dropped there with the lid off can fall into the groove, as it could before | Note it; a cap or narrower chamfer is a revision 11 question |

## Test print 4 — printed 2026-10-04, revision 11 section (results)

**PRINTED** (`test_print_4_rev11` on the printer, PETG), after revision 12 had been designed as the
final print. Its photos and the user's feedback drove revision 13 (D51 to D54). Nothing else was reported:
the planned checks below are not answered, so the final print is still the first print of every
feature in them. Results:

| Watch | Result | Change, revision 13 |
|---|---|---|
| Arches over the openings (the tray A mouth and outlet B) | Drooped a little, strung along the flat top; "make them like half octagon instead of half hexagon" | Half octagons: 45 degree facets and a short crown flat, 10 mm (tray A) and 20 mm (outlet B, D54) instead of 29 (D52, D54) |
| Pick lid | Looks like two rectangles welded together; wants a more unibody profile | One profile, constant 3.0 wall, a fillet inside the bend and a round outside, one end chamfer round it (D53) |
| Coupon (slim rail, 0.265 .. 0.165) | Every stub too large for the slot | `rail_clear` 0.40 as a best guess (D51); new coupon 0.50 .. 0.30 |
| D51 coupon (0.50 .. 0.30), printed 2026-10-05 | Loose on every stub, even 0.30 | `rail_clear` 0.28 and a 0.30 .. 0.26 coupon (D55). **Reading void, see below** |
| D55 coupon (0.30 .. 0.26), printed 2026-10-06 | Loose on every stub | **Reading void, see below.** D56 |
| The groove block against the neighbouring stub (found after the D55 print, from the user: "the rail needs more space between the nubs to fit the test block") | At the old 18 mm pitch the seated block stood 0.4 mm from the next stub (groove bottom on the tip) or 0.0 mm (mouth on the root), and overhung the plate edge by 5 mm at the first stub: it rocked against the neighbour, so the D47 (slim rail), D51 and D55 readings are invalid; `probes/coupon_fit.py` reproduces it on the D55 mesh | D56 coupon: 28 mm pitch, a PLAIN row 0.30 .. 0.10 and a crush-RIBS row (0 .. 0.20 interference), `rail_clear` 0.30 as a starting point |
| D56 coupon (`build/coupon/rail_coupon_256.3mf`) | **Planned, not printed.** Block bed-face UP over each stub; PLAIN: the stub that slides on by hand without rocking; RIBS: the least interference with no rattle that still slides on and off by hand | Set `rail_clear` from the plain row, or ask for crush ribs on the body's male rail from the ribs row |
| Everything else in the planned checks | Not reported | None |

Planned checks, kept for the final print:

**Printed:** the revision 11 section plate (`build/section/test_print_section_256.3mf` at commit 7d99c97; that path now holds the revision 13 section): the right-hand end bay cut at
the left face of divider 4, the whole height and depth (50.2 x 213 x 189 mm), the
matching pick-lid end and fill-lid end at the section's own width, and the coupon
turned 90 degrees. About 580 cm3 of solid: expect about 8 hours in PETG. Dry the
filament first. Slicer settings as test print 3 (no brim, no supports).

| Check | What to do | Pass |
|---|---|---|
| Fill tray A from the back (D42) | Pour from a bottle into hopper A's flared mouth | Easier than tray B was last time (mouth 57 mm under the lid, 60 at the rim, against B's 63 on the module); nothing spills over the flare |
| Row A refills (D36) | Take capsules from the front a few at a time | As test print 3: the pile follows |
| The last capsules (D41) | Run tray A down to the last few, including the larger ones. Where one lodges at the wall, push its end along the floor against a rib (three small half-round ribs per bay, 5 mm across) | The end rides up the rib and the capsule tips so a finger can take it; none stays flat in the corner. If one still does, the answer is a filled wedge, not bigger ribs |
| Front-right corner of tray A | Look at the stop block, filler, buttress and beads together | No lump a capsule wedges against (the probe finds no pocket over 3 mm); no gap narrower than a capsule that is deeper than a cusp |
| Pick lid on / off (D38, D44) | Seat the lid end; pinch the skirt and plate edge and lift | Seats by its lug as before; lifts off between thumb and forefinger without a notch |
| Rail and groove (D43) | Lower a spare rail into the front groove; slide the coupon block | Stiff enough; nothing tears at the break-out; the buttress no longer gets in the way in the front bin |
| Coupon (D47, PETG) | Block bed-face up over each stub | Report the label that goes down by hand and comes back out, snug but free; centre is 0.215 (superseded: the slim rail's coupon read too tight; every slim-rail reading is void since the block hit the neighbouring stub, D56; the coupon is now `build/coupon/rail_coupon_256.3mf`) |
| Labels (D45) | Stick 1/2 inch tape on both strips | Both on the front face, the back-row (B) strip above the front-row (A) strip, both visible with the lid on |
| Left wall (D46) | Handle the section | The left wall (a whole divider) does not crack; the divider / front wall corners have a fillet |
| Fill-lid end (D30) | Drop it into the mouth | Fits at 0.30 with the longer lid (121 mm); lifts out cleanly |
| Cubby opening | Look at the back | Low retaining wall (30 mm) across a pocket that takes a chapstick or two |
| Stringing | Look at the groove, bins and lid | Much less than test print 3 once the filament is dry |


## Final print — planned, revision 12 (with D51 to D54 from revision 13)

**Printed:** three plates, `build/final/final_body_256.3mf`, `final_pick_lid_256.3mf`,
`final_fill_lid_256.3mf`. PETG (dried), no brim, no supports, 15% infill. **Before the body: read the
D56 coupon** (`build/coupon/rail_coupon_256.3mf`, not yet printed). Set
`rail_clear` to the plain row's best clearance and run `python3 build/maquette/make_plate.py final --export` first:
the body bakes in the 0.30 starting point. Test print 4 reported only the arches, the lid and the coupon, so
the other revision 11 features below have never been checked on a print; the edge pass (D48) is new
too. Report anything that is not a pass.

| Watch | Where | What to look for | If it fails |
|---|---|---|---|
| D41 ribs | tray A, front-bottom corner, three per bay | Print clean as half-round ribs with a rounded end; a capsule slid to the wall rides up a rib's side and tips | A filled wedge, not larger ribs |
| D42 flare | hopper A's back wall | A clean 60-degree lean (30 degrees from vertical: the outer face is a printable 30-degree overhang, the inner face leans up); pouring from a bottle goes in without spilling | Shallower lean or a wider mouth |
| D43 slim rail and groove | right wall (groove) and left wall (rail), both ends | Rail enters the groove by hand at `rail_clear` (0.30 from D56, to be set from the D56 coupon), snug, comes out by hand; no tear at the break-out | Move `rail_clear` by one 0.05 step (the D56 coupon is the guide) |
| K1 skin cap | the 2.4 mm skin behind the rail-1 groove, front bin | No wobble or tear; flat top, 2.3 mm above the lip at worst | Thicken or lower the cap |
| D45 labels | the front face, two stacked strips | Both strips visible with the lid on, tape fits the 0.5 recess | |
| Divider fillets | tray A and tray B front-wall corners (D46, D48) | Smooth quarter-rounds, no gap between them and the divider | |
| Bed chamfer (D48) | body base and the four foot-pad recess mouths | A 0.5 mm bevel on the first layers; a 10 mm stick-on foot enters its recess | Raise `bed_chamfer` toward 0.6 |
| Side-face rounds (D48) | both side faces, along the pick plane, the step and the rim | Smooth rounds, no ragged edge, no thin shell | |
| Scallop, mouth and cubby chamfers (D48) | front wall floors, fill-mouth rim, cubby mouth | Clean 45-degree faces; the scallop chamfer fades out up the corner arcs | |
| Cubby lip (D50) | the back wall's bottom 76 mm, across the cubby mouth | A 2.8 mm wall standing 76 mm above the bed with a clean 0.5 mm chamfer on its top edge, no wobble or tear while printing; the pocket behind it takes a lip balm and a pill cutter upright | Thicken the lip or lower `cubby_lip_top` |
| Lid fit | pick lid on the body | Seats on its lugs, no jam on lift (probes pass; first time with the rounded side faces under the lid's ends) | |
| Half-octagon openings (D52) | the tray A mouth (under the wall between the rows) and outlet B (under hopper B's front wall), every bay | A 10 mm (tray A) and 20 mm (outlet B, D54) crown flat that prints without sag or strings, and clean 45-degree facets either side (test print 4 drooped and strung along the old 29 mm flat). Pour a few capsules into hopper B and watch them leave outlet B: look for any that lodge in the side corners (the throat a pill radius from a divider is 13.8 mm, a capsule 11; the mesh sweep's worst pose clears by +1.37 mm) | If outlet B's 20 mm still droops, shorten `outletB_crown_flat` and re-run `probes/outlet_arch.py`: it fails below +1.0 mm of worst-pose margin (about 19 mm); if capsules lodge, lengthen it |
| Porch ceiling, not changed by D52 | the flat 45 x 40 mm ceiling under tray B, every bay | The largest bridge left in the body, 2.2 times outlet B's crown and 4.5 times tray A's. Look for sag or strings across it; none was reported on test print 4 | A shallow gable (the vault, D26) over the porch, which costs chute height |
| One-piece pick lid (D53) | the bend between plate and skirt, outside and inside | One surface from plate through the bend to the skirt, no seam line. The 1.5 mm round on the bed edge prints without ragged first layers (worst step 0.36 mm); the 1.0 mm end chamfer is one bevel round the bend; the skirt is the plate's thickness | Go back to a 45 degree chamfer on the outside of the bend, as in revision 12 |
| Lid on the body (D53) | the lid's inside fillet beside the body's front top edge | Seats on its lugs and lifts off by pinching the skirt as before. The fillet leaves 0.10 mm to the body's front edge at the nominal pose by calculation (0.14 before; 0.141 on the stops, 0.046 at +0.2 mm up-slope, touching at about +0.36 mm, where the skirt used to touch at +0.485), so a lid that rubs when pushed up-slope is this | Float the lid higher (`pick_lid_gap` 0.2 toward 0.3; it moves the stops' clearance too) or lower `pick_bend_in_r` (its assert is `>= lid_t`: relax it knowingly) |
| Fill lid | in the mouth | 0.30 all round, lifts out by the lip; the lip's underside bevel is a fingertip rest | |
| Stringing | groove, bins, lids | Much less than test print 3 once the PETG is dry | Dry longer; tune retraction |
| Print time | body | About 960 g at 15% infill: start on a full spool | |
