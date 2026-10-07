#!/usr/bin/env python3
"""Lay a test print out on one 256 x 256 plate as a core-spec 3MF.

    python3 build/maquette/make_plate.py maquette            # the 0.42 model
    python3 build/maquette/make_plate.py section             # full-size corner section
    python3 build/maquette/make_plate.py section --export    # re-export every STL first
    python3 build/maquette/make_plate.py final --export      # the three full-size plates (revision 12)

"final" writes build/final/final_{body,pick_lid,fill_lid}_256.3mf, one part each,
centred on the plate at z = 0, from build/print_ready/{body,pick_lid,fill_lid}.stl
(which --export re-renders from print_export.scad), and checks every part against
its STL and against the 5..251 mm usable footprint.

Run from the project directory (needs OPENSCAD_BIN: source
~/.local/opt/openscad/env.sh). With --export the STLs the plate is made of are
re-rendered from the .scad sources first, so one command regenerates the whole
plate from params.scad; without it the STLs already in build/ are used.
Positions are the part's minimum corner; each STL is already in print
orientation on z = 0.
"""
import itertools, os, subprocess, sys, zipfile
from xml.sax.saxutils import escape
import numpy as np
import trimesh

# what --export renders: (output stl, scad file, -D arguments)
# NOTE: since D56 calibration_coupon.scad's default output is a 150 x 118 mm three-object layout; the
# "calibration_coupon" entries of the maquette and section modes predate it and would not fit their
# plates if re-exported. The coupon is the "coupon" mode.
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
        ("build/section/fill_lid.stl", "fit_section.scad", ['PART="fill_lid"']),
        ("build/calibration_coupon.stl", "calibration_coupon.scad", []),
    ],
    "coupon": [
        ("build/coupon/plain.stl", "calibration_coupon.scad", ['PART="plain"']),
        ("build/coupon/ribs.stl",  "calibration_coupon.scad", ['PART="ribs"']),
        ("build/coupon/block.stl", "calibration_coupon.scad", ['PART="block"']),
    ],
    "final": [
        ("build/print_ready/body.stl",     "print_export.scad", ['PART="body"']),
        ("build/print_ready/pick_lid.stl", "print_export.scad", ['PART="pick_lid"']),
        ("build/print_ready/fill_lid.stl", "print_export.scad", ['PART="fill_lid"']),
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
        ("calibration_coupon",            "build/calibration_coupon.stl", (15.0, 160.0)),
    ]),
    # full size: one end bay of the real body back to hopper B's ramp, the end
    # of the real pick lid, a corner of the fill mouth and of the fill lid
    # revision 11: the body section is the whole end bay, about 50 x 213 x 189; the
    # lid ends sit beside it and the coupon is turned 90 degrees to fit the 246 mm limit
    "section": ("build/section/test_print_section_256.3mf",
                "full-size end bay + pick lid end + fill lid end + calibration coupon", [
        ("body_section_bay5_full_size",   "build/section/body.stl",       (20.0, 20.0)),
        ("pick_lid_end_full_size",        "build/section/pick_lid.stl",   (85.0, 20.0)),
        ("fill_lid_end_full_size",        "build/section/fill_lid.stl",   (145.0, 20.0)),
        ("calibration_coupon",            "build/calibration_coupon.stl", (205.0, 20.0, "rot90")),
    ]),
    # D51/D55/D56: the rail coupon alone, to confirm the fit before the final body. D56: two
    # row plates (150.8 x 54) and the groove block, centred on the plate, probes/coupon_fit.py
    "coupon": ("build/coupon/rail_coupon_256.3mf", "rail coupon only (D56)", [
        ("rail_coupon_d56_plain",         "build/coupon/plain.stl",       (52.0, 69.0)),
        ("rail_coupon_d56_ribs",          "build/coupon/ribs.stl",        (52.0, 133.0)),
        ("groove_block",                  "build/coupon/block.stl",       (213.0, 69.0)),
    ]),
}
FINAL = [   # (3mf, object name, stl)
    ("build/final/final_body_256.3mf",     "pill_organizer_body",     "build/print_ready/body.stl"),
    ("build/final/final_pick_lid_256.3mf", "pill_organizer_pick_lid", "build/print_ready/pick_lid.stl"),
    ("build/final/final_fill_lid_256.3mf", "pill_organizer_fill_lid", "build/print_ready/fill_lid.stl"),
]
PLATE, MARGIN, MIN_GAP = 256.0, 10.0, 10.0
# the final plates carry ONE part, so the limit is the printer's usable footprint (params.scad max_part_x/y:
# 5 mm of margin each side), not the 10 mm the multi-part test plates keep between parts. The 243 mm body
# (with its rail) cannot lie within 10..246.
FINAL_MARGIN = 5.0

CT = '''<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/>
</Types>'''
RELS = '''<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Target="/3D/3dmodel.model" Id="rel0" Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/>
</Relationships>'''


