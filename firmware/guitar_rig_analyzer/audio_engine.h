// =============================================================================
// audio_engine.h     —    Guitar Rig Analyzer
// =============================================================================
// Public interface for the audio engine.
//
// CHANGELOG v0.4.0       (last functional change — no logic changes since)
// ----------------
// • audioEngine_capture() renamed to audioEngine_update() to reflect that
//   audio_engine no longer owns audio capture — it consumes a pre-captured
//   block from audio_capture (CONSUMER_LIVE) and performs live analysis on it.
//   The name "capture" was misleading once capture ownership moved to audio_capture.
//
// • Audio Library object ownership removed from this module.
//   AudioInputI2S, AudioAnalyzeFFT1024, AudioAnalyzePeak, AudioConnection,
//   and AudioControlSGTL5000 all now live in audio_capture.cpp.
//   audio_engine.cpp includes audio_capture.h and reads AudioRawBlock data
//   instead of calling Audio Library objects directly.
//
// • audioEngine_setRoute() now calls audioCap_notifyRouteChanged() after
//   updating mixer gains (see full contract in audio_engine.h and audio_capture.h).
//
// • audioEngine_setInputGain() is now a thin wrapper around audioCap_setInputGain().
//   Gain control and invalidation events are owned by audio_capture.
//
// UNCHANGED in v0.4.0:
// • SignalRoute node-based language (SOURCE_NODE, RETURN_NODE)
// • AudioFrame struct and all live DSP logic (EMA, TF, confidence, peaks)
// • tf_persistence_active flag and design choice documentation
// • Headphone passthrough noted as temporary dev behaviour
//
// SIGNAL NODE MODEL
// -----------------
// The analyzer's signal model has two measurement nodes:
//
//   SOURCE_NODE — signal leaving the instrument toward the rig.
//                    Tapped after the OPA1642 buffer. High impedance, transparent.
//
//   RETURN_NODE — signal returning from the rig.
//                    Selectable between 1/4" TS and XLR (final hardware).
//
// The transfer function H(f) = RETURN_NODE / SOURCE_NODE per frequency bin
// directly answers: "what did the rig do to the signal?"
//
// Current bench binding:
//    SOURCE_NODE → SGTL5000 Line In, I2S channel SOURCE_NODE_PHYSICAL_CH
//    RETURN_NODE → SGTL5000 Line In, I2S channel RETURN_NODE_PHYSICAL_CH
//
// Future hardware will replace the physical channel binding with a routing
// stage controlled by signal_router (planned v0.3). The rest of this module,
// and every module above it, will continue to refer only to SOURCE_NODE and
// RETURN_NODE — the physical binding will be hidden inside signal_router.
// =============================================================================


#ifndef AUDIO_ENGINE_H
#define AUDIO_ENGINE_H


#include <Arduino.h>
#include "config.h"


// =============================================================================
// SIGNAL ROUTE DESCRIPTOR
// =============================================================================
// A SignalRoute describes which physical I2S channels are currently bound to
// the SOURCE_NODE and RETURN_NODE logical measurement points.
//
// In the final hardware, this struct will be produced by signal_router based
// on jack detection and front-panel selection. For now, it is set directly
// from config.h constants and can be swapped at runtime via audioEngine_setRoute().
//
// Key principle: code ABOVE this module should refer to source and return by
// their node names (SOURCE_NODE, RETURN_NODE), never by channel numbers (0, 1).
// The channel numbers belong to SignalRoute and audio_engine internals only.
struct SignalRoute {


     // Physical I2S channel currently carrying SOURCE_NODE signal.
     // 0 = I2S LEFT, 1 = I2S RIGHT.
     // Set from SOURCE_NODE_PHYSICAL_CH in config.h by default.
     uint8_t source_node_ch;


     // Physical I2S channel currently carrying RETURN_NODE signal.
     uint8_t return_node_ch;


     // Human-readable description of this binding.
     // Printed to Serial on route changes. Stored in AudioFrame for logging.
     // Example: "Bench: SOURCE_NODE=L, RETURN_NODE=R"
     //          "CALIBRATION: channels swapped for symmetry check"
     const char* description;
};


// =============================================================================
// AUDIO FRAME — one complete analysis output block
// =============================================================================
// Produced by audioEngine_update() once per FFT_AVERAGE_COUNT raw frames.
// Contains everything the display engine, future logger, and future insights
// engine need. Using a struct makes the data boundary between modules explicit
// and serialisation to CSV straightforward.
struct AudioFrame {


    // --- Averaged FFT magnitudes (linear, 0.0–1.0) ---
    // Mean of FFT_AVERAGE_COUNT consecutive raw FFT frames, per bin.
    // SOURCE_NODE spectrum.
    float fft_source[FFT_BINS];
    // RETURN_NODE spectrum.
    float fft_return[FFT_BINS];


    // --- Transfer function per bin (dB, EMA-smoothed) ---
    // H_dB[k] = 20 * log10( avg_return[k] / avg_source[k] )
    // Smoothed with EMA across output blocks (coefficient: TF_SMOOTHING_ALPHA).
    // Bins where averaged source < TF_SOURCE_GATE → NAN (unenergised).
    float tf_db[FFT_BINS];


