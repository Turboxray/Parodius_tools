--Parodius frame-stall watcher (Mesen2 Lua, PCE)
--Counts vblank "lite path" (lag-frame) entries at $E189 vs total frames and
--logs the period between hits, to confirm/refute the 1-in-10 stall theory.
--Also samples the scanline at $E171 (STZ $33 = end of full vblank work) so we
--can see how far past vblank the ISR is finishing on normal frames.
--Run on BOTH the patched and the original ROM and compare.

local frames     = 0
local lite_hits  = 0
local last_lite  = -1      -- frame number of the previous lite hit
local last_gap   = 0
local done_line  = -1      -- scanline where $E171 last executed
local worst_line = -1
local gaps       = {}      -- recent lite periods (for the overlay)

-- File log: every LITE hit + a summary line every 300 frames (~5s), appended,
-- with a run header so multiple runs / ROMs can share the file.
local LOG_PATH = "D:/Projects/hacking/Parodius/parodius_framewatch_test.txt"
local log_file = io.open(LOG_PATH, "a")
local function flog(s)
  if log_file then log_file:write(s .. "\n"); log_file:flush() end
end
flog("=== run start ===")

local function scanline()
  local ok, st = pcall(emu.getState)
  if not ok or st == nil then return -1 end
  return st["ppu.scanline"] or st["vdc.scanline"] or -1
end

-- $E189 = lag-frame lite path (vblank IRQ arrived while $33 still set)
local function on_lite()
  lite_hits = lite_hits + 1
  if last_lite >= 0 then
    last_gap = frames - last_lite
    table.insert(gaps, last_gap)
    if #gaps > 12 then table.remove(gaps, 1) end
  end
  last_lite = frames
  local line = string.format("LITE frame=%d gap=%d (scanline %d)",
                             frames, last_gap, scanline())
  emu.log(line)
  flog(line)
end

-- $E171 = STZ $33: full vblank handler finished its work
local function on_done()
  done_line = scanline()
  if done_line > worst_line then worst_line = done_line end
end

local function on_frame()
  frames = frames + 1
  -- quiet for ~2.5s: clear the gap history so load-burst noise doesn't linger
  if last_lite >= 0 and frames - last_lite > 150 and #gaps > 0 then
    gaps = {}
    last_gap = 0
  end
  if frames % 300 == 0 then
    flog(string.format("SUMMARY frames=%d lite=%d (%.1f%%) eff=%.1f/60 done_line=%d worst=%d",
         frames, lite_hits, 100 * lite_hits / frames,
         60 * (1 - lite_hits / frames), done_line, worst_line))
  end
  local pct = frames > 0 and (100 * lite_hits / frames) or 0
  emu.drawString(8, 8, string.format("frames %d  lite %d (%.1f%%)  eff %.1f/60",
                 frames, lite_hits, pct, 60 * (1 - lite_hits / math.max(frames, 1))),
                 0xFFFFFF, 0xA0000000)
  emu.drawString(8, 20, string.format("last gap %d  gaps: %s", last_gap,
                 table.concat(gaps, ",")), 0xFFFFFF, 0xA0000000)
  emu.drawString(8, 32, string.format("ISR done @line %d (worst %d)",
                 done_line, worst_line), 0xFFFFFF, 0xA0000000)
end

emu.addMemoryCallback(on_lite, emu.callbackType.exec, 0xE189, 0xE189,
                      emu.cpuType.pce, emu.memType.pceMemory)
emu.addMemoryCallback(on_done, emu.callbackType.exec, 0xE171, 0xE171,
                      emu.cpuType.pce, emu.memType.pceMemory)
emu.addEventCallback(on_frame, emu.eventType.endFrame)

emu.displayMessage("Script", "framewatch: counting lag frames ($E189) + ISR finish line")
