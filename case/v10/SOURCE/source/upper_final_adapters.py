"""Explicit DIN relief and whole-node transfer from fresh pre-trim geometry."""
import gc
import json
import math
from pathlib import Path
import tempfile
from geometry_checks import check_boolean_result as checked
from keyboard_stage_adapter import digest,verified,catalog,valid_body

DIN_ROLES=('Part__Feature022','Part__Feature024')
def din_rows(rows):
    selected=[r for r in rows if r['name'] in DIN_ROLES]
    if sorted(r['name'] for r in selected)!=sorted(DIN_ROLES):raise ValueError('Exactly both DIN roles required')
    for r in selected:
        b=r['bbox']
        if len(b)!=6 or not all(math.isfinite(v) for v in b) or any(b[i+3]<=b[i] for i in range(3)):raise ValueError('Invalid DIN bbox')
    return selected

def fresh(c,names):
    if c.get('cold_build') is not True or set(c['outputs'])!=set(names):raise ValueError('Exact cold output contract required')
    if any(Path(p).exists() for p in c['outputs'].values()):raise ValueError('Outputs must be fresh')

def read(path,part):
    s=part.Shape();s.read(str(path));return s

def empty(shape):
    status=checked(shape)
    if status!='NOT_APPLICABLE_EMPTY_TOPOLOGY':raise ValueError('Expected exact empty topology')
    return status

def save(shape,path,part):
    shape.exportBrep(str(path));q=read(path,part);valid_body(q)
    for delta in (q.cut(shape),shape.cut(q)):
        checked(delta)
        if abs(delta.Volume)>.001:raise ValueError('Save/reopen differs')
    return digest(path)

def build_din(c):
    fresh(c,('upper_din','din_cutter','din_provenance'))
    paths={k:verified(c,k) for k in ('upper_single_rear','inventory')}
    rows=din_rows(json.loads(paths['inventory'].read_text()))
    import FreeCAD as app
    import Part as part
    if app.listDocuments():raise ValueError('Clean CAD context required')
    V=app.Vector;s=read(paths['upper_single_rear'],part);valid_body(s)
    cutter=part.makeBox(22.704,20.752,6.36,V(91.508,-26.35,30))
    edges=[e for e in cutter.Edges if e.BoundBox.ZLength>6.35]
    if len(edges)!=4:raise ValueError('Expected four DIN plan corners')
    cutter=cutter.makeFillet(1,edges)
    top=[e for e in cutter.Edges if abs(e.BoundBox.ZMin-36.36)<1e-6 and abs(e.BoundBox.ZMax-36.36)<1e-6]
    if not top:raise ValueError('DIN ceiling edges absent')
    cutter=cutter.makeFillet(.5,top).common(part.makeBox(30,30,10,V(89,-35.85,29)));checked(cutter)
    q=s.cut(cutter,1e-7);valid_body(q);checked(q);records=[]
    for row in rows:
        b=row['bbox'];common=q.common(part.makeBox(b[3]-b[0],b[4]-b[1],b[5]-b[2],V(*b[:3])))
        status=checked(common)
        if abs(common.Volume)>=1e-5:raise ValueError('DIN collision')
        records.append({'name':row['name'],'common_mm3':common.Volume,'topology_check':status})
    added=q.cut(s);outside=s.cut(q).cut(cutter)
    for diff in (added,outside):
        checked(diff)
        if abs(diff.Volume)>.001:raise ValueError('DIN affected material outside permitted cutter')
    hashes={name:save(shape,Path(c['outputs'][name]),part) for name,shape in [('upper_din',q),('din_cutter',cutter)]}
    for k in paths:verified(c,k)
    report={'input_sha256':dict(c['input_hashes']),'output_sha256':hashes,'checks':records,'ceiling':36.36,'roof':37.5,'flat_remainder':1.14,'BOP':'PASS','release_ready':False}
    Path(c['outputs']['din_provenance']).write_text(json.dumps(report,indent=2)+'\n');return report

def ownership(data,hashes):
    if data.get('status')!='PASS' or data.get('guard_disjoint_except_enter') is not True:raise ValueError('Late feature ownership unproven')
    for key in ('upper_roots','upper_din','keyboard_nodes'):
        if data.get('input_sha256',{}).get(key)!=hashes[key]:raise ValueError('Ownership SHA mismatch '+key)
    features=data.get('checked_features')
    if not isinstance(features,list) or len(features)!=56 or len(set(features))!=56:raise ValueError('Expected all56 late feature ownership checks')

