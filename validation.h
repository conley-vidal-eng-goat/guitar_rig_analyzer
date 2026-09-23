// =============================================================================
// validation.h   —   Guitar Rig Analyzer
// =============================================================================
// Known-signal validation harness — public interface.
//
// CHANGELOG v0.3.1    (last functional change — no logic changes since)
// ------------------------------------------
// Every change below is annotated with the audit finding that drove it.
//
// CHANGED [audit-1]: Added VALIDATION_SETTLE_BLOCKS as a named constant.
//   Previously it was the magic number 8 hardcoded in collectFrames().
//   It is now visible, adjustable, and documented with its dependency on
//   TF_SMOOTHING_ALPHA so that a change to the alpha does not silently
//   invalidate the settle assumption.
//
// CHANGED [audit-2]: Added raw TF accumulation fields to CollectionStats
//   (via the new RawTFStats inner struct approach — see validation.cpp).
//   collectFrames() now computes TF directly from fft_source/fft_return per
//   block rather than accumulating frame.tf_db[], which was EMA-smoothed.
//   Averaging EMA-smoothed values across blocks introduced a dependency on
//   EMA history state and the alpha constant, making two identical bench runs
//   produce slightly different mean TF values. Raw accumulation is
//   repeatable and history-independent.
//
// CHANGED [audit-3]: Added validation_runPreflightLevelCheck() to the public
//   API. The pre-flight level check was mentioned in the procedure but had no
//   corresponding code — it would have been skipped under bench pressure.
//   It is now a named, gated step that must pass before the suite runs.
//
// CHANGED [audit-4]: Corrected tf_mean comment in ValidationResult.
//   Previous comment said "stored for use by symmetry test." The symmetry
//   test runs its own fresh collections and does not read this field. The
//   correct description is: stored for external use — future SD logging,
//   baseline TF subtraction for cable characterisation.
//
// CHANGED [audit-5]: Added VALIDATION_BASELINE_PRINT_BAND_HZ constants.
//   After Test 1 passes, the baseline TF is printed to Serial in a
//   parseable CSV-like format so it can be captured and used as a zero-
//   reference for future cable characterisation. Previously there was no
//   mechanism to record the baseline — it existed only in RAM.
//
// CHANGED [audit-6]: Added TARGET_LEVEL_DBFS_MIN / MAX and
//   GATE_TO_OPERATING_LEVEL_MIN_DB to document and enforce the required
//   relationship between TF_SOURCE_GATE and the operating signal level.
//   Previously the gate and the target level were defined in separate
//   places with no stated relationship; a miscalibrated gain level could
//   push low-frequency bins below the gate, causing false NAN values.
//
// CHANGED [audit-7]: validation_runAll() prompts updated throughout.
//   Test 1 prompt removed "play guitar" — guitar is not an acceptable
//   validation stimulus. Test 4 prompt now specifies white noise and
//   explains why (pink noise rolloff reduces high-frequency energy above
//   the corner frequency, which is exactly where the slope measurement
//   needs valid bins).
//
// CHANGED [audit-8]: RC filter example corrected.
//   The 10kΩ + 10nF example previously quoted the unloaded corner (1592 Hz).
//   The loaded corner with SGTL5000 ~40kΩ input is ~1989 Hz — a 25% shift
//   that causes systematic error in the slope estimate and 2fc check if the
//   unloaded value is entered. The example now quotes the loaded corner and
//   explains the calculation.
//
// CHANGED [audit-9]: Added post-pass tolerance advisory to printResult.
//   After the initial validation suite passes with conservative tolerances,
//   the procedure calls for tightening the tolerances to reflect demonstrated
//   hardware capability. printResult() now emits an advisory when a criterion
//   passes with significant headroom (measured value < 50% of tolerance),
//   prompting the user to consider tightening the constant in validation.h.
//
// CHANGED [audit-10]: MAX_CRITERIA increased from 8 to 10.
//   The preflight check adds up to 3 criteria; the test suite was already
//   using up to 7. With the preflight now part of the same result structure,
//   8 was too tight for future expansion.
// =============================================================================


#ifndef VALIDATION_H
#define VALIDATION_H


#include <Arduino.h>
#include "config.h"
#include "audio_engine.h"


// =============================================================================
// VALIDATION CONFIGURATION
// =============================================================================


