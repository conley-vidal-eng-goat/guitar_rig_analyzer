// =============================================================================
// signal_router.cpp  —  Guitar Rig Analyzer
// =============================================================================
// Hardware signal routing: relay control, jack detection, and routing policy.
//
// This module owns the physical routing hardware (relays and jack-detect
// switches) and makes routing policy decisions. It does NOT own any Audio
// Library objects, codec registers, or measurement state.
//
// See signal_router.h for the full ownership contract, propagation model,
// and the input-route vs output-path asymmetry documentation.
//
// IMPLEMENTATION NOTES
// --------------------
// Jack debounce: each jack has a raw GPIO state, a debounced state, and a
// timestamp of the last raw-state change. A debounced transition is accepted
// only after the raw state has been stable for JACK_DEBOUNCE_MS.
//
// Relay control: relays are driven by a single GPIO each (active HIGH via
// a driver transistor or MOSFET on the PCB). Default power-on state is
// de-energised (GPIO LOW), which selects the safe default path:
//   RELAY_SEND:   buffer output → Rig Send (normal instrument signal)
//   RELAY_RETURN: TS return → codec line-in R
//
// Route description strings are built from a static buffer to avoid heap
// allocation. The buffer is stable between signalRouter_update() calls.
// =============================================================================

#include "signal_router.h"
#include "audio_engine.h"      // for audioEngine_setRoute()
#include "audio_capture.h"     // for audioCap_setInjectionMode()

// =============================================================================
// MODULE-PRIVATE STATE
// =============================================================================

// --- Debounced jack state ---
struct JackDebounce {
    bool     raw;              // Last GPIO reading
    bool     debounced;        // Accepted stable state
    uint32_t last_change_ms;   // millis() at last raw transition
};

static JackDebounce s_jack_instrument;
static JackDebounce s_jack_rig_send;
static JackDebounce s_jack_return_ts;
static JackDebounce s_jack_return_xlr;

// --- Routing state ---
static ReturnSource     s_return_source  = ReturnSource::NONE;
static ReturnPreference s_return_pref    = ReturnPreference::AUTO;
static MonitorMode      s_monitor_mode   = MonitorMode::SOURCE_RETURN;
static bool             s_injection_active = false;

// --- Status snapshot (returned by getStatus) ---
static RouterStatus s_status;

// --- Route description buffer ---
static char s_description[64];

// --- Initialisation guard ---
static bool s_initialised = false;

// =============================================================================
// PRIVATE HELPERS
// =============================================================================

// Read a jack-detect GPIO.
//
// The un-inverted convention is active LOW: LOW = inserted, HIGH = not inserted
// (a switch closing to ground when a plug goes in). Connectors whose switch does
// the opposite pass inverted = true; see the JACK_*_DETECT_INVERTED block in
// config.h for which connectors those are and why they are per-connector.
//
// Polarity lives HERE and nowhere else. It is deliberately not folded into
// pinMode, not applied at the call sites, and not baked into the debounce state,
// so there is exactly one place to look when a sense convention is wrong.
static inline bool readJackInserted(uint8_t pin, bool inverted) {
    const bool raw_present = (digitalRead(pin) == LOW);
    return raw_present ^ inverted;
}

// Raw pin level, for diagnostics only. Never used for routing decisions --
// this exists so a bench test can record the raw GPIO state alongside the
// interpreted state and prove the inversion is doing what it claims.
static inline int readJackRawLevel(uint8_t pin) {
    return digitalRead(pin);
}

// Print raw GPIO level beside the interpreted "present" state for all four
// detect inputs. This is the evidence format the Phase 5 bench test needs:
// raw pin state AND interpreted state, for both empty and inserted conditions,
// so the inversion can be shown to be correct rather than assumed.
static void logJackDetail(const char* tag) {
    Serial.printf("[SignalRouter] detail(%s)  "
                  "instrument pin%-2d raw=%s inv=%d present=%d | "
                  "send pin%-2d raw=%s inv=%d present=%d | "
                  "ts pin%-2d raw=%s inv=%d present=%d | "
                  "xlr pin%-2d raw=%s inv=%d present=%d\n",
        tag,
        JACK_INSTRUMENT_PIN, readJackRawLevel(JACK_INSTRUMENT_PIN) ? "HIGH" : "LOW ",
        (int)JACK_INSTRUMENT_DETECT_INVERTED, s_jack_instrument.debounced,
        JACK_RIG_SEND_PIN,   readJackRawLevel(JACK_RIG_SEND_PIN)   ? "HIGH" : "LOW ",
        (int)JACK_RIG_SEND_DETECT_INVERTED,   s_jack_rig_send.debounced,
        JACK_RETURN_TS_PIN,  readJackRawLevel(JACK_RETURN_TS_PIN)  ? "HIGH" : "LOW ",
        (int)JACK_RETURN_TS_DETECT_INVERTED,  s_jack_return_ts.debounced,
        JACK_RETURN_XLR_PIN, readJackRawLevel(JACK_RETURN_XLR_PIN) ? "HIGH" : "LOW ",
        (int)JACK_RETURN_XLR_DETECT_INVERTED, s_jack_return_xlr.debounced);
}

