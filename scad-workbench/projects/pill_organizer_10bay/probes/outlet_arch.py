#!/usr/bin/env python3
"""D52 / D54 probe: the two outlet openings are half octagons, and a capsule can still leave.

For bay 0 and the last bay, one ray straight up the middle of each opening's wall (the tray A
mouth under the wall between the trays, outlet B under hopper B's front wall) at a run of
distances from the left divider reads the opening's ceiling off the real body mesh.

  * the ceiling at the bay centre is outletA_top / outletB_top (the centre throat did not move)
  * the crown flat is the declared outletX_crown_flat (+-0.5): A 10, B 20 (D54)
  * the facets climb at 45 degrees (+-1.5) and the ceiling at the divider face is crown - chamfer
  * left and right facets mirror
  * worst pose (D54): a 26 x 11 spherocylinder lying on the 40 degree ramp under the wall's
    back-bottom edge, swept over every position across the bay and orientations 0..90 degrees,
    must clear the throat measured from the MESH ceiling (the project's throat formula: vertical
    opening less wall_div x tan(40), times cos(40)) with a margin of at least +1.0 mm. The reviewer
    of revision 13 found -2.47 mm on outlet B at a 10 mm crown with this sweep.

    python3 probes/outlet_arch.py
"""
import sys
import numpy as np
from _common import params, parts

P = params()
body = parts(("body",))["body"]
ok = True


def chk(label, cond):
    global ok
    ok &= bool(cond)
    print(("PASS  " if cond else "FAIL  ") + label)


w0 = P["wall_out"]; bw = P["bay_w"]; wd = P["wall_div"]
t40 = np.tan(np.radians(P["ramp_deg"])); c40 = np.cos(np.radians(P["ramp_deg"]))
L, D = P["pill_len"], P["pill_dia"]; R = D / 2; half_cyl = (L - D) / 2
MARGIN = 1.0


def ceiling(x, y, z_start):
    hits, _, _ = body.ray.intersects_location([[x, y, z_start]], [[0, 0, 1]], multiple_hits=False)
    return hits[0][2]


def worst_pose_margin(xs, open_h_x):
    """min over positions and orientations of (throat - capsule height) over the capsule's footprint."""
    throat = (open_h_x - wd * t40) * c40
    worst = 1e9
    for deg in range(0, 91, 5):
        hx = half_cyl * abs(np.cos(np.radians(deg))); hw = hx + R
        for x0 in np.arange(hw, bw - hw + 1e-9, 0.25):
            sel = (xs >= x0 - hw) & (xs <= x0 + hw)
            g = np.maximum(0, np.abs(xs[sel] - x0) - hx)
            H = R + np.sqrt(np.maximum(0, R * R - g * g))
            worst = min(worst, float(np.min(throat[sel] - H)))
    return worst


openings = (("tray A mouth", (P["yA_tray1"] + P["yA_wall1"]) / 2, P["outletA_top"], P["chute_clear"], P["outletA_crown_flat"], P["outletA_chamfer"]),
            ("outlet B", (P["yB_tray1"] + P["yB_wall1"]) / 2, P["outletB_top"], P["outlet_h"], P["outletB_crown_flat"], P["outletB_chamfer"]))
for name, y, top, open_h, crown, c in openings:
    print(f"\n{name}: crown at z {top:.2f}, flat {crown:.1f}, facet run/rise {c:.2f}, opening {open_h:.1f}")
    for bay_x0 in (w0, w0 + 4 * (bw + wd)):
        xs = np.arange(0.05, bw, 0.05)
        zc = np.array([ceiling(bay_x0 + d, y, top - open_h + 3) for d in xs])
        at = lambda d: zc[int(round((d - 0.05) / 0.05))]
        print(f"  bay at x={bay_x0:.1f}: " + "  ".join(f"{d:.1f}:{at(d):.2f}" for d in (0.3, 2.0, 5.5, 8.0, 12.0, c, bw / 2, bw - 5.5, bw - 0.3)))
        chk(f"{name}: the ceiling at the bay centre is {top:.2f} (got {at(bw / 2):.2f}, within 0.06)", abs(at(bw / 2) - top) < 0.06)
        flat_d = xs[np.abs(zc - top) < 0.15]
        flat = flat_d.max() - flat_d.min()
        chk(f"{name}: the crown flat is {flat:.1f} mm (declared {crown:.1f} +-0.5)", abs(flat - crown) <= 0.5)
        k = (at(c * 0.8) - at(c * 0.3)) / (c * 0.5)
        chk(f"{name}: the left facet climbs at {np.degrees(np.arctan(k)):.1f} degrees (45 +- 1.5)", abs(np.degrees(np.arctan(k)) - 45) < 1.5)
        chk(f"{name}: the ceiling at the divider face is crown - {c:.2f} ({at(0.3):.2f} against {top - c + 0.3:.2f})", abs(at(0.3) - (top - c + 0.3)) < 0.1)
        chk(f"{name}: left and right facets mirror (8 mm in: {at(8.0):.2f} / {at(bw - 8):.2f})", abs(at(8.0) - at(bw - 8)) < 0.06)
        m = worst_pose_margin(xs, open_h - (top - zc))
        chk(f"{name}: worst capsule pose clears the throat by {m:+.2f} mm (>= +{MARGIN:.1f})", m >= MARGIN)

print("\n" + ("RESULT: ALL PASS" if ok else "RESULT: FAILURES"))
sys.exit(0 if ok else 1)
