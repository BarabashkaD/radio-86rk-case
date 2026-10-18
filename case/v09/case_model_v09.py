"""Radio86 enclosure: recomputable FreeCAD FeaturePython geometry, invoked through MCP.
All dimensions mm. Source electronic assembly never saved or geometrically edited.
"""
import FreeCAD as A, Part, math, json
CACHE={}
def box(x0,x1,y0,y1,z0,z1):
 return Part.makeBox(x1-x0,y1-y0,z1-z0,A.Vector(x0,y0,z0))
def cyl(r,z0,z1,x,y):return Part.makeCylinder(r,z1-z0,A.Vector(x,y,z0))
def fuse(ss):
 ss=[s for s in ss if not s.isNull()]
 return ss[0].multiFuse(ss[1:]).removeSplitter() if len(ss)>1 else ss[0]
def cut(s,ss):return s.cut(Part.makeCompound(ss)).removeSplitter() if ss else s

def profile(x0,x1,yz):
 start=A.Vector(x0,*yz[0]);last=start;edges=[]
 for item in yz[1:]:
  if item[0]=='arc':
   mid=A.Vector(x0,*item[1]);end=A.Vector(x0,*item[2]);edges.append(Part.Arc(last,mid,end).toShape());last=end
  else:
   end=A.Vector(x0,*item);edges.append(Part.makeLine(last,end));last=end
 edges.append(Part.makeLine(last,start))
 return Part.Face(Part.Wire(edges)).extrude(A.Vector(x1-x0,0,0))

class ShellProxy:
 def __init__(self,obj,role):obj.addProperty('App::PropertyString','Role').Role=role;obj.Proxy=self
 def execute(self,obj):obj.Shape=geometry(obj.Parameters)[obj.Role]
 def dumps(self):return None
 def loads(self,state):pass

