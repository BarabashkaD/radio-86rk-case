"""Cold upper feeders: explicit BREP inputs, no document/GUI or source execution.
This is a faithful accepted-default port, not a full parametric implementation.
"""
import hashlib
import json
import math
from pathlib import Path
from geometry_checks import check_boolean_result

def yzprofile(x0,x1,pts):
 e=[];first=last=V(x0,*pts[0])
 for p in pts[1:]:
  if p[0]=='arc':end=V(x0,*p[2]);e.append(Part.Arc(last,V(x0,*p[1]),end).toShape())
  else:end=V(x0,*p);e.append(Part.makeLine(last,end))
  last=end
 e.append(Part.makeLine(last,first));s=Part.Face(Part.Wire(e)).extrude(V(x1-x0,0,0))
 if s.Volume<0:s.reverse()
 return s

def xzprofile(pts):
 vv=[V(x,-219,z) for x,z in pts];s=Part.Face(Part.makePolygon(vv+[vv[0]])).extrude(V(0,215.95,0))
 if s.Volume<0:s.reverse()
 return s

def mirror(s):
 q=s.copy();m=A.Matrix();m.A11=-1;m.A14=279.4;q.transformShape(m);return q

def rounded_prism(x0,x1,y0,y1,r):
 s=Part.makeBox(x1-x0,y1-y0,60,V(x0,y0,-10));ed=[e for e in s.Edges if e.BoundBox.ZLength>59.9];return s.makeFillet(r,ed)

def envelopes():
 H=37.5;deck=20.6;t=2.8;ys=-95;a=math.pi/4;R=10;Ri=7.2;ye=ys+H-deck;cy=ye+R*math.tan(a/2);cz=H-R;j=ys+(t/math.cos(a)-2)
 ob=(cy-R*math.sin(a),cz+R*math.cos(a));om=(cy-R*math.sin(a/2),cz+R*math.cos(a/2));ib=(cy-Ri*math.sin(a),cz+Ri*math.cos(a));im=(cy-Ri*math.sin(a/2),cz+Ri*math.cos(a/2))
 out=yzprofile(-10.3,289.7,[(-219,-10),(-3.05,-10),(-3.05,H),(cy,H),('arc',om,ob),(ys,deck),(-219,deck)])
 inside=yzprofile(-10.3,289.7,[(-219,-10),(-3.05,-10),(-3.05,H-t),(cy,H-t),('arc',im,ib),(j,18.6),(-219,18.6)])
 m=(20.6-30)/(5.8-3.3);b=30-m*3.3;bi=b-2.8*math.sqrt(1+m*m);it=(27.2-bi)/m;ibot=(18.6-bi)/m
 shoulder=xzprofile([(-10.3,-10),(6.5,-10),(6.5,20.6),(5.8,20.6),(3.3,30),(-10.3,30)])
 for xx,zz,rad in [(3.3,30,1.),(5.8,20.6,.6)]:
  edges=[e for e in shoulder.Edges if e.BoundBox.YLength>215 and abs(e.BoundBox.XMin-xx)<1e-5 and abs(e.BoundBox.XMax-xx)<1e-5 and abs(e.BoundBox.ZMin-zz)<1e-5 and abs(e.BoundBox.ZMax-zz)<1e-5]
  assert edges;shoulder=shoulder.makeFillet(rad,edges)
 cavity=xzprofile([(-10.3,-10),(6.5,-10),(6.5,18.6),(ibot,18.6),(it,27.2),(-10.3,27.2)])
 outerplan=rounded_prism(-10.3,289.7,-219,-3.05,5);innerplan=rounded_prism(-7.5,286.9,-216.2,-5.85,2.2)
 out=out.multiFuse([shoulder,mirror(shoulder)]).common(outerplan)
 inside=inside.multiFuse([cavity,mirror(cavity)]).common(innerplan)
 shell=out.cut(inside).common(Part.makeBox(302,218,35,V(-11.3,-220,16.2)))
 return out,inside,shell,outerplan,innerplan

def profiles(z=16.2,roof=37.5):
 h=2.;r=.3;R=.6;c=.3;t=2.8;rt=2 if roof<25 else 2.8
 lo=[(0,0),(18,0),(18,3),(t,3),(t,z+h-.3),(t-.3,z+h),(1.9,z+h),('arc',(1.9-r/math.sqrt(2),z+h-r+r/math.sqrt(2)),(1.6,z+h-r)),(1.6,z+r),('arc',(1.3+r/math.sqrt(2),z+r-r/math.sqrt(2)),(1.3,z)),(.3,z),(0,z-.3)]
 up=[(0,z+.3),(.3,z),(1.,z),('arc',(1+r/math.sqrt(2),z+r-r/math.sqrt(2)),(1.3,z+r)),(1.3,z+h+c-R),('arc',(1.9-R/math.sqrt(2),z+h+c-R+R/math.sqrt(2)),(1.9,z+h+c)),(2.8,z+h+c),(2.8,roof-rt),(18,roof-rt),(18,roof),(0,roof)]
 return lo,up

