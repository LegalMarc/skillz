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

module use_param(name, context, constraint) {}

// ------------------------------------------------------------
// 0. Printer envelope
// ------------------------------------------------------------
bed_x = 256; bed_y = 256; bed_z = 256;
bed_margin = 13;
max_part_x = bed_x - bed_margin;
max_part_y = bed_y - bed_margin;
max_part_z = bed_z - bed_margin;

// ------------------------------------------------------------
// 1. Contents -- the design pill envelope (D2)
// ------------------------------------------------------------
pill_len = 26.0;
pill_dia = 11.0;

// ------------------------------------------------------------
// 2. Walls and shell
// ------------------------------------------------------------
wall_out  = 2.8;
wall_div  = 2.4;
base_t    = 3.0;
lid_t     = 3.0;
weld_embed = 1.5;           // how far every added feature reaches INTO the
                            // solid it lands on; a coincident face is not
                            // reliably welded (INCIDENTS.md 2026-08-26)

// ------------------------------------------------------------
// 3. Bay grid
// ------------------------------------------------------------
bays        = 5;
module_w    = 230.0;
inner_w     = module_w - 2 * wall_out;
bay_w       = (inner_w - (bays - 1) * wall_div) / bays;
bay_pitch   = bay_w + wall_div;
function bay_center_x(i) = wall_out + bay_w / 2 + i * bay_pitch;

assert(module_w <= max_part_x, "module_w exceeds the usable bed width");
assert(bay_w >= pill_len * 1.5,
       "bay_w is under 1.5x pill_len -- a pill cannot lie freely across the bay");

// ------------------------------------------------------------
// 4. Section, in Y (front to back)  -- REVISION 3
//
//   [ tray A ][ tray B ][ hopper B mouth ][ hopper A mouth ]
//     front                                            back
//
// Both pick trays at the front under ONE lid, both fill mouths at the back
// under ONE lid. That grouping forces a crossing: hopper A is the BACK mouth
// but feeds the FRONT tray, so its chute ducks under tray B and hopper B.
//
// Revision 3 changes two things about that chute.
//
// (a) The ramp is 40 degrees, not 48. The chute floor is the top of hopper A's
//     floor, so a shallower ramp lowers hopper A -- and hopper B's floor rides
//     on the chute ceiling, so it comes down too. 48 degrees was only buying a
//     self-supporting chute ceiling, on an internal surface nobody sees.
//
// (b) Under tray B, and only there, the chute runs at 20 degrees instead of 40
//     -- the "porch". Because the 40 degree climb then starts 30mm further
//     back, everything behind it drops with it, and tray B's floor lands on
//     tray A's rim: one unbroken line across the front of the module.
//
// The porch is shallower than the angle of repose, so it carries a small
// stagnant wedge (calculations.md). That is the whole price of the change.
// ------------------------------------------------------------
tray_d      = 28.0;         // pick tray depth in Y, both rows
trayB_h     = 38.0;         // tray B interior height, floor to rim
outlet_h    = 30.0;         // gap under tray B's feed wall (row B's outlet)
ramp_deg    = 40;           // ramp and chute angle from horizontal (D11)
porch_deg   = 20;           // chute floor angle under tray B only (D12)
hopperB_run = 70.0;         // hopper B mouth depth in Y
hopperA_run = 32.0;         // hopper A mouth depth in Y
chute_clear = 36.0;         // clear height of the crossing chute, at the ridge
chute_ceil  = 3.0;          // floor thickness above the chute
hopper_free = 12.0;         // minimum freeboard above the highest ramp

ramp_tan  = tan(ramp_deg);
porch_tan = tan(porch_deg);

// Y stations
yA_tray0  = wall_out;                       //   2.8  tray A front face
yA_tray1  = yA_tray0 + tray_d;              //  30.8  tray A back face = chute A foot
yA_wall1  = yA_tray1 + wall_div;            //  33.2
yB_tray0  = yA_wall1;                       //  33.2  tray B front face
yB_tray1  = yB_tray0 + tray_d;              //  61.2  tray B back face = porch end
yB_wall1  = yB_tray1 + wall_div;            //  63.6  hopper B mouth, front
yB_hop1   = yB_wall1 + hopperB_run;         // 133.6  hopper B mouth, back
yA_hop0   = yB_hop1 + wall_div;             // 136.0  hopper A mouth, front
yA_hop1   = yA_hop0 + hopperA_run;          // 168.0  hopper A mouth, back
module_d  = yA_hop1 + wall_out;             // 170.8

porch_run = yB_tray1 - yA_tray1;            //  30.4

