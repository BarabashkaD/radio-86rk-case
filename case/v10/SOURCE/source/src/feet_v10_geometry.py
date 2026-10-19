"""v10 integration: preserve exact v09 feet geometry without global same-domain refinement.
Refinement on the detailed reinforced shell can damage unrelated pcurves.
"""
"""Radio86 v08: recessed spherical snap feet, CAD candidate, mm.
Execute this helper only through the authorised FreeCAD MCP writer.
Supply the CLEAN lower shell before any old feet_v02 modification. No old
bolt bore, external knuckle, nut pocket or side-entry channel is reproduced.
Two inclined rigid seats have concurrent ideal reaction lines on the nominal
desk-reaction line; spheres and flexible ears are retention, not a claimed
load-rated bearing. Real contact/load distribution still needs a physical test.
"""
import math
import json
import FreeCAD as A
import Part


def box(x0,x1,y0,y1,z0,z1):
    return Part.makeBox(x1-x0,y1-y0,z1-z0,A.Vector(x0,y0,z0))

def fuse(ss):
    ss=[s for s in ss if not s.isNull()]
    return ss[0].multiFuse(ss[1:]) if len(ss)>1 else ss[0]

def yz(x0,x1,points):
    pp=[A.Vector(x0,y,z) for y,z in points]
    return Part.Face(Part.makePolygon(pp+[pp[0]])).extrude(A.Vector(x1-x0,0,0))

def cylx(x0,x1,y,z,r):
    return Part.makeCylinder(r,x1-x0,A.Vector(x0,y,z),A.Vector(1,0,0))

def cylz(x,y,z0,z1,r):
    return Part.makeCylinder(r,z1-z0,A.Vector(x,y,z0))

def rotated(s,x,y,z,a):
    q=s.copy();q.rotate(A.Vector(x,y,z),A.Vector(1,0,0),a);return q

def rotate_points(pp,a):
    c,s=math.cos(math.radians(a)),math.sin(math.radians(a))
    return [(y*c-z*s,y*s+z*c) for y,z in pp]

def get(p,n,d):
    return float(p.get(n,d) if isinstance(p,dict) else getattr(p,n,d)) if p is not None else d

def unit(v):
    m=math.hypot(*v);return (v[0]/m,v[1]/m)

def plus(p,v,a):return (p[0]+a*v[0],p[1]+a*v[1])


def engineering_geometry(front=-219., rear=-3.05):
    ay=rear-31.95;az=2.5
    pad_z=-3.0;sole_y=ay+6.3;sole_z=-17.0
    slope=14.0/(sole_y-(front+15.0))
    # Intersection of the ideal contact-reaction lines, relative to the axis.
    concurrency=(6.3+(az-sole_z)*slope,0.)
    p1=(-.5,1.1);p2=(1.3,-1.1)
    n1=unit((p1[0]-concurrency[0],p1[1]))
    n2=unit((concurrency[0]-p2[0],-p2[1]))
    t1=(n1[1],-n1[0]);t2=(n2[1],-n2[0])
    alo,ahi=plus(p1,t1,-1.),plus(p1,t1,1.)
    bhi,blo=plus(p2,t2,-.7),plus(p2,t2,.7)
    cam=rotate_points([alo,ahi,bhi,blo,(.7,-1.2)],-105.)
    # Small internal relief avoids premature contact with seat B at 0..3 deg.
    cam=[cam[0],cam[1],(1.15,-.35)]+cam[2:]
    fixed_a=[(-3.,alo[1]),alo,ahi,(ahi[0],4.2),(-3.,4.2)]
    fixed_b=[bhi,blo,(3.0,blo[1]),(3.0,4.2),(2.6,4.2),(2.6,bhi[1])]
    return dict(axis_y=ay,axis_z=az,pad_z=pad_z,sole_y=sole_y,sole_z=sole_z,
                slope=slope,tilt_deg=math.degrees(math.atan(slope)),
                cam=cam,seat_a=fixed_a,seat_b=fixed_b,
                contacts=[dict(endpoints=[alo,ahi],normal=n1,area_mm2=36.),
                          dict(endpoints=[bhi,blo],normal=n2,area_mm2=25.2)],
                force_concurrency=concurrency)