def faces(z,y):
 lo,up=profiles(z,60)
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

def ramp_build(length=20):
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

OX=-10.3; CY=-8.05; CX=-5.3

ACCEPTED = {'Width': 300.0, 'Depth': 215.95, 'CenterX': 139.7, 'Floor': 3.0, 'Wall': 2.8, 'OuterCornerRadius': 5.0, 'PCBThickness': 1.6, 'PCBBottomZ': 13.0, 'ShoulderZ': 30.0, 'RoofZ': 37.5, 'DeckZ': 20.6, 'SideSeamZ': 16.2, 'RearSeamZ': 21.6, 'RearRampLength': 20.0, 'TongueWidth': 1.2, 'TongueHeight': 2.0, 'GrooveWidth': 1.5, 'GrooveHeight': 2.3, 'JointGap': 0.3, 'JointLargeRadius': 0.6, 'JointSmallRadius': 0.3, 'OuterSeamChamfer': 0.3, 'SideSlotExternalWidth': 3.0, 'SideSlotAngle': 60.0, 'SideSlotPitch': 5.5, 'SideSlotHeight': 6.0, 'SideSlotBottomMargin': 5.0, 'TopSlotExternalWidth': 3.0, 'TopSlotLength': 18.0, 'TopSlotAngle': 60.0, 'TopSlotPitch': 5.5, 'RibWidth': 1.8, 'RibHeight': 6.0, 'FloorInnerRadius': 2.0, 'RibRootRadius': 0.6, 'RibNodeRadius': 1.0, 'PostRootRadius': 2.0, 'BossDiameter': 10.0, 'CaseSeatZ': 16.2, 'ScrewLength': 20.0, 'HeadSeatZ': 3.2, 'HeadPocketDiameter': 6.6, 'CaseThroughDiameter': 3.4, 'InsertLength': 5.7, 'InsertOD': 4.6, 'PilotDiameter': 4.0, 'CapEdgeZ': 23.2, 'CapRise': 0.2}
FROZEN_SHA = {'foundation_rear_snapshot': '2ac6ec73b8c995c1085987928991fe4fcee4534b93a1ccc9027048a9de335cac', 'foundation_j6_snapshot': 'a3560329e289dfc053d2b2a687b3b15806a2fc306177595cf179cc1b314a9b36', 'foundation_v09_upper_snapshot': '49c0fd04090a502ccb9356500c54eda19a0c7fe89a70dc8857147af3c7d0167a'}
CANONICAL_SOURCE_SHA = {'parameters_source': '04c2a078add208acef6c7a5b4808f23f22b5d42b4f96734f8bf58ea8889ffbef', 'ventilation_source': '6bc0c727d150143a51d6831e6cd644f570056e7b69d2e89bc7d8f8bafa6cd81b'}

ENVELOPE_OUTPUTS = {'outer_volume','inner_volume','raw_shell','outer_plan','inner_plan','envelopes_provenance'}
FOUNDATION_OUTPUTS = {'upper_foundation','upper_g_overlap_mask','upper_foundation_provenance'}
ENVELOPE_INPUTS = {'parameters_source'}
FOUNDATION_INPUTS = {'parameters_source','ventilation_source','ventilation_layout','outer_volume','inner_volume','raw_shell','inner_plan','foundation_rear_snapshot','foundation_j6_snapshot','foundation_v09_upper_snapshot','keyboard_profiles','vent_frames'}

# Only values actually fixed by the corresponding recipe are locked.
ENVELOPE_FIXED = frozenset(('Width','Depth','CenterX','Wall','OuterCornerRadius','ShoulderZ','RoofZ','DeckZ','SideSeamZ'))
FOUNDATION_FIXED = ENVELOPE_FIXED | frozenset(('RearSeamZ','RearRampLength','PCBThickness','PCBBottomZ','TongueWidth','TongueHeight','GrooveWidth','GrooveHeight','JointGap','JointLargeRadius','JointSmallRadius','OuterSeamChamfer'))
VENT_LIVE = frozenset(('SideSlotExternalWidth','SideSlotAngle','SideSlotPitch','SideSlotHeight','SideSlotBottomMargin','TopSlotExternalWidth','TopSlotLength','TopSlotAngle','TopSlotPitch','RibWidth','RibHeight','RibRootRadius','RibNodeRadius'))

def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def verified(context, role):
    path=Path(context['inputs'][role]); expected=context['input_hashes'][role]
    if path.is_symlink() or not path.is_file() or digest(path)!=expected:
        raise ValueError('Input SHA mismatch: '+role)
    pinned=FROZEN_SHA.get(role,CANONICAL_SOURCE_SHA.get(role))
    if pinned and expected!=pinned:raise ValueError('Unsupported frozen/canonical revision: '+role)
    return path

