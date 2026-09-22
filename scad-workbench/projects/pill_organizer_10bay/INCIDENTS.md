# Incidents — pill_organizer_10bay

Real defects found and fixed during this design, in the entry format used by
`openscad-cad-skills/INCIDENTS.md`. Kept here because that log lives in the
installed skill clone, which is outside this repository and is recreated on
every fresh container; entries 1 and 4 are about the **tooling** and are worth
upstreaming.

### 2026-09-20 -- validate_scad.sh reported render=PASS while a part produced no STL at all
- **Where:** `validate_scad.sh --all` on this project, after adding an `assert()` to `parts/body.scad`.
- **Symptom:** the bundle printed `CHECK_RESULT render=PASS`, `connectivity=PASS` and `dimensions=PASS`, and only `bore_reachability` and `attachment` failed — with the confusing message "no input STL matched these declared bores' part". `build/body.stl` did not exist. The part had failed its own assert and never rendered; the checks that "passed" had simply skipped the missing file, and the two that failed did so for an unrelated-looking reason.
- **Root cause:** the per-part render loop does not fail the run when one part file errors, and the downstream checks treat an absent STL as nothing to check rather than as a failure.
- **Fix (in this project):** delete `build/*.stl` before every validation run, so a stale artifact can never stand in for a fresh one, and read the missing-STL message as a render failure rather than a declaration error.
- **Already promoted to a rule?** not yet — candidate: a render failure for any part under `parts/` must fail the bundle, and a check whose declared part has no STL must report FAIL, not silence. This is the same class as the 2026-09-12 entry "KLAIDINGAS PASS: dalis, kuri visai nesirenderino, gavo connectivity=PASS", which means it recurred on a different check after being logged once.

### 2026-09-20 -- the whole tier B hinge bar rendered as a detached second body
- **Where:** `parts/body.scad`, `hinge_bar_b` meeting the tier B tray rim.
- **Symptom:** `check_connectivity.py` reported 2 disconnected bodies; body 1 was the entire tier B hinge rod and its six webs, 8063 mm^3, floating free. Tier A's identical bar had welded.
- **Root cause:** the web's bottom face landed exactly on the tray rim plane and its back face exactly on the hopper wall — coincident faces on both, with no volumetric overlap. Whether the union welds them is then down to floating point, which is why one tier welded and the other did not.
- **Fix:** introduced `weld_embed = 1.5mm` and made every added feature — hinge webs, rail roots, rail buttresses — reach that far INTO the solid it lands on. Declared each as an intentional fusion in `fusions.json`.
- **Already promoted to a rule?** partly — the 2026-08-26 magnet-pocket entry records the same coincident-face class. Candidate generalisation: any feature added by `union()` must overlap its host volumetrically, never meet it on a plane.

### 2026-09-20 -- the back tier's hopper wall silently lost a step the front tier had
- **Where:** `parts/body.scad`, the `OUTER` silhouette polygon.
- **Symptom:** `motion_sweep.py` passed tier A through 105 degrees and failed tier B at 103.9. The two tiers are supposed to be the identical section, one `tier_lift` apart.
- **Root cause:** the silhouette was one hand-written polygon covering both tiers. A step added to the hopper's front wall to buy lid swing was written into the tier A portion only. The shared *cavity* profile is generated once and translated, so it got the step on both tiers — which made the back tier's wall thicker instead of stepped, and left its outer face where the lid hits it.
- **Fix:** `OUTER` is now built by `concat()` from a `tier_front(dy, dz)` function called once per tier, so the two faces cannot diverge. Added an assert that the tiers' rims stay exactly `tier_lift` apart.
- **Already promoted to a rule?** not yet — candidate: if a design declares two features identical by construction, generate both from one expression; a hand-written second copy is a divergence waiting to happen, and only a check that exercises *both* will find it.

