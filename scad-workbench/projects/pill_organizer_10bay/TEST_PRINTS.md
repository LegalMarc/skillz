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

## Test print 3 — planned, revision 10

**Printed:** `build/section/test_print_section_256.3mf`: the right-hand end bay
of the body to z 160 (49 x 146 x 160 mm), the matching pick-lid end, the fill
mouth and lid corners, and the coupon. No brim, no supports. It is about 2.5x
the volume of test print 2's plate (469 vs 191 cm3 of solid): expect 7 to 8
hours. Slicer settings as test print 2.

| Check | What to do | Pass |
|---|---|---|
| Row A refills (D36) | Pour capsules into the chute's open back end. When tray A is full, take capsules from the front, a few at a time | The pile follows the front: capsules slide forward from the chute and from the back of the tray without being grabbed at. Note any that rest on the floor |
| Row A pile depth | Look at tray A full | About 41 mm deep at the front wall, 8 mm under the wall's top; no capsule over it at rest |
| Row B (D33) | Pour into hopper B | Pile stays in tray B, below the wall in front of it |
| Pick lid stays on (D38) | Lay the lid end on the section, lugs dropping behind the pillar | Lugs go in without forcing; the lid does not slide down the slope; it moves under 1 mm before stopping against the pillar |
| Pick lid lifts | Lift it straight up by the finger notch | Comes off without catching on the pillar or buttress |
| Pick lid reversed | Try to fit it turned round | It cannot sit flat; the skirt hits the wall behind tray B |
| "FRONT" | Look at the skirt | Legible, no stringing, printed without support |
| Groove corner (D39) | Lower a spare rail into the front groove from above, handle the section | Nothing tears or cracks at the break-out; no flap inside tray A |
| Groove fit (D40) | Coupon: turn the block over, drop it over each stub | Report the label that goes down by hand without rocking (0.20 default = "0") |
| Fill-lid corner | As test print 2 | Unchanged at 0.30 |
| Bridges | Chute ceiling under tray B (now 45 x 40 mm), both outlet tops | No sag over 1 mm |
| Tray A floor | Look at the 35 degree floor | Clean, no layer artefacts that hold capsules |
