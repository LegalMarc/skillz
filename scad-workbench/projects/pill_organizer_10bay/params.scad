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
// 4. Section, in Y (front to back)
//
//   [ tray A ][ tray B ][ hopper B mouth ][ hopper A mouth ]
//     front                                            back
//
// Both pick trays at the front under ONE lid, both fill mouths at the back
// under ONE lid. That grouping forces a crossing: hopper A is the BACK mouth
// but feeds the FRONT tray, so its chute has to duck under tray B and under
// hopper B. Hopper B is the front mouth and feeds the tray right in front of
// it, so it needs no crossing at all.
//
// The crossing is what sets tray B's height, and it is not negotiable:
// tray B's floor must clear the chute's ceiling, which is already rising at
// ramp_deg by the time it gets there. Everything below derives from that.
// ------------------------------------------------------------
pocket_d  = 36.0;           // pick tray depth in Y, both rows
pocket_h  = 38.0;           // pick tray interior height, floor to rim
// Row B's outlet only. Row A's outlet is simply the chute's own constant
// section (chute_clear), because once the chute ceiling runs parallel to its
// floor there is nothing left for a separate restriction to do -- and the
// 1.67mm notch where the two met collapsed under the fillet and tore the mesh.
outlet_h  = 30.0;           // gap under tray B's feed wall
ramp_deg  = 48;             // ramp and chute angle from horizontal (D4)
hopper_run = 72.0;          // hopper B's ramp run in Y
chute_clear = 33.0;         // clear height of the crossing chute
chute_ceil  = 3.0;          // floor thickness above the chute
hopper_free = 15.0;         // freeboard above the highest ramp, for pouring

ramp_tan = tan(ramp_deg);

// Y stations
yA_tray0  = wall_out;                       //   2.8  tray A front face
yA_tray1  = yA_tray0 + pocket_d;            //  38.8  tray A back face = chute A foot
yA_wall1  = yA_tray1 + wall_div;            //  41.2  tray B front wall, back face
yB_tray0  = yA_wall1;                       //  41.2  tray B front face
yB_tray1  = yB_tray0 + pocket_d;            //  77.2  tray B back face = ramp B foot
yB_wall1  = yB_tray1 + wall_div;            //  79.6  hopper B mouth, front
yB_hop1   = yB_wall1 + hopper_run;          // 151.6  hopper B mouth, back
yA_hop0   = yB_hop1 + wall_div;             // 154.0  hopper A mouth, front

// Z stations
base_z      = base_t;                                    //   3.0  tray A floor
function rampA(y) = base_z + (y - yA_tray1) * ramp_tan;  // chute A / hopper A floor
// The two tray rows are 81mm apart in floor height, so a lid covering both as
// an L would be a Z in section -- and a Z cannot be printed without heavy
// support whichever way it is laid, because one arm is always cantilevered.
// So the whole pick surface is ONE SLOPED PLANE from the front face up to tray
// B's rim, and the lid is a flat plate lying on it. The body's outer walls,
// dividers and the wall between the trays all terminate on that plane.
pickplane_front = 74.0;                                  // rim height at the front face
function pickplane(y) = pickplane_front
                      + (y / yB_tray1) * (trayB_rim - pickplane_front);
trayA_rim   = pickplane_front;
outletA_top = base_z + outlet_h;                         //  37.0

// Tray B sits exactly high enough for chute A to pass beneath it. The binding
// point is the BACK of tray B, where chute A has already climbed furthest.
trayB_floor_min = rampA(yB_tray1) + chute_clear + chute_ceil;   // 81.65
trayB_floor = 84.0;
trayB_rim   = trayB_floor + pocket_h;                    // 122.0
outletB_top = trayB_floor + outlet_h;                    // 118.0
function rampB(y) = trayB_floor + (y - yB_tray1) * ramp_tan;

hopper_rim = 200.0;
// Hopper A's floor is chute A continuing at the same angle, so its back wall
// lands where that floor reaches the rim less freeboard.
yA_hop1  = yA_tray1 + (hopper_rim - hopper_free - base_z) / ramp_tan;   // 202.7
module_d = yA_hop1 + wall_out;                                          // 205.5
module_h = hopper_rim;

assert(trayB_floor >= trayB_floor_min,
       "tray B is too low for chute A to pass under it -- the back row's feed would run into the front row's tray");
assert(rampB(yB_wall1) - chute_ceil > rampA(yB_wall1) + chute_clear,
       "chute A does not clear hopper B's floor at the front of hopper B -- the two feeds intersect");
