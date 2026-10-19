"""Fresh lower perimeter/grid; geometry parameters are consumed, no checkpoints."""
from contextlib import contextmanager
import importlib.util
import json
import math
from pathlib import Path
import sys
from ventilation_adapter import _parameters
from keyboard_stage_adapter import verified,digest
from geometry_checks import check_boolean_result

@contextmanager
def sources(c,grid=False):
    roles=[('parameters_source','v10_parameters'),('ventilation_source','ventilation_v10'),('rounded_joint_source','rounded_joint_v10'),('ramp_source','rear_ramp_cold')]
    if grid:roles.extend([('lower_grid_layout_source','lower_grid_layout'),('lower_grid_source','lower_grid_cold')])
    old={name:sys.modules.get(name) for _,name in roles};loaded={}
    try:
        for role,name in roles:
            path=verified(c,role);spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);sys.modules[name]=m;spec.loader.exec_module(m);loaded[name]=m
        yield loaded
        for role,_ in roles:verified(c,role)
    finally:
        for name,m in old.items():
            if m is None:sys.modules.pop(name,None)
            else:sys.modules[name]=m

def locked(data):
    expected={'Width':300.,'Depth':215.95,'Wall':2.8,'Floor':3.,'CenterX':139.7,'SideSeamZ':16.2,'RearSeamZ':21.6,'RoofZ':37.5,'RearRampLength':20.,'OuterCornerRadius':5.,'PCBTopZ':14.6}
    for key,value in expected.items():
        if key not in data or not math.isclose(float(data[key]),value,rel_tol=0,abs_tol=1e-8):raise ValueError('Locked geometry '+key)
    pitch=float(data['RibPitch'])
    if not math.isfinite(pitch) or pitch<=0:raise ValueError('Positive RibPitch required')
    return pitch

def shape(path,part):s=part.Shape();s.read(str(path));return s

def object_shape(path,name,app):
    d=app.openDocument(str(path))
    try:
        o=d.getObject(name)
        if o is None or not hasattr(o,'Shape'):raise ValueError('Missing accepted object '+name)
        return o.Shape.copy()
    finally:app.closeDocument(d.Name)

def valid(s,one=True):
    if s.isNull() or not s.isValid() or s.Volume<=0 or (one and len(s.Solids)!=1):raise ValueError('Invalid lower geometry')
    s.check(True)

def save(s,path,part,one=True):
    valid(s,one);s.exportBrep(str(path));q=shape(path,part);valid(q,one)
    for delta in (q.cut(s),s.cut(q)):
        check_boolean_result(delta)
        if abs(delta.Volume)>.001:raise ValueError('Lower save/reopen differs')
    return {'sha256':digest(path),'volume_mm3':q.Volume,'solids':len(q.Solids)}

def start(c,outputs):
    locked(c['parameters'])
    if c.get('cold_build') is not True or set(c['outputs'])!=set(outputs):raise ValueError('Explicit cold outputs required')
    if any(Path(p).exists() for p in c['outputs'].values()):raise ValueError('Output already exists')

