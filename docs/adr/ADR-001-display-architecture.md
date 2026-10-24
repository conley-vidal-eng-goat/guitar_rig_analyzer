# ADR-001 — Display architecture: the Raspberry Pi 5 is the production renderer

**Status:** ACCEPTED · 2026-09-11
**Decided by:** Conley Vidal
**Supersedes:** the implicit RA8875-as-product assumption carried by `README.md`,
`guitar_rig_analyzer.ino`, TODO-12, TODO-14 and TODO-24
**Affects:** `guitar_rig_analyzer.ino`, `config.h`, `presentation.{h,cpp}` (new),
`data_sender.{h,cpp}`, `display_engine.{h,cpp}`, `docs/breadboard_bringup_v3.md`,
`tools/gen_schematic.py`, `README.md`

---

## Decision

**The Raspberry Pi 5 + 7" Touch Display 2 is the production display and UI
platform. The RA8875 is demoted to bring-up / debug hardware.**

The Teensy 4.1 remains the sole authority for acquisition, DSP and measurement
truth. It gains a **presentation boundary** — a renderer-agnostic API — and the
choice of renderer becomes a single explicit build constant rather than scattered
conditional behaviour.

```
                    GUITAR RIG ANALYZER

 Guitar / Rig
      │
      ▼
┌───────────────────────────────┐
│          Teensy 4.1           │
│                               │
│ Audio capture / codec         │
│ SOURCE_NODE / RETURN_NODE     │
│ FFT / H1 / coherence          │
│ Phase / group delay           │
│ Calibration                   │
│ Signal routing                │
│ Measurement engine            │
│ Insights / quality grading    │
│                               │
│        Presentation API       │  ← presentation.h, the only surface
└──────────────┬────────────────┘    the application calls
               │
          UART binary
       CRC + packet framing
               │
               ▼
┌───────────────────────────────┐
│       Raspberry Pi 5          │
│                               │
│ Receiver                      │
│ Measurement state model       │
│ Plotting / visualization      │
│ Touch UI                      │
│ Compare / Recall              │
│ 3D fingerprint                │
│ User workflow                 │
└──────────────┬────────────────┘
               │
               ▼
        7" Touch Display 2
```

### The governing invariant

> **The Teensy determines truth. The Pi presents truth.**

The Pi may interpolate pixels, animate plots, format values, navigate screens and
visualize data. The Pi **must never compute anything that determines whether a
measurement is valid.** The canonical measurement — including confidence,
coherence, clamp/saturation state and quality grade — is computed on the Teensy
and travels over the wire as a verdict, not as raw material for the Pi to judge.

This invariant is testable, and it is the acceptance criterion for the packet
protocol: **if the Pi has to derive a validity judgement the Teensy already made,
the protocol is wrong.** See the protocol audit in
[`ai/todo.md` TODO-34](../../ai/todo.md) — four of the five gaps found there are
instances of exactly that failure.

---

## Context — how the drift happened

An audit on 2026-09-11 compared the repository's code against its own
architecture documents and found the two pointing in opposite directions.

**Evidence that the Pi was the intended architecture:**

- [`data_sender.h:5`](../../firmware/guitar_rig_analyzer/data_sender.h#L5) — a complete binary UART protocol
  (5 packet types, CRC-16/CCITT, 460800 baud, 128 live bins, `Serial1` on pins
  0/1), described as streaming to "an external display processor (Raspberry Pi 5
  or similar)" and as *replacing* `display_engine`.
