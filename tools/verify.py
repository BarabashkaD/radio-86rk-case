"""Gate for the ksu-based keycap build (D1.1).

Run every check:     $FC verify.py
Run selected checks: $FC verify.py A A2

Exit 0 pass, 1 a real finding, 2 the gate could not run (never a verdict).

$FC is the FreeCAD console binary. It is NOT on PATH:
    FC=/Applications/FreeCAD.app/Contents/Resources/bin/freecadcmd

Arguments are positional only: FreeCAD swallows flags before Python sees them.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    import board_index                                      # noqa: E402
except Exception as _exc:                                   # noqa: BLE001
    # An unhandled exception at module level exits 0 under freecadcmd, so a
    # gate that cannot even import its own dependency would report success
    # while running no checks at all. Print, flush, then exit 2 -- "could not
    # run", never a verdict.
    print("SKIP: verify could not import board_index: %s: %s"
          % (type(_exc).__name__, _exc))
    sys.stdout.flush()
    sys.exit(2)

REPO = board_index.REPO
BOARD = board_index.BOARD
SUFFIX_UNITS = board_index.SUFFIX_UNITS
EXPECTED_HIST = {"100H": 62, "125H": 2, "150H": 1, "225H": 1, "625H": 1}
EXPECTED_SWITCHES = 67
# Asserted against ksu's measurement in check C, not merely trusted: every
# switch object in the imported document reports this as its ZMax. Without
# that assertion the whole Z chain -- seat_dz, the seat test, check G's Z
# half -- is arithmetic among hand-copied constants that no geometry can
# contradict.
STEM_TOP_Z = 15.443
STEM_TOP_TOL_MM = 0.01
CAP_GAP_MM = 0.65
CAP_MATCH_TOL_MM = 0.01
ROW_TOL_MM = 1.0
SEAT_TOL_MM = 0.10
BOARD_HEAD = "4f4c1b5"
# Two directories, split by one question: can this be regenerated headlessly?
#   MODEL  tracked. Only a GUI FreeCAD session with the ksu addon can produce
#          these, so a checkout without them cannot run most of the gate.
#   CASE   gitignored. Rebuilt in seconds by build_caps.py from MODEL plus the
#          vendored caps -- and STEP files carry a timestamp in their header,
#          so tracking an 8 MB caps.step would churn it on every build for no
#          semantic change.
MODEL = os.path.join(REPO, "model")
CASE = os.path.join(REPO, ".build", "caps")


class Fail(Exception):
    """A real finding: exit 1."""


class Skip(Exception):
    """The gate could not run: exit 2."""


def _howto(script):
    """A runnable command, not a bare name.

    `freecadcmd` is not on PATH on macOS, so a hint that says "run: freecadcmd
    build_caps.py" hands the reader a command that fails with "command not
    found". sys.executable is the interpreter actually running this file, so
    the hint is correct on any machine without hardcoding a path.
    """
    return "%s %s" % (sys.executable, script)


CHECKS = {}


def check(name):
    def deco(fn):
        CHECKS[name] = fn
        return fn
    return deco


@check("A")
def check_layout():
    """The board's layout is what every later step assumes."""
    try:
        index = board_index.build()
    except IOError as exc:
        raise Skip(str(exc))
    if len(index) != EXPECTED_SWITCHES:
        raise Fail("expected %d switches, found %d"
                   % (EXPECTED_SWITCHES, len(index)))
    hist = {}
    for suffix, _units in index.values():
        hist[suffix] = hist.get(suffix, 0) + 1
    if hist != EXPECTED_HIST:
        raise Fail("size histogram changed: %r != %r" % (hist, EXPECTED_HIST))
    for ref, (suffix, units) in index.items():
        if units is None:
            raise Fail("%s has unknown footprint suffix %r" % (ref, suffix))


def obox(shape):
    """Exact bounds.

    Shape.BoundBox over-reports a NURBS solid -- it bounds the control
    polygon, not the surface, and inflated the vendored spacebar by 10.9 mm
    on one side. Costs about 55 ms per solid, so call it once per solid and
    keep the result.
    """
    return shape.optimalBoundingBox()


def load_table(name):
    """Read a TSV, skipping blank lines and # comments."""
    path = os.path.join(REPO, name)
    if not os.path.exists(path):
        raise Skip("no %s" % path)
    if name == "keycaps.tsv":
        header = ["suffix", "units", "model_file", "stab_spacing_mm", "scale_x"]
    else:
        header = ["key", "value", "how_derived"]
    rows = []
    with open(path) as handle:
        for line in handle:
            line = line.rstrip("\n")
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            parts = line.split("\t")
            if len(parts) != len(header):
                raise Fail("%s: expected %d tab-separated fields, got %d: %r"
                           % (name, len(header), len(parts), line))
            rows.append(dict(zip(header, parts)))
    return rows


