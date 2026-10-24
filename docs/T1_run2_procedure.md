# T1 **Run 2** — operator card. `_PI`, reader consuming normally

**Prepared 2026-09-27. NOT EXECUTED. Awaiting approval of this procedure.**

Derived from [T1_run_sheet.md](T1_run_sheet.md) and verified against current
source. Run 2 is the **lowest-risk action in the whole matrix**: no flash, no
rebuild, no wiring change, no `config.h` change, no relay/route change, no
generator, no injection, no validation.

> **Comparison role vs execution order.** Run 2 is the **second** numbered run in
> the T1 comparison and the **first** executed chronologically. See
> [§11 of the run sheet](T1_run_sheet.md) — the numbers are comparison roles, not
> an order of operations.

---

## 1. Starting bench state — verify every line before pressing anything

| Item | Required state | How to confirm |
|---|---|---|
| Teensy power | USB only, as now. No supply change | — |
| Firmware on board | **`dcfbffa`**, `_PI` | banner must read `Build: Sep 26 2026 16:36:53   v0.6.0` |
| `DISPLAY_TARGET` | **`DISPLAY_TARGET_PI`** | banner: `[Main] Display target: Pi 5 (UART)` |
| `config.h` | **unmodified** | `git diff --stat config.h` → empty |
| UART wiring | Teensy pin 1 → Pi physical pin 10; Teensy GND → Pi physical pin 9. **Teensy pin 0 and Pi GPIO14 unconnected.** No rail shared | visual, no probing needed — unchanged since 2026-09-26 |
| Pi | booted, SSH reachable, `/dev/ttyAMA0` present | `ls -l /dev/ttyAMA0` |
| Phone stimulus | **~1 kHz sine playing continuously** into J4 SOURCE via the USB-C DAC and the continuity-verified TRS→TS cable. **Phone charged** — it must survive all four runs | 5 s diagnostics, below |
| SOURCE level | **≈ −21.8 dBFS**, and within **±0.5 dB** of that at both ends of the window | `[Main] SOURCE_NODE peak:` in the 5 s diagnostics |
| Return selection | **TS** — the boot default. **Do not press `j` or `k`** | `[Main] Active route:` / `Route: TS return, no injection` |
| Injection | **OFF** | same line; `ENABLE_DUT_INJECTION` is 0 in source |
| USB console | Arduino Serial Monitor open on the Teensy, **logging to a file or with scrollback long enough for 120 s + the full report** | — |
| Port ownership | **no other process holding the Teensy USB port** | `lsof /dev/cu.usbmodem*` must return nothing |

> **The ±0.5 dB tolerance is mine, not the project's.** No existing authority
> specifies a SOURCE level tolerance for T1 — step 11 says only *"identical signal
> conditions"* and *"an inconsistent input is not [fine], because block timing
> depends on it."* ±0.5 dB is a practical reading of that, chosen because the
> instrument reports one decimal place. **It is a procedural guard on the
> experiment, not an acceptance criterion**, and it is flagged as invented so it
> is never cited as project authority.

> **`lsof` matters.** On 2026-09-26 a `serial-mc` MCP process held the port with
> exclusive ownership and the Serial Monitor came up blank. `kill <pid>` recovered
> it with **no reset, reflash or replug**. Check before, not after.

---

## 2. Establishing a fresh boot-scoped `[Link]` window

**Why a power cycle is mandatory, not hygiene:** `dataSender_resetStats()` runs
**only** from `dataSender_init()`, so every `[Link]` figure is cumulative since
power-on and `TX room min` is a min-since-boot high-water mark (TODO-63). Without a
fresh boot, run 2's transport column would carry whatever the board has been doing
since 2026-09-27.

```
1.  Close the Arduino Serial Monitor.        (the port must be free to re-enumerate)
2.  Unplug the Teensy USB cable.  Wait 5 s.
3.  Re-plug it.
4.  Re-open the Serial Monitor IMMEDIATELY — the banner prints once, early,
    right after Serial.begin(), and is not repeated.
```

**Capture the banner. It is evidence, and three lines of it are the run's identity:**

