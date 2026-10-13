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

# --- transport ---------------------------------------------------------------

# shellcheck disable=SC2086
python3 -m web.server $SRC_ARGS $PREFER --host "$HOST" --port "$PORT" &
SERVER_PID=$!

cleanup() {
  [ -n "${SERVER_PID:-}" ] && kill "$SERVER_PID" 2>/dev/null || true
  [ -n "${PROFILE:-}" ] && [ -d "$PROFILE" ] && rm -rf "$PROFILE"
  return 0
}
trap cleanup EXIT INT TERM

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

# An ephemeral profile: this is a test launcher, and it must not leave state
# behind that a later run — or the Tk UI — inherits.
PROFILE="$(mktemp -d /tmp/gra-kiosk.XXXXXX)"

echo "[web] $($CHROMIUM --version 2>/dev/null || echo 'chromium: version unknown')"
echo "[web] launching kiosk at $URL"

exec "$CHROMIUM" \
  --ozone-platform=wayland \
  --kiosk "$URL" \
  --user-data-dir="$PROFILE" \
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
  --check-for-update-interval=31536000
