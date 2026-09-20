# Calculations — pill_organizer_10bay

All lengths mm, all angles degrees. `tan(48) = 1.110613`.

Revision 2. Revision 1 alternated tray / mouth / tray / mouth front-to-back and
used four lids. This revision groups **both fill mouths at the back under one
lid and both pick trays at the front under one lid**, which is a different
machine, not a detail change — see "The crossing" below.

## Inputs

| Input | Value | Source | Status |
|---|---|---|---|
| Pill envelope (length x diameter) | 26.0 x 11.0 | User, D2 | OK |
| Build volume | 256 x 256 x 256 | User sketch | OK |
| Usable footprint / height | 243 x 243 x 243 | 256 less 13mm skirt/brim + exclusion (D3) | OK |
| Bays per row | 5, two rows | User | OK |
| Lids | exactly 2, grouped by function | User, D8 | OK |
| Target charge per bay | ~90-day supply, one large capsule/day | User | OK |
| Size-00 capsule fill volume | 0.95 mL | Standard capsule table | OK |
| Bulk packing fraction, loose capsules | 0.58 | Random loose packing of cylinders | PATIKRINTI — estimated |
| Static angle of repose, gelatin capsule on PLA | ~30 | Literature figure | PATIKRINTI — estimated |

Both `PATIKRINTI` rows set margins, not fits. The design clears both by a wide
margin (ramps at 48 vs ~30 repose; capacity 1.85x-2.58x), and neither can make
one part fail to fit another. They are resolved by loading the finished unit.

## The crossing — why this revision is shaped the way it is

Grouping the mouths at the back and the trays at the front forces one flow to
cross the other. This is topological, not a detailing problem:

- **Hopper B** is the *front* mouth and feeds tray B, the tray directly in front
  of it. Plain ramp, no crossing.
- **Hopper A** is the *back* mouth but feeds tray A, the *front* tray. Its chute
  has to duck under tray B and under hopper B's ramp — 159 mm enclosed.

Tray B's height is then set by that chute, not chosen:

| Quantity | Formula | Value |
|---|---|---|
| Chute A floor at tray B's back | `base_z + (yB_tray1 - yA_tray1) x tan(48)` | 45.65 |
| Minimum tray B floor | `+ chute_clear + chute_ceil` = `45.65 + 33 + 3` | **81.65** |
| Tray B floor, chosen | with margin | 84.0 |
| Resulting rim-to-rim step | `trayB_rim - trayA_rim` | **48.0** |

`params.scad` asserts all three clearances — under tray B, and at both ends of
hopper B's ramp — so the two feeds cannot silently intersect.

## Derived — width (unchanged)

| Quantity | Formula | Value |
|---|---|---|
| Module width | chosen, <= 243 | 230.0 |
| Bay clear width | `(230 - 2x2.8 - 4x2.4) / 5` | 42.96 |
| Bay width vs pill length | 42.96 / 26.0 | 1.65x |
| Bay centres | `24.28 + i x 45.36` | 24.28, 69.64, 115.0, 160.36, 205.72 |

## Derived — section, front to back

| Feature | Y span | Z |
|---|---|---|
| Front outer wall | 0 .. 2.8 | to the pick plane |
| **Tray A** (front row) | 2.8 .. 38.8 | floor 3.0 |
| Wall between the trays | 38.8 .. 41.2 | retains tray B by 15.6 |
| **Tray B** (back row) | 41.2 .. 77.2 | floor 84.0, rim 122.0 |
| Hopper B front wall | 77.2 .. 79.6 | outlet top 114.0 |
| **Hopper B mouth** | 79.6 .. 151.6 | ramp 86.7 .. 166.6 |
| Wall between the hoppers | 151.6 .. 154.0 | cut to the seat plane |
| **Hopper A mouth** | 154.0 .. 202.7 | floor 130.9 .. 185.0 |
| Back outer wall | 202.7 .. 205.5 | |
| **Chute A** (the crossing) | 38.8 .. 154.0 | constant 33.0 clear, at 48 |
| **Overall** | | **230.0 x 205.5 x 200.0** |

Both mouths finish at `hopper_rim = 200.0`, which is what lets one flat lid
cover both. Both trays finish on one 31.9 degree plane from 74.0 at the front
face to 122.0 at tray B's rim, which is what lets one flat lid cover both.

## Derived — capacity (measured from the rendered cavity meshes)

| Row | Per bay | vs 147.4 mL charge | at 80% fill |
|---|---|---|---|
| Row A — front tray, back mouth, crossing chute | **380.9 mL** | 2.58x | 2.07x |
| Row B — back tray, front mouth, plain ramp | **272.8 mL** | 1.85x | 1.48x |

Row A is the larger because its chute *is* storage: the 159 mm the crossing
costs in length it gives back as volume. Total across ten bays: **3.27 L**.

## Derived — flow and escape paths

