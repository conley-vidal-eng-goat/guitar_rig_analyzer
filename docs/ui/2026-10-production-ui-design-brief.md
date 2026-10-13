<!-- ============================ IMPORT HEADER ============================ -->
<!--  Everything BELOW the end-of-header marker is the imported document,   -->
<!--  byte for byte. Nothing in the body has been edited.                   -->
<!-- ====================================================================== -->

> # 📥 IMPORTED — a design INPUT, not the specification of record
>
> Imported **2026-10-12** from
> `~/Desktop/guitar_rig_analyzer/Guitar_Rig_Analyzer_UI/`, a design package
> assembled outside this repository.
>
> | | |
> |---|---|
> | Source | `Guitar_Rig_Analyzer_Claude_UI_Design_Brief.md` (36.7 KB) |
> | SHA-256 of the original | `91f37b2d2e2b72fd7867eb85d5d25d058017a8d26ef46d56b78546d444c8255a` |
> | Package README SHA-256 | `36778774975221bb99e0a4dc5d6013b5c9704fbe6e620bcf23c433304481cf45` |
> | Body below this header | unmodified |
>
> **Verify the body is unmodified:**
> ```sh
> tail -n +53 docs/ui/2026-10-production-ui-design-brief.md | shasum -a 256
> # expect 91f37b2d2e2b72fd7867eb85d5d25d058017a8d26ef46d56b78546d444c8255a
> ```
>
> ---
>
> ## 🔻 Its standing
>
> **This is the SECOND design input, and the newer one.** The first is
> [`../visual_design_document.md`](../visual_design_document.md) v1.2, which
> ADR-005 names the **specification of record**. The two were written months
> apart and had never been reconciled until this import. Where they disagree —
> palette, screen count, navigation model — the resolution is recorded in
> [`README.md`](README.md), dated, with a reason. **Neither document outranks
> ADR-005, the wire contract, or bench evidence.**
>
> **It agrees with this repository on the thing that matters most.** Its §1
> states the Teensy/Pi authority boundary and §2 lists limitations that match
> ADR-005's: do not present cable capacitance, resistance, impedance, acoustic
> response or automatic buffer placement as measured facts. Its §0 forbids
> assuming any older prototype is the production UI and requires a read-only
> audit first. That audit was performed on 2026-10-12 before this import.
>
> **The images it refers to** ("the attached UI photos", §5) are in
> [`references/`](references/), with each one's standing recorded in
> [`references/README.md`](references/README.md). **Five of them render
> fabricated measurements** that ADR-005's *governing invariant* already
> adjudicated by name. They are imported as evidence of what was rejected and
> why — not as a target.

<!-- ========================= END OF IMPORT HEADER ======================== -->

# GUITAR RIG ANALYZER — PRODUCTION UI + TONE VISUALIZATION DESIGN BRIEF

**Instructions for Claude — copy this entire file into the active Guitar Rig Analyzer project session.**

## 0. Role, mission, and what success looks like

Act as a senior product designer, interactive data-visualization researcher, musician/ear-training educator, and careful embedded-systems UI engineer. We are finishing the **Guitar Rig Analyzer (GRA)**, a physical Teensy 4.1 measurement instrument with a **Raspberry Pi 5 + 7-inch Touch Display 2** production interface.

I have already experimented with several interfaces and 3D visualizations. **Do not assume any historical September Tk interface, old ToneFingerprintSplit proof of concept, or other older prototype is the production UI. Inspect the CURRENT Git HEAD and identify the NEWEST UI implementation before proposing changes.** Preserve and extend it when practical. Do not conduct an unsolicited framework migration or start a clean rebuild because it would be aesthetically convenient.

### Product vision

Create a modern, responsive, unmistakably musical scientific instrument that lets:

- **Experienced players** see rigorous, repeatable evidence supporting or challenging what they hear: *where* a rig changed the signal, *by how much*, *under which conditions*, and *how trustworthy* the result is.
- **Beginners** learn the relationship between spectral features, timing/dynamics, and guitarists' language: *warm, bright, dark, scooped, nasal, honky, boxy, thin, thick, muddy, crisp, glassy, fizzy, airy, tight,* etc. The interface should help train the ear rather than merely display labels.
- **Curious makers** explore delightful 2D and 3D audio landscapes that are genuinely data-driven, navigable, and informative, not just screen savers.