def cap_shape(suffix):
    """Load one vendored cap, normalised into a Z-up frame with base at Z=0.

    The vendored files are authored Y-up: X and Z carry the 18.2 mm plan
    dimensions centred on the origin, and Y is height with the seating face
    at Y = 0. Rotating +90 degrees about X maps Y to Z. Every cap is authored
    with its MX stem on the model origin, so no re-centring is needed -- and
    re-centring on Shape.BoundBox actively breaks the spacebar.

    A multi-solid cap is fused: DSA 1u ships a shell plus a stem contained
    inside it, and one cap must be one solid downstream.
    """
    import FreeCAD
    import Part
    for row in load_table("keycaps.tsv"):
        if row["suffix"] != suffix:
            continue
        path = os.path.join(REPO, row["model_file"])
        if not os.path.exists(path):
            raise Fail("keycaps.tsv row %r names a missing file: %s"
                       % (suffix, path))
        shape = Part.Shape()
        shape.read(path)
        shape = shape.copy()
        shape.rotate(FreeCAD.Vector(0, 0, 0), FreeCAD.Vector(1, 0, 0), 90)
        scale_x = float(row["scale_x"])
        if scale_x != 1.0:
            matrix = FreeCAD.Matrix()
            matrix.scale(scale_x, 1.0, 1.0)
            shape = shape.transformGeometry(matrix)
        solids = shape.Solids
        if len(solids) > 1:
            fused = solids[0]
            for extra in solids[1:]:
                fused = fused.fuse(extra)
            shape = fused.removeSplitter()
        return shape
    raise Fail("keycaps.tsv has no row for suffix %r" % suffix)


@check("B")
def check_models():
    """Each vendored cap is a solid of the width its row claims."""
    for row in load_table("keycaps.tsv"):
        units = float(row["units"])
        if SUFFIX_UNITS.get(row["suffix"]) != units:
            raise Fail("keycaps.tsv %s says %su, board footprint says %su"
                       % (row["suffix"], units,
                          SUFFIX_UNITS.get(row["suffix"])))
        shape = cap_shape(row["suffix"])
        if len(shape.Solids) < 1:
            raise Fail("%s yields no solids -- a surface-only or mesh import "
                       "would break the D2 booleans" % row["model_file"])
        want = units * 19.05 - CAP_GAP_MM
        got = obox(shape).XLength
        if abs(got - want) > 1.0:
            raise Fail("%s is %.2f mm wide, expected ~%.2f for %su -- wrong "
                       "file in the model_file column?"
                       % (row["model_file"], got, want, units))


@check("A2")
def check_readers_agree():
    """Three readers of one board must agree on which switches exist and
    on how wide each one is.

    This is the SW19 catcher. In D1 a kicad-cli CSV export silently dropped
    that switch -- its legend is `2 "` and the quote was not escaped -- and
    every consumer inherited the loss, so five checks unanimously agreed on
    66 switches.

    The three readers, and why there are three:

      ksu      the GUI import, via placements.json
      parser   board_index.build(), via KiCadStepUp's kicad_parser
      raw      board_index.build_raw(), a stdlib token scan sharing no code

    ksu-vs-parser catches divergence above the parse -- ksu's object
    construction, Label assignment, placement resolution. It cannot catch a
    defect INSIDE kicad_parser, because ksu reaches the board through that
    same module: both would be wrong identically. `raw` closes that gap. It
    is also the only independent source of each switch's SIZE: the suffix
    stored in placements.json is copied from `parser` at join time, so
    comparing those two is a staleness test, not an agreement test.
    """
    import json
    path = os.path.join(MODEL, "placements.json")
    if not os.path.exists(path):
        raise Skip("no %s -- run the ksu build first" % path)
    with open(path) as handle:
        joined = json.load(handle)
    index = board_index.build()
    raw = board_index.build_raw()

    from_ksu = set(joined)
    from_board = set(index)
    from_raw = set(raw)

    # The two board readers first: they share no code, so a disagreement
    # here is a parser defect, and every later comparison would be built on
    # an answer we no longer trust.
    if from_board != from_raw:
        only_parser = sorted(from_board - from_raw)
        only_raw = sorted(from_raw - from_board)
        raise Fail("the two board readers disagree -- only in kicad_parser: "
                   "%s; only in the raw scan: %s"
                   % (only_parser or "none", only_raw or "none"))
    if from_ksu != from_board:
        only_ksu = sorted(from_ksu - from_board)
        only_board = sorted(from_board - from_ksu)
        raise Fail("the two readers disagree -- only in ksu: %s; only in the "
                   "board index: %s" % (only_ksu or "none", only_board or "none"))
    if len(from_ksu) != EXPECTED_SWITCHES:
        raise Fail("both readers agree on %d switches, expected %d"
                   % (len(from_ksu), EXPECTED_SWITCHES))

    for ref in sorted(from_board):
        # Independent: kicad_parser's object model against the raw scan.
        if index[ref][0] != raw[ref][0]:
            raise Fail("%s: kicad_parser reads size %r, the raw scan reads %r"
                       % (ref, index[ref][0], raw[ref][0]))
        # Staleness: what the join FROZE against what the board says now,
        # compared against `raw` so this cannot check a value against the
        # source it was copied from.
        if joined[ref]["suffix"] != raw[ref][0]:
            raise Fail("%s: placements.json says %r, the board says %r -- "
                       "the join is stale, re-run the ksu build"
                       % (ref, joined[ref]["suffix"], raw[ref][0]))


