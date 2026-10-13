# Chromium on the Pi 5 — first run, on the real GPU and the real panel

**2026-10-12, 23:35–23:52 PDT.** ADR-005 §2's first condition, tested for the
first time. Until tonight **no browser had ever run on this Pi**: the slice-1
screenshots (2026-09-30) were headless Chrome on macOS with SwiftShader, which
says nothing about Broadcom V3D.

**No firmware change. No protocol change. No wiring change. No measurement
initiated. Nothing on the Pi's own repository was modified**, and the Tk UI ran
undisturbed on pid 1514 throughout — the same pid before, during and after.

> **🛑 THIS IS NOT T1 EVIDENCE.** TODO-36 authorised renderer development as *"a
> development decision, NOT an acceptance waiver"*, with the matrix incomplete
> behind TODO-39. A working WebGL UI is **not** evidence that T1 passed and must
> never be cited as such.
>
> **🛑 THIS IS NOT LIVE-MEASUREMENT EVIDENCE.** Every frame below came from a
> **recorded fixture** replayed from disk. The Teensy was not measuring and the
> serial path was not used — the Tk UI held `/dev/ttyAMA0`.

---

## Method

Code was staged in a **scratch directory** (`~/gra-webtest`), not the Pi's
repository checkout, which sits at `ce682cd` with 16 modified and 30 untracked
files and was deliberately left alone.

```
rsync  pi/  +  config.h data_sender.{h,cpp} insights_engine.h
              measurement_core.h measurement_engine.h signal_router.h
       +  ai/evidence/phase10-result-1khz.bin
                      SHA-256 e8b57d6f62af1367b654dd6d13270a94d73f06868ac785edf353f20179dd14a1
                      — the value already asserted by test_result_fixture.py, unmodified
```

Launched over SSH with `pi/run_web.sh`. No keyboard was attached to the Pi at any
point. Screenshots taken with `grim` on the live compositor, so every image below
is **the actual panel**, not a render of it.

## Platform inventory

| | |
|---|---|
| Model | Raspberry Pi 5 Model B Rev 1.1, 7.9 GiB |
| OS | Debian GNU/Linux 13 (trixie), kernel 6.18.50+rpt-rpi-2712 aarch64 |
| Compositor | labwc (pid 1391), `wayland-0`, with `wf-panel-pi`, `pcmanfm-pi`, `squeekboard` |
| Browser | **Chromium 152.0.7977.82** (Debian build), binary `chromium` |
| GPU modules | `v3d`, `vc4` loaded; `/dev/dri/card0,1,2` + `renderD128` |
| Output | DSI-2, **720×1280 @ 60.038 Hz**, transform normal, scale 1.0 |
| Python | 3.13.5 |

## Test suite on the Pi

```
369 tests ... OK (skipped=5)      26.0 s
```

Five skips are `'timeout fixture not present'` — `phase10-result-attempt.bin` was
not synced. **An earlier run reported 44 failures / 4 errors; that was my
incomplete sync, not a Pi defect.** `test_firmware_header_sync` and
`test_transport_atomicity` read the C++ headers from the repository root, which
the first `rsync` had not copied. With them present the suite is green.

---

## 1 — 🔴 FAILURE FOUND: the keyring dialog blocks the kiosk

**First launch did not reach the page.**
[`…-keyring-block.png`](2026-10-12-pi-chromium-keyring-block.png) — Chromium's
first run on a fresh profile asked gnome-keyring for a secret store, which raised
a modal **"Choose password for new keyring"** over the kiosk window and popped
`squeekboard` over the lower half of the panel.

**This is a kiosk-fatal failure, and it is invisible on macOS.** The page never
becomes visible, and **there is no keyboard attached to dismiss it.**

**Fix applied** in `pi/run_web.sh`: `--password-store=basic --use-mock-keychain`.
Re-launched, and the dialog did not appear. The flag carries a comment saying what
it prevents, because a later contributor tidying "redundant" flags would silently
restore the failure.

## 2 — ✅ Hardware WebGL, not software

[`…-gpu-diag.png`](2026-10-12-pi-chromium-gpu-diag.png)

```
version            WebGL 2
unmasked vendor    Google Inc. (Broadcom)
unmasked renderer  ANGLE (Broadcom, V3D 7.1.10.2, OpenGL ES 3.1)
acceleration       hardware (by renderer string)
max texture        4096
max renderbuffer   4096
```

`diag.html` treats a SwiftShader or llvmpipe renderer string as a **failure**, not
a pass with a caveat — software rendering would make every frame-rate figure taken
afterwards meaningless. The string is V3D, so the Pi's GPU is in use.

🔺 **`MAX_TEXTURE_SIZE` is 4096.** Not a problem for anything built today, and a
real ceiling for a future waterfall that wanted a larger data texture.

## 3 — ✅ Portrait, scale 1, and the full panel — but **only after a resize**

[`…-kiosk-viewport.png`](2026-10-12-pi-kiosk-viewport.png)

```
at load     668 x 392        <-- the surface has not reached fullscreen yet
on resize   720 x 1280
+2s         720 x 1280
+6s         720 x 1280
screen 720 x 1280   devicePixelRatio 1   orientation portrait-primary
```

**The kiosk does get the whole panel.** But a script that samples
`innerWidth`/`innerHeight` **once at load gets 668 × 392 and never corrects**, because
Chromium's Wayland surface is created at a provisional size and resized when the
compositor assigns the output.

