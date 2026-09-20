// ============================================================
// params.scad -- every dimension for pill_organizer_10bay.
// Units mm, angles degrees. Nothing in parts/ may be a bare
// number unless it is purely cosmetic and local to one part.
//
// Derivations and sources: calculations.md
// Architecture decision and options: plan.md
// ============================================================

$fa = 2;
$fs = 0.4;

// No-op marker read by check_param_context.py (§2). Declaring a param's
// hardware-fit context here obliges the consuming file to assert it.
module use_param(name, context, constraint) {}

// ------------------------------------------------------------
// 0. Printer envelope
// ------------------------------------------------------------
bed_x = 256; bed_y = 256; bed_z = 256;
bed_margin = 13;            // skirt/brim + exclusion zones (D3, INCIDENTS 2026-08-21)
max_part_x = bed_x - bed_margin;
max_part_y = bed_y - bed_margin;
max_part_z = bed_z - bed_margin;

// ------------------------------------------------------------
// 1. Contents -- the design pill envelope (D2)
// ------------------------------------------------------------
pill_len = 26.0;            // longest dimension of the largest pill
pill_dia = 11.0;            // largest cross-section of the largest pill

// ------------------------------------------------------------
// 2. Walls and shell
// ------------------------------------------------------------
wall_out  = 2.8;            // outer shell wall
wall_div  = 2.4;            // bay divider and hopper front wall
base_t    = 3.0;            // base plate under tier A
lid_t     = 3.0;            // plate thickness, both lid parts

// weld_embed is how far every added feature reaches INTO the solid it lands on.
// A feature that merely touches on a coincident face is not reliably welded by
// the union: the tier B hinge bar came out as a separate floating body that way,
// and check_connectivity.py caught it (INCIDENTS.md 2026-08-26, same class).
weld_embed = 1.5;

// ------------------------------------------------------------
// 3. Bay grid
// ------------------------------------------------------------
bays        = 5;
module_w    = 230.0;
inner_w     = module_w - 2 * wall_out;
bay_w       = (inner_w - (bays - 1) * wall_div) / bays;
bay_pitch   = bay_w + wall_div;
function bay_center_x(i) = wall_out + bay_w / 2 + i * bay_pitch;

assert(module_w <= max_part_x,
       "module_w exceeds the usable bed width");
assert(bay_w >= pill_len * 1.5,
       "bay_w is under 1.5x pill_len -- a pill cannot lie freely across the bay");

// ------------------------------------------------------------
// 4. Tier section, in Y (front to back). Tier A is the datum;
//    tier B is the same section raised by tier_lift.
// ------------------------------------------------------------
pocket_d  = 36.0;           // pick tray depth in Y
pocket_h  = 37.0;           // pick tray interior height, floor to rim
outlet_h  = 30.0;           // gap under the hopper front wall

// The pick lid opens backwards until its front edge meets the hopper's front
// wall. For the lid to STAY open, that stop must fall past the angle at which
// its mass centre crosses over the pivot -- and with the wall only
// (yA_pocket1 - hinge_rod_y) behind the pivot, the two land within a couple of
// degrees of each other. Measured: stop 102.9 deg, over centre 106.2 deg, so
// the lid fell shut. Moving the lid cannot fix it (shortening it moves its own
// mass centre by the same token), so the WALL moves instead: above the height
// the lid's edge sweeps to, the hopper's front wall steps back by two wall
// thicknesses, which buys swing without touching the lid at all.
lid_stop_z   = 60.0;              // height of the step in the hopper front wall
wall_step    = 2 * wall_div;      // 4.8, how far it steps back
wall_step_rise = 1.2 * wall_step; // 50.2 deg chamfer: printable, and pills slide off it
ramp_deg  = 48;             // ramp angle from horizontal (D4)
hopper_run = 72.0;          // ramp run in Y, from the hopper front wall to the back wall

