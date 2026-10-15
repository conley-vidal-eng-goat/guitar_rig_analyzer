# Amp Out buffer — as-built, DC-validated checkpoint

**Status: BUILT + DC-VALIDATED. NOT signal-validated. NOT a completed feature.**
No audio has passed through this branch and no amplifier has been connected.

**Bench sessions:** built and first DC pass **2026-09-30**; adapter reseated and
DC pass re-taken **2026-10-08** (Action 72). Both are recorded below, including
the superseded numbers.

**Journal:** 2026-10-08 (1) · **Tracking item:** TODO-69

**Tier legend** (as `docs/asbuilt/netlist.md`): `PHYS` observed · `MEAS` measured ·
`DERIV` computed from a measurement · `RPT` builder-reported, unconfirmed ·
`INF` inferred from documentation · `NYV` not yet verified.

Designators below (`U4`, `J8`, `C9`–`C11`, `R10`) are **proposed, not ratified** —
see the journal entry. They are used here for readability only and carry no
authority until `netlist.md` gains a Part III.

---

## 1. PHYS — what was physically built

Builder-reported at the bench. Column-and-trench-side is the load-bearing claim;
row letters are `RPT`. **Terminology converted to the netlist's convention:** the
numbered positions are *columns*; `A–E` and `F–J` are the *rows*, separated by the
centre trench.

| # | Item | Placement | Tier |
|---|---|---|---|
| 1 | Spare **OPA1642AID** on a Proto-Advantage **PA0001** adapter | cols **24–27**, straddling the centre trench, pin-1/notch end toward col 24 | `PHYS` placement · part identity `RPT` |
| 2 | Supply feed | pin 8 → existing **+5 V** | `PHYS` |
| 3 | Ground | pin 4 → existing **GND** | `PHYS` |
| 4 | **C9** 0.1 µF ceramic, supply decoupling | pin 8 (col 24 F–J) → col **23 F–J**; col 23 F–J jumpered to GND | `PHYS` placement · value `RPT` |
| 5 | Unity-gain feedback, channel A | pin 1 → pin 2 | `PHYS` |
| 6 | **R10** 100 kΩ input bias | pin 3 → an intermediate node → **OPA_BIAS** | placement `PHYS` · **node identity `RPT`+`DERIV`, see §3** |
| 7 | Channel B, deliberately terminated | pin 5 → *reported* "VGND" · pin 7 → pin 6 | `PHYS` placement · **node identity `NYV`, see §4** |
| 8 | RETURN_NODE branch | `16a` (K2 pole 1 COM) → col **23 A–E** | `PHYS` |
| 9 | **C10** 0.1 µF input coupling | col 23 A–E → pin 3 | `PHYS` placement · value `RPT` |
| 10 | **C11** 10 µF electrolytic output coupling | **(+)** → pin 1 · **(−)** → col **21 A–E** | `PHYS` |
| 11 | **J8** fourth 1/4" jack — "Amp Out" | TIP → col 21 A–E · SLEEVE → existing GND rail | `PHYS` |

**Not disturbed:** the existing `16a` → Audio Shield **LINE IN R** conductor was
left in place. This is a branch on RETURN_NODE, not a re-route of it.

**Trench adjacency, called out because it is easy to get wrong:** col 23 **F–J**
(the C9 decoupling/GND node) and col 23 **A–E** (the RETURN_NODE branch and C10's
input side) are **electrically separate nodes**. Confusing them builds a different
circuit — it would short the selected return to ground.

### Topology as built

```
16a (K2 pole 1 COM) = selected RETURN_NODE
  ├──────────────────────────────→ U3 LINE IN R      (pre-existing, untouched)
  └── col 23 A–E ── C10 0.1 µF ──→ U4 pin 3 (+in A)
                                     │
                       R10 100 kΩ ───┴──→ OPA_BIAS (cols 41/43, ~0.877 V)

  U4 pin 1 (out A) ── pin 2 (−in A)                  unity-gain follower
  U4 pin 1 ── C11 10 µF (+ on pin 1) ── col 21 A–E ──→ J8 Amp Out TIP
                                        J8 SLEEVE ───→ GND
```

