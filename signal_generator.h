// =============================================================================
// signal_generator.h     —   Guitar Rig Analyzer
// =============================================================================
// Public interface for the signal generator module.
//
// CHANGELOG v0.4.1     (last functional change — no logic changes since)
// ----------------
// No functional changes in this revision. Version bumped to match the rest
//
// Cross-reference notes added:
//   • startAtBlock() now explicitly references audioCap_getBlockCounter()
//     as the source of the current block counter value, consistent with
//     audio_capture.h being the canonical timebase owner.
//   • MISSED state references AbortReason::GENERATOR_MISSED in
//     measurement_core.h — confirmed consistent (both defined there).
//
// OWNERSHIP
// ---------
// signal_generator owns:
//   • DDS oscillator state (phase accumulator, frequency register)
//   • Pink noise IIR filter state
//   • Log-frequency sweep parameters and current position
//   • Block-aligned start mechanism
//   • Output amplitude control
//   • Injection into the Audio Library graph
//     (synthesis objects declared; wiring to output path deferred
//      pending signal_router hardware design — see signal_generator.cpp)
//
// signal_generator does NOT own:
//   • When to start or stop (measurement_engine decides)
//   • What measurement is being served (receives parameters, not context)
//   • Which jack the signal exits from (signal_router, future module)
//   • Capture or analysis of the generated signal (measurement_engine)
//
// AMPLITUDE UNITS — dBFS ONLY
// ---------------------------
// All amplitude parameters in the public API are in dBFS.
// 0 dBFS is never permitted as a generator output level.
// Range: –60 to –3 dBFS. Values outside this range are clamped.
// Recommended: –6 dBFS for most measurements (good SNR, clipping headroom).
//
// BLOCK-ALIGNED START
// -------------------
// signalGen_startAtBlock() guarantees output begins on the specified block
// boundary. The block counter is obtained from audioCap_getBlockCounter()
// (audio_capture is the canonical timebase).
//
// Safe margin: block_number >= audioCap_getBlockCounter() + 2.
// measurement_engine factories use N = 4 by convention.
//
// If the target block has already passed when the interrupt fires:
//    → GeneratorState::MISSED is set
//    → signalGen_startAtBlock() returns false
//    → measurement_engine transitions to ABORTED (GENERATOR_MISSED)
//    (AbortReason::GENERATOR_MISSED is defined in measurement_core.h)
//
// DDS IMPLEMENTATION
// ------------------
// Phase accumulator: double (64-bit) — prevents frequency drift over long sweeps.
// Output: sinf(float(phase_accum)) per sample via ARM Cortex-M7 FPU.
// Log sweep frequency law: f(n) = f1 * (f2/f1)^(n / (N-1))
//    where n = sample index from sweep start, N = total sweep samples.
// =============================================================================


#ifndef SIGNAL_GENERATOR_H
#define SIGNAL_GENERATOR_H


#include <Arduino.h>
#include "config.h"
#include "measurement_core.h"         // For StimulusType


// =============================================================================
// GENERATOR STATE
// =============================================================================
enum class GeneratorState : uint8_t {
     IDLE    = 0,    // No output; output path muted
     ARMED   = 1,    // Configured; waiting for target block counter
     ACTIVE = 2,     // Producing output
     MISSED = 3,     // startAtBlock() target was past when checked
                     // → measurement_engine must detect and abort
                     //   (AbortReason::GENERATOR_MISSED in measurement_core.h)
};


// =============================================================================
// GENERATOR CONFIGURATION
// =============================================================================
struct GeneratorConfig {


     StimulusType type;
     float          amplitude_dbfs;       // Range: –60 to –3 dBFS. Clamped if outside.
                                          // 0 dBFS never permitted.
     float   sine_freq_hz;           // INTERNAL_SINE: frequency [20, 20000] Hz
     float   sweep_start_hz;         // INTERNAL_LOG_SWEEP: start frequency
     float   sweep_end_hz;           //                      end frequency
     float   sweep_duration_s;       //                      duration [0.1, 10.0] s
     // INTERNAL_PINK, INTERNAL_WHITE: no additional parameters
};


// =============================================================================
// PUBLIC API
// =============================================================================


// -----------------------------------------------------------------------------
// signalGen_init()
// Initialise and mute output path. Call after audioCap_init().
// -----------------------------------------------------------------------------
void signalGen_init();


// -----------------------------------------------------------------------------
// signalGen_configure(config)
// Set type, amplitude, frequency parameters. Does not start output.
// Returns false if any parameter was clamped (clamping still applied).
// -----------------------------------------------------------------------------
bool signalGen_configure(const GeneratorConfig& config);


// -----------------------------------------------------------------------------
// signalGen_startAtBlock(block_number)
// Arm generator to begin output on the specified audio block boundary.
//
// block_number must be >= audioCap_getBlockCounter() + 2.
// (audioCap_getBlockCounter() is the canonical timebase source.)
//
// Returns true if block_number is in the future and arm was accepted.
// Returns false if block_number has already passed (MISSED state set).
//
// measurement_engine must check signalGen_getState() after a suitable
// number of blocks to confirm ACTIVE before trusting capture alignment.
// If MISSED: call measurementEngine_cancel() → ABORTED (GENERATOR_MISSED).
// -----------------------------------------------------------------------------
bool signalGen_startAtBlock(uint32_t block_number);


// -----------------------------------------------------------------------------
// signalGen_startNow()
// Start without block alignment. For listening tests and demos ONLY.
// DO NOT use for any measurement requiring phase or latency accuracy.
// -----------------------------------------------------------------------------
void signalGen_startNow();
// -----------------------------------------------------------------------------
// signalGen_stop()
// Stop immediately. Safe from any state including interrupt context.
// Transitions to IDLE.
// -----------------------------------------------------------------------------
void signalGen_stop();


// =============================================================================
// STATE QUERIES
// =============================================================================
GeneratorState signalGen_getState();
uint32_t       signalGen_getActualStartBlock();       // 0 if never started
uint32_t       signalGen_getSweepSamplesProduced();// 0 for non-sweep types
uint32_t       signalGen_getSweepSamplesDuration();// Total samples for sweep


// =============================================================================
// CONVENIENCE FACTORIES
// =============================================================================
GeneratorConfig genConfig_pink   (float amplitude_dbfs = -6.0f);
GeneratorConfig genConfig_white (float amplitude_dbfs = -6.0f);
GeneratorConfig genConfig_sine   (float freq_hz, float amplitude_dbfs = -6.0f);
GeneratorConfig genConfig_sweep (float start_hz, float end_hz,
                                  float duration_s,
                                  float amplitude_dbfs = -6.0f);


#endif // SIGNAL_GENERATOR_H
