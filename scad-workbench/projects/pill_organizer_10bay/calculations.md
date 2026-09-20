# Calculations — pill_organizer_10bay

All lengths mm, all angles degrees. `tan(48) = 1.110613`.

## Inputs

| Input | Value | Source | Status |
|---|---|---|---|
| Pill envelope (length x diameter) | 26.0 x 11.0 | User (session answer, D2) | OK |
| Build volume | 256 x 256 x 256 | User sketch ("256mm Build Volume") | OK |
| Usable footprint / height | 243 x 243 x 243 | 256 less 13mm skirt/brim + exclusion margin (D3) | OK |
| Bays per tier | 5 | User sketch ("10 cubic pill holders", two rows of five) | OK |
| Target charge per bay | ~90-day supply, one large capsule/day | User brief | OK |
| Size-00 capsule fill volume | 0.95 mL | Standard capsule-size table | OK |
| Bulk packing fraction, loose capsules | 0.58 | Random loose packing of cylinders, standard figure | PATIKRINTI — estimated, not measured |
| Static angle of repose, gelatin capsule on PLA | ~30 deg | Literature figure for smooth pharmaceutical solids | PATIKRINTI — estimated, not measured |

Both `PATIKRINTI` rows are *margin* inputs, not fit dimensions: they set how much
capacity and how much ramp-angle headroom the design carries, and the design is
deliberately well clear of both (ramp at 48 deg vs ~30 deg repose; capacity ~1.2x
the computed 90-day figure). Neither can make a part not fit another part. They are
resolved by the user loading the finished unit, not by a number this session can look up.

## Derived — width

| Quantity | Formula | Value | Status |
|---|---|---|---|
| Module width | chosen, <= 243 | 230.0 | OK |
| Outer wall | chosen | 2.8 | OK |
| Divider wall | chosen | 2.4 | OK |
| Interior X span | 230.0 - 2 x 2.8 | 224.4 | OK |
| Bay clear width | (224.4 - 4 x 2.4) / 5 | 42.96 | OK |
| Bay width vs pill length | 42.96 / 26.0 | 1.65x | OK — a pill can lie across a bay in any orientation |
| Bay pitch | 42.96 + 2.4 | 45.36 | OK |
| Bay centres | 24.28 + i x 45.36, i = 0..4 | 24.28, 69.64, 115.0, 160.36, 205.72 | OK — centre bay at module_w/2 |

## Derived — depth (Y, front to back)

| Feature | Y span | Value | Status |
|---|---|---|---|
| Front outer wall | 0 .. 2.8 | 2.8 | OK |
| Pocket A (pick tray) | 2.8 .. 38.8 | 36.0 deep | OK |
| Hopper A front wall | 38.8 .. 41.2 | 2.4 | OK |
| Hopper A mouth / ramp run | 41.2 .. 113.2 | 72.0 | OK |
| Hopper A back wall = pocket B front wall | 113.2 .. 116.0 | 2.8 | OK |
| Pocket B (pick tray) | 116.0 .. 152.0 | 36.0 deep | OK |
| Hopper B front wall | 152.0 .. 154.4 | 2.4 | OK |
| Hopper B mouth / ramp run | 154.4 .. 226.4 | 72.0 | OK |
| Back outer wall | 226.4 .. 229.2 | 2.8 | OK |
| **Total depth** | | **229.2** | OK — 13.8 under the 243 limit |

Pocket A and pocket B are both 36.0 x 37.0 in section and both span 38.8 in Y from
their own front face to their own hopper wall, so **one pick-lid part serves both**.
Hopper A and hopper B both present a 72.0 x 224.4 mouth, so **one fill-lid part
serves both** (D7).

## Derived — height (Z)

| Quantity | Formula | Value | Status |
|---|---|---|---|
| Base plate | chosen | 3.0 | OK |
| Ramp angle | chosen (D4) | 48 deg | OK |
| Ramp rise over its 74.4 run | 74.4 x tan(48) | 82.629 | OK |
| Ramp A at pocket lip (Y=38.8) | base | 3.0 | OK |
| Ramp A at hopper front wall (Y=41.2) | 3.0 + 2.4 x tan(48) | 5.665 | OK |
| Ramp A at hopper back wall (Y=113.2) | 3.0 + 82.629 | 85.629 | OK |
| Hopper A rim = tier B floor | chosen, > ramp top | 104.0 | OK — 18.37 freeboard for pouring |
| Pocket A floor / rim | 3.0 / 3.0 + 37 | 3.0 / 40.0 | OK |
| Outlet A gap (under hopper A front wall) | chosen | 30.0, top at Z 33.0 | OK |
| Outlet top vs pocket rim | 40.0 - 33.0 | 7.0 below the lid plane | OK — see "escape path" below |
| Ramp B at Y=154.4 | 104.0 + 2.4 x tan(48) | 106.665 | OK |
| Ramp B at Y=226.4 | 104.0 + 82.629 | 186.629 | OK |
| Hopper B rim | 186.629 + 18.371 | 205.0 | OK |
| Pocket B floor / rim | 104.0 / 141.0 | 104.0 / 141.0 | OK |
| **Total height** | | **205.0** | OK — 38 under the 243 limit |

