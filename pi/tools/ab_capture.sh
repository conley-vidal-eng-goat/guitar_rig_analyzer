#!/bin/sh
# Record /api/frame from the running kiosk for one state of the A/B run.
#
#   sh pi/tools/ab_capture.sh OUTDIR LABEL SECONDS
#
# Runs on the Mac. An SSH session polls the Pi's own web server at ~4 Hz, the
# Pi keeps the frames locally, and they are copied back gzipped to
# OUTDIR/LABEL.jsonl, one JSON frame per line. Read-only: it never
# touches the UART, and the kiosk stays the only holder of /dev/ttyAMA0.
#
# GRA_HOST overrides the Pi's address (default conley@guitar-rig-analyzer.local).
# AB_REMOTE_DIR, if set, leaves the frames on the Pi as AB_REMOTE_DIR/LABEL.jsonl
# and copies nothing; ab_run.py uses it to fetch every state once, after the run.
set -eu

[ $# -eq 3 ] || { echo "usage: $0 OUTDIR LABEL SECONDS" >&2; exit 2; }
OUT="$1"; LABEL="$2"; SECS="$3"
HOST="${GRA_HOST:-conley@guitar-rig-analyzer.local}"
mkdir -p "$OUT"
FILE="$OUT/$LABEL.jsonl"
[ -e "$FILE" ] && { echo "$FILE exists; refusing to overwrite" >&2; exit 1; }

# The frames are written on the Pi and copied back afterwards, so a slow Wi-Fi
# link to the Mac can't thin out the capture (2026-10-31: A2 got 99 of ~320).
REMOTE="${AB_REMOTE_DIR:-/tmp/ab-$$}/$LABEL.jsonl"
ssh -o BatchMode=yes "$HOST" python3 - "$SECS" "$REMOTE" <<'PY'
import json, os, sys, time, urllib.request
os.makedirs(os.path.dirname(sys.argv[2]), exist_ok=True)
if os.path.exists(sys.argv[2]):
    sys.exit(sys.argv[2] + " exists on the Pi; refusing to overwrite")
end = time.time() + float(sys.argv[1])
n = 0
with open(sys.argv[2], "w") as out:
    while time.time() < end:
        t = time.time()
        with urllib.request.urlopen("http://127.0.0.1:8711/api/frame", timeout=2) as r:
            f = json.load(r)
        f["_t"] = round(t, 3)
        out.write(json.dumps(f, separators=(",", ":")) + "\n")
        n += 1
        time.sleep(max(0.0, 0.25 - (time.time() - t)))
print(sys.argv[2] + ": " + str(n) + " frames, on the Pi")
PY

[ -n "${AB_REMOTE_DIR:-}" ] && exit 0

# Gzipped: the frames compress about 5x, and on 2026-10-31 the Wi-Fi fell to
# ~18 kB/s and one uncompressed 12 MB copy took eleven minutes.
ssh -o BatchMode=yes "$HOST" "gzip -c $REMOTE && rm -r $(dirname "$REMOTE")" | gunzip > "$FILE"
N=$(wc -l < "$FILE" | tr -d ' ')
echo "$FILE: $N frames"
