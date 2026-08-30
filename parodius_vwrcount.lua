--Parodius VWR write counter (Mesen2 Lua, PCE)
--Counts VDC data-port writes ($0002/$0003) made by the script engine (PC in
--$C000-$DFFF, bank $01) per frame, with first/last scanline of the burst.
--Gives the exact payload size of each decompress event.
--Log: parodius_vwrcount.txt

local LOG_PATH = "D:/Projects/hacking/Parodius/parodius_vwrcount.txt"
local log_file = io.open(LOG_PATH, "a")
local function flog(s)
  if log_file then log_file:write(s .. "\n"); log_file:flush() end
end
flog("=== run start ===")

local frames = 0
local nbytes = 0
local first_line, last_line = -1, -1

local function scanline()
  local ok, st = pcall(emu.getState)
  if not ok or st == nil then return -1 end
  return st["ppu.scanline"] or st["vdc.scanline"] or -1
end

local function on_write(addr, value)
  local ok, st = pcall(emu.getState)
  if not ok or st == nil then return end
  local pc = st["cpu.pc"] or 0
  if pc < 0xC000 or pc >= 0xE000 then return end   -- script engine only
  nbytes = nbytes + 1
  local l = st["ppu.scanline"] or st["vdc.scanline"] or -1
  if first_line < 0 then first_line = l end
  last_line = l
end

local function on_frame()
  frames = frames + 1
  if nbytes > 0 then
    flog(string.format("F=%d bytes=%d words=%d lines=%d..%d",
         frames, nbytes, nbytes // 2, first_line, last_line))
  end
  nbytes = 0; first_line = -1; last_line = -1
  emu.drawString(8, 8, string.format("frames %d", frames), 0xFFFFFF, 0xA0000000)
end

emu.addMemoryCallback(on_write, emu.callbackType.write, 0x0002, 0x0003,
                      emu.cpuType.pce, emu.memType.pceMemory)
emu.addEventCallback(on_frame, emu.eventType.endFrame)

emu.displayMessage("Script", "vwrcount: engine VWR bytes/frame -> parodius_vwrcount.txt")
