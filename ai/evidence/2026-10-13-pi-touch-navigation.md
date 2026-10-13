# Touch navigation works — one finger, one tab change

**2026-10-13.** The last gap in the shell's Pi validation, and the one that could
not be closed over SSH.

**No firmware change, no protocol change, no wiring change, no measurement
initiated.** Teensy untouched; the Tk UI still held `/dev/ttyAMA0` on pid 1514
throughout. Every frame is the pinned `phase10-result-1khz.bin` fixture.

## What was run

The committed client, unpatched — `main.js` `b1de238b…`, `fingerprint_split.js`
`5b2cf5cf…`, hash-identical to the repository, with **no FPS probe and no default-tab
override**. `let active = "live";` as committed. Launched detached with `setsid`
so it outlived the SSH session.

## The observation

| | |
|---|---|
| Before | [`…-before-tap.png`](2026-10-13-pi-touch-before-tap.png) — **LIVE** selected: cyan label, cyan top bar, the two LIVE cards on screen |
| Action | **One finger, one tap on the TONE button.** Reported by the operator |
| After | [`…-after-tap.png`](2026-10-13-pi-touch-after-tap.png) — **TONE** selected: cyan label and top bar moved to TONE, LIVE grey, the ring and legend on screen |

**Verified from the pixels, not from the report.** Both frames were captured with
`grim` off the live compositor; the selected-tab styling is read from the image.

**A second thing the pair shows, unplanned.** The ring's two amber markers sit at
different angles in the two captures. The orbit animation is running, so
`activate()` → `resize()` → `resume()` restarted a render loop that had never been
started, on a container that had been `display:none` since page load. That is
TODO-80's fix and the inactive-view pause both exercised by the tap.

## What this establishes, at its true strength

**A tap on the navigation bar changes the view on the physical touchscreen.**
The Goodix capacitive panel delivers a touch, Chromium turns it into a `click`,
and the shell routes it. 180 × 104 px targets were hit on the first attempt.

## What it does NOT establish

- **One tab, one direction.** LAB and INFO were not tapped. Returning to LIVE was
  not tapped.
- **Not swipe.** The fingerprint's drag-to-orbit is untested by touch.
- **Not sustained interaction.** One tap, not a session.
- **Nothing about measurement.** Fixture replay; the Teensy was not measuring.

ADR-005 §2 is unchanged — one of four conditions met, and the Tk UI still ships.