The experience should feel like **professional laboratory instrumentation crossed with a premium creative music tool**. Scientific trust is a nonnegotiable part of the visual design.

**Deadline context:** The MIT Maker Portfolio is due **November 1, 2026**. This is a real functioning instrument, not an unlimited redesign exercise. Prioritize a compelling, working, recorded physical-demo experience and stage experimental additions behind it. Reserve time for photos, a clear demonstration, technical explanation, and honest documentation of what is or is not working.

---

## 1. Nonnegotiable architecture and evidence rules

1. **Teensy 4.1 is the sole measurement and judgment authority.** It owns capture, routing, generator coordination, FFT/transfer-function processing, coherence, phase, group delay, calibration, result quality, insights/advisories, and export decisions/data.
2. **Raspberry Pi 5 renders the information and handles user interaction.** Do not have the Pi silently recalculate any Teensy-owned DSP, measurement judgment, quality assessment, or semantic tone classification. If a desired visualization needs a new meaningful metric, propose an explicit **Teensy-authored feature and versioned protocol field**; do not invent it on the Pi.
3. The Pi may perform harmless rendering operations—projection, layout, interpolation for visual display, camera movement, visual decimation, labels/hover/touch—but must not change the scientific meaning of the measurements.
4. **Physical hardware and current repository code override older design documents.** Recent design decisions, ADRs, protocol contracts, current as-built bench evidence, and current HEAD outrank historical documents or pasted code.
5. Do not confuse a source spectrum, return spectrum, **RETURN/SOURCE transfer function**, and an acoustic room/speaker response. They answer different questions.
6. Present **measured facts** separately from **interpretations/advisories**. A quantified result like “Return is −5.4 dB vs source in the 5–8 kHz band” is different from “This may sound darker.” Preserve insight provenance and confidence.
7. A missing/NaN, unenergized, clipped, uncalibrated, low-coherence, stale, or otherwise invalid bin must **never** be shown as if it is a valid 0 dB measurement. Visibly distinguish unsupported regions and disable unsupported claims.
8. Do not show fake live values, fabricated confidence percentages, “rig health” percentages, hardware-test passes, room responses, or unverified numerical metrics in the production UI. A sandbox/demo mode using clearly labeled synthetic/replayed fixtures is acceptable.
9. For the physical Pi, assume **no keyboard can be attached**. Recovery/deployment must be possible using the Mac/network or explicitly planned non-keyboard physical recovery, not local typing on the Pi.
10. **No hazardous automatic actuation or silent stimulus injection.** Preserve explicit routing, gain and generator safety gates. Do not change audio-routing/relay logic just to support a visual concept.
11. Never claim a user has heard a sound from a visual simulation or that the instrument knows a subjective preference. The instrument can objectively measure features; perceptual labels require context, evidence, and, ideally, comparisons.

### First action: read-only current-state audit (required)

Before writing UI code, inspect and report:

- Git branch, HEAD SHA, dirty/clean state; relevant app paths, build system, package versions, current kiosk/startup, display rotation and native dimensions.
- The newest UI architecture, its existing implemented screens and interactions, and where it currently runs.
- Current Teensy → Pi transport/schema/version and whether it delivers LIVE samples, measurement-result arrays, quality flags, insight structures, historical snapshots, and timestamps.
- The applicable ADRs, especially operator-selected SOURCE/RETURN routing, routing/injection constraints, and the Teensy/Pi authority boundary.
- A three-column table: **already delivered and verified | available in firmware but not in current protocol/UI | concept/new firmware or hardware needed**.
- What can be demoed on the actual Pi today, and the smallest reliable path to a compelling portfolio demo.

**Do not substitute historical code or assumptions for inspection. Do not edit files during this initial audit.** If you need a missing repository path or visual reference, ask me for exactly that item.

---

## 2. Engineering data: known basis, pending verification against current HEAD

The earlier project source files implement or define the following. They are a **design inventory, NOT a claim that every item is wired through the current Pi interface or verified on the physical rig**.

### Live analysis (`AudioFrame` / audio engine)

- 512-bin averaged SOURCE and RETURN FFT magnitudes (`fft_source[]`, `fft_return[]`).
- Per-bin live transfer magnitude `tf_db[] = 20 log10(RETURN/SOURCE)`, with temporal EMA smoothing and NaN for insufficient SOURCE energy.
- SOURCE and RETURN peak levels in dBFS; per-channel clipping indicators.
- Live TF confidence / valid-source coverage, persistence status, audio block counter, timestamps and active route description.
- Distinguish **absolute spectrum levels** from **rig-caused spectral gain/loss**. The latter is the main engineering story.

