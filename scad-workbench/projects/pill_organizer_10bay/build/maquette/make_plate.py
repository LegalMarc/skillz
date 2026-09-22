#!/usr/bin/env python3
"""Lay the small test print out on one 256 x 256 plate as a core-spec 3MF.

Run from the project directory after re-exporting build/maquette/*.stl and
build/calibration_coupon.stl. Positions are the part's minimum corner; each STL
is already in print orientation on z = 0.
"""
import itertools, os, zipfile
from xml.sax.saxutils import escape
import trimesh

PARTS = [
    ("pill_organizer_body_x0.42",     "build/maquette/body.stl",      (15.0, 15.0)),
    ("pill_organizer_pick_lid_x0.42", "build/maquette/pick_lid.stl",  (130.0, 15.0)),
    ("pill_organizer_fill_lid_x0.42", "build/maquette/fill_lid.stl",  (130.0, 70.0)),
    ("calibration_coupon",            "build/calibration_coupon.stl", (15.0, 135.0)),
]
PLATE, MARGIN, MIN_GAP = 256.0, 10.0, 10.0
OUT = "build/maquette/test_print_plate_256.3mf"

objs, items, bb = [], [], {}
for i, (name, path, (px, py)) in enumerate(PARTS, start=1):
    m = trimesh.load(path, force="mesh")
    lo, sz = m.bounds[0], m.bounds[1] - m.bounds[0]
    tx, ty, tz = px - lo[0], py - lo[1], -lo[2]
    v = "\n".join(f'<vertex x="{x:.4f}" y="{y:.4f}" z="{z:.4f}"/>' for x, y, z in m.vertices)
    t = "\n".join(f'<triangle v1="{a}" v2="{b}" v3="{c}"/>' for a, b, c in m.faces)
    objs.append(f'<object id="{i}" name="{escape(name)}" type="model"><mesh><vertices>\n{v}\n'
                f'</vertices><triangles>\n{t}\n</triangles></mesh></object>')
    items.append(f'<item objectid="{i}" transform="1 0 0 0 1 0 0 0 1 {tx:.4f} {ty:.4f} {tz:.4f}"/>')
    bb[name] = (px, py, px + sz[0], py + sz[1])
    assert px >= MARGIN and py >= MARGIN and px + sz[0] <= PLATE - MARGIN and py + sz[1] <= PLATE - MARGIN, name
for a, b in itertools.combinations(bb, 2):
    A, B = bb[a], bb[b]
    assert max(B[0] - A[2], A[0] - B[2], B[1] - A[3], A[1] - B[3]) >= MIN_GAP, (a, b)

model = f'''<?xml version="1.0" encoding="UTF-8"?>
<model unit="millimeter" xml:lang="en-US" xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02">
<metadata name="Title">pill_organizer_10bay test print plate: 0.42 maquette + calibration coupon, 256 x 256</metadata>
<metadata name="Designer">LegalMarc/skillz scad-workbench</metadata>
<metadata name="Description">Four objects in print orientation on a 256 x 256 plate, origin at the front-left corner. No supports. PLA or PETG, 0.2 mm layers, 3 perimeters.</metadata>
<resources>
{chr(10).join(objs)}
</resources>
<build>
{chr(10).join(items)}
</build>
</model>'''
CT = '''<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/>
</Types>'''
RELS = '''<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Target="/3D/3dmodel.model" Id="rel0" Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/>
</Relationships>'''
with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as z:
    z.writestr("[Content_Types].xml", CT); z.writestr("_rels/.rels", RELS); z.writestr("3D/3dmodel.model", model)
print("wrote", OUT, os.path.getsize(OUT) // 1024, "KB")
