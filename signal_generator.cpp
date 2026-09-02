// =============================================================================
// signal_generator.cpp   —   Guitar Rig Analyzer   v0.5.0
// =============================================================================
// Controlled stimulus generator with block-aligned start capability.
//
// GENERATOR STATUS
// -----------------
// The following are complete:
//   • Full GeneratorState machine (IDLE, ARMED, ACTIVE, MISSED)
//   • Block-aligned start mechanism via audioCap_getBlockCounter()
//   • DDS phase accumulator structure for sine and log-sweep
//   • Amplitude scaling and clamping
//   • signalGen_stop() safe from any context
//   • All public API functions
//   • Convenience factory functions
//
// GENERATOR OUTPUT WIRING
// -----------------------
// The generator is wired to the monitoring right channel (headphone R) via
// slot 2 of s_mixer_ret in audio_capture.cpp (slot 2 is routing-safe; slots 0 and
// 1 are owned by applyRoute() for physical channel selection). When the generator
// is active it can be heard on the right ear alongside RETURN_NODE passthrough.
// This makes the generator audible and measurable on the bench without needing
// signal_router.
//
// DUT INJECTION: The generated signal does not yet reach the physical RIG SEND
// jack. That path requires signal_router (hardware routing hardware not yet
// designed). Until then, use EXTERNAL stimulus for real rig measurements.
//
// Still stubbed:
//   • Pink noise 1/f IIR shaping (white noise works)
//   • signalGen_startNow() (uses startAtBlock instead)
//
// WHY AUDIO INJECTION IS STUBBED HERE
// ------------------------------------
// The generator output must eventually be injected into the signal path so
// that the rig receives a known stimulus and the analyzer captures both the
// source (what was sent) and return (what came back). The injection point
// depends on the final hardware design (RIG SEND output path). Until the
// signal routing hardware is defined and signal_router exists, we cannot wire
// the generator output into the audio graph without making assumptions about
// the jack routing that may change.
//
// The state machine, timing contract, and DDS logic are fully implemented and
// testable. Wiring the audio output is a separate, bounded task.
//
// BLOCK-ALIGNED START MECHANISM
// ------------------------------
// The canonical timebase is audioCap_getBlockCounter() from audio_capture.
// signalGen_startAtBlock(N) stores N as the pending start block.
// On each audioCap_update() → BLOCK_READY event in the main loop, the main
// loop calls signalGen_update() (below). When the current block counter
// reaches or passes the pending start block, signalGen_update() transitions
// ARMED → ACTIVE and records the actual start block.
//
// This achieves main-loop-level block alignment (within one block, ≈2.9 ms).
// For precision phase alignment (true interrupt-level), the Audio Library
// interrupt handler would need to be patched — this is a future enhancement.
// Main-loop alignment is sufficient for latency measurement and rig analysis.
//
// signalGen_update() IS NOT in the public header — it is called only by
// measurement_engine.cpp during the ARMED and ACTIVE states. It is forward-
// declared here and implemented below. measurement_engine includes this file
// via measurement_engine.cpp, not through the public header.
// =============================================================================


#include "signal_generator.h"
#include "audio_capture.h"      // For audioCap_getBlockCounter()
#include <Audio.h>
#include <math.h>


// =============================================================================
// AUDIO LIBRARY SYNTHESIS OBJECTS
// =============================================================================
// Synthesis objects are file-scope statics — signal_generator owns them.
// A local mixer blends the active source (sine or noise) and feeds into
// slot 2 of audio_capture's s_mixer_ret (routing-safe), which routes to headphone R.
// Slot 0 of s_mixer_ret carries the normal RETURN_NODE monitoring signal.


static AudioSynthWaveformSine s_sine_osc;       // DDS sine for INTERNAL_SINE
static AudioSynthNoiseWhite      s_noise_src;   // White noise source
static AudioMixer4               s_gen_mixer;   // Blends active source


// s_mixer_ret is declared in audio_capture.cpp (non-static for this reason)
extern AudioMixer4 s_mixer_ret;


