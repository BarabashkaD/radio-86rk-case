"""Unexecuted FreeCAD helper: Radio86 recessed spherical lid pivots.
Dimensions mm. Import and run only by the owning FreeCAD MCP worker.
Returns candidate shapes, not a mechanically certified assembly.
Rebuilds the lid because the source lid contains barrel notches.
"""
import math
import FreeCAD as A
import Part

META = {}

def box(x0,x1,y0,y1,z0,z1):
    return Part.makeBox(x1-x0,y1-y0,z1-z0,A.Vector(x0,y0,z0))

def fuse(items):
    return items[0].multiFuse(items[1:]).removeSplitter() if len(items)>1 else items[0]

def round_edges(shape,r):
    # Fillet failure is reported; never claim a fillet which was not built.
    try:
        out=shape.makeFillet(r,shape.Edges)
        if out.isValid() and len(out.Solids)==1:return out
    except Exception as exc:
        META.setdefault('fillet_warnings',[]).append(str(exc))
    return shape

def rotate(shape,ay,az,angle):
    out=shape.copy();out.rotate(A.Vector(0,ay,az),A.Vector(1,0,0),-angle);return out

def side_support(xa,xb,ay,az,rear=-3.05):
    # Broad smoothly curved wall-thickness bump, with no neck or free ear.
    # Half cosine blends its rear envelope into the existing wall at +/-9mm.
    yz=[(-5.95,az-9), (rear,az-9)]
    for k in range(1,49):
        z=az-9+18*k/48
        y=rear+(ay+2.8-rear)*0.5*(1+math.cos(math.pi*(z-az)/9))
        yz.append((y,z))
    yz.append((-5.95,az+9))
    pts=[A.Vector(xa,y,z) for y,z in yz]
    return Part.Face(Part.makePolygon(pts+[pts[0]])).extrude(A.Vector(xb-xa,0,0))

def build(top, axis_y=-0.25, axis_z=21.0, height=37.5,
          wall=2.8, rear=-3.05, gap=.35, cut_sweep=True, source_has_old_hinge=False):
    """Build from source upper shell containing old hinge.

    cut_sweep removes only the candidate's conservative moving envelope.
    Review removal volume and all electronics before accepting. It may open
    a local clearance crescent under the hatch; inspect appearance closed/open.
    Root fillets must be inspected: this helper builds explicit cylindrical
    inside corner material but is not a substitute for stress validation.
    """
    global META
    META={'status':'Geometric candidate; see final validation reports; physical coupon required','fillet_warnings':[],
          'axis':[axis_y,axis_z], 'sphere_diameter':3.2,
          'socket_diameter':3.8,'spring_free_length':14.,
          'spring_thickness':1.2,'spring_width':4.,
          'nominal_max_deflection':.8,'root_radius':1.,
          'required_checks':['valid solids','old hardware completely removed',
          'minimum wall behind sockets','continuous boss connections',
          '0..180 sweep and minimum clearance','J4/DIN interference',
          'tool access and assembly path','printing and load coupons']}
    # Remove all original knuckles and their bridges, preserving side walls.
    clean=top.cut(box(118.49,178.51,-5.96,axis_y+3.3,17.9,24.1)) if source_has_old_hinge else top.copy()
    pane=box(119.15,177.85,-31.65,rear-gap,height-wall,height)
    skirt=box(121.15,175.85,rear-wall,rear-gap,18.35,height)
    # Free the inward-moving spherical tips from the rigid skirt before fusion.
    ball_clear=[]
    for cx,sign in [(119.85,1),(177.15,-1)]:
        c=A.Vector(cx,axis_y,axis_z);e=c+A.Vector(sign*.9,0,0)
        ball_clear.append(Part.makeSphere(1.8,c).fuse(Part.makeCylinder(1.8,.9,c,A.Vector(sign,0,0))).fuse(Part.makeSphere(1.8,e)))
    skirt=skirt.cut(Part.makeCompound(ball_clear))
    lid_parts=[pane,skirt]
    envelope_parts=[box(118.5,178.5,-32.,rear,height-wall-.35,height+.35),
                    box(120.8,176.2,rear-wall-.35,rear,18.,height+.35)]
    sphere_centres=[]
    # Outside faces119.15/177.85; free beam lies towards hatch centre.
    # Root ends14mm before pivot. Rear skirt must not weld spring tips.
    for left in (True,False):
        face=119.15 if left else 177.85
        xa,xb=(face,face+1.2) if left else (face-1.2,face)
        root_y=axis_y-14.
        root=box(xa,xb,root_y-3.,root_y,axis_z-2.,height-wall+.1)
        beam=box(xa,xb,root_y,axis_y+.25,axis_z-2.,axis_z+2.)
        # Round the beam root on the inner X/Y corner with a quarter-disc.
        # Keeps minimum straight beam thickness; physical free length follows
        # the fillet tangent, so check effective length in CAD after fusion.
        cx=xb+1.0 if left else xa-1.0
        disk=Part.makeCylinder(1.,4.,A.Vector(cx,root_y+1.,axis_z-2.))
        root_pad=box(xa if left else xa-1.,xb+1. if left else xb,
                     root_y,root_y+1.,axis_z-2.,axis_z+2.).cut(disk)
        centre=A.Vector(face+.7 if left else face-.7,axis_y,axis_z)
        ball=Part.makeSphere(1.6,centre)
        lid_parts += [root,beam,root_pad,ball]
        sphere_centres.append(centre)
        # Inflated boxes bound all moving components except the sphere,
        # whose socket supplies its clearance. Sampling1deg with0.35 envelope
        # bounds maximum angular step displacement for radius<40mm.
        envelope_parts += [box(xa-.35 if left else xa-1.35,xb+1.35 if left else xb+.35,root_y-3.35,root_y+1.35,
                                axis_z-2.35,height-wall+.45),
                           box(xa-.35,xb+.35,root_y-.35,axis_y+.60,
                                axis_z-2.35,axis_z+2.35)]
    hatch=fuse(lid_parts)
    # Finger opening is a recess, no projecting handle.
    hatch=hatch.cut(box(143,154,-31.75,-29.3,height-1.3,height+.1))
    bosses=[side_support(115.65,118.85,axis_y,axis_z,rear),
            side_support(178.15,181.05,axis_y,axis_z,rear)]
    combined=fuse([clean]+bosses)
    before=combined.Volume
    if cut_sweep:
        moving_envelope=fuse(envelope_parts)
        # Compound cutting avoids a very expensive union of181rotated solids.
        swept=Part.makeCompound([rotate(moving_envelope,axis_y,axis_z,a)
                                 for a in range(181)])
        combined=combined.cut(swept)
    for centre in sphere_centres:
        combined=combined.cut(Part.makeSphere(1.9,centre))
    combined=combined.removeSplitter()
    META.update({'removed_clearance_volume_mm3':before-combined.Volume,
                 'top_valid':combined.isValid(),'top_solids':len(combined.Solids),
                 'hatch_valid':hatch.isValid(),'hatch_solids':len(hatch.Solids),
                 'maximum_rear_y':axis_y+2.8,
                 'caution':'Finishing is applied by hinge_snap_finish and latch_v08. Geometric checks do not establish printed strength, force or service life.'})
    return combined,hatch,META

def modify(top,hatch,axis_y,axis_z):
    """Drop-in return signature for old hinge_v02.modify; latch must be reapplied.
    This reconstructs the lid and therefore removes the old latch geometry.
    """
    upper,lid,meta=build(top,axis_y,axis_z)
    empty=Part.Shape()
    return upper,lid,empty,empty
