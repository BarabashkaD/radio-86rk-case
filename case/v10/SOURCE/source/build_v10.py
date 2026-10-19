#!/usr/bin/env python3
"""Fail-closed source reconstruction and release-check orchestration. No existing study script is executed.

Adapters must be deliberately implemented and independently reviewed. A successful
run produces a checked candidate, never automatically authorizes a print release.
"""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
import math
import time
import re
from pathlib import Path
from types import MappingProxyType

ID = re.compile(r'^[a-z][a-z0-9_]*$')
SHA = re.compile(r'^[0-9a-f]{64}$')
REQUIRED_HOOKS = frozenset({
    'geometry_equivalence', 'functional_holes', 'assembly_clearance',
    'ventilation_corridors_and_areas', 'j6_continuous_motion',
    'enter_motion_status', 'feet_continuous_motion', 'reopen_and_cold_rebuild', 'exported_mesh_audit',
})
INPUT_KINDS = {'source', 'electronics', 'layout', 'accepted_geometry', 'reference', 'checkpoint'}
OUTPUT_KINDS = {'brep', 'fcstd', 'step', 'stl', 'json', 'brep_compound', 'brep_faces', 'brep_reference', 'brep_collection'}

class BuildError(RuntimeError):
    pass

def require(condition, message):
    if not condition:
        raise BuildError(message)

def fields(obj, required, optional=()):
    require(isinstance(obj, dict), 'Expected object')
    require(set(required) <= obj.keys(), 'Missing fields: ' + str(set(required)-obj.keys()))
    require(obj.keys() <= set(required)|set(optional), 'Unknown fields: ' + str(obj.keys()-set(required)-set(optional)))

def resource_snapshot():
    import resource
    result={'maxrss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}
    try:
        for line in Path('/proc/self/status').read_text().splitlines():
            if line.startswith('VmRSS:'):result['rss_kib']=int(line.split()[1])
    except (OSError,ValueError):pass
    return result

def identifier(value):
    require(isinstance(value, str) and ID.fullmatch(value), 'Invalid identifier: '+str(value))

def relative_path(value):
    require(isinstance(value, str) and value and '\\' not in value, 'Invalid relative path')
    p = Path(value)
    require(not p.is_absolute() and '..' not in p.parts and value == p.as_posix()
            and value not in ('.', ''), 'Unsafe/noncanonical relative path: '+value)
    return p

def rooted(root, value):
    p = root / relative_path(value)
    # Symlinks are excluded even when their current target remains inside root.
    cursor = root
    for part in relative_path(value).parts:
        cursor = cursor / part
        require(not cursor.is_symlink(), 'Symlink is not an allowed artifact: '+str(cursor))
    require(p.resolve().is_relative_to(root.resolve()), 'Path escapes root')
    return p

def sha256(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1024*1024), b''):
            h.update(block)
    return h.hexdigest()

