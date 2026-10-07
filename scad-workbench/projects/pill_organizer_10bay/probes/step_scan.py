#!/usr/bin/env python3
"""D60 gate: no persistent step in any wall face of the body.

A step is two parallel, collinear-direction faces of a horizontal section (z every 1 mm) joined by a short
face 0.02 to 1.0 mm long: a coplanar-avoidance offset, a fillet that stops short, a feature narrower than the
one it joins. Slicers print them as a visible ledge. A hit that repeats in 3 or more consecutive sections
(chained by position) is persistent; one bigger than STEP_MAX (0.06 mm) fails the gate unless it is a named
exception:

  * the label recesses (0.5 mm deep, D19/D45), which need their full depth for the tape
  * F13: the rail-1 buttress top, 0.2 under the plane beside the side wall (the K1/K2-verified break-out zone)

Single-slice hits are sloped or tangent surfaces crossing the section, not steps, and are listed only.
Adapted from the final QA audit's stepscan.py (docs/reports/2026-10-07-final-qa/).

    python3 probes/step_scan.py [body.stl]      # no argument: renders parts/body.scad
"""
import sys
import numpy as np
import trimesh
from _common import params, parts

STEP_MAX = 0.06
Z0, Z1, DZ = 1.0, 189.0, 1.0
LABEL_DEPTH = 0.5


def cr(a, b):
    return a[0] * b[1] - a[1] * b[0]


def scan_z(m, vals):
    hits = []
    for v in vals:
        s = m.section(plane_origin=[0, 0, v], plane_normal=[0, 0, 1])
        if s is None:
            continue
        for e in s.entities:
            P = s.vertices[e.points][:, (0, 1)]
            merged = []
            for i in range(len(P) - 1):
                a, b = P[i], P[i + 1]
                d = b - a
                L = np.linalg.norm(d)
                if L < 1e-6:
                    continue
                if merged and abs(cr(merged[-1][2], d / L)) < 0.01 and np.dot(merged[-1][2], d / L) > 0:
                    a0 = merged[-1][0]
                    dd = b - a0
                    merged[-1] = (a0, b, dd / np.linalg.norm(dd), np.linalg.norm(dd))
                else:
                    merged.append((a, b, d / L, L))
            for i in range(len(merged) - 2):
                A, C, B = merged[i], merged[i + 1], merged[i + 2]
                if A[3] > 1.0 and B[3] > 1.0 and 0.02 < C[3] < 1.0 and abs(cr(A[2], B[2])) < 0.035 \
                        and np.dot(A[2], B[2]) > 0:
                    off = abs(cr(A[2], B[0] - A[1]))
                    if 0.02 < off < 1.0:
                        hits.append((float(v), float(C[0][0]), float(C[0][1]), float(off)))
    return hits


def link(hits):
    """Link hits in consecutive sections that sit within 1.5 mm in x, 2.5 in y and 0.05 in size."""
    hits = sorted(hits)
    cs = []
    for h in hits:
        for c in cs:
            l = c[-1]
            if abs(h[0] - l[0] - DZ) < 1e-6 and abs(h[1] - l[1]) <= 1.5 and abs(h[2] - l[2]) <= 2.5 and abs(h[3] - l[3]) <= 0.05:
                c.append(h)
                break
        else:
            cs.append([h])
    return cs


def exception(c, P):
    off = np.mean([h[3] for h in c])
    xs = [h[1] for h in c]; ys = [h[2] for h in c]; zs = [h[0] for h in c]
    mw = P["module_w"]
    if abs(off - LABEL_DEPTH) < 0.03:
        return "label recess"
    near_side = min(xs) < 6.5 or max(xs) > mw - 6.5
    if near_side and abs(off - P["boss_clip_drop"]) < 0.03 and min(zs) > 80 and P['rail1_y'] - P['rail_boss_w'] / 2 - 1 < min(ys) and max(ys) < P['rail1_y'] + P['rail_boss_w'] / 2 + 1:
        return "F13 buttress top"
    return None


def main():
    P = params()
    path = sys.argv[1] if len(sys.argv) > 1 else None
    m = trimesh.load(path) if path else parts(("body",))["body"]
    hits = scan_z(m, np.arange(Z0, Z1, DZ))
    cs = link(hits)
    persistent = [c for c in cs if len(c) >= 3]
    single = len(cs) - len(persistent)
    bad = 0
    print(f"step scan: {len(hits)} hits in {len(np.arange(Z0, Z1, DZ))} sections, {len(persistent)} persistent chains, {single} single or short")
    for c in sorted(persistent, key=lambda c: (c[0][1], c[0][2], c[0][0])):
        off = np.mean([h[3] for h in c]); ex = exception(c, P)
        tag = ex or ("PASS (<= %.2f)" % STEP_MAX if off <= STEP_MAX else "FAIL")
        if ex is None and off > STEP_MAX:
            bad += 1
        print(f"  {'exception' if ex else tag.split()[0]:9s} {off:5.2f} mm  x {c[0][1]:7.2f}  y {c[0][2]:7.2f}  z {c[0][0]:5.1f}..{c[-1][0]:5.1f}  {ex or ''}")
    print("RESULT: " + ("ALL PASS: no persistent step over %.2f mm except the named exceptions" % STEP_MAX if bad == 0 else f"{bad} FAILURES"))
    sys.exit(0 if bad == 0 else 1)


main()
