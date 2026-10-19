"""Read-only release gates; import is CAD-free. Explicit inputs, never live documents.

All successful measurements bind SHA256 of lower_final/upper_final and every
consumed artifact. No historic JSON PASS or checkpoint is accepted as proof.
Full final-body BOP is deliberately not run here; bounded intermediates receive
BOP. Missing proof is FAIL (Enter alone may be CONDITIONAL).
"""
import collections
import functools
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import sys

TOL = 1e-5
MASS_RELATIVE_TOL = 1e-7
def mass_tolerance(*volumes):
    return max(TOL,MASS_RELATIVE_TOL*max(abs(v) for v in volumes))
PCB = ((11.43,-11.43),(267.97,-11.43),(11.43,-91.44),(267.97,-91.44),(139.7,-110.49),(62.23,-204.47),(207.01,-204.47))
CASE = ((-1.8,-198.),(-1.8,-24.),(281.2,-198.),(281.2,-24.))


def require(ok, message):
    if not ok: raise ValueError(message)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def verified(context, name):
    require(name in context['inputs'], 'MISSING_INPUT:'+name)
    p = Path(context['inputs'][name])
    require(p.is_file() and not p.is_symlink(), 'INVALID_INPUT:'+name)
    require(sha(p) == context['input_hashes'][name], 'INPUT_HASH_MISMATCH:'+name)
    return p


def gate(fn):
    @functools.wraps(fn)
    def call(context):
        hashes = {}
        def bindings():
            return {'input_sha256':dict(hashes),
                    'final_shape_sha256':{n:hashes[n] for n in ('lower_final','upper_final') if n in hashes},
                    'final_global_bop':'NOT_RUN_RESOURCE_PRECAUTION'}
        try:
            require(context.get('cold_build') is True, 'COLD_CONTEXT_REQUIRED')
            for name in context['inputs']:
                verified(context, name)
                hashes[name] = context['input_hashes'][name]
            for name in ('lower_final','upper_final'): verified(context, name)
            result = fn(context)
            require(isinstance(result,dict) and result.get('status') in ('PASS','CONDITIONAL','FAIL'),'INVALID_HOOK_RESULT')
            existing=result.get('evidence',{})
            require(isinstance(existing,dict),'INVALID_HOOK_EVIDENCE')
            evidence={k:v for k,v in result.items() if k not in ('status','evidence')}
            for key,value in existing.items():
                require(key not in evidence or evidence[key]==value,'CONFLICTING_HOOK_EVIDENCE:'+key)
                evidence[key]=value
            for name in context['inputs']: verified(context, name)
            evidence.update(bindings())
            return {'status':result['status'],'evidence':evidence}
        except Exception as exc:
            evidence=bindings();evidence['blocking_requirement']=str(exc)
            return {'status':'FAIL','evidence':evidence}
    return call


def boolean_status(s):
    # Same exact-empty semantics as staging/geometry_checks.py.
    empty = not any(len(getattr(s,n)) for n in ('Solids','Shells','Wires','Faces','Edges','Vertexes'))
    require(all(math.isfinite(v) for v in (s.Volume,s.Area,s.Length)), 'NONFINITE_BOOLEAN')
    if empty:
        require(s.Volume == s.Area == s.Length == 0, 'EMPTY_WITH_MEASURE')
        if not s.isNull():
            s.check(False); require(s.isValid(), 'INVALID_EMPTY_TOPOLOGY')
        return 'NOT_APPLICABLE_EMPTY_TOPOLOGY'
    s.check(True); require(s.isValid(), 'INVALID_NONEMPTY_BOOLEAN')
    require(s.Volume >= -TOL, 'NEGATIVE_BOOLEAN_VOLUME')
    return 'PASS'


def shape(context, name, single=True):
    import Part
    s = Part.Shape(); s.read(str(verified(context,name)))
    s.check(False)
    require(not s.isNull() and s.isValid() and s.Volume > 0, 'INVALID_SOLID:'+name)
    require(len(s.Solids) == 1 if single else len(s.Solids)>0, 'SOLID_COUNT:'+name)
    return s


def box(bounds):
    import FreeCAD as A, Part
    return Part.makeBox(*(bounds[i+3]-bounds[i] for i in range(3)), A.Vector(*bounds[:3]))


def bounds(s):
    b=s.BoundBox
    return [b.XMin,b.YMin,b.ZMin,b.XMax,b.YMax,b.ZMax]


