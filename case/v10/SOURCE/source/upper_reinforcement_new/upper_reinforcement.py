"""Cold ports of upper perimeter, accepted shallow-cap bosses, chip roof grid.
No document discovery, GUI, imported study scripts, or CAD activity at import.
CAD execution and equivalence have NOT been performed for this adapter.
"""
import hashlib
import json
import math
from pathlib import Path
from zipfile import ZipFile
import xml.etree.ElementTree as ET

SHALLOW_SHA = '0a84595567c207c343cae2a4e49ed3c9538c5d808c2ebf7723d4692043b15039'
LOCKED = {'Width':300.,'Depth':215.95,'CenterX':139.7,'Wall':2.8,
          'ShoulderZ':30.,'RoofZ':37.5,'DeckZ':20.6,'SideSeamZ':16.2,
          'RearSeamZ':21.6,'RearRampLength':20.,'TongueWidth':1.2,
          'TongueHeight':2.,'GrooveWidth':1.5,'GrooveHeight':2.3,
          'JointGap':.3,'JointLargeRadius':.6,'JointSmallRadius':.3,
          'OuterSeamChamfer':.3,'OuterCornerRadius':5.}
ASSEMBLY_LOCKED = {'PCBThickness': 1.6, 'PCBBottomZ': 13.0, 'RearSeamZ': 21.6, 'RearRampLength': 20.0, 'PCBMounts': [[11.43, -11.43], [267.97, -11.43], [11.43, -91.44], [267.97, -91.44], [139.7, -110.49], [62.23, -204.47], [207.01, -204.47]], 'RearOriginX': -10.3, 'RearOuterY': -3.05, 'RearWindows': [[181.0964, 212.4964, 27.4], [92.21, 113.51, 36.36], [31.84, 41.44, 27.04], [19.293, 23.893, 21.6]], 'RearWindowChamfer': 0.5, 'RearRCA': [234.95, 21.6, 5.6], 'RearU25Box': [45.375, -10.5, 4.55, 10.85, 5.07, 29.125], 'RearJ6BoundsX': [123.25, 173.93], 'RearJ6AxisYZ': [-4.45, 16.25], 'RearJ6CutBox': [123.25, -27.85, 14.6, 50.68, 35.0, 30.0], 'RearJ6SupportRadius': 1.65, 'RearJ6SupportLength': 3.0, 'RearJ6SocketRadius': 1.15, 'RearJ6ChamferYZ': [[-3.05, 14.6], [-3.05, 13.4], [-5.05, 14.6]], 'RearSmallReliefBox': [18.793, -6.5, 21.6, 5.6, 4.0, 3.1], 'RearUpperResetClosureBox': [18.793, -5.85, 21.6, 5.6, 2.8, 3.1]}
BOSS_LOCKED = {'BossDiameter':10.,'CaseSeatZ':16.2,'ScrewLength':20.,
               'HeadSeatZ':3.2,'HeadPocketDiameter':6.6,'CaseThroughDiameter':3.4,
               'InsertLength':5.7,'InsertOD':4.6,'PilotDiameter':4.,
               'CapEdgeZ':23.2,'CapRise':.2,'CapRadius':10.1,'CapApexZ':23.4}
# Deliberately separate from lower RibPitch=40 and root fillets RibRootRadius=.6.
EXPLICIT_DEFAULTS = {'UpperChipRibPitch':44., 'UpperPerimeterRadius':2.,
                     'UpperGussetEdgeRadius':.5, 'FrontTransitionRadius':1.}
CONTRACTS = {
 'upper_perimeter':({'upper_foundation','inner_volume','lower_grid','inventory'},
                     {'upper_perimeter','upper_perimeter_provenance'}),
 'upper_bosses':({'upper_perimeter','upper_foundation','shallow_cap','lower_grid'},
                 {'upper_bosses','upper_bosses_provenance'}),
 'upper_chip_grid':({'upper_bosses','inner_volume','inventory','ventilation_layout'},
                    {'upper_chip_grid','chip_network','chip_masks','chip_plan','upper_chip_grid_provenance'}),
 'upper_details':({'upper_roots','enter_original','enter_supported','enter_addition','lower_grid','inventory'},
                   {'upper_late','front_transition','upper_details_provenance'})}

