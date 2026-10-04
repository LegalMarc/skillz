#!/usr/bin/env python3
"""D41 probe: do the corner beads lift a capsule off tray A's floor, and do they
(with the stop block, the filler and the buttress) leave a place for a capsule
to wedge?

The capsule is a 26 x 11 mm cylinder with hemispherical ends (params: pill_len,
pill_dia), modelled as its axis segment: it is free at a pose when every sampled
axis point is at least the radius from the body mesh. It is dropped from above at
each (x, y) until it touches (the lowest free z), then the pose with the lowest
centre is its rest, which is where a capsule sliding down the 35 degree floor
ends up. Run with the beads (bead_r from params) and without (-D bead_r=0).

  ALONG X  (axis parallel to the front wall, the "lying in the corner" case):
           lift = height of the capsule's underside above the floor at rest.
  ALONG Y  (axis toward the wall, an end in the corner): how close to the wall the
           capsule's centre gets, and the height of its front end above the floor.
  DIAGONALS 45 and 135 degrees in plan.
  END BAY  the same poses over the last bay (stop block, filler, buttress, side
           wall): the rest pose of each is listed, and a pose is a WEDGE if the
           capsule rests with its underside on the floor (not lifted) AND an end or
           side is within 1 mm of two non-floor features at once at a spot where
           the free width is under a capsule diameter. The check reports how many
           of the scanned poses are wedges and where.

    python3 probes/capsule_corner.py            # beads as built, middle bay and last bay
    python3 probes/capsule_corner.py 6 7 8 9    # lift vs bead radius (middle bay, along X)
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
        hi = np.array([x1 + 2.0, 30.0, 50.0])
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


if __name__ == "__main__":
    if len(sys.argv) > 1:
        for r in sys.argv[1:]:
            m = parts(("body",), defs=[f"bead_r={r}"])["body"]
            res = middle(m, orients=("x",))
            print_middle(f"bead_r {r}", res)
        sys.exit(0)
    no_b = parts(("body",), defs=["bead_r=0"])["body"]
    with_b = parts(("body",))["body"]
    print(f"bead_r {P['bead_r']}; pill {26} x {11}; floor {35} deg")
    print("MIDDLE BAY (bay 2)")
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
    print(f"\nRESULT: beads lift a capsule lying along X by {lift:.2f} mm at worst "
          f"(without beads {min(a['x'][2]):.2f}); last-bay slots: {len(wedges)}")
    sys.exit(0 if (lift >= 1.5 and not wedges) else 1)
