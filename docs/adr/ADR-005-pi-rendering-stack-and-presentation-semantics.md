# ADR-005 — The production Pi renderer is a kiosk web client, and presentation semantics are a shared contract

**Status:** ✅ **ACCEPTED** · 2026-09-30 · **amended 2026-09-30** (§1, UI framework)
**Decided by:** the account holder
**Supersedes:** the **implicit Tkinter-as-production-renderer assumption** carried by
`pi/analyzer_ui/`, by TODO-36's renderer language, and by commit `c7e1581`
("feat(pi): production UI first slice"). That choice was made in implementation and
was never recorded in an ADR; this document records it, reverses it for production,
and keeps the Tk renderer in a named role.
**Does NOT supersede:** [ADR-001](ADR-001-display-architecture.md)'s governing
invariant, its `DISPLAY_TARGET` / presentation boundary, or its demotion of the
RA8875. ADR-001 §*The governing invariant* remains binding in full and is
**strengthened**, not relaxed, by §*The governing invariant* below.
**Relates to:** [ADR-002](ADR-002-jack-presence-detection.md),
[ADR-003](ADR-003-jack-presence-is-a-ux-feature.md),
[ADR-004](ADR-004-return-source-is-operator-selected.md) — all in force and unweakened.
**Affects:** TODO-35, TODO-36, `pi/analyzer_ui/`, `pi/analyzer_link/`, a new
`pi/analyzer_link/presentation_semantics.py`, the Phase 10 renderer acceptance
matrix, and `docs/visual_design_document.md` (to be imported)

> **📝 Attribution clarification, added 2026-10-14 by Conley Vidal. The
> signature above is left exactly as written.**
>
> The *"Decided by"* line names the AI account identity, not the person. The
> accounts used on this project belong to **the account holder**, my father, and I
> use them with his permission; the AI sessions that wrote this document knew
> their human counterpart only by that name. My father did not participate in
> developing, debugging or building this instrument.
>
> **What is mine in this document, stated narrowly.** The two-processor
> architecture it builds on — a Teensy that acquires and computes, a Pi that
> displays — was my decision, and predates this ADR (see
> [ADR-001](ADR-001-display-architecture.md)). **The rendering-stack and UI
> decisions recorded below were collaborative work between Claude and me**, and
> should not be read as independently mine. That includes the choice of a kiosk
> web client over the Tk renderer, the WebGL/three.js direction, the deliberate
> non-specification of a UI framework in §1a, and the presentation-semantics
> contract.
>
> See [`../ai-assistance.md`](../ai-assistance.md) and
> [`../../ai/README.md`](../../ai/README.md).

---

## Decision

### 1. The production Pi renderer is a kiosk web client

> **AMENDED 2026-09-30, after the first implementation slice.** This section
> originally said *"a React + three.js/WebGL UI"*, naming a UI framework it had no
> reason to decide. The binding decision is **browser / WebGL + three.js**; the UI
> framework is **deliberately unspecified**. See §1a.