// Z stations
base_z  = base_t;                                        //   3.0  tray A floor
z_porch = base_z + porch_run * porch_tan;                //  14.06 chute floor at the porch end

// Chute A's floor: 20 degrees under tray B, then 40 degrees all the way back.
function chuteA_floor(y) = y <= yB_tray1
                         ? base_z  + (y - yA_tray1) * porch_tan
                         : z_porch + (y - yB_tray1) * ramp_tan;
// Its ceiling runs parallel, holding a constant section. Following a flat
// underside instead left 7197 mm^2 of bridged ceiling in revision 2
// (INCIDENTS.md 2026-09-20).
function chuteA_ceil(y) = chuteA_floor(y) + chute_clear;

// Tray B sits one slab above the chute ceiling at the porch's end -- which is
// the whole point of the porch, because that is where the ceiling is lowest.
trayB_floor = chuteA_ceil(yB_tray1) + chute_ceil;        //  53.06
trayB_rim   = trayB_floor + trayB_h;                     //  91.06
outletB_top = trayB_floor + outlet_h;                    //  83.06
function rampB(y) = trayB_floor + (y - yB_tray1) * ramp_tan;

// Tray A's rim lands exactly on tray B's floor: the line the whole revision
// is named for. Above it, the pick surface is ONE SLOPED PLANE up to tray B's
// rim -- a lid spanning two flat steps is a Z in section, and a Z cannot be
// printed without support whichever way it is laid.
trayA_rim       = trayB_floor;                           //  53.06
pickplane_front = trayA_rim;
function pickplane(y) = pickplane_front
                      + (y / yB_tray1) * (trayB_rim - pickplane_front);

// Row A's outlet is the chute's own section: at tray A the ridge stands
// chute_clear above the floor and the ceiling is already a chamfer.
outletA_top = base_z + chute_clear;                      //  39.0

hopper_rim = 141.0;
module_h   = hopper_rim;

assert(trayB_floor > chuteA_ceil(yB_tray1),
       "tray B's floor is not above the chute ceiling -- the two feeds intersect");
assert(rampB(yB_wall1) - chute_ceil > chuteA_ceil(yB_wall1) - 1e-6,
       "chute A does not clear hopper B's floor at the front of hopper B");
assert(rampB(yB_hop1) - chute_ceil > chuteA_ceil(yB_hop1) - 1e-6,
       "chute A does not clear hopper B's floor at the back of hopper B");
assert(rampB(yB_hop1) + hopper_free <= hopper_rim,
       "hopper B's ramp leaves less than hopper_free under the rim");
assert(chuteA_floor(yA_hop1) + hopper_free <= hopper_rim,
       "hopper A's floor leaves less than hopper_free under the rim");
assert(chute_clear > pill_len,
       "the crossing chute ridge is not taller than the longest pill");
assert(outlet_h > pill_len && outlet_h >= 2 * pill_dia,
       "outlet_h fails the pill-passage or slot rule");
assert(trayA_rim > outletA_top && trayB_rim > outletB_top,
       "a tray rim is at or below its own outlet top -- pills could ride out over the lid line");
trayB_front_retain = pickplane(yB_tray0) - trayB_floor;
assert(trayB_front_retain > pill_dia + 3,
       "the wall between the trays is cut too low by the pick plane -- tray B would spill into tray A");
assert(pickplane(0) < trayB_rim && pickplane(yB_tray1) > trayA_rim,
       "the pick plane does not rise from front to back");
assert(porch_deg < ramp_deg,
       "the porch is not shallower than the ramp -- it is doing nothing");
assert(module_d <= max_part_y && module_h <= max_part_z,
       "the module no longer fits the usable bed");

tray_step = trayB_rim - trayA_rim;                       //  38.0

// ------------------------------------------------------------
// 4a. Porch splitter rib (D13)
//
// Tray B's floor is carried on the bay dividers alone -- the chute runs
// underneath, so its front and back walls do not reach the floor. At 40
// degrees that underside self-supported. At 20 degrees it does not: it is a
// near-flat ceiling bridging the full bay width, which is the exact defect
// logged on 2026-09-20 and the one gate in the suite that never catches it.
//
// A single fin down the middle of the porch halves the bridge and carries the
// slab directly. Its upstream edge is knife-tapered so a pill arriving from
// the 40 degree chute is deflected into a lane rather than stopped by a step.
// ------------------------------------------------------------
rib_t     = 2.4;
rib_lead  = 12.0;           // length of the 45-degree upstream taper
rib_lane  = (bay_w - rib_t) / 2;                         //  20.28

assert(rib_lane > pill_dia * 1.5,
       "a porch lane is under 1.5x pill_dia -- pills would not run single file");