def validate_context(c, stage, inputs, outputs):
    if c.get('cold_build') is not True or c.get('stage_id')!=stage or c.get('owns_enter') is not False:
        raise ValueError('Cold stage/ownership mismatch')
    if set(c['inputs'])!=inputs or set(c['outputs'])!=outputs:
        raise ValueError('Exact input/output roles required')
    if set(c['input_hashes'])!=inputs:raise ValueError('Exact input hashes required')
    for role in inputs:verified(c,role)
    paths=[Path(p).resolve() for p in c['outputs'].values()]
    if len(set(paths))!=len(paths) or any(p.exists() for p in paths):raise ValueError('Outputs must be distinct and new')
    fixed=FOUNDATION_FIXED if stage=='upper_foundation' else ENVELOPE_FIXED
    for key in fixed:
        expected=ACCEPTED[key]
        value=c['parameters'].get(key)
        if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or abs(value-expected)>1e-8:
            raise ValueError('Accepted-default-only geometry; unsupported parameter: '+key)

def _cad():
    global A, Part, V
    import FreeCAD as A
    import Part
    V=A.Vector

def body(s,role,solids=None):
    if s.isNull() or not s.isValid() or not math.isfinite(s.Volume) or s.Volume<=0 or not s.Solids:
        raise ValueError('Invalid geometry: '+role)
    if solids is not None and len(s.Solids)!=solids:raise ValueError('Unexpected solids: '+role)
    s.check(True)
    return {'volume_mm3':s.Volume,'solids':len(s.Solids),'valid':True,'bop_check_invoked':True}

def read_shape(c,role):
    s=Part.Shape();s.read(str(verified(c,role)));body(s,role);return s

def save_shape(c,role,s):
    before=body(s,role,1);path=Path(c['outputs'][role]);s.exportBrep(str(path))
    reopened=Part.Shape();reopened.read(str(path));after=body(reopened,role+' reopened',1)
    delta=[]
    for q in (s.cut(reopened),reopened.cut(s)):
        check_boolean_result(q);delta.append(abs(q.Volume))
    if max(delta)>1e-3:raise ValueError('Saved shape changed: '+role)
    return {'sha256':digest(path),'before':before,'reopened':after,'symmetric_difference_mm3':delta}

def report(c,role,outputs,**extra):
    for key in c['inputs']:verified(c,key)
    result={'producer':'upper_feeders.'+c['stage_id'],'build_mode':'frozen_node_assembly',
            'inputs':{k:{'path':str(v),'sha256':c['input_hashes'][k]} for k,v in c['inputs'].items()},
            'outputs':outputs,'fixed_geometry_parameters':sorted(FOUNDATION_FIXED if c['stage_id']=='upper_foundation' else ENVELOPE_FIXED),'baseline_equivalence':'NOT_RUN',
            'full_case_qa':'NOT_RUN','release_ready':False,**extra}
    Path(c['outputs'][role]).write_text(json.dumps(result,indent=2,allow_nan=False)+'\n');return result

def build_envelopes(c):
    validate_context(c,'envelopes',ENVELOPE_INPUTS,ENVELOPE_OUTPUTS);_cad()
    shapes=dict(zip(('outer_volume','inner_volume','raw_shell','outer_plan','inner_plan'),envelopes()))
    outputs={name:save_shape(c,name,s) for name,s in shapes.items()}
    return report(c,'envelopes_provenance',outputs,geometry_recipe='accepted upper_envelope_geometry.py port')

def resolved_parameters(c):
    """Resolve side driver modes without importing/executing another source file."""
    p=dict(c['parameters']);mode=p.get('SideMarginMode')
    if mode is None:return p
    drivers={'height_bottom':('SideSlotHeight','SideSlotBottomMargin'),
             'top_bottom':('SideSlotTopMargin','SideSlotBottomMargin'),
             'height_top':('SideSlotHeight','SideSlotTopMargin')}
    if mode not in drivers:raise ValueError('Unknown ventilation driver mode')
    for key in ('SideSeamZ','Floor','SideSlotExternalWidth','SideSlotPitch','SideSlotAngle')+drivers[mode]:
        value=p.get(key)
        if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value):raise ValueError('Invalid side driver: '+key)
    if mode=='height_bottom':p['SideSlotTopMargin']=p['SideSeamZ']-p['SideSlotHeight']-p['SideSlotBottomMargin']
    elif mode=='top_bottom':p['SideSlotHeight']=p['SideSeamZ']-p['SideSlotTopMargin']-p['SideSlotBottomMargin']
    else:p['SideSlotBottomMargin']=p['SideSeamZ']-p['SideSlotHeight']-p['SideSlotTopMargin']
    if not (0<p['SideSlotExternalWidth']<p['SideSlotPitch'] and 0<p['SideSlotAngle']<=90 and p['SideSlotHeight']>0 and p['SideSlotTopMargin']>0 and p['SideSlotBottomMargin']>=p['Floor']):raise ValueError('Side margin/floor constraint violated')
    return p

