"""Explicit, evidence-bound alternative. Never infer RESOURCE_LIMIT from OCC errors."""
import hashlib
import json
from pathlib import Path

CATEGORIES=('local_bop','full_mesh','functional','assembly','cold_rebuild')
def verify_resource_bundle(bundle_path, artifact_sha256):
    path=Path(bundle_path);data=json.loads(path.read_text())
    status=data.get('status')
    if status not in ('RESOURCE_LIMIT','NOT_COMPLETED_PROCESS_TERMINATED_CAUSE_UNVERIFIED','NOT_RUN_RESOURCE_PRECAUTION') or data.get('artifact_sha256')!=artifact_sha256:
        raise ValueError('Wrong resource-limit artifact/status')
    reason=data.get('resource_failure',{}) if status=='RESOURCE_LIMIT' else data.get('diagnostic_availability',{})
    if not reason.get('record'):raise ValueError('Documented diagnostic availability required')
    if status=='RESOURCE_LIMIT' and reason.get('kind') not in ('OOM_KILLED','MEMORY_LIMIT','TIME_LIMIT'):raise ValueError('Explicit observed resource failure required')
    if status=='NOT_RUN_RESOURCE_PRECAUTION' and (reason.get('decision_owner')!='root' or not reason.get('decision_record')):raise ValueError('Documented root precaution decision required')
    diagnostic_key='resource_failure' if status=='RESOURCE_LIMIT' else 'diagnostic_availability'
    checks=data.get('proofs',{})
    if set(checks)!=set(CATEGORIES)|{diagnostic_key}:raise ValueError('Complete alternative proof set required')
    for category,spec in checks.items():
        rel=Path(spec['path'])
        if rel.is_absolute() or '..' in rel.parts:raise ValueError('Unsafe proof path')
        p=path.parent/rel
        if any(q.is_symlink() for q in [p,*p.parents]) or not p.is_file():raise ValueError('Unsafe/missing proof')
        if hashlib.sha256(p.read_bytes()).hexdigest()!=spec['sha256']:raise ValueError('Proof SHA mismatch')
        proof=json.loads(p.read_text())
        if proof.get('artifact_sha256')!=artifact_sha256:raise ValueError('Proof applies to another shape')
        if category==diagnostic_key:
            if proof.get('status')!=status:raise ValueError('Diagnostic evidence mismatch')
            if status=='RESOURCE_LIMIT' and proof.get('kind')!=reason['kind']:raise ValueError('Resource evidence mismatch')
            if status=='NOT_COMPLETED_PROCESS_TERMINATED_CAUSE_UNVERIFIED' and proof.get('cause_verified') is not False:raise ValueError('Do not infer termination cause')
            if status=='NOT_RUN_RESOURCE_PRECAUTION' and (proof.get('decision_owner')!='root' or not proof.get('decision_record')):raise ValueError('Missing documented precaution decision')
        elif proof.get('status')!='PASS':raise ValueError('Alternative proof not PASS')
        if category=='local_bop':
            expected=proof.get('expected_regions');actual=proof.get('checked_regions')
            if not isinstance(expected,list) or not expected or len(set(expected))!=len(expected) or actual!=expected:raise ValueError('Incomplete changed-node/junction coverage')
            nodes=proof.get('node_regions',[]);junctions=proof.get('junction_regions',[])
            if not nodes or not junctions or set(nodes)|set(junctions)!=set(expected):raise ValueError('Both nodes and junction coverage required')
        if category=='full_mesh':
            if proof.get('closed') is not True or proof.get('full_body') is not True or any(proof.get(k)!=0 for k in ('self_intersections','edge_errors','topology_errors')) or proof.get('facets',0)<=0:raise ValueError('Mesh not clean/complete')
        if category in ('functional','assembly','cold_rebuild') and not proof.get('measurements'):raise ValueError('Missing measured evidence')
    return {'bop':status,'alternative_checks':'PASS','artifact_sha256':artifact_sha256,'proof_bundle_sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