_DIAGNOSTIC_CONTEXT={}
def boolean_diagnostic(operation,a,b,result=None,**extra):
    record={**_DIAGNOSTIC_CONTEXT,'operation':operation,'a_volume':a.Volume,'b_volume':b.Volume,'a_bounds':bounds(a),'b_bounds':bounds(b),'tolerance':TOL,**extra}
    path=record.pop('diagnostic_path',None)
    if result is not None:record.update(result_volume=result.Volume,result_bounds=bounds(result),result_solids=len(result.Solids),result_faces=len(result.Faces),result_valid=bool(result.isValid()))
    if path:
        path=Path(path);path.parent.mkdir(parents=True,exist_ok=True);temporary=path.with_suffix('.json.tmp');temporary.write_text(json.dumps(record,indent=2)+'\n');temporary.replace(path)
    return record

def common(a,b):
    c=a.common(b); boolean_status(c)
    if not (-TOL <= c.Volume <= min(a.Volume,b.Volume)+mass_tolerance(a.Volume,b.Volume,c.Volume)):
        diagnostic=boolean_diagnostic('COMMON_VOLUME_INVARIANT',a,b,c)
        raise ValueError('COMMON_VOLUME_INVARIANT:'+json.dumps(diagnostic,sort_keys=True))
    return c


def clear(a,b):
    c=common(a,b); require(c.Volume<=TOL, 'COLLISION:%.12g'%c.Volume)
    return {'common_volume':c.Volume,'boolean_status':boolean_status(c)}


def compare(a,b):
    if not any(len(getattr(q,n)) for q in (a,b) for n in ('Solids','Shells','Wires','Faces','Edges','Vertexes')):
        return {'both_cuts':[0.,0.],'common':0.,'identity_residuals':[0.,0.],
                'topology':[boolean_status(a),boolean_status(b)]}
    c=common(a,b); ab=a.cut(b); ba=b.cut(a)
    statuses=[boolean_status(q) for q in (c,ab,ba)]
    residuals=[abs(a.Volume-c.Volume-ab.Volume),abs(b.Volume-c.Volume-ba.Volume)]
    mass_limit=mass_tolerance(a.Volume,b.Volume,c.Volume)
    if max(residuals)>mass_limit or ab.Volume+ba.Volume>TOL:
        boolean_diagnostic('COMPARE_INVARIANTS',a,b,c,both_cuts=[ab.Volume,ba.Volume],identity_residuals=residuals,topology=statuses)
    require(max(residuals)<=mass_limit, 'BOOLEAN_IDENTITY_INCONSISTENT')
    require(ab.Volume+ba.Volume<=TOL, 'GEOMETRY_DIFFERENCE')
    return {'both_cuts':[ab.Volume,ba.Volume],'common':c.Volume,'identity_residuals':residuals,'mass_tolerance':mass_limit,'relative_identity_residuals':[v/max(abs(a.Volume),abs(b.Volume),1e-30) for v in residuals],'difference_tolerance':TOL,'topology':statuses}


def tiles(a,b, size=40.):
    aa,bb=bounds(a),bounds(b)
    lo=[min(aa[i],bb[i])-.01 for i in range(3)]
    hi=[max(aa[i+3],bb[i+3])+.01 for i in range(3)]
    counts=[math.ceil((hi[i]-lo[i])/size) for i in range(3)]
    require(math.prod(counts)<=10000,'EXCESSIVE_AUDIT_EXTENT')
    for x in range(counts[0]):
        for y in range(counts[1]):
            for z in range(counts[2]):
                v=[lo[i]+n*size for i,n in enumerate((x,y,z))]
                yield box(v+[min(v[i]+size,hi[i]) for i in range(3)])


def tiled_compare(a,b):
    rows=[]
    for index,tile in enumerate(tiles(a,b)):
        _DIAGNOSTIC_CONTEXT.update(tile_index=index,tile_bounds=bounds(tile))
        rows.append(compare(common(a,tile),common(b,tile)))
    limit=mass_tolerance(a.Volume,b.Volume);residual=abs(a.Volume-b.Volume)
    if residual>limit:boolean_diagnostic('TOTAL_VOLUME_DIFFERENCE',a,b,mass_tolerance=limit)
    require(residual<=limit,'TOTAL_VOLUME_DIFFERENCE')
    rows.append({'total_mass_residual':residual,'mass_tolerance':limit,'relative_residual':residual/max(abs(a.Volume),abs(b.Volume),1e-30),'difference_tolerance':TOL})
    return rows


