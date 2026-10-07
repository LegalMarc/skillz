// ============================================================
// body.scad -- the organizer body, revision 12. Two pick trays
// at the FRONT under one lid, two fill mouths at the BACK under
// one lid.
//
//   [ tray A ][ tray B ][ hopper B mouth ][ hopper A mouth ]
//     front                                           back
//
// Hopper B is the front mouth and feeds tray B right in front
// of it -- a plain ramp. Hopper A is the BACK mouth and feeds
// the FRONT tray, so its chute ducks under tray B and under
// hopper B. Since revision 10 (D36) the chute is one straight 40 degree
// floor from tray A's foot to hopper A, and tray A's own floor tilts down
// toward the front wall. See params.scad section 4.
//
// Local origin: front-bottom-left outer corner. +X right,
// +Y back, +Z up. This is the assembly datum.
//
// Material: PLA or PETG.
// Print orientation: as modelled, flat on its base, no supports. The base perimeter
// carries a bed_chamfer bevel against elephant foot (D48).
//
// EXPECTED_BBOX: [243.0, 213.01, 189.0]
// ============================================================

include <../params.scad>
include <../rail_profile.scad>

module yz_extrude(x0, x1) {
    rotate([90, 0, 90]) translate([0, 0, x0])
        linear_extrude(height = x1 - x0) children();
}

// A profile in (x, z), extruded back along Y.
module xz_extrude(y0, y1) {
    translate([0, y1, 0]) rotate([90, 0, 0])
        linear_extrude(height = y1 - y0) children();
}

function wall_x0(k) = k == 0 ? 0
                    : k == bays ? module_w - wall_out
                    : wall_out + k * bay_w + (k - 1) * wall_div;
function wall_x1(k) = k == 0 ? wall_out
                    : k == bays ? module_w
                    : wall_x0(k) + wall_div;

// ------------------------------------------------------------
// Outer silhouette: the maximum-material outline, in (y, z).
// One step down at tray B's back wall, then ONE straight slope
// forward to the front face -- every wall over both trays dies
// on that plane, so a single flat plate lids both rows.
// ------------------------------------------------------------
OUTER = [
    [0,         0],
    [module_d,  0],
    [module_d,  flare_zo],                // the back wall leans out above here (D42)
    [module_d_top, hopper_rim],
    [yB_tray1,  hopper_rim],
    [yB_tray1,  trayB_rim],
    [0,         pickplane_front]
];
// The outer solid (D27, rebuilt in D48). The silhouette is extruded across the module's
// width, eroded by edge_r_top and dilated by one tool of that size (Minkowski): an opening of
// the whole solid. Every convex edge of the outside is then a true round of that radius, the
// silhouette's top edges in section (as before), the four vertical corners (the back ones
// follow the leaning back wall exactly) AND the perimeter of both side faces, which revisions
// 7 to 11 left square. The step's inside corner is concave and is untouched.
//
// The tool is a ball whose lower half is a 45 degree cone: the upper hemisphere hulled with a
// disc bed_chamfer under its equator, edge_r_top - bed_chamfer in radius. Wherever it sweeps
// the bottom of the solid the result is a flat bed face with a bed_chamfer x bed_chamfer 45
// degree bevel running round it, and round the vertical corners too, because the cone is
// the ball's own lower half. Everything comes from the one dilation: no cutter has to
// agree with the rounded surface (an earlier version cut the bevel with a cone of the footprint
// and its facets met the ball's, which left zero-volume shards that came and went with the
// number of segments).
// ball(): OpenSCAD's sphere($fn = n) has its rings half a step off the poles and the
// equator, so it is cos(180 / n) = 0.9914 of r tall and wide; scaled up by the inverse
// its flats come out exactly r.
OUTER_BOT = bed_chamfer - edge_r_top;      // the silhouette's bottom edge, so the result's bed face is z = 0
assert(bed_chamfer > 0 && bed_chamfer < edge_r_top - 0.3, "bed_chamfer must be positive and clearly smaller than the outer round");
OUTER_EXT = [
    [0,         OUTER_BOT],
    [module_d,  OUTER_BOT],
    [module_d,  flare_zo],                // the back wall leans out above here (D42)
    [module_d_top, hopper_rim],
    [yB_tray1,  hopper_rim],
    [yB_tray1,  trayB_rim],
    [0,         pickplane_front]
];
module ball(r, n = 24) { sphere(r = r / cos(180 / n), $fn = n); }
module outer_tool() {
    r = edge_r_top; c = bed_chamfer;
    hull() {
        intersection() { ball(r); translate([-r - 1, -r - 1, 0]) cube([2 * r + 2, 2 * r + 2, r + 1]); }
        translate([0, 0, -c]) cylinder(r = r - c, h = 0.01, $fn = 24);
    }
}
module outer_solid() {
    r = edge_r_top;
    minkowski() {
        translate([r, 0, 0]) yz_extrude(0, module_w - 2 * r)
            offset(delta = -r) polygon(OUTER_EXT);
        outer_tool();
    }
}

