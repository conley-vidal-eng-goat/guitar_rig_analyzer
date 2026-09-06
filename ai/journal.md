# Guitar Rig Analyzer — AI Journal

Purpose: a running record of *why* decisions were made on this firmware, written for AI readers (Claude, ChatGPT, etc.) picking up the project cold. This is not a changelog of code diffs — it's the reasoning behind them.

How to use this file:
- Newest entry goes at the top, directly below this header block. Older entries move down. Never delete an entry — if a past decision was reversed, add a new entry that says so and explain why; leave the old one in place for the history.
- One entry per session/decision, not per commit. Skip trivial stuff.
- Each entry should answer: why did we do this, what did we consider/reject, and what should the next session know.
- If you are an AI starting a session on this project, read this file top-to-bottom before touching code — the most recent entries are the most likely to still be relevant.
- **Source-of-truth precedence (added 2026-08-25):** the checked *active local tree* (`/Users/conleyvidal/Desktop/guitar_rig_analyzer/`, verified by actually reading the files, not by reading about them) is authoritative for current implementation status. Below that: runbook/bench observations (`docs/breadboard_bringup_v3.md` and actual serial-log/photo evidence) > explicitly staged design docs (contracts, patch headers, `development/`-style staging code) > historical/project-upload snapshots. Never infer "implemented" from a contract doc, a patch file, a staged source file, or a newer-looking version header/comment — verify the actual call path in the active build tree before recording a feature as done.

---

## 2026-09-05 (16) — Raw I2S samples captured: the stream is systematically corrupted. Static I2S format comparison is a clean NEGATIVE — both ends agree exactly

**Why this entry exists:** the diagnosis finally moved from inference to direct evidence. Raw `int16` samples were dumped from the existing `AudioRecordQueue` objects, and the SGTL5000 and Teensy SAI1 register configurations were read from the library sources this build actually compiles. Two substantial results, one positive and one negative.

### The raw sample evidence

A temporary periodic diagnostic (every 5 s: arm → wait for both queues → print 32+32 `int16` → disarm) was added to `audio_capture.cpp`. **It took several attempts to make it observable at all** — a one-shot startup dump is invisible because the Teensy discards serial output before a USB host attaches, and pressing reset re-enumerates the device, tearing down any already-open connection. A periodic print sidesteps both. Four dumps, spanning 150 s of runtime, all with the 1 kHz tone connected:

| Dump | Node | pos of 32 | median(neg) | max |
|---|---|---|---|---|
| 1 | SOURCE | 6 | −3412 | 28229 |
| 1 | RETURN | 6 | −3705 | 23936 |
| 2 | SOURCE | 12 | −3420 | 30589 |
| 2 | RETURN | 9 | −3008 | **32767** |
| 3 | SOURCE | 7 | −3114 | 31635 |
| 3 | RETURN | 8 | −2798 | 22917 |
| 4 | SOURCE | 6 | −2900 | 23457 |
| 4 | RETURN | 6 | −2892 | 26670 |

Across all 196 negative samples: **median −3042, IQR −3781 … −2853.**

**What the sequences show:**
1. **No 1 kHz progression, ever.** A 1 kHz sine at 44.1 kHz must trace a smooth ordered arc over ~44 samples. Not one such run appears in 256 samples. *(Note: an earlier draft argued this from a "maximum adjacent step of ~4670 counts" figure — that bound only holds for a full-scale sinusoid and was overstated as proof. The morphology argument stands on its own and is the correct one.)*
2. **A stable negative DC baseline** near −2900 to −3400, consistent across dumps and **near-identical on both channels**.
3. **Recurring discrete levels** — values repeat closely within and across dumps: ≈−2880, ≈−6530, ≈−8480 (e.g. dump 3 RETURN holds −6528/−6530/−6530/−6523/−6562). A small set of quantised levels, not a continuum.
4. **Burst corruption, not uniform noise.** Dump 4 contains an 11-sample run (SOURCE) and a 12-sample run (RETURN) within ±100 counts of −2880 — long quiet stretches punctuated by wild excursions. Dumps 1–3 have almost none.
5. **Dump 2 RETURN contains exactly `32767`** — the literal maximum, which is what pins the peak meter at `+0.0 dBFS`.

**Bounded conclusion, worded carefully.** The corruption is present in the raw `int16` samples **before any FFT, peak, or mixer arithmetic**, so this is not a level problem and not an interpretation problem. **The external analog front end is strongly ruled out as the cause of this symptom** — it is *not* fully exonerated, because the SGTL5000's own ADC and input circuitry remain upstream of these samples, and codec conversion has not yet been separated from I2S transport.

### The format comparison — a clean negative

Both ends were read from the library source this build compiles (`.../teensy/hardware/avr/1.62.0/libraries/Audio/`), not from documentation or memory.

**SGTL5000** — `audio_capture.cpp:340` calls the no-arg `enable()`, which at `control_sgtl5000.cpp:512-517` delegates to `enable(0)` on a non-KINETISL target, taking the **slave** branch at `control_sgtl5000.cpp:580`: `write(CHIP_I2S_CTRL, 0x0030)`. Decoded against the field table at `control_sgtl5000.cpp:69-103`: SCLKFREQ=0 (**64 Fs**), MS=0 (**slave**), SCLK_INV=0 (**rising edge**), DLEN=0x3 (**16 bit**), I2S_MODE=0x0, **LRALIGN=0 (data starts 1 SCLK after LRCLK — I2S format)**, LRPOL=0.

**Teensy 4.1 SAI1 RX** — `output_i2s.cpp:471-476`, `__IMXRT1062__` branch, reached from `input_i2s.cpp:49`: `FRSZ=1` (2 words/frame), `SYWD=31` (32-bit-clock sync), `MF` (MSB first), **`FSE` (frame sync early — the one-bit delay)**, `FSP`, `FSD` (master), `W0W=WNW=31`, `FBT=31`, `BCP` (samples on rising edge).

**They agree on every parameter:** I2S format with the one-bit delay at both ends, 64 clocks per frame, matching sync width and polarity, matching bit-clock edge, correct master/slave pairing with no contention. The apparent 16-bit vs 32-bit discrepancy is not one — `input_i2s.cpp:73` sets `SADDR = &I2S1_RDR0 + 2` with 16-bit DMA transfers, taking the upper half-word of each 32-bit slot, exactly where an MSB-first 16-bit sample lands. This is the stock arrangement.

**Record this precisely: the static I2S configuration mismatch hypothesis is substantially ruled out** — codec and Teensy are configured as the stock 44.1 kHz / 64-Fs / 16-bit-in-32-bit-slot I2S arrangement with matching roles, polarity, edge and alignment. **Do not record this as "I2S is correct."** The runtime electrical bus can still be wrong even when both register configurations agree; register agreement constrains only the static intent, not what the wires actually carry.

**Next — scope, not firmware.** Stop changing firmware. Measure the bus with the OWON HDS272S, starting with **LRCLK alone** (Teensy pin 20 / shield pin 20): scope ground on breadboard top-blue GND, DC coupling, ~1 V/div, ~10 µs/div. Expect a 0–3.3 V square wave at ≈44.1 kHz, one cycle ≈ **22.7 µs**. LRCLK first because it is the slowest of the three clocks and therefore the cleanest sanity check. Record measured frequency/period, high/low levels, and whether the waveform is clean and repetitive before moving to BCLK.

**Working tree note:** the temporary periodic RAWDUMP block in `audio_capture.cpp` is **uncommitted** and currently flashed to the board. It must be removed once this question is answered — it is marked `TEMPORARY DIAGNOSTIC` with a removal note.

---

## 2026-09-05 (15) — Fork resolved: `available()` is TRUE every window. The analyzers are receiving real, genuinely full-scale samples. The peak bug was real but incidental

**Run:** TODO-28 build (`b6f3dc1`) uploaded and captured. *(The board dropped off USB before the first upload attempt and the upload aborted without writing; it came back after a reconnect and the second attempt succeeded. No wiring was touched.)*

```
[Main] --- 5s diagnostics (uptime 15s) ---
[Main] Block:      107 in 5000ms = 46.7 ms/block
[Main] Loop:         9986771 iterations/5s = ~1997354/sec
[Main] SOURCE_NODE peak: +0.0 dBFS          |   RETURN_NODE peak: +0.0 dBFS
[Main] TF confidence: 100%   persistence: none (all bins live)
[Main] TF spot-check: 120Hz=-0.4dB 500Hz=-0.6dB 1kHz=+1.2dB 5kHz=+0.3dB 10kHz=-0.0dB
```

**The five answers:**

| Question | Answer |
|---|---|
| `[audioCap] peak unavailable: SOURCE` | **Never appears** |
| `[audioCap] peak unavailable: RETURN` | **Never appears** |
| SOURCE_NODE peak | `+0.0 dBFS` |
| RETURN_NODE peak | `+0.0 dBFS` |
| `CLIP_SOURCE` / `CLIP_RETURN` | **Still firing continuously** |

**✅ This takes the second branch of the fork.** `available()` returns true on every window, so the peak analyzers **are** being fed by the Audio Library graph, and `read()` is now only ever called on genuine data. **The `+0.0 dBFS` is real: actual full-scale samples are arriving at the analyzers.** The `AudioAnalyzePeak` bug was a genuine defect and is correctly fixed, but **it was not the cause** — it was masking the fact that the saturation is real.

**Combined with the disconnect test in entry (12), the picture is now tightly bounded.** The codec emits full-scale samples on **both** channels **even with the analog input physically removed**. The Audio Library graph is healthy, the analyzers are fed, the transport carries real data, the analog front end is out of the loop. **The fault is inside the codec or in how it is being clocked.**

**Next test — and a DMM can actually do this.** Continuity proved the wires connect, but it says nothing about whether a *clock is running on them*. A DMM in **DC volts** reads the time-average of a square wave, so a healthy ~50 %-duty clock on a 3.3 V rail measures around **1.6–1.7 V**, while a stuck line reads **0 V or 3.3 V**. That distinguishes "wire connected" from "clock present" with no scope and no code:

| Pin | Signal | Healthy (DC average) | Fault indication |
|---|---|---|---|
| **23** | MCLK (~11.29 MHz) | ~1.6 V | 0 V or 3.3 V ⇒ no clock |
| **21** | BCLK (~1.41 MHz) | ~1.6 V | 0 V or 3.3 V ⇒ no clock |
| **20** | LRCLK (44.1 kHz) | ~1.6 V | 0 V or 3.3 V ⇒ no clock |
| **8** | DOUT (codec → Teensy) | mid-ish, varies | pinned at 3.3 V or 0 V ⇒ codec not driving real data |
| **7** | DIN (Teensy → codec) | varies with content | — |

**Why MCLK is the prime suspect.** `AudioControlSGTL5000::enable()` writes `CHIP_CLK_CTRL` for 256×Fs, meaning the codec expects an **externally supplied MCLK** to derive its ADC clocking. I2C configuration succeeds independently of MCLK — which is exactly why `enable()` returned true and told us nothing. **If MCLK is absent or wrong, the codec's ADC has no valid conversion clock and its I2S output is meaningless, while every other check we have run still passes.** That single condition explains every observation in this entry and entry (12).

---

## 2026-09-05 (14) — Continuity clean on all 7 wires. Found a firmware bug: `AudioAnalyzePeak::read()` is called without `available()`, and its no-data return value is exactly +0.0 dBFS

**Bench:** continuity verified good on all seven signal wires, pad to pin. Combined with Rev D confirmed and the BCLK wire redone, **the interconnect is no longer a credible suspect.** Firmware init order also checked and is textbook-correct: `AudioMemory(128)` → `Wire.begin()` → `enable()` → `inputSelect(AUDIO_INPUT_LINEIN)` → `lineInLevel(5)` → `volume(0.5)` (`audio_capture.cpp:332–362`). MCLK generation confirmed active for the master path — the commented-out `CORE_PIN23_CONFIG` at `output_i2s.cpp:589` is inside `config_i2s_slave()` ("not using MCLK in slave mode"), while the master path this firmware uses sets it at lines 418/450.

**🐛 The find.** `audio_capture.cpp:507–508` reads the peak meters directly:

```c
float peak_src_lin = s_peak_src.read();
float peak_ret_lin = s_peak_ret.read();
```

**Neither call is guarded by `available()`.** From the library (`analyze_peak.h`):

```c
float read(void) {
    int min = min_sample;   // reset value:  32767
    int max = max_sample;   // reset value: -32768
    min_sample = 32767;  max_sample = -32768;
    min = abs(min);         // 32767
    max = abs(max);         // abs(-32768) = 32768
    if (min > max) max = min;       // 32767 > 32768 is false
    return (float)max / 32767.0f;   // 32768 / 32767 = 1.00003
}
```

**When no audio has reached the peak object since the previous `read()`, the function returns 1.00003 — i.e. full scale, i.e. exactly `+0.0 dBFS`.** Not a plausible-looking large number: the precise value that has been on screen for two days, on both channels, with `CLIP_*` latching every window because `peak_dbfs >= CLIP_THRESHOLD_DBFS` trivially holds.

**Why this matters more than a normal bug — it makes the two competing hypotheses indistinguishable.** `+0.0 dBFS` is produced by *both*:
1. the codec genuinely delivering full-scale garbage, **and**
2. the peak object receiving no data at all.

Every reading taken so far is consistent with either. **The measurement instrument's own meter cannot currently tell "saturated" from "silent".** That is why the diagnosis has stalled: more bench tests cannot separate these two cases while the meter collapses them.

**Honest caveat — this is not yet proof the codec is fine.** The FFT does emit at the correct 46.3 ms cadence, and `AudioAnalyzeFFT1024::update()` returns early when `receiveReadOnly()` yields NULL, which suggests blocks *are* reaching that branch of the graph. If blocks reach the FFT they should also reach the peak objects, since both hang off the same mixer outputs (`audio_capture.cpp:149–150`). By that reasoning case 1 is more likely and the bug is incidental. But the reasoning is indirect, and entry (13) is a fresh reminder of what indirect reasoning about this pipeline is worth. **The fix is worth making purely to remove the ambiguity, regardless of which case turns out to hold.**

**Proposed fix (not yet implemented):** guard both reads with `available()`, and when it is false, do not fabricate a level — carry the previous value forward or mark the window invalid, and do **not** latch `CLIP_*` from it. That converts the symptom from "always exactly 0 dBFS" into a signal that actually distinguishes the two cases on the very next run. Tracked as TODO-28.

**Also worth noting for later:** this same defect would silently corrupt real measurements once the path works — any window where a peak object is starved reports full scale and a false clip, which would poison validation tests 1–4 (TODO-9) and any calibration derived from them.

---

## 2026-09-05 (13) — CORRECTION to my own inference: block rate proves NOTHING about data arriving. Teensy is I2S master. Bad DOUT connection is back at the top

**Bench state:** wire 21 (BCLK) redone, shield confirmed **Rev D** (so pin-for-pin wiring is correct), LINE-IN-L reconnected. **No change:**

