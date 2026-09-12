// =============================================================================
// display_engine.cpp     —   Guitar Rig Analyzer
// =============================================================================
// All visual output to the RA8875-driven 800×480 IPS display.
//
// CHANGELOG v0.2.1     (last functional change — no logic changes since)
// ----------------
// • Variable and comment language updated throughout: "source" and "return"
//   now consistently refer to SOURCE_NODE and RETURN_NODE signal nodes.
//   Physical channel numbers do not appear in this file at all — the display
//   engine works purely with AudioFrame data and has no knowledge of I2S
//   channel assignments.
// • LOW SIGNAL warning site annotated with tf_persistence_active note:
//   future contributors can use that flag to add a secondary visual indicator
//   (e.g. a dim curve colour, or a small "H" marker for "history") when the
//   curve contains preserved EMA data rather than live measurements.
// • Headphone passthrough reference in the monitoring comment updated to
//   match the "temporary dev behaviour" framing in audio_engine.cpp.
// • No functional changes from v0.2.0.
// =============================================================================


// =============================================================================
// CONDITIONAL COMPILATION — RA8875 (SPI) backend
// =============================================================================
// This entire translation unit is compiled ONLY when DISPLAY_TARGET selects this
// backend. Authority: docs/adr/ADR-001-display-architecture.md.
//
// WHY THE GUARD IS HERE AND NOT JUST IN presentation.cpp: an Arduino/arduino-cli
// build compiles EVERY .cpp in the sketch folder, whether or not anything
// includes its header. Without this guard, selecting a different DISPLAY_TARGET
// would still compile and link the Adafruit RA8875 and GFX libraries,
// so DISPLAY_TARGET_NONE would not actually be free and the unselected backend
// would remain a build dependency. Verified by compile, not assumed.
//
// The guard deliberately wraps the #includes too — the include itself is the
// dependency being removed.
//
// Nothing else in the firmware calls into this file directly. The application
// and the validation harness both go through presentation_* (display_engine.h is
// reached only by presentation.cpp's matching arm).
// =============================================================================

#include "config.h"

#if DISPLAY_TARGET == DISPLAY_TARGET_RA8875

#include "display_engine.h"
#include "measurement_core.h"
#include "insights_engine.h"
#include <Adafruit_RA8875.h>
#include <math.h>


// =============================================================================
// RA8875 INSTANCE
// =============================================================================
// SPI bus is shared with SD. The Audio Shield does not use SPI (it uses I2S
// and I2C). The RA8875 library asserts RA8875_CS_PIN when communicating and
// releases it between operations — the SD library does the same with its CS.
static Adafruit_RA8875 tft(RA8875_CS_PIN, RA8875_RESET_PIN);


// =============================================================================
// PREVIOUS-CURVE STATE
// =============================================================================
// Stores Y pixel positions from the last drawn frame for erase-before-redraw.
// One entry per horizontal pixel column. ~4 KB RAM. Acceptable trade for
// flicker-free updates without a full screen clear on every frame.
static int16_t s_prev_source_y[GRAPH_W];       // Last SOURCE_NODE spectrum curve
static int16_t s_prev_return_y[GRAPH_W];       // Last RETURN_NODE spectrum curve
static int16_t s_prev_tf_y        [GRAPH_W];   // Last RIG CHANGE curve Y positions
static bool      s_prev_tf_valid[GRAPH_W];   // Whether each pixel of previous curve was finite


static bool s_confidence_warning_visible = false;
static bool s_first_update = true;

// Absent-display guard (added 2026-09-05). False until displayEngine_init()
// has fully succeeded; every public entry point that talks to the RA8875
// no-ops while it is false. Without this, an absent panel still gets driven
// over SPI and Adafruit_RA8875::waitPoll() spins on a status register that
// never satisfies — measured at ~2.2 s per displayEngine_update() call,
// throttling the live audio path 23.6x (see ai/journal.md 2026-09-05 (9)).
static bool s_display_ok = false;


// =============================================================================
// COORDINATE MAPPING HELPERS
//
// FIX [nan-coords]: every helper guards against non-finite input. Arduino's
// constrain() macro returns NaN unchanged (both '<' and '>' yield false on
// NaN), and (int)NaN is undefined behaviour on ARMv7-M — in practice it
// produces 0 or INT_MIN, which the RA8875 then happily treats as a real
// pixel coordinate and may draw outside the framebuffer. Filtering at the
// boundary stops the cascade.
// =============================================================================
static_assert(SPEC_FREQ_MIN > 0.0f && SPEC_FREQ_MAX > SPEC_FREQ_MIN,
              "SPEC_FREQ_MIN must be > 0 and < SPEC_FREQ_MAX (log scale).");