// Tier A Y stations
yA_pocket0  = wall_out;                          //   2.8  pocket A front face
yA_pocket1  = yA_pocket0 + pocket_d;             //  38.8  pocket A back face = ramp A foot
yA_hop0     = yA_pocket1 + wall_div;             //  41.2  hopper A mouth, front
yA_hop1     = yA_hop0 + hopper_run;              // 113.2  hopper A mouth, back
hop_mouth_y0 = yA_hop0 + wall_step;              //  46.0  mouth front, above the step
hop_mouth_d  = yA_hop1 - hop_mouth_y0;           //  67.2  mouth depth at the rim
yA_back     = yA_hop1 + wall_out;                // 116.0  tier A back face = pocket B front face

// Tier B Y stations -- the same section, shifted back by tier_pitch
tier_pitch  = yA_back - 0.0;                     // 116.0
yB_pocket0  = yA_pocket0 + tier_pitch;           // 118.8 -- see note below
module_d    = yA_back + pocket_d + wall_div + hopper_run + wall_out;

// The tier B section reuses pocket_d / wall_div / hopper_run directly rather
// than tier_pitch, because tier A's front wall is wall_out and tier B's is the
// shared wall at yA_hop1..yA_back. Explicit stations:
yB_pocket1  = yA_back + pocket_d;                // 152.0  pocket B back face = ramp B foot
yB_hop0     = yB_pocket1 + wall_div;             // 154.4  hopper B mouth, front
yB_hop1     = yB_hop0 + hopper_run;              // 226.4  hopper B mouth, back
yB_back     = yB_hop1 + wall_out;                // 229.2  module back face

assert(yB_back <= max_part_y,
       "module depth exceeds the usable bed depth");
assert(outlet_h > pill_len,
       "outlet_h is not larger than pill_len -- the largest pill cannot pass in every orientation");
assert(outlet_h >= 2 * pill_dia,
       "outlet_h is under 2x pill_dia -- below the slot rule for non-cohesive solids");

// ------------------------------------------------------------
// 5. Heights
// ------------------------------------------------------------
ramp_tan       = tan(ramp_deg);
ramp_rise      = hopper_run * ramp_tan;               // 82.629 over the mouth span
ramp_foot_z    = base_t;                              // ramp A foot, at the pocket lip
ramp_top_z     = ramp_foot_z + wall_div * ramp_tan + ramp_rise;  // 85.629 at yA_hop1
hopper_free    = 18.371;                              // freeboard above the ramp top, for pouring
hopper_a_rim   = ramp_top_z + hopper_free;            // 104.0
tier_lift      = hopper_a_rim - base_t;               // 101.0
pocketA_rim_z  = base_t + pocket_h;                   // 40.0
outletA_top_z  = base_t + outlet_h;                   // 33.0
// Tier B is tier A's section raised by tier_lift, so its rim is its own
// floor (= hopper_a_rim) plus the identical ramp climb plus the identical freeboard.
hopper_b_rim   = hopper_a_rim + (ramp_top_z - base_t) + hopper_free;   // 205.0
module_h       = hopper_b_rim;

assert(module_h <= max_part_z,
       "module height exceeds the usable bed height");
assert(hopper_a_rim > ramp_top_z,
       "hopper A rim is below its own ramp top -- the ramp would poke out of the mouth");
assert(pocketA_rim_z > outletA_top_z + pill_dia * 0.5,
       "the pick-tray rim is not clear enough above the outlet top -- pills could ride out over the lid line");

// ------------------------------------------------------------
// 6. Capacity (reported, and asserted against the stated brief)
// ------------------------------------------------------------
hopper_section_area = hopper_run * hopper_a_rim
                    - hopper_run * ((ramp_foot_z + wall_div * ramp_tan) + ramp_top_z) / 2;
hopper_vol_ml  = hopper_section_area * bay_w / 1000;
pocket_vol_ml  = pocket_d * pocket_h * bay_w / 1000;
bay_vol_ml     = hopper_vol_ml + pocket_vol_ml;

capsule_00_ml       = 0.95;    // size-00 capsule fill volume
loose_packing_frac  = 0.58;    // PATIKRINTI -- estimated, see calculations.md
charge_days         = 90;
charge_ml           = charge_days * capsule_00_ml / loose_packing_frac;

// This closed form ignores the wall step and the seat lips. Measured against
// the rendered cavity mesh it reads 237.7 mL against an actual 234.7 mL, i.e.
// 1.3% optimistic -- close enough to gate on, and the real figure is the one
// quoted in calculations.md and the README.
bay_vol_measured_ml = 234.7;

