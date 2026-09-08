"""Place the keycaps from the placements ksu resolved.

Reads model/placements.json -- produced from the live ksu document joined with
the board index -- and writes the caps and the envelope. No CSV is involved
anywhere in the path.

Outputs go to two places on purpose: model/envelope.step is the deliverable and
is tracked, while .build/caps/caps.step is 8 MB of regenerable geometry
whose STEP header carries a timestamp, so it is not.

Usage: $FC build_caps.py
"""
import json
import os
import sys
import traceback

import FreeCAD
import Part

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from verify import CASE, MODEL, cap_shape, load_table  # noqa: E402
except SystemExit as _exc:
    # verify's own import guard calls sys.exit, and SystemExit is NOT an
    # Exception -- so without this clause the build would inherit the gate's
    # "could not run" vocabulary and exit code for what is a build failure.
    print("build failed: verify could not load (exit %s); nothing was "
          "written, the previous caps.step is untouched and now stale"
          % _exc.code)
    sys.stdout.flush()
    sys.exit(1)
except Exception as _exc:                                    # noqa: BLE001
    # Module-level failures exit 0 under freecadcmd. Unguarded, a build that
    # died before it began would report success and leave the PREVIOUS
    # caps.step in place -- which the gate would then validate happily.
    print("build failed: cannot import verify: %s: %s"
          % (type(_exc).__name__, _exc))
    sys.stdout.flush()
    sys.exit(1)


def params():
    out = {}
    for row in load_table("params.tsv"):
        try:
            out[row["key"]] = float(row["value"])
        except ValueError:
            out[row["key"]] = row["value"]
    return out


def _warn_if_wrong_size(suffix, shape, units):
    """Say something when a keycaps.tsv row points at a cap of the wrong width.

    The build used to place whatever the table named and exit 0, so pointing a
    1.25u row at the 1.5u model produced 8 MB of wrong geometry that looked
    like a successful build. The gate catches it -- check B, with a clear
    message -- but only if you run the gate, and the whole point of this
    project is that things should not fail by looking like success.

    A warning rather than an error, deliberately: the gate is the authority on
    whether a build is acceptable, and duplicating its judgement here would
    give two places to disagree. This just refuses to be silent.
    """
    from verify import CAP_GAP_MM, obox
    want = units * 19.05 - CAP_GAP_MM
    got = obox(shape).XLength
    if abs(got - want) > 1.0:
        print("WARNING: the %s row of keycaps.tsv names a cap %.2f mm wide, "
              "but %su should be about %.2f mm. Wrong file in the model_file "
              "column? Building anyway; the gate will refuse this."
              % (suffix, got, units, want))
        sys.stdout.flush()


def placed_caps():
    """Return [(ref, shape)] with every cap moved onto its switch."""
    with open(os.path.join(MODEL, "placements.json")) as handle:
        joined = json.load(handle)
    seat_dz = params()["seat_dz"]
    cache = {}
    out = []
    for ref in sorted(joined, key=lambda r: int(r[2:])):
        entry = joined[ref]
        suffix = entry["suffix"]
        if suffix not in cache:
            cache[suffix] = cap_shape(suffix)
            _warn_if_wrong_size(suffix, cache[suffix], entry["units"])
        # copy before transforming: translate and rotate mutate in place, so
        # without this every placement of a size would share one object.
        shape = cache[suffix].copy()
        shape.translate(FreeCAD.Vector(entry["x"], entry["y"], seat_dz))
        if entry["rot_deg"]:
            shape.rotate(FreeCAD.Vector(entry["x"], entry["y"], 0),
                         FreeCAD.Vector(0, 0, 1), entry["rot_deg"])
        out.append((ref, shape))
    return out


def build_envelope():
    """One prism per key, sized to the tallest cap we allow, as a compound.

    A compound, NOT a fuse: the prisms are CAP_GAP_MM narrower than the pitch
    so neighbours sit 0.65 mm apart and touch nowhere, and the field is sparse
    besides. No boolean merges disjoint solids. One prism per cap is also the
    more useful hand-off -- D2 takes the bounding box for a single well, or
    the individual prisms for a per-key bezel.
    """
    from verify import CAP_GAP_MM
    with open(os.path.join(MODEL, "placements.json")) as handle:
        joined = json.load(handle)
    values = params()
    base_z = values["seat_dz"]
    top_z = values["env_height"]
    prisms = []
    for entry in joined.values():
        width = entry["units"] * 19.05 - CAP_GAP_MM
        depth = 19.05 - CAP_GAP_MM
        prisms.append(Part.makeBox(
            width, depth, top_z - base_z,
            FreeCAD.Vector(entry["x"] - width / 2.0,
                           entry["y"] - depth / 2.0, base_z)))
    return Part.makeCompound(prisms)


def main():
    try:
        os.makedirs(CASE, exist_ok=True)
        caps = placed_caps()
        compound = Part.makeCompound([shape for _ref, shape in caps])
        path = os.path.join(CASE, "caps.step")
        compound.exportStep(path)
        print("caps: %d placed -> %s (%.1f MB)"
              % (len(caps), path, os.path.getsize(path) / 1e6))

        envelope = build_envelope()
        env_path = os.path.join(MODEL, "envelope.step")
        envelope.exportStep(env_path)
        # .Solids rebuilds its list on each access; obox, not BoundBox, even
        # for a printed line -- a number that gets read is a number that gets
        # trusted, and the ban does not have an exception for diagnostics.
        env_solids = envelope.Solids
        env_box = envelope.optimalBoundingBox()
        print("envelope: %d solids, Z %.3f..%.3f -> %s"
              % (len(env_solids), env_box.ZMin, env_box.ZMax, env_path))
        return 0
    except Exception as exc:                                 # noqa: BLE001
        # An unhandled exception under freecadcmd exits 0 and swallows the
        # traceback, so a failed build would report success.
        print("build failed: %s: %s" % (type(exc).__name__, exc))
        traceback.print_exc()
        sys.stdout.flush()
        return 1


def _is_entry_script():
    """True when this file is the script freecadcmd was given."""
    return __name__ == "__main__" or (
        len(sys.argv) > 1
        and os.path.normcase(os.path.realpath(sys.argv[1]))
        == os.path.normcase(os.path.realpath(__file__)))


if _is_entry_script():
    rc = main()
    sys.stdout.flush()
    sys.exit(rc)
