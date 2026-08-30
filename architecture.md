# Parodius PCE — Engine Architecture

`[resident]` unless marked `[state-specific]`. ✓ = verified live, ~ = inferred.

## 1. Memory map / banking `[resident]`

The HuC6280 sees eight 8 KB logical pages via MPR0-7. Typical map:

| Page | Logical range | Bank | Role |
|------|---------------|------|------|
| MPR0 | `$0000-$1FFF` | `$FF` | Hardware I/O page (VDC `$0000-3`, VCE `$0400-7`, PSG, timer `$1403`, joypad `$1000`) |
| MPR1 | `$2000-$3FFF` | `$F8` | WRAM (8 KB). All game state + sprite staging live here |
| MPR2-5 | `$4000-$BFFF` | varies | **Banked ROM overlays** (current code/data). Seen: `20 21 2C 2D` (intro), `02-05`, `05-08`, `3C-3F`, `20 21 2E 2F` (gameplay) `[state-specific]` |
| MPR6 | `$C000-$DFFF` | `$01` | Secondary library bank (audio/`$C04E`, etc.) |
| MPR7 | `$E000-$FFFF` | `$00` | **Resident kernel** — always mapped: vectors, ISRs, helpers |

Geargrafx memory areas: WRAM 8 KB (id 0), ZP 256 B (id 1), ROM 1 MB (id 3), VRAM 32 K words (id 4),
SAT 256 words (id 6, the internal post-DMA sprite table), PALETTES 512 words (id 8), BRAM 2 KB (id 10).

ROM physical offset for a banked address = `bank*0x2000 + (addr & 0x1FFF)`.

## 2. Interrupt vectors `[resident]` ✓ (read from bank `$00` `$FFF6`)

| Vector | Addr | Handler | Purpose |
|--------|------|---------|---------|
| IRQ2/BRK | `$FFF6` | `$E188` | (also NMI slot value) |
| IRQ1 (VDC) | `$FFF8` | **`$E0DE`** | VBLANK **and** raster/RCR split — dispatched by status bits |
| TIMER (TIQ) | `$FFFA` | `$E43D` | fast periodic driver (`STA $1403` ack); pages banks, streams a byte via `($6C)`, `$FF`=end |
| NMI | `$FFFC` | `$E188` | |
| RESET | `$FFFE` | `$E000` | |

## 3. VDC interrupt handler `$E0DE` `[resident]` ✓

One vector services vblank and the raster split. Structure:

```
$E0DE  PHA/PHX/PHY                  ; save regs
       TMA #$04/#$08/#$10/#$20 +PHA ; save overlay banks MPR2-5
       LDA $3F40 / PHA              ; save selected-VDC-reg shadow
$E0F1  LDA $0000 / STA $3A          ; snapshot VDC status -> $3A  (every IRQ1!)
$E0F6  BBR 2,$3A,$E0FC              ; bit2 (RCR) clear? -> vblank check
       JMP $E1A2                    ;   else -> RASTER/HUD path
$E0FC  BBS 5,$3A,$E102              ; bit5 (VD/vblank) set? -> main vblank work
$E102  CLI                          ; re-enable IRQs (timer + re-entrant VDC may nest)
       LDA $33 / BNE -> $E189       ; $33 = vblank-in-progress guard -> LITE path if busy (lag frame)
       INC $33
       $3E00->$3E80 ... $3E60->$3EE0 ; double-buffer scroll shadow latch
       ... JSR $E259 / set CR ...
       JSR $E3B5 (X=0)              ; write BG scroll BXR/BYR (main playfield set)
       JSR $4035                    ; [state-specific] overlay video hook
       JSR $C04E                    ; bank $01 SCRIPT/ANIMATION ENGINE (VRAM copies /
                                    ;   ROM->VRAM decompression; see anim-engine.md).
                                    ;   NOT audio — music runs off the TIQ timer ISR.
       JSR $E4D7                    ; dispatcher -> (calls $4000 game logic deep inside)
       JSR $4000   (at $E161)       ; [state-specific] main game logic + SATB/star build
$E16A  LDA #$13 / JSR $E6BE         ; select DVSSR (reg $13)
$E16F  ST2 #$10                     ; write DVSSR MSB  -> SETS SATB-DMA pending bit
$E171  STZ $33 / STZ $34           ; clear vblank guard + force-clear SATB mutex
       PLA/TAM #$20.. restore banks; PLY/PLX/PLA; RTI
```

Lite path `$E189` (lag frame): re-write CR + scroll (X=0), run the `$E3FE` mutex entry, skip game
logic, `BRA $E175` epilogue. It does **not** clear `$33` — the interrupted full handler resumes
after the RTI and finishes during the lite frame.

Notes:
- The handler is long; it overruns vblank far into active display on **both** original and patched
  ROM — normal gameplay frames finish around **line ~90** (stage 1) to ~160 (heavier levels), and
  every 9th stage-1 frame doesn't finish at all (dropped logic frame → effective ~53.4Hz). Root
  cause is the `$C04E` animation engine re-decompressing the water tiles — see `anim-engine.md`. ✓
- `CLI` is deliberate: lets the timer ISR and a re-entrant VDC IRQ nest. This is central to the
  starfield race (see `sprites-and-starfield.md`).

## 4. HUD raster-split engine `$E1A2` `[resident code, state-specific data]` ✓

