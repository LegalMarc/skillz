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
// D37 (revision 10): 5 mm of plate margin each side in X and Y, so a part's
// footprint may be 246 mm; height may be 250. This replaces D3's 13 mm margin
// (243 mm), which the wider, deeper bins no longer fit. The body's footprint is
// measured INCLUDING the 3 mm joining rail (5 until D43) that stands proud of the left face.
plate_margin = 5.0;
max_part_x = bed_x - 2 * plate_margin;     // 246
max_part_y = bed_y - 2 * plate_margin;     // 246
max_part_z = 250.0;

// ------------------------------------------------------------
// 1. Contents -- the design pill envelope (D2)
// ------------------------------------------------------------
pill_len = 26.0;
pill_dia = 11.0;
repose_deg = 30;            // static angle of repose on PLA, PATIKRINTI -- estimated

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
void_top_over = 5.0;        // how far every open-topped void runs PAST the
                            // outer surface it opens through. A void whose top
                            // edge lies exactly on the shell's top face is a
                            // coplanar boolean; it held until a third cut broke
                            // through that face (INCIDENTS.md, revision 6).
                            // 5, not 1: the fillet pass rounds the void's top
                            // corners with a 4.3mm tangent, and at 1 that put
                            // solid shoulders back BELOW the pick plane.

// ------------------------------------------------------------
// 3. Bay grid
// ------------------------------------------------------------
bays        = 5;
module_w    = 240.0;        // 230 until D37: bays 42.96 -> 44.96 wide. Footprint with
                            // the 3 mm rail is 243, inside max_part_x (246)
inner_w     = module_w - 2 * wall_out;
bay_w       = (inner_w - (bays - 1) * wall_div) / bays;
bay_pitch   = bay_w + wall_div;
function bay_center_x(i) = wall_out + bay_w / 2 + i * bay_pitch;

assert(module_w + rail_out <= max_part_x,
       "module_w plus the joining rail exceeds the plate width less its margins (D37)");
assert(bay_w >= pill_len * 1.5,
       "bay_w is under 1.5x pill_len -- a pill cannot lie freely across the bay");

// ------------------------------------------------------------
// 4. Section, in Y (front to back)  -- REVISION 3 onward
//
//   [ tray A ][ tray B ][ hopper B mouth ][ hopper A mouth ]
//     front                                            back
//
// Both pick trays at the front under ONE lid, both fill mouths at the back
// under ONE lid. That grouping forces a crossing: hopper A is the BACK mouth
// but feeds the FRONT tray, so its chute ducks under tray B and hopper B.
//
// Revision 3 changed two things about that chute.
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
tray_d      = 40.0;         // pick tray depth in Y, both rows (28 until D37: "a little small")
trayB_h     = 53.0;         // tray B interior height, floor to rim (38 until D33, 47 until D37).
                            // With the 40 degree porch (D36) tray B's floor sits 49 mm higher
                            // than it did, and the wall between the trays has to stay
                            // pill_dia + 3 over that floor while the pick plane stays under
                            // 45 degrees; both set the rim, see trayA_rim below
outlet_h    = 27.0;         // gap under tray B's feed wall (row B's outlet): just
                            // over one pill length, so a capsule arriving end-on
                            // still passes. 30, then 28 after D26; 27 by D33, which
                            // is as low as that rule allows
ramp_deg    = 40;           // ramp and chute angle from horizontal (D11)
// The porch was 20 degrees (D12), then 25 (D20): shallower than repose, so it
// carried a stagnant wedge and tray A fed at the repose angle itself, with no
// margin. Test print 2 showed the result: row B, on a plain 40 degree ramp, fed
// well; row A filled once and did not refill as pills were taken. The porch is
// now the same 40 degrees as the ramp (D36), so the chute is one straight floor
// and the wedge is gone. The cost is height: everything behind the porch rises.
porch_deg   = 40;           // chute floor angle under tray B (D12, D20, D36)

// Tray A's floor is tilted down toward the front wall (D36). Pills that reach
// tray A on a flat floor stop where they land, and as the front of the pile is
// picked away the ones behind do not follow unless the pile's surface is past
// repose. On a floor steeper than the pills' own friction angle every pill on it
// slides forward, so the pile re-forms against the front wall by itself. The
// angle is chosen against the repose estimate (30, plausible range 25-35, and
// the pill-on-PLA friction angle is no higher than the pile's repose): at 35 the
// floor is at the TOP of that range, so even at a 35 degree repose nothing on it
// can rest. Steeper still costs tray_d x tan(angle) of module height for no
// further margin. calculations.md, "Derived: tray A's tilted floor".
trayA_tilt_deg = 35;        // tray A floor, falling toward the front wall (D36)
repose_hi_deg  = 35;        // top of the plausible repose range for capsules on PLA
hopperB_run = 70.0;         // hopper B mouth depth in Y
hopperA_run = 32.0;         // hopper A mouth depth in Y
chute_clear = 36.0;         // clear height of the crossing chute, at the ridge
chute_ceil  = 3.0;          // floor thickness above the chute
hopper_free = 12.0;         // minimum freeboard above the highest ramp

ramp_tan  = tan(ramp_deg);
porch_tan = tan(porch_deg);
tiltA_tan = tan(trayA_tilt_deg);

// Y stations
yA_tray0  = wall_out;                       //   2.8  tray A front face
yA_tray1  = yA_tray0 + tray_d;              //  42.8  tray A back face = chute A foot
yA_wall1  = yA_tray1 + wall_div;            //  45.2
yB_tray0  = yA_wall1;                       //  45.2  tray B front face
yB_tray1  = yB_tray0 + tray_d;              //  85.2  tray B back face = porch end
yB_wall1  = yB_tray1 + wall_div;            //  87.6  hopper B mouth, front
yB_hop1   = yB_wall1 + hopperB_run;         // 157.6  hopper B mouth, back
yA_hop0   = yB_hop1 + wall_div;             // 160.0  hopper A mouth, front
yA_hop1   = yA_hop0 + hopperA_run;          // 192.0  hopper A mouth, back
module_d  = yA_hop1 + wall_out;             // 194.8

porch_run = yB_tray1 - yA_tray1;            //  42.4

// Z stations
base_z  = base_t;                                        //   3.0  tray A floor at the front wall
z_foot  = base_z + tray_d * tiltA_tan;                   //  31.0  tray A floor at the chute foot
z_porch = z_foot + porch_run * porch_tan;                //  66.6  chute floor at the porch end

// Chute A's floor: porch_deg under tray B, then ramp_deg all the way back (the
// same angle since D36, so one straight line). Tray A's own floor, in front of
// the foot, falls forward at trayA_tilt_deg from z_foot down to base_z.
function chuteA_floor(y) = y <= yB_tray1
                         ? z_foot  + (y - yA_tray1) * porch_tan
                         : z_porch + (y - yB_tray1) * ramp_tan;
function trayA_floor(y) = base_z + (y - yA_tray0) * tiltA_tan;
// Its ceiling runs parallel, holding a constant section. Following a flat
// underside instead left 7197 mm^2 of bridged ceiling in revision 2
// (INCIDENTS.md 2026-09-20). This is the ceiling at the BAY EDGES; on the 40
// degree leg it is vaulted (D26, below), rising vault_up above this line at
// the bay centre and dropping vault_down below it at the edges.
function chuteA_ceil(y) = chuteA_floor(y) + chute_clear;

// ------------------------------------------------------------
// 4e. The vault (D26). A ceiling sloping only front-to-back at 40 degrees is
// a 50-degree-from-vertical overhang, the one print risk revisions 3-6 carried
// as an ADVISORY. Tilting the same face sideways as well -- a shallow ridge
// down the centre of each bay -- makes the diagonal steeper: with the ridge
// (vault_up + vault_down) above the edges over a half-bay, the face is
// 90 - atan(sqrt(tan(gable)^2 + tan(40)^2)) from vertical, 44.8 degrees here.
// The rise is split: the ridge goes up vault_up into the deck, so hopper B's
// floor and outlet rise with it; the edges come down vault_down, which the
// chute can spare (30 clear at the edges, 42 at the ridge). Costs row B about
// 18 mL per bay. The porch under tray B is not vaulted -- its ceiling is flat
// and bridges the bay (D29).
// ------------------------------------------------------------
vault_up    = 4.4;         // 6 / 6 until D33, 4 / 8 until D37: every mm of vault_up lifts hopper
vault_down  = 8.0;         // B's ramp foot and outlet, and with them tray B's pile. The 0.4 is
                           // D37: bays 2 mm wider made the gable shallower, 45.15 degrees from
                           // vertical, and the rise has to grow with the bay to stay under 45