def layout_audit(parameters, centres, front, rear):
    """BBox screening only; no false claim of exact imported-solid clearance."""
    raw=parameters.get('LayoutData') if isinstance(parameters,dict) else getattr(parameters,'LayoutData',None)
    if not raw:return {'status':'LayoutData absent; exact electronics screening required.'}
    data=json.loads(raw) if isinstance(raw,str) else raw
    pcb=get(parameters,'PCBTop',14.6);ay=rear-31.95
    entries=[]
    for i,xc in enumerate(centres):
        roof=(xc-15.1,xc+15.1,ay-22.6,ay+5.,6.7)
        under=[]
        for ref,b in data['components'].items():
            if b[0]<roof[1] and b[3]>roof[0] and b[1]<roof[3] and b[4]>roof[2]:
                under.append({'ref':ref,'bbox_bottom_z':b[2]+pcb,
                              'roof_vertical_gap_mm':b[2]+pcb-roof[4]})
        under.sort(key=lambda q:q['roof_vertical_gap_mm'])
        entries.append({'foot':i,'roof_bbox':list(roof),'components_above':under,
                        'minimum_bbox_vertical_gap_mm':under[0]['roof_vertical_gap_mm'] if under else None})
    return {'status':'Analytic component BBoxes only; exact BRep checks remain.',
            'cassettes':entries,
            'ribs':'X45/X235 ribs meet the cassette roofs. Cuts stop at Z5.1; roof remains to Z6.7 and fuses to the existing rib above it. X140 and Y-75/-110/-145/-180 ribs are outside the cavities.'}


