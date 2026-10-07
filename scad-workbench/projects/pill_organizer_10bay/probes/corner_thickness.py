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
TIP = 0.2         # mm2: the 70 degree lip tips of the dovetail (0.48 mm2, the same at every height) are below this
THIN_SKIN = 2.35    # the skin is 2.4: nothing thinner may stand in the break-out zone
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


def breakout_scan(mesh, mw, rail1_y, zlo, zhi, side="right", step=0.25, thin=None):
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
        t_ = THIN_SKIN if thin is None else thin
        thin_ = full.difference(full.buffer(-t_ / 2).buffer(t_ / 2)).intersection(win)
        for g in getattr(thin_, "geoms", [thin_]):
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
    ok = True
    # D59: both side faces carry the same two slots. Every check below reads the RIGHT face, so the left
    # face is checked by mirroring the mesh about the module's mid-plane and running the same code.
    views = [("right face", mesh)]
    if P is not None:
        v = mesh.vertices.copy(); v[:, 0] = mw - v[:, 0]
        mir = trimesh.Trimesh(v, mesh.faces[:, ::-1], process=False)      # mirroring flips the winding; flip it back
        views.append(("left face (mirrored about x = module_w / 2)", mir))
    for vname, mesh in views:
        print("\n########## " + vname + " ##########")
        print(f"module_w {mw}; slices every 2 mm, thin = under {THIN} mm, window = right 26 mm x front 45 mm")
        rows = run(mesh, mw, zmax)
        print(" z      thin regions  total mm2  largest mm2   regions over %.0f mm2 (x, y, area)" % SLIVER)
        for r in rows:
            print(f" {r[0]:5.1f}  {r[1]:4d}      {r[2]:8.1f}  {r[3]:8.1f}     {r[4]}")
        worst = max((r[3] for r in rows), default=0)
        print(f"\nlargest thin region in any slice: {worst:.1f} mm2   (flap if it persists over {SLIVER} mm2)")
        if P is not None:
            zp = lambda y: P["trayA_rim"] + y * (P["trayB_rim"] - P["trayA_rim"]) / P["yB_tray1"]
            y1 = P["rail1_y"]
            zlo, zhi = zp(y1 - 15) - 8, zp(y1 + 15) + 3
            for side in ("right",):      # D59: the left face is this same code on the mirrored mesh (see the views loop)
                th = breakout_scan(mesh, mw, y1, zlo, zhi, side)
                # Thin regions of the whole slice (opening radius THIN_SKIN/2: nothing thinner than the
                # skin survives it), clipped to the zone. Every region must be one of these named features;
                # anything else FAILS. (1) the convex plan corners of the buttress and wall, which an
                # opening always shaves to r^2 (1 - pi/4) = 0.30 mm2 per 90 degree corner, wherever they
                # are cut by the sloped plane; (2) the dovetail lips' 70 degree wedge tips at the outer
                # face, 0.64 mm2 and below, the same at every height; (3) where the 1 mm bevel and the
                # sloped plane run out across one of those wedge tips: within 2.5 mm of the outer face,
                # at most 5 mm2 and 1.5 mm tall. Nothing else may be thin.
                unnamed = []
                for z, x, y, a_ in th:
                    # D60: 0.45, not 0.31. F9 rounds the buttress's inboard edges, which retriangulates the sloped
                    # top; the same 90 degree corner then slices (mirrored mesh, z 102, y 27 to 28) as 0.38 to 0.39
                    # mm2. The opening shaves r^2 (cot(t/2) - (pi - t)/2) from a corner of plan angle t (r =
                    # THIN_SKIN / 2): 0.30 at 90 degrees, 0.44 at 80. A flap is over 4 mm2 and is still caught.
                    corner = a_ <= 0.45
                    lip_tip = a_ <= 0.70 and ((side == "right" and x >= mw - 0.8) or (side == "left" and x <= -2.0))
                    runout = a_ <= 5.0 and ((side == "right" and x >= mw - 2.5) or (side == "left" and x <= -2.0))
                    # (4) a horizontal slice GRAZING a bevel: the 45 degree bevel measured in the plane's own
                    # frame is 2.4 degrees from horizontal in the body (the plane rises 0.96 per mm, the
                    # bevel falls 1 per mm), so a slice within a millimetre of its height shows the
                    # lip's end as a sliver although the lip under it is solid: the front lip's bevel near the groove,
                    # and the buttress's back-top bevel.
                    gf = (side == "right" and zp(y1 - P["rail_tip_w"] / 2 - P["rail_clear"]) - P["groove_chamfer"] - 1.5 <= z
                          <= zp(y1 - P["rail_root_w"] / 2 - P["rail_clear"]) and y1 - P["rail_tip_w"] / 2 - 2.5 <= y <= y1)
                    gb = (side == "right" and zp(y1 + P["rail_boss_w"] / 2) - 0.2 - P["boss_bevel"] - 1.5 <= z
                          <= zp(y1 + P["rail_boss_w"] / 2) and y >= y1 + P["rail_boss_w"] / 2 - 3.0)
                    if not (corner or lip_tip or runout or gf or gb):
                        unnamed.append((z, x, y, a_))
                print(f"\nbreak-out zone, {side} side, horizontal slices every 0.25 mm from z {zlo:.0f} to "
                      f"{zhi:.0f}, thin = under {THIN_SKIN:.2f} mm: "
                      f"{len(th)} thin regions of >= {TIP} mm2; {len(unnamed)} are none of the named features")
                if unnamed:
                    print("      unnamed:", unnamed[:12])
                okh = not unnamed
                ok &= okh
                print(("PASS  " if okh else "FAIL  ") + f"every thin region (under the skin's thickness) in the {side} break-out zone is a named feature")
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
            # convex edges of the real mesh in the zone, by interior angle
            adj_ang = mesh.face_adjacency_angles; conv = mesh.face_adjacency_convex
            ed = mesh.vertices[mesh.face_adjacency_edges]; mid = ed.mean(1); elen = np.linalg.norm(ed[:, 0] - ed[:, 1], axis=1)
            interior = 180.0 - np.degrees(adj_ang)
            zone_r = (mid[:, 0] > mw - 12) & (mid[:, 1] > y1 - 15) & (mid[:, 1] < y1 + 15) & (mid[:, 2] > zp(y1 - 15) - 8)
            for name, zone in (("right", zone_r),):
                sh = conv & (interior < 60.0) & (elen > 0.5) & zone
                allsharp = conv & (interior < 80.0) & zone
                print(f"\n{name} break-out zone: {int(allsharp.sum())} convex edges under 80 degrees ("
                      f"{[(int(round(i)), round(float(l), 2)) for i, l in zip(interior[allsharp], elen[allsharp])]} deg, mm); "
                      f"{int(sh.sum())} under 60 degrees and over 0.5 mm long")
                okk = not sh.any()
                globals()["ok"] = ok and okk
                print(("PASS  " if okk else "FAIL  ") + f"no knife edge (interior angle under 60 degrees, over 0.5 mm long) in the {name} break-out zone")
            # the divider / front wall joint in tray A (revision 11): the vertical fillet exists
            # and the joint is at least a divider thick along its diagonal at every height
            bx0 = P["wall_out"] + 1 * (P["bay_w"] + P["wall_div"])          # bay 2's left face
            r_f = P["tray_fillet_r"]; y0 = P["yA_tray0"]
            diag = []
            for z in (12.0, 25.0, 40.0, 50.0):
                c = np.array([bx0 + r_f, y0 + r_f, z]) / 1.0
                p_in = np.array([bx0 + r_f - r_f / np.sqrt(2) + 0.15, y0 + r_f - r_f / np.sqrt(2) + 0.15, z])   # just inside the arc
                p_out = np.array([bx0 + r_f - r_f / np.sqrt(2) - 0.15, y0 + r_f - r_f / np.sqrt(2) - 0.15, z])  # just outside it, in the void
                d = run_len(mesh, [bx0 + r_f - 1.2 * r_f, y0 + r_f - 1.2 * r_f, z], [bx0 - 4.0, y0 - 2.8 - 1.0, z], step=0.02)
                diag.append((z, bool(mesh.contains([p_out])[0]) , d[0][1] if d else 0.0))
            print("  divider / front wall joint, bay 2's left divider: (z, solid at the fillet's arc, solid run along the diagonal mm):", diag)
            from skin_free_height import measure as skin_measure
            worst_free, skin_t = skin_measure(mesh, P, verbose=True)
            def chk(label, cond):
                global ok
                ok &= bool(cond); print(("PASS  " if cond else "FAIL  ") + label)
            print()
            chk(f"skin behind the groove is >= a divider ({P['wall_div']}) at every height (min {min(skins):.2f})", min(skins) >= P["wall_div"] - 1e-6)
            chk(f"buttress on either side of the groove is >= a divider + 1 mm (min {min(fb):.2f})", min(fb) >= P["wall_div"] + 1.0 - 1e-6)
            chk("the divider / front wall joint is filleted and over a divider thick along its diagonal at every height",
                all(d[1] for d in diag) and min(d[2] for d in diag) >= P["wall_div"])
            chk(f"the skin stands at most 1 x its thickness above the front lip beside the groove (worst {worst_free:.2f} mm of {skin_t})", worst_free <= skin_t + 0.05)
            chk(f"stop block reaches back to y {P['stop_back_y']:.1f} at z=62 (run {r[0][1]:.2f})", r[0][1] >= P["stop_back_y"] - 0.1)
            chk(f"material behind the contact face along the slope is >= 1.5 mm (min {min(q[1] for q in r3):.2f})", min(q[1] for q in r3) >= 1.5)
            chk("front wall and side wall run unbroken across the pillar in X (no gap)", r2[0][1] >= wo + P["pillar_w"] - 0.5)
    sys.exit(0 if ok else 1)
