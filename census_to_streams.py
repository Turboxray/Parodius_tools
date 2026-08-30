#!/usr/bin/env python3
"""Convert parodius_census.txt DEC (p1=$00) fallthrough lines into
gfxtrace-format ROMDEC lines -> parodius_extra_streams.txt.
Run by build_sf2.bat; cumulative (census log is append-only)."""
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
src_path = os.path.join(HERE, "parodius_census.txt")
out_path = os.path.join(HERE, "parodius_extra_streams.txt")

out = []
seen = set()
if os.path.exists(src_path):
    for ln in open(src_path):
        m = re.match(r"DEC   F=(\d+) stage=\$(\w+) bank=\$(\w+) p1=\$(\w+) "
                     r"dst=\$(\w+)\.w src=\$(\w+)", ln)
        if m:
            key = (m.group(3), m.group(4), m.group(6))
            if key in seen:
                continue
            seen.add(key)
            out.append("ROMDEC F=%s stage=$%s slot=0 bank=$%s p1=$%s "
                       "dst=$%s.w src=$%s words=0" % m.groups())

with open(out_path, "w", newline="\n") as f:
    f.write("=== census-derived p1=0 fallthrough streams (no VRAM dumps) ===\n")
    f.write("\n".join(out) + "\n")
print("census -> %d unique extra streams" % len(out))