def validate_manifest(m, input_root, verify_files=True):
    fields(m, {'schema_version','status','build_mode','parameters','inputs','stages','checks','deliverables'}, {'after_checks','diagnostic_artifacts'})
    require(m['schema_version'] == 1, 'Unsupported schema version')
    require(m['status'] in ('template','candidate'), 'Manifest cannot declare release readiness')
    require(m['build_mode'] in ('frozen_node_assembly','full_parametric'), 'Unknown build mode')
    require(isinstance(m['parameters'], dict), 'parameters must be an object')
    try: json.dumps(m, allow_nan=False)
    except (ValueError, TypeError) as ex: raise BuildError('Manifest must contain finite JSON values') from ex
    require(isinstance(m['inputs'], dict) and m['inputs'], 'Explicit inputs required')
    require(isinstance(m['stages'], list) and m['stages'], 'Explicit stages required')
    require(isinstance(m['checks'], list), 'checks must be a list')
    require(isinstance(m.get('after_checks',[]),list),'after_checks must be a list')
    require(all(x.get('owns_enter') is False for x in m.get('after_checks',[])),'Post-check stages cannot own geometry')
    artifacts = {}; input_paths = set()
    for name, item in m['inputs'].items():
        identifier(name); fields(item, {'path','sha256','kind'})
        require(item['kind'] in INPUT_KINDS, 'Unknown input kind')
        require(item['kind'] != 'checkpoint', 'Cold runner does not permit checkpoint inputs')
        require(m['build_mode'] != 'full_parametric' or item['kind'] != 'accepted_geometry',
                'Full parametric mode cannot silently load frozen accepted geometry')
        relative_path(item['path']); require(item['path'] not in input_paths, 'Duplicate input path')
        input_paths.add(item['path'])
        require(isinstance(item['sha256'],str) and SHA.fullmatch(item['sha256'])
                and len(set(item['sha256'])) > 1, 'Missing/placeholder SHA: '+name)
        p = rooted(input_root, item['path'])
        if verify_files:
            require(p.is_file(), 'Missing immutable input: '+name)
            require(sha256(p) == item['sha256'], 'SHA mismatch: '+name)
        artifacts[name] = ('input', item)
    diagnostics=m.get('diagnostic_artifacts',[])
    require(isinstance(diagnostics,list) and len(diagnostics)==len(set(diagnostics)),'Invalid diagnostic allowlist')
    for name in diagnostics:relative_path(name)
    ids = set(); output_paths = set(); enter_owners = []
    for stage in m['stages']+m.get('after_checks',[]):
        fields(stage, {'id','adapter','entrypoint','needs','outputs','owns_enter'})
        identifier(stage['id']); identifier(stage['entrypoint'])
        require(stage['id'] not in ids, 'Duplicate stage id'); ids.add(stage['id'])
        require(stage['adapter'] in m['inputs'] and m['inputs'][stage['adapter']]['kind']=='source',
                'Adapter must be a SHA-pinned source input')
        require(isinstance(stage['needs'],list) and len(set(stage['needs']))==len(stage['needs']), 'Invalid needs')
        require(set(stage['needs']) <= artifacts.keys(), 'Missing or forward dependency in '+stage['id'])
        require(isinstance(stage['owns_enter'],bool), 'owns_enter must be boolean')
        if stage['owns_enter']: enter_owners.append(stage['id'])
        require(isinstance(stage['outputs'],dict) and stage['outputs'], 'Stage outputs required')
        for name, spec in stage['outputs'].items():
            identifier(name); fields(spec, {'path','kind'}, {'solids','objects','bop_evidence','defer_bop','deferred_object_bop'})
            require(name not in artifacts, 'Artifact id already produced: '+name)
            relative_path(spec['path']); require(spec['path'] not in output_paths, 'Duplicate output path')
            require(spec['path'] != 'candidate_report.json', 'Reserved output path')
            output_paths.add(spec['path']); require(spec['kind'] in OUTPUT_KINDS, 'Unknown output kind')
            if 'defer_bop' in spec:
                require(spec['kind']=='brep' and spec['defer_bop'] in ('NOT_COMPLETED_PROCESS_TERMINATED_CAUSE_UNVERIFIED','NOT_RUN_RESOURCE_PRECAUTION'),'Invalid deferred diagnostic status')
                require('bop_evidence' not in spec,'Use either immediate or deferred evidence')
            if 'deferred_object_bop' in spec:
                require(spec['kind']=='fcstd' and isinstance(spec['deferred_object_bop'],dict) and set(spec['deferred_object_bop'])<=set(spec.get('objects',{})),'Invalid deferred document objects')
            if 'bop_evidence' in spec:
                require(spec['kind']=='brep','BOP alternative applies only to BREP')
                relative_path(spec['bop_evidence'])
            if spec['kind'] in ('brep','brep_collection'):
                require(type(spec.get('solids')) is int and spec['solids']>0, 'BREP expected solids required')
            if spec['kind']=='fcstd':
                require(isinstance(spec.get('objects'),dict) and spec['objects'], 'FCStd role/object solids required')
                for obj, solids in spec['objects'].items():
                    require(isinstance(obj,str) and type(solids) is int and solids>0, 'Invalid FCStd object contract')
            artifacts[name] = ('output', spec)
    require(enter_owners == ['upper_details'], 'Enter must have exactly one owner: upper_details')
    post_outputs={name for stage in m.get('after_checks',[]) for name in stage['outputs']}
    hook_ids = []
    for hook in m['checks']:
        fields(hook, {'id','adapter','entrypoint','needs'})
        identifier(hook['id']); identifier(hook['entrypoint']); hook_ids.append(hook['id'])
        require(hook['adapter'] in m['inputs'] and m['inputs'][hook['adapter']]['kind']=='source', 'Unpinned check adapter')
        require(isinstance(hook['needs'],list) and set(hook['needs']) <= artifacts.keys(), 'Unknown check dependency')
        require(not set(hook['needs'])&post_outputs,'Check cannot depend on post-check proof output')
    require(len(hook_ids)==len(set(hook_ids)) and set(hook_ids)==REQUIRED_HOOKS, 'Exact required check allowlist must be supplied')
    require(isinstance(m['deliverables'],list) and m['deliverables'] and len(set(m['deliverables']))==len(m['deliverables']), 'Explicit deliverables required')
    require(all(name in artifacts and artifacts[name][0]=='output' for name in m['deliverables']), 'Deliverables must be generated artifacts')
    require(all(artifacts[n][1]['kind'] not in ('brep_compound','brep_faces','brep_reference','brep_collection') for n in m['deliverables']),'Transport geometry cannot be a print deliverable')
    return artifacts

