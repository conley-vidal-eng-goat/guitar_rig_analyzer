# Negative control — `m` with NO stimulus: ARMED → ABORTED(TIMEOUT) on the link

**Captured 2026-09-27T07:02:11Z UTC (= 00:02 local, 2026-09-27); analysed and
preserved 2026-09-27.** Firmware `dcfbffa` unmodified. No Phase 9 validation, no
generator, no injection, no relay or route change.

## 🔺 CORRECTION TO THE RUN'S OWN DESCRIPTION — read this first

This run was originally spoken of as an *attempted stimulated RESULT measurement*.
**It was not.** The operator established afterwards that **no 1 kHz phone stimulus
was playing for any test performed after midnight on 2026-09-27**, and this
capture began at 00:02 local.

**It is a NO-STIMULUS run and must be recorded as one.** Calling it a failed
stimulated measurement would attribute a timeout to the measurement engine when
the actual cause was an absent input, and would have made the real RESULT run of
2026-09-27 21:56 look like a second attempt at the same thing rather than the
first attempt at a different thing.

## Artifacts

Two files from the same boot (**session 6**), both preserved:

| | `phase10-result-no-stimulus.bin` | `phase10-result-attempt.bin` |
|---|---|---|
| Role | **the negative control** | full-rate idle baseline, same session |
| Capture window | 60 / 60 s, `07:02:11Z` | 120 / 120 s, `06:46:05Z` |
| Bytes | **588 218** | **4 378 056** |
| Rate | 9 803 B/s | **36 483 B/s** (full idle) |
| SHA-256 | `f4095604a85ee47e6cf3c8efc48297f43614d575cca54162216fbe5f2934b4c8` | `2da46560478d1843c24f07369252aa80de932c43d560a3dfc7b8203345b05eb8` |
| Capture log | [`.capturelog`](phase10-result-no-stimulus.capturelog) | [`.capturelog`](phase10-result-attempt.capturelog) |

Both hashes re-verified on the Mac 2026-09-27 against the values `capture.sh`
printed on the Pi. Device `/dev/ttyAMA0`, receive-only link unchanged.

### ⚠️ `phase10-result-attempt.bin` is misnamed and contains no measurement at all

It was not mentioned in the bench handoff and is recorded here so it does not
become a mystery artifact. Its packet census is **LiveFrame 2 575, StatePacket
240, RouterStatus 120, Hello 120 — and zero STATUS, zero ABORTED, zero RESULT**,
with `measurement_state IDLE` and `view live` throughout. **`m` was never issued
inside this window.** The filename records an intention; the bytes record an
idle instrument.

**It is still the most valuable byte-integrity datapoint in the set.** At
4 378 056 bytes over 120 s at **full 79 % occupancy** it is 4× the committed 30 s
fixture, and it contains **zero CRC failures, zero oversize rejects, zero decode
errors, zero discarded bytes and zero end buffer** — a clean 4.38 MB sustained
stream. Its leading discard is **0**, because the capture happened to open
exactly on a sync word.

**Rename recommended, not performed:** `phase10-idle-120s-session6.bin` describes
what it is. The name is not changed here because the SHA-256 is already recorded
against the current filename in the capture log, and renaming evidence is the
operator's call.

## Timeline of the negative control (Teensy audio time)

| t | Observation |
|---|---|
| 0.499 s | session established → **6**; `STATE UNKNOWN → IDLE` |
| 1.501 s | `ROUTE return_source TS` |
| 4.998 s | STATUS `"Measuring — external stimulus"`; `STATE IDLE → ARMED` |
| **15.000 s** | **ABORTED packet, prose reason `"armed timeout"`**; `ARMED → ABORTED`; abort latch **SET with `reason_code NONE`** |
| **15.499 s** | `REASON CODE NONE → TIMEOUT` — **499 ms, one STATE period** |
| 17.499 s | LIVE STOPPED — no live frame for 2.50 s |

## ★ What this establishes

**The arm threshold refused to arm on noise, and said so in two forms.** No
stimulus → `m` → `IDLE → ARMED` → ~10 s arm wait → `ABORTED` carrying the human
string `"armed timeout"` → the **machine-readable** `TIMEOUT` enum arriving one
STATE period later → the abort staying **sticky** for the remaining 42 s.

**This is the instrument working, not failing.** A measurement engine that armed
on an absent input would produce a confident result from noise, which is the
class of defect this project's evidence discipline exists to prevent.

**The 499 ms reason-code lag reproduces the 502 ms figure from Step A on
2026-09-26** — and that is the second independent observation of it. The prose
reason rides the best-effort ABORTED packet; the enum rides the next periodic
STATE snapshot. **A receiver must not require the two to be simultaneous**, and
must not read `reason_code NONE` in the first post-abort snapshot as "no reason".

## Framing and receiver (`OBS`)

| | |
|---|---|
| frames ok | **586** |
| CRC failures | **0** |
| oversize rejects | **0** |
| decode errors | **0** |
| bytes discarded | 304 — **all leading, 0 interior** |
| buffered at end | 0 |

```
LiveFrame 344 raw (323 promoted)   Aborted 1   Status 1
StatePacket 120   RouterStatus 60   Hello 60
344×1689 + 20 + 38 + 120×15 + 60×37 + 60×47 + 304 = 588 218   → residual 0
```

Receiver: `hello_session_ids [6]`, `measurement_state ABORTED`,
`abort_latched True`, `abort_reason_code TIMEOUT`, `decode_errors 0`.

Analog observation (not part of the verdict, and consistent with no stimulus):
peak source **−63.9 dBFS**, peak return **−65.7 dBFS**, `tf_confidence 0`,
`tf_clamped_count 0`, no clipping. **Source and return are within 1.8 dB of each
other and both at the noise floor — the signature of nothing being plugged in and
playing**, which is the independent confirmation that this was a no-stimulus run.

## ★ Session counter across real power cycles (`OBS`)

Three boots are now observable in committed and preserved artifacts:

| Session | Captures |
|---|---|
| **4** | 2026-09-26: 5 s first capture, 30 s idle fixture, Step A abort |
| **6** | 2026-09-27: 120 s idle (`06:46Z`), negative control (`07:02Z`) |
| **7** | 2026-09-27: the 1 kHz RESULT run (`04:56Z` on the 28th UTC) |

**The monotonic session counter increments across real power cycles, and this is
now `OBS` rather than `INFER`.** TODO-56's central claim — a changed `session_id`
is authoritative evidence of a new Teensy session — has hardware support: two
captures inside session 6 report the same id, and a power cycle changed it.

**Session 5 was never captured.** A boot happened whose stream nobody was
recording. The counter is monotonic, not gap-free from the receiver's point of
view, so **a receiver must treat any change as a new session and must not expect
+1.**

## What this does NOT prove

- **Not reboot recovery.** No receiver was running *across* a reboot. The sessions
  come from three separate captures, so the Pi-side requirement — recover without
  being restarted and re-read HELLO — is still untested. Runbook step 10 stays open.
- **Not a RESULT.** No RESULT packet exists in either file.
- **Nothing about `x`.** No VIEW packet in either capture; the ABORTED latch was
  never acknowledged inside a capture window.
- **Not T1**, not the Pi→Teensy path, not the UI.
