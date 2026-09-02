# Guitar Rig Analyzer — AI Todo

Purpose: a running list of outstanding work, written for AI readers. Every item states *why* it matters, *what* needs to happen, and *how to prove* it's actually done — so "done" means verified, not just coded.

How to use this file:
- Keep items in priority order (top = do next), not chronological order. See journal.md for the chronological reasoning trail.
- Status legend: 🔴 not started · 🟡 in progress · 🟢 done (verified) · ⚪ blocked (on another item, or on something external)
- **Hardware-adjacent items also carry a maturity tag in brackets: [drafted] source exists but is unverified or doesn't compile · [compiles] builds clean, not yet run on hardware · [bench] actually verified on the physical board.** "Implemented in firmware" and "proven on hardware" are different facts — collapsing them into one status was a real mistake caught in review on 2026-08-25 (see journal.md). Don't repeat it.
- When an item is completed, don't delete it — mark it 🟢, fill in the proof that was actually observed, and add a one-line pointer to the journal.md entry that covers the reasoning/decision. Move it down to the "Completed" section at the bottom.
- Never mark something 🟢 on the basis of "the code looks right" — only on the basis of the proof criterion actually being checked (a validation harness run, an exported file inspected, a state transition observed, a bench photo/serial log).
- The canonical hardware bring-up procedure is `docs/breadboard_bringup_v3.md` (v3, supersedes v1/v2). Items below point to it by phase rather than duplicating its steps — read the runbook itself for full detail; this file only tracks status and the pass criterion.
- **Source-of-truth precedence:** the checked active local tree is authoritative for current implementation status — not project documents, uploaded snapshots, staging files, or patch artifacts, which are reference material only until their changes are confirmed present in the active tree. Full reasoning in journal.md 2026-08-25 (3) and (4).

---

## Track A — Hardware bring-up (current execution path)

The physical device is mid-breadboard. This track leads TODO priority over software-roadmap items until the board is signed off.

### TODO-1 — Fix the current compile blocker: wire relay/jack pin constants into the active build 🔴 [compiles clean — verified 2026-09-01, see journal.md]
**Why:** `guitar_rig_analyzer.ino` already contains a live "PHASE 2 SMOKE TEST" block using `RELAY_SEND_PIN` / `RELAY_RETURN_PIN`, and `signal_router.cpp` references the same pins plus the four jack-detect pins. None of those macros are defined in the active build — they only exist in `signal_router_config_additions.h`, which nothing currently `#include`s. As committed, neither `signal_router.cpp` nor the `.ino`'s Phase 2 block can compile. (Verified 2026-08-25 — see journal.md.)
**What:** Fold `signal_router_config_additions.h`'s existing pin definitions into the canonical `config.h` (or `#include` that file from `config.h`). The pin numbers (14/15 relay, 16/17/22/24 jack-detect) are already correct — do not invent new ones. Separately: if unrelated errors trace to Phase-B monitor-mode scaffolding (`signalRouter_setMonitorMode()`), isolate/stub that call site rather than implementing Phase B monitor modes just to silence the error — it's explicitly marked "NOT YET IMPLEMENTED — reserved for Phase B (v0.6.1)" in `signal_router.h`.
**Proof:** `guitar_rig_analyzer.ino` compiles clean for the Teensy 4.1 target with the Phase 2 smoke-test block intact.
**Evidence required before this moves off 🔴 (set 2026-08-25):** the compile result itself. If it fails, log the first meaningful compiler error verbatim and stop there — do not infer anything about TODO-2 beyond that point. Code presence (an edited `config.h`) is not evidence; a real build attempt is.

### TODO-2 — Phase 2: GPIO smoke test (relay pins 14/15) 🟡 hardware-verified (LED behavior PASS), Serial evidence incomplete — test block since removed, see journal.md
**Why:** Already drafted directly in the `.ino`, now compiles and has been run on hardware — see journal.md 2026-09-01 (1).
**What:** Run per `docs/breadboard_bringup_v3.md` § Phase 2.
**Proof (runbook sign-off criterion):** pins 14/15 toggle 0↔3.3 V, LEDs alternate for ~5 s, both outputs return LOW at the end. Sign-off checklist line: "LED smoke test toggles cleanly at boot."
**Evidence required before this moves off 🔴 (set 2026-08-25):** exactly four things, logged in journal.md when they exist — (1) TODO-1's compile result, (2) the exact Phase 2 serial output, (3) the observed LED behavior on pins 14/15, (4) whether that behavior meets the runbook's pass criterion above. Nothing short of that (a code diff, a "should work" assessment) advances this item's status.

### TODO-3 — Phase 3: Jack-detect, simulated with wire jumpers (pins 16/17/22/24) 🟡 all four pins PASS (LOW on tap, HIGH on release) — test block removed, see journal.md 2026-09-01 (2)
**Why:** Proves the four jack-detect GPIOs and the debounce logic before any real jacks are installed.
**What:** Ground pins 16, 17, 22, 24 individually per the runbook; TS/XLR return changes should also exercise the route-change path.
**Proof:** debounced `JACK_CHANGED` events observed for all four pins. Sign-off checklist line: "All four GPIOs respond to GND taps."

