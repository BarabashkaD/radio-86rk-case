"""Proposed v09 ribs. Caller alone integrates via FreeCAD MCP.
Use instead of the old explicit floor grid (set old RibHeight=0).
Does not alter document, source assembly, or existing moving parts.
All dimensions are prototype choices, not PCTG strength allowables.
"""
import math,json

def add_ribs(lower,upper,p,layout):
 import FreeCAD as A,Part
 V=A.Vector
 if isinstance(layout,str):layout=json.loads(layout)
 pcb=float(p.PCBTop);H=float(p.Height);floor=float(p.Floor)
 x0=139.7-float(p.Width)/2;x1=139.7+float(p.Width)/2
 yf=float(p.FrontY);yr=float(p.RearY);t=float(p.Wall)
 deck=pcb+float(p.GrilleTop);innerdeck=deck-float(p.GrilleThickness)
 report={'status':'Geometric rib candidate; final validation reports determine CAD/export status; physical strength unverified','lower':[],'upper':[], 'rejected_disconnected':[], 'rejected_thin_fragments':[],
 'old_floor_grid_must_be_disabled':True,'primary_rib_top_z':8.5,'secondary_rib_top_z':6.,
 'preserved_underboard_air_slab':[9.,10.3],'vent_keepout':[9.2,269.8,-72.8,-35.7],
 'material_strength_verified':False,'thermal_10W_verified':False}
 def box(xa,xb,ya,yb,za,zb):return Part.makeBox(xb-xa,yb-ya,zb-za,V(xa,ya,za))
 def cyl(r,z0,z1,x,y):return Part.makeCylinder(r,z1-z0,V(x,y,z0))
 def seg(a,b,w,z0,z1):
  dx=b[0]-a[0];dy=b[1]-a[1];l=math.hypot(dx,dy);nx=-dy/l*w/2;ny=dx/l*w/2
  pts=[V(a[0]+nx,a[1]+ny,z0),V(b[0]+nx,b[1]+ny,z0),V(b[0]-nx,b[1]-ny,z0),V(a[0]-nx,a[1]-ny,z0)]
  body=Part.Face(Part.makePolygon(pts+[pts[0]])).extrude(V(0,0,z1-z0))
  if z0<3.01 and z1>3.6:
   # Explicit 0.6 mm 45-degree root gussets, not an unverified automatic fillet.
   nnx=-dy/l;nny=dx/l
   cross=[(-w/2-.6,2.9),(-w/2-.6,3.),(-w/2,3.6),(w/2,3.6),(w/2+.6,3.),(w/2+.6,2.9)]
   pp=[V(a[0]+nnx*nn,a[1]+nny*nn,zz) for nn,zz in cross]
   root=Part.Face(Part.makePolygon(pp+[pp[0]])).extrude(V(dx,dy,0))
   body=body.fuse(root)
  elif z0>15:
   # 0.4 mm ceiling-root gussets on shallow upper ribs.
   nnx=-dy/l;nny=dx/l;zz=z1-.15
   cross=[(-w/2-.4,zz+.1),(-w/2-.4,zz),(-w/2,zz-.4),(w/2,zz-.4),(w/2+.4,zz), (w/2+.4,zz+.1)]
   pp=[V(a[0]+nnx*nn,a[1]+nny*nn,zv) for nn,zv in cross]
   body=body.fuse(Part.Face(Part.makePolygon(pp+[pp[0]])).extrude(V(dx,dy,0)))
  return body
 def fuse(items):return items[0].multiFuse(items[1:]).removeSplitter() if len(items)>1 else items[0]
 def overlapbb(a,b):return not(a.XMax<b.XMin or a.XMin>b.XMax or a.YMax<b.YMin or a.YMin>b.YMax or a.ZMax<b.ZMin or a.ZMin>b.ZMax)
 # Read-only assembly envelopes, inflated by 0.5 mm. Also preserve board support planes.
 electronic=[]
 for ref,b in layout['components'].items():
  electronic.append((ref,box(b[0]-.5,b[3]+.5,b[1]-.5,b[4]+.5,b[2]+pcb-.5,b[5]+pcb+.5)))
 foot_masks=[box(24,57,-61,-28,-1,10),box(222,255,-61,-28,-1,10)]
 lower_masks=foot_masks[:]
 # No new mass in the deep U25 underside pocket or rear connector/service band.
 for ref in ['U25','J1','J2','J4','J5','J6','J3']:
  if ref in layout['components']:
   b=layout['components'][ref];lower_masks.append(box(b[0]-1,b[3]+1,b[1]-1,b[4]+1,2.8,14.6))
 # Preserve side intake and cantilever release volumes. Low post-to-wall ties below Z4.5 remain possible.
 for left in [True,False]:
  xa,xb=(x0-.1,x0+12.) if left else (x1-12.,x1+.1)
  for ya,yb in [(-187,-109),(-109,-32)]:lower_masks.append(box(xa,xb,ya,yb,4.6,15.5))
 upper_masks=[box(9.2,269.8,-72.8,-35.7,14.6,H+1),box(112,185,-35.5,yr+5,14.6,H+5)]
 # Conservative exclusion applies ONLY to newly added ribs, never to the existing grille.
 # Invalid stabilizer source geometry keeps its prior verified local material unchanged.
 upper_masks.extend([box(235.97874,267.25876,-173.22501,-152.95481,11.44999,38.00001),box(76.47499,183.87501,-208.99519,-188.72499,11.44999,38.00001)])
 report['new_rib_stabilizer_exclusion']='Full source bbox +0.3 only for added reinforcement; existing filled grille unchanged'
 # Side snap root/beam/tool swept envelopes; never stiffen a spring.
 for left in [True,False]:
  xa,xb=(x0-.2,x0+7) if left else (x1-7,x1+.2)
  for yc in [-150,-70]:upper_masks.append(box(xa,xb,yc-14,yc+14,9.5,16.5))
 # Protect switch/stabilizer motion and LED access throughout the reinforcement band.
 for b in layout['switch_windows']:
  upper_masks.append(box(b[0]-.6,b[3]+.6,b[1]-.6,b[4]+.6,pcb-.1,deck+3))
 for x,y in [(206.375,-104.775),(225.425,-104.775)]:upper_masks.append(cyl(3,pcb-1,deck+3,x,y))
 # Explicit functional-bore keepouts. New ties must not fill screw heads or inserts.
 shell_axes=[(x0+5.65,-24),(x1-5.65,-24),(x0+5.65,-198),(x1-5.65,-198)]
 for x,y in layout['mounts']:
  upper_masks.append(cyl(float(p.UpperStopID)/2,pcb-.1,H+.1,x,y))
  lower_masks.append(cyl(float(p.InsertPilot)/2,pcb-1.6-float(p.InsertDepth),pcb+.1,x,y))
 for x,y in shell_axes:
  lower_masks.extend([cyl(1.7,-1,float(p.SeamZ)+.1,x,y),cyl(3.3,-1,3.2,x,y)])
  upper_masks.append(cyl(float(p.InsertPilot)/2,float(p.SeamZ)-.1,float(p.SeamZ)+float(p.InsertDepth),x,y))
 report['functional_bores_preserved']={'PCB_upper_head_cavities':7,'PCB_lower_insert_pilots':7,'shell_through_and_head_pockets':4,'shell_upper_insert_pilots':4}
 def trim(shape,masks):
  cutters=[m for m in masks if overlapbb(shape.BoundBox,m.BoundBox)]
  cutters += [s for ref,s in electronic if overlapbb(shape.BoundBox,s.BoundBox)]
  return shape.cut(Part.makeCompound(cutters)) if cutters else shape
 la=[];ua=[]
 def add(role,name,shape):
  shape=trim(shape,lower_masks if role=='lower' else upper_masks)
  support=lower if role=='lower' else upper
  for i,solid in enumerate(shape.Solids):
   bb=solid.BoundBox
   if role=='upper' and (min(bb.XLength,bb.YLength)<.8 or solid.Volume<1.):
    report['rejected_thin_fragments'].append({'name':name,'volume':solid.Volume,'bbox':[bb.XMin,bb.YMin,bb.ZMin,bb.XMax,bb.YMax,bb.ZMax]})
    continue
   # Positive overlap, not a face-only contact. Keeps snippets attached to actual shell.
   if solid.common(support).Volume>1e-5:
    (la if role=='lower' else ua).append(solid)
    report[role].append({'name':name,'volume':solid.Volume,'bbox':[solid.BoundBox.XMin,solid.BoundBox.YMin,solid.BoundBox.ZMin,solid.BoundBox.XMax,solid.BoundBox.YMax,solid.BoundBox.ZMax]})
   else:report['rejected_disconnected'].append(name+':'+str(i))
 # Dense hierarchical floor lattice: primary spine cells about 45..95 by35 mm,
 # secondary infill halves these spans to about20..25 by17.5 mm.
 for x in [45,140,235]:add('lower','primary_X'+str(x),seg((x,-205),(x,-35),2.,2.9,8.5))
 for y in [-180,-145,-110,-75]:add('lower','primary_Y'+str(y),seg((14,y),(265,y),2.,2.9,8.5))
 for x in [20,70,95,120,165,190,215,260]:add('lower','secondary_X'+str(x),seg((x,-205),(x,-35),1.6,2.9,6.))
 for y in [-200,-162.5,-127.5,-92.5,-57.5]:add('lower','secondary_Y'+str(y),seg((14,y),(265,y),1.6,2.9,6.))
 # Sparse diagonals in broad free floor regions, not a massive triangulated infill.
 for i,(a,b) in enumerate([((45,-180),(95,-145)),((95,-145),(140,-180)),((140,-180),(190,-145)),((190,-145),(235,-180)),((45,-145),(95,-110)),((190,-110),(235,-145)),((70,-110),(120,-75)),((165,-75),(215,-110))]):
  add('lower','diagonal'+str(i),seg(a,b,1.6,2.9,6.))
 # Short load paths from PCB posts; no full-height bridge across side air intakes.
 ties=[((11.43,-11.43),(11.43,yr-t+.15),7.),((267.97,-11.43),(267.97,yr-t+.15),7.),
       ((11.43,-91.44),(x0+t-.15,-91.44),4.5),((267.97,-91.44),(x1-t+.15,-91.44),4.5),
       ((139.7,-110.49),(140,-110),8.5),((62.23,-204.47),(62.23,yf+t-.15),7.),((207.01,-204.47),(207.01,yf+t-.15),7.)]
 for i,(a,b,z) in enumerate(ties):add('lower','post_wall_tie'+str(i),seg(a,b,2.,2.9,z))
 # Nearby rear PCB and shell screw bosses: 16 mm diagonal instead of tall solid block.
 for a,b in [((11.43,-11.43),(x0+5.65,-24)),((267.97,-11.43),(x1-5.65,-24))]:add('lower','near_boss_link',seg(a,b,2.,2.9,6.))
 # Short 45-degree conical post-root gussets. Same R4.8/Z3..3.8 envelope;
 # replaces curved toroidal roots whose trimmed tessellation self-intersected.
 for x,y in layout['mounts']:
  rr=float(p.BossDiameter)/2;rad=.8;z=floor
  root=Part.makeCone(rr+rad,rr,rad,V(x,y,z))
  root=root.cut(cyl(float(p.InsertPilot)/2,2,14,x,y));add('lower','post_root_45deg',root)
 # R0.8 concave lower wall/floor corner roots, below all intake openings.
 rr=.8
 for left in [True,False]:
  edge=x0+t if left else x1-t;sg=1 if left else -1
  xa,xb=sorted([edge-sg*.1,edge+sg*rr]);ya=yf+6;yb=yr-6
  root=box(xa,xb,ya,yb,2.9,3.+rr)
  cutter=Part.makeCylinder(rr,yb-ya+.2,V(edge+sg*rr,ya-.1,3.+rr),V(0,1,0))
  add('lower','wall_floor_R0.8',root.cut(cutter))
 for rear in [False,True]:
  edge=yr-t if rear else yf+t;sg=-1 if rear else 1
  ya,yb=sorted([edge-sg*.1,edge+sg*rr]);xa=x0+6;xb=x1-6
  root=box(xa,xb,ya,yb,2.9,3.+rr)
  cutter=Part.makeCylinder(rr,xb-xa+.2,V(xa-.1,edge+sg*rr,3.+rr),V(1,0,0))
  add('lower','wall_floor_R0.8',root.cut(cutter))
 # Upper keyboard underside lattice: shallow, clipped to all actual switch envelopes.
 # The unmodified roof provides continuous attachment; added depth only1.2 mm.
 # Follow real staggered key gaps instead of forcing a rectangular grid through keys.
 for yc in [-200.032,-180.982,-161.932,-142.882,-123.832,-104.782]:
  intervals=sorted((b[0]-.6,b[3]+.6) for b in layout['switch_windows'] if b[1]-.6<=yc<=b[4]+.6)
  merged=[]
  for aa,bb in intervals:
   if merged and aa<=merged[-1][1]:merged[-1][1]=max(merged[-1][1],bb)
   else:merged.append([aa,bb])
  for left,right in zip(merged,merged[1:]):
   if right[0]-left[1]>=1.8:
    x=(left[1]+right[0])/2
    add('upper','adaptive_key_gap',seg((x,max(-210,yc-10.5)),(x,min(-96,yc+10.5)),1.6,innerdeck-1.2,innerdeck+.15))
 for y in [-200,-190.5,-171.45,-152.4,-133.35,-114.3,-97]:
  add('upper','keyboard_Y'+str(y),seg((10,y),(270,y),1.6,innerdeck-1.2,innerdeck+.15))
 for a,b in [((20,-207),(45,-190.5)),((235,-190.5),(260,-207)),((100,-200),(120,-190.5)),((160,-190.5),(180,-200))]:
  add('upper','keyboard_diagonal',seg(a,b,1.6,innerdeck-1.2,innerdeck+.15))
 # Upper short ties attach contacts to roof/wall; no ribs under vent fields.
 for x,y in [(11.43,-11.43),(267.97,-11.43)]:add('upper','rear_contact_tie',seg((x,y),(x,yr-t+.15),2.,H-t-1.2,H-t+.15))
 for x,y in [(62.23,-204.47),(207.01,-204.47)]:add('upper','front_contact_tie',seg((x,y),(x,yf+t-.15),2.,innerdeck-1.2,innerdeck+.15))
 for x,y in [(11.43,-91.44),(267.97,-91.44)]:
  inner=deck+(y-float(p.SlopeStartY))*math.tan(math.radians(float(p.SlopeAngle)))-t/math.cos(math.radians(float(p.SlopeAngle)))
  wall=x0+t-.15 if x<139.7 else x1-t+.15
  add('upper','slope_contact_tie',seg((x,y),(wall,y),2.,inner-1.2,inner+.15))
 # Bores remain exact after the fillet/tie unions.
 lower=fuse([lower]+la) if la else lower
 for x,y in layout['mounts']:lower=lower.cut(cyl(float(p.InsertPilot)/2,pcb-1.6-float(p.InsertDepth),pcb,x,y))
 upper=fuse([upper]+ua) if ua else upper
 report.update(lower_valid=lower.isValid(),upper_valid=upper.isValid(),lower_solids=len(lower.Solids),upper_solids=len(upper.Solids),new_lower_volume=sum(s.Volume for s in la),new_upper_volume=sum(s.Volume for s in ua))
 return lower,upper,report
