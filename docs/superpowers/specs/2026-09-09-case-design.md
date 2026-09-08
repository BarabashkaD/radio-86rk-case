# Radio-86RK case — design spec

Date: 2026-09-09. Status: approved in brainstorming, awaiting implementation plan.

A 3D-printable enclosure for the assembled Radio-86RK, generated entirely by
scripts from the board and the key envelope this repository already tracks.
The user does not work in the FreeCAD GUI; every step runs under
`freecadcmd` or through the FreeCAD MCP bridge.

## 1. Goals and non-goals

Goals, in the order they were set:

1. **Printer-agnostic.** No bed size is assumed. Parts are modelled whole and
   cut into tiles by a `max_tile` parameter, so one model serves a 180 mm bed
   and a 300 mm bed.
2. **Modular.** Any upgrade to the machine should mean reprinting the smallest
   part that changed, never the whole case. Each part locates to the board,
   not to its neighbours, and is fastened independently.
3. **Accurate where it counts.** The rear plate carries every port cutout and
   prints flat, face down.
4. **Swappable keyboard frame.** The plate around the keys is its own part,
   designed against `model/envelope.step`, replaced when the cap profile
   changes.
5. **Access to the expansion header J6** from above and behind through a
   hinged lid, without opening the case.
6. **Look.** Not minimal. Reference is the Yamaha MSX2 (CX/YIS series):
   two-tier body, keyboard sunk in a well behind a raised front rim, sharp
   step to a taller rear, ribbed vent grilles, chamfers rather than radii,
   dark body with light caps. A wedge, with additional tilt feet.
7. **Everything parameterised**, one number per detail, in one file.

Non-goals: injection-moulding geometry, a transparent window, a badge, a
power switch (the board has none), fitting a specific cap set (the envelope
already covers DSA and sculpted profiles), and anything requiring a GUI
edit.

## 2. Decisions made, and why

| Decision | Choice | Rejected | Why |
|---|---|---|---|
| Structure | PCB is the chassis and datum | printed skeleton | The board is the only rigid one-piece object spanning the footprint, has seven M3 holes, and its geometry is owned upstream |
| Fastening | M3 screws into heat-set inserts, board screwed to tray bosses from above | clips | Tolerant of unknown printers; any part comes off with a screwdriver |
| Silhouette | Two-tier wedge; tilt in the tray underside; extra tilt from feet | flat slab, breadbin | Keys must stay parallel to the board, so the wedge angle lives in the tray, and every top plate stays flat |
| Rear step | Raised rear tier, inclined step face | continuous deck | Reference look; gives the rear plate height and the J6 lid a rear face |
| J6 lid | L-shaped flap hinged along the bottom of its rear face, ball-and-socket snap hinge | filament-pin hinge, lift-off | Simpler; hangs open or unhooks entirely, which removes the hanging-shelf drawback of a captive hinge |
| Hinge fit | Sockets in the rear plate, studs on the lid, stud diameter a parameter | tuning the printer | The fit is tuned by reprinting the smallest part |
| Tiling | Model whole, cut by `max_tile` after | modelling tiles | The gate checks one geometry; a printer change is a number |
| Authoring | Generated in code from `case.tsv` + board + envelope | hand-modelled `.FCStd`, hybrid | Matches the repo; tiling presets are free; the user cannot edit geometry by hand |

## 3. The board, as the case sees it

All positions in the **KiCad frame**: origin top-left, X right, Y down, rear
edge at Y 6.35, front (keyboard) edge at Y 209.55. `model/envelope.step` is
the same geometry with Y negated; `tools/case/board.py` converts once.

| Item | Value |
|---|---|
| Outline | 266.7 × 203.2 mm, X 6.35 to 273.05, Y 6.35 to 209.55, corner radius 2.54 |
| Holes, M3 | (11.43, 11.43) (267.97, 11.43) (11.43, 91.44) (267.97, 91.44) (139.7, 110.49) (62.23, 204.47) (207.01, 204.47) |
| Key field | X 6.675 to 272.725, Y 95.575 to 209.225; cap base Z 10.743, envelope ceiling Z 22.743 |
| Rear-edge externals, by X | SW68 reset 21.59 · J2 barrel jack 36.83 · U25 TO-220 regulator 50.8 · J4 DIN-8 102.87 · J6 26-pin header 148.59 (pins up, body ≈ 38 × 9 mm) · J5 DE-9 196.85 · J1 RCA 234.95 · SP1 speaker 257.81 |
| Internal only | J3 power header (77.47, 19.685), U26 DC-DC (77.47, 10.16), J7 20-pin extension (91.44, 60.96), JP1/JP2 |
| EPROMs | U10 monitor (78.74, 68.58), U11 font (238.76, 68.58), DIP-28 600 mil, long axis along Y |
| LEDs | D10 POWER (206.375, 104.775), D11 RUS/LAT (225.425, 104.775), on the F-row line between F5 and HM |
| Tallest non-key part | J4 DIN-8 at 21.47 mm; nothing on the board exceeds 22 mm |