// Number of output blocks to collect per test (after settle period).
// Each block = FFT_AVERAGE_COUNT FFT results ≈ 46.4 ms at 44.1 kHz.
// 32 blocks ≈ 1.49 seconds of live data collection.
// CHANGED [todo-27]: read "≈ 92.8 ms ... ≈ 2.97 seconds", which multiplied by the
// 1024-sample WINDOW instead of the 512-sample HOP. Results arrive every hop
// (50 % overlap), so a block is 4 × 11.6 ms, not 4 × 23.2 ms.
#define VALIDATION_FRAME_COUNT   32
// CHANGED [audit-1]: VALIDATION_SETTLE_BLOCKS promoted from magic number
// inside collectFrames() to a named constant here.
//
// Before collecting statistics, this many output blocks are discarded to
// allow the EMA smoother to converge. The EMA starts at 0.0 after
// audioEngine_resetSmoothing(); if collection begins immediately, the first
// blocks are biased toward 0 dB regardless of the actual signal.
//
// DEPENDENCY ON TF_SMOOTHING_ALPHA:
// The EMA time constant = 1 / TF_SMOOTHING_ALPHA output blocks.
// Adequate settling requires at least 3× the time constant.
//   At alpha = 0.15 (default): time constant ≈ 6.7 blocks → 3× ≈ 20 blocks.
//   At alpha = 0.05:              time constant = 20 blocks    → 3× = 60 blocks.
//   At alpha = 0.30:              time constant ≈ 3.3 blocks   → 3× ≈ 10 blocks.
//
// IMPORTANT: If TF_SMOOTHING_ALPHA is changed in config.h, recalculate the
// required settle count as ceil(3.0 / TF_SMOOTHING_ALPHA) and update this
// constant accordingly. Using too few settle blocks will bias the mean TF
// toward 0 dB, making the flat loopback test pass too easily.
//
// Default 20 matches the 3× rule at alpha = 0.15 with comfortable margin.
#define VALIDATION_SETTLE_BLOCKS     20


// Frequency bounds for the validation analysis band.
// Restricted away from the full 20–20k range for two reasons:
//   Below 200 Hz: guitar pickups and bench noise sources have inconsistent
//     spectral energy in this range; many bins may be unenergised even with
//     a "broadband" signal, producing NAN values that distort statistics.
//   Above 10 kHz: cable capacitance and the SGTL5000 anti-alias filter
//     produce a natural rolloff that would cause false failures on an
//     otherwise correct loopback. The upper bound should be tightened once
//     real hardware rolloff characteristics are characterised.
#define VALIDATION_FREQ_MIN    200.0f      // Hz
#define VALIDATION_FREQ_MAX   10000.0f     // Hz


// CHANGED [audit-6]: Target operating level bounds and gate gap minimum
// added as named constants to document the required relationship between
// the signal level at the codec and TF_SOURCE_GATE.
//
// TF_SOURCE_GATE = 0.001 ≈ –60 dBFS (linear magnitude threshold).
// At –6 to –12 dBFS operating level, the gap above the gate is 48–54 dB.
// This gap must be large enough that normal spectral variation (roll-off
// at frequency extremes, signal troughs between harmonics) does not push
// individual bins below the gate during a broadband validation stimulus.
//
// If the codec PGA level is set too low (e.g. SGTL5000_LINE_IN_LEVEL = 0),
// operating level may fall to –30 dBFS, leaving only a 30 dB gap. In that
// case low-energy bins (below 300 Hz, above 8 kHz) will fall below the gate,
// producing false NAN values and a low confidence reading that causes the
// loopback test to fail even though the pipeline is working correctly.
//
// The preflight check enforces the target level window before any test runs.
#define VALIDATION_TARGET_LEVEL_MIN_DBFS           -12.0f      // Quietest acceptable peak
#define VALIDATION_TARGET_LEVEL_MAX_DBFS            -6.0f      // Loudest acceptable peak
#define VALIDATION_GATE_GAP_MIN_DB                  40.0f      // Min gap: operating level – gate level
                                                                // At –10 dBFS and gate –60 dBFS: 50 dB g


