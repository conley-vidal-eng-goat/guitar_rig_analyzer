# Pi Link Protocol Audit — `data_sender` wire format vs. the canonical measurement model

**Date:** 2026-09-11 · **Status:** 🔒 **SCHEMA-FROZEN, TRANSPORT-UNPROVEN.** Protocol **v2** implements every fix below. The field layout is frozen as of 2026-09-11; the transport's real-time behaviour is not yet proven on hardware.

## What "schema-frozen, transport-unproven" means

This distinction is the whole point of the current state, so it is stated before anything else.

**🔒 FROZEN — do not change without a defect and a version bump.** A Pi-side parser written against these will not need rewriting:

- Field positions and widths in every packet
- Packet type ids (`0x01`–`0x07`)
- Enum meanings (`result_quality`, `calibration_type`, `estimator`, `stimulus`, `fft_mode`, `window_function`, view ids)
- Clamp and coverage semantics — the nibble encoding, and the rendering contract that `clamped == ratio` means saturated rather than measured
- RESULT layout, including the 156-byte fixed block
- Framing: sync word, length field, CRC-16/CCITT over payload, receiver resync rules

**🔓 STILL MOVABLE — a parser does not depend on these.** Phase 10's measurement may change any of them:

- Live frame **cadence** (`DISPLAY_UPDATE_EVERY_N_FRAMES`, currently 1 — a frame every block)
- **Bin count** (`DS_LIVE_BINS`) — changes frame *size*, not field *meaning*, and HELLO advertises it
- **TX buffer size** (`DS_TX_BUFFER_BYTES`) and chunking strategy
- Scheduling: when `dataSender_service()` runs, how much it drains per call
- Baud rate

A receiver that reads `live_bins` and `decim_ratio` from HELLO instead of hardcoding them is immune to every item in the second list. **Write it that way.**


**Trigger:** [ADR-001](adr/ADR-001-display-architecture.md) promoted `data_sender`
from an orphaned module to the production presentation backend. Its protocol was
written before the clamp-marker work, the confidence-denominator fix and the
insight/provenance model reached their current form, and had never been checked
against them.
**Tracked as:** TODO-34.

---

## Resolution status — protocol v2 (2026-09-11)

`PI_PROTOCOL_VERSION` is now **2** ([config.h](../config.h)). All three
`DISPLAY_TARGET` builds compile clean, and the `_PI` and `_NONE` builds compile
with **zero warnings** — the unused `payload_size` that finding T5 names is gone
along with the code that held it.

**Why v2 and not v1-frozen.** v1 was never frozen and never had a receiver, but
the literal string `protocol=1` did exist in committed source, and v2 changes the
payload shape of both LIVE_FRAME and RESULT. A version number that has appeared
in the tree is not reused for a different layout — an old log reading
`protocol=1` must not be ambiguous about which layout produced it.

| # | Finding | Status in v2 |
|---|---|---|
| L1 | TF clamp mask not transmitted | 🟢 **CLOSED** — per-bin clamped/valid nibbles + frame-level `tf_clamped_count`; render contract written into the header |
| L2 | One arithmetic mean across linear and dB domains | 🟢 **CLOSED** — linear spectra now decimate by **maximum** (peak-preserving); `tf_db` keeps the dB mean, and both choices are stated on the wire contract |
| L3 | NaN coverage lost in decimation | 🟢 **CLOSED** — per-bin valid-source-bin count; zero coverage emits NaN so the receiver pen-lifts |
| L4 | Persistence flag transmitted | 🟢 unchanged |
| R1 | `result_valid` not transmitted | 🟢 **CLOSED** — byte 0 of RESULT |
| R2 | `calibration_provenance` not transmitted | 🟢 **CLOSED** — `char[96]` at offset 58 |
| R3 | `calibration_type` / `calibration_warnings` not transmitted | 🟢 **CLOSED** — type byte + 5-bit warning field |
| R4 | Result auto-spectra absent | ⚪ **DEFERRED, deliberate** — +4 KB per RESULT; revisit once T1 is measured |
| R5 | `firmware_version` unstructured | 🟢 **CLOSED** — structured field in RESULT **and** in HELLO |
| R6 | Hardware/capture context absent | 🟢 **CLOSED** — `fft_size`, capture blocks, node channels, `line_in_level` |
| R7 | `phase_unwrapped` / `tf_raw_mag_db` absent | ⚪ **DEFERRED, deliberate** — group delay is sent; raw magnitude needs the cal curve anyway |
| T1 | Blocking UART writes in the real-time loop | 🟡 **MITIGATED — NOT YET MEASURED.** See below |
| T2 | Protocol version is a string | 🟢 **CLOSED** — structured HELLO packet (`0x06`) with a capability bitmap |
| T3 | No view-change packet | 🟢 **CLOSED** — VIEW packet (`0x07`) |
| T4 | Cannot express "feature not compiled in" | 🟢 **CLOSED** — HELLO capability bits for `ENABLE_DUT_INJECTION` / `ENABLE_MONITOR_MODE`; `MODE_PRECISION` / `MODE_LF` bits stay clear because `arm()` still rejects them |
| T5 | Unused `payload_size` | 🟢 **CLOSED** — that code path was rewritten; builds are warning-free |
| T6 | Framing design sound | 🟢 unchanged |

