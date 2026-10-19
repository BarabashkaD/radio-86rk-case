"""Production-only external generator. Release audits are deliberately separate."""
import hashlib,importlib.util,json,os,sys
from pathlib import Path
from types import MappingProxyType

def run():
    request=json.loads(Path(os.environ['RADIO_V10_REBUILD_REQUEST']).read_text())
    runtime=request['runtime'];runner=Path(runtime['runner_path'])
    if hashlib.sha256(runner.read_bytes()).hexdigest()!=runtime['runner_sha256']:raise ValueError('Runner SHA mismatch')
    sys.path.insert(0,str(runner.parent));spec=importlib.util.spec_from_file_location('_portable_runner',runner)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    manifest=request['manifest'];manifest['parameters']=request['parameters'];root=Path(request['input_root']);out=Path(request['run_root'])
    if out.exists() or out.resolve().is_relative_to(root.resolve()):raise ValueError('Fresh disjoint output required')
    known={}
    for name,item in manifest['inputs'].items():
        p=module.rooted(root,item['path'])
        if module.sha256(p)!=item['sha256']:raise ValueError('Production source closure changed: '+name)
        known[name]=p
    import FreeCAD as App
    import Part
    version=App.Version()
    if list(version[:2])!=['1','1']:raise ValueError('This generator requires FreeCAD 1.1.x; configure a compatible runtime')
    if App.listDocuments():raise ValueError('Cold process requires no open documents')
    out.mkdir(parents=True);stages=[]
    for stage in manifest['stages']:
        if stage['id']=='document_export' and request['mode']=='geometry_only':break
        if stage['adapter'] not in manifest['inputs'] or manifest['inputs'][stage['adapter']]['kind']!='source':raise ValueError('Unpinned production adapter')
        if not set(stage['needs'])<=known.keys():raise ValueError('Missing production dependency')
        outputs={k:module.rooted(out,s['path']) for k,s in stage['outputs'].items()}
        if set(outputs)&known.keys() or any(p.exists() for p in outputs.values()):raise ValueError('Output overwrite forbidden')
        for p in outputs.values():p.parent.mkdir(parents=True,exist_ok=True)
        c=MappingProxyType({'stage_id':stage['id'],'inputs':{k:known[k] for k in stage['needs']},
          'input_hashes':{k:module.sha256(known[k]) for k in stage['needs']},'outputs':outputs,
          'parameters':manifest['parameters'],'cold_build':True,'owns_enter':stage['owns_enter'],
          'build_manifest':manifest,'input_root':str(root),'output_root':str(out),'runtime':runtime})
        module.invoke(stage,c,manifest['inputs'],root)
        if App.listDocuments():raise ValueError('Adapter left document open')
        checked={k:module.check_artifact(outputs[k],s,App,Part,preview=True) for k,s in stage['outputs'].items()}
        stages.append({'id':stage['id'],'outputs':checked});known.update(outputs)
    for name,item in manifest['inputs'].items():
        if module.sha256(module.rooted(root,item['path']))!=item['sha256']:raise ValueError('Source changed during generation')
    for stage in stages:
        for name,item in stage['outputs'].items():
            if module.sha256(known[name])!=item['sha256']:raise ValueError('Generated artifact changed')
    result={'status':'GENERATED_NOT_RELEASE_VALIDATED','release_ready':False,'mode':request['mode'],
       'platform_status':runtime.get('platform_status','UNVERIFIED_PLATFORM'),
       'freecad_version':version,'stages':stages,'release_audit':'NOT_RUN_SEPARATE_WORKFLOW','global_bop':'NOT_RUN_RESOURCE_PRECAUTION'}
    (out/'portable_result.json').write_text(json.dumps(result,indent=2)+'\n')
if __name__=='__main__' or os.environ.get('RADIO_V10_REBUILD_REQUEST'):run()
