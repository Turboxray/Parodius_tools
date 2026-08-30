--Parodius Da! palette-block logger (Mesen2 Lua)
--Hooks the palette-decode routine and records every unique pointer-table entry
--the game decodes: bank, logical+absolute address, CTA, data-block ptr, colour count.
--Logs to the script window AND to a text file (LOG_PATH).
--If the file already exists it is kept and APPENDED to (per-run de-dupe only;
--redundant lines across runs/resets are fine - we sort those out when parsing).
--Right-mouse = wipe the list and start a brand-new file.

local pal_ptr = {}        -- list of entry logical addrs (for the on-screen overlay / count)
local seen = {}           -- de-dupe set, keyed by absolute offset (logical fallback)
local log_file = nil

-- Where the captured list is written. Adjust if you want it elsewhere.
local LOG_PATH = "D:/Projects/hacking/Parodius/parodius_pal_blocks_ending.txt"
--local LOG_PATH = "D:/Projects/hacking/Parodius/parodius_pal_blocks_debug.txt"
local LOG_HEADER = "# bank, entry_logical, entry_abs, CTA, block_logical, block_abs, count, colours, stage\n"

-- de-dupe key: prefer absolute offset; fall back to logical addr if unresolved
local function key_for(entry_abs, val_add)
  if entry_abs and entry_abs >= 0 then
    return string.format("A%06X", entry_abs)
  end
  return string.format("L%04X", val_add)
end

-- Convert a CPU logical address to an absolute PRG-ROM offset using the CURRENT banking.
local function abs_offset(logical)
  local ok, conv = pcall(emu.convertAddress, logical, emu.memType.pceMemory, emu.cpuType.pce)
  if ok and conv ~= nil and conv.address ~= nil then
    return conv.address
  end
  return -1
end

-- Open the log: APPEND if it already exists (write the header only when creating it).
local function open_log()
  if log_file then log_file:close(); log_file = nil end

  local existed = false
  local fr = io.open(LOG_PATH, "r")
  if fr then existed = true; fr:close() end

  log_file = io.open(LOG_PATH, "a")     -- append (creates the file if missing)
  if log_file then
    if not existed then log_file:write(LOG_HEADER) end
    log_file:flush()
    emu.log(string.format("pal log -> %s (%s)", LOG_PATH, existed and "appending" or "new file"))
  else
    emu.log("!! could not open " .. LOG_PATH .. " (io blocked? path bad?) - window log still works")
  end
end

-- Right-click reset: wipe memory and TRUNCATE to a fresh file.
local function reset_log()
  seen = {}
  pal_ptr = {}
  if log_file then log_file:close() end
  log_file = io.open(LOG_PATH, "w")
  if log_file then
    log_file:write(LOG_HEADER)
    log_file:flush()
  end
  emu.log(" ------ cleared, fresh file -------")
end

function printInfo()
  --Get the emulation state
  state = emu.getState()

  --Get the mouse's state (x, y, left, right, middle)
  mouseState = emu.getMouseState()

  --Right button held = wipe and start over
  if mouseState.right == true then
    buffer = emu.getScreenBuffer()
    for i = 1, #buffer do
      buffer[i] = buffer[i] & 0xFFFF
    end
    emu.setScreenBuffer(buffer)

    bgColor = 0x30FF6020
    fgColor = 0x304040FF
    if #pal_ptr > 0 then          -- only reset once per clear, not every held frame
      reset_log()
    end
  else
    bgColor = 0x302060FF
    fgColor = 0x30FF4040
  end

    local y_offset = 0
    local x_offset = 0

	for _, v in ipairs(pal_ptr) do
	    -- leave the commented code below. Do not delete it.
		--emu.drawString(12+x_offset, 12+y_offset, " " .. string.format("%x",v), 0xFFFFFF, 0xFF000000)
		y_offset = y_offset + 12
		if y_offset > (16*12) then
		    y_offset = 0
		    x_offset = x_offset + 34
		end
	end

  --Draw a block behind the mouse cursor - leaves a trail when moving the mouse
  --emu.drawRectangle(mouseState.x - 2, mouseState.y - 2, 5, 5, 0xAF00FF90, true, 20)
  --emu.drawRectangle(mouseState.x - 2, mouseState.y - 2, 5, 5, 0xAF000000, false, 20)
end

function read_pal_ptr()

	local val_add = emu.read16(0x2000, emu.memType.pceMemory, false)
	local state = emu.getState()
	local regY = state["cpu.y"]
	val_add = val_add + regY        -- effective address of the pointer-table entry
	local stage = emu.read(0x2093, emu.memType.pceMemory, false)   -- $93 = current stage

	-- skip if we've already recorded this entry+stage (this run or a previous one)
	local entry_abs = abs_offset(val_add)
	local k = key_for(entry_abs, val_add) .. ":" .. stage
	if seen[k] then return end
	seen[k] = true
	table.insert(pal_ptr, val_add)

	local bank = -1
	if entry_abs >= 0 then bank = entry_abs >> 13 end

	-- decode the pointer-table entry: [CTA_lo][CTA_hi][block_lo][block_hi]
	local cta       = emu.read16(val_add, emu.memType.pceMemory, false)
	local block     = emu.read16(val_add + 2, emu.memType.pceMemory, false)
	local block_abs = abs_offset(block)
	local count     = emu.read(block, emu.memType.pceMemory, false)   -- block[0] = (groups-1)
	local colours   = (count + 1) * 8

	local abs_str  = (entry_abs >= 0) and string.format("$%06X", entry_abs) or "$------"
	local babs_str = (block_abs >= 0) and string.format("$%06X", block_abs) or "$------"
	local bank_str = (bank >= 0) and string.format("$%02X", bank) or "$--"

	local line = string.format(
	    "bank=%s entry=$%04X abs=%s CTA=$%04X block=$%04X block_abs=%s count=$%02X colours=%d stage=$%02X",
	    bank_str, val_add, abs_str, cta, block, babs_str, count, colours, stage)

	emu.log(line)
	if log_file then
	    log_file:write(line .. "\n")
	    log_file:flush()
	end

end

--Register some code (printInfo function) that will be run at the end of each frame
emu.addEventCallback(printInfo, emu.eventType.endFrame);
emu.addMemoryCallback(read_pal_ptr, emu.callbackType.exec, 0x7042a, 0x7042a, emu.cpuType.pce, emu.memType.pcePrgRom);

--Open (or resume) the log file
open_log()

--Display a startup message
emu.displayMessage("Script", "Parodius palette logger loaded.")
