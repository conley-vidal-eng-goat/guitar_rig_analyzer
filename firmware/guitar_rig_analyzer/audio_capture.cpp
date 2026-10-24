// =============================================================================
// audio_capture.cpp     —   Guitar Rig Analyzer
// =============================================================================
// Implementation of the single audio acquisition layer.
//
// THIS FILE IS THE ONLY PLACE IN THE FIRMWARE THAT OWNS I2S HARDWARE.
// No other module instantiates AudioInputI2S, AudioAnalyzeFFT1024,
// AudioAnalyzePeak, or AudioControlSGTL5000. Enforcing this boundary is
// what makes the dual-consumer model trustworthy — both consumers get
// their data from the same snapshot, not from independent capture calls
// that could produce different data for the same nominal time window.
//
// WHAT THIS FILE DOES
// -------------------
// 1. Owns the Audio Library object graph (I2S in/out, mixers, FFTs, peaks,
//    record queues, SGTL5000 codec).
// 2. On each audioCap_update() call, checks whether FFT_AVERAGE_COUNT raw
//    frames have accumulated. When they have, posts an AudioRawBlock to
//    both consumer slots atomically. The AudioRawBlock.audio_block_counter
//    field is stamped from a micros()-derived 128-sample block counter because
//    Teensyduino 1.60 does not expose the Audio Library's internal update
//    counter publicly.
// 3. Tracks route and gain change notifications (from audioEngine_setRoute()
//    and audioCap_setInputGain()) and surfaces them as ROUTE_CHANGED events.
// 4. Latches clipping events and returns them at higher priority than
//    BLOCK_READY so consumers never miss an overload condition.
// 5. Provides raw sample capture path for the complex FFT measurement pipeline:
//    audioCap_beginRawCapture() arms AudioRecordQueue objects on both channels.
//    audioCap_getRawSamples() dequeues exactly FFT_SIZE samples per channel.
//    audioCap_endRawCapture() disarms and flushes the queues.
//    This gives measurement_engine access to complex time-domain samples for
//    CMSIS-DSP arm_cfft_f32(), enabling true S_xy_im and real per-bin phase.
//
// RELATIONSHIP TO audio_engine.cpp (v0.4 REFACTOR)
// -------------------------------------------------
// Before v0.4, audio_engine.cpp owned the Audio Library objects and the
// accumulator. In v0.4, those responsibilities move here. audio_engine.cpp
// is refactored to:
//   - Remove its Audio Library object declarations (they live here now)
//   - Remove its accumulator (the accumulator lives here now)
//   - Consume AudioRawBlock from audioCap_getBlock(CONSUMER_LIVE) instead
//     of calling fft_source.read() directly
//   - Keep its EMA smoothing, TF computation, and AudioFrame production
//     (those remain audio_engine's responsibility)
//
// The Audio Library patch cables must live in exactly one translation unit.
// They live here. audio_engine.cpp no longer declares AudioConnection objects.
//
// AUDIO OBJECT GRAPH
// ------------------
//   i2s_in (L) → mixer_src slot 0     ─┐
//   i2s_in (R) → mixer_src slot 1       │ applyRoute() sets one slot to 1.0,
//                                          │ the other to 0.0
//   i2s_in (L) → mixer_ret slot 0     ─┘
//   i2s_in (R) → mixer_ret slot 1
//
//   mixer_src → fft_src        (averaged FFT magnitudes → AudioRawBlock.fft_source)
//   mixer_src → peak_src       (true peak → AudioRawBlock.peak_source_dbfs)
//   mixer_src → queue_src      (raw samples → complex FFT measurement path)
//   mixer_ret → fft_ret        (averaged FFT magnitudes → AudioRawBlock.fft_return)
//   mixer_ret → peak_ret       (true peak → AudioRawBlock.peak_return_dbfs)
//   mixer_ret → queue_ret      (raw samples → complex FFT measurement path)
//
//   mixer_src → i2s_out L   (development monitoring passthrough — see config.h)
//   mixer_ret → i2s_out R   (development monitoring passthrough)
//
// =============================================================================


#include "audio_capture.h"
#include <Audio.h>
#include <Wire.h>


// =============================================================================
// AUDIO LIBRARY OBJECT GRAPH
// =============================================================================
// All Audio Library objects are file-scope globals. The Audio Library registers
// them automatically at startup; they must exist for the duration of the program.
// Declaring them here — and only here — ensures no other translation unit can
// accidentally claim I2S ownership.


// Stereo I2S input from SGTL5000
static AudioInputI2S         s_i2s_in;


// Channel selector mixers — one per logical signal node.
// applyRoute() sets exactly one input slot to gain 1.0, all others to 0.0.
// Slots 0 and 1 are wired to I2S LEFT and RIGHT respectively.
static AudioMixer4           s_mixer_src;        // Selects physical channel → SOURCE_NODE
AudioMixer4                  s_mixer_ret;        // Selects physical channel → RETURN_NODE
// Non-static: signal_generator.cpp writes to slot 2 for bench monitor output.
// Slots 0 and 1 are owned by applyRoute() for I2S channel selection.
// Slot 2 carries generator monitor; slot 3 unused.


// Analysis objects
static AudioAnalyzeFFT1024   s_fft_src;       // 1024-point FFT on SOURCE_NODE path
static AudioAnalyzePeak      s_peak_src;      // True-peak meter on SOURCE_NODE path
static AudioAnalyzeFFT1024   s_fft_ret;       // 1024-point FFT on RETURN_NODE path
static AudioAnalyzePeak      s_peak_ret;      // True-peak meter on RETURN_NODE path


// Development monitoring passthrough output (see HEADPHONE PASSTHROUGH in config.h)
// SOURCE_NODE → left ear, RETURN_NODE → right ear.
// This is temporary bench-harness behaviour — not the final product UX.
static AudioOutputI2S        s_i2s_out;


// Raw sample queues for the complex FFT measurement path.
// When armed (by audioCap_beginRawCapture()), these queues buffer raw
// 128-sample Audio Library blocks. measurement_engine drains them to get
// FFT_SIZE time-domain samples per channel, applies a Hann window, and
// runs CMSIS-DSP arm_cfft_f32() to obtain true complex spectra.
//
// Queue depth: 53 × 128 = 6,784 samples ≈ 6.6 FFT frames.
// This is enough to guarantee one full FFT_SIZE (1024-sample) frame is
// available for measurement_engine to drain each time it needs one,
// even if the main loop has a ±1 block latency.
// Total memory: 53 × 128 × 2 channels × 2 bytes (int16) = 27,136 bytes ≈ 27 KB
// Allocated from AudioMemory() pool — increase AudioMemory() if needed.
static AudioRecordQueue      s_queue_src;      // Raw samples — SOURCE_NODE
static AudioRecordQueue      s_queue_ret;      // Raw samples — RETURN_NODE


