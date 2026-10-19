import FreeCAD as A,Part,math,json
from pathlib import Path
R=Path('/workspace/scratch/072ad2dfcea4/radio_case_v10_work');V=A.Vector

def profiles(z=16.2,roof=37.5):
 h=2.;r=.3;R=.6;c=.3;t=2.8;rt=2 if roof<25 else 2.8
 lo=[(0,0),(18,0),(18,3),(t,3),(t,z+h-.3),(t-.3,z+h),(1.9,z+h),('arc',(1.9-r/math.sqrt(2),z+h-r+r/math.sqrt(2)),(1.6,z+h-r)),(1.6,z+r),('arc',(1.3+r/math.sqrt(2),z+r-r/math.sqrt(2)),(1.3,z)),(.3,z),(0,z-.3)]
 up=[(0,z+.3),(.3,z),(1.,z),('arc',(1+r/math.sqrt(2),z+r-r/math.sqrt(2)),(1.3,z+r)),(1.3,z+h+c-R),('arc',(1.9-R/math.sqrt(2),z+h+c-R+R/math.sqrt(2)),(1.9,z+h+c)),(2.8,z+h+c),(2.8,roof-rt),(18,roof-rt),(18,roof),(0,roof)]
 return lo,up

def shape(pts,y=-109.5,length=20):
 edges=[];start=last=V(-4.3+pts[0][0],y,pts[0][1])
 for p in pts[1:]:
  if p[0]=='arc':mid=V(-4.3+p[1][0],y,p[1][1]);end=V(-4.3+p[2][0],y,p[2][1]);edges.append(Part.Arc(last,mid,end).toShape())
  else:end=V(-4.3+p[0],y,p[1]);edges.append(Part.makeLine(last,end))
  last=end
 edges.append(Part.makeLine(last,start));return Part.Face(Part.Wire(edges)).extrude(V(0,length,0))
class Proxy:
 def __init__(self,o,role):self.role=role;o.Proxy=self
 def execute(self,o):
  p=o.Parameters;lo,up=profiles(p.PCBTop.Value+p.SeamAbovePCB.Value,20.6 if self.role=='keyboard' else 37.5)
  o.Shape=shape(lo if self.role=='lower' else up)
  if self.role=='keyboard':o.Shape.translate(V(32,0,0))
 def dumps(self):return self.role
 def loads(self,v):self.role=v

def build():
 d=A.newDocument('Radio86_v10_RoundedJoint');d.Label='v10 rounded side joint · local study'
 p=d.addObject('App::FeaturePython','Parameters')
 for n,val in [('PCBTop',14.6),('SeamAbovePCB',1.6)]:p.addProperty('App::PropertyLength',n,'Joint');setattr(p,n,val)
 for name,role,col in [('LowerLocal','lower',(.85,.61,.26)),('UpperRear','rear',(.3,.46,.62)),('UpperKeyboard','keyboard',(.3,.46,.62))]:
  o=d.addObject('PartDesign::FeaturePython',name);o.addProperty('App::PropertyLink','Parameters');o.Parameters=p;Proxy(o,role);o.ViewObject.ShapeColor=col
 d.recompute();report={'status':'LOCAL_STUDY_NOT_FULL_CASE','side_seam_z':16.2,'tongue_height':2.,'tongue_top':18.2,'rebate_ceiling':18.5,'clearance_below_keyboard_inside':.1,'radii':{'upper_rebate':.6,'tongue_tip':.3,'lower_root':.3,'upper_lip_tip':.3},'top_radial_gap':.3,'bottom_nominal_contact_width':.7,'parts':{}}
 for name in ['LowerLocal','UpperRear','UpperKeyboard']:
  s=d.getObject(name).Shape;report['parts'][name]={'valid':s.isValid(),'solids':len(s.Solids),'volume':s.Volume}
 report['common_mm3']=d.LowerLocal.Shape.common(d.UpperRear.Shape).Volume
 report['sections']={}
 for name in ['LowerLocal','UpperRear']:
  ws=d.getObject(name).Shape.slice(V(0,1,0),-100.)
  report['sections'][name]=[[[p.x+4.3,p.z] for p in w.discretize(Deflection=.002)] for w in ws]
 d.saveAs(str(R/'Radio86_v10_rounded_joint_study.FCStd'));json.dump(report,open(R/'rounded_joint_report.json','w'),indent=2)
 A.Gui.activeDocument().activeView().viewAxonometric();A.Gui.activeDocument().activeView().fitAll();print(report['parts'],report['common_mm3'])
