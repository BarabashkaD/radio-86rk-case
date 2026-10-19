"""Explicit cold feet stage, pinned legacy implementation, no CAD on import.

Width288 is permitted only inside the pinned legacy layout adapter. The supplied
shell remains Width300. Rubber pads are reference envelopes, not print parts.
"""
from contextlib import contextmanager
import hashlib
import importlib.util
import json
import math
from pathlib import Path
from geometry_checks import check_boolean_result
import sys

FEET_AXES=((40.,-35.,2.5),(239.4,-35.,2.5))
PADS=((10.7,-204.),(268.7,-204.),(10.7,-18.05),(268.7,-18.05))
SOURCES=(('parameters_source','v10_parameters'),('feet_legacy_source','feet_v10_geometry'),('feet_layout_source','feet_v10_adapter'))

def verified(context,name):
    p=Path(context['inputs'][name]);h=context['input_hashes'][name]
    if not p.is_file() or p.is_symlink() or hashlib.sha256(p.read_bytes()).hexdigest()!=h:
        raise ValueError('SHA mismatch: '+name)
    return p

def parameters(p):
    for key,value in {'Width':300.,'Floor':3.,'PCBBottomZ':13.,'PCBThickness':1.6,'CenterX':139.7,'Depth':215.95}.items():
        if key not in p or not math.isfinite(float(p[key])) or not math.isclose(float(p[key]),value,rel_tol=0,abs_tol=1e-8):
            raise ValueError('Fixed feet layout requires '+key+'='+str(value))
    for key,value in [('FeetAxes',FEET_AXES),('PadCentres',PADS)]:
        got=p.get(key,[])
        if len(got)!=len(value) or any(len(a)!=len(b) or any(abs(float(x)-y)>1e-8 or not math.isfinite(float(x)) for x,y in zip(a,b)) for a,b in zip(got,value)):
            raise ValueError('Unapproved '+key)
    if 'FootAngle' not in p:raise ValueError('Explicit FootAngle required')
    a=float(p['FootAngle'])
    if not math.isfinite(a) or not 0<=a<=105:raise ValueError('FootAngle must be 0..105')
    return a

@contextmanager
def sources(context):
    old={name:sys.modules.get(name) for _,name in SOURCES}
    try:
        modules={}
        for role,name in SOURCES:
            p=verified(context,role);spec=importlib.util.spec_from_file_location(name,p)
            if spec is None or spec.loader is None:raise ValueError('Cannot load pinned source')
            module=importlib.util.module_from_spec(spec);sys.modules[name]=module;spec.loader.exec_module(module);modules[role]=module
        yield modules['feet_layout_source']
    finally:
        for name,module in old.items():
            if module is None:sys.modules.pop(name,None)
            else:sys.modules[name]=module

def validate_shape(s,count):
    if s.isNull() or not s.isValid() or len(s.Solids)!=count or not math.isfinite(s.Volume) or s.Volume<=0:
        raise ValueError('Invalid shape/solid count for feet output')
    s.check(True)

def metadata_contract(meta):
    # Validate lengths too: zip alone can silently accept a missing axis.
    axes=meta.get('axes',[])
    if len(axes)!=2 or any(len(a)!=3 or any(not math.isfinite(float(x)) or abs(float(x)-y)>1e-8 for x,y in zip(a,b)) for a,b in zip(axes,FEET_AXES)):
        raise ValueError('Unexpected legacy foot axes')
    pads=meta.get('fixed_pad_centres',[])
    if len(pads)!=4 or any(len(a)!=2 or any(abs(float(x)-y)>1e-8 or not math.isfinite(float(x)) for x,y in zip(a,b)) for a,b in zip(pads,PADS)):
        raise ValueError('Unexpected legacy pad centres')
    if meta.get('actual_case_width')!=300 or meta.get('legacy_layout_span_only')!=288:
        raise ValueError('Width isolation contract failed')
    checks=meta.get('unintended_recess_checks',[])
    if len(checks)!=4 or any(not math.isfinite(float(x['unexpected_recess_volume'])) or abs(float(x['unexpected_recess_volume']))>.001 for x in checks):
        raise ValueError('Unexpected widened-layout pad recess')

