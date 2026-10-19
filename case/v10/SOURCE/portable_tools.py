"""Relocatable verified source bundle and geometry-only external generator.
No FreeCAD imports, installations, or launches during build/verify/prepare.
"""
import ast
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import uuid
import sys
REFERENCE_APP_RUN_SHA='66ea3745e20852699e2bbc692b45d21f60d936d292497964a0f6d44a5600259c'

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def require(ok,text):
    if not ok:raise ValueError(text)
def rooted(root,relative):
    require(isinstance(relative,str) and relative and '\\' not in relative,'Invalid relative path')
    p=Path(relative);require(not p.is_absolute() and '..' not in p.parts and p.as_posix()==relative,'Unsafe relative path')
    result=Path(root)
    for piece in p.parts:
        result=result/piece;require(not result.is_symlink(),'Symlink path forbidden')
    require(result.resolve().is_relative_to(Path(root).resolve()),'Path escaped bundle')
    return result

def build_bundle(source_root,manifest_path,destination,model=None):
    source_root=Path(source_root).resolve();destination=Path(destination)
    require(not destination.exists(),'Fresh bundle destination required')
    require(not destination.resolve().is_relative_to(source_root),'Bundle cannot be inside source root')
    m=json.loads(Path(manifest_path).read_text());require(m['status']=='candidate','Candidate manifest required')
    # Production stage closure only. Release QA and archival evidence are a separate bundle.
    stage_inputs={stage['adapter'] for stage in m['stages']}|{name for stage in m['stages'] for name in stage['needs']}
    excluded={k:v['kind'] for k,v in m['inputs'].items() if k not in stage_inputs}
    m['inputs']={k:v for k,v in m['inputs'].items() if k in stage_inputs}
    m['checks']=[];m.pop('after_checks',None)
    selected={v['path']:v['sha256'] for v in m['inputs'].values()}
    selected['build_v10.py']=sha(rooted(source_root,'build_v10.py'))
    # Close ordinary local Python imports without importing or executing modules.
    pending=list(selected);scanned=set()
    while pending:
        rel=pending.pop();p=rooted(source_root,rel)
        require(p.is_file() and sha(p)==selected[rel],'Source SHA mismatch: '+rel)
        if p.suffix!='.py' or rel in scanned:continue
        scanned.add(rel)
        for node in ast.walk(ast.parse(p.read_text())):
            names=[]
            if isinstance(node,ast.Import):names=[a.name for a in node.names]
            elif isinstance(node,ast.ImportFrom) and node.module:names=[node.module]
            for name in names:
                module_path=name.replace('.','/')+'.py'
                for candidate in (source_root/module_path,p.parent/module_path):
                    if candidate.is_file() and candidate.resolve().is_relative_to(source_root):
                        relative=candidate.relative_to(source_root).as_posix()
                        if relative not in selected:selected[relative]=sha(candidate);pending.append(relative)
    destination.mkdir(parents=True)
    records={};warnings=[]
    for rel,expected in sorted(selected.items()):
        src=rooted(source_root,rel);require(sha(src)==expected,'Source changed during package')
        target=rooted(destination,'source/'+rel);target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(src,target)
        records['source/'+rel]=expected
        if src.suffix in ('.py','.json') and '/workspace/' in src.read_text():warnings.append({'path':'source/'+rel,'reason':'Historical host path present; runtime use requires review'})
    target=destination/'source/project_manifest.json';target.write_text(json.dumps(m,indent=2)+'\n');records['source/project_manifest.json']=sha(target)
    for filename in ('portable_tools.py','open_saved_view.FCMacro','portable_run.py'):
        shutil.copyfile(Path(__file__).with_name(filename),destination/filename);records[filename]=sha(destination/filename)
    model_rel=None
    if model:
        model=Path(model);require(model.is_file() and not model.is_symlink(),'Missing regular model')
        model_rel='documents/model.FCStd';target=rooted(destination,model_rel);target.parent.mkdir();shutil.copyfile(model,target);records[model_rel]=sha(target)
    project={'schema_version':1,'model_kind':'SAVED_BODY_VIEW_PLUS_EXTERNAL_GEOMETRY_GENERATOR',
      'manifest':'source/project_manifest.json','input_root':'source','runner':'source/build_v10.py',
      'worker':'portable_run.py','model':model_rel,'cache_root':'cache',
      'output_root':'generated','files':records,'host_path_audit':warnings,
      'supported_modes':['geometry_only','generate_exports'],'excluded_audit_input_roles':excluded,'release_ready':False,'generator_validation':'NO_CAD_RELOCATION_EXECUTION_YET','release_audit':'NOT_INCLUDED_IN_MINIMAL_PRODUCTION_BUNDLE'}
    (destination/'portable_project.json').write_text(json.dumps(project,indent=2)+'\n')
    (destination/'runtime.example.json').write_text(json.dumps({'command':['ABSOLUTE_PATH_TO_YOUR_TRUSTED_FREECAD_PYTHON_OR_WRAPPER'],'command_sha256':'EXPLICIT_SHA256_OF_FREECAD_COMMAND_EXECUTABLE','timeout_seconds':3600,'gmsh_binary':'ABSOLUTE_PATH_TO_YOUR_GMSH_BINARY','gmsh_sha256':'EXPLICIT_SHA256_OF_LOCAL_GMSH','gmsh_command':['ABSOLUTE_PATH_TO_YOUR_GMSH_BINARY'],'gmsh_command_sha256':'EXPLICIT_SHA256_OF_COMMAND_EXECUTABLE'},indent=2)+'\n')
    verify_bundle(destination/'portable_project.json');return project

