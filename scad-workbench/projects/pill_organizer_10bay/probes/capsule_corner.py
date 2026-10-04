#!/usr/bin/env python3
"""D41 probe: do the corner beads do their job, and can a capsule wedge in tray A's corners?

The beads (revision 11 review) are three small half-round ribs per bay, radius 2.5, from the
front wall along the floor, hemispherical ends. Their job, in the user's words: something to
push a capsule's end against so it tips and can be grabbed. This measures that on the real
mesh. A capsule is a 26 x 11 mm cylinder with hemispherical ends (pill_len, pill_dia), modelled
as its axis segment on a 0.4 mm distance field of the body.

  END PUSH   a capsule lying along the FALL LINE (axis parallel to the 35 degree floor,
             perpendicular to the wall, its lower end toward the wall) is slid down the
             floor, centred on a rib, between two ribs, and over the bay's edge, until it
             stops. Reported: where its lower end stops (distance of the tip from the wall,
             with and without ribs), where it touches the rib (the contact normal on the end
             cap, and the contact's height above the capsule's axis: positive = above, a
             contact BELOW the axis pushes the end UP and tips the capsule), and how far the
             end is lifted off the floor.
  ALONG X    the same for a capsule lying along the wall, pushed ALONG X into a rib: where
             its end meets the rib and at what height on the cap.
  GAP        a capsule cannot wedge between two ribs: the clear gap is narrower than a
             capsule (asserted in params) and the end-push poses between two ribs are listed.
  LAST BAY   pockets deeper than 3 mm in the right-hand corner (stop block, filler,
             buttress, side wall, ribs) that a capsule end cannot reach.

    python3 probes/capsule_corner.py
"""
import sys
import numpy as np
import trimesh
from trimesh.proximity import signed_distance
from _common import params, parts

P = params()
R = 11.0 / 2          # pill_dia / 2 (params.scad pill_dia = 11)
HALF = (26.0 - 11.0) / 2
TILT = np.radians(35.0)
WO, BW, WD = 2.8, P["bay_w"], P["wall_div"]
MW = P["module_w"]


def floor_z(y):
    return 3.0 + (y - WO) * np.tan(TILT)


PITCH = 0.4


class World:
    """The corner of the body around one bay as a voxel distance field: a capsule
    axis point is free when its distance to the nearest solid voxel is the radius
    or more (to one voxel of tolerance)."""

    def __init__(self, mesh, x0, x1):
        from scipy.ndimage import distance_transform_edt
        self.lo = np.array([x0 - 2.0, -1.0, -1.0])
        hi = np.array([x1 + 2.0, 40.0, 60.0])        # well past anything a capsule reaches: the crop closes the mesh with solid faces here
        box = trimesh.creation.box(extents=hi - self.lo)
        box.apply_translation((hi + self.lo) / 2)
        crop = trimesh.boolean.intersection([mesh, box], engine="manifold")
        vg = crop.voxelized(PITCH).fill()
        shape = np.ceil((hi - self.lo) / PITCH).astype(int) + 1
        occ = np.zeros(shape, bool)
        idx = np.round((vg.points - self.lo) / PITCH).astype(int)
        ok = np.all((idx >= 0) & (idx < shape), axis=1)
        occ[tuple(idx[ok].T)] = True
        self.edt = distance_transform_edt(~occ) * PITCH
        self.shape = shape

    def dist(self, pts):
        i = np.round((pts - self.lo) / PITCH).astype(int)
        i = np.clip(i, 0, self.shape - 1)
        return self.edt[i[:, 0], i[:, 1], i[:, 2]]

    def free(self, c, d):
        t = np.linspace(-HALF, HALF, 9)
        pts = c[None, :] + t[:, None] * d[None, :]
        return bool(np.all(self.dist(pts) >= R - PITCH))

    def rest_z(self, x, y, d, zhi=44.0, step=0.2):
        c = np.array([x, y, zhi])
        if not self.free(c, d):
            return None
        z = zhi
        while z - step > 0 and self.free(np.array([x, y, z - step]), d):
            z -= step
        return z


def under_clearance(x, y, z, d):
    """height of the capsule's underside over the floor plane, lowest along the axis"""
    t = np.linspace(-HALF, HALF, 9)
    ys = y + t * d[1]
    zs = z + t * d[2]
    return float(np.min((zs - floor_z(ys)) * np.cos(TILT)) - R)


DIRS = {"x": np.array([1.0, 0, 0]), "y": np.array([0, 1.0, 0]),
        "d45": np.array([0.7071, 0.7071, 0]), "d135": np.array([-0.7071, 0.7071, 0])}


def rest_pose(world, x, orient, ymax=28.0, dy=0.2):
    """Where a capsule ends up when it slides down the floor toward the front wall:
    start well back, follow the floor forward (it can only go lower or stay level),
    stop at the first position it cannot enter. Dropping it from above instead would
    be blocked by the front wall's top, which no capsule ever has to clear."""
    d = DIRS[orient]
    y = ymax
    z = world.rest_z(x, y, d)
    if z is None:
        return None
    while True:
        y2 = y - dy
        # the next position: lowest free z at y2, searched downward from the current z
        if not world.free(np.array([x, y2, z]), d):
            # maybe it must go UP a hair (a bead): not allowed, gravity only lowers it
            return (x, y, z)
        z2 = z
        while z2 - 0.1 > 0 and world.free(np.array([x, y2, z2 - 0.1]), d):
            z2 -= 0.1
        y, z = y2, z2


