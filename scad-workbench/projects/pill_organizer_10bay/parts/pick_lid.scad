// ============================================================
// pick_lid.scad -- ONE lid over BOTH pick tray rows.
//
// Tray B's floor sits just above tray A's rim, but their RIMS
// are still tray_step (about 51mm) apart, so a lid covering
// both as two flat steps would be a Z in section -- unprintable
// without support whichever way it is laid, because one arm is
// always cantilevered. So the body's whole pick surface is a
// single plane at pick_lid_slope (about 40 degrees) and this is
// a flat plate lying on it, with a skirt down its front edge.
// The skirt is what holds it: PLA on PLA grips to about 17
// degrees and this slope is twice that, so the plate would
// otherwise slide straight off. The skirt also closes the
// scalloped front wall, which is cut 13mm below the plane so
// the front tray is open to the front once the lid is lifted.
//
// Two finger notches in the skirt's bottom edge (D22) are what
// you lift by: a fingertip hooks under each notch's ceiling.
//
// Local origin: the module's front-bottom-left outer corner,
// offset in X only. This part is modelled IN ASSEMBLED
// ORIENTATION -- tilted -- deliberately: modelling it flat and
// tilting it in layout.scad meant two rotations whose signs had
// to agree, and they did not; the lid swung down into the body
// instead of up the plane.
//
// Material: PLA or PETG.
// Print orientation: rotate -pick_lid_slope about X so the
//   plate lies flat on the bed, skirt upward. The skirt then
//   rises at about 50 degrees and self-supports. NOT as modelled.
//
// To remove: lift STRAIGHT UP by the two notches. Do not tilt
//   it about its back edge -- that edge is 0.35mm from the wall
//   behind tray B and the top-back corner meets the wall after
//   about 5 degrees. Nothing to unclip.
//
// EXPECTED_BBOX: [229.0, 63.85, 73.03]
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

// A profile in (x, z), extruded back along Y.
module xz_extrude(y0, y1) {
    translate([0, y1, 0]) rotate([90, 0, 0])
        linear_extrude(height = y1 - y0) children();
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
// top edge runs 2mm ABOVE the plate's underside and well below the plate's top
// face, so it lies strictly INSIDE the plate's section: an earlier version
// traced the plate's own faces exactly and the union came out non-watertight,
// which stopped every boolean check downstream from running at all. 2 rather
// than 1 so it also covers the plate's rounded bottom-front corner (D27).
HOOK = [
    [hook_front, zu(hook_front) + 2.0],
    [hook_back,  zu(hook_back)  + 2.0],
    [hook_back,  zu(0) - pick_lid_hook_h],
    [hook_front, zu(0) - pick_lid_hook_h]
];

// Both sections get their convex corners CHAMFERED at 45 degrees (D27): the
// plate's front and back edges, and the skirt's bottom edge. Chamfers, not
// rounds, because the plate's top face goes on the bed when it is printed and
// a rounded bottom edge is an overhang that steepens to 90 at the tangent; a
// 45 chamfer is the one profile that prints clean there. The plate's
// bottom-back corner is chamfered too, which lifts the last 1mm of its
// underside off the plane -- harmless. lid_round is under half the plate's
// thickness -- see params.scad for why. The x-end top edges are done in 3D
// below.
module pick_plate() { yz_extrude(0, pick_lid_w) offset(delta = lid_round, chamfer = true) offset(delta = -lid_round) polygon(PLATE); }
module pick_hook()  { yz_extrude(0, pick_lid_w) offset(delta = lid_round, chamfer = true) offset(delta = -lid_round) polygon(HOOK); }

// Chamfer along each x-end top edge of the plate: a square prism rotated 45
// degrees about the edge's own direction, centred on the edge. The edge runs
// along (0, cos s, sin s) through (x, 0, zu(0) + pick_lid_tv); rotate([s,0,0])
// is the ONE rotation that maps +Y onto that direction. It touches nothing
// but the top corner: the skirt is 3mm and more below the top face.
module pick_end_chamfers() {
    a = lid_chamfer * sqrt(2);
    for (x = [0, pick_lid_w])
        translate([x, 0, zu(0) + pick_lid_tv])
            rotate([pick_lid_slope, 0, 0]) rotate([0, 45, 0])
                cube([a, 400, a], center = true);
}

// Finger notches (D22): rounded-top slots up into the skirt's bottom edge,
// cut clear through it in Y, starting below the skirt so no cut face lands on
// the skirt's own bottom face. X positions come from the body's bay centres,
// less the lid's own X offset in the layout.
module pick_notches() {
    r = pick_notch_r;
    for (cx = pick_notch_x) {
        x0 = cx - lid_dx_local - pick_notch_w / 2;
        xz_extrude(hook_front - 1, hook_back + 1)
            offset(r = r) offset(delta = -r)
                polygon([[x0,                pick_lid_skirt_bot - 2],
                         [x0 + pick_notch_w, pick_lid_skirt_bot - 2],
                         [x0 + pick_notch_w, pick_notch_top],
                         [x0,                pick_notch_top]]);
    }
}
// layout.scad offsets the lid by lid_dx in X; the notches must stay centred
// on the BODY's bays, so the same offset is taken off here. Kept in step by the
// assert in layout.scad.
lid_dx_local = (module_w - pick_lid_w) / 2;                 // 0.5

module pick_lid_geometry() {
    difference() {
        union() { pick_plate(); pick_hook(); }
        pick_notches();
        pick_end_chamfers();
    }
}

// SUBFEATURES: pick_plate, pick_hook
SUBFEATURE = is_undef(SUBFEATURE) ? "" : SUBFEATURE;
module subfeature_by_name(name) {
    if (name == "pick_plate") pick_plate();
    else if (name == "pick_hook") pick_hook();
    else assert(false, str("Unknown sub-feature '", name, "' in pick_lid.scad"));
}
if (SUBFEATURE != "") subfeature_by_name(SUBFEATURE);
else pick_lid_geometry();
