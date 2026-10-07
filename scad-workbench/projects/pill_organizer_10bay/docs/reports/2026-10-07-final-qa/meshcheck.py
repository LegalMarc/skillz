import trimesh, numpy as np, sys
for f in sys.argv[1:]:
    m=trimesh.load(f)
    E=m.edges_unique; L=np.linalg.norm(m.vertices[E[:,0]]-m.vertices[E[:,1]],axis=1)
    print(f, 'watertight',m.is_watertight,'bodies',len(m.split(only_watertight=False)),'vol cm3',round(m.volume/1000,3),'bbox',np.round(m.bounds,3).tolist(),'edges<0.001',int((L<0.001).sum()),'edges<0.01',int((L<0.01).sum()))
