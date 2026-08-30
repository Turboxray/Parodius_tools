@echo off
rem Extract assets from the ROM, build
rem the 2.5 MB SF2-mapper expansion, blank the dead original gfx region.
set PATH=%PATH%;c:\huc\bin

python pce_gfx.py extract Parodius_Da__original.pce
if errorlevel 1 exit /b 1

(echo ; full 224 default)> variant.inc
del Parodius_SF2.pce 2>nul
pceas Parodius_SF2.asm --sf2 -raw -l 0 > build_Parodius_SF2.log
if not exist Parodius_SF2.pce (
  echo FAILED - see build_Parodius_SF2.log
  exit /b 1
)
python pce_gfx.py zero
echo built Parodius_SF2.pce