static_assert(SPEC_DB_MAX > SPEC_DB_MIN, "SPEC_DB_MAX must be > SPEC_DB_MIN.");
static_assert(TF_DB_MAX > TF_DB_MIN,     "TF_DB_MAX must be > TF_DB_MIN.");


// Log-frequency → X pixel. Non-finite input maps to SPEC_FREQ_MIN.
static inline int freqToX(float freq_hz) {
     if (!isfinite(freq_hz)) freq_hz = SPEC_FREQ_MIN;
     float f = constrain(freq_hz, SPEC_FREQ_MIN, SPEC_FREQ_MAX);
     float t = log10f(f / SPEC_FREQ_MIN) / log10f(SPEC_FREQ_MAX / SPEC_FREQ_MIN);
     int x = GRAPH_MARGIN_LEFT + (int)(t * (float)(GRAPH_W - 1));
     if (x < GRAPH_MARGIN_LEFT)              x = GRAPH_MARGIN_LEFT;
     if (x > GRAPH_MARGIN_LEFT + GRAPH_W - 1) x = GRAPH_MARGIN_LEFT + GRAPH_W - 1;
     return x;
}


// dBFS → Y pixel within the spectrum panel. Non-finite input maps to floor.
// FIX [off-by-one]: previously the multiplier was SPEC_GRAPH_H, so t=1.0
// produced Y = SPEC_GRAPH_Y + SPEC_GRAPH_H — one pixel below the panel,
// painting onto the next panel's first row. Multiplier is (H-1); the result
// is also explicitly clamped to the panel rectangle.
static inline int dbToSpecY(float db_fs) {
     if (!isfinite(db_fs)) db_fs = SPEC_DB_MIN;
     float db = constrain(db_fs, SPEC_DB_MIN, SPEC_DB_MAX);
     float t  = (SPEC_DB_MAX - db) / (SPEC_DB_MAX - SPEC_DB_MIN);
     int y = SPEC_GRAPH_Y + (int)(t * (float)(SPEC_GRAPH_H - 1));
     if (y < SPEC_GRAPH_Y)                  y = SPEC_GRAPH_Y;
     if (y > SPEC_GRAPH_Y + SPEC_GRAPH_H - 1) y = SPEC_GRAPH_Y + SPEC_GRAPH_H - 1;
     return y;
}


// Transfer function dB → Y pixel within the RIG CHANGE panel.
// TF_DB_MAX → top, 0 dB → centre, TF_DB_MIN → bottom.
// Non-finite input maps to centre (no special vertical bias).
static inline int dbToTfY(float db) {
     if (!isfinite(db)) db = 0.0f;
     float db_c = constrain(db, TF_DB_MIN, TF_DB_MAX);
     float t    = (TF_DB_MAX - db_c) / (TF_DB_MAX - TF_DB_MIN);
     int y = TF_GRAPH_Y + (int)(t * (float)(TF_GRAPH_H - 1));
     if (y < TF_GRAPH_Y)                  y = TF_GRAPH_Y;
     if (y > TF_GRAPH_Y + TF_GRAPH_H - 1) y = TF_GRAPH_Y + TF_GRAPH_H - 1;
     return y;
}


// =============================================================================
// STATIC CHROME — drawn once at init
// =============================================================================


static void drawPanelDividers() {
     tft.drawLine(0, SPECTRUM_PANEL_Y - 1,
                   DISPLAY_WIDTH - 1, SPECTRUM_PANEL_Y - 1, COL_SEPARATOR);
     tft.drawLine(0, TF_PANEL_Y - 1,
                   DISPLAY_WIDTH - 1, TF_PANEL_Y - 1, COL_SEPARATOR);
}


// Frequency tick marks and labels — shared between spectrum and RIG CHANGE panels.
// Labels cover the tonal regions a guitarist thinks about:
//    100–200 Hz: bass weight | 500 Hz: low-mid clarity | 1–2 kHz: presence
//       5–10 kHz: bite and attack | 20 kHz: air ceiling
static void drawFreqAxisLabels(int bottom_y) {
     struct { float hz; const char* label; } ticks[] = {
            { 100,    "100" }, { 200,         "200" }, { 500,   "500" },
            { 1000,   "1k"       }, { 2000,   "2k"   }, { 5000, "5k"   },
            { 10000, "10k" }, { 20000, "20k" },
     };
     const int n = sizeof(ticks) / sizeof(ticks[0]);
     for (int i = 0; i < n; i++) {
            int x = freqToX(ticks[i].hz);
            tft.graphicsMode();
            tft.drawLine(x, bottom_y, x, bottom_y + 4, COL_LABEL);
            tft.textMode();
            tft.textColor(COL_LABEL, COL_BLACK);
            int lw = strlen(ticks[i].label) * 6;
            tft.textSetCursor(x - lw / 2, bottom_y + 5);
            tft.textWrite(ticks[i].label);
     }
     tft.graphicsMode();
}


