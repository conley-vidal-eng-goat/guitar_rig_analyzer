# Energised live capture — the instrument doing its job, on its own display

**2026-09-30 (00:16–00:18 local).** The Pi production UI rendering a **live,
energised** transfer function off `/dev/ttyAMA0` on the Touch Display 2.

**No flash. No firmware change. No commands transmitted. No measurement
initiated. No wiring, routing, generator or injection change.** Firmware
`26f2bee`, session **9**, unchanged since T1 Run 2.

| Media | |
|---|---|
| Still | [`2026-09-30-pi-ui-live-energised.png`](2026-09-30-pi-ui-live-energised.png) · sha256 `9f8f5ea0…affb6b` |
| Video | [`2026-09-30-pi-ui-live-energised.mp4`](2026-09-30-pi-ui-live-energised.mp4) · 20 s real time · sha256 `b979548b…59141c` |

## Stimulus verified BEFORE the UI took the port

Receive-only, no commands sent. Two readers on one tty would split the stream,
so the reference was taken first:

```
sh pi/tools/capture.sh /dev/ttyAMA0 5 /tmp/tone.bin
5s of 5s · 182 232 B · 36 446 B/s
```

`replay.py`: session **9**, firmware 0.6.0, geometry 128/512 · 4:1 · 44 100 Hz,
`IDLE`, no abort, **peak source −22.2 dBFS**, peak return −66.8 dBFS,
`tf_confidence 0.017`, **`tf_clamped_count 4`**, no clipping. `TRANSPORT: OK`.

**Source path:** battery phone → active USB-C DAC → continuity-verified
3.5 mm TRS → 1/4" TS cable (left channel only) → **J4 SOURCE**. Continuous
~1 kHz sine. Nothing is connected to the return, which is why the return sits at
the noise floor — that is the bench configuration, not a fault.

> **Level note.** −22.2 dBFS, against −23.8 dBFS during T1 Run 2 and −21.8 dBFS
> on 2026-09-27. The phone volume is not repeatable to better than ~2 dB by hand.
> **Irrelevant here** — this is a rendering demonstration, not a measurement, and
> nothing in it depends on the absolute level. It *would* matter for the T1
> matrix, which requires identical signal conditions across all four runs.

## What the still shows

`LINK UP` · session **9** · fw 0.6.0 · proto 2 · geometry **read from HELLO**,
not hard-coded · `IDLE` · **SOURCE −22.2 dBFS** · RETURN −67.4 dBFS ·
`confidence 2% · 4/512 clamped` · router `TS`, `TS return, no injection`,
`detectors: UNKNOWN (no detect hardware fitted)` · `frames ok 123, CRC fail 0,
decode err 0, discarded 1473 (lead 1473, interior 0)`.

**The transfer function shows a short mark at ~1 kHz and nothing anywhere else:**

```
128 bins · 2 finite · 126 NaN · 0 clamped · 126 lifted
```

## ★ The pair, and why both screenshots belong in the portfolio

| | Noise floor ([earlier shot](2026-09-30-pi-ui-live-uart.png)) | Energised (this one) |
|---|---|---|
| SOURCE | −64.3 dBFS | **−22.2 dBFS** |
| TF census | `0 finite · 128 NaN · 128 lifted` | `2 finite · 126 NaN · 126 lifted` |
| Plot | **completely empty** | one mark, at the stimulus |

The first proves the renderer **refuses to fabricate**: with no input it draws
nothing and states why. The second proves it **shows real signal where real
signal exists** — and still refuses to draw the 126 bins it has no measurement
for. Either alone is half the argument. Together they are the whole one, and
neither required a firmware change to produce.

## 🔍 A contract detail worth keeping: partial clamping is DRAWN, not marked

The frame reports **4 of 512 source bins clamped**, yet the decimated live view
reports **0 clamped of 128**. Both are correct and the arithmetic explains it.

Source bins 22–25 are the energised ones. At 4:1 decimation they fall into live
bins 5 (source 20–23) and 6 (source 24–27), giving each a coverage nibble of
**clamped = 2, ratio = 4**. `data_sender.h` says a saturation marker is drawn
when **`clamped == ratio`**, so a half-clamped group is plotted as data rather
than marked as a rail. The two finite live bins are exactly bins 5 and 6.

**This is the wire contract behaving as specified, not a discrepancy** — and it
is only visible because the per-bin nibbles are on the wire at all, which is what
protocol v2's audit finding L1 exists to provide. The RESULT packet has no
equivalent, which is **TODO-65**.

## Video method — nothing installed

No Wayland screen recorder is present (`wf-recorder`, `wl-screenrec`, OBS all
absent) and installing one was explicitly out of scope. `grim` and `ffmpeg` are
already on the system, so the video is **289 `grim` frames captured over 20 s
(14.45 fps) encoded by ffmpeg at the measured rate**, which plays back in real
time. 205 KB. Good enough to show the level bars and the frame counters
advancing; not a substitute for a proper screen recorder if one is ever wanted.

## Shutdown verified, not assumed

- `/proc/<pid>/fd` during the run: **`lr-x ... -> /dev/ttyAMA0`** — opened
  `O_RDONLY`, so the UI **cannot transmit even by accident**.
- `kill -TERM` → process gone.
- `ls -l /proc/*/fd | grep -c ttyAMA0` → **0**.
- Desktop icon layer was stopped for the capture with `pcmanfm --desktop-off`
  and **restored afterwards**. Nothing persisted, no config file touched.

## What this proves — and what it does not

**Proves:** the Pi renders live, energised, Teensy-authored telemetry on its own
display, off the real UART, with geometry taken from HELLO; it draws signal where
signal exists and gaps where it has no measurement; it reports the route and the
absence of detectors honestly; and it releases the device cleanly.

**Does not prove:** anything about T1 (blocked on the harness stride defect,
TODO-39); anything about a *live* RESULT delivery (none was initiated — the
2026-09-27 fixture supplies the only real RESULT); runbook step 7's clamp
*rendering* contract, which needs a **fully** clamped decimated bin, and this
stimulus produces only half-clamped ones; the Pi→Teensy path, which stays
physically disconnected. Phase 9 and Phase 10 both remain open.
