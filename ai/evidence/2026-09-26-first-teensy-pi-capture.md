# First real Teensy → Raspberry Pi 5 transport capture

**2026-09-26** (Las Vegas evening; capture timestamps are UTC 2026-09-27).
First time any receiver has seen a byte emitted by this firmware.

## Artifact

| | |
|---|---|
| File | `first-real-teensy-pi-5s.bin` |
| **Location** | **On the Pi**, `~/guitar_rig_analyzer/first-real-teensy-pi-5s.bin` — *not yet transferred into this repository* |
| Bytes | 182 327 |
| **SHA-256** | `c1a37dd136dd0441c0be72609312f75828d57a1a045596bc9d6d3a306bf011b8` |
| Window | 2026-09-27T03:57:33Z → 03:57:38Z (5 s) |
| Device | `/dev/ttyAMA0` |
| Rate | **36 465.4 B/s ≈ 36.47 KB/s** |

Transfer it into `ai/evidence/` when convenient; `.gitignore` does not exclude
`*.bin`, so it is committable at 182 KB. Until then this record is the evidence.

## Link as built — receive-only by design

| Teensy | → | Pi |
|---|---|---|
| pin 1 / TX1 | → | GPIO15 / RXD0, **physical pin 10** |
| GND | → | **physical pin 9** |
| pin 0 / RX1 | — | **unconnected** |
| — | — | GPIO14 / TXD0 **unconnected** |

No 3.3 V or 5 V rail shared; ground is the only power-domain connection. The
link is physically incapable of Pi→Teensy traffic, which is what makes this
capture independent of serial-console configuration.

**Pi:** Raspberry Pi 5 · Touch Display 2 · Active Cooler · Raspberry Pi OS
64-bit (Debian Trixie) · kernel `6.18.50+rpt-rpi-2712` · host
`guitar-rig-analyzer`. `raspi-config`: serial login shell NO, serial hardware
YES. `console=serial0` removed from cmdline; `dtparam=uart0=on`.

**Teensy:** `dcfbffa` `_PI` artifact, v0.6.0, protocol v2. **No firmware change
was made during this work.**

## 🛑 The device finding — `/dev/serial0` was the wrong peripheral

```
serial0  -> /axi/pcie@1000120000/rp1/serial@30000   -> ttyAMA10
serial10 -> /soc@107c000000/serial@7d001000         -> ttyAMA0
```

With GPIO14/15 as TXD0/RXD0, **`/dev/serial0` → `ttyAMA10` received nothing**;
the header UART was **`/dev/ttyAMA0`**.

**The symptom pointed at the wiring, and the wiring was fine.** `MEAS`:
continuity Teensy pin 1 → Pi-end connector **PASS**; Teensy GND → Pi ground
**PASS**. A **RIGOL DHO804** showed an active 0–3.3 V UART waveform at Teensy
pin 1 **and the same activity at Pi GPIO15 / physical pin 10**. The bytes were
physically arriving while Linux read a different peripheral.

**Lesson, now in the runbook and in `capture.sh`'s zero-byte path: when a
capture is empty, check the device before the wire.**

## 🔧 Tooling defect — `capture.sh` reported a failure it never performed

First attempt:

```
sudo sh pi/tools/capture.sh /dev/serial0 30 cap.bin
  start  : 2026-09-27T03:41:07Z
  end    : 2026-09-27T03:41:08Z
  bytes  : 0
  sha256 : e3b0c442...b855      (the SHA-256 of an empty file)
```

**A 30-second capture that exited after ~1 second**, and reported zero bytes as
though the run had completed. `bash -x` found it: `stty ... min 0 time 1` lets a
no-data read return immediately, so `cat` exits before the outer `timeout`.

This was correctly **not** accepted as proof of a dead link. Had it been, the
session would have gone hunting a wiring fault that did not exist — and the
scope later proved the waveform was arriving.

**Fixed:** `min 1 time 0`, so the read blocks and the outer `timeout` controls
duration. The script now also **verifies elapsed time against the request and
exits non-zero if short**, because a capture that never ran must not be
presented as a link result. Five regression tests guard both defects.

## Replay result — `TRANSPORT: OK`

`python3 pi/tools/replay.py first-real-teensy-pi-5s.bin --seconds 5`

| | |
|---|---|
| frames ok | **127** |
| CRC failures | **0** |
| oversize rejects | **0** |
| decode errors | **0** |
| bytes discarded | 1 034 (mid-stream partial frame) |
| buffered at end | 0 |