static void drawSpectrumChrome() {
     struct { float db; const char* label; } lines[] = {
            { -20, "-20" }, { -40, "-40" }, { -60, "-60" }, { -80, "-80" }
     };
     const int n = sizeof(lines) / sizeof(lines[0]);
     for (int i = 0; i < n; i++) {
            int y = dbToSpecY(lines[i].db);
            tft.graphicsMode();
            tft.drawLine(GRAPH_MARGIN_LEFT, y,
                             GRAPH_MARGIN_LEFT + GRAPH_W, y, COL_GRID);
            tft.textMode();
            tft.textColor(COL_LABEL, COL_BLACK);
            tft.textSetCursor(2, y - 8);
            tft.textWrite(lines[i].label);
     }
     // Panel title with inline colour legend
     tft.textMode();
     tft.textColor(COL_LIGHT_GREY, COL_BLACK);
     tft.textSetCursor(GRAPH_MARGIN_LEFT + 4, SPECTRUM_PANEL_Y + 2);
     tft.textWrite("SPECTRUM            ");
     tft.textColor(COL_SOURCE, COL_BLACK);
     tft.textWrite("source");
     tft.textColor(COL_LIGHT_GREY, COL_BLACK);
     tft.textWrite("         /    ");
     tft.textColor(COL_RETURN, COL_BLACK);
     tft.textWrite("return");
    tft.graphicsMode();
    drawFreqAxisLabels(SPEC_GRAPH_Y + SPEC_GRAPH_H);
}


// RIG CHANGE panel chrome.
// "RIG CHANGE [dB]" is the player-facing label. The engineering description
// is: H_dB[k] = 20 * log10( RETURN_NODE_magnitude[k] / SOURCE_NODE_magnitude[k] )
// 0 dB centre line = "rig passes this frequency without change."
static void drawRigChangeChrome() {
    struct { float db; const char* label; bool is_zero; } lines[] = {
         { -12, "-12", false }, { -6, "-6", false },
         {    0,    "0", true   },
         {   +6,   "+6", false }, { +12, "+12", false },
    };
    const int n = sizeof(lines) / sizeof(lines[0]);
    for (int i = 0; i < n; i++) {
         int y = dbToTfY(lines[i].db);
         tft.graphicsMode();
         uint16_t col = lines[i].is_zero ? COL_MID_GREY : COL_GRID;
         tft.drawLine(GRAPH_MARGIN_LEFT, y,
                        GRAPH_MARGIN_LEFT + GRAPH_W, y, col);
         tft.textMode();
         tft.textColor(COL_LABEL, COL_BLACK);
         tft.textSetCursor(2, y - 8);
         tft.textWrite(lines[i].label);
    }
    tft.textMode();
    tft.textColor(COL_LIGHT_GREY, COL_BLACK);
    tft.textSetCursor(GRAPH_MARGIN_LEFT + 4, TF_PANEL_Y + 2);
    tft.textWrite("RIG CHANGE        [dB]   0 = no change");
    tft.graphicsMode();
    drawFreqAxisLabels(TF_GRAPH_Y + TF_GRAPH_H);
}


static void drawMeterLabels() {
    tft.textMode();
    tft.textColor(COL_SOURCE, COL_BLACK);
    tft.textSetCursor(METER_SOURCE_X, METER_PANEL_Y + 4);
    tft.textWrite("SOURCE");
    tft.textColor(COL_RETURN, COL_BLACK);
    tft.textSetCursor(METER_RETURN_X, METER_PANEL_Y + 4);
    tft.textWrite("RETURN");
    tft.graphicsMode();
}


// =============================================================================
// LIVE ELEMENT UPDATES — called every displayEngine_update()
// =============================================================================


