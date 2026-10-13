<!-- ============================ IMPORT HEADER ============================ -->
<!--  Everything BELOW the end-of-header marker is the imported document,   -->
<!--  byte for byte. Nothing in the body has been edited. Do not edit it    -->
<!--  in place: this file is a record of what was specified, and a          -->
<!--  correction belongs in docs/ui/README.md where it can be dated.        -->
<!-- ====================================================================== -->

> # 📥 IMPORTED — not written here
>
> **This is the UI specification of record**, imported under
> [ADR-005](adr/ADR-005-pi-rendering-stack-and-presentation-semantics.md)
> *Consequences* step 2 and TODO-67. Imported **2026-10-12** from
> `~/Downloads/visual_design_document.md`, where it had sat outside version
> control since it was located on 2026-09-30.
>
> | | |
> |---|---|
> | Document version | **1.2** ("v0.6.1 milestone") |
> | Source | `~/Downloads/visual_design_document.md`, mtime 2026-09-30 21:42 |
> | SHA-256 of the original | `73b4d721fd704366f234763a7c176744d22b8742a402e70e1596be2e70eb78bf` |
> | Body below this header | unmodified |
>
> **Verify the body is unmodified:**
> ```sh
> tail -n +56 docs/visual_design_document.md | shasum -a 256
> # expect 73b4d721fd704366f234763a7c176744d22b8742a402e70e1596be2e70eb78bf
> ```
>
> ---
>
> ## 🔻 Two markings this import is required to carry
>
> **1 — Every RA8875 section below is the DEMOTED display target.**
> [ADR-001](adr/ADR-001-display-architecture.md) demoted the RA8875 on
> 2026-09-11; ADR-005 *Consequences* requires that demotion be marked here.
> This document predates both. Wherever it says *"RA8875 implementation
> notes"*, *"RA8875 HARDWARE CONSTRAINTS"*, *800×480*, *RGB565*, or targets
> the device screen, read it as **reference material for a target that is no
> longer the product**. The production renderer is a kiosk web client on the
> Pi 5 at **720×1280 portrait** (ADR-005 §1). The RA8875 sections are retained
> because they contain real reasoning about draw budgets and layering, not
> because the target is live.
>
> **2 — This document does not outrank the repository.**
> Where it disagrees with current HEAD, an accepted ADR, the wire contract, or
> bench evidence, **the repository wins** (journal source-of-truth precedence,
> 2026-08-25 and 2026-09-13). ADR-005 retains architectural authority. Known
> disagreements are enumerated and resolved in
> [`ui/README.md`](ui/README.md) — read that before implementing from this file.
>
> **Referenced JSX concepts** now live in [`ui/concepts/`](ui/concepts/).
> `VortexTunnel.jsx` is **not** among them, and the reason is recorded there.

<!-- ========================= END OF IMPORT HEADER ======================== -->

# Guitar Rig Analyzer — Visual Design Document

## Document Status
**Version:** 1.2  
**Date:** v0.6.1 milestone  
**Purpose:** Captures all committed and proposed display visuals for the RA8875 device screen and the Pi 5 display processor. This is the authoritative reference for display implementation across both targets.

## Design Philosophy

This is a guitar tool, not a lab instrument. The display must:
- Feel alive, luminous, and musical — not sterile or clinical
- Be instantly readable by a guitarist who thinks in tone, not bins
- Look good enough that a player wants it on their pedalboard face-up
- Clearly separate measured facts from inferred guidance
- Never present undefined data as real measurements

**Visual language:** Dark backgrounds, glowing accent colors, smooth curves with gradient fills, soft bloom effects. Inspired by modern DAW interfaces and premium guitar modelers (Quad Cortex, Helix), not 1990s spectrum analyzers.

**Color palette:**