### 2026-09-20 -- check_collisions reported 66.9mm of penetration on a pair whose real overlap is 0.000 mm^3
- **Where:** `check_collisions.py`, `body` vs `fill_lid` declared as `touching` with range [0.0, 0.0].
- **Symptom:** "DECLARED INTERFERENCE OUT OF RANGE ... measured penetration depth is 66.900 mm". An exact boolean intersection of the same two meshes measures 0.000 mm^3. 66.9 is within 0.3 mm of the lid's own depth.
- **Root cause:** FCL cannot define a penetration depth for two faces lying exactly on one another, which is what a lid resting flush on its seat is. The verdict takes the max over all contact points and gets the part's extent instead. This is the blind spot already logged on 2026-08-19 ("the declared-contact verdict has no spatial awareness"); this entry adds a concrete reproducible number for it.
- **Fix (in this project):** the lid is modelled 0.15 mm above its seat, which is honest — the barb has 0.3 mm of lift slop, so its resting height genuinely is not determined — and the pair reports as a NEAR MISS instead.
- **Already promoted to a rule?** not yet — candidate: a declared `touching` contact with a zero-width range should be verified by boolean volume, not by FCL penetration depth.

---

## Revision 2 — grouping both fill ports at the back and both trays at the front

### 2026-09-20 -- a non-watertight part reported as "UNINTENDED INTERFERENCE, penetration depth 90.170 mm"
- **Where:** `check_collisions.py` / `check_bore_reachability.py` on `pick_lid`.
- **Symptom:** the bundle reported `collisions=FAIL` with a 90mm penetration against the body, and `bore_reachability=FAIL`. Both were misleading. The real cause was one line further down, and only visible when the checker was run by hand: `DEGRADED: build/positioned/body.stl is not watertight -- collision results for it are unreliable`. An exact boolean of the same pair refused to run at all ("Not all meshes are volumes"). The lid's own union had produced an open mesh.
- **Root cause:** the hook's overlap polygon traced the plate's underside and top face *exactly*, so the union's coincident boundaries produced zero-area faces rather than a solid weld.
- **Fix:** the hook's top edge now runs 1mm above the plate's underside and well below its top face -- strictly inside the plate's section, so the overlap is volumetric on every side.
- **Already promoted to a rule?** not yet -- candidate: when a mesh is not watertight, the bundle's `CHECK_RESULT` line should say so instead of reporting a derived number from an unreliable computation. A 90mm penetration figure that is really "this mesh is broken" sends you looking at layout positions for a long time.

### 2026-09-20 -- two rotations whose signs had to agree, and did not
- **Where:** `parts/pick_lid.scad` + `layout.scad`, the lid's tilt onto the pick plane.
- **Symptom:** 18,080 mm^3 of the lid buried in the body. The lid had swung *down* into the trays instead of up the plane.
- **Root cause:** the lid was modelled flat and tilted by `layout.scad`, while its hook was pre-rotated inside the part file so it would come out vertical. Two rotations, opposite signs, one of them wrong.
- **Fix:** the lid is modelled directly in assembled orientation. There is now one rotation in the whole chain -- the print orientation -- and it lives in a comment, not in code.
- **Already promoted to a rule?** not yet -- candidate: prefer modelling a part in the orientation it is *used* in when its placement involves a rotation; pay the cost in the print-orientation note rather than in two rotations that must cancel.

### 2026-09-20 -- a buttress under a sloped surface, capped three different wrong ways
- **Where:** `parts/body.scad`, the buttress carrying the front joining groove, which sits under the sloped pick plane.
- **Symptom:** capped at the rail's centreline height, it stood ~5mm proud at its front edge and speared the pick lid (725 mm^3). Capped at the plane's value at its footprint's low end, it left a 0.3mm wedge of wall above it, and the socket cut through that wedge tore 3 boundary edges in the mesh -- genus 1, not watertight, every containment check unreliable.
- **Root cause:** trying to derive a scalar cap height for a feature whose ceiling is not flat.
- **Fix:** the buttresses are `intersection()`-ed with the outer silhouette. They then end exactly on whatever surface is above them, with no sliver and no height to get wrong.
- **Already promoted to a rule?** not yet -- candidate: a feature added under a non-planar surface should be intersected with that surface's own solid, never capped at a computed height.