def require(value,message):
    if not value:raise ValueError(message)

def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def number(p,key,low=0.,high=None):
    value=p[key]
    require(type(value) in (int,float) and math.isfinite(value),'Invalid numeric '+key)
    require(value>low and (high is None or value<=high),'Out of range '+key)
    return float(value)

def parameters(p,stage):
    for key,val in {**LOCKED,**(BOSS_LOCKED if stage=='upper_bosses' else {})}.items():
        require(key in p and type(p[key]) in (int,float) and math.isclose(p[key],val,rel_tol=0,abs_tol=1e-8),'Locked accepted geometry: '+key)
    for key,value in ASSEMBLY_LOCKED.items():
        require(p.get(key)==value,'Locked assembly datum: '+key)
    if stage=='upper_details':return {'FrontTransitionRadius':number(p,'FrontTransitionRadius',.05)}
    if stage=='upper_bosses':
        require(p.get('CaseMounts')==[[-1.8,-198.],[-1.8,-24.],[281.2,-198.],[281.2,-24.]],'Locked CaseMounts')
        return {}
    result={k:number(p,k) for k in ('RibWidth','RibHeight')}
    require(result['RibHeight']<30 and result['RibWidth']<10,'Ribs exceed supported envelope')
    if stage=='upper_perimeter':
        result.update({k:number(p,k) for k in ('UpperPerimeterRadius','UpperGussetEdgeRadius')})
        require(result['UpperGussetEdgeRadius']<min(result['RibWidth'],result['RibHeight'])/2,'Gusset radius exceeds local section')
    else:
        require(p.get('UpperChipAirPolicy','verify_only')=='verify_only','UpperChipAirPolicy corridor_cut unsupported pending CAD equivalence and functional proof')
        result.update({k:number(p,k) for k in ('UpperChipRibPitch','RibNodeRadius')})
        require(result['UpperChipRibPitch']>2*result['RibWidth'],'Pitch too small')
        require(result['RibNodeRadius']<result['UpperChipRibPitch']/2,'Node radius too large')
    return result

def validate(context,stage):
    require(context.get('cold_build') is True and context.get('owns_enter') is (stage=='upper_details'),'Cold stage with correct Enter ownership required')
    require(context.get('stage_id')==stage,'Wrong stage')
    ins,outs=CONTRACTS[stage]
    require(set(context['inputs'])==ins,'Exact input contract: '+stage)
    require(set(context['outputs'])==outs,'Exact output contract: '+stage)
    require(set(context['input_hashes'])==ins,'Exact hash contract required')
    for role,path in context['inputs'].items():
        path=Path(path)
        require(path.is_file() and not path.is_symlink(),'Missing regular input '+role)
        require(digest(path)==context['input_hashes'][role],'Input SHA mismatch '+role)
    paths=[Path(p) for p in context['outputs'].values()]
    require(len(set(p.resolve() for p in paths))==len(paths),'Duplicate output path')
    require(not any(p.exists() or p.is_symlink() for p in paths),'Outputs must not exist')
    require(not set(p.resolve() for p in paths)&set(Path(p).resolve() for p in context['inputs'].values()),'Input/output alias')
    if stage=='upper_bosses':require(context['input_hashes']['shallow_cap']==SHALLOW_SHA,'Only accepted shallow-cap FCStd permitted')
    return parameters(context['parameters'],stage)

def cad():
    import FreeCAD as app
    import Part
    return app,Part,app.Vector

