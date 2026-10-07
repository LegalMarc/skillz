#!/usr/bin/env python3
"""D58 gate: the body ganged with a copy of itself (copy at +module_w), measured on the meshes.

Sections of the pair at >= 6 heights over each rail; at each, the y gap between the neighbour's male rail and
this body's groove, on both flanks, at 7 depths from the mouth to the rail tip. Every gap must equal
rail_clear within 0.01 mm (the 45 degree underside lead below z = rail_z0 + 3 and the top lead's last 3 mm are
the intentional exceptions and are not sampled). Then the copy is lowered straight down onto the body from
above, as a user does: no volume overlaps at any height of the descent.

    source ~/.local/opt/openscad/env.sh
    python3 probes/gang_fit.py
"""
import sys, warnings
import numpy as np
from shapely.geometry import LineString
from shapely.ops import unary_union
from _common import params, parts, moved, translation, overlap_mm3

warnings.filterwarnings("ignore")
P = params(); body = parts(("body",))["body"]
mw, rc, z0 = P["module_w"], P["rail_clear"], P["rail_z0"]
ok = True


def chk(label, cond, extra=""):
    global ok
    ok &= bool(cond)
    print(("PASS  " if cond else "FAIL  ") + label + (("  " + extra) if extra else ""))


def union_at(mesh, z):
    s = mesh.section(plane_origin=[0, 0, z], plane_normal=[0, 0, 1])
    p, _ = s.to_2D(to_2D=translation([0, 0, -z]))
    return unary_union(list(p.polygons_full))


def segs(geom):
    return [g for g in getattr(geom, "geoms", [geom]) if not g.is_empty]


neighbour = moved(body, translation([mw, 0, 0]))
rails = (("rail 1", P["rail1_y"], P["rail1_z1"], (14, 20, 30, 50, 70, 85)),
         ("rail 2", None, None, (14, 20, 40, 70, 100, 108)))
# rail 2's y and top are not in params_dump: read them from the body's own geometry via the neighbour's section
depths = (0.02, 0.5, 1.0, 1.5, 2.0, 2.5, 2.98)
worst = 0.0
for name, yc, z1, zs in rails:
    if yc is None:
        yc = P["rail2_y"]
    print(f"-- {name} (y {yc:.2f})")
    for z in zs:
        A, B = union_at(body, z), union_at(neighbour, z)
        row = []
        for d in depths:
            x = mw - d
            ln = LineString([(x, yc - 5), (x, yc + 5)])
            gs = segs(A.intersection(ln))
            rs = [g for g in segs(B.intersection(ln)) if g.bounds[1] < yc < g.bounds[3]]
            r = rs[0]
            lo = max(g.bounds[3] for g in gs if g.bounds[3] <= r.bounds[1] + 1e-9)
            hi = min(g.bounds[1] for g in gs if g.bounds[1] >= r.bounds[3] - 1e-9)
            row += [r.bounds[1] - lo, hi - r.bounds[3]]
        e = max(abs(g - rc) for g in row)
        worst = max(worst, e)
        print(f"   z {z:5.1f}: gap min {min(row):.4f} max {max(row):.4f} (rail_clear {rc})")
        chk(f"{name} z {z}: both flanks' y gap equals rail_clear at 7 depths", e < 0.01, f"(worst error {e:.4f})")
print(f"worst error over all sections {worst:.4f} mm")
for dz in (0, 0.5, 2, 5, 10, 20, 40, 80, 120):
    ov = overlap_mm3(body, moved(neighbour, translation([0, 0, dz])))
    chk(f"the copy {dz} mm above its ganged height does not intersect the body", ov < 1e-6, f"(overlap {ov:.4f} mm3)")
print("ALL PASS" if ok else "FAILED")
sys.exit(0 if ok else 1)
