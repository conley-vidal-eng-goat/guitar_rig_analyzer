// =============================================================================
// measurement_engine.cpp   —     Guitar Rig Analyzer   v0.5.0
// =============================================================================
// Precision measurement state machine and result production.
//
// COMPLEX FFT MEASUREMENT MILESTONE
// ----------------------------------------
// This implementation produces REAL measurement products from Hann-windowed
// raw time-domain samples captured via AudioRecordQueue, transformed by
// CMSIS-DSP arm_cfft_f32(), and accumulated as true complex cross-spectra.
//
// WHAT IS REAL:
//   S_xx_db[], S_yy_db[]       — averaged power spectra (dBFS) from complex FFT auto-spectra
//   tf_raw_mag_db[]             — H1 magnitude: √(S_xy_re²+S_xy_im²) / S_xx (dB)
//   coherence[]                 — γ² = |S_xy|² / (S_xx*S_yy) — true complex coherence
//   phase_unwrapped[]           — continuous per-bin phase from atan2(S_xy_im, S_xy_re)
//   group_delay_ms[]            — -d(phase)/d(omega) — real latency estimate per bin
//   result_quality              — graded from actual coherence and valid_bin_fraction
//
// HOW IT WORKS:
//   audio_capture's AudioRecordQueue objects buffer raw int16 samples.
//   measurement_engine drains BLOCKS_PER_FFT=8 blocks per FFT frame,
//   applies a Hann window, and runs arm_cfft_f32() via CMSIS-DSP.
//   The complex output bins feed true S_xy_im accumulation, enabling
//   real atan2 phase rather than the previous polarity-only (0/π) values.
//   A fallback to magnitude-only accumulation activates if CMSIS-DSP
//   is unavailable.
//
// ALL MILESTONES IMPLEMENTED:
//   Calibration application — calStore_isValid() + complex correction in Step 6
//   Export engine              — exportEngine_saveMeasurement() via EXPORTING state
//   Insights engine            — insightsEngine_analyse() called by main loop on RESULT_READY
//
// REMAINING FUTURE WORK (not in this file):
//   signal_router              — hardware jack detection and relay control
//   display_engine             — touch UI (result view and insight panel now implemented)
//
// SIGNAL GENERATOR COORDINATION
// ------------------------------
// measurement_engine calls signalGen_update() (package-private function in
// signal_generator.cpp) on each loop iteration when a generator stimulus is
// active. This is the only coupling between the two modules — generator
// state is not polled via the public header; it is driven forward here.
// =============================================================================
#include "measurement_engine.h"
#include "signal_generator.h"
#include "audio_capture.h"
#include "measurement_core.h"
#include "calibration_store.h"
#include "export_engine.h"
#include <Audio.h>
#include <string.h>
#include <math.h>


// CMSIS-DSP for complex FFT
// The Teensy 4.1 (ARM Cortex-M7) includes the CMSIS-DSP library as part of
// the Arduino/Teensyduino toolchain. arm_cfft_f32() runs the complex FFT
// in-place on an interleaved [re0, im0, re1, im1, ...] float array.
// The result is in normal (not bit-reversed) order when ifftFlag=0, bitReverseFlag=1.
#include <arm_math.h>
#include <arm_const_structs.h>


// Helper for compile-time string expansion in Serial.println
#ifndef STRINGIFY
#define STRINGIFY_INNER(x) #x
#define STRINGIFY(x) STRINGIFY_INNER(x)
#endif


// =============================================================================
// FORWARD DECLARATION — package-private signalGen_update()
// =============================================================================
// Defined in signal_generator.cpp. Not in the public header.
// Called here to drive generator state forward each loop iteration.
extern bool signalGen_update();


// =============================================================================
// MODULE-PRIVATE STATE
// =============================================================================


// Current machine state
static MeasurementState s_state          = MeasurementState::IDLE;
static AbortReason         s_abort_reason = AbortReason::NONE;


// Active measurement parameters (set by measurementEngine_arm)
static MeasurementParams s_params;


// Capture progress
static uint16_t s_frames_captured     = 0;      // Blocks consumed from CONSUMER_MEASURE
static uint32_t s_capture_start_block = 0;
static uint32_t s_capture_end_block      = 0;     // Block of last accepted capture frame


// Channel routing captured at first CAPTURE block — used by runProcessing()
// so it does not need to read the (potentially stale) consumer block post-capture.
static uint8_t s_captured_source_ch = 0;
static uint8_t s_captured_return_ch = 0;


// Armed state: for EXTERNAL stimulus, track when level threshold is met
// For INTERNAL stimulus, track the pending generator start block
static uint32_t s_arm_start_ms = 0;      // millis() when ARMED was entered


// Self-test state (simplified for skeleton)
static uint8_t s_self_test_step = 0;
static uint32_t s_self_test_baseline_block = 0;     // block counter snapshot at self-test entry


// The single resident MeasurementResult (read-only outside this module)
static MeasurementResult s_result;


// Accumulator (canonical 512-bin grid, double precision).
// Complex cross-spectrum accumulation: S_xx, S_yy, S_xy_re, S_xy_im per frame
// via CMSIS-DSP arm_cfft_f32() on AudioRecordQueue raw samples.
// Rebinning to canonical grid (for MODE_PRECISION/MODE_LF) is not yet implemented;
// those modes currently share the MODE_LIVE accumulation path.
static MeasurementAccumulator s_accum;


// Initialisation guard
static bool s_initialised = false;


// Filename used for the last export (for display feedback)
static char s_export_filename[EXPORT_FILENAME_LEN];


// =============================================================================
// COMPLEX FFT PATH — buffers, instance, and constants
// =============================================================================
// Number of 128-sample Audio Library blocks per FFT frame.
// FFT_SIZE / AUDIO_BLOCK_SAMPLES = 1024 / 128 = 8 blocks.
#define BLOCKS_PER_FFT    (FFT_SIZE / AUDIO_BLOCK_SAMPLES)


// Hann window coefficients — computed once in measurementEngine_init().
static float s_hann_window[FFT_SIZE];


// Raw time-domain sample buffers (one FFT frame per channel).
static float s_raw_src[FFT_SIZE];
static float s_raw_ret[FFT_SIZE];


// Interleaved complex arrays for arm_cfft_f32():
//   [re0, im0, re1, im1, ..., re(N-1), im(N-1)]
// Size = FFT_SIZE * 2 floats per channel.
static float s_fft_src_cx[FFT_SIZE * 2];
static float s_fft_ret_cx[FFT_SIZE * 2];
// CMSIS-DSP complex FFT instance and readiness flag.
static const arm_cfft_instance_f32* s_cfft_instance = &arm_cfft_sR_f32_len1024;
static bool s_cfft_ready = false;


// =============================================================================
// PRIVATE HELPERS
// =============================================================================


// -----------------------------------------------------------------------------
// transitionTo(new_state)
// Central state transition function. All transitions go through here so the
// Serial log always reflects the true state path.
// -----------------------------------------------------------------------------
// Helper: name a state as a const char* without touching s_state.
// Used by transitionTo() so it can log old and new state independently.
static const char* stateName(MeasurementState st) {
    switch (st) {
        case MeasurementState::IDLE:          return "IDLE";
        case MeasurementState::ARMED:         return "ARMED";
        case MeasurementState::CAPTURE:       return "CAPTURE";
        case MeasurementState::PROCESSING: return "PROCESSING";
        case MeasurementState::RESULT:        return "RESULT";
        case MeasurementState::EXPORTING:     return "EXPORTING";
        case MeasurementState::ABORTED:       return "ABORTED";
        case MeasurementState::SELF_TEST:     return "SELF_TEST";
        default:                              return "?";
    }
}


