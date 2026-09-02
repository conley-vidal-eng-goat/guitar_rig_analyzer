// =============================================================================
// SIGNAL ROUTER — GPIO PIN ASSIGNMENTS  (v0.6.0)
// =============================================================================
// These constants define the Teensy 4.1 GPIO pins used by signal_router
// for relay control and jack detection.
//
// PIN SELECTION RATIONALE:
// Pins 0–7 are used: 7 is I2S LRCLK (Audio Shield), 8–10 are RA8875.
// Pins 11–13 are SPI. Pins 18–19 are I2C (SGTL5000 control).
// Pins 20–21 and 23 are I2S data/clock (Audio Shield).
//
// We use pins in the 14–17 and 22+ range which are free on a standard
// Teensy 4.1 + Audio Shield + RA8875 setup.
//
// *** ADJUST THESE TO MATCH YOUR PCB LAYOUT ***
// All pin numbers are Teensy 4.1 digital pin numbers.
// -----------------------------------------------------------------------------

// --- Relay control (output, active HIGH energises relay coil via driver) ---
#define RELAY_SEND_PIN       14   // RELAY_SEND:   LOW=buffer→RigSend, HIGH=codec→RigSend
#define RELAY_RETURN_PIN     15   // RELAY_RETURN: LOW=TS→codec,       HIGH=XLR→codec

// --- Jack detection (input, active LOW with internal pull-up) ---
// LOW = jack inserted, HIGH = no jack.
#define JACK_INSTRUMENT_PIN  16   // Instrument In jack detect
#define JACK_RIG_SEND_PIN    17   // Rig Send jack detect
#define JACK_RETURN_TS_PIN   22   // Rig Return TS jack detect
#define JACK_RETURN_XLR_PIN  24   // Rig Return XLR jack detect

// --- Debounce timing ---
#define JACK_DEBOUNCE_MS     50   // Minimum stable time before accepting a state change