// drawOneBar: draw a single level meter bar.
// Parameters:
//    x_start     — left edge of bar area
//    db_val      — current level in dBFS
//    bar_col     — colour for active (signal) portion
//    clipping — if true, use COL_CLIP instead
static void drawOneBar(int x_start, float db_val,
                           uint16_t bar_col, bool clipping) {
     int y     = METER_PANEL_Y + METER_BAR_Y;
     if (!isfinite(db_val)) db_val = METER_DB_MIN;
     float t = constrain(
            (db_val - METER_DB_MIN) / (METER_DB_MAX - METER_DB_MIN), 0.0f, 1.0f);
     int bar_px = (int)(t * METER_BAR_W);
     uint16_t col = clipping ? COL_CLIP : bar_col;
     // Active portion
     if (bar_px > 0)
            tft.fillRect(x_start, y, bar_px, METER_BAR_H, col);
     // Empty portion
     if (bar_px < METER_BAR_W)
            tft.fillRect(x_start + bar_px, y,
                         METER_BAR_W - bar_px, METER_BAR_H, COL_DARK_GREY);
     // Numeric readout
     char buf[14];
     if (db_val <= METER_DB_MIN + 1.0f)
            snprintf(buf, sizeof(buf), "    ---   ");
     else
            snprintf(buf, sizeof(buf), "%+5.1fdBFS", db_val);
     tft.textMode();
     tft.textColor(clipping ? COL_CLIP : COL_WHITE, COL_BLACK);
     tft.textSetCursor(x_start + METER_BAR_W + 6, y);
     tft.textWrite(buf);
     tft.graphicsMode();
}


static void updateMeters(const AudioFrame* frame) {
     // SOURCE_NODE level meter
     drawOneBar(METER_SOURCE_X + 54, frame->peak_source_dbfs,
                   COL_SOURCE, frame->source_clipping);
     // RETURN_NODE level meter
     drawOneBar(METER_RETURN_X + 54, frame->peak_return_dbfs,
                   COL_RETURN, frame->return_clipping);
}


// updateSpectrumCurves: erase old SOURCE_NODE and RETURN_NODE spectrum curves,
// draw new ones. Each curve is one polyline connecting GRAPH_W data points,
// rendered as GRAPH_W-1 line segments.
static void updateSpectrumCurves(const AudioFrame* frame) {


    int16_t new_source_y[GRAPH_W];
    int16_t new_return_y[GRAPH_W];


    // Map each pixel column to its frequency, find the FFT bin, convert to Y.
    // FIX [nan-coords]: filter NaN/Inf out of the linear magnitudes before
    // converting to dBFS. audioEngine_linearToDbfs returns -120 for <=0, but
    // NaN inputs slip past its early return because NaN comparisons are false.
    for (int px = 0; px < GRAPH_W; px++) {
           float t       = (float)px / (float)(GRAPH_W - 1);
           float freq = SPEC_FREQ_MIN * powf(SPEC_FREQ_MAX / SPEC_FREQ_MIN, t);
           int     bin   = audioEngine_hzToBin(freq);
           float src_lin = frame->fft_source[bin];
           float ret_lin = frame->fft_return[bin];
           if (!isfinite(src_lin)) src_lin = 0.0f;
           if (!isfinite(ret_lin)) ret_lin = 0.0f;
           new_source_y[px] = dbToSpecY(audioEngine_linearToDbfs(src_lin));
           new_return_y[px] = dbToSpecY(audioEngine_linearToDbfs(ret_lin));
    }


    // Erase previous curves
    if (!s_first_update) {
           for (int px = 1; px < GRAPH_W; px++) {
                 int x = GRAPH_MARGIN_LEFT + px;
                 tft.drawLine(x-1, s_prev_source_y[px-1], x, s_prev_source_y[px], COL_BLACK);
                 tft.drawLine(x-1, s_prev_return_y[px-1], x, s_prev_return_y[px], COL_BLACK);
           }
    }


    // Draw new curves
    for (int px = 1; px < GRAPH_W; px++) {
           int x = GRAPH_MARGIN_LEFT + px;
           tft.drawLine(x-1, new_source_y[px-1], x, new_source_y[px], COL_SOURCE);
           tft.drawLine(x-1, new_return_y[px-1], x, new_return_y[px], COL_RETURN);
    }


    memcpy(s_prev_source_y, new_source_y, sizeof(new_source_y));
    memcpy(s_prev_return_y, new_return_y, sizeof(new_return_y));
}


