# Final QA audit, pill_organizer_10bay rev 15 (e8f5799), before the 27 h PETG print

Auditor: deep tier. Scope: the user's three slicer close-ups, then a full sweep of the body, pick lid and fill
lid for sharp convex edges, sub-mm steps, unfilleted concave pill corners and anything else that looks wrong.
No design file was edited. F1 to F8 were prototyped in a scratch copy and pass every gate (section 4).

Scratch (not in the repo, purged by macOS eventually; copy anything worth keeping):
`QA=/private/tmp/claude-501/-Users-mhm-dev-Skillz/c749e0bd-0e4d-42aa-a3b4-78e720c4e9dc/scratchpad/qa`

- `$QA/qa_proto.patch`: unified diff of `params.scad` and `parts/body.scad` that implements F1 to F8 (lines marked `QA proto`)
- `$QA/proto2/`: the patched project copy. Its probes ran against it.
- `$QA/stepscan.py`, `$QA/clus.py`: section step scanner (finds parallel faces offset 0.02 to 1.0 mm). Use it as the acceptance gate: `python3 stepscan.py body.stl z 1 189 1.0 > s.txt; python3 clus.py s.txt`
- `$QA/sharp.py`: dihedral-angle edge chains (convex and concave, over a threshold)
- `$QA/meshcheck.py`: watertight, body count, volume, bbox, short edges

## 1. Verdict