### TODO-4 — Phase 4: OPA1642 SOURCE buffer 🔴
**Why:** First real analog signal path (unity-gain JFET buffer) on the breadboard.
**What:** Build per `docs/breadboard_bringup_v3.md` § Phase 4.
**Proof:** Sign-off checklist line: "Phone test signal visible on SOURCE spectrum." Note: Test 1's pass band starts at 200 Hz — extra rolloff below ~300 Hz at this phase is the 10 nF AC-coupling cap, not a fault (runbook heads-up).

### TODO-5 — Phase 5: First real instrument jack (Switchcraft #11) 🔴
**Proof:** Sign-off checklist line: "Switchcraft #11 + invert define both work — guitar plays through, detect events fire."

### TODO-6 — Phase 6: First relay driver, RELAY_SEND (TQ2-5V) 🔴
**Why:** Breadboard uses non-latching TQ2-5V (DigiKey 255-1004-5-ND) instead of the TQ2-L2-5V purchased for the eventual PCB, because current firmware drives each relay with one static GPIO — see journal.md 2026-08-25 entry for the full reasoning. Don't "fix" this by swapping in the latching parts without also changing the firmware.
**Proof:** Sign-off checklist line: "TQ2-5V #1 clicks on `p`/`P`; continuity matches expected state."

### TODO-7 — Phase 7: RELAY_RETURN + full signal wiring (Rig Send / Rig Return TS) 🔴
**Proof:** Sign-off checklist line: "Full route matrix (4 jack combinations) produces correct route description on Serial."

### TODO-8 — Phase 8: XLR return detection 🔴
**Proof:** Sign-off checklist line: "XLR + microswitch detect both work end-to-end."

