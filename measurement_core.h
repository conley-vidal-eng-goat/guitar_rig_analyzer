// =============================================================================
// measurement_core.h     —   Guitar Rig Analyzer
// =============================================================================
// Core data structures for the precision measurement path.
//
// CHANGELOG v0.4.1     (last functional change — no logic changes since)
// ----------------
// FIX [fft-bins]: The previous version defined multiple FFT modes (1024,
//   4096, 8192) but sized all structs around FFT_BINS == 512, creating an
//   architectural contradiction: a 4096-point FFT produces 2048 bins, which
//   cannot fit into a 512-element array.
//
//   Resolution — PATH A (canonical 512-bin result grid):
//   MeasurementAccumulator, MeasurementResult, and CalibrationBuffer are ALL
//   fixed at FFT_BINS == 512 entries. This is the CANONICAL RESULT GRID.
//
//   Precision FFT modes (MODE_PRECISION = 4096pt, MODE_LF = 8192pt) operate
//   with larger internal accumulators INSIDE measurement_engine, but all
//   derived products (coherence, TF, phase, group delay) are RESAMPLED into
//   the 512-bin canonical grid before being written to MeasurementResult.
//   See PRECISION FFT REBINNING CONTRACT below.
//
//   This approach preserves:
//     • All existing file formats (CalibrationFile, fingerprint JSON)
//     • The entire memory budget (no struct size changes)
//     • Display engine assumptions (always 512 bins)
//     • All static_assert checks (unchanged)
//
// FIX [event-api]: measurement_core.h previously said MeasurementEvent is
//   observed via measurementEngine_pollEvent(). That function does not exist.
//   The actual mechanism is measurementEngine_update() returning a
//   MeasurementEvent. All comments corrected to match the actual API.
//
// FIX [threshold-ownership]: Previous comments said quality thresholds live
//   in config.h. They are defined in this header. Comments now correctly
//   state measurement_core.h as the owner of these thresholds.
//   config.h is the owner of hardware pin constants and audio engine tuning
//   (FFT_SIZE, SAMPLE_RATE, TF_SMOOTHING_ALPHA, etc.). Measurement-specific
//   constants belong here, alongside the structs that use them.
//
// =============================================================================
//
// PRECISION FFT REBINNING CONTRACT
// ---------------------------------
// When a precision FFT mode is used, measurement_engine maintains an
// INTERNAL accumulator sized for the larger FFT:
//
//   MODE_PRECISION (4096pt): internal bins = 2048, bin width = 10.8 Hz
//   MODE_LF           (8192pt): internal bins = 4096, bin width =   5.4 Hz
//
// After accumulation is complete (PROCESSING state), measurement_engine
// resamples all derived products onto the 512-bin canonical grid using
// linear interpolation in log-frequency space. The canonical grid covers
// the same 0–22,050 Hz range but at 43.1 Hz/bin resolution.
//
// WHY PATH A (fixed 512 bins) over Path B (variable bins)?
//   • File format stability: CalibrationFile and fingerprint JSON have fixed
//     array lengths. Path B would require versioned or variable-length formats.
//   • Display stability: display_engine iterates over FFT_BINS. Path B would
//     require display_engine to handle variable-length arrays.
//   • Memory predictability: fixed struct sizes make the memory budget exact.
//   • Calibration compatibility: a calibration taken in MODE_PRECISION must
//     be applicable to a measurement taken in MODE_LIVE. Fixed 512-bin
//     canonical grid makes this straightforward.
//
// WHAT PRECISION MODES ACTUALLY IMPROVE:
//   The benefit of 4096/8192-point FFTs is not more result bins — it is
//   better frequency resolution WITHIN the accumulator, which reduces
//   spectral leakage and produces more accurate bin magnitudes before
//   rebinning. The resampled result has higher per-bin accuracy even though
//   it has the same number of result bins.
//
//   Additionally, for low-frequency analysis (hum at 50/60 Hz), multiple
//   adjacent large-FFT bins can be averaged together before rebinning,
//   producing a more stable estimate than a single 43.1 Hz-wide live bin.
//
// INTERNAL ACCUMULATOR SIZING:
//   measurement_engine.cpp allocates its internal precision accumulators
//   as a separate buffer sized for the maximum precision FFT:
//     MAX_PRECISION_BINS = 8192 / 2 = 4096
//   These live in OCRAM (not DTCM) because of their size:
//     8 arrays × 4096 × 8 bytes (double) = 262,144 bytes (256 KB in OCRAM)
//   See memory budget in architecture baseline document.
//
// =============================================================================