### 2026-09-20 -- 7197 mm^2 of flat bridged ceiling, invisible to every gate
- **Where:** `parts/body.scad`, the crossing chute's ceiling where it runs under tray B.
- **Symptom:** none, from the validation bundle -- connectivity, dimensions, collisions, bores and attachment all passed. Found only by scanning face normals for near-horizontal downward faces: 7197 mm^2 at one Z, spanning 36mm of depth across every bay. It would have sagged into the chute.
- **Root cause:** the chute's ceiling followed tray B's flat underside instead of its own floor.
- **Fix:** the ceiling now runs parallel to the chute floor, holding a constant section at `ramp_deg`. Flat ceiling across the whole body fell to 1105 mm^2, none of it one large span, and the chute got a constant section as a side effect.
- **Already promoted to a rule?** not yet -- candidate: `check_printability.py` is documented as failing 4 of 4 real parts on overhang *area*, which is why it is advisory. But a scan for **near-horizontal downward faces above the bed, grouped by Z**, separates real bridged ceilings from the fillet facets that make the area metric useless -- three lines of trimesh, and it found a defect nothing else in the suite could see.

## Revisions 3-5 -- the 40 degree ramp, the porch, the scallop and the cubby

### 2026-09-20 -- a 2D section study cannot see a bridged ceiling, and this one hid a whole defect

The revision-3 profile was agreed from an annotated 2D section: 40 degree ramp,
20 degree porch under tray B, tray B's floor landing on tray A's rim. Every
number in that study was right. It still missed the defect that mattered.

Tray B's floor is carried on the bay dividers alone -- the chute passes
underneath, so the tray's own front and back walls never reach down to it. At
48 and at 40 degrees that floor's underside is the chute ceiling, sloped, and
it self-supports. At 20 degrees it is a near-flat ceiling bridging the full
43mm bay width. That is the same class of defect as the 7197 mm^2 found on this
project two revisions ago, and the suite still has no gate for it.

A section drawing is a slice through ONE plane. Bridging is about the span
PERPENDICULAR to that plane, which a section by construction cannot show. The
study was not wrong; it was answering a different question, and it was read as
though it answered this one.

Found by modelling the porch and re-running the face-normal scan (downward
faces grouped by overhang angle from vertical), not by any check in the
bundle. Fixed with a splitter rib down the middle of each porch, which halves
the bridge to 20.3mm and carries the slab directly. Confirmed by a bore
declaration that walks a lane end to end past the rib -- a sealed lane would
still be one watertight single body, so no other check would have noticed.

### 2026-09-20 -- print-ready exports dropped in build/ were silently adopted as the parts under test

The maquette and the print-oriented exports were written to `build/test_*.stl`
and `build/print_*.stl`. `validate_scad.sh --all` globs `build/` and matches STLs
to declared parts by name, so it picked those up as `body`, `pick_lid` and
`fill_lid` and ran every declaration against them. Two checks that had just
passed came back FAIL: the bores were "blocked" in `test_body.stl` because that
mesh is at 0.42 scale, and the rail grooves were "blocked" in `print_body.stl`
because that one has been translated to sit on z = 0.

Both failures were real reports about the wrong meshes. The declarations were
fine; the directory was not. Nothing warned that `build/` had grown two extra
copies of every part, and the failure text names the file, which is the only
reason it took one read rather than an afternoon.

Fixed by moving the exports to `build/print_ready/` and `build/maquette/`. Worth
upstreaming: the bundle should either ignore unexpected STLs in `build/` or say
out loud which files it adopted as which part before it starts checking them.

### 2026-09-20 -- a buttress clipped by the silhouette landed exactly on the shell's own top face

Dropping tray A's rim steepened the pick plane, and the body came back
`watertight = False` with **zero** boundary edges. Not a hole: two edges shared
by four faces each, at `y = 13.93, z = 53.17` -- which is the pick plane, at the
two X positions where rail 1's buttress meets it.

The buttress is deliberately INTERSECTED with the outer silhouette rather than
capped at a guessed height, because guessing produced a lid-spearing buttress
one way and a mesh-tearing sliver the other. But over tray A that silhouette IS
the pick plane, so the intersection lands the buttress top on the shell's own
top face. Two coplanar surfaces, no hole, no degenerate edge, and every gate
downstream refuses to run because the mesh is not watertight.

Fixed with `boss_clip_drop = 0.2`: the clip is taken against a silhouette whose
pick plane is dropped a hair, so the buttress ends strictly inside. Same shape
of fix as `seat_lip_drop`, and the third time on this project that two boolean
faces sharing one plane has cost a debugging session.

Worth saying plainly: "not watertight with zero boundary edges" is the signature
of a coplanar touch, not a gap. Counting unshared edges finds holes; it takes
counting edges shared by MORE than two faces to find this.

### 2026-09-20 -- params.scad is evaluated top to bottom, and a forward reference fails as the wrong assert

