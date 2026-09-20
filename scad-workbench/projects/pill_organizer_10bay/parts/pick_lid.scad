// ============================================================
// pick_lid.scad -- the everyday lid over one row of five pick
// trays. Printed twice: tier A and tier B are dimensionally
// identical, so one part serves both.
//
// Local origin: ON THE HINGE AXIS, at the lid's left end.
//   +Y toward the back, +Z up. Chosen so the assembly rotation
//   is a plain rotate([t,0,0]) about this file's own origin,
//   which is what joints.json's motion block drives.
//
// Material: PLA or PETG.
// Print orientation: plate face down, C-clips pointing up. No
//   supports: the clip's widest underside sits 28 deg from
//   vertical and its lowest 0.85mm is buried in the plate.
//
// Assembly: press straight down onto the body's hinge rod; the
//   five C-clips snap over it. Lifts off with a deliberate
//   forward pull -- the working load never acts that way.
//
// EXPECTED_BBOX: [229.0, 43.65, 11.546]
// ============================================================

include <../params.scad>

use_param("hinge_rod_d", "pick_lid_c_clip",
          "clip bore must clear the rod and still retain it");
assert(hinge_bore_d > hinge_rod_d && hinge_snap_gap < hinge_rod_d,
       "the clip bore must be larger than the rod and its mouth smaller, or the hinge either binds or falls off");

lid_dx   = 0.5;                                  // body X of the lid's left edge
ly_front = -(hinge_rod_y + pick_lid_overhang);   // -38.80
ly_back  = pick_lid_plate_y1 - hinge_rod_y;      //  +4.85
lz_bot   = pocketA_rim_z + pick_lid_rest_gap - hinge_rod_z;   //  -6.70
lz_top   = lz_bot + lid_t;                       //  -4.00

// Extrude a (y, z) profile along X.
module yz_extrude(x0, x1) {
    rotate([90, 0, 90]) translate([0, 0, x0])
        linear_extrude(height = x1 - x0) children();
}

PLATE = [
    [ly_front,                        lz_bot],
    [ly_back,                         lz_bot],
    [ly_back,                         lz_top],
    [ly_front + pick_lid_front_cham,  lz_top],
    [ly_front,                        lz_top - pick_lid_front_cham]
];

module pick_plate() { yz_extrude(0, pick_lid_w) polygon(PLATE); }

// One C-clip: a ring anchored to the plate on its lower-BACK quadrant only,
// so both lips stay long and compliant. Bore and mouth are cut in
// pick_lid_geometry(), after the union, so the connector becomes part of the ring.
module clip_blank_one(cx) {
    translate([cx - hinge_clip_w / 2, 0, 0]) {
        rotate([0, 90, 0]) cylinder(d = 2 * hinge_clip_or, h = hinge_clip_w);
        translate([0, 2.0, lz_bot])
            cube([hinge_clip_w, hinge_clip_or - 2.0, -lz_bot]);
    }
}

module pick_clips() {
    for (i = [0 : bays - 1]) clip_blank_one(bay_center_x(i) - lid_dx);
}

// The mouth: a funnel that flares at the outer surface so the rod finds it,
// then holds hinge_snap_gap across the retaining lips.
MOUTH_FUNNEL = [
    [0,               -hinge_snap_gap / 2],
    [-hinge_clip_or,  -hinge_snap_gap / 2 - 0.7],
    [-30,             -hinge_snap_gap / 2 - 0.7],
    [-30,              hinge_snap_gap / 2 + 0.7],
    [-hinge_clip_or,   hinge_snap_gap / 2 + 0.7],
    [0,                hinge_snap_gap / 2]
];

module clip_cuts() {
    for (i = [0 : bays - 1]) {
        cx = bay_center_x(i) - lid_dx;
        translate([cx - hinge_clip_w / 2 - 0.01, 0, 0])
            rotate([0, 90, 0]) cylinder(d = hinge_bore_d, h = hinge_clip_w + 0.02);
        yz_extrude(cx - hinge_clip_w / 2 - 0.01, cx + hinge_clip_w / 2 + 0.01)
            polygon(MOUTH_FUNNEL);
    }
}

// Clearance for the body's six hinge webs. A cylinder about the hinge axis,
// not a box: the webs surround the pivot, so only a swept-radius relief clears
// them at EVERY angle rather than just at the closed position.
module web_notches() {
    for (k = [0 : bays])
        translate([wall_x0(k) - lid_dx - pick_lid_web_clear, 0, 0])
            rotate([0, 90, 0])
                cylinder(r = pick_lid_web_r,
                         h = wall_x1(k) - wall_x0(k) + 2 * pick_lid_web_clear);
}

function wall_x0(k) = k == 0 ? 0
                    : k == bays ? module_w - wall_out
                    : wall_out + k * bay_w + (k - 1) * wall_div;
function wall_x1(k) = k == 0 ? wall_out
                    : k == bays ? module_w
                    : wall_x0(k) + wall_div;

// Everything behind and below the hinge axis is trimmed back to
// pick_lid_swing_r, so the rear edge sweeps clear of the tray rim instead of
// ploughing into it. Found by the motion sweep, not by looking at a render.
module swing_relief() {
    difference() {
        translate([-1, 0, -40]) cube([pick_lid_w + 2, 40, 40]);
        translate([-1, 0, 0]) rotate([0, 90, 0])
            cylinder(r = pick_lid_swing_r, h = pick_lid_w + 2);
    }
}

module pick_lid_geometry() {
    difference() {
        union() { pick_plate(); pick_clips(); }
        clip_cuts();
        web_notches();
        swing_relief();
    }
}

// SUBFEATURES: pick_plate, pick_clips
SUBFEATURE = is_undef(SUBFEATURE) ? "" : SUBFEATURE;
module subfeature_by_name(name) {
    if (name == "pick_plate") pick_plate();
    else if (name == "pick_clips") pick_clips();
    else assert(false, str("Unknown sub-feature '", name, "' in pick_lid.scad"));
}
if (SUBFEATURE != "") subfeature_by_name(SUBFEATURE);
else pick_lid_geometry();
