#!/usr/bin/env python3
"""Block personal data in files that go into a public repository.

Finds absolute home paths (macOS, Linux and Windows home directories) and e-mail addresses (GitHub
noreply addresses and noreply@anthropic.com are allowed) in:
  - text files;
  - text members of zip-based files (FreeCAD FCStd, 3mf, zip, Office and OpenDocument files, epub),
    and PNG/JPEG members inside them: FCStd keeps object properties in Document.xml, docx keeps the
    author and template path in docProps/*.xml, so a plain text scan of the archive misses them;
  - image metadata (PNG tEXt/zTXt/iTXt/eXIf chunks, JPEG APPn/COM segments): FreeCAD's saveImage, for
    one, writes the absolute output path into the PNG `Title` text chunk.
An image that cannot be parsed, or a .png/.jpg that is not one, is a finding. STEP, BRep, STL and PDF
files are skipped; other binary files (a NUL byte in the first 4 KiB) are skipped.

Run:  python3 -I check_private.py --staged          (what the pre-commit hook does)
      python3 -I check_private.py FILE ...
--staged scans the staged blobs, i.e. what the commit will contain, not the working tree files.
--hint TEXT, or env CHECK_PRIVATE_HINT, replaces the fix hint printed with the findings.
Prints findings as `file[:member]:line: what` and exits 1 when there are any, else 0; 2 on a usage
error or when `git` fails in --staged mode. Standard library only, Python 3.8+.
Patterns are assembled by concatenation so this file does not match itself.
"""
import argparse
import io
import os
import re
import struct
import subprocess
import sys
import zipfile
import zlib

NAME = r"[A-Za-z0-9._-]+"
PATTERNS = [
    (re.compile("/" + "Users/" + NAME), "home path"),
    (re.compile("/" + "home/" + NAME), "home path"),
    (re.compile(r"[A-Za-z]:(?:\\\\?|/)" + "Users" + r"(?:\\\\?|/)" + NAME, re.IGNORECASE),
     "windows home path"),
    (re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}"), "e-mail"),
]
ALLOWED_EMAIL = (re.compile(r"@users\.noreply\.github\.com$", re.IGNORECASE),
                 re.compile("^" + re.escape("noreply@" + "anthropic.com") + "$", re.IGNORECASE))
ZIP_EXT = (".fcstd", ".3mf", ".zip", ".docx", ".xlsx", ".pptx", ".odt", ".ods", ".odp", ".epub")
IMAGE_EXT = (".png", ".jpg", ".jpeg")
SKIP_EXT = (".brep", ".brp", ".step", ".stp", ".stl", ".pdf")
TEXT_MEMBER = re.compile(r"\.(xml|txt|json|md|py|cfg|config|rels|svg|html?|xhtml|opf|ncx|csv|ya?ml|ini|mf|model|gcode)$"
                         r"|^[^.]*$", re.IGNORECASE)
DEFAULT_HINT = "Use paths relative to the repository root; remove e-mail addresses."


def scan_text(text, where, out):
    for n, line in enumerate(text.splitlines(), 1):
        for rx, what in PATTERNS:
            for m in rx.finditer(line):
                hit = m.group(0)
                if what == "e-mail" and any(a.search(hit) for a in ALLOWED_EMAIL):
                    continue
                out.append("%s:%d: %s %s" % (where, n, what, hit[:60]))


def png_text(data):
    """Yield (key, text) of every tEXt, zTXt, iTXt and eXIf chunk."""
    i = 8
    while i + 8 <= len(data):
        n, kind = struct.unpack(">I4s", data[i:i + 8])
        body = data[i + 8:i + 8 + n]
        if len(body) < n:
            raise ValueError("truncated %s chunk" % kind.decode("latin-1"))
        i += 12 + n
        if kind == b"eXIf":
            yield "eXIf", body.decode("latin-1")
            continue
        if kind not in (b"tEXt", b"zTXt", b"iTXt"):
            continue
        key, _, rest = body.partition(b"\0")
        if kind == b"zTXt":
            rest = zlib.decompress(rest[1:])
        elif kind == b"iTXt":
            compressed, rest = rest[0], rest[2:]
            rest = rest.split(b"\0", 2)[-1]          # skip language tag and translated key
            if compressed:
                rest = zlib.decompress(rest)
        yield key.decode("latin-1"), rest.decode("utf-8", "replace")