static MeasurementEvent transitionTo(MeasurementState new_state) {
    MeasurementState old_state = s_state;


    // FIX [transition-log]: Previous version called measurementEngine_getStateDescription()
    // AFTER assigning s_state = new_state, so it printed new_state in both the
    // "from" and "to" positions — the log showed "X → old_state" instead of
    // "old_state → X". Fixed: capture both names before mutating s_state,
    // using the local stateName() helper which does not read s_state.
    const char* old_name = stateName(old_state);
    const char* new_name = stateName(new_state);


    s_state = new_state;


    Serial.printf("[MeasEngine] %s → %s\n", old_name, new_name);
    return MeasurementEvent::STATE_CHANGED;
}
// -----------------------------------------------------------------------------
// abortTo(reason)
// Transition to ABORTED with a specific reason. Stops the generator.
// Clears the accumulator. Returns the ABORTED event.
// -----------------------------------------------------------------------------
static MeasurementEvent abortTo(AbortReason reason) {
    s_abort_reason = reason;
    signalGen_stop();
    audioCap_endRawCapture();      // disarm queues — always end on any abort path
    memset(&s_accum, 0, sizeof(s_accum));
    s_frames_captured = 0;
    transitionTo(MeasurementState::ABORTED);
    Serial.printf("[MeasEngine] ABORTED: %s\n",
                     measurementEngine_getAbortDescription());
    return MeasurementEvent::ABORTED;
}


// -----------------------------------------------------------------------------
// validateParams(params)
// Returns true if params are valid enough to arm a measurement.
// -----------------------------------------------------------------------------
static bool validateParams(const MeasurementParams& p) {
    if (p.n_averages < 4) {
        Serial.println("[MeasEngine] arm() rejected: n_averages < 4");
        return false;
    }
    if (p.stimulus == StimulusType::INTERNAL_LOG_SWEEP) {
        if (p.sweep_start_hz >= p.sweep_end_hz) {
            Serial.println("[MeasEngine] arm() rejected: sweep start >= end frequency");
            return false;
        }
        if (p.sweep_duration_s < 0.1f) {
            Serial.println("[MeasEngine] arm() rejected: sweep duration < 0.1 s");
            return false;
        }
    }
    return true;
}


// =============================================================================
// PRIVATE: unwrapPhase(phase_in, phase_out, n_bins)
// =============================================================================
// Segment-aware phase unwrapping. Unwraps over contiguous runs of finite bins.
// NAN inputs (from unenergised bins) produce NAN outputs and reset the
// accumulator — each finite segment is unwrapped independently from its own
// first bin. Without this, a single NAN early in the array (likely bin 0,
// which is sub-bass and typically unenergised) would poison all subsequent
// unwrapped values via NAN propagation in the cumulative correction.
//
// Input:    phase_in[]   — wrapped phase in radians (atan2 output, NAN where ungated)
// Output: phase_out[] — unwrapped phase in radians; NAN where input is NAN
// =============================================================================
static void unwrapPhase(const float* phase_in, float* phase_out, int n_bins) {
     if (n_bins == 0) return;
     float cumulative_correction = 0.0f;
     for (int k = 0; k < n_bins; k++) {
         if (isnan(phase_in[k])) {
              // Gated bin: output NAN and reset accumulator
              phase_out[k] = NAN;
              cumulative_correction = 0.0f;
              continue;
         }
         if (k == 0 || isnan(phase_in[k-1])) {
              // First finite bin, or first after a gap: anchor this segment.
              // No correction from before the gap applies here.
              phase_out[k] = phase_in[k];
              cumulative_correction = 0.0f;
              continue;
         }
         // Normal case: both k and k-1 are finite — accumulate correction.
         float delta = phase_in[k] - phase_in[k-1];
         // FIX [inf-loop]: isnan() above gated NaN inputs, but the function's
         // contract did not exclude +/-Inf. Inf - 2π is still Inf, which
         // would hang the wrap-while loop. Treat non-finite delta the same
         // as a gap: emit NaN, reset the accumulator, and continue.
         if (!isfinite(delta)) {
             phase_out[k] = NAN;
             cumulative_correction = 0.0f;
             continue;
         }
         // Wrap delta to [-π, +π]
         while (delta >    (float)M_PI) delta -= 2.0f * (float)M_PI;
         while (delta < -(float)M_PI) delta += 2.0f * (float)M_PI;
         cumulative_correction += delta - (phase_in[k] - phase_in[k-1]);
         phase_out[k] = phase_in[k] + cumulative_correction;
     }
}


