# ADR-004 — Return source is selected by the operator; TS on every boot

**Status:** ACCEPTED · 2026-09-16 · **implemented in firmware at `ae02a8b`;
compile-verified, NOT bench-verified** (see *Implementation status*)
**Decided by:** Conley Vidal
**Supersedes:**
- [ADR-003](ADR-003-jack-presence-is-a-ux-feature.md) § *Phase 7 — resolve Return
  Source Detection Architecture*: the preference recorded there is now binding
- `signal_router_contract.md` § *Routing Policy — Return Source Selection* (the
  presence-driven policy table with XLR default priority), the return-source
  steps of § *State Machine*, the return rows of § *Measurement Arm Validity*,
  and Phase C's `AUTO` mode
- TODO-7's proof line and the former Phase 7 sign-off criterion at
  `docs/breadboard_bringup_v3.md` line 1702: *"Full route matrix (4 jack
  combinations) produces correct route description on Serial"*. That criterion
  presumed auto-detect. **Both were replaced as part of this ADR's documentation
  change**, and the old text is kept here and in git history for provenance

**Relates to:** [ADR-002](ADR-002-jack-presence-detection.md), still in force and
unweakened: if presence detection is built for informational use, ADR-002
governs how. ADR-003 remains in force apart from the section superseded above.
**Affects:** TODO-7, TODO-8, `signal_router.{h,cpp}`, `signal_router_contract.md`,
the eventual serial/Pi UI return-selection control

---

## Decision

1. **The operator's selection is the only thing that sets the return source.**
   The choices are `TS` and `XLR`. There is no `AUTO`.
2. **The return source resets to TS on every boot and is not saved.** TS is the
   state RELAY_RETURN is already in when de-energised.
3. **Jack presence must not choose the return source or decide whether a
   measurement is valid.** If presence detection exists, it may only show
   status or warnings (e.g. *"XLR selected, no XLR plug detected"*).
4. **Changing the selection is a route change.** It takes effect immediately
   and goes through the existing `audioEngine_setRoute()` → ROUTE_CHANGED
   chain, so any measurement in progress is invalidated. It must not wait
   for a jack event.
5. **A return source is always selected, so the return routing configuration
   is always defined. This says nothing about whether a return signal is
   physically connected.** "No return" is not a reachable routing state under
   this architecture. Consequently, once firmware implements this ADR,
   **`route_valid` means "the return routing configuration is defined". It
   does not establish physical return connectivity.** The name is historical.
   It is not a reason to reintroduce presence detection into validity.

---

## Why

**This is test equipment, not a consumer pedal.** Which return feeds line-in R is
part of what a measurement means. A hardware presence signal must not change it
without the operator knowing, including when a plug is added or removed mid-session.

**TS at boot, not saved, because the startup state then has no transitions.**
With RELAY_RETURN de-energised, the hardware is physically on TS. If the
software also starts at TS, the relay, software state, displayed state and
operator expectation all begin in agreement, and nothing needs actuating.
A saved XLR choice would add a startup sequence: boot physically on TS, read
the saved value, energise the relay. That is more state to reason about, and
it opens a window where the displayed configuration and the hardware disagree.
For a measurement instrument, a known startup state is worth more than the
convenience.

---

## Context — what the active tree does today

Traced 2026-09-16 in `signal_router.cpp` / `.h`, plus a repository-wide search
for callers.

**`signalRouter_setReturnPreference()` does not implement this architecture.**
ADR-003 cited it as evidence that the software anticipated explicit selection.
That overstated it: it is a **tie-breaker inside auto-detect**, not an
operator authority.

| Behaviour | Where | Conflict with this ADR |
|---|---|---|
| Jack presence decides first; the preference is read only when **both** TS and XLR are detected | `computeReturnSource()`, cpp:134–149 | Decision 1 |
| Preferred jack absent → the other one is used silently | header comment h:250 | Decisions 1, 3 |
| Neither jack detected → `ReturnSource::NONE` | cpp:138 | Decision 5 |
| `route_valid = (return_source != NONE)`, so validity depends on presence | cpp:186 | Decision 3 |
| Initial source computed from jack state at init | cpp:227 | Decision 2 |
| **Changing the preference never takes effect unless a jack also changes**: the setter only stores it, and `update()` returns before recomputing when no debounced state changed | cpp:400–409, cpp:264 | Decision 4. **In the explicit architecture this is a correctness bug, not a quirk** |

