# Pi autostart — user-level labwc config, reversible with one `rm`

**2026-09-30.** Created `~/.config/labwc/autostart` so the Pi boots into the
analyzer UI and the desktop icon layer stops compositing over it.

**No system file was modified. No firmware change. No wiring change.**

## The original configuration, preserved verbatim

`/etc/xdg/labwc/autostart`, root-owned, **unchanged**, sha256
`3a53212ad85afb47ef60ebb66c5a6c911cba210ff5577492acfafa2c68edb719`:

```sh
/usr/bin/lwrespawn /usr/bin/pcmanfm-pi &
/usr/bin/lwrespawn /usr/bin/wf-panel-pi &
/usr/bin/kanshi &
/usr/bin/lxsession-xdg-autostart
```

Verified unchanged after the edit — same sha256.

## Rollback, complete and exact

```sh
rm ~/.config/labwc/autostart
```

That is the whole of it. labwc falls back to the system file, desktop icons
return, and nothing launches at boot. **Nothing else needs undoing**, because
nothing else was touched: no system file, no systemd unit, no `.desktop` entry,
no pcmanfm preference.

## 🔺 CORRECTION — labwc runs BOTH files, not one instead of the other

**The first version of this record, and of the config, was built on a wrong
assumption and the reboot test caught it.**

I wrote that labwc reads `~/.config/labwc/autostart` **instead of** the system
file. **It does not.** labwc 0.20.1 runs the user file **in addition to**
`/etc/xdg/labwc/autostart`.

**The evidence is unambiguous**, from the first reboot:

```
1500 /bin/sh /usr/bin/lwrespawn /usr/bin/pcmanfm-pi     <- system file
1501 /bin/sh /usr/bin/lwrespawn /usr/bin/wf-panel-pi    <- system file
1507 /bin/sh /usr/bin/lwrespawn /usr/bin/wf-panel-pi    <- MY file
kanshi: 2 instances                                      <- one from each
```

**Two consequences, both mine to own.** `pcmanfm-pi` started anyway — omitting
it from an *additive* file cannot suppress it. And I **introduced duplicate
services**: two panel supervisors and two kanshi, because my file re-listed
services the system file already starts.

**Smallest correction, applied and re-tested:** the user file now contains
**only** the analyzer line. Second reboot confirmed exactly one of each —
`wf-panel-pi 1 · kanshi 1 · pcmanfm 1 · Xwayland 1 · python3 1`.

**The desktop-icon objective was met anyway, by a different mechanism.**
`pcmanfm-pi` runs and draws icons, but the analyzer sets `-topmost` and both
boot screenshots show it fullscreen with **nothing compositing over it**. The
`pcmanfm --desktop-off` workaround used for the 2026-09-29 captures is no longer
needed. **Suppressing pcmanfm was never necessary — only getting above it was.**

## What was created

`~/.config/labwc/autostart` (user-owned, 0664). **Final content, after the
correction above — one line, because the file is ADDITIVE:**

```sh
/home/conley/guitar_rig_analyzer/pi/run_ui.sh --serial /dev/ttyAMA0 &
```

Everything else — `pcmanfm-pi`, `wf-panel-pi`, `kanshi`,
`lxsession-xdg-autostart` — comes from the untouched system file.

| Property | Why |
|---|---|
| **NOT wrapped in `lwrespawn`** | Operator decision. Escape must terminate the app normally; `/dev/ttyAMA0` must stay free for diagnostics afterwards; a crashing app must not enter a restart loop; this is a development instrument, not a locked-down kiosk. **Verified: after terminating the UI it did not return, and a fresh `capture.sh` succeeded immediately.** |
| Nothing else listed | because the file is additive — re-listing stock services duplicates them, which is exactly the defect the first reboot exposed. |

## ⚠️ Known risk, flagged before the test rather than after

