# DRAFT — not spliced, not committed

**Intended destination:** `ai/journal.md`.
**⚠️ PLACEMENT: NOT at the top of the file.** The journal's newest-first rule puts
this entry **below** the three 2026-10-08 entries and **above** 2026-09-30. Pasting
it at the top would put 2026-10-05 above 2026-10-08 and break the ordering.

**Reviewer's note on what this entry deliberately does not do:** it does not mark
the J4 tip connection repaired, and it does not close the volume/noise
investigation. Both are stated as open inside the entry.

---

## 2026-10-05 (1) — **A diagnostic jumper left fitted for 23 days was shorting the guitar input to ground, and removing it opened the J4 tip conductor.** Neither the fault nor the repair attempt reached the record until this entry, and the original symptom is still unexplained

**Nothing in this entry was written down at the time.** The session ran on
2026-10-05; the next journal entries are 2026-10-08 (1)–(3) on the Amp Out
buffer, which do not mention it. This entry is reconstructed from the bench
dialogue three days later. **Treat every number in it as transcribed, not
captured** — the same caution Part II of `docs/asbuilt/netlist.md` carries.

### The caveat first, because the headline is incomplete

The confirmed short explains **silence**. It does **not** explain the symptom that
started the session — *"terrible drop in volume"*, which implies audible guitar.
A dead short to ground does not attenuate; it mutes. **The original report is
still unexplained, and this entry does not close the volume investigation.**
See "What this does not establish" below.

### What was reported — `OBS` / `RPT`, builder-reported by ear

| Stage | Report |
|---|---|
| Opening symptom | severe volume loss **and** broadband noise, guitar → J4 → J5 → Headrush, versus the same guitar direct into the Headrush |
| Listening test — guitar volume at maximum, Headrush on a clean low-gain patch, above the 12th fret then open low E | *"nothing except occasional constant screeching from different pedals"* |
| Does the hiss scale with patch gain? | *"constant"* |
| Headrush input used | instrument input, and the same jack the guitar had been in directly |
| After jumper removal | no guitar; fuzz unchanged |

**The level progression — weak, then absent — is itself a data point**, and it is
part of why the original symptom is not accounted for.

### MEASURED — `MEAS`, DMM, power off except where noted

**Before removing the jumper:**

| Measurement | Reading |
|---|---|
| `col 30` → GND jumper, visual | **present** (`PHYS/OBS`) |
| J4 **sleeve** → breadboard GND rail | **0.2 Ω** |
| J4 **tip** → GND | **1.2 Ω** |
| J5 **sleeve** → breadboard GND rail | **0.2 Ω** |

**After removing the jumper:**

| Measurement | Expected | Reading |
|---|---|---|
| J4 tip → GND | OL | **OL** |
| **J4 tip lug → col 30** | ~0 Ω | **OL** 🔴 |
| col 33 → col 37 (the `33d`→`37d` jumper) | ~0 Ω | **6 Ω** |
| col 37 → col 41 (R5 into OPA_BIAS) | 73–108 kΩ | **100.7, unit not confirmed** |
| col 48 → J5 tip (K1 NC, de-energised) | ~0 Ω | **203.7, unit not confirmed** |
| col 30 → col 33 | OL | **OL** — expected, C1 blocks DC |
| col 35 → col 48 | OL | **50.5 MΩ** — C2 leakage, healthy |

**Two readings are recorded with their units unconfirmed and must not be cited as
either.** `100.7` and `203.7` were reported without a magnitude prefix. They are
left ambiguous here rather than silently promoted to the value that makes sense,
because that promotion is precisely the class of error the C1 / `BC103` finding
(netlist A1) was about.

### NOT MEASURED, and recorded as such

**U1 pin 1 → GND, powered.** Reported back as `0.874` V. **Provenance
unresolved.** `0.874 V` is the exact figure already in the record from journal
2026-09-05 (5), and when asked whether this was a live reading or a quotation of
that entry, no answer was given. **It is therefore not evidence about the board's
state on 2026-10-05** and is excluded from the measured table above. Tier: none.

### INFERRED — `DERIV`, computed from the measurements above

1. **The 1.2 Ω tip → GND was the jumper, not the guitar.** It decomposes as
   ≈1.0 Ω of tip-wire contact plus the 0.2 Ω jumper path, matching the sleeve's
   own 0.2 Ω. A pickup reads **6–15 kΩ** DC, four orders of magnitude away, so no
   state of the instrument or its volume pot can produce 1.2 Ω.
2. **Attenuation while shorted ≈ −74 dB.** A ~6 kΩ pickup source into a 1.2 Ω
   load gives 1.2 / 6001 ≈ 2 × 10⁻⁴. C1 sits in parallel with the short and was
   therefore fed ≈0.02 % of the instrument.
3. **The J4 tip conductor was intact before the removal and open after it.**
   The only conductor on that lug runs to col 30, so the 1.2 Ω path had to pass
   through col 30 and the jumper — which requires the tip wire to have been
   connected at ≈1 Ω. It now reads OL. **This is an inference from two readings,
   not an observation of the wire being pulled.** Nobody saw it come out.
4. **The 6 Ω at col 33 → col 37 is electrically immaterial** — 6 Ω feeding a
   ~100 kΩ node is ≈ −0.0005 dB — **but it is ~30× this board's 0.2 Ω norm**, so
   it is logged as a marginal-contact watch item, not as a pass.

