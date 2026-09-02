// =============================================================================
// audio_capture.h    —   Guitar Rig Analyzer   v0.5.0
// =============================================================================
// Single audio acquisition layer. Captures stereo I2S blocks from the
// SGTL5000 codec exactly once per block and distributes snapshots to
// registered downstream consumers via a double-buffered slot model.
//
// CHANGELOG v0.4.1
// ----------------
// FIX [event-api]: audioCap_pollEvent() did not exist in the public API —
//   the comments referenced it but the actual mechanism is audioCap_update()
//   returning an AudioCaptureEvent. All comments now reference audioCap_update()
//   as the event source. audioCap_pollEvent() is removed from all comments.
//
// FIX [route-change]: The header promised that audio_capture surfaces route
//   changes as ROUTE_CHANGED events, but provided no mechanism for the
//   outside world to notify audio_capture that a route change occurred.
//   audioCap_notifyRouteChanged(source_ch, return_ch) is now added to the
//   public API. audioEngine_setRoute() must call this to delegate hardware
//   routing — audioCap_notifyRouteChanged() is what actually programs the
//   mixer gains (audio_capture owns the mixers). The dependency is documented
//   in both directions: here, and in audio_engine.h.
//
// OWNERSHIP RULE
// --------------
// This module owns the entire SINK chain: SGTL5000 codec, AudioInputI2S,
// the two routing AudioMixer4s (s_mixer_src / s_mixer_ret), AudioAnalyzeFFT1024
// (live FFT path), AudioAnalyzePeak (level meters), AudioRecordQueue (raw
// samples for the precision path), AudioOutputI2S (headphone monitor), and
// AudioControlSGTL5000. No other module calls the Audio Library's input,
// codec, peak, FFT, or capture-queue objects directly.
//
// signal_generator.cpp is the ONE exception, and only for the SOURCE chain:
// it owns its own AudioSynthWaveformSine / AudioSynthNoiseWhite / AudioMixer4
// and feeds the result into s_mixer_ret slot 2 by contract. applyRoute() and
// audioCap_notifyRouteChanged() are aware of slot 2 and restore its gain to
// 1.0f after every route change.
//
// TWO CONSUMERS
// -------------
// CONSUMER_LIVE      → audio_engine (live display path)
// CONSUMER_MEASURE → measurement_engine (precision measurement path)
//
// Each consumer has its own AudioRawBlock slot. When a new I2S block is
// ready, both slots are updated in the same audioCap_update() call.
// Each consumer reads its own slot independently.
//
// BLOCK COUNTER AS CANONICAL TIMEBASE
// ------------------------------------
// audio_block_counter in AudioRawBlock is the canonical timing primitive
// for the entire system. It increments once per 128-sample I2S block
// (≈2.9 ms at 44,100 Hz). All timing references — generator start,
// capture start, latency measurement — derive from this counter.
// No module invents its own sense of audio time.
//
// EVENT NOTIFICATION MODEL
// ------------------------
// audioCap_update() is called once per main loop iteration. It returns
// an AudioCaptureEvent describing the highest-priority pending event.
// The main loop acts on this return value and forwards events to downstream
// consumers as appropriate. There is no separate poll function.
// =============================================================================


#ifndef AUDIO_CAPTURE_H
#define AUDIO_CAPTURE_H


#include <Arduino.h>
#include "config.h"


// =============================================================================
// CONSUMER IDENTIFIERS
// =============================================================================
enum class AudioConsumer : uint8_t {
     LIVE    = 0,     // audio_engine — live display path
     MEASURE = 1,     // measurement_engine — precision measurement path
     COUNT   = 2      // sentinel — number of consumers
};


// =============================================================================
// AudioRawBlock
// =============================================================================
// A snapshot of one averaged output block from the audio capture layer.
// This is the data contract between audio_capture and its consumers.
// Consumers receive a const reference — they never write to this struct.
//
// DESIGN CONSTRAINT: AudioRawBlock carries averaged magnitude FFT data
// sized for FFT_BINS (512 bins, 1024-point FFT). It is the LIVE-PATH
// data structure. The precision measurement path (measurement_engine)
// uses its own CMSIS-DSP complex accumulator and does NOT use
// fft_source/fft_return for precision work — those fields are for
// audio_engine (live spectrum display) only.
// =============================================================================
struct AudioRawBlock {


     // -------------------------------------------------------------------------
     // CANONICAL TIMING
     // -------------------------------------------------------------------------
     // audio_block_counter: the master timebase. Increments once per
     // 128-sample I2S block. Do not substitute millis() for any decision
     // that requires sample-accurate alignment.
     uint32_t audio_block_counter;
     uint32_t timestamp_ms;          // Wall-clock secondary reference only