assert(bay_vol_ml > charge_ml,
       "a bay no longer holds the stated 90-day size-00 charge");
assert(abs(bay_vol_ml - bay_vol_measured_ml) / bay_vol_measured_ml < 0.05,
       "the closed-form capacity has drifted over 5% from the measured cavity -- re-measure and update bay_vol_measured_ml");

// ------------------------------------------------------------
// 7. Pick-lid hinge
// ------------------------------------------------------------
hinge_rod_d     = 6.0;
hinge_clip_wall = 1.7;
hinge_clearance = 0.15;                                   // radial, uncalibrated (tier 2)
hinge_bore_d    = hinge_rod_d + 2 * hinge_clearance;      // 6.3
hinge_clip_or   = hinge_bore_d / 2 + hinge_clip_wall;     // 4.95
hinge_snap_gap  = 5.6;                                    // C opening, must be < rod d to retain
hinge_clip_w    = 11.0;                                   // clip width along X
hinge_web_w     = 6.0;                                    // rod support web width along X
hinge_rod_z     = pocketA_rim_z + 7.0;                    // 47.00
hinge_rod_y     = yA_pocket1 - hinge_clip_or - hinge_clearance;   // 33.70

use_param("hinge_rod_d", "body_rod",        "rod carried by the hopper front wall");
use_param("hinge_rod_d", "pick_lid_c_clip", "clip bore must clear the rod and still retain it");

// The clip is anchored to the lid only on its lower-back quadrant, so each lip
// is a long arc, not a stub. That is what makes the snap survivable: peak
// bending strain is 3*t*d/(2*L^2), and a short stiff lip at this deflection
// would be near 10% -- far past what PLA tolerates.
hinge_clip_defl   = (hinge_rod_d - hinge_snap_gap) / 2;
hinge_clip_arc    = 3.14159 * (hinge_bore_d / 2 + hinge_clip_wall / 2) / 2;   // the SHORT lip
hinge_clip_strain = 3 * hinge_clip_wall * hinge_clip_defl / (2 * pow(hinge_clip_arc, 2));

assert(hinge_snap_gap < hinge_rod_d,
       "the C-clip mouth is not narrower than the rod -- the lid would not be retained");
assert(hinge_clip_strain < 0.015,
       "C-clip lip strain over 1.5% -- widen the mouth or lengthen the lip, do not just hope");
assert(hinge_rod_y + hinge_clip_or + hinge_clearance <= yA_pocket1,
       "the C-clip outer radius fouls the hopper front wall -- the lid cannot reach its 95 deg rest");
assert(hinge_rod_z - hinge_clip_or > pocketA_rim_z - lid_t,
       "the hinge rod sits too low -- the clip would foul the pick-tray rim");

pick_lid_len = yA_pocket1;                    // 38.8, front face to hopper wall face
pick_lid_w   = module_w - 1.0;                // 229.0, 0.5 clearance each side when ganged
pick_lid_plate_y1 = hinge_rod_y + hinge_clip_or;   // 38.65, rear edge of the plate
// A front grab lip that OVERHANGS forward rather than hanging down. A skirt
// dropping below the plate would leave the plate floating 4mm off the bed with
// only the skirt touching -- the lid has to print plate-down, clips up.
pick_lid_overhang = 5.0;
// Chamfer on the lid's front TOP edge, so the corner that reaches the hopper
// wall first is the front BOTTOM one. The top corner is nearer the pivot
// plane, so it hits sooner and stops the lid short; taking it off buys several
// degrees of swing at no cost.
pick_lid_front_cham = 3.0;
// The lid hangs from the rod, and the bore has hinge_clearance of radial slop,
// so its closed position is not fixed by the tray rim. Model it floating this
// far above the rim: it is what actually happens, and it keeps the lid/body
// pair a near miss rather than a declared contact -- a declared contact is
// exempted from the motion sweep, and the swing is the one thing here that
// most needs sweeping.
pick_lid_rest_gap = 0.3;
// Anything on the lid BEHIND the hinge axis swings DOWN as the lid opens, and
// the tray rim is right there. Measured by motion_sweep.py: the plate's square
// rear-bottom corner sat at radius 8.27 from the axis and fouled the rim at
// 3.8 deg. Everything below the axis and behind it is therefore cut back to
// this radius -- the pivot's own height above the rim, less a running margin.
pick_lid_swing_r  = (hinge_rod_z - pocketA_rim_z) - 0.2;   // 6.80

