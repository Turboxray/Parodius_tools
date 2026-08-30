;==================================================================
;  Parodius Da! (PC Engine) -- window / HUD overlay patch
;------------------------------------------------------------------
;  Base : Parodius_Da__original.pce   (clean 1 MB original HuCard)
;  Goal : extend the playfield to the full 224 lines; HUD sits below.
;
;  Build:  go.bat   ->   pceas Parodius_patch.asm -raw -l 3 -S
;  Out  :  Parodius_patch.pce   (1 MB HuCard image)
;
;  Method: incbin the CLEAN original, then switch .bank/.org to
;          overwrite individual sites.  Section [V4] re-applies the
;          hand-made v4 hack (colour palette + HUD-BYR) as source/.db;
;          the numbered overlays [1]-[6] then extend the window on top.
;          This file is the complete change-log from the original.
;==================================================================

  .mlist
  .list

;==================================================================
; HUD / window variant select
;------------------------------------------------------------------
; Assemble this file directly           -> FULL 224-line window (default)
; Assemble Parodius_patch_stockHUD.asm  -> colour hack only, HUD untouched
; Assemble Parodius_patch_hud208.asm    -> split at line 208
; Assemble Parodius_patch_hud216.asm    -> split at line 216
;
; HUD_STOCK skips every window overlay.  A wrapper sets SPLIT_X to pick
; the split line: split line = $100 + SPLIT_X.
;
; NOTE the RCR-inclusive off-by-one: the split takes effect AFTER the
; compare line renders, so VISIBLE playfield = split_line + 1 lines:
;   stock $04 -> 197 lines, $10 -> 209, $18 -> 217, $20 -> 225.
; (Verified in-game: stock = 197, "208" build = 209 -> +12 lines over
; stock, a solid compromise.)  The public option names keep the nominal
; 208/216/224 labels.  SPLIT_X also drives the sprite bottom cull.  HUD_FULL (default, 224)
; additionally enables the 224-only overlays: [2] scroll-comp removal
; and [7] VDS -3.  The mid variants keep the stock comp/VDS for now —
; measure and split those guards if 208/216 want their own values.
;==================================================================
  .ifndef HUD_STOCK
    .ifndef SPLIT_X
HUD_FULL = 1
SPLIT_X  = $20      ; HUD split line 224 (RCR $0120)
    .endif
HUD_BGY  = $0F      ; HUD-region BG Y offset ($0C stock)
  .endif

;##################################################################
  .incbin "Parodius_Da__original.pce"
;##################################################################


;==================================================================
; [V4]  Hand-made v4 hack, layered on the original
;------------------------------------------------------------------
; (a) simple-split HUD BG Y offset: $E2C6  $0C -> $0F  (twin of [6] $E29E)
; (b) palette / colour data, banks $38-$3B  (~1110 bytes)
; v4 also moved the splits ($E1D8/$E2CE) and added a vertical comp
; ($ED20/$FFA0); those are SUPERSEDED by overlays [1][2][4] below.
;------------------------------------------------------------------
  .ifndef HUD_STOCK
  .bank 0
    .org $E2C5
    lda #HUD_BGY      ; v4: simple-split HUD BG Y ($0C->$0F)
  .endif

; ---- v4 palette / colour data (banks $38-$3B): editable colours ----
;   macros: palette_macros.inc   |   the 220 colour blocks: palette.inc
  .include "palette_macros.inc"
  .include "palette.inc"
;==================================================================


;==================================================================
; [1]  Game area = 224 lines  (HUD split at scanline 224)
;------------------------------------------------------------------
; A state-dispatched routine ($E2B0..) sets VDC reg 6 (RCR) to
; (split_line + $40) via one of three paths:
;
;     $E2B6  ldx #$20      ; split line 224   (already; used by some states)
;     $E2CD  ldx #$04/$15  ; orig $04 / v4 $15  <-- NORMAL GAMEPLAY (active)
;     $E2E5  lda $3E41     ; computed split   (scroll-tracking states; leave as-is)
;
; Normal gameplay uses the fixed $E2CD path (confirmed: reg-6 write
; fires with X=$15).  Move it to 224: ldx #$15 -> ldx #$20
; -> RCR = $0120 -> playfield lines 0..223 (224), HUD 224..239 (16).
;------------------------------------------------------------------
  .ifndef HUD_STOCK
  .bank 0
    .org $E2CD
    ldx #SPLIT_X      ; orig #$04 (v4 #$15)  (gameplay split line = $100+SPLIT_X)
  .endif