# ksu uses raw KiCad X/Y; D1 is drill-origin relative. Verified on SW3:
#   ksu (15.875, -104.775)  ->  D1 (9.600, -98.500)
# so the mapping is x - 6.275 and y + 6.275. Getting these signs backwards
# makes the comparison fail on a perfectly correct build by 12.55 mm per axis.
DATUM_OFFSET_X = -6.275
DATUM_OFFSET_Y = 6.275
# D1 puts the board BOTTOM on Z=0, ksu puts the board TOP there.
#
# 1.595, NOT the 1.510 that D1's board solid measures. Those are different
# quantities and the difference is real: kicad-cli exports a board solid
# spanning Z 0.000..1.510 while mounting components on a plane 1.595 above
# the same origin. Using the board's thickness as the component offset makes
# the caps appear to disagree by 0.085 mm.
#
# Measured from the SWITCH BODIES, not the caps. Both pipelines placed the
# same SW_Cherry_MX_PCB model from the same board file through completely
# different toolchains, so their stem tops give the frame offset
# independently: D1 17.0375, ksu 15.4425, difference 1.5950 -- identical on
# SW1, SW3 and SW19, at opposite corners of the board.
#
# Deriving this offset from the caps instead would make check G's Z test a
# tautology. Both pipelines seat a cap at (its own stem top - its own socket
# ceiling), so a cap-derived offset would cancel exactly and always pass.
# Taken from the switches, the Z test reduces to "both pipelines measured
# the same socket ceiling" -- which they did independently, in different
# frames, and which is worth asserting.
DATUM_OFFSET_Z = 1.595
XY_TOL_MM = 0.001


@check("A3")
def check_positions_agree():
    """Where each switch SITS, cross-checked against D1's own extraction.

    A2 settles which switches exist and how wide each is; it says nothing
    about position. Check C, which comes later, largely cannot either: the
    caps it measures were BUILT from placements.json, so comparing them back
    to it is self-consistency. C earns its keep on seating, one-to-one
    matching and overlap -- not on absolute XY.

    This is the check that makes absolute position falsifiable, and it uses
    a genuinely separate derivation: D1's placement.csv comes from
    kicad-cli's position export, which shares no code path with ksu. If the
    two agree, the coordinates are right in a way neither pipeline alone can
    establish.

    It runs BEFORE any geometry exists, so a datum error is caught in
    seconds rather than after a full cap build. Check G repeats the
    comparison on the built solids, which is a different assertion: that the
    two pipelines PLACED what they read, not merely that they read the same.
    """
    import csv
    import json
    placements_path = os.path.join(MODEL, "placements.json")
    if not os.path.exists(placements_path):
        raise Skip("no %s -- run the ksu build first" % placements_path)
    # The tracked copy, not D1's gitignored build output. Freezing it does not
    # weaken the cross-check: it was produced by kicad-cli, a toolchain sharing
    # nothing with ksu, and that is where its independence comes from. Freezing
    # does make it a snapshot of one board revision -- which is why check E
    # pins the board's HEAD. If the board moves, E fails first and says so.
    d1_path = os.path.join(MODEL, "reference-placement.csv")
    if not os.path.exists(d1_path):
        raise Skip("no %s -- re-export it with D1's export_mech.py to make "
                   "the cross-check possible" % d1_path)
    with open(placements_path) as handle:
        joined = json.load(handle)

    d1 = {}
    with open(d1_path) as handle:
        for row in csv.DictReader(handle):
            if row["Package"].startswith("CHERRY_PCB_"):
                d1[row["Ref"]] = (float(row["PosX"]), float(row["PosY"]),
                                  float(row["Rot"]))
    if not d1:
        raise Skip("%s holds no CHERRY_PCB_ rows -- it is not a placement "
                   "export of this board" % d1_path)

    if set(joined) != set(d1):
        only_ksu = sorted(set(joined) - set(d1))
        only_d1 = sorted(set(d1) - set(joined))
        raise Fail("the two pipelines disagree on which switches exist -- "
                   "only in ksu: %s; only in D1: %s"
                   % (only_ksu or "none", only_d1 or "none"))

    for ref in sorted(joined):
        entry = joined[ref]
        want_x = entry["x"] + DATUM_OFFSET_X
        want_y = entry["y"] + DATUM_OFFSET_Y
        got_x, got_y, got_rot = d1[ref]
        if abs(want_x - got_x) > XY_TOL_MM or abs(want_y - got_y) > XY_TOL_MM:
            raise Fail("%s sits at (%.4f, %.4f) in ksu, which maps to "
                       "(%.4f, %.4f), but D1 reads (%.4f, %.4f) -- a "
                       "%.4f mm disagreement"
                       % (ref, entry["x"], entry["y"], want_x, want_y,
                          got_x, got_y,
                          max(abs(want_x - got_x), abs(want_y - got_y))))
        if abs(got_rot - entry["rot_deg"]) > 0.001:
            raise Fail("%s is rotated %.3f deg in ksu and %.3f deg in D1"
                       % (ref, entry["rot_deg"], got_rot))


