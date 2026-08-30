# Parodius PCE — Sprites, SATB & the Starfield Dropout

✓ = verified live, ~ = inferred. See `architecture.md` for the kernel/ISR context.

## 1. SATB / sprite-DMA pipeline `[resident mechanism]` ✓

- **SATB source** = VRAM word **`$1000`** (`DVSSR` reg `$13` = `$1000`). 64 sprites × 4 words = `$1000-$10FF`.
- **Manual DMA mode**: DCR (reg `$0F`) = `0` (bit4/DSR clear). So auto-at-vblank is OFF.
- The internal SAT (post-DMA) is Geargrafx memory area id 6.

### SATB DMA semantics (HuC6270, authoritative — per project owner)

> The VRAM→internal-SAT transfer can **only** happen at vblank, never on an arbitrary scanline.
> - **Auto** (DCR bit4 set): DMA on the first vblank line, every frame.
> - **Manual** (this game): writing `DVSSR` **sets a pending/request bit**; at vblank, *if* the bit is
>   set the DMA runs and the bit is cleared.

So the game's `LDA #$13 / ST2 #$10` at **`$E16A`** (end of the vblank handler) only **sets the request**.
It executes at y≈47-55 (active display, because the handler overran) ✓ — but the actual transfer waits
for the next vblank. *(Earlier "DMA fires mid-screen and overwrites the SAT" theory was wrong — retired.)*

## 2. The starfield — Gradius-style SATB-tail RMW `[state-specific]` ✓

Parodius implements its starfield exactly like the Gradius / Gradius II PCE ports: a
**read-modify-write of the SATB *tail* directly in VRAM**. Routine `$40B8-$416B` in **bank `$3C`**,
called from `$4000` via the vblank path's `$E161`. Observed running at y≈46 (top-of-frame overrun). ✓

```
$40B8..$40CD   ST1/ST2 #$00 ×N           ; (clear path) zero SATB entries in VRAM
loop ($40CF):
  $40DD  index = 63 - sprite#            ; walks the TAIL downward (stars = high indices)
  $40E4  VRAM addr = $1000 + index*4 ; ST2 #$10
  $40E9  JSR $E6B1                        ; set MARR (VRAM read pointer)
  $40EC  TAI $0002,$2000,#$0008           ; READ entry: VDC read port -> WRAM $2000
         ... wrap-X math (counter $02/$03 resets to $0120=288; tables $4174/$4194/$416C/$4170,Y) ...
  $415E  TIA $2000,$0002,#$0008           ; WRITE entry back: WRAM $2000 -> VDC data port
  $4165  DEX / BMI exit / JMP $40EC       ; next entry (one entry per iteration)
```

Confirmed via a VRAM **read** breakpoint on `$10FC`: the routine genuinely reads the SATB tail back
out of VRAM (the read fired at `$40F3`, just after `TAI`). ✓ Stars only need their **X** updated (Gradius
pattern), though the current code copies all 4 words per entry.

State variables: see `symbols.md` (`$00-$09` star scratch, `$4174`/`$4194`/`$416C`/`$4170` tables in bank `$3C`).

## 3. The bug: partial star dropout `[state-specific]` ✓ root-caused

**Symptom:** after moving the HUD split lower (taller window), the farground stars — the **tail/highest
-index** SATB entries — partially drop out, intermittently.

**Cause:** the star RMW edits the **live VRAM SATB one entry at a time**, in a loop that is
**interruptible between entries** (a single `Txx` is atomic, but the loop is not — see §5). The same VRAM
SATB is what the vblank DMA latches. On a frame where the work runs late enough that the latching vblank
lands *mid-loop*, the DMA captures a torn SATB — some tail entries new, some last-frame's, some zeroed by
the clear path → partial star dropout. It's **load-dependent** (heavy frames push the loop later) and got
worse because **moving the split down lengthened the handler overrun**, shrinking the margin to the latch.

A `$34` **mutex** already protects this section from *concurrent* re-entry (architecture §5), but it does
**not** protect against the *latch*-vs-*write* race, and the vblank ISR even force-clears `$34`.

**Retired theories:** mid-screen DMA (DMA is vblank-only); 16-sprites-per-line overflow.

## 4. `Txx` block-copy cost `[resident HW behavior]` ✓ (per project owner + math)

- Base block instruction: **17 cycles**, plus **6 cycles/byte** (the read+write pair).
- **+1 cycle/byte** when a side touches the I/O page (the VDC data port `$0002/$0003`). WRAM side is free.
- An 8-byte hardware copy (one sprite, 4 words): `17 + 8×(6+1)` = **73 cycles**.
- Paid **twice per star** (`TAI` read + `TIA` write) = **146 cycles** of block I/O per entry, before
  per-entry overhead (~200 cyc/star all-in).
- **Key property: `Txx` are non-interruptible** — the CPU holds off IRQs until the block finishes. So a
  single large blit *cannot be torn*.
  - Whole 64-sprite SATB in one `TIA` (256 B): `17 + 256×7` = **1809 cyc** (~4 scanlines), atomic.
  - 16-star block (128 B): `17 + 128×7` = **913 cyc**, atomic.

(For reference, a scanline ≈ 455 CPU cycles at 7.16 MHz; vblank ≈ 23 lines ≈ ~10.5k cycles.)

## 5. Fix options

The data lives in VRAM and is RMW'd in place, so "trigger the DMA early" alone is insufficient — the fix
must stop the latching vblank from catching the loop mid-flight.

1. **Do the starfield first / early** `[recommended for correctness]` — run the star update at the start
   of the frame's work so it completes with ~a full frame of margin before the latching vblank. Safe to run
   the IRQ-blocking copies at the top of the display (no RCR scheduled there in single-split gameplay;
   watch multi-split/boss states). Costs 1 frame of star latency (invisible).
2. **Single atomic blit** `[recommended for speed]` — keep star X-state in **WRAM**, build the entries in
   a WRAM shadow, push with **one `TIA`** (atomic → un-tearable). Removes the `TAI` read-back entirely.
   Note: X words aren't contiguous in the SATB (every 4th word), so a single `TIA` implies blitting whole
   entries; weigh vs. writing only X words per star.
3. **Gate the request** — only set `DVSSR` (`$E16A`) after the star loop completes, so a vblank that
   interrupts the loop simply skips the DMA that frame (stale-but-whole, not torn).

Best = (1)+(2): correct *and* fast. Before coding, measure in the **target gameplay state**:
- exact **star count** (where X is initialized for the `$40B8` loop),
- whether **only the X word** changes per star per frame (diff a star entry across two frames).
