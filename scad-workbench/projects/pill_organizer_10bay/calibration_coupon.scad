// ============================================================
// calibration_coupon.scad -- PRINT THIS FIRST.
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
// well as the fit. D56 spaces the stubs 28 mm apart (the block
// seated on any stub is >= 10 mm from every other), sets
// rail_clear 0.30 (the loosest stub of the D55 coupon: a
// starting point, not a reading), and adds a
// second row for a different way to close the gap: crush ribs.
//
//   Print with NO brim (a brim's first layers squeeze the block's
//   groove and read tighter than it is). Three separate objects:
//   PLAIN plate, RIBS plate, the groove block (`PART` = plain, ribs,
//   block; `all` lays them out for preview).
//
//   HOW TO READ IT. Turn the block over so the face that was on the
//   bed is UP (the groove mouth has a 0.5 mm elephant's-foot relief
//   there; enter from the other face) and drop it over each stub, the
//   groove opening toward the stub's root.
//
//   PLAIN row: five stubs at clearance 0.30, 0.25, 0.20, 0.15, 0.10
//     mm per side against the block's groove (labels in hundredths:
//     30 25 20 15 10). The fit is the stub that slides on by hand
//     WITHOUT ROCKING. Set rail_clear to that clearance. (The groove
//     flank is less steep than the male's, so its tip corner has
//     0.14 mm less room than its mouth: below about 0.15 the tip
//     corner binds on the mesh, exactly as it would on the body.)
//
//   RIBS row: five stubs with the plain profile at 0.30 clearance and
//     two vertical half-round ribs (radius 0.5) on each sloped flank,
//     tapering away over the top 1.5 mm so the block starts. The
//     ribs press on the groove flank by 0.00, 0.05, 0.10, 0.15,
//     0.20 mm (labels 0 5 10 15 20): a printed, deliberately
//     squashed interference. The fit is the LEAST interference that
//     has no rattle and still slides on and off by hand. Ribs make a
//     loose rail snug; they do not make a loose rail tight, so
//     report both rows.
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

PART      = "all";      // "plain" | "ribs" | "block" | "all" (preview layout)

plate_t   = 4.0;
stub_h    = 12.0;       // above the plate
stub_lead = 0.6;        // 45 degree chamfer round the stub's top edge
pitch     = 28.0;       // D56: block footprint 18 + 10
blk_w     = 18.0;       // groove block x
blk_d     = 16.0;       // groove block y
blk_h     = 18.0;
x_first   = 25.0;       // first stub's tip x: block (groove bottom on the tip) reaches 14.6 behind it
stub_y    = 30.0;
plate_d   = 54.0;
label_y   = 9.0;
row_y     = 46.0;
label_d   = 0.6;
gap       = 10.0;

plain_clear = [0.30, 0.25, 0.20, 0.15, 0.10];   // per side against the groove (at its mouth)
rib_x       = [0.00, 0.05, 0.10, 0.15, 0.20];   // interference against the groove flank
rib_clear   = 0.30;                             // the ribbed stubs' own flank clearance
rib_r       = 0.5;                              // half-round rib radius
rib_d       = [0.9, 2.1];                       // rib positions along the flank, as depth from the stub root
rib_taper   = 1.5;                              // ribs gone over the top 1.5 mm
groove_d    = rail_out + rail_depth_clear;      // 3.4
plate_w     = x_first + 4 * pitch + groove_d + (x_first - (blk_w - groove_d));   // equal margin both ends

assert(pitch >= blk_w + 10, "pitch leaves under 10 mm between the seated block and a neighbouring stub (D56)");
assert(abs(rail_clear - rib_clear) < 1e-9, "the ribbed row's stubs are the plain profile at the block's own clearance");

module label(s, size = 4) {
    linear_extrude(label_d + 0.1) text(s, size = size, halign = "center", valign = "center", font = "Liberation Sans:style=Bold");
}
function hundredths(v) = str(round(v * 100));
function two_dp(v) = let(h = round(v * 100)) str(floor(h / 100), ".", floor((h % 100) / 10), h % 10);

module rail_trapezoid(root_w, tip_w, depth, clear = 0) {
    polygon([[ 0,     -(root_w / 2 + clear)],
             [ 0,      (root_w / 2 + clear)],
             [-depth,  (tip_w  / 2 + clear)],
             [-depth, -(tip_w  / 2 + clear)]]);
}

// The body's male rail section, offset per side by off = rail_clear - clearance
module stub_section(off) {
    rail_trapezoid(rail_root_w + 2 * off, rail_tip_w + 2 * off, rail_out);
}

