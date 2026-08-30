@echo off
rem Build all HUD variants (ROM names match the distribution convention):
rem   Parodius_patch_224h.pce          full 224-line window
rem   Parodius_patch_stock_height.pce  colour hack only
rem   Parodius_patch_208h.pce          208-line window
rem   Parodius_patch_216h.pce          216-line window
set PATH=%PATH%;c:\huc\bin

for %%B in (Parodius_patch_224h Parodius_patch_stock_height Parodius_patch_208h Parodius_patch_216h) do (
  del %%B.pce 2>nul
  pceas %%B.asm -raw -l 0 > build_%%B.log
  if not exist %%B.pce (
    echo FAILED: %%B  - see build_%%B.log
    exit /b 1
  )
  echo built %%B.pce
)
echo all variants built.