// Test 1 / Test 2 — Flat loopback tolerances.
//
// NOTE ON TIGHTENING:
// These are intentionally conservative first-pass values suitable for
// initial bench bring-up. After the suite passes with real hardware,
// record the actual measured values (printed in the test report) and
// tighten these constants to ≈2× the measured values. A validation suite
// that passes with large headroom provides less assurance than one tuned
// to the demonstrated hardware capability. See audit-9 advisory in printResult.
#define LOOPBACK_MEAN_TOLERANCE_DB      0.5f         // |mean TF| across band must be < this
#define LOOPBACK_PP_TOLERANCE_DB        2.0f         // Peak-to-peak TF swing must be < this
#define LOOPBACK_CONFIDENCE_MIN         0.50f        // Fraction of bins energised must be > this


// Test 2 — Symmetry tolerances.
#define SYMMETRY_MAX_DIFF_DB                1.0f      // Max per-bin A-B difference
#define SYMMETRY_MIN_SHARED_BIN_FRAC        0.50f     // Min fraction of bins valid in both passes


// Test 3 — Known gain offset tolerance.
#define GAIN_OFFSET_TOLERANCE_DB     1.0f


// Test 4 — Known filter tolerances.
//
// CHANGED [audit-8]: RC filter example corrected in validation_runAll() prompt.
// The unloaded corner frequency for 10kΩ + 10nF is 1592 Hz. The loaded corner
// with SGTL5000 ~40kΩ input impedance in parallel with the capacitor is:
//   R_eff = 10k || 40k = 8kΩ
//   fc_loaded = 1 / (2π × 8000 × 10e-9) ≈ 1989 Hz
// A 25% shift. Entering the unloaded value causes systematic error in the
// slope estimate and 2fc attenuation check. The prompt now quotes the loaded
// value. If the filter output is buffered (recommended), use the unloaded value.
#define FILTER_SLOPE_TOLERANCE_DBOCTAVE        2.0f
#define FILTER_2FC_MAX_DELTA_DB               -4.0f         // Signed dB — MUST be negative
#define FILTER_MONO_STEP_DB                    0.5f         // Upward step ≥ this = bump
#define FILTER_MONO_MAX_BUMPS                  5            // Max bumps — hardware tuning target


// =============================================================================
// RESULT STRUCTURES
// =============================================================================


// Per-criterion result.
struct ValidationCriterion {
     const char* name;
     float          measured;
     float          tolerance;
     bool           passed;
     const char* units;
};


// CHANGED [audit-10]: MAX_CRITERIA increased from 8 to 10.
// The preflight check adds criteria; 8 was too tight for future expansion.
#define MAX_CRITERIA      10


struct ValidationResult {
     const char*                test_name;
     bool                       all_passed;
     ValidationCriterion        criteria[MAX_CRITERIA];
     int                        criterion_count;
     uint32_t                   frames_collected;
     uint32_t                   duration_ms;


     // CHANGED [audit-4]: Comment corrected.
     // Previous: "stored for use by symmetry test."
     // Corrected: the symmetry test runs its own independent collections and
     // does NOT read this field. This array is stored for EXTERNAL use:
     //      - Future SD logging (baseline TF reference file)
     //      - Cable characterisation: subtract this from cable measurements to
     //        isolate cable contribution from fixture contribution
     //      - Re-printing or post-processing without re-running the test
     float tf_mean[FFT_BINS];
};


// =============================================================================
// PUBLIC API
// =============================================================================


// -----------------------------------------------------------------------------
// validation_init()
// Prepares internal state. Call once from setup() after both engines init.
// Prints analysis band, frame count, and settle period to Serial.
// -----------------------------------------------------------------------------
void validation_init();


// -----------------------------------------------------------------------------
// CHANGED [audit-3]: validation_runPreflightLevelCheck() added.
// Previously the pre-flight level check existed only in the procedure document
// and comments — there was no code to enforce it. Under bench pressure it
// would be skipped. This function makes it a gated, named step.
//
// Checks:
//   1. SOURCE_NODE peak level is within VALIDATION_TARGET_LEVEL_MIN/MAX_DBFS
//   2. RETURN_NODE peak level is within the same window
//   3. The gap between operating level and TF_SOURCE_GATE is >= GATE_GAP_MIN_DB
//
// Must pass before the validation suite runs. If it fails, the most likely
// cause is SGTL5000_LINE_IN_LEVEL being wrong for the connected signal source.
// Adjust the level and re-run until this passes.
// -----------------------------------------------------------------------------
ValidationResult validation_runPreflightLevelCheck();


