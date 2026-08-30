# Parodius PCE — Symbol / Address Reference

Consolidated from live RE. ✓ verified, ~ inferred. `[R]` resident kernel (bank `$00`, global),
`[S]` state-specific. Addresses are logical unless noted; bank given where it matters.

## Resident kernel routines (bank `$00`, `$E000-$FFFF`)

| Addr | Conf | Name / role |
|------|------|-------------|
| `$E000` | ✓ | RESET entry |
| `$E0DE` | ✓ | **IRQ1 / VDC handler** (vblank + raster dispatch) `[R]` |
| `$E0F1` | ✓ | snapshot VDC status → `$3A` (runs on every IRQ1) |
| `$E102` | ✓ | vblank main-work path |
| `$E10A` | ✓ | `INC $33` (set vblank-in-progress guard) |
| `$E16A` | ✓ | **DVSSR write** = set SATB-DMA pending bit (`LDA #$13`/`ST2 #$10`) |
| `$E171` | ✓ | vblank epilogue: `STZ $33` / `STZ $34` (force-clear mutex) |
| `$E175` | ✓ | shared epilogue (restore banks, RTI) |
| `$E188` | ✓ | IRQ2/NMI/BRK handler |
| `$E189` | ✓ | vblank LITE / lag-frame path |
| `$E1A2` | ✓ | **raster / HUD-split handler** (`$3F2F`-indexed) `[R]` |
| `$E1A9` | ✓ | raster-list interpreter (negative `$3F2F`) |
| `$E259` | ~ | VDC setup (called early in vblank) |
| `$E36E(A)` | ✓ | bank-switch IN: save MPR2→`$3F00`, page `A..A+3` into MPR2-5 |
| `$E375` | ✓ | `$E36E` tail (page only, no save) |
| `$E381` | ✓ | bank-switch RESTORE from `$3F00` |
| `$E3B5(X)` | ✓ | write BG scroll BXR(7)/BYR(8) from shadows; X=0 playfield, X=1 HUD |
| `$E3C6` | ✓ | write X-scroll half only |
| `$E3D8` | ✓ | **wait-for-VD** primitive (`STZ $3A` / `BBR 5,$3A,self`) |
| `$E3FE` | ✓ | mutex-guarded object work entry (`$34` lock → `JSR $5797`) |
| `$E411` | ✓ | sibling mutex-guarded entry (`$34` lock → `JSR $55DC`) |
| `$E43D` | ✓ | TIMER (TIQ) ISR — `STA $1403` ack; bank-pages; streams `($6C)`, `$FF`=end |
| `$E4D7` | ✓ | vblank **game-state dispatcher**: jump table (via `$E6CE`) on `$30`, 7 entries `$E514/$E51D/$E539/$E584/$E5BA/$E5D3/$E5F0`; each pages its own banks |
| `$E6BC` | ✓ | select VDC reg 5 (CR) |
| `$E6BE(A)` | ✓ | select VDC reg `A` (shadow `$3F40`) |
| `$E6B1` | ✓ | select VDC reg 2 (VWR/VRR data) |
| `$E6B5` | ✓ | select VDC reg 1 (MARR, read addr) |
| `$E6B9` | ✓ | select VDC reg 0 (MAWR, write addr) |
| `$E6C5` | ✓ | CR high byte = 0 → VRAM auto-increment +1 |
| `$E6CE` | ✓ | inline-jump-table dispatch: `JSR $E6CE` + address table follows, indexed by A |
| `$EEF5` | ✓ | foreground frame epilogue: `INC $80`; reset per-frame state |
| `$ECD9..$ED1F` | ✓ | foreground main-loop body (bank-bracketed subsystem calls) |

## Script/animation engine (bank `$01`, `$C000-$DFFF` via MPR6) — see `anim-engine.md`

| Addr | Conf | Name / role |
|------|------|-------------|
| `$C04E` | ✓ | **engine entry** (vblank `$E151`): walk 8 slots, tick countdowns, run events. NOT audio |
| `$C063` | ✓ | slot-state dispatch (1→`$C06D` 2→`$C0C1` 3→`$C0FB`) |
| `$C06D` | ✓ | tick: `DEC $38A0,X`; on 0 fetch sequence (`$C5BA` table) + run events |
| `$C159` | ✓ | event dispatch: `$FE`→copy, `$FF`→end, else→decompress |
| `$C168` | ✓ | **`$FE` VRAM→VRAM copy** `[FE][?][src.w][dst.w][cnt×16w]`; unrolled loop `$C191-$C24C`, ~32.5 cyc/word |
| `$C25C` | ✓ | **ROM→VRAM decompressor** `[bank][p1][dst.w][src]`; two-stream RLE/LZ; ~100 cyc/output-byte |
| `$C4A9`/`$C4B0` | ✓ | decompressor VDC data writers (lo/hi) |
| `$C5BA` | ✓ | sequence pointer table (indexed by `$3888,X` ×2) |

## ROM data regions

