// =============================================================================
// audio_engine.cpp     —   Guitar Rig Analyzer
// =============================================================================
// Implementation of the audio engine.
//
// CHANGELOG v0.4.0     (last functional change — no logic changes since)
// ----------------
// • Audio Library object ownership REMOVED from this file.
//   AudioInputI2S, AudioAnalyzeFFT1024, AudioAnalyzePeak, AudioConnection
//   graph, and AudioControlSGTL5000 now live in audio_capture.cpp.
// • audioEngine_capture() RENAMED to audioEngine_update().
//   Reads AudioRawBlock from audio_capture (CONSUMER_LIVE) instead of
//   calling Audio Library objects directly.
// • audioEngine_init() no longer calls AudioMemory, Wire.begin, or
//   sgtl5000.enable() — those are audioCap_init()'s responsibility.
// • audioEngine_setInputGain() is now a thin wrapper around
//   audioCap_setInputGain().
// • audioEngine_setRoute() calls audioCap_notifyRouteChanged() unconditionally
//   (the #ifdef AUDIO_CAPTURE_H guard has been removed).
// =============================================================================


#include "audio_engine.h"
#include "audio_capture.h"
#include <Audio.h>
#include <Wire.h>
// =============================================================================
// AUDIO OBJECT GRAPH
// =============================================================================
// FIX [double-ownership]: Sink-chain Audio Library objects (AudioInputI2S,
// the routing AudioMixer4s, AudioAnalyzeFFT1024, AudioAnalyzePeak,
// AudioOutputI2S, AudioControlSGTL5000, AudioRecordQueue, and their
// AudioConnection patch cables) have been REMOVED from this file. They are
// owned exclusively by audio_capture.cpp, which declares them as static
// file-scope globals to enforce single ownership at link time.
//
// audio_engine.cpp is a pure consumer. It reads AudioRawBlock data from
// audio_capture via audioCap_getBlock(AudioConsumer::LIVE).
// It does not interact with the Audio Library hardware layer at all.
//
// (signal_generator.cpp owns the SOURCE chain — AudioSynthWaveformSine,
// AudioSynthNoiseWhite, its own AudioMixer4 — and feeds into s_mixer_ret slot 2
// by contract with audio_capture. That hand-off is not duplicated here.)


// =============================================================================
// MODULE-PRIVATE STATE
// =============================================================================


// EMA smoothing buffer for the transfer function.
// Holds the smoothed H_dB[k] value for every bin.
// Updated only for energised bins (see TF PERSISTENCE BEHAVIOUR in config.h).
static float s_tf_smoothed[FFT_BINS];


// Active signal route (logical node → physical channel binding).
// Snapshot kept here so AudioFrame carries route context for logging.
static SignalRoute s_active_route;


// Initialisation guard
static bool s_initialised = false;


// FIX [dead-state]: Removed s_accum_source[], s_accum_return[], s_accum_count,
// and s_block_number. The averaging accumulator now lives in audio_capture.cpp.
// The canonical block counter is AudioStream::update_counter (the Teensy Audio
// Library's per-ISR counter). audioCap_getBlockCounter() returns it directly.
// AudioRawBlock.audio_block_counter carries this value at block-post time.
// This file no longer accumulates or counts.


// =============================================================================
// PRIVATE HELPERS
// =============================================================================


// applyRoute() and clearAccumulators() have been removed.
// FIX [double-ownership]: applyRoute() referenced mixer_source/mixer_return
//    which no longer exist in this file. Route application is now performed
//    by audio_capture's internal applyRoute() helper, called from
//    audioCap_notifyRouteChanged().
// FIX [dead-state]: clearAccumulators() managed s_accum_source/return which
//    are removed below. audio_capture owns the accumulator now.


// =============================================================================
// PUBLIC FUNCTION IMPLEMENTATIONS
// =============================================================================