Pocket B rim at Z 141.0 = pocket A rim 40.0 + 101.0; tier B is tier A raised by
101.0 with an extra 3.0 of floor slab, i.e. `tier_b_lift = hopper_a_rim - base_t = 101.0`.

## Derived — capacity

| Quantity | Formula | Value | Status |
|---|---|---|---|
| Hopper A section area | 72.0 x 104.0 - 72.0 x (5.665 + 85.629)/2 | 4201 mm^2 | OK |
| Hopper volume per bay | 4201 x 42.96 | 180,480 mm^3 = 180.5 mL | OK |
| Pick tray volume per bay | 36.0 x 37.0 x 42.96 | 57,220 mm^3 = 57.2 mL | OK |
| Total per bay | | **237.7 mL** | OK |
| 90 size-00 capsules, loose | 90 x 0.95 / 0.58 | 147.4 mL | OK |
| Margin on a 90-day size-00 charge | 237.7 / 147.4 | **1.61x** | OK |
| Usable hopper fill at angle of repose (~80%) | 180.5 x 0.8 + 57.2 | 201.6 mL | OK — still 1.37x |
| Equivalent size-0 capsules (0.68 mL) | 201.6 x 0.58 / 0.68 | ~172 capsules | OK |

Honest statement of the result: **one bay holds a 90-day once-daily charge of the
largest pill class with ~35% to spare, and comfortably more of anything smaller.**
It does not swallow a 400-count bottle in one pour.

## Derived — flow and escape paths

| Check | Formula | Value | Status |
|---|---|---|---|
| Outlet gap vs pill length | 30.0 / 26.0 | 1.15x | OK — any pill passes in any orientation |
| Outlet gap vs pill diameter | 30.0 / 11.0 | 2.73x | OK — above the ~2x slot rule for non-cohesive solids |
| Bay width vs pill length (arch across the slot) | 42.96 / 26.0 | 1.65x | PATIKRINTI — see note |
| Ramp angle vs angle of repose | 48 - 30 | 18 deg margin | OK |
| Ramp underside overhang from vertical | 90 - 48 | 42 deg | OK — inside the 45 deg FDM band |
| Gap between pick-lid rear edge and hopper wall | 38.8 - 36.5 | 2.3 | OK — 7.0 above the outlet top, and 2.3 < 11.0 pill dia |

Arch note: a 42.96 mm slot is 1.65x the longest pill, and the rule of thumb for
reliable mass flow is 2x-3x the largest particle. Two 26 mm capsules *can* in
principle span 42.96 mm. This is mitigated, not eliminated: the ramp is 18 deg
above the repose angle, the slot is 30 mm tall so an arch has no abutment above it,
and the flow is intermittent (a few pills at a time) rather than continuous. The
honest statement is that an occasional tap on the case may be needed, which is
normal for every gravity pill/candy dispenser. Widening the bay past 42.96 is only
possible by dropping to 4 bays per tier, which loses two pill types.

## Derived — joining rails (D5)

| Quantity | Value | Status |
|---|---|---|
| Profile | trapezoid, explicit top/bottom widths, extruded along Z | OK |
| Root width (at the module face) | 7.0 | OK |
| Tip width (outboard) | 11.0 | OK |
| Protrusion | 5.0 | OK |
| Validity condition | tip 11.0 > root 7.0 > 0 -> a real trapezoid, no self-intersection | OK |
| Flank angle, implied | atan(5.0 / 2.0) = 68.2 deg from the face | OK — reported, never used as an input |
| Socket clearance, per flank | 0.35 | PATIKRINTI — uncalibrated, tier 2 |
| Rail 1 centre / Z span | Y 77.2, Z 10 .. 95 | OK — side wall is 104 tall there |
| Rail 2 centre / Z span | Y 190.4, Z 10 .. 190 | OK — side wall is 205 tall there |
| Rail separation | 113.2 | OK — resists yaw between ganged modules |

The rail is deliberately parameterised by two widths rather than a flank angle:
`INCIDENTS.md` 2026-08-30 records a dovetail defined as `h * tan(50)` that exceeded
half its own width and rendered a self-intersecting bowtie with a non-watertight
mesh. Two explicit widths cannot produce that shape, and `params.scad` asserts it.

## Derived — pick-lid hinge

| Quantity | Value | Status |
|---|---|---|
| Rod diameter | 6.0 | OK |
| Rod axis (tier A) | Y 33.7, Z 47.0 | OK |
| Rod axis (tier B) | Y 146.9, Z 148.0 | OK — tier A lifted by 101.0 |
| C-clip bore | 6.3 (0.15 radial running clearance) | PATIKRINTI — uncalibrated, tier 2 |
| C-clip wall | 1.8, outer radius 4.95 | OK |
| Clearance, clip OD to hopper wall face | 38.8 - 33.7 - 4.95 | 0.15 | OK — the wall is the backstop |
| Open angle | ~95 deg, past vertical, gravity-held | OK — verified by motion sweep, not by eye |
| Clip snap gap | 4.8 (< 6.0 rod) | PATIKRINTI — uncalibrated, tier 2 |

