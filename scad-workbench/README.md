# scad-workbench

A provisioned, verified OpenSCAD toolchain for agent-driven mechanical design —
plus the survey of existing agent CAD skills that led to picking it.

This directory ships **no skill of its own**. The best available skill for
moving mechanical assemblies is already MIT-licensed and actively maintained;
rewriting it would be worse and slower. What was missing is the part every
project in the survey leaves to the reader: a toolchain that actually works on
a headless machine, and an acceptance test proving the verification can fail.

```
./install.sh    # toolchain + libraries + skills, idempotent
./verify.sh     # acceptance test: must catch a motion clash, must not invent one
```

## Why this stack

**OpenSCAD 2026.01 nightly, not the distro package.** Ubuntu 24.04 ships
2021.01, which predates the Manifold backend and falls back to CGAL. On the
test bracket the difference is sub-second versus tens of seconds, and Manifold
reports genus and manifoldness directly — information the checkers depend on.
Installed by extracting the AppImage (`--appimage-extract`) because containers
rarely provide FUSE.

**The GL stack, explicitly.** The AppImage bundles Qt but links against system
libEGL/libGL and exits before printing `--version` without them. Combined with
`xvfb-run`, PNG rendering works fully offscreen. Measured round trip on a
four-feature bracket: **STL 0.35 s, PNG 0.57 s.** Fast enough that "render and
look at it" is a normal step in a loop rather than a thing to avoid.

**BOSL2 via `OPENSCADPATH`.** Gears, threads and attachment primitives, resolved
by search path so no model file carries an absolute include.

**The Python stack installs separately** because it is not needed to *write* or
*render* a model, only to *check* one. The skill degrades honestly without it.

## The survey

Ranked for agent-driven design of moving assemblies, on a headless machine.

| Skill | Engine | ★ | Commits | Last commit | License |
|---|---|---|---|---|---|
| [Altern92/openscad-cad-skills](https://github.com/Altern92/openscad-cad-skills) | OpenSCAD | 0 | 121 | 2026-09-19 | MIT |
| [cyberchitta/cad-khana](https://github.com/cyberchitta/cad-khana) | build123d | 16 | 92 | 2026-07-26 | Apache-2.0 |
| [andreahaku/openscad_claude_skill](https://github.com/andreahaku/openscad_claude_skill) | OpenSCAD | 15 | 20 | 2026-08-14 | MIT |
| [flowful-ai/cad-skill](https://github.com/flowful-ai/cad-skill) | CadQuery | 572 | 21 | 2026-07-14 | PolyForm **Noncommercial** |
| [iancanderson/openscad-agent](https://github.com/iancanderson/openscad-agent) | OpenSCAD | 128 | 2 | 2026-02-03 | MIT |

Also examined: [mitsuhiko/agent-stuff](https://github.com/mitsuhiko/agent-stuff)
(3.1k★ repo, but the OpenSCAD skill is a small personal corner of it, shaped
for one author's environment); [Wyrd-Group/build123d-mcp](https://github.com/Wyrd-Group/build123d-mcp)
(463 commits, Apache-2.0, but an MCP server rather than a skill);
[clawd-maf/cad-agent](https://github.com/clawd-maf/cad-agent) (Docker + VTK
render server).

**Stars are the worst signal in this table.** The two most-starred entries have
2 and 21 commits; the most capable has zero stars. Popularity here tracks launch
publicity, not depth.

### Why Altern92 wins on this brief

It is the only one that verifies a mechanism *through its range of motion*.
Everything else checks the assembled pose, which for a gearbox, hinge, latch or
cam is close to meaningless — parts clear at 0° and interfere at 37°.

Three things mark it as engineering rather than demo:

1. **Checks report five outcomes** — PASS, FAIL, not-applicable, inconclusive,
   advisory — with a coverage count. An inconclusive check cannot be laundered
   into a pass, which is the failure mode that makes most verification theatre.
2. **It states its own limits first.** `motion_sweep.py` opens with "Sampling,
   not a proof" and explains that a clash narrower than the step can be missed.
   It repeats the caveat on failure, when it would be easiest to sound certain.
3. **It defends against the mistake that fakes a pass.** Meshing external gears
   turn opposite ways; a same-sign ratio produces a sweep that passes while
   proving nothing. The tool refuses to run on a sign-flipped declaration.

Its `doctor.py` reports the highest tier the current install can support and
refuses to promise fit without a measured calibration profile. That honesty is
the reason to trust the rest.

**The risk is real and worth stating:** zero stars, zero forks, a single author,
and internal engineering notes written in Lithuanian. It is verified here, not
vouched for by a community.

### Runners-up, and what each is actually best at

**cad-khana** is the closest competitor and the better choice on a workstation.
Its `mechanism.json` — structured interference, clearance and assertion results
— is the right output shape for an agent. It loses on weight (OCCT) and because
`khana view` targets the VS Code OCP viewer, useless to a headless session.

**andreahaku** is the best-architected *single-part* skill: a validation gate
enforcing arithmetic before vision (syntax → bbox → manufacturability → render),
which kills most errors without paying for a render, plus genuine STL-to-
parametric reconstruction at a documented 95–96% accuracy. Nothing else does
inverse CAD. It simply is not aimed at assemblies.

**flowful-ai** is the most polished and by far the most adopted, with a
Gridfinity generator and six-view previews. Note the license before reaching for
it: PolyForm Noncommercial 1.0.0 permits "personal study, private entertainment,
hobby projects, amateur pursuits." Hobby printing is squarely inside the grant;
billable client work is not.

**iancanderson** is a clean three-skill minimal reference — worth reading to see
the shape of the problem, not to depend on.

## What is verified, and what is not

`verify.sh` asserts the checker catches a defect that exists only in motion, and
stays quiet on the same geometry once the defect is removed.

What remains unproven after a green run: **fit**. Without a measured calibration
profile the stack verifies geometry, not tolerance — a bore comes out the
diameter you asked for, but whether that diameter yields a working press fit on
your printer is your calibration, not this toolchain's. `doctor.py` will say so.
