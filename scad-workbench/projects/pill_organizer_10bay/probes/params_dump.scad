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
cube(0.001);