assert(rampB(yB_hop1) - chute_ceil > rampA(yB_hop1) + chute_clear,
       "chute A does not clear hopper B's floor at the back of hopper B");
assert(rampB(yB_hop1) + hopper_free <= hopper_rim,
       "hopper B's ramp reaches the rim -- it would poke out of its own mouth");
assert(rampA(yA_hop1) + hopper_free <= hopper_rim + 0.001,
       "hopper A's floor reaches the rim");
assert(chute_clear > pill_len,
       "the crossing chute is not taller than the longest pill");
assert(outlet_h > pill_len && outlet_h >= 2 * pill_dia,
       "outlet_h fails the pill-passage or slot rule");
assert(trayA_rim > outletA_top && trayB_rim > outletB_top,
       "a tray rim is at or below its own outlet top -- pills could ride out over the lid line");
// The wall between the two trays is cut off by the sloped plane. What is left
// of it above tray B's floor is all that stops tray B's pills spilling forward
// into tray A, so it has to clear a pill lying on its side.
trayB_front_retain = pickplane(yB_tray0) - trayB_floor;
assert(trayB_front_retain > pill_dia + 3,
       "the wall between the trays is cut too low by the pick plane -- tray B would spill into tray A");
assert(pickplane(0) < trayB_rim && pickplane(yB_tray1) > trayA_rim,
       "the pick plane does not rise from front to back");
assert(module_d <= max_part_y && module_h <= max_part_z,
       "the module no longer fits the usable bed");

// The step the pick lid has to bridge. Reported, not chosen -- it falls out
// of the crossing geometry above.
tray_step = trayB_rim - trayA_rim;                       //  81.0

// ------------------------------------------------------------
// 5. Hopper mouths (both at the back, both at hopper_rim -> ONE flat lid)
// ------------------------------------------------------------
hop_mouth_y0 = yB_wall1;                                 //  79.6
hop_mouth_y1 = yA_hop1;                                  // 202.7
hop_mouth_d  = hop_mouth_y1 - hop_mouth_y0;              // 123.1

// ------------------------------------------------------------
// 6. Capacity
// ------------------------------------------------------------
capsule_00_ml       = 0.95;    // size-00 capsule fill volume
loose_packing_frac  = 0.58;    // PATIKRINTI -- estimated, see calculations.md
charge_days         = 90;
charge_ml           = charge_days * capsule_00_ml / loose_packing_frac;

// Measured from the rendered cavity meshes, not a closed form -- the two rows
// now have genuinely different sections, so one formula cannot cover both.
bayA_vol_measured_ml = 0;   // filled in after the first render
bayB_vol_measured_ml = 0;

// ------------------------------------------------------------
// 7. Pick lid -- ONE lid over BOTH tray rows, lift-off
//
// It is not hinged, and that is forced rather than chosen. Grouping both
// trays at the front puts tray_step = 81mm of riser between them, so the lid
// is an L in section. An L's mass centre sits ~48mm BELOW any back-top pivot,
// which puts its over-centre angle near 144 degrees -- it cannot be reached,
// and the lid would fall shut every time. Hinging at the front instead runs
// the far corner into the benchtop at ~24 degrees. A lid that lifts off
// cleanly beats one that will not stay where it is put.
// ------------------------------------------------------------
pick_lid_w     = module_w - 1.0;       // 229.0, 0.5 clearance each side when ganged
pick_lid_clear = 0.35;                 // along the slope, at the back edge
pick_lid_slope = atan((trayB_rim - pickplane_front) / yB_tray1);   // 31.9 deg
pick_lid_len   = sqrt(pow(yB_tray1, 2) + pow(trayB_rim - pickplane_front, 2))
                 - pick_lid_clear;     // 90.5 along the slope
// A flat plate on a 32 degree slope slides: PLA on PLA is good for about 17
// degrees. The lid is therefore hung on a lip that hooks over the module's
// front top edge -- that lip, not friction, is what holds it in place, and
// lifting the front edge is how it comes off.
pick_lid_hook_t = 3.0;
pick_lid_hook_h = 7.0;

pick_lid_gap = 0.2;    // vertical float above the pick plane; keeps the pair a
                       // near miss rather than a coplanar resting contact
pick_lid_tv  = lid_t / cos(pick_lid_slope);   // vertical thickness of a slab
                                              // whose PERPENDICULAR thickness is lid_t