;==================================================================
; [2]  Remove vertical-scroll compensation (BG *and* all sprites)
;------------------------------------------------------------------
; The comp is ONE shared value, computed each frame at $ED1B-$ED24:
;
;     $ED1B  AD B4 27  lda $27B4
;     $ED1E  38        sec
;     $ED1F  E9 20     sbc #$20
;     $ED21  4A 4A 4A  lsr lsr lsr   ; /8   (orig comp; v4 used /16 + $FFA0)
;     $ED24  8D 73 38  sta $3873     ; <- shared vertical offset
;
; It is consumed by BOTH:
;   - BG   : $ED27-$ED35 derive $3E40 (BYR) from A.
;   - sprites: bank $3C $400F  lda #$30 / sec / sbc $3873 / sta $12
;              ($12 = sprite base Y; every sprite is offset by -$3873).
;
; With the full 224 window the comp isn't wanted.  Force the comp term
; to 0: $3873 = 0  (no sprite offset) and $3E40 = $3869-$3874 (the
; level's natural BG Y).  BG and sprites lose the same shift together.
;------------------------------------------------------------------
  .ifdef HUD_FULL    ; full 224: no comp at all
  .bank 0
    .org $ED1B
    lda #$00          ; was(orig): lda $27B4/sec/sbc #$20/lsr/lsr/lsr  (v4: sbc #$10/jsr $FFA0)
    nop               ; pad the removed 7 bytes (keep $ED24 STA $3873 in place)
    nop
    nop
    nop
    nop
    nop
    nop
  .endif

  .ifdef HUD_MID     ; mid windows: SCALED comp = ($27B4 - COMP_OFF) >> COMP_SHIFT
                     ; (wrapper sets COMP_OFF/COMP_SHIFT; *** TBD: measure ***)
                     ; >>4+ doesn't fit the 9-byte site, so shift via a helper in
                     ; the resident free run at $FF9B (v4 did the same at $FFA0).
                     ; NOTE: $FF9B-$FFBF is the only resident free space - the
                     ; planned anim-engine 60fps fix may want it too (anim-engine.md).
  .bank 0
    .org $ED1B
    lda $27B4         ; 9 bytes exactly; STA $3873 at $ED24 kept
    sec
    sbc #COMP_OFF
    jsr hud.comp.shift
    .org $FF9B
hud.comp.shift:               ; COMP_SHIFT lsr's (2..5 supported)
  .if (COMP_SHIFT >= 5)
    lsr a
  .endif
  .if (COMP_SHIFT >= 4)
    lsr a
  .endif
  .if (COMP_SHIFT >= 3)
    lsr a
  .endif
    lsr a
    lsr a
    rts
  .endif


;==================================================================
; [3]  Bottom-Y sprite cull -> match the 224 window
;------------------------------------------------------------------
; Metasprite renderer ($445D, bank $3C) clips each cel's Y at $4512:
; for display lines >=192 (SATB-Y high byte 1) it culls when
; (Y_low >= $13), where display line = 192 + Y_low.  So $13 is the
; bottom cull bound: $13 = cull_line - 192.
;
; $13 is set per-frame at $4017:
;     $4017  A9 20      lda #$20        ; line 224
;     $4019  A4 45      ldy $45
;     $401B  C0 02      cpy #$02
;     $401D  D0 02      bne $4021
;     $401F  A9 08      lda #$08        ; line 200  <-- gameplay ($45==2)
;     $4021  85 13      sta $13
;
; Gameplay ($45==2) culls at line 200, which now drops sprites that
; are visible in the taller 224 window (e.g. the ship near the
; bottom: object Y $27B4 -> screen line ~208).  Raise it to 224.
;------------------------------------------------------------------
  .ifndef HUD_STOCK
  .bank $3C
    .org $401F
    lda #SPLIT_X      ; was: lda #$08   (gameplay bottom cull 200 -> 192+SPLIT_X)
  .endif


;==================================================================
; [4]  Table-interpreter HUD split -> 224  (later / multi-split levels)
;------------------------------------------------------------------
; Levels that use the multi-split table interpreter ($3F2F negative,
; $E1A9) program their HUD split as a TYPE-0 event = a FIXED RCR write
; at $E1D7:
;     $E1D7  13 04   st1 #$04   ; orig RCR low $04 (v4 $15) -> RCR $0104/$0115
;     $E1D9  23 01   st2 #$01   ; RCR high = $01
; (Parallax bands are type >=2, table-driven via $E1EC reading the
;  per-level line table at ptr $48; e.g. lines $5F..$EF = 31..175.)
;
; This is the table-path twin of the simple-split path's $E2CD.  Raise
; the fixed HUD split to 224 to match.
;------------------------------------------------------------------
  .ifndef HUD_STOCK
  .bank 0
    .org $E1D7
    st1 #SPLIT_X      ; orig #$04 (v4 #$15)  (table-path HUD split = $100+SPLIT_X)
  .endif


;==================================================================
; [6]  Table-interpreter HUD BG Y offset -> $0F  (later levels)
;------------------------------------------------------------------
; The table-interp path sets the HUD-region BG Y scroll (BYR shadow
; $3EC1) at $E29E:  lda #$0C / sta $3EC1.  The simple-split path's twin
; ($E2C5, set in [V4]) is #$0F, but this one stayed #$0C, so the HUD
; background is misaligned on table-interp levels (e.g. level 6).
; Match it: #$0C -> #$0F.
;------------------------------------------------------------------
  .ifndef HUD_STOCK
  .bank 0
    .org $E29E
    lda #HUD_BGY      ; was: lda #$0C   (table-path HUD BG Y offset)
  .endif


;==================================================================
; [5]  *** DEBUG WARP: start on level 6 ***  (comment out for release)
;------------------------------------------------------------------
; $93 = stage counter, 0-based (level 6 = 5; 6280 zero page = $2093),
; found by diffing stage-1 vs level-6 RAM.  The stage-set routine at
; $EA95 loads $93 from a table each time a stage begins:
;     $EAA4  B9 F6 EA  lda $EAF6,Y  / $EAA7 sta $93   ; $35==0 path
;     $EAAF  B9 F2 EA  lda $EAF2,Y  / $EAB2 sta $93   ; $35!=0 path
; A new game uses $EAF6[0] = 0 (stage 1).  Force both loads to stage 5
; so every stage-start lands on level 6.  General stage-select: set the
; #$05 immediates to (target level - 1).  Toggle off for normal play.
;------------------------------------------------------------------
  ; .bank 0
  ;  .org $EAA4
  ;  lda #$06        ; was: lda $EAF6,Y   (stage-set, $35==0 path)
  ;  nop
  ;  .org $EAAF
  ;  lda #$06        ; was: lda $EAF2,Y   (stage-set, $35!=0 path)
  ;  nop
;==================================================================


;==================================================================
; [7]  Initial VDC VPR (reg $0C) VDS: $0F -> $0C  (display start 3 lines up)
;------------------------------------------------------------------
; Boot VDC-init is a table-driven loop at $E075 reading 3-byte [reg][lo][hi]
; entries from a table at $E0BA.  VPR (reg $0C) entry is at $E0CF = "0C 02 0F"
; (VSW=$02, VDS=$0F).  The VDS high byte sits at $E0D1; reduce it by 3:
; $0F -> $0C  ->  VPR = $0C02.
;------------------------------------------------------------------
  .ifdef HUD_FULL    ; 224 only (display start 3 lines up; mid TBD)
  .bank 0
    .org $E0D1
    .db $0C           ; VDS: $0F -> $0C
  .endif
;==================================================================
