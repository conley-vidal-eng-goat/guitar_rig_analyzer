// =============================================================================
// signal_router.h  —  Guitar Rig Analyzer
// =============================================================================
// Hardware signal routing: relay control, jack detection, and routing policy.
//
// OWNERSHIP
// ---------
// signal_router owns:
//   • Relay GPIO control (RELAY_SEND, RELAY_RETURN)
//   • Jack detection GPIO reads (4 jacks with debounce)
//   • Routing policy decisions (operator return selection, injection gating)
//   • Monitor mode state (future: SOURCE / RETURN / BLEND)
//   • Human-readable route description strings
//
// signal_router does NOT own:
//   • Audio capture hardware (audio_capture owns I2S, SGTL5000, mixers)
//   • Audio Library objects or connections
//   • Measurement state or decisions (measurement_engine decides when to arm)
//   • Display rendering (display_engine)
//   • Generator state (signal_generator owns DDS and synthesis objects)
//
// HOW ROUTING CHANGES PROPAGATE
// -----------------------------
// When the operator selects a different return source
// (signalRouter_setReturnSource()):
//   1. signal_router sets the relay GPIO(s)
//   2. signal_router calls audioEngine_setRoute(new_route)
//      → audioCap_notifyRouteChanged() programs mixers + latches ROUTE_CHANGED
//      → main loop sees ROUTE_CHANGED on next audioCap_update()
//      → main loop calls measurementEngine_notifyRouteChanged()
//      → measurement_engine aborts any in-progress capture
//
// signal_router does NOT call audio_capture or measurement_engine directly.
// It uses audioEngine_setRoute() as the single entry point, preserving the
// existing invalidation chain that the rest of the codebase depends on.
//
// INJECTION MODE
// ---------------
// When injection is enabled, audio_capture's output mixer (s_mixer_send)
// switches from SOURCE_NODE monitoring to generator output on I2S out L.
// The SGTL5000 line-out L then carries the generator signal, which reaches
// the Rig Send jack through RELAY_SEND (energised to position B).
//
// Injection is controlled explicitly — not by jack detection.
// measurement_engine calls signalRouter_setInjectionEnabled(true) at CAPTURE
// entry for internal-stimulus measurements, and false at CAPTURE exit.
// signal_router sets the relay and calls audioCap_setInjectionMode().
//
// RETURN SOURCE (ADR-004)
// ---------------
// The operator selects the return: TS or XLR. TS on every boot, never saved.
// Jack presence never chooses the return, drives RELAY_RETURN, or decides
// route validity.
//
// JACK DETECTION
// ---------------
// Informational only (ADR-003 / ADR-004). Polarity is per connector; see the
// JACK_*_DETECT_INVERTED block in config.h.
// Debounce: 50 ms minimum on all inputs.
//
// RELAY CONTROL
// ---------------
// Two SPDT relays, each controlled by one GPIO:
//   RELAY_SEND:   LOW = buffer output → Rig Send (normal)
//                 HIGH = codec line-out L → Rig Send (injection)
//   RELAY_RETURN: LOW = TS return → codec line-in R (default)
//                 HIGH = XLR return → codec line-in R
//
// Default power-on: both de-energised (normal signal path, TS return).
// Firmware establishes this in signalRouter_init(). Before that, pin 15 is in
// the MCU reset state, so the PHYSICAL power-on state depends on the relay
// driver's base pulldown. The RELAY_RETURN driver is not built yet: that is a
// Phase 7 bench requirement, not something this code proves.
// =============================================================================

#ifndef SIGNAL_ROUTER_H
#define SIGNAL_ROUTER_H

#include <Arduino.h>
#include "config.h"

// =============================================================================
// JACK DETECTION STATE
// =============================================================================
struct JackState {
    bool instrument_in;    // true = jack inserted in Instrument In
    bool rig_send;         // true = jack inserted in Rig Send
    bool return_ts;        // true = jack inserted in Rig Return TS
    bool return_xlr;       // true = jack inserted in Rig Return XLR
};

