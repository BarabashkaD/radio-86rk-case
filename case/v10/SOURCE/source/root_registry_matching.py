"""Strict unique geometric matching; never silently reuse stale OCC indices."""
import math

def near(a,b,tol=1e-5):return len(a)==len(b) and all(math.isfinite(float(x)) and abs(x-y)<=tol for x,y in zip(a,b))
def same(a,b):
    if a['curve_type']!=b['curve_type'] or abs(a['length']-b['length'])>1e-5:return False
    pa,pb=a['points'],b['points']
    if not (all(near(x,y) for x,y in zip(pa,pb)) or all(near(x,y) for x,y in zip(pa,reversed(pb)))):return False
    left=a['adjacent'];right=b['adjacent']
    if len(left)!=len(right):return False
    unused=list(range(len(right)))
    for f in left:
        found=next((j for j in unused if f['face_type']==right[j]['face_type'] and near(f['normal'],right[j]['normal'])),None)
        if found is None:return False
        unused.remove(found)
    return True

def match(registry,candidates):
    if len(registry)!=50:raise ValueError('Accepted registry requires50 signatures')
    rows=[];used=set()
    for ref in registry:
        matches=[c for c in candidates if same(ref,c)]
        if len(matches)!=1 or matches[0]['index'] in used:raise ValueError('Missing/ambiguous geometric root match '+str(ref['index']))
        chosen=matches[0]['index'];used.add(chosen);rows.append({'edge':chosen,'radius':ref['radius'],'reference_edge':ref['index']})
    return rows

def describe(net):
    records=[]
    for i,e in enumerate(net.Edges):
        u0,u1=e.ParameterRange;pts=[e.valueAt(u) for u in (u0,(u0+u1)/2,u1)];p=pts[1]
        # Only the accepted sloped roof region can own these roots.
        if not (-96<p.y<-73.9 and p.z>19):continue
        adjacent=[]
        for f in net.Faces:
            if any(a.isSame(e) for a in f.Edges):
                n=f.normalAt(*f.Surface.parameter(p));adjacent.append({'face_type':type(f.Surface).__name__,'normal':[n.x,n.y,n.z]})
        records.append({'index':i,'curve_type':type(e.Curve).__name__,'length':e.Length,'points':[[p.x,p.y,p.z] for p in pts],'adjacent':adjacent})
    return records
