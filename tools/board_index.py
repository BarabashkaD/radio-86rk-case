"""Read switch footprints straight from the .kicad_pcb, headless.

kicad_parser is KiCadStepUp's own parser and, unlike the workbench, imports
fine under freecadcmd. Reading the board's s-expressions directly means a
legend containing a double quote -- SW19's is `2 "` -- cannot corrupt the
data the way kicad-cli's CSV export did.
"""
import os
import sys

# Derived from $HOME so a checkout works for anyone, and overridable for a
# non-default FreeCAD install -- the same idiom as RADIO86RK_BOARD below.
KSU_MOD = os.environ.get(
    "KSU_MOD",
    os.path.expanduser("~/Library/Application Support/FreeCAD/v1-1/"
                       "Mod/kicadStepUpMod"))
# The repo root, one level up: this file lives in tools/.
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BOARD = os.environ.get("RADIO86RK_BOARD",
                       os.path.join(os.path.dirname(REPO), "radio-86rk"))
PCB = os.path.join(BOARD, "KiCad", "Radio-86RK.kicad_pcb")

SUFFIX_UNITS = {"100H": 1.00, "125H": 1.25, "150H": 1.50,
                "225H": 2.25, "625H": 6.25}


def build(pcb_path=None):
    """Return {ref: (suffix, units)} for every CHERRY_PCB_* footprint."""
    path = pcb_path or PCB
    if not os.path.exists(path):
        raise IOError("no board at %s" % path)
    if KSU_MOD not in sys.path:
        sys.path.insert(0, KSU_MOD)
    import kicad_parser
    pcb = kicad_parser.KicadPCB.load(path)

    index = {}
    for footprint in pcb.footprint:
        lib = str(footprint[0]).strip('"')
        if "CHERRY_PCB_" not in lib:
            continue
        suffix = lib.split("CHERRY_PCB_")[-1].strip('"')
        ref = None
        for prop in footprint.property:
            try:
                if str(prop[0]).strip('"') == "Reference":
                    ref = str(prop[1]).strip('"')
                    break
            except Exception:                      # noqa: BLE001
                continue
        if ref is None:
            raise ValueError("a %s footprint has no Reference property" % lib)
        index[ref] = (suffix, SUFFIX_UNITS.get(suffix))
    return index


def _next_token(text, i):
    """Return (kind, value, next_index); kind is '(' ')' 'str' 'sym' or None.

    Quoted strings honour backslash escapes. SW19's Value is written
    `"2 \\""` in the board file, and a scanner that stops at the first bare
    quote loses the rest of that footprint -- which is the shape of the
    defect that dropped SW19 from D1's export.
    """
    n = len(text)
    while i < n and text[i].isspace():
        i += 1
    if i >= n:
        return None, None, i
    char = text[i]
    if char in "()":
        return char, char, i + 1
    if char == '"':
        buf = []
        j = i + 1
        while j < n:
            if text[j] == "\\" and j + 1 < n:
                buf.append(text[j + 1])
                j += 2
                continue
            if text[j] == '"':
                j += 1
                break
            buf.append(text[j])
            j += 1
        return "str", "".join(buf), j
    j = i
    while j < n and not text[j].isspace() and text[j] not in "()":
        j += 1
    return "sym", text[i:j], j


def build_raw(pcb_path=None):
    """The same map, read by a scanner that shares no code with build().

    build() goes through kicad_parser, which is KiCadStepUp's module. Two
    readers that both call it agree by construction: a defect inside it
    yields two identical wrong answers and nothing notices. This one uses
    the standard library only -- no ksu, no FreeCAD -- so comparing the two
    is a real test rather than a tautology.

    Deliberately a different algorithm, not a rewrite of build(): a token
    scan that tracks list depth, rather than an object model. Duplicating
    the parsing STRATEGY would reintroduce the correlation this exists to
    remove.
    """
    path = pcb_path or PCB
    if not os.path.exists(path):
        raise IOError("no board at %s" % path)
    with open(path) as handle:
        text = handle.read()

    index = {}
    stack = []                  # head symbol of each open list, innermost last
    footprint_depth = None      # depth of the footprint list currently open
    lib = ref = prop_name = None
    argc = {}                   # depth -> atoms seen after that list's head
    i = 0
    while True:
        kind, value, i = _next_token(text, i)
        if kind is None:
            break
        if kind == "(":
            stack.append(None)
            argc[len(stack)] = 0
            continue
        if kind == ")":
            depth = len(stack)
            head = stack.pop() if stack else None
            argc.pop(depth, None)
            if head == "footprint" and footprint_depth == depth:
                if ref is None:
                    raise ValueError("a %s footprint has no Reference "
                                     "property" % lib)
                if lib and "CHERRY_PCB_" in lib:
                    suffix = lib.split("CHERRY_PCB_")[-1]
                    index[ref] = (suffix, SUFFIX_UNITS.get(suffix))
                footprint_depth = None
                lib = ref = None
            continue

        depth = len(stack)
        if depth == 0:
            continue
        if stack[-1] is None:                       # this atom is the head
            stack[-1] = value if kind == "sym" else ""
            if stack[-1] == "footprint" and footprint_depth is None:
                footprint_depth = depth
                lib = ref = None
            elif stack[-1] == "property":
                prop_name = None
            continue

        argc[depth] = argc.get(depth, 0) + 1
        position = argc[depth]
        if stack[-1] == "footprint" and depth == footprint_depth:
            if position == 1 and kind == "str":
                lib = value
        elif stack[-1] == "property" and footprint_depth is not None:
            if position == 1 and kind == "str":
                prop_name = value
            elif position == 2 and kind == "str" and prop_name == "Reference":
                # Only the footprint's own Reference, not a nested one.
                if depth == footprint_depth + 1:
                    ref = value
    if stack:
        raise ValueError("unbalanced parentheses in %s" % path)
    return index
