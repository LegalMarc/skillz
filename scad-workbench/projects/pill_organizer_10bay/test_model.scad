// ============================================================
// test_model.scad -- a scaled maquette of the whole module, for
// a quick bench print. Geometry is identical to the real part;
// only the scale changes, so proportions, the flush tray-A-rim /
// tray-B-floor line, the crossing chute and the two lid planes
// all read true.
//
// It is a FORM model, not a function model. At this scale a
// size-00 capsule does not fit any bay, and the fill lid's snap
// tabs come out around 0.5mm thick -- present, but token. Print
// it to judge the shape and the lid fit, not the flow.
//
// TEST_SCALE 0.42 puts the module at roughly 99 x 72 x 59 mm.
//
// Parts are emitted one at a time, in PRINT orientation, by the
// generated wrappers in build/. See README.md.
// ============================================================

include <params.scad>
use <parts/body.scad>
use <parts/pick_lid.scad>
use <parts/fill_lid.scad>

TEST_SCALE = 0.42;

// Print orientations, full size. Each is dropped onto z = 0 afterwards.
module print_body()     { body_geometry(); }
module print_pick_lid() { rotate([-pick_lid_slope, 0, 0]) pick_lid_geometry(); }
module print_fill_lid() { rotate([180, 0, 0]) fill_lid_geometry(); }
