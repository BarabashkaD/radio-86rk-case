"""Block personal data in files that go into this public repository.

Finds absolute home paths (/Users/<name>, /home/<name>, C:\\Users\\<name>) and e-mail addresses
(GitHub noreply addresses are allowed) in text files and inside zip-based files (FCStd, 3mf, zip):
FCStd keeps its object properties in Document.xml inside the archive, so a plain text scan misses them.

Run:  python3 -I tools/check_private.py --staged     (what the pre-commit hook does)
      python3 -I tools/check_private.py FILE ...
Prints findings as `file[:member]:line: what` and exits 1 when there are any, else 0.
Fix: write paths relative to the repository root or as `<архив>/…`, never absolute home paths.
"""
import re
import subprocess
import sys
import zipfile

PATTERNS = [
    (re.compile(r"/Users/[A-Za-z0-9._-]+"), "home path"),
    (re.compile(r"/home/[A-Za-z0-9._-]+"), "home path"),
    (re.compile(r"[A-Za-z]:\\\\?Users\\\\?[A-Za-z0-9._-]+", re.IGNORECASE), "windows home path"),
    (re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}"), "e-mail"),
]
ALLOWED_EMAIL = (re.compile(r"@users\.noreply\.github\.com$"), re.compile(r"^noreply@anthropic\.com$"))
ZIP_EXT = (".fcstd", ".3mf", ".zip")
SKIP_EXT = (".brep", ".brp", ".step", ".stp", ".stl", ".png", ".jpg", ".jpeg", ".pdf")
TEXT_MEMBER = re.compile(r"(\.xml|\.txt|\.json|\.md|\.py|\.cfg|\.config|\.rels)$|^[^.]*$", re.IGNORECASE)


def scan_text(text, where, out):
    for n, line in enumerate(text.splitlines(), 1):
        for rx, what in PATTERNS:
            for m in rx.finditer(line):
                hit = m.group(0)
                if what == "e-mail" and any(a.search(hit) for a in ALLOWED_EMAIL):
                    continue
                out.append("%s:%d: %s %s" % (where, n, what, hit[:60]))


def scan_file(path, out):
    low = path.lower()
    if low.endswith(SKIP_EXT):
        return
    if low.endswith(ZIP_EXT):
        try:
            with zipfile.ZipFile(path) as z:
                for name in z.namelist():
                    if TEXT_MEMBER.search(name):
                        scan_text(z.read(name).decode("utf-8", "replace"), "%s:%s" % (path, name), out)
        except zipfile.BadZipFile:
            out.append("%s: not a valid zip" % path)
        return
    try:
        with open(path, "rb") as fh:
            data = fh.read()
    except OSError:
        return
    if b"\0" in data[:4096]:
        return  # binary
    scan_text(data.decode("utf-8", "replace"), path, out)


def staged_files():
    res = subprocess.run(["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR", "-z"],
                         capture_output=True, check=True)
    return [p for p in res.stdout.decode("utf-8").split("\0") if p]


def main(argv):
    files = staged_files() if argv[1:2] == ["--staged"] else argv[1:]
    out = []
    for f in files:
        scan_file(f, out)
    for line in out:
        print(line)
    if out:
        print("check_private: %d finding(s). Use paths relative to the repository root or `<архив>/…`." % len(out),
              file=sys.stderr)
    return 1 if out else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