def ventilation_contract(c):
    data=json.loads(verified(c,'ventilation_layout').read_text())
    if data.get('producer')!='ventilation_adapter.build_layout':raise ValueError('Canonical ventilation layout required')
    for role,sha in CANONICAL_SOURCE_SHA.items():
        if data.get('sources',{}).get(role)!=sha:raise ValueError('Ventilation layout source mismatch')
    resolved=resolved_parameters(c)
    for key in ACCEPTED:
        value=resolved.get(key)
        got=data.get('parameters',{}).get(key)
        if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value):raise ValueError('Missing/nonfinite canonical parameter: '+key)
        if isinstance(got,bool) or not isinstance(got,(int,float)) or not math.isfinite(got) or abs(got-value)>1e-8:
            raise ValueError('Ventilation layout parameter mismatch: '+key)
    derived_top=resolved['SideSeamZ']-resolved['SideSlotHeight']-resolved['SideSlotBottomMargin']
    reported_top=data.get('parameters',{}).get('SideSlotTopMargin',derived_top)
    if isinstance(reported_top,bool) or not isinstance(reported_top,(int,float)) or not math.isfinite(reported_top) or abs(reported_top-derived_top)>1e-8:raise ValueError('Canonical derived side top margin mismatch')
    slots=data.get('top',{}).get('slots',[])
    if not slots or data.get('top',{}).get('count')!=len(slots):raise ValueError('Invalid canonical top channel count')
    return data

def build_foundation(c):
    validate_context(c,'upper_foundation',FOUNDATION_INPUTS,FOUNDATION_OUTPUTS)
    ventilation_contract(c);_cad()
    out=read_shape(c,'outer_volume');raw=read_shape(c,'raw_shell');ip=read_shape(c,'inner_plan')
    read_shape(c,'inner_volume')  # explicit upstream envelope input, not silently ignored
    def box(x,y,z,dx,dy,dz):return Part.makeBox(dx,dy,dz,V(x,y,z))
    roof=raw.common(ip)
    left=faces(16.2,-214)[1].extrude(V(0,154,0)).common(out)
    ramp=ramp_build(20)[1].cut(box(-5.1,-5.85,0,100,3,50)).common(out)
    f=faces(16.2,-214)[1];center=V(-5.3,-214,0)
    corner=f.revolve(center,V(0,0,1),90).common(box(-10.3,-219,0,5,5,50)).common(out)
    f.rotate(center,V(0,0,1),90)
    front=f.extrude(V(290,0,0)).common(box(-5.3,-219,0,290,2.8,50)).common(out)
    jc=box(115,-35,0,67,40,50)
    rear=read_shape(c,'foundation_rear_snapshot').cut(jc)
    jupper=read_shape(c,'foundation_j6_snapshot').common(jc)
    roof=roof.cut(box(-20,-5.85,0,320,10,50)).cut(jc)
    # Preserve the analytic shoulder-to-deck R0.6 tails while replacing the keyboard.
    shoulder_skins=[roof.common(box(x,-216,20.6,.5,121,1.4)) for x in (6.,272.9)]
    for i,skin in enumerate(shoulder_skins):body(skin,'preserved shoulder skin '+str(i),1)
    roof=roof.cut(box(6,-216,0,267.4,121,50));keyboard=read_shape(c,'keyboard_profiles')
    roof=roof.cut(box(9.2,-72.8,0,260.6,37.1,50));vent=read_shape(c,'vent_frames')
    for k in range(7):
        x,y=257.8088,-13.97
        if k:x+=2.75*math.cos((k-1)*math.pi/3);y+=2.75*math.sin((k-1)*math.pi/3)
        roof=roof.cut(Part.makeCylinder(.75,5,V(x,y,34)))
    pieces=[('roof',roof),('left',left),('right',mirror(left)),('left ramp',ramp),('right ramp',mirror(ramp)),('front left',corner),('front right',mirror(corner)),('front',front),('rear',rear),('J6 upper',jupper),('keyboard',keyboard),('vent frames',vent)]
    # Accepted correct_upper_g_overlap recipe, using the SAME nine fresh G pieces.
    ipover=rounded_prism(-7.55,286.95,-216.25,-5.80,2.25)
    gmask=raw.common(ipover).cut(ip)
    g_piece_names=('left','right','left ramp','right ramp','front left','front right','front','rear','J6 upper')
    g_pieces={name:q for name,q in pieces if name in g_piece_names}
    if set(g_pieces)!=set(g_piece_names):raise ValueError('Missing exact foundation G mask piece')
    for name in g_piece_names:gmask=gmask.cut(g_pieces[name])
    body(gmask,'generated G overlap mask')
    mask_path=Path(c['outputs']['upper_g_overlap_mask']);gmask.exportBrep(str(mask_path))
    reopened_mask=Part.Shape();reopened_mask.read(str(mask_path));mask_metrics=body(reopened_mask,'reopened G overlap mask')
    mask_deltas=[]
    for delta in (gmask.cut(reopened_mask),reopened_mask.cut(gmask)):
        check_boolean_result(delta);mask_deltas.append(abs(delta.Volume))
    if max(mask_deltas)>1e-6:raise ValueError('Saved G overlap mask changed')
    mask_output={'sha256':digest(mask_path),'topology':mask_metrics,'symmetric_difference_mm3':mask_deltas,
                 'recipe':'raw.common(ipover).cut(ip), minus nine exact fresh foundation G pieces','piece_names':list(g_piece_names)}
    pieces += [('left shoulder skin',shoulder_skins[0]),('right shoulder skin',shoulder_skins[1])]
    s=roof;steps=[{'piece':'roof',**body(s,'roof')}]
    for name,q in pieces[1:]:
        body(q,name);v=s.Volume;s=s.fuse(q,.00001)
        if s.Volume<v-.001:raise ValueError('Union lost volume: '+name)
        steps.append({'piece':name,**body(s,'union '+name)})
    src=read_shape(c,'foundation_v09_upper_snapshot')
    for x,y in [(11.43,-11.43),(267.97,-11.43),(11.43,-91.44),(267.97,-91.44),(139.7,-110.49),(62.23,-204.47),(207.01,-204.47)]:
        q=src.common(Part.makeCylinder(4.01,23,V(x,y,14.6)));body(q,'PCB stop')
        v=s.Volume;s=s.fuse(q,.00001)
        if s.Volume<v-.001:raise ValueError('PCB stop union lost volume')
        steps.append({'pcb_stop':[x,y],**body(s,'PCB stop union')})
    output=save_shape(c,'upper_foundation',s)
    return report(c,'upper_foundation_provenance',{'upper_foundation':output,'upper_g_overlap_mask':mask_output},steps=steps,
                  frozen_nodes=sorted(FROZEN_SHA),ventilation_geometry_equivalence='NOT_RUN',
                  remaining=['Four upper bosses/local ribs','Perimeter fillets and gussets','Shoulder/roof blending','Current upper stabilization and full-case acceptance'])

