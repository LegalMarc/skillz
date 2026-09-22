// ============================================================
// calibration_coupon.scad -- PRINT THIS FIRST.
//
// Not part of the assembly; deliberately outside parts/ so the
// validation bundle does not treat it as a component.
//
// doctor.py reports no calibration profile on the machine that
// designed this, which means every fit here is geometry-only
// (tier 2): a groove cut 0.35mm wide of its rail in the MODEL is
// whatever your printer and filament make of it. Two fits in
// this design are sensitive to that, and both are cheap to get
// wrong and annoying to discover after a 20-hour body print:
//
//   1. the joining rail in its groove (rail_clear, 0.35/side)
//   2. the fill lid's snap tab barb in its pocket
//      (fill_tab_barb 1.1 less fill_lid_clear 0.3 = 0.8 engaged)
//
// This coupon prints in under an hour and tells you which column
// fits. Then set the matching value in params.scad.
//
// What is on it (all separate islands, no supports):
//   RAIL   a plate with five male rail stubs, root and tip widths
//          offset by -0.15 .. +0.15, and a loose groove block cut
//          exactly as the body cuts its grooves. Drop the block
//          over each stub: the one that goes down with hand
//          pressure and does not rock is your clearance.
//   SNAP   five miniature fill lids (two tabs, the real barb at
//          -0.15 .. +0.15) and one miniature mouth with the real
//          pocket geometry. Press each lid in, lift it out by
//          its lip: it should click both ways and hold a shake.
//          The lids print flipped, tabs up, exactly like the lid.
//
// Revision 1's coupon carried a gauge for a hinge rod that has
// not existed since revision 2, referenced a parameter that no
// longer exists, and tested no snap at all; nobody noticed
// because the coupon is outside every gate (INCIDENTS.md).
//
// EXPECTED_BODIES: 8 (rail plate with its five stubs, groove block, five mini lids, mouth block)
// ============================================================

include <params.scad>

plate_t   = 4.0;
pitch     = 18.0;
steps     = [-0.15, -0.075, 0.0, 0.075, 0.15];   // offset applied to the nominal fit
label_d   = 0.6;
gap       = 6.0;

module label(s, size = 4) {
    linear_extrude(label_d + 0.1) text(s, size = size, halign = "center", font = "Liberation Sans:style=Bold");
}
function step_label(v) = str(v > 0 ? "+" : "", round(v * 1000));

// ---------------------------------------------------------------- RAIL
module rail_trapezoid(root_w, tip_w, depth, clear = 0) {
    polygon([[ 0,     -(root_w / 2 + clear)],
             [ 0,      (root_w / 2 + clear)],
             [-depth,  (tip_w  / 2 + clear)],
             [-depth, -(tip_w  / 2 + clear)]]);
}
module groove_gauge(off) {
    // A short male rail with its widths offset. The block below drops over it.
    linear_extrude(height = 12)
        rail_trapezoid(rail_root_w + 2 * off, rail_tip_w + 2 * off, rail_out);
}
module rail_plate() {
    w = len(steps) * pitch + 10;
    difference() {
        cube([w, 30, plate_t]);
        for (i = [0 : len(steps) - 1])
            translate([10 + i * pitch, 5, plate_t - label_d]) label(step_label(steps[i]));
        translate([w / 2, 5, plate_t - label_d]) label("RAIL", 3);
    }
    for (i = [0 : len(steps) - 1])
        translate([10 + i * pitch + rail_out, 20, plate_t - 0.01]) groove_gauge(steps[i]);
}
module groove_block() {
    // The body's groove: rail_out + rail_depth_clear deep, rail_clear per side,
    // open top AND bottom so it drops over a standing stub.
    difference() {
        cube([18, 16, 18]);
        translate([18, 8, -1]) linear_extrude(height = 20)
            rail_trapezoid(rail_root_w, rail_tip_w, rail_out + rail_depth_clear, rail_clear);
    }
}

