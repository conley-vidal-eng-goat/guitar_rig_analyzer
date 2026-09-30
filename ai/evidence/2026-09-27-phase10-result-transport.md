# The first RESULT to cross the wire — real 1 kHz stimulus, Teensy → Pi 5

**2026-09-27 (capture timestamped 2026-09-28T04:56:04Z UTC = 21:56 local).**
First hardware exercise of the **reliable** transport path. Firmware `26f2bee`
unmodified. No Phase 9 validation, no internal generator, no injection, no relay
or route change, no wiring change.

## Artifacts

| | |
|---|---|
| UART capture | [`phase10-result-1khz.bin`](phase10-result-1khz.bin) |
| Bytes | **125 480** |
| **SHA-256** | `e8b57d6f62af1367b654dd6d13270a94d73f06868ac785edf353f20179dd14a1` |
| Capture log | [`phase10-result-1khz.capturelog`](phase10-result-1khz.capturelog) |
| Device | `/dev/ttyAMA0`, receive-only link unchanged |
| Firmware | `26f2bee`, v0.6.0, protocol v2, build `Sep 26 2026 16:36:53` |
| Session | **7** |

**Hash re-verified on the Mac 2026-09-27** against the value `capture.sh` printed
on the Pi. They agree, so the artifact survived the transfer intact.

**Firmware provenance re-checked, not assumed.** The archived HEX
[`firmware/26f2bee-PI/guitar_rig_analyzer.ino.hex`](firmware/26f2bee-PI/guitar_rig_analyzer.ino.hex)
still hashes to md5 `55ee39a5d8fba94cdad9606e9fa20a2f` / sha256
`24b71d73bf60a0d6ff9cbb5737a46bba6a04887a1fe55479d356b5a87dce3a6e`. The only
firmware-source drift between `26f2bee` and the current tree is a **comment-only**
edit to `data_sender.h` (the stale throughput table, corrected in `0f7f2dd`'s
lineage), so the running binary and the current source agree behaviourally.

## ⚠️ `capture.sh` printed its low-rate warning. It is not a link fault here.

The script compares against the ~36 500 B/s idle stream and this capture averaged
**2 091 B/s**, so it emitted the generic *"A byte count far below that is a link
fault"* text. That heuristic is calibrated for an **idle** instrument and this
instrument was not idle: after `m` completed, `presentation_updateLive()` is gated
to `IDLE|ARMED`, so LIVE_FRAME production **stopped by design** and only the
15/37/47-byte periodic packets remained. The low rate is the expected consequence
of the state the instrument was in, and the replay below — not the rate line — is
authoritative for what arrived.

**The warning's wording is worth keeping** rather than softening: it caught a real
defect on 2026-09-26. What it needs is a state-aware caveat, recorded as a tooling
note, not a relaxation.

## Preconditions — the stimulus, measured before the run (`MEAS`, USB console)

External source path: battery phone → active USB-C DAC → continuity-verified
3.5 mm TRS → 1/4" TS cable (left channel only, per
[`2026-09-13-J4-continuity-identification.md`](2026-09-13-J4-continuity-identification.md))
→ **J4 SOURCE**. Continuous ~1 kHz sine.

| | |
|---|---|
| SOURCE_NODE peak | **−21.8 dBFS** |
| RETURN_NODE peak | **−66.2 dBFS** |
| TF confidence | 2 % |
| TF clamped bins | 4 of 512 |
| 1 kHz spot | `RAIL[−24.0 dB]` |
| Raw SOURCE samples | clean sine, ≈ ±2 660 counts |
| Route | TS return, no injection |

−21.8 dBFS sits comfortably above the strict −40 dBFS arm threshold and far below
the −0.5 dBFS clip threshold, and matches the previously characterised −21.6 dBFS
condition. **No internal generator, injection or validation harness was involved.**

## Timeline (Teensy audio time, from the STATE block counter)

| t | Observation |
|---|---|
| 0.000 s | session established → **7**; `STATE UNKNOWN → IDLE` |
| 1.001 s | `ROUTE return_source TS` |
| 2.502 s | STATUS `"Measuring — external stimulus"` |
| 3.001 s | `STATE IDLE → CAPTURE`; **RESULT packet, quality POOR, valid True** |
| 3.500 s | `STATE CAPTURE → RESULT` |
| 5.001 s | LIVE STOPPED — no live frame for 2.50 s |

### The Pi's state sequence is shorter than USB's. That is not a contradiction.

USB observed `IDLE → ARMED → CAPTURE → PROCESSING → RESULT`. The Pi's periodic
STATE snapshots show `IDLE → CAPTURE → RESULT`. **STATE is a 500 ms sampler, and
ARMED and PROCESSING were both shorter than one sampling interval**, so they fell
between snapshots. A receiver must therefore never treat the STATE sequence as a
complete transition log — it is a state *observable*, which is exactly what
TODO-57 specified it to be.

