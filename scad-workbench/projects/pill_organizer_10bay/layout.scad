// Origin: front-bottom-left outer corner of the body.
// +X right, +Y back, +Z up. Millimetres.
//
// The two pick lids and the two fill lids are the SAME two parts placed twice:
// tier B is tier A shifted by [0, tier_dy, tier_dz], which is the whole point
// of building the body from one repeated section.
include <params.scad>

tier_dy = yA_back - wall_out;      // 113.2
tier_dz = tier_lift;               // 101.0
lid_dx  = 0.5;

LAYOUT = [
    ["body",       [0, 0, 0], [0, 0, 0]],
    ["pick_lid",   [lid_dx, hinge_rod_y,           hinge_rod_z],           [0, 0, 0]],
    ["pick_lid_b", [lid_dx, hinge_rod_y + tier_dy, hinge_rod_z + tier_dz], [0, 0, 0]],
    ["fill_lid",   [wall_out + fill_lid_clear, hop_mouth_y0 + fill_lid_clear,           fill_seat_z + fill_lid_seat_gap],           [0, 0, 0]],
    ["fill_lid_b", [wall_out + fill_lid_clear, hop_mouth_y0 + fill_lid_clear + tier_dy, fill_seat_z + fill_lid_seat_gap + tier_dz], [0, 0, 0]]
];

function layout_pos(name, i=0) = i >= len(LAYOUT) ? undef :
    LAYOUT[i][0] == name ? LAYOUT[i][1] : layout_pos(name, i+1);
function layout_rot(name, i=0) = i >= len(LAYOUT) ? undef :
    LAYOUT[i][0] == name ? LAYOUT[i][2] : layout_rot(name, i+1);

module at(name) {
    pos = layout_pos(name); rot = layout_rot(name);
    assert(pos != undef, str("Layout entry not found: ", name));
    translate(pos) rotate(rot) children();
}
