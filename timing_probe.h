// =============================================================================
// timing_probe.h  —  Guitar Rig Analyzer
// =============================================================================
// T1 ACCEPTANCE HARNESS.
//
// Exists to answer exactly one question, and it is not a question about UART:
//
//   *** Can the presentation transport become unavailable without measurably
//       perturbing the Teensy's audio/measurement timing? ***
//
// Authority: docs/adr/ADR-001-display-architecture.md (the failure hierarchy),
// docs/pi_link_protocol_audit.md finding T1 (the open question),
// docs/breadboard_bringup_v3.md Phase 10 steps 11-12 (the procedure).
//
// THE FAILURE HIERARCHY THIS MEASURES
// -----------------------------------
//   renderer degradation  <  transport loss  <  measurement disturbance
//
// A dropped frame is acceptable. A delayed or corrupted measurement is not. This
// module measures the right-hand side of that inequality — the acquisition path —
// because that is the side that must not move.
//
// WHY A SEPARATE MODULE, AND WHY IT MEASURES ACQUISITION RATHER THAN TRANSPORT
// ---------------------------------------------------------------------------
// The tempting mistake is to instrument the transport and declare victory when
// presentation_*() call times are small. That is NOT the pass condition, and this
// module is shaped to make the distinction hard to fudge:
//
//   A microsecond-fast presentation call can still disturb the instrument
//   indirectly — through interrupt load, UART ISR activity, DMA contention, or
//   buffer servicing. None of that shows up in a call-duration figure.
//
// So the pass condition is comparative, not absolute: acquisition timing under
// DISPLAY_TARGET_PI must be INDISTINGUISHABLE from the same metrics captured
// under DISPLAY_TARGET_NONE. There is no threshold to argue about — the control
// run is the threshold.
//
// This matters more here than in a typical embedded project because the firmware
// is built around a single capture owner and a single canonical timebase (the
// audio block counter). Perturbing that layer compromises far more than the
// display: every time-sensitive operation in the system references it.
//
// PROCEDURE (see Phase 10 for the full version)
// ---------------------------------------------
//   Run 1  DISPLAY_TARGET_NONE                      <- the control
//   Run 2  DISPLAY_TARGET_PI, Pi reading normally
//   Run 3  DISPLAY_TARGET_PI, Pi reader STOPPED     (kill -STOP its process)
//   Run 4  DISPLAY_TARGET_PI, cable pulled mid-RESULT
//
// Identical window length, identical signal conditions. Press 'T' at the end of
// each and keep the output verbatim in ai/journal.md. The report is emitted as
// stable key=value lines specifically so the four runs can be diffed mechanically
// rather than eyeballed.
// =============================================================================

#ifndef TIMING_PROBE_H
#define TIMING_PROBE_H

#include <Arduino.h>
#include "config.h"

// -----------------------------------------------------------------------------
// timingProbe_reset()
// Clears all accumulators and starts a new measurement window. Call at the start
// of each of the four runs so windows are comparable.
// -----------------------------------------------------------------------------
void timingProbe_reset();

// -----------------------------------------------------------------------------
// timingProbe_noteBlock(output_block_number)
// Call ONCE per processed analysis block, from the main loop, as early as
// possible after the block is recognised.
//
// Records the block-to-block period (mean / max / min) and detects SKIPPED
// blocks: the canonical timebase is monotonic, so a gap greater than 1 in
// output_block_number means an analysis block was produced that the loop never
// processed. That is the single most direct evidence of measurement disturbance
// available without touching the capture layer.
// -----------------------------------------------------------------------------
void timingProbe_noteBlock(uint32_t output_block_number);

// -----------------------------------------------------------------------------
// timingProbe_noteLoopIteration(duration_us)
// Call once per loop() iteration with the measured duration of the whole body.
//
// Catches anything that blocks, wherever it lives — not just presentation calls.
// A transport layer that is individually fast but collectively starves the loop
// shows up here and nowhere else.
// -----------------------------------------------------------------------------
void timingProbe_noteLoopIteration(uint32_t duration_us);

// -----------------------------------------------------------------------------
// timingProbe_report()
// Emits the fixed-format T1 report to USB Serial, including the transport
// figures from the active presentation backend so one paste captures both sides
// of the comparison.
//
// Prints the pass condition as a reminder, because the whole point is that a
// small transport number is not a pass.
// -----------------------------------------------------------------------------
void timingProbe_report();

#endif // TIMING_PROBE_H
