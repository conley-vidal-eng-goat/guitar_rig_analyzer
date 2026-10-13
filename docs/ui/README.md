# UI design sources — precedence, reconciliation, and what is being built

**Created 2026-10-12.** Three documents now describe this instrument's interface.
They were written months apart, by different hands, against different hardware
targets, and until today two of them were not in version control at all. This file
is the one place that says **which wins when they disagree**, and records each
resolution with a date and a reason.

Read this before implementing from any of them.

---

## 1. What is here

| Path | What it is | Standing |
|---|---|---|
| [`../visual_design_document.md`](../visual_design_document.md) | v1.2, "v0.6.1 milestone". Six committed visuals, a screen map, an implementation priority list, RA8875 draw budgets. | **Specification of record** (ADR-005 *Consequences* step 2) |
| [`2026-10-production-ui-design-brief.md`](2026-10-production-ui-design-brief.md) | The October brief. Product vision, a 3-level evidence model, a tone-vocabulary research programme, a 7-destination IA, 10 candidate visualisations, a 5-stage work process. | **Design input**, newer, not binding |
| [`concepts/`](concepts/) | Seven JSX mockups referenced by the two documents above. | Reference implementations — see [`concepts/README.md`](concepts/README.md) |
| [`references/`](references/) | Nineteen images the October brief calls its visual references. | Inspiration and, for five of them, **evidence of what was rejected** — see [`references/README.md`](references/README.md) |

---

## 2. Precedence — highest authority first

This is the project's existing source-of-truth rule (`ai/journal.md`, 2026-08-25
and 2026-09-13), applied to interface work.

1. **Physical hardware behaviour and bench evidence.** What the instrument
   actually does.
2. **The wire contract.** `pi/analyzer_link/protocol.py`, `packets.py`, and
   `data_sender.h`. A field that is not on the wire cannot be displayed.
3. **Accepted ADRs.** [ADR-001](../adr/ADR-001-display-architecture.md) (authority
   boundary, RA8875 demotion), [ADR-002](../adr/ADR-002-jack-presence-detection.md)
   / [ADR-003](../adr/ADR-003-jack-presence-is-a-ux-feature.md) (presence is
   informational), [ADR-004](../adr/ADR-004-return-source-is-operator-selected.md)
   (operator-selected return), and
   [**ADR-005**](../adr/ADR-005-pi-rendering-stack-and-presentation-semantics.md),
   which **retains architectural authority over everything in this directory**.
4. **Current HEAD.** Working, tested code outranks a document describing it.
5. **`visual_design_document.md` v1.2** — the specification of record for *visual*
   decisions not settled above.
6. **The October design brief** — an input. Persuasive, newer, and explicitly
   subordinate: its own §1.4 says *"Physical hardware and current repository code
   override older design documents"*, and §0 forbids assuming any prototype is the
   production UI without inspection.

> **The governing invariant sits above all six** (ADR-005):
> *A renderer may transform how authoritative state is displayed, but it may not
> transform uncertainty, absence, or undefined state into asserted measurement,
> connectivity, validity, quality, or advice.*

---

## 3. Reconciliations — where the documents disagree

Each row is a real disagreement, resolved on **2026-10-12** by the account holder after
the Stage A read-only audit. A resolution here does not edit the source documents;
they are imported byte-for-byte and stay that way.

### 3.1 Display target

| Source | Says |
|---|---|
| v1.2 | Dual target: RA8875 800×480 **and** Pi 5 720×1280 |
| October brief | "Do not hardcode an old 800×480 RA8875 target as the production display" |
| Repository | ADR-001 demoted the RA8875 on 2026-09-11; `wlr-randr` measured **720×1280 portrait, transform normal, scale 1.0** on 2026-09-29 |

**✅ Resolved: 720×1280 portrait, Pi 5 + Touch Display 2, single target.** Every
RA8875 section in v1.2 is reference material for a demoted target and is marked as
such in that file's import header. The two documents already agree; v1.2 is simply
older than the ADR.

### 3.2 Palette

Three palettes exist and none is a superset of another.

| Role | v1.2 | October brief | **Shipping code** |
|---|---|---|---|
| Background | `#060a10` | `#090C12` | **`#04070b`** |
| Attenuation / cut | `#d0b020` → `#e83030` (yellow→red) | — | **`#4cc9f0` → `#90e0ef`** (cyan) |
| Boost | `#2088d0` → `#30c850` (blue→green) | — | **`#ff7b00` → `#ffd166`** (orange) |
| Not established | — | — | **`#d29922`** (amber) |
| SOURCE channel | `#3498db` steel blue | — | not assigned |
| RETURN channel | `#2ecc71` emerald | — | not assigned |
| Accents / chrome | — | `#38D6F5` `#8C62FF` `#E856FF` `#55E5B0` `#FFBF50` `#FF6474` | `#9fb3c8` `#8b9bad` `#6b7f94` |
| Body text | `#d8e4f0` | — | `#d8e4f0` |