     // -------------------------------------------------------------------------
     // AVERAGED FFT MAGNITUDES (linear, 0.0–1.0) — LIVE PATH ONLY
     // -------------------------------------------------------------------------
     // Mean of FFT_AVERAGE_COUNT raw 1024-point FFT frames.
     // Used by audio_engine for live spectrum and TF display.
     // measurement_engine does NOT use these for precision measurements —
     // it maintains its own complex accumulator at the required FFT size.
     float fft_source[FFT_BINS];      // SOURCE_NODE, 512 bins
     float fft_return[FFT_BINS];      // RETURN_NODE, 512 bins


     // -------------------------------------------------------------------------
     // PEAK LEVELS (dBFS)
     // -------------------------------------------------------------------------
     float peak_source_dbfs;
     float peak_return_dbfs;


     // -------------------------------------------------------------------------
     // CLIPPING FLAGS
     // -------------------------------------------------------------------------
     bool source_clipping;
     bool return_clipping;


     // -------------------------------------------------------------------------
     // SIGNAL ROUTE SNAPSHOT
     // -------------------------------------------------------------------------
     uint8_t source_node_ch;    // Physical I2S channel → SOURCE_NODE
     uint8_t return_node_ch;    // Physical I2S channel → RETURN_NODE


     // -------------------------------------------------------------------------
     // AVERAGING METADATA
     // -------------------------------------------------------------------------
     uint8_t frames_averaged;      // Normally FFT_AVERAGE_COUNT; may be less after
                                   // a route change mid-accumulation
};


// =============================================================================
// AUDIO CAPTURE EVENTS
// =============================================================================
// Returned by audioCap_update(). The main loop observes this return value
// and acts on it. There is no separate poll function — audioCap_update()
// IS the event notification mechanism.
//
// Only one event is returned per audioCap_update() call. If multiple events
// are pending, the highest-priority is returned first; lower-priority
// events remain pending for subsequent calls.
//
// Priority order (highest first):
//    CLIP_SOURCE, CLIP_RETURN > ROUTE_CHANGED > BLOCK_READY > NONE
enum class AudioCaptureEvent : uint8_t {
     NONE            = 0,   // No pending event; no new block this call
     BLOCK_READY     = 1,   // New block posted to both consumer slots
     CLIP_SOURCE     = 2,   // Source clipping detected (latched until returned)
     CLIP_RETURN     = 3,   // Return clipping detected (latched until returned)
     ROUTE_CHANGED = 4,     // Route changed via audioCap_notifyRouteChanged()
                            // Block counter at change available via
                            // audioCap_getLastRouteChangedBlock()
};


// =============================================================================
// PUBLIC API
// =============================================================================


// -----------------------------------------------------------------------------
// audioCap_init()
// Initialise Audio Library, SGTL5000 codec, FFT and peak objects.
// Returns true on success; false if SGTL5000 does not respond on I2C.
// Call once from setup() before any other audio function.
// -----------------------------------------------------------------------------
bool audioCap_init();


// -----------------------------------------------------------------------------
// audioCap_update()
// CALL ONCE PER MAIN LOOP ITERATION.
//
// Drives the audio capture pipeline:
//    1. Checks if FFT_AVERAGE_COUNT raw frames have accumulated (non-blocking)
//    2. If ready: fills both consumer slots with a fresh AudioRawBlock
//    3. Marks both consumers' blocks as fresh
//    4. Increments audio_block_counter
//    5. Checks for clipping; latches clip events
//
// FIX [event-api]: Returns AudioCaptureEvent directly. This IS the event
// notification mechanism — there is no separate audioCap_pollEvent().
// The main loop should read the return value every iteration and act on it:
//
//    AudioCaptureEvent ev = audioCap_update();
//    if (ev == AudioCaptureEvent::BLOCK_READY) {
//          // notify consumers
//    } else if (ev == AudioCaptureEvent::ROUTE_CHANGED) {
//          // measurement_engine should abort if in CAPTURE
//    }
//
// audio_capture does NOT call into audio_engine or measurement_engine.
// It distributes data; the main loop coordinates consumer reactions.
// -----------------------------------------------------------------------------
AudioCaptureEvent audioCap_update();


// -----------------------------------------------------------------------------
// audioCap_getBlock(consumer)
// Returns a const reference to the most recently posted block for the
// specified consumer. Updated in place each time audioCap_update() posts
// a new block. Caller must read before the next audioCap_update() call.
// -----------------------------------------------------------------------------
const AudioRawBlock& audioCap_getBlock(AudioConsumer consumer);


// -----------------------------------------------------------------------------
// audioCap_isBlockFresh(consumer)
// Returns true if a new block has been posted since the last call to
// audioCap_markConsumed(consumer).
// -----------------------------------------------------------------------------
bool audioCap_isBlockFresh(AudioConsumer consumer);


// -----------------------------------------------------------------------------
// audioCap_markConsumed(consumer)
// Marks the current block as consumed for this consumer.
// Call after reading and processing the block.
// -----------------------------------------------------------------------------
void audioCap_markConsumed(AudioConsumer consumer);


// -----------------------------------------------------------------------------
// audioCap_getBlockCounter()
// Returns the current audio block counter (canonical timebase).
// Same value as the most recently posted AudioRawBlock.audio_block_counter.
// Use when you need the current counter without waiting for a new block.
// -----------------------------------------------------------------------------
uint32_t audioCap_getBlockCounter();