### TODO-9 — Phase 9: Validation harness on real hardware (tests 1–4) 🔴
**Why:** This is `validation_runAll()' exercised against actual physical loopback/pads/filters — not `SELF_TEST`, which only proves the audio block counter is advancing (see journal.md). Do not treat a passed self-test as equivalent to this.
**What:** Run tests 1 (flat loopback), 2 (channel-swap symmetry), 3 (known 6 dB gain offset), 4 (known RC filter response) per the runbook.
**Proof:** Sign-off checklist line: "`1`, `2`, `3`, `4` all PASS."

### TODO-10 — Breadboard sign-off 🔴
**Why:** The runbook is explicit that build success and even individual phase passes are not the finish line — full board sign-off requires physical evidence before moving to PCB design.
**What:** Photograph the entire board, save serial logs, and record the results in `docs/bench_runbook.md` §8 (this file does not exist yet — it must be created at sign-off time, don't assume prior bench history is already captured there).
**Proof:** all Phase 1–9 sign-off checklist boxes ticked, photos taken, `docs/bench_runbook.md` §8 updated with the date.

---

## Track B — Firmware-only (deferred until hardware catches up, or independent of it)

### TODO-11 — Complete the signal_router promotion (steps 3-6), one step per matching hardware phase — not ahead of it ⚪ blocked on Track A
**Why:** `signal_router.h/.cpp`, `signal_router_config_additions.h`, and `audiocap_injection_api.h` are staging code from the documented promotion checklist (`development/README.md`), already moved to the repo root (step 2 done, no `development/` folder remains) but not integrated: no `s_mixer_send` in `audio_capture.cpp`, the generator still only feeds the monitor mixer, `measurement_engine.cpp` never calls `signalRouter_canInject()`. Confirmed by reading the actual files directly, twice (Mac tree and this Claude Project's own docs) — see journal.md 2026-08-25 (3) and (4). **Decision (2026-08-25 (4)):** do not move the files back into `development/` — they're already wired into the live Phase 2 smoke test (`RELAY_SEND_PIN`/`RELAY_RETURN_PIN`) and reverting would be pure source-layout churn with no hardware progress to show for it. Keep them at the repo root, but keep the promotion explicitly marked incomplete/in-progress — do not treat the TODO-1 compile fix as license to also merge the injection audio graph.
**What:** Complete checklist steps 3-6 incrementally, each gated on its own hardware phase actually existing and being testable, not speculatively ahead of it: merge the pin constants into `config.h` now (TODO-1 — pins are already correctly designed, this is integration only, not pin design); add `s_mixer_send` to `audio_capture.cpp` only once the relay/routing hardware it depends on (Phase 6/7) is on the bench; implement `audioCap_setInjectionMode` and the `measurement_engine` arm-time gate (`signalRouter_canInject()`) only once injection can be immediately tested against real hardware, not before.
**Proof:** an INTERNAL-stimulus MODE_LIVE run (not MODE_PRECISION — see TODO-13) shows the actual generated signal present in the RETURN_NODE capture with a rig connected — not silence, not today's monitor-only loopback.

### TODO-12 — Polish result UX in display_engine 🟡
**Why:** Was the previously-stated next milestone from the software roadmap. Still real work, just not the current execution path — the project has moved into hardware bring-up (Track A) first.
**What:** Using the existing panel geometry — meter panel (quality/provenance header), spectrum panel (insight list), TF panel (measured `tf_cal_mag_db` curve using existing TF chrome) — refine the result screen's layout, readability, and the MEASUREMENT-vs-ADVISORY visual distinction in the insight panel.
**Proof:** A measurement run using the currently supported MODE_LIVE complex-FFT path (not MODE_PRECISION — `arm()` still rejects that, see TODO-13) reaches RESULT and the display clearly shows quality/provenance, the TF curve (correct NaN pen-lift on invalid bins), and an unambiguous MEASUREMENT-vs-ADVISORY insight list, reviewed against real captured data.

### TODO-13 — Precision FFT rebinning (MODE_PRECISION / MODE_LF) 🔴
**Why:** These modes exist conceptually in `measurement_core.h` but `arm()` rejects them (confirmed still true on 2026-08-25) because the OCRAM accumulator and bin-remapping logic don't exist yet.
**What:** Implement the OCRAM accumulator and frequency-bin remapping for MODE_PRECISION and MODE_LF; only remove the `arm()`-time rejection once the full path produces real, correctly-rebinned data end to end.
**Proof:** `arm()` accepts MODE_PRECISION/MODE_LF, a measurement completes through RESULT with correctly rebinned data, verified against the validation harness's known-response tests — not just "it produces numbers."

### TODO-14 — Touch UI interaction 🔴
**Why:** `display_engine` renders the result view and insight panel; all measurement control still goes through the serial `x` command.
**What:** Add touch handling wired to the same `measurement_engine` control entry points the serial `x` command uses today.
**Proof:** A touch action produces the identical state transition the serial command produces: ABORTED → acknowledge + restore live; RESULT → `measurementEngine_returnToLive()` + restore live; active measurement → cancel. Live display updates must still only occur in IDLE / ARMED.

### TODO-15 — Pink noise 1/f shaping 🔴 low priority
**Why:** `StimulusType::INTERNAL_PINK` exists as an enum value but `signal_generator.cpp` only implements white noise; the 1/f IIR shaping is explicitly stubbed. Could otherwise be mistaken for a real pink-noise source.
**What:** Implement the 1/f shaping filter in `signal_generator.cpp`.
**Proof:** measured spectrum of INTERNAL_PINK output shows a ~-3 dB/octave slope, not a flat (white) spectrum.

### TODO-16 — Real-hardware tolerance/threshold tuning (validation.cpp + insights_engine.cpp) 🔴 low priority — do after Track A produces consistent good measurements
**Why:** The validation harness and insight thresholds are deliberately conservative placeholders (`validation.cpp`'s tighten-tolerance advisory fires when a passing criterion has >2x headroom). Don't forget to revisit these once real hardware is characterized — and don't "fix" wide tolerances before then, they're intentional.
**What:** After Phase 9 (TODO-9) passes repeatedly on real hardware, tighten the tolerance/threshold constants based on observed headroom.
**Proof:** tolerances tightened, validation still passes consistently across repeated runs.

### TODO-17 — Sample-accurate (interrupt-level) generator alignment ⚪ only if accuracy requirements justify it
**Why:** Current alignment is block-level (~2.9 ms, one Audio Library block) by design; true interrupt-level alignment is explicitly future work in `signal_generator.cpp`. Only worth doing if a future latency/phase-accuracy claim needs tighter-than-one-block precision.
**What:** Patch the Audio Library interrupt handler for sample-accurate stimulus start.
**Proof:** measured start-alignment jitter is sub-sample, vs. today's ≤1-block bound.

---

## Completed (verified — do not re-report as bugs; see journal.md for the reasoning trail)

The following were already fixed as of the 2026-08-25 baseline and confirmed via the project's iterative bug-fix passes. Listed here so future sessions don't waste time re-discovering or re-litigating them:

- CRC-32 seed/final-XOR bug in calibration_store — 🟢
- `getRawSamples()` all-or-none contract — 🟢
- JSON escaping / non-finite (NaN/Inf → `null`) export handling in export_engine — 🟢
- Phase unwrap made segment-aware across NaN gaps — 🟢
- `capture_end_block` stamps the last accepted capture frame, not later processing time — 🟢
- TF erase logic respects previous validity gaps — 🟢
- Insight-band mean helpers return NaN on no valid bins; detectors guard against non-finite results — 🟢
- Validation preflight aborts on ROUTE_CHANGED — 🟢
- Rig-analysis factory uses EXTERNAL stimulus — 🟢
- Self-calibration factory uses EXTERNAL stimulus (DUT injection wiring itself tracked separately — see TODO-11) — 🟢
- Non-H1 estimators rejected instead of silently mislabeled — 🟢
- Route-change abort distinct from user cancel via `measurementEngine_notifyRouteChanged()` — 🟢
- Result screen wiring implemented; `x` from RESULT uses `measurementEngine_returnToLive()` — 🟢