assert(pick_lid_swing_r < hinge_rod_z - pocketA_rim_z,
       "the lid's rear swing radius reaches past the tray rim -- it will foul on opening");
assert(pick_lid_swing_r > hinge_clip_or,
       "the swing relief would cut into the C-clip ring itself");
assert(pick_lid_rest_gap > hinge_clearance,
       "the modelled rest gap is smaller than the hinge's own radial slop -- the lid would bear on the rim instead of the rod");
pick_lid_web_clear = 0.6;                     // per side, around the body's hinge webs
// The body's hinge webs surround the pivot, so a rectangular notch that merely
// clears them at the closed position is not enough -- the plate corner beside
// it sweeps THROUGH the web further round. Measured: a tangential touch at
// 68 deg. The notch is therefore a cylinder about the hinge axis, sized to the
// web's own farthest corner, which no rotation can defeat.
pick_lid_web_span_y = (yA_pocket1 + weld_embed) - (hinge_rod_y - hinge_clip_or - 1.0);
pick_lid_web_r = sqrt(pow(yA_pocket1 + weld_embed - hinge_rod_y, 2)
                    + pow(hinge_rod_z - (pocketA_rim_z - weld_embed), 2))
                 + pick_lid_web_clear;        // 11.30

assert(pick_lid_web_r > hinge_clip_or,
       "the web relief is smaller than the clip ring -- it would not clear the web");
// Measured, not calculated: the lid's front edge meets the stepped hopper wall
// at 111.7 deg, and its mass centre crosses the pivot at 107.0 deg, so it
// rests open under its own weight with 4.7 deg to spare. Two hand calculations
// of the stop angle were both wrong before the boolean measurement settled it.
pick_lid_open_deg  = 111.7;
pick_lid_overcentre_deg = 107.0;

assert(pick_lid_open_deg > pick_lid_overcentre_deg + 2.0,
       "the pick lid's hard stop is not clear of its own over-centre angle -- it will fall shut");

assert(yA_pocket1 - pick_lid_plate_y1 < pill_dia,
       "the gap behind the pick lid is wider than a pill -- pills could escape over the tray rim");

// ------------------------------------------------------------
// 8. Fill lid (drops into the hopper mouth, flush with the rim,
//    retained by two cantilever snap tabs)
// ------------------------------------------------------------
// The lid does NOT rebate into the rim. An earlier version cut a 2.5mm seat
// into 2.4-2.8mm walls and left 0.3mm fins standing 3mm tall -- unprintable.
// Instead the four divider tops are cut down by one lid thickness across the
// mouth, and a ledge is added INWARD from the mouth walls to carry the edges.
fill_lid_clear  = 0.30;                       // per side, uncalibrated (tier 2)
fill_ledge_w    = 3.0;                        // inward projection of the seat ledge
fill_ledge_t    = 2.0;                        // ledge thickness
fill_seat_z     = hopper_a_rim - lid_t;       // 101.0, underside of the seated lid
// The lid's resting height is not actually fixed by the seat: the barb has
// 0.3mm of lift slop against its pocket ceiling, so the lid can sit anywhere
// in that band. It is modelled at mid-slop, which also keeps the pair a near
// miss rather than a coplanar resting contact -- FCL cannot define a
// penetration depth for two faces lying exactly on each other and reported
// 66.9mm for a pair whose real boolean overlap measures 0.000 mm3
// (INCIDENTS.md 2026-08-19, the declared-contact verdict's known blind spot).
fill_lid_seat_gap = 0.15;
fill_lid_x      = inner_w    - 2 * fill_lid_clear;   // 223.8
fill_lid_y      = hop_mouth_d - 2 * fill_lid_clear;  // 66.6
// Snap-tab cantilever. Length and thickness are set by the strain the barb
// deflection puts on the beam, not by looks: peak bending strain for a
// cantilever deflected d at its tip is 3*t*d / (2*L^2), and PLA is only good
// for a percent or two. A short stubby tab cannot make this engagement.
fill_tab_w      = 16.0;
fill_tab_t      = 1.5;
fill_tab_drop   = 13.0;                       // how far the tab hangs below the lid
// The barb must clear the lid's own side clearance before it engages anything,
// so real retention is (barb - clear), not barb.
fill_tab_barb   = 1.1;                        // barb protrusion into the wall pocket
fill_tab_engage = fill_tab_barb - fill_lid_clear;   // 0.8, what actually holds
fill_tab_ramp   = 3.0;                        // lead-in ramp, as a multiple of the barb
fill_tab_strain = 3 * fill_tab_t * (fill_tab_barb - fill_lid_clear) / (2 * pow(fill_tab_drop, 2));
fill_tab_pocket_h = 6.0;
fill_barb_top_z   = fill_seat_z - fill_tab_drop + 5.0;              // 90.0, barb's flat top
fill_barb_bot_z   = fill_barb_top_z - fill_tab_ramp * fill_tab_barb; // 87.6, foot of the lead-in ramp
fill_tab_pocket_z = fill_barb_top_z - fill_tab_pocket_h + 0.3;      // 84.3, pocket floor
// 0.3 is the lift slop between the barb's flat top and the pocket ceiling --
// enough for assembly tolerance, small enough that the lid does not rattle.

