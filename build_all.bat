@echo off
rem Build ALL ROMs from the single sources, one per window-height variant:
rem   patch (1 MB):  Parodius_patch_{224h,stock_height,208h,216h}.pce
rem   SF2   (2.5MB): Parodius_SF2_{224h,stock_height,208h,216h}.pce
rem Variant equates are written to variant.inc per invocation (pceas has
rem no -D). SF2 assets are extracted once; each SF2 image gets its dead
rem original gfx region zeroed.
set PATH=%PATH%;c:\huc\bin

python pce_sf2_mapper_prep.py extract Parodius_Da__original.pce
if errorlevel 1 exit /b 1

call :variant_224h
call :build_patch Parodius_patch_224h
if errorlevel 1 exit /b 1
call :build_sf2 Parodius_SF2_224h
if errorlevel 1 exit /b 1

call :variant_stock
call :build_patch Parodius_patch_stock_height
if errorlevel 1 exit /b 1
call :build_sf2 Parodius_SF2_stock_height
if errorlevel 1 exit /b 1

call :variant_208h
call :build_patch Parodius_patch_208h
if errorlevel 1 exit /b 1
call :build_sf2 Parodius_SF2_208h
if errorlevel 1 exit /b 1

call :variant_216h
call :build_patch Parodius_patch_216h
if errorlevel 1 exit /b 1
call :build_sf2 Parodius_SF2_216h
if errorlevel 1 exit /b 1

call :variant_224h
echo all builds complete.
exit /b 0

:variant_224h
(echo ; full 224 default)> variant.inc
exit /b 0
:variant_stock
(echo HUD_STOCK = 1)> variant.inc
exit /b 0
:variant_208h
(echo HUD_MID = 1& echo SPLIT_X = $10& echo COMP_OFF = $20& echo COMP_SHIFT = 4)> variant.inc
exit /b 0
:variant_216h
(echo HUD_MID = 1& echo SPLIT_X = $18& echo COMP_OFF = $20& echo COMP_SHIFT = 5)> variant.inc
exit /b 0

:build_patch
del %1.pce 2>nul
pceas Parodius_rebuild.asm --raw -l 0 -o %1.pce > build_%1.log
if not exist %1.pce (
  echo FAILED: %1  - see build_%1.log
  exit /b 1
)
echo built %1.pce
exit /b 0

:build_sf2
del %1.pce 2>nul
pceas Parodius_SF2.asm --sf2 -raw -l 0 -o %1.pce > build_%1.log
if not exist %1.pce (
  echo FAILED: %1  - see build_%1.log
  exit /b 1
)
python pce_sf2_mapper_prep.py zero %1.pce
echo built %1.pce
exit /b 0
