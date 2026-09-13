#!/usr/bin/env python3
"""TODO-41B corruption analysis.

OUTLIER CRITERION (stated explicitly, because run D's was never recorded):

A sample is an outlier if its discrete second difference
    d2[i] = x[i-1] - 2*x[i] + x[i+1]
satisfies BOTH, with STRICTLY-GREATER-THAN in each case (not >=):
    |d2[i]| > 10 * median(|d2|)   (relative, local robustness)
    |d2[i]| > 100 counts          (absolute floor)

median(|d2|) is computed from the 30 interior second-difference values of
THAT SAME 32-sample window - not a global median, not a running median.
If that median is 0 (a perfectly flat window) it is treated as 1 so the
relative term cannot divide the threshold to zero; the 100-count floor
then governs.

Rationale: a coherent 1 kHz sine at 44.1 kHz has angular frequency
w = 2*pi*1000/44100 = 0.1425 rad/sample, so its curvature is bounded by
A*w^2 ~= 0.0203*A. At the observed A ~= 930 counts that is ~19 counts.
A corrupted I2S word lands thousands of counts away, giving a second
difference two to three orders of magnitude larger. The dual condition
stops a quiet window (tiny median) producing false positives and stops a
loud window masking a real impulse. Edge samples (first/last) have no
second difference and are not evaluated: 30 of 32 samples per window.
"""
import re, sys, statistics as st

path = sys.argv[1]
txt = open(path, errors='replace').read()

win_re  = re.compile(r'uptime (\d+)s')
peak_re = re.compile(r'SOURCE_NODE peak:\s*([-\d.]+) dBFS\s*\|\s*RETURN_NODE peak:\s*([-\d.]+) dBFS')
src_re  = re.compile(r'\[RAWDUMP\] SOURCE: ([-\d ]+)')
ret_re  = re.compile(r'\[RAWDUMP\] RETURN: ([-\d ]+)')
blk_re  = re.compile(r'Block:\s+(\d+) in 5000ms = ([\d.]+) ms/block')
mem_re  = re.compile(r'AudioMemory: (\d+) in use, (\d+) max')
clamp_re= re.compile(r'TF clamped bins: (\d+) of (\d+)')

def outliers(vals):
    if len(vals) < 3: return 0, []
    d2 = [vals[i-1] - 2*vals[i] + vals[i+1] for i in range(1, len(vals)-1)]
    med = st.median([abs(v) for v in d2]) or 1
    thr = max(10*med, 100)
    idx = [i+1 for i,v in enumerate(d2) if abs(v) > thr]
    return len(idx), idx

blocks = txt.split('--- 5s diagnostics')
rows = []
for b in blocks[1:]:
    up = win_re.search(b); pk = peak_re.search(b)
    s  = src_re.search(b);  r = ret_re.search(b)
    bl = blk_re.search(b);  m = mem_re.search(b); cl = clamp_re.search(b)
    if not (up and pk and s and r): continue
    sv = [int(x) for x in s.group(1).split()]
    rv = [int(x) for x in r.group(1).split()]
    so,_ = outliers(sv); ro,_ = outliers(rv)
    rows.append(dict(up=int(up.group(1)), sp=float(pk.group(1)), rp=float(pk.group(2)),
                     so=so, ro=ro, ns=len(sv), nr=len(rv),
                     ms=float(bl.group(2)) if bl else None,
                     mmax=int(m.group(2)) if m else None,
                     clamp=int(cl.group(1)) if cl else None,
                     smax=max(abs(v) for v in sv), rmax=max(abs(v) for v in rv)))

n = len(rows)
if n == 0:
    print("NO WINDOWS PARSED"); sys.exit(1)
ns = sum(max(0, r['ns']-2) for r in rows); nr = sum(max(0, r['nr']-2) for r in rows)
cap_s = sum(r['ns'] for r in rows); cap_r = sum(r['nr'] for r in rows)
tot_so = sum(r['so'] for r in rows); tot_ro = sum(r['ro'] for r in rows)
clean  = sum(1 for r in rows if r['so']==0 and r['ro']==0)
clip   = sum(1 for r in rows if r['sp'] >= -0.5 or r['rp'] >= -0.5)

print(f"WINDOWS ANALYSED      : {n}")
print(f"SAMPLES EVALUATED     : SOURCE {ns}  RETURN {nr}   <- detector denominator")
print(f"SAMPLES CAPTURED      : SOURCE {cap_s}  RETURN {cap_r}   (2/window have no 2nd difference)")
print(f"DURATION              : uptime {rows[0]['up']}s -> {rows[-1]['up']}s "
      f"({(rows[-1]['up']-rows[0]['up'])/60:.1f} min)")
print()
print(f"SOURCE outliers/window: mean {tot_so/n:.3f}   total {tot_so}")
print(f"RETURN outliers/window: mean {tot_ro/n:.3f}   total {tot_ro}")
print(f"COMPLETELY CLEAN WIN  : {clean}/{n} = {100*clean/n:.1f} %")
print(f"WORST WINDOW (SOURCE) : {max(r['so'] for r in rows)} of 30 evaluable")
print(f"WORST WINDOW (RETURN) : {max(r['ro'] for r in rows)} of 30 evaluable")
print(f"CLIP EVENTS (>=-0.5)  : {clip}   ({100*clip/n:.1f} % of windows)")
print()
sp=[r['sp'] for r in rows]; rp=[r['rp'] for r in rows]
print(f"SOURCE peak dBFS      : mean {sum(sp)/n:.2f}  min {min(sp):.1f}  max {max(sp):.1f}")
print(f"RETURN peak dBFS      : mean {sum(rp)/n:.2f}  min {min(rp):.1f}  max {max(rp):.1f}")
print(f"SOURCE raw |max|      : {max(r['smax'] for r in rows)} counts")
print(f"RETURN raw |max|      : {max(r['rmax'] for r in rows)} counts")
ms=[r['ms'] for r in rows if r['ms']]
if ms: print(f"BLOCK PERIOD ms       : mean {sum(ms)/len(ms):.2f}  min {min(ms)}  max {max(ms)}")
mm=[r['mmax'] for r in rows if r['mmax'] is not None]
if mm: print(f"AudioMemoryUsageMax   : min {min(mm)}  max {max(mm)}")
cc=[r['clamp'] for r in rows if r['clamp'] is not None]
if cc: print(f"TF clamped bins       : min {min(cc)}  max {max(cc)} of 512")
print()
print("BAND BREAKDOWN (quarters, to expose any drift):")
q = max(1, n//4)
for i in range(0, n, q):
    ch = rows[i:i+q]
    if not ch: continue
    print(f"  uptime {ch[0]['up']:>5}-{ch[-1]['up']:<5}s  n={len(ch):>3}  "
          f"SRC {sum(c['so'] for c in ch)/len(ch):.3f}/win  "
          f"RET {sum(c['ro'] for c in ch)/len(ch):.3f}/win  "
          f"SRCpeak {sum(c['sp'] for c in ch)/len(ch):.2f} dBFS")
bad = [r for r in rows if r['so'] or r['ro']]
if bad:
    print(f"\nWINDOWS WITH ANY OUTLIER ({len(bad)}):")
    for r in bad[:20]:
        print(f"  uptime {r['up']}s  SRC {r['so']}  RET {r['ro']}  "
              f"peaks {r['sp']}/{r['rp']} dBFS")
else:
    print("\nNO WINDOW CONTAINED ANY OUTLIER BY THE STATED CRITERION.")
