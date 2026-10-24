# Resuming from cold — Raspberry Pi 5 and Teensy 4.1, both powered off

**Written 2026-10-13 on the MacBook, with both devices powered off and
physically inaccessible. Nothing in this document has been executed.**

This is the procedure for getting from *everything off* to *a trustworthy
live link*, run from the Mac, one stage at a time. It exists because the
most expensive mistakes on this project have not been wrong measurements —
they have been **measurements taken in a state nobody had verified**, and
then reasoned from for days.

---

## How to read this

**Every stage states its power state explicitly.** Where a stage says
`POWER: OFF`, it means off at the start of the stage and still off at the end.
A stage that changes power state says so in its own step.

Each stage has four parts, and **the failure response is not optional reading**:

| | |
|---|---|
| **Prerequisites** | what must already be true. If it is not, stop |
| **Expected observation** | the specific thing you should see |
| **Failure response** | what to do when you do not see it — including *stop here* |
| **Evidence to preserve** | what to capture *while the state exists*, not afterwards |

### 🛑 Four standing rules

1. **No keyboard can be attached to the Pi.** Everything is done from the Mac
   over SSH. Any step that would need a keypress on the Pi is a design fault,
   not an instruction. The one known exception was `Escape` to close the Tk UI;
   since 2026-10-15 the kiosk ships instead and §5 gives the keyboard-free way
   to stop it. **Rebooting is the one action that still needs a password** —
   `ssh -t conley@guitar-rig-analyzer.local 'sudo reboot'` from the Mac, where
   `-t` is what lets the prompt appear. Still no Pi keyboard.
2. **Do not advance a stage on a partial pass.** If a stage is amber, it is
   failed. The whole point of staging is that a later observation cannot be
   contaminated by an earlier unverified one.
3. **Capture evidence while the state exists.** A screenshot taken after you
   fixed something is evidence about the fix, not about the fault.
4. **Power the Pi down cleanly** (`sudo shutdown -h now`, wait for the activity
   LED to stop) before removing power. Pulling power from a running Pi risks
   the SD card, and the SD card is the whole instrument.

---

## Stage 0 — Mac-side preparation

**POWER: OFF. Both devices stay off for this entire stage.**

**Prerequisites:** the Mac, this repository, and network access to wherever the
Pi will attach.

**Steps**

1. Confirm the repository state you intend to deploy:
   ```sh
   cd ~/Developer/guitar_rig_analyzer
   git log --oneline -3
   git status --short
   sh pi/run_tests.sh          # expect: OK
   ```
2. Note the commit hash. **Write it in the session log before you power
   anything on.** Every observation later in the session is an observation
   *about that commit*, and reconstructing it afterwards from memory is how
   evidence loses its provenance.
3. Decide, in advance and in writing, what the session is for. The next
   milestone is a controlled measurement, not another screen.

**Expected observation:** a known commit, a clean-enough tree, a green suite on
the Mac.

**Failure response:** if the suite fails on the Mac it will fail on the Pi.
Fix it here, where there is a keyboard and a debugger. Do not power on.

**Evidence to preserve:** commit hash, `git status` output, test count.

---

## Stage 1 — Power on the Pi **alone**

**POWER: Pi ON. Teensy stays OFF.**

The Teensy stays off deliberately. This stage establishes that the *display
and compute half* is healthy, with no serial traffic in the picture to
confuse a fault. If the Pi is broken, you want to know that before a link
failure gives you two candidate causes.

**Prerequisites:** Stage 0 complete. Teensy unpowered.

**Steps**

1. Apply power to the Pi. Wait for the panel to light.
2. From the Mac:
   ```sh
   ssh conley@guitar-rig-analyzer.local
   ```
3. Once in:
   ```sh
   uptime                              # expect: minutes, not days
   cat /proc/sys/kernel/random/boot_id # new value => a genuine fresh boot
   wlr-randr                           # expect: DSI-2, 720x1280, transform normal, scale 1.0
   vcgencmd get_throttled              # expect: throttled=0x0
   df -h /                             # expect: free space; a full card fails strangely
   ```