    // --- TF persistence flag ---
    // true   = engine is currently preserving EMA history for one or more
    //          unenergised bins. The NAN entries in tf_db[] reflect the display
    //          gaps, but the internal EMA buffer for those bins still holds the
    //          last valid smoothed value. This is the "sticky instrument" mode.
    // false = all bins were energised this block; no persistence in effect.
    //
    // Consumers (display engine, future logger) can use this flag to annotate
    // the frame: e.g. display adds the LOW SIGNAL warning, logger marks the
    // row as "partial measurement."
    //
    // See: TF PERSISTENCE DESIGN DECISION in config.h for full discussion.
    bool tf_persistence_active;


    // --- TF clamp markers (added 2026-09-07, TODO-29) ---
    // audioEngine_update() clamps each bin's raw TF into
    // [TF_DB_MIN - 6, TF_DB_MAX + 6] before it enters the EMA, so a
    // boundary-bin outlier cannot poison the smoothing history. That clamp is
    // correct and is retained — but until now the railed value was written
    // into tf_db[k] indistinguishably from a real measurement, and consumers
    // had no way to tell a saturated bin from a measured one.
    //
    // Observed 2026-09-07 with nothing connected to RETURN_NODE: the true TF
    // was ~-47 dB, 23 dB below the -24.0 dB rail, and the diagnostic printed
    // "1kHz=-24.0dB" in 33 of 33 consecutive windows as though it were data.
    // Evidence: ai/evidence/2026-09-07-tf-clamp-preserved.md
    //
    // Bit k of tf_clamped_bits is set when bin k's raw TF was outside the
    // clamp window THIS BLOCK, i.e. tf_db[k] is a rail, not a measurement.
    // Note a bin can be partially railed over time: the EMA mixes clamped and
    // unclamped contributions, so a value that is not exactly at the rail can
    // still be contaminated by it. The bit reflects this block only.
    //
    // Stored as a bitmask rather than bool[FFT_BINS] because AudioFrame is
    // stack-allocated in validation.cpp and the firmware holds a ~4 KB
    // worst-case stack budget (see measurement_engine.cpp FIX [stack-budget]).
    // 64 bytes instead of 512.
    //
    // Read with audioEngine_tfBinClamped() — do not index the mask directly.
    uint32_t tf_clamped_bits[FFT_BINS / 32];

    // Number of bins clamped this block (0-FFT_BINS). A spot-check samples
    // only five frequencies; this says how much of the whole curve is railed.
    uint16_t tf_clamped_count;


    // --- TF confidence ---
    // FIX [confidence-denominator]: reported over the analysis band
    // (200 Hz – 10 kHz) only, NOT over all 512 FFT bins. Earlier versions
    // divided by FFT_BINS, which capped the achievable value near ~0.45
    // (only ~228 of 512 bins are in-band) and made the validation suite's
    // LOOPBACK_CONFIDENCE_MIN (= 0.50) unreachable on real hardware.
    //
    // Definition: fraction (0.0–1.0) of in-band bins that were above
    // TF_SOURCE_GATE and produced a finite TF this block.
    //   0.0 = silence / instrument not playing in the analysis band.
    //   1.0 = every in-band bin energised (broadband stimulus).
    // Compare against TF_CONFIDENCE_THRESHOLD to decide whether to warn.
    float tf_confidence;


    // --- Peak levels (dBFS), captured over the full averaging window ---
    float peak_source_dbfs;
    float peak_return_dbfs;


    // --- Clipping flags (within 0.5 dBFS of full scale) ---
     bool source_clipping;
     bool return_clipping;


     // --- Frame metadata ---
     uint32_t   output_block_number;   // Increments each time capture() returns true
     uint32_t   timestamp_ms;          // millis() at moment of capture
     SignalRoute active_route;         // Route snapshot — self-documenting in logs
};


// =============================================================================
// PUBLIC API
// =============================================================================


// -----------------------------------------------------------------------------
// audioEngine_init()
// Initialises the audio engine as a CONSUMER of audio_capture.
// This function does NOT allocate AudioMemory, initialise the SGTL5000 codec,
// program mixers, or arm FFT objects — those are all audioCap_init()'s
// responsibility. audioCap_init() must be called before audioEngine_init().
// audioEngine_init() sets up EMA smoothing state and the initial SignalRoute.
// Returns true on success (always true if audio_capture is initialised).
// Call once from setup(), after audioCap_init().
// -----------------------------------------------------------------------------
bool audioEngine_init();


// -----------------------------------------------------------------------------
// audioEngine_update(frame)
// RENAMED from audioEngine_capture() in v0.4.0.
// "capture" was misleading — audio_engine no longer captures audio.
// "update" correctly describes what this function does: consume a block from
// audio_capture's CONSUMER_LIVE slot and update the AudioFrame with live
// display analysis results (EMA TF, spectrum, peaks, confidence).
//
// Non-blocking. Call every loop iteration.
// Checks audioCap_isBlockFresh(CONSUMER_LIVE). If a fresh block is available,
// consumes it, runs EMA smoothing, TF, and peak metering, fills *frame,
// calls audioCap_markConsumed(CONSUMER_LIVE), and returns true.
// Returns false (frame unchanged) when no fresh block is available.
// -----------------------------------------------------------------------------
bool audioEngine_update(AudioFrame* frame);


