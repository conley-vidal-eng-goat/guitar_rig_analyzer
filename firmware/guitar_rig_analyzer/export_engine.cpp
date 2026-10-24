// =============================================================================
// export_engine.cpp     —   Guitar Rig Analyzer
// =============================================================================
// Implementation of the durable file output layer.
//
// JSON WRITING STRATEGY
// ---------------------
// No heap allocation. No snprintf of the full document into a RAM buffer.
// All JSON is written incrementally to SD using a small fixed stack buffer
// (EXPORT_WRITE_BUF_SIZE bytes). The buffer is flushed to SD when:
//   (a) it is full, or
//   (b) a logical flush point is reached (e.g., end of an array)
//
// This means peak RAM usage during export is:
//   stack: EXPORT_WRITE_BUF_SIZE bytes (~256 B)
//   no heap, no large stack frame, no copy of the result
//
// The SD write is the bottleneck (~200 ms for a full fingerprint at FAT speed).
// This is acceptable — export is a post-measurement operation, not a live path.
//
// FLOAT SERIALISATION
// -------------------
// Floats are written with snprintf("%.4f") into a 32-byte stack buffer.
// snprintf is bounds-safe; dtostrf is not — a single out-of-range finite float
// (e.g. from an upstream NaN-poisoned path) would overflow dtostrf's 16-byte
// buffer. We accept the slightly larger code size for the safety guarantee.
// Non-finite values (NaN, Inf) are written as JSON null.
// =============================================================================


#include "export_engine.h"
#include <SD.h>
#include <string.h>
#include <stdio.h>


// =============================================================================
// MODULE-PRIVATE STATE
// =============================================================================
static bool s_available = false;


// Write buffer. Flush to SD when full or at logical boundaries.
#define EXPORT_WRITE_BUF_SIZE 256
static char   s_wbuf[EXPORT_WRITE_BUF_SIZE];
static int    s_wbuf_len = 0;
static File   s_file;                        // Currently open export file
// =============================================================================
// PRIVATE: LOW-LEVEL WRITE HELPERS
// =============================================================================


// Flush the write buffer to the open file.
static bool wflush() {
    if (s_wbuf_len == 0) return true;
    size_t n = s_file.write((uint8_t*)s_wbuf, s_wbuf_len);
    bool ok = (n == (size_t)s_wbuf_len);
    s_wbuf_len = 0;
    return ok;
}


// Append a string to the write buffer, flushing as needed.
static bool wstr(const char* s) {
    while (*s) {
        s_wbuf[s_wbuf_len++] = *s++;
        if (s_wbuf_len == EXPORT_WRITE_BUF_SIZE) {
            if (!wflush()) return false;
        }
    }
    return true;
}


// Append a single character.
static bool wchar(char c) {
    s_wbuf[s_wbuf_len++] = c;
    if (s_wbuf_len == EXPORT_WRITE_BUF_SIZE) {
        return wflush();
    }
    return true;
}


// Write a JSON key: "key":
static bool wkey(const char* key) {
    return wchar('"') && wstr(key) && wstr("\":");
}


// Write a JSON string value with standard JSON escaping.
// Escapes: " => \", \ => \\, common control chars => \n \t \r \b \f,
// other control characters 0x00-0x1F => \uXXXX.
// Bytes >= 0x80 are emitted verbatim — calStore_load sanitises the description
// at the trust boundary, so this should only ever see ASCII-printable input
// from internal call sites (firmware_version, provenance strings).
//
// Without proper escaping, a description containing " or \ produces malformed
// JSON that fails to parse on the receiving end.
static bool wstrval(const char* val) {
    if (!wchar('"')) return false;
    if (val) {
        for (const char* p = val; *p; p++) {
            unsigned char c = (unsigned char)*p;
            if (c == '"') {
                if (!wstr("\\\"")) return false;
            } else if (c == '\\') {
                if (!wstr("\\\\")) return false;
            } else if (c == '\n') {
                if (!wstr("\\n"))  return false;
            } else if (c == '\r') {
                if (!wstr("\\r"))  return false;
            } else if (c == '\t') {
                if (!wstr("\\t"))  return false;
            } else if (c == '\b') {
                if (!wstr("\\b"))  return false;
            } else if (c == '\f') {
                if (!wstr("\\f"))  return false;
            } else if (c < 0x20) {
                char esc[8];
                snprintf(esc, sizeof(esc), "\\u%04X", c);
                if (!wstr(esc)) return false;
            } else {
                if (!wchar((char)c)) return false;
            }
        }
    }
    return wchar('"');
}