**Nothing downstream depends on the auto-detect behaviour.** Nothing calls
`setReturnPreference`, and no serial command exists for it. `canMeasure()` and
`canInject()` have no callers. The main loop discards `update()`'s
`RouterEvent` (`guitar_rig_analyzer.ino:352`). Pin 22's detect sense is recorded
as *"not built, sense unverified"* (`config.h:280`). Changing the policy
therefore breaks no consumer.

---

## Implementation status

| Step | Status |
|---|---|
| Decision + contract | ✅ `9e41943` |
| Firmware | ✅ **`ae02a8b`**: compiles (teensy41), and the new symbol is present in the ELF. Pre-commit ordering audit: post-switch audio cannot enter an in-progress measurement before ROUTE_CHANGED aborts it, for all currently reachable arm paths (journal 2026-09-16 (5)) |
| **Bench verification** | ❌ **None.** The pin-15 RELAY_RETURN driver is not built. Relay switching, TS/XLR routing and physical TS-at-power-on (which depends on the driver's base pulldown) are all unobserved. TODO-7's proof is the acceptance test |

*Historical:* this section originally recorded "documentation and contract only;
firmware deliberately untouched". The firmware requirements it listed are kept
below as the specification `ae02a8b` was checked against.

The firmware change must at least:

- replace presence-driven `computeReturnSource()` with the operator selection,
  initialised to TS in `signalRouter_init()`;
- apply a selection change immediately: relay, then `audioEngine_setRoute()`;
- stop `route_valid` depending on return-jack presence, and document it as
  "routing configuration defined", not "return connected" (Decision 5);
- provide a way to make the selection, e.g. a serial command (no letter chosen
  here);
- retire or redefine `ReturnPreference::AUTO` and
  `setReturnPreference()`. Do not quietly keep the old name with new
  semantics.

---

## Consequences

### Phase 7 hardware

- **Pin 22 is not required for Phase 7.** Keep the Switchcraft #11 on Rig Return
  TS. **Do not replace it, and do not build a TS-return detection mechanism** to
  satisfy the old route matrix.
- Phase 7's hardware work is the RELAY_RETURN driver on pin 15 plus the signal
  wiring.

### TODO-7 acceptance (replaces the 4-jack route matrix)

To be run **after** the firmware change:

> **PASS:** At boot, with no operator action, RELAY_RETURN is de-energised and
> the router reports TS. Selecting XLR energises RELAY_RETURN (contacts transfer
> by continuity), raises ROUTE_CHANGED, and changes the route description.
> Selecting TS reverses all three. The reported source follows the selection
> **whatever jacks are plugged in, including none**. A TS signal on Rig Return
> reaches line-in R when TS is selected. A power cycle returns to TS.

Carrying XLR signal end-to-end remains Phase 8's job.

### TODO-8

The routing half of Phase 8's *"XLR + microswitch detect both work end-to-end"*
no longer depends on detection. The microswitch design (journal 2026-09-13 (10))
is unaffected as a design, but whether to build it is now a question for the
informational-status feature, not for routing. **Revisit that criterion
before Phase 8; this ADR does not rewrite it.**

### Not decided here

- Whether presence warnings are implemented at all, and for which jacks.
- Rig Send / injection gating, still deferred per ADR-003.
- Where the selection appears in the Pi UI.

### Explicitly rejected

- **Saving the selection across reboots.** See *Why*.
- **Automatic detection**, and **keeping `AUTO` as an optional mode alongside
  explicit selection.** Either one reintroduces presence-driven topology
  changes.
- **Treating `setReturnPreference()` as already sufficient.** See *Context*.
- **Changing firmware in the same commit as this decision.**

---

## Provenance note

Reached from a code audit (`signal_router.cpp` `computeReturnSource`,
`updateStatus`, `signalRouter_init`, `signalRouter_update`,
`signalRouter_setReturnPreference`; `signal_router.h:93–100, 241–253`;
`guitar_rig_analyzer.ino:307–352`; `config.h:243–281`; a caller search), not
from the contract's description of itself. Journal **2026-09-16 (4)**.