---

## 2. MEAS — what was actually measured

### 2026-10-08, after reseating the adapter — current record

| Node | Reading | Condition |
|---|---|---|
| U4 pin 1 (out A) | **0.876 V** | stable |
| U4 pin 2 (−in A) | **0.876 V** | stable |
| U4 pin 3 (+in A) | **0.876 V** | stable |

All three equal and stable is the signature of a closed-loop unity follower whose
input sits at **0.876 V**.

### 2026-09-30, before reseating — SUPERSEDED, retained as the record of the fault

| Node | Reading | Status |
|---|---|---|
| U4 pin 8 | **4.96 V** | supply present |
| U4 pin 4 | **0.1 mV** rel. GND | ground present |
| U4 pin 3 | **2.571 V** | ⛔ **superseded** — intermittent contact |
| U4 pin 1 | **2.569 V** | ⛔ **superseded** — intermittent contact |
| J8 TIP → SLEEVE, DC | **1.5 mV** | taken after C11 and J8 were fitted, unloaded |

Remaining pins were reported checked and "behaving normally" on both passes —
**no numbers were recorded, so that is `RPT` and is not evidence of a value.**

### Reference values this is measured against (prior record, not re-taken)

| Node | Value | Source |
|---|---|---|
| **OPA_BIAS**, cols 41 A–E ∪ 43 A–E | **0.874 V** `MEAS` / 0.877 V calculated | journal 2026-09-05 (5) |
| **VGND**, `BOT_RED` / col 45 A–E | **2.495 V** `MEAS` | journal 2026-09-16 |
| U1 pin 3 droop, pre-rebias (violated CM) | 2.480 → **2.153 V**, −327 mV | journal 2026-09-05 (1) |

---

## 3. Resolved — the bias node is OPA_BIAS, not VGND

The 2026-09-30 build report described R10 as reaching *"an intermediate node →
existing VGND (~2.5 V)"*. **That description is wrong about the node.**

Builder-confirmed 2026-10-08: R10 lands on **OPA_BIAS** — the ~0.877 V node built
by the 2026-09-05 (4) rebias specifically to cure this problem on U1 — at **cols
41 A–E ∪ 43 A–E** (bridged `41e`→`43e`). **Not** col 45 / `BOT_RED`.

Independent corroboration: **0.876 V measured against 0.874 V recorded** on
OPA_BIAS — a **2 mV** agreement. VGND would have read **2.495 V**, 1.6 V away.

**Consequence.** TI specifies V<sub>CM</sub> = (V−) − 0.1 V to (V+) − 3.5 V, i.e. a
**−0.1 … 1.5 V** window on this 5 V rail. **0.876 V is inside it, near its centre
(~0.925 V).** The TODO-21 common-mode defect is **not reproduced on channel A**;
this buffer inherits U1's *fixed* topology — a single series resistor from a
decoupled bias node, which holds input impedance at exactly 100 kΩ and keeps rail
noise out of the signal path.

**Tier: `RPT` + `DERIV`. Deliberately not promoted to `MEAS`** — no continuity
check from the intermediate node to col 41/43 has been taken. The voltage
agreement is strong evidence; it is not a traced conductor.

**Column precision is load-bearing.** OPA_BIAS is **41/43**; **col 45 is VGND**
(R3 `45a`, R4 `45b`, grey jumper `45c` → `BOT_RED`). This board already carries
D9/TODO-45, where a runbook called `45a` "a free column" while col 45 is the VGND
divider — built literally, it would have put a relay base drive on the VGND rail
and destroyed Teensy pin 14. Record `41`/`43` or `45`, never "around 44".

---

## 4. Resolved — the 2.571 V anomaly was mechanical

