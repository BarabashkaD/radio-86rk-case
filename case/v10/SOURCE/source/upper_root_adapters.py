"""Constructive/rounded upper roots and locked-network source rebuild of50 roots."""
import gc
import importlib.util
import json
import math
from pathlib import Path
from keyboard_stage_adapter import verified,digest,valid_body
from geometry_checks import check_boolean_result as checked

def read(path,part):s=part.Shape();s.read(str(path));return s

def inputs(c,names,outputs):
    if c.get('cold_build') is not True or set(c['outputs'])!=set(outputs):raise ValueError('Explicit cold outputs required')
    if any(Path(p).exists() for p in c['outputs'].values()):raise ValueError('Outputs must be new')
    return {k:verified(c,k) for k in names}

def save(s,path,part):
    valid_body(s);s.exportBrep(str(path));q=read(path,part);valid_body(q)
    for d in (s.cut(q),q.cut(s)):
        checked(d)
        if abs(d.Volume)>.001:raise ValueError('Saved roots differ')
    return digest(path)

def constructive(c):
    paths=inputs(c,('upper_chip_grid','chip_masks','lower_grid'),('upper_constructive','upper_constructive_report'))
    import FreeCAD as app
    import Part as part
    V=app.Vector;s=read(paths['upper_chip_grid'],part);mask=read(paths['chip_masks'],part);low=read(paths['lower_grid'],part);shift=low.copy();shift.translate(V(0,0,.3));rr=float(c['parameters']['UpperWallRootRadius']);records=[]
    if not 0<rr<5:raise ValueError('Unsupported wall root radius')
    for i,(p,n,dv) in enumerate([(V(-7.5,-73.9,34.7),V(1,0,0),V(0,65.85,0)),(V(286.9,-73.9,34.7),V(-1,0,0),V(0,65.85,0)),(V(-5.3,-5.85,34.7),V(0,-1,0),V(290,0,0))]):
        a=p-n*.05+V(0,0,.05);b=p+n*rr+V(0,0,.05);cc=p+n*rr;d=p+V(0,0,-rr);e=d-n*.05
        arc=part.Arc(cc,p+n*(rr-rr/math.sqrt(2))+V(0,0,-rr+rr/math.sqrt(2)),d).toShape()
        q=part.Face(part.Wire([part.makeLine(a,b),part.makeLine(b,cc),arc,part.makeLine(d,e),part.makeLine(e,a)])).extrude(dv)
        if q.Volume<0:q.reverse()
        q=q.cut(mask).cut(shift);kept=[t for t in q.Solids if t.Volume>1 and t.common(s).Volume>1e-6]
        if not kept:records.append({'root':i,'status':'NO_CONNECTED_MATERIAL'});continue
        q=part.makeCompound(kept);candidate=s.fuse(q,.00001);checked(candidate);valid_body(candidate)
        if candidate.Volume<s.Volume-.001:raise ValueError('Constructive root lost material')
        s=candidate;records.append({'root':i,'status':'PASS','volume':q.Volume})
    h=save(s,Path(c['outputs']['upper_constructive']),part);report={'radius':rr,'records':records,'output_sha256':h,'input_sha256':dict(c['input_hashes']),'release_ready':False}
    Path(c['outputs']['upper_constructive_report']).write_text(json.dumps(report,indent=2)+'\n');return report

def accepted_g_fragment(volume,b):
    # Exact accepted rule; do not expand thresholds to fit an unexpected fragment.
    return volume<.01 and -216.28<b.YMin<b.YMax<-216.24 and 18.2<b.ZMin<b.ZMax<18.4