// -----------------------------------------------------------------------------
// audioEngine_setRoute(route)
// Records the new logical node → physical channel binding in s_active_route
// and resets EMA smoothing (old history is not valid after a route change).
//
// Hardware routing (mixer gain programming) is owned by audio_capture, not
// audio_engine. This function delegates the hardware update by calling
// audioCap_notifyRouteChanged(), which applies the new mixer gains via
// audio_capture's internal applyRoute() helper.
//
// In the current bench harness, call this to swap channels for calibration.
// In future hardware, call this from signal_router when jack selection changes.
//
// *** DEPENDENCY — audio_capture notification (required from v0.4 onward) ***
// The implementation of this function MUST call:
//   audioCap_notifyRouteChanged(route.source_node_ch, route.return_node_ch)
// This is what applies the new mixer gains AND latches the ROUTE_CHANGED event
// so the main loop can cancel any in-progress precision capture.
//
// Without this call, the main loop cannot detect the route change, and
// measurement_engine will silently accumulate data through a channel-binding
// change, producing a corrupt result with no error flag.
//
// The complete route-change chain:
//   audioEngine_setRoute()
//     → audioCap_notifyRouteChanged()              [programs mixers + records change]
//     → audioCap_update() returns ROUTE_CHANGED    [next main loop iteration]
//     → main loop calls measurementEngine_cancel() if state == CAPTURE
//     → measurement_engine → ABORTED (ROUTE_CHANGED)
//
// See audio_capture.h for the audioCap_notifyRouteChanged() specification.
// -----------------------------------------------------------------------------
void audioEngine_setRoute(const SignalRoute& route);


// -----------------------------------------------------------------------------
// CHANGED [todo-50]: audioEngine_setRouteDescription(description)
//
// Updates ONLY the route description carried in AudioFrame metadata.
// No mixer gains. No smoothing reset. No audioCap_notifyRouteChanged().
// NO ROUTE_CHANGED EVENT.
//
// Exists so signalRouter_init() can synchronise the description at boot
// WITHOUT making boot a route-change transition (ADR-004 Decision 2). Before
// this, the 5 s diagnostic and the Pi's ROUTER_STATUS both reported
// audio_engine's own init string on a board whose router was already in TS.
//
// THIS IS NOT A SUBSTITUTE FOR audioEngine_setRoute(). Use setRoute() for any
// real route change — it is what makes gains, smoothing and the event follow.
// Using this setter in its place would leave the mixer bound to the old
// channels while the metadata claimed otherwise.
//
// Stores the caller's pointer; the string must outlive the binding. A nullptr
// is ignored.
// -----------------------------------------------------------------------------
void audioEngine_setRouteDescription(const char* description);


// -----------------------------------------------------------------------------
// audioEngine_getRoute()
// Returns the currently active SignalRoute (const reference, read only).
// -----------------------------------------------------------------------------
const SignalRoute& audioEngine_getRoute();


// -----------------------------------------------------------------------------
// audioEngine_setInputGain(gain_db)
// Thin wrapper around audioCap_setInputGain(gain_db) as of v0.4.0.
// Gain control and the associated capture-invalidation event are now owned
// by audio_capture. This function exists for backwards compatibility with
// call sites that used audioEngine_setInputGain() before v0.4.
// Prefer calling audioCap_setInputGain() directly in new code.
// -----------------------------------------------------------------------------
void audioEngine_setInputGain(float gain_db);


// -----------------------------------------------------------------------------
// audioEngine_resetSmoothing()
// Clears the EMA buffer and frame accumulators.
// Call before connecting a new device under test so stale history from the
// previous rig does not contaminate the first blocks of the new measurement.
// -----------------------------------------------------------------------------
void audioEngine_resetSmoothing();


// Frequency / magnitude conversion helpers (pure functions, no side effects).
float audioEngine_binToHz(int bin);           // Bin index → Hz
int   audioEngine_hzToBin(float freq_hz);     // Hz → nearest bin index
float audioEngine_linearToDbfs(float linear); // Linear magnitude → dBFS


// -----------------------------------------------------------------------------
// audioEngine_tfBinClamped(frame, bin)
// True when frame->tf_db[bin] is a clamp rail rather than a measured value —
// the bin's raw transfer function fell outside [TF_DB_MIN-6, TF_DB_MAX+6] on
// the block this frame describes.
//
// Any consumer that RENDERS tf_db to a human (serial diagnostic, display curve,
// export) must check this first and present the bin as saturated rather than
// printing the rail as a number. See TODO-29.
//
// Returns false for a null frame or an out-of-range bin index.
// -----------------------------------------------------------------------------
bool audioEngine_tfBinClamped(const AudioFrame* frame, int bin);


#endif // AUDIO_ENGINE_H