vault_lead  = 2.0;          // the ridge starts this far behind the porch end
vault_ramp  = 8.0;          // and rises over this run, not in a vertical step (D35)
vault_slope = (vault_up + vault_down) / (bay_w / 2);            // tan of the gable
vault_deg   = atan(vault_slope);                                //  29.2
vault_face_from_vertical = 90 - atan(sqrt(pow(vault_slope, 2) + pow(ramp_tan, 2)));  // 44.8
vault_top_over = 2.0;       // how far the vault's solid reaches up into the deck
vault_embed = 1.0;          // how far each roof half reaches INTO its divider or
                            // side wall. Less than weld_embed because the side
                            // walls also carry the rail roots' weld_embed from
                            // outside, and 1.5 + 1.5 does not fit in 2.8
vault_y0    = yB_tray1 + vault_lead;                            // 87.2, ridge starts
vault_y1    = yB_hop1 - 0.6;                                    // 157.0, ridge ends
vault_roof_y0 = yB_tray1 + vault_lead / 2;                      //  86.2, the added solid starts
vault_roof_y1 = yB_hop1;                                        // 157.6, and ends, inside the wall between the hoppers
function chuteA_ridge(y) = chuteA_ceil(y)
    + (y > vault_y0 && y < vault_y1 ? vault_up * min(1, (y - vault_y0) / vault_ramp) : 0);

assert(vault_face_from_vertical <= 45.0,
       "the vaulted chute ceiling is still past the 45 degree overhang limit -- raise vault_up + vault_down");
assert(chute_clear - vault_down >= pill_len + 2 && chute_clear - vault_down >= 2 * pill_dia,
       "the chute at the bay edges, under the vault's low side, is too low for a pill");
assert(vault_top_over < chute_ceil,
       "the vault's solid reaches through the deck into hopper B's floor");
assert(vault_embed + weld_embed < wall_out - 0.2,
       "the vault roof's embed and the rail root's embed meet inside the side wall");
assert(vault_roof_y0 > yB_tray1 && vault_roof_y0 < vault_y0 && vault_y1 < vault_roof_y1,
       "the vault's added solid must start before the ridge void and end after it, each strictly, or their faces coincide");

// Tray B sits one slab above the chute ceiling at the porch's end -- which is
// the whole point of the porch, because that is where the ceiling is lowest.
trayB_floor = chuteA_ceil(yB_tray1) + chute_ceil;        // 105.59
trayB_rim   = trayB_floor + trayB_h;                     // 158.59
// Hopper B's ramp rides one deck above the vault's RIDGE, so it starts
// vault_up above tray B's floor: a 4mm riser at the tray's back wall that
// pills drop off (D26). The outlet top rises with it.
rampB_foot  = trayB_floor + vault_up;                    // 109.99
outletB_top = rampB_foot + outlet_h;                     // 136.99
function rampB(y) = rampB_foot + (y - yB_tray1) * ramp_tan;

// Tray A's rim is set INDEPENDENTLY of tray B's floor (D15). It started life
// level with it, which looked right in section, but pills only pile to the
// chute mouth at 39 and slope forward from there to about 23 at the front
// wall -- so a 53mm rim left a 32mm reach down into the front tray every time.
// Dropping the rim steepens the one pick plane instead of adding a second lid:
// the reach falls to 21mm at the front and 28mm at the back, and the front
// face loses 11mm. How far it can drop is bounded by trayB_front_retain below.
//
// Above the rim the pick surface is ONE SLOPED PLANE up to tray B's rim -- a
// lid spanning two flat steps is a Z in section, and a Z cannot be printed
// without support whichever way it is laid.
// 43, not 42: raising the porch to 25 degrees (D20) lifted tray B's floor by
// 3.1mm, and the wall between the trays only keeps its pill_dia + 3 retaining
// height if the plane's front end comes up with it. The front WALL is
// scalloped to trayA_front_h regardless, so the reach over the wall is unchanged.
trayA_rim       = 77.0;   // 43 until D33 (44), 77 from D36/D37. The 40 degree porch and the tilted
                          // tray A floor lift tray B's floor to 105.6, and the wall between the
                          // trays must stand pill_dia + 3 over it (trayB_front_retain) with the
                          // plane under 45 degrees (the pick lid prints on it). The plane's
                          // front end is what is left to move; the front WALL is scalloped
                          // down to trayA_front_h regardless (D17), so the reach is unchanged
pickplane_front = trayA_rim;
function pickplane(y) = pickplane_front
                      + (y / yB_tray1) * (trayB_rim - pickplane_front);

// Tray B's pile (D33). Pills leave hopper B under the flat bottom of its front
// wall at outletB_top and fall forward at repose from that wall's front face.
// That surface, not tray B's depth, is what the wall between the trays has to
// hold back -- the same model D17 applies to tray A. Revision 7's vault lifted
// the outlet 6mm and put this pile 1.9-3.3mm ABOVE the wall at the 30 degree
// estimate: with the lid off, row B would have spilled into row A. Found by the
// revision 8 review; trayB_front_retain measured from the floor and never saw it.
trayB_pile_front = outletB_top - (yB_tray1 - yB_tray0) * tan(repose_deg);
trayB_pile_margin = pickplane(yB_tray0) - trayB_pile_front;
assert(trayB_pile_margin >= 5.0,
       "tray B's pill pile stands within 5mm of the top of the wall between the trays -- row B would spill into row A");
assert(pickplane(yB_tray0) - (outletB_top - (yB_tray1 - yB_tray0) * tan(25)) > 0,
       "at a 25 degree repose tray B's pile would overtop the wall between the trays");
assert(trayB_rim - outletB_top >= 3.0,
       "hopper B's outlet top is within 3mm of tray B's rim -- pills could ride out under the lid");

// Row A's outlet is the chute's own section: at tray A the ridge stands
// chute_clear above the floor and the ceiling is already a chamfer.
outletA_top = z_foot + chute_clear;                      //  67.0
// Tray A is fed by that mouth, so its pill surface is not flat: it peaks there
// and falls forward at the angle of repose. That surface, not the tray's depth,
// is what the front wall has to retain (D17).
trayA_pile_front = outletA_top - tray_d * tan(repose_deg);   //  43.9

hopper_rim = 189.0;         // 141 until D36: everything behind the porch rose with it. 18 mm of
                            // freeboard over hopper B's ramp end (170.7), as before
module_h   = hopper_rim;

// ------------------------------------------------------------
// 4g. Hopper A's pouring flare (D42, revision 11). Test print 3: filling tray A
// from the back was "a little harder" than tray B: hopper A's mouth is the narrow
// one (39 mm against B's 63). The back wall of the module, behind hopper A, now
// leans outward from the end of the chute floor up to the rim, inner and outer faces
// parallel, so the opening you pour into widens toward the rim. It starts AT the
// chute floor's end (the floor is not touched, so no pill can rest on a flattened
// floor) and the whole recess the fill lid sits in is carried back with it, so the lid
// is simply longer: it still drops into a rectangular recess with fill_lid_clear all
// round and rests flat. The outer face leans out at flare_deg from vertical, an
// overhang inside the 45 degree no-support rule. The extra depth is only above
// flare_zo; the base and the cubby keep module_d.
// ------------------------------------------------------------
flare_deg  = 30;
flare_tan  = tan(flare_deg);
flare_z0   = chuteA_floor(yA_hop1);                       // 156.2: inner face leans from here
function flare_dy(z) = max(0, z - flare_z0) * flare_tan;   // how far the inner face has moved back
flare_th_h = wall_out / cos(flare_deg);                    // horizontal wall thickness along the lean
// where the OUTER face starts to lean: at the back edge of the cubby's ceiling (the 45 degree
// plane meets the back face 3 mm under the chute floor there), so the cubby's edge and the
// lean share one point and no 0.8 mm2 flat sliver is left between them (review K4). The
// matching assert is next to the cubby, which is defined after this.
flare_zo   = chuteA_floor(module_d) - 3.0;
module_d_top = module_d + max(0, hopper_rim - flare_zo) * flare_tan;   // depth at the rim
assert(flare_deg >= 20 && flare_deg <= 40,
       "the hopper A flare is outside 20..40 degrees from vertical (D42): the outer face overhang would pass 45 or the mouth would barely widen");