VENT_INPUTS = {'parameters_source','ventilation_source','ventilation_layout'}
VENT_OUTPUTS = {'vent_frames','vent_frames_provenance'}
TOP_FIELDS = tuple((12+52.2*i,58.2+52.2*i,-70.,-38.5) for i in range(5))

def vent_settings(c):
    p=resolved_parameters(c);values={}
    for name in ('RibWidth','RibHeight','RibNodeRadius','RibRootRadius','TopSlotExternalWidth','TopSlotLength','TopSlotAngle','TopSlotPitch'):
        v=p.get(name)
        if isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) or v<=0:raise ValueError('Invalid ventilation parameter: '+name)
        values[name]=v
    if p['TopSlotAngle']>90 or p['TopSlotExternalWidth']>=p['TopSlotPitch']:raise ValueError('Invalid top channel dimensions')
    if p['RibWidth']>=3 or p['RibNodeRadius']>=3 or p['RibRootRadius']>=min(p['RibHeight'],2.8):
        raise ValueError('Rib size exceeds preserved local frame boundary')
    return values

def _positive(s):
    if s.Volume<0:s.reverse()
    return s

def _strip(a,b,w,z,h):
    dx=b[0]-a[0];dy=b[1]-a[1];length=math.hypot(dx,dy)
    n=V(-dy/length*w/2,dx/length*w/2,0);p=V(a[0],a[1],z);q=V(b[0],b[1],z)
    pts=[p+n,q+n,q-n,p-n]
    return _positive(Part.Face(Part.makePolygon(pts+[pts[0]])).extrude(V(0,0,h)))

def top_air(slots, p, extension):
    # Identical canonical top_cutters transform, using canonical layout output.
    # Local roots need extension=RibHeight+.1: default depth=2.8+6+.1+.2=9.1.
    k=1/math.tan(math.radians(p['TopSlotAngle']));depth=p['Wall']+extension+.2;cuts=[]
    for ss in slots:
        rect=ss.get('rect');direction=ss.get('bottom_dir')
        if not isinstance(rect,list) or len(rect)!=4 or any(isinstance(x,bool) or not isinstance(x,(int,float)) or not math.isfinite(x) for x in rect):raise ValueError('Invalid canonical top slot rectangle')
        if direction not in ([0,-1],[1,0],[-1,0]):raise ValueError('Invalid canonical top slot direction')
        xa,ya,xb,yb=rect;dx,dy=direction
        if xb<=xa or yb<=ya:raise ValueError('Nonpositive canonical top slot rectangle')
        pts=[V(x-.1*k*dx,y-.1*k*dy,p['RoofZ']+.1) for x,y in [(xa,ya),(xb,ya),(xb,yb),(xa,yb)]]
        cuts.append(_positive(Part.Face(Part.makePolygon(pts+[pts[0]])).extrude(V(depth*k*dx,depth*k*dy,-depth))))
    return Part.makeCompound(cuts)

