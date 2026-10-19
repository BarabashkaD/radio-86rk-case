"""Explicit frozen-v09 triangle producer and catalog-only node feeder; no GUI."""
import hashlib
import json
import math
from pathlib import Path
from geometry_checks import check_boolean_result

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def source(c,name):
    p=Path(c['inputs'][name])
    if p.is_symlink() or not p.is_file() or sha(p)!=c['input_hashes'][name]:raise ValueError('Input SHA mismatch '+name)
    return p

def segments_from_layout(raw):
    if not isinstance(raw,list) or not raw:raise ValueError('Nonempty switch windows required')
    for b in raw:
        if len(b)!=6 or not all(isinstance(v,(int,float)) and math.isfinite(v) for v in b):raise ValueError('Invalid window bbox')
    wins=[(b[0]-.3,b[3]+.3,b[1]-.3,b[4]+.3) for b in raw if b[3]-b[0]<25 and b[1]<-95]
    result=[]
    for i,a in enumerate(wins):
        for b in wins[i+1:]:
            for aa,bb in ((a,b),(b,a)):
                gap=bb[0]-aa[1];ya=max(aa[2],bb[2]);yb=min(aa[3],bb[3])
                if .8<gap<4 and yb-ya>2:result.append(('Y',(aa[1]+bb[0])/2,ya,yb,gap))
                gap=bb[2]-aa[3];xa=max(aa[0],bb[0]);xb=min(aa[1],bb[1])
                if .8<gap<4 and xb-xa>2:result.append(('X',(aa[3]+bb[2])/2,xa,xb,gap))
    if len(result)!=120:raise ValueError('Accepted layout must yield120 segments')
    return result

def intersections(segments):
    nodes={}
    for a in [s for s in segments if s['axis']=='Y']:
        for b in [s for s in segments if s['axis']=='X']:
            x,y=a['center'],b['center']
            if a['from']-b['width']/2-.01<=y<=a['to']+b['width']/2+.01 and b['from']-a['width']/2-.01<=x<=b['to']+a['width']/2+.01:
                key=(round(x,6),round(y,6));value=(x,y,a['width'],b['width'])
                if key in nodes and nodes[key]!=value:raise ValueError('Ambiguous crossing')
                nodes[key]=value
    return nodes

def fresh(c,names):
    if c.get('cold_build') is not True or set(c['outputs'])!=set(names):raise ValueError('Exact cold output contract required')
    if any(Path(p).exists() for p in c['outputs'].values()):raise ValueError('Existing output')

def body(s):
    if s.isNull() or not s.isValid() or len(s.Solids)!=1 or s.Volume<=0:raise ValueError('Expected one valid keyboard solid')
    s.check(True)

def build_profiles(c):
    fresh(c,('keyboard_profiles','keyboard_segments'));vp=source(c,'v09_reference');lp=source(c,'layout')
    segments=segments_from_layout(json.loads(lp.read_text())['switch_windows'])
    import FreeCAD as app
    import Part as part
    if app.listDocuments():raise ValueError('Clean document context required')
    doc=app.openDocument(str(vp))
    try:
        obj=doc.getObject('UpperShell')
        if obj is None:raise ValueError('Approved v09 UpperShell missing')
        full=obj.Shape.copy()
    finally:app.closeDocument(doc.Name)
    V=app.Vector;original=full.common(part.makeBox(267.4,121,8,V(6,-216,14)));cutters=[];report=[];rf=.3
    for direction,center,a,b,w in segments:
        p=V(center,(a+b)/2,18) if direction=='Y' else V((a+b)/2,center,18)
        tip=17.4 if original.isInside(p,1e-6,False) else 18.6
        theta=math.atan((w/2)/(20.6-tip));zc=tip+rf/math.sin(theta);ut=rf*math.cos(theta);zt=zc-rf*math.sin(theta)
        def point(u,z):return V(center+u,a,z) if direction=='Y' else V(a,center+u,z)
        p0,p1,p2,p3=point(-w/2,20.6),point(w/2,20.6),point(ut,zt),point(-ut,zt)
        face=part.Face(part.Wire([part.makeLine(p0,p1),part.makeLine(p1,p2),part.Arc(p2,point(0,zc-rf),p3).toShape(),part.makeLine(p3,p0)]))
        keep=face.extrude(V(0,b-a,0) if direction=='Y' else V(b-a,0,0))
        if keep.Volume<0:keep.reverse()
        box=part.makeBox(w,b-a,6.6,V(center-w/2,a,14)) if direction=='Y' else part.makeBox(b-a,w,6.6,V(a,center-w/2,14))
        cutters.append(box.cut(keep));report.append({'axis':direction,'center':center,'from':a,'to':b,'width':w,'virtual_tip':tip,'actual_round_tip':zc-rf,'radius':rf})
    result=original.cut(part.makeCompound(cutters));body(result)
    added=result.cut(original);check_boolean_result(added)
    if abs(added.Volume)>=.001:raise ValueError('Triangle source gained material')
    output=Path(c['outputs']['keyboard_profiles']);result.exportBrep(str(output));reopened=part.Shape();reopened.read(str(output));body(reopened)
    for delta in (result.cut(reopened),reopened.cut(result)):
        check_boolean_result(delta)
        if abs(delta.Volume)>.001:raise ValueError('Triangle save mismatch')
    source(c,'v09_reference');source(c,'layout')
    data={'segments':report,'count':120,'source_object':'UpperShell','crop':[6,-216,14,267.4,121,8],
          'input_sha256':dict(c['input_hashes']),'output_sha256':sha(output),'added_mm3':added.Volume,'BOP':'PASS','baseline_equivalence':'NOT_RUN','release_ready':False}
    Path(c['outputs']['keyboard_segments']).write_text(json.dumps(data,indent=2)+'\n');return data

def build_catalog(c):
    fresh(c,('keyboard_nodes',));p=source(c,'keyboard_profiles');sp=source(c,'keyboard_segments')
    segments=json.loads(sp.read_text())['segments']
    import FreeCAD as app
    import Part as part
    if app.listDocuments():raise ValueError('Clean document context required')
    base=part.Shape();base.read(str(p));body(base);records=[]
    for (xr,yr),(x,y,wx,wy) in intersections(segments).items():
        # Preserve original producer's rounded probe coordinates, but keep exact
        # centers for subsequent replacement booleans.
        if not base.isInside(app.Vector(xr,yr,20),1e-6,False):continue
        tip=17.4 if base.isInside(app.Vector(xr,yr,18),1e-6,False) else 18.6
        records.append({'xy':[x,y],'probe_xy':[xr,yr],'widths':[wx,wy],'tip':tip})
    if len(records)!=81:raise ValueError('Expected81 accepted crossings')
    source(c,'keyboard_profiles');source(c,'keyboard_segments')
    data={'nodes':records,'count':81,'input_sha256':dict(c['input_hashes']),'geometry_modified':False,'release_ready':False}
    Path(c['outputs']['keyboard_nodes']).write_text(json.dumps(data,indent=2)+'\n');return data