def g_invariant(c):
    paths=inputs(c,('upper_constructive','lower_grid','upper_g_overlap_mask'),('upper_g_checked','upper_g_report'))
    import FreeCAD as app
    import Part as part
    original=read(paths['upper_constructive'],part);valid_body(original)
    low=read(paths['lower_grid'],part);mask=read(paths['upper_g_overlap_mask'],part)
    if mask.isNull() or not mask.Solids or mask.Volume<=0 or not mask.isValid():raise ValueError('Invalid generated G mask')
    for sol in mask.Solids:checked(sol)
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
    # One actual mask intersection identifies bounded changed regions, never a full-shape difference.
    selected=original.common(mask);checked(selected)
    allowed=part.makeCompound([mask]+discarded_shapes)
    default_gussets=all(abs(float(c['parameters'][k])-v)<1e-8 for k,v in
                       [('RibWidth',1.8),('RibHeight',6.),('UpperGussetEdgeRadius',.5),('UpperPerimeterRadius',2.)])
    if default_gussets:
        guard_bounds=[[x-1.2,-216.4,18.,x+1.2,-216.0,18.7] for x in (35.,90.,139.7,190.,245.)]
    else:
        # Edited supported dimensions get regions from actual changed solids, not default coordinates.
        guard_bounds=[]
        for sol in list(selected.Solids)+discarded_shapes:
            b=sol.BoundBox;guard_bounds.append([b.XMin-.01,b.YMin-.01,b.ZMin-.01,b.XMax+.01,b.YMax+.01,b.ZMax+.01])
        # Merge intersecting bounds so measured removal volumes are never double counted.
        changed=True
        while changed:
            changed=False
            for i in range(len(guard_bounds)):
                for j in range(i+1,len(guard_bounds)):
                    a,b=guard_bounds[i],guard_bounds[j]
                    if all(a[k]<=b[k+3] and b[k]<=a[k+3] for k in range(3)):
                        guard_bounds[i]=[min(a[k],b[k]) for k in range(3)]+[max(a[k+3],b[k+3]) for k in range(3)]
                        guard_bounds.pop(j);changed=True;break
                if changed:break
        if len(guard_bounds)>81:raise ValueError('G correction exceeds bounded local region budget; explicit review required')
    guards=[part.makeBox(*(b[i+3]-b[i] for i in range(3)),app.Vector(*b[:3])) for b in guard_bounds]
    if guards:
        union=part.makeCompound(guards)
        for q in [selected]+discarded_shapes:
            unguarded=q.cut(union);checked(unguarded)
            if abs(unguarded.Volume)>1e-7:raise ValueError('G correction extends outside declared changed-region guards')
    elif selected.Volume>1e-7 or discarded_shapes:raise ValueError('Missing changed-region guards')
    local_records=[];removed_volume=0.;added_volume=0.;outside_volume=0.
    for bounds,guard in zip(guard_bounds,guards):
        local_allowed=allowed.common(guard);checked(local_allowed)
        before=original.common(guard);after=s.common(guard);checked(before);checked(after)
        added=after.cut(before);removed=before.cut(after);checked(added);checked(removed)
        outside=removed.cut(local_allowed);checked(outside)
        if abs(added.Volume)>1e-7:raise ValueError('G correction added material in local guard')
        if abs(outside.Volume)>1e-7:raise ValueError('G correction removed outside accepted local mask/fragment')
        added_volume+=added.Volume;removed_volume+=removed.Volume;outside_volume+=outside.Volume
        local_records.append({'bounds':bounds,'added_mm3':added.Volume,'removed_mm3':removed.Volume,'outside_allowed_mm3':outside.Volume,'local_BOP':'PASS'})
    residual=abs(original.Volume-s.Volume-removed_volume);scale=max(abs(original.Volume),abs(s.Volume),abs(removed_volume))
    mass_limit=max(1e-5,1e-7*scale)
    if residual>mass_limit:raise ValueError('G correction mass identity')
    common=s.common(low);status=checked(common)
    if abs(common.Volume)>.0001:raise ValueError('Cold G overlap remains after accepted membrane correction')
    h=save(s,Path(c['outputs']['upper_g_checked']),part)
    r={'common_before_mm3':before_common.Volume,'common_before_check':before_status,'common_mm3':common.Volume,'common_check':status,
       'output_sha256':h,'input_sha256':dict(c['input_hashes']),'generated_mask_sha256':c['input_hashes']['upper_g_overlap_mask'],
       'repair_applied':True,'recipe':'accepted full fresh foundation mask followed by exact disconnected G fragment rule',
       'discarded_new_gusset_slivers':discarded,'added_mm3':added_volume,'removed_mm3':removed_volume,
       'local_mask_checks':local_records,'outside_authorized_removal_mm3':outside_volume,'global_delta_cuts':'NOT_RUN_BOUNDED_CHANGED_REGIONS','default_five_guards':default_gussets,
       'mass_identity':{'residual_mm3':residual,'relative_residual':residual/scale if scale else 0.,'limit_mm3':mass_limit},'release_ready':False}
    for key in ('upper_constructive','lower_grid','upper_g_overlap_mask'):verified(c,key)
    Path(c['outputs']['upper_g_report']).write_text(json.dumps(r,indent=2)+'\n');return r

