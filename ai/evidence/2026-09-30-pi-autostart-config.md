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

## What was created

`~/.config/labwc/autostart` (user-owned, 0664). labwc reads this **instead of**
the system file when it exists, so the copy retains every stock service except
one:

```sh
/usr/bin/lwrespawn /usr/bin/wf-panel-pi &
/usr/bin/kanshi &
/usr/bin/lxsession-xdg-autostart
/home/conley/guitar_rig_analyzer/pi/run_ui.sh --serial /dev/ttyAMA0 &
```

| Change | Why |
|---|---|
| `pcmanfm-pi` **dropped** | It draws the desktop icon layer, which composites **over** a fullscreen window on this session — a Wastebasket icon landed on the instrument during the 2026-09-29 captures and had to be worked around with `pcmanfm --desktop-off`. Dropping it removes the cause rather than the symptom. **Consequence: no desktop icons.** The file manager is still reachable from the panel. |
| analyzer launched last | so the panel and XDG autostart are up first |
| **NOT wrapped in `lwrespawn`** | Operator decision. Escape must terminate the app normally; `/dev/ttyAMA0` must stay free for diagnostics afterwards; a crashing app must not enter a restart loop; this is a development instrument, not a locked-down kiosk. |

`wf-panel-pi`, `kanshi` and `lxsession-xdg-autostart` are retained exactly as the
system file has them, including `lwrespawn` on the panel.

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
reboot test measures the minimal configuration. **If it fails, that is a result,
not a surprise.**

The autostart line has no output redirect, so if the UI is absent check
`journalctl --user -b` for the compositor's captured stderr, then launch it by
hand over SSH to see the error directly.

## Pre-reboot baseline, for comparison afterwards

| | |
|---|---|
| Display | DSI-2, **720×1280 portrait**, transform normal, scale 1.0 |
| Teensy | firmware `26f2bee`, **session 9**, IDLE — the Teensy is not rebooting, so the session id should still read **9** afterwards |
| Stimulus | ~1 kHz tone playing, SOURCE ≈ −22 dBFS |
| UART | free — `0` fds on `/dev/ttyAMA0`, no `python3` running |
| `run_ui.sh` | present, `-rwxr-xr-x`, `sh -n` clean |
| User autostart | did not previously exist; system default was in use |

## Reboot acceptance checklist (not yet run)

SSH reconnects · DSI stays 720×1280 portrait · UI launches automatically · no
desktop icons over the application · HELLO establishes session **9** · live
SOURCE/RETURN update · framing/CRC/decode healthy · **exactly one** UI instance ·
Escape exits and genuinely releases `/dev/ttyAMA0` · **no respawn after Escape** ·
manual launch works afterwards.

## Not affected by this change, and still open

**TODO-39** (T1 timing-probe counter stride) · **TODO-65** (RESULT lacks per-bin
clamp metadata) · **runbook step 7** (fully-clamped decimated-bin presentation
unverified — the current stimulus produces only half-clamped groups) · **T1 runs
3/4** (no-flow-control premise invalid) · **Phase 9**. None of these is advanced
by UI or autostart evidence.