// =============================================================================
// PRIVATE: gradeQuality(mean_coherence, valid_bin_fraction, clip_detected)
// =============================================================================
// Grades measurement quality using the thresholds defined in measurement_core.h.
// =============================================================================
static ResultQuality gradeQuality(float mean_coh, float valid_frac, bool clip) {
     if (clip)                                                 return ResultQuality::INVALID;
     if (mean_coh >= RESULT_QUALITY_EXCELLENT_COH &&
         valid_frac >= RESULT_QUALITY_EXCELLENT_BINS)          return ResultQuality::EXCELLENT;
     if (mean_coh >= RESULT_QUALITY_GOOD_COH &&
         valid_frac >= RESULT_QUALITY_GOOD_BINS)               return ResultQuality::GOOD;
     if (mean_coh >= RESULT_QUALITY_MARGINAL_COH &&
         valid_frac >= RESULT_QUALITY_MARGINAL_BINS)           return ResultQuality::MARGINAL;
     return ResultQuality::POOR;
}
// =============================================================================
// runProcessing()
// =============================================================================
// Computes all derived measurement products from the accumulated cross-spectrum
// data in s_accum and writes them into s_result. Called once per measurement
// when CAPTURE completes. Runs to completion without yielding (~1 ms on M7).
//
// Steps 1–9 produce these real measurement products:
//    S_xx_db[], S_yy_db[]       — averaged power spectra (dBFS), per bin
//    coherence[]                — γ² = |S_xy|²/(S_xx·S_yy), true complex coherence
//    tf_raw_mag_db[]            — H1 = √(S_xy_re²+S_xy_im²)/S_xx (dB)
//    phase_unwrapped[]          — continuous atan2(S_xy_im, S_xy_re), unwrapped
//    group_delay_ms[]           — –d(phase)/d(ω), real per-bin latency estimate
//    tf_cal_mag_db[]            — tf_raw minus calibration (or identity if no cal)
//    tf_cal_phase_rad[]         — phase minus calibration (or identity if no cal)
//    result_quality             — EXCELLENT/GOOD/MARGINAL/POOR from actual coherence
//    CalibrationWarnings        — which calibration conditions applied
//    calibration_provenance     — human-readable string for export and display
// =============================================================================
static void runProcessing() {
     memset(&s_result, 0, sizeof(s_result));


     const uint16_t n = s_accum.frames_accumulated;
     const double      inv = (n > 0) ? (1.0 / (double)n) : 0.0;


     // -------------------------------------------------------------------------
     // Step 1: Metadata
     // -------------------------------------------------------------------------
     s_result.result_valid            = true;
     s_result.capture_start_block     = s_capture_start_block;
     s_result.capture_end_block       = s_capture_end_block;     // stamped at last captured frame
     s_result.timestamp_ms            = millis();
     s_result.n_averages_completed = s_frames_captured;
     s_result.fft_size                = fftModeToSize(s_params.fft_mode);
     s_result.fft_mode                = s_params.fft_mode;
     s_result.window_function         = s_params.window_function;
     s_result.estimator               = s_params.estimator;
     s_result.stimulus                = s_params.stimulus;
     s_result.generator_active        = (s_params.stimulus != StimulusType::EXTERNAL);
     s_result.line_in_level           = SGTL5000_LINE_IN_LEVEL;


     // Use route metadata cached during CAPTURE — avoids reading a potentially
     // stale consumer block slot after capture has ended.
     s_result.source_node_ch = s_captured_source_ch;
     s_result.return_node_ch = s_captured_return_ch;
// -------------------------------------------------------------------------
// Step 2: Averaged auto-spectra and cross-spectrum
// -------------------------------------------------------------------------
// FIX [stack-budget]: previously these four FFT_BINS-sized double arrays were
// declared on the stack here (~16 KB) plus a float[FFT_BINS] phase_wrapped
// below (~2 KB) for a total of 18 KB on every measurement — far above the
// 4 KB worst-case threshold the rest of the firmware respects (AudioFrame
// is global precisely to avoid this). Moved to module-static storage; values
// are written before each read and only live for the duration of runProcessing.
// Static allocation is safe: measurement_engine is single-threaded and
// runProcessing() is never re-entered (PROCESSING state is exclusive).
static double mean_Sxx   [FFT_BINS];
static double mean_Syy   [FFT_BINS];
static double mean_Sxy   [FFT_BINS];     // mean S_xy_re per bin
static double mean_Sxy_im[FFT_BINS];     // mean S_xy_im per bin (non-zero from complex FFT)
for (int k = 0; k < FFT_BINS; k++) {
      mean_Sxx   [k] = s_accum.S_xx   [k] * inv;
      mean_Syy   [k] = s_accum.S_yy   [k] * inv;
      mean_Sxy   [k] = s_accum.S_xy_re[k] * inv;
      mean_Sxy_im[k] = s_accum.S_xy_im[k] * inv;        // non-zero from complex FFT path
}


// -------------------------------------------------------------------------
// Step 3: Per-bin products — coherence, H1, and spectra
// -------------------------------------------------------------------------
// Noise floor gate: bins where source power is below this are "unenergised".
const double SOURCE_GATE_POWER = (double)TF_SOURCE_GATE * (double)TF_SOURCE_GATE;


// Analysis band for quality grading and valid_bin_fraction.
// Matches VALIDATION_FREQ_MIN/MAX and insights_engine analysis band.
// Sub-bass and near-Nyquist bins are naturally poorly energised even with
// good stimulus — counting them against quality produces false downgrades.
const float canonical_bin_hz         = (float)SAMPLE_RATE / (float)(FFT_BINS * 2);
const int        k_analysis_lo       = (int)(MEAS_ANALYSIS_LOW_HZ   / canonical_bin_hz);
const int        k_analysis_hi       = (int)(MEAS_ANALYSIS_HIGH_HZ / canonical_bin_hz);
const int        analysis_band_bins = k_analysis_hi - k_analysis_lo + 1;


// FIX [stack-budget]: moved to static storage — see mean_S* note above.
static float phase_wrapped[FFT_BINS];    // Intermediate: atan2 output, for unwrapping
int     energised_count = 0;             // energised bins in analysis band only
float coherence_sum        = 0.0f;       // sum over analysis band energised bins


for (int k = 0; k < FFT_BINS; k++) {
      double Sxx = mean_Sxx[k];
      double Syy = mean_Syy[k];
      double Sxy = mean_Sxy[k];        // real part of mean cross-spectrum


      // Auto-spectra in dBFS.
      // Power → dBFS: 10 * log10(power). The magnitudes in AudioRawBlock are
      // normalised to [0,1] where 1.0 = full scale. Power = magnitude^2.
      // 10 * log10(magnitude^2) = 20 * log10(magnitude), same as dBFS.
      s_result.S_xx_db[k] = (Sxx > 0) ? (float)(10.0 * log10(Sxx)) : -120.0f;
      s_result.S_yy_db[k] = (Syy > 0) ? (float)(10.0 * log10(Syy)) : -120.0f;
if (Sxx < SOURCE_GATE_POWER) {
    // Unenergised bin — source had insufficient energy.
    // Coherence is 0.0f (valid sentinel for "no data", used by
    //   insights_engine and calStore_saveFromResult).
    // All derived TF products are NAN, not 0.0f.
    // This is critical: zeros look like real 0 dB / 0 rad / 0 ms
    // measurements to export consumers and external analysis tools.
    // NAN propagates through arithmetic and is unambiguously absent.
    s_result.coherence[k]         = 0.0f;
    s_result.tf_raw_mag_db[k]     = NAN;
    s_result.tf_cal_mag_db[k]     = NAN;
    s_result.tf_cal_phase_rad[k] = NAN;
    phase_wrapped[k]              = NAN;    // propagates through unwrap
    s_result.phase_unwrapped[k]   = NAN;
    s_result.group_delay_ms[k]    = NAN;
    continue;
}
// Only count this bin toward quality metrics if it is in the
// analysis band (200 Hz – 10 kHz). Sub-bass and near-Nyquist bins
// are allowed to be weak without penalising overall quality.
if (k >= k_analysis_lo && k <= k_analysis_hi) {
    energised_count++;
}


// Coherence: γ²[k] = |S_xy[k]|² / (S_xx[k] * S_yy[k])
// Complex cross-spectrum: |S_xy|² = S_xy_re² + S_xy_im²
// (the imaginary part is non-zero on the CMSIS-DSP complex FFT path).
// Range: 0.0 (no correlation) to 1.0 (perfect correlation).
// High coherence means the return is consistently related to the source
// at this frequency — indicates a stable linear system response.
// Low coherence means noise, nonlinearity, or insufficient stimulus.
float gamma2 = 0.0f;
double Sxy_im = mean_Sxy_im[k];    // always in scope for coherence, H1, and phase
if (Syy > 0) {
    // |S_xy|² = S_xy_re² + S_xy_im² — correct for complex cross-spectrum
    double numerator = Sxy*Sxy + Sxy_im*Sxy_im;
    gamma2 = (float)(numerator / (Sxx * Syy));
    gamma2 = constrain(gamma2, 0.0f, 1.0f);
}
s_result.coherence[k] = gamma2;
if (k >= k_analysis_lo && k <= k_analysis_hi) {
    coherence_sum += gamma2;
}


// H1 transfer function magnitude: |S_xy| / S_xx in dB.
// Sxy_im declared before the coherence block — in scope for H1 and phase.
double H1_mag = sqrt(Sxy*Sxy + Sxy_im*Sxy_im) / Sxx;      // |S_xy| / S_xx
     float   H1_dB   = (H1_mag > 0) ? (float)(20.0 * log10(H1_mag)) : -120.0f;
     H1_dB = constrain(H1_dB, TF_DB_MIN - 6.0f, TF_DB_MAX + 6.0f);
     s_result.tf_raw_mag_db[k] = H1_dB;


     // Phase: arg(S_xy[k]) = atan2(S_xy_im, S_xy_re).
     phase_wrapped[k] = atan2f((float)Sxy_im, (float)Sxy);
}


// -------------------------------------------------------------------------
// Step 4: Phase unwrapping
// -------------------------------------------------------------------------
// phase_wrapped[] now contains true per-bin phase from atan2(S_xy_im, S_xy_re).
// Range [-π, +π]. unwrapPhase() produces a continuous (non-wrapping) curve
// representing the total phase transfer of the system vs frequency.
// With a broadband stimulus and high coherence, this reflects system group delay
// and any frequency-dependent phase shift (e.g. all-pass filters, cable effects).
unwrapPhase(phase_wrapped, s_result.phase_unwrapped, FFT_BINS);


// -------------------------------------------------------------------------
// Step 5: Group delay from phase derivative
// -------------------------------------------------------------------------
// Group delay is now derived from true continuous unwrapped phase.
// tau[k] = -d(phase)/d(omega) estimates the propagation delay at each frequency.
// For a system with flat group delay (e.g. a cable with only capacitance), this
// will be approximately constant across frequency. For a digital reverb or delay
// pedal, it will show a clear broadband offset equal to the hardware latency.
// For minimum-phase systems, group delay rises at the resonant frequency.
//
// Algorithm: central finite difference of unwrapped phase over omega.
// tau[k] = -d(phase)/d(omega)
//
// FIX [canonical-grid]: phase_unwrapped[] is on the canonical 512-bin result
// grid regardless of the internal FFT mode used during accumulation. The
// canonical bin spacing is SAMPLE_RATE / (FFT_BINS * 2), not SAMPLE_RATE / FFT_SIZE.
// These are equal only for MODE_LIVE (where FFT_SIZE == FFT_BINS * 2 == 1024).
// For MODE_PRECISION and MODE_LF the internal FFT is larger, but the result
// has been rebinned to the canonical grid before reaching this code.
// Using FFT_SIZE here would give correct omega spacing for MODE_LIVE but
// wrong spacing for precision modes — a subtle but real accuracy error.
const float delta_omega = 2.0f * (float)M_PI * canonical_bin_hz;


s_result.group_delay_ms[0] = NAN;         // Edge bin: central-difference undefined
for (int k = 1; k < FFT_BINS - 1; k++) {
     float d_phase     = s_result.phase_unwrapped[k+1] - s_result.phase_unwrapped[k-1];
     float d_omega     = 2.0f * delta_omega;    // Two-bin central difference span
     float tau_s       = -d_phase / d_omega;    // Seconds (negative sign by convention)
     s_result.group_delay_ms[k] = tau_s * 1000.0f;
}
s_result.group_delay_ms[FFT_BINS-1] = NAN;         // Edge bin: central-difference undefined


// -------------------------------------------------------------------------
// Step 6: Apply calibration correction
// -------------------------------------------------------------------------
// calibrated_mag_db[k]      = tf_raw_mag_db[k]       - cal.cal_mag_db[k]
// calibrated_phase_rad[k] = phase_unwrapped[k]       - cal.cal_phase_rad[k]
//
// Subtraction is correct because the calibration stores the loopback
// transfer function (what the hardware adds), and we remove it from
// the measurement (what the DUT + hardware adds together).
//
// Bins where bin_valid[k] is false had insufficient loopback coherence —
// the correction for those bins is zero (identity), flagged as partial.
{
     uint16_t meas_fft_size = fftModeToSize(s_params.fft_mode);
     CalibrationValidity validity = CalibrationValidity::MISSING;
     if (s_params.apply_calibration) {
         validity = calStore_isValid(s_params.fft_mode,
                                       meas_fft_size, SAMPLE_RATE,
                                       s_params.window_function,
                                       SGTL5000_LINE_IN_LEVEL);
     }


     const CalibrationBuffer& cal = calStore_getBuffer();
     bool partial = false;


     switch (validity) {
         case CalibrationValidity::VALID:
         case CalibrationValidity::SOFT_MISMATCH: {
             // Apply correction — subtract the loopback TF from the raw measurement
             for (int k = 0; k < FFT_BINS; k++) {
                 if (cal.bin_valid[k]) {
                     s_result.tf_cal_mag_db       [k] = s_result.tf_raw_mag_db[k]
                                                        - cal.cal_mag_db[k];
                     s_result.tf_cal_phase_rad[k] = s_result.phase_unwrapped[k]
                                                        - cal.cal_phase_rad[k];
                 } else {
                     // Invalid calibration bin — identity correction
                     s_result.tf_cal_mag_db       [k] = s_result.tf_raw_mag_db[k];
                     s_result.tf_cal_phase_rad[k] = s_result.phase_unwrapped[k];
                     partial = true;
                 }
             }
             s_result.calibration_applied = true;
             s_result.calibration_type      = cal.type;
    s_result.calibration_warnings.calibration_missing                 = false;
    s_result.calibration_warnings.line_in_level_mismatch              =
           (validity == CalibrationValidity::SOFT_MISMATCH);
    s_result.calibration_warnings.partial_calibration_applied         = partial;
    s_result.calibration_warnings.calibration_from_import             =
           (cal.type == CalibrationType::USER_IMPORTED);
    snprintf(s_result.calibration_provenance,
                sizeof(s_result.calibration_provenance),
                "%s%s", cal.description,
                (validity == CalibrationValidity::SOFT_MISMATCH)
                    ? " [level mismatch]" : "");
    Serial.printf("[MeasEngine] Calibration applied: '%s'%s%s\n",
                     cal.description,
                     (validity == CalibrationValidity::SOFT_MISMATCH)
                         ? " (soft: level mismatch)" : "",
                     partial ? " (partial: some bins invalid)" : "");
    break;
}


case CalibrationValidity::HARD_MISMATCH: {
    // Hard mismatch — do not apply, copy raw as calibrated
    memcpy(s_result.tf_cal_mag_db,          s_result.tf_raw_mag_db,
              FFT_BINS * sizeof(float));
    memcpy(s_result.tf_cal_phase_rad, s_result.phase_unwrapped,
              FFT_BINS * sizeof(float));
    s_result.calibration_applied = false;
    s_result.calibration_warnings.calibration_missing = false;
    // FIX [hard-mismatch-warning]: previously this branch surfaced no flag at
    // all, so downstream consumers (display, insights, export) could not tell
    // "no calibration loaded" apart from "loaded calibration was rejected as
    // incompatible". The new hard_parameter_mismatch bit makes the rejection
    // explicit. See CalibrationWarnings in measurement_core.h.
    s_result.calibration_warnings.hard_parameter_mismatch = true;
    Serial.println("[MeasEngine] Calibration NOT applied: hard parameter mismatch (FFT size, "
                   "sample rate, window, or quality mode).");
    snprintf(s_result.calibration_provenance,
                sizeof(s_result.calibration_provenance),
                "hard mismatch — not applied");
    break;
}


default:     // MISSING or apply_calibration == false
    memcpy(s_result.tf_cal_mag_db,          s_result.tf_raw_mag_db,
              FFT_BINS * sizeof(float));
    memcpy(s_result.tf_cal_phase_rad, s_result.phase_unwrapped,
              FFT_BINS * sizeof(float));
    s_result.calibration_applied = false;
    // calibration_missing is true only when the user requested calibration
    // AND none was loaded. Opting out of calibration is not a "missing" warning.
    s_result.calibration_warnings.calibration_missing =
           s_params.apply_calibration && (validity == CalibrationValidity::MISSING);
    snprintf(s_result.calibration_provenance,
                sizeof(s_result.calibration_provenance),
                s_cfft_ready
                    ? (s_params.apply_calibration
                             ? "none — no calibration loaded"
                                  : "none — calibration not requested")
                            : "none — magnitude fallback (cfft init failed)");
             break;
     }
}


// -------------------------------------------------------------------------
// Step 7: Health metrics
// -------------------------------------------------------------------------
// valid_bin_fraction: energised in-band bins / total in-band bins.
// Grading over the analysis band only prevents naturally weak sub-bass
// and near-Nyquist bins from penalising an otherwise good measurement.
s_result.valid_bin_fraction = (analysis_band_bins > 0)
     ? (float)energised_count / (float)analysis_band_bins : 0.0f;
s_result.mean_coherence = (energised_count > 0)
     ? coherence_sum / (float)energised_count : 0.0f;
s_result.clip_detected        = (s_accum.clip_source_count + s_accum.clip_return_count) > 0;
s_result.clip_source_count = s_accum.clip_source_count;
s_result.clip_return_count = s_accum.clip_return_count;


// -------------------------------------------------------------------------
// Step 8: Grade result quality
// -------------------------------------------------------------------------
s_result.result_quality = gradeQuality(
     s_result.mean_coherence,
     s_result.valid_bin_fraction,
     s_result.clip_detected
);


// -------------------------------------------------------------------------
// Step 9: Firmware context
// -------------------------------------------------------------------------
// Calibration status is set in Step 6 above. This step records firmware version.
// (Nothing else to do here — provenance and warnings are already set.)


// FIX [format-string]: pass FIRMWARE_VERSION via "%s" so accidentally
// introducing a '%' in the version macro can't trigger format-string UB.
snprintf(s_result.firmware_version,
          sizeof(s_result.firmware_version), "%s", FIRMWARE_VERSION);


Serial.printf("[MeasEngine] Processing complete. "
               "Frames: %d, coherence: %.2f, valid bins: %.0f%%, quality: %s\n",
               s_frames_captured,
               s_result.mean_coherence,
               s_result.valid_bin_fraction * 100.0f,
               (s_result.result_quality == ResultQuality::EXCELLENT) ? "EXCELLENT" :
               (s_result.result_quality == ResultQuality::GOOD)           ? "GOOD" :
               (s_result.result_quality == ResultQuality::MARGINAL)       ? "MARGINAL" :
               (s_result.result_quality == ResultQuality::POOR)           ? "POOR" : "INVALID");
}   // end runProcessing()


