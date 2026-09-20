# Review handoff — pill_organizer_10bay, revision 6

For a fresh session asked to review this design critically. It is written to be
pasted as that session's opening prompt, or read from the repo.

## Your task

Independently review `scad-workbench/projects/pill_organizer_10bay` at
revision 6 and report what is wrong with it. Do not rubber-stamp it. The suite
it ships with reports 13 passed / 0 failed / 4 n/a / 0 inconclusive / 1
advisory, and that is exactly the condition under which a review is worth
doing: every automated gate is already green, so anything still wrong is
something no gate looks at.

Revision 5 shipped with the same green suite. A review of it found four
defects the suite could not see — a joining groove capped by the wall it was
cut in, a snap catch 0.7 mm thick, label recesses 9 mm tall for a 12 mm tape,
and a cubby ceiling past the overhang limit that a decision called
self-supporting — plus a print-ready export standing on its skirt. They are the
last eight entries in `INCIDENTS.md`, each with the probe that found it.
Assume revision 6 has its own.

## Bootstrap

```sh
source ~/.local/opt/openscad/env.sh        # or run scad-workbench/install.sh first
cd scad-workbench && ./verify.sh           # must report 6 passed / 0 failed
cd projects/pill_organizer_10bay
```

Load the `scad-modeler` skill and the `openscad-cad` skill together. Read this
project's `INCIDENTS.md` first — it is the highest-value file here. Then re-run
both gates yourself rather than trusting the numbers above:

```sh
~/.local/src/openscad-cad-skills/scad-modeler/scripts/validate_scad.sh --all
python3 ~/.local/src/openscad-cad-skills/scad-modeler/scripts/check_rules.py --project-dir .
```

## What to read, in order

| File | What it holds |
|---|---|
| `INCIDENTS.md` | Twenty real defects across six revisions, each with the tell that found it |
| `plan.md` | The revision table (1–6) and decisions D1–D25, with criticality and provenance |
| `calculations.md` | Every derived number, the PATIKRINTI assumptions, and the decisions/assumptions log |
| `README.md` | What it is, how it works, and the reviewer's-attention list |
| `params.scad` | Single source of dimensions. Every constraint is an assert() here |
| `parts/*.scad` | body, pick_lid, fill_lid. Each carries EXPECTED_BBOX and SUBFEATURES |
| `print_export.scad` | The print orientations and the drop to z = 0; `build/print_ready/` and `build/maquette/` come from it |
| `joints.json`, `bores.json`, `attachments.json`, `fusions.json` | The declarations the suite checks against |
| `build/prev_asm/contact.png`, `build/prev_open/contact.png`, `build/prev_body/contact.png` | Six views each of the assembly, the assembly with both lids lifted, and the body alone |

## Known soft spots — start here, then look for what is not on this list

1. **The angle of repose is an estimate.** `repose_deg = 30`, marked
   PATIKRINTI. The ramp has 10 degrees of margin over it; the porch does not
   and cannot — pills reach tray A by flowing over the stagnant wedge, whose
   surface is at repose by construction. What the porch angle sets is the
   throat over that wedge: 32.6 mm at 30 degrees, 28.9 at 35, one pill length
   at about 38. Revision 6 moved the porch from 20 to 25 for that reason
   (D20). Is a straight repose line from the chute mouth the right model for
   the pile in tray A, and is 30 defensible for gelatin capsules on PLA?
2. **The porch lanes are 20.28 mm.** Pills must run single file through a
   30 mm stretch. The splitter rib's knife-edged upstream taper is the only
   thing stopping a capsule that arrives crosswise from stopping dead at it.
   Nothing verifies this.
3. **The chute ceiling on the 40-degree leg is a 50-degree-from-vertical
   overhang**, 30,900 mm² of it in 43 mm bays. This is the single ADVISORY and
   the one print risk left in the body. `chute_clear` carries a sag allowance;
   the stated fallback is a gabled ceiling. The cubby ceiling, which was the
   same overhang across 224 mm, is at 45 now (D21) — check that the deck it
   leaves (3 mm at the back face, 14 at the front) is right, and that the
   `cubby_deck` attachment point is still in the deck.
