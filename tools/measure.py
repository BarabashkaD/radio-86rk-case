"""One-shot measurements whose results are pasted into params.tsv.

Not part of the build. It exists so a derived number can be reproduced and
audited rather than trusted.

Usage: $FC measure.py seat
"""
import os
import sys

import FreeCAD
import Part

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from verify import STEM_TOP_Z, cap_shape             # noqa: E402
except SystemExit as _exc:
    # SystemExit is not an Exception: verify's own guard exits, and
    # without this clause that would surface as the gate's vocabulary rather
    # than a failed measurement.
    print("measurement failed: verify could not load (exit %s)" % _exc.code)
    sys.stdout.flush()
    sys.exit(1)
except Exception as _exc:                                    # noqa: BLE001
    # Module-level failures exit 0 under freecadcmd: a measurement that never
    # ran would look like one that succeeded and printed nothing.
    print("measurement failed: cannot import verify: %s: %s"
          % (type(_exc).__name__, _exc))
    sys.stdout.flush()
    sys.exit(1)


def socket_ceiling(shape):
    """Z of the lowest material on the cap's central axis.

    The MX cross socket opens downward at the cap's centre, so a thin probe
    on that axis meets no material until the cavity's ceiling.

    The probe is intersected with each solid SEPARATELY and the minimum
    taken. A boolean against a multi-solid compound returns only ONE fragment
    and silently discards the rest.

    Each hit's Z is read TWICE: once via raw Shape.BoundBox, once via
    optimalBoundingBox(). BoundBox is banned everywhere else in this project
    because it over-reports a NURBS solid -- it bounds the control polygon,
    not the surface -- and inflated a keycap by 10.9 mm elsewhere in this
    pipeline. seat_dz is computed from the optimalBoundingBox() figure only;
    the raw BoundBox figure is measured and printed purely as a check, so an
    over-reporting call would show up as a disagreement instead of silently
    floating every cap.
    """
    bounds = shape.optimalBoundingBox()
    probe = Part.makeCylinder(
        0.4, bounds.ZLength + 2.0,
        FreeCAD.Vector(bounds.Center.x, bounds.Center.y, bounds.ZMin - 1.0))
    ceilings = []
    ceilings_raw = []
    for solid in shape.Solids:
        hit = solid.common(probe)
        if hit.Solids:
            ceilings.append(hit.optimalBoundingBox().ZMin)
            ceilings_raw.append(hit.BoundBox.ZMin)
    if not ceilings:
        print("error: no material on the central axis: this cap has no "
              "modelled socket. Fall back to a bounding-box seat and record "
              "that choice in params.tsv.")
        sys.stdout.flush()
        raise SystemExit(1)
    exact = min(ceilings)
    raw = min(ceilings_raw)
    print("socket ceiling (raw BoundBox)         : %.3f" % raw)
    print("socket ceiling (optimalBoundingBox)   : %.3f" % exact)
    print("difference (raw - optimal)            : %.3f" % (raw - exact))
    return exact


def cmd_seat():
    shape = cap_shape("100H")
    bounds = shape.optimalBoundingBox()
    ceiling = socket_ceiling(shape)
    seat_dz = STEM_TOP_Z - ceiling
    print("cap normalised  : Z %.3f .. %.3f" % (bounds.ZMin, bounds.ZMax))
    print("socket ceiling  : %.3f (cap frame)" % ceiling)
    print("stem top        : %.3f (ksu frame)" % STEM_TOP_Z)
    print("seat_dz         : %.3f" % seat_dz)
    print("cap base lands at Z %.3f, cap top at Z %.3f"
          % (bounds.ZMin + seat_dz, bounds.ZMax + seat_dz))


def _is_entry_script():
    """True when this file is the script freecadcmd was given."""
    return __name__ == "__main__" or (
        len(sys.argv) > 1
        and os.path.normcase(os.path.realpath(sys.argv[1]))
        == os.path.normcase(os.path.realpath(__file__)))


if _is_entry_script():
    args = sys.argv[2:]
    if args and args[0] == "seat":
        cmd_seat()
    else:
        print("usage: measure.py seat")
        sys.stdout.flush()
        raise SystemExit(1)
    sys.stdout.flush()