// =============================================================================
// PUBLIC FUNCTION IMPLEMENTATIONS
// =============================================================================


// -----------------------------------------------------------------------------
// measurementEngine_init()
// -----------------------------------------------------------------------------
void measurementEngine_init() {
     s_state         = MeasurementState::IDLE;
     s_abort_reason = AbortReason::NONE;
     s_frames_captured = 0;
     s_self_test_step   = 0;
     s_initialised      = true;
     memset(&s_result, 0, sizeof(s_result));
     memset(&s_accum,   0, sizeof(s_accum));


     // Pre-compute Hann window coefficients for FFT_SIZE points.
     // Only needs to happen once; coefficients never change.
     for (int n = 0; n < FFT_SIZE; n++) {
         s_hann_window[n] = 0.5f * (1.0f - cosf(2.0f * (float)M_PI * n / (FFT_SIZE - 1)));
     }


     // Initialise CMSIS-DSP complex FFT instance for FFT_SIZE-point transform.
     // Teensyduino 1.60 exposes precomputed CMSIS CFFT instances rather than
     // arm_cfft_init_f32(). Point at the 1024-point flash-resident table.
     s_cfft_instance = &arm_cfft_sR_f32_len1024;
     s_cfft_ready = true;
     Serial.println("[MeasEngine] CMSIS-DSP arm_cfft_f32 ready (FFT_SIZE="
                    STRINGIFY(FFT_SIZE) ")");


     Serial.println("[MeasEngine] Measurement engine initialised (v0.5 — complex FFT path).");
     Serial.println("[MeasEngine] State: IDLE. Call measurementEngine_arm() to begin.");


     // Arm the power-on self-test. It will run during the first calls to
     // measurementEngine_update() without blocking setup().
     measurementEngine_runSelfTest();
}