4. **The fill lid's snap is new geometry** (D23): 12 mm tabs, a 35-degree barb
   return, 0.8 mm of real engagement, a 2.7 mm catch, and a pull lip. The
   release force under a fingertip on the lip against two tabs is not
   calculated, only bounded by the strain assert. Print the coupon.
5. **The pick lid's finger notches** (D22) open a 22 x 2 mm sliver of tray
   above the scalloped wall. The pill line is 9 mm below the notch top. Judge
   whether that is enough with the lid being lifted while the tray is heaped.
6. **The front joining groove now opens through the pick plane** under the
   lid's right edge (D14, corrected). The male on a neighbour has to drop 132
   mm to seat both rails. Nothing verifies the assembly motion; there is no
   motion sweep in this revision.
7. **The cubby deck is 3 mm at the back face** over a 224 mm span. Hand
   calculated deflection is under a millimetre at pill loads. Nobody has
   checked print-time behaviour or PLA creep under sustained load.
8. **Bay width is 1.65x the longest pill** against a 2–3x arching rule of
   thumb. Two capsules can in principle span a bay. Mitigated, not eliminated.
9. **Capacity is a geometric maximum**, measured from the cavity meshes with
   the fill line at the underside of the lid. It is not a practical fill.
10. **Tier 2 throughout.** `doctor.py` reports no calibration profile, so every
    clearance — rail 0.35, fill lid 0.30, snap 0.8 — is geometry only.
11. **The label recesses are 0.5 mm deep** in walls 2.4 and 2.8 mm thick, and
    the upper strip sits on the wall between the trays, which is also the wall
    doing the `trayB_front_retain` job. The retained wall was measured on the
    mesh at 1.9; `trayB_front_retain` itself is 14.6 against a 14.0 floor.
12. **Coverage gaps are not passes.** Four checks are not-applicable and
    `check_rules.py` reports three antecedents that never fired (R-01, R-09,
    R-12). Seven rules are MANUAL. Nothing moves in this revision, so there is
    no motion sweep at all.

## Failure modes this project keeps producing

- **Two boolean faces sharing one plane.** Five incidents now
  (`seat_lip_drop`, `boss_clip_drop`, `scallop_over`, `void_top_over`, and the
  hinge bar of revision 1). The tell is "not watertight with zero boundary
  edges": count edges shared by MORE than two faces, and split the mesh —
  the stray body is the zero-volume face pair. Check whether any remaining cut
  boundary is derived from the same expression as the face it lands on.
- **An assert on the wrong variable, or written to enforce the defect.** The
  0.7 mm catch had an assert on `fill_ledge_t` while the cut used
  `fill_ledge_w + 1`; the blind groove had an assert that it must NOT break
  out of the wall. Read every assert against the cut it claims to guard.
- **A declaration that does not test its own `_why`.** The groove bore said
  "open out of the top of the wall" and ended inside the socket. For every
  bore, check that its end point is where the claim needs it to be.
- **Documented, never written.** D19's sizes existed in four documents and
  not in `params.scad`. For every number in `plan.md`'s newest decisions
  (D20–D25), find it in `params.scad`.
- **Assignments are order-sensitive; asserts are not.** A top-level
  assignment that reads a variable defined below it gets `undef`; a top-level
  `assert()` runs after every assignment and sees final values. Check that no
  derived value reads something defined below it.
- **A rotation with the wrong sign.** Revision 2 had two; revision 5's print
  export had one. Scan every exported print orientation by face normal, not
  by eye.

## What a useful report looks like

State findings as: what is wrong, how you established it (a command and its
output, not an assertion), and what it would take to fix. Rank by whether it
stops the part working, stops it printing, or is cosmetic. If you think a
decision in `plan.md` is wrong rather than merely unverified, say so and say
which decision ID.

If you find nothing, say what you looked at and what would have had to be true
for you to find something — a review that concludes "looks good" without that
is indistinguishable from one nobody ran.