// updateTFCurve: erase old RIG CHANGE curve, redraw 0 dB line, draw new curve.
// NAN bins produce pen-lift gaps — visually communicates "no data here."
// Manages LOW SIGNAL warning overlay based on tf_confidence.
static void updateTFCurve(const AudioFrame* frame) {


    int16_t new_tf_y          [GRAPH_W];
    bool         new_tf_valid[GRAPH_W];


    for (int px = 0; px < GRAPH_W; px++) {
           float t       = (float)px / (float)(GRAPH_W - 1);
           float freq = SPEC_FREQ_MIN * powf(SPEC_FREQ_MAX / SPEC_FREQ_MIN, t);
           int     bin   = audioEngine_hzToBin(freq);
           float tf      = frame->tf_db[bin];
           // FIX [nan-coords]: isfinite catches NaN and +/-Inf — the prior
           // code gated on isnan only, leaving +Inf to flow into (int) casts.
     if (!isfinite(tf)) {
         new_tf_valid[px] = false;
         new_tf_y[px]        = (int16_t)dbToTfY(0.0f);
     } else {
         new_tf_valid[px] = true;
         new_tf_y[px]        = (int16_t)dbToTfY(tf);
     }
}


// Erase old TF curve.
// Only erase segments where the previous frame actually drew a line,
// i.e. both endpoints were valid. Drawing black through NAN gaps would
// wipe the 0 dB line or other chrome that was never covered by the curve.
if (!s_first_update) {
     for (int px = 1; px < GRAPH_W; px++) {
         if (s_prev_tf_valid[px] && s_prev_tf_valid[px-1]) {
                int x = GRAPH_MARGIN_LEFT + px;
                tft.drawLine(x-1, s_prev_tf_y[px-1], x, s_prev_tf_y[px], COL_BLACK);
         }
     }
     // Redraw 0 dB reference line (erase may have wiped it).
     // Must happen before drawing new curve so the curve can cross over it.
     int y0 = dbToTfY(0.0f);
     tft.drawLine(GRAPH_MARGIN_LEFT, y0,
                     GRAPH_MARGIN_LEFT + GRAPH_W, y0, COL_MID_GREY);
}


// Draw new TF curve (pen-lift on NAN gaps)
for (int px = 1; px < GRAPH_W; px++) {
     if (new_tf_valid[px] && new_tf_valid[px-1]) {
         int x = GRAPH_MARGIN_LEFT + px;
         tft.drawLine(x-1, new_tf_y[px-1], x, new_tf_y[px], COL_TRANSFER);
     }
}


memcpy(s_prev_tf_y,         new_tf_y,     sizeof(new_tf_y));
memcpy(s_prev_tf_valid, new_tf_valid, sizeof(new_tf_valid));


// --- LOW SIGNAL confidence warning ---
// Shown when tf_confidence < TF_CONFIDENCE_THRESHOLD.
// Cleared automatically when confidence recovers.
//
// frame->tf_persistence_active is available here for future use.
// When true, some portion of the displayed curve contains preserved EMA
// history rather than live measurements. A future visual refinement could
// dim the TF curve colour or add a small "H" (history) marker when
// tf_persistence_active is true but confidence is still above threshold
    // (i.e. some bins are live, some are preserved). For now we do not add
    // a separate indicator — the LOW SIGNAL warning covers the more serious
    // case, and the EMA persistence is the intended "sticky instrument" feel.


    bool show_warning = (frame->tf_confidence < TF_CONFIDENCE_THRESHOLD);


    if (show_warning && !s_confidence_warning_visible) {
        // Draw warning text in centre of RIG CHANGE panel
        int wx = DISPLAY_WIDTH / 2 - 48;
        int wy = TF_GRAPH_Y + TF_GRAPH_H / 2 - 8;
        tft.textMode();
        tft.textColor(COL_WARNING, COL_BLACK);
        tft.textSetCursor(wx, wy);
        tft.textWrite("LOW SIGNAL");
        tft.graphicsMode();
        s_confidence_warning_visible = true;


    } else if (!show_warning && s_confidence_warning_visible) {
        // Clear warning and restore any grid lines covered by the clear rect.
        // NOTE: if future code adds annotations near the panel centre, expand
        // this clear rect to cover them, or switch to a full panel fill/redraw.
        int wx = DISPLAY_WIDTH / 2 - 48;
        int wy = TF_GRAPH_Y + TF_GRAPH_H / 2 - 8;
        tft.fillRect(wx - 2, wy - 2, 100, 20, COL_BLACK);
        // Restore the 0 dB line if it falls within the cleared area
        int y0 = dbToTfY(0.0f);
        tft.drawLine(GRAPH_MARGIN_LEFT, y0,
                        GRAPH_MARGIN_LEFT + GRAPH_W, y0, COL_MID_GREY);
        s_confidence_warning_visible = false;
    }
}


// =============================================================================
// PUBLIC IMPLEMENTATIONS
// =============================================================================