@gate
def geometry_equivalence(c):
    rows={}
    root=Path(c['output_root']);_DIAGNOSTIC_CONTEXT.clear();_DIAGNOSTIC_CONTEXT.update(diagnostic_path=str(root.with_name(root.name+'_check_diagnostics')/'geometry_equivalence.json'),input_sha256=dict(c['input_hashes']))
    for role in ('lower','upper'):
        final=shape(c,role+'_final')
        _DIAGNOSTIC_CONTEXT.update(comparison='baseline_'+role,role=role)
        # Equal SHA of the verified complete BREP files proves identical bytes;
        # this is not a claim that a Boolean operation or global BOP was run.
        baseline_role='baseline_'+role;final_role=role+'_final'
        if c['input_hashes'][final_role]==c['input_hashes'][baseline_role]:
            verified(c,final_role);verified(c,baseline_role)
            rows[baseline_role]={'method':'EXACT_BYTE_IDENTITY_SHA256','sha256':c['input_hashes'][final_role],
                                 'ordinary_final_shape_validated':True,'boolean_operations':'NOT_APPLICABLE_IDENTICAL_BYTES'}
        else:
            rows[baseline_role]=tiled_compare(final,shape(c,baseline_role))
        # STEP reimport uses Part.Shape.read, independently of export process.
        _DIAGNOSTIC_CONTEXT.update(comparison=role+'_step',role=role)
        rows[role+'_step']=tiled_compare(final,shape(c,role+'_step'))
    return {'status':'PASS','comparisons':rows,'scope':'Baseline exact-byte SHA identity when equal, otherwise tiled both-cuts/common volume equivalence; STEP always independently reimported and compared; not a surface Hausdorff certificate'}


@gate
def functional_holes(c):
    import FreeCAD as A, Part
    p=c['parameters']; low=shape(c,'lower_final'); upper=shape(c,'upper_final');rows=[]
    expected={'PCBBottomZ':13.,'PCBThickness':1.6,'CaseSeatZ':16.2,'HeadSeatZ':3.2,'PilotDiameter':4.,'ScrewLength':20.,'CaseThroughDiameter':3.4,'HeadPocketDiameter':6.6}
    require(all(k in p and abs(float(p[k])-v)<1e-8 for k,v in expected.items()), 'FUNCTIONAL_PROBES_REQUIRE_APPROVED_DIMENSIONS')
    for role,s,axes,r,z,h in [('pcb_lower',low,PCB,1.99,6.31,6.69),('case_through',low,CASE,1.69,.01,16.18),('case_head',low,CASE,3.29,.01,3.18),('pcb_head',upper,PCB,2.75,14.6,3.),('case_pilot',upper,CASE,1.999,16.2,7.),('case_shaft',upper,CASE,1.5,3.2,20.)]:
        for i,(x,y) in enumerate(axes):
            probe=Part.makeCylinder(r,h,A.Vector(x,y,z))
            local=common(s,box([x-5.1,y-5.1,z-.01,x+5.1,y+5.1,z+h+.01]))
            rows.append(dict(clear(local,probe),role=role,index=i,axis=[x,y],radius=r,z_range=[z,z+h]))
    for i,(x,y) in enumerate(PCB):
        ring=Part.makeCylinder(4,.05,A.Vector(x,y,14.6)).cut(Part.makeCylinder(3.1,.05,A.Vector(x,y,14.6)))
        require(common(upper,ring).Volume>1e-4,'MISSING_PCB_ANNULAR_FOOT:'+str(i))
    return {'status':'PASS','probes':rows,'scope':'Approved nominal cavity probes and retained PCB contact bands; not screw tolerance or strength certification'}


@gate
def assembly_clearance(c):
    import FreeCAD as A
    low=shape(c,'lower_final');up=shape(c,'upper_final');pcb=shape(c,'pcb_placed')
    import Part
    rear=Part.Shape();rear.read(str(verified(c,'rear_electronics_placed')))
    require(not rear.isNull() and rear.Solids,'EMPTY_ELECTRONICS_REFERENCE')
    proof=json.loads(verified(c,'electronics_placement_provenance').read_text())
    require(proof.get('producer')=='placed_electronics_v1' and set(proof['rear_references'])=={'J1','J2','J4','J5','J6','U25','SW68'},'ELECTRONICS_REFERENCE_COVERAGE_REQUIRED')
    require(proof['source_sha256']==c['input_hashes']['electronics'],'ELECTRONICS_SOURCE_BINDING')
    require(all(proof['output_sha256'][n]==c['input_hashes'][n] for n in ('pcb_placed','rear_electronics_placed')),'ELECTRONICS_PLACEMENT_BINDING')
    require(all(abs(a-b)<1e-4 for a,b in zip(bounds(pcb),[6.35,-209.55,13.,273.05,-6.35,14.6])), 'PCB_PLACEMENT_MISMATCH')
    rows=[clear(common(low,t),common(up,t)) for t in tiles(low,up)]
    rows.extend([clear(low,pcb),clear(up,pcb)])
    bottom=[f for f in pcb.Faces if f.BoundBox.ZLength<1e-6 and abs(f.BoundBox.ZMin-13)<1e-5]
    require(bottom,'MISSING_REAL_PCB_BOTTOM_FACES')
    for f in bottom:
        sweep=f.extrude(A.Vector(0,0,30))
        if sweep.Volume<0:sweep.reverse()
        boolean_status(sweep);rows.append(clear(low,sweep))
    observations=proof.get('rear_solids',[])
    require(len(observations)==len(rear.Solids),'REFERENCE_LEAF_COVERAGE_REQUIRED')
    for fixed in (low,up):
        for index,component in enumerate(rear.Solids):
            observed=observations[index];b=bounds(component)
            require(observed['index']==index and all(abs(a-z)<1e-6 for a,z in zip(b,observed['bounds'])),'REFERENCE_LEAF_BINDING')
            window=box([v-.001 for v in b[:3]]+[v+.001 for v in b[3:]])
            crop=common(fixed,window)
            if observed['allowed_use']=='EXACT_BOOLEAN':
                boolean_status(component);rows.append(clear(crop,component))
            else:
                require(observed['allowed_use']=='CONSERVATIVE_BBOX_ONLY','UNKNOWN_REFERENCE_POLICY')
                require(boolean_status(crop)=='NOT_APPLICABLE_EMPTY_TOPOLOGY','INVALID_REFERENCE_BBOX_NOT_CLEAR')
                rows.append({'reference_index':index,'status':'PASS_CONSERVATIVE_BBOX','source_BOP':observed['BOP'],'source_error':observed['error']})
    return {'status':'PASS','checks':rows,'scope':'Closed shells; actual PCB static and continuous +Z 30 mm removal with upper removed; rear electronics STATIC only'}


