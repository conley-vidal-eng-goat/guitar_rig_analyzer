#!/bin/sh
# Launch the web client: the UI transport plus Chromium in kiosk mode.
#
#   sh pi/run_web.sh                      # replay the real 1 kHz RESULT capture
#   sh pi/run_web.sh --serial /dev/ttyAMA0  # live, receive-only
#   sh pi/run_web.sh --diag               # display/GPU diagnostics page instead
#   sh pi/run_web.sh --no-browser         # server only; connect from elsewhere
#   sh pi/run_web.sh --host 0.0.0.0       # serve on the LAN (see the warning)
#
# *** THIS IS NOT AUTOSTART, AND MUST NOT BECOME IT YET. ***
#
# ADR-005 §2 makes the web client the production default only after it can, on
# the Pi: boot into Chromium; connect to analyzer_link; render real protocol-v2
# frames; and survive disconnect and reconnect. Until all four hold, the Tk UI
# is what ships. This script exists to TEST those conditions, not to assume
# them. It does not read, write or create ~/.config/labwc/autostart, and the Tk
# autostart installed by d4eca26 is left exactly as it is.
#
# *** DESIGNED TO BE RUN OVER SSH, BECAUSE THE PI HAS NO KEYBOARD. ***
#
# Launching a GUI client from an SSH session needs the compositor's socket,
# which an SSH environment does not inherit. The WAYLAND block below finds it
# rather than assuming it, and says so when it cannot.
#
# Standard library only on the Python side. No pip, no npm, no build step, and
# no network access: three.js is vendored under static/vendor/.
set -eu

cd "$(dirname "$0")"

FIXTURE="../ai/evidence/phase10-result-1khz.bin"
HOST="127.0.0.1"
PORT="8711"
PAGE="/"
BROWSER=1
SRC_ARGS=""
PREFER=""

while [ $# -gt 0 ]; do
  case "$1" in
    --serial)     SRC_ARGS="--serial $2"; shift 2 ;;
    --fixture)    SRC_ARGS="--fixture $2"; shift 2 ;;
    --prefer)     PREFER="--prefer $2"; shift 2 ;;
    --host)       HOST="$2"; shift 2 ;;
    --port)       PORT="$2"; shift 2 ;;
    --diag)       PAGE="/diag.html"; shift ;;
    --no-browser) BROWSER=0; shift ;;
    -h|--help)    sed -n '2,28p' "$0"; exit 0 ;;
    *)            echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done

[ -n "$SRC_ARGS" ] || SRC_ARGS="--fixture $FIXTURE"

case "$HOST" in
  127.0.0.1|localhost) ;;
  *) echo "[web] ⚠  binding $HOST — this panel is not authenticated." >&2 ;;
esac

URL="http://${HOST}:${PORT}${PAGE}"
[ "$HOST" = "0.0.0.0" ] && URL="http://127.0.0.1:${PORT}${PAGE}"

# --- refuse to start against somebody else's transport -----------------------
#
# TODO-82. A previous run could have left an orphaned `web.server` bound to this
# port. The port-wait below connects to WHATEVER answers, so without this guard a
# relaunch attaches to the orphan and presents ITS data as the new run's — and on
# a live run that orphan is also the process holding /dev/ttyAMA0. Observed on
# the Pi 2026-10-13: killing the browser left the transport on PID 1, still bound
# and still answering.
#
# The decision uses the same connect probe as the port-wait below, so it adds no
# dependency; `ss` is used only to NAME the occupant, and its absence degrades
# the message, never the refusal.
#
# 🛑 A FREE PORT IS NOT A FREE UART, AND THIS GUARD MUST NEVER BE READ AS ONE.
#    Before a live handoff, sweep the descriptors instead:
#        ls -l /proc/*/fd 2>/dev/null | grep ttyAMA0
if python3 -c "import socket,sys; s=socket.socket(); s.settimeout(0.2);
sys.exit(0 if s.connect_ex(('127.0.0.1', $PORT)) == 0 else 1)" 2>/dev/null; then
  echo "[web] :$PORT is already bound — refusing to start." >&2
  occupant="$(ss -ltnpH "sport = :$PORT" 2>/dev/null || true)"
  if [ -n "$occupant" ]; then
    echo "[web]   $occupant" >&2
    occ_pid="$(printf '%s' "$occupant" | sed -n 's/.*pid=\([0-9][0-9]*\).*/\1/p' | head -1)"
    if [ -n "$occ_pid" ] && [ -r "/proc/$occ_pid/cmdline" ]; then
      echo "[web]   pid $occ_pid: $(tr '\0' ' ' < "/proc/$occ_pid/cmdline")" >&2
      if ls -l "/proc/$occ_pid/fd" 2>/dev/null | grep -q ttyAMA; then
        echo "[web]   ⚠  THAT PROCESS IS HOLDING A SERIAL DEVICE." >&2
      fi
    fi
  fi
  echo "[web] Stop it by PID, or pass --port to serve somewhere else." >&2
  exit 1
