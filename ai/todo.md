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

### TODO-4 — Phase 4: OPA1642 SOURCE buffer 🟡 **resuming under a documented temporary bring-up config** — see journal.md 2026-09-05 (3)
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

### TODO-23 — Buffer input impedance is ~100 kΩ — too low for a guitar pickup 🔴 lands on Phase 5
**Why:** The input bias resistor to VGND is 100 kΩ (confirmed by the runbook's own corner-frequency arithmetic, R = 100 000), setting input impedance at ~100 kΩ. The runbook's Phase 4 Background justifies the JFET choice by noting pickups are high-impedance (6–250 kΩ) — then loads them with 100 kΩ, which rolls off highs and reduces output. Standard guitar-amp input is ~1 MΩ. **The runbook argues for a high-impedance front end and builds a comparatively low-impedance one.**
**What:** Harmless at Phase 4 (a phone is a low-impedance source) but it bites at Phase 5's first real instrument jack. Raise the bias resistor toward 1 MΩ, which **also shifts the input RC corner** — resolve jointly with TODO-19 and TODO-21 rather than in isolation, since all three touch the same network.
**Proof:** a guitar plugged into the Phase 5 jack shows no audible/measurable high-frequency loss versus the same guitar into a known 1 MΩ amp input.

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

### TODO-26 — Both nodes read `+0.0 dBFS` 🟡 **FAULT CLEARED 2026-09-06 — but possibly MASKED, not fixed. Verify with scope disconnected.**
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
**⚠️ CONFOUNDED — the 1 kHz stimulus vanished during this test.** Raw windows are low-level noise (±100), not the ±280 coherent square wave seen in all six prior dumps; `TF confidence: 0%`, every spot-check `---`. The tone stopped or the input wiring was disturbed when the clip was attached. **Re-run with the tone confirmed live and measured at column 30** before treating this as settled — the outlier conclusion above survives because it is measured against the noise floor, but nothing else from this round should be relied on.
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

### TODO-24 — Pin 8 collision: RA8875 reset vs I2S RX_DATA0 🟡 **config fixed 2026-09-05 (8→5, compile-verified); rewire + boot-order halt still outstanding**
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

### TODO-19 — Decide C1 input coupling cap value before trusting any low-frequency measurement 🔴 low priority, but a correctness trap
**Why:** C1 = 10 nF gives a high-pass corner of ~160 Hz — *above* the low-E fundamental at 82 Hz. The runbook's own Phase 4 Background flags this and suggests 0.1 µF ceramic (20 on hand) for a ~16 Hz corner. Left as-is, low-frequency rolloff will look like a fault or, worse, be silently accepted as real rig response.
**What:** Keep 10 nF for topology validation. Before any bass-inclusive measurement, either swap to 0.1 µF or explicitly document the 160 Hz floor as a known measurement limit.
**Proof:** either the swap is made and a sub-100 Hz tone passes at expected level, or the 160 Hz corner is recorded as a stated limitation everywhere results are reported. Interacts with TODO-4's note that Test 1's pass band starts at 200 Hz.
**The corner has never actually been measured** — TODO-4's 1 kHz reading is *consistent with* 159 Hz but constrains it only to ~125–205 Hz, since a high-pass probed 6× above its corner barely moves. **Run one frequency sweep and use it for both purposes:** readings at ~40, 80, 159, 320, 640 Hz, checking for −3 dB at the corner and a 6 dB/octave slope below it. That measures the real corner *and* supplies this item's decision evidence in a single pass.

### TODO-20 — Backfill Phase 1's verify numbers — it PASSED, but predates this journal 🔴 record-keeping gap, not a build gap
**Why:** Phase 1 passed and the +5 V rail worked — confirmed by Conley 2026-09-03. It has no journal entry only because the journal was created *after* Phase 1 was completed, and no TODO item because Track A's numbering starts at TODO-1 (compile blocker) / TODO-2 (Phase 2). **This is an artifact of when record-keeping started, not evidence of an unverified build** — an earlier draft of TODO-4 wrongly inferred the latter. Corrected here so no future session re-derives that mistake.
**What:** Log Phase 1's end-of-phase results retroactively if the numbers can be recalled or re-measured: +5 V rail 4.85–5.10 V; VGND 2.40–2.60 V; VGND midpoint symmetry within 0.05 V; GND continuity top-blue↔bottom-blue; **no** top-red↔top-blue short. Note Step 2 (line 561) sources 5 V from the **`VUSB` pad**, not VIN — see TODO-4.
**Proof:** Phase 1's five checks present in journal.md with values, so the evidence chain from Phase 1 forward is continuous and the "last known-good state" is documented rather than reconstructed from memory.
**Broader lesson worth keeping:** the journal starting mid-build means **the earliest phases have a silent evidence gap**. When reasoning about regressions, "no record" here does not mean "never tested" for anything at or before Phase 1.

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
**Known outstanding at time of writing (2026-09-01):** Phase 3's "All four GPIOs respond to GND taps" line is **not** yet tickable — only its electrical half is proven; the `JACK_CHANGED` / `ROUTE_CHANGED` event half is deferred to TODO-11. Phase 2's Serial evidence is also incomplete (TODO-2). Both must be closed here, not waved through.

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