def pinned_module(c, role, name):
    spec=importlib.util.spec_from_file_location(name,verified(c,role));m=importlib.util.module_from_spec(spec)
    sys.modules[name]=m
    try:spec.loader.exec_module(m)
    except Exception:
        sys.modules.pop(name,None);raise
    return m


@gate
def ventilation_corridors_and_areas(c):
    from dataclasses import fields
    names=('v10_parameters','ventilation_v10');old={n:sys.modules.get(n) for n in names}
    try:
        pm=pinned_module(c,'parameters_source',names[0]);vm=pinned_module(c,'ventilation_source',names[1])
        data=c['parameters'];p=pm.Parameters(**{f.name:data[f.name] for f in fields(pm.Parameters)}).validate()
        low=shape(c,'lower_final');up=shape(c,'upper_final');rows=[];areas={}
        for group,generated,layout in [('side',vm.side_cutters,vm.side_layout),('top',vm.top_cutters,vm.top_layout)]:
            ext=float(data['Ventilation'+group.title()+'InwardExtension'])
            require(math.isfinite(ext) and ext>=0,'INVALID_CORRIDOR_EXTENSION')
            actual=shape(c,group+'_cutters',False);canonical=generated(p,ext);slots,_=layout(p)
            require(len(actual.Solids)==len(canonical)==len(slots)>0,'CUTTER_COUNT_MISMATCH')
            for i,(a,b) in enumerate(zip(actual.Solids,canonical)):
                compare(a,b)
                rows.append({'group':group,'index':i,'lower':clear(low,a),'upper':clear(up,a)})
            mouth=p.SideSlotExternalWidth*p.SideSlotHeight if group=='side' else p.TopSlotExternalWidth*p.TopSlotLength
            angle=p.SideSlotAngle if group=='side' else p.TopSlotAngle
            areas[group]={'count':len(slots),'single_mouth_mm2':mouth,'total_mouth_mm2':mouth*len(slots),'normal_flow_section_mm2':mouth*len(slots)*math.sin(math.radians(angle))}
        return {'status':'PASS','corridors':rows,'areas':areas,'scope':'Canonical actual cutters clear through final bodies; geometric open area, not thermal/airflow certification'}
    finally:
        for name,value in old.items():
            if value is None:sys.modules.pop(name,None)
            else:sys.modules[name]=value


def rotational_certificate(moving,fixed,axis,start,end,sign=1,step=.4):
    import FreeCAD as A
    b=moving.BoundBox;radius=max(math.hypot(y-axis[1],z-axis[2]) for y in (b.YMin,b.YMax) for z in (b.ZMin,b.ZMax))
    n=math.ceil((end-start)/step);width=(end-start)/n;worst=float('inf')
    require(n>0,'EMPTY_ROTATION_DOMAIN')
    for i in range(n):
        angle=start+(i+.5)*width;s=moving.copy();s.rotate(A.Vector(*axis),A.Vector(1,0,0),sign*angle)
        distance=s.distToShape(fixed)[0]
        bound=distance-2*radius*math.sin(math.radians(width)/4)
        require(math.isfinite(bound) and bound>1e-6,'UNRESOLVED_CONTINUOUS_INTERVAL:%.6f..%.6f'%(start+i*width,start+(i+1)*width))
        worst=min(worst,bound)
    return {'domain_deg':[start,end],'intervals':n,'radius_bound':radius,'minimum_clearance_bound':worst}