def chip_roots(c):
    paths=inputs(c,('upper_g_checked','chip_network','chip_plan','chip_masks','chip_root_recipe'),('upper_roots','upper_chip_root_report'))
    import FreeCAD as app
    import Part as part
    V=app.Vector
    s=read(paths['upper_g_checked'],part);plan=read(paths['chip_plan'],part);net=read(paths['chip_network'],part);masks=read(paths['chip_masks'],part)
    recipe=json.loads(paths['chip_root_recipe'].read_text())
    if recipe['method']!='explicit flat quarter-circle roots plus addressed sloped roots' or recipe['flat_profiles']!=81:raise ValueError('Unapproved chip root recipe')
    points=[V(*row['point']) for row in recipe['sloped_attempts'] if row['status']=='PASS']
    if len(points)!=4:raise ValueError('Expected four accepted addressed roots')
    progress=Path(c['outputs']['upper_chip_root_report']).with_name('chip_root_progress.json')
    prism=plan.extrude(V(0,0,40))
    if prism.Volume<0:prism.reverse()
    mask_solids=list(masks.Solids)
    def cut_local_masks(q):
     b=q.BoundBox
     near=[m for m in mask_solids if m.BoundBox.XMin<b.XMax and m.BoundBox.XMax>b.XMin and m.BoundBox.YMin<b.YMax and m.BoundBox.YMax>b.YMin and m.BoundBox.ZMin<b.ZMax and m.BoundBox.ZMax>b.ZMin]
     return q.cut(part.makeCompound(near)) if near else q
    roots=[];rad=float(c['parameters']['RibRootRadius']);rec={'method':'explicit flat quarter-circle roots plus addressed sloped roots','radius':rad,'flat_profiles':0,'sloped_attempts':[]}
    for ei,e in enumerate(plan.Edges):
     a,b=e.ParameterRange;p=e.valueAt(a);mid=e.valueAt((a+b)/2);t=e.tangentAt((a+b)/2);n=V(-t.y,t.x,0);n.normalize();curve=e.Curve
     if prism.isInside(V(mid.x,mid.y,1)+n*.02,1e-7,False):n=-n
     if isinstance(curve,part.Circle):
      n=V(p.x-curve.Center.x,p.y-curve.Center.y,0);n.normalize();nt=V(mid.x-curve.Center.x,mid.y-curve.Center.y,0);nt.normalize()
      if prism.isInside(V(mid.x,mid.y,1)+nt*.02,1e-7,False):n=-n
     elif not isinstance(curve,part.Line):continue
     p.z=34.7;ps=[p-n*.05+V(0,0,.05),p+n*rad+V(0,0,.05),p+n*rad,p+V(0,0,-rad),p-n*.05+V(0,0,-rad)]
     arc=part.Arc(ps[2],p+n*(rad-rad/math.sqrt(2))+V(0,0,-rad+rad/math.sqrt(2)),ps[3]).toShape()
     f=part.Face(part.Wire([part.makeLine(ps[0],ps[1]),part.makeLine(ps[1],ps[2]),arc,part.makeLine(ps[3],ps[4]),part.makeLine(ps[4],ps[0])]))
     if isinstance(curve,part.Circle):q=f.revolve(V(curve.Center.x,curve.Center.y,0),curve.Axis,math.degrees(b-a))
     else:dv=e.valueAt(b)-e.valueAt(a);dv.z=0;q=f.extrude(dv)
     if q.Volume<0:q.reverse()
     # Flat roof starts at exact R7.2 tangent Y=-73.9578643763.
     q=q.common(part.makeBox(294.4,68.1078643763,2,V(-7.5,-73.9578643763,33.9)));q=cut_local_masks(q)
     if q.Solids and q.Volume>1e-6:roots.extend(q.Solids)
    rec['flat_profiles']=len(roots)
    if float(c['parameters']['RibRootRadius'])==.6 and len(roots)!=81:raise ValueError('Default chip root profile count changed')
    for i,q in enumerate(roots):
     progress.write_text(json.dumps({'phase':'flat_roots','completed':i,'total':len(roots)})+'\n')
     before=s.Volume;out=s.fuse(q,.000001);assert out.Solids and out.isValid() and out.Volume>=before-.001;s=out
    s.check(True);assert len(s.Solids)==1
    for point in points:
     progress.write_text(json.dumps({'phase':'addressed_roots','completed':len(rec['sloped_attempts']),'total':4})+'\n')
     near=[]
     for e in s.Edges:
      b=e.BoundBox
      if b.XMin-.001<=point.x<=b.XMax+.001 and b.YMin-.001<=point.y<=b.YMax+.001 and b.ZMin-.001<=point.z<=b.ZMax+.001:
       if e.distToShape(part.Vertex(point))[0]<1e-5:near.append(e)
     if not near:raise ValueError('Accepted root edge missing')
     try:
      q=s.makeFillet(rad,[min(near,key=lambda x:x.Length)]);q.check(True);assert q.isValid() and len(q.Solids)==1 and -.0001<=q.Volume-s.Volume<100;assert q.cut(s).common(masks).Volume<1e-6,'Root addition enters protected volume';s=q;rec['sloped_attempts'].append({'point':[point.x,point.y,point.z],'status':'PASS'})
     except Exception as ex:raise ValueError('Accepted addressed chip root failed: '+str(ex)) from ex
    s.check(True);assert s.isValid() and len(s.Solids)==1
    rec.update(valid=True,solids=1,BOP='PASS',volume=s.Volume,remaining_failed_sloped=sum(a['status']=='FAILED' for a in rec['sloped_attempts']))
    h=save(s,Path(c['outputs']['upper_roots']),part);rec.update(output_sha256=h,recipe_sha256=digest(paths['chip_root_recipe']),release_ready=False)
    Path(c['outputs']['upper_chip_root_report']).write_text(json.dumps(rec,indent=2)+'\n');return rec