// ------------------------------------------------------------
// 4b. Hopper divider lean (D16)
//
// Hopper A's mouth was 32mm against hopper B's 70 -- you pour the same charge
// into both, and one of them is a slot. That ratio was not chosen; it fell out
// of holding the two rows' VOLUMES near each other, which is the wrong thing
// to equalise when the number you meet with a bottle in your hand is the mouth.
//
// The wall between the two mouths therefore leans forward at the top, pivoting
// where it springs off the chute ceiling. Leaning costs hopper B a wedge above
// its own floor and gives hopper A the same wedge, which is cheap: hopper A is
// the taller of the two there. It also gives hopper A a mouth wider than its
// throat, which is the right way round for a hopper.
// ------------------------------------------------------------
hopA_lean  = 8.8;                                        // forward offset at the rim
// Where the wall springs. It used to be the chute ceiling alone. The vault
// (D26) lifted hopper B's ramp foot, so the ramp now ENDS 7mm above that
// point -- and a wall that starts leaning below the ramp's end crosses the
// ramp's own face: the review of revision 7 measured it 0.2-0.8mm thick over
// its bottom 5mm in every bay. It now springs from whichever is higher, and
// VOID_A carries a vertex there so the wall is vertical up to it.
hopwall_z0 = max(chuteA_ceil(yA_hop0), rampB(yB_hop1));  // 170.7, the ramp's end
function hopwall_A(z) = yA_hop0
                      - hopA_lean * max(0, z - hopwall_z0) / (hopper_rim - hopwall_z0);
function hopwall_B(z) = hopwall_A(z) - wall_div;

hop_lean_deg  = atan(hopA_lean / (hopper_rim - hopwall_z0));   // 25.7 (19.35 before the vault fix)
mouthB_w      = hopwall_B(hopper_rim - lid_t) - yB_wall1;             // 62.6
mouthA_w      = yA_hop1 + flare_dy(hopper_rim - lid_t) - hopwall_A(hopper_rim - lid_t);   // 56.6 under the lid (39.4 before D42)
mouthA_rim    = yA_hop1 + flare_dy(hopper_rim) - hopwall_A(hopper_rim);                  // 59.7 at the rim
mouth_ratio   = mouthB_w / mouthA_w;                           // 1.11 since D42 (1.59, about 3:2, before it)

assert(hop_lean_deg < 40,
       "the hopper divider leans past the FDM overhang band -- its front face would need support");
assert(hopwall_A(rampB(yB_hop1)) - yB_hop1 >= wall_div - 1e-6,
       "the hopper divider is thinner than wall_div where hopper B's ramp ends -- the lean starts below the ramp's end");
assert(hopper_rim - hopwall_z0 >= 10.0,
       "the hopper divider springs from less than 10mm under the rim: the lean would run out of height (hopwall_z0 is a max() that contains rampB's end, so it cannot be asserted against it)");
// D16's 3:2 band assert is retired (review K3): the flare (D42) sets hopper A's mouth
// directly, to at least 55 mm at the rim, so the ratio is a consequence (1.11), not a target.
// A band on it would only repeat the next assert or fail for the wrong reason.
assert(mouthA_rim >= 55.0,
       "hopper A's mouth at the rim is under 55mm front to back (D42)");
assert(mouthA_w > pill_len + 8 && mouthB_w > pill_len + 8,
       "a fill mouth is too narrow to pour a bottle into");


assert(trayB_floor > chuteA_ceil(yB_tray1),
       "tray B's floor is not above the chute ceiling -- the two feeds intersect");
assert(rampB(yB_wall1) - chute_ceil > chuteA_ridge(yB_wall1) - 1e-6,
       "chute A's vault ridge does not clear hopper B's floor at the front of hopper B");
assert(rampB(yB_hop1) - chute_ceil > chuteA_ridge(yB_hop1) - 1e-6,
       "chute A's vault ridge does not clear hopper B's floor at the back of hopper B");
assert(rampB(vault_y1) - chute_ceil > chuteA_ridge(vault_y1 - 1e-3) - 1e-6,
       "chute A's vault ridge does not clear hopper B's floor where the ridge ends");
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
assert(porch_deg >= ramp_deg - 1e-6,
       "the porch is shallower than the ramp -- it carries a stagnant wedge that tray A cannot feed over (D36)");
assert(trayA_tilt_deg >= repose_hi_deg && trayA_tilt_deg < ramp_deg,
       "tray A's floor is not steeper than the top of the repose range, or it is steeper than the ramp it is fed by (D36)");
assert(module_d_top <= max_part_y && module_h <= max_part_z,
       "the module no longer fits the usable bed");

tray_step = trayB_rim - trayA_rim;                       //  81.59

// ------------------------------------------------------------
// 4c. Scalloped front wall (D17)
//
// Dropping the LID PLANE any further is blocked: its back end is pinned to
// tray B's rim, so a lower front end cuts the wall between the trays below
// trayB_front_retain and tray B spills forward into tray A. But the lid plane
// and the front WALL do not have to be the same height.
//
// So the front face is scalloped down to trayA_front_h across each bay, while
// the dividers and the two side walls still run up to the plane and carry the
// lid. With the lid off you reach over a 30mm wall instead of a 42mm one, and
// the pills -- which crest at 22.8 there -- are open to the front. With the
// lid on, its skirt hangs down the outside and closes the scallops.
// ------------------------------------------------------------
trayA_front_h   = 55.0;     // 30 until D36 (pile crests at 43.9, not 22.8), 52 until the revision 10
                            // review: at a 25 degree repose the crest is 48.4 and the wall must
                            // stand over it by at least a pill radius (asserted), not 2 mm
trayA_scallop_r = 6.0;
// The two END bays are not scalloped all the way to the side wall (D38). The
// front wall stays at the full pick-plane height for pillar_w beside each side
// wall, and behind it sits a STOP BLOCK (section 9, pick_stop_*) whose back
// face is perpendicular to the pick plane. That face is what stops the pick lid
// sliding down its slope: the lid's lug drops in directly behind it. See
// pick_lid.scad and probes/lid_retention.py. (Until revision 10 the lid's
// skirt was believed to do this job; it hangs OUTSIDE the front face, sliding
// down the slope takes it further from that face, and it retained nothing.
// INCIDENTS.md.)
pillar_w        = 6.0;      // from the side wall's inner face, in X (stop block width too)
// The scallop's sides would otherwise land exactly on the bay dividers' own
// faces -- two boolean faces sharing one plane, which is what left 57
// non-manifold edges the first time. It oversteps instead, taking a sliver off
// each divider's front tip above the scallop line.
scallop_over    = 0.4;
// Label recesses for 1/2 inch Brother TZe tape (D19). Two per bay: the lower
// strip on the module's own front face, below the lid skirt so it reads with
// the lid on; the upper strip on the wall between the trays, which faces
// forward over tray A. Revision 5 documented these sizes but never wrote them
// here -- the recesses shipped 9mm tall for a 12mm tape (INCIDENTS.md,
// revision 6). Defined here, not in section 10, because the skirt assert in
// section 7 reads them.
label_tape_w    = 12.0;     // 1/2 inch TZe, nominal
label_clear     = 0.6;      // tape sits in the recess without being pushed
label_h         = label_tape_w + label_clear;            //  12.6
label_w         = 36.0;
label_z         = 0.5;      // recess depth; tape is about 0.16 thick
// D45 (revision 11): both labels on the module's flat front face, below the skirt,
// stacked: the row A (front tray) label low, the row B (back tray) label above it,
// as the trays stack from the front-bottom up and back. The upper strip on the wall
// between the trays (D19) is gone: reaching over tray A for it was awkward and the
// rail buttress half hid it.
label_gap       = 4.0;      // between the two strips
label_z_center  = 14.0;     // row A strip, centre height on the front face
label_b_center  = label_z_center + label_h + label_gap;          // row B strip, 30.6
label_cut_over  = 1.0;      // the cut starts this far OUTSIDE the face, never inside it

