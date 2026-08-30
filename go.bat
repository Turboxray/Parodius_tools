@echo off
set PATH=%PATH%;c:\huc\bin
del Parodius_patch_224h.pce 2>nul
pceas Parodius_patch_224h.asm -raw -l 3 -S > log.txt
type log.txt
pause
