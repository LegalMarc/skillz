#!/usr/bin/env python3
"""D62 probe: the lug's cross-section (area, bending section modulus) at depths below the plate, old vs new.

The lug is a cantilever standing up from the plate in the print, loaded at its tip. The bending stress at a
section is M / Z with M the same for both lugs, so the ratio of section moduli Z is the stress ratio. Z is
measured on the meshes by slicing the lug with planes parallel to the plate, at depth g below the underside:
  Z_x = I about the s axis / half-width in X   (a knock sideways, across the lug's thickness)
  Z_s = I about the x axis / half-length in s  (a knock along the slope)
The old lug is build/pick_lid.stl as committed at revision 17 (git show), the new one is a fresh render.

    source ~/.local/opt/openscad/env.sh
    python3 probes/lug_section.py [old_lid.stl]
"""
import subprocess, sys, os, tempfile
import numpy as np
import trimesh
from shapely.geometry import Polygon
from shapely.ops import unary_union
from _common import params, parts, PROJECT

P = params()
a = np.radians(P["slope"])
u = np.array([0.0, np.cos(a), np.sin(a)]); N = np.array([0.0, -np.sin(a), np.cos(a)])
org = np.array([0.0, 0.0, P["pickplane_front"] + 0.2])        # the underside at y = 0 (lid frame, no lid_dx)
new = parts(("pick_lid",), defs=('SUBFEATURE="pick_lugs"',))["pick_lid"]
if len(sys.argv) > 1:
    old = trimesh.load(sys.argv[1])
else:
    out = subprocess.run(["git", "show", "HEAD:scad-workbench/projects/pill_organizer_10bay/build/pick_lid.stl"],
                         capture_output=True, cwd=PROJECT, check=True).stdout
    with tempfile.NamedTemporaryFile(suffix=".stl", delete=False) as f:
        f.write(out); old_path = f.name
    old = trimesh.load(old_path)


def lug_section(mesh, g, left=True):
    """The left lug's section g mm below the underside (lid frame): polygon in (x, s)."""
    o = org - N * g
    path = mesh.section(plane_origin=o, plane_normal=N)
    M = np.eye(4); M[0, :3] = [1, 0, 0]; M[1, :3] = u; M[2, :3] = N
    M[:3, 3] = -M[:3, :3] @ o
    p2, _ = path.to_2D(to_2D=M)
    polys = [Polygon(e) for e in p2.discrete if len(e) > 3]
    polys = [q for q in polys if q.is_valid and 1.0 < q.area < 300]
    sel = [q for q in polys if q.centroid.x < 120] if left else [q for q in polys if q.centroid.x > 120]
    return unary_union(sel)


def zmod(poly):
    # about the centroid, axes x and s
    minx, mins, maxx, maxs = poly.bounds
    cx, cs = poly.centroid.x, poly.centroid.y
    pts = np.array(poly.exterior.coords)
    x = pts[:, 0] - cx; s = pts[:, 1] - cs
    x1, s1 = np.roll(x, -1), np.roll(s, -1)
    cr = x * s1 - x1 * s
    Ixx = (cr * (s * s + s * s1 + s1 * s1)).sum() / 12      # about the x axis (bending in s)
    Iss = (cr * (x * x + x * x1 + x1 * x1)).sum() / 12      # about the s axis (bending in x)
    Iss, Ixx = abs(Iss), abs(Ixx)
    return poly.area, Iss / max(cx - minx, maxx - cx), Ixx / max(cs - mins, maxs - cs)


print("section g mm below the plate | area mm2 | Z_x (sideways knock) mm3 | Z_s (knock along the slope) mm3")
for g in (0.3, 1.0, 2.0, 3.5, 5.0, 6.5):
    ao, zxo, zso = zmod(lug_section(old, g))
    an, zxn, zsn = zmod(lug_section(new, g))
    print(f"  g {g:3.1f}  old {ao:6.2f} {zxo:7.2f} {zso:7.2f}   new {an:6.2f} {zxn:7.2f} {zsn:7.2f}   ratio area {an/ao:4.2f}  Z_x {zxn/zxo:5.2f}  Z_s {zsn/zso:5.2f}")
