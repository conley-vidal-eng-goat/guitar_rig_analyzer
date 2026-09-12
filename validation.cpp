// =============================================================================
// validation.cpp   —   Guitar Rig Analyzer
// =============================================================================
// Known-signal validation harness — implementation.
// See validation.h for the full changelog of audit-driven changes.
//
// KEY ARCHITECTURAL CHANGE IN THIS REVISION [audit-2]
// ----------------------------------------------------
// collectFrames() previously accumulated frame.tf_db[], which is the
// EMA-smoothed transfer function. Averaging EMA-smoothed values across
// blocks is incorrect for a validation harness because:
//
//   1. The result depends on the EMA history at the start of collection.
//      Two identical bench runs with different prior signal histories
//      produce different mean TF values even if the physical signal is
//      identical. This is not repeatable.
//
//   2. The result depends on TF_SMOOTHING_ALPHA. A tighter alpha produces
//      a smoother curve but a slower-converging mean; the settle period
//      would need to be tuned alongside the alpha, which couples two
//      independent parameters.
//
// The fix: collectFrames() now accumulates fft_source[] and fft_return[]
// (the averaged linear magnitudes, which are history-free per block) and
// computes the TF directly from their means. This is independent of EMA
// state and produces the same result regardless of what the analyzer was
// doing before the test was invoked.
//
// The EMA is still used for the live display (that is its purpose). It is
// bypassed entirely in the validation path.
// =============================================================================


#include "validation.h"
#include "audio_capture.h"     // for audioCap_update() in polling loops
#include "presentation.h"      // presentation boundary — NOT display_engine
                               // directly. The harness must report through
                               // whichever renderer is selected; see
                               // docs/adr/ADR-001-display-architecture.md.
#include <math.h>
#include <stdlib.h>


// =============================================================================
// MODULE-PRIVATE TYPES
// =============================================================================


// CHANGED [audit-2]: CollectionStats now accumulates linear FFT magnitudes
// (fft_source and fft_return) instead of EMA-smoothed tf_db values.
// The TF is computed from the accumulated means at the end of collection,
// not averaged from smoothed per-block TF values.
//
// Why double for the accumulators?
//    fft_source/fft_return values are float in [0.0, 1.0].
//    Summing 32+ float values near the precision boundary can accumulate
//    rounding error. double gives 15 significant digits vs float's 7,
//    which is more than adequate for 32-block sums.
struct CollectionStats {
     double     accum_source[FFT_BINS];    // Sum of fft_source[] across blocks
     double     accum_return[FFT_BINS];    // Sum of fft_return[] across blocks
     int        valid_count [FFT_BINS];    // Blocks where source was above gate
     float      mean_tf     [FFT_BINS];    // Computed after collection: TF in dB
     float      mean_confidence;           // Mean tf_confidence across blocks
     uint32_t blocks_collected;
};


// =============================================================================
// PRIVATE HELPERS
// =============================================================================


static bool binInAnalysisBand(int bin) {
     float f = audioEngine_binToHz(bin);
     return (f >= VALIDATION_FREQ_MIN && f <= VALIDATION_FREQ_MAX);
}


// Keep capture/live queues drained while waiting for numeric Serial input
// during validation prompts. This avoids stale live blocks after long setup
// pauses without introducing heap-allocating String reads.
static float readSerialFloatWithAudioPump(float default_value) {
    char buf[24];
    uint8_t len = 0;
    AudioFrame discard;

    while (!Serial.available()) {
        audioCap_update();
        if (audioCap_isBlockFresh(AudioConsumer::LIVE)) {
            audioEngine_update(&discard);
        }
        delay(5);
    }

    bool done = false;
    while (!done) {
        if (Serial.available()) {
            char c = (char)Serial.read();
            if (c == '\r') continue;
            if (c == '\n') {
                done = true;
            } else if (len < sizeof(buf) - 1) {
                buf[len++] = c;
            }
        } else {
            audioCap_update();
            if (audioCap_isBlockFresh(AudioConsumer::LIVE)) {
                audioEngine_update(&discard);
            }
            delay(5);
        }
    }
    buf[len] = '\0';
    return (len > 0) ? atof(buf) : default_value;
}


// -----------------------------------------------------------------------------
// collectFrames(count, stats)
//
// CHANGED [audit-2]: Accumulates fft_source[] and fft_return[] directly
// instead of frame.tf_db[]. TF is computed from means after collection.
//
// CHANGED [audit-1]: Settle period now uses VALIDATION_SETTLE_BLOCKS
// constant (defined in validation.h) instead of the magic number 8.
// See validation.h for the dependency on TF_SMOOTHING_ALPHA.
//
// Gate logic: a block contributes to bin k's accumulation only if
// fft_source[k] >= TF_SOURCE_GATE. This mirrors the gate in the audio
// engine but is applied to the raw per-block FFT, not to the EMA output.
// Bins with zero valid blocks produce NAN in mean_tf[].
// -----------------------------------------------------------------------------
// Returns true on success, false if a ROUTE_CHANGED event aborted collection.
// Caller must treat a false return as an invalid result.
static bool collectFrames(int count, CollectionStats* stats) {


     for (int k = 0; k < FFT_BINS; k++) {
           stats->accum_source[k] = 0.0;
           stats->accum_return[k] = 0.0;
    stats->valid_count [k] = 0;
    stats->mean_tf        [k] = 0.0f;
}
stats->mean_confidence     = 0.0f;
stats->blocks_collected = 0;


// CHANGED [audit-1]: Use named constant instead of magic number 8.
// VALIDATION_SETTLE_BLOCKS is defined in validation.h alongside the
// documentation of its dependency on TF_SMOOTHING_ALPHA.
int settle_remaining = VALIDATION_SETTLE_BLOCKS;
int collected           = 0;
AudioFrame frame;

// FIX [no-audio-timeout]: bound the collection loop with a wall-clock
// deadline. Without this, a stuck codec or unresponsive Audio Library
// causes collectFrames() to spin forever. Budget: expected duration of
// (count + settle) blocks plus 50% margin, with a 30-second hard ceiling
// so even pathologically slow configurations cannot hang the device.
uint32_t expected_ms = (uint32_t)((count + VALIDATION_SETTLE_BLOCKS) *
                                  FFT_AVERAGE_COUNT * FFT_SIZE * 1000UL /
                                  (uint32_t)SAMPLE_RATE);
uint32_t deadline_ms = millis() + expected_ms + expected_ms / 2 + 1000;
if (expected_ms > 30000UL) deadline_ms = millis() + 30000UL;


while (collected < count) {
    if ((int32_t)(millis() - deadline_ms) >= 0) {
        Serial.printf("[Validation] ABORT: collectFrames timed out after %lu ms "
                      "(%d/%d blocks)\n",
                      (unsigned long)expected_ms, collected, count);
        return false;
    }
    // Drive audio_capture before checking consumer freshness.
    // audioCap_update() is what posts new AudioRawBlocks; without it,
    // audioEngine_update() will always see stale data and spin forever.
    // This mirrors the main loop structure (audioCap_update first, then consumers).
    AudioCaptureEvent cap_ev = audioCap_update();
    if (cap_ev == AudioCaptureEvent::CLIP_SOURCE ||
        cap_ev == AudioCaptureEvent::CLIP_RETURN) {
        Serial.println("[Validation] WARNING: clipping detected during collection.");
    }
    // Abort on route change — frames before/after cannot be averaged together.
    if (cap_ev == AudioCaptureEvent::ROUTE_CHANGED) {
        Serial.println("[Validation] ABORT: route changed mid-collection — test invalid.");
        return false;
    }
    if (!audioEngine_update(&frame)) continue;


    if (settle_remaining > 0) {
        settle_remaining--;
        continue;
    }


    // CHANGED [audit-2]: Accumulate raw FFT magnitudes, not tf_db.
    // Apply the source gate per-bin: only accumulate bins where the
    // source has enough energy for the TF to be meaningful.
    for (int k = 0; k < FFT_BINS; k++) {
        float src = frame.fft_source[k];
        float ret = frame.fft_return[k];
        if (!isfinite(src) || !isfinite(ret)) continue;
        if (src >= TF_SOURCE_GATE) {
            stats->accum_source[k] += (double)src;
            stats->accum_return[k] += (double)ret;
            stats->valid_count [k]++;
        }
    }
          stats->mean_confidence      += frame.tf_confidence;
          stats->blocks_collected++;
          collected++;
    }


    if (stats->blocks_collected > 0) {
          stats->mean_confidence /= (float)stats->blocks_collected;
    }


    // CHANGED [audit-2]: Compute mean TF from accumulated linear magnitudes.
    // This is independent of EMA history and TF_SMOOTHING_ALPHA.
    // H_dB[k] = 20 * log10( mean_return[k] / mean_source[k] )
    for (int k = 0; k < FFT_BINS; k++) {
          if (stats->valid_count[k] == 0) {
                  stats->mean_tf[k] = NAN;
                  continue;
          }
          double mean_src = stats->accum_source[k] / (double)stats->valid_count[k];
          double mean_ret = stats->accum_return[k] / (double)stats->valid_count[k];
          // Floor return at 1e-9 to avoid log(0) on fully-attenuated bins.
          if (mean_ret < 1e-9) mean_ret = 1e-9;
          stats->mean_tf[k] = (float)(20.0 * log10(mean_ret / mean_src));
    }
    return true;
}


