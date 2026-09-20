# Calculations — pill_organizer_10bay

All lengths mm, all angles degrees. `tan(40) = 0.839100`, `tan(25) = 0.466308`,
`tan(30) = 0.577350`, `tan(35) = 0.700208`.

**Revision 6.** See `plan.md` for the revision table and the full decision log.
Revision 2 forced the crossing by grouping the lids by function; revision 3
changed the crossing chute's ramp angle and added the porch under tray B, taking
the envelope from 9.45 L to 5.54 L; revision 4 fixed the reach into tray A and
the fill-mouth split; revision 5 put the dead wedge to work as a cubby; revision
6 is the independent review's fixes (a blind joining groove, a 0.7 mm snap catch,
label recesses that did not fit the tape, a cubby ceiling past the overhang
limit) plus the porch at 25 degrees and the grips. Neither row ever drops below
the 90-day charge.

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

Both `PATIKRINTI` rows set margins, not fits. Neither can make one part fail to
fit another. They are resolved by loading the finished unit.

The repose figure carries more weight than it did in revision 2, because
revision 3 onward spends margin against it deliberately — see "The porch" below.
Two things are worth being precise about. First, the 10 degree margin (40 − 30)
belongs to the ramp only: pills reach tray A by flowing over the stagnant wedge
on the porch, and that wedge's surface is at the repose angle by construction,
so the last 30 mm always feeds at the repose angle itself. That is how any pile
discharges (material at repose avalanches when more arrives), not a defect, but
it is not a margin. Second, the number the porch angle really sets is the throat
left over the wedge if the estimate is low — the table under "The porch" carries
it at 30 and 35 degrees. Jenike mass-flow criteria (walls 55–60 degrees from
horizontal) are for cohesive powders discharging through an orifice; ten
discrete 26 mm capsules falling into an open tray are not that problem, and the
straight repose line is the right first-order model for them. The loaded trial
and the coupon print are what resolve it.

## The crossing — why this revision is shaped the way it is

Grouping the mouths at the back and the trays at the front forces one flow to
cross the other. This is topological, not a detailing problem:

- **Hopper B** is the *front* mouth and feeds tray B, the tray directly in front
  of it. Plain ramp, no crossing.
- **Hopper A** is the *back* mouth but feeds tray A, the *front* tray. Its chute
  has to duck under tray B and under hopper B's ramp — 105 mm enclosed.

## Why the floor is a straight line, not a curve

The chute floor must fall toward its outlet at the angle of repose or steeper at
every point, and it is anchored at tray A's floor. So for every `y`:

`z(y) >= z_out + tan(theta_min) * (y - y_out)`

The straight line at the minimum flow angle is therefore the **lowest floor that
exists**. Any curve either lies above it (holding less) or below it (holding
pills that fill once and never discharge). A curved floor was considered and
rejected on that ground: the candidate arc gained 127 mL/bay, of which 47 mL
(37%) sat below the 30-degree line.

## Derived — the ramp angle (D11)

Hopper A's floor *is* the top of the chute, so the ramp angle sets how deep
hopper A can be, and hopper B's floor rides one slab above the chute ceiling, so
it comes down too. At a fixed 230 x 171 footprint:

| Ramp | hopper A floor, front edge | hopper B floor | dead wedge | chute ceiling as an overhang |
|---|---|---|---|---|
| 48 | 120 | 78 | 47.0% | 42 deg from vertical |
| 44 | 105 | 74 | 41.3% | 46 deg from vertical |
| **40** | **91** | **70** | **38.9%** | **50 deg from vertical** |
| 36 | 79 | 66 | 31.8% | 54 deg from vertical |

40 degrees keeps 10 degrees of margin over the repose estimate and puts the
chute ceiling 50 degrees from vertical — past the conservative 45-degree rule,
on an internal surface nobody sees, with a sag allowance carried in
`chute_clear`.

## Derived — the porch (D12, D20)

| Quantity | Formula | Value |
|---|---|---|
| Porch run | `yB_tray1 - yA_tray1` | 30.4 |
| Chute floor at the porch end | `base_z + porch_run x tan(25)` | 17.18 |
| Tray B floor | `+ chute_clear + chute_ceil` | **56.18** |
| Tray A rim | set independently — see "the reach" below | **43.0** |
| Stagnant wedge on the porch | `0.5 x run^2 x (tan(30) - tan(25)) x bay_w` | **2.2 mL/bay**, 1.5% of a charge |
| Flow channel over that wedge, repose 30 | `chute_clear - run x (tan(30) - tan(25))` | **32.6** — 1.25x pill length, 3.0x pill diameter |
| Flow channel over that wedge, repose 35 | `chute_clear - run x (tan(35) - tan(25))` | **28.9** — 1.11x pill length |