def topology(shape, solids, evidence_path=None, artifact_sha256=None):
    require(not shape.isNull(), 'Null shape')
    require(math.isfinite(shape.Volume) and shape.Volume>0, 'Nonpositive/nonfinite volume')
    require(len(shape.Solids)==solids, 'Unexpected solid count')
    require(shape.isValid(), 'Invalid BREP')
    if evidence_path is not None:
        from resource_bop_gate import verify_resource_bundle
        shape.check(False)
        alternative=verify_resource_bundle(evidence_path,artifact_sha256)
        return {'volume_mm3':shape.Volume,'solids':len(shape.Solids),'valid':True,**alternative}
    shape.check(True)  # ordinary failure is never reclassified as a resource limit
    return {'volume_mm3':shape.Volume,'solids':len(shape.Solids),'valid':True,'bop':'PASS'}

def check_artifact(path, spec, app, part, preview=False):
    require(path.is_file() and path.stat().st_size>0, 'Missing/empty output: '+str(path))
    result = {'sha256':sha256(path),'bytes':path.stat().st_size,'kind':spec['kind']}
    if (preview or 'defer_bop' in spec) and spec['kind'] in ('brep','brep_compound','brep_faces'):
        shape=part.Shape();shape.read(str(path))
        require(not shape.isNull() and shape.isValid(),'Invalid rebuild preview shape')
        if spec['kind']=='brep':
            require(shape.Volume>0 and len(shape.Solids)==spec['solids'],'Wrong rebuild body topology')
        elif spec['kind']=='brep_compound':require(len(shape.Solids)>0,'Empty rebuild compound')
        else:require(len(shape.Faces)>0 and not shape.Solids,'Invalid rebuild plan')
        result['topology']={'solids':len(shape.Solids),'valid':True,'bop':'NOT_RUN_REBUILD_PREVIEW' if preview else 'PENDING_ALTERNATIVE_GATE','requested_status':spec.get('defer_bop')}
    elif spec['kind']=='brep':
        shape=part.Shape(); shape.read(str(path)); result['topology']=topology(shape,spec['solids'], rooted(path.parent,spec['bop_evidence']) if 'bop_evidence' in spec else None,result['sha256'])
    elif spec['kind'] in ('brep_compound','brep_faces'):
        shape=part.Shape();shape.read(str(path))
        require(not shape.isNull() and shape.isValid(),'Invalid transport geometry')
        shape.check(True)
        if spec['kind']=='brep_compound':
            require(len(shape.Solids)>0,'Compound needs solids')
            for solid in shape.Solids:topology(solid,1)
        else:
            require(len(shape.Faces)>0 and len(shape.Solids)==0,'Plan requires faces and no solids')
            for face in shape.Faces:
                require(face.isValid(),'Invalid plan face');face.check(True)
        result['topology']={'solids':len(shape.Solids),'faces':len(shape.Faces),'bop':'PASS','print_body':False}
    elif spec['kind']=='brep_collection':
        shape=part.Shape();shape.read(str(path));shape.check(False)
        require(not shape.isNull() and shape.isValid(),'Invalid component collection')
        require(len(shape.Solids)==spec['solids'],'Component count mismatch')
        for solid in shape.Solids:topology(solid,1)
        result['topology']={'solids':len(shape.Solids),'individual_bop':'PASS','whole_bop':'NOT_APPLICABLE_OVERLAPPING_COMPONENTS','print_body':False}
    elif spec['kind']=='brep_reference':
        shape=part.Shape();shape.read(str(path));require(not shape.isNull(),'Null external reference')
        bb=shape.BoundBox;bounds=[bb.XMin,bb.YMin,bb.ZMin,bb.XMax,bb.YMax,bb.ZMax]
        require(all(math.isfinite(v) for v in bounds),'Nonfinite reference bounds')
        result['reference']={'ordinary_valid':bool(shape.isValid()),'bop':'NOT_RUN_REFERENCE_ONLY',
            'allowed_use':'CONSERVATIVE_BBOX_KEEPOUT_ONLY','bounds_xyzxyz':bounds,
            'manufacturing_body':False,'boolean_or_distance_proof_allowed':False}
    elif spec['kind']=='fcstd':
        # Adapter must close its document; reading an already-open one is not reopen QA.
        require(not any(Path(d.FileName).resolve()==path.resolve() for d in app.listDocuments().values() if d.FileName), 'Adapter left output document open')
        d=app.openDocument(str(path))
        try:
            result['objects']={}
            for name, count in spec['objects'].items():
                obj=d.getObject(name); require(obj is not None and hasattr(obj,'Shape'), 'Missing saved object: '+name)
                if name in spec.get('deferred_object_bop',{}):
                    sh=obj.Shape;require(not sh.isNull() and sh.isValid() and len(sh.Solids)==count and sh.Volume>0,'Invalid deferred document object')
                    sh.check(False);result['objects'][name]={'valid':True,'solids':count,'bop':'PENDING_LINKED_BODY_GATE','source_artifact':spec['deferred_object_bop'][name]}
                else:result['objects'][name]=topology(obj.Shape,count)
        finally:
            app.closeDocument(d.Name)
    elif spec['kind']=='json':
        json.loads(path.read_text())
    # STEP and STL bytes are hashed here, independently reimported/audited by hooks.
    return result