Note the key field runs to within 0.3 mm of the left and right board edges,
so the keyboard well is bounded at the sides by the tray wall itself.

These numbers are **not** copied into `case.tsv`. The build reads them from
the pinned board checkout and the assembly model every run.

## 4. Parts

Every part is one solid returned by one function. Heights are above the
board's top face unless stated. *param* marks a `case.tsv` row; the default
is shown.

### 4.1 Overall body

- Two tiers. Front tier top (the rim around the well) at 18 mm *(param
  `rim_z`)*. Rear tier top at 45 mm *(param `deck_z`)*. Step face inclined
  60° from horizontal *(param `step_angle`)*, foot of the step at Y 92, just
  behind the F-row envelope edge at 95.6.
- Wall 2.4 mm *(param `wall`)*, plates 3.0 mm *(param `plate`)*, board edge
  to wall inner face 1.5 mm *(param `board_gap`)*. Outer footprint about
  274.5 × 211 mm before the front rim.
- Outer vertical and horizontal edges chamfered 3 mm *(param `chamfer`)*.
- The board is inclined 6° *(param `wedge_angle`)*, thin end at the front,
  so the ports point slightly upward at the rear as on period machines.
- Resulting outside height, approximately: 27 mm at the front rim, 79 mm at
  the rear. `deck_z` is the lever if the rear reads too heavy.

### 4.2 Tray

- One solid: floor 2.4 mm, wall following the board outline at `board_gap`,
  two-tier side walls, step wall, open rear, wedge underside.
- Seven bosses under the board holes: Ø7 *(param `boss_d`)*, Ø4.0 insert hole
  *(param `insert_d`)*, 5 mm tall *(param `standoff`)*. Board screwed down
  from above, M3 × 8.
- Underside is a plane at `wedge_angle` to the board. Four Ø10 × 1 mm recesses
  for rubber pads *(param `pad_d`)*. Two dovetail slots at the rear for feet.
- Wall tops carry Ø4.0 insert holes for the deck and frame screws. Front-tier
  side walls are 3.6 mm thick from Z 9 up, leaving a 1.2 mm ledge for the
  keyboard frame.
- A groove in the floor at the rear seats the rear plate; the side walls end
  in faces with insert holes the rear plate screws into.
- Tiling cuts run front-to-back, are placed to miss every boss and insert
  hole, and each cut receives two Ø3 alignment pins *(param `pin_d`)* in
  blind sockets plus one M3 strap on the inside.

### 4.3 Keyboard frame

- 3 mm plate, Z 9 to 12, spanning wall inner face to inner face, resting on
  the side ledges, a ledge on the front rim and the step wall. Four
  countersunk M3 screws at the corners into wall-top inserts.
- Opening: union of the 67 envelope footprints, offset outward 1.0 mm
  *(param `key_offset`)*, in `outline` mode (follows the blocks and their
  gaps). `hull` mode gives one rectangle *(param `opening_mode`)*.
- DSA caps stand 7 mm above the frame; sculpted caps about 11 mm. Both are
  inside the 22.74 mm envelope ceiling.
- Two Ø3.4 holes at D10 and D11. `light_pipe` mode makes them Ø4 counterbores
  for 3 mm light pipes *(param `led_mode`)*.
- Tiled if wider than `max_tile`; the cut is placed in a gap between key
  blocks so it never crosses an opening edge.

### 4.4 Rear-tier deck

- 3 mm plate, Z 45 to 48, wall inner face to inner face, from the step to
  the rear plate, notched around the J6 lid, screwed into wall-top inserts.
- Vent grille: slots 2 mm wide × 40 mm long at 5 mm pitch *(params
  `vent_w`, `vent_l`, `vent_pitch`)*, running front-to-back, in two regions
  *(param `vent_regions`)*: over U25/U26 at the left, over SP1 at the right.
