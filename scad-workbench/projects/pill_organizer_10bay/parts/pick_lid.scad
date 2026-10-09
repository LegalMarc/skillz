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
// A directly behind a stop block in the front corner. They are tapered and filleted at the root (D62-D64). Both stop faces are
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
// no lettering (D61). It has no finger notches or anything hung from it (D44):
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
// EXPECTED_BBOX: [239.0, 87.35, 111.63]   (87.95 until D61 removed the 0.6 mm FRONT relief)
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
// chamfered ends: a seam at the bend and a two-piece look (test print 4). This is a single
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

// layout.scad offsets the lid by lid_dx in X; the lugs are
// placed on the BODY's coordinates, so the same offset is taken off here. Kept in
// step by the assert in layout.scad.
lid_dx_local = (module_w - pick_lid_w) / 2;                 // 0.5

// Retention lugs (D32, D34, D38, D62-D64): one under each end of the plate, hanging into
// the end bay of tray A directly behind a stop block in the front corner (params.scad
// 9). Both stop faces are PERPENDICULAR TO THE PICK PLANE: the lug's front face
// here, the block's back face in body.scad. Going down the slope the lid moves
// along that face's normal and stops after pick_lug_clear; lifting by the front
// edge swings the lug along the plane's normal, which is along the faces, so
// nothing jams. Built in the plate's own frame (s along the slope, n normal to
// it, negative below the underside) and placed by the ONE rotation that lays
// that frame on the plane; it reaches 1 mm up into the plate so the union is
// volumetric. The tip's X edges are chamfered (pick_lug_chamfer) to lead it in.
// Revision 18 (D62-D64) stiffens it without moving the front face, the outboard face or the tip: the
// back and inboard faces draft outward toward the plate, the back is 2 mm longer, and the same two
// sides carry a root fillet. The body is already printed; every added surface keeps 1 mm or more to it
// (probes/lug_clearance.py).
function lug_s(y) = y / cos(pick_lid_slope);

// D62-D64: the lug is one lofted solid, built in the plate's own frame as (x, s, n) with x measured
// INBOARD from the lug's outboard face (the face that keeps pick_lug_clear to the side wall), s along
// the slope from the lid frame's origin and n normal to the plate (negative below the underside).
// Seen from the tip (n = -d) to the root (n = 0) it widens on its INBOARD side and its BACK side only,
// by pick_lug_grow over the whole depth (the same slope on both, k = grow / d); the front face (the stop
// face, s = s0) and the outboard face (x = 0) are straight along n, exactly as in D38. Printed with the
// plate on the bed the lug narrows going up: no overhang. At the root a fillet of radius pick_lug_fillet_r
// runs round the same two sides (D63). Every cross-section is the same kind of ring, a rectangle whose
// back-inboard corner is rounded, so rings loft one to the next with no collapsed vertices and the solid
// is watertight by construction. A ring at level n: x from xlo to xw, s from s0 to sw, grown by u on the
// inboard and back sides, with the corner radius pick_lug_round + u centred on the lug's own corner.
LUG_ARC_N = 10;      // segments of the fillet's arc (rings along n)
LUG_CORNER_N = 6;    // segments of the rounded back-inboard corner in each ring
function lug_k()       = pick_lug_grow / pick_lug_d;
function lug_xw(n)     = pick_lug_t + lug_k() * (n + pick_lug_d);              // inboard face at level n
function lug_sw(n)     = pick_lug_s0 + pick_lug_len + lug_k() * (n + pick_lug_d);   // back face at level n
function lug_ring(n, xlo, xw, sw, u) =
    let(rho = pick_lug_round, cx = xw - rho, cs = sw - rho, R = rho + u)
    concat([[xlo, pick_lug_s0, n], [xw + u, pick_lug_s0, n]],
           [for (j = [0 : LUG_CORNER_N]) let(a = 90 * j / LUG_CORNER_N) [cx + R * cos(a), cs + R * sin(a), n]],
           [[xlo, sw + u, n]]);
// the fillet arc in the (x, n) section: a circle of radius r tangent to the plate plane (n = np) and to the
// drafted face, which meets the plate at the angle 90 + theta. np is the plate plane the fillet is drawn for.
lug_theta = atan(lug_k());
lug_np    = -pick_lug_plate_embed;
lug_T     = pick_lug_fillet_T;                                                  // tangent length from the corner (params.scad)
lug_xc    = lug_xw(lug_np);                                                    // the wall at the plate plane
lug_C     = [lug_xc + lug_T, lug_np - pick_lug_fillet_r];                      // fillet circle centre (x, n)
function lug_arc(j) = let(a = 90 + (90 - lug_theta) * j / LUG_ARC_N)
                      lug_C + pick_lug_fillet_r * [cos(a), sin(a)];            // j = 0: plate tangent point; j = N: tangent point on the wall
LUG_RINGS = concat(
    [lug_ring(-pick_lug_d, pick_lug_chamfer, pick_lug_t - pick_lug_chamfer, pick_lug_s0 + pick_lug_len, 0),
     lug_ring(-pick_lug_d + pick_lug_chamfer, 0, lug_xw(-pick_lug_d + pick_lug_chamfer), lug_sw(-pick_lug_d + pick_lug_chamfer), 0)],
    [for (j = [LUG_ARC_N : -1 : 0]) let(p = lug_arc(j), n = p[1], u = p[0] - lug_xw(n))
        lug_ring(n, 0, lug_xw(n), lug_sw(n), j == LUG_ARC_N ? 0 : u)],
    // 1 mm up into the plate (3 thick), the fillet's outer edge carried straight on
    [let(n = 1.0, u = lug_xc + lug_T - lug_xw(n)) lug_ring(n, 0, lug_xw(n), lug_sw(n), u)]);
assert(lug_xc + lug_T - lug_xw(1.0) > 0.05, "the lug's fillet is too small for its draft (D63)");
assert(lug_arc(LUG_ARC_N)[1] > -pick_lug_d + pick_lug_chamfer + 0.5, "the root fillet reaches the tip chamfer (D63)");
module lug_loft(rings) {
    m = len(rings[0]); k = len(rings);
    pts = [for (r = rings) each r];
    side = [for (i = [0 : k - 2]) for (v = [0 : m - 1])
               let(w = (v + 1) % m, a = i * m + v, b = i * m + w, c = (i + 1) * m + w, d = (i + 1) * m + v)
               each [[a, c, b], [a, d, c]]];
    bottom = [[for (v = [0 : m - 1]) v]];
    top = [[for (v = [m - 1 : -1 : 0]) (k - 1) * m + v]];
    polyhedron(points = pts, faces = concat(side, bottom, top), convexity = 6);
}
// x_out: lid-local X of the lug's outboard face; sgn = +1 when the inboard side is +X (left lug), -1 (right lug)
module pick_lug(x_out, sgn) {
    translate([x_out, 0, zu(0)]) rotate([pick_lid_slope, 0, 0]) mirror([sgn > 0 ? 0 : 1, 0, 0]) lug_loft(LUG_RINGS);
}
module pick_lugs() {
    pick_lug(pick_lug_x_left - lid_dx_local, 1);
    pick_lug(pick_lug_x_right + pick_lug_t - lid_dx_local, -1);
}

// No "FRONT" mark (D61): the D38 embossed lettering is removed. The lugs already make the lid go on one way
// only, and printed with the plate on the bed the raised letters on the downward-facing skirt made the slicer
// report floating regions and ask for supports.

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
        union() { pick_body(); pick_lugs(); }
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
