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
//                   wall, up to z 165 (6 mm above tray B's rim) and
//                   back to where hopper B's ramp rises through that
//                   height, so hopper B is a closed funnel open only
//                   at the top. Pour real capsules in: they run down
//                   the ramp, out under the outlet and pile in tray B
//                   -- it must stay below the wall in front of it
//                   (D33). Drop more in the chute's open back end and
//                   they run down the 40 degree chute (D36) onto tray
//                   A's tilted floor and should keep sliding forward as
//                   you pick from the front: THE test of revision 10.
//                   Also in it: tray A's scalloped front, with the
//                   pillar beside the right side wall (D38); the mouth
//                   into tray A with its chamfered corners; the flat
//                   chute-ceiling bridge under tray B (D29); the
//                   opening into hopper B; the start of the vaulted
//                   chute in cross-section; and the front joining
//                   groove breaking out through the top, now with a
//                   4.4 mm skin and a longer buttress (D39).
//   PART="pick_lid" the matching right-hand end of the pick lid (cut back
//                   far enough to include the right finger notch), in
//                   print orientation, with its right retention lug
//                   (D38). Lay it on the section: the lug drops in
//                   directly behind the pillar (0.5 mm clear), the
//                   plate sits flat on the plane, the skirt covers
//                   the scalloped front. Then tip the section up and
//                   try to slide the lid down the slope: it must stop
//                   after under 1 mm. Lift it straight off; it must
//                   come without catching. "FRONT" is on the skirt.
//   PART="mouth"    the right-front corner of the fill mouth, full
//                   size: the top 11mm of the body there, with its
//                   seat ledges and the half divider it bears on.
//   PART="fill_lid" the matching corner of the fill lid, printed
//                   flipped as the real one is. Drop it into the
//                   mouth corner: 0.30 all round, no rocking, lifts
//                   out cleanly (D30).
//
// Both are cut by the same x plane, through the middle of divider 4,
// so the lid end sits on the section exactly as on the body.
// ============================================================
include <params.scad>
use <parts/body.scad>
use <parts/pick_lid.scad>
use <parts/fill_lid.scad>

PART = is_undef(PART) ? "body" : PART;

sec_x0 = wall_x0(4) + wall_div / 2;          // the middle of divider 4
sec_z1 = 165.0;     // 6.4 mm over tray B's rim (158.6): the wall behind the lid's back edge is there
                    // (review F2). Hopper B's ramp passes 166 at y 152, the most the closed funnel allows
// back to where hopper B's ramp rises 1mm past the top cut, so the funnel's
// floor leaves through the top and its back is closed
sec_y1 = ceil(yB_tray1 + (sec_z1 + 1 - rampB_foot) / ramp_tan);
assert(sec_y1 < yB_hop1 - 5, "the section's back cut reaches hopper B's back wall");
assert(rampB(sec_y1) > sec_z1, "hopper B's ramp is not above the top cut at the back -- the funnel would be open at the back");
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
pick_lid_backy = yB_tray1 - pick_lid_back_clear;
pick_lid_shift = pick_lid_backy * cos(pick_lid_slope)
               + (pickplane(pick_lid_backy) + pick_lid_gap + pick_lid_tv) * sin(pick_lid_slope);
// The lid piece is cut wider than the body section, back to just before the right-hand
// finger notch (bay 4's centre, x 156..178), so that the section's lid has a
// notch to lift by. Its left part overhangs air: it is a lid end, not a lid.
lid_x0 = min(sec_x0 - (module_w - pick_lid_w) / 2,
             pick_notch_x[1] - pick_notch_w / 2 - (module_w - pick_lid_w) / 2 - 8);

module lid_section() {
    translate([-lid_x0, pick_lid_shift, pick_lid_drop])
        rotate([180 - pick_lid_slope, 0, 0])
            intersection() {
                pick_lid_geometry();
                translate([lid_x0, -10, 0]) cube([pick_lid_w, 100, 200]);
            }
}

// The fill mouth's right-front corner, and the matching corner of the lid --
// one world box for both, clear of rail 2's groove behind it.
mouth_y0 = yB_tray1 - 3;        // 58.2, in front of the mouth's front wall: air at this height
mouth_y1 = yB_wall1 + 24.4;     // 24 mm into the mouth, short of rail 2's groove
mouth_z0 = fill_seat_z - 8;     // 130
assert(mouth_y1 < rail2_y - rail_root_w / 2 - rail_clear - 2, "the mouth corner cuts into rail 2's groove");
fill_lid_pos = [wall_out + fill_lid_clear, hop_mouth_y0 + fill_lid_clear,
                fill_seat_z + fill_lid_seat_gap];          // as layout.scad
module mouth_box() { translate([sec_x0, mouth_y0, mouth_z0]) cube([module_w - sec_x0 + 10, mouth_y1 - mouth_y0, 50]); }
module mouth_section() {
    translate([-sec_x0, -mouth_y0, -mouth_z0]) intersection() { body_geometry(); mouth_box(); }
}
// printed flipped (top face on the bed) by the same rotation print_export.scad
// uses -- a rotation, not a mirror, which would print the corner's mirror image
module fill_lid_section() {
    translate([0, mouth_y1 - mouth_y0, fill_lid_pos[2] + lid_t]) rotate([180, 0, 0])
        translate([-sec_x0, -mouth_y0, 0])
            intersection() { translate(fill_lid_pos) fill_lid_geometry(); mouth_box(); }
}

if (PART == "body") translate([-sec_x0, 0, 0]) body_section();
else if (PART == "pick_lid") lid_section();
else if (PART == "mouth") mouth_section();
else if (PART == "fill_lid") fill_lid_section();
else assert(false, str("Unknown PART '", PART, "'"));