| Role | Color | Hex | Notes |
|------|-------|-----|-------|
| Background | Near-black | `#060a10` | Deep blue-black, not pure black |
| Panel bg | Dark navy | `#0a0e16` | Subtle contrast from background |
| Source accent | Steel blue | `#3498db` | Instrument input signal |
| Return accent | Emerald green | `#2ecc71` | Rig return signal |
| Transfer function | Warm amber | `#f0a030` | The rig's tonal signature |
| Boost (outward) | Blue → green | `#2088d0` → `#30c850` | Added energy |
| Cut (inward) | Yellow → red | `#d0b020` → `#e83030` | Missing energy |
| Grid lines | Faint blue-grey | `rgba(40,60,90,0.25)` | Present but not distracting |
| Labels | Muted slate | `#4a6578` | Legible without competing |
| White text | Soft white | `#d8e4f0` | Not harsh pure white |

---

## COMMITTED VISUALS

These are approved for implementation. Reference mockups exist as JSX artifacts.

---

### 1. Radial Tone Fingerprint ✅ COMMITTED

**Reference:** `radial_tone_fingerprint.jsx`  
**Screen:** Primary live view OR dedicated view (switchable)  
**Data source:** Live `tf_db[512]` from audio_engine (or `tf_cal_mag_db[512]` from result)  
**Update rate:** ~11 Hz (every averaged output block)

#### Description

A circular spectral comparison display centered on screen. The instrument's tonal signature is rendered as a living, breathing radial pattern.

#### Layout

- **Center:** Fixed dark circle (radius ~88px) representing the input baseline (zero reference). This circle never changes size. It is the visual anchor.
- **Border:** Thin white line with soft glow and subtle pulsing — slow heartbeat feel, responds gently to signal presence. Communicates "the circle is alive" without overpowering the spectral motion.
- **Spectral segments:** Ring of 48 evenly-spaced radial lines arranged symmetrically around the circle.

#### Frequency mapping (radial position)

| Clock position | Frequency range | Musical name |
|---------------|-----------------|--------------|
| 6 o'clock (bottom) | 20–60 Hz | Sub |
| ~7:30 / 4:30 | 60–200 Hz | Bass |
| ~9:00 / 3:00 | 200–2 kHz | Mids |
| ~10:30 / 1:30 | 2–8 kHz | Upper / Presence |
| 12 o'clock (top) | 8–20 kHz | Air / Treble |

Frequency rises symmetrically up both sides — matching bands appear as mirrored pairs on left and right. This creates a mirrored circular spectrum.

#### Segment behavior

- **Outward from circle** = return has MORE energy than input at that frequency (boost)
- **Inward toward center** = return has LESS energy than input (cut)
- **Distance from circle** = magnitude of spectral difference (dB)
- **Thickness of segment** = absolute signal energy at that frequency (stronger = thicker, weaker = thinner)

#### Color behavior

| Direction | Near circle | Far from circle |
|-----------|------------|-----------------|
| Outward (boost) | Deep blue `#2088d0` | Shifting to green `#30c850` |
| Inward (cut) | Yellow `#d0b020` | Orange to red `#e83030` |

#### Rendering technique

- Each segment rendered as 3 layered strokes: outer glow (wide, low alpha), mid glow, core line (narrow, high alpha)
- Gradient along each segment from near-circle to far-end
- Catmull-Rom or similar smoothing NOT needed — segments are straight radial lines, smoothness comes from the count and glow
- Line cap: round
- Center circle drawn FIRST, then segments ON TOP, then pulsing border ON TOP of everything

#### Rendering order (critical)

1. Background + guide rings
2. Center circle (dark fill + subtle radial gradient)
3. Center label ("INPUT BASELINE") — faint, under segments
4. Spectral segments — both outward (boost) and inward (cut)
5. Pulsing border glow + white ring — on top of everything
6. Frequency labels around outside
7. Legend (boost/cut color key)

#### Key constants

| Constant | Value | Notes |
|----------|-------|-------|
| `BASE_R` | 88 px | Center circle radius |
| `MAX_OUT` | 130 px | Maximum outward extension |
| `MAX_IN` | 70 px | Maximum inward extension |
| `NUM_BANDS` | 48 | Spectral segments (24 per side, mirrored) |
| `PULSE_SPEED` | ~1.2 Hz | Border glow breathing rate |
| `MIN_THICKNESS` | 1.5 px | Minimum segment width (low energy) |
| `MAX_THICKNESS` | 6 px | Maximum segment width (high energy) |