// Codec control
#if ENABLE_SGTL_REGISTER_DUMP
// -----------------------------------------------------------------------------
// SGTL5000RegisterReader — minimal subclass exposing the protected read().
//
// AudioControlSGTL5000::read() is protected, not private, so a subclass can
// publish it without touching any library file. This adds no state and no
// virtual overrides; it exists purely so the diagnostic below can observe the
// codec. write() is deliberately NOT exposed — this diagnostic is read-only.
// -----------------------------------------------------------------------------
class SGTL5000RegisterReader : public AudioControlSGTL5000 {
public:
    using AudioControlSGTL5000::read;
};
static SGTL5000RegisterReader s_sgtl5000;
#else
static AudioControlSGTL5000 s_sgtl5000;
#endif


// --- Patch cables ---
// I2S LEFT   (ch 0) → both mixers on slot 0
static AudioConnection s_conn_L_msrc(s_i2s_in, 0, s_mixer_src, 0);
static AudioConnection s_conn_L_mret(s_i2s_in, 0, s_mixer_ret, 0);


// I2S RIGHT (ch 1) → both mixers on slot 1
static AudioConnection s_conn_R_msrc(s_i2s_in, 1, s_mixer_src, 1);
static AudioConnection s_conn_R_mret(s_i2s_in, 1, s_mixer_ret, 1);


// SOURCE_NODE path → FFT, peak, and raw queue
static AudioConnection s_conn_msrc_fft      (s_mixer_src, 0, s_fft_src,   0);
static AudioConnection s_conn_msrc_peak (s_mixer_src, 0, s_peak_src,      0);
static AudioConnection s_conn_msrc_queue(s_mixer_src, 0, s_queue_src, 0);


// RETURN_NODE path → FFT, peak, and raw queue
static AudioConnection s_conn_mret_fft      (s_mixer_ret, 0, s_fft_ret,   0);
static AudioConnection s_conn_mret_peak (s_mixer_ret, 0, s_peak_ret,     0);
static AudioConnection s_conn_mret_queue(s_mixer_ret, 0, s_queue_ret, 0);


// Monitoring passthrough — SOURCE → output L, RETURN → output R
static AudioConnection s_conn_msrc_out(s_mixer_src, 0, s_i2s_out, 0);
static AudioConnection s_conn_mret_out(s_mixer_ret, 0, s_i2s_out, 1);


// =============================================================================
// MODULE-PRIVATE STATE
// =============================================================================


// --- Consumer slots ---
// Two independent AudioRawBlock instances, one per consumer.
// audioCap_update() writes to both when a new block is ready.
// Consumers read from their own slot via audioCap_getBlock().
static AudioRawBlock s_blocks[static_cast<uint8_t>(AudioConsumer::COUNT)];


// Freshness flags — one per consumer.
// Set to true when audioCap_update() posts a new block.
// Cleared when the consumer calls audioCap_markConsumed().
static bool s_block_fresh[static_cast<uint8_t>(AudioConsumer::COUNT)];


// --- Linear magnitude accumulators (for AudioRawBlock.fft_source/return) ---
// Accumulate raw FFT magnitudes over FFT_AVERAGE_COUNT frames.
// double precision prevents rounding loss on the sum of many small floats.
// These produce the LIVE PATH averaged spectrum (not the precision complex acc.).
static double s_accum_src[FFT_BINS];
static double s_accum_ret[FFT_BINS];
static int    s_accum_count = 0;


// Teensy AudioStream::update_counter is not public in Teensyduino 1.60.
// Derive a monotonic 128-sample block counter from elapsed time instead.
static uint32_t audioBlockCounterFromMicros() {
    const double blocks_per_us =
        (double)SAMPLE_RATE / ((double)AUDIO_BLOCK_SAMPLES * 1000000.0);
    return (uint32_t)((double)micros() * blocks_per_us);
}


// --- Canonical audio block counter ---
// The canonical timebase for the entire system is a monotonic 128-sample block
// estimate derived from micros(). Teensyduino 1.60 does not expose the Audio
// Library's internal update counter publicly, so this preserves the same unit
// and wrap behaviour without depending on a private core symbol.
//
// audio_capture does not use an averaged-output counter for timing. That
// eliminates the previous bug where s_block_counter incremented once per
// averaged output block (~46.4 ms), making the claimed 2.9 ms timing precision
// 32× coarser than advertised.
//
// s_output_block_number: a separate display-only counter that increments once
// per averaged AudioRawBlock posted (i.e., once every FFT_AVERAGE_COUNT FFT frames).
// This appears in AudioRawBlock.output_block_number for UI display purposes only.
// It is NOT used for generator timing or latency measurement.
static uint32_t s_output_block_number = 0;
// --- Current route (channel binding) ---
// Updated by audioCap_notifyRouteChanged(). Snapshot into each AudioRawBlock.
static uint8_t s_source_ch = SOURCE_NODE_PHYSICAL_CH;
static uint8_t s_return_ch = RETURN_NODE_PHYSICAL_CH;


// --- Route change event state ---
// s_route_changed_pending: true from the moment notifyRouteChanged() is called
//    until the next audioCap_update() returns ROUTE_CHANGED.
// s_last_route_changed_block: block counter at the time of the last notification.
static bool      s_route_changed_pending     = false;
static uint32_t s_last_route_changed_block = 0;


// --- Clipping event latches ---
// Set when clipping is detected. Cleared when the event is returned by
// audioCap_update(). Latching ensures a clip is never silently dropped
// even if the main loop is slightly slow to call audioCap_update().
static bool s_clip_source_pending = false;
static bool s_clip_return_pending = false;

// TEMPORARY DIAGNOSTIC (2026-09-05) — state for the periodic raw sample dump
// in audioCap_update(). One 32+32 dump per 5 s: arm, wait for both queues,
// print, disarm. Periodic rather than one-shot because a startup dump is
// unobservable — the Teensy discards serial output before a USB host attaches,
// and a reset re-enumerates the device, tearing down any open connection.
// Remove both with that block.
static uint32_t s_raw_next_ms = 0;       // next arm time; 0 = arm immediately
static bool     s_raw_armed   = false;   // queues currently armed for a dump


// --- Init guard ---
static bool s_initialised = false;


// Cached current SGTL5000 line-in level. Used by audioCap_setInputGain() to
// suppress no-op ROUTE_CHANGED events when the requested level equals the
// current one — previously every setInputGain() call aborted in-progress
// measurements even if the value did not change.
static int s_current_line_in_level = SGTL5000_LINE_IN_LEVEL;


// =============================================================================
// PRIVATE HELPERS
// =============================================================================