```
     Guitar Rig Analyzer   v0.6.0
     Build: Sep 26 2026 16:36:53   v0.6.0          <- MUST match exactly
[Main] Display target: Pi 5 (UART)                 <- MUST say Pi 5
[DataSender] Session id N | HELLO ...              <- RECORD N
```

**If the build stamp is anything other than `Sep 26 2026 16:36:53`: STOP.** A
different binary is on the board and nothing measured against it is comparable to
the archived artifact. Preserve what you have and report it.

**Record the session id.** It is how `t1_diff.py` proves runs did not share a boot.
Expect it to have advanced past **7** (the 1 kHz RESULT run), since the counter
increments on every `_PI` boot.

> A reboot releases every GPIO to reset state for a few milliseconds before
> `setup()` reclaims it. That already happens on every power cycle of this image —
> it is not new, and `signalRouter_init()` drives both relay pins LOW again.

---

## 3. Pi commands — copy/paste ready

**Working directory:** `~/guitar_rig_analyzer` on the Pi (the repo clone).

Run 2 uses the **repo tool**, not an ad-hoc reader. Run 2 needs no suspension, so
`capture.sh` is correct: it sets the tty, enforces the duration, refuses to
overwrite evidence, and prints bytes, sha256 and rate. *(The ad-hoc backgrounded
`cat` is needed only for runs 3 and 4, where the PID must be ours to `kill -STOP` —
`capture.sh` cannot be used there because its `timeout` sends a SIGTERM that stays
**pending** on a stopped process.)*

```bash
cd ~/guitar_rig_analyzer

sudo sh pi/tools/capture.sh /dev/ttyAMA0 150 t1-run2-pi-normal.bin \
    2>&1 | tee t1-run2-pi-normal.capturelog
```

**Why 150 s for a 120 s window.** The reader must be consuming *for the whole
window*. 150 s brackets the 120 s window with ~15 s of slack at each end for
operator latency between "capturing…" and pressing `t`, and between pressing `T`
and the capture ending. **The window is defined by `t`→`T` on the Teensy, never by
the capture length.**

| Question | Answer |
|---|---|
| Exact working directory | `~/guitar_rig_analyzer` |
| Exact evidence filename | `t1-run2-pi-normal.bin` + `t1-run2-pi-normal.capturelog` |
| How the PID is captured | **Not needed.** `capture.sh` runs in the foreground and exits on its own. No PID handling in run 2 — that is a run 3/4 concern |
| How we prove the reader is alive | The script prints `capturing 150 s ...` on start, then `bytes:` / `rate:` on completion. **`rate ≈ 36 500 B/s` is the proof it consumed normally for the whole window.** Live frames stopped or a stalled reader would show a far lower rate |
| How it is stopped cleanly | It stops itself at 150 s (`timeout 150 cat`). **Do not Ctrl-C it** — that skips the duration check and the sha256 |
| Partial UART data on termination | The final in-flight packet is lost. `timeout` SIGTERMs `cat` while it is blocked in `read()`, so bytes already read are already written; the packet being transmitted at that instant is simply never completed. It appears as `buffered at end > 0` or, per the 2026-09-27 audit of five captures, as the file ending exactly on a frame boundary. **Harmless and expected — it is not loss on the link** |

**Do not run anything else on the Pi during the window.** No replay, no second
reader on `/dev/ttyAMA0`, no `xxd`.

> `capture.sh` will print its `~36 500 B/s` expectation text at the end. For run 2
> that is the *correct* comparison — no measurement is armed, so the instrument is
> at full idle rate. **This differs from the 1 kHz RESULT capture**, where the same
> warning fired on a healthy artifact (TODO-62) because live frames stop after a
> measurement. Run 2 has no such excuse: **a rate far below ~36 500 B/s in run 2 is
> a real finding.**

---

## 4. Teensy USB commands — verified against source

