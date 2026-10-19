"""New lower reinforcement study; no previous floor grid is reused."""
import FreeCAD as A, Part, math
import ventilation_v10 as ventilation
from lower_grid_layout import layout
from v10_parameters import PCB_MOUNTS, CASE_MOUNTS
V=A.Vector
MOUNTS=list(PCB_MOUNTS)
CASES=list(CASE_MOUNTS)
def pos(s):
 if not s.isNull() and s.Volume<0:s.reverse()
 return s
def stage(n):pass
def bbox(b):return [b.XMin,b.YMin,b.ZMin,b.XMax,b.YMax,b.ZMax]
def strip(a,b,w,z=2.95,h=6.05):
 d=V(b[0]-a[0],b[1]-a[1],0);d.normalize();n=V(-d.y,d.x,0)*w/2;p=V(*a,z) if False else V(a[0],a[1],z);q=V(b[0],b[1],z)
 pts=[p+n,q+n,q-n,p-n];return pos(Part.Face(Part.makePolygon(pts+[pts[0]])).extrude(V(0,0,h)))
def closest(p,a,b):
 dx=b[0]-a[0];dy=b[1]-a[1];t=max(0,min(1,((p[0]-a[0])*dx+(p[1]-a[1])*dy)/(dx*dx+dy*dy)));q=(a[0]+t*dx,a[1]+t*dy);return math.hypot(p[0]-q[0],p[1]-q[1]),q

def root(x,y,r,Rf):
 # Exact concave quarter-circle, revolved around the actual mounting axis.
 p0=V(x+r-.05,y,2.95);p1=V(x+r+Rf,y,2.95);p2=V(x+r+Rf,y,3);pm=V(x+r+Rf-Rf/math.sqrt(2),y,3+Rf-Rf/math.sqrt(2));p3=V(x+r,y,3+Rf);p4=V(x+r-.05,y,3+Rf)
 wire=Part.Wire([Part.makeLine(p0,p1),Part.makeLine(p1,p2),Part.Arc(p2,pm,p3).toShape(),Part.makeLine(p3,p4),Part.makeLine(p4,p0)])
 return pos(Part.Face(wire).revolve(V(x,y,0),V(0,0,1),360))

def trim(sh,masks):
 for m in masks:
  a=sh.BoundBox;b=m.BoundBox
  if a.XMax<b.XMin or a.XMin>b.XMax or a.YMax<b.YMin or a.YMin>b.YMax or a.ZMax<b.ZMin or a.ZMin>b.ZMax:continue
  sh=sh.cut(m)
  if sh.isNull():return sh
 return sh.removeSplitter()

