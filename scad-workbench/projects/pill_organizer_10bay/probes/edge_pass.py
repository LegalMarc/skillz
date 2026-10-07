#!/usr/bin/env python3
"""D48/D60 probe: the edge pass is in the real meshes.

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
# D60 (F6): the front face takes a scallop_round_r round on the whole scallop outline, not the old 45 degree
# chamfer: 0.1 behind the face the floor has dropped e = r (1 - sin t) with cos t = 1 - 0.1 / r
rr = P["scallop_round_r"]; e1 = rr * (1 - np.sin(np.arccos(1 - 0.1 / rr)))
removed(body, [120.0, 0.1, fh - e1 + 0.05], [120.0, 0.1, fh - e1 - 0.05], f"scallop front round r {rr}, floor edge, 0.1 behind the face")
removed(body, [120.0, 0.02, fh - 0.5], [120.0, 0.02, fh - rr - 0.05], f"scallop front round r {rr}, floor edge, at the face")
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

# ---- D60 final QA pass (F1 to F12) ----
print("\nbody, D60")
bw = P["bay_w"]; wd = P["wall_div"]; dx0 = wo + bw            # divider 1's left face
dz = P["trayA_front_h"] + P["trayA_scallop_r"] + 1.0
# F1/F6: the divider noses are as wide as the divider less 2 x scallop_over (0.05), and rounded on the front face
so = P["scallop_over"]
for yq in (2.0, 3.4):       # in the front wall, and on the tray side where the 0.4 step was
    removed(body, [dx0 + 0.02, yq, 70.0], [dx0 + 0.08, yq, 70.0], f"F1: divider 1's face at z 70, y {yq}, steps only scallop_over ({so}) into the divider")
e2 = rr * (1 - np.sin(np.arccos(1 - 0.1 / rr)))
removed(body, [dx0 + so + e2 - 0.05, 0.1, 70.0], [dx0 + so + e2 + 0.05, 0.1, 70.0], f"F6: divider nose front edge is rounded r {rr} (0.1 behind the face)")
# F2: the corner fillet climbs to the scallop arc, no flat ledge at trayA_front_h - 1
chk("F2: no ledge at trayA_front_h - 1: the fillet is still solid 3 mm above it, 0.3 off the divider face and the wall",
    body.contains([[dx0 - 0.3, wo + 0.3, P["trayA_front_h"] + 2.0]])[0])
# F3: the stop block, its filler and the pillar agree within 0.05
chk("F3: the stop block is pillar_w less 0.05 wide", abs(P["pick_stop_w"] - (P["pillar_w"] - 0.05)) < 1e-9)
# F4: the wall between the trays has a bevel on its back-top edge (no 46 degree knife)
y1 = P["yA_wall1"]
removed(body, [25.0, y1 - 0.05, zp(y1) - 0.05], [25.0, y1 - 0.05, zp(y1) - 1.2], "F4: wall back-top edge is bevelled")
# F5: tray B's corner gusset climbs to the bevel (was 2 mm under the plane at the face)
bxb = wo + bw + wd      # divider 1's right face
chk("F5: tray B gusset is solid 1.6 mm under the plane, 0.3 off the corner",
    body.contains([[bxb + 0.3, y1 + 0.3, zp(y1) - 1.6]])[0])
# F7: end bay tray A front corner has a fillet at the stop block's face
xb = wo + P["pick_stop_w"]
chk("F7: end bay front corner is filleted at the stop block face (0.25 from both faces is solid)",
    body.contains([[xb + 0.25, wo + 0.25, 40.0]])[0])
# F8: the dividers' top edges are rounded and still leave a flat of 1.5 mm or more for the lid
yy = 20.0
removed(body, [dx0 + 0.02, yy, zp(yy) - 0.03], [dx0 + 0.02, yy, zp(yy) - 0.9], "F8: divider top edge (left face) is rounded")
xs = np.arange(dx0, dx0 + wd, 0.02)
flat = body.contains([[x, yy, zp(yy) - 0.002] for x in xs])
fw = flat.sum() * 0.02
chk(f"F8: the divider's flat at the plane (0.002 under it) is {fw:.2f} mm, 1.5 or more", fw >= 1.5)
# F9: vertical rounds on the rail-1 buttress's inboard edges and the filler's back-inner edge
bi = wo + P["rail_boss"]; yf = P["rail1_y"] - P["rail_boss_w"] / 2; yb_ = P["rail1_y"] + P["rail_boss_w"] / 2
removed(body, [bi - 0.1, yf + 0.1, 80.0], [bi - 0.4, yf + 0.5, 80.0], "F9: buttress front inboard edge is rounded r 1")
removed(body, [bi - 0.1, yb_ - 0.1, 80.0], [bi - 0.4, yb_ - 0.5, 80.0], "F9: buttress back inboard edge is rounded r 1")
xe = wo + P["pick_stop_w"] - 0.05
removed(body, [xe - 0.05, yf + 0.5 - 0.05, 40.0], [xe - 0.55, yf + 0.5 - 0.5, 40.0], "F9: filler back-inner edge is rounded r 1")
# F10: the fill-seat cut oversteps 0.05, not 0.4: no notch in the rim wall beside a divider
chk("F10: the rim wall beside divider 1 has no 0.4 notch (0.2 behind the mouth face, z 187.5, is solid)",
    body.contains([[dx0 + wd / 2, P["hop_mouth_y0"] - 0.2, 187.5]])[0])
# F11: the seat ledge tip ends in a vertical land, not a 45 degree knife
fs = P["fill_seat_z"]
removed(body, [25.0 + 0, P["hop_mouth_y0"] + P["fill_ledge_w"] - P["seat_lip_drop"] - P["fill_ledge_land"] + 0.1, fs - 0.45],
        [25.0, P["hop_mouth_y0"] + P["fill_ledge_w"] - P["seat_lip_drop"] - P["fill_ledge_land"] - 0.1, fs - 0.45],
        "F11: seat ledge tip is a vertical land")
# F12: the pull-lip notch's vertical edges are rounded
nx0 = P["module_w"] / 2 - P["fill_grip_d"] / 2; nr = P["pull_notch_r"]; fy0 = P["hop_mouth_y0"] - wd
removed(body, [nx0 - 0.1, fy0 + 0.1, fs + 1.0], [nx0 - 0.4, fy0 + 0.4, fs + 1.0], f"F12: pull-lip notch edge (tray side) is rounded r {nr}")
removed(body, [nx0 - 0.1, P["hop_mouth_y0"] - 0.1, fs + 1.0], [nx0 - 0.4, P["hop_mouth_y0"] - 0.4, fs + 1.0], f"F12: pull-lip notch edge (mouth side) is rounded r {nr}")

print("\npick lid (as modelled: assembled orientation)")
w = P["pick_lid_w"]; zu = lambda y: zp(y) + P["pick_lid_gap"]
sc_ = P["pick_skirt_chamfer"]; ht = P["pick_lid_hook_t"]
removed(pick, [0.1, -ht + 0.1, 60.0], [sc_ + 0.3, -ht + 0.1 + 0.2, 60.0], "skirt outer end edge, left")
removed(pick, [w - 0.1, -ht + 0.1, 60.0], [w - sc_ - 0.3, -ht + 0.1 + 0.2, 60.0], "skirt outer end edge, right")
uc = P["pick_under_chamfer"]
removed(pick, [0.05, 40.0, zu(40.0) + 0.05], [uc + 0.3, 40.0, zu(40.0) + 0.05], "plate underside x-end edge, left")
removed(pick, [w - 0.05, 40.0, zu(40.0) + 0.05], [w - uc - 0.3, 40.0, zu(40.0) + 0.05], "plate underside x-end edge, right")
chk("the plate's end face keeps over 1 mm of flat between its two chamfers", P["lid_t"] - 1.0 - uc >= 1.0)

# D53: the end chamfer runs on round the bend. Points on the bend's arc (the profile's own centre line
# of the round), at three angles, are cut away at x = 0.1 and stay at x = c + 0.3.
al = np.radians(P["slope"])
Ro = P["pick_bend_out_r"]; turn = 90.0 - P["slope"]; tv = P["lid_t"] / np.cos(al)
Co = np.array([-ht, zu(-ht) + tv]); to = Ro * np.tan(np.radians(turn / 2))
cen = np.array([-ht + Ro, Co[1] - to])
for frac in (0.25, 0.5, 0.75):
    a = np.radians(180 - turn * frac)
    q = cen + (Ro - 0.05) * np.array([np.cos(a), np.sin(a)])          # 0.05 inside the round's surface
    removed(pick, [0.1, q[0], q[1]], [P["lid_chamfer"] + 0.3, q[0], q[1]], f"end chamfer round the bend, {int(frac * 100)} % round, left")
    removed(pick, [w - 0.1, q[0], q[1]], [w - P["lid_chamfer"] - 0.3, q[0], q[1]], f"end chamfer round the bend, {int(frac * 100)} % round, right")
# and the body of the bend is solid in the middle of the lid, so the round did not open a gap
a = np.radians(180 - turn * 0.5)
chk("the bend is solid 0.3 mm inside its round, mid-width", pick.contains([[120.0, *(cen + (Ro - 0.3) * np.array([np.cos(a), np.sin(a)]))]])[0])

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