def topology(shape,one=False):
    require(not shape.isNull() and shape.Volume>0 and shape.isValid() and shape.Solids,'Invalid/empty solid shape')
    if one:require(len(shape.Solids)==1,'Expected one connected shell')
    shape.check(True)
    return {'volume_mm3':shape.Volume,'solids':len(shape.Solids),'valid':True,'bop_call_completed':True}

def read(context,role,part):
    shape=part.Shape();shape.read(str(context['inputs'][role]));topology(shape);return shape

def positive(shape):
    if shape.Volume<0:shape.reverse()
    return shape

def component_masks(path,part,V,skip_pcb=False):
    rows=json.loads(Path(path).read_text());require(isinstance(rows,list) and rows,'Empty inventory')
    masks=[]
    for row in rows:
        box=row['bbox'];require(len(box)==6 and all(type(v) in (int,float) and math.isfinite(v) for v in box),'Invalid component bounds')
        if not all(abs(v)<10000 for v in box) or box[3]-box[0]<.001 or box[4]-box[1]<.001 or (skip_pcb and row['name']=='Pcb_cd8b'):continue
        require(box[5]>=box[2],'Reversed component bounds')
        masks.append(part.makeBox(box[3]-box[0]+1,box[4]-box[1]+1,box[5]-box[2]+1,V(box[0]-.5,box[1]-.5,box[2]-.5)))
    return masks

def finish(context,shapes,report,report_role):
    for role,shape in shapes.items():
        if role=='chip_plan':
            require(not shape.isNull() and shape.isValid() and shape.Faces and not shape.Solids,'Invalid planar face transport')
            for face in shape.Faces:
                require(face.Area>0 and face.BoundBox.ZLength<1e-6 and abs(face.BoundBox.ZMin)<1e-6,'Nonplanar chip plan')
                face.check(True)
            result={'faces':len(shape.Faces),'area_mm2':shape.Area,'valid':True,'bop_scope':'EACH_FACE_ONLY'}
        elif role in ('chip_network','chip_masks'):
            require(shape.Solids and shape.isValid(),'Invalid compound transport')
            for solid in shape.Solids:topology(solid,True)
            result={'volume_mm3':shape.Volume,'solids':len(shape.Solids),'valid':True,'bop_scope':'EACH_CONSTITUENT_ONLY'}
        else:result=topology(shape,True)
        path=Path(context['outputs'][role]);shape.exportBrep(str(path))
        result['sha256']=digest(path);report.setdefault('artifacts',{})[role]=result
    # Check immutable inputs again before claiming adapter completion.
    for role,path in context['inputs'].items():require(digest(path)==context['input_hashes'][role],'Input changed '+role)
    report.update(producer='upper_reinforcement.'+context['stage_id'],input_hashes=dict(context['input_hashes']),release_ready=False,geometry_equivalence='NOT_RUN',enter_owned=context['owns_enter'])
    Path(context['outputs'][report_role]).write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    return report

