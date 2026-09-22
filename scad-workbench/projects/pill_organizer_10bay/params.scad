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
void_top_over = 1.0;        // how far every open-topped void runs PAST the
                            // outer surface it opens through. A void whose top
                            // edge lies exactly on the shell's top face is a
                            // coplanar boolean; it held until a third cut broke
                            // through that face (INCIDENTS.md, revision 6)

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
tray_d      = 28.0;         // pick tray depth in Y, both rows
trayB_h     = 38.0;         // tray B interior height, floor to rim
outlet_h    = 28.0;         // gap under tray B's feed wall (row B's outlet);
                            // 30 before the vault (D26) lifted the ramp foot
ramp_deg    = 40;           // ramp and chute angle from horizontal (D11)
// The porch was 20 degrees (D12). Pills reach tray A by flowing OVER the
// stagnant wedge the porch carries, and that wedge's surface is by
// construction at the angle of repose -- so the last 30mm to tray A never had
// the 10 degree margin the ramp has. What the porch angle does control is how
// much throat is left over the wedge if the real repose is higher than the 30
// degree estimate: at 20 degrees a 35 degree repose closed the throat to
// 25.8mm, under one pill length. At 25 it stays 28.9. (D20)
porch_deg   = 25;           // chute floor angle under tray B only (D12, D20)
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
// 18 mL per bay. The porch under tray B is not vaulted -- the rib carries it.
// ------------------------------------------------------------
vault_up    = 6.0;
vault_down  = 6.0;
vault_lead  = 2.0;          // the ridge starts this far behind the porch end
vault_slope = (vault_up + vault_down) / (bay_w / 2);            // tan of the gable
vault_deg   = atan(vault_slope);                                //  29.2
vault_face_from_vertical = 90 - atan(sqrt(pow(vault_slope, 2) + pow(ramp_tan, 2)));  // 44.8
vault_top_over = 2.0;       // how far the vault's solid reaches up into the deck
vault_embed = 1.0;          // how far each roof half reaches INTO its divider or
                            // side wall. Less than weld_embed because the side
                            // walls also carry the rail roots' weld_embed from
                            // outside, and 1.5 + 1.5 does not fit in 2.8
vault_y0    = yB_tray1 + vault_lead;                            //  63.2, ridge starts
vault_y1    = yB_hop1 - 0.6;                                    // 133.0, ridge ends
vault_roof_y0 = yB_tray1 + vault_lead / 2;                      //  62.2, the added solid starts
vault_roof_y1 = yB_hop1;                                        // 133.6, and ends, inside the wall between the hoppers
function chuteA_ridge(y) = chuteA_ceil(y) + (y > vault_y0 && y < vault_y1 ? vault_up : 0);

assert(vault_face_from_vertical <= 45.0,
       "the vaulted chute ceiling is still past the 45 degree overhang limit -- raise vault_up + vault_down");
assert(chute_clear - vault_down > pill_len + 2 && chute_clear - vault_down >= 2 * pill_dia,
       "the chute at the bay edges, under the vault's low side, is too low for a pill");
assert(vault_top_over < chute_ceil,
       "the vault's solid reaches through the deck into hopper B's floor");
assert(vault_embed + weld_embed < wall_out - 0.2,
       "the vault roof's embed and the rail root's embed meet inside the side wall");
assert(vault_roof_y0 > yB_tray1 && vault_roof_y0 < vault_y0 && vault_y1 < vault_roof_y1,
       "the vault's added solid must start before the ridge void and end after it, each strictly, or their faces coincide");

// Tray B sits one slab above the chute ceiling at the porch's end -- which is
// the whole point of the porch, because that is where the ceiling is lowest.
trayB_floor = chuteA_ceil(yB_tray1) + chute_ceil;        //  56.18
trayB_rim   = trayB_floor + trayB_h;                     //  94.18
// Hopper B's ramp rides one deck above the vault's RIDGE, so it starts
// vault_up above tray B's floor: a 6mm riser at the tray's back wall that
// pills drop off (D26). The outlet top rises with it.
rampB_foot  = trayB_floor + vault_up;                    //  62.18
outletB_top = rampB_foot + outlet_h;                     //  90.18
function rampB(y) = rampB_foot + (y - yB_tray1) * ramp_tan;

assert(trayB_rim - outletB_top >= 3.0,
       "hopper B's outlet top is within 3mm of tray B's rim -- pills could ride out under the lid");

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
trayA_rim       = 43.0;
pickplane_front = trayA_rim;
function pickplane(y) = pickplane_front
                      + (y / yB_tray1) * (trayB_rim - pickplane_front);