#### Preset signatures (verified in mockup)

| Rig type | Visual signature |
|----------|-----------------|
| Overdrive pedal | Bass blooms outward (bottom), mid scoop cuts inward (sides), presence pushes out (upper sides), HF rolls inward (top) |
| Clean boost | Gentle outward expansion everywhere, slight treble lift near top |
| Wah (mid position) | One dramatic band pushes far outward in mids, everything else collapses inward |
| Long cable | Bottom half unchanged, top half progressively cuts inward with warm yellow→orange→red |
| Pink noise (flat) | Full symmetric outward bloom if rig adds gain, or full symmetric inward collapse if rig attenuates — reveals overall tonal balance as a complete shape |

#### RA8875 implementation notes

- Uses `drawLine()` per segment — 48 bands × 2 sides × 3 layers = ~288 line draws per frame
- Fill gradient approximated by layered strokes at different widths/alphas
- No alpha blending needed — glow layers use progressively wider, dimmer strokes
- `fillCircle()` for center baseline
- Text rendering for labels at fixed positions (not per-frame computed)
- Target frame rate: 10–15 fps acceptable for the breathing animation

---

### 1b. 3D Radial Tone Fingerprint ✅ COMMITTED

**Reference:** `radial_tone_3d.jsx`  
**Screen:** Dedicated view (companion app or future display hardware with GPU)  
**Data source:** Live `tf_db[512]` from audio_engine (or `tf_cal_mag_db[512]` from result)  
**Update rate:** ~30–60 fps (Three.js WebGL)

#### Description

A rotatable 3D version of the Radial Tone Fingerprint. The baseline is a thin pulsing white ring floating in space (no solid disc). Cylindrical bars rise upward for boosts and drop downward for cuts. The user can orbit freely (full 360°) with touch/mouse drag to view from any angle — above, below, or side-on. A cyan reference line anchored to the ring tracks the closest frequency to the viewer, with a real-time frequency readout.

#### Layout

- **Baseline ring:** Thin white torus (radius 0.012) at y=0, pulsing with the same heartbeat timing as the 2D version. No solid disc — bars are fully visible above and below.
- **Bars:** 48 mirrored band pairs (96 cylinders total), arranged on a circle at 88% of ring radius. Bars extend upward (boost) or downward (cut) from the ring plane.
- **Reference line:** Short cyan cylinder (25% of max bar height) anchored to the ring at the closest point to the camera. Always visible in front of the bars.
- **Reference dot:** Small cyan sphere where the reference line meets the ring.
- **Frequency readout:** Cyan text rendered on a 2D canvas overlay, top-left corner, 22px bold monospace with glow shadow. Updates every frame as the view rotates.

#### Frequency mapping (same as 2D)

- Bottom of circle (closest when viewed from default angle): lowest frequencies (20 Hz)
- Top of circle: highest frequencies (20 kHz)
- Left and right sides: mirrored (same frequency appears twice)
- As the user orbits, different frequency regions rotate to the front

#### Bar behavior

- **Upward from ring** = boost (return has more energy than input)
- **Downward from ring** = cut (return has less energy)
- **Height** = magnitude of spectral difference (dB)
- **Thickness (radius)** = absolute signal energy at that frequency

#### Color behavior — per-bar proportional gradient

Each bar has a gradient spanning its full length from base (near ring) to tip (far end):

| Direction | Base (at ring) | Tip (far end) |
|-----------|---------------|---------------|
| Boost (up) | Deep blue `rgb(0.1, 0.3, 0.95)` | Bright green (shifting with magnitude) |
| Cut (down) | Bright yellow `rgb(1.0, 0.9, 0.15)` | Deep red (shifting with magnitude) |

The gradient spans proportionally across each bar regardless of height. This makes short and tall bars equally distinguishable by color pattern — every boost bar shows the blue→green transition, every cut bar shows yellow→red.