def lift_of(pose, orient):
    return under_clearance(*pose, DIRS[orient])


def middle(mesh, bay=2, orients=("x",)):
    x0 = WO + bay * (BW + WD)
    w = World(mesh, x0, x0 + BW)
    xs = np.arange(x0 + 13.5, x0 + BW - 13.5 + 0.01, 3.0)   # a capsule along X is 26 long: its end stays 5.5 from the divider
    out = {}
    for o in orients:
        poses = [rest_pose(w, x, o) for x in xs]
        out[o] = (xs, poses, [lift_of(p, o) for p in poses])
    return out


def print_middle(name, res):
    for o, (xs, poses, lifts) in res.items():
        ys = [p[1] for p in poses]
        print(f"  {name:11s} along {o:4s}: underside above the floor at rest min {min(lifts):5.2f} max {max(lifts):5.2f} mm; "
              f"centre y {min(ys):.2f} .. {max(ys):.2f}")


FALL = np.array([0.0, np.cos(TILT), np.sin(TILT)])       # up the floor, away from the wall
NF = np.array([0.0, -np.sin(TILT), np.cos(TILT)])        # the floor's normal


def slide_down(world, x, y0=24.0, dy=0.1):
    """a capsule lying along the fall line, resting on the floor at floor-line position y0,
    slid toward the wall until the next step is blocked. Returns its centre, or None."""
    hover = 0.5     # the floor is a staircase of 0.4 mm voxels at 35 degrees: ride half a millimetre above it
    def centre(y):
        return np.array([x, y, floor_z(y)]) + (R + hover) * NF
    y = y0
    if not world.free(centre(y), FALL):
        return None
    while world.free(centre(y - dy), FALL):
        y -= dy
        if y < WO - 1:
            break
    return centre(y)


def contact_on_cap(world, c):
    """where the lower end cap of a fall-line capsule at centre c touches something that is not
    the floor or the front wall: the mean point, its height above the axis (along the floor normal;
    negative = below the axis, which pushes the end UP) and its elevation angle."""
    low = c - HALF * FALL
    pts = []
    for th in np.linspace(0, np.pi / 2, 19):
        for ph in np.linspace(0, 2 * np.pi, 48, endpoint=False):
            # a direction on the cap hemisphere facing the wall (-FALL), built in an orthonormal frame
            u = np.array([1.0, 0, 0]); v = np.cross(FALL, u)
            dirn = -np.cos(th) * FALL + np.sin(th) * (np.cos(ph) * u + np.sin(ph) * v)
            p = low + (R + 0.05) * dirn
            if world.dist(p[None, :])[0] > 0.9:
                continue
            # not the floor: the point is more than 0.9 mm above the floor plane; not the wall: > 0.9 from y = 2.8
            above = (p[2] - floor_z(p[1])) * np.cos(TILT)
            if above < 0.9 or p[1] < WO + 0.9:
                continue
            pts.append((p, dirn))
    if not pts:
        return None
    p = np.mean([q[0] for q in pts], axis=0)
    h = float(np.mean([R * np.dot(q[1], NF) for q in pts]))      # height above the axis, floor-normal direction
    elev = float(np.degrees(np.arcsin(np.clip(np.mean([np.dot(q[1], NF) for q in pts]), -1, 1))))
    return p, h, elev, len(pts)


def end_push(mesh_b, mesh_n, bay=2):
    x0 = WO + bay * (BW + WD)
    wb = World(mesh_b, x0, x0 + BW); wn = World(mesh_n, x0, x0 + BW)
    pitch = BW * 0.25
    rib_x = [x0 + pitch * k for k in (1, 2, 3)]
    cases = [("centred on rib 2", rib_x[1]), ("centred in the gap between ribs 2 and 3", rib_x[1] + pitch / 2),
             ("centred on rib 1", rib_x[0]), ("beside rib 1, against the divider (centre 5.6 from it)", x0 + 5.6)]
    rows = []
    for name, x in cases:
        cb = slide_down(wb, x); cn = slide_down(wn, x)
        if cb is None or cn is None:
            rows.append((name, None)); continue
        tip_b = (cb - (HALF + R) * FALL)[1] - WO; tip_n = (cn - (HALF + R) * FALL)[1] - WO
        lift_b = float(((cb - HALF * FALL)[2] - floor_z((cb - HALF * FALL)[1])) * np.cos(TILT) - R) - 0.5   # less the 0.5 hover
        con = contact_on_cap(wb, cb)
        rows.append((name, (tip_n, tip_b, lift_b, con)))
    return rows


