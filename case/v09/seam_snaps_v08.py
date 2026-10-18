"""PROPOSED geometry helper; never imported/executed against CAD by its author.

modify(lower, upper, p) -> (lower, upper, diagnostic_dict)
Needs FreeCAD/Part in the caller. Keep four existing shell screws.
First restrict the old registration lip AND its groove to front/rear 8 mm
bands (see INTEGRATION_RU.md). Do not apply over the old full side groove.
All snap dimensions are coupon candidates, NOT PCTG strength allowables.
"""
import math


def modify(lower, upper, p):
    import FreeCAD as App
    import Part
    V = App.Vector
    t = float(p.Wall)
    z = float(p.SeamZ)
    x0, x1 = 139.7-float(p.Width)/2, 139.7+float(p.Width)/2
    yf, yr = float(p.FrontY), float(p.RearY)
    if abs(t-2.8) > 1e-6:
        raise ValueError('Proposed seam is dimensioned for Wall=2.8; redesign for other walls.')
    centres = (-150., -70.)
    exclusions = [(-204., -192.), (-30., -18.)]  # existing shell screw bosses
    report = {'status': 'unvalidated_proposal', 'snaps': [],
              'side_span_y': [yf+8, yr-8], 'screw_exclusions_y': exclusions,
              'lip_uv': [1.6, 2.8], 'lip_z': [z-.10, z+2.4],
              'groove_uv': [1.3, 3.1], 'groove_top_z': z+2.7,
              'nominal_root_strain_simple_beam': 1.5*1.2*.7/20**2,
              'warning': 'No material allowable or fatigue rating; physical coupon required.'}

    def local_box(left, u0, u1, y0, y1, z0, z1):
        xa, xb = (x0+u0, x0+u1) if left else (x1-u1, x1-u0)
        return Part.makeBox(xb-xa, y1-y0, z1-z0, V(xa, y0, z0))

    def prism(left, points_uz, ya, yb):
        pts = [V(x0+u if left else x1-u, ya, zz) for u, zz in points_uz]
        return Part.Face(Part.makePolygon(pts+[pts[0]])).extrude(V(0, yb-ya, 0))

    def fuse(shapes):
        return shapes[0].multiFuse(shapes[1:]) if len(shapes)>1 else shapes[0]

    def segments(a, b, holes):
        intervals = [(a,b)]
        for lo, hi in holes:
            nxt=[]
            for aa,bb in intervals:
                if hi <= aa or lo >= bb: nxt.append((aa,bb))
                else:
                    if aa < lo: nxt.append((aa,lo))
                    if hi < bb: nxt.append((hi,bb))
            intervals=nxt
        return intervals

    lower_add, upper_add, lower_cuts, upper_cuts = [], [], [], []
    for left in (True, False):
        side='left' if left else 'right'
        # The tongue is a continuous rail carried periodically by the existing
        # louver tops. Its bottom overlaps them by 0.30 mm (tops at Z10.2).
        # At solid sidewall sections overlap is 0.10 mm. This closes the top
        # 0.10 mm of side intake locally within u1.6..2.8; explicit tradeoff.
        root_holes=[(yc-13.2,yc-8.8) for yc in centres]
        all_holes=exclusions+root_holes
        for ya,yb in segments(yf+8,yr-8,all_holes):
            # 0.3-mm entrance bevel on the inward upper edge.
            tongue=prism(left,[(1.6,z-.1),(2.8,z-.1),(2.8,z+2.1),
                               (2.5,z+2.4),(1.6,z+2.4)],ya,yb)
            lower_add.append(tongue)
        for ya,yb in segments(yf+8,yr-8,exclusions):
            upper_cuts.append(local_box(left,1.3,3.1,ya,yb,z-.05,z+2.7))

        # Local underside gusset strengthens short partial louver support at Y-163.2.
        xa,xb=(x0+1.6,x0+2.8) if left else (x1-2.8,x1-1.6)
        pp=[V(xa,-170,8.6),V(xa,-163.2,9.9),V(xa,-163.2,10.05),V(xa,-170,10.05)]
        lower_add.append(Part.Face(Part.makePolygon(pp+[pp[0]])).extrude(V(xb-xa,0,0)))
        report['local_support_gusset']={'y':[-170,-163.2],'u':[1.6,2.8],'max_intake_projection_reduction_each_mm2':4.42}

        for yc in centres:
            a,b=yc-10,yc+10
            hook_a,hook_b=b-3,b
            # Local lower catch: 1.2-mm high bridge above a through pocket.
            catch=local_box(left,1.6,2.8,b-5,b+2,z-.1,z+3.2)
            pocket=local_box(left,1.3,3.1,hook_a-.3,hook_b+.3,z+.2,z+2.)
            lower_add.append(catch.cut(pocket))
            # Remove the ordinary rail in exactly the same latch pocket.
            lower_cuts.append(pocket)
            upper_cuts.append(local_box(left,1.3,3.1,b-5.3,b+2.3,z-.05,z+3.5))
            # Horizontal cantilever, root at a, free tip at b, bending inward.
            arm=local_box(left,3.2,4.4,a,b,z+.6,z+3.8)
            root=local_box(left,.8,5.2,a-3,a,z+.6,z+4.6)
            # Analytic concave fillets in XY on both beam-root corners.
            fillets=[]
            for ua,ub,cu in [(2.4,3.2,2.4),(4.4,5.2,5.2)]:
                sq=local_box(left,ua,ub,a,a+.8,z+.6,z+3.8)
                cx=x0+cu if left else x1-cu
                circle=Part.makeCylinder(.8,3.4,V(cx,a+.8,z+.5),V(0,0,1))
                fillets.append(sq.cut(circle))
            # Hook lead-in is 45 degrees, retaining face horizontal at z+1.8.
            hook=prism(left,[(3.2,z+.6),(3.2,z+1.8),
                             (2.4,z+1.8),(2.4,z+1.4)],hook_a,hook_b)
            pad=local_box(left,3.2,4.4,hook_a,hook_b,z+3.7,z+4.4)
            upper_add.append(fuse([arm,root,hook,pad]+fillets))
            # Tool enters above the catch (top z+3.2), never through its bridge.
            # Cutter stops before arm u3.2. Press INWARD, by approx 0.7 mm.
            access=local_box(left,-.2,3.0,hook_a-.3,hook_b+.3,z+3.3,z+4.6)
            upper_cuts.append(access)
            report['snaps'].append({'side':side,'centre_y':yc,
                'root_y':a,'free_end_y':b,'beam_uv':[3.2,4.4],
                'beam_z':[z+.6,z+3.8], 'hook_y':[hook_a,hook_b],
                'catch_underside_z':z+2.,'hook_top_z':z+1.8,
                'axial_latch_play':.2,'nominal_engagement':.4,
                'nominal_inward_release':.7,'root_radius':.8,
                'release_window_y':[hook_a-.3,hook_b+.3],
                'release_window_z':[z+3.3,z+4.6],
                'root_interruption_y':[a-3.2,a+1.2]})

    # Cut original upper first, then fuse new arms. Do not cut arms with their
    # own release-window/groove tools. Lower pockets cut both rail and catch.
    upper=upper.cut(fuse(upper_cuts))
    lower=fuse([lower]+lower_add).cut(fuse(lower_cuts))
    upper=fuse([upper]+upper_add)
    lower,upper=lower.removeSplitter(),upper.removeSplitter()
    report['lower_valid']=lower.isValid()
    report['upper_valid']=upper.isValid()
    report['lower_solids']=len(lower.Solids)
    report['upper_solids']=len(upper.Solids)
    report['final_intersection_volume']=lower.common(upper).Volume
    # Diagnostics deliberately do not claim a successful assembly or flexure.
    return lower,upper,report