## Framing and receiver (`OBS`, from the artifact)

| | |
|---|---|
| frames ok | **306** |
| CRC failures | **0** |
| oversize rejects | **0** |
| decode errors | **0** |
| bytes discarded | 1 598 — **all leading, 0 interior** (see the accounting record) |
| buffered at end | 0 |
| byte-accounting residual | **0** |

```
LiveFrame 64 raw (55 promoted, 9 geometry-blocked pre-HELLO)
Result     1     Status  1     StatePacket 120     RouterStatus 60     Hello 60
64×1689 + 8908 + 38 + 60×37 + 60×47 + 120×15 + 1598 = 125 480
```

Receiver: session established, `hello_session_ids [7]`, firmware `0.6.0`,
geometry 128 live / 512 FFT / 4:1 @ 44 100 Hz, `measurement_state RESULT`,
`abort_latched False`, `abort_reason NONE`, `view result`.
Router: `return_source TS`, all four detectors **UNKNOWN**,
`any_detector_available False`, injection inactive, `SOURCE_RETURN`,
description `"TS return, no injection"`.

## ★ The primary result — a complete Teensy-authored RESULT arrived intact

**8 901 B payload / 8 908 B framed, one packet, CRC valid.**

| Teensy-authored field | Value |
|---|---|
| `result_valid` | True |
| `quality` | POOR |
| `fft_size` | 1024 |
| `n_averages_completed` | 32 |
| `mean_coherence` | 0.798961 |
| `valid_bin_fraction` | 0.017467 |
| `insight_count` | 4 |
| `calibration_type` | INTERNAL_LOOPBACK, **applied False** |
| `calibration_warning_bits` | `0x01` `['CALIBRATION_MISSING']` |
| `clip_detected` | False |

All four canonical arrays decoded at the **512-bin** completed grid (not
`fft_size`), and the **per-array NaN conventions survived**, which is the point:

| array | elems | finite | NaN | ±Inf | min | max |
|---|---:|---:|---:|---:|---:|---:|
| `tf_cal_mag_db` | 512 | 4 | 508 | 0 | −24 | −24 |
| `tf_cal_phase_rad` | 512 | 4 | 508 | 0 | 1.767 | 2.1 |
| `group_delay_ms` | 512 | 2 | 510 | 0 | 0.04597 | 0.5739 |
| `coherence` | 512 | **512** | **0** | 0 | 0 | 0.9954 |

Magnitude, phase and group delay are NaN for an unenergised bin; group delay is
additionally NaN at bins 0 and 511 by design; **coherence uses 0.0, never NaN**,
because zero coherence is itself meaningful. Nothing became a silent zero and no
infinity appeared. This is the representation contract holding across a real
physical link, and it is what stops the Pi drawing a rail as a measurement.

## Analog observation — kept separate from the transport claim

| | |
|---|---|
| peak source | −21.8 dBFS |
| peak return | −66.2 dBFS |
| tf_confidence | 0.017 |
| tf_clamped_count | 4 / 512 |
| clipping | none |

**The sparse, POOR result is the expected shape for this experiment and is not a
defect.** The source was a single narrowband tone and the return path carried
essentially noise, so only the bins around 1 kHz were energised. The goal was
RESULT *transport*, not broadband DUT characterisation. **`replay.py` cannot fail
on any of this, by design.**

## Teensy-authored measurement judgment (`MEAS`, USB console)

```
[MeasEngine] Processing complete. Frames: 32, coherence: 0.80, valid bins: 2%, quality: POOR
[Main] Quality: POOR, coherence: 0.80, valid bins: 2%
[Insights] 4 insight(s) [advisories quality-gated]
```

1. `[MEAS][ALERT] Measurement quality` — POOR, coherence 0.80, valid bins 2 %.
2. `[MEAS][WARN] No calibration applied` — raw hardware TF; channel asymmetry not removed.
3. `[MEAS][WARN] Advisory analysis unavailable` — requires MARGINAL or better, no clipping, coherence ≥ 0.70.
4. `[MEAS][WARN] Signal level decrease` — broadband mean TF −24.0 dB.

**Point 3 is the quality gate working.** The firmware refused to author advisories
it could not justify, and the refusal itself crossed the wire as an insight. The
Pi is required to render these four records and forbidden to derive its own.

## RESULT → IDLE acknowledgement and recovery

`x` was sent, and USB reported:

```
[MeasEngine] RESULT → IDLE
[Main] Returned to live view.
```

### 🛑 This is USB evidence. It is NOT Pi→Teensy proof, and it is not on the link.