// -----------------------------------------------------------------------------
// applyRoute(source_ch, return_ch)
// Programs mixer gains to route the specified physical I2S channels to the
// SOURCE_NODE and RETURN_NODE analysis paths.
//
// For s_mixer_src: the slot matching source_ch gets gain 1.0; others get 0.0.
// For s_mixer_ret: the slot matching return_ch gets gain 1.0; others get 0.0.
// NOTE: slot 2 of s_mixer_ret is used by signal_generator.cpp for bench
// monitoring. applyRoute() zeros it as a side-effect of clearing unused slots;
// audioCap_notifyRouteChanged() restores it to 1.0f immediately after
// applyRoute() so the monitor survives route changes automatically.
//
// This is the ONLY place in the firmware where physical channel numbers (0, 1)
// are used to configure hardware. Everything above this layer uses node names.
// -----------------------------------------------------------------------------
static void applyRoute(uint8_t source_ch, uint8_t return_ch) {
     // Clamp to valid range (only slots 0 and 1 are wired)
     source_ch = source_ch % 2;
     return_ch = return_ch % 2;


     // SOURCE_NODE mixer: pass only the source channel
    s_mixer_src.gain(0, (source_ch == 0) ? 1.0f : 0.0f);
    s_mixer_src.gain(1, (source_ch == 1) ? 1.0f : 0.0f);
    s_mixer_src.gain(2, 0.0f);
    s_mixer_src.gain(3, 0.0f);


    // RETURN_NODE mixer: pass only the return channel
    s_mixer_ret.gain(0, (return_ch == 0) ? 1.0f : 0.0f);
    s_mixer_ret.gain(1, (return_ch == 1) ? 1.0f : 0.0f);
    s_mixer_ret.gain(2, 0.0f);
    s_mixer_ret.gain(3, 0.0f);
}


// -----------------------------------------------------------------------------
// clearAccumulators()
// Resets magnitude accumulator arrays and frame count to zero.
// Called after each completed output block and on route/gain change.
// When a route or gain change occurs mid-accumulation, any partially
// accumulated frames are invalid (they mix data from different channel
// bindings or gain levels). Clearing ensures the next block starts clean.
// -----------------------------------------------------------------------------
static void clearAccumulators() {
    memset(s_accum_src, 0, sizeof(s_accum_src));
    memset(s_accum_ret, 0, sizeof(s_accum_ret));
    s_accum_count = 0;
}


// -----------------------------------------------------------------------------
// linearToDbfs(linear)
// Converts a linear FFT magnitude (0.0–1.0) to dBFS.
// Returns –120.0 for zero or sub-zero inputs.
// Defined here (rather than depending on audio_engine) so audio_capture
// is self-contained and does not create a circular dependency.
// -----------------------------------------------------------------------------
static inline float linearToDbfs(float linear) {
    if (linear <= 0.0f) return -120.0f;
    return max(20.0f * log10f(linear), -120.0f);
}


// =============================================================================
// PUBLIC FUNCTION IMPLEMENTATIONS
// =============================================================================


