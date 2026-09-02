// =============================================================================
// insights_engine.cpp   —   Guitar Rig Analyzer   v0.5.0
// =============================================================================
// Interprets MeasurementResult into structured Insight objects.
//
// DETECTION ALGORITHM DESIGN PRINCIPLES
// --------------------------------------
// 1. Prefer no insight over a false positive.
//    Each detection has a threshold that must be clearly exceeded before
//    generating an insight. Conservative thresholds mean quiet operation on
//    ambiguous results — the instrument stays silent rather than inventing
//    problems that are not there.
//
// 2. All ADVISORY insights are suppressed for POOR and INVALID results.
//    The quality gate is absolute: if coherence is too low to trust the TF,
//    no inferences about the rig are made. A single quality-warning insight
//    is emitted instead to explain why the advisory panel is empty.
//
// 3. MEASUREMENT insights report what was measured, not what it means.
//    "Treble cut: –8.2 dB at 8 kHz" is a measurement.
//    "Possible long cable run" is an advisory.
//    The distinction is preserved in the Insight.mode field and the display
//    layer renders them differently.
//
// 4. Frequency-specific insights carry a frequency_hz field.
//    Broadband insights carry frequency_hz = 0.
//    This allows the display engine to draw a marker on the TF curve at the
//    relevant frequency.
//
// ANALYSIS BAND
// -------------
// All detection algorithms restrict their analysis to the band defined by
// INS_ANALYSIS_LOW_HZ and INS_ANALYSIS_HIGH_HZ. This excludes:
//   • Sub-bass bins (< 80 Hz): low stimulus energy, high noise, low relevance
//   • Near-Nyquist bins (> 16 kHz): poor coherence typical at high frequencies
// The bin range is computed once in insightsEngine_analyse() and passed
// to each detector as k_lo and k_hi (inclusive).
// =============================================================================


#include "insights_engine.h"
#include <string.h>
#include <math.h>


// =============================================================================
// MODULE-PRIVATE STATE
// =============================================================================
static InsightList s_insights;


// =============================================================================
// PRIVATE HELPERS
// =============================================================================


// Add one insight to the list. Returns false if list is full.
static bool addInsight(InsightMode mode, InsightSeverity severity,
                          const char* title, const char* detail, const char* action,
                          float freq_hz, float mag_db, ResultQuality quality) {
    if (s_insights.count >= INSIGHTS_MAX_COUNT) return false;
    Insight& ins = s_insights.items[s_insights.count++];
    ins.mode         = mode;
    ins.severity     = severity;
    ins.frequency_hz = freq_hz;
    ins.magnitude_db = mag_db;
    ins.data_quality = quality;
    strncpy(ins.title,     title    ? title   : "", INSIGHT_TITLE_LEN   - 1);
    strncpy(ins.detail, detail ? detail : "", INSIGHT_DETAIL_LEN - 1);
    strncpy(ins.action, action ? action : "", INSIGHT_ACTION_LEN - 1);
    ins.title [INSIGHT_TITLE_LEN       - 1] = '\0';
    ins.detail[INSIGHT_DETAIL_LEN - 1] = '\0';
    ins.action[INSIGHT_ACTION_LEN - 1] = '\0';
    return true;
}


// Hz → bin index (nearest, clamped to [0, FFT_BINS-1])
// Canonical bin spacing: SAMPLE_RATE / (FFT_BINS * 2)
static int hzToBin(float hz) {
    float bin_hz = (float)SAMPLE_RATE / (float)(FFT_BINS * 2);
    int k = (int)(hz / bin_hz + 0.5f);
    if (k < 0)             k = 0;
    if (k >= FFT_BINS)     k = FFT_BINS - 1;
    return k;
}


