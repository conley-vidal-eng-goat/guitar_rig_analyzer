# Live Pi UI smoke test — the production UI reading the real UART

**2026-09-30 (00:05–00:15 local).** First time the Pi UI has rendered live
Teensy telemetry off `/dev/ttyAMA0` on the physical Touch Display 2.

**No flash. No firmware change. No validation harness, generator, injection,
relay or analog change. No measurement initiated.** Firmware `26f2bee`,
session **9**, unchanged since T1 Run 2. Receive-only wiring untouched.

Media: [`2026-09-30-pi-ui-live-uart.png`](2026-09-30-pi-ui-live-uart.png)
(live, `/dev/ttyAMA0`) and
[`2026-09-29-pi-ui-result-view.png`](2026-09-29-pi-ui-result-view.png)
(the real 2026-09-27 RESULT, replayed).

## Ground truth established BEFORE the UI touched the port

Two readers on one tty would split the byte stream, so the reference capture was
taken first, with the UI not running:

```
sh pi/tools/capture.sh /dev/ttyAMA0 5 /tmp/gt.bin
elapsed 5s of 5s · 182 305 B · 36 461 B/s
sha256 e2e3bc42bdb6750d518047c6ec705dc972a38a5abbe03d4ae26ff437e37faefa
```

`replay.py`: session **9**, firmware 0.6.0, geometry 128/512/4:1/44100,
`measurement_state IDLE`, no abort, `return_source TS`, all four detectors
UNKNOWN, `any_detector_available False`, injection inactive,
**peak source −65.2 dBFS / peak return −66.2 dBFS**, `tf_confidence 0.0`,
`tf_clamped_count 0`. `TRANSPORT: OK`.

## ⚠️ The 1 kHz stimulus was NOT playing

Source and return within 1 dB of each other, both at the noise floor, zero
confidence, zero clamped bins — the documented signature of an absent input. The
phone tone stopped again at some point after Run 2.

**That is not a defect and it did not block the smoke test.** Every item on the
checklist is about the *link and the renderer*, none of which depends on signal
being present. It also produced a sharper demonstration than a tone would have:
with nothing on the input the live TF plot is **completely empty**, and the
instrument says exactly why — `0 finite · 128 NaN · 0 clamped · 128 lifted`.
A UI willing to fabricate would have drawn something there.

**What it does mean:** the portfolio "hero" shot of an *energised* live transfer
function still needs the tone restarted. Everything else is captured.

## Checklist — all verified

| Required | Observed |
|---|---|
| UI launches on the physical Touch Display | ✅ fullscreen 720×1280 portrait, captured with `grim` |
| HELLO establishes the session | ✅ `LINK UP`, session **9**, fw 0.6.0, proto 2, geometry 128/512 · 4:1 · 44100 Hz — all from HELLO, none hard-coded |
| Live SOURCE/RETURN telemetry updates | ✅ SOURCE −64.3 → −64.7 → −63.5 dBFS across captures; RETURN −65.2…−67.4. Noise-floor wander, which is what a real noise floor does |
| Live TF updates without fabricating | ✅ **nothing drawn**: `128 bins · 0 finite · 128 NaN · 0 clamped · 128 lifted`, confidence 0 % |
| Router reports TS and detectors UNKNOWN | ✅ `Return source: TS`, `TS return, no injection`, `detectors: UNKNOWN (no detect hardware fitted)`, with the ADR-004 note on screen |
| Connection status correct | ✅ `LINK UP` while streaming; `LINK STALE` (amber) on the spent fixture — the staleness rule works in both directions |
| Closes cleanly, releases the device | ✅ see below |

### Live counters advancing (same run, 6 s apart)

`frames ok 100 → 255` — **155 frames in 6 s = 25.8 packets/s** against the
producer's measured 25.6/s. `CRC fail 0`, `decode err 0`, `interior 0`
throughout.

### Receive-only, proved rather than asserted

```
ls -l /proc/<pid>/fd  →  lr-x------ 1 conley conley 64 … 3 -> /dev/ttyAMA0
```

**`lr-x`** — opened read-only. `SerialSource` uses `os.O_RDONLY`, so the UI
**cannot transmit even by accident**. The Pi→Teensy direction stays physically
disconnected *and* structurally impossible from this code.

### Clean shutdown and device release

`kill -TERM` → process gone; `ls -l /proc/*/fd | grep -c ttyAMA0` → **0**; and a
fresh `capture.sh` immediately afterwards succeeded (109 693 B at 36 564 B/s),
which proves the device was actually released rather than merely closed on paper.

### Leading-discard split, visible live

Three launches reported `discarded 634 / 357 / 96 — (lead N, interior 0)`. The
figure varies because it is set by **where inside a packet the reader attached**,
which is exactly what the 2026-09-27 byte-accounting analysis established. Every
one had **interior 0**. The instrument now shows that split on its own face.

## 🛑 TODO-65 preserved and visible, not silently resolved

**RESULT carries no per-bin clamp mask.** The real RESULT's four finite magnitude
bins all read exactly **−24.0 dB**, the firmware's clamp rail, and nothing in the
RESULT packet distinguishes a measured −24.0 dB from a railed one. LIVE_FRAME
carries per-bin coverage nibbles and `tf_clamped_count`; RESULT carries neither.

**The Pi does not infer clamp status.** It prints the limitation on the plot:

> *all 4 finite bin(s) sit on the −24.0 dB clamp rail · RESULT carries no per-bin
> clamp mask, so measured and railed are indistinguishable here · live frame
> reports 4/512 clamped*

The −24.0 dB comparison is a **disclosure heuristic, not a classification**: it
says "these might be rails and I cannot tell", never "these are rails". It must
be deleted when the protocol closes the gap. A test pins the gap's existence so
it fails loudly when that happens.

## What this does NOT establish

- **Not T1.** Blocked on the harness stride defect (TODO-39); untouched here.
- **Not a live RESULT.** No measurement was initiated, deliberately — the
  2026-09-27 fixture already provides a real one. RESULT rendering is proven
  against recorded bytes, not against a live delivery.
- **Not the Pi→Teensy path.** Physically disconnected; commands render disabled.
- **Not runbook step 7.** The clamp *rendering* contract needs an energised,
  clamped live signal to demonstrate, which needs the tone back.
- **Not Phase 9, not Phase 10.** Both open.

## Blockers to making this the production launch path

**None technical.** It runs, reads live, renders honestly, and exits cleanly.
Outstanding for "normal launch path" status:

1. **Autostart** — a `.desktop` entry or systemd user unit so the panel comes up
   into the instrument rather than the desktop. Not done; a deliberate choice, so
   the Pi stays a normal desktop while it is also a development machine.
2. **Desktop icon layer** composites *over* the fullscreen window on this labwc
   session. Worked around for captures with `pcmanfm --desktop-off`, restored
   afterwards. Autostart plus a hidden desktop would remove it permanently.
3. **Fullscreen race** — `-fullscreen` applied before the window is mapped was
   silently ignored on roughly one launch in several under XWayland. Fixed by
   re-asserting it 120 ms after mapping; the launch that exposed it came up
   windowed with a taskbar, which is how it was caught.
