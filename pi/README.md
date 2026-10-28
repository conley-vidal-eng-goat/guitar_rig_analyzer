# `pi/`: the Raspberry Pi side

The Raspberry Pi 5 receives the Teensy's binary UART stream, decodes it, and
draws it on the 7" Touch Display 2 as a full-screen browser kiosk. See
[ADR-001](../docs/adr/ADR-001-display-architecture.md),
[ADR-005](../docs/adr/ADR-005-pi-rendering-stack-and-presentation-semantics.md)
and the [protocol audit](../docs/pi_link_protocol_audit.md).

## Layout

```
analyzer_link/          the wire protocol
  crc.py                CRC-16/CCITT-FALSE, matching crc16_block() in data_sender.cpp
  protocol.py           constants and enums mirrored from the firmware headers
  framing.py            sync, resync, CRC check, bounded lengths
  packets.py            decoders for every packet type, plus UnknownPacket
  state.py              packets -> instrument state
  presentation_semantics.py
                        the one classification layer every renderer uses
web/                    production renderer
  server.py             reads the UART (or a capture file), serves /api/frame
  payload.py            builds the classified frame the browser draws
  lab.py                LAB-view diagnostics computed from Teensy values
  static/               the browser client: LIVE, TONE, LAB and INFO views
analyzer_ui/            the older Tkinter renderer, kept as a test reference
tools/                  capture.sh, replay.py, byte_audit.py, t1_diff.py,
                        ab_capture.sh + ab_compare.py (rig A/B), pink_noise.py
tests/                  571 tests
deploy/                 kiosk autostart files and install steps
run_web.sh              start the kiosk web UI
run_kiosk_boot.sh       what the Pi runs at boot
run_ui.sh               start the Tkinter UI
run_tests.sh            run the test suite
```

Python 3 standard library only: no pytest, no numpy, no network. Run the tests
with `sh pi/run_tests.sh`. To run the UI against a recorded capture instead of
the live UART:

```sh
cd pi && python3 -m web.server --fixture ../ai/evidence/phase10-result-1khz.bin
```

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

## Evidence status

| Claim | How it's known |
|---|---|
| CRC, framing, resync, length limits and unknown-type handling behave correctly | Offline tests |
| Mirrored constants and enums match the firmware headers | Drift-guard test parses the real headers |
| Decoder agrees with the compiled firmware on the wire | Real captures off the UART, including a full 8,908-byte RESULT ([record](../ai/evidence/2026-09-27-phase10-result-transport.md)) |
| Kiosk renders live Teensy data on the panel, boots unattended, survives a Teensy power cycle | Panel captures in [`ai/evidence/`](../ai/evidence/) dated 2026-10-12 to 2026-10-18 |

Test vectors are built from this repository's own reading of `data_sender.h`,
so on their own they can't catch a misreading shared by encoder and decoder.
That's what the real captures are for: an em-dash decoding bug was only found
that way.

## Not built

- **Pi→Teensy control.** The wire isn't connected, and the Pi opens the port
  read-only. Control won't go through the presentation boundary
  ([presentation.h](../firmware/guitar_rig_analyzer/presentation.h)); it needs
  its own validation.

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

## Receiver state model (`state.py`)

`ReceiverState` turns packets into the Pi's belief about the instrument. Feed
it CRC-verified frames with `on_frame(frame, now_ms=...)`; it owns geometry, so
it does its own decoding. It never raises on bad input — a receiver that dies
on a malformed packet is a receiver that stops rendering.

Four rules govern it, and they exist to stop the UI filling gaps with
assumptions:

| | Rule |
|---|---|
| **UNKNOWN is a state** | Silence, HELLO, connection and session establishment are **never** mapped to IDLE. `UNKNOWN` means the Teensy has not said |
| **Sticky ABORTED** | Cleared only by an authoritative observation of `IDLE`, or by the session ending. Never by silence, reconnect, status text, or a view change |
| **Session rollover** | A changed `session_id` ends the previous session: its state is invalidated, the new session starts `UNKNOWN` |
| **No promotion pre-HELLO** | Telemetry is decoded and counted, but not promoted into instrument state, until a valid HELLO identifies the session |