// Mean TF value over a frequency band [lo_hz, hi_hz] (calibrated if available).
// Skips bins below min_coherence and NaN bins (gated/unenergised).
// Returns NAN when no valid bins exist — callers must check isfinite() before use.
// Returning NAN (not 0.0f) is critical: 0.0f looks like a real 0 dB measurement
// and would cause detectors to fire on phantom differences from empty bands.
static float bandMean(const MeasurementResult& r, float lo_hz, float hi_hz,
                         float min_coherence = 0.5f) {
    int k_lo = hzToBin(lo_hz);
    int k_hi = hzToBin(hi_hz);
    float sum = 0.0f;
    int     count = 0;
    const float* tf = r.calibration_applied ? r.tf_cal_mag_db : r.tf_raw_mag_db;
    for (int k = k_lo; k <= k_hi; k++) {
          if (r.coherence[k] < min_coherence) continue;
          if (isnan(tf[k])) continue;
          sum += tf[k];
          count++;
    }
    return (count > 0) ? sum / (float)count : NAN;
}


// Mean group delay over the analysis band.
// Skips bins where coherence is below threshold OR where group_delay_ms is NaN.
// NaN appears in edge bins (central-difference undefined) and in any bin where
// the source was below the gate. Without this guard, a single NaN in the band
// would poison the mean and cause detectLatency() to emit no insight at all.
static float bandMeanGroupDelay(const MeasurementResult& r, int k_lo, int k_hi,
                                   float min_coherence = 0.6f) {
    float sum = 0.0f;
    int     count = 0;
    for (int k = k_lo; k <= k_hi; k++) {
          if (r.coherence[k] < min_coherence) continue;
          if (isnan(r.group_delay_ms[k]))      continue;
          sum += r.group_delay_ms[k];
          count++;
    }
    return (count > 0) ? sum / (float)count : NAN;
}


// =============================================================================
// PRIVATE: DETECTION ALGORITHMS
// Each function adds 0–2 insights to s_insights.
// They receive the analysis band k_lo..k_hi (pre-computed in analyse()).
// They receive the result quality for the data_quality field.
// =============================================================================


// -----------------------------------------------------------------------------
// detectDataQuality
// Always runs regardless of quality gate.
// Emits MEASUREMENT insights only — never ADVISORY.
// Reports: quality grade, coherence, clipping, calibration state.
// Advisory analysis is unavailable when quality is POOR/INVALID,
// coherence is below INS_MIN_COHERENCE_FOR_ADV, or clipping occurred.
// (Those conditions are checked in insightsEngine_analyse(), not here.)
// -----------------------------------------------------------------------------
static void detectDataQuality(const MeasurementResult& r) {
char detail[INSIGHT_DETAIL_LEN];
const char* qname =
    (r.result_quality == ResultQuality::EXCELLENT) ? "EXCELLENT" :
    (r.result_quality == ResultQuality::GOOD)        ? "GOOD" :
    (r.result_quality == ResultQuality::MARGINAL)    ? "MARGINAL" :
    (r.result_quality == ResultQuality::POOR)        ? "POOR" : "INVALID";


snprintf(detail, sizeof(detail),
         "Quality: %s. Coherence: %.2f. Valid bins: %.0f%%.",
         qname, r.mean_coherence, r.valid_bin_fraction * 100.0f);


InsightSeverity sev =
    (r.result_quality >= ResultQuality::GOOD) ? InsightSeverity::INFO :
    (r.result_quality == ResultQuality::MARGINAL) ? InsightSeverity::WARNING
                                                     : InsightSeverity::ALERT;


addInsight(InsightMode::MEASUREMENT, sev,
           "Measurement quality",
           detail, "",
           0.0f, r.mean_coherence, r.result_quality);


if (r.clip_detected) {
    snprintf(detail, sizeof(detail),
             "Clipping on %s%s%s during capture.",
             r.clip_source_count ? "SOURCE" : "",
             (r.clip_source_count && r.clip_return_count) ? " and " : "",
             r.clip_return_count ? "RETURN" : "");
    addInsight(InsightMode::MEASUREMENT, InsightSeverity::ALERT,
               "Clipping detected",
               detail,
               "Reduce input gain (audioCap_setInputGain) and re-measure.",
               0.0f, 0.0f, r.result_quality);
}


// Calibration state is an instrument fact, not an inference about the rig.
// Reclassified as MEASUREMENT so it always appears regardless of quality gate.
if (r.calibration_warnings.calibration_missing) {
    addInsight(InsightMode::MEASUREMENT, InsightSeverity::WARNING,
               "No calibration applied",
               "Results show raw hardware TF — channel asymmetry is not removed.",
               "Run a flat loopback measurement and press 'c' to calibrate.",
               0.0f, 0.0f, r.result_quality);
} else if (r.calibration_warnings.line_in_level_mismatch) {
    addInsight(InsightMode::MEASUREMENT, InsightSeverity::WARNING,
               "Calibration level mismatch",
               "Calibration was taken at a different input gain level. "
               "Phase correction is valid; magnitude correction is approximate.",
                   "Re-calibrate at the current gain level for full accuracy.",
                   0.0f, 0.0f, r.result_quality);
    }
}


