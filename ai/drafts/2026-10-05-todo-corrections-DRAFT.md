# DRAFT — proposed `ai/todo.md` corrections. Not applied, not committed

Source: journal draft `2026-10-05-journal-entry-DRAFT.md`.
Line numbers are as of this reading and will shift; the **quoted text** is the
reliable anchor.

**Scope discipline.** Every change below is either (a) replacing a stale
*assertion of current bench state* with a tiered one, or (b) adding a
supersession marker above retained text. **No existing text is deleted** — the
never-delete rule applies to `todo.md` reasoning the same way it does to the
journal. Items 1–4 are record corrections; item 5 is a new tracking item; item 6
is a source change and should not ride in the same commit.

**What these corrections must NOT do, and do not:** mark the J4 tip connection
repaired, or close TODO-19 / TODO-23 / TODO-21 / TODO-40.

---

## 1. TODO-40 — the BENCH STATE list is stale, and each of the four needs its own tier

### 1a. Line 349

**Currently reads:**
> **🚨 BENCH STATE — four deviations from the −31.49 dBFS pooled baseline are currently in place:** `48e` lifted off LINE-IN-L · LINE-IN-L jumpered to GND · J2 removed · `col 30` → GND jumper fitted. **Restore all four and re-baseline before any future reading is treated as comparable.**

**Proposed replacement:**
> **🚨 BENCH STATE — the four-deviation list below is SUPERSEDED as a statement of current state (2026-10-05). Original retained; status per item, with tiers, because they are not equally established:**
>
> | Deviation | Status | Tier |
> |---|---|---|
> | `col 30` → GND jumper fitted | **REMOVED 2026-10-05** | **`MEAS`** — J4 tip → GND = OL, and J4 tip lug → col 30 = OL |
> | `48e` lifted off LINE-IN-L | **believed restored** | **`DERIV`, not measured** — `netlist.md` §3 carries `48e` → LINE-IN-L as `PHYS`, and §14's SOURCE −10.1 dBFS on 2026-09-19 is unobtainable without it |
> | LINE-IN-L jumpered to GND | **believed removed** | **`DERIV`, not measured** — with `48e` connected this jumper would short SOURCE_NODE, which §14's −10.1 dBFS excludes |
> | J2 removed | **permanent, not pending** | `PHYS/OBS` — `netlist.md` §10.0 **S-1**, 2026-09-21: no conductor remains. **Stop listing this as a deviation awaiting restoration** |
>
> **Two `DERIV` rows are inferred from a reading taken for another purpose and
> have never been probed. Do not cite either as confirmed.** One continuity check
> each would promote them to `MEAS`.
>
> **🔺 The baseline problem is now worse, not better.** The −31.49 dBFS pooled
> figure was taken with the guitar connected and volume up. Journal 2026-10-05 (1)
> establishes that **`J4 tip lug → col 30` last read OL**, so the instrument input
> may be physically disconnected. **Until that one conductor is measured, the
> pooled baseline cannot be attached to any known configuration** — removing the
> col 30 jumper did not restore comparability by itself.

### 1b. Line 361

**Currently reads:**
> **Also outstanding from this session:** `col 30` → GND jumper still fitted, `48e` → LINE-IN-L still lifted, J2 still removed. **Restore all three and re-baseline…**

**Proposed:** prepend `⛔ **SUPERSEDED 2026-10-05 — see the BENCH STATE table above. Retained as the record of what was outstanding at the time.**` and leave the sentence unedited.

### 1c. Lines 235, 313, 321 — three restoration checklists naming the jumper

All three are **instructions**, not state assertions, so they are factually
unchanged; they just now have one step already done. Minimal edit, on each:

**Proposed:** append `*(2026-10-05: the `col 30` → GND jumper step is complete — `MEAS`. The LINE-IN-L ground jumper and `48e` steps are `DERIV` only; see TODO-40's BENCH STATE table.)*`

---

## 2. TODO-6 — the ⛔ hold on the jumper is superseded by this item's own decision

Both lines below sit **beneath** TODO-6's own boundary marker — *"Everything below
this line predates the continuity identification… the SHUNT topology reasoning
does not describe the installed jack."* They were nonetheless read as live, and
they placed a hold on removing a jumper that was shorting the guitar input.

### 2a. Line 708, the 🧪 falsifiable prediction

**Proposed:** prepend `⛔ **UNPERFORMABLE — withdrawn 2026-09-13 (9). J4 has no SHUNT contact to wire; lug #2 and the long spring are one TIP net. Retained as the record of the proposed experiment.**`

### 2b. Line 709, the ⛔ consequence-for-deviation-restoration hold

**Proposed:** prepend
> ⛔ **SUPERSEDED 2026-09-13 (10), acted on 2026-10-05.** This hold was dependent on the SHUNT → pin 16 experiment, which **2026-09-13 (9)** withdrew as unperformable, and on detect using the TIP node, which **2026-09-13 (10)** decided against — *"do not sense their TIP nodes."* **Nothing was load-bearing on the jumper**: pin 16 has no conductor to J4, appears nowhere in `netlist.md`, and showed zero `JACK_CHANGED` events across 45 windows of insert/remove. The jumper was removed 2026-10-05 and no detect capability was lost, because none existed. **Retained because the never-delete rule applies, and because the hold being read as current for 22 days is itself the lesson.**

