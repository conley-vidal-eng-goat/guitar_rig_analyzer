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

### TODO-1 — Fix the current compile blocker: wire relay/jack pin constants into the active build 🟢 **DONE — compile proof satisfied 2026-09-01, status corrected 2026-09-07**
**Status correction (2026-09-07, record-keeping only — no code change):** this item carried 🔴 alongside a bracketed note saying its own proof was already met. The two contradicted each other for six days. The stated proof criterion — "`guitar_rig_analyzer.ino` compiles clean for the Teensy 4.1 target with the Phase 2 smoke-test block intact" — was satisfied on 2026-09-01 (journal.md 2026-09-01 (1)) and has been re-satisfied by every build since; the firmware captured from the board on 2026-09-07 is that build running on hardware. Marked 🟢 on the evidence that already existed, not on new evidence.
**Why:** `guitar_rig_analyzer.ino` already contains a live "PHASE 2 SMOKE TEST" block using `RELAY_SEND_PIN` / `RELAY_RETURN_PIN`, and `signal_router.cpp` references the same pins plus the four jack-detect pins. None of those macros are defined in the active build — they only exist in `signal_router_config_additions.h`, which nothing currently `#include`s. As committed, neither `signal_router.cpp` nor the `.ino`'s Phase 2 block can compile. (Verified 2026-08-25 — see journal.md.)
**What:** Fold `signal_router_config_additions.h`'s existing pin definitions into the canonical `config.h` (or `#include` that file from `config.h`). The pin numbers (14/15 relay, 16/17/22/24 jack-detect) are already correct — do not invent new ones. Separately: if unrelated errors trace to Phase-B monitor-mode scaffolding (`signalRouter_setMonitorMode()`), isolate/stub that call site rather than implementing Phase B monitor modes just to silence the error — it's explicitly marked "NOT YET IMPLEMENTED — reserved for Phase B (v0.6.1)" in `signal_router.h`.
**Proof:** `guitar_rig_analyzer.ino` compiles clean for the Teensy 4.1 target with the Phase 2 smoke-test block intact.
**Evidence required before this moves off 🔴 (set 2026-08-25):** the compile result itself. If it fails, log the first meaningful compiler error verbatim and stop there — do not infer anything about TODO-2 beyond that point. Code presence (an edited `config.h`) is not evidence; a real build attempt is.

### TODO-2 — Phase 2: GPIO smoke test (relay pins 14/15) 🟡 hardware-verified (LED behavior PASS), Serial evidence incomplete — test block since removed, see journal.md
**Why:** Already drafted directly in the `.ino`, now compiles and has been run on hardware — see journal.md 2026-09-01 (1).
**What:** Run per `docs/breadboard_bringup_v3.md` § Phase 2.
**Proof (runbook sign-off criterion):** pins 14/15 toggle 0↔3.3 V, LEDs alternate for ~5 s, both outputs return LOW at the end. Sign-off checklist line: "LED smoke test toggles cleanly at boot."
**Evidence required before this moves off 🔴 (set 2026-08-25):** exactly four things, logged in journal.md when they exist — (1) TODO-1's compile result, (2) the exact Phase 2 serial output, (3) the observed LED behavior on pins 14/15, (4) whether that behavior meets the runbook's pass criterion above. Nothing short of that (a code diff, a "should work" assessment) advances this item's status.

### TODO-3 — Phase 3: Jack-detect, simulated with wire jumpers (pins 16/17/22/24) 🟡 [bench] electrical half PASS, router-event half deferred — see journal.md 2026-09-01 (3)
**Why:** Proves the four jack-detect GPIOs and the debounce logic before any real jacks are installed.
**What:** Ground pins 16, 17, 22, 24 individually per the runbook; TS/XLR return changes should also exercise the route-change path.
**Proof — the runbook's end-of-phase table is four rows, and only two are met.** Do not read this item as a full Phase 3 pass:

| Runbook check | Status | Evidence |
|---|---|---|
| Each of pins 16/17/22/24 emits `JACK_CHANGED` on GND tap | 🔴 **deferred** | router never in live path |
| Pin 22 (TS) or 24 (XLR) also emits `ROUTE_CHANGED` | 🔴 **deferred** | same |
| DMM idle shows ~3.3 V (INPUT_PULLUP active) | 🟢 met | pin 16 = **3.293 V** |
| DMM tapped to GND shows < 0.1 V | 🟢 met | pin 16 = **0.0–0.1 V** |

