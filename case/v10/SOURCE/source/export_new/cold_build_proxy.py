"""External FreeCAD proxy: recompute runs a pinned cold graph, never scales snapshots.
Keep this module on FreeCAD's Python path when reopening the project.
"""
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import subprocess
import uuid

EDITABLE = ('SideSlotExternalWidth','SideSlotPitch','SideSlotAngle','SideSlotHeight',
 'SideSlotBottomMargin','SideSlotTopMargin','TopSlotExternalWidth','TopSlotLength','TopSlotAngle',
 'TopSlotPitch','FloorInnerRadius','PostRootRadius','FootAngle','RibWidth','RibHeight','RibPitch','RibRootRadius','RibNodeRadius',
 'UpperChipRibPitch','UpperPerimeterRadius','UpperGussetEdgeRadius','FrontTransitionRadius')
ROLES={'LowerShell':'lower_final','UpperShell':'upper_final',
       'FoldFootLeft':'foot_left','FoldFootRight':'foot_right','PadReferences':'pad_references'}

def digest(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def canonical(x):return json.dumps(x,sort_keys=True,separators=(',',':'),allow_nan=False)
def cache_key(parameters, hashes):return hashlib.sha256(canonical({'parameters':parameters,'inputs':hashes}).encode()).hexdigest()

def validate_runtime(runtime):
    command=runtime.get('command')
    if not isinstance(command,list) or not command or any(not isinstance(x,str) for x in command):
        raise ValueError('RebuildCommand_REQUIRED: runtime.command must be argv for trusted Python with FreeCAD')
    if not Path(command[0]).is_absolute() or not Path(command[0]).is_file():
        raise ValueError('RebuildCommand_REQUIRED: interpreter must be an existing absolute path')
    runner=Path(runtime.get('runner_path',''))
    if not runner.is_absolute() or not runner.is_file() or digest(runner)!=runtime.get('runner_sha256'):
        raise ValueError('Pinned build_v10.py runner required')
    if not Path(runtime.get('cache_root','')).is_absolute():raise ValueError('Absolute cache_root required')
    return command

MARGIN_MODES=('height_bottom','top_bottom','height_top')
DEPENDENT={'height_bottom':'SideSlotTopMargin','top_bottom':'SideSlotHeight','height_top':'SideSlotBottomMargin'}

def verified_source(desc, role):
    spec=desc['manifest']['inputs'][role];root=Path(desc['input_root']).resolve()
    relative=Path(spec['path'])
    if relative.is_absolute() or '..' in relative.parts:raise ValueError('Unsafe source path: '+role)
    p=root/relative
    cursor=root
    for part in relative.parts:
        cursor=cursor/part
        if cursor.is_symlink():raise ValueError('Symlink source closure: '+role)
    if not p.is_file() or digest(p)!=spec['sha256']:raise ValueError('Source closure changed: '+role)
    return p

def resolve_margins(desc,values):
    mode=values.get('SideMarginMode','height_bottom')
    if mode not in MARGIN_MODES:raise ValueError('Unknown SideMarginMode')
    path=verified_source(desc,'ventilation_parameters_source')
    spec=importlib.util.spec_from_file_location('_cold_pinned_margins',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module.resolve(values,mode)


class ColdBuildProxy:
    def __init__(self,obj,descriptor):
        self.descriptor=descriptor;self.armed=False;self.running=False;self.syncing=False
        obj.Proxy=self
    def dumps(self):return self.descriptor
    def loads(self,state):self.descriptor=state;self.armed=True;self.running=False;self.syncing=False
    def __getstate__(self):return self.descriptor
    def __setstate__(self,state):self.loads(state)
    def onChanged(self,obj,prop):
        if not getattr(self,'armed',False) or getattr(self,'syncing',False):return
        if prop not in ('SideMarginMode','SideSlotHeight','SideSlotTopMargin','SideSlotBottomMargin'):return
        self.syncing=True
        try:
            values=dict(self.descriptor['parameters'])
            for key in self.descriptor['editable']:values[key]=float(getattr(obj,key))
            values['SideMarginMode']=str(obj.SideMarginMode)
            values,derived=resolve_margins(self.descriptor,values)
            setattr(obj,derived,values[derived])
            for key in ('SideSlotHeight','SideSlotTopMargin','SideSlotBottomMargin'):
                obj.setEditorMode(key,1 if key==derived else 0)
            obj.ColdRebuild='PARAMETERS_CHANGED_REBUILD_REQUIRED';obj.LastError=''
        except Exception as ex:
            obj.ColdRebuild='BLOCKED_OR_FAILED';obj.LastError=str(ex)
        finally:self.syncing=False
    def execute(self,obj):
        if not self.armed or self.running:return
        self.running=True
        try:
            desc=self.descriptor
            values=dict(desc['parameters'])
            for key in desc['editable']:values[key]=float(getattr(obj,key))
            if any(not math.isfinite(values[k]) for k in desc['editable']):raise ValueError('Nonfinite parameter')
            hashes=desc['input_hashes']
            for source_role in desc['manifest']['inputs']:verified_source(desc,source_role)
            if hasattr(obj,'SideMarginMode'):
                values['SideMarginMode']=str(obj.SideMarginMode)
                values,derived=resolve_margins(desc,values)
            key=cache_key(values,hashes)
            if key==obj.BuiltKey:return
            runtime=desc['runtime'];command=validate_runtime(runtime)
            worker=Path(desc['worker_path'])
            if digest(worker)!=desc['worker_sha256']:raise ValueError('Cold worker hash mismatch')
            cache_root=Path(runtime['cache_root']).resolve()
            input_root=Path(desc['input_root']).resolve()
            output_root=Path(desc['output_root']).resolve()
            if any(cache_root.is_relative_to(root) or root.is_relative_to(cache_root) for root in (input_root,output_root)):
                raise ValueError('Cache must be disjoint from source and initial output roots')
            cache=cache_root/(key+'-'+uuid.uuid4().hex)
            cache.mkdir(parents=True,exist_ok=False)
            request=dict(desc,parameters=values,cache_key=key,run_root=str(cache/'artifacts'))
            request_path=cache/'request.json';request_path.write_text(canonical(request))
            obj.ColdRebuild='RUNNING'
            env=dict(os.environ, RADIO_V10_REBUILD_REQUEST=str(request_path))
            completed=subprocess.run(command+[str(worker)],env=env,capture_output=True,text=True,
                                     timeout=runtime.get('timeout_seconds',3600),check=False)
            (cache/'worker_stdout.txt').write_text(completed.stdout)
            (cache/'worker_stderr.txt').write_text(completed.stderr)
            if completed.returncode:raise RuntimeError('Cold graph failed; diagnostics: '+str(cache))
            result=json.loads((cache/'artifacts'/'rebuild_result.json').read_text())
            if result.get('cache_key')!=key:raise ValueError('Rebuild key mismatch')
            import Part
            replacements={}
            for name,role in ROLES.items():
                record=result['roles'][role];p=Path(record['path'])
                if not p.resolve().is_relative_to((cache/'artifacts').resolve()) or p.is_symlink():raise ValueError('Unsafe rebuilt artifact path')
                if digest(p)!=record['sha256']:raise ValueError('Regenerated role hash mismatch')
                shape=Part.Shape();shape.read(str(p))
                if shape.isNull() or not shape.isValid() or len(shape.Solids)!=(4 if name=='PadReferences' else 1):
                    raise ValueError('Invalid regenerated '+name)
                if obj.Document.getObject(name) is None:raise ValueError('Missing document role '+name)
                replacements[name]=shape
            # All loads validate before the first mutation. Restore on assignment failure.
            previous={n:obj.Document.getObject(n).Shape.copy() for n in replacements}
            try:
                for name,shape in replacements.items():obj.Document.getObject(name).Shape=shape
            except Exception:
                for name,shape in previous.items():obj.Document.getObject(name).Shape=shape
                raise
            obj.BuiltKey=key;obj.ColdRebuild='GEOMETRY_REBUILT_UNVALIDATED'
            obj.FullParametersJSON=json.dumps(values,sort_keys=True,allow_nan=False)
            for name,role in ROLES.items():
                target=obj.Document.getObject(name)
                if hasattr(target,'SourceSHA256'):target.SourceSHA256=result['roles'][role]['sha256']
            obj.LastError='';obj.LastBuildDirectory=str(cache)
            # No automatic save, print release, re-export, or claim that downstream QA passed.
        except Exception as ex:
            obj.ColdRebuild='BLOCKED_OR_FAILED';obj.LastError=str(ex)
        finally:self.running=False
