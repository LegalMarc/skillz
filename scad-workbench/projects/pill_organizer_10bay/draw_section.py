"""Section study for the pill organizer.

Panel 1 answers whether curving the chute floor buys usable volume (it does not:
the straight line at the minimum flow angle is provably the lowest floor there
is). Panel 2 is the change that does pay: a shallow porch under tray B, which
drops tray B's floor onto tray A's rim and takes the whole stack down with it.

Emits build/section_study.svg. Render to PNG with headless Chromium.
Pure geometry; reads nothing from the OpenSCAD model. The numbers here are a
proposal to be transcribed into params.scad once approved.
"""
import math
BW = 42.96      # bay clear width
CH = 147.4      # 90-day size-00 charge, one bay
W  = 230.0      # module width
PILL_L, PILL_D = 26.0, 11.0
REPOSE = 30.0   # estimated angle of repose, capsules on PLA (PATIKRINTI)
t, w, base, slab, FB = 2.8, 2.4, 3.0, 3.0, 12.0

def area(p):
    s = 0
    for i in range(len(p)):
        a, b = p[i], p[(i + 1) % len(p)]
        s += a[0] * b[1] - b[0] * a[1]
    return abs(s) / 2

def build(deg, porch_deg, tA_d, tA_h, tB_d, tB_h, cc, hB_d, hA_d, H):
    """One bay pair in section. The chute floor runs at porch_deg under tray B,
    then climbs at deg. porch_deg == deg gives the plain straight ramp."""
    k = math.tan(math.radians(deg)); kp = math.tan(math.radians(porch_deg))
    kr = math.tan(math.radians(REPOSE))
    yA1 = t + tA_d; yB0 = yA1 + w; yB1 = yB0 + tB_d
    yHB0 = yB1 + w; yHB1 = yHB0 + hB_d
    yHA0 = yHB1 + w; yHA1 = yHA0 + hA_d; D = yHA1 + t
    zP = base + (yB1 - yA1) * kp                      # chute floor at the end of the porch
    nf = lambda y: base + (y - yA1) * kp if y <= yB1 else zP + (y - yB1) * k
    zB0 = zP + cc + slab; zB1 = zB0 + tB_h; zA1 = base + tA_h
    ng = lambda y: nf(y) + cc + slab                  # hopper B floor
    if H < max(ng(yHB1), nf(yHA1)) + FB or zB1 > H - FB:
        return None
    tA = [(t, base), (yA1, base), (yA1, zA1), (t, zA1)]
    ch = [(yA1, base), (yB1, zP), (yHA0, nf(yHA0)), (yHA0, nf(yHA0) + cc), (yB1, zP + cc), (yA1, base + cc)]
    hA = [(yHA0, nf(yHA0)), (yHA1, nf(yHA1)), (yHA1, H), (yHA0, H)]
    tB = [(yB0, zB0), (yB1, zB0), (yB1, zB1), (yB0, zB1)]
    hB = [(yHB0, ng(yHB0)), (yHB1, ng(yHB1)), (yHB1, H), (yHB0, H)]
    sil = [(0, 0), (D, 0), (D, H), (yHB0 - w, H), (yHB0 - w, zB1), (yA1, zB1), (yA1, zA1), (0, zA1)]
    wd = [(yA1, base), (yB1, zP), (yHA1, nf(yHA1)), (yHA1, 0), (yA1, 0)]
    stag = sum(max(0.0, (base + (yA1 + (i + .5) * (yB1 - yA1) / 400 - yA1) * kr)
                   - nf(yA1 + (i + .5) * (yB1 - yA1) / 400)) for i in range(400)) * (yB1 - yA1) / 400
    return dict(deg=deg, porch=porch_deg, D=D, H=H, zA1=zA1, zB0=zB0, zB1=zB1, cc=cc,
                vA=sum(map(area, [tA, ch, hA])) * BW / 1000,
                vB=sum(map(area, [tB, hB])) * BW / 1000, env=W * D * H / 1e6,
                hAf=nf(yHA0), hBf=ng(yHB0), nf=nf, stag=stag * BW / 1000,
                throat=cc - (yB1 - yA1) * (kr - kp),
                cavp=100 * sum(map(area, [tA, ch, hA, tB, hB])) / area(sil),
                wedp=100 * area(wd) / area(sil),
                polys=dict(sil=sil, tA=tA, ch=ch, hA=hA, tB=tB, hB=hB, wd=wd),
                ys=(yA1, yB0, yB1, yHB0, yHB1, yHA0, yHA1))

