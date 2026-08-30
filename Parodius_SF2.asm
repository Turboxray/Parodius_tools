;==================================================================
;  Parodius Da! -- SF2-mapper expansion build (2.5 MB / 20 Mbit)
;------------------------------------------------------------------
;  Base : the full hack (Parodius_rebuild.asm: colours + 224 window)
;  Adds : every graphics stream stored uncompressed in expansion banks
;         $80+ (pce_sf2_mapper_prep.py extract, from stream_manifest.txt)
;         + a load hook that serves them instead of decompressing.
;
;  Build:  build_sf2.bat  ->  pceas Parodius_SF2.asm --sf2 -raw
;  Out  :  Parodius_SF2.pce  (2.5 MB StreetFighterII-mapper HuCard)
;
;  Mapper: banks $00-$3F fixed; $40-$7F is a window into 4 pages
;  selected by writing $1FF0-$1FF3 (reachable at $FFF0-$FFF3 via the
;  always-mapped MPR7 = bank $00).  pceas file banks $80-$BF appear
;  in the window as MPR banks $40-$7F while page 1 is latched, etc.
;
;  Result: the game's chronic dropped frames are gone (stock loses 1
;  frame in 9 re-decompressing the water; this build measures 0 lag /
;  eff 60.0 in gameplay).
;==================================================================

; SF2 page latch (write-only; value ignored, address selects page)
sf2.latch = $FFF0            ; +0..+3 = page 0..3

  .include "Parodius_rebuild.asm"

;==================================================================
; Load hook: divert ROMDEC events to the stored uncompressed assets
;------------------------------------------------------------------
; The engine's event dispatcher at $C159 (bank $01, MPR6) reaches the
; decompressor via "JMP $C25C" at $C164 with A = event bank byte,
; Y = 0, ZP $08/$09 -> event [bank][p1][dst.w][src].  We intercept:
;
;   [bank][src][p1] not in table -> original decompressor (should never
;      happen for known content: flips are stored as pre-flipped assets)
;   match -> set MAWR from the event, latch SF2 page, map the asset
;      bank, stream the stored data (~47 cyc/word vs ~200/word
;      decompressing), advance the event ptr, rejoin at $C159.
;   NOTE: build_sf2.bat ZEROES the original upper 512K ($080000-$0FFFFF)
;      after assembly - the census proved it holds only graphics streams
;      (all served from the expansion) and $FF padding.
;
; The springboard lives in the resident free run at $FF9B (always
; mapped); the main hook in fixed bank $23's free space (always
; reachable - the SF2 window only covers banks $40-$7F).  While
; diverting: MPR2 = bank $23 (code), MPR3 = LUT bank $80 (page 1),
; MPR4 = asset bank.  No interrupt masking is needed (see the note at
; sf2.hook.main); page 0 is restored on every exit path.  ZP $00-$07
; scratch = the decompressor's own scratch (only touched when the
; decompressor won't run, or before it initialises them).
;==================================================================

;------------------------------------------------------------------
; patch: $C164 "JMP $C25C" -> springboard
;------------------------------------------------------------------
  .bank $01
    .org $C164
    jmp sf2.hook.entry

;------------------------------------------------------------------
; springboard (resident bank 0, free run $FF9B-$FFBF)
;------------------------------------------------------------------
  .bank 0
    .org $FF9B
sf2.hook.entry:             ; A = event bank byte, Y = 0
    pha                     ; keep event bank for the fall-through path
    tma #$02
    pha
    lda #$23
    tam #$02                ; hook code at $4000
    jsr sf2.hook.main       ; returns C=1 if the event was diverted
    pla
    tam #$02
    pla                     ; A = event bank byte again
    cly                     ; $C25C expects Y=0
  bcs .diverted
    jmp $C25C               ; not ours: original decompressor
.diverted
    jmp $C159               ; event consumed: next token ($FF -> rts)

;------------------------------------------------------------------
; main hook (fixed bank $23, free space after $46AF)
;------------------------------------------------------------------
  .bank $23
    .org $46AF

sf2.hook.main:              ; in: ($08) = event, Y = 0  (A is CLOBBERED by the
                            ; springboard's bank map - read the event directly)
                            ; out: C=1 diverted / C=0 pass through
                            ; ZP scratch $00-$07 = the decompressor's own
    lda [$08]               ; event bank byte
    sta <$00
    ldy #$01
    lda [$08],y
    sta <$01                ; event p1 - flips match pre-flipped assets

    tma #$03                ; NOTE: no SEI. The page latch is IRQ-safe because
    pha                     ; the census proved banks $40-$7F hold ONLY gfx
                            ; streams (+$FF pad) - all data any IRQ handler
                            ; (TIQ pages its own banks + restores) could read
                            ; lives under $40, latch-independent. And no IRQ
                            ; path writes MAWR ($5797/$55DC verified), so the
                            ; copy itself needs no masking either.
    lda #$40                ; WINDOW bank $40 + page 1 = file bank $80 (LUT).
    tam #$03                ; (Mapping the raw $80+ bank number reads open
    stz sf2.latch+1         ; bus - the SF2 window is banks $40-$7F only.)

    ldx #sf2.bucket.count-1
