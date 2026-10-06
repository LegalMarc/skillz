// ============================================================
// calibration_coupon.scad -- PRINT THIS FIRST.
//
// Not part of the assembly; deliberately outside parts/ so the
// validation bundle does not treat it as a component.
//
// One fit in this design depends on how your printer and
// filament come out rather than on the geometry: the joining
// rail in its groove. Test print 1's coupon (printed with a brim
// that fused into the walls) read 0.50 per side; test print 2,
// with no brim, found the block loose on every stub down to 0.30;
// test print 3 (Generic PETG, no brim) found the "0" stub (0.20)
// the best but slightly tight: "a little looser, around -10 to -15".
// rail_clear became 0.215 (D47); but the D43 slim rail's coupon
// (0.265 .. 0.165) was too tight on every stub, so D51 sets 0.40
// as a best guess; its coupon (0.50 .. 0.30) was loose on every
// stub, even 0.30. The fit is between 0.265 (too tight) and 0.30
// (loose), so D55 centres on 0.28 and this coupon brackets it
// 0.30 .. 0.26 in 0.01 steps, at the printer's resolution limit.
// The reading is for the
// filament it was printed in: use the same one for the unit, or
// run the coupon again.
//
//   RAIL   a plate with five male rail stubs, widths offset by
//          -20 .. +20 (microns per side, relative to the default
//          rail_clear; clearance 0.30 .. 0.26), and a loose groove
//          block cut exactly as the body cuts its grooves
//          (rail_clear per side). Turn the block bed-face UP and
//          drop it over each stub: the one that goes down with
//          hand pressure and does not rock is your fit. If it is
//          not "0", tell the designer the label.
//          The groove's bed-face mouth is chamfered 0.5mm so the
//          first layers' squash (elephant's foot) does not read
//          as a tight fit -- but enter from the other face anyway.
//
// The fill lid's snap test is gone with the snap tabs (D30):
// the lid now rests in its recess by gravity. Its 0.30mm
// clearance is checked full size by fit_section.scad's fill-lid
// corner -- test print 1's lid was a 0.42 maquette, where every
// clearance shrank with it, so it confirmed nothing.
//
// Print with NO brim: a brim's first layers squeeze the groove
// block's opening and read as a tighter fit than it is.
//
// EXPECTED_BODIES: 2 (rail plate with its five stubs, groove block)
// ============================================================

include <params.scad>

plate_t   = 4.0;
pitch     = 18.0;
steps     = [-0.02, -0.01, 0.0, 0.01, 0.02];    // offset applied to the male's half-width
label_d   = 0.6;
gap       = 6.0;

module label(s, size = 4) {
    linear_extrude(label_d + 0.1) text(s, size = size, halign = "center", font = "Liberation Sans:style=Bold");
}
function step_label(v) = str(v > 0 ? "+" : "", round(v * 1000));

module rail_trapezoid(root_w, tip_w, depth, clear = 0) {
    polygon([[ 0,     -(root_w / 2 + clear)],
             [ 0,      (root_w / 2 + clear)],
             [-depth,  (tip_w  / 2 + clear)],
             [-depth, -(tip_w  / 2 + clear)]]);
}
module groove_gauge(off) {
    linear_extrude(height = 12)
        rail_trapezoid(rail_root_w + 2 * off, rail_tip_w + 2 * off, rail_out);
}
module rail_plate() {
    w = len(steps) * pitch + 10;
    difference() {
        cube([w, 30, plate_t]);
        for (i = [0 : len(steps) - 1])
            translate([10 + i * pitch, 5, plate_t - label_d]) label(step_label(steps[i]));
        translate([w / 2, 25, plate_t - label_d]) label(str("RAIL ", rail_clear), 2.6);
    }
    for (i = [0 : len(steps) - 1])
        translate([10 + i * pitch + rail_out, 17, plate_t - 0.01]) groove_gauge(steps[i]);
}
module groove_block() {
    // The body's groove: rail_out + rail_depth_clear deep, rail_clear per side,
    // open top AND bottom so it drops over a standing stub.
    difference() {
        cube([18, 16, 18]);
        translate([18, 8, -1]) linear_extrude(height = 20)
            rail_trapezoid(rail_root_w, rail_tip_w, rail_out + rail_depth_clear, rail_clear);
        // elephant's-foot relief: the groove's outline grown 0.5 at the bed,
        // tapering to nothing 0.5 up -- a 45 degree chamfer round the mouth
        translate([18, 8, 0]) hull() {
            translate([0, 0, -1]) linear_extrude(height = 1.01)
                offset(delta = 0.5)
                    rail_trapezoid(rail_root_w, rail_tip_w, rail_out + rail_depth_clear, rail_clear);
            linear_extrude(height = 0.5)
                rail_trapezoid(rail_root_w, rail_tip_w, rail_out + rail_depth_clear, rail_clear);
        }
    }
}

module coupon() {
    rail_plate();
    translate([len(steps) * pitch + 10 + gap, 0, 0]) groove_block();
}

coupon();
echo(str("coupon: rail clearance per side ", [for (s = steps) rail_clear - s]));