def invoke(spec, context, inputs, input_root):
    source=inputs[spec['adapter']]; path=rooted(input_root,source['path'])
    require(sha256(path)==source['sha256'], 'Adapter changed after preflight')
    module_name='_v10_'+source['sha256']+'_'+spec['id']
    mspec=importlib.util.spec_from_file_location(module_name,path)
    require(mspec is not None and mspec.loader is not None, 'Cannot load adapter')
    module=importlib.util.module_from_spec(mspec); mspec.loader.exec_module(module)
    function=getattr(module,spec['entrypoint'],None)
    require(callable(function),'Missing adapter entrypoint: '+spec['entrypoint'])
    return function(context)

def debug_resume_prefix(spec,manifest,input_root,output_root):
    """Reuse only verified completed prefix for diagnostics, never a cold/release proof."""
    import shutil
    old_path=Path(spec['manifest_path']);report_path=Path(spec['report_path'])
    require(old_path.is_absolute() and report_path.is_absolute(),'Absolute debug-resume paths required')
    require(not old_path.is_symlink() and sha256(old_path)==spec['manifest_sha256'],'Old manifest changed')
    require(not report_path.is_symlink() and sha256(report_path)==spec['report_sha256'],'Old report changed')
    old=json.loads(old_path.read_text());prior=json.loads(report_path.read_text());origin=report_path.parent
    require(prior['status']=='FAILED','Debug resume requires stopped failed run')
    require(prior['manifest_sha256']==hashlib.sha256(json.dumps(old,sort_keys=True).encode()).hexdigest(),'Prior report/manifest mismatch')
    require(old['parameters']==manifest['parameters'] and old['build_mode']==manifest['build_mode'],'Resume parameters changed')
    completed=prior['stages'];n=len(completed)
    require(0<n<len(manifest['stages']),'Invalid completed prefix')
    required=set();later_adapters={s['adapter'] for s in manifest['stages'][n:]+manifest['checks']+manifest.get('after_checks',[])}
    for before,now,record in zip(old['stages'][:n],manifest['stages'][:n],completed):
        require(before==now and record['id']==now['id'] and record['status'] in ('PASS','DEBUG_REUSED_SHA_VERIFIED'),'Completed stage contract changed')
        required.update(now['needs']);required.add(now['adapter'])
    require(set(old['inputs']).issubset(manifest['inputs']),'Resume removed an input')
    for name,specification in old['inputs'].items():
        if specification!=manifest['inputs'][name]:
            require(name not in required and name in later_adapters,'Completed/helper input changed: '+name)
    records=[];paths={}
    for stage,record in zip(manifest['stages'][:n],completed):
        require(set(record['outputs'])==set(stage['outputs']),'Prior output allowlist mismatch')
        for name,out in stage['outputs'].items():
            source=rooted(origin,out['path']);require(source.is_file() and sha256(source)==record['outputs'][name]['sha256'],'Prior output changed: '+name)
            destination=rooted(output_root,out['path']);destination.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(source,destination);require(sha256(destination)==record['outputs'][name]['sha256'],'Resume copy mismatch')
            paths[name]=destination
        record=dict(record,status='DEBUG_REUSED_SHA_VERIFIED',origin_report_sha256=spec['report_sha256'])
        records.append(record)
    return records,paths

