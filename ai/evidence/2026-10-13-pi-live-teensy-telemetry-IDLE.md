# Physical Pi 5 displaying live Teensy telemetry — IDLE, no measurement initiated

**2026-10-13 · bench photograph · `OBS`**

![Pi 5 panel showing live telemetry](2026-10-13-pi-live-teensy-telemetry-IDLE.png)

Original, unedited. SHA-256
`d6635a13ed3c71492a04f0017a0087aef555504e2758aced074c4c52a6bdd049`.

**The first photographic record of the physical Pi rendering live telemetry from
a powered Teensy.** Every previous web-renderer image in this directory was a
recorded fixture replayed from disk. This is the Tk renderer on the real panel,
reading a real UART, with the instrument powered.

## Session context

Taken during the staged cold-resume of 2026-10-13, after the Pi-side baseline
was established and immediately after the Teensy was powered on. Procedure:
[`docs/pi_resume_from_cold.md`](../../docs/pi_resume_from_cold.md).

| | |
|---|---|
| Renderer | Tk (`analyzer_ui`), PID 1505, autostarted at boot |
| Code running | the **Pi's own checkout**, last recorded at `ce682cd` and dirty — **not** the Mac's `cc994de` |
| UART | `/dev/ttyAMA0`, fd 3, opened `O_RDONLY` |
| Pi health | `throttled=0x0`, live and sticky bits clear |
| Operator action on the UI | **none** — not touched, not tapped |

## Transcribed from the photograph

| Field | Value |
|---|---|
| Link | `LINK UP` |
| Session | `46` |
| Firmware | `0.6.0` |
| Protocol | `2` |
| Geometry | `128/512 bins · 4:1 · 44100 Hz` |
| Serial device | `serial:/dev/ttyAMA0` |
| View | `LIVE` |
| Measurement state | **`IDLE`** |
| `SOURCE_NODE` | **−39.8 dBFS** |
| `RETURN_NODE` | **−53.8 dBFS** |
| Live TF | `confidence 0%` · `0/512 clamped` |
| TF coverage | `128 bins : 0 measured · 128 unmeasured` |
| Return source | `TS` — "TS return, no injection" |
| Detectors | `UNKNOWN (no detect hardware fitted)` |
| Frames | `frames ok 5910 · CRC fail 0 · decode err 0` |
| Discarded | `1 (lead 1, interior 0)` |
| Commands | `commands disabled — Pi→Teensy not connected` |

## What this establishes

**The link carries decodable protocol v2 packets from a real Teensy.** 5910
frames accepted with **zero CRC failures and zero decode errors** is the first
evidence in this project that the receiver's reading of `data_sender.h` agrees
with the compiled firmware **on the wire** — the shared-author evidence loop that
`pi/README.md` flags as unbroken by any synthetic test.

**HELLO arrived and geometry was negotiated**, not assumed: `128/512 · 4:1 ·
44100` came off the wire, which is why the TF panel can be drawn at all.

**The authority boundary is visible on the panel.** `commands disabled —
Pi→Teensy not connected` is rendered as a statement, and `detectors: UNKNOWN (no
detect hardware fitted)` refuses to report jack presence it cannot sense.

**`discarded 1 (lead 1, interior 0)`** — one lead-in byte dropped while the
scanner acquired sync, zero interior discards. That is the expected signature of
attaching mid-stream, and the interior count being zero is the meaningful half.

## 🛑 What this does NOT establish

**Nothing about measurement accuracy.** The instrument is `IDLE`. No capture was
armed, no stimulus applied, no calibration loaded. `0 measured · 128 unmeasured`
is the correct and honest display for that state.

**The 14.0 dB SOURCE−RETURN difference is NOT an insertion loss.** These are two
independent input-level readings on an uncalibrated instrument, not a transfer
function. A transfer function divides RETURN by SOURCE per bin and requires the
source gate to be passed; `confidence 0%` says that never happened here. Reading
the gap as rig attenuation is exactly the error
[`evidence-tier-discipline`](../todo.md) exists to prevent. See also **TODO-78**:
every level measured before 2026-10-12 was taken under an unintended ≈1.59 kΩ
shunt, and no post-repair baseline has been established.

**`frames ok` is not packet validation by this project's own standard.** The Tk
renderer decoded these bytes with the same codebase that wrote the test vectors.
The independent check is a **raw byte capture** replayed offline, which is the
next stage and had not been run when this photograph was taken.

**Session 46** means the Teensy has booted 46 times, not that this session is
46 minutes old or in any way validated.

## Open bench blockers, unaffected by this photograph

**TODO-70** (controlled RETURN→SOURCE leak test) · **TODO-75** (grounded-probe
floor, gates every amplitude claim at J8) · **TODO-78** (re-baseline under the
corrected C10 topology). None is advanced by a display working. The volume
investigation of 2026-10-05 also remains open.