- Optional EPROM hatches over U10 and U11, about 20 × 45 mm each, modelled
  as outlines and cut only when `eprom_hatches` is on. Off by default; see §9.

### 4.5 Rear plate

- 3 mm, full outer width, from the tray floor groove to Z 48, screwed into
  the side-wall end faces and the deck. Prints face down.
- Cutouts are the connector bodies' silhouettes from the assembly model,
  projected onto the plate, offset by 0.5 mm *(param `port_margin`)*: J2
  barrel jack, J4 DIN-8, J5 DE-9 with its two jack-screw holes, J1 RCA, and a
  Ø6 access hole in front of SW68 *(param `reset_d`)*.
- J6 window: 65 × 21 mm *(params `lid_w`, derived from `hinge_z`)*, from
  the hinge line at Z 24 *(param `hinge_z`, must exceed the tallest flanking
  port)* to the deck, centred on J6. The plate's top edge is straight across
  its full width, which is what keeps it accurate.
- Two spherical sockets in the window's side edges, on the hinge axis, each
  opened upward through a keyhole throat 0.4 mm narrower than the stud
  *(param `throat_undersize`)*.
- Optional 0.6 mm label recesses above each port for paint fill *(param
  `labels`, off)*.
- Tiled only if `max_tile` is below its width, and then with a single cut at
  the J6 window where the lid already interrupts it.

### 4.6 J6 lid

- L-shaped, 3 mm: rear face 65 × 21 mm, top face 65 × 25 mm *(param
  `lid_depth`)*. Closed, the rear face is flush with the rear plate and the
  top face rests on a lip of the deck.
- On each side edge, on the hinge axis: a Ø6 half-round bearing that takes
  the load and a Ø5 spherical stud *(param `stud_d`)* on a Ø3 neck that only
  retains. Interference 0.3 mm *(param `stud_interference`)*.
- Pressed down into the keyhole sockets to fit; swings back and down to hang
  on the rear plate; lifts off entirely when unhooked.
- 34 × 3 mm notch in the bottom edge of the rear face for a 26-way ribbon
  with the lid closed *(param `lid_notch`)*.
- The lid is the first part to print on any new printer: it proves the
  stud fit, and `stud_d` is adjusted by ±0.2 mm and reprinted rather than
  touching the printer.

### 4.7 Side bay

- 60 × 20 mm opening *(params `bay_w`, `bay_h`)* in the left rear-tier wall,
  Z 20 to 40, with a blank cover screwed from inside and four M3 insert
  bosses on the wall's inner face for a future module bracket.
- `bay_side` is left, right or none *(param)*. Left by default, as on the
  reference machine.

### 4.8 Feet

- Two rear feet, 10 and 20 mm *(param `foot_heights`)*, adding about 3° and
  5° of tilt, sliding into the tray's dovetail slots. Print flat.

## 5. Parameters — `case.tsv`

Same shape as `params.tsv`: `key`, `value`, and a `drives` column naming the
part and feature. Groups and defaults:

| Group | Keys |
|---|---|
| shell | wall 2.4 · plate 3.0 · board_gap 1.5 · chamfer 3 |
| tiers | rim_z 18 · deck_z 45 · step_angle 60 |
| wedge | wedge_angle 6 · pad_d 10 |
| keyboard frame | key_offset 1.0 · opening_mode outline · led_mode hole |
| rear plate | port_margin 0.5 · reset_d 6 · hinge_z 24 · lid_w 65 · labels 0 · throat_undersize 0.4 |
| lid | lid_depth 25 · stud_d 5.0 · stud_interference 0.3 · lid_notch 1 |
| vents | vent_w 2 · vent_l 40 · vent_pitch 5 · vent_regions left,right |
| bay | bay_side left · bay_w 60 · bay_h 20 |
| fasteners | insert_d 4.0 · boss_d 7 · standoff 5 · screw M3 |
| tiling | max_tile 256 · tile_gap 0.2 · pin_d 3 · preset standard |
| options | eprom_hatches 0 |

`preset` is a convenience row: mini sets `max_tile` 180, standard 256, large
300. An explicit `max_tile` wins.

## 6. Tooling

```
tools/build_case.py          entry: [part ...] [preset]; positional, sys.argv[2:]
tools/case/params.py         loads case.tsv, validates types, ranges, drives column
tools/case/board.py          outline, holes, connector silhouettes, key field; frame conversion
tools/case/tray.py           tray(params, board) -> solid
tools/case/keyboard_frame.py
tools/case/deck.py
tools/case/rear_plate.py
tools/case/lid.py
tools/case/bay.py
tools/case/feet.py
tools/case/tiling.py         split(solid, max_tile, keep_out) -> tiles with pins and straps
tools/case/export.py         STEP + STL per part, manifest, assembly document
```