// ------------------------------------------------------------
// VOID_B -- tray B, its outlet, and hopper B. The simple row:
// the mouth sits directly behind the tray it feeds.
// ------------------------------------------------------------
VOID_B = [
    [yB_tray0,                   trayB_floor],
    [yB_tray1,                   trayB_floor],
    // Hopper B's ramp rides a deck above the vault RIDGE, so it starts vault_up
    // above the tray floor: a riser at the tray's back wall that the opening
    // pass rounds at the top (D26).
    [yB_tray1,                   rampB_foot],
    [yB_hop1,                    rampB(yB_hop1)],
    // Hopper B's back wall leans forward at the top (params.scad 4b), which is
    // what evens the two fill mouths up to about 3:2. It pivots here, at its
    // own floor, so the ramp below it is untouched.
    [hopwall_B(fill_seat_z - fill_ledge_w), fill_seat_z - fill_ledge_w],
    [hopwall_B(fill_seat_z) - fill_ledge_w, fill_seat_z],
    [hopwall_B(fill_seat_z) - fill_ledge_w, hopper_rim + 1],
    [yB_wall1 + fill_ledge_w,    hopper_rim + 1],
    [yB_wall1 + fill_ledge_w,    fill_seat_z],
    [yB_wall1,                   fill_seat_z - fill_ledge_w],
    [yB_wall1,                   outletB_top],
    [yB_tray1,                   outletB_top],
    [yB_tray1,                   trayB_rim + void_top_over],
    [yB_tray0,                   pickplane(yB_tray0) + void_top_over]
];

// The mouth both hoppers share, full width at the rim so the lid can pass
// down. Without it the seat lips run to the rim and the lid cannot drop in.
MOUTH = [
    [hop_mouth_y0, fill_seat_z - seat_lip_drop],
    [hop_mouth_y1, fill_seat_z - seat_lip_drop],
    [hop_mouth_y1, hopper_rim + 1],
    [hop_mouth_y0, hopper_rim + 1]
];

// ------------------------------------------------------------
// VOID_A -- tray A, the crossing chute, and hopper A. One
// continuous void: the chute IS hopper A's lower half, so the
// volume the crossing costs in height it gives back in capacity.
// The floor breaks once, at the chute foot, from the tilted tray A
// floor (trayA_tilt_deg, D36) onto the 40 degree chute.
// Along the climb behind tray B the ceiling runs parallel to the floor
// (vaulted, D26); under tray B it is flat (D29).
// ------------------------------------------------------------
VOID_A = [
    [yA_tray0,                   base_z],                      // tray A's floor at the front wall
    [yA_tray1,                   z_foot],                      // chute foot: the floor has risen trayA_tilt_deg (D36)
    [yB_tray1,                   z_porch],                     // end of the porch (porch_deg = ramp_deg since D36)
    [yA_hop1,                    chuteA_floor(yA_hop1)],       // one 40 deg climb to the back
    // the back wall's inner face leans out from the floor's end (D42), parallel to the outer
    [yA_hop1 + flare_dy(fill_seat_z - fill_ledge_w),                  fill_seat_z - fill_ledge_w],
    [yA_hop1 + flare_dy(fill_seat_z - fill_ledge_w) - fill_ledge_w,   fill_seat_z],
    [yA_hop1 + flare_dy(fill_seat_z - fill_ledge_w) - fill_ledge_w,   hopper_rim + 1],
    [hopwall_A(fill_seat_z) + fill_ledge_w, hopper_rim + 1],
    [hopwall_A(fill_seat_z) + fill_ledge_w, fill_seat_z],
    [hopwall_A(fill_seat_z - fill_ledge_w), fill_seat_z - fill_ledge_w],
    // the same leaning wall from hopper A's side, straight down to where it
    // springs off the chute ceiling. Hopper A ends up with a mouth wider than
    // its own throat, which is the right way round for a hopper.
    [yA_hop0,                    hopwall_z0],                 // vertical up to where the lean springs
    [yA_hop0,                    chuteA_ceil(yA_hop0)],
    // The vault (D26): between vault_y1 and vault_y0 the void's ceiling is
    // raised to the ridge and a little more; vault_roof() then puts the gabled
    // solid back under it. The ridge void starts strictly INSIDE the roof's
    // span at both ends, so no face of the two coincides.
    [vault_y1,                   chuteA_ceil(vault_y1)],
    [vault_y1,                   chuteA_ceil(vault_y1) + vault_up + 1],
    [vault_y0 + vault_ramp,      chuteA_ceil(vault_y0 + vault_ramp) + vault_up + 1],   // ramped, not stepped (D35)
    [vault_y0,                   chuteA_ceil(vault_y0)],
    [yB_tray1,                   porch_ceil_z],                // where the 40 deg leg meets the porch
    // The porch ceiling is FLAT (D29): a bridge across the bay, not a 25 degree
    // overhang held up by a rib. The wall between the trays hangs down in front
    // of it to outletA_top and forms the mouth into tray A, as before.
    [yA_wall1,                   porch_ceil_z],
    [yA_wall1,                   outletA_top],
    [yA_tray1,                   outletA_top],                 // the mouth's top edge
    [yA_tray1,                   pickplane(yA_tray1) + void_top_over],
    [yA_tray0,                   pickplane(yA_tray0) + void_top_over]
];

// Opening rounds the cavity's convex corners, which fillets every internal
// corner of the solid -- tray floors and the chute foot, where a pill would
// otherwise wedge. Applied to the flow voids only, never to OUTER, so the
// part's bounding box stays exact. Both tray voids run void_top_over PAST the
// pick plane (as MOUTH runs past the rim): a void top lying exactly on the
// shell's top face is a coplanar boolean, and it left a zero-area face pair
// on the plane once the rail-1 groove was cut out through it.
module void_a_2d() { offset(r = fillet_r) offset(r = -fillet_r) polygon(VOID_A); }
module void_b_2d() { offset(r = fillet_r) offset(r = -fillet_r) polygon(VOID_B); }
module mouth_2d()  { polygon(MOUTH); }

