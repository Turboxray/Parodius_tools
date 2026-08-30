--Parodius SF2 hook probe v2 (Mesen2 Lua)
--Counts springboard/main/fallthrough AND samples what the hook actually
--sees at $6000 right after mapping MPR3=$80 + latching SF2 page 1
--(exec hook at $46C5). Expected: 0a 12 16 18 1c 20 30 34 (bucket banks).
--Log: parodius_hookprobe.txt

local log_file = io.open("D:/Projects/hacking/Parodius/parodius_hookprobe.txt", "a")
local function flog(s)
  if log_file then log_file:write(s .. "\n"); log_file:flush() end
end
flog("=== run start ===")

local spring, main, fall = 0, 0, 0
local sampled = 0

local function on_spring() spring = spring + 1 end
local function on_fall() fall = fall + 1 end

local function on_latched()
  main = main + 1
  if sampled < 4 then
    sampled = sampled + 1
    local b = {}
    for i = 0, 7 do
      b[#b + 1] = string.format("%02X", emu.read(0x6000 + i, emu.memType.pceMemory, false))
    end
    flog(string.format("sample %d: $6000 = %s (expect 0A 12 16 18 1C 20 30 34)",
         sampled, table.concat(b, " ")))
  end
end

local function on_frame()
  emu.drawString(8, 8, string.format("spring=%d latched=%d fallthru=%d divert=%d",
                 spring, main, fall, spring - fall), 0xFFFFFF, 0xA0000000)
end

emu.addMemoryCallback(on_spring, emu.callbackType.exec, 0xFF9B, 0xFF9B,
                      emu.cpuType.pce, emu.memType.pceMemory)
emu.addMemoryCallback(on_latched, emu.callbackType.exec, 0x46C5, 0x46C5,
                      emu.cpuType.pce, emu.memType.pceMemory)
emu.addMemoryCallback(on_fall, emu.callbackType.exec, 0xC25C, 0xC25C,
                      emu.cpuType.pce, emu.memType.pceMemory)
emu.addEventCallback(on_frame, emu.eventType.endFrame)
emu.displayMessage("Script", "hookprobe v2 -> parodius_hookprobe.txt")