def prescribed_j6_press(released):
    """Explicit ruled-section prescription from j6_press_board_check.py.

    Parameter delta translates each beam material point only in Z by
    -delta*f(s), with 0<=f<=1; therefore Hausdorff speed <=1 mm/mm.
    Hook has exactly the same speed bound. No material constitutive claim.
    Endpoint equivalence to accepted bodies is mandatory, not assumed.
    """
    import FreeCAD as A, Part
    cx=148.59;length=14.;root_y=-13.55
    hook=common(released,box([cx-4,-29.56,33.,cx+4,-27.45,38.]))
    require(hook.Volume>0,'J6_MISSING_PRESCRIBED_HOOK')
    beam_domain=box([cx-4,-27.551,34.3,cx+4,-13.55,38.3])
    fixed=released.cut(beam_domain).cut(hook);boolean_status(fixed)
    # The first 1 mm is the declared bonded root (not a shell exclusion).
    root_domain=box([cx-4,-14.55,34.3,cx+4,-13.54,38.3])
    fixed_away=fixed.cut(root_domain);boolean_status(fixed_away)
    def state(delta):
        require(0<=delta<=1.2,'J6_DEFLECTION_OUTSIDE_PRESCRIPTION')
        wires=[]
        for i in range(29):
            x=length*i/28.;dz=delta*x*x*(3*length-x)/(2*length**3);y=root_y-x
            pts=[A.Vector(cx-4,y,36.3-dz),A.Vector(cx+4,y,36.3-dz),A.Vector(cx+4,y,37.5-dz),A.Vector(cx-4,y,37.5-dz)]
            wires.append(Part.makePolygon(pts+[pts[0]]))
        beam=Part.makeLoft(wires,True,True);claw=hook.copy();claw.translate(A.Vector(0,0,-delta))
        moving=beam.fuse(claw);boolean_status(moving)
        full=fixed.fuse(moving);boolean_status(full)
        return full,moving
    return state,fixed_away,root_domain


def j6_press_certificate(released,pressed,obstacles):
    import FreeCAD as A
    state,fixed_away,root=prescribed_j6_press(released)
    # A ruled surrogate is not accepted merely because a historical report
    # passed. It must reproduce both actual accepted motion endpoint bodies.
    try:
        endpoint_zero=tiled_compare(state(0.)[0],released)
        endpoint_pressed=tiled_compare(state(1.2)[0],pressed)
    except Exception as exc:
        raise ValueError('J6_PRESCRIBED_DEFLECTION_ENDPOINT_EQUIVALENCE_REQUIRED: '+str(exc))
    rows=[]
    for angle in (0.,5.):
        worst=float('inf');self_worst=float('inf');root_overlap=[]
        for i in range(12):
            delta=(i+.5)*.1;full,moving=state(delta)
            # Midpoint to all points in a delta interval is at most .05 mm.
            # The extra .01 mm is a conservative numerical allowance, not
            # permission for an unmatched endpoint or changed rigid body.
            self_bound=moving.distToShape(fixed_away)[0]-.06
            require(math.isfinite(self_bound) and self_bound>1e-6,'J6_SELF_CLEARANCE_OUTSIDE_BONDED_ROOT_UNPROVEN')
            self_worst=min(self_worst,self_bound)
            root_overlap.append(common(moving,root).Volume)
            full.rotate(A.Vector(0,-4.45,16.25),A.Vector(1,0,0),-angle)
            for obstacle in obstacles:
                bound=full.distToShape(obstacle)[0]-.06
                require(math.isfinite(bound) and bound>1e-6,'J6_PRESS_INTERVAL_UNRESOLVED:angle=%g,delta=%g'%(angle,delta))
                worst=min(worst,bound)
        rows.append({'angle_deg':angle,'delta_domain_mm':[0.,1.2],'interval_count':12,
                     'minimum_clearance_bound_mm':worst,'self_clearance_outside_bonded_root_mm':self_worst,
                     'declared_bonded_root_bounds':bounds(root),'midpoint_moving_root_volume_mm3':root_overlap})
    return {'endpoints':{'unpressed':endpoint_zero,'pressed':endpoint_pressed},'continuous_intervals':rows}