```
[Main] --- 5s diagnostics (uptime 55s) ---
[Main] Block:      108 in 5000ms = 46.3 ms/block
[Main] SOURCE_NODE peak: +0.0 dBFS   |   RETURN_NODE peak: +0.0 dBFS
[Main] TF spot-check: 120Hz=-0.7dB 500Hz=+1.9dB 1kHz=+0.3dB 5kHz=+0.3dB 10kHz=+1.2dB
```

**❌ Correcting entry (12)'s observation #1.** It argued: *"107 blocks in 5000 ms … `AudioAnalyzeFFT1024` only emits when it has been fed real blocks, so the I2S bus is delivering samples on time. This rules out a dead bus, a missing clock, and a disconnected data line."* **That reasoning is invalid.**

`audio_capture.cpp:85` instantiates **`AudioInputI2S`**, not `AudioInputI2Sslave`. Verified in the library: `AudioInputI2S::begin()` calls `AudioOutputI2S::config_i2s()` (`input_i2s.cpp:49`) — the **Teensy is the I2S master**. It generates MCLK, BCLK and LRCLK itself and clocks samples in on its own schedule **whether or not the codec drives DOUT**. A completely open pin 8 still yields blocks at exactly the correct rate, filled with whatever the floating input reads.

So the 46.3 ms figure confirms only that the Teensy's own clock generation is healthy. **It rules out nothing on the codec side.** Entry (12)'s conclusion — that the analog front end is exonerated — still stands, because that rested on the disconnect test, not on this. Only the "transport works" sub-claim is withdrawn.

**Consequence: "pin 8 is not actually delivering data" returns as the leading hypothesis** — not *unwired* (it is wired, and that correction in entry (11) stands), but potentially **not electrically good**, or the codec is not driving it. A floating or open DOUT reads as garbage at full amplitude on both channels, which is exactly the observation.

This also **weakens entry (12)'s alignment hypothesis**. The "disconnecting L changed R by 1.1 dB" clue is equally well explained by noise on a floating pin drifting between samples — it does not require frame misalignment. Both remain possible; the open-connection explanation is now simpler and fits more of the evidence.

**Method note worth keeping.** This is the second time in two days that a plausible-sounding inference about the *cause* was built on an unverified assumption about the *mechanism*. The fix both times was reading the actual source rather than reasoning from how the system ought to behave. `AudioInputI2S` vs `AudioInputI2Sslave` is one identifier, and it inverts the meaning of the single most-cited number in the diagnosis.

**Next — cheapest test with the highest information, and it needs no code:** power down and **continuity-test all seven signal wires end to end**, shield pad to Teensy pin: 7, **8**, 18, 19, 20, 21, **23**, plus ground. A cold joint on **8 (DOUT)** or **23 (MCLK)** explains every symptom. Test pad-to-pin, not wire-end-to-wire-end — the joint is the suspect, not the copper.

---

## 2026-09-05 (12) — DECISIVE: SOURCE_NODE stays at +0.0 dBFS with the analog input physically disconnected. The analog front end is exonerated; the fault is in the codec/I2S data path

**The test.** With everything powered and running, the red signal wire from `48e` → LINE-IN-L was removed. All shield↔Teensy wiring, shield ground, the op-amp circuit and the 1 kHz source were left in place — deliberately starving the codec of input while keeping the digital path fully alive. Captured over `serial-mcp`:

```
[Main] --- 5s diagnostics (uptime 610s) ---
[Main] Block:      107 in 5000ms = 46.7 ms/block
[Main] Loop:         11358732 iterations/5s = ~2271746/sec
[Main] SOURCE_NODE peak: +0.0 dBFS          |   RETURN_NODE peak: -1.1 dBFS
[Main] TF confidence: 100%   persistence: ACTIVE
[Main] TF spot-check:   120Hz=-2.0dB  500Hz=-1.7dB  1kHz=-0.5dB  5kHz=-1.8dB  10kHz=-1.2dB
```
`CLIP_SOURCE` and `CLIP_RETURN` continue firing throughout.

**✅ Result: SOURCE_NODE remains pegged at `+0.0 dBFS` with no analog signal reaching the codec at all.** This is conclusive. **The analog front end — the OPA1642 buffer, the 0.877 V bias, the coupling caps — is not the cause and is exonerated by this test.** The full-scale condition originates downstream, in the codec, the I2S transport, or the software that consumes it. All the analog work from entries (4)–(6) stands; it was simply never visible through a broken digital path.

**Three observations that narrow it much further:**

1. **Data is flowing at exactly the right rate.** 107 blocks in 5000 ms = 46.7 ms/block, matching the corrected 46.44 ms FFT hop expectation (TODO-27). `AudioAnalyzeFFT1024` only emits when it has been fed real blocks, so **the I2S bus is delivering samples on time.** This rules out a dead bus, a missing clock, and a disconnected data line. The transport works; its *content* is wrong.

2. **The values are not stuck — they move.** RETURN went from `+0.0` to `-1.1 dBFS` when the wire came out. A hard-stuck pattern (all-ones, latched bits) would read exactly 0.0 dBFS forever. Fluctuation near full scale means the samples vary but are saturated — closer to "garbage at full amplitude" than "frozen register".

3. **⚠️ Disconnecting the LEFT input changed the RIGHT channel's reading.** SOURCE_NODE is L, RETURN_NODE is R. Pulling the L wire moved RETURN from `+0.0` to `-1.1 dBFS`. **The two channels are not independent.** In a correctly framed I2S stream they would be. This is the single most diagnostic fact in the capture, and it points hard at **I2S frame alignment** — L and R sample data being interleaved or shifted so that one channel's content leaks into the other.

**Leading hypothesis: an I2S format/alignment mismatch, not a wiring fault.** Bit-length or frame-sync misalignment produces exactly this triad — correct sample *rate*, saturated *values*, and cross-channel contamination. The wiring is pin-for-pin correct for a Rev D shield on a Teensy 4.x (verified against the Audio library source in entry (7)), and the codec answers on I2C, so the remaining suspects are how the codec is framing the data versus how `AudioInputI2S` expects to read it. Worth checking in order: whether the shield is genuinely Rev D rather than a Rev C wired by pin number; whether LRCLK (20) and BCLK (21) are transposed at one end; and the codec's I2S format registers as actually written by `AudioControlSGTL5000::enable()`.

**What this does NOT mean.** It is not evidence the buffer is good — it is evidence the buffer has not yet been *tested*. SOURCE_NODE has never carried a trustworthy number. Phase 4's criterion (SOURCE_NODE visibly and correctly receiving the injected signal) remains unmet, and the expected correct reading is still ≈ **−10.4 dBFS** for the present 0.143 V<sub>rms</sub> input at `LINE_IN_LEVEL 5`.

**Next:** reconnect the LINE-IN-L wire (nothing is gained by leaving it out), then attack the I2S framing question rather than the analog side.

---

## 2026-09-05 (11) — CORRECTION: the I2S interconnect was already wired. Floating-RX hypothesis void; loop rate up 59×; generator and gain both ruled out

**❌ Correcting entry (9) and (10).** Both claimed the I2S lines had never been wired, and built a "floating RX_DATA0" explanation for the `+0.0 dBFS` readings on top of it. **That was wrong, and it was written from stale context** — the interconnect had already been installed and verified: **18→18, 19→19, 23→23, 21→21, 20→20, 8→8, 7→7**, plus power and ground. Pin 8 is connected, so a floating RX line cannot be the cause. The wiring must not be redone or disturbed.

**Why the error is worth recording rather than quietly fixing:** it is the same failure this journal already has a standing rule against — reasoning from a document (my own earlier note) instead of from the current state of the bench. The rule exists because it has cost this project days once already, and it caught me here too.

**New evidence from a fresh capture (uptime 430 s, guard build):**

```
[Main] Block:   107 in 5000ms = 46.7 ms/block (expected 92.9 ms, delta -46.2 ms)
[Main] Loop:    11355891 iterations/5s = ~2271178/sec
[Main] SOURCE_NODE peak: +0.0 dBFS   |   RETURN_NODE peak: +0.0 dBFS
[Main] TF confidence: 100%   persistence: none (all bins live)
```

**The display guard's effect is larger than entry (10) recorded.** Loop rate is now **~2.27 M iterations/s against ~38 k/s before** — a **59× increase**, on top of the 47× block-period recovery. The unguarded SPI was consuming essentially the entire main loop. Block period holds at 46.7 ms, consistent with the 46.3 ms in entry (10) and with the corrected 46.44 ms expectation (TODO-27).

**Boot lines finally observed** (recovered from the buffer rather than a clean reset): `[Validation] Harness ready (v0.5.0)`, analysis band 200–10000 Hz, `[CalStore] SD not available` and `[ExportEngine] SD not available` (expected — no card), and the SigGen block.

**Two candidate explanations ruled out by reading the tree:**
1. **Generator bleeding into RETURN.** `[SigGen] Output wired to monitoring R (headphone right) via s_mixer_ret slot 2` is a genuinely suspicious line — RETURN_NODE *is* the R channel. But the default route mutes it: `audio_capture.cpp:280` sets `s_mixer_ret.gain(2, 0.0f)`, and `signal_generator.cpp:331/335` initialise both oscillator amplitudes to 0.0. Not the cause.
2. **Input gain too high.** `SGTL5000_LINE_IN_LEVEL` is **5**, the library default = **1.33 V<sub>pp</sub> full scale**. The present analog input is ~0.143 V<sub>rms</sub> = 0.404 V<sub>pp</sub>, which should read ≈ **−10.4 dBFS**. Not the cause either — and this is a useful number to keep, because it says what a *correct* reading would look like.

**Where that leaves the diagnosis.** `s_peak_src` and `s_peak_ret` sit directly after the channel-select mixers (`audio_capture.cpp:150`) with the route `SOURCE_NODE=L, RETURN_NODE=R`, so these values are the I2S L and R channels. **Both reading exactly full scale, in lockstep, with a flat 0 dB TF at 100 % confidence, is a digital signature rather than an analog one** — that is what identical saturated data on both channels looks like. Leading hypotheses are now an I2S clocking fault despite the wires being present (BCLK/LRCLK on 21/20 transposed, or a marginal MCLK joint on 23) or the codec's ADC emitting a stuck pattern. **The codec answering on I2C proves nothing about the I2S bus** — that distinction is the thing to hold onto.

**Next:** the disconnect-LINE-IN-L test (TODO-26) is exactly the right discriminator and should be run before anything else — it separates "analog input is overdriving" from "the digital path is producing garbage" with one wire and one diagnostic window.

---

## 2026-09-05 (10) — Display guard CONFIRMED on hardware: 2194 → 46.3 ms/block, a 47× recovery. And the "expected 92.9 ms" constant is itself wrong by 2×

**Why this entry exists:** on-hardware verification of TODO-25's guard (committed `8548c4c`, uploaded and run). The pass criterion was a measurement, not a compile, and it passed decisively. Investigating the residual discrepancy then turned up a separate firmware bug.

**✅ The guard works. Measured, before and after:**

| | Blocks | Window | Period |
|---|---|---|---|
| Before (`9037726`) | 3 | 6583 ms | **2194.3 ms/block** |
| After (`8548c4c`) | **108** | 5000 ms | **46.3 ms/block** |

A **47× improvement**, and stable across consecutive diagnostic windows (uptime 20 s and 25 s both report 108 blocks / 46.3 ms). The unguarded `waitPoll()` spin against the absent RA8875 was the entire bottleneck, exactly as diagnosed in entry (9). TODO-25's proof criterion is met.

**🐛 New finding — the firmware's own expectation is miscalculated, and it makes a correct system look broken.** The diagnostic now reports `46.3 ms/block (expected 92.9 ms, delta -46.6 ms)` — apparently running 2× *too fast*. It is not. **The constant is wrong.**

`guitar_rig_analyzer.ino:99`:
```c
static const float EXPECTED_BLOCK_MS =
    1000.0f * FFT_AVERAGE_COUNT * FFT_SIZE / (float)SAMPLE_RATE;
    // = 1000 × 4 × 1024 / 44100 ≈ 92.9 ms
```

That assumes `AudioAnalyzeFFT1024` consumes 1024 fresh samples per result. **It does not — it runs 50 % overlap.** Verified in the Audio library source (`analyze_fft1024.cpp`): after setting `outputflag = true` it resets `state = 4`, retaining the most recent 4 blocks (4 × 128 = 512 samples) and needing only 512 new samples for the next FFT. The true emission period is therefore the **hop size**, not the window:

> 1000 × FFT_AVERAGE_COUNT × (FFT_SIZE / 2) / SAMPLE_RATE = 1000 × 4 × 512 / 44100 = **46.44 ms**

Measured **46.3 ms** — agreement to 0.3 %. **The hardware is running at exactly the correct rate; the expectation is off by a factor of two.** `EXPECTED_BLOCK_MS` should use `FFT_SIZE / 2`. It is diagnostic-only (the printf at line 186 and the delta at line 555), so behaviour is unaffected — but left as-is, every diagnostic report forever shows a phantom −46.6 ms anomaly, which is precisely the kind of false signal that costs this project days. Tracked as TODO-27.

**🚨 Unchanged, and expected to be: both nodes still read `+0.0 dBFS` with continuous `CLIP_SOURCE`/`CLIP_RETURN`.** The display guard was never going to affect this, and it didn't. This remains TODO-26 — the I2S data path. Note the clip spam is now *denser* than before simply because the pipeline runs 47× faster, so it fills the capture buffer quickly; that is a symptom of the fix working, not a new problem.

**⚠️ Boot banner still not captured.** The 60 s capture window opened right after the upload, and the first diagnostic already reports uptime 20 s — so the board had booted (at upload) and printed its banner before the port was open, and no reset occurred during the window. The init sequence, including whatever `audioCap_init()` reports about the codec and whether the new `[DisplayEngine] ERROR: RA8875 not found` line appears, is still unobserved. **A reset with the port already open is still owed.**

**Next:** (1) wire the I2S interconnect (TODO-26) — the one thing standing between this bench and a real measurement; (2) fix `EXPECTED_BLOCK_MS` (TODO-27); (3) capture a genuine boot banner.

---

## 2026-09-05 (9) — Display init non-fatal: boot now reaches audio and the codec initialises. But the live path is 23.6× too slow, and BOTH nodes read +0.0 dBFS — including the one with nothing plugged into it

**Why this entry exists:** records the first successful run of the full pipeline on this bench, and two serious problems the run exposed. Captured over `serial-mcp` rather than transcribed by eye.

**✅ The primary question is answered: YES.** `displayEngine_init()` failing no longer halts the sketch. The board reaches `audioCap_init()` and `audioEngine_init()`, both succeed, and it is running in `loop()` — captured at uptime 82–115 s, emitting its 5 s diagnostics and reporting `Route: Default bench: SOURCE_NODE=L, RETURN_NODE=R`. **The SGTL5000 initialised**, which also means the I2C control path (pins 18/19) is working. Phase 4's firmware blockers are cleared.

**🚨 PROBLEM 1 — the live path runs 23.6× slower than designed, and the display is the cause.**

```
[Main] Block:   3 in 6583ms = 2194.3 ms/block (expected 92.9 ms, delta +2101.5 ms)
[Main] Display: 3 updates    = 2194.3 ms/update (expected 92.9 ms)
[Main] Loop:    192127 iterations/5s = ~38425/sec
```

