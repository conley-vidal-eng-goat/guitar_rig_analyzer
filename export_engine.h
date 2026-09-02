// =============================================================================
// export_engine.h       —   Guitar Rig Analyzer   v0.5.0
// =============================================================================
// Owner of all durable file output for the guitar rig analyzer.
//
// OWNERSHIP
// ---------
// export_engine owns:
//     • Writing MeasurementResult as a JSON fingerprint to SD
//     • Writing baseline TF CSV (for cable reference and bench characterisation)
//     • Writing validation run logs
//     • Generating unique filenames when no name is specified
//
// export_engine does NOT own:
//     • The MeasurementResult itself (measurement_engine owns that)
//     • Calibration files (calibration_store owns those)
//     • When to export (measurement_engine and main loop decide that)
//
// JSON FINGERPRINT FORMAT
// -----------------------
// Files are written with extension ".json" to the SD root (or a subdirectory
// defined by EXPORT_DIR_DEFAULT in config.h).
//
// Top-level structure:
// {
//     "schema": 1,
//     "firmware": "0.5.0",
//     "timestamp_ms": 12345678,
//     "capture_blocks": { "start": N, "end": M },
//     "frames": 32,
//     "fft_size": 1024,
//     "fft_mode": "LIVE",
//     "window": "HANN",
//     "estimator": "H1",
//     "stimulus": "EXTERNAL",
//     "quality": "GOOD",
//     "mean_coherence": 0.923,
//     "valid_bin_fraction": 0.881,
//     "clip_detected": false,
//     "source_ch": 0,
//     "return_ch": 1,
//     "line_in_level": 5,
//     "calibration": {
//       "applied": true,
//          "provenance": "bench loopback",
//          "warnings": {
//              "missing": false,
//              "level_mismatch": false,
//              "partial": false,
//              "imported": false
//          }
//     },
//     "bins": 512,
//     "hz": [ 0.0, 43.1, 86.1, ... 512 floats ... ],
//     "S_xx_db":              [ ... 512 floats ... ],
//     "S_yy_db":              [ ... 512 floats ... ],
//     "coherence":            [ ... 512 floats ... ],
//     "tf_raw_mag_db":        [ ... 512 floats ... ],
//     "tf_cal_mag_db":        [ ... 512 floats ... ],
//     "tf_cal_phase_rad":[ ... 512 floats ... ],
//     "group_delay_ms":       [ ... 512 floats ... ]
// }
//
// MEMORY MODEL
// ------------
// No dynamic allocation. JSON is written to SD incrementally using a small
// stack buffer (EXPORT_WRITE_BUF_SIZE bytes, defined in config.h).
// A write buffer is flushed when full or when a newline is emitted.
// The entire result file is never held in RAM simultaneously — the largest
// per-call stack use is the write buffer.
//
// FILE NAMING
// -----------
// If filename is NULL or empty, the engine generates a name of the form:
//     "r_<timestamp_ms_hex>.json"
// e.g. "r_00B71B00.json"
// This guarantees uniqueness (timestamp_ms advances monotonically) with short names.
// =============================================================================


#ifndef EXPORT_ENGINE_H
#define EXPORT_ENGINE_H


#include <Arduino.h>
#include "config.h"
#include "measurement_core.h"


// =============================================================================
// PUBLIC API
// =============================================================================


// -----------------------------------------------------------------------------
// exportEngine_init()
// Initialise the export engine. Checks SD availability and creates the
// export directory (EXPORT_DIR_DEFAULT) if it does not exist.
// Returns true if SD is available and ready. Returns false if SD is absent —
// export functions will fail gracefully but the device continues operating.
// Call from setup() after SD is initialised.
// -----------------------------------------------------------------------------
bool exportEngine_init();


// -----------------------------------------------------------------------------
// exportEngine_saveMeasurement(result, filename)
// Serialise a MeasurementResult to SD as a JSON fingerprint.
//
// If filename is NULL or empty, a unique name is generated from
// result.timestamp_ms (hex). The actual filename used is written into
// filename_out (if non-NULL, must be at least EXPORT_FILENAME_LEN bytes).
//
// Returns true on success; false if SD write fails.
// Does not modify the result or require any specific measurement state.
// Can be called from any context after RESULT state is entered.
// -----------------------------------------------------------------------------
bool exportEngine_saveMeasurement(const MeasurementResult& result,
                                     const char*             filename,
                                     char*                   filename_out);


// -----------------------------------------------------------------------------
// exportEngine_saveBaselineCSV(result, filename)
// Write the transfer function as a three-column CSV file:
//   hz, tf_cal_mag_db, coherence
// One row per FFT bin. Suitable for import into Excel, MATLAB, or REW.
//
// Used for cable characterisation reference after a flat loopback run.
// If filename is NULL, generates a name of the form "b_<timestamp_hex>.csv".
// -----------------------------------------------------------------------------
bool exportEngine_saveBaselineCSV(const MeasurementResult& result,
                                      const char*             filename);


// -----------------------------------------------------------------------------
// exportEngine_isAvailable()
// Returns true if SD is available and the export engine initialised successfully.
// Check this before calling save functions if SD absence is expected.
// -----------------------------------------------------------------------------
bool exportEngine_isAvailable();


// Maximum filename length for generated names (including null terminator)
#define EXPORT_FILENAME_LEN     32
#endif // EXPORT_ENGINE_H
