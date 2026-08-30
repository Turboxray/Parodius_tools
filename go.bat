@echo off
set PATH=%PATH%;c:\huc\bin
(echo ; full 224 default)> variant.inc
del Parodius_patch_224h.pce 2>nul
pceas Parodius_patch.asm --raw -l 3 -S -o Parodius_patch_224h.pce > log.txt
type log.txt
pause