// The accessory cubby (params.scad 4d): one void the full inner width, opening
// through the BACK face only, so both side walls stay solid. Its ceiling is a
// 45 degree plane -- the conservative FDM overhang limit -- anchored cubby_ceil
// under the chute floor at the back face and thickening forward (D21). Cut
// here rather than in body_geometry so the rail buttresses, which are unioned
// afterwards, are not eaten by it.
// Nothing flows through the cubby, but it is cleaned and its corners collect dust, so since
// D48 its inside corners are filleted like every flow void's, in three dimensions: the void
// is the profile eroded by cubby_fillet_r, extruded across the shortened width and dilated by
// a ball, which rounds every convex edge of the VOID (the floor / front wall, floor / side
// wall, ceiling / side wall and ceiling / front wall corners). The lip's top is a concave edge
// of the void and stays sharp under an opening; it carries cubby_chamfer below. The void ends
// cubby_end_over past the back face, further than the ball is wide, so the rounding of its end
// edges happens in the air behind the module (the back wall leans out above flare_zo, but
// slower than the 45 degree ceiling climbs, so nothing of it is reached).
cubby_end_over = 1 + cubby_fillet_r + 1;
CUBBY_OPEN = [
    [cubby_y0,     base_t],
    [cubby_back,   base_t],
    [cubby_back,   base_t + cubby_lip_h],
    [module_d + cubby_end_over, base_t + cubby_lip_h],
    [module_d + cubby_end_over, cubby_ceil_z(module_d + cubby_end_over)],
    [cubby_y0,     cubby_ceil_z(cubby_y0)]
];
module cubby_void() {
    r = cubby_fillet_r;
    minkowski() {
        translate([wall_out + r, 0, 0]) yz_extrude(0, inner_w - 2 * r)
            offset(delta = -r) polygon(CUBBY_OPEN);
        ball(r);
    }
}

// The cubby's mouth in the back face (D48): the sides and the lip's top are 90 degree
// convex edges of the module's back wall, where a hand goes in for the accessories.
// A cone of the mouth's own outline, growing 45 degrees outward from the face, takes a
// cubby_chamfer bevel off all three. Its top is the cubby's own 45 degree ceiling plane
// (a hair, 0.05, under it, so no face lies on the ceiling), so it does not cut above the
// mouth; the leaning wall begins exactly there. The near plate is 0.3 inside the void.
module cubby_chamfer_cut() {
    c = cubby_chamfer; yi = module_d - c - 0.3; yo = module_d + 1;
    x0 = wall_out; x1 = module_w - wall_out; zl = base_t + cubby_lip_h;
    function ztop(y) = cubby_ceil_z(y) - 0.05;
    hull() {
        translate([x0 + 0.3, yi, zl + 0.3]) cube([x1 - x0 - 0.6, 0.01, ztop(yi) - zl - 0.3]);
        translate([x0 - (c + 1), yo, zl - (c + 1)]) cube([x1 - x0 + 2 * (c + 1), 0.01, ztop(yo) - zl + (c + 1)]);
    }
}

module body_shell() {
    difference() {
        outer_solid();
        for (i = [0 : bays - 1]) {
            x0 = wall_x1(i);
            yz_extrude(x0, x0 + bay_w) void_a_2d();
            yz_extrude(x0, x0 + bay_w) void_b_2d();
            yz_extrude(x0, x0 + bay_w) mouth_2d();
        }
        cubby_void();
    }
}

// ------------------------------------------------------------
// Outlet facets (D29, reshaped by D52). The top of each outlet opening -- the bottom
// edge of the wall between the trays, into tray A, and of hopper B's front
// wall, into tray B -- spans the whole bay with nothing under it. Test print 1
// printed both ragged and test print 4 drooped and strung along the 29 mm flat
// the D29 chamfers left. A 45 degree triangle in each top corner, one per divider
// face, fills the corner so the opening is a half octagon: vertical dividers, two
// 45 degree facets climbing toward the centre, and a crown flat (D54: 10 mm on tray A's
// mouth, 20 mm on outlet B). Each facet is outletX_chamfer (17.48, 12.48) long in both run and rise. Each prism
// reaches 1mm into its divider and up into the wall, and stops 0.05mm inside
// both faces of the wall in Y (D35): running it past them left a fin in the
// air on each side, and flush would put a face on a face of the shell.
// ------------------------------------------------------------
module outlet_corner(x_wall, dir, z_edge, z_top, y0, y1, c) {
    T = z_top + 1;
    // in (x, z): a right triangle against the divider face at x_wall, its
    // hypotenuse at 45 degrees through (x_wall + dir*c, z_edge)
    xz_extrude(y0, y1)
        polygon([[x_wall - dir * 1,                    T],
                 [x_wall + dir * (c + (T - z_edge)),   T],
                 [x_wall - dir * 1,                    z_edge - c - 1]]);
}
module outlet_chamfers() {
    for (i = [0 : bays - 1]) {
        x0 = wall_x1(i); x1 = x0 + bay_w;
        for (side = [[x0, 1], [x1, -1]]) {
            outlet_corner(side[0], side[1], outletA_top, outletA_top,
                          yA_tray1 + 0.05, yA_wall1 - 0.05, outletA_chamfer);
            outlet_corner(side[0], side[1], outletB_top, outletB_top,
                          yB_tray1 + 0.05, yB_wall1 - 0.05, outletB_chamfer);
        }
    }
}