// -----------------------------------------------------------------------------
// computeBandStats — unchanged from v0.3.0
// -----------------------------------------------------------------------------
static void computeBandStats(const float* mean_tf,
                                   float* out_mean, float* out_pp,
                                   float* out_min,   float* out_max) {
    float sum = 0.0f, mn = 1e9f, mx = -1e9f;
    int       n     = 0;
    for (int k = 0; k < FFT_BINS; k++) {
          if (!binInAnalysisBand(k)) continue;
          float v = mean_tf[k];
          if (isnan(v)) continue;
          sum += v;
          if (v < mn) mn = v;
          if (v > mx) mx = v;
          n++;
    }
    if (n == 0) {
          *out_mean = NAN; *out_pp = NAN; *out_min = NAN; *out_max = NAN;
    } else {
          *out_mean = sum / (float)n;
          *out_pp      = mx - mn;
          *out_min     = mn;
          *out_max     = mx;
    }
}


// -----------------------------------------------------------------------------
// estimateSlope — unchanged from v0.3.0
// Least-squares fit in log2-frequency space. Returns dB/octave.
// Returns NAN if fewer than 4 valid bins exist above the cutoff.
// -----------------------------------------------------------------------------
static float estimateSlope(const float* mean_tf, float above_freq_hz) {
    float sum_x = 0, sum_y = 0, sum_xx = 0, sum_xy = 0;
    int     n        = 0;
    for (int k = 0; k < FFT_BINS; k++) {
          float f = audioEngine_binToHz(k);
          if (f < above_freq_hz || f > VALIDATION_FREQ_MAX) continue;
          float v = mean_tf[k];
          if (isnan(v)) continue;
          float x = log2f(f);
          sum_x     += x; sum_y     += v;
          sum_xx += x * x; sum_xy += x * v;
          n++;
    }
    if (n < 4) return NAN;
    float denom = (float)n * sum_xx - sum_x * sum_x;
    if (fabsf(denom) < 1e-9f) return NAN;
    return ((float)n * sum_xy - sum_x * sum_y) / denom;
}


// -----------------------------------------------------------------------------
// addCriterion — unchanged from v0.3.0
// -----------------------------------------------------------------------------
static void addCriterion(ValidationResult* result, const char* name,
                               float measured, float tolerance,
                               bool passed, const char* units) {
    if (result->criterion_count >= MAX_CRITERIA) {
          Serial.println("[Validation] WARNING: MAX_CRITERIA exceeded.");
          return;
    }
    int i = result->criterion_count++;
    result->criteria[i] = { name, measured, tolerance, passed, units };
    if (!passed) result->all_passed = false;
}


// -----------------------------------------------------------------------------
// initResult — unchanged from v0.3.0
// -----------------------------------------------------------------------------
static void initResult(ValidationResult* result, const char* name) {
    result->test_name           = name;
    result->all_passed          = true;
    result->criterion_count     = 0;
    result->frames_collected = 0;
    result->duration_ms         = 0;
    memset(result->criteria, 0, sizeof(result->criteria));
    memset(result->tf_mean,     0, sizeof(result->tf_mean));
}


// =============================================================================
// PUBLIC: validation_init()
// =============================================================================
void validation_init() {
    // CHANGED [audit-1]: Settle period now printed using the named constant
    // rather than the previously hardcoded value of 8.
    Serial.println("[Validation] Harness ready       (v0.5.0).");
    Serial.printf ("[Validation] Analysis band: %.0f – %.0f Hz\n",
                   VALIDATION_FREQ_MIN, VALIDATION_FREQ_MAX);
    Serial.printf ("[Validation] Collection: %d blocks (~%.1f s) + %d settle blocks (~%.1f s)\n",
                   VALIDATION_FRAME_COUNT,
                   (float)VALIDATION_FRAME_COUNT   * FFT_AVERAGE_COUNT * FFT_SIZE / SAMPLE_RATE,
                   VALIDATION_SETTLE_BLOCKS,
                   (float)VALIDATION_SETTLE_BLOCKS * FFT_AVERAGE_COUNT * FFT_SIZE / SAMPLE_RATE);
    Serial.printf ("[Validation] Target level: %.0f to %.0f dBFS        "
                   "Gate gap min: %.0f dB\n",
                   VALIDATION_TARGET_LEVEL_MIN_DBFS,
                   VALIDATION_TARGET_LEVEL_MAX_DBFS,
                   VALIDATION_GATE_GAP_MIN_DB);
    // CHANGED [audit-2]: Notify that raw FFT accumulation is used, not EMA.
    Serial.println("[Validation] TF computed from raw FFT means (EMA bypassed).");
}


