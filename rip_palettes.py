#!/usr/bin/env python3
"""Rip the ORIGINAL palette data from the ROM -> palette_org.inc.

Uses palette.inc as the structural map (which blocks exist, at which
bank:org, with which headers) and re-reads every block's colours from the
user-supplied original ROM. Output format is identical to palette.inc
(same emitter), with the MODIFIED tags stripped - so the palette editor
can diff your recolour against the true originals.

ROM block format: [count = groups-1] then per 8-colour group:
[mask byte: bit(7-k) = colour k's 9th bit] [8 low bytes].

Usage: rip_palettes.py [rom] [palette.inc] [out]
"""
import os
import sys
import importlib.util

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("pie", os.path.join(HERE, "palette_editor.py"))
pie = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pie)


def rom_colors(rom, abs_off, count):
    """Read (count+1)*8 9-bit colours from the ROM block at abs_off."""
    cols = []
    p = abs_off + 1
    for _ in range(count + 1):
        mask = rom[p]
        for k in range(8):
            cols.append(rom[p + 1 + k] | (((mask >> (7 - k)) & 1) << 8))
        p += 9
    return cols


def main():
    rom_path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "Parodius_Da__original.pce")
    inc_path = sys.argv[2] if len(sys.argv) > 2 else os.path.join(HERE, "palette.inc")
    out_path = sys.argv[3] if len(sys.argv) > 3 else os.path.join(HERE, "palette_org.inc")

    rom = open(rom_path, "rb").read()
    pal = pie.PaletteIncFile(inc_path)
    for key, b in pal.blocks.items():
        cols = rom_colors(rom, b["abs"], b["count"])
        assert len(cols) == len(b["colors"]), "size mismatch at block $%X" % b["abs"]
        pal.set_colors(key[0], key[1], cols)
    # orig == new -> save() strips every MODIFIED tag
    pal.orig_colors = {k: list(b["colors"]) for k, b in pal.blocks.items()}
    pal.path = out_path
    pal.save()
    print("wrote %s: %d blocks (original ROM colours)" % (os.path.basename(out_path), len(pal.blocks)))


if __name__ == "__main__":
    main()
