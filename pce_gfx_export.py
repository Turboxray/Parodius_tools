#!/usr/bin/env python3
"""Export decompressed graphics as SF2-expansion build material.

From gfxtrace captures + the ROM, writes:
  gfx_bins/<bank>_<src>.bin      decompressed VRAM data (p1=0) per stream
  Parodius_SF2_assets.inc        auto-generated: expansion banks ($81+) with
                                 .incbin'd assets (first-fit, no bank crossing)
                                 + GnG-style lookup tables in bank $80:
                                 match keys (event bank + src), asset location
                                 (SF2 page/bank/addr), byte length, VRAM dst.

The future load-hook walks the match table with the ROMDEC event's [bank][src]
as the ID; on a hit it streams the stored data instead of decompressing.
NOTE: only p1=$00 events may be diverted - flipped variants ($01-$03) must
fall through to the original decompressor (they mirror at decompress time).

Usage:  pce_gfx_export.py <rom> <trace.txt> [more traces...]
"""
import os
import sys
import importlib.util

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("rip", os.path.join(HERE, "pce_gfx_rip.py"))
rip = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rip)
dec = rip.dec

FIRST_BANK = 0x80          # LUT bank; assets from $81
BANK_SIZE = 0x2000


def walk_table(rom, blocks):
    """Merge in every ROMDEC event reachable from the $C5BA sequence table
    (bank $01) - covers content no playthrough triggered (second loop,
    other characters' routes, unused). Trace entries take precedence."""
    def b1(a):
        return rom[0x2000 + (a - 0xC000)]

    def w1(a):
        return b1(a) | (b1(a + 1) << 8)

    added = 0
    i = 0
    while True:
        p = w1(0xC5BA + i * 2)
        if not (0xC600 <= p < 0xE000):
            break
        j = p + 2
        while True:
            ep = w1(j)
            j += 2
            if ep == 0xFFFF:
                break
            k = ep
            for _ in range(32):
                t = b1(k)
                if t == 0xFF:
                    break
                if t == 0xFE:
                    k += 7
                    continue
                key = (t, w1(k + 4))
                if key not in blocks:
                    blocks[key] = {"calls": 0, "stages": set(), "dsts": set(),
                                   "p1s": set(), "slots": set()}
                    added += 1
                blocks[key]["dsts"].add(w1(k + 2))
                blocks[key]["p1s"].add(b1(k + 1))
                k += 6
        i += 1
    print("static table walk: +%d streams not in the traces" % added)
    return blocks


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        return
    rom = open(sys.argv[1], "rb").read()
    blocks = walk_table(rom, rip.parse_traces(sys.argv[2:]))

    bindir = os.path.join(HERE, "gfx_bins")
    os.makedirs(bindir, exist_ok=True)

    assets = []
    for (bank, src) in sorted(blocks):
        info = blocks[(bank, src)]
        # one asset per (bank, src, p1) variant seen - flips are pre-applied
        # offline so the hook can divert them too (nothing decompresses at
        # runtime and the original compressed data becomes fully dead)
        for p1 in sorted(set(info["p1s"]) | {0}):
            hdr, dic, out, clen = dec.decode_block_full(rom, bank, src, p1)
            name = "%02X_%04X" % (bank, src)
            if p1:
                name += "_f%d" % p1
            with open(os.path.join(bindir, name + ".bin"), "wb") as f:
                f.write(out)
            assets.append({"bank": bank, "src": src, "p1": p1, "name": name,
                           "len": len(out), "dst": min(info["dsts"]),
                           "stages": info["stages"]})

    # first-fit decreasing into expansion banks (no block crosses a bank)
    assets.sort(key=lambda a: -a["len"])
    banks = []                       # list of (used, [assets])
    for a in assets:
        for b in banks:
            if b[0] + a["len"] <= BANK_SIZE:
                a["ebank"] = FIRST_BANK + 1 + banks.index(b)
                a["eoff"] = b[0]
                b[1].append(a)
                banks[banks.index(b)] = (b[0] + a["len"], b[1])
                break
        else:
            a["ebank"] = FIRST_BANK + 1 + len(banks)
            a["eoff"] = 0
            banks.append((a["len"], [a]))
    assets.sort(key=lambda a: (a["ebank"], a["eoff"]))

    def page_of(ebank):
        return (ebank - 0x40) // 0x40      # $80-$BF -> 1, $C0-$FF -> 2, ...

    # bucket by event bank (the ID's first byte); per-bucket 8-byte records
    buckets = {}
    for a in assets:
        buckets.setdefault(a["bank"], []).append(a)
    assert len(buckets) <= 64, "too many event banks for the bucket directory"
    for bk, lst in buckets.items():
        assert len(lst) <= 255, "bucket $%02X exceeds 255 streams" % bk

    with open(os.path.join(HERE, "Parodius_SF2_assets.inc"), "w", newline="\n") as f:
        w = f.write
        w(";==================================================================\n")
        w("; AUTO-GENERATED by pce_gfx_export.py - do not edit by hand.\n")
        w("; Uncompressed graphics assets + lookup tables for the SF2 build.\n")
        w("; Match key = the ROMDEC event's [bank][src lo][src hi]; only p1=$00\n")
        w("; events may be diverted (flips fall through to the decompressor).\n")
        w(";\n")
        w("; Layout: bucket directory keyed by event bank -> per-bucket record\n")
        w("; list: [count] then count x 8-byte records\n")
        w(";   +0 src.lo  +1 src.hi  +2 (p1<<4)|sf2page  +3 asset WINDOW bank\n")
        w(";   +4 addr.lo +5 addr.hi +6 len.lo           +7 len.hi\n")
        w("; Flip variants (p1 1-3) are separate pre-flipped assets - match\n")
        w("; includes p1, so NOTHING falls through to the decompressor for\n")
        w("; known streams and the original upper 512K is fully dead.\n")
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
                # bank byte = WINDOW bank ($40-$7F); page nibble selects the
                # 512KB (works for page-3 file banks $100+ too); p1 in the
                # high nibble of the page byte
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
            w("asset.%s:                ; %d bytes -> dst $%04X.w (stages %s)\n"
              % (a["name"], a["len"],
                 a["dst"], ",".join("$%02X" % s for s in sorted(a["stages"]))))
            w("  .incbin \"gfx_bins/%s.bin\"\n" % a["name"])

    used = sum(b[0] for b in banks)
    print("wrote %d bins (%d bytes) into banks $%02X-$%02X + LUT bank $%02X"
          % (len(assets), used, FIRST_BANK + 1, FIRST_BANK + len(banks), FIRST_BANK))


if __name__ == "__main__":
    main()
