# FLASH CANDIDATE — `dcfbffa` · `DISPLAY_TARGET_PI`

**This is the artifact to flash. Do not rebuild.**

Because [guitar_rig_analyzer.ino:215](../../../../firmware/guitar_rig_analyzer/guitar_rig_analyzer.ino#L215) stamps
`__DATE__`/`__TIME__`, builds are **not reproducible**: recompiling this exact
commit produces a different binary with a different hash. **Any rebuild, source
change, or configuration change invalidates this candidate** and requires a new
artifact with a new manifest. The `.hex` in this directory is therefore the only
thing that can later be matched against the board.

Not yet flashed as of this manifest.

## Artifact

| | |
|---|---|
| File | `guitar_rig_analyzer.ino.hex` |
| Size | 682 701 bytes (Intel HEX) · 242 688 bytes of image data |
| **md5** | `55ee39a5d8fba94cdad9606e9fa20a2f` |
| **sha256** | `24b71d73bf60a0d6ff9cbb5737a46bba6a04887a1fe55479d356b5a87dce3a6e` |

## Source

| | |
|---|---|
| Commit | `dcfbffabb791923e9c36f0fdbaf75d00fe9052f5` (`dcfbffa`) |
| Subject | docs(phase10): reconcile runbook with the final producer contract |
| Firmware-bearing files uncommitted | **none** |
| Other tree state | `docs/asbuilt/*` and `tools/gen_schematic.py` modified by the concurrent as-built capture session — **not compiled, cannot affect this binary** |

## Build

| | |
|---|---|
| Target | `teensy:avr:teensy41` |
| `DISPLAY_TARGET` | `DISPLAY_TARGET_PI` |
| `FIRMWARE_VERSION` | `0.6.0` |
| `PI_PROTOCOL_VERSION` | `2` |
| arduino-cli | 1.4.1 (Homebrew, 2026-01-19) |
| Teensy core | `teensy:avr` 1.62.0 |
| Toolchain | teensy-compile 15.2.1 |
| Command | `arduino-cli compile --clean --fqbn teensy:avr:teensy41` |
| **Warnings / errors** | **0** |
| FLASH | code 159 236 · data 74 248 · headers 9 200 |
| RAM1 | variables 220 288 · code 155 800 · padding 8 040 · 140 160 free |
| RAM2 | variables 62 528 · 461 760 free |

## Compiled-in identity — the flash verification target

Extracted from the image itself, not from the build log:

```
__DATE__  Sep 26 2026
__TIME__  16:36:53
```

After flashing, the board must print on USB Serial:

```
Build: Sep 26 2026 16:36:53   v0.6.0
[Main] Display target: Pi 5 (UART)
[DataSender] Session id N | HELLO re-announced every 1000 ms | STATE every 500 ms
```

**Any other date/time means a different binary is on the board.** The session
id is the one line that legitimately differs per boot — record the value it
prints, since it is what HELLO carries.

## Replaces

`029ac05` — `Build: Sep 21 2026 17:21:24 v0.6.0`, hex md5
`65405de70fc778fdd8cf6a48e1cbe45e` (journal 2026-09-21 (3)).

Flash safety review for this transition: journal **2026-09-26 (7)**. Summary —
no credible boot-time electrical change to the breadboard; GPIO modes, relay
state, generator/injection and audio routing all unchanged; `validation_init()`
is print-only; Phase 9 tests reachable only by explicit USB command. One new
boot-time side effect: a 2-byte EEPROM write for the session counter, executed
before `audioCap_init()`.