### Captured result (`MeasurementResult` / measurement engine)

- Canonical 512-bin frequency grid (historical sample-rate baseline 44.1 kHz, roughly 43.1 Hz/bin; read actual HEAD settings).
- Per-bin source/return power spectra: `S_xx_db[]`, `S_yy_db[]`.
- Transfer function magnitude: raw and (when valid) calibrated (`tf_raw_mag_db[]`, `tf_cal_mag_db[]`).
- Coherence `gamma^2`, true complex cross-spectrum-based phase and unwrapped phase, calibrated phase, group delay (`group_delay_ms[]`) where valid.
- Capture and route metadata: timestamps, generator/stimulus and measurement settings, number of averaged frames, mode, FFT size, window, estimator, SOURCE/RETURN channel assignments.
- Result quality/mean coherence/valid-bin fraction, clipping, calibration applied/warnings/provenance; explicit missing data.
- Historical JSON fingerprint export and CSV baseline support.
- **Caution:** Historical source documentation contains inconsistent or transitional notes about higher-resolution 4096/8192 FFT modes; do not imply these modes are operational until HEAD and bench evidence prove it.

### Existing insight system (`InsightList`)

- Teensy-authored structured insights have mode **MEASUREMENT** vs **ADVISORY**, severity, title/detail/action, frequency, magnitude and source quality.
- Known historical algorithms target treble rolloff, midrange boost/cut, broadband level changes, polarity patterns, and group-delay/latency signals, subject to quality gates.
- Do not silently enlarge this list in the frontend. Where richer tone classification is desired, first define required data, algorithm, firmware ownership, and quality gating.

### Known limitations to respect

- A linear H(f) measurement **does not fully characterize distortion, compression, fuzz, attack/bloom, note separation, reverb, or other time-varying/nonlinear phenomena**. A low-coherence result can indicate noise, nonlinear effects, nonstationarity, or insufficient stimulus. Don't portray it automatically as a defective device.
- A direct electrical SOURCE/RETURN capture cannot independently judge a speaker's sound in a room unless suitable acoustic pickup/mic data are actually captured.
- Don't show **cable capacitance (pF), resistance (ohms), true pickup/input impedance, acoustic frequency response, automatic buffer placement, or room acoustic metrics** as measured facts without a verified sensor/circuit/test method and firmware feature. Some inspiration images show these as aspirational concepts, not as presently delivered capabilities.
- Never pretend the UI can set EQ corrections in an external rig unless genuine controllable hardware/software exists; an adjustment can be an **educational suggestion**, not an action the analyzer claims to perform.

---

## 3. The core conceptual distinction: 3 evidence levels

Build a transparent evidence model with visible badges/labels (design the exact language/appearance):

**A. MEASURED — direct, objective**

Examples: “−4.8 dB at 6.2 kHz,” “midrange notch centered at 930 Hz,” “coherence 0.96 in this band,” “group delay 2.7 ms,” “return peak −8.3 dBFS,” “gain difference vs reference +2.1 dB.” Include frequency range, reference/baseline, mode, timestamp and quality when useful.

**B. TONAL CHARACTERISTIC — measurable feature mapped to vocabulary**

Examples: “upper-mid emphasis,” “low-mid buildup,” “mid-scooped relative response,” “treble rolloff,” “strong harmonic activity” **only if the required signal analysis exists**. A computed label must point to supporting measurements and its definition, and must honor low-data/quality gates.

**C. PERCEPTUAL INTERPRETATION / SUGGESTION — evidence-informed but conditional**

Examples: “This upper-mid emphasis may be perceived as more forward or honky,” “This lower-mid rise may add body but risk muddiness in dense chords,” “Try a level-matched comparison with a small cut in this region.” Phrase as hypotheses where necessary; suggest a test that can confirm or refute them. Do not collapse human hearing, musical preference, or causes into absolute certainty.

The central CTA for every characteristic should be: **Show me where**, **Why does it sound that way?**, **Let me compare**, or **Help me hear it**.

---

## 4. Tone terminology → evidence framework

Research these primary reference articles and use their definitions, while preserving the distinction between data and metaphor:

- Belforti Instruments, *Guitar Tone Terminology: What the Words Really Mean*: https://belforti.shop/blogs/b-log/tone-terminology
- Seymour Duncan, *Dictionary of Tone Terms*: https://www.seymourduncan.com/blog/latest-updates/dictionary-of-tone-terms

Build an editable, validated **Tone Vocabulary Specification** (owned by the Teensy/firmware classification layer if used for actual judgments). For each term document: definition, physically measurable features, exact algorithm/proxy, stimulus/context required, sample/reference normalization, frequency regions as **initial research hypotheses** (not universal standards), thresholds and calibration procedure, confounders, reliability grade, and “listen for this” teaching guidance.

Seed investigation with the following map:

| Vocabulary | Initial measurable clues (NOT proof by themselves) | What requires more than static H(f) |
|---|---|---|
| Bright / Dark | high-frequency energy or TF tilt relative to a defined midrange/reference | playback level, monitoring chain, listening context |
| Warm / Thick / Fat | low-mid strength relative to upper bands; not just total bass | note clarity and dynamics; where the reference starts |
| Scooped | measurable midrange deficit versus neighboring lower/upper bands | whether that is desirable in a musical mix |
| Honky / Nasal / Boxy | localized midrange peaks/resonances compared with neighboring bands | listening tests; microphone/room context for acoustic cases |
| Thin | deficit in bass and low-mid support versus a controlled comparison | genre and mix role |
| Glassy / Sparkly | extended, smooth high end and harmonic energy where measurable | absence of harshness and perception cannot be guaranteed from single ratio |
| Piercing / Icepick / Harsh | upper-mid/treble emphasis and possible narrow peaks | level dependence, sensitivity, context; don't call injury from a spectrum |
| Muddy / Mushy | low-mid excess relative to useful definition | actual note overlap/articulation, distortion, decay, mix context |
| Crispy/Crisp / Attack | onset slope and timing in an envelope **if captured** | stable time-domain onset detection and consistent playing |
| Tight / Floppy / Chunky | low-frequency envelope, decay, attack and dynamics | pulse-response or note-by-note analysis beyond static TF |
| Compressed / Bloom / Sustain | time-varying dynamic-envelope/level relationships | calibrated before/after time-domain data and repeated controlled playing |
| Fizzy / Sizzle / Distorted | additional upper harmonics, distortion products, or modulation under suitable stimulus | nonlinear signal analysis; a linear transfer ratio alone is inadequate |
| Airy / Spacious | possible top-end openness, decay/diffuse effects | reverb-tail, stereo/spatial/acoustic capture as appropriate |
| Twang / Quack / Woody / Vintage / Creamy | characteristic blends of spectral and temporal cues | instrument/playing context; treat as comparative learned descriptors, not facts |

Do **not** hardcode arbitrary textbook frequency bands as if physics assigns one precise boundary to words such as *warm* or *honky*. Propose initial overlapping frequency zones, make them configurable, then validate with matched A/B recordings and player feedback.

Examples of good learner-facing language:

- “**Measured:** The rig boosts 1.1–1.7 kHz relative to your bypass capture. **Often described as:** more forward/nasal. Tap the highlighted region to see why.”
- “**Measured:** Low mids are +3.2 dB relative to the baseline. **You might hear:** added body. A dense chord test would help determine whether it is also muddy.”
- “**Not enough evidence:** Source energy is low in this band. Play a different phrase or run an appropriate approved test.”

### A practical tonal feature catalog (new Teensy fields if needed)

Ask what can responsibly be calculated from existing results and what needs more sensing:

- Spectral tilt; broad-band and narrow-band gain change; peaks/notches center/width/Q; low/mid/high energy ratios relative to measured SOURCE and baseline.
- Band-specific coherence and uncertainty/quality masks; calibration and clipping summary; latency/group-delay and phase irregularity where trustworthy.
- Dynamic range/crest factor, onset/attack and decay rates, compression curves—**only with valid temporal measurement data and repeatable stimulus**.
- Harmonic ratios/distortion metrics, intermodulation, time-varying modulation, and reverb decay—**future validated measurement routines, not inferred from a single FFT**.
- Tone matching/A-B fingerprint features, repeatability across captures, and user-defined target/reference comparisons—require comparable test conditions and provenance.

Every new semantic feature should expose in the protocol: `feature_id`, `value`, `units`, `frequency_band`, `reference`, `quality/validity`, `evidence`, `algorithm_version`, and `source_result_id` (or equivalent), with clearly defined optional fields. Design no frontend-side scientific verdicts.

