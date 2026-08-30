--Parodius gfx-decompression tracer (Mesen2 Lua, PCE)
--Logs every script-engine event (ROMDEC decompress / VCOPY) with stage + frame,
--and for ROMDEC events also dumps the exact VRAM bytes the event produced -
--ground truth for validating the offline Python decoder (pce_gfx_decode.py).
--Play through levels with this loaded to build the corpus.
--Log: parodius_gfxtrace.txt (append; '=== run start ===' per run)

local LOG_PATH = "D:/Projects/hacking/Parodius/parodius_gfxtrace.txt"
local MAX_DUMP = 4096          -- max bytes of VRAM dumped per event

local log_file = io.open(LOG_PATH, "a")
local function flog(s)
  if log_file then log_file:write(s .. "\n"); log_file:flush() end
end
flog("=== run start ===")

local frames = 0
local ev = nil                 -- in-flight ROMDEC event
local nbytes = 0               -- VDC data bytes written by the engine during ev

local function rd(a)  return emu.read(a, emu.memType.pceMemory, false) end
local function rd16(a) return emu.read16(a, emu.memType.pceMemory, false) end
local function vram(w) -- read VRAM word
  return emu.read16(w * 2, emu.memType.pceVideoRam, false)
end

-- $C25C: ROMDEC event start
local function on_romdec()
  local ptr = rd16(0x2008)
  ev = { bank = rd(ptr), p1 = rd(ptr + 1), dst = rd16(ptr + 2),
         src = rd16(ptr + 4), slot = rd(0x20CE), frame = frames,
         stage = rd(0x2093) }
  nbytes = 0
end

-- count engine writes to the VDC data port while an event is in flight
local function on_write(addr, value)
  if ev == nil then return end
  local ok, st = pcall(emu.getState)
  if not ok or st == nil then return end
  local pc = st["cpu.pc"] or 0
  if pc >= 0xC000 and pc < 0xE000 then nbytes = nbytes + 1 end
end

-- $C35D: ROMDEC event finished ($FF end-token handler)
local function on_end()
  if ev == nil then return end
  local words = math.floor(nbytes / 2)
  flog(string.format(
    "ROMDEC F=%d stage=$%02X slot=%d bank=$%02X p1=$%02X dst=$%04X.w src=$%04X words=%d",
    ev.frame, ev.stage, ev.slot, ev.bank, ev.p1, ev.dst, ev.src, words))
  local dumpw = math.min(words, math.floor(MAX_DUMP / 2))
  local line = {}
  for i = 0, dumpw - 1 do
    line[#line + 1] = string.format("%04X", vram(ev.dst + i))
    if #line == 16 then flog("  " .. table.concat(line, " ")); line = {} end
  end
  if #line > 0 then flog("  " .. table.concat(line, " ")) end
  if dumpw < words then flog("  (truncated at " .. dumpw .. " words)") end
  ev = nil
end

-- $C168: VCOPY event (log only; output = VRAM src copy, no dump needed)
local function on_vcopy()
  local ptr = rd16(0x2008)
  flog(string.format(
    "VCOPY  F=%d stage=$%02X slot=%d src=$%04X.w dst=$%04X.w words=%d",
    frames, rd(0x2093), rd(0x20CE), rd16(ptr + 2), rd16(ptr + 4),
    rd(ptr + 6) * 16))
end

local function on_frame()
  frames = frames + 1
  emu.drawString(8, 8, string.format("gfxtrace F=%d", frames), 0xFFFFFF, 0xA0000000)
end

emu.addMemoryCallback(on_romdec, emu.callbackType.exec, 0xC25C, 0xC25C,
                      emu.cpuType.pce, emu.memType.pceMemory)
emu.addMemoryCallback(on_end, emu.callbackType.exec, 0xC35D, 0xC35D,
                      emu.cpuType.pce, emu.memType.pceMemory)
emu.addMemoryCallback(on_vcopy, emu.callbackType.exec, 0xC168, 0xC168,
                      emu.cpuType.pce, emu.memType.pceMemory)
emu.addMemoryCallback(on_write, emu.callbackType.write, 0x0002, 0x0003,
                      emu.cpuType.pce, emu.memType.pceMemory)
emu.addEventCallback(on_frame, emu.eventType.endFrame)

emu.displayMessage("Script", "gfxtrace: events + VRAM ground truth -> parodius_gfxtrace.txt")