// Row A's outlet is the chute's own section: at tray A the ridge stands
// chute_clear above the floor and the ceiling is already a chamfer.
outletA_top = base_z + chute_clear;                      //  39.0
// Tray A is fed by that mouth, so its pill surface is not flat: it peaks there
// and falls forward at the angle of repose. That surface, not the tray's depth,
// is what the front wall has to retain (D17).
trayA_pile_front = outletA_top - tray_d * tan(repose_deg);   //  22.8

hopper_rim = 141.0;
module_h   = hopper_rim;

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
hopwall_z0 = chuteA_ceil(yA_hop0);                       // 112.8, where the wall springs
function hopwall_A(z) = yA_hop0
                      - hopA_lean * max(0, z - hopwall_z0) / (hopper_rim - hopwall_z0);
function hopwall_B(z) = hopwall_A(z) - wall_div;

hop_lean_deg  = atan(hopA_lean / (hopper_rim - hopwall_z0));   // 17.3
mouthB_w      = hopwall_B(hopper_rim - lid_t) - yB_wall1;             // 62.1
mouthA_w      = yA_hop1 - hopwall_A(hopper_rim - lid_t);              // 39.9
mouth_ratio   = mouthB_w / mouthA_w;                           // 1.56, about 3:2

assert(hop_lean_deg < 40,
       "the hopper divider leans past the FDM overhang band -- its front face would need support");
assert(mouth_ratio > 1.3 && mouth_ratio < 1.9,
       "the two fill mouths are no longer within the 3:2 band the lean exists to hit");
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
assert(porch_deg < ramp_deg,
       "the porch is not shallower than the ramp -- it is doing nothing");
assert(module_d <= max_part_y && module_h <= max_part_z,
       "the module no longer fits the usable bed");

tray_step = trayB_rim - trayA_rim;                       //  49.06

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
trayA_front_h   = 30.0;
trayA_scallop_r = 6.0;
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
label_z_center  = 13.0;     // lower strip, centre height on the front face
labelB_z0 = chuteA_ceil(yA_tray1);                       //  39.0, chute mouth top
labelB_z1 = pickplane(yA_tray1);                         //  pick plane over that wall
label_b_center = (labelB_z0 + labelB_z1) / 2;
label_cut_over  = 1.0;      // the cut starts this far OUTSIDE the face, never inside it

assert(label_w < bay_w - 4,
       "the label recess is wider than the bay leaves room for");
assert(labelB_z1 - labelB_z0 > label_h + 6,
       "the wall between the trays is too short to carry a tape label");
assert(min(wall_out, wall_div) - label_z >= 1.8,
       "the label recess is cut so deep it leaves a wall thinner than 1.8mm");
assert(label_z_center - label_h / 2 > 2,
       "the lower label recess runs off the bottom of the front face");

assert(trayA_front_h > trayA_pile_front + 5,
       "the scalloped front wall is at or under the pill line -- row A would spill out of its own front");
assert(trayA_front_h < trayA_rim - 6,
       "the scallop is too shallow to be worth cutting");
assert(trayA_scallop_r < (bay_w - 2 * trayA_scallop_r) / 2,
       "the scallop radius has eaten the flat part of the scallop");

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
cubby_h_front = cubby_ceil_z(cubby_y0) - base_t;
// A retaining lip across the opening, so whatever is in there stays in there
// when the module is slid around the bench. You reach in over it rather than
// sliding things out. It is simply the bottom of the back wall, left uncut.
// Level with the cubby's shallow end, so the forward part is a shelf you can
// see into, not a well you fish in (D21; the 42 of revision 5 stood 12mm
// above a 30mm shallow end).
cubby_lip_h = 30.0;

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
assert(cubby_lip_h <= cubby_h_front + 0.5,
       "the retaining lip stands above the cubby's own shallow end -- the front becomes a well");
assert(cubby_lip_h < cubby_h_back * 0.6,
       "the retaining lip takes more than 60% of the cubby's opening height");

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
pick_lid_gap    = 0.2;   // vertical float above the pick plane; keeps the pair a
                         // near miss rather than a coplanar resting contact
// Not a hook any more but a skirt (D17): it hangs down the OUTSIDE of the front
// face, past the scalloped wall, and closes the scallops. It also does what the
// old 7mm hook did -- stop the lid sliding down its own plane -- because it
// cannot pass the front face.
pick_lid_skirt_over = 6.0;                       // overlap onto the scalloped wall
pick_lid_hook_h = pickplane_front + pick_lid_gap
                - (trayA_front_h - pick_lid_skirt_over);       //  18.2
