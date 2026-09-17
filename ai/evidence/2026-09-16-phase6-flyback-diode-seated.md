# 2026-09-16 — Phase 6 flyback diode seated, relay marking

**File:** `2026-09-16-phase6-flyback-diode-seated.jpg` (downscaled from the builder's 4032×3024 original, `IMG_4168`).

**Taken:** 2026-09-16 at the end of Phase 6 bring-up (RELAY_SEND), after the coil polarity fix and the flyback diode reseat. Board powered from USB; relay de-energised.

**What it shows (`PHOTO`):**
- The Panasonic relay straddling the centre gap at columns 55–59, marked **TQ2-5V · ATQ209 · JAPAN · 60214TH**. ATQ209 is Panasonic's product number for the TQ2-5V. This is the *spare*, now fitted. The removed original also reads TQ2-5V (builder report, 2026-09-16).
- The 1N4148 flyback diode arched over the relay, with **both leads inserted into holes in the column-55 strips on opposite sides of the gap**. Neither lead is lifted.
- The TQ orientation bar runs along the whole column-55 short edge.

**What it does NOT show:**
- **Which row side is `a` and which is `f`.** Row letters are out of frame.
- **The diode band end, reliably.** Not legible at this angle.
- **Spring-contact quality.** Insertion is visible; grip is not.
- **Pin 1's row side.** The orientation bar marks the pin-1 *end* (column 55), not whether pin 1 is at `55a` or `55f`.

**Where the conclusions actually rest:**
- Coil polarity (pin 1 = + at `55a`): reversing the coil wiring made the contacts transfer. That is an intervention A/B, not this photo.
- Diode band at `55a`: bench report plus 0.602 V out-of-circuit diode-mode reading, and the fact that the relay picks up (a forward-biased diode across the coil would clamp it to ~0.7 V).

See `ai/journal.md` 2026-09-16 (1)–(3) and `ai/todo.md` TODO-6 / TODO-47.
