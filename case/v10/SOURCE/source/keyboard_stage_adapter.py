"""Cold whole-node replacement; consumes regenerated triangle/segments/catalog only."""
import gc
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
from geometry_checks import check_boolean_result


def digest(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def verified(c,key):
    p=Path(c['inputs'][key])
    if p.is_symlink() or not p.is_file() or digest(p)!=c['input_hashes'][key]:raise ValueError('Input SHA mismatch: '+key)
    return p

def catalog(nodes,segments):
    xs=sorted({s['center'] for s in segments if s['axis']=='Y'});ys=sorted({s['center'] for s in segments if s['axis']=='X'})
    if len(nodes)!=81:raise ValueError('Accepted cold catalog requires all 81 nodes')
    out=[];seen=set()
    for row in nodes:
        coords=[]
        for value,axis in zip(row['xy'],(xs,ys)):
            matches=[v for v in axis if abs(v-value)<1e-5]
            if len(matches)!=1:raise ValueError('Ambiguous/missing exact center')
            coords.append(matches[0])
        key=tuple(coords)
        if key in seen or len(row['xy'])!=2 or len(row['widths'])!=2 or any(abs(w-2.85)>1e-8 for w in row['widths']) or row['tip'] not in (17.4,18.6):raise ValueError('Invalid accepted node')
        seen.add(key);out.append((key,row['tip']))
    return out

def valid_body(s):
    if s.isNull() or not s.isValid() or len(s.Solids)!=1 or s.Volume<=0:raise ValueError('Expected valid one-solid keyboard')

def build_keyboard(context):
    if context.get('cold_build') is not True:raise ValueError('Cold execution required')
    if set(context['outputs'])!={'keyboard_replaced','keyboard_provenance'}:raise ValueError('Exact keyboard outputs required')
    if any(Path(p).exists() for p in context['outputs'].values()):raise ValueError('Outputs must be fresh')
    paths={k:verified(context,k) for k in ('keyboard_profiles','keyboard_segments','keyboard_nodes','keyboard_geometry_source')}
    nodes=json.loads(paths['keyboard_nodes'].read_text())['nodes'];segments=json.loads(paths['keyboard_segments'].read_text())['segments'];rows=catalog(nodes,segments)
    spec=importlib.util.spec_from_file_location('cold_keyboard_geometry',paths['keyboard_geometry_source']);g=importlib.util.module_from_spec(spec);spec.loader.exec_module(g)
    import FreeCAD as app
    import Part as part
    if app.listDocuments():raise ValueError('Clean CAD context required')
    source_hash=context['input_hashes']['keyboard_profiles'];V=app.Vector;records=[]
    output=Path(context['outputs']['keyboard_replaced'])
    with tempfile.TemporaryDirectory(prefix='keyboard_cold_',dir=output.parent) as tmp:
        previous=paths['keyboard_profiles'];previous_sha=source_hash
        for start in range(0,81,4):
            base=g.load(previous,previous_sha,part=part);valid_body(base);pieces=[];cuts=[]
            for i in range(start,min(start+4,81)):
                (x,y),tip=rows[i];old=g.load(paths['keyboard_profiles'],source_hash,part=part)
                local=old.common(part.makeBox(3.1,3.1,7,V(x-1.55,y-1.55,14)));local.translate(V(-x,-y,0))
                q=g.template(tip,app=app,part=part).common(local);q.check(True)
                if not q.isValid() or q.isNull():raise ValueError('Invalid local replacement')
                extra=q.cut(local);status=check_boolean_result(extra)
                if abs(extra.Volume)>1e-3:raise ValueError('Replacement leaves source region')
                q.translate(V(x,y,0));pieces.append(q);cuts.append(part.makeBox(2.85,2.85,7,V(x-1.425,y-1.425,14)))
                records.append({'node':i,'exact_xy':[x,y],'template_bop':'PASS','extra_status':status,'extra_mm3':extra.Volume})
                del old,local,extra;gc.collect()
            result=base.cut(part.makeCompound(cuts),1e-7).multiFuse(pieces,1e-7);valid_body(result)
            previous=Path(tmp)/('batch_%03d.brep'%min(start+4,81));result.exportBrep(str(previous));previous_sha=digest(previous)
            del base,result,pieces,cuts;gc.collect()
        # Exclusive final write; intermediate files belong only to this run.
        with previous.open('rb') as src,output.open('xb') as dst:
            for block in iter(lambda:src.read(1024*1024),b''):dst.write(block)
        reopened=g.load(output,digest(output),part=part);valid_body(reopened)
        report={'producer':'keyboard_stage_adapter.build_keyboard','nodes':records,'count':81,'batch_size':4,'solids':1,
                'volume_mm3':reopened.Volume,'output_sha256':digest(output),'input_sha256':dict(context['input_hashes']),
                'global_bop':'NOT_RUN','junction_bop':'NOT_RUN','full_mesh':'NOT_RUN','release_ready':False}
    for k in paths:verified(context,k)
    Path(context['outputs']['keyboard_provenance']).write_text(json.dumps(report,indent=2)+'\n')
    return report