// ------------------------------------------------------------
// The vault (params.scad 4e, D26). Each bay's chute ceiling on the 40 degree
// leg becomes a shallow gable: a ridge vault_up above the plain ceiling at the
// bay centre, vault_down below it at the dividers. The void polygon is cut to
// the ridge; this puts the two sloping halves of the roof back. Each half is
// one polygon in (x, z) extruded along Y and sheared to follow the 40 degree
// leg, reaching vault_embed into its divider, 1mm past the bay centre into its
// partner, and vault_top_over up into the deck -- every union volumetric.
// ------------------------------------------------------------
module vault_roof_half(x0, cx) {
    s = vault_slope;
    multmatrix([[1, 0, 0, 0],
                [0, 1, 0, 0],
                [0, ramp_tan, 1, chuteA_ceil(vault_roof_y0) - vault_roof_y0 * ramp_tan],
                [0, 0, 0, 1]])
        xz_extrude(vault_roof_y0, vault_roof_y1)
            polygon([[x0 - vault_embed, -vault_down - vault_embed * s],
                     [cx + 1.0,         vault_up + s],
                     [cx + 1.0,         vault_up + vault_top_over],
                     [x0 - vault_embed, vault_up + vault_top_over]]);
}

module vault_roof() {
    for (i = [0 : bays - 1]) {
        x0 = wall_x1(i); cx = bay_center_x(i);
        vault_roof_half(x0, cx);
        translate([2 * cx, 0, 0]) mirror([1, 0, 0]) vault_roof_half(x0, cx);
    }
}

// ------------------------------------------------------------
// Fill-lid seat. One lid spans BOTH mouths, so everything
// standing above the seat plane between them comes down to it.
// ------------------------------------------------------------
module fill_seat_cut() {
    for (k = [1 : bays - 1])
        translate([wall_x0(k) - seat_cut_over,
                   hop_mouth_y0 - seat_cut_over, fill_seat_z])
            cube([wall_div + 2 * seat_cut_over,
                  hop_mouth_d + 2 * seat_cut_over, lid_t + 2]);

    translate([wall_out - seat_cut_over, yB_hop1 - seat_cut_over, fill_seat_z])
        cube([inner_w + 2 * seat_cut_over,
              wall_div + 2 * seat_cut_over, lid_t + 2]);

    // No barb pockets or ledge reliefs: the lid is held by gravity in its
    // recess (D30); the snap tabs broke on test print 1.

    // Pull-lip notch (D23): the wall in front of the lid comes down to the seat
    // plane across fill_grip_d, so the lid's lip can carry on forward over it.
    translate([module_w / 2 - fill_grip_d / 2, hop_mouth_y0 - wall_div - 1, fill_seat_z])
        cube([fill_grip_d, wall_div + 3, lid_t + 2]);
}

// The fill mouth's rim (D48). Both hoppers share one rectangular opening; its four
// inside edges at the rim are 90 degree convex edges that the pouring hand, the pills and the lid
// all pass. A cone of the opening's outline, growing 45 degrees from mouth_chamfer under
// the rim, bevels all four at once, and doubles as a lead-in for the lid. The near plate is 0.3
// inside the opening, so no cutter face lies on a wall of the mouth.
module mouth_chamfer_cut() {
    c = mouth_chamfer; z0 = hopper_rim - c - 0.3; z1 = hopper_rim + 1;
    s = 0.02;   // the front and back flanks sit 0.02 further out than the side flanks, so the cone's corner edges never run through the mouth's own vertical corner edges
    x0 = wall_out; x1 = module_w - wall_out;
    hull() {
        translate([x0 + 0.3, hop_mouth_y0 + 0.3 - s, z0]) cube([x1 - x0 - 0.6, hop_mouth_y1 - hop_mouth_y0 - 0.6 + 2 * s, 0.01]);
        translate([x0 - (c + 1), hop_mouth_y0 - (c + 1) - s, z1])
            cube([x1 - x0 + 2 * (c + 1), hop_mouth_y1 - hop_mouth_y0 + 2 * (c + 1) + 2 * s, 0.01]);
    }
}

// ------------------------------------------------------------
// Scalloped front wall (params.scad 4c). The lid plane cannot come down any
// further -- its back end is pinned to tray B's rim -- but the front WALL can.
// Each bay's share of the front face drops to trayA_front_h, while the four
// dividers and the two side walls still run up to the plane and carry the lid.
// The lid's skirt hangs down the outside and closes the scallops.
// ------------------------------------------------------------
module scallop_outline(x0, x1, r) {
    offset(r = r)
        polygon([[x0 + r, trayA_front_h + r],
                 [x1 - r, trayA_front_h + r],
                 [x1 - r, trayA_front_h + 40],
                 [x0 + r, trayA_front_h + 40]]);
}
function scallop_x0(i) = i == 0 ? wall_x1(i) + pillar_w : wall_x1(i) - scallop_over;
function scallop_x1(i) = i == bays - 1 ? wall_x1(i) + bay_w - pillar_w : wall_x1(i) + bay_w + scallop_over;
module front_scallop_cut() {
    r = trayA_scallop_r;
    for (i = [0 : bays - 1]) {
        // The two end bays stop pillar_w short of their side wall (D38): the
        // front wall stays at the full pick-plane height there and the pick
        // lid's lug drops in behind it. No scallop_over on that side, since the
        // cut then ends in the middle of the front wall, on no face of its own.
        xz_extrude(-1, wall_out + 1) scallop_outline(scallop_x0(i), scallop_x1(i), r);
    }
}

