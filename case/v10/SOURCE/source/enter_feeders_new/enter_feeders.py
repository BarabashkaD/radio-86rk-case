"""Cold Enter component producers. No assembly mutation, GUI, discovery or source exec.

Runtime CAD imports are deliberately deferred. Geometry has NOT been executed in
this delivery. The only model assembly owner is the separate upper_details stage.
"""
import hashlib
import json
import math
from pathlib import Path

V09_SHA = 'e1fa1b6c20a1da08d4d0c86b3cd397e0cadad070100ca004078a43a75224d553'
SUPPORTED_SHA = '2b0585ac5b9511ad47e068f5943f2ab4114fd9401ce9dd2b24200706719ada50'
ELECTRONICS_SHA = '69a7b21326895688aa86923bd2094633bb2f038f2043c6379b0d6f62ff8e2d26'
ROLES = tuple('Part__Feature%03d' % i for i in range(10,15))
ROI = (230., -197., 14., 44., 49., 10.)
# Only the seven successful operations in the historical report, in original order.
# Replaying an operation is mandatory; exceptions never silently downgrade geometry.
FILLET_CENTERS = (
 (253.99291338582702,-173.52500009999997,17.400000000000002),
 (254.792913385827,-173.5250001,17.800000000000004),
 (253.19291338582696,-173.5250001,17.800000000000004),
 (271.7464565,-170.99999999999997,18.599999999999998),
 (253.09291299999998,-173.16250005,18.599999999999998),
 (254.52291299999993,-172.43,18.10666666666667),
 (253.90925907093336,-171.81634607093315,17.559396664390647),
)

def digest(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda:f.read(1048576),b''):h.update(chunk)
    return h.hexdigest()

def verified(c,name,expected):
    p=Path(c['inputs'][name])
    if not p.is_absolute() or any(q.is_symlink() for q in (p,*p.parents)):
        raise ValueError('Explicit absolute nonsymlink input required: '+name)
    if not p.is_file() or c['input_hashes'][name]!=expected or digest(p)!=expected:
        raise ValueError('Unapproved or changed input: '+name)
    return p

def contract(c,stage,inputs,outputs):
    if c.get('cold_build') is not True or c.get('stage_id')!=stage or c.get('owns_enter') is not False:
        raise ValueError('Component feeder must be cold and must not own model Enter')
    if set(c['inputs'])!=set(inputs) or set(c['input_hashes'])!=set(inputs) or set(c['outputs'])!=set(outputs):
        raise ValueError('Exact input/output contract required')
    paths=[Path(p) for p in c['outputs'].values()]
    if len(set(paths))!=len(paths):raise ValueError('Output paths alias')
    for p in paths:
        if not p.is_absolute() or p.exists() or any(q.is_symlink() for q in (p,*p.parents)):
            raise ValueError('Fresh absolute nonsymlink output required')
        if not p.parent.is_dir():raise ValueError('Runner must prepare output parent')

def checked(s,solid_count=None,allow_empty=False):
    measures=(s.Volume,s.Area,s.Length)
    if not all(math.isfinite(v) for v in measures):raise ValueError('Nonfinite shape')
    empty=not any(len(getattr(s,n)) for n in ('Solids','Shells','Faces','Wires','Edges','Vertexes'))
    if empty:
        if not allow_empty or any(v!=0 for v in measures):raise ValueError('Unexpected empty shape')
        if not s.isNull():
            s.check(False)
            if not s.isValid():raise ValueError('Invalid empty shape')
        return
    s.check(True)
    if not s.isValid():raise ValueError('Invalid topology')
    if not allow_empty and (s.Volume<=0 or not s.Solids):raise ValueError('Expected volume')
    if solid_count is not None and len(s.Solids)!=solid_count:raise ValueError('Wrong solid count')

def difference(a,b,tolerance=.001):
    q=a.cut(b,1e-7);checked(q,allow_empty=True)
    if abs(q.Volume)>tolerance:raise ValueError('Geometry equivalence/containment failed')
    return q.Volume

def save(s,path,part):
    checked(s);s.exportBrep(str(path));q=part.Shape();q.read(str(path))
    checked(q,len(s.Solids));difference(s,q);difference(q,s)
    return {'sha256':digest(path),'solids':len(s.Solids),'volume_mm3':s.Volume,'bop':'PASS'}

