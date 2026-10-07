// ============================================================
// calibration_coupon.scad -- SUPERSEDED BY D59; the future clip will get its own coupon.
//
// D59 (revision 15) postponed joining: the body has plain dovetail slots on both side
// faces and no male rail, so this coupon no longer gates the body print. Five coupons
// (D47, D51, D55, D56, D58) failed to give a usable fit on a 3.6 / 6.0 x 3 mm rail. It is
// kept as the record of what was tried; do not print it for the body. The text below is
// the historical header (written before D59, "PRINT THIS FIRST" no longer applies).
//
// Not part of the assembly; deliberately outside parts/ so the
// validation bundle does not treat it as a component.
//
// One fit in this design depends on how your printer and
// filament come out rather than on the geometry: the joining
// rail in its groove. History: test print 1's coupon (brim fused
// into the walls) read 0.50; test print 2 found the block loose
// down to 0.30; test print 3 (PETG) found 0.20 slightly tight
// (D47: 0.215); the D43 slim rail's coupon (0.265 .. 0.165) read
// too tight (D51: 0.40); the D51 coupon (0.50 .. 0.30) read loose
// on every stub; the D55 coupon (0.30 .. 0.26) read loose on every
// stub. THE SLIM-RAIL READINGS (the D47 coupon, the D51 coupon and the
// D55 coupon) ARE VOID: the groove block stood 0.4 mm (at pitch 18, groove bottom on the
// tip) or 0.0 mm (mouth on the root) from the neighbouring stub, so
// the block rocked against it, and the hand felt the neighbour as
// well as the fit. D56 spaces the stubs 30 mm apart (the block
// seated against its wall is >= 9 mm from every other stub, wall and label), sets
// rail_clear 0.30 (the loosest stub of the D55 coupon: a
// starting point, not a reading), and adds a
// second row for a different way to close the gap: crush ribs. D58
// adds the backstop wall behind each stub and makes the ribs triangular.
//
//   Print with NO brim (a brim's first layers squeeze the block's
//   groove and read tighter than it is). Three separate objects:
//   PLAIN plate, RIBS plate, the groove block (`PART` = plain, ribs,
//   block; `all` lays them out for preview).
//
//   HOW TO READ IT. Turn the block over so the face that was on the
//   bed is UP (the groove mouth has a 0.5 mm elephant's-foot relief
//   there; enter from the other face). Push the block DOWN onto the
//   stub, holding its open face (the groove's mouth) against the wall
//   behind the stub: that wall is the neighbouring module's face in
//   the body, and it leaves the rail tip 0.4 mm off the groove floor,
//   as the body does. Do not slide it along the wall; drop it.
//
//   PLAIN row (the primary reading): five stubs whose flank gap to the
//     groove is 0.30, 0.25, 0.20, 0.15, 0.10 mm per side (labels in
//     hundredths: 30 25 20 15 10). The fit is the stub that goes on by
//     hand WITHOUT ROCKING. Set rail_clear to that clearance. The
//     labels are Y gaps; the gap normal to the flank is 0.928 times
//     the label. Since D57 the groove is the male's section offset
//     outward with the same flank slope (rail_profile.scad), so the gap
//     is the label at every depth.
//
//   RIBS row (a second opinion): five stubs with a vertical TRIANGULAR
//     rib, 0.8 mm proud with a 0.2 mm crest, twice on each sloped flank
//     (0.9 and 2.1 mm from the root), tapering away over the top
//     1.5 mm so the block starts. The stubs are slimmer than the plain
//     ones; the crests press on the groove flank by 0, 0.1, 0.2, 0.3,
//     0.4 mm (labels 0 10 20 30 40). The fit is the LEAST interference
//     that has no rattle and still goes on and off by hand. Ribs crush
//     and wear on a joint that is separated and rejoined, so a reading
//     here says what a first fit feels like, not what the tenth does:
//     the plain row is the primary reading. Report both rows.
//
// The fill lid's snap test is gone with the snap tabs (D30): the
// lid rests in its recess by gravity (fit_section.scad checks it).
//
// EXPECTED_BODIES: 3 (PLAIN plate with its five stubs, RIBS plate with
//                     its five ribbed stubs, groove block)
// probes/coupon_fit.py seats the block on every stub in the mesh and
// asserts the spacing, the labels and the interference.
// ============================================================

