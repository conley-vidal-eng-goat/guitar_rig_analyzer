// =============================================================================
// measurement_engine.h   —   Guitar Rig Analyzer
// =============================================================================
// Public interface for the precision measurement engine.
//
// CHANGELOG v0.4.1
// ----------------
// FIX [event-api]: measurementEngine_pollEvent() did not exist in this header
//   and was never the correct mechanism. The actual event model is that
//   measurementEngine_update() returns a MeasurementEvent directly. All
//   comments in this header now correctly describe update() as the source
//   of events. There is no separate poll function.
//
// PRECISION MODES: MODE_PRECISION and MODE_LF are defined in measurement_core.h
// but are not yet implemented. measurementEngine_arm() rejects those modes
// and returns false. All measurement factories currently use MODE_LIVE.
// When implemented, those modes will use an OCRAM large-FFT accumulator
// and rebin to the canonical 512-bin result grid.
//
// FIX [route-change]: The dependency on audioCap_notifyRouteChanged() is
//   now documented explicitly. audioEngine_setRoute() → audioCap_notifyRouteChanged()
//   → ROUTE_CHANGED event → main loop → measurementEngine_notifyRouteChanged().
//   The chain is complete and documented here.
//
// OWNERSHIP
// ---------
// measurement_engine owns:
//   • The measurement state machine
//   • MeasurementAccumulator (internal to measurement_engine.cpp)
//   • Internal precision accumulator in OCRAM
//     (NOT YET IMPLEMENTED — measurementEngine_arm() rejects MODE_PRECISION
//      and MODE_LF; all factories use MODE_LIVE)
//   • MeasurementResult (produced and owned; external modules get const ref)
//   • Calibration application (reads CalibrationBuffer from calibration_store)
//   • Generator start/stop commands
//   • Event notification (via measurementEngine_update() return value)
//
// measurement_engine does NOT own:
//   • Audio acquisition (audio_capture)
//   • File I/O (export_engine)
//   • Display output (display_engine)
//   • Generator parameters (signal_generator)
//   • Calibration storage (calibration_store)
//   • Advisory interpretation (insights_engine)
//
// EVENT MODEL — CORRECT DESCRIPTION
// ----------------------------------
// Events are returned by measurementEngine_update(), called once per main
// loop iteration. There is no separate event queue or poll function.
//
//   MeasurementEvent ev = measurementEngine_update();
//   switch (ev) {
//       case MeasurementEvent::RESULT_READY:
//         displayEngine_showResult(measurementEngine_getResult(), insightsEngine_getInsights()
//         break;
//       case MeasurementEvent::ABORTED:
//         // STICKY ABORT: do NOT call acknowledgeAbort() here automatically.
//         // The ABORTED state is latched until the user explicitly clears it
//         // (via a button, touch action, or 'x' Serial command). This ensures
//         // the abort reason is visible on the display before the state resets.
//         // Call acknowledgeAbort() from the user action handler, not here.
//         displayEngine_drawStatusMessage(measurementEngine_getAbortDescription());
//         // measurementEngine_acknowledgeAbort(); ← call from user action only
//         break;
//       ...
//   }
//
// STATE MACHINE — SINGLE RESPONSIBILITY RULE
// ------------------------------------------
// State transitions happen ONLY inside measurement_engine.
// measurementEngine_cancel() is the only externally-triggered transition.
//
// ROUTE CHANGE HANDLING
// ----------------------
// When audioEngine_setRoute() is called:
//   1. audioEngine_setRoute() calls audioCap_notifyRouteChanged()
//   2. audioCap_notifyRouteChanged() programs the mixer gains
//        (audio_capture owns the mixers — audio_engine only records route metadata)
//   3. On next audioCap_update(), AudioCaptureEvent::ROUTE_CHANGED is returned
//   4. Main loop sees ROUTE_CHANGED and calls measurementEngine_notifyRouteChanged()
//        (from any active measurement state, not only CAPTURE)
//   5. measurement_engine transitions to ABORTED (ROUTE_CHANGED)
//
// The main loop owns step 4. measurement_engine reacts, it does not detect
// route changes independently.
// =============================================================================


#ifndef MEASUREMENT_ENGINE_H
#define MEASUREMENT_ENGINE_H


#include <Arduino.h>
#include "config.h"
#include "measurement_core.h"
#include "audio_capture.h"


// =============================================================================
// MEASUREMENT STATE
// =============================================================================
enum class MeasurementState : uint8_t {


