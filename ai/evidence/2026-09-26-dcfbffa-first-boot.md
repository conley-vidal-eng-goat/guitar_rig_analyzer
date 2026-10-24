# First boot of `dcfbffa` — flash verification

**2026-09-26.** First run of the Phase 10 transport work on hardware.
Raw log: [`2026-09-26-dcfbffa-first-boot.jsonl`](2026-09-26-dcfbffa-first-boot.jsonl)

## Flashed artifact

| | |
|---|---|
| Source commit | `dcfbffa` |
| Artifact | `ai/evidence/firmware/dcfbffa-PI/guitar_rig_analyzer.ino.hex` |
| **sha256** | `24b71d73bf60a0d6ff9cbb5737a46bba6a04887a1fe55479d356b5a87dce3a6e` |
| md5 | `55ee39a5d8fba94cdad9606e9fa20a2f` |
| Hash verified immediately before upload | yes |
| Replaces | `029ac05`, `Build: Sep 21 2026 17:21:24` |

## Verification — `OBS`

| Check | Result |
|---|---|
| Build identity | **`Build: Sep 26 2026 16:36:53   v0.6.0`** — exact match to the manifest |
| Display target | `[Link]` diagnostics present → `DISPLAY_TARGET_PI` (see gap below) |
| DataSender init | Started; 4096 B TX buffer, 128 live bins, 4:1 decimation, protocol v2 |
| **Session id** | **`0`** |
| Route at boot | `TS return, no injection` — ADR-004 boot default |
| Validation | `[Validation] Harness ready` printed; **no test ran** |
| Generator / injection | No activity |
| Relay | No transition logged |
| Measurement | None armed; no RESULT queued |
| Block timing | 46.3–46.7 ms vs 46.4 expected |
| Transport call time | max **282 µs** — microseconds, not milliseconds |
| TX room min | 2500 B of 4096 B |

**Session id 0 is correct, not a failure.** The EEPROM counter had never been
written, so it read `0xFFFF` and incremented to `0`. This is the documented
first-boot case, and the reason a receiver must never treat `0` as "absent".

## All four producers live — first hardware evidence

Counters across two consecutive 5 s windows (uptime 18 s → 23 s):

| Producer | Δ over 5 s | Rate | Target |
|---|---:|---:|---|
| HELLO (TODO-56) | 5 | **1.0/s** | 1000 ms ✅ |
| STATE (TODO-57) | 10 | **2.0/s** | 500 ms ✅ |
| ROUTER_STATUS (TODO-58) | 5 | **1.0/s** | 1000 ms ✅ |
| LIVE_FRAME | 108 | **21.6/s** | one per block |

`Atomicity: 0 best-effort packets refused` — correct: no RESULT has been staged,
so TODO-59's invariant has had nothing to refuse. **It is instrumented but not
yet exercised.**

## 🔺 Two predictions falsified — both useful

**1. LIVE_FRAME rate is 21.6/s, not ~11 Hz.** The runbook and `data_sender.h`
both said ~11 Hz. Measured: 108 frames per 5 s window, one per 46.3 ms block.

The consequence is not cosmetic:

```
21.6/s x 1689 B = 36 482 B/s of 46 080 B/s at 460800 8N1 = 79% duty
```

not the ~41 % the runbook predicted. Sync words are **~25.6/s**, not ~15/s.
The 79 % figure matches what TODO-34 derived independently ("~36.7 ms against a
measured 46.3 ms block period"), so **`data_sender.h`'s "~11 Hz" and its
bandwidth table are stale — they predate TODO-27's correction** that the FFT
hop, not the window, sets the cadence. The runbook inherited the stale figure.

**2. `TF clamped bins: 0 of 512`, not near 512.** Predicted high clamping from
the 2026-09-07 precedent. Wrong, and the reason is instructive: on 2026-09-07
there **was** source signal with nothing on RETURN, so the ratio railed. Here
there is no signal at all — SOURCE peak −64 dBFS, essentially the noise floor —
so source bins fall below `TF_SOURCE_GATE` and `tf_db` is **NaN (pen-lift), not
clamped**. Gated and railed are different states. The prediction conflated them.

**This is exactly why that expectation was demoted to the weaker tier before the
capture.** In the hard tier it would have failed a completely healthy run.

## Evidence gap — stated, not glossed

**The boot banner was not captured.** The serial port could only be opened after
`arduino-cli upload` returned, by which time the first lines — the banner,
`[Main] Display target: ...` — had already been emitted. Capture begins mid
SGTL register dump.

Build identity is nonetheless established: `printBuildIdentity()` is deliberately
**one format string** shared by the banner and the 5 s diagnostic block
(`guitar_rig_analyzer.ino:205-215`), so the diagnostic line carries the same
identity by construction. The display target is established behaviourally — the
entire `[Link]` block exists only under `DISPLAY_TARGET_PI`.

**To close the gap:** capture a clean boot at the next authorized power cycle,
which the UART wiring sequence requires anyway (runbook step 2b → 2g).

## Not done

No `v`, no Tests 1–4, no injection, no generator, no relay operation, no
measurement armed, no analog breadboard change. Phase 9 untouched. No Phase 10
step passed: this proves the firmware runs and emits, **not** that anything
receives or decodes it.
