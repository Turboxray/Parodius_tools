# Parodius PCE — Frame Rate & the VRAM Animation Engine

Investigation of the game's ~54Hz effective update rate (2026-08-23). Root cause found and
quantified: the **bank `$01` script/animation engine** re-decompresses the stage-1 water
tiles from ROM every 9 frames, and the decompression is so slow the vblank handler misses
the next vblank IRQ — dropping exactly one logic frame per animation step.

`[R]` = resident kernel, `[S]` = state/stage-specific. ✓ verified live, ~ inferred.

## 1. Symptom & verdict ✓

- In-game feel: "stalls every ~10th frame", ~54Hz. Measured: **1 frame dropped in 9,
  metronomically** (462/462 gaps == 9 over 1200+ frames), effective **53.4/60**.
- **Identical on the original and patched ROM** (11.0% vs 11.1% lag frames) — the port
  shipped this way; the 224-line window hack did not cause or worsen it.
- The pre-stage "outer" area runs at a true 60 (no animated water). Other levels drop
  frames irregularly (their own animation cadence + genuine load; e.g. one captured level
  ran `done` at +256..259 of a 263-line frame every frame — riding the edge).
- NOT the music/sound driver (that runs off the TIQ timer ISR, cheap), NOT the scroll
  seam, NOT SATB shuffling, NOT a deliberate governor.

## 2. Drop mechanism (lite path) `[R]` ✓

Vblank IRQ (Mesen scanline ~254-257) enters `$E102`, sets guard `$33`, runs the full
handler; on a normal stage-1 frame it finishes (`$E171`, `STZ $33/$34`) ~85 lines later.
On a heavy frame the work exceeds the whole frame, the next vblank IRQ finds `$33` set and
takes the **lite path `$E189`**: re-write CR + scroll (X=0), run the `$E3FE` mutex-guarded
object/SATB entry, epilogue — **game logic skipped, `$33` NOT cleared**. The interrupted
full handler then resumes after the RTI and completes ~line 30-80 of the lite frame.

Correction to older notes: the full handler does not "overrun vblank by ~50 lines" — on
normal gameplay frames it finishes around **line 90** (stage 1) to **line 160** (heavier
levels) of active display; the every-9th heavy frame doesn't finish at all.

## 3. The script/animation engine `$C04E` (bank `$01`, MPR6) ✓

Previously mislabeled "audio/secondary". Called every vblank from `$E151`. Structure:

```
$C04E  LDA $3B / BNE rts            ; global disable
       for X = 7..0:                ; 8 script SLOTS
         LDA $3880,X / BEQ next     ; slot state (0 = idle)
         dispatch state-1 via $E6CE table: 1->$C06D  2->$C0C1  3->$C0FB
$C06D  LDA $38A0,X / BNE: DEC, RTS  ; per-slot frame countdown -> CHEAP on most frames
       ; countdown hit 0: fetch sequence via table $C5BA[$3888,X] -> ($00)
       ; reload countdown from seq data (stage-1 water = 9  <-- the beat)
       ; per event at ($08): JSR $C159, INC $3890,X, loop until nonzero duration
```

Slot arrays (WRAM): `$3880` state, `$3888` sequence id (index into pointer table
`$C5BA`), `$3890` sequence position, `$3898` loop counter, `$38A0` tick countdown.
`$CE` = current slot during dispatch; ZP `$08/$09` = event pointer.

### Event types (`$C159` dispatch) ✓

| byte 0 | handler | format | action |
|--------|---------|--------|--------|
| `$FE` | `$C168` | `[FE][?][src.w lo,hi][dst.w lo,hi][count]` (7 bytes) | **VRAM→VRAM copy**, count×16 words. MARR=src, MAWR=dst, increment +1, interleaved `LDA $0002/STA $0002/LDA $0003/STA $0003` unrolled ×16 (`$C191-$C24C`). ~32.5 cyc/word (the slower of the two known orderings; read-read-write-write is 29.6). |
| `$FF` | rts | 1 byte | end/hold |
| else | `$C25C` | `[bank][p1][dst.w lo,hi][src lo,hi]` (6 bytes) | **decompress ROM→VRAM**. Byte 0 = ROM bank (paged via `$E36E`). Two-stream RLE/LZ decoder: control stream at `($12)` (= src + (hdr&$7F) + 1), data at `($00)`; token classes 0/1/2/<$40/$40-7F/$80-family; VDC writers at `$C4A9/$C4B0`, helpers `$C3EF/$C3F8/$C3FD`. Event advance +6 at `$C35F`, loops to `$C159`. |