// Write a JSON integer
static bool wint(int32_t v) {
    char buf[16];
    snprintf(buf, sizeof(buf), "%ld", (long)v);
    return wstr(buf);
}


// Write a JSON float (4 decimal places).
// Non-finite values (NaN, Inf) are written as JSON null per RFC 8259.
// Buffer is sized to handle any IEEE-754 single finite value formatted as %.4f
// (worst-case: -FLT_MAX produces ~46 chars; 64 gives safe margin).
static bool wfloat(float v) {
    if (!isfinite(v)) return wstr("null");
    char buf[64];
    int n = snprintf(buf, sizeof(buf), "%.4f", v);
    if (n < 0 || (size_t)n >= sizeof(buf)) {
        // Defensive: snprintf truncation — emit null rather than partial number
        return wstr("null");
    }
    return wstr(buf);
}


// Write a JSON boolean
static bool wbool(bool v) {
    return wstr(v ? "true" : "false");
}


// =============================================================================
// PRIVATE: ENUM-TO-STRING HELPERS
// =============================================================================
static const char* fftModeStr(FftMode m) {
    switch (m) {
        case FftMode::MODE_LIVE:      return "LIVE";
        case FftMode::MODE_PRECISION: return "PRECISION";
        case FftMode::MODE_LF:        return "LF";
        default:                      return "UNKNOWN";
    }
}
static const char* windowStr(WindowFunction w) {
    switch (w) {
        case WindowFunction::HANN:     return "HANN";
        case WindowFunction::BLACKMAN: return "BLACKMAN";
        case WindowFunction::FLAT_TOP: return "FLAT_TOP";
        default:                       return "UNKNOWN";
    }
}
static const char* estimatorStr(TfEstimator e) {
    switch (e) {
        case TfEstimator::H1: return "H1";
        case TfEstimator::H2: return "H2";
        case TfEstimator::HV: return "HV";
        default:              return "UNKNOWN";
    }
}
static const char* stimulusStr(StimulusType s) {
    switch (s) {
        case StimulusType::EXTERNAL:           return "EXTERNAL";
        case StimulusType::INTERNAL_SINE:      return "INTERNAL_SINE";
        case StimulusType::INTERNAL_PINK:      return "INTERNAL_PINK";
        case StimulusType::INTERNAL_WHITE:     return "INTERNAL_WHITE";
        case StimulusType::INTERNAL_LOG_SWEEP: return "INTERNAL_LOG_SWEEP";
        default:                               return "UNKNOWN";
    }
}
static const char* qualityStr(ResultQuality q) {
    switch (q) {
        case ResultQuality::EXCELLENT: return "EXCELLENT";
        case ResultQuality::GOOD:      return "GOOD";
        case ResultQuality::MARGINAL:  return "MARGINAL";
        case ResultQuality::POOR:      return "POOR";
        case ResultQuality::INVALID:   return "INVALID";
        default:                       return "UNKNOWN";
    }
}


// =============================================================================
// PRIVATE: WRITE A FLOAT ARRAY AS A JSON ARRAY
// Each element is written with 4 decimal places. Non-finite => null.
// Emits:   [v0,v1,...,vN-1]
// =============================================================================
static bool writeFloatArray(const float* arr, int n) {
    if (!wchar('[')) return false;
    for (int k = 0; k < n; k++) {
        if (k > 0 && !wchar(',')) return false;
        if (!wfloat(arr[k]))       return false;
    }
    return wchar(']');
}