// Update debounce state for one jack. Returns true if debounced state changed.
static bool updateDebounce(JackDebounce* j, uint8_t pin, bool inverted) {
    bool current_raw = readJackInserted(pin, inverted);
    uint32_t now = millis();

    if (current_raw != j->raw) {
        // Raw state changed — reset the debounce timer
        j->raw = current_raw;
        j->last_change_ms = now;
        return false;   // Not yet stable
    }

    // Raw state is unchanged. Has it been stable long enough?
    if (j->debounced != j->raw && (now - j->last_change_ms) >= JACK_DEBOUNCE_MS) {
        j->debounced = j->raw;
        return true;    // Debounced state just transitioned
    }

    return false;   // No change
}

// Apply the return source policy based on current debounced jack state
// and user preference. Returns the selected ReturnSource.
static ReturnSource computeReturnSource() {
    bool ts  = s_jack_return_ts.debounced;
    bool xlr = s_jack_return_xlr.debounced;

    if (!ts && !xlr) return ReturnSource::NONE;
    if (ts && !xlr)  return ReturnSource::TS;
    if (!ts && xlr)  return ReturnSource::XLR;

    // Both inserted — apply preference
    switch (s_return_pref) {
        case ReturnPreference::TS:   return ReturnSource::TS;
        case ReturnPreference::XLR:  return ReturnSource::XLR;
        case ReturnPreference::AUTO:
        default:                     return ReturnSource::XLR;  // XLR preferred
    }
}

// Set the RELAY_RETURN GPIO based on the selected return source.
static void applyReturnRelay(ReturnSource source) {
    switch (source) {
        case ReturnSource::XLR:
            digitalWrite(RELAY_RETURN_PIN, HIGH);  // Position B: XLR → codec
            break;
        case ReturnSource::TS:
        case ReturnSource::NONE:
        default:
            digitalWrite(RELAY_RETURN_PIN, LOW);   // Position A: TS → codec (default)
            break;
    }
}

// Build a human-readable route description string.
static void buildDescription() {
    const char* ret_str =
        (s_return_source == ReturnSource::TS)  ? "TS return" :
        (s_return_source == ReturnSource::XLR) ? "XLR return" :
                                                  "no return";

    const char* inj_str = s_injection_active ? ", injection active" : ", no injection";

    snprintf(s_description, sizeof(s_description), "%s%s", ret_str, inj_str);
}

// Update the RouterStatus snapshot from current state.
static void updateStatus() {
    s_status.jacks.instrument_in = s_jack_instrument.debounced;
    s_status.jacks.rig_send      = s_jack_rig_send.debounced;
    s_status.jacks.return_ts     = s_jack_return_ts.debounced;
    s_status.jacks.return_xlr    = s_jack_return_xlr.debounced;

    s_status.return_source    = s_return_source;
    s_status.injection_active = s_injection_active;
    s_status.route_valid      = (s_return_source != ReturnSource::NONE);
    s_status.can_inject       = s_status.route_valid && s_jack_rig_send.debounced;

    buildDescription();
    s_status.description = s_description;
}

// =============================================================================
// PUBLIC FUNCTION IMPLEMENTATIONS
// =============================================================================

