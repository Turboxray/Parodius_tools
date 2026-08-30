#!/usr/bin/env python3
"""Mark fade-group membership in palette.inc block headers.

A BG fade is a run of consecutive same-size blocks stored back-to-back, every
frame dimmer-or-equal to the brightest "full" frame.  This tags each member's
header comment with:

    | fade $<groupid> <rank>/<total>        (clean fade-from-black)
    | prefade $<groupid> <rank>/<total>     (fade-like but NOT from-black:
                                             sectional / tail-of-fade, e.g. L7)

- groupid = absolute offset of the group's brightest (full) frame.
- rank    = this frame's position by brightness, 1 = darkest .. total = full.
- fade vs prefade: "fade" if the darkest step keeps >=50% of the full frame's
  lit colours fully black (the not-yet-revealed background); else "prefade".
  (User's rule: originally-black colours must stay black in a faded frame.)

Only BG groups (CTA < $0100) are tagged; sprite runs (>= $0100) are colour-cycle
animations, not fades.  Classification uses the ORIGINAL colours (palette_org.inc)
so recolours don't change the grouping.  Idempotent: an existing tag is replaced.
Edits ONLY header comment lines; colour data is left byte-for-byte intact.
"""
import re, importlib.util

spec = importlib.util.spec_from_file_location("pie", "palette_inc_editor.py")
pie = importlib.util.module_from_spec(spec); spec.loader.exec_module(pie)

def rgb(c):  return ((c >> 3) & 7, (c >> 6) & 7, c & 7)
def bri(cs): return sum(sum(rgb(c)) for c in cs)
def size(b): return 1 + (b["count"] + 1) * 9
def cta_is_bg(b):
    for tok in str(b.get("cta", "")).replace("$", "").split(","):
        try:
            if int(tok, 16) < 0x100: return True
        except ValueError: pass
    return False

def detect(org):
    """abs -> (kind, groupid_abs, rank, total) for every BG fade-group member."""
    B = sorted(org.blocks.values(), key=lambda b: b["abs"])
    runs, q = [], [B[0]]
    for b in B[1:]:
        p = q[-1]
        if p["abs"] + size(p) == b["abs"] and p["count"] == b["count"]:
            q.append(b)
        else:
            if len(q) >= 3: runs.append(q)
            q = [b]
    if len(q) >= 3: runs.append(q)

    fmap = {}
    for run in runs:
        if not cta_is_bg(run[0]): continue          # BG only
        order = sorted(run, key=lambda b: bri(b["colors"]))   # dark -> full
        full = order[-1]; dark = order[0]
        # fade-from-black: the darkest frame is mostly black (background not yet
        # revealed).  Reference-independent so the chosen "full" can't fool it.
        absblack = sum(1 for c in dark["colors"] if c == 0) / len(dark["colors"])
        kind = "fade" if absblack >= 0.60 else "prefade"
        for rank, fr in enumerate(order, start=1):
            fmap[fr["abs"]] = (kind, full["abs"], rank, len(order))
    return fmap

FADE_TAG = re.compile(r"\s*\|\s*(?:pre)?fade\s+\$[0-9A-Fa-f]+\s+\d+/\d+")

def apply_tag(header, kind, groupid, rank, total):
    h = FADE_TAG.sub("", header)                    # strip any existing tag (idempotent)
    tag = " | %s $%X %d/%d" % (kind, groupid, rank, total)
    if "*** MODIFIED" in h:
        return re.sub(r"\s*(\*\*\* MODIFIED)", tag + r"  \1", h, count=1)
    return re.sub(r"\s*---\s*$", tag + " ---", h)

def main():
    org = pie.PaletteIncFile("palette_org.inc")
    fmap = detect(org)
    cur = pie.PaletteIncFile("palette.inc")
    lines = cur.lines
    n_fade = n_pre = 0
    for b in cur.blocks.values():
        hl = b["hline"]
        header = FADE_TAG.sub("", lines[hl])        # clear stale tags everywhere
        if b["abs"] in fmap:
            kind, gid, rank, total = fmap[b["abs"]]
            header = apply_tag(header, kind, gid, rank, total)
            if kind == "fade": n_fade += 1
            else: n_pre += 1
        lines[hl] = header
    with open(cur.path, "w", newline="\n") as f:
        f.write("\n".join(lines))
    groups = {gid for (_, gid, _, _) in fmap.values()}
    print("tagged %d frames across %d BG fade groups: %d fade, %d prefade"
          % (len(fmap), len(groups), n_fade, n_pre))

if __name__ == "__main__":
    main()
