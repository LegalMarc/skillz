"""Section study for the pill organizer.

Compares two candidate revision-3 profiles at the same footprint: a 48 degree
ramp (the angle revision 2 uses) against a 40 degree ramp. Shallower ramps drop
hopper A's floor, which drops hopper B's floor with it, so both hoppers deepen
and the dead wedge under the crossing chute shrinks.

Emits build/section_study.svg. Render to PNG with headless Chromium.
Pure geometry; reads nothing from the OpenSCAD model. The numbers here are a
proposal to be transcribed into params.scad once approved.
"""
import math
BW = 42.96      # bay clear width
CH = 147.4      # 90-day size-00 charge, one bay
W  = 230.0      # module width
t, w, base, slab, FB = 2.8, 2.4, 3.0, 3.0, 12.0   # wall, divider, floor, chute ceiling, freeboard

def area(p):
    s = 0
    for i in range(len(p)):
        a, b = p[i], p[(i + 1) % len(p)]
        s += a[0] * b[1] - b[0] * a[1]
    return abs(s) / 2

def build(deg, tA_d, tA_h, tB_d, tB_h, cc, hB_d, hA_d, H):
    """Section of one bay pair. y runs front to back, z up. Returns None if infeasible."""
    k = math.tan(math.radians(deg))
    yA1 = t + tA_d; yB0 = yA1 + w; yB1 = yB0 + tB_d
    yHB0 = yB1 + w; yHB1 = yHB0 + hB_d
    yHA0 = yHB1 + w; yHA1 = yHA0 + hA_d; D = yHA1 + t
    nf = lambda y: base + (y - yA1) * k                  # chute A floor
    zB0 = nf(yB1) + cc + slab; zB1 = zB0 + tB_h; zA1 = base + tA_h
    ng = lambda y: zB0 + (y - yB1) * k                   # hopper B floor, parallel to the chute ceiling
    if H < max(ng(yHB1), nf(yHA1)) + FB or zB1 > H - FB:
        return None
    tA = [(t, base), (yA1, base), (yA1, zA1), (t, zA1)]
    ch = [(yA1, base), (yHA0, nf(yHA0)), (yHA0, nf(yHA0) + cc), (yA1, base + cc)]
    hA = [(yHA0, nf(yHA0)), (yHA1, nf(yHA1)), (yHA1, H), (yHA0, H)]
    tB = [(yB0, zB0), (yB1, zB0), (yB1, zB1), (yB0, zB1)]
    hB = [(yHB0, ng(yHB0)), (yHB1, ng(yHB1)), (yHB1, H), (yHB0, H)]
    sil = [(0, 0), (D, 0), (D, H), (yHB0 - w, H), (yHB0 - w, zB1), (yA1, zB1), (yA1, zA1), (0, zA1)]
    wd = [(yA1, base), (yHA1, nf(yHA1)), (yHA1, 0), (yA1, 0)]
    vA = sum(map(area, [tA, ch, hA])) * BW / 1000
    vB = sum(map(area, [tB, hB])) * BW / 1000
    return dict(deg=deg, D=D, H=H, zA1=zA1, zB0=zB0, zB1=zB1, vA=vA, vB=vB, env=W * D * H / 1e6,
                hAf=nf(yHA0), hBf=ng(yHB0), cc=cc,
                cavp=100 * sum(map(area, [tA, ch, hA, tB, hB])) / area(sil),
                wedp=100 * area(wd) / area(sil),
                polys=dict(sil=sil, tA=tA, ch=ch, hA=hA, tB=tB, hB=hB, wd=wd),
                ys=(yA1, yB0, yB1, yHB0, yHB1, yHA0, yHA1))

G48 = build(48, 28, 34, 28, 38, 36, 70, 32, H=169)   # the profile shown previously
G40 = build(40, 28, 34, 28, 38, 36, 70, 32, H=155)   # same footprint, shallower ramp

