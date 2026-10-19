"""Preserve accepted v09 foot/pad coordinates in the widened v10 shell.
Legacy Width below is ONLY the original foot layout span. It does not alter
any dimension of the supplied v10 shell. Exact returned axes are asserted.
"""
import FreeCAD as A,Part
from v10_parameters import DEFAULT,FEET_AXES
import feet_v10_geometry as legacy
PAD_CENTRES=((10.7,-204.),(268.7,-204.),(10.7,-18.05),(268.7,-18.05))
def build(base,angle=0.):
 q=base.copy();checks=[]
 intended=Part.makeCompound([Part.makeCylinder(5.2,2.,A.Vector(x,y,-1.)) for x,y in PAD_CENTRES])
 # Reject an accidental widened-layout recess rather than silently filling it.
 # Existing approved recesses are excluded from this diagnostic, as they
 # partially overlap the unwanted locations despite having different centres.
 for x,y in [(4.7,-204.),(274.7,-204.),(4.7,-18.05),(274.7,-18.05)]:
  probe=Part.makeCylinder(5.19,.98,A.Vector(x,y,.01));missing=probe.cut(q).cut(intended).Volume
  checks.append({'xy':[x,y],'unexpected_recess_volume':missing})
  if missing>.001:raise ValueError('Existing unintended Width300 pad recess at '+str((x,y)))
 for x,y in PAD_CENTRES:q=q.cut(Part.makeCylinder(5.2,2.,A.Vector(x,y,-1.)))
 pp={'Width':288.,'Floor':DEFAULT.Floor,'FrontY':-219.,'RearY':-3.05,'PCBTop':DEFAULT.PCBTopZ,'FootAngle':angle}
 out=legacy.build_foldout_feet(q,parameters=pp,angle=angle)
 assert all(abs(a-b)<1e-8 for old,new in zip(out['meta']['axes'],FEET_AXES) for a,b in zip(old,new))
 out['meta']['v10_preserved_absolute_axes']=True;out['meta']['actual_case_width']=DEFAULT.Width;out['meta']['legacy_layout_span_only']=288.;out['meta']['fixed_pad_centres']=PAD_CENTRES;out['meta']['pad_recess_radius']=5.2;out['meta']['pad_recess_topZ']=1.;out['meta']['unintended_recess_checks']=checks
 return out
