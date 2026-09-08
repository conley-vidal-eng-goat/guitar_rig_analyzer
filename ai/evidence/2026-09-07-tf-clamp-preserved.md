# Evidence: TF diagnostic pinned at the −24.0 dB clamp rail (PRE-FIX behaviour)

Captured 2026-09-07 from `/dev/cu.usbmodem195969201` @ 115200, firmware as of commit `e6daac8`
(no local modifications). Bench in the verified post-Phase-4 baseline: short I²S leads,
LINE-IN-L jumper in row 48, headphone jack unplugged, 1 kHz tone at 0.143 V<sub>rms</sub>.

**Purpose:** record the defective behaviour before changing it, so the fix has a
before/after trail. This file is the "before".

## What the diagnostic printed

33 consecutive 5 s windows, uptime 390–550 s:

| Uptime | SOURCE peak | RETURN peak | true gap | 120 Hz | 500 Hz | **1 kHz** | 5 kHz |
|---|---|---|---|---|---|---|---|
| 390 | −9.0 | −56.0 | 47.0 | −24.0 | −23.4 | **−24.0** | --- |
| 395 | −9.1 | −55.8 | 46.7 | −23.4 | −24.0 | **−24.0** | --- |
| 400 | −9.0 | −56.3 | 47.3 | −22.3 | −24.0 | **−24.0** | −23.5 |
| 405 | −9.0 | −56.0 | 47.0 | −22.4 | −23.8 | **−24.0** | −23.2 |
| 410 | −9.0 | −56.2 | 47.2 | −22.2 | −23.7 | **−24.0** | --- |
| 415 | −9.0 | −56.5 | 47.5 | −23.5 | −24.0 | **−24.0** | --- |
| 420 | −8.9 | −55.8 | 46.9 | −23.1 | −24.0 | **−24.0** | --- |
| 425 | −9.1 | −56.7 | 47.6 | −23.0 | −23.8 | **−24.0** | --- |
| 430 | −9.1 | −56.3 | 47.2 | −23.2 | −23.9 | **−24.0** | --- |
| 435 | −9.2 | −56.5 | 47.3 | −23.7 | −24.0 | **−24.0** | --- |
| 440 | −8.8 | −56.2 | 47.4 | −23.1 | −23.9 | **−24.0** | −23.9 |
| 445 | −9.0 | −56.9 | 47.9 | −21.8 | −23.7 | **−24.0** | --- |
| 450 | −9.0 | −55.3 | 46.3 | −23.6 | −23.9 | **−24.0** | --- |
| 455 | −9.1 | −56.7 | 47.6 | −22.0 | −23.8 | **−24.0** | --- |
| 460 | −9.0 | −56.3 | 47.3 | −23.8 | −24.0 | **−24.0** | --- |
| 465 | −8.9 | −55.8 | 46.9 | −21.7 | −23.8 | **−24.0** | --- |
| 470 | −9.1 | −56.7 | 47.6 | −22.9 | −23.9 | **−24.0** | --- |
| 475 | −9.0 | −55.8 | 46.8 | −22.5 | −23.9 | **−24.0** | --- |
| 480 | −9.2 | −56.7 | 47.5 | −24.0 | −23.8 | **−24.0** | --- |
| 485 | −9.3 | −56.2 | 46.9 | −21.3 | −23.3 | **−24.0** | --- |
| 490 | −9.2 | −56.9 | 47.7 | −21.1 | −23.8 | **−24.0** | --- |
| 495 | −9.1 | −56.5 | 47.4 | −23.4 | −24.0 | **−24.0** | --- |
| 500 | −9.3 | −56.0 | 46.7 | −22.9 | −24.0 | **−24.0** | --- |
| 505 | −9.0 | −56.3 | 47.3 | −22.4 | −23.9 | **−24.0** | --- |
| 510 | −9.0 | −56.5 | 47.5 | −22.9 | −23.9 | **−24.0** | --- |
| 515 | −9.3 | −56.5 | 47.2 | −23.1 | −23.3 | **−24.0** | −23.1 |
| 520 | −9.4 | −57.1 | 47.7 | −22.1 | −23.7 | **−24.0** | −23.1 |
| 525 | −9.1 | −56.2 | 47.1 | −23.0 | −23.8 | **−24.0** | --- |
| 530 | −9.2 | −57.2 | 48.0 | −23.0 | −24.0 | **−24.0** | −22.7 |
| 535 | −9.0 | −56.3 | 47.3 | −22.6 | −23.9 | **−24.0** | −23.8 |
| 540 | −8.9 | −56.3 | 47.4 | −21.7 | −23.7 | **−24.0** | −22.6 |
| 545 | −9.2 | −56.5 | 47.3 | −23.5 | −24.0 | **−24.0** | −23.2 |
| 550 | −9.2 | −56.3 | 47.1 | −23.7 | −24.0 | **−24.0** | −23.1 |

All values in dB / dBFS. "true gap" = SOURCE peak − RETURN peak.

## Why this is a defect and not a measurement

- **1 kHz reads exactly −24.0 dB in 33 of 33 windows.** That is
  `TF_DB_MIN - 6.0f` = `-18.0f - 6.0f` — the lower rail of the `constrain()` at
  [audio_engine.cpp:283](../../audio_engine.cpp#L283), with `TF_DB_MIN` at
  [config.h:391](../../config.h#L391). It is the clamp, not the signal.
- **The true transfer function is ≈ −47 dB**, 23 dB below the rail. Nothing is connected
  to RETURN_NODE; what it sees is channel crosstalk. There is no rig in the loop, so the
  correct answer is "out of range", and the correct display is *not* a number.
- **500 Hz and 120 Hz are partially railed.** They read −23.3 to −24.0, which is the EMA
  converging onto the rail from bins whose raw value is also below it. The variation makes
  them look like live measurements; they are not.
- **5 kHz alternates between `---` and ≈−23 dB.** The `---` is the honest output
  (`TF_SOURCE_GATE` rejected the bin → NAN). The ≈−23 dB is the railed one. The same
  diagnostic therefore prints both an honest and a dishonest representation of the same
  condition, seconds apart, with no way to tell them apart.
- **`persistence: ACTIVE` is lit in every window** and stays lit, because railed bins keep
  feeding the EMA history.

## Scope of the defect

Confined to the live frame (`AudioFrame.tf_db[]`), the display curve, and this serial
diagnostic. **`validation.cpp` is NOT affected** — it computes TF from raw FFT means with
the EMA bypassed ([validation.cpp:47](../../validation.cpp#L47)), so the 40 dB gate gap is
measured on unclamped data.

Fix tracked as TODO-29. See journal.md 2026-09-07 (7) and (8).
