// ============================================================
// body.scad -- the organizer body, revision 8. Two pick trays
// at the FRONT under one lid, two fill mouths at the BACK under
// one lid.
//
//   [ tray A ][ tray B ][ hopper B mouth ][ hopper A mouth ]
//     front                                           back
//
// Hopper B is the front mouth and feeds tray B right in front
// of it -- a plain ramp. Hopper A is the BACK mouth and feeds
// the FRONT tray, so its chute ducks under tray B and under
// hopper B. See params.scad section 4 for why the chute runs at
// porch_deg under tray B and ramp_deg everywhere else.
//
// Local origin: front-bottom-left outer corner. +X right,
// +Y back, +Z up. This is the assembly datum.
//
// Material: PLA or PETG.
// Print orientation: as modelled, flat on its base, no supports.
//
// EXPECTED_BBOX: [245.0, 194.8, 189.0]
// ============================================================

include <../params.scad>

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
    [module_d,  hopper_rim],
    [yB_tray1,  hopper_rim],
    [yB_tray1,  trayB_rim],
    [0,         pickplane_front]
];
// The silhouette with its top edges rounded (D27): an opening pass rounds
// every convex corner, then a plain band puts the two base corners back so the
// first layers stay square on the bed. The step's inside corner is concave and
// is untouched.
module outer_2d() {
    union() {
        offset(r = edge_r_top) offset(r = -edge_r_top) polygon(OUTER);
        polygon([[0, 0], [module_d, 0],
                 [module_d, edge_r_top + 0.5], [0, edge_r_top + 0.5]]);
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
    [yA_hop1,                    fill_seat_z - fill_ledge_w],
    [yA_hop1 - fill_ledge_w,     fill_seat_z],
    [yA_hop1 - fill_ledge_w,     hopper_rim + 1],
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
CUBBY = [
    [cubby_y0,     base_t],
    [cubby_back,   base_t],                      // inside face of the retaining lip
    [cubby_back,   base_t + cubby_lip_h],        // up and over it
    [module_d + 1, base_t + cubby_lip_h],        // out through the back wall above it
    [module_d + 1, cubby_ceil_z(module_d + 1)],  // 45 degree ceiling (D21)
    [cubby_y0,     cubby_ceil_z(cubby_y0)]
];
// No fillet pass here: nothing flows through the cubby, and the closing
// operation the flow voids use would round the lip's own top edge away.
module cubby_2d() { polygon(CUBBY); }

module body_shell() {
    difference() {
        yz_extrude(0, module_w) outer_2d();
        for (i = [0 : bays - 1]) {
            x0 = wall_x1(i);
            yz_extrude(x0, x0 + bay_w) void_a_2d();
            yz_extrude(x0, x0 + bay_w) void_b_2d();
            yz_extrude(x0, x0 + bay_w) mouth_2d();
        }
        yz_extrude(wall_out, module_w - wall_out) cubby_2d();
    }
}

// ------------------------------------------------------------
// Outlet corner chamfers (D29). The top of each outlet opening -- the bottom
// edge of the wall between the trays, into tray A, and of hopper B's front
// wall, into tray B -- spans the whole bay with nothing under it, and test
// print 1 printed both ragged. A 45 degree triangle in each top corner, one
// per divider face, shortens that span by 2 x outlet_chamfer. Each prism
// reaches 1mm into its divider and up into the wall, and stops 0.05mm inside
// both faces of the wall in Y (D35): running it past them left a fin in the
// air on each side, and flush would put a face on a face of the shell.
// ------------------------------------------------------------
module outlet_corner(x_wall, dir, z_edge, z_top, y0, y1) {
    c = outlet_chamfer;
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
                          yA_tray1 + 0.05, yA_wall1 - 0.05);
            outlet_corner(side[0], side[1], outletB_top, outletB_top,
                          yB_tray1 + 0.05, yB_wall1 - 0.05);
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

// Round the body's four vertical corners (D27). Each cutter is the square
// corner block minus the corner cylinder, overstepping OUTWARD into air so no
// cut face lands on the body's own faces.
module corner_cuts() {
    r = corner_r;
    for (c = [[0, 0, 0], [module_w, 0, 90], [module_w, module_d, 180], [0, module_d, 270]])
        translate([c[0], c[1], -1]) rotate([0, 0, c[2]])
            linear_extrude(height = module_h + 2)
                difference() {
                    translate([-1, -1]) square([r + 1, r + 1]);
                    translate([r, r]) circle(r = r, $fn = 64);
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

// ------------------------------------------------------------
// Scalloped front wall (params.scad 4c). The lid plane cannot come down any
// further -- its back end is pinned to tray B's rim -- but the front WALL can.
// Each bay's share of the front face drops to trayA_front_h, while the four
// dividers and the two side walls still run up to the plane and carry the lid.
// The lid's skirt hangs down the outside and closes the scallops.
// ------------------------------------------------------------
module front_scallop_cut() {
    r = trayA_scallop_r;
    for (i = [0 : bays - 1]) {
        // The two end bays stop pillar_w short of their side wall (D38): the
        // front wall stays at the full pick-plane height there and the pick
        // lid's lug drops in behind it. No scallop_over on that side, since the
        // cut then ends in the middle of the front wall, on no face of its own.
        x0 = i == 0         ? wall_x1(i) + pillar_w : wall_x1(i) - scallop_over;
        x1 = i == bays - 1  ? wall_x1(i) + bay_w - pillar_w : wall_x1(i) + bay_w + scallop_over;
        xz_extrude(-1, wall_out + 1)
            offset(r = r)
                polygon([[x0 + r, trayA_front_h + r],
                         [x1 - r, trayA_front_h + r],
                         [x1 - r, trayA_front_h + 40],
                         [x0 + r, trayA_front_h + 40]]);
    }
}

// ------------------------------------------------------------
// Joining rails. Trapezoid by two explicit widths, never a flank
// angle, extruded along Z so nothing overhangs.
// ------------------------------------------------------------
module rail_trapezoid(root_w, tip_w, depth, clear = 0) {
    polygon([[ 0,     -(root_w / 2 + clear)],
             [ 0,      (root_w / 2 + clear)],
             [-depth,  (tip_w  / 2 + clear)],
             [-depth, -(tip_w  / 2 + clear)]]);
}

module rail_male_one(y, z1) {
    translate([0, y, rail_z0]) {
        // 45 degree underside: the full section from rail_lead_bot up, hulled
        // with a sliver at the wall face at the bottom, so nothing flat hangs
        // in mid-air. The sliver sits 0.5 inside the wall so no face coincides.
        hull() {
            translate([0, 0, rail_lead_bot])
                linear_extrude(height = z1 - rail_z0 - rail_lead - rail_lead_bot)
                    rail_trapezoid(rail_root_w, rail_tip_w, rail_out);
            translate([0, -rail_root_w / 2, 0]) cube([0.5, rail_root_w, 0.01]);
        }
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
    [module_d,  hopper_rim],
    [yB_tray1,  hopper_rim],
    [yB_tray1,  trayB_rim      - boss_clip_drop],
    [0,         pickplane_front - boss_clip_drop]
];

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
        translate([cx - label_w / 2, -label_cut_over, label_z_center - label_h / 2])
            cube([label_w, label_cut_over + label_z, label_h]);
        translate([cx - label_w / 2, yA_tray1 - label_cut_over,
                   label_b_center - label_h / 2])
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
}

// ------------------------------------------------------------
module body_geometry() {
    difference() {
        union() { body_shell(); outlet_chamfers(); vault_roof(); rail_male(); rail_bosses(); }
        fill_seat_cut();
        front_scallop_cut();
        rail_socket_cut();
        label_cuts();
        foot_pad_cuts();
        corner_cuts();
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
