; ================================================================
; palette_macros.inc - colour-packing macros for Parodius palettes
;   Include this BEFORE palette.inc.
;
;   rgb(r,g,b)  -> a 9-bit PCE colour (GGGRRRBBB); r,g,b each 0..7.
;                  palette.inc emits a #RRGGBB swatch comment above each
;                  16-colour group so a VS Code colour plugin previews it.
;   pal8 c0..c7 -> packs 8 colours into the game's block layout:
;                  one mask byte (bit8 of each colour, colour0 = MSB)
;                  followed by the 8 low bytes.
; ================================================================

rgb  .func (((\2)<<6)|((\1)<<3)|(\3))

pal8 .macro
     .db (((\1>>8)&1)<<7)|(((\2>>8)&1)<<6)|(((\3>>8)&1)<<5)|(((\4>>8)&1)<<4)|(((\5>>8)&1)<<3)|(((\6>>8)&1)<<2)|(((\7>>8)&1)<<1)|((\8>>8)&1)
     .db (\1&$FF),(\2&$FF),(\3&$FF),(\4&$FF),(\5&$FF),(\6&$FF),(\7&$FF),(\8&$FF)
     .endm
