#!/usr/bin/env python3
"""Propagate palette recolors down a fade group.

Parodius stores BG fade-in/out as a run of same-size blocks (same CTA, stored
back-to-back), every frame dimmer-or-equal to the brightest "full" frame.  When
you recolor only the full frame, the fade-in still ramps in the OLD colors and
snaps to the new look on the last frame.

This tool regenerates the *still-original* fade steps from your edited frame,
using the ORIGINAL per-channel fade ratios so the exact fade curve is preserved:

    new_step[ch] = round( new_ref[ch] * orig_step[ch] / orig_ref[ch] )

- ref = the brightest frame you edited in the group (your target look).
- Colours you did NOT recolor reproduce their original step exactly (no churn).
- A channel that was 0 at the original ref but lit in your recolor is ramped by
  the colour's own progress (or, if it was pure black, the frame's mean progress).

BG only: groups whose CTA >= $0100 (sprites) are skipped.

Default is DRY RUN (prints a preview, writes nothing).  Pass --write to apply.
"""
import sys, importlib.util

spec = importlib.util.spec_from_file_location("pie", "palette_inc_editor.py")
pie = importlib.util.module_from_spec(spec); spec.loader.exec_module(pie)

def rgb(c):  return [(c >> 3) & 7, (c >> 6) & 7, c & 7]
def pack(r, g, b): return (g << 6) | (r << 3) | b
def bri(cs): return sum(sum(rgb(c)) for c in cs)
def bl(a):   return "$%02X:$%04X" % (a >> 13, 0x4000 + (a & 0x1FFF))
def clamp(v): return 0 if v < 0 else 7 if v > 7 else v

def cta_is_bg(b):
    # block header CTA may list several; BG if the first/any is < $0100
    s = str(b.get("cta", "")).replace("$", "")
    for tok in s.split(","):
        try:
            if int(tok, 16) < 0x100: return True
        except ValueError: pass
    return False

def block_size(b): return 1 + (b["count"] + 1) * 9

def detect_groups(org):
    B = sorted(org.blocks.values(), key=lambda b: b["abs"])
    runs, q = [], [B[0]]
    for b in B[1:]:
        p = q[-1]
        if p["abs"] + block_size(p) == b["abs"] and p["count"] == b["count"]:
            q.append(b)
        else:
            if len(q) >= 3: runs.append(q)
            q = [b]
    if len(q) >= 3: runs.append(q)
    return runs

def frame_progress(orgS, orgR):
    """colour-progress per index: sum(step_ch)/sum(ref_ch) over ref_ch>0 channels."""
    p = []
    for sc, rc in zip(orgS, orgR):
        s = rgb(sc); r = rgb(rc)
        num = sum(s[k] for k in range(3) if r[k] > 0)
        den = sum(r[k] for k in range(3) if r[k] > 0)
        p.append(num / den if den else None)
    return p

def propagate(new_ref, orgR, orgS, global_prog):
    """Build a new step from new_ref using orig ratios; returns (colors, n_fallback)."""
    out = []; fb = 0
    prog = frame_progress(orgS, orgR)
    gp = global_prog
    for j in range(len(new_ref)):
        nr = rgb(new_ref[j]); r = rgb(orgR[j]); s = rgb(orgS[j])
        res = [0, 0, 0]
        for k in range(3):
            if r[k] > 0:
                res[k] = clamp(round(nr[k] * s[k] / r[k]))
            elif nr[k] > 0:        # user lit a channel dark at ref -> ramp by progress
                fb += 1
                p = prog[j] if prog[j] is not None else gp
                res[k] = clamp(round(nr[k] * p))
            else:
                res[k] = 0
        out.append(pack(*res))
    return out, fb

# Groups held for deliberate manual handling (ref absolute offset):
#   $7342A (= ref $39:$542A) = L4 208-col BG fade — the contiguous run is two
#   merged sub-sequences (a fade + a second scene/animation), so a single-ref
#   ratio is unsafe.
HOLD = {0x7342A}

