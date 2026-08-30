--Parodius vblank-profiler (Mesen2 Lua, PCE)
--Stamps the scanline (as "lines since the vblank IRQ") at each subcall of the
--full vblank handler, one log line per frame, to find which call balloons on
--the every-9th "heavy" frame.  Call sequence (from the $E0DE disassembly):
--  $E102 start -> $E259 -> $4035 -> $E3FE(SATB mutex) -> $C04E(audio)
--  -> $E631 -> $E4D7(dispatch) -> $4000(game logic) -> $E30B -> $E171 done
--Log: parodius_framewatch2.txt (append; '=== run start ===' per run)

local LOG_PATH = "D:/Projects/hacking/Parodius/parodius_framewatch2a.txt"
local log_file = io.open(LOG_PATH, "a")
local function flog(s)
  if log_file then log_file:write(s .. "\n"); log_file:flush() end
end
flog("=== run start ===")

local LINES = 263          -- lines per frame (close enough on both ROMs)
local frames = 0
local t0     = nil         -- absolute line count at $E102 (this frame's IRQ)
local stamps = {}          -- name -> lines-since-IRQ (first hit per frame)
local lite   = false

-- stamp points: name -> logical addr
local POINTS = {
  { "e259", 0xE259 }, { "p4035", 0x4035 }, { "mtx",  0xE3FE },
  { "c04e", 0xC04E }, { "e631", 0xE631 }, { "e4d7", 0xE4D7 },
  { "p4000", 0x4000 }, { "e30b", 0xE30B }, { "done", 0xE171 },
}

local function scanline()
  local ok, st = pcall(emu.getState)
  if not ok or st == nil then return -1 end
  return st["ppu.scanline"] or st["vdc.scanline"] or -1
end

local function now() return frames * LINES + scanline() end

local function on_start()               -- $E102: full-path vblank work begins
  t0 = now()
  stamps = {}
end

local function make_stamp(name)
  return function()
    if t0 and stamps[name] == nil then
      local v = now() - t0
      if v < 0 then v = v + LINES end   -- frame counter lags the scanline wrap
      stamps[name] = v
    end
  end
end

local function on_lite() lite = true end

local function zp(a) return emu.read(0x2000 + a, emu.memType.pceMemory, false) end

local function on_frame()
  frames = frames + 1
  local parts = {}
  for _, p in ipairs(POINTS) do
    local v = stamps[p[1]]
    parts[#parts + 1] = p[1] .. (v ~= nil and ("+" .. v) or "+-")
  end
  flog(string.format("F=%d %s $39=%02X $4A=%02X%s",
       frames, table.concat(parts, " "), zp(0x39), zp(0x4A),
       lite and "  LITE" or ""))
  lite = false
end

emu.addMemoryCallback(on_start, emu.callbackType.exec, 0xE102, 0xE102,
                      emu.cpuType.pce, emu.memType.pceMemory)
for _, p in ipairs(POINTS) do
  emu.addMemoryCallback(make_stamp(p[1]), emu.callbackType.exec, p[2], p[2],
                        emu.cpuType.pce, emu.memType.pceMemory)
end
emu.addMemoryCallback(on_lite, emu.callbackType.exec, 0xE189, 0xE189,
                      emu.cpuType.pce, emu.memType.pceMemory)
emu.addEventCallback(on_frame, emu.eventType.endFrame)

emu.displayMessage("Script", "framewatch2: per-call vblank profile -> parodius_framewatch2.txt")