| Check | Value | Status |
|---|---|---|
| Chute A clear section | 33.0, constant | OK — 1.27x pill length |
| Row B outlet | 30.0 | OK — 1.15x pill length, 2.7x pill diameter |
| Ramp / chute angle vs repose | 48 - 30 = 18 margin | OK |
| Ramp underside overhang from vertical | 42 | OK — inside the 45 FDM band |
| Wall between trays, above tray B's floor | 15.6 | OK — 1.4x pill diameter |
| Bay width vs pill length | 1.65x | PATIKRINTI — see note |

Arch note, unchanged from revision 1: 42.96 mm is 1.65x the longest pill against
a 2x-3x rule of thumb, so two capsules can in principle span a bay. Mitigated by
the steep ramp, the tall section and intermittent draw, not eliminated. An
occasional tap may be needed, as with any gravity pill dispenser.

**New risk in this revision**: chute A is enclosed for 159 mm. It is open at
*both* ends — tray A at one end, hopper A's mouth at the other — so a dowel can
be pushed through it, and both ends are declared in `bores.json` and walked by
`check_bore_reachability.py`. But it cannot be reached into the way an open ramp
can. That is the price of the grouping, and it is worth stating plainly.

## Derived — lids

| Quantity | Value | Status |
|---|---|---|
| Pick plane slope | `atan(48 / 77.2)` = 31.9 | OK |
| Pick lid | one flat plate, 229.0 x 79.85, lift-off | OK |
| Pick lid retention | hook over the front top edge | OK — PLA/PLA grips to ~17, slope is 32, so friction alone would not hold |
| Fill lid | one flat plate, 223.8 x 124.7, drop-in | OK |
| Fill lid retention | two cantilever snap tabs, 10.0 x 1.2, 0.8 engagement | PATIKRINTI — uncalibrated |
| Fill tab peak bending strain | `3 t d / 2L^2` = 1.44% | OK — under the 1.5% budget |
| Rail socket clearance, per flank | 0.35 | PATIKRINTI — uncalibrated |

Neither lid is hinged, and that is forced rather than chosen — see D9. An
L-section lid bridging the 48 mm rim step has its mass centre about 48 mm below
any back-top pivot, which puts its over-centre angle near 144 degrees: it cannot
be reached, so the lid falls shut every time. A front pivot runs the far corner
into the benchtop at about 24 degrees.

## Physical assembly narrative (SKILL.md §0.6)

**Pick lid.** *Insertion*: lay it on the plane and let the hook drop over the
front top edge; lift the front edge to remove. Nothing else is on that path.
*Neighbours*: `pick_plate` and `pick_hook`, declared in `fusions.json`; the hook
reaches 1 mm above the plate's underside so the two weld volumetrically — tracing
the plate's own faces exactly produced a **non-watertight** lid, which silently
degraded every boolean check downstream. *Retention*: the hook, not friction.
*Purchased fit*: none.

**Fill lid.** *Insertion*: straight down into the shared mouth, which is full
width at the rim and steps in below the seat plane via a 45 degree chamfer. Both
tabs flex inward 0.8 mm and spring into their pockets. Two obstructions on that
path were found by measurement: the seat lips ran directly under the tabs, and
the back tab reached below hopper A's floor at the back wall — the tab is now
10 mm and thinned to 1.2 mm to stay inside the strain budget at that length.
*Neighbours*: `fill_plate` and `fill_tabs`, declared. *Retention*: the barbs'
flat tops on their pocket ceilings, with 0.3 mm of lift slop — which is why the
lid is modelled floating 0.15 mm above its seat rather than resting on it.

**Joining rails.** *Insertion*: lower the next module alongside; both grooves run
from their floor clear out of the top of the side wall, so the rails engage
progressively with no minimum lift. Declared in `bores.json`. *Neighbours*: the
buttresses that carry the grooves are **intersected with the outer silhouette**
rather than capped at a guessed height — capping at the rail centreline left one
proud of the sloped pick plane and it speared the pick lid; capping at the
footprint's low end left a 0.3 mm wedge of wall that tore a hole in the mesh.
*Retention*: gravity and the undercut, which is correct for a bench organizer.

## Measured, not calculated

| Quantity | Measured | How |
|---|---|---|
| Row A capacity | 380.9 mL/bay | volume of the rendered cavity mesh |
| Row B capacity | 272.8 mL/bay | same |
| Flat bridged ceiling, body | 1105 mm^2 | face-normal scan, down from 9409 before the chute ceiling was sloped |
| Flat bridged ceiling, fill lid as printed | 35 mm^2 | same, in its flipped print orientation |
| Flat bridged ceiling, pick lid | 0 mm^2 | same |

## Unresolved

Every `PATIKRINTI` is either an uncalibrated snap/slide fit (rail socket, fill-lid
barb) — resolved by printing the calibration coupon, not by looking anything up —
or an estimated bulk-solids figure that sets a margin the design is well clear of.
