# `ai/`: the engineering record

This folder holds the project's reasoning trail: a dated journal, a list of
open work with how each item will be proven done, and the raw evidence both of
them cite.

## Who wrote it

I'm Conley Vidal. I designed the system, bought the hardware, and built the
instrument: I soldered the OPA1642 onto its adapter, wired the breadboard,
installed the relays and their flyback diodes, wired the audio jacks, and
assembled the Raspberry Pi and touchscreen. I took the bench measurements
recorded here; AI helped plan the tests, interpret the results and write them
up.

**The journal is written by AI, in the first person.** It was a handoff document
between working sessions, and its header says it was written for AI readers.
The writing voice isn't mine; the measurements in it are. Where it says "the
operator" or "the builder," it means me.

## What's here

| Path | What it is |
|---|---|
| [`journal.md`](journal.md) | Dated entries, **newest first**: why each decision was made, what was considered and rejected, and what the next session needed to know. Entries are never deleted. A reversed decision gets a new entry, and the old one stays. |
| [`todo.md`](todo.md) | Open work in priority order. Each item says why it matters, what has to happen, and how it will be proven done. |
| [`evidence/`](evidence/) | Bench records, serial captures, raw `.bin` byte streams, screenshots, photos, and the exact firmware image that was flashed. |
| [`drafts/`](drafts/) | Two journal drafts that were never merged in, kept as written. |

The journal is about 9,600 lines, so the reading list at the end is the short
way in.

## How claims are tagged

"We wrote the code" and "it works on the board" are different facts, so every
claim is tagged with how it is known.

**Evidence tiers** (defined in [`../docs/asbuilt/netlist.md`](../docs/asbuilt/netlist.md)):

| Tag | Meaning |
|---|---|
| `PHYS` | Physically observed |
| `MEAS` | Measured, with the number recorded |
| `DERIV` | Calculated from a measurement |
| `PHOTO` | Read from a photograph |
| `RPT` | Reported by me, not independently confirmed |
| `INF` | Inferred from documentation |
| `NYV` | Not yet verified |

A tag is only upgraded when new evidence comes in. If a part's position was
seen but its value was only reported, it stays `PHYS` for position and `RPT`
for value.

**Maturity tags** on hardware work: `[drafted]` code exists but is untested,
`[compiles]` builds but has never run on hardware, `[bench]` verified on the
board.

**Status:** 🔴 not started · 🟡 in progress · 🟢 done and verified · ⚪ blocked.

This started with a correction I made on 2026-08-25. The first journal and todo
entries marked "firmware written" and "hardware proven" as the same status, and
I asked for them to be kept apart. The maturity tags came from that. The tier
system and the never-delete rule grew out of it over the following weeks,
worked out with AI. The objection was mine; the full system wasn't mine alone.

## Where to start

1. **The OPA1642 bias defect**, journal entry `2026-09-05 (1)`. The buffer was
   biased at 2.5 V on a 5 V supply, outside the part's input common-mode range.
   Two hardware theories were wrong; the real mistake was in the written
   procedure. A 159 kΩ pin-to-pin reading ruled out a short, so the bias was
   investigated before the part was replaced, and the part turned out to be
   fine.
2. **Phase 6 stopped at column 45**, journal entry `2026-09-15 (1)`. The
   procedure called a breadboard column free, but I remembered putting two
   resistors there. I stopped before wiring it. It was the analog reference
   divider, and the next power-up would have driven a 3.3 V output pin into it.
3. **The return-path fault**, journal entry `2026-10-18 (1)`. The rig's return
   had gone silent. Settings were ruled out from the Teensy's serial output, the
   netlist narrowed it to one wire run, and a touch test pointed at the codec's
   LINE IN R solder joint. Resoldering it brought the return back.
4. **[The timing test that was wrong](evidence/2026-09-29-t1-harness-block-stride-defect.md)**.
   A reported 44,490 "skipped audio blocks" turned out to be arithmetic, not
   observation. The conclusion recorded was that the test couldn't decide the
   requirement, not that the requirement passed.
5. **[The buffer DC checkpoint](evidence/2026-10-08-ampout-buffer-dc-checkpoint.md)**:
   a record that refuses to upgrade values that were reported but never read.

## Mistakes left in

Some of my bench reports were wrong. One swapped two jacks and sent a research
effort at the wrong one. One measurement was taken with the Teensy powered off,
so it proved nothing either way. One placement was tagged `PHYS` when it should
have been `RPT`. They're still in the record, with their corrections.

See also [`../docs/ai-assistance.md`](../docs/ai-assistance.md) for how AI was
used on this project.
