#!/usr/bin/env python3
"""D39 probe: how thin is the material around the rail-1 groove's break-out?

Test prints 1 and 2 tore at the corner where the front joining groove breaks out
through the pick plane, and a thin flap inside tray A cracked. This slices the
real body every 2 mm of height through that corner (the right-hand 26 mm of X,
the front 45 mm of Y), and in each slice finds every part of the solid that is
thinner than THIN mm: a morphological opening with radius THIN/2 removes
everything that does, and what the opening removes is what is thin. Slivers
under a few mm2 are the 45-70 degree wedge tips every convex corner has; a
flap shows up as a blob of tens of mm2 that persists up the slices.

    python3 probes/corner_thickness.py              # the current body
    python3 probes/corner_thickness.py old_body.stl 230 # another mesh, with its module_w

Also measures the named features along straight lines with the mesh itself:
the skin behind the groove, the buttress in front of and behind the groove at
its widest, and the pillar.
"""
import sys
import numpy as np
import trimesh
from shapely.geometry import box, Polygon
from shapely.ops import unary_union
from _common import params, parts

THIN = 2.0
TIP = 0.6         # mm2: the 70 degree lip tips of the dovetail (0.48 mm2, the same at every height) are below this
SLIVER = 4.0      # mm2: below this a thin region is a wedge tip, not a flap


def solid_at(mesh, z):
    s = mesh.section(plane_origin=[0, 0, z], plane_normal=[0, 0, 1])
    if s is None:
        return Polygon()
    p2, T = s.to_2D()
    polys = []
    for poly in p2.polygons_full:
        def tr(c):
            c = np.asarray(c)
            h = np.c_[c, np.zeros(len(c)), np.ones(len(c))]
            return [tuple(r[:2]) for r in (T @ h.T).T[:, :3]]
        polys.append(Polygon(tr(poly.exterior.coords), [tr(i.coords) for i in poly.interiors]))
    return unary_union(polys)


def run(mesh, module_w, zmax):
    win = box(module_w - 26, -1, module_w + 1, 45)
    rows = []
    for z in np.arange(6.0, zmax, 2.0):
        sol = solid_at(mesh, float(z)).intersection(win)
        if sol.is_empty:
            continue
        opened = sol.buffer(-THIN / 2).buffer(THIN / 2)
        thin = sol.difference(opened)
        geoms = [g for g in getattr(thin, "geoms", [thin]) if g.area >= 0.3]
        big = [g for g in geoms if g.area >= SLIVER]
        rows.append((z, len(geoms), sum(g.area for g in geoms),
                     max([g.area for g in geoms], default=0.0),
                     [(round(g.centroid.x, 1), round(g.centroid.y, 1), round(g.area, 1)) for g in big]))
    return rows


def breakout_scan(mesh, mw, rail1_y, zlo, zhi, side="right", step=0.25):
    """Fine slices (<= 0.5 mm) through the rail-1 groove's break-out zone: the
    18 mm of Y round the groove, the outer 9-10 mm of X on that side, from the
    plane's height at the buttress front to above the groove's top. Returns the
    thin regions (under THIN mm) of 0.2 mm2 or more, per slice."""
    xs = (mw - 9, mw + 1) if side == "right" else (-6, 9)
    win = box(xs[0], rail1_y - 9, xs[1], rail1_y + 9)
    out = []
    for z in np.arange(zlo, zhi, step):
        full = solid_at(mesh, float(z)).intersection(box(-8, -2, mw + 8, 60))
        if full.is_empty:
            continue
        # thin regions of the WHOLE slice, then clipped to the zone: clipping first
        # would invent thin slivers at the zone's own edges
        thin = full.difference(full.buffer(-THIN / 2).buffer(THIN / 2)).intersection(win)
        for g in getattr(thin, "geoms", [thin]):
            if g.area >= TIP:
                out.append((round(float(z), 2), round(g.centroid.x, 1), round(g.centroid.y, 1), round(g.area, 2)))
    return out


def run_len(mesh, p0, p1, step=0.05):
    """Lengths of the solid runs along p0 -> p1."""
    p0, p1 = np.array(p0, float), np.array(p1, float)
    n = int(np.linalg.norm(p1 - p0) / step)
    pts = p0 + (p1 - p0) * np.linspace(0, 1, n)[:, None]
    inside = mesh.contains(pts)
    runs, start = [], None
    for i, v in enumerate(inside):
        if v and start is None: start = i
        if not v and start is not None:
            runs.append(((p0 + (p1 - p0) * start / n).round(2).tolist(), round((i - start) * np.linalg.norm(p1 - p0) / n, 2))); start = None
    if start is not None:
        runs.append(((p0 + (p1 - p0) * start / n).round(2).tolist(), round((n - start) * np.linalg.norm(p1 - p0) / n, 2)))
    return runs


