// =============================================================================
// calibration_store.cpp    —   Guitar Rig Analyzer
// =============================================================================
// Implementation of the calibration buffer owner.
//
// SD ACCESS
// ---------
// Uses the Teensy 4.1 built-in SD library (SD.h). The SD card is accessed via
// the Teensy 4.1's on-board SDIO interface (faster than SPI, no CS pin needed).
// SD.begin() must succeed before any calStore_load/save operation.
// Failures are reported to Serial and treated as non-fatal — the device
// continues operating without calibration.
//
// CRC-32
// ------
// The Teensy 4.1 has a hardware CRC unit accessible via the Kinetis CRC
// peripheral registers. We use a software CRC-32 here for portability and
// simplicity — the calibration file write path is not performance-critical
// (written once, read occasionally). The CRC protects against SD corruption.
//
// BINARY FILE LAYOUT
// ------------------
// See calibration_store.h for the full format description.
// Offsets are defined as named constants below for maintainability.
// =============================================================================


#include "calibration_store.h"
#include <SD.h>
#include <string.h>
#include <math.h>


// =============================================================================
// FILE FORMAT CONSTANTS
// =============================================================================
static const uint32_t CAL_MAGIC            = 0x52494743;    // "RIGC"
static const uint16_t CAL_SCHEMA_VER       = 1;
static const float    CAL_MIN_COH_FOR_BIN  = 0.80f;         // Below this -> bin_valid = false
static const uint32_t CAL_FILE_SIZE        = 4678;          // Total expected file size in bytes


// Byte offsets in the binary file
static const uint32_t OFF_MAGIC          = 0;       // uint32
static const uint32_t OFF_SCHEMA_VER     = 4;       // uint16
static const uint32_t OFF_FFT_MODE       = 6;       // uint8
static const uint32_t OFF_FFT_SIZE       = 7;       // uint16
static const uint32_t OFF_SAMPLE_RATE    = 9;       // uint32
static const uint32_t OFF_WINDOW_FUNC    = 13;      // uint8
static const uint32_t OFF_LINE_IN_LEVEL  = 14;      // uint8
static const uint32_t OFF_CAL_TYPE       = 15;      // uint8
static const uint32_t OFF_TIMESTAMP_MS   = 16;      // uint32
static const uint32_t OFF_DESCRIPTION    = 20;      // char[46]
static const uint32_t OFF_CAL_MAG_DB     = 66;      // float[512]
static const uint32_t OFF_CAL_PHASE_RAD  = 2114;    // float[512]
static const uint32_t OFF_BIN_VALID      = 4162;    // uint8[512]
static const uint32_t OFF_CRC32          = 4674;    // uint32


// =============================================================================
// MODULE-PRIVATE STATE
// =============================================================================
static CalibrationBuffer s_cal;                   // Resident buffer — always valid to read
static bool              s_sd_available = false;


// =============================================================================
// PRIVATE: CRC-32 (standard IEEE 802.3 polynomial 0xEDB88320, bit-reversed)
// =============================================================================
// Pure CRC-32 state update — no seed, no final XOR.
// Caller must initialise crc to 0xFFFFFFFF before the first call and
// apply ~crc after the last call to get the standard CRC-32 value.
static uint32_t crc32_step(uint32_t crc, const uint8_t* data, size_t len) {
    for (size_t i = 0; i < len; i++) {
        crc ^= data[i];
        for (int j = 0; j < 8; j++) {
            crc = (crc >> 1) ^ (0xEDB88320u & -(crc & 1u));
        }
    }
    return crc;
}


// Compute standard CRC-32 over bytes 0..(total_len-5).
// Bytes (total_len-4)..(total_len-1) are the stored CRC and are NOT included.
static uint32_t computeFileCRC(const uint8_t* buf, size_t total_len) {
    if (total_len < 4) return 0;
    uint32_t crc = 0xFFFFFFFFu;                    // standard seed
    crc = crc32_step(crc, buf, total_len - 4);     // process all bytes except stored CRC
    return ~crc;                                    // standard final XOR
}


