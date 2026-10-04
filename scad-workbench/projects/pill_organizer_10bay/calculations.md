# Calculations — pill_organizer_10bay

All lengths mm, all angles degrees. `tan(40) = 0.839100`, `tan(25) = 0.466308`,
`tan(30) = 0.577350`, `tan(35) = 0.700208`.

**Revision 10.** Test print 2 (D36-D40). Tray A's floor tilts 35 degrees toward
the front wall, the porch is 40 degrees, bins are deeper and wider, the pick lid
is retained by lugs against stop blocks with faces perpendicular to the pick plane, the rail-1 buttress is thicker. Where a table
below says "(rev 9)" its numbers are the old ones; the new ones are in the
revision 10 sections at the end of this file, which win.

**Revision 9.** See `plan.md` for the revision table and the full decision log.
Revision 9 is the review of revision 8: tray B's pile kept below the wall in
front of it (D33), the pick lid's lugs moved to tray A (D34), and edge and
corner fixes (D35).
Revision 7 vaulted the crossing chute's ceiling (D26) and rounded the external
edges (D27). Revision 8 is test print 1: the porch ceiling flat and its rib
gone (D29), the fill lid nesting by gravity (D30), rail clearance from the
coupon (D31), and locating lugs on the pick lid (D32).
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
| Usable footprint / height | 246 x 246 x 250 | 256 less 5 mm margin each side in X and Y, height 250 (D37; D3's 243 x 243 x 243 is superseded) | OK |
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
`chute_clear`. Revision 7 removes that overhang without touching the ramp
angle: see "the vault" below.

## Derived — the vault (D26)

A face that slopes 40 degrees front-to-back and nothing sideways is 50 degrees
from vertical. Give the same face a sideways slope too — a shallow ridge down
the centre of each bay — and the diagonal steepens:

`face from vertical = 90 − atan( sqrt( tan(gable)² + tan(40)² ) )`

| Quantity | Formula | Value |
|---|---|---|
| Rise, edge to ridge | `vault_up + vault_down` | 12.0 |
| Gable | `atan(12 / (bay_w / 2))` | 29.2 deg |
| Face from vertical | formula above | **44.8 deg** (was 50) |
| Chute clear at the ridge / at the dividers | `chute_clear + 4` / `− 8` | 40 / **28** — 1.08x pill length, 2.5x diameter (42 / 30 at 6 / 6 until D33) |
| Hopper B ramp foot | `trayB_floor + vault_up` | 60.18 — a 4 mm riser at tray B's back wall (6 until D33); the fillet is at its foot, its top edge is sharp |
| Hopper divider spring point | `max(chuteA_ceil(yA_hop0), rampB(yB_hop1))` | 122.93 — the ramp's end; below it the wall is vertical and 2.4 thick (D28; 0.2 at revision 7 as first committed) |
| Hopper B outlet top | `rampB_foot + outlet_h`, outlet_h 27 | 87.18 — flat across the wall's thickness (D35), 16 mm under tray B's rim |
| Deck at the ridge | `chute_ceil` | 3.0, declared in `attachments.json` as `vault_deck` |
| Row B capacity | measured | 182.4 → 166.1 mL at revision 7; **179.2 mL** at revision 9 (D33), 1.22x the charge, 109 days |

Where the rise goes is the whole decision. All of it up (ridge +12) lifts
hopper B's floor 12 mm and leaves 0.4 mm of freeboard under the rim; all of it
down (edges −12) leaves 24 mm clear at the dividers, under one pill length.
Split, neither limit is approached. The ridge void starts 1 mm inside each end
of the added roof solid (`vault_roof_y0 < vault_y0`, `vault_y1 < vault_roof_y1`)
so the two never share a face; the 1 mm lips this leaves at each end of the
ridge are internal and vertical. The porch under tray B is not vaulted: its
ceiling is a flat bridge (D29). Since D35 the ridge rises over its first
vault_ramp (8 mm) behind the porch instead of in one vertical step.

Face-normal scan of the body, downward faces 50–55 degrees from vertical,
above the bed: 21,758 mm² before, about 2,200 after — and of that, 59 mm² is
under hopper B. The review of revision 7 traced the rest not to the seat
ledge but to fillet shoulders the opening pass put back under the pick plane
when the tray voids ran only 1 mm past it (the 4.3 mm tangent of a 2 mm round
on a 50-degree corner); `void_top_over` is 5 now and they are gone. The two
end lips of each vault ridge are 6 mm tall at the bay centre and at the
edges respectively, facing the flow; watch bays 1 and 5 under a full charge.

The thin-wall half of `check_printability.py` (0.8 mm threshold) reports 39
of 1500 samples after the D28 fix, down from 52; a 20,000-sample ray-cast map
puts every one of them on an acute edge — the splitter rib's knife taper at
the bay centres (rib removed, D29), the dovetail lips of both rails, the seat-ledge noses, and
grazing hits on the obtuse plane-to-wall edges. No wall reads under 0.8.

## Derived — tray B's pile (D33)

Tray B is fed from hopper B through the outlet under the wall at its back, so
its pill surface peaks at that outlet's top and falls forward at repose — the
same model D17 applies to tray A. What the wall between the trays has to hold
back is that surface where it meets the wall, not tray B's depth.

| Quantity | Formula | Revision 8 | Revision 9 |
|---|---|---|---|
| Outlet top | `trayB_floor + vault_up + outlet_h` | 56.18 + 6 + 28 = 90.18 | 56.18 + 4 + 27 = **87.18** |
| Pile at the wall | `outletB_top − tray_d × tan(30)` | 74.01 | **71.01** |
| Wall top | `pickplane(yB_tray0)` | 70.76 | **76.10** |
| Margin at 30° / 25° / 35° | | **−3.25** / −6.36 / +0.19 | **5.09** / 1.98 / 8.53 |

Revision 8 would have spilled row B into row A with the lid off. The fix takes
from three places: vault_up 6 → 4 (vault_down 6 → 8 keeps the gable, and the
chute's 28 at the dividers still clears a pill length), outlet_h 28 → 27 (the
floor is `> pill_len`, so a capsule arriving end-on still passes), and the
wall's top raised by tray B 38 → 47 deep and tray A's rim 43 → 44. The plane
steepens to 44.0 degrees; the pick lid's skirt then prints at 46 degrees.

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

## Derived — the porch ceiling (D29, replacing the rib of D13)

Tray B's floor is carried on the bay dividers alone; the chute runs under it.
Revisions 3–7 ran that ceiling parallel to the 25-degree porch floor and held
it up with a 2.4 mm splitter rib down the middle of each porch. Test print 1
printed it ragged anyway, and the rib split the flow into two 20.3 mm lanes.

| Quantity | Formula | Value |
|---|---|---|
| Porch ceiling | `chuteA_ceil(yB_tray1)`, flat | **53.18** |
| Deck under tray B's floor | `trayB_floor − porch_ceil_z` | 3.0 |
| Bridge, per bay | bay width × porch depth | 42.96 × 28.0 |
| Chute clear at the porch end | `porch_ceil_z − z_porch` | 36.0 |
| Chute clear at the mouth's back face | `porch_ceil_z − chuteA_floor(33.2)` | 49.1 |
| Mouth into tray A | bottom of the wall between the trays | 39.0, unchanged |
| Outlet corner chamfers | `outlet_chamfer` at 45° | 8.0; top span 27.0 of 42.96 |

The ceiling meets the 40-degree leg's ceiling at tray B's back wall at the same
height, so there is no step in the flow. The pocket behind the mouth adds about
13 mL to row A per bay; the measured capacity below includes it.

Verified by `bores.json`: `porch_centre_bay3` runs down the old rib line;
`chute_porch_bay1` and `chute_porch_bay5` still walk the porch end to end.

## Derived — the section

| Feature | Y span | Z |
|---|---|---|
| **Tray A** | 2.8 .. 30.8 | floor 3.0, rim 43.0 |
| Wall between trays | 30.8 .. 33.2 | |
| **Tray B** | 33.2 .. 61.2 | floor 56.18, rim 94.18 |
| **Chute A porch**, 25 deg | 30.8 .. 61.2 | floor 3.0 .. 17.18, ridge 39.0 .. 53.18 |
| **Chute A ramp**, 40 deg | 61.2 .. 136.0 | floor 17.18 .. 79.94 |
| **Hopper B mouth** | 63.6 .. 133.6 | floor 64.19 .. 122.93 (6 mm riser at 61.2, D26) |
| **Hopper A mouth** | 136.0 .. 168.0 | floor 79.94 .. 106.79 |
| **Overall** | | **235.0 x 170.8 x 141.0** (235 includes the 5 mm rail) |

Both mouths finish at `hopper_rim = 141`, which is what lets one flat lid cover
both. Both trays finish on one 44.0-degree plane from 44.0 at the front face to
103.18 at tray B's rim (39.9 degrees, 43.0 to 94.18 until D33), which is what lets one flat lid cover both.

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
| 43.0, porch 25 (rev 6) | 39.9 deg | 22.5 | 29.8 | 14.6 |
| **44.0, tray B 47 deep (rev 9, D33)** | **44.0 deg** | **23.9** | **34.8** | **19.9** |

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
| **8.8** | **17.3 deg** (19.3 from revision 6, the spring point rose with the porch; **26.0** from revision 7's review fix, when it rose to the end of hopper B's ramp, D28) | **62.1** (62.3; **62.7**) | **39.9** (39.7; **39.3**) | **1.56 : 1** (1.59) |
| 12.0 | 23.1 deg | 59.3 | 42.7 | 1.39 : 1 |

The wall pivots where it springs off the chute ceiling, so hopper B's ramp below
it is untouched. Its overhanging face is under 20 degrees from vertical, well
inside the FDM band. Hopper B loses about 5 mL/bay and hopper A gains the same.

## Derived — capacity (measured from the rendered cavity meshes)

| Row | Per bay | vs 147.4 mL charge | Days at one/day |
|---|---|---|---|
| Row A — front tray, back mouth, crossing chute | **286.9 mL** | 1.95x | 175 |
| Row B — back tray, front mouth, plain ramp | **179.2 mL** | 1.22x | 109 |

Measured with the fill line at the underside of the lid (`fill_seat_z`), the
porch ribs subtracted and the fillets included — not from the idealised section,
which reads about 8% high on row B because it ignores the seat ledges. Revision
5 held 293.0 / 191.6; the 25 degree porch (D20) cost 3 and 9 mL, the vault
(D26) a further 16 on row B. Revision 8's flat porch ceiling (D29) adds the
pocket behind each front-bin mouth to row A, +13 mL; row B's 170.9 includes
the D28 hopper divider fix.

Total across ten bays: **2.38 L** in a **5.54 L** envelope. Revision 2 held
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
| Solid volume, body | rev 5 / rev 6 / rev 7 | 929.3 / 1049.4 / **1138.1 cm3** |

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

## Derived — the fill lid fit and grips (D30, D23)

| Quantity | Formula | Value |
|---|---|---|
| Clearance all round | `fill_lid_clear` | 0.30 — NOT yet confirmed: test print 1's lid was at 0.42 scale (0.13); the full-size section print checks it |
| Seat ledge | `fill_ledge_w` | 3.0 |
| Underside lead-in chamfer | `fill_lead_in` at 45° | 0.6 |
| Lid bearing on the ledge | `fill_ledge_w − fill_lid_clear − fill_lead_in` | 2.1 |
| Retention | gravity, in a 3 mm recess | stays put when set down; not against tipping, by the brief |
| Pull lip | `fill_lip_w x fill_lip_len` | 30 x 8, full plate thickness, over a 34 wide notch cut to the seat plane |

## Derived — flow and escape paths

| Check | Value | Status |
|---|---|---|
| Chute ridge section | 36.0, constant | OK — 1.38x pill length |
| Row A outlet (the chute's own section at tray A) | 36.0 | OK |
| Row B outlet | 27.0 | OK — 1.04x pill length, 2.5x pill diameter; asserted > pill_len |
| Ramp angle vs repose | 40 - 30 = 10 margin | OK, reduced from 18 |
| Porch angle vs repose | 25 - 30 = **-5** | BY DESIGN — the flow over the wedge is at repose; throat 32.6 / 28.9 at 30 / 35 deg repose |
| Chute ceiling overhang, 40 deg leg | **44.8 from vertical**, vaulted (D26) | OK — was 50 and ADVISORY through revision 6 |
| Chute clear under the vault's low side | 30 at the dividers | OK — 1.15x pill length, 2.7x pill diameter |
| Hopper B outlet vs tray B rim | 16.0 | OK — asserted >= 3 |
| Tray B pile vs the wall in front of it | 5.1 at 30° repose, 2.0 at 25° | OK — D33; asserted >= 5 and > 0 |
| Porch ceiling | flat bridge, 42.96 x 28 per bay | OK — slicer bridge; D29 (was a 25° overhang with a rib) |
| Outlet tops | 45° corner chamfers, 27 mm span | OK — D29 |
| Cubby ceiling overhang | 45 from vertical, 22,100 mm^2 across 224 mm | OK — at the limit, D21 (was 50) |
| Front joining groove | open from z 10 to 67.0, through the plane at 66.0 | OK — blind in revisions 3-5 |
| Wall between trays, above tray B's floor | 19.9 | OK — but what it must hold back is the pile, not the floor: see D33 |
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
| A4 | Assumption | Ordinary | A flat 43 x 28 mm bridge (the porch ceiling, D29) prints without support and with under 1 mm of sag | Open — resolved by the full-size test print |
| A5 | Assumption | Ordinary | Tray A's pill surface follows a 30-degree repose slope forward from the chute mouth, which is what the reach table is computed from | Open — resolved by loading the unit |
| A6 | Assumption | Ordinary | (Retired with the snap tabs, D30.) | Closed |
| A7 | Assumption | Ordinary | A 45-degree-from-vertical ceiling 224 mm wide prints clean in PLA with part cooling | Open — resolved by the test print |
| A8 | Assumption | Ordinary | Pills dropping a 6 mm rounded riser from hopper B's ramp foot onto tray B's floor do not bounce out over the 38 mm tray wall | Open — resolved by loading the unit |

## Derived — external edges (D27)

| Edge | Treatment | Wall behind it |
|---|---|---|
| Body vertical corners (4) | round, r 3.0 | 2.8 walls; the inner corner stays sharp, 2.7 mm on the diagonal |
| Body top edges in section (both edges of the step, back) | round, r 1.5 | 2.4 mm wall tops keep 0.9 mm of flat |
| Front edge of the pick plane | the same pass, but the corner is obtuse (130°): a 0.16 mm easing | |
| Side walls' long top edges (x = 0, 230) | left square: they run along the extrusion | |
| Male rail undersides | 45° chamfer from the wall face, D28 | were flat, 10 mm above the bed |
| Body base edges | left square | first layers |
| Pick lid plate, front and back edges | chamfer 1.0, in section (under half the 3 mm plate; a 1.5 round collapsed it; a round of any size is a 90-degree overhang where this face meets the bed) | |
| Pick lid plate, x-end top edges | chamfer 1.0 | |
| Pick lid skirt bottom edge | chamfer 1.0 | the notches already carry r 4 |
| Fill lid, plan corners incl. the lip | round, r 2.0 | more clearance at the mouth's sharp corners, not less |
| Fill lid, top perimeter | chamfer 1.0 | printed face-down: a 1 mm 45-degree first-layer overhang |
| Scallops, finger notches, riser, every flow corner | already rounded | |


## Revision 10

All values from `params.scad`, measured values from the probes in `probes/`.

### Derived: tray A's tilted floor (D36)

Test print 2: row B, on a plain 40 degree ramp, fed well; row A, on a flat floor
behind a 25 degree porch, filled once and did not refill as pills were taken.
A pill on a floor stays put if the floor is shallower than the friction angle of
pill on PLA, and that angle is no higher than the pile's repose (estimate 30,
plausible 25-35). So the floor has to be at least as steep as the top of that
range for every pill on it to be able to slide.

| Quantity | Formula | Value |
|---|---|---|
| Tray A floor tilt | `trayA_tilt_deg`, asserted >= `repose_hi_deg` (35) and < ramp (40) | **35 degrees** |
| Floor at the front wall / at the chute foot | `base_z` / `base_z + tray_d x tan(35)` | 3.0 / 31.0 |
| Height cost | `tray_d x tan(35)`; at 30 degrees it would be 23.1, at 40 33.6 | 28.0 |
| Chute floor | 40 degrees from the foot (porch = ramp, D36) | one straight line, 31.0 at y 42.8, 66.6 at y 85.2 |
| Mouth into tray A | true minimum, `(chute_clear - wall_div x tan(40)) x cos(40)`, from the back-bottom corner of the wall between the trays (the front-bottom corner gives 27.6) | **26.03**, 1.0x pill length; asserted >= pill length. Only a capsule standing on end is limited by it |
| Pile crest at the front wall, repose r | `outletA_top - tray_d x tan(r)`, outletA_top 67.0 | 48.4 (25), **43.9 (30)**, 39.0 (35) |
| Pile depth at the front wall | crest - 3.0 | 45.4 (25), **40.9 (30)**, 36.0 (35) |
| Front wall (scalloped) | `trayA_front_h`; 52 until the revision 10 review | 55.0 |
| Reach over the wall, repose 30 / 25 | wall - crest | **11.1** / 6.6 (asserted > pill radius, 5.5, at 25) |

What 35 buys against the estimate: at repose 30 the floor is 5 degrees past it,
at 35 it is exactly at the limit, and at 25 10 degrees past. Below the floor's
angle the pile cannot rest on it, so the pile re-forms against the front wall as
pills are removed. What it costs: a pile 41 mm deep at the front wall (36 at
repose 35) and a wall 55 high. The pile is deeper at the front than at the
mouth (36) because the floor is steeper than the pile surface; that is the point.
The porch no longer carries a wedge: the throat/stagnation tables of D12 and D20
above are history.

### Derived: why the module grew (D36, D37)

| Quantity | Formula | Value (rev 9 -> rev 10) |
|---|---|---|
| tray_d | | 28 -> 40 |
| Bay clear width | `(inner_w - 4 x wall_div) / 5`, module_w 240 | 42.96 -> 44.96 |
| Porch run | `yB_tray1 - yA_tray1` | 30.4 -> 42.4 |
| Chute floor at the porch end | `z_foot + run x tan(40)` | 17.2 -> 66.6 |
| Tray B floor | `+ chute_clear + chute_ceil` | 56.2 -> 105.6 |
| Tray A rim (pick plane's front end) | see below | 44 -> 77 |
| Tray B rim | floor + trayB_h (53) | 103.2 -> 158.6 |
| Pick plane | rise 81.6 over 85.2 | 44.0 -> 43.8 degrees |
| hopper_rim | 18 over hopper B's ramp end (170.7) | 141 -> 189 |
| Body | | 235 x 170.8 x 141 -> **245 x 194.8 x 189** (245 includes the 5 mm rail) |

Tray A's rim is what the plane's front end has to be, not a free choice. Two
things bind it: the wall between the trays must stand `pill_dia + 3` over tray
B's floor (`trayB_front_retain` 14.7 here; the pile test D33 is 6.4 at repose 30
and 1.95 at 25), and the plane's slope must stay at or under 45 degrees, because
the pick lid prints with the plate on the bed and the skirt, and now the lugs'
vertical faces, lean over by that angle. Tray B's floor rose 49 mm; the plane at
the wall between the trays is `rimA + (yB_tray0 / yB_tray1) x rise`, so rim A
had to rise with it: 77. The front WALL stays low (55) by D17.

Plate fit (D37): footprint 245 x 194.8 (limit 246 x 246), height 189 (250). Pick
lid in its print orientation 239 x 139.3 x 22.7; fill lid 233.8 x 111.8 x 3. The
vault's gable on the wider bay: `vault_up + vault_down` 12 -> 12.4 (4.4 / 8.0)
so the face stays at 44.9 degrees from vertical (45.15 with 12.0); chute clear
at the dividers 28.0, as before.

### Derived: capacity (D37), measured by `probes/capacity.py`

The bay's footprint box minus the body, under the fill line (the pick plane over
the trays, `fill_seat_z` over the hoppers), split into connected voids.