def reference_observation(shape):
    if shape.isNull():raise ValueError('Null electronics reference')
    bb=shape.BoundBox;bounds=[bb.XMin,bb.YMin,bb.ZMin,bb.XMax,bb.YMax,bb.ZMax]
    if not all(math.isfinite(v) for v in bounds):raise ValueError('Nonfinite reference bounds')
    valid=bool(shape.isValid());error=None
    try:shape.check(True)
    except Exception as ex:error=str(ex)
    return {'ordinary_valid':valid,'bop':'ERROR' if error else 'COMPLETED',
            'bop_exception':error,'status':'REFERENCE_INVALID_BBOX_ONLY' if error or not valid else 'REFERENCE_VALID_BBOX_ONLY',
            'bounds_xyzxyz':bounds,'solids':len(shape.Solids),'faces':len(shape.Faces),
            'allowed_use':'CONSERVATIVE_BBOX_KEEPOUT_ONLY','manufacturing_body':False,
            'boolean_or_distance_proof_allowed':False}

def save_reference(shape,path,part,observed):
    shape.exportBrep(str(path));restored=part.Shape();restored.read(str(path))
    if restored.isNull():raise ValueError('Lost electronics reference')
    bb=restored.BoundBox;bounds=[bb.XMin,bb.YMin,bb.ZMin,bb.XMax,bb.YMax,bb.ZMax]
    if any(abs(a-b)>1e-7 for a,b in zip(bounds,observed['bounds_xyzxyz'])):raise ValueError('Reference bounds changed on serialization')
    return dict(observed,sha256=digest(path),saved_ordinary_valid=bool(restored.isValid()),
                roundtrip_scope='BBOX_ONLY_NOT_BOOLEAN_EQUIVALENCE')

def beam(a,b,app,part):
    V=app.Vector;dv=V(b[0]-a[0],b[1]-a[1],0);n=V(-dv.y,dv.x,0);n.normalize()
    p=V(a[0],a[1],17.4);w=1.8;h=1.2;r=.2;t=math.atan(w/2/h)
    zc=r/math.sin(t);ut=r*math.cos(t);zt=zc-r*math.sin(t)
    pp=(p-n*w/2+V(0,0,h),p+n*w/2+V(0,0,h),p+n*ut+V(0,0,zt),p-n*ut+V(0,0,zt))
    wire=part.Wire([part.makeLine(pp[0],pp[1]),part.makeLine(pp[1],pp[2]),part.Arc(pp[2],p+V(0,0,zc-r),pp[3]).toShape(),part.makeLine(pp[3],pp[0])])
    s=part.Face(wire).extrude(dv)
    if s.Volume<0:s.reverse()
    checked(s,1);return s

def partition_fillet_delta(before,after,edge,app,part):
    # Nine disjoint boxes at most, with all changed material confined near the edge.
    a=before.BoundBox;b=after.BoundBox;e=edge.BoundBox
    bounds=[min(a.XMin,b.XMin)-.01,min(a.YMin,b.YMin)-.01,min(a.ZMin,b.ZMin)-.01,
            max(a.XMax,b.XMax)+.01,max(a.YMax,b.YMax)+.01,max(a.ZMax,b.ZMax)+.01]
    xs=sorted(set([bounds[0],bounds[3]]+[v for v in (e.XMin-.6,e.XMax+.6) if bounds[0]<v<bounds[3]]))
    ys=sorted(set([bounds[1],bounds[4]]+[v for v in (e.YMin-.6,e.YMax+.6) if bounds[1]<v<bounds[4]]))
    rows=[];removed=added=before_sum=after_sum=0.
    for x0,x1 in zip(xs,xs[1:]):
        for y0,y1 in zip(ys,ys[1:]):
            box=part.makeBox(x1-x0,y1-y0,bounds[5]-bounds[2],app.Vector(x0,y0,bounds[2]))
            aa=before.common(box);bb=after.common(box)
            checked(aa,allow_empty=True);checked(bb,allow_empty=True)
            minus=aa.cut(bb,1e-7);plus=bb.cut(aa,1e-7);common=aa.common(bb)
            for q in (minus,plus,common):checked(q,allow_empty=True)
            residual=max(abs(aa.Volume-minus.Volume-common.Volume),abs(bb.Volume-plus.Volume-common.Volume))
            if residual>1e-5:raise ValueError('Partition Boolean identity failed')
            near=(x0>=e.XMin-.600001 and x1<=e.XMax+.600001 and y0>=e.YMin-.600001 and y1<=e.YMax+.600001)
            if not near and abs(minus.Volume)+abs(plus.Volume)>1e-5:raise ValueError('Fillet changed material outside edge neighborhood')
            removed+=abs(minus.Volume);added+=abs(plus.Volume);before_sum+=aa.Volume;after_sum+=bb.Volume
            rows.append({'xy':[x0,y0,x1,y1],'removed':minus.Volume,'added':plus.Volume,'common':common.Volume,'identity_error':residual,'near_edge':near})
    if max(abs(before_sum-before.Volume),abs(after_sum-after.Volume))>.001:raise ValueError('Incomplete fillet partition')
    if removed+added>=3:raise ValueError('Partition fillet locality bound exceeded')
    return {'removed_mm3':removed,'added_mm3':added,'partition':rows,'local_boolean_BOP':'PASS'}