**✅ Resolved, by what a colour *means* rather than by which document is newer:**

- **Semantic colours come from the shipping code and do not move.** Cyan =
  attenuated, orange = boosted, amber = value present but direction not
  established. These are already in `fingerprint_split.js`, in the on-screen
  legend, and in two committed evidence screenshots. Changing them would silently
  relabel published evidence. Note this *inverts* v1.2 §1's 2D mapping
  (which made cuts warm and boosts cool) — **the 3D Split spec, v1.2 §1c, already
  uses the shipping assignment**, so the conflict is internal to v1.2 and the
  newer section wins.
- **Chrome, surfaces, typography and new 2D charts take the October brief's
  palette.** It is the more developed system and does not collide with any
  semantic colour.
- **SOURCE and RETURN keep v1.2's steel blue and emerald** as channel identities.
- 🔺 **Open, for Stage B:** steel blue `#3498db` sits close to the cut-cyan
  `#4cc9f0`. They never share a view today, but the proposed Two-River
  visualisation would put SOURCE, RETURN and their difference on one axis. If it
  is built, one of the two must move. **Do not resolve this by eye on a Mac** —
  it is a legibility question on a 7-inch panel at arm's length.

### 3.3 Navigation and screen count

| Source | Says |
|---|---|
| v1.2 | A screen map of seven views (Live, Result, Aborted, Radial 2D, Radial 3D, Split 3D, Waterfall 3D); switching is a view toggle, no nav chrome specified |
| October brief | Seven top-level destinations (Live, Tone Explorer, Lab, 3D Studio, Compare, Learn, Setup), while itself suggesting "four prime destinations + contextual secondary pages" |
| Repository | One screen, no navigation |

**✅ Resolved: four tabs — LIVE / TONE / LAB / INFO**, persistent bottom bar,
720×1280 portrait, one level deep, no nested stacks.

| Tab | Content | Default |
|---|---|---|
| **LIVE** | Source/Return meters, live spectrum, transfer-function display | ◉ yes |
| **TONE** | The existing 3D Tone Fingerprint, full-bleed, cold/warm language and orbit preserved | |
| **LAB** | Coherence, phase, group delay, provenance, Teensy-authored insights | |
| **INFO** | Jack routing, firmware/protocol versions, link health, diagnostics | |

**Why four and not seven.** Three of the brief's destinations — Compare/Library,
Learn/Ear-Training, and the action half of Setup/Diagnostics — need persistent
storage, audio playback, or a command path that does not exist. The brief's own §6
anticipates the reduction. v1.2's seven "screens" are mostly *views of one data
stream*, not destinations, and collapse into TONE.

### 3.4 🛑 Navigation must not imply control