| Row | Middle bay | End bay | vs 147.4 mL charge | Days at one/day |
|---|---|---|---|---|
| Row A, front tray, crossing chute | **427.6 mL** | 404.5 (bay 1), 407.0 (bay 5) | 2.90x | 261 |
| Row B, back tray, plain ramp | **200.2 mL** | 193.1 | 1.36x | 122 |
| Cubby, per bay | 366 | 361 | | |

Both rows were 286.9 / 179.2 mL at revision 9. Total, ten bays, geometric
maximum with the lids on: about 3.09 L in a 9.0 L envelope. Row A's chute is
taller and longer and its mouth pocket under tray B is 70 mm tall at the front;
that pocket fills with pills that sit above the mouth and feed through it.

### Derived: pick lid retention (D38, perpendicular faces after the review)

The first version stopped the lid with a lug whose front face was vertical,
against the vertical back face of a pillar. The review of revision 10 showed it
jamming on removal: lifting the lid by the front notches pivots it about its
back edge, 106 mm behind the lugs, and a lug at depth d below the plane moves
`d x theta` toward the stop while it rises `106 x theta` along the normal. With a
vertical face that meant 7 to 25 mm3 of overlap at 0.5 to 2 degrees of tilt,
freeing only at about 3 degrees. With both faces perpendicular to the plane the
lug rises along the faces, and its sideways approach (0.5 mm of clearance, `d x
theta`) only closes after it has risen clear of the stop (6.9 mm of overlap
against `106 x theta` of rise: clear at 3.7 degrees, contact would need 4.7).