def build_perimeter(context):
    p=validate(context,'upper_perimeter');app,part,V=cad()
    s=read(context,'upper_foundation',part);inside=read(context,'inner_volume',part);low=read(context,'lower_grid',part)
    lowshift=low.copy();lowshift.translate(V(0,0,.3))
    r={'parameters_consumed':p,'fillets':[],'gussets':[], 'limitations':['Front low deck retains only 0.1 mm above accepted G ceiling; no full perimeter radius there.']}
    for loc,coord in [('X',-7.5),('X',286.9),('Y',-5.85)]:
        candidates=[]
        for edge in s.Edges:
            b=edge.BoundBox
            flat=(b.XLength<1e-5 and abs(b.XMin-coord)<1e-5) if loc=='X' else (b.YLength<1e-5 and abs(b.YMin-coord)<1e-5)
            if flat and b.ZMin>25 and edge.Length>5 and b.ZLength<12:candidates.append(edge.CenterOfMass)
        for center in candidates:
            edge=min(s.Edges,key=lambda e:(e.CenterOfMass-center).Length)
            try:
                q=s.makeFillet(p['UpperPerimeterRadius'],[edge]);topology(q)
                require(abs(q.Volume-s.Volume)<3000,'Unexpected fillet volume delta');s=q
                r['fillets'].append({'center':[center.x,center.y,center.z],'status':'APPLIED'})
            except Exception as ex:
                # Legacy explicitly permits local fillet failures. Preserve this, report it.
                r['fillets'].append({'center':[center.x,center.y,center.z],'status':'FAILED','error':str(ex)})
    masks=component_masks(context['inputs']['inventory'],part,V,True)
    masks.append(part.makeBox(73,33,45,V(112,-35.5,0)));mask=part.makeCompound(masks)
    positions=[(V(x,y,0),V(nx,0,0)) for x,nx in [(-7.5,1),(286.9,-1)] for y in [-165,-115,-65]]
    positions += [(V(x,-216.2,0),V(0,1,0)) for x in [35,90,139.7,190,245]]
    positions += [(V(x,-5.85,0),V(0,-1,0)) for x in [25,60,85,225,255]]
    adds=[]
    for point,normal in positions:
        row={'xy':[point.x,point.y]}
        try:
            probe=point+normal*.01
            cross=inside.common(part.makeLine(V(probe.x,probe.y,0),V(probe.x,probe.y,45)))
            require(cross.Vertexes,'No local ceiling');z=max(v.Point.z for v in cross.Vertexes)
            tangent=V(-normal.y,normal.x,0)
            a=point-normal*.08-tangent*(p['RibWidth']/2)+V(0,0,z+.05)
            b=a+V(0,0,-p['RibHeight']-.05);c=a+normal*(p['RibHeight']+.08)
            q=positive(part.Face(part.makePolygon([a,b,c,a])).extrude(tangent*p['RibWidth']))
            edges=[e for e in q.Edges if abs(e.Length-p['RibWidth'])<1e-5]
            try:q=q.makeFillet(p['UpperGussetEdgeRadius'],edges);row['edge_fillet']='APPLIED'
            except Exception as ex:row.update(edge_fillet='FAILED',fillet_error=str(ex))
            q=q.cut(mask).cut(lowshift)
            kept=[sol for sol in q.Solids if sol.Volume>=1 and sol.common(s).Volume>=1e-5]
            adds.extend(kept);row.update(roof_inside=z,kept_solids=len(kept),status='KEPT' if kept else 'MASKED_OR_DISCONNECTED')
        except Exception as ex:row.update(status='FAILED',error=str(ex))
        r['gussets'].append(row)
    for q in adds:
        before=s.Volume;s=s.fuse(q,.00001);require(s.Solids and s.Volume>=before-.001,'Gusset fuse lost volume')
    r['lower_common_mm3']=s.common(low).Volume
    r['incomplete_requested_features']=any(x['status']=='FAILED' for x in r['fillets']+r['gussets']) or any(x.get('edge_fillet')=='FAILED' for x in r['gussets'])
    return finish(context,{'upper_perimeter':s},r,'upper_perimeter_provenance')