// -----------------------------------------------------------------------------
// audioCap_init()
// -----------------------------------------------------------------------------
bool audioCap_init() {
// Allocate Audio Library DMA memory.
// Two AudioRecordQueue objects now share this pool.
// Each queue holds up to 53 blocks; with both queues armed simultaneously
// that is 106 blocks × 128 samples × 2 bytes (int16) ≈ 27 KB peak.
// We need at least 106 + graph pipeline headroom (~16) = 122 blocks.
// Rounding up to 128 blocks (32,768 bytes) gives safe headroom.
// [Each block = 128 samples × 2 bytes (int16) = 256 bytes;   128 × 256 = 32 KB]
// If audio drop-outs occur (fft.available() returns false unexpectedly),
// increase this value. The Teensy 4.1 has 1 MB DTCM; 128 blocks is fine.
AudioMemory(128);


// Start I2C bus for SGTL5000 register writes
Wire.begin();


// Verify codec responds on I2C.
// Failure here almost always means the Audio Shield is not fully seated.
if (!s_sgtl5000.enable()) {
    Serial.println("[AudioCapture] ERROR: SGTL5000 not found on I2C.");
    Serial.println("[AudioCapture] Check that the Audio Shield is fully seated.");
    return false;
}


// Select line input (not microphone).
// The OPA1642 buffer drives the line input; the on-board microphone
// is not used in this design.
s_sgtl5000.inputSelect(AUDIO_INPUT_LINEIN);


// Set initial PGA gain.
// *** CALIBRATION REQUIRED — see SGTL5000_LINE_IN_LEVEL note in config.h ***
// This value must be verified with the actual OPA1642 buffer hardware.
// Target: peaks at –6 to –12 dBFS during normal signal levels.
s_sgtl5000.lineInLevel(SGTL5000_LINE_IN_LEVEL);


// Set headphone monitoring level (development passthrough — see config.h)
s_sgtl5000.volume(SGTL5000_HEADPHONE_VOL);


#if ENABLE_SGTL_REGISTER_DUMP
// -----------------------------------------------------------------------------
// Read-only codec state dump (TODO-43). No writes. See config.h for rationale.
// Registers per NXP SGTL5000 datasheet Rev. 5.
// -----------------------------------------------------------------------------
{
    const uint16_t id   = (uint16_t)s_sgtl5000.read(0x0000);  // CHIP_ID
    const uint16_t adcc = (uint16_t)s_sgtl5000.read(0x0020);  // CHIP_ANA_ADC_CTRL
    const uint16_t anac = (uint16_t)s_sgtl5000.read(0x0024);  // CHIP_ANA_CTRL
    const uint16_t anap = (uint16_t)s_sgtl5000.read(0x0030);  // CHIP_ANA_POWER
    const uint16_t digp = (uint16_t)s_sgtl5000.read(0x0002);  // CHIP_DIG_POWER
    const uint16_t refc = (uint16_t)s_sgtl5000.read(0x0028);  // CHIP_REF_CTRL
    const uint16_t lreg = (uint16_t)s_sgtl5000.read(0x0026);  // CHIP_LINREG_CTRL
    const uint16_t clkc = (uint16_t)s_sgtl5000.read(0x0004);  // CHIP_CLK_CTRL

    Serial.println("[SGTL] ===== SGTL5000 REGISTER DUMP (read-only) =====");
    Serial.printf ("[SGTL] REQUESTED  input        = AUDIO_INPUT_LINEIN\n");
    Serial.printf ("[SGTL] REQUESTED  lineInLevel  = %d\n", SGTL5000_LINE_IN_LEVEL);
    Serial.println("[SGTL] ---------------- actual register state ----------------");

    Serial.printf ("[SGTL] CHIP_ID           0x%04X\n", id);
    Serial.printf ("[SGTL]   PARTID          0x%02X   (0xA0 = SGTL5000)\n", (id >> 8) & 0xFF);
    Serial.printf ("[SGTL]   REVID           0x%02X\n", id & 0xFF);
    Serial.println("[SGTL]   NOTE: codec silicon ID/revision. NOT the shield PCB revision.");

    Serial.printf ("[SGTL] CHIP_ANA_ADC_CTRL 0x%04X\n", adcc);
    Serial.printf ("[SGTL]   ADC_VOL_LEFT    %2u     (lineInLevel; 0=least gain, 15=most)\n", adcc & 0x0F);
    Serial.printf ("[SGTL]   ADC_VOL_RIGHT   %2u\n", (adcc >> 4) & 0x0F);
    Serial.printf ("[SGTL]   ADC_VOL_M6DB    %u      (1 = range reduced by 6.0 dB)\n", (adcc >> 8) & 0x01);

    Serial.printf ("[SGTL] CHIP_ANA_CTRL     0x%04X\n", anac);
    Serial.printf ("[SGTL]   SELECT_ADC      %u      (0 = MIC, 1 = LINEIN)\n", (anac >> 2) & 0x01);
    Serial.printf ("[SGTL]   MUTE_ADC        %u\n", anac & 0x01);
    Serial.printf ("[SGTL]   SELECT_HP       %u      (0 = DAC, 1 = LINEIN)\n", (anac >> 6) & 0x01);
    Serial.printf ("[SGTL]   MUTE_HP         %u\n", (anac >> 4) & 0x01);
    Serial.printf ("[SGTL]   MUTE_LO         %u\n", (anac >> 8) & 0x01);

    Serial.printf ("[SGTL] CHIP_ANA_POWER    0x%04X\n", anap);
    Serial.printf ("[SGTL]   ADC_POWERUP     %u\n", (anap >> 1) & 0x01);
    Serial.printf ("[SGTL]   LINEOUT_POWERUP %u\n", (anap >> 0) & 0x01);
    Serial.printf ("[SGTL]   REFTOP_POWERUP  %u\n", (anap >> 5) & 0x01);
    Serial.printf ("[SGTL]   HEADPHONE_PWRUP %u\n", (anap >> 4) & 0x01);
    Serial.printf ("[SGTL]   VAG_POWERUP     %u\n", (anap >> 7) & 0x01);
    Serial.printf ("[SGTL]   VCOAMP_POWERUP  %u\n", (anap >> 8) & 0x01);
    Serial.printf ("[SGTL]   ADC_MONO        %u      (1 = stereo ADC)\n", (anap >> 6) & 0x01);
    Serial.printf ("[SGTL]   DAC_MONO        %u      (1 = stereo DAC)\n", (anap >> 14) & 0x01);

    Serial.printf ("[SGTL] CHIP_DIG_POWER    (0x0002) = 0x%04X\n", digp);
    Serial.printf ("[SGTL]   ADC_POWERUP     %u\n", (digp >> 5) & 0x01);
    Serial.printf ("[SGTL]   DAC_POWERUP     %u\n", (digp >> 4) & 0x01);
    Serial.printf ("[SGTL]   DAP_POWERUP     %u\n", (digp >> 6) & 0x01);
    Serial.printf ("[SGTL]   I2S_OUT_POWERUP %u\n", (digp >> 1) & 0x01);
    Serial.printf ("[SGTL]   I2S_IN_POWERUP  %u\n", (digp >> 0) & 0x01);

    // CHIP_REF_CTRL — VAG_VAL is the ADC/DAC voltage reference. NXP states that
    // changing it scales the ADC output signal, so it sits directly in the
    // volts-to-counts relationship under investigation (TODO-43). Programmable
    // range is only 0.800-1.575 V (< 6 dB end to end), so it cannot by itself
    // account for a ~19 dB discrepancy.
    Serial.printf ("[SGTL] CHIP_REF_CTRL     (0x0028) = 0x%04X\n", refc);
    Serial.printf ("[SGTL]   VAG_VAL         %2u     = %.3f V  (0.800 V + 25 mV/step, max 1.575 V)\n",
                      (refc >> 4) & 0x1F,
                      0.800f + 0.025f * (float)((refc >> 4) & 0x1F));
    Serial.printf ("[SGTL]   BIAS_CTRL       %u      (0 = nominal; raw code, not decoded)\n", (refc >> 1) & 0x07);
    Serial.printf ("[SGTL]   SMALL_POP       %u\n", refc & 0x01);

    // NOTE: CHIP_LINREG_CTRL is at ADDRESS 0x0026. Do not confuse that with the
    // VALUE 0x0026 that CHIP_ANA_CTRL (address 0x0024) happened to read back on
    // 2026-09-13. Coincidence, not a conflict.
    Serial.printf ("[SGTL] CHIP_LINREG_CTRL  (0x0026) = 0x%04X\n", lreg);
    Serial.printf ("[SGTL]   D_PROGRAMMING   %2u     (VDDD regulator, 50 mV/step: 0x0=1.60 V .. 0xF=0.85 V)\n", lreg & 0x0F);
    Serial.printf ("[SGTL]   VDDC_ASSN_OVRD  %u      (0 = automatic charge-pump source)\n", (lreg >> 5) & 0x01);
    Serial.printf ("[SGTL]   VDDC_MAN_ASSN   %u      (0 = VDDA, 1 = VDDIO; only if OVRD = 1)\n", (lreg >> 6) & 0x01);

    Serial.printf ("[SGTL] CHIP_CLK_CTRL     (0x0004) = 0x%04X\n", clkc);
    // Field order verified against control_sgtl5000.cpp, which writes
    // CHIP_CLK_CTRL = 0x0004 | 0x03 for "use PLL". The PLL code is 0x3 in
    // MCLK_FREQ, so MCLK_FREQ is bits 1:0 and SYS_FS is bits 3:2 -- the
    // opposite of this decoder's first version. 0x0004 therefore reads as
    // 44.1 kHz / 256*Fs, matching the library's own comment.
    Serial.printf ("[SGTL]   SYS_FS          %u      (0=32k 1=44.1k 2=48k 3=96k)\n", (clkc >> 2) & 0x03);
    Serial.printf ("[SGTL]   MCLK_FREQ       %u      (0=256Fs 1=384Fs 2=512Fs 3=PLL)\n", clkc & 0x03);
    Serial.printf ("[SGTL]   RATE_MODE       %u      (0=SYS_FS 1=1/2 2=1/4 3=1/6)\n", (clkc >> 4) & 0x03);

    Serial.println("[SGTL] ================ end register dump ================");
}
#endif


// Apply Hann windowing to both FFT objects.
// The Hann window tapers the time-domain frame to zero at both edges,
// dramatically reducing spectral leakage. Without windowing, a tone
// between two bin centres smears energy across many adjacent bins.
// With Hann, energy is confined to ~2–3 bins around the true frequency.
// This matters for the live spectrum display and for the EMA TF in audio_engine.
// (The precision measurement path uses CMSIS-DSP with its own windowing.)
s_fft_src.windowFunction(AudioWindowHanning1024);
s_fft_ret.windowFunction(AudioWindowHanning1024);


// Apply default signal route from config.h
     s_source_ch = SOURCE_NODE_PHYSICAL_CH;
     s_return_ch = RETURN_NODE_PHYSICAL_CH;
     applyRoute(s_source_ch, s_return_ch);


     // Initialise all consumer slots to a known state.
     // fft arrays are zeroed so a consumer that reads before the first block
     // gets silence rather than garbage.
     const uint8_t n_consumers = static_cast<uint8_t>(AudioConsumer::COUNT);
     for (uint8_t i = 0; i < n_consumers; i++) {
         memset(&s_blocks[i], 0, sizeof(AudioRawBlock));
         s_blocks[i].source_node_ch = s_source_ch;
         s_blocks[i].return_node_ch = s_return_ch;
         s_block_fresh[i] = false;
     }


     // Clear accumulators and all event latches
     clearAccumulators();
     s_output_block_number       = 0;      // display counter only
     s_route_changed_pending     = false;
     s_last_route_changed_block = 0;
     s_clip_source_pending       = false;
     s_clip_return_pending       = false;
     s_initialised               = true;


     Serial.println("[AudioCapture] SGTL5000 initialised. Acquisition active.");
     Serial.printf ("[AudioCapture] Route: SOURCE_NODE=ch%d, RETURN_NODE=ch%d\n",
                     s_source_ch, s_return_ch);
     // CHANGED [todo-27]: these two lines were the surviving second copy of the
     // window-vs-hop error. The first printed "23.2 ms/frame" — a correct WINDOW
     // duration wearing a label that reads as a cadence — and the second then
     // multiplied that window by FFT_AVERAGE_COUNT, yielding "92.9 ms" against a
     // true block period of 46.4 ms. The firmware contradicted itself by 2×
     // within one boot sequence (see [Main] Block: expected 46.4 ms).
     //
     // Both quantities are now named explicitly so the distinction cannot be
     // lost again: the 23.2 ms window is real and useful, it simply is not the
     // rate at which results arrive.
     Serial.printf ("[AudioCapture] FFT: %d bins, %.2f Hz/bin, "
                     "%.1f ms/window, %.1f ms hop (50%% overlap)\n",
                     FFT_BINS,
                     (float)SAMPLE_RATE / FFT_SIZE,
                     1000.0f * FFT_SIZE        / SAMPLE_RATE,
                     1000.0f * FFT_HOP_SAMPLES / SAMPLE_RATE);
     Serial.printf ("[AudioCapture] Block period: %d results × %.1f ms hop = %.1f ms\n",
                     FFT_AVERAGE_COUNT,
                     1000.0f * FFT_HOP_SAMPLES / SAMPLE_RATE,
                     1000.0f * FFT_AVERAGE_COUNT * FFT_HOP_SAMPLES / SAMPLE_RATE);


     return true;
}