// -----------------------------------------------------------------------------
// measurementEngine_update()
// Drives the state machine. Called once per main loop iteration.
// Returns MeasurementEvent::NONE most of the time.
// -----------------------------------------------------------------------------
MeasurementEvent measurementEngine_update() {


    if (!s_initialised) return MeasurementEvent::NONE;


    switch (s_state) {


        // -----------------------------------------------------------------------
        case MeasurementState::IDLE:
        case MeasurementState::RESULT:
        case MeasurementState::ABORTED:
            // No-op. Waiting for external action (arm, acknowledge, etc.)
            return MeasurementEvent::NONE;


        // -----------------------------------------------------------------------
        case MeasurementState::ARMED: {
            // Check arm timeout
            if (s_params.arm_timeout_ms > 0 &&
                (millis() - s_arm_start_ms) > s_params.arm_timeout_ms) {
                return abortTo(AbortReason::TIMEOUT);
            }


            // Drive generator forward if using internal stimulus
            if (s_params.stimulus != StimulusType::EXTERNAL) {
                bool gen_started = signalGen_update();
                if (signalGen_getState() == GeneratorState::MISSED) {
                    return abortTo(AbortReason::GENERATOR_MISSED);
                }
                if (gen_started) {
                    // Generator has started on the target block — begin capture
                    s_capture_start_block = signalGen_getActualStartBlock();
                    s_frames_captured        = 0;
                    memset(&s_accum, 0, sizeof(s_accum));
                    s_accum.frames_requested = s_params.n_averages;
                    s_accum.capture_start_block = s_capture_start_block;
                    s_accum.generator_start_block = s_capture_start_block;
                    s_accum.fft_mode                = s_params.fft_mode;
                    s_accum.window_function         = s_params.window_function;
                    s_accum.estimator               = s_params.estimator;
                    s_accum.stimulus                = s_params.stimulus;
                    s_capture_end_block = s_capture_start_block;      // will be updated per fram
                    audioCap_beginRawCapture();       // arm raw queues for complex FFT path
                    transitionTo(MeasurementState::CAPTURE);
                    return MeasurementEvent::STATE_CHANGED;
        }
        return MeasurementEvent::NONE;
    }


    // EXTERNAL stimulus: wait for source level above a minimum threshold.
    // Use the CONSUMER_MEASURE block if fresh.
    if (audioCap_isBlockFresh(AudioConsumer::MEASURE)) {
        const AudioRawBlock& blk = audioCap_getBlock(AudioConsumer::MEASURE);
        audioCap_markConsumed(AudioConsumer::MEASURE);


        // Level threshold: source must be above –40 dBFS to begin capture.
        // This prevents accumulating frames of silence before the signal
        // arrives, which would bias the TF toward 0 dB.
        if (blk.peak_source_dbfs > -40.0f) {
            s_capture_start_block = blk.audio_block_counter;
            s_frames_captured        = 0;
            memset(&s_accum, 0, sizeof(s_accum));
            s_accum.frames_requested        = s_params.n_averages;
            s_accum.capture_start_block = s_capture_start_block;
            s_accum.fft_mode                = s_params.fft_mode;
            s_accum.window_function         = s_params.window_function;
            s_accum.estimator               = s_params.estimator;
            s_accum.stimulus                = s_params.stimulus;
            audioCap_beginRawCapture();       // arm raw queues for complex FFT path
            transitionTo(MeasurementState::CAPTURE);
            return MeasurementEvent::STATE_CHANGED;
        }
    }
    return MeasurementEvent::NONE;
}


// -----------------------------------------------------------------------
case MeasurementState::CAPTURE: {


    // Drive generator if active
    if (s_params.stimulus != StimulusType::EXTERNAL) {
        signalGen_update();
        if (signalGen_getState() == GeneratorState::MISSED) {
            return abortTo(AbortReason::GENERATOR_MISSED);
        }
    }


    // Consume a fresh CONSUMER_MEASURE block
    if (!audioCap_isBlockFresh(AudioConsumer::MEASURE)) {
        return MeasurementEvent::NONE;
    }
    const AudioRawBlock& blk = audioCap_getBlock(AudioConsumer::MEASURE);
audioCap_markConsumed(AudioConsumer::MEASURE);


// Cache route metadata from the first capture block.
if (s_frames_captured == 0) {
     s_captured_source_ch = blk.source_node_ch;
     s_captured_return_ch = blk.return_node_ch;
}


// Check clipping abort condition
if (s_params.abort_on_clip &&
     (blk.source_clipping || blk.return_clipping)) {
     AbortReason r = blk.source_clipping ? AbortReason::CLIP_SOURCE
                                              : AbortReason::CLIP_RETURN;
     return abortTo(r);
}
// Track clipping counts even without abort
if (blk.source_clipping) s_accum.clip_source_count++;
if (blk.return_clipping)     s_accum.clip_return_count++;


// ---------------------------------------------------------------
// COMPLEX FFT ACCUMULATION — True cross-spectrum from raw samples
// ---------------------------------------------------------------
// We now have two data paths in parallel:
//
// PATH A — AudioRawBlock magnitudes (always available):
//    Used only for: clipping detection, peak levels, display.
//    NOT used for complex accumulation.
//
// PATH B — AudioRecordQueue raw samples (armed at CAPTURE entry):
//    FFT_SIZE/AUDIO_BLOCK_SAMPLES = 8 blocks per FFT frame.
//    Provides true time-domain samples → Hann window → CMSIS FFT
//    → true complex S_xy_im → real phase via atan2.
//
// We wait until 8 blocks of raw samples are in the queue before
// computing one complex FFT frame. This is independent of the
// AudioRawBlock rate (which averages FFT_AVERAGE_COUNT=4 frames).
if (!s_cfft_ready) {
     // Fall back to magnitude accumulation if CMSIS-DSP failed to init.
     // This produces magnitude-domain results (old behaviour) with a warning.
     for (int k = 0; k < FFT_BINS; k++) {
         double src = (double)blk.fft_source[k];
         double ret = (double)blk.fft_return[k];
         s_accum.S_xx     [k] += src * src;
         s_accum.S_yy     [k] += ret * ret;
         s_accum.S_xy_re[k] += src * ret;
         s_accum.S_xy_im[k] += 0.0;
         s_accum.X_re     [k] += src;
           s_accum.Y_re     [k] += ret;
    }
    s_accum.frames_accumulated++;
    s_frames_captured++;
    s_capture_end_block = audioCap_getBlockCounter();           // timestamp of this frame
} else {
    // Drain one FFT frame (BLOCKS_PER_FFT = 8 blocks = 1024 samples)
    // from the AudioRecordQueue when enough samples are available.
    // This may not happen on every AudioRawBlock iteration — the queues
    // fill 8× as fast as AudioRawBlocks post, so we drain when ready.
    while (audioCap_rawSamplesAvailable() >= BLOCKS_PER_FFT) {


           // Get raw float32 samples for this FFT frame
           if (!audioCap_getRawSamples(s_raw_src, s_raw_ret, BLOCKS_PER_FFT)) {
               break;     // Shouldn't happen after availability check, but guard
           }


           // Apply Hann window and pack into interleaved complex array.
           // arm_cfft_f32() expects: [re0, im0, re1, im1, ..., re(N-1), im(N-1)]
           // Time-domain samples are real → imaginary part = 0.
           for (int n = 0; n < FFT_SIZE; n++) {
               float w = s_hann_window[n];
               s_fft_src_cx[2*n]          = s_raw_src[n] * w;    // re
               s_fft_src_cx[2*n + 1] = 0.0f;                      // im (real signal)
               s_fft_ret_cx[2*n]          = s_raw_ret[n] * w;    // re
               s_fft_ret_cx[2*n + 1] = 0.0f;                      // im (real signal)
           }


           // Forward complex FFT (in-place).
           // ifftFlag=0 → forward, bitReverseFlag=1 → output in natural order.
           arm_cfft_f32(s_cfft_instance, s_fft_src_cx, 0, 1);
           arm_cfft_f32(s_cfft_instance, s_fft_ret_cx, 0, 1);


           // Accumulate cross-spectrum over the positive-frequency bins only.
           // FFT output: bins 0..FFT_SIZE-1. Positive freq: 0..FFT_BINS-1 (512).
           // Bin 0 = DC, bin FFT_BINS-1 = Nyquist.
           // Scale factor: 1/FFT_SIZE for amplitude normalisation.
           // We apply it here so the accumulated sums stay in a sensible range.
           const double fft_scale = 1.0 / (double)FFT_SIZE;
           for (int k = 0; k < FFT_BINS; k++) {
               // Complex source spectrum: X[k] = fft_src_cx[2k] + j*fft_src_cx[2k+1
               double Xre = (double)s_fft_src_cx[2*k]           * fft_scale;
               double Xim = (double)s_fft_src_cx[2*k + 1] * fft_scale;
               // Complex return spectrum: Y[k]
               double Yre = (double)s_fft_ret_cx[2*k]           * fft_scale;
               double Yim = (double)s_fft_ret_cx[2*k + 1] * fft_scale;
                 // Auto-spectra: S_xx[k] += |X[k]|², S_yy[k] += |Y[k]|²
                 s_accum.S_xx[k] += Xre*Xre + Xim*Xim;
                 s_accum.S_yy[k] += Yre*Yre + Yim*Yim;


                 // Cross-spectrum: S_xy[k] += conj(X[k]) * Y[k]
                 //     = (Xre - j*Xim)(Yre + j*Yim)
                 //     = (Xre*Yre + Xim*Yim) + j*(Xre*Yim - Xim*Yre)
                 s_accum.S_xy_re[k] += (Xre*Yre + Xim*Yim);     // real part
                 s_accum.S_xy_im[k] += (Xre*Yim - Xim*Yre);     // imaginary part


                 // Store X and Y directly for H2 estimator (future)
                 s_accum.X_re[k] += Xre;     s_accum.X_im[k] += Xim;
                 s_accum.Y_re[k] += Yre;     s_accum.Y_im[k] += Yim;
            }
            s_accum.frames_accumulated++;
            s_frames_captured++;
            s_capture_end_block = audioCap_getBlockCounter();     // timestamp of this frame


            // Stop accumulating if we've reached the requested frame count
            if (s_frames_captured >= s_params.n_averages) break;
        }
    }


    // Check for sweep completion
    if (s_params.stimulus == StimulusType::INTERNAL_LOG_SWEEP) {
        uint32_t produced     = signalGen_getSweepSamplesProduced();
        uint32_t total_dur = signalGen_getSweepSamplesDuration();
        if (total_dur > 0 && produced >= total_dur) {
            // Sweep ended — close capture regardless of frame count
            signalGen_stop();
            goto do_processing;
        }
    }


    // Normal completion: enough frames accumulated
    if (s_frames_captured >= s_params.n_averages) {
        goto do_processing;
    }
    return MeasurementEvent::NONE;


do_processing:
    signalGen_stop();
    audioCap_endRawCapture();      // disarm queues — capture window closed
    transitionTo(MeasurementState::PROCESSING);
    // Fall through immediately — PROCESSING runs to completion
}
// FALL THROUGH intentional
// -----------------------------------------------------------------------
case MeasurementState::PROCESSING: {
    // Runs to completion. Produces MeasurementResult.
    runProcessing();
    transitionTo(MeasurementState::RESULT);
    return MeasurementEvent::RESULT_READY;
}


// -----------------------------------------------------------------------
case MeasurementState::EXPORTING: {
    // Synchronous export — runs to completion (≈200 ms at FAT SD speed).
    // EXPORTING is entered via measurementEngine_exportToSD(); s_export_filename
    // was set there. The result remains valid after export.
    bool ok = exportEngine_saveMeasurement(s_result, s_export_filename, nullptr);
    transitionTo(MeasurementState::RESULT);
    return ok ? MeasurementEvent::EXPORT_COMPLETE : MeasurementEvent::EXPORT_FAILED;
}


// -----------------------------------------------------------------------
case MeasurementState::SELF_TEST: {
    // Pipeline liveness check: confirms the audio capture block counter is
    // advancing, meaning the I2S interrupt and Audio Library are alive.
    //
    // This is NOT a signal-path loopback test. It cannot detect:
    //       • codec communication failure (SGTL5000 not responding)
    //       • analog signal path faults (open input, bad connection)
    //       • DSP measurement accuracy (TF, coherence, phase)
    //
    // For signal-path validation: run the validation suite ('v' command).
    // That suite tests the full acquisition → FFT → TF pipeline with a
    // known stimulus and expected result.
    switch (s_self_test_step) {
         case 0: {
                // Wait for at least one new ISR block to confirm pipeline is live.
                // s_self_test_baseline_block was captured in runSelfTest() — we
                // confirm the counter has advanced past that snapshot.
                uint32_t now = audioCap_getBlockCounter();
                if (now > s_self_test_baseline_block) {
                    s_self_test_step = 1;
                }
                return MeasurementEvent::NONE;
         }
         case 1: {
                Serial.println("[MeasEngine] Startup check: audio pipeline alive "
                               "(I2S + Audio Library producing blocks).");
                Serial.println("[MeasEngine] For full signal-path validation, run 'v'.");
                    transitionTo(MeasurementState::IDLE);
                    s_self_test_step = 0;
                    return MeasurementEvent::SELF_TEST_PASSED;
                }
                default:
                    transitionTo(MeasurementState::IDLE);
                    return MeasurementEvent::NONE;
            }
        }
    }
    return MeasurementEvent::NONE;
}