// Wire: sine → gen_mixer slot 0, noise → gen_mixer slot 1
// Wire: gen_mixer → s_mixer_ret SLOT 2 (not slot 0 or 1 — applyRoute() owns
// those for I2S channel selection). Slot 2 is never touched by routing logic,
// so generator monitoring is independent of physical channel routing.
// applyRoute() sets slot 2 gain to 0.0f, which we override in signalGen_init().
static AudioConnection s_conn_sine_mix (s_sine_osc,           0, s_gen_mixer,     0);
static AudioConnection s_conn_noise_mix(s_noise_src, 0, s_gen_mixer,              1);
static AudioConnection s_conn_gen_mon        (s_gen_mixer, 0, s_mixer_ret,        2);   // slot 2 — routin


// =============================================================================
// MODULE-PRIVATE STATE
// =============================================================================


// Current generator state.
// FIX [volatile-state]: marked volatile because signalGen_stop() is documented
// ISR-safe — without volatile, the main loop reader can cache s_state in a
// register and miss a write made from interrupt context.
static volatile GeneratorState s_state = GeneratorState::IDLE;


// Active configuration (set by signalGen_configure)
static GeneratorConfig s_config;


// Block-aligned start state.
// volatile for the same reason as s_state — the values are read after the
// barrier-free transition out of ARMED.
static volatile uint32_t s_pending_start_block = 0;   // Block at which to start output
static volatile uint32_t s_actual_start_block  = 0;   // Block at which output actually began


// Maximum skew (in 128-sample blocks) tolerated between the target start block
// and the block on which signalGen_update() actually runs. The main loop can
// stall briefly (RA8875 SPI draw, SD flush, long Serial print); a single-block
// skew is normal and must not trip the MISSED detector. 8 blocks ≈ 23 ms — well
// inside one FFT frame, so the alignment guarantee is preserved.
#define SIGGEN_MAX_START_SKEW_BLOCKS    8u


// DDS state for sine and log-sweep
// Phase accumulator in double to prevent drift over long sweeps.
static double   s_dds_phase          = 0.0;          // Current phase (radians)
static double   s_dds_phase_inc      = 0.0;          // Phase increment per sample
static uint32_t s_sweep_samples_produced           = 0;
static uint32_t s_sweep_samples_total              = 0;


// Linear amplitude (0.0–1.0), derived from amplitude_dbfs at configure time
static float s_amplitude_linear = 0.0f;


// =============================================================================
// PRIVATE HELPERS
// =============================================================================


// Convert dBFS to linear amplitude (0.0–1.0).
// –6 dBFS → 0.501,     –12 dBFS → 0.251,     0 dBFS → 1.0
static inline float dbfsToLinear(float dbfs) {
    return powf(10.0f, dbfs / 20.0f);
}


// Clamp amplitude_dbfs to the safe range [–60, –3].
// Returns true if clamping was applied, false if value was in range.
// FIX [nan-amplitude]: dbfs == NaN is not caught by '>' or '<' comparisons
// (NaN compares unordered, both return false), so it would slip through to
// powf(10, NaN/20) which produces a NaN amplitude → AudioSynth*.amplitude(NaN)
// which is undefined. We replace NaN with a conservative default of –6 dBFS
// and report it as clamped.
static bool clampAmplitude(float& dbfs) {
    bool clamped = false;
    if (!isfinite(dbfs)) { dbfs = -6.0f; clamped = true; }
    if (dbfs > -3.0f)    { dbfs = -3.0f;  clamped = true; }
    if (dbfs < -60.0f)   { dbfs = -60.0f; clamped = true; }
    return clamped;
}
// Prepare DDS parameters from the current s_config.
// Called when transitioning ARMED → ACTIVE.
// Each case explicitly mutes the inactive source so that switching stimulus
// types within a session (e.g. INTERNAL_WHITE → INTERNAL_SINE) does not
// leave residual output from the previous type.
static void prepareDDS() {
    s_dds_phase = 0.0;


    switch (s_config.type) {


        case StimulusType::INTERNAL_SINE:
            // Phase increment per sample for the target frequency.
            s_dds_phase_inc = (2.0 * M_PI * s_config.sine_freq_hz) / SAMPLE_RATE;
            s_sine_osc.frequency(s_config.sine_freq_hz);
            s_sine_osc.amplitude(s_amplitude_linear);
            s_noise_src.amplitude(0.0f);     // mute noise path
            break;


        case StimulusType::INTERNAL_LOG_SWEEP:
            // Initial phase increment for the sweep start frequency.
            s_dds_phase_inc = (2.0 * M_PI * s_config.sweep_start_hz) / SAMPLE_RATE;
            s_sweep_samples_produced = 0;
            s_sweep_samples_total    = (uint32_t)(s_config.sweep_duration_s * SAMPLE_RATE);
            s_noise_src.amplitude(0.0f);     // mute noise path
            break;


        case StimulusType::INTERNAL_WHITE:
            s_noise_src.amplitude(s_amplitude_linear);
            s_sine_osc.amplitude(0.0f);      // mute sine path
            break;


        case StimulusType::INTERNAL_PINK:
            // White noise source — pink 1/f shaping IIR filter to be added
            s_noise_src.amplitude(s_amplitude_linear);
            s_sine_osc.amplitude(0.0f);      // mute sine path
            break;


        default:
            break;
    }
}