def build_ventilation_frames(c):
    # Envelope dimensions fixed; live vent and rib parameters are not locked.
    validate_context(c,'ventilation_frames',VENT_INPUTS,VENT_OUTPUTS)
    settings=vent_settings(c);layout=ventilation_contract(c);_cad();p=resolved_parameters(c)
    width=p['RibWidth'];height=p['RibHeight'];node_radius=p['RibNodeRadius'];rf=p['RibRootRadius']
    ceiling=p['RoofZ']-p['Wall'];bottom=ceiling-height
    slots=layout['top']['slots'];panel=Part.makeBox(260.6,37.1,p['Wall'],V(9.2,-72.8,ceiling))
    panel=panel.cut(top_air(slots,p,0.)).removeSplitter()
    xa=TOP_FIELDS[0][0]-width/2;xb=TOP_FIELDS[-1][1]+width/2;ya=-70-width/2;yb=-38.5+width/2
    corners=[(xa,ya),(xb,ya),(xb,yb),(xa,yb)];segments=[(corners[i],corners[(i+1)%4]) for i in range(4)]
    for i in range(4):
        x=(TOP_FIELDS[i][1]+TOP_FIELDS[i+1][0])/2;segments.append(((x,ya),(x,yb)))
    strips=[_strip(a,b,width,bottom,height+.1) for a,b in segments]
    network=strips[0].multiFuse(strips[1:]).removeSplitter()
    exclusions=Part.makeCompound([Part.makeBox(xb-xa,yb-ya,height+.3,V(xa,ya,bottom-.1)) for xa,xb,ya,yb in TOP_FIELDS])
    network=network.cut(exclusions).removeSplitter();body(network,'frame network')
    bottom_faces=[f for f in network.Faces if f.BoundBox.ZLength<1e-6 and abs(f.BoundBox.ZMin-bottom)<1e-5]
    if not bottom_faces:raise ValueError('Frame network has no bottom faces')
    face=Part.makeCompound(bottom_faces) if len(bottom_faces)>1 else bottom_faces[0]
    face=face.makeOffset2D(node_radius,0,False,False,True).makeOffset2D(-node_radius,0,False,False,True)
    rounded=_positive(face.extrude(V(0,0,height+.1)))
    if rounded.Volume<network.Volume-.001:raise ValueError('Node rounding lost network volume')
    rounded=rounded.common(Part.makeBox(260.6,37.1,height+.3,V(9.2,-72.8,bottom-.1))).cut(exclusions)
    # Accepted upper_roof_ribs_geometry exports the rounded network.
    # Sweep roots along its actual straight and circular boundaries.
    network=rounded
    air=top_air(slots,p,height+.1);s=panel.fuse(rounded).cut(air)
    edges=[]
    for face in network.Faces:
        if face.BoundBox.ZLength<1e-6 and abs(face.BoundBox.ZMin-bottom)<1e-5:edges.extend(face.Edges)
    roots=[]
    for e in edges:
        a,b=e.ParameterRange;pt=e.valueAt(a);mid=e.valueAt((a+b)/2);t=e.tangentAt((a+b)/2);n=V(-t.y,t.x,0);n.normalize()
        sample_z=bottom+min(1.3,height/2)
        if network.isInside(V(mid.x,mid.y,sample_z)+n*.02,1e-7,False):n=-n
        curve=e.Curve
        if isinstance(curve,Part.Circle):
            n=V(pt.x-curve.Center.x,pt.y-curve.Center.y,0);n.normalize();test=V(mid.x-curve.Center.x,mid.y-curve.Center.y,0);test.normalize()
            if network.isInside(V(mid.x,mid.y,sample_z)+test*.02,1e-7,False):n=-n
        elif not isinstance(curve,Part.Line):raise ValueError('Unsupported root boundary curve')
        pt.z=ceiling
        pts=[pt-n*.05+V(0,0,.05),pt+n*rf+V(0,0,.05),pt+n*rf,pt+V(0,0,-rf),pt-n*.05+V(0,0,-rf)]
        arc=Part.Arc(pts[2],pt+n*(rf-rf/math.sqrt(2))+V(0,0,-rf+rf/math.sqrt(2)),pts[3]).toShape()
        face=Part.Face(Part.Wire([Part.makeLine(pts[0],pts[1]),Part.makeLine(pts[1],pts[2]),arc,Part.makeLine(pts[3],pts[4]),Part.makeLine(pts[4],pts[0])]))
        if isinstance(curve,Part.Circle):q=face.revolve(V(curve.Center.x,curve.Center.y,0),curve.Axis,math.degrees(b-a))
        else:
            dv=e.valueAt(b)-e.valueAt(a);dv.z=0;q=face.extrude(dv)
        q=_positive(q);body(q,'root sweep');roots.append(q)
    if not roots:raise ValueError('No root sweeps')
    q=s.multiFuse(roots)
    if q.Volume<s.Volume-.001:raise ValueError('Root union lost volume')
    # Preserve default z27..39 clip, varying lower bound with actual rib depth.
    clip_bottom=bottom-1.7
    q=q.common(Part.makeBox(260.6,37.1,p['RoofZ']+1.5-clip_bottom,V(9.2,-72.8,clip_bottom)))
    q=q.cut(air)
    field_clear=Part.makeCompound([Part.makeBox(xb-xa,yb-ya,ceiling-clip_bottom,V(xa,ya,clip_bottom)) for xa,xb,ya,yb in TOP_FIELDS])
    q=q.cut(field_clear)
    overlaps={}
    for name,tool in [('channel',air),('field_interior',field_clear)]:
        common=q.common(tool)
        check_boolean_result(common);overlaps[name]=abs(common.Volume)
        if overlaps[name]>1e-3:raise ValueError('Ventilation clearance obstructed: '+name)
    output=save_shape(c,'vent_frames',q)
    return report(c,'vent_frames_provenance',{'vent_frames':output},parameters_consumed=settings,
                  channel_count=len(slots),air_depth=p['Wall']+height+.3,air_inward_extension=height+.1,
                  frame_layout='ONE_OUTER_FRAME_FOUR_SHARED_SEPARATORS',root_sweeps=len(roots),
                  overlaps_mm3=overlaps,rib_pitch_usage='not consumed; fixed existing shared separator positions',
                  frozen_nodes=[],geometry_recipe='upper_roof_ribs_geometry + upper_roof_constructive_roots port')

