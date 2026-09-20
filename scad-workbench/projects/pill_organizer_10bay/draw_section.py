"""Section study for the pill organizer: current revision 2 vs proposed revision 3.

Emits build/section_study.svg. Render to PNG with headless Chromium.
Pure geometry — reads nothing from the OpenSCAD model, so the numbers here are a
proposal to be transcribed into params.scad once approved.
"""
import math
k=math.tan(math.radians(48)); BW=42.96; CHARGE=147.4; W=230.0
def area(p):
    s=0
    for i in range(len(p)): a,b=p[i],p[(i+1)%len(p)]; s+=a[0]*b[1]-b[0]*a[1]
    return abs(s)/2
# ---- CURRENT rev2 ----
cH,cD=200.0,205.474
cf=lambda y:3+(y-38.8)*k; cg=lambda y:84+(y-77.2)*k; cpp=lambda y:74+(y/77.2)*(122-74)
sil_c=[(0,0),(cD,0),(cD,cH),(77.2,cH),(77.2,122),(0,74)]
trayA_c=[(2.8,3),(38.8,3),(38.8,cpp(38.8)),(2.8,cpp(2.8))]
chute_c=[(38.8,3),(154,cf(154)),(154,cf(154)+33),(38.8,36)]
hopA_c=[(154,cf(154)),(202.7,cf(202.7)),(202.7,cH),(154,cH)]
trayB_c=[(41.2,84),(77.2,84),(77.2,122),(41.2,122)]
hopB_c=[(79.6,cg(79.6)),(151.6,cg(151.6)),(151.6,cH),(79.6,cH)]
wedge_c=[(38.8,3),(202.7,cf(202.7)),(202.7,0),(38.8,0)]
cav_c=sum(map(area,[trayA_c,chute_c,hopA_c,trayB_c,hopB_c]))
print("CURRENT  sil=%.0f cav=%.0f (%.1f%%) wedge=%.0f (%.1f%%) env=%.2fL"%(
  area(sil_c),cav_c,100*cav_c/area(sil_c),area(wedge_c),100*area(wedge_c)/area(sil_c),W*cD*cH/1e6))
print("  rowA=%.0f mL (%.2fx)  rowB=%.0f mL (%.2fx)"%(
  sum(map(area,[trayA_c,chute_c,hopA_c]))*BW/1000, sum(map(area,[trayA_c,chute_c,hopA_c]))*BW/1000/CHARGE,
  sum(map(area,[trayB_c,hopB_c]))*BW/1000, sum(map(area,[trayB_c,hopB_c]))*BW/1000/CHARGE))
# ---- trade: hopper B depth vs footprint/height ----
t,w,base,slab,fb=2.8,2.4,3.0,3.0,12.0
def build(tA_d,tA_h,tB_d,tB_h,cc,hB_d,hA_d):
    yA1=t+tA_d; yB0=yA1+w; yB1=yB0+tB_d; yHB0=yB1+w; yHB1=yHB0+hB_d
    yHA0=yHB1+w; yHA1=yHA0+hA_d; D=yHA1+t
    nf=lambda y: base+(y-yA1)*k
    zB0=nf(yB1)+cc+slab; zB1=zB0+tB_h; zA1=base+tA_h
    ng=lambda y: zB0+(y-yB1)*k
    H=math.ceil(max(ng(yHB1),nf(yHA1))+fb)
    tA=[(t,base),(yA1,base),(yA1,zA1),(t,zA1)]
    ch=[(yA1,base),(yHA0,nf(yHA0)),(yHA0,nf(yHA0)+cc),(yA1,base+cc)]
    hA=[(yHA0,nf(yHA0)),(yHA1,nf(yHA1)),(yHA1,H),(yHA0,H)]
    tB=[(yB0,zB0),(yB1,zB0),(yB1,zB1),(yB0,zB1)]
    hB=[(yHB0,ng(yHB0)),(yHB1,ng(yHB1)),(yHB1,H),(yHB0,H)]
    sil=[(0,0),(D,0),(D,H),(yHB0-w,H),(yHB0-w,zB1),(yA1,zB1),(yA1,zA1),(0,zA1)]
    wd=[(yA1,base),(yHA1,nf(yHA1)),(yHA1,0),(yA1,0)]
    vA=sum(map(area,[tA,ch,hA]))*BW/1000; vB=sum(map(area,[tB,hB]))*BW/1000
    cav=sum(map(area,[tA,ch,hA,tB,hB]))
    return dict(D=D,H=H,zA1=zA1,zB0=zB0,zB1=zB1,vA=vA,vB=vB,env=W*D*H/1e6,
        cavp=100*cav/area(sil),wedp=100*area(wd)/area(sil),
        polys=dict(sil=sil,tA=tA,ch=ch,hA=hA,tB=tB,hB=hB,wd=wd),
        ys=(yA1,yB0,yB1,yHB0,yHB1,yHA0,yHA1))