### 🔺 A record contradiction this surfaced, and it is a documentation defect

`docs/asbuilt/netlist.md` **§14** records, as bench-proven with a real signal on
2026-09-19: *guitar → J4 → buffer → SOURCE_NODE → J5 → external TS cable → J6 →
K2 NC → COM → LINE IN R*, **SOURCE −10.1 / RETURN −10.2 dBFS**.

**That result is impossible with col 30 shorted to ground.** Yet TODO-40 asserts
the jumper has been fitted continuously since 2026-09-12. Both cannot be true, so
**the jumper was removed and re-fitted at least once between 2026-09-12 and
2026-10-05, and neither event was recorded.** `netlist.md` §10.0, which exists to
track exactly this kind of post-freeze change to Part I, does not carry it either.

This is a defect in the record, not in the circuit. It is also the second
unrecorded-bench-state problem on this board, and it is the reason the TODO-40
pooled baseline cannot presently be attached to any known configuration.

### What was decided, and why the TODO-6 hold did not apply

TODO-6 carries **⛔ "Do not restore deviations independently of this item"** on
this jumper, because it supplied the DC path a SHUNT → pin 16 detect experiment
would have needed. That reasoning is superseded **by TODO-6's own content**:

- **2026-09-13 (9)** established J4 has **no SHUNT contact** — lug #2 and the long
  spring are one TIP net — and formally withdrew the experiment as unperformable.
- **2026-09-13 (10)** decided detect moves to an independent Omron D2F-01L, with
  *"do not sense their TIP nodes"* stated explicitly.
- TODO-6 itself marks the boundary: *"Everything below this line predates the
  continuity identification… the SHUNT topology reasoning does not describe the
  installed jack."* **Both the ⛔ hold and the 🧪 prediction sit below that line.**

So the jumper was load-bearing for a feature since decided never to use that node.
TODO-6 also already said of it: *"It shorts the guitar signal to ground. The
jumper works for detect by accident."* Removal was correct and cost nothing.

### What this does NOT establish — read before citing this entry

- 🔴 **That the J4 tip connection is repaired.** It was identified, not fixed.
  **No measurement was taken after the fault was found.** Last recorded state is
  `J4 tip lug → col 30 = OL`. Any subsequent SOURCE or RETURN reading may have
  been taken with the instrument input physically disconnected.
- 🔴 **That the volume/noise investigation is closed.** The short explains
  silence. The reported *volume drop with audible guitar* is unexplained.
  Candidates, none tested: an intermittent short; a degrading tip contact passing
  through a high-resistance phase before opening; or the audible content having
  been the noise floor all along, misattributed. **Not resolvable from the record.**
- 🔴 **That TODO-19, TODO-23, TODO-21 or TODO-40 contributed to what was heard.**
  All four remain real and unfixed, and all four were masked by the short. They
  were initially offered as the leading explanation and that was wrong — a
  confirmed wiring fault outranked four documented design limitations. **Worth
  keeping: the open items were the most interesting hypothesis and the cheapest
  check was the correct one.**
- 🔴 **Hypothesis 5 — the Rig Send ground reference.** J5's sleeve returns to
  Audio Shield GND (§12.3) while the signal on col 48 is generated against the
  breadboard rail, so the ground-potential difference TODO-40 measured as a
  **33.1 dB** effect on LINE-IN-L sits in series with the audio at the Headrush
  input. TODO-40 has only ever examined that topology on a codec **input**, never
  on an **output** feeding an external amplifier. **Raised, never tested.**
- 🔴 **The two unit-ambiguous readings**, and the `0.874 V` provenance.

### Promotions this session earned — proposed, for `netlist.md` §12.3

Named explicitly, because promotion requires saying what the new evidence was.

| Row | Was | Now proposed | Evidence |
|---|---|---|---|
| **J4 sleeve → GND** | `RPT`, no figure | **`MEAS` 0.2 Ω** | this session |
| **J5 sleeve → GND** | `MEAS`, no figure | **`MEAS` 0.2 Ω** | this session |

The J4 row also closes **step 3 of TODO-6's own next-bench-sequence** — *"Verify
whether SLEEVE is actually connected to system GND"* — open since 2026-09-13.
Not applied here; `netlist.md` is already modified on this branch.

### What the next session should know

1. **Measure `J4 tip lug → col 30` before anything else.** It is the leading
   hardware suspect on this board and its last recorded value is OL.
2. The front end's own open items are untouched and still predict a thin, hissing
   guitar once signal is restored: TODO-19 (~145–160 Hz corner, low E at −6 dB),
   TODO-23 (~100 kΩ input impedance), TODO-40 (~40 mV_pp floor at col 48),
   TODO-21 (~0.5 V downward headroom, clipping points never measured).
   **−10.1 dBFS at SOURCE on a strum is the figure to compare against.**
3. R5's in-circuit reading is new input to **TODO-32** and does not close it.
4. **Method note.** Three of the four hypotheses carried into this session were
   documented design limitations, and the actual cause was a diagnostic left
   fitted. The record said it was fitted, in four places, and it was read as
   historical rather than current. **A bench-state deviation with no recorded
   removal is a live condition, not a footnote.**
