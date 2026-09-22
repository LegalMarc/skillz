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

## Revision history

A **revision** here is a change that alters what the object is or how you use
it, not merely a dimension — each one required the whole suite to be re-run.
Revisions 1–3 were labelled by topology alone, which stopped being honest once
revision 3 kept absorbing changes to how you pick and pour; 4 and 5 are split
out to match. The decision IDs are the real change log and have always been
accurate.

| Rev | What changed | Decisions | Commit |
|---|---|---|---|
| 1 | Terraced two tiers, tray / mouth / tray / mouth front-to-back, four lids, hinged pick lids | D1–D7 | `165a436` |
| 2 | Both fill ports grouped at the BACK, both pick trays at the FRONT, two lids. Forces the crossing chute; both lids become lift-off; the pick surface becomes one sloped plane | D8–D10 | `9f98c89` |
| 3 | Ramp 48 → 40 degrees, a 20-degree porch under tray B, and a splitter rib to carry the porch ceiling. Envelope 9.45 → 5.54 L | D11–D14 | `82494c1` |
| 4 | Reach and pour. Tray A's rim set independently of tray B's floor, the hopper divider leaned to even the two fill mouths, the front wall scalloped and the lid's hook grown into a skirt | D15–D17 | `8944111`, `d521a1e` |
| 5 | The dead wedge becomes an accessory cubby with a 42 mm retaining lip, and two rows of 1/2 inch TZe tape recesses | D18–D19 | `4d129da`, `22db5bb`, `b2de005` |
| 6 | The independent review's fixes and the product pass. Front joining groove opened (it was blind); fill-lid snap given a real catch and a releasable barb; the label recesses actually sized for the tape; cubby ceiling to 45 degrees; porch to 25 degrees; finger notches on the pick lid, a pull lip on the fill lid, foot pads; print-ready export corrected | D20–D25 | `03023f7` |
| 7 | The vault: the crossing chute's 40-degree ceiling gabled across each bay so its face is inside the 45-degree overhang limit, which removes the last ADVISORY from the body. Every external edge and corner rounded or chamfered | D26–D27 | this branch |

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
| D4 | Decision | Ordinary | SUPERSEDED by D11. Ramp angle 50 degrees from horizontal for both tiers. Well above the ~30 degree static angle of repose of gelatin capsules and coated tablets on PLA, and its underside is a 50-degree-from-horizontal overhang, inside FDM's 45-degree-from-vertical comfort band. | Confirmed | Standard FDM overhang limit; angle-of-repose margin stated, not measured |
| D5 | Decision | Ordinary | Joining rails are straight-sided trapezoids defined by explicit top and bottom widths, extruded along Z, never by a flank angle. | Confirmed | INCIDENTS.md 2026-08-30 "dovetail bowtie, impossible 50deg angle" — a flank-angle-parameterised trapezoid self-intersected |
| D6 | Decision | Critical | Snap-fit dimensions (pick-lid C-clip on its rod, fill-lid tab engagement) are geometry-only at tier 2 — no calibration profile exists on this machine. A calibration coupon is proposed to the user rather than a single guessed clearance. | Confirmed | doctor.py: "Calibration profile: none -- fits are uncalibrated" |
| D7 | Decision | Ordinary | SUPERSEDED by D8. |
| D8 | Decision | Critical | Both fill ports grouped at the BACK under one lid, both pick trays at the FRONT under one lid -- two lids total. This forces a crossing: hopper A is the back mouth but feeds the front tray, so its chute runs enclosed under tray B and under hopper B (159mm at revision 2; 105 from revision 3). The crossing sets tray B onto a pedestal (81mm at revision 2; 53 from revision 3); that number is not a choice, it falls out of the chute clearance at ramp_deg and is asserted in params.scad. | Confirmed | User instruction, this session |
| D9 | Decision | Ordinary | Both lids lift off; neither is hinged. An L-section lid spanning an 81mm step has its mass centre ~48mm below any back-top pivot, putting its over-centre angle near 144 degrees (unreachable), and a front pivot runs the far corner into the benchtop at ~24 degrees. | Confirmed | Measured on the previous revision's lid; same geometry, worse step |
| D10 | Decision | Ordinary | The pick surface is a single sloped plane rather than two steps, so its lid is a flat plate. A Z-section lid cannot be printed without support whichever way it is laid, because one arm is always cantilevered. | Confirmed | This session |
| D11 | Decision | Critical | Ramp angle 40 degrees, not 48. The chute floor is also hopper A's floor, so a shallower ramp lowers hopper A, and hopper B's floor rides on the chute ceiling and comes down with it. 48 degrees was bought nothing but a self-supporting chute ceiling on an internal surface nobody sees; at 40 that ceiling is a 50-degree-from-vertical overhang, accepted with a sag allowance in chute_clear. Repose margin drops from 18 to 10 degrees, still ample against the ~30 degree estimate. | Confirmed | This session; angle sweep at a fixed envelope, build/section_study.png |
| D12 | Decision | Critical | Under tray B, and only there, the chute floor runs at 20 degrees instead of 40 -- the porch. The 40 degree climb then starts 30mm further back, so everything behind it drops: tray B's floor lands on tray A's rim. The porch is shallower than repose, so it carries a stagnant wedge of about 4 mL per bay (2.8% of a charge); the flow channel over that wedge stays 30mm, which is 1.1x pill length and 2.7x pill diameter, so nothing bridges. | Confirmed | User instruction, this session; stagnation and throat computed in calculations.md |
| D13 | Decision | Critical | A splitter rib runs down the middle of each porch. Tray B's floor is carried on the bay dividers alone -- the chute runs underneath, so the tray's own front and back walls never reach it. At 40 degrees that underside self-supported; at 20 it is a near-flat ceiling bridging the full 43mm bay, which is the exact defect logged on 2026-09-20 and the one no gate in the suite catches. The rib halves the bridge to 20.3mm and carries the slab directly. Cost: the porch becomes two 20.3mm lanes instead of one 43mm lane, so pills run single file through it. | Confirmed | This session; found by modelling the porch, not by the 2D study |
| D14 | Decision | Ordinary | Rail 1 moved from mid tray B to mid tray A. Under tray B its buttress stood in a porch lane and narrowed it below the single-file rule; tray A is a pick pocket, where a 5mm buttress in one corner costs nothing. | Confirmed | This session; asserted in params.scad |
| D15 | Decision | Critical | Tray A's rim is set independently of tray B's floor, at 42 rather than 53.06, which steepens the single pick plane from 31.8 to 38.7 degrees. Pills only pile to the chute mouth at 39 and slope forward from there to about 23 at the front wall, so a rim level with tray B's floor left a 32mm reach into the front tray every time. At 42 the reach is 21mm at the front and 28mm at the back, and the front face loses 11mm. How far the rim can drop is bounded by the wall that stops tray B spilling forward into tray A, asserted as trayB_front_retain. | Confirmed | User instruction, this session |
| D16 | Decision | Ordinary | The wall between the two fill mouths leans 8.8mm forward at the rim (17.3 degrees from vertical), pivoting where it springs off the chute ceiling. The mouths were 70mm and 32mm because the two rows' VOLUMES were held near each other; the number you actually meet, with a bottle in your hand, is the mouth. Leaning brings them to 62.1 and 39.9, about 3:2. It costs hopper B a wedge above its own floor and gives hopper A the same wedge, and it gives hopper A a mouth wider than its throat, which is the right way round for a hopper. | Confirmed | User instruction, this session |
| D17 | Decision | Critical | The lid plane and the front WALL are separated. The plane stays at 42 because its back end is pinned to tray B's rim and a lower front end cuts the wall between the trays below trayB_front_retain. The front face is instead scalloped down to 30 across each bay, leaving the dividers and both side walls at the plane to carry the lid. Pills crest at 22.8 at the front wall, so 30 keeps 7.2mm of freeboard and the reach over the wall is 7.2mm instead of 21.4mm down through the plane. The lid's 7mm hook becomes an 18.2mm skirt that hangs down the outside of the front face, closes the scallops with 6mm of overlap, and does the hook's old job of stopping the lid sliding down its own slope. | Confirmed | User instruction, this session |
| D18 | Decision | Ordinary | The dead wedge under the crossing chute becomes an accessory cubby, opening through the BACK face only so both side walls stay full. One void the full inner width, 70mm deep, 42mm tall at its shallow end and 103mm at the back, with its ceiling parallel to the chute floor so it self-supports rather than bridging. 1.1 L of the section that was solid infill is now usable space. A 42mm lip across the opening, left as the uncut bottom of the back wall, keeps the contents in when the module is slid about; 58mm of clear opening remains above it. The deck between cubby and chute is 3mm and is declared in attachments.json. | Confirmed | User instruction, this session |
| D19 | Decision | Ordinary | Label recesses sized for 1/2 inch Brother TZe tape (12.0 nominal + 0.6 clearance = 12.6 tall, 36 long, 0.5 deep), two per bay: the lower strip on the module's own front face below the lid skirt so it reads with the lid on, the upper strip on the wall between the trays, which faces forward over tray A. Neither is on a lid -- lids come off and go back the other way round. At 0.5 deep the tape, about 0.16 thick, sits fully below flush and cannot be caught by a sleeve. | Confirmed -- but not implemented until revision 6: revision 5 shipped 32 x 9 x 0.6 (INCIDENTS.md) | User instruction, this session |
| D20 | Decision | Critical | Porch 25 degrees, not 20, and tray A's rim 43, not 42. Pills reach tray A by flowing over the stagnant wedge on the porch, and that wedge's surface is at repose by construction, so the last 30mm never had the ramp's 10 degree margin. What the porch angle controls is the throat left over the wedge if the real repose exceeds the 30 degree estimate: at 20 degrees a 35 degree repose closed it to 25.8, under one pill length; at 25 it stays 28.9, and the wedge halves to 2.2 mL. Everything behind the porch rises 3.1mm; the rim comes up 1 to keep trayB_front_retain over pill_dia + 3. Capacity 290 / 182 mL per bay, still 1.97x / 1.24x the charge. | Confirmed | Review finding 6; this session |
| D21 | Decision | Ordinary | The cubby ceiling is its own 45 degree plane, anchored 3mm under the chute floor at the back face and thickening forward, instead of a 40 degree plane parallel to the chute. The old ceiling was a 50-degree-from-vertical overhang across 224mm with nothing between the side walls -- the same overhang the chute ceiling carries as an advisory, called "self-supporting" in D18. The shallow end drops from 41 to 33mm; the retaining lip comes down from 42 to 30 to match it, so the front of the cubby is a shelf you see into rather than a well. Supersedes the lip height in D18. | Confirmed | Review finding 5; face-normal scan, this session |
| D22 | Decision | Ordinary | Two finger notches in the pick lid's skirt, 22 x 8 with rounded tops, under bays 2 and 4. The lid must be lifted straight up (its back edge is 0.35 from the wall behind tray B and jams after 5 degrees of tilt), and a 229mm plate hung 0.35 off the front face gave nothing to lift by. The notch top runs 2mm above the scalloped wall and 9 above the pill line. | Confirmed | Review finding 7; this session |
| D23 | Decision | Critical | The fill lid's snap: tab drop 12 (was 10) so the barb pocket sits 2.7mm below the seat-ledge relief instead of 0.7; the barb's retaining face at 35 degrees instead of flat, so a deliberate pull releases it every refill rather than breaking the catch; and a 30 x 8 pull lip carried forward from the plate's front edge across a 34mm notch in the wall in front of the mouth, out over tray B's air, where a fingertip hooks under it. The notch stops at the seat plane, so nothing below the lid is opened. | Confirmed | Review finding 2; this session |
| D24 | Decision | Ordinary | Four 10 x 1mm recesses in the base for stick-on rubber feet, 15mm in from each corner. Under the back pair the base is the cubby floor and keeps 2mm. | Confirmed | This session |
| D25 | Decision | Ordinary | Both tray voids run 1mm PAST the pick plane, as the mouth void already ran past the rim. A void whose top lies exactly on the shell's top face is a coplanar boolean; it survived five revisions and failed the moment the opened groove cut through the same face. | Confirmed | INCIDENTS.md, revision 6 |
| D26 | Decision | Critical | The chute ceiling on the 40-degree leg is vaulted: a shallow gable across each bay, ridge 6mm above the plain ceiling at the bay centre, edges 6mm below it at the dividers (gable 29.2 degrees). A face sloping 40 degrees front-to-back and 29.2 degrees sideways is 44.8 degrees from vertical -- inside the conservative FDM limit -- where the plain ceiling was 50, the one ADVISORY the body carried since revision 3. The rise is split so neither side pays it all: the ridge goes up into the deck, so hopper B's ramp starts 6mm above tray B's floor (a riser at the tray's back wall, rounded by the existing internal fillet) and its outlet rises with it (outlet_h 30 -> 28 to keep 4mm under the rim); the edges come down, leaving 30mm clear at the dividers and 42 at the ridge. The porch is not vaulted -- the rib carries it. The ridge void starts 1mm inside each end of the added roof solid so no faces coincide. Cost: row B 182 -> 166 mL per bay, still 1.13x the 90-day charge. | Confirmed | User instruction, this session; face-normal scan and contains() probes |
| D27 | Decision | Ordinary | No external edge is left sharp. Body: the four vertical corners rounded at 3mm (a cutter overstepping outward, so no cut face lands on the body's own faces), the top edges of the silhouette rounded at 1.5 (an opening pass on OUTER's convex corners, with the base corners put back square for the first layers). Lids: plan-view corners rounded at 2, the fill lid's top perimeter chamfered 1mm (each convex outline hulled with its own inset, the lip kept 0.1 inside the plate's faces), the pick lid's plate and skirt edges chamfered in section (its top face goes on the bed, where a round is a 90-degree overhang) and at its x-ends. Internal flow corners already carry the 2mm fillet from revision 1. | Confirmed | User instruction, this session |

## Parts and dependency order

| Part | Depends on | Notes |
|---|---|---|
| body | - | The terraced two-tier body: 10 bays, both ramps, both pick trays, joining rails, label recesses, accessory cubby, foot-pad recesses, fill-lid seat. Print upright, no supports. |
| pick_lid | body | ONE lid over both tray rows. A flat plate lying on the body's pick plane (about 40 degrees), with a skirt down its front edge and two finger notches in the skirt. Lifts straight off. |
| fill_lid | body | ONE lid over both hopper mouths. Drops into the shared mouth onto seat lips, retained by two cantilever snap tabs with 35 degree return faces; a pull lip on its front edge is what you lift it by. |
