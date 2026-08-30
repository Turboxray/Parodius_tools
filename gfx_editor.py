#!/usr/bin/env python3
"""Editor/viewer for the extracted graphics (gfx_bins/*.bin).

The bins are raw decompressed VRAM data (little-endian words). View them as
8x8 BG tiles or 16x16 sprite cells (the format isn't stored in the bin -
toggle to whichever looks right; the choice is remembered per file).

Left: the sheet (all cells). Click a cell to edit it; right-click a cell to
paint it with the ACTIVE palette (see below). Right: the cell editor -
left-click/drag paints with the selected colour index, right-click picks the
colour under the cursor. Ctrl+Z undo, Ctrl+S save.

Palettes: slot 0 is greyscale. "Add from .inc..." imports any 16-colour
subpalette slice from palette.inc / palette_org.inc / other. Palettes map to
cells (right-click, or the "-> cell"/"-> all" buttons); the mapping and the
imported palettes are saved in a <bin>.palmap.json sidecar, kept separately
for the tile and sprite views. Colour indices in the bin are untouched -
palettes only change how it's displayed.

Usage: gfx_editor.py [file.bin]
"""
import json
import math
import os
import re
import sys
import importlib.util
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

HERE = os.path.dirname(os.path.abspath(__file__))
BINDIR = os.path.join(HERE, "gfx_bins")

FMT = {"tile": {"wpc": 16, "size": 8, "per_row": 16},
       "sprite": {"wpc": 64, "size": 16, "per_row": 8}}
# built-in greyscale palettes (slot 0..NBUILTIN-1, always present):
# 4bpp ramp, its reverse, a 3bpp ramp (0-7 twice, for 8-colour content
# viewed in 4bpp cells), and its reverse
G16 = [(v * 17, v * 17, v * 17) for v in range(16)]
G8 = [(int(v / 7.0 * 255),) * 3 for v in range(8)]
BUILTINS = [("greyscale", G16),
            ("greyscale reversed", G16[::-1]),
            ("3bpp greys (0-7 x2)", G8 + G8),
            ("3bpp greys reversed", G8[::-1] + G8[::-1])]
NBUILTIN = len(BUILTINS)
BIN_RE = re.compile(r"^([0-9A-Fa-f]{2})_([0-9A-Fa-f]{4})(?:_f(\d+))?\.bin$")


def load_table():
    """compressed_gfx_table.txt -> {(bank,src,p1): {dst, dlen, stages}}.
    Tags each bin with the stage ids that load it (trace + sequence table)."""
    table = {}
    path = os.path.join(HERE, "compressed_gfx_table.txt")
    if not os.path.exists(path):
        return table
    for ln in open(path):
        f = ln.split()
        if not f or ln.startswith(";"):
            continue
        stages = f[7] if len(f) > 7 and f[7] != "-" else ""
        table[(int(f[0], 16), int(f[1], 16), int(f[2], 16))] = {
            "dst": int(f[6], 16), "dlen": int(f[5], 16), "stages": stages}
    return table


def _load_pie():
    """palette_editor.py provides PaletteIncFile for the .inc import."""
    try:
        spec = importlib.util.spec_from_file_location(
            "pie", os.path.join(HERE, "palette_editor.py"))
        pie = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(pie)
        return pie
    except Exception:
        return None


def vce_rgb(c):
    return (int(((c >> 3) & 7) / 7 * 255), int(((c >> 6) & 7) / 7 * 255),
            int((c & 7) / 7 * 255))


# ---------------- planar codecs ----------------

def tile_decode(words):
    px = [[0] * 8 for _ in range(8)]
    for r in range(8):
        p0, p1 = words[r] & 0xFF, words[r] >> 8
        p2, p3 = words[r + 8] & 0xFF, words[r + 8] >> 8
        for x in range(8):
            b = 7 - x
            px[r][x] = ((p0 >> b) & 1) | (((p1 >> b) & 1) << 1) | \
                       (((p2 >> b) & 1) << 2) | (((p3 >> b) & 1) << 3)
    return px


