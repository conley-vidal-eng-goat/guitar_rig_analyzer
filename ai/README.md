# `ai/` — the engineering record

**Read this before reading anything else in this directory.**

This folder holds the reasoning trail for the Guitar Rig Analyzer: a dated
journal, an outstanding-work list with proof criteria, and the raw bench
evidence those two cite. It is the most useful material in the repository and
it is also the easiest to misread, so this file says what it is, who wrote it,
and how to read a name in it.

---

## 1. Attribution — a clarification from the builder

**Added 2026-10-14 by Conley Vidal. Nothing in this directory's history was
edited to add it.**

I am **Conley Vidal**. I designed the system architecture, selected and bought
the hardware, and physically built this instrument — I soldered the OPA1642
onto its surface-mount adapter, wired the breadboard, installed the relays and
their flyback diodes, wired the audio jacks, and assembled the Raspberry Pi
and its touchscreen. Every voltage, resistance and continuity reading recorded
in this directory was taken by me at the bench.

**`ai/journal.md` is written in the first person by an AI**, about work the AI
and I did together. Its header says it is written for AI readers, and that is
what it is — a handoff document between working sessions. The engineering voice
in it is not mine. The measurements in it are.

**Where the journal says "Conley," it means me.** The AI accounts used on this
project belong to my father, **the account holder**, and I use them with his
permission. The AI sessions knew their human counterpart only by that account
identity, so that is the name they wrote down. My father did not participate in
developing, debugging or building this instrument. All 159 commits in this
repository are authored `Conley Vidal <conleyvidal@icloud.com>`, which is the
independent record of who was doing the work.

**Historical entries have deliberately not been rewritten.** Changing 34 names
across six weeks of dated records would damage the one thing that makes this
trail worth reading. This note is the correction; the record stays as written.

---

## 2. What is in here

| Path | What it is |
|---|---|
| [`journal.md`](journal.md) | Dated reasoning trail, **newest entry first**. 136 entries. Why a decision was made, what was considered and rejected, and what the next session needs to know. Entries are never deleted — a reversed decision gets a new entry that says so, and the old one stays. |
| [`todo.md`](todo.md) | Outstanding work in priority order. Every item states why it matters, what has to happen, and **how it will be proven done**. |
| [`evidence/`](evidence/) | The raw material: bench records, serial captures, `.bin` byte streams, screen captures, photographs, and the archived firmware image that was actually flashed. |

These are large — the journal is about 9,000 lines. **Section 4 below is the
short way in.**

---

## 3. How a claim is graded

Both files and every evidence record tag their claims, because "we wrote the
code" and "it works on the board" are different facts and this project has
been burned by collapsing them.

**Evidence tiers** (defined in [`../docs/asbuilt/netlist.md`](../docs/asbuilt/netlist.md)):

| Tier | Meaning |
|---|---|
| `PHYS` | Physically observed |
| `MEAS` | Measured, with the number recorded |
| `DERIV` | Computed from a measurement |
| `PHOTO` | Read from a photograph |
| `RPT` | Builder-reported, not independently confirmed |
| `INF` | Inferred from documentation |
| `NYV` | Not yet verified |

A tier is **never promoted by assumption.** A component whose position was seen
but whose value was only reported stays `PHYS` for placement and `RPT` for
value, on the same row. Records in here decline to promote their own claims —
one reads *"no numbers were recorded, so that is `RPT` and is not evidence of a
value."*

**Maturity tags** on hardware-adjacent work: `[drafted]` source exists but is
unverified · `[compiles]` builds clean, never run on hardware · `[bench]`
verified on the physical board.

**Status:** 🔴 not started · 🟡 in progress · 🟢 done *(verified, not just
coded)* · ⚪ blocked.

This grading system exists because of a specific correction I made on
**2026-08-25**: I read the first journal and todo entries and objected that they
recorded "firmware written" and "hardware proven" as the same status. The
maturity tags were added in response. The tier vocabulary and the never-delete
rule grew out of that over the following weeks through the same AI-assisted
workflow — I raised the original objection; I did not design every later detail
of the system by myself.

---

## 4. Five entry points, if you are reading this cold

1. **[The OPA1642 common-mode defect](journal.md)** — journal entry
   `2026-09-05 (1)`. The buffer was biased at 2.5 V on a 5 V supply, outside
   the part's specified input common-mode range. Two plausible hardware
   hypotheses were wrong; the real fault was in the written procedure. The
   suspect chip was **exonerated by measurement** (159 kΩ pin-to-pin, no short)
   rather than replaced on suspicion.
2. **[Phase 6 halted on column 45](journal.md)** — journal entry
   `2026-09-15 (1)`. The procedure called a breadboard column free. I remembered
   building "something else with 2 resistors" there and asked before fitting the
   jumper. It was the analog reference divider, and the next boot would have
   driven a 3.3 V output pin onto it.
3. **[The timing harness that lied](evidence/2026-09-29-t1-harness-block-stride-defect.md)**
   — 44,490 "skipped audio blocks" that never happened. The measuring
   instrument was broken, not the thing being measured. The conclusion recorded
   was *"T1 is not adjudicated"*, not a pass.
4. **[The buffer DC checkpoint](evidence/2026-10-08-ampout-buffer-dc-checkpoint.md)**
   — the tier discipline applied to a record's own contents, refusing to
   promote values that were reported but never read.
5. **[What the design references are allowed to mean](../docs/ui/references/README.md)**
   — nineteen visual references catalogued, **six marked as fabrications**
   because the numbers on them correspond to no sensor this instrument has.

---

## 5. One honest warning

Some builder reports in here were later found wrong. A report transposed two
jacks and sent a research effort at the wrong one. One measurement was taken
with the Teensy powered off, making its conclusion void in both directions. One
placement was tagged `PHYS` when it was a builder report and should have read
`RPT` — the todo file calls that *"this project's own named failure mode,"*
committed in the very document that cites the lesson.

Those are left in place, with their corrections. A record that never caught its
author in an error would not be worth much.

---

*See also: [`../docs/ai-assistance.md`](../docs/ai-assistance.md) for how AI was
used on this project and what I did and did not write.*