     IDLE          = 0,
     // No measurement active. Live display runs normally.
     // Exit: measurementEngine_arm() → ARMED


     ARMED         = 1,
     // Waiting for start condition.
     // EXTERNAL stimulus: waiting for source level above threshold.
     // INTERNAL stimulus: waiting for specified block counter value.
     // Exit:
     //      Start condition met → CAPTURE
     //      arm_timeout_ms elapsed → ABORTED (TIMEOUT)
     //      measurementEngine_cancel()              → ABORTED (USER_CANCEL)
//    measurementEngine_notifyRouteChanged() → ABORTED (ROUTE_CHANGED)


     CAPTURE       = 2,
     // Accumulating complex FFT frames.
     // Reads CONSUMER_MEASURE block from audio_capture each loop.
     //
     // CURRENT IMPLEMENTATION: all three modes share the MODE_LIVE accumulation
     // path — direct accumulation into the canonical 512-bin MeasurementAccumulator.
     // The internal OCRAM large-FFT accumulator and rebinning step described in
     // measurement_core.h are not yet implemented. MODE_PRECISION and MODE_LF
     // produce correctly-structured results but without the additional internal
     // frequency resolution those modes are intended to provide.
     // This limitation is documented in measurement_engine.cpp s_accum comment.
     //
     // For MODE_LIVE: accumulates directly into MeasurementAccumulator (fully implemented).
     // Exit:
     //      n_averages_completed → PROCESSING
     //      Clipping (if abort_on_clip) → ABORTED
     //      measurementEngine_cancel() → ABORTED (USER_CANCEL)
     //      (Main loop calls cancel() when it sees AudioCaptureEvent::ROUTE_CHANGED)


     PROCESSING = 3,
     // Compute all derived products from MeasurementAccumulator (canonical grid):
     //      auto-spectra → coherence → H1/H2 → phase → group delay → calibration.
     // Runs to completion without yielding (~1 ms at 600 MHz with FPU).
     // Generator stopped on entry.
     // Exit: always → RESULT


     RESULT      = 4,
     // MeasurementResult is valid and stable.
     // Main loop calls displayEngine_showResult() and insightsEngine_getInsights()
     // on RESULT_READY. Results are also accessible via getResult() and Serial.
     // Exit:
     //   measurementEngine_arm() → ARMED (new measurement)
     //   measurementEngine_returnToLive() → IDLE
     //   measurementEngine_exportToSD() → EXPORTING


     EXPORTING   = 5,
     // export_engine serialising result to SD (~200 ms for JSON).
     // Exit: complete → RESULT


     ABORTED     = 6,
     // Fatal condition or user cancel. AbortReason set.
     // Accumulator cleared. Generator stopped.
     // Exit: measurementEngine_acknowledgeAbort() → IDLE


     SELF_TEST   = 7,
     // Startup pipeline liveness check: verifies that audio_capture is
     // producing blocks (AudioStream::update_counter is advancing).
     // This does NOT perform a loopback signal test — it confirms the
     // I2S / Audio Library pipeline is alive, not that measurements are accurate.
     // A full signal-path validation requires the validation suite ('v' command).
     // Raises SELF_TEST_PASSED (pipeline alive) or SELF_TEST_FAILED (no blocks).
     // Device continues to IDLE regardless of result.
     // Exit: complete → IDLE
};


// =============================================================================
// PUBLIC API
// =============================================================================


// -----------------------------------------------------------------------------
// measurementEngine_init()
// Call from setup() after audioCap_init() and calibration_store_init().
// Loads default calibration. Arms power-on self-test (runs during first
// calls to measurementEngine_update() — does not block setup()).
// -----------------------------------------------------------------------------
void measurementEngine_init();


// -----------------------------------------------------------------------------
// measurementEngine_update()
// CALL ONCE PER MAIN LOOP ITERATION.
//
// FIX [event-api]: This function IS the event notification mechanism.
// There is no separate measurementEngine_pollEvent().
//
// Drives the state machine:
//   IDLE:        no-op
//   ARMED:       checks start condition
//   CAPTURE:     reads CONSUMER_MEASURE; accumulates
//                For precision modes: accumulates into OCRAM buffer;
//                when complete, resamples to canonical grid → PROCESSING
//   PROCESSING: derives all products; transitions to RESULT
//   RESULT:      no-op
//   EXPORTING:   drives export_engine
//   ABORTED:     no-op
//   SELF_TEST:   drives self-test sequence
//
// Returns MeasurementEvent::NONE most of the time.
// Returns a non-NONE event when state changes or a notable condition occurs.
// The main loop should switch on the returned event:
//
//   MeasurementEvent ev = measurementEngine_update();
//   if (ev == MeasurementEvent::RESULT_READY) { ... }
//   if (ev == MeasurementEvent::ABORTED)       { ... }
// -----------------------------------------------------------------------------
MeasurementEvent measurementEngine_update();


