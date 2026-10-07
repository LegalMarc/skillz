#!/usr/bin/env python3
"""D59 gate: both side faces carry the same two joining SLOTS (there is no male rail), measured on the mesh.

D58's version of this probe measured the male rail against the neighbour's groove. D59 postponed joining: the
body has two dovetail slots on each side face and a future, separately printed spring clip (a double-dovetail
key) joins two units. What the clip needs from the body, checked here on the real mesh:

  1. Each slot (right face, left face; rail 1 and rail 2) is rail_groove_2d() at many heights and 8 depths: the
     void's y bounds at x = face -/+ depth equal the profile (root/2 + rail_clear growing to tip/2 + rail_clear
     over rail_out, then straight to the floor at rail_out + rail_depth_clear) within 0.01 mm, centred on the
     rail's y; the floor depth is right; the slot floor is z = rail_z0 (solid at rail_z0 - 0.1, void at +0.1).
  2. The left slots are the mirror images of the right slots about the module's mid-plane: bounds agree to 0.002.
  3. Each slot is open through the top: no solid anywhere in its column from rail_z0 up to the top of the body.
  4. The body has no male rail: nothing stands outside x = 0 .. module_w.
  5. Ganged pair (a copy at +module_w, faces touching): at each height the two facing slots form a bowtie cavity
     about the shared plane, mirror-symmetric, the same y centre for both bodies and both rails; and a
     double-dovetail key (two male trapezoids base to base on the plane) fits it with rail_clear on every flank
     (the key shifted +-(rail_clear - 0.01) in y stays inside the cavity).

    source ~/.local/opt/openscad/env.sh
    python3 probes/gang_fit.py
"""
import sys, warnings
import numpy as np
from shapely.geometry import LineString, Polygon, box
from shapely.ops import unary_union
from shapely.affinity import translate
from _common import params, parts, moved, translation

warnings.filterwarnings("ignore")
P = params(); body = parts(("body",))["body"]
mw, rc, z0 = P["module_w"], P["rail_clear"], P["rail_z0"]
rw, tw, ro, rdc = P["rail_root_w"], P["rail_tip_w"], P["rail_out"], P["rail_depth_clear"]
ok = True
TOL = 0.01


def chk(label, cond, extra=""):
    global ok
    ok &= bool(cond)
    print(("PASS  " if cond else "FAIL  ") + label + (("  " + extra) if extra else ""))


def union_at(mesh, z):
    s = mesh.section(plane_origin=[0, 0, z], plane_normal=[0, 0, 1])
    p, _ = s.to_2D(to_2D=translation([0, 0, -z]))
    return unary_union(list(p.polygons_full))


def half_w(d):
    """expected half-width of the slot at depth d from the face (rail_groove_2d)"""
    return rw / 2 + rc + (tw - rw) / 2 * min(d, ro) / ro


def void_bounds(solid, x, yc):
    """y interval of the void on the line x = const that contains yc (None if solid there)"""
    ln = LineString([(x, yc - 6), (x, yc + 6)])
    free = ln.difference(solid)
    for g in getattr(free, "geoms", [free]):
        if not g.is_empty and g.bounds[1] <= yc <= g.bounds[3]:
            return g.bounds[1], g.bounds[3]
    return None


depths = (0.02, 0.5, 1.0, 1.5, 2.0, 2.5, 2.98, 3.2, 3.38)
# rail 1 breaks out through the sloped plane (countersink above z ~ 91): sample below it; rail 2 to near the rim
rails = (("rail 1", P["rail1_y"], P["rail1_soc_z1"], np.linspace(z0 + 1, 88, 24)),
         ("rail 2", P["rail2_y"], P["rail2_soc_z1"], np.linspace(z0 + 1, 184, 24)))
worst = 0.0; worst_mirror = 0.0
for name, yc, zt, zs in rails:
    for z in zs:
        S = union_at(body, float(z))
        for d in depths:
            br = void_bounds(S, mw - d, yc); bl = void_bounds(S, d, yc)
            if br is None or bl is None:
                chk(f"{name} z {z:.1f} depth {d}: void present on both faces", False); continue
            h = half_w(d)
            e = max(abs(br[0] - (yc - h)), abs(br[1] - (yc + h)), abs(bl[0] - (yc - h)), abs(bl[1] - (yc + h)))
            worst = max(worst, e)
            worst_mirror = max(worst_mirror, abs(br[0] - bl[0]), abs(br[1] - bl[1]))
chk("both faces, both rails, 24 heights x 9 depths each: every slot flank equals rail_groove_2d (centred on its rail y)",
    worst < TOL, f"(worst error {worst:.4f} mm over {2 * 2 * 24 * len(depths)} flank pairs)")
chk("left slots are the mirror images of the right slots about x = module_w / 2",
    worst_mirror < 0.002, f"(worst difference {worst_mirror:.5f} mm)")