// -----------------------------------------------------------------------------
// signalRouter_init()
// -----------------------------------------------------------------------------
void signalRouter_init() {
    // Configure relay GPIOs as outputs, default de-energised (LOW)
    pinMode(RELAY_SEND_PIN,   OUTPUT);
    pinMode(RELAY_RETURN_PIN, OUTPUT);
    digitalWrite(RELAY_SEND_PIN,   LOW);   // Buffer → Rig Send (safe default)
    digitalWrite(RELAY_RETURN_PIN, LOW);   // TS return → codec (default)

    // Configure jack detect GPIOs as inputs with internal pull-up.
    // Active LOW: switch closes to ground when jack is inserted.
    pinMode(JACK_INSTRUMENT_PIN, INPUT_PULLUP);
    pinMode(JACK_RIG_SEND_PIN,   INPUT_PULLUP);
    pinMode(JACK_RETURN_TS_PIN,  INPUT_PULLUP);
    pinMode(JACK_RETURN_XLR_PIN, INPUT_PULLUP);

    // Read initial jack state — treat as already debounced (device just powered up)
    uint32_t now = millis();

    s_jack_instrument = { readJackInserted(JACK_INSTRUMENT_PIN, JACK_INSTRUMENT_DETECT_INVERTED),
                          readJackInserted(JACK_INSTRUMENT_PIN, JACK_INSTRUMENT_DETECT_INVERTED), now };
    s_jack_rig_send   = { readJackInserted(JACK_RIG_SEND_PIN,   JACK_RIG_SEND_DETECT_INVERTED),
                          readJackInserted(JACK_RIG_SEND_PIN,   JACK_RIG_SEND_DETECT_INVERTED),   now };
    s_jack_return_ts  = { readJackInserted(JACK_RETURN_TS_PIN,  JACK_RETURN_TS_DETECT_INVERTED),
                          readJackInserted(JACK_RETURN_TS_PIN,  JACK_RETURN_TS_DETECT_INVERTED),  now };
    s_jack_return_xlr = { readJackInserted(JACK_RETURN_XLR_PIN, JACK_RETURN_XLR_DETECT_INVERTED),
                          readJackInserted(JACK_RETURN_XLR_PIN, JACK_RETURN_XLR_DETECT_INVERTED), now };

    // Initialise routing state from current jack state
    s_return_source    = computeReturnSource();
    s_return_pref      = ReturnPreference::AUTO;
    s_injection_active = false;
    s_monitor_mode     = MonitorMode::SOURCE_RETURN;

    // Apply initial relay positions
    applyReturnRelay(s_return_source);
    // RELAY_SEND is already LOW (buffer, non-injection) from the GPIO init above

    // Build initial status
    updateStatus();
    s_initialised = true;

    Serial.println("[SignalRouter] Initialised.");
    Serial.printf("[SignalRouter] Jacks: instrument=%d send=%d return_ts=%d return_xlr=%d\n",
                  s_jack_instrument.debounced, s_jack_rig_send.debounced,
                  s_jack_return_ts.debounced, s_jack_return_xlr.debounced);
    logJackDetail("init");
    Serial.printf("[SignalRouter] Return source: %s\n",
                  s_return_source == ReturnSource::TS  ? "TS" :
                  s_return_source == ReturnSource::XLR ? "XLR" : "NONE");
    Serial.printf("[SignalRouter] Route: %s\n", s_description);
}

// -----------------------------------------------------------------------------
// signalRouter_update()
// -----------------------------------------------------------------------------
RouterEvent signalRouter_update() {
    if (!s_initialised) return RouterEvent::NONE;

    // Debounce all four jack detect inputs
    bool any_changed = false;
    any_changed |= updateDebounce(&s_jack_instrument, JACK_INSTRUMENT_PIN, JACK_INSTRUMENT_DETECT_INVERTED);
    any_changed |= updateDebounce(&s_jack_rig_send,   JACK_RIG_SEND_PIN,   JACK_RIG_SEND_DETECT_INVERTED);
    any_changed |= updateDebounce(&s_jack_return_ts,  JACK_RETURN_TS_PIN,  JACK_RETURN_TS_DETECT_INVERTED);
    any_changed |= updateDebounce(&s_jack_return_xlr, JACK_RETURN_XLR_PIN, JACK_RETURN_XLR_DETECT_INVERTED);

    if (!any_changed) {
        return RouterEvent::NONE;
    }

    // A jack state changed — recompute return source
    ReturnSource new_source = computeReturnSource();
    bool source_changed = (new_source != s_return_source);

    // Check if a required jack was removed
    bool was_valid = (s_return_source != ReturnSource::NONE);
    bool now_valid = (new_source != ReturnSource::NONE);

    // Check if injection path was broken (rig_send removed while injecting)
    if (s_injection_active && !s_jack_rig_send.debounced) {
        // Rig Send jack removed during injection — disable injection immediately.
        // The relay goes to safe default, mixer goes to SOURCE monitoring.
        // This is a safety measure; measurement_engine will also abort via
        // ROUTE_CHANGED from the return-source change if applicable.
        digitalWrite(RELAY_SEND_PIN, LOW);
        #if ENABLE_DUT_INJECTION
audioCap_setInjectionMode(false);
#endif
        s_injection_active = false;
        Serial.println("[SignalRouter] WARNING: Rig Send removed during injection — "
                       "injection disabled.");
    }

    s_return_source = new_source;

    if (source_changed) {
        // Apply relay change
        applyReturnRelay(new_source);

        // Propagate input route change through the standard invalidation chain.
        // This is the ONLY place signal_router calls audioEngine_setRoute().
        // It triggers: audioCap_notifyRouteChanged() → ROUTE_CHANGED event →
        //              main loop → measurementEngine_notifyRouteChanged()
        SignalRoute new_route = {
            SOURCE_NODE_PHYSICAL_CH,
            RETURN_NODE_PHYSICAL_CH,
            s_description   // will be rebuilt below, but description is stable
        };
        buildDescription();
        new_route.description = s_description;
        audioEngine_setRoute(new_route);

        Serial.printf("[SignalRouter] Return source changed: %s\n",
                      new_source == ReturnSource::TS  ? "TS" :
                      new_source == ReturnSource::XLR ? "XLR" : "NONE");
    }

    // Update status snapshot
    updateStatus();

    Serial.printf("[SignalRouter] Jack change: instrument=%d send=%d ts=%d xlr=%d → %s\n",
                  s_jack_instrument.debounced, s_jack_rig_send.debounced,
                  s_jack_return_ts.debounced, s_jack_return_xlr.debounced,
                  s_description);
    logJackDetail("change");

    // Determine the most important event to return
    if (was_valid && !now_valid) {
        return RouterEvent::ROUTE_INVALID;
    }
    if (source_changed) {
        return RouterEvent::ROUTE_CHANGED;
    }
    return RouterEvent::JACK_CHANGED;
}