// -----------------------------------------------------------------------------
// detectTrebleRolloff
// Compares the mean TF in the HF region to the midrange reference.
// A significant drop indicates cable capacitance, missing treble presence, etc.
// -----------------------------------------------------------------------------
static void detectTrebleRolloff(const MeasurementResult& r, ResultQuality quality,
                                   bool allow_advisory) {
    float mf_mean = bandMean(r, INS_TREBLE_ROLLOFF_MF_HZ * 0.5f,
                                   INS_TREBLE_ROLLOFF_MF_HZ * 2.0f);
    float hf_mean = bandMean(r, INS_TREBLE_ROLLOFF_HF_HZ * 0.7f,
                                   INS_TREBLE_ROLLOFF_HF_HZ * 1.4f);
    if (!isfinite(mf_mean) || !isfinite(hf_mean)) return;     // no valid data in band
    float drop_db = mf_mean - hf_mean;


    if (drop_db >= INS_TREBLE_ROLLOFF_DB) {
        char detail[INSIGHT_DETAIL_LEN];
        snprintf(detail, sizeof(detail),
                 "%.1f dB drop from %.0f Hz reference to %.0f Hz region.",
                 drop_db, INS_TREBLE_ROLLOFF_MF_HZ, INS_TREBLE_ROLLOFF_HF_HZ);


        addInsight(InsightMode::MEASUREMENT, InsightSeverity::WARNING,
                   "Treble rolloff",
                   detail, "",
                   INS_TREBLE_ROLLOFF_HF_HZ, -drop_db, quality);


        // Advisory: infer possible cause (suppressed when quality gated)
        if (!allow_advisory) return;
        const char* cause =
            (drop_db >= 8.0f) ? "Significant capacitive loading — likely a long or "
                                    "high-capacitance cable, or a passive pickup into a low "
                                    "impedance input." :
            (drop_db >= 4.0f) ? "Moderate treble loss — consider a shorter cable or "
                                    "a buffer pedal after the guitar." :
                                    "";
        if (cause[0]) {
            addInsight(InsightMode::ADVISORY, InsightSeverity::WARNING,
                          "Treble rolloff cause",
                          cause,
                          drop_db >= 8.0f
                              ? "Try a shorter cable or add a high-impedance buffer at the guitar."
                              : "Try a shorter cable.",
                          INS_TREBLE_ROLLOFF_HF_HZ, -drop_db, quality);
        }
    }
}