---

## 5. Visual design system: premium dark-mode instrument

**Mood:** deep-ink/near-black surfaces with restrained, high-luminance spectral color. Not a generic SaaS sales dashboard and not a neon arcade. The graphs are the hero; controls recede until needed. Surface should feel fast, tactile, precise, musical, and unusually beautiful.

**Suggested palette (explore, do not blindly copy):** graphite `#090C12`; layered navy `#111827`; soft hairlines `#253047`; cyan/ice-blue `#38D6F5`; electric violet `#8C62FF`; magenta `#E856FF`; spring/teal `#55E5B0`; golden amber `#FFBF50`; coral for overload/critical conditions `#FF6474`. Color must have stable **semantic purpose**; never use green/red alone for validity. Offer a colorblind-friendly alternative and reduced-motion mode.

**Typographic and compositional direction:** precise, crisp numerals; spacious instrument-style labeling; no tiny legends or unreadable fine print; generous graph viewport; high-quality anti-aliased lines; gradient fills used to clarify depth/intensity. Avoid noisy textures, unnecessary glow, crowded mini-cards, and generic KPI tiles.

**Motion:** smooth but faithful: interpolate display positions without inventing data, keep frequency bins stable, use controlled fade/trails with an explicit persistence window, use rate-limiting and graceful low-FPS fallback. Paused/frozen/replay must be labeled. Animations should be attractive on a stationary screenshot **and** during actual playing.

**Form factor:** detect and report current Touch Display 2 native dimensions, actual installed rotation, OS scale, browser viewport and touch behavior. Design responsive layouts for actual Pi **portrait and/or landscape as configured**, plus desktop development. Do not hardcode an old 800x480 RA8875 target as the production display. Aim for appropriately large touch targets (~44 logical CSS px or larger depending on scale), simple one-handed navigation, and high visibility at arm's length.

**Design principles:**

1. A player should understand “what changed?” in about three seconds.
2. There is always a visible way to tell **what is measured vs inferred**.
3. Advanced detail is available with one tap, not permanently jammed onto the dashboard.
4. Axis labels, dB reference, frequency, time and provenance remain accessible even for spectacular 3D views.
5. Data quality directly affects color/opacity/masking; quality does not live only in a buried Settings page.
6. The interface must still be excellent with advanced 3D disabled.

Use the attached UI photos as *visual references*, not as literal functional specifications. Especially note (a) saturated 3D waterfalled spectra, (b) smooth and delicate cyan/purple flowing line-contour terrain, (c) restrained dark analytics with radiant gradients, (d) radial 3D tone fingerprint, (e) premium small-screen instrument panels. The photographs featuring impedance, cable capacitance and imaginary scores are design inspiration **only**, not claims about finished firmware.

---

## 6. Information architecture and navigation to design

Design an explicit navigation hierarchy with consistent Back/Home, current measurement, save/freeze/compare, quick access to settings, and visible current route/health.

Suggested top-level destinations (adjust after reviewing existing app):

1. **LIVE / PLAY** — source/return level, fast RTA-style response, strongest observed rig differences, immediate on-screen feedback, quality and clipping. Primary stage-demo view.
2. **TONE EXPLORER** — derived descriptors with supporting evidence, interactive annotated frequency bands, “What this might sound like,” A/B relationship, and non-prescriptive experiments for improvement.
3. **LAB / ANALYZE** — full precision-oriented spectrum, transfer function, source/return overlay, coherence, phase and group delay; cursor inspection, units, baseline, calibration, status, exports.
4. **3D STUDIO** — functional, manipulable 3D waterfall, radial landscape, contour field, or other data-grounded views; camera/preset controls, educational overlay, quality rendering.
5. **COMPARE / LIBRARY** — snapshots A/B, overlay/difference, named rig configurations, matched capture settings, saved fingerprints and metadata. Only expose features actually supported by storage/protocol.
6. **LEARN / EAR TRAINING** — choose a tone trait, predict the difference, perform/safely audition controlled examples where actual audio playback exists, reveal the plot, read the evidence, track practice *locally only if implemented*.
7. **SETUP / DIAGNOSTICS** — connected jacks, SOURCE/RETURN selection, injection/generator state, safe level setup, calibration, export, protocol/firmware versions, missing features, recovery/debug.