Three audio blocks in 6.58 s where ~70 were expected. **Block count and display count are identical (3 and 3)** — and `guitar_rig_analyzer.ino:504` calls `displayEngine_update()` once per processed block (`s_total_blocks % DISPLAY_UPDATE_EVERY_N_FRAMES == 0`). So each block is paying ~2.2 s of display time. The loop itself spins fine at ~38 k iterations/s, so nothing is deadlocked — the time is being burned *inside* the display call.

**This is the risk flagged in entry (8), materialised in its milder form.** `display_engine.cpp` has no `s_initialised` guard, so every `displayEngine_*` call still drives SPI at an RA8875 that is not there. `Adafruit_RA8875::waitPoll()` spins on a status register; with no device the read never satisfies the exit condition promptly, so instead of the predicted infinite hang it burns roughly two seconds per call and returns. Prediction was directionally right, severity was wrong — worth noting, because "it didn't hang" could easily have been mistaken for "the display is harmless."

**Fix:** add an `s_display_ok` guard in `display_engine.cpp`, set from `displayEngine_init()`'s result, and early-return from every public entry point when false. That is the change entry (8) deliberately did not make pre-emptively; the evidence now justifies it. Tracked as TODO-25.

**🚨 PROBLEM 2 — both nodes are pegged at full scale, and one of them has nothing connected.**

```
[Main] SOURCE_NODE peak: +0.0 dBFS   |   RETURN_NODE peak: +0.0 dBFS
[Main] audioCap: CLIP_RETURN detected
[Main] audioCap: CLIP_SOURCE detected      (repeating continuously)
[Main] TF confidence: 100%   TF spot-check: 120Hz=+1.0dB 500Hz=+0.3dB 1kHz=+1.3dB 5kHz=+0.8dB 10kHz=-0.1dB
```

**RETURN_NODE reads +0.0 dBFS with nothing wired to it.** That single fact rules out a real-signal explanation — an unconnected input cannot legitimately sit at digital full scale. Two corroborating details point the same way: both channels clip continuously and in lockstep, and the transfer function is flat within ±1 dB at 100 % confidence across 120 Hz–10 kHz, which is what you get when **both channels are reading the same saturated data**, not what a real acoustic measurement looks like.