def build(base,wall,inventory,p,rib_pitch=40.):
 floor_radius=p.FloorInnerRadius;rib_root=p.RibRootRadius;node_radius=p.RibNodeRadius;post_radius=p.PostRootRadius
 rib_width=p.RibWidth;rib_height=p.RibHeight;extrusion=rib_height+.05
 assert 0<rib_width<rib_pitch and 0<rib_height<9.7 and rib_pitch>0
 assert 0<rib_root<rib_height and 0<node_radius<rib_pitch and 0<post_radius<9.7
 assert 0<floor_radius<2.2,'FloorInnerRadius must be below inner plan radius2.2'
 stage('base supplied');r={'parameters':{'FloorInnerRadius':floor_radius,'RibRootRadius':rib_root,'NodeRadius':node_radius,'PostRootRadius':post_radius,'RibThickness':rib_width,'RibNetHeight':rib_height,'RibTopZ':3+rib_height,'RibPitchMinimumNormal':rib_pitch},'warnings':[]}
 # Exact parametric concave floor/wall quarter-circle, swept around all corners.
 stage('perimeter roots')
 def rootface(x,y,dx,dy):
  a=V(x,y,2.95);b=V(x+dx*floor_radius,y+dy*floor_radius,2.95);c=V(b.x,b.y,3);mid=V(x+dx*floor_radius*(1-1/math.sqrt(2)),y+dy*floor_radius*(1-1/math.sqrt(2)),3+floor_radius*(1-1/math.sqrt(2)));end=V(x,y,3+floor_radius)
  return Part.Face(Part.Wire([Part.makeLine(a,b),Part.makeLine(b,c),Part.Arc(c,mid,end).toShape(),Part.makeLine(end,a)]))
 roots_perimeter=[]
 for x,dx in [(-7.5,1),(286.9,-1)]:roots_perimeter.append(pos(rootface(x,-214,dx,0).extrude(V(0,205.95,0))))
 for y,dy in [(-216.2,1),(-5.85,-1)]:roots_perimeter.append(pos(rootface(-5.3,y,0,dy).extrude(V(290,0,0))))
 for cx,cy,ang in [(-5.3,-214,90),(-5.3,-8.05,-90)]:
  q=pos(rootface(-7.5,cy,1,0).revolve(V(cx,cy,0),V(0,0,1),ang));roots_perimeter.append(q);m=A.Matrix();m.A11=-1;m.A14=279.4;qq=q.copy();qq.transformShape(m);roots_perimeter.append(qq)
 r['perimeter_fillet_applied']=True;r['perimeter_radius_method']='exact quarter-circle profiles, straight sweeps and toroidal corner revolutions';r['corner_inner_floor_radius']=2.2-floor_radius
 # New diagonal families follow the solid web adjacent to selected channel exits.
 anchors=ventilation.rib_anchors(p,normal_pitch=rib_pitch)
 lines,step=layout(p,anchors,rib_pitch)
 connections=[]
 all_lines=lines+connections
 stage('grid fuse');pieces=[strip(a,b,rib_width,h=extrusion).fuse(Part.makeCylinder(rib_width/2,extrusion,V(a[0],a[1],2.95))).fuse(Part.makeCylinder(rib_width/2,extrusion,V(b[0],b[1],2.95))) for a,b in all_lines]
 pieces += [Part.makeCylinder(4,extrusion,V(x,y,2.95)) for x,y in MOUNTS]+[Part.makeCylinder(5,extrusion,V(x,y,2.95)) for x,y in CASES]
 grid=pieces[0].multiFuse(pieces[1:]).removeSplitter()
 assert grid.Solids and grid.Volume>1000,'Invalid raw regular grid'
 # Round every vertical grid junction where OCC accepts a single global fillet.
 stage('node fillets');ves=[]
 for e in grid.Edges:
  b=e.BoundBox
  if b.ZLength>rib_height-.01 and b.XLength<1e-5 and b.YLength<1e-5:
   point=e.CenterOfMass;count=sum(grid.isInside(V(point.x+.03*math.cos(k*math.pi/4),point.y+.03*math.sin(k*math.pi/4),3+rib_height/2),1e-7,False) for k in range(8))
   if count>=5:ves.append(e)
 try:
  q=grid.makeFillet(node_radius,ves)
  if q.isNull() or not q.Solids or q.Volume<grid.Volume-.001 or not q.isValid():raise ValueError('invalid or empty grid fillet')
  grid=q;r['grid_node_fillet_edges']=len(ves);r['grid_nodes_rounded']=True
 except Exception as ex:
  stage('planar round closing')
  fs=[f for f in grid.Faces if f.BoundBox.ZLength<1e-5 and abs(f.BoundBox.ZMin-2.95)<1e-5]
  face=Part.makeCompound(fs) if len(fs)>1 else fs[0]
  expanded=face.makeOffset2D(node_radius,0,False,False,True)
  closed=expanded.makeOffset2D(-node_radius,0,False,False,True)
  q=pos(closed.extrude(V(0,0,extrusion)))
  if q.isNull() or not q.isValid():raise ValueError('Planar node rounding failed')
  removed=grid.cut(q).Volume
  if removed>1e-3:raise ValueError('Planar closing unexpectedly removed '+str(removed)+' mm3')
  added=q.cut(grid).Volume;grid=q;r['grid_nodes_rounded']=True;r['grid_rounding_method']='planar circular closing R1 after global 3D fillet declined';r['grid_rounding_added_volume']=added

 # Fillet the isolated grid/floor junction before adding detailed walls and mounting cavities.
 stage('isolated grid roots')
 plate=Part.makeBox(300,215.95,3,V(-10.3,-219,0));pedges=[e for e in plate.Edges if e.BoundBox.ZLength>2.99 and e.BoundBox.XLength<1e-6 and e.BoundBox.YLength<1e-6];plate=plate.makeFillet(5,pedges)
 rooted=plate.fuse(grid,.0001).removeSplitter()
 es=[e for e in rooted.Edges if e.BoundBox.ZLength<1e-5 and abs(e.BoundBox.ZMin-3)<1e-5 and e.BoundBox.XMin>-9 and e.BoundBox.XMax<288.4 and e.BoundBox.YMin>-217.5 and e.BoundBox.YMax<-4.5]
 try:
  qroot=rooted.makeFillet(rib_root,es)
  previous_rooted=rooted;rooted=qroot
  if rooted.isNull() or not rooted.Solids or rooted.Volume<plate.Volume+grid.Volume-1000 or not rooted.isValid():raise ValueError('isolated floor root invalid or empty')
  r['rib_roots_applied']=True;r['rib_root_edges']=len(es);r['rib_root_method']='isolated floor and rounded grid before walls/cuts'
 except Exception as ex:
  if 'previous_rooted' in locals():rooted=previous_rooted
  raise ValueError('Requested rib root fillet failed: '+str(ex))
 grid=rooted
 # Conservative electronics masks apply ONLY to added reinforcement.
 stage('component masks');inv=inventory;masks=[]
 for o in inv:
  b=o['bbox']
  if all(abs(v)<10000 for v in b) and b[3]-b[0]>.001 and b[4]-b[1]>.001 and b[2]<13 and b[5]>3 and b[3]-b[0]<290 and b[4]-b[1]<210 and o['name']!='Pcb_cd8b':
   masks.append(Part.makeBox(b[3]-b[0]+.6,b[4]-b[1]+.6,max(.01,16-b[2]+.3),V(b[0]-.3,b[1]-.3,b[2]-.3)))
 clip=Part.makeBox(300,215.95,20,V(-10.3,-219,0));grid=grid.common(clip)
 if masks:grid=trim(grid,masks)
 assert not grid.isNull() and grid.Volume>190000,'Empty/missing grid floor after masks'
 # Triangular perimeter gussets: underside PCB13 minus .3; electronics masks reduce locally.
 stage('gussets');gus=[];ginfo=[]
 def gusset(x,y,dx,dy,label):
  n=V(-dy,dx,0);p=V(x,y,2.99);ps=[p-n,p+V(10*dx,10*dy,0)-n,p+V(0,0,9.71)-n]
  s=pos(Part.Face(Part.makePolygon(ps+[ps[0]])).extrude(n*2))
  if masks:s=trim(s,masks)
  gus.append(s);ginfo.append({'label':label,'root':[x,y],'requested_top':12.7})
 for y in [-210,-187,-109.5,-32]:
  gusset(-7.6,y,1,0,'left');gusset(287,y,-1,0,'right')
 for x in [35,90,139.7,190,245]:gusset(x,-216.3,0,1,'front')
 for x in [25,62,110,148.59,220,260]:gusset(x,-5.75,0,-1,'rear')
 stage('post roots');roots=[root(x,y,4,post_radius) for x,y in MOUNTS]+[root(x,y,5,post_radius) for x,y in CASES]
 stage('additions fuse');additions=grid;seq=[]
 for i,q in enumerate(gus+roots+roots_perimeter):
  q=pos(q)
  if q.isNull() or q.Volume<1e-7:continue
  q.check(True);before=additions.Volume;candidate=additions.fuse(q,.0001)
  assert not candidate.isNull() and candidate.Solids and candidate.Volume>=before-.001,'Additions material loss at'+str(i)
  seq.append({'i':i,'before':before,'part_volume':q.Volume,'after':candidate.Volume});additions=candidate
 r['sequential_additions']=seq
 if masks:additions=trim(additions,masks)
 assert additions.Volume>190000,'Empty additions after masks'
 # Preserve channel exits, not just wall holes: continue each air corridor 12mm inward.
 stage('air corridors');air=ventilation.side_cutters(p,inward_extension=11.95)
 airshape=Part.makeCompound(air);additions=additions.cut(airshape).removeSplitter()
 stage('final fuse')
 try:out=base.fuse(additions,.0001);r['fuzzy_union_tolerance']=.0001
 except Exception:out=base.fuse(additions,0.0001);r['fuzzy_union_tolerance']=.0001
 assert out.Volume>=base.Volume-1e-3,'Union lost base volume'
 missing=base.cut(out);r['base_missing_after_union_mm3']=missing.Volume
 assert missing.Volume<.001,'Union removed actual base material'
 out.check(True);r['union_bop']='PASS'
 # Functional cavities remain exact; no reinforcement inside eleven bores.
 stage('functional holes');
 for x,y in MOUNTS:out=out.cut(Part.makeCylinder(2,6.8,V(x,y,6.3)))
 for x,y in CASES:out=out.cut(Part.makeCylinder(1.7,18,V(x,y,-1))).cut(Part.makeCylinder(3.3,4.2,V(x,y,-1)))
 out=out.cut(airshape)
 out.check(True);r['final_bop']='PASS'
 r.update({'valid':out.isValid(),'solids':len(out.Solids),'volume':out.Volume,'diagonal_lines':lines,'local_post_links':connections,'gussets':ginfo,'normal_pitch':[step*math.sin(math.radians(p.SideSlotAngle))],'component_masks':len(masks),'channel_count':len(air),'channel_common':out.common(airshape).Volume,'bbox':bbox(out.BoundBox)})
 return out,r,grid
