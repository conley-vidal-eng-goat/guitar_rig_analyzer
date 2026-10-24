# Step A — sustained authoritative state with live telemetry absent

**2026-09-26.** First hardware exercise of a measurement-state transition over
the Teensy→Pi link. No wiring change, no stimulus, no generator, no injection,
no relay or route change, no Phase 9 activity.

## Artifacts

| | |
|---|---|
| UART capture | [`phase10-stepA-abort.bin`](phase10-stepA-abort.bin) |
| Bytes | **347 870** |
| **SHA-256** | `3ac52680b28f4c2a7f2d3e4ea850a94b9493b726bde60afa3deccd190ba95380` |
| USB console | [`2026-09-26-stepA-usb-console.jsonl`](2026-09-26-stepA-usb-console.jsonl) — 106 events |
| Device | `/dev/ttyAMA0`, receive-only link unchanged |
| Firmware | `dcfbffa`, v0.6.0, protocol v2 — **unmodified** |

## ⚠️ Evidence classes, kept separate

- **Artifact fact:** the file is 347 870 bytes with the SHA-256 above.
- **Artifact-derived timing:** the STATE `audio_block_counter` spans **44.498 s**.
- **NOT ESTABLISHED:** there is **no preserved `capture.sh` completion output**
  independently showing `elapsed: 45s of 45s requested`. The terminal output was
  not retained.

**The 44.498 s audio span must not be read as `capture.sh` reporting 45/45 s.**
They are different claims from different sources. The script's own duration
check therefore has no record for this run, even though the artifact strongly
suggests the capture ran essentially to completion.

## Procedural deviations — recorded, not hidden

Two things did not go as planned, and both were established from the bytes
rather than from wall-clock reasoning.

**1. The capture began AFTER `m` was issued.** The first STATE packet already
reports `ARMED` (`STATE UNKNOWN -> ARMED` at t=0.000) and there are **zero
STATUS packets**, so the `"Measuring — external stimulus"` message that `m`
emits is absent. **The planned 5 s IDLE baseline was never captured.** The
operator's intent was `m` at ~5 s into a 45 s capture; the bytes show the
opposite ordering.

**2. The ABORTED dwell was ~35 s, not the planned ~15 s.** Command timing was
driven through tool round-trips whose latency was assumed negligible and was
not — several seconds each. Consequently `x` fell outside the capture window
entirely.

**Neither is a firmware or protocol defect.** Both are procedure, and the
second accidentally produced *better* evidence for the question Step A exists
to answer.

## ★ Primary result — a direct packet-composition check

Following the ABORTED packet at byte offset **343 845**, the remaining **4 025**
captured bytes contain:

| | |
|---|---|
| STATE | **71** |
| HELLO | **35** |
| ROUTER_STATUS | **35** |
| **LIVE_FRAME** | **0** |

This is deliberately stated as a byte-offset packet census rather than as a
counter freeze or a timeline gap-heuristic result. It depends on no
interpretation: either a LIVE_FRAME appears after offset 343 845 or it does not,
and none does.

**All 71 of those subsequent STATE snapshots carry `ABORTED` with
`abort_reason TIMEOUT`. None of those 71 carries `NONE`.** The single `NONE`
interval belongs to the ABORTED packet itself, which sets the latch 502 ms
before the next snapshot arrives — see below. Stated this way so the headline
cannot be read as contradicting the documented reason-code lag.

### What that establishes

> Without STATE, the Pi would have continued receiving link traffic but lacked
> authoritative measurement-state telemetry telling it the Teensy was latched in
> ABORTED(TIMEOUT).

The 70 HELLO and ROUTER_STATUS packets are the reason the weaker phrasing
("silence indistinguishable from a dead link") is wrong and was withdrawn: the
link was demonstrably healthy throughout. **Link health and measurement state
are separable, and only STATE carries the latter.** That is TODO-57's
justification, on hardware, sustained for ~35 s.

## Observed sequence

| Audio time | Observation |
|---|---|
| t=0.000 | SESSION established → **4**; `STATE UNKNOWN -> ARMED` (already armed) |
| t=0.000 → 8.998 | **19 STATE packets reporting ARMED**; **202 LIVE_FRAME** (201 promoted + 1 pre-HELLO) ≈ 22/s |
| t=**8.998** | **ABORTED packet, reason string `"armed timeout"`**; `STATE ARMED -> ABORTED`; abort latch **SET with `reason_code NONE`** |
| t=**9.500** | `REASON CODE NONE -> TIMEOUT` — **502 ms later, exactly one STATE announce period** |
| t=9.500 → 44.498 | **71 consecutive STATE snapshots carrying ABORTED/TIMEOUT**, zero LIVE_FRAME |
| capture end | receiver state **ABORTED · latched · TIMEOUT · view=aborted** |

**LIVE_FRAME continued throughout ARMED** — 202 packets — confirming the
firmware's `IDLE | ARMED` display gate from the receiving end.

**The two-stage abort information is confirmed on hardware.** The ABORTED packet
carries the human-readable prose and sets the latch; the machine-readable code
arrives with the next STATE snapshot 502 ms later. The receiver therefore knows
*that* an abort occurred before it knows *why* in codeable form — harmless,
because the prose is immediate, and now measured rather than predicted.

## Framing

**383 frames · 0 CRC failures · 0 oversize rejects · 0 decode errors · 0
buffered at end.** Session `[4]` stable throughout. `TRANSPORT: OK`.

## Every byte accounted for — residual 0

```
LIVE   202 × 1689 = 341 178      (201 promoted + 1 pre-HELLO)
STATE   90 ×   15 =   1 350
HELLO   45 ×   47 =   2 115
ROUTER  45 ×   37 =   1 665
ABORTED  1 ×   20 =      20      ("armed timeout" = 13 B + 7 framing)
discarded         +   1 542
                  ---------
                    347 870  =  captured 347 870
```

## The timeline decision, independently validated

Byte-position time renders the **35.50 s** live-telemetry absence as **0.52 s** —
a **68× understatement**. Had the axis not been moved to the Teensy
`audio_block_counter` before this run, this capture's central observation would
have been invisible in the analysis. The synthetic test predicted a distortion;
the hardware supplied one.

## OPEN — not demonstrated

- **Post-`x` recovery ordering.** `ViewChange: 0` in the artifact: there is **no
  VIEW packet, no latch clear, no IDLE transition and no LIVE_FRAME resumption**
  in the UART evidence. The ordering of those four is **unestablished**. The USB
  console shows the firmware reached `ABORTED → IDLE`, but that is the
  producer's view and is not receiver evidence.
- A Pi **attaching during** a sticky ABORTED (it was attached throughout).
- A **deliberately suppressed or lost** ABORTED event.
- `capture.sh` duration self-report for this run.
- RESULT transport · TODO-59 atomicity at runtime · Pi→Teensy · the T1 matrix ·
  the production UI.

## Analog observations — NOT transport evidence

`peak_source −63.5 dBFS` · `peak_return −66.2 dBFS` · `tf_confidence 0.0` ·
`tf_clamped_count 0` · no clipping. Consistent with an idle instrument and no
stimulus, which is what the ARMED timeout required.

## Process rule established by this run

**A serial MCP `export_log` is temporary evidence.** It writes into the
capture directory, which `.gitignore` excludes (`.serial-logs/`). The USB
console log for this run was only preserved because it was explicitly copied
into `ai/evidence/` and hashed. **Do that immediately after any run worth
keeping** — discovering it after a valuable RESULT capture would be expensive.
