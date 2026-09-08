# Radio-86RK Case Build Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Generate every part of the 3D-printable Radio-86RK case from `case.tsv`, the pinned board and `model/envelope.step`, render it around the board, gate it, and tile it for any printer bed.

**Architecture:** A `tools/case/` package where each part is one pure function `part(p, b, L) -> Part.Solid` from parameters, board data and a shared `Layout` of derived coordinates. `build_case.py` writes STEP/STL per part plus a case document; `render_case.py` shoots renders in a GUI FreeCAD launched from the shell; `verify.py` gains eight lettered checks; `tiling.py` cuts any oversize part by `max_tile` after modelling. Milestone order is deliberately "see it first": parts → export → render (Task 10), then the gate, then tiling, then polish.

**Tech Stack:** FreeCAD 1.1.1 `Part` module under `freecadcmd`; the GUI binary `/Applications/FreeCAD.app/Contents/MacOS/FreeCAD` for renders; Python 3 stdlib `unittest` as the test runner (runs under `freecadcmd`); no pip packages.

**Spec:** `docs/superpowers/specs/2026-09-09-case-design.md`

## Global Constraints

- Interpreter: `FC=/Applications/FreeCAD.app/Contents/Resources/bin/freecadcmd`. There is no `freecadcmd` on `PATH`; system `python3` is blocked on this machine and lacks `Part`.
- FreeCAD swallows flags: script arguments are positional and land at `sys.argv[2:]`. Never design a `--flag`.
- `__name__` is never `"__main__"` under `freecadcmd`; use the `_is_entry_script()` idiom from `tools/build_caps.py`.
- An unhandled exception exits 0. Guard module-level imports and `main()`; print, `sys.stdout.flush()`, exit non-zero.
- `Shape.BoundBox` is banned; use `optimalBoundingBox()` (the `obox()` helper).
- Board revision is pinned at `4f4c1b5`; the board repo is read-only from here.
- Frame: all case geometry is in the **board frame** used by `model/envelope.step` and `model/radio86rk-assembly.FCStd`: X as KiCad, Y = −(KiCad Y), Z = 0 at the board's top face, board bottom at Z −1.6. Rear edge is Y −6.35 (the maximum Y), front edge Y −209.55.
- Every FreeCAD launch prints a `3DconnexionNavlib.framework` dlopen failure; ignore it. Filter with `grep -v 3Dconnexion`.
- After any GUI FreeCAD run, `git status`; revert any `model/*.FCStd` diff you cannot explain.
- Commit messages end with the two attribution lines used in this repo (see `git log -1`).
- In zsh, do not start an `echo` argument with `=`; it triggers command-path expansion.

## Deviations from the spec, decided while probing the board

- `hinge_z` is 26, not 24, and `lid_w` is 60, not 65. The DIN body reaches Z 21.46 and the DE‑9 body starts at X 181.4; socket blocks on the plate's inner face need Z ≥ 23 and X ≤ 178.6 to keep 1 mm clearance. Window: X 118.6–178.6, Z 26–45. Lid rear face is 19 mm.
- Renders do not use the MCP bridge. A GUI FreeCAD launched from the shell with a script (`/Applications/FreeCAD.app/Contents/MacOS/FreeCAD script.py`) renders, closes the document and quits cleanly; verified in this session with no `.FCStd` write-back. The MCP path stays documented for the board import only.
- The step face belongs to the **deck** (a "hood": top plate + step face), not the tray. A tray wall crossing the board mid-span could not reach the floor, and a wall floating 6 mm above the floor is unprintable. The tray's side walls simply step from Z 9 to Z 45 at `y_step`.
- The keyboard frame is fixed by two screws in the front rim ledge and is held down at the rear by the hood's step face resting on it. No screws near the switches: the key field runs to 0.3 mm from the board edges, so there is no room for bosses beside it.
- The floor is the inclined bottom plate; bosses grow toward the rear. No solid wedge.

## Verified facts the code relies on (measured this session)

| Object | Label prefix in the assembly | Board-frame box |
|---|---|---|
| PCB | `Pcb_` | X 6.35..273.05, Y −209.55..−6.35, Z −1.6..0 |
| J1 RCA | `J1_` | X 229.15..240.75, Y −16.24..−1.74, Z −4.2..12.4 |
| J2 barrel | `J2_` | X 31.74..41.14, Y −20.67..−6.17, Z −2.76..12.14 |
| J4 DIN‑8 | `J4_` | X 92.51..113.21, Y −25.35..−6.60, Z −3.44..21.46 |
| J5 DE‑9 | `J5_` | X 181.40..212.20, Y −19.10..−0.66, Z −5.4..12.5 |
| J6 header | `J6_` | X 128.25..168.93, Y −17.38..−8.28, Z −3.0..9.1 |
| SW68 reset | `SW68_` | X 17.24..25.94, Y −12.96..−0.11, Z −3.51..7.39 |
| U25 regulator | `U25_` | X 45.67..55.92, Y −10.19..−5.73, Z −9.75..18.77 |
| SP1 speaker | `SP1_` | X 251.81..263.81, Y −19.97..−7.97, Z −5.0..9.3 |
| D10, D11 LEDs | `D10_`, `D11_` | X 204.88..208.28 / 223.93..227.33, Y −106.68..−102.88, Z to 8.3 |
| caps | label `caps` | 67 solids |

Component objects are the direct children of the group labelled `Top_…`; their `.Shape` is already in the global frame for `Part::Feature`, `App::Link` and `App::Part` alike. Children *of* a refdes `App::Part` are in local coordinates and must be skipped. Opening the assembly headlessly takes 0.4 s.

Board holes in the KiCad file appear as `(footprint "My_Components:Hole_3mm"` followed within four lines by `(at X Y)`. Seven of them.

`makeOffsetShape(-0.8, 0.01)` on a 1.2 mm plate raises `ValueError: Null shape`; on a 3 mm plate it returns a solid. The printability check treats the exception as "vanished".

---

### Task 1: Parameter file, loader, and the test runner

**Files:**
- Create: `case.tsv`
- Create: `tools/case/__init__.py` (empty)
- Create: `tools/case/params.py`
- Create: `tools/test_case.py`
- Create: `tools/case/tests/__init__.py` (empty)
- Create: `tools/case/tests/test_params.py`

**Interfaces:**
- Produces: `tools.case.params.load(path=None) -> Params`; `Params` has attribute access (`p.wall` → float, `p.opening_mode` → str), `p.raw` (dict of str), `p.drives` (dict key→str), `p.hash()` → sha1 hex of the file bytes, `p.path`. `params.REQUIRED` is the tuple of keys every `case.tsv` must contain. Raises `params.ParamError` on any defect.
- Produces: `$FC tools/test_case.py [module ...]` runs unittest modules under `tools/case/tests`, exit 0/1.

- [ ] **Step 1: Write `case.tsv`**

```tsv
# Radio-86RK case parameters. One row per number. Board-derived numbers
# (outline, holes, port positions, key field) are NOT here: build_case.py
# reads them from the pinned board and the assembly every run.
#
# key	value	drives
wall	2.4	tray, hood, rear plate: vertical wall thickness
plate	3.0	frame, hood, rear plate, lid, covers: plate thickness
board_gap	1.5	tray: board edge to wall inner face
chamfer	3.0	tray, hood: outer edge chamfer (polish task)
rim_z	18	tray: top of the front rim above the board
rim_depth	10	tray: front rim thickness front-to-back
rim_ledge	5	tray: ledge inside the rim that the frame rests on
frame_z	9	tray, frame: underside of the keyboard frame plate
deck_z	45	tray, hood, rear plate, lid: underside of the rear-tier deck plate
step_gap	2.5	hood: distance from the key envelope's rear edge to the step face
step_angle	90	hood: step face angle from horizontal (polish task makes it 60)
wedge_angle	6	tray, rear plate: underside incline, thin end at the front
standoff	5	tray: floor top to board bottom at the front bosses
pad_d	10	tray: rubber pad recess diameter underneath
key_offset	1.0	frame: opening margin around every key footprint
opening_mode	outline	frame: outline (follows blocks) or hull (one rectangle)
led_mode	hole	frame: hole (Ø3.4) or light_pipe (Ø4 counterbore)
led_hole_d	3.4	frame: LED hole diameter in hole mode
port_margin	0.5	rear plate: cutout margin around a connector section
plug_margin	1.0	rear plate: extra margin for connectors that stop short of the plate
reset_margin	1.25	rear plate: margin around the reset button section
hinge_z	26	rear plate, lid: hinge axis height above the board
lid_w	60	rear plate, lid: window and lid width, centred on J6
lid_depth	25	lid: top face depth front-to-back
stud_d	5.0	lid: spherical stud diameter
stud_interference	0.3	lid: stud diameter minus socket diameter
throat_undersize	0.4	rear plate: keyhole throat narrower than the stud by this much
socket_block	6	rear plate: socket block width beside the window
lid_notch	1	lid: 1 cuts a 34x3 ribbon notch in the rear face, 0 does not
labels	0	rear plate: 1 adds 0.6 mm label recesses (option, off)
vent_w	2	hood: vent slot width
vent_l	40	hood: vent slot length front-to-back
vent_pitch	5	hood: vent slot pitch
vent_regions	left,right	hood: which regions get vents (left over U25/U26, right over SP1)
bay_side	left	tray, bay cover: left, right or none
bay_w	60	tray, bay cover: bay opening width
bay_h	20	tray, bay cover: bay opening height
bay_z	20	tray, bay cover: bay opening bottom above the board
insert_d	4.0	all: heat-set insert hole diameter for M3
insert_depth	6	all: heat-set insert hole depth
boss_d	7	tray: boss diameter around an insert
screw_clear_d	3.4	all: M3 clearance hole diameter
foot_heights	10,20	feet: the two foot heights
max_tile	256	tiling: largest part footprint any preset prints, mm
tile_gap	0.2	tiling: clearance at a tile seam
pin_d	3	tiling: alignment pin diameter
preset	standard	tiling: mini (180), standard (256) or large (300); explicit max_tile wins
eprom_hatches	0	hood: 1 cuts the U10/U11 hatches (option, off)
```

- [ ] **Step 2: Write the failing test `tools/case/tests/test_params.py`**

```python
import os
import unittest

from tools.case import params

REPO = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))))


class LoadTest(unittest.TestCase):
    def test_defaults_load_and_are_typed(self):
        p = params.load()
        self.assertEqual(p.wall, 2.4)
        self.assertEqual(p.opening_mode, "outline")
        self.assertEqual(p.vent_regions, "left,right")
        self.assertEqual(p.foot_heights, "10,20")
        self.assertIn("tray", p.drives["wall"])
        self.assertEqual(len(p.hash()), 40)

    def test_every_required_key_present(self):
        p = params.load()
        for key in params.REQUIRED:
            self.assertIn(key, p.raw, key)

    def test_missing_drives_is_an_error(self):
        path = os.path.join(REPO, ".build", "test_params_bad.tsv")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as h:
            h.write("wall\t2.4\t\n")
        with self.assertRaises(params.ParamError):
            params.load(path)

    def test_unknown_key_is_an_error(self):
        path = os.path.join(REPO, ".build", "test_params_unknown.tsv")
        with open(os.path.join(REPO, "case.tsv")) as h:
            text = h.read()
        with open(path, "w") as h:
            h.write(text + "wal\t2.4\ttypo\n")
        with self.assertRaises(params.ParamError):
            params.load(path)

    def test_preset_sets_max_tile_when_not_explicit(self):
        p = params.load()
        self.assertEqual(p.max_tile, 256)
        self.assertEqual(params.preset_tile("mini"), 180)
        self.assertEqual(params.preset_tile("large"), 300)
```

- [ ] **Step 3: Write the test runner `tools/test_case.py`**

```python
"""Run the case package's unit tests under freecadcmd.

    $FC tools/test_case.py                # every tools/case/tests/test_*.py
    $FC tools/test_case.py test_tray      # one module

pytest cannot import Part; unittest can run inside freecadcmd. Exit 0 when
every test passes, 1 otherwise -- and always flush, because freecadcmd drops
unflushed stdout on sys.exit.
"""
import os
import sys
import traceback
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO not in sys.path:
    sys.path.insert(0, REPO)


def main():
    names = sys.argv[2:]
    tests_dir = os.path.join(REPO, "tools", "case", "tests")
    loader = unittest.defaultTestLoader
    if names:
        suite = unittest.TestSuite(
            loader.loadTestsFromName("tools.case.tests." + n) for n in names)
    else:
        suite = loader.discover(tests_dir, pattern="test_*.py",
                                top_level_dir=REPO)
    result = unittest.TextTestRunner(stream=sys.stdout, verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


def _is_entry_script():
    return __name__ == "__main__" or (
        len(sys.argv) > 1
        and os.path.normcase(os.path.realpath(sys.argv[1]))
        == os.path.normcase(os.path.realpath(__file__)))


if _is_entry_script():
    try:
        rc = main()
    except Exception:                                        # noqa: BLE001
        traceback.print_exc()
        rc = 1
    sys.stdout.flush()
    sys.exit(rc)
```

- [ ] **Step 4: Run the test to verify it fails**

Run: `$FC tools/test_case.py test_params 2>&1 | grep -v 3Dconnexion`
Expected: `ModuleNotFoundError: No module named 'tools.case.params'` (or ImportError) and exit 1.

- [ ] **Step 5: Write `tools/case/params.py`**

```python
"""case.tsv: one row per number, with a column saying what it drives.

Same shape as params.tsv. Values that parse as float are floats; anything
else stays a string (opening_mode, vent_regions, foot_heights, preset).
"""
import hashlib
import os

REPO = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
DEFAULT_PATH = os.path.join(REPO, "case.tsv")

REQUIRED = (
    "wall", "plate", "board_gap", "chamfer", "rim_z", "rim_depth",
    "rim_ledge", "frame_z", "deck_z", "step_gap", "step_angle",
    "wedge_angle", "standoff", "pad_d", "key_offset", "opening_mode",
    "led_mode", "led_hole_d", "port_margin", "plug_margin", "reset_margin",
    "hinge_z", "lid_w", "lid_depth", "stud_d", "stud_interference",
    "throat_undersize", "socket_block", "lid_notch", "labels", "vent_w",
    "vent_l", "vent_pitch", "vent_regions", "bay_side", "bay_w", "bay_h",
    "bay_z", "insert_d", "insert_depth", "boss_d", "screw_clear_d",
    "foot_heights", "max_tile", "tile_gap", "pin_d", "preset",
    "eprom_hatches",
)

PRESETS = {"mini": 180.0, "standard": 256.0, "large": 300.0}


class ParamError(Exception):
    """case.tsv is malformed: exit 2 territory, never a verdict."""


def preset_tile(name):
    if name not in PRESETS:
        raise ParamError("unknown preset %r; known: %s"
                         % (name, ", ".join(sorted(PRESETS))))
    return PRESETS[name]


class Params(object):
    def __init__(self, raw, drives, path):
        self.raw = raw
        self.drives = drives
        self.path = path

    def __getattr__(self, key):
        raw = self.__dict__.get("raw", {})
        if key not in raw:
            raise AttributeError(key)
        value = raw[key]
        try:
            return float(value)
        except ValueError:
            return value

    def list(self, key):
        """Comma-separated string row -> list of stripped strings."""
        return [s.strip() for s in self.raw[key].split(",") if s.strip()]

    def floats(self, key):
        return [float(s) for s in self.list(key)]

    def hash(self):
        with open(self.path, "rb") as handle:
            return hashlib.sha1(handle.read()).hexdigest()


def load(path=None):
    path = path or DEFAULT_PATH
    if not os.path.exists(path):
        raise ParamError("no %s" % path)
    raw, drives = {}, {}
    with open(path) as handle:
        for lineno, line in enumerate(handle, 1):
            line = line.rstrip("\n")
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            parts = line.split("\t")
            if len(parts) != 3:
                raise ParamError("%s:%d: expected 3 tab-separated fields, "
                                 "got %d: %r" % (path, lineno, len(parts),
                                                 line))
            key, value, what = parts
            if key not in REQUIRED:
                raise ParamError("%s:%d: unknown key %r" % (path, lineno, key))
            if not what.strip():
                raise ParamError("%s:%d: %r has an empty drives column"
                                 % (path, lineno, key))
            if key in raw:
                raise ParamError("%s:%d: duplicate key %r" % (path, lineno, key))
            raw[key] = value
            drives[key] = what
    missing = [k for k in REQUIRED if k not in raw]
    if missing:
        raise ParamError("%s: missing keys: %s" % (path, ", ".join(missing)))
    p = Params(raw, drives, path)
    if p.raw["opening_mode"] not in ("outline", "hull"):
        raise ParamError("opening_mode must be outline or hull")
    if p.raw["led_mode"] not in ("hole", "light_pipe"):
        raise ParamError("led_mode must be hole or light_pipe")
    if p.raw["bay_side"] not in ("left", "right", "none"):
        raise ParamError("bay_side must be left, right or none")
    preset_tile(p.raw["preset"])
    return p
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `$FC tools/test_case.py test_params 2>&1 | grep -v 3Dconnexion`
Expected: `Ran 5 tests` … `OK`, exit 0.

- [ ] **Step 7: Commit**

```bash
git add case.tsv tools/case/__init__.py tools/case/params.py tools/test_case.py tools/case/tests/__init__.py tools/case/tests/test_params.py
git commit -m "Case parameters: case.tsv, loader, and a unittest runner under freecadcmd"
```

---

### Task 2: Board reader

**Files:**
- Create: `tools/case/board.py`
- Create: `tools/case/tests/test_board.py`

**Interfaces:**
- Produces: `tools.case.board.load(assembly=None, envelope=None, pcb=None) -> Board` with attributes `xmin, xmax, ymin, ymax` (board outline, board frame), `thickness` (1.6), `corner_r` (2.54), `holes` (list of `(x, y)` in board frame), `key` (object with `xmin, xmax, ymin, ymax, zmin, zmax` of the envelope), `components` (list of `(ref, shape)`), method `component(ref) -> shape` (raises `KeyError`), method `components_matching(prefixes)`; constants `EXTERNAL_REFS = ("J1", "J2", "J4", "J5", "SW68")`, `EXPANSION_REF = "J6"`, `LED_REFS = ("D10", "D11")`, `HATCH_REFS = ("U10", "U11")`.
- Produces: `board.obox(shape)`.
- Consumes: `tools.board_index.BOARD` and `.PCB` for paths.

- [ ] **Step 1: Write the failing test `tools/case/tests/test_board.py`**

```python
import unittest

