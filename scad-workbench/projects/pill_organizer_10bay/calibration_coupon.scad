// ============================================================
// calibration_coupon.scad -- PRINT THIS FIRST.
//
// Not part of the assembly; deliberately outside parts/ so the
// validation bundle does not treat it as a component.
//
// doctor.py reports no calibration profile on the machine that
// designed this, which means every fit here is geometry-only
// (tier 2): a 6.30mm bore comes out 6.30mm in the MODEL, and
// what your printer and filament actually produce at that
// number is unknown. Three fits in this design are sensitive
// to that, and all three are cheap to get wrong and annoying
// to discover after a 20-hour print:
//
//   1. the pick lid's C-clip on its 6.0mm hinge rod
//   2. the fill lid's snap tab barb in its pocket
//   3. the joining rail in its groove
//
// This coupon prints in a few minutes and tells you which
// column fits. Then set the matching value in params.scad.
// ============================================================

include <params.scad>

plate_t   = 4.0;
pitch     = 18.0;
steps     = [-0.15, -0.075, 0.0, 0.075, 0.15];   // offset applied to the nominal fit
label_d   = 0.6;

module rod_gauge(off) {
    // A rod at the modelled hinge diameter; the lid's clip should turn freely
    // on the one that matches, with no side play you can feel.
    cylinder(d = hinge_rod_d + off, h = 14, $fn = 64);
}

module groove_gauge(off) {
    // A short length of the joining rail's male trapezoid. The right one
    // slides into a printed groove with hand pressure and no rock.
    linear_extrude(height = 12)
        polygon([[0, -(rail_root_w / 2 + off)],
                 [0,  (rail_root_w / 2 + off)],
                 [-rail_out,  (rail_tip_w / 2 + off)],
                 [-rail_out, -(rail_tip_w / 2 + off)]]);
}

module coupon() {
    w = len(steps) * pitch + 10;
    difference() {
        cube([w, 44, plate_t]);
        for (i = [0 : len(steps) - 1])
            translate([10 + i * pitch, 6, plate_t - label_d])
                linear_extrude(label_d + 0.1)
                    text(str(steps[i] > 0 ? "+" : "", steps[i] * 1000),
                         size = 4, halign = "center");
    }
    for (i = [0 : len(steps) - 1]) {
        translate([10 + i * pitch, 16, plate_t])              rod_gauge(steps[i]);
        translate([10 + i * pitch + rail_out, 34, plate_t])   groove_gauge(steps[i]);
    }
}

coupon();
