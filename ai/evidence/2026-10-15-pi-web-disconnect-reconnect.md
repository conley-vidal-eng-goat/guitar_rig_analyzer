# The web kiosk survived a Teensy disconnect and reconnect — ADR-005 §2.4

**2026-10-15, 20:30:04–20:35:01 PDT.** The last of
[ADR-005](../../docs/adr/ADR-005-pi-rendering-stack-and-presentation-semantics.md)
§2's four conditions, and the one that had never been exercised deliberately.

**No firmware change, no protocol change, no wiring change, no measurement
initiated.** The instrument was `IDLE` throughout. The Teensy was power-cycled
at the bench by the operator; nothing else was touched.

| | |
|---|---|
| Repository | `b68d648`, clean tree |
| Code running | `~/gra-ui/pi/`, **byte-identical to Mac HEAD** (60 files, `__pycache__` excluded) |
| Launcher | `sh run_web.sh --serial /dev/ttyAMA0 --prefer live` |
| Transport | `python3 -m web.server`, pid **11153**, sole `/dev/ttyAMA0` holder |
| Supervisor / browser | pid **11149** / pid **11177** |
| Pi health | `throttled=0x0`, 48.8 °C at the end |
| Sampler | `/api/frame` once per second, 286 samples |

Raw log: [`2026-10-15-pi-web-reconnect-link.log`](2026-10-15-pi-web-reconnect-link.log),
SHA-256 `505863e591d4116fbc718a16aea9c745898c25e312288a4b2adb424694dcadcf`.

---

## The transition, as recorded

```
20:30:04  kind=live     stale=False  session=49     <- baseline, frames rising
20:31:38  kind=live     stale=True   session=49     <- disconnect detected
20:31:55  kind=unknown  stale=None   session=None   <- receiver reset, awaiting HELLO
20:31:58  kind=live     stale=False  session=50     <- recovered, new session
```

**Session advanced 49 → 50.** The Teensy's EEPROM boot counter is the
independent witness that the device genuinely restarted; a link that merely
hiccuped would have come back on 49.

**`frames_in` froze at exactly `7911` for all 16 stale samples** and resumed at
`7934`. The counter did not advance by a single frame while the link was down,
which is what distinguishes a real outage from a slow poll.

**After recovery: 177 samples, `frames_in` 7934 → 12612 (+4678), monotonically
non-decreasing, mean 26.6 frames/sample** — the same ~26 frames/s the link
carried before the disconnect.

### Panel captures — the physical display, not a render

| | |
|---|---|
| Before | [`…-baseline.png`](2026-10-15-pi-web-reconnect-baseline.png) — `session 49 · LINK UP · 1102 frames`, TONE, two MEASURED bands drawn |
| After | [`…-recovered.png`](2026-10-15-pi-web-reconnect-recovered.png) — `session 50 · LINK UP · 11209 frames`, TONE, one MEASURED band |

Both captured with `grim` off the live compositor at 720×1280.

## Timing, stated at its true strength

| Interval | Observed |
|---|---|
| Last frame advance → `stale` raised | **≤ 2 s** |
| `stale` held (operator's hold + Teensy boot) | **17 s** |
| Receiver reset → live on the new session | **3 s** |
| Total link interruption seen by the Pi | **21 s** |

🔺 **The sampler is not a precise 1 Hz clock.** It is `curl` plus `sleep 1`, so
inter-sample gaps measured **1–2 s** and 12 of 285 gaps exceeded one second.
Every figure above carries **±1–2 s**, and two seconds are missing from the log
entirely (20:31:45, 20:33:03) — curl latency, not link events.

🔺 **The 3 s re-acquisition is measured from the Pi's first observation of the
Teensy returning, not from the physical replug.** The operator's replug time was
not recorded, so the Teensy's own boot time is inside the 17 s stale window and
is not separable from it by this record.

## What this establishes

**The web client survives a disconnect and reconnect without intervention —
ADR-005 §2.4, the project's longest-standing untested renderer condition.**

**It recovered with no restart of anything.** Supervisor `11149`, transport
`11153` and browser `11177` were alive before the event and alive afterwards,
with unchanged `/proc/<pid>/stat` start times (boot + 763.78 / 763.82 /
764.02 s). Exactly one kiosk browser, exactly one transport, exactly one
`ttyAMA0` descriptor, throughout.

**`decode_errors` stayed at 0 in every sample that carried one.** A reconnect is
not charged as a transport fault — the behaviour `replay.py`'s `reset()` was
built for, now observed on hardware rather than argued from code.

**The failure was displayed honestly.** `LINK STALE` appeared on the panel and
the last values were held rather than zeroed or blanked. The operator's
independent report (`RPT`) — *"the web UI showed LINK STALE… recovered and
resumed displaying live data"* — agrees with the log (`OBS`).

## 🛑 What this does NOT establish

**Nothing about measurement accuracy.** `IDLE` throughout, no capture armed, no
stimulus. The single MEASURED band in the recovered capture is ambient, not a
measurement anyone should read.

**One cycle, not a population.** One disconnect and one reconnect. Nothing here
speaks to repeated cycles, to a disconnect *during* a capture, or to a partial
link (bytes arriving corrupted rather than stopping).

**A Teensy power-cycle, not every disconnect.** The UART lines were not pulled
and the Pi-side device node never disappeared. A cable fault is a different
experiment.

**It does NOT establish behaviour when the Teensy is absent at kiosk start.**
That is the boot-time case, and it was not exercised. `/dev/ttyAMA0` exists
whenever `dtparam=uart0=on` is set, so `SerialSource` should open it and simply
report *"no HELLO yet"* — but **that is reasoning from the code, not an
observation**, and it must not be recorded as one.

**`frames_in` is cumulative across sessions, not per-session.** It ran 7911 →
7934 across the session change rather than resetting. A future reader must not
read a non-zero `frames_in` as "frames received during this session".

## ADR-005 §2 after this test

| # | Condition | State |
|---|---|---|
| 1 | Boot directly into Chromium | 🔴 **still not written** — the autostart is untouched |
| 2 | Connect to `analyzer_link` | ✅ met 2026-10-13 |
| 3 | Render real protocol-v2 frames | ✅ met 2026-10-13 |
| 4 | Survive disconnect and reconnect | ✅ **MET — this record** |

**Three of four.** The Tk UI still ships until §2.1 holds.

## State of the Pi at the end of this record

| | |
|---|---|
| `~/.config/labwc/autostart` | **UNCHANGED**, sha256 `b40fbc70…` — a reboot still brings back the Tk UI |
| `/etc/xdg/labwc/autostart` | **UNCHANGED**, sha256 `3a53212a…` |
| Tk UI | stopped by SIGTERM at 20:25 for the UART handoff; **not** respawned, launcher preserved |
| Web kiosk | **running**, sole UART holder |
| Rollback | `~/gra-rollback/` — backup, hash record, and `restore-tk-startup.sh` |
| Pi's own checkout | untouched, `ce682cd`, 49 dirty/untracked entries preserved |