#ifndef MEASUREMENT_CORE_H
#define MEASUREMENT_CORE_H


#include <Arduino.h>
#include "config.h"
// =============================================================================
// PRECISION FFT CONSTANTS
// =============================================================================
// Maximum internal bin count for precision modes (8192-point FFT → 4096 bins).
// Used to size the internal precision accumulator in measurement_engine.cpp.
// NOT used to size MeasurementResult or CalibrationBuffer (those are always 512).
#define MAX_PRECISION_BINS   4096     // 8192-pt FFT / 2


// =============================================================================
// SUPPORTING ENUMERATIONS
// =============================================================================


// -----------------------------------------------------------------------------
// FFT mode
// FIX [fft-bins]: Each mode now documents:
//    (a) the internal FFT size used during accumulation
//    (b) the internal bin count during accumulation
//    (c) the fact that derived products are resampled to 512 canonical bins
//
// *** ORDERING INVARIANT — DO NOT CHANGE NUMERIC VALUES ***
// calStore_isValid() (calibration_store.cpp) compares FftMode values as
// integers to determine calibration quality relative to measurement quality:
//    higher enum value = higher internal FFT resolution = higher quality
//    MODE_LIVE(0) < MODE_PRECISION(1) < MODE_LF(2)
// If a new mode is added, it must respect this ordering and calStore_isValid()
// must be reviewed. Assigning MODE_LF a value less than MODE_PRECISION, for
// example, would silently invert the hard/soft mismatch logic.
// -----------------------------------------------------------------------------
enum class FftMode : uint8_t {


     MODE_LIVE = 0,
     // Internal: 1024-point FFT, 512 bins, 43.1 Hz/bin, 23.2 ms/frame.
     // Result: 512 canonical bins (no rebinning needed — direct 1:1).
     // Use for: live display, quick spot checks, anything needing fast response.


     MODE_PRECISION = 1,
     // Internal: 4096-point FFT, 2048 bins, 10.8 Hz/bin, 92.9 ms/frame.
     // Result: resampled to 512 canonical bins (4:1 average in log-freq space).
     // Use for: rig analysis, cable measurements, pedal fingerprinting.
     // Internal accumulator lives in OCRAM.
     //
     // *** NOT YET IMPLEMENTED ***
     // The OCRAM large-FFT accumulator and rebinning step are not yet coded.
     // measurementEngine_arm() rejects MODE_PRECISION and returns false.
     // All factory functions that previously requested this mode have been
     // demoted to MODE_LIVE. This value is reserved for future implementation.
     MODE_LF = 2,
     // Internal: 8192-point FFT, 4096 bins, 5.4 Hz/bin, 185.8 ms/frame.
     // Result: resampled to 512 canonical bins (8:1 average in log-freq space).
     // Use for: hum detection (50/60 Hz), bass resonance analysis,
     //                pickup resonance below 200 Hz.
     // Internal accumulator lives in OCRAM.
     //
     // *** NOT YET IMPLEMENTED ***
     // Same status as MODE_PRECISION. Reserved for future implementation.
     // measurementEngine_arm() rejects MODE_LF and returns false.
};


inline uint16_t fftModeToSize(FftMode mode) {
     switch (mode) {
            case FftMode::MODE_LIVE:         return 1024;
            case FftMode::MODE_PRECISION: return 4096;
            case FftMode::MODE_LF:           return 8192;
            default:                         return 1024;
     }
}


// Number of internal bins for a given FFT mode (before rebinning)
inline uint16_t fftModeToInternalBins(FftMode mode) {
     return fftModeToSize(mode) / 2;
}


// -----------------------------------------------------------------------------
// Window function codes
// Window choice affects both spectral leakage and amplitude accuracy.
//       Hann:        good general-purpose; low sidelobes; use for most measurements
//       Blackman: better sidelobe rejection; slightly wider main lobe
//       FlatTop:     best amplitude accuracy per bin; poor frequency resolution
//                    Use for calibration and gain measurements.
//
// Window is stored in calibration files. Applying a calibration taken with
// Hann to a measurement taken with FlatTop is a HARD mismatch — different
// window shapes produce different per-bin amplitude scaling.
// -----------------------------------------------------------------------------
enum class WindowFunction : uint8_t {
     HANN           = 0,
     BLACKMAN = 1,
     FLAT_TOP = 2,
};