Do not put all seven on a 7-inch screen simultaneously if it causes crowding. Consider four prime destinations + contextual secondary pages, a thoughtful bottom tab bar or slim rail, and full-screen graphs with a single consistent back gesture/button. Demonstrate the navigation with a clickable, coherent flow: live → inspect peak → tone explanation → compare → save/return.

Permanent status signals should include, as available from actual protocol: active SOURCE/RETURN route; measurement mode and capture state; clipping/level caution; calibration state; freshness/connected state; quality on results. Never bury a disconnected or uncalibrated condition beneath a beautiful chart.

---

## 7. Visualizations: classics + functional 3D experiments

Provide **standard, trusted views** even if innovative views become the signature:

- Spectrum analyzer/RTA with logarithmic Hz axis, dB axis and source/return overlay, selectable persistence/peak hold and valid-data masking.
- Transfer-function magnitude `RETURN/SOURCE` vs frequency, prominently featuring **0 dB** as no change, +dB boost and −dB attenuation; coherent masked gaps.
- Coherence vs frequency (0–1) with explicit limits and context: a quality indicator for TF confidence, not a simple universal “tone score.”
- Phase and group delay with quality masking and calibration information.
- Time-history / waterfall of repeated **actual** frames with clear time axis; note that old trails must be stored intentionally rather than invented from one frame.
- Before/after A/B overlays and **Teensy-authored or appropriately authorized** band differences with a reference label and level-matching warning.
- Peak/clipping and route/measurement state in compact, useful instrument displays.

**Propose at least 8 inventive visual concepts, then recommend the best 3 for rapid prototype and the best 1 for the portfolio demo.** Feel free to reject these starting points and invent something much more original:

### Candidate experimental directions

**1. Tone Terrain / Spectral Mountains** — X = log-frequency, Y = recent capture history/time, Z = SOURCE/RETURN spectral amplitude or TF difference; color = amplitude or delta (explicit legend). A moving landscape where a boost becomes a ridge and a cut becomes a valley. Show response vs spectrum distinctly.

**2. Contour River / Neon Topography** — smooth luminous stacked contour lines (purple/cyan/white) that move with actual history. Mark low-mid body, mid scoop, upper-mid focus, treble air with unobtrusive labels tied to real frequency bands. Don't bend geometry gratuitously; explain what height, spacing, color and movement encode.

**3. Radial Tone Fingerprint 2.0** — map frequency around a circular ring (or around a sector with clear directional legend), height = transfer magnitude relative 0 dB, hue distinguishes boost from cut, alpha = quality. Compare two captures as concentric rings. Design around touch readability and the discontinuity where the frequency scale wraps.

**4. Two-River SOURCE/RETURN** — two aligned spectral ribbons flowing toward each other; their difference is emphasized at corresponding frequencies. Rich visual metaphor that *directly teaches* why two signals are measured and what H(f) means.

**5. Harmonic Aurora** — bright standing columns or shimmering strands associated with harmonic content from a verified note/tonal analysis. **Only** label fundamentals/harmonics/distortion if the needed detection really exists; otherwise propose it as future firmware R&D.

**6. Coherence Veil / Trust Field** — overlay translucent fog / desaturation over frequency regions with poor validity, low source excitation, high uncertainty or clipping. Show precisely which parts of the graph can be trusted and which cannot. Make the quality gate visually intuitive.

**7. Time-Lens / Delay Sculpture** — shape a time/frequency field using Teensy-provided phase/group delay, with stable numeric scales and appropriate cautions; let user select a frequency and see whether delay differs across bands.

**8. Sculpted A/B Ghost** — a frozen reference contour and a live contour share one spatial view, with an illuminated separation wherever the rig changes the spectrum. The contour is a **comparison**, not just decoration.

**9. Tone Constellation** — stars/points for defined features (energy bands, resonances, measured shifts), positioned using meaningful coordinates. Selection reveals exact measurement. Never randomize stars as if they are meaningful spectral data.

**10. Touch-to-Hear Spectrum** — touching a band displays its measured effect and, if actual authorized audio examples/monitoring exist, enters a safe guided A/B practice experience. If audio playback is absent, the educational walkthrough still works without pretending to make sound.

For EVERY visual proposal give a mini specification:

- Insight users obtain in 3 seconds, and teaching value for a beginner.
- Exact data fields and provenance, including proposed Teensy additions.
- Mapping of each visual dimension (x/y/z/hue/opacity/motion) to a real physical quantity or state.
- Axis/unit/legend/touch behavior; source versus return versus TF distinction.
- Quality-mask/NaN handling, capture freshness, slow-data behavior.
- Expected Pi 5 GPU/rendering cost, graceful 2D fallback, reduced-motion option.
- Thumbnail/wireframe, an end-to-end user interaction, and one reason the design might fail.

Do not stack several WebGL canvases simultaneously if it makes the Pi unstable. For new rendering engines/libraries, first inspect the existing stack and justify any additional dependency; prefer a reproducible, performance-bounded rendering path. Three.js/WebGL/shader use is an option, not a mandate. Keep numeric overlays sharp and available above 3D graphics.

---

## 8. Make tone descriptors interactive, useful, and testable

Design a signature experience called **“What Changed My Tone?”** (name is provisional). It should work like this:

1. Player plays the guitar or runs a safe, permitted stimulus and sees LIVE data/validity.
2. UI highlights a **real, measured** difference from SOURCE to RETURN or a named baseline. E.g., a highlighted low-mid rise or narrow upper-mid peak.
3. A small tag offers a vocabulary connection: “More body / possibly warmer,” “Mid-scooped,” or “Upper-mid focus.” These are **not absolute verdicts**.
4. Tap tag → a teachable micro-panel: **measurement / audible description / where on graph / likely context / how to test / what a change may accomplish**.
5. Offer one concrete, reversible action to *try outside the instrument* (“Compare with your EQ band lowered by ~2 dB near this region,” when warranted). Do not assert it has altered the player's physical signal.
6. Store a reference/compare only if the current device actually supports this. Where not supported, demonstrate as explicit planned functionality.
7. In a practice mode, invite the learner to listen *before revealing* the descriptor, then compare their observation to the measured feature.

The **expert mode** should present dense, exact curves and numbers, uncertainty/provenance, and minimal advice. **Learn mode** should present a beautiful annotated visualization, simple language, and optional listening exercises. Both must show the same authoritative Teensy data, not separate contradictory algorithms.

### Essential experiments

- **Band highlight:** one measured boost/notch and a single human-readable adjective; linked cursor in all views.
- **Bright vs dark:** level-matched A/B using actual captures; a trace overlay with teaching text.
- **Mid scoop:** overlay low/mid/high regions and show exactly why the descriptor was offered.
- **Coherence confidence:** demonstrate that some curves are not interpretable when the data quality fails; teach users that absence of evidence is not an EQ value.
- **Nonlinear distortion example:** if not implemented, explicitly mark a future measurement experiment, not an unsupported diagnosis.

---

## 9. Robust interaction, data and acceptance requirements

### Navigation and controls

- Every page must offer a safe, discoverable route back; no dead ends.
- Quick start to live mode; freeze/unfreeze, switch measured visualization, inspect exact Hz/dB value, save/compare where truly supported.
- Touch dragging, pinch/zoom or explicit zoom/reset controls, large precision-safe selectors, back/home that work without a physical keyboard.
- Consistent measurement states: idle, armed, capturing, processing, result, aborted, disconnected, stale, failed calibration, clipping.
- Clear accidental-tap protection for any injection/routing/gain-sensitive commands.

### Data integrity

- Read the **current serial/network/protocol contract** first. Propose schema additions as needed; do not parse undocumented assumptions.
- Live timestamps, reconnection behavior, missing packet behavior, version/schema compatibility, and a visible simulation/demo indicator.
- Controlled fixture playback for UI development; test with silence, single tone, broadband stimulus, steep EQ, clipped data, low coherence, no calibration, NaNs, route changes, and disconnected Teensy.
- Test math/visual encoding with known arrays: flat 0 dB line, a +6 dB peak, a −12 dB notch, gaps, and A/B identical traces. **Fixture labels must clearly mark these as artificial.**
- Avoid untruthful UI strings like “All Good” for a partly unknown rig; distinguish instrumentation/measurement readiness from judgments about music.

### Accessibility and performance