**Why `VIEW(LIVE)` does not clear an abort.** `presentation_restoreLive()` is
called from two places in the firmware — after `acknowledgeAbort()`
([.ino:590](../firmware/guitar_rig_analyzer/guitar_rig_analyzer.ino#L590)) *and* after `returnToLive()` from
a RESULT view ([:600](../firmware/guitar_rig_analyzer/guitar_rig_analyzer.ino#L600)) — and `presentation.h`
documents it as a **view** transition. "Show the live view" is not "the engine
is no longer ABORTED". The protocol does not make the first imply the second,
so the model moves the view and leaves the latch alone.

**Why an `IDLE` observation does clear it.** The firmware leaves `ABORTED` only
through `measurementEngine_acknowledgeAbort() → IDLE`
([measurement_engine.h:167](../firmware/guitar_rig_analyzer/measurement_engine.h#L167)). So an authoritative
`IDLE` is evidence of acknowledgement — a Teensy-authored fact, not a Pi
decision. The rule is written against *any* packet carrying a measurement
state, not against `LIVE_FRAME`, so TODO-57's state packet plugs in unchanged.

**Local time is used for one thing only:** deciding the link has gone quiet.
`is_stale()` is a fact about the link and never alters measurement state. The
canonical measurement timebase is the Teensy's audio block counter, which
arrives as `output_block_number`.

### The STATE packet (`0x08`, TODO-57)

Every measurement state is now observable. The Teensy announces an
authoritative snapshot every `STATE_ANNOUNCE_MS` (500 ms):

```
[0]    measurement_state
[1]    abort_reason
[2-3]  reserved
[4-7]  audio_block_counter
```

It means exactly one thing: *this was the Teensy's state when the snapshot was
constructed.* Periodic rather than transition-driven, so a Pi attaching
mid-CAPTURE or during a sticky ABORTED learns the state without waiting for a
transition that may never come — and a dropped ABORTED event self-heals within
500 ms.

**Two reasons, and the difference matters.** `abort_reason_code` is the
machine-readable fact and arrives with every snapshot. `abort_reason` is the
prose from the ABORTED event and **may legitimately be `None`** — a receiver
that attached after the abort knows *why* but was never told the wording.
Render accordingly; don't treat a missing string as a missing abort.

**`audio_block_counter` is a timestamp, not a sequence number.** The firmware
derives it from `micros()`, so it **wraps to zero roughly every 71.6 minutes**
and never exceeds ~1.48e6. The model records it and implements no newer-than
comparison, because such a comparison would be wrong. Ordering is already
guaranteed by the transport, which writes whole packets in FIFO order.

### Route state (`ROUTER_STATUS` 0x05, TODO-58)

Emitted immediately on a real change and repaired every `ROUTER_REPAIR_MS`
(1 s), so a Pi attaching at an arbitrary moment converges without waiting for
anything to happen.

**Jack detection is three-valued. Never read presence on its own.**

```python
status.detect(protocol.Jack.RETURN_XLR)   # PRESENT | ABSENT | UNKNOWN
```

| `available` | `present` | meaning |
|---|---|---|
| 0 | — | **UNKNOWN** — no detector exists; the presence bit is not evidence |
| 1 | 0 | ABSENT |
| 1 | 1 | PRESENT |

A Boolean cannot carry *"we have no detector"*, which is why the packet has two
masks. **All four detectors are unavailable on the current hardware**, so
`UNKNOWN` is the expected answer today, not an error — three are unbuilt and
the instrument jack is a two-terminal part with no switch terminal at all.

**`return_source` is the only authority on the selected return.** It is
operator-selected (ADR-004). Never infer it from presence: *"XLR plug detected
therefore XLR is active"* is forbidden by ADR-004 Decision 3, and today it
would be inferred from a pullup artefact. An XLR plug present while TS is
selected is a legitimate state to render.

**`route_valid` and `can_inject` are not on the wire and must not be
reconstructed.** The first was a tautology recomputable from `return_source`;
the second depended on an unavailable detector, so its honest value was
UNKNOWN.

Before the first `ROUTER_STATUS`, and after a session change, `router` is
`None` — render route as unknown. **Do not assume TS** even though ADR-004
makes it the boot default: the operator may have selected XLR long before the
Pi attached.

## Still true: RESULT cannot be decoded before HELLO

`fft_bins` has no other carrier, and the `insight_count` that would let you
solve for the array length sits *after* the arrays. `decode_result()` raises
`GeometryUnknown` rather than guessing. With the re-announcement in place the
wait is now bounded by about a second instead of by a Teensy reboot.

---

# `pi/web/` — the web renderer (TODO-67)

`python3 -m web.server --fixture <capture>` serves a classified frame at
`/api/frame` and the client at `/`. See
[ADR-005](../docs/adr/ADR-005-pi-rendering-stack-and-presentation-semantics.md).

**The browser is given nothing to reinterpret.** `/api/frame` carries bands that
`presentation_semantics` has already classified — no coverage nibbles, no raw TF
array, no non-finite value. `value` is present only when a band is MEASURED. The
client performs no DSP, no measurement and no grading, and `getUserMedia` is
prohibited and CI-enforced (`tests/test_web_payload.py`).

## Vendored dependency

`web/static/vendor/three.module.js` is committed rather than fetched.

| | |
|---|---|
| Package | `three` |
| Version | **0.169.0** |
| Source | `npm pack three@0.169.0`, from the `build/three.module.js` of that tarball |
| Upstream | https://threejs.org/ · https://github.com/mrdoob/three.js |
| License | MIT — full text in [`web/static/vendor/three.LICENSE`](web/static/vendor/three.LICENSE) |
| Size | ~1.3 MB |

**Why it is in git.** The instrument must render with no internet, no CDN, no npm
and no deploy-time download — it is a panel on a pedalboard, not a web app. Pinning
the file also freezes the exact version the visualization was tested against, so a
rendering change can never arrive from an upstream release nobody chose.

Updating it means replacing the file, re-running the suite, and re-capturing the
evidence screenshots, because the pinned renders are version-specific.
