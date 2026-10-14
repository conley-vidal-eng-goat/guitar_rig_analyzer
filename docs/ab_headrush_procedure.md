# The Headrush A/B — showing that the instrument detects a real change in a real rig

**Written 2026-10-13 from the firmware and presentation contracts. Nothing in this
document has been executed.** It is the procedure for the demonstration the
portfolio actually needs: change one thing in a guitar rig, and have the
instrument report the difference.

---

## 0. Why TONE showed zero measured bands — and why that was correct

This question had to be answered before the experiment could be designed, because
the answer determines the stimulus.

```
config.h:526   #define TF_SOURCE_GATE  0.001f      // linear FFT magnitude, ~ -60 dBFS
config.h:560   #define TF_CONFIDENCE_THRESHOLD 0.10f   // >= 51 of 512 bins energised
```

A bin whose **averaged source magnitude** is below the gate is *unenergised*: the
firmware writes `NAN` to `tf_db[]` and clears the bin's `valid` nibble. The Pi
reads that nibble as **`pen_lift`** and classifies the bin **UNMEASURED**
(`presentation_semantics.classify_live`), and an UNMEASURED band draws **nothing**.

**A plucked guitar note energises a handful of bins out of 512.** Observed on the
panel 2026-10-13: `confidence 4 %`, `6 measured · 122 unmeasured`. That is the
instrument working exactly as specified. **It is not a rendering defect, and it is
not a flat response.**

### 🛑 How to tell absence of measurement from a flat response

They look nothing alike, and conflating them would be the single worst error this
experiment could make:

| | On TONE | On LIVE |
|---|---|---|
| **No measurement** | no bar at all, band counted `unmeasured` | `confidence` low, coverage says `0 measured · 128 unmeasured` |
| **Flat response** | a bar at or near the 0.03 minimum height on **every** band, counted `measured` | `confidence` high, `128 measured · 0 unmeasured`, the TF curve drawn flat near 0 dB |

**The census line on screen is the discriminator, and it is always on screen.** If
the bands are `unmeasured`, the instrument is saying *"I did not measure this"* —
never *"this is 0 dB."*

### What follows for the experiment

**Guitar playing cannot produce a valid transfer function, and two guitar
performances cannot be compared.** A TF divides RETURN by SOURCE per bin, which
*does* normalise out the source — but only for bins the source actually
energised, and two performances energise different bins. Setting A and setting B
would be compared across different bin sets, which is not a comparison.

**The experiment needs a repeatable broadband stimulus.** `docs/breadboard_bringup_v3.md`
already uses one for exactly this purpose: *"Plug a phone into the test cable.
Play a song at low volume."* Pink noise is better than music — broadband,
stationary, and repeatable by replaying the same file at the same level.

---

## 1. Which measurement: LIVE or RESULT

**Both, in that order.** They answer different questions and the second is the
evidence.

| | LIVE TF | RESULT |
|---|---|---|
| How it starts | continuously, whenever the instrument is powered | armed by the `m` command |
| Smoothing | EMA, `TF_SMOOTHING_ALPHA 0.15` | per-measurement averaging |
| Quality verdict | none — only `confidence` | **graded**: EXCELLENT / GOOD / MARGINAL / POOR, from coherence and the fraction of bins meeting it |
| Coherence | not reported | reported |
| Who can trigger it | nobody — it just runs | **the Mac, over the Teensy's USB console** |

```
measurement_core.h:248-253
  EXCELLENT  coherence >= 0.95  and >= 0.90 of bins
  GOOD       coherence >= 0.85  and >= 0.75 of bins
  MARGINAL   coherence >= 0.70  and >= 0.50 of bins
  POOR       below that
```

**🔺 The Pi cannot arm a measurement.** Pi→Teensy is physically disconnected and
the panel says so (`commands disabled`). `m` must be typed on the Teensy's USB
serial console from the Mac — `/dev/cu.usbmodem192895301` at 115200. That is the
only command path that exists.

**🔺 LIVE's EMA is "sticky" by design** (`config.h:529-554`): when a bin falls
below the gate its smoothing buffer is **not** reset, so it holds its last value.
With continuous broadband stimulus every bin stays energised and the EMA converges
in about a second, so stickiness does not bite — **but it is why the stimulus must
be running continuously across the A→B change and for a dwell afterwards.** Stop
the noise between settings and the curve you see next may be partly the previous
setting's.

---

## 2. What this experiment can and cannot claim

**✅ It can claim an *observed differential change*, with its limitations stated.** A transfer function is a ratio, and the comparison
is A against B on the same instrument, same routing, same gain, same stimulus,
minutes apart. **A differential claim survives the absence of calibration**, which
is exactly the state this instrument is in — and that makes it the strongest
measurement available today, not a compromise.

**❌ It cannot claim a verified Headrush frequency response.** Call it what it is:
*the instrument reported a repeatable difference between two rig settings.* Four
open items say why, and none is closed by this procedure:

- **TODO-43** — the volts-to-dBFS mapping is unexplained and the line-in level is
  uncalibrated. **Every dBFS figure here is an instrument reading, not a voltage.**

- **TODO-75** — the grounded-probe floor on the DHO804 is unrecorded. **It gates
  every amplitude claim.**
- **TODO-78** — every level measured before 2026-10-12 was taken through an
  unintended ≈1.59 kΩ shunt. **No post-repair baseline exists.**
- **TODO-70** — the controlled RETURN→SOURCE leak test has never run, so some
  fraction of SOURCE may be RETURN leaking through the shared `OPA_BIAS` node.

**🛑 And the repaired Instrument In short has NOT been electrically revalidated.**
The operator reported the continuity gone (`RPT`, journal 2026-10-13 (5)); no
measurement was recorded, no coordinates, no photograph. **Do not write that the
input has been verified.** It has been reported repaired.

---

## 3. The bench procedure

### Prerequisites

| | |
|---|---|
| Instrument | powered, session stable, `LINK UP` on the panel |
| Kiosk | running; the web transport is the sole `/dev/ttyAMA0` holder |
| Mac | on AC, lid open, `caffeinate` running, Teensy USB present |
| Return source | **TS** — set at boot and operator-selected (ADR-004). The panel must read `Return source: TS` |
| Detectors | `UNKNOWN (no detect hardware fitted)` — **the instrument cannot confirm what is plugged in. The operator must.** |

### Signal path to confirm by eye — not by the instrument

```
stimulus source ──► INSTRUMENT IN ──►(SOURCE tap)──► RIG SEND ──► Headrush input
                                                                        │
            (RETURN tap)◄── RIG RETURN TS ◄─────────────────── Headrush output
```

The rig under test sits inside the loop. The transfer function **is** the
Headrush's response.

**🛑 Do not enable internal injection.** `injection_active` is false, `can_inject`
requires `rig_send` detection, and the detect hardware is not fitted. Enabling it
is a separate decision with its own routing and safety caveats.

### Stimulus — and the electrical question, answered from the as-built record

**🛑 GATE: nothing is connected until this section is read and the source is
confirmed. A phone output and an instrument output are not interchangeable, and
"it has a 3.5 mm jack" is not an electrical argument.**

**What the record actually says.** The input stage was *designed* for this case —
`breadboard_bringup_v3.md` justifies the input coupling capacitor in exactly these
terms: *"your phone outputs AC centered on its own ground, which has no idea what
our VGND is. Cap blocks DC, passes signal."* The same document's Phase-7 verify
step is **"plug a phone into the test cable, play a song at low volume"**, with the
acceptance band **SOURCE −24 to −6 dBFS**. So a phone source is documented bench
practice on this board, not an assumption introduced here.

**The path** (`docs/asbuilt/netlist.md`): `J4 1/4" jack tip → col 30 → C1 → U1A
(OPA1642, JFET) → U1 pin 1 → C2 10 µF → col 48 SOURCE_NODE → jumper → U3 LINE-IN-L`.
The buffer is **unity** — 1 kHz gain measured at **0.9848** (journal 2026-09-05) —
so **nothing attenuates the source before the codec.** Whatever the phone puts
out arrives.

**Estimated headroom, and the estimate's provenance.** One calibration point
exists: **0.123 Vrms at LINE-IN-L → SOURCE ≈ −29.9 dBFS** (`config.h:346`).
Scaling from it, the −24 to −6 dBFS acceptance band is roughly **0.24 to 1.9 Vrms**
at the jack. A phone headphone output into a high-impedance load typically
delivers 0.3–1.0 Vrms at full volume, so **a phone lands inside the band and
cannot reach the top of it.**

**🔺 That estimate rests on a single point and an unexplained full scale.**
TODO-43: the same figure implies a full-scale input of ~10.85 Vpp, while
`lineInLevel()` spans only 3.12 Vpp (level 0) to 0.24 Vpp (level 15) — **no
register value can produce the observed result**, and `SGTL5000_LINE_IN_LEVEL 5`
is marked *"CALIBRATE BEFORE FIELD USE"*. **The volts-to-dBFS mapping on this
instrument is not understood.** So the level is set **empirically, by watching
SOURCE on the panel**, never computed — and this is another reason the experiment
may only claim a difference.

**🛑 Ground loop — use a phone on battery, not a laptop on a charger.** The
coupling capacitor blocks DC but the sleeve still bonds the source's ground to the
analyzer's GND, which bonds to the Teensy's GND, which bonds to the Mac's USB
ground. A mains-powered source closes a loop through the mains earth; a
battery-powered phone with nothing else plugged into it does not. **Disconnect the
phone's charger before connecting it.**

**No internal source is available.** `config.h` has `#define ENABLE_DUT_INJECTION 0`
— injection is compiled out, `injection_active` is false, and the detect hardware
is not fitted. There is no stimulus inside the established routing architecture,
which is why an external one is required at all.

### Setting the level