## Unresolved

Every `PATIKRINTI` above is one of two kinds:

1. **Uncalibrated snap/slide fits** (rail socket clearance, C-clip bore, clip snap
   gap). `doctor.py` reports no calibration profile on this machine, so these are
   geometry-only at tier 2. A calibration coupon is proposed in the final report —
   this is not a number that can be looked up, it is a property of the user's
   printer and filament.
2. **Estimated bulk-solids figures** (packing fraction, angle of repose) which set
   margins, not fits, and which the design is well clear of.

---

# Physical assembly narrative (SKILL.md §0.6)

Written before the geometry, per feature that shares a `union()` or mates with
a separately printed part. This is the step that no geometry check can perform.

## Pick lid on its hinge rod

**Insertion path.** The lid is pressed straight down onto the rod. Each C-clip's
mouth faces forward and flares 0.7 mm at its outer surface, so the rod finds the
opening; the lips spread `(6.0 - 5.6)/2 = 0.20 mm` each and close behind it.
Nothing else lies on that path: the rod is exposed across each of the five bay
spans, and the six webs that carry it sit at the wall positions, which the lid
is relieved for. Declared in `bores.json` only indirectly — the real check here
is the motion sweep, not a bore.

**Shared-part neighbours.** Inside `body.scad`'s `union()`: `body_shell`,
`hinge_bar_a`, `hinge_bar_b`, `rail_male`. Every one of those overlaps the shell
on purpose by `weld_embed = 1.5 mm`, declared in `fusions.json`. That number is
not cosmetic: at zero overlap the tier B hinge bar came out of the boolean as a
**detached second body**, which `check_connectivity.py` caught and no render
would have.

**Retention.** The rod is captured on four sides by the clip, which is open only
forward. The lid's working load — its own weight, closed or open — never acts
forward, so the mouth is never the load path. A deliberate forward pull removes
the lid, which is intended: it is the way to take the lid off for cleaning.

**Purchased-part fit.** None. Every fit in this design is printed-to-printed,
which is exactly why the calibration coupon below is not optional.

## Fill lid in its seat

**Insertion path.** Straight down into the mouth, which is full width at the rim
and steps in by `fill_ledge_w = 3.0 mm` below the seat plane via a 45 degree
chamfer. The two snap tabs flex inward `fill_tab_barb - fill_lid_clear = 0.8 mm`
as they pass the mouth walls and spring into their pockets. **Two obstructions
on that path were found by measurement, not by inspection**: the seat lips ran
directly under the tabs (42 mm^3 of solid interference each), and the back tab's
tip reached 0.7 mm below the ramp at the deep end of the hopper. The lips are
now relieved at the tab positions and the tab is shortened to 13 mm.

**Shared-part neighbours.** `fill_plate` and `fill_tabs`, declared in
`fusions.json`; the tabs are rooted in the plate's underside and the overlap is
the built-in end of the cantilever.

**Retention.** The barbs' flat tops bear on their pocket ceilings with 0.3 mm of
lift slop. That slop is why the lid is modelled floating 0.15 mm above its seat
rather than resting on it — its exact height genuinely is not determined.

## Joining rail in its groove

**Insertion path.** The neighbouring module is lowered alongside; both grooves
run from their floor at `rail_z0 = 12` clear out of the top of the side wall, so
the rails engage progressively with no minimum lift. `bores.json` declares both
grooves and `check_bore_reachability.py` walks them end to end — this is the
check that would catch the groove being sealed by the rail buttress, which
during development it very nearly was.

**Shared-part neighbours.** The buttress that carries the groove originally ran
to the wall top and stood proud **into the fill-lid seat**, which would have held
the lid 3 mm off it. It now stops 0.3 mm below the seat plane.

**Retention.** Gravity and the undercut. The trapezoid resists separation in X
and yaw; nothing resists lifting one module straight up, which is correct for a
bench organizer and is what the user asked for.

---

# Measured results (not calculated)

Three numbers in this design were calculated by hand first and were **wrong**.
They are listed with what the measurement actually said, because the hand
figures are what a reader would otherwise assume.

| Quantity | Hand calculation | Measured | How |
|---|---|---|---|
| Pick lid hard stop | 107.1 deg, then 102.8 deg | **111.7 deg** | boolean intersection vs. angle, bisected to 0.1 deg |
| Pick lid over-centre angle | ~96.8 deg | **107.0 deg** | mass centre of the rendered lid, rotated about the hinge axis |
| Open-lid margin | "comfortable" | **+4.7 deg** | the difference between the two above |
| Per-bay capacity | 237.7 mL | **234.7 mL** | volume of the rendered cavity mesh |

The lid rests open under its own weight because 111.7 > 107.0. It did not, in
three earlier revisions; the fix was to step the hopper's front wall back by two
wall thicknesses above `lid_stop_z`, which buys swing without touching the lid.

| Capacity, final | Value |
|---|---|
| One bay, measured | 234.7 mL |
| Ten bays | 2.35 L |
| 90-day once-daily size-00 charge | 147.4 mL |
| Margin, geometric | 1.59x |
| Margin, at 80% practical fill | 1.27x |
