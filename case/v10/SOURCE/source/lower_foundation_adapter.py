"""Accepted lower-fan extraction and fixed-v10 foundation; no GUI/discovery/import side effects.

Port of bottom_layout_geometry_solid with explicit template, fixed approved axes,
and typed integration contract. It does not add walls, grids, or feet.
"""
import hashlib
import json
import math
from pathlib import Path
from geometry_checks import check_boolean_result

APPROVED_SHALLOW_SHA='0a84595567c207c343cae2a4e49ed3c9538c5d808c2ebf7723d4692043b15039'
APPROVED_FAN_SHA='63c06374011af1207ab23e5f8d55e7777d35f23a8d8f61369951bbc690e4fa9b'
PCB_AXES=((11.43,-11.43),(267.97,-11.43),(11.43,-91.44),(267.97,-91.44),(139.7,-110.49),(62.23,-204.47),(207.01,-204.47))
CASE_AXES=((-1.8,-198.),(-1.8,-24.),(281.2,-198.),(281.2,-24.))
SOURCE_AXIS=(-1.8,-198.)
# Frozen extraction extent from accepted bottom_layout_study, not a fit tolerance.
FAN_CROP=(-7.5,-214.,2.9,13.7,32.,13.3)
GEOMETRIC_DIFFERENCE_LIMIT_MM3=1e-3

def _verified(context,name,approved=None):
    path=Path(context['inputs'][name]);expected=context['input_hashes'][name]
    if approved is not None and expected!=approved:raise ValueError('Unapproved source hash: '+name)
    if not path.is_file() or path.is_symlink() or hashlib.sha256(path.read_bytes()).hexdigest()!=expected:
        raise ValueError('SHA mismatch: '+name)
    return path

def _solid(shape):
    if shape.isNull() or not shape.isValid() or len(shape.Solids)!=1 or not math.isfinite(shape.Volume) or shape.Volume<=0:
        raise ValueError('Expected one positive valid solid')
    shape.check(True)
    return shape

def _equivalence(a,b):
    _solid(a);_solid(b)
    removed=a.cut(b);added=b.cut(a);common=a.common(b)
    checks=[check_boolean_result(shape) for shape in (removed,added,common)]
    values={'a_minus_b_mm3':abs(removed.Volume),'b_minus_a_mm3':abs(added.Volume),'common_mm3':common.Volume,'boolean_topology_checks':checks}
    tol=GEOMETRIC_DIFFERENCE_LIMIT_MM3
    if max(values['a_minus_b_mm3'],values['b_minus_a_mm3'])>tol or abs(common.Volume-a.Volume)>tol or abs(common.Volume-b.Volume)>tol:
        raise ValueError('Accepted fan geometry mismatch: '+str(values))
    return values

def extract_fan(context):
    if set(context['outputs'])!={'fan','fan_provenance'}:raise ValueError('Exact fan output contract required')
    source=_verified(context,'shallow_cap',APPROVED_SHALLOW_SHA)
    reference=_verified(context,'fan_reference',APPROVED_FAN_SHA)
    import FreeCAD as app
    import Part
    if app.listDocuments():raise ValueError('Fan extraction requires a clean document context')
    doc=app.openDocument(str(source))
    try:
        obj=doc.getObject('Lower')
        if obj is None or not hasattr(obj,'Shape'):raise ValueError('Approved source has no Lower role')
        original=obj.Shape.copy();_solid(original)
    finally:app.closeDocument(doc.Name)
    x,y,z,dx,dy,dz=FAN_CROP
    fan=original.common(Part.makeBox(dx,dy,dz,app.Vector(x,y,z))).removeSplitter();_solid(fan)
    baseline=Part.Shape();baseline.read(str(reference));comparison=_equivalence(fan,baseline)
    out=Path(context['outputs']['fan']);fan.exportBrep(str(out))
    reopened=Part.Shape();reopened.read(str(out));saved_comparison=_equivalence(fan,reopened)
    _verified(context,'shallow_cap',APPROVED_SHALLOW_SHA);_verified(context,'fan_reference',APPROVED_FAN_SHA)
    report={'producer':'lower_foundation_adapter.extract_fan','source_object':'Lower','source_sha256':APPROVED_SHALLOW_SHA,
        'accepted_reference_sha256':APPROVED_FAN_SHA,'output_sha256':hashlib.sha256(out.read_bytes()).hexdigest(),
        'crop_xyz_dxyz':FAN_CROP,'source_axis_xy':SOURCE_AXIS,'reference_comparison':comparison,
        'saved_comparison':saved_comparison,'difference_limit_mm3':GEOMETRIC_DIFFERENCE_LIMIT_MM3,
        'excluded_upper_geometry':True,'release_ready':False}
    Path(context['outputs']['fan_provenance']).write_text(json.dumps(report,indent=2)+'\n')
    return report