assert(label_w < bay_w - 4,
       "the label recess is wider than the bay leaves room for");
assert(label_gap >= 3.0, "the two label strips are closer than 3mm");
// (the upper strip vs the lid skirt is asserted once, in section 7 with the skirt)
assert(min(wall_out, wall_div) - label_z >= 1.8,
       "the label recess is cut so deep it leaves a wall thinner than 1.8mm");
assert(label_z_center - label_h / 2 > 2,
       "the lower label recess runs off the bottom of the front face");

assert(trayA_front_h > trayA_pile_front + 5,
       "the scalloped front wall is at or under the pill line -- row A would spill out of its own front");
assert(trayA_front_h > outletA_top - tray_d * tan(25) + pill_dia / 2,
       "at a 25 degree repose tray A's pile would crest within a pill radius of the front wall's top (or over it)");
assert(trayA_front_h < trayA_rim - 6,
       "the scallop is too shallow to be worth cutting");
assert(trayA_scallop_r < (bay_w - 2 * trayA_scallop_r) / 2,
       "the scallop radius has eaten the flat part of the scallop");

// ------------------------------------------------------------
// 4a. The porch ceiling (D29, replacing the splitter rib of D13)
//
// Tray B's floor is carried on the bay dividers alone -- the chute runs
// underneath. Revisions 3-7 ran the chute ceiling under it parallel to the
// 25 degree porch floor, which is a near-flat overhang across the whole bay,
// and held it up with a splitter rib down the middle of each porch. The first
// test print showed both costs: the ceiling printed as a ragged, stringy edge
// at the back of every front bin anyway, and the rib stood as an unexplained
// fin in each bin that split the pill flow into two 20mm lanes.
//
// The ceiling under tray B is now FLAT, one deck below tray B's floor -- the
// height it already reached at tray B's back wall, so the 40 degree leg meets
// it with no step. A flat 43mm span is a bridge every slicer recognises and
// prints with bridge settings; a 25 degree ceiling is the worst case, each
// layer an unsupported overhang. The mouth into tray A is still the bottom of
// the wall between the trays at outletA_top, so the pile in tray A is
// unchanged; behind that wall the chute simply has a taller pocket.
// ------------------------------------------------------------
porch_ceil_z = chuteA_ceil(yB_tray1);                    // 102.59, flat
// Both outlet openings get 45 degree chamfers in their top corners, so the
// unsupported span across the top of each opening is shorter than the bay.
outlet_chamfer = 8.0;

assert(bay_w - 2 * outlet_chamfer > pill_len,
       "the outlet corner chamfers narrow the top of the opening below one pill length -- a capsule lying crosswise would catch");

// The throats, measured perpendicular to the 40 degree floor from the nearest point
// of the wall in front (review F3, G5). The nearest point is that wall's back-bottom
// corner, wall_div further up the floor than its front-bottom corner, so
// (opening - wall_div x tan(40)) x cos(40). At the bay centre; near a divider the
// 45 degree outlet chamfers (outlet_chamfer 8) lower the opening's top by
// (outlet_chamfer - distance from the divider), so the corner throat is smaller.
function throat(open_h, from_divider = 1000) =
    (open_h - max(0, outlet_chamfer - from_divider) - wall_div * ramp_tan) * cos(ramp_deg);
mouthA_min        = throat(chute_clear);                    // 26.03 at the bay centre
mouthA_corner_min = throat(chute_clear, 0);                 // 19.9 at the divider face
mouthA_corner_pill = throat(chute_clear, pill_dia / 2);     // 24.1 a pill's radius from the divider
// What actually fed in test print 2: row B's outlet, 27 mm vertical on the same 40
// degree ramp with the same chamfers, measured the same way.
mouthB_demonstrated        = throat(outlet_h);              // 19.2 at the bay centre
mouthB_corner_demonstrated = throat(outlet_h, 0);           // 13.0 at the divider face
// Row A's mouth is NOT a measured fit: it is asserted never to be tighter than the
// one that fed well, with 25% in hand at the centre, and (sanity floor) at least one
// pill length. The pill-length floor only matters to a capsule standing on end.
// (These two asserts are a backstop: the chute-height-under-the-vault and tray B pile-margin
// asserts above bind first today; these only start to matter if those limits are relaxed.)
assert(mouthA_min >= 1.25 * mouthB_demonstrated && mouthA_corner_min >= mouthB_corner_demonstrated,
       "row A's mouth is tighter than row B's, which is the one test print 2 showed feeding well (centre 1.25x, at the divider face 1.0x)");
assert(mouthA_min >= pill_len,
       "the minimum of the mouth into tray A, measured perpendicular to the floor, is under one pill length (sanity floor)");

// ------------------------------------------------------------
// 4d. Accessory cubby (D18)
//
// The wedge under the crossing chute is a third of the printed section and it
// can never hold pills -- the chute floor has to fall toward tray A at the
// angle of repose, so nothing can sit below that line and still discharge.
// What it CAN do is hold everything else: a splitter, a funnel, the spare
// lids. The cubby opens through the BACK face only -- both side walls are left
// full -- as one void the full inner width, with its ceiling running parallel
// to the chute floor so it self-supports rather than bridging.
// ------------------------------------------------------------
cubby_d    = 70.0;          // depth in Y from the back face
cubby_ceil = 3.0;           // MINIMUM deck thickness between the cubby and the chute
// The ceiling used to run parallel to the chute floor at 40 degrees, which
// revision 5 called "self-supporting". It is a 50-degree-from-vertical
// overhang -- the same one the chute ceiling carries as an ADVISORY -- across
// the full 224mm inner width with nothing to anchor a drooping perimeter to.
// It now runs at 45 degrees, the conservative FDM limit, anchored so the deck
// is cubby_ceil thick at the back face and thickens toward the front. (D21)
cubby_ceil_deg = 45;
cubby_back  = module_d - wall_out;
cubby_y0   = module_d - cubby_d;
function cubby_ceil_z(y) = chuteA_floor(module_d) - cubby_ceil
                         - (module_d - y) * tan(cubby_ceil_deg);
cubby_h_back  = cubby_ceil_z(module_d) - base_t;
assert(abs(flare_zo - cubby_ceil_z(module_d)) < 1e-6,
       "the flare's outer lean no longer starts at the back edge of the cubby's ceiling (K4)");
// normal thickness of the leaning back wall: the horizontal gap between the two lean lines
// (outer through (module_d, flare_zo), inner through (yA_hop1, flare_z0)) times cos(flare_deg)
flare_wall_t = ((module_d - yA_hop1) + (flare_z0 - flare_zo) * flare_tan) * cos(flare_deg);
assert(flare_wall_t >= wall_out - 0.2,
       "the leaning back wall behind hopper A is more than 0.2mm thinner than wall_out");
cubby_h_front = cubby_ceil_z(cubby_y0) - base_t;
// A retaining lip across the opening, so whatever is in there stays in there
// when the module is slid around the bench. You reach in over it rather than
// sliding things out. It is simply the bottom of the back wall, left uncut.
// Its top stands cubby_lip_top (76) above the bench (D50, the user's decision,
// superseding D21's 30): the back of the cubby is a deep pocket that holds
// upright items (lip balm, a pill cutter). That puts the lip above the cubby's
// shallow end on purpose, so the front of the cubby is a well.
cubby_lip_top = 76.0;
cubby_lip_h = cubby_lip_top - base_t;

assert(cubby_y0 > yB_tray1 + 10,
       "the cubby reaches forward into the porch, where the chute floor is too low to leave a deck");
assert(cubby_ceil_deg >= ramp_deg && cubby_ceil_deg <= 45,
       "the cubby ceiling must be at least as steep as the chute floor (or the deck thins toward the back) and no steeper than the 45 degree overhang limit");
assert(cubby_h_front > 25,
       "the cubby's shallow end is too low to put anything in");