#### Interaction

- **Drag/swipe:** Full 360° orbit. Swipe right rotates view right, swipe left rotates left. No angle clamping — user can orbit underneath to inspect cut bars from below.
- **Auto-rotation:** Slow continuous orbit when not being dragged. Creates the mesmerizing "floating in space" effect.
- **Touch support:** Full touch drag with preventDefault for smooth mobile experience.

#### Reference line behavior

- Anchored to the ring (DISC_RADIUS), not the bar radius — always in front of bars from the viewer's perspective
- Tracks the closest point on the ring to the camera, recalculated every frame
- Frequency readout uses angular distance from the bottom of the circle: bottom = 20 Hz, sides = mids, top = 20 kHz
- Left/right sides are mirrored (same frequency on both sides)

#### Key constants

| Constant | Value | Notes |
|----------|-------|-------|
| `DISC_RADIUS` | 2.8 | Ring radius in 3D units |
| `MAX_BAR_HEIGHT` | 3.5 | Maximum bar extension |
| `NUM_BANDS` | 48 | Spectral segments (× 2 for mirror = 96 bars) |
| `MAX_DB` | 18 | Full-scale dB range |
| `camDist` | 8.5 | Camera orbit distance |
| Ref line height | 12.5% of MAX_BAR_HEIGHT | Small marker, not dominant |
| Ref line radius | 0.04 | Thick enough to be visible |

#### Verified preset signatures (interactive mockup)

| Preset | Visual signature |
|--------|-----------------|
| Overdrive | Bass columns rise tall (blue→green) at bottom, mid-scoop bars drop (yellow→red) on sides, presence peak rises on upper sides, HF drops at top |
| Clean Boost | Gentle short bars rising everywhere — mostly blue with hints of green |
| Wah (mid position) | Dramatic single-band spike on sides, everything else drops below the ring |
| Long Cable | Bottom half unchanged (tiny bars), top half drops progressively deeper (yellow→orange→red), visible when orbiting underneath |

#### Implementation notes

- Built with Three.js (r128 available in artifact environment)
- `MeshBasicMaterial` with `vertexColors: true` for vivid colors unaffected by lighting angle
- No glow/shadow bars — single cylinder per band for clean rendering
- Frequency readout rendered on a transparent 2D canvas overlay (pointer-events: none)
- No fog — clean dark background for maximum color vibrancy
- Lighting: ambient white (0.45) + top point light + warm underlight for cut bar illumination

#### Platform considerations

This visualization uses WebGL and is designed for a companion app or future hardware with GPU capability. It is NOT targeted at the RA8875 display (which lacks 3D rendering). Potential deployment paths:
- Companion smartphone/tablet app connected via Bluetooth or USB
- Web dashboard for desktop review of exported measurement data
- Future hardware revision with a GPU-capable display
- The 2D Radial Tone Fingerprint (Section 1) is the RA8875-targeted equivalent

---

### 2. Live Spectrum (Filled-Area Curves) ✅ COMMITTED

**Reference:** `display_concept_v2.jsx`  
**Screen:** Live view  
**Data source:** `fft_source[512]`, `fft_return[512]` from AudioFrame

#### Description

Two overlaid filled-area spectrum curves — source (blue) and return (green) — rendered with smooth Catmull-Rom spline interpolation, vertical gradient fills, and subtle glow lines. The fill gives visual mass so energy distribution is instantly readable.

#### Style

- Smooth flowing curves (not jagged point-to-point)
- Vertical gradient fill: vivid accent color at peak → transparent at baseline
- Source rendered first (under), return on top — overlap visible through transparency
- 2px main line with wider soft glow underneath
- Log-frequency x-axis, dBFS y-axis
- Musical frequency labels: bass / mids / treble alongside Hz values

#### RA8875 implementation notes

- Catmull-Rom is too expensive on RA8875 — approximate with column-by-column `drawFastVLine()` fills
- Each column: one vertical line from baseline to curve value, colored with the accent color
- Overlay achieved by drawing return AFTER source — no true alpha blending needed
- Glow approximated by drawing the curve trace at 3px width in a dimmer shade, then 1.5px in full accent

