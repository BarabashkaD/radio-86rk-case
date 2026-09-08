# Vendored DSA keycap models

Five STEP solids, used **for rendering only**. Nothing the case design depends
on is derived from their outer surface: `model/envelope.step` is built from key
pitch and a measured height, not from these meshes. See "What is tracked and
why" in the top-level README.

## What the files say about themselves

Every header was written by the same tool chain on the same two days in March
2017, exported from Autodesk through ST-Developer:

| File | Original path in the header | Timestamp |
|---|---|---|
| `DSA 1u.step` | `A:/User/Documents/DSA Keycap Project/DSA 1u.step` | 2017-03-11 |
| `DSA 1.25u.step` | `A:/User/Documents/DSA Keycap Project/DAS 1.25u.step` | 2017-03-11 |
| `DSA 1.5u.step` | `A:/User/Documents/DSA Keycap Project/DSA 1.5u.step` | 2017-03-11 |
| `DSA 2.25u.step` | `A:/User/Documents/DSA Keycap Project/DSA 2.25u.step` | 2017-03-11 |
| `DSA Spacebar 6.25u.step` | `A:/User/Documents/DSA Keycap Project/DSA Spacebar 6.25u (50mm spacing).step` | 2017-03-12 |

The headers carry an empty `author` and an empty `organization`, so they name
no rights holder. "DSA Keycap Project" is a directory name on someone's A:
drive, not an attribution.

## Open question — unresolved, and the repository is public

**The upstream source and licence of these five files are not established.**
That was known before publishing and publishing went ahead anyway, as a
deliberate decision rather than an oversight. The repository's own licence
(GPL-3.0) does not extend to them; nobody here can grant rights they do not
hold.

Note that removing these files would not undo their redistribution: their
geometry is baked into `model/radio86rk-assembly.FCStd` and their measured
height sets `model/envelope.step`.

**If you are the rights holder and object, open an issue and it will be
resolved.** The pipeline reaches the vendored geometry through exactly one
column of `keycaps.tsv` (`model_file`), so substituting a set whose licence is
known is a five-line change plus re-deriving `seat_dz` — the repository is
deliberately built so that swap is cheap.

The files are byte-for-byte as received. Corrections live in `keycaps.tsv`
(`scale_x`), never in the vendored geometry.