**Expected observation:** SSH answers; uptime is small; the panel reports
**720×1280 portrait, scale 1.0**; `throttled=0x0`.

**Failure response**

| Symptom | Response |
|---|---|
| `guitar-rig-analyzer.local` does not resolve | Try the IP from the router. mDNS is not a dependency of the instrument, only of convenience |
| SSH refused but the panel is lit | The Pi booted and networking did not. **Do not proceed** — you have no keyboard-free way in |
| Panel dark but SSH works | A display fault, not a boot fault. Record it and continue only if the session's goal does not need the panel |
| `throttled` non-zero | Power supply or thermal. **Stop.** An undervolted Pi produces intermittent faults that will be blamed on the link |
| `wlr-randr` shows a different geometry | Record it and stop. Every layout decision in this UI assumes 720×1280 portrait |

**Evidence to preserve:** `boot_id`, `wlr-randr` output, `get_throttled`.

---

## Stage 2 — Establish what is actually running, before trusting any of it

**POWER: Pi ON. Teensy still OFF.**

> ### ⚠️ The single most important fact in this document
>
> **🔺 CHANGED 2026-10-15 — the Pi now autostarts the WEB KIOSK, not the Tk UI.**
>
> `~/.config/labwc/autostart` contains one line:
> ```sh
> /home/conley/gra-ui/pi/run_kiosk_boot.sh &
> ```
> ADR-005 §2's four conditions were met on 2026-10-13 and 2026-10-15, and the
> migration was verified by a controlled reboot. See
> [`../pi/deploy/README.md`](../pi/deploy/README.md) and
> [`../ai/evidence/2026-10-15-pi-web-autostart-reboot.md`](../ai/evidence/2026-10-15-pi-web-autostart-reboot.md).
>
> So on every boot:
>
> 1. **`~/gra-ui/` is what runs** — a durable deployment kept byte-identical to
>    this repository's `pi/` tree. It is *not* `~/gra-webtest` or `~/gra-stage-*`
>    (scratch trees), and *not* the Pi's own checkout.
> 2. **`/dev/ttyAMA0` is already held** — by `python3 -m web.server`, the
>    transport. Nothing else can open it until that process ends.
>
> Neither of those is a fault. Both are facts you must establish *before*
> interpreting anything.
>
> **The Tk UI is still installed and still works**, as ADR-005 §2's reference
> renderer. It no longer starts by itself. `~/guitar_rig_analyzer` remains at
> **`ce682cd` with 49 dirty/untracked entries**, deliberately untouched — it
> holds the known-good Tk launcher the boot fallback uses, and uncommitted work
> that exists nowhere else. **Do not `git checkout .` in it.**

**Prerequisites:** Stage 1 passed.

**Steps**

1. What is running, and does it hold the UART?
   ```sh
   pgrep -af 'web.server'          # expect ONE — the production transport
   pgrep -af analyzer_ui           # expect NONE since 2026-10-15
   pgrep -af run_kiosk_boot        # expect ONE — the boot supervisor
   ls -l /dev/ttyAMA0 /dev/serial0
   ```
   🔺 **`sudo lsof` needs a password on this Pi and `pgrep -af <pattern>` matches
   your own command line** — both bit real sessions. Count the descriptor
   holders instead, which is the thing actually being asked about:
   ```sh
   for p in /proc/[0-9]*; do for f in $p/fd/*; do
     case "$(readlink "$f" 2>/dev/null)" in */ttyAMA0)
       echo "pid ${p#/proc/}: $(tr '\0' ' ' < $p/cmdline)";; esac
   done; done 2>/dev/null
   ```
   Expect **exactly one**, and expect it to be `web.server`.