- [`docs/breadboard_bringup_v3.md:109`](../breadboard_bringup_v3.md#L109) — "This
  is the **`USE_PI_DISPLAY`** build (since you bought the Pi 5 + touch display).
  The Teensy still owns all DSP and routing; the Pi just renders."
- The bring-up runbook's master parts list purchases a Pi 5 8GB, an Active
  Cooler, a 27 W PSU, a Pi Touch Display 2 (7") and a Freenove GPIO breakout HAT.
- [`ai/todo.md` TODO-24](../../ai/todo.md) reserves Teensy pins 0/1 for
  `Serial1` / `data_sender` and rejects them as candidates for the display reset
  on that basis.

**Evidence that the repository was building an RA8875 product:**

- `USE_PI_DISPLAY` **did not exist anywhere in the code** — no build flag, no
  `#if`, no `config.h` entry. That runbook line was its only occurrence in the
  entire repository.
- `guitar_rig_analyzer.ino` called `displayEngine_*` unconditionally at ~20 sites
  and had no reference to `data_sender` at all.
- `data_sender` had **zero callers**. It compiled into the build and did nothing.
- Verified bench effort went into the RA8875 path: TODO-25's `s_display_ok` guard
  (47× block-rate recovery, 2026-09-05) and TODO-24's `RA8875_RESET_PIN` 8→5
  move, which [`ai/journal.md:1234`](../../ai/journal.md#L1234) calls "a real
  product-level fix, not a bring-up expedient."
- Track B carried TODO-12 (polish `display_engine` result UX) and TODO-14 (touch
  UI via `RA8875_INT_PIN`). **No todo item existed** for promoting `data_sender`,
  for Pi-side software, or for a Pi integration phase.
- The as-built capture reserved the RA8875 and omitted the Pi:
  [`tools/gen_schematic.py`](../../tools/gen_schematic.py) listed
  "RA8875_CS / INT / RESET — SPI display — deferred" in the planned-future block
  with no Pi UART row, and the schematic's NOT INSTALLED panel named the RA8875
  display only.
- The runbook's parts list marks the Pi hardware "used in Phase 9", but Phase 9
  in that same document is the **validation harness**. The Pi was in the bill of
  materials with nowhere to be installed.
- `README.md` — the architecture document — contained no Pi at all. Its block
  diagram terminated at `display_engine → RA8875 800x480`.

**The sharpest symptom:** pins 0/1 were being *reserved* for a UART link to a
renderer that no build could select. The project was paying the Pi path's
resource cost without possessing a Pi path.

---

## Rationale

1. **The Teensy's real-time budget is already committed.** Acquisition, complex
   FFT, H1 estimation, coherence, unwrapped phase, group delay, calibration
   application, routing and quality grading are hard real-time work on a
   single-threaded super-loop. Adding a sophisticated touch UI to the same core
   creates coupling the design does not need, and makes every UI frame a
   potential audio-block stall. The measured RA8875 incident is the precedent:
   an absent display spun `waitPoll()` and stretched the audio block period from
   46 ms to 2194 ms — a **display** defect that destroyed **acquisition**.

2. **The Pi has room for what makes the instrument compelling.** The radial tone
   fingerprint, saved-measurement browsing, A/B comparison views, rich plots and
   real touch interaction are all work the Pi can do without competing with the
   FFT for cycles.

3. **The interface already exists and is better evidence than it looked.**
   `data_sender`'s protocol was not speculative hand-waving: it has framing, a
   sync word, CRC-16/CCITT over the payload, per-baud bin-resolution budgeting,
   and a documented receiver algorithm. It needs an audit before being frozen,
   not a rewrite.

4. **A display must never be able to break an analyzer.** Fatal display
   initialisation is the wrong dependency direction regardless of which panel
   wins. The presentation boundary makes that structural rather than incidental.

---

## Consequences

### Accepted

- `DISPLAY_TARGET` replaces the never-implemented boolean `USE_PI_DISPLAY`:

  ```c
  #define DISPLAY_TARGET_PI      1
  #define DISPLAY_TARGET_RA8875  2
  #define DISPLAY_TARGET_NONE    3

  #define DISPLAY_TARGET DISPLAY_TARGET_PI
  ```

  A tri-state is preferred over a boolean specifically because
  `DISPLAY_TARGET_NONE` is independently valuable: it permits bench DSP work with
  no display hardware attached and no renderer cost at all, which is the
  configuration most of Phases 5–9 actually run in.

- The application calls `presentation_*` only. `presentation.cpp` dispatches to
  `data_sender`, `display_engine`, or a null backend at compile time. No
  measurement or DSP code knows which renderer exists. Adding a renderer means
  adding one `#elif` arm, not touching call sites.

- **`display_engine` is retained, not deleted.** It is a working, bench-verified
  backend and stays available as `DISPLAY_TARGET_RA8875` for debug use. Removing
  working code to express an architectural preference would be a net loss.

- TODO-12 and TODO-14 are **superseded, not deleted** — their RA8875 framing no
  longer describes product work, but the reasoning trail is project history worth
  keeping. Same for TODO-24's pin-8 analysis: the engineering record stays, the
  rewire stops being a product blocker.

### Costs

- A Pi-side codebase is now a real deliverable: receiver, parser, CRC rejection,
  reconnect behaviour, state model, and every view. This is a second
  language/runtime to maintain.
- The protocol becomes a compatibility surface between two codebases. Versioning
  is now mandatory, not optional — which is why the protocol audit (TODO-34)
  must close **before** the wire format is frozen.
- Two display hardware sets are owned: an 800×480 5" RA8875 and a 7" Pi Touch
  Display 2. `display_engine`'s panel geometry is written for the former and will
  not be retargeted.

### Explicitly rejected

- **Mechanically replacing the ~20 `displayEngine_*` calls with `dataSender_*`
  calls.** This was the obvious move and it is the wrong one: it would hard-wire
  a second renderer assumption into the application and produce another
  architecture fork to untangle later. The presentation boundary exists to make
  renderer choice a build decision instead of a source edit.
- **Deleting `display_engine`.** See above.
- **Retrofitting the Pi into Phase 9.** Phase 9 is the validation harness. The Pi
  link gets its own phase with its own acceptance criteria, because pretending a
  completed phase included untested work is exactly the status-collapsing error
  `ai/todo.md` already warns against.

---

## Sequencing

The architecture split is resolved **before** further UI work. Every hour spent
polishing the RA8875 interface makes the correction more expensive, so TODO-12
and TODO-14 do not proceed in their current form.

| Step | Item | State |
|---|---|---|
| 1 | Record this decision | ✅ this document |
| 2 | `DISPLAY_TARGET` + presentation boundary, compile-verified | ✅ TODO-33 |
| 3 | Display removed from boot criticality | ✅ already true — see note |
| 4 | Audit packet protocol against canonical 512-bin model before freezing | 🔴 TODO-34 |
| 5 | Pi integration phase with independent bench acceptance | 🔴 TODO-35 (Phase 10) |
| 6 | Pi-side deliverables | 🔴 TODO-36 |
| 7 | README / runbook / schematic reconciliation | ✅ TODO-37 |

**Note on step 3.** Audit expectation was that `displayEngine_init()` failure
halted boot. It does not, and has not since the TODO-25 work:
[`guitar_rig_analyzer.ino:197`](../../firmware/guitar_rig_analyzer/guitar_rig_analyzer.ino#L197) already logs a
warning and continues, and `display_engine.cpp` guards all six entry points on
`s_display_ok`. The dependency direction was fixed before this ADR was written;
it is recorded here as verified rather than as changed. The `presentation_*`
boundary preserves that property for every backend.

---

## Provenance note

This ADR documents a decision and a code audit. **It contains no bench claims.**
Every assertion above is sourced to a file, a line, or an existing journal entry;
where it cites a measurement (the 46 ms / 2194 ms block period, the 8→5 pin move)
it cites the journal entry that recorded it rather than re-deriving it. Nothing
here has been verified against a Pi, because no Pi has yet been connected —
that is TODO-35's job.