Why 25 and not the revision-3 value of 20 (D20): the throat over the wedge is
the most repose-sensitive number in the design. At 20 degrees it was 29.5 with
the estimate and 25.8 — under one pill length — if the real repose is 35. At 25
it clears one pill length up to about 38 degrees of repose. The cost is 3.1 mm
of height behind the porch, which the module absorbs under `hopper_rim`
(freeboard 24 mm over hopper B's ramp, asserted), and 1 mm on tray A's rim to
keep `trayB_front_retain` over its floor.

The porch is still the whole reason tray B's floor lands near tray A's rim: the
40-degree climb starts 30 mm further back, so everything behind it drops with it.

## Derived — the porch splitter rib (D13)

Tray B's floor is carried on the bay dividers alone. At 20 degrees its underside
is a near-flat ceiling spanning the full bay:

| Quantity | Value |
|---|---|
| Bay clear width | 42.96 |
| Rib thickness | 2.4 |
| Lane width, each side | **20.28** — 1.8x pill diameter, so pills run single file |
| Bridged span, before / after | 42.96 / **20.28** |
| Rib upstream taper | 12.0, knife-edged, so a pill from the 40-degree chute is deflected into a lane rather than stopped by a step |

Verified by `bores.json`: `chute_porch_bay1` and `chute_porch_bay5` walk a lane
end to end past the rib. A sealed lane would still be one watertight single
body, so no other check in the bundle would notice.

## Derived — the section

| Feature | Y span | Z |
|---|---|---|
| **Tray A** | 2.8 .. 30.8 | floor 3.0, rim 43.0 |
| Wall between trays | 30.8 .. 33.2 | |
| **Tray B** | 33.2 .. 61.2 | floor 56.18, rim 94.18 |
| **Chute A porch**, 25 deg | 30.8 .. 61.2 | floor 3.0 .. 17.18, ridge 39.0 .. 53.18 |
| **Chute A ramp**, 40 deg | 61.2 .. 136.0 | floor 17.18 .. 79.94 |
| **Hopper B mouth** | 63.6 .. 133.6 | floor 58.19 .. 116.93 |
| **Hopper A mouth** | 136.0 .. 168.0 | floor 79.94 .. 106.79 |
| **Overall** | | **235.0 x 170.8 x 141.0** (235 includes the 5 mm rail) |

Both mouths finish at `hopper_rim = 141`, which is what lets one flat lid cover
both. Both trays finish on one 39.9-degree plane from 43.0 at the front face to
94.18 at tray B's rim, which is what lets one flat lid cover both.

## Derived — the reach into tray A (D15)

Tray A is fed by the chute mouth, so its pill surface is not flat: it peaks at
the mouth and falls forward at the angle of repose.

| Quantity | Formula | Value |
|---|---|---|
| Pill surface at the chute mouth | `base_z + chute_clear` | 39.0 |
| Pill surface at the front wall | `- tray_d x tan(30)` | 22.8 |

The reach is the gap between that surface and the one lid plane above it, and
the plane's front end is the only free variable — its back end is pinned to tray
B's rim.

| Tray A rim | Pick plane | Reach at the front | Reach at the back | Tray-B retaining wall |
|---|---|---|---|---|
| 53.06 (level with tray B's floor) | 31.8 deg | 32.0 | 33.2 | 20.6 |
| 48.0 | 35.1 deg | 27.1 | 30.7 | 18.3 |
| 42.0 | 38.7 deg | 21.4 | 27.7 | 15.6 |
| 38.0 | 40.9 deg | 17.6 | 25.7 | 13.7 — fails `trayB_front_retain` |
| **43.0, porch 25 (rev 6)** | **39.9 deg** | **22.5** | **29.8** | **14.6** |

The floor on this is `trayB_front_retain > pill_dia + 3`: below it the wall
between the trays is cut so low by the plane that tray B spills forward into
tray A. Raising the porch to 25 degrees (D20) lifted tray B's floor by 3.1, so
the rim came up 1 to keep 0.6 mm over that bound; the reach through the plane
grew by 1 mm, and the reach over the scalloped wall did not change.

A second lid over tray A alone would remove the constraint entirely, at the cost
of the two-lid brief. What removes it without a third part is separating the lid
plane from the front WALL (D17):

| Quantity | Value |
|---|---|
| Lid plane at the front face | 43.0, so `trayB_front_retain` is 14.6 |
| Front wall, scalloped across each bay | **30.0** |
| Pill crest at that wall | 22.8 |
| **Freeboard, and the reach over the wall** | **7.2** |
| Lid skirt, hanging outside the front face | 19.2 long, bottom at 24.0, 6.0 of overlap |
| Finger notches in the skirt (D22) | 2 x 22 wide, 8 tall, top at 32.0 — 2 above the wall, 9 above the pill line |

The dividers and both side walls still run up to the plane, so the lid is
carried exactly as before and the scallops are invisible once it is on. With it
off, tray A is a parts bin: open at the top and open at the front.

## Derived — the fill mouths (D16)

The two mouths were 70mm and 32mm, a 2.2 : 1 split that fell out of holding the
two rows' volumes near each other. Leaning the wall between them evens the
openings instead:

| Lean at the rim | Angle from vertical | Hopper B mouth | Hopper A mouth | Ratio |
|---|---|---|---|---|
| 0 | 0 | 70.0 | 32.0 | 2.19 : 1 |
| 6.0 | 12.0 deg | 64.6 | 37.4 | 1.73 : 1 |
| **8.8** | **17.3 deg** (19.3 from revision 6, the spring point rose with the porch) | **62.1** (62.3) | **39.9** (39.7) | **1.56 : 1** |
| 12.0 | 23.1 deg | 59.3 | 42.7 | 1.39 : 1 |

The wall pivots where it springs off the chute ceiling, so hopper B's ramp below
it is untouched. Its overhanging face is under 20 degrees from vertical, well
inside the FDM band. Hopper B loses about 5 mL/bay and hopper A gains the same.

## Derived — capacity (measured from the rendered cavity meshes)

| Row | Per bay | vs 147.4 mL charge | Days at one/day |
|---|---|---|---|
| Row A — front tray, back mouth, crossing chute | **290.2 mL** | 1.97x | 177 |
| Row B — back tray, front mouth, plain ramp | **182.4 mL** | 1.24x | 111 |

Measured with the fill line at the underside of the lid (`fill_seat_z`), the
porch ribs subtracted and the fillets included — not from the idealised section,
which reads about 8% high on row B because it ignores the seat ledges. Revision
5 held 293.0 / 191.6; the 25 degree porch (D20) costs 3 and 9 mL.

Total across ten bays: **2.36 L** in a **5.54 L** envelope. Revision 2 held
3.27 L in 9.45 L. This is the geometric maximum with the lid on, not a practical
fill; a pour stops when the pile reaches the mouth.

## Derived — the accessory cubby (D18, D21)

| Quantity | Formula | Value |
|---|---|---|
| Depth in Y from the back face | `cubby_d` | 70.0 |
| Width | `inner_w`, both side walls left full | 224.4 |
| Ceiling | its own plane at `cubby_ceil_deg = 45`, anchored `cubby_ceil` under the chute floor at the back face | — |
| Height at the shallow end | `at y = 100.8` | 33.1 |
| Height at the back face | `at y = 170.8` | 103.1 |
| Deck between cubby and chute | back face / cubby front | 3.0 / 14.3 |
| Retaining lip across the opening | `cubby_lip_h`, level with the shallow end | 30.0 |
| Clear opening above the lip | | 73.1 |
| Cubby volume | trapezoid x width | about 1.07 L |
| Solid volume, body | rev 5 / rev 6 | 929.3 / **1049.4 cm3** |

Revision 5 ran the ceiling parallel to the chute floor and called it
self-supporting. A 40 degree slope is a 50-degree-from-vertical overhang — the
same one the chute ceiling carries as an ADVISORY — and here it spanned the
full 224 mm with nothing to anchor a drooping perimeter to. At 45 degrees it is
inside the conservative limit at any width. The deck it leaves is 3 mm at the
back face only, thickening to 14 at the cubby's front; a uniformly loaded 3 mm
PLA plate over that span deflects under a millimetre at the pill loads involved,
and `attachments.json` declares the deck mid-span so nothing can silently cut it
away.

## Derived — label recesses (D19)

| Quantity | Formula | Value |
|---|---|---|
| Tape width, 1/2 inch TZe | `label_tape_w` | 12.0 |
| Recess height | `+ label_clear` | 12.6 |
| Recess length / depth | | 36.0 / 0.5 |
| Lower strip, on the front face | `label_z_center` | 13.0 — top at 19.3, clears the lid skirt at 24.0 |
| Upper strip, on the wall between the trays | `(chuteA_ceil(yA_tray1) + pickplane(yA_tray1)) / 2` | 53.9 |
| Exposed height of that wall | `39.0 .. 68.8` | 29.8 — carries 12.6 with 8.6 either side |
| Wall left behind the recess | `wall_div - label_z` | 1.9 — measured on the mesh, revision 6 |

These are the numbers D19 recorded; revision 5's `params.scad` never received
them (32 x 9 x 0.6, and the upper cut 1.0 deep). Revision 6 writes them.

## Derived — the fill lid snap and grips (D23)

| Quantity | Formula | Value |
|---|---|---|
| Tab drop / thickness / width | | 12.0 / 1.2 / 16.0 |
| Barb / real engagement | `fill_tab_barb - fill_lid_clear` | 1.1 / 0.8 |
| Bending strain at full deflection | `3 t d / (2 L^2)` | 1.0% |
| Barb return face | `fill_tab_return_deg` | 35 deg from horizontal — releases under a pull, holds a knock |
| Catch the front barb latches on | `fill_catch_t` = relief bottom − pocket top | **2.7** (0.7 in revision 5) |
| Pull lip | `fill_lip_w x fill_lip_len` | 30 x 8, full plate thickness, over a 34 wide notch cut to the seat plane |

## Derived — flow and escape paths

| Check | Value | Status |
|---|---|---|
| Chute ridge section | 36.0, constant | OK — 1.38x pill length |
| Row A outlet (the chute's own section at tray A) | 36.0 | OK |
| Row B outlet | 30.0 | OK — 1.15x pill length, 2.7x pill diameter |
| Ramp angle vs repose | 40 - 30 = 10 margin | OK, reduced from 18 |
| Porch angle vs repose | 25 - 30 = **-5** | BY DESIGN — the flow over the wedge is at repose; throat 32.6 / 28.9 at 30 / 35 deg repose |
| Porch lane vs pill diameter | 20.28 / 11.0 = 1.8x | OK for single file |
| Chute ceiling overhang, 40 deg leg | 50 from vertical, 30,900 mm^2 in 43 mm bays | ADVISORY — past the 45 rule, internal surface |
| Chute ceiling overhang, porch leg | 65 from vertical | OK — bridged span cut to 20.28 by the rib |
| Cubby ceiling overhang | 45 from vertical, 22,100 mm^2 across 224 mm | OK — at the limit, D21 (was 50) |
| Front joining groove | open from z 10 to 62.9, through the plane at 61.9 | OK — blind in revisions 3-5 |
| Wall between trays, above tray B's floor | 14.6 | OK — 1.3x pill diameter, bounded by D15 |
| Front wall over tray A's pill crest | 7.2 | OK — scalloped, D17 |
| Bay width vs pill length | 1.65x | PATIKRINTI — see note |

Arch note, unchanged from revision 1: 42.96 mm is 1.65x the longest pill against
a 2x-3x rule of thumb, so two capsules can in principle span a bay. Mitigated by
the steep ramp and the tall section, not eliminated. An occasional tap may be
needed, as with any gravity dispenser.

## Decisions and assumptions log

| ID | Kind | Criticality | Statement | Status |
|---|---|---|---|---|
| A1 | Assumption | Ordinary | Loose capsule packing fraction 0.58 | Open — resolved by loading the unit |
| A2 | Assumption | Ordinary | Static angle of repose ~30 degrees on PLA | Open — resolved by the coupon print and a loaded trial |
| A3 | Assumption | Ordinary | A 50-degree-from-vertical internal ceiling prints acceptably in PLA with part cooling | Open — resolved by the test print |
| A4 | Assumption | Ordinary | A 20.28 mm bridge prints without support | Open — resolved by the test print |
| A5 | Assumption | Ordinary | Tray A's pill surface follows a 30-degree repose slope forward from the chute mouth, which is what the reach table is computed from | Open — resolved by loading the unit |
| A6 | Assumption | Ordinary | A 35 degree barb return releases a 0.8 mm engagement under a fingertip pull on the lip without exceeding the tab's strain; the calibration coupon's snap fingers are the check | Open — resolved by the coupon print |
| A7 | Assumption | Ordinary | A 45-degree-from-vertical ceiling 224 mm wide prints clean in PLA with part cooling | Open — resolved by the test print |