def tile_encode(px):
    words = [0] * 16
    for r in range(8):
        p0 = p1 = p2 = p3 = 0
        for x in range(8):
            v, b = px[r][x], 7 - x
            p0 |= (v & 1) << b; p1 |= ((v >> 1) & 1) << b
            p2 |= ((v >> 2) & 1) << b; p3 |= ((v >> 3) & 1) << b
        words[r] = p0 | (p1 << 8)
        words[r + 8] = p2 | (p3 << 8)
    return words


def sprite_decode(words):
    px = [[0] * 16 for _ in range(16)]
    for r in range(16):
        for x in range(16):
            b = 15 - x
            px[r][x] = ((words[r] >> b) & 1) | (((words[16 + r] >> b) & 1) << 1) | \
                       (((words[32 + r] >> b) & 1) << 2) | (((words[48 + r] >> b) & 1) << 3)
    return px


def sprite_encode(px):
    words = [0] * 64
    for r in range(16):
        for x in range(16):
            v, b = px[r][x], 15 - x
            words[r] |= (v & 1) << b
            words[16 + r] |= ((v >> 1) & 1) << b
            words[32 + r] |= ((v >> 2) & 1) << b
            words[48 + r] |= ((v >> 3) & 1) << b
    return words


DECODE = {"tile": tile_decode, "sprite": sprite_decode}
ENCODE = {"tile": tile_encode, "sprite": sprite_encode}


