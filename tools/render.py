"""Re-shoot the tracked renders in model/renders/.

This module runs INSIDE a GUI FreeCAD instance. FreeCAD cannot save a
viewport image without one, and that is not a limitation this project can
route around: under freecadcmd, `import FreeCADGui` appears to succeed on
FreeCAD 1.1.1 but yields a stub with no getDocument and no activeDocument,
and forcing initialisation with showMainWindow() aborts the process outright
(`libc++abi: ... recursive_mutex lock failed`) -- a fatal C++ abort, not a
catchable Python exception. Do not spend time trying; the renders need a GUI.

Drive it through the FreeCAD MCP:

    spawn_freecad_instance(gui=True)
    execute_python("import render; render.render_all()")

The renders are 1600x1100 to match the files already tracked, so a re-shoot
can be compared against its predecessor. Changing the resolution breaks that
comparison, which is the only reason these files are tracked at all.
"""
import os
import sys

# The repo root, one level up: this file lives in tools/.
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODEL = os.path.join(REPO, "model")
PROJECT = os.path.join(MODEL, "radio86rk-assembly.FCStd")
RENDERS = os.path.join(MODEL, "renders")

WIDTH = 1600
HEIGHT = 1100
BACKGROUND = "White"

# Datum geometry renders as huge grey planes that swallow the model. Note
# App::Part is deliberately ABSENT: it is the container holding the board, and
# hiding it would hide everything inside it.
DATUM_TYPES = (
    "App::Plane", "App::Line", "App::Origin", "App::OriginGroup",
    "PartDesign::CoordinateSystem", "PartDesign::Plane", "PartDesign::Line",
    "PartDesign::Point",
)

VIEWS = (
    ("computer-axonometric.png", "viewAxonometric"),
    ("computer-top.png", "viewTop"),
)


def render_all(project=None, out_dir=None):
    """Open the tracked project, shoot both views, close without saving.

    Returns [(path, bytes)] for what it wrote.

    The close is not tidiness, it is the point. Leaving the document open
    lets the session's shutdown write it back: observed shutdowns have
    rewritten this exact file with nothing having called save(), at sizes that
    differ from session to session, so there is no byte count to recognise it
    by. .gitignore covers the harmless .FCBak it drops beside it but not the
    tracked .FCStd itself. Closing here means there is nothing left open for
    a shutdown to flush. Run `git status` afterwards anyway.
    """
    import FreeCAD
    import FreeCADGui

    project = project or PROJECT
    out_dir = out_dir or RENDERS
    os.makedirs(out_dir, exist_ok=True)

    doc = FreeCAD.openDocument(project)
    name = doc.Name
    written = []
    try:
        FreeCADGui.ActiveDocument = FreeCADGui.getDocument(name)
        for obj in doc.Objects:
            view = obj.ViewObject
            if view is not None:
                view.Visibility = obj.TypeId not in DATUM_TYPES

        view = FreeCADGui.activeDocument().activeView()
        for filename, orient in VIEWS:
            getattr(view, orient)()
            # fitAll AFTER the visibility changes, never before: framing the
            # datum planes and then hiding them leaves the model a speck.
            view.fitAll()
            path = os.path.join(out_dir, filename)
            view.saveImage(path, WIDTH, HEIGHT, BACKGROUND)
            size = os.path.getsize(path)
            if size < 20000:
                raise RuntimeError(
                    "%s is only %d bytes -- that is a blank canvas, not a "
                    "render; the camera framed nothing" % (path, size))
            written.append((path, size))
            print("%-28s %7.1f KB  %dx%d" % (filename, size / 1024.0,
                                             WIDTH, HEIGHT))
    finally:
        # closeDocument discards in-memory changes; nothing here should have
        # made any, and that is exactly what must not be written back.
        FreeCAD.closeDocument(name)
        print("closed %s without saving" % name)
    sys.stdout.flush()
    return written
