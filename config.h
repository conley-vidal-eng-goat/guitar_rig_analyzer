// =============================================================================
// config.h   —    Guitar Rig Analyzer   v0.5.0
// =============================================================================
// Central configuration. All hardware pin assignments, tuning constants,
// display geometry, and calibration placeholders live here.
//
// CHANGELOG v0.5.0
// ----------------
// • REMEDIATION PASS 2026-05-15: compile blockers fixed (truncated literals,
//   missing semicolons), NaN/Inf chains blocked across audio_engine /
//   display_engine / signal_generator, atomic calibration save with CRC
//   readback, JSON escapes brought to RFC 8259, filename trust-boundary
//   validation, validation harness made deterministic with bounded deadlines.
//   No constant in this file changed semantically — the constants documented
//   below still apply. See audit/Remediation_Report_2026-05-15.md.
//
// CHANGELOG v0.2.1
// ----------------
// • FIXED: EMA alpha tuning guidance was inverted in the editing guide below.
//   It now correctly states: smaller alpha = smoother/laggier,
//   larger alpha = snappier/noisier.      (The detailed inline comment was already
//   correct; only the quick-reference guide at the top was wrong.)
// • UPDATED: Signal routing constants and comments now use node-based language
//   (SOURCE_NODE, RETURN_NODE) instead of channel-based language (left, right).
//   The current stereo I2S mapping is still used in hardware, but it is now
//   explicitly described as a physical binding of a logical node, not a
//   permanent identity. See SIGNAL ROUTING section below.
// • UPDATED: Headphone passthrough noted as temporary development monitoring
//   behaviour, not final product UX.
//
// EDITING GUIDE     (read this before touching any constant)
// -------------------------------------------------------
// Hardware rewire?             → Change pin assignments in the HARDWARE sections.
// Signal too quiet?            → Increase SGTL5000_LINE_IN_LEVEL (calibrate first).
// Signal clipping?             → Decrease SGTL5000_LINE_IN_LEVEL.
// TF curve too jittery?        → DECREASE TF_SMOOTHING_ALPHA (more smoothing, more lag).
// TF curve too laggy?          → INCREASE TF_SMOOTHING_ALPHA (less smoothing, snappier).
// "LOW SIGNAL" too often?      → Decrease TF_CONFIDENCE_THRESHOLD.
// "LOW SIGNAL" not showing? → Increase TF_CONFIDENCE_THRESHOLD.
// Display too slow?            → Reduce FFT_AVERAGE_COUNT or DISPLAY_UPDATE_EVERY_N_FRAMES.
//
// EMA ALPHA QUICK REFERENCE (this is the most commonly confused parameter)
// -------------------------------------------------------------------------
// TF_SMOOTHING_ALPHA weights the NEW measurement in the running average:
//   new_smoothed = ALPHA * new_measurement + (1 - ALPHA) * old_smoothed
//
//   ALPHA → 0.0 : old history dominates → very smooth, very laggy
//   ALPHA → 1.0 : new measurement dominates → immediate response, very noisy
//
// Recommended starting range: 0.10 – 0.25.
// Do not set above 0.5 for live monitoring use; the curve becomes unreadable.
// =============================================================================


#ifndef CONFIG_H
#define CONFIG_H


#define FIRMWARE_VERSION "0.5.0"


// =============================================================================
// HARDWARE — SPI BUS    (RA8875 display + optional SD)
// =============================================================================
// The Teensy Audio Shield uses I2S (audio data) and I2C (codec control).
// It does NOT use SPI. The SPI bus is therefore free for the RA8875 display
// and microSD, arbitrated by separate active-LOW chip-select lines.
//
// Teensy 4.1 SPI0 (hardware-accelerated):
//   SCK   → pin 13   (shared)
//   MISO → pin 12    (shared)
//   MOSI → pin 11    (shared)
//
// Only one CS may be LOW at a time. Libraries handle this automatically when
// each peripheral is constructed with its own CS pin.
// -----------------------------------------------------------------------------
#define RA8875_CS_PIN       10   // RA8875 chip select (active LOW)
#define RA8875_INT_PIN       9   // RA8875 touch interrupt output (future use)
#define RA8875_RESET_PIN     8   // RA8875 hardware reset (active LOW)