### T1 — what changed, and what is still unproven

The architectural rule is now explicit in the source:

> **Presentation transport must be lossy before measurement becomes lossy.**

Implemented as:

| Packet | Delivery | On no room |
|---|---|---|
| LIVE_FRAME | best effort, latest-wins | **dropped and counted** |
| RESULT | reliable — staged, drained across loop iterations | queued; superseded by a newer result |
| STATUS / ABORTED / ROUTER / VIEW / HELLO | best effort | dropped and counted |

Every write is gated on `availableForWrite()` and there are **no blocking writes
left in the module**. The UART TX buffer is extended to 4 KB via
`addMemoryForWrite()` — without that, `availableForWrite()` could never report
room for a 1 689-byte frame and *every* live frame would be dropped, a silent
total failure of the live path that would present as a Pi-side bug. A
`static_assert` now enforces `DS_TX_BUFFER_BYTES > one framed live frame`.

**Safety net for dropped events:** `measurement_state` travels in every live
frame, so a dropped ABORTED costs the reason string, not the fact. Receivers
should treat the live frame's state byte as authoritative and event packets as
enrichment.

**What is still unproven.** The prediction below stands and has **not** been
measured:

| Packet | Size | Predicted wire time | vs. 46.3 ms block period |
|---|---:|---:|---|
| LIVE_FRAME, 128 bins, v2 | 1 689 B | ~36.7 ms | ~79 % |
| RESULT, 12 insights | 10 012 B | ~217 ms | ~4.7 periods |

v2's live frame is *larger* than v1's (1 689 B vs 1 559 B) because closing L1 and
L3 costs 130 bytes of coverage data. That is the correct trade — the added bytes
are what stop the Pi rendering a saturation rail as a measurement — and it is
only safe **because** the frame is now droppable rather than blocking.

The instrumentation to settle it exists: `dataSender_getStats()` and the `u`
serial command report measured max/mean call duration, drop counts and longest
drop streak, minimum observed TX room, and result drain time. **With the
non-blocking policy the measured max call time should be microseconds, not
milliseconds.** A max approaching a millisecond means something is blocking and
the policy has been violated somewhere.

**Do not close T1 on this document's authority.** It closes on a Phase 10 bench
measurement with a Pi actually consuming data, plus the disconnected-Pi case.

---

## Why this audit exists

ADR-001 establishes one invariant:

> **The Teensy determines truth. The Pi presents truth.**

That invariant has a mechanical test:

> **If the Pi must derive a judgement the Teensy already made, the protocol is
> wrong.**

Four of the findings below are failures of exactly that test. They are not
cosmetic omissions — they are places where the firmware computes a verdict and
then drops it on the floor at the UART, leaving the Pi to guess.

**Evidence basis.** This is a source audit: every finding is sourced to a file and
line. The transport findings (T1) include an analytic timing prediction derived
from baud rate and packet size — **that prediction has not been measured on
hardware** and is labelled as such. Nothing here has been verified against a Pi,
because no Pi has been connected.

---

## Reference: what the canonical model contains

