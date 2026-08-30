#!/usr/bin/env python3
"""Zero the upper 512K of the original image inside Parodius_SF2.pce
(file $080000-$0FFFFF = banks $40-$7F = SF2 page 0).

Safe because (census, 2026-08): that region holds ONLY compressed graphics
streams + $FF padding, and the SF2 build serves every known stream -
including pre-flipped p1 variants - from the expansion banks. Any straggler
event would now draw zeroed tiles (visible + logged by parodius_census.lua)
instead of silently decompressing.
"""
import os

HERE = os.path.dirname(os.path.abspath(__file__))
p = os.path.join(HERE, "Parodius_SF2.pce")
rom = bytearray(open(p, "rb").read())
rom[0x080000:0x100000] = bytes(0x80000)
open(p, "wb").write(rom)
print("zeroed $080000-$0FFFFF (original upper 512K)")
