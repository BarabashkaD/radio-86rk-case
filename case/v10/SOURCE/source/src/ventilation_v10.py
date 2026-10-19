"""Canonical v10 opening dimensions and cutters, independent of old study defaults.
Angles are to the host wall/roof plane. Mouth width is measured on that plane.
Top/bottom side margins are dependent: height and bottom are editable, top derives.
"""
import math
from v10_parameters import DEFAULT
SIDE_FIELDS=((-184.,-112.5),(-106.5,-35.))
TOP_FIELDS=tuple((12+52.2*i,58.2+52.2*i,-70.,-38.5) for i in range(5))
def side_layout(p=DEFAULT):
 p.validate();shift=p.Wall/math.tan(math.radians(p.SideSlotAngle));slots=[];fields=[]
 for left in (True,False):
  for ya,yb in SIDE_FIELDS:
   n=math.floor((yb-ya-5-p.SideSlotExternalWidth-abs(shift))/p.SideSlotPitch)+1
   if n<1:raise ValueError('No side opening fits its preserved field')
   span=(n-1)*p.SideSlotPitch+p.SideSlotExternalWidth+abs(shift)
   first=ya+(yb-ya-span)/2+p.SideSlotExternalWidth/2
   fields.append({'left':left,'bounds':[ya,yb],'count':n,'first':first})
   slots.extend({'left':left,'outer_y':first+i*p.SideSlotPitch,'inner_y':first+i*p.SideSlotPitch+shift,'z0':p.SideSlotBottomMargin,'z1':p.SideSlotBottomMargin+p.SideSlotHeight} for i in range(n))
 return slots,fields

def top_layout(p=DEFAULT,margin=5.):
 shift=p.Wall/math.tan(math.radians(p.TopSlotAngle));slots=[];fields=[]
 for i,(xa,xb,ya,yb) in enumerate(TOP_FIELDS):
  central=i==2;u0,u1=(ya,yb) if central else (xa,xb);v0,v1=(xa,xb) if central else (ya,yb)
  n=math.floor((u1-u0-2*margin-p.TopSlotExternalWidth-shift)/p.TopSlotPitch)+1
  if n<1 or v1-v0<p.TopSlotLength+2*margin:raise ValueError('Top opening cannot preserve minimum field margins')
  extent=(n-1)*p.TopSlotPitch+p.TopSlotExternalWidth;fm=(u1-u0-extent-shift)/2;negative=central or i>=2;um=fm+(shift if negative else 0);vm=(v1-v0-p.TopSlotLength)/2
  fields.append({'id':i+1,'count':n,'whole_channel_margin':fm,'length_margin':vm})
  for j in range(n):
   u=u0+um+j*p.TopSlotPitch;v=v0+vm
   slots.append({'field':i+1,'rect':[v,u,v+p.TopSlotLength,u+p.TopSlotExternalWidth] if central else [u,v,u+p.TopSlotExternalWidth,v+p.TopSlotLength],'bottom_dir':[0,-1] if central else ([1,0] if i<2 else [-1,0])})
 return slots,fields

def side_cutters(p=DEFAULT,inward_extension=0.):
 import FreeCAD as A,Part
 V=A.Vector;out=[];k=1/math.tan(math.radians(p.SideSlotAngle));x0=p.CenterX-p.Width/2;x1=p.CenterX+p.Width/2
 for ss in side_layout(p)[0]:
  pts=[]
  for u,d in [(-p.SideSlotExternalWidth/2,-.05),(p.SideSlotExternalWidth/2,-.05),(p.SideSlotExternalWidth/2,p.Wall+inward_extension+.05),(-p.SideSlotExternalWidth/2,p.Wall+inward_extension+.05)]:
   pts.append(V(x0+d if ss['left'] else x1-d,ss['outer_y']+u+d*k,ss['z0']))
  q=Part.Face(Part.makePolygon(pts+[pts[0]])).extrude(V(0,0,p.SideSlotHeight))
  if q.Volume<0:q.reverse()
  out.append(q)
 return out

def top_cutters(p=DEFAULT,inward_extension=0.):
 import FreeCAD as A,Part
 V=A.Vector;out=[];k=1/math.tan(math.radians(p.TopSlotAngle));depth=p.Wall+inward_extension+.2
 for ss in top_layout(p)[0]:
  xa,ya,xb,yb=ss['rect'];dx,dy=ss['bottom_dir'];pts=[V(x-.1*k*dx,y-.1*k*dy,p.RoofZ+.1) for x,y in [(xa,ya),(xb,ya),(xb,yb),(xa,yb)]]
  q=Part.Face(Part.makePolygon(pts+[pts[0]])).extrude(V(depth*k*dx,depth*k*dy,-depth))
  if q.Volume<0:q.reverse()
  out.append(q)
 return out

def rib_anchors(p=DEFAULT,normal_pitch=40.):
 # Pick actual channel-adjacent solid webs with >=40mm normal spacing.
 slots=[s for s in side_layout(p)[0] if s['left']];chosen=[];minimum=normal_pitch/math.sin(math.radians(p.SideSlotAngle))
 for s in slots:
  y=s['inner_y']+p.SideSlotPitch/2
  if not chosen or y-chosen[-1]>=minimum-1e-8:chosen.append(y)
 return chosen

def add_properties(o):
 for name in ('SideSlotExternalWidth','SideSlotAngle','SideSlotPitch','SideSlotHeight','SideSlotBottomMargin','TopSlotExternalWidth','TopSlotLength','TopSlotAngle','TopSlotPitch'):
  if name not in o.PropertiesList:o.addProperty('App::PropertyAngle' if 'Angle' in name else 'App::PropertyLength',name,'Ventilation')
  setattr(o,name,getattr(DEFAULT,name))
 if 'SideSlotTopMargin' not in o.PropertiesList:o.addProperty('App::PropertyLength','SideSlotTopMargin','Ventilation')
 o.setExpression('SideSlotTopMargin','SideSeamZ - SideSlotBottomMargin - SideSlotHeight');o.setEditorMode('SideSlotTopMargin',1)
