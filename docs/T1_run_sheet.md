# T1 acceptance run sheet — execution aid for Phase 10 step 11

**Prepared 2026-09-27. NOTHING HAS BEEN FLASHED OR RUN.** This sheet is an
execution aid only. **It defines no acceptance criteria.** Every pass condition
below is quoted or referenced from existing project authority:

| Authority | What it owns |
|---|---|
| [breadboard_bringup_v3.md](breadboard_bringup_v3.md) Phase 10 **step 11** | the procedure and the metric table |
| [timing_probe.h](../firmware/guitar_rig_analyzer/timing_probe.h) | the question, the failure hierarchy, "the control run is the threshold" |
| `ai/todo.md` **TODO-35** | the acceptance matrix and its pass condition |
| `ai/todo.md` **TODO-34** T1 | why the measurement exists |
| [ADR-001](adr/ADR-001-display-architecture.md) | the failure hierarchy being defended |

> **The question, restated so it is never mistaken for "does UART work":**
> *Can the presentation transport become unavailable without measurably
> perturbing the Teensy's audio/measurement timing?*

---

## ✅ THE THREE DECISIONS — MADE BY THE OPERATOR 2026-09-27

Recorded here as settled. The reasoning that produced each option set is kept
below, because a decision without its alternatives is not reviewable.

| | Decision | Consequence |
|---|---|---|
| **D1** | **Tests 1–4 are NOT run during T1.** Option (b), with one change: a USB-liveness observation may be collected as **supplemental** evidence and **must never be described as satisfying the Tests 1–4 clause.** | **T1/TODO-35 CANNOT BE DECLARED FULLY CLOSED from this matrix.** The step 11 clause is recorded as **UNEXECUTED/DEFERRED**, not substituted. |
| **D2** | **Approved in principle:** run 4 uses a deliberately stalled reader so the drain stays pending. **Gated on a source verification** (below) before run 4 executes. | Run 4 is not authorised until the abandonment mechanism is verified from source. |
| **D3** | **Approved:** never break the link at Pi physical pin 10. Exact break point and procedure to be produced and reviewed **before** run 4. | **No physical disconnect is authorised yet.** |

### 🛑 D1 — the deferred clause, stated so it cannot be quietly lost

Step 11 requires: *"the validation suite (`1`–`4`) still runs and passes with the
Pi stalled. A dead renderer must not be able to fail a measurement."* TODO-35
repeats it. **This is not being executed.** The standing Phase 9 rule remains in
force and is not relaxed for a timing experiment.

**Therefore, when this matrix completes, the correct status is:**
*"T1 acquisition acceptance satisfied; the step 11 validation-suite clause
UNEXECUTED. TODO-35 not fully closed."*

A USB-liveness check (`i`, `j`, `k`, `T`, `u` all answer while the Pi is stalled)
**may** be recorded as supplemental. It answers a narrower question — is the USB
console alive under backpressure — and it is **not equivalent to, and does not
satisfy,** "a dead renderer cannot fail a measurement". Do not write it up as
though it were.

### 🛑 D2 — source verification owed BEFORE run 4, not inferred from a counter name

Before run 4 is authorised, these must be established from **current source**:

- what causes a staged RESULT to remain pending;
- what condition increments `result_bytes_abandoned`;
- whether physically disconnecting TX while the reader is stalled actually
  produces abandonment, or whether the Teensy simply blocks in a pending state
  indefinitely with the counter untouched;
- what firmware action or state transition, if any, is *required* to trigger
  abandonment (a superseding RESULT? a timeout? an explicit cancel?).

**Not yet done.** It is pure source reading with no bench risk, and it is queued
ahead of run 4. **If abandonment turns out to require an event we are not willing
to cause, run 4's confirmation criterion has to change** — which is exactly why
this is verified before the wire is touched rather than after.

### 🛑 D3 — the break point is still to be specified

Approved conclusion: **not Pi physical pin 10**, because pin 8 (GPIO14/TXD0) is
adjacent and driven. The exact break point and procedure — preferring a purpose-made
mid-cable junction or the Teensy pin 1 side, after checking neighbouring conductors
and whether the boards should be powered — is produced and reviewed **before** run 4.