**Xwayland is not running.** `DISPLAY=:0` *is* exported into the session (read
from a live `wf-panel-pi`'s `/proc/<pid>/environ`), but labwc starts Xwayland
**lazily**, on the first X client connection. Tk is an X client, so it should
spawn Xwayland on demand — that is what happened on every manual launch.

**At boot the machine is busier**, and a `-fullscreen` mapping race has already
been observed once on this session (fixed by re-asserting it 120 ms after map).
If the UI does not appear after reboot, the first thing to try is a delay:

```sh
sh -c 'sleep 5; exec /home/conley/guitar_rig_analyzer/pi/run_ui.sh --serial /dev/ttyAMA0' &
```

The launch line was left exactly as specified rather than pre-hardened, so the
reboot test measures the minimal configuration.

**✅ THE RISK DID NOT MATERIALISE.** On both reboots Xwayland started on demand
(`/usr/bin/Xwayland … :0 -rootless -core -terminate 10`) and the UI came up
fullscreen without any delay. **No `sleep` was needed and none was added.**

The autostart line has no output redirect, so if the UI is absent check
`journalctl --user -b` for the compositor's captured stderr, then launch it by
hand over SSH to see the error directly.

## Pre-reboot baseline, for comparison afterwards

| | |
|---|---|
| Display | DSI-2, **720×1280 portrait**, transform normal, scale 1.0 |
| Teensy | firmware `dcfbffa`, **session 9**, IDLE — the Teensy is not rebooting, so the session id should still read **9** afterwards |
| Stimulus | ~1 kHz tone playing, SOURCE ≈ −22 dBFS |
| UART | free — `0` fds on `/dev/ttyAMA0`, no `python3` running |
| `run_ui.sh` | present, `-rwxr-xr-x`, `sh -n` clean |
| User autostart | did not previously exist; system default was in use |

## Reboot acceptance results

Two reboots. **Reboot 1** exposed the additive-autostart defect above;
**reboot 2**, after the one-line correction, is the accepted run. The Teensy was
**not** power-cycled at any point — session **9** throughout, which is itself the
check that the Pi reboot did not disturb it.

| # | Item | Reboot 1 | Reboot 2 | Evidence |
|---|---|---|---|---|
| 1 | Fresh boot | ✅ | ✅ | boot_id `9ad8e08f` → `5b313ae5` → `4c05ebf4`; uptime 0 min |
| 2 | DSI-2 720×1280 portrait | ✅ | ✅ | `wlr-randr`: 720x1280, transform normal, scale 1.0 |
| 3 | Exactly one UI, auto-launched | ✅ | ✅ | `python3 -m analyzer_ui --serial /dev/ttyAMA0`, count 1 |
| 4 | Fullscreen, no icons over it | ✅ | ✅ | both screenshots; `-topmost` holds above the icon layer |
| 5 | HELLO, firmware, session 9 | ✅ | ✅ | `LINK UP`, session **9**, fw 0.6.0, proto 2, 128/512·4:1·44100 |
| 6 | Live SOURCE/RETURN, energised TF | ✅ | ✅ | −22.2 / −66.8 dBFS; `2 finite · 126 NaN`, confidence 2 %, 4/512 clamped |
| 7 | Framing / CRC / decode | ✅ | ✅ | `frames ok 964` then `283`, **CRC 0, decode 0, interior discard 0** |
| 8 | No unexpected route or state change | ✅ | ✅ | `IDLE`, `TS return, no injection`, detectors UNKNOWN |
| 9 | Screenshot of auto-launched app | ✅ | ✅ | `…boot-FAIL.png`, `…boot-PASS.png` |
| 10 | Terminate releases the UART, no respawn | ✅ | — | 1 fd → **0**; still 0 after 4 s; fresh `capture.sh` 109 594 B @ 36 531 B/s |
| 11 | Manual relaunch works, exits cleanly | ✅ | — | via the production `run_ui.sh` line; 1 instance, 1 fd → 0 on exit |
| — | **No duplicate services** | ❌ **FAIL** | ✅ **PASS** | 2× panel supervisor + 2× kanshi → exactly 1 of each |

### ⚠️ Item 10 is PARTIAL and must not be read as a full pass

**The Escape key itself was not pressed.** No key-injection tool is installed
(`xdotool`, `wtype`, `ydotool`, `dotool` all absent) and installing one was out
of scope, so Escape could not be exercised remotely.

What *was* verified is everything Escape leads to: the process terminates, the
UART goes to **0 fds**, a fresh capture succeeds, and **it does not come back**.
The binding is `self.root.bind("<Escape>", lambda _e: self.root.destroy())`, and
`destroy()` ends the mainloop exactly as SIGTERM does, so the paths converge —
but that is an argument, not an observation. **One operator keypress closes it.**

## Not affected by this change, and still open

**TODO-39** (T1 timing-probe counter stride) · **TODO-65** (RESULT lacks per-bin
clamp metadata) · **runbook step 7** (fully-clamped decimated-bin presentation
unverified — the current stimulus produces only half-clamped groups) · **T1 runs
3/4** (no-flow-control premise invalid) · **Phase 9**. None of these is advanced
by UI or autostart evidence.