Three asserts fired in a row on values that were plainly correct:
`hop_lean_deg < 40` on a lean of 17.3 degrees, `trayA_front_h > pile + 5` on
30 against 22.8, `pick_lid_hook_h > 4` on 18.2. Each time the cause was the
same: the expression referenced a variable defined LOWER in the file, that
reference evaluated to `undef`, and the comparison came back false.

OpenSCAD's documented "last assignment wins" behaviour had me assuming top-level
variables were hoisted. In this build they are not, at least not across
`include`d scope in the way that matters here. The failure mode is nasty because
the assert that fires names a constraint that is not the problem -- it sends you
to re-check the geometry rather than the line number.

Fixed by ordering: `repose_deg` moved up beside the pill envelope it describes,
`trayA_pile_front` moved down beside `outletA_top` it derives from,
`pick_lid_gap` moved above the skirt derived from it, and the hopper-lean block
moved below the Z stations. Rule of thumb for this file: a derived value goes
immediately after the last thing it reads, never in the section it belongs to
thematically.

### 2026-09-20 -- a per-bay cut whose sides landed exactly on the bay dividers

Scalloping the front face down per bay produced 57 non-manifold edges. The
scallop spanned exactly `wall_x1(i) .. + bay_w`, which is exactly the divider
faces on either side, so the cut plane and an existing face plane coincided --
the third instance of this failure on this project, after `seat_lip_drop` and
`boss_clip_drop`.

Fixed with `scallop_over = 0.4`, the same overstep `seat_cut_over` already uses,
which takes a sliver off each divider's front tip above the scallop line and
nothing else. Three fixes, three names, one root cause: any cut whose boundary
is derived from the same expression as the face it lands on needs an explicit
overstep or drop. It is worth a lint rule.

## Revision 6 -- the independent review, and what it found

Revision 5 shipped with every gate green: 13 passed / 0 failed / 4 n/a / 1
advisory. A fresh session was asked to review it without trusting those
numbers. It reproduced them, then found the following by reading the
declarations against what they claimed to test and by probing the mesh with
`trimesh.contains()` along lines nothing in the suite walks.

