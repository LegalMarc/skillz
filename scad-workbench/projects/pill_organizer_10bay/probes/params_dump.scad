// Echoes the handful of derived numbers the probes need, one "PROBE name=value"
// line each, so the probes never re-derive geometry that params.scad owns.
include <../params.scad>
echo(str("PROBE slope=", pick_lid_slope));
echo(str("PROBE lid_dx=", (module_w - pick_lid_w) / 2));
echo(str("PROBE module_w=", module_w));
echo(str("PROBE module_d=", module_d));
echo(str("PROBE module_h=", module_h));
echo(str("PROBE lug_clear=", pick_lug_clear));
echo(str("PROBE lid_len=", pick_lid_len));
echo(str("PROBE lid_back_y=", yB_tray1 - pick_lid_clear));
echo(str("PROBE engage_asserted=", pick_lug_engage));
echo(str("PROBE rail_boss=", rail_boss));
echo(str("PROBE rail_skin=", rail_skin));
echo(str("PROBE rail1_y=", rail1_y));
echo(str("PROBE rail_out=", rail_out));
echo(str("PROBE rail_tip_w=", rail_tip_w));
echo(str("PROBE rail_clear=", rail_clear));
echo(str("PROBE rail1_soc_z1=", rail1_soc_z1));
echo(str("PROBE wall_out=", wall_out));
echo(str("PROBE pillar_w=", pillar_w));
echo(str("PROBE trayA_rim=", trayA_rim));
echo(str("PROBE trayB_rim=", trayB_rim));
echo(str("PROBE yA_tray0=", yA_tray0));
echo(str("PROBE yA_tray1=", yA_tray1));
echo(str("PROBE yB_tray0=", yB_tray0));
echo(str("PROBE yB_tray1=", yB_tray1));
echo(str("PROBE fill_seat_z=", fill_seat_z));
echo(str("PROBE bay_w=", bay_w));
echo(str("PROBE wall_div=", wall_div));
echo(str("PROBE module_h=", module_h));
echo(str("PROBE charge_ml=", charge_ml));
echo(str("PROBE trayA_pile_front=", trayA_pile_front));
echo(str("PROBE outletA_top=", outletA_top));
echo(str("PROBE z_foot=", z_foot));
echo(str("PROBE trayB_floor=", trayB_floor));
cube(0.001);