fi

# --- transport ---------------------------------------------------------------

# shellcheck disable=SC2086
python3 -m web.server $SRC_ARGS $PREFER --host "$HOST" --port "$PORT" &
SERVER_PID=$!

# --- lifecycle ---------------------------------------------------------------
#
# TODO-82, found on the Pi 2026-10-13. This script used to `exec` Chromium, which
# REPLACES the shell and therefore destroys the trap below, so cleanup could
# never run: the transport was orphaned onto PID 1 and the ephemeral profile was
# left on disk (TODO-83, 171 MB leaked across two launches that evening). The
# shell now survives as the supervisor and both children are tracked here.

alive() {
  # True only if the pid exists AND is not a zombie. `kill -0` cannot tell the
  # difference, and an unreaped child made `ps -p` report an already-dead server
  # as running during the 2026-10-13 teardown — which is exactly the kind of
  # ambiguity that must not stand between an operator and a UART handoff.
  # Field 3 of /proc/<pid>/stat is the state; comm (field 2) may contain spaces
  # and parentheses, so strip through the LAST ')' rather than splitting on them.
  if [ -r "/proc/$1/stat" ]; then
    _st="$(sed 's/.*) //' "/proc/$1/stat" 2>/dev/null | cut -d' ' -f1)"
    [ -n "$_st" ] && [ "$_st" != "Z" ]
  elif [ -d /proc ]; then
    return 1                      # Linux and no such entry: the pid is gone
  else
    kill -0 "$1" 2>/dev/null      # non-Linux dev box: zombies indistinguishable
  fi
}

stop_child() {
  # Bounded shutdown with escalation. An unbounded `wait` would hang this script
  # — and strand the profile on disk — if a child ignored SIGTERM.
  #
  # SIGTERM is sent unconditionally, before any liveness check. That is
  # deliberate: it is harmless if the child is already dead, and it means the
  # `wait` at the end is ALWAYS preceded by a signal, so it can never block
  # forever even if `alive` is wrong. The pid cannot have been recycled either,
  # because an unreaped child of this shell keeps its pid until we wait for it.
  _pid="$1"; _label="$2"
  kill "$_pid" 2>/dev/null || true
  _i=0
  while [ "$_i" -lt 50 ] && alive "$_pid"; do _i=$((_i + 1)); sleep 0.1; done
  if alive "$_pid"; then
    echo "[web] $_label ($_pid) ignored SIGTERM for 5 s — escalating to SIGKILL" >&2
    kill -9 "$_pid" 2>/dev/null || true
    _i=0
    while [ "$_i" -lt 20 ] && alive "$_pid"; do _i=$((_i + 1)); sleep 0.1; done
  fi
  wait "$_pid" 2>/dev/null || true          # reap: this shell is the parent
  if alive "$_pid"; then
    echo "[web] ✗ $_label ($_pid) SURVIVED SIGKILL — do not relaunch blind" >&2
    return 1
  fi
  return 0
}

CLEANED=0
cleanup() {
  # Idempotent: EXIT fires after an INT/TERM handler has already run.
  if [ "$CLEANED" -ne 0 ]; then return 0; fi
  CLEANED=1
  _rc=0
  if [ -n "${BROWSER_PID:-}" ]; then
    if ! stop_child "$BROWSER_PID" browser; then _rc=1; fi
  fi
  if [ -n "${SERVER_PID:-}" ]; then
    if ! stop_child "$SERVER_PID" transport; then _rc=1; fi
  fi
  # ONLY this launch's profile. A blanket `rm -rf /tmp/gra-kiosk.*` would delete
  # a profile belonging to a kiosk another session started, with no way to tell
  # whose it was — so historical ones are reported at startup and removed by a
  # human who has checked ownership.
  if [ -n "${PROFILE:-}" ] && [ -d "$PROFILE" ]; then
    rm -rf "$PROFILE" && echo "[web] removed profile $PROFILE"
  fi
  if [ "$_rc" -ne 0 ]; then
    echo "[web] ✗ cleanup incomplete — verify by PID before relaunching" >&2
  fi
  return 0
}

# Separate handlers rather than one shared trap: INT and TERM must terminate the
# script, and an EXIT-only trap would let the shell carry on after the signal.
trap 'cleanup' EXIT
trap 'echo "[web] SIGINT received"  >&2; cleanup; exit 130' INT
trap 'echo "[web] SIGTERM received" >&2; cleanup; exit 143' TERM

# Wait for the port rather than sleeping a guessed interval: a fixed sleep is
# either slower than it needs to be or wrong on a cold boot.
i=0
while [ "$i" -lt 100 ]; do
  if python3 -c "import socket,sys; s=socket.socket(); s.settimeout(0.2);