assert(cubby_ceil >= 3.0,
       "the deck between the cubby and the chute is thinner than a printed floor");
assert(cubby_lip_h + base_t < cubby_ceil_z(module_d) - 25,
       "the retaining lip leaves under 25mm of clear opening above it");
// D50: the lip stands 73 mm over the floor, so the cubby's floor in front of it is a well
// (the user's decision, superseding D21's "a shelf you see into"). Two things still have to
// hold for it to be a pocket and not a sealed box: the lip stays under the ceiling at the
// shallow end (which is 83 mm tall, so by about 10 mm), and the lip is a horizontal,
// up-facing step (a bridge-free edge: it is the uncut bottom of the back wall).
assert(cubby_lip_h <= cubby_h_front - 5,
       "the retaining lip comes within 5mm of the cubby's ceiling at the shallow end: the front of the pocket is sealed off from the back");
assert(cubby_lip_h < cubby_h_back * 0.6,
       "the retaining lip takes more than 60% of the cubby's opening height");

// ------------------------------------------------------------
// 5. Hopper mouths (both at the back, both at hopper_rim -> ONE flat lid)
// ------------------------------------------------------------
hop_mouth_y0 = yB_wall1;                                 //  87.6
hop_mouth_y1 = yA_hop1 + flare_dy(hopper_rim - lid_t);             // 209.2: the recess follows the flare to the lid's underside
hop_mouth_d  = hop_mouth_y1 - hop_mouth_y0;              // 121.6

// ------------------------------------------------------------
// 6. Capacity
// ------------------------------------------------------------
capsule_00_ml       = 0.95;
loose_packing_frac  = 0.58;    // PATIKRINTI -- estimated, see calculations.md
charge_days         = 90;
charge_ml           = charge_days * capsule_00_ml / loose_packing_frac;

bayA_vol_measured_ml = 0;
bayB_vol_measured_ml = 0;

// ------------------------------------------------------------
// 7. Pick lid -- ONE lid over BOTH tray rows, lift-off
// ------------------------------------------------------------
pick_lid_w     = module_w - 1.0;
pick_lid_clear = 0.35;       // skirt to the front face
pick_lid_back_clear = 1.2;   // plate back edge to the wall behind tray B. 0.35 until the revision 10
                             // review: lifting the lid by the front edge pivots it about this edge
                             // and the top-back corner swings into that wall after about 9 degrees;
                             // 1.2 clears a 15 degree tilt (probes/lid_retention.py (e))
pick_lid_slope = atan((trayB_rim - pickplane_front) / yB_tray1);   // 43.8 deg
pick_lid_len   = sqrt(pow(yB_tray1, 2) + pow(trayB_rim - pickplane_front, 2))
                 - pick_lid_back_clear;
pick_lid_hook_t = 3.0;
pick_lid_gap    = 0.2;   // vertical float above the pick plane; keeps the pair a
                         // near miss rather than a coplanar resting contact
// A skirt (D17): it hangs down the OUTSIDE of the front face, past the
// scalloped wall, and closes the scallops. It does NOT retain the lid. Revisions
// 6 to 9 said it did ("it cannot pass the front face"), which is true only of
// sliding BACKWARD, up the slope. Sliding down the slope moves the lid forward,
// and the skirt, which hangs 0.35 outside that face, simply moves further from
// it: nothing touches. Test print 2 slid the lid straight off. Retention is the
// lug-and-pillar pair of D38 (section 12 below); this is a cover and a place for
// the "FRONT" mark.
pick_lid_skirt_over = 6.0;                       // overlap onto the scalloped wall
pick_lid_hook_h = pickplane_front + pick_lid_gap
                - (trayA_front_h - pick_lid_skirt_over);       //  31.2
pick_lid_skirt_bot = pickplane_front + pick_lid_gap - pick_lid_hook_h;   //  46.0
pick_lid_tv  = lid_t / cos(pick_lid_slope);

assert(pick_lid_slope > 17.0 && pick_lid_slope <= 45.0,
       "the pick plane is outside 17..45 degrees: under 17 friction alone would hold the lid and the lugs are decoration; over 45 the lid's skirt prints past the no-support limit");
// The skirt's bottom is trayA_front_h - pick_lid_skirt_over BY DEFINITION, so
// an assert on that difference cannot fail (revision 10 review, F7). What can
// fail is the overlap input itself, and the real property -- the skirt of the
// built lid reaching below the scalloped wall's top -- is measured on the meshes
// by probes/lid_retention.py (g).
assert(pick_lid_skirt_over >= 3.0,
       "the lid skirt overlaps the scalloped front wall by under 3mm, so it will not hide the scallop");
assert(pick_lid_skirt_bot > label_b_center + label_h / 2 + 2,
       "the lid skirt covers the bay labels");

// No finger notches (D44, revision 11; D22 superseded). Test print 3: the lid comes
// off fine and the user pinches it between thumb and forefinger; nothing is cut
// into or hung from it. It comes off tilted about its back edge or straight up,
// then forward (probes/lid_retention.py (e), (e2), (f), (h)).

// ------------------------------------------------------------
// 8. Fill lid (drops into the hopper mouth, flush with the rim, held by
//    gravity in its recess -- D30)
//
// Revisions 5-7 retained it with two cantilever snap tabs. The first test print
// broke every tab, on the lid and on all ten coupon lids: a tab printed
// standing up bends ACROSS its layer lines, the weakest direction of any FDM
// part, and no engagement value fixes that. The brief only needs the lid to
// stay put when it is set down, so it now simply nests: it drops into the
// recess above the seat ledges with fill_lid_clear all round and rests on
// them, and a lead-in chamfer on its underside finds the recess.
// ------------------------------------------------------------
fill_lid_clear  = 0.30;     // NOT confirmed: test print 1 was a 0.42 maquette (0.13);
                            // fit_section.scad's fill-lid corner checks it full size
fill_ledge_w    = 3.0;
fill_ledge_t    = 2.0;
fill_seat_z     = hopper_rim - lid_t;         // 186.0
fill_lid_seat_gap = 0.15;                     // modelled at mid-slop; a coplanar
                                              // resting contact makes FCL report a
                                              // nonsense penetration depth
                                              // (INCIDENTS.md 2026-08-19)
fill_lid_x      = inner_w     - 2 * fill_lid_clear;
fill_lid_y      = hop_mouth_d - 2 * fill_lid_clear;
fill_lead_in    = 0.6;      // 45 degree chamfer on the lid's underside perimeter
ramp_at_back    = max(rampB(yB_hop1), chuteA_floor(yA_hop1));

// A pull lip on the lid's front edge and a matching notch in the wall in
// front of it (D23). The lid sits flush, so without these the only purchase
// was a fingernail on a 3mm edge. The wall between tray B and hopper B is cut
// down to the seat plane across fill_grip_d, and the lid's plate carries on
// forward across that cut and out over tray B's air, where a fingertip hooks
// under it. The cut stops at the seat plane, so it opens nothing below the
// lid: the hopper stays closed with the lid on.
fill_lip_w      = 30.0;
fill_lip_len    = 8.0;
fill_grip_d     = fill_lip_w + 4.0;                  //  34.0, the wall notch
seat_cut_over   = 0.4;
seat_lip_drop   = 0.2;

assert(fill_lip_len > wall_div + fill_lid_clear + 3.0,
       "the pull lip does not reach past the wall in front of the lid far enough to get a finger under");
assert(fill_lip_w + 2 * fill_lid_clear < fill_grip_d - 2.0,
       "the pull lip is wider than the notch cut for it");
assert(fill_grip_d < bay_w,
       "the grip notch is wider than one bay");
assert(seat_lip_drop > 0 && seat_lip_drop < 0.5,
       "seat_lip_drop must be a small positive offset");
min_rim_w = 1.8;
assert(wall_out - seat_cut_over >= min_rim_w && wall_div - seat_cut_over >= min_rim_w,
       "the seat cut oversteps so far it leaves a rim thinner than min_rim_w");
assert(fill_lid_x < inner_w && fill_lid_y < hop_mouth_d,
       "the fill lid is not smaller than the mouth it drops into");