// =============================================================================
// SIGNAL ROUTER — BREADBOARD GPIO ASSIGNMENTS
// =============================================================================
// Teensy 4.1 assignments for docs/breadboard_bringup_v3.md.
// These are breadboard bring-up assignments and are not necessarily the
// permanent production-PCB pin assignments.

#define RELAY_SEND_PIN      14
#define RELAY_RETURN_PIN    15

#define JACK_INSTRUMENT_PIN 16
#define JACK_RIG_SEND_PIN   17
#define JACK_RETURN_TS_PIN  22
#define JACK_RETURN_XLR_PIN 24

#define JACK_DEBOUNCE_MS    50

// =============================================================================
// FEATURE PROMOTION STATE
// =============================================================================
// These features are present in future/staged routing work but are NOT yet
// promoted into the active breadboard firmware.

#define ENABLE_DUT_INJECTION 0
#define ENABLE_MONITOR_MODE 0


// microSD uses the Teensy 4.1 on-board SDIO slot (faster than SPI).
// No SPI CS constant needed. If you add an external SPI SD module, define one.
#define SD_LOG_PREFIX        "rig_log_"
#define CAL_FILE_DEFAULT     "rig_cal.cal"    // Default calibration file on SD root
#define EXPORT_DIR_DEFAULT "exports"           // Subdirectory for JSON and CSV exports


// =============================================================================
// HARDWARE — SGTL5000 / TEENSY AUDIO SHIELD
// =============================================================================
// I2S: audio samples via DMA — driven automatically by the Audio Library.
// I2C: codec register control on pins 18 (SDA) / 19 (SCL) — Wire.begin().
//
// SGTL5000_LINE_IN_LEVEL: integer 0–15, controls the analogue PGA.
//
//   *** CALIBRATION PLACEHOLDER — NOT A FINAL VALUE ***
//   Correct value depends on the OPA1642 buffer output swing and any
//   level-shifting between the buffer and the codec.
//   Target: guitar peaks reaching –6 to –12 dBFS during normal playing.
//   Procedure: play guitar at typical intensity, read peak_source_dbfs in
//   Serial output, adjust level until peaks sit in the target range,
//   verify no clipping on the hardest pick strokes.
// -----------------------------------------------------------------------------
#define SGTL5000_LINE_IN_LEVEL     5      // *** CALIBRATE BEFORE FIELD USE ***
#define SGTL5000_HEADPHONE_VOL     0.5f   // 0.0–1.0. Start conservatively.
// =============================================================================
// SIGNAL ROUTING — LOGICAL NODE DEFINITIONS
// =============================================================================
// The analyzer thinks in terms of logical signal nodes, not physical channels.
// A "node" is a named point in the signal path with a defined role:
//
//   SOURCE_NODE — the exact signal being sent to the rig (pre-rig measurement
//                  point). In the final hardware this comes from the 1/4" TS
//                  instrument input, after the OPA1642 buffer stage.
//
//   RETURN_NODE — the signal coming back from the rig (post-rig measurement
//                  point). In the final hardware this is selectable between
//                  the 1/4" TS return and the XLR return jack.
//
// CURRENT BENCH HARNESS — PHYSICAL BINDING
// -----------------------------------------
// Right now, both nodes are bound to I2S stereo channels because that is the
// only analogue input path available on the bench rig:
//
//   SOURCE_NODE   → SGTL5000 Line In LEFT    (I2S channel 0)
//   RETURN_NODE   → SGTL5000 Line In RIGHT (I2S channel 1)
//
// This binding is temporary. In the final hardware, a signal routing stage
// (relays or CMOS mux, controlled by the signal_router module added in v0.3)
// will connect the selected physical jacks to the codec inputs. At that point,
// the firmware will stop caring about "left" and "right" entirely — it will
// only refer to SOURCE_NODE and RETURN_NODE, and the routing hardware decides
// which jack maps to which.
//
// The constants below define the CURRENT physical binding only.
// Changing them here is the only edit needed to swap channels on the bench.
// They are named to make clear they are bindings, not identities.
// -----------------------------------------------------------------------------
#define SOURCE_NODE_PHYSICAL_CH   0   // I2S channel currently carrying SOURCE_NODE
#define RETURN_NODE_PHYSICAL_CH   1   // I2S channel currently carrying RETURN_NODE