sys.exit(0 if s.connect_ex(('127.0.0.1', $PORT)) == 0 else 1)" 2>/dev/null; then
    break
  fi
  i=$((i + 1))
  sleep 0.1
done
if [ "$i" -ge 100 ]; then
  echo "[web] transport did not open :$PORT within 10 s" >&2
  exit 1
fi
echo "[web] transport up at $URL  (after $((i * 100)) ms)"

if [ "$BROWSER" -eq 0 ]; then
  echo "[web] --no-browser: serving until interrupted."
  wait "$SERVER_PID"
  exit 0
fi

# --- Wayland session, found rather than assumed ------------------------------

if [ -z "${WAYLAND_DISPLAY:-}" ]; then
  : "${XDG_RUNTIME_DIR:=/run/user/$(id -u)}"
  export XDG_RUNTIME_DIR
  for s in "$XDG_RUNTIME_DIR"/wayland-*; do
    case "$s" in *.lock) continue ;; esac
    [ -S "$s" ] || continue
    WAYLAND_DISPLAY="$(basename "$s")"
    export WAYLAND_DISPLAY
    echo "[web] found compositor socket: \$XDG_RUNTIME_DIR/$WAYLAND_DISPLAY"
    break
  done
fi

if [ -z "${WAYLAND_DISPLAY:-}" ]; then
  cat >&2 <<'EOF'
[web] No Wayland socket found, so there is no session to open a window in.

      Over SSH this usually means the desktop session is not running, or it
      belongs to a different user. Check with:

          loginctl list-sessions
          ls /run/user/*/wayland-*

      To serve without a browser and connect from another machine:

          sh pi/run_web.sh --no-browser --host 0.0.0.0
EOF
  exit 1
fi

# --- Chromium ----------------------------------------------------------------

CHROMIUM=""
for c in chromium-browser chromium /usr/bin/chromium-browser /usr/bin/chromium; do
  if command -v "$c" >/dev/null 2>&1; then CHROMIUM="$c"; break; fi
done
if [ -z "$CHROMIUM" ]; then
  echo "[web] no chromium binary found (tried chromium-browser, chromium)" >&2
  echo "[web] install it, or run with --no-browser and connect remotely" >&2
  exit 1
fi

# Pre-existing profiles are REPORTED, never removed (TODO-83). One of them may
# belong to a kiosk that another session is still running, and a glob delete
# cannot tell whose it is. Cleaning them is a decision for somebody who has
# checked that no chromium is running.
for d in /tmp/gra-kiosk.*; do
  [ -d "$d" ] || continue
  echo "[web] note: pre-existing profile $d ($(du -sh "$d" 2>/dev/null | cut -f1)) — left alone" >&2
done

# An ephemeral profile: this is a test launcher, and it must not leave state
# behind that a later run — or the Tk UI — inherits.
PROFILE="$(mktemp -d /tmp/gra-kiosk.XXXXXX)"

echo "[web] $($CHROMIUM --version 2>/dev/null || echo 'chromium: version unknown')"
echo "[web] launching kiosk at $URL"

# --password-store=basic is NOT cosmetic. Without it, Chromium's first run on a
# fresh profile asks gnome-keyring for a secret store, which raises a modal
# "Choose password for new keyring" dialog ON TOP OF THE KIOSK WINDOW and pops
# the on-screen keyboard. Observed on this Pi, 2026-10-12, first launch. The page
# never becomes visible and no keyboard is attached to dismiss it. This flag is
# what stands between a kiosk that boots and one that hangs on a password prompt.
"$CHROMIUM" \
  --ozone-platform=wayland \
  --kiosk "$URL" \
  --user-data-dir="$PROFILE" \
  --password-store=basic \
  --use-mock-keychain \
  --window-size=720,1280 \
  --force-device-scale-factor=1 \
  --no-first-run \
  --noerrdialogs \
  --disable-infobars \
  --disable-session-crashed-bubble \
  --disable-features=TranslateUI \
  --disable-pinch \
  --overscroll-history-navigation=0 \
  --autoplay-policy=user-gesture-required \
  --check-for-update-interval=31536000 &
BROWSER_PID=$!

echo "[web] supervisor $$ · transport $SERVER_PID · browser $BROWSER_PID"

# *** `wait` ON A BACKGROUND CHILD, NOT A FOREGROUND ONE. ***
#
# A trapped signal that arrives while a POSIX shell waits on a FOREGROUND command
# is not acted on until that command finishes — which for a kiosk means never. So
# removing the `exec` is necessary but NOT sufficient: Chromium must also run in
# the background and be waited for, because `wait` is interruptible and a
# foreground command is not. SIGTERM is then prompt, and a browser crash simply
# returns here and falls through to the EXIT trap.
wait "$BROWSER_PID" || true
echo "[web] browser exited — shutting the transport down"
