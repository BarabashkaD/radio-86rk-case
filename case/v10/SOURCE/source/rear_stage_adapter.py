"""Cold accepted rear feeders. Fixed dimensions are checked, not falsely editable.
No document discovery, checkpoint reads, final union or GUI invocation.
"""
from contextlib import contextmanager
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import sys
from geometry_checks import check_boolean_result

ACCEPTED = {
    'Width':300., 'RearSeamZ':21.6, 'RoofZ':37.5, 'Floor':3., 'Wall':2.8,
    'PCBTopZ':14.6, 'TongueHeight':2., 'JointGap':.3,
    'JointLargeRadius':.6, 'JointSmallRadius':.3,
    'RearOriginX':-10.3, 'RearOuterY':-3.05,
    'RearWindows':[[181.0964,212.4964,27.4],[92.21,113.51,36.36],
                   [31.84,41.44,27.04],[19.293,23.893,21.6]],
    'RearWindowChamfer':.5,
    'RearRCA':[234.95,21.6,5.6],
    'RearU25Box':[45.375,-10.5,4.55,10.85,5.07,29.125],
    'RearJ6BoundsX':[123.25,173.93], 'RearJ6AxisYZ':[-4.45,16.25],
    'RearJ6CutBox':[123.25,-27.85,14.6,50.68,35.,30.],
    'RearJ6SupportRadius':1.65, 'RearJ6SupportLength':3.,
    'RearJ6SocketRadius':1.15,
    'RearJ6ChamferYZ':[[-3.05,14.6],[-3.05,13.4],[-5.05,14.6]],
    'RearSmallReliefBox':[18.793,-6.5,21.6,5.6,4.,3.1],
    'RearUpperResetClosureBox':[18.793,-5.85,21.6,5.6,2.8,3.1],
}

def _equal(a,b):
    if isinstance(b,list):
        return isinstance(a,(list,tuple)) and len(a)==len(b) and all(_equal(x,y) for x,y in zip(a,b))
    return not isinstance(a,bool) and isinstance(a,(int,float)) and math.isfinite(a) and math.isclose(a,b,rel_tol=0,abs_tol=1e-8)

def contract(parameters):
    for key,value in ACCEPTED.items():
        if key not in parameters or not _equal(parameters[key],value):
            raise ValueError('Unsupported accepted rear parameter: '+key)
    return dict(ACCEPTED)

def _verify(context,role):
    p=Path(context['inputs'][role])
    if p.is_symlink() or not p.is_file() or hashlib.sha256(p.read_bytes()).hexdigest()!=context['input_hashes'][role]:
        raise ValueError('Source SHA mismatch: '+role)
    return p

@contextmanager
def sources(context):
    roles={'rounded_joint_source':'rounded_joint_v10','rear_geometry_source':'rear_wall_with_j6_geometry'}
    saved={name:sys.modules.get(name) for name in roles.values()}
    try:
        modules={}
        for role,name in roles.items():
            spec=importlib.util.spec_from_file_location(name,_verify(context,role))
            mod=importlib.util.module_from_spec(spec);sys.modules[name]=mod;spec.loader.exec_module(mod);modules[role]=mod
        yield modules['rear_geometry_source']
        for role in roles:_verify(context,role)
    finally:
        for name,old in saved.items():
            if old is None:sys.modules.pop(name,None)
            else:sys.modules[name]=old

def topology(shape,which):
    if shape.isNull() or not shape.isValid() or not math.isfinite(shape.Volume) or shape.Volume<=0:
        raise ValueError('Invalid rear geometry')
    count=len(shape.Solids)
    if count<1 or (which==0 and count!=1):raise ValueError('Unexpected rear solids')
    shape.check(True)
    return {'solids':count,'volume_mm3':shape.Volume,'valid':True}

def equivalent(a,b):
    values={}
    for name,shape in [('removed_mm3',a.cut(b)),('added_mm3',b.cut(a)),('common_mm3',a.common(b))]:
        values[name+'_topology_check']=check_boolean_result(shape)
        values[name]=abs(shape.Volume)
    if max(values['removed_mm3'],values['added_mm3'],abs(a.Volume-values['common_mm3']),abs(b.Volume-values['common_mm3']))>1e-3:
        raise ValueError('Rear save/reopen mismatch')
    return values

def _build(context,which):
    p=contract(context['parameters']);name='rear_lower' if which==0 else 'rear_upper'
    if set(context['outputs'])!={name,name+'_provenance'}:raise ValueError('Exact rear output contract required')
    # Fail before geometry construction instead of overwriting a prior result.
    if any(Path(x).exists() for x in context['outputs'].values()):raise ValueError('Rear outputs must be new')
    import FreeCAD as app
    import Part
    if app.listDocuments():raise ValueError('Rear feeder needs clean document context')
    with sources(context) as module:
        shape=module.build_lower() if which==0 else module.build_upper()
        original=topology(shape,which);path=Path(context['outputs'][name]);shape.exportBrep(str(path))
        reopened=Part.Shape();reopened.read(str(path));actual=topology(reopened,which)
        if actual['solids']!=original['solids']:raise ValueError('Reopen changed solid count')
        comparison=equivalent(shape,reopened)
    report={'producer':'rear_stage_adapter.build_'+('lower' if which==0 else 'upper'),
            'accepted_parameters':p,'input_sha256':{r:context['input_hashes'][r] for r in ('rounded_joint_source','rear_geometry_source')},
            'output_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'topology':actual,'save_reopen':comparison,
            'j6_supports_present':which==0,'standalone_upper_may_have_multiple_solids':which==1,
            'final_union_gate':'NOT_RUN','baseline_equivalence_gate':'NOT_RUN','release_ready':False}
    Path(context['outputs'][name+'_provenance']).write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    return report

def build_lower(context):return _build(context,0)
def build_upper(context):return _build(context,1)