// =============================================================================
// PRIVATE: VALIDATE A CALLER-PROVIDED FILENAME LEAF
// Rejects path traversal, separators, control chars, and high-bit bytes.
// Used at the trust boundary between the public save APIs and SD I/O.
// Returns true if the leaf is safe to use under EXPORT_DIR_DEFAULT.
// =============================================================================
static bool isSafeFilename(const char* name) {
    if (!name || !name[0]) return false;
    size_t len = strlen(name);
    if (len >= EXPORT_FILENAME_LEN) return false;
    if (name[0] == '.' && (len == 1 || (len == 2 && name[1] == '.'))) return false;
    for (size_t i = 0; i < len; i++) {
        unsigned char c = (unsigned char)name[i];
        if (c == '/' || c == '\\') return false;
        if (i > 0 && name[i - 1] == '.' && c == '.') return false;
        if (c < 0x20 || c == 0x7F) return false;
        if (c > 0x7E)              return false;
    }
    return true;
}


// =============================================================================
// PRIVATE: WRITE THE FULL JSON FINGERPRINT
//
// FIX [early-exit]: Previously every step used `ok &= ...` accumulation and
// continued writing even after a failure. A mid-write SD error (full card,
// removed mid-export) still drove ~48 KB of SD operations to a failed handle.
// We now check `ok` after each logical block and bail out early.
// =============================================================================
static bool writeJSON(const MeasurementResult& r) {
    // FIX [frequency-axis]: The exported arrays are on the canonical 512-bin grid,
    // always spanning 0 to SAMPLE_RATE/2 Hz with FFT_BINS equally spaced bins.
    // The canonical bin spacing is SAMPLE_RATE / (FFT_BINS * 2) = SAMPLE_RATE / 1024
    // regardless of r.fft_size (which may be 4096 or 8192 for precision modes).
    const float canonical_bin_hz = (float)SAMPLE_RATE / (float)(FFT_BINS * 2);

    bool ok = true;

    // Open
    ok &= wstr("{\n");

    // --- Schema and firmware ---
    ok &= wstr("    "); ok &= wkey("schema");   ok &= wint(1);                       ok &= wstr(",\n");
    ok &= wstr("    "); ok &= wkey("firmware"); ok &= wstrval(r.firmware_version);   ok &= wstr(",\n");
    if (!ok) return false;

    // --- Timing ---
    ok &= wstr("    "); ok &= wkey("timestamp_ms");    ok &= wint(r.timestamp_ms);   ok &= wstr(",\n");
    ok &= wstr("    "); ok &= wkey("capture_blocks");
    ok &= wstr("{\"start\":");
    ok &= wint(r.capture_start_block);
    ok &= wstr(",\"end\":");
    ok &= wint(r.capture_end_block);
    ok &= wstr("},\n");
    if (!ok) return false;

    // --- Measurement parameters ---
    ok &= wstr("    "); ok &= wkey("frames");    ok &= wint(r.n_averages_completed);          ok &= wstr(",\n");
    ok &= wstr("    "); ok &= wkey("fft_size");  ok &= wint(r.fft_size);                      ok &= wstr(",\n");
    ok &= wstr("    "); ok &= wkey("fft_mode");  ok &= wstrval(fftModeStr(r.fft_mode));       ok &= wstr(",\n");
    ok &= wstr("    "); ok &= wkey("window");    ok &= wstrval(windowStr(r.window_function)); ok &= wstr(",\n");
    ok &= wstr("    "); ok &= wkey("estimator"); ok &= wstrval(estimatorStr(r.estimator));    ok &= wstr(",\n");
    ok &= wstr("    "); ok &= wkey("stimulus");  ok &= wstrval(stimulusStr(r.stimulus));      ok &= wstr(",\n");
    if (!ok) return false;

    // --- Quality and health ---
    ok &= wstr("    "); ok &= wkey("quality");            ok &= wstrval(qualityStr(r.result_quality)); ok &= wstr(",\n");
    ok &= wstr("    "); ok &= wkey("mean_coherence");     ok &= wfloat(r.mean_coherence);              ok &= wstr(",\n");
    ok &= wstr("    "); ok &= wkey("valid_bin_fraction"); ok &= wfloat(r.valid_bin_fraction);          ok &= wstr(",\n");
    ok &= wstr("    "); ok &= wkey("clip_detected");      ok &= wbool(r.clip_detected);                ok &= wstr(",\n");
    if (!ok) return false;

    // --- Hardware context ---
    ok &= wstr("    "); ok &= wkey("source_ch");     ok &= wint(r.source_node_ch); ok &= wstr(",\n");
    ok &= wstr("    "); ok &= wkey("return_ch");     ok &= wint(r.return_node_ch); ok &= wstr(",\n");
    ok &= wstr("    "); ok &= wkey("line_in_level"); ok &= wint(r.line_in_level);  ok &= wstr(",\n");
    if (!ok) return false;

    // --- Calibration block ---
    ok &= wstr("    "); ok &= wkey("calibration"); ok &= wstr("{\n");
    ok &= wstr("        "); ok &= wkey("applied");    ok &= wbool(r.calibration_applied);              ok &= wstr(",\n");
    ok &= wstr("        "); ok &= wkey("provenance"); ok &= wstrval(r.calibration_provenance);         ok &= wstr(",\n");
    ok &= wstr("        "); ok &= wkey("warnings");   ok &= wstr("{\n");
    ok &= wstr("            "); ok &= wkey("missing");        ok &= wbool(r.calibration_warnings.calibration_missing);          ok &= wstr(",\n");
    ok &= wstr("            "); ok &= wkey("level_mismatch");ok &= wbool(r.calibration_warnings.line_in_level_mismatch);        ok &= wstr(",\n");
    ok &= wstr("            "); ok &= wkey("partial");        ok &= wbool(r.calibration_warnings.partial_calibration_applied);  ok &= wstr(",\n");
    ok &= wstr("            "); ok &= wkey("hard_mismatch");  ok &= wbool(r.calibration_warnings.hard_parameter_mismatch);      ok &= wstr(",\n");
    ok &= wstr("            "); ok &= wkey("imported");       ok &= wbool(r.calibration_warnings.calibration_from_import);      ok &= wstr("\n");
    ok &= wstr("        }\n");
    ok &= wstr("    },\n");
    if (!ok) return false;

    // --- Bin geometry ---
    // bins: number of canonical result bins (always FFT_BINS = 512)
    // hz: per-bin centre frequency array — canonical grid, always 512 entries
    //      hz[k] = k * canonical_bin_hz regardless of measurement mode
    ok &= wstr("    "); ok &= wkey("bins"); ok &= wint(FFT_BINS); ok &= wstr(",\n");
    ok &= wstr("    "); ok &= wkey("hz");
    ok &= wchar('[');
    for (int k = 0; k < FFT_BINS; k++) {
        if (k > 0) { ok &= wchar(','); }
        ok &= wfloat((float)k * canonical_bin_hz);
        if (!ok) return false;
    }
    ok &= wstr("],\n");
    ok &= wflush();
    if (!ok) return false;

    // --- Spectral arrays ---
    // Each array is written on one line. For 512 bins at ~10 chars/element +
    // commas, each array is ~6 KB. Total file size: ~48 KB for 7 arrays.
    ok &= wstr("    "); ok &= wkey("S_xx_db");          ok &= writeFloatArray(r.S_xx_db,          FFT_BINS); ok &= wstr(",\n");
    ok &= wflush();
    if (!ok) return false;

    ok &= wstr("    "); ok &= wkey("S_yy_db");          ok &= writeFloatArray(r.S_yy_db,          FFT_BINS); ok &= wstr(",\n");
    ok &= wflush();
    if (!ok) return false;

    ok &= wstr("    "); ok &= wkey("coherence");        ok &= writeFloatArray(r.coherence,        FFT_BINS); ok &= wstr(",\n");
    ok &= wflush();
    if (!ok) return false;

    ok &= wstr("    "); ok &= wkey("tf_raw_mag_db");    ok &= writeFloatArray(r.tf_raw_mag_db,    FFT_BINS); ok &= wstr(",\n");
    ok &= wflush();
    if (!ok) return false;

    ok &= wstr("    "); ok &= wkey("tf_cal_mag_db");    ok &= writeFloatArray(r.tf_cal_mag_db,    FFT_BINS); ok &= wstr(",\n");
    ok &= wflush();
    if (!ok) return false;

    ok &= wstr("    "); ok &= wkey("tf_cal_phase_rad"); ok &= writeFloatArray(r.tf_cal_phase_rad, FFT_BINS); ok &= wstr(",\n");
    ok &= wflush();
    if (!ok) return false;

    // group_delay_ms is the last array — no trailing comma
    ok &= wstr("    "); ok &= wkey("group_delay_ms");   ok &= writeFloatArray(r.group_delay_ms,   FFT_BINS); ok &= wstr("\n");
    ok &= wflush();
    if (!ok) return false;

    // Close document
    ok &= wstr("}\n");
    ok &= wflush();

    return ok;
}


