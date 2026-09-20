// ============================================================
// fill_lid.scad -- ONE lid over BOTH hopper mouths. Both mouths
// finish at hopper_rim, which is what lets a single flat plate
// cover them.
//
// Local origin: front-bottom-left corner of the lid plate.
//   +Y toward the back, +Z up (as installed). The pull lip
//   extends to -Y from that corner.
//
// Material: PLA or PETG.
// Print orientation: FLIPPED -- plate top face on the bed, the
//   two snap tabs pointing up. Each barb then tapers inward as
//   it rises, so nothing overhangs but the barb's own 1.1mm
//   ledge, which bridges. The pull lip is in the plate's own
//   plane, so it prints as part of the first layers.
//
// Assembly: drop into the mouth and press; both tabs flex
//   inward over the wall and snap into their pockets. To lift:
//   hook a fingertip under the pull lip, which stands out over
//   tray B's air in front of the mouth, and pull up. The barbs'
//   35 degree return faces cam the tabs inward and release (D23).
//
// EXPECTED_BBOX: [223.8, 112.9, 15.0]
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
    // Pull lip (D23): the plate carried forward, at full thickness, across the
    // notch cut in the wall in front of the mouth and out over tray B. It
    // overlaps the plate by 1mm so the union is volumetric, not a shared face.
    translate([fill_lid_x / 2 - fill_lip_w / 2, -fill_lip_len, 0])
        cube([fill_lip_w, fill_lip_len + 1.0, lid_t]);
}

// Barb profile in (y, z), local to the tab's outer face at y = 0, pointing -Y.
// The retaining face slopes DOWN toward the barb's tip at fill_tab_return_deg
// (D23), so a pull on the lid cams the tab inward instead of tearing the
// pocket; below it a shallow ramp lets the tab cam in as the lid is pressed
// home.
BARB = [
    [0.5,            fill_barb_top_z - fill_seat_z],
    [-fill_tab_barb, fill_barb_top_z - fill_seat_z - fill_tab_barb * tan(fill_tab_return_deg)],
    [0.5,            fill_barb_bot_z - fill_seat_z]
];

assert(fill_barb_top_z - fill_tab_barb * tan(fill_tab_return_deg) > fill_barb_bot_z + 0.5,
       "the barb's return face runs down into its own entry ramp");

module fill_tabs() {
    x0 = fill_lid_x / 2 - fill_tab_w / 2;
    // front
    // Each tab runs 1mm up INTO the plate and each barb 0.5mm into its tab, so
    // every union here overlaps volumetrically instead of sharing a face.
    translate([x0, 0, -fill_tab_drop]) cube([fill_tab_w, fill_tab_t, fill_tab_drop + 1.0]);
    yz_extrude(x0, x0 + fill_tab_w) polygon(BARB);
    // back, mirrored about the lid's mid-depth
    translate([x0, fill_lid_y - fill_tab_t, -fill_tab_drop])
        cube([fill_tab_w, fill_tab_t, fill_tab_drop + 1.0]);
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
