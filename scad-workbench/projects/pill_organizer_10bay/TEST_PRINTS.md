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
