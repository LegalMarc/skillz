#!/usr/bin/env python3
"""Face-normal printability scan of the print-ready parts.

For each STL (in its print orientation, z = 0 on the bed) list every downward
face more than LIMIT degrees from vertical above the bed, grouped by how it
faces and where it is:

  * flat:  normal within 5 degrees of straight down. A deliberate bridge if it
           is one of the declared ones (the chute ceiling under tray B, the
           outlet tops, the cubby ceiling, the vault lips) and a defect otherwise.
  * steep: past LIMIT from vertical but not flat: the real overhangs.

    python3 probes/overhang_scan.py build/print_ready/*.stl
"""
import sys
import numpy as np
import trimesh

LIMIT = 45.0        # degrees from vertical
EPS_BED = 0.05      # faces this close to z = 0 are the bed face


def scan(path):
    m = trimesh.load(path)
    n = m.face_normals
    a = m.area_faces
    z = m.triangles_center[:, 2]
    # angle between the face normal and straight down: 0 = a flat ceiling,
    # 90 = a vertical wall. "Past LIMIT from vertical" = normal within
    # 90 - LIMIT of straight down.
    ang_down = np.degrees(np.arccos(np.clip(-n[:, 2], -1, 1)))
    past = (n[:, 2] < 0) & (ang_down < 90 - LIMIT) & (z > EPS_BED)
    flat = past & (ang_down < 5.0)
    steep = past & ~flat
    print(f"\n{path}: {len(m.faces)} faces, bounds {m.bounds[0].round(1).tolist()} .. {m.bounds[1].round(1).tolist()}")
    print(f"  downward faces past {LIMIT:.0f} deg from vertical, above the bed: "
          f"flat {a[flat].sum():.0f} mm2, steep {a[steep].sum():.0f} mm2")
    for name, mask in (("flat", flat), ("steep", steep)):
        idx = np.where(mask)[0]
        if not len(idx):
            continue
        keys = {}
        for i in idx:
            k = (name, tuple(np.round(n[i], 1)), round(z[i] / 5) * 5 if name == "flat" else round(z[i] / 20) * 20)
            keys.setdefault(k, []).append(i)
        rows = []
        for k, ii in keys.items():
            c = m.triangles_center[ii]
            rows.append((a[ii].sum(), k, c.min(0), c.max(0), ang_down[ii].mean()))
        rows.sort(key=lambda r: -r[0])
        for area, k, lo, hi, ad in rows[:16]:
            print(f"    {name:5s} {area:8.1f} mm2  normal {k[1]}  {90 - ad:4.1f} deg from vertical  "
                  f"x {lo[0]:.0f}..{hi[0]:.0f} y {lo[1]:.0f}..{hi[1]:.0f} z {lo[2]:.0f}..{hi[2]:.0f}")
    return a[flat].sum(), a[steep].sum()


if __name__ == "__main__":
    for p in sys.argv[1:]:
        scan(p)