bool displayEngine_init() {


    s_display_ok = false;   // Stays false on every failure path below.

    if (!tft.begin(RA8875_800x480)) {
        Serial.println("[DisplayEngine] ERROR: RA8875 not found on SPI.");
        Serial.printf ("[DisplayEngine] Check CS=%d, RESET=%d, SCK=13, MOSI=11, MISO=12\n",
                          RA8875_CS_PIN, RA8875_RESET_PIN);
        return false;
    }


    tft.displayOn(true);
    tft.GPIOX(true);                                  // Backlight transistor enable
    tft.PWM1config(true, RA8875_PWM_CLK_DIV1024);
    tft.PWM1out(255);                               // Full brightness — lower for dark rooms
    tft.fillScreen(COL_BLACK);
    tft.graphicsMode();


    // Draw all static chrome
    drawPanelDividers();
    drawMeterLabels();
    drawSpectrumChrome();
    drawRigChangeChrome();


    // Initialise previous-curve arrays to neutral positions
    int spec_floor = dbToSpecY(SPEC_DB_MIN);
    int tf_centre     = dbToTfY(0.0f);
    for (int px = 0; px < GRAPH_W; px++) {
        s_prev_source_y[px] = spec_floor;
        s_prev_return_y[px] = spec_floor;
        s_prev_tf_y       [px] = tf_centre;
        s_prev_tf_valid[px] = false;
    }


    s_first_update                  = true;
    s_confidence_warning_visible = false;


    s_display_ok = true;    // Only set once the panel is fully up and drawn.
    Serial.println("[DisplayEngine] RA8875 ready. Layout drawn.");
    return true;
}


void displayEngine_update(const AudioFrame* frame) {
    if (!s_display_ok) return;
    if (frame == nullptr) return;
    updateMeters(frame);
    updateSpectrumCurves(frame);
    updateTFCurve(frame);
    s_first_update = false;
}


void displayEngine_drawStatusMessage(const char* msg) {
    if (!s_display_ok) return;
    // Clear a fixed region in the centre of the meter panel (top band).
    // SOURCE and RETURN labels (far left/right) are left untouched.
    char safe_msg[48];
    strncpy(safe_msg, msg ? msg : "", sizeof(safe_msg) - 1);
    safe_msg[sizeof(safe_msg) - 1] = '\0';
    tft.fillRect(200, METER_PANEL_Y + 4, 370, 18, COL_BLACK);
    tft.textMode();
    tft.textColor(COL_WHITE, COL_BLACK);
    tft.textSetCursor(202, METER_PANEL_Y + 4);
    tft.textWrite(safe_msg);
    tft.graphicsMode();
}
// =============================================================================
// RESULT VIEW — private helpers
// =============================================================================


// Helper: map ResultQuality → badge colour
static uint16_t qualityColour(ResultQuality q) {
    switch (q) {
           case ResultQuality::EXCELLENT: return COL_QUALITY_EXCELLENT;
           case ResultQuality::GOOD:          return COL_QUALITY_GOOD;
           case ResultQuality::MARGINAL:      return COL_QUALITY_MARGINAL;
           default:                           return COL_QUALITY_POOR;
    }
}