# Proposed insertion into build_v10; no CAD execution.
def prepare_debug_dag(spec,manifest):
    old_path=Path(spec['manifest_path']);report_path=Path(spec['report_path'])
    require(old_path.is_absolute() and report_path.is_absolute(),'Absolute debug paths required')
    require(not old_path.is_symlink() and sha256(old_path)==spec['manifest_sha256'],'Old manifest changed')
    require(not report_path.is_symlink() and sha256(report_path)==spec['report_sha256'],'Old report changed')
    old=json.loads(old_path.read_text());prior=json.loads(report_path.read_text())
    require(prior['status'] in ('FAILED','DEBUG_GEOMETRY_REBUILT_UNVALIDATED','GEOMETRY_REBUILT_UNVALIDATED'),'Only a stopped diagnostic can be resumed')
    require(prior['manifest_sha256']==hashlib.sha256(json.dumps(old,sort_keys=True).encode()).hexdigest(),'Prior report/manifest mismatch')
    require(old['parameters']==manifest['parameters'] and old['build_mode']==manifest['build_mode'],'Resume parameters changed')
    require(set(old['inputs']).issubset(manifest['inputs']),'Resume removed an input')
    records={r['id']:r for r in prior['stages']};require(len(records)==len(prior['stages']),'Duplicate prior stages')
    stages={s['id']:s for s in old['stages']};hashes={n:v['sha256'] for n,v in old['inputs'].items()}
    for record in prior['stages']:
        require(record['id'] in stages and record['status'] in ('PASS','DEBUG_REUSED_SHA_VERIFIED'),'Unverified previous stage')
        require(set(record['outputs'])==set(stages[record['id']]['outputs']),'Prior output contract mismatch')
        hashes.update({n:o['sha256'] for n,o in record['outputs'].items()})
    return {'old':old,'records':records,'stages':stages,'hashes':hashes,'root':report_path.parent,'report_sha256':spec['report_sha256']}

def reuse_debug_stage(state,manifest,stage,known,output_root):
    import shutil
    record=state['records'].get(stage['id'])
    if record is None or state['stages'][stage['id']]!=stage:return None
    adapter=stage['adapter']
    if state['old']['inputs'][adapter]!=manifest['inputs'][adapter]:return None
    for name in stage['needs']:
        if name not in state['hashes'] or sha256(known[name])!=state['hashes'][name]:return None
    # Source helpers declared by this stage are covered by the same needs hashes.
    paths={}
    for name,out in stage['outputs'].items():
        source=rooted(state['root'],out['path'])
        require(source.is_file() and sha256(source)==record['outputs'][name]['sha256'],'Prior output changed: '+name)
        destination=rooted(output_root,out['path']);require(not destination.exists(),'Reused destination exists')
        destination.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,destination)
        require(sha256(destination)==record['outputs'][name]['sha256'],'Debug copy mismatch')
        paths[name]=destination
    return dict(record,status='DEBUG_REUSED_SHA_VERIFIED',origin_report_sha256=state['report_sha256']),paths