pick_lid_skirt_bot = pickplane_front + pick_lid_gap - pick_lid_hook_h;   //  24.0
pick_lid_tv  = lid_t / cos(pick_lid_slope);

assert(pick_lid_slope > 17.0,
       "the pick plane is shallow enough for friction to hold the lid, so the hook is over-designed");
assert(pick_lid_hook_h > 4.0,
       "the front hook is too shallow to retain the lid on its slope");
assert(pick_lid_skirt_bot < trayA_front_h - 3.0,
       "the lid skirt does not reach far enough down to overlap the scalloped front wall");
assert(pick_lid_skirt_bot > label_z_center + label_h / 2 + 2,
       "the lid skirt covers the bay labels");

// Finger notches in the skirt (D22). The lid comes off with a straight lift --
// its back edge is 0.35mm from the wall behind tray B, so tilting it about
// that edge jams the top-back corner after 5 degrees -- and a 229mm plate
// hung 0.35mm off the front face gives nothing to lift by. Two rounded slots
// in the skirt's bottom edge, one under each hand, leave a 3mm ceiling to
// hook a fingertip under. Their top runs a little above the scalloped wall,
// so the notch shows a sliver of tray, but stays above the pill line.
pick_notch_w   = 22.0;
pick_notch_h   = 8.0;
pick_notch_r   = 4.0;
pick_notch_top = pick_lid_skirt_bot + pick_notch_h;              //  32.0
pick_notch_x   = [bay_center_x(1), bay_center_x(bays - 2)];      // bays 2 and 4

assert(pick_notch_top > trayA_pile_front + 5,
       "a skirt notch opens the front below the pill line -- pills would roll out through it");
assert(pick_notch_top < trayA_front_h + 3,
       "a skirt notch runs so far above the scalloped wall that it stops closing the scallop");
assert(pick_notch_w < bay_w - 6 && pick_notch_r * 2 < pick_notch_w,
       "a skirt notch is wider than a bay's share of the skirt, or its rounding has eaten it");

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
// 12, not 10 (D23). The tab's barb pocket and the seat-ledge relief for the
// same tab are two separate cuts in the same 2.4mm wall; in revision 5 they
// were 0.7mm apart, so the barb latched on a 0.7 x 1.0mm sliver of PLA. The
// pocket now sits a full fill_catch_t below the relief -- see the assert.
fill_tab_drop   = 12.0;
fill_tab_barb   = 1.1;
// Each tab's outer face sits this far INSIDE the plate's edge. The tab reaches
// 1mm up into the plate for a volumetric weld; flush with the edge, that 1mm
// put the tab's outer face on the plate's own edge face, and the union came
// out non-manifold (revision 7). The barb still projects fill_tab_barb past
// the plate edge, so the engagement is unchanged.
fill_tab_inset  = 0.2;
fill_tab_engage = fill_tab_barb - fill_lid_clear;
fill_tab_ramp   = 3.0;
// The barb's retaining face is no longer flat (D23). A flat face against a
// flat pocket ceiling is a permanent snap: it comes out by breaking. At 35
// degrees the lid still needs a deliberate pull to release, but a pull
// releases it, every refill, without fatiguing the tab.
fill_tab_return_deg = 35;
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
assert(fill_tab_return_deg >= 30 && fill_tab_return_deg <= 50,
       "the barb return angle is outside the releasable-but-retained band");

// A pull lip on the lid's front edge and a matching notch in the wall in
// front of it (D23). The lid sits flush, so without these the only purchase
// was a fingernail on a 3mm edge through an 18mm slot. The wall between tray
// B and hopper B is cut down to the seat plane across fill_grip_d, and the
// lid's plate carries on forward across that cut and out over tray B's air,
// where a fingertip hooks under it. The cut stops at the seat plane, so it
// opens nothing below the lid: the hopper stays closed with the lid on.
fill_lip_w      = 30.0;
fill_lip_len    = 8.0;
fill_grip_d     = fill_lip_w + 4.0;                  //  34.0, the wall notch
seat_cut_over   = 0.4;
seat_lip_drop   = 0.2;
// The seat-ledge relief for each tab oversteps INTO the wall by this much in
// Y so its face never lands on the wall's own face (the coplanar-touch class).
fill_notch_over = 1.0;
fill_notch_bot_z = fill_seat_z - fill_ledge_w - fill_notch_over;    // 134.0
// What the front barb actually latches on: the material between the top of
// its pocket and the bottom of the relief notch above it.
fill_catch_t    = fill_notch_bot_z - (fill_tab_pocket_z + fill_tab_pocket_h);  // 2.7

