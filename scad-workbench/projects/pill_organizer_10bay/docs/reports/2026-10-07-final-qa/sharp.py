import trimesh, numpy as np, sys, networkx as nx
m=trimesh.load(sys.argv[1]); thr=float(sys.argv[2]) if len(sys.argv)>2 else 40
ang=np.degrees(m.face_adjacency_angles); cvx=m.face_adjacency_convex
E=m.face_adjacency_edges
L=np.linalg.norm(m.vertices[E[:,0]]-m.vertices[E[:,1]],axis=1)
for kind,mask in [('CONVEX',cvx),('CONCAVE',~cvx)]:
    sel=(ang>thr)&mask
    G=nx.Graph(); 
    for (a,b),an,l in zip(E[sel],ang[sel],L[sel]): G.add_edge(a,b,ang=an,l=l)
    comps=[]
    for c in nx.connected_components(G):
        sg=G.subgraph(c); tot=sum(d['l'] for _,_,d in sg.edges(data=True))
        if tot<1.0: continue
        V=m.vertices[list(c)]; lo=V.min(0); hi=V.max(0)
        a=np.mean([d['ang'] for _,_,d in sg.edges(data=True)])
        comps.append((tot,lo,hi,a))
    print(kind, len(comps))
    for tot,lo,hi,a in sorted(comps,key=lambda t:(round(t[1][2]),t[1][0])):
        print('  len %7.1f  dihedral %5.1f  x %6.1f..%6.1f y %6.1f..%6.1f z %6.1f..%6.1f'%(tot,a,lo[0],hi[0],lo[1],hi[1],lo[2],hi[2]))
