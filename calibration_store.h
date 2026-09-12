// =============================================================================
// calibration_store.h     —     Guitar Rig Analyzer
// =============================================================================
// Owner of the resident CalibrationBuffer and all calibration file I/O.
//
// OWNERSHIP
// ---------
// calibration_store owns:
//   • The one resident CalibrationBuffer in DTCM
//   • All calibration file load/save operations on SD
//   • Calibration validity decisions (VALID / SOFT_MISMATCH / HARD_MISMATCH)
//   • The provenance description string
//
// calibration_store does NOT own:
//   • When to apply calibration (measurement_engine decides)
//   • The measurement that created the calibration (that is MeasurementResult)
//   • Triggering measurements (the UI/main loop does that)
//
// CALIBRATION FILE FORMAT
// -----------------------
// Binary flat file, extension ".cal":
//
//   Bytes 0–3:       Magic number     0x52494743   ("RIGC")
//   Bytes 4–5:       Schema version     (uint16, currently 1)
//   Bytes 6:         FftMode            (uint8)
//   Bytes 7–8:       fft_size           (uint16)
//   Bytes 9–12:      sample_rate        (uint32)
//   Bytes 13:        window_function (uint8)
//   Bytes 14:        line_in_level      (uint8)
//   Bytes 15:        cal_type           (uint8)
//   Bytes 16–19:     capture_timestamp_ms (uint32)
//   Bytes 20–65:     description[46] (char, null-padded)
//   Bytes 66–2113:     cal_mag_db[512]       (float32[512])
//   Bytes 2114–4161: cal_phase_rad[512] (float32[512])
//   Bytes 4162–4673: bin_valid[512]           (uint8[512], 1=valid 0=invalid)
//   Bytes 4674–4677: CRC-32 of bytes 0–4673
//
// Total file size: 4678 bytes.
//
// The CRC-32 uses the standard polynomial (0xEDB88320).
// A file with a bad CRC is rejected — load returns false and the
// previous resident buffer state is preserved (not zeroed to MISSING).
//
// HARD vs SOFT MISMATCH RULES
// ---------------------------
// HARD mismatch (calibration NOT applied):
//   • fft_size differs from the current measurement's FFT size
//   • sample_rate differs from SAMPLE_RATE in config.h
//   • window_function differs from the measurement's window function
//   These mismatches cause systematic per-bin errors that cannot be corrected.
//
// SOFT mismatch (calibration applied with warning):
//   • line_in_level differs by 1–2 steps
//     The phase correction is still valid; the magnitude correction is
//     approximate (off by the PGA gain difference, ~1.5 dB per step).
//   • A MODE_PRECISION calibration applied to a MODE_LIVE measurement
//     (calibration has higher resolution than the measurement — conservative,
//     not mathematically wrong).
//
// MODE_LIVE calibration applied to MODE_PRECISION measurement is a HARD
// mismatch — the calibration lacks the per-bin accuracy the measurement expects.
// =============================================================================


#ifndef CALIBRATION_STORE_H
#define CALIBRATION_STORE_H


#include <Arduino.h>
#include "config.h"
#include "measurement_core.h"


// =============================================================================
// PUBLIC API
// =============================================================================


// -----------------------------------------------------------------------------
// calStore_init()
// Initialise the calibration store. Attempts to load the default calibration
// file from SD (path defined by CAL_FILE_DEFAULT in config.h). If the file
// does not exist or fails its CRC check, the store starts with no calibration
// (CalibrationBuffer.loaded = false) and a warning is printed to Serial.
//
// Call from setup() after audioCap_init(). SD must be available.
// Does not halt the device if no calibration is found.
// -----------------------------------------------------------------------------
void calStore_init();


// -----------------------------------------------------------------------------
// calStore_load(filename)
// Loads a calibration file from SD into the resident CalibrationBuffer.
// Validates magic number, schema version, and CRC-32 before accepting.
// Returns true on success; false on any validation failure.
// On failure, the previous buffer state is preserved.
// -----------------------------------------------------------------------------
bool calStore_load(const char* filename);


// -----------------------------------------------------------------------------
// calStore_saveFromResult(result, filename, description)
// Saves a new calibration file to SD from a completed MeasurementResult.
// The result must have been a flat loopback measurement (no DUT in signal path).
// Bins where result.coherence[k] < CAL_MIN_COHERENCE_FOR_BIN are marked
// bin_valid=false in the saved file and are excluded from correction.
//
// Also loads the saved calibration as the new resident buffer.
// Returns true on success; false if SD write fails or result_valid is false.
// If a previous file exists, it is backed up on-card and restored if the new
// write or verify fails.
// -----------------------------------------------------------------------------
bool calStore_saveFromResult(const MeasurementResult& result,
                                const char* filename,
                                const char* description);


// -----------------------------------------------------------------------------
// calStore_isValid(fft_mode, fft_size, sample_rate, window, line_in_level)
// Checks whether the resident calibration is applicable to a measurement
// with the given parameters.
//
// FIX [mode-mismatch]: FftMode is now a required parameter. The rules
// documented in the header comment above are now enforced:
//
//   HARD_MISMATCH:
//     fft_size, sample_rate, or window_function differs — systematic per-bin error
//     MODE_LIVE calibration applied to MODE_PRECISION or MODE_LF measurement —
//       calibration has lower resolution than the measurement expects
//
//   SOFT_MISMATCH (applied with warning):
//     line_in_level differs — magnitude approximate, phase valid
//     MODE_PRECISION calibration applied to MODE_LIVE measurement —
//       calibration has higher resolution; conservative but not wrong
//     MODE_LF calibration applied to MODE_LIVE or MODE_PRECISION —
//       calibration has higher resolution; conservative
//
//   VALID:
//     All parameters match exactly (including FftMode)
//
//   MISSING:
//     No calibration is loaded
//
// Returns:
//   VALID / SOFT_MISMATCH / HARD_MISMATCH / MISSING
//
// Call from measurementEngine PROCESSING state before Step 6.
// -----------------------------------------------------------------------------
CalibrationValidity calStore_isValid(FftMode           meas_fft_mode,
                                       uint16_t        fft_size,
                                       uint32_t        sample_rate,
                                       WindowFunction window,
                                       uint8_t         line_in_level);


// -----------------------------------------------------------------------------
// calStore_getBuffer()
// Returns a const reference to the resident CalibrationBuffer.
// Always safe to call. If not loaded, buffer.loaded == false and all
// correction arrays are zero (identity correction).
// -----------------------------------------------------------------------------
const CalibrationBuffer& calStore_getBuffer();


// -----------------------------------------------------------------------------
// calStore_isLoaded()
// Quick check without acquiring the full buffer reference.
// -----------------------------------------------------------------------------
bool calStore_isLoaded();


// -----------------------------------------------------------------------------
// calStore_getDescription()
// Returns a human-readable description of the loaded calibration.
// Returns "none" if no calibration is loaded.
// -----------------------------------------------------------------------------
const char* calStore_getDescription();


// -----------------------------------------------------------------------------
// calStore_clear()
// Unloads the resident calibration. The buffer is zeroed and loaded=false.
// Does NOT delete the file from SD.
// Useful for testing uncalibrated measurements.
// -----------------------------------------------------------------------------
void calStore_clear();


#endif // CALIBRATION_STORE_H