## 4. Stage 1 measurements ✓

Captured with the Lua tools (below); 5204-frame run, pre-stage + most of level 1.

| slot | what | dst (VRAM) | cadence | payload / step |
|------|------|-----------|---------|----------------|
| 7 | **water** (BG tiles) | `$2E30.w` | **exactly 9 frames** | ROMDEC, 6-frame cycle (src `$9616/$98BA/$9B57/$9DF2/$A090/$A335`, ~680 B compressed) → **~1092 B = 546 words = 34 tiles** |
| 0 | ship anim (sprite) | `$7F80.w` | 1-8 frames, movement-driven | ROMDEC, 5 frames (bank `$40`, src `$B757..$B9E9`), 66-139 words |
| ? | small always-on anim | — | every frame | ~11-12 words |

**Cost of the water step: ~240 scanlines ≈ 108k CPU cycles.**

| metric | value |
|--------|-------|
| decompressor average | **~200 cyc/word, ~100 cyc/output-byte, ~3.2k cyc ≈ 7 scanlines per 8×8 tile** |
| in literal runs (event viewer) | ~32 cyc/word — copy speed; the average is killed by token handling + per-byte JSR + nested TIQ time |
| same 546 words as plain CPU copy | ~17.7k cyc ≈ **39 scanlines** |
| same via VDC VRAM-DMA (SOUR/DESR/LENR `$10-$12`) | **~0 CPU** (VDC-internal slot arbitration, no /RDY stall) |

Why the copies are extra slow here: CPU port access stalls on VDC **/RDY** until a free
VRAM slot; the engine runs deep in **active display** (handler is ~85 lines in when it
starts), when slots are scarcest. Blanking-time access is markedly cheaper per word.

Frame-drop arithmetic: ship alone fits, water alone is marginal (~205-line bursts seen
fitting), **water frames always drop**; ship+water on the same frame (172/660 events)
explains bursts > drops (840 heavy bursts vs 463 drops in the profiler run).

### The `$FE` VCOPY path IS used in production — bubble/cloud level ✓ (2026-08-24)

Event-viewer capture on the later bubble/cloud level shows the manual-copy loop live:
PCs `$C191-$C24E` (the unrolled block), alternating VDC data-port R/W pairs — read from
MARR, write to MAWR, lo/hi interleave. **That level keeps its animated tilesets resident
in VRAM and steps them with `$FE` copies — no realtime decompression at all.** Measured
pair spacing ≈ 81 master ≈ **27 CPU cycles/word** sustained, matching the bench numbers
(29.6/32.5 cyc/word for the two orderings) and ~7× cheaper per word than stage 1's
decompressor. Same engine, two data-authoring conventions; stage 1 simply got the
expensive one. The fix below is therefore "port stage 1 to the bubble level's own
convention" — the VCOPY path is production-proven, no engine risk.

## 5. Fix — IMPLEMENTED (SF2 build) & MEASURED ✓ 2026-08-24

Shipped in `Parodius_SF2.asm` (not the plan below — the SF2 expansion made a
better route possible): a load hook at the `$C164` dispatcher jump diverts
every ROMDEC event whose `[bank][src]` matches the LUT (bank `$80`, bucketed
records) to a chunked copy from uncompressed assets in expansion banks —
**window addressing**: latch the asset's SF2 page, map `$40|(bank&$3F)`.
Flips (`p1≠0`) and unknown streams still fall through to the decompressor.
**Measured: stage-1 gameplay 0 lag frames, eff 60.0/60** (was 11%/53.4);
vblank handler finishes ~line 56-79 (was 85-160). Debug war story: two
stacked bugs made 100% fallthrough look like success (A-clobber in the
springboard; raw `$80+` MPR mapping = open bus) — caught by the null-water
experiment + hookprobe. A graceful-fallback hook needs a POSITIVE detection
test (`parodius_hookprobe.lua`).

## 5b. Original fix plan (superseded, kept for reference)

Goal: true 60fps in stage 1 (and any level whose lag is animation-driven, not load).

1. At level load, decompress all 6 water frames once into free VRAM:
   6 × 546 = **3,276 words (~6.4 KB)**.