// -----------------------------------------------------------------------------
// audioCap_update()
//
// FIXED [block-ready-semantics]: The previous implementation returned
// BLOCK_READY whenever CONSUMER_LIVE's freshness flag was set, meaning it
// would repeat BLOCK_READY every call until audio_engine consumed its slot —
// even though no new block was posted in those subsequent calls. This made
// event semantics muddy: the event should mean "a new block was posted THIS
// call," not "a consumer still has unread data."
//
// The fix: a local bool posted_new_block tracks whether a block was actually
// posted in this specific call. BLOCK_READY is returned only when that flag
// is true. Consumer freshness (s_block_fresh[]) remains a separate concern:
// it answers "does this consumer still have unread data?" (audioCap_isBlockFresh).
// The event answers "what happened this iteration?" (audioCap_update return).
//
// This separation means:
//    audioCap_isBlockFresh(consumer) → consumer-side state (persists until consumed)
//    BLOCK_READY event                 → call-site event (true exactly once per block)
//
// STATE MACHINE (implicit, driven by s_accum_count):
//    Most calls: accumulate one FFT frame if available. Return clip/route/NONE.
//    When FFT_AVERAGE_COUNT frames accumulated: post block, set posted_new_block.
//
// EVENT PRIORITY ORDER (highest first):
//    CLIP_SOURCE or CLIP_RETURN — overload must never be silently dropped
//    ROUTE_CHANGED              — invalidates in-progress precision captures
//    BLOCK_READY                — a new block was posted THIS call
//    NONE                       — nothing happened this iteration
//
// Only one event per call. Clip and route events are latched until returned.
// BLOCK_READY is NOT latched — it is emitted once, in the call where posting
// occurred. If a higher-priority event also occurred, it takes precedence and
// BLOCK_READY is effectively lost. This is acceptable: consumers use
// audioCap_isBlockFresh() to check for unread data regardless of whether
// they missed a BLOCK_READY event.
// -----------------------------------------------------------------------------
AudioCaptureEvent audioCap_update() {


     if (!s_initialised) return AudioCaptureEvent::NONE;


     // =========================================================================
     // TEMPORARY DIAGNOSTIC — one-shot raw sample dump (2026-09-05, TODO-26)
     // -------------------------------------------------------------------------
     // Prints 32 consecutive int16 samples from each node, once, then disarms.
     // Purpose: SOURCE and RETURN both read +0.0 dBFS with genuinely full-scale
     // samples reaching the analyzers, while clocks, DOUT and continuity all
     // measure healthy. Looking at the actual sample sequence distinguishes the
     // remaining hypotheses; a level meter cannot.
     // Read the SEQUENCE, not just the extremes — a real 1 kHz tone at 44.1 kHz
     // moves smoothly over ~44 samples per cycle.
     // REMOVE THIS BLOCK once the question is answered.
     // =========================================================================
     // Periodic dump: arm -> wait for both queues -> print 32+32 -> disarm.
     // One dump per 5 s. Periodic rather than one-shot because a startup dump
     // cannot be observed: the Teensy discards serial output before a USB host
     // attaches, and pressing reset re-enumerates the device, tearing down any
     // already-open connection.
     // Read the SEQUENCE, not just the extremes — a real 1 kHz tone at 44.1 kHz
     // moves smoothly over ~44 samples per cycle.
     if (!s_raw_armed) {
         if ((int32_t)(millis() - s_raw_next_ms) >= 0) {
             // TEMPORARY DIAGNOSTIC (2026-09-07) — Audio Library block-pool
             // telemetry. Printed at ARM time so it appears unconditionally every
             // 5 s, even if the queues never fill. Tests whether the once-observed
             // hang at uptime ~2370 s was resource exhaustion: a climbing "max"
             // would show the 128-block pool filling. AudioMemoryUsage() and
             // AudioMemoryUsageMax() are plain accessors — they touch nothing in
             // the audio path. Lives here rather than in the .ino because
             // audio_capture owns the Audio Library objects and the .ino must not
             // reference them (see the module boundary note at the top of
             // audio_capture.h). Pool size is the literal 128 passed to
             // AudioMemory() below; if that changes this line only reads stale.
             Serial.printf("[Main] AudioMemory: %u in use, %u max, of 128 allocated\n",
                              (unsigned)AudioMemoryUsage(),
                              (unsigned)AudioMemoryUsageMax());

             audioCap_beginRawCapture();   // clears, then begins => fresh samples
             s_raw_armed = true;
         }
     } else {
         const int src_avail = s_queue_src.available();
         const int ret_avail = s_queue_ret.available();

         if (src_avail >= 1 && ret_avail >= 1) {
             const int16_t* src_blk = s_queue_src.readBuffer();
             const int16_t* ret_blk = s_queue_ret.readBuffer();

             if (src_blk != nullptr && ret_blk != nullptr) {
                 Serial.printf("[RAWDUMP] 32 int16 per node (src_avail=%d ret_avail=%d)\n",
                                  src_avail, ret_avail);
                 Serial.print("[RAWDUMP] SOURCE:");
                 for (int i = 0; i < 32; i++) { Serial.print(' '); Serial.print(src_blk[i]); }
                 Serial.println();
                 Serial.print("[RAWDUMP] RETURN:");
                 for (int i = 0; i < 32; i++) { Serial.print(' '); Serial.print(ret_blk[i]); }
                 Serial.println();
             } else {
                 Serial.printf("[RAWDUMP] NULL BUFFER despite available: src=%s ret=%s\n",
                                  src_blk ? "ok" : "NULL", ret_blk ? "ok" : "NULL");
             }

             // Free exactly what was read, then disarm immediately so the queues
             // return to their normal idle state (only measurement_engine arms
             // them) and cannot hoard AudioMemory between dumps.
             if (src_blk != nullptr) s_queue_src.freeBuffer();
             if (ret_blk != nullptr) s_queue_ret.freeBuffer();
             audioCap_endRawCapture();

             s_raw_armed   = false;
             s_raw_next_ms = millis() + 5000;
         }
     }
     // ===================== END TEMPORARY DIAGNOSTIC ==========================


     // FIXED [block-ready-semantics]: Local flag — true only if a new block
     // is posted during THIS call. Drives BLOCK_READY return below.
     bool posted_new_block = false;


     // --- Accumulate one raw FFT frame if available ---
     // Both FFT objects share the same I2S clock, so they complete together.
     // We require both to be available before consuming either, ensuring
     // source and return data always come from the same time window.
     //
     // RACE NOTE [fft-output-buffer]:
     //   AudioAnalyzeFFT1024::available() clears the readiness flag; read(bin)
     //   returns the bin from a shared output[] buffer that the audio update
     //   chain rewrites when a new FFT completes (every ~23 ms at FFT_SIZE=1024).
     //   The 512-bin read loop below completes in microseconds on a 600 MHz
     //   M7, so under normal load no new FFT lands mid-loop. Under heavy
     //   contention (SPI display draw, SD flush, ISR latency) the audio
     //   update could race the read and mix two FFT frames' bins. Downstream
     //   consumers (audio_engine, measurement_engine) guard against the
     //   resulting NaN / outlier bins via isfinite() checks and the ret/src
     //   outlier discard in audio_engine.cpp. A library-level fix requires
     //   modifying AudioAnalyzeFFT1024 to expose an atomic-snapshot API.
     if (s_fft_src.available() && s_fft_ret.available()) {


         // Accumulate raw magnitude per bin.
         // fft.read(k) returns linear magnitude [0.0, 1.0] and resets the
         // internal available flag — it must be called exactly once per frame.
for (int k = 0; k < FFT_BINS; k++) {
    s_accum_src[k] += s_fft_src.read(k);
    s_accum_ret[k] += s_fft_ret.read(k);
}
s_accum_count++;


// --- Completed averaging block? ---
if (s_accum_count >= FFT_AVERAGE_COUNT) {


    // Compute averaged magnitudes and peak levels.
    const double inv = 1.0 / (double)FFT_AVERAGE_COUNT;


    // Read peaks over the full averaging window.
    // AudioAnalyzePeak.read() returns peak since last call, then resets.
    // Call BEFORE the block is posted so peak_*_dbfs reflects this window.
    //
    // TODO-28 (2026-09-05): read() MUST be guarded by available(). With no
    // audio since the previous read, the analyzer's reset values survive and
    // abs(-32768)/32767 = 1.00003 is returned — exactly full scale, exactly
    // +0.0 dBFS. That is indistinguishable from genuine saturation and latches
    // a false clip every window. Never read an unavailable analyzer; carry the
    // last valid value forward instead, and never derive clipping from one.
    const bool src_peak_valid = s_peak_src.available();
    const bool ret_peak_valid = s_peak_ret.available();


    // Last known-good peak/clip state, carried across unavailable windows.
    // Initialised to linearToDbfs()'s existing silence floor only because a
    // value is required before the first valid read — never written on an
    // unavailable window, so starvation cannot masquerade as silence.
    static float s_last_peak_src_dbfs = -120.0f;
    static float s_last_peak_ret_dbfs = -120.0f;
    static bool  s_last_src_clipping  = false;
    static bool  s_last_ret_clipping  = false;


    if (src_peak_valid) {
        s_last_peak_src_dbfs = linearToDbfs(s_peak_src.read());
        s_last_src_clipping  = (s_last_peak_src_dbfs >= CLIP_THRESHOLD_DBFS);
    } else {
        Serial.println("[audioCap] peak unavailable: SOURCE");
    }
    if (ret_peak_valid) {
        s_last_peak_ret_dbfs = linearToDbfs(s_peak_ret.read());
        s_last_ret_clipping  = (s_last_peak_ret_dbfs >= CLIP_THRESHOLD_DBFS);
    } else {
        Serial.println("[audioCap] peak unavailable: RETURN");
    }


    const float peak_src_dbfs = s_last_peak_src_dbfs;
    const float peak_ret_dbfs = s_last_peak_ret_dbfs;


    // Latch clipping events BEFORE posting block.
    // This ensures the main loop can react to clipping in the same
    // iteration it receives the block, not one iteration later.
    // Latched only from a peak that was actually available this window.
    if (src_peak_valid && s_last_src_clipping) s_clip_source_pending = true;
    if (ret_peak_valid && s_last_ret_clipping) s_clip_return_pending      = true;


    // Build the block once; copy into all consumer slots.
    // Single construction guarantees both consumers receive bitwise-identical
    // data for the same block counter value — the core of the
    // "one capture, two views" guarantee.
    AudioRawBlock new_block;
    // FIX [canonical-timebase]: Use the 128-sample block counter estimate,
    // not the averaged output-block counter.
    new_block.audio_block_counter = audioBlockCounterFromMicros();
    new_block.timestamp_ms         = millis();      // advisory only — use block_counter
    new_block.source_node_ch       = s_source_ch;
    new_block.return_node_ch       = s_return_ch;
    new_block.frames_averaged      = (uint8_t)s_accum_count;
    new_block.peak_source_dbfs     = peak_src_dbfs;
    new_block.peak_return_dbfs     = peak_ret_dbfs;
    // Carried with their peak values so each block stays self-consistent —
    // never re-derived from a peak that was unavailable this window.
    new_block.source_clipping      = s_last_src_clipping;
    new_block.return_clipping      = s_last_ret_clipping;


    for (int k = 0; k < FFT_BINS; k++) {
        new_block.fft_source[k] = (float)(s_accum_src[k] * inv);
                new_block.fft_return[k] = (float)(s_accum_ret[k] * inv);
            }


            // Post to all consumer slots
            const uint8_t n = static_cast<uint8_t>(AudioConsumer::COUNT);
            for (uint8_t i = 0; i < n; i++) {
                s_blocks[i]        = new_block;
                s_block_fresh[i] = true;
            }


            s_output_block_number++;     // display-only counter; NOT the timing primitive
            clearAccumulators();


            // FIXED [block-ready-semantics]: Mark that a block was posted
            // in THIS call. This flag — not consumer freshness — drives the
            // BLOCK_READY event return below.
            posted_new_block = true;
        }
    }


    // --- Return highest-priority pending event ---
    if (s_clip_source_pending) {
        s_clip_source_pending = false;
        return AudioCaptureEvent::CLIP_SOURCE;
    }
    if (s_clip_return_pending) {
        s_clip_return_pending = false;
        return AudioCaptureEvent::CLIP_RETURN;
    }
    if (s_route_changed_pending) {
        s_route_changed_pending = false;
        return AudioCaptureEvent::ROUTE_CHANGED;
    }


    // FIXED [block-ready-semantics]: Return BLOCK_READY only when a new
    // block was actually posted in THIS call — not when a consumer still
    // has unread data from a previous call.
    if (posted_new_block) {
        return AudioCaptureEvent::BLOCK_READY;
    }


    return AudioCaptureEvent::NONE;
}


