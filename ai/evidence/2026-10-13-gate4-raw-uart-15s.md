# Raw UART capture with no renderer attached — the independent reference for Gate 4

**2026-10-13, 20:57:48–20:58:03 PDT (03:57:48Z). Repository `6161b5b`.
`OBS`.**

The first raw capture taken on this instrument **with nothing else holding the
port**. Every previous one was taken in a session where the Tk UI had just been
stopped for the purpose; this one sits between a verified handoff (journal
2026-10-13 (8)) and a web transport that has never opened the device.

**No firmware change, no wiring change, no autostart change. Tk was not running,
the web server was not running, Chromium was not running.** The capture is raw
bytes only — `capture.sh` performs no decoding during acquisition, deliberately.

## Artefact

```
ai/evidence/2026-10-13-gate4-raw-uart-15s.bin
547 219 bytes
sha256  e90f74a457b09f91490769316be5873c3f34bc9a4cdf2dd20ab15e3a401f580a
```

Captured on the Pi at `/tmp/gate4-raw-205748.bin`, transferred to the Mac, and
**the sha256 verified on both machines.** `replay.py` was then run on the
transferred copy and reproduced the Pi's output line for line — a second machine,
a second decoder run, the same bytes.

## Acquisition

```
device  : /dev/ttyAMA0 -> /dev/ttyAMA0          (NOT /dev/serial0, which is ttyAMA10)
config  : 460800 8N1 raw, no flow control, min 1 time 0
elapsed : 15s of 15s requested
bytes   : 547219
rate    : 36481 B/s
```

**No `sudo`.** `conley` is in `dialout`; the `sudo` in the older procedure is
unnecessary on this machine.

**The rate is the headline.** 36 481 B/s against **36 465 B/s** measured on this
hardware 2026-09-26, and against the **36 483 B/s** constant `sources.py` has
carried since. Agreement to about 0.05 % across eighteen days, two sessions and
a firmware the board has restarted into since.

`capture.sh` passed its own duration check — 15 s elapsed of 15 s requested. That
check exists because a 2026-09-26 defect produced a plausible-looking failure
report from a capture that had run for about one second.

## Decode — `pi/tools/replay.py`, offline, after the fact

```
packets decoded
  LiveFrame            301        StatePacket           30
  RouterStatus          15        Hello                 15

framing
  frames ok        382
  CRC failures     0
  oversize rejects 0
  bytes discarded  1532  (leading 1532, interior 0 in 0 event(s))
  buffered at end  119

receiver state
  session_established   True        hello_session_ids   [47]
  firmware_version      0.6.0       measurement_state   IDLE
  geometry              live_bins 128 · fft_bins 512 · decim 4 · 44100 Hz
  decode_errors         0
  geometry_unavailable  21          not_promoted_pre_hello  3

router status
  return_source TS · injection_active False · monitor SOURCE_RETURN
  detectors: all unknown — no detect hardware fitted

TRANSPORT: OK
```

**Rates.** 301 LiveFrames over 15 s is 20.1/s placed; some of the 21
`geometry_unavailable` frames are live frames that arrived before the first
HELLO and so could not be located, which brings the actual live-frame rate to
≈21/s — consistent with the ~21.5/s the design assumes. HELLO at 15 in 15 s is
exactly the documented 1 Hz re-announcement.

**`session 47`** — the same session the Tk UI reported immediately before it was
stopped. **The Teensy did not restart across the handoff.**

## What this establishes

**The link is structurally healthy right now.** Zero CRC failures, zero oversize
rejects, **zero interior discards in zero events**, no decode errors, at the
nominal byte rate, in a 15-second window with no reader competing for the port.

**1 532 leading discarded bytes is attach loss, not corruption** — the scanner
discarding the tail of the frame it landed inside when the capture began. It is
≈0.9 of one frame, which is what landing uniformly inside a ≈1 700 B frame
produces.

🔺 **A non-zero leading discard is expected but not required, and the acceptance
criterion does not depend on it.** Opening the port near a frame boundary could
legitimately yield zero. The criterion is **no unexplained CRC failures and no
interior discards** — correction supplied in review, and recorded because the
earlier prediction (journal 2026-10-13 (8)) stated the non-zero case too
strongly. It happened to hold here; it was still an overclaim as written.

**This is the reference the web transport must be compared against.** A
continuous blocking reader absorbs the full 36 481 B/s. Whether a reader that
pumps only when an HTTP request arrives — every 500 ms — absorbs the same is the
open question Gate 4 §5 exists to answer, and now there is a same-evening,
same-session number to compare it with rather than an eighteen-day-old one.

## What this does NOT establish

**It is not independent verification of the protocol's field semantics.**
`replay.py` and the firmware still share one author's reading of
`data_sender.h`. What a raw capture independently establishes is **structural**:
byte rate, framing, CRC integrity, and the absence of mid-stream corruption.
Those do not depend on anyone's interpretation of a field. The semantic loop has
been broken twice before by hardware streams — most sharply by the UTF-8 em dash
the synthesised vectors could never have contained — and nothing here adds a
third.

**It is not a measurement.** `peak_source −51.1 dBFS`, `peak_return −52.1 dBFS`,
`tf_confidence 0.0` are reported by `replay.py` under a heading that says
*"analog observations (NOT part of the verdict)"*, and that heading is correct.
The instrument is `IDLE`, nothing was played, no capture was armed, and the
SOURCE/RETURN gap here is two uncalibrated input readings — **not an insertion
loss**. TODO-78's re-baseline remains outstanding, and the Instrument In short
repaired earlier this evening (journal 2026-10-13 (5), `RPT`) means the level
history is not comparable across the repair anyway.

**It says nothing about the 20:05 event.** It is a clean 15-second window taken
50 minutes afterwards, consistent with the 49 745 frames Tk accumulated with no
further loss, and consistent with a single past event. It does not identify one.

**It does not advance TODO-34 or TODO-35.** Both already record the receive and
RESULT transports as proven on hardware (2026-09-26 / 2026-09-27). This is a
re-confirmation at the current firmware and session, not a new acceptance.
