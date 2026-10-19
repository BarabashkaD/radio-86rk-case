"""Canonical tessellation helper.
Upper uses isolated official Gmsh on the unchanged source BREP; all other roles
use Netgen. Geometry and complete mesh audit remain separate mandatory gates.
"""
import hashlib
import json
import os
import re
from pathlib import Path
import subprocess
import uuid

SETTINGS={'min_length':.08,'max_length':3.,'curvature_points':32,'algorithm':'front2d','threads':1}
NETGEN={'Fineness':2,'SecondOrder':0,'Optimize':1,'MaxLength':3.,'MinLength':.08}
def gmsh_log_failures(text):
    return [line for line in text.splitlines() if re.search(r'(?:^\s*Error\s*:|No elements in surface|Failed to recover boundary mesh|MISSING_SURFACE)',line,re.IGNORECASE)]

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def export(shape,role,path,*,runtime,gmsh_binary,gmsh_sha256,compare_geometry,filter_zero_area,source_brep_sha256=None,reuse_helper=None):
    path=Path(path)
    if path.exists() or path.is_symlink():raise ValueError('Canonical STL must be fresh')
    if shape.isNull() or not shape.isValid() or len(shape.Solids)!=1:raise ValueError('Expected valid single print solid')
    config=runtime.get('canonical_mesh_reuse')
    if role=='upper' and config is not None:
        if reuse_helper is None or not isinstance(source_brep_sha256,str):raise ValueError('Reuse requires verified input BREP SHA and pinned helper')
        return reuse_helper.export_reused(config,path,source_brep_sha256=source_brep_sha256,gmsh_sha256=gmsh_sha256)
    import Mesh,MeshPart
    if role!='upper':
        mesh=MeshPart.meshFromShape(Shape=shape,**NETGEN)
        if mesh.CountFacets<=0:raise ValueError('Empty Netgen mesh')
        mesh.write(str(path));saved=Mesh.Mesh(str(path))
        if saved.CountFacets!=mesh.CountFacets:raise ValueError('STL roundtrip failed')
        return {'engine':'Netgen','settings':NETGEN,'facets':saved.CountFacets,'stl_sha256':sha(path),'audit':'PENDING_FULL_TOPOLOGY_AND_SELF_INTERSECTIONS'}
    binary=Path(gmsh_binary)
    if not binary.is_file() or sha(binary)!=gmsh_sha256:raise ValueError('Unverified bundled Gmsh binary')
    wrapper=Path(runtime['command'][0]);expected=binary.parents[2]/'AppRun'
    if wrapper.resolve()!=expected.resolve():raise ValueError('Gmsh must use the same verified official AppRun')
    cache=Path(runtime['cache_root']).resolve();run=cache/('canonical-upper-mesh-'+uuid.uuid4().hex);run.mkdir(parents=True,exist_ok=False)
    source=run/'source.brep';shape.exportBrep(str(source))
    # Direct meshing preserves source topology and avoids an unnecessary normalization.
    target=source
    raw=run/'upper_raw.stl'
    command=[str(wrapper),'gmsh',str(target),'-2','-format','stl','-bin','-clmin','.08','-clmax','3','-clcurv','32','-algo','front2d','-nt','1','-o',str(raw)]
    profile=run/'profile';profile.mkdir();env=dict(os.environ)
    for key,folder in [('HOME','home'),('XDG_CONFIG_HOME','config'),('XDG_DATA_HOME','data'),('XDG_CACHE_HOME','cache')]:
        directory=profile/folder;directory.mkdir();env[key]=str(directory)
    result=subprocess.run(command,capture_output=True,text=True,env=env,timeout=runtime.get('timeout_seconds',7200),check=False)
    (run/'stdout.log').write_text(result.stdout);(run/'stderr.log').write_text(result.stderr)
    if result.returncode!=0 or not raw.is_file():raise ValueError('Gmsh failed; diagnostic directory '+str(run))
    issues=gmsh_log_failures(result.stdout+'\n'+result.stderr)
    if issues:raise ValueError('Gmsh incomplete surface mesh: '+json.dumps(issues)+'; diagnostic '+str(run))
    filtered=filter_zero_area(raw,path)
    if hasattr(filtered,'to_dict'):filtered=filtered.to_dict()
    saved=Mesh.Mesh(str(path))
    if saved.CountFacets<=0:raise ValueError('Empty canonical Gmsh mesh')
    report={'engine':'Gmsh','binary_sha256':gmsh_sha256,'settings':SETTINGS,'source_brep_sha256':sha(source),'mesh_input_brep_sha256':sha(target),'source_preprocessing':'NONE_DIRECT_SOURCE_BREP','zero_area_filter':filtered,'facets':saved.CountFacets,'stl_sha256':sha(path),'diagnostic_directory':str(run),'audit':'PENDING_FULL_TOPOLOGY_AND_SELF_INTERSECTIONS'}
    (run/'provenance.json').write_text(json.dumps(report,indent=2)+'\n')
    return report