// -----------------------------------------------------------------------------
// audioCap_getBlock(consumer)
// -----------------------------------------------------------------------------
const AudioRawBlock& audioCap_getBlock(AudioConsumer consumer) {
     return s_blocks[static_cast<uint8_t>(consumer)];
}


// -----------------------------------------------------------------------------
// audioCap_isBlockFresh(consumer)
// -----------------------------------------------------------------------------
bool audioCap_isBlockFresh(AudioConsumer consumer) {
     return s_block_fresh[static_cast<uint8_t>(consumer)];
}


// -----------------------------------------------------------------------------
// audioCap_markConsumed(consumer)
// -----------------------------------------------------------------------------
void audioCap_markConsumed(AudioConsumer consumer) {
     s_block_fresh[static_cast<uint8_t>(consumer)] = false;
}


// -----------------------------------------------------------------------------
// audioCap_getBlockCounter()
// Returns the micros()-derived 128-sample block counter. This has the same
// units as the Teensy Audio Library processing block (~2.9 ms at 44,100 Hz)
// and is the canonical timing primitive for the entire system.
//
// For signal_generator timing: call this, add your margin (≥ 2), pass the
// result to signalGen_startAtBlock(). The generator will start on that block.
// -----------------------------------------------------------------------------
uint32_t audioCap_getBlockCounter() {
     return audioBlockCounterFromMicros();
}


