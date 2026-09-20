// Origin: front-bottom-left outer corner of the body.
// +X right, +Y back, +Z up. Millimetres.
//
// Three parts, three placements. The two tiers are no longer one section
// repeated -- grouping both mouths at the back and both trays at the front
// gives the two rows genuinely different sections, so each is written once.
include <params.scad>

lid_dx = 0.5;

LAYOUT = [
    ["body",     [0, 0, 0], [0, 0, 0]],
    // Modelled already tilted onto the 31.9 degree pick plane, so it only
    // needs offsetting in X. Its own pick_lid_gap keeps the pair a near miss
    // rather than a coplanar resting contact, which FCL cannot measure a
    // penetration depth for.
    ["pick_lid", [lid_dx, 0, 0], [0, 0, 0]],
    // Dropped into the shared mouth over BOTH hoppers.
    ["fill_lid", [wall_out + fill_lid_clear,
                  hop_mouth_y0 + fill_lid_clear,
                  fill_seat_z + fill_lid_seat_gap], [0, 0, 0]]
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