// =============================================================================
// HEADPHONE PASSTHROUGH — DEVELOPMENT MONITORING
// =============================================================================
// Currently: SOURCE_NODE signal → headphone LEFT output
//            RETURN_NODE signal → headphone RIGHT output
//
// *** THIS IS TEMPORARY DEVELOPMENT BEHAVIOUR, NOT THE FINAL UX ***
//
// The final product vision is a selectable monitor output — the player should
// be able to choose what they hear (source only, return only, or a blend).
// The fixed stereo split is convenient for bench verification (you can confirm
// both channels are receiving the right signal by ear) but is not what we
// settled on for the shipped product.
//
// When the signal_router module and touch UI are added (planned v0.3/v0.8),
// this will be replaced by a monitored output with an explicit selection state.
// Until then, the stereo split is acceptable as a development convenience.
// Do not design any hardware around the assumption that this is permanent.
// =============================================================================


// =============================================================================
// AUDIO ENGINE — FFT, AVERAGING, AND SMOOTHING
// =============================================================================


// FFT window size. Must be 1024 for AudioAnalyzeFFT1024.
// Frame duration = 1024 / 44100 ≈ 23.2 ms per raw frame.
// Bin width       = 44100 / 1024 ≈ 43.1 Hz per bin.
// Usable bins     = 512 (indices 0–511, covering 0 to 22,050 Hz).
#define FFT_SIZE      1024
#define SAMPLE_RATE   44100
#define FFT_BINS      (FFT_SIZE / 2)


// --- Linear frame averaging ---
// FFT_AVERAGE_COUNT raw frames are accumulated into a sum, then divided.
// The averaged result is what feeds the transfer function and display.
//
// WHY average source and return separately before dividing?
//   Single pick attacks produce large single-frame spikes in specific bins.
//   Computing the TF from raw frames would show those as false boosts/cuts.
//   Averaging first produces a stable spectral estimate representative of
//   the rig's steady-state frequency response — which is what we care about.
//
// Timing:
//   4 frames × 23.2 ms = 92.8 ms per averaged output block ≈ 10.8 blocks/sec.
//   Display updates every DISPLAY_UPDATE_EVERY_N_FRAMES blocks.
#define FFT_AVERAGE_COUNT     4


// How many averaged output blocks to skip between display redraws.
// 1 → update every block (~92.8 ms, ~10.8 fps) — start here.
// 2 → update every other block (~185 ms, ~5.4 fps) — if display stalls audio.
#define DISPLAY_UPDATE_EVERY_N_FRAMES    1


// Transfer function EMA smoothing coefficient.
// Applied AFTER linear averaging, on computed dB TF values, once per block.
//
//   new_smoothed[k] = ALPHA * raw_tf[k] + (1 - ALPHA) * old_smoothed[k]
//
// *** SEE EDITING GUIDE AT TOP OF FILE FOR TUNING DIRECTION ***
// Smaller ALPHA = more smoothing, more temporal lag (history dominates).
// Larger ALPHA   = less smoothing, faster response (current value dominates).
// Recommended range: 0.10 – 0.25. Default 0.15 is a reasonable starting point.
#define TF_SMOOTHING_ALPHA   0.15f


// Noise floor gate for the TF calculation (linear FFT magnitude, 0.0–1.0).
// Bins whose averaged source magnitude is below this are "unenergised".
// Their tf_db[] entry is set to NAN — the display skips them (curve gap).
// 0.001 ≈ –60 dBFS: below guitar fundamentals, above codec noise floor.
#define TF_SOURCE_GATE   0.001f