// =============================================================================
// PACKAGE-PRIVATE: signalGen_update()
// =============================================================================
// Called by measurement_engine on each main loop iteration while the
// generator is in ARMED or ACTIVE state. NOT declared in the public header —
// this is an internal coordination function between signal_generator and
// measurement_engine.
//
// In ARMED: checks whether the current block counter has reached the pending
//       start block. If so, transitions to ACTIVE and records the actual start block.
//       If the current counter has PASSED the pending block (missed window),
//       transitions to MISSED.
//
// In ACTIVE: for LOG_SWEEP, updates sweep sample count. Transitions to IDLE
//       when sweep is complete (measurement_engine detects this and closes capture).
//
// Returns true when state transitions to ACTIVE (signals measurement_engine
// that capture can now begin with timing confidence).
// Returns false in all other cases.
// -----------------------------------------------------------------------------
bool signalGen_update() {
     uint32_t now = audioCap_getBlockCounter();


     if (s_state == GeneratorState::ARMED) {
            // FIX [missed-tolerance]: previous code used strict equality (==) for
            // start detection. A single main-loop stall of two blocks (common
            // under SPI display draw or SD flush) caused now > pending → MISSED,
            // even though the documented "+2 block margin" promised this should
            // be safe. We now treat any reach-or-pass within
            // SIGGEN_MAX_START_SKEW_BLOCKS as a successful alignment, and use the
            // unsigned-difference idiom so the comparison is wrap-safe.
            uint32_t age = now - s_pending_start_block;   // unsigned wrap-safe
            bool reached = ((int32_t)age >= 0);
            if (reached) {
                if (age > SIGGEN_MAX_START_SKEW_BLOCKS) {
                    // Skew exceeds tolerance — alignment lost.
                    // measurement_engine must abort rather than produce mis-timed data.
                    s_state = GeneratorState::MISSED;
                    Serial.printf("[SigGen] MISSED: target block %lu, current block %lu (skew %lu)\n",
                                  (unsigned long)s_pending_start_block,
                                  (unsigned long)now,
                                  (unsigned long)age);
                    return false;
                }
                // Within tolerance — begin output, but record the *target* block as
                // the actual start so measurement_engine's accumulation window matches
                // the intent (any 1–8 block skew is a sub-FFT-frame artefact).
                s_actual_start_block = s_pending_start_block;
                prepareDDS();
                s_state = GeneratorState::ACTIVE;
                Serial.printf("[SigGen] ACTIVE at block %lu (target %lu, skew %lu)\n",
                              (unsigned long)now,
                              (unsigned long)s_pending_start_block,
                              (unsigned long)age);
                return true;      // Signal to measurement_engine: aligned start confirmed
            }
            // Not yet — stay ARMED
            return false;
     }


     if (s_state == GeneratorState::ACTIVE) {
            if (s_config.type == StimulusType::INTERNAL_LOG_SWEEP) {
                // Advance sweep sample counter by one block's worth of samples.
                // The actual per-sample DDS update happens in the Audio Library
                // interrupt context (when injection is implemented). For now,
                // we track the count at block granularity.
                // FIX [sweep-timing]: The Teensy Audio Library processes audio
                // in blocks of 128 samples, not FFT_SIZE (1024) samples.
            // Using FFT_SIZE here would advance the sweep counter 8× too fast,
            // causing premature sweep completion and incorrect
            // signalGen_getSweepSamplesProduced() values, which directly
            // affects sweep completion detection and latency / IR timing.
            // AUDIO_BLOCK_SAMPLES = 128 is the correct block size constant
            // from the Teensy Audio Library (defined in AudioStream.h).
            uint32_t samples_per_block = AUDIO_BLOCK_SAMPLES;     // 128, not FFT_SIZE
            s_sweep_samples_produced += samples_per_block;


            if (s_sweep_samples_produced >= s_sweep_samples_total) {
                  // Sweep complete — stop output. measurement_engine detects
                  // this via signalGen_getSweepSamplesProduced() and closes capture.
                  signalGen_stop();
                  Serial.println("[SigGen] Sweep complete, generator stopped.");
            }
        }
        return false;
    }


    return false;
}


