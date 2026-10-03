// ============================================================
// fit_section.scad -- a FULL-SIZE corner of the real body and the
// matching end of the real pick lid, for a test print that checks
// what the 0.42 maquette cannot.
//
// The maquette scales every clearance and wall with it: at 0.42 the
// fill lid's 0.30 clearance is 0.13, the pick lid's lug clearance
// 0.21 and its lug 1.0mm thick, every 2.4mm wall 1.0mm, and every
// bridge is printed by a full-size nozzle. It judges shape; it
// cannot judge fit or bridging. This section can.
//
//   PART="body"     the right-hand end of the body, full size: bay 5
//                   from the middle of divider 4 to the right side
//                   wall, front 70mm, up to z 100. Tray A with its
//                   scalloped front and label recess, the mouth into
//                   tray A with its chamfered corners, the flat porch
//                   bridge (D29), tray B, the opening into hopper B,
//                   the start of the vaulted chute in cross-section,
//                   and the front joining groove breaking out
//                   through the top (the corner test print 1 tore).
//   PART="pick_lid" the matching right-hand end of the pick lid, in
//                   print orientation, with its right locating lug
//                   (D32). Lay it on the section to check seating,
//                   the lug's fit against the side wall, and the
//                   skirt over the scalloped front.
//
// Both are cut by the same x plane, through the middle of divider 4,
// so the lid end sits on the section exactly as on the body.
// ============================================================
include <params.scad>
use <parts/body.scad>
use <parts/pick_lid.scad>

PART = is_undef(PART) ? "body" : PART;

sec_x0 = wall_x0(4) + wall_div / 2;          // the middle of divider 4
sec_y1 = 70.0;
sec_z1 = 100.0;
function wall_x0(k) = wall_out + k * bay_w + (k - 1) * wall_div;   // as body.scad

module body_section() {
    intersection() {
        body_geometry();
        translate([sec_x0, -1, -1]) cube([module_w - sec_x0 + 10, sec_y1 + 1, sec_z1 + 1]);
    }
}

// The lid as print_export.scad prints it: top face on the bed, rotated
// [180 - slope] about X and dropped onto z = 0 -- after cutting it.
pick_lid_drop  = (pickplane_front + pick_lid_gap + pick_lid_tv) * cos(pick_lid_slope);
pick_lid_backy = yB_tray1 - pick_lid_clear;
pick_lid_shift = pick_lid_backy * cos(pick_lid_slope)
               + (pickplane(pick_lid_backy) + pick_lid_gap + pick_lid_tv) * sin(pick_lid_slope);
lid_x0 = sec_x0 - (module_w - pick_lid_w) / 2;  // the same plane, in the lid's own x

module lid_section() {
    translate([-lid_x0, pick_lid_shift, pick_lid_drop])
        rotate([180 - pick_lid_slope, 0, 0])
            intersection() {
                pick_lid_geometry();
                translate([lid_x0, -10, 0]) cube([pick_lid_w, 100, 200]);
            }
}

if (PART == "body") translate([-sec_x0, 0, 0]) body_section();
else if (PART == "pick_lid") lid_section();
else assert(false, str("Unknown PART '", PART, "'"));
