@echo off
rem Build all HUD variants from the single Parodius_patch.asm - the variant
rem equates are written to variant.inc per invocation (pceas has no -D).
rem   Parodius_patch_224h.pce          full 224-line window
rem   Parodius_patch_stock_height.pce  colour hack only
rem   Parodius_patch_208h.pce          208-line window
rem   Parodius_patch_216h.pce          216-line window
set PATH=%PATH%;c:\huc\bin

(echo ; full 224 default)> variant.inc
call :build Parodius_patch_224h
if errorlevel 1 exit /b 1

(echo HUD_STOCK = 1)> variant.inc
call :build Parodius_patch_stock_height
if errorlevel 1 exit /b 1

(echo HUD_MID = 1& echo SPLIT_X = $10& echo COMP_OFF = $20& echo COMP_SHIFT = 4)> variant.inc
call :build Parodius_patch_208h
if errorlevel 1 exit /b 1

(echo HUD_MID = 1& echo SPLIT_X = $18& echo COMP_OFF = $20& echo COMP_SHIFT = 5)> variant.inc
call :build Parodius_patch_216h
if errorlevel 1 exit /b 1

(echo ; full 224 default)> variant.inc
echo all variants built.
exit /b 0

:build
del %1.pce 2>nul
pceas Parodius_patch.asm --raw -l 0 -o %1.pce > build_%1.log
if not exist %1.pce (
  echo FAILED: %1  - see build_%1.log
  exit /b 1
)
echo built %1.pce
exit /b 0