- Each part module exposes one pure function from parameters and board data
  to a `Part.Solid`. No file access inside part modules.
- `build_case.py` follows the repo's five traps: `_is_entry_script()` on
  `sys.argv[1]`, guarded imports and `main()`, `sys.stdout.flush()` before
  every exit, `optimalBoundingBox()` for all extents, flags never used.
- Inputs: `RADIO86RK_BOARD` checkout (pinned revision enforced by the gate),
  `model/radio86rk-assembly.FCStd` for connector bodies, `model/envelope.step`
  for the key field, `case.tsv` and `params.tsv`.
- GUI-only steps run through the MCP bridge as today: `tools/render.py`
  gains `case-front-iso`, `case-rear-iso` and `case-lid-open` views of the
  assembly, closing the document explicitly.

## 7. Outputs

| Path | Tracked | Content |
|---|---|---|
| `model/case/<part>.step` | yes | untiled solids, board frame, one per part |
| `model/case/manifest.tsv` | yes | per part: bounding box, tile count per preset, hash of `case.tsv` + board revision |
| `model/radio86rk-case.FCStd` | yes | the case around the board model, for renders |
| `model/renders/case-*.png` | yes | visual sign-off, 1600 × 1100 |
| `.build/case/<preset>/<part>-<n>.stl` | no | tiles per preset, regenerated |
| `.build/case/<part>.stl` | no | untiled meshes |

Outputs are written only after every requested part has built; a failure
leaves the previous outputs untouched and exits 2.

## 8. The gate

New checks appended to `tools/verify.py`, lettered on from the current
eleven, each exit-coded and `verdict:`-printing as today. Each check must be
demonstrated failing on an injected fault before it is believed; the fault
is recorded beside the check.

| Check | Passes when | Injected fault |
|---|---|---|
| Envelope clearance | no case solid intersects `envelope.step`; the frame opening contains every prism with ≥ `key_offset` | shift `key_offset` to −0.5 |
| Component clearance | no case solid within 1.0 mm of any assembly component, using real solids | set `deck_z` to 20 |
| Port alignment | every external connector silhouette lies inside its cutout with `port_margin`; no cutout without a connector | offset one connector 2 mm in `board.py` |
| Hole alignment | seven bosses concentric with the board holes within 0.1 mm | swap two hole coordinates |
| Tile size | every tile in a preset fits `max_tile` × `max_tile` × 60 mm by `optimalBoundingBox()` | set `max_tile` to 100 without re-tiling |
| Manifest currency | manifest hash equals hash of current `case.tsv` + board revision | edit one `case.tsv` value after building |
| Printability | inward offset of every part by 2 × nozzle width (0.8 mm) does not vanish | set `plate` to 1.2 |
| Hinge geometry | sockets and studs coaxial, `hinge_z` above the tallest flanking port | set `hinge_z` to 15 |

## 9. Optional ideas, registered

Not in the base design. Positions are reserved so a later part can add them
without moving anything.

- **EPROM hatches** over U10 (monitor) and U11 (font) in the rear-tier
  deck. Worthwhile only with ZIF sockets or tool-less carriers.
- **Port labels** as paint-fill recesses on the rear plate.
- **Middle hinge support** for the J6 lid: a rib under the hinge line with a
  half-socket, if a 65 mm lid ever twists.
- **Cartridge-style expansion** through the J6 window: a vertical board with
  a card guide inside the window.
- **Floor vents** under the regulator area.

## 10. Verification plan

Three routes with no shared failure mode:

1. **The gate** on geometry, every build.
2. **Renders** through the MCP bridge, compared against the reference look
   and the previous render.
3. **A physical print** of the smallest parts first: the lid, one foot, then
   the rear plate. The lid proves the stud fit; the rear plate proves the
   port cutouts against the real board. Large parts print only after both
   pass.

Numbers the first build will revisit, in order: `deck_z` (rear proportion),
`wedge_angle`, `key_offset` against real caps, `stud_interference` against
the user's printer.

## 11. Open questions

None blocking. The board revision is pinned at `4f4c1b5`; if it moves, the
existing pinning check fails first and this design re-derives every
board-driven number on the next build.