// The scallop's floor edge, front face and tray side (D48): a 45 degree chamfer along the
// top edge of the front wall wherever the scallop has cut it down, where a finger rests and
// a pill is pulled over. Each cutter is a frustum of the scallop's own outline SHIFTED DOWN,
// not grown: it is scallop_chamfer deep at the wall's face and nothing at that depth into the
// wall, so the bevel is widest on the flat floor, narrows up the rounded corners as they steepen
// and fades out where they meet the vertical sides; it never reaches the dividers' tips (which
// scallop_over has already thinned) and stops 0.1 short of the bay's own sides. The tray-side
// frustum starts 0.2 into the tray and shifts a little further, so it stays above the divider
// fillets' tops (front_fillets stops 1 under the scallop floor).
module scallop_chamfer_cuts() {
    c = scallop_chamfer; r = trayA_scallop_r; e = 0.2;
    for (i = [0 : bays - 1]) {
        a = scallop_x0(i) + scallop_over + 0.1; b = scallop_x1(i) - scallop_over - 0.1;   // inside the bay's own width, clear of the divider tips
        // Each frustum is the hull of two thin plates of the outline, one far out in the air and one
        // far inside the scallop cut itself, so the shift runs straight through the wall's face at 45
        // degrees: shift(y) = c - y on the front face, c - (wall_out - y) on the tray side. (Plates
        // of any thickness bend the hull's slope: its lower surface runs to the plate's far edge.)
        // front face: shift c + 1.6 at y = -1.6, -0.6 (up) at y = c + 0.6
        hull() {
            translate([0, -1.6, 0]) xz_extrude(0, 0.01) translate([0, -(c + 1.6)]) scallop_outline(a, b, r);
            translate([0, c + 0.6, 0]) xz_extrude(0, 0.01) translate([0, 0.6]) scallop_outline(a, b, r);
        }
        // tray side: shift c + e at y = wall_out + e, -0.6 at y = wall_out - c - 0.6
        hull() {
            translate([0, wall_out + e, 0]) xz_extrude(0, 0.01) translate([0, -(c + e)]) scallop_outline(a, b, r);
            translate([0, wall_out - c - 0.6, 0]) xz_extrude(0, 0.01) translate([0, 0.6]) scallop_outline(a, b, r);
        }
    }
}

// ------------------------------------------------------------
// Joining rails. Trapezoid by two explicit widths, never a flank
// angle, extruded along Z so nothing overhangs. The sections (male, and the groove
// offset from it, D57) live in rail_profile.scad, shared with the coupon.
// ------------------------------------------------------------

module rail_male_one(y, z1) {
    // D58: the rail's flanks are EXACTLY rail_male_2d() at every height. (Until D58 the underside was a
    // hull of the section's prism with a sliver at the wall face, which pushed both flanks outward over
    // the whole height: +0.171 per side at the root at z 20, +0.023 at z 80, so the ganged gap was 0.13
    // where the groove said 0.30.) The 45 degree printable underside is now a CUT of the exact prism by a
    // wedge: the rail's first solid at x = -d is z = d above rail_z0, up to rail_lead_bot.
    zh = z1 - rail_z0 - rail_lead;
    translate([0, y, rail_z0]) {
        // one solid for the section and its weld block, cut by the wedge, so the underside is one surface
        // (the cut's edge at the wall face lies inside the bottom face, not on another solid's edge)
        intersection() {
            linear_extrude(height = zh)
                union() {
                    rail_male_2d();
                    translate([0, -rail_root_w / 2]) square([weld_embed, rail_root_w]);
                }
            rotate([90, 0, 0]) linear_extrude(height = 4 * rail_tip_w, center = true)
                polygon([[ weld_embed + 1, -1], [weld_embed + 1, zh + 1], [-rail_out - 1, zh + 1], [-rail_out - 1, rail_lead_bot],
                         [-rail_lead_bot, rail_lead_bot], [0, 0], [weld_embed + 1, 0]]);
        }
        translate([0, 0, zh])
            linear_extrude(height = rail_lead, scale = 0.45)
                rail_male_2d();
        // the weld block's last rail_lead (inside the wall), reaching 0.5 down into the main solid and 0.2 in
        // from each of its faces so no two faces share a plane
        translate([0.2, -rail_root_w / 2 + 0.2, zh - 0.5])
            cube([weld_embed - 0.4, rail_root_w - 0.4, rail_lead + 0.5]);
    }
}

module rail_male() {
    rail_male_one(rail1_y, rail1_z1);
    rail_male_one(rail2_y, rail2_z1);
}

module rail_boss_one(y, z1, right) {
    translate([right ? module_w - wall_out - rail_boss : wall_out - weld_embed,
               y - rail_boss_w / 2, 0])
        cube([rail_boss + weld_embed, rail_boss_w, z1]);
}

// The buttresses are INTERSECTED with the outer silhouette rather than capped
// at a guessed height. Capping at the centreline left rail 1 proud at its
// front edge and it speared the pick lid; capping at the footprint's low end
// left a 0.3mm wedge of wall that tore a hole in the mesh.
// The silhouette used for that clip, with the pick plane dropped a hair so the
// buttress tops land strictly inside the shell instead of on its own top face.
OUTER_CLIP = [
    [0,         0],
    [module_d,  0],
    [module_d,  flare_zo],                // the back wall leans out above here (D42)
    [module_d_top, hopper_rim],
    [yB_tray1,  hopper_rim],
    [yB_tray1,  trayB_rim      - boss_clip_drop],
    [0,         pickplane_front - boss_clip_drop]
];