.bfind
    lda sf2.bucket.bank,x
    cmp <$00
  beq .bfound
    dex
  bpl .bfind
  bra .unwind               ; no bucket for this event bank

.bfound
    lda sf2.bucket.ptr.lo,x
    sta <$02
    lda sf2.bucket.ptr.hi,x
    sta <$03                ; $02/$03 -> [count][records...]
    lda [$02]
    sta <$00                ; remaining record count
    inc <$02
  bne .scan
    inc <$03

.scan                       ; record: +0 src.lo +1 src.hi +2 (p1<<4)|page
    ldy #$04                ;         +3 window bank +4 addr.lo +5 addr.hi
    lda [$08],y             ;         +6 len.lo +7 len.hi
    cmp [$02]               ; event src.lo
  bne .next
    ldy #$05
    lda [$08],y             ; event src.hi
    ldy #$01
    cmp [$02],y
  bne .next
    ldy #$02
    lda [$02],y             ; record (p1<<4)|page
    lsr a
    lsr a
    lsr a
    lsr a
    cmp <$01                ; record p1 == event p1?
  beq .found
.next
    lda <$02
    clc
    adc #$08
    sta <$02
  bcc .n0
    inc <$03
.n0
    dec <$00
  bne .scan

.unwind
    stz sf2.latch           ; page 0 back
    pla
    tam #$03
.pass
    clc
  rts

.found                      ; [$02] -> matched record
.divert                     ; harvest the record to ZP
    ldy #$02                ; BEFORE touching the latch (the record is in
    lda [$02],y             ; the page-1 LUT bank).
    and #$0F                ; low nibble = SF2 page (high = p1)
    sta <$06                ; SF2 page
    iny
    lda [$02],y
    sta <$07                ; asset bank
    iny
    lda [$02],y
    pha                     ; addr.lo
    iny
    lda [$02],y
    pha                     ; addr.hi
    iny
    lda [$02],y
    sta <$04                ; len.lo
    iny
    lda [$02],y             ; len.hi
    lsr a
    sta <$05
    lda <$04
    ror a
    sta <$04                ; $04/$05 = word count (len/2; len is even)
    pla
    sta <$03                ; $02/$03 = data ptr
    pla
    sta <$02

    tma #$04
    sta <$01                ; save MPR4
    lda <$07                ; asset file bank -> window bank:
    and #$3F                ;   $40 | (bank & $3F), page latch picks the 512KB
    ora #$40
    tam #$04                ; asset data at $8000
    ldy <$06
    sta sf2.latch,y         ; latch the asset's own SF2 page (value ignored)

    ldy #$02                ; repurpose $06/$07 = running VRAM dst (event dst)
    lda [$08],y
    sta <$06
    iny
    lda [$08],y
    sta <$07

    cly
; ------------------------------------------------------------------
; CHUNKED copy: <=64 words per SEI window, MAWR re-established every
; chunk (an interrupt in the CLI gap can clobber MAWR via the lite
; path's SATB work).  IRQ handlers reachable in the gaps touch only
; fixed banks (objects $20-$23, DDA samples $24-$2B), so the non-0
; page latch is safe across them; CR's auto-increment bits live in
; its high byte, which no handler writes.  Keeps RCR (HUD split) and
; TIQ (DDA) on time during big loads: no bar bounce, no stutter.
; ------------------------------------------------------------------
.chunk
    jsr $E6C5               ; auto-increment +1 (cheap insurance)
    jsr $E6B9               ; select MAWR
    lda <$06
    sta $0002
    lda <$07
    sta $0003               ; MAWR = running dst
    jsr $E6B1               ; select VWR data port
    ldx #$40                ; up to 64 words per window
.copy
    lda [$02],y
    sta $0002
    iny
    lda [$02],y
    sta $0003
    iny
  bne .nowrap
    inc <$03
.nowrap
    inc <$06                ; running dst++
  bne .nodst
    inc <$07
.nodst
    lda <$04                ; 16-bit word count--
  bne .declo
    dec <$05
.declo
    dec <$04
    lda <$04
    ora <$05
  beq .copydone
    dex
  bne .copy
  bra .chunk                ; chunk boundary: re-establish MAWR (insurance)
.copydone

    lda <$01
    tam #$04                ; restore MPR4
    stz sf2.latch           ; page 0 back
    pla
    tam #$03                ; restore MPR3

.consume
    lda <$08                ; consume the 6-byte event
    clc
    adc #$06
    sta <$08
  bcc .done
    inc <$09
.done
    sec
  rts

;==================================================================
; Expansion: uncompressed graphics assets + lookup tables
;==================================================================
  .include "Parodius_SF2_assets.inc"

;==================================================================
; Pad the image to the full 2.5 MB (banks $00-$13F)
;==================================================================
  .bank $13F, "pad"
    .org $5FFF
    .db 0