// =============================================================================
// PUBLIC FUNCTION IMPLEMENTATIONS
// =============================================================================


// -----------------------------------------------------------------------------
// signalGen_init()
// -----------------------------------------------------------------------------
void signalGen_init() {
    s_state = GeneratorState::IDLE;
    s_pending_start_block      = 0;
    s_actual_start_block       = 0;
    s_sweep_samples_produced = 0;
    s_sweep_samples_total      = 0;
    s_dds_phase                = 0.0;
    s_dds_phase_inc            = 0.0;
    s_amplitude_linear         = 0.0f;


    // Zero the Audio Library synthesis objects (silence)
    s_sine_osc.amplitude(0.0f);
    s_noise_src.amplitude(0.0f);
    // gen_mixer: pass-through gains (amplitude on sources controls level)
    s_gen_mixer.gain(0, 1.0f);        // sine channel
    s_gen_mixer.gain(1, 1.0f);        // noise channel
    s_gen_mixer.gain(2, 0.0f);
    s_gen_mixer.gain(3, 0.0f);
    // Set s_mixer_ret slot 2 to 1.0 so the generator monitor is live.
    // applyRoute() zeros slot 2 as a side-effect, but
    // audioCap_notifyRouteChanged() restores it to 1.0f immediately after
    // applyRoute(), so the monitor survives route changes automatically.
    s_mixer_ret.gain(2, 1.0f);      // generator monitor — always on


    // Default config: white noise at –6 dBFS
    s_config = genConfig_white(-6.0f);


    Serial.println("[SigGen] Signal generator initialised.");
    Serial.println("[SigGen] Output wired to monitoring R (headphone right) via s_mixer_ret slot 2.");
    Serial.println("[SigGen] DUT injection pending signal_router — use EXTERNAL stimulus for measurements.");
    Serial.println("[SigGen] NOTE: Audio output injection is stubbed — "
                     "state machine and timing are active.");
}