// =============================================================================
// PRIVATE: read/write helpers for multi-byte primitives (little-endian).
// memcpy preserves host byte order for IEEE-754 floats; Teensy 4.1 is
// little-endian so the file is little-endian throughout.
// =============================================================================
static uint32_t readU32(const uint8_t* p) {
    return ((uint32_t)p[0])         | ((uint32_t)p[1] << 8) |
           ((uint32_t)p[2] << 16)   | ((uint32_t)p[3] << 24);
}
static uint16_t readU16(const uint8_t* p) {
    return ((uint16_t)p[0]) | ((uint16_t)p[1] << 8);
}
static float readF32(const uint8_t* p) {
    float f; memcpy(&f, p, 4); return f;
}
static void writeU32(uint8_t* p, uint32_t v) {
    p[0] = (uint8_t)(v      );
    p[1] = (uint8_t)(v >>  8);
    p[2] = (uint8_t)(v >> 16);
    p[3] = (uint8_t)(v >> 24);
}
static void writeU16(uint8_t* p, uint16_t v) {
    p[0] = (uint8_t)(v     );
    p[1] = (uint8_t)(v >> 8);
}
static void writeF32(uint8_t* p, float v) {
    memcpy(p, &v, 4);
}


// =============================================================================
// PRIVATE: filename trust-boundary check
// =============================================================================
// Calibration files live at the SD root. Public calStore_* callers may pass a
// filename, so reject path traversal, separators, control/high-bit bytes, and
// overlong leaf names before touching SD.
static bool isSafeCalFilename(const char* name) {
    if (!name || !name[0]) return false;
    size_t len = strlen(name);
    if (len >= 48) return false;
    // Reserved scratch leaves used by calStore_saveFromResult() for on-card
    // rollback. Public callers may not target these directly.
    if (strcmp(name, "rig_cal.bak") == 0) return false;
    if (name[0] == '.' && (len == 1 || (len == 2 && name[1] == '.'))) return false;
    for (size_t i = 0; i < len; i++) {
        unsigned char c = (unsigned char)name[i];
        if (c == '/' || c == '\\') return false;
        if (i > 0 && name[i - 1] == '.' && c == '.') return false;
        if (c < 0x20 || c == 0x7F) return false;
        if (c > 0x7E) return false;
    }
    return true;
}


// Copy one root-level SD file to another. The destination is replaced only
// after an explicit remove succeeds, avoiding FILE_WRITE append semantics.
static bool copyCalFile(const char* src, const char* dst) {
    if (!src || !dst) return false;

    if (SD.exists(dst)) {
        if (!SD.remove(dst)) {
            Serial.printf("[CalStore] copy failed: cannot remove scratch '%s'\n", dst);
            return false;
        }
    }

    File in = SD.open(src, FILE_READ);
    if (!in) {
        Serial.printf("[CalStore] copy failed: cannot open source '%s'\n", src);
        return false;
    }

    File out = SD.open(dst, FILE_WRITE);
    if (!out) {
        Serial.printf("[CalStore] copy failed: cannot create destination '%s'\n", dst);
        in.close();
        return false;
    }

    uint8_t chunk[96];
    bool ok = true;
    while (in.available()) {
        int n = in.read(chunk, sizeof(chunk));
        if (n < 0) {
            ok = false;
            break;
        }
        if (n == 0) break;
        if (out.write(chunk, (size_t)n) != (size_t)n) {
            ok = false;
            break;
        }
    }

    in.close();
    out.close();

    if (!ok) {
        SD.remove(dst);
        Serial.printf("[CalStore] copy failed: write/read error '%s' -> '%s'\n", src, dst);
        return false;
    }

    File vf = SD.open(dst, FILE_READ);
    if (!vf) {
        Serial.printf("[CalStore] copy failed: cannot verify '%s'\n", dst);
        return false;
    }
    bool size_ok = ((uint32_t)vf.size() == CAL_FILE_SIZE);
    vf.close();
    if (!size_ok) {
        SD.remove(dst);
        Serial.printf("[CalStore] copy failed: verify size mismatch for '%s'\n", dst);
        return false;
    }

    return true;
}


