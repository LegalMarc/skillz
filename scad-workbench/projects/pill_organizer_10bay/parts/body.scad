// ============================================================
// body.scad -- the terraced two-tier organizer body, 10 bays.
//
// Local origin: front-bottom-left outer corner of the module.
//   +X to the right, +Y toward the back, +Z up. This IS the
//   assembly datum, so layout.scad places it at [0,0,0].
//
// Material: PLA or PETG.
// Print orientation: as modelled, flat on its base, no supports.
//   Every ramp underside is 42 deg from vertical and every rail
//   flank is extruded along Z, so nothing overhangs past 45 deg.
//
// EXPECTED_BBOX: [235.0, 229.2, 205.001]
// ============================================================

include <../params.scad>

use_param("hinge_rod_d", "body_rod", "rod carried by the hopper front wall");
assert(hinge_rod_d >= 5.0,
       "hinge_rod_d under 5mm: the rod bridges a full bay width unsupported and would sag");

// ------------------------------------------------------------
// Helpers
// ------------------------------------------------------------
// Extrude a (y, z) profile along X, from x0 to x1.
module yz_extrude(x0, x1) {
    rotate([90, 0, 90]) translate([0, 0, x0])
        linear_extrude(height = x1 - x0) children();
}

// X spans of the six full-height walls: two outer, four dividers.
function wall_x0(k) = k == 0 ? 0
                    : k == bays ? module_w - wall_out
                    : wall_out + k * bay_w + (k - 1) * wall_div;
function wall_x1(k) = k == 0 ? wall_out
                    : k == bays ? module_w
                    : wall_x0(k) + wall_div;

pocketB_rim_z = hopper_a_rim + pocket_h;      // 141.0
tier_dy       = yA_back - wall_out;           // 113.2
tier_dz       = tier_lift;                    // 101.0

// Tolerance, not equality: hopper_b_rim and hopper_a_rim + tier_dz are
// algebraically the same number reached by two different chains of floating
// point, and == on them fails on the last bit.
assert(abs(hopper_b_rim - (hopper_a_rim + tier_dz)) < 1e-6,
       "the two tiers' rims are no longer one tier_lift apart -- the shared section has drifted");

// ------------------------------------------------------------
// Outer silhouette, in (y, z). This is the maximum-material
// outline; every cavity is subtracted from it afterwards.
// ------------------------------------------------------------
// The front face of ONE tier, walked forward (decreasing Y): the stepped
// hopper wall, then the drop to that tier's tray rim. Generated per tier from
// one profile rather than written out twice -- writing it twice is exactly how
// the tier B wall lost its step while tier A had it, which the motion sweep
// caught as a pick lid that stopped 8 degrees early on the back tier only.
function tier_front(dy, dz) = [
    [yA_pocket1 + wall_step + dy, hopper_a_rim + dz],                    // stepped wall, top
    [yA_pocket1 + wall_step + dy, lid_stop_z + wall_step_rise + dz],     // down its front face
    [yA_pocket1 + dy,             lid_stop_z + dz],                      // chamfer to the lower face
    [yA_pocket1 + dy,             pocketA_rim_z + dz]                    // down to that tier's tray rim
];

OUTER = concat(
    [[0, 0], [yB_back, 0], [yB_back, hopper_b_rim]],
    tier_front(tier_dy, tier_dz),            // tier B's hopper wall
    [[yA_hop1, pocketA_rim_z + tier_dz],     // forward across the tier B tray
     [yA_hop1, hopper_a_rim]],               // down pocket B's front wall to the tier A rim
    tier_front(0, 0),                        // tier A's hopper wall
    [[0, pocketA_rim_z]]
);

// One bay's cavity for one tier, in tier-A coordinates: pick tray,
// outlet gap under the hopper front wall, ramp, hopper mouth.
// The mouth is full width at the rim so the fill lid can pass down, and steps
// IN by fill_ledge_w just below the seat plane to form the lip the lid lands
// on. The step is a 45 degree chamfer, so the lip's underside does not
// overhang. Building the lip out of the cavity profile -- rather than adding a
// ledge solid afterwards -- is deliberate: the added-solid version put two
// boolean faces on the same plane and produced 78 zero-length edges.
CAVITY = [
    [wall_out,                base_t],                      // tray floor, front
    [yA_pocket1,              base_t],                      // tray floor, back = ramp foot
    [yA_hop1,                 ramp_top_z],                  // up the ramp at ramp_deg
    [yA_hop1,                 fill_seat_z - fill_ledge_w],  // up the hopper back wall
    [yA_hop1 - fill_ledge_w,  fill_seat_z],                 // 45 deg chamfer under the back lip
    [yA_hop1 - fill_ledge_w,  fill_seat_z + 1],
    [hop_mouth_y0 + fill_ledge_w, fill_seat_z + 1],
    [hop_mouth_y0 + fill_ledge_w, fill_seat_z],
    [hop_mouth_y0,            fill_seat_z - fill_ledge_w],  // 45 deg chamfer under the front lip
    [hop_mouth_y0,            lid_stop_z + wall_step_rise], // down the stepped wall's inner face
    [yA_hop0,                 lid_stop_z],                  // chamfer back to the lower inner face
    [yA_hop0,                 outletA_top_z],               // down the hopper front wall's inner face
    [yA_pocket1,              outletA_top_z + wall_div],    // 45 deg: the outlet ceiling RISES toward
                                                            // the tray, so the throat diverges as pills
                                                            // leave it, and the wall's underside is a
                                                            // chamfer rather than a flat bridged ceiling
    [yA_pocket1,              pocketA_rim_z],               // up the hopper front wall's outer face
    [wall_out,                pocketA_rim_z]                // forward across the tray rim
];

