# Visual references — and what each one is allowed to mean

**Imported 2026-10-12** from the October design package
(`~/Desktop/guitar_rig_analyzer/Guitar_Rig_Analyzer_UI/references/`). Nineteen
unique images, byte-for-byte copies.

> `IMG_2057(1).jpeg` was **not** imported: it is byte-identical to `IMG_2057.jpeg`
> (both SHA-256 `2a040362bf15a2f866e18e4b7bbd0f2ed712149b6c5bdef8143dd90d0ce1a09b`).

The package's own README states the rule these are imported under:

> *"Images are visual inspiration, not proven existing hardware capabilities. The
> repository's current HEAD and physically validated measurements remain
> authoritative."*

The October brief §5 repeats it: *"The photographs featuring impedance, cable
capacitance and imaginary scores are design inspiration only, not claims about
finished firmware."*

**They are imported anyway, and six of them are imported precisely because they are
wrong.** ADR-005's *governing invariant* uses them as its worked counter-example
but does not contain them; until now the ADR named pictures that lived outside
version control. Now the ADR's example is checkable.

---

## A — Product renders of the device (6)

AI-generated renders of a pedal-format analyzer. **Read the screens, not the
enclosure.**

| File | On screen | Standing |
|---|---|---|
| `A67BC769-1890-4053-AC87-6E2E0693499D.jpeg` | **"3D Radial Tone Fingerprint"** — ring of bars, cool green/blue left, warm orange/red right, cyan reference line, `1.25 kHz ▾ reference` readout | ✅ **The direct visual ancestor of what is built.** [`fingerprint_split.js`](../../../pi/web/static/fingerprint_split.js) is this picture, and the missing reference line and readout are tracked in [`../concepts/README.md`](../concepts/README.md) |
| `F064CBC2-D007-4289-B20D-98D330814DB0.jpeg` | `LIVE` bar spectrum + `−6.3 dB`; `RIG CHANGE` ±dB curve; `CORRECTION` curve, `HF loss: −2.2 dB` | 🟡 **Mixed.** The top two panels map to real wire fields and are a fair reference for the LIVE tab. **`CORRECTION: +6 kHz +3 dB` is advice the firmware does not author** — and the instrument cannot apply an EQ change to an external rig in any case |
| `562275E6-02AF-46BA-857A-D56C974FE604.jpeg` | 6-tile `MENU`: Cable Test · Impedance Profile · Noise Analysis · Reference Capture · Rig Fingerprint · Latency Map, plus Buffer Advisor / Calibration / Settings | 🔴 **Not buildable as drawn.** Five of the nine destinations have no measurement behind them, and **every tile implies a command the Pi cannot send** ([`../README.md`](../README.md) §3.4). Useful only as evidence of the destination count that was reduced to four |
| `68E5D0BD-F6CC-472E-8CAD-1FECA3EBB3C2.jpeg` | `Treble Loss: −2.8 dB` · `Mid Boost: +1.4 dB @ 800 Hz` · `Recommendation: Add input buffer` · `RIG MATCH: 89%` | 🔴 **Quoted by name in ADR-005.** *"Rendering them is fine. Computing them on the Pi is not."* The first two resemble real `insights[]` entries; the last two are fabricated |
| `87704B1E-9BED-4318-8435-CAB6F55E41A2.jpeg` | `BUFFER PLACEMENT ADVISOR` · `Cable Length: 22 ft` · `Capacitance: 565 pF` · `Evaluation: MEDIUM` · `Rig Health: 90%` | 🔴 Same. No sensor exists for any number on this screen |
| `E191AFC0-C8C6-4702-BAFC-A43B0769D3D1.jpeg` | `Resistance: 0.8 Ω` · `Capacitance: 540 pF (27 ft)` · impedance curve vs Ω · `HUM −53 dB` / `HISS −92 dB` · `RIG HEALTH: 91%` | 🔴 Same |

---

## B — Real measurement software (5)

Screen captures of working analyzers. **These are the only images here that show an
honest instrument**, and they are the most useful references in the set.

| File | What it is | Worth taking |
|---|---|---|
| `IMG_2195.jpeg` | An SDR "Waterfall 3D": thermal-mapped frequency × time surface, **labelled axes in MHz and µs, and a dBm colour key down the right edge** | The colour key. A thermal ramp without a legend is decoration; with one it is data. v1.2 §6 specifies the ramp and the legend strip |
| `IMG_2193.jpeg` | "Spectrum Analyser" — 3D peak surface, blue→red by height | Height and colour as **redundant** cues for one quantity |
| `IMG_2197.jpeg` | "Spectrum3D" — point-cloud spectrum with a **labelled frequency axis (0–6000)** | Axis labelling survives into 3D |
| `IMG_2194.jpeg` | Wireframe contour terrain, rainbow by depth | The contour-river aesthetic the brief §7.2 asks about, in its honest form. *(Window title is a joke from the source video; ignore it.)* |
| `IMG_2057.jpeg` | A classic RTA: log-frequency bars, **peak-hold segments**, and a cursor readout — `Freq: 250.00 Hz  Level: 82.46 dB` | **The closest reference to the LIVE tab.** Peak-hold and a numeric cursor readout are both specified (v1.2 §4) and both unbuilt |

---

## C — Dark dashboard styling (4)

`IMG_2090` · `IMG_2091` · `IMG_2092` · `IMG_2093`

Stock SaaS analytics UI: gradient area fills, rounded panels, soft glow, muted
grid lines, generous label spacing. **Styling only — no instrument content.** Take
the surface treatment and the restraint of the grid; the October brief §5 is
explicit that the result must not read as *"a generic SaaS sales dashboard"*, and
`IMG_2093`'s KPI-tile grid is the thing to avoid.

---

## D — Abstract data art (2)

`IMG_2130` · `IMG_2131`

Stock "big data" illustrations — fanned coloured lines resolving into particle
fields. Mood and palette only. Nothing here encodes a quantity.

---

## E — Music-visualizer tunnels (2)

`IMG_2280` · `IMG_2281`

Phone screenshots of a YouTube Short (Aloboi, *Give Me More*): purple and cyan line
tunnels reacting to music.

🔺 **This is the ancestry of `VortexTunnel.jsx`**, which ADR-005 §9 excludes from
production because it acquires its own audio through `getUserMedia` — a second
measurement path outside the Teensy authority boundary. **The aesthetic is not the
problem; the input path is.** A tunnel driven by `fft_return[]` with an honest axis
would be a legitimate proposal. A tunnel driven by the Pi's microphone is the
instrument visualising the room while implying it is visualising the rig.

---

## Using these

1. **Group B first.** It is the only group showing measurements that exist.
2. **Group A's one good screen is `A67BC769`**, and it is already built.
3. **Group C for surface treatment**, not for layout.
4. **Nothing in group A's remaining five screens may be reproduced**, including as
   a "coming soon" placeholder. Under ADR-005 the correct display of a judgement no
   wire field carries is its absence.