2. What state is the Pi's own checkout in?
   ```sh
   git -C ~/guitar_rig_analyzer log --oneline -1
   git -C ~/guitar_rig_analyzer status --short | head -20
   ```
3. Is there scratch work left from last session?
   ```sh
   ls -la ~/gra-webtest 2>/dev/null
   ```

**Expected observation:** exactly **one** `web.server` process holding **one** fd
on `/dev/ttyAMA0`, one `run_kiosk_boot.sh` supervisor, one `chromium --kiosk`,
and **no** `analyzer_ui`; the Pi's own checkout at a commit that is not HEAD;
`~/gra-ui` present and matching this repository's `pi/` tree.

**Failure response**

| Symptom | Response |
|---|---|
| No `web.server` process | The kiosk did not start. **Read `~/gra-ui-boot.log` first** — the supervisor records every attempt, the reason, and whether it fell back |
| An `analyzer_ui` process is running | The Tk **fallback** fired, meaning the kiosk failed three times. The log says why. The panel is not blank, so this is a degraded success, not an outage |
| More than one of anything | A duplicate-startup defect of the kind the 2026-09-30 reboot exposed. Check for a second supervisor; the lock in `$XDG_RUNTIME_DIR/gra-kiosk-boot.lock` should make this impossible |
| `/dev/ttyAMA0` missing | The UART is not configured. On a Pi 5 **`/dev/serial0` is the wrong device** — it maps to `ttyAMA10`. Do not substitute it |
| Checkout is dirty in ways you do not recognise | Record it. **Do not `git checkout .`** — those modifications may be the only copy of something |

**Evidence to preserve:** process list, UART holder, the Pi checkout's commit
and dirty-file count. This is the "what was actually running" record that every
later claim depends on.

---

## Stage 3 — Stage current code **without touching the Pi's checkout**

**POWER: Pi ON. Teensy still OFF.**

**Prerequisites:** Stage 2 complete; you know what the Pi is running.

> **Deploy to `~/gra-webtest`, never to `~/guitar_rig_analyzer`.** The Pi's
> checkout is the thing the autostart line points at, and it is dirty. Writing
> to it would change what boots *and* risk destroying uncommitted work, in one
> step, with no undo. The scratch tree is removable with one `rm -rf`.

**Steps**

1. From the **Mac**:
   ```sh
   cd ~/Developer/guitar_rig_analyzer
   rsync -av --delete pi/ conley@guitar-rig-analyzer.local:~/gra-webtest/pi/
   (cd firmware/guitar_rig_analyzer && \
    rsync -av --mkpath config.h data_sender.h data_sender.cpp insights_engine.h \
             measurement_core.h measurement_engine.h signal_router.h \
             conley@guitar-rig-analyzer.local:~/gra-webtest/firmware/guitar_rig_analyzer/)
   rsync -av ai/evidence/phase10-result-1khz.bin \
             ai/evidence/phase10-teensy-pi-idle-30s.bin \
             conley@guitar-rig-analyzer.local:~/gra-webtest/ai/evidence/
   ```
   The C++ headers are **not optional**: `test_firmware_header_sync.py` and
   `test_transport_atomicity.py` read them from `firmware/guitar_rig_analyzer/`. Omitting them
   produced "44 failures / 4 errors" on 2026-10-12 that were entirely a sync
   gap and not a Pi defect.
2. On the **Pi**:
   ```sh
   cd ~/gra-webtest && sh pi/run_tests.sh
   ```

**Expected observation:** the suite passes, with skips only for fixtures you
chose not to sync. Compare the count against the Mac's.

**Failure response:** a failure here is a **sync problem until proven
otherwise**. Check the headers arrived before concluding anything about the Pi.
A genuine Pi-only failure is interesting and must be recorded as such.

**Evidence to preserve:** the test output with its count and skip list; the
`rsync` summary; `sha256sum` of any fixture you synced.

---

## Stage 4 — Power on the Teensy and prove the link with **raw bytes**