def shoulder_skin(part,V):
    """Exact original pre-axis prefix, with Y-span replacements -214..-182.
    Only the upper G profile is used. No study-file execution or imports.
    """
    z=16.2;r=.3;R=.6;h=2.;c=.3;outer=-10.3
    points=[(0,z+.3),(.3,z),(1.,z),('arc',(1+r/math.sqrt(2),z+r-r/math.sqrt(2)),(1.3,z+r)),
            (1.3,z+h+c-R),('arc',(1.9-R/math.sqrt(2),z+h+c-R+R/math.sqrt(2)),(1.9,z+h+c)),(2.8,z+h+c)]
    m=(20.6-30)/(5.8-3.3);b=30-m*3.3;bi=b-2.8*math.sqrt(1+m*m)
    top=(27.2-bi)/m;bottom=(18.6-bi)/m
    points += [(2.8,27.2),(top-outer,27.2),(bottom-outer,18.6),(16.8,18.6),(16.8,20.6),(5.8-outer,20.6),(3.3-outer,30),(0,30)]
    first=last=V(outer+points[0][0],-214,points[0][1]);edges=[]
    for p in points[1:]:
        if p[0]=='arc':
            end=V(outer+p[2][0],-214,p[2][1]);edges.append(part.Arc(last,V(outer+p[1][0],-214,p[1][1]),end).toShape())
        else:end=V(outer+p[0],-214,p[1]);edges.append(part.makeLine(last,end))
        last=end
    edges.append(part.makeLine(last,first));up=part.Face(part.Wire(edges)).extrude(V(0,32,0))
    for xx,zz,rr in [(3.3,30,1.),(5.8,20.6,.6)]:
        selected=[e for e in up.Edges if abs(e.BoundBox.XMin-xx)<1e-5 and abs(e.BoundBox.XMax-xx)<1e-5 and abs(e.BoundBox.ZMin-zz)<1e-5 and abs(e.BoundBox.ZMax-zz)<1e-5 and e.Length>31.9]
        if selected:up=up.makeFillet(rr,selected)
    return up

def shallow_brep(path):
    """Read only pinned Upper BREP; never restore FCStd Python proxies/documents."""
    require(digest(path)==SHALLOW_SHA,'Wrong accepted shallow cap')
    with ZipFile(path) as z:
        root=ET.fromstring(z.read('Document.xml'))
        obj=root.find("./ObjectData/Object[@name='Upper']")
        require(obj is not None,'Missing accepted Upper')
        entry=obj.find("./Properties/Property[@name='Shape']/Part")
        require(entry is not None and entry.get('file')=='Upper.Shape.brp','Unexpected shallow cap shape member')
        placement=obj.find("./Properties/Property[@name='Placement']/PropertyPlacement")
        require(placement is not None,'Missing placement')
        require(all(abs(float(placement.get(k)))<1e-12 for k in ('Px','Py','Pz','Q0','Q1','Q2')) and abs(float(placement.get('Q3'))-1)<1e-12,'Nonidentity frozen placement')
        return z.read('Upper.Shape.brp').decode('ascii')

def integrate_bosses(context):
    validate(context,'upper_bosses');app,part,V=cad()
    s=read(context,'upper_perimeter',part);original=read(context,'upper_foundation',part)
    guard=part.makeBox(310,34,50,V(-15,-30,0))
    s=s.cut(guard).fuse(original.common(guard),.00001);topology(s)
    accepted=part.Shape();accepted.importBrepFromString(shallow_brep(context['inputs']['shallow_cap']))
    source_diagnostic={'ordinary_valid':bool(accepted.isValid()),'BOP':'NOT_RUN','role':'PINNED_EXTRACTION_SOURCE_ONLY'}
    try:
        topology(accepted,True);source_diagnostic['BOP']='PASS'
    except Exception as ex:
        source_diagnostic.update(BOP='FAILED_SOURCE_TOPOLOGY',error=str(ex))
    diagnostic=Path(context['outputs']['upper_bosses_provenance']).with_name('shallow_source_diagnostic.json')
    diagnostic.write_text(json.dumps(source_diagnostic,indent=2)+'\n')
    unit=accepted.cut(shoulder_skin(part,V));require(unit.Solids and unit.Volume>100,'Failed accepted shoulder subtraction')
    pts=[(-220,-1),(0,-1),(0,23.9),(-10,23.9),(-30,18.5),(-220,18.5)]
    vv=[V(-20,y,z) for y,z in pts];below=positive(part.Face(part.makePolygon(vv+[vv[0]])).extrude(V(330,0,0)))
    report={'source_diagnostic':source_diagnostic,'units':[],'cap_source_sha256':SHALLOW_SHA,'seatZ':16.2,'cap_edgeZ':23.2,'cap_apexZ':23.4,'rear_guard_restored':True,'rear_guard_y':[-30,4],'rear_perimeter_rounds_pending':True,'Enter_candidate_added':False,'frozen_boss_radii':True}
    for side in [0,1]:
        for yy in [-198,-24]:
            q=unit.copy();q.translate(V(0,yy+198,0));axis=-1.8
            if side:
                matrix=app.Matrix();matrix.A11=-1;matrix.A14=279.4;q.transformShape(matrix);axis=281.2
            core=part.makeCylinder(5,40,V(axis,yy,0));q=q.cut(below.cut(core));topology(q)
            cap=q.common(part.makeCylinder(2.,.21,V(axis,yy,23.2)));topology(cap)
            require(cap.Volume>0,'Missing accepted shallow cap')
            before=s.Volume;s=s.fuse(q,.00001);require(s.Solids and s.Volume>=before-.001,'Boss fuse lost volume')
            report['units'].append({'axis':[axis,yy],'volume_mm3':q.Volume,'solids':len(q.Solids),'unit_BOP':'PASS','cap_BOP':'PASS','cap_volume_mm3':cap.Volume})
    low=read(context,'lower_grid',part);report['closed_common_mm3']=s.common(low).Volume
    return finish(context,{'upper_bosses':s},report,'upper_bosses_provenance')

