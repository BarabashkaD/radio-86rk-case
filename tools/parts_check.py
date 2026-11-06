"""Check that exported case parts in .build/parts/ match the current accepted FCStd (no FreeCAD needed).

Run:  $CAD_PY -I tools/parts_check.py            (CAD_PY from tools/local.env)
Env (optional): SRC — FCStd to check against (default: the file named in case/CURRENT.path)

Prints one line RESULT {json} and exits 0 when the parts are fresh, 1 when they are stale or missing
(then run: tools/fcq tools/extract_parts.py). Fresh means: a manifest exists for the SHA-256 of the
source FCStd, and every exported file still has the SHA-256 recorded in that manifest.
A check that uses stale or unchecked parts is NOT RUN, never PASS.
"""
import hashlib
import json
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def main():
    src = os.environ.get("SRC")
    if not src:
        with open(os.path.join(REPO, "case", "CURRENT.path"), encoding="utf-8") as fh:
            src = os.path.join(REPO, "case", fh.read().strip())
    src_sha = sha256(src)
    out_dir = os.path.join(REPO, ".build", "parts", src_sha[:12])
    manifest_path = os.path.join(out_dir, "parts-manifest.json")
    res = {"source": os.path.relpath(os.path.abspath(src), REPO), "source_sha256": src_sha,
           "dir": os.path.relpath(out_dir, REPO)}
    if not os.path.isfile(manifest_path):
        res.update(status="missing", reason="no manifest for this source SHA")
        return res
    with open(manifest_path, encoding="utf-8") as fh:
        manifest = json.load(fh)
    if manifest.get("source_sha256") != src_sha:
        res.update(status="stale", reason="manifest source SHA differs")
        return res
    bad = []
    files = [(p["file"], p["file_sha256"]) for p in manifest["parts"]]
    files += [(p["stl"]["file"], p["stl"]["file_sha256"]) for p in manifest["parts"] if "stl" in p]
    for name, want in files:
        path = os.path.join(out_dir, name)
        if not os.path.isfile(path):
            bad.append(name + ": missing")
        elif sha256(path) != want:
            bad.append(name + ": SHA differs")
    res.update(status="stale" if bad else "fresh", files=len(files), problems=bad)
    return res


if __name__ == "__main__":
    result = main()
    print("RESULT " + json.dumps(result, ensure_ascii=False))
    sys.stdout.flush()
    sys.exit(0 if result["status"] == "fresh" else 1)
