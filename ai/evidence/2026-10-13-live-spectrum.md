# The LIVE spectrum — the first real instrument data on screen

**2026-10-13.** The reviewed FFT presentation contract, forwarded through the
payload and rendered on the panel.

**No firmware change, no protocol change, no wiring change, no measurement
initiated.** Every frame is the pinned `phase10-teensy-pi-idle-30s.bin` fixture
(2026-09-26, 30 s idle). The Tk UI kept `/dev/ttyAMA0` throughout.

| | |
|---|---|
| Tests | **432**, green on macOS **and** on the Pi (21 new) |
| Pi render | [`…-pi-live-spectrum.png`](2026-10-13-pi-live-spectrum.png) — `grim`, 720×1280 |
| macOS render | [`…-mac-live-spectrum.png`](2026-10-13-mac-live-spectrum.png) — headless, `--disable-gpu` |
| CPU, LIVE tab | **6.4 %** of one core (TONE is 30.4 %) |

LIVE has **no animation loop at all**. The spectrum redraws on the 500 ms poll,
so the tab costs a fifth of what the orbiting fingerprint does.

---

## Units — established, not assumed

| Source | Says |
|---|---|
| `audio_capture.cpp:693` | `s_accum_src[k] += s_fft_src.read(k)` |
| `audio_capture.cpp:99` | `s_fft_src` is an `AudioAnalyzeFFT1024` |
| `audio_capture.cpp:485` | `windowFunction(AudioWindowHanning1024)` |
| `audio_capture.cpp:778` | `fft_source[k] = accum * (1.0 / FFT_AVERAGE_COUNT)` |

A **Hann window** is applied; its coherent gain is 0.5, so a full-scale sine does
not read 1.0 in its bin. The mapping from full-scale input to 1.0 **has never
been calibrated on this instrument.**

🔺 `audio_capture.cpp:332` defines `linearToDbfs()` — converts these to "dBFS"
with a `-120.0` floor, and **has no callers.** Its name is an unverified claim
and its floor is an invented number. Wiring it up would put both on screen as
measurements. **TODO-81.**

**The axis therefore reads "dB relative to FFT magnitude 1.0 — not dBFS",** and
these values never share an axis with `peak_source_dbfs`.

## The display floor is a drawing choice

The idle capture contains **5 bins at exactly 0.0** (3 source, 2 return).
`log10(0)` is undefined, so those points are drawn at **−100 dB**, the named
display floor — and the screen says so:

> *5 point(s) drawn at the −100 dB display floor, of which 5 are a measured
> magnitude of exactly zero. The floor is where this graph stops, not a noise
> floor the instrument reported. Marked on the baseline.*

A zero magnitude is a **measurement of silence**, so it is classified MEASURED,
forwarded as `0.0` rather than `null`, counted, and marked on the baseline. The
instrument never said "−100 dB"; the renderer said "at or below the bottom of my
axis".

## 🔺 Coverage starts at 151 Hz, which is above a low E

Transmitted bin 0 spans **0 – 150.73 Hz**. It contains DC, and because the
firmware decimates by MAXIMUM without recording which source bin won, a large
value there may be a DC offset or a real tone near 130 Hz — nothing on the wire
distinguishes them. It is excluded from the log axis and **127 of 128 bins are
plotted.**

**So the live spectrum cannot see below 151 Hz, and a low-E fundamental at
82.41 Hz falls inside that gap.** The region is **drawn, hatched and labelled
"not transmitted"** rather than cropped away, because cropping the axis to the
data would have hidden a real limitation of the instrument. This matters for a
guitar analyzer and should be read before any conclusion about low-end response.

## What the screen shows, and why both numbers are right

```
spectrum (source)    128 bins · 128 measured · 0 unmeasured
spectrum (return)    128 bins · 128 measured · 0 unmeasured
transfer function    128 bins · 0 measured · 128 unmeasured
ring (presentation)   48 bins · 0 measured ·  48 unmeasured
```

**The same frame is fully measured as a spectrum and entirely absent as a
transfer function.** A magnitude has no denominator; a transfer function divides
by the source, and below `TF_SOURCE_GATE` there is nothing to divide by. Both
statements are correct, they are on one screen, and the Coverage card says why.

The traces sit near −80 dB rel. 1.0 while the instrument reports **−63.9 dBFS**
peak. Different quantities — per-bin averaged magnitude versus time-domain peak —
kept in separate cards with the unit on each, and the screen says *do not compare
the numbers.*

## No second resample

Each point is one transmitted bin at its own centre frequency. The firmware
already decimated 512 → 128 by MAXIMUM to preserve narrow peaks; reducing again
at the display would flatten exactly what it preserved. `resample_peak()` exists
in the contract for displays that genuinely must reduce — it is **not** used
here.

## The scope fence was replaced, not deleted

`TestFftScopeFence` fired as designed the moment the spectrum landed. It is
replaced by `TestSpectrumIsRenderedUnderTheReviewedContract` (14 tests) plus
`TestSpectraOnTheWire` (11 tests), which assert what the reviewed contract
requires rather than merely that nothing touches the arrays: the unit is never
labelled dBFS, the floor is a named exported constant never called a noise floor,
an exact zero is drawn at the floor and not discarded, the DC bin is excluded,
the spans tile without gaps, no second resample occurs, and the canvas is never
sized from a one-shot read.

## What this does NOT establish

- **Not live measurement.** Fixture replay; the Teensy was not measuring.
- **Not a calibrated level.** The 1.0 reference is uncalibrated; only
  *relative* shape is meaningful.
- **Not T1.** Unchanged.
- **Nothing below 151 Hz**, ever, on this live path.
- **Not touch on this screen.** The tab was reached by launching on it.

ADR-005 §2 unchanged: one of four conditions met; the Tk UI still ships.
