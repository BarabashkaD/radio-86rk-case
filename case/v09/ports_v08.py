import FreeCAD as A,Part,math
V=A.Vector
def box(x0,x1,y0,y1,z0,z1):return Part.makeBox(x1-x0,y1-y0,z1-z0,V(x0,y0,z0))
def fuse(ss):return ss[0].multiFuse(ss[1:]).removeSplitter()
def rib(x0,x1,inner_low,y0,y1,z0,z1):
 pts=[V(x0,y0,z1),V(x1,y0,z1),V(x1 if inner_low=='right' else x0,y0,z0)]
 return Part.Face(Part.makePolygon(pts+[pts[0]])).extrude(V(0,y1-y0,0))
def modify(top,p):
 H=float(p.Height);t=float(p.Wall);rear=float(p.RearY);pcb=float(p.PCBTop);seam=float(p.SeamZ)
 # RCA: rounded U aperture preserves vertical upper-shell assembly.
 panel=box(227,243,rear-t,rear,seam,H)
 circular=Part.makeCylinder(5.6,t+.2,V(234.95,rear-t-.1,21.6),V(0,1,0))
 opening=circular.fuse(box(229.35,240.55,rear-t-.1,rear+.1,seam-.1,21.6))
 opening=opening.fuse(Part.makeCone(5.6,6.1,.5,V(234.95,rear-.5,21.6),V(0,1,0))).fuse(box(228.85,241.05,rear-.5,rear+.1,seam-.1,21.6))
 top=fuse([top,panel.cut(opening)])
 # DC: local recessed face aligned with connector, supported above PCB only.
 face=-6.1701;inside=face-t
 top=top.cut(box(29.04,44.24,inside,rear+.1,pcb+.3,H+.1))
 dc=fuse([box(29.04,44.24,inside-.1,rear,H-t,H),box(29.04,31.84,inside,face,pcb+.3,H),box(41.44,44.24,inside,face,pcb+.3,H),box(29.04,44.24,inside,face,26.74,H),box(26.25,29.14,inside,rear,pcb+.3,H),box(44.14,45.37,inside,rear,33.675,H)])
 # Offset of body rectangle by0.3, with true radius0.3 top corners.
 y=inside-.2;r=.3;x0=31.84;x1=41.44;z=26.74
 p0=V(x0,y,seam-.1);p1=V(x1,y,seam-.1);p2=V(x1,y,z);p3=V(41.14,y,z+r);p4=V(32.14,y,z+r);p5=V(x0,y,z)
 edges=[Part.makeLine(p0,p1),Part.makeLine(p1,p2),Part.Arc(p2,V(41.14+r/math.sqrt(2),y,z+r/math.sqrt(2)),p3).toShape(),Part.makeLine(p3,p4),Part.Arc(p4,V(32.14-r/math.sqrt(2),y,z+r/math.sqrt(2)),p5).toShape(),Part.makeLine(p5,p0)]
 tool=Part.Face(Part.Wire(edges)).extrude(V(0,rear-inside+.5,0));dc=dc.cut(tool);top=fuse([top,dc])
 # D-sub J5: flank face at Y-6.4574, continuous roof, open-bottom insertion slot.
 jf=-6.4574;ji=jf-t;xl=181.0964;xr=212.4964
 top=top.cut(box(178.85,215.2964,ji,rear+.1,pcb+.3,H+.1))
 jp=fuse([box(178.85,215.2964,ji-.1,rear,H-t,H),box(178.85,xl,ji,jf,pcb+.3,H),box(xr,215.2964,ji,jf,pcb+.3,H),box(178.85,215.2964,ji,jf,27.4,H),box(178.85,179.05,ji,rear,pcb+.3,H),box(215.0964,217.8964,ji,rear,pcb+.3,H)])
 top=fuse([top,jp])
 # Long low gussets run alongX; only1.8mm extra inward depth. No added PCB supports.
 ribs=[rib(76,92.21,'right',-11.1,-9.3,28,H-t+.1),rib(113.51,118.15,'left',-11.1,-9.3,28,H-t+.1),rib(15.5,31.84,'right',inside-1.6,inside+.1,28,H-t+.1),rib(214.3,229.35,'right',rear-t-1.6,rear-t+.1,28,H-t+.1),rib(240.55,255.6,'left',rear-t-1.6,rear-t+.1,28,H-t+.1)]
 return fuse([top]+ribs)