// -----------------------------------------------------------------------------
// validation_runAll()
// Runs preflight + all four tests in sequence.
// Returns true only if ALL tests (including preflight) passed.
// -----------------------------------------------------------------------------
bool validation_runAll();


// Individual test runners — callable directly for targeted re-runs.
ValidationResult validation_runFlatLoopback();
ValidationResult validation_runChannelSwapSymmetry();
ValidationResult validation_runKnownGainOffset(float expected_offset_db);
ValidationResult validation_runKnownFilter(float corner_freq_hz,
                                           float expected_slope_db_per_octave);


// -----------------------------------------------------------------------------
// validation_printResult(result)
// CHANGED [audit-9]: Now emits a tighten-tolerances advisory when a criterion
// passes with measured value < 50% of tolerance. This prompts the user to
// update the constants in validation.h after initial bring-up, so that future
// runs catch regressions that would still pass the conservative first-pass values.
// -----------------------------------------------------------------------------
void validation_printResult(const ValidationResult& result);


// -----------------------------------------------------------------------------
// CHANGED [audit-5]: validation_printBaseline() added.
// After Test 1 passes, prints the full mean TF array to Serial in a parseable
// format (CSV-compatible: "baseline_tf_hz,baseline_tf_db") so the data can be
// captured from the Serial log and used as a zero-reference for cable
// characterisation. Previously this data existed only in RAM and was lost
// when the next test ran.
// -----------------------------------------------------------------------------
void validation_printBaseline(const ValidationResult& loopback_result);
// -----------------------------------------------------------------------------
// CHANGED [todo-48]: validation_waitForUser() now returns a CONSENT VERDICT.
//
// Was: void, and it read-and-discarded every byte — so a keystroke meant as
// "cancel" was consumed as consent and started a test on a nonconforming
// fixture. It now captures the first byte.
//
// Returns true  on CR, LF, 'y' or 'Y'  — proceed.
// Returns false on anything else       — the caller MUST NOT run its test.
//
// 'y' is accepted alongside CR/LF deliberately: a serial monitor set to
// "No Line Ending" sends nothing on Enter, so a CR/LF-only rule would hang the
// prompt with no way out. The printed prompt states both.
//
// Blocks while pumping audio_capture, so the LIVE FFT consumer slot stays
// drained during the wait (unchanged from the previous behaviour).
// -----------------------------------------------------------------------------
bool validation_waitForUser(const char* prompt);


// -----------------------------------------------------------------------------
// CHANGED [todo-48]: validation_preflightGate() — the shared entry gate.
//
// validation_runPreflightLevelCheck() previously had ONE caller, runAll(). The
// single-test commands '1'–'4' ran their test directly, so a dead SOURCE showed
// up as a NaN table inside a result report instead of a clear preflight failure.
// Every entry point now gates on this function.
//
// return_is_attenuated:
//   false — plain loopback fixture, Rig Send -> Rig Return TS (preflight,
//           test 1, test 2). SOURCE and RETURN carry the same signal, so
//           the FULL preflight applies.
//   true  — test 3 (resistive pad) and test 4 (RC low-pass). These fixtures
//           attenuate RETURN BY DESIGN, and preflight requires RETURN inside a
//           6 dB-wide window. Gating on the RETURN criteria would fail a
//           CORRECT fixture, so only the SOURCE-side criteria are gated on.
//
// Returns true when the test may proceed. Prints the reason when it may not.
// -----------------------------------------------------------------------------
bool validation_preflightGate(bool return_is_attenuated);


// -----------------------------------------------------------------------------
// ADDED 2026-09-22 (journal (3)): Test 3's expected-offset entry, owned in one
// place so both the 'v' suite and the standalone '3' command share one policy.
//
// Returns the operator's EXPECTED INSTALLED SOURCE->RETURN OFFSET in dB — the
// offset of the whole path as validation_runKnownGainOffset() measures it, NOT
// the unloaded divider ratio. THERE IS NO DEFAULT: empty, malformed, partially
// numeric and overlength entries re-prompt; an explicit 0 is valid. Blocks until
// a valid number is entered; declining happens earlier, at the consent prompt.
// -----------------------------------------------------------------------------
float validation_promptExpectedOffset();


#endif // VALIDATION_H