// The BACK tab hangs down at the deep end of the hopper, where the ramp has
// climbed nearly to the rim. Measured: at 16mm the tab tip was 0.7mm inside
// the ramp. The tab's length is therefore bounded from below by the strain it
// must survive and from above by the ramp it must not hit.
fill_tab_tip_z  = fill_seat_z - fill_tab_drop;
ramp_at_back    = base_t + (yA_hop1 - yA_pocket1) * ramp_tan;    // 85.63

assert(fill_tab_tip_z > ramp_at_back + 1.0,
       "the fill lid's back snap tab reaches below the ramp at the back of the hopper");
assert(fill_tab_strain < 0.015,
       "snap-tab bending strain over 1.5% -- lengthen the tab or thin it, do not just shrink the barb");
fill_grip_d     = 18.0;                       // fingernail relief notch in the front rim
// The seat cut oversteps the mouth slightly on all four sides. Two reasons:
// it must also take the top off the rail buttresses, which otherwise stand
// proud into the seat and hold the lid 3mm off it; and an exactly-coincident
// cut face against the existing mouth void produced zero-area triangles.
seat_cut_over   = 0.4;
// The lid seats on the four divider tops -- the strongest support, and the
// only one that carries it across the middle of its 71mm span. The front and
// back lips sit this far below that plane: they stop the lid tilting into a
// bay and close the edge gap, without fighting the dividers for the seat. It
// also means the lip top and the divider cut floor are not the same plane,
// which is what was generating zero-area triangles where they met.
seat_lip_drop   = 0.2;

assert(seat_lip_drop > 0 && seat_lip_drop < 0.5,
       "seat_lip_drop must be a small positive offset: 0 puts two boolean faces on one plane, large rocks the lid");

min_rim_w = 1.8;        // thinnest rim the seat cut may leave standing 3mm tall
assert(wall_out - seat_cut_over >= min_rim_w && wall_div - seat_cut_over >= min_rim_w,
       "the seat cut oversteps so far it leaves a rim thinner than min_rim_w");

assert(lid_stop_z > outletA_top_z + 10 && lid_stop_z + wall_step_rise < hopper_a_rim - 10,
       "the wall step sits too near the outlet or the rim to be a clean feature");
assert(wall_step_rise / wall_step > 1.0,
       "the wall step's chamfer is shallower than 45 deg and would overhang");
assert(fill_lid_x < inner_w && fill_lid_y < hop_mouth_d,
       "the fill lid is not smaller than the mouth it drops into");
assert(fill_tab_engage >= 0.6,
       "under 0.6mm of real barb engagement once the lid's own clearance is taken off");