// The rail-1 buttress's back face is vertical and its top is the sloped plane, so
// where they meet is the same 46 degree edge every wall's back face has with this
// plane; here it sits next to the groove that tore in test prints 1 and 2, so it
// is bevelled like the groove's front lip (D43): boss_bevel x boss_bevel in the
// plane's own frame, which leaves a 90 degree or wider edge.
module boss_back_bevel(x0, x1) {
    c = boss_bevel; y1 = rail1_y + rail_boss_w / 2;
    ya = y1 - c * cos(pick_lid_slope);                          // c along the top surface
    A = [ya, pickplane(y1) - boss_clip_drop - c * sin(pick_lid_slope)];
    B = [y1, pickplane(y1) - boss_clip_drop - c];
    d = B - A;
    // the half-plane above the line AB, extended past both ends: it crosses the
    // boss's top at A and ends in the air behind the back face, so no cutter face
    // lies on a face of the boss
    L1 = A - 2 * d; L2 = B + 2 * d;
    yz_extrude(x0, x1) polygon([L1, L2, [L2[0], L2[1] + 10], [L1[0], L1[1] + 10]]);
}
module rail_bosses() {
    intersection() {
        union() {
            for (right = [true, false]) {
                rail_boss_one(rail1_y, trayB_rim, right);
                rail_boss_one(rail2_y, fill_seat_z - 0.3, right);
            }
        }
        yz_extrude(0, module_w) polygon(OUTER_CLIP);
    }
}
// cut from the finished body, only in the bay (0.1 off the side wall's inner face)
module boss_bevels() {
    boss_back_bevel(wall_out + 0.1, wall_out + rail_boss + 1);
    boss_back_bevel(module_w - wall_out - rail_boss - 1, module_w - wall_out - 0.1);
}

// Corner beads (D41, revision 11, redesigned after the review). Test print 3: the last
// capsules in row A lodge in the 55 degree wedge where the 35 degree floor meets the
// front wall. Three small beads per bay, each a short half-round rib with a hemispherical
// end: radius bead_r, its axis ON the floor surface, running from the front wall out
// along the fall line for bead_len. They are for pushing a capsule's end against (it
// rides up the rib's side and tips), not a ramp. Attached to the wall and the floor, so
// nothing is behind them; their sides are vertical to the layers and their ends face up
// and out, so they print without support; the 6.2 mm clear gaps between ribs are narrower
// than a capsule (11), so no capsule can wedge between two. Clipped to the tray: not out
// through the front face, not below the bed.
module corner_beads() {
    if (bead_r > 0)
        intersection() {
            union() for (i = [0 : bays - 1])
                for (f = bead_fracs) {
                    // J: the floor/wall junction under the bead's axis, nudged off the wall's face and
                    // up off the floor's surface so no sphere vertex row lies ON either plane
                    J = [wall_x1(i) + bay_w * f, yA_tray0 + 0.07, base_z + 0.05];
                    translate(J) hull() {
                        sphere(r = bead_r, $fn = 32);
                        translate([0, (bead_len - bead_r) * cos(trayA_tilt_deg), (bead_len - bead_r) * sin(trayA_tilt_deg)])
                            sphere(r = bead_r, $fn = 32);
                    }
                }
            translate([0, yA_tray0 - 1.0, base_z - 1.5]) cube([module_w, bead_len + 4, 3 * bead_r + bead_len]);
        }
}

// Vertical fillets where each divider and side wall meets tray A's front wall
// (revision 11). The flow-void fillets (fillet_r) are rounded in the (y, z) profile
// only, so the joint between a divider and the front wall was a bare 90 degree T.
// Test print 3's section split along exactly that joint on its 1.2 mm half-divider
// (D46 fixes the section); the full module's joint is 2.4 on 2.8 mm and fused, but a
// bare T is where a layer line wants to open, and it is a square pocket for a capsule
// end. A tray_fillet_r quarter-round in each of the twelve corners, from the floor up
// to just under the scallop, fixes both; the scallop cut trims anything above.
//
// D48 does the same for tray B's front wall (the wall between the trays, face at yB_tray0):
// pills pile against it just as they do against tray A's front wall. Its gusset starts 1 under
// tray B's floor and stops tray_fillet_top_under below the wall's top plane at the face, so
// the plane's slope (the wall's top rises 0.96 mm per mm toward the back) clears it.
module front_fillets() {
    corner_fillets(yA_tray0, base_z - 1, trayA_front_h - 1.0);
    corner_fillets(yB_tray0, trayB_floor - 1, pickplane(yB_tray0) - tray_fillet_top_under);
}
module corner_fillets(y0, z0, z1) {
    r = tray_fillet_r;
    for (i = [0 : bays - 1]) {
        bx0 = wall_x1(i); bx1 = bx0 + bay_w;
        translate([0, 0, z0]) linear_extrude(height = z1 - z0) {
            difference() {      // left corner of the bay: the fillet grows toward +x
                translate([bx0 - 0.3, y0 - 0.3]) square([r + 0.3, r + 0.3]);
                translate([bx0 + r, y0 + r]) circle(r = r + 0.03, $fn = 48);   // +0.03: crosses the faces, not tangent to them
            }
            difference() {      // right corner: toward -x
                translate([bx1 - r, y0 - 0.3]) square([r + 0.3, r + 0.3]);
                translate([bx1 - r, y0 + r]) circle(r = r + 0.03, $fn = 48);
            }
        }
    }
}