Chromium in kiosk mode on the Pi 5, rendering a three.js/WebGL UI against
the 7" Touch Display 2 at **720×1280 portrait** (measured 2026-09-29 by `wlr-randr`,
DSI-2, transform normal, scale 1.0 — see [`app.py:3`](../../pi/analyzer_ui/app.py#L3)).

The deciding factor is **not** that WebGL looks better. It is that the six committed
visuals in the visual design document were architected against that renderer — the two
Pi-targeted ones (`ToneFingerprintSplit.jsx`, `WaterfallSpectrum3D.jsx`)
already specify 720×1280 portrait, InstancedMesh draw-call collapsing, `lerp` frame
interpolation at a stated coefficient, and a pixel ratio capped at 1 for the embedded
GPU. Porting them to Tk 2D or Python GL would convert Phase 10 integration work into
a graphics rewrite, and the rewrite would be judged against no specification but
itself.

### 1a. The UI framework is deliberately unspecified

**Binding:** browser, WebGL, three.js, 720×1280 portrait. **Not binding:** which
UI framework, if any, wraps it.

The first implementation (TODO-67 slice 1) uses **native ES modules** with no
framework and no build step, because no framework-specific requirement exists yet:
the client is a single visualization driven by one authoritative payload, and its
entire state is the array of classified bands the Pi sends. React would have added
a toolchain without yet adding capability.

**React is not rejected.** The committed concepts are written as React components,
and React may be introduced whenever real UI complexity justifies it — multiple
coordinated views, routing between screens, shared interactive state, a settings
surface. That is an implementation decision at the time, not a reversal of this ADR.

Recorded because the implementation deliberately differs from this ADR's original
wording. An accepted ADR that disagrees with the code is worse than one that never
specified the detail: the next reader cannot tell which is the decision and which
is the drift.

### 2. The Tkinter renderer is retained as the reference/debug renderer

`pi/analyzer_ui/` is **not deleted and not frozen**. It becomes the named
reference renderer: the one that has been run against the real UART on the physical
display, and the one a disagreement is adjudicated against.

This mirrors ADR-001's treatment of `display_engine` exactly, and for the same
reason: *removing working, bench-exercised code to express an architectural
preference would be a net loss.*

The web client becomes the production default only after it can, on the Pi:
boot directly into Chromium; connect to `analyzer_link`; render real protocol-v2
frames; and survive disconnect and reconnect. Until all four hold, the Tk UI is
what ships.

### 3. ADR-001's authority rule is restated and remains binding

The Teensy owns measurements, validity, quality grading, advisories and insights.
The Pi owns presentation. Changing the rendering technology changes nothing about
this. A WebGL renderer has **more** capacity to fabricate a convincing picture than
a Tk canvas does, so the boundary matters more here, not less.

### 4. A shared presentation-semantics layer, consumed by both renderers

A protocol-adjacent module — `pi/analyzer_link/presentation_semantics.py`, with an
equivalent contract exposed to the web client over the UI transport — classifies
Teensy-authored state into display-ready semantics **once**. Renderers consume the
classification. **A renderer must not independently reinterpret raw protocol fields.**

It is deliberately **not** called a bin-classification module. Naming it for FFT bins
would invite exactly the wrong scope, because the problem is not specific to bins
(§5). Bin classification is one operation within the contract, not the contract.

### 5. Defined state is not evidence of physical establishment

This is the general principle; the 4-of-512-bin case is one instance.

| Defined state | What it does **not** establish |
|---|---|
| `route_valid` — "return routing configuration is defined" | That anything is physically connected. The repo router contract says its historical name is not grounds to reintroduce presence detection. |
| `detect_available` — a detector is fitted | Jack presence. Absent a detector the UI says *"no detector"*, never *"not present"* ([`model.py:148`](../../pi/analyzer_ui/model.py#L148), TODO-58). |
| A return source is always selected (ADR-004) | That a return signal exists. |
| A finite float at `tf_cal_mag_db[i]` | That bin `i` was measured. It may be the −24.0 dB clamp rail. |
| A finite float anywhere in a RESULT array | That the value is a measurement rather than storage. RESULT carries **no per-bin clamp mask** (§6). |

A renderer that collapses any left column into the right column has fabricated a
claim the instrument never made.

### 6. The bin provenance contract

Every displayed frequency location must retain enough provenance to distinguish:

| Class | Meaning | Source of truth |
|---|---|---|
| **MEASURED** | A finite value the instrument actually measured | finite, `valid > 0`, not clamped |
| **CLAMPED** | A real value limited by the firmware/protocol rail | coverage `clamped == ratio` (`data_sender.h`) |
| **UNMEASURED** | No measurement exists at this location | NaN, or `valid == 0` (pen-lift) |
| **INDETERMINATE** | A value is present, but the authoritative metadata required to classify its presentation semantics is absent | RESULT arrays: no per-bin clamp mask exists |

**`INDETERMINATE` is defined narrowly and is not a generic uncertainty bucket.** It
means precisely this: *the value is present, but the authoritative metadata required to
classify its presentation semantics is absent.* Three consequences follow.

- It is a statement about **missing metadata**, never about a suspicious value. A bin
  must **never** be classified `INDETERMINATE` because its value looks wrong, looks
  railed, sits at a round number, or disagrees with its neighbours. Inferring the class
  from the value is the TODO-29 defect wearing a new label.
- It is **not** a fallback for unclassifiable input. A NaN is `UNMEASURED`; a bin with
  `valid == 0` is `UNMEASURED`; a parse failure is an error. None of them are
  `INDETERMINATE`.
- It is **transitional by construction.** When the RESULT protocol carries authoritative
  clamp metadata, those same bins become `MEASURED` or `CLAMPED` with no change to this
  contract — only to the evidence available to it. The class exists to hold the gap
  open and visible, not to paper over it.

The canonical — and currently the only — example is the RESULT clamp-metadata gap. It is
already stated on the face of the Tk instrument
([`app.py:376`](../../pi/analyzer_ui/app.py#L376)): LIVE_FRAME carries per-bin coverage
nibbles and a frame-level `tf_clamped_count`, and **RESULT carries neither**, so in a
RESULT nothing distinguishes a measured −24.0 dB from the rail. The 2026-09-27
hardware RESULT has 4 finite bins of 512 and **all four sit on that rail.** A renderer
must be able to say so rather than drawing four confident points.

**This does not license guessing from the value.** The four bins are classified
`INDETERMINATE` because RESULT carries no clamp mask — *not* because they read −24.0 dB.
Had they read −11.3 dB they would be `INDETERMINATE` too. The −24.0 dB coincidence is
reportable context for the operator, never a classification input. Closing the
underlying protocol gap is TODO-65's business, and it is not closed by inference here.

**Resampling and interpolation must not manufacture coverage.** This is not
hypothetical; it is already recorded. Source bins 22–25 fall into live bins 5 and 6 at
4:1, giving each `clamped=2, ratio=4`. Because `data_sender.h` marks saturation only
when `clamped == ratio`, a **half-clamped group is drawn as data, not marked as a
rail** (TODO-36, 2026-09-30). Both the "4/512 clamped" and "0 of 128 clamped" figures
are correct, and the decimation is where the meaning changed. Any display-side
resampling — a 512-bin array onto a 48-segment ring, or onto the waterfall's 96 bins —
has the same hazard, and the contract must make the combining rule explicit rather
than leaving it to each three.js component.

### 7. Presentation-only transformations are explicitly permitted

So this ADR cannot be read as forbidding the visuals it authorises, the following are
**allowed** and are not boundary violations:

- geometry generation; mesh construction; camera motion and orbit
- interpolation **for animation between received frames** (the committed designs
  specify `lerp` at 0.14–0.22 against ~10.8 Hz data)
- smoothing of visual transitions; easing; pulse and glow effects
- colour mapping, thermal palettes, gradient fills
- resampling **for display**, subject to §6's rule that coverage is not manufactured
- layout, typography, units, number formatting, view navigation

The test is not whether the renderer computed something. It is whether what it
computed can change measurement meaning or manufacture a Teensy-owned judgement.

### 8. `INJECTION_LOST` is a deferred requirement, recorded with its trace — not Phase 10 work

The Downloads copy of `signal_router_contract.md` (2026-09-30, a fork that is *behind*
the repo on ADR-004 policy and *ahead* of it on injection lifecycle) specifies a
`RouterEvent::INJECTION_LOST` that the main loop **must** forward to
`measurementEngine_notifyRouteChanged()`, because `audioCap_setInjectionMode(false)`
is silent by design and raises no `ROUTE_CHANGED`.

It exists nowhere in this codebase. [`signal_router.cpp:295`](../../signal_router.cpp#L295)
disables injection on Rig Send removal and returns only `JACK_CHANGED`;
[`guitar_rig_analyzer.ino:450`](../../guitar_rig_analyzer.ino#L450) answers
`JACK_CHANGED` with `presentation_routerStatus()` and nothing else.

**It cannot fire today.** `signalRouter_setInjectionEnabled()` has no caller, and
[`guitar_rig_analyzer.ino:386`](../../guitar_rig_analyzer.ino#L386) states that
measurement_engine does not consult `signalRouter_canInject()`, so `s_injection_active`
is never true. This is a **prerequisite for enabling internal-stimulus measurement**,
not a current defect and not a UI blocker. Tracked as TODO-66. **It does not enter
Phase 10.**

### 9. Two concept files are unreferenced by the specification, and are treated differently

`visual_design_document.md` names exactly six JSX references. **`VortexTunnel.jsx` and
`ToneFingerprintSurface.jsx` are not among them.** They are not equivalent, and are not
classified together.

**`ToneFingerprintSurface.jsx`** — an undocumented variant: 720×1280, 64 bands,
Teensy-shaped data, no second input path. It is a **candidate**, not a committed visual.
If it is wanted in production it gets a design-document section first, so the
specification keeps leading the implementation. Until then it is not built.

**`VortexTunnel.jsx`** — a boundary violation, not merely undocumented.

It acquires audio through `getUserMedia` at `FFT_SIZE 256`. That is a **second
measurement/input path outside the Teensy authority boundary** — the instrument would
be visualising the room, not the rig, with nothing on screen to say which. It was saved
three minutes after the committed set and never written up. It is retained as a visual
experiment only, and **must not be wired to the production view switcher.**

---

## The governing invariant

ADR-001 gave the rule in terms of validity. Phase 10's real failures have been about
**absence** rather than validity, so the rule is restated to cover them:

> **A renderer may transform how authoritative state is displayed, but it may not
> transform uncertainty, absence, or undefined state into asserted measurement,
> connectivity, validity, quality, or advice.**

This is one rule covering the 4/512-bin problem, the `route_valid` naming hazard,
detector masking under ADR-002/003, RESULT's missing clamp mask, and protocol fields
that do not exist yet. It is testable: for any rendered element, name the
Teensy-authored field it asserts. If none exists, the renderer invented it.

**Worked against the attached RA8875 concepts**, which are useful precisely because
several of them fail it: "RIG HEALTH: 90%", "Evaluation: MEDIUM", "Rig Match: 89%",
and "Recommendation: Add input buffer" are all Teensy-owned judgements
(`insights_engine`, `result_quality`). Rendering them is fine. **Computing them on the
Pi is not.** If no wire field carries them, the correct display is their absence.

---

## Context

Nine UI concepts and a 29 KB `visual_design_document.md` (v1.2) were located in
`~/Downloads` on 2026-09-30, alongside 21 firmware files that are an **older snapshot
than this repository** and are not to be merged. The design document names six
committed visuals, a screen map across both display targets, and an implementation
priority list. It is the most developed UI specification the project has, and until
now it was not in the repository at all.

The Tk renderer was built on 2026-09-29/30 without reference to it, because it had not
been found. That renderer is real work and is bench-exercised: it has rendered live
telemetry off `/dev/ttyAMA0` on the physical display, and a 20 s energised capture
exists. Nothing about this ADR treats it as wasted — see §2.

The specification and the implementation therefore disagree about the rendering stack.
This ADR resolves that disagreement **before** more renderer code is written, because
the alternative is that the implementation silently becomes the specification.

---

## Rationale

1. **The committed designs already encode Pi-specific performance engineering.**
   InstancedMesh collapsing 96 meshes to 2 draw calls, `Float32Array.copyWithin` for
   zero-allocation waterfall scrolling, pixel ratio capped at 1, static materials with
   per-instance colour. Re-deriving that in another stack discards work that was
   already done and reasoned about.

2. **The renderer's input assumptions are now measured, not speculative.** T1 Run 2:
   **46.440 ms ± 0.089 ms** block period, **21.5 frames/s**, **0 dropped frames**,
   **282 µs** max transport call time. The designs' ~10.8 Hz data rate with `lerp`
   interpolation to 60 FPS is consistent with that.

3. **A shared semantics layer is the only way two renderers cannot disagree.** With
   Tk retained as reference (§2) there are, by construction, two renderers for a
   period. If each classifies bins itself, "reference renderer" means nothing — there
   would be no single answer to adjudicate against.

4. **Three.js makes fabrication cheaper.** A continuous mesh surface over the band
   ring interpolates across missing bands by default; that is what a surface *is*.
   Under the real RESULT that renders 508 undefined locations as smooth terrain. The
   contract must exist before the first component is written, not after.

---

## Consequences

### Accepted

- A web client is a new Pi-side deliverable: build tooling, a UI transport from
  `analyzer_link` to the browser, kiosk autostart replacing the Tk autostart
  (`d4eca26`, reversible with one `rm`), and offline asset serving.
- `presentation_semantics.py` becomes a **protocol-adjacent** module. It is covered by
  the drift guard discipline already applied to `protocol.py`
  (`test_firmware_header_sync.py`).
- `docs/visual_design_document.md` is imported into the repository as the UI
  specification of record, with its RA8875 sections marked as the demoted target per
  ADR-001.
- The Tk renderer gains a second job: it is the oracle for semantics tests.

### Costs

- Two renderers are maintained during migration. This is accepted deliberately and is
  time-boxed by §2's four conditions.
- A browser is now in the boot path, with its own failure modes (GPU driver, kiosk
  flags, Wayland compositor interaction). None of these may be allowed to affect
  acquisition — ADR-001 §4's reasoning applies unchanged, and the Teensy's indifference
  to the renderer is what makes that structural.
- JavaScript becomes a third language in the project.

### Explicitly rejected

- **Porting the committed designs to Tk 2D or Python GL.** §1.
- **Deleting the Tk renderer on acceptance of this ADR.** §2.
- **Letting each three.js component decide what an unmeasured bin looks like.** §4, §6.
- **Treating this ADR as a renderer acceptance waiver.** See *Sequencing*.
- **Merging any of the 21 Downloads firmware files.** They are an older snapshot:
  `data_sender.h` is 6,851 B against the repo's 38,786 B and predates the protocol-v2
  coverage nibbles the entire bin contract depends on.

---

## Sequencing

**🛑 This ADR does not close, waive, or reset any Phase 10 acceptance gate.**

TODO-36 records renderer development as *provisionally authorised 2026-09-29 — "a
development decision, NOT an acceptance waiver"* — with the T1 matrix incomplete
behind TODO-39's instrumentation defect. **A web renderer inherits that gate
unchanged.** Changing rendering technology is not a reason to re-open a settled
authorisation on easier terms, and a working WebGL UI must never be cited as evidence
that T1 passed.

| Step | Item | State |
|---|---|---|
| 1 | Record this decision | 🟡 this document, PROPOSED |
| 2 | Import `visual_design_document.md` as the UI spec of record | 🟢 **done 2026-10-12** — [`docs/visual_design_document.md`](../visual_design_document.md), RA8875 sections marked demoted in its import header. Sources reconciled in [`docs/ui/README.md`](../ui/README.md) |
| 3 | `presentation_semantics.py` + tests against the 4-finite/508-undefined RESULT | 🔴 TODO-68 |
| 4 | Tk renderer refactored onto the shared contract (proves it on known-good code) | 🔴 TODO-68 |
| 5 | UI transport: `analyzer_link` → browser | 🔴 TODO-67 |
| 6 | First three.js view against real frames | 🔴 TODO-67 |
| 7 | Kiosk autostart; disconnect/reconnect survival | 🔴 TODO-67 |
| 8 | Web client becomes production default | 🔴 gated on §2's four conditions |
| 8a | **MEASURED bar rendering visually validated** | 🔴 **open evidence debt** — see below |
| 9 | `INJECTION_LOST` propagation | 🔴 TODO-66 — **not Phase 10** |

Step 3 precedes step 6 deliberately. The pathological RESULT — **4 finite bins of 512,
all on the −24.0 dB clamp rail, 508 undefined** — is the acceptance fixture for the
contract, and it already exists as pinned hardware evidence
(`ai/evidence/phase10-result-1khz.bin`, SHA-256 asserted by
[`test_result_fixture.py`](../../pi/tests/test_result_fixture.py)). The contract is
proven against real bytes before any GPU work begins.

**🔺 OPEN EVIDENCE DEBT: the MEASURED bar path has never been seen.** Both pinned
fixtures classify to **zero** MEASURED bands — the RESULT is 4 indeterminate of 512,
the idle capture is 128 unmeasured of 128. So slice 1 proves the renderer *refuses
to draw what it must not*, and proves nothing about how it draws what it should.
Bar heights, side assignment, the cold/warm ramps, coverage-driven thickness and
frame easing have unit tests and **no visual confirmation**.

**This is not closed with synthetic data.** Generating a plausible high-coverage
frame to exercise the bars would produce a convincing screenshot of a measurement
that never happened, which is the precise failure this ADR exists to prevent — and
a screenshot, once in `ai/evidence/`, outlives the caveat attached to it. The debt
stays open until the instrument produces a genuine measurement that establishes
measured coverage across the band.

---

## Provenance note

**This ADR contains no bench claims.** Every assertion is sourced to a file, a line, a
committed evidence record, or an existing todo entry. The measured figures it cites
(46.440 ms ± 0.089 ms, 21.5 frames/s, 282 µs, 4 finite bins of 512, the 4:1 coverage
arithmetic) are **quoted from records already in this repository**, not re-derived
here. Nothing in it has been verified against a browser, because no browser has yet
been run on the Pi — that is step 6's job, under the acceptance gate step 1 does not
waive.

The design document and firmware files it reasons about were read from `~/Downloads`
and are **not yet in the repository**; §*Consequences* step 2 imports the one that
belongs here, and the firmware files are explicitly rejected.