| Packet | Decoded | Rate |
|---|---:|---:|
| LiveFrame | 93 | 18.6/s |
| StatePacket | 10 | 2.0/s |
| RouterStatus | 5 | 1.0/s |
| Hello | 5 | 1.0/s |

**Receiver state:** session established, `hello_session_ids [4]`, firmware
`0.6.0`, geometry `{live_bins 128, fft_bins 512, decim_ratio 4, sample_rate
44100}`, `measurement_state IDLE`, `abort_latched False`, `abort_reason_code
NONE`, view `live`, `geometry_unavailable 14`, `not_promoted_pre_hello 3`.

**Router status:** `return_source TS` · all four detectors **`unknown`** ·
`any_detector_available False` · `injection_active False` · `monitor_mode
SOURCE_RETURN` · `"TS return, no injection"`.

## ✅ Every byte accounted for

The strongest result here is not `TRANSPORT: OK` — it is that the capture
reconciles to the byte:

```
LIVE    107 x 1689 = 180 723     (93 promoted + 14 pre-HELLO)
STATE    10 x   15 =     150
HELLO     5 x   47 =     235
ROUTER    5 x   37 =     185     (7 + 23-char description + 7 framing)
                   ---------
                     181 293
discarded            +  1 034     (mid-stream partial frame)
                   ---------
                     182 327  =  captured 182 327     residual 0
```

`frames_ok 127` = 113 decoded + 14 geometry-blocked. **No unexplained gaps, no
malformed packets, nothing unaccounted for.**

**The 18.6/s live rate is not a producer slowdown.** Including the 14 pre-HELLO
frames the receiver counted but refused to promote: **107 / 5 s = 21.4/s**,
against the 21.6/s measured at the producer on the same firmware. The aggregate
byte rate — 36 465 B/s against a 36 500 B/s prediction — confirms it
independently.

## Session id

Producer test 2026-09-26: session **0**. This capture: session **4**. `INFER`:
consistent with the EEPROM counter advancing across intervening `_PI` boots.
**The exact reboot sequence was not observed and is not claimed.** What is
established is that the counter is **not stuck**, and that a value other than
the first-boot `0` reaches the receiver intact.

## What this proves

1. Real Teensy v0.6.0 protocol-v2 bytes left `Serial1`.
2. They traversed the physical Teensy→Pi UART wiring.
3. A Pi 5 received them on GPIO15/UART0 via `/dev/ttyAMA0`.
4. The Pi framing/parser decoded **real hardware bytes** — 127 frames, zero
   errors of any class.
5. Periodic HELLO **repaired a mid-stream attach** and established session 4.
   This is TODO-56 working on hardware for the first time.
6. STATE recovered authoritative `IDLE` with no abort — TODO-57 on hardware.
7. ROUTER_STATUS recovered route and **all four detectors as UNKNOWN** —
   TODO-58's honest-ignorance contract, on hardware.
8. Pre-HELLO telemetry was counted and **not promoted**, exactly as designed.
9. Measured 36.47 KB/s against a ~36.5 KB/s prediction.

**The shared-author evidence loop is broken.** The parser is no longer only
agreeing with its author's reading of `data_sender.h`; it has decoded bytes the
compiled firmware actually produced.

## What this does NOT prove

- **RESULT transport on hardware** — no RESULT was emitted or received.
- **TODO-59 atomicity at runtime** — nothing staged a RESULT, so the invariant
  had nothing to refuse.
- **Pi→Teensy command path** — physically disconnected.
- Touch-command handling; **no production UI exists**.
- Reconnect / reboot / session-change acceptance matrix.
- **CRC-invalid rejection on hardware** — only a clean stream was observed.
- **Unknown packet-type tolerance on hardware** — none appeared.
- The T1 acceptance matrix, or Phase 10 overall.
- Any analog transfer-function correctness.

**Analog observations, NOT transport evidence:** `peak_source −65.2 dBFS`,
`peak_return −66.8 dBFS`, `tf_confidence 0.0`, `tf_clamped_count 0`, no clipping.
Consistent with an idle instrument and nothing plugged in.

## Not done

No Phase 9 validation was invoked — no `v`, no Tests 1–4. No generator, no
injection, no relay operation, no measurement armed, no return-source change, no
analog breadboard change. **Phase 9 status is unaffected by this work.**