// ---------------------------------------------------------------- SNAP
mini_w      = 22.0;                       // lid width in x
mouth_d     = 30.0;                       // mouth length in y, wall to wall
mini_len    = mouth_d - 2 * fill_lid_clear;
block_h     = 22.0;
seat_z      = block_h - lid_t;            // lid top flush with the block top
pocket_lo   = fill_tab_pocket_z - fill_seat_z;                        // -12.7 below the seat
barb_top    = fill_barb_top_z - fill_seat_z;                          //  -7
barb_bot    = fill_barb_bot_z - fill_seat_z;                          // -10.3

module mini_barb(off) {
    b = fill_tab_barb + off; s = tan(fill_tab_return_deg);
    polygon([[fill_tab_inset + fill_tab_root, barb_top + fill_tab_root * s],
             [-b,                             barb_top - (b + fill_tab_inset) * s],
             [fill_tab_inset + fill_tab_root, barb_bot]]);
}
module mini_lid(off) {
    // As modelled: plate on z 0..lid_t, tabs hanging below. Flipped for print by the caller.
    x0 = mini_w / 2 - fill_tab_w / 2;
    difference() {
        cube([mini_w, mini_len, lid_t]);
        translate([mini_w / 2, mini_len / 2 - 2, -0.1]) mirror([1, 0, 0]) label(step_label(off));
    }
    for (side = [0, 1]) {
        translate([0, side == 0 ? 0 : mini_len, 0]) mirror([0, side, 0]) {
            translate([x0, fill_tab_inset, -fill_tab_drop]) cube([fill_tab_w, fill_tab_t, fill_tab_drop + 1]);
            rotate([90, 0, 90]) translate([0, 0, x0]) linear_extrude(height = fill_tab_w) mini_barb(off);
        }
    }
}
module mini_lid_print(off) { translate([0, mini_len, lid_t]) rotate([180, 0, 0]) mini_lid(off); }

module mouth_block() {
    W = mini_w + 2; L = mouth_d + 2 * wall_div;
    difference() {
        cube([W, L, block_h]);
        // the mouth above the seat, full width; below it a narrower well so the
        // lid rests on 1.5mm side ledges at seat_z, as it rests on the body's
        translate([1, wall_div, seat_z]) cube([mini_w, mouth_d, lid_t + 1]);
        translate([2.5, wall_div, seat_z + pocket_lo - 2]) cube([mini_w - 3, mouth_d, -pocket_lo + 2.01]);
        // the two barb pockets, cut into the walls as fill_seat_cut() cuts them
        for (y = [wall_div - fill_tab_barb, wall_div + mouth_d - 0.01])
            translate([W / 2 - fill_tab_w / 2 - 0.5, y, seat_z + pocket_lo])
                cube([fill_tab_w + 1, fill_tab_barb + 0.01, fill_tab_pocket_h]);
        // a pull notch in one wall, as the body has, to lift the lid by
        translate([W / 2 - 6, -1, seat_z]) cube([12, wall_div + 2, lid_t + 1]);
        translate([W / 2, L + 1, block_h - label_d]) rotate([0, 0, 180]) label("SNAP", 3);
    }
}

assert(seat_z + pocket_lo - 2 > 1.0, "the mini mouth's well runs through its own floor");
assert(fill_tab_barb + min(steps) - fill_lid_clear > 0.4, "the loosest snap step has under 0.4mm of engagement");

// ---------------------------------------------------------------- layout
module coupon() {
    rail_plate();
    translate([len(steps) * pitch + 10 + gap, 0, 0]) groove_block();
    for (i = [0 : len(steps) - 1])
        translate([i * (mini_w + gap), 30 + gap, 0]) mini_lid_print(steps[i]);
    translate([len(steps) * (mini_w + gap) + gap, 30 + gap, 0]) mouth_block();
}

coupon();
echo(str("coupon: snap engagement per step ",
         [for (s = steps) fill_tab_barb + s - fill_lid_clear], "; rail clearance per side ", rail_clear));