Continuous **pink noise**, raised slowly from silence while watching the panel,
until SOURCE sits in **−24 to −6 dBFS**. Aim near **−12 dBFS** — comfortably
inside, with headroom at the top. Then write the volume setting down and **do not
touch it again for the rest of the session.** It is the control variable.

**Check for clipping before trusting anything:** the LIVE payload carries
`source_clip` and `return_clip`, and the TONE census reports `clamped` bands.
**Any clipping on either channel voids the comparison** — reduce the level and
restart from the dwell.

### The parameter to change

**One Headrush parameter with an unambiguous frequency-domain signature.** A
cabinet/IR change or a single tone control (bass or treble at a stated setting) is
ideal; gain, drive and anything time-based are not — compression and delay are not
a linear transfer function and the comparison would not mean what it looks like.

Record the exact preset name and every setting you can see, for both A and B.

### The sequence

| # | Action | Expected on screen | Record |
|---|---|---|---|
| 1 | Confirm connections by eye; photograph the rig | `Return source: TS` | photo |
| 2 | Start pink noise; set level | LIVE `confidence` climbs toward 100 %, `128 measured · 0 unmeasured` | the level, a panel capture |
| 3 | **Dwell 30 s** | census stable, `decode_errors 0`, `stale false` | counters before |
| 4 | Capture **A** on LIVE | TONE shows sustained bars | panel captures, `/api/frame` JSON |
| 5 | Arm a RESULT from the Mac: `m` | state `MEASURING` → `RESULT`, a quality grade | the RESULT, its grade and coherence |
| 6 | **Change exactly one Headrush parameter.** Nothing else. | LIVE curve moves within ~1 s | the new setting |
| 7 | **Dwell 30 s** — mandatory, for the EMA | census stable again | — |
| 8 | Capture **B**, then arm a second RESULT | a second grade and coherence | same set as A |
| 9 | Stop the noise | bands return to `unmeasured` — **the honest display of no input** | final counters |

### 🔑 The leak control, which this experiment gets for free

TODO-70 — the uncontrolled RETURN→SOURCE leak through the shared `OPA_BIAS` node —
**is not cancelled by differencing.** If some RETURN energy reaches SOURCE, and the
Headrush change alters RETURN's spectrum, then SOURCE changes too and the ratio is
contaminated in a way a simple A/B cannot see.

**But the experiment contains its own detector for it.** The stimulus is fixed and
untouched, so **SOURCE must be identical in A and B.** If SOURCE's spectrum moves
when only the Headrush changed, the only remaining path is leakage.

> **Record SOURCE's own spectrum in both states and compare it first.**
> SOURCE unchanged → the leak did not bias this comparison measurably.
> SOURCE changed → the result is contaminated, and by how much is now visible.

That turns an open blocker into a measured bound inside the run, without new
hardware. It does not close TODO-70, which needs its own controlled test.

### Comparing only what is comparable

**Compare the intersection, not the union.** A bin is in the comparison only if it
is `MEASURED` in **both** A and B. A bin that is `UNMEASURED` or `CLAMPED` in
either state carries no comparable value, and quietly treating a missing bin as
unchanged would manufacture a flat region that was never measured.

Report the intersection size alongside the result: *"N of 128 bins measured in
both states"* is part of the claim, not a footnote.

### Stop conditions

Stop and report, do not improvise, if: `confidence` never rises above
`TF_CONFIDENCE_THRESHOLD` with noise running; the session id changes (a Teensy
restart invalidates the pair); `decode_errors` or interior discards become
non-zero; the RESULT aborts (`measurementEngine_getAbortReason()` — `TIMEOUT`
means it never saw stimulus); or the panel stops updating.

### Evidence to preserve

Both `/api/frame` payloads, both RESULTs with grade and coherence, panel captures
of LIVE and TONE in both states, the stimulus file and level, every Headrush
setting, the session id at both ends, and the link counters before and after.
**A and B are only comparable if the session id is identical at both.**

---

## 4. What this run also settles about the UI

A sustained broadband stimulus is the first condition under which the TONE bar
path is continuously populated, so **four open items can be closed in the same
session at no extra cost**:

| | How |
|---|---|
| **TODO-90** | emissive bars and the second easing channel become visible, because bars exist for minutes rather than seconds |
| **TODO-88** | clipping either happens under real data or does not — and the camera decision stops being a worst-case argument. **Orbit deliberately while the bars are up** |
| **TODO-87** | scroll LIVE with a finger during the dwell and check that nothing highlights |
| **TODO-89** | tap through all four views during the dwell and judge whether 5 Hz reads as live |

**Do them during the dwells, not during the captures.** A finger on the panel
while a RESULT is being armed is an uncontrolled variable.

---

## 5. The exact first physical action

> **Photograph the rig as it currently stands, and write down every Headrush
> setting you can see — before touching anything.**

Nothing is connected, disconnected or adjusted. If the A/B later shows a change,
that photograph is what establishes the change was the one parameter and not
something that moved while you were working. It is also the portfolio's picture of
the instrument in its working state, and that state exists right now.