// Helper: draw the measured TF curve from a float array into the TF panel.
// Identical NaN-aware pen-lift logic as updateTFCurve() in live mode.
// Does NOT touch s_prev_tf_y / s_prev_tf_valid — those are for the live path.
static void drawResultTFCurve(const float* tf_cal_mag_db) {
    int16_t y          [GRAPH_W];
    bool         valid[GRAPH_W];


    // FIX [magic-bins]: previously hardcoded 512 — now uses FFT_BINS so a
    // future config change does not silently corrupt the index. Also guards
    // non-finite values (NaN and ±Inf) before passing to dbToTfY.
    const float canonical_bin_hz = (float)SAMPLE_RATE / (float)(FFT_BINS * 2);
    for (int px = 0; px < GRAPH_W; px++) {
           float t        = (float)px / (float)(GRAPH_W - 1);
           float freq = SPEC_FREQ_MIN * powf(SPEC_FREQ_MAX / SPEC_FREQ_MIN, t);
           int     k    = (int)(freq / canonical_bin_hz + 0.5f);
           if (k < 0)              k = 0;
           if (k >= FFT_BINS)      k = FFT_BINS - 1;
           float db = tf_cal_mag_db[k];
           if (!isfinite(db)) {
                 valid[px] = false;
                 y[px]       = (int16_t)dbToTfY(0.0f);
           } else {
                 valid[px] = true;
                 y[px]       = (int16_t)dbToTfY(db);
           }
    }


    // Draw with pen-lift on NaN gaps
    for (int px = 1; px < GRAPH_W; px++) {
           if (valid[px] && valid[px-1]) {
                 int x = GRAPH_MARGIN_LEFT + px;
                 tft.drawLine(x-1, y[px-1], x, y[px], COL_TRANSFER);
           }
    }
}
// Helper: render the insight list into the spectrum panel area.
// Spectrum panel chrome is already cleared by the caller.
// Renders up to 5 insights; MEASUREMENT and ADVISORY are colour-coded.
static void drawInsightPanel(const InsightList& insights) {
    const int PANEL_X        = GRAPH_MARGIN_LEFT;
    const int PANEL_Y        = SPECTRUM_PANEL_Y + 2;
    const int LINE_H         = 14;     // px per text line
    const int GAP            = 3;      // px between insights
    const int MAX_SHOW       = 5;
    const int COL_WIDTH      = DISPLAY_WIDTH - GRAPH_MARGIN_LEFT - GRAPH_MARGIN_RIGHT;


    // Header: insight count
    char hdr[64];
    if (insights.quality_gated) {
        snprintf(hdr, sizeof(hdr), "INSIGHTS        %d result(s)     [advisories gated]",
                    insights.count);
    } else {
        snprintf(hdr, sizeof(hdr), "INSIGHTS        %d result(s)",
                    insights.count);
    }
    tft.textMode();
    tft.textColor(COL_LIGHT_GREY, COL_BLACK);
    tft.textSetCursor(PANEL_X, PANEL_Y);
    tft.textWrite(hdr);
    tft.graphicsMode();


    // Separator line under header
    tft.drawLine(PANEL_X, PANEL_Y + LINE_H + 2,
                    PANEL_X + COL_WIDTH, PANEL_Y + LINE_H + 2, COL_SEPARATOR);


    int y = PANEL_Y + LINE_H + 6;
    int shown = 0;
    // FIX [insight-overflow]: compute the footer Y once so the loop can
    // stop rendering before the next insight would overpaint it. Previously
    // the loop only checked MAX_SHOW; 5 long insights (~17 px each) could
    // exceed the panel height and overdraw the footer or adjacent chrome.
    const int insight_footer_y = SPECTRUM_PANEL_Y + SPECTRUM_PANEL_H - LINE_H - 2;
    for (int i = 0; i < insights.count && shown < MAX_SHOW; i++) {
        const Insight& ins = insights.items[i];
        // Would this insight (title + optional detail + gap) cross the footer?
        int est_height = LINE_H + (ins.detail[0] ? LINE_H : 0) + GAP;
        if (y + est_height > insight_footer_y) break;


        // Title colour: severity and mode
        uint16_t title_col =
               (ins.severity == InsightSeverity::ALERT)      ? COL_INSIGHT_ALERT :
               (ins.mode     == InsightMode::ADVISORY)          ? COL_INSIGHT_ADV      :
                                                                   COL_INSIGHT_MEAS;


        // Mode tag: narrow prefix so MEASUREMENT/ADVISORY is always visible
        const char* tag = (ins.mode == InsightMode::MEASUREMENT) ? "M " : "A ";


        // Title line
        char title_line[INSIGHT_TITLE_LEN + 4];
        snprintf(title_line, sizeof(title_line), "%s%s", tag, ins.title);


        tft.textMode();
        tft.textColor(title_col, COL_BLACK);
        tft.textSetCursor(PANEL_X, y);
        tft.textWrite(title_line);
        y += LINE_H;


        // Detail line (truncated — RA8875 font is 8px wide, ~92 chars in panel)
        if (ins.detail[0]) {
            tft.textColor(COL_INSIGHT_DETAIL, COL_BLACK);
            tft.textSetCursor(PANEL_X + 12, y);          // indent under tag
            // Truncate to fit panel width: (COL_WIDTH - 12) / 8 chars ≈ 92
            char detail_line[88];
            strncpy(detail_line, ins.detail, 87);
            detail_line[87] = '\0';
            tft.textWrite(detail_line);
            y += LINE_H;
        }


        tft.graphicsMode();
        y += GAP;
        shown++;
    }


    // Footer hint at bottom of panel (always visible)
    int footer_y = SPECTRUM_PANEL_Y + SPECTRUM_PANEL_H - LINE_H - 2;
    tft.textMode();
    tft.textColor(COL_DARK_GREY, COL_BLACK);
    tft.textSetCursor(PANEL_X, footer_y);
    tft.textWrite("s=save     b=csv   c=cal   m=retest     x=back");
    tft.graphicsMode();
}


