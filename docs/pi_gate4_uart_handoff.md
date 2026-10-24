# Gate 4 — handing `/dev/ttyAMA0` from the Tk UI to the web client

**Written 2026-10-13 after Gates 0–3 passed.** It is the procedure for the one
step ADR-005 §2 condition 2 has never cleared: a browser on this Pi rendering a
live Teensy frame.

**Execution state: §1 has been run and passed (2026-10-13 ~20:45, `e81b16d`,
journal 2026-10-13 (6)). §2 onward has NOT been run.** Each section says so at
its head; do not assume a section is proven because the one above it is.

Companion to [`pi_resume_from_cold.md`](pi_resume_from_cold.md), which covers
getting from cold to a trustworthy link. This covers the handoff itself.

---

## What is already established, so it is not re-litigated here

| | |
|---|---|
| Staged code | `/home/conley/gra-stage-todo82`, sha256-identical to the Mac, **505 tests green on the Pi** |
| Fixture rendering | All four views on the physical panel, touch navigation in three directions, swipe-to-orbit by finger |
| Launcher lifecycle | `b10cc67` — supervisor shell, bounded shutdown, port guard, profile cleanup. Verified on the hardware |
| UART ownership | Tk, pid 1505, `fd 3 -> /dev/ttyAMA0`, `O_RDONLY`, sole holder |
| Privilege | **No `sudo` anywhere in this procedure.** `conley` is in `dialout`; `sudo` needs a password and cannot be used non-interactively |

## 🛑 Five standing rules for this gate

1. **Descriptor ownership is the observation; process liveness is commentary.**
   `ps -p` and `kill -0` both report a zombie as running. The question "is the
   UART free?" is answered by `ls -l /proc/*/fd | grep ttyAMA0` and nothing else.
2. **Never `pkill -f`.** Three login sessions are typically open on this box, and
   an unanchored pattern reaches into all of them. Every process started here
   writes a pidfile and is stopped by that pid.
3. **Rehearse the recovery before you need it** (§1). Discovering that the Tk
   relaunch does not work *after* giving up the UART is the one failure this
   procedure exists to prevent.
4. **Capture evidence while the state exists.** The first live-rendered frame in
   this project's history is not reproducible on demand.
5. **A reboot always works.** Both autostart files are unmodified, so
   `sudo reboot` (interactive password) restores Tk exactly as it is now. That
   is the floor under every step below.

---

## §1 — Rehearse the rollback **without touching the UART**

**This is the most important stage and it is free.** The documented recovery —
relaunching Tk over SSH — has **never been run**. [`run_ui.sh`](../pi/run_ui.sh)
has no Wayland/X socket discovery (only `run_web.sh` does), and Tk draws through
XWayland, so an SSH session that inherits no `DISPLAY` is the obvious failure.

It can be proven in advance, because **a second Tk instance backed by a fixture
needs no serial port at all**:

> ## ✅ EXECUTED AND PASSED — 2026-10-13, ~20:45, repository `e81b16d`
>
> Journal 2026-10-13 (6). The command below is the one that **actually worked**,
> not the one originally drafted here. **Do not reconstruct it from memory;
> re-derive it from the live process as step 1 does.**

**Step 1 — read the display environment, do not assume it.** The authority is the
process that is drawing on the panel right now:

```sh
tr '\0' '\n' < /proc/1505/environ | grep -E '^(DISPLAY|WAYLAND_DISPLAY|XDG_RUNTIME_DIR|XAUTHORITY)='
pgrep -af -i xwayland          # confirm the X server exists and how it was started
ls -la /tmp/.X11-unix/         # confirm the socket
python3 -c "import tkinter; print(tkinter.TkVersion)"
```

Observed 2026-10-13: `DISPLAY=:0`, `XAUTHORITY=/home/conley/.Xauthority`,
`XDG_RUNTIME_DIR=/run/user/1000`, `WAYLAND_DISPLAY=wayland-0`; Xwayland pid 1568
running **`-auth /home/conley/.Xauthority :0`**; socket `X0`; Tk 8.6.

🔺 **`XAUTHORITY` was missing from the first draft of this procedure.** The X
server runs with authority enabled, and while an X client defaults to
`$HOME/.Xauthority` and would probably have connected anyway, *probably* is not
a recovery path. This is why step 1 reads rather than assumes.