---

### 3. Transfer Function Curve (Split-Fill) ✅ COMMITTED

**Reference:** `display_concept_v2.jsx`  
**Screen:** Live view (lower panel) and Result view (main panel)

#### Description

The rig's tonal signature as a smooth amber curve on a ±18 dB grid. Fills differently above and below the 0 dB reference line — warmer above (boosts), cooler below (cuts). The 0 dB line is dashed and prominent.

#### Style

- Smooth Catmull-Rom curve (approximated on RA8875)
- Above 0 dB: amber gradient fill from curve down to zero line
- Below 0 dB: muted warm gradient fill from zero line down to curve
- Prominent dashed 0 dB reference line
- "▲ louder" and "▼ quieter" hints at panel edges
- Thicker line (2.5px) for the hero curve

---

### 4. Level Meters (Gradient Bars with Peak Hold) ✅ COMMITTED

**Reference:** `display_concept_v2.jsx`  
**Screen:** Live view (top panel)

#### Description

Horizontal gradient-filled bars with peak-hold indicators and dBFS readout. Source (blue) and Return (green).

#### Style

- Rounded-corner bar background
- Gradient fill: green → yellow → red across the range
- White peak-hold line (2px) that decays slowly (PEAK_DECAY_DB_PER_UPDATE)
- Numeric dBFS readout to the right of the bar
- Clip threshold turns readout red

---

### 5. Result View (Quality Badge + Insight Panel) ✅ COMMITTED

**Reference:** `display_concept_v2.jsx`  
**Screen:** Result view (after measurement completes)

#### Description

Header with colored quality pill badge, coherence/valid-bin stats, and provenance line. Main area shows the TF result curve (large). Right panel shows insights with M/A distinction.

#### Insight panel style

- Each insight: colored tag pill (M=amber, A=teal, alert=red) + title + detail
- Tag pill has subtle colored background wash
- Measurement facts feel bold and definitive
- Advisory items feel softer — slightly muted color, indented detail
- Footer shows available commands

---

### 1c. Split Tone Fingerprint (3D) ✅ COMMITTED

**Reference:** `ToneFingerprintSplit.jsx`  
**Screen:** Dedicated view (Pi 5 + Touch Display 2, 720×1280 portrait)  
**Data source:** Live `tf_db[512]` from data_sender live frame packets  
**Update rate:** ~10.8 Hz data, interpolated to 60 FPS rendering

#### Description

An evolution of the 3D Radial Tone Fingerprint that splits the ring into two meaningful halves instead of mirroring the same data. The left side shows missing/attenuated frequencies (cold colors, bars dropping below the ring), and the right side shows augmented/boosted frequencies (warm colors, bars rising above the ring). Direction reinforces meaning: down = loss, up = gain.

#### Layout

- **Left half of ring:** Missing/attenuated frequencies. Bars DROP BELOW the ring plane in cold cyan colors. Deeper cuts = taller downward bars.
- **Right half of ring:** Augmented/boosted frequencies. Bars RISE ABOVE the ring plane in warm orange colors. Stronger boosts = taller upward bars.
- **Divider line:** Thin horizontal line separating the two halves.
- **Baseline ring:** Thin white pulsing torus (same heartbeat as other versions).
- **Cyan reference line:** Short cyan cylinder anchored to the ring, tracking the nearest frequency. Frequency and dB readout on the 2D overlay.

#### Color scheme

| Side | Meaning | Direction | Base color | Alert color |
|------|---------|-----------|------------|-------------|
| Left | Missing / attenuated | Below ring (↓) | Cyan `#4cc9f0` | Light cyan `#90e0ef` |
| Right | Augmented / boosted | Above ring (↑) | Orange `#ff7b00` | Gold `#ffd166` |

#### Pi optimization features

