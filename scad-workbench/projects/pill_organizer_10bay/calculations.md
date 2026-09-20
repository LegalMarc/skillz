# Calculations — pill_organizer_10bay

All lengths mm, all angles degrees. `tan(40) = 0.839100`, `tan(20) = 0.363970`,
`tan(30) = 0.577350`.

**Revision 3.** Revision 1 alternated tray / mouth / tray / mouth front-to-back
with four lids. Revision 2 grouped both fill mouths at the back under one lid
and both pick trays at the front under one lid, which forced a crossing.
Revision 3 keeps that topology and changes two things about the crossing
chute — the ramp angle, and a shallow porch under tray B — which together take
the envelope from 9.45 L to 5.54 L without dropping either row below the
90-day charge.

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

The repose figure now carries more weight than it did in revision 2, because
revision 3 spends margin against it deliberately — see "The porch" below. If
the real requirement turns out to be nearer mass flow (walls 55–60 degrees from
horizontal) rather than repose, the dead wedge grows rather than shrinks and
the ramp has to go back up. That is what the calibration coupon print is for.

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

## Derived — the porch (D12)

| Quantity | Formula | Value |
|---|---|---|
| Porch run | `yB_tray1 - yA_tray1` | 30.4 |
| Chute floor at the porch end | `base_z + porch_run x tan(20)` | 14.06 |
| Tray B floor | `+ chute_clear + chute_ceil` | **53.06** |
| Tray A rim | `= tray B floor`, by construction | **53.06** |
| Stagnant wedge on the porch | `0.5 x run^2 x (tan(30) - tan(20)) x bay_w` | **4.2 mL/bay**, 2.8% of a charge |
| Flow channel over that wedge | `chute_clear - run x (tan(30) - tan(20))` | **29.5** — 1.1x pill length, 2.7x pill diameter |

The porch is the whole reason tray B's floor and tray A's rim land on one line:
the 40-degree climb starts 30 mm further back, so everything behind it drops
about 25 mm with it.

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
| **Tray A** | 2.8 .. 30.8 | floor 3.0, rim 53.06 |
| Wall between trays | 30.8 .. 33.2 | |
| **Tray B** | 33.2 .. 61.2 | floor 53.06, rim 91.06 |
| **Chute A porch**, 20 deg | 30.8 .. 61.2 | floor 3.0 .. 14.06, ridge 39.0 .. 50.06 |
| **Chute A ramp**, 40 deg | 61.2 .. 136.0 | floor 14.06 .. 76.83 |
| **Hopper B mouth** | 63.6 .. 133.6 | floor 55.08 .. 113.82 |
| **Hopper A mouth** | 136.0 .. 168.0 | floor 76.83 .. 103.68 |
| **Overall** | | **235.0 x 170.8 x 141.0** (235 includes the 5 mm rail) |

Both mouths finish at `hopper_rim = 141`, which is what lets one flat lid cover
both. Both trays finish on one 31.8-degree plane from 53.06 at the front face to
91.06 at tray B's rim, which is what lets one flat lid cover both.

## Derived — capacity (measured from the rendered cavity meshes)

| Row | Per bay | vs 147.4 mL charge | Days at one/day |
|---|---|---|---|
| Row A — front tray, back mouth, crossing chute | **298.4 mL** | 2.02x | 182 |
| Row B — back tray, front mouth, plain ramp | **198.8 mL** | 1.35x | 121 |

Measured with the fill line at the underside of the lid (`fill_seat_z`), the
porch ribs subtracted and the fillets included — not from the idealised section,
which reads about 8% high on row B because it ignores the seat ledges.

Total across ten bays: **2.49 L** in a **5.54 L** envelope. Revision 2 held
3.27 L in 9.45 L.

## Derived — flow and escape paths

| Check | Value | Status |
|---|---|---|
| Chute ridge section | 36.0, constant | OK — 1.38x pill length |
| Row A outlet (the chute's own section at tray A) | 36.0 | OK |
| Row B outlet | 30.0 | OK — 1.15x pill length, 2.7x pill diameter |
| Ramp angle vs repose | 40 - 30 = 10 margin | OK, reduced from 18 |
| Porch angle vs repose | 20 - 30 = **-10** | BY DESIGN — see the porch table above |
| Porch lane vs pill diameter | 20.28 / 11.0 = 1.8x | OK for single file |
| Chute ceiling overhang, 40 deg leg | 50 from vertical | ADVISORY — past the 45 rule, internal surface |
| Chute ceiling overhang, porch leg | 70 from vertical | OK — bridged span cut to 20.28 by the rib |
| Wall between trays, above tray B's floor | 20.6 | OK — 1.9x pill diameter |
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