// -----------------------------------------------------------------------------
// detectMidChange
// Detects a significant boost or cut in the mid-frequency band relative to
// the broadband mean. Useful for detecting EQ pedals, wah position, etc.
// -----------------------------------------------------------------------------
static void detectMidChange(const MeasurementResult& r, int k_lo, int k_hi,
                                ResultQuality quality, bool allow_advisory) {
    float broad_mean = bandMean(r,
                                      (float)(k_lo) * (float)SAMPLE_RATE / (float)(FFT_BINS * 2),
                                      (float)(k_hi) * (float)SAMPLE_RATE / (float)(FFT_BINS * 2));
    float mid_mean      = bandMean(r, INS_MID_BAND_LOW_HZ, INS_MID_BAND_HIGH_HZ);
    if (!isfinite(broad_mean) || !isfinite(mid_mean)) return;        // no valid data in band
    float diff_db       = mid_mean - broad_mean;


    if (fabsf(diff_db) >= INS_MID_BOOST_DB) {
        bool is_boost = (diff_db > 0);
        char detail[INSIGHT_DETAIL_LEN];
        snprintf(detail, sizeof(detail),
                    "%.1f dB %s in %.0f–%.0f Hz band vs broadband mean.",
                    fabsf(diff_db),
                    is_boost ? "boost" : "cut",
                    INS_MID_BAND_LOW_HZ, INS_MID_BAND_HIGH_HZ);


        addInsight(InsightMode::MEASUREMENT,
                      fabsf(diff_db) >= 6.0f ? InsightSeverity::WARNING : InsightSeverity::INFO,
                      is_boost ? "Mid-range boost" : "Mid-range cut",
                      detail, "",
                      (INS_MID_BAND_LOW_HZ + INS_MID_BAND_HIGH_HZ) * 0.5f,
                      diff_db, quality);


        if (!allow_advisory) return;
        addInsight(InsightMode::ADVISORY,
                      InsightSeverity::INFO,
                      is_boost ? "Mid boost detected" : "Mid cut detected",
                      is_boost ? "Possible: mid-boost EQ pedal, wah in parked position, "
                                    "or resonance peak in the signal chain."
                                : "Possible: mid-scoop EQ pedal, notch filter, "
                                    "or resonance dip in the signal chain.",
                      "",
                      (INS_MID_BAND_LOW_HZ + INS_MID_BAND_HIGH_HZ) * 0.5f,
                      diff_db, quality);
    }
}
// -----------------------------------------------------------------------------
// detectLevelShift
// Detects a significant broadband level offset (all bins shifted up or down).
// Indicates a gain pedal, booster, or attenuator in the signal path.
// -----------------------------------------------------------------------------
static void detectLevelShift(const MeasurementResult& r, int k_lo, int k_hi,
                                    ResultQuality quality, bool allow_advisory) {
    float mean = bandMean(r,
                             (float)(k_lo) * (float)SAMPLE_RATE / (float)(FFT_BINS * 2),
                             (float)(k_hi) * (float)SAMPLE_RATE / (float)(FFT_BINS * 2));
    if (!isfinite(mean)) return;       // no valid data in band


    if (fabsf(mean) >= INS_LEVEL_SHIFT_DB) {
          bool is_boost = (mean > 0);
          char detail[INSIGHT_DETAIL_LEN];
          snprintf(detail, sizeof(detail),
                   "Broadband mean TF: %+.1f dB.", mean);


          addInsight(InsightMode::MEASUREMENT,
                      fabsf(mean) >= 6.0f ? InsightSeverity::WARNING : InsightSeverity::INFO,
                      is_boost ? "Signal level increase" : "Signal level decrease",
                      detail, "",
                      0.0f, mean, quality);


          if (!allow_advisory) return;
          addInsight(InsightMode::ADVISORY, InsightSeverity::INFO,
                      is_boost ? "Gain detected" : "Attenuation detected",
                      is_boost ? "The rig is boosting the signal. Check for a clean boost, "
                                    "buffer, or a pedal with makeup gain."
                                  : "The rig is attenuating the signal. Check for a passive "
                                    "device, volume pedal position, or cable loading.",
                      "",
                      0.0f, mean, quality);
    }
}


