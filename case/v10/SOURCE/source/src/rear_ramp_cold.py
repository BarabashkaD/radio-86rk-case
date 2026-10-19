import FreeCAD as A,Part,math
import rounded_joint_v10 as gj
V=A.Vector;OX=-10.3;CY=-8.05;CX=-5.3

def faces(z,y):
 lo,up=gj.profiles(z,60)
 lo[:4]=[(0,-30),(18,-30),(18,-27),(2.8,-27)]
 out=[]
 for pts in (lo,up):
  es=[];start=last=V(OX+pts[0][0],y,pts[0][1])
  for p in pts[1:]:
   if p[0]=='arc':end=V(OX+p[2][0],y,p[2][1]);es.append(Part.Arc(last,V(OX+p[1][0],y,p[1][1]),end).toShape())
   else:end=V(OX+p[0],y,p[1]);es.append(Part.makeLine(last,end))
   last=end
  es.append(Part.makeLine(last,start));f=Part.Face(Part.Wire(es))
  # Clip profile to the wall band, leaving fixed bottom/roof trimming for after sweep.
  vv=[V(OX,y,-35),V(OX+2.8,y,-35),V(OX+2.8,y,65),V(OX,y,65)];f=f.common(Part.Face(Part.makePolygon(vv+[vv[0]])))
  out.append(f)
 return out

_cache={}
def build(length=20):
 if not 5<=length<=45: raise ValueError("RampLength must be between 5 and 45 mm for this local study")
 clip=Part.makeBox(2.8,100,37.5,V(OX,-80,0))
 parts=[[],[]]
 for y,z,dy,dz in [(-60,16.2,50-length,0),(-10-length,16.2,length,5.4),(-10,21.6,1.95,0)]:
  for i,f in enumerate(faces(z,y)):parts[i].append(f.extrude(V(0,dy,dz)).common(clip))
 # Exact concentric corner: outer R5 / inner R2.2; unchanged transverse G profile.
 for i,f in enumerate(faces(21.6,CY)):
  solid=f.revolve(V(CX,CY,0),V(0,0,1),-90)
  ring=Part.makeCylinder(5,37.5,V(CX,CY,0)).cut(Part.makeCylinder(2.2,38,V(CX,CY,-.1)))
  quad=Part.makeBox(5,5,37.5,V(OX,CY,0));parts[i].append(solid.common(ring).common(quad))
  f.rotate(V(CX,CY,0),V(0,0,1),-90)
  rear=f.extrude(V(25,0,0)).common(Part.makeBox(25,2.8,37.5,V(CX,-5.85,0)));parts[i].append(rear)
 sh=[]
 for pp in parts:
  s=pp[0].multiFuse(pp[1:]).removeSplitter();sh.append(s)
 return sh