**`PHYS` (Action 72): the OPA1642 was not fully seated in its socket.** After
reseating, pins 1/2/3 read a stable 0.876 V.

The 2026-09-30 readings put pin 3 at **+76 mV above** the recorded VGND, where a
genuine common-mode violation had driven U1 **−327 mV below** it — opposite sign.
76 mV across 100 kΩ implies ≈**0.76 µA** out of the input, about six orders of
magnitude above a JFET gate's picoamps. That hypothesis is **withdrawn**;
intermittent contact accounts for the anomalous and unstable readings.

**What the arithmetic was still good for:** it established that the two numbers
could not both be correct, which is what sent the investigation back to the
hardware. A DC reading that disagrees with a recorded node by a physically
implausible amount is a reason to doubt the connection before the design.

---

## 5. OPEN — channel B's bias node is unconfirmed. One probe · ✅ **RESOLVED 2026-10-08 — see §9**

> **Forward pointer.** This question is answered: U4 pin 5 is on `col 38 F–J`
> (`U1_INP_B`, OPA_BIAS via the `38j`→`41c` jumper) and pin 7 reads 0.872 V.
> **The text below is retained unedited** as the record of the open question and
> the reasoning that made it blocking. Read §9 for current state.

The build report says **pin 5 → VGND**. That same report also said "VGND" where
OPA_BIAS is in fact wired (§3), so pin 5 is *probably* on OPA_BIAS too — which
would be correct and would mirror U1 (`U1_INP_B`: blue jumper `38j` → `41c`;
netlist deviation D1 notes U1 pin 5 ties directly to OPA_BIAS with no 100 kΩ).

**Probably is not measured.** It matters because journal 2026-09-05 (4) **Finding
3** applies directly if pin 5 really sits at ~2.5 V: an unused half whose input is
outside its CM range is **not reliably terminated**, and an oscillating channel B
radiates through the shared supply pins into channel A — the exact failure the
termination exists to prevent. This is the named mechanism behind "oscillation-free
is not yet claimed."

| Reading at U4 pin 5 → GND | Means |
|---|---|
| **0.876 V** | correct; mirrors U1; channel B properly terminated |
| **≈2.5 V** | journal 2026-09-05 (4) Finding 3 is live on the unused half |

---

## 6. What this checkpoint establishes — and what it does not

### Supported by the evidence above

- The second OPA1642 is installed on cols 24–27 and is now **fully seated** (`PHYS`).
- Supply and ground are present and correct under static measurement (`MEAS`,
  2026-09-30: 4.96 V / 0.1 mV).
- Channel A's input sits at **0.876 V**, **inside** the OPA1642's specified
  common-mode window (`MEAS` + `DERIV`).
- Channel A behaves as a unity follower **under DC, no-signal conditions** — pins
  1, 2 and 3 all at 0.876 V (`MEAS`).
- Channel B is wired as a terminated unity follower rather than left floating
  (`PHYS` placement; **bias node `NYV`** — §5).
- RETURN_NODE has been branched at `16a` with the existing LINE IN R conductor
  left in place (`PHYS`).
- J8 is wired through the buffer, TIP from col 21 A–E, SLEEVE to GND (`PHYS`).
- C11 blocks the internal bias from the external jack **at the unloaded static
  condition tested**: J8 TIP → SLEEVE = **1.5 mV** (`MEAS`).

### NOT supported — do not cite this record for any of these

- Audio passes through Amp Out.
- Frequency response through the buffer is flat.
- Gain is unity across the audio band.
- The buffer is oscillation-free under dynamic or loaded conditions.
- Connecting an amplifier does not alter the RETURN_NODE measurement.
- Downstream amplifier operation has passed.
- TS/XLR selection has been observed at Amp Out.
- **The feature is complete.** It is not.

**The DC pass is the same class of evidence that looked healthy on U1 while U1 was
operating outside its specified common-mode range.** It is a necessary gate, not a
sufficient one.