// -----------------------------------------------------------------------------
// detectPolarityInversion
// Detects if the phase is inverted (near π) across most of the analysis band.
// Indicates a polarity-reversed cable, transformer, or certain pedals.
// -----------------------------------------------------------------------------
static void detectPolarityInversion(const MeasurementResult& r, int k_lo, int k_hi,
                                          ResultQuality quality, bool allow_advisory) {
    int     inverted_bins = 0;
    int     total_coherent = 0;
    for (int k = k_lo; k <= k_hi; k++) {
        if (r.coherence[k] < 0.5f) continue;
        total_coherent++;
        // FIX [polarity-test]: Previous test was too broad — any phase > 2.5 rad
        // was counted as inverted, which covers a large non-inverted region.
        // Correct test: phase must be genuinely near ±π (i.e. near 180°).
        //
        // We work directly with the signed phase in [-π, +π] from atan2.
        // For unwrapped phase, we take the value modulo 2π first to get the
        // representative wrapped angle, then test proximity to ±π.
        // The tolerance is defined by INS_POLARITY_PHASE_THRESH (0.5 rad ≈ 29°).
        float phase = r.tf_cal_phase_rad[k];
        // FIX [inf-loop]: isfinite catches NaN and ±Inf. Without this guard,
        // an Inf phase value would enter the wrap-while loop and never
        // terminate (Inf - 2π is still Inf), hanging the analysis until
        // the watchdog resets the device.
        if (!isfinite(phase)) continue;
        // Wrap to (-π, +π] for a consistent "near ±π" test
        while (phase >    (float)M_PI) phase -= 2.0f * (float)M_PI;
        while (phase < -(float)M_PI) phase += 2.0f * (float)M_PI;
        // "Near π": either very close to +π or very close to -π
        if (fabsf(fabsf(phase) - (float)M_PI) <= INS_POLARITY_PHASE_THRESH) {
             inverted_bins++;
        }
    }
    if (total_coherent == 0) return;


    float inverted_fraction = (float)inverted_bins / (float)total_coherent;
    if (inverted_fraction >= INS_POLARITY_BIN_FRACTION) {
        addInsight(InsightMode::MEASUREMENT, InsightSeverity::ALERT,
                    "Polarity inversion",
                    "Phase is inverted (near 180°) across most of the analysis band.",
                    "",
                    0.0f, 0.0f, quality);
        if (allow_advisory)
        addInsight(InsightMode::ADVISORY, InsightSeverity::ALERT,
                    "Polarity inversion: check wiring",
                    "Likely cause: a cable with swapped tip/sleeve, a transformer-coupled "
                    "device with reversed phase, or a pedal with known phase inversion.",
                    "Check all XLR pin assignments and TS wiring. Try reversing one "
                    "connector. Use a polarity-correct patch cable.",
                    0.0f, 0.0f, quality);
    }
}


// -----------------------------------------------------------------------------
// detectLatency
// Reports the mean group delay as a latency measurement.
// Flags if the delay is potentially audible or unusually high.
// -----------------------------------------------------------------------------
static void detectLatency(const MeasurementResult& r, int k_lo, int k_hi,
                              ResultQuality quality, bool allow_advisory) {
    float mean_delay_ms = bandMeanGroupDelay(r, k_lo, k_hi);
    if (!isfinite(mean_delay_ms)) return;        // no valid group-delay data in band


    if (fabsf(mean_delay_ms) >= INS_LATENCY_NOTE_MS) {
        char detail[INSIGHT_DETAIL_LEN];
        snprintf(detail, sizeof(detail),
                    "Mean group delay: %.2f ms across analysis band.", mean_delay_ms);


        InsightSeverity sev = (fabsf(mean_delay_ms) >= INS_LATENCY_WARN_MS)
                                    ? InsightSeverity::WARNING : InsightSeverity::INFO;


        addInsight(InsightMode::MEASUREMENT, sev,
                      "Signal latency",
                      detail, "",
                      0.0f, mean_delay_ms, quality);


        if (allow_advisory && fabsf(mean_delay_ms) >= INS_LATENCY_WARN_MS) {
            addInsight(InsightMode::ADVISORY, InsightSeverity::WARNING,
                          "Potentially audible latency",
                          "Latency above 5 ms may be perceptible when monitoring live. "
                          "Digital pedals, amp simulators, and certain reverbs introduce "
                          "processing delay.",
                          "Check any digital devices in the chain for low-latency modes.",
                          0.0f, mean_delay_ms, quality);
        }
    }
}


// =============================================================================
// PUBLIC FUNCTION IMPLEMENTATIONS
// =============================================================================


