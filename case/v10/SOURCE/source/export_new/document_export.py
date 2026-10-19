"""Cold export stage; no CAD import until invoked; never performs monolithic BOP.
Model carries external real graph-rebuild proxy, not a false PartDesign history.
"""
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import sys

PRINT_ROLES={'LowerShell':('lower_final','lower'), 'UpperShell':('upper_final','upper'),
 'J6Hatch':('j6_accepted','hatch'), 'FoldFootLeft':('foot_left','left_foot'),
 'FoldFootRight':('foot_right','right_foot')}
REQUIRED_INPUTS={'lower_final','upper_final','j6_accepted','foot_left','foot_right','parameters_source','pad_references','export_proxy_source','export_worker_source'}

def digest(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def encoded(x):return json.dumps(x,sort_keys=True,allow_nan=False)
def checked_shape(shape,count):
    if shape.isNull() or not shape.isValid() or len(shape.Solids)!=count or not math.isfinite(shape.Volume) or shape.Volume<=0:
        raise ValueError('Invalid ordinary shape/solid count')
    return shape

def readonly(obj,name,value,kind='App::PropertyString',group='Provenance'):
    obj.addProperty(kind,name,group);setattr(obj,name,value);obj.setEditorMode(name,1)

def proxy_module():
    p=Path(__file__).with_name('cold_build_proxy.py')
    existing=sys.modules.get('cold_build_proxy')
    if existing is not None:
        if Path(existing.__file__).resolve()!=p.resolve():raise ValueError('Conflicting cold_build_proxy module')
        return existing
    spec=importlib.util.spec_from_file_location('cold_build_proxy',p)
    m=importlib.util.module_from_spec(spec);sys.modules['cold_build_proxy']=m;spec.loader.exec_module(m);return m

def descriptor(context,proxy):
    manifest=context.get('build_manifest')
    worker=Path(__file__).with_name('cold_rebuild_worker.py')
    result={'parameters':dict(context['parameters']),'input_hashes':dict(context['input_hashes']),
      'manifest':manifest,'input_root':str(context.get('input_root','')),
      'output_root':str(context.get('output_root','')),
      'runtime':dict(context.get('runtime') or {}),'worker_path':str(worker.resolve()),
      'worker_sha256':digest(worker),'editable':[]}
    # Diagnostic cache must never leak into independent cold graph runtime.
    result['runtime'].pop('canonical_mesh_reuse',None)
    # No editable control without the complete graph dependency descriptor.
    if isinstance(manifest,dict) and context.get('input_root'):
        result['editable']=[k for k in proxy.EDITABLE if k in result['parameters']]
        result['input_hashes']={k:v['sha256'] for k,v in manifest['inputs'].items()}
        result['input_hashes']['__manifest__']=hashlib.sha256(encoded(manifest).encode()).hexdigest()
    return result

def build_stage(context):
    if not context.get('cold_build'):raise ValueError('Cold context required')
    if not REQUIRED_INPUTS<=set(context['inputs']):raise ValueError('Missing export input')
    required={'model','export_provenance'}|{prefix+'_'+fmt for _,prefix in PRINT_ROLES.values() for fmt in ('stl',)}
    if set(context['outputs'])!=required:raise ValueError('Require FCStd, provenance and STL for all five print parts')
    paths={k:Path(v) for k,v in context['inputs'].items()}
    for k,p in paths.items():
        if not p.is_file() or p.is_symlink() or digest(p)!=context['input_hashes'][k]:raise ValueError('Input SHA mismatch: '+k)
    out={k:Path(v) for k,v in context['outputs'].items()}
    if len({p.resolve() for p in out.values()})!=len(out):raise ValueError('Duplicate output path')
    if any(p.exists() or p.is_symlink() or p.resolve() in {q.resolve() for q in paths.values()} for p in out.values()):raise ValueError('Output exists/aliases input')
    for role,filename in [('export_proxy_source','cold_build_proxy.py'),('export_worker_source','cold_rebuild_worker.py')]:
        if paths[role].resolve()!=Path(__file__).with_name(filename).resolve():raise ValueError('Proxy/worker source closure path mismatch')
    proxy=proxy_module();desc=descriptor(context,proxy)
    import FreeCAD as app
    import Part
    import MeshPart
    def helper(role,name):
        spec=importlib.util.spec_from_file_location(name,paths[role]);module=importlib.util.module_from_spec(spec);sys.modules[name]=module;spec.loader.exec_module(module);return module
    cm=helper('canonical_mesh_source','v10_canonical_mesh')
    reuse_helper=None
    if (context.get('runtime') or {}).get('canonical_mesh_reuse') is not None:
        if 'canonical_mesh_reuse_source' not in paths:raise ValueError('Pinned mesh reuse helper input required')
        reuse_helper=helper('canonical_mesh_reuse_source','v10_canonical_mesh_reuse')
    zf=helper('zero_area_filter_source','v10_zero_area_filter')
    comparison=helper('release_checks_source','v10_mesh_geometry_comparison')
    meshconfig=json.loads(paths['canonical_mesh_config'].read_text());mesh_records={}
    if app.listDocuments():raise ValueError('Export requires no open CAD documents')
    shapes={}
    for name,(role,_) in PRINT_ROLES.items():
        if role=='j6_accepted':
            source=app.openDocument(str(paths[role]))
            try:
                hatch=source.getObject('Hatch')
                if hatch is None:raise ValueError('Accepted J6 FCStd lacks exact Hatch role')
                shapes[name]=checked_shape(hatch.Shape.copy(),1)
            finally:app.closeDocument(source.Name)
        else:
            shape=Part.Shape();shape.read(str(paths[role]));shapes[name]=checked_shape(shape,1)
    pads=Part.Shape();pads.read(str(paths['pad_references']));checked_shape(pads,4)
    doc=app.newDocument('Radio86V10ColdProject')
    try:
        doc.Label='Radio86 v10 | cold graph project | candidate'
        printed=doc.addObject('App::DocumentObjectGroup','PrintParts');printed.Label='Print parts (5)'
        refs=doc.addObject('App::DocumentObjectGroup','ReferenceOnly');refs.Label='References (not for printing)'
        for name,(role,prefix) in PRINT_ROLES.items():
            obj=doc.addObject('Part::Feature',name);obj.Shape=shapes[name]
            obj.Label=name+' | '+('accepted locked J6' if name=='J6Hatch' else 'cold graph output')
            readonly(obj,'SourceRole',role);readonly(obj,'SourceSHA256',context['input_hashes'][role])
            readonly(obj,'PrintPart',True,'App::PropertyBool');printed.addObject(obj)
        pad=doc.addObject('Part::Feature','PadReferences');pad.Shape=pads;refs.addObject(pad)
        readonly(pad,'PrintPart',False,'App::PropertyBool');pad.Label='Rubber pads | reference only'
        if getattr(pad,'ViewObject',None) is not None:pad.ViewObject.Visibility=False
        control=doc.addObject('App::FeaturePython','ColdBuild')
        readonly(control,'FullParametersJSON',encoded(desc['parameters']))
        readonly(control,'DependencyJSON',encoded(desc))
        readonly(control,'ManifestSHA256',hashlib.sha256(encoded(desc['manifest']).encode()).hexdigest())
        readonly(control,'ColdRebuild','NOT_RUN_INITIAL_CANDIDATE')
        readonly(control,'LastError','');readonly(control,'LastBuildDirectory','')
        readonly(control,'BuiltKey',proxy.cache_key(desc['parameters'],desc['input_hashes']))
        readonly(control,'ModelKind','EXTERNAL_COLD_GRAPH_WITH_ACCEPTED_LOCKED_J6')
        readonly(control,'GUIReopenRequirement','cold_build_proxy.py must be on FreeCAD Python path')
        readonly(control,'LockedParameters','Width, Wall, J6 geometry and all non-exposed parameters')
        for key in desc['editable']:
            control.addProperty('App::PropertyFloat',key,'Cold graph drivers');setattr(control,key,float(desc['parameters'][key]))
        if desc['editable']:
            control.addProperty('App::PropertyEnumeration','SideMarginMode','Cold graph drivers')
            control.SideMarginMode=list(proxy.MARGIN_MODES)
            control.SideMarginMode=desc['parameters'].get('SideMarginMode','height_bottom')
            derived=proxy.DEPENDENT[str(control.SideMarginMode)]
            if derived in desc['editable']:control.setEditorMode(derived,1)
        rebuild=proxy.ColdBuildProxy(control,desc)
        if not desc['editable']:control.ColdRebuild='BLOCKED_MISSING_GRAPH_CONTEXT'
        else:
            try:proxy.validate_runtime(desc['runtime'])
            except ValueError as ex:control.ColdRebuild='BLOCKED_RUNTIME_REQUIRED';control.LastError=str(ex)
        doc.recompute()
        for name,(role,prefix) in PRINT_ROLES.items():
            mesh_records[prefix]=cm.export(shapes[name],prefix,out[prefix+'_stl'],runtime=context['runtime'],gmsh_binary=meshconfig['gmsh_binary'],gmsh_sha256=meshconfig['gmsh_sha256'],compare_geometry=comparison.tiled_compare,filter_zero_area=zf.filter_binary_stl,source_brep_sha256=context['input_hashes'][role],reuse_helper=reuse_helper)
        rebuild.armed=True
        doc.saveAs(str(out['model']))
    finally:app.closeDocument(doc.Name)
    reopened=app.openDocument(str(out['model']))
    try:
        for name in PRINT_ROLES:checked_shape(reopened.getObject(name).Shape,1)
        checked_shape(reopened.getObject('PadReferences').Shape,4)
        control=reopened.getObject('ColdBuild')
        if control is None or control.FullParametersJSON!=encoded(desc['parameters']):raise ValueError('Saved parameters mismatch')
        if not isinstance(control.Proxy,proxy.ColdBuildProxy):raise ValueError('Cold proxy not restored')
        status=control.ColdRebuild
    finally:app.closeDocument(reopened.Name)
    for k,p in paths.items():
        if digest(p)!=context['input_hashes'][k]:raise ValueError('Immutable input changed')
    records={k:{'path':str(p),'sha256':digest(p),'bytes':p.stat().st_size} for k,p in out.items() if k!='export_provenance'}
    if any(v['bytes']==0 for v in records.values()):raise ValueError('Empty output')
    report={'status':'EXPORTED_REOPENED_CAD_RELEASE_NOT_PROVEN','release_ready':False,
      'step_export':{'status':'EXCLUDED_FROM_RELEASE','reason':'Historical STEP roundtrip failed; no STEP validity claim'},
      'cold_rebuild':status,'model_kind':'EXTERNAL_COLD_GRAPH_WITH_ACCEPTED_LOCKED_J6',
      'input_sha256':dict(context['input_hashes']),'parameters':desc['parameters'],
      'outputs':records,'bop':'NOT_RUN_EXPORT_ADAPTER','editable':desc['editable'],
      'canonical_meshes':mesh_records,'mesh_tolerance':{'policy':'canonical_mixed_gmsh_upper_netgen_others'},
      'limitations':['Independent STL and assembly audits required','Changed geometry requires explicit save and regenerated exports',
        'External source closure, proxy module and configured FreeCAD Python runtime required',
        'Accepted J6 is locked geometry, not regenerated from dimensions']}
    out['export_provenance'].write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    return report