**Leading hypothesis: the I2S data path is not wired, so RX_DATA0 floats and reads as garbage at full scale.** The session record shows LINE-IN-L and shield ground connected and soldered, and power verified — but **no step ever wired the I2S lines (7, 8, 20, 21, 23)**, because Phase 4 never specifies the interconnect at all (runbook gap #3, entry (7)). I2C clearly *is* connected, since the codec initialised. That combination — control path alive, data path absent — matches the symptoms exactly.

**Critically, this means the analog front end has NOT been vindicated or condemned by this run.** SOURCE_NODE at +0.0 dBFS is not evidence the buffer works; it is evidence the digital path is untrustworthy. **Do not interpret any of these numbers as a measurement.** Phase 4 remains open, exactly as stated: SOURCE_NODE must *visibly and correctly* receive the injected signal.

**Not captured — the boot banner.** The board had been up 82 s before the serial connection was opened, so the capture begins mid-`loop()`. Everything above is inferred from the running diagnostics rather than read from the init sequence. A reset with the port already open will retain the full `[Main]` banner in the ring; worth doing to confirm the exact init lines, including whatever `audioCap_init()` reports about the codec.

**Next:** (1) wire the I2S interconnect — TX 7, **RX 8**, LRCLK 20, BCLK 21, MCLK 23, plus 3.3 V and GND, per entry (7)'s verified table; (2) add the `s_display_ok` guard; (3) reset with the port open and capture the true boot banner.

---

## 2026-09-05 (8) — `RA8875_RESET_PIN` moved 8 → 5. Pin conflict resolved in source; the boot-order halt is NOT

**Change made:** `config.h:79` — `#define RA8875_RESET_PIN 8` → `5`, with an inline comment recording why and warning against reverting. **Compile-verified clean** for `teensy:avr:teensy41` (FLASH 157572 / RAM1 218720, unchanged, as expected for a pin renumber). No wiring touched, per instruction — pin 5 becomes the display reset when the RA8875 is eventually mounted; Audio Shield pin 8 stays on Teensy pin 8 for I2S input.

**Why one line was sufficient:** the pin is referenced only through the macro — `display_engine.cpp:36` (`Adafruit_RA8875 tft(RA8875_CS_PIN, RA8875_RESET_PIN)`) and `display_engine.cpp:440` (a diagnostic printf). Grepped the whole tree for hardcoded `8`s in this role and found none, so there is no second place to update.

**⚠️ This resolves TODO-24's pin conflict but does NOT unblock the SOURCE_NODE test.** The two blockers in entry (7) were independent, and only one is now fixed. `guitar_rig_analyzer.ino:197` still calls `displayEngine_init()` before `audioCap_init()` and still halts forever on failure, and the RA8875 is still not on the bench — so the firmware will still halt before audio initialises. **Expect the board to blink-halt on reset until display init is made non-fatal.** That is the remaining step, and it is a separate edit.

**Worth noting:** with the reset moved, the display no longer sidesteps the conflict by accident — pin 8 is now free for I2S regardless of whether display init runs. That is strictly better than relying on skipping display init to keep pin 8 clear, and it means the eventual product can have both.

**Next:** make display init non-fatal, then reset and capture the boot output. The serial connection is held open, so the banner will be retained in the RX ring.

---

## 2026-09-05 (7) — Audio Shield wired; power checks pass. But TWO firmware blockers make the SOURCE_NODE test impossible as things stand — a boot-order halt, and a hard pin-8 collision between the display and I2S RX

**Why this entry exists:** records shield wiring progress and its power verification, and documents two firmware-level blockers found by reading the active tree before the test was run. Neither is an analog problem. Both would have presented as "no signal at SOURCE_NODE," which is exactly the symptom that sent this project on a two-day hunt once already.

**Progress:** LINE-IN-L wire and shield ground connected and soldered. Power isolation and rails verified with the shield attached:

| Check | Reading | Verdict |
|---|---|---|
| +5 V → GND resistance | 13.99 kΩ | no short |
| 3.3 V → GND resistance | 8.06 kΩ | no short |
| 3.3 V rail, powered | 3.3 V | ✅ |
| +5 V rail, powered | 4.99 V | ✅ |

**Runbook gap #3 in Phase 4 — credit to ChatGPT for catching it.** Phase 4 goes straight from wiring LINE-IN-L to expecting the Teensy to see SOURCE_NODE, but **never specifies how the Audio Shield connects to the Teensy at all** — no I2S, I2C, or power interconnect is given anywhere in the phase. That is the third independent defect in Phase 4 (after the invalid common-mode bias and the missing USB reconnect).

**The interconnect, verified from the Teensy Audio library source rather than from memory** (`.../teensy/hardware/avr/1.62.0/libraries/Audio/`, `__IMXRT1062__` branch — the Teensy 4.x path):

| Signal | Pin | Source |
|---|---|---|
| I2S TX_DATA0 (Teensy → shield) | **7** | `output_i2s.cpp:83` |
| **I2S RX_DATA0 (shield → Teensy)** | **8** | `input_i2s.cpp:222` |
| LRCLK / RX_SYNC | **20** | `input_i2s.cpp:451` |
| BCLK / RX_BCLK | **21** | `input_i2s.cpp:453` |
| MCLK | **23** | `input_i2s.cpp:450` |
| SDA / SCL (codec control) | 18 / 19 | Wire default, Teensy 4.x |
| Power | 3.3 V, GND | — |

Note the earlier working list of "7, 18, 19, 20, 21, 23, 3.3 V, 5 V, GND" **omits pin 8 and includes 5 V.** Pin 8 is the line carrying line-in audio *into* the Teensy — without it SOURCE_NODE is silent by construction. The shield runs from 3.3 V; it does not need 5 V.

**🚨 BLOCKER 1 — pin 8 is assigned to the display's reset line.** `config.h:79` declares `#define RA8875_RESET_PIN 8`, and `display_engine.cpp:36` passes it to `Adafruit_RA8875 tft(RA8875_CS_PIN, RA8875_RESET_PIN)`. **Pin 8 cannot be both the RA8875 reset and I2S RX_DATA0.** Whichever initialises last wins the pin mux: if the display claims it, no audio input reaches the Teensy at all; if `AudioInputI2S` claims it, the display's reset line is driven by I2S data. This is a genuine design conflict in the active tree, not a wiring mistake.

**🚨 BLOCKER 2 — and it masks blocker 1.** `guitar_rig_analyzer.ino:197` calls `displayEngine_init()` **before** `audioCap_init()`, and on failure halts permanently:

```
if (!displayEngine_init()) {
    Serial.println("[Main] FATAL: Display init failed. Halting.");
    pinMode(LED_BUILTIN, OUTPUT);
    while (true) { digitalWrite(LED_BUILTIN, !digitalRead(LED_BUILTIN)); delay(150); }
}
```

**The RA8875 is not on the bench** — journal 2026-09-01 (1) already recorded the board halting here, described at the time as expected. So today the firmware halts in a blink loop *before audio is ever initialised*. **The SOURCE_NODE test cannot pass, no matter how good the analog front end is**, and the failure would look identical to a dead buffer.

**Fixes, and they are different in scope:**
- **To run the test today:** make display init non-fatal (log and continue instead of halting), or temporarily skip it, so `setup()` reaches `audioCap_init()`. This resolves blocker 2 *and* sidesteps blocker 1 in one move — if `displayEngine_init()` never runs, the Adafruit library never claims pin 8, so I2S RX is free. Minimal change, matches the existing convention of temporary bring-up code.
- **Before the display and audio ever coexist:** `RA8875_RESET_PIN` must move off pin 8 permanently. Free pins on this design are **2, 3, 4, 5** (0/1 are `Serial1` for `data_sender`; 6 is the shield's MEMCS and best avoided; 9–24 are all allocated). **Pin 5 recommended.** This is a real product-level fix, not a bring-up expedient. Tracked as TODO-24.

**Also checked, and it is fine:** `RA8875_CS_PIN` is 10, which is also the shield's SD chip-select — but `calibration_store.cpp:404` uses `SD.begin(BUILTIN_SDCARD)`, the Teensy 4.1's own slot, so the shield's SD is unused. **Leave the shield's SD socket empty** and the shared pin 10 is harmless.

**Not recorded — the headroom bracket is still open.** A reading at ~0.55 V<sub>rms</sub> was requested to close the 0.460→0.686 gap but does not appear in the session record. The bracket stands as *onset of measurable compression somewhere above 0.460 and by 0.686 V<sub>rms</sub>*.

**Bench tooling now live.** `serial-mcp` is connected to `/dev/cu.usbmodem195969201` at 115200 with the connection held open, so its RX ring will retain the boot banner whenever the Teensy is reset — the `[Main]` output can then be read back in full rather than transcribed by eye. A read taken before any reset returned zero bytes, consistent with a sketch that prints its banner once in `setup()` and then only on events.

**Next:** decide the display-init bypass, reset the board, and capture the actual boot output. That output will show whether it halts at display init as predicted, and if bypassed, whether `audioCap_init()` finds the SGTL5000.

---

## 2026-09-05 (6) — BENCH: headroom characterised. Linear ceiling ≈ 0.5 V<sub>rms</sub>, and at 0.460 V the *entire* measured loss is the coupling cap — the buffer itself is unity

**Why this entry exists:** completes the headroom sweep started in entry (5). The buffer is now characterised, not assumed. One reading turns out to validate a second, unrelated part of the design for free.

**The sweep (1 kHz, bias 0.874 V):**

| Input V<sub>rms</sub> | Output V<sub>rms</sub> | Gain | dB | Verdict |
|---|---|---|---|---|
| 0.460 | 0.453 | 0.9848 | −0.133 | linear |
| 0.648 | 0.613 | 0.9460 | −0.482 | compressing |
| 0.686 | 0.639 | 0.9315 | −0.616 | clearly compressing |
| 0.460 *(repeat)* | 0.453 | 0.9848 | −0.133 | **linear — repeatable** |

Monotonic across all four points, and the return to 0.460 V reproduced 0.453 V exactly. **The compression is real and repeatable, not drift** — the below-knee / above-knee / below-knee-again structure is what makes this a characterisation rather than an anecdote.

**✅ The best result here is the one that looks like a small loss.** At 0.460 V the gain is 0.9848 — 1.5% down. That is *not* op-amp compression. The input high-pass formed by C1 = 10 nF into the 100 kΩ bias resistor has a corner at **f<sub>c</sub> = 1/(2π·100k·10n) = 159.2 Hz**, and at 1 kHz its predicted response is:

> |H| = (f/f<sub>c</sub>) / √(1 + (f/f<sub>c</sub>)²) = 6.28 / √40.5 = **0.9867  (−0.116 dB)**

Measured 0.9848 against a predicted 0.9867 — a **0.19% discrepancy, inside meter accuracy.**

**Conclusion that holds:** the buffer's own small-signal gain is **unity to within measurement error**. The op-amp contributes no measurable loss at 0.460 V, and the 1.5% is the coupling network, not compression.

**Conclusion that does NOT hold — corrected here before it propagated.** A first draft of this entry claimed the reading "independently validates the C1/R network at its designed 159 Hz corner." **It does not.** It is *consistent with* a 159 Hz corner, which is a much weaker statement, and the difference matters. At 1 kHz the high-pass is only −0.116 dB down, so the measurement barely constrains f<sub>c</sub> at all:

| Assumed f<sub>c</sub> | Predicted \|H\| at 1 kHz |
|---|---|
| 100 Hz | 0.9950 |
| **159 Hz** | **0.9867** |
| 200 Hz | 0.9806 |
| 300 Hz | 0.9578 |

With ±0.5% meter accuracy, the measured 0.9848 is consistent with **any corner from roughly 125 Hz to 205 Hz** — a ±25% window. Measuring a high-pass a full 6× above its corner is close to the least informative place to probe it. **Validating the corner requires a frequency sweep, not a single point:** readings at ~40, 80, 159, 320 and 640 Hz, checking for −3 dB at the corner and a 6 dB/octave slope below it. That sweep is worth doing anyway — it is exactly the evidence TODO-19 needs to decide whether C1 stays at 10 nF or moves to 0.1 µF, so it should be run once and used for both purposes.

The entry (4) topology point does still stand on its own: biasing through a series resistor kept input impedance at exactly 100 kΩ by construction, so the corner did not move — but that follows from the circuit, not from this measurement.

**Why the knee falls where it does.** Converting each level to instantaneous excursion around the 0.874 V bias (peak = V<sub>rms</sub> × √2):

| Input V<sub>rms</sub> | Peak | Excursion | Against the limits |
|---|---|---|---|
| 0.460 | 0.651 V | 0.224 … **1.525 V** | grazing both — 25 mV over the 1.5 V CM ceiling |
| 0.686 | 0.970 V | **−0.096** … **1.844 V** | below the output floor *and* 0.34 V over the CM ceiling |

So the circuit runs out of room at both ends nearly simultaneously — which is expected, since the bias was deliberately placed near the centre of the usable window.

**The finding, stated at the precision actually measured:** *onset of measurable compression occurs somewhere above 0.460 V<sub>rms</sub> and by 0.686 V<sub>rms</sub>.* That bracket is what the data supports. Any single figure inside it — including the "≈ 0.5 V<sub>rms</sub>" used in earlier drafts of this entry — is an interpolation across a 49% gap, not a measurement, and should be written as the bracket unless two more points are taken to close it.

**The installed circuit outperforms the datasheet-derived worst case.** Entry (4) predicted the knee at 0.4–0.45 V<sub>rms</sub>; the measured bracket sits entirely above that. Two reasons, both anticipated: the real load (10 µF into a high-impedance codec input) is far lighter than the 2 kΩ the output-swing spec assumes, so the output floor sits nearer 0.2 V than 0.35 V; and the datasheet's common-mode range is a guaranteed limit that typical parts exceed. **Prediction and measurement agreeing to ~10% on a limit derived from two independent datasheet constraints is a strong result** — that is the part worth putting in the portfolio.

**Two caveats on the characterisation, stated so it isn't over-claimed:**
1. **The knee is interpolated across a 49% gap** (0.460 → 0.686 V<sub>rms</sub>). "≈ 0.5 V<sub>rms</sub>" is an inference between two points, not a measured knee. Two more readings in that gap — say 0.55 and 0.62 V — would pin it, and that region is *safe* to test (unlike going higher). Five minutes for materially better evidence.
2. **By the standard 1 dB compression criterion (P1dB), the knee has not actually been reached.** Referenced to the C1-corrected small-signal gain of 0.9867, 1 dB down is 0.879; the worst measured point is 0.9315, only **0.49 dB** down. So "≈ 0.5 V<sub>rms</sub>" is the onset of *visible* compression, roughly a 0.5 dB point — a more conservative and more useful number for this application than P1dB, but it should be labelled as such rather than called the 1 dB point.

**Agreed: do not drive higher.** At 0.686 V<sub>rms</sub> the negative peak is already at **−0.096 V**, essentially exactly the −0.1 V common-mode floor. Beyond that the input protection structures begin to conduct and the input stops being a high-impedance node. The datasheet notes the OPA164x suppresses phase reversal under common-mode overdrive (the rail limits the output instead), so this is graceful rather than destructive — but there is no information to be gained above this level and some risk in seeking it.

**Operating recommendation, anchored to a measured point rather than an interpolated one.** For a *measurement* instrument, running just below the compression onset is not good enough: THD rises well before gain visibly compresses. Take **0.460 V<sub>rms</sub> — the highest level actually measured as linear** — as the reference, and work down from there: **target ≤ 0.23 V<sub>rms</sub> (−6 dB), preferably ~0.15 V<sub>rms</sub> (−10 dB)** for any capture whose numbers are meant to be trusted. Deriving the limit from the measured point rather than the interpolated knee means it stays valid regardless of where the knee actually falls in the bracket. 0.460 V is fine for proving signal flow; it is not where quantitative measurements should be taken.

**Next:** reconnect the Audio Shield path and confirm the signal reaches SOURCE_NODE in firmware. Note the bench tooling for this is already installed — the `serial-mcp` server is configured and approved, so the Teensy's `[Main]` output can be captured directly rather than read off a monitor by eye.

---

## 2026-09-05 (5) — BENCH: OPA_BIAS built, common-mode fix CONFIRMED by measurement, buffer passing signal. But the test level is already ~50% past the linear limit

**Why this entry exists:** first bench results after building the temporary OPA_BIAS configuration from entry (4). The fix works and is proven by the numbers. A second reading of the same numbers shows the test signal is already into compression, which matters for the headroom test planned next.

**Measured:**

| Node | Reading |
|---|---|
| OPA_BIAS node | 0.874 V |
| Pin 3 (+in A) | 0.868 V |
| Pin 1 (out A), idle | 0.875 V |
| Pin 5 (+in B) | 0.876 V |
| Input AC (1 kHz) | 0.648 V |
| Op-amp output AC | 0.613 V |
| Post-cap output AC | 0.603 V |
| Output DC **while driven** | 0.890 V |

**✅ The common-mode defect is fixed, and the evidence is unambiguous.** Compare the droop on pin 3 before and after:

| | Bias source | Pin 3 | Droop |
|---|---|---|---|
| **Before** (VGND 2.5 V) | 2.480 V | 2.153 V | **327 mV** |
| **After** (OPA_BIAS 0.877 V) | 0.874 V | 0.868 V | **6 mV** |

A **54× reduction in droop.** The input stage has stopped drawing the current it was drawing when operated out of range — which is exactly what the fix predicted. Pin 1 tracks pin 3 to within 7 mV, so the follower is behaving as a follower. **TODO-21's proof criterion ("pin 3 within 30 mV of its intended bias with the op-amp installed") is met** — 0.868 V against a designed 0.877 V is 9 mV. The as-built divider landed within 3 mV of its calculated 0.877 V, so the resistor arithmetic was right too. **Pin 5 sits at 0.876 V**, confirming the channel-B half of the fix landed as well.

**⚠️ But the drive level is already past the linear region — the "buffer is alive" reading is not a clean linear measurement.** At 0.648 V<sub>rms</sub>, a sine has 0.916 V peak. Around a 0.874 V bias that demands an excursion from **−0.04 V to +1.79 V**, which violates *both* limits at once: the negative peak goes below the output floor (0.2–0.35 V) and below the CM floor (−0.1 V), while the positive peak exceeds the **1.5 V CM ceiling** by 0.29 V. Predicted linear ceiling for this configuration is ~0.44 V<sub>rms</sub>, so the test ran roughly **50% above it.**

Two independent signatures in the data confirm this rather than it being a prediction:
1. **Gain is 0.946 (−0.48 dB), not unity.** A follower does not lose 5.4%. The high-pass from C1 into 100 kΩ accounts for only ~0.1 dB at 1 kHz. The remainder is compression.
2. **Output DC shifts 15 mV under drive** (0.875 → 0.890 V). A linear stage shows *no* DC shift with signal applied. Asymmetric clipping rectifies the waveform and pulls the average — this is a textbook clipping tell, and it moved in the expected direction.

**Consequence for the next test:** the headroom sweep must **start well below** this level and work *up*, or the knee will already be behind the starting point and the result will read as "output stops tracking immediately." Suggested: begin near **0.1 V<sub>rms</sub>**, step up, and record input vs output at each step. The knee should appear near **0.4–0.45 V<sub>rms</sub>**; finding it materially lower or higher than that is itself informative, since it calibrates the real installed-circuit limit against the datasheet-derived prediction — which was the entire point of characterising rather than assuming.

**Minor, not alarming:** post-cap output (0.603 V) sits 1.6% below the op-amp output (0.613 V). At 1 kHz the 10 µF coupling cap has X<sub>C</sub> ≈ 16 Ω, which should be negligible into a high-impedance load, so this is most likely meter scatter. Worth a second look only if it grows at low frequencies, where it would indicate the coupling cap is working into a lower load than assumed.

**Status:** the temporary Phase 4 configuration is **electrically validated at small signal**. It is not yet characterised for headroom, and until it is, no capture from it should be treated as quantitatively trustworthy — a measurement instrument whose front end is compressing produces artifacts of its own front end.

**Next:** headroom sweep from 0.1 V<sub>rms</sub> upward, logging input vs output, to locate the actual knee. Then compare against the 0.4–0.45 V<sub>rms</sub> prediction and record both in TODO-4's proof.

---

## 2026-09-05 (4) — CORRECTION: entry (3)'s 1.2 V output-floor figure was wrong. Verified from TI's datasheet; final bias design is ~0.88 V on a decoupled OPA_BIAS node

**Why this entry exists:** entry (3) below built its headroom analysis and its 1.34 V bias recommendation on an output-swing figure of "1.2 V from each rail." **That figure is wrong.** It came from a web search result summarising a third-party blog, not from TI. ChatGPT flagged it; the datasheet was then pulled and parsed directly to settle it. Entry (3) is left in place per this file's rules — this entry supersedes its numbers and its recommendation.

**Verified, extracted from TI's OPA164x datasheet (SBOS484) Electrical Characteristics table:**

```
VO   Voltage output swing from rail
     RL = 10 kΩ, AOL ≥ 120 dB     (V–)+0.2     (V+)–0.2
     RL = 2 kΩ,  AOL ≥ 114 dB     (V–)+0.35    (V+)–0.35
VCM  Common-mode voltage range    (V–)–0.1     (V+)–3.5
```

So the output swings to within **0.2 V** (10 kΩ) or **0.35 V** (2 kΩ) of the rails — not 1.2 V. **Sourcing discipline note for future sessions: a search-result summary is not a datasheet.** A number that drives a build recommendation must come from the primary document. This one was off by 6× and would have produced a materially worse circuit.

**Corrected headroom analysis.** For a unity-gain follower the signal *is* the common-mode voltage, so the usable window is the intersection:

| Constraint | Range at V+ = 5 V |
|---|---|
| Input common-mode | −0.1 … **1.5 V** |
| Output swing, R<sub>L</sub> = 2 kΩ | **0.35** … 4.65 V |
| Output swing, R<sub>L</sub> = 10 kΩ | **0.20** … 4.80 V |
| **Usable (conservative, 2 kΩ)** | **0.35 – 1.50 V — 1.15 V wide** |

That is **~4× wider than entry (3) claimed**, and it makes the stopgap comfortably viable rather than marginal. The optimum bias is the window's centre, ≈ **0.925 V** (2 kΩ) or ≈ 0.85 V (10 kΩ) — so the originally proposed ~1.0 V was close to right, and **entry (3)'s 1.34 V was actively worse**: it leaves only 0.16 V of upward room before the common-mode ceiling. Correction accepted in full.

**Topology change — bias from a decoupled node, not from a divider sitting on the input.** Both earlier proposals put the divider directly at pin 3, which makes the divider's Thévenin resistance the input impedance *and* leaves the bias node undecoupled, feeding +5 V rail noise straight into the signal path attenuated only by the divider ratio. The original circuit did not have this problem: it biased from **VGND, which Phase 1 decouples** (10 µF + 0.1 µF), through a single 100 kΩ series resistor. Preserve that structure:

1. **Build a separate `OPA_BIAS` rail** — 47 kΩ (+5 V → node) + 10 kΩ (node → GND) ⇒ **0.877 V**, R<sub>th</sub> = 8.25 kΩ, draw 88 µA.
2. **Decouple it** — 10 µF electrolytic (+ to OPA_BIAS, − to GND) plus 0.1 µF ceramic, mirroring Phase 1 Steps 8–9.
3. **100 kΩ from OPA_BIAS → pin 3** — this is the *existing* bias resistor, simply moved off VGND.
4. **100 kΩ from OPA_BIAS → pin 5**, replacing Step 10a's jumper to VGND (entry (3)'s pin 5 finding, which ChatGPT confirmed).
5. **Leave VGND completely untouched** — it stays 2.5 V for everything else.

**Why 0.877 V and not 1.000 V:** two resistors instead of five, and it sits nearer the window centre. Worst-case (2 kΩ) headroom is ±0.53 V peak; at the real light load, ±0.62 V. Round 1.000 V is available as 4× 10 kΩ + 1× 10 kΩ if a clean number is preferred — the difference is ~1 dB, not worth three extra parts.

**Why this topology is better than either earlier proposal:** input impedance stays exactly 100 kΩ (set by the series resistor, not the divider), so **the C1 corner does not move** and TODO-19 is unchanged in kind; TODO-23's eventual 1 MΩ swap stays a single-part change; and the bias node is properly decoupled. The JFET inputs draw picoamps, so those 100 kΩ resistors carry no DC current and drop no voltage — the 8.25 kΩ source is stiff enough with nothing further needed.

**Stock check (from the runbook's master parts list):** 1 kΩ ×60 · 10 kΩ ×60 · 47 kΩ ×40 · 100 kΩ ×50 · 10 µF ×10 · 0.1 µF ×20 · 10 nF ×10. Everything above is on hand; **no order needed.**

**Unchanged from entry (3):** the pin 5 finding stands and is now confirmed by both reviewers. The characterisation-before-trust principle stands — bias it, drive a controlled signal, find the real clipping point rather than assuming the datasheet boundary is the installed-circuit limit. Bench state remains OPA out, USB unplugged, VGND untouched until the new bias node is built and measured.

**Next:** build OPA_BIAS (steps 1–5 above), verify it reads ~0.88 V unloaded, install the OPA1642, confirm pin 3 and pin 1 both sit within 30 mV of it, then characterise the clipping points.

---

## 2026-09-05 (3) — Option 3 (rebias to ~1 V) adopted as the documented temporary bring-up config. Design work done: 1.0 V is the WRONG target, and the usable window is far tighter than assumed

> **⛔ NUMBERS SUPERSEDED BY 2026-09-05 (4) — READ THAT FIRST.** This entry's "output swings to within 1.2 V of each rail" is **wrong** — it came from a search-result summary, not TI. The datasheet says 0.2 V (10 kΩ) / 0.35 V (2 kΩ). Consequently this entry's 0.3 V window and its 1.34 V bias recommendation are both void; the correct target is ~0.88–1.0 V. The **pin 5 finding below is correct and stands.** Retained unedited per the never-delete rule.

**Why this entry exists:** Conley decided to proceed with the Option 3 stopgap to get a working prototype for the MIT Maker Portfolio while the PCB architecture (TODO-21) is settled in parallel. That is **compliant with the decision gate in entry (2)** — the gate explicitly permits "an explicitly documented temporary bring-up configuration," and this entry is that documentation. This entry records the actual design calculation, which turned up two problems with the plan as proposed.

**Finding 1 — 1.0 V is below the op-amp's own output floor. Do not bias there.** TI specifies the OPA1642's output as swinging **to within 1.2 V of each rail** (at R<sub>L</sub> = 2 kΩ to midsupply). On a 5 V rail that puts the output floor at **1.2 V**. A unity-gain follower's output must sit at its input bias, so **a 1.0 V bias asks the output to sit somewhere it cannot go.** The proposed 1.0 V target is not viable as stated.

**Finding 2 — the usable window is the intersection of two constraints, and it is narrow.** For a follower, the signal *is* the common-mode voltage, so the instantaneous input must stay inside the CM range while the output stays inside its swing range:

| Constraint | Range at V+ = 5 V |
|---|---|
| Input common-mode (TI) | −0.1 V … **1.5 V** |
| Output swing, R<sub>L</sub> = 2 kΩ (TI) | **1.2 V** … 3.8 V |
| **Usable intersection** | **1.2 V … 1.5 V — only 0.3 V wide** |

At the rated load that is a **0.3 V<sub>pp</sub> ceiling (~106 mV<sub>rms</sub>)**, centred at ~1.35 V. Not a bias-point choice — **no bias point does better**, because the window itself is only 0.3 V wide. This is an inherent consequence of running this part on 5 V, and it is the strongest evidence yet that the OPA1642 is genuinely the wrong part for a 5 V rail rather than merely mis-biased.

**The saving grace, and it must be measured, not assumed.** That 1.2 V output figure is specified at R<sub>L</sub> = 2 kΩ. **The real load here is far lighter** — a 10 µF cap into the codec's line-in, and later a rig input through the relay, both high-impedance. Output swing improves substantially with light loads, typically to within a few hundred millivolts of the rails. If the real floor is ~0.3 V, the window opens to 0.3–1.5 V (**1.2 V wide, ±0.6 V peak**) and the stopgap is comfortably demo-valid. **The entire viability of Option 3 rests on this one unmeasured number.**

**So the first bench task is characterisation, not construction:** bias pin 3 at ~1.35 V, drive a small signal, and find where the output actually clips. That measurement — 15 minutes, no new parts — converts the go/no-go from a guess into data. It is also exactly the kind of evidence the portfolio benefits from.

**Buildable divider, from stock on hand.** The parts list holds 1 kΩ (60), 10 kΩ (60), 47 kΩ (40), 100 kΩ (50) — **no 1 MΩ**, and the list itself annotates the 100 kΩ as "substitute for 1 MΩ", confirming TODO-23's low input impedance was a deliberate substitution rather than an oversight. Replacing the single 100 kΩ-to-VGND bias with a divider from +5 V:

| Target | Build | V<sub>bias</sub> | R<sub>th</sub> (= input Z) |
|---|---|---|---|
| **Recommended** | 3× 100 kΩ series (+5 V→pin 3) · 100 kΩ + 10 kΩ series (pin 3→GND) | **1.34 V** | 80.5 kΩ |
| Simpler | 3× 100 kΩ series (+5 V→pin 3) · 1× 100 kΩ (pin 3→GND) | **1.25 V** | 75 kΩ |

The 1.34 V option is preferred: it sits above even the worst-case 1.2 V output floor, while staying 0.16 V below the CM ceiling. Both keep input impedance in the same 75–80 kΩ neighbourhood as the existing 100 kΩ, so the AC-coupling corner shifts only slightly (TODO-19 unaffected in kind).

**⚠️ Finding 3 — pin 5 has the same defect and everyone has missed it.** Phase 4 Step 10a ties **pin 5 (+in B) to VGND ≈ 2.5 V**. That is the *same* common-mode violation, on the unused half. The runbook terminates channel B specifically to stop it oscillating; a channel B whose input sits outside its CM range is not reliably terminated, and an oscillating unused half radiates through the shared supply pins into channel A — the exact failure the termination exists to prevent. **The rebias must move pin 5 to the same new bias node as pin 3**, not leave it on VGND. Rebiasing only pin 3 leaves the fix half-done.

**Portfolio framing (Conley's stated goal).** This is a legitimate and, if anything, stronger story than a clean build: a spec violation found by measurement, the part exonerated rather than swapped on suspicion, a quantified headroom limit derived from two datasheet constraints, and a temporary configuration adopted deliberately with its limits documented and its replacement already scoped. **The one thing that would undermine it is presenting the stopgap as the final architecture.** Label it as bring-up in any writeup.

**Next:** build the 1.34 V divider (pin 3 **and** pin 5), then measure the actual clipping points before trusting any capture. TODO-21's architecture decision remains open and unaffected.

---

## 2026-09-05 (2) — Decision gate adopted for the Phase 4 fix; the "raise the supply" recommendation is withdrawn as premature

**Why this entry exists:** entry (1) below found the defect and closed with a recommendation. Conley pushed back on that recommendation and added a process constraint. Both are adopted here, and the reasoning is worth preserving because the *shape* of the mistake is one this project keeps having to guard against.

**Process decision — a gate before the bench, not after it.** Adopted verbatim in intent:

> Determine whether the production analyzer is required to operate from the existing 5 V USB-derived analog rail. **Do not modify Phase 4 hardware until that requirement is settled.** The selected solution must be the intended PCB architecture, except for an explicitly documented temporary bring-up configuration.

**Bench state until the gate clears: breadboard unpowered, OPA1642 removed.**

**Why the gate matters.** The pull will be toward the Option 3 stopgap (re-bias to ~1.0 V) simply to keep making visible progress. That would create a *second* electrical configuration which can silently diverge from the eventual PCB — and once the breadboard stops matching the intended product, every bench result it produces stops being evidence for that product. This is the same failure mode this project already has a rule for: the source-of-truth precedence rule exists because a document describing intent got mistaken for a verified tree. A stopgap breadboard is that mistake in hardware form.

**Recommendation withdrawn, and why it was wrong.** Entry (1) recommended raising the analog supply, reasoning that noise and distortion matter for a measurement instrument and the OPA1642 is the better part. That call was made at the wrong altitude: **it compared op-amp datasheets and never priced the system.** Adding a second analog rail to a Teensy-based field instrument pulls in boost/regulator circuitry, converter switching noise landing next to an audio front end, an analog grounding strategy, power sequencing, protection between the analog and 3.3/5 V domains, PCB area, and BOM. A 5 V rail-to-rail-input buffer can be the cleaner *product* even with a somewhat worse standalone noise figure. The correct framing is Conley's: **is single-USB-power part of the product architecture?** Everything else follows from that answer.

**A technical point that pushes further in the same direction — flagged for verification, not asserted as settled.** The main argument for keeping the OPA1642 is its ~5 nV/√Hz voltage noise. But at this stage's source impedance that advantage is largely invisible. Once TODO-23 raises the input impedance toward 1 MΩ, the effective noise resistance seen at the input — that bias resistor in parallel with a 6–250 kΩ pickup — lands in the tens-to-low-hundreds of kΩ, and √(4kTR) at 200 kΩ is already **≈ 57 nV/√Hz**. That is roughly 10× the op-amp's own contribution, so **the gap between a 5 nV/√Hz JFET part and a 10–15 nV/√Hz CMOS RRI part largely disappears into the source's own thermal noise.** What still genuinely separates candidates is **THD+N**, which does matter for a measurement instrument, and **current noise**, which gets multiplied by that same large source impedance — meaning any candidate must be CMOS or JFET input and **a bipolar-input part is disqualified outright at these impedances.** If this arithmetic survives checking with real datasheet numbers, the noise case for the extra rail mostly evaporates.

**Next engineering task — explicitly not breadboarding.** A short component/architecture comparison: *OPA1642 + higher analog rail* vs. *best-qualified 5 V RRI replacement*, compared on input common-mode range at 5 V, output swing at the required load, input bias current, voltage noise, current noise, THD+N, GBW, unity-gain stability, supply current, package compatibility, and availability/cost — plus behaviour at the ~1 MΩ input impedance TODO-23 will require. Decide once, update `docs/breadboard_bringup_v3.md`, then resume Phase 4.

**Also affirmed:** entry (1)'s proof criterion — *pin 3 measures within 30 mV of its intended bias with the op-amp installed* — is kept as written. It directly detects the exact failure that started this, which is what a proof criterion is for.

---

## 2026-09-05 (1) — ROOT CAUSE: Phase 4's circuit is invalid by design. The OPA1642 cannot be biased at midsupply on a 5 V single rail — TI's common-mode input range forbids it. The chip is not damaged.

**Why this entry exists:** supersedes the hardware-fault hypotheses in the 2026-09-03 entry below with a *design* defect in the runbook itself, verified against the manufacturer's datasheet. This is the highest-value engineering finding on the project so far and is written up accordingly. Entry (1) of 2026-09-03 is left in place per this file's rules; its "OPA1642 is reverse-powered" hypothesis is **rejected** — see below.

**The finding.** `docs/breadboard_bringup_v3.md` § Phase 4 biases the OPA1642's non-inverting input (pin 3) to VGND ≈ 2.5 V while powering the part from a single +5 V rail (Step 3: pin 4 → GND; Step 4: pin 8 → +5 V). **That operating point is outside the device's specified input common-mode range.**

TI's OPA164x datasheet specifies:

> V<sub>CM</sub> = (V−) − 0.1 V to (V+) − 3.5 V

**Independently verified against TI's published datasheet, not taken on assertion.** The datasheet further states explicitly that *for V<sub>S</sub> less than ±3.5 V, the common-mode input range does not include midsupply.*

Applied to this circuit — V+ = 5 V, V− = 0 V — the legal common-mode window is **−0.1 V to +1.5 V**. Phase 4 biases at 2.5 V, **a full volt above the ceiling.** Critically, 5 V *is* a legal total supply for the part (absolute range 4.5–36 V), which is exactly what makes this defect easy to miss: the supply is valid, the *input bias point at that supply* is not. Choosing a JFET part for its picoamp bias current, then operating its inputs outside their valid window, defeats the reason it was chosen.

**Bench evidence, and it fits cleanly:**

| Observation | Reading | Interpretation |
|---|---|---|
| VGND rail, op-amp removed | **2.480 V** | divider healthy, unloaded |
| Pin 3, op-amp removed | **2.480 V** | bias path correct — no fault upstream |
| Pin 3, op-amp installed | **2.153 V** | input stage outside CM range, loading the bias node |
| Pin 1 (output) | **~2.153 V** | follower tracking a corrupted input, as expected |
| Pin 3 → pin 4 resistance | **159 kΩ** | **not a short** — chip is not damaged |
| +5 V rail | **4.99 V** | supply healthy |

The ~327 mV droop on a node that measures 2.480 V unloaded is the signature: the input stage is drawing current it should not, because it is being operated past its specified limit. A damaged part would show a low resistance and a collapsed rail. Neither is present.

**Rejected hypothesis — "the OPA1642 is reverse-powered."** The 2026-09-03 entry ranked this first. It is wrong, and the 159 kΩ pin 3→pin 4 measurement plus the healthy 4.99 V rail refute it directly: a reverse-powered op-amp conducts hard through its substrate and crushes the supply. **Do not flip, replace, or re-seat the chip on the strength of that entry.** The part is fine and should stay in service.

**✅ RESOLVED — the 0 V rail was an unpowered board. USB was not plugged in.** Confirmed by Conley 2026-09-05. There was never an electrical fault, no intermittent, and nothing to chase: **the rail reads 0 V because nothing was powering it.** The healthy 4.99 V now is simply the same rail with USB connected.

**This vindicates the original hypothesis and reinstates the runbook defect as the real cause of the detour.** The first analysis on 2026-09-03 identified exactly this — Phase 4 says "Unplug USB" at Step 1 (line 884) and **never says to plug it back in**, yet its end-of-phase verify at line 1027+ demands five live DMM readings. That hypothesis was then withdrawn on a report that the 0 V had been measured with power connected, which turned out to be mistaken. The correct chain is the simple one: *the runbook told him to unplug USB, never told him to plug it back in, and then asked him to measure voltages.*

**Everything the withdrawal produced was wrong and is retracted:**
- The "this is a REGRESSION" framing in the 2026-09-03 entry — **there was no regression.** The rail never failed.
- The "OPA1642 is reverse-powered" hypothesis — already refuted by the 159 kΩ measurement, now doubly moot.
- The escalation flag over the Teensy not enumerating on 2026-09-03 at 11:14 PDT — **same cause.** An unplugged Teensy does not enumerate. Not evidence of overcurrent or damage.
- The VUSB-vs-VIN concern is **no longer implicated in any fault.** It remains a genuine documentation inconsistency worth settling (the runbook specifies the `VUSB` pad and never mentions VIN in 1860 lines, while the debugging session probed "5V/VIN"), but nothing is broken because of it. Demoted to housekeeping.

**The lesson, and it is the valuable part of this whole episode:** a documentation gap consumed roughly two days of hardware debugging across two AI sessions, produced two false hardware hypotheses, and nearly resulted in a good op-amp being replaced on suspicion. **Fixing TODO-18 is not cosmetic.** Cheapest test first, always: confirm the supply is connected before testing the load.

**Note on what survives.** The common-mode finding in this entry is **entirely independent of the 0 V episode** and stands unchanged. It was found by correct measurement (2.480 V chip-out vs 2.153 V chip-in) against a powered board, and it is a real defect in the design. The 0 V rail was a red herring running alongside it, not part of it.

**Blast radius — confined to one stage, but that stage is load-bearing.** Checked every phase for op-amp usage: only Phase 4 instantiates a buffer. Phase 7 does **not** add a second op-amp — it branches the *existing* buffer output at `48e` into RELAY_SEND NC_1 while keeping the permanent SOURCE_NODE tap to Line-In L. So one fix corrects the whole design, but until it lands, **every downstream phase that depends on SOURCE_NODE is built on an invalid buffer** — Phase 7's routing and Phase 9's validation tests 1–4 included. Phases 5–9 should not be treated as verifiable until this is corrected.

**Three legitimate fixes, with the engineering trade-off stated. Not decided here — this is Conley's call.**

1. **Raise the analog supply (preserves the OPA1642).** For a 2.5 V bias, V+ must be ≥ 6.0 V absolute minimum; realistically 9 V for margin. Cleanest form: a separate 9 V feed for the analog section sharing GND, with **VGND re-centred to ~4.5 V** so the swing is symmetric — 4.5 V sits comfortably inside the 9 V window's 5.5 V ceiling. Output AC-coupling already blocks the DC difference, so nothing downstream cares about the new midpoint. **Best audio performance** — keeps a part chosen for genuinely good reasons (low noise, low distortion, picoamp bias current suited to high-impedance pickups), and preserves the Phase 0.5 SMD soldering already done, with 5 spares in hand. **Cost:** a supply rail the USB-powered product does not currently have, which the eventual PCB must then carry (boost converter or external supply).
2. **Swap to an op-amp whose CM range includes 2.5 V at 5 V — i.e. rail-to-rail input.** Keeps the single USB-derived 5 V rail and needs no new supply. Requires a CMOS/JFET input to retain low bias current for high-impedance sources. Candidates to evaluate against their datasheets, **not to be adopted on this list alone:** TLV9062, OPA2320, MCP6022. **Cost:** new parts to order, the OPA1642 spares and soldered adapters wasted, and RRIO CMOS parts are typically noisier with worse distortion than the OPA1642 — a real concern for an instrument whose purpose is *measurement*.
3. **Stopgap — bias below 1.5 V, keep everything else.** Not in the original framing, worth recording as the only zero-new-parts option. Re-reference pin 3 to ~1.0 V (inside the −0.1 to 1.5 V window) via a divider rather than the 2.5 V VGND rail. Unblocks the bench *today*. **But** the OPA1642's output does not swing rail-to-rail (roughly V− + 0.6 V to V+ − 0.6 V), so an output sitting at 1.0 V has only ~0.4 V of downward headroom — tight and asymmetric. Adequate for phone-level Phase 4 validation, marginal for a hot pickup. **Also changes the input RC corner**, so it interacts with TODO-19. Treat as a bring-up expedient, never as the final design.

**Recommendation, stated as opinion:** for a *measurement* instrument, option 1 is technically strongest — noise and distortion are the product's whole point, and the OPA1642 is the right part operated correctly. Option 2 is the right answer only if keeping a single USB-derived rail is a hard product constraint. The deciding question is what the eventual PCB's power architecture looks like; fixing the breadboard one way and the PCB another wastes the work.

**Secondary finding, same phase, worth checking before Phase 5.** The input bias resistor to VGND is 100 kΩ (confirmed by the runbook's own corner-frequency arithmetic in its Phase 4 Background, which uses R = 100 000). That sets the buffer's input impedance at roughly 100 kΩ. The runbook's own Background justifies the JFET choice by noting *"guitar pickups are high-impedance (6–250 kΩ)"* — but a 100 kΩ input then loads that pickup heavily, rolling off highs and reducing output. Standard guitar-amp input impedance is ~1 MΩ. **The runbook argues for a high-impedance front end and then builds a comparatively low-impedance one.** Harmless for Phase 4 (a phone is a low-impedance source), but it lands directly on Phase 5's first real instrument jack. Tracked as TODO-23.

**Portfolio note (explicitly requested).** This entry is written to stand as engineering evidence: a bench anomaly was traced past two plausible-but-wrong hardware hypotheses to a specification violation in the design itself, verified against the manufacturer's datasheet rather than assumed, with the failing part exonerated by measurement (159 kΩ, no short) instead of being replaced on suspicion. The cheap wrong answer — "swap the chip" — would have destroyed the evidence and left the defect in the design.

**Next:** decide the fix direction (options 1–3 above), then correct `docs/breadboard_bringup_v3.md` § Phase 4 for **both** defects it now carries — the invalid common-mode operating point, and the missing "reconnect USB" step before the end-of-phase verify (TODO-18, now confirmed to have caused a two-day debugging detour).

---

## 2026-09-03 (1) — Phase 4 built through Step 11; +5V rail reads 0 V **with USB connected** — UNRESOLVED, real fault. Leading hypothesis: the supply wire is on VIN, but the runbook specifies VUSB

**Why this entry exists:** records Phase 4 physical progress made in a ChatGPT-driven session, logs an open electrical fault that is **not yet solved**, and captures a separate runbook defect found while investigating it. Nothing here is a fix — the fault is live as of this entry.

> **⛔ SUPERSEDED BY 2026-09-05 (1) — READ THAT FIRST. Do not action anything below.** The 0 V rail this entry investigates was an **unpowered board — USB was not plugged in.** There was no fault, no regression, and no damaged part. This entry's core premise ("0 V measured with power connected") was mistaken, so its regression framing, its reverse-powered-OPA1642 hypothesis, and its enumeration escalation are all void. Retained unedited per this file's never-delete rule, as the record of how a documentation gap (TODO-18) produced two days of false hardware hypotheses.

> **Corrected in-session (2026-09-03), before this entry was ever acted on.** The first draft of this entry recorded the decisive voltage measurement as "not yet taken" and led with the theory that the rail was simply unpowered because the runbook forgets to say "reconnect USB." Conley then confirmed **he was reading 0 V with power plugged in**, which falsifies that theory outright. The affected sections are rewritten below rather than appended to, because the draft asserted a *measurement had not happened when it had* — leaving a false evidence claim at the top of this file would undermine the exact discipline the file exists to enforce. The superseded theory is retained in full under "Rejected hypothesis" below so the reasoning trail survives. The runbook gap it identified is real and is still tracked (TODO-18), it is just **not the cause of this fault.**

**Phase 4 physical build — completed steps (per the runbook's numbering):**
- Step 9 — feedback jumper — done.
- Step 10a — pin 5 (+in B) → VGND, jumper `38f` → bottom-red rail — done.
- Step 10b — pin 6 (−in B) → pin 7 (out B), jumper `37f` → `36f` — done. Unused op-amp half now terminated as a unity-gain follower (prevents the channel-B oscillation the runbook warns about).
- Step 11 — output AC-coupling cap, 10 µF electrolytic, long leg (+) → `35e`, short leg (−) → `48e` — done. **Polarity is correct**: `35e` is the op-amp output sitting at ~2.5 V VGND, `48e` is the downstream side near 0 V DC, so the + terminal is on the higher-DC node as required.
- Steps 12–13 (3.5 mm breakout to LINE-IN-L; test source prep) — status not clearly recorded in the source transcript. **Verify before proceeding.** One related observation was logged: on the breakout cable in use, **white is the tip conductor** (left audio).

**THE OPEN FAULT — do not treat as solved.** At the Phase 4 end-of-phase DMM checks, the +5 V rail read **0 V** against an expected 4.85–5.10 V, **with USB power connected.** This is a real fault, not a measurement setup error.

Diagnostics run so far, and what each one ruled out:

| Test | Result | Rules out |
|---|---|---|
| Voltage, +5 V rail → GND, **USB connected** | **0 V** | — this is the fault |
| Continuity, +5 V rail → GND | **no beep** | hard short across the supply |
| Continuity, "5V/VIN" pin → top-red +5 V rail | **beep** | broken/missing supply jumper |

**THIS IS A REGRESSION, and the suspect window is narrow.** Conley confirmed Phase 1 passed — the +5 V rail **did** work. It has no journal record only because this journal was created *after* Phase 1 was completed; absence of a record here is a bookkeeping artifact, not absence of a passing test. Do not treat the rail as never-proven.

The last independently-confirmed *powered and healthy* state is **Phase 3**, and its evidence is strong: pin 16 measured **3.293 V** at idle. That reading is the Teensy's own internal pull-up — it cannot exist unless the board is powered and the 3.3 V regulator is working. Phase 4's Step 1 then unplugs USB, and every subsequent step is unpowered construction.

**So everything between "Phase 3 measured fine" and "Phase 4 verify reads 0 V" is suspect, and that window contains exactly one thing: the Phase 4 OPA1642 build.** Phases 2 and 3 are behind the last-good marker. Focus there and nowhere else.

**⚠️ Host-side enumeration check, run 2026-09-03 11:14 PDT — the Teensy is NOT enumerating.** `ls /dev/cu.usbmodem*` returns no matches and `arduino-cli board list` shows no Teensy. On **2026-09-01**, the same two checks returned `Teensyduino USB Serial, VID:16C0 PID:0483, serial 19596920` on `/dev/cu.usbmodem195969201` and a Teensy 4.1 at `usb:130000`. **This is ambiguous and must be disambiguated before it is interpreted** — Phase 4 instructs USB unplugged, so if the cable is simply out, this means nothing. **But if USB is currently connected and the board still does not enumerate, that is a major escalation**: it would mean VBUS has collapsed or the board is no longer running, consistent with an overcurrent condition on the breadboard pulling the USB port into current limit. Check the cable state first, then re-run `arduino-cli board list`.

**Second-opinion analysis — leading hypothesis: the supply wire is on the wrong pin. The runbook says VUSB. The debugging session tested VIN. On a Teensy 4.1 these are not the same net.**

Verified directly against `docs/breadboard_bringup_v3.md`:
- Phase 1, Step 2 (line 561): *"Run a red wire from Teensy **`VUSB`** pad → top-red rail. The VUSB pad on the Teensy 4.1 is at the very edge of the board, near the USB-C connector."*
- Grepping the entire 1860-line runbook for VUSB/VIN returns **two hits, both VUSB** (lines 554 and 561). **The runbook never mentions VIN at all.**
- The source debugging session, however, tested continuity to *"Teensy breakout 5V/VIN pin"* and then instructed measuring *"Teensy 5V/VIN → GND."* That pin was assumed equivalent to the documented VUSB source. It is not.

On the Teensy 4.1, **VUSB** carries USB VBUS directly, whereas **VIN** is the external-supply *input* pin. They are linked only through a cuttable trace on the underside of the board. If that link is cut — or if the breakout's screw terminal labeled "5V/VIN" is wired as an input-only path — then VIN sits at 0 V even with USB fully powered and the board running. That produces exactly the observed symptom, and it is consistent with every test above: the wire is intact (beep), nothing is shorted (no beep), the Teensy is alive (enumerates), and yet the rail is dead.

**Ranked hypotheses and the single test that discriminates each.** Re-ranked once the regression was established — a wiring-was-always-wrong theory can no longer be leading, because the same supply wiring delivered 4.85–5.10 V at Phase 1 and a working 3.293 V pull-up at Phase 3.

1. **The OPA1642 is reverse-powered — inserted rotated 180°, or offset by a row/column** *(leading)*. This is the single highest-probability failure in the suspect window, and it fits every symptom at once: a reverse-powered op-amp conducts hard through its substrate, crushing the rail to near 0 V; the resulting path is a diode drop plus current limiting, typically tens-to-hundreds of ohms, **which does not beep on a continuity test**; and the excess draw can push the USB port into current limit, which would explain the board no longer enumerating. The runbook's placement is genuinely easy to get wrong — pins 1–4 run *down* the `e` row (`35e`→`38e`) and pins 5–8 run *back up* the `f` row (`38f`→`35f`), so **pin 8 (V+) is at `35f` and pin 4 (V−) is at `38e`**. A 180° rotation swaps V+ and V− exactly. **Tests, all with USB unplugged:** confirm the notch/pin-1 marker is on the **left**; confirm the adapter straddles the center gap on columns 35–38 with no row offset; then **power up and immediately feel the chip — a reverse-powered op-amp gets hot fast.** Fastest decisive test: **pull the OPA1642 out entirely, power up, and measure the rail.** If it returns to ~5 V, the chip or its wiring is the fault and everything upstream is fine.
2. **A wiring error introduced in Phase 4 shorts or loads the rail** — the phase added the VGND jumper (`38f`→bottom-red), the feedback jumper, the `37f`→`36f` link, and the output cap. Check especially that the pin 4 (V−, GND) connection at `38e` was not accidentally run to the bottom-red **VGND** rail instead of GND; `38e` and `38f` sit on opposite sides of the center gap and are easy to transpose. Test: with USB unplugged, measure top-red↔top-blue in **ohms**, not continuity mode.
3. **Reversed or failed 10 µF electrolytic** — Phase 1 Step 4 places one with (+) in top-red, (−) in top-blue; Phase 4 Step 11 places another. Reversed, an electrolytic conducts and can crush the rail at tens-to-hundreds of ohms — again, **below a dead short, so no beep.** The Phase 1 one is less suspect now (it survived Phase 1's verify) but could have degraded. Feel both for warmth; the runbook's Phase 1 verify warns "nothing should hum, smoke, or get warm." *(Note: the Phase 4 output cap's polarity was checked and is correct — (+) on `35e` at ~2.5 V, (−) on `48e`.)*
4. **Supply wire lands on VIN rather than the documented VUSB pad** *(demoted — was leading before the regression was known)*. The runbook specifies the **`VUSB`** pad (Phase 1 Step 2, line 561) and never mentions VIN anywhere in its 1860 lines, while the debugging session tested "5V/VIN." On a Teensy 4.1, VUSB carries USB VBUS and VIN is the external-supply input, joined only by a cuttable underside trace. **This cannot be the root cause of a regression** — the wire has not moved and it worked at Phases 1 and 3. It remains worth resolving as a *measurement* error: if the probe was on VIN rather than the rail's actual source, the 0 V reading may be describing the wrong net entirely. Probe the VUSB pad directly to settle it, and standardize on the documented pin from here on.

**Rejected hypothesis (retained for the trail).** The first draft of this entry led with: Phase 4 says "Unplug USB" at Step 1 and never says to reconnect, so the 0 V reading was simply an unpowered board. That gap in the runbook is **real and verified** — Phase 4 (lines 848–1056) contains exactly one power instruction, line 884's "Unplug USB", no upload step, and no reconnect, yet its verify table at line 1027+ demands five live readings. Phase 4 is the only phase with this hole (Phase 1 says "Plug in USB"; Phase 2 restores power implicitly via `arduino-cli upload`; Phase 3 asserts USB is plugged in). **But it is not the cause here**, because the 0 V was measured with power connected. Kept as TODO-18 on its own merits — it will bite someone later even though it did not cause this.

**Process note worth keeping.** Two lessons, both cheap: (1) confirm the supply is connected before testing the load — the source session ruled out breadboard faults before establishing whether power was applied; (2) **when a runbook names a specific pin, probe that pin.** Substituting "5V/VIN" for the documented VUSB silently changed which net was under test, and every subsequent measurement inherited that substitution. The continuity beep that appeared to confirm the supply path was, under this hypothesis, confirming a wire to the wrong pin.

**Deferred decision surfaced by the runbook's own Background section (not acted on):** input coupling cap C1 = 10 nF gives a high-pass corner of ~160 Hz, which sits *above* the low-E fundamental at 82 Hz. The runbook flags this and suggests swapping C1 to a 0.1 µF ceramic (20 on hand) for a ~16 Hz corner. Fine to leave at 10 nF for topology validation — but this must be resolved before any bass-inclusive measurement is trusted, and it interacts with the existing TODO-4 note that Test 1's pass band starts at 200 Hz.

**Next, in this order — stop as soon as one explains it:**
1. **Is USB actually plugged in right now?** If yes, re-run `arduino-cli board list`. Still no Teensy ⇒ escalate: VBUS has collapsed or the board is not running, pointing hard at overcurrent from the breadboard.
2. **Pull the OPA1642 out of the breadboard**, power up, measure the rail. Rail returns to ~4.85–5.10 V ⇒ the chip or its immediate wiring is the fault and everything upstream is exonerated in one move. This is the highest-information single test available; do it before any fine-grained probing.
3. If the rail is still dead with the chip out: measure top-red ↔ top-blue in **ohms** (not continuity), and feel both 10 µF electrolytics for warmth.
4. If the rail is fine with the chip out: re-seat the OPA1642 with the **notch on the left**, straddling the gap at columns 35–38, no row offset — then power up and immediately check the chip for heat.
5. Separately, probe the **VUSB pad** directly (board edge by the USB-C connector) to settle whether earlier readings were even taken on the right net, and use the documented pin from here on.

**Backfill owed:** Phase 1's verify passed but predates this journal, so its actual numbers were never recorded. Log them retroactively if they can be recovered — see TODO-20.

---

## 2026-09-01 (3) — Phase 3 DMM evidence added; entry (2)'s "PASSED" is narrowed to *electrical* pass, router event integration explicitly deferred

**Why this entry exists:** entry (2) below recorded Phase 3 as satisfying "the Phase 3 sign-off checklist line in full." That was measured against one line of the checklist, not the runbook's actual four-row end-of-phase verify table. This entry adds the DMM evidence collected afterward and corrects the scope of the claim. Per this file's rule, entry (2) is left unedited — this supersedes its status wording.

**New electrical evidence (DMM, pin 16):**
- Idle, not grounded: **3.293 V** — internal pull-up confirmed active.
- Tapped to GND: **0.0–0.1 V**, fluctuating between the two. Consistent with the runbook's `< 0.1 V` target at the meter's display resolution; the fluctuation is meter quantization, not a floating or partially-pulled node.

Combined with entry (2)'s observation that pins 16, 17, 22, and 24 all showed clean LOW-on-tap / HIGH-on-release transitions in the temporary standalone test firmware, the GPIO layer and the debounce logic are electrically proven.

**The discrepancy, stated plainly.** `docs/breadboard_bringup_v3.md` § Phase 3's end-of-phase verify table has **four** rows, not one:

| Runbook check | Status |
|---|---|
| Each of pins 16, 17, 22, 24 generates a `JACK_CHANGED` event when tapped to GND | **NOT met** — no router in the live path |
| Pin 22 (TS) or pin 24 (XLR) also generates a `ROUTE_CHANGED` event | **NOT met** — same reason |
| DMM with no tap shows ~3.3 V (INPUT_PULLUP active) | **MET** — 3.293 V |
| DMM with pin tapped to GND shows < 0.1 V | **MET** — 0.0–0.1 V |

The two event rows cannot have been satisfied by what was actually run. The temporary test block polled the four pins directly with `digitalRead()` + `JACK_DEBOUNCE_MS`; it never called `signalRouter_init()` / `signalRouter_update()`, which are what emit `JACK_CHANGED` and `ROUTE_CHANGED`. Those functions have never been integrated into the live path in the active tree — that was the deliberate scope call recorded in entry (1) below (running the full router before the audio stack init would have silently expanded the test past Phase 3), and it remains true after the test block's removal.

**Root cause of the confusion, worth flagging for future phases:** the runbook's Phase 3 Step 1 states *"No code changes for this phase — `signalRouter_init()` already configures these pins as `INPUT_PULLUP`"* (`docs/breadboard_bringup_v3.md` line 785). That premise is false for the active tree and always has been. The runbook was written against the intended post-promotion firmware, not against what is actually built today. **Expect the same class of mismatch in later phases** — Phase 5 (line 1200), Phase 7 (line 1531), and Phase 8 (line 1638) all likewise expect live `JACK_CHANGED` / `ROUTE_CHANGED` / `ROUTE_INVALID` output from the router. Read each phase's expectations against the active tree before running it, per this file's source-of-truth precedence rule.

**Decision (Conley's call, adopted):** record Phase 3 as **"GPIO/debounce electrical test passed; full router event integration deferred"** rather than claiming the end-of-phase table was met. What was rejected: marking Phase 3 fully signed off on the strength of the electrical rows alone, which would have put an unearned tick in the sign-off checklist that TODO-10 later depends on. The deferred half does not block Phase 4 — the OPA1642 buffer is an analog signal-path build that does not touch jack-detect events — but it must be closed before TODO-10 breadboard sign-off, and it is genuinely the same work as TODO-11's promotion steps.

**Next:** Phase 4, Step 1 — unplug USB, then place the OPA1642 exactly as `docs/breadboard_bringup_v3.md` § Phase 4 specifies. Note the runbook's own heads-up carried in TODO-4: Test 1's pass band starts at 200 Hz, so extra rolloff below ~300 Hz at this phase is the 10 nF AC-coupling cap, not a fault.

---

## 2026-09-01 (2) — Phase 3 jack-detect GPIO test PASSED on all four pins; temporary test block removed

**Why this entry exists:** closes out Phase 3 from entry (1) below with the hardware result, and records the cleanup that follows a pass per the runbook's own convention (temporary bring-up code is removed once its phase is proven, same pattern as Phase 2).

**Result — Phase 3 bench criterion met:** all four jack-detect GPIOs responded correctly to brief GND taps, confirmed via Serial monitor (this time attached before reset, learning from Phase 2's missed evidence window):
- Pin 16 INSTRUMENT: LOW on tap, HIGH on release — PASS
- Pin 17 RIG_SEND: LOW on tap, HIGH on release — PASS
- Pin 22 RETURN_TS: LOW on tap, HIGH on release — PASS
- Pin 24 RETURN_XLR: LOW on tap, HIGH on release — PASS

This satisfies the Phase 3 sign-off checklist line ("All four GPIOs respond to GND taps") in full — no partial/incomplete evidence this time, unlike Phase 2's LED-only result.

**Cleanup performed:** the temporary `while(true)` jack-detect polling block (added in entry (1), immediately after `Serial.begin`/`delay`, ending in an infinite loop by design) was removed from `guitar_rig_analyzer.ino` in Arduino IDE. Verified via search ("PHASE 3" — no results) before saving. `setup()` now flows directly from `Serial.begin(115200); delay(500);` into the version banner and normal module init (display, audio, etc.) exactly as it did before entry (1)'s edit — the breadboard hardware and LED diagnostics from Phase 2 were left untouched throughout, per instruction.

**Next:** move to the next runbook phase (Phase 4, OPA1642 source buffer per `todo.md`).

---

## 2026-09-01 (1) — TODO-1 promotion complete, compile-clean; Phase 2 hardware-verified and retired; Phase 3 GPIO test staged, not yet flashed

**Why this entry exists:** closes out TODO-1 from the 2026-08-25 (4) entry below, records the Phase 2 breadboard result, and stages Phase 3. Session spanned code edits plus live hardware bring-up on Conley's Mac/Teensy 4.1.

**TODO-1 (pin/config promotion) — done, verified by compile:** the 7 breadboard GPIO constants from `signal_router_config_additions.h` were copied (not `#include`d — per the 2026-08-25 (4) decision to avoid a staging-artifact dependency) directly into `config.h` as plain `#define`s. Also fixed an unrelated pre-existing corruption in `config.h`'s CS-pin comment (a word split mid-token across two lines, missing its `//` prefix — `'lly' does not name a type`). Both fixes confirmed via `arduino-cli compile --fqbn teensy:avr:teensy41 .`: no errors from config.h's territory.

**New compile errors found beyond TODO-1's scope, resolved without promoting unfinished features:** `data_sender.cpp` referenced `RouterStatus::monitor_mode` (doesn't exist yet) and `signal_router.cpp` called `audioCap_setInjectionMode()` (not declared yet, 3 call sites). Conley's explicit instruction: preserve the future architecture, don't invent stub implementations, don't delete the files. Fix: added `ENABLE_DUT_INJECTION` and `ENABLE_MONITOR_MODE` feature-promotion flags to `config.h` (both `0`), wrapped all 3 `audioCap_setInjectionMode()` calls in `#if ENABLE_DUT_INJECTION`/`#endif`, and wrapped the `monitor_mode` payload byte in `#if ENABLE_MONITOR_MODE ... #else payload[3] = 0; #endif`. This compiles clean and makes the unpromoted capabilities explicitly disabled rather than silently broken or fake-implemented. **What was rejected:** writing a stub `audioCap_setInjectionMode()` — would falsely imply the capability exists.

**Phase 2 (LED relay smoke test) — hardware-verified, then retired:** the smoke-test block was first inserted at the end of `setup()` per the original bring-up guide instruction, compiled and uploaded — but the board halted at display init (`RA8875` not present, expected) before ever reaching the smoke test, and neither `[BringUp]` Serial line was observed. Root cause: display init runs before the end of `setup()`, so code placed after it is unreachable on this bench. Fix: moved the block (unchanged) to immediately after `Serial.begin(115200); delay(500);`, before the version banner and `displayEngine_init()`. Recompiled, reflashed: the two relay-GPIO LEDs were observed alternating for ~5 seconds — hardware criterion PASS. Serial evidence incomplete (monitor was attached after the 5s window closed) — not backfilled/invented per Conley's instruction. Per Conley's follow-up, the smoke-test block was then removed entirely from `guitar_rig_analyzer.ino` (Phase 2 closed out; relay LED hardware itself untouched).

**Phase 3 (jack-detect GPIO test) — staged, compile-verified, not yet flashed:** per Conley's explicit scope call, `signalRouter_init()`/`signalRouter_update()` are NOT live yet in the active tree (contradicts the phase-3 runbook's assumption), and the router contract shows `signalRouter_update()` can call `audioEngine_setRoute()` — so running the full router before the audio stack init would silently expand the test past Phase 3. Instead, a standalone `while(true)` GPIO polling block (pins 16/17/22/24, `INPUT_PULLUP`, debounced via `JACK_DEBOUNCE_MS`) was inserted right after `Serial.begin`/`delay`, deliberately before `displayEngine_init()` — the infinite loop means display init and the rest of `setup()` never run during this test, isolating it from the missing RA8875 by design. **Bug caught before it shipped:** typing this block in a real code editor (used Arduino IDE instead of TextEdit specifically to avoid the macOS autocorrect corruption that hit Phase 2's block) triggered the editor's auto-bracket-matching, which left 4 duplicate stray closing braces after the `while` loop — caught by manually counting open/close braces (9 required, 12 present) before saving, and removed. Compile self-verified clean in Arduino IDE (FLASH/RAM stats printed, only the pre-existing benign `setRotation` warning).

**Incident, resolved — no hardware impact:** self-verifying the compile via the IDE's checkmark button unexpectedly proceeded into the upload path (`Opening Teensy Loader...`) rather than stopping at verify-only. Per Conley's instruction, did not press the physical PROGRAM button, did not touch wiring. The attempt timed out on its own (Teensy's HalfKay bootloader never got a manual reset to enter program mode, so no flash write occurred) — confirmed idle toolbar state before saving. Board is still running the Phase 2 firmware. `guitar_rig_analyzer.ino` saved with the Phase 3 block in place; flashing deferred to an explicit, deliberate upload command per Conley's request, so we know exactly which build goes on the board.

**Next:** flash the Phase 3 build explicitly, ground pins 16/17/22/24 briefly one at a time, confirm all four print LOW then return HIGH in the Serial monitor (attach monitor before reset this time, learning from Phase 2's missed evidence window).

---

## 2026-08-25 (4) — Confirmed: source-of-truth precedence rule adopted; promotion decision made (stay at root, minimal integration only)

**Why this entry exists:** closing the loop on the last two entries. Conley agreed the staging-folder explanation is correct, added an important nuance (the broader AI knowledge corpus he has access to genuinely contains multiple historical/staged copies of these modules, including a `signal_generator.cpp` labeled v0.6.0 elsewhere), and proposed a standing precedence rule plus a decision on the open question from the previous entry.

**Nuance preserved:** the corpus available to other sessions/platforms can contain older v0.4/v0.5 files, staged/generated later revisions, and patch artifacts side by side. None of that overturns what was verified directly in this session (this Claude Project's actual docs and the Mac tree both show the same unintegrated v0.5.0 files) — but it explains why an assistant reading a different slice of that corpus could reasonably describe a design-stage revision as committed. The guardrail is the same one this file already learned the hard way: verify against the active tree, don't infer status from a document about the tree.

**Standing rule adopted (now also in this file's "How to use" header above):** the checked active local tree is authoritative for current implementation status. Below that, in order: runbook/bench observations > explicitly staged design docs (contracts, patch headers, staging-folder code) > historical/project-upload snapshots. Never infer "implemented" from a contract, a patch file, a staged source file, or a newer-looking version comment — verify the actual call path in the active build tree.

**Promotion decision (resolves the open question from the 2026-08-25 (3) entry):** do not move `signal_router*` back into a `development/` folder. The files have already crossed that boundary and the Phase 2 smoke test is actively using their interface (`RELAY_SEND_PIN`/`RELAY_RETURN_PIN`) — moving them backward would be a second source-layout churn with no hardware progress to show for it. Instead: keep them at the repo root, treat the promotion as explicitly **incomplete/in-progress** (not done, not reverted), complete only TODO-1 (wire the already-designed pin constants into `config.h`, get the Phase 2 build clean) now, and do not use that compile fix as license to also merge the rest of the DUT-injection audio graph (`s_mixer_send`, `audioCap_setInjectionMode`, the `measurement_engine` arm-time gate). Those remaining promotion steps land only when their corresponding hardware phase exists and can be tested immediately — not speculatively ahead of the hardware. This preserves the original point of staging (no untestable behavior in production code) without undoing the file move that already happened.

**Current state model (precise, six-part — replaces any single implemented/not-implemented flag for this feature):**
1. Router control layer (`signal_router.h/.cpp`) — drafted, moved into repo root.
2. Pin/config promotion (`signal_router_config_additions.h` → `config.h`) — incomplete (= TODO-1).
3. Audio injection graph (`s_mixer_send`, generator send-path wiring) — incomplete, not started.
4. Arm-time injection gating (`signalRouter_canInject()` in `measurement_engine`) — incomplete, not started.
5. Compilation of the current repo root — presently blocked (undefined pin macros).
6. Breadboard verification — not yet begun (Track A, Phase 2 onward).

**Also confirmed already correct, no change needed:** todo.md's TODO-12 (result UX polish) proof criterion already reads "a measurement run using the currently supported MODE_LIVE complex-FFT path (not MODE_PRECISION — `arm()` still rejects that, see TODO-13)" — this was fixed in the 2026-08-25 (2) rewrite and does not say "precision measurement." No further change needed there.

**Next:** TODO-11 in todo.md is reworded to reflect the "stay at root, minimal integration only, defer the rest to matching hardware phases" decision instead of leaving it as an open question.

## 2026-08-25 (3) — "Newer v0.6 branch" theory checked and not supported; the real explanation is a staging folder promoted prematurely

**Why this entry exists:** a second review round claimed this session's Mac-tree findings and an earlier pass over "the project files uploaded into this conversation" were reading two different generations — an old v0.5 `measurement_engine.cpp`/`audio_capture.cpp`/`signal_generator.cpp` plus a newer v0.6 set with the injection wiring actually done, both supposedly present in the project materials. Before writing that into this file as the reconciling fact, it was checked directly against this Claude Project's actual documents (not against the earlier prose description of them) — same discipline as the previous entry. **The newer-v0.6-generation theory does not hold up.** What's actually going on is more specific and more useful to know.

**What was checked:** `project_info` lists each of the 30 project docs with its upload timestamp. All 30 were created within the same two-minute window (2026-05-15, 18:37:04–18:38:55) — one snapshot, not two generations. `measurement_engine.cpp`, `audio_capture.cpp`, and `signal_generator.cpp` each appear exactly once in that list (only `README.md` appears twice — see below, that duplication is real but means something different). Reading all three files' actual content directly: all three are tagged v0.5.0, and their content is substantively identical to what's on Conley's Mac — same "DUT injection not yet wired" warning printed in `measurementEngine_arm()`, same `s_gen_mixer → s_mixer_ret` slot-2 monitor-only wiring in `signal_generator.cpp`, no `s_mixer_send`, no `audioCap_setInjectionMode` definition anywhere in `audio_capture.cpp`. There is no second, newer copy of any of these three files anywhere this session can read.

**What actually explains the duplicate `README.md` and the gap:** the project also holds a *second* `README.md` — not a newer/older pair of the same doc, but the repo's root `README.md` plus a separate `development/README.md` describing a documented pre-integration staging area. Its own words: *"C++ source for capabilities that are designed and partially implemented but not yet wired into the live firmware. Files here are not compiled by the Arduino/Teensy build — they live one level below the repo root."* It lists `signal_router.h`, `signal_router.cpp`, `signal_router_config_additions.h`, and `audiocap_injection_api.h` as exactly the contents of that staging folder, and gives an explicit 8-step **promotion checklist** to move them into the live build:
1. Hardware (relay board + jack-detect wiring) exists on the bench.
2. Move the `signal_router*` C++ files and `audiocap_injection_api.h` into the repo root.
3. Merge `signal_router_config_additions.h`'s GPIO assignments into the root `config.h`.
4. Add `s_mixer_send` to `audio_capture.cpp`.
5. Implement `audioCap_setInjectionMode(bool)` in `audio_capture.{h,cpp}`.
6. Add `signalRouter_canInject()` / `setInjectionEnabled()` calls to `measurement_engine`'s ARM and CAPTURE transitions.
7. Move `signal_router_contract.md` to `docs/` as the implementation reference.
8. Run the firmware-review cycle on the integrated code.

The repo root `README.md` (present on Conley's Mac too) independently corroborates this and is explicit about the danger: *"`development/` in particular contains C++ source for the next milestone (signal_router, data_sender) that is intentionally not yet wired in — silently including it would either break the build or worse, change behavior. Copy `.ino`, `.cpp`, `.h` from the root explicitly."*

**Where the Mac tree actually stands against that checklist, verified directly:**
- Step 1 (hardware on the bench) — in progress; this is Track A in todo.md, just getting started (Phase 2 not yet run).
- Step 2 (move `signal_router*` files into the repo root) — **done**, but there is no `development/` folder on the Mac at all anymore (confirmed: `ls development/` → no such directory). The staging files are sitting directly in the repo root today.
- Steps 3–6 (merge pins into `config.h`, add `s_mixer_send`, implement `audioCap_setInjectionMode`, wire the `measurement_engine` gate) — **not done**, confirmed by direct inspection in the previous entry.
- Step 7 (move the contract doc to `docs/`) — not done; `signal_router_contract.md` is also still at the repo root.

**So the accurate statement is:** the promotion checklist's own step 1 is supposed to precede step 2 — hardware should exist on the bench *before* the staging files move into the build path — and on the Mac tree, step 2 happened while step 1 was still outstanding. That's the direct, now-precisely-understood cause of the compile blocker recorded in the previous entry: the project's own documentation explicitly predicted this exact failure mode, and it happened. There is no missing "newer implementation" to go find or merge — the implementation work described in steps 3–6 has not been written anywhere accessible to this session, on the Mac or in the project docs.

**Open question for Conley, not decided here:** whether to (a) leave the `signal_router*` files at the repo root and just complete TODO-1 (wire the pin constants into `config.h`) so the Phase 2 smoke test can compile today, deferring steps 3–6 until Track A's hardware phases are further along — the pragmatic path, since Phase 2 code is already live in the `.ino` — or (b) move the files back into a `development/` folder per the checklist's own ordering and re-promote them later in a controlled way once hardware is proven. Either is defensible; this just needed to be surfaced rather than decided unilaterally.

**Decision:** todo.md's TODO-11 is reworded from "reconcile/merge an existing newer v0.6 implementation" (unsupported) to "complete the documented promotion checklist steps 3–6 for the signal_router staging code already sitting in the repo root" — the work itself was never done anywhere this session can see, on either source. The compile-fix priority (TODO-1) and phase ordering from the previous two entries stand unchanged; this entry only corrects the "where does the missing code live" question.

**Next:** if Conley does have a genuinely newer/different `signal_router` implementation from another source (a different chat's uploads, a separate branch, work in progress elsewhere), that would still be worth reconciling — but it isn't in this Claude Project's knowledge base or on the Mac tree, so it can't be assumed to exist without being pointed to directly.

## 2026-08-25 (2) — Corrected record: breadboard bring-up is active, and the earlier DUT-injection status was overstated; found the runbook

**Why this entry exists:** Conley reviewed the first journal/todo entries and flagged that they collapse "firmware written" and "hardware/build proven" into one status, and that the DUT-injection item in particular was stale. Before rewriting anything, every specific claim in his critique was checked against the actual source tree (not against prose docs describing intent) — these two files exist so a future AI can trust them without re-deriving the codebase, so unverified claims don't belong in them either. Some of the critique was right, some was overstated relative to the current source, and a genuine, previously-undocumented compile blocker turned up in the process. Full trail below. This entry supersedes the DUT-injection status recorded in the entry below it; that entry is left unedited, per this file's own "never delete, add a correction" rule.

**Confirmed correct, verified directly in source:**
- `signal_router.h` / `signal_router.cpp` are genuinely tagged v0.6.0 and implement a real relay-control + jack-debounce state machine (relay pins, `audioCap_setInjectionMode()` calls, `signalRouter_canInject()`).
- `signal_router_config_additions.h` genuinely defines `RELAY_SEND_PIN=14`, `RELAY_RETURN_PIN=15`, `JACK_INSTRUMENT_PIN=16`, `JACK_RIG_SEND_PIN=17`, `JACK_RETURN_TS_PIN=22`, `JACK_RETURN_XLR_PIN=24`.
- There is an active, detailed breadboard bring-up runbook: `docs/breadboard_bringup_v3.md` (v3, dated 2026-06-01, ~1860 lines; supersedes v1/v2, which are kept alongside for reference). It defines nine phases (0, 0.5, 1–9), each with a parts tray, numbered steps, an end-of-phase verify, and a final sign-off checklist. **This is now the canonical hardware bring-up source.** todo.md points to it by phase number instead of duplicating its steps, so the two can't drift apart — read the runbook itself for step-by-step detail.
- The relay decision is real and specific: 10× TQ2-L2-5V (latching DPDT) were purchased for the eventual PCB, but the breadboard uses 2× TQ2-5V (non-latching, DigiKey 255-1004-5-ND) instead, because `signal_router.cpp` drives each relay with a single static `digitalWrite(PIN, HIGH/LOW)` — a latching relay needs a set coil *and* a reset coil (two GPIOs), which the current firmware doesn't implement. (`docs/breadboard_bringup_v3.md`, "About your relays" sidebar and Phase 6.) This is exactly the kind of decision that looks like a mistake to a future AI ("why only 2 of the 10 relays bought?") without this note.
- Pink-noise stimulus is a real, labeled stub, not a false claim: `signal_generator.cpp` explicitly says white noise works and "pink 1/f shaping IIR filter to be added." `StimulusType::INTERNAL_PINK` exists as an enum value but does not yet produce spectrally-shaped output.
- Generator alignment is block-level, not sample-accurate, by design: `signal_generator.cpp` states alignment is achieved "within one block, ≈2.9 ms" via main-loop timing, and true interrupt-level/sample-accurate alignment is explicitly called out as a future enhancement. This is a measurement-limitation fact, not a bug — recorded so no future session claims tighter phase/latency accuracy than the hardware currently delivers.
- The validation harness is deliberately conservative-then-tighten by design: `validation.cpp` (tagged `CHANGED [audit-9]`) adds an advisory whenever a passing criterion has more than 2x headroom over its tolerance, explicitly prompting tightening later. Insight thresholds are provisional in the same spirit. Don't "fix" wide tolerances without checking whether they're intentional placeholders awaiting real hardware characterization.
- SELF_TEST is not physical validation: `measurement_engine.cpp`'s `SELF_TEST` state only waits for the audio block counter to advance past a baseline — it proves the audio engine is alive, nothing about the analog signal path. A future AI must not treat "self-test passed" as breadboard sign-off.
- `signal_router.h` explicitly marks extended monitor modes as unimplemented: `signalRouter_setMonitorMode()`'s own doc comment reads "NOT YET IMPLEMENTED — reserved for Phase B (v0.6.1)." If a build error traces back to monitor-mode scaffolding, the fix is to isolate/stub that call site — not to implement Phase B monitor modes just to silence the error.

**Overstated in the critique — corrected against the actual .cpp/.h files, not the design-contract doc:**
`signal_router_contract.md` is titled "v0.6 Design Contract" and reads as a spec with a three-step integration checklist, not a record of completed work. Checked each step against the real files:
1. "audio_capture.cpp: Add `s_mixer_send`..." — **not done.** `audio_capture.cpp` / `.h` are still tagged v0.5.0 and contain no `s_mixer_send` and no `audioCap_setInjectionMode` definition. `audiocap_injection_api.h` is a patch note ("This function is **added to** audio_capture.h") — it has not been applied.
2. "signal_generator.cpp: make `s_gen_mixer` non-static..." — **not done.** `signal_generator.cpp` is still v0.5.0; `s_gen_mixer` feeds only `s_mixer_ret` slot 2 (the *monitor/return* mixer) — the same "audible on monitoring right channel, not on Rig Send" behavior the original journal entry described. There is no connection to any send-path mixer anywhere in that file.
3. "measurement_engine.cpp: check `signalRouter_canInject()` before arming..." — **not done.** `measurement_engine.cpp` is still v0.5.0 and contains zero references to `signalRouter_canInject()`. `arm()` does not gate on router state at all.

So DUT injection is **not** "implemented in firmware, pending only bench verification." The relay/jack-detect control layer has been drafted against the v0.6 contract; the audio-path injection wiring and the arm()-time gate described in that same contract have not been started.

**New finding — a real, previously undocumented compile blocker:** `guitar_rig_analyzer.ino` (last modified 2026-08-19, the newest file in the tree) already contains a live block — `// ==== PHASE 2 SMOKE TEST — REMOVE BEFORE PHASE 3 =====` — using `RELAY_SEND_PIN` / `RELAY_RETURN_PIN` directly. Those macros are defined only in `signal_router_config_additions.h`. A project-wide search for `#include "signal_router_config_additions.h"` turns up zero hits, and `config.h` (still v0.5.0) doesn't define the pins itself. So **as currently committed, this firmware does not compile** — not just the `.ino`'s Phase 2 block, but `signal_router.cpp` itself (it references `RELAY_SEND_PIN` directly too). Separately, `signal_router.h` isn't `#include`d by the `.ino` or by anything else in the active build, so even once it compiles, nothing currently calls into the router module. Practically: **Phase 2 as written cannot yet have been run successfully against this exact source snapshot.** The fix matches what Conley described — fold `signal_router_config_additions.h`'s existing pin constants into the canonical `config.h` (or `#include` the file there). The pin numbers are already correct; do not invent new ones. This is the single highest-priority code fix right now (todo.md TODO-1).

**Also confirmed, newly recorded:** the pin map is explicitly a breadboard-stage assignment, not a finalized PCB constraint — `docs/breadboard_bringup_v3.md` frames the whole exercise as "a working breadboard prototype... that will eventually live on a custom PCB," with sign-off feeding into a KiCad schematic. Pins 14/15/16/17/22/24 should not be treated as immutable product architecture. Also: the runbook's sign-off step says to record results in `docs/bench_runbook.md` §8 — that file does not exist yet in `docs/`. It will need to be created at actual sign-off time; don't assume it already holds bench history.

**Also reconfirmed unchanged:** `measurementEngine_arm()` still correctly rejects `MODE_PRECISION`/`MODE_LF` — that part of the original todo.md (precision FFT rebinning item) was accurate and is untouched by this review.

**Decision:** Reordered todo.md so hardware bring-up leads (compile fix → Phase 2 → … → Phase 9 → sign-off), broken into one item per phase carrying the runbook's own pass criterion, instead of one giant "implement signal_router" item. Result-UX polish and the other software-only items move down but are not dropped. Hardware-adjacent todo items now carry a maturity tag — drafted / compiles / bench-verified — alongside the usual status emoji, since collapsing those two facts into one flag was the root problem Conley flagged.

**Next:** once the compile fix lands and Phase 2 actually runs on hardware, update its todo.md entry with the observed result (LED toggle behavior + serial log excerpt) — not just "code written."

## 2026-08-25 — Created ai/journal.md and ai/todo.md as the cross-platform knowledge base

**Why:** Work on this firmware spans multiple AI sessions and potentially multiple AI platforms. Without a persistent, in-repo record, every new session has to re-derive the architecture from scratch by re-reading 21+ source files. These two files exist so any AI (or human) picking up the project can orient in minutes: journal.md explains *why* decisions were made, todo.md tracks *what* is outstanding, why it matters, and how to prove it's done.

**Context carried forward from the Claude Project instructions (source of truth as of this date — read there for full detail):**
- Architecture: `audio_capture` is the sole owner of audio hardware (I2S / SGTL5000 / mixers / FFT / peak objects / raw AudioRecordQueues). `audio_engine` (live path) and `measurement_engine` (precision path) are the two independent consumers reading from it. `display_engine` is a pure renderer with no signal processing. `export_engine`, `calibration_store`, `insights_engine`, and `validation` are supporting subsystems. Canonical timing source is `AudioStream::update_counter` — every time-sensitive operation references this single timebase.
- `measurement_engine` is a real 8-state machine (ARMED / CAPTURE / PROCESSING / RESULT / EXPORTING / ABORTED, plus related states) with a true complex FFT path: Hann window, Sxy real/imaginary accumulation, atan2 phase, segment-aware phase unwrapping, group delay, calibration correction application, correct `capture_start_block` / `capture_end_block` tracking, and distinct abort reasons for USER_CANCEL vs ROUTE_CHANGED.
- Design philosophy (non-negotiable): MEASUREMENT (direct fact) vs ADVISORY (interpretation) must stay separated in `insights_engine`, and advisories are suppressed when measurement quality is low. Deferred features must be honestly blocked at runtime — never silently degrade into fake functionality or aspirational comments that don't match behavior.
- Known-completed fixes — treat these as done, do not re-report as bugs: CRC-32 seed/final-XOR bug; `getRawSamples()` all-or-none contract; JSON escaping / non-finite (NaN/Inf → JSON null) export handling; segment-aware phase unwrap across NaN gaps; `capture_end_block` now stamps the last accepted capture frame (not later processing time); TF erase logic respects previous validity gaps; insight-band mean helpers return NaN on no valid bins and detectors guard against non-finite results; validation preflight aborts on ROUTE_CHANGED; rig-analysis and self-calibration factories use EXTERNAL stimulus (not a silent fake INTERNAL path); non-H1 estimators are rejected rather than silently mislabeled; route-change abort is distinct from user cancel via `measurementEngine_notifyRouteChanged()`; result screen wiring (`displayEngine_showResult`, `displayEngine_showAborted`, `displayEngine_restoreLive`) is implemented and the serial `x` command from RESULT correctly calls `measurementEngine_returnToLive()` before restoring the live display.
- Intentionally deferred, and already handled *honestly* (blocked/labeled at runtime, not bugs unless behavior starts claiming otherwise):
  1. `signal_router` / DUT injection — the internal stimulus generator is audible on the monitoring right channel but does not yet reach the physical RIG SEND output. Internal-stimulus factories that would imply real DUT injection must not silently claim to work; current public factories use EXTERNAL stimulus where appropriate.
  2. Precision FFT rebinning — `MODE_PRECISION` and `MODE_LF` exist conceptually in the code but `arm()` rejects them until the OCRAM accumulator + rebinning logic are actually implemented.
  3. Touch UI — the display's result view and insight panel are implemented for rendering; touch interaction is still future work.
- Review priorities going forward (per project instructions): prioritize logic bugs, state-machine mismatches, incorrect metadata, invalid exports, missing NaN/undefined-bin guards, route-change/cancel/abort-cause correctness, display-state vs measurement-state mismatches, and stale comments that misdescribe behavior — over flagging "not yet implemented" items that are already honestly blocked and documented. Also: prefer the newest canonical revision of a file when duplicates/snapshots exist.

**Decision:** Seeded todo.md from the project's stated "Recommended next milestone" order (1. polish result UX, 2. implement signal_router / true DUT injection, 3. implement precision FFT rebinning) plus touch UI, so these don't live only in prose instructions and get lost between sessions/platforms.

**Next:** As real review or coding sessions happen on this project (from any AI platform), log findings and decisions here — newest entry on top — and keep todo.md's status/proof fields current as items move or complete.