### 🔺 This is a live defect in the shipping renderer

[`fingerprint_split.js`](../../pi/web/static/fingerprint_split.js) reads
`container.clientWidth` / `clientHeight` **once**, in `createFingerprint()`, and
derives the camera aspect *and* `cameraDistance` from them. There is no `resize`
handler. On this Pi it therefore fits the ring to a 668 × 392 viewport and then
displays it at 720 × 1280 — which is visible in §4's screenshot as a ring that is
small, vertically off-centre, and surrounded by dead space.

**The code comment is right and the code is wrong.** The module already says the
ring "must fit the NARROW axis. On 720x1280 portrait that is the horizontal one,
so a distance tuned on a landscape mock crops the ring." The arithmetic does that
correctly — from numbers that are not the panel's. **Found only on hardware; a
macOS window is sized correctly before first paint, so this cannot reproduce
there.** Fix belongs with the four-tab shell work, and the shell must take the
same lesson: **no layout may be computed from a one-shot viewport read.**

## 4 — ✅ The instrument UI renders real recorded bytes on the panel

[`…-fingerprint-fixture.png`](2026-10-12-pi-web-fingerprint-fixture.png)

```
source 512 bins · 0 measured · 4 indeterminate · 508 unmeasured
   ->  ring 48 bins · 0 measured · 2 indeterminate · 46 unmeasured
quality POOR · 32 averages · coherence 0.799 · NOT calibrated · session 7 · LINK STALE
```

**Identical to the census in the 2026-09-30 macOS record**, from the same fixture,
through the same contract. On screen: the baseline ring, the divider, and **exactly
two amber markers**. **No bars. 46 of 48 bands draw nothing.**

`LINK STALE` is correct and not a fault — the fixture replay had ended.

## 5 — ✅ 60 fps with the real renderer

[`…-fingerprint-60fps.png`](2026-10-12-pi-web-fingerprint-60fps.png)

```
60 fps (min 45)      25 s continuous, orbit animation running,
                     3 InstancedMeshes, pixel ratio 1
```

Measured by a temporary probe appended to the **scratch copy** of `main.js`, which
was restored immediately afterwards — the Pi's copy now hashes identically to the
repository's (`32cfba36…`). The probe drew nothing and touched no measurement
value. **It is not in the repository.**

The worst 1-second sample was 45 fps. **I did not establish when it occurred**, so
it is reported as the worst sample and not attributed to startup.

The trivial-scene cadence on `diag.html` was also 60 fps, so the fingerprint's draw
load is not reducing the steady-state rate.

## 6 — ⚠️ Touch: capability confirmed, delivery NOT tested

```
max touch points   10
pointer events     supported
observed           none
```

**Nobody touched the panel.** `diag.html` has a drag pad that records real pointer
events, and it recorded nothing because this was run entirely over SSH. The
capability is reported by the browser; **delivery to the page is unverified**, and
so is the fingerprint's swipe-to-orbit. This needs one person and one finger.

---

## ADR-005 §2 — the four conditions for the web client to become production default

| # | Condition | State |
|---|---|---|
| 1 | Boot directly into Chromium | 🔴 **NOT TESTED** — launched manually over SSH. No autostart was written, and the Tk autostart is untouched |
| 2 | Connect to `analyzer_link` | 🟡 **PARTIAL** — the transport ran and decoded correctly, but from a **recorded fixture**. `--serial /dev/ttyAMA0` has still never been run |
| 3 | Render real protocol-v2 frames | ✅ **MET** — real recorded protocol-v2 bytes, decoded, classified and rendered on the panel |
| 4 | Survive disconnect and reconnect | 🔴 **NOT TESTED** |

**The Tk UI remains what ships.** One of four conditions is met.

## What this does NOT establish

- **Not T1.** Independent evidence track, unchanged.
- **Not the MEASURED bar path.** This fixture classifies to **zero** MEASURED
  bands, so bar heights, side assignment, the cyan and orange ramps,
  coverage-driven thickness and frame easing remain visually unconfirmed. ADR-005's
  🔺 open evidence debt is **unchanged**, and this run did not attempt to close it
  with generated data.
- **Not live measurement.** The Teensy was not measuring.
- **Not the serial path, not autostart, not reconnect, not touch delivery.**
- **Not long-run stability.** Longest continuous run was ~25 s.

## State of the Pi afterwards

| | |
|---|---|
| Chromium / UI server processes | none |
| Tk UI | running, **pid 1514 — the same pid as before this session** |
| `/etc/xdg/labwc/autostart` | sha256 `3a53212a…` — unchanged, matches the 2026-09-30 record |
| `~/.config/labwc/autostart` | mtime 2026-09-30 00:30:46, untouched, still launching `run_ui.sh --serial /dev/ttyAMA0` |
| Pi's repository checkout | untouched |
| `~/gra-webtest` | scratch tree, removable with one `rm -rf` |
| Chromium profiles | ephemeral, `/tmp/gra-kiosk.*`, deleted |

## Next

1. **Fix the one-shot viewport read** in `fingerprint_split.js`, with a resize
   handler, as part of the four-tab shell.
2. **Touch delivery** — one session, one finger, on `diag.html`'s pad and then the
   fingerprint's orbit.
3. **`--serial /dev/ttyAMA0`** against the live Teensy, which requires stopping the
   Tk UI so the port is free.
4. Only after 2 and 3: disconnect/reconnect, then autostart.
