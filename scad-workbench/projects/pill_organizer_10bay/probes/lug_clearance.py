#!/usr/bin/env python3
"""D62-D64 probe: the stiffened pick-lid lugs against the COMMITTED body (build/body.stl).

The body is already printed, so this reads build/body.stl, not a fresh render, and measures on the
meshes: the minimum distance from the lugs to the body at the nominal pose and along every removal
motion (tilt about the back edge, straight lift, lift along the plane's normal, lift then forward).

The lug keeps two faces 0.5 mm from the body BY DESIGN: the front (stop) face against the stop block and
the outboard face against the side wall. Everything D62-D64 added (the drafted back and inboard faces,
the longer back, the root fillet) must keep >= 1.0 mm to every body surface, so the surface samples on
those two planes are excluded from the "new material" figure; the all-in minimum is reported as well.

    source ~/.local/opt/openscad/env.sh
    python3 probes/lug_clearance.py
"""
import os, sys
import numpy as np
import trimesh
from trimesh.proximity import closest_point
from _common import params, parts, moved, translation, PROJECT

NEW_MIN = 1.0
P = params()
M = parts(("pick_lid",))
LUGS = parts(("pick_lid",), defs=('SUBFEATURE="pick_lugs"',))["pick_lid"]
body = trimesh.load(os.path.join(PROJECT, "build", "body.stl"))
assert body.is_watertight
s = np.radians(P["slope"])
u = np.array([0.0, np.cos(s), np.sin(s)])
N = np.array([0.0, -np.sin(s), np.cos(s)])
dx = P["lid_dx"]
lid = moved(M["pick_lid"], translation([dx, 0, 0]))
lugs = moved(LUGS, translation([dx, 0, 0]))
down = -u
# The lugs live in the front 60 mm (y) of the body and in the two end bays: crop to that so the exact
# point-to-triangle queries stay quick (the crop is far larger than any pose reaches).
c = body.triangles_center
keep_f = (c[:, 1] < 60.0) & ((c[:, 0] < 25.0) | (c[:, 0] > 215.0))
body = trimesh.Trimesh(body.vertices, body.faces[keep_f], process=False)

# surface samples of the lugs, minus the two faces that are 0.5 mm from the body by design
pts, fidx = trimesh.sample.sample_surface(lugs, 6000, seed=1)
# the mesh's own vertices are added: the closest point of a polyhedron to a plane is usually a corner
pts = np.vstack([pts, lugs.vertices])
# the front (stop) face is the plane s = s0 in the lid frame; the outboard faces are x = wall + clearance
s0 = P["stop_y"] / np.cos(s) - 0.2 * np.sin(s) + P["lug_clear"]
sc = pts[:, 1] * np.cos(s) + (pts[:, 2] - (P["pickplane_front"] + 0.2)) * np.sin(s)
on_front = np.abs(sc - s0) < 0.02
on_out = (np.abs(pts[:, 0] - (P["wall_out"] + P["lug_clear"])) < 0.02) | (np.abs(pts[:, 0] - (P["module_w"] - P["wall_out"] - P["lug_clear"])) < 0.02)
# Points within 1 mm of the front plane (along the slope) or of an outboard plane (in X) are the edge regions of the two
# faces that are 0.5 mm from the body by design (the old lug's inboard and back faces sit just as close at those edges),
# so they belong to the D38 contact, not to D62-D64.
near_out = (np.abs(pts[:, 0] - (P["wall_out"] + P["lug_clear"])) < 1.0) | (np.abs(pts[:, 0] - (P["module_w"] - P["wall_out"] - P["lug_clear"])) < 1.0)
new_mask = ~(on_front | on_out | near_out) & (sc >= s0 + 1.0)
print(f"lug surface samples: {len(pts)}, of which {int(new_mask.sum())} are not on the front or outboard faces")


def mind(T):
    q = pts @ T[:3, :3].T + T[:3, 3]
    d = closest_point(body, q)[1]
    return float(d[new_mask].min()), float(d.min())


def tf(ang=0.0, lift=0.0, off=None, pivot=None):
    T = np.eye(4)
    if ang:
        T = trimesh.transformations.rotation_matrix(-np.radians(ang), [1, 0, 0], pivot)
    Tt = translation(np.zeros(3) if off is None else off)
    Tl = translation([0, 0, lift])
    return Tt @ Tl @ T


back = lid.vertices[np.isclose(lid.vertices[:, 1], lid.bounds[1][1])]
pivot = back[np.argmin(back[:, 2])]
rest_off = down * P["lug_clear"]
ok = True
worst_new = 99.0


def report(label, rows):
    global ok, worst_new
    dn = min(r[1] for r in rows)
    da = min(r[2] for r in rows)
    at = [r[0] for r in rows if r[1] == dn][0]
    worst_new = min(worst_new, dn)
    good = dn >= NEW_MIN
    ok &= good
    print(("PASS  " if good else "FAIL  ") + f"{label}: new material min {dn:.3f} mm (at {at}); all-in min {da:.3f} mm")


dn, da = mind(np.eye(4))
print(f"nominal pose: new material min {dn:.3f} mm, all-in min {da:.3f} mm (0.5 = front/outboard faces by design)")
report("nominal pose", [("nominal", dn, da)])
dn, da = mind(translation(rest_off))
report("rest pose (0.5 mm down-slope, on the stops; all-in 0 is the stop contact)", [("rest", dn, da)])
rows = []
RIDE = 0.25     # the up-slope ride the lid needs from the rest pose to tilt (lid_retention (e2): 0.19 mm at most)
for ang in np.arange(0.0, 15.01, 1.0):
    for base, bn in ((np.zeros(3), "nominal"), (rest_off + u * RIDE, f"rest + {RIDE} mm ride")):
        T = tf(ang=ang, off=None, pivot=pivot + base)
        T = translation(base) @ T
        a, b = mind(T)
        rows.append((f"{ang:g} deg from {bn}", a, b))
report("tilt about the back edge 0..15 deg, from nominal and from the rest pose", rows)
rows = [(f"{k} mm", *mind(translation([0, 0, float(k)]))) for k in range(0, 31, 2)]
report("straight lift 0..30 mm", rows)
rows = [(f"{k} mm", *mind(translation(N * float(k)))) for k in range(0, 31, 2)]
report("lift along the plane's normal 0..30 mm", rows)
rows = []
for h in (8.0, 15.0, 24.0):
    for fwd in np.arange(0.0, 60.01, 5.0):
        rows.append((f"lift {h:g} then forward {fwd:g}", *mind(translation([0, -float(fwd), h]))))
report("lift 8/15/24 mm then draw forward 0..60 mm", rows)
print(f"\nRESULT: {'ALL PASS' if ok else 'FAILED'} (worst new-material distance {worst_new:.3f} mm, limit {NEW_MIN})")
sys.exit(0 if ok else 1)