// -----------------------------------------------------------------------------
// insightsEngine_analyse(result)
// -----------------------------------------------------------------------------
void insightsEngine_analyse(const MeasurementResult& result) {
    // Clear the insight list
    memset(&s_insights, 0, sizeof(s_insights));
    s_insights.count                = 0;
    s_insights.quality_gated        = false;
    s_insights.source_quality = result.result_quality;


    // Pre-compute analysis band bin indices (same canonical grid as everything else)
    const float canonical_bin_hz = (float)SAMPLE_RATE / (float)(FFT_BINS * 2);
    int k_lo = (int)(INS_ANALYSIS_LOW_HZ        / canonical_bin_hz);
    int k_hi = (int)(INS_ANALYSIS_HIGH_HZ / canonical_bin_hz);
    if (k_lo < 0)             k_lo = 0;
    if (k_hi >= FFT_BINS)     k_hi = FFT_BINS - 1;
    // Step 1: Data quality insight (always runs, regardless of quality)
    detectDataQuality(result);


    // Step 2: Quality gate for ADVISORY insights only.
    //
    // FIX [quality-gate-contract]: The previous implementation returned early when
    // advisory was gated, suppressing ALL later detectors including MEASUREMENT-mode
    // ones. The header contract says MEASUREMENT insights are always emitted; only
    // ADVISORY insights are suppressed for POOR/INVALID results.
    //
    // Fix: allow_advisory is passed to each detector. Each detector independently
    // decides whether to emit its advisory half. MEASUREMENT halves always run.
    bool allow_advisory = (result.result_quality >= ResultQuality::MARGINAL &&
                                 result.mean_coherence     >= INS_MIN_COHERENCE_FOR_ADV &&
                                 !result.clip_detected);


    if (!allow_advisory) {
         s_insights.quality_gated = true;
         // Emit one MEASUREMENT insight explaining why advisories are unavailable.
         // This tells the user what to fix, without pretending the spectra weren't measured.
         char detail[INSIGHT_DETAIL_LEN];
         snprintf(detail, sizeof(detail),
                    "Quality is %s. Advisory analysis requires MARGINAL or better, "
                    "no clipping, and coherence >= %.2f.",
                    (result.result_quality == ResultQuality::INVALID) ? "INVALID" :
                    (result.result_quality == ResultQuality::POOR)          ? "POOR"    :
                    result.clip_detected ? "CLIPPED" : "LOW-COHERENCE",
                    INS_MIN_COHERENCE_FOR_ADV);
         addInsight(InsightMode::MEASUREMENT, InsightSeverity::WARNING,
                      "Advisory analysis unavailable",
                      detail,
                      "Improve signal level, reduce noise, or re-run the measurement.",
                      0.0f, 0.0f, result.result_quality);
    }


    // Step 3: Run all detectors.
    // MEASUREMENT insights: always run.
    // ADVISORY insights: emitted only when allow_advisory == true.
    // Each detector receives allow_advisory and suppresses its advisory half if false.
    detectTrebleRolloff         (result,         result.result_quality, allow_advisory);
    detectMidChange             (result, k_lo, k_hi, result.result_quality, allow_advisory);
    detectLevelShift            (result, k_lo, k_hi, result.result_quality, allow_advisory);
    detectPolarityInversion(result, k_lo, k_hi, result.result_quality, allow_advisory);
    detectLatency               (result, k_lo, k_hi, result.result_quality, allow_advisory);
}
// -----------------------------------------------------------------------------
// insightsEngine_getInsights()
// -----------------------------------------------------------------------------
const InsightList& insightsEngine_getInsights() {
    return s_insights;
}


// -----------------------------------------------------------------------------
// insightsEngine_printToSerial()
// -----------------------------------------------------------------------------
void insightsEngine_printToSerial() {
    const InsightList& list = s_insights;


    Serial.printf("[Insights] %d insight(s)", list.count);
    if (list.quality_gated) Serial.print(" [advisories quality-gated]");
    Serial.println();


    for (int i = 0; i < list.count; i++) {
        const Insight& ins = list.items[i];
        const char* mode_str = (ins.mode == InsightMode::MEASUREMENT) ? "MEAS" : "ADV ";
        const char* sev_str   = (ins.severity == InsightSeverity::ALERT)       ? "ALERT   " :
                                  (ins.severity == InsightSeverity::WARNING)    ? "WARN    " :
                                                                                  "INFO    ";
        Serial.printf("   [%s][%s] %s\n", mode_str, sev_str, ins.title);
        if (ins.detail[0]) Serial.printf("            %s\n", ins.detail);
        if (ins.action[0]) Serial.printf("            → %s\n", ins.action);
        if (ins.frequency_hz > 0)
            Serial.printf("            @ %.0f Hz\n", ins.frequency_hz);
    }
}
