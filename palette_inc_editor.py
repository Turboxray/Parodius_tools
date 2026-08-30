#!/usr/bin/env python3
"""Parodius Da! palette.inc colour editor.

Two side-by-side palette panels: browse a block into each (via the dropdown or
Browse), edit colours, and copy colours between them by position.  Save writes
all changes back into palette.inc (re-running the build then applies them).

The file parsing/saving lives in PaletteIncFile (no Tk) so it can be tested
headlessly; the Tkinter GUI sits on top.
"""
import os, re, json

HERE = os.path.dirname(os.path.abspath(__file__))
INC_FILE = os.path.join(HERE, "palette.inc")
VCE_IMG  = os.path.join(HERE, "vce_pal.png")
SORT_CFG = os.path.join(HERE, ".palette_editor.json")   # remembered Browse sort

# Default Browse sort: by "used" descending -> Special, L8, L7 ... L1 (you look
# at a level first).  Persisted to SORT_CFG and reused across opens / restarts.
DEFAULT_SORT = [["used", True]]


def load_sort():
    try:
        with open(SORT_CFG) as f:
            sk = json.load(f).get("sortkeys")
        if isinstance(sk, list) and all(isinstance(x, list) and len(x) == 2 for x in sk):
            return [[str(c), bool(r)] for c, r in sk]
    except Exception:
        pass
    return [list(x) for x in DEFAULT_SORT]


def save_sort(sortkeys):
    try:
        with open(SORT_CFG, "w") as f:
            json.dump({"sortkeys": [[c, bool(r)] for c, r in sortkeys]}, f)
    except Exception:
        pass


def used_rank(s):
    """Numeric rank for the 'used' column: OP (opening) and EN (ending) highest,
    then Special, then L8..L1, then 'all levels', then unknown.  Higher = earlier
    when sorted descending."""
    s = s or ""
    best = -1.0
    if re.search(r"\bOP\b", s):
        best = max(best, 98.0)
    if re.search(r"\bEN\b", s):
        best = max(best, 96.0)
    if re.search(r"Special", s):
        best = max(best, 90.0)
    for m in re.finditer(r"\bL(\d+)\b", s):
        best = max(best, float(m.group(1)))
    if best < 0 and "all levels" in s:
        best = 0.5
    return best


def compact_used(s):
    """Display compaction for the 'used' field: Special-1 -> S1, Special-2 -> S2,
    Special -> S (keeps L1..L8, OP, EN, etc. as-is)."""
    return re.sub(r"Special-?(\d*)", lambda m: "S" + m.group(1), s or "")


def compact_cta(s):
    """Display CTAs as 3 hex digits (they never exceed $1F0): $0130 -> $130."""
    out = []
    for tok in (s or "").split(","):
        m = re.match(r"\$?([0-9A-Fa-f]+)$", tok.strip())
        out.append("$%03X" % int(m.group(1), 16) if m else tok.strip())
    return ",".join(out)


def block_sort_key(b, key, col):
    bank, org = key
    if col == "addr":
        return bank * 0x10000 + org
    if col == "colours":
        try: return int(b.get("colours", 0))
        except (TypeError, ValueError): return 0
    if col == "used":
        return used_rank(b.get("used", ""))
    if col == "edited":
        return 1 if b.get("edited") else 0
    if col == "fade":
        m = re.match(r"(fade|prefade)\s+\$([0-9A-Fa-f]+)\s+(\d+)/(\d+)", b.get("fade", "") or "")
        if not m:
            return (2, 0, 0)
        return (0 if m.group(1) == "fade" else 1, int(m.group(2), 16), int(m.group(3)))
    if col == "subpal":
        m = re.match(r"\s*(\d+)", b.get("subpal", "") or "")
        return int(m.group(1)) if m else -1
    return str(b.get(col, ""))


def order_keys(blocks, sortkeys):
    keys = sorted(blocks.keys())                 # stable tiebreak by (bank, org)
    for col, rev in reversed(sortkeys):
        keys.sort(key=lambda k: block_sort_key(blocks[k], k, col), reverse=rev)
    return keys