assert(fill_ledge_w >= 2.5, "the fill-lid seat ledge is too narrow to carry the lid edge");
// What the lid actually bears on: the four bay dividers and the hopper divider,
// cut to fill_seat_z. The perimeter ledges sit seat_lip_drop lower, so the lid
// floats over them and they only catch it if it is dropped in tilted (the
// revision 8 review measured the dividers at 137.99 and the ledges at 137.79).
// (fill_lid_x is defined as inner_w - 2 x fill_lid_clear, so it spans the
// dividers by definition; the assert that said so could not fail. The real
// check is the next but one: the lid is smaller than the mouth.)
assert(fill_ledge_w - fill_lid_clear - fill_lead_in >= 1.5,
       "the lead-in chamfer leaves under 1.5mm of lid over the perimeter ledge");
assert(fill_seat_z - fill_ledge_t > rampB(yB_hop1)
       && fill_seat_z - fill_ledge_t > chuteA_floor(yA_hop1),
       "the seat ledge hangs below a hopper floor -- it would be in the pill path");

// ------------------------------------------------------------
// 9. Joining rails (D5)
// ------------------------------------------------------------
rail_root_w = 3.6;        // D43: 1.5 x wall_div (7 until revision 11)
rail_tip_w  = 6.0;         // 11 until revision 11; flank slope unchanged (0.4)
rail_out    = 3.0;         // 5 until revision 11: about the divider thickness
rail_clear  = 0.40;        // 0.35 -> 0.50 (D31) -> 0.20 (D40) -> 0.215 (D47) -> 0.40 (D51). Test print 3's
                           // coupon (old 5 mm rail): "0" (0.20) best, slightly tight. The D43 slim rail's
                           // coupon (0.265 .. 0.165) was too tight on EVERY stub: a 3.6/6.0 mm dovetail
                           // closes up more in print than the old 7/11 one. 0.40 is a best guess; the D51
                           // coupon brackets it 0.50 .. 0.30 in 0.05 steps.
rail_depth_clear = 0.40;

assert(rail_tip_w > rail_root_w && rail_root_w > 0,
       "rail trapezoid is degenerate -- tip must be wider than root");
assert(rail_clear * 2 < rail_root_w / 2, "rail clearance has eaten the rail root");

rail_z0   = 10.0;
// The male rail's underside is a 45 degree chamfer from the wall face at
// rail_z0 out to full depth rail_out higher: a flat 5 x 9mm underside 10mm
// above the bed drooped on the review's face scan, and a drooped rail bottom
// is exactly what jams the neighbour's groove (revision 7 review, finding 2).
rail_lead_bot = rail_out;
rail_lead = 3.0;
// D43 (revision 11, supersedes D39's numbers): the buttress behind the rail-1
// groove protrudes rail_boss = 3 mm into the bay beyond the side wall's inner face
// (was 7: "the buttress protrudes too far into the front bin", and the
// lock-and-key looked overbuilt). The groove is cut rail_out + rail_depth_clear =
// 3.4 deep into wall_out + rail_boss = 5.8, leaving a SKIN of 2.4 = wall_div, as
// stiff as the dividers (which feel stiff enough at 15% infill). Either side of the
// groove the buttress is rail_boss_margin - rail_clear = 3.8 mm. D39's lesson stands:
// where the pick plane cuts the buttress the skin must not stand as a thin blade,
// so no region under 2 mm may stand over 1 mm tall there (probes/corner_thickness.py).
rail_boss = 3.0;
rail_boss_margin = 4.0;         // buttress beyond the groove tip, each side, in Y
rail_boss_w = rail_tip_w + 2 * rail_boss_margin;   // buttress footprint in Y (14)
// D41 corner beads (revision 11, redesigned after the review): three small half-round ribs
// per bay, radius bead_r (2.5, 5 mm across), bead_len long from the front wall along the floor,
// hemispherical ends. 2.5 because: the beads are for pushing a capsule's end against, and a
// capsule's end cap is 5.5 in radius, so a rib of 2.5 meets it low on the cap (the contact
// normal then points up and out at about 45 degrees, which lifts the end: probes/capsule_corner.py);
// a larger rib becomes a ramp the capsule simply rests on (revision 11's first try, 8 mm).
// bead_len 13 reaches past the line (10.6 mm from the wall along the floor) where a capsule
// in the wedge touches the floor. The pitch is bay_w / 4, so the clear gap between ribs
// is pitch - 2 bead_r = 6.2 mm, narrower than a capsule (11): none wedges between two.
bead_r     = 2.5;           // 0 removes them
bead_len   = 13.0;
bead_fracs = [0.25, 0.5, 0.75];   // across each bay, fraction of the clear width
bead_gap   = bay_w * 0.25 - 2 * bead_r;
assert(bead_r == 0 || (bead_gap < pill_dia && bead_gap > 3.0),
       "the gap between corner beads is not narrower than a capsule, or is under 3mm (D41)");
boss_bevel = 1.0;           // the same bevel on the buttress's back-top edge (D43)
groove_chamfer = 1.0;        // 45 degree bevel round the rail-1 groove's break-out through the plane (H2): the
                            // lip in front of it was a 46 degree knife edge that tore in test prints 1 and 2
rail_skin = rail_boss + wall_out - rail_out - rail_depth_clear;   // 2.4, groove bottom to tray A
// Rail 1's buttress is clipped by the outer silhouette rather than capped at a
// guessed height. Over tray A that silhouette IS the pick plane, so the clip
// lands the buttress top exactly on the shell's own top face -- two coplanar
// surfaces, an edge shared by four faces, and a mesh that reports as having no
// holes while still not being watertight. The clip is therefore taken against
// a silhouette dropped by this much, so the buttress ends strictly inside.
boss_clip_drop = 0.2;
assert(boss_clip_drop > 0 && boss_clip_drop < 0.5,
       "boss_clip_drop must be a small positive offset: 0 puts two faces on one plane");

// Rail 1 sits under tray A, not under tray B. Under tray B it would stand in
// the porch and narrow one lane of an end bay below the single-file rule; tray
// A is a pick pocket, where a 5mm buttress in one corner costs nothing.
rail1_y      = (yA_tray0 + yA_tray1) / 2;                  //  22.8, mid tray A
// A dovetail groove is entered from above, so it has to break out of the top
// of the wall that carries it -- and over tray A that top is the pick plane,
// which is HIGHEST at the groove's back edge. Revision 3 capped this groove at
// the plane's lowest point across the buttress and asserted it must not run
// past the wall: a blind pocket, 4-11mm under the surface along its whole
// length, that no neighbouring module could ever enter (INCIDENTS.md,
// revision 6). The groove now runs 1mm clear of the plane at its own back
// edge; the pick lid covers the opening in use.
rail1_groove_y1 = rail1_y + rail_tip_w / 2 + rail_clear;   //  28.5, groove back edge
rail1_soc_z1 = pickplane(rail1_groove_y1) + 1.0;           // 105.3, out through the plane
// The male on the neighbour stays below ITS OWN wall's lowest point across
// the male's footprint, so it never stands proud of the plane it is under.
rail1_z1     = pickplane(rail1_y - rail_tip_w / 2) - 4.0;  //  89.6
rail2_y      = (yB_wall1 + yB_hop1) / 2;                   // 122.6, mid hopper B
rail2_soc_z1 = hopper_rim + 1.0;                           // 190.0
rail2_z1     = 112.0;

skin_trim_over = 0.4;       // the skin-top trim reaches this far past the groove floor, into the groove's air
// the lowest front-lip top beside the groove (at the tip depth, 0.5 mm in front of the flank, where
// the buttress is clipped boss_clip_drop under the plane or the bevel has taken groove_chamfer - 0.5,
// whichever is deeper) plus one skin thickness, less 0.1
skin_cap_z = pickplane(rail1_y - rail_tip_w / 2 - rail_clear - 0.5) - max(boss_clip_drop, groove_chamfer - 0.5) + rail_skin - 0.1;
rail_sep  = rail2_y - rail1_y;                             //  99.8

assert(rail1_soc_z1 > rail1_z1 + rail_lead && rail2_soc_z1 > rail2_z1 + rail_lead,
       "a rail groove is shorter than its own male plus its lead");