# ---- drawing ----
CH=147.4
g=build(28,34,28,38,36,70,32)
p=g['polys']; yA1,yB0,yB1,yHB0,yHB1,yHA0,yHA1=g['ys']
nD,nH,zA1,zB0,zB1=g['D'],g['H'],g['zA1'],g['zB0'],g['zB1']

S=2.30; M=56; GAP=96; TOP=104
def P(pts,oy,ox,Hmm): return " ".join(f"{ox+q[0]*S:.1f},{oy+(Hmm-q[1])*S:.1f}" for q in pts)

Wpx=int(M*2+GAP+(cD+nD)*S); Hpx=int(TOP+cH*S+312)
oyC=TOP; oxC=M; oyN=TOP+(cH-nH)*S; oxN=M+cD*S+GAP
SOLID='#cfc8b9'; CAV='#8fbf6a'; DEAD='#e0705a'; LID='#3d5a80'; INK='#242424'
o=[f'<svg xmlns="http://www.w3.org/2000/svg" width="{Wpx}" height="{Hpx}" viewBox="0 0 {Wpx} {Hpx}" font-family="Helvetica,Arial,sans-serif">',
   f'<rect width="{Wpx}" height="{Hpx}" fill="#fcfbf8"/>',
   '<defs><pattern id="hx" width="9" height="9" patternTransform="rotate(45)" patternUnits="userSpaceOnUse">'
   f'<rect width="9" height="9" fill="{DEAD}" fill-opacity="0.30"/>'
   f'<line x1="0" y1="0" x2="0" y2="9" stroke="{DEAD}" stroke-width="2.2" stroke-opacity="0.75"/></pattern></defs>']
def blk(pts,oy,ox,Hm,fill,sw=1.2,stroke=INK):
    o.append(f'<polygon points="{P(pts,oy,ox,Hm)}" fill="{fill}" stroke="{stroke}" stroke-width="{sw}"/>')
def txt(x,y,s,sz=12.5,col=INK,anc="start",wt="normal"):
    o.append(f'<text x="{x:.1f}" y="{y:.1f}" font-size="{sz}" fill="{col}" text-anchor="{anc}" font-weight="{wt}">{s}</text>')
def lidbar(y0,y1,z0,z1,oy,ox,Hm):
    x0,x1=ox+y0*S,ox+y1*S; a=oy+(Hm-z0)*S-4; b=oy+(Hm-z1)*S-4
    o.append(f'<line x1="{x0:.0f}" y1="{a:.0f}" x2="{x1:.0f}" y2="{b:.0f}" stroke="{LID}" stroke-width="6" stroke-linecap="round"/>')
def lab(pts,oy,ox,Hm,s,sz=11.5,col="#1b3a10",dy=0,wt="bold"):
    cx=sum(q[0] for q in pts)/len(pts); cz=sum(q[1] for q in pts)/len(pts)
    txt(ox+cx*S,oy+(Hm-cz)*S+4+dy,s,sz,col,"middle",wt)
