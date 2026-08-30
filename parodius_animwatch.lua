--Parodius VRAM-copy watcher (Mesen2 Lua, PCE)
--Hooks the script engine's $FE event handler at $C168 (bank $01, MPR6) and
--logs every VRAM->VRAM copy it performs: source, dest, size, script slot.
--Event format: [FE][??][src_lo hi][dst_lo hi][count x16 words]  (ZP $08 = ptr)
--Log: parodius_animwatch.txt (append; '=== run start ===' per run)

local LOG_PATH = "D:/Projects/hacking/Parodius/parodius_animwatch.txt"
local log_file = io.open(LOG_PATH, "a")
local function flog(s)
  if log_file then log_file:write(s .. "\n"); log_file:flush() end
end
flog("=== run start ===")

local frames = 0
local copies = 0

local function rd(a)  return emu.read(a, emu.memType.pceMemory, false) end
local function rd16(a) return emu.read16(a, emu.memType.pceMemory, false) end

local function on_fe()
  local ptr  = rd16(0x2008)          -- ZP $08/$09 = event pointer
  local src  = rd16(ptr + 2)
  local dst  = rd16(ptr + 4)
  local cnt  = rd(ptr + 6)
  local slot = rd(0x20CE)            -- $CE = current script slot (X)
  copies = copies + 1
  flog(string.format("F=%d slot=%d VCOPY src=$%04X.w dst=$%04X.w words=%d",
       frames, slot, src, dst, cnt * 16))
end

-- $C25C = decompress-from-ROM event: [bank][p1][dst_lo hi][src_lo hi]
local function on_rom()
  local ptr  = rd16(0x2008)
  local bank = rd(ptr)               -- event byte 0 = ROM bank (A at entry)
  local p1   = rd(ptr + 1)
  local dst  = rd16(ptr + 2)
  local src  = rd16(ptr + 4)
  local slot = rd(0x20CE)
  copies = copies + 1
  flog(string.format("F=%d slot=%d ROMDEC bank=$%02X p1=$%02X dst=$%04X.w src=$%04X",
       frames, slot, bank, p1, dst, src))
end

local function on_frame()
  frames = frames + 1
  emu.drawString(8, 8, string.format("frames %d  vram-copies %d", frames, copies),
                 0xFFFFFF, 0xA0000000)
end

emu.addMemoryCallback(on_fe, emu.callbackType.exec, 0xC168, 0xC168,
                      emu.cpuType.pce, emu.memType.pceMemory)
emu.addMemoryCallback(on_rom, emu.callbackType.exec, 0xC25C, 0xC25C,
                      emu.cpuType.pce, emu.memType.pceMemory)
emu.addEventCallback(on_frame, emu.eventType.endFrame)

emu.displayMessage("Script", "animwatch: logging $FE VRAM copies -> parodius_animwatch.txt")