- **InstancedMesh:** Two instanced meshes (cold + warm) instead of 96 individual meshes — collapses to 2 draw calls.
- **Frame interpolation:** Data arrives at ~10.8 Hz; `lerp` smoothing at 0.16/0.14 makes rendering feel 60 FPS.
- **Pixel ratio capped at 1** for stable frame rate on embedded GPU.
- **Static materials** with per-instance color instead of per-frame vertex buffer rewrites.

#### Interaction

- Full 360° orbit — no vertical clamping. User can orbit underneath to inspect cut bars.
- Touch support with swipe-to-rotate.
- Pause/resume orbit button.
- Camera looks at ring center `(0, 0, 0)` so both upward and downward bars are equally visible.

#### Key constants

| Constant | Value | Notes |
|----------|-------|-------|
| Display target | 720×1280 | Pi Touch Display 2, portrait orientation |
| `NUM_BANDS` | 48 | Per side |
| `DISC_RADIUS` | 3.15 | Ring radius |
| `MAX_BAR_HEIGHT` | 4.2 | Maximum bar extension |
| Left arc | 0.62π – 1.38π | ~137° arc for missing frequencies |
| Right arc | -0.38π – 0.38π | ~137° arc for augmented frequencies |

---

### 6. 3D Waterfall Spectrum ✅ COMMITTED

**Reference:** `WaterfallSpectrum3D.jsx`, `waterfall_demo.jsx`  
**Screen:** Dedicated live view (Pi 5 + Touch Display 2, 720×1280 portrait)  
**Data source:** Live `fft_source[512]` or `fft_return[512]` from data_sender live frame packets  
**Update rate:** ~10.8 Hz data, interpolated to 60 FPS rendering

#### Description

A live 3D scrolling landscape where frequency, time, and amplitude map to the X, Y, and Z axes. New spectrum data arrives at the front edge and the entire terrain scrolls backward into depth — the user always sees the present moment closest to them with history receding behind. This is a pure live visualization, not a comparison tool.

#### Axes

| Axis | Dimension | Mapping |
|------|-----------|---------|
| X | Frequency | Log scale, 20 Hz (left) → 20 kHz (right), 96 bins |
| Z | Time | Newest at front, scrolling backward, 80 time slices |
| Y | Amplitude | Height — louder frequencies rise into peaks |

#### Color mapping (thermal palette)

Height and color are redundant cues — both represent amplitude:

| Amplitude | Color | Description |
|-----------|-------|-------------|
| 0–15% | Deep blue/black | Silence / noise floor |
| 15–35% | Blue → cyan | Low-level signal |
| 35–55% | Cyan → green | Moderate signal |
| 55–72% | Green → yellow | Strong signal |
| 72–88% | Yellow → orange/red | Hot / loud |
| 88–100% | Red → white-hot | Peak / clipping territory |

The color legend strip is rendered on the 2D overlay at the top left for reference.

#### Mesh implementation

A single `PlaneGeometry` with `(FREQ_BINS - 1) × (TIME_SLICES - 1)` subdivisions, rotated to lie flat on the XZ plane. Each frame:
1. All rows shift back by one position (`Float32Array.copyWithin`)
2. The newest spectrum is written to row 0 (front edge)
3. Vertex Y positions and vertex colors update from the history buffer
4. Vertex normals are recomputed for lighting

This is a single mesh, single draw call, single material — highly efficient for embedded GPU. No geometry allocation per frame.

#### Reference line

- Cyan vertical cylinder at the front edge of the waterfall
- Tracks the frequency position closest to the camera's viewing angle
- Cyan dot at the base on the front edge
- 2D overlay shows frequency in cyan with glow, amplitude in thermal-palette color

#### Interaction

- Full 360° orbit with drag/touch
- Slow auto-rotation when not being touched
- Pause/resume button
- View from above = traditional 2D waterfall (color map). View from side = mountain range silhouette. View from low angle = dramatic landscape.

#### Key constants

| Constant | Value | Notes |
|----------|-------|-------|
| Display target | 720×1280 | Pi Touch Display 2, portrait orientation |
| `FREQ_BINS` | 96 | Frequency resolution |
| `TIME_SLICES` | 80 | History depth (~7.4 seconds at 10.8 Hz) |
| `PLANE_WIDTH` | 8 | 3D units |
| `PLANE_DEPTH` | 10 | 3D units |
| `MAX_HEIGHT` | 3.0 | Peak amplitude height |
| Vertex count | 96 × 80 = 7,680 | Single mesh, manageable for Pi GPU |