Geometry per side, left (the right is the mirror):

| Quantity | Formula | Value |
|---|---|---|
| Stop face | perpendicular to the plane; meets the plane at `pick_stop_y` and runs `pick_stop_depth` down along the inward normal, then drops vertically to the floor | y 3.8 at the plane, 9.0 deep, back to y 10.0 |
| Stop block | fused to the side wall and front wall, `pick_stop_w` wide, top 0.2 under the plane (clipped by OUTER_CLIP) | x 2.8 .. 8.4, y 1.0 .. 10.0 |
| Front wall pillar | scallop stops `pillar_w` from the side wall | x 2.8 .. 8.8 |
| Lug | `pick_lug_t` x `pick_lug_len` x `pick_lug_d` | 4.0 (X) x 4.0 (along the slope) x 7.0 (perpendicular to the plate) |
| Lug position | against the side wall, in front of the buttress | x 3.3 .. 7.3; lowest corner y 11.8, buttress front y 14.3 (rail1_y moved +3 for this) |
| Clearance | `pick_lug_clear`, along the slope, face to face | 0.5 (probe: first contact 0.51) |
| Engagement | lug depth below the plane, perpendicular | 6.86 mm; stop face runs 9.0 deep |
| Material behind the face | along the slope from the face | 5.3 at the top (`y / cos(slope)`), 9.1 at 4 mm down |
| Air under the lug | to tray A's pile line | 29.7 mm |
| Lug front face in print | vertical (perpendicular to the plate) | no overhang |
| Stop face in print | faces up and back, 46 degrees above horizontal | no support, sheds pills |

