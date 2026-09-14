# J4 continuity identification — the installed jack has no switched contact

**Date:** 2026-09-13 · **Conditions:** power OFF, DMM in continuity/beep mode,
nothing else changed on the bench. Builder-performed, reported at the bench.

## Measurements, as taken

| # | Probe A | Probe B | Plug | Result |
|---|---|---|---|---|
| 1 | metal threaded barrel/body | **lug #1** | none | **BEEP** |
| 2 | metal threaded barrel/body | lug #2 | none | no beep |
| 3 | **lug #2** | **long spring/contact** | none | **BEEP** |
| 4 | **lug #2** | **long spring/contact** | **TS plug inserted** | **STILL BEEPS** |

## What these measurements establish on their own

**Measurement 1** — lug #1 is bonded to the jack body: **lug #1 = SLEEVE / GND.**

**Measurements 3 and 4 together are the decisive pair.** Lug #2 and the long
spring are continuous **both empty and with a TS plug inserted**. A switched
(shunt) contact is defined by opening on insertion. This pair does not open.

Therefore, from the measurements alone and independent of any datasheet:
**among the contacts probed, there is no switched contact.** Lug #2 and the long
spring are two parts of one conductor — the tip contact assembly.

- **lug #1** = SLEEVE / GND
- **lug #2 + long spring** = TIP (one net)
- **no shunt/switch terminal found**

## Corroborating claim — recorded as a citation, NOT independently verified here

Switchcraft lists the **#11** as *1/4" Mono 2 Conductor … Open Circuit*, circuit
schematic *"Single Open"*; a shunted variant exists as a **different part**
(e.g. **12AW11**, *"Tip is Shunt"*). **This is a datasheet claim relayed at the
bench and has not been verified against a Switchcraft document by this session.**
It explains the measurement but the measurement does not depend on it.

## Boundary of the claim

What is established: **no switched contact exists among the three probe points
tested.** Not established: that the part has no fourth contact anywhere. If a
detect contact is ever claimed to exist on this jack, it must be located and its
open-on-insertion behaviour demonstrated — a continuity pair that fails to open
is not a switch.

An alternative reading of measurement 4 — *a shunt contact that exists but failed
to actuate* (plug not fully seated, bent contact) — is not supported: under that
reading lug #2 and the spring would be separate nets that happen to touch, and
measurement 3 would have to be the shunt resting on the tip. That is possible in
principle, but it would still leave **no third net available** to wire to pin 16,
so the operational conclusion is unchanged either way.

## Immediate safety consequence

**Do NOT connect Teensy pin 16 to lug #2 or to the long spring.** Both are the
guitar TIP. `INPUT_PULLUP` would place a 22 kΩ pull-up to 3.3 V directly on the
instrument signal node, biasing it and loading it far below the ~1 MΩ target of
TODO-23. The planned SHUNT → pin 16 experiment is **withdrawn — it cannot be
performed**, because the contact it was to be wired to does not exist.
