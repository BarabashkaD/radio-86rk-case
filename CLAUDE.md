# radio-86rk-case — working notes for agents

What this project *is*: see [README.md](README.md). This file is how to **work
in it**.

The board lives in the sibling repo `radio-86rk` and is **read-only from here**.
This repo never commits to it, and check E enforces that.

## Layout

    keycaps.tsv     one row per key size: which model file, how wide
    params.tsv      derived scalars, each with a column recording how it was measured
    model/          the tracked deliverable — the assembled project, the envelope, the references
    tools/          everything runnable
    vendor/         the keycap solids, verbatim as received

## One interpreter

Everything runs under FreeCAD's console binary. There is no `freecadcmd` on
`PATH` on macOS; the path below is the console binary, and reaching for the
system Python will not work — this repo needs FreeCAD's `Part` module.

    FC=/Applications/FreeCAD.app/Contents/Resources/bin/freecadcmd

    $FC tools/build_caps.py   # place caps, write model/envelope.step
    $FC tools/verify.py       # the gate, 11 checks
    $FC tools/measure.py seat # re-derive seat_dz after a cap profile change

Two steps need a GUI FreeCAD instance driven by the FreeCAD MCP, because
KiCadStepUp and viewport rendering both refuse to load under the console
binary. **Put this repo on `sys.path` first** — a spawned instance does not
start here, and observed working directories have included two unrelated repos:

    import sys; sys.path.insert(0, "<path to radio-86rk-case>")
    import tools.import_board as import_board
    import_board.rebuild("<path to .kicad_pcb>")   # only when the board changes
    import tools.render as render; render.render_all()

## Five traps

Each fails by *looking like success* — the script appears to run and does
nothing, or reports a result it did not earn.

- **FreeCAD swallows flags.** `$FC script.py --thing` silently produces no
  output at all. Script arguments are positional and land at `sys.argv[2:]`.
- **`__name__` is never `"__main__"` under the console binary.** The guard
  `if __name__ == "__main__":` never fires; scripts are imported as modules.
  Use `_is_entry_script()` keyed on `sys.argv[1]`.
- **An unhandled exception exits 0.** A build that died before it began will
  report success and leave the previous outputs in place, which the gate will
  then happily validate. Guard module-level imports and `main()` both.
- **stdout is discarded on `sys.exit()` unless flushed.** Always
  `sys.stdout.flush()` before exiting or the output disappears.
- **`Shape.BoundBox` over-reports a NURBS solid.** It bounds the control
  polygon, not the surface, and once inflated a keycap by 10.9 mm — enough to
  reverse which cap is tallest. Use `optimalBoundingBox()`; `obox()` wraps it.

## The gate

`tools/verify.py` exits `0` pass, `1` a real finding, `2` could not run. Exit 2
is never a verdict on the design, and the gate always prints a `verdict:` line
including when it ends `INCOMPLETE`, so it is safe to parse for.

Run one check with `$FC tools/verify.py C`, or all with no argument.

**Every check must be demonstrated failing on an injected fault** before it is
believed. A check nobody has seen fail is decoration. Two classes of defect
have shown up repeatedly in this repository's own verification code:

- **Tautologies** — a check comparing a value against something derived from
  that value. Three were found and closed. The current `seat_dz` and
  `STEM_TOP_Z` checks re-derive their numbers from geometry rather than
  trusting the recorded ones, and that is deliberate.
- **Stale inputs** — a gate reading whatever happens to be on disk. One
  reported `PASS` on artifacts from the previous day, immediately after the
  build that should have replaced them had failed.

## After any GUI FreeCAD session, run `git status`

Closing a GUI instance writes back the tracked
`model/radio86rk-assembly.FCStd` with nothing having called `save()`. Treat it
as reliable rather than intermittent: it has now been observed across several
sessions, at differing sizes — 6,289 bytes and 1,594 bytes — so match on "an
unexplained diff to that file", never on a byte count. The mechanism was never
pinned down. `.gitignore` covers the harmless `.FCBak` it drops beside the file
and does **not** cover the `.FCStd`.

Revert any `.FCStd` diff you cannot explain by a specific edit. Never reason
from "no step called save" — the observed rewrite did not either.
`tools/render.py` closes its document explicitly for this reason; do the same
in any new GUI code.

## Noise you can ignore

Every FreeCAD launch on this machine prints a `3DconnexionNavlib.framework`
`dlopen` failure. It is a missing SpaceMouse driver, it is harmless, and it
appears on successful runs too. Filter it when reading transcripts.

## macOS: `~/Documents` is protected

KiCad's third-party model tree usually lives under `~/Documents`, which macOS
withholds from any process without Full Disk Access. Every file there reports
`Operation not permitted` while `ls` still shows it at full size, so tools
report *missing models* rather than a permission problem. Nothing in the
current build path touches it — but if you restore anything that shells out to
`kicad-cli`, this is the first thing to check.

## What has been verified, and how

Four independent cold-reproduction audits have been run against this
repository: a fresh agent, an empty folder, permitted to read only `CLAUDE.md`
and `README.md`, forbidden to read any source. The fourth reached a passing
gate from a cold clone. Their reports are not in this repo; the practice is
worth repeating after any significant documentation change, because every round
found defects the author could not see.