// The stop blocks (D38). In each end bay's front corner of tray A, fused to the
// side wall and to the front wall, a block whose BACK face is perpendicular to
// the pick plane: it leaves the plane at pick_stop_y and runs pick_stop_depth
// down along the plane's inward normal, then drops vertically to the floor. The
// pick lid's lug bears on that face (pick_lid.scad). The face meets the block's
// top (the plane) at 90 degrees, so there is no knife edge, and it prints facing
// up and back at about 46 degrees above horizontal, with no support. Like the
// buttresses, the block is clipped by OUTER_CLIP so its top lands a hair under
// the shell's own top face instead of on it.
module stop_block_profile() {
    sa = sin(pick_lid_slope); ca = cos(pick_lid_slope);
    P0 = [pick_stop_y, pickplane(pick_stop_y)];
    F  = function(t) [P0[0] + t * sa, P0[1] - t * ca];
    Fm = F(-1.5); P1 = F(pick_stop_depth);
    polygon([[1.0, Fm[1]], Fm, P1, [P1[0], base_z - 1], [1.0, base_z - 1]]);
}
// The filler (G4, revision 10 re-review). Between a stop block's lower back face
// (y 10.0) and the rail-1 buttress (from y 14.3) there was a 4.3 mm blind slot,
// open only toward the bay, floor to plane, that traps small tablets and fragments
// and cannot be cleaned. This fills it, x from the side wall to just inside the
// buttress's inner face, y from inside the block to well into the buttress. Its top
// falls at 45 degrees toward the bay (so it sheds, and prints facing up), starting
// pick_filler_drop under the block's corner P1 and ending in the bay's own air, well
// under the lug's swept envelope.
module stop_filler_profile() {   // in (x, z), for the LEFT side; mirrored for the right
    sa = sin(pick_lid_slope); ca = cos(pick_lid_slope);
    zt = pickplane(pick_stop_y) - pick_stop_depth * ca - pick_filler_drop;     // top at the side wall
    xe = wall_out + pick_stop_w - 0.3;      // as wide as the stop block (less 0.3, not coplanar with its side): D43 slimmed the buttress to 3 mm, narrower than the block, and a filler to the buttress left a 3 x 6 mm nook beside it
    polygon([[wall_out - weld_embed, base_z - 1], [xe, base_z - 1],
             [xe, zt - (xe - wall_out)], [wall_out, zt], [wall_out - weld_embed, zt]]);
}
module stop_filler_left() {
    y0 = pick_stop_back_y - 0.5; y1 = rail1_boss_y0 + 0.5;
    translate([0, y1, 0]) rotate([90, 0, 0]) linear_extrude(height = y1 - y0) stop_filler_profile();
}
module stop_blocks() {
    intersection() {
        union() {
            yz_extrude(wall_out - weld_embed, wall_out + pick_stop_w) stop_block_profile();
            yz_extrude(module_w - wall_out - pick_stop_w, module_w - wall_out + weld_embed) stop_block_profile();
            stop_filler_left();
            translate([module_w, 0, 0]) mirror([1, 0, 0]) stop_filler_left();
        }
        yz_extrude(0, module_w) polygon(OUTER_CLIP);
    }
}
// G7: the block's top is clipped boss_clip_drop under the plane (a top ON the
// plane is a coplanar union that fails to weld), which left a 0.2 mm step against
// the front wall's top at y = 2.8. The front wall's top over the pillar is trimmed
// to the same height with a cutter whose floor is the clip polygon itself, a hair
// ABOVE the block's top (stop_trim_lift), so the two are flush to within 0.05 mm
// and no two faces coincide. The lid still floats pick_lid_gap over the plane.
module stop_trim() {
    for (x0 = [wall_out, module_w - wall_out - pillar_w])
        intersection() {
            yz_extrude(x0, x0 + pillar_w) polygon([[-1, -1], [-1, 400], [pick_stop_back_y, 400], [pick_stop_back_y, -1]]);
            translate([0, 0, stop_trim_lift]) yz_extrude(x0, x0 + pillar_w)
                difference() { translate([-5, 20]) square([60, 400]); polygon(OUTER_CLIP); }
        }
}

module rail_socket_cut() {
    for (r = [[rail1_y, rail1_soc_z1], [rail2_y, rail2_soc_z1]])
        translate([module_w, r[0], rail_z0]) {
            linear_extrude(height = r[1] - rail_z0)
                rail_groove_2d();
            translate([0, -(rail_root_w / 2 + rail_clear), 0])
                cube([weld_embed, rail_root_w + 2 * rail_clear, r[1] - rail_z0]);
        }
}