// -----------------------------------------------------------------------------
// measurementEngine_arm(params)
// -----------------------------------------------------------------------------
bool measurementEngine_arm(const MeasurementParams& params) {
    if (s_state != MeasurementState::IDLE &&
        s_state != MeasurementState::RESULT) {
        Serial.println("[MeasEngine] arm() rejected: not in IDLE or RESULT state");
        return false;
    }
    if (!validateParams(params)) return false;


    // Guard 1: MODE_PRECISION and MODE_LF are not yet implemented.
    // Reject rather than silently running MODE_LIVE under the wrong label.
    if (params.fft_mode == FftMode::MODE_PRECISION ||
        params.fft_mode == FftMode::MODE_LF) {
        Serial.printf("[MeasEngine] arm() rejected: fft_mode %d "
                        "(PRECISION/LF) not yet implemented. "
                        "Use MODE_LIVE.\n", (int)params.fft_mode);
        return false;
    }


    // Guard 2: H2 and HV estimators are not yet implemented.
    // The processing path computes |S_xy|/S_xx (H1) unconditionally.
    // Allowing H2/HV would record the wrong estimator in result metadata.
    if (params.estimator != TfEstimator::H1) {
        Serial.printf("[MeasEngine] arm() rejected: estimator %d "
                        "(H2/HV) not yet implemented. Use H1.\n",
                        (int)params.estimator);
        return false;
    }


    // Warning: internal stimulus does not yet reach the DUT (RIG SEND jack).
    // The generator state machine runs correctly and the output is audible
    // on the monitoring path, but DUT injection is pending signal_router.
// Measurements will capture the rig's response to whatever signal is
// present on RETURN_NODE — not the intended controlled stimulus.
// Use EXTERNAL stimulus for real rig measurements.
if (params.stimulus != StimulusType::EXTERNAL) {
     Serial.println("[MeasEngine] WARNING: internal stimulus selected — "
                      "DUT injection not yet wired. Results will not "
                      "reflect controlled stimulus.");
     Serial.println("[MeasEngine] Use EXTERNAL stimulus for real rig measurements.");
}


s_params          = params;
s_abort_reason = AbortReason::NONE;
s_arm_start_ms = millis();
s_frames_captured = 0;
memset(&s_accum, 0, sizeof(s_accum));


// For internal stimulus: arm the generator at current_block + 4
// (4 blocks ≈ 12 ms margin — safely in the future)
//
// NOTE [generator-stub]: signal_generator.cpp declares AudioSynthWaveformSine
// and AudioSynthNoiseWhite but their output is NOT yet connected to the audio graph
// (pending signal_router hardware design). The generator state machine runs
// correctly (ARMED → ACTIVE, block-aligned timing), but the DUT will not
// receive the generated stimulus until the injection wiring is completed.
// Measurements with EXTERNAL stimulus are not affected by this limitation.
// Measurements with internal stimulus will capture the rig's response to
// whatever signal happens to be present, not the intended controlled stimulus.
if (params.stimulus != StimulusType::EXTERNAL) {
     GeneratorConfig gen_cfg{};
     gen_cfg.type             = params.stimulus;
     gen_cfg.amplitude_dbfs = params.stimulus_amplitude_dbfs;
     gen_cfg.sine_freq_hz     = params.stimulus_freq_hz;
     gen_cfg.sweep_start_hz = params.sweep_start_hz;
     gen_cfg.sweep_end_hz     = params.sweep_end_hz;
     gen_cfg.sweep_duration_s = params.sweep_duration_s;


     signalGen_configure(gen_cfg);
     uint32_t start_block = audioCap_getBlockCounter() + 4;
     if (!signalGen_startAtBlock(start_block)) {
           Serial.println("[MeasEngine] arm() failed: generator could not be armed");
           return false;
     }
}


transitionTo(MeasurementState::ARMED);
Serial.printf("[MeasEngine] Armed: %d averages, mode=%d, stimulus=%d\n",
                 params.n_averages,
                   (int)params.fft_mode,
                   (int)params.stimulus);
    return true;
}