include <params.scad>
include <rail_profile.scad>

PART      = "all";      // "plain" | "ribs" | "block" | "all" (preview layout)

plate_t   = 4.0;
stub_h    = 12.0;       // above the plate
stub_lead = 0.6;        // 45 degree chamfer round the stub's top edge
wall_t    = 3.0;        // D58: the backstop wall at each stub's root plane (the neighbouring module's face in the body)
wall_w    = 24.0;       //   wider in y than the 16 mm block
wall_h    = 14.0;       //   and taller than the stub
blk_w     = 18.0;       // groove block x
blk_d     = 16.0;       // groove block y
blk_h     = 18.0;
pitch     = 30.0;       // the block (seated against the wall) clears the previous stub's wall by pitch - 21 = 9
x_first   = 25.0;       // first stub's tip x; its block reaches 15 behind it (root - 18)
stub_y    = 32.0;
plate_d   = 60.0;
label_y   = 9.0;
row_y     = 54.0;
label_d   = 0.6;
gap       = 10.0;

plain_clear = [0.30, 0.25, 0.20, 0.15, 0.10];   // per side against the groove, y gap (0.928 x that normal to the flank)
rib_x       = [0.00, 0.10, 0.20, 0.30, 0.40];   // D58: nominal interference of the rib crest against the groove flank
rib_h       = 0.8;                              // every rib stands 0.8 proud (normal to the flank) of its stub
rib_d       = [0.9, 2.1];                       // rib positions along the flank, as depth from the stub root
rib_taper   = 1.5;                              // ribs gone over the top 1.5 mm
plate_w     = x_first + 4 * pitch + rail_out + wall_t + 10;

assert(pitch >= blk_w + wall_t + 8, "pitch leaves under 8 mm between the seated block and the previous stub's wall");

module label(s, size = 4) {
    linear_extrude(label_d + 0.1) text(s, size = size, halign = "center", valign = "center", font = "Liberation Sans:style=Bold");
}
function hundredths(v) = str(round(v * 100));
function two_dp(v) = let(h = round(v * 100)) str(floor(h / 100), ".", floor((h % 100) / 10), h % 10);

// The body's male rail section, offset per side by off = rail_clear - clearance (y gap to the groove flank)
module stub_section(off) {
    rail_trapezoid(rail_root_w + 2 * off, rail_tip_w + 2 * off, rail_out);
}

// Ribs. k_stub is the flank slope; (n_x, n_y) its outward normal on the +y flank (the -y flank is mirrored).
k_stub = (rail_tip_w - rail_root_w) / 2 / rail_out;
n_x    = k_stub / sqrt(1 + k_stub * k_stub);
n_y    = 1 / sqrt(1 + k_stub * k_stub);
function stub_hw(off, d) = rail_root_w / 2 + off + k_stub * d;
// the rib's section in the flank's own frame: t along the flank (toward the root), n out of it.
// Its base starts 0.2 INSIDE the stub, so its sides cross the flank plane instead of ending on it.
module rib_profile(sh = 0) {
    polygon([[-0.55, -0.2 - sh], [0.55, -0.2 - sh], [0.1, rib_h - sh], [-0.1, rib_h - sh]]);
}
module rib_frame(off, d) {
    multmatrix([[n_y, n_x, 0, -d], [-k_stub * n_y, n_y, 0, stub_hw(off, d)], [0, 0, 1, 0], [0, 0, 0, 1]])
        children();
}
module rib(off, d, sg) {
    z0 = plate_t - 0.5;
    za = plate_t + stub_h - rib_taper;
    zb = plate_t + stub_h - stub_lead;           // the chamfer starts here; the rib is gone inside it
    if (sg < 0) mirror([0, 1, 0]) rib_hull(off, d, z0, za, zb);
    else rib_hull(off, d, z0, za, zb);
}
module rib_hull(off, d, z0, za, zb) {
    hull() {
        translate([0, 0, z0]) linear_extrude(za - z0) rib_frame(off, d) rib_profile();
        translate([0, 0, zb - 0.01]) linear_extrude(0.01) rib_frame(off, d) rib_profile(rib_h + 0.3);
    }
}

