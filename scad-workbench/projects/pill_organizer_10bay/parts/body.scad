// ============================================================
// body.scad -- the organizer body. Two pick trays at the FRONT
// under one lid, two fill mouths at the BACK under one lid.
//
//   [ tray A ][ tray B ][ hopper B mouth ][ hopper A mouth ]
//     front                                           back
//
// Hopper B is the front mouth and feeds tray B, right in front
// of it -- a plain ramp. Hopper A is the BACK mouth and feeds
// the FRONT tray, so its chute ducks under tray B and under
// hopper B. That crossing is what lifts tray B onto a pedestal;
// see params.scad section 4.
//
// Local origin: front-bottom-left outer corner. +X right,
// +Y back, +Z up. This is the assembly datum.
//
// Material: PLA or PETG.
// Print orientation: as modelled, flat on its base, no supports.
//
// EXPECTED_BBOX: [235.0, 205.474, 200.0]
// ============================================================

include <../params.scad>

// ------------------------------------------------------------
module yz_extrude(x0, x1) {
    rotate([90, 0, 90]) translate([0, 0, x0])
        linear_extrude(height = x1 - x0) children();
}

function wall_x0(k) = k == 0 ? 0
                    : k == bays ? module_w - wall_out
                    : wall_out + k * bay_w + (k - 1) * wall_div;
function wall_x1(k) = k == 0 ? wall_out
                    : k == bays ? module_w
                    : wall_x0(k) + wall_div;

// ------------------------------------------------------------
// Outer silhouette: the maximum-material outline, in (y, z).
// Two steps down toward the front, one per tray row.
// ------------------------------------------------------------
OUTER = [
    [0,         0],
    [module_d,  0],
    [module_d,  hopper_rim],
    [yB_tray1,  hopper_rim],     // hopper B's front wall, outer face
    [yB_tray1,  trayB_rim],      // top of the pick plane, at tray B's rim
    [0,         pickplane_front] // ONE straight slope forward to the front face:
                                 // every wall over both trays dies on this plane,
                                 // so a single flat plate lids both rows
];

// ------------------------------------------------------------
// VOID_B -- tray B, its outlet, and hopper B. The simple row:
// the mouth sits directly behind the tray it feeds.
// ------------------------------------------------------------
VOID_B = [
    [yB_tray0,                   trayB_floor],
    [yB_tray1,                   trayB_floor],                 // ramp foot
    [yB_hop1,                    rampB(yB_hop1)],              // up the ramp
    [yB_hop1,                    fill_seat_z - fill_ledge_w],
    [yB_hop1 - fill_ledge_w,     fill_seat_z],                 // 45 deg under the back lip
    [yB_hop1 - fill_ledge_w,     hopper_rim + 1],
    [yB_wall1 + fill_ledge_w,    hopper_rim + 1],
    [yB_wall1 + fill_ledge_w,    fill_seat_z],
    [yB_wall1,                   fill_seat_z - fill_ledge_w],  // 45 deg under the front lip
    [yB_wall1,                   outletB_top],
    [yB_tray1,                   outletB_top + wall_div],      // 45 deg, as tray A's
    [yB_tray1,                   trayB_rim],
    [yB_tray0,                   pickplane(yB_tray0)]     // up under the pick plane
];

// The mouth both hoppers share, full width at the rim so the lid can pass
// down, overlapping the voids by 1mm in Z so the union is volumetric. Without
// it the seat lips ran all the way to the rim and the lid could not drop in --
// 6450 mm^3 of it was buried in them.
MOUTH = [
    [hop_mouth_y0, fill_seat_z - seat_lip_drop],
    [hop_mouth_y1, fill_seat_z - seat_lip_drop],
    [hop_mouth_y1, hopper_rim + 1],
    [hop_mouth_y0, hopper_rim + 1]
];

// ------------------------------------------------------------
// VOID_A -- tray A, its outlet, the crossing chute, and hopper A.
// One continuous void: the chute IS hopper A's lower half, so the
// volume the crossing costs in height it gives back in capacity.
// Its ceiling is the underside of tray B, then the underside of
// hopper B's ramp, which is why the two never meet.
// ------------------------------------------------------------
VOID_A = [
    [yA_tray0,                   base_z],
    [yA_tray1,                   base_z],                      // chute foot
    [yA_hop1,                    rampA(yA_hop1)],              // one straight climb to the back
    [yA_hop1,                    fill_seat_z - fill_ledge_w],
    [yA_hop1 - fill_ledge_w,     fill_seat_z],                 // 45 deg under the back lip
    [yA_hop1 - fill_ledge_w,     hopper_rim + 1],
    [yA_hop0 + fill_ledge_w,     hopper_rim + 1],
    [yA_hop0 + fill_ledge_w,     fill_seat_z],
    [yA_hop0,                    fill_seat_z - fill_ledge_w],  // 45 deg under the front lip
    [yA_hop0,                    rampB(yB_hop1) - chute_ceil], // down to the chute ceiling
    // The ceiling runs PARALLEL to the chute floor the whole way, holding a
    // constant chute_clear section. Following tray B's flat underside instead
    // left 7197 mm^2 of flat ceiling bridging 43mm across every bay -- the
    // single worst print risk in the part. Sloped at ramp_deg it self-supports,
    // and row A has capacity to spare for what the change gives back.
    [yB_wall1,                   rampA(yB_wall1) + chute_clear],
    [yA_wall1,                   rampA(yA_wall1) + chute_clear],
    [yA_tray1,                   rampA(yA_tray1) + chute_clear],// straight on into tray A: the
                                                               // chute's own section IS row A's
                                                               // outlet, and its ceiling is already
                                                               // a ramp_deg chamfer
    [yA_tray1,                   pickplane(yA_tray1)],   // up under the pick plane
    [yA_tray0,                   pickplane(yA_tray0)]
];