| Banks | Contents |
|-------|----------|
| `$24-$2B` | **DDA sample data** (~64KB): 92-100% 5-bit values, `$FF`-terminated runs — the TIQ streamer's (`$E43D`, via `($6C)`) source. Fixed-region ⇒ SF2 page latch can never affect sample playback. |
| `$38-$3B` | palette blocks (the colour hack's `palette.inc` target) |
| various | compressed graphics = 62% of the ROM (637KB) — map: `rom_map.png`; heaviest: `$17-$1F`, `$30-$37`, most of `$40-$7F` |

## Banked game routines

| Addr | Bank | Conf | Role |
|------|------|------|------|
| `$4000` | overlay | ✓ | main per-frame game logic + SATB/star build hook `[S]` |
| `$4035` | overlay | ~ | overlay video hook (vblank `$E148`) `[S]` |
| `$40B8-$416B` | `$3C` | ✓ | **starfield SATB-tail RMW** loop `[S]` |
| `$40EC` | `$3C` | ✓ | `TAI $0002,$2000,#8` — read SATB entry VRAM→WRAM |
| `$415E` | `$3C` | ✓ | `TIA $2000,$0002,#8` — write SATB entry WRAM→VRAM |
| `$47D7` | `$20` | ✓ | per-object update (flags `$2216`, vel `$2248,X`) |
| `$580C` | `$20` | ✓ | object dispatcher loop (8 slots, intro) |
| `$5797` | overlay | ~ | object/SATB work (under `$34` mutex) |
| `$55DC` | overlay | ~ | object work (under `$34` mutex, `$E411`) |
| `$5219` | `$20` | ~ | 16-bit shift-add multiply (coord scaling) |

## Zero-page / WRAM variables

| Addr | Conf | Role |
|------|------|------|
| `$00`-`$01` | ✓ | pointer scratch (star routine; also generic) |
| `$02`-`$03` | ✓ | star X wrap counter (resets to `$0120`=288) |
| `$04`-`$09` | ~ | star routine scratch (masks/flags `$08`,`$09`) |
| `$08`-`$09` | ✓ | anim-engine event pointer (also generic scratch) |
| `$10`-`$16` | ✓ | anim-engine decompressor scratch (`$12/$13` = control-stream ptr) |
| `$30` | ✓ | game-state selector (index into `$E4D7` jump table) |
| `$31` | ✓ | sub-state selector (state 2's inner dispatch) |
| `$33` | ✓ | vblank-in-progress guard |
| `$34` | ✓ | **SATB/object critical-section mutex** (bit7 = lock) |
| `$39` | ✓ | display-blank frame countdown: while >0, vblank writes CR with BG+SPR masked off (`$E127-$E13C`); 0 in normal gameplay |
| `$3A` | ✓ | VDC-status snapshot (set by `$E0F1`); VD bit = bit5 |
| `$3F` | ✓ | cleared in vblank (`STZ` at `$E157`) |
| `$45` | ~ | reset by `$E3AE` |
| `$4A`-`$4B` | ✓ | CR/display-control working value |
| `$4D` | ✓ | raster-event index (HUD interpreter) |
| `$6C` | ✓ | timer-ISR stream pointer (`($6C)`) |
| `$80` | ✓ | frame counter (`INC` at `$EEF5`) |
| `$CE` | ✓ | anim-engine current slot (X saved across event calls) |
| `$3880,X` | ✓ | anim-engine slot state (0=idle; X=0..7) |
| `$3888,X` | ✓ | anim-engine sequence id (× 2 → `$C5BA` table) |
| `$3890,X` | ✓ | anim-engine sequence position |
| `$3898,X` | ✓ | anim-engine loop counter |
| `$38A0,X` | ✓ | anim-engine tick countdown (stage-1 water reload = 9 → the lag beat) |
| `$93`/`$94`/`$95`/`$99` | ~ | game-state selectors (foreground dispatch) |
| `$9F`,`$A3` | ~ | foreground dispatch indices |
| `$3E00-$3E60` | ✓ | scroll **working** shadows (BXR/BYR lo/hi) |
| `$3E80-$3EE1` | ✓ | scroll **latched** shadows (double-buffered; X-indexed 0/1) |
| `$3EC0` | ✓ | scroll offset subtracted from raster split lines |
| `$3F00` | ✓ | saved MPR2 bank (by `$E36E`) |
| `$3F08` | ✓ | saved MPR2 bank (by `$E411`) |
| `$3F2F` | ✓ | raster-split mode selector (0/positive/negative) |
| `$3F30` | ✓ | CR shadow (display-control byte) |
| `$3F40` | ✓ | selected-VDC-register shadow |
| `$40`,`$48` | ✓ | raster-list pointers (event types / scanlines) |

## Hardware (bank `$FF` I/O page)

| Addr | Role |
|------|------|
| `$0000`/`$0001` | VDC address/status |
| `$0002`/`$0003` | VDC data LO/HI |
| `$0400-$0407` | VCE (HuC6260) |
| `$1403` | timer (TIQ ack) |

## VDC registers of note (HuC6270)

| Reg | Name | Value seen | Note |
|-----|------|-----------|------|
| `$05` | CR (control) | `$18CC` | sprites+BG on, vblank+RCR IRQ enabled |
| `$06` | RCR | `$0115` (gameplay) | raster-compare → HUD split ~line 230 `[S]` |
| `$07`/`$08` | BXR/BYR | scroll | written by `$E3B5` |
| `$09` | MWR | `$0030` | BG map dimensions `[S]` |
| `$0C` | VPR | `$0F02` | VSW=3, VDS=16 |
| `$0D` | VDW | `$00EF` | 240 active lines `[S]` |
| `$0E` | VCR | `$0003` | bottom blank = 4 |
| `$0F` | DCR | `$0000` | SATB auto-DMA OFF (manual mode) |
| `$13` | DVSSR | `$1000` | SATB source = VRAM word `$1000` |