# ----------------------------------------------------------------------------
# File model (no GUI) -- parse blocks, edit colours, write back
# ----------------------------------------------------------------------------
class PaletteIncFile:
    """Loads palette.inc and exposes blocks keyed by (bank, org)."""

    def __init__(self, path=INC_FILE):
        self.path = path
        with open(path, "r") as f:
            self.lines = f.read().split("\n")
        self.blocks = {}          # (bank, org) -> dict
        self.orig_colors = {}     # (bank, org) -> [9-bit colours] from the original (for MODIFIED tag)
        self._parse()

    # colour helpers (3-bit r,g,b <-> 9-bit GGGRRRBBB, matching the pal8 macro)
    @staticmethod
    def rgb_to9(r, g, b):
        return ((g & 7) << 6) | ((r & 7) << 3) | (b & 7)

    @staticmethod
    def to_rgb(c):
        return ((c >> 3) & 7, (c >> 6) & 7, c & 7)   # r, g, b

    @staticmethod
    def _exp8(v):
        return int(v * 255 / 7 + 0.5)                # 3-bit level -> 8-bit (matches generator)

    def _parse(self):
        n = len(self.lines)
        i = 0
        while i < n:
            mh = re.match(r"^; --- block \$([0-9A-Fa-f]+)\s*:\s*CTA\s+(\S+)\s+(.*?)\s*\|", self.lines[i])
            if not mh:
                i += 1
                continue
            info = {"abs": int(mh.group(1), 16), "cta": mh.group(2), "where": mh.group(3),
                    "header": self.lines[i], "hline": i}
            bank = org = count = None
            cstart = cend = None
            j = i + 1
            while j < n and not self.lines[j].startswith("; --- block"):
                l = self.lines[j]
                m = re.match(r"^\s*\.bank \$([0-9A-Fa-f]+)", l)
                if m: bank = int(m.group(1), 16)
                m = re.match(r"^\s*\.org \$([0-9A-Fa-f]+)", l)
                if m: org = int(m.group(1), 16)
                m = re.match(r"^\s*\.db \$([0-9A-Fa-f]+)", l)
                if m: count = int(m.group(1), 16)
                if re.match(r"^\s*(pal8 |; #)", l):
                    if cstart is None: cstart = j
                    cend = j
                j += 1
            if bank is not None and org is not None and cstart is not None:
                info.update(bank=bank, org=org, count=count, cstart=cstart, cend=cend,
                            colors=self._parse_colors(cstart, cend))
                h = info["header"]
                info["section"] = "sprite" if "sprite palette" in h else ("BG" if "BG palette" in h else "?")
                mu = re.search(r"used:\s*(.*?)\s*(?:\||\*\*\*|---\s*$)", h)
                info["used"] = mu.group(1).strip() if mu else "?"
                info["edited"] = "MODIFIED" in h
                mf = re.search(r"\|\s*((?:pre)?fade)\s+\$([0-9A-Fa-f]+)\s+(\d+)/(\d+)", h)
                info["fade"] = ("%s $%s %s/%s" % mf.group(1, 2, 3, 4)) if mf else ""
                ms = re.search(r"palette\s+([\d,\- ]+)", h)
                info["subpal"] = ms.group(1).strip() if ms else ""
                info["colours"] = (count + 1) * 8 if count is not None else len(info["colors"])
                self.blocks[(bank, org)] = info
            i = j

    def _parse_colors(self, cstart, cend):
        cols = []
        for k in range(cstart, cend + 1):
            for m in re.finditer(r"rgb\((\d+),(\d+),(\d+)\)", self.lines[k]):
                cols.append(self.rgb_to9(int(m.group(1)), int(m.group(2)), int(m.group(3))))
        return cols

    def get(self, bank, org):
        return self.blocks.get((bank, org))

    def _emit_colors(self, colors):
        """Regenerate the #RRGGBB + pal8 lines for a colour list (matches gen_palette_inc.pl)."""
        out = []
        groups = [colors[i:i + 8] for i in range(0, len(colors), 8)]
        gi = 0
        while gi < len(groups):
            pair = groups[gi:gi + 2]
            flat = [c for g in pair for c in g]
            hexs = " ".join("#%02x%02x%02x" % (self._exp8(self.to_rgb(c)[0]),
                                               self._exp8(self.to_rgb(c)[1]),
                                               self._exp8(self.to_rgb(c)[2])) for c in flat)
            out.append("    ; " + hexs)
            for g in pair:
                out.append("    pal8 " + ", ".join("rgb(%d,%d,%d)" % self.to_rgb(c) for c in g))
            gi += 2
        return out

    def set_colors(self, bank, org, colors):
        b = self.blocks[(bank, org)]
        assert len(colors) == len(b["colors"]), "colour count must not change"
        b["colors"] = list(colors)

    def save(self):
        """Rewrite each block's colour region (same line count) and refresh its
        '*** MODIFIED: N ***' header tag (vs orig_colors, if known), then write."""
        for key in sorted(self.blocks, key=lambda k: -self.blocks[k]["cstart"]):
            b = self.blocks[key]
            new = self._emit_colors(b["colors"])
            assert len(new) == b["cend"] - b["cstart"] + 1, "regenerated region size changed"
            self.lines[b["cstart"]:b["cend"] + 1] = new
            if key in self.orig_colors:
                mod = sum(1 for a, o in zip(b["colors"], self.orig_colors[key]) if a != o)
                h = re.sub(r"\s*\*\*\* MODIFIED:[^*]*\*\*\*", "", b["header"])  # strip old tag
                if mod > 0:
                    tag = "  *** MODIFIED: %d colour%s ***" % (mod, "" if mod == 1 else "s")
                    h = re.sub(r"\s*---\s*$", tag + " ---", h)
                self.lines[b["hline"]] = h
                b["header"] = h
        with open(self.path, "w", newline="\n") as f:   # keep LF; don't let Windows write CRLF
            f.write("\n".join(self.lines))