// =============================================================================
// PUBLIC: validation_printResult()
// CHANGED [audit-9]: Tighten-tolerances advisory added for passing criteria
// with large headroom (measured < 50% of tolerance).
// =============================================================================
void validation_printResult(const ValidationResult& r) {
    Serial.println();
    Serial.println("┌─────────────────────────────────────────────────┐");
    Serial.printf ("│     TEST: %-41s│\n", r.test_name);
    Serial.printf ("│     Result: %-6s    Frames: %4lu   Duration: %5lums   │\n",
                   r.all_passed ? "PASS" : "FAIL",
                   r.frames_collected, r.duration_ms);
    Serial.println("├──────────────────────────────────────┬──────────┤");
    Serial.println("│ Criterion                                    │   Result   │");
    Serial.println("├──────────────────────────────────────┼──────────┤");


    bool any_headroom = false;
    for (int i = 0; i < r.criterion_count; i++) {
        const ValidationCriterion& c = r.criteria[i];
        char meas_str[16];
        if (isnan(c.measured))
               snprintf(meas_str, sizeof(meas_str), "     NAN");
        else
               snprintf(meas_str, sizeof(meas_str), "%+6.2f", c.measured);


        Serial.printf("│ %-36s │ %s %-3s %s │\n",
                         c.name, meas_str, c.units,
                         c.passed ? "   PASS" : "   FAIL");


        // CHANGED [audit-9]: Flag criteria with large pass headroom.
        // "Large headroom" = measured value < 50% of tolerance AND the
        // criterion passed. This prompts the user to tighten the tolerance
        // constant after initial bring-up so future runs catch regressions
        // that would still pass the conservative first-pass value.
        // We only flag positive tolerances (absolute comparisons); skip
        // negative-valued thresholds (FILTER_2FC_MAX_DELTA_DB) and
        // informational criteria (tolerance == measured).
        if (c.passed && c.tolerance > 0.0f && !isnan(c.measured)
               && fabsf(c.measured) < 0.5f * c.tolerance) {
               any_headroom = true;
        }
    }
    Serial.println("└──────────────────────────────────────┴──────────┘");


    // CHANGED [audit-9]: Post-pass advisory for tolerance tightening.
    if (r.all_passed && any_headroom) {
        Serial.println("[Validation] ADVISORY: One or more criteria passed with");
        Serial.println("[Validation] >50% headroom. Consider tightening the");
        Serial.println("[Validation] corresponding constants in validation.h to");
        Serial.println("[Validation] reflect demonstrated hardware capability.");
        Serial.println("[Validation] A tighter tolerance catches future regressions.");
    }
    Serial.println();
}


// =============================================================================
// PUBLIC: validation_printBaseline()
// CHANGED [audit-5]: New function. Prints the mean TF from a loopback result
// in CSV format so the data can be captured from the Serial log and used as
// a zero-reference for future cable characterisation.
//
// Format (one line per bin, only analysis-band bins):
//       baseline_hz,baseline_tf_db
//       200.0,+0.03
//       243.1,-0.12
//       ...
//
// To capture: in the Arduino Serial Monitor, enable "Show Timestamp" and
// copy the lines between the START/END markers into a .csv file.
// =============================================================================
void validation_printBaseline(const ValidationResult& loopback_result) {
     if (!loopback_result.all_passed) {
               Serial.println("[Validation] Baseline not printed — test did not pass.");
               return;
     }
     Serial.println("\n[Validation] === BASELINE TF START ===");
     Serial.println("baseline_hz,baseline_tf_db");
     for (int k = 0; k < FFT_BINS; k++) {
               if (!binInAnalysisBand(k)) continue;
               float f    = audioEngine_binToHz(k);
               float tf = loopback_result.tf_mean[k];
               if (isnan(tf)) {
                   Serial.printf("%.1f,NaN\n", f);
               } else {
                   Serial.printf("%.1f,%+.4f\n", f, tf);
               }
     }
     Serial.println("[Validation] === BASELINE TF END ===\n");
     Serial.println("[Validation] Copy the lines between START/END markers to");
     Serial.println("[Validation] a .csv file for cable characterisation reference.");
}


