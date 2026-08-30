# Parodius PCE — Compressed Graphics Format

The format decoded by the bank-`$01` engine's ROM→VRAM event handler (`$C25C`,
see `anim-engine.md`). Offline decoder: `pce_gfx_decode.py` — **verified
bit-exact against 54/54 in-game VRAM captures** covering every mode:
tile/sprite × raw/dictionary × all flip states (level 1 corpus via
`parodius_gfxtrace.lua`, 2026-08-24; 406 decoder calls, 43 unique streams,
54 unique (stream, flip) outputs — sprites are stored once and mirrored via
`p1` at decompress time). ✓ = corpus-verified.

## Stream layout

```
src+0                  header: bit7 = SPRITE writer, bits6-0 = dict length D
src+1 .. src+D         dictionary (pixel-value remap table; engine always
                       indexes 16 entries at src+1 - D only offsets the ctrl)
src+1+D ..             control stream (tokens below)
```

Event: `[bank][p1][dst.w lo,hi][src lo,hi]` (6 bytes; `bank..bank+3` paged into
MPR2-5, `src` is a `$4000-$BFFF` logical address). `p1`: bit0 = **hflip**,
bit1 = **vflip** (sprite writer only). Event list ends with token `$FF`.

## Control tokens ✓  (produce the intermediate byte stream)

| token | bytes | output |
|-------|-------|--------|
| `$00` | `00 cnt fix L0..` | cnt words of (fix, literal_i); cnt 0 → 256 |
| `$01` | `01 lo hi b` | b × cnt16 |
| `$02` | `02 cnt b1 b2` | word (b1,b2) × cnt; cnt 0 → 256 |
| `$03-$3F` | `n b` | b × n |
| `$40-$7F` | `n` | (n&$3F) zero bytes; 0 → 256 |
| `$80` | `80 lo hi L..` | cnt16 literal bytes |
| `$81-$BF` | `n L..` | (n&$3F) literal bytes |
| `$C0-$FD` | `n L..` | (n&$3F) words of ($00, literal_i); 0 → 256 |
| `$FE` | `FE cnt b1-b4` | 4-byte pattern × cnt; cnt 0 → 256 |
| `$FF` | `FF` | end of event |

## The byte writer `$C3FD` ✓

Bytes are buffered in WRAM at `$3C80` and flushed to the VDC data port in
chunks. The buffered data is **already in VRAM planar layout**; the optional
"conversion" is an in-place **pixel-value remap** through the dictionary.

**Tile writer** (header bit7 clear): 128-byte chunks (4 BG tiles).
Flush = linear `$3C80-$3CFF`. If D>0, remap first (below) over plane arrays
`$3C80/$3CA0/$3CC0/$3CE0` (+X, X=31..0).

**Sprite writer** (header bit7 set): 32-byte chunks. On store, `p1` bit0
bit-reverses each byte (hflip). If D>0, remap over `$3C7F/$3C80/$3C8F/$3C90`
(+X, X = 15,13,..,1 — 16-bit rows as byte pairs). Flush: forward pairs, or
descending pairs (`p1` bit1 = vflip).

**The remap pipeline** (per row-byte X, 4 plane bytes): A=0, then **nine**
passes (`$07`=8 counts down through 0) of:

```
Y = A & $0F ; A = table[Y]        ; table = 16 bytes at src+1
ASL A                             ; C = new pixel bit (table bit 7)
ROL plane3,X ; ROL A              ; new bit in, OLD DATA bit out -> into A
ROL plane2,X ; ROL A              ;   (planes in the order listed above,
ROL plane1,X ; ROL A              ;    table bits 7,6,5,4 -> planes 3..0)
ROL plane0,X ; ROL A
```

Each pass rotates 4 new bits in while the 4 displaced *original* bits assemble
in A as the **next pixel's dictionary index** — the data itself carries the
indices. Pass 0 is pipeline priming: it writes `table[0]` bits that the next
8 passes push off the end of the byte (this is why `dict[0]` is always `$00`).
So: original planar pixel value → `table[value]` high nibble, in place, with
zero extra memory reads.

## Consequences for the 60fps hack

- A block with D=0 is a **raw stored stream**: the control layer alone
  reconstructs VRAM data verbatim. Re-encoding any graphics as `$80`-literal
  runs with header `$00`/`$80` and `p1=0` needs no knowledge of the planar
  modes at all.
- Encoding cost table and the stage-1 water case: see `anim-engine.md`.

## Gap census (2026-08-24) — the bytes BETWEEN the known streams

After folding all traced + table-walked + census-discovered streams (470),
the graphics banks still held 43 gaps / 35.5 KB. Static classification:

| kind | bytes | notes |
|---|---|---|
| unknown → mostly identified | 19.8 KB | bank `$20` chunk = object-engine CODE (`STZ` runs — banks `$20-$23` are the paged object engine); bank `$15` = 8-byte SATB-entry-shaped records (metasprite cell templates, likely); bank `$16` = repeated-word template table; banks `$46/$64/$65` small chunks still open |
| **orphan compressed streams** | 9.6 KB | initially looked unreferenced — ALL turned out to be real content loaded via dynamic per-state events: other characters' pose/shield/death frames, octopus pod scale steps, slow-pose end frames. (Shields are the extreme case: each DAMAGE-SHRINK size is a separate stream, loaded only when the shield degrades to it — and a special pickup replaces the shield, skipping the rest. Full capture required deliberately tanking hits per character.) Every one was subsequently captured live (census) and folded. The one "debris" suspect (`$08E000`) was a mid-stream decode mirage — really the body of stream `$44:$9E79` (`$08DE79-$08E2F7`, its header in the adjacent "unknown" chunk). **Final: the graphics banks contain no unused streams at all.** |
| padding (`$FF` bank tails) | 4.7 KB | dead, reclaimable |
| pointer table | 2.3 KB | bank `$0D`, `$01A000` |

Runtime confirmation of accessors is blocked by a Mesen limitation: PRG-ROM
READ callbacks (like VRAM WRITE callbacks) never fire from Lua — the gap
watchpoints in `parodius_census.lua` can only catch EXEC. A future pass
needs logical-address callbacks + `convertAddress`, or native breakpoints.

## Tools

- `pce_gfx_decode.py <rom> <bank> <src>` — decode one block (hex dump).
- `pce_gfx_decode.py <rom> --verify <trace>` — validate against a
  `parodius_gfxtrace.lua` capture (VRAM ground truth per ROMDEC event).
- All paths including flips are corpus-verified; later-level captures can
  only add new (stream, mode) instances, not new mechanics.