assert(rail1_soc_z1 >= pickplane(rail1_groove_y1) + 0.5
       && rail2_soc_z1 >= hopper_rim + 0.5,
       "a rail groove does not break out of the top of the wall that carries it -- a blind dovetail cannot be entered");
assert(rail1_z1 + rail_lead < pickplane(rail1_y - rail_tip_w / 2),
       "the front male rail stands proud of the pick plane on its own module");
assert(rail1_y + rail_boss_w / 2 < yA_tray1,
       "rail 1's buttress reaches back into the chute mouth");
// rail_skin is wall_out + rail_boss - rail_out - rail_depth_clear and is exactly wall_div today:
// the assert has ZERO margin, on purpose (the skin is as stiff as a divider and no stiffer), so
// any change that thins it fails here; it does not protect against a change that thickens it.
assert(rail_skin >= wall_div - 1e-6,
       "the skin between the rail-1 groove and tray A is thinner than a divider (D43)");
// material left either side of the groove at its widest (its tip, grown by rail_clear)
rail_boss_side = rail_boss_margin - rail_clear;      // 3.8
assert(rail_boss_side >= wall_div + 1.0 - 1e-6,
       "the buttress leaves under a divider plus 1mm of material either side of the rail groove at its widest (D43); measured on the mesh by probes/corner_thickness.py");
assert(bay_w - rail_boss >= pill_len,
       "the rail buttress narrows an end bay below one pill length");
assert(rail_sep > 50, "the two rails are too close together to resist yaw");

// Retention lug and stop block (D32, D34, D38; face geometry after the revision
// 10 review). Two lugs hang from the lid's underside into the END bays of
// tray A, each directly behind a STOP BLOCK in the front corner of the bay. The
// stop faces are PERPENDICULAR TO THE PICK PLANE (normal along the up-slope
// direction) on both the lug's front face and the block's back face:
//   * down-slope the lid moves along that normal and stops after pick_lug_clear
//     (0.5 mm) of travel, with the faces parallel and flat on each other;
//   * lifted by the front edge the lid pivots about its back edge and the lug
//     moves along the plane's NORMAL, i.e. along the faces, not into them. The
//     first version had a vertical stop face, which the swinging lug drove into
//     at 0.5-2 degrees of tilt and jammed (review of revision 10, F1).
// The block is fused to the side wall and the front wall; its top is the pick
// plane, so the contact face meets the top surface at 90 degrees and there is no
// knife edge. The face prints facing up and back (about 46 degrees above
// horizontal), so it needs no support and sheds pills; the lug's face stands
// vertical in the lid's print orientation.
pick_lug_t     = 4.0;       // thickness in X (3 until the review: a cantilever across layers)
pick_lug_clear = 0.5;       // along the slope, lug face to stop face; also to the side wall in X
pick_lug_len   = 4.0;       // along the slope, front face to back face
pick_lug_d     = 7.0;       // perpendicular to the plate, below its underside
pick_lug_chamfer = 1.0;     // lead-in chamfer on the tip's X edges
pick_stop_w    = pillar_w - 0.4;   // the block is a hair narrower than the pillar, so its side face does not
                            // lie on the scallop cut's face (a coplanar boolean)
stop_trim_lift = 0.05;      // the front wall over the pillar is trimmed to this far above the block's clipped top
pick_filler_drop = 0.5;     // the filler's top at the side wall, under the stop block's corner P1
pick_filler_inset = 0.4;    // the filler ends this far inside the buttress's inner face
pick_stop_off  = 1.0;       // where the stop face meets the plane, behind the front wall's inner face
pick_stop_depth = 9.0;      // how far down (perpendicular) the stop face runs from the plane
pick_stop_y    = yA_tray0 + pick_stop_off;                              //   3.8
// the stop face's position along the slope, measured from the lid frame's origin
// (the underside at y = 0), and the lug's faces from it
pick_stop_s    = pick_stop_y / cos(pick_lid_slope) - pick_lid_gap * sin(pick_lid_slope);
pick_lug_s0    = pick_stop_s + pick_lug_clear;
pick_lug_s1    = pick_lug_s0 + pick_lug_len;
pick_lug_x_left  = wall_out + pick_lug_clear;                           //   3.3, low-X face (wall side)
pick_lug_x_right = module_w - wall_out - pick_lug_clear - pick_lug_t;   // 232.7, low-X face (interior side)
rail1_boss_y0  = rail1_y - rail_boss_w / 2;                             //  14.3, buttress front face
// Contact depth: the lug's depth below the plane, perpendicular to it (the
// underside floats pick_lid_gap above the plane). The stop block's top is
// boss_clip_drop under the plane; the face is perpendicular, so that costs
// only the first boss_clip_drop x cos(slope).
pick_lug_engage = pick_lug_d - pick_lid_gap * cos(pick_lid_slope);
pick_stop_back_y = pick_stop_y + pick_stop_depth * sin(pick_lid_slope);  // where the face ends, 10.0
// The lug's lowest, rearmost corner in body coordinates, and the air between it
// and tray A's pill line there.
pick_lug_corner_y = pick_lug_s1 * cos(pick_lid_slope) + pick_lug_d * sin(pick_lid_slope);
pick_lug_corner_z = pickplane_front + pick_lid_gap + pick_lug_s1 * sin(pick_lid_slope)
                  - pick_lug_d * cos(pick_lid_slope);
pick_lug_air   = pick_lug_corner_z
               - (trayA_pile_front + (pick_lug_corner_y - yA_tray0) * tan(repose_deg));
// Material behind the contact face along the slope, at the top of the face (where
// the block is thinnest): from the face back to the front wall's outer face.
pick_stop_top_thick = pick_stop_y / cos(pick_lid_slope);

assert(pick_lug_engage >= 5.0,
       "the lug engages the stop face by under 5mm, measured perpendicular to the plane (D38)");
assert(pick_stop_depth >= pick_lug_d + 1.0,
       "the stop face does not run 1mm deeper than the lug that bears on it (D38)");
assert(pick_stop_w >= pick_lug_clear + pick_lug_t + 1.0,
       "the stop block does not extend 1mm beyond the lug it stops (D38)");
assert(pick_lug_corner_y + 2.0 <= rail1_boss_y0,
       "a pick-lid lug's lowest corner is within 2mm of the rail-1 buttress in front of which it hangs");
assert(pick_stop_back_y + 2.0 <= rail1_boss_y0,
       "the stop block's lower back face is within 2mm of the rail-1 buttress");
assert(pick_lug_air > 10,
       "a pick-lid lug hangs within 10mm of tray A's pill line");
assert(pick_lug_t + pick_lug_clear < bay_w / 4,
       "a pick-lid lug takes too much of its bay");
assert(pick_lug_chamfer < pick_lug_t / 2 - 0.5,
       "the lug's lead-in chamfers leave under 1mm of its tip");
assert(pick_stop_top_thick >= 1.5,
       "the stop block leaves under 1.5mm of material behind the contact face at its top (knife edge, D38/F6)");
// pick_lug_clear is the lid's travel to first contact along the slope BY
// CONSTRUCTION (the faces are perpendicular to it). The travel is not asserted
// here because the formula is the definition; probes/lid_retention.py measures
// it on the meshes.

// The "FRONT" mark on the skirt's outer face (D38): embossed, raised by
// pick_front_h, readable from the front with the lid on. Printed with the plate
// on the bed the skirt leans out at 43.8 degrees and the relief is 0.6mm tall:
// the letters' TOP edges face down at 46.2 degrees from vertical, 1.2 past the
// 45 degree rule, over a 0.6mm step (about 0.2mm of overhang per layer). Accepted
// and listed, not fixed: about 3 mm2 in all.
pick_front_text = "FRONT";
pick_front_size = 9.0;
pick_front_h    = 0.6;

// ------------------------------------------------------------
// 10. Cosmetic / ergonomic
// ------------------------------------------------------------
// Label recesses: section 4c, beside the scalloped front wall they sit under.

tray_fillet_r = 2.0;        // vertical fillets where dividers meet tray A's front wall (revision 11)
tray_fillet_top_under = 2.0;   // D48: tray B's divider gussets stop this far under the wall's top plane at its face
fillet_r  = 2.0;            // internal: every flow-void corner (opening pass)

