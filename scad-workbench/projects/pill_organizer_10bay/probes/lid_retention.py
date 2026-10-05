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
  (e) tilted 0..15 degrees about its BACK edge in 0.25 degree steps (the way a
      lid lifted by the front notches or hinged on from the back moves), with
      the back edge raised 0, 1 and 3 mm, it never intersects the body; the
      minimum clearance is reported every degree. The first stop face was
      vertical and jammed here at 0.5-2 degrees (review of revision 10, F1)
  (f) lifted along the plane's normal, 0..30 mm, it never intersects
  (g) the built lid's skirt reaches below the scalloped front wall's top

Exit status 1 on any failure.
"""
import sys
import numpy as np
import trimesh
from _common import params, parts, overlap_mm3, moved, translation

TOL = 0.5   # mm^3 of overlap that counts as contact (a 0.01 mm sliver is 0.1)
TOL_REST = 0.05   # the rest-pose cases start in contact, so they use a tenfold tighter threshold

P = params()
M = parts(("body", "pick_lid", "fill_lid"))
body, lid0 = M["body"], M["pick_lid"]
fill = moved(M["fill_lid"], translation([P["fill_x"], P["fill_y"], P["fill_z"]]))
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
      f"(expected {P['lug_clear']:.3f} = the clearance: both stop faces are perpendicular to the slope)")
# how much of the stop face the lug covers, from the overlap at 2 mm
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

# (e) tilt about the back edge
print()
back = lid.vertices[np.isclose(lid.vertices[:, 1], lid.bounds[1][1])]
pivot = back[np.argmin(back[:, 2])]
print(f"      back edge pivot at y {pivot[1]:.2f}, z {pivot[2]:.2f}")
fcl_ok = True
try:
    from trimesh.collision import CollisionManager
    cm = CollisionManager(); cm.add_object("body", body)
except Exception:
    fcl_ok = False
worst, first_bad, mins = 0.0, None, {}
for lift in (0.0, 1.0, 3.0):
    for ang in np.arange(0.0, 15.01, 0.25):
        R = trimesh.transformations.rotation_matrix(-np.radians(ang), [1, 0, 0], pivot)
        m = moved(lid, translation([0, 0, lift]) @ R)
        v = overlap_mm3(body, m)
        if v > TOL and first_bad is None: first_bad = (lift, ang, v)
        worst = max(worst, v)
        if fcl_ok and abs(ang - round(ang)) < 1e-9 and lift == 0.0:
            mins[int(round(ang))] = cm.min_distance_single(m)
front_z = [moved(lid, trimesh.transformations.rotation_matrix(-np.radians(5), [1, 0, 0], pivot)).bounds[1][2] - lid.bounds[1][2]]
check("(e) tilting about the back edge, 0..15 deg x back edge raised 0/1/3 mm (183 poses): no intersection",
      first_bad is None, f"worst overlap {worst:.3f} mm3" if first_bad is None else f"first overlap at lift {first_bad[0]} mm, {first_bad[1]} deg: {first_bad[2]:.2f} mm3")
if mins:
    print("      min clearance lid <-> body, back edge not raised, mm per degree of tilt:")
    print("      " + "  ".join(f"{a}:{d:.2f}" for a, d in mins.items()))
# the same poses in the reverse order are the lid being hinged ON from the back;
# the poses are identical, so the result is too -- stated, not re-run.

# (e2) tilt from the rest pose (touching the stops under gravity), with up-slope ride
print()
rest = moved(lid, translation(down * P["lug_clear"]))
check("(e2) the rest pose touches the stops without intersecting", overlap_mm3(body, rest) <= TOL_REST,
      f"overlap {overlap_mm3(body, rest):.3f} mm3 (lid {P['lug_clear']} mm down-slope of nominal)")
# the up-slope room from the rest pose: how far the lid can ride up the slope before it first meets
# the body (the lid's fillet beside the body's front top edge, since D53; the skirt before that)
lo, hi = 0.0, 2.0
for _ in range(14):
    mid = (lo + hi) / 2
    if overlap_mm3(body, moved(rest, translation(u * mid))) > TOL_REST: hi = mid
    else: lo = mid
ROOM = lo
print(f"      up-slope room from the rest pose: {ROOM:.3f} mm before the lid meets the body ({ROOM - P['lug_clear']:.3f} mm past the nominal pose)")
try:
    from trimesh.proximity import closest_point
    pts, _ = trimesh.sample.sample_surface(rest, 60000)
    front = pts[(pts[:, 1] < 4.0) & (pts[:, 0] > 20) & (pts[:, 0] < 220)]     # the skirt and the bend's fillet, between the lugs (which touch the stops by design)
    c = P["lug_clear"]
    for name, off in (("rest (on the stops, 0.5 down-slope of nominal)", 0.0), ("nominal pose", c), ("nominal + 0.2 up-slope", c + 0.2), ("nominal + 0.3 up-slope", c + 0.3)):
        q = front + u * off
        print(f"      closest skirt / fillet to body, {name}: {closest_point(body, q)[1].min():.3f} mm")
except Exception as ex:
    print("      (closest distance not measured: %s)" % ex)
def tilted(base, ang, ride):
    T = translation(u * ride)
    piv = pivot + down * P["lug_clear"] + u * ride
    R = trimesh.transformations.rotation_matrix(-np.radians(ang), [1, 0, 0], piv)
    return moved(base, R @ T)
need = {}
bad_at_zero = []
for ang in np.arange(0.25, 15.01, 0.25):
    if overlap_mm3(body, tilted(rest, ang, 0.0)) <= TOL_REST:
        need[ang] = 0.0; continue
    bad_at_zero.append(ang)
    lo, hi = 0.0, ROOM
    if overlap_mm3(body, tilted(rest, ang, hi)) > TOL_REST:
        need[ang] = None; continue
    for _ in range(12):
        mid = (lo + hi) / 2
        if overlap_mm3(body, tilted(rest, ang, mid)) > TOL_REST: lo = mid
        else: hi = mid
    need[ang] = hi
unsolved = [a for a, r in need.items() if r is None]
mx = max((r for r in need.values() if r is not None), default=0.0)
amax = max((a for a, r in need.items() if r == mx), default=0.0)
print(f"      from the rest pose with no ride, overlap at {len(bad_at_zero)} of {len(need)} angles"
      + (f" ({bad_at_zero[0]:.2f} .. {bad_at_zero[-1]:.2f} deg)" if bad_at_zero else ""))
print("      up-slope ride needed to clear it, mm, by degree of tilt (max over each degree's four steps):")
rows = []
for d in range(1, 16):
    rs = [need[a] for a in need if d - 1 < a <= d and need[a] is not None]
    rows.append(f"{d}:{max(rs):.2f}")
print("      " + "  ".join(rows))
check("(e2) tilting 0.25..15 deg from the rest pose clears with an up-slope ride inside the room there is (measured above)",
      not unsolved and mx < ROOM, f"max ride {mx:.3f} mm at {amax:.2f} deg, room {ROOM:.3f} mm" if not unsolved else f"no ride up to {ROOM:.3f} mm clears at {unsolved}")

# (h) lift, then draw forward; and where a straight lift meets the fill lid
print()
first = None
for k in np.arange(0.0, 40.01, 0.5):
    if overlap_mm3(fill, moved(lid, translation([0, 0, float(k)]))) > TOL:
        first = k; break
print(f"      a straight lift meets the fill lid's pull lip after {first} mm")
badh = []
for h in (8.0, 10.0, 15.0, 20.0, 24.0):
    for fwd in np.arange(0.0, 140.01, 5.0):
        m = moved(lid, translation([0, -float(fwd), h]))
        if overlap_mm3(body, m) > TOL or overlap_mm3(fill, m) > TOL:
            badh.append((h, fwd)); break
check("(h) lift 8/10/15/20/24 mm, then draw forward 0..140 mm: clears the body and the fill lid", not badh,
      "" if not badh else f"collides at (lift, forward) {badh}")
check("    a straight lift alone meets the fill lid only beyond 24 mm", first is not None and first > 24.0, f"first contact at {first} mm")

# (f) along the plane's normal
worst = 0.0
for k in range(0, 31):
    worst = max(worst, overlap_mm3(body, moved(lid, translation(N * float(k)))))
check("(f) lifts along the plane's normal 0..30 mm (31 poses): no intersection", worst <= TOL,
      f"worst overlap {worst:.3f} mm3")

# (g) the skirt really covers the scalloped wall
skirt_bot = lid.bounds[0][2]
check("(g) the built lid's skirt reaches at least 3 mm below the scalloped front wall's top",
      skirt_bot <= P["trayA_front_h"] - 3.0, f"skirt bottom z {skirt_bot:.1f}, wall top {P['trayA_front_h']:.1f}")
# first contact along the slope, as built, vs the 0.5 mm clearance
print("\nRESULT:", "ALL PASS" if ok else "FAILED")
sys.exit(0 if ok else 1)
