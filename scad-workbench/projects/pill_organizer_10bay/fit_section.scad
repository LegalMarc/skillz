// ============================================================
// fit_section.scad -- a FULL-SIZE end bay of the real body and the
// matching ends of the real pick lid and fill lid, for a test print
// that checks what the 0.42 maquette cannot.
//
// The maquette scales every clearance and wall with it: at 0.42 the
// fill lid's 0.30 clearance is 0.13, the pick lid's lug clearance
// 0.21 and its lug 1.0mm thick, every 2.4mm wall 1.0mm, and every
// bridge is printed by a full-size nozzle. It judges shape; it
// cannot judge fit or bridging. This section can.
//
// Revision 11 (D46): the section is cut at the LEFT FACE of divider 4, so
// its left wall is that whole 2.4 mm divider, not the 1.2 mm half-divider that
// split away from the front wall on test print 3. It now runs the full height
// and depth of the module (hopper A's mouth and the D42 flare included), so
// "fill tray A from the back" is tested on the real hopper, and the fill lid
// piece drops into the section's own mouth instead of into a separate corner.
//
//   PART="body"     the right-hand end bay, full size: bay 5 from divider 4
//                   to the right side wall, the whole height and depth.
//                   Pour real capsules into hopper A's flared mouth and into
//                   hopper B: they run to tray A (tilted floor, D36, corner
//                   beads, D41) and tray B. Tray A's scalloped front, the stop
//                   block, filler and slim buttress (D43), the front rail
//                   groove with its bevel, the stacked front labels (D45) and
//                   the cubby opening are all in it.
//   PART="pick_lid" the matching end of the pick lid, in print orientation,
//                   at the section's own width: its lug stops against the stop
//                   block, it lifts off pinched between thumb and forefinger,
//                   it has no notch (D44).
//   PART="fill_lid" the matching end of the fill lid, printed flipped as the
//                   real one is. Drop it into the section's mouth: 0.30 all
//                   round, no rocking, lifts out cleanly (D30).
//
// All are cut by the same x plane, so a lid end sits on the section exactly
// as on the body.
// ============================================================
include <params.scad>
use <parts/body.scad>
use <parts/pick_lid.scad>
use <parts/fill_lid.scad>

PART = is_undef(PART) ? "body" : PART;

sec_x0 = wall_x0(4);                         // the left face of divider 4: a full divider is the left wall
sec_z1 = module_h;
sec_y1 = module_d_top;
function wall_x0(k) = wall_out + k * bay_w + (k - 1) * wall_div;   // as body.scad

module body_section() {
    intersection() {
        body_geometry();
        translate([sec_x0, -1, -1]) cube([module_w - sec_x0 + 10, sec_y1 + 2, sec_z1 + 2]);
    }
}

// The lid as print_export.scad prints it: top face on the bed, rotated
// [180 - slope] about X and dropped onto z = 0 -- after cutting it.
pick_lid_drop  = (pickplane_front + pick_lid_gap + pick_lid_tv) * cos(pick_lid_slope);
pick_lid_backy = yB_tray1 - pick_lid_back_clear;
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

// The fill lid's end: the lid from the middle of divider 4 to its right edge, whole
// length, as one world box.
fill_lid_pos = [wall_out + fill_lid_clear, hop_mouth_y0 + fill_lid_clear,
                fill_seat_z + fill_lid_seat_gap];          // as layout.scad
fl_x0 = sec_x0 + wall_div / 2;
fl_y0 = fill_lid_pos[1] - 1; fl_y1 = fill_lid_pos[1] + fill_lid_y + 1;
module fl_box() { translate([fl_x0, fl_y0, fill_seat_z - 1]) cube([module_w - fl_x0 + 10, fl_y1 - fl_y0, 10]); }
// printed flipped (top face on the bed) by the same rotation print_export.scad
// uses -- a rotation, not a mirror, which would print the end's mirror image
module fill_lid_section() {
    translate([0, fl_y1 - fl_y0, fill_lid_pos[2] + lid_t]) rotate([180, 0, 0])
        translate([-fl_x0, -fl_y0, 0])
            intersection() { translate(fill_lid_pos) fill_lid_geometry(); fl_box(); }
}

if (PART == "body") translate([-sec_x0, 0, 0]) body_section();
else if (PART == "pick_lid") lid_section();
else if (PART == "fill_lid") fill_lid_section();
else assert(false, str("Unknown PART '", PART, "'"));
