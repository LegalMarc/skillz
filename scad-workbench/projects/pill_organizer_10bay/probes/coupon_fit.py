#!/usr/bin/env python3
"""D56 probe: the rail coupon's groove block, seated on every stub in the mesh.

For each stub the block is turned bed-face UP (rotated 180 degrees about x, so the groove still
opens toward +x), its groove bottom is put on the stub's tip, its centre on the stub's y, and its
underside on the plate top. Then, on the meshes:

  * the block overlaps no OTHER stub (exact boolean volume) and clears each by >= MIN_GAP mm;
  * the block lies inside the plate (margin reported) and covers no label recess;
  * the stub's own root clearance (y gap, groove half-width minus stub half-width at the stub root,
    mid-height cross-section) equals its label; on a ribbed stub the deepest rib penetration into the
    groove flank equals the label's interference;
  * every body is watertight with no zero-area faces (the sliver class, INCIDENTS.md).

    source ~/.local/opt/openscad/env.sh
    python3 probes/coupon_fit.py                                  # the current calibration_coupon.scad
    python3 probes/coupon_fit.py --old build/calibration_coupon.stl --clear 0.30,0.29,0.28,0.27,0.26
        # a single-plate coupon from before D56 (stubs and block in one file), to reproduce the defect
"""
import argparse, math, os, sys, tempfile, warnings
warnings.filterwarnings('ignore')
import numpy as np
import trimesh
from shapely.geometry import LineString, Point, Polygon, box
from _common import scad, moved, translation, overlap_mm3, PROJECT

MIN_GAP = 8.0          # block to any neighbouring stub, mm (D56)
PLATE_T = 4.0
MID = PLATE_T + 6.0    # mid-height of a 12 mm stub
ok = True


def chk(label, cond, extra=""):
    global ok
    ok &= bool(cond)
    print(("PASS  " if cond else "FAIL  ") + label + (("  " + extra) if extra else ""))


def section(mesh, z):
    s = mesh.section(plane_origin=[0, 0, z], plane_normal=[0, 0, 1])
    if s is None:
        return []
    p2, _ = s.to_2D(to_2D=translation([0, 0, -z]))
    return list(p2.polygons_full)


def bodies(mesh):
    return sorted(mesh.split(only_watertight=False), key=lambda m: -m.volume)


def mesh_health(name, m):
    areas = m.area_faces
    chk(f"{name}: watertight, winding consistent, no zero-area face",
        m.is_watertight and m.is_winding_consistent and areas.min() > 1e-9,
        f"({len(m.faces)} faces, smallest {areas.min():.2e} mm2)")


def seat(block, stub_tip_x, stub_y):
    """Block turned bed-face up, groove bottom on the stub tip, underside on the plate top."""
    c = block.bounds.mean(axis=0)
    R = trimesh.transformations.rotation_matrix(math.pi, [1, 0, 0], c)
    b = moved(block, R)
    sec = section(block, block.bounds[0][2] + 9)
    mouth_x = block.bounds[1][0]
    y0, y1 = block.bounds[0][1], block.bounds[1][1]
    groove_bottom = min(x for p in sec for x, y in p.exterior.coords
                        if x > block.bounds[0][0] + 5 and y0 + 1 < y < y1 - 1)
    d = [stub_tip_x - groove_bottom, stub_y - c[1], PLATE_T - b.bounds[0][2]]
    return moved(b, translation(d))


def halfspan(poly, x, yc, kind):
    """kind 'stub': (ymin, ymax) of the stub at x.  'block': the cavity's (lower edge, upper edge)."""
    ln = LineString([(x, yc - 9), (x, yc + 9)])
    seg = poly.intersection(ln)
    segs = [g for g in getattr(seg, "geoms", [seg]) if not g.is_empty]
    if kind == "stub":
        ys = [y for g in segs for _, y in g.coords]
        return min(ys), max(ys)
    lo = max(g.bounds[3] for g in segs if g.bounds[3] < yc)
    hi = min(g.bounds[1] for g in segs if g.bounds[1] > yc)
    return lo, hi