Reached when the IRQ1 status has bit2 (RCR) set. Driven by **`$3F2F`** (signed selector):

```
$E1A2  LDY $3F2F
       BEQ  $E21D        ; 0   -> minimal (CLI, exit)
       BPL  $E1FA        ; +   -> simple fixed split (the HUD)
                         ; -   -> $E1A9 table-driven multi-split interpreter
```

- **Simple HUD split** (`$3F2F` positive, gameplay = `2`): `LDA $3F30 / AND #$BF / STA $0002`
  (clear CR bit6 = sprites off for the HUD band) then `LDX #$01 / JSR $E3B5` (load the **X=1**
  scroll set = HUD-region scroll). Exits via shared epilogue `$E175`.
- **Table interpreter** (`$3F2F` negative): per event, read type from `($40),Y`, act
  (disable display / `$E3C6` scroll / `$E3B5` sprites), reprogram **RCR (reg 6)** to the next split
  line from `($48),Y` minus scroll `$3EC0`, advance index `$4D`. Pointers `$40`/`$48` and index `$4D`
  are the per-effect raster list.

In Stage 1 gameplay, **RCR = `$0115`** → split near line ~230 (the bottom HUD). ✓

`$E3B5` = BG scroll writer: selects reg 8 (BYR) then reg 7 (BXR), writes from shadow regs
`$3EC0/$3EE0` (BYR) and `$3E80/$3EA0` (BXR), **indexed by X**: X=0 = main playfield, X=1 = HUD set.
`$E3C6` is the entry that writes only the X-scroll half. ✓

## 5. Frame-sync / threading model `[resident]` ✓

This engine is **interrupt-driven**; there is **no classic foreground idle-spinlock** (the foreground
object engine in bank `$20` is CPU-saturated — sampled PCs always landed mid-work). Frame pacing is the
interrupt structure plus these primitives:

| ZP | Role |
|----|------|
| `$33` | **vblank-in-progress guard**. `INC` at `$E10A`, `STZ` at `$E171`. If already set on entry → lite/lag path. |
| `$34` | **Re-entrancy MUTEX** (bit7 = lock) for the object/SATB/starfield critical section. See below. |
| `$3A` | VDC-status snapshot, written by the shared IRQ entry `$E0F1` on **every** IRQ1. |
| `$80` | Frame counter, `INC` in the foreground frame epilogue `$EEF5`. |
| `$39` | A frame countdown (`DEC` at `$E12D`). |

**The `$34` mutex** guards the SATB/star critical section against re-entry (needed because `CLI` allows
nesting):
```
$E3FE  LDA $34 / BNE bail          ; already locked -> skip
       LDA #$80 / STA $34          ; LOCK (bit7)
       LDA #$20 / JSR $E375        ; page object banks
       JSR $5797                   ; run object/SATB/star work
       STZ $34                     ; UNLOCK
$E411  ... BIT $34 / BMI bail ... STA #$80 ... JSR $55DC ... STZ $34   ; sibling guard
```
The **vblank ISR force-clears `$34`** at `$E171` every frame. The **HUD path never touches `$34`**
(it only `STZ $4D`).

**The VD wait primitive** `$E3D8` (`STZ $3A` / `BBR 5,$3A,self`) blocks until the VDC status has bit5
(VD/vblank) set. Because `$3A` is fed by `$E0F1` on every IRQ1 but only a **vblank** IRQ has VD set,
this wait is released **only by vblank** — a HUD/RCR IRQ writes `$3A` with VD clear and cannot release it.

**Answer to "who resets the sync flag — vblank or HUD?": the VBLANK routine, never the HUD** — true for
both `$34` and the `$3A`/VD wait.

## 6. Bank-switch + VDC-register helpers `[resident]` ✓/~

| Routine | What it does |
|---------|--------------|
| `$E36E(A)` ✓ | Save current MPR2 → `$3F00`, then page banks `A,A+1,A+2,A+3` into MPR2-5. `$E375` is the no-save tail. |
| `$E381` ✓ | Restore MPR2-5 from `$3F00` (undo `$E36E`). |
| `$E6BE(A)` ✓ | Select VDC register `A` (`STA $3F40` shadow, `STA $0000`). |
| `$E6BC` ✓ | Select VDC register 5 (CR). |
| `$E6CE` ✓ | Far-call / bank trampoline: `JMP ($2002)`. Appears all over call stacks. |
| `$E6B1`/`$E6B5` ~ | VDC address helpers used by the starfield (set MARR/MAWR + prime). |

## 7. Vertical timing (modified ROM) `[state-specific]` ✓

VDC regs: VSW=3, VDS=16, **VDW (reg `$0D`) = `$00EF` = 240 active lines**, VCR (reg `$0E`) = `$0003` = 4.
Total ≈ 263. **Vblank window ≈ 23 lines**, but the per-frame vblank handler needs ~110-160 scanlines
(stage 1 normal frames; more on heavy levels) → it always overruns deep into active display, on the
original ROM too. This is the timing pressure behind the starfield bug: extending the window (bigger
VDW) shrinks the already-tight vblank. The every-9th-frame total overrun (dropped frame) is the
animation engine's water decompression — measured and root-caused in `anim-engine.md`.

Diagnostic: temporarily enlarging VCR (e.g. `$0040`) pushes the work into real blanking — confirms the
budget relationship, but isn't a real fix (it lengthens the frame / lowers refresh).
