@echo off
set PATH=%PATH%;c:\huc\bin
python pce_sf2_mapper_prep.py check Parodius_Da__original.pce
if errorlevel 1 exit /b 1
(echo ; full 224 default)> variant.inc
del Parodius_patch_224h.pce 2>nul
pceas Parodius_rebuild.asm --raw -l 3 -S -o Parodius_patch_224h.pce > log.txt
type log.txt
pause
