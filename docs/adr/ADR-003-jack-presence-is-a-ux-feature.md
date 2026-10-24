# ADR-003 — Jack presence detection is a UX/automation feature, not a hardware requirement

**Status:** ACCEPTED · 2026-09-13 · **§ Phase 7 SUPERSEDED 2026-09-16 by
[ADR-004](ADR-004-return-source-is-operator-selected.md)** (explicit selection
made binding). The rest of this ADR is unchanged and in force.
**Decided by:** Conley Vidal
**Supersedes:** the Phase 5 sign-off criterion *"detect events fire"*
(`docs/breadboard_bringup_v3.md` line 1700), and the implicit assumption across
TODO-3, TODO-5, TODO-7 and TODO-11 that every jack requires mechanical presence
detection
**Relates to:** [ADR-002](ADR-002-jack-presence-detection.md), which constrains
*how* detection may be implemented if it is implemented at all. **ADR-002 is
unaffected and remains in force.**
**Affects:** TODO-5, TODO-7, TODO-11, `signal_router.{h,cpp}`, `config.h`,
`docs/breadboard_bringup_v3.md` Phases 5/7/8, and the jack BOM

---

## Decision

**Jack presence detection is a UX / automation feature. It is not a hardware
requirement, and no phase may be blocked on it until the feature it serves is
itself shown to be required.**

The project had treated "the jack must report presence" as a build requirement.
A trace of the active tree shows that for the instrument input it protects,
routes, enables, disables and validates nothing. Phase 5 was therefore waiting
on a GPIO transition that no downstream logic reads.

**The Switchcraft #11 is not failing at being a guitar jack.** It was assigned a
second job — mechanical presence detection — that the product does not currently
need. **Do not buy a 12A. Do not replace the #11s.**

---

## Context — what the code actually consumes

Traced in the active tree, 2026-09-13. `s_jack_instrument.debounced` appears in
three places: the status struct, two serial prints, nothing else.

| Decision path | Depends on |
|---|---|
| `computeReturnSource()` | `return_ts`, `return_xlr` only |
| `route_valid` | return source ≠ `NONE` |
| `can_inject` | `route_valid && rig_send` |
| `buildDescription()` | return source + injection state |
| `applyReturnRelay()` | return source |

**Instrument presence appears in none of them.** Its only downstream consumer is
`data_sender.cpp:603`, packing it as bit 0 of the router-status packet — a UI
indicator. That packet's chain is `presentation_routerStatus()` →
`dataSender_sendRouterStatus()`, and **`presentation_routerStatus()` is never
called from the application.** `signalRouter_canMeasure()` and
`signalRouter_canInject()` are never called either.

**So instrument presence currently feeds nothing at all**, and when the Pi UI is
wired up it will feed one indicator.

### Which detects are actually load-bearing

| Pin | Jack | Function | Status |
|---|---|---|---|
| 16 | Instrument In (#11) | **none** — informational only | **not required** |
| 17 | Rig Send (#11) | gates `can_inject` | inert; injection not implemented |
| 22 | Rig Return TS (#11) | `computeReturnSource()` → **drives `applyReturnRelay()`** | genuinely load-bearing |
| 24 | Return XLR | same as pin 22 | microswitch already designed |

---

## Decisions by phase

### Phase 5 — instrument jack detection REMOVED from acceptance

**Keep the Switchcraft #11.** Pin 16 may remain implemented in firmware, but its
state is **informational and non-authoritative**.

**Revised acceptance criterion, replacing *"detect events fire"*:**

> **PASS:** A standard 1/4" TS guitar connected to Instrument In passes cleanly
> through the intended analog signal path with normal level and no unintended
> loading, distortion, oscillation, or loss of signal.

Requiring the original criterion would mean redesigning functioning hardware to
satisfy an obsolete test.

### Phase 7 — resolve Return Source Detection Architecture BEFORE changing hardware

> **SUPERSEDED 2026-09-16 by [ADR-004](ADR-004-return-source-is-operator-selected.md).**
> Explicit operator selection is now binding: TS on every boot, not saved, and
> presence detection is informational only. Pin 22 is not required for Phase 7.
> **Correction to the text below:** `signalRouter_setReturnPreference()` is *not*
> evidence that explicit routing was anticipated. It is a tie-breaker inside
> auto-detect, consulted only when both returns are detected (see ADR-004 § Context).
> The original text is kept below for the record.

Two legitimate architectures, and the choice is a **product decision, not an
electrical one**:

1. **Automatic routing** — detect which return is physically connected and select
   it. Requires a reliable presence mechanism; the #11 alone is not sufficient.
2. **Explicit routing** — the operator selects the return. `signalRouter_setReturnPreference()`
   already exists, which is evidence the software architecture anticipated this.

**Preference recorded, not yet binding: explicit selection**, unless later
testing demonstrates a compelling reason for automatic detection. The rationale
is that this is **test equipment, not a consumer pedal.** An explicit
`Return: TS / XLR` choice makes the measurement configuration unambiguous and
avoids letting a hardware-presence signal silently determine a scientifically
meaningful routing choice.

**Do not replace the TS return #11 until this is decided.** Note that TODO-7's
current proof line — *"Full route matrix (4 jack combinations) produces correct
route description"* — presumes automatic detection and **must be revisited as
part of this decision.**

### Injection phase — resolve the functional requirement behind Rig Send detection separately

**Do not assume a mechanical jack switch is the answer.** First define what is
being prevented. If the concern is injecting a sweep with no rig connected, note
that **a plug being present does not prove the downstream rig is connected
correctly** — so plug presence may be the wrong signal entirely, not merely an
inconvenient one. Decide the requirement before selecting a mechanism.

---

## Consequences

### Accepted

- Phase 5 closes on signal path alone. Its remaining work is measurement, not
  construction or procurement.
- **$0 spend.** No jacks replaced, no microswitches bought.
- `e5b702b` **stays in the tree unchanged.** The router runs, reads four pins and
  gates nothing. There is no benefit to removing it because some inputs are not
  yet authoritative — it is the framework in which the Phase 7 decision will be
  made, and removing it would cost work now and again later.
- ADR-002 remains in force and unweakened. It governs *how* detection may be
  built; this ADR governs *whether* it is needed. **If Phase 7 chooses automatic
  detection, ADR-002's constraint applies in full.**

### Costs

- The Pi UI's jack indicators will show a permanently-absent instrument jack
  until pin 16 is either wired to something real or the indicator is removed.
  **Acceptable, but it must not be read as a fault.**
- Three decisions are deferred rather than made. Each is recorded above with the
  question it must answer.

### Explicitly rejected

- **Buying a Switchcraft 12A.** Its tip-shunt topology is ruled out by ADR-002,
  and it solves a problem the product does not have.
- **Replacing the #11 with a TRS jack now.** Viable (see journal 2026-09-13 (11)
  and (12)) but premature: it would be bought to serve a feature not yet
  established as required.
- **Removing the signal_router integration.** See above.

---

## Provenance note

Derived from a trace of the active tree on 2026-09-13, not from design intent:
`signal_router.cpp` (`computeReturnSource`, `updateStatus`, `buildDescription`,
`applyReturnRelay`), `data_sender.cpp:596–610`, `presentation.cpp:68–69`, and a
repository-wide search for callers of `signalRouter_canMeasure()` and
`signalRouter_canInject()` (none). Journal **2026-09-13 (13)**.

The branch that led here began by accepting a runbook drawing as as-built fact;
this ADR was reached by reading the code instead of the documentation, and that
is the reason it reverses a conclusion the documentation had made look settled.