def j6_nominal_engagement(released,pressed,lower,upper,connector):
    import FreeCAD as A
    cx=148.59
    catch=box([cx-4.3,-29.85,36.5,cx+4.3,-28.25,37.5])
    core=box([cx-4.1,-29.65,36.7,cx+4.1,-28.45,37.3])
    missing=core.cut(upper);boolean_status(missing)
    require(missing.Volume<=TOL,'J6_FINAL_CATCH_CORE_MISSING')
    nominal=[clear(released,x) for x in (lower,upper,connector)]
    # Attempted opening without pressing must meet the nominal retention lip.
    # This is a geometric engagement witness, not an allowed opening path.
    attempted=released.copy();attempted.rotate(A.Vector(0,-4.45,16.25),A.Vector(1,0,0),-3.)
    engagement=common(attempted,core)
    require(engagement.Volume>1e-4,'J6_NO_NOMINAL_RETENTION_ENGAGEMENT')
    contact=common(attempted,upper);outside=contact.cut(catch);boolean_status(outside)
    require(outside.Volume<=TOL,'J6_RETENTION_COLLISION_OUTSIDE_DECLARED_CATCH')
    clear(attempted,lower);clear(attempted,connector)
    pressed_attempt=pressed.copy();pressed_attempt.rotate(A.Vector(0,-4.45,16.25),A.Vector(1,0,0),-3.)
    released_path=[clear(pressed_attempt,x) for x in (lower,upper,connector)]
    return {'nominal_closed':nominal,'retention_witness_angle_deg':3.,'catch_bounds':bounds(catch),
            'catch_core_bounds':bounds(core),'eroded_core_overlap_mm3':engagement.Volume,
            'intended_catch_contact_mm3':contact.Volume,'outside_catch_overlap_mm3':outside.Volume,
            'pressed_at_witness':released_path}


@gate
def j6_continuous_motion(c):
    low=shape(c,'lower_final');up=shape(c,'upper_final');pressed=shape(c,'j6_pressed');released=shape(c,'j6_released');connector=shape(c,'j6_connector',False)
    proof=json.loads(verified(c,'j6_extraction_provenance').read_text())
    require(proof.get('producer')=='accepted_j6_extraction_v1' and proof['source_sha256']==c['input_hashes']['j6_accepted'],'J6_SOURCE_PROVENANCE_MISMATCH')
    for role,name in {'j6_pressed':'HatchPressed','j6_released':'Hatch','j6_connector':'Connector'}.items():
        require(proof['outputs'][role]['object']==name and proof['outputs'][role]['sha256']==c['input_hashes'][role],'J6_EXTRACTED_BODY_BINDING')
    rows=[]
    for moving,start,end in ((pressed,0.,5.),(released,5.,120.)):
        for fixed in (low,up,connector):rows.append(rotational_certificate(moving,fixed,(0.,-4.45,16.25),start,end,-1))
    press=j6_press_certificate(released,pressed,(low,up,connector))
    engagement=j6_nominal_engagement(released,pressed,low,up,connector)
    return {'status':'PASS','rigid_intervals':rows,'prescribed_press':press,'nominal_engagement':engagement,
            'evidence':{'physical_status':'UNVERIFIED_PHYSICAL_TEST_REQUIRED',
                        'limitations':['Prescribed geometric deflection only; PCTG elasticity, fatigue, required force, and practical tool access require physical testing.',
                                       'J6 operating motion proof covers press at 0 degrees, pressed rotation 0–5 degrees, release at 5 degrees, and released rotation 5–120 degrees; hinge-ear insertion is a separate assembly operation.']}}


@gate
def feet_continuous_motion(c):
    # Explicitly avoid converting the historic core-only or excluded-seat audit
    # into a full-feet certificate. Full joints include intended contact.
    return {'status':'FAIL','blocking_requirement':'FULL_FEET_0_TO_105_CONTINUOUS_PROOF_INCLUDING_SEATS_DETENTS_AND_OTHER_FOOT_BOUND_TO_FINAL_SHAPES',
            'required_axes':[[40.,-35.,2.5],[239.4,-35.,2.5]],'rejected_substitutes':['core-only sweep','excluded seat regions','discrete endpoint checks','snapshot report']}


@gate
def enter_motion_status(c):
    return {'status':'CONDITIONAL','blocking_requirement':'ACTUAL_ENTER_KEY_AND_STABILIZER_CONTINUOUS_TRAVEL_PROOF_BOUND_TO_UPPER_FINAL',
            'release_ready':False,'scope':'No motion clearance claim; support geometry alone is insufficient'}


@gate
def reopen_and_cold_rebuild(c):
    return {'status':'FAIL','blocking_requirement':'INDEPENDENT_SECOND_COLD_BUILD_AND_FCSTD_CLOSE_REOPEN_RECOMPUTE_EQUIVALENCE_BOUND_TO_FINAL_SHAPES',
            'rejected_substitutes':['cold_build boolean','same-session snapshots','historic reopen report','matching BREP byte hashes without independent run provenance']}