def verify_bundle(project_path):
    project_path=Path(project_path).resolve();root=project_path.parent;p=json.loads(project_path.read_text())
    require(p['schema_version']==1,'Unknown portable schema')
    for rel,expected in p['files'].items():
        f=rooted(root,rel);require(f.is_file() and sha(f)==expected,'Bundle SHA mismatch: '+rel)
    manifest=json.loads(rooted(root,p['manifest']).read_text())
    input_root=rooted(root,p['input_root'])
    for role,spec in manifest['inputs'].items():require(sha(rooted(input_root,spec['path']))==spec['sha256'],'Manifest input changed: '+role)
    for key in ('runner','worker','cache_root','output_root'):rooted(root,p[key])
    return p

def prepare_rebuild(project_path,runtime_path,parameters=None,mode='geometry_only'):
    project_path=Path(project_path).resolve();root=project_path.parent;p=verify_bundle(project_path)
    runtime=json.loads(Path(runtime_path).read_text());command=runtime.get('command')
    require(isinstance(command,list) and command and all(isinstance(x,str) for x in command),'Explicit runtime argv required')
    require(Path(command[0]).is_absolute() and Path(command[0]).is_file(),'Configure a trusted installed FreeCAD Python/runtime executable')
    require(mode in ('geometry_only','generate_exports'),'Unsupported rebuild mode')
    require(sha(command[0])==runtime.get('command_sha256'),'Explicit FreeCAD command executable SHA mismatch')
    manifest=json.loads(rooted(root,p['manifest']).read_text());values=dict(manifest['parameters'])
    if parameters:values.update(parameters)
    json.dumps(values,allow_nan=False)
    cache=rooted(root,p['cache_root'])/uuid.uuid4().hex;cache.mkdir(parents=True,exist_ok=False)
    runner=rooted(root,p['runner']);worker=rooted(root,p['worker'])
    resolved_runtime={'command':command,'runner_path':str(runner),'runner_sha256':sha(runner),
      'cache_root':str(rooted(root,p['cache_root'])),'timeout_seconds':runtime.get('timeout_seconds',3600)}
    input_root=rooted(root,p['input_root'])
    if mode=='generate_exports':
        binary=Path(runtime.get('gmsh_binary',''))
        mesh_spec=manifest['inputs'].get('canonical_mesh_config')
        require(mesh_spec is not None,'Canonical mesh contract missing')
        original=json.loads(rooted(input_root,mesh_spec['path']).read_text())
        require(binary.is_absolute() and binary.is_file(),'Configure an existing local Gmsh binary')
        require(isinstance(runtime.get('gmsh_sha256'),str) and sha(binary)==runtime['gmsh_sha256'],'Local Gmsh SHA must be explicitly configured and match')
        gmsh_command=runtime.get('gmsh_command')
        require(isinstance(gmsh_command,list) and gmsh_command and all(isinstance(x,str) for x in gmsh_command),'Explicit local Gmsh argv required')
        gmsh_executable=Path(gmsh_command[0])
        require(gmsh_executable.is_absolute() and gmsh_executable.is_file() and sha(gmsh_executable)==runtime.get('gmsh_command_sha256'),'Explicit Gmsh command executable SHA mismatch')
        reference_match=sha(binary)==original['gmsh_sha256'] and sys.platform=='linux' and sha(command[0])==REFERENCE_APP_RUN_SHA
        resolved_runtime.update(gmsh_command=gmsh_command,gmsh_command_sha256=runtime['gmsh_command_sha256'],
          platform_status='VERIFIED_LINUX_REFERENCE' if reference_match else 'UNVERIFIED_PLATFORM')
        local_source=cache/'configured_source';shutil.copytree(input_root,local_source)
        original_reference_hash=original['gmsh_sha256']
        original['gmsh_binary']=str(binary);original['gmsh_sha256']=runtime['gmsh_sha256']
        config=rooted(local_source,mesh_spec['path']);config.write_text(json.dumps(original,indent=2)+'\n')
        mesh_spec['sha256']=sha(config);input_root=local_source
        adapter_spec=manifest['inputs']['canonical_mesh_source'];adapter=rooted(local_source,adapter_spec['path'])
        adapter_before=sha(adapter);text=adapter.read_text()
        old_wrapper="    wrapper=Path(runtime['command'][0]);expected=binary.parents[2]/'AppRun'\n    if wrapper.resolve()!=expected.resolve():raise ValueError('Gmsh must use the same verified official AppRun')"
        new_wrapper="    gmsh_command=runtime['gmsh_command']\n    if sha(Path(gmsh_command[0]))!=runtime['gmsh_command_sha256']:raise ValueError('Local Gmsh command SHA mismatch')"
        require(text.count(old_wrapper)==1 and text.count("command=[str(wrapper),'gmsh',str(target)")==1,'Canonical adapter changed; review relocation patch before use')
        text=text.replace(old_wrapper,new_wrapper).replace("command=[str(wrapper),'gmsh',str(target)","command=list(gmsh_command)+[str(target)")
        adapter.write_text(text);adapter_spec['sha256']=sha(adapter)
        (cache/'runtime_materialization.json').write_text(json.dumps({'platform_status':resolved_runtime['platform_status'],
          'reference_gmsh_sha256':original_reference_hash,'configured_gmsh_sha256':runtime['gmsh_sha256'],
          'adapter_original_sha256':adapter_before,'adapter_relocated_sha256':sha(adapter),'geometry_recipe_changed':False,
          'release_ready':False},indent=2)+'\n')
        local_runner=local_source/'build_v10.py';resolved_runtime['runner_path']=str(local_runner);resolved_runtime['runner_sha256']=sha(local_runner)
    request={'mode':mode,'manifest':manifest,'parameters':values,'input_root':str(input_root),
      'output_root':str(rooted(root,p['output_root'])),'runtime':resolved_runtime,'run_root':str(cache/'artifacts'),
      'cache_key':hashlib.sha256(json.dumps({'parameters':values,'files':p['files']},sort_keys=True,allow_nan=False).encode()).hexdigest()}
    f=cache/'request.json';f.write_text(json.dumps(request,indent=2)+'\n')
    return {'request_path':str(f),'command':command+[str(worker)],'timeout_seconds':resolved_runtime['timeout_seconds']}

