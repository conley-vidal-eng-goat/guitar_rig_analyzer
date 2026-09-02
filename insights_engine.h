// =============================================================================
// insights_engine.h     —   Guitar Rig Analyzer   v0.5.0
// =============================================================================
// Interprets a MeasurementResult into labelled, quality-gated observations.
//
// OWNERSHIP
// ---------
// insights_engine owns:
//   • Detection algorithms for known rig phenomena
//   • The resident InsightList (most recent analysis)
//   • The quality gate (POOR and INVALID results produce no advisories)
//
// insights_engine does NOT own:
//   • The MeasurementResult (measurement_engine owns that)
//   • Display of insights (display_engine renders them)
//   • Triggering measurements (the main loop does that)
//   • Export of insights (export_engine would handle that — future)
//
// THE MEASUREMENT vs ADVISORY DISTINCTION
// ----------------------------------------
// Every Insight carries a mode field distinguishing two kinds of output:
//
//   MEASUREMENT   — derived directly and unambiguously from result data.
//     Examples: "treble cut: –8.2 dB at 8 kHz", "latency: 4.3 ms broadband"
//     These are statements of measured fact. Display them in the same visual
//     register as the TF curve itself. No asterisk, no hedging.
//
//   ADVISORY      — an interpretation or inference about what the measurement
//                     might mean for the user's rig or setup.
//     Examples: "possible long cable run", "polarity inversion detected — check wiring"
//     These are suggestions, not measurements. Display them distinctly (different
//     colour, icon, or panel) so the user can distinguish "what was measured"
//     from "what we think it might mean."
//
// This separation prevents the instrument from presenting an inference as if
// it were a direct measurement. Users trust instruments that are honest about
// their confidence level.
//
// QUALITY GATE
// ------------
// Advisory insights (InsightMode::ADVISORY) are suppressed when ANY of these
// conditions hold:
//   • result_quality is POOR or INVALID
//   • mean_coherence is below INS_MIN_COHERENCE_FOR_ADV (= MARGINAL threshold)
//    • clip_detected is true
//
// When gated, a single MEASUREMENT insight explains why advisories are unavailable.
//
// MEASUREMENT insights are always emitted regardless of result quality, because
// spectra and TF values are factually correct even when coherence is low.
// Calibration state warnings ("no cal", "level mismatch") are also always emitted
// as MEASUREMENT insights — they describe instrument conditions, not rig inferences.
//
// DETECTION THRESHOLDS
// --------------------
// Thresholds are defined as named constants in this header so they can be
// tuned after real hardware characterisation without opening the .cpp file.
// Initial values are conservative — they produce insights for clear phenomena
// only and prefer silence over false positives.
// =============================================================================


#ifndef INSIGHTS_ENGINE_H
#define INSIGHTS_ENGINE_H


#include <Arduino.h>
#include "config.h"
#include "measurement_core.h"


// =============================================================================
// INSIGHT TYPES
// =============================================================================


enum class InsightMode : uint8_t {
     MEASUREMENT = 0,         // Direct measurement fact — display like data
     ADVISORY          = 1,   // Interpretation / inference — display distinctly
};


// NOTE: ResultQuality (from measurement_core.h) comparisons in this module
// use ordinal ordering (e.g. result_quality >= ResultQuality::MARGINAL).
// That is safe because measurement_core.h documents the explicit ordering:
//    INVALID(0) < POOR(1) < MARGINAL(2) < GOOD(3) < EXCELLENT(4)
// If that enum ever changes, the comparisons here must be reviewed.
// See the ordering note in measurement_core.h near the ResultQuality definition.


enum class InsightSeverity : uint8_t {
     INFO       = 0,      // Neutral observation ("latency: 2.1 ms")
     WARNING = 1,         // Worth the user's attention ("treble loss –8 dB detected")
     ALERT      = 2,      // Requires action ("clipping detected — reduce gain")
};


// Maximum number of insights that can be stored in one InsightList.
// Bounded to prevent unbounded stack/memory use.
#define INSIGHTS_MAX_COUNT      12


// Maximum string lengths for insight text fields
#define INSIGHT_TITLE_LEN       48
#define INSIGHT_DETAIL_LEN      128
#define INSIGHT_ACTION_LEN      128