def jpeg_text(data):
    """Yield (segment, text) of every APPn and COM segment before the image data."""
    i = 2
    while i + 4 <= len(data) and data[i] == 0xFF:
        marker = data[i + 1]
        if marker == 0xFF:                             # fill byte
            i += 1
            continue
        if marker == 0xDA:                             # start of scan: metadata is over
            return
        n, = struct.unpack(">H", data[i + 2:i + 4])
        if 0xE0 <= marker <= 0xEF or marker == 0xFE:
            yield "%02X" % marker, data[i + 4:i + 2 + n].decode("utf-8", "replace")
        i += 2 + n
    raise ValueError("no start of scan")


def scan_image_bytes(data, where, out):
    try:
        if data[:8] == b"\x89PNG\r\n\x1a\n":
            parts = png_text(data)
        elif data[:2] == b"\xff\xd8":
            parts = jpeg_text(data)
        else:
            out.append("%s: not a PNG or JPEG" % where)
            return
        for key, text in parts:
            scan_text(text, "%s:%s" % (where, key), out)
    except (ValueError, IndexError, struct.error, zlib.error) as e:
        out.append("%s: unreadable image metadata (%s)" % (where, e))


def scan_zip(data, where, out):
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            for name in z.namelist():
                member = "%s:%s" % (where, name)
                if name.lower().endswith(IMAGE_EXT):
                    scan_image_bytes(z.read(name), member, out)
                elif TEXT_MEMBER.search(name.rsplit("/", 1)[-1]):
                    scan_text(z.read(name).decode("utf-8", "replace"), member, out)
    except (zipfile.BadZipFile, zlib.error, OSError, NotImplementedError, RuntimeError) as e:
        out.append("%s: not a readable zip (%s)" % (where, e))


def scan_bytes(name, data, out):
    """Scan the content `data` of the file `name`; the name picks the scanner."""
    low = name.lower()
    if low.endswith(SKIP_EXT):
        return
    if low.endswith(ZIP_EXT):
        scan_zip(data, name, out)
    elif low.endswith(IMAGE_EXT):
        scan_image_bytes(data, name, out)
    elif b"\0" not in data[:4096]:              # other binary files are skipped
        scan_text(data.decode("utf-8", "replace"), name, out)


def scan_file(path, out):
    try:
        with open(path, "rb") as fh:
            data = fh.read()
    except OSError as e:
        out.append("%s: unreadable (%s)" % (path, e))
        return
    scan_bytes(path, data, out)


def git(*args):
    return subprocess.run(["git"] + list(args), capture_output=True, check=True).stdout


def staged_blobs():
    """(path, blob id) of every added, copied, modified or renamed entry in the index.

    The blob is what the commit will contain, which may differ from the working tree file.
    Submodule entries (mode 160000) have no blob and are skipped; a symlink's blob is its target.
    """
    raw = git("diff", "--cached", "--raw", "-z", "--no-abbrev", "--diff-filter=ACMR").decode("utf-8", "surrogateescape")
    fields = raw.split("\0")
    out, i = [], 0
    while i < len(fields) and fields[i].startswith(":"):
        meta = fields[i][1:].split()
        status = meta[4]
        path = fields[i + 2] if status[0] in "RC" else fields[i + 1]
        i += 3 if status[0] in "RC" else 2
        if meta[1] != "160000":
            out.append((path, meta[3]))
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description="Block home paths and e-mail addresses in files.")
    ap.add_argument("--staged", action="store_true", help="scan the files staged for commit")
    ap.add_argument("--hint", help="fix hint printed with the findings (default: env CHECK_PRIVATE_HINT)")
    ap.add_argument("files", nargs="*")
    args = ap.parse_args(argv)
    hint = args.hint or os.environ.get("CHECK_PRIVATE_HINT") or DEFAULT_HINT
    out = []
    if args.staged:
        if args.files:
            ap.error("give either --staged or files, not both")
        try:
            for path, blob in staged_blobs():
                scan_bytes(path, git("cat-file", "blob", blob), out)
        except (OSError, subprocess.CalledProcessError, IndexError) as e:
            print("check_private: git failed (%s)" % e, file=sys.stderr)
            return 2
    for f in args.files:
        scan_file(f, out)
    for line in out:
        print(line)
    if out:
        print("check_private: %d finding(s). %s" % (len(out), hint), file=sys.stderr)
    sys.stdout.flush()
    return 1 if out else 0


if __name__ == "__main__":
    sys.exit(main())