# ---------------- drawing ----------------
S, M, GAP, TOP = 2.30, 56, 96, 116
Hmax = max(G48['H'], G40['H'])
Wpx = max(int(M * 2 + GAP + (G48['D'] + G40['D']) * S), M + 724 + 74 + 348)
Hpx = int(TOP + Hmax * S + 372)
SOLID, CAV, DEAD, LID, INK = '#cfc8b9', '#8fbf6a', '#e0705a', '#3d5a80', '#242424'
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
    yA1, yB0, yB1, yHB0, yHB1, yHA0, yHA1 = g['ys']
    def P(pts): return " ".join(f"{ox+q[0]*S:.1f},{oy+(H-q[1])*S:.1f}" for q in pts)
    def blk(pts, fill, sw=1.2, stroke=INK):
        o.append(f'<polygon points="{P(pts)}" fill="{fill}" stroke="{stroke}" stroke-width="{sw}"/>')
    def lab(pts, s, sz=11.5, col="#1b3a10", dy=0):
        cx = sum(q[0] for q in pts) / len(pts); cz = sum(q[1] for q in pts) / len(pts)
        txt(ox + cx * S, oy + (H - cz) * S + 4 + dy, s, sz, col, "middle", "bold")
    def lidbar(y0, y1, z):
        o.append(f'<line x1="{ox+y0*S:.0f}" y1="{oy+(H-z)*S-4:.0f}" x2="{ox+y1*S:.0f}" y2="{oy+(H-z)*S-4:.0f}" '
                 f'stroke="{LID}" stroke-width="6" stroke-linecap="round"/>')
    def zmark(y, z, s, side=1):
        x = ox + y * S; yy = oy + (H - z) * S
        o.append(f'<line x1="{x-7:.0f}" y1="{yy:.0f}" x2="{x+7:.0f}" y2="{yy:.0f}" stroke="#7a5b3a" stroke-width="2"/>')
        txt(x + side * 11, yy + 4, s, 11, "#7a5b3a", "start" if side > 0 else "end", "bold")
    blk(p['sil'], SOLID)
    blk(p['wd'], "url(#hx)", 0, "none")
    for q in (p['tA'], p['ch'], p['hA'], p['tB'], p['hB']):
        blk(q, CAV)
    lidbar(0, yA1, g['zA1']); lidbar(yB0, yB1, g['zB1']); lidbar(yHB0 - w, g['D'], H)
    txt(ox, TOP - 74, title, 18, INK, "start", "bold")
    txt(ox, TOP - 54, sub, 13.5, "#555")
    txt(ox, TOP - 36, note, 12.5, notecol, "start", "bold")
    lab(p['tA'], "tray A", 11, "#1b3a10", -6); lab(p['tA'], "34 mm", 10.5, "#1b3a10", 8)
    lab(p['tB'], "tray B", 11)
    lab([(yA1, base), (yA1 + 52, base + 52 * math.tan(math.radians(g['deg'])))],
        f"chute A &#183; {g['cc']:.0f} mm clear", 11, "#1b3a10", -24)
    lab(p['hA'], "hop A", 11); lab(p['hB'], "hopper B", 11)
    zmark(yHA0, g['hAf'], f"hop A floor {g['hAf']:.0f}", -1)
    lab([(yA1 + 18, 0), (yHA1, 0), (yHA1, 26)], f"DEAD WEDGE &#183; {g['wedp']:.0f}%", 12.5, "#8c3b25", -6)
    return oy

panel(G48, M, "48&#176; ramp &#183; what I showed you",
      f"230 &#215; {G48['D']:.0f} &#215; {G48['H']:.0f} mm = {G48['env']:.2f} L",
      "hopper A bottoms out 120 mm up &#8212; a sliver", "#8c3b25")
panel(G40, M + G48['D'] * S + GAP, "40&#176; ramp &#183; your fix",
      f"230 &#215; {G40['D']:.0f} &#215; {G40['H']:.0f} mm = {G40['env']:.2f} L",
      "hopper A bottoms out 91 mm up &#8212; and the box is 14 mm shorter", "#1b3a10")