def build_perimeter(c):
    start(c,('lower_base','lower_wall','lower_perimeter_provenance'))
    paths={k:verified(c,k) for k in ('lower_foundation','rear_wall','j6_accepted')}
    import FreeCAD as app
    import Part as part
    if app.listDocuments():raise ValueError('Clean CAD context required')
    V=app.Vector
    with sources(c) as mods:
        p=_parameters(mods['v10_parameters'].Parameters,c['parameters']);rg=mods['rear_ramp_cold'];vent=mods['ventilation_v10']
        def mirror(s):
            m=app.Matrix();m.A11=-1;m.A14=2*p.CenterX;q=s.copy();q.transformShape(m);return q
        left=rg.faces(p.SideSeamZ,-214)[0].extrude(V(0,154,0)).common(part.makeBox(p.Wall,154,40,V(-10.3,-214,0)))
        ramp=rg.build(p.RearRampLength)[0].cut(part.makeBox(100,3,40,V(-5.1,-5.85,0)))
        f=rg.faces(p.SideSeamZ,-214)[0];center=V(-5.3,-214,0)
        corner=f.revolve(center,V(0,0,1),90).common(part.makeBox(5,5,40,V(-10.3,-219,0))).common(part.makeCylinder(5,40,center).cut(part.makeCylinder(2.2,40,center)))
        f.rotate(center,V(0,0,1),90);front=f.extrude(V(290,0,0)).common(part.makeBox(290,2.8,40,V(-5.3,-219,0)))
        rear=object_shape(paths['rear_wall'],'LowerRear',app).common(part.makeBox(290,15,40,V(-5.3,-15,0)))
        # Accepted continuous rear: preserve the entire wall below Z6.
        # Never derive a material-removal mask from OCC's loose trimmed-curve bbox.
        j=object_shape(paths['j6_accepted'],'Lower',app).common(part.makeBox(66,30,34.1,V(115,-20,5.9)))
        rear=rear.cut(part.makeBox(66,15,34,V(115,-15,6))).fuse(j,.000001)
        wall=left.multiFuse([mirror(left),ramp,mirror(ramp),corner,mirror(corner),front,rear])
        # Rebuild unperforated geometry each time. Narrowing vents restores material.
        cutters=part.makeCompound(vent.side_cutters(p));wall=wall.cut(cutters)
        foundation=shape(paths['lower_foundation'],part);base=foundation.fuse(wall,.00001)
        records={name:save(q,Path(c['outputs'][name]),part,one=name=='lower_base') for name,q in [('lower_base',base),('lower_wall',wall)]}
        report={'inputs':dict(c['input_hashes']),'parameters':p.manifest(),'outputs':records,'channel_count':len(vent.side_layout(p)[0]),'post_feet_single_rear_required':True,'release_ready':False}
    for k in paths:verified(c,k)
    Path(c['outputs']['lower_perimeter_provenance']).write_text(json.dumps(report,indent=2)+'\n');return report

def build_grid(c):
    start(c,('lower_grid','lower_grid_provenance'))
    paths={k:verified(c,k) for k in ('lower_base','lower_wall','inventory')}
    import FreeCAD as app
    import Part as part
    if app.listDocuments():raise ValueError('Clean CAD context required')
    with sources(c,grid=True) as mods:
        p=_parameters(mods['v10_parameters'].Parameters,c['parameters'])
        result,report,grid=mods['lower_grid_cold'].build(shape(paths['lower_base'],part),shape(paths['lower_wall'],part),json.loads(paths['inventory'].read_text()),p,float(c['parameters']['RibPitch']))
        record=save(result,Path(c['outputs']['lower_grid']),part)
        report.update(input_sha256=dict(c['input_hashes']),output=record,release_ready=False,checkpoint_used=False)
    for k in paths:verified(c,k)
    Path(c['outputs']['lower_grid_provenance']).write_text(json.dumps(report,indent=2)+'\n');return report

def integrate_rear(c):
    start(c,('lower_final','lower_rear_provenance'))
    paths={k:verified(c,k) for k in ('lower_with_feet','rear_lower','j6_accepted')}
    import FreeCAD as app
    import Part as part
    if app.listDocuments():raise ValueError('Clean CAD context required')
    V=app.Vector;lower=shape(paths['lower_with_feet'],part);rear=shape(paths['rear_lower'],part);accepted=object_shape(paths['j6_accepted'],'Lower',app)
    for q in (lower,rear,accepted):valid(q)
    region=part.makeBox(66,40,40,V(115,-32,0));new=rear.common(region)
    diffs=(new.cut(accepted),accepted.cut(new))
    for q in diffs:check_boolean_result(q)
    if sum(abs(q.Volume) for q in diffs)>=.001:raise ValueError('Accepted J6 comparison failed')
    cut=part.makeBox(289.6,3.06,34.1,V(-5.1,-5.85,5.9));replacement=rear.common(part.makeBox(289.62,3.06,34.11,V(-5.11,-5.85,5.89)))
    result=lower.cut(cut).fuse(replacement,1e-7);valid(result)
    allowed=cut.fuse(replacement);before=lower.cut(allowed);after=result.cut(allowed)
    for q in (before.cut(after),after.cut(before)):
        check_boolean_result(q)
        if abs(q.Volume)>.001:raise ValueError('Lower changed outside rear integration band')
    record=save(result,Path(c['outputs']['lower_final']),part)
    for k in paths:verified(c,k)
    report={'inputs':dict(c['input_hashes']),'output':record,'post_feet_repair':True,'release_ready':False}
    Path(c['outputs']['lower_rear_provenance']).write_text(json.dumps(report,indent=2)+'\n');return report
