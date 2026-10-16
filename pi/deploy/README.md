# Pi production deployment — what boots, from where, and how to undo it

**2026-10-15.** The Raspberry Pi 5 boots into the **web kiosk**. This directory
holds the startup configuration *as deployed*, so the repository represents it
rather than merely describing it.

> ### 🛑 Files in this directory are COPIES, not the live configuration.
>
> The Pi's real startup file is `~/.config/labwc/autostart`, which is **outside
> any git checkout** and cannot be changed by `git pull`. Nothing in this
> directory takes effect until it is *installed* (below). A commit here is a
> record of what was deployed, **not** the deployment — if you edit
> `labwc-autostart.kiosk` and commit it, the Pi still boots the old file.
>
> Verify what is actually running by hash, never by reading this directory:
>
> ```sh
> ssh conley@guitar-rig-analyzer.local 'sha256sum ~/.config/labwc/autostart'
> ```

## What is tracked here, and what only exists on the Pi

| Tracked in this repo | Lives only on the Pi |
|---|---|
| `labwc-autostart.kiosk` — the installed autostart, verbatim | `~/.config/labwc/autostart` (the live file) |
| `labwc-autostart.tk-original` — the pre-migration Tk autostart | `~/gra-rollback/` (backups + the record) |
| `restore-tk-startup.sh` — the rollback script | `~/gra-ui/` (the deployed code tree) |
| `../run_kiosk_boot.sh` — the boot supervisor | `~/gra-ui-boot.log` (the supervisor's log) |
| | `/etc/xdg/labwc/autostart` (root-owned, **never modified**) |

**`~/guitar_rig_analyzer` is the Pi's own stale git checkout.** It sits at
`ce682cd` with 49 dirty/untracked entries and is **deliberately not updated** —
it holds the known-good Tk launcher the fallback uses, and uncommitted work that
exists nowhere else. Do not `git checkout .` in it.

## Hashes as deployed, 2026-10-15

| File | SHA-256 |
|---|---|
| `labwc-autostart.kiosk` | `e9f90ba9321d3417009c30e584d6388bd6d8c8ddcb11433d7a3405706d695083` |
| `labwc-autostart.tk-original` | `b40fbc70653ccfa53a808b170877f1cc9ab589f6e17d95498064ea5c6f986c60` |
| `restore-tk-startup.sh` | `677782aa4a8a6e7b7c13f51aad161d1599e2887baa5209d3c9a23673e03d816f` |
| `../run_kiosk_boot.sh` | `faf87fe74d8192948e911ba4cfbc2df67cf00b79be0706a8936922946ff82c32` |
| `/etc/xdg/labwc/autostart` (unmodified) | `3a53212ad85afb47ef60ebb66c5a6c911cba210ff5577492acfafa2c68edb719` |

## The boot chain

```
lightdm → labwc → ~/.config/labwc/autostart   (user file, ADDITIVE to the system one)
                      └── ~/gra-ui/pi/run_kiosk_boot.sh &
                              ├── waits for the Wayland socket (bounded 30 s)
                              ├── run_web.sh --serial /dev/ttyAMA0 --prefer live
                              │       ├── python3 -m web.server   (sole ttyAMA0 holder)
                              │       └── chromium --kiosk
                              └── on repeated startup failure → Tk UI from the Pi's own checkout
```

**labwc runs the user file IN ADDITION to `/etc/xdg/labwc/autostart`, not
instead of it.** That cost a reboot to learn on 2026-09-30 — the first version
re-listed stock services and produced two panel supervisors and two kanshi. The
user file therefore contains **exactly one active line**.

**Why not a systemd user service.** `graphical-session.target` is **inactive**
on this Pi: lightdm → labwc never activates it. A unit with
`WantedBy=graphical-session.target` would silently never fire. Measured
2026-10-15 with `systemctl --user is-active graphical-session.target`. labwc
autostart is also the already-proven mechanism, and adding a second startup
manager would mean two things could launch the UI.

## Install (first time, or after a rollback)

```sh
cd ~/Developer/guitar_rig_analyzer
rsync -a --exclude __pycache__ pi/ conley@guitar-rig-analyzer.local:~/gra-ui/pi/
ssh conley@guitar-rig-analyzer.local \
  'cat ~/gra-ui/pi/deploy/labwc-autostart.kiosk > ~/.config/labwc/autostart'
```

`cat >` rather than `mv`/`cp` deliberately: it writes **through** the existing
file, so mode `664` and ownership survive.

Verify before rebooting:

```sh
ssh conley@guitar-rig-analyzer.local '
  sha256sum ~/.config/labwc/autostart            # expect e9f90ba9...
  sha256sum /etc/xdg/labwc/autostart             # expect 3a53212a... (unchanged)
  grep -vE "^\s*#" ~/.config/labwc/autostart | grep -vE "^\s*$"   # exactly ONE line
  ls -l ~/gra-ui/pi/run_kiosk_boot.sh            # must be executable
'
```

## Rollback to the Tk UI — over SSH, no keyboard

```sh
ssh conley@guitar-rig-analyzer.local 'sh ~/gra-rollback/restore-tk-startup.sh'
```

Restores `~/.config/labwc/autostart` byte-for-byte to the Tk original and
**verifies the hash before and after**, refusing to write if the backup itself
is wrong. Takes effect on the next boot; the script prints the commands to bring
Tk back immediately without rebooting.

To stop the kiosk claiming the panel on the next boot **without** restoring Tk:

```sh
ssh conley@guitar-rig-analyzer.local 'touch ~/gra-ui/DISABLE_KIOSK_AUTOSTART'
```

🔺 **A rollback path that has not been exercised is a claim, not a capability.**
This one was run for real on 2026-10-15 before the reboot: it restored the Tk
file, the hash was checked, and the kiosk config was then re-applied.

## Rebooting the Pi needs a password, and that is not a fault

`sudo` on this Pi requires a password and polkit refuses `systemctl reboot` from
an SSH session — an SSH session is `Remote=yes`, so polkit's `allow_active=yes`
does not apply and it falls through to `auth_admin_keep`. From the Mac:

```sh
ssh -t conley@guitar-rig-analyzer.local 'sudo reboot'
```

The `-t` allocates a pseudo-terminal so the password prompt can appear. No
keyboard on the Pi is needed, or ever has been.

## The supervisor is not a restart loop, and that is deliberate

`run_kiosk_boot.sh` retries a bounded **3** times and only for **startup**
failures. An exit after ≥60 s of running is treated as a deliberate teardown and
the supervisor exits with it, leaving `/dev/ttyAMA0` free.

That preserves the 2026-09-30 operator decision which kept the Tk line out of
`lwrespawn`: terminating the UI must free the UART for diagnostics, and a
crashing application must not enter a restart loop. A naive supervisor would
seize the UART back from an operator who had just freed it.