assert(rib_lane < 30.0,
       "the porch bridge is still too wide to print without support");

// ------------------------------------------------------------
// 5. Hopper mouths (both at the back, both at hopper_rim -> ONE flat lid)
// ------------------------------------------------------------
hop_mouth_y0 = yB_wall1;                                 //  63.6
hop_mouth_y1 = yA_hop1;                                  // 168.0
hop_mouth_d  = hop_mouth_y1 - hop_mouth_y0;              // 104.4

// ------------------------------------------------------------
// 6. Capacity
// ------------------------------------------------------------
capsule_00_ml       = 0.95;
loose_packing_frac  = 0.58;    // PATIKRINTI -- estimated, see calculations.md
charge_days         = 90;
charge_ml           = charge_days * capsule_00_ml / loose_packing_frac;
repose_deg          = 30;      // PATIKRINTI -- estimated, see calculations.md

bayA_vol_measured_ml = 0;
bayB_vol_measured_ml = 0;

// ------------------------------------------------------------
// 7. Pick lid -- ONE lid over BOTH tray rows, lift-off
// ------------------------------------------------------------
pick_lid_w     = module_w - 1.0;
pick_lid_clear = 0.35;
pick_lid_slope = atan((trayB_rim - pickplane_front) / yB_tray1);   // 31.8 deg
pick_lid_len   = sqrt(pow(yB_tray1, 2) + pow(trayB_rim - pickplane_front, 2))
                 - pick_lid_clear;
pick_lid_hook_t = 3.0;
pick_lid_hook_h = 7.0;
pick_lid_gap = 0.2;
pick_lid_tv  = lid_t / cos(pick_lid_slope);

assert(pick_lid_slope > 17.0,
       "the pick plane is shallow enough for friction to hold the lid, so the hook is over-designed");
assert(pick_lid_hook_h > 4.0,
       "the front hook is too shallow to retain the lid on its slope");
assert(pick_lid_hook_h < trayA_rim - outletA_top + 5.0,
       "the front hook hangs below row A's outlet top and would foul the chute mouth");

// ------------------------------------------------------------
// 8. Fill lid (drops into the hopper mouth, flush with the rim,
//    retained by two cantilever snap tabs)
// ------------------------------------------------------------
fill_lid_clear  = 0.30;
fill_ledge_w    = 3.0;
fill_ledge_t    = 2.0;
fill_seat_z     = hopper_rim - lid_t;         // 138.0
fill_lid_seat_gap = 0.15;                     // modelled at mid-slop; a coplanar
                                              // resting contact makes FCL report a
                                              // nonsense penetration depth
                                              // (INCIDENTS.md 2026-08-19)
fill_lid_x      = inner_w     - 2 * fill_lid_clear;
fill_lid_y      = hop_mouth_d - 2 * fill_lid_clear;
fill_tab_w      = 16.0;
fill_tab_t      = 1.2;
fill_tab_drop   = 10.0;
fill_tab_barb   = 1.1;
fill_tab_engage = fill_tab_barb - fill_lid_clear;
fill_tab_ramp   = 3.0;
fill_tab_strain = 3 * fill_tab_t * (fill_tab_barb - fill_lid_clear) / (2 * pow(fill_tab_drop, 2));
fill_tab_pocket_h = 6.0;
fill_barb_top_z   = fill_seat_z - fill_tab_drop + 5.0;
fill_barb_bot_z   = fill_barb_top_z - fill_tab_ramp * fill_tab_barb;
fill_tab_pocket_z = fill_barb_top_z - fill_tab_pocket_h + 0.3;
fill_tab_tip_z  = fill_seat_z - fill_tab_drop;
ramp_at_back    = max(rampB(yB_hop1), chuteA_floor(yA_hop1));

assert(fill_tab_tip_z > ramp_at_back + 1.0,
       "the fill lid's back snap tab reaches below the ramp at the back of the hopper");
assert(fill_tab_strain < 0.015,
       "snap-tab bending strain over 1.5% -- lengthen the tab or thin it");
fill_grip_d     = 18.0;
seat_cut_over   = 0.4;
seat_lip_drop   = 0.2;

assert(seat_lip_drop > 0 && seat_lip_drop < 0.5,
       "seat_lip_drop must be a small positive offset");
min_rim_w = 1.8;
assert(wall_out - seat_cut_over >= min_rim_w && wall_div - seat_cut_over >= min_rim_w,
       "the seat cut oversteps so far it leaves a rim thinner than min_rim_w");
assert(fill_lid_x < inner_w && fill_lid_y < hop_mouth_d,
       "the fill lid is not smaller than the mouth it drops into");