// =============================================================================
// PUBLIC FUNCTION IMPLEMENTATIONS
// =============================================================================


// -----------------------------------------------------------------------------
// exportEngine_init()
// -----------------------------------------------------------------------------
bool exportEngine_init() {
    // SD.begin() should already have been called by calStore_init() before
    // this function. We do not call SD.begin() here — calling it twice on
    // a Teensy 4.1 can cause SD controller state issues. We simply test
    // whether the card is accessible.
    File root = SD.open("/");
    s_available = (bool)root;
    if (root) root.close();
    if (s_available) {
        // Create export directory if it does not exist.
        // FIX [mkdir-check]: previously the return of mkdir was ignored, so a
        // failed mkdir would silently break every subsequent save (the parent
        // directory of the export filename would not exist). We now log and
        // disable export rather than producing silent failures downstream.
        if (!SD.exists(EXPORT_DIR_DEFAULT)) {
            if (!SD.mkdir(EXPORT_DIR_DEFAULT)) {
                Serial.printf("[ExportEngine] WARNING: mkdir('%s') failed. "
                              "File export disabled.\n", EXPORT_DIR_DEFAULT);
                s_available = false;
                return false;
            }
        }
        Serial.printf("[ExportEngine] Ready. Export directory: %s\n", EXPORT_DIR_DEFAULT);
    } else {
        Serial.println("[ExportEngine] SD not available. File export disabled.");
    }
    return s_available;
}


