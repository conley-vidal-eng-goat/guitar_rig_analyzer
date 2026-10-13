# Concept mockups — roster and standing

**Imported 2026-10-12** from `~/Downloads`, where they had sat outside version
control since being located on 2026-09-30. All seven are **byte-for-byte copies**
of the originals; the originals are unmodified and still in place.

These are **React/JSX mockups written for an artifact sandbox**. They are not
buildable in this repository and are not meant to be — there is no React, no
bundler and no `node_modules` here, by decision (see
[`../README.md`](../README.md) §3.5). They are reference implementations: read
them for geometry, constants, colour ramps and performance technique, then port
what is needed into `pi/web/static/` as plain ES modules.

**None of them is a data contract.** Every one generates its own demo data. The
authoritative contract is `pi/analyzer_link/presentation_semantics.py` and the
payload in `pi/web/payload.py`, and a port must consume that instead.

---

## Imported

| File | v1.2 section | Status | Target | Already ported? |
|---|---|---|---|---|
| `ToneFingerprintSplit.jsx` | §1c Split Tone Fingerprint (3D) | ✅ committed | Pi 720×1280 | **Yes** → [`pi/web/static/fingerprint_split.js`](../../../pi/web/static/fingerprint_split.js) |
| `WaterfallSpectrum3D.jsx` | §6 3D Waterfall Spectrum | ✅ committed | Pi 720×1280 | No |
| `waterfall_demo.jsx` | §6, second reference | ✅ committed | Pi | No |
| `radial_tone_3d.jsx` | §1b 3D Radial Tone Fingerprint | ✅ committed | GPU display | No — superseded in practice by §1c |
| `radial_tone_fingerprint.jsx` | §1 Radial Tone Fingerprint (2D) | ✅ committed | **RA8875 800×480 — demoted** | No. Useful as the 2D fallback for TONE |
| `display_concept_v2.jsx` | §2 live spectrum, §3 TF split-fill, §4 level meters, §5 result view | ✅ committed | **RA8875 800×480 — demoted** | No. **The main source for the LIVE and LAB tabs** |
| `ToneFingerprintSurface.jsx` | *none* | 🟡 **candidate, not committed** | 720×1280, 64 bands | No — and must not be built yet |

### On `ToneFingerprintSurface.jsx`

ADR-005 §9 classifies it as an **undocumented variant**: Teensy-shaped data, no
second input path, but no section in the specification of record. *"If it is wanted
in production it gets a design-document section first, so the specification keeps
leading the implementation. Until then it is not built."* It is imported so the
candidate is inspectable, not so it can be wired up.

🔺 It is also a **continuous surface**, which is the exact hazard ADR-005
*Rationale* §4 names: *"A continuous mesh surface over the band ring interpolates
across missing bands by default; that is what a surface is. Under the real RESULT
that renders 508 undefined locations as smooth terrain."* Any future port needs an
explicit answer for how the surface breaks at an UNMEASURED band before it draws a
single triangle.

---

## 🛑 Not imported

| File | SHA-256 | Why not |
|---|---|---|
| `VortexTunnel.jsx` | `9668b26d3a5c4d4aeb10e36f6624f70c67e7f7df83472d557ebf401f827bb242` | **Boundary violation.** It acquires audio itself: `navigator.mediaDevices.getUserMedia({audio: true})` into an `AudioContext` analyser at `fftSize = 256` (lines 49–56). That is a **second measurement path outside the Teensy authority boundary** — the instrument would be visualising the room, not the rig, with nothing on screen to say which. ADR-005 §9 excludes it from production. `pi/tests/test_web_payload.py` CI-enforces the absence of eight acquisition identifiers from client code, with comments stripped so a mention in prose cannot mask a call. **Importing it would put a `getUserMedia` call in the repository for no gain.** It remains in `~/Downloads` as a retained visual experiment, per ADR-005. |
| `display_concept.jsx` | `65bf72397583fbe00916048ae1012d653d760791e0c267f7203174015a915e8d` | Superseded v1 of `display_concept_v2.jsx` — same 800×480 target, not referenced by any section of the specification of record. No content that v2 lacks. Available in `~/Downloads` if wanted; say so and it is a one-line follow-up. |

The two images that inspired `VortexTunnel.jsx` **are** imported, as
[`../references/IMG_2280.jpeg`](../references/IMG_2280.jpeg) and
[`IMG_2281.jpeg`](../references/IMG_2281.jpeg). The aesthetic is not the problem;
the acquisition path is.

---

## What the shipping port changed, and what it still lacks

[`pi/web/static/fingerprint_split.js`](../../../pi/web/static/fingerprint_split.js)
is a port of `ToneFingerprintSplit.jsx` to a plain ES module. The geometry, arcs,
colours, `InstancedMesh` batching and camera behaviour follow the original.

**Deliberate divergences — do not "restore" these from the JSX:**

| Original | Port | Why |
|---|---|---|
| Receives raw band values | Receives **already-classified** bands with no coverage nibbles, no NaNs, no raw arrays | It cannot classify even by accident (ADR-005 §4) |
| Draws a `0.02` stub on the inactive side | Draws **nothing** for UNMEASURED | The stub was fine for synthetic data where every band had a value. Here it would assert a measurement |
| Eases every frame | Eases only while a band stays MEASURED; a class change snaps | A band must never animate *through* a magnitude it never had |
| `CAMERA_DISTANCE = 10.5` fixed | Distance fitted to the **narrow** axis | On 720×1280 portrait the narrow axis is horizontal; a landscape-tuned distance crops the ring |

**Present in the JSX and/or the §1c spec, absent from the port — candidates for the
TONE tab:**

- Cyan reference line tracking the nearest band to the camera (`REF_LINE_*`,
  lines 46–47, 208–213, 337)
- 2D overlay readout: title, frequency and dB for the tracked band (lines 137–157,
  340–357)
- Pulsing baseline ring — the "heartbeat" the specification gives all three
  fingerprint variants
- Pause/resume orbit control (specified in v1.2 §1c *Interaction*)

🔺 The readout is the one to think hardest about. It must print **only** what the
payload carries: a band with `value: null` has a frequency and a class but **no
dB**, and the readout has to say so rather than print `0.0 dB` or fall back to a
neighbour.