// -----------------------------------------------------------------------------
// Transfer function estimator
// H1: S_xy / S_xx     — optimal when return channel is noisier
// H2: S_yy / S_xy*    — optimal when source channel is noisier
// HV: geometric mean — unbiased when noise is symmetric (future)
// For internal generator stimulus, use H1 (source is clean).
// -----------------------------------------------------------------------------
enum class TfEstimator : uint8_t {
     H1 = 0,
     H2 = 1,
     HV = 2,    // Reserved — not yet implemented
};


// -----------------------------------------------------------------------------
// Stimulus type
// Generator amplitude is always dBFS in the public API.
// -----------------------------------------------------------------------------
enum class StimulusType : uint8_t {
     EXTERNAL             = 0,
     INTERNAL_SINE        = 1,
     INTERNAL_PINK        = 2,
     INTERNAL_WHITE       = 3,
     INTERNAL_LOG_SWEEP = 4,
};


// -----------------------------------------------------------------------------
// Result quality grade
// FIX [threshold-ownership]: Thresholds are defined in THIS header, not
// config.h. measurement_core.h is the owner of measurement-specific constants.
// config.h owns hardware constants (pins, codec levels, FFT_SIZE, SAMPLE_RATE).
// -----------------------------------------------------------------------------
enum class ResultQuality : uint8_t {
     EXCELLENT = 4,
     GOOD       = 3,
     MARGINAL   = 2,
     POOR       = 1,
     INVALID    = 0,   // Clipping, or too few bins to grade
};


// FIX [threshold-ownership]: Defined here, not in config.h.
// Adjust after real hardware characterisation (see validation advisory).


// Analysis band for quality grading and valid_bin_fraction.
// Sub-bass (< ANALYSIS_LOW_HZ) and near-Nyquist (> ANALYSIS_HIGH_HZ) bins
// are naturally poorly energised and excluded from quality metrics.
// Must match VALIDATION_FREQ_MIN/MAX in validation.h.
#define MEAS_ANALYSIS_LOW_HZ     200.0f
#define MEAS_ANALYSIS_HIGH_HZ    10000.0f
#define RESULT_QUALITY_EXCELLENT_COH          0.95f
#define RESULT_QUALITY_EXCELLENT_BINS         0.90f
#define RESULT_QUALITY_GOOD_COH               0.85f
#define RESULT_QUALITY_GOOD_BINS              0.75f
#define RESULT_QUALITY_MARGINAL_COH           0.70f
#define RESULT_QUALITY_MARGINAL_BINS          0.50f
// Any result with clip_detected = true → INVALID, regardless of coherence.


// -----------------------------------------------------------------------------
// Calibration type
// -----------------------------------------------------------------------------
enum class CalibrationType : uint8_t {
     INTERNAL_LOOPBACK = 0,
     EXTERNAL_LOOPBACK = 1,
     MICROPHONE             = 2,
     USER_IMPORTED          = 3,
};


// -----------------------------------------------------------------------------
// Calibration validity result (from calibration_store)
// -----------------------------------------------------------------------------
enum class CalibrationValidity : uint8_t {
     VALID           = 0,
     SOFT_MISMATCH = 1,        // Line-in level differs; phase valid, magnitude approximate
     HARD_MISMATCH = 2,        // FFT size, window, or sample rate mismatch — DO NOT apply
     MISSING         = 3,
};


// -----------------------------------------------------------------------------
// Measurement events
// FIX [event-api]: These events are returned by measurementEngine_update(),
// not by a separate measurementEngine_pollEvent() function (which does not
// exist). The main loop calls measurementEngine_update() once per iteration
// and observes the return value. There is no separate polling mechanism.
// -----------------------------------------------------------------------------
enum class MeasurementEvent : uint8_t {
     NONE               = 0,
     STATE_CHANGED      = 1,       // State transitioned; call measurementEngine_getState()
     RESULT_READY       = 2,       // RESULT state entered; call measurementEngine_getResult()
     EXPORT_COMPLETE    = 3,
     EXPORT_FAILED      = 4,
     SELF_TEST_PASSED = 5,
     SELF_TEST_FAILED = 6,
     ABORTED            = 7,       // Call measurementEngine_getAbortReason()
};