def main():
    write = "--write" in sys.argv
    org = pie.PaletteIncFile("palette_org.inc")
    cur = pie.PaletteIncFile("palette.inc")
    byabs_org = {b["abs"]: b for b in org.blocks.values()}
    byabs_cur = {b["abs"]: b for b in cur.blocks.values()}
    def edited(b): return byabs_cur[b["abs"]]["colors"] != b["colors"]

    groups = detect_groups(org)
    planned = []   # (group, ref_block, [(step_block, new_colors, nfb), ...])
    skipped = []
    for run in groups:
        if not cta_is_bg(run[0]): continue
        ed = [b for b in run if edited(b)]
        if not ed: continue
        ref = max(ed, key=lambda b: bri(b["colors"]))      # brightest edited = target full
        if ref["abs"] in HOLD:
            skipped.append((run, ref, "held for manual (multi sub-sequence / sectional fade)"))
            continue
        orgR = byabs_org[ref["abs"]]["colors"]
        new_ref = byabs_cur[ref["abs"]]["colors"]
        # global frame progress per step (mean colour progress) for pure-black fallback
        todo = []
        bad = 0
        for s in run:
            if edited(s): continue                          # never overwrite your edits
            orgS = byabs_org[s["abs"]]["colors"]
            if bri(orgS) >= bri(orgR): continue             # only fade DOWN from the full
            # mixed-sequence guard: a clean fade step is <= ref per channel
            v = sum(1 for sc, rc in zip(orgS, orgR)
                    for a, b2 in zip(rgb(sc), rgb(rc)) if a > b2 + 1)
            if v > len(orgS) * 0.06 * 3: bad += 1
            gp = (bri(orgS) / bri(orgR)) if bri(orgR) else 0
            newc, fb = propagate(new_ref, orgR, orgS, gp)
            todo.append((s, newc, fb))
        if bad > len(run) * 0.3:
            skipped.append((run, ref, "mixed fade+animation (%d/%d frames exceed ref)" % (bad, len(run))))
            continue
        if todo:
            # fade-from-black: at the darkest step, most colours that are lit in the
            # full frame must still be black (the not-yet-revealed background).  A run
            # that already starts mostly-lit is a sectional / tail-of-fade, not a clean
            # fade-from-black, and propagating it leaks the background early (L7 case).
            dark_s = min((s for s, _, _ in todo), key=lambda s: bri(byabs_org[s["abs"]]["colors"]))
            dcols = byabs_org[dark_s["abs"]]["colors"]
            absblack = sum(1 for c in dcols if c == 0) / len(dcols)   # reference-independent
            if absblack < 0.60:
                skipped.append((run, ref, "not a fade-from-black (darkest step only %d%% black - likely sectional)"
                                % (100 * absblack)))
                continue
            darkest = min(bri(byabs_org[s["abs"]]["colors"]) for s, _, _ in todo)
            if darkest >= bri(orgR) * 0.85:
                skipped.append((run, ref, "brightness range too small (darkest=%d ref=%d) - not a real fade"
                                % (darkest, bri(orgR))))
                continue
            planned.append((run, ref, todo))

    print("=== FADE PROPAGATION %s ===\n" % ("(WRITE)" if write else "(DRY RUN - nothing written)"))
    total_changed = 0
    for run, ref, todo in planned:
        used = run[0].get("used", "?"); n = len(run[0]["colors"])
        print("%s  %dcol CTA %s  ref(edited full)=%s  -> regen %d step(s):"
              % (used, n, run[0].get("cta"), bl(ref["abs"]), len(todo)))
        for s, newc, fb in todo:
            orgS = byabs_org[s["abs"]]["colors"]
            chg = sum(1 for a, b in zip(newc, orgS) if a != b)
            total_changed += chg
            note = "  (%d via newly-lit-channel fallback)" % fb if fb else ""
            print("     %s : %3d colours would change%s" % (bl(s["abs"]), chg, note))
        # one sample recolored colour, across the regen
        print()
    if skipped:
        print("--- skipped (need manual review) ---")
        for run, ref, why in skipped:
            print("   %s  %dcol CTA %s : %s"
                  % (run[0].get("used"), len(run[0]["colors"]), run[0].get("cta"), why))
        print()
    print("Total colour cells that would change:", total_changed)

    if write:
        cur.orig_colors = {k: b["colors"] for k, b in org.blocks.items()}   # for MODIFIED tags
        for run, ref, todo in planned:
            for s, newc, fb in todo:
                bank = s["abs"] >> 13
                addr = 0x4000 + (s["abs"] & 0x1FFF)
                cur.set_colors(bank, addr, newc)
        cur.save()
        print("\nWritten to palette.inc.")
    else:
        print("\n(dry run) re-run with --write to apply.")

if __name__ == "__main__":
    main()