// -----------------------------------------------------------------------------
// audioEngine_init()
// -----------------------------------------------------------------------------
bool audioEngine_init() {
     // v0.4: Codec init, AudioMemory, Wire.begin, FFT windowing, and I2S
     // are owned by audio_capture. audioCap_init() must be called before
     // this function. audioEngine_update() will return false until
     // audio_capture has posted its first block.


     // Record the default signal route in s_active_route so that AudioFrame
     // snapshots carry the correct route context for logging.
     // Route APPLICATION (mixer gains) is owned by audio_capture — it is applied
     // inside audioCap_init() via the default SOURCE_NODE_PHYSICAL_CH /
     // RETURN_NODE_PHYSICAL_CH constants from config.h.
     // audio_engine does not touch mixer hardware.
     s_active_route = {
          SOURCE_NODE_PHYSICAL_CH,
          RETURN_NODE_PHYSICAL_CH,
          "Default bench: SOURCE_NODE=L, RETURN_NODE=R"
     };


     memset(s_tf_smoothed, 0, sizeof(s_tf_smoothed));
     s_initialised = true;


     Serial.println("[AudioEngine] Live analysis consumer ready (v0.4).");
     Serial.printf ("[AudioEngine] Route: %s\n", s_active_route.description);
     Serial.println("[AudioEngine] Codec init is audio_capture's responsibility.");
     return true;
}


