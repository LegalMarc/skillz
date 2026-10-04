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
| Front bins | A vertical fin halfway across each bin, with no apparent purpose | It was the porc## Test print 3 — planned, revision 10

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