### 2026-09-20 -- the front joining groove was a blind pocket, and the assert that guaranteed it was written on purpose
- **Where:** `params.scad` section 9, `rail1_soc_z1`; `bores.json` `rail_groove_front`.
- **Symptom:** none from the suite. `contains()` along x = 227.3 found solid from z = 48 up to the pick plane (52-60) over the groove's whole Y span. A dovetail is entered from above; this one had 4-11mm of wall over it. Two modules could never be ganged, which is the one thing the rails exist for.
- **Root cause:** revision 3 (D14) capped the groove at `pickplane(rail1_y - rail_boss_w/2)` -- the plane's LOWEST point across the buttress -- and added an assert that the groove must not run past the wall. Revision 2 had `rail1_soc_z1 = trayB_rim + 1.0; // groove OPEN at the body top`. The bore declared to prove the groove was "open ... out of the top of the side wall" ended at z = 47, inside the socket, so it proved only that the pocket existed.
- **Fix:** `rail1_soc_z1 = pickplane(rail1_y + rail_tip_w/2 + rail_clear) + 1.0` (out through the plane at the groove's own back edge, its highest point); the assert flipped to `>=`; the bore's end raised to z = 66, in open air above the plane. The male stays 4mm under its own wall's lowest point.
- **Already promoted to a rule?** not yet -- candidate: a bore declaration whose `_why` says "open to the outside" must END outside the part's surface, or it tests nothing about the exit. And: an assert written to keep a feature INSIDE a surface is exactly the wrong assert for a feature whose job is to break through one; state the physical requirement (enterable), not the geometric one (tidy).

### 2026-09-20 -- the fill lid's front snap latched on a 0.7mm sliver, and the assert protecting it measured a different cut
- **Where:** `parts/body.scad` `fill_seat_cut()`; `params.scad` section 8.
- **Symptom:** none from the suite; `attachments.json` probed the wall BEHIND the pocket (1.4mm, PASS). `contains()` at y = 63.1-63.5 found solid at z 133.4-133.9 only: the barb pocket's ceiling (133.3) and the seat-ledge relief for the same tab (from 134.0) were 0.7mm apart, over the 1.0mm the barb actually engaged.
- **Root cause:** the relief is cut `fill_ledge_w + 1` tall from `fill_seat_z - fill_ledge_w - 1`; the assert guarding the pocket used `fill_ledge_t` = 2.0, a variable the cut never reads. Same shape as the 2026-09-02 `nas_deck_v3` entry: the right assert on the wrong variable.
- **Fix:** `fill_tab_drop` 10 -> 12 (pocket 2mm lower), `fill_notch_over` named, `fill_catch_t` derived from the cut's own numbers and asserted >= 2.0 (it is 2.7); a second attachment point on the catch itself.
- **Already promoted to a rule?** R-15's second mode is meant for this and did not fire: `fill_ledge_t` and `fill_ledge_w` are not name-family siblings by its heuristic. Candidate: an assert whose formula uses a variable no part file reads is suspect on its own.

### 2026-09-20 -- D19's label recesses were documented, committed, and never written into params.scad
- **Where:** `params.scad` section 10 (revision 5); commit `b2de005`.
- **Symptom:** the commit message, plan D19, calculations.md and README all say 12.6 x 36 x 0.5 for 1/2 inch TZe tape, with `label_tape_w` and `label_clear`. The file had `label_w = 32, label_h = 9, label_z = 0.6` and neither variable. A 12mm tape does not fit a 9mm recess. The diff added only the centring and four asserts.
- **Also:** the upper cut started `label_z` in FRONT of the wall and ran `label_z + 1` deep -- the 1mm overstep on the wrong side -- so it went 1.0mm into a 2.4mm wall, leaving 1.4 where the docs said 1.9. The assert checked the parameter, not the cut.
- **Fix:** `label_tape_w`, `label_clear`, `label_h` derived, 36 x 12.6 x 0.5; both cuts start `label_cut_over` OUTSIDE the face and go `label_z` in; the assert now bounds the wall LEFT (>= 1.8). Moved to section 4c so nothing reads them from above.
- **Already promoted to a rule?** not yet -- candidate: a commit that names dimensions must diff `params.scad` for them; and a recess cut's overstep goes on the air side, which is worth a lint on any `translate([.., face - depth, ..]) cube([.., depth + over, ..])` shape.

### 2026-09-20 -- the cubby ceiling was called self-supporting; it was the same 50 degree overhang as the ADVISORY, five times wider
- **Where:** `params.scad` 4d, plan D18, calculations.md.
- **Symptom:** the face-normal scan (the one that found the 7197 mm^2 bridge in revision 2) put 29,972 mm^2 of downward face at exactly 50 degrees from vertical in the cubby, spanning x 4.5-225.5 with nothing between the side walls. The chute ceiling carried as ADVISORY is 30,889 mm^2 at the same angle, anchored every 43mm.
- **Root cause:** "parallel to the chute floor so it self-supports rather than bridging" conflated not-bridging with self-supporting. A 40 degree slope IS a 50 degree overhang whichever way it is described.
- **Fix:** the ceiling is its own plane at `cubby_ceil_deg = 45`, anchored 3mm under the chute floor at the back face and thickening forward (14 at the cubby's front). Cost: the shallow end drops from 41 to 33; the lip comes down to 30 to match, so the front is a shelf, not a well.
- **Already promoted to a rule?** not yet -- candidate: any claim of "self-supports" in a decision must cite the overhang angle from vertical, and the scan by angle band is cheap enough to run on every revision.

### 2026-09-20 -- the "forward reference" rule in this file was half right: it is assignments that are order-sensitive, not asserts
- **Where:** the revision 3-5 entry "params.scad is evaluated top to bottom"; section 7's skirt assert, which read `label_h` from section 10.
- **Symptom:** the review flagged that assert as the same defect class and expected it to fire. It does not, and the real render emits no warning for it.
- **Root cause:** verified with a minimal file: `assert(b > 1); c = b > 1; b = 5;` -- the assert passes and `c` is `undef` with "Ignoring unknown variable". A top-level `assert()` is a statement, and statements run after every assignment has been evaluated; an assignment that reads a later assignment gets `undef`. The three asserts that fired in the original incident did so because the VALUES they compared were forward-referencing assignments.
- **Fix:** rule restated. Only an assignment must follow what it reads; an assert may sit anywhere. The label block was moved anyway, for legibility.
- **Already promoted to a rule?** this entry is the correction.

### 2026-09-20 -- the "print-ready" pick lid stood on its skirt edge with the plate 14mm in the air
- **Where:** `test_model.scad` `print_pick_lid()`, `build/print_ready/pick_lid.stl`.
- **Symptom:** `rotate([-pick_lid_slope, 0, 0])` does lay the plate flat -- with the skirt pointing DOWN. Dropped to z = 0, the exported lid rested on the skirt's bottom edge and the 229 x 64mm plate hung 14mm above the bed. Revision 5's bbox for it, `[229, 94.12, 16.98]`, was consistent with exactly that. No gate looks at `build/print_ready/`.
- **Root cause:** one rotation, wrong sign -- the class the revision 2 entry "two rotations whose signs had to agree" warned about, on a single rotation.
- **Fix:** `print_export.scad`: `rotate([180 - pick_lid_slope, 0, 0])` puts the plate's top face on the bed and the skirt up at 40 degrees from vertical; the drop to z = 0 is analytic from params. Verified by scanning the exported mesh: 0 mm^2 of downward face past 45 degrees off the bed, worst 39.9.
- **Already promoted to a rule?** not yet -- candidate: a print-orientation export gets the same face-normal scan as the modelled part, since the orientation is the whole point of the file.

### 2026-09-20 -- opening the groove through the pick plane left a zero-area face pair on the plane
- **Where:** `parts/body.scad`, VOID_A / VOID_B top edges.
- **Symptom:** body not watertight, 0 boundary edges, 2 edges shared by 4 faces, one extra "body" of 2 faces and zero volume lying ON the pick plane between the groove's inner face (x = 224.6) and the side wall (x = 227.2).
- **Root cause:** both tray voids' top edges were defined on exactly the plane OUTER's top face lies on -- a coplanar difference that had held through five revisions until a third cut (the groove) broke through the same face. MOUTH already ran `hopper_rim + 1` for the same reason.
- **Fix:** `void_top_over = 1.0`; both tray voids now run past the plane. Fourth instance of the coplanar class on this project, and the first where the coincidence was pre-existing and only became live when a new cut touched it.
- **Already promoted to a rule?** the candidate from `scallop_over` stands, with one addition: an open-topped void must run PAST the surface it opens through, not TO it, even when the render happens to come out clean.

### 2026-09-20 -- the maquette exported at full size because an included file's default overwrote the wrapper's value
- **Where:** `test_model.scad` including `print_export.scad`.
- **Symptom:** `SCALE = TEST_SCALE;` in the wrapper, `SCALE = is_undef(SCALE) ? 1.0 : SCALE;` in the include; OpenSCAD warned "assigned ... but was overwritten" and the maquette came out 230mm wide.
- **Root cause:** OpenSCAD evaluates a re-assigned top-level variable at its FIRST position with its LAST expression; at that point `SCALE` was undefined, so the default won.
- **Fix:** the wrapper sets `TEST_SCALE` only, and the include reads it as a fallback.
- **Already promoted to a rule?** not yet -- same family as the revision 3-5 hoisting entry: never assign the same top-level name in both an includer and its include.

## Revision 7 -- the vault and the edges

### 2026-09-20 -- reaching a snap tab 1mm up into its plate put the tab's outer face on the plate's edge face
- **Where:** `parts/fill_lid.scad`, the back tab.
- **Symptom:** fill lid not watertight, 3 edges shared by 4-6 faces, all on the line x 103.9-119.9, y = 103.8 (the plate's back edge), z 0-1.
- **Root cause:** revision 6 extended each tab 1mm up into the plate for a volumetric weld (the tab had ended exactly on the plate's underside). The tab is flush with the plate's edge, so that 1mm put the tab's outer face ON the plate's back face. The front tab survived only because the pull lip covers it.
- **Fix:** `fill_tab_inset = 0.2`: each tab's outer face sits 0.2mm inside the plate's edge. The barb still projects `fill_tab_barb` past the edge, so the engagement is unchanged.
- **Already promoted to a rule?** the coplanar candidate from `scallop_over` again, in its union form: a feature that overlaps its host must not be flush with any face of the host in the overlap.

### 2026-09-20 -- a Minkowski chamfer left zero-area slivers at a concave corner, and the hull that replaced it floated the lip off the bed
- **Where:** `parts/fill_lid.scad`, `fill_plate()`, the top chamfer (D27).
- **Symptom:** first, 4 edges shared by 4-6 faces and four zero-volume "bodies", all within 0.1mm of (97.9, 0, 3.0) -- the concave corner where the pull lip meets the plate, on the chamfer's top plane. Then, with the lip built as its own hulled piece 0.1mm inside the plate's faces, the print-orientation scan showed 267 mm^2 of 90 degree overhang: the lip's top face, 0.1mm above the bed.
- **Root cause:** `minkowski()` of a non-convex outline with a cone sweeps the near-apex ring through the concave corner and emits degenerate faces there; `hull()` cannot take the whole outline because it is not convex. Keeping the lip 0.1 inside the plate on BOTH faces avoided coplanar faces but moved the face that goes on the bed.
- **Fix:** plate and lip are each a convex rounded rectangle hulled with its own inset. The lip's top is flush with the plate's; its solid ends at `lip_back` = 0.95, inside the plate's 1mm chamfer band, where the plate's top is already below lid_t, so the two top faces lie on one plane without overlapping. Its underside sits 0.1 above the plate's. Its own chamfer runs along its front and sides only.
- **Already promoted to a rule?** not yet -- candidate: chamfer a non-convex outline as a union of convex pieces hulled separately; and a face that goes on the bed is never the one to offset.

### 2026-09-20 -- the vault roof and a rail root both reached weld_embed into the same 2.8mm side wall
- **Where:** `parts/body.scad`, `vault_roof()` at bay 1's left edge and bay 5's right edge, `check_subfeature_overlap.py`.
- **Symptom:** UNINTENDED SUB-FEATURE OVERLAP body__rail_male.stl <-> body__vault_roof.stl, 20.69 mm^3.
- **Root cause:** the roof halves reached `weld_embed` = 1.5 into whatever wall bounds their bay; the rail roots reach 1.5 into the side walls from outside. 1.5 + 1.5 in a 2.8 wall.
- **Fix:** `vault_embed` = 1.0 for the roof, with an assert that the two embeds leave 0.2 of wall between them.
- **Already promoted to a rule?** not yet -- candidate: any two features welding into the same wall from opposite sides need an assert on the sum of their embeds against the wall.

### 2026-09-20 -- rounding a 3mm plate with a 1.5mm opening pass erased the pick lid, but only when the assembly asked for it
- **Where:** `parts/pick_lid.scad`, `pick_plate()` / `pick_hook()`, first attempt at D27.
- **Symptom:** the part file rendered, passed its bbox and was watertight. `assembly.scad -D MODE="part" -D PART="pick_lid"` produced "Current top level object is empty" with no warning, `build/positioned/pick_lid.stl` was left over from revision 6, and the collision check passed against that stale file. The six-view renders of the open assembly simply had no pick lid in them, which is how it was noticed.
- **Root cause:** `offset(r = 1.5) offset(r = -1.5)` on a section whose perpendicular thickness is exactly 3.0 erodes it to a zero-width line. Standalone, floating point left a sliver the dilation grew back; through `use<>` it was exactly empty. The skirt (2.65 wide) was in the same state.
- **Fix:** `lid_round = 1.0` with an assert against half the plate and skirt thickness.
- **Already promoted to a rule?** not yet -- two candidates. An opening-pass radius must be asserted under half the thinnest section it runs through. And the positioned render must FAIL the bundle when it is empty, and a stale `build/positioned/*.stl` must never be adopted: this is the 2026-09-20 "render=PASS while a part produced no STL" entry again, one directory over.

## Revision 7, the review -- what a green suite plus a dismissed advisory hid

### 2026-09-22 -- the vault lifted hopper B's ramp end above the hopper divider's spring point, and the divider went to 0.2mm at its foot in every bay
- **Where:** `params.scad` `hopwall_z0`; `parts/body.scad` VOID_A and VOID_B.
- **Symptom:** none from the 13 gates. `contains()` along y at x = 104: wall 0.52 at z = 123, 0.22 at 124, 0.58 at 126, 1.40 at 130, 2.4 only from 135. Identical in bays 1 and 5. `check_printability.py` HAD said `THIN WALL: minimum measured thickness 0.002 mm < required 0.80 mm (52/1500 samples)` -- inside the ADVISORY whose overhang half fails every real part, so nobody read its other half.
- **Root cause:** D26 moved the ramp's end to 122.9; the divider's lean still sprang from the chute ceiling at 115.9. VOID_B draws the leaning face from the ramp's end; VOID_A draws it from the spring point 7mm lower. Two faces of the same wall, drawn from two different origins, crossed. D16's invariant ("pivots where it springs off the chute ceiling, so hopper B's ramp below it is untouched") was never asserted.
- **Fix:** `hopwall_z0 = max(chuteA_ceil(yA_hop0), rampB(yB_hop1))`, a vertex at that height in VOID_A so the wall is vertical up to it, and an assert on the WALL THICKNESS at the ramp's end (`hopwall_A(rampB(yB_hop1)) - yB_hop1 >= wall_div`). Lean 26.0, mouths 62.7 / 39.3. Found by the review's contains() sweep; confirmed 2.4mm at every probed height after the fix.
- **Already promoted to a rule?** two candidates. When one wall's two faces are drawn from two different features (here a ramp end and a lean pivot), assert the wall's thickness at the feature that can move. And an ADVISORY with two halves must be read in full: the overhang half being noise does not make the thin-wall half noise.

### 2026-09-22 -- the male rails' undersides were flat faces 10mm above the bed
- **Where:** `parts/body.scad` `rail_male_one`, `rail_z0` = 10.
- **Symptom:** face-normal scan of the print-oriented body, 85-95 band: 90 mm^2 at z = 10.0, x -3.3..-1.7, y 15-100 -- the two trapezoids' undersides, in mid-air. A drooped rail bottom is the first thing to enter the neighbour's groove.
- **Fix:** the male is a hull of its full section from `rail_lead_bot` up with a sliver at the wall face at `rail_z0`, so its underside is a 45 degree chamfer. Probe: first solid at x = -0.5 / -2.5 / -4.5 is z 10.6 / 12.6 / 14.6.

### 2026-09-22 -- the barb's return face was 25.7 degrees, not the 35 D23 states, and the assert checked the parameter
- **Where:** `parts/fill_lid.scad` BARB.
- **Symptom:** print-orientation scan: two faces at 64.3 from vertical (= 90 - 25.7), 23 mm^2 each. The polygon put the root at the barb-top height 0.5 inside the tab and spread the 1.1 * tan(35) drop over a 1.6 run.
- **Fix:** the return face is the line through (tab outer face, barb top) at `fill_tab_return_deg`; the root is that line continued `fill_tab_root` into the tab. `barb_face_deg` is derived from the polygon and asserted equal to the parameter; the print scan now reads 55 from vertical (= 90 - 35). Same class as the `fill_ledge_t` assert of revision 5: right assert, wrong variable.

### 2026-09-22 -- the fillet pass put shoulders back under the pick plane
- **Where:** `parts/body.scad` VOID_A / VOID_B top edges, `void_top_over` = 1.
- **Symptom:** print scan: 160 mm^2 at 62-73 degrees at y 29.3-29.8, z 67; 210 mm^2 at 56-79 at y 60.1-60.8, z 93 -- 1-2mm downward shelves in both trays, misattributed in calculations.md to the seat ledge.
- **Root cause:** the voids' top corners are 50 degree corners (the plane meets a vertical wall); an opening pass with r = 2 rounds them over a 2 / tan(25) = 4.3mm tangent, so with the corner only 1mm above the plane the round put solid back below it.
- **Fix:** `void_top_over` = 5. Rule: an opening pass's tangent length on the sharpest corner it touches, not its radius, is what an overstep must exceed.

### 2026-09-22 -- smaller items from the same review, all fixed
- `pick_notches()` started its polygon 2mm below the skirt with r = 4 rounding, leaving 0.5mm feathers at the skirt edge; it starts 6 below now (`pick_notch_under`).
- `bores.json` `rail_groove_back` ended at z = 140, inside the groove (142); it ends at 144 now. The front groove's bore had been fixed for exactly this in revision 6; the back one was missed.
- The back seat-ledge relief ended exactly on the back wall's inner face (the front one oversteps by `fill_notch_over`); it oversteps now.
- Stale numbers in params.scad comments, the pick lid header's wrong-sign print rotation, joints.json's "38mm apart", the porch angle in a bore's `_why`, and D26's "rounded riser" (the fillet is at its foot; the top edge is a sharp convex edge).
