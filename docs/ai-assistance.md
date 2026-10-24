# How AI was used on this project

*Conley Vidal*

I built this instrument's hardware. AI wrote most of its software. This page
says which parts are which.

Every commit in this repository carries a trailer like:

```
Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
```

So `git log` has always shown it. This page explains the details.

## What I did

**Architecture.** I decided to split the instrument across two processors: a
Teensy 4.1 to capture audio and compute the measurement, and a Raspberry Pi 5
to display it. I researched whether the Teensy could handle the time-critical
signal processing while the Pi handled graphics, and I bought the Pi, the 7"
Touch Display 2, the cooler, the power supply and the HAT for that plan before
any code existed. Partway through, the code drifted to a different display
setup; [ADR-001](adr/ADR-001-display-architecture.md) brought it back to the
original plan.

**The physical build.** I chose and bought the components and assembled
everything: the OPA1642 soldered onto its surface-mount adapter, the breadboard
wiring, the TQ2-5V relays with their MMBT3904 drivers and 1N4148 flyback
diodes, the 1/4" and XLR jacks, and the Raspberry Pi with its touchscreen. My
bosses at 4Wall taught me to solder; I did this assembly myself.

**Bench measurements.** I took the voltage, resistance, continuity and scope
readings during construction and troubleshooting. AI helped plan those tests,
interpret the results and write the records. Several times, a reading I took
was what decided between two competing explanations.

**Checking the procedure against the board.** The bring-up procedure was
written with AI. Building the board exposed eleven mistakes in it, two of
which would have damaged hardware if followed exactly. I found those where the
document didn't match the board in front of me.

## What AI did

I knew a lot more about hardware than software going in, so I used Claude and
ChatGPT for the software. **Claude generated most of the Teensy firmware and
the Raspberry Pi software. I'm not the independent author of that code.** I
directed parts of the architecture and behavior, tested it on the hardware, and
worked with AI to track down problems.

AI also co-wrote the bring-up procedure, the architecture decision records, and
the engineering journal.

**The journal is AI-written.** [`ai/journal.md`](../ai/journal.md) is written in
the first person by AI, about work we did together. It was a handoff document
between sessions. The voice isn't mine; the measurements are. See
[`ai/README.md`](../ai/README.md).

A note on commit prefixes: 46 commits begin with `ai:`. That doesn't mean "AI
wrote this." It's a scope prefix meaning "updates the `ai/` engineering
record," like `docs:` or `fix:`. Those commits only touch notes, logs and
photos. The `Co-Authored-By` trailer is what marks AI involvement.

## Three cases

### 1. "Written" isn't "working" (2026-08-25, mine)

I read the first journal and todo entries and objected that they marked
"firmware written" and "hardware proven" as the same status. I wanted the
records to separate what existed in code from what had been tested on the
instrument.

The `[drafted]` / `[compiles]` / `[bench]` maturity tags were added in
response. The wider evidence tags (`PHYS`, `MEAS`, `RPT`, `NYV` and the rest)
and the rule that entries are never deleted grew out of that over the next few
weeks, worked out with AI. The original objection is mine; the system that grew
from it isn't mine alone.

### 2. Column 45 (2026-09-15, mine)

Partway through Phase 6, the procedure told me to run a jumper from breadboard
column 45 to Teensy pin 14 and said the column was free. A continuity reading
didn't behave the way it should have, and I remembered putting two resistors
there earlier in the build. The instructions didn't match my board, so I
stopped and asked before connecting anything.

Column 45 was the midpoint of the +5 V / ground divider that makes the analog
reference voltage, built back in Phase 1. The firmware already on the board
drives pin 14 high on command, so that jumper would have put a 3.3 V output
straight onto the analog reference at the next power-up. Phase 6 was stopped
before the board was powered.

### 3. The OPA1642 bias (shared)

The buffer was biased at 2.5 V, the middle of its single 5 V supply. That's
outside the part's input common-mode range: TI's datasheet allows (V−) − 0.1 V
to (V+) − 3.5 V, which is −0.1 V to +1.5 V on this supply. The supply voltage
was fine; the bias point wasn't. That's why it was easy to miss.

- **AI found the defect** by checking the datasheet against the procedure.
- **My measurements narrowed it down:** 2.480 V at the input with the chip out
  and 2.153 V with it in, a 327 mV droop showing the input stage loading a node
  it shouldn't. A 159 kΩ pin-to-pin reading showed no short, which was reason
  enough to investigate the bias before replacing the part. That reading alone
  didn't prove the chip was undamaged; passing signal correctly after the fix
  did.
- **We worked out the fix together.** I remember suggesting a resistor-based way
  to lower the bias. AI had also listed a divider as one of three options,
  though it recommended a different one (raising the analog supply to 9 V). The
  record doesn't settle exactly who proposed what first, so I won't claim more
  than that. What got built is a 47 kΩ / 10 kΩ divider holding the input at
  0.874 V, with the unused half of the op-amp tied to the same node so it
  can't oscillate.
- **It worked.** Input droop went from 327 mV to 6 mV, and over the next three
  days, through a rework and several power cycles, the operating point moved
  3–4 mV. The divider later measured 8.20 kΩ against 8.246 kΩ predicted.

It's still a bring-up fix, not a final design.

## Things I got wrong

Some of my bench reports were wrong, and they're still in the record with their
corrections:

- I swapped two jacks in a report, which sent a research effort at the wrong
  one.
- I took one measurement with the Teensy powered off, so it proved nothing
  either way.
- One part placement I reported got tagged `PHYS` (observed) when it should
  have been `RPT` (reported).

## How I tried to use it

In my own words, from when I was asked about this:

> I didn't want to let AI diminish my cognitive thinking. I simply wanted to use
> it as a tool to help with the things I didn't know what to do. I would then
> learn from the AI and boom — we make progress.

I checked what it told me instead of accepting it automatically. Sometimes I was
right to push back, and sometimes the thing that turned out wrong was my own
report.

What I can stand behind: I picked a problem I wanted to measure, chose and
bought the hardware, built the instrument by hand, took the bench readings, and
pushed for the records to keep what we had written separate from what we had
actually proven. Most of the code that runs on it isn't mine.
