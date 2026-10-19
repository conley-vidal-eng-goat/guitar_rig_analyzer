# The return is restored, and TONE draws a level-matched return on the panel for the first time

**2026-10-18.** TODO-93 closed. Production kiosk (`~/gra-ui`, `afd1944`), real
UART, Stratocaster strummed through J4 → J5 → rig → J6 → J8.

![TONE with a working return](2026-10-18-pi-tone-return-restored.png)

`2026-10-18-pi-tone-return-restored.png` (`f62ee5f8…`) is a `grim` capture of
the panel. `…-frame.json` (`6bb776e6…`) is the `/api/frame` response from the
same instant, taken by a separate request (link live, session 56, 0 decode
errors).

## What fixed it (operator's account, `RPT`)

The operator resoldered the shield's LINE IN R joint and fitted a new jumper.
The jumper's breadboard end first went into **GND instead of column 16**, which
tied LINE IN R to ground (return −53..−67 dBFS, nothing tracking). Moving it to
**`16a` (K2 COM, column 16)** restored the return. Which of the joint or the
original jumper was the first fault is **not separable** from what was observed.

## The numbers

15 s monitor while strumming (52 frames, link live throughout):

| | |
|---|---|
| Source peak | −49.4 .. −6.1 dBFS |
| Return peak | −35.0 .. **0.0** dBFS, **return_clip set in 2 frames** |
| Sections above floor | input ≤ 8, **return ≤ 10**, rig-only ≤ 3 |
| Rig gain | +4.2 .. +7.1 dB (median +5.6) |

A burst a few minutes later read **+2.6 .. +4.5 dB with no clipping**, and the
screenshot shows **+2.8 dB**. Whether the rig level was changed in between is
not recorded.

Per bin in the saved frame (source / return as received / return matched):

| bin | Hz | src | ret | matched |
|---|---|---|---|---|
| 1 | 237 | −21.6 | −18.0 | −20.9 |
| 2 | 409 | −31.1 | −27.4 | −30.3 |
| 3 | 581 | −30.0 | −29.3 | −32.3 |
| 5 | 926 | −45.2 | −40.6 | −43.5 |
| 7 | 1270 | −52.5 | −46.4 | −49.3 |

Bin 1 is louder than FULL_DB (−24 dB), so it is drawn full length with the ▲ cap, as designed.

## What this establishes, and what it does not

- ✅ **The level-matched return path works on real signal, on the panel.** The
  gain number, matched cool bars and white rig-only seats all appear. This
  closes the caveat in `2026-10-16-pi-tone-input-over-return.md`.
- ✅ The instrument localised a wiring fault: the return input measured
  nothing while J8 was audible, and the touch test came back flat.
- ⚠️ **The 2 clipped return frames are not valid measurements**, and TONE does
  not yet show the clip flags (TODO-95). Rig-only seats in clipped frames may be
  clipping distortion rather than rig noise.
- ❌ **The right headphone channel is still silent** while the return is
  demonstrably present in the data (TODO-94). Ear tests on the right channel
  were therefore never a valid return check.
- ❌ No accuracy claim: uncalibrated, dB re FFT 1.0, decimated-max spectra.
