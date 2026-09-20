include <layout.scad>
use <parts/body.scad>
use <parts/pick_lid.scad>
use <parts/fill_lid.scad>

MODE = is_undef(MODE) ? "assembly" : MODE;
PART = is_undef(PART) ? "" : PART;

module part_by_name(name) {
    if (name == "body") body_geometry();
    else if (name == "pick_lid" || name == "pick_lid_b") pick_lid_geometry();
    else if (name == "fill_lid" || name == "fill_lid_b") fill_lid_geometry();
    else assert(false, str("Unknown part in layout: ", name));
}

if (MODE == "assembly") {
    for (i = [0 : len(LAYOUT) - 1]) at(LAYOUT[i][0]) part_by_name(LAYOUT[i][0]);
    echo("BOM: body x1 (printed), pick_lid x2 (printed), fill_lid x2 (printed)");
    echo(str("BOM: overall ", module_w + rail_out, " x ", yB_back, " x ", module_h,
             " mm; ", 2 * bays, " bays at ", bay_vol_ml, " mL each"));
} else if (MODE == "part") {
    at(PART) part_by_name(PART);
} else if (MODE == "open") {
    // Both pick lids swung to their measured hard stop against the stepped
    // hopper wall, and both fill lids lifted clear -- the state the unit is in
    // while you are actually picking pills out of it.
    at("body") body_geometry();
    for (n = ["pick_lid", "pick_lid_b"])
        at(n) rotate([-pick_lid_open_deg, 0, 0]) pick_lid_geometry();
    for (n = ["fill_lid", "fill_lid_b"])
        at(n) translate([0, 0, 40]) fill_lid_geometry();
} else if (MODE == "exploded") {
    at("body") body_geometry();
    for (n = ["pick_lid_a", "pick_lid_b"]) at(n) translate([0, -30, 30]) pick_lid_geometry();
    for (n = ["fill_lid_a", "fill_lid_b"]) at(n) translate([0, 0, 45]) fill_lid_geometry();
}