def geometry(p):
 key=tuple(float(getattr(p,n)) for n in PARAMS)+ (p.LayoutData,)
 if key in CACHE:return CACHE[key]
 v={n:float(getattr(p,n)) for n in PARAMS};data=json.loads(p.LayoutData)
 W=v['Width'];x0=139.7-W/2;x1=139.7+W/2;y0=v['FrontY'];y1=v['RearY'];t=v['Wall'];floor=v['Floor'];seam=v['SeamZ'];pcb=v['PCBTop'];deck=pcb+v['GrilleTop'];H=v['Height'];a=math.radians(v['SlopeAngle']);ys=v['SlopeStartY'];ye=ys+(H-deck)/math.tan(a);j=ys+(t/math.cos(a)-v['GrilleThickness'])/math.tan(a)
 R=v['UpperTransitionRadius'];Ri=R-t;cy=ye+R*math.tan(a/2);cz=H-R
 ob=(cy-R*math.sin(a),cz+R*math.cos(a));om=(cy-R*math.sin(a/2),cz+R*math.cos(a/2))
 ib=(cy-Ri*math.sin(a),cz+Ri*math.cos(a));im=(cy-Ri*math.sin(a/2),cz+Ri*math.cos(a/2))
 outerYZ=[(y0,0),(y1,0),(y1,H),(cy,H),('arc',om,ob),(ys,deck),(y0,deck)]
 # Separate floor and walls, then the continuous roof profile.
 base=box(x0,x1,y0,y1,0,seam).cut(box(x0+t,x1-t,y0+t,y1-t,floor,seam+1))
 side=profile(x0,x1,outerYZ).cut(box(x0+t,x1-t,y0+t,y1-t,-1,H+1)).common(box(x0-1,x1+1,y0-1,y1+1,seam,H+1))
 roof=profile(x0+t-.1,x1-t+.1,[(y0+t,deck-v['GrilleThickness']),(j,deck-v['GrilleThickness']),ib,('arc',im,(cy,H-t)),(y1,H-t),(y1,H),(cy,H),('arc',om,ob),(ys,deck),(y0+t,deck)])
 top=fuse([side,roof])
 # Stationary switch/stabilizer apertures, preserving full key travel above low deck.
 windows=[]
 for b in data['switch_windows']:
  windows.append(box(b[0]-v['SwitchSideClearance'],b[3]+v['SwitchSideClearance'],b[1]-v['SwitchSideClearance'],b[4]+v['SwitchSideClearance'],deck-3,deck+1))
 for x,y in [(206.375,-104.775),(225.425,-104.775)]:windows.append(cyl(v['LEDAperture']/2,deck-3,pcb+10,x,y))
 top=cut(top,windows)
 # All seven PCB posts. Insert blind bores deliberately interference-fit, provisional.
 posts=[]
 for x,y in data['mounts']:
  post=cyl(v['BossDiameter']/2,floor-.1,pcb-1.6,x,y)
  post=post.cut(cyl(v['InsertPilot']/2,pcb-1.6-v['InsertDepth'],pcb,x,y))
  posts.append(post)
 # Four completely independent shell screw pedestals and downward-opening upper bosses.
 shell_axes=[(x0+5.65,-24),(x1-5.65,-24),(x0+5.65,-198),(x1-5.65,-198)]
 lower=[];upper=[];holes=[]
 for x,y in shell_axes:
  lo=cyl(4,floor-.1,seam,x,y)
  # rectangular attachment to wall, overlapped with cylinder and wall.
  wallx=x0 if x<(x0+x1)/2 else x1-t
  lo=fuse([lo,box(min(wallx,x),max(wallx+t,x),y-3,y+3,floor-.1,seam)])
  lower.append(lo)
  roofz=deck-v['GrilleThickness'] if y<ys else H-t
  up=cyl(4,seam,roofz+.1,x,y)
  up=fuse([up,box(min(wallx,x),max(wallx+t,x),y-3,y+3,seam,roofz+.1)])
  upper.append(up.cut(cyl(v['InsertPilot']/2,seam-.1,seam+v['InsertDepth'],x,y)))
  holes.extend([cyl(1.7,-1,seam+.1,x,y),cyl(3.3,-1,3.2,x,y)])
 base=cut(fuse([base]+posts+lower),holes);top=fuse([top]+upper)
 # Recessed feet, non-ventilated bottom.
 feet=[];footcuts=[]
 for x,y in [(x0+15,y0+15),(x1-15,y0+15),(x0+15,y1-15),(x1-15,y1-15)]:
  footcuts.append(cyl(5.2,-1,1,x,y));feet.append(cyl(5,-1,1,x,y))
 base=cut(base,footcuts)
 # Rear connector openings are open across the split; conservative body + provisional mating clearance.
 ports=[]
 for ref in ['J1','J2','J4','J5','SW68']:
  b=data['components'][ref];zlo=max(floor+.7,b[2]+pcb-.6);zhi=b[5]+pcb+.8
  ports.append(box(b[0]-.8,b[3]+.8,y1-t-4,y1+3,zlo,zhi))
 b=data['components']['U25'];insidePocket=box(b[0]-.3,b[3]+.3,b[1]-.3,b[4]+.3,max(floor,b[2]+pcb-.3),b[5]+pcb+.3)
 base=cut(base,ports+[insidePocket]);top=cut(top,ports+[insidePocket])
 # Open upper port slots to the parting seam, allowing vertical removal.
 portEntrances=[]
 for ref in ['J1','J2','J4','J5','SW68']:
  b=data['components'][ref];portEntrances.append(box(b[0]-.8,b[3]+.8,y1-t-4,y1+3,seam-.1,b[5]+pcb+.8))
 b=data['components']['U25']
 top=cut(top,portEntrances+[box(b[0]-.3,b[3]+.3,b[1]-.3,b[4]+.3,seam-.1,b[5]+pcb+.3)])
 # J3 is a vertical connector: real top access, J7 remains internal.
 b=data['components']['J3']
 if v['J3TopAccess']>0:top=top.cut(box(b[0]-2,b[3]+2,b[1]-2,b[4]+2,H-t-.1,H+.1))
 # J6 L-hatch, separate replaceable cover; clearance and pin hinge provisional.
 hx0=118.5;hx1=178.5;hy=-32;hz=18;gap=v['HatchGap'];axY=y1+v['HatchAxisOffsetY'];axZ=v['HatchAxisZ']
 hatchcut=fuse([box(hx0,hx1,hy,y1+1,H-t-.1,H+.1),box(hx0,hx1,y1-t-.1,y1+.1,hz,H+.1)])
 top=top.cut(hatchcut)
 hatch=fuse([box(hx0+gap,hx1-gap,hy+gap,y1-gap,H-t,H),box(hx0+gap,hx1-gap,y1-t,y1-gap,hz+gap,H)])
 # Small pull recess, no claimed cable closure path until actual IDC plug supplied.
 hatch=hatch.cut(box(143,154,hy+gap,hy+gap+2,H-1.3,H+.1))
 pin=Part.makeCylinder(1.2,hx1-hx0-1,A.Vector(hx0+.5,axY,axZ),A.Vector(1,0,0))
 if v['Ventilation']>0:
  # Approved overlapping, constant-thickness louvers; all blades fused into deep frames.
  q=t/math.sqrt(2);P=10;L=11.5;poly=[(q,0),(L,L-q),(L-q,L),(0,q)]
  topcuts=[];frames=[];blades=[]
  field_count=int(v['TopVentRegions']);bridge=6.;field_width=(255.-bridge*(field_count-1))/field_count
  for field in range(field_count):
   xa=12.+field*(field_width+bridge);xb=xa+field_width
   ya,yb=-70,-38.5
   theta=math.radians(10 if field==2 else 20)
   pitch=3.45 if field==2 else 5.0
   projection=3.9 if field==2 else 6.2
   aa=t*math.cos(theta);bb=t*math.sin(theta)
   vv=(projection-aa)/math.tan(theta);depth=vv+bb
   top_poly=[(aa,0),(projection,vv),(projection-aa,depth),(0,bb)]
   zl=H-depth
   topcuts.append(box(xa,xb,ya,yb,zl-.1,H+.1))
   for xx0,xx1 in [(xa-t,xa+(.3 if field!=2 else 0)),(xb-(.3 if field!=2 else 0),xb+t)]:frames.append(box(xx0,xx1,ya-t,yb+t,zl,H))
   for yy0,yy1 in [(ya-t,ya+(.3 if field==2 else 0)),(yb-(.3 if field==2 else 0),yb+t)]:frames.append(box(xa-t,xb+t,yy0,yy1,zl,H))
   for blade in range(9):
    reverse=field>=2
    pts=[(blade*pitch+(projection-u if reverse else u),H-v) for u,v in top_poly]
    if field==2:
     blades.append(profile(xa-1,xb+1,[(ya+u,z) for u,z in pts]))
    else:
     pp=[A.Vector(xa+u,ya-1,z) for u,z in pts]
     blades.append(Part.Face(Part.makePolygon(pp+[pp[0]])).extrude(A.Vector(0,yb-ya+2,0)))
  top=fuse([cut(top,topcuts)]+frames+blades)
  sidecuts=[];sideblades=[]
  for left in [True,False]:
   xedge=x0 if left else x1
   for ya,yb in [(-184,-112.5),(-106.5,-35)]:
    sidecuts.append(box(x0-.1,x0+t+.1,ya,yb,5,10.001) if left else box(x1-t-.1,x1+.1,ya,yb,5,10.001))
    for i in range(7):
     pts=[A.Vector(xedge+vv if left else xedge-vv,ya+i*P+u,2.8) for u,vv in poly]
     sideblades.append(Part.Face(Part.makePolygon(pts+[pts[0]])).extrude(A.Vector(0,0,7.4)))
    for yy0,yy1 in [(ya-t,ya+.3),(yb-.3,yb+t)]:sideblades.append(box(x0,x0+L,yy0,yy1,2.8,10.2) if left else box(x1-L,x1,yy0,yy1,2.8,10.2))
  base=fuse([cut(base,sidecuts)]+sideblades)
  # Avoid overlap at seam: upper shell relieved above the side intake blades.
  top=cut(top,[box(x0-.1,x0+L+.25,ya-.1,yb+.1,9.999,10.45) if left else box(x1-L-.25,x1+.1,ya-.1,yb+.1,9.999,10.45) for left in [True,False] for ya,yb in [(-186.8,-109.7),(-109.3,-32.2)]])
 # Explicit floor ribs distribute keyboard/post loads; free air space remains above.
 ribs=[]
 if v['RibHeight']>0:
  for xx in [45.,140.,235.]:ribs.append(box(xx-v['RibThickness']/2,xx+v['RibThickness']/2,-205,-35,floor-.1,floor+v['RibHeight']))
  for yy in [-180.,-145.,-110.,-75.]:ribs.append(box(14,265,yy-v['RibThickness']/2,yy+v['RibThickness']/2,floor-.1,floor+v['RibHeight']))
  # Analytic quarter-circle root fillets, radius0.8, around the seven posts.
  for x,y in data['mounts']:
   rr=v['BossDiameter']/2;R=.8;z=floor
   pp0=A.Vector(0,0,z);pp1=A.Vector(rr+R,0,z);pp2=A.Vector(rr,0,z+R)
   mid=A.Vector(rr+R-R/math.sqrt(2),0,z+R-R/math.sqrt(2))
   wire=Part.Wire([Part.makeLine(pp0,pp1),Part.Arc(pp1,mid,pp2).toShape(),Part.makeLine(pp2,A.Vector(0,0,z+R)),Part.makeLine(A.Vector(0,0,z+R),pp0)])
   root=Part.Face(wire).revolve(A.Vector(0,0,0),A.Vector(0,0,1),360);root.translate(A.Vector(x,y,0));ribs.append(root)
  base=fuse([base]+ribs)
  base=cut(base,[cyl(v['InsertPilot']/2,pcb-1.6-v['InsertDepth'],pcb,x,y) for x,y in data['mounts']])
 # Registration tongue, with0.25mm clearance. Interrupted near independent fasteners.
 lipOuter=box(x0+t-1.2,x1-t+1.2,y0+t-1.2,y1-t+1.2,seam-.1,seam+1.2)
 lip=lipOuter.cut(box(x0+t,x1-t,y0+t,y1-t,seam-.2,seam+1.4))
 gro=box(x0+t-1.45,x1-t+1.45,y0+t-1.45,y1-t+1.45,seam-.05,seam+1.45).cut(box(x0+t+.25,x1-t-.25,y0+t+.25,y1-t-.25,seam-.1,seam+1.5))
 interrupts=[box(x-5,x+5,y-6,y+6,seam-.2,seam+2) for x,y in shell_axes]
 lip=cut(lip,interrupts+ports);gro=cut(gro,interrupts)
 endMask=fuse([box(x0-1,x1+1,y0-1,y0+8,seam-1,seam+4),box(x0-1,x1+1,y1-8,y1+1,seam-1,seam+4)])
 lip=lip.common(endMask);gro=gro.common(endMask)
 base=fuse([base,lip]);top=top.cut(gro)
 # Matched outer/inner corner radii keep nominal2.8mm wall thickness.
 Ri=v['CornerRadius']-t
 if Ri>0:
  fills=[]
  for xx,yy,sx,sy in [(x0,y0,1,1),(x1,y0,-1,1),(x0,y1,1,-1),(x1,y1,-1,-1)]:
   cx=xx+sx*v['CornerRadius'];cy=yy+sy*v['CornerRadius'];ix=xx+sx*t;iy=yy+sy*t
   fill=box(min(ix,cx),max(ix,cx),min(iy,cy),max(iy,cy),floor-.1,H+.1).cut(cyl(Ri,floor-.2,H+.2,cx,cy))
   fills.append(fill)
  fill=fuse(fills).common(profile(x0,x1,outerYZ))
  base=fuse([base,fill.common(box(x0,x1,y0,y1,floor-.1,seam))])
  top=fuse([top,fill.common(box(x0,x1,y0,y1,seam,H+.1))]).cut(gro)
 # Rounded vertical outer corners; foot contact planes remain flat.
 cornercuts=[]
 for xx,yy,sx,sy in [(x0,y0,1,1),(x1,y0,-1,1),(x0,y1,1,-1),(x1,y1,-1,-1)]:
  R=v['CornerRadius'];cx=xx+sx*R;cy=yy+sy*R
  corner=box(min(xx,cx),max(xx,cx),min(yy,cy),max(yy,cy),-.1,H+.1).cut(cyl(R,-.2,H+.2,cx,cy));cornercuts.append(corner)
 base=cut(base,cornercuts);top=cut(top,cornercuts)
 import grille_fill_v05
 top=grille_fill_v05.modify(top,p)
 # Seven hollow upper PCB contacts: nominal zero gap, no preload allowance.
 contacts=[]
 for x,y in data['mounts']:
  rr=v['UpperStopOD']/2;ri=v['UpperStopID']/2
  contact=cyl(rr,pcb+v['UpperStopGap'],H,x,y).cut(cyl(ri,pcb-.1,H+.1,x,y))
  # Thickened tapered root only on the two long rear sleeves, above electronics.
  if y>-20:
   z=H-t-1.4
   root=Part.makeCone(rr,rr+.8,1.5,A.Vector(x,y,z)).cut(cyl(ri,z-.1,z+1.6,x,y))
   contact=contact.fuse(root)
  contacts.append(contact.common(profile(x0,x1,outerYZ)))
 top=fuse([top]+contacts)
 # Local DIN face panel, aligned with metal flange; open top keeps main wall2.8.
 top=top.cut(box(88,118,-9.4,y1+.1,pcb+.3,H+.1))
 local=[box(88,118,-9.5,y1,H-t,H),box(88.44,92.21,-9.4,-6.6,pcb+.3,H),box(113.51,116.29,-9.4,-6.6,pcb+.3,H),box(88.44,90.8,-9.4,y1,pcb+.3,H),box(115.2,118,-9.4,y1,20.1,H)]
 local=fuse(local).cut(box(92.21,113.51,-8.9,y1+.1,pcb+.3,36.36))
 top=fuse([top,local])
 # Separate acoustic grille over the imported SP1 centre; sound performance unknown.
 holes=[cyl(.75,H-t-.1,H+.1,257.8088, -13.97)]
 for k in range(6):
  ang=k*math.pi/3;holes.append(cyl(.75,H-t-.1,H+.1,257.8088+2.75*math.cos(ang),-13.97+2.75*math.sin(ang)))
 top=cut(top,holes)
 import ports_v08
 top=ports_v08.modify(top,p).cut(gro)
 # Tool-less provisional PCTG latch replaces the two service screws.
 hatchAxes=[]
 import latch_v08
 hatch=latch_v08.modify(hatch,H)
 # Discrete hardware reference solids.
 screws=[];inserts=[]
 for x,y in shell_axes:
  screws.append(fuse([cyl(1.5,3.2,15.2,x,y),cyl(2.75,.2,3.2,x,y)]))
  inserts.append(cyl(2.3,seam,seam+5.7,x,y).cut(cyl(1.25,seam-.1,seam+5.8,x,y)))
 for x,y in data['mounts']:
  screws.append(fuse([cyl(1.5,pcb-6,pcb+.01,x,y),cyl(2.75,pcb,pcb+3,x,y)]))
  inserts.append(cyl(2.3,pcb-1.6-5.7,pcb-1.6,x,y).cut(cyl(1.25,pcb-8,pcb,x,y)))
 for x,y in hatchAxes:
  screws.append(fuse([cyl(1.5,31.2,39.2,x,y),cyl(2.85,39.2,40.9,x,y)]))
  inserts.append(cyl(2.3,30.75,36.45,x,y).cut(cyl(1.25,30.6,36.6,x,y)))
 import hinge_snap_candidate
 top,hatch,hingeReport=hinge_snap_candidate.build(top,axY,axZ,H,cut_sweep=False)
 import hinge_snap_finish
 top,hatch,finishReport=hinge_snap_finish.finish(top,hatch,axY,axZ)
 hingeReport['finishing']=finishReport
 hatch=latch_v08.modify(hatch,H)
 pin=Part.Shape();hingeHardware=Part.Shape()
 json.dump(hingeReport,open(__file__.replace('case_model_v09.py','hinge_report.json'),'w'),indent=2)
 import seam_snaps_v08
 base,top,seamReport=seam_snaps_v08.modify(base,top,p)
 json.dump(seamReport,open(__file__.replace('case_model_v09.py','seam_report.json'),'w'),indent=2)
 out={'HingeHardware':hingeHardware,'LowerShell':base.removeSplitter(),'UpperShell':top.removeSplitter(),'J6Hatch':hatch.removeSplitter(),'HingePin':pin,'Feet':Part.makeCompound(feet),'Screws':Part.makeCompound(screws),'Inserts':Part.makeCompound(inserts)}
 import feet_snap_v08
 ft=feet_snap_v08.build_foldout_feet(out['LowerShell'],p)
 for role in ['LowerShell','FoldFeet','FootHardware','Feet']:out[role]=ft[role]
 json.dump(ft['meta'],open(__file__.replace('case_model_v09.py','feet_report.json'),'w'),indent=2)
 import rib_grid_v09
 out['LowerShell'],out['UpperShell'],ribReport=rib_grid_v09.add_ribs(out['LowerShell'],out['UpperShell'],p,data)
 json.dump(ribReport,open(__file__.replace('case_model_v09.py','rib_report.json'),'w'),indent=2)
 CACHE.clear();CACHE[key]=out
 return out
PARAMS={'UpperTransitionRadius':10.,'CornerRadius':5.,'UpperStopOD':8.,'UpperStopID':6.2,'UpperStopGap':0.,'HatchAxisOffsetY':0.,'HatchAxisZ':25.7,'TopVentRegions':5.,'FootAngle':0.,'FootLift':14.,'FootAxisZ':2.5,'Width':288.,'FrontY':-219.,'RearY':-3.05,'Wall':2.8,'Floor':3.,'SeamZ':10.,'PCBTop':14.6,'GrilleTop':6.,'GrilleThickness':2.,'Height':37.5,'SlopeAngle':45.,'SlopeStartY':-95.,'SwitchSideClearance':.3,'LEDAperture':4.4,'BossDiameter':8.,'InsertPilot':4.,'InsertDepth':6.7,'HatchGap':.35,'Ventilation':1.,'RibHeight':0.,'RibThickness':1.6,'J3TopAccess':0.,'TopLouverReverse':1.}
