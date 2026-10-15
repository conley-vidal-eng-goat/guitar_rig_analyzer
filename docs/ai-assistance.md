# How AI was used on this project

**Conley Vidal · 2026-10-14**

I built this instrument's hardware. AI wrote most of its software. Both of
those are true, and this document says which is which, because the repository
is hard to read correctly without it.

---

## This was never hidden

Every one of the **159 commits** in this repository carries a machine-readable
AI co-authorship trailer:

```
Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
```

No commit lacks it. Anyone running `git log` has always been able to see it.
This document explains that record; it does not confess it.

---

## What I did

**Architecture.** I decided the instrument should be split across two
processors: a **Teensy 4.1** to acquire the audio and compute the measurement,
and a **Raspberry Pi 5** to display the result. I researched that the Teensy
could handle the time-critical acquisition and signal processing while the Pi
handled the graphics. I bought the hardware for that plan — the Pi 5, the 7"
Touch Display 2, the cooler, the PSU and the HAT — before any of it was
implemented. The repository's own audit later described it as *"the original
plan"* while finding that the code had quietly drifted to a different display;
[ADR-001](adr/ADR-001-display-architecture.md) put it back.

**The physical build.** I selected and bought the components, and I assembled
everything: the OPA1642 soldered onto its surface-mount adapter, the breadboard
wiring, the TQ2-5V relays with their MMBT3904 drivers and 1N4148 flyback
diodes, the 1/4" and XLR audio jacks, and the Raspberry Pi with its
touchscreen. My bosses at 4Wall taught me to solder; I did this assembly
myself.

**Every measurement.** Each voltage, resistance, continuity and scope reading
in this repository was taken by me at the bench. In this project those readings
are not a formality — they are repeatedly the thing that decided between two
competing explanations.

**Questioning the written procedure.** The bring-up procedure was developed
with AI, and building the board exposed **eleven defects in it**, two of which
damage hardware if followed literally. Those came out of the gap between what
the document said and what the board in front of me actually did.

## What AI did

I came to Claude and ChatGPT because I knew considerably more about hardware
than software. **Claude generated most of the Teensy firmware and most of the
Raspberry Pi code. I am not the independent author of that code and I do not
claim to be.** I understand what each subsystem is for and how the pieces fit
together. I cannot explain much of the implementation line by line, and how
well I understand it varies by subsystem — the measurement link and the
presentation boundary I follow well, the DSP internals much less so.

AI also co-wrote the breadboard bring-up procedure, the architecture decision
records, and the engineering journal.

**The journal is AI-written.** [`ai/journal.md`](../ai/journal.md) is written in
the first person by an AI, about work the two of us did together. Its own
header says it is written for AI readers — it is a handoff document between
sessions. The engineering voice in it is not mine; the measurements in it are.
Where it says "Conley," it means me: the AI accounts belong to my father,
**the account holder**, and I use them with his permission, so that is the name the
sessions recorded. See [`ai/README.md`](../ai/README.md).

**One convention worth correcting.** 45 of the 159 commits begin with `ai:`. I
had assumed that marked AI-authored changes. It does not — those commits touch
only `.md`, `.log` and `.jpg` files, never a single source file. `ai:` is an
ordinary scope prefix meaning *"this updates the `ai/` engineering record,"*
alongside `docs:`, `feat(pi):` and `fix:`. The `Co-Authored-By` trailer was
always the thing doing that job.

---

## Three specific cases, graded honestly

### 1. "Written" is not "working" — 2026-08-25 · **mine**

I read the first journal and todo entries and objected that they recorded
*firmware written* and *hardware proven* as the same status. I wanted the
documentation to distinguish what existed in software from what had actually
been tested on the physical instrument.

Maturity tags — `[drafted]` / `[compiles]` / `[bench]` — were added in
response, and the journal records the reason as *"collapsing those two facts
into one flag was the root problem"* I had flagged. The wider evidence-tier
vocabulary (`PHYS` / `MEAS` / `DERIV` / `RPT` / `INF` / `NYV`) and the
never-delete rule grew from that over the following weeks **through the same
AI-assisted workflow.** The original objection is mine. The full system that
grew out of it is not mine alone.