#### Data contract

Accepts an array of amplitude values (0.0–1.0), one per frequency bin. The component handles resampling from any input bin count to its internal 96 bins. Data arrives via `getLiveData` prop or the data_sender UART protocol.

#### Pi optimization features

- Single mesh, single draw call (no InstancedMesh needed — PlaneGeometry is already one object)
- `Float32Array.copyWithin` for zero-allocation row shifting
- Vertex buffer updates only — no geometry creation per frame
- Frame interpolation via `lerp` at 0.22 smoothing
- Pixel ratio capped at 1

---

## PROPOSED VISUALS (not yet committed — exploring)

These are candidates for future implementation. Each has a practical version and an eye-candy version.

---

### 7. Circular Arc Meters (eye candy alternative to bar meters)

180° or 270° arc gauges with glowing needles. Source and return as facing arcs creating a symmetric butterfly shape. Pulsing ring at signal presence.

**Status:** Exploring — needs mockup to evaluate readability vs. bars.

---

### 8. Heat Ribbon TF Curve (eye candy alternative to split-fill)

TF curve where the line color shifts with magnitude: blue for cuts → white at 0 dB → warm orange/red for boosts. Fill uses the same color mapping. Thermal camera effect.

**Status:** Exploring — could be powerful but may be confusing if color also means something else on screen.

---

### 9. Atmospheric Fog (confidence indicator)

When signal confidence is low, the TF panel background gradually brightens/hazes like fog rolling in. As signal returns, fog clears. No text needed — visceral and intuitive.

**Status:** Exploring — elegant concept, needs bench testing to evaluate whether it reads clearly.

---

### 10. Signal Flow Diagram (route/injection status)

Tiny animated dot traveling along a path showing current signal flow: guitar → analyzer → rig → return. Path changes when injection is active. Like a simplified animated circuit.

**Status:** Exploring — would be beautiful but complex to implement on RA8875.

---

### 11. Frequency Coverage Map (valid bin visualization)

Thin horizontal strip showing which frequency regions had valid data (lit) vs gaps (dark) in the result view. Binary heatmap of measurement coverage.

**Status:** Exploring — lightweight and informative, good candidate for result view header.

---

### 12. Shattered Curve (abort visualization)

On abort, the TF graph shows a fragmented version of partial data with pieces drifting apart. Communicates "this measurement broke" visually.

**Status:** Exploring — strong concept, implementation complexity may not justify the rare occurrence.

---

### 13. Circular Oscilloscope (pure eye candy)

Time-domain waveform wrapped around a circle like a Lissajous pattern. Shape morphs fluidly as the guitar signal changes. Purely mesmerizing to watch.

**Status:** Exploring — would require raw sample access in the display loop, which is architecturally possible but not currently wired.

---

### 14. Phase Response Overlay

Cyan ribbon overlaid on TF magnitude showing the system's phase response. Dual-axis display (dB left, radians right).

**Status:** Exploring — data exists in result (`tf_cal_phase_rad[512]`), not yet displayed. Primarily useful for advanced users.

---

### 15. Group Delay Visualization

Group delay in ms vs frequency, rendered as a depth layer behind the TF curve creating a pseudo-3D terrain effect.

**Status:** Exploring — data exists (`group_delay_ms[512]`). Could be a powerful diagnostic view for latency analysis.

---

### 16. Baseline Comparison Overlay

Current result vs saved baseline — two TF curves overlaid. Current in full amber, baseline as a dimmer ghosted trace. Difference visible instantly.

**Status:** Exploring — high user value for A/B comparisons. Requires loading baseline CSV at display time.

---

## SCREEN MAP

