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

## Revision 3 -- the 40 degree ramp and the porch under tray B

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