// -----------------------------------------------------------------------------
// audioCap_notifyRouteChanged(source_ch, return_ch)
//
// FIX [route-change]: This function was missing from v0.4.0.
//
// Must be called by audioEngine_setRoute() immediately after changing
// the mixer gains. This is the mechanism by which audio_capture learns
// that the signal routing has changed.
//
// audio_capture records:
//   - The block counter at the time of the change
//   - The new channel assignments (for the next AudioRawBlock snapshot)
//
// On the next audioCap_update() call, a ROUTE_CHANGED event is returned.
// The main loop forwards this to measurement_engine, which can then decide
// whether to abort an in-progress capture.
//
// DEPENDENCY NOTE: audio_engine.h (audioEngine_setRoute) depends on this
// function. audio_capture.h depends on nothing in audio_engine — the
// dependency is one-directional: audio_engine → audio_capture.
// This is correct: audio_capture is the lower layer.
//
// Parameters:
//   source_ch — new physical I2S channel for SOURCE_NODE (0 or 1)
//   return_ch — new physical I2S channel for RETURN_NODE (0 or 1)
// -----------------------------------------------------------------------------
void audioCap_notifyRouteChanged(uint8_t source_ch, uint8_t return_ch);


// -----------------------------------------------------------------------------
// audioCap_getLastRouteChangedBlock()
// Returns the block counter at which the most recent route change was
// notified via audioCap_notifyRouteChanged(). Returns 0 if no route
// change has occurred since init.
// Used by measurement_engine to determine whether a route change occurred
// during an active accumulation window.
// -----------------------------------------------------------------------------
uint32_t audioCap_getLastRouteChangedBlock();


// -----------------------------------------------------------------------------
// audioCap_setInputGain(gain_db)
// Adjusts SGTL5000 line-in PGA gain and raises a ROUTE_CHANGED event
// (via the same internal path as audioCap_notifyRouteChanged) so that
// measurement_engine can abort any in-progress capture.
// A gain change has the same invalidating effect on precision measurements
// as a route change.
// -----------------------------------------------------------------------------
void audioCap_setInputGain(float gain_db);


// =============================================================================
// RAW SAMPLE CAPTURE API — Complex FFT measurement path
// =============================================================================
// These functions provide access to raw int16→float32 sample streams from
// the AudioRecordQueue objects in audio_capture.cpp. They are used exclusively
// by measurement_engine to obtain time-domain samples for CMSIS-DSP complex FFT.
//
// USAGE SEQUENCE (measurement_engine internal):
//   audioCap_beginRawCapture();           // arm queues on CAPTURE entry
//   while (capturing) {
//       if (audioCap_rawSamplesAvailable() >= BLOCKS_PER_FFT) {
//           audioCap_getRawSamples(src, ret, BLOCKS_PER_FFT);   // drain one FFT frame
//           // apply Hann window, run arm_cfft_f32(), accumulate cross-spectrum
//       }
//   }
//   audioCap_endRawCapture();              // disarm queues on CAPTURE exit (any path)
//
// BLOCKS_PER_FFT = FFT_SIZE / AUDIO_BLOCK_SAMPLES = 1024 / 128 = 8 blocks.


// -----------------------------------------------------------------------------
// audioCap_beginRawCapture()
// Arms both AudioRecordQueue objects. Call at CAPTURE state entry.
// Clears any stale blocks from a previous run before arming.
// -----------------------------------------------------------------------------
void audioCap_beginRawCapture();


// -----------------------------------------------------------------------------
// audioCap_rawSamplesAvailable()
// Returns the number of complete 128-sample blocks in the source queue.
// Both queues fill at the same rate; checking source is authoritative.
// Use this to know when getRawSamples() can be called.
// -----------------------------------------------------------------------------
int audioCap_rawSamplesAvailable();


// -----------------------------------------------------------------------------
// audioCap_getRawSamples(src_out, ret_out, n_blocks)
// Drains n_blocks × 128 samples from each queue into float32 output buffers.
// Converts int16 Audio Library samples (–32768..+32767) to float32 (–1.0..+1.0).
// Returns true if n_blocks were available and all were consumed.
// Returns false if insufficient blocks, or on a rare ISR-race nullptr.
// All-or-none contract: on false return, both queues are fully flushed so
// the caller's next call begins from a fresh, contiguous window.
// Caller must ensure src_out and ret_out each hold n_blocks × 128 floats.
// -----------------------------------------------------------------------------
bool audioCap_getRawSamples(float* src_out, float* ret_out, int n_blocks);


// -----------------------------------------------------------------------------
// audioCap_endRawCapture()
// Disarms queues and discards buffered blocks. Call at CAPTURE exit (any path:
// completion, abort, cancel). Not calling this leaks memory continuously.
// -----------------------------------------------------------------------------
void audioCap_endRawCapture();


#endif // AUDIO_CAPTURE_H