@check("C")
def check_placement():
    """The caps are present, seated on their stems, and do not collide."""
    import Part
    caps_path = os.path.join(CASE, "caps.step")
    if not os.path.exists(caps_path):
        raise Skip("no %s -- run: %s" % (caps_path, _howto("build_caps.py")))
    import json
    placements_path = os.path.join(MODEL, "placements.json")
    if not os.path.exists(placements_path):
        raise Skip("no %s -- run the ksu build first" % placements_path)
    with open(placements_path) as handle:
        joined = json.load(handle)

    seat_dz = None
    for row in load_table("params.tsv"):
        if row["key"] == "seat_dz":
            seat_dz = float(row["value"])
    if seat_dz is None:
        raise Skip("params.tsv has no seat_dz -- run measure.py seat")

    # ANCHOR seat_dz ITSELF, by re-deriving it rather than trusting the file.
    #
    # Anchoring STEM_TOP_Z alone was not enough. seat_dz is the OTHER
    # hand-recorded number, and every geometric test below is blind to it:
    # the seat test compares a cap base against the same recorded value that
    # positioned the cap, containment moves with it, and the clearance floor
    # moves with it too. A typo of 10.743 -> 10.243 was demonstrated to pass
    # C, D and H; only check G caught it, and G skips wherever D1's gitignored
    # build outputs are absent. Re-measuring the socket ceiling here closes
    # that, and costs one probe.
    try:
        from measure import socket_ceiling                # noqa: E402
        ceiling = socket_ceiling(cap_shape("100H"))
    except SystemExit as exc:
        # socket_ceiling exits when a cap has no modelled socket; inside a
        # check that must be a Skip, never a process exit.
        raise Skip("the socket ceiling could not be probed (%s) -- seat_dz "
                   "cannot be re-derived" % exc)
    want_seat = STEM_TOP_Z - ceiling
    if abs(seat_dz - want_seat) > STEM_TOP_TOL_MM:
        raise Fail("params.tsv records seat_dz %.4f, but re-deriving it "
                   "now gives %.4f (stem top %.3f - socket ceiling %.4f) -- "
                   "the recorded value does not match the geometry it claims "
                   "to come from" % (seat_dz, want_seat, STEM_TOP_Z, ceiling))

    # ANCHOR THE Z CHAIN TO MEASURED GEOMETRY.
    #
    # Everything about height in this project descends from STEM_TOP_Z, and
    # that constant is a hand-copied literal. The seat test below cannot
    # catch a wrong one: build_caps translates each cap by seat_dz and
    # cap_shape normalises the cap's base to Z=0, so a cap's ZMin is seat_dz
    # BY CONSTRUCTION and the comparison is an identity. Check G's Z half is
    # likewise arithmetic among recorded constants.
    #
    # ksu measured the real stem top per switch and stored it. Assert the
    # literal against that measurement, and the identities below become
    # consequences of something a board or model change can falsify.
    missing = [ref for ref, entry in joined.items() if "stem_top" not in entry]
    if missing:
        # A finding, not a Skip: placements.json predates the anchor, so the
        # Z chain is unverified. Letting a KeyError become "could not run"
        # would report the absence of the check as merely inconvenient.
        raise Fail("%d entries in placements.json carry no stem_top (%s ...) "
                   "-- it predates the anchor; re-run the ksu build"
                   % (len(missing), ", ".join(sorted(missing)[:3])))
    off = [(ref, entry["stem_top"]) for ref, entry in joined.items()
           if abs(entry["stem_top"] - STEM_TOP_Z) > STEM_TOP_TOL_MM]
    if off:
        ref, measured = off[0]
        raise Fail("STEM_TOP_Z is %.3f but ksu measured %.6f on %s (%d switch"
                   "es disagree) -- the constant no longer describes the "
                   "board, and every derived height is wrong with it"
                   % (STEM_TOP_Z, measured, ref, len(off)))

    # Staleness, the same class check F guards for the import log. A build
    # that dies partway leaves the PREVIOUS caps.step in place, and every
    # test below would validate that one happily.
    if os.path.getmtime(caps_path) < os.path.getmtime(placements_path) - 1.0:
        raise Fail("caps.step predates placements.json -- it was built from "
                   "different placements; re-run build_caps.py")

    caps = Part.Shape()
    caps.read(caps_path)
    solids = list(caps.Solids)
    if len(solids) != EXPECTED_SWITCHES:
        raise Fail("caps.step holds %d solids, expected %d"
                   % (len(solids), EXPECTED_SWITCHES))

    # Rotation is applied by build_caps and compared against D1's independent
    # reading in check A3. Here we assert the stronger property this board
    # actually has -- every switch upright -- so a future revision that
    # rotates one fails loudly rather than yielding a cap that is turned but
    # still centred, which the distance match below would happily accept.
    rotated = {ref: entry["rot_deg"] for ref, entry in joined.items()
               if abs(entry["rot_deg"]) > 0.001}
    if rotated:
        raise Fail("switches carry a non-zero rotation, which nothing "
                   "downstream verifies: %r" % rotated)

    boxes = [obox(solid) for solid in solids]
    claimed = {}
    for ref, entry in joined.items():
        best, best_d2 = None, None
        for index, box in enumerate(boxes):
            d2 = ((box.Center.x - entry["x"]) ** 2
                  + (box.Center.y - entry["y"]) ** 2)
            if best_d2 is None or d2 < best_d2:
                best, best_d2 = index, d2
        if best_d2 ** 0.5 > CAP_MATCH_TOL_MM:
            raise Fail("no cap within %.2f mm of %s at (%.3f, %.3f); nearest "
                       "is %.4f mm away"
                       % (CAP_MATCH_TOL_MM, ref, entry["x"], entry["y"],
                          best_d2 ** 0.5))
        if best in claimed:
            raise Fail("one cap is serving both %s and %s -- a switch has no "
                       "cap of its own" % (claimed[best], ref))
        claimed[best] = ref
        box = boxes[best]
        # A TOLERANCE, not a straddle. `ZMin < STEM_TOP_Z < ZMax` passes for
        # any seat error smaller than the cap's own height -- an 8.2 mm window
        # that accepts a 3 mm error. D1 shipped a 5 mm displacement on this
        # axis, so the check that exists to catch it must actually be tight.
        if abs(box.ZMin - seat_dz) > SEAT_TOL_MM:
            raise Fail("%s cap base is at Z %.4f, expected %.4f (tolerance "
                       "%.2f mm) -- it is not seated correctly"
                       % (ref, box.ZMin, seat_dz, SEAT_TOL_MM))
        if not (box.ZMin < STEM_TOP_Z < box.ZMax):
            raise Fail("%s cap spans Z %.3f..%.3f which does not straddle the "
                       "stem top %.3f -- it is not seated"
                       % (ref, box.ZMin, box.ZMax, STEM_TOP_Z))

    # Group into rows by tolerance FIRST, then order each row by X.
    # A single sort key cannot do both: intra-row Y differs by ~3e-12 mm by
    # transform history, so raw Y becomes the primary key and X never orders
    # anything; and round(y, 1) ties on the .x5 boundary the pitch produces.
    rows = []
    for box in sorted(boxes, key=lambda b: b.Center.y):
        if rows and abs(rows[-1][0] - box.Center.y) <= ROW_TOL_MM:
            rows[-1][1].append(box)
        else:
            rows.append((box.Center.y, [box]))
    for _centre, members in rows:
        members.sort(key=lambda b: b.Center.x)
        for left, right in zip(members, members[1:]):
            overlap = left.XMax - right.XMin
            if overlap > 0.001:
                raise Fail("neighbouring caps overlap in X by %.3f mm near "
                           "(%.1f, %.1f)"
                           % (overlap, left.Center.x, left.Center.y))