---

## The option sets that produced those decisions, retained for the reasoning trail

### D1 — Step 11 requires running validation Tests 1–4 in run 3. Your standing rule forbids them.

Step 11, verbatim: *"**Also verify in runs 3 and 4:** the firmware stays fully
responsive on USB Serial, and the validation suite (`1`–`4`) still runs and
passes with the Pi stalled. A dead renderer must not be able to fail a
measurement."* TODO-35 repeats it: *"Validation suite still runs and passes in
run 3."*

This is a **documented acceptance criterion**, so invoking it here would not be
"casual" — but it is still Phase 9's harness, it has never been runtime-tested on
this hardware, and it blocks the main loop by design. **Options:**

- **(a) Run them in run 3 as written.** T1 closes fully. Accepts first-ever
  runtime execution of the validation harness during a timing-sensitive run.
- **(b) Defer the clause.** Record it as explicitly outstanding, and T1 closes
  *except* for "a dead renderer cannot fail a measurement". Substitute a weaker
  but honest USB-responsiveness check: `i`, `j`/`k` and `T` all answer while the
  Pi is stalled. **This is what I would do** — the clause is about USB liveness
  under backpressure, and Tests 1–4 are a heavyweight way to ask that question
  while carrying their own unvalidated risk.
- **(c) Run them, but in a separate window after `T` is captured**, so a
  validation-induced timing artefact cannot contaminate the T1 figures. Costs
  nothing except time, and it satisfies the clause without mixing the two.

**Nothing below assumes an answer.** Run 3's procedure has the check marked
`[D1]` at the point it would happen.

### D2 — Run 4 asks you to pull a wire inside a 102 ms window. That is not hand-achievable.

Step 11's run 4 is *"TX wire **pulled while a RESULT is draining**"*. Measured on
2026-09-27 with a normally-consuming reader: **`max drain 102 ms`**. A hand-timed
pull will miss it almost every time, and `result_bytes_abandoned = 0` means run 4
did not happen (the differ flags exactly this).

**Options:**

