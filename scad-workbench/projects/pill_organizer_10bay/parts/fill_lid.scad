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
// Print orientation: FLIPPED -- plate top face on the bed. The
//   pull lip is in the plate's own plane; the underside lead-in
//   chamfer is a 45 degree face at the top of the print.
//
// Fit (D30): the lid drops into the recess above the seat
//   ledges with fill_lid_clear all round and rests on them. It
//   is held by gravity, which is all the brief needs -- it stays
//   put when set down. Revisions 5-7 had two snap tabs; test
//   print 1 broke every one, because a tab printed standing up
//   bends across its layer lines. To lift: hook a fingertip under
//   the pull lip, which stands out over tray B's air.
//
// EXPECTED_BBOX: [233.8, 129.0, 3.0]
// ============================================================

include <../params.scad>

module yz_extrude(x0, x1) {
    rotate([90, 0, 90]) translate([0, 0, x0])
        linear_extrude(height = x1 - x0) children();
}

// The plate and the pull lip (D23) are each a convex outline -- a rounded
// rectangle -- so each can be chamfered by hull(): the outline lid_t minus
// lid_chamfer tall, hulled with the outline inset by lid_chamfer at the top.
// A single non-convex outline cannot be chamfered that way (hull fills the
// concave corners where the lip meets the plate), and a Minkowski cone left
// zero-area slivers at exactly those corners (revision 7).
//
// Where the lip meets the plate (D27, revision 7): the lip's top is FLUSH with
// the plate's top, because that face goes on the bed when the lid is printed
// flipped and a lip 0.1mm above the bed prints in mid-air. So the lip's solid
// ends at y = lip_back, INSIDE the plate's front chamfer band (0 < lip_back <
// lid_chamfer), where the plate's top is already below lid_t: the two top
// faces lie on one plane but never overlap. Its underside sits lip_in above
// the plate's underside, so the two bottom faces never overlap either. The
// lip's own chamfer runs along its front and sides only; its back edge is
// vertical and buried.
module rounded_rect(w, d) {
    offset(r = lid_edge_r) offset(r = -lid_edge_r) square([w, d]);
}
// The underside perimeter carries a fill_lead_in chamfer (D30): the lid now
// simply drops into its recess and rests on the seat ledges, and the chamfer
// is what lets it find the recess. Printed flipped, it is a 45 degree face
// near the top of the print.
module fill_plate_slab() {
    hull() {
        linear_extrude(height = 0.01)
            offset(delta = -fill_lead_in) rounded_rect(fill_lid_x, fill_lid_y);
        translate([0, 0, fill_lead_in])
            linear_extrude(height = lid_t - lid_chamfer - fill_lead_in) rounded_rect(fill_lid_x, fill_lid_y);
        translate([0, 0, lid_t - 0.01]) linear_extrude(height = 0.01)
            offset(delta = -lid_chamfer) rounded_rect(fill_lid_x, fill_lid_y);
    }
}
lip_back = lid_chamfer - 0.05;     // where the lip's solid ends, inside the chamfer band
lip_in   = 0.1;                    // its underside, above the plate's underside
// The lip's underside perimeter (D48) is a fill_lip_chamfer bevel, where a fingertip hooks
// under it. Its first layer is the outline inset on the front and the sides only: the back
// end is buried in the plate, whose own lead-in chamfer lies above the lip's underside there,
// so insetting it would leave a 0.05 mm ledge under the plate.
module fill_lip_slab() {
    d = fill_lip_len + lip_back; c = fill_lip_chamfer;
    translate([fill_lid_x / 2 - fill_lip_w / 2, -fill_lip_len, 0]) hull() {
        translate([0, 0, lip_in]) linear_extrude(height = 0.01) union() {
            offset(delta = -c) rounded_rect(fill_lip_w, d);
            translate([c, d - c - 0.5]) square([fill_lip_w - 2 * c, c + 0.5]);
        }
        translate([0, 0, lip_in + c]) linear_extrude(height = lid_t - lid_chamfer - lip_in - c)
            rounded_rect(fill_lip_w, d);
        translate([lid_chamfer, lid_chamfer, lid_t - 0.01]) linear_extrude(height = 0.01)
            square([fill_lip_w - 2 * lid_chamfer, d - lid_chamfer]);
    }
}
assert(lip_back > 0 && lip_back < lid_chamfer,
       "the lip must end inside the plate's chamfer band, or its top face overlaps the plate's");
module fill_plate() { fill_plate_slab(); fill_lip_slab(); }

module fill_lid_geometry() { fill_plate(); }

// SUBFEATURES: fill_plate_slab, fill_lip_slab
SUBFEATURE = is_undef(SUBFEATURE) ? "" : SUBFEATURE;
module subfeature_by_name(name) {
    if (name == "fill_plate_slab") fill_plate_slab();
    else if (name == "fill_lip_slab") fill_lip_slab();
    else assert(false, str("Unknown sub-feature '", name, "' in fill_lid.scad"));
}
if (SUBFEATURE != "") subfeature_by_name(SUBFEATURE);
else fill_lid_geometry();