Additionally observed (standalone test firmware, since removed): pins 16, 17, 22, 24 all showed clean LOW-on-tap / HIGH-on-release transitions — GPIO + `JACK_DEBOUNCE_MS` debounce proven at the electrical layer.
**Why the two event rows can't be ticked:** the temporary test block polled the pins with `digitalRead()` directly. It never called `signalRouter_init()` / `signalRouter_update()`, which are what emit `JACK_CHANGED` / `ROUTE_CHANGED`, and those have never been integrated into the active tree's live path (deliberate scope call — journal.md 2026-09-01 (1)). Note the runbook's Phase 3 Step 1 claims "No code changes for this phase — `signalRouter_init()` already configures these pins"; **that premise is false for the active tree.** Same mismatch is waiting in Phases 5, 7, and 8 — check each against the active tree before running it.
**To close the deferred half:** it is the same work as TODO-11 (router promotion), not a separate task. Does **not** block Phase 4 (analog signal path, doesn't touch jack-detect events), but **must** be closed before TODO-10 breadboard sign-off — do not tick the "All four GPIOs respond to GND taps" sign-off line on today's evidence.

### TODO-4 — Phase 4: OPA1642 SOURCE buffer 🟢 **SOURCE_NODE CRITERION MET 2026-09-07 — signal present, digitally clean, and at the predicted level.** Still under a documented temporary bring-up config — see journal.md 2026-09-05 (3)
**✅ PASS EVIDENCE 2026-09-07 — journal.md 2026-09-07 (7).** With 0.143 V<sub>rms</sub> at the LINE IN L pad, `SGTL5000_LINE_IN_LEVEL = 5` predicts **−10.3 dBFS**; five consecutive diagnostic windows measured **−9.1 / −9.2 / −8.9 / −8.9 / −9.0 dBFS** — agreement to **1.3 dB**, inside DMM AC accuracy at 1 kHz plus the PGA's ~1.5 dB step. Every `[RAWDUMP]` window coherent, zero corrupted samples, zero clip events, `AudioMemoryUsageMax` pinned at 20.
**The earlier −39 dBFS deficit had two independent causes, both now closed:** the flying-lead I²S interconnect (journal 2026-09-07 (6)) and the 3.5 mm cable being plugged into the Audio Shield's **headphone output jack** instead of LINE IN L (journal 2026-09-07 (7)). **The −39.1 dBFS figure is retired — do not use it as a baseline.**
**⚠️ Level is above the operating limit set below.** −9.0 dBFS is fine for proving signal flow, but the trustworthy-capture target derived from the measured linear point is **≤ 0.23 V<sub>rms</sub>, preferably ~0.15 V<sub>rms</sub>** at the buffer input — re-check that the 0.143 V<sub>rms</sub> now at LINE IN L corresponds to a buffer input inside that window before taking any quantitative capture.
**Still open under this item:** TODO-23 (input impedance), TODO-19 (C1 corner), and TODO-21's architecture decision. None of them are contradicted by this pass.
**Gate status:** cleared via the decision gate's explicit exception for "a documented temporary bring-up configuration." **TODO-21's architecture decision remains open and is not affected by this.** Do not let the stopgap become the PCB design.
**🔧 The rebias — BUILD THIS.** (Supersedes an earlier 1.34 V figure in this item, which rested on a wrong output-swing number — see journal.md 2026-09-05 (4).)
Verified from TI's datasheet: output swings to within **0.2 V** (R<sub>L</sub>=10 kΩ) / **0.35 V** (2 kΩ) of the rails; V<sub>CM</sub> = (V−)−0.1 to (V+)−3.5. Usable follower window at 5 V = **0.35 – 1.50 V**, centre ≈ 0.925 V.
1. **Build a separate `OPA_BIAS` node:** 47 kΩ (+5 V → node) + 10 kΩ (node → GND) ⇒ **0.877 V**, R<sub>th</sub> = 8.25 kΩ, 88 µA. *(Round alternative: 4× 10 kΩ + 1× 10 kΩ ⇒ 1.000 V — ~1 dB worse, three more parts.)*
2. **Decouple it:** 10 µF electrolytic (+ to OPA_BIAS, − to GND) + 0.1 µF ceramic, mirroring Phase 1 Steps 8–9.
3. **100 kΩ from OPA_BIAS → pin 3** — the existing bias resistor, just moved off VGND.
4. **100 kΩ from OPA_BIAS → pin 5**, replacing Step 10a's jumper to VGND. Pin 5 has the **same CM violation**; an out-of-range channel B isn't reliably terminated and can oscillate into channel A through the shared supply — the exact failure that termination exists to prevent.
5. **Leave VGND untouched** — stays 2.5 V for everything else.
**Why biased from a decoupled node rather than a divider at pin 3:** keeps input impedance at exactly 100 kΩ (set by the series resistor), so **the C1 corner does not move** and TODO-19 is unchanged in kind; keeps TODO-23's 1 MΩ swap a single-part change; and stops +5 V rail noise entering the signal path through an undecoupled divider. JFET inputs draw picoamps, so those 100 kΩ resistors drop no DC.
**Headroom at 0.877 V:** ±0.53 V peak worst-case (2 kΩ), ±0.62 V at the real light load ⇒ ~1.1–1.2 V<sub>pp</sub>. Comfortably demo-valid. **Still characterise it** — drive a controlled signal and find the actual clipping point rather than assuming the datasheet boundary is the installed-circuit limit.
**Stock:** 1 kΩ ×60 · 10 kΩ ×60 · 47 kΩ ×40 · 100 kΩ ×50 · 10 µF ×10 · 0.1 µF ×20. **Nothing to order.**
**✅ BUILT AND VALIDATED AT SMALL SIGNAL 2026-09-05** — see journal.md 2026-09-05 (5). OPA_BIAS = 0.874 V (designed 0.877). Pin 3 = 0.868 V, pin 1 = 0.875 V, pin 5 = 0.876 V. **Droop on pin 3 fell from 327 mV to 6 mV — a 54× reduction, and definitive proof the common-mode defect is fixed.** TODO-21's ≤30 mV proof criterion is met (9 mV).
**✅ HEADROOM CHARACTERISED 2026-09-05** — see journal.md 2026-09-05 (6). 1 kHz sweep at 0.874 V bias:

| In V<sub>rms</sub> | Out V<sub>rms</sub> | Gain | Verdict |
|---|---|---|---|
| 0.460 | 0.453 | 0.9848 | linear |
| 0.648 | 0.613 | 0.9460 | compressing |
| 0.686 | 0.639 | 0.9315 | clearly compressing |
| 0.460 *(repeat)* | 0.453 | 0.9848 | **linear — repeatable** |

**Result, at the precision actually measured:** *onset of measurable compression occurs **somewhere above 0.460 V<sub>rms</sub> and by 0.686 V<sub>rms</sub>**.* Write it as that bracket. Any single figure inside it (earlier drafts said "≈0.5 V<sub>rms</sub>") is an interpolation across a 49% gap, not a measurement. The bracket sits entirely above entry-(4)'s predicted 0.4–0.45, so the installed circuit beats the datasheet-derived worst case — real load far lighter than the 2 kΩ swing spec assumes, and the CM range is a guaranteed minimum.
**Bonus finding — the 1.5% loss at 0.460 V is the coupling cap, not the op-amp.** C1 = 10 nF into 100 kΩ ⇒ f<sub>c</sub> = 159.2 Hz, predicted 1 kHz response 0.9867; measured 0.9848, inside meter accuracy. **The buffer's own gain is unity to within measurement error.**
**But this does NOT validate the 159 Hz corner** — only shows the reading is *consistent with* it. At 1 kHz the high-pass is a mere −0.116 dB down, so with ±0.5% meter accuracy the result fits any corner from ~125 to ~205 Hz (±25%). Probing a high-pass 6× above its corner is nearly the least informative place to measure it.
**Two caveats, so this isn't over-claimed:** (1) two safe readings at ~0.55 and ~0.62 V would close the 49% gap and pin the knee — 5 minutes for materially better evidence. (2) By the standard **P1dB** criterion the knee has *not* been reached — the worst point is only 0.49 dB down — so this is an onset-of-compression figure (~0.5 dB) and must be labelled as such, never called the 1 dB point.
**Do not drive higher.** At 0.686 V<sub>rms</sub> the negative peak is −0.096 V, essentially at the −0.1 V CM floor; beyond that the input protection conducts and the input stops being high-impedance. Graceful (the OPA164x suppresses phase reversal) but nothing to learn up there.
**⚠️ Operating limit for trustworthy captures — anchored to the measured point, not the interpolated knee:** THD rises well before gain visibly compresses. Reference **0.460 V<sub>rms</sub>, the highest level actually measured as linear**, and work down: target **≤ 0.23 V<sub>rms</sub> (−6 dB)**, preferably **~0.15 V<sub>rms</sub> (−10 dB)**. Deriving it from the measured point keeps it valid wherever the knee actually falls in the bracket. 0.460 V proves signal flow; it is not where quantitative captures should be taken.
**Audio Shield wired 2026-09-05** — LINE-IN-L + shield ground soldered. Power verified with shield attached: +5 V→GND 13.99 kΩ, 3.3 V→GND 8.06 kΩ (no shorts); rails 3.3 V and 4.99 V. ✅
**🚨 The SOURCE_NODE test CANNOT PASS yet — two firmware blockers, neither analog. See TODO-24 and journal.md 2026-09-05 (7).** Both would present as "no signal at SOURCE_NODE," the same symptom that already cost this project two days once.
**✅ Display init made non-fatal 2026-09-05** — [guitar_rig_analyzer.ino:197](guitar_rig_analyzer.ino#L197) now logs `[Main] WARNING: Display init failed. Continuing without display.` and continues instead of halting in a blink loop. Compile-verified clean (FLASH 157508 / RAM1 218720). **Not yet uploaded — the Teensy was disconnected when the upload was attempted.**
**⚠️ Watch for a runtime hang at the next line.** `display_engine.cpp` has **no `s_initialised` guard**, so every `displayEngine_*` call still executes against an absent RA8875 — starting with `displayEngine_drawStatusMessage("Initialising audio...")` immediately after. Register writes into the void are harmless, but the Adafruit library's `waitPoll()` spins on a status register, and with no device on the bus MISO floats: read as 0x00 it returns instantly, read as 0xFF it can **loop forever**. If the boot output stops right after the WARNING line, that is the cause, and the fix is an `s_display_ok` guard in `display_engine.cpp` — deliberately not added yet, since the change was scoped to the failure behaviour only.
**Serial capture is live:** `serial-mcp` holds `/dev/cu.usbmodem195969201` open at 115200, so its RX ring retains the boot banner whenever the board is reset — press reset and the full `[Main]` output can be read back rather than transcribed by eye.
**Proof for this config:** measured clipping points recorded, and the intended demo signal level shown to sit inside them with margin — not merely "the spectrum moves."
**Why:** First real analog signal path (unity-gain JFET buffer) on the breadboard.
**What:** Build per `docs/breadboard_bringup_v3.md` § Phase 4. **Step 1 is: unplug USB.** Place the OPA1642 exactly as the runbook specifies — do not improvise placement or substitute the part.
**Build progress:** Steps 9, 10a, 10b, 11 complete. Cap polarity verified correct (+ on `35e` at ~2.5 V VGND, − on `48e`). Steps 12–13 status **unrecorded — re-verify before proceeding.** Cable note: white = tip conductor.
**🚨 BLOCKER — +5 V rail reads 0 V *with USB connected* (expected 4.85–5.10 V). REAL FAULT, NOT SOLVED.**
Already ruled out, do not re-run: no short (+5 V→GND continuity = no beep); wire to the probed pin intact ("5V/VIN"→top-red rail = beep); **board alive and USB power present** — the Teensy enumerated this session as `VID:16C0 PID:0483 serial 19596920` on `/dev/cu.usbmodem195969201` and `arduino-cli` saw a Teensy 4.1 at `usb:130000`, which is impossible without VBUS and a working 3.3 V regulator. So 5 V reaches the board and is not reaching the rail.
**🟢 SUPERSEDED 2026-09-05 — root cause found, and it is a design defect, not a hardware fault. See journal.md 2026-09-05 (1) and TODO-21/22/23.** The OPA1642 is biased at 2.5 V midsupply on a 5 V single rail, but TI specifies V<sub>CM</sub> = (V−) − 0.1 V to (V+) − 3.5 V — a ceiling of **1.5 V** at this supply, with the datasheet explicitly stating midsupply is excluded below ±3.5 V. Verified against TI's datasheet directly. Evidence: pin 3 reads 2.480 V with the chip out and **2.153 V** with it in; pin 3→pin 4 measures **159 kΩ (not a short)**; rail is healthy at **4.99 V**. **The chip is NOT damaged — do not flip, replace, or re-seat it.** The reverse-powered hypothesis below is rejected.
**✅ The 0 V rail was NOT a fault — USB simply wasn't plugged in (closed, TODO-22).** Caused by the runbook's missing "reconnect USB" step (TODO-18). The common-mode defect above is independent of it and stands on its own measurements.
**⛔ Everything below is superseded and VOID — do not action.** Its premise ("0 V measured with power connected") was mistaken, so the regression framing, the reverse-powered-OPA1642 hypothesis, and the lost-enumeration escalation are all void. Retained only as the record of the detour:
**This is a REGRESSION and the suspect window is one phase wide.** Phase 1 passed — the rail worked (unrecorded only because this journal postdates Phase 1). Last confirmed powered-and-healthy state is **Phase 3**, evidenced by the 3.293 V pull-up reading on pin 16, which is impossible on an unpowered board. Phase 4 then unplugs USB and is pure construction. **Everything suspect lies in the Phase 4 OPA1642 build. Do not re-investigate Phases 1–3.**
**⚠️ Escalation flag — the Teensy no longer enumerates.** Checked 2026-09-03 11:14 PDT: `ls /dev/cu.usbmodem*` no matches, `arduino-cli board list` no Teensy. On 2026-09-01 both saw it (`serial 19596920`, `usb:130000`). **Ambiguous until the cable state is known** — Phase 4 says USB unplugged. But if USB *is* connected and it still doesn't enumerate, VBUS has collapsed or the board isn't running, which points at overcurrent from the breadboard.
**Leading hypothesis — the OPA1642 is reverse-powered** (rotated 180°, or offset a row/column). Fits every symptom simultaneously: crushes the rail to ~0 V; conducts through the substrate at tens-to-hundreds of ohms so continuity **doesn't beep**; and the excess draw can trip USB current limit, explaining the lost enumeration. Placement is easy to get wrong — pins 1–4 run *down* the `e` row (`35e`→`38e`), pins 5–8 run *back up* the `f` row (`38f`→`35f`), so **pin 8 (V+) = `35f`, pin 4 (V−) = `38e`**; a 180° rotation swaps them exactly.
**Next tests, in order, stop when one explains it:** (1) confirm whether USB is plugged in, then re-run `arduino-cli board list`; (2) **pull the OPA1642 out, power up, measure the rail** — returns to ~5 V ⇒ chip or its wiring is the fault, everything upstream exonerated (highest-information single test, do it first); (3) rail still dead with chip out ⇒ measure top-red↔top-blue in **ohms, not continuity**, and feel both 10 µF electrolytics for warmth; (4) rail fine with chip out ⇒ re-seat with notch **left**, straddling the gap at columns 35–38, no row offset, then check for heat on power-up; (5) separately probe the **VUSB pad** to confirm earlier readings were even on the right net.
**Demoted hypothesis (was leading):** supply wire on VIN rather than the documented VUSB pad — the runbook specifies `VUSB` (line 561) and never mentions VIN, while the debugging session tested "5V/VIN." **Cannot be the root cause of a regression** — that wire hasn't moved and worked at Phases 1 and 3. Still worth settling as a possible *measurement* error on the wrong net.
**Proof:** Sign-off checklist line: "Phone test signal visible on SOURCE spectrum." Note: Test 1's pass band starts at 200 Hz — extra rolloff below ~300 Hz at this phase is the 10 nF AC-coupling cap, not a fault (runbook heads-up).
**Not blocked by TODO-3's deferred half:** this phase is analog signal path only and does not depend on jack-detect events or the router being live.

### TODO-21 — Correct Phase 4's invalid op-amp operating point (design defect) 🔴 **blocks Phases 4–9** — decide direction, then fix the runbook
**Why:** Phase 4 biases the OPA1642's pin 3 to VGND ≈ 2.5 V on a single +5 V rail. TI specifies V<sub>CM</sub> = (V−) − 0.1 V to (V+) − 3.5 V ⇒ a **1.5 V ceiling** here, and states outright that midsupply is excluded for V<sub>S</sub> < ±3.5 V. 5 V is a legal *supply* for the part, which is what makes this easy to miss — the supply is valid, the bias point at that supply is not. Measured proof: pin 3 = 2.480 V chip-out, **2.153 V** chip-in. Full analysis in journal.md 2026-09-05 (1).
**Blast radius:** only Phase 4 instantiates a buffer — Phase 7 branches the *same* output at `48e` rather than adding a second op-amp. So one fix corrects everything, but **Phases 5–9 are not verifiable until it lands**, since they all sit downstream of SOURCE_NODE.
**🛑 DECISION GATE — before any bench changes.** Determine whether the production analyzer is required to operate from the existing 5 V USB-derived analog rail. **Do not modify Phase 4 hardware until that requirement is settled.** The selected solution must be the intended PCB architecture, except for an explicitly documented temporary bring-up configuration.
**Bench safety state until then: breadboard unpowered, OPA1642 removed.**

**Why the gate exists:** the pull toward Option 3 to "keep moving" would create a second electrical configuration that can silently diverge from the eventual PCB. Two configurations means two sets of bench results, and the breadboard stops being evidence for the product.

**What — the next engineering task is NOT breadboarding.** It is a short component/architecture comparison, decided once, with `docs/breadboard_bringup_v3.md` updated before Phase 4 resumes:

> **OPA1642 + higher analog rail  vs.  best-qualified 5 V rail-to-rail-input replacement.**

Compare each candidate on, at minimum: **input common-mode range at 5 V · output swing at the required load · input bias current · voltage noise · current noise · THD+N · GBW · unity-gain stability · supply current · package compatibility · availability and cost.** Add two that are specific to this design: **current noise × source impedance** (see below) and **behaviour with the ~1 MΩ input impedance that TODO-23 will require**.

**The three directions, stated neutrally — no recommendation, pending the gate:**
1. **Raise the analog supply** (V+ ≥ 6.0 V min, realistically 9 V; re-centre VGND to ~4.5 V for symmetric swing). Keeps the OPA1642 and the Phase 0.5 soldering. **Full cost is system-level, not just the op-amp:** boost/regulator circuitry, converter switching noise injected near an audio front end, analog grounding strategy, power sequencing, protection between analog and 3.3/5 V domains, PCB area, BOM.
2. **Swap to a rail-to-rail-input op-amp** (CMOS/JFET input required for low bias current). Keeps the single 5 V USB rail and the simpler power architecture. Candidates to qualify against datasheets, **not adopt blind:** TLV9062, OPA2320, MCP6022. Cost: new parts, OPA1642 stock and soldered adapters wasted, and typically worse THD+N.
3. **Stopgap:** bias pin 3 to ~1.0 V instead of 2.5 V. Zero new parts, but leaves only ~0.4 V of downward output headroom and shifts the input RC corner (TODO-19). **Gated — only as an explicitly documented temporary bring-up configuration, never as the product answer.**

**⚠️ Noise arithmetic that materially weakens Option 1's main argument — verify before relying on it.** The case for keeping the OPA1642 rests largely on its voltage noise (~5 nV/√Hz). But at this stage's source impedance, the *source's own Johnson noise dominates by more than an order of magnitude*: a 1 MΩ bias resistor (TODO-23) in parallel with a 6–250 kΩ pickup gives an effective noise resistance in the tens-to-low-hundreds of kΩ, and √(4kTR) at 200 kΩ is already **≈ 57 nV/√Hz** — roughly 10× the op-amp's contribution. **The difference between a 5 nV/√Hz OPA1642 and a 10–15 nV/√Hz CMOS RRI part is therefore largely invisible in this application.** What still genuinely differentiates them is **THD+N** (matters for a measurement instrument) and **current noise**, which must stay low because it is multiplied by that same large source impedance — so any candidate must be CMOS or JFET input; **a bipolar-input part is disqualified outright at these impedances.** This should be checked with real numbers during the comparison, but if it holds, the noise argument for the added rail largely evaporates and Option 2 becomes the stronger system answer.
**Recommendation: withdrawn, deliberately.** An earlier draft of this item recommended Option 1. That call weighted the op-amp datasheet in isolation and did not price the system consequences of a second analog rail. **This is an architecture decision gated on the product requirement above, not a component preference.**
**Proof:** pin 3 measures within 30 mV of its intended bias with the op-amp installed, and `docs/breadboard_bringup_v3.md` § Phase 4 is edited so the runbook no longer specifies an out-of-spec circuit.

### TODO-22 — 0 V rail 🟢 **CLOSED 2026-09-05 — no fault. USB was not plugged in.**
**Resolution:** confirmed by Conley — the board was unpowered. A 0 V reading on an unpowered rail is correct behaviour, not a fault. There was no intermittent, no regression, no damage, and nothing to fix. The Teensy's failure to enumerate on 2026-09-03 has the same cause.
**Root cause of the two-day detour:** the runbook gap in **TODO-18** — Phase 4 says "Unplug USB" and never says to reconnect before demanding live DMM readings. This was correctly identified on 2026-09-03, then wrongly withdrawn on a mistaken report that the 0 V had been measured with power connected. Reinstated.
**Kept from this item, demoted to housekeeping:** the runbook specifies the **`VUSB` pad** (Phase 1 Step 2, line 561) and never mentions VIN in 1860 lines, while the debugging session probed "5V/VIN." A real documentation inconsistency worth settling for clarity — but **not implicated in any fault.** See journal.md 2026-09-05 (1).

### TODO-42 — Decouple the internal generator from the RETURN measurement path 🔴 **measurement-architecture defect — a generated tone appears directly in RETURN_NODE**
**The defect.** `signal_generator.cpp:99` wires `s_conn_gen_mon(s_gen_mixer, 0, s_mixer_ret, 2)` — the generator is summed into **slot 2 of `s_mixer_ret`**. That same mixer feeds the RETURN analysis taps: `s_fft_ret`, `s_peak_ret` and `s_queue_ret` ([audio_capture.cpp:149–151](audio_capture.cpp#L149)). **So an internally generated test tone appears directly in RETURN_NODE and can be mistaken for returned DUT signal, crosstalk, or measurement response.**
**Why it matters now:** RETURN has been the control channel for the entire SOURCE-floor investigation — the reference that distinguishes a channel-specific effect from a system-wide one. Any future validation that starts the generator silently destroys that control, **and the contamination looks like a plausible signal rather than an obvious fault**, which is the dangerous kind.
**Requirement:** generator output to the physical DUT/send path must not contaminate the SOURCE_NODE or RETURN_NODE measurement taps. The monitor tap is a legitimate feature — it needs its own path to the DAC that does not pass through an analysis mixer.
**Also missing, and needed for any generator-based test:** there is **no way to start the generator.** `signalGen_init()` is called at boot ([guitar_rig_analyzer.ino:280](guitar_rig_analyzer.ino#L280)) and nothing calls `signalGen_configure()` / `signalGen_startAtBlock()` afterwards. The serial handler accepts `v 1 2 3 4 r u t T` and none of them touch the generator. Add explicit generator control as part of this item.
**Note on the current output path, verified from the tree:** the tone reaches **LINE OUT / headphone RIGHT**, not left — `s_mixer_ret` → `s_i2s_out` channel **1** ([audio_capture.cpp:156](audio_capture.cpp#L156)). Anyone wiring a loopback to LINE OUT L would get silence and likely misdiagnose it.
**Clarification on "stubbed":** the boot banner's *"Audio output injection is stubbed"* is narrower than it reads. **Sine generation itself works** — `AudioSynthWaveformSine s_sine_osc` is a real DDS oscillator. What is stubbed is DUT injection to a physical RIG SEND jack (awaiting `signal_router`), pink-noise 1/f shaping, and `signalGen_startNow()`.
**Evidence required to close:** with the generator enabled and **no physical RETURN connection**, RETURN_NODE remains at its established idle floor (currently ≈−65.5 dBFS post-stack); and the physical generator output is independently verified at the DAC pad with a scope or DMM.
**Blocks:** any generator-based validation, including a Teensy-sourced loopback for TODO-41B. **This is why 41B uses an external phone/computer source into the real 1/4" jack instead.**

### TODO-41A — Post-stack idle baseline 🟢 **PASS 2026-09-13 — asymmetry collapsed 29.4 dB → 0.13 dB**
**Hardware:** new Teensy 4.1 + new Rev D shield, native stack (shield → Teensy → breakout), flashed `c18fac7` (first upload since `e6daac8`). Pre-power 3V3→GND check clean. LINE-IN-L deliberately left disconnected to isolate the stack.
**Result — 8 consecutive windows:** SOURCE mean **−65.39 dBFS**, RETURN mean **−65.26 dBFS**, **Δ 0.13 dB**. No impulses, outliers or clip events. Raw ±15–16 counts on both channels; −65.4 dBFS ⇒ 17.6 counts, so peak metric and raw data agree.
**RETURN improved ≈6 dB** — it sat near −59 dBFS through every flying-wire condition and nothing in that investigation moved it. Both inputs getting quieter together is a topology signature, not a per-channel fix.
**⚠️ This is the post-stack SYSTEM idle floor, NOT the SGTL5000's intrinsic floor.** The codec has not been isolated; do not cite it as a codec noise figure.
**🚨 CONFOUND, recorded so it is not lost:** both boards are new, so this run changed topology **and** hardware simultaneously. The pin-8 contention-damage hypothesis for the *old* Teensy (journal 2026-09-07 (4)) was weakened but never disproved, and new silicon eliminates any such damage. **"The stack fixed it" and "the old hardware was degraded" are not separated by this measurement.** The configuration works, which is what matters for proceeding; the causal claim stays conditional. Only a flying-wire re-creation on the new boards would separate them, and that is not worth the disturbance.
**Also first-on-hardware in this run, recorded separately:** Pi link measured at **max 283 µs call time, 1077 frames, 0 dropped**, TX room min 2482/4096 B, block period unchanged at 46.3 ms — against T1's ~33.8 ms blocking prediction. First hardware evidence for `c64e876`; **does not close T1**, which needs the controlled `timing_probe` comparison against the `_NONE` control. And `TF clamped bins: 0 of 512` — TODO-29 running on hardware for the first time. New normal loop rate ~1.50 M/s (was ~2.15 M) — the Pi link work, not a regression.

### TODO-41B — Post-stack stimulated I²S validation 🟢 **PASS 2026-09-13 — 324/324 clean windows, zero outliers**
**Conclusion, stated narrowly:** under the new native Teensy 4.1 + PJRC Audio Shield Rev D stacked configuration, with a continuous external ~1 kHz stimulus applied through the real instrument-input analog path, **324 diagnostic windows spanning 26.9 minutes contained zero outliers on either SOURCE_NODE or RETURN_NODE under Outlier detector v1.** All 324 windows clean, zero clipping events, no quarter-to-quarter emergence of corruption. **This establishes the post-stack stimulated reference for I²S integrity under the tested conditions.**
**🚫 NOT concluded: "the stack fixed the corruption" or "the old Teensy was damaged."** Hardware and topology changed together (TODO-41A confound). Established is stronger than a hypothesis, narrower than causality: **the current assembled system does not reproduce the corruption under this test.**
**Stimulus (recorded WITH the result):** phone → USB-C adapter → real 1/4" jack, 1 kHz L+R, **0.141 V<sub>rms</sub> at `48e`** (0.140 avg / 0.143 max, 995–997 Hz, clean sine). SOURCE **−29.88 dBFS mean**, raw |max| 1179 counts.
**🔻 CORRECTION 2026-09-13 — the 0.141 V<sub>rms</sub> figure is INVALID as an absolute voltage.** It was a scope reading taken with a 1× probe on a 10×-configured channel, so it is ~10× high. Reconstructed true value **≈0.014–0.016 V<sub>rms</sub>**, explicitly *reconstructed* — no matched-setting measurement at `48e` exists. See journal 2026-09-13 (6) and TODO-43.
**The 41B PASS is unaffected**: its claim is about I²S corruption and was established from ADC data (324/324 clean, zero detector-v1 outliers) with SOURCE at −29.88 dBFS against a −55 dBFS post-stack idle floor. Absolute volts never entered the claim.
**Consequence that must not be lost:** 41B intended to reproduce 2026-09-07 (7)'s 0.143 V<sub>rms</sub> (a valid DMM measurement). Setting the phone to a 10×-inflated display put the true level ~20 dB lower, so **41B ran ~20 dB below its designed stimulus level** — planned margin ≈51 dB above the floor, achieved ≈25 dB. Ample, and the PASS holds, but **41B cannot be cited as having covered level-dependent corruption.**
**Numbers:** 9 720 samples evaluated per node (10 368 captured; 2/window have no 2nd difference) · worst window 0 of 30 evaluable on both nodes · quarterly bands all 0.000/win, n=81 each · block period 46.43 ms mean · `AudioMemoryUsageMax` pinned at 19 · `TF clamped bins` constant at 3/512.
**Control channel:** RETURN averaged **−66.22 dBFS**. No evidence of a stimulus-correlated RETURN rise; RETURN remained at approximately the established post-stack idle-floor region. **Any crosstalk is below what this measurement can resolve from the RETURN noise floor.**

```
Outlier detector v1
For each 32-sample window, evaluate interior samples i=1..30 using
d2[i] = x[i-1] - 2x[i] + x[i+1].
Let m = median(|d2|) over those 30 values; if m=0, use m=1.
Flag sample i only when |d2[i]| > 10m and |d2[i]| > 100 counts.
Report 30 evaluated samples/window and 32 captured samples/window separately.
```
Both comparisons strictly greater-than, not ≥. `m` is the median of the 30 interior second-difference magnitudes of **that same window**.
**Evidence committed:** `ai/evidence/2026-09-13-41B-stimulated-validation.md` · raw log `ai/evidence/2026-09-13-41B-capture.log.gz` · analyser `tools/analyze_corruption.py`. **Reproduce:** `gunzip -c ai/evidence/2026-09-13-41B-capture.log.gz > /tmp/41B.log && python3 tools/analyze_corruption.py /tmp/41B.log`
**Run D retired as a quantitative benchmark** — historical evidence that corruption existed and motivated the DOUT reworks, but it recorded neither stimulus level nor outlier criterion, so its numbers cannot be recomputed.
**🟢 RESOLVED 2026-09-13 (was open separately; never downgraded this PASS):** the **19.4 dB** amplitude discrepancy — 0.141 V<sub>rms</sub> at `48e` → −29.88 dBFS against −10.5 dBFS predicted from `SGTL5000_LINE_IN_LEVEL = 5`. Tracked as TODO-43.
**Remaining deviations to restore, one at a time with re-measurement after each:** LINE-IN-L ground jumper, J2 if wanted, `col 30` → GND jumper.

### TODO-47 — Identify the relay actually fitted: the contacts do not follow the coil 🟢 **RESOLVED 2026-09-16 — root cause was reversed coil polarity, not the part**
**✅ 2026-09-16:** the coil was reversed. **Evidence is the intervention:** rewiring +5 V to pin 1 (`55a`), with the relay left in place, made the contacts transfer and return (journal 2026-09-16 (2)). *(An earlier line here cited the pin-1 stripe at `55a` as `PHOTO`. The TQ's bar marks only the pin-1 end, not the row side, so that reading overclaimed; see journal 2026-09-16 (3).)* **Both relays are TQ2-5V:** the fitted spare by photo (ATQ209 · 60214TH) and the removed original by builder report. No latching part was involved.
**🔄 UPDATE 2026-09-16 — latching hypothesis FALSIFIED as the cause; leading hypothesis is now REVERSED COIL POLARITY.** A spare marked **TQ2-5V**, pins 5/6 **OL**, 183.5 Ω, with **4.69 V across the coil** (pickup ≤ 3.75 V) and collector 127.1 mV, shows the same energised pattern: `56`↔`57` closed, `57`↔`58` open, `56`↔`58` open. So the fault follows the placement/drive, not the part. **The TQ is a polarized relay.** Panasonic ASCTB14E p.10 (single side stable) puts **`+` on pin 1 and `−` on pin 10**. The runbook (step 7/9), and therefore the bench, puts +5 V on pin 10 (`55f`). Reverse drive reinforces the magnet's reset bias, so current flows and the contacts never transfer. Evidence: [`evidence/2026-09-16-tq-datasheet-coil-polarity.png`](evidence/2026-09-16-tq-datasheet-coil-polarity.png); journal 2026-09-16 (1).
- **Decisive check (USB unplugged):** which **row side** carries the pin-1 stripe, `55a` or `55f`? (The coil is proven on column 55, so "column 55 vs 59" cannot discriminate.) **`55a` ⇒ reversed, hypothesis confirmed. `55f` ⇒ polarity already correct, hypothesis dead.**
- **🔻 WRONG — do not follow.** A 180° in-plane rotation moves pin 1 to `59f` and the coil to column 59, and swaps NC/NO on the a–e side. The pin-to-`55f` mapping below is a mirror image, which a DIP cannot do. Caught by the bench chat; see journal 2026-09-16 (2). *(Original text:)* **Fix if confirmed:** rotate the relay 180° in-plane. Pin 1 → `55f` (+5 V), pin 10 → `55a` (collector). Pole 2 lands on a–e as NC `56a` / COM `57a` / NO `58a`: same function per hole, so **no rewiring and the diode stays**.
- **Proof:** after rotation, `p` energised gives `57a`↔`58a` **beep** and `56a`↔`57a` **open**; the second `p` reverses both.
- **Still worth doing:** record the **original** relay's marking before it goes back in a drawer, so a TQ2-L2-5V is not left mixed in with TQ2-5Vs.
- **Superseded:** the latching-specific text below is retained as history. Its A/B-trap warning is still sound in general.
**Why:** the coil energises (audible click, collector saturated at 125.6 mV) but the contact state is **identical energised and de-energised**, on both poles, verified with the relay out of the board. That is the behaviour of a **dual-coil latching relay driven on one coil**: it throws once on a pulse and then holds state with zero current, ignoring the GPIO thereafter.
**The bench already reported the signature and it was explained away.** *"The relay clicks every other `p` input"* was attributed to one direction being louder. It is not perceptual — a non-latching relay clicks on **every** state change; a latching relay driven on one coil clicks only when that coil is pulsed. **A raw bench observation was overruled by an assumption about how the part should behave.** Treat that as the reusable lesson.
**Documentary support:** runbook L1229 gates this phase on *"wait for the TQ2-5V to arrive — TQ2-L2-5V (latching) won't work with the current firmware"* (gate never checked); L149 lists TQ2-5V as **"to buy"** while L150 lists **10× TQ2-L2-5V on hand**; L19 contradicts L149 by claiming 5× TQ2-5V in stock.
**What — two decisive tests, either sufficient, USB unplugged:**
1. **Read the marking on the relay body** — `TQ2-5V` vs `TQ2-L2-5V`. Physical observation, top of this project's precedence order.
2. **Measure `59a` ↔ `59f` (pins 5 and 6).** The runbook calls these "mechanical only — no electrical connection", which is true for the TQ2 but **not** for the TQ2-L2, where they are the second coil. **OL ⇒ non-latching. A couple of hundred ohms ⇒ latching.** Take `55a`↔`55f` too — TQ2-5V coil is specified 178 Ω.
**If confirmed latching — do not improvise a fix at the bench.** `signal_router.cpp` drives each relay with one static `digitalWrite()`; a latching part needs a set coil *and* a reset coil, i.e. **two GPIOs per relay plus pulse-drive firmware** — a router architecture change touching Phase 7 and the pin budget. Options: (a) obtain genuine TQ2-5V parts and keep the firmware as designed, or (b) accept dual-coil latching and re-scope the router. **That is an ADR-level decision** (cf. ADR-002/003), and journal 2026-08-25 already recorded the reasoning — re-read it rather than re-deriving.
**Not concluded:** that the part is latching. The alternative is a non-latching part with mechanically stuck contacts. The marking settles it. **The driver stage is unaffected either way** — V1 through V6a stand, and the MMBT3904 stage is proven. The defect, if any, is the part, not the build.
**⚠️ COIL RESISTANCE DOES NOT IDENTIFY THE PART — do not treat it as confirmation.** A spare measured **183.5 Ω** across `55a`↔`55f` and was called "a healthy TQ2-5V" on that basis. The TQ2-5V's single coil is specified 178 Ω; the TQ2-L2's coils are in the same family and range, so **~180 Ω is consistent with either part.** The reading confirms an intact coil and says nothing about latching. Only the marking and the pins 5/6 reading discriminate.
**⚠️ THE A/B SWAP HAS A TRAP — read before interpreting it.** A spare relay has been seated for an A/B against the original. **That comparison is only informative if the two parts differ.** The drawer holds 10× TQ2-L2-5V and, per L149, possibly zero TQ2-5V — so "the spare TQ2-5V" may be a second TQ2-L2-5V. If both are latching they will behave identically, and the natural reading of that result — *"both relays do the same thing, so it isn't the relay"* — is **exactly wrong** and would send the investigation into the driver stage, which is already proven. **Identify both parts by marking before interpreting any A/B outcome.** Column 59 carries nothing (pins 5/6 are unjumpered), so `59a`↔`59f` can be measured on a seated relay with USB unplugged.
**Proof:** the fitted relay's part number is recorded from its own marking, with the `59a`↔`59f` reading alongside it, and TODO-6's contact criterion is restated against that part's real datasheet.

### TODO-45 — Runbook hard-codes `45a` as "a free column" in two phases; column 45 is VGND 🔴 **blocks TODO-6 from being followed as written**
**➕ 2026-09-17 — third stale-coordinate instance, still UNCORRECTED in the runbook:** Phase 7 step 1 says *"Build a mirror of phase 6 at columns 60–70"*. The board ends at **column 64** (`PHYS`), so that location cannot exist. The driver was instead built at **columns 8–18** (see TODO-7). **The runbook text has not been changed** — correct Phase 7 step 1 to the as-built site in the same pass that fixes Phase 4 step 6 and Phase 6 steps 3–4.
**Why:** `docs/breadboard_bringup_v3.md` calls `45a` a free column in **Phase 4 step 6** (L968–969: 100 kΩ `37a`→`45a`, plus a jumper `45a`→`BOT_RED`) and again in **Phase 6 step 3–4** (L1269–1271: 1 kΩ base resistor to `45a`, then **jumper `45a` → Teensy pin 14**). [`docs/asbuilt/netlist.md`](../docs/asbuilt/netlist.md) records col 45 A–E as **VGND** at `PHYS` — R3 in `45a`, R4 in `45b`, grey jumper `45c` to `BOT_RED`. The Phase 4 instance was dodged by accident when the TODO-21 common-mode redesign moved R5 to `37c`→`41d`. **The Phase 6 instance is live and hazardous** — it puts a 3.3 V push-pull GPIO on the reference rail. See journal 2026-09-15 (1) and TODO-6.
**What:** correct both runbook steps to the as-built reality — Phase 4 step 6 rewritten to describe the OPA_BIAS arrangement actually built, Phase 6 steps 3–4 retargeted to the relocated drive column (TODO-6 V3). Add col 45 = VGND to the runbook's own coordinate notes so a third phase does not claim it. This is the **seventh** documented runbook defect (netlist §5 D5 counts six).
**🔻 WITHDRAWN 2026-09-15 — "Phase 6 step 7's TQ2 contact table is wrong."** This item briefly recorded that `58a` is NC while the runbook calls it NO. **The deduction was unsound** — it assumed the energised sweep showed a transferred contact state, and the bare-relay test proved the contacts never transferred at all. Read correctly, `56`↔`57` closed is the *de-energised* pair and `58` = NO, which is what the runbook says. **No defect is established in the POLE 1 table.** See journal 2026-09-15 (5). *(The general caution still stands on its own merits after the MMBT3904 error: treat every pinout table here as unverified until measured — POLE 2 and the Phase 7 mirror included.)*
**Also fix while in there — Phase 6's parts gate was never enforced, and the document contradicts itself about whether the part exists.** L1229 says *"Wait for the TQ2-5V to arrive before doing this phase. TQ2-L2-5V (latching) won't work with the current firmware"* — Phase 6 was executed without that gate being checked. L149 lists TQ2-5V as **"to buy"**; L19 claims **"5× TQ2-5V (2 used + 3 spare)"** on hand. Both cannot be true, and v3's own changelog says v3 fixed "a stale parts-availability claim in Phase 1." **Make the gate a hard precondition with a part-marking check, and reconcile L19 against L149.** Related: the step 7 claim that pins 5 & 6 are "mechanical only — no electrical connection" is **part-specific** — on the TQ2-L2 those pins are the second coil. See TODO-47.
**Also fix while in there — Phase 6 step 7 inverts the TQ2 coil polarity (2026-09-16; eleventh defect, ✅ CONFIRMED at the bench — reversing the coil made the contacts transfer).** The table says pin 1 = COIL (−) and pin 10 = COIL (+), and step 9 wires pin 10 to +5 V. Panasonic ASCTB14E p.10, single side stable: **pin 1 = `+`, pin 10 = `−`**, and the TQ is polarized, so reverse drive does not operate. The runbook cites this very datasheet, so a citation is not verification. Correct steps 7–10: pin 1 → +5 V, pin 10 → collector, diode band on the pin-1 node. Keep pin 1 at `55a` and swap the wiring; **do not** "move pin 1 to `55f`", which is not physically possible without moving the coil to column 59. The contact rows 2/3/4 = NC/COM/NO are bench-proven correct. and fix the **Phase 7 mirror**, which inherits the error. See TODO-47.
**Also fix while in there — the Phase 6 verify table contradicts the Phase 6 code.** The end-of-phase table reads "Type `p` (energise)" / "Type `P` (de-energise)"; step 11's own snippet is `case 'p': case 'P':` wrapped around a `static bool` toggle, so **either character flips the state and pressing `p` twice de-energises.** Ninth documented runbook defect. Fix the table to describe a toggle, or change the snippet to make `P` an explicit de-energise — not both readings in one document.
**🟢 DONE 2026-09-16 (comment corrected with `[PHASE6-TEMP]` removal).** **Also fix while in there — [.ino:314](../guitar_rig_analyzer.ino#L314)'s premise has expired.** Its comment justifies `signalRouter_init()`'s relay-GPIO activity as "electrically inert" because "Phase 6 is not built." Phase 6 **is** now built on those pins. Correct that comment when `[PHASE6-TEMP]` is removed.
**Also fix while in there — Phase 6 step 2's transistor pin order is wrong, and the runbook contradicts itself on it.** Step 2 (L1263) instructs "orient the adapter so its silkscreen reads **E – B – C** left-to-right (E nearest column 49, C nearest column 51)"; Phase 0.5 (L504) says the adapter is marked "**C / B / E**". Both put the **Base** in the centre. An MMBT3904 in SOT-23 has **pin 1 = Base, pin 2 = Emitter, pin 3 = Collector** — the *emitter* is the centre pin — and the bench confirmed C=`49`, E=`50`, B=`51` (TODO-6 V2). Built as step 2 instructs, the emitter and base are swapped: the driver does not switch, and the base-emitter junction gets reverse-biased toward its ~6 V breakdown. **Correct step 2, correct step 6 (emitter jumper moves `49a`→`50a`), and reconcile L504.** Step 2's own "sanity-check each header pin back to the SOT-23 pad" is what saved this — keep that line and make it mandatory rather than parenthetical.
**Also fix while in there:** Phase 7 step 1 specifies "a mirror of phase 6 at **columns 60–70**." The netlist records the BB830 as **60 columns**; a standard BB830's 830 tie points implies **63**. The exact figure needs a bench count — but under *either*, a Phase 6 mirror (which spans 49→59, eleven columns) **cannot start at column 60 and fit.** Verify the real column count and re-site Phase 7.
**Proof:** a reader following v3's Phase 4 and Phase 6 literally, on this board, lands on free columns and never on col 45; and Phase 7's coordinates fall within the board's 60 columns.

### TODO-46 — Trace every as-built deviation forward into later phases 🔴
**✅ 2026-09-17 — forward-trace DONE for the Phase 7 RELAY_RETURN driver** (not for the later signal wiring). Its coordinates (cols 8–18) were checked against the occupied 30–64 region, the Phase 6 driver at 49–59, and D3's VGND at col 45: no overlap, and the only shared nodes are the two rails, both verified by continuity first. **The Phase 7 signal-path wiring still needs its own forward-trace** — it will reach into the occupied region, which the driver did not. **D3 was assessed benign in isolation and was not; assume the others were assessed the same way**
**Why:** netlist §5 deviation **D3** ("VGND divider is at col 45, not col 15… Pure relocation. Runbook Phase 1 coordinates are stale") is correct as far as it goes and **its assessment is still wrong**, because two later runbook phases hard-code the destination column. A relocation is only benign if nothing downstream claims the destination, and D3 never checked. That produced TODO-45 and halted TODO-6 mid-build with firmware already installed. **The same forward-trace is missing from D1, D2, D4, D5 and X-1…X-5.**
**What:** for each recorded deviation and hole-level divergence, grep the runbook for the coordinates and nodes it moved *away from* **and** *toward*, and record for each one whether any later phase depends on the old location or claims the new one. D5 is the priority case — it is already known to be jointly destructive with D3 (fitting the Phase 0 step 5 `TOP_RED`↔`BOT_RED` bridges makes `BOT_RED` +5 V, and any col-45→GPIO jumper then destroys a non-5V-tolerant Teensy pin).
**Broader defect this exposes:** the netlist's deviation table assesses each deviation **against design intent** and never **against the rest of the runbook**. "All benign, all recorded" is a claim about electrical correctness, not about document consistency — and the second one is what bites during construction. Consider a required "downstream coordinate claims" column in the table.
**Owner note:** `docs/asbuilt/netlist.md` belongs to the concurrent capture session — coordinate rather than editing it unilaterally.
**Proof:** every row of netlist §5 and §5a carries an explicit forward-trace result, and no runbook phase references a coordinate that a deviation has reassigned.

### TODO-44 — As-built jack entry records the signal tip only; sleeve and switch→pin16 are missing 🔴 **this omission is what let the Phase 5 detect step disappear**
**Why:** `docs/asbuilt/netlist.md` documents the 1/4" jack as `1/4" JACK tip ─ col30 ─ C1 ─ col33 ─ jmp ─ col37`. There is **no SLEEVE entry, no SWITCH entry, and Teensy pin 16 does not appear anywhere in the document.** The runbook requires three conductors (TIP, SLEEVE, SWITCH → pin 16); the as-built records one. Because the record showed only what was built and never showed what was *required*, an unbuilt Phase 5 step stayed invisible until firmware was written against it and produced a null result — see journal 2026-09-13 (7).
**🔻 REVISED 2026-09-13:** J4 was continuity-identified as a **two-terminal** jack — lug #1 = SLEEVE/GND, lug #2 + long spring = TIP, **no switch terminal**. So the as-built entry needs **TIP and SLEEVE**, plus an explicit statement that **the part has no switched contact** — which is exactly the kind of required-but-absent fact a present-connections-only record cannot express.
**What:** the as-built jack entry must carry the conductors that exist with their own evidence tags — TIP (lug #2 + long spring, one net) and SLEEVE (lug #1, bonded to the body) — and record the **absence** of a detect contact as a positive statement rather than an omission. Add the `SOURCE_IN` net's DC-path status explicitly too, since `col 30` having or lacking a DC reference is now known to be functionally significant.
**Broader defect this exposes:** an as-built document that records only present connections cannot distinguish *"built and correct"* from *"never built."* Consider whether required-but-absent connections deserve an explicit tag (e.g. `MISSING`) rather than silent omission.
**Owner note:** `docs/asbuilt/netlist.md` belongs to the concurrent capture session — coordinate rather than editing it unilaterally. See `ai/journal.md` provenance entries.
**Proof:** the as-built jack entry lists TIP, SLEEVE and SWITCH→pin 16 with evidence tags, and a reader can tell from the document alone whether the detect conductor exists.

### TODO-43 — 19.4 dB amplitude discrepancy between `48e` and the ADC 🟢 **CLOSED 2026-09-13 — measurement-scale error, not a hardware or codec fault**
**RESOLUTION — 1× probe on a 10×-configured scope channel.** Matched-setting measurement (physical probe 10×, DHO804 CH1 probe ratio 10×, 10 mV/div) at the SGTL5000-side pad of the LINE-IN-L coupling capacitor, shield-local GND: **16.3 mV<sub>rms</sub>** (16.3 avg, ~16.5 max, ~15.9 min, ~1.00 kHz, clean sine). 16.3 mV<sub>rms</sub> × 2√2 = 46.1 mV<sub>pp</sub>; 20·log₁₀(0.0461/1.33) = **−29.2 dBFS predicted vs −29.9…−30.4 observed — agreement 0.7–1.2 dB.** Journal **2026-09-13 (6)**.
**Positively ruled out:** ~19 dB codec conversion-gain anomaly; 10:1 loss through the shield input network; failed SGTL5000 configuration. The register dump (`d63a753`) and datasheet audit eliminated the codec so completely that the instrument was the only suspect left.
**Proof criterion met:** an independent predicted-vs-observed agreement (0.7–1.2 dB) reproducing the same quality of agreement the 2026-09-07 (7) DMM measurement achieved (1.3 dB) at a level ~19 dB higher.
**Superseded below — the original open-item text is preserved unchanged, per the never-delete rule.**

**Observation, and nothing more:** **0.141 V<sub>rms</sub> measured at `48e` produced −29.88 dBFS mean SOURCE** over the 324-window stimulated run on the current stacked system, against **−10.5 dBFS predicted** from `SGTL5000_LINE_IN_LEVEL = 5` (1.33 V<sub>pp</sub> full scale ⇒ 0.4702 V<sub>rms</sub>). **Discrepancy 19.4 dB.** No divider hypothesis, no codec-configuration hypothesis is attached — both were raised prematurely and withdrawn.
**Why this datum is good:** a 324-window mean on a stable stimulus, not a single-window reading. Prior single-window figure was 20.2 dB.
**Historical contrast worth keeping:** on the **old** board the same 0.143 V<sub>rms</sub> gave **−9.0 dBFS**, agreeing with the same arithmetic to 1.3 dB (journal 2026-09-07 (7)). The relationship held then and does not now.
**Next test — each measurement referenced to its OWN local ground** (the 2026-09-12 (3) lesson): measure `48e` → breadboard GND and record V<sub>rms</sub>; then move only the probe tip to the Audio Shield **LINE-IN-L pad** using the shield's **own GND pad** as reference, and record V<sub>rms</sub>.
- LINE-IN-L ≈ 0.014 V<sub>rms</sub> while `48e` ≈ 0.141 ⇒ a real ~10:1 loss in the physical path.
- LINE-IN-L still ≈ 0.141 V<sub>rms</sub> ⇒ the discrepancy is downstream of the pad — codec configuration, line-input gain interpretation, or digital-path scaling.
**Does not block anything measured so far.** 41B's corruption result is independent of absolute level.


**Why this is separate:** the instruction to run the 360/360 validation *while leaving LINE-IN-L disconnected* cannot be satisfied — run D (journal 2026-09-07 (6)) injected a 1 kHz tone **through** LINE-IN-L. The idle data is strong evidence against obvious corruption (both channels inside ±16 counts, no impulses, and a corrupted word would be unmissable against a floor that low — arguably more sensitive than run D, which had a full-scale tone to hide in) **but it is not the same test.** Run D's claim is about a *stimulated* pipeline over ≥300 windows.
**🚨 Run D's stimulus level was NEVER RECORDED — see journal 2026-09-13 (2).** Entry 2026-09-07 (6) documents outliers, clean %, worst window and `+0 dBFS %` but no level, V<sub>rms</sub> or amplitude. And run D predates the headphone-jack fix, so its stimulus went through the **wrong jack** at ≈0.027 V<sub>rms</sub> — reproducing it exactly would mean recreating a known-faulty path.
**What — use 0.143 V<sub>rms</sub> at LINE-IN-L instead** (documented, reproducible, previously gave **−9.0 dBFS** through the correct path, journal 2026-09-07 (7)). LINE-IN-L reconnected to `48e`, 1 kHz, then ≥300 windows counting outliers per 32 samples on both nodes. Margin is ≈51 dB against the −60.3 dBFS idle floor — **more than run D had.**
**Record the stimulus conditions WITH the result this time:** level, frequency, source, injection point. Run D's non-reproducibility is the reason.
**Proof:** mean SOURCE and RETURN outliers/32 at **0.00**, clean windows 100 %, zero clip events, compared directly against run D's table. Record the new baseline as the post-stack reference; **run D's numbers describe a topology that no longer exists.**
**Then, and only then:** restore the remaining deviations one at a time, re-measuring after each — remove the LINE-IN-L ground jumper, re-fit J2 if wanted, remove the `col 30` → GND jumper.
**Also update after this passes:** `docs/asbuilt/netlist.md` §4 and `tools/gen_schematic.py` still describe flying leads. Regenerate; do not hand-edit the SVGs.

### TODO-41 — superseded by TODO-41A / TODO-41B 🟢 **split 2026-09-13**
**Why:** stacking the Rev D shield onto the Teensy replaces the flying I²S *and ground* interconnect with the native header path. That is a structural change to the exact thing journal 2026-09-07 (6) identified as the root cause of the digital corruption, and to the ground return that journal 2026-09-12 (3) measured as worth **33.1 dB**. It is very likely an improvement on both counts — and it invalidates every baseline taken before it.
**What — in this order, with nothing else changed in between:**
1. **Re-run the I²S validation that produced 360/360 clean windows** (journal 2026-09-07 (6), run D: 0.00 outliers/32 on both nodes, 0 clip events, ≥300 windows). Pass = corruption stays at zero.
2. **Take a fresh SOURCE idle-floor baseline**, ≥5 windows, and record the RETURN floor alongside it.
3. **Only then** restore the four outstanding deviations (`48e` → LINE-IN-L, remove the LINE-IN-L ground jumper, re-fit J2 if wanted, remove the `col 30` → GND jumper) — **one at a time, re-measuring after each.**
**🚨 The −31.49 dBFS pooled baseline is HISTORICAL after stacking.** It describes a board with a flying ground return that no longer exists. Comparing post-stack readings to it as though the topology were unchanged would be the same error class as quoting the −39.1 dBFS figure after the interconnect fix.
**Watch specifically:** LINE-IN-L still arrives by flying wire from the breadboard front end. Stacking bonds shield GND and breadboard GND through the header/breakout into one net at far lower impedance. **That may resolve TODO-40's mechanism or relocate it** — the post-stack SOURCE floor is the measurement that says which.
**Also update after stacking:** `docs/asbuilt/netlist.md` §4 (interconnect) and `tools/gen_schematic.py` — the wire map, the physical-form notes and the drawings all describe flying leads and become stale on contact. Regenerate; do not hand-edit the SVGs.
**Proof:** both (1) and (2) recorded in journal.md with values, before any other change.

### TODO-40 — The elevated SOURCE floor depends on the external GROUND-RETURN PATH 🟡 **mechanism localised 2026-09-12; which of two mechanisms is still open**
**Observed.** With `48e` disconnected, grounding LINE-IN-L to **breadboard GND** gave **≈−31.9 dBFS**; grounding the same pad with a short jumper to the **Audio Shield's own GND** gave **≈−65.0 dBFS**. **Moving only the return point improved SOURCE by 33.1 dB.** Termination impedance identical in both — a wire to ground.
**Inference.** The elevated floor depends on the external ground-return path. **Not** caused merely by terminating LINE-IN-L, and **not** by the front-end signal source.
**Still unresolved.** Whether the mechanism is a real breadboard↔shield **ground-potential difference**, **loop-area pickup**, or a combination. Both predict this result; this test does not separate them.
**🔽 Next and only bench step:** scope directly between breadboard GND and the Audio Shield GND pad — same short-ground-spring setup, same settings, against the recorded **≈32 mV<sub>pp</sub> probe floor**. A real LF potential difference confirms ground-potential difference; a floor-indistinguishable reading points at loop pickup.
**Supporting observations — corroboration, NOT proof:** (a) SOURCE became ≈5.9 dB *quieter* than RETURN, the first inversion of the asymmetry all session; (b) the prior SOURCE/RETURN correlation disappeared — a successful prediction of the shared-disturbance hypothesis, since removing the shared path removed the correlation.
**🔧 Provisional design rule (see TODO-5):** codec analog input returns reference the Audio Shield ground **locally**; do not route the return through the breadboard ground path until the mechanism is characterised.
**❌ Candidates now dead:** the codec-common-mode explanation (a shield-local ground would have dragged the input just as far and instead gave the quietest reading of the investigation); the front end as source; J2; the pickup and guitar cable.
**📉 D2 / missing 10 µF on OPA_BIAS — now clearly NOT the cause.** Kept only as a spec deviation worth correcting: with the ≈32 mV<sub>pp</sub> control recorded, the +5 V rail (33) and OPA_BIAS (31) are both indistinguishable from the probe floor. Fit it, record before/after, expect no change to this.
**🔺 Proven, and this is the whole of it (journal 2026-09-12 (2)):** *the elevated SOURCE reading appears whenever LINE-IN-L is given an external low-impedance connection — even to ground — and largely disappears when LINE-IN-L is left floating.*

| LINE-IN-L | 48e | SOURCE |
|---|---|---|
| driven by front end | connected | −31.3 dBFS |
| **floating** | disconnected | **−57.0 dBFS** |
| **bare jumper to GND** | **disconnected** | **−31.9 dBFS** |

**A plain ground wire reproduces the level within 0.6 dB with the front end physically removed.** Two earlier framings are withdrawn: the front end does not supply the noise, and "the codec is exonerated" (entry (1)) asserted more than a two-state test can support.
**⚠️ D2 / the missing 10 µF bulk cap is now a WEAK hypothesis, not the leading one.** Once the ~32 mV<sub>pp</sub> grounded-probe control was recorded, both the +5 V rail (33) and OPA_BIAS (31) proved indistinguishable from the probe floor. Rail noise arriving via R1/R2/R5 would have to be visible at OPA_BIAS; it is not. **Fit the cap anyway** — it is a recorded departure from TODO-4 step 2 and the part is in stock — **but record before/after so it is evidence, not housekeeping, and do not expect it to fix this.**
**Three candidate mechanisms, none established:** (1) ground-potential difference between breadboard GND and the shield's analog ground; (2) loop-area pickup — both the front-end and ground-jumper cases share a *wire* enclosing area, the floating case does not; (3) codec input condition — if LINE-IN-L is DC-coupled to the SGTL5000 pin, tying it to GND forces the input outside its common-mode window around VAG. **(3) is answerable from PJRC's published Rev D schematic with no bench work — do that first, it is free.**
**The discriminating bench test:** ground LINE-IN-L with a **very short wire to the Audio Shield's OWN GND pad**, not the breadboard rail. Collapses loop area and localises the reference in one move. Drops toward −57 ⇒ mechanism (1) or (2). Stays near −31.9 ⇒ mechanism (3). One wire move, rules out two of three.
**Supporting evidence (not proof):** SOURCE and RETURN track in sign and direction across all five windows and break at the *same sample index* in the uptime-130 s window, with nothing connected to RETURN. SOURCE ≈30× RETURN = 29.5 dB, which is the SOURCE/RETURN asymmetry itself.
**🚨 BENCH STATE — four deviations from the −31.49 dBFS pooled baseline are currently in place:** `48e` lifted off LINE-IN-L · LINE-IN-L jumpered to GND · J2 removed · `col 30` → GND jumper fitted. **Restore all four and re-baseline before any future reading is treated as comparable.**
**Established (journal 2026-09-12 (1)):** lifting `48e` off SGTL5000 LINE-IN-L dropped SOURCE_NODE from **−31.3 to −57.0 dBFS, a 25.9 dB collapse**, leaving it 1.8 dB above the open RETURN channel. The noise arrives *through* the LINE-IN-L connection. ~~The codec, its routing and the digital capture path are exonerated.~~ **Withdrawn 2026-09-12 — see the reframe above; a bare ground jumper reproduces the effect.** Independently corroborated: −31.3 dBFS back-converts to 36.2 mV<sub>pp</sub> at the codec input, against 45.77 mV<sub>pp</sub> measured on the scope at the same node.
**NOT established:** where between C1's output and `48e` it originates.
**🔺 The hypothesis — deviation D2.** `docs/asbuilt/netlist.md` §5 records that OPA_BIAS carries **only C4 (0.1 µF)**, while TODO-4 step 2 specified **10 µF electrolytic + 0.1 µF ceramic**. The bulk cap was never fitted. OPA_BIAS draws 88 µA static, has R<sub>th</sub> = 8.25 kΩ, and is fed by R1 47 kΩ from a +5 V rail shared with the Teensy and the codec. R5 then delivers whatever is on that node to pin 3 — a picoamp JFET gate, so essentially undivided — and a unity-gain follower reproduces it. The rail-to-bias divider ratio is 10/(47+10) = **0.175**, so ~180 mV<sub>pp</sub> of rail noise would yield ~31 mV<sub>pp</sub> at OPA_BIAS.
**⚠️ Why this is only a hypothesis.** The scope readings 31.35 (OPA_BIAS) → 37.90 (pin 1) → 45.77 mV<sub>pp</sub> (`48e`) look like a rising gradient, **but the grounded-probe control was never recorded under the final settings (20 MHz limit engaged)**. The probe/scope floor is unknown, so the first two figures may be substantially or entirely floor. **A gradient measured against an unknown floor is not a gradient.** Do not treat D2 as diagnosed.
**Competing candidates, none excluded:** U1's own noise · the biased high-impedance node at col 33/37 picking up directly · C2 · the `48e` run itself · a shared ground/rail mechanism coupling preferentially into the high-impedance path.
**Proof criterion — in this order, and step 1 is not optional:**
1. **Record the grounded-probe control V<sub>pp</sub> under the exact final scope settings.** Every amplitude comparison in this investigation depends on it. Until it exists, no reading below the ~46 mV<sub>pp</sub> at `48e` can be interpreted.
2. **Scope the +5 V rail, same settings.** If it reads ≈5.7× the OPA_BIAS amplitude, the divider path is consistent. If the rail is clean, the noise is local to the bias node and D2 remains the right fix for a different reason.
3. **Fit the 10 µF bulk cap on OPA_BIAS** (+ to OPA_BIAS, − to GND), reconnect `48e` → LINE-IN-L, and re-measure SOURCE_NODE peak over ≥5 windows. **This is the decisive single-variable test.** SOURCE falling materially below −31.3 dBFS confirms D2 was contributing; no movement falsifies it and the search moves to the other candidates.
**Note the fix is worth doing either way:** D2 is a recorded departure from the specified design, and **10 µF ×10 is already in stock** per TODO-4. Fitting it corrects a known deviation regardless of what it does to the noise floor — but **record the before/after so the result is evidence, not housekeeping.**
**Bench-safety:** all of this is on the analog section (cols 41–43) and the `48e` run. It does **not** touch the Audio Shield or the I²S interconnect, so it does not threaten the R1-protected geometry (journal 2026-09-07 (6)).
**Also outstanding from this session:** `col 30` → GND jumper still fitted, `48e` → LINE-IN-L still lifted, J2 still removed. **Restore all three and re-baseline before any result is treated as comparable to the −31.49 dBFS pooled baseline.**

### TODO-32 — R5's value has never been measured, and it sets BOTH the input impedance and the C1 corner 🔴 **blocks TODO-23 and TODO-19 — resolve before Phase 5's first pickup**
**Why:** every statement this project makes about input impedance (TODO-23) and low-frequency corner (TODO-19) rests on R5 = 100 kΩ, and **nothing has ever verified that number.** It traces to TODO-4 step 3 and the runbook — design intent. `docs/asbuilt/netlist.md` carries it as `DERIV`, which **cannot be supported**: R1–R4 are derivable because the divider sets a voltage that was measured (0.874 V vs 0.877 V predicted), but R5 feeds a JFET gate drawing picoamps, drops no measurable voltage, and is constrained by no recorded measurement. The correct tag is `INF`.
**What the in-circuit probing showed (2026-09-08, ChatGPT bench session):** `37c` ↔ the bias node measured **73.5 kΩ** in circuit, against ~108 kΩ expected for 100 kΩ + the 8.25 kΩ OPA_BIAS Thévenin. That is unexplained. It may be a mis-identified probe column (see journal 2026-09-08 (1)) rather than a wrong resistor — **in-circuit readings cannot separate the two, which is the whole point.**
**Consequences if R5 is not 100 kΩ:**
- **Input impedance** is R5. 75 kΩ loads a 6–250 kΩ pickup harder than the record claims and moves TODO-23's 1 MΩ target further away.
- **The C1 corner** is set by R5. 10 nF into 100 kΩ ⇒ 159 Hz; into 75 kΩ ⇒ **212 Hz**. Every low-frequency limitation quoted in this project comes from an unmeasured number.
- Journal 2026-09-05 (6)'s consistency check assumed 100 kΩ. It mildly favours 100 kΩ (predicts 0.9867 vs 0.9782 for 75 kΩ, measured 0.9848) but that entry already says a 1 kHz probe is nearly the least informative place to measure a 159 Hz high-pass.
**What:** **lift one leg of R5 and measure it out of circuit.** Then read its colour bands and record both. Do it in the same bench pass as any other analog-section work — it touches cols 37/41 only, **not** the shield or the I²S geometry, so it does not threaten R1's protected configuration.
**Proof:** an out-of-circuit ohmmeter reading and a band reading agreeing on one value, recorded in journal.md, and `docs/asbuilt/netlist.md` R5 promoted from `DERIV` to `MEAS`.
**Sequencing:** resolve jointly with TODO-23 and TODO-19 — if R5 is being swapped toward 1 MΩ anyway, measure the old part on the way out rather than making two passes.

### TODO-23 — Buffer input impedance is ~100 kΩ — too low for a guitar pickup 🔴 lands on Phase 5
**Why:** The input bias resistor to VGND is 100 kΩ (confirmed by the runbook's own corner-frequency arithmetic, R = 100 000), setting input impedance at ~100 kΩ. The runbook's Phase 4 Background justifies the JFET choice by noting pickups are high-impedance (6–250 kΩ) — then loads them with 100 kΩ, which rolls off highs and reduces output. Standard guitar-amp input is ~1 MΩ. **The runbook argues for a high-impedance front end and builds a comparatively low-impedance one.**
**What:** Harmless at Phase 4 (a phone is a low-impedance source) but it bites at Phase 5's first real instrument jack. Raise the bias resistor toward 1 MΩ, which **also shifts the input RC corner** — resolve jointly with TODO-19 and TODO-21 rather than in isolation, since all three touch the same network.
**Proof:** a guitar plugged into the Phase 5 jack shows no audible/measurable high-frequency loss versus the same guitar into a known 1 MΩ amp input.

### TODO-29 — TF spot-check / live TF is pinned at the −24.0 dB clamp rail 🟡 **[compiles] serial diagnostic FIXED, compile-verified, NOT uploaded — see journal.md 2026-09-07 (8)**
**✅ Evidence preserved first:** `ai/evidence/2026-09-07-tf-clamp-preserved.md` — 33 consecutive windows in which `1kHz` printed exactly −24.0 dB every time while the true TF was −46.3 to −48.0 dB.
**✅ Change made (additive only, no measured value altered):** `AudioFrame.tf_clamped_bits[]` + `tf_clamped_count`, set in `audioEngine_update()`, read via `audioEngine_tfBinClamped()`. The serial diagnostic now prints `RAIL[-24.0dB]` and a `TF clamped bins: N of 512` line. **The clamp itself is unchanged** — `tf_db[]`, the EMA, confidence and persistence are bit-identical.
**Compile evidence (Teensy 4.1):** FLASH 158 340 → 158 532 (+192), RAM1 218 752 → 218 816 (**+64, exactly the bitmask**). Clean; the two warnings are pre-existing and present in the baseline build.
**🔴 Still open — `display_engine.cpp` renders railed bins as ordinary curve points.** [display_engine.cpp:347](display_engine.cpp#L347) reads `frame->tf_db[bin]` with no clamp check; `audioEngine_tfBinClamped()` exists for it. Separate consumer, separate change.
**🔴 Still open — not yet on hardware.** Board is still running `e6daac8`. Upload gated on Conley photographing the verified baseline first.
**Pass criterion when it does go up:** with RETURN disconnected, `1kHz` reads `RAIL[...]` and `TF clamped bins` is a large fraction of 512 — the same physical condition as the evidence file, reported honestly. **A large clamped count is not a regression.**
**Why:** [audio_engine.cpp:283](audio_engine.cpp#L283) clamps every bin with `constrain(tf_raw, TF_DB_MIN - 6.0f, TF_DB_MAX + 6.0f)`, and `TF_DB_MIN = -18.0f` ([config.h:391](config.h#L391)) ⇒ a hard floor at exactly **−24.0 dB**. Observed 2026-09-07: every diagnostic window prints `1kHz=-24.0dB` while the actual SOURCE−RETURN gap is **47.3 dB** (−9.0 vs −56.3 dBFS). The number looks like a measurement and is a rail. The EMA then converges onto the rail and `persistence: ACTIVE` stays lit indefinitely.
**Not a validation bug:** `validation.cpp` computes TF from raw FFT means with the EMA bypassed ([validation.cpp:47](validation.cpp#L47)), so the 40 dB gate gap is measured on unclamped data. The defect is confined to the live frame, the display curve, and the serial diagnostic.
**What:** decide whether ±18 dB is the right *display* range (it probably is, for a guitar rig) and then stop letting the clamp masquerade as data — e.g. mark clamped bins distinctly (NAN, or a `tf_clamped` flag) rather than storing the rail value, so the display draws a gap and the diagnostic prints something other than a plausible number. Do **not** simply widen `TF_DB_MIN`; that moves the rail without fixing the reporting.
**Proof:** with RETURN disconnected, the diagnostic reports a clamped/undefined indication rather than `-24.0dB`, and with a real rig in the loop the spot-check tracks the measured gap.

### TODO-30 — Remove the temporary RAWDUMP and AudioMemory diagnostics 🔴 **UPGRADED 2026-09-16: potential MEASUREMENT-INTEGRITY defect, not just noise. Fix before relying on `m` for measurement validation**
**⚠️ Measurement conflict (2026-09-16, CODE-DERIVED, NOT bench-observed):** RAWDUMP (`audio_capture.cpp:596–648`) is compiled in unconditionally. Every 5 s it calls `audioCap_beginRawCapture()` (`clear()` + `begin()`), reads one block, then calls `audioCap_endRawCapture()` (`end()` + `clear()`), **on `s_queue_src`/`s_queue_ret`, the same queues `measurement_engine` arms at CAPTURE entry (`measurement_engine.cpp:780, 808`) and drains for the complex-FFT transfer function (`:895–899`).** During a capture this would (1) discard raw samples mid-capture, breaking frame contiguity, and (2) leave the queues **disarmed**. `audioCap_rawSamplesAvailable()` then cannot reach `BLOCKS_PER_FFT`, and CAPTURE has no timeout, so an `m` measurement would likely stall or accumulate non-contiguous frames. It cannot inject foreign samples (see journal 2026-09-16 (5)); it can only destroy or disarm them. **Fix as its own change, not folded into other work.** The existing compile-flag plan (re-enable RAWDUMP on demand) must also stop it touching the measurement queues while a measurement is armed or capturing.
**Why:** both were added for the I²S corruption hunt, which closed 2026-09-07 (entries 6 and 7). `[RAWDUMP]` prints 64 int16 values per 5 s window and `AudioMemory` telemetry was there purely to test the (refuted) leak hypothesis. They cost serial bandwidth and clutter every capture.
**What:** strip both. **Keep the ability to re-enable RAWDUMP behind a compile-time flag** — it is the only tool that ever showed sample-level corruption directly, and it is the thing to reach for first if the fault ever returns.
**Proof:** a clean 5 s diagnostic window with no `[RAWDUMP]` lines, and the build still compiles with the flag turned on.

### TODO-27 — `EXPECTED_BLOCK_MS` is wrong by 2× — the FFT overlaps 50% 🔴 diagnostic-only, but it fakes a permanent anomaly
**Why:** [guitar_rig_analyzer.ino:99](guitar_rig_analyzer.ino#L99) computes `1000 × FFT_AVERAGE_COUNT × FFT_SIZE / SAMPLE_RATE` = 92.9 ms, assuming `AudioAnalyzeFFT1024` consumes 1024 fresh samples per result. **It doesn't — it runs 50 % overlap.** Verified in the Audio library source (`analyze_fft1024.cpp`): after `outputflag = true` it resets `state = 4`, keeping the last 4 blocks (512 samples) and needing only 512 new ones. True period = `1000 × 4 × 512 / 44100` = **46.44 ms**; measured **46.3 ms**, agreeing to 0.3 %. The hardware is right and the constant is wrong.
**What:** use the hop size — `FFT_SIZE / 2` — in the formula. Diagnostic-only (the printf at :186 and the delta at :555), so no behavioural change; but left alone, every diagnostic forever reports a phantom −46.6 ms anomaly, exactly the sort of false signal that has already cost this project days.
**Proof:** diagnostics report a delta near zero on a healthy run.

### TODO-25 — `s_display_ok` guard in display_engine.cpp 🟢 **DONE — verified on hardware 2026-09-05, 47× recovery**
**Result:** block period **2194.3 ms → 46.3 ms** (3 blocks/6583 ms → **108 blocks/5000 ms**), stable across consecutive diagnostic windows. The unguarded `waitPoll()` spin against the absent RA8875 was the entire bottleneck. Committed `8548c4c`. See journal.md 2026-09-05 (10). *(46.3 ms is the correct period — the "expected 92.9 ms" it is compared against is itself wrong; see TODO-27.)*
**✅ Implemented:** file-static `s_display_ok`, false until `displayEngine_init()` fully succeeds (set false at entry so every failure path leaves it false; set true only after `tft.begin()` *and* the chrome draw). `if (!s_display_ok) return;` added as the first statement of all five other public entry points — `_update`, `_drawStatusMessage`, `_showResult`, `_showAborted`, `_restoreLive`. Internal helpers are `static` and unreachable from outside, so the public entry points cover every path to the panel. 16 insertions, one file; no audio, setup-ordering, or pin changes. Compiles clean (FLASH 157636 / RAM1 218720).
**🔴 Not yet proven on hardware** — the pass criterion below is a measurement, not a compile.
**Why:** with the RA8875 absent, every `displayEngine_*` call still drives SPI at a device that isn't there. Measured 2026-09-05: **2194 ms per block against an expected 92.9 ms**, with block count and display count identical (3 and 3) because [guitar_rig_analyzer.ino:504](guitar_rig_analyzer.ino#L504) calls `displayEngine_update()` once per processed block. The loop still spins at ~38 k iterations/s, so nothing deadlocks — the ~2.2 s is burned inside `Adafruit_RA8875::waitPoll()`, which spins on a status register that never satisfies with no device on the bus. Predicted in journal 2026-09-05 (8) as a possible infinite hang; it turned out to be a severe slowdown instead, which is easier to mistake for "harmless."
**What:** add a file-static `s_display_ok`, set from `displayEngine_init()`'s return, and early-return from every public entry point when false. Deliberately not done pre-emptively — the change was scoped to failure behaviour only. The evidence now justifies it.
**Proof:** with the display absent, block period returns to ~92.9 ms and the display/block counts decouple.

### TODO-28 — `AudioAnalyzePeak::read()` called without `available()` 🟢 **DONE — fixed, uploaded, verified `b6f3dc1`. Real bug, but NOT the cause**
**Verified on hardware 2026-09-05:** `available()` returns **true every window** — neither `[audioCap] peak unavailable` line ever appears. The analyzers are being fed, `read()` now only ever runs on genuine data, and **the `+0.0 dBFS` is real full-scale sample data**. The defect was genuine and is correctly fixed, but it was masking the fact that the saturation is real rather than causing it. See journal.md 2026-09-05 (15).
**Why:** `audio_capture.cpp:507–508` calls `s_peak_src.read()` / `s_peak_ret.read()` unguarded. From `analyze_peak.h`, when no audio has arrived since the last read the reset values (`min_sample=32767`, `max_sample=-32768`) survive, and `abs(-32768)=32768` ⇒ `32768/32767 = 1.00003` ⇒ **exactly `+0.0 dBFS`**, with `CLIP_*` latching every window because the threshold test trivially passes.
**The real damage:** `+0.0 dBFS` is produced *both* by a codec delivering full-scale garbage **and** by a peak object receiving nothing. **The meter cannot distinguish "saturated" from "silent"**, so no bench test can separate those two cases while this stands. That is precisely why TODO-26 has stalled.
**Caveat, stated honestly:** the FFT emits at the correct 46.3 ms cadence and `AudioAnalyzeFFT1024::update()` returns early on a NULL input block, so blocks probably *do* reach the graph — both the FFT and the peaks hang off the same mixer outputs (`audio_capture.cpp:149–150`). That makes "genuine garbage" the more likely case and this bug incidental. But the reasoning is indirect, and indirect reasoning about this pipeline has already been wrong twice this week.
**What:** guard both reads with `available()`. When false, **do not fabricate a level** — carry the previous value or mark the window invalid, and do **not** latch `CLIP_*` from it.
**✅ Implemented 2026-09-05, compile-verified** (FLASH 157892 / RAM1 218720). `available()` checked **once** per window and reused — it is consuming (clears `new_output`), so a second call would have created a new bug while fixing this one. `read()` only inside the valid branch. Clipping gated in **both** places it is derived: the latch at :518 and the block fields at :536, which now carry `s_last_*_clipping` so each block's peak and clip flag come from the same window. `-120.0f` used only as the pre-first-read initializer (already this module's documented silence floor at :308), never written on an unavailable window. Diagnostics print `[audioCap] peak unavailable: SOURCE` / `: RETURN` independently. `AudioRawBlock` API, FFT path, routing and codec setup untouched.
**Proof:** on the next run the two cases become distinguishable — genuine saturation still reads ≈0 dBFS, starvation no longer does.
**The fork this creates:** `peak unavailable` appears ⇒ the Audio Library graph is not delivering blocks to the analyzers, investigate data delivery. No such line but peaks still ≈0 dBFS ⇒ real full-scale samples are entering the analyzers, move down to codec/I²S/analog input.
**Also fixes a latent measurement hazard:** once the path works, any starved window would report full scale and a false clip, poisoning validation tests 1–4 (TODO-9) and anything calibrated from them.

### TODO-26 — Both nodes read `+0.0 dBFS` 🟢 **CLOSED 2026-09-07 — root cause found and fixed: signal integrity on the flying-lead I²S interconnect.**
**Resolution:** shortening the shield↔Teensy jumpers (8/20/21/23 + GND + 3.3 V) took corruption to **exactly zero across 360 windows**, 0 % of windows clipping against 100 % in every previous run — journal.md 2026-09-07 (6). Re-confirmed live 2026-09-07: five windows at −9.0 dBFS with clean raw dumps and no clip events — journal.md 2026-09-07 (7).
**Hypotheses this closed as WRONG, kept so they are not re-run:** the AudioMemory leak, warm-up/settling, monotonic degradation, DOUT joint quality (three reworks, none of them the cause), and pin-8 output-contention damage. Every endpoint test passed throughout because the fault was in the medium between the endpoints.
**Everything below is the investigation record, retained for its method — the conclusions in it are superseded.**
*(historical, from 2026-09-06:)* **FAULT CLEARED 2026-09-06 — but possibly MASKED, not fixed. Verify with scope disconnected.**
**✅ Scope (RIGOL DHO804) proved all three clocks correct:** LRCLK **44.108 kHz** stable ~50 % duty · BCLK **~2.82 MHz** · MCLK **~11.29 MHz** — exactly 1× / 64× / 256× Fs. **The initial "Vpp = 468 mV" was a probe attenuation mismatch (probe on 1X, scope assuming 10X), NOT a finding** — corrected to 10X and levels read normally. Together with the register comparison, **both static configuration and runtime bus timing are confirmed good.**
**✅ The pipeline now works.** Three consecutive dumps (uptime 605/635/645 s): `SOURCE_NODE peak −38.9 / −38.2 / −39.1 dBFS`, `RETURN −50.1 / −49.2 / −50.1`, **no clipping, no wild excursions, no −2880 DC baseline**. Dump C crosses zero at samples 1 and 24 ⇒ **23 samples/half-cycle = 958.7 Hz** against 22.05 expected for 1 kHz. **The injected tone is being decoded correctly.** (Waveform is square, not sine — the phone is producing a square tone. Not a fault.) Full data: journal.md 2026-09-06 (1).
**🔺 DIAGNOSIS — the fault points strongly to the physical/interconnect layer, NOT DSP or static I²S configuration.** The decisive observation: **the same flashed build** went from corrupted full-scale raw samples to a clean ~1 kHz waveform after physical handling. Supporting evidence: (1) corruption was burst-like with long quiet runs — an intermittent, not a design fault; (2) both channels affected identically ⇒ a shared resource; (3) clocks and register config now both proven correct, eliminating the structural hypotheses; (4) the fault cleared during a session of repeated physical handling — probe clips attached, channels moved, tone disconnected and reconnected; (5) **two unexplained USB dropouts** earlier in this project, one aborting an upload, independently fit a marginal connection. The corrupted data's stable −2880 DC offset has also vanished.
**❌ NOT concluded: "intermittent connection, most likely ground."** An earlier version of this item said that. Ground is *a* candidate, not established. **The suspect set is the shared ground path AND the clock/data jumpers** — handling any of them could have changed contact pressure.
**✅ SCOPE-REMOVED TEST RUN 2026-09-06 — answer is BOTH, see journal.md 2026-09-06 (2).** Scope connected: peaks −38.9 / −38.2 / −39.1 dBFS, no clipping. Scope removed: peaks **+0.0 / +0.0 / −1.9 dBFS**, clipping continuous. **So the scope was demonstrably suppressing something.** But the *original* fault did not return — no −2880 DC baseline, no −2880/−6530/−8480 quantised levels, no 6–12 wild excursions per 32 samples. **All six raw windows (three with scope, three without) are clean, coherent ±280-count ~1 kHz square waves.**
**Rate collapsed ~400×, not eliminated.** Originally ~20–35 % of samples corrupted. Now raw windows are clean while the peak still catches outliers — the peak window is ~2048 samples and the dump shows 32 (**1.6 %**), so a ~1-in-2048 rate would be missed ~98 % of the time. Outliers are 41 dB above the −41.4 dBFS signal, so they cannot be audio.
**⚠️ Caveat on this evidence:** RAWDUMP arms then reads the *first* block, so if corruption is bursty in time it may systematically sample quiet moments. "Windows are clean" is weaker than it looks.
**Revised reading:** physical handling substantially improved the connection *and* the scope ground was additionally suppressing the residual. Consistent with a marginal contact whose severity varies with mechanical/electrical conditions. **Still does not identify which connection.**
**✅ GROUND-CLIP-ONLY TEST RUN 2026-09-06 — ground alone does NOT suppress the outliers. See journal.md 2026-09-06 (3).**

| Condition | Peak | Raw bulk | Outliers above bulk |
|---|---|---|---|
| Full scope (probes + ground) | −38.9 dBFS | ≈−41 dBFS | **≈2 dB — essentially none** |
| No scope at all | +0.0 dBFS | ≈−41 dBFS | ≈41 dB |
| **Ground clip only** | **−2.2 dBFS** | ≈−50 dBFS | **≈48 dB** |

Peaks stayed at −2.2 dBFS, barely different from −1.9 with the scope fully removed and nowhere near −38.9 with the full scope. **The earlier suppression depended on more than the ground path.**
**✅ RE-RUN 2026-09-06 WITH TONE CONFIRMED PLAYING — result stands, and we caught an event. See journal.md 2026-09-06 (4).** Peaks −2.3/−1.8, −1.7/−6.4, −2.3/−1.5 dBFS across three dumps, against −38.9 with the full scope. SOURCE shows the coherent ~1 kHz square wave throughout; TF confidence recovered to 80/77/7 %. **Ground alone does not suppress the fault.**
**🔬 THE KEY OBSERVATION — a single-sample impulse caught in-window:**
```
RETURN: ... -68  -76  [27514]  -79  -11 ...
```
**One sample at −1.5 dBFS wedged between neighbours at −52.7 dBFS: a 51 dB single-sample excursion**, and it accounts for that window's −1.8 dBFS peak. The paired SOURCE window is a clean square wave. **This is an isolated single-word error — one I²S word decoded wrongly while its neighbours are correct. A sustained framing or format problem cannot produce that; it would corrupt every word.**
**Three severity regimes, consistently ordered:** original fault 6–12 per 32 (**20–35 %**) · ground-clip-only 1 in 96 (**~1 %**) · full scope, peak == signal level over 2048 samples (**<0.05 %**).
**🔺 Ground substantially ruled out as the mechanism.** Adding a ground path changed nothing; adding probe tips changed everything. Tips sat on **LRCLK (20), BCLK (21), DOUT (8)**, each ~1 MΩ ∥ ~10 pF — a load that damps ringing and sharpens edges. Isolated single-word errors are exactly what a marginal edge produces: most edges read correctly, an occasional one does not. **Hypothesis: signal integrity on one of the clock/data jumpers.**
**✅ PIN 8 (DOUT) TEST RUN 2026-09-06 — loading DOUT makes it DRAMATICALLY WORSE. Strong localization. See journal.md 2026-09-06 (5).**

| Condition (same session, same tone) | Peaks | Signal present? |
|---|---|---|
| Ground clip only | −2.3 / −1.7 / −2.3 dBFS | ✅ coherent ~1 kHz |
| **Ground + pin 8 tip** | **+0.0 / +0.0 / +0.0 dBFS** | **❌ gone** |

Adding **~10 pF to DOUT reverted the fault to original severity** — −2000 DC baseline back, wild excursions back, coherent square wave destroyed. Three dumps each way, minutes apart, otherwise identical.
**🔺 Mechanism, stated correctly this time:** extra capacitance **slows** the DOUT edge (it cannot sharpen one — an earlier version of this item said "damps ringing and sharpens edges", which is electrically wrong). If DOUT only just meets the Teensy's setup time at the sampling edge, slowing it pushes the transition past the sampling instant and bits read wrong. **DOUT has very little timing margin — ~10 pF is enough to break it comprehensively.**
**❌ This invalidates the "full scope suppressed the fault" story.** Entry (1) recorded three clean dumps at −38.9 dBFS with probes on 20, 21 **and 8**. If loading pin 8 breaks the link, the full-scope condition should have broken too. It didn't. Both cannot be explained by probe loading. **The likeliest reading is that the earlier suppression was coincidental — the fault is time-varying. Treat the scope-suppression correlation as unproven.**
**❌ Also corrected:** "a framing/format problem cannot produce an isolated bad word" was too strong. Correct claim: **a persistent static framing mismatch is ruled out.** An isolated bad word does not by itself prove the fault is on an I²S jumper — **a transient codec/ADC event could produce one too.**
**❌ CLOSURE TEST FAILED 2026-09-06 — removing the pin-8 tip did NOT restore the clean regime. My pin-8 causal claim is REFUTED. See journal.md 2026-09-06 (6).** Three dumps at uptime 1435/1445/1455 s, all still `+0.0 dBFS`, clipping continuous, −1500…−2200 DC baseline, no coherent waveform.
**🔺 THE REAL PICTURE — monotonic degradation all session, never any recovery:**

| uptime | Condition | SOURCE peak | Regime |
|---|---|---|---|
| 605–645 s | Full scope (3 tips + gnd) | −38.9 / −38.2 / −39.1 | **CLEAN** |
| 735–900 s | Ground clip only | −2.2 … −2.3 | **mild** |
| 1180–1210 s | Ground + pin 8 tip | 0.0 / 0.0 / 0.0 | **SEVERE** |
| 1345–1410 s | Pin 8 removed (14 windows) | 0.0 throughout | **SEVERE** |
| 1435–1455 s | Pin 8 removed | 0.0 / 0.0 / 0.0 | **SEVERE** |

**⚠️ EVERY probe-based A/B test this session is confounded** — none controlled for a monotonic time trend, and each intervention coincided with a step down that would have happened anyway. "Full scope suppressed it", "ground alone doesn't suppress", and "pin 8 loading caused the regression" are all now unsupported; the last is outright refuted.
**Better-fitting hypothesis — cumulative mechanical disturbance.** Every intervention involved physically attaching/detaching a probe near the shield/Teensy jumpers. If a connection there is marginal, each handling event nudges it further out of contact, and nothing in the sequence restores it. That explains both the one-way degradation and why removing the load changed nothing. **The electrical-loading explanation is refuted; mechanical disturbance is consistent with all data but unproven.**
**✅ UNATTENDED CONTROL RUN 2026-09-06 — 102 windows over 510 s, scope fully absent. See journal.md 2026-09-06 (7).**
**❌ First: the peak metric is misleading.** `SOURCE_NODE peak` pegs at 0.0 dBFS if **one** sample in ~2048 is bad — it cannot distinguish "one bad sample" from "stream destroyed". **Use raw outlier count per 32-sample window instead.** Reclassifying by it changes the conclusions.
**Answer 1 — recover / stay severe / drift?** By peak: fluctuates, 66 % at 0.0 dBFS, never returns to −38. **By outlier count: RECOVERED** — 82/102 windows have **zero** outliers, mean **0.21/32 = 0.64 %**, versus 7–9/32 during the pin-8 period.
**Answer 2 — morphology?** **Improved markedly.** Coherent ~1 kHz waveform present throughout, DC baseline back near zero, against the pin-8 era which had no waveform and a −2000 baseline.
**Answer 3 — spontaneous transitions?** **Constantly**, in both directions, with nothing touched and the scope absent.
**❌❌ REFUTES my "monotonic degradation" claim and the "cumulative mechanical disturbance" hypothesis from the previous entry.** The fault recovered on its own; a cumulative-damage model predicts it cannot. That reading rested on five widely-spaced samples; 102 closely-spaced ones show **rapid bidirectional fluctuation over seconds-to-minutes**. The apparent trend was a sparse-sampling artefact.
**🚨 NEW SYMPTOM — the board halted.** Silent since uptime ≈2370 s, 12+ min and counting, still USB-enumerated with the connection open and error-free. `loop()` or Serial has stopped; no boot banner, so a hang not a reboot.
**⚠️ Our own diagnostic is a credible suspect for the halt — do NOT blame the hardware fault yet.** The RAWDUMP block arms/disarms the record queues **every 5 s** (~470 cycles since boot). One leaked `audio_block_t` per cycle would exhaust the 128-block `AudioMemory` pool within a few hundred cycles.
**✅ DISCRIMINATOR RUN 2026-09-07 — HALT DID NOT REPRODUCE. See journal.md 2026-09-07 (1).** Power-cycled USB only, scope absent, tone off, wiring untouched. **Ran 46.8 min continuously (uptime 55 → 2860 s, 540 windows) and never stopped**, passing straight through the previous ~2370 s halt point (~572 RAWDUMP cycles vs ~474 at the earlier halt).
**Deterministic resource exhaustion at a fixed cycle count is ruled out — but not resource exhaustion generally.** A variable-rate leak, or one gated on a condition that didn't recur, would still fit. **Proving or killing it needs `AudioMemoryUsage()` / `AudioMemoryUsageMax()` telemetry** in the 5 s diagnostics, not another timing run.
**❌ Correction:** an earlier version implied a repeatable halt would *prove* "one leaked `audio_block_t` per RAWDUMP cycle". It would not — it would make deterministic firmware/resource exhaustion strongly likely, after which the arm/read/free/disarm paths need inspecting and the pool instrumented.
**📊 The fault fluctuates enormously AND improves over a run.** 540 windows: 26 % perfectly clean, range **0 to 27 outliers per 32**, mean 3.14/32 = 9.81 %. **Trend within the run, untouched: first third 6.75 → last third 0.83 outliers/32 — an ~8× improvement over 47 min** with no scope, no tone, no changes.
**🔺 Best-fitting *description* (not a mechanism):** warm-up / settling behaviour — high error rate when cold, improving over tens of minutes, still fluctuating window-to-window. Consistent with a contact whose resistance or geometry shifts as the board warms, but it does **not** name a conductor or distinguish a marginal contact from a temperature-sensitive component.
**📐 The ≥100-window rule is now demonstrated, not asserted:** with 26 % of windows perfectly clean and others at 27/32 corrupted, **any three consecutive windows could have "proved" almost anything** — which is exactly what happened repeatedly on 2026-09-06.
**✅ COLD-START RUN 2026-09-07 — 420 windows / 36.5 min, cooled overnight, untouched. See journal.md 2026-09-07 (2).**
**✅ AudioMemory LEAK RULED OUT — definitively.** `AudioMemoryUsageMax()` read **exactly 20 in all 420 windows** (min 20, max 20, pool 128), in-use ~13, across ~440 RAWDUMP arm/disarm cycles. The pool is not climbing at all. **The RAWDUMP block leaks nothing and is exonerated as the cause of the ~2370 s halt.** That halt is now unexplained, unattributed, and remains a single unreproduced event.
**❌ WARM-UP HYPOTHESIS DID NOT REPRODUCE.** Predicted high-at-cold-start declining with time; observed **low → high → low**:

| Band | Uptime | n | SRC out/32 | RET out/32 | mem MAX |
|---|---|---|---|---|---|
| 1 | 0–545 s | 100 | **2.83** | 2.26 | 20 |
| 2 | 550–1070 s | 100 | **9.50** | 8.81 | 20 |
| 3 | 1075–1575 s | 100 | **7.29** | 6.66 | 20 |
| 4 | 1580–2090 s | 100 | **4.82** | 3.65 | 20 |
| 5 | 2095–2190 s | 20 | **2.85** | 0.95 | 20 |

Started near its best, climbed **3.4×** to a peak in band 2, then declined back. The previous run showed a monotonic 6.75 → 0.83. **Two runs, two different shapes ⇒ time-since-cold-start does not predict the error rate.** The earlier "warm-up trend" was most likely one arbitrary slice of slow wandering — the same sparse-sampling trap as the 3-window conclusions, just at a larger scale.
**SOURCE and RETURN track each other closely in every band** — one shared cause, not two independent faults. **No halt this run** (36.5 min continuous).
**📐 Method update — the ≥100-window rule is not sufficient.** The wandering timescale (~10 min) is *longer* than a 100-window band (~8.5 min). **Future comparisons need much longer bands or interleaved A/B/A/B sampling**, so slow drift cannot masquerade as a treatment effect. Comparing two conditions measured minutes apart — every hardware test done so far — remains unsafe.
**🎯 ROOT CAUSE LOCALISED 2026-09-07 — DOUT (pin 8) found PHYSICALLY BROKEN. See journal.md 2026-09-07 (3).** Mechanical inspection found the DOUT jumper broken; it was remade. Only that connection was touched.
**Remaking it made corruption 4.2× WORSE — and that is the proof we needed:**

| Metric | PRE (420 win) | POST (360 win) |
|---|---|---|
| Mean SRC outliers/32 | **5.95** | **24.72** |
| Mean RET outliers/32 | 5.14 | 26.85 |
| Clean windows | 3.1 % | **0.6 %** |
| Worst window | 31/32 | **32/32** |
| `AudioMemoryUsageMax` | 20 | 20 |

Post-repair bands: 21.87 / 24.63 / 27.01 / 25.82. **Pre-repair bands spanned 2.83–9.50 — the lowest post band is 2.3× the worst pre band. Zero overlap.**
**✅ FIRST A/B WHERE THE EFFECT DWARFS THE WANDERING.** 780 windows, 4.2× shift, no band overlap, against a fault that drifts only 3.4× on its own. **Changing DOUT pin 8 changed the error rate decisively ⇒ DOUT pin 8 is causally involved.**
**It retrospectively explains everything:** a partly-broken DOUT gives sporadic single-word errors, perfect clocks, correct registers, both channels affected together (shared data line), a rate that wanders with contact conditions, and occasional dropouts. **It was never fully open** — coherent 1 kHz waveforms appeared throughout, so this was a marginal/partly-failed joint, not a severed one.
**❌ SECOND REWORK FAILED THE CRITERION 2026-09-07. See journal.md 2026-09-07 (4).**

| Run | DOUT state | n | SRC out/32 | clean % | bands |
|---|---|---|---|---|---|
| **A** | original (found broken) | 420 | **5.95** | 3.1 % | 2.83–9.50 |
| **B** | 1st rework | 360 | **24.72** | 0.6 % | 21.87–27.01 |
| **C** | 2nd rework | 360 | **8.54** | 0.0 % | 6.93–10.03 |

Criterion was "well below 5.95, ideally near zero". Got **8.54 — FAIL**. **C's bands sit inside A's range, so C is statistically indistinguishable from the original broken joint.** The second rework only undid the first rework's damage (2.9× better than B); it improved nothing.
**🔺 DOUT is causally involved but reworking it is NOT sufficient.** Three joint states → three distinguishable rates, so the conductor matters. But three good-faith attempts gave 5.95 / 24.72 / 8.54 and **none is a working link. Even the best corrupts 18.6 % of samples** — a synchronous bus over a few cm should have essentially zero bit errors. **That scale says something is fundamentally broken in the DOUT path, not merely imperfect contact.** Stop reworking the joint.
**🔺 NEW HYPOTHESIS — pin 8 damaged by output-vs-output contention.** Until 2026-09-05, `RA8875_RESET_PIN` was **8** (changed to 5 in `eeaec99`). `Adafruit_RA8875::begin()` does `pinMode(reset, OUTPUT)` and toggles it **even when the display is absent**, because pin setup precedes the failing chip-ID check. Meanwhile the SGTL5000 was driving that same pin as DOUT — **two active drivers fighting**, across every boot while the shield was wired and the define still said 8. That could permanently degrade the Teensy's pin 8 input stage or the codec's DOUT driver, and would explain what rework cannot: three failed joints, an enormous rather than marginal error rate, wandering with conditions, and perfect clocks/registers throughout. **Hypothesis, not conclusion.**
**✅ SCOPE DONE 2026-09-07 — DOUT timing and driver both CLEAR. See journal.md 2026-09-07 (5).** Persistence view: DOUT changes at the BCLK launch edge, settles, stays stable; opposite (sampling) edge **~175–180 ns** away — a large nominal setup margin. **Full logic transitions, no weak-driver signature.** Ringing settles well before sampling, and the probe on a long lead can itself add ringing. Bench note: **scope readings never hold still**, consistent with the wandering error rate.
**❌ MY PIN-8 CONTENTION-DAMAGE HYPOTHESIS IS WEAKENED.** Damage would show reduced swing, asymmetric levels or degraded edges; none present. **"DOUT arrives too late" is also dropped** — setup margin is large. The contention timeline stays on record but the electrical signature is absent.
**✅ Continuity exhausted as a test** — every shield→Teensy pin passes. DC continuity says nothing about edge quality, intermittent contact under operation, or crosstalk.
**🔺 NEW LEADING SUSPECT — flying-lead interconnect geometry.** Photo shows long, loosely routed shield↔Teensy leads. Large loop area, no controlled return path, mutual coupling, inconsistent geometry. **This reframes the three-rework result (5.95 / 24.72 / 8.54): each rework changed wire length and routing, hence coupling and reflections — not joint quality.** That explains why three good-faith joints all failed.
**➡️ NEXT EXPERIMENT — power OFF, shorten the whole I²S bus.** Move the shield adjacent to the Teensy; replace jumpers for **8, 20, 21, 23 plus GND and 3.3 V** with the shortest practical wires (a few inches max); keep them tightly grouped, avoid loops. **Leave the analog breadboard alone. No firmware changes. Do not rework DOUT again.** Then repeat the identical ≥300-window run.
**Falsifiability:** given natural wandering of 2.83–9.50, only a **large** effect is interpretable. Collapse toward zero supports the hypothesis; a modest halving does not.
**(superseded) scope DOUT for LEVELS and EDGES —** Earlier work confirmed DOUT toggles (1.716 V DC average) but never examined swing or edge quality. **Compare DOUT against BCLK on the same probe and scope settings** — BCLK is Teensy-driven and known healthy, so it is the reference. Materially reduced swing, asymmetric levels, or visibly slow edges on DOUT would support the damage hypothesis and shift the remedy from remaking a wire to replacing a part.
**Confirmed again:** `AudioMemoryUsageMax` pinned at 20 in both runs (leak stays dead), and **100 % of windows in both runs read +0.0 dBFS** — re-proving the peak metric is useless here; raw outlier count carries the signal.
**📐 Methodological rule going forward:** any A/B test needs **≥100 windows per condition** to see through the fluctuation. Three dumps is nowhere near enough — that is precisely why this session produced so many confident wrong answers.

**Guardrail:** "DOUT has almost no setup-time margin" remains unproven, and this result *weakens* it — the evidence it rested on has been refuted.
**Historical note — the first attempt at this test was confounded:** Raw windows are low-level noise (±100), not the ±280 coherent square wave seen in all six prior dumps; `TF confidence: 0%`, every spot-check `---`. The tone stopped or the input wiring was disturbed when the clip was attached. **Re-run with the tone confirmed live and measured at column 30** before treating this as settled — the outlier conclusion above survives because it is measured against the noise floor, but nothing else from this round should be relied on.
**🔺 Shifted suspicion — clock/data lines, not ground.** With the full scope attached, three probe tips were also touching **LRCLK (20), BCLK (21), DOUT (8)**. A probe presents ~1 MΩ ∥ ~10 pF; on a marginal or reflective line that small capacitive load damps ringing and cleans edges. Suppression correlating with probe tips rather than ground points at **signal integrity on the clock/data jumpers**. Hypothesis, not conclusion.
**➡️ NEXT:** (1) confirm and measure the tone at column 30; (2) repeat ground-clip-only; (3) then attach **ground + one probe tip at a time** — pin 8, then 21, then 20 — and see whether any single line's capacitive load restores the clean ≈−38 dBFS state. That isolates the marginal conductor with nothing soldered.
**Still no permanent ground jumper** — this round makes that clearer, since ground alone demonstrably isn't the mechanism.
**❌ Do NOT pre-commit to a remedy.** An earlier version proposed "add a second solid ground bond" if the test fails — premature, because it presupposes which connection is marginal, and adding redundancy would likely mask the defect again while leaving it unidentified. **If corruption returns, prove exactly which connection is at fault first.**
**Two open questions from the clean data:** (a) level is **~28 dB below prediction** (−38.9 dBFS measured vs ≈−10.4 expected for 0.143 V<sub>rms</sub> at `LINE_IN_LEVEL 5`) — re-measure at the buffer output before any calibration; (b) **RETURN reads −50 dBFS with nothing connected**, ~11 dB below SOURCE and tracking the same waveform — quantify this crosstalk before it contaminates a transfer-function measurement.
**❌ CORRECTION (2026-09-05):** an earlier version of this item claimed the I2S lines were never wired. **That was wrong — it was written from stale context.** The interconnect **is** physically wired and verified: **18→18, 19→19, 23→23, 21→21, 20→20, 8→8, 7→7**, plus power and ground. **Do not re-wire it and do not change the existing shield wiring.** The "floating RX_DATA0" hypothesis is void: pin 8 is connected.
**Why this is still wrong:** both nodes sit at `+0.0 dBFS` with continuous `CLIP_SOURCE`/`CLIP_RETURN`, and the TF is flat at 100 % confidence. The analog input is presently ~**0.143 V<sub>rms</sub>**, and `SGTL5000_LINE_IN_LEVEL` is **5** — the library default, **1.33 V<sub>pp</sub> full scale**. 0.143 V<sub>rms</sub> = 0.404 V<sub>pp</sub> ⇒ a legitimate reading would be ≈ **−10.4 dBFS**, nowhere near clipping. So the gain setting does not explain it either.
**Ruled out so far:**
- *Signal generator bleeding into RETURN* — `[SigGen] Output wired to monitoring R via s_mixer_ret slot 2` looked suspicious, but the default route mutes it: `audio_capture.cpp:280` sets `s_mixer_ret.gain(2, 0.0f)`, and `signal_generator.cpp:331/335` initialise amplitude to 0.0.
- *Codec input misconfigured* — `audio_capture.cpp:350` calls `inputSelect(AUDIO_INPUT_LINEIN)` correctly.
- *Display interference / timing starvation* — fixed and verified (TODO-25); the readings are unchanged by it.
**Where the peaks come from:** `s_peak_src` and `s_peak_ret` sit after the channel-select mixers (`audio_capture.cpp:150`), with the active route `SOURCE_NODE=L, RETURN_NODE=R`. So these are the I2S L and R channels directly. **Both reading exactly full scale points at the I2S/codec data path, not the analog front end.**
**Leading hypotheses now:** (a) an I2S clock problem despite the wires being present — e.g. BCLK/LRCLK (21/20) transposed, or a marginal joint on MCLK (23); the codec answering on I2C proves nothing about the I2S bus. (b) the codec's ADC not clocking properly and emitting a stuck pattern.
**✅ TEST RUN 2026-09-05 — RESULT IS DECISIVE. Fault is in the codec/I2S path; the analog front end is exonerated.** With `48e`→LINE-IN-L physically disconnected and everything else live: `SOURCE_NODE peak: +0.0 dBFS` **unchanged**, `RETURN_NODE peak: -1.1 dBFS`, both still clipping continuously. **SOURCE stays pegged at full scale with no analog signal reaching the codec at all.** See journal.md 2026-09-05 (12).
**Three facts — but #1 was wrong and is withdrawn:**
1. ~~**The transport works.**~~ **❌ WITHDRAWN (see journal 2026-09-05 (13)).** The claim was that a correct block rate proves I2S is delivering samples. It doesn't. `audio_capture.cpp:85` uses **`AudioInputI2S`**, not the slave variant, so **the Teensy is I2S master** — it generates MCLK/BCLK/LRCLK and clocks samples in on its own schedule regardless of whether the codec drives DOUT. An open pin 8 still produces blocks at exactly the right rate, full of whatever the floating pin reads. The 46.3 ms figure confirms only the Teensy's own clock generation. **It rules out nothing on the codec side.**
2. **Values move, so nothing is stuck.** RETURN shifted `+0.0` → `-1.1 dBFS` when the wire came out. A latched all-ones pattern would sit at exactly 0.0 forever. This is saturated garbage, not a frozen register.
3. **⚠️ Disconnecting the LEFT input changed the RIGHT channel.** SOURCE=L, RETURN=R. Pulling L moved RETURN by 1.1 dB. **The channels are not independent** — in a correctly framed I2S stream they would be. This is the most diagnostic fact available.
**Tried 2026-09-05, no change:** BCLK wire (21) redone; shield confirmed **Rev D** (so pin-for-pin wiring is correct and the Rev C theory is dead); LINE-IN-L reconnected. Readings identical — both nodes `+0.0 dBFS`, still clipping.
**🔺 Leading hypothesis now: DOUT (pin 8) is not electrically delivering data** — wired, but possibly a cold joint, or the codec isn't driving it. An open DOUT reads as garbage at full amplitude on both channels, which is exactly the observation, and the withdrawal of fact #1 above removes the reason this was ruled out. The frame-alignment theory is weakened too: "disconnecting L moved R by 1.1 dB" is equally explained by noise on a floating pin, without needing misalignment.
**Continuity tested 2026-09-05: all seven wires good.** Wiring is no longer a credible suspect — but continuity proves the wires *connect*, not that a *clock is running on them*.
**➡️ NEXT TEST — DMM in DC volts on the clock lines, powered and running.** A DMM reads the time-average of a square wave, so a healthy ~50 %-duty clock on 3.3 V measures ≈**1.6–1.7 V**; a stuck line reads **0 V or 3.3 V**. No scope, no code:

| Pin | Signal | Healthy (DC avg) | Fault |
|---|---|---|---|
| **23** | MCLK ~11.29 MHz | ~1.6 V | 0 V / 3.3 V ⇒ no clock |
| **21** | BCLK ~1.41 MHz | ~1.6 V | 0 V / 3.3 V ⇒ no clock |
| **20** | LRCLK 44.1 kHz | ~1.6 V | 0 V / 3.3 V ⇒ no clock |
| **8** | DOUT (codec→Teensy) | mid-ish, varies | pinned 3.3 V / 0 V ⇒ codec not driving real data |
| **7** | DIN (Teensy→codec) | varies | — |

**✅ RAW SAMPLES CAPTURED 2026-09-05 — the stream is systematically corrupted.** Four dumps over 150 s, 1 kHz tone connected. No 1 kHz progression ever appears in 256 samples; stable negative DC baseline (all-sample median **−3042**, IQR −3781…−2853); recurring discrete levels ≈−2880 / −6530 / −8480; burst corruption against quiet runs (dump 4 held 11–12 consecutive samples within ±100 of −2880); dump 2 RETURN contains exactly **32767**, which is what pins the peak meter at +0.0 dBFS. Both channels structurally identical. Full data in journal.md 2026-09-05 (16).
**Bounded conclusion:** corruption exists in the raw `int16` samples **before** any FFT/peak/mixer arithmetic — not a level problem, not an interpretation problem. **The external analog front end is strongly ruled out as the cause of this symptom** — *not* fully exonerated, since the SGTL5000's own ADC and input circuitry are still upstream of these samples and codec conversion has not been separated from I2S transport.
**✅ STATIC I2S FORMAT COMPARISON — CLEAN NEGATIVE.** Read from the library sources this build compiles. SGTL5000 (`control_sgtl5000.cpp:580`, slave branch via `enable(0)`): `CHIP_I2S_CTRL=0x0030` ⇒ 64 Fs, slave, rising edge, 16-bit, **LRALIGN=0 (1-SCLK delay = I2S)**. Teensy SAI1 RX (`output_i2s.cpp:471-476`): FRSZ=1, SYWD=31, MF, **FSE (frame sync early = the 1-bit delay)**, FSP, FSD, W0W=WNW=31, FBT=31, BCP (rising edge). The 16-vs-32-bit difference is not a mismatch — `input_i2s.cpp:73` reads `&I2S1_RDR0 + 2` with 16-bit DMA, taking the upper half-word where an MSB-first 16-bit sample lands.
**Word this precisely:** the *static configuration mismatch* hypothesis is substantially ruled out — both ends are the stock 44.1 kHz / 64-Fs / 16-bit-in-32-bit-slot arrangement with matching roles, polarity, edge and alignment. **Do NOT record this as "I2S is correct"** — the runtime electrical bus can still be wrong while both register configurations agree.
**➡️ NEXT: scope the bus, no more firmware changes.** OWON HDS272S, **LRCLK first** (pin 20) — slowest clock, cleanest sanity check. Ground on top-blue GND, DC coupling, ~1 V/div, ~10 µs/div. Expect 0–3.3 V square at ≈44.1 kHz, one cycle ≈ **22.7 µs**. Record frequency/period, high/low levels, and whether it is clean and repetitive before moving to BCLK.
**🧹 Cleanup owed:** the temporary periodic RAWDUMP block in `audio_capture.cpp` is uncommitted and currently flashed. Remove it once this is answered.

**🔺 MCLK (23) was the prime suspect before the format read —** superseded, but retained: `AudioControlSGTL5000::enable()` writes `CHIP_CLK_CTRL` for 256×Fs — the codec expects an **externally supplied MCLK** to clock its ADC. **I2C configuration succeeds regardless of MCLK**, which is exactly why `enable()` returned true and told us nothing. If MCLK is absent or wrong, the ADC has no valid conversion clock and its I2S output is meaningless — while every other check we have run still passes. That single condition explains every observation.
**Correct reading to expect once fixed:** ≈ **−10.4 dBFS** for the present 0.143 V<sub>rms</sub> input at `LINE_IN_LEVEL 5`.
**⚠️ Until this is done, no number from the firmware is a measurement.** SOURCE_NODE at +0.0 dBFS is *not* evidence the analog buffer works; it is evidence the digital path is untrustworthy. Do not read the current diagnostics as validating or condemning the front end.
**Proof:** RETURN_NODE reads near the noise floor with nothing connected, and SOURCE_NODE tracks the injected signal level rather than sitting at full scale.

### TODO-24 — Pin 8 collision: RA8875 reset vs I2S RX_DATA0 🟢 **NO LONGER A PRODUCT BLOCKER — ADR-001 demoted the RA8875 (2026-09-11)**
**Status 2026-09-11:** the config fix stands and the engineering record below is
kept in full — it is the most instructive debugging narrative in this project and
the reason pins 0/1 were protected for the Pi link in the first place. But under
[ADR-001](../docs/adr/ADR-001-display-architecture.md) the RA8875 is debug hardware,
so `RA8875_RESET_PIN` is only claimed when `DISPLAY_TARGET == DISPLAY_TARGET_RA8875`.
**The physical rewire is now required only if you deliberately select the RA8875
debug backend with the panel mounted** — not for the production build, and not for
any Phase 5–9 bench work (use `DISPLAY_TARGET_NONE`).
**The boot-order concern is closed separately and was already false:**
`displayEngine_init()` failure has not halted boot since the TODO-25 work — the
`.ino` logs a warning and continues, and `display_engine.cpp` guards all six entry
points on `s_display_ok`. `presentation_init()` now carries that non-fatal contract
explicitly for every backend, so no future renderer can reintroduce the dependency.
**Original entry (retained):** 🟡 config fixed 2026-09-05 (8→5, compile-verified); rewire + boot-order halt still outstanding
**✅ Done:** `config.h:79` now `#define RA8875_RESET_PIN 5`, with an inline warning against reverting. Compiles clean for `teensy:avr:teensy41`. One line sufficed — the pin is referenced only via the macro (`display_engine.cpp:36` and `:440`), no hardcoded 8s anywhere.
**🔴 Still outstanding:** (a) physical rewire of the display reset to pin 5 when the RA8875 is actually mounted — no wiring changed yet, by instruction; (b) **the boot-order halt is a separate blocker and is NOT fixed** — see below. Moving the pin does not by itself let the SOURCE_NODE test run.
**Why:** `config.h:79` sets `#define RA8875_RESET_PIN 8`, passed to `Adafruit_RA8875 tft(...)` at `display_engine.cpp:36`. **Pin 8 is I2S RX_DATA0 on Teensy 4.x** — the line carrying line-in audio *into* the Teensy. Verified from the Audio library source, `input_i2s.cpp:222` (`__IMXRT1062__` branch), not from memory. Whichever initialises last wins the mux: display wins ⇒ no audio input at all; `AudioInputI2S` wins ⇒ the display's reset line is driven by I2S data.
**Verified Teensy 4.x shield interconnect** (Phase 4 never specifies this — runbook gap #3): TX 7 · **RX 8** · LRCLK 20 · BCLK 21 · MCLK 23 · SDA 18 · SCL 19 · 3.3 V · GND. The shield runs on **3.3 V, not 5 V**. Any pin list omitting **8** guarantees a silent SOURCE_NODE.
**Compounding blocker:** [guitar_rig_analyzer.ino:197](guitar_rig_analyzer.ino#L197) calls `displayEngine_init()` *before* `audioCap_init()` and halts forever on failure. The RA8875 isn't on the bench, so the firmware halts before audio initialises — **and this masks the pin conflict**, since you never reach the code that would expose it.
**What:** (a) *Bring-up:* make display init non-fatal or skip it — reaches `audioCap_init()` and sidesteps the pin conflict, since the library then never claims pin 8. (b) *Product fix:* move `RA8875_RESET_PIN` off pin 8 permanently. Free pins: **2, 3, 4, 5** — 0/1 are `Serial1` (`data_sender`), 6 is the shield's MEMCS and best avoided, 9–24 all allocated. **Pin 5 recommended.** Needs the config change *and* a rewire when the display is mounted.
**Not a problem:** `RA8875_CS_PIN` 10 also being the shield's SDCS — `calibration_store.cpp:404` uses `SD.begin(BUILTIN_SDCARD)` (the Teensy's own slot), so the shield's SD is unused. **Leave the shield's SD socket empty.**
**Proof:** with the display present and audio running together, `audioCap_init()` succeeds and SOURCE_NODE shows signal while the display renders — the two coexisting is the whole point.

### TODO-18 — Fix the runbook: Phase 4 unplugs USB and never restores it 🔴 **HIGH — confirmed cause of a two-day debugging detour**
**Why:** `docs/breadboard_bringup_v3.md` § Phase 4 (lines 848–1056) contains exactly one power instruction — line 884, "**1. Unplug USB.**" There is no upload step and no reconnect instruction anywhere in the phase. Its End-of-phase verify (line 1027+) then demands five live DMM readings (+5 V pin 8, <0.05 V pin 4, 2.45–2.55 V pins 3/1, <50 mV at `48e`), all of which need the board powered. **Following Phase 4 exactly as written leaves you measuring an unpowered board.** Worth fixing on its own merits — it will mislead someone eventually.
**Confirmed 2026-09-05 — this WAS the cause.** The 0 V rail was an unpowered board; USB was not plugged in. Correctly diagnosed on 2026-09-03, wrongly withdrawn on a mistaken report that power had been connected, now reinstated. **Cost of this one missing line: ~two days of bench debugging across two AI sessions, two false hardware hypotheses, and a nearly-replaced healthy op-amp.** Treat as high priority, not cosmetic.
**Also fix while in Phase 4:** the invalid common-mode operating point (TODO-21). The phase carries two independent defects.
**Phase 4 is the only phase with this gap** — Phase 1 says "Plug in USB"; Phase 2 restores power implicitly via `arduino-cli upload`; Phase 3 asserts "Make sure USB is plugged in and the firmware is running." Phase 4 removes power and never brings it back.
**What:** Insert an explicit "Reconnect USB" step between Step 13 and the End-of-phase verify. While there, audit Phases 5–9 for the same unplug-without-restore pattern (Phase 5 also opens with "Unplug USB" — confirm it restores power before its own verify).
**Proof:** Phase 4 read end-to-end contains an explicit power-restore step ahead of its first live measurement, and no other phase demands a live reading without a preceding powered state.

### TODO-31 (D5) — Runbook rail-bridge contradiction: followed literally, the instructions short +5 V to VGND 🔴 **documentation defect, adjacent to TODO-18 — not a hardware fault**
**Why:** `docs/breadboard_bringup_v3.md` Phase 0 Step 5 (line 262) instructs bridging **top-red ↔ bottom-red** at columns 1 and 60. Phase 1 Step 7 (line ~627) then **re-purposes bottom-red as VGND** ("This *re-purposes the bottom-red rail as VGND.*"). Nothing between them says to remove or revise the earlier red bridges. **Followed literally and in order, the runbook connects +5 V to VGND.**
**This is a defect in the instructions, not a claim about the board.** Whatever the bench actually has, the runbook cannot be followed as written. Same class as TODO-18 (Phase 4 unplugs USB and never restores it): a step sequence that is individually sensible and collectively wrong, and it will mislead whoever next uses the document for reconstruction.
**Surfaced 2026-09-07** during the `docs/asbuilt/netlist.md` audit; named D5 by the photo-owning session (`0476826b`). See journal.md 2026-09-07 (7)/(8) era and the audit exchange.
**What:** Audit and correct the Phase 0 → Phase 1 sequence. Either Step 5 should bridge GND only, or Step 7 must explicitly instruct removing the red bridges before bottom-red becomes VGND. **Do this before the runbook is used for any reconstruction.** While there, audit whether any other phase re-purposes a rail that an earlier phase bonded.
**Proof:** Phase 0 → Phase 1 read end-to-end never places +5 V and VGND on the same net at any point in the sequence.
**✅ The defect was NOT built — confirmed 2026-09-07 by direct visual inspection** (`docs/asbuilt/netlist.md` §6b): no red conductor bridges `TOP_RED`↔`BOT_RED` at either end; only the yellow GND bridges are fitted. VGND is intact and the col-45 divider works as intended. **So this is purely a documentation fix with no hardware implication** — but it is still a live trap for anyone who follows the runbook as written.
**Not blocking:** no bench action required. The as-built bridge status is closed in TODO-20.

### TODO-19 — Decide C1 input coupling cap value before trusting any low-frequency measurement 🔴 low priority, but a correctness trap
**Why:** C1 = 10 nF gives a high-pass corner of ~160 Hz — *above* the low-E fundamental at 82 Hz. The runbook's own Phase 4 Background flags this and suggests 0.1 µF ceramic (20 on hand) for a ~16 Hz corner. Left as-is, low-frequency rolloff will look like a fault or, worse, be silently accepted as real rig response.
**What:** Keep 10 nF for topology validation. Before any bass-inclusive measurement, either swap to 0.1 µF or explicitly document the 160 Hz floor as a known measurement limit.
**Proof:** either the swap is made and a sub-100 Hz tone passes at expected level, or the 160 Hz corner is recorded as a stated limitation everywhere results are reported. Interacts with TODO-4's note that Test 1's pass band starts at 200 Hz.
**The corner has never actually been measured** — TODO-4's 1 kHz reading is *consistent with* 159 Hz but constrains it only to ~125–205 Hz, since a high-pass probed 6× above its corner barely moves. **Run one frequency sweep and use it for both purposes:** readings at ~40, 80, 159, 320, 640 Hz, checking for −3 dB at the corner and a 6 dB/octave slope below it. That measures the real corner *and* supplies this item's decision evidence in a single pass.

### TODO-20 — Backfill Phase 1's verify numbers — it PASSED, but predates this journal 🔴 record-keeping gap, not a build gap
**Why:** Phase 1 passed and the +5 V rail worked — confirmed by Conley 2026-09-03. It has no journal entry only because the journal was created *after* Phase 1 was completed, and no TODO item because Track A's numbering starts at TODO-1 (compile blocker) / TODO-2 (Phase 2). **This is an artifact of when record-keeping started, not evidence of an unverified build** — an earlier draft of TODO-4 wrongly inferred the latter. Corrected here so no future session re-derives that mistake.
**What:** Log Phase 1's end-of-phase results retroactively if the numbers can be recalled or re-measured: +5 V rail 4.85–5.10 V; VGND 2.40–2.60 V; VGND midpoint symmetry within 0.05 V; GND continuity top-blue↔bottom-blue; **no** top-red↔top-blue short. Note Step 2 (line 561) sources 5 V from the **`VUSB` pad**, not VIN — see TODO-4.
**Proof:** Phase 1's five checks present in journal.md with values, so the evidence chain from Phase 1 forward is continuous and the "last known-good state" is documented rather than reconstructed from memory.
**🔺 2026-09-07 — the power-isolation criterion above is the same question as the as-built audit's GAP-7. Merged here rather than tracked twice.** This item already carried "**no** top-red↔top-blue short" as a Phase 1 sign-off check, and **that check was never evidenced.** The `docs/asbuilt/netlist.md` audit re-derived the same gap independently from the runbook (see TODO-31/D5), which is what surfaced the overlap.
**What the record does and does not establish:**
- **Retrospective evidence, 2026-09-05:** the VGND rail measured **2.480 V** with the op-amp removed (journal.md 2026-09-05 (1), journal.md:1335). A fitted top-red↔bottom-red bridge would have put VGND at ~5 V. **That reading therefore demonstrates no +5 V/VGND bridge existed at the time of the measurement** — it retrospectively satisfies the Phase 1 criterion for that date. Historical `MEAS`.
- **It does not establish the current as-built state.** The OPA_BIAS rework happened later the same day (journal 2026-09-05 (3)–(5)), so rail wiring could in principle have changed after that reading. Treat 2.480 V as historical evidence, not as proof of present physical routing.
- **Current status: awaiting photo reconciliation.** The photo-owning session (`0476826b`) has been asked a photo-only question — whether any **red** conductor bridges top-red↔bottom-red at columns ~1 or ~60 — with the known yellow GND bridges explicitly excluded as evidence either way. **No bench measurement is authorised for this**; if the photographs cannot resolve it, the correct answer is unverified.
**✅ CLOSED 2026-09-07 by direct visual inspection — no red bridges fitted** (`docs/asbuilt/netlist.md` §6b). `PHYS`. The Phase 1 power-isolation criterion is now evidenced, four weeks late, by observation rather than by the retrospective 2.480 V argument.
**The 2.480 V reading is demoted to a historical consistency check**, exactly as scoped above — it falsified a bridge on 2026-09-05 and was never proof of the present state. It was right, and it was still the wrong thing to close on.
**Method note worth keeping:** this gap stayed open through two failed photographic passes and closed only on a directed look at the board. Photographs proved sufficient for topology, component identity and interconnect geometry, and insufficient for one specific class of question — **which of two adjacent rail rows a conductor lands in.** Same limitation closed GAP-1. Budget a physical look for rail-row questions; do not expect a photo set to answer them.
**Still open in this item:** the other four Phase 1 numbers (+5 V rail, VGND value, divider symmetry, GND continuity) remain unlogged.
**Broader lesson worth keeping:** the journal starting mid-build means **the earliest phases have a silent evidence gap**. When reasoning about regressions, "no record" here does not mean "never tested" for anything at or before Phase 1.

### TODO-5 — Phase 5: First real instrument jack (Switchcraft #11) 🟡 **RE-SCOPED 2026-09-13 — jack detection REMOVED from acceptance. Keep the #11. Buy nothing. Remaining work is measurement, not construction**
**📐 GOVERNED BY [ADR-003](../docs/adr/ADR-003-jack-presence-is-a-ux-feature.md).** Jack presence detection is a **UX/automation feature, not a hardware requirement.** Repo trace: `s_jack_instrument.debounced` gates **nothing** — absent from `computeReturnSource()`, `route_valid`, `can_inject`, `buildDescription()` and `applyReturnRelay()`. Its only consumer is `data_sender.cpp:603` (a UI bit), reached via `presentation_routerStatus()`, which is **never called**. `canMeasure()`/`canInject()` are never called either. **Pin 16 currently feeds nothing at all.**
**✅ REVISED ACCEPTANCE CRITERION — replaces *"detect events fire"*:**
> **PASS:** A standard 1/4" TS guitar connected to Instrument In passes cleanly through the intended analog signal path with normal level and no unintended loading, distortion, oscillation, or loss of signal.
**🔺 CONSEQUENCE OF THE RE-SCOPE — TODO-23 and TODO-32 are now IN Phase 5's critical path, not beside it.** The old criterion was about a GPIO toggling. The new one is about **signal quality**, and *"no unintended loading"* is precisely TODO-23's subject: the input bias resistor is ~100 kΩ against a 6–250 kΩ pickup, where standard guitar-amp input is ~1 MΩ. **TODO-23's proof line and this criterion are effectively the same test** — *"a guitar shows no audible/measurable high-frequency loss versus the same guitar into a known 1 MΩ amp input."* And **TODO-32 gates TODO-23**, because R5 **is** the input impedance and its value has never been measured (`netlist.md` carries it as `DERIV`, which that item argues should be `INF`).
**So Phase 5 may legitimately FAIL its new criterion on loading grounds** — that would be a real result about the analog front end, not a regression. Sequence R5-measurement → impedance decision → guitar test, rather than discovering it as a surprise.
**The #11 is electrically correct for a TS guitar and is not failing at its job.** It had been assigned a second job — mechanical presence detection — that the product does not need. **Do NOT buy a 12A. Do NOT replace the #11.** Pin 16 may stay implemented; its state is **informational and non-authoritative**.
**`b32d04a` stays in the tree unchanged.** The router runs, reads four pins, gates nothing. It is the framework the Phase 7 decision will be made in; removing it would cost work now and again later.
**⚠️ Not a workaround — a requirements correction.** The old criterion was written believing the #11 had a switch contact. It does not (bench DMM + Switchcraft's own *"Open circuit"* designation). ADR-002 remains in force for *how* detection may be built if Phase 7 decides it is needed.
**Everything below predates the re-scope and is retained per the never-delete rule.**
**🔻 SUPERSEDING FINDING 2026-09-13 — read this before anything else in this item.** Bench continuity (power off, DMM) identified J4 as a **two-terminal open-circuit jack**: lug #1 = SLEEVE/GND; **lug #2 continuous with the long spring both empty AND with a TS plug inserted** — a pair that does not open is not a switch. Lug #2 and the spring are two parts of the TIP conductor. **There is no SHUNT terminal.** Evidence: `ai/evidence/2026-09-13-J4-continuity-identification.md`, journal **2026-09-13 (9)**.
**🚫 DO NOT connect Teensy pin 16 to lug #2 or the long spring.** Both are the guitar TIP. `INPUT_PULLUP` would put a 22 kΩ pull-up to 3.3 V directly on the instrument signal node. **The SHUNT → pin 16 experiment is WITHDRAWN — it cannot be performed.**
**🔴 This is a PARTS blocker, not wiring and not firmware.** Runbook line 181 specifies Switchcraft #11 ×10 for **Phase 5 AND Phase 7** (instrument in, rig send, rig return TS). If the installed part is representative of all ten, **no 1/4" jack in the design can report presence**, so Phase 5's *"detect events fire"* and Phase 7's route matrix are both blocked. Relayed, not verified here: Switchcraft lists the **#11** as *2 Conductor, Open Circuit*; the shunted variant is a different part number (e.g. **12AW11**, *"Tip is Shunt"*).
**✅ Phase 8 is unaffected and is already ADR-002-compliant** — its XLR detect uses a **separate COM-NC lever microswitch** wired pin 24 → GND (runbook ~line 1638), an independent contact that never touches an audio node, with ~0 Ω to ground. **An ADR-002-compliant pattern already exists in this project's own runbook.** Observation, not a selection.
**✅ DECISION MADE 2026-09-13 (breadboard prototype scope):** keep the #11 as the audio jack; detect presence with an **independent Omron D2F-01L COM–NC lever microswitch** — the element already designed into Phase 8. Likely standardised across all three 1/4" positions. **Do not replace the #11s; do not sense their TIP nodes.** Journal **2026-09-13 (10)**.
**Firmware needs NO change.** `COM → pin 16` (INPUT_PULLUP) + `NC → GND`: released ⇒ raw LOW ⇒ `present=0`; pressed ⇒ raw HIGH ⇒ `present=1`, with `JACK_INSTRUMENT_DETECT_INVERTED` already **1**. `b32d04a` as running on the board is correct for this topology.
**ADR-002 compliance is maximal, not marginal:** detect path is `pin 16 → COM → NC → GND` and never touches an audio node — zero DC loading on the guitar input. ~0 Ω closed-contact against the < 9.4 kΩ bound.
**🔴 PARTS GATE — ASSUME D2F-01L ON HAND = 0. The bench proof below is BLOCKED on parts.** The D2F-01L appears exactly once in the repo: `breadboard_bringup_v3.md` line 1583, inside the Phase 8 **design figure**. That is evidence it was *planned*, not *purchased*. The purchased list is *"3× Switchcraft #11, 1× Neutrik XLR"* — no microswitch of any kind. **Standardising 3× 1/4" + XLR needs four units; four must be bought, not three.**
**🔻 CORRECTION — an earlier version of this item said "one is enough, nothing blocks the next step." That was wrong** and contradicted the sentence beside it: a part drawn in a design figure is not a part in a bin. See journal **2026-09-13 (11)**.
**NEXT — electrical proof BEFORE mechanical integration. Do not mount the switch.**
1. Power OFF. Continuity-identify COM/NC: lever untouched ⇒ COM↔NC beeps; depressed ⇒ beep stops. Ignore NO. *(Runbook line 2002 admits it has no macro photo of the D2F-01L terminals — electrical ID is the correct method.)*
2. Two temporary connections only: `pin 16 → COM`, `GND → NC`. **Nothing connects to J4.** Audio path untouched.
3. Power up, lever released ⇒ expect `raw=LOW inv=1 present=0`. Press ⇒ expect `JACK_CHANGED`, `raw=HIGH inv=1 present=1`. Release ⇒ back to LOW / `present=0`.
**⚠️ A passing hand-press does NOT close Phase 5.** Mechanical actuation by an inserted TS plug is part of the feature. Sign-off still requires plug insertion to drive the transition. Mounting the lever so a TS plug reliably presses it is **deferred, not solved — and is the harder half.**
**Root cause of the wasted branch:** the runbook's SVG at lines 1105–1113 draws a SWITCH terminal, and that component description was accepted as as-built fact. **A document describing what a part does is not evidence that the part on the bench is that part.**
**Everything below this line predates the continuity identification and is retained unchanged per the never-delete rule. The firmware status remains accurate; the SHUNT topology reasoning does not describe the installed jack.**
**📐 GOVERNED BY [ADR-002](../docs/adr/ADR-002-jack-presence-detection.md).** The permanent jack-detect implementation must satisfy ADR-002: *jack presence sensing must be electrically independent of the high-impedance audio signal node.* The current J4 SHUNT→TIP topology is retained **only** for the controlled diagnostic-jumper experiment below and carries no implication of acceptance. ADR-002 does **not** select a replacement topology — that decision is open.
**✅ Firmware half — compile-verified, uploaded, running (`b32d04a`).** `signalRouter_init()` and `signalRouter_update()` are in the live path; per-connector polarity support present. **No evidence of firmware failure**, and none of success either — it is untestable until the hardware exists. Three of four detect inputs behave exactly as unwired pull-up inputs should.
**🔴 Electrical detect half — NOT BUILT.** Live pin 16 stayed `HIGH` through **empty → insert → remove → insert**, uptime 18–218 s, 45 windows, continuous capture, **zero `JACK_CHANGED` events**. The as-built record carries the tip signal path only — no sleeve entry, no switch-lug entry, and Teensy pin 16 appears nowhere in `docs/asbuilt/netlist.md`. The runbook requires **three** pigtail conductors (line 1129: red = tip, black = sleeve, green = switch; line 1149: SWITCH → Teensy pin 16). **One of three was built.** This is an omitted bench construction step, not a polarity calibration issue.
**🚫 DO NOT touch `JACK_INSTRUMENT_DETECT_INVERTED`.** An unwired INPUT_PULLUP pin reading HIGH is not evidence about jack polarity. Evidence: `ai/evidence/2026-09-13-phase5-detect-null-result.log`, journal **2026-09-13 (7)**.
**🔺 AND the runbook's detect design cannot work here — read journal 2026-09-13 (7) before wiring.** The #11's SWITCH lug shorts to **TIP** when empty. TIP is `col 30`, whose net is `col 30 · J4 tip · C1` with **C1 = 10 nF ceramic** (`netlist.md` line 95, `PHYS`) and no other connection — **DC blocked**. So SWITCH → pin 16 gives **HIGH when empty AND HIGH when inserted**; the pin never changes, and **no invert value can recover a transition that the hardware does not produce.** The runbook's own truth table (line 1118) says this outright and then prescribes the invert anyway, dismissing the Cliff CL1384 make-on-insertion alternative at line 1221.
**🧪 Falsifiable prediction — test it, do not assume it.** The `col 30` → GND diagnostic jumper is **currently fitted** and supplies the missing DC path. So: (1) wire SWITCH → pin 16 **with the jumper still fitted** ⇒ detect should work, empty = LOW, inserted = HIGH, shipped `INVERTED = 1` correct. (2) Remove that jumper ⇒ detect should break, pin 16 stuck HIGH. Both holding demonstrates the coupling instead of arguing it.
**⛔ CONSEQUENCE FOR DEVIATION RESTORATION:** the `col 30` → GND jumper, scheduled for removal as a diagnostic deviation, is **load-bearing for a feature that does not exist yet**. Removing it to "restore the baseline" would break detect before detect ever worked, and would look like a firmware bug. **Do not restore deviations independently of this item.**
**❗ Not claimed:** that grounding `col 30` is an acceptable production answer. It shorts the guitar signal to ground. The jumper works for detect *by accident*.
**🔺 OPTION CLOSED 2026-09-13 (8) — "a DC reference on TIP" cannot work.** `INPUT_PULLUP` on Teensy 4.x is `IOMUXC_PAD_PUS(3)` = **22 kΩ** (`cores/teensy4/digital.c:180`). To pull pin 16 below V<sub>IL</sub> ≈ 0.99 V through the SHUNT contact, R<sub>TIP→GND</sub> must be **< 9.4 kΩ** (< 42.9 kΩ even with the chip's most favourable 100 kΩ pull-up). That resistor **is** the input impedance, and TODO-23 wants ~1 MΩ. **≥23× apart in opposite directions — a contradiction, not a tuning problem.** The ~0 Ω diagnostic jumper works precisely because it is far below that bound, and nothing compatible with a guitar input ever could be.
**Surviving production options, all keeping detection OFF the audio node:** (1) isolated make-on-insertion contact (Cliff CL1384, dismissed at runbook line 1221); (2) a separate detect switch independent of the audio tip; (3) high-impedance buffered/comparator sensing. **No decision made here.**
**📐 Terminology — this jack is TS, not TRS.** Terminals are **TIP — SLEEVE — SHUNT/SWITCH**; SHUNT is normally closed to TIP and opened mechanically by a TS plug. **No ring conductor is involved anywhere in the detect scheme.** Audit 2026-09-13 found no existing error — every `ring` in `ai/` and `netlist.md` is a serial RX ring buffer or a genuine 3.5 mm TRS cable (J1 *is* TRS, so `netlist.md:313` and `:523` are correct). Preemption, not correction: do not let J1's legitimate tip/ring/sleeve leak into J4's description.
**Next bench sequence (power OFF first, one change at a time):**
1. Leave the breadboard otherwise unchanged. Power OFF.
2. Positively identify all three #11 lugs again: TIP, SLEEVE, SWITCH.
3. Verify whether SLEEVE is actually connected to system GND.
4. Verify SWITCH has no conductor yet.
5. Add **only** the missing SWITCH → pin 16 connection if sleeve grounding is already correct. If sleeve is also missing, add it as its own separately documented step.
6. Power up and test raw pin 16 empty/inserted **before** removing the existing diagnostic ground jumper.
7. Only after detect works, deal with deviation restoration — re-testing after each single change.
**Proof:** unchanged — both halves of the sign-off line. Record raw pin 16, `inv`, interpreted `present`, and the `JACK_CHANGED` line for **all four states** (boot empty, insert, remove, insert). That one session also supplies the independent observation that lifts the electrical half off `RPT`.

**✅ Detect firmware written 2026-09-13 — compile-verified, not on hardware.** Both blockers from the 2026-09-07 audit are cleared, and both were re-verified in the active tree before the edit (`signalRouter` appeared nowhere in the `.ino`; `JACK_DETECT_INVERTED` existed only in the runbook):
1. `signalRouter_init()` now called once in `setup()`; `signalRouter_update()` called every `loop()` iteration, unconditionally (debounce is time-based, so it must not be gated on audio-block availability).
2. Polarity added as **four per-connector defines**, not one global flag: `JACK_INSTRUMENT_DETECT_INVERTED 1`, the other three `0`. Only the instrument jack is built; asserting a sense convention for Phase 7/8 connectors that do not exist would be an inference recorded as a fact. Applied in exactly one place — `readJackInserted(pin, inverted)` returns `raw_present ^ inverted` — not in `pinMode`, not at call sites, not baked into debounce state.
**Scope held:** injection stays off, `s_mixer_send` is still absent, `measurement_engine` still does not call `signalRouter_canInject()`. Those are TODO-11 / Phase 6-7 and must not ride along.
**⚠️ Disclosed, not silent:** `signalRouter_init()` also sets `RELAY_SEND_PIN`/`RELAY_RETURN_PIN` to OUTPUT and drives them LOW, then calls `applyReturnRelay()`. Nothing is connected to those pins (Phase 6 unbuilt), so it is electrically inert. During an instrument-jack plug/unplug no relay write occurs at all: `applyReturnRelay()` runs only when the *return source* changes, which depends on pins 22/24, and those float to HIGH ⇒ not-inserted ⇒ source stays `NONE`. **If relay GPIO activity is unacceptable it needs a fifth change (a compile-time actuation guard) that was deliberately NOT made, to keep this patch to the four scoped items.**
**Compile evidence:** `DISPLAY_TARGET_PI`, `ENABLE_DUT_INJECTION 0` — FLASH 156 608, RAM1 218 080. `audio_capture.cpp` and `audio_engine.cpp` byte-untouched; audio graph and generator behaviour unchanged.
**🔴 BENCH TEST REQUIRED — one session closes BOTH halves of the sign-off.** With the stack powered, plug and unplug the Switchcraft #11 instrument jack and record, for **both** empty and inserted:
- raw GPIO level on pin 16, and
- interpreted `instrument present` state, and
- that a `JACK_CHANGED` event fires on each transition.
The firmware prints all three together on a `[SignalRouter] detail(...)` line at init and on every change, specifically so this evidence exists in one place. **Expected:** empty ⇒ pin 16 `LOW`, present `0`; inserted ⇒ pin 16 `HIGH`, present `1`. If that comes out reversed, `JACK_INSTRUMENT_DETECT_INVERTED` is wrong and is a one-character fix — **do not rewire the jack.**
**Why this single test is worth two:** it closes the detect half AND supplies the independent observation that upgrades the electrical half off `RPT` (builder-reported), which currently cannot support a Phase 5 sign-off on its own.

**✅ Electrical half done — builder-reported 2026-09-08.** The real 1/4" jack is installed and the path verified end to end: **guitar → 1/4" jack → col 30 → C1 → col 33 → OPA1642 → C2 → SGTL5000 LINE-IN-L**. The old J1 3.5 mm breakout is **no longer the guitar path** — any instruction routing a guitar through J1 or a 1/4"→3.5 mm adapter is stale and actively misleading. `RPT` (builder-reported; not yet photo- or continuity-confirmed by an independent pass).
**🔴 Detect-event half NOT done, and it is the harder half.** The sign-off line is *"Switchcraft #11 + invert define both work — guitar plays through, **detect events fire**."* Guitar-plays-through is now met. Detect events cannot fire, for two independent reasons verified in the active tree 2026-09-07:
1. **`signalRouter_init()` / `signalRouter_update()` are not called anywhere in `guitar_rig_analyzer.ino`.** The router has never been in the live path. This is TODO-3's deferred half and TODO-11.
2. **`JACK_DETECT_INVERTED` does not exist** in `config.h` or `signal_router.cpp`. The runbook prescribes it because the Switchcraft #11 switch is shorted-to-tip when empty and open when inserted, so the logic reads backwards without it.
Both are compile-time work. **Neither requires touching the bench.**
**⚠️ The runbook's Phase 5 repeats the TODO-18 defect.** Step 5 says "Unplug USB" and no reconnect, re-plug, power-restore or upload instruction appears anywhere in the rest of the phase. Same gap that cost two days at Phase 4. Fix before following it.
**Open measurement question raised during bring-up (2026-09-08):** SOURCE_NODE idles at **≈−31.5 dBFS** against RETURN's **≈−60.8 dBFS** on the same codec, rails and board — a ~29 dB asymmetry. Guitar volume at zero did not change it (means −31.40 → −31.48 dBFS, 0.08 dB), which weakens the pickup/cable-antenna hypothesis without eliminating cable contribution. **Localised to the SOURCE-side analog path, or specific to it — shared power/ground mechanisms are not excluded by this evidence alone.** See journal.md 2026-09-08.
**🔧 PROVISIONAL WIRING RULE — applies from Phase 5 onward, derived from measurement (journal 2026-09-12 (3)):**
> **Codec analog input returns should reference the Audio Shield ground locally. Do not route the return through the breadboard ground path until the ground-path mechanism is fully characterised.**
**Evidence:** moving only the LINE-IN-L ground return from the breadboard rail to the shield's own GND pad improved the SOURCE noise floor by **33.1 dB** (−31.9 → −65.0 dBFS), with termination impedance unchanged. **Provisional** because the 33.1 dB is measured but the mechanism — ground-potential difference vs loop-area pickup — is not yet identified, so the rule states what to do and not yet why. See TODO-40.

**Proof:** unchanged — both halves of the sign-off line, not just the first.

### TODO-6 — Phase 6: First relay driver, RELAY_SEND (TQ2-5V) 🟢 **SIGNED OFF 2026-09-16** — journal 2026-09-16 (3). As built: pin 14 → col 53 → 0.993 kΩ → B `51` · E `50` → GND · C `49` → coil− `55f` · coil+ `55a` → +5 V · 1N4148 band `55a` · 10 kΩ `51`→GND · contacts `56a` NC / `57a` COM / `58a` NO.
- **Residuals (non-blocking):** (a) 🟢 **closed by photo**: both leads land in col-55 holes; band not legible, so orientation rests on the electrical argument; relay marked TQ2-5V / ATQ209. Image: [`evidence/2026-09-16-phase6-flyback-diode-seated.jpg`](evidence/2026-09-16-phase6-flyback-diode-seated.jpg) + `.md`. *(was:)* **photo** of the reseated 1N4148 with both legs seated (reseat was confirmed only by "done"; an in-circuit diode check is masked by the coil). (b) 🟢 **closed**: `?` read back over serial, help list has no `p=` line, so the cleaned build is running. (c) 🟢 **closed**: the removed original relay also reads **TQ2-5V** (builder report). No latching part was ever in this investigation.
- **V6c — 🟢 `55a` = +5 V (pin 1), `55f` = collector (pin 10).** *(was:)* record the as-built coil wiring. Which jumper now goes to `55a` (should be +5 V / pin 1) and which to `55f` (should be collector / pin 10)? The fix was made in a bench-chat turn and is not written down.
- **V6d — 🟢 0.602 V out of circuit, band at `55a`, non-band leg reseated in `55f`.** Post-fix saturation re-measured: **129.1 mV**. *(was:)* diode after the fix. 1N4148 band must be on the **+5 V node** (`55a` if the rails were swapped), ~0.65 V band→non-band in diode mode, USB unplugged. The working relay rules out a *forward* diode, but a missing or unseated one would pass silently and let the BJT take the turn-off spike.
- **V6e — 🟢 uploaded and read back from the board (no `p=` in the help output).** *(was:)* flash the cleaned build. The `[PHASE6-TEMP]` handler has been removed and the build compiles (FLASH code 156 608 B). The board still runs the build with `p`.
- **V6f — 🟢 8.94 kΩ in circuit** (base strip → GND). Confirms presence; the parallel paths explain the low reading.
*(Header before 2026-09-16: 🟡 HALTED MID-BUILD 2026-09-15 — runbook coordinate collision.)*

**🛑 DO NOT FIT the runbook's `45a` → Teensy pin 14 jumper (Phase 6 step 4), and do not power up with it fitted.** Column 45 A–E is **VGND**, not a free column — see journal.md 2026-09-15 (1).

**The collision.** [`docs/asbuilt/netlist.md`](../docs/asbuilt/netlist.md) records at `PHYS`: R3 10 kΩ `TOP_GND`→`45a`, R4 10 kΩ `TOP_RED`→`45b`, grey jumper `45c`→`BOT_RED`, and the VGND net as `BOT_RED · 45c · col 45 A–E · C7+ · C8+`. R3/R4 are the "two resistors at column 45" seen at the bench. Runbook Phase 6 steps 3–4 (L1269–1271) call `45a` "a free column"; **R3 is already in that exact hole.** Root cause is netlist deviation **D3** (divider relocated col 15 → col 45, assessed "pure relocation") whose downstream consequence was never traced — TODO-46.

**Why step 4 specifically is hazardous.** It is a direct, unresistored 3.3 V push-pull GPIO onto the analog reference rail. [`config.h:243`](../config.h#L243) `RELAY_SEND_PIN 14`; [`signal_router.cpp:202-204`](../signal_router.cpp#L202) `signalRouter_init()` drives pin 14 **LOW at boot**; [`signal_router.cpp:375`](../signal_router.cpp#L375) drives it HIGH on `p`. With that jumper fitted, first power-up clamps VGND to 0 V and dumps C8 (10 µF at 2.5 V) into the pin.
**Bounded by two recorded facts, not by assumption:** netlist **D4** — "VGND is alive but unloaded, nothing on the board uses it" — so the Phase 4/5 analog path (biased from OPA_BIAS, not VGND) was never exposed; and netlist §1 `TOP_RED ↔ BOT_RED bridged? **No.**` at `PHYS`, so col 45 sits at 2.5 V and the non-5V-tolerant Teensy pin was never over-volted. **⚠️ If the Phase 0 step 5 bridges that deviation D5 warns about are ever fitted, `BOT_RED` becomes +5 V and this jumper destroys pin 14 instantly.** D3 and D5 are individually survivable and jointly destructive.

**Bench state as found (2026-09-15).** Continuity through the new 1 kΩ base resistor reads from the column-51 side but not to column 45 — *consistent with* that leg never having seated in a col-45 hole, i.e. the hazardous connection likely never completed. **Not proof** — the same reading comes from a leg in the wrong strip. V1 settles it. (A 1 kΩ resistor will not beep in continuity mode on most meters; use resistance mode, strip to strip.)

**✅ RESOLVED 2026-09-15 — transistor orientation is `49` = Collector, `50` = Emitter, `51` = Base.** The adapter is on the runbook's columns (49/50/51); it is the **pin order** the runbook gets wrong. My earlier guess in this item — that the adapter had shifted right to 50/51/52 — was wrong and is superseded. **The centre pin is the EMITTER, not the Base**, which is correct for an MMBT3904 in SOT-23 (pin 1 = B, pin 2 = E, pin 3 = C — the collector is the lone pin on its side of the package). Runbook step 2's "silkscreen reads **E – B – C**" is therefore impossible for this part, and it contradicts the runbook's own Phase 0.5 L504 ("note the **C / B / E** silkscreen markings"). Bench evidence below is self-consistent with C/E/B and with nothing else. **Step 6's "jumper from `49a` (Emitter strip) to GND" must move to column 50.**

**Verification sequence — in order, USB unplugged throughout:**
- **V1 — prove column 45 is untouched by Phase 6 work.** 🟢 **CLOSED 2026-09-15 — `BOT_RED` (VGND) → GND = 2.495 V.** Half-supply, undisturbed: the col-45/pin-14 collision is not built and nothing is clamping the rail. Earlier reasoning retained below.
  - *(superseded detail)* Base-drive node measured **0.5 mV** with USB plugged in, confirming pin 14 boots LOW and nothing drives that node — see [signal_router.cpp:202-204](../signal_router.cpp#L202). **Still outstanding, and now a one-probe check while powered: `BOT_RED` → GND must read ≈ 2.50 V.** If the col-45 collision were built and live, pin 14 would be clamping VGND and `BOT_RED` would read near 0 V. Until that number is recorded, "0.5 mV somewhere" does not distinguish *"the node is safely undriven"* from *"VGND is being held down."*
- **V2 — establish the transistor's real columns.** 🟢 **CLOSED 2026-09-15 — C=`49`, E=`50`, B=`51`.** Evidence, USB plugged in, black probe on `TOP_GND`: pin 14 = 0.5 mV (BJT off) · **collector `49` = 4.99 V** (pulled up through the coil — proves 49 is the node tied to coil−, and that the device is off) · **coil+ `55f` = 4.99 V**. Both coil ends at rail = correctly de-energised, 0 V across the coil.
- **V2a — 🟢 CLOSED 2026-09-15 — cathode band confirmed at `55f` (COIL +, rail side).** The destructive-on-first-actuation case is ruled out. Reasoning retained because it generalises: *(superseded gate)* The V2 readings **cannot** detect a reversed 1N4148: with the BJT off there is ~0 V across the coil, so a backwards diode passes nothing and reads identically to a correct one. It is only tested at the instant the transistor saturates — and it fails destructively. The runbook's own step 10 says it: *"Reversed: the diode shorts +5V to GND through the BJT whenever pin 14 goes HIGH."* That short is limited only by the diode and the BJT (rated 200 mA), it would take out both, and it browns out the +5 V rail that feeds the Teensy carrier and the Audio Shield. **Check: the cathode band must be at `55f` (COIL +, the rail side), not at `55a`.** Visual is enough if the band is legible; otherwise unplug USB and use diode mode — ~0.65 V band-to-non-band, OL reversed.
- **V3 — rebuild steps 3–4 on the relocated column.** 1 kΩ from the *verified* Base strip (**col 51**) to **column 53 A–E** (preferred: unclaimed in the netlist, and on the relay side of the transistor, keeping a switching drive line clear of the cols 30–48 analog block). Column 46 A–E is the fallback. **Verify the chosen column is dead first** — no continuity to either rail, to col 45, or to col 48 (SOURCE_NODE) — rather than trusting a document that calls it free. Then jumper that column → Teensy pin 14.
- **V3 — rebuild steps 3–4 on the relocated column.** 🟢 **CLOSED 2026-09-15 — col 53 ↔ col 51 (Base) = 0.993 kΩ.** Base drive relocated off col 45 to **column 53**, and the resistor is seated: 0.993 kΩ against 1 kΩ nominal is a 0.7 % agreement, well inside a 1 % part. **This closes the original failure mode** that began the halt — the unseated leg that read continuity from one side only. (My reconciliation of 2026-09-15 (3) listed this as outstanding; that was wrong — the measurement had already been taken. Corrected on builder report.) No need to repeat unless the node is physically disturbed.
- **V4 — 🟢 emitter confirmed: col `50` → GND = 0.0 mV.** 10 kΩ pulldown on the Base strip still unconfirmed by measurement (not load-bearing while pin 14 is a driven output; matters during reset).
- **V5 — 🟢 → removed 2026-09-16.** `[PHASE6-TEMP]` handler and help line deleted after the contact cycle passed, and the build compiles. Before that: **the `p` command now exists.** It did **not** before 2026-09-15: the dispatch at [guitar_rig_analyzer.ino:395](../guitar_rig_analyzer.ino#L395) handled `v 1 2 3 4 r m T t u i x s b c` and no `p`, so runbook step 11 had never been carried out and `p` would have printed `Unknown command` with the relay silent — a phantom fault on a driver that had just passed six checks. Added as `[PHASE6-TEMP]` (case + help line; **grep that tag to remove before Phase 7**). **`p` and `P` are the same toggle** — the runbook's verify table says otherwise and its own snippet disagrees with it; trust the printed `[BringUp]` state line, not the keystroke.
- **V5a — 🟢 compile verified 2026-09-15.** `arduino-cli compile --fqbn teensy:avr:teensy41 .` succeeds with the `[PHASE6-TEMP]` handler in place. FLASH code 156 736 B, RAM1 variables 218 080 B / 142 368 B free for locals, RAM2 62 528 B. No errors, no new warnings. `RELAY_SEND_PIN` resolves via `config.h` ([.ino:102](../guitar_rig_analyzer.ino#L102)).
- **V6a — driver stage 🟢 PASS 2026-09-15.** Uploaded; `p` clicks the relay both ways; **collector `49` = 125.6 mV energised** (criterion 0.1–0.3 V) and 4.99 V de-energised. GPIO → 0.993 kΩ → base → saturation → coil → actuation is proven end to end. Journal 2026-09-15 (4).
- **V6b — 🟢 PASS 2026-09-16.** LOW: `56a`↔`57a` closed / `57a`↔`58a` open. HIGH: open / **closed**. LOW again: closed / open. Collector 4.99 V off. **`56a` NC, `57a` COM, `58a` NO**, bench-proven. Cause of the earlier failure: reversed coil polarity. *(History:)* 🔄 2026-09-16: no longer blocked on part identity. A verified TQ2-5V fails identically. Leading cause is reversed coil polarity** (datasheet: pin 1 = +; runbook/bench: +5 V on pin 10). Gate: stripe row side `55a` vs `55f`, then ~~rotate the relay 180°~~ (wrong, see TODO-47) and re-run. See TODO-47 and journal 2026-09-16 (1). *(Original text follows.)* **BLOCKED ON PART IDENTIFICATION. See TODO-47.** The contact pattern is **identical energised and unpowered** — `56`↔`57` closed, `57`↔`58` open, `56`↔`58` open, on both poles, in circuit and with the relay out of the board. **The coil energises but the contacts never transfer.** Leading hypothesis: the fitted part is a **TQ2-L2-5V dual-coil latching** relay, not a TQ2-5V. **No further contact measurement is meaningful until the part is identified** — every reading taken against the wrong part model produces a finding that has to be retracted, which has already happened once here.
  **🔻 Withdrawn from this item:** the earlier conclusions "`58a` is NC" and "the runbook's contact map is wrong." Both rested on the energised sweep showing a transferred state; it did not. Journal 2026-09-15 (5).
  *(superseded — it clicked; retained for the diagnostic logic)* **If it prints HIGH and nothing clicks:** with V3 now closed at 0.993 kΩ, the base path is proven, so suspicion moves to the relay itself, the `55a`→`49` coil− jumper, or BJT saturation. The collector still discriminates: 4.99 V = base not reaching the BJT despite the resistor being seated (check the col 53 → pin 14 jumper); 0.1–0.3 V = BJT saturating correctly and the fault is relay-side.

**Why:** Breadboard uses non-latching TQ2-5V (DigiKey 255-1004-5-ND) instead of the TQ2-L2-5V purchased for the eventual PCB, because current firmware drives each relay with one static GPIO — see journal.md 2026-08-25 entry for the full reasoning. Don't "fix" this by swapping in the latching parts without also changing the firmware.
**Proof:** Sign-off checklist line: "TQ2-5V #1 clicks on `p`/`P`; continuity matches expected state." **Plus V1–V3 recorded**, since the as-built coordinates now differ from the runbook's and a future rebuild needs the real ones.

### TODO-7 — Phase 7: RELAY_RETURN + full signal wiring (Rig Send / Rig Return TS) 🔴 — return-source architecture DECIDED ([ADR-004](../docs/adr/ADR-004-return-source-is-operator-selected.md))
**Pre-wiring checklist (2026-09-16, Phase 6 now signed off):** (1) ~~decision gate~~ **decided 2026-09-16, see below**; (2) count the BB830's columns and re-site the mirror, because "cols 60–70" cannot fit (TODO-45); (3) correct runbook Phase 6 steps 7–10 coil polarity first so the mirror doesn't copy it; (4) template = **TODO-6's as-built line**, not the runbook; (5) forward-trace new coordinates against col 53–59 (TODO-46); (6) only **pole 1** contacts are bench-proven.
**✅ DECISION GATE CLOSED 2026-09-16 — [ADR-004](../docs/adr/ADR-004-return-source-is-operator-selected.md).** Explicit operator selection is binding: `TS` / `XLR`, no `AUTO`. **TS on every boot, not saved** (matches de-energised RELAY_RETURN). Jack presence must not choose the return or decide measurement validity; it may only show status or warnings. Selection changes go through `audioEngine_setRoute()` → ROUTE_CHANGED immediately.
**Hardware consequence:** **pin 22 is not required for Phase 7.** Keep the TS return #11. Do not replace it, and do not build a TS-return detection mechanism. Phase 7 hardware = pin-15 RELAY_RETURN driver + signal wiring.
**Firmware: implemented at `3460080`, compile-verified, NOT bench-verified.** `setReturnPreference()` and the auto-detect path are removed. `signalRouter_setReturnSource()` plus serial `j` (TS) / `k` (XLR). Order: **(a)** decision/contract ✅ `e9ebd75` → **(b)** firmware ✅ `3460080` → **(c)** bench proof below ❌ **not started. Phase 7 is NOT complete.** Pin 15 has no driver yet, and **the Phase 7 driver copy must include the base pulldown**: physical TS-at-power-on depends on it, because pin 15 is in MCU reset state until `signalRouter_init()` runs late in `setup()`.
**🔨 BENCH PROGRESS 2026-09-17 — driver #2 BUILT at columns 8–18, resting state measured, but BLOCKED: the board is running a pre-ADR-004 build.**
- **Site chosen and forward-traced (TODO-46 done for the driver):** BB830 is physically **columns 1–64** (`PHYS`, builder), hardware occupies ~30–60, **1–29 empty**. The runbook's "mirror at cols 60–70" is impossible. Driver #2 = the Phase 6 **as-built** line shifted left 41 columns: GPIO pin 15 → `12`; 1 kΩ `12`→`10`; **C `8` · E `9` · B `10`** (as-built order C-E-B, NOT the runbook's E-B-C silkscreen order); 10 kΩ pulldown `10`→GND; coil+ `14a`→+5 V; coil− `14f`→collector `8`; 1N4148 band `14a`; relay body `14`–`18`; pole 1 `15a` NC / `16a` COM / `17a` NO. **No coordinate lands in 30–64; col 45 (VGND) untouched.**
- **Rails verified before placement** (`MEAS`, continuity, power off): red and blue rails both continuous `8`↔`18`; blue ↔ circuit GND; **red ↔ the +5 V node feeding the Phase 6 driver**. That last beep also closes netlist **GAP-5** (`TOP_RED` col 5 ↔ col 55 continuity, previously `NYV`) **if the rail probed was the top pair — builder has not yet confirmed top vs bottom.** Netlist edit belongs to the capture session, so it is recorded here, not written into `docs/asbuilt/netlist.md`.
- **Build reported continuity-clean** (`RPT`, builder: "it's a lot of solder but continuity is clean").
- **Resting state at power-on, before any Serial command** (`MEAS`): base `10a`→GND **1.7 mV**; Teensy pin 15→GND **2.6 mV**; **`14f`→GND 4.98 V** with `14a` at +5 V ⇒ **≈0 V across the coil, relay de-energised.** This is the intended TS/default state, now bench evidence rather than assumption.
- **⚠️ What this does NOT prove:** *why* pin 15 is LOW. The 10 kΩ pulldown and `signalRouter_init()`'s `digitalWrite(RELAY_RETURN_PIN, LOW)` both hold it there, and **the pre-ADR-004 build does that too**. Distinguishing them needs a measurement during reset, before `setup()` reaches the router.
- **🛑 FLASH MISMATCH — the running build is older than `3460080`.** Sending `j` returned `[Main] Unknown command: 'j'.` and a help list ending at `r=reset EMA` with **no `j`/`k` line** (`MEAS`, serial readback). The local tree and `HEAD` do contain it (`guitar_rig_analyzer.ino:452`). **Source ✅ / flashed ❌. Do not send `k` until reflashed** — on the old build `k` is also unknown, so it proves nothing, and no other command drives pin 15.
- **No new Phase 7 firmware is needed.** `j`/`k` already are the Phase 7 relay control. **Do not add a `[PHASE7-TEMP]` pin-15 toggle:** `signal_router.cpp` owns pin 15, and a second writer would desynchronise the router's state from the hardware — the same reason `[PHASE6-TEMP]` was removed (journal 2026-09-16 (2)).
- **Next, in order:** (1) flash the current tree; (2) confirm the help list now shows `j=return TS  k=return XLR`; (3) re-measure the resting state; (4) send `j` — expect no relay change, `14f` stays ≈4.98 V; (5) send `k` — expect the relay to pick up, `14f` to fall to ~0.13 V (Phase 6 measured 129.1 mV), and `15a`/`16a`/`17a` continuity to transfer; (6) send `j` again to confirm it releases; (7) power-cycle and confirm it comes up TS de-energised.

**✅ DRIVER + CONTACTS PASS 2026-09-19 (journal 2026-09-19 (1)).** `k` → click, coil **4.78 V**, `16a` COM↔`17a` NO closed / `15a` NC↔COM open; `j` → clean release, COM↔NC closed. Survives power-off → cold boot → XLR → TS untouched. Pole 1 bench-proven **on relay #2**; pole 2 still datasheet-level. Firmware path observed end to end on hardware (`j` no-op; `k` → route change → `[Main] audioCap: ROUTE_CHANGED`).
**⚠️ It did not work first try, and the fix is NOT identified.** Before probing, the driver stalled in the active region under load: collector `8a` **3.556 V** (earlier 3.733 V), emitter **291 mV**, coil carrying ≈⅓ of ~27 mA. Load-dependent ⇒ series resistance in the emitter path (adapter emitter joint / `9a` contact / GND jumper). Reseating/probing changed something and it became repeatable — **an unexplained recovery, not a diagnosis. If it returns, measure the base-resistor drop (`12a`→`10a`) FIRST** (it was queued and never captured), then the emitter. **A continuity beep does not rule this out:** ~1 mA proves a path, not low resistance at 27 mA.
**🔻 TOPOLOGY CORRECTION 2026-09-19 (journal (2)): there is NO Rig Send jack.** Only two Switchcraft #11s exist — the Phase 5 **Instrument In** jack and the Phase 7 **Rig Return TS** jack. Runbook Phase 7 steps 9–10 (build Rig Send) are **not done**. Tonight's temporary cable joined **`SOURCE_IN` (col 30, the raw input node ahead of the buffer)** to the TS return, not a buffered send. Cable since removed — it put an AC load on the raw input node (LINE IN R is AC-coupled, `DERIV`, so DC was never the issue).
**Return-path evidence so far (directional, NOT sign-off):** relay A→B→A with nothing else changed moved the SOURCE−RETURN gap 0.0–0.3 dB (TS) → 4.2–4.7 dB (XLR) → 0.3/2.5 dB (TS). Mechanism identified, but it is a drifting **noise floor**, not a stimulus, and one restored-TS cycle read 2.5 dB. **Still needed: a real stimulus, and the Rig Send jack.**
**✅ RIG SEND JACK BUILT + FIRST VALID TF 2026-09-19 (journal (4)).** Third Switchcraft #11 installed: TIP → `SOURCE_NODE`, sleeve → **Audio Shield GND** (matches the 33.1 dB lesson), no stable TIP↔sleeve short (~0 Ω → 50 MΩ → OL, charging), `48e` → LINE-IN-L preserved. With a real guitar: **SOURCE −10.1 / RETURN −10.2 dBFS, TF confidence 15 % (> 10 %), 120 Hz / 500 Hz / 1 kHz all −0.0 dB**, raw samples tracking. **The intended chain conducts and produces a valid estimate.** Bounds: `---` at 5/10 kHz is *no qualifying data*, **not** roll-off; −0.0 dB is a **cable loop, not a calibrated result** (that is TODO-9 Test 1 with its fixture); 15 % is barely over threshold from a decaying strum.
**Remaining for Phase 7 sign-off:** a **stimulus-present A/B** (play → select XLR → RETURN collapses → select TS → returns); the noise-floor A/B was done on the floor only. Earlier gap — the signal path (TS return → line-in R) — is now **closed**, so the ADR-004 proof line below is only partly satisfied. This coil's resistance was never measured (the ~27 mA figure borrows relay #1's 183 Ω).

**Proof (ADR-004, run after (b)):** At boot, with no operator action, RELAY_RETURN is de-energised and the router reports TS. Selecting XLR energises RELAY_RETURN (contacts transfer by continuity), raises ROUTE_CHANGED, and changes the route description. Selecting TS reverses all three. The reported source follows the selection **whatever jacks are plugged in, including none**. A TS signal on Rig Return reaches line-in R when TS is selected. A power cycle returns to TS. *(Replaces "Full route matrix (4 jack combinations) produces correct route description on Serial", which presumed auto-detect. Runbook sign-off line 1702 carried that same criterion and was **corrected as part of the ADR-004 documentation change**. The old text is preserved in ADR-004 and git history.)*

### TODO-48 — Validation harness: the "Press Enter" prompt accepts ANY byte, and single tests skip preflight 🟡 **not blocking; found 2026-09-19 by running Test 1 by accident**
**Why:** `validation_waitForUser()` (`validation.cpp:471`) waits on `while (!Serial.available())` and then flushes the buffer. The prompt says *"Press Enter to continue"*, but **any character continues, and there is no decline/cancel path once the prompt is up.** A keystroke meant as cancel (`x`) was consumed as consent and started Test 1 on a nonconforming fixture. Separately, the single-test commands `1`–`4` call `waitForUser()` then run the test directly (`guitar_rig_analyzer.ino:409–423`), **bypassing the preflight level check** that only `v` → `validation_runAll()` performs — so a dead SOURCE surfaces as NaN inside a result table instead of a clear preflight failure.
**What:** accept only Enter (or an explicit key) as consent, add a decline key that returns without running, and make the single-test paths run the same preflight as `v`. **No code changes were made when this was found** — the bench session deliberately kept moving.
**Proof:** a keypress other than the consent key leaves the harness waiting; the decline key returns to the main loop with no test run; `1` on a silent SOURCE reports a preflight failure rather than a NaN table.

### TODO-49 — Unexplained `SOURCE_IN` resistance readings 🟡 `NYV` — **do not reuse as evidence in either direction**
**`NYV` / anomalous bench measurement:** POWER-OFF resistance measurements reported **~14–23 Ω from `SOURCE_IN` to ground**, while `SOURCE_IN` across C1 repeatedly measured **~77.4 kΩ**. The observations were internally difficult to reconcile with the known topology. **No wiring defect was identified or corrected. Investigation intentionally deferred; do not use these resistance readings as evidence of a hardware fault or of a hardware pass.**
**What:** if revisited, re-measure with a stated probe topology (which two holes, which meter range, what else is connected) before interpreting, and record whether C1 is in or out of circuit for each reading. Nothing tonight produced an observed functional failure of the Phase 7 return hardware.

### TODO-8 — Phase 8: XLR return **signal path** 🟡 **signal path BUILT and contact-proven 2026-09-19; not signed off**
**Scope re-titled under ADR-004:** this was "XLR return detection". Routing no longer depends on detection, so the phase is the **signal path**; the **D2F-01L microswitch is intentionally not built**.
**As-built (journal 2026-09-19 (3)):** pin 2 → **`17a`** (relay #2 pole-1 NO) · pin 1 → top breadboard GND rail · pin 3 → top breadboard GND rail · no other connector contacts wired. Passive, power off: pin2→pin1 **OL**, pin2→pin3 **OL**, pin1→pin3 **0.2 Ω**, pin2→top GND **OL** (post-handling bridge check only, not independent isolation proof). **Connector marking not read back — part identity `NYV`** (TODO-47's lesson).
**Contact proof (`MEAS`, nothing rewired between states):** XLR pin 2 → LINE IN R = **OPEN (TS) → BEEP (XLR) → OPEN (TS)**.
**⚠️ Known signal-quality risk, not a defect:** the XLR reference is the **breadboard** rail while the codec's is the shield; journal 2026-09-12 (3) measured 33.1 dB from exactly that distinction on the return point. **Test when a real signal first runs: compare the XLR noise floor against the TS path.** Do not rewire pre-emptively.
**Proof (revised, ADR-004):** the contact proof above, **plus** a real analog signal through XLR pin 2 reaching RETURN_NODE with a noise floor comparable to the TS path. *(Replaces "XLR + microswitch detect both work end-to-end", which presumed detection was required. **Runbook sign-off line 1703 still carries the old wording and is uncorrected** — same stale-checkbox trap as line 1702 was; correct it in the same pass as TODO-45's other runbook fixes.)*
**Parts note:** intended connector is the Neutrik **NC3FAH2-0** combo (XLR + 1/4" TRS in one hole). Its TRS contacts are **deliberately unwired** — if they are ever used, they become a second path into `17a` and must be documented. **✅ The earlier "revisit the microswitch criterion before Phase 8" flag is now resolved** by the ADR-004 re-scope above: detection is optional UX, ADR-002 governs it if ever built.

### TODO-50 — `[Main] Route:` misreports the route until the first `j`/`k` 🟡 presentation-only; **observed during a valid measurement 2026-09-19**
**Why:** `signalRouter_init()` deliberately does **not** call `audioEngine_setRoute()` — boot is not a route-change transition (ADR-004 Decision 2, and the property that makes TS-at-boot clean, with no relay actuation and no ROUTE_CHANGED). So `audio_engine` keeps the description from its own `init()` (`audio_engine.cpp:110–114`) and the 5 s diagnostic prints `Route: Default bench: SOURCE_NODE=L, RETURN_NODE=R` **on a board whose router is in TS.** Observed during the first valid TF run (journal 2026-09-19 (4)). The same string goes to the Pi in ROUTER_STATUS, so a UI would show it too.
**Not a hardware or routing fault** — the router's state is authoritative and correct; this is stale *presentation* state.
**What:** have `signalRouter_init()` set the route description without raising ROUTE_CHANGED (e.g. a description-only setter on `audio_engine`), **or** decide to leave it and document the behaviour where operators will read it. **Do not "fix" it by calling `audioEngine_setRoute()` at boot** — that reintroduces the boot transition ADR-004 removed on purpose.
**Proof:** a fresh boot with no commands prints a route description matching the router's selection, and the boot still shows no relay actuation and no ROUTE_CHANGED.

### TODO-9 — Phase 9: Validation harness on real hardware (tests 1–4) 🔴
**Why:** This is `validation_runAll()' exercised against actual physical loopback/pads/filters — not `SELF_TEST`, which only proves the audio block counter is advancing (see journal.md). Do not treat a passed self-test as equivalent to this.
**What:** Run tests 1 (flat loopback), 2 (channel-swap symmetry), 3 (known 6 dB gain offset), 4 (known RC filter response) per the runbook.
**Proof:** Sign-off checklist line: "`1`, `2`, `3`, `4` all PASS."

### TODO-10 — Breadboard sign-off 🔴
**Why:** The runbook is explicit that build success and even individual phase passes are not the finish line — full board sign-off requires physical evidence before moving to PCB design.
**What:** Photograph the entire board, save serial logs, and record the results in `docs/bench_runbook.md` §8 (this file does not exist yet — it must be created at sign-off time, don't assume prior bench history is already captured there).
**Proof:** all Phase 1–9 sign-off checklist boxes ticked, photos taken, `docs/bench_runbook.md` §8 updated with the date.
**Known outstanding at time of writing (2026-09-01):** Phase 3's "All four GPIOs respond to GND taps" line is **not** yet tickable — only its electrical half is proven; the `JACK_CHANGED` / `ROUTE_CHANGED` event half is deferred to TODO-11. Phase 2's Serial evidence is also incomplete (TODO-2). Both must be closed here, not waved through.

---

## Track C — Display architecture reconciliation (ADR-001) — **resolve before any further UI work**

Opened 2026-09-11 after an audit found the repository building an RA8875 product
while still carrying the Pi 5 architecture as documentation and dead code. The
decision is recorded in [docs/adr/ADR-001-display-architecture.md](../docs/adr/ADR-001-display-architecture.md):
**the Pi 5 is the production renderer; the RA8875 is demoted to debug hardware;
the Teensy remains sole authority for measurement truth.**

Sequencing rule: TODO-12 and TODO-14 do **not** proceed in their current form.
Every hour spent polishing the RA8875 interface makes this correction more
expensive.

### TODO-33 — `DISPLAY_TARGET` + presentation boundary 🟢 **DONE — compile-verified 2026-09-11, all three targets**
**Why:** the application had ~20 direct `displayEngine_*` calls and `data_sender`
had zero callers — two renderer architectures, one unreachable. Swapping the call
sites to `dataSender_*` would have hard-wired the second assumption in place of
the first. A boundary makes renderer choice a build decision.
**What was done:**
- `presentation.{h,cpp}` — the only display-facing API the application may call.
  Seven functions, one-way by design: no return path exists through which a
  renderer could report a measurement value or validity verdict back into the
  measurement path.
- `config.h` — `DISPLAY_TARGET` tri-state (`_PI` / `_RA8875` / `_NONE`) replacing
  the never-implemented boolean `USE_PI_DISPLAY`, with an `#error` on an invalid
  value. `_NONE` is independently valuable: it is the honest configuration for
  bench DSP work with no panel attached, which is what Phases 5–9 actually run in.
- `guitar_rig_analyzer.ino` — 27 call sites rewired to `presentation_*`; header
  documentation and boot banner updated. The banner now prints the backend name so
  no serial log pasted into this journal can be misattributed to the wrong renderer.
- **`validation.cpp` — 14 direct `displayEngine_*` calls found and rewired.** This
  was a real leak: the validation harness, which runs Phase 9 and proves the
  instrument works, was hard-wired to the RA8875 and would have kept an RA8875
  dependency alive inside a Pi build while reporting nothing to the Pi.
- `display_engine.cpp` and `data_sender.cpp` bodies wrapped in
  `#if DISPLAY_TARGET == ...` guards. Necessary because an Arduino build compiles
  **every** `.cpp` in the sketch folder regardless of includes — without the
  guards, `_NONE` would not actually be free and the unselected backend would stay
  a build dependency.

**Proof (observed, not inferred):** all three targets compile clean for
`teensy:avr:teensy41`. `arduino-cli compile -v` library lists confirm exclusivity —
Adafruit RA8875 / GFX / BusIO appear **only** in the `_RA8875` build. Figures below
are post-TODO-34 (protocol v2):

| Target | FLASH code | RAM1 free for locals | RAM2 vars | warnings | Adafruit libs linked |
|---|---:|---:|---:|---:|---|
| `_NONE` | 147 904 | 148 928 | 46 720 | **0** | no |
| `_PI` | 152 960 | 146 656 | 62 528 | **0** | no |
| `_RA8875` | 158 596 | 140 608 | 46 720 | 2 | yes (3) |

The `_PI` build's two remaining warnings are gone as of TODO-34 — the unused
`payload_size` went with the rewritten code path. The two `_RA8875` warnings are
the pre-existing Adafruit `setRotation` hiding, inside the third-party library
itself. The `_PI` RAM2 delta (+15 808 B) is the three `DMAMEM` transport buffers
landing in OCRAM rather than the tight RAM1 budget, as intended — RAM1 free for
locals differs by only ~2.3 KB between `_PI` and `_NONE`.
**Not yet uploaded to hardware** — compile proof only. `[compiles]`

### TODO-34 — Audit and freeze the Pi link wire format 🟡 **SCHEMA FROZEN 2026-09-11 (protocol v2). Transport unproven — T1 bench measurement outstanding**

**🟢 Closed in source (protocol v2, `PI_PROTOCOL_VERSION 2`):** all five 🔴 findings plus six 🟡.
- **L1 — clamp state now on the wire.** Per transmitted bin, one byte carries the number of source bins CLAMPED (high nibble) and VALID (low nibble), plus frame-level `tf_clamped_count` over all 512 source bins. The rendering contract is written into `data_sender.h`: `clamped == ratio` means draw a saturation indicator, **not** the rail value; `valid == 0` means pen-lift.
- **L2 — decimation domains separated.** Linear spectra decimate by **maximum** (peak-preserving: an arithmetic mean under-reported a lone peak by 12 dB); `tf_db` keeps the dB mean. Both choices are now stated on the wire contract rather than being undocumented defaults.
- **L3 — NaN coverage preserved** via the valid nibble; a bin with no energised source bins emits NaN.
- **R1 `result_valid`, R2 `calibration_provenance[96]`, R3 `calibration_type` + 5 warning bits, R5 structured `firmware_version`, R6 `fft_size`/capture blocks/node channels/`line_in_level`** — all transmitted.
- **T2 → structured HELLO packet** (`0x06`) with numeric protocol/bin/baud fields and a capability bitmap. **T4** closed by that bitmap: the Pi can now distinguish "monitor mode off" from "monitor mode not compiled in", so it will not render a control that cannot respond. `MODE_PRECISION`/`MODE_LF` bits stay clear because `arm()` still rejects them — advertising them would be a lie the Pi would act on.
- **T3 → VIEW packet** (`0x07`). `presentation_restoreLive()` no longer sends a magic `"VIEW:LIVE"` status string.
- **T5** gone with the rewritten code path; `_PI` and `_NONE` now compile with **zero warnings**.
- **R4 / R7 deliberately deferred** (result auto-spectra = +4 KB/packet, revisit after T1; `phase_unwrapped`/`tf_raw_mag_db` recoverable or redundant). Recorded as decisions, not omissions.

**🟡 T1 — mitigated architecturally, NOT YET MEASURED. This is the only thing standing between v2 and a freeze.**
The rule is now explicit in source: **presentation transport must be lossy before measurement becomes lossy.** LIVE_FRAME is best-effort/droppable/latest-wins; RESULT is reliable, staged and drained across loop iterations by `dataSender_service()`; events are best-effort. Every write is gated on `availableForWrite()` and **no blocking write remains**. The TX buffer is extended to 4 KB via `addMemoryForWrite()` — a `static_assert` enforces that it exceeds one framed live frame, because otherwise `availableForWrite()` could never report room and *every* frame would silently drop.
Safety net: `measurement_state` rides in every live frame, so a dropped ABORTED costs the reason string, not the fact.
**Note the trade made knowingly:** v2's live frame is *larger* than v1's (1 689 B vs 1 559 B, ~36.7 ms vs ~33.8 ms predicted) because closing L1/L3 costs 130 bytes of coverage data. Those bytes are what stop the Pi rendering a rail as a measurement, and the larger frame is only safe *because* it is now droppable.
**Proof required (Phase 10 step 11/12, TODO-35):** measured max call duration in **microseconds**; block timing with a Pi consuming indistinguishable from `DISPLAY_TARGET_NONE`; and block timing unchanged with the Pi **absent, stalled, and yanked mid-result**. A high drop count with a low max call time is the policy working. **Do not close T1 on a source reading.**

**Instrumentation shipped for that measurement:** `dataSender_getStats()` / `dataSender_printDiagnostics()`, surfaced as the `u` serial command and printed inside the existing 5 s diagnostic window so transport figures sit directly beneath block timing — the question is never "how many frames dropped" alone, it is "did transmission perturb acquisition".

**Protocol acceptance tests** (docs/pi_link_protocol_audit.md): A the truth question per field · B no new blocking write · C layout drift cannot be silent (`static_assert` + a runtime check that refuses to send a drifted packet) · D receiver survives unknown packet types · E renderer cannot perturb measurement.

**Original audit findings, retained below for the reasoning trail:**
**Why:** `data_sender`'s protocol was written before the clamp-marker work, the
confidence-denominator fix and the insight/provenance model reached their current
form, and had never been checked against them. Promoting it to production makes it
a compatibility surface between two codebases.
**Findings:** [docs/pi_link_protocol_audit.md](../docs/pi_link_protocol_audit.md) —
**17 findings, five 🔴, four of them failures of the ADR-001 invariant** ("the
Teensy determines truth"). Every invariant failure is the same mistake: the
firmware computes a verdict and does not put it on the wire.
- **L1 🔴 the TF clamp mask is not transmitted.** `tf_clamped_bits[]` /
  `tf_clamped_count` exist precisely so consumers can distinguish a saturation
  rail from a measurement, and `audio_engine.h:310` makes checking them mandatory
  for any consumer that renders `tf_db` to a human. `sendLiveFrame()` sends
  neither. **This re-opens TODO-29 on a new surface** — the Pi would plot a flat,
  confident, entirely fictional −24.0 dB curve exactly as the serial diagnostic
  did in 33 of 33 windows on 2026-09-07 before `aa9a795` fixed it.
- **R1 🔴 `result_valid` is not transmitted at all.** The Pi must infer validity
  from the quality enum — re-deriving a judgement the Teensy already made.
- **R2/R3 🔴 `calibration_provenance`, `calibration_type` and
  `calibration_warnings` are not transmitted.** The result view is specified to
  show provenance (README, TODO-12 proof criterion) and cannot. A calibrated
  result would display with its own warnings silently dropped.
- **T1 🔴 blocking UART writes sit in the real-time super-loop.** A 1 559-byte
  live frame is ~33.8 ms of wire time at 460 800 baud — **73 % of the measured
  46.3 ms audio block period** — and `DISPLAY_UPDATE_EVERY_N_FRAMES` is 1, so one
  is sent every block. A max-size RESULT is ~214 ms, ~4.6 block periods. Same
  failure shape as the RA8875 `waitPoll()` incident, different peripheral.
  **⚠️ This is an analytic prediction from baud rate and packet size, NOT a bench
  measurement** — the TX buffer size and whether Audio-library DMA survives a
  stall have not been measured. Instrument it before recording it as a finding.
- **T2 🟡 the protocol version is a human-readable string** the Pi must parse to
  establish its own compatibility contract.
**What:** close L1, R1, R2, R3 and T2 — they change the payload shape — then
version and freeze the format. Measure T1 before choosing its fix.
**Proof:** a frozen, numbered protocol spec; a Teensy-side packet dump showing
clamp state, `result_valid` and provenance present; and a measured (not predicted)
worst-case loop-blocking figure for both packet types.

### TODO-35 — Phase 10: Pi 5 integration and bench acceptance 🔴 **ready to run — this phase is what closes TODO-34's T1 and freezes protocol v2**
**Why:** the Pi 5, Active Cooler, 27 W PSU, Touch Display 2 and Freenove GPIO HAT
were all purchased and the runbook's parts list marks them "used in Phase 9" — but
Phase 9 in that same document is the **validation harness**. The Pi was in the bill
of materials with nowhere to be installed. Retrofitting it into Phase 9 would
repeat exactly the status-collapsing error this file warns against.
**What:** Phase 10 in `docs/breadboard_bringup_v3.md` — Teensy `Serial1`
(pins 0/1) to the Pi UART via the Freenove HAT, level/ground verification before
any data, then link bring-up.
**Proof:** acceptance must test **Teensy UART → Pi → rendered known data
independently of the full analyzer** — a synthetic/known frame rendered correctly
on the Pi panel, plus CRC-rejection behaviour demonstrated by deliberately
corrupting a packet. Do not accept the phase on "the analyzer seems to work".

**🔬 THE T1 ACCEPTANCE MATRIX — this is the decisive test and the harness for it
now ships.** `timing_probe.{h,cpp}`, compiled into **all three** targets (the
control run must use identical code, or the comparison is meaningless). Commands:
`t` starts a measurement window, `T` prints a fixed-format `key=value` report
built to be diffed mechanically.

| Run | Build | Condition | Role |
|---|---|---|---|
| 1 | `_NONE` | no display hardware | **THE CONTROL** |
| 2 | `_PI` | reader consuming normally | normal operation |
| 3 | `_PI` | reader suspended (`kill -STOP`), UART stays full | sustained backpressure |
| 4 | `_PI` | TX pulled mid-RESULT drain | loss mid-transaction |

Identical window length (≥60 s) and identical signal conditions across all four.

**Pass condition — acquisition must not move:**
- `block_ms_mean` / `block_ms_max` / `block_ms_spread` **indistinguishable from run 1**
- `blocks_skipped` / `skip_events` / `largest_block_gap` = **0 in every run**
- `loop_us_max` and `audio_blocks_high_water` comparable to run 1
- Validation suite still runs and passes in run 3

**Transport is ALLOWED to degrade:** drops in runs 3/4 are expected and correct;
`TX room min = 0` in runs 3/4 is backpressure being absorbed as designed;
non-zero abandoned result bytes in run 4 is correct.

**⚠️ DO NOT PASS ON A SMALL CALL TIME.** A microsecond-fast `presentation_*()` can
still disturb the instrument through interrupt load, UART ISR activity, DMA
contention or buffer servicing — none of which appear in a call-duration figure.
The pass condition is the comparison against run 1. The control run *is* the
threshold; there is no absolute number to argue about. This matters more here than
in a typical embedded project because the firmware is built around one capture
owner and one canonical timebase, and everything time-sensitive references it.

Keep all four reports verbatim in journal.md. On pass: T1 closes, protocol v2 goes
from *schema-frozen, transport-unproven* to proven, and the milestone is
**v0.6.0 — Pi presentation architecture validated**.

### TODO-36 — Pi-side software deliverables 🔴 **schema is frozen — write the parser; start the renderer only after T1 passes**
**Status 2026-09-11:** protocol v2 is **schema-frozen** — field positions, packet
type ids, enum meanings, clamp/coverage semantics and the RESULT layout will not
change without a defect and a version bump. The parser can be written now.

**Read `live_bins` and `decim_ratio` from the HELLO packet rather than hardcoding
them.** Cadence, bin count, TX buffering, chunking and baud are explicitly NOT
frozen — Phase 10's T1 measurement may change any of them — and a receiver that
takes its geometry from HELLO is immune to all of it. One that hardcodes 128 bins
will break the first time the cadence lever is pulled.

**Do not start the renderer/UI until T1 passes.** Building views on a transport not
yet shown to be harmless to measurement timing is the one dependency worth
respecting here; the parser is safe to build because the schema is frozen, but the
renderer embeds assumptions about frame rate and latency that T1 could invalidate.
**Why:** ADR-001 accepts a second codebase as a real cost. None of it exists yet.
**What:** receiver + framing scanner; packet parser; CRC rejection and resync;
reconnect/stall behaviour (the Teensy may reboot mid-stream); measurement state
model mirroring the firmware's `IDLE → ARMED → CAPTURE → PROCESSING → RESULT`
plus sticky `ABORTED`; live spectrum/TF view; completed-measurement view showing
quality **and** provenance; touch navigation; then Compare/Recall and the radial
tone fingerprint.
**Constraint — non-negotiable (ADR-001):** the Pi must not compute anything that
determines whether a measurement is valid. Confidence, coherence, clamp state and
quality grade arrive as verdicts and are displayed, never recomputed. Interpolating
pixels, animating, formatting and navigating are all fine.
**Proof:** a held-out recorded packet stream replays to identical rendered output;
a deliberately corrupted packet is rejected, not rendered; a mid-stream Teensy
reboot recovers without a restart.

### TODO-39 — T1 acceptance harness (`timing_probe`) 🟢 **DONE — compile-verified 2026-09-11, all three targets**
**Why:** the T1 pass condition is "acquisition timing indistinguishable from the
`_NONE` control", and **the firmware could not produce the numbers that claim
requires.** The 5 s window reported a block-period *mean* only — no max, no
spread, no skipped-block detection, no audio high-water, no loop-body max. Phase 10
could have been "passed" on a small transport figure while a real perturbation went
unmeasured, which is precisely the failure mode the pass condition is written to
prevent.
**What was done:** `timing_probe.{h,cpp}` — block period mean/max/min/spread;
**skipped-block detection from gaps in the canonical block counter** (a gap > 1
means an analysis block was produced that the loop never processed — the most
direct evidence of measurement disturbance available without touching the capture
layer); whole-loop-body duration max, which catches anything blocking wherever it
lives rather than only presentation calls; audio block high-water with a per-window
reset so a boot spike cannot contaminate later runs. Wired into `loop()` and
`setup()`; `t` / `T` serial commands; emits the transport block in the same report
so one paste captures both sides.
**Compiled into all three targets deliberately** — guarding it to `_PI` would make
the control run unmeasurable and void the entire test.
**Honest limitation, stated in the source rather than glossed:** `audio_capture`
exposes no dropped-block or per-queue overrun counter, so `audio_blocks_high_water`
is the Audio library's **global** figure and is corroborating pressure data only.
`blocks_skipped` is the authoritative overrun evidence. The report says so, so
nobody cites it as "capture overruns".
**Proof:** all three targets compile clean (`_PI` and `_NONE` warning-free).
**Not yet uploaded** — compile proof only. `[compiles]`

### TODO-38 — Single authoritative firmware version; 0.6.0 baseline 🟢 **DONE 2026-09-11**
**Why:** `FIRMWARE_VERSION` said `0.5.0` while `data_sender.{h,cpp}` headers said `v0.6.1` and **21 other module headers carried their own `v0.5.0`**. A version stamped into every exported measurement must have exactly one source, and a module-local product version is drift waiting to be cited as fact.
**What was done:**
- `FIRMWARE_VERSION "0.6.0"` — a deliberate baseline, not a patch bump, and deliberately **not** 0.6.1 just because a header already claimed it (that header had run ahead of the product). 0.6.0 means one thing: *first firmware baseline implementing the Pi 5 production display architecture* — presentation boundary, three compile targets, backend exclusion, validation harness migrated off the renderer, protocol v2 with the four truth-invariant defects closed.
- `PI_PROTOCOL_VERSION 2` added as a **separate** constant. Firmware version and wire-format version are different compatibility concepts: a firmware bump that does not touch the wire must not invalidate a working receiver, and a wire change must be visible even if the firmware version is untouched. v1 → v2 because v2 changes the payload shape of both LIVE_FRAME and RESULT, and a version number that has appeared in the tree is not reused for a different layout.
- **Module-local product versions stripped from all 21 files** (headers and .cpp alike). Original file permissions preserved exactly — several were read-only and were restored to read-only afterward.
**Proof:** `grep -rn "Guitar Rig Analyzer[ ]*v0\.[0-9]" *.h *.cpp *.ino` returns nothing; all three targets compile; the banner and HELLO both report 0.6.0 from the single constant.

### TODO-37 — Reconcile README, runbook and as-built drawings with ADR-001 🟢 **DONE 2026-09-11**
**Why:** stale architecture docs are more dangerous than cosmetic debt in this
repo specifically, because AI assistants are first-class readers of it. A future
agent reading the old README would reconstruct the wrong project — and the audit
that opened this track found exactly that happening across four documents at once.
**What was done:** README architecture/tech-stack/prerequisites/repo-structure
sections corrected (and its stale claims about non-existent directories removed);
the runbook's `USE_PI_DISPLAY` claim replaced with the real `DISPLAY_TARGET`
mechanism and its Phase 9 parts-list mismatch fixed; a Pi UART row added to the
as-built reserved-hardware list in `tools/gen_schematic.py` and the drawings
regenerated.

---

## Track B — Firmware-only (deferred until hardware catches up, or independent of it)

### TODO-11 — Complete the signal_router promotion (steps 3-6), one step per matching hardware phase — not ahead of it ⚪ blocked on Track A
**🚦 ADDED 2026-09-16 — PREREQUISITE before any internal-stimulus arm path becomes reachable (from the ADR-004 ordering audit, journal 2026-09-16 (5); code-derived).** `measurementEngine_update()` in **ARMED with internal stimulus does not consume the fresh MEASURE block** (`measurement_engine.cpp:784`), so a stale block can reach CAPTURE and open the raw-sample drain gate (`:831–835`, `:895`). Combined with `audioCap_update()` returning clip events before ROUTE_CHANGED (`audio_capture.cpp:792–803`), a return-source change could then let post-switch raw samples be accumulated, and potentially finish a mixed-topology RESULT, before the delayed abort, **if `abort_on_clip = false`**. Unreachable today (the only arm caller is `m`: EXTERNAL, `abort_on_clip = true`). **Close it before enabling injection. Do not pick the fix yet:** candidates include always consuming the block in ARMED and giving ROUTE_CHANGED priority over clip. Decide with its own trace once injection is active.
**🚦 ADDED 2026-09-13 — resolve the functional requirement behind Rig Send (pin 17) detection separately. See [ADR-003](../docs/adr/ADR-003-jack-presence-is-a-ux-feature.md).** Pin 17 gates `can_inject`, and `canInject()` is currently never called. **Do not assume a mechanical jack switch is the answer.** First define what is being prevented: if the concern is injecting a sweep with no rig connected, note that **a plug being present does not prove the downstream rig is connected correctly** — so plug presence may be the wrong signal entirely, not merely an inconvenient one. **Decide the requirement before selecting a mechanism.**
**Why:** `signal_router.h/.cpp`, `signal_router_config_additions.h`, and `audiocap_injection_api.h` are staging code from the documented promotion checklist (`development/README.md`), already moved to the repo root (step 2 done, no `development/` folder remains) but not integrated: no `s_mixer_send` in `audio_capture.cpp`, the generator still only feeds the monitor mixer, `measurement_engine.cpp` never calls `signalRouter_canInject()`. Confirmed by reading the actual files directly, twice (Mac tree and this Claude Project's own docs) — see journal.md 2026-08-25 (3) and (4). **Decision (2026-08-25 (4)):** do not move the files back into `development/` — they're already wired into the live Phase 2 smoke test (`RELAY_SEND_PIN`/`RELAY_RETURN_PIN`) and reverting would be pure source-layout churn with no hardware progress to show for it. Keep them at the repo root, but keep the promotion explicitly marked incomplete/in-progress — do not treat the TODO-1 compile fix as license to also merge the injection audio graph.
**What:** Complete checklist steps 3-6 incrementally, each gated on its own hardware phase actually existing and being testable, not speculatively ahead of it: merge the pin constants into `config.h` now (TODO-1 — pins are already correctly designed, this is integration only, not pin design); add `s_mixer_send` to `audio_capture.cpp` only once the relay/routing hardware it depends on (Phase 6/7) is on the bench; implement `audioCap_setInjectionMode` and the `measurement_engine` arm-time gate (`signalRouter_canInject()`) only once injection can be immediately tested against real hardware, not before.
**Proof:** an INTERNAL-stimulus MODE_LIVE run (not MODE_PRECISION — see TODO-13) shows the actual generated signal present in the RETURN_NODE capture with a rig connected — not silence, not today's monitor-only loopback.

### TODO-12 — Polish result UX in display_engine ⚪ **SUPERSEDED by ADR-001 — do not proceed in this form**
**Status 2026-09-11:** the RA8875 is no longer the product renderer
([ADR-001](../docs/adr/ADR-001-display-architecture.md)). Polishing its result
screen is no longer product work, and doing it now makes the architecture
correction more expensive. **Kept, not deleted** — the panel-geometry reasoning and
the MEASUREMENT-vs-ADVISORY visual requirement below are the real design content,
and they transfer to the Pi's result view as TODO-36 acceptance criteria. The
requirement that the result view show quality **and provenance** is also what
surfaced TODO-34's R2 finding: the provenance string is not on the wire, so the Pi
cannot currently satisfy it either.
**Why (original, retained):** Was the previously-stated next milestone from the software roadmap. Still real work, just not the current execution path — the project has moved into hardware bring-up (Track A) first.
**What:** Using the existing panel geometry — meter panel (quality/provenance header), spectrum panel (insight list), TF panel (measured `tf_cal_mag_db` curve using existing TF chrome) — refine the result screen's layout, readability, and the MEASUREMENT-vs-ADVISORY visual distinction in the insight panel.
**Proof:** A measurement run using the currently supported MODE_LIVE complex-FFT path (not MODE_PRECISION — `arm()` still rejects that, see TODO-13) reaches RESULT and the display clearly shows quality/provenance, the TF curve (correct NaN pen-lift on invalid bins), and an unambiguous MEASUREMENT-vs-ADVISORY insight list, reviewed against real captured data.

### TODO-13 — Precision FFT rebinning (MODE_PRECISION / MODE_LF) 🔴
**Why:** These modes exist conceptually in `measurement_core.h` but `arm()` rejects them (confirmed still true on 2026-08-25) because the OCRAM accumulator and bin-remapping logic don't exist yet.
**What:** Implement the OCRAM accumulator and frequency-bin remapping for MODE_PRECISION and MODE_LF; only remove the `arm()`-time rejection once the full path produces real, correctly-rebinned data end to end.
**Proof:** `arm()` accepts MODE_PRECISION/MODE_LF, a measurement completes through RESULT with correctly rebinned data, verified against the validation harness's known-response tests — not just "it produces numbers."

### TODO-14 — Touch UI interaction ⚪ **SUPERSEDED by ADR-001 — touch moves to the Pi**
**Status 2026-09-11:** touch interaction is a Pi-side deliverable (TODO-36), not an
RA8875 one. `RA8875_INT_PIN` stays defined for the debug backend but no touch
handler will be written for it. **Kept, not deleted** — the proof criterion below
is the valuable part and transfers verbatim: whatever drives a state transition,
touch or packet, must produce the *identical* transition the serial command
produces, and live updates must still only occur in IDLE / ARMED. Under ADR-001
this becomes a stronger constraint, since the Pi must route control actions back
through the same `measurement_engine` entry points rather than modelling state
locally.
**Why (original, retained):** `display_engine` renders the result view and insight panel; all measurement control still goes through the serial `x` command.
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