// Opening rounds the cavity's convex corners, which fillets every internal
// corner of the solid -- tray floors and the chute foot, where a pill would
// otherwise wedge. Applied to the flow voids only, never to OUTER, so the
// part's bounding box stays exact.
module void_a_2d() { offset(r = fillet_r) offset(r = -fillet_r) polygon(VOID_A); }
module void_b_2d() { offset(r = fillet_r) offset(r = -fillet_r) polygon(VOID_B); }
module mouth_2d()  { polygon(MOUTH); }

module body_shell() {
    difference() {
        yz_extrude(0, module_w) polygon(OUTER);
        for (i = [0 : bays - 1]) {
            x0 = wall_x1(i);
            yz_extrude(x0, x0 + bay_w) void_a_2d();
            yz_extrude(x0, x0 + bay_w) void_b_2d();
            yz_extrude(x0, x0 + bay_w) mouth_2d();
        }
    }
}

// ------------------------------------------------------------
// Fill-lid seat. One lid spans BOTH mouths, so everything standing
// above the seat plane between them comes down to it: the four
// dividers, and the wall that separates hopper A from hopper B.
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

    // Barb pockets: front one in hopper B's front wall, back one in the
    // module's back wall.
    for (s = [0, 1])
        translate([module_w / 2 - fill_tab_w / 2 - 0.5,
                   s == 0 ? hop_mouth_y0 - fill_tab_barb : hop_mouth_y1 - 0.01,
                   fill_tab_pocket_z])
            cube([fill_tab_w + 1.0, fill_tab_barb + 0.01, fill_tab_pocket_h]);

    // The seat lips run right under the lid's front and back edges, which is
    // exactly where its snap tabs hang down. Relieve them where the tabs pass,
    // or the tabs drive straight through the lips.
    for (side = [0, 1])
        translate([module_w / 2 - fill_tab_w / 2 - 1.0,
                   side == 0 ? hop_mouth_y0 - 1 : hop_mouth_y1 - fill_ledge_w - 1,
                   fill_seat_z - fill_ledge_w - 1])
            cube([fill_tab_w + 2.0, fill_ledge_w + 1, fill_ledge_w + 2]);

    // Fingernail relief in the front mouth wall.
    translate([module_w / 2 - fill_grip_d / 2, hop_mouth_y0 - wall_div - 1, fill_seat_z])
        cube([fill_grip_d, wall_div + 3, lid_t + 2]);
}

// ------------------------------------------------------------
// Joining rails. Trapezoid by two explicit widths, never a flank
// angle (INCIDENTS 2026-08-30), extruded along Z so nothing
// overhangs. Rail 1 sits beside tray B, rail 2 beside hopper B.
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
        translate([0, -rail_root_w / 2, 0])
            cube([weld_embed, rail_root_w, z1 - rail_z0]);
    }
}

module rail_male() {
    rail_male_one(rail1_y, rail1_z1);
    rail_male_one(rail2_y, rail2_z1);
}

// The buttress stops just BELOW the plane above it, never on it: ending a
// union exactly on a cut plane left a detached sliver of buttress behind.
module rail_boss_one(y, z1, right) {
    w = boss_w;
    translate([right ? module_w - wall_out - rail_boss : wall_out - weld_embed,
               y - w / 2, 0])
        cube([rail_boss + weld_embed, w, z1]);
}

// Rail 1's buttress lives under the SLOPED pick plane. Rather than guess a cap
// height for it -- capping at the centreline left it proud at the front edge
// and it speared the pick lid; capping at the footprint's low end left a 0.3mm
// wedge of wall that tore a hole in the mesh -- the buttresses are simply
// INTERSECTED with the outer silhouette. They then end exactly on whatever
// surface is above them, with no sliver and nothing to get wrong.
boss_w = rail_tip_w + 8;

module rail_bosses() {
    intersection() {
        union() {
            for (right = [true, false]) {
                rail_boss_one(rail1_y, trayB_rim, right);
                rail_boss_one(rail2_y, fill_seat_z - 0.3, right);
            }
        }
        yz_extrude(0, module_w) polygon(OUTER);
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

// Labels: tray A on the module's front face, tray B on its own front wall,
// which faces forward over tray A's lid and is read at a glance from standing.
module label_cuts() {
    for (i = [0 : bays - 1]) {
        cx = bay_center_x(i);
        translate([cx - label_w / 2, -1, pickplane_front / 2 - label_h / 2])
            cube([label_w, 1 + label_z, label_h]);
        translate([cx - label_w / 2, yA_tray1 - label_z,
                   (trayB_floor + pickplane(yA_tray1)) / 2 - label_h / 2])
            cube([label_w, label_z + 1, label_h]);
    }
}

// ------------------------------------------------------------
module body_geometry() {
    difference() {
        union() { body_shell(); rail_male(); rail_bosses(); }
        fill_seat_cut();
        rail_socket_cut();
        label_cuts();
    }
}

// SUBFEATURES: body_shell, rail_male
SUBFEATURE = is_undef(SUBFEATURE) ? "" : SUBFEATURE;
module subfeature_by_name(name) {
    if (name == "body_shell") body_shell();
    else if (name == "rail_male") rail_male();
    else assert(false, str("Unknown sub-feature '", name, "' in body.scad"));
}
if (SUBFEATURE != "") subfeature_by_name(SUBFEATURE);
else body_geometry();