@check("D")
def check_envelope():
    """The envelope contains every cap, one prism per cap."""
    import Part
    env_path = os.path.join(MODEL, "envelope.step")
    caps_path = os.path.join(CASE, "caps.step")
    for path in (env_path, caps_path):
        if not os.path.exists(path):
            raise Skip("no %s -- run: %s" % (path, _howto("build_caps.py")))

    envelope = Part.Shape()
    envelope.read(env_path)
    env_solids = list(envelope.Solids)
    if len(env_solids) != EXPECTED_SWITCHES:
        raise Fail("envelope.step holds %d solids, expected %d -- one per cap"
                   % (len(env_solids), EXPECTED_SWITCHES))

    caps = Part.Shape()
    caps.read(caps_path)
    # obox, not BoundBox. The prisms are makeBox solids, so the two agree
    # exactly here -- but the ban is unconditional precisely so that no
    # reader has to work out whether a given shape is one of the safe ones.
    env_centres = [obox(solid).Center for solid in env_solids]
    claimed = {}
    for solid in caps.Solids:
        centre = obox(solid).Center
        best, best_d2 = None, None
        for index, env_centre in enumerate(env_centres):
            d2 = ((env_centre.x - centre.x) ** 2
                  + (env_centre.y - centre.y) ** 2)
            if best_d2 is None or d2 < best_d2:
                best, best_d2 = index, d2
        if best_d2 ** 0.5 > CAP_MATCH_TOL_MM:
            raise Fail("no envelope prism within %.2f mm of the cap at "
                       "(%.1f, %.1f)" % (CAP_MATCH_TOL_MM, centre.x, centre.y))
        if best in claimed:
            raise Fail("one prism serves the caps at (%.1f, %.1f) and "
                       "(%.1f, %.1f)" % (claimed[best][0], claimed[best][1],
                                         centre.x, centre.y))
        claimed[best] = (centre.x, centre.y)
        # cut against ITS OWN prism: a boolean over the whole compound
        # returns one fragment and drops the other 66.
        outside = solid.cut(env_solids[best])
        if outside.Solids and outside.Volume > 0.01:
            raise Fail("a cap near (%.1f, %.1f) sticks %.3f mm3 outside its "
                       "envelope prism -- D2's top plate would clip it"
                       % (centre.x, centre.y, outside.Volume))