// --- TF PERSISTENCE DESIGN DECISION ---
// When a bin is unenergised (below TF_SOURCE_GATE), the EMA smoothing buffer
// for that bin is NOT updated — its last valid value is preserved internally.
//
// This creates a deliberate design trade-off:
//
//   CURRENT BEHAVIOUR ("sticky instrument"):
//     The engine retains the last known response for each bin.
//     If the player stops, the EMA holds. If the player resumes, the curve
//     rebuilds from where it left off rather than from scratch.
//     The display shows NAN gaps (curve gaps) + LOW SIGNAL warning so the
//     user knows the visible portions may be stale. The engineer sees the
//     trade-off; the guitarist sees "low signal."
//
//   ALTERNATIVE ("strict live measurement"):
//     Reset EMA to 0.0 for unenergised bins. Curve disappears when signal
//     drops; rebuilds from 0 dB each time signal returns. More honest about
//     what is actually measured right now, but the curve is unstable on
//     single-note lines where only a few bins are ever energised.
//
// This choice should be revisited after real hardware testing with actual
// guitar material. The sticky instrument feel is the current working hypothesis.
// To switch: in audio_engine.cpp audioEngine_update(), change the gated-bin
// block to also reset s_tf_smoothed[k] = 0.0f.
// See: audio_engine.cpp, label "TF PERSISTENCE BEHAVIOUR".


// Confidence: minimum fraction of bins above TF_SOURCE_GATE for the TF
// display to be considered reliable. Below this, "LOW SIGNAL" is shown.
// 0.10 = at least 51 of 512 bins must have source energy.
#define TF_CONFIDENCE_THRESHOLD      0.10f


// Peak meter decay: dBFS drop per display update cycle.
// At ~93 ms/cycle: 1.5 dB/cycle ≈ 16 dB/sec ≈ hardware VU ballistics.
#define PEAK_DECAY_DB_PER_UPDATE      1.5f
// =============================================================================
// DISPLAY — PHYSICAL DIMENSIONS
// =============================================================================
#define DISPLAY_WIDTH         800
#define DISPLAY_HEIGHT        480


// =============================================================================
// DISPLAY — THREE-BAND SCREEN LAYOUT
// =============================================================================
//
//   Y=0    ┌─────────────────────────────────── 800 px ──────┐
//          │   LEVEL METERS                                         │ Band 0 (60 px)
//   Y=60   ├──────────────────────────────────────────────────┤
//          │   SPECTRUM     (source + return overlay)               │ Band 1 (200 px)
//   Y=260 ├──────────────────────────────────────────────────┤
//          │   RIG CHANGE     [dB]                                  │ Band 2 (220 px)
//   Y=480 └──────────────────────────────────────────────────┘
// -----------------------------------------------------------------------------
#define METER_PANEL_Y          0
#define METER_PANEL_H         60


#define SPECTRUM_PANEL_Y           (METER_PANEL_Y + METER_PANEL_H)
#define SPECTRUM_PANEL_H           200


#define TF_PANEL_Y     (SPECTRUM_PANEL_Y + SPECTRUM_PANEL_H)
#define TF_PANEL_H     (DISPLAY_HEIGHT - TF_PANEL_Y)


// Graph inner margins (same for both panels)
#define GRAPH_MARGIN_LEFT                50
#define GRAPH_MARGIN_RIGHT               10
#define GRAPH_MARGIN_TOP                 14
#define GRAPH_MARGIN_BOTTOM              20


#define GRAPH_W     (DISPLAY_WIDTH - GRAPH_MARGIN_LEFT - GRAPH_MARGIN_RIGHT)


#define SPEC_GRAPH_Y       (SPECTRUM_PANEL_Y + GRAPH_MARGIN_TOP)
#define SPEC_GRAPH_H       (SPECTRUM_PANEL_H - GRAPH_MARGIN_TOP - GRAPH_MARGIN_BOTTOM)