// -----------------------------------------------------------------------------
// Abort reasons
// -----------------------------------------------------------------------------
enum class AbortReason : uint8_t {
     NONE                   = 0,
     USER_CANCEL            = 1,
     CLIP_SOURCE            = 2,
     CLIP_RETURN            = 3,
     TIMEOUT                = 4,
     GENERATOR_MISSED       = 5,
     ROUTE_CHANGED          = 6,
     CALIBRATION_MISMATCH = 7,
     HARDWARE_FAULT         = 8,
};


// =============================================================================
// CALIBRATION WARNING FLAGS
// =============================================================================
struct CalibrationWarnings {
     bool calibration_missing;             // User requested calibration but none was loaded
     bool line_in_level_mismatch;          // Soft — phase valid, magnitude approximate
     bool partial_calibration_applied;     // Some bins had no valid cal data
     bool calibration_from_import;         // User-imported, not self-generated
     // FIX [hard-mismatch-warning]: previously there was no flag to indicate
     // that a loaded calibration was rejected at measurement time for an
     // incompatible parameter set (FFT size, sample rate, window, quality).
     // Downstream consumers could not distinguish "no calibration loaded"
     // from "calibration loaded but rejected". The hard_parameter_mismatch
     // bit makes the rejection explicit.
     bool hard_parameter_mismatch;
};


// =============================================================================
// MEASUREMENT PARAMETERS
// =============================================================================
struct MeasurementParams {


     FftMode          fft_mode;            // Determines internal FFT size
     WindowFunction window_function;
     uint16_t         n_averages;          // Complex FFT frames to accumulate


     TfEstimator      estimator;


     StimulusType     stimulus;
     float            stimulus_amplitude_dbfs;
     float            stimulus_freq_hz;          // INTERNAL_SINE only
     float            sweep_start_hz;            // INTERNAL_LOG_SWEEP only
     float            sweep_end_hz;
     float            sweep_duration_s;


     bool             apply_calibration;
     uint32_t         arm_timeout_ms;
     bool             abort_on_clip;
};
// =============================================================================
// MeasurementAccumulator
// =============================================================================
// Transient double-precision working structure. Owned by measurement_engine.
// Never exported. Discarded after MeasurementResult is computed.
//
// FIX [fft-bins]: This struct is sized for the CANONICAL 512-bin grid (FFT_BINS).
// For precision FFT modes (4096pt, 8192pt), measurement_engine maintains
// a SEPARATE larger accumulator in OCRAM (declared in measurement_engine.cpp,
// not in this struct). After accumulation, the precision accumulator's derived
// products are resampled into this struct's arrays before PROCESSING completes.
//
// In other words: this struct always has FFT_BINS entries regardless of mode.
// The larger-FFT internal work happens in memory outside this struct.
//
// Memory: ~32 KB in DTCM.
// =============================================================================
struct MeasurementAccumulator {


     // After rebinning from precision modes, these contain the
     // canonical-grid complex averaged spectra (512 bins).
     double X_re[FFT_BINS];
     double X_im[FFT_BINS];
     double Y_re[FFT_BINS];
     double Y_im[FFT_BINS];


     // Auto-spectra and cross-spectrum in canonical grid
     double S_xx[FFT_BINS];
     double S_yy[FFT_BINS];
     double S_xy_re[FFT_BINS];
     double S_xy_im[FFT_BINS];


     // Accumulation metadata
     uint16_t frames_accumulated;
     uint16_t frames_requested;
     uint32_t capture_start_block;
     uint32_t generator_start_block;
     uint16_t clip_source_count;
     uint16_t clip_return_count;


     // Mode used — needed by PROCESSING to know which rebinning path was taken
     FftMode        fft_mode;
     WindowFunction window_function;
     TfEstimator    estimator;
     StimulusType   stimulus;
     bool           apply_calibration;
};
// =============================================================================
// MeasurementResult
// =============================================================================
// Persisted float-precision result. Always 512 canonical bins regardless of
// the FftMode used during accumulation. Produced by measurement_engine in the
// PROCESSING state. Read-only outside measurement_engine.
//
// FIX [fft-bins]: fft_mode records which mode produced this result so that
// consumers know the internal resolution used, even though all arrays are
// 512 bins. This is important for calibration matching: a calibration taken
// in MODE_PRECISION has higher per-bin accuracy than one taken in MODE_LIVE,
// even though both have the same array dimensions.
//
// Memory: ~16 KB in DTCM.
// =============================================================================
struct MeasurementResult {


