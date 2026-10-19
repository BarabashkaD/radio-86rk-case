import FreeCAD as A,Part,math
V=A.Vector
def normal(f,p):
 uv=f.Surface.parameter(p);return f.normalAt(*uv)
def profile(p,n,N,r=.6):
 if N.z<0:N=-N
 n.normalize();N.normalize();k=n.dot(N);assert abs(k)<.999
 center=p+(n-N)*(r/(1-k));a=center+N*r;b=center-n*r
 direction=center-p;direction.normalize();mid=center-direction*r
 points=[p-n*.05+N*.05,a+N*.05,a,b,b-n*.05]
 return Part.Wire([Part.makeLine(points[0],points[1]),Part.makeLine(points[1],points[2]),Part.Arc(a,mid,b).toShape(),Part.makeLine(points[3],points[4]),Part.makeLine(points[4],points[0])])
def build_one(net,plan,masks,cavity,index,radius=.6):
 prism=plan.extrude(V(0,0,40))
 if prism.Volume<0:prism.reverse()
 e=net.Edges[index];u0,u1=e.ParameterRange;p=e.valueAt((u0+u1)/2)
 adj=[f for f in net.Faces if any(a.isSame(e) for a in f.Edges)]
 sides=[f for f in adj if abs(normal(f,p).z)<1e-7]
 assert sides,'No vertical rib-side face'
 side=sides[0]
 # The compound network carries duplicate coplanar side faces on these
 # trimming seams. Obtain the roof from the actual cavity BOUNDARY.
 roofs=[f for f in cavity.Faces if abs(normal(f,p).z)>.05 and f.distToShape(Part.Vertex(p))[0]<1e-5]
 assert roofs,'Point is not on roof boundary'
 roof=roofs[0]

 def wire(u):
  q=e.valueAt(u);n=normal(side,q);probe=V(q.x,q.y,1)+n*.02
  if prism.isInside(probe,1e-7,False):n=-n
  return profile(q,n,normal(roof,q),radius)
 constant_normals=(normal(side,e.valueAt(u0))-normal(side,e.valueAt(u1))).Length<1e-7 and (normal(roof,e.valueAt(u0))-normal(roof,e.valueAt(u1))).Length<1e-7
 stations=[e.valueAt(u0),e.valueAt(u1)]
 if isinstance(e.Curve,Part.Line) and constant_normals:q=Part.Face(wire(u0)).extrude(e.valueAt(u1)-e.valueAt(u0));mode='exact extrusion'
 else:
  count=max(5,min(33,int(math.ceil(e.Length))+1));parameters=[u0+(u1-u0)*i/(count-1) for i in range(count)];stations=[e.valueAt(u) for u in parameters];q=Part.makeLoft([wire(u) for u in parameters],True,False);mode='sampled loft; radius between stations not certified'
 if q.Volume<0:q.reverse()
 b=q.BoundBox;near=[m for m in masks.Solids if m.BoundBox.XMin<b.XMax and m.BoundBox.XMax>b.XMin and m.BoundBox.YMin<b.YMax and m.BoundBox.YMax>b.YMin and m.BoundBox.ZMin<b.ZMax and m.BoundBox.ZMax>b.ZMin]
 if near:q=q.cut(Part.makeCompound(near))
 q.check(True);assert q.isValid() and q.Volume>0
 return q,{'edge':index,'mode':mode,'radius_nominal':radius,'volume':q.Volume,'solids':len(q.Solids),'BOP':'PASS','constant_endpoint_normals':constant_normals,'max_station_chord':max((b-a).Length for a,b in zip(stations,stations[1:]))}