**Step 2 — launch, with all four variables taken verbatim:**

```sh
cd ~/gra-stage-todo82
setsid nohup env DISPLAY=:0 \
                XAUTHORITY=/home/conley/.Xauthority \
                XDG_RUNTIME_DIR=/run/user/1000 \
  sh pi/run_ui.sh --fixture ../ai/evidence/phase10-result-1khz.bin \
  >/tmp/tk-rehearsal.log 2>&1 &
echo $! > /tmp/tk-rehearsal.pid
sleep 8
cat /tmp/tk-rehearsal.log
ls -l /proc/$(cat /tmp/tk-rehearsal.pid)/fd
WAYLAND_DISPLAY=wayland-0 XDG_RUNTIME_DIR=/run/user/1000 grim /tmp/gate4-01-tk-rehearsal.png
```

**Expected observation:** a second Tk window on the panel, drawing the fixture,
holding **no** serial descriptor. Pid 1505 untouched throughout.

**🛑 A started process is not a window.** Verify from the capture, by the three
things that discriminate the rehearsal from production: the header reads
**`fixture:phase10-result-1khz.bin`** not `serial:/dev/ttyAMA0`, the session is
the fixture's (**7**) not the live one, and the link block shows a large *lead*
discard with **interior 0** — the signature of attaching to a recorded stream
mid-file. Observed 2026-10-13: `306 frames ok · discarded 1598 (lead 1598,
interior 0)`, descriptors `/dev/null`, two log fds, **one X11 socket**, two
pipes, and no serial device anywhere.

**Failure response**

| Symptom | Response |
|---|---|
| `couldn't connect to display ":0"` | Try `DISPLAY=:1`, then `ls /tmp/.X11-unix/`. **Resolve it here.** This is the whole point of the rehearsal |
| No window, no error | Check `/tmp/tk-rehearsal.log`. A Tk import failure is a staging problem, not a display one |
| It works | **Record the exact command that worked.** That string is the rollback for the rest of the session |

🔺 **Counting processes: use `pgrep -af`, never `pgrep -c`.** On 2026-10-13
`pgrep -c analyzer_ui` returned **0** while `pgrep -af analyzer_ui` printed pid
1505 — `-c` without `-f` matches the process *name*, which is `python3`, not the
command line. A count taken that way reads as "Tk is gone" at the exact moment
that misreading is most expensive. Count descriptor holders instead; that is the
question actually being asked.

Then stop it by pid and confirm the original is unaffected:

```sh
kill "$(cat /tmp/tk-rehearsal.pid)"; sleep 2
ps -p "$(cat /tmp/tk-rehearsal.pid)" >/dev/null 2>&1 && echo "STILL RUNNING" || echo "rehearsal stopped"
pgrep -af analyzer_ui          # expect: 1505 only
ls -l /proc/1505/fd | grep ttyAMA
```

**Do not proceed to §3 until this stage has passed.** If Tk cannot be relaunched
over SSH, the only recovery is a reboot — which is acceptable, but you must know
that *before* you give up the port, not after.

---

## §2 — Baseline, immediately before the handoff

```sh
pgrep -af analyzer_ui
ls -l /proc/1505/fd | grep ttyAMA
for p in $(ls /proc | grep -E '^[0-9]+$'); do
  ls -l /proc/$p/fd 2>/dev/null | grep -q ttyAMA0 && echo "ttyAMA0 held by $p ($(tr -d '\0' </proc/$p/comm))"
done
ss -ltnp 2>/dev/null | grep 8711 || echo "8711 free"
vcgencmd get_throttled; vcgencmd measure_temp
sha256sum /etc/xdg/labwc/autostart ~/.config/labwc/autostart
WAYLAND_DISPLAY=wayland-0 XDG_RUNTIME_DIR=/run/user/$(id -u) grim /tmp/gate4-02-tk-before.png
```

**Record the Tk panel's link block verbatim** — session id, `frames ok`,
`CRC fail`, `discarded (lead / interior)`. Those are the last numbers from the
proven renderer, and every claim about the web client's reception is relative
to them.

**Expected:** `3a53212a…` / `b40fbc70…`, `throttled=0x0`, one holder, port free.

**Stop if:** anything other than 1505 holds the UART, or either autostart hash
has changed.

