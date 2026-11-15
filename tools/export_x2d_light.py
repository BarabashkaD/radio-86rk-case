"""Rebuild the seven released X2D STL files with tools/fcq tools/export_x2d_light.py."""
import hashlib
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import traceback

import FreeCAD as App
import Mesh
import MeshPart
import Part


def sha256(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def verify_files(folder, parts):
    for part in parts:
        path = folder / part["file"]
        if sha256(path) != part["sha256"]:
            raise ValueError(f"{path.name} differs from the released STL")


def export_part(document, part, recipe, brep, folder):
    obj = document.getObject(part["object"])
    if obj is None:
        raise ValueError(f"Missing source object {part['object']}")
    shape = Part.getShape(obj, "", transform=True)
    if shape.isNull() or len(shape.Solids) != 1:
        raise ValueError(f"Expected one solid in {part['object']}")
    # The measured export settings were selected on a reloaded assembly-space BREP.
    shape.exportBrep(str(brep))
    body = Part.Shape()
    body.read(str(brep))
    mesh = MeshPart.meshFromShape(
        Shape=body.cleaned(), LinearDeflection=recipe["linear_mm"],
        AngularDeflection=part["angular_rad"], Relative=recipe["relative"],
    )
    path = folder / part["file"]
    mesh.write(str(path))
    reopened = Mesh.Mesh(str(path))
    if (reopened.CountFacets != part["facets"] or reopened.countComponents() != 1
            or not reopened.isSolid() or reopened.hasNonManifolds()
            or reopened.hasNonUniformOrientedFacets()):
        raise ValueError(f"{path.name} failed the released mesh checks")


def main():
    repo = Path(__file__).resolve().parents[1]
    recipe = json.loads((repo / "case/print/x2d/light-v1.json").read_text())
    source = repo / recipe["source"]
    if sha256(source) != recipe["source_sha256"]:
        raise ValueError("Accepted FCStd differs from the source pinned in light-v1.json")
    parent = repo / ".build" / "x2d-light"
    parent.mkdir(parents=True, exist_ok=True)
    output = parent / recipe["version"]
    parts = recipe["parts"]
    if not output.is_dir():
        with TemporaryDirectory(dir=parent) as tmp:
            stage = Path(tmp) / "stl"
            stage.mkdir()
            doc = App.openDocument(str(source))
            try:
                for part in parts:
                    export_part(doc, part, recipe, Path(tmp) / "part.brep", stage)
            finally:
                App.closeDocument(doc.Name)
            verify_files(stage, parts)
            try:
                stage.rename(output)
            except OSError:
                if not output.is_dir():
                    raise
                # A concurrent exporter may already have installed the same bundle.
    verify_files(output, parts)
    return {"ok": True, "version": recipe["version"], "parts": len(parts),
            "dir": output.relative_to(repo).as_posix()}


try:
    print("RESULT " + json.dumps(main()), flush=True)
except Exception:
    print("RESULT " + json.dumps({"ok": False, "error": traceback.format_exc()}), flush=True)
    sys.exit(1)