# ----------------------------------------------------------------------------
# GUI
# ----------------------------------------------------------------------------
def run_gui():
    import tkinter as tk
    from tkinter import ttk, messagebox
    try:
        from PIL import Image
    except ImportError:
        Image = None

    BOX = 24

    class PalettePanel:
        """One palette view: quick-browse dropdown + Browse, a colour grid with
        multi-select (Ctrl+click), and a colour editor.  Edits a working copy of
        one block; App.save() commits every panel to palette.inc."""

        def __init__(self, app, parent, title):
            self.app = app
            self.title = title
            self.key = None
            self.colors = []
            self.orig = []
            self.sel = None            # last-clicked index (drives the editor)
            self.selset = set()        # multi-selection (for copy)
            self.staged = 0
            self._nav_keys = []

            f = ttk.LabelFrame(parent, text=title, padding=6)
            self.frame = f
            nb = ttk.Frame(f); nb.pack(side=tk.TOP, fill=tk.X)
            ttk.Button(nb, text="Browse...", command=self.browse).pack(side=tk.LEFT)
            ttk.Button(nb, text="<", width=2, command=lambda: self.nav_step(-1)).pack(side=tk.LEFT, padx=(6, 0))
            self.nav = ttk.Combobox(nb, width=30, state="readonly")
            self.nav.pack(side=tk.LEFT, fill=tk.X, expand=True)
            self.nav.bind("<<ComboboxSelected>>", self.nav_select)
            ttk.Button(nb, text=">", width=2, command=lambda: self.nav_step(1)).pack(side=tk.LEFT)
            self.info = ttk.Label(f, text="(no block loaded)"); self.info.pack(side=tk.TOP, fill=tk.X, pady=(3, 3))

            mid = ttk.Frame(f); mid.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
            self.canvas = tk.Canvas(mid, width=16 * (BOX + 2) + 8, height=9 * (BOX + 2) + 8,
                                    bg="#1a1a1a", highlightthickness=0)
            vsb = ttk.Scrollbar(mid, orient=tk.VERTICAL, command=self.canvas.yview)
            self.canvas.configure(yscrollcommand=vsb.set)
            vsb.pack(side=tk.RIGHT, fill=tk.Y)
            self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            self.canvas.bind("<Button-1>", lambda e: self.click(e, False))
            self.canvas.bind("<Control-Button-1>", lambda e: self.click(e, True))
            self.canvas.bind("<MouseWheel>", lambda e: self.canvas.yview_scroll(int(-e.delta / 120), "units"))

            ed = ttk.LabelFrame(f, text="Colour (r,g,b 0-7)", padding=6); ed.pack(side=tk.TOP, fill=tk.X, pady=(4, 0))
            self.lbl_sel = ttk.Label(ed, text="Select a colour"); self.lbl_sel.grid(row=0, column=0, columnspan=8, sticky=tk.W)
            self.sw_cur = tk.Label(ed, width=8, height=2, bg="#333"); self.sw_cur.grid(row=1, column=0, padx=3, pady=3)
            self.sw_new = tk.Label(ed, width=8, height=2, bg="#333"); self.sw_new.grid(row=1, column=1, padx=3, pady=3)
            self.scales = {}
            for idx, ch in enumerate("RGB"):
                ttk.Label(ed, text=ch).grid(row=1, column=2 + idx * 2, sticky=tk.E)
                s = tk.Scale(ed, from_=0, to=7, orient=tk.HORIZONTAL, length=70, command=lambda e: self.stage())
                s.grid(row=1, column=3 + idx * 2); self.scales[ch] = s
            self.btn_apply = ttk.Button(ed, text="Apply (Enter)", command=self.apply, state=tk.DISABLED)
            self.btn_apply.grid(row=2, column=0, columnspan=8, pady=3, sticky=tk.W)

        def palmap(self):
            return self.app._palmap()

        def refresh_nav(self):
            pal = self.app.pal
            if not pal:
                return
            self._nav_keys = order_keys(pal.blocks, self.app.sortkeys)
            vals = []
            for (bk, og) in self._nav_keys:
                b = pal.blocks[(bk, og)]
                fade = (b.get("fade", "") or "").replace("prefade", "fade")
                sec = "SPR" if b.get("section") == "sprite" else ("BG" if b.get("section") == "BG" else "?")
                vals.append("$%02X:$%04X  %-3s %-5s [%d] %s%s"
                            % (bk, og, sec, compact_cta(b.get("cta", "")), b.get("colours", 0),
                               compact_used(b.get("used", "?")), "  " + fade if fade else ""))
            self.nav["values"] = vals
            self.nav_sync()

        def nav_sync(self):
            if self.key in self._nav_keys:
                self.nav.current(self._nav_keys.index(self.key))

        def nav_select(self, ev=None):
            i = self.nav.current()
            if 0 <= i < len(self._nav_keys):
                self.load(*self._nav_keys[i])

        def nav_step(self, d):
            if not self._nav_keys:
                return
            i = self.nav.current()
            i = 0 if i < 0 else max(0, min(len(self._nav_keys) - 1, i + d))
            self.nav.current(i)
            self.nav_select()

        def browse(self):
            self.app.browse(self)

        def load(self, bank, org):
            b = self.app.pal.get(bank, org)
            if not b:
                return
            self.key = (bank, org)
            self.colors = list(b["colors"]); self.orig = list(b["colors"])
            self.sel = None; self.selset = set(); self._toggle(False)
            self.lbl_sel.config(text="Select a colour")
            self.info.config(text="$%02X:$%04X  CTA %s  %s  -  %d colours"
                             % (bank, org, compact_cta(b["cta"]), b["where"], len(self.colors)))
            self.draw(); self.nav_sync()
            self.app.update_copy_state()

        def draw(self):
            self.canvas.delete("all")
            pm = self.palmap()
            for i, c in enumerate(self.colors):
                row, col = divmod(i, 16)
                x, y = 4 + col * (BOX + 2), 4 + row * (BOX + 2)
                fill = "#%02x%02x%02x" % pm.get(c, (0, 0, 0))
                if i == self.sel:
                    outline, w = "#ffffff", 3
                elif i in self.selset:
                    outline, w = "#ffcc33", 3
                else:
                    outline, w = "#444", 1
                self.canvas.create_rectangle(x, y, x + BOX, y + BOX, fill=fill, outline=outline, width=w)
            rows = (len(self.colors) + 15) // 16
            self.canvas.configure(scrollregion=(0, 0, 16 * (BOX + 2) + 8, max(rows, 1) * (BOX + 2) + 8))

        def _index_at(self, ev):
            col = (int(self.canvas.canvasx(ev.x)) - 4) // (BOX + 2)
            row = (int(self.canvas.canvasy(ev.y)) - 4) // (BOX + 2)
            i = row * 16 + col
            return i if (0 <= col < 16 and 0 <= i < len(self.colors)) else None

        def click(self, ev, ctrl):
            i = self._index_at(ev)
            if i is None:
                return
            self.app.active = self     # last-clicked panel = Ctrl+C/V target
            if ctrl:
                self.selset.discard(i) if i in self.selset else self.selset.add(i)
            else:
                self.selset = {i}
            self.sel = i
            self.staged = self.colors[i]
            self._toggle(True)        # enable first: .set() on a disabled Scale is ignored,
            r, g, b = PaletteIncFile.to_rgb(self.colors[i])   # which broke the first click after load
            self.scales["R"].set(r); self.scales["G"].set(g); self.scales["B"].set(b)
            self.stage(); self.draw()
            self.app.update_copy_state()

        def selection(self):
            return sorted(self.selset) if self.selset else ([self.sel] if self.sel is not None else [])

        def _toggle(self, on):
            st = tk.NORMAL if on else tk.DISABLED
            for s in self.scales.values(): s.config(state=st)
            self.btn_apply.config(state=st)

        def stage(self):
            if self.sel is None:
                return
            r, g, b = self.scales["R"].get(), self.scales["G"].get(), self.scales["B"].get()
            self.staged = PaletteIncFile.rgb_to9(r, g, b)
            pm = self.palmap()
            self.lbl_sel.config(text="Index %d   $%03X -> $%03X (r%d g%d b%d)   [%d selected]"
                                % (self.sel, self.colors[self.sel], self.staged, r, g, b, len(self.selection())))
            self.sw_cur.config(bg="#%02x%02x%02x" % pm.get(self.colors[self.sel], (0, 0, 0)))
            self.sw_new.config(bg="#%02x%02x%02x" % pm.get(self.staged, (0, 0, 0)))

        def apply(self):
            if self.sel is None:
                return
            self.colors[self.sel] = self.staged
            self.draw(); self.stage()

        def commit(self):
            if self.key:
                self.app.pal.set_colors(self.key[0], self.key[1], self.colors)

    class App:
        def __init__(self, root):
            self.root = root
            root.title("Parodius palette.inc editor")
            self.pal = None
            self.active = None        # panel that was last clicked (Ctrl+C/V target)
            self.clip = []            # colour clipboard (9-bit values)
            self.sortkeys = load_sort()
            self.rgb_master = {i: (int(((i >> 3) & 7) / 7 * 255),
                                   int(((i >> 6) & 7) / 7 * 255),
                                   int((i & 7) / 7 * 255)) for i in range(512)}
            self.alt = dict(self.rgb_master)
            if Image and os.path.exists(VCE_IMG):
                try:
                    px = list(Image.open(VCE_IMG).convert("RGB").getdata())
                    for i in range(min(512, len(px))):
                        self.alt[i] = px[i][:3]
                except Exception:
                    pass
            self._build()
            self._reload_file()

        def _build(self):
            self.root.minsize(940, 560)
            top = ttk.Frame(self.root, padding=6); top.pack(side=tk.TOP, fill=tk.X)
            ttk.Button(top, text="Reload file", command=self._reload_file).pack(side=tk.LEFT)
            # SOURCE selector: what the panels load/browse from. Saving always
            # writes to palette.inc (the build input) regardless of source.
            ttk.Label(top, text="  Source:").pack(side=tk.LEFT)
            self.src_var = tk.StringVar(value="palette.inc (working)")
            src = ttk.Combobox(top, textvariable=self.src_var, width=24, state="readonly",
                               values=["palette.inc (working)",
                                       "palette_org.inc (original)",
                                       "other file..."])
            src.pack(side=tk.LEFT, padx=(2, 8))
            src.bind("<<ComboboxSelected>>", lambda e: self._pick_source())
            self.use_vce = tk.BooleanVar(value=True)
            ttk.Checkbutton(top, text="VCE colours", variable=self.use_vce,
                            command=self._toggle_pal).pack(side=tk.LEFT, padx=12)
            ttk.Button(top, text="Save to palette.inc", command=self.save).pack(side=tk.RIGHT)
            self.info = ttk.Label(self.root, text="", padding=(6, 0)); self.info.pack(side=tk.TOP, fill=tk.X)

            main = ttk.Frame(self.root); main.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=6, pady=6)
            self.left = PalettePanel(self, main, "Palette A  (editing target)")
            self.left.frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            cc = ttk.Frame(main); cc.pack(side=tk.LEFT, fill=tk.Y, padx=6)
            ttk.Label(cc, text="copy\nselected\ncolours").pack(side=tk.TOP, pady=(60, 6))
            self.btn_l2r = ttk.Button(cc, text="A  >  B", width=8,
                                      command=lambda: self.copy(self.left, self.right), state=tk.DISABLED)
            self.btn_l2r.pack(side=tk.TOP, pady=2)
            self.btn_r2l = ttk.Button(cc, text="A  <  B", width=8,
                                      command=lambda: self.copy(self.right, self.left), state=tk.DISABLED)
            self.btn_r2l.pack(side=tk.TOP, pady=2)
            self.copy_note = ttk.Label(cc, text="", wraplength=78, justify=tk.CENTER)
            self.copy_note.pack(side=tk.TOP, pady=6)
            ttk.Label(cc, text="Ctrl+C copy\nCtrl+V paste\n(any position,\neither way)",
                      justify=tk.CENTER).pack(side=tk.TOP, pady=(18, 0))
            self.right = PalettePanel(self, main, "Palette B  (source)")
            self.right.frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            self.root.bind("<Return>", lambda e: self._apply_focused())
            self.root.bind("<Control-c>", lambda e: self.clip_copy())
            self.root.bind("<Control-v>", lambda e: self.clip_paste())

        def _apply_focused(self):
            for p in (self.left, self.right):
                if p.sel is not None:
                    p.apply(); return

        def _palmap(self):
            return self.alt if self.use_vce.get() else self.rgb_master

        def _toggle_pal(self):
            for p in (self.left, self.right):
                p.draw()
                if p.sel is not None:
                    p.stage()

        def _pick_source(self):
            sel = self.src_var.get()
            if sel.startswith("other"):
                from tkinter import filedialog
                p = filedialog.askopenfilename(initialdir=HERE, title="Source .inc",
                                               filetypes=[("inc files", "*.inc"), ("all", "*.*")])
                if not p:
                    self.src_var.set(os.path.basename(getattr(self, "src_path", INC_FILE)))
                    return
                self.src_path = p
            elif sel.startswith("palette_org"):
                self.src_path = os.path.join(HERE, "palette_org.inc")
            else:
                self.src_path = INC_FILE
            self._reload_file()

        def _reload_file(self):
            try:
                src = getattr(self, "src_path", INC_FILE)
                self.pal = PaletteIncFile(src)
                org_path = os.path.join(HERE, "palette_org.inc")
                if os.path.exists(org_path):
                    org = PaletteIncFile(org_path)
                    self.pal.orig_colors = {k: b["colors"] for k, b in org.blocks.items()}
                note = "" if self.pal.orig_colors else " (palette_org.inc missing: no MODIFIED tags)"
                self.info.config(text="Loaded %s (%d blocks)%s.  Saving writes palette.inc."
                                 % (os.path.basename(src), len(self.pal.blocks), note))
                for p in (self.left, self.right):
                    p.refresh_nav()
                    if p.key and self.pal.get(*p.key):
                        p.load(*p.key)
                    elif p._nav_keys:
                        p.load(*p._nav_keys[0])
                self.update_copy_state()
            except Exception as ex:
                messagebox.showerror("Load error", str(ex))

        def update_copy_state(self):
            both = bool(self.left.key) and bool(self.right.key)
            same = both and len(self.left.colors) == len(self.right.colors)
            st = tk.NORMAL if same else tk.DISABLED
            self.btn_l2r.config(state=st); self.btn_r2l.config(state=st)
            if not both:
                self.copy_note.config(text="load both panels")
            elif not same:
                self.copy_note.config(text="counts differ\n(%d vs %d)" % (len(self.left.colors), len(self.right.colors)))
            else:
                self.copy_note.config(text="same #subpalettes - OK")

        def copy(self, src, dst):
            if not src.key or not dst.key:
                return
            if len(src.colors) != len(dst.colors):
                messagebox.showwarning("Copy", "The two palettes have different colour counts; can't copy by position.")
                return
            idxs = src.selection()
            if not idxs:
                messagebox.showinfo("Copy", "Select one or more colours in the source panel first (Ctrl+click for several).")
                return
            for i in idxs:
                dst.colors[i] = src.colors[i]
            dst.draw()
            if dst.sel is not None:
                dst.staged = dst.colors[dst.sel]; dst.stage()
            self.info.config(text="Copied %d colour%s %s (not saved yet - hit Save to commit)."
                             % (len(idxs), "" if len(idxs) == 1 else "s",
                                "A -> B" if dst is self.right else "B -> A"))

        def clip_copy(self):
            """Ctrl+C: copy the selected colour(s) of the last-clicked panel to the
            colour clipboard (position-independent, unlike the A>B buttons)."""
            p = self.active
            if not p or not p.key:
                return
            idxs = p.selection()
            if not idxs:
                self.info.config(text="Ctrl+C: click a colour first."); return
            self.clip = [p.colors[i] for i in idxs]
            try:                       # mirror as text for pasting outside the app
                self.root.clipboard_clear()
                self.root.clipboard_append(" ".join("$%03X" % c for c in self.clip))
            except tk.TclError:
                pass
            which = "A" if p is self.left else "B"
            self.info.config(text="Copied %d colour%s from Palette %s: %s"
                             % (len(self.clip), "" if len(self.clip) == 1 else "s", which,
                                " ".join("$%03X" % c for c in self.clip[:16])))

        def clip_paste(self):
            """Ctrl+V: paste the colour clipboard into the last-clicked panel.
            1 colour -> fills every selected swatch; N colours onto N selected ->
            pairs them in index order; otherwise pastes the run starting at the
            last-clicked swatch (clipped at the end of the block)."""
            p = self.active
            if not p or not p.key or not self.clip:
                if not self.clip:
                    self.info.config(text="Ctrl+V: nothing copied yet (Ctrl+C first).")
                return
            sel = p.selection()
            if not sel:
                self.info.config(text="Ctrl+V: click a destination swatch first."); return
            if len(self.clip) == 1:
                for i in sel:
                    p.colors[i] = self.clip[0]
                n = len(sel)
            elif len(self.clip) == len(sel):
                for i, c in zip(sel, self.clip):
                    p.colors[i] = c
                n = len(sel)
            else:
                start = p.sel if p.sel is not None else sel[0]
                n = 0
                for off, c in enumerate(self.clip):
                    if start + off >= len(p.colors):
                        break
                    p.colors[start + off] = c; n += 1
            p.draw()
            if p.sel is not None:
                p.staged = p.colors[p.sel]
                r, g, b = PaletteIncFile.to_rgb(p.staged)
                p.scales["R"].set(r); p.scales["G"].set(g); p.scales["B"].set(b)
                p.stage()
            which = "A" if p is self.left else "B"
            self.info.config(text="Pasted %d colour%s into Palette %s (not saved yet - hit Save to commit)."
                             % (n, "" if n == 1 else "s", which))

        def browse(self, target):
            if not self.pal:
                return
            win = tk.Toplevel(self.root); win.title("Load into %s" % target.title)
            win.geometry("820x520"); win.transient(self.root); win.grab_set()
            bar = ttk.Frame(win); bar.pack(side=tk.BOTTOM, fill=tk.X)
            body = ttk.Frame(win); body.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
            cols = ("addr", "section", "subpal", "colours", "fade", "used", "edited")
            widths = {"addr": 90, "section": 60, "subpal": 100, "colours": 55,
                      "fade": 140, "used": 240, "edited": 55}
            tv = ttk.Treeview(body, columns=cols, show="headings")
            for c in cols:
                tv.heading(c, text=c.capitalize())
                tv.column(c, width=widths[c], anchor=tk.W)
            vsb = ttk.Scrollbar(body, orient=tk.VERTICAL, command=tv.yview)
            tv.configure(yscrollcommand=vsb.set)
            vsb.pack(side=tk.RIGHT, fill=tk.Y); tv.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            for (bank, org), b in self.pal.blocks.items():
                tv.insert("", tk.END, iid="%02X_%04X" % (bank, org), values=(
                    "$%02X:$%04X" % (bank, org), b.get("section", "?"), b.get("subpal", ""),
                    b.get("colours", 0), (b.get("fade", "") or "").replace("prefade", "fade"), b.get("used", "?"),
                    "yes" if b.get("edited") else ""))

            def resort():
                for i, k in enumerate(order_keys(self.pal.blocks, self.sortkeys)):
                    tv.move("%02X_%04X" % k, "", i)
                rank = {c: (n + 1, r) for n, (c, r) in enumerate(self.sortkeys)}
                for c in cols:
                    t = c.capitalize()
                    if c in rank:
                        n, r = rank[c]; t += "  %s%d" % ("v" if r else "^", n)
                    tv.heading(c, text=t)
                save_sort(self.sortkeys)
                self.left.refresh_nav(); self.right.refresh_nav()

            def on_head(col, shift):
                sk = self.sortkeys
                ex = next((k for k in sk if k[0] == col), None)
                if shift:
                    if ex: ex[1] = not ex[1]
                    else: sk.append([col, False])
                else:
                    if ex and len(sk) == 1: ex[1] = not ex[1]
                    else: sk[:] = [[col, False]]
                resort()

            def on_click(e):
                if tv.identify_region(e.x, e.y) != "heading":
                    return
                cid = tv.identify_column(e.x); idx = int(cid[1:]) - 1
                if 0 <= idx < len(cols):
                    on_head(cols[idx], bool(e.state & 0x0001))
                return "break"
            tv.bind("<Button-1>", on_click)
            resort()

            def pick(ev=None):
                sel = tv.selection()
                if not sel:
                    return
                bank, org = int(sel[0][:2], 16), int(sel[0][3:], 16)
                win.destroy(); target.load(bank, org)
            tv.bind("<Double-1>", pick)
            ttk.Label(bar, text="Loading into %s.  Click header to sort; Shift+click sub-sort; double-click to open."
                      % target.title).pack(side=tk.LEFT, padx=6)
            ttk.Button(bar, text="Open selected", command=pick).pack(side=tk.RIGHT, padx=6, pady=6)

        def save(self):
            if not self.pal:
                return
            if not (self.left.key or self.right.key):
                messagebox.showwarning("Save", "Load a block first."); return
            # destination is ALWAYS palette.inc (the build input), regardless
            # of which source file the panels are showing
            src = getattr(self, "src_path", INC_FILE)
            if src == INC_FILE:
                dest = self.pal
            else:
                dest = PaletteIncFile(INC_FILE)
                dest.orig_colors = dict(self.pal.orig_colors)
            skipped = []
            for p in (self.left, self.right):
                if p.key:
                    if dest.get(*p.key):
                        dest.set_colors(p.key[0], p.key[1], p.colors)
                    else:
                        skipped.append("$%02X:$%04X" % p.key)
            dest.save()
            self.left.orig = list(self.left.colors); self.right.orig = list(self.right.colors)
            self.left.refresh_nav(); self.right.refresh_nav()
            msg = "Wrote palette.inc. Re-run the build to apply."
            if skipped:
                msg += "\n(Not in palette.inc, skipped: %s)" % ", ".join(skipped)
            messagebox.showinfo("Saved", msg)

    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    run_gui()