| Screen | Primary visual | Secondary visuals | Entry condition |
|--------|---------------|-------------------|-----------------|
| **Live** | Spectrum + TF panels (or 2D Radial Fingerprint) | Meters, jack status, monitor mode | Default / idle |
| **Result** | TF result curve (large) | Quality badge, insight panel, provenance | RESULT_READY event |
| **Aborted** | Abort reason text | (future: shattered curve) | ABORTED event |
| **Radial 2D** | 2D Radial Tone Fingerprint (full screen) | Frequency labels, legend | User toggle or dedicated mode |
| **Radial 3D** | 3D Radial Tone Fingerprint (full screen) | Cyan reference line, frequency readout | Pi display |
| **Split 3D** | Split Tone Fingerprint (left=missing, right=augmented) | Cyan reference, dB readout | Pi display |
| **Waterfall 3D** | 3D Waterfall Spectrum (scrolling landscape) | Cyan reference, amplitude readout, color legend | Pi display |

### View switching model

The visualizations span two deployment targets:

**RA8875 device display (800×480):**
1. **Standard live view** — meters + spectrum + TF (practical, detailed)
2. **2D Radial Tone Fingerprint** (Section 1) — full-screen radial display

Toggle via Serial command ('F') or future touch gesture. Both consume the same live data.

**Pi 5 display (720×1280 portrait, via data_sender UART):**
The Pi renderer can switch between multiple 3D views:
1. **3D Radial Tone Fingerprint** (Section 1b) — mirrored radial, full orbit
2. **Split Tone Fingerprint** (Section 1c) — left=missing, right=augmented
3. **3D Waterfall Spectrum** (Section 6) — live scrolling frequency×time landscape

All three consume the same live frame data from the Teensy. View switching is handled on the Pi side — the Teensy sends the same packets regardless of which visualization is active.

**Both targets:**
Result view and aborted view are separate screens entered by measurement events. The Pi receives RESULT and ABORTED packet types and switches to the appropriate display.

---

## IMPLEMENTATION PRIORITY

| Priority | Visual | Why |
|----------|--------|-----|
| 1 | Standard live view (spectrum + TF + meters) | Core instrument functionality |
| 2 | Result view (TF curve + quality + insights) | Measurement output |
| 3 | 2D Radial Tone Fingerprint | Pedalboard-worthy eye candy, committed, RA8875 target |
| 4 | 3D Radial Tone Fingerprint | Pi display, committed |
| 5 | Split Tone Fingerprint (3D) | Pi display, committed — missing vs augmented split |
| 6 | 3D Waterfall Spectrum | Pi display, committed — live scrolling landscape |
| 7 | Peak-hold meter decay | Already has constant, needs implementation |
| 8 | Baseline comparison overlay | High user value for A/B testing |
| 9 | Frequency coverage map | Lightweight result view enhancement |
| 10–16 | Remaining proposed visuals | Evaluate after bench testing |

---

## RA8875 HARDWARE CONSTRAINTS

| Capability | Available | Notes |
|-----------|-----------|-------|
| Resolution | 800×480 | Fixed |
| Color depth | 16-bit RGB565 | 65,536 colors |
| Hardware accelerated | Filled rect, line, circle, triangle | Fast primitives |
| Text rendering | Built-in ROM font | Limited sizes, no anti-aliasing |
| Alpha blending | Not available | Simulate with layered drawing |
| Anti-aliasing | Not available | Use thicker lines, glow layers |
| SPI clock | Up to 20 MHz | Shared with SD card |
| Touch | Resistive, interrupt-driven | Future — not used in v0.6 |
| Frame rate target | 10–15 fps for animation | Breathing/pulse effects |
| Partial update | Yes — only redraw changed regions | Critical for performance |

### Performance strategy

- Static elements (grid, labels, axis) drawn once on screen entry
- Dynamic elements (curves, meters, segments) redrawn per frame
- Use `fillRect()` to erase previous curve position before drawing new
- Radial fingerprint: ~288 line draws per frame at ~11 fps = ~3,168 line/sec
- Standard spectrum: ~740 vertical line draws per frame (column fill)
- Both are within RA8875 SPI throughput budget at 20 MHz