- **(a) Perform run 4 with the reader already suspended** (run 3's condition).
  The 4 096 B TX buffer fills, the 8 908 B RESULT cannot complete, and the drain
  stays pending for as long as the reader is stopped — seconds or minutes, not
  milliseconds. The pull then lands inside the drain with near-certainty.
  **Recommended.** It is a deviation from the literal wording (which does not say
  the reader is stopped in run 4) and it makes run 4 "backpressure **and** loss
  mid-transaction" rather than loss alone. It still satisfies the stated role —
  *loss mid-transaction* — and `result_bytes_abandoned > 0` is the objective
  confirmation either way.
- **(b) Attempt it with a live reader and repeat until `result_bytes_abandoned >
  0`.** Faithful to the wording, likely several attempts, each needing a fresh
  `m` and therefore a fresh RESULT.
- **(c) Do both.** (a) first to establish the behaviour, then (b) once for
  fidelity to the text.

**Confirm which before the board is touched**, because (a) changes run 4's Pi-side
setup.

### D3 — Where the TX wire is broken is a real electrical decision.

**Do NOT break the link at Pi physical pin 10.** Pin 10 (GPIO15/RXD0) sits
directly beside **pin 8 (GPIO14/TXD0)**. With the header UART enabled, GPIO14 is
a **driven 3.3 V output**. A jumper slipping sideways from pin 10 onto pin 8
connects the Teensy's TX output directly to the Pi's TX output — two push-pull
drivers fighting, which is a genuine damage path for both.

**Safe break points, in order of preference:**

1. **A mid-cable DuPont junction** away from every other conductor — best, because
   nothing conductive is within reach of a slip.
2. **Teensy pin 1.** Its neighbours are pin 0 (RX1, unconnected) and pin 2. A slip
   onto pin 0 is a harmless TX→RX loopback on the same MCU.
3. **Pi pin 10 — only if 1 and 2 are impossible**, and then only pulling straight
   up and away, never toward the pin 8 side.

`MEAS`/`PHYS` note: no rail is shared between the boards and the line carries no
inductive load, so making and breaking it while powered is otherwise benign.

---

## `_NONE` boot / electrical safety review

**Question:** can flashing and booting `DISPLAY_TARGET_NONE` change routing,
relay state, generator/injection state, GPIO configuration, or analog behaviour,
relative to the `_PI` image currently on the board?

**Answer: no, and the reason is structural rather than incidental.**
`guitar_rig_analyzer.ino` contains **no `#if DISPLAY_TARGET` guard anywhere**.
Every hardware bring-up call runs unconditionally and identically under both
targets; only `presentation_*()` dispatch differs, inside
[presentation.cpp](../firmware/guitar_rig_analyzer/presentation.cpp).

| Subsystem | Call site | Differs under `_NONE`? | Evidence |
|---|---|---|---|
| Relay GPIOs | `signalRouter_init()` — [.ino:402](../firmware/guitar_rig_analyzer/guitar_rig_analyzer.ino#L402) | **No** | `pinMode(OUTPUT)` + `digitalWrite(LOW)` on both relay pins, unconditional ([signal_router.cpp:210-214](../firmware/guitar_rig_analyzer/signal_router.cpp#L210)) |
| Relay state at boot | same | **No** | both **de-energised (LOW)**; `applyReturnRelay(TS)` |
| Return source | same | **No** | `ReturnSource::TS` on every boot, never restored from storage (ADR-004) |
| Injection | same | **No** | `s_injection_active = false`; `ENABLE_DUT_INJECTION` is 0 |
| Monitor mode | same | **No** | `MonitorMode::SOURCE_RETURN`; `ENABLE_MONITOR_MODE` is 0 ([config.h:358](../firmware/guitar_rig_analyzer/config.h#L358)) |
| Jack-detect GPIOs | same | **No** | four × `INPUT_PULLUP`, unconditional |
| Generator | `signalGen_init()` — [.ino:356](../firmware/guitar_rig_analyzer/guitar_rig_analyzer.ino#L356) | **No** | sine and noise amplitude `0.0f`, `GeneratorState::IDLE` ([signal_generator.cpp:323](../firmware/guitar_rig_analyzer/signal_generator.cpp#L323)) |
| Codec / I2S / AudioMemory | `audioCap_init()` | **No** | unconditional, fatal-halt on failure in both |
| Validation harness | `validation_init()` | **No** | print-only; tests reachable only by explicit USB command |
| Calibration / export / SD | `calStore_init()`, `exportEngine_init()` | **No** | unconditional |
| **Serial1 / pin 1 (TX)** | `dataSender_init()` via `presentation_init()` | **YES** | `data_sender.cpp` is compiled out entirely under `_NONE`, so `Serial1.begin()` never runs and **pin 1 stays in reset state (input, high-Z)** |
| **EEPROM session counter** | `nextSessionId()` in `dataSender_init()` | **YES** | the 2-byte flash-emulated EEPROM write **does not happen** under `_NONE`. The session id therefore does **not** advance during run 1 |
| RA8875 pins | `_RA8875` only | **No** | not selected; libraries not linked |

**Consequences of the two differences, both benign:**

- **Teensy pin 1 becomes a floating input.** It is wired to Pi GPIO15/RXD0, which
  the Pi holds with its own internal pull-up when configured as RXD0. A high-Z
  driver against a pulled-up receiver is not a hazard to either device. The Pi
  will simply receive nothing — which is the point of the control run. **Do not
  interpret an empty Pi capture during run 1 as a fault.**
- **No EEPROM write under `_NONE`.** One less boot-time side effect than the `_PI`
  image, so strictly *safer*. It also means the session-id sequence will show
  `_PI` boots only — useful to know when reading the next capture's HELLO.

**Precedent:** the same review was performed for the `44c4680 → 26f2bee`
transition (journal 2026-09-26 (7), and the `_PI` MANIFEST records its summary).
Its conclusion — *"no credible boot-time electrical change to the breadboard; GPIO
modes, relay state, generator/injection and audio routing all unchanged"* —
carries over, and `_NONE` removes the one new side effect that review flagged.

**Residual risk is the flashing operation itself, not the image:** a Teensy reboot
briefly releases every GPIO to its reset state before `setup()` reclaims it. That
already happens on every power cycle of the current image, so it is not new to
`_NONE`.

---

## Firmware artifacts — what can be reused, what must be built

| Run | Target | Artifact | Rebuild needed? |
|---|---|---|---|
| 2, 3, 4 | `_PI` | **already on the board**, `26f2bee` | **No.** No flash at all if these run first |
| 2, 3, 4 (restore) | `_PI` | [`ai/evidence/firmware/26f2bee-PI/guitar_rig_analyzer.ino.hex`](../ai/evidence/firmware/26f2bee-PI/guitar_rig_analyzer.ino.hex) | **No — flash the archived hex, do not rebuild** |
| 1 | `_NONE` | **does not exist** | **Yes**, one build + one new manifest |

**Why the archived `_PI` hex is the right way back.** `__DATE__`/`__TIME__` are
stamped into the image ([.ino:215](../firmware/guitar_rig_analyzer/guitar_rig_analyzer.ino#L215)), so
recompiling `26f2bee` produces a **different binary with a different hash** and
the board could no longer be matched against the flashed-artifact record. Its
MANIFEST says so outright: *"This is the artifact to flash. Do not rebuild."*
`arduino-cli upload -i <hex>` (verified available: `arduino-cli 1.4.1`, `-i,
--input-file` supported) restores the exact known-good binary, and the board must
then print `Build: Sep 26 2026 16:36:53   v0.6.0`.

**Source-drift check, done 2026-09-27:** the only firmware-source difference
between `26f2bee` and the current tree is a **comment-only** edit to
`data_sender.h`. The `_NONE` build will therefore be behaviourally equivalent to
`26f2bee` apart from `DISPLAY_TARGET` — but it is still a *different binary* and
needs its own manifest with its own hash.

### Build command for run 1 (not executed)

```
# one line changed in config.h:129 —  DISPLAY_TARGET DISPLAY_TARGET_NONE
arduino-cli compile --clean --fqbn teensy:avr:teensy41 \
    --output-dir ai/evidence/firmware/<sha>-NONE firmware/guitar_rig_analyzer
```
Record: warnings (**must be 0**), FLASH code/data/headers, RAM1/RAM2, the
extracted `__DATE__`/`__TIME__`, md5 and sha256 — same MANIFEST shape as
`26f2bee-PI`. **Then revert `config.h` before anything else is built.**

---

## ★ Minimum flash sequence

**One flash completes all four runs. Two returns the board to the known-good image.**

```
  board is HERE:  _PI  26f2bee  (known good, flashed 2026-09-26)
        │
        ├── PHASE A — NO FLASH ─────────────────────────────
        │     boot ▸ run 2   (reader consuming)
        │     boot ▸ run 3   (reader kill -STOP)
        │     boot ▸ run 4   (TX broken mid-drain)      [D2]
        │
        ├── FLASH 1 ▸ _NONE (new build) ───────────────────
        │     boot ▸ run 1   THE CONTROL
        │
        └── FLASH 2 ▸ archived 26f2bee-PI hex ─────────────
              boot ▸ run 2-REPEAT  (drift control, optional)
              board is back on the known-good image
```

**Why runs 2–4 come first, even though run 1 is "the control":**

1. **It costs zero flashes.** The board already runs `_PI`.
2. **If run 2 fails, the known-good image was never disturbed.** A blocking path
   found in run 2 means stop (step 11 says so), and you stop with the board in
   exactly the state today's RESULT evidence was gathered on.
3. Run 1's ordering is an **analysis** dependency, not an execution one. Nothing
   in step 11 or `timing_probe.h` requires the control to be captured first.

**The cost, and the mitigation.** If bench conditions drift between run 4 and run
1, the control is compromised and the whole matrix is void. So:

- **Log SOURCE_NODE peak dBFS at the start and end of every run** from the 5 s
  diagnostics. The stimulus must read the same to within ~0.5 dB across all four.
- **Flash 2 + run 2-repeat is the drift control.** If run-2-repeat matches run 2,
  the bench did not move and run 1 is a valid control for all of them. This is
  free, because flash 2 is one you want anyway to restore the known-good image.

---

## Conditions held identical across all four runs

Step 11: *"Run all four under identical window length and identical signal
conditions. A guitar left plugged in and untouched is fine; an inconsistent input
is not, because block timing depends on it."*

| | |
|---|---|
| Window | **EXACTLY 120 s for every run.** Fixed 2026-09-27. Authority requires "≥60 s, identical" (step 11, TODO-35) and says longer is better for the max figures; 120 s satisfies both and removes the operator judgment. **Do not vary it between runs.** |
| Stimulus | the ~1 kHz phone → USB-C DAC → TRS→TS → J4 source, **left running untouched** across all four runs. It read **−21.8 dBFS** on 2026-09-27 and armed reliably |
| Route | TS return, no injection — the boot default, do not touch `j`/`k` |
| Link wiring | unchanged: Teensy pin 1 → Pi pin 10, GND → pin 9, pin 0 and GPIO14 unconnected |
| Pi | booted, `/dev/ttyAMA0`, `stty` applied once per boot |
| USB | Serial Monitor open on the Teensy for the whole run |

> **⚠️ Stimulus is required for runs 2–4 and irrelevant to run 1.** Run 4 needs
> `m` to reach RESULT, which needs a real source above the arm threshold. Keeping
> the same stimulus for run 1 costs nothing and removes a variable, so leave it
> playing. If the phone cannot survive four runs, **charge it before starting** —
> a stimulus change mid-matrix voids the comparison.

---

## 🔺 Two accounting defects found while preparing this — read before reading any report

### Transport figures are BOOT-scoped, not window-scoped

`timingProbe_reset()` (the `t` command) clears **only** the `[T1]` acquisition
accumulators. `dataSender_resetStats()` is called **once, from
`dataSender_init()`** — nowhere else. So every `[Link]` figure is cumulative
since power-on, and `TX room min` is a **min-since-boot** high-water mark.

**Consequence for the matrix:** if runs 2, 3 and 4 share one boot, run 3's drop
counts include run 2's, and once `TX room min` hits 0 in run 3 it reads 0 in run 4
forever. **Therefore: reboot between every run.** A reboot is free, needs no
reflash, resets the `[Link]` block, and increments the session id — which is the
observable the differ uses to catch two runs sharing a boot.

**This also explains the `TX room min: 0 B` seen on 2026-09-27**: it was a
min-since-boot figure from a session that had already drained a full RESULT.
Nothing timestamped it against the drain. Tracked as **TODO-63**.

### `TX room min: 0 B` is ambiguous in the current build

[data_sender.cpp:1002](../firmware/guitar_rig_analyzer/data_sender.cpp#L1002) prints
`(s.tx_room_min == 0xFFFFFFFFu) ? 0UL : s.tx_room_min` — so the **never-sampled
sentinel prints as 0**, indistinguishable from a genuinely observed zero. In `_PI`
with traffic flowing the sentinel is always overwritten, so today's reading was
real, but the display collapses "unknown" into a meaningful value, which the
project's own rule forbids. Tracked as **TODO-64**. **Not a blocker for T1** —
just do not read `TX room min: 0` in a run with zero `send_calls` as evidence of
anything.

### Everything else the report consumes IS window-scoped — audited, not assumed

Asked directly: does a reboot plus `t` really reset every metric the report and the
differ consume? Traced call site by call site 2026-09-27.

| Report line | Source | Scope | Reset by |
|---|---|---|---|
| `window_ms` | `millis() - s_window_start_ms` | window | `t` |
| `block_n`, `block_ms_mean/max/min/spread` | `timing_probe.cpp` statics | window | `t` |
| `blocks_skipped`, `skip_events`, `largest_block_gap` | same | window | `t` |
| `loop_iters`, `loop_us_max`, `loop_us_mean` | same | window | `t` |
| `audio_blocks_high_water` | `AudioMemoryUsageMax()` | window | `t` → `AudioMemoryUsageMaxReset()` |
| `audio_blocks_used` | `AudioMemoryUsage()` | instantaneous | n/a |
| `display_target`, `firmware`, `protocol` | compile-time | constant | n/a |
| **entire `[Link]` block** | `s_stats` in `data_sender.cpp` | **BOOT** | power cycle only (TODO-63) |

**Verified exhaustively:** `timingProbe_reset()` is called from exactly two places
— `setup()` ([.ino:363](../firmware/guitar_rig_analyzer/guitar_rig_analyzer.ino#L363)) and the `t` command
([.ino:602](../firmware/guitar_rig_analyzer/guitar_rig_analyzer.ino#L602)). `AudioMemoryUsageMaxReset()` is
called from exactly one place, inside `timingProbe_reset()`. `dataSender_resetStats()`
is called from exactly one place, `dataSender_init()`. Nothing else resets any of
them, and no other command (`r`, `u`, `m`, `x`, `j`, `k`) touches them.

**One skip-detector subtlety, and it is handled correctly.** `output_block_number`
is monotonic from the capture layer and is *not* reset by `t`. But
`timingProbe_reset()` clears `s_have_block_number`, so the first block after `t`
establishes a fresh baseline instead of reporting a huge gap. A `t` mid-stream
cannot manufacture a false `blocks_skipped`.

**The sketch's own counters do NOT reach the report.** `s_total_blocks`,
`s_total_displays` and `s_loop_iterations` are boot-scoped statics feeding only the
5 s diagnostic block, and that block prints *deltas* against `s_diag_blocks_prev` /
`s_diag_displays_prev`. None of them appear in `[T1]`, so they cannot contaminate
the comparison.

**What reboot-per-run actually buys.** With one boot per run, boot scope collapses
onto run scope, which is what makes the differ's run-3/run-4 transport expectations
meaningful at all. **But `[Link]` still covers slightly MORE than the window** — it
includes the ~10 s settle before `t` and anything after `T`, plus the boot-time
measurement self-test. Say "per boot", not "per window", when writing transport
figures up.

### ⚠️ `loop_us_max` is dominated by the 5 s diagnostic print, in every run

[.ino:930](../firmware/guitar_rig_analyzer/guitar_rig_analyzer.ino#L930) closes the loop-body timer as the
**last statement in `loop()`**, deliberately, so the measured duration covers the
5 s diagnostic print on the iterations where it fires — the source comment says so.

**Consequence:** `loop_us_max` is essentially *"the worst 5 s-diagnostic
iteration"*, not *"the worst transport iteration"*. And because that print is one
line under `_NONE` and about fourteen under `_PI`, **`loop_us_max` is the single
metric most contaminated by the print asymmetry.** Expect it higher in runs 2–4
for reasons that have nothing to do with the transport.

Step 11 asks only that `loop_us_max` be *"comparable to run 1"* — not identical —
and the decisive metrics are `block_ms_*` and `blocks_skipped`. **Do not read an
inflated `loop_us_max` in runs 2–4 as a transport fault without first accounting
for the extra USB printing.**

### A confound that cannot be removed without a firmware change

The 5 s diagnostic block calls `presentation_printDiagnostics()` unconditionally.
Under `_NONE` that is **one line**; under `_PI` about **fourteen**. So the control
run does measurably less USB printing than runs 2–4.

**The bias runs against runs 2–4** — they carry the extra print load — so if they
still match the control, the conclusion is safe. Record it; do not use it to
excuse a marginal failure.

---

## The runs

### Preparation (no flash, no bench change)

```
[ ]  stimulus playing, phone charged, SOURCE peak logged: ______ dBFS
[ ]  Pi booted, USB Serial Monitor open on the Teensy
[ ]  no serial-MCP process holding the port:  lsof /dev/cu.usbmodem*
[ ]  Pi tty configured once per Pi boot:
     sudo stty -F /dev/ttyAMA0 460800 cs8 -cstopb -parenb -crtscts \
          raw -echo -echoe -echok -ixon -ixoff -icrnl -onlcr min 1 time 0
```

> **`capture.sh` is deliberately NOT used for runs 2–4.** It wraps the reader in
> `timeout`, and SIGTERM sent to a `kill -STOP`ped process stays *pending* until
> SIGCONT — so run 3 would hang the script and leave the reader in an unclear
> state. Use a bare backgrounded reader whose PID you own. `capture.sh` remains
> the right tool for ordinary evidence captures.

### Per-run procedure (identical shape every time)

```
1.  Power-cycle the Teensy.            <- mandatory: resets the [Link] block
2.  Confirm the banner:  Build: ____________________  v0.6.0
                         Display target: ______________
                         Session id: ____   (absent under _NONE)
3.  Set up the Pi-side reader for this run (below).
4.  Let it settle ~10 s. Log SOURCE peak: ______ dBFS
5.  Press  t        <- starts the window (setup() also starts one at boot)
6.  Wait the FIXED window: 120 s   (same for all four, no exceptions)
7.  Press  T        <- the report
8.  Save the WHOLE console paste verbatim to the filename below.
9.  Log SOURCE peak again: ______ dBFS
```

### Run 2 — `_PI`, reader consuming normally

**➡️ Full deterministic operator card: [T1_run2_procedure.md](T1_run2_procedure.md).**
Run 2 uses the repo tool `pi/tools/capture.sh`, **not** an ad-hoc `cat`: run 2
needs no suspension, so the tool that already sets the tty, enforces the duration,
and prints bytes/sha256/rate is the right reader. The ad-hoc backgrounded `cat` is
needed only for runs 3 and 4, where the PID must be ours to `kill -STOP`.

### Run 3 — `_PI`, reader suspended (sustained backpressure)

```
Pi:  cat /dev/ttyAMA0 > run3.bin &   ; echo $!   -> PID ______
     let it consume ~5 s, then:   sudo kill -STOP <PID>
     leave it STOPPED for the whole window
     afterwards:                  sudo kill -CONT <PID> ; kill <PID>
Save: ai/evidence/t1-run3-pi-stalled.txt
Expect (step 11): live frames DROPPED — that is the policy working.
                  TX room min 0 — backpressure correctly absorbed.
                  HELLO drops ~1/s — expected, NOT a defect (TODO-56).
[D1]  While STOPPED, confirm USB stays responsive.
      Minimum:   i , j , k , T  all answer.
      If option (a) or (c) was chosen: also run validation 1-4 and record
      PASS/FAIL. Under (c), do this AFTER `T` is captured.
```

### Run 4 — `_PI`, TX broken mid-RESULT-drain  `[D2]` `[D3]`

```
Pi:  per the D2 option you chose (recommended (a): reader STOPPED first)
Teensy:  press  m   -> wait for RESULT to be staged
Break the link at the point chosen in D3 — NOT at Pi pin 10
Restore the link, then press  T
Save: ai/evidence/t1-run4-pi-pulled.txt
CONFIRM THE RUN HAPPENED: result_bytes_abandoned > 0.
   If it is 0 the pull missed the drain and run 4 must be repeated.
   The differ flags this for you.
Expect: non-zero abandoned result bytes is CORRECT (step 11).
```

### Run 1 — `_NONE`, THE CONTROL  (after FLASH 1)

```
Build + archive + manifest per "Firmware artifacts" above.
Flash, then confirm the banner says:  Display target: none
Pi:  nothing to do. Pin 1 is high-Z; the Pi will receive NOTHING.
     That is correct and is not a fault.
Save: ai/evidence/t1-run1-none-control.txt
Expect: the [Link] block is replaced by the single line
        "[Link] No display backend compiled in (DISPLAY_TARGET_NONE)."
```

### Run 2-repeat — drift control (after FLASH 2, optional but cheap)

```
Flash the ARCHIVED 26f2bee-PI hex:
    arduino-cli upload -i ai/evidence/firmware/26f2bee-PI/guitar_rig_analyzer.ino.hex \
        --fqbn teensy:avr:teensy41 -p <port>
Confirm:  Build: Sep 26 2026 16:36:53   v0.6.0
Repeat run 2 exactly. If it matches the first run 2, the bench did not
drift and run 1 is a valid control for all of runs 2-4.
Save: ai/evidence/t1-run2-repeat-drift-control.txt
```

---

## Reading the four reports

```
python3 pi/tools/t1_diff.py \
    ai/evidence/t1-run1-none-control.txt \
    ai/evidence/t1-run2-pi-normal.txt \
    ai/evidence/t1-run3-pi-stalled.txt \
    ai/evidence/t1-run4-pi-pulled.txt
```

The control is always the **first** argument. Exit codes: `0` clean, `1` the
absolute rule was violated, `3` procedural findings need resolving. **Exit 0 is
not a T1 pass** — see below.

### What the tool checks, and what it refuses to check

| Criterion | Source | Automated? |
|---|---|---|
| `blocks_skipped` = 0 in **every** run | step 11, "no exceptions" | **Yes — enforced** |
| `skip_events` = 0 in every run | step 11 | **Yes — enforced** |
| `largest_block_gap` = 0 in every run | step 11 | **Yes — enforced** |
| identical window length | step 11 | Yes — flagged if >10 % apart |
| control really is `_NONE` | step 11 run table | Yes — flagged |
| runs did not share a boot | TODO-63 (this sheet) | Yes — flagged via session id |
| run 3 actually applied backpressure | step 11 expectations | Yes — flagged |
| run 4 actually hit the drain | step 11 expectations | Yes — flagged |
| `block_ms_mean/max/spread` **indistinguishable from run 1** | step 11, TODO-35 | **NO — reported with deltas, YOURS to judge** |
| `loop_us_max`, `audio_blocks_high_water` **comparable to run 1** | step 11, TODO-35 | **NO — reported, yours to judge** |
| transport drops, `TX room min`, abandoned bytes | step 11: "allowed to degrade" | **NO — reported, never judged** |

**Why the comparative metrics are not automated.** No authority in this project
defines "indistinguishable", and `timing_probe.h` says there is deliberately *"no
threshold to argue about — the control run is the threshold"*. A tool that picked
a number would be inventing an acceptance criterion and handing back a green tick
nobody authorised. Step 11 also warns: **"DO NOT PASS THIS STEP ON A SMALL CALL
TIME."**

**A worked reason to distrust percentages.** In a smoke test, a 0.2 ms change in
`block_ms_max` showed as **`block_ms_spread +33.3 %`**, because the spread is a
small difference of two large numbers. A percentage gate would have failed a
healthy run; an absolute-millisecond eye would not. Read both columns.

### If block timing degrades in any run

Step 11: **stop.** *"The non-blocking policy has been violated somewhere, and no
amount of Pi-side work will fix it. Find the blocking path first"* — starting from
acceptance test B in [pi_link_protocol_audit.md](pi_link_protocol_audit.md).

---

## Evidence to preserve

| Item | Where |
|---|---|
| 4 (or 5) verbatim console pastes | `ai/evidence/t1-run*.txt`, **and verbatim in `ai/journal.md`** (TODO-35: "Keep all four reports verbatim in journal.md") |
| `t1_diff.py` output | the evidence record for the run |
| `_NONE` build: hex + MANIFEST + md5/sha256 + `__DATE__`/`__TIME__` + warnings/FLASH/RAM | `ai/evidence/firmware/<sha>-NONE/` |
| Confirmation the board returned to `Build: Sep 26 2026 16:36:53` | the record and the journal |
| SOURCE peak dBFS at the start and end of each run | the record |
| `run2.bin` / `run3.bin` + sha256 | optional, free extra transport artifacts |
| D1/D2/D3 decisions and any deviation | the record — *deviations are recorded, not smoothed over* |

## What must NOT happen

- **No flash until the operator approves the specific action.**
- **No `v`. No Tests 1–4 unless D1 option (a) or (c) is explicitly chosen.**
- **No internal generator, no injection, no relay or route change, no `j`/`k`.**
- **No rebuild of the `_PI` image** — flash the archived hex.
- **No breaking the link at Pi pin 10** (D3).
- **Do not close T1 on a Teensy-side count.** TODO-34: *"`results_sent` IS NOT
  DELIVERY EVIDENCE."* T1 is about acquisition timing, and delivery is proven at
  the Pi or not at all.
- **Do not close Phase 9.** Unrelated and still open.
- **Do not read `TX room min: 0` as a failure** unless step 11 makes it one. It
  does not: in runs 3/4 it is *"the backpressure, correctly absorbed."*