def build_enter(c):
    names=('enter_original','enter_supported','enter_addition','enter_provenance')
    contract(c,'enter_support',('v09_reference','enter_supported_reference'),names)
    reference=verified(c,'enter_supported_reference',SUPPORTED_SHA)
    source=verified(c,'v09_reference',V09_SHA)
    import FreeCAD as app
    import Part as part
    # Opening only the explicitly verified file; no search for an active document.
    doc=app.openDocument(str(source))
    try:
        obj=doc.getObject('UpperShell')
        if obj is None or not hasattr(obj,'Shape'):raise ValueError('Missing approved UpperShell')
        whole=obj.Shape.copy()
    finally:app.closeDocument(doc.Name)
    old=whole.common(part.makeBox(*ROI[3:],app.Vector(*ROI[:3])));checked(old,1)
    link=beam((253.992913,-174.3),(253.992913,-171.),app,part).fuse(beam((253.092913,-171.9),(273.492913,-171.9),app,part))
    checked(link,1);s=old.fuse(link,.000001);checked(s,1);before=s.copy();attempts=[]
    diagnostic_dir=Path(c['output_root']).with_name(Path(c['output_root']).name+'_enter_diagnostics')
    diagnostic_dir.mkdir(parents=True,exist_ok=False)
    for index,center in enumerate(FILLET_CENTERS):
        v=app.Vector(*center);edges=sorted(s.Edges,key=lambda e:(e.CenterOfMass-v).Length)
        if not edges or (edges[0].CenterOfMass-v).Length>.2:raise ValueError('Fillet edge missing')
        if len(edges)>1 and abs((edges[1].CenterOfMass-v).Length-(edges[0].CenterOfMass-v).Length)<1e-9:
            raise ValueError('Ambiguous fillet edge')
        q=s.makeFillet(.3,[edges[0]]);checked(q,1)
        if abs(q.Volume-s.Volume)>=3:raise ValueError('Fillet volume change exceeds historical bound')
        # Reject false full-body deltas as observed in the historical diagnostic.
        minus=s.cut(q,1e-7);plus=q.cut(s,1e-7)
        diagnostics={}
        for label,shape in [('before',s),('after',q),('minus',minus),('plus',plus)]:
            target=diagnostic_dir/('%02d_%s.brep'%(index,label));shape.exportBrep(str(target))
            diagnostics[label]={'path':str(target),'sha256':digest(target),'volume':shape.Volume,'ordinary_valid':bool(shape.isValid())}
        row={'center':center,'diagnostics':diagnostics}
        try:
            checked(minus,allow_empty=True);checked(plus,allow_empty=True)
            if abs(minus.Volume)+abs(plus.Volume)>=3:raise ValueError('Fillet locality/equivalence unproven')
            row.update(global_boolean_BOP='PASS',removed_mm3=minus.Volume,added_mm3=plus.Volume)
        except Exception as ex:
            row.update(global_boolean_BOP='FAILED',global_boolean_error=str(ex),alternative='PARTITION_PENDING')
            (diagnostic_dir/('%02d_report.json'%index)).write_text(json.dumps(row,indent=2)+'\n')
            row.update(alternative='FINAL_ACCEPTED_SOURCE_EQUIVALENCE_REQUIRED',diagnostic_status='FAILED_DELTA_DIAGNOSTIC')
        (diagnostic_dir/('%02d_report.json'%index)).write_text(json.dumps(row,indent=2)+'\n')
        attempts.append(row);s=q
    accepted=part.Shape();accepted.read(str(reference));checked(accepted,1)
    accepted_comparison={'generated_minus_reference':difference(s,accepted),'reference_minus_generated':difference(accepted,s)}
    verified(c,'enter_supported_reference',SUPPORTED_SHA)
    addition=s.cut(old,1e-7);checked(addition)
    removed=old.cut(s,1e-7);checked(removed,allow_empty=True)
    rebuilt=old.cut(removed,1e-7).fuse(addition,1e-7);checked(rebuilt,1)
    difference(s,rebuilt);difference(rebuilt,s)
    shapes=dict(enter_original=old,enter_supported=s,enter_addition=addition)
    verified(c,'v09_reference',V09_SHA)
    results={n:save(q,c['outputs'][n],part) for n,q in shapes.items()}
    verified(c,'v09_reference',V09_SHA)
    report={'producer':'enter_feeders.build_enter','source_object':'UpperShell','crop_xyz_size':ROI,
      'input_sha256':dict(c['input_hashes']),'outputs':results,'fillets':attempts,
      'removed_original_mm3':removed.Volume,'assembly_owner':'upper_details','assembly_modified':False,
      'motion_status':'CONDITIONAL','physical_motion':'NOT_VALIDATED','baseline_equivalence':{'status':'PASS','reference_sha256':SUPPORTED_SHA,**accepted_comparison},
      'release_ready':False,'recipe':'rounded triangle plus seven historical successful R0.3 operations'}
    Path(c['outputs']['enter_provenance']).write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    return {**{n:str(c['outputs'][n]) for n in shapes},'provenance':report}