### 2. Column 45 — 2026-09-15 · **mine**

Mid-way through Phase 6, the procedure told me to run a jumper from breadboard
column 45 to Teensy pin 14 and described that column as free. I had taken a
continuity reading that did not behave, and I remembered building **"something
else with 2 resistors"** there. I asked whether that was the cause before
fitting the jumper.

It was. Column 45 is the midpoint of the +5 V / ground divider that generates
the analog reference rail, built back in Phase 1. The firmware already on the
board sets pin 14 as an output and drives it high on command, so fitting that
jumper would have put a 3.3 V push-pull output directly onto the analog
reference — on the next power-up. Phase 6 was halted before the board was
energised.

What I contributed was knowing my own board and not believing a document. No
AI, no drawing and no photograph supplied "something else with 2 resistors."

### 3. The OPA1642 bias — **collaborative, and the record is specific about who did what**

The buffer was biased at the 2.5 V mid-supply point while running on a single
+5 V rail. That is outside the part's specified input common-mode range — TI's
datasheet gives `(V−) − 0.1 V` to `(V+) − 3.5 V`, so −0.1 V to +1.5 V on this
rail, and states that below ±3.5 V supplies the range does not include
mid-supply. The supply voltage was legal; **the input bias point at that supply
was not.** That is what makes the defect easy to miss.

- **AI found the defect**, by checking the manufacturer's datasheet against the
  bring-up procedure.
- **My measurements proved it**: 2.480 V at the input with the chip removed,
  2.153 V with it installed — a 327 mV droop showing the input stage loading a
  node it should not — and 159 kΩ pin-to-pin establishing the part was **not
  damaged** and should stay in service.
- **The fix was developed together.** I remember suggesting a resistor-based
  approach to bring the bias down. AI had also written a divider up as one of
  three options, and had recommended a different one (raising the analog supply
  to 9 V). The contemporaneous record does not establish the exact sequence of
  who proposed what, and I am not going to claim more than that. What got built
  is a 47 kΩ / 10 kΩ divider holding the input at **0.874 V**, with the unused
  half of the op-amp moved onto the same node so it could not oscillate.
- **It worked, measurably.** Input droop went from 327 mV to **6 mV**, and over
  the following three days — across an interconnect rework and several power
  cycles — the operating point moved **3–4 mV**. The divider's resistance later
  measured 8.20 kΩ against 8.246 kΩ predicted, 0.6% agreement.

This remains a **bring-up configuration**, not a final design. Saying otherwise
would be the one thing that would make the story dishonest.

---

## Things I got wrong

Some of my own bench reports were later found to be mistaken, and they are
still in the record with their corrections:

- A report transposed two jacks, sending a research effort at the wrong one.
- One measurement was taken with the Teensy powered off, which made its
  conclusion void in both directions rather than evidence for either.
- One component placement I reported was written down as `PHYS` (observed) when
  it should have been `RPT` (reported). The todo file calls that *"this
  project's own named failure mode,"* committed in the very document that cites
  the lesson.

I am leaving these in. The grading system exists because of mistakes like
these, and a record that never caught its author in an error would not be worth
reading.

---

## How I tried to use it

In my own words, from when I was asked about this directly:

> I didn't want to let AI diminish my cognitive thinking. I simply wanted to use
> it as a tool to help with the things I didn't know what to do. I would then
> learn from the AI and boom — we make progress.

That is the whole approach. I evaluated what it told me instead of accepting it
automatically — sometimes I was right to push back, and sometimes the thing
that turned out to be wrong was my own report.

What I can defend is this: I identified a problem I wanted to measure, chose
and bought the hardware, built the instrument with my hands, took every
measurement, and insisted that the documentation tell the difference between
what we had written and what we had actually proven. The code that runs on it
is largely not mine.
