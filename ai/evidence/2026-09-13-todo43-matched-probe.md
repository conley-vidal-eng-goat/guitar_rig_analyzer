# TODO-43 closure evidence — matched-probe measurement

**Image:** `2026-09-13-todo43-matched-probe.jpg` (Photo Booth capture, 2026-09-13 18:55 local)

## Conditions

| | |
|---|---|
| Probe point | SGTL5000-side pad of the LINE-IN-L coupling capacitor |
| Ground reference | Audio Shield local GND |
| Physical probe switch | **10×** |
| Scope channel probe ratio | **10×** (DHO804 CH1) |
| Vertical | 10.00 mV/div, 0.00 V offset, AC coupled, 20 MHz BW limit |
| Timebase | 500.00 µs/div, 1.25 MSa/s, 10.00 kpts, 800 ns/pt |
| Stimulus | phone → USB-C adapter → 1/4" instrument jack, 1 kHz, unchanged from the mismatched-probe reading |

## Reading

VRMS — Cur 16.3 mV, Avg 16.3 mV, Max ~16.5 mV, Min ~15.9 mV, Cnt 24.
Freq — Cur 989 Hz, Avg 1.00 kHz, Max 1.00 kHz, Min 968 Hz, Cnt 24.
Clean sine with HF fuzz riding on it, no clipping.

## Independent check from the image itself

The trace spans ≈5 divisions peak-to-peak at 10 mV/div ⇒ ≈50 mV<sub>pp</sub> including
the fuzz. 16.3 mV<sub>rms</sub> × 2√2 = 46.1 mV<sub>pp</sub> for the sine alone.
The visual envelope and the VRMS readout agree.

## Result

46.1 mV<sub>pp</sub> against `lineInLevel(5)` full scale of 1.33 V<sub>pp</sub>:
20·log₁₀(0.0461/1.33) = **−29.2 dBFS predicted**, **−29.9 … −30.4 dBFS observed**.
Agreement **0.7–1.2 dB**. See journal 2026-09-13 (6), TODO-43.

## ⚠️ Two caveats on this image as evidence

1. **The probe attenuation ratio is not visible in the frame.** The CH1 badge shows
   `10.00mV/ 0.00V 20MHz ~` but the cropped capture does not include the probe-ratio
   field. The 10× physical switch and 10× channel ratio are recorded here from the
   operator's report at the bench, not read off this image. A future capture taken to
   document a scale question should include the probe-ratio field in frame — that is
   precisely the standing lesson this investigation produced.
2. **The trigger level reads 45.00 mV on CH1, above the signal's ≈±25 mV excursion**,
   so the scope was most likely free-running in AUTO sweep. This does not affect the
   VRMS or frequency statistics, which are computed over the acquisition record
   regardless of trigger (Cnt 24 measurement samples on both). Noted so nobody later
   reads the screenshot and mistakes it for a triggered acquisition.
