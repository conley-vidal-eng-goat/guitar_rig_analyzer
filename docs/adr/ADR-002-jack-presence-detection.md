# ADR-002 — Jack presence sensing must be electrically independent of the audio signal node

**Status:** ACCEPTED · 2026-09-13 · **worked example CORRECTED 2026-09-13** —
see *Correction* below. The Decision and invariant are unchanged.
**Decided by:** Conley Vidal
**Supersedes:** the Phase 5 jack-detect topology prescribed by
`docs/breadboard_bringup_v3.md` lines 1118–1221 (Switchcraft #11 SHUNT → Teensy
pin 16, corrected by a firmware invert)
**Affects:** `config.h` (`JACK_*_PIN`, `JACK_*_DETECT_INVERTED`),
`signal_router.{h,cpp}`, `docs/breadboard_bringup_v3.md` Phases 5/7/8,
`docs/asbuilt/netlist.md`, TODO-5, TODO-23, TODO-44, and the eventual PCB

---

## Decision

**Jack presence sensing must be electrically independent of the high-impedance
audio signal node.**

Digital presence detection must not impose a DC loading requirement on an audio
node that conflicts with that node's analog requirements.

A detect circuit **may** observe the audio node directly, including through a
high-impedance buffer or comparator, provided its effective loading does not
violate the audio design's impedance, bias, or signal-integrity requirements.
What is forbidden is the loading, not the connection.

**This ADR does not choose the replacement topology.** It establishes a
constraint that any candidate must satisfy, and records that the selection
remains open. See *Candidates — selection unresolved* below.

### The governing invariant

> A detect function and an audio function must not share a node when satisfying
> the detect threshold or bias requirement would force that node outside the
> audio path's permitted impedance, bias, or signal-integrity range.

---

## ⚠️ Correction — 2026-09-13, after this ADR was accepted

**The installed J4 has no switched contact.** Bench continuity identification
(power off, DMM) found lug #1 = SLEEVE/GND, and **lug #2 continuous with the long
spring both empty and with a TS plug inserted** — a pair that does not open is
not a switch. Lug #2 and the spring are two parts of the TIP conductor. Relayed
but not verified here: Switchcraft lists the **#11** as *2 Conductor, Open
Circuit*; the shunted variant is a different part (e.g. **12AW11**). Evidence:
`ai/evidence/2026-09-13-J4-continuity-identification.md`, journal **2026-09-13 (9)**.

**What this changes and what it does not:**

- **The Decision and the governing invariant are UNCHANGED and were never
  dependent on J4.** They constrain any detect topology on any audio node.
- **The arithmetic below is UNCHANGED and still correct.** 22 kΩ pull-up,
  < 9.4 kΩ required for a guaranteed LOW, ~1 MΩ wanted — that conflict is
  general to GPIO pull-up detection on a high-impedance audio node.
- **The J4 worked example is WRONG in its premise.** Section 1 below reasons
  about a SHUNT→TIP path that **does not exist on this jack**. It is retained,
  not deleted, because the reasoning is valid for a jack that *does* have a shunt
  contact — read it as *"why a shunted jack would also fail here"*, not as a
  description of the installed part.
- **The retained experiment is WITHDRAWN — it cannot be performed.** There is no
  SHUNT contact to wire to pin 16. See the experiment section below.
- **Root cause of the error:** a component description in a build document
  (`breadboard_bringup_v3.md` lines 1105–1113, which draw a SWITCH terminal) was
  accepted as as-built fact. A document describing what a part does is not
  evidence that the part on the bench is that part.

**Consequence now in scope:** the parts list (runbook line 181) specifies
Switchcraft #11 ×10 for **Phase 5 and Phase 7**. If the installed part is
representative, **no 1/4" jack in the design can report presence**, which makes
this a parts/design blocker rather than a wiring problem. **Phase 8 is
unaffected and is already ADR-002-compliant** — its XLR detect uses a separate
COM-NC lever microswitch wired pin 24 → GND, an independent contact that never
touches an audio node.