assert(fill_ledge_w >= 2.5,
       "the fill-lid seat ledge is too narrow to carry the lid edge");
assert(fill_tab_barb < wall_div - 0.8,
       "the snap barb is too deep for the wall it latches into");
assert(fill_tab_pocket_z + fill_tab_pocket_h < fill_seat_z - fill_ledge_t,
       "the barb pocket runs up into the seat ledge");
assert(fill_barb_top_z < fill_tab_pocket_z + fill_tab_pocket_h
       && fill_barb_bot_z > fill_tab_pocket_z,
       "the barb does not land inside its own pocket");
assert(fill_seat_z - fill_tab_drop < fill_barb_bot_z,
       "the snap tab tip is above its own barb -- the barb would have nothing to sit on");
assert(fill_seat_z - fill_ledge_t > ramp_top_z,
       "the seat ledge hangs below the ramp top -- it would be in the pill path");

// ------------------------------------------------------------
// 9. Joining rails (D5) -- trapezoid by two explicit widths,
//    never by a flank angle. Extruded along Z: no overhang.
// ------------------------------------------------------------
rail_root_w = 7.0;          // width where the rail meets the module face
rail_tip_w  = 11.0;         // width at the outboard tip (undercut)
rail_out    = 5.0;          // protrusion from the face
rail_clear  = 0.35;         // per flank, uncalibrated (tier 2)
rail_depth_clear = 0.40;    // socket depth over rail protrusion

assert(rail_tip_w > rail_root_w && rail_root_w > 0,
       "rail trapezoid is degenerate -- tip must be wider than root (INCIDENTS 2026-08-30 bowtie)");
assert(rail_clear * 2 < rail_root_w / 2,
       "rail clearance has eaten the rail root");

rail_z0   = 12.0;           // both rails seat on the groove floor -> bottoms flush
rail_lead = 3.0;            // taper at the rail top, so it finds the groove
rail_boss = 5.0;            // inner buttress carrying the groove, both side walls

rail1_y   = (yA_hop0 + yA_hop1) / 2;          //  77.2, mid hopper A
rail1_z1  = 90.0;                              // male top
rail1_soc_z1 = hopper_a_rim + 1.0;             // 105.0 -- groove OPEN at the body top
rail2_y   = (yB_hop0 + yB_hop1) / 2;          // 190.4, mid hopper B
rail2_z1  = 180.0;
rail2_soc_z1 = hopper_b_rim + 1.0;             // 206.0

rail_sep  = rail2_y - rail1_y;                 // 113.2

// Each groove runs from its floor to the top of the side wall above it, so a
// neighbouring module is simply lowered alongside and both rails engage
// progressively -- no minimum lift, and the groove floor at rail_z0 is what
// registers the two modules flush at the bottom.
assert(rail1_soc_z1 > rail1_z1 && rail2_soc_z1 > rail2_z1,
       "a rail groove is shorter than its own male -- the modules could not be brought together");
assert(rail1_soc_z1 <= hopper_a_rim + 1.0 && rail2_soc_z1 <= hopper_b_rim + 1.0,
       "a rail groove runs past the side wall that is supposed to carry it");
assert(rail_boss + wall_out - rail_out - rail_depth_clear >= 1.5,
       "not enough material left behind the rail groove -- the buttress is too thin");
assert(bay_w - rail_boss >= pill_len,
       "the rail buttress narrows an end bay below one pill length");
assert(rail_sep > 100,
       "the two rails are too close together to resist yaw between ganged modules");

// ------------------------------------------------------------
// 10. Cosmetic / ergonomic
// ------------------------------------------------------------
label_w   = 32.0;
label_h   = 9.0;
label_z   = 0.6;            // recess depth
fillet_r  = 2.0;            // internal radius, tray floor to wall
foot_h    = 0.0;            // flat bottom; no feet (bed adhesion surface)

echo(str("bay_w = ", bay_w));
echo(str("module = ", module_w, " x ", yB_back, " x ", module_h));
echo(str("per-bay volume = ", bay_vol_ml, " mL (hopper ", hopper_vol_ml,
         " + tray ", pocket_vol_ml, "); 90-day size-00 charge = ", charge_ml, " mL"));
