#!/usr/bin/env python3
"""D48 probe: the edge pass is in the real meshes.

Point-in-solid tests on the three parts, each a pair: a point that the treatment must
have REMOVED is outside the mesh, and a point 0.1 mm further in (still on the nominal
body) is inside. They are placed from params.scad, so a change of radius moves them.
Also measures: the body's bed face against the first full layer (the elephant-foot
chamfer), and that every part is one watertight body.

    python3 probes/edge_pass.py
"""
import sys
import numpy as np
import trimesh
from _common import params, parts

P = params()
M = parts(("body", "pick_lid", "fill_lid"))
body, pick, fill = M["body"], M["pick_lid"], M["fill_lid"]
ok = True


def chk(label, cond):
    global ok
    ok &= bool(cond)
    print(("PASS  " if cond else "FAIL  ") + label)


def removed(mesh, gone, kept, label):
    g = mesh.contains([gone])[0]
    k = mesh.contains([kept])[0]
    chk(f"{label}: {np.round(gone, 2).tolist()} is cut away, {np.round(kept, 2).tolist()} stays", (not g) and k)


for n, m in M.items():
    chk(f"{n} is one watertight body ({len(m.faces)} triangles)", m.is_watertight and len(m.split(only_watertight=False)) == 1)

mw, wo, r = P["module_w"], P["wall_out"], P["edge_r_top"]
c45 = lambda c, depth: c - depth        # inside a 45 degree chamfer of leg c, at 'depth' in from the face

print("\nbody")
bc = P["bed_chamfer"]
# bed chamfer: at z = 0.1 the footprint is inset by bc - 0.1 on every side
removed(body, [bc - 0.1 - 0.1, 100, 0.1], [bc - 0.1 + 0.1, 100, 0.1], "bed chamfer, left face")
removed(body, [mw - (bc - 0.1) + 0.1, 100, 0.1], [mw - (bc - 0.1) - 0.1, 100, 0.1], "bed chamfer, right face")
removed(body, [100, bc - 0.1 - 0.1, 0.1], [100, bc - 0.1 + 0.1, 0.1], "bed chamfer, front face")
removed(body, [100, P["module_d"] - (bc - 0.1) + 0.1, 0.1], [100, P["module_d"] - (bc - 0.1) - 0.1, 0.1], "bed chamfer, back face")
def width(z):
    b = body.section(plane_origin=[0, 0, z], plane_normal=[0, 0, 1]).bounds
    return b[1][0] - b[0][0], b[1][1] - b[0][1]
w0, w1 = width(0.02), width(bc + 0.1)
chk(f"the bed face (z = 0.02) is {2 * (bc - 0.02):.2f} narrower than the first full section in X and Y (measured {w1[0] - w0[0]:.2f}, {w1[1] - w0[1]:.2f})",
    abs(w1[0] - w0[0] - 2 * (bc - 0.02)) < 0.05 and abs(w1[1] - w0[1] - 2 * (bc - 0.02)) < 0.05)
# foot-pad recess mouths: wider on the bed face, by the same 45 degrees
fp = 15.0; fr = 5.0
removed(body, [fp + fr + bc - 0.1 - 0.1, fp, 0.1], [fp + fr + bc - 0.1 + 0.1, fp, 0.1], "foot-pad recess mouth lead-in")

# the side faces' perimeter is rounded (x = 0 face, along the rim and the pick plane)
zr = P["hopper_rim"]
removed(body, [0.04, 190.0, zr - 0.04], [r - 0.2, 190.0, zr - 0.04], "outer round, left face x rim edge")
removed(body, [mw - 0.04, 190.0, zr - 0.04], [mw - r + 0.2, 190.0, zr - 0.04], "outer round, right face x rim edge")
sl = np.tan(np.radians(P["slope"]))
zp = lambda y: P["trayA_rim"] + y * sl
# on the pick plane, 0.04 under it, at x = 0.04 (the plane's normal is (0, -s, 1)/n; 0.04 down is fine at this scale)
removed(body, [0.04, 60.0, zp(60.0) - 0.04], [r - 0.2, 60.0, zp(60.0) - 0.4], "outer round, left face x pick plane")

# the mouth rim
mc = P["mouth_chamfer"]
y0 = P["hop_mouth_y0"]; y1 = P["hop_mouth_y1"]
removed(body, [60.0, y0 - 0.05, zr - 0.05], [60.0, y0 - mc - 0.2, zr - 0.05], "mouth chamfer, front edge")
removed(body, [60.0, y1 + 0.05, zr - 0.05], [60.0, y1 + mc + 0.2, zr - 0.05], "mouth chamfer, back edge")
removed(body, [wo - 0.05, 130.0, zr - 0.05], [wo - mc - 0.2, 130.0, zr - 0.05], "mouth chamfer, left edge")