// =============================================================================
// RETURN SOURCE SELECTION
// =============================================================================
// Values are carried in protocol v2 ROUTER_STATUS (byte 1): do not renumber.
enum class ReturnSource : uint8_t {
    NONE = 0,   // Never produced under ADR-004. Kept for protocol compatibility.
    TS   = 1,   // 1/4" TS return selected (boot default)
    XLR  = 2,   // XLR return selected
};

// =============================================================================
// MONITOR MODE (Phase B — not implemented in v0.6.0)
// =============================================================================
// Controls what the player hears on the headphone output.
// In v0.6.0, monitoring is fixed:
//   Normal:    headphone L = SOURCE, headphone R = RETURN
//   Injection: headphone L = generator, headphone R = RETURN
enum class MonitorMode : uint8_t {
    SOURCE_RETURN = 0,   // L = source, R = return (default)
    RETURN_ONLY   = 1,   // Both channels = return (future)
    BLEND         = 2,   // Blended source + return on both (future)
};

// =============================================================================
// ROUTER STATUS — full snapshot of current routing state
// =============================================================================
struct RouterStatus {
    // RAW debounced detector readings. These are engineering observations and
    // are kept raw ON PURPOSE, so bring-up diagnostics can see actual pin
    // state. A reading here is NOT evidence of plug presence unless the
    // matching bit in detect_available is set.
    //
    // The wire contract is enforced at the presentation boundary, not here:
    // data_sender masks presence bits whose detector is unavailable. The raw
    // GPIO value is not "bad data" needing sanitising — it simply is not
    // evidence of presence when no detect hardware exists.
    JackState     jacks;

    // Which detectors physically exist in this build (config.h
    // JACK_*_DETECT_AVAILABLE). A hardware/build fact, constant at runtime.
    // Carried on the struct so every consumer sees the qualification attached
    // to the observation rather than having to remember to look it up.
    JackState     detect_available;

    // Operator-selected return source (ADR-004). Always TS or XLR.
    ReturnSource  return_source;

    // Whether generator injection is currently active
    bool          injection_active;

    // REMOVED FROM THE WIRE 2026-09-26 (TODO-58): route_valid and can_inject.
    //
    // route_valid was (selected_return != NONE). ADR-004 guarantees a selection
    // always exists, so it was a tautology — always true, fully recomputable
    // from return_source, and its name asserted physical connectivity it never
    // established.
    //
    // can_inject was route_valid && rig_send.debounced: a tautology AND an
    // unavailable detector. Its honest value today is UNKNOWN, and a Boolean
    // cannot carry that. Neither had any consumer — signalRouter_canInject()
    // and signalRouter_canMeasure() are defined and called nowhere.
    //
    // They remain on this struct for the two getters below and for bench
    // diagnostics; they are simply not transmitted. Injection readiness can
    // return to the wire when the Teensy can authoritatively establish it.
    bool          route_valid;
    bool          can_inject;

    // Human-readable description of current route
    // e.g. "TS return, no injection"  /  "XLR return, injection active"
    const char*   description;
};

// =============================================================================
// ROUTING EVENT — returned by signalRouter_update()
// =============================================================================
// Only one event per call. Highest priority returned first.
enum class RouterEvent : uint8_t {
    NONE            = 0,   // No change this iteration
    JACK_CHANGED    = 1,   // A jack was inserted or removed (debounced)
    ROUTE_CHANGED   = 2,   // Not returned by update() under ADR-004: return
                           // changes come from signalRouter_setReturnSource()
    ROUTE_INVALID   = 3,   // Unreachable under ADR-004. Kept for compatibility
};

// =============================================================================
// PUBLIC API
// =============================================================================

// -----------------------------------------------------------------------------
// signalRouter_init()
// Configure GPIO pins for relay control and jack detection.
// Sets relay defaults (both de-energised: normal path, TS return).
// Reads initial jack state. Call from setup() after audioCap_init().
// -----------------------------------------------------------------------------
void signalRouter_init();

