// =============================================================================
// presentation.h  —  Guitar Rig Analyzer
// =============================================================================
// THE PRESENTATION BOUNDARY.
//
// Authority: docs/adr/ADR-001-display-architecture.md (ACCEPTED 2026-09-11).
//
// This is the ONLY display-facing surface the application is permitted to call.
// Nothing above this header knows, or may ask, whether the renderer is a
// Raspberry Pi 5 over UART, an RA8875 over SPI, or nothing at all.
//
//   guitar_rig_analyzer.ino  ──calls──▶  presentation_*  ──dispatches──▶  backend
//
// Backend selection is the single constant DISPLAY_TARGET in config.h:
//
//   DISPLAY_TARGET_PI      → data_sender      (binary UART, production)
//   DISPLAY_TARGET_RA8875 → display_engine   (SPI panel, debug/fallback)
//   DISPLAY_TARGET_NONE    → null backend     (bench DSP, no display hardware)
//
// WHY THIS LAYER EXISTS
// ---------------------
// The repository previously had ~20 direct displayEngine_* calls in the .ino and
// a complete, zero-caller data_sender module — two renderer architectures, one
// of them unreachable. The obvious fix (swap the call sites to dataSender_*)
// would have hard-wired the second assumption in place of the first and produced
// another fork to untangle. Routing through one API instead makes renderer
// choice a build decision. Adding a renderer is one #elif arm here, not an edit
// to every call site. See ADR-001 "Explicitly rejected".
//
// THE GOVERNING INVARIANT
// -----------------------
//   *** The Teensy determines truth. The renderer presents truth. ***
//
// Every function below is one-way: application → renderer. There is
// deliberately NO return path through which a renderer could report a
// measurement value, a validity verdict, a quality grade, or a confidence
// figure back into the measurement path. A renderer may format, plot, animate,
// interpolate and navigate; it may not decide what is true.
//
// That is why none of these functions return data, and why presentation_init()
// returns bool only to report whether the renderer came up — never to gate
// acquisition. See the "boot criticality" note below.
//
// *** IF Pi -> TEENSY INPUT IS EVER ADDED, IT DOES NOT COME THROUGH HERE. ***
// Touch commands travelling back from the Pi (TODO-36 contemplates them driving
// measurement_engine) are CONTROL, not presentation. They belong behind a
// separate input/control boundary with its own validation, because they cross a
// trust boundary this one does not: presentation is outbound-only today, so it
// adds no externally-controlled input surface at all.
//
// Routing control back through this API would destroy the property that makes it
// worth having — that a renderer cannot influence measurement. A control channel
// may ask the measurement engine to do something through the same entry points
// the serial shell uses (arm, cancel, acknowledge); it must never carry a
// measurement value, a validity verdict, or a quality grade INTO the DSP path.
//
// BOOT CRITICALITY
// ----------------
// A display failure must NEVER prevent acquisition or DSP from starting. This is
// not a style preference: with the RA8875 absent, the Adafruit library's
// waitPoll() spin stretched the audio block period from 46 ms to 2194 ms — a
// display defect that destroyed acquisition (journal 2026-09-05 (10), TODO-25).
// Callers MUST treat a false return from presentation_init() as a warning and
// continue. Every backend's remaining entry points must stay safe to call after
// a failed init.
// =============================================================================

#ifndef PRESENTATION_H
#define PRESENTATION_H

#include "config.h"
#include "audio_engine.h"        // AudioFrame
#include "measurement_core.h"    // MeasurementResult
#include "insights_engine.h"     // InsightList


// =============================================================================
// BACKEND IDENTITY
// =============================================================================

// -----------------------------------------------------------------------------
// presentation_backendName()
// Human-readable name of the compiled-in backend ("Pi 5 (UART)", "RA8875 (SPI)",
// or "none"). For the boot banner and for serial diagnostics, so a log always
// records which renderer the firmware was built against. Never null.
// -----------------------------------------------------------------------------
const char* presentation_backendName();


// =============================================================================
// LIFECYCLE
// =============================================================================

// -----------------------------------------------------------------------------
// presentation_init()
// Brings up the selected renderer. Call once from setup().
//
// Returns true if the renderer is usable, false if it is not.
//
// *** A false return is NOT fatal and MUST NOT halt boot. *** Log it and
// continue to audio init. All other presentation_* calls remain safe after a
// failed init — they become no-ops. DISPLAY_TARGET_NONE always returns true.
// -----------------------------------------------------------------------------
bool presentation_init();