def transfer_keyboard(c):
    fresh(c,('upper_final','upper_transfer_provenance'))
    names=('upper_din','upper_roots','keyboard_profiles','keyboard_replaced','keyboard_nodes','keyboard_segments','enter_original','enter_supported','late_ownership')
    paths={k:verified(c,k) for k in names};ownership(json.loads(paths['late_ownership'].read_text()),c['input_hashes'])
    nodes=catalog(json.loads(paths['keyboard_nodes'].read_text())['nodes'],json.loads(paths['keyboard_segments'].read_text())['segments'])
    import FreeCAD as app
    import Part as part
    if app.listDocuments():raise ValueError('Clean CAD context required')
    V=app.Vector;out=Path(c['outputs']['upper_final']);log=[]
    erem=read(paths['enter_original'],part).cut(read(paths['enter_supported'],part));checked(erem)
    with tempfile.TemporaryDirectory(prefix='upper_nodes_',dir=out.parent) as tmp:
        previous=paths['upper_din'];previous_hash=c['input_hashes']['upper_din']
        for start in range(0,81,4):
            if digest(previous)!=previous_hash:raise ValueError('Batch source changed')
            base=read(previous,part);valid_body(base);pieces=[];cuts=[];batch=[]
            for i in range(start,min(81,start+4)):
                (x,y),tip=nodes[i];guard=part.makeBox(2.89,2.89,7,V(x-1.445,y-1.445,14))
                old=read(paths['keyboard_profiles'],part).common(guard)
                new=read(paths['keyboard_replaced'],part).common(guard)
                local=read(paths['upper_roots'],part).common(guard)
                checked(old);checked(local)
                extra=local.cut(old,1e-7);missing=old.cut(local,1e-7);es=checked(extra);empty(missing)
                if not 0<=extra.Volume<=local.Volume+1e-7:raise ValueError('Invalid extra material')
                rebuilt=old.fuse(extra,1e-7) if extra.Volume>1e-8 else old
                empty(rebuilt.cut(local,1e-7));empty(local.cut(rebuilt,1e-7))
                new=new.cut(erem,1e-7);q=new.fuse(extra,1e-7) if extra.Volume>1e-8 else new
                checked(q)
                if q.isNull():raise ValueError('Null replacement')
                pieces.append(q);cuts.append(part.makeBox(2.85,2.85,7,V(x-1.425,y-1.425,14)))
                batch.append({'node':i,'xy':[x,y],'extra_mm3':extra.Volume,'extra_check':es})
                del old,new,local,extra,missing,rebuilt;gc.collect()
            result=base.cut(part.makeCompound(cuts),1e-7).multiFuse(pieces,1e-7);valid_body(result)
            for row in batch:
                x,y=row['xy'];junction=result.common(part.makeBox(5,5,8,V(x-2.5,y-2.5,13.5)));checked(junction)
                if len(junction.Solids)!=1:raise ValueError('Invalid transfer junction')
                row['junction_BOP']='PASS'
            log.extend(batch);previous=Path(tmp)/('upper_%03d.brep'%min(81,start+4));result.exportBrep(str(previous));previous_hash=digest(previous)
            del base,result,pieces,cuts;gc.collect()
        with previous.open('rb') as source,out.open('xb') as target:
            for block in iter(lambda:source.read(1024*1024),b''):target.write(block)
        valid_body(read(out,part))
        # Earlier batch crops do not certify the final SHA: recheck all81 final junctions.
        final_hash=digest(out)
        for row in log:
            x,y=row['xy'];final_body=read(out,part)
            region=final_body.common(part.makeBox(5,5,8,V(x-2.5,y-2.5,13.5)));checked(region)
            if len(region.Solids)!=1:raise ValueError('Invalid final junction')
            row['final_junction_BOP']='PASS';row['artifact_sha256']=final_hash
            row['final_junction_bounds']=[x-2.5,y-2.5,13.5,x+2.5,y+2.5,21.5]
            row['final_junction_volume_mm3']=region.Volume;row['final_junction_solids']=len(region.Solids)
            del final_body,region;gc.collect()
    for k in paths:verified(c,k)
    report={'input_sha256':dict(c['input_hashes']),'output_sha256':digest(out),'nodes':log,'global_BOP':'NOT_RUN','full_mesh':'NOT_RUN','release_ready':False}
    Path(c['outputs']['upper_transfer_provenance']).write_text(json.dumps(report,indent=2)+'\n');return report
