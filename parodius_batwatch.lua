--Parodius BAT diff-watcher v2 (Mesen2 Lua, PCE)
--Snapshots the BAT (VRAM words $0000-$07FF) every frame and logs changed
--cells: the scroll-seam columns and their tile values. Those values are
--then searched in ROM offline to locate the map/metatile data directly.
--(v1's VRAM write-callbacks never fire in Mesen for VDC port writes.)
--Log: parodius_batwatch.txt

local LOG_PATH = "D:/Projects/hacking/Parodius/parodius_batwatch.txt"
local BAT_WORDS = 0x1000         -- 128x32 map (stage 1 MWR $0030) - FULL BAT
local MAX_CHANGED = 96           -- per frame: more than this = full redraw, summarize

local log_file = io.open(LOG_PATH, "a")
local function flog(s)
  if log_file then log_file:write(s .. "\n"); log_file:flush() end
end
flog("=== run start (v2 diff) ===")

local frames = 0
local prev = nil
local events = 0

local function read_bat()
  local t = {}
  for w = 0, BAT_WORDS - 1 do
    t[w] = emu.read16(w * 2, emu.memType.pceVideoRam, false)
  end
  return t
end

local function on_frame()
  frames = frames + 1
  local cur = read_bat()
  if prev ~= nil then
    local changed = {}
    for w = 0, BAT_WORDS - 1 do
      if cur[w] ~= prev[w] then
        changed[#changed + 1] = w
      end
    end
    if #changed > 0 then
      events = events + 1
      if #changed > MAX_CHANGED then
        flog(string.format("F=%d FULLDRAW %d cells changed", frames, #changed))
      else
        -- group by column (BAT is 64 wide: col = w & 63, row = w >> 6)
        local parts = {}
        for _, w in ipairs(changed) do
          parts[#parts + 1] = string.format("%04X:%04X", w, cur[w])
        end
        flog(string.format("F=%d n=%d %s", frames, #changed,
             table.concat(parts, " ")))
      end
    end
  end
  prev = cur
  emu.drawString(8, 8, string.format("batdiff F=%d events=%d", frames, events),
                 0xFFFFFF, 0xA0000000)
end

emu.addEventCallback(on_frame, emu.eventType.endFrame)
emu.displayMessage("Script", "batdiff v2: per-frame BAT diffs -> parodius_batwatch.txt")