def build_feet(context):
    required={'lower_with_feet','foot_left','foot_right','pad_references','feet_provenance'}
    if set(context['outputs'])!=required:raise ValueError('Exact feet-stage outputs required')
    angle=parameters(context['parameters']);lower_path=verified(context,'lower_grid')
    # Optional diagnostic pin is independent from the caller-supplied input_hashes.
    pin=context['parameters'].get('CleanLowerExpectedSHA256')
    if pin is not None and pin!=context['input_hashes']['lower_grid']:raise ValueError('Clean-lower checkpoint pin mismatch')
    import FreeCAD as app
    import Part
    if app.listDocuments():raise ValueError('Feet stage requires no open documents')
    base=Part.Shape();base.read(str(lower_path));validate_shape(base,1)
    b=base.BoundBox
    allowed=Part.makeBox(300.,b.YLength+2.,max(1.,b.ZMax+1.),app.Vector(-10.3,b.YMin-1.,0.))
    outside=base.cut(allowed);outside_check=check_boolean_result(outside)
    if outside.Volume>1e-7 or outside.Area>1e-7 or outside.Length>1e-7:
        raise ValueError('Lower exceeds exact Width300/Z>=0 domain')
    floor_rows=[]
    for x in (-10.3,289.6):
        probe=Part.makeBox(.1,10.,1.,app.Vector(x,-140.,1.))
        missing=probe.cut(base);check_boolean_result(missing)
        if missing.Volume>1e-7:raise ValueError('Missing nominal outer floor support strip')
        floor_rows.append({'x':x,'probe_volume':probe.Volume,'missing_mm3':missing.Volume})
    width_guard={'raw_bbox_diagnostic':[b.XMin,b.YMin,b.ZMin,b.XMax,b.YMax,b.ZMax],
                 'outside_check':outside_check,'outside_mm3':outside.Volume,'floor_strips':floor_rows}
    with sources(context) as module:
        result=module.build(base,angle=angle)
    metadata_contract(result['meta'])
    feet=result.get('individual_folded',[])
    if len(feet)!=2:raise ValueError('Expected exactly two individual feet')
    selected={'lower_with_feet':result['LowerShell'],'pad_references':result['Feet']}
    for name,foot,axis in zip(('foot_left','foot_right'),feet,FEET_AXES):
        q=foot.copy()
        if angle:q.rotate(app.Vector(*axis),app.Vector(1,0,0),angle)
        selected[name]=q
    records={}
    for name,shape in selected.items():
        count=4 if name=='pad_references' else 1;validate_shape(shape,count)
        p=Path(context['outputs'][name]);shape.exportBrep(str(p))
        reloaded=Part.Shape();reloaded.read(str(p));validate_shape(reloaded,count)
        missing=shape.cut(reloaded);extra=reloaded.cut(shape)
        boolean_checks=[check_boolean_result(delta) for delta in (missing,extra)]
        if max(abs(missing.Volume),abs(extra.Volume))>.001:raise ValueError('Saved feet geometry changed')
        records[name]={'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'volume_mm3':reloaded.Volume,'solids':count,
                       'boolean_topology_checks':boolean_checks,'before_minus_after_mm3':missing.Volume,'after_minus_before_mm3':extra.Volume}
    # Recheck source inputs after evaluation; no historical report is treated as PASS.
    for name in ['lower_grid']+[role for role,_ in SOURCES]:verified(context,name)
    report={'producer':'feet_stage_adapter.build_feet','clean_lower_sha256':context['input_hashes']['lower_grid'],
        'sources':{role:context['input_hashes'][role] for role,_ in SOURCES},'outputs':records,'angle_deg':angle,
        'meta':result['meta'],'width_guard':width_guard,'pad_references_are_print_parts':False,
        'continuous_motion_checked':False,'electronics_collision_checked':False,'physical_fit_checked':False,'release_ready':False}
    Path(context['outputs']['feet_provenance']).write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    return report