SPATIAL_INPUTS = {'parameters_source','outer_volume','inner_volume','upper_late','lower_final','inventory'}
SPATIAL_OUTPUTS = {'outer_blended','inner_blended','blended_shell','upper_spatial_blend','spatial_blend_provenance'}

def spatial_edge_candidate(c,length):
    return -95.1<c.y<-80 and 18.59<c.z<30.01 and (c.x<7 or c.x>272.4) and length>.3

def spatial_edges(shape):
    selected=[];records=[]
    for i,e in enumerate(shape.Edges):
        center=e.valueAt(sum(e.ParameterRange)/2)
        if not spatial_edge_candidate(center,e.Length):continue
        adjacent=[f for f in shape.Faces if any(x.isSame(e) for x in f.Edges)]
        if len(adjacent)!=2 or not all(isinstance(f.Surface,Part.Plane) for f in adjacent):continue
        normals=[f.normalAt(*f.Surface.parameter(center)) for f in adjacent]
        if not all(abs(n.z)>.05 for n in normals):continue
        selected.append(e);records.append({'index':i,'center':[center.x,center.y,center.z],'length':e.Length,'normals':[[n.x,n.y,n.z] for n in normals]})
    return selected,records

def checked_boolean(s,name):
    empty=not any(len(getattr(s,key)) for key in ('Solids','Shells','Wires','Faces','Edges','Vertexes'))
    measures=[s.Volume,s.Area,s.Length]
    if not all(math.isfinite(value) for value in measures):raise ValueError('Nonfinite Boolean measure: '+name)
    if empty:
        if any(value!=0 for value in measures):raise ValueError('Empty topology with nonzero measure: '+name)
        if not s.isNull():
            s.check(False)
            if not s.isValid():raise ValueError('Invalid empty topology: '+name)
        return {'volume_mm3':0.,'solids':0,'empty':True,'bbox':None,'bop':'NOT_APPLICABLE_EMPTY_TOPOLOGY'}
    s.check(True)
    if not s.isValid() or s.Volume<0:raise ValueError('Invalid nonempty Boolean: '+name)
    b=s.BoundBox
    return {'volume_mm3':s.Volume,'solids':len(s.Solids),'empty':False,
            'bbox':[b.XMin,b.YMin,b.ZMin,b.XMax,b.YMax,b.ZMax],'bop':'PASS'}

def spatial_delta_guard(delta,record,guard):
    if record['empty']:
        return {'bbox':None,'containment':'NOT_APPLICABLE_EMPTY_TOPOLOGY','outside':'NOT_APPLICABLE_EMPTY_TOPOLOGY'}
    b=record['bbox']
    if any(b[i]<bound-1e-6 for i,bound in enumerate((-20.,-98.,0.))) or any(b[i+3]>bound+1e-6 for i,bound in enumerate((300.,-76.,40.))):raise ValueError('Spatial delta bbox escapes ownership guard')
    outside=checked_boolean(delta.cut(guard),'spatial delta outside ownership guard')
    if not outside['empty']:raise ValueError('Spatial delta has topology outside ownership guard')
    return {'bbox':b,'containment':'EXACT_EMPTY_OUTSIDE','outside':outside['bop']}

def spatial_inventory(rows):
    if not isinstance(rows,list) or not rows:raise ValueError('Nonempty component inventory required')
    selected=[];skipped=[]
    for row in rows:
        if not isinstance(row,dict) or not isinstance(row.get('name'),str):raise ValueError('Malformed inventory row')
        b=row.get('bbox')
        if not isinstance(b,list) or len(b)!=6 or any(isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) for v in b):raise ValueError('Malformed component bbox')
        if not all(abs(v)<10000 for v in b) or min(b[3]-b[0],b[4]-b[1],b[5]-b[2])<.001:
            skipped.append(row['name']);continue
        if b[4]<-98 or b[1]>-79 or (b[0]>11 and b[3]<268.4):continue
        selected.append(row)
    return selected,skipped