// The rail-1 groove breaks out through the SLOPED pick plane, and its front
// flank is vertical, so the lip of material just in front of it ended in a
// 46 degree knife edge about 2 mm tall: the spot that tore in test prints 1 and 2
// (revision 10 final review, H2). A countersink, sheared to the plane, takes a
// groove_chamfer x groove_chamfer 45 degree bevel off the groove's mouth in the
// plane's own frame: built flat (z' above the plane) and sheared by the plane's
// slope, so in the body it leaves the front lip a >= 90 degree edge and the back
// lip 134 degrees. It stops at the groove's floor plane so the skin behind the
// groove keeps its full thickness. The groove stays open through the top.
module groove_outline() {
    rail_groove_2d();
}
// The skin's free height (revision 11 review K1). The plane rises 0.96 mm per mm toward
// the back, so over the groove's width the skin's top climbed up to 6.4 mm (2.6 x its
// own thickness) above the front lip beside it: a 2.4 mm wall standing free on its
// outer side. Its top is trimmed flat to skin_cap_z, no more than rail_skin above the
// front lip's lowest top (which is the clipped buttress, pick_plane - boss_clip_drop,
// at the groove's tip depth, 0.5 mm in front of the flank). The back lip is not
// touched, so the trimmed skin ends in a step up to it, a 90 degree inside corner; the
// front lip is not touched. The cutter reaches skin_trim_over past the groove floor
// into the groove's own air, so no cutter face lies on the skin's outer face; at the
// back it clips the back lip's lowest 0.4 mm by at most 0.14 mm (named in calculations.md).
module skin_trim() {
    y0 = rail1_y - rail_tip_w / 2 - rail_clear + 0.4;
    y1 = rail1_y + rail_tip_w / 2 + rail_clear + 0.15;     // +0.15: not on the back flank's edge line at the groove floor (a coplanar edge)
    x0 = module_w - wall_out - rail_boss - 1;
    x1 = module_w - rail_out - rail_depth_clear + skin_trim_over;
    translate([x0, y0, skin_cap_z]) cube([x1 - x0, y1 - y0, 60]);
}

module rail1_countersink() {
    c = groove_chamfer;
    sl = (trayB_rim - pickplane_front) / yB_tray1;
    intersection() {
        multmatrix([[1, 0, 0, module_w], [0, 1, 0, rail1_y], [0, sl, 1, pickplane(rail1_y)], [0, 0, 0, 1]])
            hull() {
                translate([0, 0, -c]) linear_extrude(height = 0.01) groove_outline();
                translate([0, 0, 3]) linear_extrude(height = 0.01) offset(delta = c + 3) groove_outline();
            }
        translate([module_w - rail_out - rail_depth_clear + 0.06, 0, 0]) cube([rail_out + 10, 400, 400]);   // 0.06 off the floor: a cutter face ON the groove floor is a coplanar boolean; the 0.06 strip of un-bevelled lip left beside the floor is below the nozzle
        // front flank only: the back lip meets the plane at 134 degrees and needs no bevel
        translate([module_w - 20, -1, 0]) cube([40, rail1_y + 1, 400]);
    }
}

// Label recesses for 1/2 inch TZe tape: the lower strip on the module's own
// front face, below the lid skirt so it reads with the lid on; the upper strip
// on the wall between the trays, which faces forward over tray A and is read at
// a glance once the lid is off.
// Both cuts start label_cut_over OUTSIDE the face and go label_z into it. The
// upper cut used to start label_z in front of the wall and run label_z + 1
// deep, i.e. 1.0mm into a 2.4mm wall instead of 0.6 (INCIDENTS.md, rev 6).
module label_cuts() {
    for (i = [0 : bays - 1]) {
        cx = bay_center_x(i);
        for (zc = [label_z_center, label_b_center])      // row A low, row B above it
            translate([cx - label_w / 2, -label_cut_over, zc - label_h / 2])
                cube([label_w, label_cut_over + label_z, label_h]);
    }
}

// Recesses for four stick-on rubber feet (D24), cut up into the base.
module foot_pad_cuts() {
    for (p = [[foot_pad_inset, foot_pad_inset],
              [module_w - foot_pad_inset, foot_pad_inset],
              [foot_pad_inset, module_d - foot_pad_inset],
              [module_w - foot_pad_inset, module_d - foot_pad_inset]])
        translate([p[0], p[1], -1])
            cylinder(h = 1 + foot_pad_depth, d = foot_pad_d, $fn = 48);
    // elephant foot squeezes each recess's mouth smaller: a bed_chamfer lead-in cone on the
    // bed face (it crosses the recess wall at bed_chamfer, steeper than the wall is tall, so
    // it is transversal to it) keeps the full diameter for the stick-on foot
    for (p = [[foot_pad_inset, foot_pad_inset],
              [module_w - foot_pad_inset, foot_pad_inset],
              [foot_pad_inset, module_d - foot_pad_inset],
              [module_w - foot_pad_inset, module_d - foot_pad_inset]])
        translate([p[0], p[1], -1])
            cylinder(h = 1 + bed_chamfer + 0.2, d1 = foot_pad_d + 2 * (bed_chamfer + 1.0), d2 = foot_pad_d - 0.4, $fn = 48);
}

// ------------------------------------------------------------
module body_geometry() {
    difference() {
        union() { body_shell(); outlet_chamfers(); vault_roof(); rail_male(); rail_bosses(); stop_blocks(); corner_beads(); front_fillets(); }
        fill_seat_cut();
        front_scallop_cut();
        stop_trim();
        rail_socket_cut();
        rail1_countersink();
        boss_bevels();
        skin_trim();
        label_cuts();
        foot_pad_cuts();
        mouth_chamfer_cut();
        cubby_chamfer_cut();
        scallop_chamfer_cuts();
    }
}

// SUBFEATURES: body_shell, outlet_chamfers, vault_roof, rail_male
SUBFEATURE = is_undef(SUBFEATURE) ? "" : SUBFEATURE;
module subfeature_by_name(name) {
    if (name == "body_shell") body_shell();
    else if (name == "outlet_chamfers") outlet_chamfers();
    else if (name == "vault_roof") vault_roof();
    else if (name == "rail_male") rail_male();
    else assert(false, str("Unknown sub-feature '", name, "' in body.scad"));
}
if (SUBFEATURE != "") subfeature_by_name(SUBFEATURE);
else body_geometry();