---

## 7. Next gate — incremental, and in this order

0. **Two probes first, before any signal.** U4 pin 5 → GND (§5), and continuity
   from R10's intermediate node to col 41/43 to promote §3 from `DERIV` to `MEAS`.
   ✅ **First probe MET 2026-10-08 — §9**, by a better route: pin 5's conductor was
   *observed* at `col 38 F–J` (`PHYS`) and pin 7 reads **0.872 V** (`MEAS`). The
   continuity half is **still outstanding**.
1. Returned audio reaches the buffer and appears at Amp Out.
2. The output waveform is sensible — amplitude, no oscillation, no clipping.
3. Amp Out does not materially disturb the RETURN_NODE measurement. Predicted
   load: ≈**101.6 kΩ** at 1 kHz (100 kΩ ∥ with 1.59 kΩ of C10); effect scales with
   the DUT's source impedance at J6.
4. Only then connect a downstream amplifier.
5. Selected-return behaviour is preserved and observable at Amp Out.

**None of these are passed. Do not mark any of them so.** Full criteria in TODO-69.

---

## 8. Design notes carried forward — `DERIV`, none built

- **Corner asymmetry.** C10 0.1 µF into R10 100 kΩ = **15.9 Hz**. The RETURN
  measurement tap does not share this high-pass, and whether the Rev D shield AC-
  or DC-couples its LINE IN pads is still open (journal 2026-09-12). Amp Out and
  the measurement tap are therefore **not guaranteed to share a low-frequency
  response** — relevant if Amp Out is ever treated as a monitor of what was measured.
- ✅ **FITTED 2026-10-08 (Action 79) — see §10.** Original note retained:
  **No bleed resistor on C11.** Col 21 has no DC path to ground, so J8's TIP floats
  when unloaded; the 1.5 mV reading is consistent with a settled floating node.
  Charge redistribution on first plug-in means a transient into a powered amp.
  100 kΩ–1 MΩ from col 21 to GND would define the jack and bound it.
- **Decoupling loop length.** C3 sits directly across U1 pin 8 (`34i`→`35i`). C9
  reaches GND via col 23 F–J **plus a jumper** — a longer loop. Acceptable;
  recorded rather than silently normalised.
- **C11 polarity is correct and matches C2's precedent:** (+) on the ~0.876 V
  op-amp output, (−) on the near-0 V downstream node.

---

## 9. Update 2026-10-08 (Actions 72–79) — channel B resolved

Appended. **Sections 1–8 are retained unedited**; only forward-pointer markers were
added to §5, §7 step 0 and §8.

### New evidence

| # | Observation | Tier |
|---|---|---|
| 12 | U4 **pin 5** conductor lands on **col 38 F–J** | `PHYS` |
| 13 | U4 **pin 7** (out B) | **0.872 V** `MEAS` |
| 14 | U4 **pins 1 / 2 / 3** (channel A), re-confirmed | **0.876 V**, stable `MEAS` |
| 15 | J8 TIP → SLEEVE, DC, **before** the bleed resistor | **0 mV** `MEAS` |
| 16 | **R11** 100 kΩ Amp Out bleed resistor installed (Action 79) | `PHYS` placement · value `RPT` → **`MEAS` 2026-10-08, see §12** |

### §5 is closed, in the safe direction

**Journal 2026-09-05 (4) Finding 3 does not apply to this part.** Channel B is a
terminated unity follower sitting at **0.872 V** — inside the −0.1…1.5 V
common-mode window, and **2 mV** from the 0.874 V recorded on OPA_BIAS
(2026-09-05 (5)). Both halves of U4 are in spec.

Channel B's bias node is promoted **`NYV` → `PHYS` + `MEAS`**: the conductor was
observed at its landing column, and pin 7's voltage independently agrees with the
node it claims. Named explicitly, because promotion requires saying what the new
evidence was.

### What `col 38 F–J` is — the wording is load-bearing

