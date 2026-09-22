#!/usr/bin/env bash
# Multi-view render for the look-and-correct loop.
#
# The skill's own guidance is a single --viewall isometric. One angle hides the
# errors that matter most: a bore through the wrong face, a part floating off
# its mate, a broken symmetry, a feature present on one side only. This renders
# the six standard views and tiles them into ONE contact sheet, so the agent
# spends a single image read per iteration instead of six.
#
#   ./render.sh model.scad [outdir] [-D name=value ...]
#
# Writes <outdir>/{front,back,left,right,top,iso}.png and contact.png.
# Read contact.png first; open a single view only when it shows something.
set -euo pipefail

PREFIX="${SCAD_WORKBENCH_PREFIX:-$HOME/.local/opt/openscad}"
# shellcheck source=/dev/null
[ -f "$PREFIX/env.sh" ] && source "$PREFIX/env.sh"
: "${OPENSCAD_BIN:?run install.sh first, then: source $PREFIX/env.sh}"

[ $# -ge 1 ] || { sed -n '2,12p' "$0" | sed 's/^# \?//'; exit 2; }
SCAD="$1"; shift
OUT="${1:-build/preview}"; [ $# -gt 0 ] && shift
mkdir -p "$OUT"
# Remaining args (e.g. -D wall=3) are forwarded to every view. Held in an array
# because "$@" inside render_view would refer to the function's own arguments.
EXTRA=("$@")

SIZE="${RENDER_SIZE:-800,600}"

# One shared camera for every view. --viewall fits each view independently,
# which silently renders the same part at different scales from different
# angles -- an agent comparing proportions across those views would "correct"
# a distortion that does not exist. So: measure the bounding box once, derive
# a single centre and distance, and hold both fixed across all six.
read -r CX CY CZ DIST <<<"$(
  xvfb-run -a "$OPENSCAD_BIN" --backend=manifold --summary all \
    --summary-file - -o "$OUT/.bbox.stl" "${EXTRA[@]}" "$SCAD" 2>/dev/null |
  python3 -c '
import json, sys, math
try:
    bb = json.load(sys.stdin)["geometry"]["bounding_box"]
    lo, hi = bb["min"], bb["max"]
except Exception:
    print("0 0 0 0"); sys.exit()
c = [(a + b) / 2 for a, b in zip(lo, hi)]
diag = math.dist(lo, hi) or 1.0
# gimbal camera, default 22.5 deg fov: dist = size / (2*tan(fov/2)), +15% margin
print(f"{c[0]:.4f} {c[1]:.4f} {c[2]:.4f} {diag / (2*math.tan(math.radians(11.25))) * 1.15:.4f}")
')"
if [ "${DIST:-0}" = "0" ]; then
  echo "  (bbox unavailable -- falling back to per-view autofit)" >&2
  FIT=(--viewall --autocenter); CX=0; CY=0; CZ=0; DIST=0
else
  FIT=()
  printf '  scale locked: centre (%s, %s, %s) distance %s\n' "$CX" "$CY" "$CZ" "$DIST"
fi

render_view() {
  xvfb-run -a "$OPENSCAD_BIN" --backend=manifold --render \
    --imgsize="$SIZE" --camera="$CX,$CY,$CZ,$2,0,$3,$DIST" "${FIT[@]}" \
    --colorscheme="${RENDER_COLORSCHEME:-Tomorrow}" \
    -o "$OUT/$1.png" "${EXTRA[@]}" "$SCAD" >/dev/null 2>"$OUT/.$1.log" \
    || { echo "render failed: $1"; sed -n '1,8p' "$OUT/.$1.log"; return 1; }
}

echo "Rendering $SCAD -> $OUT/"
render_view front  90 0
render_view back   90 180
render_view left   90 270
render_view right  90 90
render_view top     0 0
render_view iso    55 25

# Contact sheet: 3x2 grid, each view labelled. One read covers all six.
python3 - "$OUT" <<'PY'
import sys, os
try:
    from PIL import Image, ImageDraw
except ImportError:
    sys.exit("  (pillow not installed -- individual views written, no contact sheet)")
out = sys.argv[1]
names = ["front", "back", "left", "right", "top", "iso"]
imgs = [(n, Image.open(os.path.join(out, n + ".png")).convert("RGB"))
        for n in names if os.path.exists(os.path.join(out, n + ".png"))]
if not imgs:
    sys.exit("  no views to tile")
w, h = imgs[0][1].size
cols, bar = 3, 22
rows = (len(imgs) + cols - 1) // cols
sheet = Image.new("RGB", (w * cols, (h + bar) * rows), "white")
d = ImageDraw.Draw(sheet)
for i, (name, im) in enumerate(imgs):
    x, y = (i % cols) * w, (i // cols) * (h + bar)
    d.rectangle([x, y, x + w, y + bar], fill=(32, 32, 32))
    d.text((x + 6, y + 6), name.upper(), fill="white")
    sheet.paste(im, (x, y + bar))
sheet.save(os.path.join(out, "contact.png"))
print(f"  contact.png  ({cols}x{rows} grid, {len(imgs)} views)")
PY
ls -1 "$OUT"/*.png | sed 's/^/  /'