// -----------------------------------------------------------------------------
// measurementEngine_cancel()
// -----------------------------------------------------------------------------
void measurementEngine_cancel() {
    if (s_state == MeasurementState::IDLE     ||
        s_state == MeasurementState::RESULT ||
        s_state == MeasurementState::ABORTED) {
        return;    // No-op
    }
    abortTo(AbortReason::USER_CANCEL);
}


// -----------------------------------------------------------------------------
// measurementEngine_notifyRouteChanged()
// -----------------------------------------------------------------------------
void measurementEngine_notifyRouteChanged() {
    // Route-change triggered abort: separate from user cancel so the abort
    // reason correctly identifies the cause (topology invalidation, not
    // explicit user action). The main loop calls this — not cancel() — when
    // audioCap_update() returns AudioCaptureEvent::ROUTE_CHANGED.
    if (s_state == MeasurementState::IDLE     ||
        s_state == MeasurementState::RESULT ||
        s_state == MeasurementState::ABORTED) {
        return;    // No-op — no measurement in progress
    }
    abortTo(AbortReason::ROUTE_CHANGED);
}


// -----------------------------------------------------------------------------
// measurementEngine_acknowledgeAbort()
// -----------------------------------------------------------------------------
void measurementEngine_acknowledgeAbort() {
    if (s_state == MeasurementState::ABORTED) {
        s_abort_reason = AbortReason::NONE;
        transitionTo(MeasurementState::IDLE);
    }
}