# the scallop's floor edge
sc = P["scallop_chamfer"]; fh = P["trayA_front_h"]
removed(body, [120.0, 0.1, fh - 0.1], [120.0, 0.1, fh - sc - 0.1], "scallop chamfer, front face")
removed(body, [120.0, wo - 0.1, fh - 0.1], [120.0, wo - 0.1, fh - sc - 0.1], "scallop chamfer, tray side")
chk("the scallop floor itself is still at trayA_front_h in the middle of the wall", body.contains([[120.0, 1.4, fh - 0.05]])[0]
    and not body.contains([[120.0, 1.4, fh + 0.05]])[0])

# the cubby: filleted corners, chamfered mouth
cf = P["cubby_fillet_r"]; cy = P["cubby_y0"]; bt = P["base_t"]
chk(f"cubby floor / front wall corner is filleted (a point in the corner, {0.25} mm from both faces, is solid)",
    body.contains([[120.0, cy + 0.25, bt + 0.25]])[0])
chk("cubby floor / side wall corner is filleted",
    body.contains([[wo + 0.25, 160.0, bt + 0.25]])[0])
cc = P["cubby_chamfer"]; md = P["module_d"]; zl = bt + P["cubby_lip_h"]
removed(body, [wo - 0.05, md - 0.05, 100.0], [wo - cc - 0.3, md - 0.05, 100.0], "cubby mouth chamfer, left side edge")
removed(body, [120.0, md - 0.05, zl - 0.05], [120.0, md - 0.05, zl - cc - 0.3], "cubby mouth chamfer, lip top")

# tray B's front-wall corner fillet
tf = P["tray_fillet_r"]; yb = P["yB_tray0"]; bx = 2.8 + 44.96 + 2.4   # bay 1's left divider face
chk("tray B front wall / divider corner is filleted (a point 0.25 mm from both faces is solid)",
    body.contains([[bx + 0.25, yb + 0.25, P["trayB_floor"] + 10.0]])[0])

print("\npick lid (as modelled: assembled orientation)")
w = P["pick_lid_w"]; zu = lambda y: zp(y) + P["pick_lid_gap"]
sc_ = P["pick_skirt_chamfer"]; ht = P["pick_lid_hook_t"]
removed(pick, [0.1, -ht + 0.1, 60.0], [sc_ + 0.3, -ht + 0.1 + 0.2, 60.0], "skirt outer end edge, left")
removed(pick, [w - 0.1, -ht + 0.1, 60.0], [w - sc_ - 0.3, -ht + 0.1 + 0.2, 60.0], "skirt outer end edge, right")
uc = P["pick_under_chamfer"]
removed(pick, [0.05, 40.0, zu(40.0) + 0.05], [uc + 0.3, 40.0, zu(40.0) + 0.05], "plate underside x-end edge, left")
removed(pick, [w - 0.05, 40.0, zu(40.0) + 0.05], [w - uc - 0.3, 40.0, zu(40.0) + 0.05], "plate underside x-end edge, right")
chk("the plate's end face keeps over 1 mm of flat between its two chamfers", P["lid_t"] - 1.0 - uc >= 1.0)

print("\nfill lid (as modelled: plate top up)")
fc = P["fill_lip_chamfer"]
sl_ = fill.section(plane_origin=[0, 0, 1.0], plane_normal=[0, 0, 1])   # above the chamfer: the lip's full width
lip_pts = np.array([v for e in sl_.entities for v in sl_.vertices[e.points]])
lip = lip_pts[lip_pts[:, 1] < -1.0]
lx0, lx1 = lip[:, 0].min(), lip[:, 0].max()
removed(fill, [lx0 - 0.0 + 0.04, -P["fill_lip_len"] / 2, 0.12], [lx0 + fc + 0.3, -P["fill_lip_len"] / 2, 0.12], "lip underside chamfer, left side")
removed(fill, [lx1 - 0.04, -P["fill_lip_len"] / 2, 0.12], [lx1 - fc - 0.3, -P["fill_lip_len"] / 2, 0.12], "lip underside chamfer, right side")
removed(fill, [(lx0 + lx1) / 2, -P["fill_lip_len"] + 0.04, 0.12], [(lx0 + lx1) / 2, -P["fill_lip_len"] + fc + 0.3, 0.12], "lip underside chamfer, front")

print("\n" + ("RESULT: ALL PASS" if ok else "RESULT: FAILURES"))
sys.exit(0 if ok else 1)
