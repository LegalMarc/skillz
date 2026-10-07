#!/usr/bin/env python3
"""K1 probe: how far does the rail-1 groove's skin stand above the lips beside it?

The skin is the wall between the groove's floor and tray A (rail_skin = 2.4 mm). The
pick plane slopes up toward the back, so over the groove's width the skin's top rises
above the FRONT lip's top (the material in front of the groove at the same height).
A free-standing wall taller than a few times its own thickness is what tore on test
prints 1 and 2. This rasterises the real mesh in YZ at several x (the skin, and across
the groove's depth) and reports, for every y over the groove's width, the skin's top
minus the front lip's top.

    python3 probes/skin_free_height.py
"""
import sys
import numpy as np
from _common import params, parts


def top_z(mesh, x, ys, zlo, zhi, step=None):
    """highest solid z at (x, y): a vertical ray from above, the first (highest) hit"""
    ys = np.asarray(ys, float)
    o = np.c_[np.full_like(ys, x), ys, np.full_like(ys, zhi)]
    d = np.tile([0.0, 0.0, -1.0], (len(ys), 1))
    loc, ray, _ = mesh.ray.intersects_location(o, d, multiple_hits=True)
    out = [None] * len(ys)
    for p, r in zip(loc, ray):
        if p[2] >= zlo and (out[r] is None or p[2] > out[r]):
            out[r] = float(p[2])
    return out


def measure(mesh, P, verbose=True):
    mw = P["module_w"]; y1 = P["rail1_y"]
    skin_t = P["rail_skin"]
    tip_half = P["rail_tip_w"] / 2 + P["rail_clear"]
    root_half = P["rail_root_w"] / 2 + P["rail_clear"]
    floor_x = mw - P["rail_out"] - P["rail_depth_clear"]            # groove floor
    x_skin = floor_x - skin_t / 2                                   # middle of the skin
    ys = np.arange(y1 - tip_half - 2.0, y1 + tip_half + 2.0 + 1e-9, 0.2)
    zp = lambda y: P["trayA_rim"] + y * (P["trayB_rim"] - P["trayA_rim"]) / P["yB_tray1"]
    zlo, zhi = zp(y1 - 12) - 6, zp(y1 + 12) + 3
    skin = np.array([t if t is not None else np.nan for t in top_z(mesh, x_skin, ys, zlo, zhi)])
    res = {}
    worst = 0.0
    for label, x in (("groove floor +0.2", floor_x + 0.2), ("mid groove", mw - P["rail_out"] / 2),
                     ("mouth -0.3", mw - 0.3)):
        half = root_half + (tip_half - root_half) * min(mw - x, P["rail_out"]) / P["rail_out"]   # D57: flanks to the rail tip depth, straight below it
        yf = y1 - half                                              # front lip's edge at this depth
        front = top_z(mesh, x, [yf - 0.5], zlo, zhi)[0]             # the front lip's top beside the groove
        gy = ys[(ys > yf + 0.05) & (ys < y1 + half - 0.05)]         # over the groove's width
        sk = skin[(ys > yf + 0.05) & (ys < y1 + half - 0.05)]
        h = np.nanmax(sk) - front
        res[label] = (round(yf, 2), round(front, 2), round(float(np.nanmax(sk)), 2), round(float(h), 2))
        worst = max(worst, h)
    if verbose:
        print(f"skin {skin_t} mm thick, middle at x={x_skin:.1f}; front lip top vs highest skin top over the groove's width:")
        for k, (yf, ft, st, h) in res.items():
            print(f"  at {k:18s}: lip edge y {yf:6.2f}, front lip top z {ft:7.2f}, skin top max z {st:7.2f} -> skin stands {h:5.2f} mm above the lip ({h / skin_t:4.2f} x its thickness)")
    return worst, skin_t


if __name__ == "__main__":
    import trimesh
    P = params(); mesh = parts(("body",))["body"]
    # D59: both side faces carry the slots; the left face is this same measurement on the mesh mirrored
    # about the module's mid-plane (mirroring flips the winding, so the faces are reversed back)
    v = mesh.vertices.copy(); v[:, 0] = P["module_w"] - v[:, 0]
    mirrored = trimesh.Trimesh(v, mesh.faces[:, ::-1], process=False)
    allok = True
    for side, m in (("right", mesh), ("left", mirrored)):
        print(f"-- {side} face")
        worst, t = measure(m, P)
        ok = worst <= 1.0 * t + 0.05
        allok &= ok
        print(("PASS  " if ok else "FAIL  ") + f"{side}: the skin stands at most 1 x its thickness ({t}) above the front lip (worst {worst:.2f} mm = {worst / t:.2f} x)")
    sys.exit(0 if allok else 1)