from tools.case import board


class BoardTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.b = board.load()

    def test_outline_matches_the_pcb_solid(self):
        b = self.b
        self.assertAlmostEqual(b.xmin, 6.35, 2)
        self.assertAlmostEqual(b.xmax, 273.05, 2)
        self.assertAlmostEqual(b.ymin, -209.55, 2)
        self.assertAlmostEqual(b.ymax, -6.35, 2)
        self.assertEqual(b.thickness, 1.6)

    def test_seven_holes_in_board_frame(self):
        holes = sorted(self.b.holes)
        self.assertEqual(len(holes), 7)
        self.assertIn((11.43, -11.43), holes)
        self.assertIn((139.7, -110.49), holes)
        self.assertIn((207.01, -204.47), holes)

    def test_key_field_from_envelope(self):
        k = self.b.key
        self.assertAlmostEqual(k.xmin, 6.675, 2)
        self.assertAlmostEqual(k.ymax, -95.575, 2)
        self.assertAlmostEqual(k.zmax, 22.743, 2)

    def test_external_connectors_found_in_global_frame(self):
        b = self.b
        j6 = board.obox(b.component("J6"))
        self.assertAlmostEqual(j6.XMin, 128.25, 1)
        self.assertAlmostEqual(j6.ZMax, 9.1, 1)
        j4 = board.obox(b.component("J4"))
        self.assertAlmostEqual(j4.ZMax, 21.46, 1)
        sw = board.obox(b.component("SW68"))
        self.assertAlmostEqual(sw.YMax, -0.11, 1)
        for ref in board.EXTERNAL_REFS + (board.EXPANSION_REF,) + board.LED_REFS:
            b.component(ref)

    def test_children_of_refdes_parts_are_not_listed(self):
        refs = [ref for ref, _ in self.b.components]
        self.assertNotIn("B3F", refs)
        self.assertNotIn("B32", refs)
        self.assertGreater(len(refs), 150)
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `$FC tools/test_case.py test_board 2>&1 | grep -v 3Dconnexion`
Expected: ImportError on `tools.case.board`, exit 1.

- [ ] **Step 3: Write `tools/case/board.py`**

```python
"""The board as the case sees it, in the board frame.

Board frame = the frame of model/envelope.step and the assembly: X as
KiCad, Y = -(KiCad Y), Z = 0 at the board's top face. Nothing here is
copied into case.tsv; every run re-reads the pinned checkout and the
assembly so the case cannot drift from the board.
"""
import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
TOOLS = os.path.join(REPO, "tools")
if TOOLS not in sys.path:
    sys.path.insert(0, TOOLS)
import board_index                                          # noqa: E402

MODEL = os.path.join(REPO, "model")
ASSEMBLY = os.path.join(MODEL, "radio86rk-assembly.FCStd")
ENVELOPE = os.path.join(MODEL, "envelope.step")

EXTERNAL_REFS = ("J1", "J2", "J4", "J5", "SW68")
EXPANSION_REF = "J6"
LED_REFS = ("D10", "D11")
HATCH_REFS = ("U10", "U11")
BOARD_THICKNESS = 1.6
CORNER_R = 2.54          # Edge.Cuts arcs; only the tray's inner corners use it

_HOLE_RE = re.compile(
    r'\(footprint "My_Components:Hole_3mm"(?:(?!\(footprint ).)*?'
    r'\(at ([-\d.]+) ([-\d.]+)', re.S)
_REF_RE = re.compile(r'^([A-Z]+\d+)_')


def obox(shape):
    """Exact bounds; Shape.BoundBox over-reports NURBS and is banned."""
    return shape.optimalBoundingBox()


class Box(object):
    def __init__(self, bb):
        self.xmin, self.xmax = bb.XMin, bb.XMax
        self.ymin, self.ymax = bb.YMin, bb.YMax
        self.zmin, self.zmax = bb.ZMin, bb.ZMax


class Board(object):
    def __init__(self, outline, holes, key, components):
        self.xmin, self.xmax, self.ymin, self.ymax = outline
        self.thickness = BOARD_THICKNESS
        self.corner_r = CORNER_R
        self.holes = holes
        self.key = key
        self.components = components
        self._by_ref = dict(components)

    def component(self, ref):
        return self._by_ref[ref]

    def components_matching(self, prefixes):
        return [(r, s) for r, s in self.components if r.startswith(prefixes)]

    @property
    def width(self):
        return self.xmax - self.xmin

    @property
    def depth(self):
        return self.ymax - self.ymin


def read_holes(pcb_path):
    with open(pcb_path) as handle:
        text = handle.read()
    holes = [(float(x), -float(y)) for x, y in _HOLE_RE.findall(text)]
    if len(holes) != 7:
        raise ValueError("expected 7 Hole_3mm footprints in %s, found %d"
                         % (pcb_path, len(holes)))
    return holes


def read_assembly(path):
    """Return (outline, [(ref, shape)]) from the tracked assembly.

    Components are the direct children of the ksu 'Top_*' group. Their
    .Shape is global for Part::Feature, App::Link and App::Part alike; the
    children OF a refdes App::Part are in local coordinates and are skipped
    because they are not Top's children.
    """
    import FreeCAD
    doc = FreeCAD.openDocument(path)
    try:
        tops = [o for o in doc.Objects if o.Label.startswith("Top_")]
        if len(tops) != 1:
            raise ValueError("%s: expected one Top_* group, found %d"
                             % (path, len(tops)))
        top = tops[0]
        pcbs = [o for o in doc.Objects if o.Label.startswith("Pcb_")]
        if len(pcbs) != 1:
            raise ValueError("%s: expected one Pcb_* object" % path)
        bb = obox(pcbs[0].Shape)
        outline = (bb.XMin, bb.XMax, bb.YMin, bb.YMax)
        components = []
        for obj in top.Group:
            if not hasattr(obj, "Shape") or obj.Shape.isNull():
                continue
            match = _REF_RE.match(obj.Label)
            if not match:
                continue
            components.append((match.group(1), obj.Shape.copy()))
        caps = doc.getObjectsByLabel("caps")
        if caps:
            components.append(("caps", caps[0].Shape.copy()))
    finally:
        FreeCAD.closeDocument(doc.Name)
    return outline, components


def read_key_field(path):
    import Part
    shape = Part.Shape()
    shape.read(path)
    if len(shape.Solids) != 67:
        raise ValueError("%s holds %d solids, expected 67"
                         % (path, len(shape.Solids)))
    return Box(obox(shape))


def load(assembly=None, envelope=None, pcb=None):
    assembly = assembly or ASSEMBLY
    envelope = envelope or ENVELOPE
    pcb = pcb or board_index.PCB
    for path in (assembly, envelope, pcb):
        if not os.path.exists(path):
            raise IOError("no %s" % path)
    outline, components = read_assembly(assembly)
    return Board(outline, read_holes(pcb), read_key_field(envelope),
                 components)
```

Note on `top.Group`: if `Top_*` turns out not to expose `.Group` (it is an `App::Part`, which does), fall back to `[o for o in doc.Objects if top in o.InList]`.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `$FC tools/test_case.py test_board 2>&1 | grep -v 3Dconnexion`
Expected: `Ran 5 tests` … `OK`. If `test_children_of_refdes_parts_are_not_listed` fails with `B3F` present, the `Top_` group is exposing grandchildren: filter with `obj.InList` containing `top` and nothing else labelled with a refdes.

- [ ] **Step 5: Commit**

```bash
git add tools/case/board.py tools/case/tests/test_board.py
git commit -m "Case: read outline, holes, key field and component solids from the board"
```

---

### Task 3: Layout and geometry helpers

**Files:**
- Create: `tools/case/layout.py`
- Create: `tools/case/geom.py`
- Create: `tools/case/tests/test_layout.py`

**Interfaces:**
- Produces: `tools.case.layout.Layout(p, b)` with derived coordinates (all floats, board frame):
  - `x0i, x1i` inner wall faces; `x0o, x1o` outer faces
  - `y_front_i` inner face of the front rim (= `b.ymin - board_gap`); `y_front_o` outer face (= `y_front_i - rim_depth`); `y_ledge` (= `y_front_i - rim_ledge`)
  - `y_rear_i` rear plate inner face (= `b.ymax + board_gap`); `y_rear_o` (= `y_rear_i + plate`)
  - `y_step` step face front (= `b.key.ymax + step_gap`); `y_step_back` (= `y_step + wall`)
  - `z_board_bottom` (−1.6); `z_floor_front` (= `z_board_bottom - standoff`, floor top at the front edge); `z_under_front` (= `z_floor_front - wall`)
  - `z_frame` (= `frame_z`), `z_frame_top` (+plate), `z_rim`, `z_deck`, `z_deck_top`
  - `x_j6`, `x_win0`, `x_win1` (J6 centre and window edges), `z_hinge`
  - methods `under_z(y)` (underside plane Z at Y), `floor_z(y)` (= `under_z(y) + wall`), `outer_box()` → `(x0o, x1o, y_front_o, y_rear_o)`
  - `hood_bosses` → list of 4 `(x, y)` centres; `frame_screws` → list of 2 `(x, y)`; `rear_plate_screws` → list of 4 `(x, z)`
- Produces: `tools.case.geom`: `V` (FreeCAD.Vector), `prism(x0, x1, y0, y1, z0, z1)`, `rounded_prism(x0, x1, y0, y1, z0, z1, r)`, `cyl_z(x, y, z0, z1, d)`, `cyl_y(x, z, y0, y1, d)`, `below_plane(L, margin=200)` (a huge solid occupying everything below the underside plane; cut it away), `between_planes(L, thickness)` (slab from the underside plane up `thickness`, clipped to `outer_box`), `vertical_edges(shape)`, `fuse_all(shapes)`, `cut_all(shape, tools)`, `obox`.

- [ ] **Step 1: Write the failing test `tools/case/tests/test_layout.py`**

```python
import math
import unittest

from tools.case import board, geom, layout, params


class LayoutTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.p = params.load()
        cls.b = board.load()
        cls.L = layout.Layout(cls.p, cls.b)

    def test_inner_and_outer_walls(self):
        L = self.L
        self.assertAlmostEqual(L.x0i, 4.85, 3)
        self.assertAlmostEqual(L.x1i, 274.55, 3)
        self.assertAlmostEqual(L.x0o, 2.45, 3)
        self.assertAlmostEqual(L.y_rear_i, -4.85, 3)
        self.assertAlmostEqual(L.y_rear_o, -1.85, 3)
        self.assertAlmostEqual(L.y_front_i, -211.05, 3)
        self.assertAlmostEqual(L.y_front_o, -221.05, 3)
        self.assertAlmostEqual(L.y_step, -93.075, 3)

    def test_underside_drops_toward_the_rear(self):
        L = self.L
        self.assertAlmostEqual(L.under_z(L.y_front_o), -9.0, 3)
        drop = (L.y_rear_o - L.y_front_o) * math.tan(math.radians(6))
        self.assertAlmostEqual(L.under_z(L.y_rear_o), -9.0 - drop, 3)
        self.assertLess(L.under_z(L.y_rear_o), L.under_z(L.y_front_o))

    def test_window_sits_between_din_and_de9(self):
        L = self.L
        self.assertAlmostEqual(L.x_j6, 148.59, 1)
        self.assertGreater(L.x_win0, 113.21 + 1.0)
        self.assertLess(L.x_win1, 181.40 - 1.0)

    def test_below_plane_is_below(self):
        L = self.L
        cut = geom.below_plane(L)
        # A point just under the front outer edge is inside the cut solid;
        # a point just above it is not.
        self.assertTrue(cut.isInside(geom.V(100, L.y_front_o + 1, -9.5), 1e-6, True))
        self.assertFalse(cut.isInside(geom.V(100, L.y_front_o + 1, -8.5), 1e-6, True))
        # At the rear the plane is lower.
        self.assertTrue(cut.isInside(geom.V(100, L.y_rear_o - 1, -20.0), 1e-6, True))

    def test_between_planes_is_a_wall_thick_slab(self):
        L = self.L
        slab = geom.between_planes(L, self.p.wall)
        bb = geom.obox(slab)
        self.assertAlmostEqual(bb.XMin, L.x0o, 2)
        self.assertAlmostEqual(bb.XMax, L.x1o, 2)
        self.assertAlmostEqual(bb.ZMax, -9.0 + self.p.wall, 1)
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `$FC tools/test_case.py test_layout 2>&1 | grep -v 3Dconnexion`
Expected: ImportError, exit 1.

- [ ] **Step 3: Write `tools/case/geom.py`**

```python
"""Small Part helpers shared by every part module. Pure geometry, no I/O."""
import math

import FreeCAD
import Part

V = FreeCAD.Vector
BIG = 2000.0


def obox(shape):
    return shape.optimalBoundingBox()


def prism(x0, x1, y0, y1, z0, z1):
    return Part.makeBox(x1 - x0, y1 - y0, z1 - z0, V(x0, y0, z0))


def vertical_edges(shape):
    out = []
    for e in shape.Edges:
        if e.Length < 1e-6:
            continue
        t = e.tangentAt(e.FirstParameter)
        if abs(t.z) > 0.999:
            out.append(e)
    return out


def rounded_prism(x0, x1, y0, y1, z0, z1, r):
    box = prism(x0, x1, y0, y1, z0, z1)
    if r <= 0:
        return box
    return box.makeFillet(r, vertical_edges(box))


def cyl_z(x, y, z0, z1, d):
    return Part.makeCylinder(d / 2.0, z1 - z0, V(x, y, z0), V(0, 0, 1))


def cyl_y(x, z, y0, y1, d):
    return Part.makeCylinder(d / 2.0, y1 - y0, V(x, y0, z), V(0, 1, 0))


def fuse_all(shapes):
    shapes = [s for s in shapes if s is not None]
    if not shapes:
        raise ValueError("nothing to fuse")
    out = shapes[0]
    if len(shapes) > 1:
        out = out.fuse(shapes[1:])
    return out.removeSplitter()


def cut_all(shape, tools):
    tools = [t for t in tools if t is not None]
    if not tools:
        return shape
    return shape.cut(tools).removeSplitter()


def _tilted_box(L, z_top, height):
    """A BIG box whose TOP face lies on the plane z = z_top at y_front_o,
    inclined by -wedge_angle about the X axis through that edge, so the
    top face drops toward the rear (+Y). Right-hand rule about +X: a
    positive angle lifts +Y toward +Z, so the drop needs the negative."""
    box = Part.makeBox(BIG, BIG, height,
                       V(-BIG / 2.0, L.y_front_o - BIG / 2.0, z_top - height))
    box.rotate(V(0, L.y_front_o, z_top), V(1, 0, 0), -L.p.wedge_angle)
    return box


def below_plane(L, margin=200.0):
    """Everything below the underside plane: cut it from tray and rear plate."""
    return _tilted_box(L, L.z_under_front, margin + 60.0)


def between_planes(L, thickness):
    """The floor: a slab of `thickness` sitting on the underside plane,
    clipped to the outer footprint. Its top follows the incline too."""
    lower = _tilted_box(L, L.z_under_front, 400.0)
    upper = _tilted_box(L, L.z_under_front + thickness, 400.0)
    slab = upper.cut(lower)
    x0, x1, y0, y1 = L.outer_box()
    clip = prism(x0, x1, y0, y1, -400, 400)
    return slab.common(clip).removeSplitter()
```

- [ ] **Step 4: Write `tools/case/layout.py`**

```python
"""Every derived coordinate in one place, so parts agree by construction.

Board frame throughout. Front = keyboard edge = smaller Y. Rear = ports =
larger Y (the rear edge is Y -6.35).
"""
import math