static bool restoreCalBackup(const char* filename, const char* backup_filename) {
    if (SD.exists(filename) && !SD.remove(filename)) {
        Serial.printf("[CalStore] restore failed: cannot remove failed '%s'\n", filename);
        return false;
    }
    if (!copyCalFile(backup_filename, filename)) {
        Serial.printf("[CalStore] restore failed: backup '%s' not restored to '%s'\n",
                      backup_filename, filename);
        return false;
    }
    if (!SD.remove(backup_filename)) {
        Serial.printf("[CalStore] restore warning: could not remove scratch '%s'\n",
                      backup_filename);
    }
    return true;
}


// =============================================================================
// PRIVATE: parseBuffer — deserialise a valid binary buffer into s_cal
//
// FIX [trust-boundary]: previously the function wrote directly into s_cal
// incrementally. Any check failure mid-parse (or a future addition of a check)
// would have left the resident buffer half-populated. We now stage into a
// stack temporary and commit atomically on success. The header promises that
// "on failure, the previous buffer state is preserved" — this honours it.
//
// FIX [enum-validation]: every enum field is range-checked. A malicious .cal
// file can supply any byte (0..255) for these uint8 fields. Without validation
// an attacker-controlled value would flow into downstream switch statements
// that may exhibit unexpected behaviour after compiler optimization.
//
// FIX [description-sanitise]: description bytes outside printable ASCII are
// replaced with '?' before commit. Without this, an attacker-controlled
// description containing 0x80–0xFF bytes would produce invalid UTF-8 in the
// JSON export, crashing strict desktop parsers.
// =============================================================================
static bool parseBuffer(const uint8_t* buf) {
    // Verify magic
    if (readU32(buf + OFF_MAGIC) != CAL_MAGIC) {
        Serial.println("[CalStore] Load failed: bad magic number");
        return false;
    }

    // Verify schema version
    uint16_t schema = readU16(buf + OFF_SCHEMA_VER);
    if (schema != CAL_SCHEMA_VER) {
        Serial.printf("[CalStore] Load failed: schema version %u (expected %u)\n",
                      schema, CAL_SCHEMA_VER);
        return false;
    }

    // Verify CRC
    uint32_t stored_crc   = readU32(buf + OFF_CRC32);
    uint32_t computed_crc = computeFileCRC(buf, CAL_FILE_SIZE);
    if (stored_crc != computed_crc) {
        Serial.printf("[CalStore] Load failed: CRC mismatch (stored=0x%08lX computed=0x%08lX)\n",
                      (unsigned long)stored_crc, (unsigned long)computed_crc);
        return false;
    }

    // Stage into a local temporary; commit only on success.
    CalibrationBuffer tmp;
    memset(&tmp, 0, sizeof(tmp));

    // Validate and deserialise header
    uint8_t fft_mode_byte = buf[OFF_FFT_MODE];
    if (fft_mode_byte > (uint8_t)FftMode::MODE_LF) {
        Serial.printf("[CalStore] Load failed: invalid fft_mode byte %u\n", fft_mode_byte);
        return false;
    }
    tmp.fft_mode = (FftMode)fft_mode_byte;

    uint16_t fft_size_val = readU16(buf + OFF_FFT_SIZE);
    if (fft_size_val != 1024 && fft_size_val != 4096 && fft_size_val != 8192) {
        Serial.printf("[CalStore] Load failed: invalid fft_size %u\n", fft_size_val);
        return false;
    }
    tmp.fft_size = fft_size_val;

    uint32_t sample_rate_val = readU32(buf + OFF_SAMPLE_RATE);
    if (sample_rate_val < 8000u || sample_rate_val > 192000u) {
        Serial.printf("[CalStore] Load failed: invalid sample_rate %lu\n",
                      (unsigned long)sample_rate_val);
        return false;
    }
    tmp.sample_rate = sample_rate_val;

    uint8_t window_byte = buf[OFF_WINDOW_FUNC];
    if (window_byte > (uint8_t)WindowFunction::FLAT_TOP) {
        Serial.printf("[CalStore] Load failed: invalid window_function byte %u\n", window_byte);
        return false;
    }
    tmp.window_function = (WindowFunction)window_byte;

    uint8_t line_in_val = buf[OFF_LINE_IN_LEVEL];
    if (line_in_val > 15u) {
        Serial.printf("[CalStore] Load failed: invalid line_in_level %u (max 15)\n", line_in_val);
        return false;
    }
    tmp.line_in_level = line_in_val;

    uint8_t cal_type_byte = buf[OFF_CAL_TYPE];
    if (cal_type_byte > (uint8_t)CalibrationType::USER_IMPORTED) {
        Serial.printf("[CalStore] Load failed: invalid cal_type byte %u\n", cal_type_byte);
        return false;
    }
    tmp.type = (CalibrationType)cal_type_byte;

    tmp.capture_timestamp_ms = readU32(buf + OFF_TIMESTAMP_MS);

    // Description: copy then sanitise to printable ASCII at the trust boundary.
    memcpy(tmp.description, buf + OFF_DESCRIPTION, 46);
    for (int i = 0; i < 45; i++) {
        unsigned char c = (unsigned char)tmp.description[i];
        if (c == 0) break;                           // legitimate early-terminate
        if (c < 0x20 || c == 0x7F || c > 0x7E) {
            tmp.description[i] = '?';
        }
    }
    tmp.description[45] = '\0';                      // Ensure null termination

    // Deserialise correction arrays. A CRC-valid but malicious calibration can
    // still encode NaN/Inf floats; reject those for valid bins so bad SD data
    // cannot poison a trusted measurement. Invalid bins are normalised to
    // identity correction regardless of stored payload.
    for (int k = 0; k < FFT_BINS; k++) {
        float mag = readF32(buf + OFF_CAL_MAG_DB    + k*4);
        float ph  = readF32(buf + OFF_CAL_PHASE_RAD + k*4);
        bool valid = (buf[OFF_BIN_VALID + k] != 0);
        if (valid && (!isfinite(mag) || !isfinite(ph))) {
            Serial.printf("[CalStore] Load failed: non-finite calibration bin %d\n", k);
            return false;
        }
        tmp.cal_mag_db   [k] = valid ? mag : 0.0f;
        tmp.cal_phase_rad[k] = valid ? ph  : 0.0f;
        tmp.bin_valid    [k] = valid;
    }

    tmp.loaded = true;
    // Commit atomically.
    s_cal = tmp;
    return true;
}


