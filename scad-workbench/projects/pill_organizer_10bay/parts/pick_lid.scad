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
// Plate and skirt are ONE piece (D53): a single profile, extruded once, with a
// concave fillet inside the bend and a small round outside it, and one chamfer
// along each x-end that runs on round the bend.
//
// The skirt closes the scalloped front wall, which is cut well below the plane
// so the front tray is open to the front once the lid is lifted, and carries
// the embossed "FRONT". It has no finger notches or anything hung from it (D44):
// you pinch it between thumb and forefinger.
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
// To remove: pinch the skirt and plate edge between thumb and forefinger and lift.
//   It may tilt about its back edge (1.2 mm from the wall behind tray B; swept
//   clear to 15 degrees) or come straight up or along the plane's normal, then
//   forward; none of these touches the stop blocks after the first few
//   millimetres (probes/lid_retention.py, joints.json motion). Nothing to unclip.
//
// EXPECTED_BBOX: [239.0, 87.95, 111.63]
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

hook_front = -pick_lid_hook_t;          // -3.35: the skirt is lid_t thick, like the plate
hook_back  = -pick_lid_clear;           // -0.35, clear of the module's front face

// ---- The lid's ONE section (D53) -----------------------------------------------------
// Plate and skirt used to be two polygons (PLATE and HOOK) unioned, each with its own
// chamfered ends: a seam at the bend and a two-piece look (test print 3). This is a single
// closed (y, z) profile, extruded once across the lid's width. Walking it from the skirt's
// bottom-outer corner: up the skirt's outer face, round the bend (outside radius
// pick_bend_out_r), along the plate's top face to the back, down the back face, forward along
// the underside (the seating plane, floated pick_lid_gap), round the bend again on the inside
// (pick_bend_in_r, a fillet that adds material) and down the skirt's inner face to the bottom.
// The skirt is lid_t thick, the same as the plate, so the wall is one thickness all the way
// round; the inside fillet makes the bend itself a little thicker (calculations.md).
// Convex corners that are not the bend keep the 45 degree chamfers of D27, worked out the way
// offset(delta, chamfer = true) does it: the cut is L = 2 r (1 - sin(a/2)) / sin(a) long on each
// leg of a corner of interior angle a. Those are the skirt's two bottom corners and the plate's
// two back corners; the plate's top face goes on the bed, so the corners there stay chamfers
// and the one round is the bend, which is only a 46 degree turn (see pick_bend_out_r).
alpha   = pick_lid_slope;
pdir    = [cos(alpha), sin(alpha)];             // along the plate, up and back
function lid_zT(y) = zu(y) + pick_lid_tv;       // plate top face
function lid_cham(a) = 2 * lid_round * (1 - sin(a / 2)) / sin(a);
function arc_pts(c, r, a0, a1, n = 16) = [for (i = [0 : n]) c + r * [cos(a0 + (a1 - a0) * i / n), sin(a0 + (a1 - a0) * i / n)]];

skirt_zb   = zu(0) - pick_lid_hook_h;           // the skirt's bottom
bend_turn  = 90 - alpha;                        // 46.2: how far the surface turns at the bend
// outside (convex) round, top face to skirt outer face
bo_t   = pick_bend_out_r * tan(bend_turn / 2);  // tangent length
bo_C   = [hook_front, lid_zT(hook_front)];      // the sharp corner it replaces
bo_B1  = [hook_front, bo_C[1] - bo_t];          // on the outer face
bo_cen = bo_B1 + [pick_bend_out_r, 0];
bo_B2  = bo_C + bo_t * pdir;                    // on the top face
// inside (concave) fillet, underside to skirt inner face; the air wedge there is 90 + alpha wide
bi_t   = pick_bend_in_r / tan((90 + alpha) / 2);
bi_C   = [hook_back, zu(hook_back)];
bi_F1  = [hook_back, bi_C[1] - bi_t];           // on the skirt's inner face
bi_cen = bi_F1 + [pick_bend_in_r, 0];
bi_F2  = bi_C + bi_t * pdir;                    // on the underside
// plate back corners: top (interior angle 90 - alpha) and bottom (90 + alpha)
bk_Ct  = [lid_back_y, lid_zT(lid_back_y)];
bk_Cb  = [lid_back_y, zu(lid_back_y)];
bk_Lt  = lid_cham(90 - alpha);
bk_Lb  = lid_cham(90 + alpha);
sk_ch  = lid_cham(90);

assert(norm(bo_cen + pick_bend_out_r * [cos(180 - bend_turn), sin(180 - bend_turn)] - bo_B2) < 1e-6
       && norm(bi_cen + pick_bend_in_r * [cos(90 + alpha), sin(90 + alpha)] - bi_F2) < 1e-6,
       "the bend arcs do not land on their tangent points");

LID_PROFILE = concat(
    [[hook_front + sk_ch, skirt_zb], [hook_front, skirt_zb + sk_ch]],
    arc_pts(bo_cen, pick_bend_out_r, 180, 180 - bend_turn),
    [bk_Ct - bk_Lt * pdir, bk_Ct + bk_Lt * [0, -1],
     bk_Cb + bk_Lb * [0, 1], bk_Cb - bk_Lb * pdir],
    arc_pts(bi_cen, pick_bend_in_r, 90 + alpha, 180),
    [[hook_back, skirt_zb + sk_ch], [hook_back - sk_ch, skirt_zb]]
);

module pick_body() { yz_extrude(0, pick_lid_w) polygon(LID_PROFILE); }