class Layout(object):
    def __init__(self, p, b):
        self.p, self.b = p, b
        # X walls
        self.x0i = b.xmin - p.board_gap
        self.x1i = b.xmax + p.board_gap
        self.x0o = self.x0i - p.wall
        self.x1o = self.x1i + p.wall
        # Y: front rim, step, rear plate
        self.y_front_i = b.ymin - p.board_gap
        self.y_front_o = self.y_front_i - p.rim_depth
        self.y_ledge = self.y_front_i - p.rim_ledge
        self.y_rear_i = b.ymax + p.board_gap
        self.y_rear_o = self.y_rear_i + p.plate
        self.y_step = b.key.ymax + p.step_gap
        self.y_step_back = self.y_step + p.wall
        # Z
        self.z_board_bottom = -b.thickness
        self.z_floor_front = self.z_board_bottom - p.standoff
        self.z_under_front = self.z_floor_front - p.wall
        self.z_frame = p.frame_z
        self.z_frame_top = p.frame_z + p.plate
        self.z_rim = p.rim_z
        self.z_deck = p.deck_z
        self.z_deck_top = p.deck_z + p.plate
        self.z_hinge = p.hinge_z
        # J6 window
        from tools.case.board import obox
        j6 = obox(b.component("J6"))
        self.x_j6 = (j6.XMin + j6.XMax) / 2.0
        self.x_win0 = self.x_j6 - p.lid_w / 2.0
        self.x_win1 = self.x_j6 + p.lid_w / 2.0
        # Fastener positions (see spec §4 and the plan's deviations)
        bx = p.boss_d / 2.0 - 1.5          # boss centre 2.0 mm inside the wall face
        self.hood_bosses = [
            (self.x0i + bx, -86.5), (self.x1i - bx, -86.5),
            (self.x0i + bx, -8.35), (self.x1i - bx, -8.35),
        ]
        y_screw = self.y_front_i - p.rim_ledge / 2.0
        self.frame_screws = [(30.0, y_screw), (250.0, y_screw)]
        self.rear_plate_screws = [(self.x0i + 3.0, 23.0), (self.x0i + 3.0, 39.0),
                                  (self.x1i - 3.0, 23.0), (self.x1i - 3.0, 39.0)]

    def under_z(self, y):
        return self.z_under_front - (y - self.y_front_o) * math.tan(
            math.radians(self.p.wedge_angle))

    def floor_z(self, y):
        return self.under_z(y) + self.p.wall

    def outer_box(self):
        return (self.x0o, self.x1o, self.y_front_o, self.y_rear_o)
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `$FC tools/test_case.py test_layout 2>&1 | grep -v 3Dconnexion`
Expected: `Ran 5 tests` … `OK`. If `test_below_plane_is_below` fails on the rear point, the rotation sign is inverted: flip the sign in `_tilted_box` and re-run. Do not adjust the test.

- [ ] **Step 6: Commit**

```bash
git add tools/case/layout.py tools/case/geom.py tools/case/tests/test_layout.py
git commit -m "Case: shared layout coordinates and Part helpers, wedge plane verified"
```

---

### Task 4: Tray

**Files:**
- Create: `tools/case/tray.py`
- Create: `tools/case/tests/test_tray.py`

**Interfaces:**
- Produces: `tools.case.tray.tray(p, b, L) -> Part.Solid`; `tray.bay_opening_box(p, b, L) -> Part.Solid or None` (the box cut out of the side wall; also used by the bay cover); `tray.board_bosses(p, b, L) -> list[Part.Solid]`.

Geometry, in words: outer footprint `x0o..x1o × y_front_o..y_rear_o`. Side walls: front tier (`y_front_o..y_step`) up to `z_frame`; rear tier (`y_step..y_rear_o`) up to `z_deck`. Front rim block `y_front_o..y_front_i` up to `z_rim`, with a ledge rebate `y_ledge..y_front_i` above `z_frame`. Rear is open (rear plate closes it). Floor = `between_planes(L, wall)`. Seven board bosses from the floor to `z_board_bottom`, Ø `boss_d`, with Ø `insert_d` holes `insert_depth` deep from the top. Four hood bosses Ø `boss_d` hung on the side walls from Z 2 to `z_deck` with insert holes from the top; the two rear ones are 6 × 7 blocks that also carry the two horizontal rear-plate insert holes each. Frame insert holes in the rim ledge at `frame_screws`. Four Ø `pad_d` × 1 recesses under the corners. Bay opening cut from the chosen side wall. Everything cut by `below_plane`.

- [ ] **Step 1: Write the failing test `tools/case/tests/test_tray.py`**

```python
import unittest

from tools.case import board, geom, layout, params, tray


class TrayTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.p = params.load()
        cls.b = board.load()
        cls.L = layout.Layout(cls.p, cls.b)
        cls.t = tray.tray(cls.p, cls.b, cls.L)

    def test_is_one_valid_solid(self):
        self.assertTrue(self.t.isValid())
        self.assertEqual(len(self.t.Solids), 1)

    def test_footprint_and_heights(self):
        L, bb = self.L, geom.obox(self.t)
        self.assertAlmostEqual(bb.XMin, L.x0o, 2)
        self.assertAlmostEqual(bb.XMax, L.x1o, 2)
        self.assertAlmostEqual(bb.YMin, L.y_front_o, 2)
        self.assertAlmostEqual(bb.YMax, L.y_rear_o, 2)
        self.assertAlmostEqual(bb.ZMax, L.z_deck, 2)
        self.assertAlmostEqual(bb.ZMin, L.under_z(L.y_rear_o), 1)

    def test_board_sits_on_seven_bosses(self):
        L, t = self.L, self.t
        for x, y in self.b.holes:
            # material just under the board, around the hole
            self.assertTrue(t.isInside(geom.V(x + 2.6, y, L.z_board_bottom - 0.5), 1e-6, True), (x, y))
            # the insert hole itself is empty
            self.assertFalse(t.isInside(geom.V(x, y, L.z_board_bottom - 0.5), 1e-6, True), (x, y))

    def test_board_volume_is_empty(self):
        b, L, t = self.b, self.L, self.t
        for x, y in ((50.0, -50.0), (140.0, -150.0), (260.0, -100.0)):
            self.assertFalse(t.isInside(geom.V(x, y, -0.8), 1e-6, True))
            self.assertFalse(t.isInside(geom.V(x, y, 5.0), 1e-6, True))

    def test_side_walls_step_at_y_step(self):
        L, t = self.L, self.t
        xw = (L.x0o + L.x0i) / 2.0
        self.assertTrue(t.isInside(geom.V(xw, L.y_step + 5, L.z_deck - 1), 1e-6, True))
        self.assertFalse(t.isInside(geom.V(xw, L.y_step - 5, L.z_frame + 1), 1e-6, True))
        self.assertTrue(t.isInside(geom.V(xw, L.y_step - 5, L.z_frame - 1), 1e-6, True))

    def test_front_rim_has_a_ledge(self):
        L, t = self.L, self.t
        y_rim = (L.y_front_o + L.y_ledge) / 2.0
        y_ledge = (L.y_ledge + L.y_front_i) / 2.0
        self.assertTrue(t.isInside(geom.V(140, y_rim, L.z_rim - 1), 1e-6, True))
        self.assertFalse(t.isInside(geom.V(140, y_ledge, L.z_frame + 1), 1e-6, True))
        self.assertTrue(t.isInside(geom.V(140, y_ledge, L.z_frame - 1), 1e-6, True))

    def test_rear_is_open(self):
        L, t = self.L, self.t
        self.assertFalse(t.isInside(geom.V(140, L.y_rear_i + 1.5, 10.0), 1e-6, True))

    def test_bay_opening_on_the_left(self):
        L, t, p = self.L, self.t, self.p
        xw = (L.x0o + L.x0i) / 2.0
        y_mid = (L.y_step + L.y_rear_i) / 2.0
        self.assertFalse(t.isInside(geom.V(xw, y_mid, p.bay_z + p.bay_h / 2.0), 1e-6, True))
        self.assertTrue(t.isInside(geom.V(L.x1o - 1.2, y_mid, p.bay_z + p.bay_h / 2.0), 1e-6, True))

    def test_hood_bosses_have_insert_holes(self):
        L, t = self.L, self.t
        for x, y in L.hood_bosses:
            self.assertFalse(t.isInside(geom.V(x, y, L.z_deck - 1), 1e-6, True), (x, y))
            self.assertTrue(t.isInside(geom.V(x, y, L.z_deck - self.p.insert_depth - 1), 1e-6, True), (x, y))
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `$FC tools/test_case.py test_tray 2>&1 | grep -v 3Dconnexion`
Expected: ImportError on `tools.case.tray`, exit 1.

- [ ] **Step 3: Write `tools/case/tray.py`**

```python
"""The tray: floor, walls, bosses. The PCB is the chassis; this holds it."""
from tools.case import geom
from tools.case.geom import V, prism, cyl_z, cyl_y, fuse_all, cut_all

Z_BOSS_FOOT = 2.0        # hung bosses start above the board surface
Z_LOW = -80.0            # deep enough to be cut by the underside plane


def board_bosses(p, b, L):
    out = []
    for x, y in b.holes:
        z0 = L.floor_z(y) - 0.5           # sink into the floor, fuse cleanly
        out.append(cyl_z(x, y, z0, L.z_board_bottom, p.boss_d))
    return out


def _board_insert_holes(p, b, L):
    return [cyl_z(x, y, L.z_board_bottom - p.insert_depth,
                  L.z_board_bottom + 0.1, p.insert_d) for x, y in b.holes]


def _walls(p, b, L):
    x0o, x1o, y0o, y1o = L.outer_box()
    # front tier shell, up to z_frame; rear tier shell up to z_deck
    front = prism(x0o, x1o, y0o, L.y_step, Z_LOW, L.z_frame)
    rear = prism(x0o, x1o, L.y_step, y1o, Z_LOW, L.z_deck)
    shell = fuse_all([front, rear])
    # the front rim rises to z_rim
    rim = prism(x0o, x1o, y0o, L.y_front_i, Z_LOW, L.z_rim)
    shell = fuse_all([shell, rim])
    # hollow: inner cavity from the floor top upward, rear open
    cavity = prism(L.x0i, L.x1i, L.y_front_i, y1o + 1.0, Z_LOW + 1.0, 400.0)
    shell = cut_all(shell, [cavity])
    # ledge rebate inside the rim
    rebate = prism(L.x0i, L.x1i, L.y_ledge, L.y_front_i + 0.01, L.z_frame, 400.0)
    shell = cut_all(shell, [rebate])
    return shell


def _hood_bosses(p, b, L):
    out = []
    for i, (x, y) in enumerate(L.hood_bosses):
        if i < 2:                          # front pair: round, hung on the wall
            out.append(cyl_z(x, y, Z_BOSS_FOOT, L.z_deck, p.boss_d))
        else:                              # rear pair: blocks, also hold the rear plate
            on_left = x < L.x_j6
            bx0 = L.x0i - 0.5 if on_left else L.x1i - 6.0
            bx1 = L.x0i + 6.0 if on_left else L.x1i + 0.5
            out.append(prism(bx0, bx1, L.y_rear_i - 7.0, L.y_rear_i, Z_BOSS_FOOT, L.z_deck))
    return out


def _hood_insert_holes(p, b, L):
    return [cyl_z(x, y, L.z_deck - p.insert_depth, L.z_deck + 0.1, p.insert_d)
            for x, y in L.hood_bosses]


def _rear_plate_insert_holes(p, b, L):
    return [cyl_y(x, z, L.y_rear_i - p.insert_depth, L.y_rear_i + 0.1, p.insert_d)
            for x, z in L.rear_plate_screws]


def _frame_insert_holes(p, b, L):
    return [cyl_z(x, y, L.z_frame - p.insert_depth, L.z_frame + 0.1, p.insert_d)
            for x, y in L.frame_screws]


def _pad_recesses(p, b, L):
    out = []
    for x in (L.x0o + 12.0, L.x1o - 12.0):
        for y in (L.y_front_o + 12.0, L.y_rear_o - 12.0):
            z = L.under_z(y)
            out.append(cyl_z(x, y, z - 5.0, z + 1.0, p.pad_d))
    return out


def bay_opening_box(p, b, L):
    if p.bay_side == "none":
        return None
    y_mid = (L.y_step + L.y_rear_i) / 2.0
    y0, y1 = y_mid - p.bay_w / 2.0, y_mid + p.bay_w / 2.0
    if p.bay_side == "left":
        x0, x1 = L.x0o - 1.0, L.x0i + 1.0
    else:
        x0, x1 = L.x1i - 1.0, L.x1o + 1.0
    return prism(x0, x1, y0, y1, p.bay_z, p.bay_z + p.bay_h)


def tray(p, b, L):
    shell = _walls(p, b, L)
    floor = geom.between_planes(L, p.wall)
    body = fuse_all([shell, floor] + board_bosses(p, b, L) + _hood_bosses(p, b, L))
    body = cut_all(body, _board_insert_holes(p, b, L) + _hood_insert_holes(p, b, L)
                   + _rear_plate_insert_holes(p, b, L) + _frame_insert_holes(p, b, L)
                   + _pad_recesses(p, b, L) + [bay_opening_box(p, b, L)])
    body = cut_all(body, [geom.below_plane(L)])
    solids = body.Solids
    if len(solids) != 1:
        raise ValueError("tray is %d solids, expected 1" % len(solids))
    return solids[0]
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `$FC tools/test_case.py test_tray 2>&1 | grep -v 3Dconnexion`
Expected: `Ran 9 tests` … `OK`. Typical failures and their fixes: `tray is 2 solids` means a boss does not reach the floor at the rear (increase the `-0.5` sink or check `floor_z`); `test_board_volume_is_empty` failing at Z 5 means the cavity did not cut through the rim: check the cavity starts at `y_front_i`.

- [ ] **Step 5: Commit**

```bash
git add tools/case/tray.py tools/case/tests/test_tray.py
git commit -m "Case: the tray -- floor on the wedge plane, two-tier walls, bosses, bay opening"
```

---

### Task 5: Keyboard frame

**Files:**
- Create: `tools/case/keyboard_frame.py`
- Create: `tools/case/tests/test_keyboard_frame.py`