// -----------------------------------------------------------------------------
// audioEngine_update(frame)
// RENAMED from audioEngine_capture() in v0.4.0.
//
// Consumes a fresh AudioRawBlock from audio_capture (CONSUMER_LIVE) and
// updates *frame with live display analysis: EMA TF, spectrum, confidence,
// and peak levels. Non-blocking: returns false if no fresh block is available.
//
// The averaging that was previously done here (accumulating FFT_AVERAGE_COUNT
// raw frames) is now done inside audio_capture. This function receives the
// already-averaged fft_source[] and fft_return[] from the AudioRawBlock.
// All EMA smoothing and TF computation remains here — only the data source
// has changed.
// -----------------------------------------------------------------------------
bool audioEngine_update(AudioFrame* frame) {


     if (!s_initialised || frame == nullptr) return false;


     // Check whether audio_capture has a fresh block for the live consumer.
     // This replaces the old fft_source.available() && fft_return.available() check.
     if (!audioCap_isBlockFresh(AudioConsumer::LIVE)) {
          return false;
     }


     // Consume the block — get a const reference to the posted AudioRawBlock.
     // This does NOT copy the data; it reads directly from audio_capture's slot.
     const AudioRawBlock& block = audioCap_getBlock(AudioConsumer::LIVE);


     // FIX [double-scaling]: The previous version had two copy loops.
     // The first copied block data correctly (no scaling). The second then
     // re-multiplied by inv = 1.0/FFT_AVERAGE_COUNT, dividing magnitudes a
// second time. audio_capture already averages over FFT_AVERAGE_COUNT
// frames — dividing again pushed magnitudes lower than intended and
// would cause the TF source gate (TF_SOURCE_GATE) to suppress bins
// that should have been energised.
//
// Fix: copy directly from block with no scaling. The data is ready to use.
for (int k = 0; k < FFT_BINS; k++) {
       frame->fft_source[k] = block.fft_source[k];
       frame->fft_return[k] = block.fft_return[k];
}


// Mark the live consumer slot as consumed.
// Must be called after reading all data from the block reference.
audioCap_markConsumed(AudioConsumer::LIVE);


{     // scope: TF / EMA / confidence computation — data source changed, logic unchanged


// --- Step 2: Transfer function with EMA smoothing ---
//
// H_dB[k] = 20 * log10( avg_return[k] / avg_source[k] )
//
// Per bin:
//      Energised (source >= TF_SOURCE_GATE):
//        Compute raw H_dB, clamp, apply EMA, store in frame->tf_db[k].
//        Increment energised counter for confidence.
//
//      Unenergised (source < TF_SOURCE_GATE):
//        Set frame->tf_db[k] = NAN.
//
// --- TF PERSISTENCE BEHAVIOUR ---
// For unenergised bins, s_tf_smoothed[k] is LEFT UNCHANGED.
// The EMA buffer retains the last valid smoothed value.
// frame->tf_db[k] carries NAN (display shows a gap; confidence warning fires),
// but the internal history is preserved so the curve rebuilds smoothly when
// signal returns rather than jumping from 0 dB each time.
//
// This is the "sticky instrument" design choice. See config.h for the full
// discussion and instructions for switching to "strict live measurement."
// To switch: uncomment the line "s_tf_smoothed[k] = 0.0f;" below.


const float alpha        = TF_SMOOTHING_ALPHA;
const float one_minus = 1.0f - alpha;
int            energised = 0;


// FIX [confidence-denominator]: count in-band bins separately so
// tf_confidence is reported over the analysis band (200 Hz–10 kHz) rather
// than the full 512-bin range. See Step 3 below for the reason this matters.
int in_band_energised = 0;
int in_band_total      = 0;
const float bin_hz_for_conf = (float)SAMPLE_RATE / (float)FFT_SIZE;
const int   k_conf_lo       = (int)(200.0f   / bin_hz_for_conf);   // 200 Hz
const int   k_conf_hi       = (int)(10000.0f / bin_hz_for_conf);   // 10 kHz


// TODO-29: clear this block's clamp markers. tf_db[] is republished every
// block, so its "is this a rail?" annotation must be republished with it —
// a stale bit would mislabel a good measurement as saturated.
memset(frame->tf_clamped_bits, 0, sizeof(frame->tf_clamped_bits));
frame->tf_clamped_count = 0;


for (int k = 0; k < FFT_BINS; k++) {


       float src = frame->fft_source[k];
    float ret = frame->fft_return[k];


    bool in_band = (k >= k_conf_lo && k <= k_conf_hi);
    if (in_band) in_band_total++;


    // FIX [nan-input]: NaN propagates silently — NaN < TF_SOURCE_GATE is
    // false, so without an explicit isfinite check the bin falls through to
    // log10f(NaN/NaN) = NaN, constrain(NaN) = NaN (Arduino macro), and the
    // EMA latches NaN permanently until audioEngine_resetSmoothing(). The
    // FFT race in audio_capture.cpp can produce NaN samples in rare ISR/
    // main-loop interleavings; the guard prevents permanent bin poisoning.
    if (!isfinite(src) || !isfinite(ret) || src < TF_SOURCE_GATE) {
        // Unenergised or invalid bin — mark as undefined for display
        // s_tf_smoothed[k] is intentionally LEFT UNCHANGED (TF persistence).
        frame->tf_db[k] = NAN;
        // s_tf_smoothed[k] = 0.0f;     // ← Uncomment to switch to strict mode
        continue;
    }


    energised++;
    if (in_band) in_band_energised++;


    // Floor return at 1e-6 (≈ –120 dBFS) to avoid log(0).
    // Occurs on bins fully attenuated by the rig (e.g. extreme high-frequency
    // rolloff from a long, capacitive cable run).
    if (ret < 1e-6f) ret = 1e-6f;


    // FIX [tf-outlier]: discard bins where ret/src is physically impossible
    // for a passive (or near-unity) rig. A bin where src is just above the
    // gate (~0.001) and ret is loud (e.g. 0.5) produces tf_raw ≈ +54 dB —
    // the constrain() below clips it, but the EMA still pollutes for ~20
    // blocks. The 20 dB threshold accommodates active boost pedals but
    // rejects unphysical glitches and route-change transients.
    if (ret > 10.0f * src) {
        frame->tf_db[k] = NAN;
        continue;
    }


    // Raw TF value in dB
    float tf_raw = 20.0f * log10f(ret / src);


    // Final defence: even with the guards above, ensure tf_raw is finite
    // before letting it touch the EMA history.
    if (!isfinite(tf_raw)) {
        frame->tf_db[k] = NAN;
        continue;
    }


    // Clamp before EMA to prevent boundary-bin outliers from corrupting
    // the smoothing history. 6 dB beyond display range is a generous margin.
    //
    // TODO-29: the clamp itself is UNCHANGED — it is doing its job, and the
    // numbers it produces are byte-for-byte what they were. What is new is
    // that we RECORD it. Before this, a clamped bin was written into tf_db[k]
    // as a bare number and every consumer displayed the rail as though it
    // were a measured transfer function. Marking the bin lets a renderer say
    // "saturated" instead of quoting the rail as data.
    const float tf_lo = TF_DB_MIN - 6.0f;
    const float tf_hi = TF_DB_MAX + 6.0f;
    if (tf_raw < tf_lo || tf_raw > tf_hi) {
        frame->tf_clamped_bits[k >> 5] |= (1UL << (k & 31));
        frame->tf_clamped_count++;
    }
    tf_raw = constrain(tf_raw, tf_lo, tf_hi);


    // Apply EMA. First block after reset converges from 0 toward true TF.
    s_tf_smoothed[k] = alpha * tf_raw + one_minus * s_tf_smoothed[k];


    frame->tf_db[k] = s_tf_smoothed[k];
}


// --- Step 3: Confidence and persistence flag ---
// FIX [confidence-denominator]: previously divided by FFT_BINS (=512), which
// hard-capped tf_confidence near ~0.45 even with a perfect broadband stimulus
// (only ~228 of 512 bins are inside the validation analysis band 200-10k Hz).
// The validation suite's LOOPBACK_CONFIDENCE_MIN (0.50) was unreachable.
// Reporting confidence over the in-band bin count matches the meaning the
// rest of the firmware uses for quality metrics.
frame->tf_confidence          = (in_band_total > 0)
                                    ? (float)in_band_energised / (float)in_band_total
                                    : 0.0f;
frame->tf_persistence_active = (energised < FFT_BINS);      // Any NAN bins?


// --- Step 4: Peak levels ---
// v0.4: Peak levels come from AudioRawBlock (computed by audio_capture).
// AudioAnalyzePeak objects are now owned by audio_capture.cpp.
frame->peak_source_dbfs = block.peak_source_dbfs;
frame->peak_return_dbfs = block.peak_return_dbfs;
frame->source_clipping   = block.source_clipping;
frame->return_clipping   = block.return_clipping;


// --- Step 5: Metadata ---
// v0.4: Use the canonical block counter from audio_capture.
frame->output_block_number = block.audio_block_counter;
frame->timestamp_ms           = block.timestamp_ms;
frame->active_route           = s_active_route;
    } // end scope block


    return true;
}


