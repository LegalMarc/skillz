# Handoff: designing parts in a fresh session

Read this first, follow it in order. It assumes you are a coding agent with a
Bash tool and an image-capable Read tool, starting in a container with nothing
installed.

## 1. Bootstrap

```bash
cd scad-workbench && ./install.sh && source ~/.local/opt/openscad/env.sh
```

Takes a few minutes, mostly an 84 MB download. It is idempotent — rerun it
freely. It **exits non-zero if the result cannot render**, so a zero exit is a
real signal. Note the tier it prints.

Then confirm the chain end to end before designing anything:

```bash
./verify.sh    # expect: 6 passed, 0 failed
```

## 2. Load the skill — by reading it, not by waiting for it

`install.sh` symlinks three skills into `~/.claude/skills/`, but **a session
that installs them mid-run will not have them auto-loaded** — discovery happens
at startup. Do not wait for a skill to trigger. Read it directly:

```bash
~/.local/src/openscad-cad-skills/scad-modeler/SKILL.md        # assemblies, motion
~/.local/src/openscad-cad-skills/openscad-cad/SKILL.md        # single parts
~/.local/src/openscad-cad-skills/openscad-organic/SKILL.md    # organic forms
```

`scad-modeler/SKILL.md` is ~900 lines. Read it fully before your first
assembly — it encodes failure modes (`include` re-running a part's own render,
`$fn` undersizing bores, unresolved `BOSL2/std.scad`) that cost hours to
rediscover. `references/` holds the deeper material; load on demand.

## 3. The loop

```
params.scad asserts  ->  render  ->  LOOK  ->  numeric checks  ->  correct
```

**Write relationships as `assert()` in `params.scad` before the geometry that
depends on them.** Two circles must satisfy `r1 + r2 > center_distance`; a
shaft must fit its bore. These evaluate at near-zero cost before any geometry
is built, and they make a bad edit fail loudly instead of quietly producing a
wrong part.

**Render six views and look at them:**

```bash
./render.sh model.scad build/preview          # add -D wall=3 to override params
```

Then **Read `build/preview/contact.png`** — one image, six labelled views, all
locked to one camera scale. Read a single view only when the sheet shows
something worth magnifying. (It is one shared scale deliberately: `--viewall`
fits each view independently, so the same part renders at different sizes from
different angles, and an agent comparing proportions across that would chase a
distortion that isn't there.)

**Then run the numeric checks** — `run_checks.py`, and `motion_sweep.py` for
anything that moves. Declare motion in `joints.json`; the sweep is the only
thing here that can catch a part that is clear at rest and interferes at 37°.

## 4. What the render can and cannot tell you

This is the rule that keeps a visual loop from making things worse.

**A render is evidence about topology, not dimension.** Use it to catch: a bore
through the wrong face, a feature on one side only, a part floating off its
mate, an inside-out boolean, a shape that simply isn't what was asked for.

**Never judge size from the image.** Do not conclude a wall is too thin, a
clearance too tight, or a part too tall by looking. Those come from
`// EXPECTED_BBOX: [x, y, z]` and `check_dimensions.py`, which derive tolerance
from the part's own facet resolution. An agent that "corrects" a dimension
because a picture looked wrong will introduce a defect the numbers would have
denied.

Arithmetic first, vision second — asserts and checks catch most errors before
a render is even worth paying for.

## 5. Discipline that the checks depend on

- **Every dimension lives in `params.scad`.** A bare number in a part file is
  invisible to change propagation.
- **`// EXPECTED_BBOX:` on any part whose size matters** — otherwise
  `check_dimensions.py` has nothing to check against and stays silent.
- **Never widen `min_clearance_mm` to make a sweep pass.** Fix the centre
  distance, the backlash, or the layout. The tool says this itself.
- **An `inconclusive` result is not a pass.** The checks report five outcomes
  precisely so it cannot be read as one.
- **Lower `--step-deg` before calling a mechanism clear.** The sweep samples;
  a tooth flank is not resolved at 5°.

## 6. Limits — state these rather than working around them

- **Fit is unverified.** Without a measured calibration profile the stack is at
  tier 2: geometry only. A bore comes out the diameter requested; whether that
  yields a working press fit on a specific printer is uncalibrated. Say so
  rather than implying a fit will work.
- **The sweep samples, it does not prove.** A clash narrower than the step, far
  from the global minimum, can be missed.
- **Two-part assemblies get little from the sweep.** If every moving pair is
  already a declared contact it reports "nothing to check" — correctly. The
  sweep earns its keep at three or more parts.

## 7. When to stop and ask

Ask the user rather than guessing when: a dimension depends on hardware not yet
specified (a bearing OD, a screw length, a shaft diameter); a tolerance depends
on their printer; or the request is ambiguous about which surface mates with
what. Guessing a mating dimension produces a part that looks right in every
view and does not fit.

Otherwise, work autonomously: design, render, look, check, correct, and report
what you assumed.