// =============================================================================
// PRIVATE: serializeToBuffer — serialise s_cal into a binary buffer
// =============================================================================
static void serializeToBuffer(uint8_t* buf) {
    memset(buf, 0, CAL_FILE_SIZE);

    writeU32(buf + OFF_MAGIC,         CAL_MAGIC);
    writeU16(buf + OFF_SCHEMA_VER,    CAL_SCHEMA_VER);
    buf[OFF_FFT_MODE]       = (uint8_t)s_cal.fft_mode;
    writeU16(buf + OFF_FFT_SIZE,      s_cal.fft_size);
    writeU32(buf + OFF_SAMPLE_RATE,   s_cal.sample_rate);
    buf[OFF_WINDOW_FUNC]    = (uint8_t)s_cal.window_function;
    buf[OFF_LINE_IN_LEVEL]  = s_cal.line_in_level;
    buf[OFF_CAL_TYPE]       = (uint8_t)s_cal.type;
    writeU32(buf + OFF_TIMESTAMP_MS,  s_cal.capture_timestamp_ms);
    memcpy(buf + OFF_DESCRIPTION, s_cal.description, 46);

    for (int k = 0; k < FFT_BINS; k++) {
        writeF32(buf + OFF_CAL_MAG_DB    + k*4, s_cal.cal_mag_db   [k]);
        writeF32(buf + OFF_CAL_PHASE_RAD + k*4, s_cal.cal_phase_rad[k]);
        buf[OFF_BIN_VALID + k] = s_cal.bin_valid[k] ? 1 : 0;
    }

    // CRC over bytes 0..(CAL_FILE_SIZE-5)
    uint32_t crc = computeFileCRC(buf, CAL_FILE_SIZE);
    writeU32(buf + OFF_CRC32, crc);
}