@check("H")
def check_interior_clearance():
    """The envelope must not swallow a tall board component.

    This check is headless and scalar: it compares max_component_z against
    the envelope floor and cannot see X or Y at all. What makes that
    comparison meaningful is done at MEASUREMENT time, not here -- Task 7
    measured max_component_z with optimalBoundingBox in the ksu-imported GUI
    document, scoped to only those components whose XY footprint overlaps a
    key footprint (see params.tsv's how_derived for max_component_z).
    Because the check itself has no component geometry to consult, it must
    trust that upstream scoping; it exists so a future re-measurement that
    picks up a tall part actually under the keyboard fails here rather than
    in a printed case.
    """
    import Part
    env_path = os.path.join(MODEL, "envelope.step")
    if not os.path.exists(env_path):
        raise Skip("no %s -- run: %s" % (env_path, _howto("build_caps.py")))
    values = {}
    for row in load_table("params.tsv"):
        values[row["key"]] = row["value"]
    if "max_component_z" not in values:
        raise Skip("params.tsv has no max_component_z")
    tallest = float(values["max_component_z"])
    envelope = Part.Shape()
    envelope.read(env_path)
    # obox(), not envelope.BoundBox: BoundBox is banned project-wide because
    # it over-reports NURBS. The envelope is built entirely from
    # Part.makeBox() prisms, so the two happen to coincide here -- but the
    # ban is unconditional, and the next reader should not see the banned
    # call modelled as an acceptable shortcut.
    floor = obox(envelope).ZMin
    if tallest > floor:
        raise Fail("the tallest non-switch component reaches Z %.3f but the "
                   "envelope floor is Z %.3f -- a component intrudes into the "
                   "keyboard well" % (tallest, floor))


@check("I")
def check_project_caps_current():
    """The caps saved inside the .FCStd must match the ones the build makes.

    The project file carries a top-level `caps` object -- a Part::Feature of
    67 solids, not a live link to anything. Nothing else in this repo ever
    opens that file: build_caps.py writes caps.step and envelope.step and
    never touches it, and until this check existed no gate did either.

    So the one artifact a person actually opens to LOOK at the design could
    drift from the pipeline silently. Change the profile in keycaps.tsv,
    re-run build_caps.py, and you get new geometry in caps.step and
    envelope.step while the project still shows the old caps -- with every
    other check passing, because every other check reads the STEP files.

    Compared on solid count and on each solid's bounding-box centre, sorted,
    because solid ORDER is not guaranteed to survive a STEP round trip and an
    order-sensitive comparison would fail for no real reason. Positions are
    what matters: this asks whether the caps sit in the same places.
    """
    import Part
    import FreeCAD
    project = os.path.join(MODEL, "radio86rk-assembly.FCStd")
    caps_path = os.path.join(CASE, "caps.step")
    if not os.path.exists(project):
        raise Skip("no %s -- it is tracked; is this a partial checkout?"
                   % project)
    if not os.path.exists(caps_path):
        raise Skip("no %s -- run: %s" % (caps_path, _howto("build_caps.py")))

    doc = FreeCAD.openDocument(project)
    try:
        found = doc.getObjectsByLabel("caps")
        if not found:
            raise Fail("%s has no object labelled 'caps' -- the project no "
                       "longer carries the keycaps it is tracked to show"
                       % project)
        in_doc = found[0].Shape.Solids
        built = Part.Shape()
        built.read(caps_path)
        in_step = built.Solids
        if len(in_doc) != len(in_step):
            raise Fail("the project holds %d caps, caps.step holds %d -- "
                       "re-render the project: freecadcmd is not enough, see "
                       "render.py" % (len(in_doc), len(in_step)))

        def centres(solids):
            return sorted(tuple(round(v, 4) for v in s.BoundBox.Center)
                          for s in solids)

        a, b = centres(in_doc), centres(in_step)
        off = [(x, y) for x, y in zip(a, b) if x != y]
        if off:
            raise Fail(
                "%d of %d caps sit in different places in the project than "
                "the build produces; first: project %s vs built %s. The "
                "project is stale -- re-import and re-save it, or re-render."
                % (len(off), len(a), off[0][0], off[0][1]))
    finally:
        # Close without saving: an open document can be written back by the
        # session's shutdown, and this one is tracked. See render.py.
        FreeCAD.closeDocument(doc.Name)


