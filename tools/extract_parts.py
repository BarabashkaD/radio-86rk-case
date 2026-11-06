# Export the case parts of the current accepted FCStd to .build/parts/<sha12>/ with parts-manifest.json.
#
# Run:   tools/fcq tools/extract_parts.py
# Env (optional): SRC   — FCStd to export (default: the file named in case/CURRENT.path)
#                 STL=1 — also write print meshes (MeshPart 0.015 / 0.08, Relative=False)
# Prints one line RESULT {json}. Exported parts are derived files: check them with tools/parts_check.py
# before use, and never commit them (.build/ is ignored).
import hashlib
import json
import os
import sys
import time
import traceback

import FreeCAD as App
import Part

REPO = os.path.dirname(os.path.dirname(os.path.abspath(sys.argv[1] if len(sys.argv) > 1 and sys.argv[1].endswith(".py") else __file__)))
# Object name in the assembly -> short part name. Links are exported with their placement applied.
PARTS = [
    ("Case", "lower"),
    ("UpperOcc01", "upper"),
    ("UpperOcc18", "cover"),
    ("Big", "leg-big-left"),
    ("Small", "leg-small-left"),
    ("RightBig", "leg-big-right"),
    ("RightSmall", "leg-small-right"),
]


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def facts(shape):
    bb = shape.BoundBox
    return {"solids": len(shape.Solids), "faces": len(shape.Faces), "edges": len(shape.Edges),
            "volume": round(shape.Volume, 6), "area": round(shape.Area, 6),
            "bb": [round(v, 6) for v in (bb.XMin, bb.YMin, bb.ZMin, bb.XMax, bb.YMax, bb.ZMax)]}


def main():
    t0 = time.time()
    src = os.environ.get("SRC")
    if not src:
        with open(os.path.join(REPO, "case", "CURRENT.path"), encoding="utf-8") as fh:
            src = os.path.join(REPO, "case", fh.read().strip())
    src = os.path.abspath(src)
    src_sha = sha256(src)
    out_dir = os.path.join(REPO, ".build", "parts", src_sha[:12])
    os.makedirs(out_dir, exist_ok=True)
    for name in os.listdir(out_dir):            # never leave files from an earlier, failed run
        os.remove(os.path.join(out_dir, name))
    doc = App.openDocument(src)
    parts = []
    problems = []
    for obj_name, short in PARTS:
        obj = doc.getObject(obj_name)
        if obj is None:
            problems.append("missing object " + obj_name)
            continue
        shape = Part.getShape(obj, "", transform=True)
        expected = facts(shape)
        path = os.path.join(out_dir, "part-%s.brep" % short)
        shape.exportBrep(path)
        back = Part.Shape()
        back.read(path)
        got = facts(back)
        if got != expected:
            problems.append("%s: re-read differs %s vs %s" % (short, got, expected))
        entry = {"part": short, "object": obj_name, "label": obj.Label, "file": os.path.basename(path),
                 "file_sha256": sha256(path), **expected}
        if os.environ.get("STL") == "1":
            import MeshPart
            mesh = MeshPart.meshFromShape(Shape=shape.copy(), LinearDeflection=0.015, AngularDeflection=0.08, Relative=False)
            stl = os.path.join(out_dir, "part-%s.stl" % short)
            mesh.write(stl)
            entry["stl"] = {"file": os.path.basename(stl), "file_sha256": sha256(stl), "facets": mesh.CountFacets,
                            "closed": mesh.isSolid(), "non_manifold": mesh.hasNonManifolds()}
        parts.append(entry)
    App.closeDocument(doc.Name)
    manifest = {"source": os.path.relpath(src, REPO), "source_sha256": src_sha,
                "created": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "freecad": ".".join(App.Version()[:3]),
                "export": "Part.getShape(obj, '', transform=True).exportBrep", "parts": parts}
    with open(os.path.join(out_dir, "parts-manifest.json"), "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, ensure_ascii=False, indent=1)
    print("RESULT " + json.dumps({"ok": not problems, "dir": os.path.relpath(out_dir, REPO), "parts": len(parts),
                                  "problems": problems, "sec": round(time.time() - t0, 1)}, ensure_ascii=False))


try:
    main()
except Exception:
    print("RESULT " + json.dumps({"ok": False, "error": traceback.format_exc()[-800:]}))
sys.stdout.flush()