// -----------------------------------------------------------------------------
// signalGen_configure(config)
// -----------------------------------------------------------------------------
bool signalGen_configure(const GeneratorConfig& config) {
    bool clamped = false;


    s_config = config;


    // Clamp amplitude
    clamped = clampAmplitude(s_config.amplitude_dbfs);
    s_amplitude_linear = dbfsToLinear(s_config.amplitude_dbfs);


    // FIX [config-nan]: NaN-guard every frequency / duration field before clamping.
    // Arduino's constrain()/comparison operators return false on NaN, so a NaN
    // value would slip past the min/max checks and be used directly in
    // (uint32_t)(NaN * SAMPLE_RATE) and powf(10, NaN/20) — both undefined.
    if (!isfinite(s_config.sine_freq_hz))     { s_config.sine_freq_hz     = 1000.0f; clamped = true; }
    if (!isfinite(s_config.sweep_start_hz))   { s_config.sweep_start_hz   = 20.0f;   clamped = true; }
    if (!isfinite(s_config.sweep_end_hz))     { s_config.sweep_end_hz     = 20000.0f; clamped = true; }
    if (!isfinite(s_config.sweep_duration_s)) { s_config.sweep_duration_s = 1.0f;    clamped = true; }

    // Validate type-specific parameters.
    // Nyquist is SAMPLE_RATE/2; we use a conservative 0.45*SAMPLE_RATE upper bound
    // so that anti-alias filtering and DDS quantisation noise stay manageable.
    const float NYQ_SAFE_HZ = 0.45f * (float)SAMPLE_RATE;
    if (s_config.type == StimulusType::INTERNAL_SINE) {
        if (s_config.sine_freq_hz < 20.0f)        { s_config.sine_freq_hz = 20.0f;        clamped = true; }
        if (s_config.sine_freq_hz > NYQ_SAFE_HZ)  { s_config.sine_freq_hz = NYQ_SAFE_HZ;  clamped = true; }
    }
    if (s_config.type == StimulusType::INTERNAL_LOG_SWEEP) {
        if (s_config.sweep_start_hz < 20.0f)         { s_config.sweep_start_hz   = 20.0f;        clamped = true; }
        if (s_config.sweep_start_hz > NYQ_SAFE_HZ)   { s_config.sweep_start_hz   = NYQ_SAFE_HZ;  clamped = true; }
        if (s_config.sweep_end_hz   < 20.0f)         { s_config.sweep_end_hz     = 20.0f;        clamped = true; }
        if (s_config.sweep_end_hz   > NYQ_SAFE_HZ)   { s_config.sweep_end_hz     = NYQ_SAFE_HZ;  clamped = true; }
        // Ordering: end must be strictly above start
        if (s_config.sweep_end_hz <= s_config.sweep_start_hz) {
            s_config.sweep_end_hz = s_config.sweep_start_hz + 100.0f;
            if (s_config.sweep_end_hz > NYQ_SAFE_HZ) s_config.sweep_end_hz = NYQ_SAFE_HZ;
            clamped = true;
        }
        if (s_config.sweep_duration_s < 0.1f)        { s_config.sweep_duration_s = 0.1f;         clamped = true; }
        if (s_config.sweep_duration_s > 10.0f)       { s_config.sweep_duration_s = 10.0f;        clamped = true; }
    }

    // Re-clamp amplitude in case any caller passed NaN
    if (!isfinite(s_config.amplitude_dbfs)) { s_config.amplitude_dbfs = -6.0f; clamped = true; }
    clampAmplitude(s_config.amplitude_dbfs);
    s_amplitude_linear = dbfsToLinear(s_config.amplitude_dbfs);

    if (clamped) {
        Serial.println("[SigGen] WARNING: One or more parameters were clamped to valid range.");
    }
    // FIX [sweep-stub]: the log-sweep DDS does not yet update the per-sample
    // phase increment across the sweep duration — prepareDDS() sets the start
    // frequency, and signalGen_update() only advances a sample counter. The
    // audible output for INTERNAL_LOG_SWEEP is therefore a single tone at
    // sweep_start_hz, not a swept signal. Document the limitation loudly so
    // callers do not interpret a "completed sweep" as a real measurement.
    // Sweep correctness is moot today because DUT injection is also stubbed,
    // but the next maintainer must implement per-sample DDS before relying
    // on INTERNAL_LOG_SWEEP for latency or impulse-response measurements.
    if (s_config.type == StimulusType::INTERNAL_LOG_SWEEP) {
        Serial.println("[SigGen] WARNING: INTERNAL_LOG_SWEEP DDS is stubbed — audible output");
        Serial.println("[SigGen] WARNING: will be a tone at sweep_start_hz, not a real sweep.");
        Serial.println("[SigGen] WARNING: Use EXTERNAL stimulus for real sweep measurements.");
    }
    return !clamped;
}