// =============================================================================
// PUBLIC: validation_waitForUser()
// Hardened in v0.3.0 with 30 ms post-flush delay. Unchanged through v0.5.0.
// =============================================================================
void validation_waitForUser(const char* prompt) {
     Serial.println();
     Serial.println(">>> WAITING FOR USER <<<");
     Serial.println(prompt);
     Serial.println(">>> Press Enter to continue <<<");
     presentation_status("VALIDATION: waiting — see Serial");
     while (Serial.available()) Serial.read();

     // FIX [drain-audio]: previously this loop just delay(10)'d. While the
     // user reads the prompt and decides whether to press Enter, FFT-path
     // blocks accumulate in the live consumer slot with no reader — for a
     // multi-second wait, the next collection would see those stale blocks
     // as fresh. We now pump audio_capture on every iteration so the
     // LIVE FFT path stays drained.
     //
     // SCOPE NOTE: audioCap_update() reads from the live FFT objects only.
     // It does NOT drain the precision AudioRecordQueue (that queue is
     // drained by measurement_engine via audioCap_getRawSamples()). Current
     // validation flow never calls waitForUser() while a precision capture
     // is armed, so this is sufficient. If a future test ever arms the raw
     // queue and then prompts the user, add explicit queue draining here.
     AudioFrame discard;
     while (!Serial.available()) {
         audioCap_update();
         if (audioCap_isBlockFresh(AudioConsumer::LIVE)) {
             // Consume and discard — keep the live consumer slot drained.
             audioEngine_update(&discard);
         }
         delay(5);
     }
     delay(30);
     while (Serial.available()) Serial.read();

     // One more drain pass after the user-interaction settles, so the next
     // measurement starts from a clean state.
     audioCap_update();
     if (audioCap_isBlockFresh(AudioConsumer::LIVE)) {
         audioCap_markConsumed(AudioConsumer::LIVE);
     }
}
// =============================================================================
// CHANGED [audit-3]: PREFLIGHT LEVEL CHECK — new function.
//
// Previously this check existed only in the procedure document. Under bench
// pressure it would have been skipped. Making it a named, gated function
// ensures it runs and produces a structured pass/fail result before any
// test consumes codec data.
//
// What it checks:
//    1. SOURCE_NODE peak is within the target level window
//          [VALIDATION_TARGET_LEVEL_MIN_DBFS, VALIDATION_TARGET_LEVEL_MAX_DBFS]
//    2. RETURN_NODE peak is within the same window
//    3. The gap between the measured operating level and TF_SOURCE_GATE
//          is at least VALIDATION_GATE_GAP_MIN_DB (guards against a miscalibrated
//          gain level pushing low-energy bins below the gate)
//    4. Neither channel is clipping
//
// Collection: uses 4 output blocks (no settle needed — peak measurement
// is not EMA-dependent). Reports the mean peak level over those blocks.
//
// If this fails: adjust SGTL5000_LINE_IN_LEVEL in config.h and recompile,
// or reduce the signal generator output level if level is too high.
// =============================================================================
ValidationResult validation_runPreflightLevelCheck() {


     ValidationResult result;
     initResult(&result, "Preflight Level Check");
     presentation_status("PREFLIGHT: checking signal levels...");
     Serial.println("\n[Validation] Preflight Level Check");
     Serial.printf ("[Validation] Target: %.0f to %.0f dBFS      Gate gap: %.0f dB min\n",
                       VALIDATION_TARGET_LEVEL_MIN_DBFS,
                       VALIDATION_TARGET_LEVEL_MAX_DBFS,
                       VALIDATION_GATE_GAP_MIN_DB);


     // Collect 4 blocks — enough for stable peak reading without a full settle.
     // Peak measurement uses AudioAnalyzePeak which is not EMA-dependent.
     const int LEVEL_CHECK_BLOCKS = 4;
     float sum_src = 0.0f, sum_ret = 0.0f;
     bool     any_src_clip = false, any_ret_clip = false;
     int      collected = 0;
     AudioFrame frame;
     uint32_t t_start = millis();


     // FIX [no-audio-timeout]: bound the preflight wait. Expected duration is
     // ~4 blocks * ~93 ms ~= 370 ms; allow 2 s before declaring "no audio"
     // so a stuck codec or unresponsive Audio Library cannot hang the device.
     uint32_t pre_deadline_ms = millis() + 2000UL;
     while (collected < LEVEL_CHECK_BLOCKS) {
            if ((int32_t)(millis() - pre_deadline_ms) >= 0) {
                Serial.println("[Validation] PREFLIGHT ABORT: no audio blocks in 2 s.");
                result.all_passed = false;
                return result;
            }
            // Drive audio_capture first (same pattern as collectFrames()).
            // Abort on ROUTE_CHANGED — level data from mixed topologies is invalid.
    AudioCaptureEvent cap_ev = audioCap_update();
    if (cap_ev == AudioCaptureEvent::ROUTE_CHANGED) {
        Serial.println("[Validation] PREFLIGHT ABORT: route changed mid-collection.");
        result.all_passed = false;
        return result;
    }
    if (!audioEngine_update(&frame)) continue;
    sum_src += frame.peak_source_dbfs;
    sum_ret += frame.peak_return_dbfs;
    if (frame.source_clipping) any_src_clip = true;
    if (frame.return_clipping)     any_ret_clip = true;
    collected++;
}


result.frames_collected = collected;
result.duration_ms         = millis() - t_start;


float mean_src_dbfs = sum_src / (float)collected;
float mean_ret_dbfs = sum_ret / (float)collected;


Serial.printf("[Validation] SOURCE_NODE mean peak: %+.1f dBFS\n", mean_src_dbfs);
Serial.printf("[Validation] RETURN_NODE mean peak: %+.1f dBFS\n", mean_ret_dbfs);


// Criterion 1: SOURCE_NODE level in target window
bool src_in_window = (mean_src_dbfs >= VALIDATION_TARGET_LEVEL_MIN_DBFS &&
                         mean_src_dbfs <= VALIDATION_TARGET_LEVEL_MAX_DBFS);
addCriterion(&result, "SOURCE_NODE level in window",
                mean_src_dbfs, VALIDATION_TARGET_LEVEL_MAX_DBFS,
                src_in_window, "dBFS");


// Criterion 2: RETURN_NODE level in target window
bool ret_in_window = (mean_ret_dbfs >= VALIDATION_TARGET_LEVEL_MIN_DBFS &&
                         mean_ret_dbfs <= VALIDATION_TARGET_LEVEL_MAX_DBFS);
addCriterion(&result, "RETURN_NODE level in window",
                mean_ret_dbfs, VALIDATION_TARGET_LEVEL_MAX_DBFS,
                ret_in_window, "dBFS");


// Criterion 3: Gate gap — BOTH channels must be well above TF_SOURCE_GATE.
// Gate level in dBFS = 20 * log10(TF_SOURCE_GATE) ≈ –60 dBFS.
// A narrow gap means bins will be gated out, degrading TF accuracy.
// An under-level RETURN produces unreliable TF even when SOURCE is fine,
// so both channels must pass this criterion independently.
float gate_dbfs = 20.0f * log10f(TF_SOURCE_GATE);
float gap_src      = mean_src_dbfs - gate_dbfs;
float gap_ret      = mean_ret_dbfs - gate_dbfs;
addCriterion(&result, "Source-to-gate gap (> min)",
                gap_src, VALIDATION_GATE_GAP_MIN_DB,
                  gap_src >= VALIDATION_GATE_GAP_MIN_DB, "dB");
     addCriterion(&result, "Return-to-gate gap (> min)",
                  gap_ret, VALIDATION_GATE_GAP_MIN_DB,
                  gap_ret >= VALIDATION_GATE_GAP_MIN_DB, "dB");


     // Criterion 4: No clipping on either channel
     bool no_clip = (!any_src_clip && !any_ret_clip);
     addCriterion(&result, "No clipping (both channels)",
                  any_src_clip || any_ret_clip ? 1.0f : 0.0f,
                  0.0f, no_clip, "clip");


     if (!src_in_window || !ret_in_window) {
         Serial.println("[Validation] LEVEL FAIL: Adjust SGTL5000_LINE_IN_LEVEL in");
         Serial.println("[Validation] config.h, or reduce the signal generator output.");
         Serial.printf ("[Validation] Current level setting: %d     "
                          "(0=lowest gain, 15=highest)\n", SGTL5000_LINE_IN_LEVEL);
     }


     validation_printResult(result);
     presentation_status(result.all_passed
         ? "PREFLIGHT: PASS — levels OK"
         : "PREFLIGHT: FAIL — adjust gain, see Serial");
     return result;
}