// =============================================================================
// PUBLIC FUNCTION IMPLEMENTATIONS
// =============================================================================


// -----------------------------------------------------------------------------
// calStore_init()
// -----------------------------------------------------------------------------
void calStore_init() {
    // Zero the buffer — all correction arrays start as identity (zero dB, zero rad)
    memset(&s_cal, 0, sizeof(s_cal));
    s_cal.loaded = false;

    // Try to initialise SD
    s_sd_available = SD.begin(BUILTIN_SDCARD);
    if (!s_sd_available) {
        Serial.println("[CalStore] SD not available. Calibration file I/O disabled.");
        Serial.println("[CalStore] Operating uncalibrated.");
        return;
    }

    // Try to load the default calibration file
    if (SD.exists(CAL_FILE_DEFAULT)) {
        bool ok = calStore_load(CAL_FILE_DEFAULT);
        if (ok) {
            Serial.printf("[CalStore] Default calibration loaded: %s\n", CAL_FILE_DEFAULT);
            Serial.printf("[CalStore] Description: %s\n", s_cal.description);
        } else {
            Serial.printf("[CalStore] Default calibration file exists but failed to load: %s\n",
                          CAL_FILE_DEFAULT);
            Serial.println("[CalStore] Operating uncalibrated.");
        }
    } else {
        Serial.printf("[CalStore] No default calibration file found (%s).\n", CAL_FILE_DEFAULT);
        Serial.println("[CalStore] Run a loopback measurement and press 'c' to calibrate.");
    }
}


// -----------------------------------------------------------------------------
// calStore_load(filename)
// -----------------------------------------------------------------------------
bool calStore_load(const char* filename) {
    if (!s_sd_available) {
        Serial.println("[CalStore] load() failed: SD not available");
        return false;
    }
    if (!filename || !filename[0]) {
        Serial.println("[CalStore] load() failed: null/empty filename");
        return false;
    }
    if (!isSafeCalFilename(filename)) {
        Serial.printf("[CalStore] load() rejected: unsafe filename '%s'\n", filename);
        return false;
    }

    File f = SD.open(filename, FILE_READ);
    if (!f) {
        Serial.printf("[CalStore] load() failed: cannot open '%s'\n", filename);
        return false;
    }

    if ((uint32_t)f.size() != CAL_FILE_SIZE) {
        Serial.printf("[CalStore] load() failed: size %lu (expected %lu)\n",
                      (unsigned long)f.size(), (unsigned long)CAL_FILE_SIZE);
        f.close();
        return false;
    }

    // Read entire file into a stack buffer.
    // CAL_FILE_SIZE = 4678 bytes — safe for stack on Teensy 4.1.
    uint8_t buf[CAL_FILE_SIZE];
    int     raw_read = f.read(buf, CAL_FILE_SIZE);
    f.close();

    if (raw_read < 0 || (uint32_t)raw_read != CAL_FILE_SIZE) {
        Serial.printf("[CalStore] load() failed: read %d bytes (expected %lu)\n",
                      raw_read, (unsigned long)CAL_FILE_SIZE);
        return false;
    }

    return parseBuffer(buf);
}