---

## §3 — The handoff

```sh
kill 1505
sleep 3
pgrep -af analyzer_ui || echo "Tk stopped"
for p in $(ls /proc | grep -E '^[0-9]+$'); do
  ls -l /proc/$p/fd 2>/dev/null | grep -q ttyAMA0 && echo "STILL HELD by $p"
done; echo "-- sweep complete: no output above means 0 descriptors --"
```

**Expected:** no `analyzer_ui`; **zero** descriptors on `ttyAMA0`; the desktop
on the panel. Proven 2026-09-30: the UART goes to 0 fds and the process does not
respawn, because the autostart line is deliberately not `lwrespawn`-wrapped.

**Failure response**

| Symptom | Response |
|---|---|
| A descriptor survives the process | A stale fd. **Stop** — it is a real defect and nothing downstream is interpretable |
| The process returns by itself | Something wrapped it. Inspect `~/.config/labwc/autostart` before anything else |
| You want Tk back right now | The command recorded in §1, with `--serial /dev/ttyAMA0` instead of `--fixture` |

**Evidence:** the before and after descriptor sweeps. *"The UART was free"* is a
claim; `0` is an observation.

---

## §4 — Raw bytes first, no renderer

> ## ✅ EXECUTED AND PASSED — 2026-10-13 20:57:48, repository `a5c2319`
>
> `15s of 15s · 547 219 B · **36 481 B/s** · sha256 e90f74a4…580a`
> `frames ok 382 · CRC failures 0 · oversize 0 · discarded 1532 (lead 1532, **interior 0 in 0 events**) · decode_errors 0 · session 47`
> Evidence: [`2026-10-13-gate4-raw-uart-15s.md`](../ai/evidence/2026-10-13-gate4-raw-uart-15s.md)
> and the capture beside it. Journal 2026-10-13 (9).

**Preconditions:** zero UART holders by full `/proc` sweep; no Tk, web server or
Chromium running; the rollback script present.

```sh
pinctrl get 14,15      # expect: GPIO14 = TXD0 / GPIO15 = RXD0
```

🔺 **`raspi-gpio` is NOT installed on this Pi.** The older procedure prescribes
it, the command failed mid-gate on 2026-10-13, and **a precondition that cannot
be run is worse than one that is absent** — it reads as a failure. `pinctrl` is
its replacement on current Raspberry Pi OS and is present here; `gpioinfo` is too.
Observed 2026-10-13: `14: a4 pn | hi // GPIO14 = TXD0`, `15: a4 pu | hi //
GPIO15 = RXD0`. This check is **diagnostic for a zero-byte capture**, not a gate
— if bytes arrive at the nominal rate, the pins are evidently right.

```sh
cd ~/gra-stage-todo82/pi
sh tools/capture.sh /dev/ttyAMA0 15 /tmp/gate4-raw-$(date +%H%M%S).bin
sha256sum /tmp/gate4-raw-*.bin
python3 tools/replay.py /tmp/gate4-raw-*.bin
```

**No `sudo`** — `dialout` membership covers it, and the `sudo` in
`pi_resume_from_cold.md` §4 is unnecessary on this machine.

**Expected:** 15 s elapsed, ≈**547 kB**, ≈**36 500 B/s**. The 2026-09-26
hardware measurement was 36 465 B/s; 2026-10-13 gave 36 481 B/s. The script
checks its own duration.

**Acceptance is `CRC failures 0` and `interior 0`, not a particular leading
discard.** A non-zero *leading* discard is expected when attaching mid-stream
and is attach loss, not corruption — but opening near a frame boundary can
legitimately give zero, so its magnitude is not a criterion and its presence is
not required. Interior discards and CRC failures are findings and must be
investigated, never written off as startup artefacts.

**Why before the renderer:** it separates "the link is bad" from "the Pi-side
read cadence is bad". Without it those two produce the same symptom and you will
spend the evening guessing.

---

## §5 — The cadence measurement ⚠️ **the open question**

