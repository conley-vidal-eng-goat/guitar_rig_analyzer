#!/bin/sh
# Raw Serial1 capture — RUN ON THE RASPBERRY PI.
#
#   sudo sh capture.sh <device> <seconds> <output.bin>
#   e.g.  sudo sh capture.sh /dev/ttyAMA0 30 cap.bin
#
# Writes RAW BYTES ONLY. No decoding happens during acquisition, deliberately:
# a decoded log proves the decoder agreed with itself, whereas raw bytes from a
# flashed Teensy are what breaks the shared-author evidence loop. Decode later,
# offline, with pi/tools/replay.py against this exact file.
#
# =============================================================================
# *** ON A PI 5, /dev/serial0 IS PROBABLY THE WRONG DEVICE. ***
# =============================================================================
# Established on this hardware 2026-09-26 (journal): with GPIO14/15 configured
# as TXD0/RXD0, /dev/serial0 symlinked to ttyAMA10 and received NOTHING, while
# the header UART was reachable as /dev/ttyAMA0.
#
#   serial0  -> /axi/pcie@1000120000/rp1/serial@30000   -> ttyAMA10
#   serial10 -> /soc@107c000000/serial@7d001000         -> ttyAMA0
#
# The Pi 5 renumbered its UARTs and /dev/serial0 no longer reliably means "the
# 40-pin header UART". Confirm on YOUR hardware; do not copy a device path from
# an older model, and do not copy this one without checking.
# =============================================================================
set -eu

DEV="${1:?usage: capture.sh <device> <seconds> <output.bin>}"
SECS="${2:?usage: capture.sh <device> <seconds> <output.bin>}"
OUT="${3:?usage: capture.sh <device> <seconds> <output.bin>}"

[ -e "$DEV" ] || { echo "no such device: $DEV" >&2; exit 1; }
[ -e "$OUT" ] && { echo "refusing to overwrite $OUT" >&2; exit 1; }

RESOLVED=$(readlink -f "$DEV" 2>/dev/null || echo "$DEV")
echo "device : $DEV -> $RESOLVED"
echo "config : 460800 8N1 raw, no flow control, min 1 time 0"

# -----------------------------------------------------------------------------
# min 1 time 0 — DO NOT CHANGE THIS TO `min 0 time 1`.
#
# It was `min 0 time 1`, and on 2026-09-26 that silently broke a capture: with
# no data arriving, a read returns immediately, `cat` sees EOF-like behaviour
# and EXITS, and the script reported "bytes: 0" for what looked like a
# completed 30 s run. It had actually run for ~1 second. A zero-byte result
# that exits early is indistinguishable from a dead link unless you check the
# clock, and the operator nearly accepted it as proof of a wiring fault.
#
# `min 1 time 0` makes the read block until at least one byte arrives, so the
# OUTER `timeout` is what ends the capture — which is what the caller asked
# for. The duration check below enforces that this stays true.
# -----------------------------------------------------------------------------
stty -F "$DEV" 460800 cs8 -cstopb -parenb -crtscts \
     raw -echo -echoe -echok -ixon -ixoff -icrnl -onlcr min 1 time 0

echo "capturing $SECS s ..."
START_EPOCH=$(date -u +%s)
START=$(date -u +%Y-%m-%dT%H:%M:%SZ)
timeout "$SECS" cat "$DEV" > "$OUT" || true
END_EPOCH=$(date -u +%s)
END=$(date -u +%Y-%m-%dT%H:%M:%SZ)

ELAPSED=$((END_EPOCH - START_EPOCH))
BYTES=$(wc -c < "$OUT")

echo
echo "start   : $START"
echo "end     : $END"
echo "elapsed : ${ELAPSED}s of ${SECS}s requested"
echo "bytes   : $BYTES"
echo "sha256  : $(sha256sum "$OUT" | cut -d' ' -f1)"
echo

# -----------------------------------------------------------------------------
# Duration check. The 2026-09-26 defect produced a plausible-looking failure
# report from a capture that never ran. A short capture is a TOOLING fault and
# must not be presented as a link result.
# -----------------------------------------------------------------------------
if [ "$ELAPSED" -lt $((SECS - 1)) ]; then
    echo "FAIL: capture ended after ${ELAPSED}s but ${SECS}s were requested." >&2
    echo "      This is a TOOLING fault, not evidence about the link." >&2
    echo "      Do not interpret the byte count. Check the stty line above" >&2
    echo "      still says 'min 1 time 0'." >&2
    exit 2
fi

if [ "$BYTES" -eq 0 ]; then
    echo "WARNING: ${SECS}s elapsed and NOTHING arrived." >&2
    echo "  The capture ran to completion, so this is a real observation --" >&2
    echo "  but before concluding the link is dead, check the DEVICE:" >&2
    echo "    ls -l /dev/serial0 /dev/ttyAMA*" >&2
    echo "    raspi-gpio get 14,15        # expect TXD0 / RXD0" >&2
    echo "  On a Pi 5, /dev/serial0 may map to ttyAMA10 while the 40-pin" >&2
    echo "  header UART is /dev/ttyAMA0. That exact mistake cost a session" >&2
    echo "  on 2026-09-26 -- the scope showed a healthy 3.3 V waveform" >&2
    echo "  arriving at the Pi header pin while serial0 read nothing." >&2
    exit 3
fi

RATE=$((BYTES / ELAPSED))
echo "rate    : ${RATE} B/s"
echo
echo "Expected for an idle instrument: ~36 500 B/s (~25.6 packets/s), so"
echo "~1.1 MB over 30 s. Measured on hardware 2026-09-26: 36 465 B/s."
echo "A byte count far below that is a link fault -- fix it here before"
echo "replaying anything."