// -----------------------------------------------------------------------------
// audioCap_notifyRouteChanged(source_ch, return_ch)
//
// Called by audioEngine_setRoute() when the signal route changes.
// audio_capture owns the mixer hardware, so it is this function —
// not audio_engine — that actually applies the new mixer gains.
//
// This function:
//    1. Applies the new mixer gains via the local applyRoute() helper,
//       routing the specified physical channels to SOURCE_NODE and RETURN_NODE.
//    2. Records the block counter at the time of the change.
//    3. Updates s_source_ch and s_return_ch so future AudioRawBlock snapshots
//       carry the correct channel assignments.
//    4. Clears the accumulator — frames accumulated under the old route are
//       invalid. A partial block mixing frames from different channel bindings
//       is meaningless and must be discarded.
//    5. Latches s_route_changed_pending so the next audioCap_update() call
//       returns AudioCaptureEvent::ROUTE_CHANGED.
// -----------------------------------------------------------------------------
void audioCap_notifyRouteChanged(uint8_t source_ch, uint8_t return_ch) {
     // Update channel assignments
     s_source_ch = source_ch % 2;
     s_return_ch = return_ch % 2;


     // Apply new mixer gains — audio_capture owns the mixers
     applyRoute(s_source_ch, s_return_ch);


     // Restore generator monitor gain on slot 2.
     // applyRoute() sets slot 2 to 0.0f as a side-effect of clearing all
     // unused slots. signal_generator.cpp wires its output to slot 2 and
     // expects it to remain at 1.0f. Restoring here makes the monitor
     // survive route changes without requiring an explicit caller action.
     s_mixer_ret.gain(2, 1.0f);


     // Record the block counter at which the change occurred
     s_last_route_changed_block = audioBlockCounterFromMicros();


     // Discard any partial accumulation — frames before and after the route
     // change cannot be averaged together.
     clearAccumulators();


     // Latch the event for return on next audioCap_update()
     s_route_changed_pending = true;


     Serial.printf("[AudioCapture] Route change notified at block %lu: "
                   "SOURCE_NODE=ch%d, RETURN_NODE=ch%d\n",
                   s_last_route_changed_block, s_source_ch, s_return_ch);
}


// -----------------------------------------------------------------------------
// audioCap_getLastRouteChangedBlock()
// -----------------------------------------------------------------------------
uint32_t audioCap_getLastRouteChangedBlock() {
     return s_last_route_changed_block;
}