def vdim(y,z0,z1,oy,ox,Hm,s,side=-1):
    x=ox+y*S; a=oy+(Hm-z0)*S; b=oy+(Hm-z1)*S
    o.append(f'<line x1="{x:.0f}" y1="{a:.0f}" x2="{x:.0f}" y2="{b:.0f}" stroke="#7a5b3a" stroke-width="1.2"/>')
    for yy in (a,b): o.append(f'<line x1="{x-4:.0f}" y1="{yy:.0f}" x2="{x+4:.0f}" y2="{yy:.0f}" stroke="#7a5b3a" stroke-width="1.6"/>')
    txt(x+side*7,(a+b)/2+4,s,11,"#7a5b3a","end" if side<0 else "start","bold")

# ================= CURRENT =================
blk(sil_c,oyC,oxC,cH,SOLID)
blk(wedge_c,oyC,oxC,cH,"url(#hx)",0,"none")
for q in (trayA_c,chute_c,hopA_c,trayB_c,hopB_c): blk(q,oyC,oxC,cH,CAV)
o.append(f'<polygon points="{P([(2.8,36),(38.8,36),(38.8,cpp(38.8)),(2.8,cpp(2.8))],oyC,oxC,cH)}" fill="url(#hx)" stroke="none"/>')
lidbar(0,77.2,74,122,oyC,oxC,cH); lidbar(79.6,202.7,200,200,oyC,oxC,cH)
txt(oxC,TOP-62,"CURRENT &#183; revision 2",18,INK,"start","bold")
txt(oxC,TOP-42,"230 &#215; 205 &#215; 200 mm   =   9.45 L",13.5,"#555")
txt(oxC,TOP-24,"pick tray 73&#8211;95 mm deep &#183; front face 74 mm",12.5,"#8c3b25","start","bold")
lab(trayA_c,oyC,oxC,cH,"tray A",12,"#1b3a10",-26); lab(trayA_c,oyC,oxC,cH,"reach 73&#8211;95 mm",10.5,"#8c3b25",-11)
lab(chute_c,oyC,oxC,cH,"chute A &#183; 159 mm enclosed",11)
lab(hopA_c,oyC,oxC,cH,"hopper A",11); lab(trayB_c,oyC,oxC,cH,"tray B",11); lab(hopB_c,oyC,oxC,cH,"hopper B",11)
lab([(60,0),(190,0),(190,40)],oyC,oxC,cH,"SOLID &#183; 46% of the section",12.5,"#8c3b25",6)
vdim(-8,0,74,oyC,oxC,cH,"74")
# ================= PROPOSED =================
blk(p['sil'],oyN,oxN,nH,SOLID)
blk(p['wd'],oyN,oxN,nH,"url(#hx)",0,"none")
for q in (p['tA'],p['ch'],p['hA'],p['tB'],p['hB']): blk(q,oyN,oxN,nH,CAV)
lidbar(0,yA1,zA1,zA1,oyN,oxN,nH); lidbar(yB0,yB1,zB1,zB1,oyN,oxN,nH)
lidbar(yHB0-2.4,nD,nH,nH,oyN,oxN,nH)
txt(oxN,TOP-62,"PROPOSED &#183; revision 3",18,INK,"start","bold")
txt(oxN,TOP-42,f"230 &#215; {nD:.0f} &#215; {nH:.0f} mm   =   {g['env']:.2f} L   (&#8722;30%)",13.5,"#555")
txt(oxN,TOP-24,"pick tray 34 mm deep &#183; front face 37 mm",12.5,"#1b3a10","start","bold")
lab(p['tA'],oyN,oxN,nH,"tray A",11,"#1b3a10",-6); lab(p['tA'],oyN,oxN,nH,"34 mm",10.5,"#1b3a10",8)
lab([(yA1,3),(88,3+(88-yA1)*k)],oyN,oxN,nH,"chute A = the store &#183; 36 mm clear",11,"#1b3a10",-26)
lab(p['hA'],oyN,oxN,nH,"hop A",11); lab(p['tB'],oyN,oxN,nH,"tray B",11); lab(p['hB'],oyN,oxN,nH,"hopper B",11)
lab([(46,0),(150,0),(150,30)],oyN,oxN,nH,"SAME WEDGE &#183; still 47%",12.5,"#8c3b25",-8)
txt(oxN+98*S,oyN+nH*S-8,"hollow it out &#8594; open front cubby, 3.3 L",11,"#8c3b25","middle")
vdim(-8,0,zA1,oyN,oxN,nH,"37")
vdim(nD+9,0,nH,oyN,oxN,nH,f"{nH:.0f}",1)