def chip_segments(pitch):
    require(type(pitch) in (int,float) and math.isfinite(pitch) and pitch>0,'Invalid chip pitch')
    slope=1/math.sqrt(3);dy=pitch/math.cos(math.pi/6);segments=[]
    # Legacy +/-8 is insufficient for small edited pitch. Derive the covering range.
    kmin=math.floor(-294.4*slope/dy)-1;kmax=math.ceil(89.15/dy)+1
    require(kmax-kmin<10000,'Excessively dense grid')
    for sign in [1,-1]:
        x=-7.5 if sign==1 else 286.9
        for k in range(kmin,kmax+1):
            y=-95+k*dy;a=max(0,(-95-y)/slope);b=min(294.4,(-5.85-y)/slope)
            if b>a:segments.append(((x+sign*a,y+a*slope),(x+sign*b,y+b*slope)))
    return segments

def strip(a,b,width,part,V):
    dx=b[0]-a[0];dy=b[1]-a[1];length=math.hypot(dx,dy)
    n=V(-dy/length*width/2,dx/length*width/2,0);p=V(*a,0);q=V(*b,0)
    pts=[p+n,q+n,q-n,p-n]
    return positive(part.Face(part.makePolygon(pts+[pts[0]])).extrude(V(0,0,40)))

def ventilation(context,part,V):
    layout=json.loads(Path(context['inputs']['ventilation_layout']).read_text())
    require(layout.get('producer')=='ventilation_adapter.build_layout','Expected canonical ventilation layout')
    p=context['parameters'];stored=layout['parameters']
    keys=('RoofZ','Wall','TopSlotAngle','TopSlotPitch','TopSlotExternalWidth','TopSlotLength')
    for key in keys:
        value=number(p,key)
        require(type(stored[key]) in (int,float) and math.isclose(value,stored[key],rel_tol=0,abs_tol=1e-8),'Stale canonical ventilation '+key)
    require(p['TopSlotAngle']<=90 and p['TopSlotExternalWidth']<p['TopSlotPitch'],'Invalid top slots')
    slots=layout['top']['slots'];require(slots and len(slots)==layout['top']['count'],'Invalid canonical slots')
    # Cut through all roof/rib heights. Frame box remains exact legacy exclusion.
    k=1/math.tan(math.radians(p['TopSlotAngle']));depth=p['RoofZ']+.2
    cutters=[]
    for slot in slots:
        xa,ya,xb,yb=slot['rect'];dx,dy=slot['bottom_dir']
        require(all(type(v) in (int,float) and math.isfinite(v) for v in [xa,ya,xb,yb,dx,dy]) and xb>xa and yb>ya,'Invalid canonical rect')
        require((dx,dy) in ((1,0),(-1,0),(0,-1)),'Invalid top channel direction')
        pts=[V(x-.1*k*dx,y-.1*k*dy,p['RoofZ']+.1) for x,y in [(xa,ya),(xb,ya),(xb,yb),(xa,yb)]]
        cutters.append(positive(part.Face(part.makePolygon(pts+[pts[0]])).extrude(V(depth*k*dx,depth*k*dy,-depth))))
    return cutters