// -----------------------------------------------------------------------------
// signalRouter_getStatus()
// -----------------------------------------------------------------------------
const RouterStatus& signalRouter_getStatus() {
    return s_status;
}

// -----------------------------------------------------------------------------
// signalRouter_getJacks()
// -----------------------------------------------------------------------------
JackState signalRouter_getJacks() {
    return s_status.jacks;
}

// -----------------------------------------------------------------------------
// signalRouter_canInject()
// -----------------------------------------------------------------------------
bool signalRouter_canInject() {
    return s_status.can_inject;
}

// -----------------------------------------------------------------------------
// signalRouter_canMeasure()
// -----------------------------------------------------------------------------
bool signalRouter_canMeasure() {
    return s_status.route_valid;
}

// -----------------------------------------------------------------------------
// signalRouter_setInjectionEnabled(enabled)
// -----------------------------------------------------------------------------
bool signalRouter_setInjectionEnabled(bool enabled) {
    if (enabled) {
        // Guard: reject if rig_send is not inserted
        if (!s_jack_rig_send.debounced) {
            Serial.println("[SignalRouter] setInjectionEnabled(true) rejected: "
                           "Rig Send jack not inserted.");
            return false;
        }

        // Set relay to codec-out position and switch output mixer to generator
        digitalWrite(RELAY_SEND_PIN, HIGH);
        #if ENABLE_DUT_INJECTION
    audioCap_setInjectionMode(true);
#endif
        s_injection_active = true;

        Serial.println("[SignalRouter] Injection enabled: generator → Rig Send.");
    } else {
        // Restore relay to buffer position and switch output mixer to SOURCE
        digitalWrite(RELAY_SEND_PIN, LOW);
        #if ENABLE_DUT_INJECTION
audioCap_setInjectionMode(false);
#endif
        s_injection_active = false;

        Serial.println("[SignalRouter] Injection disabled: buffer → Rig Send.");
    }

    updateStatus();
    return true;
}

// -----------------------------------------------------------------------------
// signalRouter_setReturnPreference(pref)
// -----------------------------------------------------------------------------
void signalRouter_setReturnPreference(ReturnPreference pref) {
    if (s_return_pref == pref) return;
    s_return_pref = pref;
    Serial.printf("[SignalRouter] Return preference set to %s\n",
                  pref == ReturnPreference::TS   ? "TS" :
                  pref == ReturnPreference::XLR  ? "XLR" : "AUTO");
    // The preference takes effect on the next signalRouter_update() if both
    // jacks are inserted. We do not immediately change the relay here because
    // the debounce state may be mid-transition.
}

// -----------------------------------------------------------------------------
// signalRouter_setMonitorMode(mode)
// *** NOT YET IMPLEMENTED — reserved for Phase B (v0.6.1). ***
// Stores the mode but does not change any mixer gains.
// -----------------------------------------------------------------------------
void signalRouter_setMonitorMode(MonitorMode mode) {
    s_monitor_mode = mode;
    Serial.printf("[SignalRouter] Monitor mode set to %d (not yet implemented).\n",
                  (int)mode);
}