if __name__ == "__main__":
    no_b = parts(("body",), defs=["bead_r=0"])["body"]
    with_b = parts(("body",))["body"]
    print(f"bead_r {P['bead_r']}, bead_len {P['bead_len']}; pill 26 x 11; floor 35 deg; clear gap between ribs "
          f"{BW * 0.25 - 2 * P['bead_r']:.2f} mm (capsule diameter 11)")
    print("\nEND PUSH: a capsule lying along the fall line is slid down the floor toward the front wall (middle bay)")
    ok_push = True
    for name, r in end_push(with_b, no_b):
        if r is None:
            print(f"  {name}: could not be placed"); continue
        tip_n, tip_b, lift_b, con = r
        print(f"  {name}: its tip stops {tip_b:5.2f} mm from the wall (without ribs {tip_n:5.2f}, where the capsule meets the wall)"
              + (f"; touches a rib at {con[2]:+.0f} deg elevation, {con[1]:+.2f} mm from the axis (negative = below it: pushes the end UP), {con[3]} sample points" if con else "; touches no rib (stopped by the wall or floor)"))
        if "on rib" in name:
            ok_push &= (tip_b - tip_n) > 1.0 and con is not None and con[1] < 0     # held out, and touched BELOW the axis
    print("\nMIDDLE BAY, rest poses of a capsule lying along the wall and others (no ribs vs ribs)")
    a = middle(no_b, orients=("x", "y", "d45", "d135"))
    print_middle("no beads", a)
    b = middle(with_b, orients=("x", "y", "d45", "d135"))
    print_middle("with beads", b)
    lift = min(b["x"][2])
    # LAST BAY: stop block, filler, buttress, side wall. Slice the corner at several heights.
    # In each slice the centres a capsule can reach are the free area eroded by a capsule
    # radius; what a capsule can cover is those centres grown back by the radius. The free
    # area it can NOT cover is where a capsule's end cannot get to but something narrower
    # can: every 90 degree corner leaves a cusp of 2.3 mm (R x (sqrt(2) - 1)); a POCKET is
    # an uncovered area reaching deeper than 3 mm from the covered area, which only a slot
    # narrower than a capsule, or an acute corner, produces. Those are where a capsule
    # tip, a fragment or a tablet lodges.
    from shapely.geometry import box as sbox
    from corner_thickness import solid_at
    gaps = []
    bay = 4
    x1 = WO + bay * (BW + WD) + BW
    zone = sbox(x1 - 32, WO, x1, 30.0)
    for z in (26.0, 32.0, 40.0, 48.0):          # above the floor everywhere in the zone (a slice through the sloped floor is a sliver, not a pocket); a capsule never rests above the pile (crest 49)
        sol = solid_at(with_b, z).buffer(0)
        free = zone.difference(sol)
        if free.is_empty:
            continue
        # only the bay's own air: voids enclosed in the solid (the rail groove, for one) are not reachable
        parts_ = list(getattr(free, "geoms", [free]))
        free = max(parts_, key=lambda g: g.area)
        centres = free.buffer(-R)
        covered = centres.buffer(R) if not centres.is_empty else None
        pocket = free.difference(covered) if covered is not None else free
        for g in getattr(pocket, "geoms", [pocket]):
            if g.area < 1.0:
                continue
            # only pockets against the bay's real corner features, not the zone's own cut edges
            inner = g.intersection(sbox(x1 - 31, WO + 0.5, x1 - 0.1, 29.5))
            if inner.is_empty or inner.area < 1.0:
                continue
            depth = max(covered.distance(__import__("shapely").geometry.Point(c)) for c in list(inner.exterior.coords)) if covered is not None and inner.geom_type == "Polygon" else 0.0
            if depth > 3.0:
                gaps.append((z, round(inner.centroid.x, 1), round(inner.centroid.y, 1), round(inner.area, 1), round(depth, 1)))
    print(f"  pockets in the last bay's corner zone, deeper than 3 mm (z, x, y, area mm2, depth mm): {len(gaps)}"
          + (f": {gaps}" if gaps else ""))
    wedges = gaps
    # rest poses near the lump, for the record
    w = World(with_b, WO + bay * (BW + WD), x1)
    rows = []
    for o in ("x", "y", "d45", "d135"):
        for x in np.arange(x1 - 30.0, x1 - 6.0, 4.0):
            p = rest_pose(w, x, o)
            if p is not None:
                rows.append((o, round(float(x), 1), round(float(p[1]), 1), round(float(p[2]), 1), round(lift_of(p, o), 2)))
    print("  rest poses within 30 mm of the right side wall (orientation, x, y, z, lift mm):")
    for r_ in rows:
        print("    ", r_)
    print("  note: the capsule axis is held horizontal in the model, so only ALONG X (parallel to the contour lines of the 35 degree floor) is a true rest pose;"
          "\n        the other orientations are reported for the record (a capsule lying along Y really tilts with the floor).")
    print(f"\nRESULT: a capsule on a rib is held out from the wall and pushed up from below the axis: {ok_push}; "
          f"capsule along X lifted {lift:.2f} mm at worst (without ribs {min(a['x'][2]):.2f}); last-bay pockets: {len(wedges)}")
    sys.exit(0 if (ok_push and not wedges) else 1)