@check("E")
def check_non_invasive():
    """This repo never modifies the board repo."""
    import subprocess
    if not os.path.isdir(os.path.join(BOARD, ".git")):
        raise Skip("no board checkout at %s" % BOARD)
    result = subprocess.run(["git", "-C", BOARD, "status", "--porcelain"],
                            capture_output=True, text=True)
    if result.returncode != 0:
        raise Skip("git failed in %s: %s" % (BOARD, result.stderr.strip()))
    if result.stdout.strip():
        raise Fail("the board repo has uncommitted changes; D1.1 must not "
                   "touch it:\n%s" % result.stdout.rstrip())

    # A clean tree is not enough: `git commit -a` leaves the tree clean while
    # violating the spec's "zero new commits" outright. Pin HEAD as well.
    head = subprocess.run(["git", "-C", BOARD, "rev-parse", "HEAD"],
                          capture_output=True, text=True)
    if head.returncode != 0:
        raise Skip("git rev-parse failed in %s" % BOARD)
    actual = head.stdout.strip()
    if not actual.startswith(BOARD_HEAD):
        raise Fail("the board repo is at %s, expected %s -- D1.1 must make no "
                   "commits there, and a clean tree does not prove it did not"
                   % (actual[:7], BOARD_HEAD))


@check("F")
def check_import_health():
    """The ksu import loaded everything, and altered nothing.

    Both of the defects this catches were invisible in geometry and in every
    render: without prefix3d_2 ksu silently loads 140 models instead of 209,
    dropping all 67 switches; and it discards a non-unit model scale, which
    rendered U26 3.1 mm too shallow. Each was one line in a 200-line log.
    """
    path = os.path.join(MODEL, "import_log.txt")
    if not os.path.exists(path):
        raise Skip("no %s -- capture ksu's report view after the build" % path)
    with open(path) as handle:
        log = handle.read()

    # A stale log from a previous good run would pass every assertion below
    # while the current build is broken -- the exact silent-success class this
    # check exists to catch. Refuse a log older than the import it describes.
    #
    # The reference is placements.json, NOT caps.step. The log describes the
    # ksu IMPORT, and the documented order is: import -> placements.json ->
    # capture the log -> build_caps.py -> caps.step. Against caps.step the
    # guard has inverted polarity: it fails a correct build, because a rebuild
    # of the caps legitimately postdates a log that still describes the import
    # they came from. It passed only by the accident of one re-capture.
    import_path = os.path.join(MODEL, "placements.json")
    if os.path.exists(import_path):
        if os.path.getmtime(path) < os.path.getmtime(import_path) - 1.0:
            raise Fail("import_log.txt predates placements.json -- it does not "
                       "describe the import that produced this build; "
                       "re-capture the report view")
    if "added 209 model(s)" not in log:
        raise Fail("the log does not report 209 models added; 140 means "
                   "prefix3d_2 is unset and every keyswitch is missing")
    for needle, what in (("error missing", "a model failed to resolve"),
                         ("wrong scale!!!", "ksu discarded a model scale")):
        if needle in log:
            lines = [ln for ln in log.splitlines() if needle in ln]
            raise Fail("%s: %s" % (what, lines[0].strip()))