// geometry of one rib: its centre (x, y) for the +y flank, mirrored for the -y flank. The rib
// peak stands X beyond the groove's flank, measured along the stub flank's normal, at its own position,
// so the interference is the same on both ribs although the groove's flank is not parallel to the stub's.
k_stub = (rail_tip_w - rail_root_w) / 2 / rail_out;
k_grv  = (rail_tip_w - rail_root_w) / 2 / groove_d;
n_x    = k_stub / sqrt(1 + k_stub * k_stub);
n_y    = 1 / sqrt(1 + k_stub * k_stub);
function stub_hw(off, d)  = rail_root_w / 2 + off + k_stub * d;
function reach(off, d)    = (rail_root_w / 2 + rail_clear + k_grv * d - stub_hw(off, d)) / (n_y + k_grv * n_x);
function rib_centre(off, d, X, out = 0) =
    let(p = reach(off, d) + X, c = (out == 0 ? p - rib_r : -(rib_r + 0.1)))
    [-d + c * n_x, stub_hw(off, d) + c * n_y];

module rib(off, d, X, sg) {
    z0 = plate_t - 0.5;
    za = plate_t + stub_h - rib_taper;
    zb = plate_t + stub_h - stub_lead;           // the chamfer starts here; the rib is gone inside it
    ca = rib_centre(off, d, X);
    cb = rib_centre(off, d, X, 1);
    assert(reach(off, d) + X <= rib_r, "rib is taller than a half-round");
    hull() {
        translate([ca[0], sg * ca[1], z0]) linear_extrude(za - z0) circle(r = rib_r, $fn = 48);
        translate([cb[0], sg * cb[1], zb - 0.01]) linear_extrude(0.01) circle(r = rib_r, $fn = 48);
    }
}

module stub(off, X = -1) {
    z0 = plate_t - 0.5;
    zt = plate_t + stub_h;
    hull() {
        translate([0, 0, z0]) linear_extrude(zt - z0 - stub_lead) stub_section(off);
        translate([0, 0, zt - 0.01]) linear_extrude(0.01) offset(delta = -stub_lead) stub_section(off);
    }
    if (X >= 0)
        for (sg = [-1, 1], d = rib_d) rib(off, d, X, sg);
}

// A row plate: five stubs, tip to root along -x..+x with the root at the right, labels cut into the top
module row_plate(row_label, labels, offs, ribs) {
    difference() {
        cube([plate_w, plate_d, plate_t]);
        for (i = [0 : 4])
            translate([x_first + i * pitch + rail_out / 2, label_y, plate_t - label_d]) label(labels[i]);
        translate([4, row_y, plate_t - label_d]) {
            linear_extrude(label_d + 0.1) text(row_label, size = 4, halign = "left", valign = "center", font = "Liberation Sans:style=Bold");
        }
        translate([plate_w - 4, row_y, plate_t - label_d])
            linear_extrude(label_d + 0.1) text(str("RAIL ", two_dp(rail_clear)), size = 4, halign = "right", valign = "center", font = "Liberation Sans:style=Bold");
    }
    for (i = [0 : 4])
        translate([x_first + i * pitch + rail_out, stub_y, 0])
            stub(offs[i], ribs ? rib_x[i] : -1);
}
module plain_plate() {
    row_plate("PLAIN", [for (c = plain_clear) hundredths(c)], [for (c = plain_clear) rail_clear - c], false);
}
module ribs_plate() {
    row_plate("RIBS", [for (x = rib_x) hundredths(x)], [for (x = rib_x) rail_clear - rib_clear], true);
}

module groove_block() {
    // The body's groove: rail_out + rail_depth_clear deep, rail_clear per side,
    // open top AND bottom so it drops over a standing stub.
    difference() {
        cube([blk_w, blk_d, blk_h]);
        translate([blk_w, blk_d / 2, -1]) linear_extrude(height = blk_h + 2)
            rail_trapezoid(rail_root_w, rail_tip_w, rail_out + rail_depth_clear, rail_clear);
        // elephant's-foot relief: the groove's outline grown 0.5 at the bed,
        // tapering to nothing 0.5 up -- a 45 degree chamfer round the mouth
        translate([blk_w, blk_d / 2, 0]) hull() {
            translate([0, 0, -1]) linear_extrude(height = 1.01)
                offset(delta = 0.5)
                    rail_trapezoid(rail_root_w, rail_tip_w, rail_out + rail_depth_clear, rail_clear);
            linear_extrude(height = 0.5)
                rail_trapezoid(rail_root_w, rail_tip_w, rail_out + rail_depth_clear, rail_clear);
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