module stub(off, ribbed = false) {
    z0 = plate_t - 0.5;
    zt = plate_t + stub_h;
    hull() {
        translate([0, 0, z0]) linear_extrude(zt - z0 - stub_lead) stub_section(off);
        translate([0, 0, zt - 0.01]) linear_extrude(0.01) offset(delta = -stub_lead) stub_section(off);
    }
    // the backstop wall at the root plane, and a tie from the stub into it
    translate([0, -wall_w / 2, z0]) cube([wall_t, wall_w, plate_t + wall_h - z0]);
    translate([-0.5, -(rail_root_w / 2 + off - 0.3), z0]) cube([2, rail_root_w + 2 * off - 0.6, zt - z0 - stub_lead - 0.2]);   // 0.3 inside the root's corners, so no edge lies on an edge
    if (ribbed)
        for (sg = [-1, 1], d = rib_d) rib(off, d, sg);
}

// A row plate: five stubs (tip to the left, root against its wall), labels cut into the top
module row_plate(row_label, labels, offs, ribbed) {
    difference() {
        cube([plate_w, plate_d, plate_t]);
        for (i = [0 : 4])
            translate([x_first + i * pitch + rail_out / 2, label_y, plate_t - label_d]) label(labels[i]);
        translate([4, row_y, plate_t - label_d])
            linear_extrude(label_d + 0.1) text(row_label, size = 4, halign = "left", valign = "center", font = "Liberation Sans:style=Bold");
        translate([plate_w - 4, row_y, plate_t - label_d])
            linear_extrude(label_d + 0.1) text(str("RAIL ", two_dp(rail_clear)), size = 4, halign = "right", valign = "center", font = "Liberation Sans:style=Bold");
    }
    for (i = [0 : 4])
        translate([x_first + i * pitch + rail_out, stub_y, 0])
            stub(offs[i], ribbed);
}
module plain_plate() {
    row_plate("PLAIN", [for (c = plain_clear) hundredths(c)], [for (c = plain_clear) rail_clear - c], false);
}
// the base clearance (y) that leaves the rib crest rib_x[i] into the groove flank: (rib_h - X) / n_y
function rib_base_clear(x) = (rib_h - x) / n_y;
module ribs_plate() {
    row_plate("RIBS", [for (x = rib_x) hundredths(x)], [for (x = rib_x) rail_clear - rib_base_clear(x)], true);
}

module groove_block() {
    // The body's groove: rail_out + rail_depth_clear deep, rail_clear per side,
    // open top AND bottom so it drops over a standing stub.
    difference() {
        cube([blk_w, blk_d, blk_h]);
        translate([blk_w, blk_d / 2, -1]) linear_extrude(height = blk_h + 2)
            rail_groove_2d();
        // elephant's-foot relief: the groove's outline grown 0.5 at the bed,
        // tapering to nothing 0.5 up -- a 45 degree chamfer round the mouth
        translate([blk_w, blk_d / 2, 0]) hull() {
            translate([0, 0, -1]) linear_extrude(height = 1.01)
                offset(delta = 0.5)
                    rail_groove_2d();
            linear_extrude(height = 0.5)
                rail_groove_2d();
        }
    }
}

if (PART == "plain") plain_plate();
else if (PART == "ribs") ribs_plate();
else if (PART == "block") groove_block();
else {
    plain_plate();
    translate([0, plate_d + gap, 0]) ribs_plate();
    translate([plate_w + gap, 0, 0]) groove_block();
}
echo(str("coupon: plain clearances ", plain_clear, ", rib interference ", rib_x, ", plate ", plate_w, " x ", plate_d));
