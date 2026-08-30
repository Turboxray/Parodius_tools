#!/usr/bin/env python3
"""Relabel the 'used:' field of palette.inc block headers from a capture log.

  relabel_used.py <capture.txt> add  <LABEL>   add LABEL to every block the capture loaded
  relabel_used.py <capture.txt> only <LABEL>   capture is AUTHORITATIVE for LABEL:
                                               add LABEL to captured blocks AND remove it
                                               from every block NOT in the capture

Add --write to apply (default is a dry run).  Edits header comments only; colours
are untouched.  Idempotent.  Block identity is the absolute offset (block_abs in
the log == "block $ABS" in the header).

Examples:
  relabel_used.py parodius_pal_blocks_intro.txt add  OP --write   # tag opening blocks
  relabel_used.py parodius_pal_blocks_st1.txt   only L1 --write   # prune stray L1 from
                                                                  # anything not in stage 1
"""
import re, sys, importlib.util

spec = importlib.util.spec_from_file_location("pie", "palette_inc_editor.py")
pie = importlib.util.module_from_spec(spec); spec.loader.exec_module(pie)

USED_RE = re.compile(r"(used:\s*)(.*?)(\s*)(\||\*\*\*|---\s*$)")


def capture_blocks(path):
    s = set()
    for ln in open(path):
        m = re.search(r"block_abs=\$([0-9A-Fa-f]+)", ln)
        if m:
            s.add(int(m.group(1), 16))
    return s


def get_toks(header):
    m = USED_RE.search(header)
    if not m:
        return None
    return [t.strip() for t in m.group(2).split(",") if t.strip() and t.strip() != "?"]


def set_used(header, toks):
    m = USED_RE.search(header)
    val = ",".join(toks) if toks else "?"
    return header[:m.start()] + m.group(1) + val + m.group(3) + m.group(4) + header[m.end():]


def main():
    if len(sys.argv) < 4 or sys.argv[2] not in ("add", "only"):
        print(__doc__); return
    cap, mode, label = sys.argv[1], sys.argv[2], sys.argv[3]
    write = "--write" in sys.argv
    blocks = capture_blocks(cap)
    pal = pie.PaletteIncFile("palette.inc")
    byabs = {b["abs"]: b for b in pal.blocks.values()}
    added = removed = 0
    for b in pal.blocks.values():
        hl = b["hline"]
        toks = get_toks(pal.lines[hl])
        if toks is None:
            continue
        in_cap = b["abs"] in blocks
        new = list(toks)
        if in_cap and label not in new:
            new = [label] + new
        elif mode == "only" and not in_cap and label in new:
            new = [t for t in new if t != label]
        if new != toks:
            pal.lines[hl] = set_used(pal.lines[hl], new)
            if len(new) > len(toks):
                added += 1
            else:
                removed += 1
    missing = sum(1 for a in blocks if a not in byabs)
    print("%s  %s '%s'  (capture %s: %d blocks)  ->  +%d added, -%d removed%s"
          % ("WRITE" if write else "DRY ", mode, label, cap, len(blocks), added, removed,
             ("  (%d capture blocks not in palette.inc)" % missing) if missing else ""))
    if write:
        with open(pal.path, "w", newline="\n") as f:
            f.write("\n".join(pal.lines))
        print("written to palette.inc")
    else:
        print("(dry run) add --write to apply")


if __name__ == "__main__":
    main()
