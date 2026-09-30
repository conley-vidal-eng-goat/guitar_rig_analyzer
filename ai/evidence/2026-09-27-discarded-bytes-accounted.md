# `bytes discarded` accounted for byte by byte, across all five hardware captures

**2026-09-27.** The 1 kHz RESULT capture reported **1 598 bytes discarded** while
simultaneously reporting zero CRC failures, zero oversize rejects, zero decode
errors, zero end-buffer residue and a complete RESULT. The earlier 30 s idle
fixture reported 1 664, the negative control 304, and one capture reported 0.
Those figures were never explained, only bounded — so they were audited rather
than assumed harmless.

**Method:** `FrameScanner._drain()` was replicated exactly, instrumented to record
**every discard event with its absolute byte offset and cause**, fed in the same
4 096 B chunks `replay.py` uses, and run over all five artifacts. Inter-frame
contiguity was checked independently: for every frame, does its sync word sit
exactly where the previous frame ended?

## ★ Result — every discarded byte in every capture is at absolute offset 0

| Artifact | Bytes | Frames | Discarded | Events | Offset | Interior loss | Inter-frame gaps | Trailing |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `phase10-teensy-pi-idle-30s.bin` | 1 094 489 | 765 | 1 664 | **1** | **0** | **0** | **0** | **0** |
| `phase10-stepA-abort.bin` | 347 870 | 383 | 1 542 | **1** | **0** | **0** | **0** | **0** |
| `phase10-result-attempt.bin` | 4 378 056 | 3 064 | **0** | **0** | — | **0** | **0** | **0** |
| `phase10-result-no-stimulus.bin` | 588 218 | 586 | 304 | **1** | **0** | **0** | **0** | **0** |
| `phase10-result-1khz.bin` | 125 480 | 306 | 1 598 | **1** | **0** | **0** | **0** | **0** |

**One discard event per capture, at the very first byte, and nothing after it.**
`consumed + buffered == file length` in all five, so the audit is a closed
accounting rather than a sampling.

## What the discarded bytes are

The capture attaches to a stream that is already running, so it opens **inside a
packet**. The scanner cannot use those bytes: it has no sync word, no length and
no CRC for the packet they belong to, so it discards forward to the next sync.
In every case the first good frame is a **LIVE_FRAME (0x01)**, framed length
**1 689 B**, and the discard is that frame's remainder:

| Artifact | Discarded | Bytes into the live frame at open |
|---|---:|---:|
| `idle-30s` | 1 664 | 25 |
| `stepA-abort` | 1 542 | 147 |
| `result-no-stimulus` | 304 | 1 385 |
| `result-1khz` | 1 598 | 91 |
| `result-attempt` | 0 | opened **exactly** on a sync word |

All four non-zero figures are **less than one framed live frame**, which is
precisely the bound a mid-stream attach can produce. **1 598 is not a large
number — it is 91 bytes into one packet.**

## 🔑 Why the RESULT capture discarded *more* than the negative control

Because the figure has nothing to do with what happened during the capture. It is
set entirely by **where inside one packet the reader happened to attach**, which
is uniform over 0–1 688 and independent of everything else. 1 598 > 304 means the
RESULT capture opened 91 bytes into a frame and the control opened 1 385 bytes in.
**Reading a trend into these numbers would be reading noise**, and treating the
larger one as evidence of a worse link would have been exactly wrong: the capture
with the *largest* discard (`idle-30s`, 1 664) is the committed clean fixture.

## 🛠️ The old check was too weak, and it is now positional

`replay.py` compared the **total** against `max_payload_bytes()` = **10 005 B**,
calling anything below it *"explainable by a mid-stream start"*. Two faults:

1. **10 005 B is not what a mid-stream start can explain.** The reader lands inside
   one packet, so the bound is one **framed** packet, and the check used a
   *payload* size — the wrong quantity as well as the wrong magnitude.
2. **It said nothing about WHERE.** Up to 10 005 bytes of genuine **interior** loss
   — real bytes gone from the middle of the stream — would have passed silently
   under a figure the report described as a capture artefact.

The fault was in the *check*, not in the captures: the audit shows the artifacts
have zero interior loss. But the property the evidence relies on was being assumed
rather than tested. Now:

- `ScannerStats` splits the total into `bytes_discarded_leading` /
  `bytes_discarded_interior` plus `interior_discard_events`, with
  `bytes_discarded` kept as their sum so byte accounting and existing readers are
  unaffected. The split is positional: everything before the first CRC-verified
  frame is leading, everything after is interior.
- `replay.py` **fails a capture on any interior discard event**, and bounds leading
  discard by `protocol.max_framed_bytes()`.
- `reset()` (link drop) deliberately counts **nothing** — the caller threw those
  bytes away, so charging them as interior loss would make every reconnect look
  like a transport fault. The post-reset stream is a fresh attach.
- Six unit tests plus two real-byte fixture tests pin all of it.

**What this buys:** the next capture that loses a byte mid-stream fails loudly
instead of hiding inside a plausible total. That is a defect the tooling could not
previously have detected.

## Verdict on the original question

**The discarded bytes are a capture-attach artefact and nothing else, and that is
now measured rather than asserted.** They are not a parser accounting error — the
accounting closes to zero residual. They are not a transport defect — there is no
interior loss, no inter-frame gap, and no CRC failure anywhere in 6.5 MB of real
instrument bytes. They are not related to RESULT staging or live-frame suppression
— all four non-zero discards sit at offset 0, before any of that could apply.

## 🔍 Residual curiosity, recorded rather than smoothed over

**Every one of the five captures ends EXACTLY on a frame boundary** — zero trailing
bytes, zero buffered — and one of them also *began* exactly on one.

For the three low-occupancy captures that is expected: after live frames stop the
wire is idle >80 % of the time, so a capture stopped at a random instant almost
certainly stops in a gap. For the two **full-rate** captures it is not: at 79 %
occupancy each had roughly a 1-in-5 chance, ≈4 % jointly. Opening exactly on a sync
word is ≈1-in-1 689. **So something is probably aligning this, and it is not luck.**

**Leading hypothesis (`INFER`, not established):** the Pi 5 RP1 UART receive path
delivers to userspace in bursts delimited by **line idle**, and the Teensy writes
each packet as one contiguous burst followed by a gap. `cat` would then see roughly
one read per packet; the file would start wherever inside a burst the reader
attached, and end at the last **completed** burst, because the in-flight one is
never flushed to a process that `timeout` has already killed. One mechanism, and it
predicts both observations.

**Why this does not weaken any claim above.** It can only affect the *final partial
frame*, which would otherwise show up as `buffered at end > 0` — already reported,
already not an error. The byte accounting closes either way.

**Cheap way to settle it, software only, no bench risk:** on the Pi, take ~10 short
captures at full idle rate and replay each. If none ends with `buffered at end > 0`,
burst delivery is supported; if most do, the 5/5 alignment was coincidence after
all. Worth one session's ten minutes, worth nothing more than that.