def spatial_thickness(outer,shell):
    records=[]
    for fi,f in enumerate(outer.Faces):
        b=f.BoundBox
        if b.YMax<-98 or b.YMin>-79 or (b.XMin>10 and b.XMax<269.4) or b.ZMax<18:continue
        u0,u1,v0,v1=f.ParameterRange
        for iu in range(1,5):
            for iv in range(1,5):
                u=u0+(u1-u0)*iu/5;v=v0+(v1-v0)*iv/5;p=f.valueAt(u,v)
                if not (-98<p.y<-79 and 18<p.z<33 and (p.x<10 or p.x>269.4)):continue
                if f.distToShape(Part.Vertex(p))[0]>1e-6:continue
                n=f.normalAt(u,v);intersection=Part.makeLine(p+n*.02,p-n*6).common(shell)
                checked_boolean(intersection,'normal-ray intersection')
                length=sum(e.Length for e in intersection.Edges)
                if not math.isfinite(length):raise ValueError('Nonfinite thickness sample')
                records.append({'face':fi,'xyz':[p.x,p.y,p.z],'normal':[n.x,n.y,n.z],'material_length':length})
    if not records:raise ValueError('No spatial thickness samples')
    return {'normal_ray_samples':records,'minimum_sampled_thickness':min(r['material_length'] for r in records),
            'scope':'Sampled normal thickness only, not proof of global minimum','global_minimum_proven':False}

def build_spatial_blend(c):
    validate_context(c,'upper_spatial_blend',SPATIAL_INPUTS,SPATIAL_OUTPUTS)
    for key,radius in [('SpatialOuterRadius',1.),('SpatialInnerRadius',3.8)]:
        value=c['parameters'].get(key,radius)
        if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or abs(value-radius)>1e-8:raise ValueError('Unsupported spatial radius: '+key)
    rows,skipped=spatial_inventory(json.loads(verified(c,'inventory').read_text()));_cad()
    outer=read_shape(c,'outer_volume');inner=read_shape(c,'inner_volume')
    blends={};selections={}
    for label,shape,radius,expected in [('outer',outer,1.,4),('inner',inner,3.8,6)]:
        edges,records=spatial_edges(shape)
        if len(edges)!=expected:raise ValueError('Changed spatial edge selection for '+label+': '+str(len(edges)))
        q=shape.makeFillet(radius,edges);body(q,label+' blended',1);blends[label]=q
        selections[label]={'radius':radius,'edges':records,'expected_count':expected,'volume_delta':q.Volume-shape.Volume}
    # Exact source relationship: no raw_shell z16.2 trim applies here.
    old=outer.cut(inner);body(old,'original full envelope shell',1)
    new=blends['outer'].cut(blends['inner']);body(new,'blended full envelope shell',1)
    add=new.cut(old);remove=old.cut(new)
    delta={'added':checked_boolean(add,'spatial add'),'removed':checked_boolean(remove,'spatial remove')}
    guard=Part.makeBox(320,22,40,V(-20,-98,0))
    guard_report={'box_xyz_dxdydz':[-20.,-98.,0.,320.,22.,40.],
                  'added':spatial_delta_guard(add,delta['added'],guard),
                  'removed':spatial_delta_guard(remove,delta['removed'],guard)}
    current=read_shape(c,'upper_late');q=current.copy()
    if not delta['removed']['empty']:q=q.cut(remove,.000001)
    if not delta['added']['empty']:q=q.fuse(add,.000001)
    body(q,'spatial integrated',1)
    lower=read_shape(c,'lower_final');closed=q.common(lower);closed_result=checked_boolean(closed,'closed assembly common')
    if closed_result['volume_mm3']>=.0001:raise ValueError('Spatial upper collides with lower')
    collisions=[];bbox_checks=[]
    for row in rows:
        b=row['bbox'];box=Part.makeBox(b[3]-b[0],b[4]-b[1],b[5]-b[2],V(*b[:3]))
        value=0. if delta['added']['empty'] else checked_boolean(add.common(box),'added/component bbox')['volume_mm3']
        bbox_checks.append({'name':row['name'],'added_common_mm3':value})
        if value>1e-6:collisions.append({'name':row['name'],'bbox_common':value})
    if collisions:raise ValueError('Spatial added material intersects component bounding boxes: '+json.dumps(collisions))
    thickness=spatial_thickness(blends['outer'],new)
    outputs={name:save_shape(c,name,shape) for name,shape in [('outer_blended',blends['outer']),('inner_blended',blends['inner']),('blended_shell',new),('upper_spatial_blend',q)]}
    return report(c,'spatial_blend_provenance',outputs,edge_selection=selections,delta=delta,
                  closed_common_mm3=closed_result['volume_mm3'],bbox_checks=bbox_checks,spatial_operation_guard=guard_report,
                  skipped_degenerate_or_extreme_inventory=skipped,thickness=thickness,
                  source_recipe='test_upper_spatial_blends -> check_spatial_blend_thickness -> integrate_upper_spatial_blend',
                  frozen_nodes=[],raw_shell_clip_applied=False,actual_component_mesh_collision_check='NOT_RUN')
