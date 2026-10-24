# 🔴 T1's one absolute pass/fail metric counts the wrong stride — found by running Run 2

**2026-09-29.** T1 Run 2 stopped on its own stop condition,
`blocks_skipped = 44490`. **The stop was correct and the metric is wrong.**
Acquisition was healthy; the harness was manufacturing skips arithmetically.

Firmware `dcfbffa`, unmodified. No flash, no firmware edit, no retry.
Primary record: [`t1-run2-pi-normal.txt`](t1-run2-pi-normal.txt).

## The numbers that gave it away

| | |
|---|---|
| `block_n` | **2966** |
| `skip_events` | **2966** — *exactly equal to `block_n`* |
| `blocks_skipped` | **44490** = 2966 × 15, exactly |
| `largest_block_gap` | **16** — a *constant*, not a spike |
| `block_ms_mean` | **46.440 ms** |
| `block_ms_spread` | **0.089 ms** across 2966 blocks |

**Every single analysis block was flagged as having skipped exactly 15
predecessors.** That is not how real disturbance behaves — real overruns are
bursty and produce a variable gap. A fixed stride is arithmetic.

**The decisive identity:**

```
block_ms_mean / largest_block_gap  =  46.440 / 16  =  2.9025 ms
128 samples / 44100 Hz             =              =  2.9025 ms
```

Exact to four decimal places. The counter the detector reads ticks **once per
128-sample audio block**, not once per analysis block.

## Root cause, traced through source

Three facts, each verified in the tree:

1. **[timing_probe.cpp](../../firmware/guitar_rig_analyzer/timing_probe.cpp) `timingProbe_noteBlock()`** tests
   `gap > 1` and charges `gap - 1` skips, on the stated assumption that *"the
   block counter is the system's canonical monotonic timebase, so a gap > 1
   means an analysis block was produced that the main loop never processed."*
2. **[audio_engine.cpp:338](../../firmware/guitar_rig_analyzer/audio_engine.cpp#L338)** —
   `frame->output_block_number = block.audio_block_counter;`
3. **[audio_capture.h:103](../../firmware/guitar_rig_analyzer/audio_capture.h#L103)** — `audio_block_counter` is
   *"the master timebase. Increments once per"* 128-sample audio block.

So the field named `output_block_number` carries the **audio-block** counter.
The analysis block advances 2048 samples = **16** audio blocks, so the correct
expected stride is 16 and the detector's expected stride is 1.
**2966 × (16 − 1) = 44 490.** The whole figure is explained with nothing left
over.

### The field name is actively misleading, and there are two counters

`audio_capture.cpp` holds a **second**, different counter:

- **[audio_capture.cpp:226](../../firmware/guitar_rig_analyzer/audio_capture.cpp#L226)** `s_output_block_number`,
  annotated *"a separate display-only counter that increments once"* per
  analysis block, and at
  **[:791](../../firmware/guitar_rig_analyzer/audio_capture.cpp#L791)** *"display-only counter; **NOT** the
  timing primitive."*

That counter — the one whose stride really is 1 per analysis block — is the one
the detector needs, and it is **not** what gets copied into the frame.
**[audio_engine.h:195](../../firmware/guitar_rig_analyzer/audio_engine.h#L195)** documents the field as
*"Increments each time capture() returns true"*, which is **false** for the
value actually assigned. A wrong comment fed a wrong instrument.

## Why acquisition was in fact healthy — three independent corroborations

1. **The 5 s diagnostic block, which uses a different counter entirely**,
   reported **107–108 blocks per 5000 ms** in *every* block across the whole
   137.8 s window — the expected ~21.5 analysis blocks/s. Had 15 of every 16
   blocks genuinely been lost, this would have read ~7.
2. **The measured period is 46.440 ms with 0.089 ms spread over 2966 blocks.**
   If blocks were being dropped, the *interval between processed blocks* would
   have stretched to ~743 ms. It did not move at all.
3. **Zero transport drops**: live 4712/0, STATE 438/0, HELLO 220/0,
   ROUTER 219/0, events 5/0; call time max 282 µs.

## 🛑 The consequence for T1

**This metric would have failed every run of the matrix, including the
`DISPLAY_TARGET_NONE` control.** The stride is a property of the firmware's own
timebase, not of whether a Pi is attached — run 1 would have reported the same
~15 phantom skips per block.

So, stated precisely:

- **T1 cannot be adjudicated with the harness as built.** `blocks_skipped`,
  `skip_events` and `largest_block_gap` are the only criteria the project states
  *absolutely* ("0 in every run, no exceptions" — runbook step 11, TODO-35), and
  all three are currently unevaluable.
- **This is not a Phase 10 transport finding.** It is a defect in
  `timing_probe.{h,cpp}` (TODO-39), which was **compile-verified only** and had
  never been run on hardware. Run 2 is the first time it executed.
- **Run 2's acquisition data is still good evidence** — `block_ms_*`,
  `loop_us_*` and `audio_blocks_high_water` are independent of the defect. Only
  the skip family is affected.

**🔑 The project already knew the tick rate.** [`pi/tools/replay.py`](../../pi/tools/replay.py)
documents this same counter as *"AUDIO_BLOCK_SAMPLES/SAMPLE_RATE per tick …
measured against this project's own 30 s hardware fixture as 2.9027 ms/tick
versus 2.9025 ms theoretical."* The **Pi-side** tooling had the stride right all
along; the **firmware's own** skip detector did not. The two halves were never
cross-checked, and the compile-only status of `timing_probe` is exactly why.

## What to fix, and what NOT to do

**Do not fix this during acceptance on the current image.** The board runs
`dcfbffa` and that artifact is what the RESULT-transport evidence of 2026-09-27
was gathered against. Changing the firmware to repair its own instrumentation
mid-matrix would invalidate the artifact under test and force the whole Phase 10
evidence chain to be re-established.

The fix itself is small and there are two honest options:

- **(a) Compare against the correct stride.** Derive the expected audio-blocks
  per analysis block from the existing constants rather than hard-coding 16, and
  flag `gap != expected`. Both a gap *larger* and *smaller* than expected are
  findings, which the current `gap > 1` test cannot express.
- **(b) Feed the detector the analysis-block counter.** Put `s_output_block_number`
  on the frame — or add a field — so the stride genuinely is 1. Cleaner
  semantically, but it changes `AudioFrame`, and `output_block_number` is also
  transmitted on the wire ([data_sender.cpp:627](../../firmware/guitar_rig_analyzer/data_sender.cpp#L627),
  `data_sender.h` bytes [2-3]), so the Pi's interpretation would change too.
  **Protocol consequence — do not choose (b) without checking it.**

**Either way, fix the false comment at
[audio_engine.h:195](../../firmware/guitar_rig_analyzer/audio_engine.h#L195) in the same pass,** and rename or
re-document the field so the next reader cannot repeat the mistake.

**Also owed:** a re-run of Run 2 afterwards. Its window was 137.785 s rather
than the fixed 120 s (agent tool-call latency — see deviation 1 in the primary
record), which already exceeds the 10 % window tolerance the differ applies, so
this run could not have served as a window-matched member of the matrix even
with a working skip metric.

## Status changes this record justifies

- **TODO-39** (`timing_probe` harness) — was 🟢 *DONE, compile-verified*. It is
  **not** done: its decisive metric is defective and was never runtime-tested.
  Reopen.
- **TODO-35 / runbook step 11** — T1 is **blocked on the harness**, not on bench
  time. This is the new critical path for closing Phase 10's decisive step.
- **TODO-34 T1** — unchanged and still open.
- **Phase 9** — untouched, still open.