// The full-width slot at the rim, which the lid drops through. It overlaps
// CAVITY by 1mm in Z so the union is volumetric, never a coplanar touch.
MOUTH = [
    [hop_mouth_y0, fill_seat_z - seat_lip_drop],
    [yA_hop1,      fill_seat_z - seat_lip_drop],
    [yA_hop1,      hopper_a_rim + 1],
    [hop_mouth_y0, hopper_a_rim + 1]
];

// Opening the cavity rounds its convex corners, which puts a fillet on
// every internal corner of the solid -- the tray floor/wall junctions and
// the ramp foot, where a pill would otherwise wedge. Applied to the cavity
// only, never to OUTER, so the part's bounding box stays exact.
module cavity_2d() {
    union() {
        offset(r = fillet_r) offset(r = -fillet_r) polygon(CAVITY);
        polygon(MOUTH);
    }
}

// ------------------------------------------------------------
// Sub-feature: the shell -- silhouette less every bay cavity.
// ------------------------------------------------------------
module body_shell() {
    difference() {
        yz_extrude(0, module_w) polygon(OUTER);
        for (i = [0 : bays - 1]) {
            x0 = wall_x1(i);
            x1 = x0 + bay_w;
            yz_extrude(x0, x1) cavity_2d();                                  // tier A
            yz_extrude(x0, x1) translate([tier_dy, tier_dz]) cavity_2d();    // tier B
        }
    }
}

// ------------------------------------------------------------
// Fill-lid seat. The lid drops into the mouth and finishes flush
// with the rim: the four divider tops are cut down by one lid
// thickness, and a ledge is ADDED inward from the four mouth
// walls to carry the lid's edges. Nothing is rebated into the
// rim itself, so no wall is left as a thin standing fin.
// ------------------------------------------------------------
module fill_seat_cut(dy, dz) {
    translate([0, dy, dz]) {
        // Only the four divider tops stand above the seat plane inside the
        // mouth -- the rail buttresses now stop below it. Each box oversteps
        // its divider in X into the mouth void that the cavity already cut, so
        // no cut face lands exactly on an existing one.
        for (k = [1 : bays - 1])
            translate([wall_x0(k) - seat_cut_over,
                       hop_mouth_y0 - seat_cut_over, fill_seat_z])
                cube([wall_div + 2 * seat_cut_over,
                      hop_mouth_d + 2 * seat_cut_over,
                      lid_t + 2]);

        // Barb pockets in the front and back mouth walls.
        for (s = [0, 1])
            translate([module_w / 2 - fill_tab_w / 2 - 0.5,
                       s == 0 ? hop_mouth_y0 - fill_tab_barb : yA_hop1 - 0.01,
                       fill_tab_pocket_z])
                cube([fill_tab_w + 1.0, fill_tab_barb + 0.01, fill_tab_pocket_h]);

        // The seat lips run right under the lid's front and back edges, which
        // is exactly where its snap tabs hang down. Relieve them where the
        // tabs pass, or the tabs drive straight through the lips.
        for (side = [0, 1])
            translate([module_w / 2 - fill_tab_w / 2 - 1.0,
                       side == 0 ? hop_mouth_y0 - 1 : yA_hop1 - fill_ledge_w - 1,
                       fill_seat_z - fill_ledge_w - 1])
                cube([fill_tab_w + 2.0, fill_ledge_w + 1, fill_ledge_w + 2]);

        // Fingernail relief: takes the top off the front mouth wall over a
        // short span so the seated lid's front edge can be lifted.
        translate([module_w / 2 - fill_grip_d / 2,
                   hop_mouth_y0 - wall_div - 1, fill_seat_z])
            cube([fill_grip_d, wall_div + 1 + 2, lid_t + 2]);
    }
}

// ------------------------------------------------------------
// Sub-feature: the pick-lid hinge bar -- one rod per tier, carried
// by a web on top of each of the six walls.
// ------------------------------------------------------------
WEB = [
    [hinge_rod_y - hinge_clip_or - 1.0, pocketA_rim_z - weld_embed],
    [yA_pocket1 + weld_embed,           pocketA_rim_z - weld_embed],
    [yA_pocket1 + weld_embed,           hinge_rod_z + hinge_clip_or],
    [hinge_rod_y - hinge_clip_or - 1.0, hinge_rod_z + hinge_clip_or]
];