The contact face meets the block's top (the plane) at 90 degrees, so the
contact zone has no knife edge (the vertical-face pillar was a 46 degree wedge
thinning to nothing there). Lugs are 4 mm thick, up from 3: a cantilever across
the layers, with the stop block 5.6 wide to keep 1.1 mm beyond the lug.

Back edge: `pick_lid_back_clear` 1.2 mm (0.35 until the review). Tilting about the
back edge swings the plate's top-back corner into the wall behind tray B after
9 degrees at 0.35; at 1.2 it clears 15 degrees with the lid's minimum clearance
rising from 0.14 mm at rest to 0.25 at 15 degrees.

Reversed (turned 180 degrees about the plane's normal): the skirt lands in the
wall behind tray B (2449 mm3 of overlap); the lugs alone, in tray B's end bays,
touch nothing. The lid cannot be put on turned round, and it is the skirt that
says so. Output of `probes/lid_retention.py` is in `probes/lid_retention.out.txt`.

### Derived: the groove corner (D39)

| Quantity | Formula | Rev 9 -> rev 10 |
|---|---|---|
| Skin between groove bottom and tray A | `rail_boss + wall_out - rail_out - rail_depth_clear` | 2.4 -> **4.4** |
| Buttress length in Y | `rail_boss_w` | 19 -> 23 |
| Buttress either side of the groove's widest part | `(rail_boss_w - rail_tip_w - 2 x rail_clear) / 2` | 3.5 -> 5.8 |
| End bay width left | `bay_w - rail_boss` | 40.0 -> 37.96 (needs >= 26) |
| Front corner | 2.4 mm fin above the scallop -> full-height front wall 6 mm wide with a stop block behind it | |

Measured by `probes/corner_thickness.py`: skin 4.40 at z 30, 60 and 90;
buttress 5.86 / 5.81 either side; stop block to y 10.0 at z 62, 9.1 mm of material behind the contact face. Slice scan for material
under 2 mm: only wedge tips where the pick plane cuts a wall and the 0.5 mm
label recess leaves 1.9 mm; no region over 4 mm2 near the groove or the stop block
beyond the front wall's own plane-cut top.

### Derived: rail fit (D40)

`rail_clear` 0.20. Coupon stubs at clearances 0.30, 0.25, 0.20, 0.15, 0.10,
labelled by the offset from the default: -100, -50, 0, +50, +100.

### Revision 10 re-review (G1-G7)

- **Mouth throats (G5), perpendicular to the floor:** row A 26.03 at the bay centre,
  24.1 a pill's radius from a divider, 19.9 at the divider face; row B, whose outlet
  fed well in test print 2, 19.1 / 13.0 at the same places. Row A is asserted never
  tighter than row B (centre 1.25x, divider 1.0x). Pill length is kept as a sanity
  floor only: it matters to a capsule standing on end.
- **Tilting from the rest pose (G2):** under gravity the lugs touch the stop faces
  (0.5 mm down-slope of nominal). A tilt about the back edge then drives a lug's depth
  `n x theta` into its face while the face-to-face overlap lasts: 0.8 to 2 mm3 between
  0.25 and 3.25 degrees. Clearing it needs the lid to ride up-slope 0.09 mm by 1 degree,
  0.16 by 2, 0.19 by 3 and 4, nothing after 5 (room: 1.0 mm), found by
  `probes/lid_retention.py` (e2). A geometric relief cannot make it zero: while two
  perpendicular faces touch over 5 mm or more at rest, rotation about a pivot 106 mm
  away must push the deeper part of one into the other; draft or a chamfer that
  cleared it would also take away the engagement. The up-slope ride is the lid's own
  freedom (PLA flexes more than that).
- **Filler (G4):** each end bay's slot between the stop block (y 10.0) and the buttress
  (y 14.3) is filled x 2.8..9.4, top at 45 degrees falling toward the bay from 0.5
  under the block's corner (z 73.6 at the side wall), 5 mm or more under the lug's lowest
  point (z 78.8). Cost 1.8 mL in a bay-1 end bay (404.5, was 406.3).
- **Flush top (G7):** the stop block's top (0.2 under the plane, to avoid a coplanar
  union) and the front wall's top over the pillar (trimmed to 0.15 under) differ by
  0.05 mm, from 0.2.
