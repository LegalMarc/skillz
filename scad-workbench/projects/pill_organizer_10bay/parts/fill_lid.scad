// ============================================================
// fill_lid.scad -- the secure lid over one hopper mouth.
// Printed twice: hopper A and hopper B present the same mouth.
//
// Local origin: front-bottom-left corner of the lid plate.
//   +Y toward the back, +Z up (as installed).
//
// Material: PLA or PETG.
// Print orientation: FLIPPED -- plate top face on the bed, the
//   two snap tabs pointing up. Each barb then tapers inward as
//   it rises, so nothing overhangs but the barb's own 1.1mm
//   ledge, which bridges.
//
// Assembly: drop into the mouth and press; both tabs flex
//   inward over the wall and snap into their pockets. Lift it
//   out by the front edge, through the body's relief notch.
//
// EXPECTED_BBOX: [223.8, 68.8, 16.0]
// ============================================================

include <../params.scad>

assert(fill_tab_drop > fill_seat_z - fill_barb_bot_z,
       "the snap tab cannot reach its barb pocket");

module yz_extrude(x0, x1) {
    rotate([90, 0, 90]) translate([0, 0, x0])
        linear_extrude(height = x1 - x0) children();
}

module fill_plate() {
    cube([fill_lid_x, fill_lid_y, lid_t]);
}

// Barb profile in (y, z), local to the tab's outer face at y = 0, pointing -Y.
// Flat top (the retaining face), then a shallow ramp down to nothing so the
// tab cams inward as the lid is pressed home.
BARB = [
    [0,               fill_barb_top_z - fill_seat_z],
    [-fill_tab_barb,  fill_barb_top_z - fill_seat_z],
    [0,               fill_barb_bot_z - fill_seat_z]
];

module fill_tabs() {
    x0 = fill_lid_x / 2 - fill_tab_w / 2;
    // front
    translate([x0, 0, -fill_tab_drop]) cube([fill_tab_w, fill_tab_t, fill_tab_drop]);
    yz_extrude(x0, x0 + fill_tab_w) polygon(BARB);
    // back, mirrored about the lid's mid-depth
    translate([x0, fill_lid_y - fill_tab_t, -fill_tab_drop])
        cube([fill_tab_w, fill_tab_t, fill_tab_drop]);
    translate([0, fill_lid_y, 0]) mirror([0, 1, 0])
        yz_extrude(x0, x0 + fill_tab_w) polygon(BARB);
}

module fill_lid_geometry() { union() { fill_plate(); fill_tabs(); } }

// SUBFEATURES: fill_plate, fill_tabs
SUBFEATURE = is_undef(SUBFEATURE) ? "" : SUBFEATURE;
module subfeature_by_name(name) {
    if (name == "fill_plate") fill_plate();
    else if (name == "fill_tabs") fill_tabs();
    else assert(false, str("Unknown sub-feature '", name, "' in fill_lid.scad"));
}
if (SUBFEATURE != "") subfeature_by_name(SUBFEATURE);
else fill_lid_geometry();