// External edges (D27). Nothing a hand or a sleeve meets is left sharp: the
// four vertical corners of the body, its top edges, both lids' plan corners
// and the fill lid's top perimeter. Chosen small enough that no wall thins
// past its own thickness: 1.5 on a 2.4 wall top leaves 0.9 of flat.
edge_r_top = 1.5;           // body's outer rounds (D48): ONE ball radius for every outer edge. The body's
                            // silhouette, extruded, is dilated by a ball of this radius (Minkowski), so the
                            // top edges in section, the four vertical corners and the side faces' perimeter
                            // are one surface. Revisions 7 to 11 cut the vertical corners separately at
                            // corner_r 1.2 (never equal to this one: separate cutters on one tangent line
                            // left zero-area slivers, INCIDENTS.md); a single ball has no second tangent.
lid_edge_r = 2.0;           // lids' plan-view corners
lid_chamfer = 1.0;          // fill lid top perimeter; pick lid plate x-end edges
lid_round   = 1.0;          // pick lid plate front/back edges and skirt bottom, in
                            // section (45 degree chamfers -- the plate's top goes on the bed). MUST be under half the plate's thickness:
                            // an opening pass erodes by the radius first, and at
                            // exactly half the section collapses to a line (it
                            // did, at 1.5 on a 3.0 plate -- standalone it survived
                            // on floating point, through use<> it vanished and the
                            // assembly had no pick lid at all; revision 7)
assert(lid_round < lid_t / 2 - 0.3 && lid_round < (pick_lid_hook_t - pick_lid_clear) / 2 - 0.3,
       "lid_round erodes the pick lid's plate or skirt to nothing");

// D48, the edge pass (revision 12). The audit of every edge class is the table in
// calculations.md "Revision 12: the edge pass".
// Bed contact: a 45 degree chamfer round every perimeter that lies on the bed, against
// PETG's elephant foot (the first layers squash outward by about 0.2 to 0.3).
bed_chamfer     = 0.5;      // body base perimeter and foot-pad recess mouths
// Scalloped front wall: the top edge of each scallop's floor, on the front face and on
// the tray side, is a 45 degree chamfer that follows the scallop outline and fades to
// nothing up the scallop's rounded corners.
scallop_chamfer = 0.7;
// The fill mouth's rim (the opening both hoppers share), inside edge, all four sides.
mouth_chamfer   = 0.45;  // the front rim wall is wall_div wide and loses edge_r_top to the outer round: 0.45 keeps 0.45 of flat. NOT 0.4: that is seat_cut_over, and the cone's corner then crossed the seat cuts' corner lines and left four zero-volume shards
// Pick lid (print face down is the plate's top, already chamfered 1.0 on all four sides, which is the
// bed chamfer): the underside's x-end edges, and the skirt's outer end edges where the lid is pinched.
pick_under_chamfer = 0.8;   // plate x-end underside edges (the end face keeps lid_t - lid_chamfer - this = 1.2 of flat)
pick_skirt_chamfer = 1.0;   // skirt outer end edges (vertical in the assembly)
// Fill lid: the pull lip's underside perimeter, where a fingertip hooks under it
fill_lip_chamfer = 0.5;
// The cubby's mouth in the back face: the three straight edges (both sides and the lip's top).
cubby_chamfer   = 0.5;   // the side walls are wall_out wide and lose edge_r_top to the outer round: 0.5 keeps 0.8 of flat
cubby_fillet_r  = 2.0;   // the cubby's inside corners (the same 2 mm as every flow void), rounded in three dimensions

assert(edge_r_top < wall_div - 0.5,
       "the top-edge round is deeper than the thinnest wall it runs along");
assert(edge_r_top <= wall_out - 1.0,
       "the outer round is too large for the wall: where the adjoining wall is cut away it feathers the side wall's end");
assert(lid_chamfer < lid_t - 1.0, "the lid chamfer leaves under 1mm of plate");

// Recesses in the base for stick-on rubber feet (D24): a bench unit that is
// slid about on rails and bumped while pouring should not skate. Under the
// back pair the base is the cubby floor, so the recess leaves base_t less
// foot_pad_depth of it.
foot_pad_d     = 10.0;
foot_pad_depth = 1.0;
foot_pad_inset = 15.0;

assert(base_t - foot_pad_depth >= 1.5,
       "a foot-pad recess leaves under 1.5mm of floor");

// ------------------------------------------------------------
// 11. Scale -- 1.0 for the real module, <1 for a bench maquette.
// Applied in layout.scad only, so every dimension above stays true.
// ------------------------------------------------------------
model_scale = is_undef(MODEL_SCALE) ? 1.0 : MODEL_SCALE;

echo(str("bay_w = ", bay_w, "   module = ", module_w, " x ", module_d, " x ", module_h));
echo(str("tray A rim ", trayA_rim, " / tray B floor ", trayB_floor,
         " / tray B rim ", trayB_rim, "  -> pick plane ", pick_lid_slope, " deg"));
echo(str("hopper A floor ", chuteA_floor(yA_hop0), " .. ", chuteA_floor(yA_hop1),
         "   hopper B floor ", rampB(yB_wall1), " .. ", rampB(yB_hop1)));
echo(str("fill mouths: hopper B ", mouthB_w, " x hopper A ", mouthA_w,
         " = ", mouth_ratio, " : 1   (divider leans ", hop_lean_deg, " deg)"));
echo(str("tray A reach below the lid plane: ", pickplane(yA_tray0) - outletA_top
         + (yA_tray1 - yA_tray0) * tan(repose_deg), " front .. ",
         pickplane(yA_tray1) - outletA_top, " back"));
echo(str("90-day size-00 charge = ", charge_ml, " mL; porch ceiling flat at ", porch_ceil_z));
echo(str("cubby: ", inner_w, " wide x ", cubby_d, " deep x ",
         cubby_h_front, " .. ", cubby_h_back, " tall; lip ", cubby_lip_h,
         " leaves ", cubby_h_back - cubby_lip_h,
         " clear above it; deck ", cubby_ceil, " at the back .. ",
         chuteA_floor(cubby_y0) - cubby_ceil_z(cubby_y0), " at the front"));
echo(str("rail 1 groove: open from z ", rail_z0, " to ", rail1_soc_z1,
         " through the plane at ", pickplane(rail1_groove_y1),
         "; skin behind it ", rail_skin, "; tray A floor ", trayA_tilt_deg, " deg, ",
         base_z, " at the front wall .. ", z_foot, " at the chute foot; pile depth at the front wall ",
         trayA_pile_front - base_z, " (30 deg repose), ",
         outletA_top - tray_d * tan(25) - base_z, " (25), ", outletA_top - tray_d * tan(35) - base_z, " (35)"));
echo(str("pick lid retention: stop face at y ", pick_stop_y, " on the plane, ", pick_stop_depth,
         " deep; lug ", pick_lug_t, " x ", pick_lug_len, " x ", pick_lug_d, ", clearance ", pick_lug_clear,
         " along the slope; engagement ", pick_lug_engage, " mm perpendicular; lug corner y ",
         pick_lug_corner_y, " vs buttress ", rail1_boss_y0, "; air ", pick_lug_air,
         "; mouth A minimum ", mouthA_min, "; footprint ", module_w + rail_out, " x ", module_d, " x ", module_h));
echo(str("vault: gable ", vault_deg, " deg, face ", vault_face_from_vertical,
         " from vertical; chute clear ", chute_clear - vault_down, " at the edges, ",
         chute_clear + vault_up, " at the ridge; hopper B foot ", rampB_foot,
         ", outlet top ", outletB_top, ", rim margin ", trayB_rim - outletB_top,
         "; tray B pile at the wall ", trayB_pile_front, " vs wall top ", pickplane(yB_tray0),
         " (margin ", trayB_pile_margin, "); lug air ", pick_lug_air));
echo(str("tray A front wall ", trayA_front_h, " over a pill line of ", trayA_pile_front,
         " -> reach over the wall ", trayA_front_h - trayA_pile_front,
         " mm; lid skirt ", pick_lid_hook_h, " mm down to ", pick_lid_skirt_bot));
