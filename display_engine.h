// =============================================================================
// display_engine.h    —   Guitar Rig Analyzer   v0.5.0
// =============================================================================
// Public interface for the display engine.
//
// CHANGELOG v0.2.1 (last functional change — no logic changes since)
// ----------------
// • Comments use SOURCE_NODE / RETURN_NODE language throughout. The display
//   engine does not care about physical channel numbers — it reads AudioFrame
//   structs which already carry node-level data (fft_source = SOURCE_NODE FFT,
//   fft_return = RETURN_NODE FFT). No code changes; language only.
// • displayEngine_update() now acknowledges frame->tf_persistence_active in
//   its contract description — it uses tf_confidence for the LOW SIGNAL warning,
//   and tf_persistence_active is available for future annotation (e.g. a subtle
//   indicator that the curve contains preserved history, not all live data).
//
// RENDERING MODEL (static chrome + erase/redraw live elements)
// ------------------------------------------------------------
// Static chrome: panel borders, grid lines, axis labels, panel titles.
//   Drawn ONCE in displayEngine_init(). Never redrawn under normal operation.
//
// Live elements: spectrum curves, RIG CHANGE curve, level meters, warnings.
//   Updated each call to displayEngine_update(). Old curves are erased by
//   redrawing them in background colour before drawing the new curves.
//
// Known limitation: the erase/redraw strategy works correctly only for
// single-pixel-wide lines. Thicker lines, filled areas, or overlapping
// annotations will require switching to a per-panel fillRect erase before
// redraw. This is documented here so future contributors know the boundary
// before adding new visual elements.
// =============================================================================


#ifndef DISPLAY_ENGINE_H
#define DISPLAY_ENGINE_H


#include <Arduino.h>
#include "config.h"
#include "audio_engine.h"
#include "measurement_core.h"     // MeasurementResult
#include "insights_engine.h"       // InsightList


// -----------------------------------------------------------------------------
// displayEngine_init()
// Initialise RA8875 over SPI, draw static screen layout.
// Returns true on success, false if RA8875 does not respond.
// Call once from setup(), after audioEngine_init().
// -----------------------------------------------------------------------------
bool displayEngine_init();


// -----------------------------------------------------------------------------
// displayEngine_update(frame)
// Redraw all live display elements from data in *frame:
//   • Level meters (SOURCE_NODE and RETURN_NODE peak levels)
//   • Spectrum overlay (SOURCE_NODE and RETURN_NODE averaged FFT curves)
//   • RIG CHANGE curve (transfer function H_dB[] with NAN gap handling)
//   • LOW SIGNAL confidence warning (shown/hidden based on tf_confidence)
//
// frame->tf_persistence_active is available for future use (e.g. to draw a
// subtle indicator that some curve portions contain preserved EMA history
// rather than live measurements). Currently unused in the display logic.
//
// Static chrome is not redrawn. Call every output block or every N blocks
// per DISPLAY_UPDATE_EVERY_N_FRAMES in config.h.
// -----------------------------------------------------------------------------
void displayEngine_update(const AudioFrame* frame);


// -----------------------------------------------------------------------------
// displayEngine_drawStatusMessage(msg)
// Writes a short status string (~40 chars max) in the centre of the meter
// panel (top band). Does not affect spectrum or RIG CHANGE panels.
// Overwrites any previous message. Used for startup, clipping warnings,
// calibration prompts, and route change notifications.
// -----------------------------------------------------------------------------
void displayEngine_drawStatusMessage(const char* msg);


// -----------------------------------------------------------------------------
// displayEngine_showResult(result, insights)
// Transition from live view to result view. Clears the spectrum panel,
// draws the measured tf_cal_mag_db[] curve in the RIG CHANGE panel (with NaN
// gap handling), renders the InsightList in the reclaimed spectrum panel area,
// and updates the meter panel with quality grade and calibration status.
//
// The RIG CHANGE panel chrome (grid, 0 dB line, freq labels) is redrawn so
// the result curve sits on clean chrome. The spectrum panel chrome is replaced
// by the insight list. Call once on MeasurementEvent::RESULT_READY.
// -----------------------------------------------------------------------------
void displayEngine_showResult(const MeasurementResult& result,
                                 const InsightList& insights);


// -----------------------------------------------------------------------------
// displayEngine_showAborted(reason)
// Show abort messaging in the meter panel. Does not clear other panels so
// the partial spectra remain visible for context. Call on ABORTED event.
// -----------------------------------------------------------------------------
void displayEngine_showAborted(const char* reason);


// -----------------------------------------------------------------------------
// displayEngine_restoreLive()
// Transition back from result/aborted view to live view.
// Redraws spectrum chrome, clears the insight panel, clears the TF curve,
// redraws TF chrome, and resets the live-update erase buffers.
// The next call to displayEngine_update() will draw fresh live curves.
// -----------------------------------------------------------------------------
void displayEngine_restoreLive();


#endif // DISPLAY_ENGINE_H