G1 = build(40, 40, 28, 34, 28, 38, 36, 70, 32, H=155)   # straight 40 deg ramp, as last drawn
G2 = build(40, 20, 28, 50, 28, 38, 36, 70, 32, H=141)   # 20 deg porch, tray A rim on tray B's floor

# what the drawn arc would cost, measured against the repose bound
y0, yEnd = G1['ys'][0], G1['ys'][6]
RUN = yEnd - y0; RISE = RUN * math.tan(math.radians(40))
KR = math.tan(math.radians(REPOSE))
arc = lambda y: base + RISE * ((y - y0) / RUN) ** 2.2
N = 2000; DY = RUN / N
gain = sum((base + (i + .5) * DY * math.tan(math.radians(40))) - arc(y0 + (i + .5) * DY) for i in range(N)) * DY
stagn = sum(max(0, base + (i + .5) * DY * KR - arc(y0 + (i + .5) * DY)) for i in range(N)) * DY
band = 0.5 * RUN * RUN * (math.tan(math.radians(40)) - KR)

# ---------------- drawing ----------------
S, M, GAP, TOP = 2.30, 56, 104, 130
Hmax = max(G1['H'], G2['H'])
Wpx = max(int(M * 2 + GAP + (G1['D'] + G2['D']) * S), M + 700 + 78 + 352)
Hpx = int(TOP + Hmax * S + 64 + 26 + 11 * 18 + 40)
SOLID, CAV, DEAD, LID, INK, ARC, OK = '#cfc8b9', '#8fbf6a', '#e0705a', '#3d5a80', '#242424', '#e03b1e', '#c98a20'
o = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{Wpx}" height="{Hpx}" viewBox="0 0 {Wpx} {Hpx}" font-family="Helvetica,Arial,sans-serif">',
     f'<rect width="{Wpx}" height="{Hpx}" fill="#fcfbf8"/>',
     '<defs><pattern id="hx" width="9" height="9" patternTransform="rotate(45)" patternUnits="userSpaceOnUse">'
     f'<rect width="9" height="9" fill="{DEAD}" fill-opacity="0.30"/>'
     f'<line x1="0" y1="0" x2="0" y2="9" stroke="{DEAD}" stroke-width="2.2" stroke-opacity="0.75"/></pattern></defs>']

def txt(x, y, s, sz=12.5, col=INK, anc="start", wt="normal"):
    o.append(f'<text x="{x:.1f}" y="{y:.1f}" font-size="{sz}" fill="{col}" text-anchor="{anc}" font-weight="{wt}">{s}</text>')

def panel(g, ox, title, sub, note, notecol):
    oy = TOP + (Hmax - g['H']) * S
    H = g['H']; p = g['polys']
    def X(y): return ox + y * S
    def Z(z): return oy + (H - z) * S
    def P(pts): return " ".join(f"{X(q[0]):.1f},{Z(q[1]):.1f}" for q in pts)
    def blk(pts, fill, sw=1.2, stroke=INK):
        o.append(f'<polygon points="{P(pts)}" fill="{fill}" stroke="{stroke}" stroke-width="{sw}"/>')
    def lab(pts, s, sz=11.5, col="#1b3a10", dy=0):
        cx = sum(q[0] for q in pts) / len(pts); cz = sum(q[1] for q in pts) / len(pts)
        txt(X(cx), Z(cz) + 4 + dy, s, sz, col, "middle", "bold")
    blk(p['sil'], SOLID); blk(p['wd'], "url(#hx)", 0, "none")
    for q in (p['tA'], p['ch'], p['hA'], p['tB'], p['hB']):
        blk(q, CAV)
    yA1, yB0, yB1, yHB0, yHB1, yHA0, yHA1 = g['ys']
    for a, b, z in ((0, yA1, g['zA1']), (yB0, yB1, g['zB1']), (yHB0 - w, g['D'], H)):
        o.append(f'<line x1="{X(a):.0f}" y1="{Z(z)-4:.0f}" x2="{X(b):.0f}" y2="{Z(z)-4:.0f}" stroke="{LID}" stroke-width="6" stroke-linecap="round"/>')
    txt(ox, TOP - 88, title, 18, INK, "start", "bold")
    txt(ox, TOP - 68, sub, 13.5, "#555")
    txt(ox, TOP - 50, note, 12.5, notecol, "start", "bold")
    lab(p['tA'], "tray A", 11); lab(p['tB'], "tray B", 11)
    lab(p['hA'], "hop A", 11); lab(p['hB'], "hopper B", 11)
    return X, Z, oy