def build_chip_grid(context):
    p=validate(context,'upper_chip_grid');app,part,V=cad()
    s=read(context,'upper_bosses',part);inside=read(context,'inner_volume',part)
    down=inside.copy();down.translate(V(0,0,-p['RibHeight']));layer=inside.cut(down)
    segments=chip_segments(p['UpperChipRibPitch']);parts=[strip(a,b,p['RibWidth'],part,V) for a,b in segments]
    net=parts[0].multiFuse(parts[1:]).removeSplitter()
    faces=[f for f in net.Faces if f.BoundBox.ZLength<1e-6 and abs(f.BoundBox.ZMin)<1e-6]
    require(faces,'Missing grid plan face');f=part.makeCompound(faces) if len(faces)>1 else faces[0]
    f=f.makeOffset2D(p['RibNodeRadius'],0,False,False,True).makeOffset2D(-p['RibNodeRadius'],0,False,False,True)
    net=positive(f.extrude(V(0,0,40))).common(layer)
    masks=[part.makeBox(258.3,35,50,V(10.25,-71.75,0)),part.makeBox(73,33,50,V(112,-35.5,0)),part.makeCylinder(4,45,V(257.8088,-13.97,0))]
    masks += component_masks(context['inputs']['inventory'],part,V)
    for x,y in [(11.43,-11.43),(267.97,-11.43),(11.43,-91.44),(267.97,-91.44),(139.7,-110.49)]:masks.append(part.makeCylinder(3.1,45,V(x,y,0)))
    # Canonical air is a clearance gate, not a hidden change to accepted-default geometry.
    air=ventilation(context,part,V);mask=part.makeCompound(masks)
    net=net.cut(mask);shifted=net.copy();shifted.translate(V(0,0,.05));net=net.fuse(shifted).cut(mask)
    kept=[q for q in net.Solids if q.Volume>1 and q.common(s).Volume>1e-6];require(kept,'No connected roof ribs')
    net=part.makeCompound(kept);before=s.Volume;s=s.fuse(net,.00001);require(s.Volume>=before-.001,'Grid fuse lost volume')
    air_common=net.common(part.makeCompound(air)).Volume
    require(air_common<1e-6,'Chip ribs intersect canonical ventilation; explicit geometry review required')
    report={'parameters_consumed':p,'segments':segments,'kept_solids':len(kept),'mask_solids':len(mask.Solids),'root_radius_pending':True,'canonical_top_channels':len(air),'channel_network_common_mm3':air_common,'canonical_air_policy':'VERIFY_ONLY_NO_GEOMETRY_CHANGE','scope':'Chip region Y>=-95, local component masks, canonical channel clearance. Root fillets belong to later stages.'}
    return finish(context,{'upper_chip_grid':s,'chip_network':net,'chip_masks':mask,'chip_plan':f},report,'upper_chip_grid_provenance')

