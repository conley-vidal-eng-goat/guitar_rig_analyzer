# Web renderer slice 1 — real Teensy bytes reach ToneFingerprintSplit

**2026-09-30.** TODO-67's first vertical slice. The committed Split Tone
Fingerprint renders from recorded hardware captures through the shared
presentation-semantics contract (ADR-005 §4/§6, TODO-68).

**No firmware change. No protocol change. No bench action. No measurement
initiated.** Both inputs are pinned captures already in this repository.

> **🛑 THIS IS NOT T1 EVIDENCE, AND NOT PI EVIDENCE.** Rendered by headless
> Chrome on macOS with SwiftShader. **No browser has run on the Pi.** T1 remains
> open behind TODO-39; TODO-36's "development decision, NOT an acceptance waiver"
> is unchanged by anything here.

## Path

```
fixture bytes -> analyzer_link (CRC, framing, decode)
             -> presentation_semantics.classify_result / classify_live
             -> presentation_semantics.resample  (log-f, 20 Hz..20 kHz, 48 bands)
             -> web.payload                       (JSON; value ONLY if MEASURED)
             -> web.server  GET /api/frame        (stdlib HTTP, loopback, 500 ms poll)
========================= browser boundary =========================
             -> static/main.js -> fingerprint_split.js -> WebGL @ 720x1280
```

## Artifacts

| File | SHA-256 |
|---|---|
| `phase10-result-1khz.bin` | `e8b57d6f62af1367b654dd6d13270a94d73f06868ac785edf353f20179dd14a1` |
| `phase10-teensy-pi-idle-30s.bin` | `e26646cbb8df1714ae721ac45e33ad1f25486bf3af31eb9b36079e5c56ddb488` |
| `2026-09-30-web-fingerprint-split-result.png` | `b85e717898ce4c85e356c6363a5e9233803cb15e2f1c138d9f7f7e479254c3ec` |
| `2026-09-30-web-fingerprint-split-idle.png` | `c8ce28aa0fdb0b2d3bc85acedded4cf04c00f551dac8e2d06b8ce695a626e42a` |

The RESULT fixture's hash is the one already asserted by
`pi/tests/test_result_fixture.py`; it is unmodified.

## RESULT — [`…-result.png`](2026-09-30-web-fingerprint-split-result.png)

**512-bin source census** (`tf_cal_mag_db`, from `classify_result`):

```
512 bins · 0 measured · 4 indeterminate · 508 unmeasured
drawable as measurement: 0 of 512
```

The four are indices **22–25**, contiguous, and all read exactly **−24.0 dB** —
the firmware's clamp rail. They are INDETERMINATE because **RESULT carries no
per-bin clamp mask (TODO-65)**, not because of what they read. Had they read
−11.3 dB they would be INDETERMINATE too; `test_indeterminate_is_never_inferred_from_the_value`
pins that.

**48-band presentation census** (after log-frequency reduction):

```
48 bins · 0 measured · 2 indeterminate · 46 unmeasured
```

| source bin | Hz | band | band span |
|---|---|---|---|
| 22 | 947.46 | **26** | 843.4 – 973.9 Hz |
| 23 | 990.53 | **27** | 973.9 – 1124.7 Hz |
| 24 | 1033.59 | **27** | " |
| 25 | 1076.66 | **27** | " |

**Two bands, not one, and the split is fragile.** The 26/27 boundary is
**973.94 Hz** — 25.5 Hz above bin 22 and 17.5 Hz below bin 23. A change to the
ring's `F_LO`, `F_HI` or band count would move that boundary across these bins and
silently relabel what this screenshot shows. Pinned by
`test_each_of_the_four_source_bins_pins_to_an_exact_band`.

**On screen:** the baseline ring, the divider, and **exactly two amber markers** at
the band-26 and band-27 positions. **No bars.** 46 of 48 bands draw nothing at all.
HUD: `quality POOR · 32 averages · coherence 0.799 · NOT calibrated` — all
Teensy-authored, printed verbatim.

## Idle — [`…-idle.png`](2026-09-30-web-fingerprint-split-idle.png)

```
source 128 bins · 0 measured · 128 unmeasured   ->   ring 48 bins · 0 measured · 48 unmeasured
```

Every one of the 128 live bins is pen-lift (`valid == 0`). **The ring is completely
empty.** HUD: `state IDLE · src −63.9 dBFS · ret −66.2 dBFS · confidence 0%`.

A renderer willing to fabricate would have drawn something here. The same property
was recorded for the Tk renderer on 2026-09-30; it now holds for the web renderer
on the same bytes.

## The browser is given nothing to reinterpret

Classification happens entirely on the Pi side. `/api/frame` carries **classified
bands only** — no coverage nibbles, no raw TF array, no non-finite value. `value`
is present **only** when a band is MEASURED; every other class carries `null`.
`−24.0` appears nowhere in the payload.

```
audio/measurement APIs in client code    NONE
network calls from the client            1  — fetch("/api/frame")
three.js AudioListener/PositionalAudio   present in the library, NOT REFERENCED
payload is strict JSON (allow_nan=False) yes — absence can never arrive as NaN
```

`getUserMedia` is prohibited and CI-enforced against eight identifiers, with
comments stripped so a mention in prose cannot mask a call. `VortexTunnel.jsx` is
excluded from production for this reason (ADR-005 §9).

## 🔺 What this does NOT show

**The MEASURED bar path has never been rendered.** Both fixtures classify to zero
MEASURED bands, so bar heights, side assignment (`db<0` left/below, `db>0`
right/above), the cyan and orange ramps, coverage-driven thickness and frame easing
have unit tests and **no visual confirmation whatsoever**.

**This is deliberately not closed with synthetic data.** A generated high-coverage
frame would produce a convincing screenshot of a measurement that never happened —
the precise failure the contract exists to prevent — and a screenshot in
`ai/evidence/` outlives whatever caveat was attached to it. The debt stays open
until the instrument produces a genuine measurement with established coverage.

Also unproven: Chromium and WebGL **on the Pi 5's GPU** (SwiftShader on macOS says
nothing about it), the `--serial /dev/ttyAMA0` path (implemented, shares the
transport, never run), and kiosk autostart (not written).
