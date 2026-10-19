"""Proposed GUI-independent constraint resolution; not yet wired to CAD build."""
import math
MODES={'height_bottom','top_bottom','height_top'}

def resolve(values,mode='height_bottom'):
    if mode not in MODES:raise ValueError('Unknown ventilation driver mode')
    out=dict(values)
    required=['SideSeamZ','Floor','SideSlotExternalWidth','SideSlotPitch','SideSlotAngle']
    required+= {'height_bottom':['SideSlotHeight','SideSlotBottomMargin'],
                'top_bottom':['SideSlotTopMargin','SideSlotBottomMargin'],
                'height_top':['SideSlotHeight','SideSlotTopMargin']}[mode]
    for name in required:
        if name not in out or not math.isfinite(float(out[name])):raise ValueError('Missing/nonfinite '+name)
        out[name]=float(out[name])
    seam=out['SideSeamZ']
    if mode=='height_bottom':derived='SideSlotTopMargin';out[derived]=seam-out['SideSlotHeight']-out['SideSlotBottomMargin']
    elif mode=='top_bottom':derived='SideSlotHeight';out[derived]=seam-out['SideSlotTopMargin']-out['SideSlotBottomMargin']
    else:derived='SideSlotBottomMargin';out[derived]=seam-out['SideSlotHeight']-out['SideSlotTopMargin']
    if not (0<out['SideSlotExternalWidth']<out['SideSlotPitch'] and 0<out['SideSlotAngle']<=90
            and out['SideSlotHeight']>0 and out['SideSlotTopMargin']>0 and out['SideSlotBottomMargin']>=out['Floor']):
        raise ValueError('Ventilation dimensions violate floor/web/seam constraints')
    return out,derived
