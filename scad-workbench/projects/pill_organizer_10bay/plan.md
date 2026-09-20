# Plan — pill_organizer_10bay

## Task

A gravity-fed benchtop organizer for ten different supplement pills. Each of ten
bays takes a poured-in bulk charge (target: a ~90-day supply of one pill type),
holds it in a tall hopper, and feeds it by gravity down a steep ramp into a shallow
open pick tray at the front of that bay. Lifting one hinged lid exposes five pick
trays at once; two tiers give all ten. A separate, more positively-retained lid
closes each hopper mouth so the bulk charge cannot escape when the unit is moved or
knocked. Home use only — no transport, no child-resistance, no sealing claim.

Constraints taken from the brief and the sketch:

- Printer build volume 256 x 256 x 256 mm (single part must fit with real slicer margin).
- Ten bays, arranged two rows of five.
- Largest pill envelope 26 mm long x 11 mm diameter (covers a size-000 capsule and
  a large oval softgel).
- Modules gang left/right on rails so a second unit adds more pill types.
- Everyday pick lid hinges up and stays open on its own while picking.

## Architecture options

| Option | Description |
|---|---|
| Datum | **Terraced single body.** Tier A (pocket + hopper) at base level; tier B identical but raised onto a pedestal behind it, so both pick trays face the operator from the front like stadium seating. One printed body, two fill lids, two pick lids. |
| Alt A | **Two independent 5-bay modules** ganged side by side on rails, giving one row of ten. Half the print per piece, trivially within bed, but 480 mm of bench and it is not "two rows of five". |
| Alt B | **Mirrored valley single body.** Both hoppers outboard (one at the front face, one at the back face) with the two pick tray rows adjacent in the middle. Same footprint as the datum but roughly half the height and no pedestal dead volume; the back hopper is filled from the far side. |

## Comparison

| Criterion | Datum | Alt A | Alt B |
|---|---:|---:|---:|
| Matches the requested "two rows of five, one unit" | 0 | - | 0 |
| Both pick trays reachable from one standing position | 0 | + | 0 |
| Overall height (pouring clearance under a wall cabinet) | 0 | + | + |
| Filament / print time (pedestal is structure, not capacity) | 0 | + | + |
| Both hoppers fillable without turning the unit around | 0 | + | - |
| Bed fit margin | 0 | + | 0 |
| Number of distinct printed parts | 0 | + | 0 |
| **Uncertainty/risk** | 0 | + | 0 |

Alt A scores better on nearly every engineering axis but loses the one requirement
the user actually stated. Alt B is the datum's equal on requirement fit and better
on height and material, at the cost of walking around the unit to fill the far
hopper.

## Decision

| ID | Type | Criticality | Statement | Status | Evidence |
|---|---|---|---|---|---|
| D1 | Decision | Ordinary | Build the Datum (terraced single body). User was shown all three framings and chose the terraced two-rows-of-five single unit explicitly. | Confirmed | User answer, this session |
| D2 | Decision | Critical | Design pill envelope is 26.0 x 11.0 mm (length x diameter). Every bay width, outlet gap and ramp clearance derives from it. | Confirmed | User answer, this session |
| D3 | Decision | Ordinary | Max part footprint 243 x 243 mm, max height 243 mm — 256 mm bed less 13 mm for skirt/brim and bed exclusion zones. | Confirmed | INCIDENTS.md 2026-08-21 "P1S bed limit, 250mm too close to 256mm" |
| D4 | Decision | Ordinary | Ramp angle 50 degrees from horizontal for both tiers. Well above the ~30 degree static angle of repose of gelatin capsules and coated tablets on PLA, and its underside is a 50-degree-from-horizontal overhang, inside FDM's 45-degree-from-vertical comfort band. | Confirmed | Standard FDM overhang limit; angle-of-repose margin stated, not measured |
| D5 | Decision | Ordinary | Joining rails are straight-sided trapezoids defined by explicit top and bottom widths, extruded along Z, never by a flank angle. | Confirmed | INCIDENTS.md 2026-08-30 "dovetail bowtie, impossible 50deg angle" — a flank-angle-parameterised trapezoid self-intersected |
| D6 | Decision | Critical | Snap-fit dimensions (pick-lid C-clip on its rod, fill-lid tab engagement) are geometry-only at tier 2 — no calibration profile exists on this machine. A calibration coupon is proposed to the user rather than a single guessed clearance. | Confirmed | doctor.py: "Calibration profile: none -- fits are uncalibrated" |
| D7 | Decision | Ordinary | Hopper A and hopper B have equal ramp run, so one fill-lid part serves both; pocket A and pocket B are dimensionally identical, so one pick-lid part serves both. | Confirmed | Derived in calculations.md |

## Parts and dependency order

| Part | Depends on | Notes |
|---|---|---|
| body | - | The terraced two-tier body: 10 bays, both ramps, both pick trays, joining rails, label recesses, hinge rods, fill-lid seats. Print upright, no supports. |
| pick_lid | body | One part, printed x2. C-clips snap onto the body's hinge rod. `layout.scad` places it as `pick_lid` (tier A). |
| pick_lid_b | pick_lid | The SAME part placed a second time, at the tier offset [0, 113.2, 101.0]. Not a separate design -- listed because it is a separate layout placement. |
| fill_lid | body | One part, printed x2. Drops into the mouth onto a seat lip, retained by two cantilever snap tabs. `layout.scad` places it as `fill_lid` (tier A). |
| fill_lid_b | fill_lid | The SAME part at the tier offset. Again a placement, not a design. |