// =============================================================================
// PUBLIC: displayEngine_showResult()
// =============================================================================
void displayEngine_showResult(const MeasurementResult& result,
                                  const InsightList& insights) {
    if (!s_display_ok) return;
    // --- Meter panel: quality badge and calibration status ---
    const char* qname =
        (result.result_quality == ResultQuality::EXCELLENT) ? "EXCELLENT" :
        (result.result_quality == ResultQuality::GOOD)                 ? "GOOD"       :
        (result.result_quality == ResultQuality::MARGINAL)             ? "MARGINAL"   :
        (result.result_quality == ResultQuality::POOR)                 ? "POOR"       : "INVALID";
    uint16_t qcol = qualityColour(result.result_quality);
// Clear full meter panel and redraw with result context
tft.fillRect(0, METER_PANEL_Y, DISPLAY_WIDTH, METER_PANEL_H, COL_BLACK);


tft.textMode();
tft.textColor(qcol, COL_BLACK);
tft.textSetCursor(4, METER_PANEL_Y + 4);
tft.textWrite("RESULT");
tft.textSetCursor(80, METER_PANEL_Y + 4);
tft.textWrite(qname);


// Coherence
char coh_str[24];
snprintf(coh_str, sizeof(coh_str), "     coh %.2f", result.mean_coherence);
tft.textColor(COL_LABEL, COL_BLACK);
tft.textWrite(coh_str);


// Calibration applied?
tft.textSetCursor(4, METER_PANEL_Y + 22);
if (result.calibration_applied) {
    tft.textColor(COL_RETURN, COL_BLACK);
    tft.textWrite("CAL ");
    tft.textColor(COL_LABEL, COL_BLACK);
    char cal_str[50];
    strncpy(cal_str, result.calibration_provenance, 49);
    cal_str[49] = '\0';
    tft.textWrite(cal_str);
} else {
    tft.textColor(COL_WARNING, COL_BLACK);
    tft.textWrite("UNCAL");
}


// Timestamp hint
char ts_str[24];
snprintf(ts_str, sizeof(ts_str), "     t=%lus", (unsigned long)(result.timestamp_ms / 1000));
tft.textColor(COL_DARK_GREY, COL_BLACK);
tft.textWrite(ts_str);
tft.graphicsMode();


// --- Spectrum panel: clear and draw insight list ---
tft.fillRect(0, SPECTRUM_PANEL_Y, DISPLAY_WIDTH, SPECTRUM_PANEL_H, COL_BLACK);
drawInsightPanel(insights);


// --- TF panel: redraw chrome, then result curve ---
// Erase only the curve area; leave panel border and labels intact.
tft.fillRect(GRAPH_MARGIN_LEFT, TF_GRAPH_Y,
               GRAPH_W, TF_GRAPH_H, COL_BLACK);
drawRigChangeChrome();     // redraws grid lines and 0 dB reference
    drawResultTFCurve(result.tf_cal_mag_db);


    // Reset erase buffers so restoreLive() knows to do a clean first redraw
    s_first_update = true;


    Serial.println("[DisplayEngine] Result view drawn.");
}


// =============================================================================
// PUBLIC: displayEngine_showAborted()
// =============================================================================
void displayEngine_showAborted(const char* reason) {
    if (!s_display_ok) return;
    // Only update the meter panel — leave spectra/TF visible for context
    tft.fillRect(0, METER_PANEL_Y, DISPLAY_WIDTH, METER_PANEL_H, COL_BLACK);
    tft.textMode();
    tft.textColor(COL_CLIP, COL_BLACK);
    tft.textSetCursor(4, METER_PANEL_Y + 4);
    tft.textWrite("ABORTED");
    tft.textColor(COL_WARNING, COL_BLACK);
    tft.textSetCursor(80, METER_PANEL_Y + 4);
    tft.textWrite(reason ? reason : "unknown reason");
    tft.textColor(COL_DARK_GREY, COL_BLACK);
    tft.textSetCursor(4, METER_PANEL_Y + 22);
    tft.textWrite("Press x to acknowledge and return to live view.");
    tft.graphicsMode();
}


// =============================================================================
// PUBLIC: displayEngine_restoreLive()
// =============================================================================
void displayEngine_restoreLive() {
    if (!s_display_ok) return;
    // Redraw full static chrome for live mode
    tft.fillScreen(COL_BLACK);
    drawPanelDividers();
    drawMeterLabels();
    drawSpectrumChrome();
    drawRigChangeChrome();


    // Reset live-curve erase buffers
    int spec_floor = dbToSpecY(SPEC_DB_MIN);
    int tf_centre     = dbToTfY(0.0f);
    for (int px = 0; px < GRAPH_W; px++) {
        s_prev_source_y[px] = spec_floor;
        s_prev_return_y[px] = spec_floor;
        s_prev_tf_y       [px] = tf_centre;
        s_prev_tf_valid[px] = false;
    }
    s_first_update               = true;
    s_confidence_warning_visible = false;


    Serial.println("[DisplayEngine] Live view restored.");
}


#endif // DISPLAY_TARGET == DISPLAY_TARGET_RA8875