It is **not** OPA_BIAS directly. The netlist records col 38 F–J as **`U1_INP_B`** —
*U1's own pin 5 node* — reaching OPA_BIAS through the blue **`38j` → `41c`** jumper
(§3 net table, `PHYS`). Electrically OPA_BIAS, so the bias is correct.

**Topological consequence: U1 pin 5 and U4 pin 5 now share one node and one jumper.**
If `38j`→`41c` ever lifts, **both** op-amps' unused halves lose bias at once and both
become the unterminated-channel-B case Finding 3 describes. That jumper carried one
channel's termination before 2026-10-08; it now carries two. **Not a fault — a single
point of failure worth knowing is single.**

---

## 10. Update 2026-10-08 — the bleed resistor (Action 79)

**R11, 100 kΩ, col 21 A–E → GND** (`PHYS`). Closes the §8 design note.

Col 21 now has a defined DC path to ground instead of floating, so Amp Out's DC
state is set by a resistor rather than by leakage, and first plug-in no longer
redistributes an undefined charge into a powered amp.

| Consequence | Value | Assessment |
|---|---|---|
| C11 output corner | **0.159 Hz** (10 µF into 100 kΩ) | negligible across the audio band |
| Buffer DC load | **100 kΩ** | lighter than the 10 kΩ the OPA1642's 0.2 V swing spec assumes — §8 / journal 2026-10-08 (1) headroom reasoning unaffected |
| With a ~1 MΩ amp input connected | 100 kΩ ∥ 1 MΩ ≈ 90.9 kΩ, corner **0.175 Hz** | negligible |

✅ **TAKEN 2026-10-08 — 0.000 V, see §12**, and §12 explains why that reading alone
does not prove the bleed path conducts. Original note retained:

