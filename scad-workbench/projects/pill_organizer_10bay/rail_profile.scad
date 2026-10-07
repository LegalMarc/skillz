// ============================================================
// rail_profile.scad -- the joining rail's two 2D sections, in ONE place (D57).
//
// Included by parts/body.scad (the male rail and both grooves) and by
// calibration_coupon.scad (the stubs and the groove block), so the body and the
// coupon cannot disagree about the groove again. Needs params.scad (section 9).
//
// Section frame: x = 0 at the wall face (the root), x < 0 into the rail, y across it.
// The male rail is the trapezoid root_w -> tip_w over rail_out.
//
// The GROOVE is that same trapezoid offset outward by `clear` (rail_clear) on both
// flanks in y, with the SAME flank slope, so the flank gap is `clear` at every depth
// (D57). Until D56 the groove was a trapezoid between the same two widths over
// rail_out + rail_depth_clear, a gentler slope: the gap fell from rail_clear at the
// mouth to rail_clear - 0.141 at the rail tip (INCIDENTS.md, 2026-10-06).
// Past the rail tip the groove's walls run straight on (width tip_w + 2 clear) for
// rail_depth_clear, so the floor sits clear of the rail tip without the groove widening
// beyond the width the buttress and skin asserts (rail_boss_side, rail1_groove_y1) already
// use. In XY only, extruded along Z: nothing overhangs.
// ============================================================

module rail_trapezoid(root_w, tip_w, depth, clear = 0) {
    polygon([[ 0,     -(root_w / 2 + clear)],
             [ 0,      (root_w / 2 + clear)],
             [-depth,  (tip_w  / 2 + clear)],
             [-depth, -(tip_w  / 2 + clear)]]);
}

// the male rail's section
module rail_male_2d() {
    rail_trapezoid(rail_root_w, rail_tip_w, rail_out);
}

// the groove's section: the male's, grown by `clear` per side, floor rail_depth_clear past the tip
module rail_groove_2d(clear = rail_clear) {
    polygon([[ 0,                                -(rail_root_w / 2 + clear)],
             [ 0,                                 (rail_root_w / 2 + clear)],
             [-rail_out,                          (rail_tip_w  / 2 + clear)],
             [-(rail_out + rail_depth_clear),     (rail_tip_w  / 2 + clear)],
             [-(rail_out + rail_depth_clear),    -(rail_tip_w  / 2 + clear)],
             [-rail_out,                         -(rail_tip_w  / 2 + clear)]]);
}