def mesh_topology(mesh,independent_intersection_proof=None):
    points,facets=mesh.Topology
    require(len(facets)>0,'EMPTY_MESH')
    xyz=[tuple(float(v) for v in p) for p in points]
    require(all(math.isfinite(v) for p in xyz for v in p),'NONFINITE_MESH')
    # Weld exact STL positions regardless of importer vertex indexing.
    ids={p:i for i,p in enumerate(sorted(set(xyz)))}
    faces=[tuple(ids[xyz[int(i)]] for i in face) for face in facets]
    vertices={i:p for p,i in ids.items()};edges=collections.defaultdict(list);volume=0.;adj=collections.defaultdict(set)
    require(len({tuple(sorted(f)) for f in faces})==len(faces),'DUPLICATE_TRIANGLES')
    for index,f in enumerate(faces):
        require(len(f)==3 and len(set(f))==3,'DEGENERATE_TRIANGLE')
        a,b,d=[vertices[i] for i in f];u=[b[i]-a[i] for i in range(3)];v=[d[i]-a[i] for i in range(3)]
        cross=[u[1]*v[2]-u[2]*v[1],u[2]*v[0]-u[0]*v[2],u[0]*v[1]-u[1]*v[0]]
        require(sum(x*x for x in cross)>1e-20,'ZERO_AREA_TRIANGLE')
        volume+=(a[0]*(b[1]*d[2]-b[2]*d[1])+a[1]*(b[2]*d[0]-b[0]*d[2])+a[2]*(b[0]*d[1]-b[1]*d[0]))/6
        for x,y in zip(f,f[1:]+f[:1]):edges[tuple(sorted((x,y)))].append((index,x<y))
    for incident in edges.values():
        require(len(incident)==2,'NONMANIFOLD_EDGE')
        (a,da),(b,db)=incident;require(da!=db,'WINDING_CONFLICT');adj[a].add(b);adj[b].add(a)
    seen=set();pending=[0]
    while pending:
        k=pending.pop()
        if k not in seen:seen.add(k);pending.extend(adj[k]-seen)
    require(len(seen)==len(faces),'DISCONNECTED_MESH')
    # Every welded vertex must have one cyclic link, not multiple pinched fans.
    links=collections.defaultdict(lambda:collections.defaultdict(set))
    for f in faces:
        for i,v in enumerate(f):
            a,b=f[(i+1)%3],f[(i+2)%3];links[v][a].add(b);links[v][b].add(a)
    for link in links.values():
        require(all(len(adjacent)==2 for adjacent in link.values()),'NONMANIFOLD_VERTEX_LINK')
        visited=set();queue=[next(iter(link))]
        while queue:
            v=queue.pop()
            if v not in visited:visited.add(v);queue.extend(link[v]-visited)
        require(len(visited)==len(link),'PINCHED_VERTEX')
    require(volume>0,'NONPOSITIVE_SIGNED_MESH_VOLUME')
    if independent_intersection_proof is None:
        require(not mesh.getSelfIntersections(),'MESH_SELF_INTERSECTIONS')
    else:
        require(independent_intersection_proof.get('status')=='PASS_REUSED_EXACT_BYTE_PROOFS','UNVERIFIED_INTERSECTION_REUSE')
        require(independent_intersection_proof['independent_full_intersections']['intersections']==[],'REUSED_INTERSECTIONS_NOT_EMPTY')
    return {'triangles':len(faces),'vertices':len(vertices),'signed_volume':volume,'connected_components':1,'nonmanifold_edges':0,'winding_conflicts':0,'self_intersections':0}


def delivered_small_part_shape(c,source_role):
    if source_role!='j6_accepted':return shape(c,source_role)
    import FreeCAD as App
    path=verified(c,source_role)
    require(not App.listDocuments(),'HATCH_AUDIT_REQUIRES_CLOSED_DOCUMENTS')
    doc=App.openDocument(str(path))
    try:
        obj=doc.getObject('Hatch')
        require(obj is not None and hasattr(obj,'Shape'),'ACCEPTED_HATCH_OBJECT_MISSING')
        require(not any(p.TypeId=='App::Part' for p in obj.InList),'UNEXPECTED_HATCH_ASSEMBLY_ANCESTRY')
        s=obj.Shape.copy();s.check(False)
        require(not s.isNull() and s.isValid() and len(s.Solids)==1 and math.isfinite(s.Volume) and s.Volume>0,'INVALID_ACCEPTED_HATCH')
        return s
    finally:App.closeDocument(doc.Name)