Not ready as is. The three things the user saw are real and unintended: they are coplanar-avoidance offsets
(0.4, 0.4, 0.3, 0.2, 0.155 mm) and a fillet that stops 1 mm short of the scallop. All of them can be brought to
0.05 mm or less (below the slicer's resolution) without touching any function. Two more defects of the same
kind turned up (F4 knife edge, F5 tray B gusset ledges). The fixes are about 120 lines in two files.

## 2. The user's three close-ups, explained

| Close-up | What it is | Cause in code | Intended? |
|---|---|---|---|
| (a) notch, sharp vertical cut and small ledge where a divider meets the scalloped front wall | 1. The scallop cut oversteps 0.4 mm into each divider and runs 1.0 mm behind the wall (y 2.8 to 3.8), leaving a vertical 0.4 mm cut from the end of the r 6 arc (z 58.9) up to the pick plane (z 80.6). 2. The divider / front-wall fillet (`tray_fillet_r` 2) has a flat top at z 54.0 (`trayA_front_h - 1.0`), a 2 x 2 mm quarter ledge 0.6 to 1.0 mm under the chamfered scallop edge. 3. From z 54 up to the arc the corner is a bare 90 degree inside corner (8.2 mm chain). 4. The tray-side `scallop_chamfer` stops 0.1 mm short of the bay side. | `front_scallop_cut()` with `scallop_over` 0.4, cutter y to `wall_out + 1`; `front_fillets()` z1 = `trayA_front_h - 1.0`; `scallop_chamfer_cuts()` a/b | No. Side effects of avoiding coplanar faces |
| (b) thin vertical strip along the divider near the front wall | The same 0.4 mm overstep seen face on: two parallel faces 0.40 mm apart, joined by a step face at y = 3.8, z 58.9 to 80.6. Present on both faces of all 4 dividers (8 places). | `scallop_over` = 0.4 | No |
| (c) darker block beside a lighter strip, front wall stepping in thickness | 1. G7 trim: the front wall over the pillar is cut to plane - 0.155 and the stop block to plane - 0.2, while the side wall top stays on the plane: a 0.155 to 0.2 mm step along x = 2.8 (and 237.2) for y 0 to 10. The lighter strip is the side wall's 1.3 mm flat beside the outer round. 2. The stop block is 0.4 mm narrower than the pillar (x 8.4 vs 8.8): a 0.4 mm step from z 55 to 78. 3. The filler is 0.3 mm narrower than the block (x 8.1 vs 8.4): a 0.3 mm step from z 9 to 68. 4. The rail-1 buttress next to it is also clipped 0.2 under the plane (F13). | `stop_trim()`, `stop_trim_lift`, `boss_clip_drop` on `stop_blocks()`; `pick_stop_w = pillar_w - 0.4`; filler `xe = wall_out + pick_stop_w - 0.3` | No |

Evidence: sections in section 5. Renders `$QA/A_feature_a_junction.png`, `$QA/B_feature_b_divider_step.png`,
`$QA/C_feature_c_pillar_topdown.png`, `$QA/c3_endbay_left_inside.png`, `$QA/a1_div1_junction.png`.
After the fix: `$QA/P_A_junction_after.png`, `$QA/P_C_pillar_after.png`, `$QA/P_endbay_inside_after.png`,
`$QA/P3_nose_after.png` (compare `$QA/A0_nose_before.png`).

## 3. Defect list

Severity: High = the user flagged it or it reads as a mistake on the print. Medium = a sharp or fragile edge,
or the same defect class elsewhere. Low = hidden or minor, fix if cheap.

### F1 (High) Divider face step and notch at the scallop (close-ups a, b)
- Location: both faces of dividers 1 to 4, y 2.8 to 3.8, z 58.9 to 80.6 (x 47.76/48.16, 49.76/50.16, 95.12/95.52, 97.12/97.52, 142.48/142.88, 144.48/144.88, 189.84/190.24, 191.84/192.24).
- Cause: `scallop_over = 0.4` (params.scad:417) in `scallop_x0/x1()` (body.scad:380).
- Fix: `scallop_over = 0.05`. Extend the scallop cutter in y from `wall_out + 1` to `wall_out + tray_fillet_r + 0.5` (needed by F2). The divider nose is then 2.3 wide, and what is left is a 0.05 mm offset, under the slicer's resolution. 0.05 does not create coplanar faces: the prototype mesh is one watertight body with no edge under 0.001 mm.
- Do not instead make the scallop exactly bay-wide and union per-bay cavities. I tried that (`$QA/proto_cavity_failed/`): Manifold left 18 zero-volume two-triangle sheets on the coincident divider and block planes, plus 28 edges under 0.001 mm.

### F2 (High) Fillet ledge and bare corner under the scallop (close-up a)
- Location: 8 divider / front-wall corners, flat top at z 54.0, x +-0..1.7 from each divider face, y 2.8 to 4.5. Bare corner z 54 to 58.9.
- Cause: `front_fillets()`: `corner_fillets(yA_tray0, base_z - 1, trayA_front_h - 1.0)`.
- Fix: z1 = `trayA_front_h + trayA_scallop_r + 1.0`, so the extended scallop cutter (F1) trims the fillet along the r 6 arc. In `scallop_chamfer_cuts()`, run the tray-side 45 degree frustum on over the fillets (far plate at y = `wall_out + tray_fillet_r + 0.5`, shift `c + tray_fillet_r + 0.5`) and between `scallop_x0(i)` and `scallop_x1(i)` (not +-0.1 inside). Without that last part a crescent blade is left on the fillet top (seen in the first prototype).
- Result: front-face chamfer, then fillet, then divider face, one sweep (`$QA/P_A_junction_after.png`).

### F3 (High) Pillar, stop block, filler and side-wall steps (close-up c)
- Location: end bays of tray A, x 2.8 to 8.8 and 231.2 to 237.2, y 0 to 16.3.
- Cause: `pick_stop_w = pillar_w - 0.4` (params:870); filler `xe = wall_out + pick_stop_w - 0.3` (body:582); stop blocks clipped by `OUTER_CLIP` (`boss_clip_drop` 0.2); `stop_trim()` (G7) lowers the pillar 0.155.
- Fix: `pick_stop_w = pillar_w - 0.05`. Filler `xe = wall_out + pick_stop_w - 0.05`. New `stop_clip_drop = 0.05` and an `OUTER_STOP_CLIP` polygon (OUTER_CLIP with `stop_clip_drop` in place of `boss_clip_drop`) used only by `stop_blocks()`. Delete `stop_trim()` and `stop_trim_lift` from `body_geometry()`. Side wall, pillar and block tops then agree within 0.05, and pillar end, block side and filler side lie within 0.05 of one plane.
- Function: the lug engages 0.15 x cos(43.8) more. `lid_retention.py` (a) to (h) all pass. The slide-1-mm overlap goes from 25.84 to 26.28 mm3, and the up-slope room from 0.857 to 0.856 mm.

### F4 (Medium) 46 degree knife edge on the back-top of the wall between the trays
- Location: y 45.2, z 120.3 (the pick plane at the wall's tray-B face), every bay, x 2.8 to 237.2 between dividers, 225 mm in total.
- Cause: the vertical tray-B face meets the plane at 90 - 43.76 = 46.2 degrees. The audit table's B7 calls these edges "square", but this one is acute. Its top 0.4 mm is thinner than one extrusion (0.21 mm wide at 0.2 below the apex), so it will print ragged. This is the same class as H2, which `boss_back_bevel()` already fixes for the rail-1 buttress.
- Fix: `wall_back_bevels()` in the patch. This is `boss_back_bevel()`'s construction with `wall_back_bevel = 1.0` measured in the plane's frame, at y1 = `yA_wall1` with no clip drop, extruded per bay from `wall_x1(i) - 0.05` to `wall_x1(i) + bay_w + 0.05`. Every remaining edge is then 90 degrees or more. The lid's bearing strip on this wall goes from 3.3 to 2.3 mm along the plane.

### F5 (Medium) Tray B corner gussets stop 2 mm under the wall top
- Location: 10 corners at y 45.2 to 47.2: flat quarter tops at z 118.3 and a bare corner from 118.3 to 120.3. This is close-up (a)'s defect in tray B (`$QA/D_knife_wall_between_trays.png`).
- Cause: `corner_fillets(yB_tray0, trayB_floor - 1, pickplane(yB_tray0) - tray_fillet_top_under)`.
- Fix: z1 = `pickplane(yB_tray0 + tray_fillet_r) + 1`, intersected with `OUTER_STOP_CLIP` (plane - 0.05), so each gusset runs to the plane and F4's bevel trims it. `tray_fillet_top_under` becomes unused, so delete it. Lid: the plate floats 0.2 over the plane, so there is no contact.

### F6 (Medium) Sharp front-face edges of the divider noses and pillar ends; scallop front-face treatment
- Location: the vertical 90 degree edges where the front face (y 0) meets each divider nose and each pillar end, z 59 to 80, 18 edges. Today they are square (B9 "L": the 1.6 mm tips could not take a bevel; after F1 the tips are 2.3 mm).
- Fix: replace the front-face frustum in `scallop_chamfer_cuts()` with `scallop_front_round()` from the patch: a r 0.8 round along the whole scallop outline (floor, r 6 corners and both sides up to the plane), built as 5 hull frusta between outlines offset by `e = r(1 - sin t)` at depth `d = r(1 - cos t)`. New param `scallop_round_r = 0.8`. This leaves a 0.7 mm flat on the noses and 1.3 mm on the 2.8 mm scallop floor (with the 0.7 tray-side chamfer). Every surface faces up or sideways, and the overhang scan is unchanged.

### F7 (Medium) End-bay tray A front corner has no fillet
- Location: the corner between the stop block's side face and the front wall's tray face, x 8.4 (8.75 after F3) and 231.6, y 2.8, floor to arc. A bare 90 degree pill corner. The bay's own `corner_fillets` sit at x 2.8 and 237.2, buried inside the stop blocks.
- Fix: `corner_fillets(..., end_inset = pick_stop_w)` places the end bays' outer fillets at the block face. They are clear of the lugs (x 3.3 to 7.3) and stay out of the lug sweep. `capsule_corner.py` still passes with 0 last-bay pockets.

### F8 (Medium, user preference) Divider top edges on the pick plane are square
- Location: both top edges of dividers 1 to 4 over tray A (y -1 to 42.75) and tray B (45.25 to 85.15). Audit row B7 kept them sharp on purpose. The user's rule "rounded wherever possible" overrides that: these are the edges a hand passes over to pick pills.
- Fix: `divider_top_rounds()` in the patch: a quarter round of `divider_top_r = 0.6` in (x, z') sheared onto the plane, ending 0.05 short of the cross walls. The measured flat left is 1.52 mm of the 2.4 mm (section y 20: x 48.20 to 49.72). The lid still bears on that flat. `lid_retention.py` passes.
- Not done: the side walls' inner top edges. In tray A they run through the stop block and buttress zone. Add them for tray B only if wanted.

### F9 (Low) Square inboard vertical edges of the buttresses and filler (end bays)
- Location: rail-1 buttress back edge (x 5.8 / 234.2, y 29.8, z 3 to 105) and front edge above the filler (y 15.8, z 70 to 95). Rail-2 buttress both edges (y 115.6 and 129.6, z 3 to 185.7, in chute A and hopper B, where pills slide past). Filler back-inner edge (x 8.1 / 231.9, y 16.3, z 12.5 to 70.6).
- Fix (not prototyped): in `rail_boss_one()`, build the footprint as a 2D shape with r 1.0 rounds on its two inboard corners and `linear_extrude` it in place of the `cube`. Each round sits 3.7 mm from the groove (the groove tip spans y +-3.3 around the rail centre), so `corner_thickness.py`'s "buttress >= divider + 1 mm either side of the groove" holds. Round the filler's back-inner vertical edge r 1.0 by intersecting it with a plan-view rounded rectangle. Re-run `corner_thickness.py` and `skin_free_height.py`.

### F10 (Low) Fill-seat notches, 0.4 mm, at every divider and the hopper divider
- Location: 3.2 x 0.4 x 3 mm notches in the rim walls at y 87.2 to 87.6 and 209.2 to 209.6 beside each divider, and x 2.4 to 2.8 / 237.2 to 237.6 at y 157.2 to 160.4. 10 places, visible with the fill lid off.
- Cause: `seat_cut_over = 0.4` in `fill_seat_cut()`.
- Fix (not prototyped): `seat_cut_over = 0.05`. `mouth_chamfer` (0.45) was chosen not to equal `seat_cut_over`, so after the change re-check for shards with `meshcheck.py` (0 edges under 0.001) and re-run `edge_pass.py`.

### F11 (Low) Knife noses on the fill-lid seat ledges
- Location: ledge tips at z 185.8. The front (y 90.4) and back (y 204.7) tips are 45 degree wedges. The hopper-divider tips (y 147.5 and 155.5) are 34 degree wedges, and the y 147.5 underside is the 54 degree overhang the scan already lists (1064 mm2).
- Fix (not prototyped): in `VOID_A` and `VOID_B`, end each ledge's underside 0.5 mm under the ledge top and add a 0.5 mm vertical land up to it. The lid rests on the divider tops and floats 0.2 over the ledges (D30), so ledge width carries no load. Check any assert that reads `fill_ledge_w`.

### F12 (Low) Pull-lip notch edges are square (B13)
- Location: x 103 and 137, y 85.2 to 87.6, z 186 to 189.
- Fix (not prototyped): r 0.8 on the notch's 4 vertical edges, using a 2D cutter with corner pieces (the `corner_fillets` 2D shape mirrored). This only widens the lip's 2 mm side clearance.

### F13 (Low, optional) Rail-1 buttress top 0.2 under the plane next to the side wall
- Location: x 2.8 to 5.8 / 234.2 to 237.2, y 15.8 to 29.8: a 0.21 mm step beside the side wall top. The stepscan shows it at z 92 to 104 after the fixes.
- Recommendation: leave it. This is the K1/K2-verified break-out zone, and `boss_clip_drop` feeds `boss_back_bevel()`. If changed, re-run `corner_thickness.py` and `skin_free_height.py` and re-verify H2/K1.

## 4. Measured impact of F1 to F8 (prototype `$QA/proto2`, patch `$QA/qa_proto.patch`)

| Gate | Baseline (e8f5799) | With F1 to F8 |
|---|---|---|
| Mesh | watertight, 1 body, 0 edges < 0.001, 2305.49 cm3, bbox 240 x 213.013 x 189 | watertight, 1 body, 0 edges < 0.001, 2306.48 cm3, bbox unchanged |
| Steps 0.1 to 1.0 mm on wall faces (stepscan z every 1 mm) | 0.4 at 8 divider faces and both pillars; 0.3 at both fillers; 0.155/0.2 at both side walls | none over 0.06 except the label recesses (0.5, K), F10 seat notches, F13 buttress |
| `validate_scad.sh --all` | 14 / 0 / 3 / 0 / 1 | 14 / 0 / 3 / 0 / 1, "All validations passed" |
| `check_rules.py` | OK | OK, every applicable automated rule passed |
| Capacity, middle bay A / B | 437.7 / 200.0 mL | 437.7 / 200.0 mL |
| Capacity, end bays A / B | 428.2 / 198.1 mL | 427.8 / 198.1 mL |
| `lid_retention.py` (a) to (h) | pass | pass |
| `outlet_arch.py` (worst-pose margins) | pass | pass, output identical |
| `corner_thickness.py`, `skin_free_height.py`, `gang_fit.py` | pass | pass |
| `capsule_corner.py` | pass, last-bay pockets 0 | pass, last-bay pockets 0 |
| `edge_pass.py` | pass | pass |
| `overhang_scan.py` body | flat 9356, steep 3028 mm2 | flat 9356, steep 3028 mm2 |

Caveat: the capacity, skin_free_height, outlet_arch, gang_fit, overhang, validate and check_rules runs above
were made before F8 was added. lid_retention, edge_pass, corner_thickness and capsule_corner were re-run with
F8 and pass. F8 only removes about 0.1 cm3 from divider tops, but the implementer must re-run all gates on
the final tree anyway.

## 5. Evidence (sections on `build/print_ready/body.stl` equivalent, fresh render of `parts/body.scad`)

- F1: z 65, x 44 to 54, y 0 to 8: the divider tip is x 48.16 to 49.76 (1.6 mm) for y 0 to 3.8, then x 47.76 to 50.16 (2.4 mm) from y 3.8. The same holds at z 60, 70, 75 and 78. Stepscan hits for offset 0.40 at x = 48, 51, 96, 99, 141, 144, 189, 192, y 3, z 61 to 79.
- F2: y 2.9, x 49 to 58: the fillet's top is flat at z 54.000 from x 50.16 to 51.46, the bare divider face runs 54.0 to 58.86, and the arc ends at 49.76 / 61.0. Sharp-edge scan: convex 90 degree chains of 2.5 mm at z 54.0, and concave 8.2 mm chains at z 54.0 to 58.9 (8 of each).
- F3: y 0.5, 1.4 and 2.5: side wall flat top at 77.481 / 78.346 / 79.399 against the pillar at 77.329 / 78.191 / 79.244 (step 0.155). At y 3.2 the block is at 79.864 against the wall's 80.070 (0.206). z 40: block side x 8.40 for y 2.8 to 10.02, filler x 8.10 for y 10.02 to 16.3, buttress face x 5.80. z 60: pillar end x 8.8 to 8.89 against block 8.40.
- F4: x 25, y 40 to 48: (42.80, 117.99), (45.20, 120.29), then down the face from (45.20, 119.30). The apex angle is 46.2 degrees.
- F5: concave chains of 5.3 mm at y 45.2 to 46.9, z 118.3 to 120.3, and convex 2.5 mm chains at z 118.3 (10 places).
- F11: x 25: ledge (87.6, 185.8) to (90.4, 185.8), then (89.31, 184.71): a 45 degree wedge. Hopper divider (147.54, 185.8) to (149.42, 184.54): 34 degrees from horizontal.

## 6. Checked and left as is

| Item | Why left |
|---|---|
| Label recess edges, 0.5 deep (B19) | K: the tape needs the full 0.5 depth |
| Dovetail slot edges, groove countersink, skin trim step (B18, K1/K2) | K: the clip's fit and the verified break-out zone |
| Stop face, lug faces, filler top, lug sweep (B20) | K: D38 retention, measured by `lid_retention.py` |
| D41 ribs and roots (B22) | K: push-stop geometry, measured by `capsule_corner.py` |
| Outlet A / B crown and facet edges, downward bridge edges (B23) | L: down-facing in print, 36 mm clear under them. The facet prisms stop 0.05 inside both wall faces (0.05 lips, below resolution) |
| Fill-lid seat: divider tops at 186.0, ledges at 185.8 (B12) | K: the D30 rest-on-dividers fit (but see F10, F11) |
| Chute, hopper and tray B back-wall vertical corners, divider / floor edges (B27) | L: impractical, as recorded |
| Tray A back-wall / divider corners above outlet A (y 42.8, z 67 to 118) | Not a pill pocket: the pile stands at the outlet, below z 67. A gusset there would hang over the facet prisms |
| Vault ridge end lips inside chute A (y 86.2 and 157.0 to 157.6, 54 and 126 degree edges) | Internal ceiling, not touched by hand. D26/D35 record them |
| Cubby lip inner top edge (B17), cubby chamfer cone top 0.05 under the ceiling | L: inside the cubby, low contact. 0.05 is under resolution |
| Back-lean crease, outer lean 0.20 inside nominal (B4) | Accepted cosmetic (rev 12 review F1) |
| Pick lid: skirt inner end edges (P6), seating plane and lugs (P7), "FRONT" relief (P8) | K/L as audited. A 0.007 mm sliver triangle along each plate end (x 238.993 vs 239.0) is tessellation, not geometry |
| Fill lid: underside lead-in (F3), 0.05 mm seam at the lip root on the bed face, the lip's square plan root corners | K / under resolution / concave, no hazard |
| Seat-ledge 54 degree overhang under the hopper divider (1064 mm2) | Already in the overhang scan's accepted steep total. F11 shortens it |

## 7. For the implementer

1. Apply `$QA/qa_proto.patch`, or redo it by hand, then replace every `QA proto` comment with a real rationale. Delete `stop_trim()`, `stop_trim_lift`, `tray_fillet_top_under` and the now-unused `scallop_chamfer` front-frustum text. Keep `scallop_chamfer` (tray side).
2. Optionally do F9 to F12. Leave F13.
3. Gates: `validate_scad.sh --all`, `check_rules.py`, every probe in `probes/`, `$QA/meshcheck.py` (0 edges < 0.001, 1 body), `$QA/stepscan.py` + `clus.py` (no persistent hits except labels and F13), and `overhang_scan.py` on the new STL.
4. Update `edge_pass.py`: B8's front-face check should name the round (`scallop_round_r`). Add checks for F2 (no flat at z 54), F4 (bevel present), F5 (gusset reaches plane - 0.05) and F8 (divider top flat 1.5 mm or more).
5. Docs in the same commit: `calculations.md` D48 table (rows B7, B8, B9, B13, B25, B26 and new rows for F4, F7), a plan.md decision row (D60), and an INCIDENTS.md entry (coplanar-avoidance offsets of 0.3 to 0.4 mm read as visible steps on the print; use 0.05). Also update the README part sizes and volume and the resume note.
6. Rebuild the body plate: `python3 build/maquette/make_plate.py final --export`. Only the body changes.
7. Deep-tier review (this is not a small change: more than 200 lines with tests and docs).