**Interfaces:**
- Produces: `tools.case.keyboard_frame.frame(p, b, L) -> Part.Solid`; `keyboard_frame.opening_face(p, b, L) -> Part.Face` (the 2D opening at Z 0, used by the gate's envelope check).
- Consumes: `model/placements.json` via `tools.build_caps`-style reading (open the JSON directly; do not import `build_caps`, which triggers the gate's import guard).

- [ ] **Step 1: Write the failing test**

```python
import json
import os
import unittest

from tools.case import board, geom, keyboard_frame, layout, params

REPO = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))))


class FrameTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.p = params.load()
        cls.b = board.load()
        cls.L = layout.Layout(cls.p, cls.b)
        cls.f = keyboard_frame.frame(cls.p, cls.b, cls.L)
        with open(os.path.join(REPO, "model", "placements.json")) as h:
            cls.keys = json.load(h)

    def test_valid_plate_between_frame_z_and_top(self):
        f, L, bb = self.f, self.L, geom.obox(self.f)
        self.assertTrue(f.isValid())
        self.assertEqual(len(f.Solids), 1)
        self.assertAlmostEqual(bb.ZMin, L.z_frame, 3)
        self.assertAlmostEqual(bb.ZMax, L.z_frame_top, 3)
        self.assertAlmostEqual(bb.YMin, L.y_ledge, 2)
        self.assertAlmostEqual(bb.YMax, L.y_step_back, 2)

    def test_every_key_centre_is_open(self):
        f, L = self.f, self.L
        for ref, e in self.keys.items():
            self.assertFalse(f.isInside(geom.V(e["x"], e["y"], L.z_frame + 1), 1e-6, True), ref)

    def test_material_just_outside_the_field(self):
        f, L, k = self.f, self.L, self.b.key
        self.assertTrue(f.isInside(geom.V(140.0, k.ymin - self.p.key_offset - 1.0, L.z_frame + 1), 1e-6, True))

    def test_led_holes(self):
        f, L = self.f, self.L
        for ref in board.LED_REFS:
            bb = geom.obox(self.b.component(ref))
            cx, cy = (bb.XMin + bb.XMax) / 2.0, (bb.YMin + bb.YMax) / 2.0
            self.assertFalse(f.isInside(geom.V(cx, cy, L.z_frame + 1), 1e-6, True), ref)
            self.assertTrue(f.isInside(geom.V(cx, cy - 4.0, L.z_frame + 1), 1e-6, True), ref)

    def test_hull_mode_is_one_rectangle(self):
        p = params.load()
        p.raw["opening_mode"] = "hull"
        face = keyboard_frame.opening_face(p, self.b, self.L)
        self.assertEqual(len(face.OuterWire.Edges), 4)
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `$FC tools/test_case.py test_keyboard_frame 2>&1 | grep -v 3Dconnexion`
Expected: ImportError, exit 1.

- [ ] **Step 3: Write `tools/case/keyboard_frame.py`**

```python
"""The plate around the keys. Swapped when the cap profile changes."""
import json
import os

import Part

from tools.case import geom
from tools.case.geom import V, prism, cyl_z, cut_all
from tools.case import board as board_mod

REPO = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
PLACEMENTS = os.path.join(REPO, "model", "placements.json")
CAP_GAP_MM = 0.65        # matches verify.CAP_GAP_MM; the envelope prisms use it
PITCH = 19.05


def key_footprints(p):
    with open(PLACEMENTS) as handle:
        placed = json.load(handle)
    faces = []
    for entry in placed.values():
        w = entry["units"] * PITCH - CAP_GAP_MM + 2 * p.key_offset
        d = PITCH - CAP_GAP_MM + 2 * p.key_offset
        faces.append(Part.makePlane(w, d, V(entry["x"] - w / 2.0,
                                             entry["y"] - d / 2.0, 0)))
    return faces


def opening_face(p, b, L):
    faces = key_footprints(p)
    if p.opening_mode == "hull":
        k = b.key
        return Part.makePlane(k.xmax - k.xmin + 2 * p.key_offset,
                              k.ymax - k.ymin + 2 * p.key_offset,
                              V(k.xmin - p.key_offset, k.ymin - p.key_offset, 0))
    fused = faces[0].fuse(faces[1:]).removeSplitter()
    if len(fused.Faces) != 1:
        raise ValueError("key field fused into %d faces, expected 1"
                         % len(fused.Faces))
    return Part.Face(fused.Faces[0].OuterWire)


def _led_cutters(p, b, L):
    out = []
    for ref in board_mod.LED_REFS:
        bb = geom.obox(b.component(ref))
        cx, cy = (bb.XMin + bb.XMax) / 2.0, (bb.YMin + bb.YMax) / 2.0
        if p.led_mode == "light_pipe":
            out.append(cyl_z(cx, cy, L.z_frame - 1, L.z_frame_top + 1, 4.0))
        else:
            out.append(cyl_z(cx, cy, L.z_frame - 1, L.z_frame_top + 1, p.led_hole_d))
    return out


def frame(p, b, L):
    # Front part spans wall outer to outer (it sits on the wall tops);
    # behind y_step only the inner width, because the rear-tier walls rise.
    front = prism(L.x0o, L.x1o, L.y_ledge, L.y_step, L.z_frame, L.z_frame_top)
    back = prism(L.x0i, L.x1i, L.y_step - 0.01, L.y_step_back, L.z_frame, L.z_frame_top)
    plate = geom.fuse_all([front, back])
    opening = opening_face(p, b, L).extrude(V(0, 0, 100))
    opening.translate(V(0, 0, -50))
    screws = [cyl_z(x, y, L.z_frame - 1, L.z_frame_top + 1, p.screw_clear_d)
              for x, y in L.frame_screws]
    plate = cut_all(plate, [opening] + screws + _led_cutters(p, b, L))
    solids = plate.Solids
    if len(solids) != 1:
        raise ValueError("frame is %d solids, expected 1" % len(solids))
    return solids[0]
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `$FC tools/test_case.py test_keyboard_frame 2>&1 | grep -v 3Dconnexion`
Expected: `Ran 5 tests` … `OK`. If `test_led_holes` fails on the material assertion, an LED sits in the opening: check `cy - 4.0` is still behind the F‑row keys (the LEDs are at Y −104.775, the F‑row footprints start at Y −114.3 + offset); adjust the test probe to `cy + 4.0` only if the geometry shows the LEDs are inside the notch on the other side.

- [ ] **Step 5: Commit**

```bash
git add tools/case/keyboard_frame.py tools/case/tests/test_keyboard_frame.py
git commit -m "Case: keyboard frame from the key envelope, outline and hull modes, LED holes"
```

---

### Task 6: Hood (rear-tier deck with the step face)

**Files:**
- Create: `tools/case/hood.py`
- Create: `tools/case/tests/test_hood.py`

**Interfaces:**
- Produces: `tools.case.hood.hood(p, b, L) -> Part.Solid`; `hood.vent_slots(p, b, L) -> list[Part.Solid]`; `hood.lid_notch_box(p, b, L) -> Part.Solid` (the notch in the deck plate where the lid's top face sits; also used by the lid).

Geometry: top plate `x0o..x1o × y_step..y_rear_o × z_deck..z_deck_top`; step face `x0i..x1i × y_step..y_step_back × z_frame_top..z_deck_top` (vertical in this task; `step_angle` applied in Task 13). Notch for the lid's top face: `x_win0..x_win1 × (y_rear_o - lid_depth)..y_rear_o` through the plate. A lip under the notch's front edge: `x_win0..x_win1 × (y_rear_o - lid_depth - 4)..(y_rear_o - lid_depth) × (z_deck - plate)..z_deck`. Vent slots in the regions over U25/U26 (left: X from `x0i + 8` to 60) and over SP1 (right: X from 245 to `x1i - 8`), Y from `y_step_back + 8` to `y_rear_i - 8`, slot length `vent_l` clipped to that span. Screw clearance holes at `hood_bosses`. Optional EPROM hatches over U10/U11 when `eprom_hatches` is 1: `obox` of each ref plus 2 mm, cut through the plate.

- [ ] **Step 1: Write the failing test**

```python
import unittest

from tools.case import board, geom, hood, layout, params


class HoodTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.p = params.load()
        cls.b = board.load()
        cls.L = layout.Layout(cls.p, cls.b)
        cls.h = hood.hood(cls.p, cls.b, cls.L)

    def test_valid_and_bounded(self):
        h, L, bb = self.h, self.L, geom.obox(self.h)
        self.assertTrue(h.isValid())
        self.assertEqual(len(h.Solids), 1)
        self.assertAlmostEqual(bb.ZMax, L.z_deck_top, 3)
        self.assertAlmostEqual(bb.ZMin, L.z_frame_top, 3)
        self.assertAlmostEqual(bb.YMin, L.y_step, 3)
        self.assertAlmostEqual(bb.YMax, L.y_rear_o, 3)

    def test_step_face_reaches_the_frame(self):
        h, L = self.h, self.L
        y = (L.y_step + L.y_step_back) / 2.0
        self.assertTrue(h.isInside(geom.V(140, y, L.z_frame_top + 1), 1e-6, True))
        self.assertTrue(h.isInside(geom.V(140, y, L.z_deck - 1), 1e-6, True))

    def test_lid_notch_is_open_and_has_a_lip(self):
        h, L, p = self.h, self.L, self.p
        y_in_notch = L.y_rear_o - p.lid_depth / 2.0
        self.assertFalse(h.isInside(geom.V(L.x_j6, y_in_notch, L.z_deck + 1), 1e-6, True))
        y_lip = L.y_rear_o - p.lid_depth - 2.0
        self.assertTrue(h.isInside(geom.V(L.x_j6, y_lip, L.z_deck - 1), 1e-6, True))

    def test_vents_exist_left_and_right_only(self):
        h, L, p = self.h, self.L, self.p
        y = (L.y_step_back + L.y_rear_i) / 2.0
        def open_at(x):
            return not h.isInside(geom.V(x, y, L.z_deck + 1), 1e-6, True)
        self.assertTrue(any(open_at(x) for x in range(15, 60)))
        self.assertTrue(any(open_at(x) for x in range(245, 265)))
        self.assertFalse(any(open_at(x) for x in range(70, 110)))

    def test_screw_holes_over_hood_bosses(self):
        h, L = self.h, self.L
        for x, y in L.hood_bosses:
            self.assertFalse(h.isInside(geom.V(x, y, L.z_deck + 1), 1e-6, True), (x, y))

    def test_eprom_hatches_off_by_default_on_when_asked(self):
        L = self.L
        u10 = geom.obox(self.b.component("U10"))
        cx, cy = (u10.XMin + u10.XMax) / 2.0, (u10.YMin + u10.YMax) / 2.0
        self.assertTrue(self.h.isInside(geom.V(cx, cy, L.z_deck + 1), 1e-6, True))
        p = params.load()
        p.raw["eprom_hatches"] = "1"
        h2 = hood.hood(p, self.b, L)
        self.assertFalse(h2.isInside(geom.V(cx, cy, L.z_deck + 1), 1e-6, True))
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `$FC tools/test_case.py test_hood 2>&1 | grep -v 3Dconnexion`
Expected: ImportError, exit 1.

- [ ] **Step 3: Write `tools/case/hood.py`**

```python
"""The rear-tier deck: top plate plus the step face, one part."""
from tools.case import geom
from tools.case import board as board_mod
from tools.case.geom import V, prism, cyl_z, fuse_all, cut_all

VENT_MARGIN = 8.0
LID_LIP = 4.0
HATCH_MARGIN = 2.0


def lid_notch_box(p, b, L):
    return prism(L.x_win0, L.x_win1, L.y_rear_o - p.lid_depth, L.y_rear_o + 1.0,
                 L.z_deck - 1.0, L.z_deck_top + 1.0)


def _lip(p, b, L):
    return prism(L.x_win0, L.x_win1, L.y_rear_o - p.lid_depth - LID_LIP,
                 L.y_rear_o - p.lid_depth + 0.01, L.z_deck - p.plate, L.z_deck)


def vent_slots(p, b, L):
    regions = p.list("vent_regions")
    y0 = L.y_step_back + VENT_MARGIN
    y1 = L.y_rear_i - VENT_MARGIN
    length = min(p.vent_l, y1 - y0)
    yc = (y0 + y1) / 2.0
    spans = []
    if "left" in regions:
        spans.append((L.x0i + VENT_MARGIN, 60.0))
    if "right" in regions:
        spans.append((245.0, L.x1i - VENT_MARGIN))
    slots = []
    for x0, x1 in spans:
        x = x0
        while x + p.vent_w <= x1:
            slots.append(prism(x, x + p.vent_w, yc - length / 2.0, yc + length / 2.0,
                               L.z_deck - 1.0, L.z_deck_top + 1.0))
            x += p.vent_pitch
    return slots


def _hatches(p, b, L):
    if int(p.eprom_hatches) != 1:
        return []
    out = []
    for ref in board_mod.HATCH_REFS:
        bb = geom.obox(b.component(ref))
        out.append(prism(bb.XMin - HATCH_MARGIN, bb.XMax + HATCH_MARGIN,
                         bb.YMin - HATCH_MARGIN, bb.YMax + HATCH_MARGIN,
                         L.z_deck - 1.0, L.z_deck_top + 1.0))
    return out


def hood(p, b, L):
    top = prism(L.x0o, L.x1o, L.y_step, L.y_rear_o, L.z_deck, L.z_deck_top)
    step = prism(L.x0i, L.x1i, L.y_step, L.y_step_back, L.z_frame_top, L.z_deck + 0.01)
    body = fuse_all([top, step, _lip(p, b, L)])
    screws = [cyl_z(x, y, L.z_deck - 1.0, L.z_deck_top + 1.0, p.screw_clear_d)
              for x, y in L.hood_bosses]
    body = cut_all(body, [lid_notch_box(p, b, L)] + vent_slots(p, b, L)
                   + screws + _hatches(p, b, L))
    solids = body.Solids
    if len(solids) != 1:
        raise ValueError("hood is %d solids, expected 1" % len(solids))
    return solids[0]
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `$FC tools/test_case.py test_hood 2>&1 | grep -v 3Dconnexion`
Expected: `Ran 6 tests` … `OK`.

- [ ] **Step 5: Commit**

```bash
git add tools/case/hood.py tools/case/tests/test_hood.py
git commit -m "Case: the hood -- rear deck with step face, lid notch, vents, optional EPROM hatches"
```

---

### Task 7: Rear plate

**Files:**
- Create: `tools/case/rear_plate.py`
- Create: `tools/case/tests/test_rear_plate.py`

**Interfaces:**
- Produces: `tools.case.rear_plate.rear_plate(p, b, L) -> Part.Solid`; `rear_plate.port_cutters(p, b, L) -> dict[ref, Part.Solid]` (each connector's through-cutter, used by the gate's port check); `rear_plate.socket_centres(p, b, L) -> [(x, y, z), (x, y, z)]`.

Geometry: plate `x0o..x1o × y_rear_i..y_rear_o × Z_LOW..z_deck`, cut by `below_plane`.

*Port cutouts.* For each ref in `EXTERNAL_REFS`, slice the component with the plane Y = `y_rear_i - 0.01` (the plate's inner face). If that slice has no closed wire (the component stops short of the plate: J2 and J4 do), slice at the component's own `YMax - 0.3` instead and add `plug_margin` to the margin. One slice → closed wires → faces → fused into one face (inner wires are filled, so pin holes do not become islands) → `makeOffset2D(margin)`; if the offset fails or does not grow the area, fall back to the slice's bounding rectangle plus margin, built explicitly in the XZ plane. Translate the face to Y = `y_rear_i - 1` and extrude `plate + 2` along +Y. SW68 uses `reset_margin`.

*Hinge seat.* The hinge axis A is at `(y_a = y_rear_i - 3, z_hinge)`, along X. A flap whose rear face sits in the plate and rotates about an axis 3–6 mm in front of it would sweep its bottom edge into the plate below the window, so the plate gets a **cylindrical seat**: a cylinder of radius `R + tile_gap`, `R = y_rear_o - y_a = 6`, about A, spanning the window in X, is cut from the plate. The lid's rear face (Task 8) ends in the matching convex arc of radius `R`, so the closed seam on the outside is a straight line at `z_hinge` and the lid can swing back without touching the plate.

*Window.* `x_win0..x_win1 × z_hinge..z_deck+1` through the plate, plus the seat.

*Socket blocks.* On the plate's inner face beside the window: `socket_block` wide (X) × 6 deep (Y `y_rear_i - 6 .. y_rear_i`) × Z `(z_hinge - 3.5) .. z_deck`. Spherical socket of diameter `socket_d = stud_d - stud_interference` centred at `(x_win0, y_a, z_hinge)` and `(x_win1, y_a, z_hinge)`; each opened upward by a keyhole throat `socket_d - throat_undersize` wide (in Y), reaching `socket_d / 2 - 0.5` into the block in X, from the socket centre to the block top. Rear-plate screw clearance holes at `rear_plate_screws`.

- [ ] **Step 1: Write the failing test**

```python
import unittest

from tools.case import board, geom, layout, params, rear_plate


class RearPlateTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.p = params.load()
        cls.b = board.load()
        cls.L = layout.Layout(cls.p, cls.b)
        cls.r = rear_plate.rear_plate(cls.p, cls.b, cls.L)

    def test_valid_flat_plate(self):
        r, L, bb = self.r, self.L, geom.obox(self.r)
        self.assertTrue(r.isValid())
        self.assertEqual(len(r.Solids), 1)
        self.assertAlmostEqual(bb.YMax, L.y_rear_o, 3)
        self.assertAlmostEqual(bb.ZMax, L.z_deck, 3)
        self.assertAlmostEqual(bb.ZMin, L.under_z(L.y_rear_o), 1)

    def test_every_external_connector_passes_through(self):
        r, L = self.r, self.L
        y = (L.y_rear_i + L.y_rear_o) / 2.0
        for ref in board.EXTERNAL_REFS:
            bb = geom.obox(self.b.component(ref))
            cx, cz = (bb.XMin + bb.XMax) / 2.0, (bb.ZMin + bb.ZMax) / 2.0
            if ref == "SW68":
                cz = 4.2                      # the button, not the body
            self.assertFalse(r.isInside(geom.V(cx, y, cz), 1e-6, True), ref)

    def test_plate_is_solid_between_connectors(self):
        r, L = self.r, self.L
        y = (L.y_rear_i + L.y_rear_o) / 2.0
        self.assertTrue(r.isInside(geom.V(60.0, y, 2.0), 1e-6, True))   # between J2 and J4
        self.assertTrue(r.isInside(geom.V(220.0, y, 2.0), 1e-6, True))  # between J5 and J1

    def test_window_open_above_hinge_and_solid_below(self):
        r, L = self.r, self.L
        y = (L.y_rear_i + L.y_rear_o) / 2.0
        self.assertFalse(r.isInside(geom.V(L.x_j6, y, L.z_hinge + 5), 1e-6, True))
        self.assertTrue(r.isInside(geom.V(L.x_j6, y, L.z_hinge - 8), 1e-6, True))

    def test_hinge_seat_is_cut_inside_the_window_only(self):
        r, L = self.r, self.L
        y_a, z = L.y_rear_i - 3.0, L.z_hinge
        # inside the window span the plate's inner face dips below the axis
        self.assertFalse(r.isInside(geom.V(L.x_j6, L.y_rear_i + 0.5, z - 4.0), 1e-6, True))
        # outside the window span it does not
        self.assertTrue(r.isInside(geom.V(L.x_win0 - 10.0, L.y_rear_i + 0.5, z - 4.0), 1e-6, True))
        # the outer skin at the seam line is intact
        self.assertTrue(r.isInside(geom.V(L.x_j6, L.y_rear_o - 0.3, z - 2.0), 1e-6, True))

    def test_socket_blocks_have_spherical_sockets(self):
        r, L, p = self.r, self.L, self.p
        for x, y, z in rear_plate.socket_centres(p, self.b, L):
            self.assertFalse(r.isInside(geom.V(x, y, z), 1e-6, True))           # socket cavity
            self.assertTrue(r.isInside(geom.V(x, y, z - p.stud_d / 2.0 - 0.8), 1e-6, True))  # block below
            # the throat opens upward from the socket
            self.assertFalse(r.isInside(geom.V(x + (0.4 if x > L.x_j6 else -0.4), y, z + 3.0), 1e-6, True))

    def test_port_cutters_are_named(self):
        cutters = rear_plate.port_cutters(self.p, self.b, self.L)
        self.assertEqual(sorted(cutters), sorted(board.EXTERNAL_REFS))
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `$FC tools/test_case.py test_rear_plate 2>&1 | grep -v 3Dconnexion`
Expected: ImportError, exit 1.

- [ ] **Step 3: Write `tools/case/rear_plate.py`**

```python
"""The rear plate: every port cutout, the J6 window, the lid sockets."""
import Part

from tools.case import geom
from tools.case import board as board_mod
from tools.case.geom import V, prism, cyl_y, fuse_all, cut_all

Z_LOW = -80.0
SOCKET_DEPTH = 6.0       # socket block depth into the case (−Y)


def _section_face(shape, y):
    """Closed section of `shape` by the plane Y=y, as one face, holes filled.
    Returns None when no closed wire lies in that plane."""
    wires = shape.slice(V(0, 1, 0), y)
    faces = []
    for w in wires:
        if not w.isClosed():
            continue
        try:
            faces.append(Part.Face(w))
        except Exception:                                    # noqa: BLE001
            continue
    if not faces:
        return None
    face = fuse_all(faces) if len(faces) > 1 else faces[0]
    if len(face.Faces) != 1:
        # disjoint pieces (e.g. a shell and a separate pin): take the largest
        face = max(face.Faces, key=lambda f: f.Area)
    return Part.Face(face.OuterWire)


def _xz_rect(x0, x1, z0, z1, y):
    pts = [V(x0, y, z0), V(x1, y, z0), V(x1, y, z1), V(x0, y, z1), V(x0, y, z0)]
    return Part.Face(Part.makePolygon(pts))


def _offset_or_box(face, margin, y):
    """Grow a planar face by `margin`; fall back to its rectangle plus margin."""
    try:
        off = face.makeOffset2D(margin)
        if off.isValid() and off.Area > face.Area * 1.01:
            return off
    except Exception:                                        # noqa: BLE001
        pass
    bb = geom.obox(face)
    return _xz_rect(bb.XMin - margin, bb.XMax + margin, bb.ZMin - margin, bb.ZMax + margin, y)


def port_cutters(p, b, L):
    """{ref: through-cutter} for every external connector."""
    out = {}
    y_cut = L.y_rear_i - 1.0
    for ref in board_mod.EXTERNAL_REFS:
        comp = b.component(ref)
        margin = p.reset_margin if ref == "SW68" else p.port_margin
        face = _section_face(comp, L.y_rear_i - 0.01)
        if face is None:
            # stops short of the plate: its own front face, and a plug margin
            y_front = geom.obox(comp).YMax - 0.3
            face = _section_face(comp, y_front)
            if face is None:
                raise ValueError("%s: no closed section near Y %.2f" % (ref, y_front))
            margin += p.plug_margin
        bb = geom.obox(face)
        face.translate(V(0, y_cut - bb.YMin, 0))
        cutter_face = _offset_or_box(face, margin, y_cut)
        out[ref] = cutter_face.extrude(V(0, p.plate + 2.0, 0))
    return out


def hinge_axis(p, b, L):
    """(y, z) of the hinge axis, which runs along X."""
    return (L.y_rear_i - SOCKET_DEPTH / 2.0, L.z_hinge)


def seat_radius(p, b, L):
    y_a, _z = hinge_axis(p, b, L)
    return L.y_rear_o - y_a               # 6.0 with the defaults


def socket_centres(p, b, L):
    y, z = hinge_axis(p, b, L)
    return [(L.x_win0, y, z), (L.x_win1, y, z)]


def _seat_cutter(p, b, L):
    y_a, z_a = hinge_axis(p, b, L)
    r = seat_radius(p, b, L) + p.tile_gap
    return Part.makeCylinder(r, L.x_win1 - L.x_win0, V(L.x_win0, y_a, z_a), V(1, 0, 0))


def _socket_blocks(p, b, L):
    z0 = L.z_hinge - 3.5
    left = prism(L.x_win0 - p.socket_block, L.x_win0 + 0.01, L.y_rear_i - SOCKET_DEPTH,
                 L.y_rear_i + 0.01, z0, L.z_deck)
    right = prism(L.x_win1 - 0.01, L.x_win1 + p.socket_block, L.y_rear_i - SOCKET_DEPTH,
                  L.y_rear_i + 0.01, z0, L.z_deck)
    return [left, right]


def _socket_cutters(p, b, L):
    socket_d = p.stud_d - p.stud_interference
    throat = socket_d - p.throat_undersize
    reach = socket_d / 2.0 - 0.5
    out = []
    for x, y, z in socket_centres(p, b, L):
        out.append(Part.makeSphere(socket_d / 2.0, V(x, y, z)))
        # keyhole throat: from the socket centre up to the block top, `throat`
        # wide in Y, reaching `reach` into the block in X
        x0 = x - reach if x < L.x_j6 else x - 0.01
        x1 = x + 0.01 if x < L.x_j6 else x + reach
        out.append(prism(x0, x1, y - throat / 2.0, y + throat / 2.0, z, L.z_deck + 1.0))
    return out


def rear_plate(p, b, L):
    plate = prism(L.x0o, L.x1o, L.y_rear_i, L.y_rear_o, Z_LOW, L.z_deck)
    body = fuse_all([plate] + _socket_blocks(p, b, L))
    window = prism(L.x_win0, L.x_win1, L.y_rear_i - 1.0, L.y_rear_o + 1.0,
                   L.z_hinge, L.z_deck + 1.0)
    screws = [cyl_y(x, z, L.y_rear_i - 1.0, L.y_rear_o + 1.0, p.screw_clear_d)
              for x, z in L.rear_plate_screws]
    cutters = list(port_cutters(p, b, L).values())
    body = cut_all(body, [window, _seat_cutter(p, b, L)] + cutters + screws
                   + _socket_cutters(p, b, L))
    body = cut_all(body, [geom.below_plane(L)])
    solids = body.Solids
    if len(solids) != 1:
        raise ValueError("rear plate is %d solids, expected 1" % len(solids))
    return solids[0]
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `$FC tools/test_case.py test_rear_plate 2>&1 | grep -v 3Dconnexion`
Expected: `Ran 7 tests` … `OK`. If `makeOffset2D` shrinks instead of growing (wire orientation), the code already falls back to the rectangle; that is acceptable for the skeleton and a polish item later. If the plate is 2 solids, a socket cutter split a block: reduce `reach` in `_socket_cutters`.

- [ ] **Step 5: Commit**

```bash
git add tools/case/rear_plate.py tools/case/tests/test_rear_plate.py
git commit -m "Case: rear plate with port cutouts from connector sections, J6 window, ball sockets"
```

---

### Task 8: Lid, feet, bay cover

**Files:**
- Create: `tools/case/lid.py`
- Create: `tools/case/feet.py`
- Create: `tools/case/bay.py`
- Create: `tools/case/tests/test_small_parts.py`

**Interfaces:**
- Produces: `tools.case.lid.lid(p, b, L) -> Part.Solid` (closed position); `lid.lid_open(p, b, L, angle=170.0) -> Part.Solid` (rotated about the hinge axis, for renders); `tools.case.feet.feet(p, b, L) -> list[(name, Part.Solid)]` (one per height, names `foot_10`, `foot_20`); `tools.case.bay.bay_cover(p, b, L) -> Part.Solid or None`.
- Consumes: `hood.lid_notch_box`, `tray.bay_opening_box`, `rear_plate.socket_centres`.

Geometry:
- Lid rear face: `x_win0+tile_gap .. x_win1-tile_gap × y_rear_i..y_rear_o`, from `z_hinge - 7` up to `z_deck_top`, then trimmed so that below `z_hinge` only the material inside the cylinder of radius `R = seat_radius` about the hinge axis A `(y_a, z_hinge)` remains. That gives the rear face a convex arc bottom that mates with the plate's seat: on the outside the seam is at `z_hinge`, on the inside the face reaches down to about `z_hinge - 5`. Lid top face: same X × `(y_rear_o - lid_depth + tile_gap)..y_rear_o × z_deck..z_deck_top`.
- Arms: two blocks, one per side, `4` wide (X, inward from each side face) × from `y_a - 2` to `y_rear_i + 0.01` (Y) × `z_hinge ± 2` (Z), joining the rear face to the studs.
- Studs: spheres Ø `stud_d` centred exactly at `rear_plate.socket_centres` (x on the window edge, y = `y_a`, z = `z_hinge`). Because the lid's side face is only `tile_gap` inside the window edge, each sphere overlaps its arm and needs no neck.
- Notch: if `lid_notch`, a `34 × 3` cut in the rear face at `z_hinge..z_hinge+3`, centred on `x_j6` (away from the arms).
- No separate bearings: the cylindrical seat carries the load, the studs only retain.
- Feet: for each height h in `foot_heights`: a block 40 × 20 × h with a 20 × 6 dovetail tongue 4 tall on top (simple rectangular tongue in this task). Positioned at origin; they are loose parts.
- Bay cover: the `bay_opening_box` grown by 6 mm in Y and Z, 3 thick, placed on the inner side of the wall (X from `x0i` to `x0i + plate` for left), with four Ø3.4 holes at its corners.

- [ ] **Step 1: Write the failing test**

```python
import unittest

from tools.case import bay, board, feet, geom, layout, lid, params, rear_plate


class SmallPartsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.p = params.load()
        cls.b = board.load()
        cls.L = layout.Layout(cls.p, cls.b)

    def test_lid_is_an_L_with_studs_at_the_socket_centres(self):
        p, L = self.p, self.L
        s = lid.lid(p, self.b, L)
        self.assertTrue(s.isValid())
        self.assertEqual(len(s.Solids), 1)
        y_rear = (L.y_rear_i + L.y_rear_o) / 2.0
        self.assertTrue(s.isInside(geom.V(L.x_j6, y_rear, L.z_hinge + 8), 1e-6, True))
        self.assertTrue(s.isInside(geom.V(L.x_j6, L.y_rear_o - p.lid_depth / 2.0, L.z_deck + 1), 1e-6, True))
        for x, y, z in rear_plate.socket_centres(p, self.b, L):
            self.assertTrue(s.isInside(geom.V(x, y, z), 1e-6, True), (x, y, z))
        if int(p.lid_notch):
            self.assertFalse(s.isInside(geom.V(L.x_j6, y_rear, L.z_hinge + 1), 1e-6, True))

    def test_lid_open_hangs_behind_the_plate(self):
        p, L = self.p, self.L
        s = lid.lid_open(p, self.b, L)
        bb = geom.obox(s)
        self.assertGreater(bb.YMax, L.y_rear_o + 10)     # it is behind the machine
        self.assertLess(bb.ZMin, L.z_hinge - 10)         # and it hangs down

    def test_two_feet(self):
        parts = feet.feet(self.p, self.b, self.L)
        self.assertEqual([n for n, _ in parts], ["foot_10", "foot_20"])
        for name, s in parts:
            self.assertTrue(s.isValid())
        self.assertAlmostEqual(geom.obox(parts[1][1]).ZLength, 24.0, 3)

    def test_bay_cover_matches_the_opening(self):
        p, L = self.p, self.L
        cover = bay.bay_cover(p, self.b, L)
        bb = geom.obox(cover)
        self.assertAlmostEqual(bb.ZLength, p.bay_h + 12.0, 3)
        self.assertAlmostEqual(bb.XMin, L.x0i, 3)
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `$FC tools/test_case.py test_small_parts 2>&1 | grep -v 3Dconnexion`
Expected: ImportError, exit 1.

- [ ] **Step 3: Write `tools/case/lid.py`**

```python
"""The J6 lid: L-shaped, ball studs, hangs open or unhooks.

Its rear face ends in a convex arc about the hinge axis that mates with the
cylindrical seat cut into the rear plate, so it swings back without the
bottom edge sweeping into the plate.
"""
import Part

from tools.case import geom, rear_plate
from tools.case.geom import V, prism, fuse_all, cut_all

ARM_W = 4.0
ARM_H = 4.0
NOTCH_W = 34.0
NOTCH_H = 3.0


def lid(p, b, L):
    g = p.tile_gap
    x0, x1 = L.x_win0 + g, L.x_win1 - g
    y_a, z_a = rear_plate.hinge_axis(p, b, L)
    r = rear_plate.seat_radius(p, b, L)
    # rear face: full above the axis, arc-bounded below it
    rear = prism(x0, x1, L.y_rear_i, L.y_rear_o, z_a - r - 1.0, L.z_deck_top)
    keep = fuse_all([
        prism(x0 - 1.0, x1 + 1.0, L.y_rear_i - 1.0, L.y_rear_o + 1.0, z_a, L.z_deck_top + 1.0),
        Part.makeCylinder(r, x1 - x0 + 2.0, V(x0 - 1.0, y_a, z_a), V(1, 0, 0)),
    ])
    rear = rear.common(keep)
    top = prism(x0, x1, L.y_rear_o - p.lid_depth + g, L.y_rear_o, L.z_deck, L.z_deck_top)
    arms = [
        prism(x0, x0 + ARM_W, y_a - 2.0, L.y_rear_i + 0.01, z_a - ARM_H / 2.0, z_a + ARM_H / 2.0),
        prism(x1 - ARM_W, x1, y_a - 2.0, L.y_rear_i + 0.01, z_a - ARM_H / 2.0, z_a + ARM_H / 2.0),
    ]
    studs = [Part.makeSphere(p.stud_d / 2.0, V(x, y, z))
             for x, y, z in rear_plate.socket_centres(p, b, L)]
    body = fuse_all([rear, top] + arms + studs)
    if int(p.lid_notch):
        notch = prism(L.x_j6 - NOTCH_W / 2.0, L.x_j6 + NOTCH_W / 2.0,
                      L.y_rear_i - 1.0, L.y_rear_o + 1.0, z_a - 1.0, z_a + NOTCH_H)
        body = cut_all(body, [notch])
    solids = body.Solids
    if len(solids) != 1:
        raise ValueError("lid is %d solids, expected 1" % len(solids))
    return solids[0]


def lid_open(p, b, L, angle=170.0):
    s = lid(p, b, L).copy()
    y_a, z_a = rear_plate.hinge_axis(p, b, L)
    # positive rotation about +X lifts +Y toward +Z, so swinging the rear
    # face back and down is the negative direction
    s.rotate(V(0, y_a, z_a), V(1, 0, 0), -angle)
    return s
```

- [ ] **Step 4: Write `tools/case/feet.py` and `tools/case/bay.py`**

```python
"""Rear tilt feet, loose parts. Rectangular tongue; dovetail is a polish item."""
from tools.case.geom import prism, fuse_all

FOOT_W, FOOT_D = 40.0, 20.0
TONGUE_W, TONGUE_D, TONGUE_H = 20.0, 6.0, 4.0


def feet(p, b, L):
    out = []
    for h in p.floats("foot_heights"):
        block = prism(0, FOOT_W, 0, FOOT_D, 0, h)
        tongue = prism((FOOT_W - TONGUE_W) / 2.0, (FOOT_W + TONGUE_W) / 2.0,
                       (FOOT_D - TONGUE_D) / 2.0, (FOOT_D + TONGUE_D) / 2.0, h - 0.01, h + TONGUE_H)
        out.append(("foot_%d" % int(h), fuse_all([block, tongue])))
    return out
```

```python
"""Blank cover for the side bay, screwed from inside the wall."""
from tools.case import geom, tray
from tools.case.geom import V, prism, cyl_z, cut_all
import Part

FLANGE = 6.0


def bay_cover(p, b, L):
    opening = tray.bay_opening_box(p, b, L)
    if opening is None:
        return None
    bb = geom.obox(opening)
    if p.bay_side == "left":
        x0, x1 = L.x0i, L.x0i + p.plate
    else:
        x0, x1 = L.x1i - p.plate, L.x1i
    cover = prism(x0, x1, bb.YMin - FLANGE, bb.YMax + FLANGE, bb.ZMin - FLANGE, bb.ZMax + FLANGE)
    holes = []
    for y in (bb.YMin - FLANGE / 2.0, bb.YMax + FLANGE / 2.0):
        for z in (bb.ZMin - FLANGE / 2.0, bb.ZMax + FLANGE / 2.0):
            holes.append(Part.makeCylinder(p.screw_clear_d / 2.0, p.plate + 2.0,
                                           V(x0 - 1.0, y, z), V(1, 0, 0)))
    return cut_all(cover, holes)
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `$FC tools/test_case.py test_small_parts 2>&1 | grep -v 3Dconnexion`
Expected: `Ran 4 tests` … `OK`. If the lid fuses into 2 solids, an arm does not overlap its stud: the stud centre is on the window edge, the arm starts `tile_gap` inside it, and the sphere radius is 2.5, so they must overlap; check `x0`/`x1` against `socket_centres`. Also add to the lid test: `self.assertFalse(s.isInside(geom.V(L.x_j6, L.y_rear_o - 0.3, L.z_hinge - 1.0), 1e-6, True))` (outside skin ends at the seam) and `self.assertTrue(s.isInside(geom.V(L.x_j6 + 5, L.y_rear_i + 0.3, L.z_hinge - 3.0), 1e-6, True))` (inside arc reaches below the axis) — the notch sits at `x_j6 ± 17`, so probe at `x_j6 + 20` for the second if the notch is on.

- [ ] **Step 6: Commit**

```bash
git add tools/case/lid.py tools/case/feet.py tools/case/bay.py tools/case/tests/test_small_parts.py
git commit -m "Case: J6 lid with ball studs, tilt feet, bay cover"
```

---

### Task 9: Export and the build entry point

**Files:**
- Create: `tools/case/export.py`
- Create: `tools/build_case.py`
- Create: `tools/case/tests/test_export.py`
- Modify: `.gitignore` (nothing needed: `.build/` is already ignored)

**Interfaces:**
- Produces: `tools.case.export.PARTS` = ordered list of `(name, builder)` where `builder(p, b, L)` returns a solid, names: `tray, keyboard_frame, hood, rear_plate, lid, bay_cover, foot_10, foot_20`; `export.build_all(p, b, L, only=None) -> dict[name, solid]`; `export.write_parts(solids, model_case_dir, build_dir) -> list[path]` (STEP into `model/case/`, STL into `.build/case/`); `export.write_manifest(solids, p, board_head, path)`; `export.write_case_document(solids, b, L, p, path)` (the case FCStd with `pcb`, `parts`, `caps`, every case part, and `lid_open`).
- Produces: `$FC tools/build_case.py [part ...]` → exit 0 built, 1 failed, 2 could not start. Prints one line per part and a `built:` summary.
- Consumes: everything above; `tools.board_index.BOARD` and `git rev-parse` for the board head.

- [ ] **Step 1: Write the failing test `tools/case/tests/test_export.py`**

```python
import os
import unittest

from tools.case import board, export, layout, params

REPO = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))))


class ExportTest(unittest.TestCase):
    def test_part_names_are_fixed(self):
        self.assertEqual([n for n, _ in export.PARTS],
                         ["tray", "keyboard_frame", "hood", "rear_plate", "lid",
                          "bay_cover", "foot_10", "foot_20"])

    def test_build_one_part_and_write_it(self):
        p = params.load()
        b = board.load()
        L = layout.Layout(p, b)
        solids = export.build_all(p, b, L, only=["foot_10"])
        self.assertEqual(list(solids), ["foot_10"])
        out = os.path.join(REPO, ".build", "test_export")
        paths = export.write_parts(solids, out, out)
        self.assertTrue(any(x.endswith("foot_10.step") for x in paths))
        self.assertTrue(any(x.endswith("foot_10.stl") for x in paths))
        for path in paths:
            self.assertGreater(os.path.getsize(path), 100)

    def test_manifest_has_hash_and_boxes(self):
        p = params.load()
        b = board.load()
        L = layout.Layout(p, b)
        solids = export.build_all(p, b, L, only=["foot_20"])
        path = os.path.join(REPO, ".build", "test_export", "manifest.tsv")
        export.write_manifest(solids, p, "deadbee", path)
        with open(path) as h:
            text = h.read()
        self.assertIn("case_hash\t" + p.hash(), text)
        self.assertIn("board_head\tdeadbee", text)
        self.assertIn("foot_20\t", text)
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `$FC tools/test_case.py test_export 2>&1 | grep -v 3Dconnexion`
Expected: ImportError, exit 1.

- [ ] **Step 3: Write `tools/case/export.py`**

```python
"""Write the parts: STEP (tracked) and STL (regenerable), a manifest, and the
case document that render_case.py opens."""
import os

import FreeCAD
import Part

from tools.case import bay, feet, hood, keyboard_frame, lid, rear_plate, tray
from tools.case import geom


def _foot(h):
    def build(p, b, L):
        for name, solid in feet.feet(p, b, L):
            if name == "foot_%d" % h:
                return solid
        raise ValueError("no foot_%d in foot_heights" % h)
    return build


PARTS = [
    ("tray", tray.tray),
    ("keyboard_frame", keyboard_frame.frame),
    ("hood", hood.hood),
    ("rear_plate", rear_plate.rear_plate),
    ("lid", lid.lid),
    ("bay_cover", bay.bay_cover),
    ("foot_10", _foot(10)),
    ("foot_20", _foot(20)),
]


def build_all(p, b, L, only=None):
    out = {}
    for name, builder in PARTS:
        if only and name not in only:
            continue
        solid = builder(p, b, L)
        if solid is None:
            continue
        out[name] = solid
    return out


def write_parts(solids, step_dir, stl_dir):
    os.makedirs(step_dir, exist_ok=True)
    os.makedirs(stl_dir, exist_ok=True)
    paths = []
    for name, solid in solids.items():
        step = os.path.join(step_dir, name + ".step")
        solid.exportStep(step)
        stl = os.path.join(stl_dir, name + ".stl")
        solid.exportStl(stl)
        paths += [step, stl]
    return paths


def write_manifest(solids, p, board_head, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as h:
        h.write("# Written by build_case.py. The gate refuses outputs whose\n"
                "# case_hash or board_head no longer match.\n")
        h.write("case_hash\t%s\n" % p.hash())
        h.write("board_head\t%s\n" % board_head)
        h.write("# part\txlen\tylen\tzlen\tvolume_mm3\n")
        for name, solid in solids.items():
            bb = geom.obox(solid)
            h.write("%s\t%.3f\t%.3f\t%.3f\t%.0f\n"
                    % (name, bb.XLength, bb.YLength, bb.ZLength, solid.Volume))


def write_case_document(solids, b, L, p, path):
    """Case parts plus a copy of the board's solids, one document.

    The board's shapes are copied, not linked: an App::Link into another
    file makes the render depend on both documents opening in the right
    order, and this file exists only to be looked at.
    """
    doc = FreeCAD.newDocument("radio86rk_case")
    try:
        pcb = [s for r, s in b.components if r == "caps"]
        for name, solid in solids.items():
            obj = doc.addObject("Part::Feature", name)
            obj.Shape = solid
        obj = doc.addObject("Part::Feature", "lid_open")
        obj.Shape = lid.lid_open(p, b, L)
        board_parts = [s for r, s in b.components if r != "caps"]
        obj = doc.addObject("Part::Feature", "parts")
        obj.Shape = Part.makeCompound(board_parts)
        if pcb:
            obj = doc.addObject("Part::Feature", "caps")
            obj.Shape = pcb[0]
        pcb_solid = Part.makeBox(b.xmax - b.xmin, b.ymax - b.ymin, b.thickness,
                                 geom.V(b.xmin, b.ymin, -b.thickness))
        obj = doc.addObject("Part::Feature", "pcb")
        obj.Shape = pcb_solid
        doc.recompute()
        doc.saveAs(path)
    finally:
        FreeCAD.closeDocument(doc.Name)
```

- [ ] **Step 4: Write `tools/build_case.py`**

```python
"""Build the case: every part from case.tsv + the board + the envelope.

    $FC tools/build_case.py                 # all parts
    $FC tools/build_case.py lid foot_10     # some parts (positional, no flags)

Writes model/case/<part>.step (tracked), .build/case/<part>.stl,
model/case/manifest.tsv and model/radio86rk-case.FCStd. Nothing is written
until every requested part has built, so a failure leaves the previous
outputs in place and exits 1 -- loudly, because freecadcmd exits 0 on an
unhandled exception.
"""
import os
import subprocess
import sys
import traceback

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO not in sys.path:
    sys.path.insert(0, REPO)

try:
    from tools.case import board, export, layout, params      # noqa: E402
    import board_index                                        # noqa: E402
except Exception as _exc:                                     # noqa: BLE001
    print("build failed before it began: %s: %s" % (type(_exc).__name__, _exc))
    traceback.print_exc()
    sys.stdout.flush()
    sys.exit(2)

MODEL = os.path.join(REPO, "model")
CASE_DIR = os.path.join(MODEL, "case")
BUILD_DIR = os.path.join(REPO, ".build", "case")
CASE_DOC = os.path.join(MODEL, "radio86rk-case.FCStd")


def board_head():
    try:
        return subprocess.check_output(
            ["git", "-C", board_index.BOARD, "rev-parse", "--short=7", "HEAD"],
            stderr=subprocess.STDOUT).decode().strip()
    except Exception as exc:                                  # noqa: BLE001
        raise RuntimeError("cannot read the board revision: %s" % exc)


def main():
    only = sys.argv[2:] or None
    try:
        p = params.load()
        b = board.load()
        L = layout.Layout(p, b)
        head = board_head()
        solids = export.build_all(p, b, L, only=only)
        for name, solid in solids.items():
            bb = solid.optimalBoundingBox()
            print("%-15s %7.1f x %7.1f x %6.1f mm  %8.0f mm3"
                  % (name, bb.XLength, bb.YLength, bb.ZLength, solid.Volume))
        paths = export.write_parts(solids, CASE_DIR, BUILD_DIR)
        if only is None:
            export.write_manifest(solids, p, head, os.path.join(CASE_DIR, "manifest.tsv"))
            export.write_case_document(solids, b, L, p, CASE_DOC)
            print("case document -> %s" % CASE_DOC)
        else:
            print("partial build: manifest and case document NOT rewritten")
        print("built: %d parts, %d files" % (len(solids), len(paths)))
        return 0
    except params.ParamError as exc:
        print("build could not start: %s" % exc)
        return 2
    except Exception as exc:                                  # noqa: BLE001
        print("build failed: %s: %s" % (type(exc).__name__, exc))
        traceback.print_exc()
        return 1
    finally:
        sys.stdout.flush()


def _is_entry_script():
    return __name__ == "__main__" or (
        len(sys.argv) > 1
        and os.path.normcase(os.path.realpath(sys.argv[1]))
        == os.path.normcase(os.path.realpath(__file__)))


if _is_entry_script():
    rc = main()
    sys.stdout.flush()
    sys.exit(rc)
```

- [ ] **Step 5: Run the tests, then the full build**

Run: `$FC tools/test_case.py test_export 2>&1 | grep -v 3Dconnexion`
Expected: `Ran 3 tests` … `OK`.

Run: `$FC tools/build_case.py 2>&1 | grep -v '3Dconnexion\|%)\|Transfer\|WorkSession\|Step File'`
Expected: eight part lines, `case document -> …/model/radio86rk-case.FCStd`, `built: 8 parts, 16 files`, exit 0. Then `ls -la model/case .build/case` shows 8 STEP, 8 STL, the manifest.

- [ ] **Step 6: Commit the tooling and the outputs**

```bash
git add tools/case/export.py tools/build_case.py tools/case/tests/test_export.py model/case/*.step model/case/manifest.tsv model/radio86rk-case.FCStd
git commit -m "Case: build_case.py writes every part as STEP and STL, a manifest, and the case document"
```

---

### Task 10: Renders — the first look (MILESTONE)

**Files:**
- Create: `tools/render_case.py`
- Create: `model/renders/case-iso.png`, `model/renders/case-rear.png`, `model/renders/case-top.png`, `model/renders/case-lid-open.png` (outputs)

**Interfaces:**
- Produces: `/Applications/FreeCAD.app/Contents/MacOS/FreeCAD tools/render_case.py` renders four 1600 × 1100 views into `model/renders/`, writes `.build/case/render.log`, closes the document, quits. Exit 0.

- [ ] **Step 1: Write `tools/render_case.py`**

```python
"""Render the case around the board. Runs in a GUI FreeCAD launched from the
shell -- no MCP needed:

    /Applications/FreeCAD.app/Contents/MacOS/FreeCAD tools/render_case.py

FreeCAD cannot save a viewport image without a GUI, and freecadcmd's
FreeCADGui is a stub (see render.py). A GUI instance started with a script
argument runs the script after the main window is up; the script renders,
closes its document and quits the application through Qt. Stdout of the GUI
app does not reliably reach the terminal, so progress goes to a log file.

Closing the document before quitting is what keeps the tracked .FCStd from
being written back on shutdown. Run `git status` afterwards regardless.
"""
import os
import sys
import traceback

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODEL = os.path.join(REPO, "model")
PROJECT = os.path.join(MODEL, "radio86rk-case.FCStd")
RENDERS = os.path.join(MODEL, "renders")
LOG = os.path.join(REPO, ".build", "case", "render.log")

WIDTH, HEIGHT, BACKGROUND = 1600, 1100, "White"

CHARCOAL = (0.17, 0.18, 0.20)
FRAME = (0.22, 0.23, 0.25)
IVORY = (0.90, 0.88, 0.80)
GREEN = (0.10, 0.45, 0.25)
DARK = (0.25, 0.25, 0.27)

COLORS = {
    "tray": CHARCOAL, "hood": CHARCOAL, "rear_plate": CHARCOAL,
    "keyboard_frame": FRAME, "lid": CHARCOAL, "lid_open": CHARCOAL,
    "bay_cover": FRAME, "foot_10": CHARCOAL, "foot_20": CHARCOAL,
    "caps": IVORY, "pcb": GREEN, "parts": DARK,
}

# (filename, orientation method, objects hidden for this view)
VIEWS = (
    ("case-iso.png", "viewAxonometric", ("lid_open", "foot_10", "foot_20")),
    ("case-top.png", "viewTop", ("lid_open", "foot_10", "foot_20")),
    ("case-rear.png", "viewRear", ("lid_open", "foot_10", "foot_20")),
    ("case-lid-open.png", "viewRear", ("lid", "foot_10", "foot_20", "hood")),
)


def render_all(project=None, out_dir=None):
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
            vo = obj.ViewObject
            if vo is None:
                continue
            if obj.Name in COLORS:
                vo.ShapeColor = COLORS[obj.Name]
        view = FreeCADGui.activeDocument().activeView()
        for filename, orient, hidden in VIEWS:
            for obj in doc.Objects:
                if obj.ViewObject is not None:
                    obj.ViewObject.Visibility = obj.Name not in hidden
            getattr(view, orient)()
            view.fitAll()
            path = os.path.join(out_dir, filename)
            view.saveImage(path, WIDTH, HEIGHT, BACKGROUND)
            size = os.path.getsize(path)
            if size < 20000:
                raise RuntimeError("%s is %d bytes: a blank canvas" % (path, size))
            written.append((path, size))
    finally:
        FreeCAD.closeDocument(name)
    return written


def _main_gui():
    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    with open(LOG, "w") as log:
        try:
            for path, size in render_all():
                log.write("%s %d bytes\n" % (os.path.basename(path), size))
            log.write("closed without saving\nok\n")
        except Exception:                                    # noqa: BLE001
            log.write(traceback.format_exc())
            log.write("FAILED\n")
    from PySide import QtCore
    QtCore.QTimer.singleShot(500, QtCore.QCoreApplication.quit)


def _is_entry_script():
    """True when the GUI was launched with this file as its script argument.

    An MCP session that imports this module gets render_all() and nothing
    else: auto-running here would render twice and quit their FreeCAD."""
    me = os.path.realpath(__file__)
    return any(a.endswith(".py") and os.path.realpath(a) == me for a in sys.argv[1:])


def _gui_is_real():
    try:
        import FreeCADGui
        return hasattr(FreeCADGui, "getDocument")   # freecadcmd's stub lacks it
    except ImportError:
        return False


if _is_entry_script() and _gui_is_real():
    _main_gui()
```

- [ ] **Step 2: Run it and look**

Run:
```bash
/Applications/FreeCAD.app/Contents/MacOS/FreeCAD tools/render_case.py >/dev/null 2>&1; echo "exit $?"; cat .build/case/render.log; git status --short
```
Expected: `exit 0`, four lines ending in `bytes`, `ok`, and `git status` showing only the four new PNGs (no `.FCStd` diff). Then open the PNGs with the Read tool and check: the case surrounds the board, keys protrude through the frame, ports appear in the rear plate cutouts, the lid hangs open in the last view.

If the process does not exit within 90 s, the guard did not run. Debug by adding, above the guard, `open(LOG + ".argv", "w").write(repr(sys.argv))` and inspect how the GUI passes the script path; adjust `_is_entry_script` to match. Kill the stray FreeCAD with `pkill -f 'FreeCAD tools/render_case.py'` and run `git status` afterwards.

- [ ] **Step 3: Show the user, then commit**

Send the four PNGs to the user with `SendUserFile` (this is the milestone the plan was ordered around), then:

```bash
git add tools/render_case.py model/renders/case-*.png
git commit -m "Case: render_case.py shoots four views in a shell-launched GUI FreeCAD"
```

---

### Task 11: Gate checks J to Q

**Files:**
- Modify: `tools/verify.py` (append after check G, before `main()`)
- Create: `tools/case/tests/test_gate_faults.py` (documents each injected fault)

**Interfaces:**
- Produces: checks `J` envelope clearance, `K` component clearance, `L` port alignment, `M` hole alignment, `N` tile size, `O` manifest currency, `P` printability, `Q` hinge geometry. Each reads `model/case/*.step` and the manifest; each raises `Skip` if the case has not been built.
- Consumes: `tools.case.*` modules; `board.load()`; `keyboard_frame.opening_face`; `rear_plate.port_cutters`, `rear_plate.socket_centres`.

- [ ] **Step 1: Add the shared loader and checks to `tools/verify.py`**

Insert after `check_pipelines_agree` (check G):

```python
CASE_DIR = os.path.join(MODEL, "case")
CASE_PART_NAMES = ("tray", "keyboard_frame", "hood", "rear_plate", "lid",
                   "bay_cover", "foot_10", "foot_20")
COMPONENT_CLEARANCE_MM = 1.0
HOLE_TOL_MM = 0.1
NOZZLE_MM = 0.4


def _case_context():
    """Params, board, layout and the built solids -- or Skip."""
    if REPO not in sys.path:
        sys.path.insert(0, REPO)
    from tools.case import board as cboard, layout, params
    import Part
    if not os.path.isdir(CASE_DIR):
        raise Skip("no %s -- run: %s" % (CASE_DIR, _howto("build_case.py")))
    try:
        p = params.load()
    except params.ParamError as exc:
        raise Skip("case.tsv: %s" % exc)
    b = cboard.load()
    L = layout.Layout(p, b)
    solids = {}
    for name in CASE_PART_NAMES:
        path = os.path.join(CASE_DIR, name + ".step")
        if not os.path.exists(path):
            if name == "bay_cover" and p.bay_side == "none":
                continue
            raise Skip("no %s -- run: %s" % (path, _howto("build_case.py")))
        shape = Part.Shape()
        shape.read(path)
        solids[name] = shape
    return p, b, L, solids


@check("J")
def check_case_envelope_clearance():
    """No case part enters the key envelope; the frame opening clears every prism."""
    import Part
    p, b, L, solids = _case_context()
    env_path = os.path.join(MODEL, "envelope.step")
    if not os.path.exists(env_path):
        raise Skip("no envelope.step -- run: %s" % _howto("build_caps.py"))
    env = Part.Shape()
    env.read(env_path)
    for name, solid in solids.items():
        if name.startswith("foot"):
            continue
        common = solid.common(env)
        if common.Volume > 1e-3:
            raise Fail("%s intersects the key envelope by %.1f mm3"
                       % (name, common.Volume))
    from tools.case import keyboard_frame
    opening = keyboard_frame.opening_face(p, b, L)
    edge = opening.OuterWire
    for prism in env.Solids:
        bb = obox(prism)
        for x, y in ((bb.XMin, bb.YMin), (bb.XMax, bb.YMax), (bb.XMin, bb.YMax), (bb.XMax, bb.YMin)):
            pt = FreeCAD.Vector(x, y, 0)
            if not opening.isInside(pt, 1e-6, True):
                raise Fail("a key corner at (%.2f, %.2f) lies outside the frame opening" % (x, y))
            dist = edge.distToShape(Part.Vertex(pt))[0]
            if dist < p.key_offset - 0.05:
                raise Fail("frame opening is %.2f mm from a key corner at (%.2f, %.2f), need %.2f"
                           % (dist, x, y, p.key_offset))


@check("K")
def check_case_component_clearance():
    """No case part within 1.0 mm of any board component, real solids."""
    p, b, L, solids = _case_context()
    worst = None
    for name, solid in solids.items():
        if name.startswith("foot"):
            continue
        sbb = obox(solid)
        for ref, comp in b.components:
            cbb = obox(comp)
            # cheap reject on boxes before the exact distance
            if (cbb.XMin > sbb.XMax + COMPONENT_CLEARANCE_MM or cbb.XMax < sbb.XMin - COMPONENT_CLEARANCE_MM
                    or cbb.YMin > sbb.YMax + COMPONENT_CLEARANCE_MM or cbb.YMax < sbb.YMin - COMPONENT_CLEARANCE_MM
                    or cbb.ZMin > sbb.ZMax + COMPONENT_CLEARANCE_MM or cbb.ZMax < sbb.ZMin - COMPONENT_CLEARANCE_MM):
                continue
            if name == "rear_plate" and ref in ("J1", "J2", "J4", "J5", "SW68"):
                continue   # they pass THROUGH the plate by design; check L owns them
            dist = solid.distToShape(comp)[0]
            if dist < COMPONENT_CLEARANCE_MM and (worst is None or dist < worst[0]):
                worst = (dist, name, ref)
    if worst:
        raise Fail("%s is %.2f mm from %s (need %.1f)" % (worst[1], worst[0], worst[2], COMPONENT_CLEARANCE_MM))


@check("L")
def check_case_port_alignment():
    """Every external connector passes through the rear plate with margin."""
    p, b, L, solids = _case_context()
    plate = solids["rear_plate"]
    from tools.case import board as cboard
    for ref in cboard.EXTERNAL_REFS:
        comp = b.component(ref)
        slab = comp.common(Part_box_through_plate(L))
        if slab.Volume < 1e-6:
            # stops short: the plug must pass -- probe the cutter's footprint instead
            continue
        common = plate.common(slab)
        if common.Volume > 1e-3:
            raise Fail("%s collides with the rear plate (%.1f mm3)" % (ref, common.Volume))
        grown = slab.makeOffsetShape(p.port_margin - 0.05, 0.01)
        if plate.common(grown).Volume > 1e-3:
            raise Fail("%s has less than %.2f mm margin in its cutout" % (ref, p.port_margin))


def Part_box_through_plate(L):
    import Part
    return Part.makeBox(400, L.y_rear_o - L.y_rear_i + 2.0, 200,
                        FreeCAD.Vector(-50, L.y_rear_i - 1.0, -100))


@check("M")
def check_case_hole_alignment():
    """Seven bosses concentric with the board's seven holes."""
    import Part
    p, b, L, solids = _case_context()
    tray = solids["tray"]
    for x, y in b.holes:
        probe = Part.makeCylinder(p.insert_d / 2.0 - 0.05, 3.0,
                                 FreeCAD.Vector(x, y, L.z_board_bottom - 3.5), FreeCAD.Vector(0, 0, 1))
        if tray.common(probe).Volume > 1e-3:
            raise Fail("boss insert hole at (%.2f, %.2f) is not clear" % (x, y))
        ring = Part.makeCylinder(p.boss_d / 2.0 - 0.2, 1.0,
                                 FreeCAD.Vector(x, y, L.z_board_bottom - 1.5), FreeCAD.Vector(0, 0, 1))
        ring = ring.cut(Part.makeCylinder(p.insert_d / 2.0 + HOLE_TOL_MM + 0.05, 1.0,
                                          FreeCAD.Vector(x, y, L.z_board_bottom - 1.5), FreeCAD.Vector(0, 0, 1)))
        if abs(tray.common(ring).Volume - ring.Volume) > 0.02 * ring.Volume:
            raise Fail("boss at (%.2f, %.2f) is off-centre by more than %.1f mm" % (x, y, HOLE_TOL_MM))


@check("N")
def check_case_tile_size():
    """Every part (or tile, once tiling exists) fits max_tile."""
    p, b, L, solids = _case_context()
    tiles_dir = os.path.join(REPO, ".build", "case", p.preset)
    import Part
    shapes = {}
    if os.path.isdir(tiles_dir):
        for fn in sorted(os.listdir(tiles_dir)):
            if fn.endswith(".step"):
                s = Part.Shape()
                s.read(os.path.join(tiles_dir, fn))
                shapes[fn] = s
    if not shapes:
        shapes = solids
    for name, s in shapes.items():
        bb = obox(s)
        if max(bb.XLength, bb.YLength) > p.max_tile + 1e-6 or bb.ZLength > 60.0:
            raise Fail("%s is %.1f x %.1f x %.1f, over max_tile %.0f (or 60 tall)"
                       % (name, bb.XLength, bb.YLength, bb.ZLength, p.max_tile))


@check("O")
def check_case_manifest_current():
    """The outputs were built from THIS case.tsv and THIS board revision."""
    p, b, L, solids = _case_context()
    path = os.path.join(CASE_DIR, "manifest.tsv")
    if not os.path.exists(path):
        raise Skip("no %s" % path)
    values = {}
    with open(path) as handle:
        for line in handle:
            if line.startswith("#") or not line.strip():
                continue
            key, rest = line.rstrip("\n").split("\t", 1)
            values[key] = rest
    if values.get("case_hash") != p.hash():
        raise Fail("case.tsv changed since the case was built -- run: %s" % _howto("build_case.py"))
    if values.get("board_head") != BOARD_HEAD:
        raise Fail("case built against board %s, pinned is %s" % (values.get("board_head"), BOARD_HEAD))
    for name in solids:
        if name not in values:
            raise Fail("manifest has no row for %s" % name)


@check("P")
def check_case_printability():
    """Every part survives an inward offset of two nozzle widths."""
    p, b, L, solids = _case_context()
    for name, solid in solids.items():
        try:
            inner = solid.makeOffsetShape(-2 * NOZZLE_MM, 0.01)
            vanished = inner.isNull() or inner.Volume < 1e-3
        except Exception:                                    # noqa: BLE001
            vanished = True
        if vanished:
            raise Fail("%s has a wall thinner than %.1f mm somewhere" % (name, 2 * NOZZLE_MM))


@check("Q")
def check_case_hinge_geometry():
    """Sockets and studs coaxial; hinge above the tallest flanking port."""
    p, b, L, solids = _case_context()
    from tools.case import rear_plate, board as cboard
    centres = rear_plate.socket_centres(p, b, L)
    if abs(centres[0][2] - centres[1][2]) > 1e-6 or abs(centres[0][1] - centres[1][1]) > 1e-6:
        raise Fail("socket centres are not coaxial: %r" % (centres,))
    lid = solids["lid"]
    for x, y, z in centres:
        if not lid.isInside(FreeCAD.Vector(x, y, z), 1e-6, True):
            raise Fail("lid has no stud at socket centre (%.2f, %.2f, %.2f)" % (x, y, z))
    for ref in ("J4", "J5"):
        top = obox(b.component(ref)).ZMax
        if L.z_hinge - 3.5 < top + COMPONENT_CLEARANCE_MM:   # 3.5 = socket block foot below the axis
            raise Fail("hinge_z %.1f puts the socket blocks within %.1f mm of %s (top %.2f)"
                       % (L.z_hinge, COMPONENT_CLEARANCE_MM, ref, top))
```

Also add `import FreeCAD` at the top of `verify.py` next to the existing imports if it is not already imported at module level (check H imports `Part` locally; follow the same local-import style if you prefer, but `FreeCAD.Vector` is used in several checks above, so a module-level `import FreeCAD` guarded by the existing try/except is simplest).

- [ ] **Step 2: Run the new checks**

Run: `$FC tools/verify.py J K L M N O P Q 2>&1 | grep -v '3Dconnexion\|%)'`
Expected: eight `PASS` lines and `verdict: PASS`. If K fails, read the failing part and ref: the most likely first finding is the keyboard frame against a switch housing or an LED, or a hood boss against a capacitor. Fix the geometry in the part module, rebuild, re-run. Do not loosen `COMPONENT_CLEARANCE_MM`.

- [ ] **Step 3: Demonstrate each check failing on an injected fault**

For each row, apply the fault, rebuild if the fault is in `case.tsv` or code, run the single check, confirm `FAIL`, revert. Record the confirmation in `tools/case/tests/test_gate_faults.py` as a docstring table (this file is documentation that lives with the tests; it contains one trivial test so the runner picks it up):

| Check | Fault | Command |
|---|---|---|
| J | `key_offset` → `-0.5` in `case.tsv`, rebuild | `$FC tools/verify.py J` |
| K | `deck_z` → `20`, rebuild | `$FC tools/verify.py K` |
| L | in `rear_plate.port_cutters`, temporarily `face.translate(V(2.0, 0, 0))` for `ref == "J1"` before offsetting, rebuild | `$FC tools/verify.py L` |
| M | swap two entries in `b.holes` inside `tray.board_bosses` (e.g. `holes[0], holes[1] = holes[1], holes[0]`), rebuild | `$FC tools/verify.py M` |
| N | `max_tile` → `100`, do NOT rebuild | `$FC tools/verify.py N` |
| O | edit any value in `case.tsv` after building, do NOT rebuild | `$FC tools/verify.py O` |
| P | `plate` → `0.6`, rebuild | `$FC tools/verify.py P` |
| Q | `hinge_z` → `15`, rebuild | `$FC tools/verify.py Q` |

```python
"""Injected faults each gate check has been seen to FAIL on.

| check | fault                                     | seen failing |
|-------|-------------------------------------------|--------------|
| J     | key_offset -0.5                           | yes, <date>  |
| K     | deck_z 20                                 | yes, <date>  |
| L     | J1 cutter shifted 2 mm                    | yes, <date>  |
| M     | two board holes swapped in tray.py        | yes, <date>  |
| N     | max_tile 100 without rebuild              | yes, <date>  |
| O     | case.tsv edited after build               | yes, <date>  |
| P     | plate 0.6                                 | yes, <date>  |
| Q     | hinge_z 15                                | yes, <date>  |

Fill the date column as each is confirmed. A row without a date is a check
nobody has seen fail, and the repo's rule is that such a check is decoration.
"""
import unittest


class FaultTableTest(unittest.TestCase):
    def test_every_row_dated(self):
        rows = [l for l in __doc__.splitlines() if l.startswith("| ") and "check" not in l and "---" not in l]
        self.assertEqual(len(rows), 8)
        for row in rows:
            self.assertNotIn("<date>", row, row)
```

After all eight are confirmed, replace each `<date>` with the actual date so the test passes. Restore `case.tsv` and the code, rebuild, confirm `$FC tools/verify.py` reports `verdict: PASS` for the full gate.

- [ ] **Step 4: Commit**

```bash
git add tools/verify.py tools/case/tests/test_gate_faults.py model/case
git commit -m "Gate: eight case checks J-Q, each demonstrated failing on an injected fault"
```

---

### Task 12: Tiling by `max_tile`

**Files:**
- Create: `tools/case/tiling.py`
- Create: `tools/case/tests/test_tiling.py`
- Modify: `tools/case/export.py` (add `write_tiles`)
- Modify: `tools/build_case.py` (call `write_tiles` for the active preset; accept a preset name as the first positional argument when it is one of `mini`, `standard`, `large`)

**Interfaces:**
- Produces: `tiling.split(solid, max_tile, keep_out_x, p, spec=None) -> list[Part.Solid]`: cuts along X (planes of constant X) into the fewest pieces whose X length ≤ `max_tile`, nudging each cut to the nearest X outside every interval in `keep_out_x` (list of `(x0, x1)`), leaving `tile_gap` between pieces. When `spec` is given, each side of every cut gets joiner pads per the spec: 10 (X) × 10 × 6 blocks with a Ø `pin_d + 0.2` blind pin hole 5 deep along X across the seam and a Ø `insert_d` insert hole for a strap. `spec` is a `PadSpec(anchor, positions)`: `anchor` is `"floor"` (pads stand on the part's floor top at the given Y positions, found by probing the solid at that XY), `"under"` (pads hang from the part's underside at the given Y positions), or `"front"` (pads on the part's −Y face at the given `(z0, z1)` span, one tall pad per side). `spec=None` means a plain cut with no pads — the keyboard frame, whose halves are each held by their own rim screw and clamped by the hood.
- Produces: `tiling.pad_spec(p, b, L, name) -> PadSpec or None`: tray `("floor", [-150.0, -20.0])` (the wedge leaves 12 mm under the board at Y −150 and 27 mm at Y −20; at the front there is only 5 mm, so no pad there); hood `("under", [-80.0, -14.0])`; rear plate `("front", [(L.z_hinge - 1.0, L.z_deck)])` (above every port, one pad per side); keyboard frame `None`.
- Produces: `tiling.strap(p) -> Part.Solid` (30 × 10 × 3 bar, two Ø `screw_clear_d` holes 20 apart). `tiling.keep_outs(p, b, L, name) -> list[(x0, x1)]`: tray: board bosses, hood bosses and rear-plate screw X ± margins; rear plate: window edges ± (`socket_block` + 4) and every external connector ± 3; keyboard frame: the two rim screws ± 6 and the two LED holes ± 4 (the ring may be cut anywhere else); hood: hood bosses ± 6 and the lid notch span ± 4.
- Produces: `export.write_tiles(solids, p, b, L, out_dir) -> list[path]` writing `<out_dir>/<name>-<n>.step` and `.stl` for every part wider than `max_tile`, plus `strap.step/.stl` if any part was cut.

- [ ] **Step 1: Write the failing test**

```python
import unittest

import Part

from tools.case import board, geom, layout, params, tiling


class TilingTest(unittest.TestCase):
    def test_narrow_part_is_untouched(self):
        p = params.load()
        s = Part.makeBox(100, 50, 10)
        self.assertEqual(len(tiling.split(s, 256.0, [], p)), 1)

    def test_wide_slab_splits_in_two_clear_of_keep_outs(self):
        p = params.load()
        s = Part.makeBox(300, 50, 10)
        tiles = tiling.split(s, 256.0, [(140.0, 160.0)], p)
        self.assertEqual(len(tiles), 2)
        xs = sorted(geom.obox(t).XMax for t in tiles)
        cut_x = xs[0]
        self.assertTrue(cut_x <= 140.0 or cut_x >= 160.0 + p.tile_gap)
        for t in tiles:
            self.assertLessEqual(geom.obox(t).XLength, 256.0 + 1e-6)
            self.assertTrue(t.isValid())

    def test_floor_pads_stand_on_the_slab(self):
        p = params.load()
        s = Part.makeBox(300, 50, 3)                      # a 3 mm floor
        spec = tiling.PadSpec("floor", [10.0, 40.0])
        a, b_ = tiling.split(s, 256.0, [], p, spec)
        for t in (a, b_):
            self.assertTrue(t.isValid())
            self.assertAlmostEqual(geom.obox(t).ZMax, 3.0 + tiling.PAD_H, 3)   # pad on top
        # pin hole across the seam on the left tile
        x_cut = geom.obox(a).XMax
        self.assertFalse(a.isInside(geom.V(x_cut - 1.0, 10.0, 3.0 + tiling.PAD_H / 2.0), 1e-6, True))

    def test_under_pads_hang_below(self):
        p = params.load()
        s = Part.makeBox(300, 50, 3, geom.V(0, 0, 40))    # a plate at Z 40
        a, _ = tiling.split(s, 256.0, [], p, tiling.PadSpec("under", [10.0, 40.0]))
        self.assertAlmostEqual(geom.obox(a).ZMin, 40.0 - tiling.PAD_H, 3)

    def test_front_pads_on_minus_y_face(self):
        p = params.load()
        s = Part.makeBox(300, 3, 50)                      # a vertical plate, Y 0..3
        a, _ = tiling.split(s, 256.0, [], p, tiling.PadSpec("front", [(10.0, 40.0)]))
        self.assertAlmostEqual(geom.obox(a).YMin, -tiling.PAD_H, 3)

    def test_no_spec_means_plain_cut(self):
        p = params.load()
        s = Part.makeBox(300, 50, 3)
        a, _ = tiling.split(s, 256.0, [], p, None)
        self.assertAlmostEqual(geom.obox(a).ZMax, 3.0, 3)

    def test_tray_keep_outs_cover_every_boss(self):
        p = params.load()
        b = board.load()
        L = layout.Layout(p, b)
        outs = tiling.keep_outs(p, b, L, "tray")
        for x, _y in b.holes:
            self.assertTrue(any(x0 <= x <= x1 for x0, x1 in outs), x)
        self.assertEqual(tiling.pad_spec(p, b, L, "keyboard_frame"), None)
        self.assertEqual(tiling.pad_spec(p, b, L, "tray").anchor, "floor")

    def test_strap(self):
        p = params.load()
        s = tiling.strap(p)
        self.assertTrue(s.isValid())
        self.assertAlmostEqual(geom.obox(s).XLength, 30.0, 3)
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `$FC tools/test_case.py test_tiling 2>&1 | grep -v 3Dconnexion`
Expected: ImportError, exit 1.

- [ ] **Step 3: Write `tools/case/tiling.py`**

```python
"""Cut an oversize part into printable tiles, after modelling.

Cuts are planes of constant X. Where a PadSpec is given, each side of a cut
gets joiner pads with a pin hole across the seam and an insert hole for a
strap. The tiling is a pure post-process: the gate measures the uncut solid.
"""
import collections
import math

import Part

from tools.case import geom
from tools.case.geom import V, prism, cyl_z, fuse_all, cut_all

PAD = 10.0
PAD_H = 6.0
PIN_DEPTH = 5.0
STRAP_L, STRAP_W, STRAP_T, STRAP_PITCH = 30.0, 10.0, 3.0, 20.0

# anchor: "floor" | "under" | "front"; positions: Y values for floor/under,
# (z0, z1) spans for front
PadSpec = collections.namedtuple("PadSpec", "anchor positions")


def pad_spec(p, b, L, name):
    if name == "tray":
        return PadSpec("floor", [-150.0, -20.0])
    if name == "hood":
        return PadSpec("under", [-80.0, -14.0])
    if name == "rear_plate":
        return PadSpec("front", [(L.z_hinge - 1.0, L.z_deck)])
    return None


def keep_outs(p, b, L, name):
    outs = []
    if name == "tray":
        r = p.boss_d / 2.0 + 4.0
        outs += [(x - r, x + r) for x, _y in b.holes]
        outs += [(x - r, x + r) for x, _y in L.hood_bosses]
        outs += [(x - 6.0, x + 6.0) for x, _z in L.rear_plate_screws]
    elif name == "rear_plate":
        w = p.socket_block + 4.0
        outs += [(L.x_win0 - w, L.x_win0 + 1.0), (L.x_win1 - 1.0, L.x_win1 + w)]
        for ref in ("J1", "J2", "J4", "J5", "SW68"):
            bb = geom.obox(b.component(ref))
            outs.append((bb.XMin - 3.0, bb.XMax + 3.0))
    elif name == "keyboard_frame":
        outs += [(x - 6.0, x + 6.0) for x, _y in L.frame_screws]
        for ref in ("D10", "D11"):
            bb = geom.obox(b.component(ref))
            outs.append((bb.XMin - 4.0, bb.XMax + 4.0))
    elif name == "hood":
        outs += [(x - 6.0, x + 6.0) for x, _y in L.hood_bosses]
        outs.append((L.x_win0 - 4.0, L.x_win1 + 4.0))
    return outs


def _free_x(x, keep_out_x, xmin, xmax):
    """Nearest X to `x` not inside any keep-out interval."""
    def blocked(v):
        return any(x0 <= v <= x1 for x0, x1 in keep_out_x)
    if not blocked(x):
        return x
    for d in range(1, 400):
        for cand in (x - d * 0.5, x + d * 0.5):
            if xmin + 5.0 < cand < xmax - 5.0 and not blocked(cand):
                return cand
    raise ValueError("no cut position free of keep-outs near X %.1f" % x)


def _floor_top_at(solid, x, y):
    """Top of the lowest material column at (x, y): the floor's upper face."""
    probe = Part.makeCylinder(0.3, 800.0, V(x, y, -400.0), V(0, 0, 1))
    hit = solid.common(probe)
    if not hit.Solids:
        raise ValueError("no material under (%.1f, %.1f) to place a pad on" % (x, y))
    return min(geom.obox(s).ZMax for s in hit.Solids)


def _pads_and_holes(solid, x_cut, side, p, spec):
    """Pads on `side` (-1 left, +1 right) of the cut, per the spec."""
    pads, holes = [], []
    x0 = x_cut - PAD if side < 0 else x_cut
    xi = x_cut - PAD / 2.0 if side < 0 else x_cut + PAD / 2.0
    x_pin0 = x_cut - PIN_DEPTH if side < 0 else x_cut - 0.01
    pin_len = PIN_DEPTH + 0.01
    pin_r = (p.pin_d + 0.2) / 2.0

    if spec.anchor == "floor":
        for y in spec.positions:
            z0 = _floor_top_at(solid, xi, y)
            pads.append(prism(x0, x0 + PAD, y - PAD / 2.0, y + PAD / 2.0, z0 - 0.5, z0 + PAD_H))
            holes.append(Part.makeCylinder(pin_r, pin_len, V(x_pin0, y, z0 + PAD_H / 2.0), V(1, 0, 0)))
            holes.append(cyl_z(xi, y, z0 + PAD_H - p.insert_depth, z0 + PAD_H + 0.1, p.insert_d))
    elif spec.anchor == "under":
        z1 = geom.obox(solid).ZMin              # the plate's underside
        for y in spec.positions:
            pads.append(prism(x0, x0 + PAD, y - PAD / 2.0, y + PAD / 2.0, z1 - PAD_H, z1 + 0.5))
            holes.append(Part.makeCylinder(pin_r, pin_len, V(x_pin0, y, z1 - PAD_H / 2.0), V(1, 0, 0)))
            holes.append(cyl_z(xi, y, z1 - PAD_H - 0.1, z1 - PAD_H + p.insert_depth, p.insert_d))
    elif spec.anchor == "front":
        y1 = geom.obox(solid).YMin              # the plate's inner (-Y) face
        for z0, z1 in spec.positions:
            pads.append(prism(x0, x0 + PAD, y1 - PAD_H, y1 + 0.5, z0, z1))
            zc = (z0 + z1) / 2.0
            holes.append(Part.makeCylinder(pin_r, pin_len, V(x_pin0, y1 - PAD_H / 2.0, zc), V(1, 0, 0)))
            for z in (z0 + 4.0, z1 - 4.0):
                holes.append(Part.makeCylinder(p.insert_d / 2.0, p.insert_depth + 0.1,
                                               V(xi, y1 - PAD_H - 0.1, z), V(0, 1, 0)))
    else:
        raise ValueError("unknown pad anchor %r" % spec.anchor)
    return pads, holes


def split(solid, max_tile, keep_out_x, p, spec=None):
    bb = geom.obox(solid)
    if bb.XLength <= max_tile:
        return [solid]
    n = int(math.ceil(bb.XLength / (max_tile - p.tile_gap)))
    cuts = [bb.XMin + bb.XLength * i / n for i in range(1, n)]
    cuts = [_free_x(x, keep_out_x, bb.XMin, bb.XMax) for x in cuts]
    tiles = []
    edges = [bb.XMin - 1.0] + cuts + [bb.XMax + 1.0]
    for i in range(len(edges) - 1):
        x0 = edges[i] + (p.tile_gap / 2.0 if i > 0 else 0.0)
        x1 = edges[i + 1] - (p.tile_gap / 2.0 if i < len(edges) - 2 else 0.0)
        clip = prism(x0, x1, bb.YMin - 1.0, bb.YMax + 1.0, bb.ZMin - 1.0, bb.ZMax + 1.0)
        tile = solid.common(clip)
        pads, holes = [], []
        if spec is not None:
            if i > 0:
                a, h = _pads_and_holes(solid, edges[i] + p.tile_gap / 2.0, +1, p, spec)
                pads += a
                holes += h
            if i < len(edges) - 2:
                a, h = _pads_and_holes(solid, edges[i + 1] - p.tile_gap / 2.0, -1, p, spec)
                pads += a
                holes += h
        if pads:
            tile = cut_all(fuse_all([tile] + pads), holes)
        tiles.append(tile)
    for t in tiles:
        if geom.obox(t).XLength > max_tile + 1e-6:
            raise ValueError("a tile is still wider than max_tile after cutting")
    return tiles


def strap(p):
    bar = prism(0, STRAP_L, 0, STRAP_W, 0, STRAP_T)
    holes = [cyl_z(STRAP_L / 2.0 - STRAP_PITCH / 2.0, STRAP_W / 2.0, -1, STRAP_T + 1, p.screw_clear_d),
             cyl_z(STRAP_L / 2.0 + STRAP_PITCH / 2.0, STRAP_W / 2.0, -1, STRAP_T + 1, p.screw_clear_d)]
    return cut_all(bar, holes)
```

- [ ] **Step 4: Add `write_tiles` to `export.py` and wire it into `build_case.py`**

In `export.py`:

```python
def write_tiles(solids, p, b, L, out_dir):
    from tools.case import tiling
    os.makedirs(out_dir, exist_ok=True)
    paths = []
    any_cut = False
    for name, solid in solids.items():
        tiles = tiling.split(solid, p.max_tile, tiling.keep_outs(p, b, L, name), p,
                             tiling.pad_spec(p, b, L, name))
        if len(tiles) == 1:
            continue
        any_cut = True
        for i, tile in enumerate(tiles, 1):
            base = os.path.join(out_dir, "%s-%d" % (name, i))
            tile.exportStep(base + ".step")
            tile.exportStl(base + ".stl")
            paths += [base + ".step", base + ".stl"]
    if any_cut:
        s = tiling.strap(p)
        base = os.path.join(out_dir, "strap")
        s.exportStep(base + ".step")
        s.exportStl(base + ".stl")
        paths += [base + ".step", base + ".stl"]
    return paths
```

In `build_case.py` `main()`: if `sys.argv[2:]` and `sys.argv[2] in params.PRESETS`, set `p.raw["max_tile"] = str(params.preset_tile(sys.argv[2]))`, `p.raw["preset"] = sys.argv[2]`, and treat the remaining args as `only`. After `write_parts`, when `only is None`: `tile_paths = export.write_tiles(solids, p, b, L, os.path.join(BUILD_DIR, p.preset))` and print `"tiles (%s, max_tile %.0f): %d files" % (p.preset, p.max_tile, len(tile_paths))`. Note that `p.max_tile` is read through `__getattr__`, so changing `p.raw` is enough. Because `p.hash()` hashes the *file*, a preset given on the command line does not change the manifest hash — that is intended: presets are a print-time choice, not a design change.

- [ ] **Step 5: Run tests and the three presets**

Run: `$FC tools/test_case.py test_tiling 2>&1 | grep -v 3Dconnexion` → `Ran 8 tests` … `OK`.
Run: `for pr in mini standard large; do $FC tools/build_case.py $pr 2>&1 | grep -E 'tiles|built'; done`
Expected: `large` cuts nothing (`0 files`); `standard` cuts tray, keyboard_frame, hood and rear_plate once each; `mini` cuts them twice. Then `$FC tools/verify.py N` passes for the preset in `case.tsv` (`standard`). Also run `$FC tools/verify.py K` once more: the tray's floor pads at Y −150 and −20 sit under the board, and K is what proves they clear it and every pin below it.

- [ ] **Step 6: Commit**

```bash
git add tools/case/tiling.py tools/case/tests/test_tiling.py tools/case/export.py tools/build_case.py
git commit -m "Case: tile oversize parts by max_tile with pads, pins and a strap; three presets"
```

---

### Task 13: Polish — inclined step, chamfers, dovetail feet

**Files:**
- Modify: `tools/case/hood.py` (step face at `step_angle`)
- Modify: `tools/case/tray.py` (outer vertical-edge chamfers; dovetail slots for feet)
- Modify: `tools/case/feet.py` (dovetail tongue)
- Modify: `case.tsv` (`step_angle` 90 → 60)
- Modify: tests accordingly

- [ ] **Step 1: Inclined step face.** In `hood.py`, replace the vertical `step` prism with a prism whose front face is inclined: build the vertical prism from `y_step` to `y_step_back + run`, where `run = (z_deck - z_frame_top) / tan(radians(step_angle))`, then cut with a big box rotated about the X axis through `(y_step, z_frame_top)` by `-(90 - step_angle)` so the face leans back. Update `test_step_face_reaches_the_frame` to probe at Y `y_step + run/2 + wall/2` at mid-height. Confirm `y_step + run` stays in front of the hood bosses at Y −86.5 for `step_angle` 60 (run ≈ 19 mm from −93 → −74; bosses at −90..−83 collide!). Therefore also move `hood_bosses` front pair to Y −72 in `layout.py` and confirm with check K that nothing on the board is within 1 mm there (RN1 is at X 250–252, Y −81..−56, so the right boss at X 267–274 is clear; the left boss at X 3–10 is clear of C44 at X 12.7).

- [ ] **Step 2: Chamfers.** In `tray.py`, after `below_plane`, chamfer the outer vertical edges of the tray by `p.chamfer` using `geom.vertical_edges` filtered to edges whose X is within 0.01 of `x0o` or `x1o`. Wrap in try/except and fall back to no chamfer with a printed warning if OCC refuses (chamfers on edges that meet the inclined underside sometimes fail). Add a test that the tray's corner point `(x0o + 0.5, y_rear_o - 0.5, z_deck - 1)` is now outside the solid.

- [ ] **Step 3: Dovetail feet.** Replace the rectangular tongue with a trapezoid: extrude a `Part.makePolygon` trapezoid (bottom width 20, top width 24, height 4) along Y for `TONGUE_D`; cut matching slots into the tray's underside at two rear positions (X 40 and 235, Y `y_rear_o - 30`), rotated to the underside plane by `-wedge_angle` about X. Test: a foot's tongue `common` with the tray slot cutter has volume > 0.9 × tongue volume.

- [ ] **Step 4: Rebuild, gate, render, commit**

```bash
$FC tools/test_case.py && $FC tools/build_case.py && $FC tools/verify.py && /Applications/FreeCAD.app/Contents/MacOS/FreeCAD tools/render_case.py >/dev/null 2>&1; cat .build/case/render.log; git status --short
git add -A tools/case case.tsv model/case model/renders/case-*.png model/radio86rk-case.FCStd
git commit -m "Case polish: inclined step face, outer chamfers, dovetail tilt feet"
```

---

### Task 14: Documentation

**Files:**
- Modify: `README.md` (new section "The case", commands, parts table, presets, renders)
- Modify: `CLAUDE.md` (add: `build_case.py`, `test_case.py`, `render_case.py` commands; the GUI-from-shell render path and that it must close documents before quitting; the zsh `=` note; that checks J–Q exist and their fault table lives in `test_gate_faults.py`)
- Modify: `docs/superpowers/specs/2026-09-09-case-design.md` (append a short "As built" note listing the deviations from this plan's header)

- [ ] **Step 1: README.** Add after "Designing a case against the envelope": what `build_case.py` writes and where; the eight parts and what each is for (one line each); `case.tsv` and how to change a number; the three presets and the `max_tile` rule; the four renders embedded; the new checks by letter with one line each; the GUI render command with the `git status` reminder.

- [ ] **Step 2: CLAUDE.md.** Under "One interpreter", add the three new commands. Add a section "Renders without the MCP" describing the shell-launched GUI, the log file, and the close-before-quit rule. Extend "The gate" with `J`–`Q` and the injected-fault table location.

- [ ] **Step 3: Spec "As built" note** and commit:

```bash
git add README.md CLAUDE.md docs/superpowers/specs/2026-09-09-case-design.md
git commit -m "Docs: the case -- build, parameters, presets, renders, and the new gate checks"
```

- [ ] **Step 4: Final full run and report**

```bash
$FC tools/test_case.py 2>&1 | tail -3
$FC tools/build_case.py 2>&1 | grep -E 'built|tiles'
$FC tools/verify.py 2>&1 | grep -E '^(PASS|FAIL|SKIP)|verdict'
git status --short
```
Expected: tests `OK`; `built: 8 parts`; `verdict: PASS`; clean tree.

---

## Self-review against the spec

- §1 goals: printer-agnostic (Task 12), modular (Tasks 4–8 as separate parts), accurate rear plate (Task 7), swappable frame (Task 5), J6 access (Tasks 7–8), Yamaha look (Tasks 6, 13), parameters (Task 1). Covered.
- §4 parts: tray 4, frame 5, deck/hood 6, rear plate 7, lid/bay/feet 8. Front rim is part of the tray (4). Covered. Deviations listed in the header.
- §5 parameters: every key in the spec table appears in `case.tsv`, plus the added `rim_depth`, `rim_ledge`, `frame_z`, `step_gap`, `led_hole_d`, `plug_margin`, `reset_margin`, `socket_block`, `bay_z`, `insert_depth`, `screw_clear_d`.
- §6 tooling: layout matches; `bay.py` and `feet.py` exist; `hood.py` replaces `deck.py` by name (the spec's "deck" is the hood's top plate). Task 14 notes this.
- §7 outputs: STEP tracked in `model/case/`, manifest, case document, renders, STL and tiles in `.build/case/`. Covered (Tasks 9, 10, 12).
- §8 gate: eight checks with faults (Task 11). Covered.
- §9 options: `eprom_hatches`, `labels` (parameter exists; recess geometry is not implemented in this plan — the spec marks it optional and off, so it stays a documented no-op until asked).
- §10 verification: gate (11), renders (10, 13), physical print (user's step after Task 10; the plan tells the user which parts to print first in the Task 10 report).
- Type consistency: `part(p, b, L)` everywhere; `Layout` attribute names used identically in tests and modules; `socket_centres` returns `(x, y, z)` triples in both `rear_plate` and `lid`; `bay_opening_box` lives in `tray` and is imported by `bay`; `lid_notch_box` lives in `hood`.