// The x-end edge, continuous around the bend (D53). One chain of edges runs along the
// outside of the lid: the plate's top face, the bend's round, the skirt's outer face. Each x-end
// face meets that chain in one edge, and it gets one chamfer of lid_chamfer (= pick_skirt_chamfer,
// 1.0) all the way. The chain is the lid's own outline walked as a polyline (the bend's arc is
// the same 16 points the profile uses), and the cutter is one convex piece per segment: a
// quadrilateral section swept between the mitred sections at the segment's two ends. Neighbouring
// pieces share a section exactly and cross at the facet angle (2.9 degrees on the arc), so there
// is no tangent line where one analytic cutter (a prism, a cone) hands over to the next: the
// first version built it that way and the junctions came out as zero-area slivers (INCIDENTS.md).
// The section, in (n, x): n is the distance out of the surface, x in from the end face. The chamfer
// plane runs through (n = -c, x = 0) and (n = 0, x = c); the section is the triangle under that
// line, carried on past x = 0 so that no vertex or edge of the cutter lies in the end face's plane
// (a cutter vertex there left zero-area faces).
function chain_poly(c) = [[-c - 1, -1], [1, c + 1], [1, -1]];   // (n, x): a triangle, the chamfer plane its hypotenuse
// the chain, in the profile's walking order: the skirt (from below its bottom), the bend, the top
// face (to well past the back). The bend's chain points are the MIDDLES of the profile's arc facets,
// and the two points either side of it sit 2 mm into the straight faces: a chain vertex exactly on a
// profile vertex puts the cutters' crease through the facet-to-facet line and leaves zero-area faces
// there. The middles lie in the facet planes, so the chamfer is the same width to within 0.02 mm.
ARC = arc_pts(bo_cen, pick_bend_out_r, 180, 180 - bend_turn);
CHAIN = concat([[hook_front, skirt_zb - 2], [hook_front, bo_B1[1] - 2]],
               [for (i = [0 : len(ARC) - 2]) (ARC[i] + ARC[i + 1]) / 2],
               [bo_B2 + 2 * pdir, bo_B2 + 200 * pdir]);
function seg_n(i) = let(d = CHAIN[i + 1] - CHAIN[i], l = norm(d)) [-d[1] / l, d[0] / l];
// the offset vector at chain point i: the mitre of its two segments (length 1 / cos(half turn))
function miter(i) = i == 0 ? seg_n(0)
                  : i == len(CHAIN) - 1 ? seg_n(len(CHAIN) - 2)
                  : (seg_n(i - 1) + seg_n(i)) / (1 + seg_n(i - 1) * seg_n(i));
function slice_pts(i, c) = [for (q = chain_poly(c)) [q[1], CHAIN[i][0] + miter(i)[0] * q[0], CHAIN[i][1] + miter(i)[1] * q[0]]];
module chain_cut(c) {
    for (i = [0 : len(CHAIN) - 2])
        hull() polyhedron(points = concat(slice_pts(i, c), slice_pts(i + 1, c)),
                          faces = [[0, 2, 1], [3, 4, 5], [0, 1, 4, 3], [1, 2, 5, 4], [2, 0, 3, 5]]);
}
module pick_end_chamfers() {
    assert(abs(lid_chamfer - pick_skirt_chamfer) < 1e-9, "one chamfer runs round the bend: lid_chamfer and pick_skirt_chamfer are one size");
    for (end = [0, 1])
        translate([end * pick_lid_w, 0, 0]) mirror([end, 0, 0]) chain_cut(lid_chamfer);
}

// layout.scad offsets the lid by lid_dx in X; the lugs and the FRONT mark are
// placed on the BODY's coordinates, so the same offset is taken off here. Kept in
// step by the assert in layout.scad.
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
// centred on the lid. rotate([90, 0, 0]) stands
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

// Underside x-end edges (D48): the plate's end face meets its underside in a 90 degree
// convex edge along the whole slope. Same construction as the top chamfers, mirrored onto the
// underside; it starts 0.25 mm behind the point where the inside bend fillet (D53) meets the underside
// (in front of that the surface is the fillet, whose end edge stays square like the skirt's inner
// end edges); in revision 12 it started at y = 0.2 behind a sharp crotch.
// (Turned 44.5 degrees, not 45: at exactly 45 the prism's edge lies IN the underside plane, and
// where the plate's back chamfer crosses it that left zero-area slivers and a non-watertight mesh.)
module pick_under_chamfers() {
    c = pick_under_chamfer; a = c * sqrt(2);
    s0 = (bi_F2[0] + 0.25) / cos(pick_lid_slope);      // along the slope, from y = 0: 0.25 past where the inside fillet ends
    for (x = [0, pick_lid_w])
        translate([x, 0, zu(0)])
            rotate([pick_lid_slope, 0, 0]) translate([0, s0 + 200, 0]) rotate([0, 44.5, 0])
                cube([a, 400, a], center = true);
}

module pick_lid_geometry() {
    difference() {
        union() { pick_body(); pick_lugs(); pick_front_mark(); }
        pick_end_chamfers();
        pick_under_chamfers();
    }
}

// SUBFEATURES: pick_body, pick_lugs
SUBFEATURE = is_undef(SUBFEATURE) ? "" : SUBFEATURE;
module subfeature_by_name(name) {
    if (name == "pick_body") pick_body();
    else if (name == "pick_lugs") pick_lugs();
    else assert(false, str("Unknown sub-feature '", name, "' in pick_lid.scad"));
}
if (SUBFEATURE != "") subfeature_by_name(SUBFEATURE);
else pick_lid_geometry();
