"""Pure lower grid layout driven by the current ventilation and minimum rib pitch."""
import math

def layout(p,anchors,normal_pitch):
    if not anchors or not math.isfinite(normal_pitch) or normal_pitch<=0:raise ValueError('Invalid rib layout')
    slope=1/math.tan(math.radians(p.SideSlotAngle))
    step=math.ceil((normal_pitch/math.sin(math.radians(p.SideSlotAngle))-1e-9)/p.SideSlotPitch)*p.SideSlotPitch
    levels=list(anchors);y=anchors[0]-step
    while y>=-216.2-294.4*slope:levels.append(y);y-=step
    y=anchors[-1]+step
    while y<=-5.85:levels.append(y);y+=step
    lines=[]
    for side in (1,-1):
        x=-7.5 if side==1 else 286.9
        for y in sorted(set(levels)):
            if abs(slope)<1e-8:
                if side==-1 or not -216.2<=y<=-5.85:continue
                d0,d1=0,294.4
            else:d0=max(0,(-216.2-y)/slope);d1=min(294.4,(-5.85-y)/slope)
            if d1>d0:lines.append(((x+side*d0,y+d0*slope),(x+side*d1,y+d1*slope)))
    return lines,step