// -----------------------------------------------------------------------------
// calStore_saveFromResult(result, filename, description)
//
// FIX [save-atomicity]: previously the function overwrote s_cal in place
// before attempting the SD write. If the write failed, s_cal was already
// gone — the user saw a "save failed" message on the display while every
// subsequent measurement silently applied the un-persisted (now lost)
// calibration. The header promises atomicity. We now snapshot the prior
// s_cal into a stack backup, build the new cal in s_cal, write/verify on
// SD, and restore the backup on any failure path.
//
// FIX [remove-check]: SD.remove() return value is checked. A failed remove
// followed by FILE_WRITE produces an append (Arduino SD semantics) which
// would yield a doubled, CRC-invalid file.
//
// FIX [close-flush-detection]: after f.close(), the file is reopened and
// its stored CRC is read back. f.close() returns void; there is no other
// way to detect a deferred FAT flush failure. The read-back catches both
// flush failures and any post-write corruption.
// -----------------------------------------------------------------------------
bool calStore_saveFromResult(const MeasurementResult& result,
                             const char* filename,
                             const char* description) {
    static const char* CAL_SAVE_BACKUP_FILE = "rig_cal.bak";

    if (!result.result_valid) {
        Serial.println("[CalStore] save() rejected: result_valid is false");
        return false;
    }
    if (!s_sd_available) {
        Serial.println("[CalStore] save() failed: SD not available");
        return false;
    }
    if (!filename || !filename[0]) {
        Serial.println("[CalStore] save() failed: null/empty filename");
        return false;
    }
    if (!isSafeCalFilename(filename)) {
        Serial.printf("[CalStore] save() rejected: unsafe filename '%s'\n", filename);
        return false;
    }

    // Snapshot prior calibration so we can restore on failure.
    CalibrationBuffer backup = s_cal;
    bool had_existing_file = SD.exists(filename);

    // Preserve the previous on-card calibration before replacing it. This is
    // the SD-side half of the atomicity contract: if the new write or verify
    // fails, restore both RAM state and the prior file.
    if (SD.exists(CAL_SAVE_BACKUP_FILE)) {
        if (!SD.remove(CAL_SAVE_BACKUP_FILE)) {
            Serial.printf("[CalStore] save() failed: cannot clear scratch '%s'\n",
                          CAL_SAVE_BACKUP_FILE);
            return false;
        }
    }
    if (had_existing_file) {
        if (!copyCalFile(filename, CAL_SAVE_BACKUP_FILE)) {
            Serial.printf("[CalStore] save() failed: cannot back up existing '%s'\n",
                          filename);
            return false;
        }
    }

    // Populate the resident buffer from the measurement result.
    memset(&s_cal, 0, sizeof(s_cal));
    s_cal.loaded               = true;
    s_cal.fft_size             = result.fft_size;
    s_cal.fft_mode             = result.fft_mode;
    s_cal.sample_rate          = SAMPLE_RATE;
    s_cal.window_function      = result.window_function;
    s_cal.line_in_level        = result.line_in_level;
    s_cal.type                 = CalibrationType::EXTERNAL_LOOPBACK;
    s_cal.capture_timestamp_ms = millis();

    // Sanitise the user-provided description.
    const char* desc_in = (description && description[0]) ? description : "loopback";
    // Bounded scan to detect truncation without reading past the 46th byte —
    // mirrors strncpy(... 45)'s read window so we do not introduce a new
    // OOB-read trust boundary for callers that pass non-null-terminated buffers.
    size_t desc_scan = 0;
    while (desc_scan <= 45 && desc_in[desc_scan] != '\0') desc_scan++;
    if (desc_scan > 45) {
        Serial.println("[CalStore] Warning: description longer than 45 chars; truncated");
    }
    strncpy(s_cal.description, desc_in, 45);
    s_cal.description[45] = '\0';
    for (int i = 0; i < 45; i++) {
        unsigned char c = (unsigned char)s_cal.description[i];
        if (c == 0) break;
        if (c < 0x20 || c == 0x7F || c > 0x7E) s_cal.description[i] = '?';
    }

    // Copy correction arrays. Per-bin validity: coherence must be finite and
    // >= CAL_MIN_COH_FOR_BIN, and the TF / phase values must be finite.
    int valid_count = 0;
    for (int k = 0; k < FFT_BINS; k++) {
        if (isfinite(result.coherence[k]) &&
            result.coherence[k] >= CAL_MIN_COH_FOR_BIN &&
            isfinite(result.tf_raw_mag_db[k]) &&
            isfinite(result.phase_unwrapped[k])) {
            s_cal.cal_mag_db   [k] = result.tf_raw_mag_db   [k];
            s_cal.cal_phase_rad[k] = result.phase_unwrapped [k];
            s_cal.bin_valid    [k] = true;
            valid_count++;
        } else {
            s_cal.cal_mag_db   [k] = 0.0f;                  // identity: no correction
            s_cal.cal_phase_rad[k] = 0.0f;
            s_cal.bin_valid    [k] = false;
        }
    }

    Serial.printf("[CalStore] Calibration built: %d/%d bins valid (coherence >= %.2f)\n",
                  valid_count, FFT_BINS, CAL_MIN_COH_FOR_BIN);

    // Serialise to a stack buffer
    uint8_t buf[CAL_FILE_SIZE];
    serializeToBuffer(buf);

    // Explicit remove, check return.
    if (had_existing_file) {
        if (!SD.remove(filename)) {
            Serial.printf("[CalStore] save() failed: cannot remove existing '%s'\n", filename);
            // HIGH-2 contract: every SD.remove() return is checked. The backup
            // cleanup is best-effort (we are already in a failure branch and the
            // backup may legitimately not exist), but a silent failure here can
            // leave a stale '.bak' on the card that confuses the next save.
            if (had_existing_file && SD.exists(CAL_SAVE_BACKUP_FILE)) {
                if (!SD.remove(CAL_SAVE_BACKUP_FILE)) {
                    Serial.printf("[CalStore] save() warning: scratch '%s' left on SD\n",
                                  CAL_SAVE_BACKUP_FILE);
                }
            }
            s_cal = backup;
            return false;
        }
    }

    File f = SD.open(filename, FILE_WRITE);
    if (!f) {
        Serial.printf("[CalStore] save() failed: cannot create '%s'\n", filename);
        if (had_existing_file) restoreCalBackup(filename, CAL_SAVE_BACKUP_FILE);
        s_cal = backup;
        return false;
    }
    size_t n_written = f.write(buf, CAL_FILE_SIZE);
    f.close();

    if (n_written != CAL_FILE_SIZE) {
        Serial.printf("[CalStore] save() failed: wrote %u bytes (expected %lu)\n",
                      (unsigned)n_written, (unsigned long)CAL_FILE_SIZE);
        // Best-effort cleanup of the partial file, then restore prior file.
        if (had_existing_file) {
            restoreCalBackup(filename, CAL_SAVE_BACKUP_FILE);
        } else {
            SD.remove(filename);
        }
        s_cal = backup;
        return false;
    }

    // Verify by reading back the CRC. Catches deferred flush failures.
    {
        File vf = SD.open(filename, FILE_READ);
        if (!vf) {
            Serial.printf("[CalStore] save() failed: cannot reopen for verify '%s'\n", filename);
            if (had_existing_file) {
                restoreCalBackup(filename, CAL_SAVE_BACKUP_FILE);
            } else {
                SD.remove(filename);
            }
            s_cal = backup;
            return false;
        }
        bool size_ok = ((uint32_t)vf.size() == CAL_FILE_SIZE);
        if (!size_ok) {
            Serial.printf("[CalStore] save() failed: verify size %lu (expected %lu)\n",
                          (unsigned long)vf.size(), (unsigned long)CAL_FILE_SIZE);
            vf.close();
            if (had_existing_file) {
                restoreCalBackup(filename, CAL_SAVE_BACKUP_FILE);
            } else {
                SD.remove(filename);
            }
            s_cal = backup;
            return false;
        }
        uint8_t crc_bytes[4];
        vf.seek(OFF_CRC32);
        int crc_read = vf.read(crc_bytes, 4);
        vf.close();
        if (crc_read != 4) {
            Serial.println("[CalStore] save() failed: verify CRC read short");
            if (had_existing_file) {
                restoreCalBackup(filename, CAL_SAVE_BACKUP_FILE);
            } else {
                SD.remove(filename);
            }
            s_cal = backup;
            return false;
        }
        uint32_t verify_crc   = readU32(crc_bytes);
        uint32_t expected_crc = readU32(buf + OFF_CRC32);
        if (verify_crc != expected_crc) {
            Serial.printf("[CalStore] save() failed: verify CRC mismatch "
                          "(stored=0x%08lX expected=0x%08lX)\n",
                          (unsigned long)verify_crc, (unsigned long)expected_crc);
            if (had_existing_file) {
                restoreCalBackup(filename, CAL_SAVE_BACKUP_FILE);
            } else {
                SD.remove(filename);
            }
            s_cal = backup;
            return false;
        }
    }

    if (had_existing_file && SD.exists(CAL_SAVE_BACKUP_FILE)) {
        if (!SD.remove(CAL_SAVE_BACKUP_FILE)) {
            Serial.printf("[CalStore] save() warning: scratch '%s' left on SD\n",
                          CAL_SAVE_BACKUP_FILE);
        }
    }

    Serial.printf("[CalStore] Calibration saved to '%s' (%lu bytes, verified)\n",
                  filename, (unsigned long)CAL_FILE_SIZE);
    return true;
}


