# Pi-side receiver — Guitar Rig Analyzer link (protocol v2)

Raspberry Pi 5 half of the Teensy→Pi presentation link. Authority:
[ADR-001](../docs/adr/ADR-001-display-architecture.md) · TODO-34 / TODO-36 ·
[protocol audit](../docs/pi_link_protocol_audit.md) ·
[runbook Phase 10](../docs/breadboard_bringup_v3.md).

## What exists today

Bytes in, typed Teensy-authored records out. Nothing else — no serial I/O,
no UI, no framework.

```
analyzer_link/
  crc.py        CRC-16/CCITT-FALSE, mirroring crc16_block() in data_sender.cpp
  protocol.py   constants, enums, Geometry — a MIRROR of the firmware headers
  framing.py    FrameScanner: sync, resync, CRC verification, bounded lengths
  packets.py    decoders for 0x01–0x07 + UnknownPacket, and the clamp contract
tests/
  vectors.py    synthetic protocol v2 packet builder (the test stimulus)
  test_crc.py
  test_framing.py
  test_packets.py
  test_firmware_header_sync.py   drift guard — parses the real Teensy headers
```

Run: `sh pi/run_tests.sh` — Python 3 standard library only. No pytest, no
numpy, no network, no cloud service.

## The invariant this code exists to protect

> **The Teensy determines truth. The renderer presents truth.**

Nothing here computes a measurement value, a validity verdict, a quality grade
or a confidence figure. `result_valid`, `result_quality`, `mean_coherence`,
`tf_confidence` and the per-bin coverage nibbles are Teensy verdicts, read off
the wire and carried through unchanged. `test_firmware_header_sync.py` enforces
the weaker but checkable half of this by failing if the receiver ever imports
an FFT library.

The one derived thing is `BinCoverage`, and it is rendering policy over
Teensy-authored bytes: the Teensy says *"3 of 4 source bins were clamped"*, the
receiver decides that means a saturation marker. It never decides that a
clamped bin was really fine.

## Two things to know before writing a renderer

**1. Geometry comes from HELLO, never from a constant.** `live_bins`,
`fft_bins` and `decim_ratio` are explicitly *not* frozen — the T1 measurement
may change cadence or bin count. The defaults in `protocol.py` exist for tests
and offline tooling. A live receiver reads `Hello.geometry`.

**2. A clamped bin is a saturation rail, not a measurement.** Consult
`BinCoverage` before every point you draw:

| condition | render |
|---|---|
| `saturated` (clamped == ratio) | saturation indicator at the rail — **not** the value |
| `pen_lift` (valid == 0) | draw nothing |
| `partially_saturated` | plot, marked |
| `partial_coverage` | plot, marked |
| otherwise | plot normally |

On 2026-09-07 a consumer that ignored clamp state reported `1kHz=-24.0dB` in
33 of 33 consecutive windows as though the rail were data. Protocol v2 exists
largely to stop the Pi repeating that (audit finding L1).

## Evidence status — read before citing any of this

| Claim | Tier |
|---|---|
| Parser is self-consistent with `data_sender.h`; CRC, framing, resync, bounded lengths and unknown-type tolerance behave correctly | `OBS` — 70 tests, offline |
| Mirrored constants and enums match the firmware headers | `OBS` — drift guard parses the headers |
| Parser agrees with the **compiled firmware on the wire** | **NOT ESTABLISHED** |
| Any Phase 10 runbook step | **NOT PASSED** |

The test vectors are synthesized from this repository's reading of
`data_sender.h`. Encoder and decoder share one author and one interpretation,
so a misreading would be reproduced on both sides and every test would still
pass. **Firmware agreement requires a captured real Teensy byte stream**
(runbook Phase 10 step 4 onward, hardware required). Until that capture
exists, no Phase 10 step may be recorded as passed on the strength of this
directory.

## Not yet built

- Receiver state model (measurement state, sticky `ABORTED`, HELLO lifecycle)
- Serial transport (`/dev/serial0`) and capture/replay tooling
- Renderer / UI — **blocked on T1** per TODO-36, and the framework choice needs
  its own ADR rather than being buried in a code change
- Pi→Teensy command path — **does not come through the presentation boundary**
  ([presentation.h](../presentation.h)); it is CONTROL, with its own validation

## HELLO lifecycle (TODO-56)

**HELLO arrives repeatedly, not once.** The Teensy re-announces every
`HELLO_REANNOUNCE_MS` (1 s) while no RESULT is staged, so a receiver that
attaches late, restarts, or loses one to backpressure is not locked out.
Handle repeats idempotently.

Treat the period as the expected *cadence*, **not** as a timeout to enforce.
Announcements are best-effort and are dropped under backpressure by design, so
a missed one is normal and means nothing on its own.

**`session_id` (HELLO bytes 18–19) is how a repeat is told from a restart.**

| Observation | Meaning |
|---|---|
| Same `session_id` | Routine re-announcement. Same instrument session; keep your state |
| **Changed `session_id`** | **New Teensy session. Prior state is stale** — invalidate it and rebuild from current telemetry. Do not assume continuity |

It is not a security nonce, not a measurement identity, and **not unique across
devices** — two Teensys can both be at boot 42. `0` is a legitimate value (the
firmware counter wraps `0xFFFF → 0`, and a blank EEPROM's first boot lands
there), so never treat `0` as "absent".

**Do not use `output_block_number` to detect a reboot.** It is 16 bits and
wraps on its own roughly every 50 minutes, so "it went backwards" is not sound
evidence of a restart.

Acting on a session change is the receiver state model's job and is **not built
yet**. This layer only surfaces the field.

## Still true: RESULT cannot be decoded before HELLO

`fft_bins` has no other carrier, and the `insight_count` that would let you
solve for the array length sits *after* the arrays. `decode_result()` raises
`GeometryUnknown` rather than guessing. With the re-announcement in place the
wait is now bounded by about a second instead of by a Teensy reboot.
