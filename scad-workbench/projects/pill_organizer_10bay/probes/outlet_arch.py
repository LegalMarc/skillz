#!/usr/bin/env python3
"""D52 probe: the two outlet openings are half octagons.

For bay 0 (and the last bay), walk z up through the real body at the middle of each opening's wall
(the tray A mouth under the wall between the trays, outlet B under hopper B's front wall) at a run
of distances from the left divider, and read the ceiling of the opening. Reports and checks:

  * the ceiling at the bay centre is outletA_top / outletB_top (the throat there did not move)
  * the crown flat (where the ceiling is within 0.15 mm of the crown) is <= 10.5 mm
  * the facets climb at 45 degrees (+-1.5) from the divider to the crown
  * the ceiling at the divider face is the crown less outlet_chamfer
  * mirror symmetry about the bay centre

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


w0 = P["wall_out"]; bw = P["bay_w"]; c = P["outlet_chamfer"]


def ceiling(x, y, z_lo, z_hi, step=None):
    """First solid above a point known to be in the opening: one ray straight up."""
    hits, _, _ = body.ray.intersects_location([[x, y, z_lo]], [[0, 0, 1]], multiple_hits=False)
    return hits[0][2] if len(hits) else z_hi


for name, y, top in (("tray A mouth", (P["yA_tray1"] + P["yA_wall1"]) / 2, P["outletA_top"]),
                     ("outlet B", (P["yB_tray1"] + P["yB_wall1"]) / 2, P["outletB_top"])):
    print(f"\n{name}: crown at z {top:.2f}, facet run/rise {c:.2f}, flat {P['outlet_crown_flat']:.1f}")
    for bay_x0 in (w0, w0 + 4 * (bw + P["wall_div"])):
        ds = [0.3, 2.0, 5.5, 8.0, 12.0, 16.0, c, c + 2, bw / 2, bw - c - 2, bw - c, bw - 16, bw - 8, bw - 2, bw - 0.3]
        zc = [ceiling(bay_x0 + d, y, top - 20, top + 3) for d in ds]
        zc_ = dict(zip(ds, zc))
        print("  bay at x=%.1f: " % bay_x0 + "  ".join(f"{d:.1f}:{z:.2f}" for d, z in zip(ds, zc)))
        centre = zc_[bw / 2]
        chk(f"{name}: the ceiling at the bay centre is {top:.2f} (got {centre:.2f}, within 0.06)", abs(centre - top) < 0.06)
        flat_ds = np.array([d for d in np.arange(0.3, bw - 0.3, 0.25) if abs(ceiling(bay_x0 + d, y, top - 20, top + 3) - top) < 0.15])
        flat = flat_ds.max() - flat_ds.min() if len(flat_ds) else 0.0
        chk(f"{name}: the crown flat is {flat:.1f} mm (<= 10.5)", 0 < flat <= 10.5)
        slope = (zc_[12.0] - zc_[5.5]) / (12.0 - 5.5)
        chk(f"{name}: the left facet climbs at {np.degrees(np.arctan(slope)):.1f} degrees (45 +- 1.5)", abs(np.degrees(np.arctan(slope)) - 45) < 1.5)
        chk(f"{name}: the ceiling at the divider face is crown - {c:.2f} ({zc_[0.3]:.2f} against {top - c + 0.3:.2f})", abs(zc_[0.3] - (top - c + 0.3)) < 0.1)
        chk(f"{name}: left and right facets mirror (8 mm in: {zc_[8.0]:.2f} / {zc_[bw - 8]:.2f})", abs(zc_[8.0] - zc_[bw - 8]) < 0.06)

print("\n" + ("RESULT: ALL PASS" if ok else "RESULT: FAILURES"))
sys.exit(0 if ok else 1)
