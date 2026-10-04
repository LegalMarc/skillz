# Resume note — revision 11 (read this first)

**Where it stands:** revision 11 (test print 3's results, D41-D47) is implemented on
branch `pill-organizer-rev11`, created from `pill-organizer-rev10` at `0b1af30`; not
pushed, no PR. Test print 3 (the revision 10 section, Generic PETG) passed on the
lid, the lug and the row A feed; the changes are beads in tray A's corner (D41),
hopper A's flare (D42), the slim rail and buttress (D43), no finger notches (D44),
stacked front labels (D45), a section cut at a full divider that now runs the whole
end bay (D46) and `rail_clear` 0.215 with a finer PETG coupon (D47). No independent
review of revision 11 has happened yet.

**Proven:** `validate_scad.sh --all` (14 passed, 0 failed, 3 n/a, 1 advisory),
`check_rules.py`, and the probes in `probes/`: `lid_retention.py` (a)-(h),
`corner_thickness.py` (edge-angle scan of the break-out zone, skin and buttress
thickness, the divider / front wall joint), `capacity.py`, `overhang_scan.py`,
`capsule_corner.py` (the rib beads, last-bay pockets), `skin_free_height.py` (the rail skin's
free height). **Not proven:** that the three small ribs per bay are enough (they hold a capsule
lying along the fall line 4.1 mm out from the wall and push its end up; a filled wedge is the
stronger fix), that hopper A fills easily by hand, the rail fit at 0.215
(a PETG reading), and anything about the new section's strength.

**Next step:** an adversarial review of revision 11, then print
`build/section/test_print_section_256.3mf` (test print 4, about 8 h in PETG, no
brim) and record it in `TEST_PRINTS.md`; dry the PETG first (heavy stringing on
test print 3). The notes below this one are from revisions 10 and 9.

---

# Resume note — revision 10 (read this first)

**Where it stands:** revision 10 (test print 2's fixes D36-D40, the review
fixes F1-F8, G1-G7 and H1-H2) is implemented on branch
`pill-organizer-rev10`, not pushed, no PR. An independent deep-tier review
approved it at `e04b514` (COVERAGE 14 passed, 0 failed, 3 n/a, 1 advisory;
all probes pass). Two low items are left as watch rows in `TEST_PRINTS.md`
(test print 3) rather than changed. Next step: slice and print
`build/section/test_print_section_256.3mf` (test print 3, about 8 h, no brim,
no supports), then record the results in `TEST_PRINTS.md`. The review below
this note was written for revision 9 and is kept for its method.

**Proven (commands in `README.md` "Build and verify"):** the suite
(`validate_scad.sh --all`, `check_rules.py`), and four probes in `probes/` run
with `source ~/.local/opt/openscad/env.sh; python3 probes/<name>.py`:
`lid_retention.py` (retention, lift, reversal), `corner_thickness.py` (groove
skin and buttress), `capacity.py` (per-bay mL), `overhang_scan.py` (print
faces).

**Not proven:** that tilted tray A (35 degrees) feeds real capsules; that the
lugs hold on a printed lid; the rail fit at 0.20. Test print 3, see
`TEST_PRINTS.md`, is built to answer those.

**Next step:** an adversarial review of revision 10 (start with D36's height
chain: tray A rim 77 vs plane under 45 degrees vs wall retention), then print
`build/section/test_print_section_256.3mf` (no brim, 7-8 h).

---

# Review handoff — pill_organizer_10bay, revision 9

For a fresh session asked to review this design critically. It is written to be
pasted as that session's opening prompt, or read from the repo.

## Your task

Independently review `scad-workbench/projects/pill_organizer_10bay` at
revision 9 and report what is wrong with it. Revision 8 was the first one
informed by a physical print, and revision 9 fixes what the review of
revision 8 found (D33-D35): read `TEST_PRINTS.md` before anything else. Do not rubber-stamp it. The suite
it ships with reports 13 passed / 0 failed / 4 n/a / 0 inconclusive / 1
advisory, and that is exactly the condition under which a review is worth
doing: every automated gate is already green, so anything still wrong is
something no gate looks at.

Revision 5 shipped with the same green suite; a review found five defects
the suite could not see. Revision 7 shipped with the same green suite; a
review found the vault had thinned the hopper divider to 0.2 mm at its foot
in every bay — and the suite HAD seen it, in the thin-wall half of the one
ADVISORY everyone had learned to ignore for its overhang half. Revision 8 shipped green too; its review found tray B's pile standing 3.25 mm above the wall meant to retain it, because the one check on that wall measured from the floor. Read the
advisory's full text. The entries are the last fourteen in `INCIDENTS.md`,
each with the probe that found it. Assume this revision has its own.

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
| `INCIDENTS.md` | Twenty-two real defects across seven revisions, each with the tell that found it |
| `plan.md` | The revision table (1–7) and decisions D1–D27, with criticality and provenance |
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
2. **The porch ceiling is now a flat 43 x 28 mm bridge in every bay** (D29),
   with no rib. Check the pocket it leaves behind the mouth into tray A, the
   join with the 40-degree leg at tray B's back wall, and the 45-degree outlet
   corner chamfers, which are separate prisms unioned onto the shell.
3. **The hopper divider (D28)** now springs from the end of hopper B's ramp
   (122.9) and leans 26 degrees. Probe it along y at x = 104 for z 123–140:
   it must read 2.4 mm everywhere below the seat ledge. The assert guards the
   thickness at the ramp's end only.
4. **The vault (D26) is new geometry with four numbers to distrust.** The
   face is 44.8 degrees from vertical, 0.2 inside the rule. The chute is 30 mm
   clear at the dividers, 1.15x a pill. Hopper B's ramp foot is a 6 mm riser
   above tray B's floor. The deck between the ridge and hopper B's floor is
   3 mm at the ridge (`vault_deck` in `attachments.json`). The roof solid is
   built from two mirrored halves per bay, each overlapping its partner by
   1 mm at the centre and the ridge void by 1 mm at each end — the coplanar
   class waits at every one of those joins. Split the mesh and count edges
   shared by more than two faces before believing the suite.
   The cubby ceiling is at 45 (D21); check the deck it leaves (3 mm at the
   back face, 14 at the front) and that `cubby_deck` is still in the deck.
5. **The fill lid has no snap** (D30): it nests by gravity on 2.1 mm of
   ledge. The pick lid now has two locating lugs (D32) built in the plate's
   own rotated frame; check their position against the side walls and that
   nothing else in tray B's end bays meets them.
6. **The pick lid's finger notches** (D22) open a 22 x 2 mm sliver of tray
   above the scalloped wall. The pill line is 9 mm below the notch top. Judge
   whether that is enough with the lid being lifted while the tray is heaped.
7. **The front joining groove now opens through the pick plane** under the
   lid's right edge (D14, corrected). The male on a neighbour has to drop 132
   mm to seat both rails. Nothing verifies the assembly motion; there is no
   motion sweep in this revision.
8. **The cubby deck is 3 mm at the back face** over a 224 mm span. Hand
   calculated deflection is under a millimetre at pill loads. Nobody has
   checked print-time behaviour or PLA creep under sustained load.
9. **Bay width is 1.65x the longest pill** against a 2–3x arching rule of
   thumb. Two capsules can in principle span a bay. Mitigated, not eliminated.
10. **Capacity is a geometric maximum**, measured from the cavity meshes with
   the fill line at the underside of the lid. It is not a practical fill.
11. **Tier 2 throughout.** `doctor.py` reports no calibration profile, so every
    clearance is geometry only, except rail 0.50 and fill lid 0.30, which
    test print 1 measured.
12. **The label recesses are 0.5 mm deep** in walls 2.4 and 2.8 mm thick, and
    the upper strip sits on the wall between the trays, which is also the wall
    doing the `trayB_front_retain` job. The retained wall was measured on the
    mesh at 1.9; `trayB_front_retain` itself is 14.6 against a 14.0 floor.
13. **Every external edge is rounded or chamfered (D27)** with small cutters
    and 2D opening passes. Each is a boolean against an existing face: the
    corner cutters overstep outward, the fill lid's lip ends inside the
    plate's chamfer band and sits 0.1 above its underside, the pick lid's
    chamfer cutters are centred on the edge lines. Check that the rounds are
    where the decision says and nowhere else — a 1.5 round on a 2.4 wall top
    leaves 0.9 of flat.
14. **Coverage gaps are not passes.** Four checks are not-applicable and
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
