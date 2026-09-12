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
//   • Routing policy decisions (return source selection, injection gating)
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
// When signal_router detects a jack change or receives a mode command:
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
// JACK DETECTION
// ---------------
// All detect inputs use active-LOW switches with internal pull-ups.
// GPIO LOW = jack inserted, GPIO HIGH = no jack.
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
enum class ReturnSource : uint8_t {
    NONE = 0,   // No return jack detected — route invalid for measurement
    TS   = 1,   // 1/4" TS return jack selected
    XLR  = 2,   // XLR return jack selected
};

// =============================================================================
// RETURN SOURCE PREFERENCE (user override)
// =============================================================================
// AUTO: signal_router decides based on jack detection (XLR preferred when both)
// TS / XLR: force a specific source regardless of what else is plugged in
//           (still requires the selected jack to actually be inserted)
enum class ReturnPreference : uint8_t {
    AUTO = 0,   // XLR preferred when both inserted; single jack always used
    TS   = 1,   // Force TS (ignored if TS jack not inserted)
    XLR  = 2,   // Force XLR (ignored if XLR jack not inserted)
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
    // Jack detection (debounced)
    JackState     jacks;

    // Active return source (result of policy + detect + preference)
    ReturnSource  return_source;

    // Whether generator injection is currently active
    bool          injection_active;

    // Whether the current route is valid for measurement
    // (requires at least one return source)
    bool          route_valid;

    // Whether the current route supports internal stimulus
    // (requires rig_send jack + return source)
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
    ROUTE_CHANGED   = 2,   // Active return source or injection state changed
                           // (audioEngine_setRoute already called by signal_router)
    ROUTE_INVALID   = 3,   // A required jack was removed; route is now invalid
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
// Reads jack detect GPIOs (with debounce). If any detect state changed,
// recomputes routing policy and updates relays if needed. If the active
// return source changes, calls audioEngine_setRoute() to propagate the
// change through the existing invalidation chain.
//
// Returns a RouterEvent describing what changed (if anything).
// The main loop should log JACK_CHANGED and ROUTE_INVALID events.
// ROUTE_CHANGED events are already handled by the audioEngine_setRoute →
// audioCap_notifyRouteChanged → ROUTE_CHANGED event chain.
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
// Returns true if the current jack state supports generator injection:
//   rig_send jack must be inserted AND at least one return jack inserted.
// measurement_engine should check this before arming internal-stimulus
// measurements. If false, arm() should be rejected with a clear message.
// -----------------------------------------------------------------------------
bool signalRouter_canInject();

// -----------------------------------------------------------------------------
// signalRouter_canMeasure()
// Returns true if the current jack state supports any measurement:
//   at least one return jack (TS or XLR) must be inserted.
// For EXTERNAL stimulus, this is the only requirement.
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
// signalRouter_setReturnPreference(pref)
// Set the user's return source preference. Takes effect on the next
// signalRouter_update() call if both TS and XLR are inserted.
//
// AUTO: XLR preferred when both inserted (default).
// TS:   Force TS return (if TS jack is inserted).
// XLR:  Force XLR return (if XLR jack is inserted).
//
// If the preferred jack is not inserted, the other is used automatically.
// If neither is inserted, return_source = NONE regardless of preference.
// -----------------------------------------------------------------------------
void signalRouter_setReturnPreference(ReturnPreference pref);

// -----------------------------------------------------------------------------
// signalRouter_setMonitorMode(mode)
// *** NOT YET IMPLEMENTED — reserved for Phase B (v0.6.1). ***
// Controls what the player hears on headphone output.
// Currently headphone output is fixed: L = SOURCE/generator, R = RETURN.
// Calling this function in v0.6.0 has no effect but stores the mode.
// -----------------------------------------------------------------------------
void signalRouter_setMonitorMode(MonitorMode mode);

#endif // SIGNAL_ROUTER_H