@gate
def exported_mesh_audit(c):
    import Mesh
    rows={};mesh_results_by_sha={}
    reuse_config=(c.get('runtime') or {}).get('canonical_mesh_reuse')
    reuse_helper=None
    if reuse_config is not None:
        path=verified(c,'canonical_mesh_reuse_source')
        spec=importlib.util.spec_from_file_location('verified_mesh_reuse_gate',path);reuse_helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(reuse_helper)
    provenance=json.loads(verified(c,'mesh_export_provenance').read_text())
    actual_provenance=json.loads(verified(c,'export_provenance').read_text())
    require(provenance.get('producer') in ('release_mesh_export_v1','canonical_netgen_mesh_copy_v2'),'MISSING_REVIEWED_MESH_EXPORT_PROVENANCE')
    require(actual_provenance.get('status')=='EXPORTED_REOPENED_CAD_RELEASE_NOT_PROVEN','MISSING_DOCUMENT_EXPORT_PROVENANCE')
    for role in ('lower','upper'):
        final=shape(c,role+'_final');record=provenance['outputs'][role]
        require(record['source_sha256']==c['input_hashes'][role+'_final'],'STALE_AUDIT_MESH_SOURCE')
        require(actual_provenance['input_sha256'][role+'_final']==c['input_hashes'][role+'_final'],'STALE_EXPORTED_MESH_SOURCE')
        for artifact in ('audit_'+role+'_stl',role+'_stl'):
            stl=verified(c,artifact)
            expected=record['stl_sha256'] if artifact.startswith('audit_') else actual_provenance['outputs'][artifact]['sha256']
            require(expected==sha(stl),'STALE_MESH_PROVENANCE:'+artifact)
            digest=sha(stl)
            cached_proof=None
            if role=='upper' and reuse_helper is not None:
                cached_proof=reuse_helper.verified_audit_reuse(reuse_config,source_brep_sha256=c['input_hashes']['upper_final'],current_stl_path=stl)
            if digest in mesh_results_by_sha:
                r,bb=mesh_results_by_sha[digest]
            else:
                mesh=Mesh.Mesh(str(stl));r=mesh_topology(mesh,independent_intersection_proof=cached_proof)
                mb=mesh.BoundBox;bb=[mb.XMin,mb.YMin,mb.ZMin,mb.XMax,mb.YMax,mb.ZMax]
                if cached_proof is not None:
                    r=dict(r,intersection_proof_reuse=cached_proof,topology_and_vertex_links='RECOMPUTED_THIS_RUN',self_intersections_method='VERIFIED_FULL_INDEPENDENT_AUDIT_OF_EXACT_STL_BYTES')
                mesh_results_by_sha[digest]=(r,bb)
                del mesh
            require(max(abs(a-b) for a,b in zip(bb,bounds(final)))<=.1,'MESH_ENVELOPE_MISMATCH:'+artifact)
            require(abs(r['signed_volume']-final.Volume)<=max(1.,final.Volume*.001),'MESH_VOLUME_MISMATCH:'+artifact)
            rows[artifact]=r
    # All five delivered print parts are mandatory. Pads remain reference-only.
    for artifact,source_role in (('hatch_stl','j6_accepted'),('left_foot_stl','foot_left'),('right_foot_stl','foot_right')):
        final=delivered_small_part_shape(c,source_role);stl=verified(c,artifact)
        require(actual_provenance['input_sha256'][source_role]==c['input_hashes'][source_role],'STALE_SMALL_PART_SOURCE:'+artifact)
        digest=sha(stl)
        require(actual_provenance['outputs'][artifact]['sha256']==digest,'STALE_SMALL_PART_STL:'+artifact)
        if digest in mesh_results_by_sha:
            r,bb=mesh_results_by_sha[digest]
        else:
            mesh=Mesh.Mesh(str(stl))
            try:r=mesh_topology(mesh)
            except Exception as exc:raise ValueError(artifact+': '+str(exc)) from exc
            mb=mesh.BoundBox;bb=[mb.XMin,mb.YMin,mb.ZMin,mb.XMax,mb.YMax,mb.ZMax]
            mesh_results_by_sha[digest]=(r,bb)
            del mesh
        require(max(abs(a-b) for a,b in zip(bb,bounds(final)))<=.1,'MESH_ENVELOPE_MISMATCH:'+artifact)
        require(abs(r['signed_volume']-final.Volume)<=max(1.,final.Volume*.001),'MESH_VOLUME_MISMATCH:'+artifact)
        rows[artifact]=dict(r,source_role=source_role,source_sha256=c['input_hashes'][source_role],stl_sha256=digest)
    return {'status':'PASS','meshes':rows,'delivered_print_parts':['lower_stl','upper_stl','hatch_stl','left_foot_stl','right_foot_stl'],
            'scope':'All five delivered print-part STLs plus canonical lower/upper audit copies: welded topology, vertex links, edge/winding/connectivity/self-intersection checks and source/STL SHA provenance; no pad-reference print claim'}
