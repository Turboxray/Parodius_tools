# Parodius PCE — Tilemap / Metatile Format

Cracked 2026-08-24 via BAT-diff capture (`parodius_batwatch.lua`) + offline
search against the reconstructed level-1 map. ✓ = verified against the
in-game BAT, byte-exact. Compare `D:\Projects\hacking\rondo\TILEMAP.md` —
same Konami lineage, one generation earlier (no super-block tier).

## The hierarchy ✓

| tier | size | format | where (stage 1) |
|---|---|---|---|
| cell (BG tile) | 8×8 px | BAT word = `palette<<12 \| tile#` | VRAM BAT `$0000.w-$0FFF.w` (128×32, MWR `$0030`) |
| **metatile** | 32×32 px = 4×4 cells | **32 B = 16 BAT words, COLUMN-major** (4 words per cell-column, left→right), palette included | global def table @ file **`$020000`** (bank `$10`), entry N at `+N*32` |
| **map** | column of 7 metatiles = 32×224 px | **8-byte record**: 7 level-local def indices top→bottom + 1 trailing byte (attr? TBD) | bank `$11`; level-1 records observed from ~`$023B70` (region starts ~`$022C00` — pre-stage columns likely precede) |

- Level-local index → global def#: **+ base** (stage 1 base = `$4D`). Where the
  per-level base + map pointer live: TBD (per-stage table hunt).
- Def table extent (stage 1): **~280 entries** (`$020000-$0222FF`, 8,960 B) —
  fills bank `$10` + 24 spill entries; map records follow at ~`$022300`.
- **Index-width lineage vs Rondo:** both games exceed 8-bit def space.
  Parodius: per-LEVEL base window (zero per-cell cost, level confined to a
  256-entry window). Rondo ('93): per-CELL 9th bit via an 8 B/super-block
  bit-pack (rondo TILEMAP.md §1b) — full 512-entry reach anywhere, at
  1.125 B/cell. Same problem, one engine generation apart.
- Playfield = 28 BAT rows = 7 metatile rows; metatile grid is BAT-aligned
  (col % 4 == 0, row 0 = boundary).
- The stage-1 water's 2-frame wave stagger is literally authored into the map
  (alternating column records).
- Level scroll = append next column record at the seam (one 8-px BAT column
  drawn per step from the current metatile column).

## Methodology (repeatable for other levels)

1. `parodius_batwatch.lua` — per-frame BAT diff (v1's VRAM write callbacks
   never fire in Mesen for VDC port writes; diffing is the reliable capture).
   Full window `$0000-$0FFF` words; log = seam columns with values.
2. Reconstruct world columns from the log; match 4×4 col-major word blocks
   against the def table (dict lookup) — diverse blocks vote out the
   uniform-sky false matches; alignment from `batcol % 4`.
3. Convert to index columns; **delta-sweep** the ROM search (stored = idx −
   base) — that's what found the map records (delta −$4D, bank `$11`).

## Open items

- Per-stage table: map pointer, def-table base per level, map length.
- Byte 8 of the column record (always `$00` in the sampled stretch).
- Levels 2-8: same capture+search pass (bases/banks will differ).
- Map ripper: render whole levels to PNG from ROM (defs + tile rips +
  palettes already available); later, the editor + SF2-relocated maps.