def run_gui(path=None):
    pie = _load_pie()

    class App:
        def __init__(self, root):
            self.root = root
            self.path = None
            self.nbytes = 0           # original file length (save truncates to it)
            self.words = []
            self.px = []              # pixel buffer, [y][x] 4-bit indices
            self.fmt = "tile"
            self.z = 3
            self.sel = None           # selected cell index
            self.colour = 1           # paint index
            self.palettes = []        # slot 0 grey + imported: {"label","colors"(9bit) or None}
            self.active_pal = 0
            self.palmap = {"tile": {}, "sprite": {}}   # str(cell) -> slot
            self.undo_stack = []
            self.dirty = False
            self.table = load_table()
            self.meta = None
            self._build()
            if path:
                self.open_file(path)

        # ---------- helpers ----------
        def f(self):
            return FMT[self.fmt]

        def ncells(self):
            return max(1, math.ceil(len(self.words) / float(self.f()["wpc"]))) if self.words else 0

        def sheet_dims(self):
            f = self.f()
            rows = math.ceil(self.ncells() / float(f["per_row"])) if self.words else 1
            return f["per_row"] * f["size"], max(rows, 1) * f["size"]

        def cell_origin(self, ci):
            f = self.f()
            return (ci % f["per_row"]) * f["size"], (ci // f["per_row"]) * f["size"]

        def cell_rgb(self, ci):
            # unassigned cells follow the ACTIVE palette; right-click pins one
            slot = self.palmap[self.fmt].get(str(ci), self.active_pal)
            if slot >= len(self.palettes):
                slot = 0
            p = self.palettes[slot]
            return BUILTINS[p.get("builtin", 0)][1] if p["colors"] is None \
                else [vce_rgb(c) for c in p["colors"]]

        # ---------- UI ----------
        def _build(self):
            self.root.minsize(760, 560)
            top = ttk.Frame(self.root, padding=6); top.pack(side=tk.TOP, fill=tk.X)
            ttk.Button(top, text="Open...", command=self.open_dialog).pack(side=tk.LEFT)
            ttk.Button(top, text="Browse bins...", command=self.browse_bins).pack(side=tk.LEFT, padx=(6, 0))
            ttk.Button(top, text="<", width=2, command=lambda: self.step_file(-1)).pack(side=tk.LEFT, padx=(6, 0))
            ttk.Button(top, text=">", width=2, command=lambda: self.step_file(1)).pack(side=tk.LEFT)
            self.fmt_var = tk.StringVar(value="tile")
            for txt, v in (("Tiles 8x8", "tile"), ("Sprites 16x16", "sprite")):
                ttk.Radiobutton(top, text=txt, variable=self.fmt_var, value=v,
                                command=self.set_fmt).pack(side=tk.LEFT, padx=6)
            ttk.Label(top, text="Zoom:").pack(side=tk.LEFT, padx=(10, 2))
            self.zoom_var = tk.StringVar(value="3")
            zb = ttk.Combobox(top, textvariable=self.zoom_var, width=2, state="readonly",
                              values=["1", "2", "3", "4", "6"])
            zb.pack(side=tk.LEFT)
            zb.bind("<<ComboboxSelected>>", lambda e: self.set_zoom())
            ttk.Button(top, text="Save", command=self.save).pack(side=tk.RIGHT)
            self.info = ttk.Label(self.root, text="Open a .bin from gfx_bins/", padding=(6, 0))
            self.info.pack(side=tk.TOP, fill=tk.X)

            main = ttk.Frame(self.root); main.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)

            # sheet (left)
            sf = ttk.LabelFrame(main, text="Sheet  (click: edit cell, right-click: pin active palette to cell)")
            sf.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            self.sheet = tk.Canvas(sf, bg="#181818", width=420)
            vsb = ttk.Scrollbar(sf, orient=tk.VERTICAL, command=self.sheet.yview)
            self.sheet.configure(yscrollcommand=vsb.set)
            vsb.pack(side=tk.RIGHT, fill=tk.Y)
            self.sheet.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            self.sheet.bind("<Button-1>", lambda e: self.sheet_click(e, False))
            self.sheet.bind("<Button-3>", lambda e: self.sheet_click(e, True))
            self.img = None

            right = ttk.Frame(main); right.pack(side=tk.LEFT, fill=tk.Y, padx=(8, 0))

            # cell editor
            ef = ttk.LabelFrame(right, text="Cell  (paint / right-click: pick colour)")
            ef.pack(side=tk.TOP)
            self.ed = tk.Canvas(ef, width=192, height=192, bg="#181818")
            self.ed.pack(padx=4, pady=4)
            self.ed.bind("<Button-1>", self.ed_paint)
            self.ed.bind("<B1-Motion>", self.ed_paint)
            self.ed.bind("<Button-3>", self.ed_pick)
            self.cell_lbl = ttk.Label(ef, text="no cell selected"); self.cell_lbl.pack(pady=(0, 4))
            self.strip = tk.Canvas(ef, width=16 * 12, height=14, bg="#181818",
                                   highlightthickness=0)
            self.strip.pack(pady=(0, 6))
            self.strip.bind("<Button-1>", self.strip_click)

            # palettes
            pf = ttk.LabelFrame(right, text="Palettes  (radio = active)")
            pf.pack(side=tk.TOP, fill=tk.BOTH, expand=True, pady=(8, 0))
            self.pal_box = ttk.Frame(pf); self.pal_box.pack(fill=tk.BOTH, expand=True)
            bb = ttk.Frame(pf); bb.pack(fill=tk.X, pady=2)
            add = ttk.Button(bb, text="Add from .inc...", command=self.add_palette)
            add.pack(side=tk.LEFT, padx=2)
            if pie is None:
                add.config(state=tk.DISABLED)
            ttk.Button(bb, text="-> cell", width=7, command=self.pal_to_cell).pack(side=tk.LEFT, padx=2)
            ttk.Button(bb, text="-> all", width=6, command=self.pal_to_all).pack(side=tk.LEFT, padx=2)
            ttk.Button(bb, text="Remove", command=self.remove_palette).pack(side=tk.LEFT, padx=2)

            self.root.bind("<Control-s>", lambda e: self.save())
            self.root.bind("<Control-z>", lambda e: self.undo())
            self.palettes = self._builtin_slots()
            self.refresh_palettes()

        def _builtin_slots(self):
            return [{"label": lbl, "colors": None, "builtin": i}
                    for i, (lbl, _) in enumerate(BUILTINS)]

        # ---------- file ----------
        def open_dialog(self):
            initial = BINDIR if os.path.isdir(BINDIR) else HERE
            p = filedialog.askopenfilename(initialdir=initial, title="Open graphics bin",
                                           filetypes=[("bin files", "*.bin"), ("all", "*.*")])
            if p:
                self.open_file(p)

        def step_file(self, d):
            if not self.path:
                return
            folder = os.path.dirname(self.path)
            bins = sorted(f for f in os.listdir(folder) if f.lower().endswith(".bin"))
            cur = os.path.basename(self.path)
            if cur not in bins:
                return
            i = (bins.index(cur) + d) % len(bins)
            self.open_file(os.path.join(folder, bins[i]))

        def open_file(self, p):
            if self.dirty and not messagebox.askyesno(
                    "Unsaved changes", "Discard unsaved changes?"):
                return
            data = open(p, "rb").read()
            self.path = p
            self.nbytes = len(data)
            m = BIN_RE.match(os.path.basename(p))
            self.meta = self.table.get((int(m.group(1), 16), int(m.group(2), 16),
                                        int(m.group(3) or 0))) if m else None
            self.words = [data[i] | (data[i + 1] << 8) for i in range(0, len(data) - 1, 2)]
            self.palettes = self._builtin_slots()
            self.active_pal = 0
            self.palmap = {"tile": {}, "sprite": {}}
            side = self.sidecar_path()
            if os.path.exists(side):
                try:
                    sc = json.load(open(side))
                    self.fmt = sc.get("format", "tile") if sc.get("format") in FMT else "tile"
                    for pl in sc.get("palettes", []):
                        self.palettes.append({"label": pl["label"], "colors": pl["colors"]})
                    # older sidecars had fewer builtin slots: shift imports
                    shift = NBUILTIN - sc.get("nbuiltin", 1)
                    for k in ("tile", "sprite"):
                        m = {}
                        for c, s in sc.get("map", {}).get(k, {}).items():
                            s = int(s)
                            if s >= NBUILTIN - shift:
                                s += shift
                            if 0 <= s < len(self.palettes):
                                m[str(c)] = s
                        self.palmap[k] = m
                    d = int(sc.get("default", 0))
                    if d >= NBUILTIN - shift:
                        d += shift
                    if 0 <= d < len(self.palettes):
                        self.active_pal = d
                except Exception as ex:
                    messagebox.showwarning("Sidecar", "Couldn't read %s:\n%s"
                                           % (os.path.basename(side), ex))
            self.fmt_var.set(self.fmt)
            self.sel = None
            self.undo_stack = []
            self.dirty = False
            self.decode_all()
            self.refresh_palettes()
            self.render_sheet()
            self.render_cell()
            self.set_title()

        def browse_bins(self):
            """All extracted bins joined with the manifest: which stages load
            each one, and where in VRAM. Double-click to open."""
            if not os.path.isdir(BINDIR):
                messagebox.showinfo("Browse", "No gfx_bins/ - run the extract first.")
                return
            win = tk.Toplevel(self.root); win.title("gfx_bins - stage tags")
            win.geometry("640x520"); win.transient(self.root)
            body = ttk.Frame(win); body.pack(fill=tk.BOTH, expand=True)
            cols = ("file", "words", "tiles", "dst", "flip", "stages")
            widths = {"file": 140, "words": 60, "tiles": 60, "dst": 70,
                      "flip": 40, "stages": 200}
            tv = ttk.Treeview(body, columns=cols, show="headings")
            for c in cols:
                tv.heading(c, text=c)
                tv.column(c, width=widths[c], anchor=tk.W)
            vsb = ttk.Scrollbar(body, orient=tk.VERTICAL, command=tv.yview)
            tv.configure(yscrollcommand=vsb.set)
            vsb.pack(side=tk.RIGHT, fill=tk.Y); tv.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            for fn in sorted(os.listdir(BINDIR)):
                m = BIN_RE.match(fn)
                if not m:
                    continue
                key = (int(m.group(1), 16), int(m.group(2), 16), int(m.group(3) or 0))
                t = self.table.get(key)
                words = os.path.getsize(os.path.join(BINDIR, fn)) // 2
                tv.insert("", tk.END, iid=fn, values=(
                    fn, words, "%.1f" % (words / 16.0),
                    "$%04X" % t["dst"] if t else "?",
                    "f%d" % key[2] if key[2] else "",
                    (t["stages"] or "static table only") if t else "not in table"))

            def pick(ev=None):
                sel = tv.selection()
                if sel:
                    win.destroy()
                    self.open_file(os.path.join(BINDIR, sel[0]))
            tv.bind("<Double-1>", pick)
            ttk.Label(win, text="stages = stage ids seen loading the stream "
                                "(traces + $C5BA sequence table).  Double-click to open.",
                      padding=4).pack(side=tk.BOTTOM, fill=tk.X)

        def sidecar_path(self):
            return self.path + ".palmap.json" if self.path else None

        def set_title(self):
            name = os.path.basename(self.path) if self.path else "(no file)"
            self.root.title("Parodius gfx editor - %s%s" % (name, " *" if self.dirty else ""))

        def mark_dirty(self, on=True):
            self.dirty = on
            self.set_title()

        # ---------- decode / render ----------
        def decode_all(self):
            f = self.f()
            W, H = self.sheet_dims()
            self.px = [[0] * W for _ in range(H)]
            wpc = f["wpc"]
            for ci in range(self.ncells()):
                chunk = self.words[ci * wpc:(ci + 1) * wpc]
                chunk += [0] * (wpc - len(chunk))
                cell = DECODE[self.fmt](chunk)
                x0, y0 = self.cell_origin(ci)
                for r in range(f["size"]):
                    self.px[y0 + r][x0:x0 + f["size"]] = cell[r]
            n = self.ncells()
            tag = ""
            if self.meta:
                tag = "  |  VRAM dst $%04X.w, loaded by stage%s %s" % (
                    self.meta["dst"], "s" if "," in self.meta["stages"] else "",
                    "$" + self.meta["stages"].replace(",", ",$") if self.meta["stages"]
                    else "(static table only)")
            self.info.config(text="%s: %d bytes = %d words = %d %s cells%s"
                             % (os.path.basename(self.path or "?"), self.nbytes,
                                len(self.words), n, self.fmt, tag))

        def render_sheet(self):
            W, H = self.sheet_dims()
            z = self.z
            self.img = tk.PhotoImage(width=W * z, height=H * z)
            if self.words:
                # per-cell hex rows (palette differs per cell)
                hexpx = [[None] * W for _ in range(H)]
                f = self.f()
                for ci in range(self.ncells()):
                    rgb = self.cell_rgb(ci)
                    hx = ["#%02x%02x%02x" % c for c in rgb]
                    x0, y0 = self.cell_origin(ci)
                    for r in range(f["size"]):
                        row = hexpx[y0 + r]
                        src = self.px[y0 + r]
                        for x in range(f["size"]):
                            row[x0 + x] = hx[src[x0 + x]]
                rows = []
                for y in range(H):
                    r = "{" + " ".join(c for c in (hexpx[y][x] or "#000000" for x in range(W))
                                       for _ in range(z)) + "}"
                    rows.extend([r] * z)
                self.img.put(" ".join(rows))
            self.sheet.delete("all")
            self.sheet.create_image(4, 4, image=self.img, anchor=tk.NW)
            self.sheet.configure(scrollregion=(0, 0, W * z + 8, H * z + 8))
            self.draw_sel()

        def draw_sel(self):
            self.sheet.delete("selbox")
            if self.sel is None:
                return
            f, z = self.f(), self.z
            x0, y0 = self.cell_origin(self.sel)
            self.sheet.create_rectangle(4 + x0 * z, 4 + y0 * z,
                                        4 + (x0 + f["size"]) * z, 4 + (y0 + f["size"]) * z,
                                        outline="#ffffff", width=2, tags="selbox")

        def put_pixel(self, x, y):
            """Repaint one sheet pixel from self.px (after an edit)."""
            ci = self.cell_at_px(x, y)
            hx = "#%02x%02x%02x" % self.cell_rgb(ci)[self.px[y][x]]
            z = self.z
            self.img.put(hx, to=(x * z, y * z, (x + 1) * z, (y + 1) * z))

        def render_cell_on_sheet(self, ci):
            f = self.f()
            x0, y0 = self.cell_origin(ci)
            rgb = self.cell_rgb(ci)
            z = self.z
            for r in range(f["size"]):
                for x in range(f["size"]):
                    hx = "#%02x%02x%02x" % rgb[self.px[y0 + r][x0 + x]]
                    self.img.put(hx, to=((x0 + x) * z, (y0 + r) * z,
                                         (x0 + x + 1) * z, (y0 + r + 1) * z))

        def cell_at_px(self, x, y):
            f = self.f()
            return (y // f["size"]) * f["per_row"] + (x // f["size"])

        # ---------- sheet interaction ----------
        def sheet_click(self, ev, assign):
            if not self.words:
                return
            z = self.z
            x = (int(self.sheet.canvasx(ev.x)) - 4) // z
            y = (int(self.sheet.canvasy(ev.y)) - 4) // z
            W, H = self.sheet_dims()
            if not (0 <= x < W and 0 <= y < H):
                return
            ci = self.cell_at_px(x, y)
            if ci >= self.ncells():
                return
            if assign:
                self.assign_pal(ci)
            else:
                self.sel = ci
                self.draw_sel()
                self.render_cell()

        def assign_pal(self, ci):
            m = self.palmap[self.fmt]
            if self.active_pal == 0:
                m.pop(str(ci), None)
            else:
                m[str(ci)] = self.active_pal
            self.render_cell_on_sheet(ci)
            if ci == self.sel:
                self.render_cell()
            self.mark_dirty()

        def pal_to_cell(self):
            if self.sel is not None:
                self.assign_pal(self.sel)

        def pal_to_all(self):
            if not self.words:
                return
            self.palmap[self.fmt] = {} if self.active_pal == 0 else \
                {str(ci): self.active_pal for ci in range(self.ncells())}
            self.render_sheet()
            self.render_cell()
            self.mark_dirty()

        # ---------- cell editor ----------
        def ed_px(self):
            return 192 // self.f()["size"]

        def render_cell(self):
            self.ed.delete("all")
            self.render_strip()
            if self.sel is None or not self.words:
                self.cell_lbl.config(text="no cell selected")
                return
            f = self.f()
            x0, y0 = self.cell_origin(self.sel)
            rgb = self.cell_rgb(self.sel)
            pxs = self.ed_px()
            for r in range(f["size"]):
                for x in range(f["size"]):
                    c = self.px[y0 + r][x0 + x]
                    self.ed.create_rectangle(x * pxs, r * pxs, (x + 1) * pxs, (r + 1) * pxs,
                                             fill="#%02x%02x%02x" % rgb[c],
                                             outline="#333")
            slot = self.palmap[self.fmt].get(str(self.sel), 0)
            self.cell_lbl.config(text="cell %d  word $%04X  byte $%05X  pal %d"
                                 % (self.sel, self.sel * f["wpc"],
                                    self.sel * f["wpc"] * 2, slot))

        def render_strip(self):
            self.strip.delete("all")
            rgb = self.cell_rgb(self.sel) if self.sel is not None else BUILTINS[0][1]
            for i, c in enumerate(rgb):
                x = i * 12
                self.strip.create_rectangle(x, 0, x + 12, 14, fill="#%02x%02x%02x" % c,
                                            outline="#fff" if i == self.colour else "#444",
                                            width=2 if i == self.colour else 1)

        def strip_click(self, ev):
            i = ev.x // 12
            if 0 <= i < 16:
                self.colour = i
                self.render_strip()

        def _ed_xy(self, ev):
            pxs = self.ed_px()
            x, y = ev.x // pxs, ev.y // pxs
            s = self.f()["size"]
            return (x, y) if (0 <= x < s and 0 <= y < s) else (None, None)

        def ed_paint(self, ev):
            if self.sel is None:
                return
            x, y = self._ed_xy(ev)
            if x is None:
                return
            x0, y0 = self.cell_origin(self.sel)
            gx, gy = x0 + x, y0 + y
            old = self.px[gy][gx]
            if old == self.colour:
                return
            self.undo_stack.append((self.fmt, gx, gy, old))
            self.px[gy][gx] = self.colour
            self.reencode_cell(self.sel)
            self.put_pixel(gx, gy)
            pxs = self.ed_px()
            rgb = self.cell_rgb(self.sel)
            self.ed.create_rectangle(x * pxs, y * pxs, (x + 1) * pxs, (y + 1) * pxs,
                                     fill="#%02x%02x%02x" % rgb[self.colour], outline="#333")
            self.mark_dirty()

        def ed_pick(self, ev):
            if self.sel is None:
                return
            x, y = self._ed_xy(ev)
            if x is None:
                return
            x0, y0 = self.cell_origin(self.sel)
            self.colour = self.px[y0 + y][x0 + x]
            self.render_strip()

        def undo(self):
            if not self.undo_stack:
                return
            fmt, gx, gy, old = self.undo_stack.pop()
            if fmt != self.fmt:
                self.fmt = fmt
                self.fmt_var.set(fmt)
                self.set_fmt(keep_undo=True)
            self.px[gy][gx] = old
            ci = self.cell_at_px(gx, gy)
            self.reencode_cell(ci)
            self.put_pixel(gx, gy)
            if ci == self.sel:
                self.render_cell()
            self.mark_dirty()

        def reencode_cell(self, ci):
            f = self.f()
            x0, y0 = self.cell_origin(ci)
            cell = [self.px[y0 + r][x0:x0 + f["size"]] for r in range(f["size"])]
            words = ENCODE[self.fmt](cell)
            wpc = f["wpc"]
            end = min((ci + 1) * wpc, len(self.words))
            self.words[ci * wpc:end] = words[:end - ci * wpc]

        # ---------- format / zoom ----------
        def set_fmt(self, keep_undo=False):
            self.fmt = self.fmt_var.get()
            if not keep_undo:
                self.undo_stack = []       # pixel coords are format-specific
            self.sel = None
            if self.words:
                self.decode_all()
                self.render_sheet()
            self.render_cell()

        def set_zoom(self):
            self.z = int(self.zoom_var.get())
            if self.words:
                self.render_sheet()

        # ---------- palettes ----------
        def refresh_palettes(self):
            for w in self.pal_box.winfo_children():
                w.destroy()
            self.pal_var = tk.IntVar(value=self.active_pal)
            for i, p in enumerate(self.palettes):
                row = ttk.Frame(self.pal_box); row.pack(fill=tk.X, pady=1)
                ttk.Radiobutton(row, variable=self.pal_var, value=i,
                                command=self.set_active_pal).pack(side=tk.LEFT)
                cv = tk.Canvas(row, width=16 * 8, height=12, highlightthickness=0)
                cv.pack(side=tk.LEFT, padx=2)
                rgb = BUILTINS[p.get("builtin", 0)][1] if p["colors"] is None \
                    else [vce_rgb(c) for c in p["colors"]]
                for k, c in enumerate(rgb):
                    cv.create_rectangle(k * 8, 0, k * 8 + 8, 12,
                                        fill="#%02x%02x%02x" % c, outline="")
                ttk.Label(row, text="%d: %s" % (i, p["label"])).pack(side=tk.LEFT, padx=4)

        def set_active_pal(self):
            if self.active_pal == self.pal_var.get():
                return
            self.active_pal = self.pal_var.get()
            if self.words:
                self.render_sheet()
            self.render_cell()

        def remove_palette(self):
            i = self.pal_var.get()
            if i < NBUILTIN:
                return                      # builtin greys are permanent
            del self.palettes[i]
            for m in self.palmap.values():  # remap cells: gone -> grey, shift the rest
                for k in list(m):
                    if m[k] == i:
                        del m[k]
                    elif m[k] > i:
                        m[k] -= 1
            self.active_pal = 0
            self.refresh_palettes()
            if self.words:
                self.render_sheet()
            self.render_cell()
            self.mark_dirty()

        def add_palette(self):
            if pie is None:
                return
            win = tk.Toplevel(self.root); win.title("Add palette from .inc")
            win.transient(self.root); win.grab_set()
            bar = ttk.Frame(win, padding=4); bar.pack(side=tk.TOP, fill=tk.X)
            ttk.Label(bar, text="File:").pack(side=tk.LEFT)
            src_var = tk.StringVar(value="palette.inc")
            cb = ttk.Combobox(bar, textvariable=src_var, width=24, state="readonly",
                              values=["palette.inc", "palette_org.inc", "other file..."])
            cb.pack(side=tk.LEFT, padx=4)
            body = ttk.Frame(win); body.pack(fill=tk.BOTH, expand=True)
            lb = tk.Listbox(body, width=84, height=22, selectmode=tk.EXTENDED,
                            font=("Consolas", 9))
            vsb = ttk.Scrollbar(body, orient=tk.VERTICAL, command=lb.yview)
            lb.configure(yscrollcommand=vsb.set)
            vsb.pack(side=tk.RIGHT, fill=tk.Y); lb.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            prev = tk.Canvas(win, width=16 * 14, height=16, bg="#181818", highlightthickness=0)
            prev.pack(pady=4)
            slices = []                     # (label, [16 colours])

            def load(path):
                lb.delete(0, tk.END); slices[:] = []
                try:
                    pal = pie.PaletteIncFile(path)
                except Exception as ex:
                    messagebox.showerror("Load", str(ex), parent=win); return
                win.title("Add palette from %s" % os.path.basename(path))
                for (bank, org), b in pal.blocks.items():
                    cols = b["colors"]
                    sec = "SPR" if b.get("section") == "sprite" else \
                          ("BG" if b.get("section") == "BG" else "?")
                    used = pie.compact_used(b.get("used", "?"))
                    fade = (b.get("fade", "") or "").replace("prefade", "fade")
                    nsl = math.ceil(len(cols) / 16.0)
                    for s in range(int(nsl)):
                        sl = cols[s * 16:(s + 1) * 16]
                        n = len(sl)
                        sl = sl + [0] * (16 - n)
                        label = "$%02X:$%04X s%d/%d [%3d/%2d]  %-3s %-14s %s" % (
                            bank, org, s, nsl, len(cols), n, sec, used, fade)
                        slices.append((label, sl))
                        lb.insert(tk.END, label)

            def pick_file():
                sel = src_var.get()
                if sel.startswith("other"):
                    p = filedialog.askopenfilename(initialdir=HERE, parent=win,
                                                   filetypes=[("inc files", "*.inc"), ("all", "*.*")])
                    if not p:
                        return
                else:
                    p = os.path.join(HERE, sel)
                load(p)

            cb.bind("<<ComboboxSelected>>", lambda e: pick_file())

            def preview(ev=None):
                prev.delete("all")
                s = lb.curselection()
                if not s:
                    return
                for k, c in enumerate(slices[s[0]][1]):
                    r, g, b = vce_rgb(c)
                    prev.create_rectangle(k * 14, 0, k * 14 + 14, 16,
                                          fill="#%02x%02x%02x" % (r, g, b), outline="")
            lb.bind("<<ListboxSelect>>", preview)

            def add(ev=None):
                for s in lb.curselection():
                    label, cols = slices[s]
                    self.palettes.append({"label": label, "colors": cols})
                if lb.curselection():
                    self.active_pal = len(self.palettes) - 1
                    self.refresh_palettes()
                    self.mark_dirty()
                win.destroy()
            lb.bind("<Double-1>", add)
            ttk.Button(win, text="Add selected", command=add).pack(pady=4)
            load(os.path.join(HERE, "palette.inc"))

        # ---------- save ----------
        def save(self):
            if not self.path:
                return
            out = bytearray()
            for w in self.words:
                out += bytes((w & 0xFF, w >> 8))
            out = out[:self.nbytes] + bytes(self.nbytes - min(len(out), self.nbytes))
            open(self.path, "wb").write(out)
            sc = {"format": self.fmt, "nbuiltin": NBUILTIN,
                  "default": self.active_pal,
                  "palettes": [{"label": p["label"], "colors": p["colors"]}
                               for p in self.palettes[NBUILTIN:]],
                  "map": self.palmap}
            with open(self.sidecar_path(), "w") as f:
                json.dump(sc, f, indent=1)
            self.mark_dirty(False)
            self.info.config(text="Saved %s + %s" % (os.path.basename(self.path),
                                                     os.path.basename(self.sidecar_path())))

    root = tk.Tk()
    run_gui.app = App(root)          # exposed for scripted testing
    root.mainloop()


if __name__ == "__main__":
    run_gui(sys.argv[1] if len(sys.argv) > 1 else None)