**POWER: Pi ON. → Teensy ON (this stage turns it on).**

> **Raw bytes first, never a decoded view.** A decoder agreeing with itself
> proves nothing — encoder and decoder in this repository share one author and
> one reading of `data_sender.h`, so a misreading would be reproduced on both
> sides and every test would still pass. A raw capture from a flashed Teensy is
> what breaks that loop.

**Prerequisites:** Stage 3 passed. **The UART must be free.** If the Tk UI is
holding it, do §5 first.

**Steps**

1. Apply power to the Teensy.
2. Free the UART if held (see §5), then on the Pi:
   ```sh
   cd ~/gra-webtest/pi
   sudo sh tools/capture.sh /dev/ttyAMA0 30 /tmp/resume-$(date +%Y%m%d-%H%M).bin
   ```
3. Read the script's own report. It checks itself.

**Expected observation:** ~30 s elapsed, roughly **1.1 MB**, about
**36 500 B/s** for an idle instrument. The 2026-09-26 hardware measurement was
36 465 B/s.

**Failure response**

| Symptom | Response |
|---|---|
| **"capture ended after Ns but 30s were requested"** | A **tooling fault**, not a link result. Do not interpret the byte count. The `stty` line must still read `min 1 time 0` |
| 30 s elapsed, **0 bytes** | A real observation. Before concluding the link is dead: `ls -l /dev/ttyAMA*`, `pinctrl get 14,15` (expect `GPIO14 = TXD0` / `GPIO15 = RXD0`). **`raspi-gpio` is NOT installed on this Pi** — corrected 2026-10-13 after the command failed mid-gate; `pinctrl` is its replacement on current Raspberry Pi OS and `gpioinfo` is also present. On 2026-09-26 a scope showed a healthy 3.3 V waveform arriving while `serial0` read nothing — wrong device, not a wiring fault |
| Rate far below ~36 kB/s | A link fault. **Fix it here.** Do not replay or render anything until the byte rate is right |

**Evidence to preserve:** the capture file itself, its **sha256**, the script's
full report including start/end timestamps and rate. This file is the session's
primary evidence and everything downstream is derived from it.

---

## Stage 5 — The UART handoff (keyboard-free)

**POWER: both ON.**

Only one process may hold `/dev/ttyAMA0`. **Since 2026-10-15 the holder at boot
is the web transport, not the Tk UI** — stopping it is the same operation with a
different target.

**Prerequisites:** Stage 4 gave a good raw capture.

**Steps**

1. Stop the kiosk **by its supervisor**, so cleanup runs:
   ```sh
   pkill -f run_kiosk_boot.sh       # the boot supervisor
   pkill -f 'sh run_web.sh'         # the launcher; its trap reaps both children
   sleep 5
   ```
   🛑 **Signal `run_web.sh`, not the transport directly.** The launcher's trap
   is what stops the browser, reaps both children and removes the ephemeral
   Chromium profile. Killing `web.server` alone orphans the browser and leaks
   the profile — that is TODO-82/83, and it cost 171 MB in one evening.
2. Confirm **0 fds** before continuing. Not "probably free":
   ```sh
   for p in /proc/[0-9]*; do for f in $p/fd/*; do
     case "$(readlink "$f" 2>/dev/null)" in */ttyAMA0) echo HELD;; esac
   done; done 2>/dev/null | wc -l       # expect 0
   ```

**Expected observation:** no `web.server`, no `chromium --kiosk`, **0** fds on
`/dev/ttyAMA0`, and the panel showing the desktop.

**The supervisor will NOT restart it**, provided the kiosk had been running for
at least 60 s — retries are scoped to startup, exactly so that freeing the UART
for diagnostics stays possible. That is the same operator decision that kept the
Tk line out of `lwrespawn` on 2026-09-30.

**Failure response**