// -----------------------------------------------------------------------------
// audioEngine_setRoute(route)
// -----------------------------------------------------------------------------
void audioEngine_setRoute(const SignalRoute& route) {
    // Update the route record kept in this module for AudioFrame metadata.
    s_active_route = route;


    // Reset EMA smoothing — old history from the previous binding is meaningless.
    // audio_capture's accumulator is cleared by audioCap_notifyRouteChanged below.
    audioEngine_resetSmoothing();


    // Delegate route application (mixer gains) and event notification to
    // audio_capture, which owns the mixer hardware.
    // audioCap_notifyRouteChanged():
    //   1. Applies new mixer gains via its own applyRoute() helper
    //   2. Clears audio_capture's accumulator
    //   3. Latches AudioCaptureEvent::ROUTE_CHANGED for the next loop iteration
    audioCap_notifyRouteChanged(route.source_node_ch, route.return_node_ch);


    Serial.printf("[AudioEngine] Route updated: %s\n", route.description);
}


// -----------------------------------------------------------------------------
// CHANGED [todo-50]: audioEngine_setRouteDescription(description)
//
// Updates ONLY the human-readable description carried in AudioFrame metadata.
// Deliberately does NOT: apply mixer gains, reset EMA smoothing, or call
// audioCap_notifyRouteChanged(). No ROUTE_CHANGED event is raised.
//
// WHY THIS EXISTS: signalRouter_init() does not call audioEngine_setRoute(),
// because boot is not a route-change transition (ADR-004 Decision 2 — that is
// the property that makes TS-at-boot clean, with no relay actuation and no
// spurious measurement abort). The consequence was that audio_engine kept the
// description from its OWN init() and the 5 s diagnostic printed
// "Route: Default bench: SOURCE_NODE=L, RETURN_NODE=R" on a board whose router
// was in TS. The same stale string went to the Pi in ROUTER_STATUS, so a UI
// would have shown it too.
//
// The router's state was always authoritative and correct; only this
// PRESENTATION copy was stale. This setter closes that gap without
// reintroducing the boot transition ADR-004 removed on purpose.
//
// NOT a substitute for audioEngine_setRoute(). A real route change must go
// through setRoute() so that gains, smoothing and the event all follow.
//
// LIFETIME: stores the caller's pointer, exactly as setRoute() already does.
// signal_router passes its module-static s_description buffer in both cases,
// so the semantics here are unchanged from the existing path.
// -----------------------------------------------------------------------------
void audioEngine_setRouteDescription(const char* description) {
    if (description == nullptr) return;
    s_active_route.description = description;
}