// -----------------------------------------------------------------------------
// audioCap_setInputGain(gain_db)
//
// Adjusts SGTL5000 line-in PGA gain. Each step is approximately 1.5 dB.
// Range: 0–15 (SGTL5000 lineInLevel argument).
//
// A gain change has the same effect on precision measurement validity as a
// route change — the accumulated frames before the gain change were captured
// at a different level and cannot be averaged with frames after the change.
// Therefore, this function:
//    1. Applies the new gain to the codec.
//    2. Clears the accumulator.
//    3. Latches a ROUTE_CHANGED event (reusing the same event type because
//       the effect on downstream consumers is identical).
//
// The "route changed" event name is slightly misleading for a pure gain change,
// but the consequence is identical: measurement_engine must abort any capture
// in progress. Using the same event avoids adding a new GAIN_CHANGED event
// that would require all consumers to handle both identically.
// -----------------------------------------------------------------------------
void audioCap_setInputGain(float gain_db) {
     // FIX [nan-gain]: explicit isfinite check before any arithmetic. NaN slips
     // past the constrain() macro (NaN comparisons unordered) and (int)NaN is
     // UB. Without this guard, a NaN argument would write an arbitrary value to
     // the SGTL5000 PGA register.
     if (!isfinite(gain_db)) {
         Serial.println("[AudioCapture] setInputGain() ignored: non-finite gain_db");
         return;
     }
     int level = (int)constrain(gain_db / 1.5f, 0.0f, 15.0f);

     // FIX [no-op-gain]: previously every call latched ROUTE_CHANGED, which
     // aborted in-progress measurements even when the level did not change.
     // No-op when the target equals the current level.
     if (level == s_current_line_in_level) {
         Serial.printf("[AudioCapture] setInputGain(%.1f) no-op: already at level %d\n",
                       gain_db, level);
         return;
     }

     s_sgtl5000.lineInLevel(level);
     s_current_line_in_level = level;


     // Record change and discard partial accumulation (same as route change)
     s_last_route_changed_block = audioBlockCounterFromMicros();
     clearAccumulators();
     s_route_changed_pending = true;


     Serial.printf("[AudioCapture] Input gain: level %d (~%.1f dB). "
                   "Accumulator cleared, ROUTE_CHANGED event latched.\n",
                   level, gain_db);
}


// =============================================================================
// RAW SAMPLE CAPTURE API — Complex FFT measurement path
// =============================================================================


// -----------------------------------------------------------------------------
// audioCap_beginRawCapture()
// Arms both AudioRecordQueue objects. From this point forward, every 128-sample
// Audio Library block is enqueued. Call immediately before starting a CAPTURE
// state measurement to ensure no samples are missed.
//
// The queues fill silently in the Audio Library interrupt context.
// measurement_engine drains them via audioCap_getRawSamples().
//
// Call audioCap_endRawCapture() when capture is complete to stop queueing
// and free the buffered blocks.
// -----------------------------------------------------------------------------
void audioCap_beginRawCapture() {
     // Clear any stale blocks from a previous capture before arming.
     // This prevents old samples from appearing at the front of a new capture.
     s_queue_src.clear();
     s_queue_ret.clear();
     s_queue_src.begin();
     s_queue_ret.begin();
}


// -----------------------------------------------------------------------------
// audioCap_rawSamplesAvailable()
// Returns the number of complete 128-sample blocks currently available
// in the source queue. Use this to know how many times getRawSamples()
// can be called before it would block.
//
// Both queues fill at the same rate (same I2S clock), so checking either
// one is sufficient. We return the source queue count as the authoritative value.
// -----------------------------------------------------------------------------
int audioCap_rawSamplesAvailable() {
     return s_queue_src.available();
}


// -----------------------------------------------------------------------------
// audioCap_getRawSamples(src_out, ret_out, n_blocks)
// Drains exactly n_blocks × 128 samples from each queue into the caller's
// output buffers. src_out and ret_out must each hold n_blocks × 128 floats.
//
// Samples are converted from int16 (Audio Library native format, range
// –32768 to +32767) to float32 (range –1.0 to +1.0) for CMSIS-DSP.
//
// Returns true if n_blocks were successfully drained from both queues.
// Returns false if insufficient blocks, or if a rare ISR-race nullptr
// was encountered. On false, both queues are fully flushed — the
// next call starts from a fresh contiguous window (all-or-none).
//
// measurement_engine calls this to fill its FFT_SIZE-sample input buffer:
//       audioCap_getRawSamples(src_buf, ret_buf, FFT_SIZE / AUDIO_BLOCK_SAMPLES)
// which drains exactly FFT_SIZE/128 = 8 blocks per call.
// -----------------------------------------------------------------------------
bool audioCap_getRawSamples(float* src_out, float* ret_out, int n_blocks) {
     // Check availability before consuming anything
     if (s_queue_src.available() < n_blocks ||
            s_queue_ret.available() < n_blocks) {
            return false;
     }


     const float scale = 1.0f / 32768.0f;      // int16 → float32 normalisation
    for (int b = 0; b < n_blocks; b++) {
        // readBuffer() returns a pointer to the next 128-sample int16 block.
        // freeBuffer() must be called after reading to return it to the pool.
        const int16_t* src_blk = s_queue_src.readBuffer();
        const int16_t* ret_blk = s_queue_ret.readBuffer();


        if (!src_blk || !ret_blk) {
            // Unexpected nullptr despite the available() pre-check — the ISR
            // ran between available() and readBuffer() and consumed the block.
            //
            // FIX [all-or-none contract]: Free the nullptr-side immediately,
            // then drain and discard all remaining blocks from both queues.
            // This leaves the queues empty so the caller's next call starts
            // with a fresh, contiguous window — no partial-frame gap.
            // The wasted blocks (at most n_blocks-1 per occurrence) are
            // preferable to a mid-frame gap in the accumulation.
            if (src_blk) s_queue_src.freeBuffer();
            if (ret_blk) s_queue_ret.freeBuffer();
            // Drain remainder of both queues
            while (s_queue_src.available() > 0) {
                   const int16_t* blk = s_queue_src.readBuffer();
                   if (blk) s_queue_src.freeBuffer();
            }
            while (s_queue_ret.available() > 0) {
                   const int16_t* blk = s_queue_ret.readBuffer();
                   if (blk) s_queue_ret.freeBuffer();
            }
            return false;
        }


        float* src_dest = src_out + b * AUDIO_BLOCK_SAMPLES;
        float* ret_dest = ret_out + b * AUDIO_BLOCK_SAMPLES;


        for (int s = 0; s < AUDIO_BLOCK_SAMPLES; s++) {
            src_dest[s] = (float)src_blk[s] * scale;
            ret_dest[s] = (float)ret_blk[s] * scale;
        }


        s_queue_src.freeBuffer();
        s_queue_ret.freeBuffer();
    }
    return true;
}


// -----------------------------------------------------------------------------
// audioCap_endRawCapture()
// Disarms the AudioRecordQueue objects and discards any buffered blocks.
// Call when the CAPTURE state ends (completion, abort, or cancel).
// Failing to call this leaves the queues armed and filling memory indefinitely.
// -----------------------------------------------------------------------------
void audioCap_endRawCapture() {
    s_queue_src.end();
    s_queue_ret.end();
    s_queue_src.clear();
    s_queue_ret.clear();
}