// =============================================================================
// TEST 1: FLAT LOOPBACK
// =============================================================================
// Setup: same broadband bench signal (pink noise or white noise from a signal
// generator or DAW output) Y-split to both SOURCE_NODE and RETURN_NODE inputs.
// Guitar signal is NOT acceptable — it is narrowband and varies between runs.
//
// Expected result: TF ≈ 0 dB flat across the analysis band.
// =============================================================================
ValidationResult validation_runFlatLoopback() {


     ValidationResult result;
     initResult(&result, "Flat Loopback     (expect 0 dB flat)");
     presentation_status("VALIDATION 1: Flat loopback — collecting...");
     Serial.println("\n[Validation] Test 1: Flat Loopback");
     // CHANGED [audit-1]: Print the settle count using the named constant.
     Serial.printf ("[Validation] Collecting %d blocks + %d settle blocks...\n",
                      VALIDATION_FRAME_COUNT, VALIDATION_SETTLE_BLOCKS);


     uint32_t t_start = millis();
     audioEngine_resetSmoothing();
CollectionStats stats;
if (!collectFrames(VALIDATION_FRAME_COUNT, &stats)) {
    Serial.println("[Validation] Test aborted: route changed mid-collection.");
    result.all_passed = false;
    return result;
}


result.frames_collected = stats.blocks_collected;
result.duration_ms       = millis() - t_start;
// CHANGED [audit-4]: Comment corrected — tf_mean is for external use
// (SD logging, cable characterisation baseline), NOT for the symmetry test.
memcpy(result.tf_mean, stats.mean_tf, sizeof(result.tf_mean));


float band_mean, band_pp, band_min, band_max;
computeBandStats(stats.mean_tf, &band_mean, &band_pp, &band_min, &band_max);


int nan_bins = 0, total_band_bins = 0;
for (int k = 0; k < FFT_BINS; k++) {
    if (!binInAnalysisBand(k)) continue;
    total_band_bins++;
    if (isnan(stats.mean_tf[k])) nan_bins++;
}


bool mean_ok = !isnan(band_mean) && (fabsf(band_mean) < LOOPBACK_MEAN_TOLERANCE_DB);
addCriterion(&result, "Mean TF offset (< tol)",
             isnan(band_mean) ? NAN : fabsf(band_mean),
             LOOPBACK_MEAN_TOLERANCE_DB, mean_ok, "dB");


bool pp_ok = !isnan(band_pp) && (band_pp < LOOPBACK_PP_TOLERANCE_DB);
addCriterion(&result, "Peak-to-peak TF (< tol)",
             isnan(band_pp) ? NAN : band_pp,
             LOOPBACK_PP_TOLERANCE_DB, pp_ok, "dB");


bool conf_ok = (stats.mean_confidence >= LOOPBACK_CONFIDENCE_MIN);
addCriterion(&result, "Mean confidence (> tol)",
             stats.mean_confidence, LOOPBACK_CONFIDENCE_MIN, conf_ok, "frac");


float nan_frac = (total_band_bins > 0)
                 ? (float)nan_bins / (float)total_band_bins : 1.0f;
bool nan_ok = (nan_frac <= 0.05f);
addCriterion(&result, "NaN bins in band (< 5%)",
             nan_frac * 100.0f, 5.0f, nan_ok, "%");


Serial.printf("[Validation] Band: min=%+.2f max=%+.2f mean=%+.2f pp=%.2f dB\n",
              band_min, band_max, band_mean, band_pp);
Serial.printf("[Validation] Confidence: %.1f%%     NaN bins: %d/%d\n",
              stats.mean_confidence * 100.0f, nan_bins, total_band_bins);
    validation_printResult(result);


    // CHANGED [audit-5]: Print baseline TF after a pass so it can be
    // captured from the Serial log for future cable characterisation.
    if (result.all_passed) {
        validation_printBaseline(result);
    }


    presentation_status(result.all_passed
        ? "VALIDATION 1: PASS — loopback flat"
        : "VALIDATION 1: FAIL — see Serial");
    return result;
}