def build_foldout_feet(base,parameters=None,angle=None,detents=True):
    """Replacement API for feet_v02. No CAD is run merely by importing.

    Returns the four legacy integration roles plus reference geometries/meta.
    FootHardware is intentionally null: remove the old hardware document role.
    FoldFeetCore is a reference with detent bumps omitted, for rigid sweep QA.
    Full FoldFeet intentionally requires up to ~0.3 mm elastic inward ear
    deflection while traversing the shallow detents; do not interpret those
    local cam overlaps as permission to carve away the structural cheeks.
    """
    if base.BoundBox.ZMin < -.05:
        raise ValueError('Pass the clean pre-feet lower shell, not the saved shell containing old external feet/bolt channels.')
    if abs(get(parameters,'Floor',3.)-3.)>1e-6:
        raise ValueError('This candidate is defined for a 3 mm source floor.')
    width=get(parameters,'Width',288.);x0=139.7-width/2.;x1=139.7+width/2.
    front=get(parameters,'FrontY',-219.);rear=get(parameters,'RearY',-3.05)
    if angle is None:angle=get(parameters,'FootAngle',0.)
    if angle<0 or angle>105:raise ValueError('Display angle is limited to 0..105 deg.')
    g=engineering_geometry(front,rear);ay=g['axis_y'];az=g['axis_z']
    centres=[x0+44.3,x1-44.3]
    additions=[];cuts=[];seats=[];fixed_pads=[]
    full_folded=[];core_folded=[];rigid_folded=[];ear_references=[]
    socket_tools=[];detent_tools=[]

    # Preserve the existing v07 contact-pad height; the prohibition on exposed
    # hinges does not silently change the separately chosen rubber-pad height.
    for xx,yy in [(x0+15,front+15),(x1-15,front+15),(x0+15,rear-15),(x1-15,rear-15)]:
        # Keep the original blind recess: no printed pedestal below Z0.
        fixed_pads.append(cylz(xx,yy,-3.,1.,5.))

    for xc in centres:
        # Blind underside cavity, continuously covered by 1.6 mm of material.
        additions.append(box(xc-15.1,xc+15.1,ay-22.6,ay+5.,2.9,6.7))
        cuts.append(box(xc-11.7,xc+11.7,ay-21.8,ay+2.6,-.2,5.1))
        # The back wall beyond Y+2.6 supplies the seat-B load path.
        for polygon in [g['seat_a'],g['seat_b']]:
            seats.append(yz(xc-9.,xc+9.,[(ay+y,az+z) for y,z in polygon]))

        body_profile=[(-20.5,-2.2),(-20.5,.2),(-5.,.2),(-3.,-.5),(-3.,-2.2)]
        blade=yz(xc-9.,xc+9.,[(ay+y,az+z) for y,z in body_profile])
        cam=yz(xc-9.,xc+9.,[(ay+y,az+z) for y,z in g['cam']])
        neck=yz(xc-9.,xc+9.,[(ay+y,az+z) for y,z in
                    [(-3.2,-2.2),(-3.2,-.5),(-1.2,-.30),(-2.05,-.85)]])
        # A short thick root, ahead of the free spring length, connects each
        # ear to the blade. No other bridge bonds the 16 mm free ear to it.
        anchor=box(xc-11.4,xc+11.4,ay-20.5,ay-17.2,.3,4.5)
        rigid=fuse([blade,cam,neck,anchor])
        ears=[];bumps=[]
        for side in [-1,1]:
            inner=xc+side*10.;outer=xc+side*11.4
            beam_x=sorted((inner,outer))
            beam=box(beam_x[0],beam_x[1],ay-17.2,ay,.5,4.5)
            terminal=cylx(beam_x[0],beam_x[1],ay,az,2.)
            # Analytic R1.2 concave root blend, with the free tangent at Y-16.
            fx0,fx1=sorted((xc+side*8.8,xc+side*10.0))
            blend=box(fx0,fx1,ay-17.2,ay-16.,.5,4.5).cut(
                cylz(xc+side*8.8,ay-16.,.4,4.6,1.2))
            sphere_centre=A.Vector(xc+side*10.4,ay,az)
            cap=Part.makeSphere(2.,sphere_centre)
            if side>0:
                cap=cap.common(box(xc+11.25,xc+12.5,ay-2.1,ay+2.1,az-2.1,az+2.1))
            else:
                cap=cap.common(box(xc-12.5,xc-11.25,ay-2.1,ay+2.1,az-2.1,az+2.1))
            ear=fuse([beam,terminal,blend,cap]);ears.append(ear)
            socket=Part.makeSphere(2.3,sphere_centre);socket_tools.append(socket)
            # Separate elastic index cam; the principal spherical end remains
            # the pivot. Recesses are present at the two unloaded end states.
            bump=Part.makeSphere(.7,A.Vector(outer,ay-1.5,az));bumps.append(bump)
            for endpoint in [0.,105.]:
                yy,zz=rotate_points([(-1.5,0.)],endpoint)[0]
                detent_tools.append(Part.makeSphere(.9,A.Vector(outer,ay+yy,az+zz)))
            # 3 x 3 mm underside-only service access at Y-6..-3.
            sx0,sx1=sorted((xc+side*11.7,xc+side*14.8))
            cuts.append(box(sx0,sx1,ay-6.,ay-3.,-.2,4.7))
        core=fuse([rigid]+ears)
        full=fuse([core]+bumps) if detents else core

        # A flat, desk-parallel sole is derived in the deployed state, then
        # transformed back; no detached drawing geometry is substituted.
        def sole_z(y):return g['sole_z']-g['slope']*(y-g['sole_y'])
        ymin,ymax=ay-30,ay+30
        below=yz(xc-15,xc+15,[(ymin,-50),(ymax,-50),(ymax,sole_z(ymax)),(ymin,sole_z(ymin))])
        ya,yb=ay+5.1,ay+7.5
        toe=yz(xc-9,xc+9,[(ya,sole_z(ya)),(yb,sole_z(yb)),
                          (yb,sole_z(yb)+.8),(ya,sole_z(ya)+.8)])
        # Only the sole end is flattened. The cam and side spring roots are
        # far above this plane in the open position and stay unchanged.
        def finish(shape):
            op=rotated(shape,xc,ay,az,105.).cut(below)
            op=fuse([op,toe])
            folded=rotated(op,xc,ay,az,-105.)
            # Trim the small toe-platform overhang to the Z0.3 blade datum.
            # Leave the cam heel alone: it may descend to Z0.2 by design.
            folded=folded.cut(box(xc-12,xc+12,ay-23.,ay-15.,-2.,.3))
            return folded
        full_folded.append(finish(full));core_folded.append(finish(core))
        rigid_folded.append(finish(rigid))
        ear_references.append(Part.makeCompound(ears))

    lower=fuse([base.copy()]+additions).cut(fuse(cuts))
    lower=fuse([lower]+seats)
    lower=lower.cut(fuse(socket_tools))
    if detents:lower=lower.cut(fuse(detent_tools))
    # Lower mouth relief; does not cut seat B whose lowest datum is Z0.709646.
    for xc in centres:
        lower=lower.cut(yz(xc-11.75,xc+11.75,[(ay+2.59,-.20),(ay+3.45,-.20),(ay+2.59,.66)]))
        for xa,xb in [(xc-11.75,xc-9.1),(xc+9.1,xc+11.75)]:
            lower=lower.cut(yz(xa,xb,[(ay+2.59,-.20),(ay+3.64,-.20),(ay+2.59,.85)]))
    lower=lower
    def state(ss,a):return Part.makeCompound([rotated(s,x,ay,az,a) for s,x in zip(ss,centres)])
    audit=layout_audit(parameters,centres,front,rear)
    meta={
        'revision':'v08 recessed spherical snap-foot candidate',
        'axes':[[x,ay,az] for x in centres],
        'angle_deg':float(angle),'hard_stop_deg':105.,
        'sphere_diameter_mm':4.,'socket_sphere_diameter_mm':4.6,
        'nominal_radial_socket_clearance_mm':.3,'spherical_segment_mm':1.,
        'ear_to_cheek_side_gap_mm':.3,'nominal_spherical_engagement_mm':.7,
        'blind_socket_depth_mm':1.,'material_behind_socket_mm':2.4,
        'ear_free_length_mm':16.,'ear_thickness_x_mm':1.4,
        'ear_width_z_mm':4.,'root_radius_mm':1.2,
        'assembly_inward_deflection_candidate_mm':.8,
        'inward_rigid_travel_limit_candidate_mm':1.,
        'unloaded_ear_spring_assumption':'No intentional permanent assembly preload; end detents are relieved.',
        'contact_faces':g['contacts'],'contact_force_line_intersection_yz':g['force_concurrency'],
        'nominal_rigid_contact_gap_mm':0.,
        'nominal_foot_station_lift_mm':14.,'case_tilt_deg':g['tilt_deg'],
        'sole_contact_width_mm':18.,'sole_contact_depth_mm':2.4,
        'fixed_pad_bottom_z_mm':-3.,'fixed_pad_top_z_mm':1.,
        'fixed_pad_envelope_thickness_mm':4.,'printed_lower_shell_minimum_z_mm':0.,
        'folded_blade_z_mm':[.3,2.7],'folded_ears_z_mm':[.5,4.5],
        'heel_minimum_candidate_z_mm':.2,
        'cassette_width_mm':30.2,'cassette_length_mm':27.6,
        'underside_cavity_top_z_mm':5.1,'continuous_roof_top_z_mm':6.7,
        'minimum_nominal_roof_mm':1.6,
        'no_side_bolt_channels':True,'no_bottom_ventilation_passage':True,
        'obsolete_document_roles':['FootHardware'],
        'detents_enabled':bool(detents),
        'detent_validation':'Full foot has intentional elastic cam interference between the end recesses; use FoldFeetCore for rigid interference QA and separately quantify ear displacement.',
        'layout_bbox_audit':audit,
        'limits':[
            'Nominal contact concurrence is ideal planar statics, not proof of FFF load capacity or full real-world sphere unloading.',
            'Contact forces are amplified by the compact geometry. Load, PCTG grade, layer strength, creep and service life are unknown.',
            'R1.2 root, 0.8 mm assembly deflection and detent travel require an isolated printed coupon before an enclosure print.',
            'Exact BRep electronics clearance, connected solids, full motion, desk contacts and assembly/service access remain for the sole MCP writer.',
            'The 3 mm rubber-pad projection is preserved. Separate 4 mm elastomer envelopes occupy the original 1 mm blind recesses; there are no printed pedestals below Z0. Elastomer/adhesive selection is unverified.',
            'Soles have no modeled elastomer overlay; grip and pad selection remain unverified.',
        ],
    }
    return {'LowerShell':lower,'FoldFeet':state(full_folded,angle),
            'Feet':Part.makeCompound(fixed_pads),'FootHardware':Part.Shape(),
            'FoldFeetFolded':state(full_folded,0.),'FoldFeetDeployed':state(full_folded,105.),
            'FoldFeetCore':state(core_folded,angle),
            'individual_folded':full_folded,'individual_core_folded':core_folded,
            'individual_rigid_folded':rigid_folded,'ear_reference_folded':ear_references,
            'meta':meta}

build_feet=build_foldout_feet
