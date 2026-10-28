#!/bin/sh
# Record /api/frame from the running kiosk for one state of the A/B run.
#
#   sh pi/tools/ab_capture.sh OUTDIR LABEL SECONDS
#
# Runs on the Mac. One SSH session polls the Pi's own web server at ~4 Hz and
# writes one JSON frame per line to OUTDIR/LABEL.jsonl. Read-only: it never
# touches the UART, and the kiosk stays the only holder of /dev/ttyAMA0.
#
# GRA_HOST overrides the Pi's address (default conley@guitar-rig-analyzer.local).
set -eu

[ $# -eq 3 ] || { echo "usage: $0 OUTDIR LABEL SECONDS" >&2; exit 2; }
OUT="$1"; LABEL="$2"; SECS="$3"
HOST="${GRA_HOST:-conley@guitar-rig-analyzer.local}"
mkdir -p "$OUT"
FILE="$OUT/$LABEL.jsonl"
[ -e "$FILE" ] && { echo "$FILE exists; refusing to overwrite" >&2; exit 1; }

ssh -o BatchMode=yes "$HOST" python3 - "$SECS" > "$FILE" <<'PY'
import json, sys, time, urllib.request
end = time.time() + float(sys.argv[1])
while time.time() < end:
    t = time.time()
    with urllib.request.urlopen("http://127.0.0.1:8711/api/frame", timeout=2) as r:
        f = json.load(r)
    f["_t"] = round(t, 3)
    print(json.dumps(f, separators=(",", ":")), flush=True)
    time.sleep(max(0.0, 0.25 - (time.time() - t)))
PY

N=$(wc -l < "$FILE" | tr -d ' ')
echo "$FILE: $N frames"