@check("G")
def check_pipelines_agree():
    """D1.1 must agree with D1 on where every cap physically sits.

    D1 contributes a FROZEN reference (model/reference-caps.tsv), not a
    live build. Nothing here runs D1, and this gate no longer needs it.

    The two frames differ by the drill origin in X and Y and by which board
    face sits on Z=0, so the comparison applies DATUM_OFFSET_* rather than
    expecting raw equality. Two independent derivations agreeing is the whole
    reason both pipelines exist.

    What the Z half actually asserts is worth stating, because it is not
    obvious: DATUM_OFFSET_Z is measured from the switch bodies, so this test
    reduces to "both pipelines measured the same socket ceiling" -- two
    independent measurements, in different frames, by different code. Were
    the offset taken from the caps it would cancel and always pass.
    """
    import Part
    reference = os.path.join(MODEL, "reference-caps.tsv")
    d11 = os.path.join(CASE, "caps.step")
    if not os.path.exists(reference):
        raise Skip("no %s -- it is tracked; is this a partial checkout?"
                   % reference)
    if not os.path.exists(d11):
        raise Skip("no %s -- run: %s" % (d11, _howto("build_caps.py")))

    # D1's side is FROZEN, not rebuilt. It used to read D1's live
    # .build/case/caps.step, which meant this gate could not reach PASS
    # unless the other pipeline had been run -- and that pipeline needs
    # kicad-cli, so a D1.1-only checkout was permanently INCOMPLETE. The
    # numbers below still came from D1's own independent derivation; freezing
    # them keeps the cross-check and drops the runtime dependency. Same trade
    # reference-placement.csv already makes for check A3, and check E pins the board
    # revision both were taken from.
    a_centres = []
    with open(reference) as handle:
        for line in handle:
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            parts = line.split("\t")
            if len(parts) != 3:
                raise Fail("%s: expected 3 tab-separated fields, got %d: %r"
                           % (reference, len(parts), line))
            a_centres.append(tuple(float(p) for p in parts))
    a_centres.sort()

    b = Part.Shape()
    b.read(d11)
    # .Solids rebuilds its list on every access -- bind once.
    b_solids = b.Solids
    if len(a_centres) != len(b_solids):
        raise Fail("the frozen D1 reference has %d caps, D1.1 built %d"
                   % (len(a_centres), len(b_solids)))

    # obox() costs ~55 ms, so compute it ONCE per solid and reuse.
    b_boxes = [obox(s) for s in b_solids]
    b_centres = sorted((box.Center.x + DATUM_OFFSET_X,
                        box.Center.y + DATUM_OFFSET_Y,
                        box.ZMin + DATUM_OFFSET_Z) for box in b_boxes)

    worst_xy = 0.0
    worst_z = 0.0
    for (ax, ay, az), (bx, by, bz) in zip(a_centres, b_centres):
        worst_xy = max(worst_xy, ((ax - bx) ** 2 + (ay - by) ** 2) ** 0.5)
        worst_z = max(worst_z, abs(az - bz))
    if worst_xy > 0.05:
        raise Fail("the pipelines disagree in XY: worst cap-centre difference "
                   "%.4f mm after the datum offset" % worst_xy)
    # Z matters most: the two pipelines derive seat_dz INDEPENDENTLY, in
    # different frames, and D1 shipped a defect on this axis. Comparing only
    # XY would leave the one genuinely independent number uncompared.
    if worst_z > 0.05:
        raise Fail("the pipelines disagree in Z: worst cap-base difference "
                   "%.4f mm after the datum offset -- the two seat_dz values "
                   "were derived independently, so this is a real finding"
                   % worst_z)


def main():
    """Run the requested checks and report one verdict.

    A Skip does NOT abort the run. Skips accumulate and the remaining checks
    still execute: aborting on the first Skip once silenced six checks in a
    D1.1-only checkout, and exit 2 reads as "could not run", which is easy to
    mistake for "nothing was wrong".

    That used to bite hardest on A3 and G, which both read D1's gitignored
    build outputs. Neither does any more -- A3 reads the tracked
    model/reference-placement.csv and G the tracked model/reference-caps.tsv -- so a
    D1.1-only checkout now reaches PASS. The accumulation still matters: any
    check can skip for its own reasons, and one skip must not hide the rest.

    Precedence at the end: any real finding is exit 1 even if something else
    skipped, because a finding is a verdict and a skip is the absence of one.
    """
    names = sys.argv[2:] or sorted(CHECKS)
    failed, skipped = [], []
    for name in names:
        if name not in CHECKS:
            print("unknown check %r; known: %s"
                  % (name, ", ".join(sorted(CHECKS))))
            sys.stdout.flush()
            return 2
        try:
            CHECKS[name]()
        except Skip as exc:
            print("SKIP %s: %s" % (name, exc))
            skipped.append(name)
        except Fail as exc:
            print("FAIL %s: %s" % (name, exc))
            failed.append(name)
        except Exception as exc:                             # noqa: BLE001
            print("SKIP %s: could not be evaluated: %s: %s"
                  % (name, type(exc).__name__, exc))
            skipped.append(name)
        else:
            print("PASS %s" % name)
        sys.stdout.flush()

    if failed:
        print("verdict: FAIL (%s)" % ", ".join(failed)
              + (" -- and %s could not run" % ", ".join(skipped)
                 if skipped else ""))
        return 1
    if skipped:
        print("verdict: INCOMPLETE -- %s could not run, so this is not a "
              "verdict on the board" % ", ".join(skipped))
        return 2
    print("verdict: PASS")
    return 0


def _is_entry_script():
    """True when this file is the script freecadcmd was given.

    __name__ is the basename under freecadcmd whether the module is run or
    imported, so it cannot distinguish the two. sys.argv[1] can: it is the
    script FreeCAD was asked to execute.
    """
    return __name__ == "__main__" or (
        len(sys.argv) > 1
        and os.path.normcase(os.path.realpath(sys.argv[1]))
        == os.path.normcase(os.path.realpath(__file__)))


if _is_entry_script():
    rc = main()
    sys.stdout.flush()
    sys.exit(rc)