if __name__ == "__main__":
    if len(sys.argv) > 2:
        mesh = trimesh.load(sys.argv[1]); mw = float(sys.argv[2]); P = None
    else:
        P = params(); mesh = parts(("body",))["body"]; mw = P["module_w"]
    zmax = 108.0 if P is None else P["rail1_soc_z1"] + 2
    print(f"module_w {mw}; slices every 2 mm, thin = under {THIN} mm, window = right 26 mm x front 45 mm")
    rows = run(mesh, mw, zmax)
    print(" z      thin regions  total mm2  largest mm2   regions over %.0f mm2 (x, y, area)" % SLIVER)
    for r in rows:
        print(f" {r[0]:5.1f}  {r[1]:4d}      {r[2]:8.1f}  {r[3]:8.1f}     {r[4]}")
    worst = max((r[3] for r in rows), default=0)
    print(f"\nlargest thin region in any slice: {worst:.1f} mm2   (flap if it persists over {SLIVER} mm2)")
    ok = True
    if P is not None:
        zp = lambda y: P["trayA_rim"] + y * (P["trayB_rim"] - P["trayA_rim"]) / P["yB_tray1"]
        y1 = P["rail1_y"]
        zlo, zhi = zp(y1 - 15) - 8, zp(y1 + 15) + 3
        for side in ("right", "left"):
            # the left face carries the MALE rail, which has no break-out; its tapered lead
            # (the top 3 mm) ends in a small flat and is excluded
            th = breakout_scan(mesh, mw, y1, zlo, zhi if side == "right" else P["rail1_z1"] - 4.0, side)
            # a thin region only counts if it stands: it must recur, within 1 mm of the
            # same place, in MIN_RUN consecutive slices (1 mm of height). A lone slice is
            # where a chamfer's lower corner meets the dovetail lip, 0.5 mm tall, not an edge.
            run, longest, where = {}, 0, None
            for z, x, y, a_ in th:
                key = next((k for k in run if abs(k[0] - x) < 1 and abs(k[1] - y) < 1 and abs(run[k][1] - (z - 0.25)) < 0.01), None)
                n = (run.pop(key)[0] + 1) if key else 1
                run[(x, y)] = (n, z)
                if n > longest: longest, where = n, (z, x, y)
            print(f"\nbreak-out zone, {side} side, slices every 0.25 mm from z {zlo:.0f} to {zhi if side == 'right' else P['rail1_z1'] - 4:.0f}: "
                  f"{len(th)} thin regions of >= {TIP} mm2 (the dovetail lips' own 0.48 mm2 tips are below that); "
                  f"the tallest stands {longest * 0.25:.2f} mm" + (f" (at z, x, y = {where}); all of them: {th}" if th else ""))
            good = longest * 0.25 <= 1.0 - 1e-9
            ok &= good
            print(("PASS  " if good else "FAIL  ") + f"no material under {THIN} mm thick stands over 1 mm tall in the {side} break-out zone")
    if P is not None:
        y = P["rail1_y"]; wo = P["wall_out"]; ro = P["rail_out"]
        print("\nline measurements (solid runs along the line: start point, length mm):")
        skins = []
        for z in (30.0, 60.0, 90.0):
            r = run_len(mesh, [mw - 25, y, z], [mw + 0.5, y, z]); skins.append(r[0][1])
            print(f"  skin, along X at y={y:.1f}, z={z:.0f}: ", r)
        # at the groove's widest (its bottom, x = mw - rail_out) the buttress is what is left either side
        xg = mw - ro - 0.3
        fb = []
        for z in (30.0, 60.0):
            r = run_len(mesh, [xg, 5.0, z], [xg, y + 20, z]); fb += [q[1] for q in r if 8.0 < q[0][1] < y + 10]
            print(f"  buttress either side of the groove, along Y at x={xg:.1f}, z={z:.0f}: ", r)
        xs = mw - wo - 3.0           # inside the right stop block (x 231.2 .. 237.2 less 0.4)
        r = run_len(mesh, [xs, -0.5, 62.0], [xs, 14, 62.0])
        print(f"  stop block + front wall, along Y at x={xs:.1f}, z=62: ", r)
        # the contact zone: 4 mm down the stop face, just in front of it
        sa = np.sin(np.radians(P["slope"])); ca = np.cos(np.radians(P["slope"]))
        zp = lambda y: P["trayA_rim"] + y * (P["trayB_rim"] - P["trayA_rim"]) / P["yB_tray1"]
        y0 = P["stop_y"]
        cy, cz = y0 + 4 * sa, zp(y0) - 4 * ca            # a point on the face, 4 mm down
        r3 = run_len(mesh, [xs, cy - 12 * ca, cz - 12 * sa], [xs, cy + 0.2 * ca, cz + 0.2 * sa], step=0.02)
        print(f"  material behind the contact face, along the slope from the face (x={xs:.1f}): ", r3)
        r2 = run_len(mesh, [mw - 14, 1.4, 62.0], [mw + 0.5, 1.4, 62.0])
        print("  front wall + side wall, along X at y=1.4, z=62: ", r2)
        def chk(label, cond):
            global ok
            ok &= bool(cond); print(("PASS  " if cond else "FAIL  ") + label)
        print()
        chk(f"skin behind the groove is >= 4.0 mm at every height (min {min(skins):.2f})", min(skins) >= 4.0 - 1e-6)
        chk(f"buttress on either side of the groove is >= 5.0 mm (min {min(fb):.2f})", min(fb) >= 5.0 - 1e-6)
        chk(f"stop block reaches back to y {P['stop_back_y']:.1f} at z=62 (run {r[0][1]:.2f})", r[0][1] >= P["stop_back_y"] - 0.1)
        chk(f"material behind the contact face along the slope is >= 1.5 mm (min {min(q[1] for q in r3):.2f})", min(q[1] for q in r3) >= 1.5)
        chk("front wall and side wall run unbroken across the pillar in X (no gap)", r2[0][1] >= wo + P["pillar_w"] - 0.5)
    sys.exit(0 if ok else 1)
