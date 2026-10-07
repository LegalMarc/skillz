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
| Outlet facets (D52, D54; 8.0 and a 29 mm flat until revision 13) | `outletA_chamfer`, `outletB_chamfer` at 45° | 17.48 and 12.48; crown flats 10.0 and 20.0 of 44.96 |

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
| Width | `inner_w`, both side walls left full | 234.4 |
| Ceiling | its own plane at `cubby_ceil_deg = 45`, anchored `cubby_ceil` under the chute floor at the back face | — |
| Height at the shallow end | `at y = 100.8` | 82.6 |
| Height at the back face | `at y = 170.8` | 152.6 |
| Deck between cubby and chute | back face / cubby front | 3.0 / 14.3 |
| Retaining lip across the opening | `cubby_lip_h = cubby_lip_top - base_t`, top at z `cubby_lip_top` = 76 (D50, supersedes D21's 30) | 73.0 |
| Clear opening above the lip | `cubby_h_back - cubby_lip_h` (the ceiling at the back face is z 155.55) | 79.55 |
| Lip under the ceiling at the shallow end | `cubby_h_front - cubby_lip_h`, asserted >= 5 | 9.6 |
| Body volume, mesh | before / after D50 (the lip wall is 2.8 thick, 234.4 wide, 43 taller) | 2281.3 / 2309.6 cm3 |
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
| Outlet tops | 45° facets, crown flats 10 mm (tray A) and 20 mm (outlet B) | OK — D52, D54 (29 mm span until revision 13) |
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
  0.16 by 2, 0.19 by 3 and 4, nothing after 5 (room: 0.86 mm since D53's fillet, measured; 1.0 before), found by
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
- **Break-out knife edge (H2):** the rail-1 groove breaks out through the sloped plane and its
  front flank is vertical, so the lip in front of it ended in a 46 degree edge about 2 mm tall
  (a 3-6 mm2 thin region in the z = 94.6 to 96 slices, right side). A `groove_chamfer` of 3 mm,
  a 45 degree countersink built in the plane's own frame and sheared to the slope, now leaves
  that lip a 90 degree or wider edge; it stops at the groove's floor plane so the skin keeps 4.4 mm.
  `probes/corner_thickness.py` slices the zone every 0.25 mm and fails if any region under 2 mm
  stands over 1 mm tall. Left (male rail) side has no break-out; its lead taper is excluded.


## Revision 11 (test print 3)

### Derived: corner beads (D41, redesigned after the review)

Tray A's floor meets the front wall in a wedge: the floor rises toward the back at
35 degrees, the wall is vertical, so the void's angle at the junction is 55 degrees.
A size-00 capsule (11 mm diameter, radius 5.5) lying along the wall touches wall and
floor with its axis at `5.5 / sin(27.5) = 11.9` mm from the junction line, and touches
the floor `5.5 / tan(27.5) = 10.6` mm from the wall along it.

| Quantity | Formula | Value |
|---|---|---|
| Bead | a half-round rib, axis on the floor surface from the front wall, radius `bead_r`, length `bead_len`, hemispherical end | r = 2.5 (5 across), 13 long: past the 10.6 mm line where the capsule meets the floor |
| Positions, clear gap | 1/4, 1/2, 3/4 of the bay; `bay_w / 4 - 2 bead_r`, asserted under a capsule's diameter and over 3 | pitch 11.2, gap 6.2 |
| Why 2.5 | the capsule's end cap has radius 5.5; a rib of radius r, its axis on the floor and the cap resting on the floor, is touched where the cap centre is `5.5 + r` from the rib axis, i.e. `sqrt((5.5 + r)^2 - 5.5^2)` = 5.8 mm to the side for r = 2.5, at an elevation of `atan(5.5 / 5.8)` = 43 degrees above the floor (the probe reads 46) | the push is mostly sideways and 43-46 degrees up: it lifts the end. Much bigger and the rib is a ramp to rest on (the first try, 8 mm spheres) |

Measured on the mesh (`probes/capsule_corner.py`; the capsule as its axis segment on a
0.4 mm voxel distance field, so good to about 0.3 mm; the capsule rides 0.5 mm above the
floor because the voxelised floor is a staircase), middle bay:

| Case | Tip from the wall, with / without ribs | Contact on the capsule |
|---|---|---|
| Along the fall line, centred on rib 1 or rib 2 | **4.8 / 0.7 mm** | the rib's end, 3.9 mm below the axis, 46 degrees elevation: pushes the end UP |
| Along the fall line, centred in the gap between two ribs | 0.7 / 0.7 | the two ribs' shoulders, 1.8 mm below the axis, 19 degrees: nests in the channel and lifts straight out (nothing above the axis), so it does not wedge |
| Along the fall line, beside rib 1 against the divider | 0.7 / 0.7 | rib 1's flank, 0.9 mm below, 10 degrees |
| Lying along the wall | underside 2.25 mm above the floor (0.28 without) | rests on the ribs: the passive part, which a rib row of 11 mm pitch cannot avoid under a 26 mm capsule |

The sign convention the review used ("contact above the axis") applies to a force on the
cap from a bead higher than the axis; here the beads are low, so the contact is BELOW the
axis and the reaction on the capsule points up, which is what lifts it. Slices of the last
bay's corner (stop block, filler, buttress, side wall, ribs) at z 26 to 48 mm show no pocket
deeper than 3 mm that a capsule end cannot reach (every 90 degree corner leaves a cusp of
2.3 mm); the filler was widened to the stop block's width after the slimmer buttress left a
3 x 6 mm nook beside it. If the next print shows the ribs are not enough, a filled
45 degree ramp along the corner is the stronger fix.

### Derived: hopper A's flare (D42)

| Quantity | Formula | Value |
|---|---|---|
| Lean | `flare_deg` from vertical, inner face from the chute floor's end `(192.0, 156.2)` | 30 degrees |
| Inner face at the seat plane (z 186) | `192 + (186 - 156.2) x tan 30` | 209.2 (192.0 before) |
| Outer face | parallel, 3.18 mm horizontally (2.75 normal), starting at z 155.55, the back edge of the cubby's ceiling | 194.8 at z 155.55, 213.0 at the rim |
| Mouth A, front to back | inner face less the leaning divider | 56.6 under the lid (39.4), 59.7 at the rim, 48.9 between the seat ledges (33.4) |
| Mouth B | | 62.6; B : A = 1.11 (was 1.59) |
| Fill lid | `hop_mouth_d - 2 x 0.30` | 121.0 long (104), 233.8 wide, 3 thick |
| Outer overhang | | 30 degrees from vertical, inside the 45 rule |
| Footprint | | 243 x 213.0 x 189 (limit 246 x 246 x 250); 243 = 240 + the 3 mm rail |

The chute floor is not touched: it ends at its 40 degrees and the wall carries on at
60 from horizontal, so no floor shallower than the ramp appears and nothing rests on
it. The back corners' rounding follows the lean (a sheared cutter, nicked 0.03).

### Derived: rail, groove and buttress (D43)

| Quantity | Rev 10 | Rev 11 |
|---|---|---|
| Rail out of the wall `rail_out` | 5.0 | 3.0 |
| Rail root / tip width | 7.0 / 11.0 | 3.6 / 6.0 |
| Groove depth `rail_out + rail_depth_clear` | 5.4 | 3.4 |
| Buttress into the bay `rail_boss` | 7.0 | **3.0** |
| Buttress length `rail_boss_w` | 23 | 14 |
| Skin, groove floor to tray A | 4.4 | 2.4 (= wall_div) |
| Buttress either side of the groove (`margin - rail_clear`) | 5.8 | 3.8 |
| Groove front-lip bevel `groove_chamfer` / buttress back bevel `boss_bevel` | 3.0 / none | 1.0 / 1.0 |
| `rail_clear` | 0.20 | 0.215 (0.40 since D51) |

The dovetail's flank slope (0.4) is unchanged. The lug (x 3.3 to 7.3, y 5.6 to 11.8)
clears the buttress, which starts at y 15.8, by 4 mm (3.2 before).

### Derived: divider / front wall joint (revision 11)

The flow voids' fillets are rounded in the (y, z) profile only, so each divider met
tray A's front wall in a bare 90 degree T. `front_fillets()` adds a 2 mm quarter-round
in each of the twelve corners from the floor to 1 mm under the scallop line (nicked
0.03 so the cutter crosses the faces instead of lying tangent to them). Measured on
the mesh: the fillet's arc is solid at 12, 25, 40 and 50 mm, and the solid run
along the corner's diagonal is 3.49 mm at each, above the divider's 2.4.

### Derived: capacity (D37 numbers re-measured), `probes/capacity.py`

| Row | Middle bay | End bays | vs 147.4 mL | Days at one/day |
|---|---|---|---|---|
| Row A, front tray, crossing chute, flared hopper | **438.2 mL** | 428.4 / 428.8 | 2.97x | 266 |
| Row B, back tray, plain ramp | **200.2 mL** | 198.3 | 1.36x | 122 |

Row A gained 10 mL from the flare and lost a little to the beads, fillets and stop
blocks; the end bays of row B gained 5 mL from the slimmer buttress. The cubby is
unchanged by this revision.

### Derived: the section (D46)

`fit_section.scad` now cuts at `wall_x0(4)`, the left face of divider 4, so the left
wall is the whole 2.4 mm divider; it runs the whole height and depth. Body 50.2 x
213.0 x 189 mm, 523.5 cm3; pick-lid end 49.7 x 139.3 x 22.7 (21.4 cm3); fill-lid end
45.9 x 121.0 x 3 (16.5 cm3); coupon 124 x 30 turned 90 degrees. Total with the coupon
about 579 cm3, against 503 for test print 3 (about 7 h in PETG): expect about 8 h.

### Revision 11 review (K1-K4)

**K1, the skin's free height** (`probes/skin_free_height.py`, vertical rays in YZ on the real
mesh at the skin's middle x = 235.4 and at three depths across the groove):

| At | Front lip top | Skin top (max over the groove's width) | Skin above the lip, before | after |
|---|---|---|---|---|
| groove floor + 0.2 | 94.81 | 97.08 | 6.35 mm (2.65 x the skin) | **2.26 mm (0.94 x)** |
| mid groove | 95.39 | 97.08 | 6.03 (2.51 x) | **1.69 (0.70 x)** |
| mouth - 0.3 | 95.79 | 97.08 | 5.24 (2.18 x) | **1.28 (0.53 x)** |

The plane rises 0.96 mm per mm toward the back, so a skin that follows it over a groove 6.4
mm wide climbs 6.1 mm above the front lip. `skin_cap_z` trims the skin's top flat, one skin
thickness above the lowest front-lip top; the back lip is not touched, so the skin ends in a
90 degree inside corner against it, and the front lip is not touched. The trim reaches
0.4 mm past the groove floor into the groove's own air, so it clips the back lip's lowest
corner by at most 0.14 mm. The front-lip bevel went from 1.5 to 1.0 mm (the lips stay
higher); the countersink starts 0.06 mm off the groove floor, leaving a 0.06 mm strip of
un-bevelled lip beside it, below what the nozzle can print.

**K2, thin regions in horizontal slices** (the failing check in `probes/corner_thickness.py`
slices the break-out zone every 0.25 mm and opens each slice with a 2.35 mm disc, i.e.
nothing thinner than the 2.4 skin may survive; 465 regions of 0.2 mm2 or more on the right,
184 on the left; every one is one of these):

| Named feature | Where | Size | Why it is not a defect |
|---|---|---|---|
| Convex plan corner | every 90 degree vertical edge of the buttress and wall, at every height | 0.30 mm2 (`r^2 (1 - pi/4)`) | an opening always shaves a square corner |
| Dovetail lip tip | the lips' 70 degree wedge at the outer face (x 239.6, y 20.3 and 25.3), every height | 0.64 mm2 | geometry of the dovetail, present since revision 3 |
| Lip tip meeting the bevel | within 2.5 mm of the outer face | up to 5 mm2, 1.25 mm tall | the bevel run-out crossing the wedge tip |
| Grazing slice of the front-lip bevel | y 18.6-19.7, x 236.4-238.4, z 93.97-95.2 (the K2 regions: 7.6 mm2 at x 238.4, 2.8 at x 239.1) | 1.25 mm of height | the bevel, measured in the plane's frame, is 2.4 degrees from horizontal, so a horizontal slice within a millimetre of its height shows only a sheet of lip; below it the lip is solid, 3.5 mm in y |
| Grazing slice of the buttress's back-top bevel | x 235.4-235.8, y 28.7-29.0, z 103.2-104.0 (the K2 region: 5.4 mm2) | 1 mm of height | the same, on the 1 mm bevel at the buttress's back |

The edge-angle test is the one that says "no knife edge": no convex edge under 60 degrees
and over 0.5 mm long in either zone (the sharpest are the 46 degree edges where the groove
floor meets the plane, 0.1 mm long, and the lips' 70 degree wedge).

**K4, the flat sliver.** The 0.8 mm2 downward-facing flat at z 156 came from the lower back-
corner cutter ending 0.5 mm above the sheared one that starts the lean: it left a ledge.
It now ends where the sheared cutter starts (`flare_zo`), which is the back edge of the
cubby's ceiling (155.55), and an assert ties the two. 0.1 mm2 remains (below the nozzle).


## Revision 12: the edge pass (D48) and the final print files (D49)

Test print 4 is skipped; the user goes straight to the full unit. D48 audits every edge
class of the three parts. Decisions: **T** treated now (new), **E** already treated in an
earlier revision and kept, **K** kept sharp on purpose (functional), **L** left square by
judgement (not worth a cut, or the cut would make something worse). `probes/edge_pass.py`
tests every T row on the real meshes.

### Audit, body (print orientation = as modelled)

| # | Edge | Treatment before | Decision | Reason |
|---|---|---|---|---|
| B1 | Base perimeter (the bed face, 4 sides and 4 corners) | square | **T** 0.5 mm 45 degree chamfer | elephant foot; comes from the outer tool (below), so it follows the rounded corners |
| B2 | Foot-pad recess mouths (4, on the bed face) | square | **T** 45 degree lead-in cone, 0.5 mm at the bed face, crossing the recess wall at 0.5 | elephant foot closes a recess mouth by a few tenths; the 10 mm stick-on foot must still enter. The recess itself is not smaller |
| B3 | Vertical outer corners (4) | round r 1.2 (separate cutters) | **T** round r 1.5, same surface as B4/B5 | one dilation, no second tangent line (INCIDENTS) |
| B4 | Top edges in section (the step, the rim, the back lean, the pick plane's back end) | round r 1.5 | **E** unchanged | The dilation tool's lower half is a flat-bottomed cone, so the down-facing back lean (D42, 30 degrees) is dilated by r cos 30 instead of r: the whole lean sits 0.20 mm inside its nominal plane, its wall is about 2.55 mm normal instead of 2.75, and the top-back round has a 30-degree crease where it meets the lean (y 212.9, z 187.5). Cosmetic; accepted (rev 12 review F1). |
| B5 | Side faces' perimeter (x = 0 and x = 240: along the pick plane, the step, the rim, the back lean) | square | **T** round r 1.5 (hand-carried edge; up-facing or vertical, so a round, not a chamfer) | the side walls are 2.8 thick: 1.3 of flat is left. The rail-1 break-out zone on the right face was re-probed with the round running through it (below) |
| B6 | Front edge of the pick plane (130 degrees) | 0.16 mm easing | **E** unchanged | |
| B7 | Tops of dividers, walls and the front wall's pillars on the pick plane, inner edges | square | **K** | the pick lid's seating plane and its 0.2 float; a 2.4 wall top with a bevel on each side keeps 1.4 of flat for nothing |
| B8 | Scallop floor edges, front face and tray side (5 floors) | square | **T** 0.7 mm 45 degree chamfer following the outline, fading to nothing up the r 6 corners | a finger rests on it and a pill is pulled over it. Not applied up the vertical sides: the divider tips there are already thinned to 1.6 by `scallop_over` |
| B9 | Scallop sides / divider tips above the floor, pillars beside the end bays | square | **L** | the tips are 1.6 x 3.8 mm; any bevel feathers them. The pillars are the stop blocks' front |
| B10 | Fill mouth rim, inside, 4 edges | square | **T** 0.45 mm 45 degree chamfer (a cone of the opening), also a lead-in for the lid | 0.45 and not more: the front rim wall is 2.4 wide and loses 1.5 to the outer round (0.45 of flat left). Not 0.4 (see INCIDENTS) |
| B11 | Fill mouth rim, outside (the step, the back lean, the sides) | round r 1.5 / square | **E** / **T** by B4, B5 | |
| B12 | Fill-lid seat ledges, divider tops at the seat plane, the lid's 0.30 recess walls | square | **K** | the lid rests on them; the 0.30 fit |
| B13 | Pull-lip notch (the wall cut down to the seat across 34 mm), its vertical edges and its floor edge | square | **L** | the finger works under the lid's lip, not on these edges; they bound the lip's clearance of 2 mm per side. Named as the one hand-reached edge left square |
| B14 | Cubby mouth in the back face: both side edges and the lip's top edge (z 76 since D50; the cone's low edge follows `cubby_lip_h`, nothing else changed) | square | **T** 0.5 mm 45 degree chamfer (a cone of the mouth, its top on the 45 degree ceiling less 0.05) | where a hand goes in. 0.5: the side walls are 2.8 wide and lose 1.5 to the outer round (0.8 of flat left) |
| B15 | Cubby mouth, ceiling edge (135 degrees) | obtuse | **E** | |
| B16 | Cubby inside corners: floor / front wall, floor / side walls, ceiling / side walls, ceiling / front wall | square | **T** 2 mm fillet, three-dimensional (the void is dilated by a ball) | easier cleaning |
| B17 | Cubby lip, inner top edge | square | **L** | it is the lip's inside edge, 2.8 wide and 73 high (D50); accessories lie against it flat |
| B18 | Male rail and groove edges (dovetail profile, lead-in cone, rail undersides, groove countersink and bevels) | as D28, D39, D43 | **K** | the coupon must still match; the rail-1 groove bevels are the K1/K2-verified geometry |
| B19 | Label recess edges | square | **K** | the recess is 0.5 deep and the tape is 0.16: a bevel would fill it |
| B20 | Stop block, filler, lug contact faces and their 0.5 mm clearance, the lid lug sweep | square | **K** | D38 |
| B21 | Stop block, filler and buttress roots (their concave edges to the floor and walls) | square | **L** | they are fused into the end bay's corner behind the contact faces, in the one place a capsule lies against the wall; a fillet at the stop block's back-face root would run into the lug's swept envelope. The corner beads (D41) are already there to push a capsule away |
| B22 | D41 rib geometry and roots | as D41 | **K** | the push-stop function is measured (`capsule_corner.py`); a root fillet changes it |
| B23 | Outlet openings' lower edges (the hanging wall between the trays, hopper B's front wall) | square, with 8 mm corner chamfers | **L** | a downward bridge edge; a bevel is an overhang and nothing touches it (36 mm of clear height under it) |
| B24 | Flow-void corners in section (tray A and B floors, chute foot, porch, both hoppers, the D42 flare, the vault) | fillet r 2 | **E** unchanged | |
| B25 | Tray A front wall / divider and side wall vertical corners | r 2 gusset (D46) | **E** unchanged | |
| B26 | Tray B front wall / divider and side wall vertical corners (10) | square | **T** r 2 gusset from 1 mm under the floor to 2 mm under the wall's top plane | pills pile against that wall, as against tray A's front wall |
| B27 | Divider / floor edges along the flow, and the vertical corners of the chute, tray B's back wall and both hoppers | square | **L**, impractical | a three-dimensional fillet of those voids stands free where the later cuts take the wall away: above the seat plane (the seat cuts remove the dividers but not a 2 mm gusset beside them) and over the scallops. Tried on paper against the cuts, not hacked; the flow corners that matter (floors, ramps, the foot) are the profile fillets |

### Audit, pick lid (print orientation: plate top face on the bed)

| # | Edge | Before | Decision | Reason |
|---|---|---|---|---|
| P1 | Plate top face perimeter, all four sides (the bed face) | chamfer 1.0 | **E** | already over the 0.4 to 0.6 elephant-foot chamfer |
| P2 | Plate underside, front and back edges | chamfer 1.0 | **E** | |
| P3 | Plate underside, x-end edges | square | **T** 0.8 mm chamfer, from y = 0.2 back | up-facing in print; the end face keeps 3 - 1.0 - 0.8 = 1.2 mm of flat |
| P4 | Skirt bottom edge | chamfer 1.0 | **E** | |
| P5 | Skirt outer end edges (2 vertical edges, where the lid is pinched) | square | **T** 1.0 mm chamfer, not a round | the outer face hangs 43.8 degrees off vertical in print; a chamfer between it and the vertical end face stays inside that. Revision 13: now one chain with the plate's top chamfer, see P11 |
| P6 | Skirt inner end edges | square | **K** | they face the body's front face across the 0.35 clearance |
| P7 | Seating plane (underside), skirt clearance, lug and its contact face | | **K** | |
| P8 | "FRONT" relief edges | square | **L** | 0.6 mm of text |

### Audit, fill lid (print orientation: plate top face on the bed)

| # | Edge | Before | Decision | Reason |
|---|---|---|---|---|
| F1 | Top perimeter (the bed face), plate and lip | chamfer 1.0 | **E** | |
| F2 | Plan corners, plate and lip | round r 2 | **E** | |
| F3 | Underside perimeter of the plate | 0.6 lead-in chamfer | **K** | the fit's lead-in (0.30 clearance) |
| F4 | Pull lip underside perimeter, front and sides (the back is buried in the plate) | square | **T** 0.5 mm chamfer | a fingertip hooks under it |

Counts over the 39 rows: **T 12** (body B1, B2, B3, B5, B8, B10, B14, B16, B26; pick lid P3, P5; fill lid F4),
**E 11** (B4, B6, B11, B15, B24, B25; P1, P2, P4; F1, F2), **K 9** (B7, B12, B18, B19, B20, B22; P6, P7; F3),
**L 7** (B9, B13, B17, B21, B23, B27; P8; B27 is the one named impractical). Body 27 rows, pick lid 8, fill lid 4.

### Derived: the outer solid is one dilation

Revisions 7 to 11 rounded the body twice: the silhouette's convex corners by an opening pass
in the (y, z) profile, and the four vertical corners by separate cutters at `corner_r` 1.2.
Rounding the side faces' perimeter as well meant a third family of cutters along straight and
oblique lines, each of which would have had to meet the others on their tangent lines (the
INCIDENTS class). D48 replaces all of it with one operation: the silhouette extruded across the
width is eroded by `edge_r_top` (1.5) and dilated by a ball of that radius (Minkowski). Every
convex outer edge is then the same rounded surface, the back corners follow the leaning wall
(0.20 mm inside it, see B4: the cone dilates a down-facing face by r cos 30), and the bed chamfer comes from the tool's shape: its lower half is a 45 degree cone
(the upper hemisphere hulled with a disc 0.5 under its equator, 1.0 in radius), so the bed face
is flat with a 0.5 mm bevel round it, corners included. `ball()` scales OpenSCAD's sphere by
1 / cos(180 / n), because the sphere has no vertex on the poles or equator and comes out 0.9%
small. `corner_r` and its asserts are gone; `edge_r_top <= wall_out - 1.0` replaces them.
The step's inside corner stays sharp (checked on the mesh); the lid probes are unchanged
(0.14 mm clearance at rest, at revision 12).

Measured with `probes/edge_pass.py` (point-in-solid pairs placed from `params.scad`) on the
three real meshes, all pass: bed face 0.96 mm narrower than the first full section; side face round
at the rim and on the pick plane; mouth chamfer on three sides; scallop chamfer on both faces
with the floor still at `trayA_front_h` mid-wall; cubby corners filled and its mouth chamfered;
tray B corner gusset; pick lid skirt and underside chamfers; fill-lip chamfer. Each part is one
watertight body, 17002 / 2178 / 460 triangles, and has no edge under 0.001 mm (revision 11's body
had six).

### Derived: what else moved, and what did not

| Check | Revision 11 | Revision 12 |
|---|---|---|
| `validate_scad.sh --all` | 14 passed, 0 failed, 3 n/a, 0 inconclusive, 1 advisory | the same, verbatim: `COVERAGE: 14 passed, 0 failed, 3 not-applicable, 0 inconclusive, 1 advisory (18 checks reported).` |
| Capacity, middle bay (A / B) | 438.2 / 200.2 mL | 438.3 / 200.2 mL |
| Capacity, end bays (A / B) | 428.4, 428.8 / 198.3 | 428.4, 428.8 / 198.3 |
| `corner_thickness.py`: right break-out zone, thin regions | 465, all named | 422, all named; 0 knife edges |
| Skin above the front lip (groove floor / mid / mouth) | 2.26 / 1.69 / 1.28 mm | 2.26 / 1.69 / 1.57 mm (limit 2.4) |
| `lid_retention.py` (a) to (h) | all pass | all pass; clearance at rest 0.14 mm |
| `overhang_scan.py` | the declared bridges; pick lid 117 mm2 steep, fill lid 62 | the same bridges; pick lid 92, fill lid 75 (the lead-in and bed chamfers at exactly 45.0); the body reads 92 mm2 more steep (2719 to 2811): the cubby ceiling, exactly 45.0 degrees before and now, whose triangles now fall either side of the threshold on rounding noise |
| Body bounding box | 243.0 x 213.01 x 189 | the same |

Final part sizes, print orientation: body 243.0 x 213.0 x 189.0 mm (2281 cm3), pick lid
239.0 x 139.3 x 22.7 mm (103 cm3), fill lid 233.8 x 129.0 x 3.0 mm (85 cm3).

### D49: the final print files

`python3 build/maquette/make_plate.py final --export` re-renders `build/print_ready/{body,pick_lid,fill_lid}.stl`
(print orientation, z = 0) and writes `build/final/final_{body,pick_lid,fill_lid}_256.3mf`:
core-spec 3MF, one named object each (`pill_organizer_body`, `pill_organizer_pick_lid`,
`pill_organizer_fill_lid`), centred on the 256 x 256 plate at z = 0. Each is read back and
compared with its STL (size within 0.001 mm, volume within 0.01%, triangle count, watertight).
The limit checked is the printer's usable footprint, **5 to 251 mm** (`max_part_x` 246), not
10 to 246: the body with its rail is 243 mm wide and cannot lie within a 236 mm window.
Centred, the body spans x 6.5 to 249.5, y 21.5 to 234.5; the pick lid x 8.5 to 247.5, y 58.4 to 197.6;
the fill lid x 11.1 to 244.9, y 63.5 to 192.5.

## Revision 13: the half-octagon openings (D52) and the one-piece pick lid (D53)

Test print 4 (the revision 11 section, PETG, 2026-10-04) showed the arches over the openings drooping
a little and the pick lid reading as two rectangles welded together, and every stub of the slim-rail
coupon too large (D51). The first pass at the openings (D52) used a 10 mm crown on both; the review of
revision 13 found that outlet B then blocks a capsule against a divider, and D54 gave it 20 mm.

### Derived: the opening profiles (D52, D54)

Each opening is the bottom face of a 2.4 mm wall seen across the bay: vertical dividers, a 45
degree facet from each, a flat crown. The facet is `outletA_chamfer` / `outletB_chamfer` =
(`bay_w` - crown flat) / 2: tray A 17.48 (crown 10), outlet B 12.48 (crown 20), in both run and rise.
45 degrees from horizontal is the facet that climbs least while still printing: a steeper one climbs
more per mm of run, a shallower one overhangs past 45 degrees. Measured on the real body by
`probes/outlet_arch.py` (one ray up the opening at 899 distances from the divider, bays 0 and 4; all pass):

| | Tray A mouth | Outlet B |
|---|---|---|
| Crown height, flat | 67.01, 10.0 mm | 136.99, 20.0 mm |
| Facet | 45.0 degrees, 17.48 run and rise | 45.0 degrees, 12.48 run and rise |
| Ceiling at the divider face (distance 0.3) | 49.83 | 124.81 |
| Ceiling a pill radius (5.5) from the divider | 55.03 | 130.01 |
| Unsupported span across the top | 10 mm (was 29) | 20 mm (was 29; D52 had 10) |
| Throat at the bay centre, perpendicular to the 40 degree floor | 26.03, unchanged | 19.2, unchanged |
| Throat at the divider face | 12.6 (was 19.9) | 9.6 (was 13.0, the one test print 2 fed through; 5.7 at a 10 mm crown) |
| Throat a pill radius (5.5) from the divider | 16.9 (was 24.1) | 13.8 (was 17.2; 10.0 at a 10 mm crown) |
| Width over which the throat clears a pill (11 mm) | 44.96, all of it | 41.3 of 44.96 (31.3 at a 10 mm crown) |
| Worst capsule pose, mesh sweep (margin to the throat) | +4.43 mm | +1.37 mm (-2.47 at a 10 mm crown) |
| Pile margin that bounds the crown | 1.1 mm (front wall over a 25 degree pile) | 1.4 mm (D33: 6.4 against the 5.0 floor) |

The worst pose (D54). A 26 x 11 spherocylinder lies on the 40 degree ramp under the wall's back-bottom
edge; for each position across the bay and each orientation from 0 to 90 degrees its height over its footprint
is compared with the throat there (vertical opening less the facet's drop, less `wall_div` x tan 40, times
cos 40). The margin is the smallest throat-minus-capsule over all of them. At outlet B this was -2.47 mm
at a 10 mm crown (the review's scratch sweep, reproduced) and is +1.37 at 20. The margin is smaller than the
simple "throat a pill radius out minus 11" (2.8) because a capsule lying across the facets is also under the
lower ceiling at its ends. The asserts in `params.scad` guard the simple form (throat a pill radius from the
divider >= `pill_dia` + 1 on both openings; 13.79 and 16.86 against 12), the probe the full sweep (>= +1.0). At
+1.0 the shortest outlet B crown is about 19 mm (0.98 at 19, 0.6 at 18); 20 was chosen for a round number and a little margin.

Why the crowns did not rise. A higher crown at the bay centre would give the facets less to take off the
corners, but it raises the pile that forms at the centre of the opening by the same amount, and the margins
above are all that is left: raising by 9.5 mm (to keep the old corner throat at a 10 mm crown) would put
tray B's pile 3.1 mm over the wall in front of it. So the centre is unchanged (`mouthA_min`, `outlet_h` 27,
D33's margin 6.39 and tray A's front-wall margin 11.1 at 30 degrees) and the corners pay.
`mouthB_corner_demonstrated` is kept at the old chamfer (13.0) as the only corner number a print has shown.

The other flat bridges in the bays, from `overhang_scan.py` on the print-ready body. Hopper B's and
hopper A's ceilings are the 40 degree chute (vaulted, 44.8 from vertical, listed as steep) and the
leaning back wall, none flat. The flat faces left in the body are the porch ceiling under tray B
(8530 mm2 across five bays, **44.96 x 40 mm each**), the crowns above (110 mm2 each at tray A, 220 at
outlet B, five bays), and label, scallop and foot-pad ceilings of 90 to 313 mm2 that were there before. The porch
ceiling is not an opening arch (D29: a declared bridge) and is left. Droop risk: it is the longest unsupported
flat in the body, 2.2 times outlet B's 20 mm crown and 4.5 times tray A's. Test print 4 reported no complaint
about it, but the arches' complaint was the same defect at 29 mm. It is a watch row in `TEST_PRINTS.md`; the
fix, if it sags, is a gable in its ceiling like the vault's, at the cost of chute height that D33's margins
do not have.

### Derived: the one-piece pick lid (D53)

| Quantity | Value | Note |
|---|---|---|
| Profile | one closed polygon, 42 points (`LID_PROFILE`), extruded once across 239 mm | the union of `PLATE` and `HOOK` is gone; `pick_plate` and `pick_hook` sub-features became `pick_body` |
| Wall | plate 3.0 perpendicular (4.15 vertical), skirt 3.0 horizontal | the skirt was 2.65 (`pick_lid_hook_t` 3.0 to 3.35); outer face at y -3.35, inner face still -0.35 |
| Bend turn | 46.2 degrees (90 - slope) | |
| Inside fillet | r 3.0 (= `lid_t`), tangent length 1.28 | adds 0.26 on the bisector |
| Outside round | r 1.5, tangent length 0.64 | removes 0.13 on the bisector |
| Wall at the bend, on the bisector | 3.39 | 3.0 / cos(23.1) = 3.26 mitre, less 0.13, plus 0.26 |
| Other convex corners | 45 degree chamfers, 0.586 on a right angle (1.69 at the plate's acute back-top corner) | the offset-chamfer rule of D27 |
| Lid size (print orientation) | 239.0 x 139.5 x 22.7 mm, 105.5 cm3, 2418 triangles | was 139.3, 103 cm3, 2178 |
| `EXPECTED_BBOX` | [239.0, 87.95, 111.63] | y was 87.6 |
| Closest skirt / fillet to body | 0.101 mm at the nominal pose (was 0.14); 0.141 on the stops; 0.046 at +0.2 mm up-slope of nominal, 0.010 at +0.3, touching at about +0.36 | the fillet, at y 0.2 to 0.3, against the body's front top edge round; the skirt used to be the first up-slope contact, at +0.485. Measured by `lid_retention.py` (e2) on the mesh |
| Up-slope room from the stops | 0.857 mm (the tilt (e2) needs 0.191) | was taken as 1.0 mm until the review of revision 13 |
| Motion sweeps (4) | all pass, worst clearance 0.100 mm (limit 0.05) | |

The outside round against the bed. In print the plate's top is on the bed and this corner is its
edge. The round starts tangent to the bed, rises through the 46.2 degree turn to meet the skirt's own
face (which prints at 46.2 degrees from the bed), and so reaches full slope after R x (1 - cos 46.2) =
0.31 R of height. Horizontal step per 0.2 mm layer, taken at each layer's mid-height:

| R | Height of the round | Steps, layers 2 to 4 | Worst step | Worst angle from vertical |
|---|---|---|---|---|
| 1.0 | 0.31 | 0.28, 0.19, 0.19 | 0.28 | 54 |
| **1.5** | **0.46** | **0.36, 0.22, 0.19** | **0.36** | **61** |
| 2.0 | 0.62 | 0.43, 0.27, 0.20 | 0.43 | 65 |

Beyond the round the face is the skirt's 0.19 mm per layer (46.2 degrees). Revision 12's chamfer at
this corner printed a single 66.9 degree facet. R = 1.5 is the smallest radius in the asked range and is
kept above the 1.0 mm end chamfer that runs round it (a chamfer cone at x = 0 would otherwise reach the
axis); a PETG elephant foot of 0.2 to 0.3 mm at the bed softens the first step. `overhang_scan.py` now
lists the round's first 1.2 mm as steep (300 mm2 in all against 92) and the end chamfer where it lies on
the bed at exactly 45.0 degrees.

The end chamfer is built as a chain: the lid's outline from below the skirt, round the bend (the same 16-point
arc the profile uses, at its facet middles) and along the top face is walked as a polyline, and each segment's
cutter is the hull of two mitred triangular sections. Neighbouring pieces share a section exactly. Measured on
the mesh: the end section at x = 0.5 stands 0.500 to 0.501 mm inside the full section for the whole outer chain,
bend included. The first two versions failed: analytic prisms and a cone handed over on a tangent line (8 zero-area
faces, the INCIDENTS class again), then segments whose chain points sat on the profile's own facet-to-facet lines left
60 zero-area faces; the chain's points are now facet middles and 2 mm into the straight faces (`INCIDENTS.md`).
Each part is one watertight body with no edge under 0.001 mm (0.0098 mm shortest, the same as revision 12's).

### Audit rows added to the pick lid (continues "Audit, pick lid")

| # | Edge | Before | Decision | Reason |
|---|---|---|---|---|
| P9 | Outside of the bend (plate top / skirt outer corner, on the bed in print) | 0.2 mm offset-chamfer facet (a 46 degree turn) | **T** round r 1.5 | no seam line; worst layer step 0.36 mm (table above) |
| P10 | Inside of the bend (plate underside / skirt inner face, a 134 degree concave corner) | sharp, plus a 2 mm skirt top inside the plate | **T** fillet r 3.0 | up-facing in print, so no overhang; `lid_t` is the asked minimum; costs 0.04 mm of clearance |
| P11 | x-end edge round the bend: plate top face, bend, skirt outer face | a 1.0 chamfer along the top and a separate 1.0 chamfer down the skirt, meeting in a seam | **T** one 1.0 chamfer, continuous | the visible side of the two-rectangles look |
| P12 | Underside x-end chamfer (P3), where it starts | y = 0.2, behind a sharp crotch | **E** start moved to 0.25 mm past the fillet's end (y 0.82) | in front of that the surface is the fillet, whose end edge stays square like the skirt's inner end edges (P6) |

Counts over the 42 rows (revision 12's 39 and P9 to P11; P12 changes P3's start and adds no row):
**T 15**, **E 11**, **K 9**, **L 7**. Body 27 rows, pick lid 11, fill lid 4.

### Derived: what moved in revision 13

| Check | Revision 12 | Revision 13 |
|---|---|---|
| `validate_scad.sh --all` | 14 passed, 0 failed, 3 n/a, 0 inconclusive, 1 advisory | the same, verbatim: `COVERAGE: 14 passed, 0 failed, 3 not-applicable, 0 inconclusive, 1 advisory (18 checks reported).` |
| Capacity, middle bay (A / B) | 438.3 / 200.2 mL | 437.7 / 200.0 mL (the facets) |
| Capacity, end bays | 428.4, 428.8 / 198.3 | 427.9, 428.3 / 198.1, 198.1 |
| `lid_retention.py` (a) to (h) | all pass; clearance 0.14 mm | all pass; 0.10 mm at the nominal pose, 0.141 on the stops |
| `outlet_arch.py` | n/a | all pass (crown, declared flats 10 and 20, facet 45.0, divider-face height, mirror, worst pose +4.43 / +1.37 mm) |
| `edge_pass.py` | all pass | all pass, with the bend rows (chamfer round the bend at 25, 50, 75 % of the round, both ends) |
| `overhang_scan.py` | body flat 9664, steep 2811; pick lid steep 92; fill lid 75 | body flat 9356, steep 3028 (the 45.0 degree facets); pick lid steep 300; fill lid 75 |
| Body solid | 2309.6 cm3 | 2314.8 cm3 (the facets) |
| Triangles (body / pick lid / fill lid) | 17002 / 2178 / 460 | 17016 / 2418 / 460 |

The final plates were rebuilt with `python3 build/maquette/make_plate.py final --export`: the body plate
(also carries D51's `rail_clear` 0.40, which the previous plate predates) and the pick lid plate changed,
the fill lid plate did not; the section plate (`build/section/`) was rebuilt too, because `fit_section.scad` cuts the body
and the pick lid. The coupon was not touched. Final part sizes, print orientation: body 243.0 x 213.0 x 189.0 mm
(2315 cm3), pick lid 239.0 x 139.5 x 22.7 mm (105.5 cm3), fill lid 233.8 x 129.0 x 3.0 mm (85 cm3). Centred, the
body spans x 6.5 to 249.5, y 21.5 to 234.5; the pick lid x 8.5 to 247.5, y 58.2 to 197.8.


## Revision 14: the rail coupon (D56) and the groove profile (D57)

| Quantity | Before | After |
|---|---|---|
| Groove section | the male's two widths over `rail_out + rail_depth_clear` (flank slope 0.353) | the male section offset by `rail_clear` (slope 0.4), straight walls for the last 0.4 mm |
| Flank gap at depth 0 / 1 / 2 / 3 mm, `rail_clear` 0.30 | 0.300 / 0.253 / 0.206 / 0.159 | 0.300 at every depth |
| Gap at the rail tip at `rail_clear` 0.20 | 0.059 | 0.200 |
| Groove widest width | `rail_tip_w` + 2 `rail_clear` | unchanged, so `rail_boss_side` (3.8) and the skin asserts hold |
| `rail_clear` | 0.28 (D55) | 0.30 (D56, a starting point) |
| Coupon | 5 stubs, pitch 18, block 0.4 mm from the next stub | two rows of 5, pitch 28, the seated block 10 mm from the next stub; ribs row 0 to 0.20 mm |

Measured on the meshes: `probes/coupon_fit.py` (gap equal to the label at six depths on every plain stub, rib interference as labelled,
tightest gap of the 0.10 stub +0.093), the body's sections at z 60 and 150 (gap 0.3000 at depths 0.1 to 3.2 on both grooves),
`corner_thickness.py` (skin 2.40, buttress 3.70) and `skin_free_height.py` (2.30 of 2.4) still pass.
