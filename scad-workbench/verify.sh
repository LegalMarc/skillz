#!/usr/bin/env bash
# Acceptance test for the workbench.
#
# Does not ask "did the tools run" -- a broken checker runs fine and reports
# nothing. It asks whether the stack CATCHES a defect that only exists in
# motion, and whether it stays quiet on the same geometry when that defect is
# removed. A verification tool that cannot fail is not a verification tool.
#
# Case: a lever pivoting about Z, and a fixed post. At the rest pose they are
# nowhere near each other. Somewhere past 70 degrees the lever sweeps straight
# through the post. Only a swept check can see it.
set -euo pipefail

PREFIX="${SCAD_WORKBENCH_PREFIX:-$HOME/.local/opt/openscad}"
SKILLS_SRC="${SKILLS_SRC:-$HOME/.local/src/openscad-cad-skills}"
# shellcheck source=/dev/null
[ -f "$PREFIX/env.sh" ] && source "$PREFIX/env.sh"
: "${OPENSCAD_BIN:?run install.sh first}"

WORK="$(mktemp -d)"; trap 'rm -rf "$WORK"' EXIT; cd "$WORK"
pass=0; fail=0
ok()   { printf '  \033[32mPASS\033[0m  %s\n' "$*"; pass=$((pass+1)); }
bad()  { printf '  \033[31mFAIL\033[0m  %s\n' "$*"; fail=$((fail+1)); }

cat > arm.scad  <<'EOF'
translate([0,-3,0]) cube([30,6,6]);
cylinder(h=6, r=5, $fn=64);
EOF
cat > post.scad <<'EOF'
translate([0,25,0]) cylinder(h=10, r=4, $fn=64);
EOF
# Same post moved clear of the 30mm swing radius -- the control case.
cat > post_clear.scad <<'EOF'
translate([0,42,0]) cylinder(h=10, r=4, $fn=64);
EOF

echo "1. Render and export"
for p in arm post post_clear; do
  xvfb-run -a "$OPENSCAD_BIN" --backend=manifold -o "$p.stl" "$p.scad" >/dev/null 2>&1
  [ -s "$p.stl" ] && ok "$p.stl exported" || bad "$p.stl missing"
done
xvfb-run -a "$OPENSCAD_BIN" --backend=manifold --imgsize=640,480 \
  --camera=0,0,0,55,0,25,160 --render -o preview.png arm.scad >/dev/null 2>&1
[ -s preview.png ] && ok "PNG render (visual feedback loop)" || bad "PNG render failed"

mkjoints() { cat > "$1" <<EOF
{ "contacts": [],
  "motion": [ { "id": "lever_swing",
    "drivers": [ {"part": "arm", "type": "revolute",
                  "axis": [0,0,1], "origin": [0,0,0], "ratio": 1.0} ],
    "range_deg": [0, 360], "step_deg": 2.0, "min_clearance_mm": 0.5 } ] }
EOF
}
mkjoints joints.json
SWEEP="$SKILLS_SRC/scad-modeler/scripts/motion_sweep.py"

echo "2. The checker must FAIL on a real motion clash"
if python3 "$SWEEP" arm.stl post.stl --joints joints.json >clash.txt 2>&1; then
  bad "sweep passed a lever that visibly sweeps through the post"
else
  grep -q "interference" clash.txt \
    && ok "clash detected: $(grep -o 't = [0-9.]*\.\.[0-9.]*deg' clash.txt | head -1)" \
    || bad "non-zero exit but no interference reported"
fi

echo "3. The checker must stay QUIET when the defect is removed"
cp post_clear.stl post.stl
if python3 "$SWEEP" arm.stl post.stl --joints joints.json >clear.txt 2>&1; then
  ok "clear geometry reported clear (no false positive)"
else
  bad "reported interference on geometry with 12mm of clearance"; cat clear.txt
fi

printf '\n%d passed, %d failed\n' "$pass" "$fail"
[ "$fail" -eq 0 ] || exit 1