// =============================================================================
// TEST 2: CHANNEL SWAP SYMMETRY
// =============================================================================
// Setup: same Y-split loopback as Test 1. Same broadband bench stimulus.
// This test runs two independent collections: Pass A (default route) and
// Pass B (nodes swapped). The symmetry test does NOT read from Test 1's
// result — it collects its own data so that the comparison is self-contained
// and not dependent on the time gap between Test 1 and Test 2.
// =============================================================================
ValidationResult validation_runChannelSwapSymmetry() {


    ValidationResult result;
    initResult(&result, "Channel Swap Symmetry");
    Serial.println("\n[Validation] Test 2: Channel Swap Symmetry");


    // Pass A
    presentation_status("VALIDATION 2A: default route — collecting...");
    Serial.println("[Validation] Pass A: default route");
    audioEngine_resetSmoothing();
    CollectionStats stats_a;
    uint32_t t_start = millis();
    if (!collectFrames(VALIDATION_FRAME_COUNT, &stats_a)) {
        Serial.println("[Validation] Test aborted: route changed mid-collection.");
        result.all_passed = false;
        return result;
    }
    float mean_a, pp_a, min_a, max_a;
    computeBandStats(stats_a.mean_tf, &mean_a, &pp_a, &min_a, &max_a);
    Serial.printf("[Validation] Pass A: mean=%+.2f dB     pp=%.2f dB    conf=%.0f%%\n",
                     mean_a, pp_a, stats_a.mean_confidence * 100.0f);


    // Swap route
SignalRoute swapped = { RETURN_NODE_PHYSICAL_CH, SOURCE_NODE_PHYSICAL_CH,
                            "Symmetry check: SOURCE/RETURN nodes swapped" };
audioEngine_setRoute(swapped);
presentation_status("VALIDATION 2B: swapped route — collecting...");
Serial.println("[Validation] Pass B: swapped route");
audioEngine_resetSmoothing();

// FIX [route-self-abort]: audioEngine_setRoute() above latches a ROUTE_CHANGED
// event for the next audioCap_update() call. Without draining it here,
// collectFrames() would see ROUTE_CHANGED on its first update and abort
// immediately, making Test 2 Pass B unable to ever pass. We drain the
// latched event explicitly and discard any stale AudioRawBlock so
// collection starts from a fresh, post-swap state.
{
    uint32_t drain_start = millis();
    while (millis() - drain_start < 200) {
        AudioCaptureEvent ev = audioCap_update();
        if (ev == AudioCaptureEvent::ROUTE_CHANGED) break;
        if (audioCap_isBlockFresh(AudioConsumer::LIVE)) {
            audioCap_markConsumed(AudioConsumer::LIVE);
        }
        delay(2);
    }
    delay(50);   // brief settle for the new mixer state
    if (audioCap_isBlockFresh(AudioConsumer::LIVE)) {
        audioCap_markConsumed(AudioConsumer::LIVE);
    }
}

CollectionStats stats_b;
if (!collectFrames(VALIDATION_FRAME_COUNT, &stats_b)) {
      Serial.println("[Validation] Test aborted: route changed mid-collection.");
      result.all_passed = false;
      return result;
}
float mean_b, pp_b, min_b, max_b;
computeBandStats(stats_b.mean_tf, &mean_b, &pp_b, &min_b, &max_b);
Serial.printf("[Validation] Pass B: mean=%+.2f dB      pp=%.2f dB   conf=%.0f%%\n",
                mean_b, pp_b, stats_b.mean_confidence * 100.0f);


// Restore default route
SignalRoute restored = { SOURCE_NODE_PHYSICAL_CH, RETURN_NODE_PHYSICAL_CH,
                             "Default bench: SOURCE_NODE=L, RETURN_NODE=R" };
audioEngine_setRoute(restored);
Serial.println("[Validation] Default route restored.");

// Drain the latched ROUTE_CHANGED so the next test (or live display)
// is not falsely interrupted by our own restore.
{
    uint32_t drain_start = millis();
    while (millis() - drain_start < 200) {
        AudioCaptureEvent ev = audioCap_update();
        if (ev == AudioCaptureEvent::ROUTE_CHANGED) break;
        if (audioCap_isBlockFresh(AudioConsumer::LIVE)) {
            audioCap_markConsumed(AudioConsumer::LIVE);
        }
        delay(2);
    }
    delay(50);
    if (audioCap_isBlockFresh(AudioConsumer::LIVE)) {
        audioCap_markConsumed(AudioConsumer::LIVE);
    }
}


// Bin-by-bin difference with shared-bin counting
float max_diff = 0.0f;
int     diff_bin = -1, shared_valid = 0, total_band = 0;
for (int k = 0; k < FFT_BINS; k++) {
      if (!binInAnalysisBand(k)) continue;
      total_band++;
      float va = stats_a.mean_tf[k], vb = stats_b.mean_tf[k];
      if (isnan(va) || isnan(vb)) continue;
      shared_valid++;
      float d = fabsf(va - vb);
      if (d > max_diff) { max_diff = d; diff_bin = k; }
}
float shared_frac = (total_band > 0)
                        ? (float)shared_valid / (float)total_band : 0.0f;


result.frames_collected = stats_a.blocks_collected + stats_b.blocks_collected;
result.duration_ms          = millis() - t_start;
memcpy(result.tf_mean, stats_a.mean_tf, sizeof(result.tf_mean));


addCriterion(&result, "Pass A mean offset (< tol)",
               fabsf(mean_a), LOOPBACK_MEAN_TOLERANCE_DB,
               !isnan(mean_a) && fabsf(mean_a) < LOOPBACK_MEAN_TOLERANCE_DB, "dB");
addCriterion(&result, "Pass A peak-to-peak (< tol)",
               pp_a, LOOPBACK_PP_TOLERANCE_DB,
                  !isnan(pp_a) && pp_a < LOOPBACK_PP_TOLERANCE_DB, "dB");
     addCriterion(&result, "Pass B mean offset (< tol)",
                  fabsf(mean_b), LOOPBACK_MEAN_TOLERANCE_DB,
                  !isnan(mean_b) && fabsf(mean_b) < LOOPBACK_MEAN_TOLERANCE_DB, "dB");
     addCriterion(&result, "Pass B peak-to-peak (< tol)",
                  pp_b, LOOPBACK_PP_TOLERANCE_DB,
                  !isnan(pp_b) && pp_b < LOOPBACK_PP_TOLERANCE_DB, "dB");


     bool shared_ok = (shared_frac >= SYMMETRY_MIN_SHARED_BIN_FRAC);
     addCriterion(&result, "Shared valid bins (> tol)",
                  shared_frac, SYMMETRY_MIN_SHARED_BIN_FRAC, shared_ok, "frac");


     // FIX [perfect-data]: previously the criterion required diff_bin >= 0,
     // which is only set when some pair has d > max_diff (= 0 initially).
     // Byte-identical data (max_diff stays 0) produced sym_ok = false even
     // though the result is maximally good. The diff_bin index is reported
     // for diagnostics only; the pass/fail condition is shared_ok + max_diff.
     bool sym_ok = shared_ok && (max_diff < SYMMETRY_MAX_DIFF_DB);
     addCriterion(&result, "Max A-B difference (< tol)",
                  shared_ok ? max_diff : NAN,
                  SYMMETRY_MAX_DIFF_DB, sym_ok, "dB");


     Serial.printf("[Validation] Shared bins: %d/%d = %.0f%%\n",
                      shared_valid, total_band, shared_frac * 100.0f);
     if (diff_bin >= 0) {
         Serial.printf("[Validation] Max A-B diff: %.2f dB at %.0f Hz (bin %d)\n",
                          max_diff, audioEngine_binToHz(diff_bin), diff_bin);
     } else {
         Serial.println("[Validation] WARNING: No shared valid bins.");
     }


     validation_printResult(result);
     presentation_status(result.all_passed
         ? "VALIDATION 2: PASS — channels symmetric"
         : "VALIDATION 2: FAIL — see Serial");
     return result;
}


// =============================================================================
// TEST 3: KNOWN GAIN OFFSET
// =============================================================================
// Setup: fixed resistive voltage divider (1% metal film resistors) inserted
// between the signal source and RETURN_NODE input. Use fixed resistors, NOT a
// potentiometer — a pot's source impedance varies with setting and produces
// frequency-dependent loading that causes the flatness criterion to fail even
// when everything is working correctly.
//
// Calculate attenuation: Att_dB = 20 * log10(R2 / (R1 + R2))
// Example: R1=10kΩ, R2=10kΩ → –6.02 dB. Keep both resistors below 10kΩ
// to keep source impedance low enough to avoid cable capacitance rolloff.
// =============================================================================
ValidationResult validation_runKnownGainOffset(float expected_offset_db) {
ValidationResult result;
initResult(&result, "Known Gain Offset");
Serial.println("\n[Validation] Test 3: Known Gain Offset");
Serial.printf ("[Validation] Expected TF: %+.1f dB flat\n", expected_offset_db);
presentation_status("VALIDATION 3: Gain offset — collecting...");


audioEngine_resetSmoothing();
CollectionStats stats;
uint32_t t_start = millis();
if (!collectFrames(VALIDATION_FRAME_COUNT, &stats)) {
       Serial.println("[Validation] Test aborted: route changed mid-collection.");
       result.all_passed = false;
       return result;
}
result.duration_ms          = millis() - t_start;
result.frames_collected = stats.blocks_collected;
memcpy(result.tf_mean, stats.mean_tf, sizeof(result.tf_mean));


float band_mean, band_pp, band_min, band_max;
computeBandStats(stats.mean_tf, &band_mean, &band_pp, &band_min, &band_max);


Serial.printf("[Validation] Measured mean: %+.2f dB       expected: %+.1f dB   "
                 "error: %+.2f dB\n",
                 band_mean, expected_offset_db, band_mean - expected_offset_db);


float mean_error = isnan(band_mean) ? NAN : fabsf(band_mean - expected_offset_db);
bool     offset_ok   = !isnan(mean_error) && (mean_error < GAIN_OFFSET_TOLERANCE_DB);
addCriterion(&result, "Mean TF error vs expected (< tol)",
                isnan(mean_error) ? NAN : mean_error,
                GAIN_OFFSET_TOLERANCE_DB, offset_ok, "dB");


bool pp_ok = !isnan(band_pp) && (band_pp < LOOPBACK_PP_TOLERANCE_DB);
addCriterion(&result, "Peak-to-peak flatness (< tol)",
                isnan(band_pp) ? NAN : band_pp,
                LOOPBACK_PP_TOLERANCE_DB, pp_ok, "dB");


bool conf_ok = (stats.mean_confidence >= LOOPBACK_CONFIDENCE_MIN);
addCriterion(&result, "Mean confidence (> tol)",
                stats.mean_confidence, LOOPBACK_CONFIDENCE_MIN, conf_ok, "frac");


// Informational: show what was actually measured (always passes)
addCriterion(&result, "Measured mean TF (info only)",
                isnan(band_mean) ? NAN : band_mean,
                expected_offset_db, true, "dB");


validation_printResult(result);
     presentation_status(result.all_passed
         ? "VALIDATION 3: PASS — gain offset correct"
         : "VALIDATION 3: FAIL — see Serial");
     return result;
}