// -----------------------------------------------------------------------------
// measurementEngine_arm(params)
// Valid from IDLE or RESULT. Returns false if params are invalid.
// On success, transitions to ARMED.
// -----------------------------------------------------------------------------
bool measurementEngine_arm(const MeasurementParams& params);


// -----------------------------------------------------------------------------
// measurementEngine_cancel()
// Explicit user cancel: ARMED/CAPTURE/PROCESSING → ABORTED (USER_CANCEL).
// No-op from IDLE, RESULT, or ABORTED.
// For topology invalidation (route change), use measurementEngine_notifyRouteChanged()
// so the abort reason correctly identifies the cause.
// -----------------------------------------------------------------------------
void measurementEngine_cancel();


// -----------------------------------------------------------------------------
// measurementEngine_notifyRouteChanged()
// Called by the main loop when AudioCaptureEvent::ROUTE_CHANGED is received
// while a measurement is in progress. Aborts with AbortReason::ROUTE_CHANGED,
// correctly identifying the cause as topology invalidation, not user action.
// No-op from IDLE, RESULT, or ABORTED.
// -----------------------------------------------------------------------------
void measurementEngine_notifyRouteChanged();


// -----------------------------------------------------------------------------
// measurementEngine_acknowledgeAbort()
// Transition ABORTED → IDLE. Required before a new measurement can be armed.
// -----------------------------------------------------------------------------
void measurementEngine_acknowledgeAbort();


// -----------------------------------------------------------------------------
// measurementEngine_returnToLive()
// RESULT → IDLE. Caller must switch display to live view.
// -----------------------------------------------------------------------------
void measurementEngine_returnToLive();


// -----------------------------------------------------------------------------
// measurementEngine_exportToSD(filename)
// RESULT → EXPORTING. Returns false if not in RESULT or SD unavailable.
// Result remains valid after export completes.
// -----------------------------------------------------------------------------
bool measurementEngine_exportToSD(const char* filename);


// -----------------------------------------------------------------------------
// measurementEngine_runSelfTest()
// IDLE → SELF_TEST. No-op from other states.
// -----------------------------------------------------------------------------
void measurementEngine_runSelfTest();


// =============================================================================
// STATE QUERIES
// =============================================================================
MeasurementState measurementEngine_getState();
AbortReason        measurementEngine_getAbortReason();
const char*        measurementEngine_getStateDescription();
const char*        measurementEngine_getAbortDescription();
void               measurementEngine_getCaptureProgress(uint16_t* completed,
                                                         uint16_t* requested);


// =============================================================================
// RESULT ACCESS — valid ONLY when state == RESULT
// =============================================================================
const MeasurementResult& measurementEngine_getResult();


// =============================================================================
// CONVENIENCE PARAMETER FACTORIES
// =============================================================================
// Pre-configured MeasurementParams for standard measurement types.
// All use H1 estimator and apply calibration if available.
// Use these in preference to building MeasurementParams by hand.


// NOTE: All factory functions that request MODE_PRECISION or MODE_LF currently
// fall back to the MODE_LIVE accumulation path — the internal OCRAM accumulator
// and rebinning step are not yet implemented. fft_mode is stored in the result
// for future compatibility but does not affect current measurement accuracy.
//
// NOTE: Factory functions using INTERNAL_PINK, INTERNAL_SINE, or
// INTERNAL_LOG_SWEEP require the generator DUT injection path (pending
// signal_router). Until then, use EXTERNAL stimulus for real rig measurements.
MeasurementParams measureParams_rigAnalysis();     // Pink noise, MODE_PRECISION (→ LIVE), 32
MeasurementParams measureParams_cableCapacitance();// White noise, MODE_PRECISION (→ LIVE), 6
MeasurementParams measureParams_latency();         // Log sweep, internal stimulus [DUT injec
MeasurementParams measureParams_impulseResponse(); // Log sweep, internal stimulus [DUT injec
MeasurementParams measureParams_selfCalibration(); // White noise, FlatTop, 64 avg — use EXTE
MeasurementParams measureParams_humDetection();    // White noise, MODE_LF (→ LIVE), 32 avg


#endif // MEASUREMENT_ENGINE_H
