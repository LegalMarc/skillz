#!/usr/bin/env python3
"""Lay a test print out on one 256 x 256 plate as a core-spec 3MF.

    python3 build/maquette/make_plate.py maquette            # the 0.42 model
    python3 build/maquette/make_plate.py section             # full-size corner section
    python3 build/maquette/make_plate.py section --export    # re-export every STL first

Run from the project directory (needs OPENSCAD_BIN: source
~/.local/opt/openscad/env.sh). With --export the STLs the plate is made of are
re-rendered from the .scad sources first, so one command regenerates the whole
plate from params.scad; without it the STLs already in build/ are used.
Positions are the part's minimum corner; each STL is already in print
orientation on z = 0.
"""
import itertools, os, subprocess, sys, zipfile
from xml.sax.saxutils import escape
import trimesh

# what --export renders: (output stl, scad file, -D arguments)
EXPORTS = {
    "maquette": [
        ("build/maquette/body.stl",     "test_model.scad", ['PART="body"']),
        ("build/maquette/pick_lid.stl", "test_model.scad", ['PART="pick_lid"']),
        ("build/maquette/fill_lid.stl", "test_model.scad", ['PART="fill_lid"']),
        ("build/calibration_coupon.stl", "calibration_coupon.scad", []),
    ],
    "section": [
        ("build/section/body.stl",     "fit_section.scad", ['PART="body"']),
        ("build/section/pick_lid.stl", "fit_section.scad", ['PART="pick_lid"']),
        ("build/section/mouth.stl",    "fit_section.scad", ['PART="mouth"']),
        ("build/section/fill_lid.stl", "fit_section.scad", ['PART="fill_lid"']),
        ("build/calibration_coupon.stl", "calibration_coupon.scad", []),
    ],
}


def export_all(which):
    exe = os.environ.get("OPENSCAD_BIN")
    if not exe:
        sys.exit("OPENSCAD_BIN not set: source ~/.local/opt/openscad/env.sh first")
    for out, src, defs in EXPORTS[which]:
        cmd = [exe, "--backend=manifold"] + [a for d in defs for a in ("-D", d)] + ["-o", out, src]
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0 or "ERROR" in r.stderr:
            sys.exit(f"OpenSCAD failed for {out}:\n{r.stderr[-1500:]}")
        print("exported", out)


PLATES = {
    # the 0.42 maquette: shape only -- it scales every clearance and wall too
    "maquette": ("build/maquette/test_print_plate_256.3mf",
                 "0.42 maquette + calibration coupon", [
        ("pill_organizer_body_x0.42",     "build/maquette/body.stl",      (15.0, 15.0)),
        ("pill_organizer_pick_lid_x0.42", "build/maquette/pick_lid.stl",  (130.0, 15.0)),
        ("pill_organizer_fill_lid_x0.42", "build/maquette/fill_lid.stl",  (130.0, 90.0)),
        ("calibration_coupon",            "build/calibration_coupon.stl", (15.0, 150.0)),
    ]),
    # full size: one end bay of the real body back to hopper B's ramp, the end
    # of the real pick lid, a corner of the fill mouth and of the fill lid
    # revision 10: the body section is 49 x 146 x 160, the lid end 48.5 x 142.5,
    # the coupon 124 x 30; the coupon moves behind them (y 180)
    "section": ("build/section/test_print_section_256.3mf",
                "full-size end bay + pick lid end + fill mouth and lid corners + calibration coupon", [
        ("body_section_bay5_full_size",   "build/section/body.stl",       (20.0, 20.0)),
        ("pick_lid_end_full_size",        "build/section/pick_lid.stl",   (90.0, 20.0)),
        ("fill_mouth_corner_full_size",   "build/section/mouth.stl",      (160.0, 20.0)),
        ("fill_lid_corner_full_size",     "build/section/fill_lid.stl",   (160.0, 65.0)),
        ("calibration_coupon",            "build/calibration_coupon.stl", (20.0, 180.0)),
    ]),
}
WHICH = sys.argv[1] if len(sys.argv) > 1 else "maquette"
if "--export" in sys.argv:
    export_all(WHICH)
OUT, TITLE, PARTS = PLATES[WHICH]
PLATE, MARGIN, MIN_GAP = 256.0, 10.0, 10.0

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
<metadata name="Title">pill_organizer_10bay test print plate: {TITLE}, 256 x 256</metadata>
<metadata name="Designer">LegalMarc/skillz scad-workbench</metadata>
<metadata name="Description">Named objects in print orientation on a 256 x 256 plate, origin at the front-left corner. No supports. PLA or PETG, 0.2 mm layers, 3 perimeters.</metadata>
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