def execute(m, input_root, output_root, runtime=None, geometry_only=False, debug_resume=None):
    # Debug reuse may exercise exports/checks, but never becomes an independent cold proof.
    artifacts=validate_manifest(m,input_root)
    require(m['status']=='candidate','Template is not an execution request; reviewed candidate manifest required')
    require(not output_root.exists(),'Use a new nonexistent output directory; no resume/overwrite')
    require(not output_root.resolve().is_relative_to(input_root.resolve()) and
            not input_root.resolve().is_relative_to(output_root.resolve()), 'Input and output roots must be disjoint')
    import FreeCAD as app
    import Part as part
    require(not app.listDocuments(),'Cold build requires no open FreeCAD documents')
    output_root.mkdir(parents=True,exist_ok=False)
    report={'status':'RUNNING','release_ready':False,'build_mode':m['build_mode'],
            'stages':[],'checks':[],'manifest_sha256':hashlib.sha256(json.dumps(m,sort_keys=True).encode()).hexdigest()}
    report_path=output_root/'candidate_report.json'
    def save():report_path.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    known={name:rooted(input_root,item['path']) for name,item in m['inputs'].items()}
    try:
        save()
        reuse=prepare_debug_dag(debug_resume,m) if debug_resume else None
        if reuse is not None:
            report['debug_resume']=dict(debug_resume);report['cold_build_proven']=False;save()
        for stage in m['stages']:
            if geometry_only and stage['id']=='document_export':break
            validate_manifest(m,input_root)
            if reuse is not None:
                found=reuse_debug_stage(reuse,m,stage,known,output_root)
                if found is not None:
                    record,paths=found;report['stages'].append(record);known.update(paths);save();continue
            outputs={name:rooted(output_root,spec['path']) for name,spec in stage['outputs'].items()}
            for path in outputs.values():path.parent.mkdir(parents=True,exist_ok=True)
            context=MappingProxyType({'stage_id':stage['id'],'parameters':json.loads(json.dumps(m['parameters'])),
                'inputs':MappingProxyType({name:known[name] for name in stage['needs']}),
                'input_hashes':MappingProxyType({name:sha256(known[name]) for name in stage['needs']}),
                'outputs':MappingProxyType(outputs),'cold_build':True,'owns_enter':stage['owns_enter'],
                'build_manifest':json.loads(json.dumps(m)),'input_root':str(input_root.resolve()),'output_root':str(output_root.resolve()),'runtime':runtime})
            report['active_stage']=stage['id'];report['active_phase']='geometry';started=time.monotonic();before=resource_snapshot();report['active_resources_before']=before;save()
            invoke(stage,context,m['inputs'],input_root)
            require(not app.listDocuments(),'Stage must close all documents: '+stage['id'])
            observed={name:check_artifact(outputs[name],spec,app,part,preview=geometry_only) for name,spec in stage['outputs'].items()}
            known.update(outputs);report['stages'].append({'id':stage['id'],'status':'PASS','outputs':observed,'elapsed_seconds':time.monotonic()-started,'resources_before':before,'resources_after':resource_snapshot()});save()
        if geometry_only:
            for sr in report['stages']:
                for name,observed in sr['outputs'].items():require(sha256(known[name])==observed['sha256'],'Rebuild artifact changed')
            validate_manifest(m,input_root)
            report['active_stage']=None;report['status']='DEBUG_GEOMETRY_REBUILT_UNVALIDATED' if debug_resume else 'GEOMETRY_REBUILT_UNVALIDATED';report['geometry_artifacts']={name:str(path) for name,path in known.items() if name not in m['inputs']}
            save();return report
        for hook in m['checks']:
            context=MappingProxyType({'check_id':hook['id'],'parameters':json.loads(json.dumps(m['parameters'])),
                'inputs':MappingProxyType({name:known[name] for name in hook['needs']}),
                'input_hashes':MappingProxyType({name:sha256(known[name]) for name in hook['needs']}),'cold_build':True,
                'build_manifest':json.loads(json.dumps(m)),'input_root':str(input_root.resolve()),
                'output_root':str(output_root.resolve()),'runtime':runtime})
            report['active_stage']=hook['id'];report['active_phase']='checks';started=time.monotonic();before=resource_snapshot();report['active_resources_before']=before;save()
            result=invoke(hook,context,m['inputs'],input_root)
            require(isinstance(result,dict) and result.get('status') in ('PASS','CONDITIONAL','FAIL'), 'Invalid check result')
            require(isinstance(result.get('evidence'),dict) and result['evidence'], 'Check requires evidence metrics and artifact SHA')
            report['checks'].append({**result,'id':hook['id'],'elapsed_seconds':time.monotonic()-started,'resources_before':before,'resources_after':resource_snapshot()});save()
            require(result['status']!='FAIL','Check failed: '+hook['id'])
            require(result['status']=='PASS' or hook['id']=='enter_motion_status', 'Unexpected conditional mandatory check')
        # Delayed diagnostics consume actual completed checks; no producer self-certifies rebuild.
        bundle_refs={}
        for stage in m.get('after_checks',[]):
            validate_manifest(m,input_root)
            outputs={name:rooted(output_root,spec['path']) for name,spec in stage['outputs'].items()}
            for path in outputs.values():path.parent.mkdir(parents=True,exist_ok=True)
            context=MappingProxyType({'stage_id':stage['id'],'phase':'after_all_nine_checks',
                'parameters':json.loads(json.dumps(m['parameters'])),
                'inputs':MappingProxyType({name:known[name] for name in stage['needs']}),
                'input_hashes':MappingProxyType({name:sha256(known[name]) for name in stage['needs']}),
                'outputs':MappingProxyType(outputs),'cold_build':True,'owns_enter':False,
                'checks':json.loads(json.dumps(report['checks'])),'build_manifest':json.loads(json.dumps(m)),
                'input_root':str(input_root.resolve()),'output_root':str(output_root.resolve()),'runtime':runtime,
                'diagnostic_decision':{'status':'NOT_RUN_RESOURCE_PRECAUTION','decision_owner':'root',
                    'record':'Do not repeat monolithic BOP after historical process termination; cause unverified.',
                    'decision_record':'Root explicit approval 2026-10-18 for final upper and newly rebuilt keyboard intermediate; all alternative proofs mandatory.',
                    'artifacts':['keyboard_replaced','upper_final'],
                    'artifact_sha256':{name:sha256(known[name]) for name in ('keyboard_replaced','upper_final')}}})
            report['active_stage']=stage['id'];report['active_phase']='after_checks';started=time.monotonic();before=resource_snapshot();report['active_resources_before']=before;save()
            result=invoke(stage,context,m['inputs'],input_root)
            require(not app.listDocuments(),'Post-check stage left documents open')
            observed={name:check_artifact(outputs[name],spec,app,part) for name,spec in stage['outputs'].items()}
            known.update(outputs);report['stages'].append({'id':stage['id'],'status':'PASS','outputs':observed,'elapsed_seconds':time.monotonic()-started,'resources_before':before,'resources_after':resource_snapshot()});save()
            require(isinstance(result,dict),'Post-check stage requires result')
            for name,ref in result.get('bop_alternatives',{}).items():
                require(name not in bundle_refs or bundle_refs[name]==ref,'Conflicting diagnostic bundles')
                bundle_refs[name]=ref
        for result in report['checks']:
            for name,ref in result['evidence'].get('bop_alternatives',{}).items():
                require(name not in bundle_refs or bundle_refs[name]==ref,'Conflicting diagnostic bundles')
                bundle_refs[name]=ref
        from resource_bop_gate import verify_resource_bundle
        deferred={}
        for name,(origin,spec) in artifacts.items():
            if origin=='output' and 'defer_bop' in spec:
                ref=bundle_refs.get(name);require(ref in known,'Missing final diagnostic evidence bundle for '+name)
                proof=verify_resource_bundle(known[ref],sha256(known[name]))
                require(proof['bop']==spec['defer_bop'],'Diagnostic status differs from declared precaution')
                deferred[name]=proof
        for sr in report['stages']:
            for name,observed in sr['outputs'].items():
                if name in deferred:observed['topology'].update(deferred[name])
                for obj in observed.get('objects',{}).values():
                    if obj.get('bop')=='PENDING_LINKED_BODY_GATE':
                        require(obj['source_artifact'] in deferred,'Missing linked body diagnostic proof')
                        obj.update(bop=deferred[obj['source_artifact']]['bop'])
        report['deferred_diagnostics']=deferred
        # Hooks and later stages may not rewrite artifacts already certified.
        for stage_report in report['stages']:
            for name, observed in stage_report['outputs'].items():
                require(sha256(known[name]) == observed['sha256'], 'Artifact changed after its stage: '+name)
        # Inputs are immutable, including source: detect accidental adapter writes.
        validate_manifest(m,input_root)
        allowed={spec['path'] for origin,spec in artifacts.values() if origin=='output'}|{'candidate_report.json'}|set(m.get('diagnostic_artifacts',[]))
        actual={p.relative_to(output_root).as_posix() for p in output_root.rglob('*') if p.is_file() or p.is_symlink()}
        require(actual<=allowed,'Unlisted output files: '+str(actual-allowed))
        require(not any(p.is_symlink() for p in output_root.rglob('*')), 'Symlink in output')
        report['deliverables']={name:{'path':artifacts[name][1]['path'],'sha256':sha256(known[name])} for name in m['deliverables']}
        limited=any(c['status']=='CONDITIONAL' or c.get('evidence',{}).get('limitations') or c.get('evidence',{}).get('physical_status')=='UNVERIFIED_PHYSICAL_TEST_REQUIRED' for c in report['checks']) or any(o.get('topology',{}).get('bop') in ('RESOURCE_LIMIT','NOT_COMPLETED_PROCESS_TERMINATED_CAUSE_UNVERIFIED','NOT_RUN_RESOURCE_PRECAUTION') for stage in report['stages'] for o in stage['outputs'].values())
        report['active_stage']=None
        report['status']=('DEBUG_' if debug_resume else '')+('CANDIDATE_CHECKED_WITH_LIMITATIONS' if limited else 'CANDIDATE_CHECKED')
        save();return report
    except Exception as ex:
        report['status']='FAILED';report['error']=str(ex);report['failure_resources']=resource_snapshot();save();raise

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--manifest',type=Path,required=True)
    p.add_argument('--input-root',type=Path,required=True)
    p.add_argument('--output-root',type=Path)
    p.add_argument('--validate-only',action='store_true')
    p.add_argument('--geometry-only',action='store_true')
    p.add_argument('--runtime-command-json',help='Verified argv prefix for a separate FreeCAD Python process')
    args=p.parse_args();m=json.loads(args.manifest.read_text())
    try:
        validate_manifest(m,args.input_root)
        if args.validate_only:
            print(json.dumps({'status':'INPUTS_VERIFIED','cad_executed':False,'release_ready':False}));return
        require(args.output_root is not None,'--output-root is required for build')
        runtime=None
        if args.runtime_command_json:
            command=json.loads(args.runtime_command_json);require(isinstance(command,list) and command and all(isinstance(x,str) and x for x in command),'Runtime argv required')
            require(Path(command[0]).is_absolute() and Path(command[0]).is_file(),'Explicit existing runtime executable required')
            runtime={'command':command,'runner_path':str(Path(__file__).resolve()),'runner_sha256':sha256(Path(__file__)),'cache_root':str(args.output_root.resolve().parent/'cold_proxy_cache')}
        result=execute(m,args.input_root,args.output_root,runtime=runtime,geometry_only=args.geometry_only);print(json.dumps({'status':result['status'],'release_ready':False}))
    except BuildError as ex:
        p.exit(2,'Build refused: '+str(ex)+'\n')

if __name__=='__main__':main()
