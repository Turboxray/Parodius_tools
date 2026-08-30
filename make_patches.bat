@echo off
rem Build IPS + xdelta patches for every built HUD variant against the clean
rem original.  Both ROMs are headerless 1 MB images.
rem Usage:  make_patches.bat [version] [nozip]     (default version: 1_0)
rem   make_patches.bat            - patches + distro zip
rem   make_patches.bat 1_1        - patches + distro zip as v1_1
rem   make_patches.bat 1_1 nozip  - patches only (skip the zip)
rem   outputs: Parodius_patch_v<ver>_224h.ips/.xdelta          (full 224 window)
rem            Parodius_patch_v<ver>_stock_height.ips/.xdelta  (colour only)
rem            Parodius_patch_v<ver>_208h.ips/.xdelta          (208 window)
rem            Parodius_patch_v<ver>_216h.ips/.xdelta          (216 window)
setlocal
set ORIG=Parodius_Da__original.pce
set TOOLS=D:\Projects\tools
set VER=1_0
set MAKEZIP=1
if /i "%~1"=="nozip" (
  set MAKEZIP=0
) else (
  if not "%~1"=="" set VER=%~1
)
if /i "%~2"=="nozip" set MAKEZIP=0

set MADE=0
call :make Parodius_patch_224h         Parodius_patch_v%VER%_224h
call :make Parodius_patch_stock_height Parodius_patch_v%VER%_stock_height
call :make Parodius_patch_208h         Parodius_patch_v%VER%_208h
call :make Parodius_patch_216h         Parodius_patch_v%VER%_216h
if %MADE%==0 (
  echo no builds found - run go.bat or build_all.bat first.
  exit /b 1
)
if %MAKEZIP%==1 (
  powershell -NoProfile -Command "Compress-Archive -Force -Path 'Parodius_patch_v%VER%*.ips','Parodius_patch_v%VER%*.xdelta','readme.txt' -DestinationPath 'Parodius_patch_v%VER%.zip'"
  echo done: Parodius_patch_v%VER%.zip
) else (
  echo done ^(zip skipped^).
)
pause
exit /b 0

:make
if not exist %1.pce exit /b 0
"%TOOLS%\Lunar IPS.exe" -CreateIPS "%2.ips" %ORIG% %1.pce
"%TOOLS%\xdelta3.exe" -f -e -s %ORIG% %1.pce "%2.xdelta"
echo   %2.ips / %2.xdelta
set MADE=1
exit /b 0