def slope_roots(c):
    paths=inputs(c,('upper_spatial_blend','chip_network','chip_plan','chip_masks','inner_volume','slope_root_registry','slope_root_source','root_geometric_registry'),('upper_sloped','slope_additions','slope_root_report'))
    registry=json.loads(paths['slope_root_registry'].read_text());rows=registry['roots']
    network_matches=digest(paths['chip_network'])==registry['network_sha256']
    if len(rows)!=50 or len({r['edge'] for r in rows})!=50:raise ValueError('Invalid root registry')
    spec=importlib.util.spec_from_file_location('slope_root_cold',paths['slope_root_source']);mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    import Part as part
    net=read(paths['chip_network'],part)
    if not network_matches:
        from root_registry_matching import match,describe
        geometric=json.loads(paths['root_geometric_registry'].read_text())
        if geometric['net_sha256']!=registry['network_sha256']:raise ValueError('Registry provenance mismatch')
        rows=match(geometric['registry'],describe(net))
    plan=read(paths['chip_plan'],part);masks=read(paths['chip_masks'],part);cavity=read(paths['inner_volume'],part);s=read(paths['upper_spatial_blend'],part);adds=[];report=[]
    for start in range(0,50,5):
        pieces=[]
        for row in rows[start:start+5]:
            q,r=mod.build_one(net,plan,masks,cavity,row['edge'],row['radius']);valid_body(q);checked(q);pieces.append(q);adds.append(q);report.append(r)
        q=s.multiFuse(pieces,.000001);valid_body(q);checked(q)
        if q.Volume<s.Volume-.001:raise ValueError('Slope roots lost material')
        s=q;gc.collect()
    h=save(s,Path(c['outputs']['upper_sloped']),part);compound=part.makeCompound(adds);checked(compound);compound.exportBrep(str(c['outputs']['slope_additions']))
    r={'roots':report,'registry_match':'SOURCE_SHA' if network_matches else 'UNIQUE_GEOMETRIC_SIGNATURES_CAD_VARIANT_PROOF_PENDING','input_sha256':dict(c['input_hashes']),'output_sha256':h,'radius_between_sample_stations':'NOT_CERTIFIED','release_ready':False}
    Path(c['outputs']['slope_root_report']).write_text(json.dumps(r,indent=2)+'\n');return r

