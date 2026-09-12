// =============================================================================
// presentation.cpp  —  Guitar Rig Analyzer
// =============================================================================
// Compile-time dispatch for the presentation boundary. See presentation.h for
// the contract and docs/adr/ADR-001-display-architecture.md for the decision.
//
// This file is intentionally thin. It contains NO formatting, NO geometry, NO
// protocol logic and NO measurement logic — only the mapping from one renderer-
// agnostic API onto one selected backend. If you find yourself wanting to put a
// calculation here, it belongs in the backend (presentation) or in the
// measurement path (truth), never in the dispatcher.
//
// Each arm includes ONLY its own backend's header. That alone is NOT enough to
// remove the unselected backend from the build: an Arduino/arduino-cli build
// compiles every .cpp in the sketch folder regardless of what includes its
// header, so display_engine.cpp and data_sender.cpp would both still be compiled
// and linked. Each of those two files therefore carries its own
// `#if DISPLAY_TARGET == ...` guard around its entire body. The two mechanisms
// together are what make DISPLAY_TARGET genuinely exclusive — and what makes
// DISPLAY_TARGET_NONE actually free rather than nominally free.
// =============================================================================

#include "presentation.h"


// =============================================================================
#if DISPLAY_TARGET == DISPLAY_TARGET_PI
// =============================================================================
// PRODUCTION BACKEND — Raspberry Pi 5 over binary UART.
// The Teensy measures; the Pi renders. data_sender owns the wire format.
// =============================================================================

#include "data_sender.h"

const char* presentation_backendName() { return "Pi 5 (UART)"; }

bool presentation_init() {
    return dataSender_init();
}

void presentation_updateLive(const AudioFrame* frame) {
    if (frame == nullptr) return;
    dataSender_sendLiveFrame(frame);
}

void presentation_status(const char* msg) {
    if (msg == nullptr) return;
    dataSender_sendStatus(msg);
}

void presentation_showResult(const MeasurementResult& result,
                             const InsightList& insights) {
    dataSender_sendResult(result, insights);
}

void presentation_showAborted(const char* reason) {
    if (reason == nullptr) return;
    dataSender_sendAborted(reason);
}

void presentation_restoreLive() {
    // Protocol v2 carries an explicit view-transition packet. v1 had none, so
    // this had to be a STATUS string the Pi would sniff for a magic prefix —
    // a view change indistinguishable from ordinary status text (audit T3).
    dataSender_sendView(DS_VIEW_LIVE);
}

void presentation_routerStatus() {
    dataSender_sendRouterStatus();
}

void presentation_service() {
    dataSender_service();
}

void presentation_printDiagnostics() {
    dataSender_printDiagnostics();
}


// =============================================================================
#elif DISPLAY_TARGET == DISPLAY_TARGET_RA8875
// =============================================================================
// DEBUG / FALLBACK BACKEND — RA8875 800x480 over SPI.
//
// Retained deliberately (ADR-001): it is working, bench-verified code, and
// deleting it to express an architectural preference would be a net loss. It is
// NOT the production renderer and its panel geometry is not retargeted to the
// Pi's 7" display.
//
// Selecting this arm reactivates the RA8875 pin claims in config.h, including
// the pin 8 -> 5 reset rewire requirement (TODO-24). Read that entry before
// mounting the panel.
// =============================================================================

#include "display_engine.h"

const char* presentation_backendName() { return "RA8875 (SPI)"; }

bool presentation_init() {
    // display_engine guards every entry point on s_display_ok, so a false
    // return here leaves the remaining calls safe (TODO-25).
    return displayEngine_init();
}

void presentation_updateLive(const AudioFrame* frame) {
    if (frame == nullptr) return;
    displayEngine_update(frame);
}

void presentation_status(const char* msg) {
    if (msg == nullptr) return;
    displayEngine_drawStatusMessage(msg);
}

void presentation_showResult(const MeasurementResult& result,
                             const InsightList& insights) {
    displayEngine_showResult(result, insights);
}

void presentation_showAborted(const char* reason) {
    if (reason == nullptr) return;
    displayEngine_showAborted(reason);
}

void presentation_restoreLive() {
    displayEngine_restoreLive();
}

void presentation_routerStatus() {
    // Intentionally empty. display_engine has no router panel. Inventing one to
    // satisfy API symmetry would be fake work; the asymmetry is recorded in
    // presentation.h instead.
}

void presentation_service() {
    // Nothing deferred: display_engine renders synchronously inside its update
    // calls. It has no queue to drain.
}

void presentation_printDiagnostics() {
    Serial.println("[Link] RA8875 backend — no transport layer, nothing to "
                   "report. Renders synchronously over SPI.");
}


// =============================================================================
#elif DISPLAY_TARGET == DISPLAY_TARGET_NONE
// =============================================================================
// NULL BACKEND — no display hardware.
//
// The honest configuration for bench DSP work during Phases 5-9, where no panel
// is attached to anything. Costs nothing at runtime and pulls in neither the
// RA8875 library nor the UART protocol.
//
// Status text still reaches the operator: the firmware's primary bench interface
// is USB Serial, and every presentation_status() call site in the .ino already
// has a Serial.println() companion. Nothing is lost by discarding these here.
// =============================================================================

const char* presentation_backendName() { return "none"; }

bool presentation_init() { return true; }

void presentation_updateLive(const AudioFrame* frame) { (void)frame; }

void presentation_status(const char* msg) { (void)msg; }

void presentation_showResult(const MeasurementResult& result,
                             const InsightList& insights) {
    (void)result;
    (void)insights;
}

void presentation_showAborted(const char* reason) { (void)reason; }

void presentation_restoreLive() { }

void presentation_routerStatus() { }

void presentation_service() { }

void presentation_printDiagnostics() {
    Serial.println("[Link] No display backend compiled in (DISPLAY_TARGET_NONE).");
}


// =============================================================================
#else
// =============================================================================
  #error "DISPLAY_TARGET is not a recognised value. See config.h and docs/adr/ADR-001-display-architecture.md"
#endif