- Dark surfaces with legible chart labels and real contrast; color alone never carries pass/fail, boost/cut or severity.
- Tap targets sized for the real 7-inch screen. No mouse-hover-only interactions.
- Profile memory, render FPS, CPU and startup time on the **actual Pi 5**, not only the Mac.
- Aim for smooth movement at a sustainable frame rate; a consistent 25–30 FPS 3D view with reliable interactivity can beat a stuttering nominal 60 FPS. State the tested frame rate rather than inventing it.
- Pause/reduce animations when the tab/page is hidden; fallback to 2D when needed. Keep measurements safe even when graphics lag.
- Put diagnostic readouts and build/protocol version information behind a deliberate diagnostics screen.

### Portfolio reality

An excellent final demo is **an instrument that genuinely measures and explains one noticeable rig difference** and displays it through a polished, scientifically correct UI. A dozen unvalidated features are a weaker result. Provide a stable “demo route” containing the real input, a contrast between two rig conditions, a convincing graph, an explained term, and an honest evidence trail.

---

## 10. Work with me iteratively, not as a monolithic build

I want creative experimentation and will decide what stays. Do not implement every idea or overengineer features I have not chosen.

### Stage A — audit / reality check (**first response; no edits**)

Report the newest UI implementation, the current screen and data path, shipped vs missing measurements, display reality and 3 most important integration risks. List which requests require new firmware/hardware versus UI-only work. Flag any conflicts with current ADRs. Identify the minimum viable portfolio-quality UI.

### Stage B — visual direction and navigation (**design; no full rewrite**)

Show **three distinct art directions**, with color/typography/motion references and a clear proposed IA for each. Include one deliberately restrained lab instrument, one visually bold spectrum/tone explorer, and one experimental 3D direction. Explain which should become the coherent production design. Give quick sketches/interactive previews/screenshots at the REAL screen geometry.

### Stage C — experimental visualization auditions (**only 1–3 at a time**)

Propose 8+ concepts in a brief catalog; choose the top 3, then produce a **working prototype of ONE** selected new visualization using deterministic, clearly labeled fixture data (unless real Pi data is already connected safely). Keep the real architecture untouched while evaluating. Ask for feedback: **KEEP, REVISE, or DISCARD**. Do not stack abandoned experiments into production navigation.

### Stage D — integrate the winner with current UI

After selection, connect to the Teensy-authored protocol with proper invalidity masks and units; implement consistent navigation/controls and use the existing app infrastructure whenever sensible. Any new semantic analysis is proposed as a separate reviewed firmware/protocol change, with tests and no silent Pi inference.

### Stage E — device validation and portfolio capture

Run on the **physical Pi 5**, confirm display orientation, responsiveness and touch behavior, verify numerical agreement with the corresponding Teensy/serial result, inspect route/injection safety, and record the screenshot/demo flow. Provide an honest test record: PASS/FAIL/NOT TESTED, actual hardware observations, build SHA, any performance measures, remaining limitations. Then stop redesigning and help me capture project evidence.

### Expected deliverables (progressively)

1. **Current UI and measurement-data audit** with evidence and known unknowns.
2. **Product navigation map + information hierarchy** for expert and learner journeys.
3. **Visual design tokens**: type, palette, spacing, states, axes, legend language, motion and accessibility.
4. **Tone Vocabulary Specification** that separates measurable descriptors from perceptual hypotheses.
5. **Concept gallery** of novel views with truth-encoded mappings and resource estimates.
6. **One runnable UI prototype** for the best first experiment and a clear keep/revise/discard decision.
7. Only then a **small scoped integration plan** showing exact changed files, tests, rollback, and real-device validation.

### First reply to me — exact request

**Start by inspecting current Git HEAD and repository contents (read-only) and summarize what exists.** Then propose a concise direction for the minimum viable production interface and list the **three most promising, genuinely distinct visualization experiments**. Explain the measure-vs-interpretation boundary and identify which tone words can be supported with current data and which need new routines. **Do not start a rebuild or modify the repository yet.** I will choose the first concept to prototype.

I want this to be both a serious instrument and a source of joy when watching and exploring music. Surprise me with original, useful concepts—but make every beautiful claim traceable to valid evidence.

---

## Reference / provenance note

This brief was compiled using prior shared firmware module PDFs (`audio_capture`, `audio_engine`, `measurement_engine`, `measurement_core`, `insights_engine`, `calibration_store`, `export_engine`, `signal_generator`) and the user's design inspiration images. Those source PDFs are **historical snapshots**; current HEAD, active contracts, and real bench evidence are definitive. Upload the separate visual reference contact sheet and/or images to Claude's active project if they are not already present there; Claude cannot automatically see images from a different chat application.