| Symptom | Response |
|---|---|
| The kiosk returns by itself | It had been up **less than 60 s**, so the supervisor read the exit as a startup failure and retried. Wait for it to settle, or `touch ~/gra-ui/DISABLE_KIOSK_AUTOSTART` and stop it again |
| UART still held after the processes are gone | A stale fd. Record it — this is a real defect worth a TODO |
| You need the **Tk** UI back | `setsid sh ~/guitar_rig_analyzer/pi/run_ui.sh --serial /dev/ttyAMA0 &` from the **Pi's own checkout**. To make it boot again: `sh ~/gra-rollback/restore-tk-startup.sh` |
| You need the **kiosk** back | `cd ~/gra-ui/pi && setsid ./run_kiosk_boot.sh &` |

**Evidence to preserve:** the before/after descriptor count. "The UART was free"
is a claim; `0` fds is an observation.

---

## Stage 6 — Live serial into the renderer ⚠️ **NEVER DONE BEFORE**

**POWER: both ON.**

> ### 🔴 This is the genuinely unproven step. Treat it as an experiment.
>
> `web/server.py`'s own docstring marks `--serial` as **"designed, NOT
> proven"**. Every web screenshot in `ai/evidence/` to date — the four-tab
> shell, the 60 fps fingerprint, the LIVE spectrum, the LAB insights — came
> from a **recorded fixture replayed from disk**. The Tk UI held the UART
> throughout.
>
> **No browser on this Pi has ever rendered a live Teensy frame.** Expect
> defects here, and budget time for them rather than for polish.

**Prerequisites:** Stages 4 and 5 passed; UART confirmed free.

**Steps**

1. Server only first, no browser — isolate the transport from the renderer:
   ```sh
   cd ~/gra-webtest/pi
   sh run_web.sh --serial /dev/ttyAMA0 --no-browser --host 0.0.0.0
   ```
2. From the **Mac**, confirm real frames are being produced:
   ```sh
   curl -s http://guitar-rig-analyzer.local:8711/api/frame | head -c 400
   ```
   Look for `"kind":"live"` and a `link` block whose `frames_in` **increases**
   between two calls.
3. Only once that works, add the browser (on the Pi, over SSH):
   ```sh
   sh run_web.sh --serial /dev/ttyAMA0
   ```

**Expected observation:** `"kind":"live"`, `"stale":false`, `frames_in` rising,
`decode_errors: 0`, and a `session` id. In the kiosk, the status strip reads
**LINK UP** and the LIVE spectrum moves when the guitar is played.

**Failure response**

| Symptom | Response |
|---|---|
| `"kind":"unknown"`, *"no HELLO yet"* | The receiver has bytes but no HELLO. HELLO re-announces every ~1 s, so waiting a few seconds is correct; a persistent absence is a real finding |
| `decode_errors` climbing | Record the count and go back to a **raw capture** (Stage 4). Decode errors against live bytes with a clean raw capture is exactly the firmware-agreement evidence this project has never had |
| `frames_in` static | The server is up and nothing is arriving. The UART was free; something else changed |
| Kiosk shows a modal dialog | The gnome-keyring prompt. `run_web.sh` already passes `--password-store=basic --use-mock-keychain`. **If a dialog appears anyway, you cannot dismiss it without a keyboard** — kill the browser over SSH |
| Server dies on start | `SerialSource` shells out to `stty` and opens `O_RDONLY`. A `CalledProcessError` means the device rejected the settings; capture the traceback verbatim |

**Evidence to preserve:** two `/api/frame` responses a few seconds apart showing
`frames_in` rising; `grim` screenshot of the panel; the server's stderr. **If
this works, it is the first live-rendered frame in the project's history and
deserves its own evidence file.**

---

## Shutting down cleanly

```sh
# stop whatever you started, then:
sudo shutdown -h now
```
Wait for the activity LED to stop before removing power. Power the Teensy down
separately; it has no filesystem to corrupt but a clean sequence keeps the
session log honest.

