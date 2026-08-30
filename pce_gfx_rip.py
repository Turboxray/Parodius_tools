#!/usr/bin/env python3
"""Catalog + rip Parodius Da!'s compressed graphics from gfxtrace captures.

Reads one or more parodius_gfxtrace.txt-style logs, decodes every unique
compressed stream (pce_gfx_decode.py), and writes:

  gfx_rips/<bank>_<src>.png   4-bit greyscale PNG (16 grey steps of 16),
                              rendered as 8x8 tiles or 16x16 sprite cells
  gfx-blocks.md               catalog: stream, header, mode, sizes, VRAM
                              destination(s), flip variants, stages, calls

Usage:  pce_gfx_rip.py <rom> <trace.txt> [more traces...]

Rendering heuristic: sprite-cell layout iff header bit7 set AND the output is
a whole number of 64-word cells; otherwise 8x8 tiles (the water block uses
the sprite WRITER but contains BG tile data). Override by eye later if a rip
looks scrambled.
"""
import os
import re
import sys
import importlib.util

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("dec", os.path.join(HERE, "pce_gfx_decode.py"))
dec = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dec)

TILES_PER_ROW = 16

# Content format can't be inferred from the header alone (the ship is
# sprite-format data behind a tile-mode header; the water is tile data behind
# a sprite-mode header). Eyeball the rips and add corrections here.
RENDER_OVERRIDE = {
    # stage 1 ship animation frames: sprite cells, not tiles
    (0x40, 0xB757): "sprite", (0x40, 0xB820): "sprite",
    (0x40, 0xB8AF): "sprite", (0x40, 0xB93E): "sprite",
    (0x40, 0xB9E9): "sprite",
    # stage 1 scenery set (clouds/sea/galleon): tile format despite hdr $80
    (0x40, 0x6A53): "tile",
}


def tile_pixels(words):
    """16 words -> 8x8 pixel values."""
    px = [[0] * 8 for _ in range(8)]
    for r in range(8):
        p0 = words[r] & 0xFF
        p1 = words[r] >> 8
        p2 = words[r + 8] & 0xFF
        p3 = words[r + 8] >> 8
        for x in range(8):
            b = 7 - x
            px[r][x] = ((p0 >> b) & 1) | (((p1 >> b) & 1) << 1) | \
                       (((p2 >> b) & 1) << 2) | (((p3 >> b) & 1) << 3)
    return px


def sprite_pixels(words):
    """64 words -> 16x16 pixel values."""
    px = [[0] * 16 for _ in range(16)]
    for r in range(16):
        for x in range(16):
            b = 15 - x
            px[r][x] = ((words[r] >> b) & 1) | (((words[16 + r] >> b) & 1) << 1) | \
                       (((words[32 + r] >> b) & 1) << 2) | (((words[48 + r] >> b) & 1) << 3)
    return px


