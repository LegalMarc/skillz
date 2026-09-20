# Review handoff — pill_organizer_10bay, revision 5

For a fresh session asked to review this design critically. It is written to be
pasted as that session's opening prompt, or read from the repo.

---

## Your task

Independently review `scad-workbench/projects/pill_organizer_10bay` at revision
5 and report what is wrong with it. **Do not rubber-stamp it.** The suite it
ships with reports 13 passed / 0 failed / 4 n/a / 0 inconclusive / 1 advisory,
and that is exactly the condition under which a review is worth doing: every
automated gate is already green, so anything still wrong is something no gate
looks at.

Three defects on this project passed every gate before a human or a hand-written
scan caught them. They are in `INCIDENTS.md`. Assume there is a fourth.

## Bootstrap

```sh
source ~/.local/opt/openscad/env.sh        # or run scad-workbench/install.sh first
cd scad-workbench && ./verify.sh           # must report 6 passed / 0 failed
cd projects/pill_organizer_10bay
```

Load the **`scad-modeler`** skill and the **`openscad-cad`** skill together.
`scad-modeler`'s own instruction is to read `../INCIDENTS.md` before touching
geometry — this project keeps its own `INCIDENTS.md` in the project directory,
and it is the highest-value file here. Read it first.

Then re-run both gates yourself rather than trusting the numbers above:

```sh
~/.local/src/openscad-cad-skills/scad-modeler/scripts/validate_scad.sh --all
python3 ~/.local/src/openscad-cad-skills/scad-modeler/scripts/check_rules.py --project-dir .
```

## What to read, in order

| File | What it holds |
|---|---|
| `INCIDENTS.md` | Twelve real defects across three revisions, each with the tell that found it |
| `plan.md` | The revision table (1–5) and decisions **D1–D19**, with criticality and provenance |
| `calculations.md` | Every derived number, the `PATIKRINTI` assumptions, and the decisions/assumptions log |
| `README.md` | What it is, how it works, and the reviewer's-attention list |
| `params.scad` | Single source of dimensions. Every constraint is an `assert()` here |
| `parts/*.scad` | `body`, `pick_lid`, `fill_lid`. Each carries `EXPECTED_BBOX` and `SUBFEATURES` |
| `joints.json`, `bores.json`, `attachments.json`, `fusions.json` | The declarations the suite checks against |
| `build/section_lane.png`, `build/view_pair.png` | Current section and the two three-quarter views |

## Known soft spots — start here, then look for what is not on this list

1. **The angle of repose is an estimate.** `repose_deg = 30`, marked
   `PATIKRINTI`. Revision 3 onward deliberately spends margin against it: the ramp went
   48 → 40 degrees (18 → 10 degrees of margin) and the porch under tray B runs at
   **20 degrees, which is below repose on purpose**. Every capacity number and
   the whole "dead wedge" argument rests on that figure. If the real requirement
   is nearer Jenike mass flow — walls 55–60 degrees from horizontal — the
   architecture does not merely lose margin, the wedge grows and the envelope
   has to go back up. Is 30 degrees defensible for gelatin capsules on printed
   PLA, and is the repose model (a straight slope from the chute mouth) even the
   right model for the pile in tray A?
2. **The porch lanes are 20.28 mm.** Pills must run single file through a 30 mm
   stretch. The splitter rib's knife-edged upstream taper is the only thing
   stopping a capsule that arrives crosswise from stopping dead at it. Nothing
   verifies this.
3. **The chute ceiling on the 40-degree leg is a 50-degree-from-vertical
   overhang**, past the conservative 45-degree rule. This is the single
   `ADVISORY`. `chute_clear` carries a sag allowance; the stated fallback is a
   gabled ceiling. Is the allowance adequate, and is the fallback actually
   buildable without re-raising tray B?
4. **The cubby deck is 3 mm over a 224 mm span.** Hand-calculated deflection is
   under a millimetre at pill loads. Nobody has checked print-time behaviour or
   PLA creep under sustained load.
5. **Bay width is 1.65× the longest pill** against a 2–3× arching rule of thumb.
   Two capsules can in principle span a bay. Mitigated, not eliminated.
6. **Capacity is a geometric maximum.** Measured from the cavity meshes with the
   fill line at the underside of the lid. It is not a practical fill.
7. **Tier 2 throughout.** `doctor.py` reports no calibration profile, so every
   clearance — rail 0.35, fill lid 0.30, snap barb 0.8 of real engagement — is
   geometry only. A calibration coupon ships alongside and should be printed
   first.
8. **The accessory cubby's retaining lip is 42 mm**, which is taller than the
   cubby's own shallow end (41.3). That is intentional — it makes the forward
   part a well rather than a shelf — but it means anything stored there is
   lifted in and out over a lip nearly as tall as the space is deep at the
   front. Judge whether that is usable or merely defensible.
9. **The label recesses are 0.5 mm deep in walls 2.4 and 2.8 mm thick**, and
   the upper strip sits on the wall between the trays, which is also the wall
   doing the `trayB_front_retain` job. Check the interaction: the recess is not
   in the assert's formula.
10. **Coverage gaps are not passes.** Four checks are `not-applicable` and
   `check_rules.py` reports three antecedents that never fired (R-01, R-09,
   R-12). Seven rules are `MANUAL` and need explicit self-assessment. Nothing
   moves in this revision, so there is no motion sweep at all — a genuine
   reduction against revision 1, which had one.

## Two failure modes this project keeps producing

- **Two boolean faces sharing one plane.** Three separate incidents
  (`seat_lip_drop`, `boss_clip_drop`, `scallop_over`), each a non-watertight or
  torn mesh, each fixed by a small explicit offset. Check whether any remaining
  cut boundary is derived from the same expression as the face it lands on. The
  tell for this class is **"not watertight with zero boundary edges"** — counting
  unshared edges finds holes; only counting edges shared by *more* than two
  faces finds a coplanar touch.
- **`params.scad` is evaluated top to bottom, not hoisted.** A forward reference
  evaluates to `undef` and the assert that fires names a constraint that is not
  the problem. Check that no derived value reads something defined below it.

## What a useful report looks like

State findings as: what is wrong, how you established it (a command and its
output, not an assertion), and what it would take to fix. Rank by whether it
stops the part working, stops it printing, or is cosmetic. If you think a
decision in `plan.md` is wrong rather than merely unverified, say so and say
which decision ID.

If you find nothing, say what you looked at and what would have had to be true
for you to find something — a review that concludes "looks good" without that is
indistinguishable from one nobody ran.
