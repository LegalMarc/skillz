import trimesh, numpy as np, sys, collections
def cr(a,b): return a[0]*b[1]-a[1]*b[0]
m = trimesh.load(sys.argv[1])
axis = sys.argv[2]; vals = np.arange(float(sys.argv[3]), float(sys.argv[4]), float(sys.argv[5]))
N = {'x':[1,0,0],'y':[0,1,0],'z':[0,0,1]}[axis]
keep = {'x':(1,2),'y':(0,2),'z':(0,1)}[axis]
hits=[]
for v in vals:
    o=[0,0,0]; o['xyz'.index(axis)]=v
    s = m.section(plane_origin=o, plane_normal=N)
    if s is None: continue
    for e in s.entities:
        P = s.vertices[e.points][:, keep]
        # merge collinear consecutive points
        segs=[]
        for i in range(len(P)-1):
            a,b=P[i],P[i+1]; d=b-a; L=np.linalg.norm(d)
            if L<1e-6: continue
            segs.append((a,b,d/L,L))
        # merge collinear
        merged=[]
        for sg in segs:
            if merged and abs(cr(merged[-1][2], sg[2]))<0.01 and np.dot(merged[-1][2], sg[2])>0:
                a=merged[-1][0]; b=sg[1]; d=b-a; L=np.linalg.norm(d); merged[-1]=(a,b,d/L,L)
            else: merged.append(sg)
        n=len(merged)
        for i in range(n-2):
            A,C,B = merged[i],merged[i+1],merged[i+2]
            if A[3]>1.0 and B[3]>1.0 and 0.02<C[3]<1.0 and abs(cr(A[2],B[2]))<0.035 and np.dot(A[2],B[2])>0:
                off = abs(cr(A[2], B[0]-A[1]))
                if 0.02<off<1.0:
                    hits.append((round(float(v),2), (round(float(C[0][0]),2),round(float(C[0][1]),2)), round(float(off),3), round(float(C[3]),3)))
for h in hits: print(h)