assert(fill_tab_engage >= 0.6,
       "under 0.6mm of real barb engagement once the lid's own clearance is taken off");
assert(fill_ledge_w >= 2.5, "the fill-lid seat ledge is too narrow to carry the lid edge");
assert(fill_tab_barb < wall_div - 0.8, "the snap barb is too deep for the wall it latches into");
assert(fill_tab_pocket_z + fill_tab_pocket_h < fill_seat_z - fill_ledge_t,
       "the barb pocket runs up into the seat ledge");
assert(fill_barb_top_z < fill_tab_pocket_z + fill_tab_pocket_h
       && fill_barb_bot_z > fill_tab_pocket_z,
       "the barb does not land inside its own pocket");
assert(fill_seat_z - fill_tab_drop < fill_barb_bot_z,
       "the snap tab tip is above its own barb");
assert(fill_seat_z - fill_ledge_t > rampB(yB_hop1)
       && fill_seat_z - fill_ledge_t > chuteA_floor(yA_hop1),
       "the seat ledge hangs below a hopper floor -- it would be in the pill path");

// ------------------------------------------------------------
// 9. Joining rails (D5)
// ------------------------------------------------------------
rail_root_w = 7.0;
rail_tip_w  = 11.0;
rail_out    = 5.0;
rail_clear  = 0.35;
rail_depth_clear = 0.40;

assert(rail_tip_w > rail_root_w && rail_root_w > 0,
       "rail trapezoid is degenerate -- tip must be wider than root");
assert(rail_clear * 2 < rail_root_w / 2, "rail clearance has eaten the rail root");

rail_z0   = 10.0;
rail_lead = 3.0;
rail_boss = 5.0;
rail_boss_w = rail_tip_w + 8;   // buttress footprint in Y

// Rail 1 sits under tray A, not under tray B. Under tray B it would stand in
// the porch and narrow one lane of an end bay below the single-file rule; tray
// A is a pick pocket, where a 5mm buttress in one corner costs nothing.
rail1_y      = (yA_tray0 + yA_tray1) / 2;                  //  16.8, mid tray A
rail1_soc_z1 = pickplane(rail1_y - rail_boss_w / 2);       //  57.6, the wall top
rail1_z1     = rail1_soc_z1 - 14.0;
rail2_y      = (yB_wall1 + yB_hop1) / 2;                   //  98.6, mid hopper B
rail2_soc_z1 = hopper_rim + 1.0;                           // 142.0
rail2_z1     = 112.0;

rail_sep  = rail2_y - rail1_y;                             //  81.8

assert(rail1_soc_z1 > rail1_z1 && rail2_soc_z1 > rail2_z1,
       "a rail groove is shorter than its own male");
assert(rail1_soc_z1 <= pickplane(rail1_y - rail_boss_w / 2) + 1e-6
       && rail2_soc_z1 <= hopper_rim + 1.0,
       "a rail groove runs past the side wall that is supposed to carry it");
assert(rail1_y + rail_boss_w / 2 < yA_tray1,
       "rail 1's buttress reaches back into the chute mouth");
assert(rail_boss + wall_out - rail_out - rail_depth_clear >= 1.5,
       "not enough material left behind the rail groove");
assert(bay_w - rail_boss >= pill_len,
       "the rail buttress narrows an end bay below one pill length");
assert(rail_sep > 50, "the two rails are too close together to resist yaw");

// ------------------------------------------------------------
// 10. Cosmetic / ergonomic
// ------------------------------------------------------------
label_w   = 32.0;
label_h   = 9.0;
label_z   = 0.6;
fillet_r  = 2.0;
foot_h    = 0.0;

// ------------------------------------------------------------
// 11. Scale -- 1.0 for the real module, <1 for a bench maquette.
// Applied in layout.scad only, so every dimension above stays true.
// ------------------------------------------------------------
model_scale = is_undef(MODEL_SCALE) ? 1.0 : MODEL_SCALE;

echo(str("bay_w = ", bay_w, "   module = ", module_w, " x ", module_d, " x ", module_h));
echo(str("tray A rim ", trayA_rim, " = tray B floor ", trayB_floor,
         "  -> pick step ", tray_step, " mm at ", pick_lid_slope, " deg"));
echo(str("hopper A floor ", chuteA_floor(yA_hop0), " .. ", chuteA_floor(yA_hop1),
         "   hopper B floor ", rampB(yB_wall1), " .. ", rampB(yB_hop1)));
echo(str("90-day size-00 charge = ", charge_ml, " mL; porch lane ", rib_lane, " mm"));