// -----------------------------------------------------------------------------
// exportEngine_saveMeasurement(result, filename, filename_out)
// -----------------------------------------------------------------------------
bool exportEngine_saveMeasurement(const MeasurementResult& result,
                                  const char*              filename,
                                  char*                    filename_out) {
    if (!s_available) {
        Serial.println("[ExportEngine] saveMeasurement() failed: SD not available");
        return false;
    }

    // Determine the output path
    char path[64];
    char leaf[EXPORT_FILENAME_LEN];

    if (filename && filename[0] != '\0') {
        // Caller-provided name — validate at the trust boundary
        if (!isSafeFilename(filename)) {
            Serial.printf("[ExportEngine] saveMeasurement() rejected: unsafe filename '%s'\n",
                          filename);
            return false;
        }
        strncpy(leaf, filename, EXPORT_FILENAME_LEN - 1);
        leaf[EXPORT_FILENAME_LEN - 1] = '\0';
    } else {
        // Generate a unique name from timestamp_ms (hex)
        snprintf(leaf, sizeof(leaf), "r_%08lX.json", (unsigned long)result.timestamp_ms);
    }

    // Prepend the export directory. snprintf return must fit.
    int plen = snprintf(path, sizeof(path), "%s/%s", EXPORT_DIR_DEFAULT, leaf);
    if (plen < 0 || (size_t)plen >= sizeof(path)) {
        Serial.printf("[ExportEngine] saveMeasurement() rejected: path too long ('%s/%s')\n",
                      EXPORT_DIR_DEFAULT, leaf);
        return false;
    }

    if (filename_out) {
        strncpy(filename_out, leaf, EXPORT_FILENAME_LEN);
    }

    // FIX [remove-check]: explicit-remove-then-write was unchecked. A failed
    // remove would cause FILE_WRITE to append to the existing file (Arduino SD
    // semantics) producing a doubled-length, syntactically invalid JSON.
    if (SD.exists(path)) {
        if (!SD.remove(path)) {
            Serial.printf("[ExportEngine] saveMeasurement() failed: cannot remove existing '%s'\n",
                          path);
            return false;
        }
    }
    s_file = SD.open(path, FILE_WRITE);
    if (!s_file) {
        Serial.printf("[ExportEngine] saveMeasurement() failed: cannot open '%s'\n", path);
        return false;
    }

    // Reset write buffer
    s_wbuf_len = 0;

    // Write JSON incrementally
    bool ok = writeJSON(result);

    s_file.close();

    if (!ok) {
        // FIX [partial-cleanup]: if the write failed mid-document we leave a
        // truncated file behind, which downstream parsers will reject. Removing
        // the partial file gives a clean "no output" outcome rather than a
        // syntactically broken file that looks like a real export.
        SD.remove(path);
        Serial.printf("[ExportEngine] Write error for '%s' — partial file removed\n", path);
        return false;
    }

    Serial.printf("[ExportEngine] Saved: %s\n", path);
    return true;
}