**The Teensy→Pi link is receive-only.** `ByteSource` exposes `read()` and `close()`
and nothing else ([`pi/analyzer_ui/sources.py`](../../pi/analyzer_ui/sources.py));
[`app.py:19`](../../pi/analyzer_ui/app.py#L19) records that Pi→Teensy is physically
disconnected and renders command buttons disabled. TODO-35 carries the Pi→Teensy
direction as outstanding.

**So navigation switches between views of the same stream. It may not arm a
capture, change a route, trigger calibration, or run a named test.** Any control
that suggests otherwise is a fabricated capability under ADR-005's governing
invariant, and the Tk renderer's existing treatment — show the control, show it
disabled, say why — is the precedent to follow.

This is the structural reason the six-tile `MENU` render in
[`references/`](references/) cannot be built as drawn, independently of whether its
tests exist.

### 3.5 UI framework

| Source | Says |
|---|---|
| v1.2 | Silent |
| October brief | "Do not introduce a large frontend framework merely to build navigation" |
| ADR-005 §1a | Binding: browser, WebGL, three.js, 720×1280. **Not** binding: which framework, if any. React "may be introduced whenever real UI complexity justifies it" |
| Repository | Native ES modules, no build step, vendored three.js |

**✅ Resolved: stay frameworkless.** Vanilla ES modules, three.js for the
fingerprint, Canvas2D for the 2D charts. A four-tab router is a small amount of
plain JavaScript; React would add a toolchain, a build step and an offline-asset
problem to an appliance that currently has none of the three. ADR-005 §1a permits
either, and explicitly wants the reasoning recorded at the time — this is that
record.

### 3.6 Evidence models

The two documents describe different things and are **not** in conflict.

| | Model | Lives where |
|---|---|---|
| **Bin provenance** — 4 classes | `MEASURED` / `CLAMPED` / `UNMEASURED` / `INDETERMINATE` | ADR-005 §6, implemented in `presentation_semantics.py` |
| **Claim strength** — 3 levels | MEASURED / TONAL CHARACTERISTIC / PERCEPTUAL INTERPRETATION | October brief §3 |

**✅ Resolved: both, orthogonally.** Provenance answers *may this location be drawn
as data*. Claim strength answers *how strongly may this sentence be phrased*. A
displayed claim needs both.

**Levels B and C have no wire fields today** and therefore render as absent, not as
placeholders. The one exception is already on the wire and currently unrendered:
`Result.insights[]` carries Teensy-authored `MEASUREMENT` vs `ADVISORY` mode,
severity, frequency, magnitude, title and detail. **That is the brief's B/C
distinction, already authored by the measurement authority.** Rendering it verbatim
is UI work. Computing anything like it on the Pi is not.

### 3.7 Tone vocabulary

The October brief §4 asks for a validated tone-vocabulary specification mapping
*warm, honky, scooped, glassy, fizzy* and others to measurable features.

**✅ Resolved: not Pi work, and not November work.** Every such mapping is a
semantic judgement about a measurement, and ADR-001 and ADR-005 §3 put semantic
judgement on the Teensy. A tone-vocabulary feature is a firmware classification
layer plus a versioned protocol field carrying `feature_id`, `value`, `units`,
`frequency_band`, `reference`, `quality`, `evidence`, `algorithm_version` and
`source_result_id` — which is the brief's own §4 prescription. It is real work and
it is after the portfolio deadline. **No tone word is computed in the browser.**

---

## 4. Not being built before 2026-11-01

Recorded so that their absence reads as a decision rather than an oversight.

| Excluded | Why |
|---|---|
| Cable resistance, capacitance, length | No sensor, no circuit, no firmware feature |
| Input / pickup impedance profile | Same |
| Noise analysis (HUM / HISS split) | No measurement routine |
| Latency map, per-stage timing | No measurement routine |
| Buffer placement advisor | Advice the firmware does not author |
| "Rig Health %", "Rig Match %", "Evaluation: MEDIUM" | Named by ADR-005 as the worked counter-example |
| Tone vocabulary | §3.7 |
| Compare / Library | No storage layer |
| Learn / Ear training | No audio playback path |
| Any control that commands the Teensy | §3.4 |

---

## 5. Sequence (approved 2026-10-12)

| # | Step | State |
|---|---|---|
| 0 | Import the design sources and reconcile them — **this commit** | 🟢 done 2026-10-12 |
| 1 | **Prove Chromium on the physical Pi 5 + Touch Display 2.** Minimal launcher over SSH; no keyboard on the Pi; do **not** replace the Tk autostart. Record startup, WebGL renderer string, orientation, touch, frame rate | 🔴 **next** |
| 2 | Four-tab shell + tokens + status strip; TONE is today's fingerprint unchanged | 🔴 |
| 3 | `presentation_semantics` extension for the FFT arrays and coherence — own commit, own tests, contract before renderer | 🔴 |
| 4 | LIVE: meters, SOURCE/RETURN spectrum, TF strip | 🔴 |
| 5 | Bench: live capture with the guitar running, on the Pi | 🔴 |
| 6 | LAB: result detail, coherence, phase, group delay, insights verbatim | 🔴 |
| 7 | INFO; disconnect/reconnect survival | 🔴 |
| 8 | Stop building. Capture portfolio evidence | 🔴 |

**Step 1 before step 2 is deliberate.** No browser has ever run on this Pi; the
slice-1 screenshots were headless Chrome on macOS with SwiftShader. Building
screens on an unvalidated runtime is the one risk that does not shrink with time.

### 🛑 What this sequence does not do

**It does not re-open T1 on easier terms.** TODO-36 authorised renderer development
on 2026-09-29 as *"a development decision, NOT an acceptance waiver"*, with the
matrix incomplete behind TODO-39. ADR-005 *Sequencing* says it in bold and TODO-67
repeats it: **a polished WebGL UI is not evidence that T1 passed.** Renderer
technology and T1 acceptance are independent evidence tracks, and nothing in this
directory changes that.

**It does not close the MEASURED evidence debt.** Both pinned fixtures classify to
zero MEASURED bands — the RESULT is 4 indeterminate of 512, the idle capture 128
unmeasured of 128. Bar heights, side assignment, the cyan and orange ramps,
coverage-driven thickness and frame easing have unit tests and **no visual
confirmation**. ADR-005 forbids closing that with generated data, and this
directory inherits the prohibition: **no screen in this UI may be demonstrated,
screenshotted or filmed on synthetic measurements presented as real.** A labelled
fixture replay is fine; an unlabelled one in `ai/evidence/` is not.

---

## 6. Open questions

| | Question | Blocks |
|---|---|---|
| 1 | SOURCE blue vs cut-cyan legibility on the physical panel (§3.2) | Two-River |
| 2 | What `UNMEASURED` means in `fft_source[]` / `fft_return[]` — those arrays carry **no coverage nibbles**; the coverage array belongs to `tf_db[]`. A new classification rule is needed, and it belongs in `presentation_semantics.py` with tests, not in a renderer | Step 3, then LIVE |
| 3 | Whether TODO-65 (RESULT per-bin clamp mask) can close before 2026-11-01. Until it does, every finite RESULT bin is INDETERMINATE and the LAB transfer-function curve is mostly mask | LAB's usefulness |
