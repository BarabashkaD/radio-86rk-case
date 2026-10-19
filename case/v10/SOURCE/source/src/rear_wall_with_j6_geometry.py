"""Single extruded rounded G-profile; approved port and J6 functions are cutters.
No cropped wall fragments or artificial X115/X181 material seams.
"""
import FreeCAD as A,Part
import rounded_joint_v10 as gj
V=A.Vector

def build_half(which=0):
 pts=gj.profiles(21.6,37.5)[which];es=[];first=last=V(-10.3,-3.05-pts[0][0],pts[0][1])
 for p in pts[1:]:
  if p[0]=='arc':end=V(-10.3,-3.05-p[2][0],p[2][1]);es.append(Part.Arc(last,V(-10.3,-3.05-p[1][0],p[1][1]),end).toShape())
  else:end=V(-10.3,-3.05-p[0],p[1]);es.append(Part.makeLine(last,end))
  last=end
 es.append(Part.makeLine(last,first));lo=Part.Face(Part.Wire(es)).extrude(V(300,0,0))
 lo=lo.cut(Part.makeBox(5.6,4,3.1,V(18.793,-6.5,21.6)))
 if which==1:lo=lo.fuse(Part.makeBox(5.6,2.8,3.1,V(18.793,-5.85,21.6)))
 for xa,xb,zt in [(181.0964,212.4964,27.4),(92.21,113.51,36.36),(31.84,41.44,27.04),(19.293,23.893,21.6)]:
  za=14.6;cut=Part.makeBox(xb-xa,8.4,zt-za,V(xa,-9.4,za))
  def rect(y,q):
   p=[V(xa-q,y,za),V(xb+q,y,za),V(xb+q,y,zt+q),V(xa-q,y,zt+q)];return Part.makePolygon(p+[p[0]])
  cut=cut.fuse(Part.makeLoft([rect(-3.55,0),rect(-3.05,.5)],True,False));lo=lo.cut(cut)
 rca=Part.makeCylinder(5.6,8.4,V(234.95,-9.4,21.6),V(0,1,0)).fuse(Part.makeCone(5.6,6.1,.5,V(234.95,-3.55,21.6),V(0,1,0)))
 lo=lo.cut(rca).cut(Part.makeBox(10.85,5.07,29.125,V(45.375,-10.5,4.55)))
 xa,xb=123.25,173.93;ay,az=-4.45,16.25
 lo=lo.cut(Part.makeBox(xb-xa,35,30,V(xa,-27.85,14.6)))
 for x,sgn in ([(xa,-1),(xb,1)] if which==0 else []):
  lo=lo.fuse(Part.makeCylinder(1.65,3,V(x if sgn==1 else x-3,ay,az),V(1,0,0))).cut(Part.makeSphere(1.15,V(x,ay,az)))
 p=[V(xa,-3.05,14.6),V(xa,-3.05,13.4),V(xa,-5.05,14.6)]
 lo=lo.cut(Part.Face(Part.makePolygon(p+[p[0]])).extrude(V(xb-xa,0,0)))
 lo.check(True);assert lo.isValid() and (len(lo.Solids)==1 if which==0 else len(lo.Solids)>=1)
 return lo

def build_lower():return build_half(0)
def build_upper():return build_half(1)