     // Validity
     bool             result_valid;
     ResultQuality result_quality;


     // Timing
     uint32_t capture_start_block;
     uint32_t capture_end_block;
     uint32_t timestamp_ms;


     // Accumulation metadata
     uint16_t n_averages_completed;
     uint16_t fft_size;               // Actual internal FFT size used (1024/4096/8192)
     FftMode     fft_mode;            // Mode — tells consumer about per-bin accuracy
     WindowFunction window_function;
     TfEstimator       estimator;
     StimulusType      stimulus;
     bool              generator_active;


     // Hardware context
     uint8_t source_node_ch;
     uint8_t return_node_ch;
     uint8_t line_in_level;


     // Spectra (canonical 512-bin grid)
     float S_xx_db[FFT_BINS];          // Source auto-spectrum, dBFS
     float S_yy_db[FFT_BINS];          // Return auto-spectrum, dBFS
     float coherence[FFT_BINS];        // γ² per bin, 0.0–1.0


     // Transfer function
     float tf_raw_mag_db     [FFT_BINS];   // H1 or H2, uncalibrated
     float tf_cal_mag_db     [FFT_BINS];   // Calibration-corrected magnitude
     float tf_cal_phase_rad[FFT_BINS];     // Calibration-corrected phase


     // Phase (unwrapped only — wrapped phase is an intermediate step, not stored)
     float phase_unwrapped[FFT_BINS];


     // Group delay (derived from phase, stored for self-contained result)
     float group_delay_ms[FFT_BINS];


     // Health metrics
     float    valid_bin_fraction;
     float    mean_coherence;
     bool     clip_detected;
     uint16_t clip_source_count;
     uint16_t clip_return_count;


     // Calibration status
     bool                  calibration_applied;
     CalibrationType       calibration_type;
     CalibrationWarnings calibration_warnings;
     char                  calibration_provenance[96];


     // Firmware context
     char firmware_version[16];
};


// =============================================================================
// CalibrationBuffer
// =============================================================================
// Resident calibration data loaded from SD by calibration_store.
//
// FIX [fft-bins]: The calibration correction arrays are ALWAYS 512 canonical
// bins, regardless of the FftMode used when the calibration was captured.
// A calibration captured in MODE_PRECISION produces a higher-accuracy 512-bin
// result than one captured in MODE_LIVE, but both have the same array shape.
//
// Calibration matching: the fft_mode field records what mode was used, and
// calibration_store uses this for advisory purposes (a MODE_PRECISION
// calibration applied to a MODE_LIVE measurement is valid but the reverse
// should be flagged as a soft mismatch — the calibration has higher resolution
// than the measurement it is correcting).
//
// Memory: ~4 KB in DTCM.
// =============================================================================
struct CalibrationBuffer {
     bool               loaded;
     uint16_t           fft_size;         // Internal FFT size at calibration time
     FftMode            fft_mode;         // Mode used — affects per-bin accuracy
     uint32_t           sample_rate;
     WindowFunction window_function;
     uint8_t            line_in_level;
     CalibrationType type;


     uint32_t capture_timestamp_ms;
     char       description[46];


     // Canonical 512-bin correction arrays
     float cal_mag_db       [FFT_BINS];
     float cal_phase_rad[FFT_BINS];


     // Per-bin validity: false where calibration loopback had low coherence
     bool   bin_valid       [FFT_BINS];
};


// =============================================================================
// STATIC ASSERTIONS
// =============================================================================
// These confirm the canonical grid assumption and the double-precision
// requirement. If FFT_BINS or the double size changes, the build fails with
// a clear message rather than silently invalidating the memory budget and
// the rebinning contract.


static_assert(FFT_BINS == 512,
     "All result and calibration structs assume FFT_BINS=512 (canonical grid). "
     "The precision FFT accumulator in measurement_engine.cpp is separately "
     "sized for MAX_PRECISION_BINS. Update both if FFT_BINS changes.");


static_assert(sizeof(double) == 8,
     "MeasurementAccumulator requires 8-byte double (ARM Cortex-M7 hardware "
     "double). If this fails, the platform has changed and the accumulator "
     "precision guarantee no longer holds.");


static_assert(MAX_PRECISION_BINS == 4096,
     "MAX_PRECISION_BINS must be 4096 (8192-point FFT / 2). "
     "Update if LF mode FFT size changes.");


#endif // MEASUREMENT_CORE_H
