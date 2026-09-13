# Evidence: TODO-41B post-stack stimulated I²S validation — PASS

Captured 2026-09-13. Raw serial log preserved as `2026-09-13-41B-capture.log.gz`
(542 054 B raw). Reproduce with:

    gunzip -c ai/evidence/2026-09-13-41B-capture.log.gz > /tmp/41B.log
    python3 tools/analyze_corruption.py /tmp/41B.log

## Stimulus conditions — recorded WITH the result

| | |
|---|---|
| Source | phone → USB-C adapter → cable → **real 1/4" instrument jack** |
| Tone | 1 kHz, L+R |
| Level | **0.141 V<sub>rms</sub> measured at `48e`** (0.140 avg, 0.143 max) |
| Frequency (scope) | 995–997 Hz |
| Waveform | clean sine, no visible clipping |
| Analog path | jack → C1 → OPA1642 → C2 → `48e` → LINE-IN-L |
| Hardware | new Teensy 4.1 + new Rev D shield, **native stack** |
| Firmware | `c18fac7`, `DISPLAY_TARGET_PI` |
| Probe | CH1 tip `48e`, ground spring to nearby analog GND, board powered |

## Outlier detector v1 — frozen criterion

```
Outlier detector v1
For each 32-sample window, evaluate interior samples i=1..30 using
d2[i] = x[i-1] - 2x[i] + x[i+1].
Let m = median(|d2|) over those 30 values; if m=0, use m=1.
Flag sample i only when |d2[i]| > 10m and |d2[i]| > 100 counts.
Report 30 evaluated samples/window and 32 captured samples/window separately.
```

Both comparisons are **strictly greater than**, not ≥. `m` is the median of the
30 interior second-difference magnitudes of **that same window** — not a global
or running median.

## Result — verbatim analyser output

```
WINDOWS ANALYSED      : 324
SAMPLES EVALUATED     : SOURCE 9720  RETURN 9720   <- detector denominator
SAMPLES CAPTURED      : SOURCE 10368  RETURN 10368   (2/window have no 2nd difference)
DURATION              : uptime 630s -> 2245s (26.9 min)

SOURCE outliers/window: mean 0.000   total 0
RETURN outliers/window: mean 0.000   total 0
COMPLETELY CLEAN WIN  : 324/324 = 100.0 %
WORST WINDOW (SOURCE) : 0 of 30 evaluable
WORST WINDOW (RETURN) : 0 of 30 evaluable
CLIP EVENTS (>=-0.5)  : 0   (0.0 % of windows)

SOURCE peak dBFS      : mean -29.88  min -30.4  max -28.9
RETURN peak dBFS      : mean -66.22  min -67.4  max -64.7
SOURCE raw |max|      : 1179 counts
RETURN raw |max|      : 18 counts
BLOCK PERIOD ms       : mean 46.43  min 46.3  max 46.7
AudioMemoryUsageMax   : min 19  max 19
TF clamped bins       : min 3  max 3 of 512

BAND BREAKDOWN (quarters, to expose any drift):
  uptime   630-1030 s  n= 81  SRC 0.000/win  RET 0.000/win  SRCpeak -30.14 dBFS
  uptime  1035-1435 s  n= 81  SRC 0.000/win  RET 0.000/win  SRCpeak -30.13 dBFS
  uptime  1440-1840 s  n= 81  SRC 0.000/win  RET 0.000/win  SRCpeak -29.84 dBFS
  uptime  1845-2245 s  n= 81  SRC 0.000/win  RET 0.000/win  SRCpeak -29.41 dBFS

NO WINDOW CONTAINED ANY OUTLIER BY THE STATED CRITERION.
```

## Why the raw log and script are committed

Run D — the project's reference validation for six days — recorded neither its
stimulus level nor its outlier criterion, so its numbers (5.95 / 24.72 / 8.54 /
0.00) cannot be recomputed by anyone, ever. They nonetheless drove three DOUT
reworks and a hardware-damage hypothesis. **This result is committed with its
raw data, its stimulus conditions and its detection algorithm so that it is
reproducible rather than merely remembered.**
