; 216-line window variant: colors + HUD split at line 216.
; Comp values play-tested through most of the game (2026-08-24) - good.
HUD_MID    = 1
SPLIT_X    = $18    ; split line 216 (RCR $0118)
COMP_OFF   = $20    ; comp = ($27B4 - $20) >> 5
COMP_SHIFT = 5
  .include "Parodius_patch.asm"