// -----------------------------------------------------------------------------
// signalGen_startAtBlock(block_number)
// -----------------------------------------------------------------------------
bool signalGen_startAtBlock(uint32_t block_number) {
    uint32_t now = audioCap_getBlockCounter();
    uint32_t margin = block_number - now;


    // Reject if the target block has already passed. Use signed delta so a
    // start block just after the uint32_t wrap is accepted as "future."
    if (margin == 0 || (int32_t)margin < 0) {
        s_state = GeneratorState::MISSED;
        Serial.printf("[SigGen] startAtBlock(%lu) rejected: current block is %lu\n",
                        block_number, now);
        return false;
    }


    // Validate minimum margin
    if (margin < 2) {
        Serial.printf("[SigGen] WARNING: startAtBlock(%lu) margin is only %lu blocks "
                        "(minimum 2 recommended)\n", block_number, margin);
    }


    s_pending_start_block      = block_number;
    s_actual_start_block       = 0;
    s_sweep_samples_produced = 0;
    s_state = GeneratorState::ARMED;


    Serial.printf("[SigGen] Armed: target block %lu (current %lu, margin %lu)\n",
                    block_number, now, margin);
    return true;
}


// -----------------------------------------------------------------------------
// signalGen_startNow()
// For non-precision use only — no block alignment guarantee.
// -----------------------------------------------------------------------------
void signalGen_startNow() {
    s_actual_start_block     = audioCap_getBlockCounter();
    s_pending_start_block    = 0;   // FIX [stale-pending]: clear leftover from a prior arm()
    s_sweep_samples_produced = 0;
    prepareDDS();
    s_state = GeneratorState::ACTIVE;
    Serial.printf("[SigGen] startNow() at block %lu (no alignment guarantee)\n",
                    (unsigned long)s_actual_start_block);
}


// -----------------------------------------------------------------------------
// signalGen_stop()
// Safe from any context including interrupt.
// -----------------------------------------------------------------------------
void signalGen_stop() {
    s_state = GeneratorState::IDLE;
    s_sine_osc.amplitude(0.0f);
    s_noise_src.amplitude(0.0f);
    s_dds_phase       = 0.0;
    s_dds_phase_inc = 0.0;
}


// =============================================================================
// STATE QUERIES
// =============================================================================


GeneratorState signalGen_getState() {
    return s_state;
}


uint32_t signalGen_getActualStartBlock() {
    return s_actual_start_block;
}


uint32_t signalGen_getSweepSamplesProduced() {
    if (s_config.type != StimulusType::INTERNAL_LOG_SWEEP) return 0;
    return s_sweep_samples_produced;
}


uint32_t signalGen_getSweepSamplesDuration() {
    if (s_config.type != StimulusType::INTERNAL_LOG_SWEEP) return 0;
    return s_sweep_samples_total;
}


// =============================================================================
// CONVENIENCE FACTORY FUNCTIONS
// =============================================================================


GeneratorConfig genConfig_pink(float amplitude_dbfs) {
    GeneratorConfig c{};
    c.type             = StimulusType::INTERNAL_PINK;
    c.amplitude_dbfs = amplitude_dbfs;
    return c;
}


GeneratorConfig genConfig_white(float amplitude_dbfs) {
    GeneratorConfig c{};
    c.type             = StimulusType::INTERNAL_WHITE;
    c.amplitude_dbfs = amplitude_dbfs;
    return c;
}
GeneratorConfig genConfig_sine(float freq_hz, float amplitude_dbfs) {
    GeneratorConfig c{};
    c.type             = StimulusType::INTERNAL_SINE;
    c.amplitude_dbfs = amplitude_dbfs;
    c.sine_freq_hz     = freq_hz;
    return c;
}


GeneratorConfig genConfig_sweep(float start_hz, float end_hz,
                                    float duration_s, float amplitude_dbfs) {
    GeneratorConfig c{};
    c.type                 = StimulusType::INTERNAL_LOG_SWEEP;
    c.amplitude_dbfs       = amplitude_dbfs;
    c.sweep_start_hz       = start_hz;
    c.sweep_end_hz         = end_hz;
    c.sweep_duration_s     = duration_s;
    return c;
}