`x` was typed into the **Arduino Serial Monitor over native USB**. The Pi→Teensy
direction is **physically disconnected** — Teensy pin 0 and Pi GPIO14 are both
unconnected by design. Nothing here shows the Pi commanding anything.

**And the recovery is not in the capture either.** `x` was sent *after* the 60 s
window closed, so the artifact contains **zero VIEW (0x07) packets**. Pinned as a
test (`test_the_link_carried_no_view_packet`) so the absence stays a recorded fact
rather than drifting into an assumption. **Post-`x` recovery ordering over the link
remains unestablished**, exactly as Step A left it on 2026-09-26.

## Producer-side diagnostics after `x` (`MEAS`, USB, 5 s window)

| | |
|---|---|
| Block period | 107 blocks / 5 000 ms = **46.7 ms** vs 46.4 expected (**+0.3 ms**) |
| Display | 97 updates = 51.5 ms/update |
| Results | **1 queued, 1 delivered, 0 superseded, 0 B abandoned, max drain 102 ms** |
| Live frames | 4 846 sent, **0 dropped** (0.0 %), longest drop streak 0 |
| STATE | 770 sent, 0 dropped | 
| ROUTER_STATUS | 385 sent, 0 dropped |
| HELLO | 386 sent, 0 dropped, session **7** constant |
| Events | 7 sent, 0 dropped |
| Call time | max **449 µs**, mean 15.9 µs, last 282 µs, 86 861 calls |
| Frame size | 1 689 B framed, 4:1 decimation, 128 live bins, protocol v2 |
| Atomicity | **0 best-effort packets refused while a RESULT was draining** |
| TX room min | **0 B of 4 096 B** |

### 🛑 `blocked_by_result = 0` does NOT exercise TODO-59's contention path.

It means **no independent best-effort send happened to collide** during the 102 ms
drain. The counter exists and reads zero; the guard was never asked to refuse
anything. **The positive contention case remains UNEXERCISED** — not passed, not
failed. Do not manufacture a collision merely to move the counter; that needs a
justified test plan, because the only honest way to produce one is to make a
best-effort producer fire inside a known drain window.

### ⚠️ `TX room min = 0 B` — preserved as an open observation, not explained away.

Recorded rather than dismissed. What is simultaneously true: the RESULT arrived
**complete and CRC-valid**, **zero** packets of any class were dropped, and block
timing stayed within +0.3 ms of expected. The T1 matrix explicitly treats `TX room
min = 0` as *backpressure being absorbed as designed* in runs 3/4 — but this was
**run-2-like conditions** (a reader consuming normally), where it was not
predicted. A 102 ms RESULT drain against a 4 096 B buffer is the obvious
candidate, since the staged drain deliberately fills the UART as fast as it will
take bytes. **Candidate, not conclusion** — the figure is a min-since-boot
high-water mark and nothing here timestamps it against the drain.

## What this proves

`OBS`, from the artifact:

- A physical Teensy UART → Pi 5 path carried a **complete 8 908-byte framed
  RESULT** that passed CRC.
- All four canonical **512-element** arrays decoded, with **per-array NaN/finite
  semantics intact**.
- Teensy-authored result metadata survived verbatim: validity, quality grade,
  averages, coherence, valid-bin fraction, calibration type and warning bits.
- **Four Teensy-authored insight records** survived.
- HELLO, STATE and ROUTER_STATUS kept operating **through** a measurement run.
- Session **7** stayed constant; no mid-capture reboot.
- Zero CRC failures, zero oversize rejects, zero decode errors, zero interior
  byte loss, zero end-buffer residue.

`MEAS`, from USB: the measurement completed, the Teensy authored the result and
its quality judgment, acknowledgement returned the machine to IDLE, live
processing resumed, and block timing stayed healthy.

## What this does NOT prove

- **Not T1.** Nothing here compares acquisition against a `_NONE` control. One
  healthy 5 s window with a Pi attached is not the four-run matrix.
- **Not TODO-59's positive contention case.** `blocked_by_result` read 0.
- **Not RESULT rendering.** There is no production Pi UI. Runbook step 7's clamp
  contract is proven at the *data* level only; the *rendering* clause is untested.
- **Not reconnect/reboot recovery.** No receiver was running across a reboot.
- **Not the Pi→Teensy command path.** Physically disconnected.
- **Not post-`x` recovery on the link.** No VIEW packet in the capture.
- **Not CRC rejection or unknown-type tolerance on the wire.** Both remain
  offline-only proofs; no corrupted byte has ever been transmitted.
- **Not Phase 10. Not Phase 9. Not TODO-34.**
- **Nothing about the analog quality of the rig.** The result is POOR and that is
  a signal-conditions observation, not a transport or instrument finding.