// =============================================================================
// TEST 4: KNOWN FILTER RESPONSE
// =============================================================================
// Setup: first-order RC low-pass filter inserted in the RETURN_NODE path.
//
// CHANGED [audit-8]: The RC filter example has been corrected. The prompt
// now quotes the LOADED corner frequency (accounting for SGTL5000 ~40kΩ
// input impedance) rather than the unloaded value. See validation_runAll()
// prompt for the corrected example values.
//
// CHANGED [audit-7]: This test now specifies WHITE NOISE as the required
// stimulus, not pink noise. Pink noise has a natural –3 dB/octave rolloff,
// which reduces high-frequency spectral energy precisely where the slope
// estimation needs valid bins. White noise has flat energy per bin and is
// the correct choice for filter shape validation.
// =============================================================================
ValidationResult validation_runKnownFilter(float corner_freq_hz,
                                               float expected_slope_db_per_octave) {
     ValidationResult result;
     initResult(&result, "Known Filter Response");
     Serial.println("\n[Validation] Test 4: Known Filter Response");
     Serial.printf ("[Validation] Corner: %.0f Hz       Expected slope: %.0f dB/oct\n",
                      corner_freq_hz, expected_slope_db_per_octave);
     // CHANGED [audit-7]: White noise requirement noted in Serial output.
     Serial.println("[Validation] Stimulus: WHITE NOISE required (not pink noise).");
     presentation_status("VALIDATION 4: Filter check — collecting...");


     audioEngine_resetSmoothing();
     CollectionStats stats;
     uint32_t t_start = millis();
     if (!collectFrames(VALIDATION_FRAME_COUNT, &stats)) {
         Serial.println("[Validation] Test aborted: route changed mid-collection.");
         result.all_passed = false;
         return result;
     }
     result.duration_ms         = millis() - t_start;
     result.frames_collected = stats.blocks_collected;
     memcpy(result.tf_mean, stats.mean_tf, sizeof(result.tf_mean));


     // Criterion 1: delta at 2× corner frequency vs passband mean (signed dB)
     float passband_mean = 0.0f;
int      pb_count         = 0;
for (int k = 0; k < FFT_BINS; k++) {
       float f = audioEngine_binToHz(k);
       if (f < VALIDATION_FREQ_MIN || f >= corner_freq_hz) continue;
       if (isnan(stats.mean_tf[k])) continue;
       passband_mean += stats.mean_tf[k];
       pb_count++;
}
// FIX [passband-zero]: if no in-passband bin was valid, passband_mean is
// still 0.0 from initialisation. The delta would then be computed against
// zero — the test would silently pass for the wrong reason (or fail for an
// equally wrong reason). Require at least one valid passband bin AND a
// non-Nyquist 2fc bin before computing the criterion.
const float canonical_bin_hz = (float)SAMPLE_RATE / (float)(FFT_BINS * 2);
const float two_fc_hz       = corner_freq_hz * 2.0f;
bool atten_inputs_valid    = (pb_count > 0) && isfinite(two_fc_hz)
                              && two_fc_hz < ((float)SAMPLE_RATE * 0.5f - canonical_bin_hz);
if (atten_inputs_valid && pb_count > 0) passband_mean /= (float)pb_count;


int      corner2x_bin       = audioEngine_hzToBin(corner_freq_hz * 2.0f);
float tf_at_2fc             = atten_inputs_valid ? stats.mean_tf[corner2x_bin] : NAN;
float delta_at_2fc_db = (!atten_inputs_valid || isnan(tf_at_2fc))
                              ? NAN
                              : (tf_at_2fc - passband_mean);
bool     atten_ok           = !isnan(delta_at_2fc_db)
                                 && (delta_at_2fc_db < FILTER_2FC_MAX_DELTA_DB);


addCriterion(&result, "delta at 2fc vs passband (< tol)",
                isnan(delta_at_2fc_db) ? NAN : delta_at_2fc_db,
                FILTER_2FC_MAX_DELTA_DB, atten_ok, "dB");


Serial.printf("[Validation] Passband mean: %+.2f dB           TF at 2fc: %+.2f dB   "
                    "delta: %+.2f dB     threshold: %+.1f dB\n",
                    passband_mean,
                    isnan(tf_at_2fc) ? 0.0f : tf_at_2fc,
                    isnan(delta_at_2fc_db) ? 0.0f : delta_at_2fc_db,
                    FILTER_2FC_MAX_DELTA_DB);


// Criterion 2: slope estimation
float measured_slope = estimateSlope(stats.mean_tf, corner_freq_hz);
float slope_error          = isnan(measured_slope) ? NAN
                             : fabsf(measured_slope - expected_slope_db_per_octave);
bool     slope_ok          = !isnan(slope_error)
                             && (slope_error < FILTER_SLOPE_TOLERANCE_DBOCTAVE);
addCriterion(&result, "Slope vs expected (< tol)",
                isnan(slope_error) ? NAN : slope_error,
                FILTER_SLOPE_TOLERANCE_DBOCTAVE, slope_ok, "dB/oct");


if (!isnan(measured_slope)) {
       Serial.printf("[Validation] Slope: measured=%.1f        expected=%.1f   "
                        "error=%.1f dB/oct\n",
                        measured_slope, expected_slope_db_per_octave, slope_error);
} else {
       Serial.println("[Validation] WARNING: slope NAN — too few valid bins above corner.");
       Serial.println("[Validation] Switch to white noise; pink noise may lack HF energy.");
}


// Criterion 3: confidence
     bool conf_ok = (stats.mean_confidence >= LOOPBACK_CONFIDENCE_MIN);
     addCriterion(&result, "Mean confidence (> tol)",
                     stats.mean_confidence, LOOPBACK_CONFIDENCE_MIN, conf_ok, "frac");


     // Criterion 4: monotonicity above corner.
     // FIX [monotonicity]: the previous test only counted upward bumps and
     // updated prev_tf to the current value unconditionally — which meant
     // a single noisy outlier poisoned the comparison for the next bin
     // (now prev_tf is the outlier). For a first-order low-pass above its
     // corner the TF should decrease smoothly; any step bigger than
     // FILTER_MONO_STEP_DB (in either direction) is non-physical. We now
     // count both directions, and only advance prev_tf to "well-behaved"
     // values so a single outlier doesn't poison the next comparison.
     int      non_mono = 0;
     float prev_tf        = NAN;
     for (int k = 0; k < FFT_BINS; k++) {
            float f = audioEngine_binToHz(k);
            if (f < corner_freq_hz || f > VALIDATION_FREQ_MAX) continue;
            float v = stats.mean_tf[k];
            if (isnan(v)) continue;
            if (!isnan(prev_tf)) {
                float step = v - prev_tf;
                // Upward step beyond tolerance: bump.
                // Large downward step beyond tolerance: also non-physical for
                // first-order LP at this bin spacing (~43 Hz).
                if (fabsf(step) > FILTER_MONO_STEP_DB) {
                    non_mono++;
                    // Keep prev_tf at its previous well-behaved value so the
                    // next comparison is not biased by this outlier.
                    continue;
                }
            }
            prev_tf = v;
     }
     bool mono_ok = (non_mono <= FILTER_MONO_MAX_BUMPS);
     char mono_label[40];
     snprintf(mono_label, sizeof(mono_label),
                 "Monotonic rolloff (bumps <= %d)", FILTER_MONO_MAX_BUMPS);
     addCriterion(&result, mono_label,
                     (float)non_mono, (float)FILTER_MONO_MAX_BUMPS, mono_ok, "bumps");


     validation_printResult(result);
     presentation_status(result.all_passed
            ? "VALIDATION 4: PASS — filter response correct"
            : "VALIDATION 4: FAIL — see Serial");
     return result;
}