2. Rewrite slot 7's six script events from ROMDEC → **`$FE` VCOPY** events pointing at
   the cached frames (engine already supports the event type — data patch, not code).
   Per-beat cost drops ~240 → **~39 lines**; ~180 lines of margin.
3. Optional upgrades: `$FE` handler via VRAM-DMA (~0 CPU; verify DMA vs active-display
   fetch + vblank SATB-DMA interaction on hardware first), and/or the faster copy
   ordering (`lda $2 / ldx $3 / sta $2 / stx $3`, 29.6 vs 32.5 cyc/word).

### Slot-7 ROM locations (found 2026-08-23, static hunt)

- `$C5BA` table entry **id 3** (file `$25C6`) → sequence at `$C7A8` (file `$27A8`):
  `[08][80][$D20E $D215 $D21C $D223 $D22A $D231][FF FF]` — reload `$08` = 9-frame
  period (dec-to-zero inclusive; the beat is ONE byte at file `$27A8`), `$80` = loop
  forever.
- Six events, 7 bytes each, at `$D20E-$D237` (file `$320E`): `[40 00 30 2E src][FF]`.
- Compressed frames: banks `$42/$43` (file ~`$85616`+), ~680 B each.
- Space audit: bank `$01` has ZERO free bytes; resident bank one 37-byte `$FF` run at
  `$FF9B` (partly used by the mid-HUD comp helper since v1.0); big free ROM runs:
  bank `$23` 6,481 B (file `$466AF`), bank `$2F` 3,793 B. An `$FE` event list is
  8 bytes vs the current 7, so in-place event rewrite doesn't fit — either relocate
  the lists (reuse the old 42-byte event block + `$FF9B`) or use the stored-streams
  variant: re-encode the 6 frames as literal-only compressed data in the free banks
  and just repoint each event's `[bank][src]` (same-size, zero new code; literal
  tokens decode at ~copy speed).

### On V2V DMA (why Konami likely didn't, and whether we should)

The VDC's VRAM→VRAM DMA (SOUR `$10` / DESR `$11` / LENR `$12`) would do these copies
with ~zero CPU. Likely reasons the engine uses CPU copies instead: the engine runs
mid-active-display, where CPU port I/O is display-safe by construction while DMA
owns the VRAM bus (glitch risk unless confined to blanking / it yields to fetch);
DMA needs completion handling + DCR care; era-typical caution. **Open hardware
question** (bench it): does V2V DMA started mid-display trickle through blanking
slots harmlessly (→ fire-and-forget upgrade of the `$FE` handler, ~10 bytes), or
does it stomp display fetches (→ keep VCOPY, ~39 lines, already fits)?

Open items (post-fix residuals):
- **VCOPY-animated levels still lag**: cloud/bubble level (gap-17) AND the
  final level (the f54000-66000 band in the full-game profile, 2026-08-24) —
  both animate via the `$FE` VCOPY path (manual VRAM read/write loop), which
  the load hook does not intercept. Fix candidates: divert `$FE` events in
  the hook too, or upgrade the copy to V2V DMA (SOUR/DESR/LENR) — pure
  bandwidth, the data is already in VRAM. This is the top remaining item:
  it covers both residual heavy bands.
- Flipped ROMDEC variants (`p1≠0`) still decompress by design — teach the hook
  to flip (bit-reverse / reversed write order) if any flip-heavy animation
  shows a beat.
- Level-transition LITE bursts (big one-shot loads) — cosmetic, verify the
  chunked copy keeps them bounce-free.

## 6. Measurement tools (Mesen2 Lua, in repo)

| script | logs | purpose |
|--------|------|---------|
| `parodius_framewatch.lua` | `parodius_framewatch*.txt` | lag-frame (`$E189`) counter + gap periods + ISR finish line |
| `parodius_framewatch2.lua` | `parodius_framewatch2*.txt` | per-frame scanline stamps at each vblank subcall (finds which call balloons) |
| `parodius_animwatch.lua` | `parodius_animwatch.txt` | every engine event: type (VCOPY/ROMDEC), slot, bank, src, dst, size |
| `parodius_vwrcount.lua` | `parodius_vwrcount.txt` | exact VDC data-port bytes written per frame by the engine (PC-filtered) + burst scanline span |

Method notes: stamps are "scanlines since vblank IRQ"; Mesen's frame counter increments
mid-frame, so raw deltas can wrap (scripts compensate). The `c04e→e631` interval includes
nested TIQ time.
