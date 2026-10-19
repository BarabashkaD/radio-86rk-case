"""Isolated stage24 adapter. Stable root-stage source is unchanged.
Requires the runner's explicit SHA-pinned helper closure; no CAD at import.
"""
import json
import hashlib
import math
from pathlib import Path
from upper_root_adapters import inputs,read,save,accepted_g_fragment
from keyboard_stage_adapter import verified,valid_body
from geometry_checks import check_boolean_result as checked

def front_gusset_scope(parameters):
    """Only five front gusset footprints; never infer scope from arbitrary mask solids."""
    width=parameters['RibWidth'];height=parameters['RibHeight'];deck=parameters['DeckZ']
    if any(type(v) not in (int,float) or not math.isfinite(v) for v in (width,height,deck)) or not 0<width<10 or not 0<height<30 or abs(deck-20.6)>1e-8:
        raise ValueError('Unsupported front gusset dimensions/datum')
    default=abs(width-1.8)<1e-8 and abs(height-6.)<1e-8
    # Exact validated default guards. Edited height follows the construction triangle's
    # ceiling-height footprint with 0.1 margin; edited width follows extrusion width.
    zmin=18. if default else deck-2.-height-.1
    zmax=18.7
    half=1.2 if default else width/2.+.3
    return [[x-half,-216.4,zmin,x+half,-216.0,zmax] for x in (35.,90.,139.7,190.,245.)],default

