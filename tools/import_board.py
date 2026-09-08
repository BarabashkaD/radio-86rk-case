"""Import the board through KiCadStepUp and read back switch placements.

This module runs INSIDE a GUI FreeCAD instance -- ksu's workbench cannot
load under freecadcmd (ImportError: Cannot load Gui module in console
application). Drive it through the FreeCAD MCP:

    spawn_freecad_instance(gui=True)
    execute_python_async(...)          # the import takes ~40 s
    poll_job(...)

ksu is automatable even though it is not headless; those are different
properties.
"""
import json
import os
import re
import sys
import time

# Derived from $HOME, and overridable, for the same reason board_index does
# it: a hard-coded home directory makes the repo unusable to anyone else.
KSU_MOD = os.environ.get(
    "KSU_MOD",
    os.path.expanduser("~/Library/Application Support/FreeCAD/v1-1/"
                       "Mod/kicadStepUpMod"))

# The repo root, one level up: this file lives in tools/.
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# Durable, GUI-only outputs live in a TRACKED directory, not in .build/.
# Nothing here can be regenerated headlessly, so a checkout without these
# files cannot run most of the gate. See README, "What is tracked and why".
MODEL = os.path.join(REPO, "model")

SWITCH_RE = re.compile(r'^(SW\d+)_')


def _ksu():
    if KSU_MOD not in sys.path:
        sys.path.insert(0, KSU_MOD)
    import FreeCADGui
    FreeCADGui.activateWorkbench("KiCadStepUpWB")
    import kicadStepUptools as ksu
    # A module-level variable, not a preference. Left True, ksu raises modal
    # dialogs that block the GUI thread and hang the MCP call indefinitely.
    ksu.show_messages = False
    return ksu


def open_board(pcb_path):
    """Import the board. Returns the document name."""
    import FreeCAD
    ksu = _ksu()
    before = set(FreeCAD.listDocuments())
    ksu.open(pcb_path)
    new = set(FreeCAD.listDocuments()) - before
    if not new:
        raise RuntimeError("ksu.open produced no document for %s" % pcb_path)
    return sorted(new)[0]


def switch_placements(doc_name):
    """Return {ref: {x, y, z, rot_deg, stem_top}} for the keyswitches.

    Selection rule, verified to yield exactly 67 and to exclude SW68, the
    tactile reset: the Label starts with a reference designator, mentions
    Cherry_MX_PCB, and is not a Stabilizer. The reference lives in Label --
    Name is FreeCAD's internal name and is unreliable.

    Note the document does NOT carry the footprint name: SW64 (spacebar) and
    SW1 (1u) both report a 15.600 mm switch body. Size comes from
    board_index instead.
    """
    import FreeCAD
    doc = FreeCAD.getDocument(doc_name)
    out = {}
    for obj in doc.Objects:
        match = SWITCH_RE.match(obj.Label)
        if not match:
            continue
        if "Cherry_MX_PCB" not in obj.Label or "Stabilizer" in obj.Label:
            continue
        placement = obj.Placement
        out[match.group(1)] = {
            "x": placement.Base.x,
            "y": placement.Base.y,
            "z": placement.Base.z,
            "rot_deg": placement.Rotation.Angle * 57.29577951308232,
            # optimalBoundingBox, not BoundBox: this value becomes
            # STEM_TOP_Z and seeds seat_dz, so an over-report would propagate
            # into every check with nothing to catch it. They agree for the
            # current Cherry model (15.442520 both); they need not for another.
            "stem_top": obj.Shape.optimalBoundingBox().ZMax,
        }
    return out


def export_placements(doc_name, path=None):
    """Join ksu's placements with the board index and write placements.json.

    This existed only as code typed into a live session until it was needed a
    second time. Everything the headless gate knows about where switches sit
    comes through this file, so the step that produces it belongs in version
    control like any other.
    """
    import FreeCAD
    sys.path.insert(0, REPO)
    import board_index
    placements = switch_placements(doc_name)
    index = board_index.build()
    joined = {}
    for ref, entry in placements.items():
        if ref not in index:
            # A plain exception, never SystemExit: this runs inside the live
            # GUI process, where SystemExit can take down a session that cost
            # forty seconds to build.
            raise RuntimeError("ksu has %s, the board index does not" % ref)
        suffix, units = index[ref]
        joined[ref] = dict(entry, suffix=suffix, units=units)
    path = path or os.path.join(MODEL, "placements.json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as handle:
        json.dump(joined, handle, indent=1, sort_keys=True)
    return joined


def capture_report(path=None):
    """Save ksu's report view -- check F's only evidence.

    The report view is per-process: it dies with the instance and cannot be
    reconstructed afterwards by any means. Capture it in the same session as
    the import.
    """
    import FreeCADGui
    from PySide import QtGui
    widget = FreeCADGui.getMainWindow().findChild(QtGui.QTextEdit,
                                                  "Report view")
    if widget is None:
        raise RuntimeError("no Report view widget -- enable it under "
                           "View > Panels > Report view")
    text = widget.toPlainText()
    path = path or os.path.join(MODEL, "import_log.txt")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as handle:
        # Stamped so check F can refuse a log older than the import it claims
        # to describe.
        handle.write("# captured %.3f\n" % time.time())
        handle.write(text)
    return len(text)


def save_project(doc_name, path=None):
    """Save the imported document itself.

    Recreating it needs the GUI, the ksu addon, KiCad's model libraries and
    the prefix3d preferences all lined up; the file is the only artifact that
    survives any of those changing.
    """
    import FreeCAD
    path = path or os.path.join(MODEL, "radio86rk-assembly.FCStd")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    FreeCAD.getDocument(doc_name).saveAs(path)
    return path


def rebuild(pcb_path):
    """The whole GUI half, in one call, in the right order.

    Run inside a GUI instance after a board change:
        import import_board; import_board.rebuild("<path to .kicad_pcb>")
    then headlessly: freecadcmd build_caps.py && freecadcmd verify.py
    """
    name = open_board(pcb_path)
    joined = export_placements(name)
    # Capture AFTER the placements exist: check F requires the log to be no
    # older than the import it describes, and compares against that file.
    chars = capture_report()
    path = save_project(name)
    print("document %s: %d switches, %d chars of log, saved %s"
          % (name, len(joined), chars, path))
    return name