module hinge_bar(dy, dz) {
    translate([0, dy, dz]) {
        // The rod runs the full width; it is exposed in the five bay spans,
        // where the lid's C-clips snap onto it.
        translate([0, hinge_rod_y, hinge_rod_z])
            rotate([0, 90, 0]) cylinder(d = hinge_rod_d, h = module_w);
        for (k = [0 : bays])
            yz_extrude(wall_x0(k), wall_x1(k)) polygon(WEB);
    }
}

module hinge_bar_a() { hinge_bar(0, 0); }
module hinge_bar_b() { hinge_bar(tier_dy, tier_dz); }

// ------------------------------------------------------------
// Sub-feature: joining rails. Trapezoid by two explicit widths
// (never a flank angle -- INCIDENTS 2026-08-30), extruded along
// Z so no flank overhangs at all.
// ------------------------------------------------------------
module rail_trapezoid(root_w, tip_w, depth, clear = 0) {
    polygon([[ 0,     -(root_w / 2 + clear)],
             [ 0,      (root_w / 2 + clear)],
             [-depth,  (tip_w  / 2 + clear)],
             [-depth, -(tip_w  / 2 + clear)]]);
}

module rail_male_one(y, z1) {
    translate([0, y, rail_z0]) {
        linear_extrude(height = z1 - rail_z0 - rail_lead)
            rail_trapezoid(rail_root_w, rail_tip_w, rail_out);
        translate([0, 0, z1 - rail_z0 - rail_lead])
            linear_extrude(height = rail_lead, scale = 0.45)
                rail_trapezoid(rail_root_w, rail_tip_w, rail_out);
        // Weld block: reaches into the side wall so the rail is not attached to
        // the body by a coincident face alone. Kept separate from the trapezoid
        // so the flank geometry the socket has to receive stays exact.
        translate([0, -rail_root_w / 2, 0])
            cube([weld_embed, rail_root_w, z1 - rail_z0]);
    }
}

module rail_male() {
    rail_male_one(rail1_y, rail1_z1);
    rail_male_one(rail2_y, rail2_z1);
}

// Buttress behind each groove, and behind each male root, on the inner
// face of the side wall. Added after the cavities are cut.
// z1 here is neither the groove top nor the wall top: the buttress stops just
// BELOW the fill-lid seat plane. Run it to the wall top and it stands proud
// into the seat and holds the lid off it; end it exactly ON the seat plane and
// the union and the seat cut share a plane, which left a detached 1.1mm sliver
// of buttress behind. Above the buttress the groove cuts through the bare side
// wall into the mouth void -- which the lid itself then fills.
module rail_boss_one(y, z1, right) {
    w = rail_tip_w + 8;
    translate([right ? module_w - wall_out - rail_boss : wall_out - weld_embed,
               y - w / 2, 0])
        cube([rail_boss + weld_embed, w, z1]);
}

module rail_bosses() {
    for (right = [true, false]) {
        rail_boss_one(rail1_y, fill_seat_z - 0.3, right);
        rail_boss_one(rail2_y, fill_seat_z + tier_dz - 0.3, right);
    }
}

module rail_socket_cut() {
    for (r = [[rail1_y, rail1_soc_z1], [rail2_y, rail2_soc_z1]])
        translate([module_w, r[0], rail_z0]) {
            linear_extrude(height = r[1] - rail_z0)
                rail_trapezoid(rail_root_w, rail_tip_w,
                               rail_out + rail_depth_clear, rail_clear);
            translate([0, -(rail_root_w / 2 + rail_clear), 0])
                cube([weld_embed, rail_root_w + 2 * rail_clear, r[1] - rail_z0]);
        }
}

// ------------------------------------------------------------
// Label recesses: one per bay, on the front face for tier A and on
// pocket B's front wall for tier B.
// ------------------------------------------------------------
module label_cuts() {
    for (i = [0 : bays - 1]) {
        cx = bay_center_x(i);
        translate([cx - label_w / 2, -1, pocketA_rim_z / 2 - label_h / 2])
            cube([label_w, 1 + label_z, label_h]);
        translate([cx - label_w / 2, yA_hop1 - label_z,
                   hopper_a_rim + pocket_h / 2 - label_h / 2])
            cube([label_w, label_z + 1, label_h]);
    }
}

// ------------------------------------------------------------
module body_geometry() {
    difference() {
        union() {
            body_shell();
            hinge_bar_a();
            hinge_bar_b();
            rail_male();
            rail_bosses();
        }
        fill_seat_cut(0, 0);
        fill_seat_cut(tier_dy, tier_dz);
        rail_socket_cut();
        label_cuts();
    }
}

// SUBFEATURES: body_shell, hinge_bar_a, hinge_bar_b, rail_male
SUBFEATURE = is_undef(SUBFEATURE) ? "" : SUBFEATURE;

module subfeature_by_name(name) {
    if (name == "body_shell")  body_shell();
    else if (name == "hinge_bar_a") hinge_bar_a();
    else if (name == "hinge_bar_b") hinge_bar_b();
    else if (name == "rail_male")   rail_male();
    else assert(false, str("Unknown sub-feature '", name, "' in body.scad"));
}

if (SUBFEATURE != "") subfeature_by_name(SUBFEATURE);
else body_geometry();