def write_3mf(out, title, desc, objs, items):
    model = f'''<?xml version="1.0" encoding="UTF-8"?>
<model unit="millimeter" xml:lang="en-US" xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02">
<metadata name="Title">{escape(title)}</metadata>
<metadata name="Designer">LegalMarc/skillz scad-workbench</metadata>
<metadata name="Description">{escape(desc)}</metadata>
<resources>
{chr(10).join(objs)}
</resources>
<build>
{chr(10).join(items)}
</build>
</model>'''
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", CT); z.writestr("_rels/.rels", RELS); z.writestr("3D/3dmodel.model", model)
    print("wrote", out, os.path.getsize(out) // 1024, "KB")


def mesh_xml(i, name, m):
    v = "\n".join(f'<vertex x="{x:.4f}" y="{y:.4f}" z="{z:.4f}"/>' for x, y, z in m.vertices)
    t = "\n".join(f'<triangle v1="{a}" v2="{b}" v3="{c}"/>' for a, b, c in m.faces)
    return f'<object id="{i}" name="{escape(name)}" type="model"><mesh><vertices>\n{v}\n</vertices><triangles>\n{t}\n</triangles></mesh></object>'


def final_plates():
    """One part per plate, centred on the plate in X and Y, standing on z = 0, then read back."""
    for out, name, stl in FINAL:
        m = trimesh.load(stl, force="mesh")
        assert m.is_watertight, stl + " is not watertight"
        lo, sz = m.bounds[0], m.bounds[1] - m.bounds[0]
        assert sz[0] <= PLATE - 2 * FINAL_MARGIN and sz[1] <= PLATE - 2 * FINAL_MARGIN, (name, sz)
        tx, ty, tz = PLATE / 2 - sz[0] / 2 - lo[0], PLATE / 2 - sz[1] / 2 - lo[1], -lo[2]
        item = f'<item objectid="1" transform="1 0 0 0 1 0 0 0 1 {tx:.4f} {ty:.4f} {tz:.4f}"/>'
        write_3mf(out, f"pill_organizer_10bay final print: {name}, 256 x 256",
                  "One part in print orientation, centred on a 256 x 256 plate at z = 0. No supports, no brim. PETG, 0.2 mm layers, 15% infill.",
                  [mesh_xml(1, name, m)], [item])
        verify_3mf(out, name, m)


def verify_3mf(path, name, stl_mesh):
    """Read the 3MF back and compare it to its STL: same size, same volume, same triangle count,
    inside the 5..251 mm usable footprint in X and Y, on the bed in Z."""
    import re
    with zipfile.ZipFile(path) as z:
        xml = z.read("3D/3dmodel.model").decode()
    assert xml.count("<object ") == 1 and f'name="{name}"' in xml, path
    vs = np.array([[float(a) for a in m] for m in re.findall(r'<vertex x="([-\d.]+)" y="([-\d.]+)" z="([-\d.]+)"', xml)])
    fs = np.array([[int(a) for a in m] for m in re.findall(r'<triangle v1="(\d+)" v2="(\d+)" v3="(\d+)"', xml)])
    tr = [float(a) for a in re.search(r'transform="1 0 0 0 1 0 0 0 1 ([-\d.]+) ([-\d.]+) ([-\d.]+)"', xml).groups()]
    vs = vs + np.array(tr)
    m = trimesh.Trimesh(vs, fs, process=False)
    lo, hi = m.bounds
    sz, ssz = hi - lo, stl_mesh.bounds[1] - stl_mesh.bounds[0]
    assert np.allclose(sz, ssz, atol=1e-3), (sz, ssz)
    assert abs(m.volume - stl_mesh.volume) < 1e-4 * stl_mesh.volume, (m.volume, stl_mesh.volume)
    assert len(m.faces) == len(stl_mesh.faces), (len(m.faces), len(stl_mesh.faces))
    assert m.is_watertight
    assert lo[0] >= FINAL_MARGIN and lo[1] >= FINAL_MARGIN and hi[0] <= PLATE - FINAL_MARGIN and hi[1] <= PLATE - FINAL_MARGIN and abs(lo[2]) < 1e-3, (lo, hi)
    print(f"  verified {name}: {sz[0]:.1f} x {sz[1]:.1f} x {sz[2]:.1f} mm, x {lo[0]:.1f}..{hi[0]:.1f}, y {lo[1]:.1f}..{hi[1]:.1f}, "
          f"{m.volume / 1000:.1f} cm3, {len(m.faces)} triangles, matches its STL")


WHICH = sys.argv[1] if len(sys.argv) > 1 else "maquette"
if "--export" in sys.argv:
    export_all(WHICH)
if WHICH == "final":
    final_plates()
    sys.exit(0)
OUT, TITLE, PARTS = PLATES[WHICH]

objs, items, bb = [], [], {}
for i, (name, path, pos) in enumerate(PARTS, start=1):
    px, py = pos[0], pos[1]
    m = trimesh.load(path, force="mesh")
    if len(pos) > 2 and pos[2] == "rot90":      # turned 90 degrees about z, to fit the plate
        m.apply_transform(trimesh.transformations.rotation_matrix(3.141592653589793 / 2, [0, 0, 1]))
    lo, sz = m.bounds[0], m.bounds[1] - m.bounds[0]
    tx, ty, tz = px - lo[0], py - lo[1], -lo[2]
    objs.append(mesh_xml(i, name, m))
    items.append(f'<item objectid="{i}" transform="1 0 0 0 1 0 0 0 1 {tx:.4f} {ty:.4f} {tz:.4f}"/>')
    bb[name] = (px, py, px + sz[0], py + sz[1])
    assert px >= MARGIN and py >= MARGIN and px + sz[0] <= PLATE - MARGIN and py + sz[1] <= PLATE - MARGIN, name
for a, b in itertools.combinations(bb, 2):
    A, B = bb[a], bb[b]
    assert max(B[0] - A[2], A[0] - B[2], B[1] - A[3], A[1] - B[3]) >= MIN_GAP, (a, b)

write_3mf(OUT, f"pill_organizer_10bay test print plate: {TITLE}, 256 x 256",
          "Named objects in print orientation on a 256 x 256 plate, origin at the front-left corner. No supports. PLA or PETG, 0.2 mm layers, 3 perimeters.",
          objs, items)
