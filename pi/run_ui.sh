#!/bin/sh
# Launch the Pi production UI. Run from anywhere.
#
#   sh pi/run_ui.sh                       # replay the real 1 kHz RESULT capture
#   sh pi/run_ui.sh --windowed            # desktop development, not fullscreen
#   sh pi/run_ui.sh --tab result --no-realtime   # deterministic RESULT screen
#   sh pi/run_ui.sh --serial /dev/ttyAMA0 # live, receive-only
#
# Needs python3-tk (preinstalled on Raspberry Pi OS Desktop; verified Tk 8.6 on
# this Pi 2026-09-29). Standard library only otherwise — no numpy, no pip.
set -eu
cd "$(dirname "$0")"
FIXTURE="../ai/evidence/phase10-result-1khz.bin"
case " $* " in
  *" --serial "*|*" --fixture "*) exec python3 -m analyzer_ui "$@" ;;
  *) exec python3 -m analyzer_ui --fixture "$FIXTURE" "$@" ;;
esac