The web transport pumps the serial port **only when an HTTP request arrives**
([`server.py:48-51`](../pi/web/server.py#L48-L51) — no background reader), and
the client polls every 500 ms ([`main.js:20`](../pi/web/static/main.js#L20)). Tk
reads every 50 ms and loses nothing across 89 794 frames. Whether a 500 ms gap
survives the kernel's buffering **is a hypothesis and has never been measured.**

`/api/frame` cannot answer it: requesting it *is* an acquisition, so the probe
perturbs the measurement, and the payload carries no Teensy timebase, so lag is
invisible. The measurement therefore happens at the device, with the production
classes, reporting the counters HTTP does not expose:

```sh
cat > /tmp/pump_cadence.py <<'PY'
"""What a request-driven pump absorbs at a given cadence.

Production SerialSource and FrameScanner, unchanged. Measurement only: renders
nothing, writes nothing, transmits nothing.
"""
import sys, time
from analyzer_ui.sources import SerialSource
from analyzer_link import framing

cadence_ms, seconds = float(sys.argv[1]), float(sys.argv[2])
src = SerialSource("/dev/ttyAMA0")

# Settle: drain what queued while the port was closed, and let the scanner's
# lead-in discard happen OUTSIDE the window. Without this, attach backlog is
# counted as throughput and the first read is meaninglessly large.
t = time.monotonic()
while time.monotonic() - t < 1.0:
    src.read(); time.sleep(0.01)

scan = framing.FrameScanner()
t0 = time.monotonic(); series = []
while time.monotonic() - t0 < seconds:
    data = src.read()
    series.append(len(data))
    scan.feed(data)
    time.sleep(cadence_ms / 1000.0)
el = time.monotonic() - t0; src.close(); s = scan.stats
total = sum(series); due = cadence_ms / 1000.0 * 36483

print(f"cadence_ms       {cadence_ms:.0f}   window_s {el:.2f}   reads {len(series)}")
print(f"bytes_per_sec    {total/el:.0f}          arrival rate is 36483")
print(f"capture_fraction {total/el/36483*100:.1f}%     <-- 100% = nothing lost")
print(f"bytes_per_read   mean {total/len(series):.0f}  max {max(series)}  min {min(series)}"
      f"   due/read {due:.0f}")
print(f"frames_ok        {s.frames_ok} = {s.frames_ok/el:.1f}/s    expect ~21.5/s")
print(f"crc_failures     {s.crc_failures}")
print(f"discard_leading  {s.bytes_discarded_leading}")
print(f"discard_interior {s.bytes_discarded_interior}  events {s.interior_discard_events}")
print(f"first_12_reads   {series[:12]}")
PY

cd ~/gra-stage-todo82/pi
python3 /tmp/pump_cadence.py 500 20     # the web client's cadence
sleep 5                                 # port closed, queue clears
python3 /tmp/pump_cadence.py  50 20     # Tk's proven cadence
```

**Read four numbers together, not one:**

| Observation | Conclusion |
|---|---|
| `capture_fraction` ≈100 % at **both** cadences, `discard_interior 0` | **Hypothesis refuted.** Kernel buffering absorbs the gap. Proceed unmodified and record the refutation |
| ≈100 % at 50 ms, materially lower at 500 ms | **Loss confirmed.** The deficit *is* the loss; `crc_failures` and `discard_interior` name the mechanism |
| Low at **both** | Not a cadence problem. §4 already told you whether the link is healthy |

**If loss is confirmed**, the bench workaround is a keeper process that pumps at
Tk's proven cadence — **a bench instrument, not a design**, which must be named
in any evidence file that depends on it:

```sh
setsid nohup python3 -c "
import time, urllib.request
while True:
    try: urllib.request.urlopen('http://127.0.0.1:8711/api/frame', timeout=1).read()
    except Exception: pass
    time.sleep(0.05)
" >/dev/null 2>&1 &
echo $! > /tmp/gra-keeper.pid
```

It adds no data and changes no value; it only drains the UART more often. **The
real fix is a daemon thread in `FrameService` pumping on its own clock**, so the
renderer's poll rate stops being the acquisition rate. That is a reviewed commit
for a day when nothing is riding on it.

---

## §6 — Transport only, then the panel

```sh
cd ~/gra-stage-todo82/pi
setsid nohup python3 -m web.server --serial /dev/ttyAMA0 --prefer live \
  --host 0.0.0.0 --port 8711 >/tmp/gate4-srv.log 2>&1 &
echo $! > /tmp/gate4-srv.pid
sleep 3; cat /tmp/gate4-srv.log
ls -l /proc/$(cat /tmp/gate4-srv.pid)/fd | grep ttyAMA   # expect: it now holds it
```

`--prefer live` is not optional for a filmed run: with `auto`, the first RESULT
latches permanently ([`server.py:59-60`](../pi/web/server.py#L59-L60) — `snap.result`
is sticky) and the LIVE tab would go blank mid-take.

`--host 0.0.0.0` exposes an **unauthenticated panel on the LAN**. Acceptable on a
home network for a bench session; revert to the default afterwards.

From the Mac, as a **liveness check, not a rate measurement**:

```sh
curl -s http://guitar-rig-analyzer.local:8711/api/frame |
  python3 -c "import sys,json;d=json.load(sys.stdin);print(d['kind'],d['link'])"
```

**Expected:** `"kind":"live"`, `"stale":false`, a session id, `decode_errors 0`,
`frames_in` rising.

| Symptom | Response |
|---|---|
| `"kind":"unknown"`, *"no HELLO yet"* | HELLO re-announces ~1 s. Wait 5 s. A persistent absence is a real finding |
| `decode_errors` climbing | Stop and go back to §4. Decode errors against live bytes *with a clean raw capture* is the firmware-agreement evidence this project has never had |
| `CalledProcessError` on start | `stty` rejected the device. Capture the traceback verbatim |

Then the kiosk — **one pidfile, because `b10cc67` made the launcher a real
supervisor**:

```sh
kill "$(cat /tmp/gate4-srv.pid)"; sleep 2        # free 8711 for the launcher
cd ~/gra-stage-todo82/pi
setsid nohup sh run_web.sh --serial /dev/ttyAMA0 --prefer live \
  >/tmp/gate4-kiosk.log 2>&1 &
echo $! > /tmp/gate4-kiosk.pid
```

Teardown is now a single `kill "$(cat /tmp/gate4-kiosk.pid)"`; the trap stops the
transport, reaps both children and removes the profile. **Verify it anyway** with
the descriptor sweep — the launcher's own report is not the observation.

**Evidence to preserve, while the state exists:** two `/api/frame` responses
seconds apart with `frames_in` rising; a `grim` capture of the panel; the server
log; the §4 capture and its sha256. **If this works it is the first live-rendered
frame in the project's history and ADR-005 §2 condition 2 moves from 🟡 to ✅.**

---

## Rollback

| Tier | Action | Certainty |
|---|---|---|
| 1 | `kill "$(cat /tmp/gate4-kiosk.pid)"`, sweep descriptors, then the §1 command with `--serial /dev/ttyAMA0` | High **once §1 has passed**. Unproven until then |
| 2 | `sudo reboot` (interactive password) | **Certain.** Both autostart files are unmodified |
| 3 | `rm -rf ~/gra-stage-todo82` | Removes every trace of this work |

---

## 🔺 Risks specific to this gate

**1 — A Teensy restart mid-take, and the path it would exercise.** On 2026-10-13
the session went 46 → 47 unprompted, probably associated with a bench repair but
**cause unconfirmed** (journal 2026-10-13 (5)). **ADR-005 §2 condition 4 —
survive disconnect and reconnect — has never been tested.** A restart during
filming would exercise exactly that untested path, on camera. It is also an
opportunity: if it happens, *capture it* rather than restarting everything.

**2 — Mac sleep could take the instrument down.** The Mac entered clamshell
sleep at 19:04 tonight, and the Teensy's USB dropped three times. **Whether the
Teensy is powered solely from that cable is still unanswered** — if it is, that
cable also feeds the breadboard's +5 V rail, and the Mac sleeping mid-take kills
the instrument. Until it is answered, run `caffeinate -dimsu` on the Mac for the
duration of any filmed session. It costs nothing.

**3 — The transport can outlive its browser if the supervisor is `SIGKILL`ed.**
A trap cannot run on `SIGKILL`. The port guard refuses the next launch and names
the occupant, including whether it holds a serial device — but the descriptor
sweep is what makes it visible. Never conclude the UART is free from `ps`.

**4 — Longest web run on record is ~25 s.** Filming needs minutes. Untested.

**5 — Vertical scrolling on LIVE is unverified by touch.** The view is taller
than the panel. Find out before the camera is running.
