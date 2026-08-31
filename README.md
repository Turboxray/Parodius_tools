# Parodius Da! (PC Engine) — Hack Build Kit

Buildable hacks for **Parodius Da! - Shinwa kara Owarai he (J)** (HuCard,
1MB). By Turboxray.

**No ROMs or extracted game assets are included.** Supply your own clean
dump as `Parodius_Da__original.pce` (1,048,576 bytes) in the repo root;
everything is built or extracted from it. A headered dump (+512 bytes) is
detected and stripped automatically at the start of the build; any other
size aborts with an error.

## The hacks

`build_all.bat` builds **everything** — both hacks, each in all four
window-height variants (stock ~197 / 208 / 216 / full 224 lines):

| ROMs | what you get |
|---|---|
| `Parodius_patch_*.pce` (1MB) | The **colour hack + taller playfield** (v1.0): restores pixel detail hidden by duplicate palette entries. |
| `Parodius_SF2_*.pce` (2.5MB) | The **SF2-mapper expansion**: every graphics stream in the game stored uncompressed in expansion banks and served by a load hook instead of Konami's slow decompressor — **eliminates the game's chronic dropped frames** (stock: 1 frame in 9 lost to re-decompressing the water; this build: measured 0 lag frames / 60.0 eff in gameplay). Requires an SF2-mapper-capable emulator (Mesen2) or flash cart. |

(`go.bat` = quick single build of the full-height patch ROM.)

## Requirements

- `pceas` (from [HuC](https://github.com/pce-devel/huc)) at `c:\huc\bin`
  (or edit the bats)
- Python 3

## How the SF2 build works

The game stores its graphics as compressed streams (62% of the ROM). The
SF2 side of `build_all.bat`:

1. `compressed_gfx_table.txt` is the definitive map of every compressed stream
   in the game — 603 variants (bank, src, flip, offsets, sizes,
   destination), assembled from full-coverage reverse engineering: full
   playthroughs of all four characters, every state (shield damage
   levels, death frames, pose extremes...), plus the game's own sequence
   tables for content no playthrough triggers.
2. `pce_sf2_mapper_prep.py extract` (a bit-exact reimplementation of the game's
   decompressor, verified against live VRAM captures) extracts them all
   from **your** ROM into `gfx_bins/` and generates the expansion asset
   banks + lookup tables.
3. `Parodius_SF2.asm` assembles the 2.5MB image: base hack + assets + a
   hook that diverts the game's decompress events (`[bank][src][p1]`
   match) to fast copies from the expansion.
4. `pce_sf2_mapper_prep.py zero` blanks the now-dead original graphics region.

## Palette editor

`palette_editor.py` (Tkinter, needs
[Pillow](https://pypi.org/project/pillow/) for the VCE-colour view) is the
tool the colour hack was made with: two side-by-side palette panels, browse
any of the game's colour blocks by bank:addr (sortable by level/usage),
edit colours with RGB sliders (3-bit VCE), copy colours between panels
(positionally or with Ctrl+C/Ctrl+V). Each panel has its own **Source**
selector — panel B can share A's file or load its own — from the working
`palette.inc`, from `palette_org.inc` (the original colours), or any
other .inc. **Saving always writes `palette.inc`**, the file the build
consumes; a panel kept on another source purely as a reference (no edits)
is left out of the save so it can't revert your work.

An **A/B diff** window compares the two panels slot by slot — split
swatches (left half A, right half B), switchable between showing only the
differences or only the matches (non-applying slots are X'd out), live as
you edit; clicking a swatch selects that slot in both panels.

`palette_org.inc` is ripped from **your** ROM by `rip_palettes.py`
(run automatically by `build_all.bat`), using `palette.inc` as the
structural map — so the true original colours are always available for
reference and for the editor's change-count tags.

## Graphics editor

`gfx_editor.py` (Tkinter) edits the extracted graphics (`gfx_bins/*.bin`,
raw VRAM words). View any bin as **8×8 tiles or 16×16 sprite cells**
(toggle — the format isn't stored in the data), click a cell to pixel-edit
it (right-click eyedrops, Ctrl+Z undo, Ctrl+S save). Saved bins feed
straight into the SF2 build.

Palettes: builtin greys (16-step, 3bpp and reverses), plus any 16-colour
subpalette imported from `palette.inc` / `palette_org.inc` (double-click a
block to import all its slices). **Each graphic block has its own
imports**, along with its own cell pins (right-click), view format and
default palette — switch to another bin and back, and the block comes up
exactly as you left it. *Unpin* / *Remove* / *Clear* likewise act only on
the current block. **Save cfg / Load cfg** persists every block's state
in one config file (`gfx_editor_config.json`, auto-loaded on start if
present) — display only, the bin's colour indices are untouched.

Every bin is **tagged with the stages that load it**: the manifest's
`stages` column (from full-playthrough traces + the game's own `$C5BA`
sequence table) shows in the info bar on open, and **Browse bins...**
lists all 603 bins with their VRAM destination and stage tags.

### Flip variants (`_f1`/`_f2`/`_f3` bins)

The original game can decompress a graphics block plain or **with every
tile mirrored in place** — the load event's flip parameter selects
horizontal (`f1`), vertical (`f2`) or both (`f3`), applied uniformly to
the whole block (there's no per-tile flip in the data; full image mirrors
are finished by the tilemap, since the PCE BAT has no flip bits). Each
flip the game actually requests is extracted as its own pre-flipped bin —
only evidenced variants exist, not blanket copies.

The editor's **Sync flips** option (on by default) keeps a family
consistent: saving any member regenerates its siblings with the exact
transform the game uses, so an edit to the plain bin lands mirrored in
the flipped ones (or vice versa). Untick it to edit a variant
independently — e.g. to make the "mirrored" copy deliberately different
art.

## Credits

Reverse engineering, hacks and tools: **Turboxray**, 2026.