// =============================================================================
// PUBLIC: validation_runAll()
// CHANGED [audit-3]: Preflight level check added as first step.
// CHANGED [audit-7]: All prompts updated — "play guitar" removed throughout;
//       white noise vs pink noise distinction made explicit for Test 4.
// CHANGED [audit-8]: RC filter example corrected to show loaded corner.
// =============================================================================
bool validation_runAll() {


     Serial.println("\n================================================");
     Serial.println("        VALIDATION SUITE   v0.5.0 — Guitar Rig Analyzer");
     Serial.println("================================================");


     int passed = 0;
     int total     = 5;      // CHANGED [audit-3]: Was 4; preflight is now counted.


     // --- Preflight: Level Check ---
     // CHANGED [audit-3]: Preflight promoted to a counted test step.
// If this fails, stop — the signal level is wrong and all subsequent
// tests will produce unreliable data regardless of pass/fail status.
validation_waitForUser(
    "PREFLIGHT: Signal Level Check\n"
    "Connect your broadband signal source (signal generator set to\n"
    "pink noise or white noise, ~0.3 Vrms / –10 dBV) to SOURCE_NODE.\n"
    "Connect the same source to RETURN_NODE (Y-split).\n"
    "Press Enter to check that levels are in the –6 to –12 dBFS window.");
ValidationResult preflight = validation_runPreflightLevelCheck();
if (preflight.all_passed) {
    passed++;
} else {
    Serial.println("[Validation] PREFLIGHT FAILED — stopping suite.");
    Serial.println("[Validation] Adjust signal level and re-run.");
    presentation_status("PREFLIGHT FAIL — suite stopped");
    return false;
}


// --- Test 1: Flat Loopback ---
// CHANGED [audit-7]: "play guitar" removed. Broadband bench source required.
validation_waitForUser(
    "TEST 1: Flat Loopback\n"
    "Keep the Y-split connection from the preflight check.\n"
    "Stimulus: pink noise or white noise from signal generator or DAW.\n"
    "Both SOURCE_NODE and RETURN_NODE receive the SAME signal.\n"
    "Press Enter to begin collection.");
if (validation_runFlatLoopback().all_passed) passed++;


// --- Test 2: Channel Swap Symmetry ---
validation_waitForUser(
    "TEST 2: Channel Swap Symmetry\n"
    "Keep the same Y-split loopback connection and same stimulus.\n"
    "The firmware will automatically swap and restore the route.\n"
    "Press Enter to begin.");
if (validation_runChannelSwapSymmetry().all_passed) passed++;


// --- Test 3: Known Gain Offset ---
validation_waitForUser(
    "TEST 3: Known Gain Offset\n"
    "Insert a fixed resistive voltage divider in the RETURN_NODE path.\n"
    "Use 1% metal film resistors — NOT a potentiometer.\n"
    "Example: R1=10kΩ, R2=10kΩ → attenuation = –6.02 dB\n"
    "Verify the attenuation with a DMM (measure Vout/Vin ratio).\n"
    "Keep both resistors ≤10kΩ to avoid HF rolloff from cable capacitance.\n"
    "Enter the expected offset in dB, then press Enter.");


float expected_offset = -6.0f;
Serial.print("[Validation] Enter expected offset dB (default -6.0): ");
expected_offset = readSerialFloatWithAudioPump(expected_offset);
Serial.printf("[Validation] Using: %+.1f dB\n", expected_offset);


if (validation_runKnownGainOffset(expected_offset).all_passed) passed++;


// --- Test 4: Known Filter Response ---
// CHANGED [audit-7]: Prompt now specifies WHITE NOISE and explains why.
// CHANGED [audit-8]: RC example corrected to show loaded corner frequency.
validation_waitForUser(
    "TEST 4: Known Filter Response\n"
    "Insert a first-order RC low-pass filter in the RETURN_NODE path.\n"
    "\n"
    "STIMULUS: WHITE NOISE required (not pink noise).\n"
    "   Pink noise has a natural –3 dB/octave rolloff that reduces\n"
    "   energy above the corner frequency — exactly where the slope\n"
    "   estimation needs valid bins. White noise has flat energy per bin.\n"
    "\n"
    "RC EXAMPLE (unloaded): R=10kΩ, C=10nF → fc = 1592 Hz\n"
    "LOADED corner (with SGTL5000 ~40kΩ input):\n"
    "   R_eff = 10k || 40k = 8kΩ → fc_loaded ≈ 1989 Hz\n"
    "Enter THE LOADED corner frequency (or buffer the filter output\n"
    "with the second OPA1642 channel to use the unloaded value).\n"
    "Then press Enter.");


float corner = 1989.0f;     // CHANGED [audit-8]: Default is now the loaded corner.
Serial.print("[Validation] Enter loaded corner frequency Hz (default 1989): ");
corner = readSerialFloatWithAudioPump(corner);
Serial.printf("[Validation] Corner: %.0f Hz, expecting –6 dB/oct.\n", corner);


if (validation_runKnownFilter(corner, -6.0f).all_passed) passed++;


// Summary
Serial.println("\n================================================");
Serial.printf ("   SUITE COMPLETE: %d / %d passed\n", passed, total);
Serial.println("================================================");
// CHANGED [audit-9]: Remind user to tighten tolerances after full pass.
if (passed == total) {
    Serial.println("[Validation] All tests passed. NEXT STEP: review the");
    Serial.println("[Validation] measured values in each test report above.");
    Serial.println("[Validation] Where measured << tolerance, tighten the");
        Serial.println("[Validation] corresponding constant in validation.h to");
        Serial.println("[Validation] reflect actual hardware capability.");
    }


    presentation_status(
        passed == total ? "ALL VALIDATION PASSED" : "VALIDATION: failures — see Serial");
    return (passed == total);
}
