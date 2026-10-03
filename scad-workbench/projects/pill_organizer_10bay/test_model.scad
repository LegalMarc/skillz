// ============================================================
// test_model.scad -- the bench maquette: the whole module at
// TEST_SCALE, one part at a time in PRINT orientation. Geometry
// is identical to the real part; only the scale changes, so
// proportions, the crossing chute and both lid planes all read
// true.
//
// It is a FORM model, not a function model. At this scale a
// size-00 capsule does not fit any bay, and every clearance and
// wall shrinks with it (the fill lid's 0.30 becomes 0.13). Print
// it to judge the shape, not the fit or the flow -- for those,
// fit_section.scad prints a full-size end bay.
//
// TEST_SCALE 0.42 puts the module at roughly 99 x 72 x 59 mm.
//
//   scad -D 'PART="body"' -o build/maquette/body.stl test_model.scad
//
// The orientation and the drop to z = 0 live in print_export.scad;
// this file only sets the scale.
// ============================================================
TEST_SCALE = 0.42;
include <print_export.scad>
