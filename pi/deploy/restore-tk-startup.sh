#!/bin/sh
# Restore the ORIGINAL Tk startup configuration. Run over SSH; needs no keyboard.
#
#     sh ~/gra-rollback/restore-tk-startup.sh
#
# Restores ~/.config/labwc/autostart to the Tk line captured before the
# 2026-10-15 kiosk migration, then verifies the hash. It does NOT reboot and it
# does NOT stop anything that is running -- see the notes at the end.
set -eu

BACKUP="$HOME/gra-rollback/labwc-autostart.TK-ORIGINAL"
TARGET="$HOME/.config/labwc/autostart"
WANT="b40fbc70653ccfa53a808b170877f1cc9ab589f6e17d95498064ea5c6f986c60"

[ -r "$BACKUP" ] || { echo "✗ backup missing: $BACKUP" >&2; exit 1; }

got_backup="$(sha256sum "$BACKUP" | cut -d" " -f1)"
if [ "$got_backup" != "$WANT" ]; then
  echo "✗ the BACKUP itself does not match the recorded hash -- refusing." >&2
  echo "  want $WANT" >&2
  echo "  got  $got_backup" >&2
  exit 1
fi

cp -a "$BACKUP" "$TARGET"

got="$(sha256sum "$TARGET" | cut -d" " -f1)"
if [ "$got" != "$WANT" ]; then
  echo "✗ restore wrote the wrong bytes -- do NOT reboot." >&2
  exit 1
fi

echo "✓ $TARGET restored to the Tk autostart ($WANT)"
echo
echo "The Tk UI starts on the NEXT boot. To get it back NOW, without rebooting,"
echo "first make sure nothing else holds the UART:"
echo
echo "    pkill -f run_kiosk_boot.sh ; pkill -f run_web.sh"
echo "    sleep 3"
echo "    ls -l /proc/*/fd 2>/dev/null | grep ttyAMA0 || echo \"UART free\""
echo "    setsid sh ~/guitar_rig_analyzer/pi/run_ui.sh --serial /dev/ttyAMA0 >/dev/null 2>&1 &"
echo
echo "That launcher is the Pi's own checkout, which is exactly what boot would run."
