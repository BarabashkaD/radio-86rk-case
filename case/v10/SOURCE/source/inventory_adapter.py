"""Explicit-path electronics inventory feeder. No CAD activity at import time."""
import hashlib
import json
import math
from pathlib import Path

def _verified(context, name):
    p=Path(context['inputs'][name]);expected=context['input_hashes'][name]
    if not p.is_file() or p.is_symlink():raise ValueError('Missing/nonregular input: '+name)
    if hashlib.sha256(p.read_bytes()).hexdigest()!=expected:raise ValueError('SHA mismatch: '+name)
    return p

def _parent_placement(obj, app, visiting=None):
    visiting=set() if visiting is None else visiting
    token=obj.Name
    if token in visiting:raise ValueError('Cyclic App::Part hierarchy: '+token)
    parents=[p for p in obj.InList if p.TypeId=='App::Part']
    if len(parents)>1:raise ValueError('Ambiguous App::Part parents: '+token)
    if not parents:return app.Placement()
    parent=parents[0]
    return _parent_placement(parent,app,visiting|{token}).multiply(parent.Placement)

def collect(document, app, pcb_top):
    """Preserves inspect_lower_components selection and global placement semantics."""
    rows=[]
    for obj in document.Objects:
        if obj.TypeId=='App::Part' or not hasattr(obj,'Shape') or obj.Shape.isNull():continue
        if any(p.TypeId!='App::Part' and hasattr(p,'Shape') for p in obj.InList):continue
        shape=obj.Shape.copy()
        shape.Placement=_parent_placement(obj,app).multiply(shape.Placement)
        shape.translate(app.Vector(0,0,pcb_top))
        b=shape.BoundBox;box=[b.XMin,b.YMin,b.ZMin,b.XMax,b.YMax,b.ZMax]
        if not all(math.isfinite(float(x)) for x in box):raise ValueError('Nonfinite bounds: '+obj.Name)
        rows.append({'name':obj.Name,'label':obj.Label,'bbox':box,'valid':bool(shape.isValid())})
    if not rows:raise ValueError('Electronics inventory is empty')
    return sorted(rows,key=lambda row:row['name'])

def build_inventory(context):
    if set(context['outputs'])!={'inventory','inventory_provenance'}:raise ValueError('Exact inventory outputs required')
    path=_verified(context,'electronics');p=context['parameters']
    top=float(p['PCBBottomZ'])+float(p['PCBThickness'])
    if not math.isfinite(top) or not math.isclose(top,14.6,abs_tol=1e-8):raise ValueError('Unapproved electronics datum')
    if 'PCBTopZ' in p and not math.isclose(float(p['PCBTopZ']),top,abs_tol=1e-8):raise ValueError('Conflicting PCBTopZ')
    import FreeCAD as app
    if app.listDocuments():raise ValueError('Inventory requires a clean process/document context')
    doc=app.openDocument(str(path))
    try:rows=collect(doc,app,top)
    finally:app.closeDocument(doc.Name)
    # Fail before writing if input changed during the read.
    _verified(context,'electronics')
    out=Path(context['outputs']['inventory']);out.write_text(json.dumps(rows,indent=2,allow_nan=False)+'\n')
    provenance={'producer':'inventory_adapter.build_inventory','source_sha256':context['input_hashes']['electronics'],
        'inventory_sha256':hashlib.sha256(out.read_bytes()).hexdigest(),'pcb_top_z':top,
        'leaf_count':len(rows),'invalid_source_components':[r['name'] for r in rows if not r['valid']],
        'scope':'component bounds and source validity only; not assembly collision validation'}
    Path(context['outputs']['inventory_provenance']).write_text(json.dumps(provenance,indent=2)+'\n')
    return provenance
