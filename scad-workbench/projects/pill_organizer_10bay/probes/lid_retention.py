#!/usr/bin/env python3
"""D38 retention probe: does the assembled pick lid actually stay on its slope?

This is the error class that shipped through revision 9: a design note said the
skirt stopped the lid sliding down its plane, an assert encoded it, and no check
ever MOVED the lid in the direction that matters. This one does, with exact
boolean volumes on the real meshes (not a contact heuristic):

  (b) at rest the lid does not intersect the body                      (0.2 mm gap)
  (a) slid 1, 2 and 5 mm down the plane (forward and down, 
      along (0, -cos s, -sin s)) it intersects the body, and the first contact is
      within 1 mm of travel
  (c) lifted straight up 30 mm in 1 mm steps it never intersects
  (d) turned 180 degrees about the plane's normal it cannot seat: it intersects
      the body at every in-plane position that keeps it over the pick plane

Exit status 1 on any failure.
"""
import sys
import numpy as np
import trimesh
from _common import params, parts, overlap_mm3, moved, translation

TOL = 0.5   # mm^3 of overlap that counts as contact (a 0.01 mm sliver is 0.1)

P = params()
M = parts()
body, lid0 = M["body"], M["pick_lid"]
s = np.radians(P["slope"])
u = np.array([0.0, np.cos(s), np.sin(s)])       # up the plane
N = np.array([0.0, -np.sin(s), np.cos(s)])      # plane normal, out of the body
lid = moved(lid0, translation([P["lid_dx"], 0, 0]))   # as layout.scad places it
down = -u
ok = True


def check(label, cond, detail=""):
    global ok
    ok &= bool(cond)
    print(("PASS  " if cond else "FAIL  ") + label + (("   " + detail) if detail else ""))


print(f"pick plane {P['slope']:.2f} deg; lug clearance {P['lug_clear']} mm; "
      f"asserted engagement {P['engage_asserted']:.2f} mm\n")

# (b) rest
v0 = overlap_mm3(body, lid)
check("(b) at rest: lid does not intersect the body", v0 <= TOL, f"overlap {v0:.3f} mm3")

# (a) down-slope
print()
for d in (1.0, 2.0, 5.0):
    v = overlap_mm3(body, moved(lid, translation(down * d)))
    check(f"(a) slid {d:g} mm down the plane intersects the body", v > TOL, f"overlap {v:.2f} mm3")
lo, hi = 0.0, 1.0
for _ in range(14):
    mid = (lo + hi) / 2
    if overlap_mm3(body, moved(lid, translation(down * mid))) > TOL: hi = mid
    else: lo = mid
check("(a) first contact within 1 mm of travel", hi < 1.0, f"first contact at {hi:.3f} mm "
      f"(expected {P['lug_clear'] / np.cos(s):.3f} = clearance / cos(slope))")
# how much of the pillar's back face the lug covers, from the overlap at 2 mm
deep = trimesh.boolean.intersection([body, moved(lid, translation(down * 2.0))], engine="manifold")
zr = deep.bounds[:, 2]
print(f"      overlap region at 2 mm: z {zr[0]:.2f} .. {zr[1]:.2f} (height {zr[1]-zr[0]:.2f} mm), "
      f"x {deep.bounds[0,0]:.1f} .. {deep.bounds[1,0]:.1f}, y {deep.bounds[0,1]:.2f} .. {deep.bounds[1,1]:.2f}")

# (c) straight lift
print()
worst = 0.0
for k in range(0, 31):
    v = overlap_mm3(body, moved(lid, translation([0, 0, float(k)])))
    worst = max(worst, v)
check("(c) lifts straight up 30 mm (31 poses, 1 mm steps) with no intersection",
      worst <= TOL, f"worst overlap {worst:.3f} mm3")
# and sideways play: the lugs locate in X
for dx in (-0.45, 0.45):
    v = overlap_mm3(body, moved(lid, translation([dx, 0, 0])))
    check(f"    sideways {dx:+.2f} mm is still free", v <= TOL, f"overlap {v:.3f} mm3")
for dx in (-0.8, 0.8):
    v = overlap_mm3(body, moved(lid, translation([dx, 0, 0])))
    check(f"    sideways {dx:+.2f} mm is blocked by a lug or the side wall", v > TOL, f"overlap {v:.2f} mm3")

# (d) reversed: 180 degrees about the plane's normal, through the plate's centre
print()
c_world = lid.bounds.mean(axis=0)
R = trimesh.transformations.rotation_matrix(np.pi, N, c_world)
rev = moved(lid, R)
v = overlap_mm3(body, rev)
check("(d) turned 180 degrees about the plane normal: intersects the body", v > TOL, f"overlap {v:.1f} mm3")
free = []
vmin = 1e18
for shift in np.arange(-60.0, 60.01, 2.0):
    for dn in (0.0,):
        T = translation(u * shift + N * dn)
        vv = overlap_mm3(body, moved(rev, T))
        vmin = min(vmin, vv)
        if vv <= TOL: free.append(shift)
check("(d) no in-plane position within +-60 mm along the slope lets it seat",
      not free, f"min overlap over the scan {vmin:.1f} mm3; free positions {free}")
# what the reversed lid hits
hit = trimesh.boolean.intersection([body, rev], engine="manifold")
zr = hit.bounds
print(f"      reversed lid meets the body at y {zr[0,1]:.1f} .. {zr[1,1]:.1f}, z {zr[0,2]:.1f} .. {zr[1,2]:.1f}")

print("\nRESULT:", "ALL PASS" if ok else "FAILED")
sys.exit(0 if ok else 1)