// =============================================================================
// LIVE PATH
// =============================================================================

// -----------------------------------------------------------------------------
// presentation_updateLive(frame)
// Publishes one live analysis frame (spectra, peaks, TF curve, confidence,
// clip and clamp state) to the renderer.
//
// Call at the live cadence — once per processed output block, subject to
// DISPLAY_UPDATE_EVERY_N_FRAMES (~11 Hz).
//
// The frame is READ-ONLY to the renderer. A null frame is ignored.
// -----------------------------------------------------------------------------
void presentation_updateLive(const AudioFrame* frame);

// -----------------------------------------------------------------------------
// presentation_status(msg)
// Publishes a short human-readable status line ("Ready", "Measuring — external
// stimulus", "Cal save FAILED — check SD").
//
// This is a NOTIFICATION, not a measurement channel. Never encode numeric
// measurement data in a status string for the renderer to parse back out —
// that would route truth through a formatting path. A null message is ignored.
// -----------------------------------------------------------------------------
void presentation_status(const char* msg);


// =============================================================================
// RESULT PATH
// =============================================================================

// -----------------------------------------------------------------------------
// presentation_showResult(result, insights)
// Publishes a completed measurement plus its insight list.
//
// Carries the Teensy's verdicts — validity, quality grade, coherence,
// confidence, calibration provenance — as verdicts. The renderer displays them;
// it does not recompute them.
// -----------------------------------------------------------------------------
void presentation_showResult(const MeasurementResult& result,
                             const InsightList& insights);

// -----------------------------------------------------------------------------
// presentation_showAborted(reason)
// Publishes a measurement abort and its reason.
//
// The ABORTED state is sticky by design (measurement_engine.h) — the reason must
// stay visible until the user acknowledges. A renderer must not clear it on its
// own initiative; it is cleared by presentation_restoreLive() after the
// application has processed the acknowledgement.
// -----------------------------------------------------------------------------
void presentation_showAborted(const char* reason);

// -----------------------------------------------------------------------------
// presentation_restoreLive()
// Returns the renderer from a result/abort view to the live view. Call after the
// application has handled an acknowledgement or a return-to-live command.
//
// Under DISPLAY_TARGET_PI this emits an explicit view-transition packet, so a Pi
// state model never has to infer a view change from status text. (Protocol v1
// had no such packet and this mapped to a magic STATUS string — audit T3.)
// -----------------------------------------------------------------------------
void presentation_restoreLive();


// =============================================================================
// SERVICE AND DIAGNOSTICS
// =============================================================================

// -----------------------------------------------------------------------------
// presentation_service()
// *** MUST be called every loop iteration, unconditionally. ***
//
// Gives the backend a chance to make progress on deferred work without blocking.
// Under DISPLAY_TARGET_PI this drains a pending RESULT packet onto the UART as
// room appears — without it the reliable delivery path never completes. No-op for
// the other backends.
//
// Cheap when there is nothing to do. Call it outside any "if a new block
// arrived" guard: transport progress must not depend on audio activity, or a
// result queued just as the signal goes quiet would never finish sending.
// -----------------------------------------------------------------------------
void presentation_service();

// -----------------------------------------------------------------------------
// presentation_printDiagnostics()
// Prints the backend's transport/renderer health to USB Serial.
//
// Print this ALONGSIDE audio block timing, never alone. The question a reader is
// always asking is "did presentation work perturb acquisition?", and that is a
// comparison, not a single number.
// -----------------------------------------------------------------------------
void presentation_printDiagnostics();


// =============================================================================
// ROUTER PATH
// =============================================================================

// -----------------------------------------------------------------------------
// presentation_routerStatus()
// Publishes a jack/route/monitor state snapshot.
//
// No-op under DISPLAY_TARGET_RA8875 — display_engine has no router panel, and
// inventing one to satisfy API symmetry would be fake work. The asymmetry is
// real and is recorded rather than papered over: the Pi can show routing state,
// the RA8875 debug backend cannot.
// -----------------------------------------------------------------------------
void presentation_routerStatus();


#endif // PRESENTATION_H