| Source | Shape |
|---|---|
| `AudioFrame` ([audio_engine.h:104](../audio_engine.h#L104)) | live: 512-bin linear spectra ×2, 512-bin `tf_db`, clamp bitmask, persistence flag, confidence, peaks |
| `MeasurementResult` ([measurement_core.h:420](../measurement_core.h#L420)) | result: 8 × 512-bin float arrays, validity, quality, health metrics, calibration status + 96-char provenance, hardware context, firmware version |
| `InsightList` ([insights_engine.h:122](../insights_engine.h#L122)) | up to `INSIGHTS_MAX_COUNT` = 12 insights, MEASUREMENT vs ADVISORY |

---

## LIVE_FRAME (`0x01`) — findings

### 🔴 L1 — The TF clamp mask is not transmitted. This is the most serious finding.

`audio_engine` clamps each bin's raw TF into `[TF_DB_MIN-6, TF_DB_MAX+6]` before
the EMA, and records which bins were railed in `AudioFrame.tf_clamped_bits[]` plus
`tf_clamped_count`. The header states the contract explicitly
([audio_engine.h:310](../audio_engine.h#L310)):

> "Any consumer that RENDERS `tf_db` to a human (serial diagnostic, display curve,
> export) **must check this first** and present the bin as saturated rather than
> printing the rail as a number."

[`dataSender_sendLiveFrame()`](../data_sender.cpp) decimates `tf_db` straight to
the wire and transmits **neither** `tf_clamped_bits` nor `tf_clamped_count`. Under
ADR-001 the Pi becomes precisely the consumer that header is addressing, and it
is structurally unable to comply.

**Why this matters concretely.** On 2026-09-07, with nothing connected to
RETURN_NODE, the true TF was ~−47 dB — 23 dB below the −24.0 dB rail — and the
diagnostic printed `1kHz=-24.0dB` in 33 of 33 consecutive windows "as though it
were data" ([audio_engine.h:145](../audio_engine.h#L145), evidence file
`ai/evidence/2026-09-07-tf-clamp-preserved.md`). Commit `aa9a795` fixed that for
the serial diagnostic. Shipping the current packet layout would reintroduce the
identical defect on the Pi's TF plot — a flat, confident, entirely fictional
−24 dB curve.

This is also the same still-open defect as TODO-29's second half
([display_engine.cpp:347](../display_engine.cpp#L347) renders railed bins as
ordinary curve points). **Promoting `data_sender` re-opens TODO-29 on a new
surface**, which is an argument for fixing the class of bug at the presentation
boundary rather than once per renderer.

**Invariant test: FAILS.** The Teensy knows the bin is saturated. The wire discards
it. The Pi would have to re-derive saturation by pattern-matching its own plot.

**Fix:** transmit the decimated clamp state. Because decimation merges bins, a
single bit per output bin is lossy in a misleading direction — send a per-output-bin
count of clamped source bins, or a two-bit state (none / partial / all).

### 🟡 L2 — `decimateBins()` applies one arithmetic mean across two different domains

[`decimateBins()`](../data_sender.cpp) block-averages with a plain arithmetic mean.
It is called on three arrays that are **not in the same domain**:

| Array | Domain | Source |
|---|---|---|
| `fft_source`, `fft_return` | **linear** magnitude 0.0–1.0 | [audio_engine.h:107](../audio_engine.h#L107) |
| `tf_db` | **dB** | [audio_engine.h:115](../audio_engine.h#L115) |

Consequences differ per array and neither is recorded as a decision:

- **Linear spectra:** an amplitude mean buries narrow peaks. One bin at 0.5 among
  three at 0.001 decimates to 0.126 — a **12 dB under-report** of the peak. For a
  spectrum analyzer display this is the wrong default; max-hold (or a
  power-domain mean) is the conventional choice, and max-hold is what makes a
  harmonic visible at all at 128 bins.
- **`tf_db`:** an arithmetic mean of dB is a *geometric* mean of power, which
  smears both nulls and peaks of the transfer function — the two features a rig
  analyzer exists to show.

Not necessarily a bug, but currently an **undocumented default** rather than a
choice. Decide per array, then state the decision in the protocol doc so the Pi
knows what it is plotting.

### 🟡 L3 — NaN semantics silently change across decimation

`decimateBins()` skips NaN inputs and averages the survivors. A 4:1 block with one
valid bin and three NaN therefore emerges as a **fully valid** output bin.

In `tf_db`, NaN is meaningful: it marks a bin whose source fell below
`TF_SOURCE_GATE`, i.e. unenergised — it is the pen-lift signal that keeps the
display from drawing through gaps ([audio_engine.h:118](../audio_engine.h#L118)).
The Pi receives no way to distinguish "4 of 4 bins measured" from "1 of 4 bins
measured", so partial validity renders as full confidence.

**Fix:** send a valid-source-bin count (or fraction) per output bin, or propagate
NaN when coverage falls below a stated threshold. Either way the threshold becomes
a Teensy-side decision, as the invariant requires.

### 🟢 L4 — `tf_persistence_active` is transmitted correctly

Flags bit 2. The "sticky instrument" state reaches the Pi. No action.

---

## RESULT (`0x02`) — findings

### 🔴 R1 — `result_valid` is not transmitted

[`MeasurementResult.result_valid`](../measurement_core.h#L424) is the firmware's
top-level verdict on whether the measurement means anything. The RESULT payload
carries `result_quality` but **not `result_valid`**. The Pi would have to infer
validity from the quality enum.

**Invariant test: FAILS**, and this is the cleanest example in the audit. Validity
is a Teensy judgement; the Pi is left to reconstruct it.

### 🔴 R2 — `calibration_provenance[96]` is not transmitted

The result view is specified to show quality **and provenance** — README's feature
list and TODO-12's proof criterion both require it. The 96-char provenance string
never reaches the wire, so the Pi cannot display where a calibration came from,
and a saved measurement cannot record it.

### 🔴 R3 — `calibration_type` and `calibration_warnings` are not transmitted

The payload sends a single `cal_applied` bit. It omits which calibration type was
applied and, more seriously, the `calibration_warnings` field. The Pi would
present a calibrated result with no indication that the calibration carried
warnings — the firmware's own caveat is dropped.

**Invariant test: FAILS.**

### 🟡 R4 — Result auto-spectra `S_xx_db[512]` / `S_yy_db[512]` are absent

Four 512-bin arrays are sent (`tf_cal_mag_db`, `tf_cal_phase_rad`,
`group_delay_ms`, `coherence`); the source and return auto-spectra are not. The Pi
therefore has full-resolution spectra **only** in the live path, and only
decimated. Compare/Recall views over saved measurements want the real thing. Costs
+4096 bytes per RESULT — see T1 before adding it.

### 🟡 R5 — `firmware_version` is not a structured field

It appears only inside the free-text identification string built in
`dataSender_init()`, which the Pi must string-parse. A measurement saved on the Pi
cannot be reliably stamped with the firmware that produced it. Put it in the
RESULT payload (and in a structured HELLO — see T2).

### 🟡 R6 — Hardware and capture context are absent

Not transmitted: `fft_size`, `fft_mode` is sent but `capture_start_block` /
`capture_end_block`, `source_node_ch`, `return_node_ch`, `line_in_level` are not.
Recall and comparison are only meaningful if the Pi knows the route and gain a
measurement was taken under — otherwise it will happily A/B two measurements taken
at different `LINE_IN_LEVEL` settings and present the difference as a rig
difference.

### 🟡 R7 — `phase_unwrapped` and `tf_raw_mag_db` are absent

`tf_cal_phase_rad` is sent; the unwrapped phase array and the uncalibrated
magnitude are not. Probably acceptable — group delay is sent, and raw magnitude is
recoverable only with the calibration curve — but it should be a recorded decision,
not an omission.

---

## Transport and framing — findings

### 🔴 T1 — Blocking UART writes sit inside the real-time super-loop

`data_sender` writes straight to `DS_UART_PORT`. Teensy `HardwareSerial::write()`
**blocks when the TX buffer is full**, and the default Serial1 TX buffer is small.
At 460800 baud 8-N-1 the wire moves 46 080 bytes/s:

| Packet | Size | Wire time | vs. 46.3 ms audio block period |
|---|---:|---:|---|
| LIVE_FRAME @ 128 bins | 1 559 B | **~33.8 ms** | **73 % of one block period** |
| RESULT, 0 insights | 8 224 B | ~178 ms | ~3.8 block periods |
| RESULT, 12 insights (max) | 9 880 B | **~214 ms** | **~4.6 block periods** |

`DISPLAY_UPDATE_EVERY_N_FRAMES` is **1** ([config.h:317](../config.h#L317)), so a
live frame is sent **every** output block. The block period is 46.3 ms measured
(journal 2026-09-05 (10); note the `EXPECTED_BLOCK_MS` constant itself is wrong by
2×, TODO-27).

This is the **same failure shape as the RA8875 incident** that motivated ADR-001 —
a display peripheral stalling the audio loop — reached through a different
peripheral. It would be an unforced error to replace `waitPoll()` spinning with
UART blocking and call it an architectural improvement.

**⚠️ Evidence tier: this is an analytic prediction, not a measurement.** It is
derived from baud rate, packet size and the documented blocking behaviour of
`HardwareSerial`. The actual TX buffer size, and whether the Audio library's DMA
keeps the queue drained across a stall, have **not** been measured. Do not record
this as a bench finding until it is instrumented on hardware — that measurement is
part of TODO-35's acceptance.

**Candidate fixes** (decide after measuring): `Serial1.addMemoryForWrite()` with a
buffer sized to a whole live frame; chunked non-blocking transmission across loop
iterations; sending RESULT in sections; or raising
`DISPLAY_UPDATE_EVERY_N_FRAMES` to 2 and taking ~10.8 fps (corrected 2026-09-21
from "~5.4 fps", which derived from the pre-todo-27 92.9 ms block period; the
argument below is unaffected — only the rate figure was wrong). Note that the
`data_sender.h` bandwidth table reasons about **average** throughput (~18 KB/s of
46 KB/s) and is correct on that axis — the problem is **burst latency inside one
block period**, which the table does not model.

### 🟡 T2 — The protocol version is a string, not a structured field

`dataSender_init()` sends `"GRA v0.5.0 | protocol=1 | live_bins=128 | ..."` as a
STATUS packet. The Pi must string-parse its own compatibility contract, and a
breaking change cannot be detected mechanically. Since ADR-001 makes this a
two-codebase compatibility surface, versioning is now mandatory: add a dedicated
HELLO packet with numeric `protocol_version`, `live_bins`, `fft_bins`,
`firmware_version`, and a capability bitmap.

### 🟡 T3 — No view-change packet

`presentation_restoreLive()` has no packet to map to and currently sends a STATUS
string `"VIEW:LIVE"` (see [presentation.cpp](../presentation.cpp)). A Pi state
model cannot distinguish a view transition from ordinary status text without
sniffing for a magic prefix. Add an explicit view/state packet.

### 🟡 T4 — ROUTER_STATUS cannot express "feature not compiled in"

The payload has `injection_active` and `monitor_mode` bytes, but
`ENABLE_DUT_INJECTION` and `ENABLE_MONITOR_MODE` are both **0**
([config.h](../config.h)), so `monitor_mode` is written as a literal 0. The Pi
cannot distinguish "monitor mode is off" from "monitor mode does not exist in this
build" — and would be entitled to render a UI control for a capability that cannot
respond. Put the feature-promotion state in the HELLO capability bitmap (T2).

### 🟡 T5 — `payload_size` is computed and unused in `sendLiveFrame`

[data_sender.cpp:129](../data_sender.cpp#L129) computes `payload_size` and then
passes `pos` to `sendPacket()`. They are currently equal, so this is not a live
bug — it is the one site where a header-length / payload-length desync could
appear silently, and it is the source of the build's one remaining warning. Either
use it or `static_assert`/assert the equality.

### 🟢 T6 — Framing design is sound

Sync word `0xAA55`, type byte, little-endian length, CRC-16/CCITT over payload
only, documented receiver algorithm (scan → type+length → payload+CRC → verify →
discard on mismatch). No action. This is the part of `data_sender` that justifies
keeping the module rather than rewriting it.

---

## Summary

| # | Finding | Severity | Invariant |
|---|---|---|---|
| L1 | TF clamp mask not transmitted | 🔴 | **FAILS** |
| L2 | One arithmetic mean across linear and dB domains | 🟡 | — |
| L3 | NaN coverage lost in decimation | 🟡 | — |
| L4 | Persistence flag transmitted | 🟢 | ok |
| R1 | `result_valid` not transmitted | 🔴 | **FAILS** |
| R2 | `calibration_provenance` not transmitted | 🔴 | — |
| R3 | `calibration_type` / `calibration_warnings` not transmitted | 🔴 | **FAILS** |
| R4 | Result auto-spectra absent | 🟡 | — |
| R5 | `firmware_version` unstructured | 🟡 | — |
| R6 | Hardware/capture context absent | 🟡 | — |
| R7 | `phase_unwrapped` / `tf_raw_mag_db` absent | 🟡 | — |
| T1 | Blocking UART writes in the real-time loop | 🔴 | — |
| T2 | Protocol version is a string | 🟡 | — |
| T3 | No view-change packet | 🟡 | — |
| T4 | Cannot express "feature not compiled in" | 🟡 | — |
| T5 | Unused `payload_size` | 🟡 | — |
| T6 | Framing design sound | 🟢 | ok |

**Five 🔴 findings. Four invariant failures.** Every one was the same mistake: the
firmware computed a judgement and did not put it on the wire.

**All five are addressed in protocol v2** — see the resolution table at the top of
this document. The payload-shape findings (L1, R1, R2, R3, T2) are closed in
source; T1 is mitigated by the delivery policy but **its measurement is
outstanding**, and it is the one finding that can still invalidate the design.

**The schema is frozen; write the Pi-side parser against it.** Read `live_bins`
and `decim_ratio` from HELLO rather than hardcoding them, and the parser is also
immune to the cadence/sizing changes that Phase 10 might still force. See
"What schema-frozen, transport-unproven means" at the top of this document for the
exact boundary between what is frozen and what can still move.

The protocol is good work that predates three rounds of firmware learning. That is
a normal thing to find in an interface that was written early and never exercised;
it is not a reason to distrust the module.

---

## Protocol acceptance tests — the invariant, made mechanical

These exist so the four invariant failures cannot silently return. Run them
against any proposed protocol change, **before** the change is written, not after.

### Test A — the truth question, field by field

For **every** field a receiver displays, answer one question:

> Is this a **fact** the Teensy knows, or a **judgement** the Pi is
> reconstructing?

If it is a judgement — valid/invalid, clipped, clamped, saturated, quality grade,
calibration state, confidence classification, coverage — **the answer is send
it.** A receiver that computes any of these from the numbers it was given has
been handed an incomplete packet, and the defect is in the protocol, not the
receiver.

Applied to v2, every such judgement now has a wire field:

| Judgement | Where it travels |
|---|---|
| Is the result valid at all? | RESULT `result_valid` |
| How good is it? | RESULT `result_quality` |
| Was anything clipped, and how much? | RESULT flags + clip counts; LIVE flags |
| Is this TF bin a saturation rail? | LIVE per-bin clamped nibble |
| How much of this TF bin is real? | LIVE per-bin valid nibble |
| Is the whole curve railed? | LIVE `tf_clamped_count` |
| Is the curve carrying EMA history? | LIVE `tf_persistence_active` |
| Was a calibration applied, of what kind, with what warnings, from where? | RESULT cal type + warning bits + provenance |
| Does this build even have monitor mode / injection? | HELLO capability bits |
| What view should be shown? | VIEW packet + RESULT/ABORTED arrival |

### Test B — no new blocking write

`grep` the module for `DS_UART_PORT.write`. **Every** occurrence must be preceded
in its own control-flow path by an `availableForWrite()` check covering the whole
remaining packet. A write that can block is a measurement defect, not a display
defect — it is the RA8875 `waitPoll()` failure reached through a different
peripheral.

### Test C — layout drift cannot be silent

The RESULT fixed block is pinned twice: a `static_assert` on
`DS_RESULT_FIXED_BYTES`, and a runtime check that the serialiser actually filled
exactly that many bytes before the spectra begin. A field added without updating
the layout comment shifts every later offset, and the symptom on the Pi is
plausible-looking wrong floats rather than an error. The runtime check refuses to
send a drifted packet.

### Test D — a receiver survives what it does not understand

A v2 receiver must skip an unknown `packet_type` by consuming
`payload_length` bytes and resuming the scan. Verify by sending a synthetic
packet with type `0xFE`. This is what allows a future additive packet type
without a version break.

### Test E — the renderer cannot perturb the measurement

This is the Phase 10 acceptance criterion and the only one that requires
hardware. See the runbook's Phase 10; in summary, with a Pi attached and
consuming: measured max call duration stays in microseconds, and block timing is
statistically unchanged between a Pi present, a Pi stalled, and a Pi absent.