// -----------------------------------------------------------------------------
// signalRouter_update()
// Call once per main loop iteration.
// Reads jack detect GPIOs (with debounce) and refreshes status. Jack state is
// informational: it never changes the return source or RELAY_RETURN (ADR-004).
// Still disables injection if Rig Send is removed while injecting.
//
// Returns NONE or JACK_CHANGED.
// -----------------------------------------------------------------------------
RouterEvent signalRouter_update();

// -----------------------------------------------------------------------------
// signalRouter_getStatus()
// Returns a const reference to the current routing status snapshot.
// Valid at any time after signalRouter_init().
// The returned reference is stable until the next signalRouter_update() call.
// -----------------------------------------------------------------------------
const RouterStatus& signalRouter_getStatus();

// -----------------------------------------------------------------------------
// signalRouter_getJacks()
// Returns the current debounced jack detection state.
// Convenience shortcut for signalRouter_getStatus().jacks.
// -----------------------------------------------------------------------------
JackState signalRouter_getJacks();

// -----------------------------------------------------------------------------
// signalRouter_canInject()
// Returns can_inject (route_valid && rig_send detected). Under ADR-004 this is
// effectively Rig Send presence, a requirement still under review (ADR-003).
// measurement_engine should check this before arming internal-stimulus
// measurements. If false, arm() should be rejected with a clear message.
// -----------------------------------------------------------------------------
bool signalRouter_canInject();

// -----------------------------------------------------------------------------
// signalRouter_canMeasure()
// Returns route_valid: the return routing configuration is defined (ADR-004).
// Does not establish physical return connectivity. Currently has no callers.
// For INTERNAL stimulus, also check signalRouter_canInject().
// -----------------------------------------------------------------------------
bool signalRouter_canMeasure();

// -----------------------------------------------------------------------------
// signalRouter_setInjectionEnabled(enabled)
// Enable or disable generator injection to Rig Send.
//
// When enabled:
//   1. RELAY_SEND set to position B (codec line-out → Rig Send)
//   2. audioCap_setInjectionMode(true) switches output mixer to generator
//   3. injection_active = true in RouterStatus
//
// When disabled:
//   1. RELAY_SEND set to position A (buffer → Rig Send, normal)
//   2. audioCap_setInjectionMode(false) restores SOURCE monitoring on output
//   3. injection_active = false in RouterStatus
//
// Called by measurement_engine:
//   - At CAPTURE entry for INTERNAL_* stimulus types: setInjectionEnabled(true)
//   - At CAPTURE exit (any path: completion, abort, cancel): setInjectionEnabled(false)
//
// Does NOT call audioEngine_setRoute() — injection mode change is handled
// through audioCap_setInjectionMode() which raises a ROUTE_CHANGED event
// via the same mechanism as audioCap_setInputGain().
//
// Guard: if rig_send is not detected, this function does nothing and returns
// false. The relay is not energised and injection_active stays false.
// Returns true if injection state was successfully changed.
// -----------------------------------------------------------------------------
bool signalRouter_setInjectionEnabled(bool enabled);

// -----------------------------------------------------------------------------
// signalRouter_setReturnSource(source)
// Operator return selection (ADR-004). The only way to change the return.
//
// TS / XLR accepted; NONE (or anything else) rejected → false.
// Unchanged selection: no-op, no relay write, no ROUTE_CHANGED → true.
// Changed selection: updates the selection, sets RELAY_RETURN, calls
//   audioEngine_setRoute() (→ ROUTE_CHANGED → any in-progress measurement
//   aborts), refreshes status → true. Not refused during a measurement.
// Returns false before signalRouter_init().
// -----------------------------------------------------------------------------
bool signalRouter_setReturnSource(ReturnSource source);

// -----------------------------------------------------------------------------
// signalRouter_setMonitorMode(mode)
// *** NOT YET IMPLEMENTED — reserved for Phase B (v0.6.1). ***
// Controls what the player hears on headphone output.
// Currently headphone output is fixed: L = SOURCE/generator, R = RETURN.
// Calling this function in v0.6.0 has no effect but stores the mode.
// -----------------------------------------------------------------------------
void signalRouter_setMonitorMode(MonitorMode mode);

#endif // SIGNAL_ROUTER_H
