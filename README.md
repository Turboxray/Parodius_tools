# Parodius Da! (PC Engine) — Hack Build Kit

Buildable hacks for **Parodius Da! - Shinwa kara Owarai he (J)** (HuCard,
1MB). By Turboxray.

**No ROMs or extracted game assets are included.** Supply your own clean,
headerless dump as `Parodius_Da__original.pce` (1,048,576 bytes) in the
repo root; everything is built or extracted from it.

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

## Credits

Reverse engineering, hacks and tools: **Turboxray**, 2026.
