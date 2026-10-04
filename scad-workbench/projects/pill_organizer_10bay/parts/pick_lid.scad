// ============================================================
// pick_lid.scad -- ONE lid over BOTH pick tray rows.
//
// Tray B's floor sits just above tray A's rim, but their RIMS
// are still tray_step (about 82mm) apart, so a lid covering
// both as two flat steps would be a Z in section -- unprintable
// without support whichever way it is laid, because one arm is
// always cantilevered. So the body's whole pick surface is a
// single plane at pick_lid_slope (43.8 degrees) and this is a flat plate
// lying on it, with a skirt down its front edge.
//
// What holds it on that slope is NOT the skirt. PLA on PLA grips to about
// 17 degrees, and this slope is two and a half times that, so something has to
// bear against a body face that faces BACK (toward +Y). The skirt hangs outside
// the front face, 0.35 mm clear of it; sliding down the slope moves the lid
// forward, which takes the skirt AWAY from that face. Revisions 6 to 9 said
// otherwise, and test print 2 slid the lid straight off. The retention is the
// pair of lugs under the plate's ends (D38): each drops into an end bay of tray
// A directly behind a stop block in the front corner. Both stop faces are
// perpendicular to the pick plane, so the lid stops after 0.5 mm of down-slope
// travel, while lifting it by the front edge (it pivots about its back edge, and
// the lug swings along the plane's normal, i.e. along the faces) or straight up
// does not jam. An earlier vertical stop face did jam at 0.5 to 2 degrees of
// tilt (review of revision 10). probes/lid_retention.py
// checks that, the straight lift-off, and that the lid cannot be fitted turned
// round.
//
// The skirt closes the scalloped front wall, which is cut well below the plane
// so the front tray is open to the front once the lid is lifted, and carries
// the embossed "FRONT". Two finger notches in its bottom edge (D22) are what
// you lift by: a fingertip hooks under each notch's ceiling. They are grips,
// not alignment features.
//
// Local origin: the module's front-bottom-left outer corner,
// offset in X only. This part is modelled IN ASSEMBLED
// ORIENTATION -- tilted -- deliberately: modelling it flat and
// tilting it in layout.scad meant two rotations whose signs had
// to agree, and they did not; the lid swung down into the body
// instead of up the plane.
//
// Material: PLA or PETG.
// Print orientation: rotate [180 - pick_lid_slope, 0, 0] (see
//   print_export.scad) so the plate's TOP face is on the bed and
//   the skirt rises at about 46 degrees. -pick_lid_slope alone
//   lays the plate flat with the skirt pointing DOWN (INCIDENTS).
//   NOT as modelled.
//
// To remove: lift it by the finger notches. It may tilt about its back edge
//   (1.2 mm from the wall behind tray B; swept clear to 15 degrees) or come
//   straight up or along the plane's normal; none of these touches the stop
//   blocks after the first few millimetres (probes/lid_retention.py, joints.json
//   motion). Nothing to unclip.
//
// EXPECTED_BBOX: [239.0, 87.6, 111.63]
// ============================================================

include <../params.scad>

// The underside of the plate: the pick plane, floated by pick_lid_gap.
function zu(y) = pickplane(y) + pick_lid_gap;

lid_back_y = yB_tray1 - pick_lid_back_clear;   // 84.0

assert(lid_back_y > yB_tray0,
       "the pick lid does not reach across tray B");
assert(pick_lid_skirt_over > 3,
       "the front skirt overlaps the scalloped front wall by under 3mm (its bottom is front_h - overlap by definition; probes/lid_retention.py (g) measures the built lid)");

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
                polygon([[x0,                pick_lid_skirt_bot - pick_notch_under],
                         [x0 + pick_notch_w, pick_lid_skirt_bot - pick_notch_under],
                         [x0 + pick_notch_w, pick_notch_top],
                         [x0,                pick_notch_top]]);
    }
}
// layout.scad offsets the lid by lid_dx in X; the notches must stay centred
// on the BODY's bays, so the same offset is taken off here. Kept in step by the
// assert in layout.scad.
lid_dx_local = (module_w - pick_lid_w) / 2;                 // 0.5

// Retention lugs (D32, D34, D38): one under each end of the plate, hanging into
// the end bay of tray A directly behind a stop block in the front corner (params.scad
// 9). Both stop faces are PERPENDICULAR TO THE PICK PLANE: the lug's front face
// here, the block's back face in body.scad. Going down the slope the lid moves
// along that face's normal and stops after pick_lug_clear; lifting by the front
// edge swings the lug along the plane's normal, which is along the faces, so
// nothing jams. Built in the plate's own frame (s along the slope, n normal to
// it, negative below the underside) and placed by the ONE rotation that lays
// that frame on the plane; it reaches 1.5 mm up into the plate so the union is
// volumetric. The tip's X edges are chamfered (pick_lug_chamfer) to lead it in.
function lug_s(y) = y / cos(pick_lid_slope);
module pick_lug(x_low) {
    c = pick_lug_chamfer; t = pick_lug_t; d = pick_lug_d;
    s0 = pick_lug_s0; L = pick_lug_len;
    translate([0, 0, zu(0)]) rotate([pick_lid_slope, 0, 0])
        hull() {
            translate([x_low, s0, -d + c]) cube([t, L, d - c + 1.5]);
            translate([x_low + c, s0, -d]) cube([t - 2 * c, L, 0.01]);
        }
}
module pick_lugs() {
    pick_lug(pick_lug_x_left  - lid_dx_local);
    pick_lug(pick_lug_x_right - lid_dx_local);
}

// "FRONT" (D38), embossed pick_front_h proud of the skirt's outer face (y = -3),
// centred on the lid, between the two finger notches. rotate([90, 0, 0]) stands
// the text up facing -Y with its baseline along +X, so it reads left to right
// from the front; the extrusion then runs toward -Y, away from the skirt. It
// overlaps 0.4 mm into the skirt so the union is volumetric.
module pick_front_mark() {
    cx = module_w / 2 - lid_dx_local;
    cz = (pick_lid_skirt_bot + zu(0)) / 2 - pick_front_size / 2 - 4;
    translate([cx, hook_front + 0.4, cz])
        rotate([90, 0, 0])
            linear_extrude(height = pick_front_h + 0.4)
                text(pick_front_text, size = pick_front_size, halign = "center",
                     font = "Liberation Sans:style=Bold");
}

module pick_lid_geometry() {
    difference() {
        union() { pick_plate(); pick_hook(); pick_lugs(); pick_front_mark(); }
        pick_notches();
        pick_end_chamfers();
    }
}

// SUBFEATURES: pick_plate, pick_hook, pick_lugs
SUBFEATURE = is_undef(SUBFEATURE) ? "" : SUBFEATURE;
module subfeature_by_name(name) {
    if (name == "pick_plate") pick_plate();
    else if (name == "pick_hook") pick_hook();
    else if (name == "pick_lugs") pick_lugs();
    else assert(false, str("Unknown sub-feature '", name, "' in pick_lid.scad"));
}
if (SUBFEATURE != "") subfeature_by_name(SUBFEATURE);
else pick_lid_geometry();