#define TF_GRAPH_Y     (TF_PANEL_Y + GRAPH_MARGIN_TOP)
#define TF_GRAPH_H     (TF_PANEL_H - GRAPH_MARGIN_TOP - GRAPH_MARGIN_BOTTOM)


// =============================================================================
// DISPLAY — COLOUR PALETTE              (RA8875 16-bit RGB 5-6-5)
// =============================================================================
#define RGB565(r, g, b) \
     ( ((uint16_t)((r) & 0x1F) << 11) | \
       ((uint16_t)((g) & 0x3F) <<             5) | \
      ((uint16_t)((b) & 0x1F)              ) )


#define COL_BLACK          RGB565( 0,          0,        0)
#define COL_WHITE          RGB565(31, 63, 31)
#define COL_DARK_GREY      RGB565( 4,          8,        4)
#define COL_MID_GREY       RGB565(12, 24, 12)
#define COL_LIGHT_GREY     RGB565(20, 40, 20)


#define COL_SOURCE       RGB565( 6, 20, 28)                   // Steel blue   — SOURCE_NODE signal
#define COL_RETURN       RGB565( 4, 40,             8)        // Grass green — RETURN_NODE signal
#define COL_TRANSFER     RGB565(28, 44,             0)        // Amber/gold   — rig change curve
#define COL_CLIP         RGB565(28,       0,        0)        // Red          — overload warning
#define COL_WARNING      RGB565(28, 32,             0)        // Yellow-orange — low confidence


#define COL_SEPARATOR     RGB565( 8, 16,             8)
#define COL_GRID          RGB565( 4, 10,             4)
#define COL_LABEL         RGB565(18, 36, 18)


// Result view — quality badge colours
#define COL_QUALITY_EXCELLENT          RGB565( 4, 50,              8)   // Bright green
#define COL_QUALITY_GOOD               RGB565( 4, 40,              8)   // Same as COL_RETURN (green)
#define COL_QUALITY_MARGINAL           RGB565(28, 32,              0)   // Same as COL_WARNING (yellow-orange)
#define COL_QUALITY_POOR               RGB565(28,             0,   0)   // Same as COL_CLIP (red)


// Insight panel — text colours by mode and severity
#define COL_INSIGHT_MEAS               RGB565(28, 44,              0)   // Amber — measurement facts
#define COL_INSIGHT_ADV                RGB565(20, 36, 18)               // Muted teal — advisory inferences
#define COL_INSIGHT_ALERT              RGB565(28,             0,   0)   // Red — action required
#define COL_INSIGHT_DETAIL             RGB565(20, 40, 20)               // Light grey — detail text


// =============================================================================
// DISPLAY — GRAPH AXIS RANGES
// =============================================================================
#define SPEC_FREQ_MIN          20.0f
#define SPEC_FREQ_MAX 20000.0f
#define SPEC_DB_MIN       -90.0f
#define SPEC_DB_MAX            0.0f


// RIG CHANGE panel: symmetric ±18 dB.
// 0 dB centre line = "rig passes this frequency without change."
#define TF_DB_MIN     -18.0f
#define TF_DB_MAX     +18.0f


// =============================================================================
// DISPLAY — LEVEL METER GEOMETRY
// =============================================================================
#define METER_SOURCE_X         60
#define METER_RETURN_X     450
#define METER_BAR_W        320
#define METER_BAR_H         16
#define METER_BAR_Y         22


#define METER_DB_MIN     -60.0f
#define METER_DB_MAX       0.0f


// =============================================================================
// SIGNAL INTEGRITY — CLIPPING THRESHOLD
// =============================================================================
// Level at or above which a signal is considered to be clipping.
// Applied in audio_capture.cpp for clipping flags and clip event latches.
// –0.5 dBFS warns half a dB before hard digital clipping.
// Adjust downward (e.g. –1.0) for an earlier warning.
#define CLIP_THRESHOLD_DBFS       -0.5f


#endif // CONFIG_H