### 2c. Add to TODO-6's current (above-the-line) section

> **Step 3 of the next-bench-sequence below is ✅ MET (2026-10-05):** *"Verify whether SLEEVE is actually connected to system GND."* **J4 sleeve → breadboard GND rail = 0.2 Ω** (`MEAS`). Open since 2026-09-13. Proposed promotion in `netlist.md` §12.3: J4 sleeve `RPT` → `MEAS`.

---

## 3. TODO-32 — new in-circuit reading for R5, which does NOT close it

**Proposed addition:**
> **🆕 Second in-circuit reading, 2026-10-05.** `col 37` ↔ `col 41` measured **100.7** — **unit not confirmed by the operator (Ω or kΩ), and deliberately not assumed here.** Read as kΩ it agrees closely with R5 = 100 kΩ plus OPA_BIAS's 8.25 kΩ Thévenin and **conflicts with the 73.5 kΩ** in-circuit reading of 2026-09-08. Read as Ω it would mean R5 is shorted, which the rest of the front end's behaviour excludes.
>
> **This does not close TODO-32.** The item's own proof criterion is an
> **out-of-circuit** ohmmeter reading plus a colour-band reading agreeing on one
> value. Two in-circuit readings that disagree with each other are an argument for
> doing that, not a substitute. **First action: confirm the unit.**

---

## 4. TODO-69 / TODO-70 — one cross-reference

**Proposed addition to both:**
> **⚠️ Precondition from journal 2026-10-05 (1):** `J4 tip lug → col 30` last read **OL**. Any RETURN_NODE or SOURCE_NODE reading taken while that conductor is open was taken with the **instrument input physically disconnected**. Confirm it before interpreting an Amp Out or leak-path result — including TODO-70's decisive test, whose "nothing connected to Instrument In" condition would be satisfied **by accident** rather than by design, and which therefore cannot distinguish the two.

---

## 5. Proposed new item — the live blocker

Numbered TODO-71 on the assumption 70 is the current maximum; renumber as needed.

> ### TODO-71 — `J4 tip lug → col 30` last measured OPEN and has never been re-measured 🔴 [bench] **leading hardware suspect. One probe**
> **Why:** journal 2026-10-05 (1). Removing the `col 30` → GND diagnostic jumper opened the J4 Instrument In tip conductor — `DERIV` from J4 tip → GND reading **1.2 Ω** before and **OL** after, with the tip lug → col 30 then reading **OL** directly (`MEAS`). The session ended with the fault identified and **no repair measurement taken.**
> **Consequence while open:** the guitar never reaches C1, so SOURCE_NODE, RETURN_NODE, Rig Send, Rig Return and Amp Out all carry no instrument signal. **Every level reading taken in this state is a noise-floor reading**, and will look like a fault further down the chain than it is.
> **What:** power off, re-seat the J4 tip conductor in col 30, confirm **`J4 tip lug → col 30` < 1 Ω**.
> **Proof — three readings, recorded in `journal.md`:**
> 1. J4 tip lug → col 30 **< 1 Ω**, power off.
> 2. J4 tip → GND **OL**, power off, guitar unplugged. (C1 blocks DC; `netlist.md` puts nothing else on `SOURCE_IN`.)
> 3. Guitar plugged in, volume at maximum, tip → sleeve at the cable's far end = **pickup DC resistance, 6–15 kΩ**. This is the one that proves the instrument sees an open circuit again rather than a short, and it is **off-board** — it also clears the cable and the jack's tip contact.
> **Then, and separately:** a SOURCE_NODE peak reading on a strum, against **§14's −10.1 dBFS**.
> **⚠️ Do not expect clean audio on restoration.** TODO-19, TODO-23, TODO-40 and TODO-21 are all unfixed and all predict a thin, hissing signal. **A thin hissing guitar is the expected pass for this item.** A clean one is the surprising result and should be investigated, not celebrated.
> **Bench-safety:** col 30 is remote from the Audio Shield and the I²S interconnect, so this does not threaten the R1-protected geometry. **It is adjacent to the new cols 21–27 Amp Out build** (TODO-69) — the handling risk is disturbing that, not the analog columns.

---

## 6. Source change — separate commit, not part of the above

**[`signal_router.h:72`](../../signal_router.h#L72)** states:
> *"The RELAY_RETURN driver is not built yet: that is a Phase 7 bench requirement, not something this code proves."*

**Stale.** K2 and its driver were built in Phase 7 and are recorded in
`netlist.md` §12.2, with the contact map bench-proven by state on 2026-09-19 and
the relay exercised since. A comment asserting the hardware does not exist sits
directly above the code that drives it, and a reader checking whether the return
relay is real would be told no.

**Not drafted as a replacement here** — it is a source edit, it belongs in a
commit with other source corrections rather than with evidence documents, and the
wording should say what §12.2 now establishes rather than merely dropping the
claim.