// -----------------------------------------------------------------------------
// calStore_isValid(meas_fft_mode, fft_size, sample_rate, window, line_in_level)
//
// FftMode quality ordering: MODE_LIVE(0) < MODE_PRECISION(1) < MODE_LF(2).
// The numeric values are documented in measurement_core.h with an ordering
// invariant. A future renumbering would silently invert this logic, so we
// also static_assert the invariant below.
// -----------------------------------------------------------------------------
static_assert((int)FftMode::MODE_LIVE      == 0, "FftMode ordering invariant broken");
static_assert((int)FftMode::MODE_PRECISION == 1, "FftMode ordering invariant broken");
static_assert((int)FftMode::MODE_LF        == 2, "FftMode ordering invariant broken");

CalibrationValidity calStore_isValid(FftMode        meas_fft_mode,
                                     uint16_t       fft_size,
                                     uint32_t       sample_rate,
                                     WindowFunction window,
                                     uint8_t        line_in_level) {
    if (!s_cal.loaded) return CalibrationValidity::MISSING;

    // Hard mismatch checks. FFT size, sample rate, and window function
    // differences cause systematic per-bin errors that cannot be corrected.
    if (s_cal.fft_size        != fft_size)    return CalibrationValidity::HARD_MISMATCH;
    if (s_cal.sample_rate     != sample_rate) return CalibrationValidity::HARD_MISMATCH;
    if (s_cal.window_function != window)      return CalibrationValidity::HARD_MISMATCH;

    int cal_quality  = (int)s_cal.fft_mode;
    int meas_quality = (int)meas_fft_mode;
    if (cal_quality < meas_quality) {
        // e.g. MODE_LIVE cal applied to MODE_PRECISION measurement
        return CalibrationValidity::HARD_MISMATCH;
    }

    // Soft mismatch: line-in level differs.
    if (s_cal.line_in_level != line_in_level) return CalibrationValidity::SOFT_MISMATCH;

    // Higher-quality calibration applied to lower-quality measurement is
    // conservative; report as soft mismatch for visibility.
    if (cal_quality > meas_quality) return CalibrationValidity::SOFT_MISMATCH;

    return CalibrationValidity::VALID;
}


// -----------------------------------------------------------------------------
// calStore_getBuffer()
// -----------------------------------------------------------------------------
const CalibrationBuffer& calStore_getBuffer() {
    return s_cal;
}


// -----------------------------------------------------------------------------
// calStore_isLoaded()
// -----------------------------------------------------------------------------
bool calStore_isLoaded() {
    return s_cal.loaded;
}


// -----------------------------------------------------------------------------
// calStore_getDescription()
// -----------------------------------------------------------------------------
const char* calStore_getDescription() {
    return s_cal.loaded ? s_cal.description : "none";
}


// -----------------------------------------------------------------------------
// calStore_clear()
// -----------------------------------------------------------------------------
void calStore_clear() {
    memset(&s_cal, 0, sizeof(s_cal));
    s_cal.loaded = false;
    Serial.println("[CalStore] Calibration cleared. Operating uncalibrated.");
}