// -----------------------------------------------------------------------------
// audioEngine_getRoute()
// -----------------------------------------------------------------------------
const SignalRoute& audioEngine_getRoute() {
    return s_active_route;
}


// -----------------------------------------------------------------------------
// audioEngine_setInputGain(gain_db)
// v0.4: Thin wrapper around audioCap_setInputGain().
// Gain control and capture-invalidation event are owned by audio_capture.
// This function exists for call-site compatibility with pre-v0.4 code.
// -----------------------------------------------------------------------------
void audioEngine_setInputGain(float gain_db) {
    audioCap_setInputGain(gain_db);
    Serial.printf("[AudioEngine] Input gain delegated to audioCap_setInputGain(%.1f)\n",
                   gain_db);
}
// -----------------------------------------------------------------------------
// audioEngine_resetSmoothing()
// -----------------------------------------------------------------------------
void audioEngine_resetSmoothing() {
    // Clears the EMA smoothing buffer only.
    // The averaging accumulator is owned by audio_capture and is cleared
    // automatically on route/gain changes via audioCap_notifyRouteChanged().
    memset(s_tf_smoothed, 0, sizeof(s_tf_smoothed));
    Serial.println("[AudioEngine] EMA smoothing buffer reset.");
}


// -----------------------------------------------------------------------------
// Conversion helpers
// -----------------------------------------------------------------------------
float audioEngine_binToHz(int bin) {
    return (float)bin * ((float)SAMPLE_RATE / (float)FFT_SIZE);
}


int audioEngine_hzToBin(float freq_hz) {
    // FIX [nan-input]: NaN/Inf and negative inputs map to bin 0 deterministically
    // rather than depending on the (int)roundf(NaN) UB. Callers passing
    // out-of-range frequencies should treat bin 0 as "no valid bin".
    if (!isfinite(freq_hz) || freq_hz <= 0.0f) return 0;
    float bin_f = freq_hz / ((float)SAMPLE_RATE / (float)FFT_SIZE);
    int   bin   = (int)roundf(bin_f);
    if (bin < 0)             bin = 0;
    if (bin >= FFT_BINS)     bin = FFT_BINS - 1;
    return bin;
}


float audioEngine_linearToDbfs(float linear) {
    // FIX [nan-input]: explicit isfinite check before the comparison.
    // NaN compares unordered (NaN <= 0.0f is false), so a NaN would slip
    // past the original guard and reach log10f(NaN). The Arduino max()
    // macro evaluates its arguments twice — for log10f(NaN) that means
    // two NaN computations and a final NaN return, despite the floor.
    if (!isfinite(linear) || linear <= 0.0f) return -120.0f;
    float db = 20.0f * log10f(linear);
    return (db < -120.0f) ? -120.0f : db;
}


// -----------------------------------------------------------------------------
// audioEngine_tfBinClamped(frame, bin)
// TODO-29. See audio_engine.h for the contract and the reason this exists.
// -----------------------------------------------------------------------------
bool audioEngine_tfBinClamped(const AudioFrame* frame, int bin) {
    if (frame == nullptr)  return false;
    if (bin < 0 || bin >= FFT_BINS) return false;
    return (frame->tf_clamped_bits[bin >> 5] & (1UL << (bin & 31))) != 0;
}
