# The four-tab shell on the Pi — all four screens, 60 fps, and the pause proven

**2026-10-13, 00:35–00:52 PDT.** The navigation shell and the TODO-80 fix
(`cc7b704`) running on the physical Pi 5 and Touch Display 2.

**No firmware change. No protocol change. No wiring change. No measurement
initiated.** Code was staged in `~/gra-webtest`, never the Pi's repository
checkout. The Tk UI ran undisturbed on **pid 1514** throughout — the same pid as
before, during and after — and both autostart files are byte-unchanged.

> **🛑 EVERY FRAME HERE IS A RECORDED FIXTURE.** `phase10-result-1khz.bin`,
> replayed from disk. The Teensy was not measuring and the serial path was not
> used. This is not T1 evidence, not live-measurement evidence, and does not
> close the MEASURED bar debt.

---

## Test suite on the Pi

```
396 tests ... OK (skipped=5)      26.1 s
```

25 of those are new (`test_web_shell.py`). The five skips are
`'timeout fixture not present'` — a fixture not synced to the scratch tree.

## The four screens

Captured with `grim` on the live compositor at 720×1280. **These are the panel,
not renders of it.**

| Screen | | What it shows |
|---|---|---|
| LIVE | [`…-live.png`](2026-10-13-pi-shell-live.png) | *"No live frame"* — the transport is carrying a RESULT, which has no peak levels, state or confidence. Plus the **Pending** card stating why no spectrum is drawn |
| TONE | [`…-tone.png`](2026-10-13-pi-shell-tone.png) | The fingerprint, unchanged: ring, divider, **exactly two amber markers, no bars**, census and legend |
| LAB | [`…-lab.png`](2026-10-13-pi-shell-lab.png) | `valid yes · POOR · 32 averages · coherence 0.799 · NOT calibrated · firmware 0.6.0`, both censuses, and the eight fields the transport does not forward yet |
| INFO | [`…-info.png`](2026-10-13-pi-shell-info.png) | `session 7 · STALE · 306 frames · 0 decode errors`, frame geometry, and a plain statement that this is a display and not a control surface |

Every value on those screens is Teensy-authored and printed verbatim. Every
absent one is rendered as a worded reason in amber italics — **no dashes, no
zeros, no blanks.**

`LINK STALE` is correct: the fixture replay had ended.

## Performance

[`…-60fps.png`](2026-10-13-pi-shell-60fps.png)

```
TONE, full shell, 15 s:   60 fps (min 51)
```

Better than the pre-shell measurement (60, min 45) on 2026-10-12 — consistent
with the camera no longer being fitted to a viewport that never existed, though
**that is an observation, not an attribution**; I did not isolate the cause.

### The inactive-view pause is real, and measured

Chromium's total CPU across all its processes, sampled from `/proc/<pid>/stat`
over 15 s with the page already settled:

| Visible tab | CPU |
|---|---|
| **TONE** (fingerprint orbiting) | **30.4 %** of one core |
| **LAB** (fingerprint paused) | **9.4 %** of one core |

🔺 **Both figures are inflated by the measurement itself.** The FPS probe is a
scratch-only 60 Hz `requestAnimationFrame` loop that runs on every tab and does
not exist in the committed client, so the real LAB cost is **lower than 9.4 %**.
The honest reading is the **difference**: roughly **21 points of CPU released**
when the fingerprint is not the visible tab. The pause cancels the frame request
rather than returning early inside it, which is what makes that recoverable at
all.

## TODO-80 — fixed, and confirmed on the panel

The ring is now fitted to the live viewport. Camera aspect and orbit distance are
recomputed on construction, from a `ResizeObserver`, from `window.resize`, and
again each time TONE is shown after being hidden. A zero-sized container is
refused rather than used, because a `display:none` container measures 0 × 0 and
fitting to that bakes a NaN into the camera matrix.

🔺 **A design observation, not a defect.** Fitting the ring to the *narrow* axis
is what the committed design specifies, and on a 720 × 1280 portrait panel that
leaves the ring about 580 × 250 px inside a 720 × 1105 area — a lot of unused
vertical space. The visualisation is behaving exactly as specified; whether that
specification is the best use of a portrait panel is a separate tuning question
(camera pitch, or putting a readout in the space). **Not changed here**, because
preserving the committed appearance was the instruction.

## 🔺 Second defect found, and it was the more serious one

**With WebGL unavailable, the entire interface went blank** — not just TONE.

three.js throws when it cannot create a context. The scene was being constructed
eagerly during view creation, so the throw propagated out of `main.js` before it
ever ran, and **LIVE, LAB and INFO rendered nothing although none of them needs a
GPU.** Found on macOS with `--disable-gpu`, which is how the first headless DOM
check came back empty.

That is backwards: the measurement readouts are precisely the part that must
survive a graphics failure, and the design brief asks for an interface that is
still good with the 3D disabled. The scene is now built lazily on first
activation inside a guard; a failure is contained to TONE, which says so and
states that the instrument is unaffected.

**Verified on macOS with `--disable-gpu`:** the shell renders, the status strip
populates from the pinned RESULT, no fabricated zeros.
`test_a_webgl_failure_cannot_take_down_the_other_views` pins it.

## ⚠️ Touch: STILL NOT TESTED

**Nobody has touched the panel.** The capability is confirmed —
`11-005d Goodix Capacitive TouchScreen` on i2c, 10 touch points, `PointerEvent`
supported — but **no finger has tapped a tab**, because the entire session ran
over SSH and no input-synthesis tool (`wtype`, `ydotool`, `xdotool`) is installed.

The four screenshots above were taken by overriding the default tab in the
**scratch copy** of `main.js` and relaunching — `let active = "<tab>"` — which was
restored afterwards. The Pi's copy now hashes identically to the repository's
(`b1de238b…`), as does `fingerprint_split.js` (`5b2cf5cf…`).

**So this proves every screen renders. It does not prove a tap switches them.**
That needs one person and one finger, and it is the next validation step.

---

## State of the Pi afterwards

| | |
|---|---|
| Chromium / UI server processes | none |
| Tk UI | running, **pid 1514 — unchanged throughout** |
| `/etc/xdg/labwc/autostart` | `3a53212a…` — unchanged |
| `~/.config/labwc/autostart` | mtime 2026-09-30 00:30:46 — untouched |
| Pi's repository checkout | untouched |
| `~/gra-webtest` | scratch tree; `main.js` and `fingerprint_split.js` hash-identical to the repo |
| Chromium profiles | ephemeral, deleted |

## ADR-005 §2 — unchanged by this work

| # | Condition | State |
|---|---|---|
| 1 | Boot directly into Chromium | 🔴 **NOT TESTED** — launched manually; no autostart written |
| 2 | Connect to `analyzer_link` | 🟡 **PARTIAL** — fixture only; `--serial /dev/ttyAMA0` never run |
| 3 | Render real protocol-v2 frames | ✅ **MET** |
| 4 | Survive disconnect and reconnect | 🔴 **NOT TESTED** |

**The Tk UI remains what ships.**

## Next

1. **Touch** — one tap on a tab, on the panel. The one gap that cannot be closed
   remotely.
2. **The FFT presentation contract** — reviewed, in `presentation_semantics.py`,
   with tests, before any spectrum is drawn. `TestFftScopeFence` fails if that
   order is broken.
3. **`--serial /dev/ttyAMA0`** against the live Teensy, which needs the Tk UI
   stopped so the port is free.
4. Then disconnect/reconnect, then autostart.