**Still owed, one probe, low priority.** The 0 mV TIP reading (#15) was taken
**before** R11, i.e. on a floating node — indicative, not defined. **A post-bleed
TIP → SLEEVE DC reading is the one that demonstrates the architecture.** Listed in
TODO-69.

---

## 11. NEW, `DERIV`, unmeasured — RETURN→SOURCE leak through shared OPA_BIAS

Raised as **TODO-70**. Recorded here because it is a direct consequence of the bias
topology this document describes. **It is not a measured defect.**

Both buffers are now biased from the same node, and **U4 pin 3 is a signal node.**
The return signal therefore drives OPA_BIAS through R10's 100 kΩ, and OPA_BIAS feeds
U1 pin 3 through R5's 100 kΩ. **That is a path from RETURN into SOURCE that did not
exist before 2026-09-30.**

OPA_BIAS's shunt impedance is R<sub>th</sub> 8.25 kΩ ∥ **C4 alone** — netlist
deviation **D2** records that the 10 µF bulk cap specified by journal 2026-09-05 (4)
step 2 **was never fitted**.

| Frequency | Z<sub>OPA_BIAS</sub> | Leak onto OPA_BIAS | → SOURCE, instrument plugged in | → SOURCE, **input open** |
|---|---|---|---|---|
| 1 kHz | 1 334 Ω | −37.7 dB | **−55.0 dB** | **−37.7 dB** |
| 100 Hz | 5 433 Ω | −27.0 dB | **−31.2 dB** | **−27.0 dB** |

Worse at low frequency twice over: C4 stops holding OPA_BIAS down, *and* C1's 10 nF
makes U1 pin 3 high-impedance (the TODO-19 corner, arriving from an unexpected
direction). With the instrument jack open — the condition most of the SOURCE-floor
investigation ran in — there is no divider at pin 3 and the leak arrives nearly whole.

**Why it is not a footnote.** SOURCE and RETURN are the two channels whose *ratio is
the transfer function*. A leak from RETURN into SOURCE does not look like a fault; it
looks like a plausible rig response — the same hazard class TODO-42 describes. And
−55 dB at 1 kHz sits close to the −56 dBFS crosstalk floor already caveated in
netlist finding A2.

**D2's assessment needs revisiting, not rewriting.** It reads *"missing bulk cap is a
low-frequency PSRR concern, not a functional one."* Fair when one op-amp sat on the
node and nothing injected signal into it. A second buffer injecting signal makes the
missing cap a **crosstalk term** as well. Fitting the 10 µF (in stock) would improve
the first divider by ~**30 dB at 100 Hz** (Z<sub>bias</sub> 5 433 Ω → 155 Ω) and
~38 dB at 1 kHz, and close a documented deviation at the same time.

**Decisive test, cheap:** drive a known tone into **Rig Return TS** with **nothing**
connected to Instrument In, and read SOURCE_NODE. If the leak is real, SOURCE shows
the return tone near the predicted level. **If it does not, the arithmetic above is
wrong and should be corrected here.**

---

## 12. Update 2026-10-08 — three claims confirmed, two tiers promoted

Appended. **Sections 1–11 retained**; only pointer markers were added to the §9
R11 row and the §10 owed-probe note.

| # | Claim | Evidence | Tier |
|---|---|---|---|
| 17 | Channel B DC output | pin 7 = **0.872 V** | `MEAS` (as §9) |
| 18 | **R11 value** | **100 kΩ** read back | **`RPT` → `MEAS`** |
| 19 | **Amp Out DC, post-bleed** | TIP → SLEEVE = **0.000 V** | `MEAS` — supersedes the pre-bleed 0 mV (#15) and the 1.5 mV of §2 |

**R11: two claims, two tiers.** Placement stays `PHYS`; the value is now `MEAS`
because a resistor was read back rather than taken from the build report. Promoted
on named new evidence — the C1/`BC103` lesson.

### The 0.000 V is the right measurement, and it is not the proof it appears to be

It closes the probe §10 listed as owed, and it is the better reading: with R11 fitted
the jack's DC state is **defined by a resistor** rather than by leakage, at a
resolution of 0.000 V.

**It does not demonstrate that the bleed path conducts.** The pre-bleed node —
floating, with no DC path to ground at all — read **0 mV** (#15) and **1.5 mV**
(§2). **A reading that is the same with and without the component cannot
distinguish the two cases.** What the 0.000 V does prove, and it matters, is that C11
still blocks the ~0.876 V internal bias from reaching the external jack.

| To prove | Measurement | Status |
|---|---|---|
| C11 blocks the internal DC bias | TIP → SLEEVE **DC** = 0.000 V | ✅ `MEAS` |
| R11 is electrically in circuit | TIP → SLEEVE **resistance**, power off ≈ 100 kΩ | 🔴 outstanding |

**If the 100 kΩ of #18 was read in-circuit from col 21 (or the TIP) to GND, that
reading already is the second proof** and only needs recording as such. **If it was
read out of circuit before insertion, it confirms the value and not the path.** This
record does not know which, and the distinction is the difference between an observed
placement and a traced conductor.

Same shape as resolved hazard **H-1**, where lifting the COM→tip wire and re-reading
is what made the open meaningful: *the control is what makes the reading meaningful.*
Here the control is the pre-bleed reading, and it happens to match.

### Decision — no component is installed on the strength of §11's arithmetic

**Decided by Conley Vidal, 2026-10-08.** The 10 µF bulk cap of §11 candidate fix 1
is **not** to be fitted on the calculation. **TODO-70 stays open for a controlled
measurement first.**

Fitting it first would remove the condition the prediction was made about: afterwards
a null result could not distinguish *"the cap fixed it"* from *"it was never there."*
This also follows TODO-21's established gate for this board — do not modify hardware
ahead of the requirement, because two electrical configurations mean two sets of bench
results and the breadboard stops being evidence for the product.

### Explicitly still unverified

§11's predicted leak levels · the 10 µF correction · **the buffer's entire AC
performance.** No audio has passed through Amp Out and no amplifier has been
connected.