# ---- panel 1: the curve question ----
X, Z, oy = panel(G1, M, "curving the floor &#183; 40&#176; ramp",
                 f"230 &#215; {G1['D']:.0f} &#215; {G1['H']:.0f} mm = {G1['env']:.2f} L",
                 "the arc gains volume that will not discharge", "#8c3b25")
rep = [(y0, base)] + [(y0 + i * RUN / 40, base + (i * RUN / 40) * KR) for i in range(41)]
o.append('<polygon points="' + " ".join(f"{X(y0 + i*RUN/40):.1f},{Z(base + (i*RUN/40)*KR):.1f}" for i in range(41))
         + f' {X(yEnd):.1f},{Z(base):.1f}" fill="#8c8c8c" fill-opacity="0.34" stroke="none"/>')
o.append('<polygon points="' + " ".join(f"{X(y0+i*RUN/40):.1f},{Z(base+(i*RUN/40)*math.tan(math.radians(40))):.1f}" for i in range(41))
         + " " + " ".join(f"{X(y0+i*RUN/40):.1f},{Z(base+(i*RUN/40)*KR):.1f}" for i in range(40, -1, -1))
         + f'" fill="{OK}" fill-opacity="0.38" stroke="none"/>')
o.append('<polyline points="' + " ".join(f"{X(y0+i*RUN/40):.1f},{Z(base+(i*RUN/40)*KR):.1f}" for i in range(41))
         + '" fill="none" stroke="#5a5a5a" stroke-width="2" stroke-dasharray="7 5"/>')
o.append('<polyline points="' + " ".join(f"{X(y0+i*RUN/60):.1f},{Z(arc(y0+i*RUN/60)):.1f}" for i in range(61))
         + f'" fill="none" stroke="{ARC}" stroke-width="3.6" stroke-linecap="round"/>')
txt(X(y0 + RUN * 0.62), Z(base + RUN * 0.62 * math.tan(math.radians(40))) + 30,
    f"reachable by angle alone: +{band*BW/1000:.0f} mL/bay", 11.5, "#8a5f10", "middle", "bold")
txt(X(y0 + RUN * 0.55), Z(base) - 16, f"below the {REPOSE:.0f}&#176; repose line &#8212; fills once, never empties",
    11.5, "#444", "middle", "bold")
txt(X(yEnd) - 6, Z(base + RUN * KR) - 10, f"{REPOSE:.0f}&#176; repose limit", 11, "#5a5a5a", "end", "bold")
txt(X(y0 + RUN * 0.30), Z(arc(y0 + RUN * 0.30)) + 20, "your arc", 12, ARC, "middle", "bold")

# ---- panel 2: the porch ----
ox2 = M + G1['D'] * S + GAP
X2, Z2, oy2 = panel(G2, ox2, "20&#176; porch under tray B",
                    f"230 &#215; {G2['D']:.0f} &#215; {G2['H']:.0f} mm = {G2['env']:.2f} L  (&#8722;41% on revision 2)",
                    "tray B's floor lands on tray A's rim", "#1b3a10")
yA1, yB0, yB1, yHB0, yHB1, yHA0, yHA1 = G2['ys']
o.append(f'<line x1="{X2(0)-26:.0f}" y1="{Z2(G2["zA1"]):.0f}" x2="{X2(yB1)+14:.0f}" y2="{Z2(G2["zA1"]):.0f}" '
         f'stroke="#1b3a10" stroke-width="1.6" stroke-dasharray="6 4"/>')
txt(X2(0) - 30, Z2(G2['zA1']) + 4, f"{G2['zA1']:.0f}", 11.5, "#1b3a10", "end", "bold")
txt(X2(yB1) + 18, Z2(G2['zA1']) + 4, "one line", 11.5, "#1b3a10", "start", "bold")
o.append(f'<polyline points="{X2(yA1):.1f},{Z2(base):.1f} {X2(yB1):.1f},{Z2(G2["nf"](yB1)):.1f}" '
         f'fill="none" stroke="#8a5f10" stroke-width="4"/>')
txt(X2((yA1 + yB1) / 2), Z2(base) + 26, "porch", 11.5, "#8a5f10", "middle", "bold")
txt(X2(yHA1), Z2(base) - 16, f"wedge {G2['wedp']:.0f}%", 12, "#8c3b25", "end", "bold")

