#!/usr/bin/env python3
"""SF2-build graphics tool for Parodius Da! (J).

  pce_sf2_mapper_prep.py extract <rom> [manifest]   decompress every stream listed in
      compressed_gfx_table.txt from the ROM into gfx_bins/ and generate
      Parodius_SF2_assets.inc (expansion asset banks + lookup tables)
  pce_sf2_mapper_prep.py zero [pce]                 blank the dead original graphics
      region ($080000-$0FFFFF) in the assembled image (default
      Parodius_SF2.pce)

Contains a bit-exact reimplementation of the game's graphics decompressor
(verified against live VRAM captures), including the flip variants the
sprite writer applies at decompress time. See compressed_gfx_table.txt for the
full stream map.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))

FIRST_BANK = 0x80          # LUT bank; assets from $81
BANK_SIZE = 0x2000


# ----------------------------------------------------------------------------
# Decompressor (bit-exact reimplementation)
# ----------------------------------------------------------------------------
import re
import sys


def file_off(bank, logical):
    """CPU logical $4000-$BFFF with banks bank..bank+3 in MPR2-5."""
    return (bank + (logical - 0x4000) // 0x2000) * 0x2000 + (logical & 0x1FFF)


def decode_stream(rom, off):
    """Run the control stream at rom[off:]. Returns (header, dict_bytes, out)."""
    hdr = rom[off]
    dictlen = hdr & 0x7F
    dic = rom[off + 1: off + 1 + dictlen]
    p = off + 1 + dictlen
    out = bytearray()

    def n256(v):
        return 256 if v == 0 else v

    while True:
        t = rom[p]
        if t == 0xFF:
            break
        elif t == 0x00:
            cnt, fix = n256(rom[p + 1]), rom[p + 2]
            for i in range(cnt):
                out += bytes((fix, rom[p + 3 + i]))
            p += 3 + cnt
        elif t == 0x01:
            cnt = rom[p + 1] | (rom[p + 2] << 8)
            out += bytes([rom[p + 3]]) * cnt
            p += 4
        elif t == 0x02:
            cnt = n256(rom[p + 1])
            out += bytes((rom[p + 2], rom[p + 3])) * cnt
            p += 4
        elif t < 0x40:                       # $03-$3F
            out += bytes([rom[p + 1]]) * t
            p += 2
        elif t < 0x80:                       # $40-$7F
            out += b"\x00" * n256(t & 0x3F)
            p += 1
        elif t == 0x80:
            cnt = rom[p + 1] | (rom[p + 2] << 8)
            out += rom[p + 3: p + 3 + cnt]
            p += 3 + cnt
        elif t < 0xC0:                       # $81-$BF
            n = t & 0x3F
            out += rom[p + 1: p + 1 + n]
            p += 1 + n
        elif t < 0xFE:                       # $C0-$FD
            n = n256(t & 0x3F)
            for i in range(n):
                out += bytes((0, rom[p + 1 + i]))
            p += 1 + n
        else:                                # $FE
            cnt = n256(rom[p + 1])
            out += rom[p + 2: p + 6] * cnt
            p += 6
    return hdr, dic, bytes(out), p + 1 - off   # +1: include the $FF


def bitrev(b):
    r = 0
    for _ in range(8):
        r = ((r << 1) | (b & 1)) & 0xFF
        b >>= 1
    return r


class WriterSim:
    """Faithful simulation of the byte writer $C3FD + flush paths $C400/$C44B.

    WRAM $3C00-$3CFF modelled as self.w (buffer lives at $3C80; the sprite
    remap also touches $3C7F).  Tile mode (hdr bit7 clear): 128-byte chunks,
    optional in-place dictionary remap (ROL pipeline), linear flush.  Sprite
    mode (hdr bit7 set): 32-byte chunks, optional per-byte bit-reverse
    (p1 bit0 = hflip), optional descending flush (p1 bit1 = vflip)."""

    def __init__(self, hdr, p1, table):
        self.sprite = bool(hdr & 0x80)
        self.dict_on = bool(hdr & 0x7F)
        self.p1 = p1
        self.table = table               # 16 bytes at src+1
        self.w = bytearray(0x100)
        self.fb = 0
        self.out = bytearray()

    def _rol_mem(self, idx, c):
        old = self.w[idx]
        self.w[idx] = ((old << 1) | c) & 0xFF
        return old >> 7

    def _remap(self, offsets, x):
        a = 0
        for _ in range(9):    # $07=8 counts down THROUGH 0 (BPL): 9 passes -
                              # pass 0 primes the pipeline, its bit falls off
            a = self.table[a & 0x0F]
            c = a >> 7
            a = (a << 1) & 0xFF          # ASL A
            for off in offsets:
                c2 = self._rol_mem(off + x, c)          # ROL mem,X
                c = a >> 7
                a = ((a << 1) | c2) & 0xFF              # ROL A

    def put(self, b):
        if self.sprite:
            if self.p1 & 1:
                b = bitrev(b)
            x = self.fb
            self.w[0x80 + x] = b
            self.fb += 1
            if x < 0x1F:
                return
            self.fb = 0
            if self.dict_on:
                xx = 0x0F
                while xx >= 0:
                    self._remap((0x90, 0x8F, 0x80, 0x7F), xx)
                    xx -= 2
            if self.p1 & 2:              # vflip: descending pair flush
                for base in (0x7F, 0x8F):
                    xx = 0x0F
                    while xx >= 0:
                        self.out += bytes((self.w[base + xx],
                                           self.w[base + 1 + xx]))
                        xx -= 2
            else:
                self.out += self.w[0x80:0xA0]
        else:
            self.w[0x80 + self.fb] = b
            self.fb += 1
            if self.fb < 0x80:
                return
            self.fb = 0
            if self.dict_on:
                for xx in range(0x1F, -1, -1):
                    self._remap((0xE0, 0xC0, 0xA0, 0x80), xx)
            self.out += self.w[0x80:0x100]


def decode_block(rom, bank, src, p1=0):
    hdr, dic, out, _ = decode_block_full(rom, bank, src, p1)
    return hdr, dic, out


def decode_block_full(rom, bank, src, p1=0):
    """Also returns the compressed stream length (header+dict+tokens+$FF)."""
    off = file_off(bank, src)
    hdr, dic, stream, clen = decode_stream(rom, off)
    sim = WriterSim(hdr, p1, rom[off + 1: off + 17])
    for b in stream:
        sim.put(b)
    return hdr, dic, bytes(sim.out), clen


def verify(rom, trace_path):
    """Compare decoder output against gfxtrace VRAM dumps."""
    entries = []
    hdr_re = re.compile(
        r"ROMDEC F=(\d+) stage=\$(\w+) slot=(\d+) bank=\$(\w+) p1=\$(\w+) "
        r"dst=\$(\w+)\.w src=\$(\w+) words=(\d+)")
    cur = None
    for ln in open(trace_path):
        m = hdr_re.match(ln)
        if m:
            cur = {"bank": int(m.group(4), 16), "p1": int(m.group(5), 16),
                   "dst": int(m.group(6), 16), "src": int(m.group(7), 16),
                   "words": int(m.group(8)), "vram": [],
                   "frame": int(m.group(1)), "stage": int(m.group(2), 16)}
            entries.append(cur)
        elif cur is not None and ln.startswith("  ") and not ln.startswith("  ("):
            cur["vram"] += [int(w, 16) for w in ln.split()]

    seen = set()
    stats = {"raw_ok": 0, "raw_bad": 0, "planar_skip": 0}
    for e in entries:
        key = (e["bank"], e["src"], e["p1"])   # p1 changes output (flips)
        if key in seen:
            continue
        seen.add(key)
        hdr, dic, out = decode_block(rom, e["bank"], e["src"], e["p1"])
        words = [out[i] | (out[i + 1] << 8) for i in range(0, len(out) - 1, 2)]
        mode = ("sprite" if hdr & 0x80 else "tile") + \
               ("+dict" if hdr & 0x7F else "-raw")
        tag = "bank=$%02X src=$%04X hdr=$%02X p1=$%02X %-11s out=%dB vram=%dw" % (
            e["bank"], e["src"], hdr, e["p1"], mode, len(out), len(e["vram"]))
        n = min(len(words), len(e["vram"]))
        bad = [i for i in range(n) if words[i] != e["vram"][i]]
        if not bad and n > 0:
            stats["ok"] = stats.get("ok", 0) + 1
            print("OK        " + tag)
        else:
            stats["bad"] = stats.get("bad", 0) + 1
            print("MISMATCH  %s  first-bad=%s" %
                  (tag, ("word %d: mine %04X vs vram %04X" %
                         (bad[0], words[bad[0]], e["vram"][bad[0]])) if bad else "len 0"))
    print("\n%d unique blocks: %d ok, %d mismatch"
          % (len(seen), stats.get("ok", 0), stats.get("bad", 0)))


# ----------------------------------------------------------------------------
# Asset extraction / SF2 expansion generation
# ----------------------------------------------------------------------------
def read_manifest(path):
    entries = []
    for ln in open(path):
        ln = ln.strip()
        if not ln or ln.startswith(";"):
            continue
        f = ln.split()
        entries.append({"bank": int(f[0], 16), "src": int(f[1], 16),
                        "p1": int(f[2], 16), "dst": int(f[6], 16)})
    return entries


def extract(argv):
    rom = open(argv[0], "rb").read()
    manifest = argv[1] if len(argv) > 1 else os.path.join(HERE, "compressed_gfx_table.txt")
    entries = read_manifest(manifest)

    bindir = os.path.join(HERE, "gfx_bins")
    os.makedirs(bindir, exist_ok=True)

    assets = []
    for e in entries:
        hdr, dic, out, clen = decode_block_full(rom, e["bank"], e["src"], e["p1"])
        name = "%02X_%04X" % (e["bank"], e["src"])
        if e["p1"]:
            name += "_f%d" % e["p1"]
        with open(os.path.join(bindir, name + ".bin"), "wb") as f:
            f.write(out)
        assets.append({"bank": e["bank"], "src": e["src"], "p1": e["p1"],
                       "name": name, "len": len(out), "dst": e["dst"]})

    # first-fit decreasing into expansion banks (no block crosses a bank)
    assets.sort(key=lambda a: -a["len"])
    banks = []
    for a in assets:
        for bi, b in enumerate(banks):
            if b[0] + a["len"] <= BANK_SIZE:
                a["ebank"] = FIRST_BANK + 1 + bi
                a["eoff"] = b[0]
                b[1].append(a)
                banks[bi] = (b[0] + a["len"], b[1])
                break
        else:
            a["ebank"] = FIRST_BANK + 1 + len(banks)
            a["eoff"] = 0
            banks.append((a["len"], [a]))
    assets.sort(key=lambda a: (a["ebank"], a["eoff"]))

    def page_of(ebank):
        return (ebank - 0x40) // 0x40      # $80-$BF -> 1, $C0-$FF -> 2, ...

    buckets = {}
    for a in assets:
        buckets.setdefault(a["bank"], []).append(a)
    assert len(buckets) <= 64, "too many event banks for the bucket directory"
    for bk, lst in buckets.items():
        assert len(lst) <= 255, "bucket $%02X exceeds 255 streams" % bk

    with open(os.path.join(HERE, "Parodius_SF2_assets.inc"), "w", newline="\n") as f:
        w = f.write
        w(";==================================================================\n")
        w("; AUTO-GENERATED by pce_gfx_export.py from compressed_gfx_table.txt -\n")
        w("; do not edit by hand.\n")
        w(";\n")
        w("; Layout: bucket directory keyed by event bank -> per-bucket record\n")
        w("; list: [count] then count x 8-byte records\n")
        w(";   +0 src.lo  +1 src.hi  +2 (p1<<4)|sf2page  +3 asset WINDOW bank\n")
        w(";   +4 addr.lo +5 addr.hi +6 len.lo           +7 len.hi\n")
        w("; Flip variants (p1 1-3) are separate pre-flipped assets - match\n")
        w("; includes p1, so nothing decompresses at runtime for known content.\n")
        w(";==================================================================\n\n")
        w("; LUT bank is mapped at MPR3 ($6000) by the hook; assets at MPR4 ($8000).\n")
        w("  .bank $%02X, \"asset LUTs\"\n    .page 3\n    .org $6000\n\n" % FIRST_BANK)
        bks = sorted(buckets)
        w("sf2.bucket.count = %d\n\n" % len(bks))
        w("sf2.bucket.bank:\n")
        for bk in bks:
            w("    .db $%02X    ; %d streams\n" % (bk, len(buckets[bk])))
        w("\nsf2.bucket.ptr.lo:\n")
        for bk in bks:
            w("    .db low(sf2.bucket.%02X)\n" % bk)
        w("\nsf2.bucket.ptr.hi:\n")
        for bk in bks:
            w("    .db high(sf2.bucket.%02X)\n" % bk)
        for bk in bks:
            w("\nsf2.bucket.%02X:\n    .db %d\n" % (bk, len(buckets[bk])))
            for a in buckets[bk]:
                w("    .db $%02X,$%02X, $%02X,$%02X, low(asset.%s),high(asset.%s), $%02X,$%02X"
                  % (a["src"] & 0xFF, a["src"] >> 8,
                     (a["p1"] << 4) | page_of(a["ebank"]),
                     0x40 | (a["ebank"] & 0x3F), a["name"], a["name"],
                     a["len"] & 0xFF, a["len"] >> 8))
                w("   ; -> dst $%04X.w p1=%d\n" % (a["dst"], a["p1"]))
        w("\n")
        cur = None
        for a in assets:
            if a["ebank"] != cur:
                cur = a["ebank"]
                w("\n;------------------------------------------------------------------\n")
                w("  .bank $%02X, \"assets %02X\"\n    .page 4\n    .org $8000\n\n" % (cur, cur))
            w("asset.%s:                ; %d bytes -> dst $%04X.w\n"
              % (a["name"], a["len"], a["dst"]))
            w("  .incbin \"gfx_bins/%s.bin\"\n" % a["name"])

    used = sum(b[0] for b in banks)
    print("wrote %d bins (%d bytes) into banks $%02X-$%02X + LUT bank $%02X"
          % (len(assets), used, FIRST_BANK + 1, FIRST_BANK + len(banks), FIRST_BANK))


# ----------------------------------------------------------------------------
# Pre-build: sanity-check the user-supplied ROM (strip a 512-byte header)
# ----------------------------------------------------------------------------
ROM_SIZE = 0x100000


def check(argv):
    p = argv[0] if argv else os.path.join(HERE, "Parodius_Da__original.pce")
    if not os.path.exists(p):
        print("ERROR: %s not found - supply your own clean dump of\n"
              "Parodius Da! (J) under that name (see README)." % os.path.basename(p))
        sys.exit(1)
    n = os.path.getsize(p)
    if n == ROM_SIZE + 512:
        data = open(p, "rb").read()
        open(p, "wb").write(data[512:])
        print("%s had a 512-byte header - stripped (now %d bytes)."
              % (os.path.basename(p), ROM_SIZE))
    elif n != ROM_SIZE:
        print("ERROR: %s is %d bytes; expected %d (headerless) or %d "
              "(with 512-byte header). Wrong dump?"
              % (os.path.basename(p), n, ROM_SIZE, ROM_SIZE + 512))
        sys.exit(1)
    # cheap identity check: the RESET vector of bank 0 must be plausible
    with open(p, "rb") as f:
        f.seek(0x1FFE)
        lo, hi = f.read(2)
    if hi < 0xC0:
        print("WARNING: reset vector $%02X%02X looks wrong - is this really "
              "Parodius Da! (J)?" % (hi, lo))
    else:
        print("%s: OK (%d bytes, headerless)" % (os.path.basename(p), ROM_SIZE))


# ----------------------------------------------------------------------------
# Post-build: blank the dead original graphics region
# ----------------------------------------------------------------------------
def zero(argv):
    p = argv[0] if argv else os.path.join(HERE, "Parodius_SF2.pce")
    rom = bytearray(open(p, "rb").read())
    rom[0x080000:0x100000] = bytes(0x80000)
    open(p, "wb").write(rom)
    print("zeroed $080000-$0FFFFF (original upper 512K)")


def main():
    if len(sys.argv) >= 3 and sys.argv[1] == "extract":
        extract(sys.argv[2:])
    elif len(sys.argv) >= 2 and sys.argv[1] == "zero":
        zero(sys.argv[2:])
    elif len(sys.argv) >= 2 and sys.argv[1] == "check":
        check(sys.argv[2:])
    else:
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