assert(pick_lid_slope > 17.0,
       "the pick plane is shallow enough for friction to hold the lid, so the hook is over-designed -- simplify it");
assert(pick_lid_hook_h > 4.0,
       "the front hook is too shallow to retain the lid on its slope");

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
fill_seat_z     = hopper_rim - lid_t;         // 197.0, underside of the seated lid
// The lid's resting height is not actually fixed by the seat: the barb has
// 0.3mm of lift slop against its pocket ceiling, so the lid can sit anywhere
// in that band. It is modelled at mid-slop, which also keeps the pair a near
// miss rather than a coplanar resting contact -- FCL cannot define a
// penetration depth for two faces lying exactly on each other and reported
// 66.9mm for a pair whose real boolean overlap measures 0.000 mm3
// (INCIDENTS.md 2026-08-19, the declared-contact verdict's known blind spot).
fill_lid_seat_gap = 0.15;
fill_lid_x      = inner_w    - 2 * fill_lid_clear;   // 223.8
fill_lid_y      = hop_mouth_d - 2 * fill_lid_clear;  // 122.5
// Snap-tab cantilever. Length and thickness are set by the strain the barb
// deflection puts on the beam, not by looks: peak bending strain for a
// cantilever deflected d at its tip is 3*t*d / (2*L^2), and PLA is only good
// for a percent or two. A short stubby tab cannot make this engagement.
fill_tab_w      = 16.0;
fill_tab_t      = 1.2;
// The back tab hangs over hopper A's floor, which by the back wall has climbed
// to within 12mm of the seat. That, not the strain formula, is what caps the
// tab length here -- so the tab is thinned instead of lengthened to stay
// inside the strain budget.
fill_tab_drop   = 10.0;                       // how far the tab hangs below the lid
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
ramp_at_back    = max(rampB(yB_hop1), rampA(yA_hop1));   // 185.0, hopper A's floor at the back wall

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
assert(fill_seat_z - fill_ledge_t > rampB(yB_hop1) && fill_seat_z - fill_ledge_t > rampA(yA_hop1),
       "the seat ledge hangs below a hopper floor -- it would be in the pill path");

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

rail1_y   = (yA_wall1 + yB_tray1) / 2;        //  59.2, mid tray B
rail1_z1  = 70.0;                              // male top
rail1_soc_z1 = trayB_rim + 1.0;                // 123.0 -- groove OPEN at the body top
rail2_y   = (yB_wall1 + yB_hop1) / 2;         // 115.6, mid hopper B
rail2_z1  = 170.0;
rail2_soc_z1 = hopper_rim + 1.0;               // 201.0

rail_sep  = rail2_y - rail1_y;                 // 113.2

// Each groove runs from its floor to the top of the side wall above it, so a
// neighbouring module is simply lowered alongside and both rails engage
// progressively -- no minimum lift, and the groove floor at rail_z0 is what
// registers the two modules flush at the bottom.
assert(rail1_soc_z1 > rail1_z1 && rail2_soc_z1 > rail2_z1,
       "a rail groove is shorter than its own male -- the modules could not be brought together");
assert(rail1_soc_z1 <= trayB_rim + 1.0 && rail2_soc_z1 <= hopper_rim + 1.0,
       "a rail groove runs past the side wall that is supposed to carry it");
assert(rail_boss + wall_out - rail_out - rail_depth_clear >= 1.5,
       "not enough material left behind the rail groove -- the buttress is too thin");
assert(bay_w - rail_boss >= pill_len,
       "the rail buttress narrows an end bay below one pill length");
assert(rail_sep > 50,
       "the two rails are too close together to resist yaw between ganged modules");

// ------------------------------------------------------------
// 10. Cosmetic / ergonomic
// ------------------------------------------------------------
label_w   = 32.0;
label_h   = 9.0;
label_z   = 0.6;            // recess depth
fillet_r  = 2.0;            // internal radius, tray floor to wall
foot_h    = 0.0;            // flat bottom; no feet (bed adhesion surface)

echo(str("bay_w = ", bay_w, "   module = ", module_w, " x ", module_d, " x ", module_h));
echo(str("tray A rim ", trayA_rim, " / tray B rim ", trayB_rim, " -> lid step ", tray_step, " mm"));
echo(str("chute A clear under tray B = ", trayB_floor - chute_ceil - rampA(yB_tray1),
         " mm; under hopper B = ", rampB(yB_wall1) - chute_ceil - rampA(yB_wall1), " mm"));
echo(str("90-day size-00 charge = ", charge_ml, " mL"));
