# Guitar Rig Analyzer — AI Journal

Purpose: a running record of *why* decisions were made on this firmware, written for AI readers (Claude, ChatGPT, etc.) picking up the project cold. This is not a changelog of code diffs — it's the reasoning behind them.

How to use this file:
- Newest entry goes at the top, directly below this header block. Older entries move down. Never delete an entry — if a past decision was reversed, add a new entry that says so and explain why; leave the old one in place for the history.
- One entry per session/decision, not per commit. Skip trivial stuff.
- Each entry should answer: why did we do this, what did we consider/reject, and what should the next session know.
- If you are an AI starting a session on this project, read this file top-to-bottom before touching code — the most recent entries are the most likely to still be relevant.
- **Source-of-truth precedence (added 2026-08-25):** the checked *active local tree* (`/Users/conleyvidal/Developer/guitar_rig_analyzer/` since 2026-09-21 — it was `/Users/conleyvidal/Desktop/guitar_rig_analyzer/`, now frozen as evidence; see 2026-09-21 (8) — verified by actually reading the files, not by reading about them) is authoritative for current implementation status. Below that: runbook/bench observations (`docs/breadboard_bringup_v3.md` and actual serial-log/photo evidence) > explicitly staged design docs (contracts, patch headers, `development/`-style staging code) > historical/project-upload snapshots. Never infer "implemented" from a contract doc, a patch file, a staged source file, or a newer-looking version header/comment — verify the actual call path in the active build tree before recording a feature as done.
- **Source-of-truth precedence — extended to REQUIREMENTS (added 2026-09-13):** the rule above governs *implementation state*; it now governs *requirements* too. **Runbooks, diagrams, TODO acceptance criteria, and prior design assumptions must not override observed hardware behaviour, active code paths, or explicitly accepted ADRs. When they conflict, reconcile the documentation rather than forcing the implementation to satisfy a stale assumption.** Earned the hard way: a runbook drawing asserted a switch contact the physical jack did not have, and a TODO acceptance line then kept Phase 5 blocked on a GPIO transition that no code in the tree reads. See 2026-09-13 (7) through (13), and `docs/adr/ADR-002` / `ADR-003`.

---

## 2026-09-26 (6) — **TODO-58 was not "wire up the missing caller." The packet would have transmitted fabricated physical state.** Schema corrected before first transmission; two dishonest booleans removed; `UNKNOWN` given a representation. **Compile-verified only**

**What the design pass changed.** The item began as a one-line fix: `presentation_routerStatus()` is implemented in all three backends and called nowhere, so call it. Inspecting *what the packet would say* stopped that.

**🔴 Every `jacks` bit was a pullup artefact.** All four detect inputs are `INPUT_PULLUP` ([signal_router.cpp:208-211](../signal_router.cpp#L208)) with **nothing attached**. `config.h` says so about three of them in its own comments — *"Phase 7 — not built, sense unverified"* — and the fourth, marked `INSTALLED`, is a **two-terminal jack with no switch terminal** (TODO-44); TODO-5 states plainly that *"pin 16 currently feeds nothing at all."* The D2F-01L microswitches intended to provide detection are parts-blocked at zero on hand.

So adding the missing call would have begun streaming a physical claim that **no hardware supports**, to a renderer whose job is to display physical claims. The defect would have been introduced by the fix.

**🔑 The representational problem, which is the real content of this slice.** `false` cannot mean both *"no plug"* and *"no detector."* Overloading it is how a renderer ends up drawing a confident ABSENT from a floating pin — the same class of error as the 2026-09-07 clamp rail being drawn as a measurement. The packet now carries **two masks**: presence, and availability. Per detector: `available=0` → **UNKNOWN**; `available=1, present=0` → ABSENT; `available=1, present=1` → PRESENT. The Pi exposes it as a three-valued `Detect`, so a renderer cannot accidentally read presence alone.

**Two fields deleted rather than renamed, which was the sharper call.** The instinct was to rename `route_valid` and `can_inject`, since both are documented as historically misnamed. Renaming a byte while preserving a misleading computation helps nobody.

- `route_valid` was `(selected_return != NONE)`. ADR-004 guarantees a selection always exists, so it is a **tautology** — always true, fully recomputable from `return_source`, which is already on the wire. It carried zero information and its name asserted connectivity it never established.
- `can_inject` was that tautology **AND** an unavailable detector. Its honest value today is UNKNOWN, and there is no Boolean encoding of that.

Then the decisive evidence: **neither has a consumer.** `signalRouter_canInject()` and `signalRouter_canMeasure()` are defined and called nowhere; [.ino:386](../guitar_rig_analyzer.ino#L386) records that the measurement engine does not consult them. They existed only to be transmitted. Removing them costs nothing, and injection readiness can return as an authoritative fact when the Teensy can actually establish it. **Prefer primitive facts the producer owns over derived booleans it cannot guarantee.**

`injection_active` was kept, and the distinction is worth stating because it looks like the same case: HELLO's capability bit answers *"can this build inject?"*, ROUTER_STATUS answers *"is injection active right now?"*. Different facts. Constantly 0 today, and **truthfully** 0 — not unknown.

**Masking at the presentation boundary, not in the router.** `RouterStatus` keeps the **raw** debounced readings so bench diagnostics still see actual pin state; `data_sender` ANDs presence with availability on the way out. Framed deliberately as a **wire-contract obligation rather than sanitising bad data**: the raw GPIO value is not wrong, it simply is not evidence of presence when no detect conductor exists. Two layers, two jobs — the router observes hardware and owns routing authority, the presentation boundary guarantees what escapes is externally valid.

**Lifecycle: on-change + 1 Hz repair, and the trigger path needed no new coupling.** The `.ino` already owns this pattern — it calls `presentation_restoreLive()` immediately after `measurementEngine_acknowledgeAbort()`. Two call sites give the same shape: after a successful `signalRouter_setReturnSource()`, and on `JACK_CHANGED` from the `RouterEvent` that was previously `(void)`-discarded. **`signal_router.cpp` never learns a transport exists.**

Unlike TODO-57, on-change is tractable here: the authoritative field has **exactly one** mutation path, not eleven scattered transitions. The periodic path remains independently sufficient — if every on-change emission vanished, a reconnecting Pi still converges in a second. 1 Hz rather than STATE's 500 ms because route state is slowly-changing *configuration*, so it belongs in HELLO's cadence tier. **I deliberately did not inherit STATE's cadence**, and the distinction is recorded so the next packet does not inherit this one's either.

*(The `JACK_CHANGED` branch is unreachable today — no detector can change — and is wired now so the lifecycle is complete and testable when detectors are fitted, rather than leaving the periodic path silently carrying the entire contract.)*

**Corrected in place, staying at v2, and the reasoning matters.** The superseded layout had **zero firmware callers**, so it never formed part of an observed or deployed wire contract. Bumping the whole transport to v3 would imply a compatibility boundary that does not exist for this packet. Recorded explicitly as a *pre-first-transmission correction* — and this was the cheapest moment it would ever be fixable, which is the general lesson: **a packet that has never been transmitted is free to fix; one that has is not.**

**This packet stopped being the weak exception.** It previously had a single round-trip vector, which cannot catch a field reorder because encoder and decoder move together. It now has a structural guard that reads the **firmware builder**: every byte offset, the presence-AND-availability masking, the jack bit positions in *both* masks, and the absence of the removed fields. Plus an availability guard asserting all four flags are 0 — and if someone raises one, **that test should fail**, with the fix being to record as-built evidence rather than edit the test.

**Evidence.** `_PI` and `_NONE` compile clean with zero warnings. 164 tests pass (138 → 164). Negative controls, each reverted: dropping the availability mask from `payload[0]` fails the layout guard; raising a detector flag without evidence fails the availability guard.

**🔺 EVIDENCE BOUND.** Offline and compile only. **NOT FLASHED**, no serial session, no relay, generator, injection or validation. Physical jack detection remains unbuilt — this slice makes the *absence* representable, it does not make detection work. Phase 9 untouched.

**Sequencing — and this is a real transition.** With session identity (TODO-56), measurement state (TODO-57) and route state (TODO-58) all now representable, the known producer-observability holes are closed. **The next useful evidence jump is no longer another layer of offline architecture — it is a real captured Teensy byte stream.** Everything built across these five slices proves that two implementations agree with one author's reading of the source. None of it proves the instrument agrees with them.

**Portfolio note.** Five slices, five defects, and this one completes the taxonomy. TODO-56: the producer never says it. TODO-57: the producer says it only where nobody is listening. TODO-59: the producer says it correctly and destroys it in transit. TODO-58: **the producer says something it cannot know.** That last is the subtlest and the only one a wire-level test would never catch — the bytes would arrive intact, pass CRC, decode cleanly, and be false.

---

## 2026-09-26 (5) — **TODO-57 implemented: `DS_PACKET_STATE` 0x08, periodic at 500 ms. Every measurement state is now observable, and a dropped ABORTED self-heals.** Two verification questions were answered before writing code, and one of them made the design *more* restrictive

**What was broken.** The only carrier of measurement state was LIVE_FRAME byte [0], and `presentation_updateLive()` is gated to `IDLE|ARMED` ([.ino:748-756](../guitar_rig_analyzer.ino#L748)) — so that byte was effectively a two-value field, CAPTURE/PROCESSING/RESULT/EXPORTING were never observable, and a Pi attaching during a sticky ABORTED got geometry and then silence. Two comments in `data_sender.cpp` and one clause in TODO-34 asserted a safety net that did not exist.

**Why periodic, not transition-triggered — the evidence inverts the intuition.** "Announce on change, repair periodically" sounds strictly better. The call-site evidence says otherwise: `measurement_engine.cpp` has **16** `transitionTo()` sites, `update()` ever returns only **5** non-`NONE` events, and `arm`, `returnToLive`, `acknowledgeAbort` and `exportToSD` transition inside *command functions* that never pass through `update()`. `MeasurementEvent::STATE_CHANGED` exists and **the `.ino` never handles it.** Transition-triggered announcement would mean wiring ~11 currently-silent transitions across two call paths, and **its failure mode is a missing announcement — the exact defect being repaired.** A periodic snapshot reads the authoritative getter and needs none of that plumbing. Transition-triggered remains available later as an *optimisation* for latency, which is a different problem from observability.

**✅ Verification 1 — is a coherent state/reason pair obtainable?** There is no combined API; two separate getters. The instruction was to stop rather than invent synchronisation if they could not be read coherently. They can, for **two independent reasons**:

1. **The engine maintains the pairing itself.** `abortTo()` sets `s_abort_reason` **before** `transitionTo(ABORTED)`; `acknowledgeAbort()` clears it **before** `transitionTo(IDLE)`; `arm()` clears it too. So `IDLE + CLIP_SOURCE` — the exact combination we did not want to be able to emit — is **unconstructible**, regardless of interleaving.
2. **There is no interrupt path.** No ISR, no `volatile`, no `attachInterrupt` anywhere in `measurement_engine.cpp`. Nothing can transition between two adjacent reads in loop context.

(1) is the stronger guarantee because it does not depend on threading at all. (2) is the undocumented precondition that would break if the engine were ever driven from a timer, so `sendState()` says so in a comment. **No API change was needed and none was made.**

**✅ Verification 2 — and this one tightened the design.** The ruling was to treat `audio_block_counter` as timestamp-like evidence and not build newer-than logic on it. Checking the implementation turned that from prudence into necessity: `audioCap_getBlockCounter()` is not a counted variable at all but a **pure computation**, `(uint32_t)(micros() * SAMPLE_RATE / (AUDIO_BLOCK_SAMPLES * 1e6))`. Two consequences:

- Reading it is inherently atomic from any context — no shared state, so no synchronisation question.
- **It wraps to zero roughly every 71.6 minutes and never exceeds ~1.48e6.** It is *not* a monotonic 32-bit counter.

So a newer-than comparison against it would not merely be unproven, it would be **wrong** — an observation from 72 minutes in would compare as older than one from a minute ago. The restriction is now documented with that reason in both the firmware header and the Pi decoder, which makes it much harder to "optimise" away later than a bare instruction would have been.

**Two reasons, and the difference is deliberate.** `abort_reason` (enum) rides in every snapshot: the machine-readable fact, repairable, survives a dropped event and a late attach. The ABORTED packet keeps the prose. So a Pi that attaches after an abort **knows why but was never told the wording** — `abort_reason_code` is set, `abort_reason` is `None`. That is honest rather than degraded, and a test pins it, because the tempting mistake is to treat a missing string as a missing abort.

**No RESULT-pending guard on STATE, on instruction, and the consequence is recorded rather than hidden.** TODO-59 owns transport atomicity centrally; duplicating the check per producer is what made TODO-59 possible in the first place. The cost is that `state_dropped` counts **both** causes of refusal — no UART room, and the atomicity invariant. `blocked_by_result` disambiguates at the aggregate level, and both the struct comment and the `u` diagnostics line say so. Worth contrasting with HELLO, whose outer gate was *kept* for efficiency and statistics-clarity reasons: the difference is that HELLO's gate is not load-bearing for safety, and it is now documented as such.

**The false comments are corrected — both of them.** The ABORTED note and the VIEW note both claimed *"measurement_state rides in every live frame"*. Both now name the STATE packet and state why the live frame never could have done the job. TODO-34's mitigation clause got the same correction, because T1 is where someone would rely on it.

**Evidence.** `_PI` and `_NONE` compile with **zero warnings**. 138 tests pass (123 → 138). The ones that matter: every previously-unobservable state now reaches the model; **a late attach learns a sticky ABORTED with no ABORTED event ever sent**; a dropped ABORTED self-heals; `abort_reason` is legitimately `None` while the code is known; and wire positions are pinned for all four fields, so dropping the reserved bytes would fail rather than silently shifting the block counter. Two negative controls, each reverted: drifting the firmware cadence to 1000 ms fails the sync test; making STATE stop latching on ABORTED fails two tests.

The drift guard earned its keep again — it failed immediately on `DS_PACKET_STATE` not being in the packet-id mapping, in **both** directions, which is exactly the "new packet type added to one side only" case it was built for.

**🔺 EVIDENCE BOUND, unchanged.** Compile and offline only. The parser and the firmware still share one author's reading of the header. **NOT FLASHED**, no serial session, no relay, generator, injection or validation. No Phase 10 step passed; Phase 9 untouched.

**Next: TODO-58**, not the renderer. Route state is the last thing the producer still cannot tell the Pi.

**Portfolio note.** The sequence TODO-56 → 57 → 59 is worth keeping as one story: *fix the geometry announcement → discover state has the same defect → while designing that fix, discover the transport destroys results.* Each was found by asking the next obvious question about the previous one, and none would have been found by reading packet definitions. The design-gate discipline — stop, report, get a ruling, then build — is what made that chain visible instead of collapsing it into one large commit where the third defect would have been attributed to the first two.

---

## 2026-09-26 (4) — **TODO-59: a best-effort packet written during a RESULT drain lands INSIDE the result and destroys it — while the Teensy counts it as sent.** Fixed as a central transport invariant, not a per-producer gate. **Compile-verified only; TODO-57 deferred behind it**

**How it was found, which matters more than the bug.** It surfaced while answering a routine design question for TODO-57: *does a new STATE packet need sequence numbers?* Working out whether packets could be reordered meant tracing how bytes actually reach the UART — and that showed two independent writers to the same stream with nothing arbitrating between them. The defect was not in the code being designed; it was in the code that design would have sat on top of. **Asking "what could reorder this?" found something that reorders nothing and corrupts everything.**

**The defect.** `dataSender_service()` drains a staged RESULT in chunks across loop iterations, writing straight into the UART ring. `trySendBestEffort()` wrote to that same ring with **no result-pending interlock** — only a `txRoom()` check. Anything emitted between two drain passes therefore landed **inside** the RESULT's byte stream. The receiver consumes the interleaved packet as RESULT payload, fails the CRC, and **the whole result is lost.**

`dataSender_sendResult()` already knew this hazard and guarded RESULT-vs-RESULT ([data_sender.cpp:539-545](../data_sender.cpp#L539)) with the words *"interleaving two packets would corrupt both."* **The same reasoning was simply never applied to event packets.** The knowledge was in the file; its scope was too narrow.

**The part that explains why it survived review: the SMALL packet is the dangerous one.** After `dataSender_service()` returns, the loop has exited with *either* the result complete *or* `txRoom() == 0` — so a big packet is refused by the room check and looks safe. But the UART keeps draining at ~46 B/ms, so by the time another producer runs a few dozen bytes are free. A **12-byte STATUS (`"Ready"`) fits. A 1689-byte live frame does not.** Every intuition that says "watch the big packets" points the wrong way here.

Most reachable path: clip-status messages at [.ino:759-771](../guitar_rig_analyzer.ino#L759) are **outside** the live-display gate, so `presentation_status()` fires during a RESULT drain whenever the player is still making noise — precisely when a measurement has just completed. Every RESULT is exposed: minimum framed size is 8356 B against a 4096 B buffer, so every result takes ≥3 drain passes.

**🔺 The worst property is not the loss — it is that the loss is invisible from the Teensy.** `results_sent` increments regardless: it counts bytes accepted into the UART. So the firmware reports success for a result the Pi never received, and the symptom presents as a Pi-side CRC problem. **A defect that blames the other end is the expensive kind.** `results_sent`'s meaning is now documented at the field: there is no return path and no acknowledgement in this protocol, so it is a transmitter statistic and cannot be cited as delivery evidence. TODO-34 carries the same warning, because T1 is where someone would be tempted to use it.

**The fix, and the argument for where it lives.** Stated as a transport invariant rather than a rule producers must remember:

> While a staged RESULT is draining, no independently framed best-effort packet may write bytes to the stream.

Enforced in `trySendBestEffort()` — the single choke point that **all six** best-effort packet types pass through, LIVE_FRAME included via its own call at [:510](../data_sender.cpp#L510). The alternative was gating each producer, which would have worked until the next packet type was added by someone who did not know to do it. **An invariant that can be forgotten is not an invariant**, and this codebase had just demonstrated that with TODO-58's never-called publisher.

**The caller audit ran before the guard was written, not after.** The instruction was explicit — do not assume a central guard is safe merely because it looks obviously right. All six callers are best-effort by documented contract, so no exception was found. One nuance is worth keeping: **ABORTED and VIEW justify their droppability with the claim TODO-57 proved false.** Their policy is best-effort; their safety net does not exist yet. Dropping them during a drain is still strictly better than corrupting the RESULT, which loses the result *and* the event — but it is a reason to keep TODO-57 next in line rather than a reason to relax.

**The HELLO gate is kept, and its purpose was rewritten rather than left to imply something untrue.** It is no longer what makes the announcement safe — the central invariant is. It stays for two stated reasons: it avoids building 40 bytes and a CRC only to have them refused, and it keeps `hello_dropped` meaning *backpressure* rather than accumulating a drop every second of every RESULT drain. **I originally justified that gate as "don't compete for bandwidth." That was under-described: it was preventing stream corruption and I did not know it.** Worth recording — the gate was right for a reason I had not identified, which is luck, not design.

**Evidence, in two tiers that are not interchangeable.** 123 tests pass (113 → 123).

*Consumer regression (`OBS`):* the discovered stream shape is constructed and replayed — the corrupted RESULT is rejected rather than rendered, the spliced packet itself **still arrives**, and the stream recovers. That middle one is how the defect would present on a bench: **status text updating normally while measurements silently fail to appear.** A clean-result control stops the others passing for the wrong reason.

*Source structural (`OBS` of source, NOT of execution):* the guard exists in `trySendBestEffort()`, precedes any UART write, is counted, and **exactly two functions in the file write to the UART**. The last is the coverage check — a future direct writer would bypass the choke point entirely, and nothing else would notice.

Two negative controls, each reverted: removing the invariant fails two tests; adding a third direct UART writer fails the coverage test.

**Two test-writing mistakes, both mine, both instructive.** The UART-writer scan first matched `while (...)` inside the drain loop — fixed by anchoring function definitions to column 0. Then it matched `DS_UART_PORT.write` inside this file's **own banner comment**, which warns future authors about exactly this hazard. A structural test that reads prose as code is a structural test that lies; comments are now stripped, preserving line offsets.

**🔺 NOT PROVEN: that the firmware guard executes correctly.** The source tests prove it is present, not that it runs. That needs a captured Teensy stream with a RESULT delivered while clip transitions fire — bench work, and it is now part of TODO-59's proof line. `_PI` and `_NONE` compile with zero warnings. **Nothing flashed, no serial session, no relay, generator, injection or validation. Phase 9 untouched.**

**Sequencing.** TODO-59 first and isolated, exactly as directed — it protects every future producer, so TODO-57's STATE packet and TODO-58's ROUTER_STATUS now inherit the invariant by construction rather than each having to remember it. TODO-57's approved design stands: packet `0x08`, periodic-only at 500 ms, authoritative state + abort reason + reserved + canonical audio block counter.

**Portfolio note.** Four slices, four defects, and the pattern has sharpened. TODO-56, 57 and 58 were all *"the producer never says this."* TODO-59 is different: **the producer says it, correctly, and then destroys it on the way out.** All four were invisible to a protocol audit that examined packet *contents* — because contents are what an audit naturally examines, and none of these are content defects. They are lifecycle and concurrency defects, and the only thing that surfaced them was building the consumer and asking, at each step, *"what would I need in order to actually use this?"*

---

## 2026-09-26 (3) — **Receiver state model built offline. The design pass that preceded it found TWO more producer-side defects — including a documented safety net that is simply false.** UNKNOWN is a first-class state because the firmware cannot currently say otherwise. **No firmware change, no bench action, not committed**

**What the design pass was for, and why it ran before any code.** The rule for this slice was: inspect, propose the lifecycle, stop at the decision gate. That gate is what produced the two findings below. Had the model been written first, both would have been absorbed into Python as "the way it is" and become invisible — which is exactly the failure this project keeps catching one layer too late.

**🔴 F1 / TODO-57 — a documented safety net is FALSE.** `presentation_updateLive()` is gated to `IDLE | ARMED` ([.ino:748-756](../guitar_rig_analyzer.ino#L748)): in CAPTURE, PROCESSING, RESULT, EXPORTING and **ABORTED**, no live frame is sent at all. So the `measurement_state` byte at LIVE_FRAME offset [0] is effectively a **two-value field**.

That matters because [data_sender.cpp:681](../data_sender.cpp#L681) states *"measurement_state rides in every live frame, so the Pi still learns the fact"* — and **TODO-34 cites exactly that line as the mitigation for a dropped ABORTED**. It does not hold. During ABORTED there are no live frames; if the best-effort ABORTED packet drops, the Pi never learns the abort happened. It observes live frames stop, then resume showing IDLE. **The most safety-relevant state in the machine has the weakest delivery guarantee on the wire, and the compensating control written into the source does not exist.**

**🔴 F2 / TODO-57 — a reconnecting Pi cannot learn measurement state at all.** HELLO carries geometry, not state. Combined with F1, a Pi attaching during a sticky ABORTED receives HELLO and then silence, and cannot distinguish *"not IDLE/ARMED"* from *"link dead"* from *"Teensy wedged"*. **This is TODO-56's exact shape one layer up:** state announced once as an event with no way to re-obtain it. TODO-56 fixed it for geometry; measurement state still has it.

**The fix that was explicitly ruled out, and why that ruling is right.** The cheap repair is to widen the LIVE_FRAME gate so frames flow in every state. Rejected at the gate: that couples **state observability to DSP/live-stream availability**, two things that must be able to fail independently. LIVE_FRAME is a live-data product, not a state channel. Pushing a full spectrum frame through CAPTURE merely to carry one byte would also add transport load precisely when the instrument is busiest. The likely correct shape is a small authoritative state packet, or a periodic state announcement on the TODO-56 pattern — its own design pass, its own gate.

**🔴 F3 / TODO-58 — `ROUTER_STATUS` has zero callers.** `presentation_routerStatus()` is implemented in **all three** backends and `dataSender_sendRouterStatus()` builds a complete payload — and **nothing in the firmware calls either**. The packet type, the payload builder, the wire documentation and the presentation API all exist; the call site was never written. The Pi therefore cannot learn jack presence, return source, route validity or monitor mode, all of which the Live view is specified to show. Not a protocol defect — the parser decodes it correctly and is tested. Kept as a **separate, lower-priority** item from TODO-57: this is telemetry publication, that is measurement-state authority.

**Four rulings, and the one that was corrected at the gate.** I proposed that `VIEW(LIVE)` clear the abort latch. That was wrong, and the correction is worth recording because the reasoning generalises.

`presentation_restoreLive()` is called from **two** places: after `measurementEngine_acknowledgeAbort()` ([.ino:590](../guitar_rig_analyzer.ino#L590)) *and* after `measurementEngine_returnToLive()` from a RESULT view ([:600](../guitar_rig_analyzer.ino#L600)). `presentation.h` documents it as *"returns the renderer from a result/abort view to the live view"* — a **view** fact. **"The Teensy asked for the live view" and "the measurement engine is no longer ABORTED" are different claims, and the protocol does not make the first imply the second.** The pairing in the `.ino` is an incidental call-site adjacency, not a protocol contract. Treating adjacency as contract is how a boundary erodes one convenient inference at a time.

What *does* clear the latch is an authoritative observation of `IDLE`. That is not the Pi deciding an abort was acknowledged: the firmware defines ABORTED as leaving **only** through `acknowledgeAbort() → IDLE` ([measurement_engine.h:167](../measurement_engine.h#L167)), so an authoritative IDLE **is** evidence of acknowledgement. The rule is implemented against *any* packet carrying a measurement state rather than against LIVE_FRAME, so TODO-57's eventual state packet plugs in with no change here.

**The four rulings as implemented:**

| | Rule |
|---|---|
| **D1** | `UNKNOWN` is first-class. Silence, HELLO, connection and session establishment are **never** mapped to IDLE |
| **D2** | An authoritative `IDLE` observation may clear the latch. `VIEW(LIVE)` may not |
| **D3** | A changed `session_id` ends the previous session; its abort cannot remain the *current* instrument state. Cleared, recorded as **"session ended while abort was latched"**, new session starts `UNKNOWN` |
| **D4** | No promotion into renderable state before a valid HELLO. Pre-HELLO packets are still decoded and counted for diagnostics |

**D3's wording was corrected too, and precisely.** I had written "lost to reboot"; that implies telemetry failed. What is actually known is narrower: **the previous session ended before this receiver observed an acknowledgement.** The Teensy may well have been acknowledged by an operator standing in front of it. The field is named `ended_with_abort_latched` and the record keeps the reason, so the history is a statement of observation rather than of blame.

**`UNKNOWN` deliberately does not live in `protocol.MeasurementState`.** That enum is a *mirror* of the firmware's, and the drift guard fails if it gains a member the Teensy does not have — correctly, because a mirror that drifts is worse than no mirror. UNKNOWN is a **receiver** concept: the Teensy always knows its own state. So it is a separate sentinel in the receiver's vocabulary, and `ObservedState = MeasurementState | Unknown`.

**A test failed for the right reason and taught something.** I asserted that a pre-HELLO LIVE_FRAME would decode-but-not-promote, since its array lengths *are* self-describing from `payload_length`. It does not decode — and should not. **`decim_ratio` is not derivable from the frame**, and without it the per-bin coverage nibbles cannot be interpreted: *"2 of ? source bins clamped"* is not a renderable fact. Deriving a ratio would be assuming geometry, which D4 forbids. The test now pins that reasoning rather than the assumption I started with.

**Evidence.** 113 tests pass (79 → 113), standard library only. Three negative controls, each reverted after confirming it fails:

| Mutation | Result |
|---|---|
| New session assumes IDLE instead of UNKNOWN (D3) | 2 failures |
| `VIEW(LIVE)` clears the abort latch (D2) | `test_view_live_moves_the_view_but_does_NOT_clear_the_abort` |
| Telemetry promoted before HELLO (D4) | 1 failure |

The ADR-001 boundary guard now also covers `state.py` — the module most likely to want to compute something, because "the UI needs to show something" is constant pressure to fill a gap with an assumption.

**🔺 EVIDENCE BOUND, unchanged.** Offline only. No firmware was compiled or flashed, no serial session opened, no relay, generator, injection or validation. The parser and the firmware still share one author's reading of `data_sender.h`; wire agreement needs a captured Teensy stream. **No Phase 10 step is passed. Phase 9 untouched.**

**Sequencing changed as a result of this pass.** The next slice is **not** the renderer. It is the producer-side state-observability design for TODO-57 — because building UI on a state channel that cannot represent a sticky ABORTED after reconnect would make that defect invisible exactly where it matters most.

**Portfolio note.** Three slices, three defects, one pattern: **the consumer is what audits the producer.** Protocol v2 was audited once — 17 findings, five severe — and that audit asked *"is every verdict on the wire?"*. It never asked *"can a receiver that arrives late obtain this?"*. TODO-56 (geometry), TODO-57 (measurement state) and TODO-58 (route state) are all the same unasked question, and all three survived an audit that was genuinely thorough about a different one.

---

## 2026-09-26 (2) — **TODO-56 fixed in source: HELLO is now re-announced at 1 Hz and carries a session id.** Option B rejected on evidence, not preference. The generation mechanism was chosen by elimination and the rejects are recorded. **Compile-verified only — not flashed, no bench action**

**Decision, and why it was not the obvious one.** Two mechanisms could fix a HELLO that only exists at startup: periodic announcement, or an explicit Pi→Teensy request. The request option produces cleaner reconnect semantics *and* lays groundwork the touch UI will need anyway, so it was not dismissed — it was evidence-checked and deferred.

What the evidence said: **there is no inbound path in this firmware at all.** No `Serial1.read()`, no `.available()`, nothing. And [presentation.h:44](../presentation.h#L44) explicitly refuses to host one — *"IF Pi → TEENSY INPUT IS EVER ADDED, IT DOES NOT COME THROUGH HERE"* — because control crosses a trust boundary presentation deliberately does not have. So Option B is not "add a handler"; it is "build the firmware's first externally-controlled input surface, with its own boundary, its own validation and its own ADR." Option A is ~15 lines inside a function that already runs every loop iteration and is already non-blocking by contract.

**Two hazards found while costing Option B, worth keeping even though we deferred it.** `Serial1.begin()` enables the Teensy's receiver and **nothing ever drains it** — today those bytes accumulate in a ring buffer and are silently discarded, which is why nobody has noticed. And **Raspberry Pi OS ships a login console on that UART by default**; the runbook never said to disable it. Harmless while nothing reads RX; the moment a command parser exists, it would be reading kernel and getty output as input. That is now a **[STOP] in Phase 10 step 2**, to be configured while the consequence is still zero rather than diagnosed later as intermittent command injection. A console at the wrong baud also mimics a physical-layer fault, giving one symptom two plausible causes.

**🔑 The part that was not in the original defect: periodic HELLO alone is ambiguous.** A receiver seeing repeated HELLOs cannot tell a routine re-announcement from a **new Teensy session**. Without resolving that, the fix would trade "Pi can never decode a RESULT" for "Pi silently carries stale state across a reboot" — a quieter bug, not a smaller one.

The obvious substitute does not work. `output_block_number` is **16 bits** and wraps on its own roughly every 50 minutes (65536 × 46.3 ms ≈ 3034 s), so "it went backwards" is not sound evidence of a restart. HELLO's bytes `[18-19]`, documented as `reserved (0)`, now carry a **session id**: constant for one boot, different after a restart, and a *changed* value is authoritative evidence that prior state is stale. Size-preserving, no version bump.

**Generation mechanism — chosen by elimination, because "nonce" invites a bad reflex.** The instruction was explicit: do not invent something weak just because we used that word. Four facilities were checked in the Teensy 1.62.0 core before anything was written.

| Facility | Verdict |
|---|---|
| `SNVS_LPGPR0..3` | Survives a **warm** reset. But Teensy 4.1 has no coin cell on that domain, so a **power cycle clears it** — two consecutive cold boots report the same value. **Rejected** |
| `rtc_get()` / `Teensy3Clock` | Same power domain, same weakness without a VBAT cell. **Rejected** |
| `ARM_DWT_CYCCNT` / `micros()` at init | Read at a fixed point in a fixed boot sequence, so **very nearly deterministic**. This is precisely the weak-random trap — and worse, it would *look* random while colliding often. **Rejected** |
| `HW_OCOTP_MAC0` | The chip serial. Constant by definition: it identifies the **board**, not the session, so it cannot discriminate a reboot at all. **Rejected** — though it is the right field for device identity, which HELLO does not carry |

**Selected: a monotonic `uint16_t` boot counter in flash-emulated EEPROM.** The only candidate that satisfies the contract in *every* reboot mode including a cold power cycle — and deterministic, which is what makes runbook step 10 a **test** rather than an observation: the value is predictable and can be read back against the `[DataSender] Session id N` line the Teensy now prints at boot.

The placement objection resolved itself on inspection: `dataSender_init()` runs at [.ino:311](../guitar_rig_analyzer.ino#L311), **before** `audioCap_init()` at :323. No audio is running, so the firmware's only flash write has no acquisition timing to perturb.

**Limitations documented in the source rather than discovered later:** 16-bit, wraps after 65535 boots (harmless — the contract is "changed ⇒ stale", not "ordered"); **not unique across devices**; predictable by design; counts `_PI` boots only, so it is not an instrument-wide boot count; and a blank EEPROM's first boot reads `0xFFFF` and becomes **0**, which is a legitimate value a receiver must not read as "absent". A test pins that last one, because treating 0 as missing is the natural mistake.

**The EEPROM address is reserved in `config.h`, not in `data_sender.h`.** `data_sender.cpp` compiles only for `DISPLAY_TARGET_PI`, so a `_NONE` or `_RA8875` build never touches EEPROM — which is exactly why the reservation has to be global. A future EEPROM user added under a different target would collide, and the symptom would be a Pi convinced the Teensy rebooted whenever some unrelated subsystem wrote its state. A drift test asserts the reservation exists.

**Gating — the one choice that was argued rather than assumed.** Re-announce is gated on `s_result_len == 0` only, so the reliable RESULT path is never made to compete with an announcement. It is **deliberately not** gated on `MeasurementState::IDLE`: HELLO describes the instrument and protocol session, not the measurement. A Pi reconnecting during ARMED, CAPTURE, PROCESSING, RESULT, EXPORTING — or during a **sticky ABORTED**, which stays latched until `measurementEngine_acknowledgeAbort()` — must be able to obtain geometry and reconstruct that state, not sit blind waiting for IDLE. Gating on IDLE would have made the worst reconnect case the one where reconnecting matters most.

**Separate HELLO counters, and why that is not bookkeeping fussiness.** Re-announcement is *expected* to be dropped under sustained backpressure — that is the non-blocking policy working. T1 run 3 suspends the reader deliberately to keep the UART full, so folding HELLO drops into `events_dropped` would add one per second for the whole window and destroy the meaning of a figure the acceptance matrix already depends on. `hello_sent` / `hello_dropped` are therefore their own fields. **Consequence recorded against TODO-34: the T1 report's content has changed, so all four runs must be captured against this build and no earlier report may serve as a control.** Run 1 is unaffected — `data_sender.cpp` is compiled out for `_NONE`.

**⚠️ A method defect found while trying to prove the control run was untouched.** I attempted to show `_NONE` is binary-identical before and after the change by comparing hex md5. The hashes differed. The correct control — **building HEAD twice** — also produced two different hashes, because [.ino:215](../guitar_rig_analyzer.ino#L215) stamps `__DATE__`/`__TIME__` into the firmware. That is TODO-52/53's build-identity feature working as designed, and it means **the build is not reproducible and hash comparison cannot answer questions about source equivalence.**

What was actually established for `_NONE`: section sizes are **byte-identical** (`code:152448 data:72200 headers:8820`), `data_sender.cpp` is entirely `#if`'d out for that target, and the `config.h` addition is a `#define` emitting no code. **Carry this forward: "rebuild the commit and check the md5 matches" is not a valid identity procedure.** The md5 recorded for `44c4680` identifies the flashed *artifact* — which is still sound, because it was compared against the artifact that was flashed, not against a rebuild.

**Evidence.** `_PI` and `_NONE` compile clean with **zero warnings**. `_RA8875` still stops on its **pre-existing** `AUDIO_SHIELD_STACKED` `#error` — verified untouched by this change, not a regression. 79 Pi tests pass (70 → 79): six `session_id` tests including wire-position and the `0`-is-valid case, plus drift checks for `DS_HELLO_REANNOUNCE_MS` and for the `[18-19]` field no longer being documented as reserved. Both new guards verified by negative control — drifting the firmware period to 2000 ms fails the sync test, and making the Pi stop decoding the field fails three session tests.

**🔺 EVIDENCE BOUND, unchanged from slice 1 and worth restating because the work got more convincing, not more proven.** The parser and the firmware still share one author's reading of `data_sender.h`. Offline tests do **not** prove agreement with the compiled firmware on the wire; only a captured real Teensy stream does. **Nothing was flashed. No serial session was opened. T1 remains required, and no Phase 10 step is passed.**

**Bench state untouched.** The board still runs `44c4680`. No relay actuated, no generator or injection enabled, no validation routine run. Phase 9 remains exactly where 2026-09-22 (6) left it — and the Test 4 corner is still uncharacterised; the `1989.0f` figure in the tree is a nominal unloaded reference, not behaviour.

**Portfolio note.** The reusable lesson is about the shape of the original audit. Protocol v2's audit asked *"is every verdict on the wire?"* and found 17 findings. It did not ask *"can a receiver that arrives late ever decode this?"* — and so a defect that makes every RESULT permanently undecodable to a late-attaching Pi sat in the tree, through an audit, until somebody tried to be the receiver. The second lesson is smaller and sharper: the fix that looked complete (announce periodically) was still wrong until the ambiguity it introduced — repeat versus restart — was closed in the same slice.

---

## 2026-09-26 (1) — **Pi receiver slice 1: bytes → typed packets.** 70 offline tests pass; a drift guard now fails if the Python mirror leaves the firmware headers. **Two defects found by writing it — one firmware, one runbook.** No firmware change, no bench action, no Phase 10 step passed

**Problem being solved.** ADR-001 made the Pi 5 the production renderer and TODO-35 raised the Pi/UI path to the critical path on 2026-09-22 (6) for the 2026-11-01 portfolio deadline. The Teensy half of that link has existed since 2026-09-11 — presentation boundary, protocol v2, transport instrumentation. **The Pi half was zero files.** A repository audit at the start of this session confirmed it: the only Python in the tree was `tools/gen_schematic.py` and `tools/analyze_corruption.py`, both unrelated bench tools.

**Was this allowed to proceed while Phase 9 is open?** Checked rather than assumed. TODO-36: *"schema is frozen — write the parser; start the renderer only after T1 passes."* TODO-35: *"Nothing here depends on the Test 4 fixture or its capacitor."* Runbook Phase 10 **step 6** requires a receiver brought up against known data, and step 6 precedes T1 at step 11. So: parser yes, renderer no.

**🔺 DEFECT 1 — the runbook contradicted itself on exactly that question.** Phase 10 **step 12** read *"Only then start the Pi parser/renderer (TODO-36)"* — placing the parser **after** T1 — while **step 6** of the same phase places the receiver **before** it. Both clauses were written on 2026-09-11. TODO-36's status line is the specific rule and resolves it; step 12's wording was the stale half. **Corrected in this pass**, with the reasoning inline so it cannot re-rot. This is the same stale-clause failure mode as TODO-45 and TODO-18, in a section nobody had re-read since it was written.

**🔴 DEFECT 2 — HELLO is sent once, best-effort, and never retransmitted. Opened as TODO-56.** Found by asking a parser-author's question that had not been asked before: *where does the receiver get the array length for RESULT?*

`dataSender_init()` sends HELLO exactly once ([data_sender.cpp:263](../data_sender.cpp#L263)), through `timedBestEffort()` — which **drops the packet if the TX buffer is full** and increments a counter. There is no retransmission, no periodic re-announce, and no request path: `Serial1` RX is reserved but unused, so the Pi cannot ask.

That matters because **HELLO is the only carrier of `fft_bins`, and a RESULT's four `float[fft_bins]` arrays cannot be located without it.** This is not a parser limitation — it is a property of the wire format. The `insight_count` that would let a receiver solve for the array length sits *after* the arrays, so the geometry is genuinely unrecoverable from the packet alone. LIVE_FRAME is self-describing from its payload length; RESULT is not.

Consequence (`INFER` from source — **not observed on hardware**): a Pi that starts *after* the Teensy, or that loses that one frame to a full buffer at boot, decodes live frames fine and **cannot decode a single RESULT, indefinitely, until the Teensy reboots.** Runbook step 10 does not catch this — it resets the *Teensy*, which re-runs `init()` and resends HELLO. **Teensy-reboot recovery works. Pi-restart recovery is untested and unprovable against the current firmware.**

**Not fixed here, deliberately.** The fix is firmware-visible behaviour and sits behind the TODO-9 flash/identify sequence. It also has a trap worth stating before anyone writes it: a re-announce must stay on the non-blocking best-effort path — **this must not become the first blocking write in the super-loop**, which is the precise failure T1 exists to rule out. The Pi side contains the symptom instead: `decode_result()` raises `GeometryUnknown` rather than guessing a length, so it fails loudly instead of mis-slicing an array into a plausible-looking curve.

**Architecture decision — what the parser is forbidden to do.** ADR-001's invariant is *the Teensy determines truth; the renderer presents truth*. `result_valid`, `result_quality`, `mean_coherence`, `tf_confidence` and the per-bin coverage nibbles are read off the wire and carried through unchanged; none is recomputed or inferred. The one derived object is `BinCoverage`, and the distinction was drawn explicitly: the Teensy states *"3 of 4 source bins were clamped"*; the receiver decides that means a saturation marker. It never decides a clamped bin was really fine. A test enforces the checkable half by failing if any receiver module imports an FFT library — a receiver that imports numpy is one commit from recomputing a transfer function the Teensy already authored.

**Implementation.** `pi/analyzer_link/` — `crc.py` (CRC-16/CCITT-FALSE, mirroring `crc16_block`), `framing.py` (`FrameScanner`), `packets.py` (all seven v2 types plus `UnknownPacket`), `protocol.py` (constants, enums, `Geometry`). Standard library only — **pytest is not installed on this machine and no dependency was added**, so the suite is `unittest`. `sh pi/run_tests.sh`.

Two framing decisions are about not trusting a corrupted header, and both are recorded in the source rather than left as folklore:

- **Resync at `start + 1`, not past the declared payload.** A packet that failed CRC has a length field that failed CRC too; skipping by it means trusting the corruption to describe its own size. Proven by test: a STATUS packet with a deliberately inflated length no longer swallows the frames behind it.
- **Bounded length.** `0x55 0xAA` occurs inside float payload data routinely, so false syncs are *normal*. A declared length above `max_payload_bytes()` is rejected immediately. Without that, two noise bytes make the receiver wait on 64 KB that will never arrive.

**Honest limitation, found by a test that initially failed for the wrong reason.** A corrupted length field does cause a **head-of-line stall** — a length cannot be disproved without checking the CRC, and the CRC cannot be checked until that many bytes have arrived. The stall is bounded by `max_payload_bytes()` (~10 kB, ~217 ms at 460 800 baud) and self-heals as traffic continues. It is now covered by a test that documents it rather than by a comment claiming it does not happen. My first version of that test asserted recovery without supplying enough bytes for recovery to be *possible*; the failure was the test's, not the scanner's.

**Drift guard — the Pi-side half of the protocol audit's acceptance Test C.** `tests/test_firmware_header_sync.py` parses the real Teensy headers and fails if any mirrored constant, packet id or enum has moved. The firmware protects its own layout with `static_assert`; **nothing protected the Python mirror**, and a renumbered enum is the quietest possible break — the packet still parses, the CRC still passes, and the Pi displays the wrong verdict.

It caught a real mismatch on its first run: the firmware `#define` is `DS_PACKET_ROUTER` while the header's own packet table and function name say `ROUTER_STATUS`. Rather than paper over it with string munging, the mapping is now an explicit table, with a second test asserting the table covers every packet type in **both** directions.

**Proof that the guard can actually fail** — a test that cannot fail proves nothing, so three mutations were run as negative controls and each produced a failing run before being reverted:

| Mutation | Result |
|---|---|
| `MeasurementState.ABORTED` 6 → 5 | `FAIL test_every_mirrored_enum_matches` |
| `RESULT_FIXED_BYTES` 156 → 152 | 1 failure |
| coverage nibbles transposed (`clamped`/`valid` swapped) | 3 failures, incl. `test_nibbles_are_not_transposed` |

The third is the important one: transposing those nibbles turns every railed bin into a plottable one, which **is** the 2026-09-07 defect — `1kHz=-24.0dB` reported in 33 of 33 consecutive windows as though the saturation rail were data. Protocol v2 exists largely to prevent the Pi repeating it, so the contract now has a test per branch.

**🔺 EVIDENCE TIER — the bound on all of the above.** The vectors are **synthesised from this repository's reading of `data_sender.h`**. Encoder and decoder share one author and one interpretation, so a misreading of the header would be reproduced identically on both sides and all 70 tests would still pass. **Proven:** the parser is self-consistent with the header, and its CRC-rejection, resync, bounded-length and unknown-type behaviour are correct. **NOT proven:** agreement with the **compiled firmware on the wire.** That needs a captured real Teensy byte stream — runbook Phase 10 step 4 onward, hardware required. The bound is stated in `pi/README.md`, in `tests/vectors.py`, and in TODO-36, because it is exactly the kind of claim that inflates in retelling.

**No Phase 10 step is passed by this work.** Steps 8 (CRC rejection) and 9 (unknown-packet tolerance) now have offline coverage; the steps themselves are bench steps against a real stream.

**State of the bench — unchanged and untouched.** No firmware was compiled or flashed. The board still runs `44c4680` (`Build: Sep 21 2026 17:21:24 v0.6.0`, hex md5 `65405de70fc778fdd8cf6a48e1cbe45e`). No serial port was opened — `list_ports` enumerated the Teensy at `/dev/cu.usbmodem192895301` and nothing else was done. No relay was actuated, no generator enabled, no validation routine run. **Phase 9 remains blocked exactly where 2026-09-22 (6) left it.**

**Portfolio note.** The two defects are the material worth keeping, and they are the same lesson from two directions: *writing the consumer is what audits the producer*. The protocol had been audited once already — 17 findings, five severe — and the HELLO retransmission gap survived that audit because the audit asked *"is every verdict on the wire?"* and not *"can a receiver that arrives late ever decode this?"* Nobody had tried to be the receiver. Photograph-equivalent for this entry: the negative-control table above, and the `DS_PACKET_ROUTER` / `ROUTER_STATUS` mismatch the drift guard caught within seconds of first existing.

---

## 2026-09-22 (6) — **The "finish Group B, then flash once" plan is CIRCULAR and is abandoned.** New sequence: an **evidence-enabling intermediate build**, not acceptance firmware. The 100 nF film capacitor is a **validation-fixture** dependency, NOT a breadboard blocker. Critical path re-prioritised to the Pi/UI end-to-end demonstration

### Why the old sequence became impossible

The handoff sequence was: reconcile all Phase 9 text → **one** compile/flash/identify → TODO-48
runtime check → build and measure fixtures → Phase 9. That assumed the text could be finished before
flashing. **For Test 4 it cannot:**

```
Group B (Test 4 text/default/criterion)
    needs the frozen operating corner and tolerance
        needs Test 4 characterisation collections
            needs the fixture built AND a flashed, identified build
        the corner also needs the measured passband loss L
            needs a Test 1 collection to compare against
                needs a flashed, identified build
```

**Waiting for Group B before flashing prevents collecting the evidence Group B requires.** The
dependency is inverted for Test 4 and only for Test 4; Groups A, C and D were genuinely finishable
first, and they are (`119a737`, `8878bb4`, `cec814a`).

### 🔺 The first flash is NOT the Phase 9 acceptance firmware

**Recorded explicitly so the history cannot be misread later.** The build that goes on the board next
is an **EVIDENCE-ENABLING INTERMEDIATE STATE**: it contains A/C/D and **knowingly still contains
Group B's defects** — the `1989.0f` default, the 10 k/10 n prompt text, and criterion 1's one-sided
rule that cannot reject a corner that is too low.

- **⚠️ Test 4's PASS/FAIL banner is METHODOLOGICALLY INVALID in this state and counts for nothing.**
  Its criterion is known defective. **What IS usable is its reported raw quantities** — passband
  mean, TF at 2·fc, delta — because those are measurements, not verdicts. **Never record a Test 4
  PASS from this build as acceptance evidence.**
- **Characterisation data and acceptance data must stay separately labelled**, per the
  frozen-before-acceptance invariant (entry (2), decision 5).

### The revised sequence

1. **Acquire the 100 nF film capacitor; measure R and C independently** when the fixture stage is
   reached.
2. **Compile HEAD as one integrated state** before flashing. C and D were compile-verified
   individually; the accumulated state has not been built as a whole.
3. **Flash and IMMEDIATELY identify** — record commit, build stamp and hex MD5, and establish that
   the board is no longer running `44c4680`.
4. **TODO-48 runtime/preflight work BEFORE using the harness for characterisation.** Group C's
   `validation_promptExpectedOffset()` has **never been runtime-tested** — compiling is not
   evidence that it rejects `6dB`, accepts `0`, or handles overlength input. **Do not go from
   "it compiled" to trusting the harness.**
5. **Bring up Test 1** on the corrected external loopback. **This is evidence collection, not
   permission to declare Phase 9 passed.**
6. **Build and independently characterise the Test 4 fixture** — measured R and C, installed and
   powered, and whatever is needed to validate **or reject** the proposed passband-loss method.
7. **Run characterisation collections, NOT Test 4 acceptance:** establish the operational corner from
   fixture/chain evidence, and collect repeated delta values for run-to-run spread.
8. **Freeze and journal the Test 4 design** — operational corner, model-derived expected delta,
   tolerance, slope correction. **This is where ±1.00 dB survives or changes**, on pre-freeze
   evidence.
9. **Draft Group B from those frozen values.**
10. **Compile, commit, flash, verify.** **Only then** can step 2 / TODO-55 close and real Phase 9
    acceptance proceed.

**🔑 On Test 1 at step 5:** it does **not** have to PASS to serve as characterisation evidence. What
must be established is that its **collection is technically valid** and what it actually measures. **A
legitimate Test 1 failure may reveal a real hardware or system problem that must be fixed before
Test 4 characterisation. Test 1 is NOT to be tuned until it passes** — that is precisely the
acceptance-boundary defect removed in `cec814a`.

### `DECISION` — the 100 nF film capacitor is a VALIDATION-FIXTURE dependency, not a build blocker

**The capacitor belongs to an external reference fixture used to prove measurement accuracy. It is
not part of the permanent analyzer signal path.** Therefore:

- **Breadboard construction continues to completion with the permanent hardware.** **Do NOT fit a
  substitute capacitor** to satisfy Test 4 — a wrong dielectric is exactly the defect the fixture
  design exists to avoid.
- **Test 4 / Group B → DEFERRED, pending an external characterisation-fixture component.**
- **Phase 9 overall remains incomplete**, and **breadboard SIGN-OFF (TODO-10) still requires it.**
  **Construction complete ≠ signed off ≠ validated.** Those three are now tracked separately and must
  not be collapsed.

### `DECISION` — critical path re-prioritised for the 2026-11-01 Maker Portfolio deadline

**The temporary calibration fixture must not sit on the critical path to the instrument.** New order:

**finish the permanent breadboard → stable firmware/runtime → Teensy↔Pi protocol → Pi production UI
→ real end-to-end measurement demonstration → enclosure/presentation**, with **Test 4 characterisation
running as a PARALLEL validation track.**

- **The Pi UI is to be driven by REAL Teensy measurements — not canned data.** Nothing in the Pi path
  depends on the Test 4 fixture.
- **The distinction to preserve everywhere, including the portfolio: a working prototype is not a
  fully characterised measurement instrument.** The honest version is the stronger story — a
  weakness was found in the original validation methodology, a convenient PASS was refused, the
  reference fixture was redesigned, and final quantitative characterisation is gated on the correct
  component and the right evidence.

### Not done here

**Records only.** No firmware, no runbook, no compile, no flash, no serial traffic, no bench action.
**Group B not drafted.** The board still runs `44c4680`. *(Runbook note, not edited: the Phase 9
parts tray still lists the 1 nF C0G as "optional — RC filter calibration", which Group B supersedes.)*

---

## 2026-09-22 (5) — Step-2 records reconciliation. **Three implementation defects closed; every validation gate still open.** Documentation and compile evidence is NOT hardware evidence

### What this entry closes, and what it deliberately does not

**Records only** — `ai/todo.md` and this file. No firmware, no runbook, no source. Phase 9 step 2 is
**partly** done: Groups A, C and D are committed; **Group B (Test 4) is untouched and still blocks
Phase 9.**

| Group | Commit | What it fixed |
|---|---|---|
| **A** | `119a737` | The external-generator/`SOURCE_NODE` contention hazard. Text only, token-identical |
| **C** | `8878bb4` | Test 3's nominal −6.02 dB and the `-6.0` default hidden in the serial parser |
| **D** | `cec814a` | Acceptance-run-driven tolerance-tightening advice |

**⚠️ The line this pass exists to hold: none of that is validation evidence.** Three commits of
corrected text and compiled behaviour, **none flashed, none run.** **Tests 1 and 2 have never been
run on hardware through the validation harness; no retained output constitutes a valid Test 1 or
Test 2 acceptance run.** Logs from 2026-09-05/07/13/19 exist and remain useful for what they
actually recorded — they are simply not acceptance runs. **Preparatory work must not be converted
into evidence by the act of recording it.**

### `DECISION` — status after reconciliation

- **TODO-55 → 🛑 Phase 9 instructions STILL BLOCKED**, not downgraded to 🟡. The header now separates
  **RESOLVED** (the contention hazard, `119a737`) from **STILL BLOCKED** (Test 4's text, its
  `1989.0f` default, its defective criterion 1, and the TODO-48 reconciliation that follows).
  **Status communicates operational readiness, not the severity of the original defect** — an
  operator following the Test 4 text today would still build the abandoned fixture.
- **TODO-9 → 🔴 blocked, unchanged.** Its Proof still requires `1`, `2`, `3`, `4` to actually PASS.
  Stale gate language is corrected: the fixture instructions are no longer "electrically unsafe",
  the parts row records Test 3 decided and Test 4's topology frozen, and **`b275852` is no longer the
  flash target** — the accumulated set runs through `cec814a`, plus Group B.
- **TODO-16 → 🔴 open. Goal preserved, mechanism reversed.** It may no longer say "after Phase 9
  passes, tighten based on observed headroom". A revision is now a **separate, justified design
  decision, journalled and frozen before the next acceptance run**, with evidence from
  characterisation runs. **`cec814a` did not close it:** Group D removed the bad mechanism; it did
  not do the characterisation.
- **TODO-48** — scope/state note only; the Proof reconciliation is **not** done. Records that newer
  unflashed commits sit above `399e54b`, and that step 3 now also owns **harness-level post-consent
  cancellation**.
- **TODO-52** — its Y-split reference is **preserved and marked HISTORICAL**, with a note that the
  cleared finding still applies to the loop, which uses the same tip.

### 🔑 The inventory-discovery pattern — worth carrying forward

**Every one of the three groups was undercounted when inventoried by reading, and corrected by an
exhaustive mechanical search before editing:**

| Group | Inventoried by reading | Found by exhaustive search | What the extra locations were |
|---|---|---|---|
| **A** | 8 | **15** | implementation comments, the `validation.h` preflight-gate contract, a README step, the runbook's Test 2 row |
| **C** | 4 | **7** | the `20·log10(R2/(R1+R2))` definition comment, a 0.1 dB print precision, a second runbook site |
| **D** | 2 | **8 + 1** | the `validation.h` "NOTE ON TIGHTENING" recipe, three comment sites, README, and a dangling `measurement_core.h` reference |

**The counts are recorded as discovery history, not retconned.** The pattern is the finding:
**reading found the conceptual defects; only mechanical search revealed how far each assumption had
propagated.** In every case the extra locations were *developer-facing* — comments, contracts,
README — which is exactly where a stale assumption survives a prompt-only fix and re-infects the
next change. **Group D's extra locations included a concrete retuning recipe (≈2× the measured
values) that the two known sites would have left in place.**

### Not done here

**Group B not drafted. TODO-48's Proof not reconciled. Nothing compiled, flashed or run.** The board
still runs `44c4680`. No bench action, no serial traffic.

---

## 2026-09-22 (4) — **audit-9's "tighten the tolerances" advisory REMOVED.** It let an acceptance run recommend moving the boundary it had just been judged against. Group D drafted

### Why this entry exists — and why the reversal is worth keeping visible

`audit-9` tried to make the harness **self-improving**: when a criterion passed with large headroom,
it told the operator to tighten that constant to *"reflect demonstrated hardware capability"*. **The
intent was sound** — a suite that passes with huge margins gives weak assurance, and that remains
true. **The mechanism was not.** This entry records the reversal rather than quietly deleting the
advisory, because *why* the earlier approach is methodologically weaker is the useful engineering
content. **The correct policy did not exist from day one; it was earned by the Test 3 and Test 4
work above.**

### `OBS` — exhaustive inventory: 8 live locations, plus a dangling reference

| # | Location | What |
|---|---|---|
| D1 | `validation.cpp:375–400` | `any_headroom` detection loop in `printResult` |
| D2 | `validation.cpp:406–412` | the per-result ADVISORY print |
| D3 | `validation.cpp:1501–1507` | the suite-level "NEXT STEP … tighten" block |
| D4 | `validation.cpp:360–361` | `printResult` banner comment |
| D5 | `validation.h:63–68` | audit-9 changelog entry |
| D6 | `validation.h:160–166` | **"NOTE ON TIGHTENING" — a concrete rule: tighten to ≈2× the measured values** |
| D7 | `validation.h:287–290` | `printResult` declaration comment |
| D8 | `README.md:259` | advertises the advisory as a feature |
| + | `measurement_core.h:235` | *"Adjust after real hardware characterisation (see validation advisory)"* — **a dangling pointer once D1–D8 go** |

**The earlier working assumption of "two occurrences" was wrong. D6 is the most consequential and was
not on that list:** it sits directly above `LOOPBACK_MEAN_TOLERANCE_DB`, `LOOPBACK_PP_TOLERANCE_DB`
and `LOOPBACK_CONFIDENCE_MIN` and prescribes an actual retuning recipe, so the policy reached Tests
1 and 2, not only 3 and 4.

### `OBS` — what the advisory actually did

- **Trigger, per criterion:** `c.passed && c.tolerance > 0.0f && !isnan(c.measured) &&
  fabsf(c.measured) < 0.5f * c.tolerance`; the advisory then printed if
  `r.all_passed && any_headroom`.
- **It derives its recommendation from the SAME `ValidationResult`** whose pass/fail had just been
  computed against those constants.
- **It can fire after a single passing run**, and **repeatedly within one suite** — `printResult()`
  runs per test, so a clean `v` printed it up to five times, plus the suite-level block.
- **It never changed any constant automatically.** Purely emitted text.
- `tolerance > 0.0f` currently exempts the negative `FILTER_2FC_MAX_DELTA_DB` — **note that the
  planned two-sided Test 4 criterion would have a positive tolerance and would therefore have become
  eligible.**

### `DECISION` — Remedy A: remove, do not reword

Measured against the frozen-before-acceptance rule (entry (2), decision 5), three things must be kept
apart:

| | Verdict |
|---|---|
| Pre-acceptance characterisation establishing a criterion | **Legitimate** — this is the ±1.00 dB work |
| Observing headroom as a reported result | **Legitimate** — it is the evidence |
| **Using acceptance-run headroom to recommend changing the criterion** | **This is what D2/D3/D6 did** |

**Remedy A (remove) was chosen over Remedy B (scope/reword)** because the resulting invariant —
*report against frozen criteria; never recommend changing them from the acceptance run* — is
**mechanically checkable**, while qualified advisory language would leave every future reader judging
whether their case counts, and would leave D6's ≈2× recipe needing a caveat contradicting its own
specificity. **Nothing is lost:** the measured-vs-tolerance table survives untouched, and "should
these constants be tighter?" becomes a journalled pre-run decision.

### `OBS` — blast radius: measurement and pass/fail preserved, serial output intentionally changed

`any_headroom` was a **local `bool`** guarding a print. `ValidationCriterion` and `ValidationResult`
carry no headroom field; nothing was stored, returned, transmitted or displayed. `printResult()`
returns `void`; `runAll()` returns `passed == total`, unaffected.

**⚠️ Stated precisely, and NOT as token identity:** removing executable `Serial.print` branches
**necessarily changes the token stream and the compiled firmware**. **The claim is narrower and
exact: measurement and pass/fail behaviour are unchanged; serial output is intentionally changed.**
Unlike Group A, this cannot be verified by token comparison — the later single compile/flash cycle
remains necessary, and Group D must be inside it.

### Deferred — TODO-16 carries the same older policy

`ai/todo.md` TODO-16 still says to tighten the tolerance/threshold constants "after Phase 9 passes
repeatedly, based on observed headroom". **Deliberately NOT edited here.** It is a project-policy
record, and it is reconciled with TODO-55/TODO-9 when step 2 closes. **It must not simply be
deleted then:** its intent — provisional tolerances tightened once hardware evidence exists — was
reasonable, and only its *mechanism* conflicts with the frozen-before-acceptance rule. **That
evolution is evidence and is to be preserved.**

### Not done here

Not compiled, not staged, not committed. **No tolerance constant, threshold, criterion, measurement
calculation, result structure, status propagation or pass/fail expression changed.** TODO files
untouched. The board still runs `44c4680`. No bench action, no serial traffic.

---

## 2026-09-22 (3) — **Test 3's estimator consumes MORE than the 2026-09-21 decision specified**, and its `-6.0` default is hidden in the serial parser, not just in the prompt. Group A committed; Group C drafted

### Why this entry exists

Group C set out to delete a stale nominal from a prompt. Reading the estimator first turned up two
things that change what the prompt must say and what the fix must touch. **Neither rewrites the
2026-09-21 decision; both are findings that came after it.**

### 🔺 Finding 1 — the decision and the estimator describe different quantities

**`OBS`, code at `119a737`.** `validation_runKnownGainOffset()` (`validation.cpp:1023`) compares
`expected_offset_db` against `band_mean`: the mean over 200 Hz–10 kHz of
`20·log10(mean_return[k] / mean_source[k])`, where the two accumulations come from **two different
ADC channels** — SOURCE on LINE-IN-L (ch0), RETURN on LINE-IN-R (ch1). Pass is
`|band_mean − expected| < GAIN_OFFSET_TOLERANCE_DB` = **1.0 dB**.

**So the entered value must be the complete installed SOURCE→RETURN transfer offset**, which
contains at least three terms:

1. the pad's **loaded** ratio, `(R2 ∥ Z_in) / (R1 + R2 ∥ Z_in)`;
2. **any channel-to-channel gain mismatch** between the codec's two PGAs and the two input paths;
3. losses in the send/return wiring, connectors and relay contacts between the two tap points.

**The 2026-09-21 (6) decision specified** *"an independent in-circuit measurement (scope or DMM on
the two jack tips, analyzer powered so the codec loads the pad)"*. **That characterises term 1.** It
was right to insist on powered/in-circuit — that is what captures the loading — but **a jack-tip
measurement does not by itself establish terms 2 and 3**, and the decision did not address them.
**The decision is not withdrawn; this records what inspection of the implementation added to it.**

**`ASSUMPTION`, considered and NOT adopted:** that the expectation could be composed as
*scope-measured loaded pad ratio + Test 1's measured loop offset*. **This assumes the channel/path
term measured through Test 1's direct loop transfers unchanged to Test 3's different source-impedance
and loading condition. That has not been demonstrated**, and it is the same class of unsupported
codec-input assumption withdrawn in entry (2). It is recorded as a **candidate decomposition only**
and appears nowhere in the firmware.

**Consequence for the prompt:** the harness asks for the **quantity**, not a procedure. It must not
name a DMM, a scope, a Test-1 correction or any combination until one is validated.

### 🔺 Finding 2 — the `-6.0` default is in the parser, not the prompt

**`OBS`, code.** `readSerialFloatWithAudioPump(float default_value)` ends
`return (len > 0) ? atof(buf) : default_value;` and **exists twice as identical static copies** —
`validation.cpp:84` and `guitar_rig_analyzer.ino:166`. Behaviour:

| Input | Result |
|---|---|
| **bare Enter** | returns `default_value` — **silently −6.0**, the forbidden nominal |
| **malformed** (`abc`, `1.2.3`) | `atof` → **0.0**, no error, no echo |
| **partially numeric** (`6dB`) | parses the leading number, ignores the tail → `6.0` |
| explicit `0` | `0.0` — **indistinguishable from a parse failure** |
| proper negative | parsed correctly |
| over 23 chars | silently truncated, then parsed |
| timeout | **none exists** — the wait loop spins while pumping audio |

**Deleting the printed "(default -6.0)" would have left the fallback fully intact**, and fixing only
`validation.cpp` would have left the standalone `3` path calling the `.ino`'s own copy with
`-6.0f`. **Recorded because it is exactly the kind of defect a text-only pass hides.**

### `DECISION` — Group C scope, and an admitted boundary change

1. **One authority:** `validation_promptExpectedOffset()` in the harness owns Test 3's numeric entry;
   both the `v` suite and the standalone `3` path call it. **No default exists.** Bare Enter,
   malformed, partially numeric and overlength input all **re-prompt**; explicit `0` parses as a real
   value and is **not** used as the failure sentinel.
2. **No new abort convention.** Consent/preflight stays the way to decline, *before* numeric entry.
   No timeout, no `q`, no Escape added here.
3. **`readSerialFloatWithAudioPump()` is untouched** — Test 4 still uses it, and its default is a
   Group B decision.
4. **⚠️ GROUP C IS NO LONGER TEXT-ONLY.** It changes serial-input behaviour, deliberately, to remove
   the hidden default. Group A was provably token-identical; **this is not**, and the commit must say
   so. Whether it compiles now or waits for the single planned compile/flash/identify cycle is a
   separate decision.
5. **Prompt wording:** the pad's position becomes **Rig Send → pad → Rig Return TS**, consistent with
   Group A; the required input is the **expected installed SOURCE→RETURN offset for this powered
   configuration, in the same route and PGA state as the test.**

### 🔺 Finding 3 — the harness has NO post-consent operator cancellation, anywhere

**`OBS`, code at `119a737`, from a read-only inventory of the harness's cancellation semantics:**

- **`validation_waitForUser()` (`validation.cpp:471`) is the harness's ONLY operator-facing
  cancellation mechanism, and it exists ONLY as a pre-test consent gate.** It prints
  *"Press Enter (or 'y') to continue — any other key cancels"*, reads **one byte**, and returns a
  `bool`: consent is `\r`, `\n`, `y`, `Y`; **any other byte declines.** All **nine** call sites —
  five in `runAll()`, four in the `.ino` — are gates *before* a test starts.
- **There is no established post-consent cancellation gesture anywhere in the validation harness.**
  Not for parameter entry, not during collection. No `q`, no Escape, no timeout, no `validation_abort()`
  — **no function of that or any similar name exists** in `validation.h`/`validation.cpp`.
- **Collections are non-interruptible by the operator once started.** `collectFrames()` contains
  **zero** `Serial.read`/`Serial.available` calls (counted, not estimated), and validation invocations
  deliberately block the main loop (`guitar_rig_analyzer.ino:459`). Every "ABORT" string in the
  harness is a **machine-detected** condition — collection timeout, `ROUTE_CHANGED` mid-collection
  (5 sites), "no audio blocks in 2 s" — never an operator gesture.
- **⚠️ The new Test 3 numeric-entry loop differs MATERIALLY from that existing behaviour, and is not
  to be dismissed as equivalent.** Existing non-interruptible windows are **bounded** — a collection
  runs ~3 s and ends. `validation_promptExpectedOffset()` **waits indefinitely** for a valid line. An
  operator who consents and then finds they have no characterised value must send a syntactically
  valid number or reset the session.
- **Both Test 3 paths disclose the requirement BEFORE the consent gate**, so the operator has the
  established opportunity to decline: the suite prompt states *"There is NO default and no nominal
  fallback — an explicit value is required, so decline HERE if you do not have one"*, and the
  standalone `3` prompt says the same. **Sequence, suite:** prompt → consent verdict → (decline ⇒
  `suiteDeclined()`) → numeric entry. **Standalone `3`:** prompt → consent verdict → (decline ⇒
  `break`) → `validation_preflightGate(true)`, several seconds of collection → numeric entry. **In the
  standalone path the decision point is separated from the loop by the preflight**, which itself
  offers no operator exit.

### `DECISION` — post-consent cancellation DEFERRED to step 3, deliberately

**Considered and NOT adopted for Group C:**

1. **`bool validation_promptExpectedOffset(float* out_offset)`**, writing `*out` only on `true`, with
   callers branching exactly as they already do for `validation_waitForUser()`. This is the correct
   *representation* — it makes a cancellation structurally incapable of becoming a numeric
   expectation, and a bare-`float` return cannot express cancellation without a sentinel the
   estimator could consume. **It is recorded here as the preferred shape for whenever cancellation is
   designed.**
2. **Re-gating through `validation_waitForUser()` on invalid input.** It invents no new key, but it
   **gives that function a second semantic role** — error recovery and cancellation *inside parameter
   acquisition* — where today it is purely the pre-test consent gate.

**Why deferred, not solved here:** either option would establish a **Test-3-specific post-consent
cancellation behaviour** immediately before the harness-wide consent semantics are reconciled in
**step 3 with TODO-48**, whose Proof line is already known to disagree with the implemented
immediate-decline. **A local parser convenience must not set a harness-wide UX rule by accident.**

**Deferred work, owned by step 3:** design post-consent operator cancellation **once, at harness
level** — covering parameter entry and, if it is to exist at all, collection — rather than per test.
**This finding is the reason Test 3's numeric loop ships non-abortable; it is a known, recorded gap,
not an oversight.**

### `OBS` — corrected Group C inventory: 7 locations, was 4

`validation.cpp:1337` (fixture position) · `validation.cpp:1338–1341` (the −6.02 example **and** the
prescribed DMM) · `validation.cpp:1347–1349` (the `-6.0f` default and its printed description) ·
`guitar_rig_analyzer.ino:506–512` (duplicate prompt and default) · **newly found:**
`validation.cpp:1019–1021` (implementation comment defining attenuation as the **unloaded**
`20·log10(R2/(R1+R2))`) · `validation.cpp:1027` (prints the expectation at **0.1 dB** while
`band_mean` prints at 0.01 dB) · `docs/breadboard_bringup_v3.md:1946, 1955` (runbook naming the
nominal "6 dB" as the expectation).

### Not done here

**TODO-55/TODO-9 not updated. Groups B and D untouched. TODO-48's Proof line remains step 3.** Not
compiled, not flashed. The board still runs `44c4680`, and Group A's prompts are already not on it.
No bench action, no serial traffic.

---

## 2026-09-22 (2) — **The 40 kΩ codec-input figure has NO source in this repository, and the 20 kΩ–∞ loading range is WITHDRAWN.** Test 4 fixture **topology frozen** at 1 kΩ + 100 nF film — **its operating corner is NOT frozen and is not 1591.5 Hz by default**

### Why this entry exists

Entry (1) justified the fixture partly on its loading sensitivity "across Z_in 20 kΩ→∞". **That range
was never evidence-backed.** This entry withdraws it, records what the repository actually contains
about the codec input, and replaces the assumption with a method that does not need it. It also
records the Tests 1–2 evidence review and corrects a √N claim made during it.

### `OBS` — what the repository contains about the RETURN input load

- **The ~40 kΩ figure appears only in code comments, uncited**, in four places: `validation.h:58`,
  `validation.h:185–190`, `validation.cpp:1087` and the operator prompt at `validation.cpp:1361`.
  The arithmetic is shown (`10k || 40k = 8k → 1989 Hz`); **the 40 kΩ itself is asserted, never
  sourced.**
- **No PJRC Audio Shield Rev D schematic is in the repository.** The only schematics are this
  project's own as-built SVGs, generated by `tools/gen_schematic.py` from `docs/asbuilt/netlist.md`.
- **The as-built netlist treats the shield as a black box** — `U3 | PJRC Audio Shield Rev D
  (SGTL5000) | free-standing, not stacked | off-board | PHOTO` (`netlist.md:89`). It documents the
  seven-wire Teensy↔shield interconnect and the breadboard side and **stops at the shield's pads**.
  No component value exists anywhere between the LINE IN R pad and the codec.
- **No SGTL5000 datasheet or datasheet extract is held.**
- **The register dumps establish the input path, not its impedance:** `SELECT_ADC 1 (LINEIN)`,
  `ADC_VOL_LEFT/RIGHT 5`, `ADC_VOL_M6DB 0`, `ADC_POWERUP 1`
  (`ai/evidence/2026-09-13-sgtl-register-dump-v2.log`). **RETURN is a LINE IN path with the analog
  PGA at 5 of 15.**

**Precisely what is missing:** the SGTL5000 datasheet's LINE IN input-impedance specification, and
the Rev D schematic showing whether any series or shunt component sits between pad and codec pin.
The register evidence makes the first more than a lookup — **the PGA setting is part of the input's
analog configuration, so any figure adopted later must state which line-in level it applies to.**
No external/internet source was consulted; none is authorised.

### 🔻 `WITHDRAWN ASSUMPTION`

**The 20 kΩ–∞ range used in entry (1), and the ~40 kΩ in the code comments, are withdrawn as
justification.** Neither has a source. **No numeric Z_in is adopted in its place.** Statements in
entry (1) that depend on that range — notably "5.0 % across Z_in 20 kΩ→∞" — are to be read as
*conditional on a bound that is no longer claimed*, not as findings. The fixture *selection*
survives on the sensitivity argument below, which assigns no value to Z_in.

### `DERIVED` — loading sensitivity of 1 kΩ + 100 nF, assigning NO Z_in

`fc = 1 / (2π·(R∥Z_in)·C)`, R = 1 kΩ, C = 100 nF. **The table is a sensitivity sweep, not a claim
about where Z_in lies:**

| Z_in | R∥Z_in | corner | shift vs unloaded | fixture passband loss |
|---|---|---|---|---|
| 2 kΩ | 666.7 Ω | 2387 Hz | +50.0 % | −3.52 dB |
| 5 kΩ | 833.3 Ω | 1910 Hz | +20.0 % | −1.58 dB |
| 10 kΩ | 909.1 Ω | 1751 Hz | +10.0 % | −0.83 dB |
| 20 kΩ | 952.4 Ω | 1671 Hz | +5.0 % | −0.42 dB |
| ∞ | 1000 Ω | 1592 Hz | 0 % | 0 dB |

**What this establishes without any Z_in bound:** the corner stays inside the measurement band across
the entire sweep, including a 5 kΩ load no one expects. **The unknown does not threaten the fixture
choice — it threatens the number the operator ENTERS.** Entering 1591.5 Hz against a truly 1910 Hz
loaded corner is a 20 % error, which by entry (1)'s model consumes almost the whole proposed
±1.00 dB window before any measurement noise.

### `PROPOSED METHOD` / `DERIVED` — characterise the loaded corner instead of assuming Z_in

The corner depends on `R∥Z_in`, and the fixture's passband loss `L` (dB) yields it directly:

```
R∥Z_in = R · 10^(L/20)        ⇒        fc = 1 / (2π · C · R · 10^(L/20))
```

**Z_in cancels and is never estimated.** `L` is the difference in passband mean between a **Test 1**
collection (no fixture) and a **Test 4** collection (fixture fitted) on the same chain — **two
numbers both tests already print.**

Error propagation is favourable: **±0.1 dB on L → ±1.2 % of corner; ±0.2 dB → ±2.3 %.**

**⚠️ PROPOSED, NOT HARDWARE-VALIDATED.** Nothing here has been demonstrated on the bench. Its
validity depends on conditions not yet shown:

- **Same route, same level, same PGA setting** across the Test 1 and Test 4 collections, or the
  difference is not a fixture loss.
- **The RC's own attenuation is already present at the low passband edge** — −0.068 dB at 200 Hz,
  −0.152 at 300, −0.266 at 400 — so `L` must be taken from the lowest bins **with that known rolloff
  removed**.
- **`ASSUMPTION`: the codec input is resistive across the passband.** Without the Rev D schematic a
  series coupling capacitor or other reactive element cannot be excluded; such an element would make
  `L` frequency-dependent at the low edge. **If `L` proves flat across 200–400 Hz after the RC
  correction, that is itself evidence for the resistive assumption** — which is a result to be
  obtained, not one held.

### Tests 1–2 evidence review — `OBS`, and one correction

**Tests 1 and 2 have never been run on hardware** (TODO-9 🔴), and **no validation-suite output is
retained anywhere in the repository.** The only `[Validation]` strings in the logs are boot banners
from **v0.5.0** firmware. Every candidate substitute fails for a stated reason: the 41B capture's TF
is `1kHz=RAIL[-24.0dB]` with the other spot bins `---` at 1 % confidence and RETURN at −66 dBFS;
`2026-09-07-tf-clamp-preserved.md` is the documented pre-fix clamp defect; the 2026-09-05 spot-checks
were taken **with the analog input physically disconnected** and both nodes pegged at +0.0 dBFS; and
the 2026-09-19 loop TF is a **single** window at 15 % confidence from a decaying strum.
**Conclusion: the existing evidence cannot justify freezing ±1.00 dB — not because it is marginal,
but because no retained dataset measures the quantity at all.** ±1.00 dB remains **provisional**.

**🔺 CORRECTION, recorded deliberately.** During that review it was stated that 32-block averaging
suppresses noise "by roughly √32". **That √N relationship holds only under suitable
independence/uncorrelated-noise assumptions, and nothing retained establishes that assumption for
this measurement chain.** The conclusion is unaffected — the evidence is insufficient either way —
but the claim must not be carried forward as a property of this hardware. **It is also why the
instrumentation below relies on repeated whole collections, which measure the estimator directly,
rather than on per-block scatter, which would need exactly that assumption.**

**Structural finding — `OBS`, code:** `CollectionStats` (`validation.cpp:60`) retains only
`accum_source[]`, `accum_return[]`, `valid_count[]` and the derived `mean_tf[]`. **No per-block
variance is computed or retained, and nothing exports per-bin TF.** Test 1 reports band
min/max/mean/pp of the *averaged* curve — within-trace bin variation, **not** run-to-run
repeatability. Test 2's A/B `max_diff` is a **single** paired difference, confounded with the channel
asymmetry it exists to measure.

### `DECISION` — minimal evidence instrumentation (adopted; not implemented)

1. **No new measurement mechanism is needed.** `validation.cpp:1157–1162` **already prints**
   `Passband mean`, `TF at 2fc` and `delta` at 0.01 dB, and `4` is a standalone entry point
   (`guitar_rig_analyzer.ino:514–522`). **Repeated Test 4 collections yield the run-to-run
   distribution of the exact estimator criterion 1 consumes, with no code change and no independence
   assumption.**
2. **Adopted for the Phase 9 firmware reconciliation — three permanent additions, reporting only:**
   **`pb_count`** (already computed at `validation.cpp:1113–1120`, never printed); **the 2·fc bin
   index and its actual centre frequency** (`hzToBin` rounds, so the bin can sit up to 21.5 Hz off);
   and **`valid_count[]` at the 2·fc bin** (per-bin gating at `TF_SOURCE_GATE` means the one bin the
   criterion hangs on may rest on fewer blocks — or zero, giving NAN). Sited after the existing
   print, **touching no accumulator and no pass/fail path.** Permanent rather than temporary, so
   every future PASS is auditable — and to avoid TODO-30's leave-behind-diagnostics trap.
3. **Stage 3 (per-block probe) is NOT authorised.** It diagnoses *why* scatter exists; it does not
   set the tolerance.
4. **Three variance components stay separate:** **run-to-run** (measurable by repetition, no
   assumption); **within-collection** (needs new accumulation, and relating it to the estimator needs
   the independence assumption above); **systematic bias** (**not measurable by repetition at all** —
   it is common to every run, and must come from measured R and C and the characterised `L`).
5. **The criterion must not use its own characterisation to pass itself.** The window's **centre**
   comes from the model plus measured R/C/L; characterisation sets only its **width**; the tolerance
   is frozen and journalled **before** the acceptance run; the new reported values never feed
   pass/fail.

### `DECISION` — fixture frozen; operating corner NOT frozen

**FROZEN — Test 4 fixture topology and components:** **1 kΩ 1 % metal film + 100 nF film, ±5 % or
better**, first-order RC low-pass in the RETURN path, per the entry (1) topology.

**NOT FROZEN — the operating corner.** **1591.5 Hz is the nominal UNLOADED design reference only. It
is NOT the expected loaded corner and is NOT automatically the value entered into Test 4.** The
entered value must come from the **characterised fixture and chain** — measured R, measured C with
the MM420's accuracy recorded, and the measured `L` — never from the nominal, and never from an
assumed codec impedance. **Step 6 is where the components are independently measured and the
proposed loaded-corner method is physically established.**

### Inputs to Phase 9 step 2 — recorded, NOT fixed here

Four code-text locations still teach the abandoned 10 kΩ / 10 nF fixture and the uncited 40 kΩ:

| # | Location | What it says |
|---|---|---|
| 1 | `guitar_rig_analyzer.ino:519` | `readSerialFloatWithAudioPump(1989.0f)` — the loaded corner of the abandoned fixture |
| 2 | `validation.cpp:1361` | operator prompt teaching `R=10kΩ, C=10nF → 1592 Hz` and the 40 kΩ correction |
| 3 | `validation.h:56–61`, `183–190` | where the uncited 40 kΩ entered the codebase |
| 4 | `validation.cpp:1086–1089` | same assumption in the function header |

**All four cite a figure with no source**, so step 2 must replace them with the measured-`L` method
rather than substituting a better guess. **Not fixed in this entry.**

### Not done here

**No code changed. TODO-55 not updated.** Nothing purchased or built, no bench action, no serial
traffic, no external sources consulted. The board still runs `44c4680`.

---

## 2026-09-22 (1) — Test 4's attenuation criterion is **one-sided: it cannot reject a corner that is too LOW.** Model-derived replacement proposed. Fixture candidate 1 kΩ + 100 nF film — **candidate, NOT a specification. No code changed**

### Observed — `OBS (code)`, read from the tree at `e88f6a4`

- Test 4 applies four criteria ([`validation.cpp:1097–1237`](../validation.cpp#L1097-L1237)): **delta at 2·fc**
  versus the 200 Hz–fc passband mean must be `< -4.0 dB`; **slope** over [fc, 10 kHz] must be within
  `2.0 dB/oct` of an expected value; **confidence**; and **≤ 5 monotonicity bumps** over 0.5 dB
  (`validation.h:191–194`).
- **The expected slope is hardcoded `-6.0f`** at both call sites — `guitar_rig_analyzer.ino:520` and
  `validation.cpp:1377`. **The operator enters only the corner.**
- Bin spacing is **43.0664 Hz** (44100 / 1024); `audioEngine_hzToBin()` rounds to the nearest bin.
- **Criterion 1 is an inequality, not a window.** Criterion 2 compares the fit against an asymptote
  that its own window never reaches, because the window starts *at* the corner.

### Modelled — `MODEL`, ideal first-order response evaluated through the code's own bin selection

Model: `TF(f) = -10·log10(1 + (f/fc_true)²)` sampled at `k·43.0664 Hz`, with the passband mean taken
over exactly the bins `200 Hz ≤ f < fc_entered` and the 2·fc value read from `hzToBin(2·fc_entered)`
— the same selection the implementation uses. Entered corner 1591.5 Hz.

| fc_true / fc_entered | true fc | passband mean | TF at 2·fc | **delta** | slope | slope err vs −6 |
|---|---|---|---|---|---|---|
| **0.10** | 159.2 Hz | — | — | **−11.953** | −6.010 | **0.010** |
| 0.25 | 397.9 Hz | −7.285 | −18.140 | **−10.855** | −5.954 | 0.046 |
| 0.50 | 795.8 Hz | −3.483 | −12.315 | **−8.831** | −5.770 | 0.230 |
| 0.75 | 1193.6 Hz | −2.001 | −9.100 | **−7.099** | −5.502 | 0.498 |
| **1.00** | 1591.5 Hz | −1.278 | −6.998 | **−5.718** | −5.184 | 0.816 |
| 1.25 | 1989.4 Hz | −0.878 | −5.522 | **−4.644** | −4.847 | 1.153 |
| 1.50 | 2387.2 Hz | −0.637 | −4.444 | **−3.807** | −4.509 | 1.491 |
| 2.00 | 3183.0 Hz | −0.375 | −3.016 | **−2.640** | −3.872 | 2.128 |

- **For a correct fixture the expected delta is −5.72 dB, not −6.99 dB.** The theoretical −6.99 is
  referenced to DC; the code's reference is a passband mean that is itself **−1.278 dB** down.
- **The expected delta is not a constant** — **−5.507 dB** at fc 796 Hz, **−5.718** at 1592,
  **−5.754** at 2341 — because the fixed 200 Hz passband floor sits differently against each corner.
- **A corner that is too LOW is never rejected.** At **0.5×** every criterion passes (delta −8.83,
  comfortably `< -4`; slope error 0.230). **The extended sweep continues to accept every ratio down
  to 0.10×**, the lowest modelled: delta **−11.953** (passes `< -4`), slope **−6.010** — an error of
  **0.010 dB/oct**, i.e. a wildly wrong corner scores a *better* slope than the correct one — and
  **0** monotonicity bumps. The 0.10×, 0.15× and 0.25× rows were computed in the same extended sweep
  as the table above; the 0.10× row is included here so the claim rests on displayed evidence.
- A corner that is too **high** is rejected only at about **1.4×** and above.
- **Sensitivity near the correct corner: 0.049 dB per 1 % of corner error**, near symmetric.
- **The slope criterion discriminates weakly.** Re-centred on its own model value (−5.184), the error
  is **0.337** dB/oct at a 25 % corner error and **1.313** at 2× — far weaker than criterion 1.
- **Bin quantization is not a factor:** 2·fc lands at 3186.91 Hz against 3183.0 requested, ≈ 0.004 dB.
- **Fixture candidate behaviour.** 1 kΩ + 100 nF moves the corner **5.0 %** across Z_in 20 kΩ→∞
  (1591.5 → 1671 Hz), against **50 %** for the old 10 kΩ + 10 nF (1592 → 2387 Hz). Passband insertion
  loss −0.42 dB at Z_in 20 kΩ. Peak monotonicity step **0.117 dB**, well inside the 0.5 dB limit.
  32 passband bins, 196 fit bins.

**Two-sided window candidates**, centred on the model value:

| Window | Accepts fc_true / fc_entered | Rejects |
|---|---|---|
| ±0.50 dB | 0.902 – 1.108 | > 10 % low, > 11 % high |
| **±1.00 dB** | **0.813 – 1.230** | **> 19 % low, > 23 % high** |
| ±1.50 dB | 0.731 – 1.369 | > 27 % low, > 37 % high |

### Decisions — `DECISION`

1. **Fix criterion 1.** A PASS must support the claim that *the analyzer identified the known
   response*. A criterion that accepts a 0.5× — or 0.1× — corner cannot support it. Independent
   capacitance measurement characterises the **fixture**; it is not a substitute for a validation
   rule that can reject a wrong **measurement**.
2. **The expected delta is computed, never a constant** — derived from the entered corner over the
   same bins and the same passband averaging the measurement itself uses. A hardcoded number would be
   wrong at every corner but one (−5.507 vs −5.754 across the candidate range).
3. **Two-sided tolerance, provisionally ±1.00 dB — ⚠️ NOT FROZEN.** The model establishes that
   ±1.00 dB has the discrimination wanted (rejects > 19 % low / > 23 % high, with the fixture's own
   ~6 % corner uncertainty spending only ~0.3 dB). **The model cannot establish that the real
   measurement chain has the remaining ~0.7 dB of headroom.** Freezing it now would promote an
   engineering assumption to an acceptance criterion. **Next step is to examine the EXISTING
   Tests 1–2 evidence for real bin-to-bin spread. Tests 1–2 are NOT to be rerun to obtain it** unless
   the existing evidence is proven insufficient *and* a test is separately authorised. Fallback if
   the spread is worse than assumed: ±1.50 dB, accepting that it tolerates a 27 % corner error.
4. **Slope stays a shape/sanity criterion** and is **not** promoted to a quantitative corner check:
   no noise-survivable tolerance on it beats criterion 1. It should be **re-centred on the
   model-derived expectation** so a correct fixture does not begin 0.816 dB/oct into its own
   tolerance. Its job is catching a non-first-order fixture, a wiring error or a dead HF band.
5. **Fixture candidate: 1 kΩ 1 % metal film + 100 nF film, ±5 % or better** — nominal 1591.5 Hz
   unloaded, 1631–1671 Hz loaded. **Candidate, NOT a specification.** The corner will be computed
   from the **measured** R and C with the MM420's stated accuracy recorded. The specification cannot
   close until measured R/C, meter uncertainty, codec loading and the final harness tolerance are all
   closed.

### Implementation plan — `DECISION`, not yet executed

**The criterion-1 change and the Phase 9 operator-facing text reconciliation are to be prepared
together and land in ONE compile / flash / identify cycle.** Shipping the criterion change alone
would create an intermediate build whose Test 4 semantics and operator instructions disagree — the
same class of defect TODO-55 exists to remove. **The two remain logically distinguishable** in the
commit and diff (criterion/threshold logic separate from prompt and default text), so either can be
reviewed or reverted on its own. Sequence is unchanged: freeze the tolerance → write both changes →
compile, flash, positively identify → TODO-48 runtime check → build and independently measure the
fixtures → only then Phase 9.

### Not done here

**No code changed. TODO-55 not updated.** No fixture built, nothing purchased, no bench action, no
serial traffic. The board still runs `44c4680`.

---

## 2026-09-21 (8) — Canonical repository **moved out of iCloud** to `~/Developer/guitar_rig_analyzer`. Old Desktop repository **FROZEN as evidence**. Environment verified before any new commit

### Why this entry exists

The working repository lived at `~/Desktop/guitar_rig_analyzer`, inside the iCloud Drive–managed
Desktop, and a file Git had deleted came back there (entry (7)). **A working tree that something
other than Git can write to cannot be the authoritative "active local tree"** that this journal's
source-of-truth rule depends on. So the repository was moved first, and the first commit in the new
location (this one) was held until the new environment had been verified.

### How it was moved

- **Cloned with `--no-local` from the complete local Desktop repository**, not re-cloned from
  GitHub. The local branches carry commits GitHub does not have: `docs/asbuilt-capture` is 26
  ahead of origin, `main` is 2 ahead, and the two firmware branches are local-only. `--no-local` copies objects
  rather than hard-linking or borrowing them, so the new repository shares no storage with the old.
- **Not pushed.** No commits were pushed during the migration.
- **Pruned:** stale remote-tracking refs for the firmware branches, inherited from the local clone.
- **Carried over:** the repository-local `user.name`/`user.email`, and the untracked `.mcp.json` with
  exactly one change — its absolute path `Desktop` → `Developer`. That change was proven by
  reversing the substitution and running `cmp` against the original (exit 0).
- **Not migrated, deliberately:** the config key `branch.docs/asbuilt-capture.vscode-merge-base`,
  which is disposable VS Code metadata.

### ✅ Verified state

| Check | Result | Tier |
|---|---|---|
| HEAD, old vs new | both `d8e1c9ab8e2b5393bf167aa42659628ee1eb37ad` | `OBS` |
| HEAD tree, old vs new | both `a0c250729fd11cd3a56c0250470e9fdc18862049` | `OBS` |
| Four local branches | identical commits in both repositories: `docs/asbuilt-capture` `d8e1c9a`, `main` `aa9a795`, `firmware/bench-safe-todos` `f1b13ed`, `firmware/todo-51-send-relay-toggle` `3ea3880` | `OBS` |
| Object storage | no `objects/info/alternates` file in the new repository | `OBS` |
| Tags / custom hooks | none / none | `OBS` |
| `origin` | `github.com/conley-vidal-eng-goat/guitar_rig_analyzer`; GitHub's default branch queried and confirmed as `main` | `OBS` |
| File Provider association | `~/Desktop` carries `com.apple.file-provider-domain-id`. **`~/Developer` and the new repository do not** | `OBS` |
| Obsolete PDF | `docs/breadboard_bringup_v3.pdf` **absent** from the new repository | `OBS` |

The table combines the migration session's checks with a read-only re-check at the start of this
session. Branches, HEAD/tree, alternates, tags, hooks, the xattrs and the PDF were re-observed
directly. The config value comparison, the `.mcp.json` `cmp` and the GitHub default-branch query come
from the migration session and were not repeated.

### Environment gate — passed before this commit

1. **Claude project memory** follows the working-directory path, so it did not move with the
   repository. All six memory files were copied to the new project's memory directory, SHA-256
   verified file by file (6/6 match), and the originals left in place. A seventh memory, *repository
   location discipline*, was added separately; none of the migrated memories was edited.
2. **Serial MCP initially failed to connect** in the new location. `.mcp.json` passes
   `--capture-dir=<repo>/.serial-logs`. That directory is gitignored, so the clone did not bring it
   (`OBS`), and the Teensy was also unplugged at the time (`OBS`). **With both conditions present,
   neither is established as the cause.** The missing directory is a plausible contributor
   (`INFERENCE`). After the empty `.serial-logs/` was created and the Teensy connected, the server
   connected and exposed all 28 tools. It enumerated `/dev/cu.usbmodem192895301` (Teensyduino,
   VID 16C0 / PID 0483, serial 19289530) and created its lock file in the **new** `.serial-logs/`.
   **No port was opened and nothing was sent to the board.** The old `.serial-logs/` held only an
   empty lock file, so no capture evidence was left behind.

### What the next session must know

- **Work only in `~/Developer/guitar_rig_analyzer`.** The journal header's source-of-truth path is
  updated to it in this commit. The one older `~/Desktop` mention (a HEX copied there on 2026-09-19)
  is historical and is left as written.
- **`~/Desktop/guitar_rig_analyzer` is FROZEN.** Do not edit, clean, move or delete it, or the
  returned PDF inside it. It is the evidence for entry (7). Retiring it is a later, explicit
  decision.
- **Do not put the canonical repository under Desktop or Documents** while those folders are iCloud
  managed.
- **The board is unchanged:** it still runs the `44c4680` build, and this commit is records-only.
  Firmware identity was **not** re-read in the new environment, since no port was opened.

No hardware action. No serial traffic. POWER ON (Teensy connected by USB only). No breadboard
changes.

---

## 2026-09-21 (7) — The obsolete `docs/breadboard_bringup_v3.pdf` **came back after Git deleted it.** Evidence strongly supports iCloud/File Provider restoration — **the restore itself was not observed**

### Why this is its own entry

This is a finding about the development environment, not about the analyzer. It is recorded apart
from the migration (entry (8)) so that the evidence and the inference can each be cited on their own,
and so that the move that followed is never read as proof of the mechanism.

### What was observed — `OBS` / `MEAS`

- **Deleted by Git:** `b6db3d6` (2026-09-20, the runbook v3.1 correction pass) deleted
  `docs/breadboard_bringup_v3.pdf`. It is not in HEAD.
- **Came back, byte-identical:** the file then reappeared in the Desktop working tree, where
  Git reports it as untracked (`??`). Its Git blob hash, `d066b4db3262a3089a0a21b2fc6bf140cbd5b4a5`,
  matches the blob `b6db3d6` removed.
- **Quarantine xattr names `com.apple.cloudd`.** Its embedded timestamp decodes to
  **2026-09-04 19:54**, which is **before** the 2026-09-20 deletion.
- **File dates:** birth and mtime are the original 2026-08-24 20:16:54; ctime is
  2026-09-21 21:42:37. Mode is `0600`.
- **`~/Desktop` carries the iCloud Drive File Provider domain** (`com.apple.file-provider-domain-id`),
  and **Desktop & Documents sync is enabled** (observed in the migration session; not re-checked
  here). Everything else in this list was re-observed read-only in this session.
- **Not affected:** `~/Developer` and the new repository carry no File Provider association.

### Inference — `INFERENCE`, not observation

**iCloud/File Provider most likely restored the deleted file.** The cloudd quarantine attribute, the
File Provider–managed parent directory, Desktop sync being on, and a byte-identical return with its
original dates all point there.

**Limits, stated so they are not lost:**

- **The restore transaction was never directly observed or reconstructed.** No sync log, event
  record or restore timestamp ties the file's return to iCloud.
- **The quarantine timestamp predates the deletion,** so it most likely records cloudd's *earlier*
  handling of the file, not the restore. It shows cloudd has touched this file. It does not
  timestamp the reappearance.
- **The 2026-09-21 ctime marks a metadata change on that date.** Nothing links it to the restore
  specifically.
- **The `0600` mode differs from the `0644` a normal Git checkout would give** under the default
  umask. That is consistent with a non-Git writer, but it is weak evidence and is not relied on.

### Consequence

- **The response is the repository move (entry (8)), not a cleanup.** The returned PDF is **left in
  place** in the frozen Desktop repository as evidence. It is **not** deleted in this commit.
- **Standing rule:** the canonical working repository stays outside iCloud/File Provider–managed
  directories.

No hardware action.

---

## 2026-09-21 (6) — Phase 9 fixture topology **approved in principle, NOT authorized for testing.** Three physical gaps resolved; the J2 stub is gone. **No hardware is to be built from the current Phase 9 instructions**

### Why this entry exists

The read-only triage found the Phase 9 fixture routing specified inconsistently — and read
literally, it can put an external generator in contention with the OPA1642 output. **This records the evidence and the decision before any
procedure is changed**, so the procedure change can cite what it rests on.

### The problem the topology resolves

- **The harness** (`validation.cpp`) says *"Y-split to both SOURCE_NODE and RETURN_NODE inputs"*,
  and its preflight prompt tells the operator to *"Connect your broadband signal source … to
  SOURCE_NODE."*
- **The runbook** (Phase 9 table) says *"Y-split so Instrument In + Rig Send are joined."*
- **SOURCE_NODE is col 48 — the OPA1642 output after C2** (10 µF ≈ 16 Ω at 1 kHz), and the
  permanent `48e → LINE-IN-L` jumper ties the codec's SOURCE input to that same node. Rig Send is
  driven *from* it through relay #1.
- **Read literally, both instructions put an external generator in contention with the op-amp
  output** — the same class of hazard as TODO-52.

### ✅ Three physical gaps, resolved — POWER OFF

| Gap | Finding | Tier |
|---|---|---|
| **Return reference** | Rig Return TS sleeve → Audio Shield/breadboard GND = **0.9 Ω** | `MEAS` |
| **Return connector** | **No loop is currently installed.** Phase 9 will require **Rig Return TS** explicitly rather than inherit any prior configuration | `PHYS/OBS` |
| **J2** | **Disconnected. No remaining conductor from SOURCE_NODE / col 48 to the former J2 connection** | `PHYS/OBS` |

**Bound on the 0.9 Ω reading.** It establishes **DC continuity** from the return sleeve to ground.
It does **not** by itself establish which ground point is the better *noise* reference: journal
2026-09-12 (3) measured a 33.1 dB difference between two ground points that are bonded at DC. The
reading is recorded as a return-path fact, not as a noise-floor claim.

**Why the connector finding matters.** Entry 2026-09-19 (8) had the loop running Rig Send →
**XLR** Return with the route on XLR, while today's fresh boot is on TS. **"Which return jack the
loop uses" was not established. It no longer needs to be** — nothing is installed, so the Phase 9
procedure will specify it.

### 🔻 Correction: the J2 stub assumption is stale

The trace in this session carried *"J2 = an open stub on SOURCE_NODE at `48a` — it must stay empty
during the tests."* **That came from `docs/asbuilt/netlist.md` and is no longer true.** J2 is
disconnected and leaves no stub. **It is dropped from the Phase 9 topology** — there is no J2
precondition.

**The netlist still records J2 in six places, all now stale:** lines 106, 130, 137, 397, 429 and
486 (the J2 row, its shield in the GND net, `J2 open jack (48a)` in the SOURCE_NODE net, deviation
X-2, GAP-3, and the "open stub" finding). **Not edited here** — the netlist belongs to the capture
session. This is the second stale netlist statement found this session, after `RETURN_NODE =
"no conductor fitted"`: **the netlist is frozen at Phase 5**, and the RETURN path exists only in
TODO/journal prose.

### The topology — APPROVED IN PRINCIPLE, NOT AUTHORIZED FOR TESTING

```
external source → J4 Instrument In → C1 → U1 buffer → C2 → col 48 = SOURCE_NODE
                                                          ├─► 48e → LINE-IN-L   = SOURCE (ch0)
                                                          └─► 48e → 56a NC → 57a COM → Rig Send
                                                                    [ FIXTURE UNDER TEST ]
                    LINE-IN-R ← 16a COM ← 15a NC ← Rig Return TS   = RETURN (ch1)
```

**SOURCE is sampled at col 48 / LINE-IN-L; RETURN at LINE-IN-R.** Preconditions: pin 14 LOW
(relay #1 NC) and pin 15 LOW (relay #2 TS) — both the boot defaults on `44c4680`.

**Why this topology is the right one.** The generator drives the high-impedance instrument input
(R5 through C1; the JFET draws pA) instead of fighting the op-amp output. And because **SOURCE is
measured at the fixture's input terminal and RETURN at its output**, the measured TF is the
fixture's own loaded voltage ratio — **the driving impedance drops out entirely** (op-amp, C2's
reactance, the relay contact), and the buffer, C1 and R5 are upstream of both measurement points.
That is also why TODO-21 does not block Phase 9.

**"Approved in principle" means:** the routing is accepted as the design basis for the procedure.
**It does not authorize building fixtures or running Phase 9.** Authorization waits for the Test 4
fixture design and the reconciled operator-facing text.

### What the trace established about the fixtures — recorded, NOT yet decided

Every fixture output is loaded by **Z_in**, the SGTL5000 LINE-IN-R input impedance. **Z_in is
unverified:** the ~40 kΩ figure appears only as an assumption in `validation.cpp`/`validation.h`
comments, with no measurement and no datasheet citation.

- **Test 3 — the prompt's own example fails a correct fixture.** A pad's ratio is
  (R2 ∥ Z_in) / (R1 + R2 ∥ Z_in), and the harness passes only if |measured − expected| **< 1.0 dB**.
  The prompt's 10 k/10 k example with its −6.0 default gives **−7.04 dB at 40 k, −7.40 at 29 k,
  −7.96 at 20 k — a FAIL at every plausible Z_in.** **✅ Decided 2026-09-21: option (a)** —
  keep the 10 k/10 k pad and take its expected attenuation from an **independent in-circuit
  measurement** (scope or DMM on the two jack tips, analyzer powered so the codec loads the pad),
  **never** from the −6.02 nominal or the −6.0 default. The text reconciliation must therefore remove
  or replace those defaults so an operator cannot fall back on them. *Option (b), 2.2 k/2.2 k —
  nominal holds at every Z_in, 4.4 kΩ load — was considered and not chosen.*
- **Test 4 — remaining design work.** 10 k + 10 nF passes across Z_in 20 k–∞ and capacitor error
  −20 %…+80 % (modelled with the harness's own bins and criteria). **That robustness is also a
  weakness:** the test cannot detect a wrong corner. The slope criterion's −6 dB/oct expectation is
  **unattainable over its window**, which starts at the corner where a first-order slope is still
  shallow — it measures about −5.0 even with the true corner entered, and passes only on its
  ±2 dB/oct tolerance. The runbook's planned 1 nF C0G is inconsistent with the harness's "keep
  resistors ≤ 10 kΩ" guidance (1 nF puts the corner at ≥ 16 kHz, outside the band). The 10 nF
  ceramic on hand has an unknown dielectric.

### Status and sequence

- **Current Phase 9 operator instructions are NOT to be followed**, in either the harness or the
  runbook. **No hardware is to be built from them** until the procedure is reconciled.
- **Next:** design the Test 4 fixture → reconcile all operator-facing Phase 9 text (harness prompts
  and comments, the `.ino` defaults, the runbook table) → **then** reconcile TODO-48's Proof line
  against the final harness behaviour.
- Tracked as **TODO-55**. Power OFF.

---

## 2026-09-21 (5) — ✅ **TODO-54 CLOSED.** One stale sentence in `signal_router.cpp` corrected. **Documentation only — and proven comment-only at the machine-code level**

### Scope, stated first

**This corrects stale documentation. It creates no new evidence about relay behaviour.**
The measurements the corrected comment points to were recorded in journal (4); nothing here
re-measures, extends or reinterprets them.

### The change

`signal_router.cpp`, the TS-at-boot paragraph. **Lines 30–32 unchanged byte-for-byte; the
accurate first clause of line 33 unchanged.** Only the stale sentence was replaced:

```diff
 // base pulldown holding the relay de-energised. As of ADR-004 the pin-15
-// driver is not built: that is a Phase 7 bench requirement, not something
-// this code proves.
+// base pulldown holding the relay de-energised. The pin-15 driver is built
+// (TODO-7), but that power-on state is still a hardware property, not
+// something this code proves; the reset-time measurements are recorded in
+// TODO-7 and journal 2026-09-21 (4).
```

**Why the boundary sat mid-line.** The stale sentence began partway through line 33, so "leave
lines 30–33 unchanged" could not be honoured literally. The precise boundary was lines 30–32
byte-for-byte plus line 33's first clause.

**The stale sentence made three claims, and only two were stale:**

| Claim | Status |
|---|---|
| "the pin-15 driver is not built" | **Stale** — built 2026-09-17, bench-proven 2026-09-19 |
| "that is a Phase 7 bench requirement" | **Stale** — met and measured |
| "not something this code proves" | **Still true — deliberately kept** |

**The last claim is the paragraph's durable point**, and it survived the correction on purpose.
Firmware can show that nothing *drives* pin 15 before `signalRouter_init()`; it cannot
establish the pin's *physical* level during reset. Measuring the hardware did not move that
boundary — it gave the hardware claim evidence.

**The corrected block now separates three kinds of authority:**
- **code** — establishes TS when `signalRouter_init()` executes;
- **hardware** — determines the physical state before that point;
- **records** — hold the empirical evidence for that hardware behaviour.

**Wording choices, recorded so the next edit understands them:**
- **It points at the evidence rather than restating it.** No `9.38 kΩ` or `≥200 mV` in the source:
  numbers in comments are what go stale, and pointers into the append-only `ai/` records do not.
- **It drops the dated "As of ADR-004" framing** — the phrasing that let the original rot, by
  describing a moment rather than a lasting fact.
- **It cannot overclaim.** It asserts no voltage or threshold, and names pin 15 only, so it
  implies nothing about a dynamic pin-14 test that was never made.
- **"that power-on state"** refers back to line 32's "PHYSICAL power-on state", keeping one
  concept rather than introducing a second term that could be read as a different interval.

### Verification — stronger than "it compiles"

**Compile:** `teensy:avr:teensy41`, **exit code 0** (captured as the return status), `--warnings all
--verbose`, fresh build path. **0 warnings, 0 errors.** Memory figures identical to `44c4680`.

**Machine-code comparison against the archived `44c4680` build artifact**, section by section.
That artifact is bound to the board by the controlled flash-and-identity record in entry (3) —
**the board's flash contents were not read back and compared.** The sections compared are the
allocated sections with file contents, enumerated from the ELF section table; `.bss`,
`.bss.dma` and `.bss.extram` are `NOBITS` and carry no contents to compare:

| Section | Result |
|---|---|
| `.text.headers` `.text.code` `.text.progmem` `.text.itcm` `.fini` `.ARM.exidx` `.text.csf` | **IDENTICAL** |
| `.data` | **4 bytes differ** |

**The four bytes are exactly the time digits of `__TIME__`** — at offsets 16705, 16707, 16710,
16711, `17:21:24` → `19:41:10`. The date string is unchanged. **Every compared loadable section
is byte-identical to the archived `44c4680` artifact except `.data`, which differs by exactly the
four time digits of `__TIME__`.**

> **So "comment-only" is established at the machine-code level, not asserted from the diff.**
> Matching memory figures alone would not have shown that.

**⚠️ The first comparison attempt FAILED — and printed nothing.** A loop over section names
extracted from `readelf` returned **empty output**, because the name extraction itself had
failed. **Empty output is not evidence of equality.** It was not treated as a pass: the section
table was listed explicitly and each section compared by name, which produced the table above.

> **This is the same failure mode as the lost upload exit code (entry (2)):** the absence of an
> error signal read as success. **A check that cannot fail is not a check** — before trusting a
> "no differences" result, confirm the check actually examined something.

**Not flashed, deliberately.** No executable difference was found in the compared loaded sections
apart from build-identity timestamp data, so there is no runtime behaviour to validate.

### State after this commit

- **The board still runs `44c4680`** (`Build: Sep 21 2026 17:21:24   v0.6.0`, hex md5
  `65405de70fc778fdd8cf6a48e1cbe45e`). **HEAD is now ahead of the board by a comment-only
  commit.** No executable difference was found between the two in the compared sections, but the board's
  self-reported identity is still `44c4680`'s, and any future bench entry should record it as such.
- Power **OFF**.

**Next:** TODO-48 — the validation harness runtime check — and then the Phase 9 fixtures.

---

## 2026-09-21 (4) — ✅ **TODO-50 CLOSED on its existing Proof line.** The unobserved boot prefix is closed by code evidence, not by redefining the criterion. Pin-15 scope work is recorded separately, as evidence that goes *beyond* what TODO-50 requires

### The Proof line, and how it was read

> *"a fresh boot with no commands prints a route description matching the router's
> selection, and the boot still **shows** no relay actuation and no ROUTE_CHANGED."*

**It was evaluated as written.** It does not say "electrically prove that neither relay
coil energised during reset" — it asks what the boot *shows*. Closing it on that reading
is **not** a reinterpretation; strengthening it now to require electrical proof would have
been one, in the other direction.

**Why it was held at 🟡 in entry (3):** the serial capture began mid-boot, so the
early part of startup was not observed. That was the right call **while serial output was
the only evidence.** It no longer is.

### Evidence layer 1 — `OBS/RUN`: the fresh boot

- **Fresh boot of identified firmware `44c4680`** (`Build: Sep 21 2026 17:21:24   v0.6.0`,
  hex md5 `65405de70fc778fdd8cf6a48e1cbe45e`). The upload rebooted the board.
- **No serial command was sent.**
- `signalRouter_init()`'s own output was captured:
  `[SignalRouter] Return source: TS (operator-selected; boot default)` and
  `[SignalRouter] Route: TS return, no injection`.
- The first 5 s diagnostic agreed: `[Main] Route: TS return, no injection`.
- **No `ROUTE_CHANGED` appears.** The stale `Default bench: SOURCE_NODE=L, RETURN_NODE=R`
  string TODO-50 was opened for is gone.

### Evidence layer 2 — `CODE/ELF`: the unobserved prefix contains no path that can drive a relay pin

Traced read-only at clean `08f50cf`, checked against the **flashed ELF** rather than source
alone.

**Where the capture began:** `audio_capture.cpp:412`
(`[SGTL]   NOTE: codec silicon ID/revision.`), partway through the SGTL register dump inside
`audioCap_init()` (`.ino:323`). **The first firmware writes to pins 14 and 15 are all
inside `signalRouter_init()` at `.ino:402` — inside the captured window**, and its output is
in the transcript.

**Every relay write in the tree** — nine sites, all in `signal_router.cpp`:

| Site | Call | Class |
|---|---|---|
| `:200` `:201` | `pinMode(RELAY_SEND/RETURN_PIN, OUTPUT)` | executed by `signalRouter_init()` |
| `:202` `:203` | `digitalWrite(…, LOW)` | executed by `signalRouter_init()` |
| `:153` | `applyReturnRelay(TS)` → LOW | executed by `signalRouter_init()` (also `j` at runtime) |
| `:148` | `applyReturnRelay(XLR)` → HIGH | operator command `k` only; init always passes TS |
| `:289` | `digitalWrite(RELAY_SEND_PIN, LOW)` | `loop()` only, behind a guard that cannot be true |
| `:354` `:363` | `signalRouter_setInjectionEnabled()` | **zero callers** |

**None is reachable before the capture boundary. None is reachable between the boundary and
`signalRouter_init()`.** No literal `pinMode/digitalWrite(14|15, …)`; no direct
`GPIO6_DR`/`GDIR`/`digitalWriteFast` writes. `signal_router_config_additions.h` also
defines both pins but is **not `#include`d anywhere.**

**Non-project paths, checked because a name search cannot settle them:**
- **Teensy core ResetHandler.** `GPR26–29 = 0xFFFFFFFF` selects the fast GPIO bank; it
  sets neither direction nor output. `analog_init()`, `pwm_init()`, `usb_init()` make no
  pin mux, pad or drive changes.
- **Peripheral claims.** Pins 14/15 are also A0/A1 and Serial3 TX/RX. `Serial3`,
  `analogRead`, `A0`/`A1`, `analogWrite`, `tone(`, SPDIF and MQS: **0 hits.** The linked
  I2S objects configure pins **7, 8, 20, 21, 23** only.

**🔍 The non-obvious route, worth keeping as method.** Four Audio-library translation
units *do* configure pins 14/15 — `AudioInputSPDIF3`, `AudioOutputSPDIF3`,
`AudioOutputI2SQuad`, `AsyncAudioInputSPDIF3` — and **all four are linked into the flashed
binary, with static initializers that run in `__libc_init_array()` before `setup()`.** A
substring match on class names made this look alarming. It resolved cleanly only by
checking the chain link by link:

1. Each one's pin-14/15 configuration lives entirely inside **`::begin()`**
   (`input_spdif3.cpp:72`, `output_spdif3.cpp:94`, `output_i2s_quad.cpp:69`,
   `async_input_spdif3.cpp:115`).
2. **None of the four `::begin()` functions is linked.** The project constructs no
   instance of any of them.
3. What the static initializers *do* build is the static `DMAChannel dma` member, whose
   constructor calls `DMAChannel::begin()` — **DMA channel allocation only, no pin, pad or
   GPIO access.**

> **Lesson:** "linked" and "executed" are different claims, as are "a static initializer
> runs" and "the code that touches the pin runs." The Arduino build links every `.o` of a
> used library, so library code a sketch never calls still gets static initialization.

**What this layer does and does not establish.** It establishes that **no firmware can
actuate a relay** during the unobserved prefix. It does **not** by itself establish the
relays' *physical* state then: with no code driving them, pins 14/15 sit as undriven inputs
at MCU reset state, and each relay is held off by its **base pulldown**, not by firmware.
That gap is hardware, and layer 3 addresses it for pin 15.

### Evidence layer 3 — `MEAS`: pin 15, passive and dynamic

**Passive, POWER OFF, in circuit:**

| Probe | Reading |
|---|---|
| Pin 15 → GND | **9.38 kΩ** |
| Pin 15 → +3.3 V | **14.58 kΩ** |

*In-circuit readings include parallel paths; they are not the resistor's value and are not
interpreted as such here.* They **confirm a DC path to ground is present** on pin 15 —
the pulldown TODO-7 recorded as built (`RPT`) but never measured.

**Dynamic, three OFF→ON boots, DHO804 CH1 on Teensy pin 15, rising-edge trigger:**

| Boot | Trigger threshold | Result |
|---|---|---|
| 1 | +1.0 V | no positive excursion detected |
| 2 | +500 mV | no positive excursion detected |
| 3 | **+200 mV** | **scope remained WAIT for 10 s** |

> **Conclusion, stated at its true strength: no positive pin-15 excursion ≥200 mV was
> detected during the tested OFF→ON startup.**
>
> **Not** "pin 15 remained at 0 V", and **not** "no transient of any magnitude occurred."
> Below 200 mV the test increasingly measures noise, probe and trigger behaviour rather
> than the engineering question, so the threshold was deliberately not lowered further. A
> transistor driver designed to switch from a 3.3 V GPIO is nowhere near turn-on at
> <200 mV at its input.

**Scope of layer 3:** pin **15** only. **Pin 14 was not measured dynamically**; its
pulldown presence is `MEAS` from Phase 6 (V6f, 8.94 kΩ in circuit).

**Why this matters beyond TODO-50:** TODO-7 recorded explicitly that *why* pin 15 is LOW
at power-on was unproven — *"the 10 kΩ pulldown and `signalRouter_init()`'s
`digitalWrite(RELAY_RETURN_PIN, LOW)` both hold it there … Distinguishing them needs a
measurement during reset, before `setup()` reaches the router."* **This is that
measurement.** Combined with layer 2, which shows no firmware drives pin 15 before
`signalRouter_init()`, pin 15's reset-time behaviour now rests on direct dynamic evidence
rather than on an inference from the pulldown.

### Clause-by-clause result

| Proof clause | Evidence | Result |
|---|---|---|
| Fresh boot with no commands | Upload rebooted `44c4680`; no command sent | **PASS** |
| Route description matches router selection | Router reported TS; `[Main] Route: TS return, no injection` agreed | **PASS** |
| Boot shows no relay actuation | Captured router output shows no actuation/transition; **layer 2** shows the uncaptured prefix contains no firmware path capable of it | **PASS** |
| No ROUTE_CHANGED | None in the capture; the fix uses a description-only setter by design | **PASS** |

**TODO-50 → 🟢.** **The scope measurements (layer 3) are NOT part of this acceptance
criterion** and are not being retroactively made part of it. They strengthen the
engineering record independently.

### Source-documentation defect found during the trace — recorded, NOT fixed here

`signal_router.cpp:33–35`: *"As of ADR-004 the pin-15 driver is not built: that is a
Phase 7 bench requirement, not something this code proves."* **Stale** — the driver was
built at columns 8–18 on 2026-09-17 and bench-proven on 2026-09-19.

**Only that final sentence is wrong.** Lines 30–33 — the two-layer TS-at-boot model, and
that before `signalRouter_init()` the physical state *"depends on the RELAY_RETURN driver's
base pulldown"* — **are still accurate, and today's measurements now support them.** A
correction should replace the stale sentence, not the paragraph.

**Deliberately not fixed in this records commit**, so that discovery and correction stay
separate in the history. Tracked as TODO-54.

---

## 2026-09-21 (3) — ✅ **TODO-27 CLOSED on hardware.** The firmware now describes FFT cadence consistently everywhere it speaks. **The fix grew from one known line to ten sites across seven files — including a Phase 9 runtime defect**

### Why this entry exists as more than a status flip

TODO-27 was believed to be one stale diagnostic in `audio_capture.cpp`. **A read-only
audit run *before* any edit, searching by value and expression rather than by
identifier, found ten current representations of the same window-for-hop error
across seven files.** One of them changed runtime behaviour in the Phase 9 path.
The original fix had been scoped by the `EXPECTED_BLOCK_MS` identifier and by the
paragraph being edited, and **every instance that computed the period inline
survived** — including one four lines below the correction itself, in `config.h`.

That is the C1-01 four-representations lesson (journal 2026-09-20 (1)) recurring in
firmware, **after** the rule had been written down. What changed this time is that the
lesson altered the *method* — audit first, edit second — rather than only being
recorded afterward.

### The audit inventory (`44c4680`, 10 sites / 7 files)

| Class | Site | What was wrong |
|---|---|---|
| **ACTIVE/RUNTIME** | `validation.cpp:170` | `collectFrames()` deadline used `FFT_SIZE`: **4829 ms for a 2415 ms collection** |
| ACTIVE/DIAGNOSTIC | `audio_capture.cpp` FFT line | `23.2 ms/frame` — a correct *window* wearing a label that reads as a cadence |
| ACTIVE/DIAGNOSTIC | `audio_capture.cpp` block line | `4 frames × 23.2 ms = 92.9 ms` — the known contradiction |
| ACTIVE/DIAGNOSTIC | `validation.cpp:345,347` | Operator timing estimate `~3.0 s + ~1.9 s`; true `~1.5 s + ~0.9 s` |
| ACTIVE/COMMENT | `config.h:446-447` | Display-rate note `~92.8 ms, ~10.8 fps` — **four lines below the first todo-27 fix** |
| ACTIVE/COMMENT | `validation.h:92-94` | `≈ 92.8 ms … ≈ 2.97 seconds` |
| ACTIVE/COMMENT | `audio_capture.cpp:219` | `~92.9 ms` |
| ACTIVE/COMMENT | `guitar_rig_analyzer.ino:652` | `~92.9 ms` |
| DOC/CURRENT | `README.md:266` | `92.9 ms … 10.8 fps`, user-facing |
| DOC/CURRENT | `docs/pi_link_protocol_audit.md:336` | `~5.4 fps`, derived from the wrong base |

**The runtime defect failed safe** — the guard was loosened, never tightened — so it
caused no spurious aborts. But it did not bound a stuck codec as tightly as designed,
and it sits directly in the Phase 9 path. Verified numerically from the constants
after the fix: `expected_ms` = **2414 ms**, tracking the true 2414.9 ms duration at
**1.000×**; deadline `2414 + 1207 (50 %) + 1000` = **4621 ms**. **The designed
+50 % + 1000 ms margin policy is unchanged**; ~2.2 s of slack remains over the
measured collection.

### ⚠️ Legitimate numerical collisions — preserved on purpose

A value-only search would have "fixed" these into errors. **Classify semantically
before replacing.**

- **`measurement_core.h:134` — `92.9 ms/frame` for a 4096-point FFT.** That is
  `4096 / 44100`, a correct window duration for a different transform. Same number as
  the defect; unrelated quantity. **Untouched.**
- **`config.h:447` — `~92.9 ms` for `DISPLAY_UPDATE_EVERY_N_FRAMES = 2`.** That is
  `2 × 46.44 ms` and is **correct** — the same number that was wrong on the N=1 line
  four lines above. A collision warning was added so the next auditor does not
  "correct" it.
- **`config.h:401,415` and `measurement_core.h:128`** — 23.2 ms explicitly described as
  the 1024-sample *window*. Correct; kept.

The `audio_capture.cpp` fix therefore **names both quantities** instead of replacing
one with the other: the 23.2 ms window is real and useful — it simply is not the rate
at which results arrive.

### The evidence chain on hardware

| Tier | Link | Value |
|---|---|---|
| `OBS/BUILD` | Clean revision | **`44c4680`**, tree verified CLEAN |
| `OBS/BUILD` | Artifact | HEX **MD5 `65405de70fc778fdd8cf6a48e1cbe45e`**, embedded `Sep 21 2026 17:21:24   v0.6.0` |
| `OBS/BUILD` | Re-verified | MD5 re-checked immediately before upload, after the session scratchpad path changed |
| `OBS/UPLOAD` | Upload | **EXIT 0**, captured as the process return status |
| `OBS/RUN` | Board's own report | **`[Main] Build: Sep 21 2026 17:21:24   v0.6.0`** at uptime 13 s |

### `OBS/RUN` — the observations, verbatim

```
[AudioCapture] FFT: 512 bins, 43.07 Hz/bin, 23.2 ms/window, 11.6 ms hop (50% overlap)
[AudioCapture] Block period: 4 results × 11.6 ms hop = 46.4 ms
[Validation] Collection: 32 blocks (~1.5 s) + 20 settle blocks (~0.9 s)
...
[Main] --- 5s diagnostics (uptime 13s) ---
[Main] Build: Sep 21 2026 17:21:24   v0.6.0
[Main] Block:      108 in 5000ms = 46.3 ms/block (expected 46.4 ms, delta -0.1 ms)
[Main] Display: 108 updates = 46.3 ms/update (expected 46.4 ms)
[Main] Loop:         4875902 iterations/5s = ~975180/sec
...
[Main] Route: TS return, no injection
```

**The contradiction that held TODO-27 at 🟡 is gone.** The same boot previously printed
`92.9 ms` at AudioCapture and `46.4 ms` at Main. Now **23.2 ms window, 11.6 ms hop and
46.4 ms averaged result** are stated consistently, and Main **independently measures
46.3 ms** against that expectation.

**The `[Validation] Collection:` line came from `validation_init()` during ordinary
startup. VALIDATION WAS NOT INVOKED** — no `v`, no `1`–`4`. It moved from the stale
`~3.0 s / ~1.9 s` to `~1.5 s / ~0.9 s` with no test running.

**No serial command was sent at any point.** `q`, `v`, `m` untouched. The boot command
list contains no `q`. Route TS, `injection_active` false.

### ⚠️ Startup identity vs periodic identity — do not conflate them

> **The startup identity mechanism was not observed in this capture. The periodic
> identity mechanism was observed and positively identified the running compile after
> late host attachment.**

The ring began partway through the SGTL register dump, so the top-of-boot banner and
its `Build:` line had already been emitted before any host attached.
`arduino-cli upload` returns only after the board reboots, and the port was opened
after that, **so the 3 s bounded wait had already expired.**

**Do not record the bounded host-wait or the startup banner as bench-proven.** Neither
was observed. What *is* proven is the case the periodic line was designed for: a host
attaching late still gets a positive, self-contained compile identity within one 5 s
interval, **with no reset, power cycle or timing race** — the problem that four capture
strategies failed to solve earlier today.

### 🔍 Loop rate — second observation, still unexplained

`~975 180/sec` on `44c4680`, following `~973 469/sec` on `399e54b`, against
`≈ 950 000/sec` in every earlier capture.

**Two separately compiled post-change binaries now reproduce the higher rate.** That
makes it more interesting than the first isolated reading — **but it establishes
neither a cause nor that the firmware changes caused it.** Recorded as an open
observation, not a regression or improvement.

### Status

- **TODO-27 → 🟢 CLOSED.** Its Proof line has two clauses and both are met.
  *"Diagnostics report a delta near zero on a healthy run"* — **delta −0.1 ms**, `OBS`.
  *"No diagnostic anywhere in the firmware states the block period as 92.9 ms"* —
  verified on the **flashed binary**, not inferred from source: no 92.88 ms float
  constant, no literal `92.9` in any string, no stale format string; the source contains
  zero `FFT_AVERAGE_COUNT * FFT_SIZE` expressions; and the previously offending
  diagnostic was observed reporting 46.4 ms.
- **TODO-48 stays 🟡.** Flashed and running; its proof is a runtime check of the harness
  that has not been run.
- **TODO-50 stays 🟡 — by explicit decision, not because the evidence is absent.** Its
  Proof line: *"a fresh boot with no commands prints a route description matching the
  router's selection, and the boot still shows no relay actuation and no ROUTE_CHANGED."*
  **Today's capture was in fact a fresh boot with no commands** — the upload rebooted the
  board, and the ring contains `signalRouter_init()`'s own output:
  ```
  [SignalRouter] Return source: TS (operator-selected; boot default)
  [SignalRouter] Route: TS return, no injection
  ...
  [Main] Route: TS return, no injection
  ```
  The router's selection and the 5 s diagnostic agree, and **no `ROUTE_CHANGED` appears
  in the capture.** That is the failure TODO-50 was opened for, now absent.
  **The gap:** the capture began partway through boot (mid-SGTL register dump), so the
  **complete** boot sequence was not observed. The missed region is the banner,
  `presentation_init()` and DataSender init — none route-related, and it precedes
  `signalRouter_init()` — but "the boot still shows no relay actuation" is a claim about
  the whole boot, and part of it was not seen. **Whether that satisfies the Proof line is
  left as a decision rather than resolved by reinterpreting it here.**

**Next:** TODO-48's runtime check, then TODO-50's fresh-boot observation, then the Phase
9 fixtures.

---

## 2026-09-21 (2) — ✅ **TODO-53 CLOSED. The running firmware positively identifies itself.** The board is no longer an unidentified binary

### The evidence chain, link by link

Every step below is `OBS`; **there is no inference between them.**

| Tier | Link | Value |
|---|---|---|
| `OBS/BUILD` | Clean revision | **`399e54b`**, tree verified CLEAN at build time |
| `OBS/BUILD` | Artifact it produced | HEX **MD5 `55a45287ae39c5a5ffbc33f08e6801eb`**, 674 074 B |
| `OBS/BUILD` | Identity embedded in it | **`Sep 21 2026 17:09:03   v0.6.0`** |
| `OBS/UPLOAD` | First attempt | **EXIT 1 — FAILED. Nothing was written.** |
| `OBS/UPLOAD` | Second attempt, same artifact, no rebuild | **EXIT 0** |
| `OBS/RUN` | Board's own report, 11 s after attaching | **`[Main] Build: Sep 21 2026 17:09:03   v0.6.0`** |

```
[Main] --- 5s diagnostics (uptime 11s) ---
[Main] Build: Sep 21 2026 17:09:03   v0.6.0
[Main] Block:      108 in 5000ms = 46.3 ms/block (expected 46.4 ms, delta -0.1 ms)
[Main] Display: 108 updates = 46.3 ms/update (expected 46.4 ms)
[Main] Loop:         4867344 iterations/5s = ~973469/sec
[Main] SOURCE_NODE peak: -64.7 dBFS          |   RETURN_NODE peak: -62.7 dBFS
[Main] TF confidence: 0%          (threshold 10%)   persistence: ACTIVE
[Main] TF clamped bins: 0 of 512
[Main] Route: TS return, no injection
```

### ⚠️ What the stamp does and does NOT assert — read before citing this

**The firmware does not contain the git hash.** `Build:` is `__DATE__`/`__TIME__` plus
`FIRMWARE_VERSION`; it **positively identifies the COMPILE and nothing more.**

The revision→artifact association comes from the **controlled clean-tree build
record above** — a build run from a verified-clean `399e54b`, whose artifact hash
and embedded stamp were both recorded before the upload. **Taken together** the two
halves bind this running compile to `399e54b`.

> **Do not restate the stamp as though it independently asserts the commit.** It
> does not. If this record is lost, the board can still tell you *which compile* is
> running but not *which revision* produced it. Any future bench entry must record
> the observed `Build:` line **together with** the revision and artifact hash.

### `OBS/RUN`: what else the same interval established

- **`q` / temporary relay-toggle functionality is ABSENT** from the active tree and
  from the flashed artifact — verified by string and symbol search on the `.elf`
  before upload, and no `[BringUp]` line at runtime.
- **TODO-27's corrected constant is live:** `expected 46.4 ms`, delta **−0.1 ms**
  (the old build reported 92.9 ms and a permanent phantom −46.6 ms anomaly).
- **TODO-50's fix is live:** `Route: TS return, no injection` — the router's real
  state, not audio_engine's stale init string.
- Pin 14 **LOW**, route **TS**, idle floors ≈ −63 dBFS with nothing connected.
- **No serial command was sent at any point.** `q`, `v`, `m` untouched; validation
  not run.

### 🔍 Unexplained observation, preserved rather than explained

**Loop rate reads `~973 469/sec` (4 867 344 iterations / 5 s).** Every prior capture
in this project reads **≈ 950 000/sec** — about **2.5 % higher now**.

**No cause is offered and none should be assumed.** The bounded serial wait runs once
in `setup()` and cannot affect the loop; one extra `printf` per 5 s interval is far
too small. **This is not recorded as a regression, an improvement, or noise** — it is
recorded as a difference nobody currently understands. If it persists, it is a fact
about this build worth explaining; if it vanishes, that is also information.

### 🔑 Process lessons — the durable output of today

**1. Bench firmware identity must be observable AFTER attachment, not only during boot.**

The first stamp (`57dcdc1`) printed once in `setup()` and **was never captured, across
four independent strategies**: a late monitor open, a DTR/RTS pulse (Teensy 4.x ignores
those lines — uptime ran straight through, proving no reset), a physical button press
(the Teensy 4.1 button is *program mode*, not reset — it halts the sketch rather than
restarting it), and a USB power cycle with a pre-armed catcher.

**The root cause is structural, not procedural.** `Serial` here is USB CDC: Teensy
**discards everything written before a host asserts DTR**, and enumeration takes
≈1–2 s — longer than `setup()` takes to reach the banner. The identity was emitted
into a void on every cold boot, and **no amount of host-side care could recover it.**

> **A once-at-boot banner cannot establish identity on a USB-CDC board.** The fix
> (`399e54b`) was to repeat the identity in the 5 s diagnostics, so **every captured
> interval carries its own compile provenance** instead of needing correlation with a
> boot event that may never have been captured. A bounded host-wait was added too, but
> **the periodic line is the one that actually solves it.**

**2. Upload success must come from the process RETURN STATUS, never from the absence of error text.**

Today's first upload **exited 1** — `"Unable to open /dev/cu.usbmodem192895301 for
reboot request"` — because an open serial connection held the port. **Nothing was
written.**

**This is the sharper half of the lesson:** the *earlier* upload in this session
(2026-09-21, pre-`399e54b`) was reported as success **on the strength of normal-looking
output alone, because the exit code was lost to a shell-construction error.** It
happened to succeed only because no serial connection was open at that moment. **Had
one been, it would have failed identically and the failure would have been invisible**
— which is exactly the 2026-09-19 flash-identity incident rehearsing itself.

Both lessons point the same way as journal 2026-09-20 (1)'s four-representations rule:
**evidence that requires you to have been watching at the right instant is not
evidence you can rely on.**

### Status

**TODO-53 → 🟢 CLOSED.** Its Proof line is exactly two clauses and both are now met:
*"the board runs a build whose identity is recorded in the journal"* (this entry) and
*"no temporary relay command remains in the active tree"* (`q` absent from `399e54b`
and from the flashed artifact).

**TODO-27 stays 🟡 and must NOT be promoted on this capture.** Its corrected constant
being observed live is real, but journal 2026-09-21 (1) recorded a **second, stale
representation of the same 2× error** — `audio_capture.cpp` prints
`Block period: 4 frames × 23.2 ms = 92.9 ms` at init, so **this firmware now reports
46.4 ms and 92.9 ms in the same boot sequence.** That reconciliation is outstanding and
is deliberately untouched here.

**Next:** the Phase 9 chain now stands at `q worktree preserved` ✅ → `TODO-52` ✅ →
**`identified firmware on the board`** ✅ → bench-verify TODO-27/48/50 → build fixtures
→ Phase 9. **TODO-27/48/50 remain 🟡** — they are now *running*, which is not the same
as *bench-verified against their own proof criteria*.

---

## 2026-09-21 (1) — ✅ **TODO-52's decisive test was run. No second Rig Send TIP feed was detected.** The output-contention hazard is cleared as `MEAS`; the netlist clause is not

### The measurements, exactly as observed

Power **OFF** throughout. One wire lifted at one end, nothing else changed.

| # | Condition | Probe | Reading | Tier |
|---|---|---|---|---|
| 1 | **COM→TIP lifted at `57a`** | Rig Send TIP → `48d` | **OPEN** | `MEAS` |
| 2 | **COM→TIP restored at `57a`** | Rig Send TIP → `48d` | **CONTINUITY (beep)** | `MEAS` |

**PHYS:** probes removed; Rig Send ↔ Rig Return loop cable disconnected for the
test and **restored at both ends afterwards, exactly as before**. Power left OFF.

### What this establishes — stated narrowly on purpose

> **No second feed to the Rig Send TIP was detected by this isolation test. The
> known COM→TIP connection accounts for the measured continuity.**

Reading 1 is the decisive one. With COM lifted, **every** remaining path from the
TIP to col 48 would have to be a *second* feed — and there was none. Reading 2 is
the control that makes reading 1 mean something: it proves the meter, the probes
and the TIP node were all live, so the OPEN was an open circuit and **not a bad
probe contact**. Taken alone, reading 1 is indistinguishable from a failed
measurement. **That pairing is what upgrades this from `RPT` to `MEAS`.**

**This is what the hazard required.** TODO-52's concern was a direct TIP↔col 48
tie *in addition to* the COM path: in the HIGH state COM moves to `58a` = LINE
OUT L, and with a second feed still holding the TIP on col 48, the codec's
line-out driver would be tied to the OPA1642 buffer output through C2 — and,
because `audio_capture.cpp:168–172` puts a reconstructed copy of SOURCE_NODE on
LINE OUT L, that is a **closed loop around the codec**, not merely static
contention. **Reading 1 refutes the condition that loop depends on.**

### ⚠️ What it does NOT establish — recorded before it hardens into more than it is

- **"Exactly one feed" is NOT proven.** What is proven is *no second path from the
  TIP to `SOURCE_NODE`/col 48*. A conductor from the TIP to some unrelated node
  would not have shown up. **The visual check — count the conductors on the TIP
  lug — was not performed**, and it remains the only thing that would establish
  the count directly.
- **The two supplementary checks suggested with the decisive test were not taken:**
  TIP → `56a` and TIP → `58a`, both while COM was lifted.
- **The `58a` case is nevertheless covered — by an earlier measurement, not by this
  one.** Journal 2026-09-19 (8) recorded `58a` → `48d` = **OPEN**, power off,
  relay LOW, **with the TIP connected through COM**. Had a stray TIP↔`58a` tie
  existed, that probe would have reached col 48 the long way round
  (`58a` → TIP → COM `57a` → NC `56a` → `48e` ≡ `48d`) and beeped. It did not.
  **So the conclusion rests on two measurements taken a day apart, and that
  dependency is stated here rather than folded into today's result.**

### Status change, and one that deliberately does not follow

**TODO-52's electrical hazard is cleared (`MEAS`).** The item does **not** go
🟢, because its Proof line has a second clause — *"`docs/asbuilt/netlist.md`
records `56a`/`57a`/`58a` and the tip's source explicitly"* — and that netlist
still has no entry for those three columns. **That file belongs to the concurrent
capture session; coordinate rather than editing it unilaterally.** TODO-52 is
therefore 🟡 with the hazard resolved and the record clause outstanding.

> **🔒 This does NOT mean "`q` is now safe to press", and nothing here should be
> cited that way.** What is cleared is *one specific* hazard: the two-feed
> contention/loop. **TODO-53's other conditions are unchanged** — the board is
> still running an unidentified temporary build, the send path still has no real
> owner, and whether to energise pin 14 is a bench judgement that belongs to the
> bench, not to this entry. Pin 14 was last left **LOW**, which remains the safe
> side.

### Where this leaves the Phase 9 chain

`preserve/understand q worktree` ✅ (`3ea3880`) → **`TODO-52 feed-count` ✅ (today)**
→ `build/flash an identified HEAD` → `bench-verify 27/48/50` → `construct
fixtures` → `Phase 9`.

**Why TODO-52 came before the reflash, restated so the ordering survives without
this conversation:** not because any firmware depended on it, but because it was
the outstanding **physical-topology** fact needed to trust the Test 1 Y-split
fixture — Test 1 attaches to exactly this node. Knowing which binary is on the
board is *repository identity*; knowing the TIP has no second feed is *electrical
validity*. **A reflash settles the first and says nothing about the second.**
Conflating them is how a clean-looking test run gets taken for a valid one.

**Next:** build and flash an identified HEAD (TODO-53), then re-verify TODO-27,
TODO-48 and TODO-50 on hardware — they are still compile/link-verified only.

---

## 2026-09-20 (1) — The 2026-09-19 firmware and runbook work was **lost, not merged**. Rewritten from the record and committed in four reviewed commits. **Compile/link verified only — nothing has been flashed and nothing is bench-verified.**

### What happened to `firmware/bench-safe-todos`

Journal 2026-09-19 (5) recorded three firmware fixes and an eleven-defect runbook
pass as *"done on branch `firmware/bench-safe-todos` in a separate git worktree
… Nothing is committed. Review with `git diff main firmware/bench-safe-todos`."*

**That branch is an empty label.** It points at `f1b13ed`, the same commit as
`docs/asbuilt-capture`, with **zero commits on it.** The worktree it lived in was
under a session scratchpad, `git worktree list` marks it **prunable**, and the
directory is gone. No stash. `git fsck` turns up two dangling commits, both
unrelated (the Sep 1 initial commit and a Sep 7 WIP).

Verified against the live tree rather than the record, per this file's own
source-of-truth rule — and the tree was unambiguous: `validation_waitForUser()`
was still `void`, there was no `validation_preflightGate`, no
`audioEngine_setRouteDescription`, `EXPECTED_BLOCK_MS` still used `FFT_SIZE`, and
the runbook had no Appendix C.1 and no "Board coordinates" section.

**The work was unrecoverable and was rewritten from the descriptions in journal
(5) and the TODO items.**

> **🔻 The lesson is not "be careful with worktrees."** A scratchpad worktree is
> ephemeral by design. The failure was leaving four hours of reviewed work
> **uncommitted** in one, and then writing the record as though a branch name were
> durable provenance. **A branch that has never been committed to is indistinguishable
> from one that does not exist.** Commit first, then record the hash — not the
> branch name.

### The four commits

| Commit | What | Status |
|---|---|---|
| `b2cdb4f` | **TODO-48** — harness consent + shared preflight gate | compile/link verified |
| `3fdde97` | **TODO-50** — `audioEngine_setRouteDescription()`, boot stays a non-transition | compile/link verified |
| `b275852` | **TODO-27** — `EXPECTED_BLOCK_MS` uses the FFT hop; `config.h` comment corrected | compile/link verified |
| `b6db3d6` | **Runbook v3.1** — thirteen defects, Board coordinates section, Appendix C.1; stale PDF removed | documentation only |

**⚠️ ALL FOUR ARE COMPILE AND LINK VERIFIED ONLY. NOTHING HAS BEEN FLASHED.
NOTHING IS BENCH-VERIFIED.** No TODO moves off 🟡 on account of these commits.
This distinction is the whole point of Phase 9: the validation suite exists to
establish **real signal-path behaviour against explicit pass criteria on
repeatable physical measurements**, and "the code is correct" is not a claim it
makes or accepts. A compiling harness is a precondition for running Phase 9, not
a part of its result.

### One design decision that departed from journal (5)

Journal (5) described TODO-48 as making the `1`–`4` commands *"run the same
preflight as `v`."* **Implemented literally, that fails a correct fixture.**

`runAll()` runs preflight **once**, against the plain Y-split where SOURCE and
RETURN carry the same signal. Tests 3 and 4 then **deliberately attenuate RETURN**
— a 6 dB resistive pad, an RC low-pass. Preflight requires RETURN inside a
**6 dB-wide window** (`VALIDATION_TARGET_LEVEL_MIN/MAX_DBFS` = −12 … −6 dBFS) and
a 40 dB gate gap. Gating tests 3/4 on those criteria would fail the fixture *for
working correctly*.

So `validation_preflightGate(bool return_is_attenuated)` takes the fixture into
account: `false` for preflight/1/2 (full check, identical to `v`), `true` for 3/4
(SOURCE-side criteria only, and it prints that it is doing so). The failure the
item actually names — a dead SOURCE producing a NaN table instead of a clear
preflight failure — is caught either way. Criteria are looked up **by name**, not
array index, so a rename inside the preflight fails loudly instead of silently
gating on the wrong criterion.

### Compile evidence, and a false alarm worth recording

Teensy 4.1, `teensy:avr:teensy41`, clean build, no errors and no new warnings:

| | FLASH code | FLASH data | RAM1 vars |
|---|---|---|---|
| Baseline `f1b13ed` | 156 608 | 72 200 | 218 080 |
| All three firmware commits | 157 248 | 73 224 | 219 104 |

The baseline **reproduces journal (5)'s recorded numbers exactly**, which is what
establishes that the same starting tree was rebuilt.

**The size summary was byte-identical between the TODO-48-only build and the
full build** — the same stale-cache signature journal (5) warned about. It was a
false alarm, and it was checked the way that entry says to rather than by trusting
the numbers: the `.elf` md5s differ, `audioEngine_setRouteDescription(char const*)`
is in the symbol table, and searching the binaries for the IEEE-754 bytes of the
timing constant finds **4 occurrences of 46.44 ms and zero of 92.88 ms** in the
full build, and the reverse in baseline. `b2cdb4f` was also rebuilt standalone,
because it was staged from a split patch and a split patch can leave an
inconsistent tree.

### A correction found while writing the runbook pass — in my own edit

The first draft of the Phase 4 step 6 correction replaced `45a` with **`41a`**.
`docs/asbuilt/netlist.md` records **col 41 A–E as `OPA_BIAS`** (0.874 V `MEAS`,
bridged to col 43). **That is the same "it looks free" reasoning the correction
exists to stop**, committed while correcting it.

The published text therefore **names no replacement column at all.** It lists
which nearby columns are taken (41/43 = `OPA_BIAS`, 45 = VGND, 48 = `SOURCE_NODE`),
says to verify the pick is dead first, and adds *"do not trust a document that
calls a column free, **including this one**."*

### 🔑 A runbook defect is not closed when ONE occurrence is corrected

**This is the most transferable thing this session produced, and it was found by
closing TODO-31 rather than by the correction pass itself.**

`b6db3d6` corrected C1-01 — the Phase 0 step 5 instruction that bridges the red
rails which Phase 1 step 7 then re-purposes as VGND — in the **numbered step** and
in the **end-of-phase verify row**. Closing TODO-31 required auditing for *other*
rail re-purposings, and that audit found the same obsolete instruction still alive
in two more places:

- the **step-5 SVG diagram** — titled *"bridge the rails"*, drawing two red bridge
  paths, captioned *"two bridges at left, two at right"*
- the **Background paragraph** — *"we bridge the top rails to the bottom rails for
  redundancy. Two bridges per side…"*

**A reader who followed the picture, or who read the explanation to understand
why, would have walked straight back into the destructive version** — from a
document whose numbered step had just been corrected. That is arguably worse than
an uncorrected document, because the corrected step lends the stale ones credibility.

> **The rule, stated generally:**
> **A runbook defect is not closed when one occurrence is corrected. All
> representations of the affected instruction — the procedure, the verification
> table, the explanatory prose, and the diagrams — must be audited for the same
> assumption.**
>
> These are four *independent encodings of one fact*. Each can reintroduce the
> defect on its own, and prose and diagrams are the ones that get skipped, because
> correcting "the instruction" feels complete once the numbered step is right.

**Both remaining sites are now corrected**, the diagram carries an explicit warning
line, and Appendix C.1's C1-01 row records that the defect spanned **four** sites.
The audit found **no other rail re-purposing** in the document: `BOT_RED` → VGND in
Phase 1 step 7 is the only one.

**This was deliberately NOT folded back into `b6db3d6` by amending it.** The
history is more useful showing *correction → independent audit → discovery that the
correction was incomplete → follow-up* than showing a first pass that was
magically complete. The miss is the lesson.

### The v3.0 PDF was removed, not regenerated

`docs/breadboard_bringup_v3.pdf` was a legible 37-page pandoc/LaTeX rendering
(`xdvipdfmx`, created 2026-06-02) carrying **every corrected defect verbatim** —
the red-rail bridge, `45a` → pin 14, the E–B–C pin order, columns 60–70 — plus
the **pre-2026-09-17 inverted coil polarity** (its step 9 still reads *"Wire
COIL (+) → +5V rail. Jumper from `55f` (pin 10)"*).

**Not regenerated:** no `pandoc`, no TeX distribution, no alternative renderer on
this machine, and the original embeds 26 images, so the pipeline had an SVG
conversion stage that cannot be reconstructed from the artifact. Improvising a
different renderer would have produced something nobody could vouch for.
**Removed instead; the bytes remain in history at `64894d4`.** The Markdown is now
the only copy.

### ⚠️ Phase 9 is NOT unblocked by this session

**TODO-48's firmware defects being closed does not mean validation can run.** The
harness compiling correctly was one gate of several, and the others are untouched:

- **TODO-53 — open.** The board is running the temporary `q` build (boot stamp
  `Sep 19 2026 22:20:52`, md5 `a07722c6e6f5bb64f27b1719a7aa1b95`), **not any
  commit.** Results captured on an unidentified binary are not sign-off evidence;
  the flash-identity incident in journal (6) is exactly why.
- **TODO-52 — open.** Test 1's Y-split joins Instrument In and Rig Send, and the
  Rig Send tip's feed count is still `RPT`, not `MEAS`. This is the node the test
  fixture attaches to.
- **Fixture and stimulus not confirmed present** — tests 3 and 4 need a 6 dB
  resistive pad and an RC low-pass, and every test needs an **external** broadband
  source.

### 🔒 Phase 9 is external-stimulus work, and the firmware enforces it

Recorded because the internal generator will look like a shortcut, and the reason
it is not one is stronger than "we decided against it":

1. **`validation.cpp` never touches the generator.** Its prompts call for pink or
   white noise *"from signal generator or DAW"*. There is no code path from the
   suite to `signalGen_*`.
2. **`OBS/CODE`: DUT injection is NOT IMPLEMENTED in the active build.** The
   architectural comments in `signal_generator.cpp` and `audio_capture.cpp`
   describe an intended path — generator → send mixer → I2S out L → relay → Rig
   Send. **Those comments are not evidence of a callable implementation, and under
   this file's source-precedence rule the active call path wins over them.**
   `ENABLE_DUT_INJECTION` is **0** (`config.h:308`), and all three
   `audioCap_setInjectionMode()` calls sit inside `#if ENABLE_DUT_INJECTION`.
   **`audioCap_setInjectionMode()` is not defined in `audio_capture.cpp` or `.h`
   at all** — it exists only in the staging header `audiocap_injection_api.h`.
   **Setting the flag to 1 would fail to LINK, not silently enable injection.**
   `signalRouter_setInjectionEnabled()` still has **zero callers**.
3. **TODO-42 would contaminate the control channel anyway** —
   `signal_generator.cpp:99` sums the generator into `s_mixer_ret` slot 2, which
   feeds the RETURN analysis taps.

**So the validation procedure's external-stimulus scope is not merely a
convention to be relaxed — it matches what the firmware can actually do.**

> **Worth stating as its own precedence case:** an earlier working assumption in
> this session was that the firmware *does* contain a generator-to-Rig-Send
> injection route, on the strength of those architectural comments. **The
> active-tree trace refuted it.** This is the 2026-08-25 rule applied to a comment
> rather than to a contract document or a patch file: *never infer "implemented"
> from something that describes the design — verify the call path.* The comments
> are accurate about **intent** and stale about **state**.

> **⚠️ Side finding, not fixed here (records-only pass).** The in-code note at
> `measurement_engine.cpp:1108–1113` says the generator's output *"is NOT yet
> connected to the audio graph."* **That is stale** — `signal_generator.cpp:99`
> connects it to `s_mixer_ret`. The note is what TODO-42 exists to correct; it is
> recorded there rather than edited here. Mitigating: `m` uses
> `measureParams_rigAnalysis()`, whose `stimulus` is **`EXTERNAL`**
> (`measurement_engine.cpp:1302`), so the generator is not started on that path
> and the contamination is **not live today**. `measureParams_cableCapacitance()`
> requests `INTERNAL_WHITE` and is **not reachable from any serial command**.

### Open, deliberately not decided here

**The `q`-toggle worktree still exists**, uncommitted, one modified file
(`guitar_rig_analyzer.ino`), on branch `firmware/todo-51-send-relay-toggle` at a
session scratchpad path under `wt2/`. **It survived only because its session
happened not to be cleaned up** — the same exposure that destroyed
`firmware/bench-safe-todos`.

**Its disposition is left as a separate decision and was deliberately not folded
into this session's commits.** An uncommitted diagnostic build should not become
permanent firmware merely by surviving in a temp directory. TODO-53 owns the
question of who really owns the send path; **`q` is live and can reach an
output-contention state while TODO-52 is open.**

**Next:** reconcile nothing further in code. The next milestone is bench evidence
— TODO-52's lifted-wire measurement, then a known-build reflash (TODO-53), and
only then Phase 9.

---

## 2026-09-19 (8) — Bypass jumper removed and the send path now runs through the relay; loopback unchanged. **The isolation check taken does not discriminate the two-feed condition — TODO-52 stays open**

### Corrective action and result

The old direct `col 48` → Rig Send TIP jumper was **removed**, forcing Rig Send through the relay NC/COM path. Powered loopback afterwards, pin 14 LOW:

| | Value |
|---|---|
| SOURCE / RETURN | **−28.9 / −28.9 dBFS** |
| 1 kHz | **−0.0 dB** |
| Clamped bins | **0 of 512** |
| Route | `XLR return, no injection` |
| Raw SOURCE vs RETURN | essentially identical |

Claimed chain: `SOURCE_NODE`/`48e` → `56a` NC → `57a` COM → Rig Send → external loop → XLR Return → `RETURN_NODE`. **Removing the bypass did not measurably change loopback behaviour**, which is the expected outcome and a good sign.

### ✅ What the power-off check does establish

`58a` → `48d`/SOURCE_NODE = **OPEN**, power off, relay LOW. **This rules out a stray LINE-OUT-L-to-SOURCE_NODE path** — a misplaced jumper, a solder bridge, an unintended tie. That is exactly the framing the check was proposed under, and it holds. Worth having.

### 🔻 What it does NOT establish — recorded before it hardens into a closure

**With the relay de-energised, COM↔NO is open by the relay itself.** `58a` therefore reads OPEN to `48d` **whether or not the direct tip jumper exists**, because the only route between them passes through that open NO contact.

- *Jumper present*: tip↔col 48 direct, tip↔COM, COM↔NC closed, **COM↔NO open** ⇒ `58a`↔`48d` **OPEN**.
- *Jumper absent*: **COM↔NO open** ⇒ `58a`↔`48d` **OPEN**.

Identical reading under both wirings. **It cannot distinguish them.** The jumper removal is **builder-reported (`RPT`)** and very likely correct — but "removed" and "verified removed" are different claims, and this project's own tier discipline exists because that distinction has cost it time before.

**Also not evidence:** the −28.3 → **−28.9 dBFS** shift. Two identical parallel connections to one node are electrically near-indistinguishable from one (a relay contact adds ~tens of mΩ), so removing a redundant jumper should produce **no** measurable level change. The 0.6 dB is more consistent with source drift. **Do not cite it in either direction.**

### The one decisive test left (power off, one wire lifted)

No power-off measurement can separate the two wirings while COM↔NC is closed, because every point on col 48 then reaches the tip *through the relay*. The parallel path is masked by design. So either lift a wire, or count conductors:

1. Power **OFF**.
2. Lift the **COM→tip wire at `57a`** (one end, temporarily).
3. Measure **Rig Send TIP → `48d`**. **OPEN ⇒ COM is the tip's only feed, TODO-52 closes as `MEAS`. BEEP ⇒ a second feed remains** and the HIGH-state loop is live.
4. While lifted, TIP → `56a` and TIP → `58a` should also both read OPEN; a beep there locates the stray path directly.
5. Reconnect `57a` → tip and re-verify before powering up.

Purely visual alternative: **count the conductors on the Rig Send tip lug.** One is the answer.

**Position unchanged: do not press `q`, do not drive pin 14 HIGH, until this reads clean.** Pin 14 is LOW, which remains the safe side.

## 2026-09-19 (7) — Send-relay signal path wired and continuity-verified; TODO-51 closes on its stated criterion. **Open hazard: Rig Send tip may have two feeds**

### Reported as-built (`MEAS`, continuity-verified; three intended Phase 7 jumpers installed)

| Contact | Connects to | Role |
|---|---|---|
| `56a` **NC** | `48e` / buffer output | LOW / default: external source → Rig Send |
| `57a` **COM** | Rig Send jack tip | switched output to the rig |
| `58a` **NO** | Audio Shield **LINE OUT L** | HIGH: codec monitor path → Rig Send |

This matches the runbook's v3 Phase 7 SPDT-selector topology (COM = Rig Send, NC = buffer, NO = codec line-out). **Observed:** LOW delivers the external ~1 kHz source to Rig Send; HIGH delivers the LINE OUT L monitor-path signal. SOURCE/XLR measurement remained healthy at **−28.3 / −28.3 dBFS, −0.0 dB @ 1 kHz**. Pin 14 left **LOW** (safe/default). `injection_active` stayed **false** and `ENABLE_DUT_INJECTION` is still `0` — **no claim of DUT injection is made or implied.**

### ⚠️ Open hazard — NOT resolved, do not energise pin 14 until it is

`docs/asbuilt/netlist.md` §SOURCE_NODE records **column 48 rows A–E as a single node** (C2− at `48d`, jumper `48e` → LINE-IN-L, J2 open stub at `48a`). So **`48d` and `48e` are the same electrical point.**

The as-built recorded up to journal (5) had **Rig Send tip → `48d` directly**. The relay path now added is `48e` → NC → COM → **Rig Send tip**. **If that original direct jumper was not removed, the Rig Send tip has two feeds**, and in the **HIGH** state the codec's LINE OUT L driver is connected straight onto SOURCE_NODE — i.e. onto the OPA1642 buffer output through C2. That is precisely the fault the runbook's own v3 critical fix was written to prevent: *"COM↔NO connects the buffer output directly to the codec's line-out driver (two outputs fighting on one node)."*

**The LOW-state observation cannot discriminate between the two wirings** — both feeds carry the same signal in LOW, so "LOW delivers the source" is true either way. **Whether the direct jumper was removed was never reported, and must not be assumed in either direction.**

**Cheapest decisive check (power off):** count the conductors on the Rig Send tip lug — two means a second path. To confirm, lift the COM→tip wire at `57a` and re-check tip ↔ column 48; a beep with COM lifted proves a second feed. **Do not test this by energising to HIGH** — that is the hazard state.

Recorded as **TODO-52**. Pin 14 is currently LOW, which is the safe side of it.

### Status accounting against TODO-51's actual wording

TODO-51's Proof line reads: *"pin 14 observably driven HIGH and LOW from an operator command, with the RELAY_SEND contacts measured transferring (`MEAS`) — and, separately, a documented decision on whether those contacts are wired into the signal path at all."* Both clauses are now satisfied, so it moves 🟢.

**Explicitly NOT part of that criterion**, and therefore not blocking it — recorded separately so neither is silently dropped:
- **POLE 2** (`58f`/`57f`/`56f`) remains datasheet-level and untested. That caveat belongs to Phase 6 / TODO-6, not to TODO-51.
- **Cleanup of the temporary `q` firmware** → now **TODO-53**.

### ⚠️ What is actually on the board right now

**The Teensy is running the TEST build, not `f1b13ed`** — boot stamp `Sep 19 2026 22:20:52`, md5 `a07722c6e6f5bb64f27b1719a7aa1b95`. It contains the `q` toggle and the bring-up boot banner.

**This now matters more than it did when the toggle was written.** When `56a`/`57a`/`58a` were unwired, a stray `q` was electrically inert. **With the three jumpers fitted, `q` routes a real signal** — and, if the hazard above is real, into an output-contention condition. Anyone using this board should know `q` is live.

## 2026-09-19 (6) — ✅ **PIN 14 → SEND-RELAY CONTACT TRANSFER BENCH-PROVEN END TO END.** Also: an upload that appeared to succeed while the board kept running the old binary — caught only because a help menu was one line short

### The flash-identity incident (read this first — it is the transferable lesson)

Before any relay result was trusted, three successive attempts to run a test build left the board still running the **old** firmware. The only reason this was caught: the `q` command printed `Unknown command: 'q'.` and **the help menu ended one line early.** Had the change been silent — a threshold, a constant, a gain — it would have looked like a hardware result.

**What made it detectable in the end:** a deliberate, unmissable build identifier printed at boot, *before* the version banner and *before* `presentation_init()` (the Phase 2 lesson from journal 2026-09-01: a block placed after display init was never reached on this bench):

```
########################################################
[BringUp] SEND RELAY TEST BUILD
[BringUp] Build stamp: Sep 19 2026 22:20:52
```

`__DATE__`/`__TIME__` make every compile uniquely identifiable, so "which binary is on the chip" stops being an inference.

**Verification discipline used on the artifact itself:** the Intel HEX was **decoded** and searched for the new strings, rather than trusting `arduino-cli`'s size summary — which had earlier reported **byte-identical** figures across two genuinely different builds (journal (5)). Decoded image 238 592 bytes; `SEND RELAY TEST BUILD`, `Build stamp`, `q=RELAY_SEND pin14 toggle` all PRESENT. The hex was then copied to `~/Desktop/sendrelay_test_Sep19_2220.hex`, md5 **`a07722c6e6f5bb64f27b1719a7aa1b95`**, and the copy re-verified independently.

**⚠️ The root cause of the failed uploads was NEVER established — do not record one.** Contributing facts that *are* known: the Teensy platform's upload recipe is `teensy_post_compile ... -path={build.path} ... -reboot`, which hands off to the **`teensy.app` GUI loader** and depends on `-reboot` soft-resetting into HalfKay; `--input-dir` may therefore never have reached it; and this project has already recorded one upload that wrote nothing because "HalfKay never got a manual reset to enter program mode" (journal 2026-09-01). **Which of these applied here is unproven, and the successful flash path was not reported back.** If it recurs, capture the upload command's full stdout/stderr first — that artifact was requested and never obtained, and reasoning proceeded twice without it.

**Standing recommendation:** keep a build stamp in the boot banner **permanently**, not just for bring-up builds. The cost is two lines; the failure it prevents is attributing a stale binary's behaviour to hardware.

### The measurement (`MEAS`, DMM continuity, nothing rewired between states)

Driven by the temporary `q` toggle, which writes `RELAY_SEND_PIN` directly and deliberately does **not** touch injection state:

| Pin 14 | `56a` ↔ `57a` | `57a` ↔ `58a` | `56a` ↔ `58a` |
|---|---|---|---|
| **LOW** (~0 V) | **CLOSED** | OPEN | **OPEN** |
| **HIGH** (3.259 V) | OPEN | **CLOSED** | **OPEN** |

**Therefore, by state rather than by datasheet:** `57a` = **COM**, `56a` = the de-energised contact (**NC**), `58a` = the energised contact (**NO**).

**The full physical chain is proven, not merely firmware intent:**
`q` → GPIO 14 changes 0 V ↔ 3.259 V → coil energises → contacts transfer `57a` from `56a` to `58a`.

**Two things this measurement got right that are worth keeping as habit:**
1. **`56a` ↔ `58a` was checked in BOTH states and read OPEN both times.** That rules out NC and NO being bridged — a make-before-break or welded-contact fault would have shown here. Most contact checks omit this and would not have caught it.
2. **`injection_active` remained `false` throughout**, printed by the toggle itself. So none of this evidence depends on the unresolved injection path, and **TODO-42 is not implicated in it.**

### What this confirms, and what it does not

**Confirms:** the runbook's Phase 6 POLE 1 contact table (pin 2 = NC → `56a`, pin 3 = COM → `57a`, pin 4 = NO → `58a`). TODO-45 had only been able to say "no defect is established in the POLE 1 table" after withdrawing an unsound deduction on 2026-09-15. **It is now positively bench-proven, not merely un-refuted.** That is a stronger claim and should replace the weaker one.

**Does NOT establish:**
1. **What `56a` / `57a` / `58a` are connected to.** Nothing about the signal path. This is the correct next question and it must be answered *before* any audio behaviour through this relay is interpreted — `docs/asbuilt/netlist.md` still has no entry for these three columns.
2. **Anything about injection.** The toggle proves the relay. It must not be cited as injection evidence.
3. **POLE 2** (pins 7/8/9 → `58f`/`57f`/`56f`) — still datasheet-level only, untested. Same caveat already carried for relay #2's pole 2.

### Firmware status

The `q` toggle and the boot identifier are **temporary** and live only on branch `firmware/todo-51-send-relay-toggle` (one file, additive). They must be removed when the send path gets a real owner. Main tree remains clean at `f1b13ed`.

## 2026-09-19 (5) — ✅ **XLR RETURN PATH BENCH-VALIDATED WITH A REAL SIGNAL.** Stimulus-present TS/XLR A/B completed with both return sources live. Send-side relay found **unreachable from the running firmware** — code-derived, before any bench time was spent on it

### The test that was finally possible

The blocker on both Phase 7 sign-off and Phase 8 was the same one: every previous TS/XLR A/B had been run on the **noise floor**, because only one return source ever carried signal. Selecting XLR just disconnected a live TS return and selected an undriven pin 2, which proves relay isolation and nothing about XLR signal transfer.

The fix was to feed the **same** `SOURCE_NODE` stimulus to both return sources at once, with the XLR branch entering through the **physical connector** rather than a jumper to `17a` — specifically so Phase 8's evidence would be end-to-end and not bypass the thing under test.

**As-built for this session — XLR feed via a seated adapter:**

| Adapter terminal | Lands on | Tier |
|---|---|---|
| GND (pin 1) | **Audio Shield GND** | `MEAS` (continuity, power off) |
| L (pin 2) | `48d` / `SOURCE_NODE` | `MEAS` (continuity, power off) |
| R (pin 3) | top breadboard GND rail | `PHYS` |
| `48d` → GND | **no continuity** (not shorted) | `MEAS` |

### Results (`OBS`, power on, 1 kHz stimulus present throughout)

| Router state | Pin 15 | Condition | RETURN | Other |
|---|---|---|---|---|
| **TS** | ≈ 0 V | TS loop connected | **−28.3 dBFS** | — |
| **TS** | ≈ 0 V | TS loop **disconnected** | **≈ −68 dBFS** | isolation confirmed |
| **XLR** | **3.259 V** | XLR signal present | **−28.3 dBFS** | 1 kHz transfer **−0.0 dB**; raw SOURCE/RETURN essentially identical; Serial reports XLR return, no injection |

**This is the stimulus-present A/B that Phase 7 was missing**, and the first real analog signal to reach `RETURN_NODE` through the physical XLR connector. It directly confirms the documented relay convention: **LOW = TS, HIGH = XLR.**

### Bounds — what this does NOT establish

1. **−0.0 dB at 1 kHz is a loop observation, not a calibrated figure.** Same bound as journal (4). The calibrated path is TODO-9 Test 1 with its fixture, and it remains unrun.
2. **The XLR branch is a direct adapter jumper from `SOURCE_NODE` to pin 2.** So "XLR signal present" is true **by construction**. What is proven is the **connector contact + relay transfer + codec input** — not a rig loop, and not anything about what a real XLR source would do.
3. **The noise-floor comparison in TODO-8's criterion is NOT satisfied.** A TS-selected, cable-disconnected floor (≈ −68 dBFS) was captured; **an XLR-selected floor was not.** One number is not a comparison.
4. **⚠️ The grounding topology CHANGED for this test, and that matters for exactly the risk TODO-8 flagged.** The original as-built had XLR pins 1 **and** 3 on the breadboard rail. The adapter now ties pin 1 to **Audio Shield GND** while pin 3 stays on the breadboard rail. The 33.1 dB measurement of 2026-09-12 (3) came from precisely this shield-vs-breadboard distinction. **Any future noise-floor comparison must state which of the two topologies was in place** — the risk TODO-8 describes is no longer the configuration on the bench.
5. **Pin 15 = 3.259 V is a driver-state reading, not contact proof.** Contact transfer is proven by the RETURN reading, which is present. Both exist here; keep them as separate claims.

### Send-side relay: stopped before the bench, on code evidence

The stated next step was to test the send-side relay "the same way." **It is not currently testable that way, and the reason is in the firmware, not the hardware.** Established by reading the active tree at `f1b13ed`:

1. **`signalRouter_setInjectionEnabled()` has zero callers.** Only its definition (`signal_router.cpp:331`), its declaration (`signal_router.h:235`), and references in `signal_router_contract.md` / the runbook. The contract's step 6 — `measurement_engine` calling it at CAPTURE entry/exit — was never done (TODO-11). The Phase 6 `p`/`P` toggle was removed per the runbook's own step 13. `i` is `insightsEngine_printToSerial()`. **Nothing in the running firmware can drive pin 14 HIGH.**
2. **It is gated even if reached.** It rejects unless `s_jack_rig_send.debounced` is true (pin 17), and `config.h:279` still carries `JACK_RIG_SEND_DETECT_INVERTED 0 // Phase 7 — not built, sense unverified`.
3. **Injection is compiled out.** `ENABLE_DUT_INJECTION 0` (`config.h:308`) removes the `audioCap_setInjectionMode(true)` call, so the relay would move while the codec output mixer never switches to the generator.
4. **The contacts do not appear to be in the signal path.** The as-built has Rig Send tip → `48d` **directly**, and `docs/asbuilt/netlist.md` contains **no entry for `56a` / `57a` / `58a`** (the Phase 6 contact columns). *This is a documentation absence, not a bench observation* — it needs confirming against the board, but if correct, toggling RELAY_SEND would have nothing downstream to observe.

**Why the return-side method does not transfer:** it worked because RELAY_RETURN's contacts are wired into the return path **and** `j`/`k` are bound to `signalRouter_setReturnSource()`. Neither condition holds on the send side.

**Recorded as TODO-51.** The relevant point for the next session: this was caught by reading the tree *before* bench time was spent, which is the check that journal 2026-08-25 (2) was written to enforce.

### Firmware and runbook work done in parallel (compile-verified, NOT bench-verified)

Done on branch `firmware/bench-safe-todos` in a **separate git worktree**, deliberately so the main tree stayed clean at `f1b13ed` and could not be flashed with unproven code mid-session. **Nothing here has been on the board.**

- **TODO-48** — `validation_waitForUser()` returned `void` and read-and-discarded every byte, which is exactly why a cancel keystroke could not be distinguished from consent. Now captures the first byte and returns `bool`. Added `validation_preflightGate()` so the `1`–`4` single-test commands run the same level check that only `v` ran. `runAll()` aborts on decline. *(Consent accepts `y` as well as CR/LF: a monitor set to "No Line Ending" sends nothing on Enter, and strict CR/LF-only would hang the prompt with no exit.)*
- **TODO-50** — added `audioEngine_setRouteDescription()`, a description-only setter (no mixer gains, no smoothing reset, no `ROUTE_CHANGED`), called from `signalRouter_init()`. **ADR-004 Decision 2 is preserved** — boot is still not a route-change transition. Verified `signalRouter_init()` (`.ino:327`) runs after `audioEngine_init()` (`.ino:257`), so the sync is not overwritten.
- **TODO-27** — `EXPECTED_BLOCK_MS` now uses the hop size (`FFT_SIZE / 2`), giving 46.4 ms against the measured 46.3 ms instead of a permanent phantom −46.6 ms anomaly.
- **Runbook v3.1 correction pass** — eleven defects, tabulated in a new Appendix C.1: the Phase 0→1 sequence that shorts +5 V to VGND (TODO-31), Phase 4's missing USB reconnect (TODO-18), the swapped transistor pin order and the `45a`-on-the-VGND-rail base drive (TODO-45), Phase 7's impossible "columns 60–70", the unenforced parts gate, the `p`/`P` toggle contradiction, and three stale sign-off lines (TODO-3 / TODO-5 / TODO-8). Added a **"Board coordinates"** authority section, which the document had never had — the absence is how three separate phases came to claim column 45 and a column 70 that does not exist.

**Compile evidence (Teensy 4.1, clean build):** FLASH code 156 608 → 156 864, data 72 200 → 73 224; RAM1 variables 218 080 → 219 104. No errors, no warnings. `arduino-cli`'s size summary was byte-identical across two builds, which looked like a stale cache — **inclusion was confirmed by string-matching the linked `.elf` instead**, not by trusting the reported numbers.

**Nothing is committed.** Review with `git diff main firmware/bench-safe-todos`.

## 2026-09-19 (4) — ✅ **FIRST VALID TRANSFER FUNCTION THROUGH THE INTENDED CHAIN.** Rig Send jack built; real guitar signal ran Instrument In → buffer → Rig Send → cable → Rig Return TS → relay → RETURN_NODE, TF confidence 15 % (> 10 % threshold)

### Rig Send jack — install and pre-power checks

The third Switchcraft #11 is in, completing the three-jack architecture the record had been describing conceptually since Phase 5 (journal 2026-09-19 (2) corrected the belief that it already existed).

| Check | Result | Tier |
|---|---|---|
| TIP → `SOURCE_NODE` | continuity | `MEAS` |
| Sleeve → **Audio Shield GND** | continuity | `MEAS` |
| TIP → sleeve, powered off | ~0 Ω → 50 MΩ over ~15 s → **OL** | `MEAS` |
| `48e` → LINE-IN-L permanent tap | **preserved** | `PHYS` |

**On the TIP→sleeve reading: record only what it proves — no stable low-resistance TIP-to-sleeve short after installation.** The rising trace is charging behaviour; which capacitance dominates was not determined and does not need to be.

**Note the grounding contrast, deliberately:** Rig Send's sleeve went to **Audio Shield GND**, matching the 2026-09-12 (3) lesson. The Phase 8 XLR's pins 1/3 went to the **breadboard** rail. Both are recorded as built; the XLR one remains the flagged signal-quality risk (TODO-8), and this send-side choice is the one that agrees with the 33.1 dB evidence.

### Boot with nothing connected — no disturbance to SOURCE

`SOURCE_NODE −63.5 dBFS · RETURN_NODE −63.9 dBFS · TF confidence 0 % · acquisition normal` (`MEAS`, one cycle).

**Nothing indicates the parallel Rig Send branch disturbed SOURCE acquisition.** That is all it shows. **It is not a noise-floor figure** — one cycle, no stimulus, and not comparable to the −57…−60 dBFS readings of earlier sessions, which had different cabling.

### ✅ The result: first valid TF through the intended architecture

With a real guitar at Instrument In and the TS loop in place (`MEAS`):

| Quantity | Observed |
|---|---|
| SOURCE peak | **−10.1 dBFS** |
| RETURN peak | **−10.2 dBFS** |
| **TF confidence** | **15 %** (threshold 10 %) |
| 120 Hz / 500 Hz / 1 kHz | **−0.0 dB** each |
| 5 kHz / 10 kHz | `---` |
| Raw samples | SOURCE and RETURN track sample-for-sample (e.g. −1710/−1706, −1518/−1517, +432/+427) |

**Chain exercised:** Instrument In → buffer → SOURCE_NODE → Rig Send → external TS cable → Rig Return TS → RELAY_RETURN NC → COM → LINE IN R → RETURN_NODE.

**This is the first time a deliberate signal has travelled the intended path and the measurement engine has produced a valid estimate from it.** Every earlier correlation was a noise floor through an improvised path.

**Bounds — none of this is a specification:**
- **`---` at 5 kHz and 10 kHz is not evidence of roll-off.** This strum simply produced no qualifying data in those spot-check bins. Do not infer high-frequency response from it.
- **−0.0 dB at three bins is a cable loop, not a calibrated result.** Unity through a short cable is the expected sanity outcome, not a validated flat response. The formal proof is TODO-9's Test 1 with its specified fixture.
- **15 % confidence is barely over the threshold**, from a decaying, non-stationary guitar strum. It demonstrates validity, not quality.
- **No A/B was run with the stimulus present.** The strongest closure evidence would be: play, select XLR, watch RETURN collapse, select TS, watch it return. That has been done on the noise floor only.

### 🐞 Separate defect observed, not part of the signal result: stale route description at boot

`[Main] Route: Default bench: SOURCE_NODE=L, RETURN_NODE=R` — during an otherwise valid measurement, **on a board whose router is in TS.**

**Cause, and it is ADR-004 working as designed:** `signalRouter_init()` deliberately does not call `audioEngine_setRoute()`, because boot is not a route-change transition (ADR-004 Decision 2, and the "no transition at boot" property that makes TS-at-boot clean). So `audio_engine` keeps the description set in its own `init()` until the first `j`/`k`.

**Consequence:** the `[Main] Route:` diagnostic — and the same string in any Pi UI packet — **misreports the route until the first selection change.** The authoritative state is the router's; this is presentation state, and it is stale, not wrong at the hardware level.

**Deliberately not "fixed" by sending `j` before this test**, which would have added an unnecessary state transition to the first clean post-boot loopback. Recorded as **TODO-50**.

### Where this leaves the phases

**Phase 7's return path is now demonstrated end-to-end with a real signal.** Remaining before sign-off: the stimulus-present A/B above, and a decision on whether anything else in TODO-7's checklist is outstanding. **Phase 8 still owes a real signal through the XLR path plus the noise-floor comparison against TS** — today's guitar never went through XLR.

---

## 2026-09-19 (3) — ✅ PHASE 8 XLR RETURN PATH BUILT AND CONTACT-PROVEN (A→B→A from the connector to LINE IN R). Detect switch intentionally omitted under ADR-004. **Contact-path proof only — no analog signal has been through it**

### As-built

| Item | As built | Tier |
|---|---|---|
| XLR **pin 2** (hot) | → pigtail → **`17a`** = relay #2 pole-1 **NO** | `PHYS` (builder read the hole) |
| XLR **pin 1** (shield) | → **top breadboard GND rail** | `PHYS` |
| XLR **pin 3** (cold) | → **top breadboard GND rail** | `PHYS` |
| Other connector contacts | **none wired** — no undocumented second path into `17a` | `PHYS` |
| D2F-01L detect microswitch | **intentionally NOT built** (ADR-004: detection is not load-bearing for routing) | decision |
| Connector part identity | intended Neutrik **NC3FAH2-0** per runbook; **marking not read back** | `NYV` |

### Passive checks, POWER OFF

| Measurement | Result |
|---|---|
| pin 2 → pin 1 | **OL** |
| pin 2 → pin 3 | **OL** |
| pin 1 → pin 3 | **0.2 Ω** (both on the top GND rail, as intended) |
| pin 2 → top GND rail, **after** mechanically securing the connector | **OL** |

The last one is a **post-handling bridge check only.** Pin 1 is already on that rail at 0.2 Ω, so it repeats pin 2 → pin 1 plus one segment. It is not independent confirmation of isolation, and should not be counted as a second proof.

### Relay-controlled routing: A→B→A from the connector to the codec

Continuity, **XLR pin 2 → Audio Shield LINE IN R pad**, nothing rewired between states (`MEAS`):

| Relay state | Result |
|---|---|
| TS (resting) | **OPEN** |
| XLR (commanded) | **BEEP** |
| TS (restored) | **OPEN** |

**XLR pin 2 reaches LINE IN R only when XLR is selected.** This also re-proves relay transfer under command, witnessed this time from the far end of a different signal path than the 2026-09-19 (1) test used.

**It is contact-path proof, not signal-quality proof. No analog signal has travelled this path. Phase 8 is not signed off, and Phase 7 remains open** (no Rig Send jack, no real-stimulus end-to-end run).

### ⚠️ Known risk, recorded deliberately: the XLR signal reference is the breadboard rail

Pins 1 and 3 land on the **top breadboard GND rail** — option B of the three considered, not the shield ground. The precedent is journal **2026-09-12 (3)**: moving *only* the return reference from breadboard GND to shield GND improved SOURCE by **33.1 dB**. The XLR's reference is now the breadboard rail while the codec's is the shield.

**This is a signal-quality risk, not a wiring defect, and nothing should be rewired on the strength of it.** The test is specific: **when a real signal first goes down the XLR path, compare its noise floor against the TS path.** If the XLR floor is meaningfully worse, the ground reference is the first suspect and the fix is already documented.

Also noted: grounding pin 3 is standard for single-ended adaptation, but transformer-coupled or cross-coupled balanced outputs dislike a shorted cold. Low risk for guitar rigs; recorded rather than designed around.

### What Phase 8 still owes

A real signal through the XLR path with its noise floor compared against TS; the connector's marking read back (`NYV` above — TODO-47's lesson); and a decision on whether the informational detect is ever wanted (ADR-002 governs how, if so).

---

## 2026-09-19 (2) — 🔻 TOPOLOGY CORRECTION: there is no Rig Send jack. The loopback cable was tied to the **raw instrument input node**, not a buffered send. The relay A→B→A test still stands, and now has a mechanism

### The correction

**Only two Switchcraft #11s exist on the analyzer** (`PHYS`, builder): the Phase 5 jack and today's Phase 7 return jack. Sessions (this one included) had been reasoning with three conceptual jacks — Instrument In, Rig Send, Rig Return — as though each had hardware. **Runbook Phase 7 steps 9–10 build the Rig Send jack and they have not been done.**

What the temporary cable actually connected (`netlist.md:104,133`): J4's tip is **column 30 = `SOURCE_IN`**, the raw guitar input node *ahead* of the buffer, with C1 and the bias resistor on it. So the loop was:

`Instrument In tip (col 30, SOURCE_IN) → cable → Rig Return TS tip → RELAY_RETURN NC → COM → LINE IN R`

**Not** "Rig Send → Rig Return". Every statement from tonight that used that phrase should be read with this correction.

### The A→B→A relay test — evidence kept, claim bounded

Gap between SOURCE and RETURN peaks, nothing changed but the relay (`MEAS`, serial diagnostics):

| State | SOURCE − RETURN |
|---|---|
| TS | 0.0 · 0.0 · 0.3 dB |
| XLR | 4.7 · 4.2 · 4.6 dB |
| TS (restored) | 0.3 · **2.5** dB |

**The correction strengthens this rather than weakening it.** The correlation under TS now has an identified mechanism: LINE IN R was tied through the relay and cable to the same node feeding the buffer, so SOURCE (buffered) and RETURN (direct) watched one node by two routes. Selecting XLR breaks that tie and the correlation collapses.

**Bounds, stated plainly:** this is a drifting **noise floor**, not a stimulus. The 2.5 dB reading in the restored-TS cycle is a third of the way to the XLR value, and SOURCE itself moved 1.7 dB between cycles. **Directional evidence that the TS path conducts. Not a calibrated measurement, and not Phase 7 sign-off.**

**Residual correlation under XLR** (COM on an unterminated NO) is consistent with the crosstalk floor from LINE IN L that netlist finding **A2** measured at ≈ −56 dBFS. Both effects were present at once.

### Test 1 was run by accident — record as INVALID, not FAIL

An `x` intended as *cancel* was consumed as *consent* (see TODO-48) and Test 1 ran on a nonconforming fixture with no excitation. Result: TF NaN, flatness NaN, confidence 0.00, harness exited cleanly.

**Classification: INVALID TEST / WRONG FIXTURE / NO EXCITATION. It is not evidence against RETURN_NODE or the Phase 7 wiring.** With no drive on SOURCE, `S_xx ≈ 0`, so the transfer function is 0/0 — NaN is the arithmetically correct outcome, not a fault.

### LINE IN R coupling — resolved to `DERIV`

**`DERIV` — LINE IN R is AC-coupled.** Supported by PJRC documentation for the Rev C/D design (`DOC`) combined with identification of this shield as Rev D (`PHOTO`, with supporting Rev-D pin-set evidence). **The coupling capacitor on this individual shield has not been electrically measured.** A `PHYS` claim was proposed and withdrawn.

This closed the DC-into-the-codec worry. It did **not** close the other one: even through a coupling cap, hanging LINE IN R off `SOURCE_IN` puts an AC load on the raw guitar-input node and could alter the very signal being characterised. **That is why the cable was removed before any guitar went in**, rather than because anything failed.

### ⚠️ Unexplained bench readings — do not reuse as evidence

**`NYV` / anomalous bench measurement:** POWER-OFF resistance measurements reported ~14–23 Ω from `SOURCE_IN` to ground, while `SOURCE_IN` across C1 repeatedly measured ~77.4 kΩ. The observations were internally difficult to reconcile with the known topology. **No wiring defect was identified or corrected. Investigation intentionally deferred; do not use these resistance readings as evidence of a hardware fault or of a hardware pass.** (TODO-49.)

**Nothing tonight produced an observed functional failure of the Phase 7 return hardware.**

### Method note

This session drove the board directly over the serial MCP link: `j`/`k` commands and passive diagnostic capture. **Flash identity was established by help-list readback, never from the uploader's exit code** — the check that caught the pre-ADR-004 image two days ago. Power state, clicks, and meter readings stayed with the builder; a vanished USB device was explicitly **refused** as proof of power-off.

### Next

Phase 8 (XLR return). **Note before scoping it:** under ADR-004 the XLR *detect* is no longer load-bearing for routing — only the XLR **signal path to RELAY_RETURN NO (`17a`)** is required. TODO-8's "microswitch detect works end-to-end" criterion predates that decision and is flagged for revisit.

---

## 2026-09-19 (1) — ✅ PHASE 7 RELAY DRIVER + CONTACT TRANSFER BENCH-PROVEN, and ADR-004's `j`/`k` exercised on real hardware. **It did NOT work first try: the driver stalled in the active region, and the fix is not identified**

### The pass, after a cold restart with nothing touched

| Check | Observed | Tier |
|---|---|---|
| `k` → XLR | audible click; **coil 4.78 V** (≈26 mA, saturating) | `MEAS` via builder |
| XLR contacts | `16a` COM ↔ `17a` NO **closed**; `15a` NC ↔ `16a` COM **open** | `MEAS` via builder |
| TS resting contacts | COM ↔ NC **closed**; COM ↔ NO **open** | `MEAS` via builder |
| `j` → TS | clean audible release | `RPT` (audible) |
| Survives power-off → cold boot → XLR → TS | yes, hardware untouched | `MEAS`+`RPT` |

**Pole 1 of relay #2 (`15a` NC · `16a` COM · `17a` NO) is now bench-proven on this relay in both directions** — not inherited from relay #1. **Pole 2 remains datasheet-level.**

**Firmware, on hardware for the first time:** `j` took the no-op path (`Return source unchanged: TS (no route change)`, no relay write, no ROUTE_CHANGED). `k` ran the full chain — `Route change notified at block 90305` → `Route updated: XLR return, no injection` → `Return source changed: XLR` → `[Main] audioCap: ROUTE_CHANGED`. **The ADR-004 invalidation chain is now observed, not just traced.** Flash identity was proved by serial readback (`?` → help list carrying `j=return TS  k=return XLR`), never from the uploader's exit code.

### 🔻 The failure that came first, kept on the record

Before any probing or reseating, the driver **stalled in the active region under the relay load**: `8a` (collector) sat at **3.556 V** (and 3.733 V on an earlier attempt) instead of Phase 6's 129 mV, with the emitter at **291 mV** instead of ~0. The coil was passing roughly a third of its ~27 mA (`DERIV`, using relay #1's 183 Ω coil — **this coil's resistance was never measured**).

**Load-dependence was the tell:** the same transistor pulled the node near 0 V at ~5 mA and could not at ~27 mA. That is the signature of series resistance in the emitter path, not a logic or firmware fault.

**During probing and reseating something physically changed, and normal operation became repeatable. The specific bad connection was never identified.** So:

- **This is not a fixed defect. It is an unexplained recovery.** If it returns, suspect the same emitter path first: the adapter's emitter solder joint, the `9a` contact, the GND jumper.
- **"Continuity is clean" did not catch it.** A beeper tests at ~1 mA; a joint can pass that and still drop volts at 27 mA. Continuity proves a path exists, not that it is low-resistance **under load** — the same placement-vs-value split as the capacitor-value lesson.
- **The base-resistor drop (`12a`→`10a`) was queued but never recorded.** It would have separated "base drive collapsed" from "full drive, forced β ≈ 3". If the fault returns, take that reading **before** touching anything.

### Where TODO-7's ADR-004 acceptance now stands

Proven: boot comes up TS de-energised; `k` energises, raises ROUTE_CHANGED and changes the description; `j` reverses it; a power cycle returns to TS. **Not proven: a TS signal reaching line-in R** — the signal path is not wired. **Phase 7 is not signed off.**

### Still open

Which rail pair was probed (netlist **GAP-5**); the adapter row; **relay #2's marking still unread** (TODO-47's lesson); pole 2; whether the pulldown or firmware establishes pin 15 LOW during reset; and the unexplained recovery above.

**Next:** signal wiring, one connection at a time, traced from the as-built record and the contract rather than from memory (TODO-46 flagged this trace as still outstanding).

---

## 2026-09-17 (1) — 🔨 RELAY_RETURN driver #2 BUILT at cols 8–18 and measured de-energised at rest. 🛑 Then `j` came back **"Unknown command"**: the Teensy is running a build older than `3460080`. Compile ≠ flashed, caught at the bench

### What was built, and where

The runbook's "mirror at columns 60–70" is impossible: the BB830's main field is physically **columns 1–64** (`PHYS`, builder), hardware occupies ~30–60, and **1–29 is empty**. The driver was sited at **columns 8–18** by shifting the **Phase 6 as-built line left by 41 columns** — TODO-6's as-built record as the template, never the runbook:

`pin 15 → 12` · `1 kΩ 12→10` · **`C 8 · E 9 · B 10`** · `10 kΩ 10→GND` · `coil+ 14a → +5 V` · `coil− 14f → collector 8` · `1N4148 band 14a` · relay `14`–`18` · pole 1 `15a` NC / `16a` COM / `17a` NO.

**The transistor order is `C E B` left to right**, as measured on 2026-09-15 (2) — *not* the runbook's `E B C` silkscreen order. Build reported continuity-clean (`RPT`).

**Rails were proven before anything was placed** (`MEAS`, power off, continuity): both rails continuous `8`↔`18`, blue ↔ circuit GND, red ↔ **the +5 V node feeding the Phase 6 driver**. Forward-trace (TODO-46): nothing lands in 30–64, and col 45 (VGND, deviation D3) is untouched.

### The resting state is now evidence, not assumption

Powered, before any Serial command (`MEAS`): base `10a` → GND **1.7 mV** · Teensy pin 15 → GND **2.6 mV** · **`14f` → GND 4.98 V**, with `14a` on +5 V. Both coil ends sit at +5 V, so **≈0 V across the coil and the relay is de-energised** — the intended ADR-004 TS/default state.

**⚠️ What it does not prove: *why* pin 15 is LOW.** The 10 kΩ pulldown and `signalRouter_init()` both drive it there, **and the old build does the same**. ADR-004's claim that the *pulldown* guarantees TS at power-on is still unproven; it needs a reading taken during reset, before `setup()` reaches the router. Do not let "it was LOW at rest" stand in for that.

### 🛑 The flash mismatch

`j` returned `[Main] Unknown command: 'j'.`, and the help list ended at `r=reset EMA` with **no `j`/`k` line** (`MEAS`, serial readback). The local tree and `HEAD` **do** contain it (`guitar_rig_analyzer.ino:452`, committed in `3460080`). So **source ✅ / flashed ❌**: the board is running a build older than ADR-004.

**`k` was correctly not sent.** On the old build it is equally unknown, and no other command drives pin 15 — so nothing could have been learned, and the next thing typed should be a reflash.

**This is the third time this project has been saved by reading state back from the board instead of trusting a report** (see 2026-09-16 (3) item 3, which used the same unknown-command trick to prove which build was flashed). `3460080`'s own commit message says "compile-verified, NOT bench-verified" — this is what that boundary looks like when it bites. **Keep the help-list readback as the standard first check after any upload.**

### No new Phase 7 firmware

`j`/`k` **are** the Phase 7 relay control; nothing needs writing. **Do not add a `[PHASE7-TEMP]` pin-15 toggle.** `signal_router.cpp` owns pin 15, and a second writer would desynchronise the router's state from the hardware — exactly why `[PHASE6-TEMP]` was removed (2026-09-16 (2)).

### Next, one step at a time

1. Flash the current tree. 2. Confirm the help list shows `j=return TS  k=return XLR`. 3. Re-measure the resting state. 4. `j` → expect no change, `14f` stays ≈4.98 V. 5. `k` → expect pick-up, `14f` ≈0.13 V (Phase 6 read 129.1 mV), and `15a`/`16a`/`17a` continuity to transfer. 6. `j` again → releases. 7. Power-cycle → comes up TS, de-energised.

**Still open:** which rail pair was probed, top or bottom (it decides whether netlist **GAP-5** is closed); which row the MMBT3904 adapters sit in; relay #2's marking not yet read back (TODO-47's lesson: the part was assumed once already); pole 2 still datasheet-level. **Phase 7 is not signed off, and the signal path is not wired.**

---

## 2026-09-16 (5) — ✅ ADR-004 IMPLEMENTED IN FIRMWARE (`3460080`). **Compile-verified only: there is zero hardware evidence.** The ordering audit found two things worth more than the implementation: a latent injection hazard and a RAWDUMP conflict with measurement

### ⚠️ Evidence boundary. Read this first.

**ADR-004 is compile-verified, not hardware-verified.** What exists: the tree compiles for teensy41, `signalRouter_setReturnSource(ReturnSource)` is in the ELF (and absent from the baseline build), and a code-derived audit of route-change ordering. **What does NOT exist:** any evidence that pin 15 switches the Panasonic relay, that TS/XLR routing works electrically, or that the physical pulldown sets the intended power-on state. **Pin 15 has no driver.** The firmware has not been flashed. Those are Phase 7 bench evidence (TODO-7 proof), and **Phase 7 is not complete.**

### What landed

`e9ebd75` (docs/contract) → **`3460080`** (firmware), reviewed separately.
- `s_selected_return` is the only return-routing state: TS at boot; changed only by `signalRouter_setReturnSource()`. That rejects NONE, treats an unchanged selection as a no-op with no ROUTE_CHANGED, and otherwise does state → relay → `audioEngine_setRoute()` → status. It is not refused mid-measurement.
- Jack inputs stay informational. `update()` returns only NONE or JACK_CHANGED.
- `ReturnPreference`, `setReturnPreference()` and `computeReturnSource()` are removed. Keeping a function called *compute* when there is nothing to compute would have been a fossil of the auto-detect design.
- `NONE = 0` and `ROUTE_INVALID` are kept for protocol v2 compatibility; neither is produced.
- Serial: `j` = TS, `k` = XLR, direct selection and not a toggle, because the operator must be able to predict the result without knowing the prior state.

### The ordering audit: PROVEN SAFE for reachable paths, and why "same loop iteration" was the wrong argument

The question was: **can post-switch audio be accepted into an in-progress measurement before ROUTE_CHANGED aborts it?** The answer is no, for two reasons that have nothing to do with loop iterations:
1. `audioCap_notifyRouteChanged()` resets the level accumulator, and `audioCap_update()` adds **at most one FFT frame per call** against `FFT_AVERAGE_COUNT = 4`. **No MEASURE block can post for ≥ 4 calls after a switch.**
2. The complex-FFT raw-sample drain (the actual transfer-function data, filled asynchronously by the ISR) is **gated on a fresh MEASURE block** (`measurement_engine.cpp:831–835` → `:895`).

**The wrinkle "same iteration" would have hidden:** `audioCap_update()` returns clip events *before* ROUTE_CHANGED. A leftover `CLIP_RETURN` (from a block that clipped on both channels) **delays the route event by one iteration.** It is still safe, because no fresh MEASURE block can exist in that window, but only because the one live arm path (`m`: EXTERNAL, `abort_on_clip = true`) always consumes its block.

**The level-accumulator reset alone is NOT sufficient.** It does not touch the raw queues or the measurement's accumulator. Safety comes from the fresh-block gate plus `abortTo()` clearing both.

Reordering the setter (invalidate before the GPIO write) was considered and **rejected**: nothing consumes audio synchronously inside the setter, so the order there cannot affect the invariant.

### Two findings recorded separately, not folded into ADR-004

- **Injection prerequisite (TODO-11):** ARMED with *internal* stimulus does not consume its block. A stale block plus clip-deferred ROUTE_CHANGED plus `abort_on_clip = false` could let post-switch raw samples in, even completing a mixed-topology RESULT. Unreachable today. **Must be closed before any internal arm path is reachable.** The fix is deliberately not chosen yet.
- **RAWDUMP (TODO-30), upgraded from noise cleanup to a measurement-integrity concern, code-derived and NOT bench-observed:** the unconditional diagnostic clears, re-arms and then *disarms* the same `AudioRecordQueue`s the measurement drains, every 5 s. That would likely stall or corrupt an `m` capture. **Fix it before relying on `m` for measurement validation.**

### Next

Software work stops here. **Next evidence milestone: build and verify the pin-15 RELAY_RETURN driver** (copy of the Phase 6 driver *with* its base pulldown), then TODO-7's proof. The TODO-7 pre-wiring checklist still applies (TODO-45 column count, TODO-46 forward-trace, corrected coil polarity, pole 1 only).

---

## 2026-09-16 (4) — ✅ DECISION: return source is selected by the operator, TS on every boot and not saved. ADR-004 makes ADR-003's Phase 7 preference binding. **Docs only; the firmware does not implement it yet**

**[ADR-004](../docs/adr/ADR-004-return-source-is-operator-selected.md) accepted.** This closes TODO-7's decision gate.

### Decision

- The operator's selection is the only thing that sets the return source: `TS` / `XLR`, **no `AUTO`**.
- **TS on every boot, not saved.** RELAY_RETURN de-energised is physically TS, so relay, software, display and operator expectation start in agreement. A saved XLR choice would mean booting on TS, reading the saved value, then energising the relay: an extra startup transition, and a window where the displayed configuration and the hardware disagree. Known startup state beats convenience.
- Jack presence must not choose the return or decide measurement validity. It may only show status or warnings.
- Selection changes apply immediately via `audioEngine_setRoute()` → ROUTE_CHANGED.
- **A return source is always *selected*. That is not a claim that a return signal is *connected*.** When the firmware lands, `route_valid` will mean "return routing configuration is defined", not "physical return established". Do not reintroduce presence detection because of the variable's historical name.

### The audit correction worth carrying forward

ADR-003 (and entry 2026-09-13 (13)) said `signalRouter_setReturnPreference()` *"suggests the software anticipated"* explicit selection. **That overstated it.** Read in the active tree, it is a **tie-breaker inside auto-detect**. Presence decides first, the preference is read only when *both* returns are detected, and a preferred jack that is absent silently falls back to the other one. It also has a real defect: `update()` returns before recomputing when no jack changed (cpp:264), so **a preference change never takes effect unless a jack also changes.** ADR-003 now carries a correction note. The original text stays for the record.

Nothing depends on the old behaviour. `setReturnPreference`, `canMeasure()` and `canInject()` have no callers, there is no serial command, and the main loop discards the `RouterEvent`.

### Evidence tier: decided ≠ implemented

The contract's return-source table now describes the ADR-004 policy, **marked NOT YET IMPLEMENTED**. The active `signal_router.cpp` is still auto-detect. Per the source-of-truth rule, do not record explicit selection as implemented until the firmware commit lands and has been read back.

**Order, deliberately split:** (a) decision + contract (this entry) → (b) separate firmware commit → (c) bench proof per TODO-7's new acceptance line.

### Consequences

- **Pin 22 is not required for Phase 7.** Keep the TS return #11. Do not build TS-return detection. Phase 7 hardware = pin-15 driver + signal wiring.
- TODO-7 proof rewritten: boot state, XLR/TS selection moves the relay and raises ROUTE_CHANGED, the reported source ignores jack state (including no jacks), TS signal reaches line-in R, and a power cycle returns to TS.
- **Runbook sign-off line 1702 corrected directly.** It read *"Full route matrix (4 jack combinations) produces correct route description on Serial"*, which is the superseded auto-detect criterion, and now carries the ADR-004 operator-selection criterion. **This deliberately departs from ADR-003's precedent** of superseding runbook lines by reference only. Once a decision is binding, a live checkbox that contradicts it is a stale-document trap: someone running the checklist months later should not need to know an ADR invalidated it. TODO-8's "microswitch detect" criterion is flagged for revisit before Phase 8, not rewritten.
- `signal_router_contract.md` is mode 0400. It was made writable for this edit and restored to 0400, per the 2026-09-11 (2) precedent.

---

## 2026-09-16 (3) — ✅ PHASE 6 SIGNED OFF. Gaps V6c–V6f closed at the bench; cleaned firmware flashed. Three small residuals, none blocking

### Closures (bench chat readings, `MEAS` via builder unless tagged)

| Gap | Result |
|---|---|
| V6c as-built coil wiring | **`55a` = +5 V (pin 1, coil +) · `55f` = collector (pin 10, coil −)** |
| V6d diode | 1N4148 lifted one leg, diode mode **0.602 V** (healthy), band at **`55a`** (+5 V node), non-band leg reseated in `55f` |
| Saturation after the fix | collector `49` energised = **129.1 mV** (0.1–0.3 V). Fresh reading, supersedes the `RPT` 0.126–0.127 V in entry (2) |
| V6f base pulldown | **8.94 kΩ in-circuit**, base strip → GND. Not previously in this record, so `RPT` for when it was taken |
| V6e firmware | cleaned build uploaded (`RPT`: builder said "uploaded") |

Full Phase 6 driver as built: pin 14 → col 53 → 0.993 kΩ → B `51` · E `50` → GND · C `49` → coil− `55f` · coil+ `55a` → +5 V · 1N4148 band `55a` · 10 kΩ `51` → GND. Contacts: `56a` NC · `57a` COM · `58a` NO (pole 1).

### Second opinion on the sign-off: agreed, with three residuals

1. **8.94 kΩ confirms the pulldown is present, not its value.** Measured in circuit, it is in parallel with the 1 kΩ → pin 14 path into an unpowered Teensy and with the B–E junction, which pull the reading low depending on probe polarity. A 10 kΩ part reading 8.94 kΩ in circuit is expected. That is enough for sign-off, since the pulldown only matters during reset.
2. **🟢 CLOSED same day by photo (`PHOTO`; builder's close-up, not yet copied into `ai/evidence/`).** It shows both 1N4148 leads bent into holes in the column-55 strips, on opposite sides of the relay, with neither lead end left floating. A photo cannot prove spring contact, but it rules out the lifted-leg case. **The band end is not legible at the photo's resolution**, so orientation rests on the electrical argument instead: a diode forward-biased across the coil would clamp it to ~0.7 V and the relay could not have picked up (`DERIV`), plus the 0.602 V out-of-circuit reading. The photo also shows the fitted relay marked **Panasonic TQ2-5V / ATQ209** (ATQ209 is Panasonic's product number for the TQ2-5V).
   **⚠️ Evidence-tier note on pin 1:** the TQ's orientation mark in this photo is a **full-width bar across the column-55 end**, not a corner dot. It identifies the pin-1 *end*, not the row side, so it cannot distinguish `55a` from `55f`. The earlier "stripe on the `55a` side" photo reading was more than the mark can support. **Pin 1 at `55a` is still established**, by intervention: +5 V moved to `55a` and the contacts began transferring (`DERIV` from `MEAS`). The conclusion stands; the photo was never the evidence for it.
   *(Original item:)* **The diode reseat was confirmed by "done" only.** The reseat step reopened the missing-diode risk, and nothing afterwards re-closes it. 129.1 mV and working contacts pass with or without the diode, and an in-circuit diode-mode check is masked by the 183 Ω coil in parallel (≈0.2 V both ways). **The practical close is a photo showing both legs seated** (`PHOTO`). Low risk, but it is the one part whose failure is silent and cumulative (BJT absorbs turn-off spikes), so it should not rest on a one-word report.
3. **🟢 CLOSED same day, read back from the board.** This session sent `?` over `/dev/cu.usbmodem192895301` via the serial MCP. The reply was `Unknown command: '?'` followed by the help list ending at `r=reset EMA`, with **no `p=toggle RELAY_SEND` line** across a 1.5 s window. The cleaned build is running (`MEAS`). *(Original item:)* **Confirm which build is actually flashed without actuating anything:** type any unknown key (e.g. `?`). The help list must **not** contain `p=toggle RELAY_SEND [PHASE6-TEMP]`. "Uploaded" is a report of the IDE finishing, not a readback from the board.

### Before Phase 7: don't treat it as simply "next"

The bench chat's closing advice (use the corrected Phase 6 driver as the template, not the runbook) is right. Phase 7 has recorded gates that come before any wiring:

- **TODO-7 decision gate:** return-source architecture (auto-detect vs explicit selection, ADR-003) must be decided first. It changes what gets wired to pin 22.
- **TODO-45:** the runbook's "mirror at columns 60–70" cannot fit on this board (an 11-column driver can't start at col 60 on a 60/63-column BB830). **Count the board's columns and re-site first.** Also correct steps 7–10's coil polarity so the mirror copies the right one.
- **TODO-46 forward-trace:** Phase 6 itself was a new relocation (base drive at col 53, coil wiring swapped). Any Phase 7 coordinate claiming col 53–59 needs checking.
- **As-built capture:** `docs/asbuilt/netlist.md` is a 2026-09-07 baseline with no Phase 6. The wiring table above is the source until it's added. TODO-46's owner note says that file belongs to the capture session, so coordinate the edit rather than making it here.
- **Only pole 1 contacts are bench-proven.** Pole 2 (`56f`–`58f`) is still datasheet-level. Phase 7 uses COM_1/NC_1/NO_1, so this doesn't block, but don't extend "bench-proven" to pole 2.

**🟢 Closed same day:** the removed original relay reads **TQ2-5V** (`RPT`, builder). Both relays were valid non-latching parts. The only root cause was the reversed coil polarity, and **the TQ2-L2 hypothesis of 2026-09-15 (5) is fully retired**: it was wrong about the part, although its warning about checking the marking before trusting an A/B stands. Diode photo archived as [`evidence/2026-09-16-phase6-flyback-diode-seated.jpg`](evidence/2026-09-16-phase6-flyback-diode-seated.jpg).

---

## 2026-09-16 (2) — ✅ PHASE 6 RELAY_SEND PASSES. Root cause confirmed as reversed coil polarity. My "rotate 180°" fix in entry (1) was wrong, and the bench chat caught it. `[PHASE6-TEMP]` removed

### Confirmation

- **Pin-1 stripe is on `55a`** (`PHOTO`, read from the bench photos by the bench chat). The diode band is on `55f`, which is +5 V. **Pin 1 (coil +) was on the collector, so the coil was reversed.** The polarity hypothesis in entry (1) is confirmed by the physical build.
- **The polarity was corrected by rewiring, and the relay stayed in place.** Then the full cycle was run, `MEAS` via the builder:

| State | `56a`↔`57a` | `57a`↔`58a` |
|---|---|---|
| LOW (before) | closed | open |
| HIGH | **open** | **closed** |
| LOW (after) | **closed** | open |
| Collector `49`, LOW after cycling | 4.99 V | |

**Contact map now bench-proven: `56a` = NC, `57a` = COM, `58a` = NO**, which matches runbook step 7 and the datasheet (pins 2 / 3 / 4). The only defect in the step 7 table is the coil polarity. **The root cause is established by intervention, not just correlation:** the only change was the coil polarity, and the contacts started transferring.

### 🔻 My error: the 180° rotation fix in entry (1) §6 would have broken the build

Entry (1) said that rotating the relay 180° would put pin 1 at `55f` and pin 10 at `55a` with "no rewiring". **That is a mirror image, not a rotation, and you cannot mirror a DIP package.** A real in-plane 180° rotation maps column *c* → 114 − *c* and swaps the row side:

| Pin | Now | After 180° rotation |
|---|---|---|
| 1 (coil +) | `55a` | **`59f`** |
| 10 (coil −) | `55f` | **`59a`** |
| 5 / 6 (no connection) | `59a` / `59f` | `55f` / `55a` |
| 7 / 8 / 9 | f side | `56a` NO / `57a` COM / `58a` **NC** |

The coil would have moved to column 59, where nothing is wired, so the relay would not have operated at all. **NC and NO would also have swapped on the a–e side.** Not destructive, but it would have produced another null result, and another wrong finding, on a phase that has already had to retract one. **The bench chat refused to rotate, fixed the polarity with wiring instead, and was right.**

The same geometric confusion runs back into **2026-09-15 (4)**, which described "an in-plane 180° rotation (pin 1 at `55f`)". Both entries treated the package as if it could be flipped across the gap. **Lesson: before recommending any physical move, write out the full pin-by-hole table, as done above.** Reasoning about "which end" in prose is how this happened twice.

### ⚠️ Not in the record, and needed

1. **The exact rewiring is not written down.** The bench chat gave "the single wiring change" in a turn this session did not see. **Record which jumpers now go to `55a` and `55f`.** The as-built needs it, and the Phase 7 mirror will copy it.
2. **Diode orientation after the fix is not recorded.** If the rails were swapped at `55a`/`55f`, the 1N4148 band must now be on **`55a`**, the new +5 V node. The working contacts **rule out a forward-biased diode** (`DERIV`): that would have clamped the coil to ~0.7 V and it could not have picked up. They do **not** rule out a diode that is missing or unseated. That fails silently, and the MMBT3904 absorbs the turn-off spike on every de-energise. **Check: band on the +5 V node, and diode mode ~0.65 V band→non-band, USB unplugged.** Same class of gate as V2a.
3. **Collector saturation after the fix.** The bench summary quotes 0.126–0.127 V, but those match the pre-fix readings (125.6 / 127.1 mV). It is not clear it was re-measured with the corrected coil. Low risk, since the coil current is the same either polarity. Recorded as `RPT`, not `MEAS`.
4. **V4 pulldown (10 kΩ base → GND) is still unmeasured.**

### Firmware

`[PHASE6-TEMP]` `p`/`P` handler and its help line removed. It was never committed, so the tree matches `HEAD` for that hunk. `grep PHASE6-TEMP` over `*.ino *.cpp *.h` is empty. The stale [.ino:314](../guitar_rig_analyzer.ino#L314) "Phase 6 is not built … electrically inert" comment is corrected, closing that TODO-45 sub-item. **Compile verified:** `arduino-cli compile --fqbn teensy:avr:teensy41 .` gives FLASH code 156 608 B (−128 B vs the handler build), RAM1 vars 218 080 B / 142 368 B free, RAM2 62 528 B. **Not yet flashed.** The Teensy still runs the build with `p`.

**Agreed with the bench chat's reason for removing it now, plus one more.** Once RELAY_SEND's contacts enter the signal path in Phase 7, `signal_router.cpp` owns pin 14 (L282/375/384). A second writer toggling the same pin from serial would desynchronise the router's idea of relay state from the hardware.

**Next:** record the rewiring (item 1), check the diode (item 2), flash the cleaned build. Then Phase 6 sign-off, and fix runbook steps 7–10 before Phase 7 copies them.

---

## 2026-09-16 (1) — 🔎 Latching hypothesis falsified on a verified TQ2-5V. New leading hypothesis: **the coil is driven backwards** — the TQ is a polarized relay and the runbook's step 7 table inverts pin 1 / pin 10

Second opinion requested by the builder mid-session with the bench chat (ChatGPT), which had stalled on two things: it could not find a current schematic, and it had exhausted the part-identity line of enquiry.

### 1. The "missing schematic" is not missing — and the column-45 question it wanted it for is already closed

The bench chat said it could only see the v3 runbook and needed "the actual current schematic" to reconcile column 45. **The as-built record is in the repo:** [`docs/asbuilt/netlist.md`](../docs/asbuilt/netlist.md) is the authority (it already shows R5 = `37c`→`41d`), and `docs/asbuilt/schematic_sheet1_analog.svg` / `schematic_sheet2_digital.svg` / `schematic_1sheet.svg` are generated from it. It is a **2026-09-07 baseline and predates Phase 6** — the Phase 6 as-built coordinates live in TODO-6 V1–V6a, not in the netlist.

**Column 45 was resolved on 2026-09-15** (entries (1)–(3)): col 45 A–E is VGND (R3 `45a`, R4 `45b`, grey jumper `45c`→`BOT_RED`), the base drive was relocated to **col 53** (53↔51 = 0.993 kΩ), and `BOT_RED` = 2.495 V proved the collision was never built. The bench chat was about to re-open a closed item. **Nothing about column 45 bears on the relay fault.** Attach `netlist.md` plus the TODO-6 block to the bench chat rather than a schematic image.

### 2. What the spare tells us (bench chat measurements, `RPT` via builder)

| Observation | Value |
|---|---|
| Marking | **TQ2-5V** |
| `59a`↔`59f` (pins 5/6) | **OL** — not dual-coil |
| Coil resistance | 183.5 Ω (spec 178 Ω) |
| Collector energised | 127.1 mV |
| **Voltage across coil, energised** | **4.69 V** (pickup spec ≤ 75 % × 5 V = 3.75 V) |
| `56a`↔`57a` / `57a`↔`58a` / `56a`↔`58a` energised | **closed / open / open** |

**This falsifies TODO-47's latching hypothesis as the explanation of the symptom.** A marked TQ2-5V with no second coil, driven well above pickup, reproduces the original relay's behaviour exactly. Whatever the original part is, the fault now follows the **placement/drive**, not the part. That is the A/B trap TODO-47 warned about, run in the informative direction: the parts are known to differ in marking and behave identically.

### 3. The datasheet: the TQ is polarized, and pin 1 is COIL +

Panasonic ASCTB14E (2019-11 edition), p.10, *Schematic (Bottom view)*, **Single side stable**: **`+` at pin 1, `−` at pin 10**; pin 3 = COM, pin 2 = NC (closed de-energised), pin 4 = NO; mirror pole 8 / 9 / 7. The 1-coil-latching variant is drawn with the opposite polarity, which is itself a hint that polarity is functional on this family. Crop saved as [`evidence/2026-09-16-tq-datasheet-coil-polarity.png`](evidence/2026-09-16-tq-datasheet-coil-polarity.png). The usage-guidelines page of the same document: *"When connecting coils of polarized relays, please check coil polarity (+,−) at the internal connection diagram (Schematic). If any wrong connection is made it may cause unexpected malfunction… and circuit do not work."*

Pin numbers are physical, so the bottom-view drawing does not change which pin is `+`.

**Runbook Phase 6 step 7 says pin 1 = COIL (−) at `55a` and pin 10 = COIL (+) at `55f`, and step 9 wires `55f` to +5 V.** That is the reverse of the datasheet. The as-built matches the runbook: coil+ `55f` = 4.99 V was measured (entry (2)) and the collector goes to `55a`.

**Why a reversed coil produces exactly this symptom.** A single-side-stable polarized relay uses a permanent magnet biased toward the reset side. Correct polarity overcomes the bias and throws the armature; reverse polarity *adds* to the bias and pushes it harder into the de-energised state. Current flows normally (183.5 Ω, 4.69 V), and there may be an audible tick, but **the contacts never transfer.** Every observation so far fits: identical contact state energised and unpowered, on both relays, on both poles, with a healthy driver.

**The contact map is confirmed by the same drawing:** de-energised 2↔3 closed = `56`↔`57` closed, the observed pair. Consistent with the withdrawal in 2026-09-15 (5).

### 4. Correction to 2026-09-15 (4)

That entry ruled out an in-plane 180° rotation as "undetectable from coil behaviour, since pins 1 and 10 both land on column 55 either way." **That reasoning assumed a non-polarized coil and is wrong for this part.** A 180° rotation swaps which of pin 1 / pin 10 sees +5 V, which is the entire difference between working and not working.

### 5. Not yet concluded: where pin 1 actually is

The runbook *told* the builder to put pin 1 at `55a`. **No one has recorded observing it there.** If the stripe is at `55a` (a–e side), the coil is reversed and the hypothesis is confirmed at `PHYS`. If it is at `55f`, pin 1 is already on +5 V, the polarity is correct, and this hypothesis dies.

**The bench chat's pending question needs sharpening.** It asked whether the stripe is at "the column 55 end or the column 59 end". The coil is proven to be on column 55, so the stripe *must* be at the column-55 end. The question that tells us something is **which row side: `55a` (a–e) or `55f` (f–j)?**

### 6. If confirmed, the zero-rewire fix is to rotate the relay 180°

Pin 1 moves to `55f` (+5 V) and pin 10 to `55a` (collector). The a–e side then carries pole 2: pin 9 NC → `56a`, pin 8 COM → `57a`, pin 7 NO → `58a`. **That is the same function-per-hole as before, so no jumper, the diode (cathode stays on the +5 V side at `55f`) and the contact test columns all stay put.** USB unplugged to reseat. Then `p`, and `57a`↔`58a` should beep.

**Bench cost of the reversed-drive testing so far is nil:** ~26 mA through a 140 mW-class coil with opposite field. Still, don't leave it energised longer than the measurement needs.

### Consequences to carry

- **Runbook defect #11:** Phase 6 step 7 coil polarity is inverted, and step 9 wires +5 V to the wrong pin. **Phase 7's "mirror of phase 6" inherits it.** TODO-45.
- **TODO-47's framing changes:** part identity is no longer the blocker for the spare. The *original* relay's marking is still worth recording before it goes back in a drawer — a TQ2-L2-5V left mixed in with TQ2-5Vs is a future trap.
- **The lesson generalises the MMBT3904 one:** the runbook cited the right datasheet and still got the pinout wrong. A citation is not a verification. Read the drawing.

**Next:** the builder reports the stripe's row side (`55a` or `55f`). If `55a`: USB unplugged, rotate 180°, reseat, USB in, `p`, then `57a`↔`58a` (expect beep) and `56a`↔`57a` (expect open). Then `p` again for the reverse.

---

## 2026-09-15 (5) — 🛑 The contacts do not follow the coil. Leading hypothesis: the relay on the board is a TQ2-L2-5V (dual-coil latching), not a TQ2-5V — and the bench already told us so two turns earlier

**Retraction of a claim made in entry (4).** That entry stated *"`58a` is NC"* as established, and TODO-45 recorded it as a runbook defect on that basis. **The deduction was unsound.** It assumed the energised sweep was showing a *transferred* contact state. The bare-relay test proves it was not. The correct reading of the same data is the opposite — `56`↔`57` closed is the **de-energised** pair, so `58` is the **NO** side, which is what the runbook says. **The runbook's POLE 1 contact table is not shown to be wrong, and that finding is withdrawn.** What is wrong is the assumption that the relay was switching at all.

### The decisive observation

| Pair | Energised, in circuit | **Unpowered, relay out of the board** |
|---|---|---|
| `56`↔`57` | CLOSED | **CLOSED** |
| `57`↔`58` | open | **open** |
| `56`↔`58` | open | **open** |

Identical. And the bare-relay pattern repeats on **both poles** (`56f`/`57f`/`58f` the same), so the part is internally symmetric and healthy-looking. **The coil energises — click, and collector saturation at 125.6 mV — but the contacts never transfer.**

### Leading hypothesis: it is a latching relay

A dual-coil latching relay driven on **one** coil does exactly this: it takes a pulse, throws once, and then holds that state with zero current regardless of what the driven coil does afterwards. The contacts stop following the GPIO after the first actuation.

**The strongest corroboration was already reported at the bench and was explained away.** The builder said: *"the relay clicks every other p input."* That was attributed to one direction simply being louder than the other. **It is not a perceptual artefact — it is the signature of a latching relay.** A non-latching relay clicks on *every* state change, energise and release alike. A latching relay driven on a single coil clicks when that coil is pulsed and stays silent on release. The observation was correct and the interpretation was wrong; this entry exists largely because a raw bench report was overruled by an assumption about how the part *should* behave.

**Supporting circumstantial evidence, all documentary:**

- The runbook's own gate, L1229: *"**Wait for the TQ2-5V to arrive before doing this phase.** TQ2-L2-5V (latching) won't work with the current firmware."* Phase 6 was executed without that gate ever being checked.
- Parts table L149 lists **TQ2-5V … "to buy"**; L150 lists **10× TQ2-L2-5V on hand**. So the latching parts are present and the non-latching ones are recorded as *not yet purchased*.
- L19 contradicts L149 outright, claiming *"5× TQ2-5V (2 used + 3 spare)"*. The document disagrees with itself about whether this part exists — and v3's own changelog says v3 "fixes … **a stale parts-availability claim in Phase 1**", so this document has a track record of exactly this error.
- The runbook calls pins 5 & 6 *"mechanical only — no electrical connection."* That is true for the TQ2. **On the TQ2-L2 those two pins are the second coil.** The claim is part-specific and was never checked against the part actually fitted.

### Two decisive tests, either sufficient

1. **Read the marking on the relay body** — `TQ2-5V` vs `TQ2-L2-5V`. Direct physical observation, the top of this project's own precedence order.
2. **Measure `59a` ↔ `59f` (pins 5 and 6), USB unplugged.** The runbook says these have *no electrical connection*: **OL confirms non-latching.** A reading of roughly a couple of hundred ohms is a **coil**, and confirms latching. Worth also taking `55a`↔`55f` — the TQ2-5V coil is specified at 178 Ω.

### If it is confirmed latching

The consequences are already written down in this project and should be re-read rather than re-derived — journal 2026-08-25 and TODO-6's own "Why": `signal_router.cpp` drives each relay with a single static `digitalWrite()`. A latching relay needs a set coil *and* a reset coil, i.e. **two GPIOs per relay and pulse-drive firmware**. That is a signal-router architecture change touching Phase 7 and the pin budget, not a Phase 6 wiring fix. **Do not improvise it at the bench.** The options are (a) obtain genuine TQ2-5V parts and keep the firmware as designed, or (b) accept dual-coil latching and re-scope the router — an ADR-level decision, like ADR-002/003.

Note the driver stage is unaffected either way: everything from V1 to V6a stands, and the MMBT3904 stage is proven. **The defect, if confirmed, is the part, not the build.**

### What is NOT concluded

- **Not** that the relay is latching. Two hypotheses remain: a latching part, or a non-latching part whose contacts are mechanically stuck. The every-other-click report strongly favours the first, and the marking settles it.
- **Not** that the runbook's contact table is wrong — that claim is withdrawn above.
- **Not** that anything is damaged.

**Next:** read the part marking; measure `59a`↔`59f`. Do not energise again until the part is identified — pulsing one coil of a latching relay repeatedly is harmless, but every further contact measurement taken against the wrong part model produces another finding that has to be retracted.

---

## 2026-09-15 (4) — ✅ RELAY_SEND driver stage PASSES. Relay contact pinout is NOT what the runbook says — `58a` is NC, and the runbook calls it NO

**Record-keeping correction, stated plainly:** the previous turn of this session told the builder that journal entry (4) and a TODO-6 split had been written. **No write had occurred.** The claim was false when made and is corrected by this entry. Nothing on the bench was affected, but a reader trusting that message would have believed a record existed that did not.

### Driver stage — PASS

| Check | Observed | Criterion | Verdict |
|---|---|---|---|
| Upload | completed | — | ✅ |
| `p` toggles relay | audible click each state change | click on `p`/`P` | ✅ |
| Collector `49` energised | **125.6 mV** | 0.1–0.3 V (saturated BJT) | ✅ |
| Collector `49` de-energised | 4.99 V | ~5 V | ✅ |

**The MMBT3904 driver stage is proven end to end** — GPIO → 1 kΩ (0.993 kΩ, col 53→51) → base → saturation at 125.6 mV → coil current → mechanical actuation. Everything from TODO-6 V1 through V6's driver half is closed.

### Contact identification — the runbook's TQ2 contact map is wrong

The runbook's Phase 6 step 7 table asserts pin 2 = POLE1 **NC** (`56a`), pin 3 = POLE1 **COM** (`57a`), pin 4 = POLE1 **NO** (`58a`), and the end-of-phase verify expects `COM_1 ↔ NO_1` — i.e. `57a`↔`58a` — to beep when energised. **It does not.** Full sweep, relay energised, continuity mode:

| Pair | Energised |
|---|---|
| `56a` ↔ `57a` | **CLOSED** |
| `57a` ↔ `58a` | open |
| `56a` ↔ `58a` | open |

**What this establishes, and what it does not.** The closed pair when energised is `{56a, 57a}`, so COM is **one of those two** — the data cannot yet say which. What *is* already settled is the third pin: on a standard changeover, the de-energised throw must be the pin that is open to everything while energised. **`58a` is NC.** The runbook calls `58a` **NO**. That assignment is wrong regardless of how the COM question resolves.

**Orientation was eliminated as the explanation before the pinout was blamed.** An end-for-end flip (pin 1 at `59a`) is ruled out by the click itself — it would put the coil on column 59 and leave `55a`/`55f` as the mechanical-only pins 5 and 6, so the relay could not energise. A 180° in-plane rotation (pin 1 at `55f`) is undetectable from coil behaviour, since pins 1 and 10 both land on column 55 either way — but it does not help, because it puts POLE 2 (pins 7/8/9) on the a–e side, and the runbook maps *that* triple as NO/COM/NC with COM again in the middle. **Both surviving orientations predict `57a`↔`58a` closed when energised.** The observation contradicts both, so the fault is in the pin-function assignment, not the placement.

This is the **tenth** documented runbook defect, and the second pinout error in Phase 6 alone — after the MMBT3904 E–B–C ordering in entry (2). **Every pinout table in this runbook should now be treated as unverified until measured.**

### Correction to a conclusion drawn at the bench

The bench reading of this sweep was *"57a is COM, and 56a is acting as NO."* **That is one of two possibilities and is not yet supported.** `56a` is equally consistent with being COM:

| If de-energised closes | Then |
|---|---|
| `57a` ↔ `58a` | `57a` = COM · `56a` = NO · `58a` = NC |
| `56a` ↔ `58a` | `56a` = COM · `57a` = NO · `58a` = NC |

Both fit every measurement taken so far. The de-energised sweep discriminates, and until it is run the COM assignment is `INF`, not `MEAS`. Recorded because this project has been bitten specifically by promoting a placement inference to a verified fact.

### Incidental observations from the live diagnostics

Captured over the serial link while toggling (uptime 278 s and 798 s samples):

- Block period **46.3–46.7 ms**, Pi link **17 117 frames, 0 dropped**, call time max **283 µs**, TF clamped **0 of 512** — all consistent with the post-stack normals in TODO-41A.
- **Loop rate ~924 k/s, against the ~1.50 M/s recorded as the new normal in TODO-41A.** A ~38 % reduction. **Not a conclusion** — no controlled comparison was run, the two samples come from different firmware builds, and nothing in this phase's scope depends on it. Recorded as an observation to re-check when the `[PHASE6-TEMP]` handler is removed, not as a regression claim.
- SOURCE_NODE peak wandered −60.5 → −48.9 dBFS between samples with nothing connected; RETURN_NODE steady at ~−65 dBFS.

### Session note

The builder handed the serial port to this session; the Teensy is driven directly over `/dev/cu.usbmodem192895301` at 115200 via the serial MCP. **Opening the port did not reset the board** — the `static bool s_send_relay` toggle state survived, which is expected for Teensy USB serial and is worth knowing before anyone reasons about relay state across a reconnect.

**Next:** de-energised sweep of `57a`↔`58a` and `56a`↔`58a` to fix COM, then rewrite the runbook's POLE 1 table from measurement and re-run the end-of-phase criterion against the corrected mapping.

---

## 2026-09-15 (3) — All pre-trigger checks pass, but the `p` command did not exist in the firmware. Added; Phase 6 is now genuinely ready to actuate

**The runbook's Phase 6 step 11 was never carried out.** The serial dispatch in [guitar_rig_analyzer.ino:395](../guitar_rig_analyzer.ino#L395) handled `v 1 2 3 4 r m T t u i x s b c` and **no `p`**. Typing `p` would have printed `Unknown command` and the relay would have sat silent — a null result with no hardware cause, on a driver that had just passed six consecutive pre-trigger checks. That is the worst possible moment to introduce a phantom fault, and it was one keystroke away.

### Pre-trigger checks — all pass

| Check | Reading | Verdict |
|---|---|---|
| V1 — `BOT_RED` (VGND) → GND | **2.495 V** | ✅ VGND healthy at half-supply; the col-45/pin-14 collision is **not** built |
| V2 — collector `49` → GND | 4.99 V | ✅ pulled up through coil, BJT off |
| V2 — coil+ `55f` → GND | 4.99 V | ✅ 0 V across coil, de-energised |
| V2a — 1N4148 cathode band | **at `55f`** | ✅ correct; the destructive-on-first-actuation case is ruled out |
| Emitter `50` → GND | **0.0 mV** | ✅ emitter correction physically confirmed |
| Base-drive node `53` at boot | 0.5 mV | ✅ pin 14 LOW, nothing driving the base |

**V1 is now fully closed.** Entry (2) flagged that "0.5 mV at the base node" could not distinguish *"col 45 is clear"* from *"VGND is being clamped."* 2.495 V settles it in the safe direction — the divider is doing its job and nothing is pulling on it.

### The 0.5 mV reading is trustworthy, and that needed checking

A driven-LOW output and an unconfigured floating input can both read ~0 mV on a high-impedance meter — and with a 10 kΩ base pulldown to GND in the circuit, a floating pin 14 would read near 0 V too. So the reading only means what we want it to mean if pin 14 is actually configured. **It is:** [guitar_rig_analyzer.ino:320](../guitar_rig_analyzer.ino#L320) calls `signalRouter_init()` in the live path, which sets both relay pins `OUTPUT` and drives them `LOW` ([signal_router.cpp:202-204](../signal_router.cpp#L202)). Worth noting the comment at [.ino:314](../guitar_rig_analyzer.ino#L314) states this relay-GPIO activity is "electrically inert" because "Phase 6 is not built" — **that premise expired the moment the driver went onto the board.** It should be corrected when the temporary command is removed.

### Change made

Added the Phase 6 bring-up toggle to the dispatch, tagged `[PHASE6-TEMP]` in both the case and the help text so a single grep finds every piece at removal time. It matches the runbook's step 11 snippet, with one correction carried in the comment:

**`p` and `P` are the same command.** The runbook's end-of-phase verify table reads "Type `p` (energise)" / "Type `P` (de-energise)", but its own code snippet is `case 'p': case 'P':` around a `static bool` toggle — *either* character flips the state. Pressing `p` twice de-energises. The handler now prints the resulting state explicitly, so the printed line is authoritative rather than the keystroke. This is the **ninth** documented runbook defect.

### Still unverified, and the most likely cause if there is no click

**The base path has never been proven continuous since it moved to column 53.** The original failure that triggered this whole halt was an unseated resistor leg — "continuity from the 51 side, nothing from 45" — and the relocated resistor has not been re-checked end to end. The measurement that was asked for at the very start of this sequence and never cleanly answered still stands, now against the right column: **resistance col 51 (Base) ↔ col 53 ≈ 1 kΩ**, USB unplugged.

So if `p` prints `RELAY_SEND -> HIGH (energised)` and nothing clicks, the driver is not the first suspect — the 1 kΩ seating is. Distinguish them with the collector: it should fall from 4.99 V to **0.1–0.3 V** on energise. Still 4.99 V means the base is not being driven.

### What is NOT concluded

- **Not** that the relay works. Nothing has been energised yet.
- **Not** that the flashed image matches this tree. The `p` handler is absent from the sketch *as committed*; the build on the board was inferred from that, not read back from the Teensy.

### Corrections to this entry, same day

**V3 was already closed and this entry said otherwise.** Above, the base path is listed as "never been proven continuous since it moved to column 53." **That is wrong** — the builder had already measured **col 53 ↔ col 51 = 0.993 kΩ** after the relocation, which is 0.7 % off a 1 kΩ nominal and well inside a 1 % part. **The original unseated-leg failure mode is closed on the new node.** Recorded here rather than silently edited above, per this file's own rule. The lesson is narrow and worth keeping: the reconciliation carried an open item forward because *this session* had not seen the measurement, not because it had not been taken — bench state can move ahead of the record between turns, and "I have no evidence of X" must not be written as "X is unverified."

**Compile verified.** `arduino-cli compile --fqbn teensy:avr:teensy41 .` succeeds with the `[PHASE6-TEMP]` handler in place — FLASH code 156 736 B, RAM1 variables 218 080 B with 142 368 B free for locals, RAM2 62 528 B. No errors and no new warnings; `RELAY_SEND_PIN` resolves through `config.h` at [.ino:102](../guitar_rig_analyzer.ino#L102). This satisfies the same criterion TODO-1 uses — a real build attempt, not code presence.

**Next:** flash, then `p`. Expect the `[BringUp]` line and a click; verify against the end-of-phase table — collector 0.1–0.3 V, COM_1↔NO_1 closed, COM_1↔NC_1 open, and the reverse on the next press.

---

## 2026-09-15 (2) — Phase 6 driver orientation resolved by measurement; runbook step 2's transistor pin order is wrong. Flyback diode polarity is the remaining gate before first actuation

**Supersedes one claim in entry (1):** that entry recorded an open question as to whether the SIPH06-1 had shifted one column right (E=50, B=51, C=52). **It had not.** The adapter is on the runbook's own columns; it is the *pin order* the runbook states incorrectly.

### Bench evidence, USB plugged in, black probe on `TOP_GND`

| Node | Reading | What it establishes |
|---|---|---|
| Teensy pin 14 / base-drive node | **0.5 mV** | Pin 14 boots LOW per [signal_router.cpp:202-204](../signal_router.cpp#L202); nothing drives the base node |
| Collector, **column 49** | **4.99 V** | 49 is the node tied to relay coil−, pulled to the rail through the coil, BJT off |
| Coil +, **`55f`** | **4.99 V** | 0 V across the coil — correctly de-energised |

**Orientation, now settled: `49` = Collector, `50` = Emitter, `51` = Base.**

### The runbook's Phase 6 step 2 cannot be followed on this part

Step 2 (L1263) says to orient the adapter so the silkscreen reads **E – B – C** left-to-right. Phase 0.5 (L504) says the adapter is marked **C / B / E**. The two disagree with each other, and **both put the Base in the centre position.**

An MMBT3904 in SOT-23 is **pin 1 = Base, pin 2 = Emitter, pin 3 = Collector** — the collector is the lone pin on its side of the package, and **the emitter is the centre pin**. So "E – B – C" is not a valid ordering for this device in either direction. The bench result (C/E/B) is consistent with the part and with nothing else.

Built as step 2 instructs, emitter and base land swapped: the stage does not switch, and the base-emitter junction sits reverse-biased toward its ~6 V breakdown rating. **This is the eighth documented runbook defect.** Step 2's parenthetical *"sanity-check with the DMM: probe each header pin back to the SOT-23 pad"* is the line that caught it — it should be mandatory, not parenthetical. Consequence for step 6: the emitter-to-GND jumper belongs at column **50**, not `49a` as written.

### Why "both coil ends at 4.99 V" is weaker evidence than it looks

It is a correct and expected de-energised reading, and it does **not** test the flyback diode. With the BJT off there is ~0 V across the coil, so a **reversed 1N4148 passes nothing and reads identically to a correct one.** The diode is only tested at the instant the transistor saturates, and if it is backwards it fails destructively at that instant — the runbook's own step 10 states the failure mode: *"Reversed: the diode shorts +5V to GND through the BJT whenever pin 14 goes HIGH."*

That short is limited only by the diode and the MMBT3904 (200 mA rated). It would take out both parts, and it browns out the **+5 V rail that also feeds the Teensy carrier and the Audio Shield** — so a bad outcome would not stay local to Phase 6. **Cathode band must be at `55f` (COIL +, rail side).** This is recorded as TODO-6 **V2a** and gates the first `p`.

**General lesson, worth carrying past this phase:** a de-energised measurement can only confirm the *static* half of a switching circuit. Every part whose job begins at the switching edge — flyback diodes, snubbers, pulldowns during reset — is untested by any number of quiescent voltages that look right. Enumerate those parts *before* the first actuation, not after.

### Still open from entry (1)

**V1 is only half closed.** "0.5 mV at the base-drive node" confirms pin 14 is LOW, but it does not by itself distinguish *"col 45 is clear"* from *"VGND is being clamped by pin 14."* One probe settles it while the board is already powered: **`BOT_RED` → GND must read ≈ 2.50 V.** Near 0 V would mean the column-45 collision was built after all and C8 has been discharging into the pin. Recorded rather than assumed.

### What is NOT concluded

- **Not** that the driver is correct end to end. The base path itself (V3) is still on the pre-halt wiring; only the transistor's identity and the coil's static state are established.
- **Not** that the relay will actuate. If the base resistor still lands on col 45 rather than a verified free column, `p` produces no click — a benign outcome, but do not read silence as a driver fault before checking V3.

**Next:** V2a (diode band at `55f`) and the `BOT_RED` = 2.50 V reading, in either order, both before the first `p`. Then V3/V4, then the end-of-phase table — collector 0.1–0.3 V on `p`, COM_1↔NO_1 closed, COM_1↔NC_1 open, and the reverse on `P`.

---

## 2026-09-15 (1) — 🛑 PHASE 6 HALTED: column 45 is VGND, not a free column. Runbook Phase 6 step 4 would tie Teensy pin 14 directly to the analog reference rail

**Do not fit the `45a` → Teensy pin 14 jumper. Do not plug in USB until the reconciliation below is checked at the bench.** Phase 6 construction is halted, not failed — nothing is known to be damaged.

### The bench report that triggered this

Conley, mid-Phase-6 bring-up with the Phase 6 firmware already installed, measured continuity from the Base side of the new 1 kΩ base resistor (column 51) but **not** from its other leg to column 45, and asked whether the earlier circuitry at column 45 — "something else with 2 resistors" — was the cause. It is. The as-built record settles it without needing another photograph.

### Column 45 A–E is VGND — it has been since Phase 1

From [`docs/asbuilt/netlist.md`](../docs/asbuilt/netlist.md), §2 and §3, all at `PHYS` confidence at strip level:

| Ref | Value | Location |
|---|---|---|
| R3 | 10 kΩ | `TOP_GND` → **`45a`** |
| R4 | 10 kΩ | `TOP_RED` → **`45b`** |
| grey jumper | — | **`45c`** → `BOT_RED` rail |

> **VGND** | `BOT_RED` rail · `45c` via grey jumper · **col 45 A–E** · C7+ · C8+ | `PHYS`

**R3 and R4 are the two resistors Conley remembered.** They are the +5 V / GND divider whose midpoint *is* column 45 A–E, and `45c` is what distributes that midpoint to the `BOT_RED` rail. Note the exact hole matters not at all and the exact hole is occupied anyway: col 45 A–E is one node, and R3 already sits in `45a` — the precise hole Phase 6 step 3 calls free.

### Root cause: a documented deviation whose downstream consequence was never traced

This is not a new discovery so much as an old one that was filed and never followed forward. Netlist §5 deviation **D3** reads:

> D3 | VGND divider is at **col 45**, not col 15. Rail decoupling at **col 39/41/54**, not col 5/7/18/20 | Pure relocation. Runbook Phase 1 coordinates are stale

The runbook's Phase 1 puts the VGND divider at column 15. The board puts it at column 45. D3 assessed that as "pure relocation" — benign — and on its own terms it was. **But `docs/breadboard_bringup_v3.md` then hard-codes `45a` as "a free column" in two later phases, and D3's assessment never checked that.** A relocation is only benign if nothing downstream claims the destination.

Two collisions follow from it:

| Runbook | Step | What it does | Status |
|---|---|---|---|
| Phase 4 step 6 (L968–969) | 100 kΩ from `37a` → **`45a`**, plus jumper `45a` → `BOT_RED` | Would have landed the bias resistor on VGND | **Dodged by accident.** As-built R5 is `37c` → `41d`, biased from OPA_BIAS instead — the TODO-21 common-mode redesign moved it before it could collide |
| Phase 6 steps 3–4 (L1269–1271) | 1 kΩ from Base strip → **`45a`**; then **jumper `45a` → Teensy pin 14** | Ties a 3.3 V push-pull GPIO to the analog reference rail | **Live right now** |

Step 3 alone is merely wrong — it puts the BJT base resistor on the wrong node. **Step 4 is the dangerous one**, because it is a direct, unresistored connection from a Teensy output pin to a rail carrying C8 (10 µF) and C7 (0.1 µF) plus the R3/R4 divider.

### What the installed firmware would have done on the next boot

This is why the halt is worth the interruption rather than being left for the next session:

- [`config.h:243`](../config.h#L243) — `RELAY_SEND_PIN 14`
- [`signal_router.cpp:202-204`](../signal_router.cpp#L202) — `signalRouter_init()` sets pin 14 `OUTPUT` and immediately `digitalWrite(..., LOW)`
- [`signal_router.cpp:375`](../signal_router.cpp#L375) — drives it `HIGH` on the `p` relay command

So with that jumper fitted, the *first power-up* clamps VGND to 0 V and dumps C8's stored charge (2.5 V across 10 µF) into pin 14, current-limited by nothing but the pin's own impedance. Steady state is survivable — R4 sources only 5 V / 10 kΩ = 0.5 mA — but the capacitor inrush is not something to hand a GPIO deliberately.

**Two things that limit the blast radius, both recorded rather than assumed:**

1. **Netlist D4: "VGND is alive but unloaded. Nothing on the board uses it."** The analog front end biases from OPA_BIAS (col 41/43, fed by R1/R2), which is independent of VGND. So clamping VGND would *not* have corrupted the Phase 4/5 signal path. The exposure is to pin 14, C7/C8 and R3/R4 only.
2. **No 5 V-tolerance violation is possible in the as-built.** Before `pinMode()` runs, pin 14 is high-Z and column 45 sits at 2.5 V — under 3.3 V. The Teensy 4.1 is **not** 5 V tolerant, so this matters: netlist §1 records `TOP_RED ↔ BOT_RED bridged? **No.**` at `PHYS`. **If anyone ever fits the Phase 0 step 5 bridges that netlist deviation D5 warns about, `BOT_RED` becomes +5 V and this same jumper instantly destroys the pin.** D5 and D3 are individually survivable and jointly destructive.

### Reading Conley's measurement

"Continuity from the column-51 side of the resistor, nothing to column 45" is exactly the signature of that resistor leg **not seated in a column-45 hole**. That is *consistent with* the hazardous connection never having been completed, and nothing analog has misbehaved. **It is not proof** — the same reading comes from a leg seated in the wrong strip entirely. It is checkable at the bench in one measurement, recorded in the todo.

Separately: a 1 kΩ resistor will not beep on most meters in continuity mode, so "no beep" across the resistor is not evidence of a fault. Resistance mode is the right instrument here, and the meaningful reading is strip-to-strip, not leg-to-leg.

### A second, unresolved discrepancy in the same bench report

Conley reports **Base verified at column 51**. Runbook Phase 6 step 2 places the SIPH06-1 adapter at E=`49e`, B=`50e`, C=`51e`. If Base is genuinely at 51, the adapter sits one column right of the runbook — E=50, B=51, C=52 — which is *self-consistent* with the corrected Collector reaching the relay coil− node, and with continuity appearing on the 51 side of the base resistor.

**That shifts every coordinate in Phase 6 steps 3, 5 and 6, and it is not yet confirmed.** It is recorded as an open bench question, not folded into the fix.

### What is NOT concluded here

- **Not** that the board is damaged. No evidence of that, and D4 bounds what could have been affected.
- **Not** that the transistor is at 50/51/52. One builder-reported probe on one pin.
- **Not** that column 45 F–J is usable. The netlist does not record it as occupied, but R3 and R4 physically span it on their way from the top rails.

### Decision

Phase 6's Teensy-side drive node **moves off column 45.** The 1 kΩ base resistor runs from the Base strip to a genuinely free column, and *that* column jumpers to pin 14. Preferred target is **column 53 A–E** — unclaimed in the netlist, and on the relay side of the transistor, which keeps a switching drive line out of the columns 30–48 analog territory entirely. Column 46 A–E is the alternative if 53 is physically awkward. Either way the column gets verified dead before use, rather than trusted because a document called it free.

The runbook is corrected rather than worked around (TODO-45), and the remaining as-built deviations get the forward-trace that D3 never got (TODO-46).

**Next:** bench verification sequence in TODO-6 — confirm col 45 is untouched by the new work, confirm the transistor's actual columns, then rebuild steps 3–4 on the relocated column. USB stays unplugged until the first two are done.

---

## 2026-09-13 (13) — ✅ REQUIREMENTS CORRECTION: jack presence detection is a UX feature, not a hardware requirement. Phase 5 unblocks for $0

**[ADR-003](../docs/adr/ADR-003-jack-presence-is-a-ux-feature.md) accepted.** Keep the Switchcraft #11s. Buy nothing. Phase 5's *"detect events fire"* criterion is removed.

### What the code trace actually showed

`s_jack_instrument.debounced` appears in three places: the status struct and two serial prints. It is absent from **every** decision path — `computeReturnSource()`, `route_valid`, `can_inject`, `buildDescription()`, `applyReturnRelay()`. Its only downstream consumer is `data_sender.cpp:603`, one bit of a UI packet, reached through `presentation_routerStatus()` — **which is never called from the application.** `signalRouter_canMeasure()` and `signalRouter_canInject()` are never called either.

**Instrument presence currently feeds nothing at all.** Phase 5 was blocked waiting on a GPIO transition that no code reads.

| Pin | Jack | Gates | Verdict |
|---|---|---|---|
| 16 | Instrument In (#11) | **nothing** | **not required** |
| 17 | Rig Send (#11) | `can_inject` — never called | inert |
| 22 | Rig Return TS (#11) | `computeReturnSource()` → **drives the relay** | genuinely load-bearing |
| 24 | Return XLR | same | microswitch already designed |

### Why this is a requirements correction and not a workaround

The acceptance criterion was written believing the #11 had a switch contact. It does not — established twice, by bench DMM and by Switchcraft's own *"Open circuit"* designation. **The #11 is not failing at being a guitar jack; it was assigned a second job the product does not need.** Keeping the criterion would mean redesigning working hardware to satisfy an obsolete test.

**Revised Phase 5 acceptance:** *a standard 1/4" TS guitar connected to Instrument In passes cleanly through the intended analog signal path with normal level and no unintended loading, distortion, oscillation, or loss of signal.*

### Three decisions deferred, each with the question it must answer

- **Phase 7 — Return Source Detection Architecture.** Automatic presence detection vs explicit operator selection. **Preference recorded, not binding: explicit**, because this is test equipment, not a consumer pedal — an explicit `Return: TS / XLR` choice keeps the measurement configuration unambiguous rather than letting a hardware signal silently determine a scientifically meaningful routing choice. `signalRouter_setReturnPreference()` already exists, which suggests the software anticipated it. **TODO-7's proof line presumes auto-detect and must be revisited with this decision.**
- **Injection — what is Rig Send detection actually preventing?** Define the requirement before choosing a mechanism. **A plug being present does not prove the downstream rig is connected correctly**, so plug presence may be the wrong signal entirely rather than merely inconvenient.
- **ADR-002 is unweakened and still in force.** It governs *how* detection may be built; ADR-003 governs *whether* it is needed. If Phase 7 chooses automatic detection, ADR-002 applies in full.

### What this cost, and what it bought

Cost: a branch that ran from firmware through a register-level investigation, a physical dissection of the shield input, an arithmetic proof, a manufacturer search, and two ADRs. Bought: **the #11s stay, Phase 5 unblocks today, and $0 is spent** — plus three real architecture questions now stated explicitly rather than answered by accident.

**The entry point of the whole branch was accepting a runbook drawing as as-built fact.** The exit was reading the code instead of the documentation. That is the lesson worth carrying: *when a document and the tree disagree about what the system needs, the tree is the authority* — which is precisely what this journal's own source-of-truth precedence rule already said.

### ⚠️ One consequence not to misread later

The Pi UI's jack indicators will show a permanently-absent instrument jack until pin 16 is wired to something real or the indicator is removed. **That is expected, not a fault.**

---

## 2026-09-13 (12) — 🔎 Manufacturer search: Switchcraft's own catalogue independently confirms the bench finding, and **12B** is the candidate — but the datasheet CANNOT answer the question we actually need answered

### The bench finding is now independently corroborated by the manufacturer

Switchcraft's jack schematic table lists:

| Type | Circuit |
|---|---|
| **11** | **Open circuit** |
| 12A | **Tip shunt** |
| **12B** | **Double open circuit** |

**The `11` is a plain 2-conductor jack with no switching contact — exactly what the continuity test measured.** Two independent sources now agree: the DMM at the bench, and the manufacturer's own circuit designation. The runbook's drawing at lines 1105–1113, which shows a SWITCH terminal on the #11, is **wrong about the part**, and that is now settled rather than inferred.

The `12A` is confirmed as **tip shunt** — the topology already ruled out by ADR-002 and 2026-09-13 (8). **Do not buy it.**

### Candidate: Switchcraft 12B

`1/4" Stereo 3 Conductor Jack w/Nut & Washer, **Double Open Circuit**` — three independent contacts (T, R, S), **no shunt and no switch on either tip or ring**, solder lugs, panel mount in a 0.375" hole, same open-frame family as the installed `11`. Orderable: DigiKey **109541**, also RS, Mouser, CE Distribution, Amplified Parts.

*"Double open circuit"* is the operative phrase: it means the third conductor is a **plain ring contact**, not a switch — which is precisely what the TRS-ring detect scheme needs, and precisely what distinguishes it from the 12A.

### 🔺 The limit of what any datasheet can settle here

**No Switchcraft document states that a TS plug's sleeve bridges RING to SLEEVE.** That is **mechanical contact geometry**, not an electrical specification, and it is not published. It is universally true of A-gauge 1/4" jacks in practice — it is how effects pedals switch their battery — but *"universally true in practice"* is **exactly the evidence tier that started this entire branch.** A drawing asserted a switch contact; the physical part did not have one.

**So the datasheet gets us to:** *12B is a plain TRS jack, three independent contacts, no shunt, same form factor as the installed 11.*
**It does not get us to:** *ring shorts to sleeve when a TS plug is inserted.*

**That second claim must be measured on a physical sample with the actual TS cable in use, before any decision to standardise.** Conley's proposed sequence already does this and is correct as written. Buy **one** (consider two — they are inexpensive), continuity-map it, then bench-prove it.

### Also checked and set aside

**Neutrik NMJ6HF-S** — 1/4" stereo, solder lugs, ≥1 GΩ insulation, >10,000 mating cycles, contact resistance <15 mΩ. Good part, but it is a **switched** jack listing **two switching contacts**, and what those contacts do is not determinable without the mechanical drawing. For a hand-wired prototype that is added complexity in exchange for a capability the TRS-ring scheme does not need. **Not rejected — deferred**, as the fallback if the 12B's ring does not bridge reliably.

### Unchanged and still required regardless of part choice

The **TODO-40 ground measurement**. Whichever part is chosen, the TRS-ring scheme routes ~150 µA of detect current through the audio ground at the jack, and this project has an unexplained 33.1 dB ground-return sensitivity on record. **Noise-floor before/after, detect disconnected vs connected, is not optional.**

---

## 2026-09-13 (11) — 🔻 MY ERROR: I concluded a part was in hand from a figure that only shows it was designed in. And a correction to the purchasing plan

### The error

Entry (10) says, in consecutive sentences: *"It appears in **no** parts table and **not** in Cup E"* and then *"The bench proof below needs one, **and one exists.** No purchasing blocks it."*

**The second sentence contradicts the first and has no support.** The D2F-01L appears exactly once in the whole repository — `docs/breadboard_bringup_v3.md` line 1583, inside the Phase 8 *design figure*. That is evidence the part was **planned**, not that it was **bought**. The parts list Conley actually purchased from contains *"3× Switchcraft #11, 1× Neutrik XLR"* and no microswitch of any kind.

**Assume D2F-01L on hand = 0.** Standardising three 1/4" detects plus the XLR needs **four**, and the count of additional units required is **four, not three** — my earlier figure subtracted a unit that does not exist.

**This is the exact evidence-tier failure this project already has a rule for.** I had the disconfirming evidence *in the same paragraph*, wrote it down, and drew the opposite conclusion anyway. "Appears in a design figure" is the weakest possible tier for a stock claim, and I promoted it to "in hand" without noticing. It would have sent Conley searching bins for a part that was never ordered. Caught by ChatGPT at the bench, not by me.

### Second opinion on the purchasing plan — one point I disagree with

**Agreed:** do not buy the Switchcraft **12A**. Its third terminal is a **tip shunt**, which is the topology already ruled out — it hands the detect job back to the TIP node and re-creates the conflict proven in (8).

**Agreed:** "three terminals" ≠ "plug detect." That conflation is what started this whole branch.

**Disagreed — a TRS jack's RING *is* a standard insertion detector, and dismissing it may discard the best option.** The claim that a stereo jack's third conductor *"is not an independent insertion detector"* is not correct as stated. Using the ring of a TRS jack to detect a **TS** plug is the classic method (it is how effects pedals switch their battery). The mechanism: a TS plug's sleeve barrel is long enough to bridge the RING and SLEEVE contacts, so:

| State | RING | pin 16 (INPUT_PULLUP) |
|---|---|---|
| empty | open | **HIGH** |
| TS plug inserted | shorted to SLEEVE = GND | **LOW** |

**Checked against ADR-002:** the detect path is `pin 16 → RING → (plug sleeve) → SLEEVE → GND`. **It never touches TIP**, so it imposes no loading on the guitar signal node and the ~1 MΩ requirement is untouched. Closed resistance is metal-to-metal, ~0 Ω, far inside the < 9.4 kΩ bound. **Compliant.**

**Polarity:** this is the *opposite* sense from the microswitch — empty HIGH, inserted LOW — so `JACK_INSTRUMENT_DETECT_INVERTED` would be **0**, not 1. The per-connector polarity defines added in `b32d04a` already accommodate this without a code change, which is an unplanned vindication of choosing four defines over one global flag.

**The caveat that is genuinely this project's problem, and it is not generic.** The detect return path runs through the **audio ground at the jack**, and pin 16's 22 kΩ pull-up sources ~150 µA into it when a plug is inserted. That is DC and tiny. But **TODO-40 recorded a 33.1 dB change in the SOURCE noise floor from moving one ground return**, and the mechanism is still unidentified. A project with demonstrated extreme sensitivity to audio-ground return topology should not add a new DC path into that node without measuring. **Not disqualifying — it needs a before/after noise-floor measurement, which this project already knows how to take.**

### Where that leaves the purchase

Three options, none selected here:

1. **Isolated-switch 1/4" jack** — cleanest electrically, no bracket, no alignment, detect never touches any audio node. Requires finding a real part number that actually has an isolated switch rather than a tip shunt.
2. **TRS jack, ring as detect** — cheap, universally available, no mechanical work, ADR-002-compliant on TIP. Costs a DC path into audio ground that must be measured against TODO-40.
3. **External microswitch** — proven topology, zero audio-node contact of any kind, but four units to buy plus an unsolved mechanical mounting/alignment problem per jack.

**No part number is recommended until one is verified against a manufacturer datasheet.** Given how this branch started — a runbook drawing asserting a switch contact that the physical part did not have — **a datasheet claim about switching topology must be read from the manufacturer, not inferred from a catalogue category, a terminal count, or a product name.**

---

## 2026-09-13 (10) — ✅ DECISION: J4 presence detection uses an independent COM–NC lever microswitch, not the jack. Firmware needs no change

**Decision (breadboard prototype scope):** keep the Switchcraft #11 as the audio jack and detect plug presence with a **separate Omron D2F-01L COM–NC lever microswitch** — the same element already designed into Phase 8 for the XLR. Likely to standardise across all three 1/4" positions. **Do not replace the #11s to get detection, and do not sense their TIP nodes.**

**The project already solved this exact problem once.** Runbook line 1565: *"Standard XLRs don't have a switch contact, so we use a small mechanical microswitch actuated by the inserted XLR shell."* The #11 turns out to be in the same category — an audio jack with no detect contact. The answer that was written for the XLR generalises, and it was in the runbook the whole time.

### The shipped firmware is already correct — verified, not assumed

With `COM → pin 16` (INPUT_PULLUP, 22 kΩ) and `NC → GND`:

| Lever | COM–NC | pin 16 raw | `raw_present` | `^ INVERTED(1)` | `present` | Meaning |
|---|---|---|---|---|---|---|
| released | closed | **LOW** | 1 | 1^1 | **0** | plug absent ✓ |
| pressed | open | **HIGH** | 0 | 0^1 | **1** | plug inserted ✓ |

`readJackInserted()` computes `raw_present = (digitalRead(pin) == LOW)` then `raw_present ^ inverted`, and `JACK_INSTRUMENT_DETECT_INVERTED` is already **1**. **No firmware change is required** — the polarity mechanism written for the assumed shunt topology happens to be exactly right for this one. Firmware `b32d04a` as running on the board is correct for this design.

### ADR-002 compliance, and it is not marginal

The detect path is `pin 16 → COM → NC → GND`. **It never touches an audio node**, so it imposes no DC loading requirement on the guitar input at all — the strongest possible form of compliance rather than a tolerable one. Closed-contact resistance is ~0 Ω (D2F initial contact resistance is order 100 mΩ), against the < 9.4 kΩ bound derived in 2026-09-13 (8). Margin of roughly five orders of magnitude.

### 🔴 Parts gate — enough to prove it, not enough to build it

**Exactly 1× Omron D2F-01L is specified** (runbook line 1583, in the Phase 8 figure). It appears in **no** parts table and **not** in Cup E, which lists only *"3× Switchcraft #11, 1× Neutrik XLR."*

- **The bench proof below needs one.** ~~and one exists. No purchasing blocks it.~~ **🔻 WITHDRAWN 2026-09-13 — see entry (11). "One exists" was unsupported and contradicted the sentence immediately above it. A part drawn in a design figure is not a part that was purchased. Assume D2F-01L on hand = 0.**
- **Standardising across three 1/4" jacks plus the XLR needs four.** Three more to buy. That is a procurement item, not a blocker on the next step.
- Using the Phase 8 unit for the Phase 5 proof consumes the XLR's switch. Acceptable while proving architecture; note it so Phase 8 is not later found short.

### Sequencing — electrical proof BEFORE mechanical integration

**Do not mount the switch yet.** The next step proves firmware + GPIO + detection topology with nothing mounted and nothing connected to J4:

1. Power OFF. Continuity-identify **COM** and **NC** on the D2F-01L: lever untouched ⇒ COM↔NC beeps; lever depressed ⇒ beep stops. Ignore NO. **The runbook cannot help here — line 2002 admits it lacks macro photos of the D2F-01L COM/NC/NO terminals**, so electrical identification is the correct method, not excess caution.
2. Two temporary connections only: `pin 16 → COM`, `GND → NC`. **Nothing connects to J4.** The audio path is untouched.
3. Power up, lever released ⇒ expect `raw=LOW inv=1 present=0`. Press ⇒ expect `JACK_CHANGED` and `raw=HIGH inv=1 present=1`. Release ⇒ back to LOW / present=0.

**This is a stronger checkpoint than mounting first**, because it isolates the electrical question from the mechanical one. If it fails, the fault is firmware/GPIO/topology with no mechanical variable in play.

### ⚠️ Hand-actuation does NOT close Phase 5

The sign-off is *"guitar plays through, detect events fire"*, and mechanical actuation by an inserted TS plug is part of the real feature. **A passing hand-press proves the architecture, not the phase.** Phase 5 closes only when inserting a plug actuates the lever and produces the transition. The mechanical problem — mounting the lever so a TS plug reliably presses it — is deferred, not solved, and is the harder half.

### On the withdrawn arithmetic

Retained, as recorded in 2026-09-13 (9). It remains a valid proof that a hypothetical TIP-shunted implementation would conflict with the high-impedance input requirement under this GPIO pull-up. What was lost is only the opportunity to demonstrate that mechanism on J4 — because J4 never contained the contact.

---

## 2026-09-13 (9) — 🔻 CORRECTION: the installed J4 has NO switched contact at all. Entries (7) and (8) reasoned about a topology this jack does not have

**Supersedes the J4 worked example in 2026-09-13 (7) and (8), and withdraws the planned SHUNT → pin 16 experiment.** Those entries' *general* reasoning survives; their premise about this specific part does not.

### The measurement

Power OFF, DMM continuity, nothing else changed. Evidence: `ai/evidence/2026-09-13-J4-continuity-identification.md`.

| Probe A | Probe B | Plug | Result |
|---|---|---|---|
| jack barrel/body | **lug #1** | none | **BEEP** |
| jack barrel/body | lug #2 | none | no beep |
| **lug #2** | **long spring** | none | **BEEP** |
| **lug #2** | **long spring** | **TS inserted** | **STILL BEEPS** |

**The last two rows are the decisive pair.** A shunt contact is *defined* by opening on insertion. This pair does not open. So, from the measurement alone and independent of any datasheet: **there is no switched contact among the probed terminals.** Lug #2 and the long spring are two parts of one conductor.

- **lug #1** = SLEEVE / GND
- **lug #2 + long spring** = TIP, one net
- **no shunt terminal**

**Relayed corroboration, not verified by me:** Switchcraft lists the **#11** as *"1/4" Mono 2 Conductor … Open Circuit"*, schematic *"Single Open"*; the shunted variant is a **different part number** (e.g. **12AW11**, *"Tip is Shunt"*). Recorded as a citation. The measurement does not depend on it.

### What I got wrong, and at what level

Entries (7) and (8) took the runbook's SVG at line 1105–1113 — *"SWITCH terminal — internally shorted to TIP ONLY when plug is OUT"* — as a description of the installed hardware, and reasoned forward from it. **The error was accepting a component description from a build document as as-built fact.** That is the same failure mode as the `MEAS` provenance lesson and the `RPT` tier discipline this project already committed to: *a document describing what a part does is not evidence that the part on the bench is that part.*

The arithmetic in (8) — 22 kΩ pull-up, < 9.4 kΩ required, ~1 MΩ wanted — **is still correct and still proves what it proved.** It was never about this jack specifically; it is about any GPIO pull-up detect sharing a high-impedance audio node. What is withdrawn is the claim that J4's SHUNT contact is the thing that would have violated it. **J4 has no SHUNT contact to violate it with.**

### The planned experiment is withdrawn — it cannot be performed

(7) and (8) proposed: wire SHUNT → pin 16 with the `col 30` → GND jumper fitted, confirm detect works, then remove the jumper and confirm it breaks. **There is no SHUNT to wire.** Lug #2 and the long spring are both TIP, so executing it as written would have put a 22 kΩ pull-up to 3.3 V **directly on the guitar signal node** — biasing it and loading it ~100× below TODO-23's target. The stop was correct.

Note what this costs: the mechanism demonstration in (8) is now **unavailable on this hardware**. The impedance conflict remains proven by arithmetic and unproven by experiment on this bench, and that gap should be stated honestly rather than quietly dropped.

### 🔴 The real blocker is parts, not wiring or firmware

The runbook's parts list (line 181) specifies **Switchcraft #11 ×10 for Phase 5 AND Phase 7** — instrument in, rig send, rig return TS. If the installed part is representative of all ten, then **none of the three 1/4" jacks in the design can report presence at all.** Phase 5's sign-off (*"detect events fire"*) and Phase 7's route matrix both depend on detect. **This is a procurement/design blocker, not a bench-technique problem**, and it was invisible while the runbook's switched-jack drawing was taken at face value.

**Phase 8 is unaffected, and is the pattern that works.** Its XLR detect uses a **separate COM-NC lever microswitch** wired pin 24 → GND (runbook line ~1638) — an independent contact, not a jack-integrated one. That trivially satisfies ADR-002: the detect path never touches an audio node, and its resistance to ground is ~0 Ω, far inside the < 9.4 kΩ bound. **An ADR-002-compliant solution was already in this project's own runbook.** Recorded as an observation; no selection is made here.

### Next action is documentation and a parts decision — nothing electrical

Do not modify J4. Do not connect pin 16. The open question is whether Phase 5 gets a switched jack (a different part number), an independent presence sensor on the Phase 8 model, or another topology — and that requires a parts decision that has not been made.

---

## 2026-09-13 (8) — 🔺 A DC reference on TIP cannot serve both jack detect and guitar input impedance. Quantified, and the option is dead

Addendum to 2026-09-13 (7). That entry listed "a DC reference on TIP chosen jointly with TODO-23's move toward 1 MΩ" as one of three possible production fixes. **That option is now ruled out, not merely doubted.**

### The pull-up value is a fact from the toolchain, not an estimate

`cores/teensy4/digital.c:180` configures `INPUT_PULLUP` as `IOMUXC_PAD_PUS(3)`. On i.MX RT1062 the PUS field is `0 = 100 kΩ pull-down, 1 = 47 kΩ pull-up, 2 = 100 kΩ pull-up, 3 = 22 kΩ pull-up`. So pin 16 is held up by **22 kΩ**, read out of the actual core source rather than assumed.

### The two requirements are mutually exclusive on the same node

A resistor from TIP to ground would have to pull pin 16 below V<sub>IL</sub> (0.3 × V<sub>DD</sub> ≈ 0.99 V) through the closed SHUNT contact, forming a divider against the internal pull-up:

| Internal pull-up | R<sub>TIP→GND</sub> needed for a guaranteed LOW |
|---|---|
| **22 kΩ** — what `INPUT_PULLUP` actually sets | **< 9.4 kΩ** |
| 47 kΩ | < 20.1 kΩ |
| 100 kΩ — the most favourable option the chip offers | < 42.9 kΩ |

But that resistor sits **on the TIP node**, so it *is* the input impedance the pickup sees. TODO-23 wants ~**1 MΩ**, and already judges the present ~100 kΩ too low.

**Even in the best case the two requirements are ~23× apart and pull in opposite directions.** In the configuration the firmware actually uses, ~106× apart. No single resistor value satisfies both, so this is not a tuning problem — it is a contradiction, and the option is closed.

### Terminology — pinned before it can go wrong

The installed jack is **TS, not TRS**. Its three terminals are **TIP — SLEEVE — SHUNT/SWITCH**. SHUNT is a normally-closed contact tied to TIP that a TS plug mechanically opens on insertion. **There is no ring conductor anywhere in the detect scheme.**

**Audit result: no existing error.** Every `ring` in `ai/` and `docs/asbuilt/netlist.md` is either a serial RX ring buffer or a genuine 3.5 mm TRS cable — `netlist.md:313` (`J1 tip/ring/sleeve`) and `:523` (taped-off right channel) are correct, because J1 *is* TRS. **This is preemption, not a correction.** The risk is real though: a legitimate `tip/ring/sleeve` for J1 sits close enough to the 1/4" jack discussion that a later reader could see "three terminals" and infer TRS. Use TIP/SLEEVE/SHUNT for J4 without exception.

### Surviving production options — all three keep detection off the audio node

1. **An isolated make-on-insertion detect contact** (e.g. the Cliff CL1384 the runbook dismissed at line 1221).
2. **A separate detection switch or contact independent of the audio tip.**
3. **A high-impedance buffered or comparator sensing scheme**, designed so the detection network does not load the guitar input.

The common property is what makes them viable: **the detection network is not galvanically on the signal node.** The #11's SHUNT contact is unusable for digital detect here precisely because it is tied to TIP, and TIP has a hard impedance requirement pointing the other way. **No decision is made here** — this entry closes one option and records why.

### The experiment in 2026-09-13 (7) is unchanged and still worth running

Leave the `col 30` → GND jumper fitted, wire SHUNT → pin 16, confirm empty = LOW / TS plug inserted = HIGH, then remove **only** that jumper and confirm detection disappears with pin 16 stuck HIGH. That demonstrates the mechanism experimentally. Note the jumper is ~0 Ω, far below the 9.4 kΩ bound, which is exactly why it works — and why nothing compatible with a guitar input ever could.

---

## 2026-09-13 (7) — 🔴 Phase 5 detect: the conductor was never run, AND the runbook's prescribed fix cannot work on this circuit

**Live null result.** `b32d04a` uploaded and running. Across **uptime 18 → 218 s, 45 diagnostic windows, continuous capture with no gaps**, covering a deliberate **empty → insert → remove → insert** sequence on the Switchcraft #11 instrument jack:

- **Zero `JACK_CHANGED` events.**
- **Zero `detail(change)` lines.** Only `detail(init)` exists.
- Pin 16 read `HIGH` at init and was never observed otherwise.

Evidence: `ai/evidence/2026-09-13-phase5-detect-null-result.log`.

**Two independent sources agree the detect conductor was never run.** The live GPIO behaves exactly like an open INPUT_PULLUP input. And `docs/asbuilt/netlist.md` documents the jack as tip-only — `1/4" JACK tip ─ col30 ─ C1 ─ col33 ─ jmp ─ col37` — with **no sleeve entry, no switch-lug entry, and Teensy pin 16 appearing nowhere in the document at all.**

This vindicates TODO-5's 🟡 wording exactly. *"Jack INSTALLED and signal path verified"* was precise and complete: the **signal** path was built, the **detect** path was not, and nobody ever claimed otherwise. The runbook requires three pigtail conductors — line 1129 *"red = tip, black = sleeve, green = switch"* — with line 1145 TIP → col 30, line 1149 **SLEEVE → GND rail**, line 1149 **SWITCH → Teensy pin 16**. One of three was built.

**The firmware is untestable, not failed.** `signalRouter_init()`/`update()` are live, all four pins were read, per-connector polarity applied, and the evidence format printed. Three of four inputs behave exactly as unwired pullup inputs should. There is no evidence against the code, and none for it either.

### 🔺 The prescribed fix does not work on this circuit — and the runbook's own table says why

The runbook's Phase 5 truth table (line 1118) states the problem itself:

| State | Switchcraft #11 SWITCH terminal | Firmware wants |
|---|---|---|
| No plug | shorted to TIP terminal | HIGH ✓ *"matches if we wire TIP to GND but TIP carries signal... so it doesn't ✗"* |
| Plug inserted | open (floats) | LOW — *"needs INPUT_PULLUP to pull down but it pulls up ✗"* |

It then concludes *"the cleanest fix is a one-line firmware invert"* and dismisses the Cliff CL1384 make-on-insertion alternative at line 1221 as unnecessary. **That conclusion does not follow from its own table.**

**Trace the actual circuit.** The #11's SWITCH lug shorts to **TIP** when empty and floats when inserted. TIP is `col 30`, and the as-built `SOURCE_IN` net is `col 30 · J4 tip · C1` — **C1 is a 10 nF ceramic** (`docs/asbuilt/netlist.md` line 95, tagged `PHYS`), which blocks DC, and `col 30` has **no other connection**. So with SWITCH wired to pin 16 and SLEEVE grounded:

- **Empty:** pin 16 → SWITCH → TIP → col 30 → C1 → *DC blocked, nowhere*. Pull-up wins ⇒ **HIGH**.
- **Inserted:** SWITCH open. Pull-up wins ⇒ **HIGH**.

**Pin 16 reads HIGH in both states. The pin never changes, so no value of `JACK_DETECT_INVERTED` can recover a transition from it.** An invert maps HIGH→0 or HIGH→1; it cannot manufacture a state change that the hardware does not produce. The grounding that the runbook's table assumes ("closed-to-tip-to-sleeve-to-GND", line 854) requires TIP to have a DC path to ground, and this circuit deliberately does not give it one — C1 is there precisely to block DC out of the guitar signal.

**Falsifiable prediction, and it is cheap to test.** The `col 30` → GND diagnostic jumper is **currently fitted** as one of the four outstanding deviations. That jumper gives TIP the missing DC path. So:

1. Wire SWITCH → pin 16 **now, with the jumper still fitted** ⇒ detect **should** work, empty = LOW, inserted = HIGH, and `JACK_INSTRUMENT_DETECT_INVERTED = 1` as currently shipped is **correct**.
2. Remove the `col 30` → GND jumper ⇒ detect **should break**, pin 16 stuck HIGH.

If both hold, the coupling is demonstrated rather than argued, and the design question is forced into the open instead of being discovered later as a regression.

**This is why the deviations must not be restored independently.** A diagnostic jumper that was scheduled for removal turns out to be load-bearing for a feature that has not been built yet. Removing it "to restore the baseline" would have broken detect before detect ever worked, and the failure would have looked like a firmware bug.

**What I am NOT claiming:** that grounding `col 30` is an acceptable production answer. It shorts the guitar signal to ground, which defeats the input entirely. The jumper is a diagnostic, it works for detect by accident, and the real fix is a design decision — a make-on-insertion jack (the CL1384 the runbook dismissed), a different detect topology, or a DC reference on TIP chosen jointly with TODO-23's move toward 1 MΩ. **That decision is not mine to make and is not made here.**

### Standing correction to the runbook

`docs/breadboard_bringup_v3.md` Phase 5 prescribes a fix its own truth table shows to be insufficient, and rejects the alternative that would have worked. The build guide should not be followed on this point without the circuit analysis above. Recorded here rather than edited into the runbook, which is a separate artifact with its own change discipline.

---

## 2026-09-13 (6) — ✅ TODO-43 CLOSED: the 19.4 dB was a 1× probe on a 10×-configured scope channel. No codec anomaly, no shield fault

**Matched-setting measurement.** Physical probe set to 10×, DHO804 CH1 probe ratio 10×, 10 mV/div, probe on the SGTL5000-side pad of the LINE-IN-L coupling capacitor, shield-local GND, tone and wiring otherwise untouched: **16.3 mV<sub>rms</sub> current, 16.3 avg, ~16.5 max, ~15.9 min, 989 Hz current / ~1.00 kHz average, clean sine, no clipping.**

**The arithmetic closes.** 16.3 mV<sub>rms</sub> × 2√2 = **46.1 mV<sub>pp</sub>**. Against `lineInLevel(5)` full scale of 1.33 V<sub>pp</sub>: 20·log₁₀(0.0461 / 1.33) = **−29.2 dBFS predicted**, against **−29.9 … −30.4 dBFS observed**. Agreement **0.7–1.2 dB** depending on window — the same order as the 1.3 dB that closed the 2026-09-07 (7) measurement on the old board.

### The complete chain

1. **Apparent anomaly:** scope reported 0.12–0.16 V<sub>rms</sub> at the codec input node while the ADC reported ~−30 dBFS, a ~19 dB gap.
2. **Cause:** the physical probe was **1×** while the scope channel was configured for a **10×** probe, so displayed voltage was ~10× the true voltage.
3. **Controlled correction:** switching the physical probe to 10× with the channel still at 10× yields 16.3 mV<sub>rms</sub> at the same node, same tone, same everything else.
4. **Independent consistency check:** 16.3 mV<sub>rms</sub> predicts −29.2 dBFS, consistent with the measured ~−30 dBFS.

**What this rules out, positively:** no ~19 dB codec conversion-gain anomaly, no 10:1 loss through the shield input network, no failed SGTL5000 configuration. The register dump (2026-09-13 (4), commit `d63a753`) and the datasheet verification (2026-09-13 (5)) were both correct and both necessary — they eliminated the codec so completely that the instrument became the only remaining suspect.

### ⚠️ I withdraw the counter-evidence I raised in 2026-09-13 (5)

That entry offered the 2026-09-12 (3) scope reading of **45.77 mV<sub>pp</sub> at `48e` agreeing with the ADC's −31.3 dBFS** as evidence that the scope was *not* reading 10× high in that session. **That was weak evidence and I should not have weighted it as I did.** The same session records a **grounded-probe floor of ≈32 mV<sub>pp</sub>**, so a 45.77 mV<sub>pp</sub> reading is roughly 1.4× the floor — mostly instrument noise — and entry 2026-09-12 (3) already withdraws floor-contaminated readings from that session as uninterpretable. A measurement that is largely floor cannot discriminate a 10× scale error. The hypothesis was better supported than I credited.

**What that does not license:** it still does not *prove* the mismatch was in place on 09-12. No matched-setting measurement was taken that day. Any 09-12 absolute voltage remains reconstructed, not measured.

### 🔻 Historical correction — the 41B stimulus figure is invalid as an absolute voltage

TODO-41B and journal 2026-09-13 (1)/(3) record the stimulus as **0.141 V<sub>rms</sub> at `48e`** (0.140 avg / 0.143 max). That was a scope reading taken under the mismatched configuration. **Its absolute value is ~10× high and should be marked invalid.** Reconstructed true value: **≈0.014–0.016 V<sub>rms</sub>**, explicitly reconstructed — there is no matched-setting measurement at `48e`.

**41B's PASS is unaffected.** 41B's claim is about I²S corruption, and it was established from the ADC data itself: 324/324 clean windows, zero detector-v1 outliers, with SOURCE at −29.88 dBFS mean against a post-stack idle floor of −55 dBFS. The stimulus was genuinely present and genuinely strong relative to the floor. Absolute volts never entered that claim.

**But there is a consequence that is not obvious and should not be lost.** The stated *intent* of 41B was to reproduce the 2026-09-07 (7) condition of 0.143 V<sub>rms</sub> — a valid **DMM** measurement that produced −9.0 dBFS. The operator set the phone so the *scope* read ~0.141, which under the mismatch set the true level to ~0.014 V<sub>rms</sub>. **41B therefore ran roughly 20 dB below the level it was designed to test.** The planned margin was stated as ≈51 dB above the idle floor; the margin actually achieved was ~25 dB. Ample, and the PASS holds — but if I²S corruption were ever level-dependent, **41B did not probe the level it intended to probe**, and a future level-dependence question cannot cite 41B as having covered it.

### The one absolute voltage anchor that survives

**2026-09-07 (7)'s 0.143 V<sub>rms</sub> was a DMM reading** and is unaffected by probe ratio. It gave −9.0 dBFS against −10.3 predicted. Today's 16.3 mV<sub>rms</sub> gives ~−30 dBFS against −29.2 predicted. Both are consistent with a correctly-operating codec at two levels ~19 dB apart — which is simply the phone level having been set ~19 dB lower, by the operator, while trusting a 10×-inflated display.

### Standing lesson

**Record the probe attenuation setting — both the scope channel ratio and the physical probe switch — with every scope measurement, the same way stimulus conditions are recorded with every result.** This investigation spent a firmware diagnostic, two datasheet audits, a full register readback and a physical dissection of the shield input network chasing a number whose scale was never written down. The 2026-09-13 (2) lesson about unrecorded stimulus conditions and this one are the same lesson.

---

## 2026-09-13 (5) — 🔺 TODO-43: the lineInLevel arithmetic checks out two independent ways. The instrument that produced the input number changed at exactly the point the discrepancy appeared

**The proposal under test was that our expected −10 to −12 dBFS is the wrong number.** It is not. It survives two independent checks, so the suspicion moves off the expectation and onto the measured voltage feeding it.

### The expectation is sound

`control_sgtl5000.cpp` carries the table as a comment headed *"Actual measured full-scale peak-to-peak sine wave input for max signal"*, level 5 = **1.33 V<sub>pp</sub>**. That is PJRC bench data, so it could in principle be wrong on its own. It is not independent of the datasheet, though, and that is what makes it checkable: the datasheet defines ADC_VOL steps as 1.5 dB and full scale at code 0 as 3.12 V<sub>pp</sub>. Code 5 ⇒ 3.12 / 10^(7.5/20) = **1.32 V<sub>pp</sub>**. The measured table and the datasheet's own gain law agree to ~1 %. `ADC_VOL_M6DB = 0`, so no additional −6 dB is in play.

### Nothing else in the path scales the signal

- Firmware: `s_mixer_src.gain(0, 1.0f)`, all other slots 0.0f ([audio_capture.cpp:296](audio_capture.cpp#L296)). Unity. The peak detector hangs directly off that mixer output.
- Codec digital path: `CHIP_SSS_CTRL = 0x0010` — ADC→I2S direct, the DAP is powered but **not in the routing path**. `CHIP_I2S_CTRL = 0x0030` — 16-bit, 64×Fs, I2S format. `CHIP_DAC_VOL` is DAC-side only and cannot touch the ADC.
- Every register readback matches what the library wrote, so the I²C write path is landing (see 2026-09-13 (4) and commit `d63a753`).

### The observation that reframes this

The two anchor measurements were **taken with different instruments**, and the discrepancy appeared exactly when the instrument changed.

| Date | Node | Reading | Instrument | ADC | Agreement |
|---|---|---|---|---|---|
| 2026-09-07 (7) | 48e / LINE-IN-L pad | 0.143 V<sub>rms</sub> | **DMM** — stated verbatim: *"where the DMM read 0.143"* | −9.0 dBFS | **1.3 dB** |
| 2026-09-12 (1) | 48e | 0.141 V<sub>rms</sub> | **scope** — reported as *"0.140 avg, 0.143 max, 995–997 Hz, clean sine, no visible clipping"*; avg/max/min statistics, a frequency readout and waveform shape are scope outputs, not DMM outputs | −29.88 dBFS | **19.4 dB** |

**A 10× probe-attenuation mismatch predicts the observed number almost exactly.** If the scope is configured for a 10× probe while a 1× probe is attached, it displays ten times the true voltage. Today's codec-side pad reading of ~0.150 V<sub>rms</sub> displayed would then be 0.0150 V<sub>rms</sub> true = 0.0424 V<sub>pp</sub>; against 1.33 V<sub>pp</sub> full scale that is 0.0319 ⇒ **−29.9 dBFS predicted against −30.0 dBFS observed.** The header reading of ~0.123 V<sub>rms</sub> gives −31.6 dBFS predicted against −29.88 observed, a 1.7 dB agreement.

### ⚠️ Real counter-evidence, recorded so it is not lost

2026-09-12 (3) records a **scope** reading of 45.77 mV<sub>pp</sub> at 48e agreeing with the ADC's −31.3 dBFS, which back-converts to 36.2 mV<sub>pp</sub>. Had the scope been reading 10× high *then*, the true value would have been 4.58 mV<sub>pp</sub> and the ADC would have shown roughly −51 dBFS. It showed −31.3. **So the scope was not reading 10× high in that session.** For the hypothesis to hold, the probe or its menu setting must have changed between that session and the shield-probing work today — which is possible, since the probe was physically relocated to the shield in between, but is not established.

### This is not a conclusion

Two readings agreeing to 0.1 dB is suggestive and nothing more; the header figure agrees to only 1.7 dB, and the counter-evidence above is genuine. The instrument change is also **confounded with the hardware change** — new Teensy and new shield landed between 09-07 and 09-12 — exactly the TODO-41A confound in a new place. What is established is narrower: *the expectation is sound, the codec is configured correctly, the firmware is unity-gain, and the one input to the arithmetic that has never been cross-checked between two instruments is the analog voltage.*

### The discriminator, and why it is the cheapest one available

**Read the scope's probe-attenuation setting and compare it to the switch on the probe body**, then **measure the same codec-side pad with the DMM in AC volts.** No wiring change, no power cycle, no firmware change, and the DMM has no attenuation setting to get wrong. It also happens to be the instrument that historically agreed with the codec to 1.3 dB.

- DMM reads ~15 mV<sub>rms</sub> where the scope reads ~150 → the scope is the fault, the codec is correct, and TODO-43 closes as a measurement error.
- DMM reads ~150 mV<sub>rms</sub> too → the scope is exonerated, both instruments agree against the codec, and TODO-43 becomes a genuine codec-level anomaly worth escalating.

Either outcome closes a branch. **Do not probe anything new until this is done** — every deeper probe point inherits the same unverified voltage scale.

---

## 2026-09-13 (4) — ⚠️ Lesson: a clean compile is not verification that a diagnostic decodes correctly

**What happened.** While writing the read-only SGTL5000 register dump (TODO-43, commit `a298f1c`) I got two bit positions wrong in my own decode: `REFTOP_POWERUP` and `HEADPHONE_POWERUP` were both read from `CHIP_ANA_POWER` bit 4, and `CHIP_DIG_POWER`'s ADC/DAC were placed at bits 6/5 instead of 5/4. Then a patch intended to fix them **failed silently** on a string-escaping error inside a heredoc, and the compile I ran afterwards passed — against the *uncorrected* file.

**Why this matters more than the bug.** Every field in a register dump is a bit-shift of a value the compiler cannot check. `(anap >> 4) & 1` and `(anap >> 5) & 1` are both perfectly valid C. A diagnostic can therefore be 100% compilable, 100% read-only, produce plausibly-shaped output, and still be **confidently wrong** — which is strictly worse than having no diagnostic, because it manufactures evidence. This project has already had to withdraw several claims (see 2026-09-12 (2), and the D2/OPA_BIAS gradient withdrawal); a mis-decoded register would be a much harder withdrawal to catch, because nothing about the output would look anomalous.

**What actually served as verification, and what did not:**
- ❌ *Compiling clean* — proved nothing about correctness here, and in the failed-patch window actively misled: it was a green light on a file that had not changed.
- ❌ *Output looking reasonable* — every wrong decode still printed `0` or `1`.
- ✅ *Reading the corrected source back off disk* after patching, rather than trusting the patch tool's exit status.
- ✅ *Checking each bit position against the NXP SGTL5000 datasheet field map independently of the code* — `CHIP_ANA_POWER`: LINEOUT b0, ADC b1, DAC b3, HEADPHONE b4, REFTOP b5, VAG b7, VCOAMP b8; `CHIP_DIG_POWER`: I2S_IN b0, I2S_OUT b1, DAC b4, ADC b5.
- ✅ *Grepping the diagnostic block for `.write(`* (result: 0) to prove the read-only property structurally, not by intention.
- ✅ *Compiling with the flag OFF and comparing to the pre-change baseline* — FLASH 154240 / RAM1 214880, byte-identical, which proves clean removability (a different claim from correctness, and worth keeping separate).

**Standing rule for this project going forward:** the dump prints **raw hex alongside every decoded field**, deliberately. If a decode bug survives all of the above, the raw register value in the log lets any future reader reconstruct the truth independently. Never log a decoded field without the raw value it came from.

**Next session should know:** the dump is on hardware as of this entry, captured in `ai/evidence/2026-09-13-sgtl-register-dump.log`. Treat the decoded lines in that log as *derived*; the five raw values are the evidence.

---

## 2026-09-13 (3) — ✅ TODO-41B PASS: 324/324 clean windows, zero detector-v1 outliers on either node across 26.9 minutes of continuous stimulus

**TODO-41B — PASS.** Under the new native Teensy 4.1 + PJRC Audio Shield Rev D stacked configuration, with a continuous external ~1 kHz stimulus applied through the real instrument-input analog path, **324 diagnostic windows spanning 26.9 minutes contained zero outliers on either SOURCE_NODE or RETURN_NODE under Outlier detector v1.** All 324 windows were clean, with zero clipping events and no quarter-to-quarter emergence of corruption. This establishes the **post-stack stimulated reference** for I²S integrity under the tested conditions.

**Deliberately NOT concluded: "the stack fixed the corruption" or "the old Teensy was damaged."** Both physical hardware and topology changed together (the TODO-41A confound). What is established is stronger than a hypothesis and narrower than causality: **the current assembled system does not reproduce the corruption under this test.**

### Claim 1 — stimulus validity

Phone → USB-C adapter → **real 1/4" instrument jack**, 1 kHz L+R, **0.141 V<sub>rms</sub> measured at `48e`** with the board powered (0.140 avg, 0.143 max, 995–997 Hz, clean sine, no visible clipping). Path: jack → C1 → OPA1642 → C2 → `48e` → LINE-IN-L. SOURCE observed at **−29.88 dBFS mean** (−30.4 … −28.9), raw |max| 1179 counts. **The test was genuinely driven for its full duration.**

### Claim 2 — corruption result

| | |
|---|---|
| Windows analysed | **324** (uptime 630 → 2245 s, 26.9 min) |
| Samples evaluated | **9 720 per node** (10 368 captured; 2/window have no 2nd difference) |
| SOURCE outliers/window | **0.000 — total 0** |
| RETURN outliers/window | **0.000 — total 0** |
| Completely clean windows | **324/324 = 100.0 %** |
| Worst window | **0 of 30 evaluable**, both nodes |
| Clip events | **0 (0.0 %)** |

Quarterly bands all **0.000/win** — 81 windows each, no drift. That matters: the original fault wandered 3.4× on its own (journal 2026-09-07 (1)), so a drifting rate would have surfaced here.

Housekeeping steady throughout: block period **46.43 ms mean** (46.3–46.7), `AudioMemoryUsageMax` pinned at **19**, `TF clamped bins` constant at 3 of 512.

### Claim 3 — control-channel behaviour

**RETURN averaged −66.22 dBFS during 41B** (−67.4 … −64.7), raw |max| 18 counts. **There was no evidence of a stimulus-correlated RETURN rise; RETURN remained at approximately the established post-stack idle-floor region. Any crosstalk is below what this measurement can resolve from the RETURN noise floor.**

*(Wording note: an earlier draft said RETURN was "against its established post-stack idle floor of −65.3 to −65.5." That turned two means from different idle configurations into artificial bounds. Corrected.)*

### 🔓 Follow-up required — OPEN, and it does not downgrade 41B

**0.141 V<sub>rms</sub> measured at `48e` → −29.88 dBFS mean SOURCE**, against −10.5 dBFS predicted from `SGTL5000_LINE_IN_LEVEL = 5`. A **19.4 dB** discrepancy (refined from a single-window 20.2 dB). **No explanation attached.** This is now an excellent reference datum: a 324-window mean on the current stacked system, not a one-window reading.

Next test: 48e referenced to breadboard GND, then LINE-IN-L referenced to the **shield's own** GND pad — each measurement to its own local ground, per the 33.1 dB lesson of 2026-09-12 (3).

### 📦 Reproducibility — the point of this entry

**Committed with the result:** the raw serial log (`ai/evidence/2026-09-13-41B-capture.log.gz`, 542 054 B raw), the stimulus conditions, the frozen **Outlier detector v1** criterion, and the analyser itself (`tools/analyze_corruption.py`).

**Run D is retired as a quantitative benchmark.** It remains historical evidence that corruption existed and motivated the DOUT reworks — but it recorded **neither its stimulus level nor its outlier criterion**, so its numbers (5.95 / 24.72 / 8.54 / 0.00) cannot be recomputed by anyone. They still drove three reworks and a hardware-damage hypothesis. **That is the failure mode this entry exists to not repeat.**

### Acquisition note

Two acquisition-script attempts failed before data collection began (`nohup` child termination; macOS `timeout` unavailable). Neither altered stimulus, wiring, power state, or firmware, **so they are tooling events, not bench events.**

---

## 2026-09-13 (2) — Front end reconnected on the stack: connecting it now costs 5.07 dB instead of 25.7 dB. And run D's stimulus level turns out never to have been recorded

### Measured — 24 idle windows, uptime 40–155 s, `48e` → LINE-IN-L reconnected, stack ground path untouched

| | n | mean | range |
|---|---|---|---|
| SOURCE | 24 | **−60.32 dBFS** | −58.5 … −62.3 |
| RETURN | 24 | **−65.50 dBFS** | −64.3 … −66.2 |

| Topology | LINE-IN-L disconnected | front end reconnected | **cost of connecting** |
|---|---|---|---|
| Flying wires | −57.0 dBFS | −31.3 dBFS | **25.7 dB** |
| **Native stack** | −65.39 dBFS | **−60.32 dBFS** | **5.07 dB** |

**Stated as measured, and no further:** *with the native stack, reconnecting the analog front end raises SOURCE by ≈5.1 dB, versus ≈25.7 dB in the old flying-wire configuration.* **The reason is still not isolated**, because topology and physical hardware changed together (TODO-41A confound). This is not written as "hypothesis confirmed."

**RETURN is statistically unmoved** by the reconnection — −65.50 against −65.26 disconnected. Whatever the residual 5.07 dB is, it enters through the SOURCE path specifically.

**⚠️ Correction to an earlier reading of the old data.** A draft of this analysis said that under the old topology connecting the front end "dragged both channels". **It did not.** RETURN's *peak* read −56.3 / −60.9 / −58.8 / −59.1 across the old conditions and never tracked SOURCE's 34 dB swing. What correlated was the *raw waveform shape* at roughly 30× amplitude ratio — a different observation from the floor moving. What the stack did is lower the RETURN floor ≈6 dB outright.

**Residual, stated as expectation not finding:** 5.07 dB above a −65.4 floor is an ordinary amount for attaching a 100 kΩ-referenced JFET front end on a flying LINE-IN-L wire — source impedance and lead dress. Nothing has measured it, so it stays an expectation.

### 🚨 Documentation gap: run D's stimulus amplitude was never recorded

Preparing to "re-establish the exact previously documented Run-D stimulus level" found there is no such record. Entry 2026-09-07 (6) documents interconnect state, window counts, outliers/32, clean %, worst window and `+0 dBFS %` — **and no SOURCE level, no V<sub>rms</sub>, no tone amplitude.** The nearest figure, "~−39 dBFS", appears only in that entry's *next-steps* line as a back-reference to 2026-09-06 (1), a different run under a different analog configuration.

**It is worse than merely missing.** Run D predates the 2026-09-07 (7) headphone-jack discovery, so its stimulus reached the board through the **wrong jack** at roughly 0.027 V<sub>rms</sub>. **Reproducing run D exactly would mean deliberately recreating a known-faulty analog path.**

**Decision: use 0.143 V<sub>rms</sub> at LINE-IN-L**, which is documented, reproducible, and previously produced **−9.0 dBFS** through the correct analog path with the `lineInLevel 5` arithmetic agreeing to 1.3 dB (entry 2026-09-07 (7)).

**Corruption detection does not depend on matching run D's level.** Corruption presented as full-scale impulses ~41 dB above the signal. At −9 dBFS against a −60 dBFS floor the margin is ≈51 dB — **more than run D had.**

**Lesson, and it generalises:** run D was treated as the project's reference validation for six days, and it is not reproducible, because the one parameter needed to repeat it was the one nobody wrote down. **A validation run's stimulus conditions are part of its result.** Record level, frequency, source and injection point alongside every pass/fail figure, or the pass cannot be repeated — only remembered.

---

## 2026-09-13 (1) — TODO-41A PASS: native stack takes BOTH channels to ≈−65.3 dBFS and collapses the asymmetry from 29.4 dB to 0.13 dB. First hardware evidence for the Pi link and for TODO-29

**Hardware:** new Teensy 4.1 + new Audio Shield Rev D, soldered as a native stack (shield → Teensy → breakout). Flashed with **`c18fac7`** — the first upload since `e6daac8`, so TODO-29's clamp marking and the whole `c64e876` architecture reach hardware for the first time. Pre-power 3V3→GND resistance check clean. **LINE-IN-L deliberately left disconnected**, so this isolates the effect of the stack itself.

### The result — 8 consecutive windows, uptime 20–55 s

```
SOURCE:  -65.2 -65.2 -65.7 -65.7 -64.7 -65.7 -65.2 -65.7   mean -65.39
RETURN:  -65.2 -65.2 -65.2 -65.2 -65.7 -64.7 -65.7 -65.2   mean -65.26
```

| Topology | SOURCE | RETURN | Δ |
|---|---|---|---|
| Flying wires, LINE-IN-L → breadboard GND | −31.9 | −60.9 | 29.0 dB |
| Flying wires, floating | −57.0 | −58.8 | 1.8 dB |
| Flying wires, → shield GND | −65.0 | −59.1 | −5.9 dB |
| **Native stack** | **−65.39** | **−65.26** | **0.13 dB** |

**The channel-dependent disturbance is gone.** And **RETURN improved ≈6 dB**, which nothing in the entire flying-wire investigation moved — it sat near −59 dBFS through every condition. Both inputs getting quieter *together* is the signature of a topology change rather than a per-channel fix.

Raw data is ±15–16 counts on both channels, sample-for-sample near-identical. −65.4 dBFS ⇒ 17.6 counts, so the peak metric and the raw dumps agree.

**⚠️ Language discipline — this is the post-stack SYSTEM idle floor, NOT "the codec's own floor."** An earlier draft said the latter. **The SGTL5000 has not been isolated**, so nothing here establishes its intrinsic noise floor; what is measured is the whole assembled system at idle with LINE-IN-L open.

### 🚨 The confound, stated because it is real and easy to lose

**Both boards are new.** This run changed *two* things at once: the interconnect topology (flying leads → native stack) **and** the physical hardware (new Teensy, new shield). Journal 2026-09-07 (4) hypothesised pin-8 output contention damage on the *old* Teensy while `RA8875_RESET_PIN` was still 8; that hypothesis was weakened by scope evidence but never disproved. **New silicon eliminates any such damage, so "the stack fixed it" and "the old hardware was degraded" are not separated by this measurement.**

It does not diminish the result — the configuration works, which is what matters for proceeding — but the *causal* claim must stay conditional. If an explanation is ever needed, the only clean test is re-creating the flying-wire topology on the new boards, which is not worth the disturbance now.

### First hardware evidence for `c64e876` — the Pi link, measured rather than predicted

| Metric | Value |
|---|---|
| Live frames | **1077 sent, 0 dropped**, longest drop streak 0 |
| Call time | **max 283 µs**, mean 280.7 µs |
| TX room min | 2482 B of 4096 B |
| Frame size | 1689 B framed, 4:1 decimation, 128 live bins, protocol v2 |
| Block period | **46.3 ms throughout — identical to every pre-stack run** |

**The T1 prediction was ~33.8 ms of blocking write time per frame against a 46.3 ms block period. Measured: 283 µs.** Two orders of magnitude below the prediction, and acquisition timing is unmoved. The non-blocking policy and the `addMemoryForWrite()` 4 KB buffer both do what entry 2026-09-11 (2) claimed. **This does not close T1** — the formal acceptance is a controlled comparison against the `_NONE` control using `timing_probe`, with skipped blocks reading zero. But it is the first evidence, and it points the right way.

**`TF clamped bins: 0 of 512`** — TODO-29 on hardware for the first time. The line reports honestly instead of printing a rail as data.

**Loop rate is the new normal: ~1.50 M iterations/s, down from ~2.15 M.** That is the Pi link work and is irrelevant at this margin. Recorded so it is not mistaken for a regression later.

### ❌ TODO-41B is NOT satisfied by this, and must not be promoted

The instruction to *"run the same I²S validation that gave 360/360 clean windows"* while *"leaving LINE-IN-L disconnected"* cannot both hold: run D (journal 2026-09-07 (6)) injected a 1 kHz tone **through** LINE-IN-L.

What the idle data supports: across 8 windows both channels stayed inside ±16 counts with **no impulses, no outliers, no clip events**. Against a floor that low a corrupted I²S word would be unmissable — arguably a more sensitive corruption check than run D's, which had a full-scale tone to hide in. **It is still not the same test.** Run D's claim is about a *stimulated* pipeline over ≥300 windows, and only that test can be compared to it.

**Split recorded as TODO-41A (PASS) and TODO-41B (NOT YET RUN)** specifically so the idle result cannot drift into being cited as a run-D pass.

---

## 2026-09-12 (4) — Stacking approved on a verified pin map. `AUDIO_SHIELD_STACKED` guard added, and a stale comment that was hiding the pin-10 conflict corrected

**No hardware changed by this session.** Compile proof only. The physical stack is being built at the bench; this entry records the verification that authorised it and the source change that protects it.

### The pin-map question, settled against the active tree

An assisting session flagged two potential conflicts from project PDFs that predate commit `eeaec99` and the `DISPLAY_TARGET` work. **Both dissolve against the current source:**

| Claim from the PDFs | Active tree |
|---|---|
| "RA8875 uses 8–10 for display signals" | **`RA8875_RESET_PIN` is 5, not 8.** Moved 8→5 in `eeaec99` *because* pin 8 is I2S RX_DATA0 (TODO-24, already closed in source) |
| "pin 10 conflicts with the shield's SD CS" | **True only when `DISPLAY_TARGET == RA8875`.** `RA8875_CS_PIN` is referenced only inside `display_engine.cpp`, which is wholly wrapped at lines 46–820. Under `_PI` (current) or `_NONE` that unit is not compiled and **no Adafruit library is linked** — verified from `arduino-cli compile -v`. Nothing configures or drives 5, 9 or 10 |

Confirmed correct: calibration uses `SD.begin(BUILTIN_SDCARD)` — the Teensy 4.1 SDIO socket — so the shield's SPI SD path is irrelevant to the analyzer's storage.

**Verdict: connect all pins.** The shield's 7, 8, 18, 19, 20, 21, 23 are exactly what we want connected. 14, 16, 17, 22, 24 have no Rev D counterpart. 10–13 are free under the production build.

**One caveat recorded rather than fixed:** pin 15 / A1 shares a trace with the Rev D's *unpopulated* VOL pad. A stub, not a driver. `RELAY_RETURN_PIN` stays on 15; relocating it for an unpopulated pad would be motion without benefit, and 15 is also analog-capable.

### 🔧 The stale comment was the real finding

`config.h` stated: *"The Teensy Audio Shield uses I2S and I2C. **It does NOT use SPI.** The SPI bus is therefore free for the RA8875 display and microSD."*

**That is false for a stacked Rev D**, which carries its own microSD on SPI with CS on pin 10. It was harmlessly true while the shield was connected by selective flying wires — only the pins we chose were live — and becomes false the moment every populated header position is connected.

**This is the exact shape of defect that has cost this project the most: a premise that is true of the current topology, written as though it were true of the design.** Corrected in place with the reason stated, not silently.

### `AUDIO_SHIELD_STACKED` — a topology fact, enforced

```
#define AUDIO_SHIELD_STACKED 1
#if (DISPLAY_TARGET == DISPLAY_TARGET_RA8875) && AUDIO_SHIELD_STACKED
#error "RA8875_CS_PIN (10) collides with the stacked Audio Shield's microSD CS..."
#endif
```

Deliberately **not** a blanket `#error` on `_RA8875`: the RA8875 is still a legitimate debug backend on a flying-wire rig, and breaking it outright would trade one wrong assumption for another. The flag encodes the *hardware topology*, so the error fires only on the combination that is actually unsafe.

**Proof — all three cases exercised, not assumed:**

| Build | Result |
|---|---|
| `_PI` + stacked | compiles, FLASH 154 240 / RAM1 214 880 |
| `_RA8875` + stacked | **fails with the intended message** |
| `_RA8875` + not stacked | compiles, FLASH 159 876 / RAM1 220 928 |

### 🔺 Stacking is a ground change, and that may matter more than the pin map

Entry (3) measured **33.1 dB** of improvement from moving the codec's ground return off the breadboard rail onto the shield's own GND pad. **Stacking replaces that flying ground wire with header pins straight into the Teensy's ground plane** — the shortest possible local return, which is precisely what that measurement called for. Same class of structural fix as the short-lead I²S change in entry 2026-09-07 (6).

**Two consequences, both of which must be honoured:**

1. **The −31.49 dBFS pooled baseline and the entire four-condition elimination become HISTORICAL the moment the stack is soldered.** They describe a board with a flying ground return that will no longer exist. Do not compare post-stack readings to them as though the topology were unchanged.
2. **LINE-IN-L still arrives by flying wire from the breadboard front end.** Stacking bonds shield GND and breadboard GND through the header and breakout — far lower impedance than the flying wire, but they become one net. **That could resolve TODO-40's mechanism or relocate it, and only a measurement will say which.** The provisional wiring rule on TODO-5 stands until then.

### The sequence, and why it is worth stating before 40+ joints

Stack → **immediately re-run the validation that produced 360/360 clean windows** → **take a fresh SOURCE idle baseline** → only then change anything else. Known-good flying-wire → native stacked → validated → new baseline. That preserves the ability to attribute a regression to the stack rather than to whatever came after it, which is the discipline that eventually solved the I²S corruption.

---

## 2026-09-12 (3) — ✅ THE GROUND-RETURN PATH IS THE MECHANISM. Moving only the return point, breadboard GND → shield GND, improves SOURCE by 33.1 dB

**Observed.** With `48e` disconnected, grounding LINE-IN-L to **breadboard GND** produced **≈−31.9 dBFS**, while grounding the same LINE-IN-L pad with a short jumper to the **Audio Shield's own GND** produced **≈−65.0 dBFS**. **Moving only the return point improved SOURCE by 33.1 dB.**

**Inference.** The elevated SOURCE floor depends on the **external ground-return path**. It is not caused merely by terminating LINE-IN-L, and not by the front-end signal source itself.

**Still unresolved.** Whether the mechanism is an actual breadboard↔shield **ground-potential difference**, **loop-area pickup**, or some combination. This test does not separate them — both predict this result.

### The four codec-input states

| LINE-IN-L | 48e | n | mean SOURCE | vs RETURN |
|---|---|---|---|---|
| Driven by front end | connected | 5 | −31.3 dBFS | +29.4 dB |
| Bare jumper → **breadboard** GND | disconnected | 5 | −31.9 dBFS | +29.0 dB |
| Floating | disconnected | 5 | −57.0 dBFS | +1.8 dB |
| **Short jumper → shield's OWN GND** | disconnected | 5 | **−65.0 dBFS** | **−5.9 dB** |

Readings for the fourth state: **−66.2 / −64.3 / −65.2 / −64.3 / −65.2 dBFS**; RETURN −58.5 to −59.7, mean −59.1.

**The termination impedance is identical in states 2 and 4** — a wire to ground in both. Only the ground it returns to changed.

### ❌ Candidate (3) from entry (2) is dead

Entry (2) listed a third mechanism: that grounding LINE-IN-L drags the SGTL5000 input outside its common-mode window around VAG. **A shield-local ground would do that just as thoroughly, and instead produced the quietest reading of the entire investigation.** Withdrawn. The candidate set is now (1) ground-potential difference and (2) loop-area pickup.

### Two supporting observations — recorded as supporting, not as proof

1. **SOURCE became ≈5.9 dB quieter than RETURN** — the first inversion of the asymmetry all session. Consistent with SOURCE being properly terminated to local ground while RETURN floats. Raw dumps: SOURCE spans ≈±10 counts, RETURN ≈±35.
2. **The prior SOURCE/RETURN correlation disappeared.** Through every earlier condition the two channels tracked in sign and direction, breaking at the same sample index. In these five windows they are independent — at uptime 280 s RETURN sweeps −36 → +20 while SOURCE stays flat inside ±8.

Observation 2 is the more interesting of the pair: the correlation was flagged in entry (2) as supporting-not-proof of a shared disturbance, and it now behaves exactly as that hypothesis predicts once the shared path is removed. **That is a successful prediction rather than a post-hoc fit — but it remains corroboration, not proof.**

### 🔧 Provisional design rule, derived from measurement

> **Codec analog input returns should reference the Audio Shield ground locally. Do not route the return through the breadboard ground path until the ground-path mechanism is fully characterised.**

**Provisional** is the operative word: the rule follows from a 33.1 dB measured improvement, but the underlying mechanism is not yet identified, so the rule states what to do and not yet why. Applies from Phase 5 onward — recorded on TODO-5 and TODO-40.

### The discriminator, and why it is now interpretable

**Scope directly between breadboard GND and the Audio Shield GND pad** — same short-ground-spring setup, same settings, against the **recorded ≈32 mV<sub>pp</sub> probe floor**. A real low-frequency potential difference confirms (1); a reading indistinguishable from the floor points at (2). That control is what makes this measurement meaningful, and its absence is what made the earlier 31 → 38 → 46 mV<sub>pp</sub> sequence uninterpretable.

### Bench state

Still four deviations from the −31.49 dBFS pooled baseline: `48e` lifted · LINE-IN-L now grounded **to shield GND** · J2 removed · `col 30` → GND jumper fitted. Restore and re-baseline before any reading is compared to it.

---

## 2026-09-12 (2) — CORRECTION to entry (1): grounding LINE-IN-L reproduces the floor with the front end disconnected. "The codec is exonerated" is withdrawn; the proven claim is narrower

**Entry (1) concluded that the elevated SOURCE floor is delivered by the analog front end and that "the codec, its routing and the digital capture path are exonerated."** A third codec-input state was then measured and **that conclusion does not survive it.**

### The three states

| LINE-IN-L condition | 48e | SOURCE |
|---|---|---|
| Driven by front end | connected | **−31.3 dBFS** |
| **Floating** | disconnected | **−57.0 dBFS** |
| **Tied to GND by a bare jumper** | **disconnected** | **−31.9 dBFS** |

Readings for the third state: **−31.9 / −31.9 / −32.0 / −31.9 / −31.9 dBFS**, RETURN −60.8 to −61.1.

**A plain wire to ground reproduces the level to within 0.6 dB of the front-end-driven case, with the front end physically removed.** The front end therefore cannot be the source. Entry (1)'s inference was correct that the noise arrives *through* the LINE-IN-L connection and wrong about what supplies it.

### What is actually proven, stated narrowly

> **The elevated SOURCE reading appears whenever LINE-IN-L is given an external low-impedance connection — even to ground. It largely disappears when LINE-IN-L is left floating.**

That is the whole of it. **"The codec is exonerated" is withdrawn.** The codec's behaviour when its input is externally connected versus floating is now squarely inside the suspect set, not outside it.

**Supporting evidence, and labelled as supporting rather than proof:** SOURCE and RETURN track each other in sign and direction across all five windows, and in the uptime-130 s window both break downward at the *same sample index* — with nothing connected to RETURN at all. SOURCE runs ≈30× RETURN, and 30× is 29.5 dB, which is the SOURCE/RETURN asymmetry itself. That is consistent with one common disturbance coupling ~30× harder into the input that has a conductor on it. **It is consistent with a ground-potential difference; it does not establish one.**

### Candidate mechanisms — three, none established

1. **Ground-potential difference** between breadboard GND and the Audio Shield's analog ground reference. Tie LINE-IN-L to breadboard ground and the ADC, referenced to the shield's ground, sees the difference between them.
2. **Loop-area pickup.** Both the front-end case and the ground-jumper case share a *wire*, and a wire from LINE-IN-L out to breadboard GND and back through the shield's ground return encloses area. The floating case encloses none. This is a different mechanism from (1) and is not distinguished by any measurement taken so far.
3. **Codec input condition.** If LINE-IN-L is DC-coupled to the SGTL5000 pin on the shield, tying it to GND forces the ADC input toward 0 V and outside its expected common-mode window around VAG — a genuine fault condition that would produce exactly this. **Whether the Rev D shield AC- or DC-couples its LINE IN pads decides whether this candidate is live at all, and it is answerable from PJRC's published schematic with no bench work.**

### The discriminating test, and why it beats measuring the ground difference first

**Ground LINE-IN-L with a very short wire to the Audio Shield's OWN GND pad**, not to the breadboard rail. That collapses the loop area to near zero *and* makes the reference local in one move.

- Floor **drops toward −57** ⇒ mechanism (1) or (2) — an external ground path or the loop it encloses.
- Floor **stays near −31.9** ⇒ mechanism (3) — the codec's response to having its input tied low, independent of where the ground comes from.

One wire move, no new instrument, and it splits the candidate set cleanly. The direct breadboard-GND-to-shield-GND scope measurement is still worth taking and is now interpretable — the ~32 mV<sub>pp</sub> grounded-probe control has been recorded — but it can only confirm mechanism (1), whereas the short-wire test can rule out two of three.

### Bench state, and why it must be restored before any comparison

Four deviations from the −31.49 dBFS pooled baseline are currently in place: **`48e` lifted off LINE-IN-L · LINE-IN-L jumpered to GND · J2 removed · `col 30` → GND jumper fitted.** No future reading is comparable to the baseline until all four are restored. Tracked in TODO-40.

### Method note

This is the second inference in two entries that a further test overturned, and both times the sequence was sound: state the narrow claim, design the test that could break it, run it. **Entry (1)'s error was not the inference — it was the word "exonerated", which asserted more than a two-state test can support.** The corrected form is a conditional statement about when the reading appears, which is exactly as much as the data says.

---

## 2026-09-12 (1) — ✅ DECISIVE SPLIT: lifting 48e off LINE-IN-L drops SOURCE by 25.9 dB. The elevated floor is delivered through the analog front end, not generated in the codec

**Observed.** Disconnecting the `48e` → SGTL5000 LINE-IN-L conductor reduced SOURCE_NODE from **≈−31.3 dBFS to ≈−57.0 dBFS**, a **25.9 dB reduction**, leaving SOURCE only **1.8 dB** above the open RETURN channel.

**Inference.** The elevated SOURCE floor is introduced through the connected analog front-end path upstream of LINE-IN-L.

**NOT yet proven.** That OPA_BIAS, or the missing 10 µF bulk capacitor recorded as deviation **D2**, is the root cause. See the probe-floor caveat below.

### The elimination sequence, in full

| # | Condition | n | mean SOURCE | Δ vs baseline |
|---|---|---|---|---|
| 0 | Guitar connected, volume up, J2 fitted | 14 | −31.49 dBFS | — |
| 1 | Guitar volume at 0 | 5 | −31.48 dBFS | +0.01 |
| 2 | J2 3.5 mm stub removed | 5 | −31.28 dBFS | +0.21 |
| 3 | `col 30` → GND jumper fitted | 5 | −31.12 dBFS | +0.37 |
| 4 | **`48e` lifted off LINE-IN-L** | 5 | **−57.04 dBFS** | **−25.55** |

Readings for condition 4: **−57.1 / −57.2 / −57.1 / −56.7 / −57.1 dBFS**, RETURN −58.3 to −59.2 across the same windows.

**Conditions 1–3 moved the floor by 0.37 dB in total.** Shorting the pickup at its volume pot, removing the open J2 stub from SOURCE_NODE, and grounding the jack-side of C1 all did nothing. Condition 4 moved it 25.9 dB. **Everything external to the board is eliminated; the source is on the board, between C1's output and LINE-IN-L.**

**Two corroborating details.** TF spot-check went to `---` at every frequency including 120 Hz — the only bin that had reported a value all session — and confidence fell to 0 %. And in the uptime-145 s window SOURCE and RETURN track each other sample-for-sample, ramping at the same index: common-mode codec floor showing on two undriven inputs, exactly as expected.

### The scope numbers agree with the ADC — that part is solid

| Node | Scope V<sub>pp</sub> |
|---|---|
| OPA_BIAS `col 41` | 31.35 mV |
| U1 pin 1 / `35e` | 37.90 mV |
| C2 out / `48e` | 45.77 mV |

**−31.3 dBFS back-converts to 36.2 mV<sub>pp</sub>** at the codec input (0.665 V peak full scale at `SGTL5000_LINE_IN_LEVEL = 5`). Against 45.77 mV<sub>pp</sub> measured at the same node, that is the same magnitude. **The scope and the ADC independently agree there is ~40 mV<sub>pp</sub> arriving at LINE-IN-L.** The elevated floor was never a digital artifact.

### ⚠️ The 31 → 38 → 46 progression is NOT yet a noise gradient — correction to an earlier reading of it

An earlier draft of this analysis treated the three scope readings as a rising gradient and concluded the noise originates at OPA_BIAS. **That conclusion is withdrawn as premature.**

**The grounded-probe control was never recorded under the exact final settings** (20 MHz limit engaged). Without it, the probe/scope noise floor is unknown, and the first two readings — 31.35 and 37.90 mV<sub>pp</sub> — may be substantially or entirely floor. Only the 48e figure is independently corroborated, by the ADC.

**A gradient measured against an unknown floor is not a gradient.** Record the control first; every amplitude comparison in this investigation depends on it.

### What is and is not established

- ✅ **Established:** the noise enters LINE-IN-L through the front-end connection; ~40 mV<sub>pp</sub> is real and present at `48e`; the codec, its routing and the digital capture path are exonerated; nothing external to the board contributes materially.
- ❓ **Open:** where between C1's output and `48e` it originates. Candidates: the OPA_BIAS network through R5 (**D2**, hypothesis — TODO-33), U1's own noise, the biased high-impedance node at col 33/37, C2, or the 48e run itself.

### Method note

**Three consecutive over-claims this session, all the same shape:** stating a conclusion first and the disqualifying caveat second — the "J2 removed" result before the removal had happened, "shorts the amplifier input" when C1 blocks DC, and now the OPA_BIAS gradient against an unrecorded floor. Each was caught, none propagated into a bench action, but the pattern is the thing to fix. **The caveat belongs in front of the claim, or the claim should not be made.**

---

## 2026-09-11 (3) — Protocol v2 schema FROZEN. T1 acceptance harness built, because the firmware could not produce the numbers the pass condition requires

**Why this entry exists:** the decision was made to freeze the field layout and move from code reasoning to bench proof. Acting on that surfaced a gap that would have quietly invalidated the bench test. **The bench was never touched.** Compile proof only.

### The schema is frozen, and the freeze has an explicit scope

Protocol v2's state is now recorded as **"schema-frozen, transport-unproven"**, and that distinction is doing real work rather than hedging:

**🔒 Frozen — a parser written against these will not need rewriting:** field positions and widths, packet type ids `0x01`–`0x07`, every enum meaning, clamp and coverage semantics including the rendering contract, the RESULT layout and its 156-byte fixed block, and the framing/resync rules.

**🔓 Still movable — a parser does not depend on these:** live frame cadence (`DISPLAY_UPDATE_EVERY_N_FRAMES`, currently 1), bin count, TX buffer size and chunking strategy, when `dataSender_service()` runs, baud rate.

The practical consequence is written into TODO-36: **a receiver that reads `live_bins` and `decim_ratio` from HELLO instead of hardcoding them is immune to everything in the second list.** One that hardcodes 128 bins breaks the first time the cadence lever gets pulled. That is the single most useful thing to tell whoever writes the Pi side, and it is only sayable because HELLO became structured in v2.

`PI_PROTOCOL_VERSION` stays at **2**. Changing the payload shape while a committed `protocol=1` existed is exactly what a protocol version is for; reverting to 1 would erase historical meaning.

### The gap: the pass condition was unmeasurable

The T1 pass condition is *"acquisition timing indistinguishable from the `DISPLAY_TARGET_NONE` control"*. Checking whether the firmware could actually produce that comparison: **it could not.**

The 5 s diagnostic window reported a block-period **mean only** — computed as `elapsed / blocks`. No max. No spread. No skipped-block detection. No audio high-water. No loop-body maximum. Nothing in `audio_capture` exposes a dropped-block or per-queue overrun counter either.

So Phase 10 could have been "passed" on the strength of a small `[Link] Call time` figure while a genuine perturbation went entirely unmeasured — **which is the exact failure mode the pass condition was written to prevent.** Writing a careful acceptance criterion and then having no instrument to evaluate it against is worse than having no criterion, because it produces false confidence with a paper trail.

### `timing_probe.{h,cpp}`

Measures the side that must not move:

- **Block period mean / max / min / spread.** The mean alone cannot distinguish steady 46.3 ms from alternating 40/53 ms, and it is the spread that would reveal transport interference.
- **Skipped-block detection from gaps in the canonical block counter.** The counter is monotonic, so a gap > 1 in `output_block_number` means an analysis block was produced that the loop never processed. This is the most direct evidence of measurement disturbance obtainable without modifying the capture layer, and it is the metric that must read **zero in every run, no exceptions**.
- **Whole-loop-body duration max**, timed from the first statement to the last. Catches anything that blocks wherever it lives — a transport that is individually fast but collectively starves the loop shows up only here.
- **Audio block high-water, reset per window.** Without the reset a boot-time spike would contaminate every subsequent run and the four runs would not be comparable.

**Compiled into all three targets deliberately.** Guarding it to `_PI` would make the control run unmeasurable and void the entire test — the control must run identical code.

**Output is fixed-format `key=value` lines** specifically so the four runs can be diffed mechanically rather than eyeballed, and the report prints the pass condition inside itself, including the warning that a small call time is not a pass.

**One honest limitation, stated in the source rather than glossed:** `audio_blocks_high_water` is the Audio library's **global** figure, not a per-queue overrun counter, because `audio_capture` does not expose one. The report says so explicitly so nobody later cites it as "capture overruns". `blocks_skipped` is the authoritative overrun evidence.

### The thing I was most careful not to do

The tempting shape for this harness was to instrument the transport more heavily. That would have been the wrong instrument for the question. A microsecond-fast `presentation_*()` call can still disturb the instrument indirectly — interrupt load, UART ISR activity, DMA contention, buffer servicing — and **none of that appears in a call-duration figure.** So the harness measures acquisition, and the pass condition is comparative: run 1 *is* the threshold, which means there is no number to argue about.

This matters more in this firmware than it would in most. The system is built around one capture owner and one canonical timebase, and every time-sensitive operation references it. Perturbing that layer compromises far more than the display — which is also why `blocks_skipped` gets an absolute requirement (zero) while everything else is judged comparatively.

### The T1 acceptance matrix

Written into Phase 10 and TODO-35. Four runs, identical window length (≥60 s) and identical signal conditions:

| Run | Build | Condition | Role |
|---|---|---|---|
| 1 | `_NONE` | no display hardware | **THE CONTROL** |
| 2 | `_PI` | reader consuming normally | normal operation |
| 3 | `_PI` | reader suspended (`kill -STOP`), UART stays full | sustained backpressure |
| 4 | `_PI` | TX pulled mid-RESULT drain | loss mid-transaction |

Acquisition must not move; transport is *allowed* to degrade. Drops in runs 3/4 are expected, `TX room min = 0` in runs 3/4 is backpressure correctly absorbed, and non-zero abandoned result bytes in run 4 is correct behaviour. Run 3 additionally requires that the validation suite still runs and passes — a dead renderer must not be able to fail a measurement.

### Also added

`result_bytes_abandoned` to the transport stats, so run 4 can report how much of a superseded/abandoned result never reached the wire rather than only that it happened.

### What the next session should know

1. **The next action is bench work only.** Do not touch protocol fields. Run the four-configuration matrix, paste all four `T` reports verbatim here, and diff them.
2. **`t` starts a window, `T` reports.** A window also starts automatically at the end of `setup()`, after init, so a run is measurable even if `t` is forgotten.
3. **`blocks_skipped` must be 0 in all four runs.** Everything else is judged against run 1. If block timing degrades anywhere, stop and find the blocking path — acceptance test B in the protocol audit is where to start.
4. **On pass:** T1 closes, v2 goes from schema-frozen to proven, and the milestone is **v0.6.0 — Pi presentation architecture validated**. Only then start the Pi renderer. The parser can be written now.
5. The portfolio-relevant story here is not "added UART". It is that a **semantic audit made the packets larger, which exposed a real-time systems conflict, and the resolution was to change the delivery contract rather than delete measurement meaning** — and then that writing the acceptance criterion revealed the instrument to evaluate it did not exist yet, so that got built before the test was run. Both of those are the same discipline applied twice.
6. Track A remains untouched: TODO-21, TODO-32, TODO-23, TODO-29.

---

## 2026-09-11 (2) — Protocol v2: the four truth-invariant defects closed, transport made non-blocking, firmware baselined at 0.6.0

**Why this entry exists:** entry (1) built the presentation boundary and then used it to audit `data_sender`, finding 17 protocol defects. This session fixed them. **The bench was never touched.** No measurement taken, no wire moved, no firmware uploaded. Compile proof only.

### The ordering was the decision

Conley's sequencing: **semantic completeness first, packet mechanics second.** `result_valid`, provenance and clamp state are not optional UI metadata — they are part of the *meaning* of a measurement. Polishing framing around a packet that omits whether the measurement is valid would be optimising the wrong layer.

That ordering immediately surfaced a conflict worth recording: closing L1 and L3 **makes the live frame bigger** — 1 689 B vs v1's 1 559 B, because per-bin clamp and validity coverage costs 130 bytes. So the semantic fix makes the T1 backpressure prediction *worse* (~36.7 ms of wire time vs ~33.8 ms, against a measured 46.3 ms block period). The resolution is not to shrink the payload but to change the delivery contract, which is what made the next part necessary rather than optional.

### Presentation transport must be lossy before measurement becomes lossy

This is the architectural rule that came out of the session and it is now explicit in the source:

- **LIVE_FRAME** — best effort, droppable, latest-wins. A stale frame has no value; dropping one costs a visual update.
- **RESULT** — reliable. Staged into a buffer and drained across loop iterations by `dataSender_service()`. A completed measurement matters, so it is queued rather than dropped; a newer result supersedes an undrained one (latest-wins, counted).
- **STATUS / ABORTED / ROUTER / VIEW / HELLO** — best effort.

Every write is gated on `availableForWrite()`. **There are no blocking writes left in the module,** and the acceptance test for that is mechanical: grep for `.write(` and confirm each is preceded by a room check covering the whole remaining packet.

**The subtlety that would have broken this silently.** Teensy's default Serial1 TX buffer is far smaller than one live frame, so `availableForWrite()` could *never* report room for one, and **every single live frame would have been dropped** — a total failure of the live path presenting as a Pi-side bug. Fixed with `addMemoryForWrite()` and a 4 KB buffer, and pinned with a `static_assert` that the buffer exceeds one framed frame. Worth stating plainly: a non-blocking policy with an undersized buffer is not a conservative choice, it is a broken one.

**Safety net, deliberately designed in.** `measurement_state` travels in *every* live frame. A dropped ABORTED therefore costs the reason string, not the fact — the Pi still observes `state == ABORTED` on the next frame. Event loss degrades gracefully instead of desynchronising the Pi's state model, and receivers are told in the header to treat the live frame's state byte as authoritative and event packets as enrichment.

### The invariant, turned into a test that finds things

Entry (1) stated it as a slogan and then as a test. Applied field by field, the test is what produced the fix list:

> For every field the Pi displays: is this a **fact** the Teensy knows, or a **judgement** the Pi is reconstructing? If it is a judgement — valid/invalid, clipped, clamped, quality, calibration state, confidence, coverage — **send it.**

Every such judgement now has a wire field. The clamp case is the one that matters most and it got the most care: per-bin nibbles (clamped count / valid count), a frame-level `tf_clamped_count`, and a rendering contract written into `data_sender.h` saying that `clamped == ratio` means *draw a saturation indicator, not the rail value*. Phase 10 step 7 tests it with nothing connected to RETURN_NODE — the exact condition that produced `1kHz=-24.0dB` in 33 of 33 windows on 2026-09-07.

### Decimation: one function was doing two incompatible jobs

v1 applied a single arithmetic mean to `fft_source`/`fft_return` (**linear** magnitude) and to `tf_db` (**dB**). Separated:
- Linear spectra now decimate by **maximum**. An arithmetic mean buries narrow peaks — one bin at 0.5 among three at 0.001 means 0.126, a **12 dB under-report** — which for a spectrum display is the wrong default. Harmonics are the thing a player wants to see.
- `tf_db` keeps the dB mean (a geometric mean of power), appropriate for a transfer-function curve, with the valid/clamped nibbles saying how much to trust each point.

Both are now stated on the wire contract. They were never *wrong* so much as **undocumented defaults** — and an undocumented default in an interface between two codebases becomes a disagreement later.

### Three smaller things worth keeping

1. **I added a `frameInto()` helper, then didn't use it** — both paths frame differently by necessity (the live path writes three times after one room check; the reliable path frames into its staging buffer to be chunk-drained). The compiler caught it as unused. Removed, and replaced the spot with a comment explaining why there is deliberately *no* shared framing helper: a shared one would be a standing temptation toward a partial write.
2. **Two `strncpy` truncation warnings were real signal.** The calls were safe only because of a preceding `memset`. Replaced with an explicit `writeFixedString()` using `strnlen` + bounded `memcpy`. Being explicit beat silencing the warning.
3. **Layout drift is now impossible to do silently.** The RESULT fixed block is pinned by a `static_assert` on the constant *and* a runtime check that the serialiser actually filled exactly that many bytes. These fail for different reasons and both are needed: a field added without updating the layout comment shifts every later offset, and the symptom on the Pi is plausible-looking wrong floats, not an error. The runtime check refuses to send a drifted packet rather than emitting one the Pi will misparse into confident garbage.

### T3 closed on a judgement call

T3 (no view-change packet) was a 🟡 and outside the "five reds" scope. I closed it anyway, because my own audit said "resolve before freezing the wire format" and **this change is the pre-freeze change** — leaving a known-wrong-shaped message in a format about to be frozen would have meant a v3 for something already understood. `presentation_restoreLive()` now sends a VIEW packet instead of a magic `"VIEW:LIVE"` status string.

### Versioning: 0.6.0, and two numbers instead of one

`FIRMWARE_VERSION` was `0.5.0` while `data_sender`'s headers said `v0.6.1` and **21 other module headers carried their own `v0.5.0`**.

- **0.6.0**, not 0.6.1. The existing 0.6.1 was a header that had run ahead of the product; adopting it would inherit a number that never meant anything. 0.6.0 now means exactly one thing: *first firmware baseline implementing the Pi 5 production display architecture.* That is a useful thing for an exported measurement to be stamped with.
- **Bumped after the fixes, not during.** Stamping an intermediate reconciliation state would have produced a version that means "halfway through a refactor".
- **`PI_PROTOCOL_VERSION 2` as a separate constant.** Firmware version and wire format are different compatibility concepts — a firmware bump that does not touch the wire must not invalidate a working receiver. v1 → v2 because the payload shape of both LIVE_FRAME and RESULT changed; a version number that has appeared in the tree is not reused for a different layout, or an old log reading `protocol=1` becomes ambiguous about which layout produced it.
- **All 21 module-local versions stripped.** Original file permissions preserved exactly — several were read-only and were restored to read-only.

### Proof — observed, not inferred

| Target | FLASH code | RAM1 free for locals | RAM2 vars | warnings | Adafruit libs |
|---|---:|---:|---:|---:|---|
| `_NONE` | 147 904 | 148 928 | 46 720 | **0** | no |
| `_PI` | 152 960 | 146 656 | 62 528 | **0** | no |
| `_RA8875` | 158 596 | 140 608 | 46 720 | 2 | yes (3) |

`_PI` and `_NONE` are now **warning-free**; v1's unused `payload_size` went with the rewritten code path, and `_RA8875`'s two remaining warnings are inside the Adafruit library itself. The `_PI` RAM2 delta (+15 808 B) is the three `DMAMEM` transport buffers landing in OCRAM rather than the tight RAM1 budget, exactly as intended — RAM1 free-for-locals differs by only ~2.3 KB between `_PI` and `_NONE`. `[compiles]` — **nothing uploaded.**

### What the next session should know

1. **T1 is the whole remaining question, and it is not answerable from source.** The predicted ~36.7 ms / 46.3 ms occupancy is still arithmetic. The instrumentation to settle it ships (`u` serial command; transport figures print inside the existing 5 s window so they sit directly beneath block timing). **With the non-blocking policy the measured max call time should be microseconds.** A max near a millisecond means something blocks and the policy was violated somewhere.
2. **Protocol v2 is a freeze candidate, not frozen.** A Pi parser can be written against it now. The one thing that might still move is frame **sizing or cadence**, not field layout — if T1 measures badly, the lever is `DISPLAY_UPDATE_EVERY_N_FRAMES` (currently 1, i.e. a frame every block) or the bin count, not the semantics.
3. **Phase 10 step 12 is the real acceptance test**, not step 11: block timing must be unchanged with the Pi **absent, stalled** (`kill -STOP` its reader so the UART stays full), **and yanked mid-result**. A high drop count with a low max call time is the design working. If block timing degrades in any of the three, stop — no amount of Pi-side work fixes it.
4. **Do not route Pi → Teensy input through `presentation_*`.** Touch commands are CONTROL, not presentation, and belong behind a separate boundary with its own validation — presentation is outbound-only today and so adds no externally-controlled input surface at all. This is now written into `presentation.h`. Routing control back through the display API would destroy the property that makes the boundary worth having.
5. Track A is still untouched. TODO-21, TODO-32, TODO-23 and TODO-29 are where they were.

---

## 2026-09-11 — Display architecture drift found and resolved. ADR-001: the Pi 5 is the production renderer; a presentation boundary now separates truth from presentation

**Why this entry exists:** an audit asked a simple question — does the repository still implement the original plan (Teensy captures and computes, Pi 5 renders)? — and found that it does not, and had not for some time. The capture half was intact and enforced. The display half had quietly inverted. **The bench was never touched this session.** No measurement taken, no wire moved, no firmware uploaded. Everything below is a source audit plus a refactor verified by compile only.

### What the drift actually was

Two architectures coexisted, and only one was reachable:

| Pi 5 architecture — documented | RA8875 architecture — actually built |
|---|---|
| `data_sender.{h,cpp}`: complete binary UART protocol, 5 packet types, CRC-16/CCITT, per-baud bin budget | `.ino` called `displayEngine_*` unconditionally at ~20 sites |
| Runbook L109: "This is the **`USE_PI_DISPLAY`** build" | **`USE_PI_DISPLAY` existed nowhere in the source.** That one sentence was its only occurrence in the repository |
| Pi 5, cooler, PSU, 7" Touch Display 2, Freenove HAT all purchased | Verified bench effort went to the RA8875: TODO-25's `s_display_ok` guard, TODO-24's pin 8→5 move |
| TODO-24 reserved pins 0/1 for `Serial1` / `data_sender` | Track B carried TODO-12 and TODO-14, both RA8875 UI work |
| — | `data_sender` had **zero callers**. It compiled and did nothing |
| — | `README.md` contained no Pi at all; its diagram ended at `display_engine → RA8875` |
| — | `tools/gen_schematic.py` reserved the RA8875 and had **no Pi UART row** |

**The sharpest symptom:** pins 0/1 were being *protected* for a UART link to a renderer that **no build could select**. The project was paying the Pi path's resource cost without possessing a Pi path.

**A second one worth recording:** the runbook's parts list marked five Pi components "used in Phase 9", but Phase 9 in that same document is the **validation harness**. No phase in v3 ever installed the Pi. It was bought with nowhere to go. That is what an unbuilt phase looks like from the inside — the parts arrive, the code gets written, and nothing ever connects the two.

### The decision

Recorded in [docs/adr/ADR-001-display-architecture.md](../docs/adr/ADR-001-display-architecture.md): **recommit to the Pi 5 as the production renderer; demote the RA8875 to bring-up/debug hardware.**

Reasoning, in the order that actually decided it:
1. The Teensy's real-time budget is already committed to acquisition, complex FFT, H1, coherence, phase, group delay, calibration, routing and quality grading. Adding a sophisticated touch UI to the same core creates coupling the design does not need.
2. **The RA8875 incident is the precedent, not an anecdote.** An *absent* display spun `waitPoll()` and stretched the audio block period from 46 ms to 2194 ms — a display defect that destroyed acquisition (entry 2026-09-05 (10)). Keeping the renderer on the measuring core means every UI frame is a potential audio stall.
3. The Pi has room for what makes the instrument compelling — fingerprint visualization, saved-measurement browsing, comparison views, real touch interaction.
4. The interface already existed and is better evidence than it looked. `data_sender` has framing, a sync word, CRC-16/CCITT, and a documented receiver algorithm. It needed an audit, not a rewrite.

### The governing invariant, and why it is stated as a test

> **The Teensy determines truth. The Pi presents truth.**

Stated that way it is a slogan. Stated as a test it is useful:

> **If the Pi must derive a judgement the Teensy already made, the protocol is wrong.**

That test immediately found four real defects (below). It is now the acceptance criterion for the wire format.

### What was rejected, and why it mattered

**Mechanically replacing the ~20 `displayEngine_*` calls with `dataSender_*` calls.** This was the obvious move and it was the wrong one — it would have hard-wired a second renderer assumption in place of the first and produced another fork to untangle later. Instead the application calls `presentation_*`, and `DISPLAY_TARGET` in `config.h` dispatches at compile time to `data_sender`, `display_engine`, or a null backend.

**A boolean `USE_PI_DISPLAY`.** A tri-state is strictly better because `DISPLAY_TARGET_NONE` is independently valuable: it is the honest configuration for bench DSP work with no panel attached, which is what Phases 5–9 actually run in. A boolean cannot express "no display" — the state the bench has been in this whole time.

**Deleting `display_engine`.** It is working, bench-verified code. Removing it to express an architectural preference would be a net loss; it stays as the `_RA8875` backend.

### Two things the refactor found that the audit had missed

**1. `validation.cpp` had 14 direct `displayEngine_drawStatusMessage()` calls.** The original audit counted only the `.ino`'s ~20 and missed these entirely. This mattered: the validation harness is what runs Phase 9 and *proves the instrument works*. Left alone, it would have kept an RA8875 dependency alive inside a Pi build while reporting none of its progress to the Pi. Rewired to `presentation_status()`.

**2. A header guard in `presentation.cpp` alone does not exclude a backend.** I wrote a comment claiming that under `_NONE` neither backend is "dragged in", then the compile disproved it: **an Arduino/arduino-cli build compiles every `.cpp` in the sketch folder regardless of what includes its header.** `display_engine.cpp` and `data_sender.cpp` were both still being compiled and linked. Fixed by wrapping each file's entire body — includes and all — in its own `#if DISPLAY_TARGET == ...` guard, and the false comment was corrected rather than left in. Without that, `DISPLAY_TARGET_NONE` would have been nominally free and actually not.

### Proof — observed, not inferred

All three targets compile clean for `teensy:avr:teensy41`, built from the same tree with only the one `#define` changed:

| Target | FLASH code | RAM1 vars | warnings | Adafruit libs in build |
|---|---:|---:|---:|---|
| `_NONE` | 147 840 | 211 520 | 0 | **no** |
| `_PI` | 150 848 | 212 672 | 1 | **no** |
| `_RA8875` | 158 596 | 218 816 | 2 | yes (RA8875, GFX, BusIO) |

The library column is from `arduino-cli compile -v` "Using library" lines and is the direct evidence that the guards work — the three Adafruit libraries are a build dependency **only** in the RA8875 build. The `_PI` warning is the pre-existing unused `payload_size` in `data_sender.cpp`; the `_RA8875` warnings are the pre-existing Adafruit `setRotation` hiding. Both are the baseline pair recorded in entry 2026-09-05. `[compiles]` — **nothing was uploaded to hardware.**

### The protocol audit is the most important outcome of this session

`data_sender`'s wire format predates the clamp-marker work, the confidence-denominator fix and the current insight/provenance model, and had never been checked against any of them. Full findings in [docs/pi_link_protocol_audit.md](../docs/pi_link_protocol_audit.md) — **17 findings, five 🔴, four of them failures of the invariant test above.**

The one that matters most:

**L1 — the TF clamp mask is not transmitted.** `AudioFrame.tf_clamped_bits[]` and `tf_clamped_count` exist precisely so a consumer can tell a saturation rail from a measurement, and `audio_engine.h:310` makes checking them **mandatory** for "any consumer that RENDERS `tf_db` to a human". `sendLiveFrame()` sends neither. So the Pi would plot a flat, confident, entirely fictional −24.0 dB curve — **the identical defect that printed `1kHz=-24.0dB` in 33 of 33 consecutive windows on 2026-09-07** before `aa9a795` fixed it for the serial diagnostic. This also means **promoting `data_sender` re-opens TODO-29 on a new surface**, which is an argument for eventually fixing that bug class at the presentation boundary rather than once per renderer.

Then: **R1** `result_valid` — the top-level verdict — is not transmitted at all; the Pi must infer validity from the quality enum. **R2/R3** calibration provenance, type and warnings are not transmitted, so a calibrated result would display with its own caveats silently dropped, and the "show quality *and provenance*" requirement (README, TODO-12's proof criterion) cannot be met by either renderer today.

**T1 is a prediction, and is labelled as one.** A 1 559-byte live frame is ~33.8 ms of blocking UART write time at 460 800 baud against a measured 46.3 ms audio block period — **73 %** — and `DISPLAY_UPDATE_EVERY_N_FRAMES` is 1, so one is sent every block. A max-size RESULT is ~214 ms. That is the same failure shape as the RA8875 `waitPoll()` stall, reached through a different peripheral, and it would be an unforced error to trade one for the other. **But it is arithmetic from baud rate and packet size, not a bench observation** — the actual TX buffer size and whether Audio-library DMA survives a stall have not been measured. It must not be recorded as a bench finding until instrumented; that measurement is part of Phase 10's acceptance.

### Why the documentation fixes are not cosmetic

Four documents independently corroborated the *wrong* architecture: README, the runbook, the as-built netlist, and the generated schematics. AI assistants are first-class readers of this repository, and a stale architecture document does not merely fail to help — it actively causes the next agent to reconstruct the wrong project. The README was additionally describing six directories that do not exist here (`audit/`, `development/`, `visualizations/`, `mock-test/`, `.github/`, `docs/ai/`) and claiming `signal_router` and `data_sender` were staged in `development/` when both have been at the root for some time. All corrected, with the correction stated in place rather than silently applied, so the drift itself stays visible.

The as-built record got the narrowest and most interesting fix: its reserved-hardware list contained the RA8875 and **no Pi UART row at all**. A frozen as-built document that omits the production display interface while reserving the debug one will mislead a future reconstruction, so pins 0/1 are now documented as reserved in both `netlist.md` and `tools/gen_schematic.py`, and the drawings were regenerated from source (not hand-edited).

### What the next session should know

1. **Do not proceed with TODO-12 or TODO-14 as written.** Both are superseded (kept, not deleted — the design content transfers to the Pi's views).
2. **Do not write a Pi-side parser yet.** TODO-34 must close first: five findings change the payload shape, so building against the current layout means building twice.
3. **TODO-24 is no longer a product blocker.** The pin 8→5 rewire is needed only if you deliberately select the RA8875 debug backend with the panel mounted. Use `DISPLAY_TARGET_NONE` for Phases 5–9.
4. **Always check the `[Main] Display target:` banner line** before interpreting a serial log. It was added specifically so a bench observation can never be misattributed to the wrong display architecture — which is the error class this entire session was about.
5. `FIRMWARE_VERSION` is still `0.5.0` while `data_sender.{h,cpp}` headers say `v0.6.1`. Not changed here — a version bump stamps into every exported measurement result and is a deliberate decision, not a cleanup. Flagged, not resolved.
6. Track A is untouched. The hardware bring-up path and its open items (TODO-21, TODO-32, TODO-23, TODO-29) are exactly where they were.

---

## 2026-09-07 (9) — As-built capture FROZEN. Schematic reverse-engineered from the board, then audited against bench evidence: 2 material defects found and corrected

**Why this entry exists:** the breadboard reached a known-good state on 2026-09-07 (6)/(7) after days of debugging, and nothing existed that could reconstruct it. This session captured it — a verified netlist, a generated schematic in one-sheet and two-sheet forms, and an audit of that schematic against the physical evidence. **The bench was never touched.** No measurement was taken, no wire moved, no firmware uploaded.

### The rule that governed the whole session

**Evidence hierarchy, applied without exception:** physical observation > photograph > measurement > active firmware > this journal > `docs/breadboard_bringup_v3.md`. Where the runbook and the board disagreed, **the board won and the disagreement was recorded** rather than reconciled. Six runbook defects are now documented, including a new one (D5): Phase 0 Step 5 bridges `TOP_RED`↔`BOT_RED` at columns 1 and 60, and Phase 1 Step 7 then declares `BOT_RED` to be VGND — **followed literally, the runbook shorts VGND to +5 V.** The board does not have those bridges.

A second rule mattered as much: **documentation completeness is never a reason to touch a known-good bench.** Two gaps are recorded as `NYV` by explicit decision (`TOP_RED` col5↔col55 continuity; the Dinkle carrier's `5V` terminal provenance). They are decisions, not oversights.

### What the capture established

- **Analog front end fully traced** — OPA1642A on a PA0001 adapter, pin 1 at `35e`; the OPA_BIAS topology from 2026-09-05 (4) confirmed as-built at columns 41/43; VGND alive at column 45, **not** column 15 as the runbook says; W1, the orange jumper `TOP_RED`→`35h`, found only on the third pass.
- **Interconnect map closed** — all ten wires, 1:1 screw→pad, and **the physical set matches the firmware exactly**: pins 7, 8, 18, 19, 20, 21, 23 with nothing left over on either side.
- **The fix quantified** — jumpers ≈25–30 mm against the 100–200 mm flying leads of entry (5). A **4–8× reduction in conductor length**. That ratio is the measurable content of the fix and the thing a rebuild must reproduce.

### 🔺 The audit found two material defects in my own drawing

**A1 — four capacitor values were asserted but never read.** C3/C4/C5/C7 carried "0.1 µF" from the runbook's parts list. They had only ever been described as *"yellow things"* — **the same description given for C1, which turned out to be `BC103` = 10 nF.** The single data point available contradicted the assumption applied to the other four. `PHYS` had covered their presence and position; it never covered their value. Conley has since confirmed 0.1 µF at the bench, so they are restored — but tagged `RPT` (reported), not `PHYS`, because no marking was read back. **One thread stays open:** the confirmation said *"all three"* while four are listed; recorded, not assumed away.

**A2 — RETURN_NODE was missing from the schematic entirely.** `RETURN_NODE_PHYSICAL_CH 1` ([config.h:174](../config.h#L174)) binds it to I²S channel 1 = U3 **LINE IN R**, which **has no conductor fitted.** The drawing simply omitted it. **This is worse than an ordinary omission, and the reason is the important part: the firmware reports a level for that channel, and −56 dBFS is the crosstalk floor bleeding from LINE IN L — not a measurement.** An undocumented open input that still prints a plausible number is the same class of trap as TODO-29's clamped TF bins, and it nearly reached a portfolio drawing. LINE IN R is now drawn with an explicit no-connect cross and annotated on the face of the sheet.

**A3 — VGND's 2.50 V was stated as fact.** It is *calculated* from R3/R4 being a matched pair. The only measurement, 2.480 V (2026-09-05 (1)), predates the OPA_BIAS rework and was taken at the old column-15 divider. Now labelled "calculated".

**A4 — R5 = 100 kΩ upgraded `INF` → `DERIV`.** Entry (6) measured a 1 kHz gain of **0.9848** against **0.9867** predicted for 100 kΩ with C1 = 10 nF; 22 kΩ would predict ≈0.81 and is excluded. **Independent of the colour-band reading, and the same measurement corroborates C1 = 10 nF from a second direction.**

### An I²S naming scare that turned out to be a documentation defect, not a wiring one

A review flagged the data-line labels as reversed. They were not. `config.h:81-85` and journal:1077 both establish that **pin 8 carries audio INTO the Teensy**, so the drawn directions were correct. The real defect was that **the drawing never declared its convention.** Net names on this project are **codec-referenced**: `I2S_DIN` is the *codec's* data input (Teensy pin 7, `SAI1_TX_DATA0`) and `I2S_DOUT` is the *codec's* data output (Teensy pin 8, `SAI1_RX_DATA0`). Read Teensy-first, they look backwards.

**Renaming the nets would have been the wrong fix.** It would have contradicted `config.h` and severed the link between the schematic and entries (3)–(6), which spent days on "DOUT pin 8" — the drawing would silently have started describing a different wire. Fixed instead by declaring the convention on the drawing, adding the `SAI1_*` aliases, and putting direction arrows on every signal line.

### Lesson worth keeping

Entry (6)'s lesson was that the fault lived in the medium between the endpoints. **This session's is narrower and about documentation: `PHYS` is not one claim, it is two.** "This part is in this hole" and "this part has this value" have completely different evidence, and a table with a single verification column silently merges them. Every value defect found today — A1, A3, and the R5 upgrade — is that same conflation. The netlist now separates strip-level from hole-level confidence and position from value, and adds an `RPT` tag for things reported at the bench but not independently confirmed.

### Digital-section value/provenance audit, same session

Run clocks → 5 V function → part identity, deliberately in that order so the
best-evidenced claims set a baseline before hardware-identity questions.

**✅ D1 — the clocks are the strongest evidence in the whole document, and one was under-stated.** All three derive from `SAMPLE_RATE 44100` ([config.h:208](../config.h#L208)) and were independently measured on a RIGOL DHO804 in 2026-09-06 (1): LRCLK 44.108 kHz against 44.100 derived (**0.018 %**), BCLK ~2.82 MHz against 2.8224, MCLK ~11.29 MHz against 11.2896. **Defect: LRCLK carried no frequency on the drawing** while BCLK and MCLK did, making the frame clock look less established than it is. All three now show value, ratio and provenance.

**🟡 D2 — "5V pass-through, unused by codec" was half-asserted.** The wire is real and `PHYS`; the *"unused"* claim has no primary source. journal:1077's "the shield runs from 3.3 V; it does not need 5 V" is a project assertion, not a datasheet citation, and says nothing about other Rev D circuitry. Now marked `NYV`. Harmless either way — but a reconstructor should not be told a pin is unused on this document's authority.

**🟡 D3 — "SGTL5000" is a functional identification, not a package reading.** The QFN marking has never been read and is illegible in every photo. The claim rests on the Rev D silkscreen plus `AudioControlSGTL5000::enable()` returning true — a device at the SGTL5000 I²C address accepting SGTL5000 register writes. Good evidence, adequate here, but `DERIV` not `PHOTO`. **The Rev C/Rev D question raised at journal:962 is discharged three ways:** silkscreen, bench confirmation (journal:913), and the working 7/8/20/21/23 pin set being the Rev D assignment.

**Carrier identity stays open.** "Dinkle" names the *terminal blocks*, not the carrier PCB — so what its `5V` terminal is internally wired to (VUSB / VIN / the 5V pin) remains `NYV`, same root as X-5.

### Postscript — A1's count slip

The bench confirmation of the four 0.1 µF ceramics said *"all three"* for four parts. The discrepancy was raised rather than absorbed, and confirmed as a slip. **The four stay `RPT`, not `PHYS`** — a bench recollection is not equivalent to a read marking, and C1 is the reason why.

**Next:** nothing outstanding on the capture. Phase 5 when the bench reopens.

---

## 2026-09-08 (1) — Phase 5 prep, bench probing: the assisting session is re-deriving the PRE-REBIAS topology, and two readings point at column mis-identification rather than a circuit fault

**No hardware changed by this session. No measurements taken by this session.** This entry records a second opinion on a bench sequence run in a parallel ChatGPT conversation, which does not have filesystem access and is therefore working from the runbook's description rather than from `docs/asbuilt/netlist.md`.

### 🚨 The important correction: col 41 is NOT "the VGND-side leg"

The assisting session proposed, as its next step, a continuity check from **col 41** — described as *"the VGND-side leg of that 100 kΩ resistor"* — to **col 45**, VGND. It framed the intended topology as *"100 kΩ from the op-amp pin-3 node to VGND."*

**That is the topology that was proven invalid and abandoned on 2026-09-05.** Per `docs/asbuilt/netlist.md` §3:

- **OPA_BIAS** = col 41 A–E ∪ col 43 A–E (bridged `41e`→`43e`), fed by R1 47 kΩ from +5 V and R2 10 kΩ to GND ⇒ **0.877 V**, R<sub>th</sub> = 8.25 kΩ
- **VGND** = `BOT_RED` · col 45 A–E, fed by R3/R4 10 kΩ/10 kΩ ⇒ **2.50 V**, R<sub>th</sub> = 5.0 kΩ
- **R5 100 kΩ: `37c` → `41d`** — pin 3 to **OPA_BIAS**, not to VGND

**Separating those two nets IS the common-mode fix** (TODO-21, journal 2026-09-05 (1)–(5)). TI's V<sub>CM</sub> ceiling is (V+) − 3.5 V = 1.5 V on this rail; biasing pin 3 at VGND ≈ 2.5 V is outside it, which is what caused the 327 mV droop that the rebias reduced to 6 mV.

**So the proposed 41↔45 check is safe to run but its interpretation is inverted: NO BEEP is the correct, healthy answer.** A beep would mean OPA_BIAS is shorted to VGND, the buffer is back at an invalid operating point, and every measurement since 2026-09-05 is suspect. It is a fault test, not a confirmation test.

### 🔺 Two readings both land on OPA_BIAS's Thévenin resistance — probe reference is the likelier problem

| Reported | Expected from the as-built netlist | Reading |
|---|---|---|
| `45a` → GND | VGND divider, 10k ∥ 10k = **5.00 kΩ** | **8.58 kΩ** |
| `42d` → GND | col 42 A–E is GND ⇒ **≈0 Ω** | **8.08 kΩ** |
| `37c` ↔ `42d` | pin 3 → GND ⇒ R5 + 8.25k ≈ **108 kΩ** | **73.5 kΩ** |
| `42d` → `BOT_RED` (VGND) | separate nets ⇒ **no beep** | **no beep** ✅ |

**8.58 kΩ and 8.08 kΩ both sit within a few percent of 8.246 kΩ = 47 k ∥ 10 k, the OPA_BIAS Thévenin resistance.** Neither matches the 5.0 kΩ that VGND should present, and neither matches the ≈0 Ω that a GND column should present. Two independent probings, several minutes apart, landing on the same wrong-but-identical value is the signature of **column mis-identification on a crowded board**, not of two separate circuit faults.

The one reading that behaved exactly as the netlist predicts is the `no beep` between the bias node and VGND — which is the reading that confirms the rebias is intact.

### The measurement that would settle it in one step

**OPA_BIAS and VGND are distinguishable by resistance to GND alone, with power off:**

- **8.25 kΩ ⇒ you are on OPA_BIAS** (col 41 / col 43)
- **5.0 kΩ ⇒ you are on VGND** (col 45 / `BOT_RED`)
- **≈0 Ω ⇒ GND** (col 42, col 34, `38b`)

One reading identifies which net a probe is on, without a continuity hunt and without relying on counting columns. **Establish the probe reference before taking any more readings** — a sequential chain of measurements built on an unverified column index accumulates error rather than resolving it.

### ⚠️ R5's value is now genuinely in doubt, and it is not a cosmetic question

`docs/asbuilt/netlist.md` carries R5 as `DERIV`. **That tag cannot be supported.** The R1–R4 derivation works because the divider sets a voltage that was measured (0.874 V vs 0.877 V predicted). **No such derivation exists for R5:** it feeds a JFET gate drawing picoamps, so it drops no measurable voltage, and no recorded measurement constrains it. Its value traces to TODO-4 step 3 and the runbook — i.e. `INF`, design intent, never verified.

**Why it matters now, at Phase 5:**
- **TODO-23** — input impedance *is* R5. If it is 75 kΩ rather than 100 kΩ, the front end loads a 6–250 kΩ pickup harder than the record claims, and the 1 MΩ target moves further away.
- **TODO-19** — the C1 corner is set by R5. 10 nF into 100 kΩ ⇒ 159 Hz; into 75 kΩ ⇒ 212 Hz. The whole low-frequency limitation is quoted from a number nobody has measured.
- Journal 2026-09-05 (6)'s consistency argument assumed 100 kΩ. At 1 kHz it predicts 0.9867 for 100 kΩ and 0.9782 for 75 kΩ against a measured 0.9848, so the sweep mildly favours 100 kΩ — but that is a 6× -above-corner probe and, as that entry itself says, nearly the least informative place to measure a high-pass.

**Resolution: lift one leg of R5 and measure it out of circuit.** In-circuit readings cannot settle it, which is exactly what the 73.5 kΩ reading demonstrates. Logged as TODO-32.

### ✅ Follow-up same session — col 41 confirmed OPA_BIAS, and the powered readings quietly re-verify Phase 4

**`col 41` → GND = 8.20 kΩ** against 8.246 kΩ predicted (47 k ∥ 10 k). **0.6 % agreement.** col 41 is OPA_BIAS, OPA_BIAS is not VGND, and the rebias network is intact. The earlier 8.08 / 8.58 kΩ readings were the same net under wrong labels, as suspected.

**Powered readings reported alongside it, and they are worth more than the identification:**

| Node | 2026-09-05 (5) | 2026-09-08 | Δ |
|---|---|---|---|
| OPA_BIAS | 0.874 V | *(not re-read)* | — |
| U1 pin 3 | 0.868 V | **0.864 V** | −4 mV |
| U1 pin 1 | 0.875 V | **0.872 V** | −3 mV |

**Three days, one interconnect rework, one LINE-IN-L restoration, several power cycles — and the operating point moved by 3–4 mV.** That is a reproducibility result the project did not have before. The analog front end is stable, and the rebias is not drifting.

**And C2's output settled to 4.1 mV DC.** The runbook's Phase 4 end-of-phase table requires *"C2 output is DC-free — red on `48e`, black on GND — **< 50 mV**"*. **4.1 mV passes with 12× margin.** That criterion had never been logged as met; it is met now. Together with pin 1 tracking pin 3 (both criteria on the same table), Phase 4's electrical verify is substantially closed on real numbers rather than on inference.

### R5: the stock list is evidence nobody has cited

TODO-4's recorded inventory is **1 kΩ ×60 · 10 kΩ ×60 · 47 kΩ ×40 · 100 kΩ ×50 · 10 µF ×10 · 0.1 µF ×20**. There is **no 75 kΩ and no 68 kΩ in stock.** A resistor reading 73.5 kΩ is 26.5 % below 100 kΩ — far outside any plausible tolerance — so if R5 really were 73.5 kΩ it would have to be a part that is not in the documented inventory at all.

**That materially raises the probability that R5 IS 100 kΩ and the 73.5 kΩ reading has a different explanation** — most likely one probe on an unconfirmed column, which is precisely the failure mode this entry already documents. It does not close TODO-32; an unmeasured resistor stays unmeasured. But it changes the prior.

**Better next measurement than a column-to-column repeat:** `col 37` (pin 3 node) → **GND**, power off. GND is a known reference, so only one endpoint can be wrong. Predicted **108.25 kΩ** if R5 = 100 kΩ (R5 + the 8.25 kΩ OPA_BIAS Thévenin), versus **81.75 kΩ** if R5 = 73.5 kΩ. The two hypotheses are 32 % apart — unmissable on any meter, and it needs nothing lifted.

### Standing note for Phase 5

This is the same class of error the project has now hit repeatedly: **a document describing the intended circuit was used in place of the record of the built one.** The runbook still describes the pre-rebias Phase 4. Anyone assisting at the bench without filesystem access will reconstruct that circuit in good faith. `docs/asbuilt/netlist.md` is the reconstruction authority — paste the relevant net rows into any assisting conversation before probing, not after a discrepancy appears.

---

## 2026-09-07 (8) — TODO-29: the TF diagnostic was printing a clamp rail as data. Evidence preserved, then annotated rather than changed. **Compiled only — NOT uploaded, bench untouched**

**Also this session, record-keeping only:** TODO-1 corrected 🔴 → 🟢. It had carried a red status alongside a bracketed note saying its own compile proof was already met — the two contradicted each other for six days. No code changed; the proof (journal 2026-09-01 (1)) already existed.

### The evidence, captured before touching anything

33 consecutive 5 s windows, uptime 390–550 s, firmware at `e6daac8` with no local modifications, bench in the verified post-Phase-4 baseline. Full table in **`ai/evidence/2026-09-07-tf-clamp-preserved.md`**.

| | Range across 33 windows |
|---|---|
| SOURCE_NODE peak | −8.8 to −9.4 dBFS |
| RETURN_NODE peak | −55.3 to −57.2 dBFS |
| **True TF (SOURCE − RETURN)** | **−46.3 to −48.0 dB** |
| Printed `1kHz=` | **−24.0 dB in 33 of 33 windows** |
| Printed `500Hz=` | −23.3 to −24.0 dB |
| Printed `120Hz=` | −21.1 to −24.0 dB |

**−24.0 dB is `TF_DB_MIN - 6.0f` exactly** ([config.h:391](config.h#L391), [audio_engine.cpp:283](audio_engine.cpp#L283) pre-change). The printed values sit **22–26 dB above the truth**, and the 1 kHz bin is pinned at the rail 100 % of the time.

**The detail that makes this worse than a plain error:** 5 kHz alternated between `---` and ≈−23 dB across windows. `---` is the honest output (bin below `TF_SOURCE_GATE` → NAN). The ≈−23 dB is the railed one. **The same diagnostic printed both an honest and a dishonest rendering of the same physical condition, seconds apart, with nothing to distinguish them.**

### The change: annotate, do not alter

**The clamp is correct and is kept byte-for-byte.** It exists to stop a boundary-bin outlier poisoning the EMA history, and it does that job. The defect was never the clamping — it was that the rail was published into `tf_db[]` as a bare number with no way for any consumer to know.

So the fix is **purely additive**: record the clamp, and make the renderer say so.

- `AudioFrame` gains `tf_clamped_bits[FFT_BINS/32]` and `tf_clamped_count` ([audio_engine.h:162](audio_engine.h#L162)).
- `audioEngine_update()` sets bit *k* when bin *k*'s raw TF falls outside the window, clearing the mask each block so a stale bit can never mislabel a good measurement.
- `audioEngine_tfBinClamped(frame, bin)` is the read accessor; the mask is not to be indexed directly.
- The serial diagnostic prints `1kHz=RAIL[-24.0dB]` instead of `1kHz=-24.0dB`, plus a new `[Main] TF clamped bins: N of 512` line — because the spot-check samples five bins and the whole curve can be railed.

**No measured value changes.** `tf_db[]`, the EMA, the display curve, confidence and persistence are all bit-identical to before. The only difference is that a saturated bin is now labelled as one.

**Why a bitmask and not `bool[512]`:** `AudioFrame` is stack-allocated in `validation.cpp` (lines 83, 151, 467, 528) and the firmware holds a ~4 KB worst-case stack budget (`measurement_engine.cpp` FIX [stack-budget], which notes "AudioFrame is global precisely to avoid this"). 64 bytes instead of 512.

### Compile evidence — Teensy 4.1, `arduino-cli 1.4.1`

| | FLASH code | RAM1 variables |
|---|---|---|
| Baseline (`e6daac8`, stashed) | 158 340 | 218 752 |
| With the change | 158 532 | **218 816** |
| Δ | +192 | **+64** |

**+64 bytes of RAM is exactly the 64-byte bitmask** in the single global `s_frame`; `tf_clamped_count` fell into existing padding. That the arithmetic lands exactly is itself a check that only one `AudioFrame` is statically allocated, as the design intends.

Clean compile. The two warnings emitted (`payload_size` unused in `data_sender.cpp`, `setRotation` hidden in the Adafruit library) are both pre-existing and appear identically in the baseline build.

### ⛔ Not done, deliberately

- **Not uploaded.** The board is still running `e6daac8`. The bench is untouched and stays in the verified baseline until Conley has photographed it.
- **`display_engine.cpp` still renders railed bins as curve points** ([display_engine.cpp:347](display_engine.cpp#L347) reads `tf_db[bin]` directly). The accessor exists for it; wiring it in is a separate change against a separate consumer. Recorded on TODO-29.
- **TODO-18, TODO-27 and TODO-30 deliberately NOT bundled.** One defect, one change, one verification trail — Conley's call, and the right one given how much of this project's lost time came from confounded multi-variable changes.

**Note for whoever uploads this:** most source files are mode 400. `audio_engine.h` and `audio_engine.cpp` were temporarily set u+w to edit and restored to 400 afterwards; `guitar_rig_analyzer.ino` is back at 600. Verify with `stat -f '%OLp %N' *.cpp *.h *.ino` if anything looks off.

**Expected post-upload behaviour, to be checked against the pre-fix table above:** with RETURN still disconnected, `1kHz` should read `RAIL[-24.0dB]` and `TF clamped bins` should be a large fraction of 512. **That is not a regression — it is the same physical condition, finally reported honestly.** The number to watch is that no bin prints a bare value while its raw TF is out of range.

---

## 2026-09-07 (7) — ✅ ANALOG LEVEL SOLVED TOO. The 28 dB deficit was the 3.5 mm cable in the **headphone output jack**. SOURCE_NODE now reads −9.0 dBFS against a −10.3 dBFS prediction

**The bench finding (ChatGPT session, Conley at the bench):** the signal was being fed into the Audio Shield's **headphone output jack**, not into LINE IN L. The dedicated LINE-IN-L jumper had been unplugged from row 48 earlier in the debugging and never restored. With the headphone plug removed and that jumper returned to row 48:

| Probe point | Before | After |
|---|---|---|
| 48e (SOURCE_NODE) → GND, AC | 0.027 V<sub>rms</sub> | **0.143 V<sub>rms</sub>** |
| Audio Shield LINE IN L pad → GND, AC | — | **0.143 V<sub>rms</sub>** |

That is **14.5 dB** of analog loss removed — caused by driving a phone's line output into the SGTL5000's *headphone amplifier output*. (Output-into-output. Both ends are short-circuit protected and the levels below show no damage, but it is not a thing to repeat.)

### ✅ The digital reading now matches the analog measurement

Serial capture this session, 5 consecutive 5 s diagnostic windows, uptime 365–385 s, 1 kHz tone, no firmware change:

| Uptime | SOURCE_NODE peak | RETURN_NODE peak | ms/block | AudioMemory in use / max |
|---|---|---|---|---|
| 365 s | **−9.1 dBFS** | −57.6 dBFS | 46.3 | 12 / 20 |
| 370 s | **−9.2 dBFS** | −56.0 dBFS | 46.7 | 10 / 20 |
| 375 s | **−8.9 dBFS** | −56.3 dBFS | 46.3 | 16 / 20 |
| 380 s | **−8.9 dBFS** | −57.1 dBFS | 46.3 | 14 / 20 |
| 385 s | **−9.0 dBFS** | −56.3 dBFS | 46.7 | 12 / 20 |

**The arithmetic closes.** `SGTL5000_LINE_IN_LEVEL = 5` ([config.h:138](config.h#L138)) ⇒ 1.33 V<sub>pp</sub> full scale = 0.665 V<sub>pk</sub>. A 0.143 V<sub>rms</sub> sine is 0.202 V<sub>pk</sub> ⇒ 0.202/0.665 = 0.304 ⇒ **−10.3 dBFS predicted**. Measured **−9.0 dBFS**, a **1.3 dB** agreement. Back-solving, the codec sees 0.167 V<sub>rms</sub> where the DMM read 0.143 — 17 % high, comfortably inside handheld-DMM AC accuracy at 1 kHz combined with the PGA's ~1.5 dB step granularity and the codec's full-scale tolerance. **Nothing is left unexplained.**

**The old −39.1 dBFS figure is retired, not explained.** It was recorded 2026-09-06 (1), before the interconnect fix and with the headphone-jack misconnection in place. It should never be used as a comparison point again.

**RETURN crosstalk also improved by itself.** It was −50.1 dBFS / 11 dB below SOURCE on 2026-09-06 (1); it is now **−56 to −57.6 dBFS, 47.3 dB below SOURCE**. Both open questions from entry (6) are now closed by the same measurement.

**And run D's zero-corruption result holds live.** Every `[RAWDUMP]` window in this capture is a coherent, monotonic waveform with no single-sample impulses, `src_avail=1 ret_avail=1` throughout, and `AudioMemoryUsageMax` still pinned at 20. Six minutes of uptime, zero clip events.

### ⚠️ Corrections to the bench session's reasoning

1. **"RETURN_NODE / LINE IN L" conflates two different nodes.** LINE IN **L** is I2S channel 0, which is bound to **SOURCE_NODE** — `SOURCE_NODE_PHYSICAL_CH 0` ([config.h:173](config.h#L173)), and the binding is spelled out at [config.h:158](config.h#L158): "SOURCE_NODE → SGTL5000 Line In LEFT". RETURN_NODE is channel 1 = LINE IN **R**, which has nothing wired to it — it is the −57 dBFS crosstalk channel. Reading RETURN_NODE as the result of this test would have reported the noise floor as the answer.
2. **"The analog attenuation mystery is resolved" was over-claimed at the moment it was said.** On the evidence then in hand, 0.027 V<sub>rms</sub> predicts −24.8 dBFS while the recorded digital level was −39.1 dBFS — so the headphone-jack finding left ~14 dB unaccounted for and could not have been the whole story. It is moot *now* only because both of those numbers turned out to be stale. The inference was not valid at the time it was drawn; the conclusion happens to survive for a different reason.
3. **The two 0.143 V readings are not independent evidence.** 48e and the LINE IN L pad are the two ends of the jumper that had just been plugged in. Identical readings prove the jumper conducts — a continuity check, not confirmation that "the signal makes it all the way."
4. **The 54–66 kΩ / 603 kΩ resistance hunt on row 48 was never resolved, and no longer needs to be.** It was chasing a phantom: the attenuation was upstream, in the jack choice, not a stray resistive path into row 48. Left unexplained deliberately — do not spend more bench time on it.

### 🔺 New finding: the TF spot-check diagnostic is reading a clamp rail, not a measurement

Every window reports `1kHz=-24.0dB` exactly, with 120 Hz / 500 Hz / 5 kHz sitting at −21 to −24 dB. **−24.0 dB is not a measurement — it is the clamp.** [audio_engine.cpp:283](audio_engine.cpp#L283) does `constrain(tf_raw, TF_DB_MIN - 6.0f, TF_DB_MAX + 6.0f)` with `TF_DB_MIN = -18.0f` ([config.h:391](config.h#L391)), i.e. a hard floor at exactly −24.0 dB. The true transfer function right now is SOURCE − RETURN ≈ **−47 dB** (nothing is connected to RETURN), which is 23 dB below the floor, so every energised bin rails and the EMA converges onto the rail.

**Validation is unaffected** — `validation.cpp` computes TF from raw FFT means with the EMA bypassed ([validation.cpp:47](validation.cpp#L47)), so the 40 dB gate gap is measured on unclamped data. **The live path and the display are affected**, and the diagnostic prints a plausible-looking number with no indication that it is pinned. That is the same class of false signal as TODO-27's phantom −46.6 ms delta. Logged as TODO-29.

**Where this leaves the project:** Phase 4's SOURCE_NODE criterion is met on every axis — signal present, digitally clean, and at the level the analog measurement predicts. **Next:** strip the temporary RAWDUMP / AudioMemory diagnostics (TODO-30), settle TODO-29, then Phase 5.

---

## 2026-09-07 (6) — ✅ SOLVED. Shortening the I²S interconnect took corruption to EXACTLY ZERO across 360 windows

**The change:** Audio Shield moved adjacent to the Teensy; jumpers for **8 (DOUT), 20 (LRCLK), 21 (BCLK), 23 (MCLK), GND and 3.3 V** replaced with short, tightly-grouped wires. LINE-IN-L deliberately left long — the analog path is unchanged. **No firmware change. DOUT joint untouched from run C.**

*Pre-power safety check: 3.3 V→GND 8.06 kΩ, 5 V→GND 14.12 kΩ — matching the 8.06 / 13.99 kΩ measured days earlier, so no short was introduced.*

| Interconnect state | n | SRC/32 | RET/32 | clean % | worst | +0 dBFS % |
|---|---|---|---|---|---|---|
| A: long leads, DOUT broken | 420 | 5.95 | 5.14 | 3.1 % | 31 | 100 % |
| B: long leads, 1st rework | 360 | 24.72 | 26.85 | 0.6 % | 32 | 100 % |
| C: long leads, 2nd rework | 360 | 8.54 | 8.07 | 0.0 % | 20 | 100 % |
| **D: SHORT leads** | **360** | **0.00** | **0.00** | **100 %** | **0** | **0 %** |

**Run D bands: 0.00 / 0.00 / 0.00 / 0.00.** Zero corrupted samples in 11,520 per node. **Not one clip event in 30 minutes**, against 100 % of windows clipping in every previous run. Serial output dropped from ~597 KB to ~60 KB per 5-minute capture — a 10× reduction that is purely the absence of clip spam.

**Root cause: signal integrity on the flying-lead I²S interconnect.** Not a broken joint, not a damaged pin, not the codec, not firmware.

### What this retrospectively explains

- **Three DOUT reworks giving 5.95 / 24.72 / 8.54** — each changed wire length and routing, hence coupling and reflections. Never joint quality.
- **Perfect clocks, correct registers, good continuity, full DOUT logic swing, correct DOUT timing** — all true, and all irrelevant, because the corruption came from coupling in flight rather than from any endpoint.
- **Both channels always affected together** — shared DOUT line.
- **Wandering rate, spontaneous recovery, "warm-up" trends** — geometry-dependent coupling shifting with temperature and wire position.
- **Continuity passing on every pin** — DC continuity was never going to detect this.

### Hypotheses this kills

**My pin-8 contention-damage hypothesis is dead**, and so is "DOUT arrives too late". The physics that mattered was edge rate, not clock rate: the i.MX RT1062 drives ~1–2 ns edges, whose spectral content reaches ~350 MHz, where 10–20 cm flying leads are electrically long and behave as unterminated transmission lines with real reflections and crosstalk. **MCLK at 11.29 MHz running alongside DOUT was the likely dominant aggressor.**

### Lesson worth keeping

Days were spent testing endpoints — joints, pins, registers, drivers, firmware — because every endpoint measurement passed. **The fault was in the medium between them, and no endpoint test could ever have found it.** The one measurement that would have pointed here early is the one never taken: the physical geometry of the interconnect, treated as a circuit element rather than as plumbing.

**Phase 4's SOURCE_NODE criterion is now met: the pipeline receives the injected signal correctly, with zero digital corruption.**

**Next:** re-verify the analog chain now that measurements are finally trustworthy — the ~−39 dBFS level (≈28 dB below the −10.4 dBFS prediction) and the RETURN crosstalk at ≈−50 dBFS both need re-measuring against clean data. Then remove the temporary RAWDUMP and AudioMemory diagnostics.

---

## 2026-09-07 (5) — Scope persistence view clears DOUT timing and the driver. My pin-8 damage hypothesis is WEAKENED. New leading suspect: the flying-lead I²S interconnect

**Scope findings (persistence view, DOUT vs BCLK):**

- **DOUT changes at essentially the same instant as the BCLK launch edge**, then settles and stays stable for the rest of the bit interval.
- The opposite (sampling) BCLK edge is **~175–180 ns away** — consistent with a 2.8224 MHz BCLK's 177 ns half-period. **A large nominal stable-data window exists before sampling.**
- **DOUT shows full-looking logic transitions** — no evidence of a weak driver.
- Ringing is visually significant **but settles long before the sampling edge**, and a probe on a long flying lead can itself contribute ringing, so its true on-board magnitude is not established.

**Also noted at the bench: none of the scope measurements hold still** — the readings fluctuate continuously rather than settling on a value. That is consistent with the wandering error rate already quantified (run A bands 2.83–9.50 outliers/32).

### ❌ My pin-8 contention-damage hypothesis is substantially weakened

Entry (4) proposed that pin 8 was damaged by output-vs-output contention while `RA8875_RESET_PIN` was still 8. **The scope evidence argues against it:** a damaged output driver or input stage would typically show reduced swing, asymmetric levels or degraded edges. **DOUT shows full logic transitions and lands on the correct BCLK edge with ~half a bit period of margin.** The timeline for the contention remains real and worth remembering, but the electrical signature that would support damage is absent.

**"DOUT arrives too late at the Teensy" is likewise dropped as a primary hypothesis** — the measured setup margin is large.

### ✅ Continuity is confirmed and exhausted as a test

Every shield→Teensy pin has been continuity-checked and passes. **That test is now exhausted:** DC continuity says nothing about edge quality, intermittent contact under operation, or crosstalk. A jumper can read ~0 Ω and still be a poor 2.8 MHz interconnect.

### 🔺 New leading suspect: the physical interconnect geometry

A photo of the bench shows the shield↔Teensy connections are **long, loosely routed flying leads**. For I²S at this edge rate that is a serious signal-integrity suspect even with perfect continuity, because of large loop area, no controlled return path, mutual coupling between adjacent wires, and inconsistent geometry.

**This reframes the three-rework result from entries (3) and (4).** Those runs gave 5.95 / 24.72 / 8.54 outliers per 32 and were read as three different *joint qualities*. **A better explanation is that each rework changed the wire's length and routing, and therefore its coupling and reflections.** That fits without requiring any of the joints to have been defective — and it explains why three good-faith attempts all failed to fix anything.

### The experiment

Power off. **Do not rework DOUT again.** Instead eliminate the interconnect as a variable:

- Move the Audio Shield physically adjacent to the Teensy breakout.
- Replace the long jumpers for **8 (DOUT), 20 (LRCLK), 21 (BCLK), 23 (MCLK)** with the shortest practical wires — a few inches at most, shorter if possible.
- **Also shorten GND and 3.3 V.**
- Keep the six wires grouped tightly, avoiding large loops.
- Leave the analog breadboard section alone. No firmware changes.

Then repeat the identical ≥300-window measurement. **If the error rate collapses from ~8.5 outliers/32 toward zero, that is stronger evidence than anything obtained so far.**

**Falsifiability matters here:** given the natural wandering (2.83–9.50 in run A), only a **large** effect is interpretable. A collapse toward zero supports the hypothesis; a modest halving does not, and would argue the interconnect is not the dominant cause.

---

## 2026-09-07 (4) — Second DOUT rework FAILS the criterion. Three joint states, three error rates, none working. New hypothesis: pin 8 output contention damage

**Result of the second rework, 360 windows / 30.5 min, measured identically to the previous two runs:**

| Run | DOUT state | n | SRC out/32 | RET out/32 | clean % | worst | bands |
|---|---|---|---|---|---|---|---|
| **A** | original (found broken) | 420 | **5.95** | 5.14 | 3.1 % | 31 | 2.83 – 9.50 |
| **B** | 1st rework | 360 | **24.72** | 26.85 | 0.6 % | 32 | 21.87 – 27.01 |
| **C** | 2nd rework | 360 | **8.54** | 8.07 | 0.0 % | 20 | 6.93 – 10.03 |

**Pass criterion was "mean SOURCE outliers/32 well below 5.95, ideally near zero". Result: 8.54. FAIL.**

**C is statistically indistinguishable from A.** Run C's bands (6.93–10.03) sit inside run A's range (2.83–9.50). Run B's bands (21.87–27.01) do not overlap either. **So the second rework undid the damage of the first — 2.9× better than B — but did not improve on the original broken joint at all.**

### What three joint states tell us

**DOUT is causally involved** — three different physical states produced three distinguishable error rates, and B's separation from A and C is unambiguous. That result from entry (3) stands.

**But DOUT rework is not sufficient to fix it.** Three attempts at that connection have produced 5.95, 24.72 and 8.54 outliers per 32. **None is a working link.** Even the best of them corrupts **18.6 % of samples**.

**That number is the important one.** A synchronous digital bus running a few centimetres should have *essentially zero* bit errors. 18.6 % is not a marginal connection — it is a systematically broken one. **We have been treating this as a contact-quality problem when the scale of the error rate says something is fundamentally wrong with the DOUT path, not merely imperfect.**

### 🔺 New hypothesis: pin 8 was damaged by output-vs-output contention

**Until 2026-09-05, `RA8875_RESET_PIN` was defined as pin 8** (`config.h`, changed to 5 in commit `eeaec99`). `display_engine.cpp:36` passes it to `Adafruit_RA8875`, whose `begin()` does `pinMode(reset, OUTPUT)` and toggles it — **and it does that even when the display is absent, because the pin setup happens before the chip-ID check fails.**

**Meanwhile the Audio Shield's SGTL5000 was driving that same pin as DOUT.** That is a direct **output-driving-output contention**: the Teensy actively pulling pin 8 while the codec actively drove it, through however many boot cycles occurred while the shield was wired and `RA8875_RESET_PIN` was still 8.

**That is a credible mechanism for permanent damage** to either the Teensy's pin 8 input stage or the SGTL5000's DOUT output driver — and damage of that kind would explain everything the rework attempts cannot: why three separate good-faith joints all fail, why the error rate is enormous rather than marginal, why it wanders with conditions, and why clocks and registers all check out perfectly.

**This is a hypothesis, not a conclusion.** It fits the timeline and the symptom scale, but nothing yet demonstrates the pin or the driver is actually degraded.

**The discriminating measurement is electrical, on the scope, and specific:** probe DOUT (pin 8) while the codec is transmitting and check **logic levels and edge quality** — does it reach a full rail-to-rail swing, and are the edges clean? A damaged output driver or a damaged input stage typically shows reduced swing, asymmetric levels, or visibly slow edges. Earlier scope work confirmed DOUT was *toggling* (1.716 V DC average) but never examined its **levels or edges** — only that it was active.

**Next:** stop reworking the joint. Scope DOUT for amplitude and edge quality against a known-good reference — ideally compare against BCLK on the same probe and settings, since BCLK is driven by the Teensy and known healthy. If DOUT's swing or edges are materially worse than BCLK's, the damage hypothesis gains real support and the remedy becomes replacing a part, not remaking a wire.

---

## 2026-09-07 (3) — BREAKTHROUGH: DOUT pin 8 was found physically broken. Redoing it made corruption **4.2× WORSE** — the first proven causal link to a specific conductor

**The finding on the bench:** during the mechanical inspection, **DOUT (pin 8) was found physically broken** and was remade. Only that connection was touched; the breadboard analog section and all other jumpers were left alone.

**The measurement:** 360 windows over 30.5 min post-repair, against the 420-window cold-start run as baseline. Same firmware, scope disconnected, same 1 kHz tone, nothing else changed.

| Metric | PRE-repair (420 win) | POST-repair (360 win) | Change |
|---|---|---|---|
| Mean SOURCE outliers/32 | **5.95** | **24.72** | **4.2× worse** |
| Mean RETURN outliers/32 | 5.14 | 26.85 | 5.2× worse |
| Completely clean windows | 3.1 % | **0.6 %** | 5× fewer |
| Worst window (SOURCE) | 31/32 | **32/32** | — |
| Windows at +0.0 dBFS | 100 % | 100 % | unchanged |
| `AudioMemoryUsageMax` | 20 | 20 | unchanged |

**And it holds across every band — this is not one bad stretch:**

| Band | Uptime | n | SRC out/32 | RET out/32 |
|---|---|---|---|---|
| 1 | 80–580 s | 100 | 21.87 | 23.95 |
| 2 | 585–1095 s | 100 | 24.63 | 27.67 |
| 3 | 1100–1600 s | 100 | 27.01 | 28.45 |
| 4 | 1615–1910 s | 60 | 25.82 | 27.63 |

**The pre-repair bands spanned 2.83 – 9.50. The lowest post-repair band is 21.87 — 2.3× the *worst* pre-repair band.** The distributions do not overlap at all.

### Why this is a breakthrough despite being "worse"

**This is the first A/B in the entire investigation where the effect size dwarfs the wandering.** Every previous comparison was confounded by a fault that drifts 3.4× on its own; this one moved 4.2× with 780 windows behind it and zero band overlap. **Changing DOUT pin 8 changed the error rate — decisively.**

**That establishes DOUT pin 8 as causally involved.** Not inferred from probe loading, not inferred from correlation with handling — demonstrated by a deliberate change to that one conductor producing an effect far outside the fault's natural range.

**It also retrospectively explains the whole investigation.** A partially-broken DOUT would produce exactly what we spent days chasing: sporadic single-word errors, perfect clocks, correct register configuration, both channels affected together (they share the data line), a rate that wanders with contact conditions, and occasional total dropouts.

**Note it was never fully open.** A truly open DOUT would give pure garbage, yet coherent 1 kHz waveforms appeared throughout. So "broken" here means a marginal or partly-failed joint, not a severed connection — consistent with the intermittency.

### The actionable conclusion

**The remade joint is substantially worse than the broken one it replaced.** That is a defect in the rework, not a reason to doubt the diagnosis. **DOUT pin 8 should be redone again, carefully** — inspect for a cold joint, insufficient wetting, a bridged or partially-lifted pad, a nicked conductor, or a wire that is now longer or routed differently than before.

**Target for the next attempt:** mean SOURCE outliers/32 should fall **well below the pre-repair 5.95**, ideally toward zero, measured over ≥300 windows. Anything in the 20s means the joint is still bad.

**Housekeeping confirmed again:** `AudioMemoryUsageMax` stayed pinned at 20 across both runs — the leak remains dead. And **100 % of windows in both runs sat at +0.0 dBFS**, which re-proves that the peak metric is useless as a discriminator here; the raw outlier count is what carries the signal.

**Next:** rework DOUT pin 8 again with care, then repeat the ≥300-window measurement. This is now a single-variable experiment with a known baseline and a known-bad comparison point, which is the strongest position this investigation has been in.

---

## 2026-09-07 (2) — COLD-START RUN: AudioMemory is flat (leak ruled out). But the warm-up hypothesis did NOT reproduce — the fault rises then falls

**Setup:** board cooled overnight, scope fully disconnected, wiring untouched, 1 kHz tone playing. Diagnostic build with `AudioMemoryUsage()` telemetry uploaded on power-up and logging started immediately. **420 complete windows over 36.5 minutes**, uptime 0 → 2190 s, nothing touched.

*Caveat on "cold": the board was already enumerated when the upload watcher fired, so it had been powered for a brief unknown period (seconds) before the upload reset it. After an overnight cool-down that is a negligible warm-up, but it is not a perfectly instrumented cold start.*

### ✅ Result 1 — AudioMemory is completely flat. The leak hypothesis is dead.

```
[Main] AudioMemory: 10 in use, 20 max, of 128 allocated
```

**`AudioMemoryUsageMax()` read exactly 20 in every one of the 420 windows** — minimum 20, maximum 20, across 36.5 minutes and ~440 RAWDUMP arm/disarm cycles. In-use hovered around 13.

**This kills the resource-exhaustion explanation for the ~2370 s halt outright.** The pool is not climbing, not even slowly. The RAWDUMP block's arm/read/free/disarm path leaks nothing — it returns every block it takes. Combined with entry (1)'s non-reproduction of the halt, **the once-observed hang is now unexplained and unattributed, and our diagnostic is exonerated as its cause.** It remains a single unreproduced event.

### ❌ Result 2 — the warm-up/settling hypothesis did NOT reproduce

Corruption by 100-window band, SOURCE and RETURN outliers per 32-sample window:

| Band | Uptime | n | SRC out/32 | RET out/32 | mem in-use | mem MAX |
|---|---|---|---|---|---|---|
| 1 | 0–545 s | 100 | **2.83** | 2.26 | 13.1 | 20 |
| 2 | 550–1070 s | 100 | **9.50** | 8.81 | 12.9 | 20 |
| 3 | 1075–1575 s | 100 | **7.29** | 6.66 | 13.0 | 20 |
| 4 | 1580–2090 s | 100 | **4.82** | 3.65 | 13.0 | 20 |
| 5 | 2095–2190 s | 20 | **2.85** | 0.95 | 13.0 | 20 |

**The prediction was high-at-cold-start declining with time. What actually happened is low → high → low.** The error rate *started* near its best (2.83), climbed 3.4× to a peak in band 2 (9.50), then declined steadily back to 2.85.

The previous run (entry (1)) showed a monotonic decline, 6.75 → 0.83. **This run shows a hump. The two are not the same shape, so time-since-cold-start does not predict the error rate.**

**The honest reading: the fault wanders slowly, on a timescale of roughly ten minutes, with no reproducible relationship to elapsed run time.** The apparent "warm-up trend" in the previous run was most likely one arbitrary slice of that wandering — the same sparse-sampling trap as the earlier 3-window conclusions, just at a larger scale. **A single 47-minute run was not enough to establish a trend either.**

**Also notable: SOURCE and RETURN track each other closely** across every band (2.83/2.26, 9.50/8.81, 7.29/6.66, 4.82/3.65). Both channels rise and fall together, consistent with a single shared cause rather than two independent faults.

**No halt this run either** — 36.5 minutes continuous, still transmitting when logging stopped.

### Where this leaves things

- **Ruled out:** AudioMemory leak/exhaustion (definitively, by direct measurement); deterministic halt timing; monotonic warm-up.
- **Established:** the corruption is slow-wandering on a ~10-minute scale, affects both channels together, and is unrelated to audio-buffer resources.
- **Still unexplained:** the single halt at uptime ~2370 s, now with its most plausible cause eliminated.
- **Still unlocalised:** which conductor or component is marginal.

**Implication for method:** the wandering timescale (~10 min) is *longer* than a 100-window band (~8.5 min). **Any future comparison needs either much longer bands or interleaved A/B/A/B sampling** so that slow drift cannot masquerade as a treatment effect. Comparing two conditions measured minutes apart — which is every hardware test done so far — remains unsafe.

**Next:** with resource exhaustion eliminated and no reproducible time signature, the remaining productive move is a *mechanical* one — power off and inspect/re-seat the shield↔Teensy interconnect, since nothing electrical or firmware-side has survived scrutiny. That should be done as a deliberate one-shot change with a long before/after measurement, not another rapid A/B.

---

## 2026-09-07 (1) — Halt did NOT reproduce: 47 min continuous, no hang. And the fault improved 8× over the run with nobody touching it

**The discriminator test.** Power-cycled USB only, scope fully disconnected, tone off, wiring untouched, no rebuild. Logged continuously from uptime 55 s.

### Result 1 — no halt

**Ran 46.8 minutes continuously (uptime 55 → 2860 s, 540 diagnostic windows) and never stopped.** The previous run halted at uptime ≈2370 s; this one passed straight through that point and was still transmitting when logging ended at 2860 s.

**A deterministic resource exhaustion tied to a fixed cycle count is ruled out.** At ~5 s per RAWDUMP arm/disarm cycle, the previous halt was at roughly cycle 474; this run reached ~572 cycles with no ill effect.

**Stated at the right strength, per the correction adopted below:** non-reproduction at the same uptime **weakens** the resource-exhaustion hypothesis but does not eliminate it — a leak with a *variable* rate, or one gated on a condition that did not recur, would still fit. **Proving or killing it properly requires `AudioMemoryUsage()` / `AudioMemoryUsageMax()` telemetry** to show directly whether the 128-block pool is climbing. That is the honest next step for the halt question, not another timing run.

**Correction adopted:** an earlier draft implied a repeatable halt would prove "one leaked `audio_block_t` per RAWDUMP cycle." It would not. It would make deterministic firmware/resource exhaustion *strongly likely*, after which the arm/read/free/disarm paths would need inspecting and the pool instrumented to identify the actual mechanism.

### Result 2 — the fault fluctuates enormously, and improved over the run

SOURCE raw outliers per 32-sample window, 540 dumps:

| Outliers/32 | Windows | |
|---|---|---|
| 0 | 140 | 25.9 % |
| 1–2 | 161 | 29.8 % |
| 3–5 | 122 | 22.6 % |
| 6–10 | 102 | 18.8 % |
| 11–27 | 15 | 2.8 % |

**Mean 3.14 per 32 = 9.81 % of samples**, with a range from **0 to 27 out of 32**.

**And it improved steadily across the run, untouched:**

> mean outliers/32 — **first third: 6.75** → **last third: 0.83**

**An ~8× improvement over 47 minutes with nobody touching the board, no scope attached, and no configuration change.**

### What this establishes

- **The halt is not reproducible on time.** It happened once in ~40 min and not at all in the following ~47 min.
- **The corruption is not merely bidirectional noise — it has a slow downward trend within a run.** Combined with the previous session's spontaneous recovery, the fault behaves like something that *settles* while the board runs.
- **A warm-up / thermal / mechanical-settling character is now the best-fitting description.** A connection whose contact resistance or geometry changes slightly as the board warms would produce exactly this: high error rate when cold, improving over tens of minutes, still fluctuating window-to-window, and occasionally much worse.

Stated carefully: this is a **description of the behaviour**, not an identified mechanism. It does not name a conductor, and it does not distinguish a marginal contact from a temperature-sensitive component.

### Method note

The previous session's conclusions all rested on 3-window samples. This run has 540. The distribution above — where 26 % of windows are perfectly clean while others carry 27 corrupted samples out of 32 — shows exactly why: **any three consecutive windows could have "proved" almost anything.** The ≥100-window rule recorded in entry (7) is now demonstrated, not just asserted.

**Next:** the halt and the corruption are separate questions and should be pursued separately. For the halt, add `AudioMemoryUsage()`/`AudioMemoryUsageMax()` to the 5 s diagnostics — cheap, and it settles the leak question directly. For the corruption, any future comparison must run ≥100 windows per condition, and should ideally control for elapsed run time given the warm-up trend just measured.

---

## 2026-09-06 (7) — THE UNATTENDED CONTROL. Fault RECOVERS spontaneously — refuting monotonic degradation. And the board halted on its own after 8.5 minutes

**The control this investigation never had.** Scope fully disconnected (tips *and* ground), tone playing, nothing touched, no firmware change. 102 diagnostic windows captured across **510 s (8.5 min)** of continuous unattended running, uptime 1860–2370 s.

### ❌ First: the peak metric has been misleading us

`SOURCE_NODE peak` pegs at 0.0 dBFS whenever **one** sample in the ~2048-sample peak window is corrupted. It cannot distinguish "one bad sample in 2048" from "the stream is destroyed". **Raw outlier count per 32-sample window is the correct metric**, and reclassifying by it changes the conclusions.

### Answer 1 — Do the peaks recover, stay severe, or drift further?

**By peak: fluctuates, never recovers.** 67/102 windows at 0.0 dBFS (66 %), the rest ≈−1.4 to −2.8 dBFS, flipping between the two every few windows. Never returns to −38 dBFS.

**By raw outlier count — it RECOVERED:**

| Outliers per 32 (SOURCE) | Windows |
|---|---|
| 0 | **82** |
| 1 | 19 |
| 2 | 1 |

**Mean 0.21 outliers per 32 = 0.64 % of samples.** Compare:

| Phase | Outliers/32 | Coherent waveform? |
|---|---|---|
| Pin-8 loaded (1180–1210 s) | 9, 6, 1 | ❌ none, −2000 DC baseline |
| Pin-8 removed (1435–1455 s) | ~7–9 | ❌ none |
| Ground-only (865–900 s) | 0, 0, 1 | ✅ present |
| **Unattended (1860–2370 s)** | **mean 0.21** | ✅ present |

### Answer 2 — Does the raw morphology change?

**Yes — it improved markedly.** The coherent ~1 kHz waveform is present throughout and the DC baseline returned to near zero. Example, uptime 2360 s, zero outliers:

```
217 45 209 -143 -501 -321 -379 -379 -358 -326 -405 -407 -400 -361 -477 -489 -429 -402 -283 -435 -444 -413 -519 -314 92 -108 248 37 218 124 284 60
```

That is signal, not corruption — against the pin-8-era windows which had no waveform at all.

### Answer 3 — Spontaneous transitions with nobody touching it?

**Constantly.** Peaks flip between 0.0 and ≈−2 dBFS every few windows; outlier counts move 0→1→2→0 window to window. **All with the board completely untouched and the scope entirely absent.**

### ❌❌ This refutes my "monotonic degradation" hypothesis from entry (6)

Entry (6) concluded the fault had "only ever gotten worse, never better" and proposed **cumulative mechanical disturbance** as the explanation. **Both are wrong.** The fault recovered substantially with nobody touching anything — from ~7–9 outliers/32 to 0.21. A cumulative-damage model predicts no recovery, and recovery is exactly what happened.

That reading was built on five widely-spaced samples. 102 closely-spaced samples show something different: **the fault fluctuates in both directions on a timescale of seconds to minutes, spontaneously.** The apparent monotonic trend was an artefact of sparse sampling.

**Consequence, now firmly established: every probe A/B correlation from this session is confounded** — not by a trend, but by rapid bidirectional fluctuation. No conclusion about ground, pin 8, or full-scope suppression survives.

### 🚨 And then it stopped

**The board went completely silent at uptime ≈2370 s and has stayed silent for 12+ minutes.** It is still USB-enumerated (`arduino-cli` sees a Teensy 4.1, `/dev/cu.usbmodem195969201` present, connection `state: open`, no errors), but is transmitting nothing. The 5 s diagnostics come from `loop()`, so **`loop()` has stopped or Serial output has died** — a hang, not a reboot, since no boot banner appeared.

**⚠️ Do not attribute this halt to the hardware fault yet. Our own temporary diagnostic is a credible suspect.** The RAWDUMP block calls `audioCap_beginRawCapture()` / `audioCap_endRawCapture()` **every 5 seconds** — roughly 100 arm/disarm cycles during this run alone, and ~470 since boot. If even one `audio_block_t` leaks per cycle (a block queued between `readBuffer()` and `end()`, say), the 128-block `AudioMemory` pool would be exhausted within a few hundred cycles. That is a firmware-side explanation for a progressive stall that has nothing to do with the connection under investigation.

**The discriminating test is cheap and needs no rebuild: power-cycle and watch the uptime at which it halts again.** A repeatable halt near ~2370 s indicates a deterministic resource leak — almost certainly ours. A halt at a random, different uptime, or no halt at all, points elsewhere.

### Where this leaves the investigation

- **Ruled out:** monotonic degradation; cumulative mechanical disturbance; every probe-loading correlation.
- **Established:** the fault is spontaneous, bidirectional, and fluctuates over seconds-to-minutes; between events the pipeline decodes the 1 kHz tone correctly.
- **New and unattributed:** a complete halt after ~40 minutes of uptime, with our own diagnostic a live suspect.
- **Methodological:** use raw outlier count, not peak dBFS. Any future A/B test needs runs of ≥100 windows per condition to see through the fluctuation — three dumps is nowhere near enough, and that is why this session produced so many confident wrong answers.

**Next:** power-cycle, log uptime-to-halt. Resolve whether the halt is ours before touching the bench mechanically.

---

## 2026-09-06 (6) — Closure test FAILS: removing the pin-8 tip did NOT restore the clean regime. The fault has degraded MONOTONICALLY all session — every probe correlation so far is confounded

**The test:** pin-8 tip removed only. Ground clip still attached, pins 20/21 untouched, tone playing, no firmware change. Three dumps, uptime 1435 / 1445 / 1455 s.

**All three remain fully corrupted.** `+0.0 dBFS` on both nodes, clipping continuous, −1500 to −2200 DC baseline, wild excursions, no coherent waveform:

```
uptime 1455s
SOURCE: -1399 14294 -1475 -1385 -1436 -1485 -1424 -1449 -7548 31487 14277 -4111 -7573 -1532 -4990 555 -1467 -1553 -946 -7575 -7567 -1357 -1920 -2041 23515 -2012 -1946 -1907 -2048 -2024 -2040 -2006
RETURN: -1506 -1385 -1878 -1003 1467 -1847 -2409 -1042 8721 3294 -3573 -5315 -3068 -860 -1872 -1636 -1408 -1522 -1493 -1493 -1491 25630 -1519 -1623 -1629 -1587 -1648 -1645 -1648 -1683 -1570 -1628
```

**❌ My pin-8 causal claim in entry (5) is refuted.** If the ~10 pF load had caused the regression, removing it should have restored the previous regime. It did not.

### The real picture: monotonic degradation across the whole session

Peak history assembled from the session log plus 14 consecutive windows recovered from the serial ring:

| uptime | Condition | SOURCE peak | Regime |
|---|---|---|---|
| 605–645 s | Full scope (3 tips + gnd) | −38.9 / −38.2 / −39.1 | **CLEAN** |
| 735–900 s | Ground clip only | −2.2 … −2.3 | **mild** |
| 1180–1210 s | Ground + pin 8 tip | 0.0 / 0.0 / 0.0 | **SEVERE** |
| 1345–1410 s | Pin 8 removed (14 windows) | 0.0 throughout | **SEVERE** |
| 1435–1455 s | Pin 8 removed | 0.0 / 0.0 / 0.0 | **SEVERE** |

**The fault has only ever gotten worse, never better, and it has never recovered from any step.** Clean → mild → severe, monotonically, over ~14 minutes. It has now held severe for 275+ seconds across two different probe configurations.

### What that does to every conclusion drawn today

**Every probe-based A/B test this session is confounded**, because none of them controlled for a monotonic time trend. Each intervention coincided with a step down that would have happened anyway:

- "Full scope suppressed the fault" — already downgraded in entry (5); now clearly just the earliest, best point on a declining curve.
- "Ground alone does not suppress" — cannot be distinguished from continued decline.
- "Pin 8 loading caused the regression" — **refuted outright** by this test.

**A better hypothesis fits the monotonic shape: cumulative mechanical disturbance.** Every intervention has involved physically attaching or detaching a probe near the shield/Teensy jumpers. If a connection there is marginal, each handling event nudges it further out of contact — and nothing in the sequence would restore it. That explains both the one-way degradation and why removing the load changed nothing.

Stated carefully: **the electrical-loading explanation is refuted; a mechanical-disturbance explanation is consistent with all the data but is not yet proven.** The distinction matters, because they call for opposite next steps.

### Methodological correction for the rest of this investigation

**No further A/B probe tests until the time behaviour is characterised.** They cannot produce interpretable results against a drifting baseline. What is needed first:

1. **Stop touching the board.** Leave it completely alone, powered, tone playing, and log peaks for 10–15 minutes with no intervention. That establishes whether the severe regime is stable, recovers, or continues to degrade — the control this session never had.
2. Only then, if a stable baseline exists, resume single-variable tests — and repeat each one twice with an unattended interval between, so a trend can be separated from an effect.

**Also keep in mind for the guardrail already recorded:** "DOUT has almost no setup-time margin" remains an unproven hypothesis, and this entry weakens rather than strengthens it, since the evidence it rested on has been refuted.

**Next:** hands off the bench; unattended peak logging.

---

## 2026-09-06 (5) — Pin 8 (DOUT) probe test: loading DOUT makes it DRAMATICALLY WORSE, not better. Strong localization to DOUT — and it invalidates the "full scope suppressed it" story

**Two wording corrections adopted first, both raised in review and both right:**

1. **"A framing/format problem cannot produce an isolated bad word" was too strong.** The correct claim is that a **persistent static framing mismatch is ruled out** — a constant one-bit or word-length error would corrupt every word. An isolated bad word does **not** by itself prove the fault is on an I²S jumper; **a transient codec/ADC event could produce a single bad sample too.**
2. **"Damps ringing and sharpens edges" is electrically wrong.** Probe capacitance **damps ringing and *slows* an edge.** It cannot sharpen one. Any argument built on probe loading must use the correct mechanism.

That second correction turns out to matter enormously, because of what happened next.

**The test:** ground clip retained, **pin 8 (DOUT) probe tip added only** — no BCLK, no LRCLK tips. Tone playing. Three dumps, uptime 1180 / 1200 / 1210 s. All three: `SOURCE_NODE peak: +0.0 dBFS | RETURN_NODE peak: +0.0 dBFS`, clipping continuous, TF confidence a meaningless 100 %.

```
uptime 1180s
SOURCE: -1935 -1958 -2019 -2050 31885 23733 -2028 -2240 -7571 23799 -3006 -7610 31737 -1528 665 25142 230 32767 -2458 14338 22503 23695 -7744 -192 -1230 -1662 -1687 -1737 -219 -1540 -2003 -1510
RETURN: -2188 -2178 -2248 -2178 -2169 28988 -2194 -5879 -2104 -2081 -5892 -2469 -3928 737 24230 3921 -711 -2847 -3637 -659 23442 24116 -2440 -3760 -2135 -1786 -2060 -1943 -2164 -2135 -2161 -2145

uptime 1200s
SOURCE: 12145 -620 -1797 -1824 -1290 -7604 -1651 -1591 -1167 -587 -4272 -7583 -1808 -1501 -1632 -1852 32767 -2014 -1913 -2083 -2020 -2083 -2072 -2059 -2017 -2019 -2083 -2000 -1992 31582 -2074 -2111
RETURN: 25517 -1971 -1939 -1487 -1487 -4615 -1943 -1974 -1951 -1928 -1847 -1870 -1914 -1966 -1959 -2014 -2040 -2013 -1991 -1996 -2010 -2031 -2049 -2024 -1978 -2013 -2034 -2058 -2069 -2050 -1978 -2034

uptime 1210s
SOURCE: -2144 -1971 -2023 -1957 -2115 -2099 -2640 -2504 -2599 -2585 -2518 -2560 -2592 -2633 -2549 -2601 -2456 -2557 -2552 -2547 -2570 -8075 -2570 -2627 -2460 -2425 -2384 -2156 -1890 -1909 -2037 -1945
RETURN: -1842 -1940 -1805 2362 -2185 -1931 -1867 -2074 -1816 -1900 -1942 -1932 -1909 -1944 -1900 -1897 -1902 -1909 -1913 -1907 -1899 -1908 24725 -5630 -1953 -5620 -1965 -1547 -2965 -1787 3002 25287
```

**Adding ~10 pF to DOUT reverted the fault to its original severity.** The −2000 DC baseline is back, the wild excursions are back, and — decisively — **the coherent 1 kHz square wave is gone from SOURCE.** Compare the immediately preceding ground-only condition, same session, same tone: peaks −1.7 to −2.3 dBFS with a clean ±280 square wave.

| Condition (same session, same tone) | Peaks | Signal present? |
|---|---|---|
| Ground clip only | −2.3 / −1.7 / −2.3 dBFS | ✅ coherent ~1 kHz |
| **Ground + pin 8 tip** | **+0.0 / +0.0 / +0.0 dBFS** | **❌ gone** |

**This is a strong localization to DOUT (pin 8), and the physics is now the right way round.** Extra capacitance **slows** the DOUT edge. If the data is only just meeting the Teensy's setup time at the sampling clock edge, slowing it pushes the transition past the sampling instant and the bit is read wrong. **DOUT has very little timing margin** — ~10 pF, which is nothing on a healthy line, is enough to break it comprehensively. That is a far more coherent mechanism than the one in the previous entry.

**⚠️ And it invalidates the "full scope suppressed the fault" narrative.** Entry (1) recorded three clean dumps (−38.9 dBFS) with the *full* scope attached — probes on 20, 21 **and 8**. If loading pin 8 breaks the link, the full-scope condition should have been broken too. It wasn't. **Those two observations cannot both be explained by probe loading.** The likeliest reading is that the earlier full-scope "suppression" was **coincidental** — the fault is time-varying, and that window happened to be quiet. **The scope-suppression correlation should be treated as unproven from here on**, and this entry supersedes the weight placed on it in entries (1)–(4).

**What survives all of this, as the firmest result:** loading DOUT with ~10 pF reliably and repeatably destroys the link, across three dumps, against a directly-comparable three-dump baseline taken minutes earlier under otherwise identical conditions. **DOUT is the marginal node.**

**Next:** remove the pin-8 tip and confirm the ground-only baseline returns — that closes the loop and proves the degradation was caused by the load rather than by time. Then, if it does, the question becomes *why* DOUT has so little margin: jumper length, routing next to a clock line, a poor joint at either end, or the codec's drive strength into that wire.

---

## 2026-09-06 (4) — Ground-clip-only, RE-RUN with the tone confirmed playing. Result stands: ground alone does NOT suppress. And we caught a corruption event in the act — a single-sample impulse 51 dB above its neighbours

**The test, properly run:** scope ground clip alone on the GND rail, no probe tips, no channels, no wiring changes, **1 kHz tone confirmed playing**. Three dumps, uptime 865 s / 890 s / 900 s.

| | SOURCE peak | RETURN peak |
|---|---|---|
| uptime 865 s | −2.3 dBFS | −1.8 dBFS |
| uptime 890 s | −1.7 dBFS | −6.4 dBFS |
| uptime 900 s | −2.3 dBFS | −1.5 dBFS |

**The confounded result from entry (3) is confirmed with the stimulus present: ground alone does not suppress the fault.** Peaks sit at −1.7 to −2.3 dBFS against −38.9 dBFS with the full scope attached. The stimulus is unambiguously back — SOURCE shows the coherent ~1 kHz square wave in all three dumps, and TF confidence recovered to 80 % / 77 % / 7 %.

### The event, caught in a 32-sample window

```
[RAWDUMP] RETURN: -82 -80 -73 -77 -81 -86 -88 -75 -68 -76 27514 -79 -11 6 -19 4 -17 4 -8 -30 -5 -1 21 0 -6 -72 -32 -14 -23 22 -4 -32
                                                              ^^^^^ index 10
```

**One sample. `27514`, sitting between `−76` and `−79`.** That is **−1.5 dBFS wedged between neighbours at −52.7 dBFS — a 51 dB single-sample excursion**, and it accounts for the −1.8 dBFS peak reported in the same window. The corresponding SOURCE window is a clean coherent square wave.

**This is the single most diagnostic observation of the whole investigation.** The corruption is not a distortion of the signal, not a level error, not a framing offset applied continuously. **It is an isolated single-word error** — one I²S word decoded wrongly while the words either side of it are correct. A sustained framing or format problem cannot produce that; it would corrupt every word.

### Rate, across all conditions

| Condition | Corrupted samples | vs original |
|---|---|---|
| Original fault | 6–12 per 32 = **20–35 %** | — |
| Ground clip only | 1 in 96 ≈ **1 %** | ~20–35× better |
| Full scope (probes + ground) | peak == signal level over a 2048-sample window ⇒ **< 0.05 %** | a further ≥20× |

Three distinct severity regimes, and the ordering is consistent every time it has been measured.

### What this implicates

**Ground is now substantially ruled out as the mechanism.** Adding a ground path changed nothing measurable; adding probe tips changed everything. With the full scope attached, tips were on **LRCLK (20), BCLK (21) and DOUT (8)** — each presenting ~1 MΩ ∥ ~10 pF. On a line with marginal edges or reflections, that small capacitive load damps ringing and sharpens the sampled transition. **Isolated single-word errors are exactly what a marginal edge produces**: most clock edges are read correctly, an occasional one is not, and one word decodes wrong.

Stated as a hypothesis, not a conclusion: **signal integrity on one of the clock/data jumpers**, with the error rate set by how close that line's edges sit to the decision threshold.

**Next — isolate the conductor.** Keep the ground clip attached, then add **one probe tip at a time**: pin 8 (DOUT), then 21 (BCLK), then 20 (LRCLK), capturing dumps after each. If a single line's capacitive load drops the peaks back toward −38 dBFS, that names the marginal conductor. Nothing soldered, one variable at a time, fully reversible.

**Still no permanent ground jumper.** This round removes the last reason to consider one — ground demonstrably is not the mechanism.

---

## 2026-09-06 (3) — Ground-clip-only test: outliers NOT suppressed, so ground alone isn't the mechanism. But the 1 kHz signal vanished mid-test — CONFOUNDED, needs re-running

**The test:** scope ground clip alone reattached to the breadboard GND rail. No probe tips, no channels enabled, no wiring changes. Two dumps, uptime 735 s and 750 s.

```
[Main] SOURCE_NODE peak: -2.2 dBFS   |   RETURN_NODE peak: -5.6 dBFS      (uptime 735s)
[RAWDUMP] SOURCE: 8 -85 10 -45 -20 -53 -18 -49 -17 -83 61 -56 121 -77 110 -62 22 -126 95 -58 128 -161 33 -87 -80 -158 65 -95 1 -64 -37 -50
[RAWDUMP] RETURN: -32 -29 -8 -18 10 4 -6 -3 -5 -14 -14 -7 -5 1 -23 -17 -9 -9 9 -9 7 30 45 18 0 14 -26 -28 11 19 9 29

[Main] SOURCE_NODE peak: -2.2 dBFS   |   RETURN_NODE peak: -52.6 dBFS     (uptime 750s)
[RAWDUMP] SOURCE: -5 -17 45 -71 -23 -95 -35 -27 -96 -47 -45 55 -52 -54 224 38 -17 123 -25 -44 -41 30 -26 -12 -15 -90 -49 1 -18 -52 -43 8
[RAWDUMP] RETURN: 8 6 -14 -18 9 -13 -23 -10 -10 4 -14 3 -1 -21 -31 11 -8 -10 -13 -12 -4 11 15 -8 0 -12 -6 15 14 -41 -5 -15
```
Both dumps: `TF confidence: 0%`, every TF spot-check `---`. `CLIP_RETURN` still firing.

**⚠️ CONFOUND — the 1 kHz signal is no longer present.** The raw windows are low-level noise (±100, one excursion to 224), **not** the coherent ±280-count ~1 kHz square wave seen in all six previous dumps. TF confidence dropped from 68–100 % to **0 %**, and every spot-check bin reads `---`. Something changed about the input between the scope-removed test and this one — the tone stopped playing, or attaching the clip disturbed the input wiring. **The test as designed cannot be interpreted while the stimulus is absent**, and it must be re-run with the tone confirmed live.

**What can still be concluded, because it does not depend on the stimulus.** The outlier behaviour is measurable against the noise floor regardless of whether the tone is present:

| Condition | Peak | Raw bulk level | Outliers above bulk |
|---|---|---|---|
| Full scope (probes + ground) | −38.9 dBFS | ≈−41 dBFS | **≈2 dB — essentially none** |
| No scope at all | +0.0 dBFS | ≈−41 dBFS | ≈41 dB |
| **Ground clip only** | **−2.2 dBFS** | **≈−50 dBFS** | **≈48 dB** |

**The ground clip alone did not suppress the outliers.** Peaks stayed at −2.2 dBFS — barely different from the −1.9 dBFS seen with the scope entirely removed, and nowhere near the −38.9 dBFS of the full-scope condition. **That answers the second branch of the test: the earlier suppression depended on more than the ground path.**

**What that implicates.** With the full scope attached, three probe tips were also in contact — on **LRCLK (20), BCLK (21) and DOUT (8)**. A scope probe presents roughly 1 MΩ in parallel with ~10 pF. On a marginal or reflective line, that small capacitive load can damp ringing and clean up edges. **The suppression correlating with probe tips rather than ground shifts suspicion toward the clock/data lines themselves** — signal integrity on the jumpers, not the ground return. That is a hypothesis, not a conclusion; the confounded stimulus means this round proves less than it should.

**Next — re-run properly.** Confirm the 1 kHz tone is playing and reaching column 30 (measure it), then repeat the ground-clip-only capture. After that, the discriminating test is to attach **ground plus a single probe tip**, one line at a time (8, then 21, then 20), and see whether any individual line's capacitive load restores the clean −38 dBFS state. That isolates which conductor is marginal without soldering anything.

**Still not adding a permanent ground jumper** — this round makes that even clearer, since ground alone demonstrably isn't the mechanism.

---

## 2026-09-06 (2) — Scope-removed test: the answer is BOTH. Corruption returned, but ~400× rarer than the original fault. The scope was suppressing it AND something got reseated

**The test:** all probe tips and ground clips removed, board wiring untouched, USB and 1 kHz tone still connected. Three dumps at uptime 100 s / 120 s / 130 s.

| | SOURCE peak | RETURN peak | Clipping | Raw 32-sample window |
|---|---|---|---|---|
| **Scope connected** (previous session) | −38.9 dBFS | −50.1 dBFS | none | coherent ~1 kHz |
| | −38.2 dBFS | −49.2 dBFS | none | coherent ~1 kHz |
| | −39.1 dBFS | −50.1 dBFS | none | coherent ~1 kHz |
| **Scope removed** (this session) | **+0.0 dBFS** | **+0.0 dBFS** | **continuous** | **coherent ~1 kHz** |
| | **+0.0 dBFS** | −1.0 dBFS | **continuous** | **coherent ~1 kHz** |
| | −1.9 dBFS | −2.9 dBFS | **continuous** | **coherent ~1 kHz** |

Representative dump with the scope removed (uptime 100 s):
```
[Main] SOURCE_NODE peak: +0.0 dBFS   |   RETURN_NODE peak: +0.0 dBFS
[RAWDUMP] SOURCE: 271 227 282 291 267 255 244 261 239 272 273 210 231 183 282 -246 -308 -315 -304 -257 -287 -268 -313 -183 -298 -290 -299 -212 -226 -328 -292 -326
[RAWDUMP] RETURN: 29 29 11 48 9 24 9 4 -3 -5 -7 42 28 -4 -30 -92 -85 -86 -51 -91 -93 -95 -101 -106 -96 -101 -99 -75 -61 -94 -84 -83
```

**Neither of the two predicted outcomes happened cleanly. Both did, partially.**

**What returned:** full-scale outliers and continuous clipping. With the scope attached, no sample anywhere in the peak window exceeded ≈−38 dBFS across three dumps. With it removed, the peak immediately pegs at 0 dBFS. **The scope connection was demonstrably suppressing something.**

**What did NOT return:** the original fault. That produced a −2880 DC baseline, quantised levels at −2880/−6530/−8480, and 6–12 wild excursions *per 32 samples*. **None of that is present.** All three windows here are clean, coherent ±280-count ~1 kHz square waves — indistinguishable from the scope-connected dumps.

**The corruption rate has collapsed.** Originally ~6–12 corrupted samples per 32 (≈20–35 %). Now the raw windows are clean while the peak meter still sees outliers, which bounds the rate: the peak window is roughly `FFT_AVERAGE_COUNT(4) × 512-sample hop = 2048 samples`, of which the dump shows **32 = 1.6 %**. A rate near 1-in-2048 would be missed by a 32-sample window about 98 % of the time. **That is a reduction on the order of 400× from the original fault, not an elimination.**

**The outliers are definitely not signal.** The coherent waveform sits at −41.4 dBFS; the peak reads 0.0 dBFS. **41 dB above the audio** is not something the analog path can produce at these levels.

**⚠️ Sampling-bias caveat on my own evidence.** The RAWDUMP arms the queue, then reads the *first* block immediately. If corruption is bursty in time rather than uniformly distributed, this could systematically sample quiet moments. The "windows are clean" observation is therefore weaker than it looks, and should not by itself be read as "the data path is fine between events." Widening the dump or sampling at a random offset would settle it — deliberately not done yet, to avoid another firmware cycle mid-diagnosis.

**Revised reading.** Two things appear to be true at once: physical handling during the scope session **substantially improved** the connection (the baseline is far better than before and has stayed better with the scope gone), and the scope's ground clip was **additionally suppressing** the residual fault. That is consistent with a marginal contact whose severity varies with mechanical and electrical conditions — but it still does **not** identify which connection. The suspect set remains the shared ground path and the clock/data jumpers.

**Next: prove which connection is marginal.** Do not add redundancy — a second ground would very likely suppress the symptom again and destroy the evidence. The useful move is to reintroduce the scope's ground clip *alone* (no probe tips, no channels enabled) and re-run the dumps. If the peaks drop back to ≈−38 dBFS with only a ground path added, that isolates the fault to the ground return with a single reversible change and nothing soldered.

---

## 2026-09-06 (1) — ✅ THE FAULT HAS CLEARED. Scope proved all three clocks correct; the pipeline now decodes a coherent ~1 kHz signal. The fault points to the physical/interconnect layer, not DSP or static I²S config

**This is the breakthrough entry.** After the scope session the corruption stopped, and SOURCE_NODE is now receiving real audio for the first time on this bench.

### Scope results (RIGOL DHO804) — all clocks correct

| Signal | Pin | Measured | Expected | Verdict |
|---|---|---|---|---|
| LRCLK | 20 | **44.108 kHz**, stable, ~50 % duty | 44.1 kHz (1× Fs) | ✅ |
| BCLK | 21 | **~2.82 MHz** | 2.8224 MHz (64× Fs) | ✅ |
| MCLK | 23 | **~11.29 MHz** | 11.2896 MHz (256× Fs) | ✅ |

**Do not record the initial "Vpp = 468 mV" reading as a finding.** It was a **probe attenuation mismatch** — the probe was set to 1X while the scope assumed 10X. Corrected to 10X, the levels read normally. A healthy digital signal can look badly undersized from this alone, and it nearly became a false lead.

With the register comparison from 2026-09-05 (16) already showing both ends agree, and the scope now showing all three clocks at exactly the right frequencies with clean edges, **both the static configuration and the runtime bus timing are confirmed good.**

### The fault cleared

Three consecutive dumps at uptime 605 s / 635 s / 645 s, 1 kHz tone connected:

```
[Main] SOURCE_NODE peak: -38.9 dBFS   |   RETURN_NODE peak: -50.1 dBFS
[RAWDUMP] SOURCE: 286 277 280 293 270 298 266 265 245 262 264 249 268 237 293 -80 -339 -285 -302 -302 -312 -296 -305 -324 -332 -298 -320 -308 -303 -293 -297 -295
[RAWDUMP] RETURN: 70 65 67 70 69 47 58 42 66 58 53 61 36 46 29 -27 -45 -59 -61 -77 -90 -76 -77 -69 -52 -61 -69 -60 -73 -70 -51 -63

[Main] SOURCE_NODE peak: -38.2 dBFS   |   RETURN_NODE peak: -49.2 dBFS
[RAWDUMP] SOURCE: -329 -275 -303 -296 -273 -312 -251 -322 -293 -265 152 330 265 304 287 294 306 266 292 297 295 291 251 259 268 260 259 270 264 276 277 247
[RAWDUMP] RETURN: -81 -71 -71 -47 -55 -66 -71 -62 -70 -44 70 54 46 73 73 81 70 64 78 62 77 81 54 63 49 56 78 52 52 62 57 32

[Main] SOURCE_NODE peak: -39.1 dBFS   |   RETURN_NODE peak: -50.1 dBFS
[RAWDUMP] SOURCE: -353 -38 315 260 295 274 265 298 276 278 271 262 275 261 262 258 267 253 253 272 266 276 232 256 160 -277 -309 -267 -319 -298 -305 -315
[RAWDUMP] RETURN: -66 18 64 48 62 56 57 65 55 67 76 49 77 61 45 57 56 65 36 56 45 55 54 46 17 -31 -73 -85 -77 -69 -50 -65
```

**Everything that characterised the fault is gone.** No `+0.0 dBFS`. No `CLIP_SOURCE`/`CLIP_RETURN` in these windows. No wild excursions to ±20000–32767. No −2880/−6530/−8480 quantised levels. No DC baseline.

**And the signal is genuinely there.** Dump C has zero crossings at sample indices 1 and 24 — **23 samples per half-cycle ⇒ 958.7 Hz**, against 22.05 samples/half-cycle for an exact 1 kHz at 44.1 kHz. Amplitude is a consistent ±270–295 counts on both sides of zero. **This is the injected tone, decoded correctly.** Waveform shape is square rather than sinusoidal (flat tops, fast transitions), so the phone is evidently producing a square tone — worth knowing, not a fault.

### Diagnosis: the fault is strongly pointing toward a physical/interconnect issue, not DSP or static I²S configuration

**The decisive observation:** the same firmware went from corrupted full-scale raw samples to a clean ~1 kHz waveform after physical handling. Nothing in firmware or configuration changed between the corrupted runs and these clean ones — **the same flashed build produced both.**

**Deliberately NOT concluded: "intermittent connection, most likely ground."** An earlier draft of this entry said exactly that. Ground is *a* candidate, not an established one — the evidence below narrows the fault to the physical layer but does not identify which connection. **The suspect set is the shared ground path AND the clock/data jumpers**, because handling any of them during probing could have changed contact pressure.

Five observations support the physical-layer read:

1. **The corruption was burst-like** — long quiet runs (11–12 consecutive stable samples in dump 4 of the previous session) punctuated by wild values. That is the signature of an intermittent connection, not a design or format fault.
2. **Both channels were affected identically**, which implicates a shared resource — ground or a clock — rather than a per-channel path.
3. **Clocks and register configuration are now both proven correct**, eliminating the two leading structural hypotheses.
4. **The fault cleared during a session involving repeated physical handling** — probe clips attached, channels moved, the tone disconnected and reconnected. Any of that can change contact pressure on a breadboard or a solder joint.
5. **Two unexplained USB dropouts** earlier in this project — the board vanishing from the bus mid-session, once aborting an upload — are independently consistent with a marginal connection somewhere in the power or interconnect path, and were never explained.

The corrupted data also carried a **stable −2880 DC offset** that has now vanished entirely; the samples sit symmetrically about zero.

**⚠️ The critical caveat: the scope may be masking the fault rather than fixing it.** The probe's ground clip adds a path that was not there before. **Disconnect the scope and re-run the dumps before believing this is solved.**

**Do NOT pre-commit to a remedy.** An earlier draft of this entry proposed "add a second solid ground bond" as the fix if the no-scope test fails. That is premature — it presupposes which connection is marginal. **If corruption returns, the next step is to prove exactly which connection is at fault**, not to add redundancy blindly. Adding a second ground would very likely mask the problem again while leaving the real defect in place and unidentified. **No board wiring should be added or changed until the no-scope test result is known.**

### Two open questions raised by the clean data

1. **Level is ~28 dB below prediction.** At `LINE_IN_LEVEL 5` (1.33 V<sub>pp</sub> FS), 0.143 V<sub>rms</sub> should read ≈ −10.4 dBFS. Measured −38.9 dBFS. Either the phone output is far lower than during the earlier headroom sweep, or something is attenuating the path. Needs re-measuring at the buffer output before any calibration.
2. **RETURN_NODE reads −50 dBFS with nothing connected to it** — roughly 11 dB below SOURCE, tracking the same waveform. That is channel crosstalk, plausible on a breadboard but worth quantifying before it contaminates a transfer-function measurement.

**Next:** disconnect the scope, re-run dumps, and see whether the fault returns. That single test decides between "fixed" and "masked".

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