def front_transition(radius,part,V):
    """Port of front_roof_smooth_transition.build, accepted G and deck fixed."""
    start_y=-216.2;groove_z=18.5;deck_z=18.6;x0=3.434579985474514;x1=275.9654200145255
    h=deck_z-groove_z;require(0<h<2*radius,'Transition requires 0<rise<2R')
    theta=math.acos(1-h/(2*radius));d=radius*math.sin(theta);midy=start_y+d;endy=start_y+2*d
    a=V(x0,start_y,groove_z);m=V(x0,midy,groove_z+h/2);b=V(x0,endy,deck_z)
    ma=V(x0,start_y+radius*math.sin(theta/2),groove_z+radius*(1-math.cos(theta/2)))
    mb=V(x0,endy-radius*math.sin(theta/2),deck_z-radius*(1-math.cos(theta/2)))
    c=V(x0,endy,deck_z+.05);e=V(x0,start_y-.01,deck_z+.05);f=V(x0,start_y-.01,groove_z)
    face=part.Face(part.Wire([part.Arc(a,ma,m).toShape(),part.Arc(m,mb,b).toShape(),part.makeLine(b,c),part.makeLine(c,e),part.makeLine(e,f),part.makeLine(f,a)]))
    q=positive(face.extrude(V(x1-x0,0,0)));topology(q,True)
    return q,{'radius':radius,'rise':h,'inward_span':2*d,'start_y':start_y,'end_y':endy,'groove_ceiling':groove_z,'deck_inside':deck_z}

def build_details(context):
    """Sole Enter delta application + front transition. No keyboard-node trimming."""
    p=validate(context,'upper_details');app,part,V=cad()
    s=read(context,'upper_roots',part)
    original=read(context,'enter_original',part);supported=read(context,'enter_supported',part)
    removal=original.cut(supported);require(0<=removal.Volume<5,'Enter rounding removal Boolean failed')
    # Empty removal is allowed; do not run positive-volume topology on it.
    if removal.Volume>1e-7:
        topology(removal);s=s.cut(removal,.000001);topology(s,True)
    link=read(context,'enter_addition',part);b=link.BoundBox
    require(link.Volume<100 and b.XMin>252.7 and b.XMax<273.6 and b.YMin>-175 and b.YMax<-170.8 and b.ZMin>17.3 and b.ZMax<18.7,'Unexpected Enter addition extent')
    before=s.Volume;s=s.fuse(link,.000001);topology(s,True)
    require(s.Volume>=before-.001,'Enter fuse lost volume')
    report={'keyboard_trimming_applied':False,'Enter_original_removed_mm3':removal.Volume,'Enter_rounded_added':True,'Enter_addition_volume_mm3':link.Volume,'Enter_actual_added_mm3':s.Volume-before,'Enter_motion_status':'CONDITIONAL','parameters_consumed':p}
    q,meta=front_transition(p['FrontTransitionRadius'],part,V)
    low=read(context,'lower_grid',part);require(q.common(low).Volume<.0001,'Front transition intersects lower')
    collisions=[];rows=json.loads(Path(context['inputs']['inventory']).read_text());require(isinstance(rows,list) and rows,'Empty inventory')
    for component in rows:
        box=component['bbox'];require(len(box)==6 and all(type(v) in (int,float) and math.isfinite(v) for v in box),'Invalid component bounds')
        if not all(abs(v)<10000 for v in box) or min(box[3]-box[0],box[4]-box[1],box[5]-box[2])<.001:continue
        if box[4]<q.BoundBox.YMin or box[1]>q.BoundBox.YMax or box[2]>18.65 or box[5]<18.5:continue
        solid=part.makeBox(box[3]-box[0],box[4]-box[1],box[5]-box[2],V(*box[:3]));common=q.common(solid).Volume
        if common>1e-6:collisions.append({'name':component['name'],'bbox_common_mm3':common})
    require(not collisions,'Front transition component collisions: '+str(collisions))
    s=s.fuse(q,.000001)
    report.update(front_transition=meta,front_transition_component_bbox_collisions=collisions,closed_common_mm3=s.common(low).Volume)
    return finish(context,{'upper_late':s,'front_transition':q},report,'upper_details_provenance')