# ================= TABLE =================
y0=TOP+cH*S+52
txt(M,y0-26,"one bay, 90-day size-00 charge = 147.4 mL &#183; both designs are 230 mm wide, 5 bays per row",13,INK,"start","bold")
cols=[M,M+352,M+520,M+700]
hdr=["","current","proposed","change"]
for i,h in enumerate(hdr): txt(cols[i],y0,h,12.5,"#555","start" if i==0 else "end","bold")
o.append(f'<line x1="{M}" y1="{y0+6}" x2="{cols[3]}" y2="{y0+6}" stroke="#bbb" stroke-width="1"/>')
rows=[("row A  (front tray, back port, crossing chute)","381 mL  2.58&#215;",f"{g['vA']:.0f} mL  {g['vA']/CH:.2f}&#215;","232 days"),
      ("row B  (back tray, front port, plain ramp)","286 mL  1.94&#215;",f"{g['vB']:.0f} mL  {g['vB']/CH:.2f}&#215;","122 days"),
      ("front face height","74 mm","37 mm","&#8722;50%"),
      ("reach down into the pick tray","73&#8211;95 mm","34 mm","&#8722;60%"),
      ("step, tray A rim to tray B rim","48 mm","77 mm","taller row B"),
      ("chute A clear section / enclosed run","33 mm / 159 mm","36 mm / 104 mm","wider, shorter"),
      ("cavity as a share of the printed section","46.7%",f"{g['cavp']:.1f}%","unchanged"),
      ("overall envelope","9.45 L",f"{g['env']:.2f} L","&#8722;30%"),
      ("flat lids needed","2 &#183; sloped planes","2 &#183; stepped pick lid","same count")]
for i,r in enumerate(rows):
    yy=y0+26+i*18
    if i%2==0: o.append(f'<rect x="{M-6}" y="{yy-13}" width="{cols[3]-M+12}" height="18" fill="#000" fill-opacity="0.028"/>')
    txt(cols[0],yy,r[0],12,"#444")
    txt(cols[1],yy,r[1],12,"#888","end"); txt(cols[2],yy,r[2],12,"#1b3a10","end","bold"); txt(cols[3],yy,r[3],12,"#666","end")
lx=cols[3]+70
txt(lx,y0,"key",12.5,INK,"start","bold")
for i,(c,s) in enumerate([(CAV,"pill cavity"),(SOLID,"printed wall"),("url(#hx)","dead wedge &#8212; cannot hold pills"),(LID,"lid")]):
    yy=y0+24+i*20
    o.append(f'<rect x="{lx}" y="{yy-10}" width="17" height="13" fill="{c}" stroke="{INK}" stroke-width=".8"/>')
    txt(lx+25,yy,s,12,"#555")
txt(lx,y0+24+4*20+10,"the wedge is the price of filling at the back",11.5,"#8c3b25","start","bold")
txt(lx,y0+24+4*20+26,"and picking at the front &#8212; it is ~47% at any",11.5,"#8c3b25")
txt(lx,y0+24+4*20+42,"ramp angle. Shrink the box, not the wedge.",11.5,"#8c3b25")
o.append('</svg>')
open('build/section_study.svg','w').write("\n".join(o))
print(Wpx,Hpx,"| D=%.1f H=%.0f env=%.2f rowA=%.0f rowB=%.0f"%(nD,nH,g['env'],g['vA'],g['vB']))
