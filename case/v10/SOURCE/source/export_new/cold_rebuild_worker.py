"""Run only the upstream graph in a fresh interpreter with FreeCAD available."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
from types import MappingProxyType

def main(request_path):
    request=json.loads(Path(request_path).read_text());runtime=request['runtime']
    runner=Path(runtime['runner_path'])
    if hashlib.sha256(runner.read_bytes()).hexdigest()!=runtime['runner_sha256']:raise ValueError('Runner SHA mismatch')
    sys.path.insert(0,str(runner.parent))
    spec=importlib.util.spec_from_file_location('pinned_build_v10',runner)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    m=request['manifest'];m['parameters']=request['parameters']
    root=Path(request['input_root']);out=Path(request['run_root'])
    module.validate_manifest(m,root)
    if out.exists():raise ValueError('Cold output already exists')
    if out.resolve().is_relative_to(root.resolve()) or root.resolve().is_relative_to(out.resolve()):raise ValueError('Input/output roots overlap')
    known={k:module.rooted(root,v['path']) for k,v in m['inputs'].items()}
    # The runner owns ordinary shape checks and the monolithic-BOP precaution.
    module.execute(m,root,out,runtime=runtime,geometry_only=True)
    for stage in m['stages']:
        if stage['id']=='document_export':break
        for name,output in stage['outputs'].items():known[name]=module.rooted(out,output['path'])
    roles={k:{'path':str(known[k]),'sha256':module.sha256(known[k])} for k in
           ('lower_final','upper_final','foot_left','foot_right','pad_references','keyboard_replaced')}
    (out/'rebuild_result.json').write_text(json.dumps({'cache_key':request['cache_key'],'roles':roles,
      'release_ready':False,'checks':'UPSTREAM_ARTIFACT_CHECKS_ONLY'},indent=2))
if __name__=='__main__' or os.environ.get('RADIO_V10_REBUILD_REQUEST'):
    main(os.environ['RADIO_V10_REBUILD_REQUEST'])
