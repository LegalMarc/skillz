// ============================================================
// pick_lid.scad -- ONE lid over BOTH pick tray rows.
//
// Revision 3 brought tray B's floor down onto tray A's rim, but
// their RIMS are still 38mm apart, so a lid covering both as two
// flat steps would be a Z in section -- unprintable without
// support whichever way it is laid, because one arm is always
// cantilevered. So the body's whole pick surface is a single
// 38.7 degree plane and this is a flat plate lying on it, with
// a skirt down its front edge. The skirt is what holds it: PLA
// on PLA grips to about 17 degrees and this slope is 39, so the
// plate would otherwise slide straight off. The skirt also
// closes the scalloped front wall, which is cut 12mm below the
// plane so the front tray is open to the front once the lid is
// lifted.
//
// Local origin: the module's front-bottom-left outer corner,
// offset in X only. This part is modelled IN ASSEMBLED
// ORIENTATION -- tilted -- deliberately: modelling it flat and
// tilting it in layout.scad meant two rotations whose signs had
// to agree, and they did not; the lid swung down into the body
// instead of up the plane.
//
// Material: PLA or PETG.
// Print orientation: rotate -38.7 deg about X so the plate lies
//   flat on the bed, hook upward. The hook then rises at 51 deg
//   and self-supports. NOT as modelled.
//
// To remove: lift the front edge until the hook clears the
//   front face, then slide it forward. Nothing to unclip.
//
// EXPECTED_BBOX: [229.0, 63.85, 70.829]
// ============================================================

include <../params.scad>

// The underside of the plate: the pick plane, floated by pick_lid_gap.
function zu(y) = pickplane(y) + pick_lid_gap;

lid_back_y = yB_tray1 - pick_lid_clear;        // 60.85

assert(lid_back_y > yB_tray0,
       "the pick lid does not reach across tray B");
assert(zu(0) - pick_lid_hook_h < trayA_front_h - 3,
       "the front skirt does not reach down past the scalloped front wall");

module yz_extrude(x0, x1) {
    rotate([90, 0, 90]) translate([0, 0, x0])
        linear_extrude(height = x1 - x0) children();
}

hook_front = -pick_lid_hook_t;          // -3.0
hook_back  = -pick_lid_clear;           // -0.35, clear of the module's front face

PLATE = [
    [hook_front, zu(hook_front)],
    [lid_back_y, zu(lid_back_y)],
    [lid_back_y, zu(lid_back_y) + pick_lid_tv],
    [hook_front, zu(hook_front) + pick_lid_tv]
];

// The skirt hangs down past the module's front face, 0.35mm clear of it. Its
// top edge runs 1mm ABOVE the plate's underside and well below the plate's top
// face, so it lies strictly INSIDE the plate's section: an earlier version
// traced the plate's own faces exactly and the union came out non-watertight,
// which stopped every boolean check downstream from running at all.
HOOK = [
    [hook_front, zu(hook_front) + 1.0],
    [hook_back,  zu(hook_back)  + 1.0],
    [hook_back,  zu(0) - pick_lid_hook_h],
    [hook_front, zu(0) - pick_lid_hook_h]
];

module pick_plate() { yz_extrude(0, pick_lid_w) polygon(PLATE); }
module pick_hook()  { yz_extrude(0, pick_lid_w) polygon(HOOK); }

module pick_lid_geometry() { union() { pick_plate(); pick_hook(); } }

// SUBFEATURES: pick_plate, pick_hook
SUBFEATURE = is_undef(SUBFEATURE) ? "" : SUBFEATURE;
module subfeature_by_name(name) {
    if (name == "pick_plate") pick_plate();
    else if (name == "pick_hook") pick_hook();
    else assert(false, str("Unknown sub-feature '", name, "' in pick_lid.scad"));
}
if (SUBFEATURE != "") subfeature_by_name(SUBFEATURE);
else pick_lid_geometry();
