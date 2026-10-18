"""Small unexecuted CAD finishing helper, for the owning MCP worker only.
Call after hinge_snap_candidate.build and before latch finishing. Dimensions mm.
Opening150..180deg gives direct access to the outside faces of spring arms;
no release hole is bored through a spherical socket.
"""
import FreeCAD as A
import Part

def box(x0,x1,y0,y1,z0,z1):
    return Part.makeBox(x1-x0,y1-y0,z1-z0,A.Vector(x0,y0,z0))

def prism_xy(points,z0,z1):
    vs=[A.Vector(x,y,z0) for x,y in points]
    return Part.Face(Part.makePolygon(vs+[vs[0]])).extrude(A.Vector(0,0,z1-z0))

def finish(top,hatch,axis_y=-.25,axis_z=21.,rear=-3.05,wall=2.8):
    # Gentle insertion ramps outside the working spherical depression.
    # Face-socket intersection ends atdy~1.616; ramps begin atdy1.70.
    lead=[]
    for face,sign in [(118.85,-1),(178.15,1)]:
        lead.append(prism_xy([(face,axis_y+1.70),
                              (face,axis_y+3.70),
                              (face+sign*.90,axis_y+3.70)],
                             axis_z-2.1,axis_z+2.1))
    top=top.cut(Part.makeCompound(lead))
    # Rigid rails anchored to the existing central rear skirt. Their nearest
    # surfaces limit nominal tip motion0.90mm at beam station12/14.
    # Stop gap=delta*s^2*(3L-s)/(2L^3)=0.70845. Keep clear of full sphere.
    rails=[]
    stop_gap=.9*12.**2*(3*14.-12.)/(2*14.**3)
    for xa,xb in [(120.35+stop_gap,123.05),(173.95,176.65-stop_gap)]:
        rail=box(xa,xb,rear-wall-.05,axis_y-2.,axis_z-1.7,axis_z+1.7)
        # Top access notch: keeps the lower rail web and end travel stop.
        # Open from above when detached; inspect with a2.5mm spudger envelope.
        notch=box(xa-.05,xb+.05,axis_y-4.8,axis_y-2.3,axis_z+.4,axis_z+1.8)
        rails.append(rail.cut(notch))
    hatch=hatch.multiFuse(rails).removeSplitter()
    meta={'release_pose_degrees':[150,180],
          'release_action':'Push outer arm faces inward at2.5..5mm from ball centre; do not lever against socket lip.',
          'tool_blade_width_mm':2.5,'travel_stop_local_gap_mm':stop_gap,
          'stop_station_mm':12.,'nominal_tip_stop_mm':.9,
          'entry_ramp_run_mm':2.,'entry_ramp_depth_mm':.9,
          'entry_ramp_angle_deg':24.2,
          'caution':'CAD and printed access check required. Rails must be included in0..180 sweep.'}
    return top.removeSplitter(),hatch,meta