assert(fill_catch_t >= 2.0,
       "under 2mm of wall between the barb pocket and the seat-ledge relief -- the snap latches on a sliver");
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
rail1_y      = (yA_tray0 + yA_tray1) / 2;                  //  16.8, mid tray A
// A dovetail groove is entered from above, so it has to break out of the top
// of the wall that carries it -- and over tray A that top is the pick plane,
// which is HIGHEST at the groove's back edge. Revision 3 capped this groove at
// the plane's lowest point across the buttress and asserted it must not run
// past the wall: a blind pocket, 4-11mm under the surface along its whole
// length, that no neighbouring module could ever enter (INCIDENTS.md,
// revision 6). The groove now runs 1mm clear of the plane at its own back
// edge; the pick lid covers the opening in use.
rail1_groove_y1 = rail1_y + rail_tip_w / 2 + rail_clear;   //  22.65, groove back edge
rail1_soc_z1 = pickplane(rail1_groove_y1) + 1.0;           //  62.9, out through the plane
// The male on the neighbour stays below ITS OWN wall's lowest point across
// the male's footprint, so it never stands proud of the plane it is under.
rail1_z1     = pickplane(rail1_y - rail_tip_w / 2) - 4.0;  //  48.5
rail2_y      = (yB_wall1 + yB_hop1) / 2;                   //  98.6, mid hopper B
rail2_soc_z1 = hopper_rim + 1.0;                           // 142.0
rail2_z1     = 112.0;

rail_sep  = rail2_y - rail1_y;                             //  81.8

assert(rail1_soc_z1 > rail1_z1 + rail_lead && rail2_soc_z1 > rail2_z1 + rail_lead,
       "a rail groove is shorter than its own male plus its lead");
assert(rail1_soc_z1 >= pickplane(rail1_groove_y1) + 0.5
       && rail2_soc_z1 >= hopper_rim + 0.5,
       "a rail groove does not break out of the top of the wall that carries it -- a blind dovetail cannot be entered");
assert(rail1_z1 + rail_lead < pickplane(rail1_y - rail_tip_w / 2),
       "the front male rail stands proud of the pick plane on its own module");
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
// Label recesses: section 4c, beside the scalloped front wall they sit under.

fillet_r  = 2.0;            // internal: every flow-void corner (opening pass)

// External edges (D27). Nothing a hand or a sleeve meets is left sharp: the
// four vertical corners of the body, its top edges, both lids' plan corners
// and the fill lid's top perimeter. Chosen small enough that no wall thins
// past its own thickness: 1.5 on a 2.4 wall top leaves 0.9 of flat.
corner_r   = 3.0;           // body's vertical outer corners
edge_r_top = 1.5;           // body's top edges (OUTER's convex corners)
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

assert(edge_r_top < wall_div - 0.5,
       "the top-edge round is deeper than the thinnest wall it runs along");
assert(corner_r > wall_out && corner_r < 6,
       "the corner round should be a little larger than the wall so the inner corner stays sharp, and not so large it eats the rail zone");
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
echo(str("90-day size-00 charge = ", charge_ml, " mL; porch lane ", rib_lane, " mm"));
echo(str("cubby: ", inner_w, " wide x ", cubby_d, " deep x ",
         cubby_h_front, " .. ", cubby_h_back, " tall; lip ", cubby_lip_h,
         " leaves ", cubby_h_back - cubby_lip_h,
         " clear above it; deck ", cubby_ceil, " at the back .. ",
         chuteA_floor(cubby_y0) - cubby_ceil_z(cubby_y0), " at the front"));
echo(str("rail 1 groove: open from z ", rail_z0, " to ", rail1_soc_z1,
         " through the plane at ", pickplane(rail1_groove_y1),
         "; fill catch ", fill_catch_t, " mm; porch throat at repose ",
         chute_clear - porch_run * (tan(repose_deg) - porch_tan), " / at 35 deg ",
         chute_clear - porch_run * (tan(35) - porch_tan)));
echo(str("vault: gable ", vault_deg, " deg, face ", vault_face_from_vertical,
         " from vertical; chute clear ", chute_clear - vault_down, " at the edges, ",
         chute_clear + vault_up, " at the ridge; hopper B foot ", rampB_foot,
         ", outlet top ", outletB_top, ", rim margin ", trayB_rim - outletB_top));
echo(str("tray A front wall ", trayA_front_h, " over a pill line of ", trayA_pile_front,
         " -> reach over the wall ", trayA_front_h - trayA_pile_front,
         " mm; lid skirt ", pick_lid_hook_h, " mm down to ", pick_lid_skirt_bot));