y0 = TOP + Hmax * S + 62
txt(M, y0 - 28, "same footprint, same bays, same two lids &#183; one bay, 90-day size-00 charge = 147.4 mL",
    13, INK, "start", "bold")
cols = [M, M + 372, M + 540, M + 724]
for i, h in enumerate(["", "48&#176; ramp", "40&#176; ramp", "change"]):
    txt(cols[i], y0, h, 12.5, "#555", "start" if i == 0 else "end", "bold")
o.append(f'<line x1="{M}" y1="{y0+6}" x2="{cols[3]}" y2="{y0+6}" stroke="#bbb" stroke-width="1"/>')
rows = [("hopper A floor, at its front edge", f"{G48['hAf']:.0f} mm", f"{G40['hAf']:.0f} mm", "29 mm lower"),
        ("hopper B floor", f"{G48['hBf']:.0f} mm", f"{G40['hBf']:.0f} mm", "8 mm lower"),
        ("tray B floor / rim", f"{G48['zB0']:.0f} / {G48['zB1']:.0f} mm", f"{G40['zB0']:.0f} / {G40['zB1']:.0f} mm", "8 mm lower"),
        ("row A capacity", f"{G48['vA']:.0f} mL  {G48['vA']/CH:.2f}&#215;", f"{G40['vA']:.0f} mL  {G40['vA']/CH:.2f}&#215;", "+7%"),
        ("row B capacity", f"{G48['vB']:.0f} mL  {G48['vB']/CH:.2f}&#215;", f"{G40['vB']:.0f} mL  {G40['vB']/CH:.2f}&#215;", "+7%"),
        ("dead wedge, share of the section", f"{G48['wedp']:.1f}%", f"{G40['wedp']:.1f}%", "&#8722;8 pts"),
        ("cavity, share of the section", f"{G48['cavp']:.1f}%", f"{G40['cavp']:.1f}%", "cavity now wins"),
        ("overall height", f"{G48['H']:.0f} mm", f"{G40['H']:.0f} mm", "&#8722;14 mm"),
        ("envelope", f"{G48['env']:.2f} L", f"{G40['env']:.2f} L", "&#8722;8%"),
        ("margin over the ~30&#176; angle of repose", "18&#176;", "10&#176;", "still ample"),
        ("chute ceiling, as an overhang", "42&#176; from vertical", "50&#176; from vertical", "past the 45&#176; rule")]
for i, r in enumerate(rows):
    yy = y0 + 26 + i * 18
    if i % 2 == 0:
        o.append(f'<rect x="{M-6}" y="{yy-13}" width="{cols[3]-M+12}" height="18" fill="#000" fill-opacity="0.028"/>')
    txt(cols[0], yy, r[0], 12, "#444")
    txt(cols[1], yy, r[1], 12, "#888", "end")
    txt(cols[2], yy, r[2], 12, "#1b3a10", "end", "bold")
    txt(cols[3], yy, r[3], 12, "#666", "end")
lx = cols[3] + 74
txt(lx, y0, "key", 12.5, INK, "start", "bold")
for i, (c, s) in enumerate([(CAV, "pill cavity"), (SOLID, "printed wall"),
                            ("url(#hx)", "dead wedge &#8212; cannot hold pills"), (LID, "lid")]):
    yy = y0 + 24 + i * 20
    o.append(f'<rect x="{lx}" y="{yy-10}" width="17" height="13" fill="{c}" stroke="{INK}" stroke-width=".8"/>')
    txt(lx + 25, yy, s, 12, "#555")
for i, s in enumerate(["a shallower ramp lowers hopper A's floor, and",
                       "hopper B's floor rides on it, so both deepen.",
                       "The only thing 48&#176; was buying was a self-",
                       "supporting chute ceiling &#8212; and that ceiling is",
                       "an internal surface nobody sees."]):
    txt(lx, y0 + 128 + i * 16, s, 11.5, "#8c3b25", "start", "bold" if i == 0 else "normal")
o.append('</svg>')
open('build/section_study.svg', 'w').write("\n".join(o))
print(Wpx, Hpx)
