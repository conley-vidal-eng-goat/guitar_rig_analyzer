#!/bin/sh
# Raw Serial1 capture — RUN ON THE RASPBERRY PI.
#
#   sudo sh capture.sh <device> <seconds> <output.bin>
#   e.g.  sudo sh capture.sh /dev/serial0 30 cap.bin
#
# Writes RAW BYTES ONLY. No decoding happens during acquisition, deliberately:
# a decoded log proves the decoder agreed with itself, whereas raw bytes from a
# flashed Teensy are what breaks the shared-author evidence loop. Decode later,
# offline, with pi/tools/replay.py against this exact file.
set -eu

DEV="${1:?usage: capture.sh <device> <seconds> <output.bin>}"
SECS="${2:?usage: capture.sh <device> <seconds> <output.bin>}"
OUT="${3:?usage: capture.sh <device> <seconds> <output.bin>}"

[ -e "$DEV" ] || { echo "no such device: $DEV" >&2; exit 1; }
[ -e "$OUT" ] && { echo "refusing to overwrite $OUT" >&2; exit 1; }

echo "device : $DEV -> $(readlink -f "$DEV" 2>/dev/null || echo "$DEV")"
echo "config : 460800 8N1 raw, no flow control"

# 460800 8N1, raw, no echo, no flow control, no character translation.
stty -F "$DEV" 460800 cs8 -cstopb -parenb -crtscts \
     raw -echo -echoe -echok -ixon -ixoff -icrnl -onlcr min 0 time 1

echo "capturing $SECS s ..."
START=$(date -u +%Y-%m-%dT%H:%M:%SZ)
timeout "$SECS" cat "$DEV" > "$OUT" || true
END=$(date -u +%Y-%m-%dT%H:%M:%SZ)

BYTES=$(wc -c < "$OUT")
echo
echo "start  : $START"
echo "end    : $END"
echo "bytes  : $BYTES"
echo "sha256 : $(sha256sum "$OUT" | cut -d' ' -f1)"
echo
echo "Expected for ~30 s idle: ~1.1 MB at ~36.5 KB/s."
echo "A byte count far below that means the link, not the parser, is the"
echo "problem -- fix it here before replaying anything."
