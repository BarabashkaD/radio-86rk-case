"""Local stabilizer openings. Static/top-insertion checked; rotational envelope conditional on indicated wire axis."""
import FreeCAD as A,Part
WIRE={'space': {'axis': [178.61507938642, -192.051729806228, 16.167291070523], 'arm_projection_boxes': [[79.07716298484536, 81.27666567604666, -203.6699587958192, -180.43350081663678], [179.07524865439933, 181.2747513456007, -203.7480088805569, -180.35545073189908]], 'central_max_z': 17.990361214711402, 'assumption': 'Rigid wire rotates about long X-axis cylinder; full360deg conservative. Axis interpretation requires physical verification.'}, 'enter': {'axis': [241.28075, -169.86622538947302, 16.188020325584], 'arm_projection_boxes': [[238.58099865439934, 240.78050134560067, -181.5244338749687, -158.20801690397732], [262.46099865439936, 264.66050134560066, -181.5244338749687, -158.20801690397732]], 'central_max_z': 17.976874707584393, 'assumption': 'Rigid wire rotates about long X-axis cylinder; full360deg conservative. Axis interpretation requires physical verification.'}}
def box(x0,x1,y0,y1,z0,z1):return Part.makeBox(x1-x0,y1-y0,z1-z0,A.Vector(x0,y0,z0))
def modify(top,p):
 z0=p.PCBTop+p.GrilleTop-p.GrilleThickness;z1=p.PCBTop+p.GrilleTop
 # Restore original broad clearance regions to a continuous slab, then recut local clearances.
 patches=[box(76.4749,183.8751,-208.5251,-188.7249,z0,z1),box(235.97865,267.25885,-173.2251,-153.4249,z0,z1)]
 top=top.multiFuse(patches).removeSplitter()
 cuts=[]
 # Every ordinary Cherry envelope retains the established0.3mm side clearance.
 import json
 for b in json.loads(p.LayoutData)['switch_windows']:
  if b[3]-b[0]>25:continue
  cuts.append(box(b[0]-.3,b[3]+.3,b[1]-.3,b[4]+.3,z0-.01,z1+.01))
 # Spacebar fixed housings and sliding posts: upper mounting projections,0.3XY clearance.
 for xa,xb in [(76.475,83.875),(176.475,183.875)]:cuts.append(box(xa,xb,-205.825,-194.225,z0-.01,z1+.01))
 # Enter: merge the two 0.13/0.15mm slivers with the central opening, never print them as webs.
 cuts.append(box(235.97875,267.25875,-170.032086614173,-153.832086614173,z0-.01,z1+.01))
 # Narrow arms: conservative full-revolution XY envelopes, with0.3mm clearance.
 for group in WIRE.values():
  for xa,xb,ya,yb in group['arm_projection_boxes']:cuts.append(box(xa,xb,ya,yb,z0-.01,z1+.01))
 # Flush removal of free branches introduced by conservative arm corridors.
 for xa,ya,xb,yb in [[236.367913386, -172.882086614, 238.580998654, -170.032086614], [240.780501346, -172.882086614, 262.460998654, -170.032086614], [264.660501346, -172.882086614, 267.25875, -170.032086614], [252.567913386, -189.082086614, 255.417913386, -172.882086614], [76.475, -194.225, 79.077162985, -189.082086614], [181.274751346, -194.225, 183.875, -189.082086614]]:cuts.append(box(xa-.0000001,xb+.0000001,ya-.0000001,yb+.0000001,z0-.01,z1+.01))
 return top.cut(Part.makeCompound(cuts)).removeSplitter()
