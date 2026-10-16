#!/bin/sh
# Boot-time supervisor for the production web kiosk. Started by labwc autostart.
#
#   ~/.config/labwc/autostart:
#       /home/conley/gra-ui/pi/run_kiosk_boot.sh &
#
# *** THIS IS THE AUTOSTART. `run_web.sh` IS STILL THE LAUNCHER. ***
#
# ADR-005 §2 makes the web client the production default once it can, on the Pi:
# boot into Chromium; connect to analyzer_link; render real protocol-v2 frames;
# and survive disconnect and reconnect. The last three were met on 2026-10-13
# and 2026-10-15 (ai/evidence/2026-10-15-pi-web-disconnect-reconnect.md). This
# script exists to meet the first WITHOUT re-implementing any of the launcher
# behaviour that was proven getting there — it calls `run_web.sh` and adds only
# what boot needs: waiting for the compositor, bounded retries, and a fallback.
#
# *** IT MUST NEVER BECOME A RESTART LOOP. ***
#
# The 2026-09-30 operator decision deliberately refused `lwrespawn` for the Tk
# autostart, for reasons that apply unchanged here:
#   - terminating the UI must free /dev/ttyAMA0 for diagnostics;
#   - a crashing application must not enter a restart loop;
#   - this is a development instrument, not a locked-down appliance.
# So retries are bounded AND scoped to STARTUP ONLY: a kiosk that came up and
# ran is never restarted when it exits, because by then the exit is an
# operator's deliberate teardown and restarting would fight them for the UART.
# See RAN_THRESHOLD below, which is the whole of that distinction.
#
# Standard library only, POSIX sh, no new dependency.
set -u

cd "$(dirname "$0")"

SERIAL="${GRA_SERIAL:-/dev/ttyAMA0}"
PORT="${GRA_PORT:-8711}"
PREFER="${GRA_PREFER:-live}"
MAX_TRIES="${GRA_MAX_TRIES:-3}"
RAN_THRESHOLD="${GRA_RAN_THRESHOLD:-60}"   # seconds; see below
LOG="${GRA_BOOT_LOG:-$HOME/gra-ui-boot.log}"
TK_LAUNCHER="${GRA_TK_LAUNCHER:-$HOME/guitar_rig_analyzer/pi/run_ui.sh}"
DISABLE="${GRA_DISABLE_FLAG:-$HOME/gra-ui/DISABLE_KIOSK_AUTOSTART}"

log() { printf '%s  %s\n' "$(date +%Y-%m-%dT%H:%M:%S%z)" "$*" >> "$LOG" 2>/dev/null; }

log "=== boot supervisor starting (pid $$) ==="

# --- an escape hatch that needs no file editing --------------------------------
#
# `touch ~/gra-ui/DISABLE_KIOSK_AUTOSTART` over SSH stops the kiosk taking the
# panel on the next boot, without touching autostart and without root. The
# rollback script is still the way to put the Tk UI BACK; this only gets the
# kiosk out of the way.
if [ -e "$DISABLE" ]; then
  log "disable flag present ($DISABLE) — not starting the kiosk"
  exit 0
fi

# --- one supervisor, not two ---------------------------------------------------
#
# `mkdir` is the atomic test-and-set; a lock FILE plus `[ -e ]` is a race. labwc
# runs the user autostart once, but a hand-launched copy over SSH must not end up
# fighting the booted one for the port and the UART.
LOCK="${XDG_RUNTIME_DIR:-/tmp}/gra-kiosk-boot.lock"
if ! mkdir "$LOCK" 2>/dev/null; then
  log "another supervisor holds $LOCK — exiting without starting anything"
  exit 0
fi
release_lock() { rmdir "$LOCK" 2>/dev/null || true; }
trap 'release_lock' EXIT
trap 'log "SIGINT";  release_lock; exit 130' INT
trap 'log "SIGTERM"; release_lock; exit 143' TERM

# --- wait for the compositor, bounded ------------------------------------------
#
# labwc runs its autostart as the session comes up, so at boot the Wayland socket
# can be a moment behind this script. `run_web.sh` discovers the socket too, but
# it EXITS if there is none — which at boot would burn a retry on a race rather
# than a fault. Waiting here makes the retries mean "the kiosk failed", not "the
# session was not ready yet".
: "${XDG_RUNTIME_DIR:=/run/user/$(id -u)}"
export XDG_RUNTIME_DIR

have_socket() {
  [ -n "${WAYLAND_DISPLAY:-}" ] && [ -S "$XDG_RUNTIME_DIR/$WAYLAND_DISPLAY" ]
}

i=0
while [ "$i" -lt 60 ]; do                      # 60 × 0.5 s = 30 s
  have_socket && break
  for s in "$XDG_RUNTIME_DIR"/wayland-*; do
    case "$s" in *.lock) continue ;; esac
    [ -S "$s" ] || continue
    WAYLAND_DISPLAY="$(basename "$s")"
    export WAYLAND_DISPLAY
    break
  done
  have_socket && break
  i=$((i + 1))
  sleep 0.5