def parent_placement(obj,app,seen=()):
    if obj.Name in seen:raise ValueError('Cyclic App::Part hierarchy')
    parents=[p for p in obj.InList if p.TypeId=='App::Part']
    if len(parents)>1:raise ValueError('Ambiguous App::Part hierarchy')
    if not parents:return app.Placement(),[]
    p=parents[0];outer,chain=parent_placement(p,app,seen+(obj.Name,))
    return outer.multiply(p.Placement),chain+[p.Name]

def matrix_values(placement):
    return list(placement.toMatrix().A)

def extract_stabilizer(c):
    keys=tuple('enter_stabilizer_'+str(i) for i in range(10,15))
    contract(c,'extract_stabilizer',('electronics',),keys+('enter_stabilizer_provenance',))
    source=verified(c,'electronics',ELECTRONICS_SHA)
    p=c['parameters'];top=float(p['PCBBottomZ'])+float(p['PCBThickness'])
    explicit_top=float(p.get('PCBTopZ',top))
    if not math.isfinite(top) or not math.isfinite(explicit_top) or abs(top-14.6)>1e-8 or abs(explicit_top-14.6)>1e-8:
        raise ValueError('Approved electronics datum is exactly Z14.6')
    import FreeCAD as app
    import Part as part
    doc=app.openDocument(str(source));shapes={};rows=[];observations={}
    try:
        for key,name in zip(keys,ROLES):
            obj=doc.getObject(name)
            if obj is None or not hasattr(obj,'Shape'):raise ValueError('Missing exact stabilizer object: '+name)
            s=obj.Shape.copy();parent,chain=parent_placement(obj,app)
            original=matrix_values(s.Placement);s.Placement=parent.multiply(s.Placement)
            s.translate(app.Vector(0,0,14.6));observations[key]=reference_observation(s)
            shapes[key]=s;rows.append({'output':key,'object':name,'label':obj.Label,'parent_chain':chain,
              'parent_matrix':matrix_values(parent),'source_shape_matrix':original,'final_shape_matrix':matrix_values(s.Placement),
              'assembly_translation_mm':[0,0,14.6]})
    finally:app.closeDocument(doc.Name)
    verified(c,'electronics',ELECTRONICS_SHA)
    results={n:save_reference(s,c['outputs'][n],part,observations[n]) for n,s in shapes.items()}
    verified(c,'electronics',ELECTRONICS_SHA)
    report={'producer':'enter_feeders.extract_stabilizer','input_sha256':dict(c['input_hashes']),
      'objects':rows,'outputs':results,'motion_status':'CONDITIONAL','physical_motion':'NOT_VALIDATED',
      'assembly_modified':False,'release_ready':False}
    Path(c['outputs']['enter_stabilizer_provenance']).write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    return report