def main():
    import argparse
    parser=argparse.ArgumentParser();sub=parser.add_subparsers(dest='action',required=True)
    v=sub.add_parser('verify');v.add_argument('project')
    b=sub.add_parser('bundle');b.add_argument('source_root');b.add_argument('manifest');b.add_argument('destination');b.add_argument('--model')
    r=sub.add_parser('rebuild');r.add_argument('project');r.add_argument('runtime');r.add_argument('--parameters');r.add_argument('--mode',choices=['geometry_only','generate_exports'],default='geometry_only')
    args=parser.parse_args()
    if args.action=='verify':print(json.dumps({'status':'HASH_CLOSURE_VERIFIED_NO_CAD','files':len(verify_bundle(args.project)['files'])}))
    elif args.action=='bundle':print(json.dumps(build_bundle(args.source_root,args.manifest,args.destination,args.model),indent=2))
    else:
        params=json.loads(Path(args.parameters).read_text()) if args.parameters else None
        plan=prepare_rebuild(args.project,args.runtime,params,args.mode)
        env=dict(os.environ,RADIO_V10_REBUILD_REQUEST=plan['request_path'])
        result=subprocess.run(plan['command'],env=env,timeout=plan['timeout_seconds'],check=False)
        require(result.returncode==0,'External generator failed')
        output=Path(plan['request_path']).parent/'artifacts/portable_result.json'
        require(output.is_file(),'No successful generator result; inspect runtime output')
        print(json.dumps({'status':'GEOMETRY_REBUILT_UNVALIDATED','result':str(output),'release_ready':False}))
if __name__=='__main__':main()
