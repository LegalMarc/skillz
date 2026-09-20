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