// -----------------------------------------------------------------------------
// measurementEngine_returnToLive()
// -----------------------------------------------------------------------------
void measurementEngine_returnToLive() {
    if (s_state == MeasurementState::RESULT) {
        transitionTo(MeasurementState::IDLE);
    }
}


// -----------------------------------------------------------------------------
// measurementEngine_exportToSD(filename)
// -----------------------------------------------------------------------------
bool measurementEngine_exportToSD(const char* filename) {
    if (s_state != MeasurementState::RESULT) {
        Serial.println("[MeasEngine] exportToSD() ignored: not in RESULT state");
        return false;
    }
    if (!exportEngine_isAvailable()) {
        Serial.println("[MeasEngine] exportToSD() failed: export engine not available (SD?)");
        return false;
    }
    // Store the requested filename. EXPORTING state will read it.
    if (filename && filename[0] != '\0') {
        strncpy(s_export_filename, filename, EXPORT_FILENAME_LEN - 1);
        s_export_filename[EXPORT_FILENAME_LEN - 1] = '\0';
    } else {
        s_export_filename[0] = '\0';     // signal to generate a name
    }
    transitionTo(MeasurementState::EXPORTING);
    return true;
}


// -----------------------------------------------------------------------------
// measurementEngine_runSelfTest()
// -----------------------------------------------------------------------------
void measurementEngine_runSelfTest() {
    if (s_state != MeasurementState::IDLE) return;
    s_self_test_step = 0;
    s_self_test_baseline_block = audioCap_getBlockCounter();    // snapshot current counter
    transitionTo(MeasurementState::SELF_TEST);
    Serial.println("[MeasEngine] Self-test started.");
}


// =============================================================================
// STATE QUERIES
// =============================================================================


MeasurementState measurementEngine_getState() {
    return s_state;
}
AbortReason measurementEngine_getAbortReason() {
    return s_abort_reason;
}


const char* measurementEngine_getStateDescription() {
    switch (s_state) {
        case MeasurementState::IDLE:          return "IDLE";
        case MeasurementState::ARMED:         return "ARMED";
        case MeasurementState::CAPTURE:       return "CAPTURE";
        case MeasurementState::PROCESSING: return "PROCESSING";
        case MeasurementState::RESULT:        return "RESULT";
        case MeasurementState::EXPORTING:     return "EXPORTING";
        case MeasurementState::ABORTED:       return "ABORTED";
        case MeasurementState::SELF_TEST:     return "SELF_TEST";
        default:                              return "UNKNOWN";
    }
}


const char* measurementEngine_getAbortDescription() {
    switch (s_abort_reason) {
        case AbortReason::NONE:                     return "none";
        case AbortReason::USER_CANCEL:              return "user cancel";
        case AbortReason::CLIP_SOURCE:              return "SOURCE_NODE clipping";
        case AbortReason::CLIP_RETURN:              return "RETURN_NODE clipping";
        case AbortReason::TIMEOUT:                  return "armed timeout";
        case AbortReason::GENERATOR_MISSED:         return "generator missed start block";
        case AbortReason::ROUTE_CHANGED:            return "route changed mid-capture";
        case AbortReason::CALIBRATION_MISMATCH:     return "calibration parameter mismatch";
        case AbortReason::HARDWARE_FAULT:           return "hardware fault";
        default:                                    return "unknown";
    }
}


void measurementEngine_getCaptureProgress(uint16_t* completed, uint16_t* requested) {
    if (completed) *completed = s_frames_captured;
    if (requested) *requested = (s_state == MeasurementState::CAPTURE)
                                  ? s_params.n_averages : 0;
}


// =============================================================================
// RESULT ACCESS
// =============================================================================


const MeasurementResult& measurementEngine_getResult() {
    // Caller is responsible for checking state == RESULT before calling.
    return s_result;
}
// =============================================================================
// CONVENIENCE PARAMETER FACTORIES
// =============================================================================


MeasurementParams measureParams_rigAnalysis() {
    MeasurementParams p{};
    p.fft_mode               = FftMode::MODE_LIVE;     // demoted: MODE_PRECISION accumulator no
    p.window_function        = WindowFunction::HANN;
    p.n_averages             = 32;
    p.estimator              = TfEstimator::H1;
    p.stimulus               = StimulusType::EXTERNAL;     // DUT injection not yet wired
    p.apply_calibration      = true;
    p.arm_timeout_ms         = 10000;
    p.abort_on_clip          = true;
    return p;
}


MeasurementParams measureParams_cableCapacitance() {
    MeasurementParams p{};
    p.fft_mode               = FftMode::MODE_LIVE;     // demoted: MODE_PRECISION accumulator no
    p.window_function        = WindowFunction::HANN;
    p.n_averages             = 64;
    p.estimator              = TfEstimator::H1;
    p.stimulus               = StimulusType::INTERNAL_WHITE;
    p.stimulus_amplitude_dbfs = -6.0f;
    p.apply_calibration      = true;
    p.arm_timeout_ms         = 15000;
    p.abort_on_clip          = true;
    return p;
}


MeasurementParams measureParams_latency() {
    MeasurementParams p{};
    p.fft_mode               = FftMode::MODE_LIVE;
    p.window_function        = WindowFunction::HANN;
    p.n_averages             = 8;
    p.estimator              = TfEstimator::H1;
    p.stimulus               = StimulusType::INTERNAL_LOG_SWEEP;
    p.stimulus_amplitude_dbfs = -6.0f;
    p.sweep_start_hz         = 4000.0f;
    p.sweep_end_hz           = 44100.0f / 2.0f - 100.0f;
    p.sweep_duration_s       = 0.5f;
    p.apply_calibration      = true;
    p.arm_timeout_ms         = 5000;
    p.abort_on_clip          = true;
    return p;
}


MeasurementParams measureParams_impulseResponse() {
    MeasurementParams p{};
    p.fft_mode               = FftMode::MODE_LIVE;      // demoted: MODE_PRECISION accumulator no
    p.window_function        = WindowFunction::HANN;
    p.n_averages             = 8;
    p.estimator              = TfEstimator::H1;
    p.stimulus               = StimulusType::INTERNAL_LOG_SWEEP;
    p.stimulus_amplitude_dbfs = -6.0f;
    p.sweep_start_hz         = 20.0f;
    p.sweep_end_hz           = 20000.0f;
    p.sweep_duration_s       = 2.0f;
    p.apply_calibration      = true;
    p.arm_timeout_ms         = 10000;
    p.abort_on_clip          = true;
    return p;
}


MeasurementParams measureParams_selfCalibration() {
    MeasurementParams p{};
    p.fft_mode               = FftMode::MODE_LIVE;      // demoted: MODE_PRECISION accumulator no
    p.window_function        = WindowFunction::FLAT_TOP;
    p.n_averages             = 64;
    p.estimator              = TfEstimator::H1;
    p.stimulus               = StimulusType::EXTERNAL;     // DUT injection not yet wired
    p.apply_calibration      = false;      // Never apply cal during self-calibration
    p.arm_timeout_ms         = 15000;
    p.abort_on_clip          = true;
    return p;
}


MeasurementParams measureParams_humDetection() {
    MeasurementParams p{};
    p.fft_mode               = FftMode::MODE_LIVE;      // demoted: MODE_LF accumulator not yet i
    p.window_function        = WindowFunction::HANN;
    p.n_averages             = 32;
    p.estimator              = TfEstimator::H1;
    p.stimulus               = StimulusType::EXTERNAL;      // Listen passively for hum
    p.apply_calibration      = false;
    p.arm_timeout_ms         = 0;       // No timeout — wait indefinitely for signal
    p.abort_on_clip          = false;
    return p;
}