def render(out_bytes, sprite_mode):
    """-> (width, height, rows of pixel values)."""
    words = [out_bytes[i] | (out_bytes[i + 1] << 8)
             for i in range(0, len(out_bytes) - 1, 2)]
    cells = []
    if sprite_mode and len(words) % 64 == 0 and len(words) > 0:
        size, per = 16, 64
        for c in range(len(words) // 64):
            cells.append(sprite_pixels(words[c * 64:(c + 1) * 64]))
    else:
        size, per = 8, 16
        n = len(words) // 16
        for c in range(n):
            cells.append(tile_pixels(words[c * 16:(c + 1) * 16]))
    if not cells:
        return 8, 8, [[0] * 8 for _ in range(8)]
    per_row = max(1, (TILES_PER_ROW * 8) // size)
    rows = (len(cells) + per_row - 1) // per_row
    W, H = per_row * size, rows * size
    img = [[0] * W for _ in range(H)]
    for i, cell in enumerate(cells):
        cy, cx = divmod(i, per_row)
        for r in range(size):
            img[cy * size + r][cx * size:cx * size + size] = cell[r]
    return W, H, img


def save_png(path, W, H, img):
    from PIL import Image
    im = Image.new("P", (W, H))
    pal = []
    for v in range(16):
        pal += [v * 16] * 3
    im.putpalette(pal + [0] * (768 - len(pal)))
    im.putdata([v for row in img for v in row])
    im.save(path, bits=4)


def parse_traces(paths):
    ev_re = re.compile(
        r"ROMDEC F=\d+ stage=\$(\w+) slot=(\d+) bank=\$(\w+) p1=\$(\w+) "
        r"dst=\$(\w+)\.w src=\$(\w+)")
    blocks = {}
    for path in paths:
        for ln in open(path):
            m = ev_re.match(ln)
            if not m:
                continue
            key = (int(m.group(3), 16), int(m.group(6), 16))
            b = blocks.setdefault(key, {"calls": 0, "stages": set(),
                                        "dsts": set(), "p1s": set(),
                                        "slots": set()})
            b["calls"] += 1
            b["stages"].add(int(m.group(1), 16))
            b["p1s"].add(int(m.group(4), 16))
            b["dsts"].add(int(m.group(5), 16))
            b["slots"].add(int(m.group(2)))
    return blocks


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        return
    rom = open(sys.argv[1], "rb").read()
    blocks = parse_traces(sys.argv[2:])
    outdir = os.path.join(HERE, "gfx_rips")
    os.makedirs(outdir, exist_ok=True)

    rows = []
    for (bank, src) in sorted(blocks):
        info = blocks[(bank, src)]
        hdr, dic, out, clen = dec.decode_block_full(rom, bank, src)
        words = len(out) // 2
        ov = RENDER_OVERRIDE.get((bank, src))
        if ov is not None:
            sprite = ov == "sprite"
        else:
            sprite = bool(hdr & 0x80)
        as_sprite = sprite and words % 64 == 0 and words > 0
        name = "%02X_%04X.png" % (bank, src)
        W, H, img = render(out, sprite)
        save_png(os.path.join(outdir, name), W, H, img)
        rows.append({
            "bank": bank, "src": src, "off": dec.file_off(bank, src),
            "hdr": hdr, "dict": hdr & 0x7F, "clen": clen, "words": words,
            "mode": ("spr" if sprite else "tile") + ("+dict" if hdr & 0x7F else ""),
            "render": "16x16" if as_sprite else "8x8",
            "png": name, "info": info,
        })

    with open(os.path.join(HERE, "gfx-blocks.md"), "w", newline="\n") as f:
        f.write("# Parodius Da! - Compressed Graphics Block Catalog\n\n")
        f.write("Generated by `pce_gfx_rip.py` from gfxtrace captures. One row per\n")
        f.write("compressed stream; PNG rips (4-bit greyscale) in `gfx_rips/`.\n")
        f.write("`words` = decompressed size; `comp` = compressed bytes (hdr+dict+\n")
        f.write("tokens+FF); `p1` = flip variants seen; `dst.w` = VRAM word dest(s).\n\n")
        f.write("| bank:src | file off | hdr | mode | comp | words | tiles | "
                "render | p1 | dst.w | stage | slot | calls | png |\n")
        f.write("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|\n")
        for r in sorted(rows, key=lambda r: (min(r["info"]["stages"]), r["off"])):
            i = r["info"]
            f.write("| $%02X:$%04X | $%06X | $%02X | %s | %d | %d | %.1f | %s "
                    "| %s | %s | %s | %s | %d | %s |\n" % (
                        r["bank"], r["src"], r["off"], r["hdr"], r["mode"],
                        r["clen"], r["words"], r["words"] / 16.0, r["render"],
                        ",".join("$%02X" % v for v in sorted(i["p1s"])),
                        ",".join("$%04X" % v for v in sorted(i["dsts"])),
                        ",".join("$%02X" % v for v in sorted(i["stages"])),
                        ",".join(str(v) for v in sorted(i["slots"])),
                        i["calls"], r["png"]))
        total_c = sum(r["clen"] for r in rows)
        total_u = sum(r["words"] * 2 for r in rows)
        f.write("\n%d streams: %d bytes compressed -> %d bytes uncompressed "
                "(%.0f%% ratio)\n" % (len(rows), total_c, total_u,
                                      100.0 * total_c / max(total_u, 1)))
    print("wrote gfx-blocks.md + %d PNGs to gfx_rips/" % len(rows))


if __name__ == "__main__":
    main()