// -----------------------------------------------------------------------------
// exportEngine_saveBaselineCSV(result, filename)
// -----------------------------------------------------------------------------
bool exportEngine_saveBaselineCSV(const MeasurementResult& result,
                                  const char*              filename) {
    if (!s_available) {
        Serial.println("[ExportEngine] saveBaselineCSV() failed: SD not available");
        return false;
    }

    char path[64];
    if (filename && filename[0] != '\0') {
        if (!isSafeFilename(filename)) {
            Serial.printf("[ExportEngine] saveBaselineCSV() rejected: unsafe filename '%s'\n",
                          filename);
            return false;
        }
        int plen = snprintf(path, sizeof(path), "%s/%s", EXPORT_DIR_DEFAULT, filename);
        if (plen < 0 || (size_t)plen >= sizeof(path)) {
            Serial.println("[ExportEngine] saveBaselineCSV() rejected: path too long");
            return false;
        }
    } else {
        char leaf[EXPORT_FILENAME_LEN];
        snprintf(leaf, sizeof(leaf), "b_%08lX.csv", (unsigned long)result.timestamp_ms);
        int plen = snprintf(path, sizeof(path), "%s/%s", EXPORT_DIR_DEFAULT, leaf);
        if (plen < 0 || (size_t)plen >= sizeof(path)) {
            Serial.println("[ExportEngine] saveBaselineCSV() rejected: path too long");
            return false;
        }
    }

    if (SD.exists(path)) {
        if (!SD.remove(path)) {
            Serial.printf("[ExportEngine] saveBaselineCSV() failed: cannot remove existing '%s'\n",
                          path);
            return false;
        }
    }
    s_file = SD.open(path, FILE_WRITE);
    if (!s_file) {
        Serial.printf("[ExportEngine] saveBaselineCSV() failed: cannot open '%s'\n", path);
        return false;
    }
    s_wbuf_len = 0;

    // FIX [frequency-axis]: Use canonical grid spacing, not r.fft_size.
    const float canonical_bin_hz = (float)SAMPLE_RATE / (float)(FFT_BINS * 2);

    bool ok = true;

    // Header row
    ok &= wstr("hz,tf_cal_mag_db,coherence\r\n");

    // One row per bin.
    // Non-finite values (NaN from unenergised bins) are written as empty fields
    // so CSV consumers see missing data, not platform-dependent "nan" strings.
    char row[64];
    for (int k = 0; k < FFT_BINS && ok; k++) {
        float hz  = (float)k * canonical_bin_hz;
        float mag = result.tf_cal_mag_db[k];
        float coh = result.coherence[k];
        int   n;
        if (isfinite(mag) && isfinite(coh)) {
            n = snprintf(row, sizeof(row), "%.2f,%.4f,%.4f\r\n", hz, mag, coh);
        } else if (isfinite(mag)) {
            n = snprintf(row, sizeof(row), "%.2f,%.4f,\r\n", hz, mag);
        } else if (isfinite(coh)) {
            n = snprintf(row, sizeof(row), "%.2f,,%.4f\r\n", hz, coh);
        } else {
            n = snprintf(row, sizeof(row), "%.2f,,\r\n", hz);
        }
        if (n < 0 || (size_t)n >= sizeof(row)) {
            ok = false;
            break;
        }
        ok &= wstr(row);
        if (k % 32 == 31) ok &= wflush();
    }
    ok &= wflush();

    s_file.close();

    if (!ok) {
        SD.remove(path);
        Serial.printf("[ExportEngine] CSV write error for '%s' — partial file removed\n", path);
        return false;
    }

    Serial.printf("[ExportEngine] Baseline CSV saved: %s\n", path);
    return true;
}


// -----------------------------------------------------------------------------
// exportEngine_isAvailable()
// -----------------------------------------------------------------------------
bool exportEngine_isAvailable() {
    return s_available;
}