def layout_contract(p):
    # This fixed-v10 adapter intentionally refuses dimensional extrapolation of a
    # frozen fan. It is not a generic parametric foundation until verified as such.
    locked={'Width':300.,'Depth':215.95,'CenterX':139.7,'Floor':3.,'Wall':2.8,'OuterCornerRadius':5.,
            'PCBBottomZ':13.,'PCBThickness':1.6,'CaseSeatZ':16.2,'CaseThroughDiameter':3.4,
            'HeadPocketDiameter':6.6,'HeadSeatZ':3.2,'PilotDiameter':4.,'BossDiameter':10.}
    for name,value in locked.items():
        if name not in p or not math.isfinite(float(p[name])) or not math.isclose(float(p[name]),value,rel_tol=0,abs_tol=1e-8):
            raise ValueError('Frozen foundation requires '+name+'='+str(value))
    for key,expected in [('PCBMounts',PCB_AXES),('CaseMounts',CASE_AXES)]:
        supplied=p.get(key,[])
        if len(supplied)!=len(expected) or sorted(map(tuple,supplied))!=sorted(expected):raise ValueError('Unapproved axes: '+key)
    return {'pcb_axes':PCB_AXES,'case_axes':CASE_AXES,'x0':p['CenterX']-p['Width']/2,'x1':p['CenterX']+p['Width']/2,
            'front':-219.,'rear':-3.05,'floor':p['Floor'],'outer_radius':p['OuterCornerRadius']}

def fan_placements(p):
    layout_contract(p);cx=float(p['CenterX']);records=[]
    for x,y in CASE_AXES:
        mirror=x>cx
        base_x=2*cx-SOURCE_AXIS[0] if mirror else SOURCE_AXIS[0]
        records.append({'axis':(x,y),'mirror_x':mirror,'mirror_translation':2*cx,
                        'translation':(x-base_x,y-SOURCE_AXIS[1],0.)})
    return records

def make_foundation(template,p,app,part):
    cfg=layout_contract(p);_solid(template);V=app.Vector;floor=cfg['floor']
    b=part.makeBox(p['Width'],cfg['rear']-cfg['front'],floor,V(cfg['x0'],cfg['front'],0))
    edges=[e for e in b.Edges if e.BoundBox.ZLength>floor-.001 and e.BoundBox.XLength<1e-6 and e.BoundBox.YLength<1e-6]
    if len(edges)!=4:raise ValueError('Expected four base vertical edges')
    b=b.makeFillet(cfg['outer_radius'],edges)
    posts=[]
    for x,y in PCB_AXES:
        post=part.makeCylinder(4,13-(floor-.1),V(x,y,floor-.1))
        root=part.makeCone(4.8,4,.8,V(x,y,floor))
        posts.append(post.fuse(root).cut(part.makeCylinder(2,6.8,V(x,y,6.3))))
    fans=[]
    for placement in fan_placements(p):
        q=template.copy()
        if placement['mirror_x']:
            matrix=app.Matrix();matrix.A11=-1;matrix.A14=placement['mirror_translation'];q.transformShape(matrix)
        q.translate(V(*placement['translation']));_solid(q);fans.append(q)
    b=b.multiFuse(posts+fans).removeSplitter()
    for x,y in CASE_AXES:
        b=b.cut(part.makeCylinder(1.7,18,V(x,y,-1))).cut(part.makeCylinder(3.3,4.2,V(x,y,-1)))
    return _solid(b.removeSplitter())

def build_foundation(context):
    if set(context['outputs'])!={'lower_foundation','lower_foundation_provenance'}:raise ValueError('Exact foundation outputs required')
    path=_verified(context,'fan');reference=_verified(context,'fan_reference',APPROVED_FAN_SHA)
    import FreeCAD as app
    import Part
    if app.listDocuments():raise ValueError('Foundation requires a clean document context')
    fan=Part.Shape();fan.read(str(path));baseline=Part.Shape();baseline.read(str(reference));comparison=_equivalence(fan,baseline)
    shape=make_foundation(fan,context['parameters'],app,Part)
    # Independent shrunken gauges based on frozen functional specification.
    holes={'pcb':[shape.common(Part.makeCylinder(1.99,6.69,app.Vector(x,y,6.31))).Volume for x,y in PCB_AXES],
           'case':[shape.common(Part.makeCylinder(1.69,16.1,app.Vector(x,y,.05))).Volume for x,y in CASE_AXES],
           'heads':[shape.common(Part.makeCylinder(3.29,3.18,app.Vector(x,y,.01))).Volume for x,y in CASE_AXES]}
    if any(abs(v)>1e-6 for vals in holes.values() for v in vals):raise ValueError('Functional hole gauge obstruction')
    out=Path(context['outputs']['lower_foundation']);shape.exportBrep(str(out));reopened=Part.Shape();reopened.read(str(out))
    saved=_equivalence(shape,reopened)
    report={'producer':'lower_foundation_adapter.build_foundation','scope':'fixed accepted v10 foundation only; no grid, walls or feet',
        'fan_reference_comparison':comparison,'fan_input_sha256':context['input_hashes']['fan'],
        'axes':{'pcb':PCB_AXES,'case':CASE_AXES},'fan_placements':fan_placements(context['parameters']),
        'hole_gauges_common_mm3':holes,'volume_mm3':shape.Volume,'saved_comparison':saved,
        'output_sha256':hashlib.sha256(out.read_bytes()).hexdigest(),'release_ready':False}
    Path(context['outputs']['lower_foundation_provenance']).write_text(json.dumps(report,indent=2)+'\n')
    return report