done

if have_socket; then
  log "compositor socket: \$XDG_RUNTIME_DIR/$WAYLAND_DISPLAY (after $((i * 500)) ms)"
else
  log "no Wayland socket after 30 s — the kiosk cannot open a window"
  log "falling back to the Tk UI, which is an X client and brings up Xwayland itself"
  i="$MAX_TRIES"                               # skip straight to the fallback
fi

# --- clear OUR OWN orphan, and nothing else ------------------------------------
#
# A transport orphaned by a failed attempt would hold both :PORT and the UART, so
# every later retry would hit `run_web.sh`'s port guard and the Tk fallback would
# find the UART busy too. Scope is deliberately narrow: our uid, a `web.server`
# command line, and OUR port. Anything else is somebody's deliberate run and is
# left alone — a blanket sweep here would be the TODO-83 mistake again.
clear_our_orphan() {
  for d in /proc/[0-9]*; do
    pid="${d#/proc/}"
    [ "$pid" = "$$" ] && continue
    [ -O "$d" ] || continue                                  # our uid only
    c="$(tr '\0' ' ' < "$d/cmdline" 2>/dev/null)" || continue
    case "$c" in
      *"web.server"*"--port $PORT"*)
        log "clearing orphaned transport pid $pid: $c"
        kill "$pid" 2>/dev/null || true
        n=0
        while [ "$n" -lt 50 ] && [ -e "$d" ]; do n=$((n + 1)); sleep 0.1; done
        [ -e "$d" ] && { log "orphan $pid ignored SIGTERM — SIGKILL"; kill -9 "$pid" 2>/dev/null || true; sleep 0.5; }
        ;;
    esac
  done
}

# --- bounded startup retries ---------------------------------------------------
#
# 🛑 RAN_THRESHOLD IS THE LINE BETWEEN A SUPERVISOR AND A RESTART LOOP.
#
# `run_web.sh` returns when the browser exits. Two very different things produce
# that return:
#
#   (a) it never came up          -> returns in a few seconds   -> RETRY
#   (b) it came up and ran, then an operator killed it to free the UART, or it
#       crashed after a long healthy run
#                                 -> returns after >= RAN_THRESHOLD -> STOP
#
# Restarting case (b) would seize /dev/ttyAMA0 back from whoever just freed it,
# which is exactly the behaviour the 2026-09-30 decision refused. So a kiosk that
# ran for a minute and then exited is treated as a deliberate end, and this
# script exits with it.
try=0
while [ "$try" -lt "$MAX_TRIES" ]; do
  try=$((try + 1))
  clear_our_orphan

  log "attempt $try/$MAX_TRIES: run_web.sh --serial $SERIAL --prefer $PREFER --port $PORT"
  started="$(date +%s)"
  sh run_web.sh --serial "$SERIAL" --prefer "$PREFER" --port "$PORT" >> "$LOG" 2>&1
  rc=$?
  ran=$(( $(date +%s) - started ))
  log "run_web.sh exited rc=$rc after ${ran}s"

  if [ "$ran" -ge "$RAN_THRESHOLD" ]; then
    log "the kiosk ran for ${ran}s before exiting — treating this as a deliberate"
    log "teardown, NOT a startup failure. Not restarting; the UART is left free."
    exit 0
  fi

  if [ "$try" -lt "$MAX_TRIES" ]; then
    backoff=$((try * 3))
    log "startup failure — retrying in ${backoff}s"
    sleep "$backoff"
  fi
done

# --- the documented fallback: never leave the panel blank ----------------------
#
# There is no keyboard on this Pi. A kiosk that will not start must not leave an
# empty desktop, because the only way back in would be SSH from a Mac that may
# not be running. The Tk UI is the reference renderer (ADR-005 §2), it is
# bench-proven, and it is launched here from the Pi's OWN CHECKOUT — which is
# exactly what boot used to run, so the fallback state is the previous known-good
# state and not some third configuration nobody has seen.
log "all $MAX_TRIES startup attempts failed"
clear_our_orphan

held=""
for d in /proc/[0-9]*; do
  for f in "$d"/fd/*; do
    case "$(readlink "$f" 2>/dev/null)" in
      */ttyAMA0) held="$held ${d#/proc/}" ;;
    esac
  done
done 2>/dev/null
if [ -n "$held" ]; then
  log "WARNING: /dev/ttyAMA0 still held by pid(s)$held — Tk will start WITHOUT serial"
  log "falling back to the Tk UI on the pinned fixture so the panel is not blank"
  release_lock
  exec sh "$TK_LAUNCHER"
fi

if [ -x "$TK_LAUNCHER" ]; then
  log "falling back to the Tk UI: $TK_LAUNCHER --serial $SERIAL"
  release_lock
  exec sh "$TK_LAUNCHER" --serial "$SERIAL"
fi

log "FALLBACK UNAVAILABLE: $TK_LAUNCHER is not executable. The panel will be empty."
log "Recover over SSH:  sh ~/gra-rollback/restore-tk-startup.sh"
exit 1
