#!/usr/bin/env bash
# Provision a headless OpenSCAD workbench for agent-driven mechanical design.
#
# Every agent CAD skill surveyed in README.md opens with "install OpenSCAD" and
# then assumes, without checking, a build new enough to carry the Manifold
# backend and a machine with GL libraries already present. Neither holds in a
# container: the distro package is 2021.01 (pre-Manifold, CGAL-slow) and the
# official AppImage will not start without libEGL. This script closes that gap.
#
# Idempotent. Safe to re-run. Verifies before it claims success.
set -euo pipefail

SNAPSHOT="${OPENSCAD_SNAPSHOT:-OpenSCAD-2026.01.02.ai30348-x86_64.AppImage}"
PREFIX="${SCAD_WORKBENCH_PREFIX:-$HOME/.local/opt/openscad}"
LIBDIR="${OPENSCADPATH:-$HOME/.local/share/OpenSCAD/libraries}"
SKILLDIR="${CLAUDE_SKILL_DIR:-$HOME/.claude/skills}"
SKILLS_REPO="${SKILLS_REPO:-https://github.com/Altern92/openscad-cad-skills.git}"
SKILLS_SRC="${SKILLS_SRC:-$HOME/.local/src/openscad-cad-skills}"

say() { printf '\n\033[1m==> %s\033[0m\n' "$*"; }

# --- 1. Runtime libraries -----------------------------------------------------
# The AppImage bundles Qt but not the GL/XCB stack it links against. Without
# libEGL.so.1 it exits before printing --version. xvfb supplies the X display
# that PNG rendering requires even when offscreen.
say "Runtime libraries"
if command -v apt-get >/dev/null 2>&1; then
  SUDO=""; [ "$(id -u)" -ne 0 ] && SUDO="sudo"
  $SUDO apt-get update -qq
  DEBIAN_FRONTEND=noninteractive $SUDO apt-get install -y -qq \
    libegl1 libgl1 libglu1-mesa libopengl0 libxi6 libxrender1 libxrandr2 \
    libxcursor1 libxinerama1 libfontconfig1 libxkbcommon-x11-0 libdbus-1-3 \
    libxcb-cursor0 libxcb-icccm4 libxcb-image0 libxcb-keysyms1 libxcb-randr0 \
    libxcb-render-util0 libxcb-shape0 libxcb-xinerama0 libxcb-xkb1 \
    xvfb git curl python3-pip
else
  echo "  no apt-get; ensure libEGL, libGL, xvfb and git are present" >&2
fi

# --- 2. OpenSCAD with the Manifold backend ------------------------------------
# Extracted rather than run as an AppImage: --appimage-extract needs no FUSE,
# which containers generally do not provide.
say "OpenSCAD ($SNAPSHOT)"
mkdir -p "$PREFIX"
if [ ! -x "$PREFIX/squashfs-root/AppRun" ]; then
  curl -fsSL -o "$PREFIX/openscad.AppImage" \
    "https://files.openscad.org/snapshots/$SNAPSHOT"
  chmod +x "$PREFIX/openscad.AppImage"
  ( cd "$PREFIX" && ./openscad.AppImage --appimage-extract >/dev/null )
  rm -f "$PREFIX/openscad.AppImage"
fi
export OPENSCAD_BIN="$PREFIX/squashfs-root/AppRun"
export OPENSCAD="$OPENSCAD_BIN"
export OPENSCADPATH="$LIBDIR"
"$OPENSCAD_BIN" --version

# Manifold is the whole reason for the nightly. Fail loudly if it is absent
# rather than silently falling back to CGAL and blaming the geometry later.
if ! "$OPENSCAD_BIN" --help 2>&1 | grep -q -- '--backend'; then
  echo "FAIL: this build has no --backend flag; Manifold unavailable." >&2
  exit 1
fi

# --- 3. Geometry libraries ----------------------------------------------------
# BOSL2 supplies the gear, thread and attachment primitives that any real
# mechanism leans on. Resolved via OPENSCADPATH, never by absolute include.
say "OpenSCAD libraries"
mkdir -p "$LIBDIR"
clone_lib() {
  [ -d "$LIBDIR/$1" ] && { echo "  $1 present"; return; }
  git clone --depth 1 -q "$2" "$LIBDIR/$1" && echo "  $1 cloned"
}
clone_lib BOSL2 https://github.com/BelfrySCAD/BOSL2.git
clone_lib MCAD  https://github.com/openscad/MCAD.git

# --- 4. Verification dependencies ---------------------------------------------
# Not needed to write or render a model -- only to check the result. The skill
# degrades honestly without them, which is why they install separately.
say "Python verification stack"
pip install -q --disable-pip-version-check \
  trimesh shapely scipy networkx python-fcl manifold3d rtree pyyaml jsonschema \
  pillow   # render.sh's contact sheet; views still render without it

# --- 5. The skills ------------------------------------------------------------
say "openscad-cad-skills"
if [ -d "$SKILLS_SRC/.git" ]; then git -C "$SKILLS_SRC" pull -q --ff-only || true
else mkdir -p "$(dirname "$SKILLS_SRC")"; git clone -q "$SKILLS_REPO" "$SKILLS_SRC"; fi
mkdir -p "$SKILLDIR"
for s in openscad-cad scad-modeler openscad-organic; do
  ln -sfn "$SKILLS_SRC/$s" "$SKILLDIR/$s" && echo "  linked $s"
done

# --- 6. Environment -----------------------------------------------------------
say "Environment"
ENVFILE="$PREFIX/env.sh"
cat > "$ENVFILE" <<ENV
# source this before invoking OpenSCAD or any check script
export OPENSCAD_BIN="$OPENSCAD_BIN"
export OPENSCAD="$OPENSCAD_BIN"
export OPENSCADPATH="$LIBDIR"
scad()  { xvfb-run -a "\$OPENSCAD_BIN" --backend=manifold "\$@"; }
export -f scad 2>/dev/null || true
ENV
echo "  wrote $ENVFILE"

# --- 7. Self-check ------------------------------------------------------------
say "Doctor"
DOCTOR_LOG="$PREFIX/doctor.log"
python3 "$SKILLS_SRC/scad-modeler/scripts/doctor.py" 2>&1 | tee "$DOCTOR_LOG" || true

# The doctor is the authority on whether this install is usable. An earlier
# revision printed "Workbench ready" over a tier-0 report because OPENSCAD_BIN
# was set but never exported, so the doctor could not see the binary that had
# just been installed one step above. Trust the report, not the script.
if grep -q "Highest supportable tier: 0" "$DOCTOR_LOG"; then
  echo >&2
  echo "INSTALL FAILED: the doctor reports tier 0 -- nothing can be rendered" >&2
  echo "or exported. Full report: $DOCTOR_LOG" >&2
  exit 1
fi

cat <<DONE

Workbench ready.  Activate with:   source $ENVFILE
Acceptance test:                   ./verify.sh
Render six views + contact sheet:  ./render.sh model.scad build/preview

Note the doctor's tier line. Without a measured calibration profile the
stack verifies geometry, not fit -- a bore will be the diameter you asked
for, but whether your printer produces a working press fit at that diameter
is unproven until you calibrate.
DONE