---

## Context — the proof

The installed instrument jack is **J4, a Switchcraft #11, which is TS, not
TRS.** Its three terminals are **TIP — SLEEVE — SHUNT/SWITCH**. SHUNT is a
normally-closed contact tied to TIP that a TS plug mechanically opens on
insertion. No ring conductor is involved. *(J1, a 3.5 mm jack elsewhere in the
build, genuinely is TRS — do not let its terminology leak into J4's.)*

The runbook wires SHUNT → Teensy pin 16 with `INPUT_PULLUP` and corrects the
resulting sense with a firmware invert. That cannot work on this circuit, for
two independent reasons.

### 1. Even a shunted jack would not change state on this circuit

*(Retained for a jack that HAS a shunt contact. The installed J4 does not — see Correction above.)*

TIP is `col 30`. The as-built `SOURCE_IN` net is `col 30 · J4 tip · C1`, where
**C1 is a 10 nF ceramic** (`docs/asbuilt/netlist.md` line 95, tagged `PHYS`),
and `col 30` has no other connection. C1 blocks DC. Therefore:

| State | Path from pin 16 | Pin 16 |
|---|---|---|
| Empty | SHUNT → TIP → col 30 → C1 → *DC blocked* | pull-up wins ⇒ **HIGH** |
| TS plug inserted | SHUNT open | pull-up wins ⇒ **HIGH** |

**No value of a polarity define can recover a transition the hardware does not
produce.** An invert maps HIGH→0 or HIGH→1; it cannot manufacture a state
change. The runbook's own truth table at line 1118 states this
(*"matches if we wire TIP to GND but TIP carries signal... so it doesn't"*) and
then prescribes the invert regardless, dismissing the Cliff CL1384
make-on-insertion alternative at line 1221.

### 2. Giving TIP a DC reference is arithmetically incompatible

`INPUT_PULLUP` on Teensy 4.x is `IOMUXC_PAD_PUS(3)`
(`cores/teensy4/digital.c:180`). On i.MX RT1062 the PUS field is
`0 = 100 kΩ pull-down, 1 = 47 kΩ pull-up, 2 = 100 kΩ pull-up, 3 = 22 kΩ pull-up`.
The internal pull-up is therefore **22 kΩ**.

For pin 16 to read LOW it must be pulled below V<sub>IL</sub> ≈ 0.3 × V<sub>DD</sub>
≈ 0.99 V through a divider against that pull-up:

| Internal pull-up | R<sub>TIP→GND</sub> required for a guaranteed LOW |
|---|---|
| **22 kΩ** — what `INPUT_PULLUP` actually sets | **< 9.4 kΩ** |
| 47 kΩ | < 20.1 kΩ |
| 100 kΩ — the most favourable option the chip offers | < 42.9 kΩ |

That resistor sits on the TIP node, so **it is the input impedance the pickup
sees.** TODO-23 targets **~1 MΩ** and already judges the present ~100 kΩ too low
for a 6–250 kΩ pickup.

**The two requirements are ≥23× apart in the best case and ~106× apart as
configured, pulling in opposite directions.** No single resistor value satisfies
both. This is an architectural contradiction, not a component-value optimisation.

### Why the current diagnostic jumper appears to work

A `col 30` → GND jumper is fitted as one of four outstanding bench deviations.
It is ~0 Ω — far below the 9.4 kΩ bound — which is exactly why it would make
detect function, and exactly why nothing compatible with a guitar input could.
**It works by accident and is not a candidate solution.** It also shorts the
guitar signal to ground.

---

## Rationale

The failure is topological, not a bad component. The #11's SHUNT contact is a
perfectly good switch; it is unusable *here* because its only switched node is
TIP, and TIP carries a hard high-impedance requirement pointing the other way.
Any scheme that senses presence *on the signal node* inherits that conflict,
whatever parts it is built from. Stating the constraint at the node level rather
than the component level is what makes it survive a change of jack, of MCU, or
of pull-up value.

---

## Consequences

### Accepted

- The Phase 5 detect topology as written in the runbook is **not buildable as
  specified** and must not be followed on this point.
- TODO-5's sign-off (*"detect events fire"*) cannot be met by wiring alone; it
  requires a topology decision first.
- Detect for Phase 7 (`JACK_RIG_SEND_PIN` 17, `JACK_RETURN_TS_PIN` 22) and
  Phase 8 (`JACK_RETURN_XLR_PIN` 24) inherits this constraint. Jacks #2 and #3
  are also Switchcraft #11s, so the same analysis applies before they are wired
  — **this ADR should be consulted before Phase 7 construction, not after.**
- The per-connector `JACK_*_DETECT_INVERTED` defines in `config.h` remain
  correct as a mechanism and are unaffected. Polarity handling was never the
  problem.

### Costs

- A part or sub-circuit not currently in stock may be required.
- Phase 5 sign-off is deferred behind a design decision rather than a bench step.

### Explicitly rejected

- **A resistor from TIP to ground sized to make the SHUNT contact work.**
  Rejected on the arithmetic above: ≥23× incompatible with the input-impedance
  requirement.
- **A firmware polarity fix.** Rejected because the pin does not change state;
  no polarity value addresses that.
- **Retaining the `col 30` → GND jumper as the production answer.** Rejected: it
  shorts the guitar signal.

---

## Candidates — selection unresolved

Recorded so the option space is not lost. **None is chosen, and this list is not
ranked.** Each satisfies the constraint by keeping detection off the audio node.

1. **Isolated make-on-insertion detect contact** — e.g. Cliff CL1384, the
   alternative the runbook dismissed at line 1221.
2. **A separate detection switch or contact** independent of the audio tip.
3. **High-impedance buffered or comparator sensing**, designed so the detection
   network does not load the guitar input.

Selecting among these is a hardware decision requiring a parts and PCB-area
assessment that has not been made. **Do not treat this list as a recommendation.**

---

## ~~The bench experiment is retained, deliberately~~ — WITHDRAWN 2026-09-13

The arithmetic proves the incompatibility. It does **not** prove that the
assembled hardware behaves by the stated mechanism. Those are different evidence
claims and this project keeps both.

**🔻 WITHDRAWN — this experiment cannot be performed.** It required wiring J4's
SHUNT contact to pin 16, and J4 has no SHUNT contact. Executing it as written
would have connected a 22 kΩ pull-up to 3.3 V **directly onto the guitar TIP**.
The cost is real and is recorded rather than dropped: **the impedance conflict
below remains proven by arithmetic and unproven by experiment on this bench.**
The text is preserved for the record:

~~Retained experiment (see TODO-5 for the full power-off sequence):~~

1. Leave the `col 30` → GND jumper fitted; wire SHUNT → pin 16.
   **Predict:** detect works — empty = LOW, TS plug inserted = HIGH.
2. Remove **only** that jumper.
   **Predict:** detect disappears — pin 16 stuck HIGH in both states.

Both outcomes holding demonstrates the mechanism on the real board rather than
on paper. The J4 SHUNT → TIP topology is retained **solely** for this controlled
experiment and carries no implication of acceptance.

---

## Provenance note

Derived from a live null result on firmware `b32d04a`: empty → insert → remove →
insert produced zero `JACK_CHANGED` events across 45 diagnostic windows, uptime
18–218 s, captured continuously —
`ai/evidence/2026-09-13-phase5-detect-null-result.log`. Analysis in
`ai/journal.md` entries **2026-09-13 (7)** and **2026-09-13 (8)**.

The pull-up value is read from the installed toolchain
(`cores/teensy4/digital.c:180`), not assumed. The C1 value and the `SOURCE_IN`
net are from `docs/asbuilt/netlist.md` (line 95, tagged `PHYS`). The runbook
line references are to `docs/breadboard_bringup_v3.md` as of this date.
