"""Pure explicit keyboard geometry helpers; CAD equivalence gate NOT RUN.
Port of round_keyboard_nodes_v2.profile and keyboard_exact_batches.template.
No source execution, GUI, document discovery, filesystem writes or global CAD state.
"""
import hashlib
import math
from pathlib import Path

def load(path, expected_sha256, *, part):
    path=Path(path)
    if path.is_symlink() or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=expected_sha256:
        raise ValueError('Keyboard source SHA mismatch')
    shape=part.Shape();shape.read(str(path))
    if shape.isNull() or not shape.isValid():raise ValueError('Invalid keyboard source')
    if hashlib.sha256(path.read_bytes()).hexdigest()!=expected_sha256:raise ValueError('Keyboard source changed during read')
    return shape

def profile(x,y,w,length,along,tip,*,app,part):
    if along not in ('X','Y'):raise ValueError('Unknown axis')
    if not all(math.isfinite(v) for v in (x,y,w,length,tip)) or w<=0 or length<=0 or tip>=20.6:raise ValueError('Invalid profile parameters')
    V=app.Vector;top=20.6;rf=.3;theta=math.atan(w/2/(top-tip));zc=tip+rf/math.sin(theta);ut=rf*math.cos(theta);zt=zc-rf*math.sin(theta)
    def p(u,z):return V(x+u,y-length/2,z) if along=='Y' else V(x-length/2,y+u,z)
    ps=[p(-w/2,top),p(w/2,top),p(ut,zt),p(-ut,zt)]
    f=part.Face(part.Wire([part.makeLine(ps[0],ps[1]),part.makeLine(ps[1],ps[2]),part.Arc(ps[2],p(0,zc-rf),ps[3]).toShape(),part.makeLine(ps[3],ps[0])]))
    q=f.extrude(V(0,length,0) if along=='Y' else V(length,0,0))
    if q.Volume<0:q.reverse()
    return q

def template(tip,*,app,part):
    if tip not in (17.4,18.6):raise ValueError('Unsupported accepted tip')
    s=profile(0,0,2.85,8,'Y',tip,app=app,part=part).fuse(profile(0,0,2.85,8,'X',tip,app=app,part=part)).removeSplitter()
    edges=[]
    for edge in s.Edges:
        p=edge.valueAt(sum(edge.ParameterRange)/2)
        if abs(abs(p.x)-abs(p.y))<1e-5 and abs(p.x)<1.4251 and p.z<20.59:edges.append(edge)
    if not edges:raise ValueError('No valley edges found')
    q=s.makeFillet(.15,edges);q.check(True)
    return q.common(part.makeBox(2.89,2.89,6.6,app.Vector(-1.445,-1.445,14)))
