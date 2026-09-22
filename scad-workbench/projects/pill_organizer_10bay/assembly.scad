include <layout.scad>
use <parts/body.scad>
use <parts/pick_lid.scad>
use <parts/fill_lid.scad>

MODE = is_undef(MODE) ? "assembly" : MODE;
PART = is_undef(PART) ? "" : PART;

module part_by_name(name) {
    if (name == "body") body_geometry();
    else if (name == "pick_lid") pick_lid_geometry();
    else if (name == "fill_lid") fill_lid_geometry();
    else assert(false, str("Unknown part in layout: ", name));
}

if (MODE == "assembly") {
    for (i = [0 : len(LAYOUT) - 1]) at(LAYOUT[i][0]) part_by_name(LAYOUT[i][0]);
    echo("BOM: body x1, pick_lid x1, fill_lid x1 -- all printed, no hardware");
    echo(str("BOM: overall ", module_w + rail_out, " x ", module_d, " x ", module_h,
             " mm; ", 2 * bays, " bays"));
} else if (MODE == "part") {
    at(PART) part_by_name(PART);
} else if (MODE == "open") {
    // Both lids lifted clear -- the state the unit is in while you fill it.
    at("body") body_geometry();
    at("pick_lid") translate([0, -95, 55]) pick_lid_geometry();
    at("fill_lid") translate([0, 0, 70]) fill_lid_geometry();
} else if (MODE == "exploded") {
    at("body") body_geometry();
    at("pick_lid") translate([0, -70, 45]) pick_lid_geometry();
    at("fill_lid") translate([0, 0, 90]) fill_lid_geometry();
}