struct Insight {
     InsightMode        mode;
     InsightSeverity severity;
     char               title [INSIGHT_TITLE_LEN];       // Short label, e.g. "Treble rolloff"
     char               detail[INSIGHT_DETAIL_LEN];      // e.g. "–8.2 dB at 8 kHz vs 1 kHz reference
     char               action[INSIGHT_ACTION_LEN];      // e.g. "Consider a shorter cable or buffer"
     float              frequency_hz;     // Relevant frequency, or 0 if broadband
     float              magnitude_db;     // Relevant magnitude, or 0 if not applicable
     ResultQuality      data_quality;     // Quality of the result this was derived from
};


struct InsightList {
     Insight   items[INSIGHTS_MAX_COUNT];
     uint8_t   count;                 // Number of valid entries in items[]
     bool      quality_gated;         // true if advisories were suppressed due to low quality
     ResultQuality source_quality;       // Quality of the result that was analysed
};


// =============================================================================
// DETECTION THRESHOLDS
// =============================================================================
// Tune these after real-world hardware characterisation.
// Starting values are intentionally conservative (prefer no insight over false positive).


// Treble rolloff: HF region mean must be this many dB below MF reference
#define INS_TREBLE_ROLLOFF_DB             4.0f      // dB drop from midrange reference to trigger
#define INS_TREBLE_ROLLOFF_MF_HZ          1000.0f // Midrange reference frequency
#define INS_TREBLE_ROLLOFF_HF_HZ          8000.0f // High-frequency check point


// Mid boost/cut: a band mean that differs significantly from broadband mean
#define INS_MID_BOOST_DB                  3.0f      // dB above broadband mean to flag as boost
#define INS_MID_CUT_DB                    3.0f      // dB below broadband mean to flag as cut
#define INS_MID_BAND_LOW_HZ               500.0f
#define INS_MID_BAND_HIGH_HZ              4000.0f


// Broadband level shift: total mean TF differs from 0 dB by more than this
#define INS_LEVEL_SHIFT_DB                1.5f      // dB from 0 dB to flag as level change


// Polarity inversion: phase is near ±π across most of the analysis band.
// This constant is a TOLERANCE around ±π, not a simple threshold.
// A bin is counted as inverted when: fabsf(fabsf(wrapped_phase) - π) <= THRESH
// 0.5 rad ≈ 29° — a bin must be within 29° of 180° to count as inverted.
#define INS_POLARITY_PHASE_THRESH   0.5f       // radians tolerance around ±π
#define INS_POLARITY_BIN_FRACTION   0.7f       // fraction of bins that must show inversion


// Latency: broadband mean group delay above this → note latency
#define INS_LATENCY_NOTE_MS         1.0f       // ms — below this is not worth flagging
#define INS_LATENCY_WARN_MS         5.0f       // ms — above this, flag as potentially audible


// Low coherence gate for advisory logic
#define INS_MIN_COHERENCE_FOR_ADV   (RESULT_QUALITY_MARGINAL_COH)     // same as MARGINAL thresh


// Analysis band: ignore DC and near-Nyquist bins
#define INS_ANALYSIS_LOW_HZ         80.0f
#define INS_ANALYSIS_HIGH_HZ        16000.0f


// =============================================================================
// PUBLIC API
// =============================================================================


// -----------------------------------------------------------------------------
// insightsEngine_analyse(result)
// Analyse a MeasurementResult and populate the internal InsightList.
//
// Rules:
//   • If result.result_quality is POOR or INVALID, only data-quality insights
//     are emitted. No advisory insights are generated from bad data.
//   • MEASUREMENT insights (directly derived from spectra) are always emitted.
//   • Results are generated in severity order within each mode.
//
// Call after measurement_engine returns RESULT_READY and before displaying
// or exporting. The result does not need to have calibration applied —
// insights are generated from tf_raw_mag_db and tf_cal_mag_db independently.
// If calibration is applied, calibrated values are used; otherwise raw values.
//
// Thread safety: not re-entrant. Call from the main loop only.
// -----------------------------------------------------------------------------
void insightsEngine_analyse(const MeasurementResult& result);


// -----------------------------------------------------------------------------
// insightsEngine_getInsights()
// Returns a const reference to the most recently generated InsightList.
// Valid after any call to insightsEngine_analyse().
// The reference is stable until the next call to insightsEngine_analyse().
// -----------------------------------------------------------------------------
const InsightList& insightsEngine_getInsights();
// -----------------------------------------------------------------------------
// insightsEngine_printToSerial()
// Prints all insights from the most recent analysis to Serial.
// Useful for bench diagnostics and Serial command output.
// -----------------------------------------------------------------------------
void insightsEngine_printToSerial();


#endif // INSIGHTS_ENGINE_H
