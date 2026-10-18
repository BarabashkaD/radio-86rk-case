import FreeCAD as A,Part
V=A.Vector
def box(x0,x1,y0,y1,z0,z1):return Part.makeBox(x1-x0,y1-y0,z1-z0,V(x0,y0,z0))
def parts():
 beam=box(138,157,-31.4,-30.2,37,40.2)
 root=box(136,139,-31.4,-27.6,37,40.2)
 yz=[(-33,37.5),(-32.2,36.8),(-30.2,36.8),(-30.2,38),(-33,38)]
 pp=[V(154,y,z) for y,z in yz];hook=Part.Face(Part.makePolygon(pp+[pp[0]])).extrude(V(3,0,0))
 return beam,root,hook
def modify(hatch,H):
 shift=A.Vector(0,0,H-41)
 hole=box(139,160,-31.7,-27.8,36.5,41.2);hole.translate(shift);hatch=hatch.cut(hole)
 items=list(parts())
 for q in items:q.translate(shift)
 return hatch.multiFuse(items).removeSplitter()