for name, yc, zt, zs in rails:
    S = union_at(body, float(zs[len(zs) // 2]))
    # floor depth: along y = yc the void ends at the groove floor on each face
    fr = LineString([(mw - 5, yc), (mw + 0.5, yc)]).difference(S)
    fl = LineString([(-0.5, yc), (5, yc)]).difference(S)
    fr_x = min(g.bounds[0] for g in getattr(fr, "geoms", [fr]) if not g.is_empty and g.bounds[2] >= mw - 1e-6) if not fr.is_empty else None
    fl_x = max(g.bounds[2] for g in getattr(fl, "geoms", [fl]) if not g.is_empty and g.bounds[0] <= 1e-6) if not fl.is_empty else None
    want = ro + rdc
    chk(f"{name}: slot floor at depth {want:.2f} on both faces",
        fr_x is not None and fl_x is not None and abs((mw - fr_x) - want) < TOL and abs(fl_x - want) < TOL,
        f"(right {None if fr_x is None else mw - fr_x:.3f}, left {fl_x})")
    # blind floor and open top, along the slot's centre column at mid-depth on each face
    for face, x in (("right", mw - 1.5), ("left", 1.5)):
        zs_col = np.arange(z0 + 0.1, 190.0, 0.25)
        inside = body.contains(np.c_[np.full_like(zs_col, x), np.full_like(zs_col, yc), zs_col])
        chk(f"{name}, {face} face: no solid in the slot column from z {z0 + 0.1:g} to 190 (open through the top)", not inside.any(),
            f"({int(inside.sum())} solid samples)")
        below = body.contains([[x, yc, z0 - 0.1], [x, yc, z0 - 2.0]])
        chk(f"{name}, {face} face: the slot floor is blind at z = {z0:g} (solid just below)", bool(below.all()))
        chk(f"{name}, {face} face: slot is entered from above (void at z = {z0 + 0.1:g})",
            not body.contains([[x, yc, z0 + 0.1]])[0])

lo, hi = body.bounds
chk("no male rail: the body spans exactly x 0 .. module_w", abs(lo[0]) < 1e-3 and abs(hi[0] - mw) < 1e-3, f"(x {lo[0]:.3f} .. {hi[0]:.3f})")

# the ganged pair: a copy at +module_w, faces touching
neighbour = moved(body, translation([mw, 0, 0]))
key_half = lambda sign, yc: Polygon([(mw, yc - rw / 2), (mw, yc + rw / 2), (mw + sign * ro, yc + tw / 2), (mw + sign * ro, yc - tw / 2)])
sym = 0.0; gap_ok = True; worst_fit = 1e9
for name, yc, zt, zs in rails:
    for z in zs[::3]:
        A, B = union_at(body, float(z)), union_at(neighbour, float(z))
        U = unary_union([A, B])
        win = box(mw - 3.6, yc - 6, mw + 3.6, yc + 6)
        cav = win.difference(U)
        # the cavity component holding the pair's plane
        parts_ = [g for g in getattr(cav, "geoms", [cav]) if g.contains(Polygon([(mw - .01, yc - .01), (mw + .01, yc - .01), (mw + .01, yc + .01), (mw - .01, yc + .01)]))]
        if not parts_:
            chk(f"{name} z {z:.1f}: the pair has a cavity at the plane", False); gap_ok = False; continue
        cav = parts_[0]
        mirror = Polygon([(2 * mw - x, y) for x, y in cav.exterior.coords])
        sym = max(sym, cav.symmetric_difference(mirror).area)
        key = unary_union([key_half(+1, yc), key_half(-1, yc)])
        # the flank gap is rail_clear measured ALONG y (the groove is the male offset by rail_clear in y, D57), so the key
        # shifted by +-(rail_clear - TOL) in y must still lie inside the cavity (the slot floor is a further 0.4 away in x)
        grown = unary_union([translate(key, 0, rc - TOL), translate(key, 0, -(rc - TOL))])
        worst_fit = min(worst_fit, 1.0 - grown.difference(cav).area / max(grown.area, 1e-9))
        # centred: both facing slots share the rail's y (cavity bounds symmetric about yc at the plane)
        ys = LineString([(mw, yc - 6), (mw, yc + 6)]).intersection(cav).bounds
        gap_ok &= abs((ys[1] + ys[3]) / 2 - yc) < 1e-3
chk("ganged pair: the facing slots form a bowtie cavity, mirror-symmetric about the shared plane at every sampled height",
    sym < 1e-3, f"(worst asymmetry {sym:.5f} mm2)")
chk("ganged pair: the cavity is centred on each rail's y (both bodies, both rails)", gap_ok)
chk(f"ganged pair: a double-dovetail key (two male trapezoids base to base) fits the cavity with rail_clear of y play per flank (checked at rail_clear - {TOL})",
    worst_fit > 1 - 1e-6, f"(worst covered fraction {worst_fit:.6f})")
print("ALL PASS" if ok else "FAILED")
sys.exit(0 if ok else 1)