def repair_surround(c):
    paths=inputs(c,('upper_sloped',),('upper_surround','j6_surround_addition','j6_surround_report'))
    import FreeCAD as app
    import Part as part
    V=app.Vector;s=read(paths['upper_sloped'],part)
    patch=part.makeBox(67.2,29.35,2.8,V(114.9,-35.1,34.7)).cut(part.makeBox(50.68,35,10,V(123.25,-27.85,32))).cut(part.makeBox(8.6,2,3.2,V(144.29,-29.85,34.4)))
    patch=patch.fuse(part.makeBox(8.6,1.6,1,V(144.29,-29.85,36.5)));q=s.fuse(patch,1e-7);valid_body(q);checked(q)
    guard=part.makeBox(67.4,29.6,3,V(114.8,-35.2,34.6));old=s.common(guard);new=q.common(guard);removed=old.cut(new);added=new.cut(old)
    checked(removed);checked(added)
    if abs(removed.Volume)>=1e-5:raise ValueError('J6 surround removed material')
    h=save(q,Path(c['outputs']['upper_surround']),part);patch.exportBrep(str(c['outputs']['j6_surround_addition']))
    r={'added_mm3':added.Volume,'removed_mm3':removed.Volume,'output_sha256':h,'input_sha256':dict(c['input_hashes']),'release_ready':False}
    Path(c['outputs']['j6_surround_report']).write_text(json.dumps(r,indent=2)+'\n');return r

def single_rear(c):
    paths=inputs(c,('upper_surround','rear_upper'),('upper_single_rear','upper_rear_report'))
    import FreeCAD as app
    import Part as part
    V=app.Vector;s=read(paths['upper_surround'],part);rear=read(paths['rear_upper'],part)
    cut=part.makeBox(289.6,2.81,30,V(-5.1,-5.85,14.6));rep=rear.common(part.makeBox(289.62,2.81,30,V(-5.11,-5.85,14.6)))
    q=s.cut(cut).fuse(rep,1e-7);valid_body(q);checked(q)
    old=s.common(cut);new=q.common(cut);a=new.cut(old);b=old.cut(new);checked(a);checked(b)
    h=save(q,Path(c['outputs']['upper_single_rear']),part);r={'output_sha256':h,'input_sha256':dict(c['input_hashes']),'local_added':a.Volume,'local_removed':b.Volume,'release_ready':False}
    Path(c['outputs']['upper_rear_report']).write_text(json.dumps(r,indent=2)+'\n');return r

def late_ownership(c):
    names=('upper_roots','upper_din','keyboard_nodes','keyboard_segments','slope_additions','enter_addition','front_transition','j6_surround_addition','din_cutter','spatial_blend_provenance')
    paths=inputs(c,names,('late_ownership',))
    from keyboard_stage_adapter import catalog
    import FreeCAD as app
    import Part as part
    V=app.Vector;nodes=catalog(json.loads(paths['keyboard_nodes'].read_text())['nodes'],json.loads(paths['keyboard_segments'].read_text())['segments'])
    spatial=json.loads(paths['spatial_blend_provenance'].read_text())
    guard_proof=spatial.get('spatial_operation_guard',{})
    if guard_proof.get('box_xyz_dxdydz')!=[-20.,-98.,0.,320.,22.,40.] or any(guard_proof.get(k,{}).get('containment') not in ('EXACT_EMPTY_OUTSIDE','NOT_APPLICABLE_EMPTY_TOPOLOGY') for k in ('added','removed')):raise ValueError('Spatial operations not bounded by ownership guard')
    # Roots are generated, not pulled from an historical glob.
    roots=read(paths['slope_additions'],part).Solids
    if len(roots)!=50:raise ValueError('Accepted registry requires50 generated roots')
    features=[('root_%02d'%i,s) for i,s in enumerate(roots)]
    features += [(name,read(paths[name],part)) for name in ('enter_addition','front_transition','j6_surround_addition','din_cutter')]
    features += [('spatial_guard',part.makeBox(320,22,40,V(-20,-98,0))),('rear_guard',part.makeBox(289.62,2.81,30,V(-5.11,-5.85,14.6)))]
    records=[]
    for name,feature in features:
        b=feature.BoundBox
        for (x,y),_ in nodes:
            if b.XMax<x-1.445 or b.XMin>x+1.445 or b.YMax<y-1.445 or b.YMin>y+1.445 or b.ZMax<14 or b.ZMin>21:continue
            common=feature.common(part.makeBox(2.89,2.89,7,V(x-1.445,y-1.445,14)))
            if checked(common)!='NOT_APPLICABLE_EMPTY_TOPOLOGY':raise ValueError('Late feature intersects replacement guard: '+name)
        records.append(name)
    r={'status':'PASS','guard_disjoint_except_enter':True,'input_sha256':dict(c['input_hashes']),'checked_features':records,'release_ready':False}
    Path(c['outputs']['late_ownership']).write_text(json.dumps(r,indent=2)+'\n');return r
