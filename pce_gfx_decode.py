#!/usr/bin/env python3
"""Offline decoder for Parodius Da!'s compressed graphics (engine $C25C).

Stream layout (from the bank-$01 disassembly, see anim-engine.md):
  src+0                  header:  bit7 = sprite-layout flush, &$7F = dict length
  src+1 .. src+dictlen   dictionary (chunky->planar conversion table), absent if 0
  src+1+dictlen ..       CONTROL stream (tokens below) -> byte stream -> 128-byte
                         buffer at WRAM $3C80 -> flushed raw or planar-converted

Control tokens (byte counts are of the OUTPUT stream):
  $00 cnt fix L0..Ln     cnt words of (fix, literal)      (cnt=0 -> 256)
  $01 lo hi b            b repeated cnt16 times
  $02 cnt b1 b2          word (b1,b2) repeated cnt        (cnt=0 -> 256)
  $03-$3F b              b repeated n times
  $40-$7F                (n&$3F) zero bytes               (n=0 -> 256)
  $80 lo hi L...         cnt16 literal bytes
  $81-$BF L...           (n&$3F) literal bytes
  $C0-$FD L...           (n&$3F) words of (00, literal)   (n=0 -> 256)
  $FE cnt b1 b2 b3 b4    4-byte pattern repeated cnt      (cnt=0 -> 256)
  $FF                    end of event

Usage:
  pce_gfx_decode.py <rom> <bank> <src>          decode one block, hex to stdout
  pce_gfx_decode.py <rom> --verify <trace.txt>  check every ROMDEC entry of a
                                                parodius_gfxtrace.lua log against
                                                its captured VRAM ground truth
NOTE: raw mode (dictlen==0) is exact; the planar/dictionary flush conversions
are NOT implemented yet - verify mode reports those separately so the corpus
tells us what to implement next.
"""
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


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        return
    rom = open(sys.argv[1], "rb").read()
    if sys.argv[2] == "--verify":
        verify(rom, sys.argv[3])
        return
    bank, src = int(sys.argv[2], 16), int(sys.argv[3], 16)
    hdr, dic, out = decode_block(rom, bank, src)
    print("header $%02X  (sprite=%d, dictlen=%d)  output %d bytes"
          % (hdr, hdr >> 7, hdr & 0x7F, len(out)))
    if dic:
        print("dict:", dic.hex(" "))
    for i in range(0, len(out), 16):
        print("%04X: %s" % (i, out[i:i + 16].hex(" ")))


if __name__ == "__main__":
    main()
