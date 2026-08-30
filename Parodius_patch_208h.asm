; 208-line window variant: colors + HUD split at line 208.
; Comp values play-tested through most of the game (2026-08-24) - good.
HUD_MID    = 1
SPLIT_X    = $10    ; split line 208 (RCR $0110)
COMP_OFF   = $20    ; comp = ($27B4 - $20) >> 4
COMP_SHIFT = 4
  .include "Parodius_patch.asm"