# ---------------- table ----------------
y0t = TOP + Hmax * S + 64
txt(M, y0t - 28, "one bay, 90-day size-00 charge = 147.4 mL &#183; capsule 26 &#215; 11 mm", 13, INK, "start", "bold")
cols = [M, M + 348, M + 522, M + 700]
for i, h in enumerate(["", "straight 40&#176;", "20&#176; porch", "change"]):
    txt(cols[i], y0t, h, 12.5, "#555", "start" if i == 0 else "end", "bold")
o.append(f'<line x1="{M}" y1="{y0t+6}" x2="{cols[3]}" y2="{y0t+6}" stroke="#bbb" stroke-width="1"/>')
rows = [("tray A rim", f"{G1['zA1']:.0f} mm", f"{G2['zA1']:.0f} mm", "= front face"),
        ("tray B floor", f"{G1['zB0']:.0f} mm", f"{G2['zB0']:.0f} mm", f"step {G2['zB0']-G2['zA1']:+.0f} mm"),
        ("hopper A floor, front edge", f"{G1['hAf']:.0f} mm", f"{G2['hAf']:.0f} mm", "25 mm lower"),
        ("hopper B floor", f"{G1['hBf']:.0f} mm", f"{G2['hBf']:.0f} mm", "15 mm lower"),
        ("row A", f"{G1['vA']:.0f} mL  {G1['vA']/CH:.2f}&#215;", f"{G2['vA']:.0f} mL  {G2['vA']/CH:.2f}&#215;", "+6%"),
        ("row B", f"{G1['vB']:.0f} mL  {G1['vB']/CH:.2f}&#215;", f"{G2['vB']:.0f} mL  {G2['vB']/CH:.2f}&#215;", "+1%"),
        ("dead wedge / cavity", f"{G1['wedp']:.0f}% / {G1['cavp']:.0f}%", f"{G2['wedp']:.0f}% / {G2['cavp']:.0f}%", "cavity 2&#215; the wedge"),
        ("overall height", f"{G1['H']:.0f} mm", f"{G2['H']:.0f} mm", "&#8722;14 mm"),
        ("envelope", f"{G1['env']:.2f} L", f"{G2['env']:.2f} L", "&#8722;9%"),
        ("stagnant pills on the porch", "none", f"{G2['stag']:.1f} mL/bay", "2.8% of a charge"),
        ("flow channel over the porch", "n/a", f"{G2['throat']:.0f} mm", f"1.1&#215; pill length")]
for i, r in enumerate(rows):
    yy = y0t + 26 + i * 18
    if i % 2 == 0:
        o.append(f'<rect x="{M-6}" y="{yy-13}" width="{cols[3]-M+12}" height="18" fill="#000" fill-opacity="0.028"/>')
    txt(cols[0], yy, r[0], 12, "#444")
    txt(cols[1], yy, r[1], 12, "#888", "end")
    txt(cols[2], yy, r[2], 12, "#1b3a10", "end", "bold")
    txt(cols[3], yy, r[3], 12, "#666", "end")
lx = cols[3] + 78
txt(lx, y0t, "key", 12.5, INK, "start", "bold")
for i, (c, s) in enumerate([(CAV, "pill cavity"), (SOLID, "printed wall"),
                            ("url(#hx)", "dead wedge"), (OK, "reachable by angle"),
                            ("#8c8c8c", "below repose &#8212; unreachable")]):
    yy = y0t + 24 + i * 19
    o.append(f'<rect x="{lx}" y="{yy-10}" width="17" height="13" fill="{c}" stroke="{INK}" stroke-width=".8"/>')
    txt(lx + 25, yy, s, 12, "#555")
for i, s in enumerate(["the floor has to fall toward the outlet at the",
                       "repose angle or steeper, at every point. So it",
                       "can never sit below a straight line drawn at",
                       "that angle from tray A. The straight ramp IS",
                       "the lowest floor; a curve is either above it",
                       "(less volume) or below it (stagnant pills)."]):
    txt(lx, y0t + 132 + i * 15, s, 11.2, "#8c3b25", "start", "bold" if i == 0 else "normal")
o.append('</svg>')
open('build/section_study.svg', 'w').write("\n".join(o))
print(Wpx, Hpx, "| arc gain %.0f mL/bay, stagnant %.0f mL/bay (%.0f%%)" % (gain*BW/1000, stagn*BW/1000, 100*stagn/gain))
