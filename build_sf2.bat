@echo off
rem Regenerate the asset include from the trace corpus, then build the
rem 2.5 MB SF2-mapper expansion ROM.
set PATH=%PATH%;c:\huc\bin

python census_to_streams.py
python pce_gfx_export.py Parodius_Da__original.pce parodius_gfxtrace.txt parodius_extra_streams.txt
if errorlevel 1 exit /b 1

del Parodius_SF2.pce 2>nul
pceas Parodius_SF2.asm --sf2 -raw -l 0 > build_Parodius_SF2.log
if not exist Parodius_SF2.pce (
  echo FAILED - see build_Parodius_SF2.log
  exit /b 1
)
python zero_upper.py
echo built Parodius_SF2.pce