def g_invariant(c):
    paths=inputs(c,('upper_constructive','lower_grid','upper_g_overlap_mask'),('upper_g_checked','upper_g_report'))
    import FreeCAD as app
    import Part as part
    original=read(paths['upper_constructive'],part);valid_body(original)
    low=read(paths['lower_grid'],part);mask=read(paths['upper_g_overlap_mask'],part)
    if mask.isNull() or not mask.Solids or mask.Volume<=0 or not mask.isValid():raise ValueError('Invalid generated G mask')
    for sol in mask.Solids:checked(sol)
    full_mask_volume=mask.Volume
    guard_bounds,default_gussets=front_gusset_scope(c['parameters'])
    guards=[part.makeBox(*(b[i+3]-b[i] for i in range(3)),app.Vector(*b[:3])) for b in guard_bounds]
    union=part.makeCompound(guards)
    mask=mask.common(union);checked(mask)
    if not mask.Solids or mask.Volume<=0:raise ValueError('Empty front-only G correction mask')
    before_common=original.common(low);before_status=checked(before_common)
    s=original.cut(mask);s.check(False);discarded=[];discarded_shapes=[]
    if len(s.Solids)>1:
        keep=[]
        for sol in s.Solids:
            b=sol.BoundBox
            if accepted_g_fragment(sol.Volume,b):
                discarded_shapes.append(sol)
                discarded.append({'volume_mm3':sol.Volume,'bounds':[b.XMin,b.YMin,b.ZMin,b.XMax,b.YMax,b.ZMax]})
            else:keep.append(sol)
        if len(keep)!=1:raise ValueError('Unexpected disconnected G solids outside accepted discard rule')
        s=keep[0];s.check(False)
    valid_body(s)
    # Persist geometry before diagnostics; absence of the final report means unvalidated.
    candidate=Path(c['outputs']['upper_g_checked']).with_name('upper_g_candidate_unvalidated.brep')
    if candidate.exists():raise ValueError('Candidate output must be new')
    s.exportBrep(str(candidate))
    candidate_sha256=hashlib.sha256(candidate.read_bytes()).hexdigest()
    # One actual mask intersection identifies bounded changed regions, never a full-shape difference.
    selected=original.common(mask);checked(selected)
    if guards:
        union=part.makeCompound(guards)
        for q in [selected]+discarded_shapes:
            unguarded=q.cut(union);checked(unguarded)
            if abs(unguarded.Volume)>1e-7:raise ValueError('G correction extends outside declared changed-region guards')
    elif selected.Volume>1e-7 or discarded_shapes:raise ValueError('Missing changed-region guards')
    progress_path=Path(c['outputs']['upper_g_report']).with_name('upper_g_progress.json')
    progress_state={'candidate_sha256':candidate_sha256,'input_sha256':dict(c['input_hashes']),'release_ready':False}
    def progress(phase,**values):
        progress_state.update(phase=phase,**values)
        temporary=progress_path.with_suffix('.json.tmp')
        temporary.write_text(json.dumps(progress_state,indent=2,allow_nan=False)+'\n')
        temporary.replace(progress_path)
    progress('local_diagnostics_start')
    try:
        local_records=[];removed_volume=0.;added_volume=0.;outside_volume=0.
        for guard_index,(bounds,guard) in enumerate(zip(guard_bounds,guards)):
            progress('guard_start',guard_index=guard_index,bounds=bounds)
            before=original.common(guard);after=s.common(guard);checked(before);checked(after)
            progress('before_delta_booleans',guard_index=guard_index,bounds=bounds,before_mm3=before.Volume,after_mm3=after.Volume)
            added=after.cut(before);removed=before.cut(after);checked(added);checked(removed)
            progress('before_guard_assertions',guard_index=guard_index,removed_mm3=removed.Volume,added_mm3=added.Volume,removed_status=checked(removed),completed_guards=list(local_records))
            if abs(added.Volume)>1e-7:raise ValueError('G correction added material in local guard')
            added_volume+=added.Volume;removed_volume+=removed.Volume
            local_records.append({'bounds':bounds,'added_mm3':added.Volume,'removed_mm3':removed.Volume,'local_BOP':'PASS'})
        residual=abs(original.Volume-s.Volume-removed_volume);scale=max(abs(original.Volume),abs(s.Volume),abs(removed_volume))
        mass_limit=max(1e-5,1e-7*scale)
        progress('before_mass_assertion',residual_mm3=residual,limit_mm3=mass_limit,removed_mm3=removed_volume)
        if residual>mass_limit:raise ValueError('G correction mass identity')
        progress('before_final_lower_common')
        common=s.common(low);status=checked(common)
        if abs(common.Volume)>.0001:raise ValueError('Cold G overlap remains after accepted membrane correction')
        h=save(s,Path(c['outputs']['upper_g_checked']),part)
    except Exception as error:
        anomaly_files={}
        for label in ('before','after','removed'):
            shape=locals().get(label)
            if shape is not None:
                try:
                    path=progress_path.with_name('anomaly_'+label+'.brep')
                    shape.exportBrep(str(path));anomaly_files[label]=str(path)
                except Exception as export_error:anomaly_files[label]={'export_error':str(export_error)}
        progress('FAILED',failed_phase=progress_state.get('phase'),exception_type=type(error).__name__,exception=str(error),anomaly_files=anomaly_files)
        raise
    progress('stage_diagnostics_passed',local_records=local_records)
    r={'common_before_mm3':before_common.Volume,'common_before_check':before_status,'common_mm3':common.Volume,'common_check':status,
       'output_sha256':h,'candidate_unvalidated_path':str(candidate),'candidate_unvalidated_sha256':candidate_sha256,'input_sha256':dict(c['input_hashes']),'generated_mask_sha256':c['input_hashes']['upper_g_overlap_mask'],
       'repair_applied':True,'recipe':'fresh foundation mask intersected with five front gusset scopes BEFORE cut, then exact disconnected G fragment rule','full_generated_mask_volume_mm3':full_mask_volume,'applied_front_mask_volume_mm3':mask.Volume,'front_scope_bounds':guard_bounds,
       'discarded_new_gusset_slivers':discarded,'added_mm3':added_volume,'removed_mm3':removed_volume,
       'local_mask_checks':local_records,'outside_authorized_removal_mm3':None,'outside_allowed_diagnostic':{'status':'FAILED_DIAGNOSTIC_OCC_NULL_SHAPE','evidence_sha256':'95c3b394928da9764042238d4acb5b09730334b717d25467dbb8255eee5690cc','failed_adapter_sha256':'74a14d271752399f1a78fa17f1c39b4a658d63689656baacd9ef70600a0aa357','mandatory_path':False},'construction_status':'CONSTRUCTION_VALIDATED_FINAL_EQUIVALENCE_REQUIRED','final_equivalence_required':True,'required_final_reference_sha256':'533b115a99efbb3b79748faf302492cdd94914ed7f40ebedcf437878d223c2c1','global_delta_cuts':'NOT_RUN_BOUNDED_CHANGED_REGIONS','default_five_guards':default_gussets,
       'mass_identity':{'residual_mm3':residual,'relative_residual':residual/scale if scale else 0.,'limit_mm3':mass_limit},'release_ready':False}
    for key in ('upper_constructive','lower_grid','upper_g_overlap_mask'):verified(c,key)
    Path(c['outputs']['upper_g_report']).write_text(json.dumps(r,indent=2)+'\n');return r
