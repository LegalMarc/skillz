#!/usr/bin/env python3
"""Per-bay capacity, measured from the real body mesh.

Row A (front tray, crossing chute, back hopper) and row B (back tray, front
hopper) of one bay, with the fill line at the lid: the pick plane over the trays
(the pick lid's underside) and fill_seat_z over the hoppers. Method: the bay's
inner box minus the body gives every void in it; the part of that under the fill
line is cut out and split into connected components; the components holding a
point in tray A and a point in tray B are the two rows.

    python3 probes/capacity.py [bay_index]      # default: the middle bay, 2
"""
import sys
import numpy as np
import trimesh
from shapely.geometry import Polygon
from _common import params, parts

P = params()
body = parts(("body",))["body"]
k = int(sys.argv[1]) if len(sys.argv) > 1 else 2
bw, wd, wo = P["bay_w"], P["wall_div"], 2.8
x0 = wo + k * (bw + wd)
mod_d = P["module_d_top"]
# fill region: a prism in (y, z) extruded across the bay
rimA, rimB, yB1 = P["trayA_rim"], P["trayB_rim"], P["yB_tray1"]
plane = lambda y: rimA + y / yB1 * (rimB - rimA)
# the seat recess (0.2 deep) joins the two hoppers right at fill_seat_z, so the fill
# line is taken 0.3 under it: under 0.1 mL per bay of difference
fz = P["fill_seat_z"] - 0.3
poly = Polygon([(0, 0), (mod_d, 0), (mod_d, fz), (yB1, fz), (yB1, plane(yB1)), (0, plane(0))])
region = trimesh.creation.extrude_polygon(poly, bw)           # extruded along +z; remap to x
V = np.array(region.vertices)
region.vertices = np.c_[V[:, 2] + x0, V[:, 0], V[:, 1]]       # (x, y, z) = (extrusion, poly x, poly y)
region.invert() if region.volume < 0 else None
# the box is the bay's own footprint, floor to fill line, front face to back face:
# the faces it shares with the outside close the tray A scallop and the cubby mouth
box = trimesh.creation.box(extents=[bw, mod_d, fz])
box.apply_translation([x0 + bw / 2, mod_d / 2, fz / 2])
cav = trimesh.boolean.difference([box, body], engine="manifold")
cav = trimesh.boolean.intersection([cav, region], engine="manifold")
parts_ = cav.split(only_watertight=False)
xc = x0 + bw / 2
probe = {}
# a point surely inside tray A's void (above the tilted floor), and one in tray B
probe["A"] = [xc, P["yA_tray0"] + 6, 3 + 6 * np.tan(np.radians(35)) + 5]
probe["B"] = [xc, P["yB_tray0"] + 8, P["trayB_floor"] + 10]
res = {}
for name, pt in probe.items():
    hit = [c for c in parts_ if c.contains([pt])[0]]
    res[name] = hit[0].volume / 1000 if hit else float("nan")
print(f"bay {k} (x {x0:.1f} .. {x0 + bw:.1f}): row A {res['A']:.1f} mL, row B {res['B']:.1f} mL"
      f"   (charge {P['charge_ml']:.1f} mL: A {res['A'] / P['charge_ml']:.2f}x, B {res['B'] / P['charge_ml']:.2f}x)")
for c in sorted(parts_, key=lambda c: -c.volume)[:5]:
    print(f"  component {c.volume / 1000:7.1f} mL   y {c.bounds[0][1]:6.1f} .. {c.bounds[1][1]:6.1f}   z {c.bounds[0][2]:6.1f} .. {c.bounds[1][2]:6.1f}")