---

## Rollback — everything this project added to the Pi, and how to remove it

| Added | Remove with | Effect |
|---|---|---|
| `~/.config/labwc/autostart` (**now the kiosk line**) | `sh ~/gra-rollback/restore-tk-startup.sh` to go back to **Tk**, or `rm ~/.config/labwc/autostart` for **nothing** at boot | The script restores the Tk file byte-for-byte and verifies the hash both sides. `rm` leaves only the untouched system file. 🔺 **Exercised for real on 2026-10-15** before the migration reboot — not merely written |
| Kiosk at boot, without restoring Tk | `touch ~/gra-ui/DISABLE_KIOSK_AUTOSTART` | Supervisor exits immediately on the next boot. Needs no root and no file editing |
| `~/gra-ui` (**the production deployment**) | `rm -rf ~/gra-ui` | 🛑 **Roll the autostart back FIRST.** Deleting this while the kiosk line is installed leaves boot with nothing to run — the supervisor itself lives here, so even the Tk fallback is gone |
| `~/gra-webtest`, `~/gra-stage-cc994de`, `~/gra-stage-todo82` | `rm -rf` each | Scratch trees from the 2026-10-12/13 sessions. **Nothing boots from these.** The Pi's own checkout is unaffected |
| `~/gra-rollback` | leave it | The way back. Removing it removes the recovery path |
| Chromium kiosk profile | `du -sh /tmp/gra-kiosk.*`, then `rm -rf` the ones you have confirmed belong to no running kiosk | 🔺 **CORRECTED 2026-10-13.** This row used to read *"nothing — deletes it on exit"*. It did not: `exec` destroyed the trap (TODO-82), and two launches leaked **171 MB**. Fixed in `run_web.sh`, so launches from 2026-10-13 onward do clean up after themselves — but **anything left by an earlier launch is still there** |

🔺 **A rollback table that is wrong is worse than one that is missing**, because it is what an operator consults *instead of* checking. The row above was believed for a day and was false for the whole of it. Verify a rollback claim before relying on it.

**No system file has ever been modified.** `/etc/xdg/labwc/autostart` is
root-owned and unchanged, sha256
`3a53212ad85afb47ef60ebb66c5a6c911cba210ff5577492acfafa2c68edb719` — verify it
before and after any session that touches autostart.

---

## What this procedure does **not** do

**It does not touch the breadboard, the wiring, the firmware or the routing.**
Every stage above is Pi-side and software-side. The bench work has its own
sequence and its own blockers, and they are not advanced by anything here:

- **TODO-75** — the grounded-probe floor on the DHO804, still unrecorded. It
  gates **every amplitude claim** at J8.
- **TODO-70** — the controlled RETURN→SOURCE leak test, live since 2026-10-12
  and the highest-value measurement currently available. Until it runs, some
  fraction of SOURCE may be RETURN leaking through the shared `OPA_BIAS` node,
  which would **inflate SOURCE and understate the loss** in the flattering
  direction.
- **TODO-78** — re-baseline SOURCE and RETURN under the corrected C10
  topology. Every level measured before 2026-10-12 was taken through a ≈1.59 kΩ
  shunt instead of the intended ≈101.6 kΩ.

**It does not resolve the volume problem.** The 2026-10-05 symptom — severe
volume loss with audible guitar, versus the same guitar direct into the
Headrush — is **still unexplained**. The diagnostic jumper that was shorting the
input is gone and the C10 fault is repaired, and the path is now audible
end-to-end, but *audible* is `OBS` from a human ear at low volume. It is not a
level measurement and it does not close that investigation. If the volume
symptom recurs, it is a bench question, not a Pi question, and it should not be
diagnosed from the UI.

**A GOOD quality grade is a target, not a prerequisite.** A POOR result whose
cause you identified, changed one variable against, and documented is stronger
portfolio evidence than a GOOD grade you cannot explain.