def analyse(tag, plate, block, expect, ribs):
    """plate: one mesh (plate + stubs); expect: per stub (root clearance[, interference]).

    Two poses per stub. BOTTOM: the groove bottom on the stub tip (the block pushed fully on; the
    mouth then stands rail_depth_clear past the stub root). ROOT: the groove mouth level with the stub
    root, which is how the body seats the rail (the walls meet there), and where the label's
    clearance is defined. Neighbour, edge and label checks take the worse of the two."""
    top = section(plate, PLATE_T + 6)
    stubs = sorted(top, key=lambda p: p.bounds[0])
    labels = [Polygon(h) for p in section(plate, PLATE_T - 0.3) for h in p.interiors]
    pb = plate.bounds
    cut = trimesh.creation.box(extents=[1e3, 1e3, 40], transform=translation([0, 0, PLATE_T + 0.001 + 20]))
    stub_solids = trimesh.boolean.intersection([plate, cut], engine="manifold").split(only_watertight=False)
    stub_solids = sorted(stub_solids, key=lambda m: m.bounds[0][0])
    assert len(stub_solids) == len(stubs) == len(expect), (len(stub_solids), len(stubs), len(expect))
    print(f"-- {tag}: {len(stubs)} stubs, plate x {pb[0][0]:.1f}..{pb[1][0]:.1f}, y {pb[0][1]:.1f}..{pb[1][1]:.1f}")
    for i, (sp, exp) in enumerate(zip(stubs, expect)):
        tip, root = sp.bounds[0], sp.bounds[2]
        yc = (sp.bounds[1] + sp.bounds[3]) / 2
        bottom = seat(block, tip, yc)
        rootpose = moved(bottom, translation([root - bottom.bounds[1][0], 0, 0]))
        worst_gap, worst_ov, edge, lab_gap, lab_ov = 1e9, 0.0, 1e9, 1e9, 0.0
        for blk in (bottom, rootpose):
            bb = blk.bounds
            for j, sm in enumerate(stub_solids):
                if j == i:
                    continue
                worst_ov = max(worst_ov, overlap_mm3(blk, sm))
                worst_gap = min(worst_gap,
                                trimesh.proximity.closest_point(sm, blk.vertices)[1].min(),
                                trimesh.proximity.closest_point(blk, sm.vertices)[1].min())
            edge = min(edge, bb[0][0] - pb[0][0], pb[1][0] - bb[1][0], bb[0][1] - pb[0][1], pb[1][1] - bb[1][1])
            fp = section(blk, PLATE_T + 0.3)[0]
            lab_ov = max([lab_ov] + [fp.intersection(l).area for l in labels])
            lab_gap = min([lab_gap] + [fp.distance(l) for l in labels])
        # own clearance, mid-height, in the ROOT pose
        bsec = [p for p in section(rootpose, MID) if p.area > 50][0]
        lo, hi = halfspan(bsec, root - 0.001, yc, "block")
        slo, shi = halfspan(sp, root - 0.001, yc, "stub")
        root_clear = ((hi - shi) + (slo - lo)) / 2
        # flank gap (y, both flanks, mean) at several depths from the root: D57 says it is the label everywhere
        depths = (0.3, 1.5, 2.7) if ribs else (0.1, 0.6, 1.2, 1.8, 2.4, 2.9)    # ribs sit at 0.9 and 2.1 +- 0.4
        gaps = []
        for dep in depths:
            glo, ghi = halfspan(bsec, root - dep, yc, "block")
            plo, phi = halfspan(sp, root - dep, yc, "stub")
            gaps.append(((ghi - phi) + (plo - glo)) / 2)
        verts = [Point(x, y) for x, y in sp.exterior.coords]
        tight = min((-1 if bsec.contains(v) else 1) * bsec.exterior.distance(v) for v in verts)
        own_ov = overlap_mm3(rootpose, stub_solids[i])
        print(f"   stub {i}: tip x {tip:6.1f}  block x {bottom.bounds[0][0]:6.1f}..{bottom.bounds[1][0]:6.1f} (bottom pose)  "
              f"nearest other stub {worst_gap:5.2f}  overlap w/ others {worst_ov:.3f} mm3  "
              f"plate edge margin {edge:5.2f}  label gap {lab_gap:5.2f}")
        print(f"            root clearance {root_clear:+.4f} (label {exp[0]:.2f})  "
              f"tightest gap, any stub vertex {tight:+.4f}  overlap with its own groove {own_ov:.4f} mm3")
        chk(f"{tag} stub {i}: no overlap with any other stub", worst_ov < 1e-6)
        chk(f"{tag} stub {i}: block clears every other stub by >= {MIN_GAP} mm", worst_gap >= MIN_GAP,
            f"(measured {worst_gap:.2f})")
        chk(f"{tag} stub {i}: block inside the plate", edge >= 0, f"(margin {edge:.2f})")
        chk(f"{tag} stub {i}: block covers no label", lab_ov < 1e-6 and lab_gap > 0.5, f"(gap {lab_gap:.2f})")
        print("            flank gap at depth " + "  ".join(f"{d}: {g:.4f}" for d, g in zip(depths, gaps)))
        chk(f"{tag} stub {i}: flank gap equals the label {exp[0]:.2f} at every depth sampled",
            all(abs(g - exp[0]) < 0.005 for g in gaps), f"(worst error {max(abs(g - exp[0]) for g in gaps):.4f})")
        if not ribs:
            chk(f"{tag} stub {i}: no part of the stub touches the groove", tight > 0, f"(tightest {tight:+.4f})")
        chk(f"{tag} stub {i}: root clearance equals its label {exp[0]:.2f}", abs(root_clear - exp[0]) < 0.005,
            f"(measured {root_clear:.4f})")
        if ribs:
            chk(f"{tag} stub {i}: rib interference equals its label {exp[1]:.2f}",
                abs(-tight - exp[1]) < 0.006 if exp[1] > 0 else abs(tight) < 0.006,
                f"(measured {-tight:.4f})")


ap = argparse.ArgumentParser()
ap.add_argument("--old", help="single-plate STL from before D56 (plate, stubs and block in one file)")
ap.add_argument("--clear", help="expected root clearances of the --old stubs, left to right")
a = ap.parse_args()

if a.old:
    m = trimesh.load(os.path.join(PROJECT, a.old) if not os.path.isabs(a.old) else a.old)
    parts = bodies(m)
    block = [p for p in parts if p.bounds[1][2] - p.bounds[0][2] > 17][0]
    plate = [p for p in parts if p is not block][0]
    exp = [(float(c),) for c in a.clear.split(",")]
    analyse("old coupon", plate, block, exp, False)
else:
    with tempfile.TemporaryDirectory() as d:
        M = {}
        for part in ("plain", "ribs", "block"):
            out = os.path.join(d, part + ".stl")
            scad(["-D", f'PART="{part}"', "calibration_coupon.scad"], out)
            M[part] = trimesh.load(out)
            mesh_health(part, M[part])
            chk(f"{part}: one body", len(bodies(M[part])) == 1)
    analyse("plain", M["plain"], M["block"], [(c,) for c in (0.30, 0.25, 0.20, 0.15, 0.10)], False)
    analyse("ribs", M["ribs"], M["block"], [(0.30, x) for x in (0.0, 0.05, 0.10, 0.15, 0.20)], True)

print("ALL PASS" if ok else "FAILED")
sys.exit(0 if ok else 1)