Both verified in [guitar_rig_analyzer.ino:591-604](../firmware/guitar_rig_analyzer/guitar_rig_analyzer.ino#L591):

| Send | Source effect | Expected response |
|---|---|---|
| `t` | `timingProbe_reset()` — clears the window accumulators **and** calls `AudioMemoryUsageMaxReset()` | exactly one line: `[T1] Measurement window reset — press 'T' to report.` |
| `T` | `timingProbe_report()` — prints the report. **Does NOT reset anything** | the full `[T1] …` block, then the `[Link] …` block, then `[T1] --- PASS CONDITION ---` |

**Case is significant.** `case 't':` and `case 'T':` are **separate** cases — unlike
`'u'/'U'`, `'i'/'I'` and `'x'/'X'`, which are paired. Lowercase `t` starts a window;
uppercase `T` reports. Getting them the wrong way round silently restarts the
window instead of reporting it.

**The handler reads ONE character and flushes the rest of the line**
([.ino:494-496](../firmware/guitar_rig_analyzer/guitar_rig_analyzer.ino#L494)): `char cmd = Serial.read(); while
(Serial.available()) Serial.read();`. So the command is the **first character you
type**, with or without a line ending, and a trailing newline is discarded
harmlessly.

### 🛑 Every keystroke into that window is a command. Two are dangerous.

- **`v` or `V` runs the entire validation suite.** Both cases are mapped
  (`case 'v': case 'V':`). **D1 forbids this.** A stray `v` during run 2 voids the
  run and breaks the standing Phase 9 rule.
- **`1`–`4` run individual validation tests.** Same prohibition.
- `j` / `k` change the return relay. `m` arms a measurement. `x` cancels. `r`
  resets EMA. `s` / `b` / `c` write to SD.

**Type nothing but `t` at the start and `T` at the end.** If a stray character is
sent, record it, treat the run as void, and start a fresh boot rather than
pretending it did not happen.

**`u` is safe but not needed** — it prints the `[Link]` block, which `T` already
includes. Using it mid-window only adds USB print load.

---

## 5. The measurement window

**Exactly 120 s.** Fixed for all four runs, no exceptions.

Authority: step 11 — *"Identical window length (≥60 s; longer is better for the max
figures)"*; TODO-35 repeats *"Identical window length (≥60 s)"*. 120 s satisfies
both, doubles the sample for the max figures, and removes an operator judgment. No
current authority requires a different duration.

Expected cross-check: at the measured 46.4 ms block period, 120 s ⇒
**`block_n` ≈ 2 580** (roughly 2 550–2 620). A `block_n` far from that means the
window was not 120 s, whatever `window_ms` says.

Use a phone stopwatch or `sleep 120` on the Pi as the timer. A few seconds of
operator latency is fine — the differ tolerates up to 10 % window drift between
runs, and `window_ms` records what actually happened.

---

## 6. Execution sequence

```
[ ] 1.  Confirm §1 bench state, line by line.
[ ] 2.  lsof /dev/cu.usbmodem*          -> must be empty
[ ] 3.  Power-cycle the Teensy per §2. Re-open the Serial Monitor at once.
[ ] 4.  Record: Build stamp ______________________  (MUST be Sep 26 2026 16:36:53)
        Record: Display target ____________________  (MUST be Pi 5 (UART))
        Record: Session id ________
[ ] 5.  Start the Pi capture (§3). Wait for "capturing 150 s ...".
[ ] 6.  Let it settle ~10 s so at least two 5 s diagnostic blocks have printed.
[ ] 7.  Record START SOURCE peak from the latest 5 s block: ________ dBFS
        Confirm "Route: TS return, no injection".
[ ] 8.  Send  t        -> expect "[T1] Measurement window reset — press 'T' to report."
[ ] 9.  Wait EXACTLY 120 s. TOUCH NOTHING. Type nothing.
[ ]10.  Record END SOURCE peak from the last 5 s block before you report: ______ dBFS
[ ]11.  Send  T        -> the full report
[ ]12.  Let the Pi capture finish on its own. Record bytes, sha256, rate.
[ ]13.  Save the ENTIRE Serial Monitor transcript (banner through report) verbatim.
```

**Step 10 before step 11, deliberately.** The SOURCE peak is read from the
*automatically printed* 5 s diagnostics, so no command is needed and the window is
not disturbed. Reading it after `T` would work too, but taking it from the last
block *inside* the window keeps the observation inside the measured period.

---

## 7. SOURCE peak observations — no command, no disturbance

The 5 s diagnostic block prints automatically and unconditionally, every 5 s, in
every run:

```
[Main] SOURCE_NODE peak: -21.8 dBFS          |   RETURN_NODE peak: -65.2 dBFS
[Main] TF confidence: 2%          (threshold ...)
[Main] Route: TS return, no injection
```

**Read both observations off the transcript.** Send nothing. Any command would add
USB print load inside the window and, if mistyped, could do far worse.

Required: the first block after settling (START) and the last block before `T`
(END). **They must agree to within ±0.5 dB** (procedural guard, §1). ~24 of these
blocks will appear across a 120 s window — that redundancy is itself evidence the
stimulus held steady, and it costs nothing to keep.

---

## 8. Stop conditions

### STOP, preserve everything, do not retry

| Trigger | Why |
|---|---|
| Build stamp ≠ `Sep 26 2026 16:36:53` | a different binary is on the board; nothing is comparable to the archived artifact |
| `[Main] Display target:` ≠ `Pi 5 (UART)` | wrong target; this is not run 2 |
| `blocks_skipped`, `skip_events` or `largest_block_gap` **> 0** | **step 11: stop.** The non-blocking policy has been violated and no Pi-side work fixes it. Start from acceptance test B in [pi_link_protocol_audit.md](pi_link_protocol_audit.md). **This is the finding the whole matrix exists to look for — do not retry to get a cleaner number** |
| `block_ms_mean` or `block_ms_max` far from ~46.4 / ~46.7 ms | acquisition is already disturbed before the control exists |
| `audioCap_init()` / `audioEngine_init()` FATAL at boot | hardware or codec fault; stop and diagnose |
| Any unexpected relay click, or `Route:` not reading TS/no-injection | unexplained hardware state change |
| A stray validation command was sent (`v`, `V`, `1`–`4`) | D1 violated; void the run, record it, fresh boot. **Do not silently re-run** |
| Smoke, heat, or any physical anomaly | obviously |

### VOID and retry with a fresh boot (not a stop)

| Trigger | Why |
|---|---|
| Serial Monitor blank | check port ownership with `lsof` first — see §1. Recovery needs no reset or reflash |
| Banner missed (monitor opened late) | the identity lines are required evidence; reboot and catch them |
| `capture.sh` exits non-zero (2 = short capture, 3 = zero bytes) | a **tooling** fault, not a link result. Do not interpret the byte count. Exit 3 ⇒ check the device before the wire (`/dev/serial0` is *not* the header UART on this Pi) |
| Window materially off 120 s, or `block_n` far outside 2 550–2 620 | the window is the controlled variable |
| START and END SOURCE peaks differ by more than ±0.5 dB | the stimulus moved; recharge or re-seat and redo |
| Ctrl-C on `capture.sh` | skips the duration check and sha256 |

### NOT a stop condition — expected, and must not be "fixed"

- **`TX room min: 0 B of 4096 B`** — step 11 does not make this a failure. It is
  also boot-scoped and ambiguous with a never-sampled sentinel (TODO-63, TODO-64).
- **`Atomicity: 0 best-effort packets refused`** — expected. It means nothing
  collided; it is not a pass and not a fault (TODO-59).
- **Some live frames dropped in run 2** — permitted. Step 11: transport is allowed
  to degrade. Run 2 carries **no** role expectation in the differ.
- **`loop_us_max` in the high hundreds of µs or low ms** — dominated by the 5 s
  diagnostic print, which is the last thing inside the timed loop body.
- **A low `[Link] Results:` count (`0 queued`)** — correct. Run 2 arms no
  measurement.

---

## 9. Expected outputs that show run 2 was exercised correctly

These establish the **procedure** was followed. **None of them pre-judges T1** —
that needs run 1, which does not exist yet.

| Observation | Expected | What it proves |
|---|---|---|
| Build stamp | `Sep 26 2026 16:36:53   v0.6.0` | the archived artifact is what ran |
| `[T1] display_target=` | `Pi 5 (UART)` | correct target |
| `[T1] window_ms=` | ≈ `120000` (±10 %) | the window was the controlled one |
| `[T1] block_n=` | ≈ 2 580 | the window really ran at the expected cadence |
| `[T1] firmware=` | `0.6.0 protocol=2` | same build family as every other run |
| `[Link] Session id:` | one value, distinct from other runs | run 2 had its own boot |
| `capture.sh` rate | ≈ **36 500 B/s** | **the reader consumed normally for the whole window — this is what makes it run 2** |
| `capture.sh` elapsed | `150s of 150s requested` | the reader was alive across the window |
| `[Link] Live frames:` | thousands sent | the transport was actually working |
| `[Link] Call time: max` | microseconds, not milliseconds | no blocking write — but **a small call time is NOT a pass** (step 11) |
| SOURCE peak start/end | both ≈ −21.8 dBFS, within ±0.5 dB | the stimulus held |
| `blocks_skipped` | `0` | the only absolute criterion, and it applies to every run |

**What run 2 alone cannot establish:** anything comparative. `block_ms_*` means
nothing until run 1 exists. Do not write "run 2 passed" — write "run 2 executed
correctly; comparison pending run 1."

---

## 10. Evidence set for run 2

| Artifact | Name | Notes |
|---|---|---|
| Full USB transcript | `ai/evidence/t1-run2-pi-normal.txt` | banner → report, **verbatim**. This is the file `t1_diff.py` reads |
| Pi raw UART capture | `t1-run2-pi-normal.bin` (on the Pi) | ~5.5 MB at 150 s. **Recommend keeping on the Pi and recording bytes + sha256 only** — we already hold a 4.38 MB full-rate artifact and a second adds little. Commit only if you want it |
| Capture log | `ai/evidence/t1-run2-pi-normal.capturelog` | small; carries start/end/elapsed/bytes/sha256/rate |
| sha256 of the `.bin` | from the capture log | record whether or not the file is committed |
| Session id | from `[Link] Session id:` | the boot discriminator |
| Build identity | `Sep 26 2026 16:36:53 v0.6.0` | ties the run to `dcfbffa` |
| SOURCE peak start / end | dBFS, both | stimulus-stability guard |
| Deviations | anything at all | *recorded, not smoothed over* |

Names carry the run number and condition (`t1-run2-pi-normal`) so they cannot be
confused with run 1 (`t1-run1-none-control`), run 3 (`t1-run3-pi-stalled`), run 4
(`t1-run4-pi-pulled`) or the drift control (`t1-run2-repeat-drift-control`).

The transcript must **also** be pasted verbatim into `ai/journal.md` — TODO-35:
*"Keep all four reports verbatim in journal.md."*

---

## 11. Feeding run 2 into the differ — later, not now

```bash
# NOT YET RUNNABLE. Run 1 does not exist, and the control must be argument 1.
python3 pi/tools/t1_diff.py \
    ai/evidence/t1-run1-none-control.txt \
    ai/evidence/t1-run2-pi-normal.txt \
    ai/evidence/t1-run3-pi-stalled.txt \
    ai/evidence/t1-run4-pi-pulled.txt
```

**Do not compare anything after run 2.** There is no control yet, so there is
nothing to compare against — `timing_probe.h`: *"the control run IS the
threshold."*

A **parse-only sanity check** is safe and worth doing as soon as the transcript
exists, to catch a truncated or mis-saved paste while the bench is still set up:

```bash
python3 -c "
import sys; sys.path.insert(0,'pi/tools')
from t1_diff import parse_report
r = parse_report(open('ai/evidence/t1-run2-pi-normal.txt').read())
print(r['acquisition']); print('transport_present', r['transport_present'])
"
```

---

## 12. What is NOT authorised by this card

- **No flash. No rebuild. No `config.h` change.**
- **No `v`, no `V`, no `1`–`4`** — D1 stands.
- **No generator, no injection, no `j`/`k`, no relay or route change.**
- **No `m`** — run 2 arms no measurement.
- **No wiring change and no disconnect** — D3 is unresolved and run 4 is not
  authorised.
- **No firmware fix for TODO-63 or TODO-64** during acceptance. Changing the image
  to improve its own instrumentation would invalidate the artifact under test.
- **No Phase 9 activity of any kind.**
- **Runs 3 and 4 are not authorised by this card.** Run 3 needs the ad-hoc reader
  procedure; run 4 needs the D2 source verification and the D3 break point first.
