// ============================================================
// print_export.scad -- one part, in PRINT orientation, dropped
// onto z = 0. This is the file the STLs in build/print_ready/
// and build/maquette/ are exported from:
//
//   scad -D 'PART="pick_lid"' -o build/print_ready/pick_lid.stl print_export.scad
//   scad -D 'PART="body"' -o build/maquette/body.stl test_model.scad   (scaled)
//
// Orientations (README.md, Bill of materials):
//   body      as modelled, flat on its base.
//   pick_lid  plate TOP face on the bed, skirt rising at about
//             50 degrees. That is rotate([180 - pick_lid_slope,
//             0, 0]): revision 5 used -pick_lid_slope, which
//             also lays the plate flat but leaves the skirt
//             pointing DOWN, so the "print-ready" lid stood on
//             its skirt edge with the plate 14mm in the air
//             (INCIDENTS.md, revision 6).
//   fill_lid  flipped, plate top face on the bed, tabs up.
//
// The drop to z = 0 is analytic, from the same params the parts
// are built from -- OpenSCAD cannot measure its own mesh.
// ============================================================
include <params.scad>
use <parts/body.scad>
use <parts/pick_lid.scad>
use <parts/fill_lid.scad>

PART  = is_undef(PART) ? "body" : PART;
// test_model.scad sets TEST_SCALE before including this file. It cannot set
// SCALE itself: OpenSCAD evaluates a re-assigned variable at its FIRST
// position with its LAST expression, so the is_undef() default here would
// win and the maquette would come out full size (it did, once).
SCALE = is_undef(SCALE) ? (is_undef(TEST_SCALE) ? 1.0 : TEST_SCALE) : SCALE;

// Lowest point of the rotated pick lid: the plate's top face, which after the
// rotation is a horizontal plane at -(plate top at y = 0) * cos(slope). Its
// most negative Y is the plate's top-back corner; shifted so the part starts
// at y = 0 like the others.
pick_lid_drop  = (pickplane_front + pick_lid_gap + pick_lid_tv) * cos(pick_lid_slope);
pick_lid_backy = yB_tray1 - pick_lid_clear;
pick_lid_shift = pick_lid_backy * cos(pick_lid_slope)
               + (pickplane(pick_lid_backy) + pick_lid_gap + pick_lid_tv) * sin(pick_lid_slope);

module print_body()     { body_geometry(); }
module print_pick_lid() { translate([0, pick_lid_shift, pick_lid_drop])
                              rotate([180 - pick_lid_slope, 0, 0]) pick_lid_geometry(); }
module print_fill_lid() { translate([0, 0, lid_t]) rotate([180, 0, 0]) fill_lid_geometry(); }

scale(SCALE) {
    if      (PART == "body")     print_body();
    else if (PART == "pick_lid") print_pick_lid();
    else if (PART == "fill_lid") print_fill_lid();
    else assert(false, str("Unknown PART '", PART, "'"));
}
echo(str("print_export: ", PART, " at scale ", SCALE));
