"""Pinned canonical ventilation feeders. Layout is pure Python; cutters need FreeCAD."""
from contextlib import contextmanager
from dataclasses import fields
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import sys

@contextmanager
def _sources(context):
    names={'parameters_source':'v10_parameters','ventilation_source':'ventilation_v10'}
    saved={n:sys.modules.get(n) for n in names.values()}
    try:
        loaded={}
        for role,name in names.items():
            path=Path(context['inputs'][role]);expected=context['input_hashes'][role]
            if not path.is_file() or path.is_symlink() or hashlib.sha256(path.read_bytes()).hexdigest()!=expected:
                raise ValueError('Source SHA mismatch: '+role)
            spec=importlib.util.spec_from_file_location(name,path)
            if spec is None or spec.loader is None:raise ValueError('Cannot import pinned source')
            module=importlib.util.module_from_spec(spec);sys.modules[name]=module;spec.loader.exec_module(module);loaded[role]=module
        yield loaded['parameters_source'],loaded['ventilation_source']
    finally:
        for name,old in saved.items():
            if old is None:sys.modules.pop(name,None)
            else:sys.modules[name]=old

def _parameters(cls, data):
    if "SideMarginMode" in data:
        from ventilation_parameters import resolve
        data,_=resolve(data,data["SideMarginMode"])
    names={f.name for f in fields(cls)}
    missing=names-data.keys()
    if missing:raise ValueError('Missing canonical parameters: '+str(sorted(missing)))
    values={k:float(data[k]) for k in names}
    if not all(math.isfinite(v) for v in values.values()):raise ValueError('Nonfinite parameter')
    p=cls(**values).validate()
    for key in ('SideSlotTopMargin','PCBTopZ','CapRadius','CapApexZ'):
        if key in data and not math.isclose(float(data[key]),float(getattr(p,key)),rel_tol=0,abs_tol=1e-8):
            raise ValueError('Conflicting derived parameter: '+key)
    return p

def build_layout(context):
    if set(context['outputs'])!={'ventilation_layout'}:raise ValueError('Exact ventilation_layout output required')
    with _sources(context) as (pm,vm):
        p=_parameters(pm.Parameters,context['parameters']);side,sfields=vm.side_layout(p);top,tfields=vm.top_layout(p)
        report={'producer':'ventilation_adapter.build_layout','sources':{k:context['input_hashes'][k] for k in ('parameters_source','ventilation_source')},
            'parameters':p.manifest(),'side':{'slots':side,'fields':sfields,'count':len(side)},
            'top':{'slots':top,'fields':tfields,'count':len(top)},'rib_anchors':vm.rib_anchors(p),
            'cad_cutters_checked':False,'release_ready':False}
    Path(context['outputs']['ventilation_layout']).write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    return report

def build_cutters(context):
    if set(context['outputs'])!={'side_cutters','top_cutters','ventilation_cutters_provenance'}:
        raise ValueError('Exact cutter outputs required')
    # Extensions are explicit. No silent reuse of a short wall-only cutter for ribs.
    side_extension=float(context['parameters']['VentilationSideInwardExtension'])
    top_extension=float(context['parameters']['VentilationTopInwardExtension'])
    if not all(math.isfinite(x) and x>=0 for x in (side_extension,top_extension)):raise ValueError('Invalid inward extension')
    import Part
    with _sources(context) as (pm,vm):
        p=_parameters(pm.Parameters,context['parameters'])
        groups={'side_cutters':vm.side_cutters(p,side_extension),'top_cutters':vm.top_cutters(p,top_extension)}
        measurements={}
        for name,shapes in groups.items():
            if not shapes:raise ValueError('Empty cutters')
            for shape in shapes:
                if shape.isNull() or not shape.isValid() or shape.Volume<=0 or len(shape.Solids)!=1:raise ValueError('Invalid individual cutter')
                shape.check(True)
            combined=Part.makeCompound(shapes);combined.check(True)
            path=Path(context['outputs'][name]);combined.exportBrep(str(path))
            # Read the saved BREP, not only the in-memory compound.
            reopened=Part.Shape();reopened.read(str(path));reopened.check(True)
            if not reopened.isValid() or len(reopened.Solids)!=len(shapes):raise ValueError('Cutter serialization failed')
            measurements[name]={'solids':len(reopened.Solids),'volume_mm3':reopened.Volume,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
    report={'producer':'ventilation_adapter.build_cutters','sources':{k:context['input_hashes'][k] for k in ('parameters_source','ventilation_source')},
        'extensions':{'side':side_extension,'top':top_extension},'outputs':measurements,
        'legacy_symmetric_difference_checked':False,'release_ready':False}
    Path(context['outputs']['ventilation_cutters_provenance']).write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    return report
