# Parodius Da! (PC Engine) — Hack Toolchain

Reverse-engineering toolchain and buildable hacks for **Parodius Da! -
Shinwa kara Owarai he (J)** (HuCard, 1MB). By Turboxray.

**No ROMs or extracted game assets are included.** Supply your own clean,
headerless dump as `Parodius_Da__original.pce` (1,048,576 bytes) in the
repo root; everything is built or extracted from it.

## The hacks

| build | what you get |
|---|---|
| `go.bat` / `build_all.bat` | The **colour hack + taller playfield** (v1.0): restores pixel detail hidden by duplicate palette entries, and offers four window heights (stock ~197 / 208 / 216 / full 224 lines). `make_patches.bat [ver]` produces distributable IPS/xdelta patches + zip. |
| `build_sf2.bat` | The **SF2-mapper expansion** (2.5MB): every graphics stream in the game stored uncompressed in expansion banks and served by a load hook instead of Konami's slow decompressor — **eliminates the game's chronic dropped frames** (stock: 1 frame in 9 lost to re-decompressing the water; this build: measured 0 lag frames / 60.0 eff in gameplay). Requires an SF2-mapper-capable emulator (Mesen2) or flash cart. |

## Requirements

- `pceas` (from [HuC](https://github.com/pce-devel/huc)) at `c:\huc\bin`
  (or edit the bats)
- Python 3 (+ [Pillow](https://pypi.org/project/pillow/) for the PNG tools)
- [Mesen2](https://mesen.ca) for the Lua capture/analysis scripts

## How the SF2 build works

The game's graphics live as compressed streams (62% of the ROM — format
fully documented in `gfx-compression.md`). The build pipeline:

1. `census_to_streams.py` + the tracked capture logs (`parodius_gfxtrace.txt`,
   `parodius_census.txt`) enumerate every stream the game ever loads —
   including per-character, per-state, and flipped variants.
2. `pce_gfx_export.py` decompresses them all from **your** ROM into
   `gfx_bins/` (untracked) and generates the asset banks + lookup tables.
3. `Parodius_SF2.asm` assembles the 2.5MB image: base hack + assets + a
   hook that diverts the game's decompress events (`[bank][src][p1]`
   match) to fast copies from the expansion.
4. `zero_upper.py` blanks the now-dead original graphics region.

New content coverage is self-extending: play with `parodius_census.lua`
loaded in Mesen2 and any stream the hook misses is logged and folded in
on the next build.

## Analysis tools

| tool | purpose |
|---|---|
| `pce_gfx_decode.py` | decode any compressed stream (bit-exact, verified vs live VRAM); `--verify` mode checks a capture log |
| `pce_gfx_rip.py` | catalog (`gfx-blocks.md`) + 4-bit greyscale PNG rips of every stream |
| `parodius_gfxtrace.lua` | log every decompress event + its VRAM output (ground truth) |
| `parodius_census.lua` | fallthrough monitor + unknown-byte watchpoints |
| `parodius_framewatch.lua` / `2` | lag-frame counter / per-call vblank profiler |
| `parodius_batwatch.lua` | BAT diff capture (tilemap reverse-engineering) |
| `palette_inc_editor.py` + fade/gen tools | the colour hack's palette pipeline |

## Documentation

`architecture.md` (engine, IRQs, banking) · `anim-engine.md` (the lag
investigation + fix) · `gfx-compression.md` (stream format + census) ·
`tilemap.md` (map format) · `sprites-and-starfield.md` · `symbols.md` ·
`palette-map.md` · `gfx-blocks.md` (stream catalog)

## Credits

Reverse engineering, hacks and tools: **Turboxray**, 2026.
