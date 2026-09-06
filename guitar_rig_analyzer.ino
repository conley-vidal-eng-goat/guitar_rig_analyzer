// =============================================================================
// guitar_rig_analyzer.ino     —     Guitar Rig Analyzer     v0.5.0
// =============================================================================
//
// TARGET HARDWARE
//   • Teensy 4.1    (600 MHz ARM Cortex-M7, 1 MB DTCM + 1 MB OCRAM)
//   • Teensy Audio Shield     (SGTL5000 via I2S audio + I2C control — not SPI)
//   • Adafruit RA8875 + 800×480 5" IPS touchscreen           (SPI)
//   • OPA1642 ultra-high-impedance input buffer           (analogue, pre-codec)
//
// REQUIRED LIBRARIES
//   • Adafruit RA8875             v1.4.x or later   (Library Manager)
//   • Adafruit BusIO              (auto-installed with RA8875)
//   • Teensy Audio Library        (bundled with Teensyduino)
//
// ARDUINO IDE SETTINGS
//   Board: Teensy 4.1 | Optimize: Fastest | CPU: 600 MHz | USB: Serial
//
// SIGNAL NODE MODEL
// -----------------
// This firmware thinks in terms of two logical signal measurement nodes:
//
//   SOURCE_NODE — signal leaving the instrument, sent to the rig (Rig Send).
//                   Tapped after the OPA1642 buffer (≥1 MΩ, transparent to pickup).
//
//   RETURN_NODE — signal returning from the rig (Rig Return).
//
// Transfer function H(f) = RETURN_NODE / SOURCE_NODE per frequency bin.
// "What did the rig do to the signal?" — answered bin by bin in dB.
//
// CURRENT BENCH BINDING
// ---------------------
//   SOURCE_NODE → SGTL5000 Line In LEFT        (I2S channel 0)
//   RETURN_NODE → SGTL5000 Line In RIGHT (I2S channel 1)
//
// This binding is set in config.h (SOURCE_NODE_PHYSICAL_CH /
// RETURN_NODE_PHYSICAL_CH)
// and managed by audio_capture.cpp via the SignalRoute mechanism.
//
// ACTIVE MODULES (v0.5.0)
// -----------------------
//   audio_capture           — single I2S acquisition owner, dual consumer model,
//                             AudioRecordQueue for raw sample capture
//   audio_engine            — live display consumer (EMA TF, spectrum, peaks)
//   measurement_engine      — precision state machine + complex FFT accumulation
//                             + calibration application + export trigger
//   signal_generator        — block-aligned DDS stimulus generator
//   calibration_store       — binary calibration file load/save/validate on SD
//   export_engine           — JSON fingerprint + CSV export to SD
//   insights_engine         — measurement/advisory interpretation layer
//   validation              — known-signal validation harness
//   display_engine          — RA8875 live display + result view + insight panel
//
// STILL TO ADD (future milestones)
// ---------------------------------
//   signal_router           — hardware jack detection + relay control
//   display_engine          — touch UI (result view and insight panel now
//                             implemented)
//   insights refinement     — threshold tuning against real hardware data
//
// HEADPHONE MONITORING (temporary bench behaviour)
// -------------------------------------------------
// SOURCE_NODE → left ear, RETURN_NODE → right ear.
// This is a development convenience. Final product will have selectable source.
//
// CHANGELOG v0.5.0
// ----------------
// • audio_capture: single I2S owner, AudioRecordQueue for complex FFT path
// • measurement_engine: full complex FFT via CMSIS-DSP arm_cfft_f32(),
//   real S_xy_im, atan2 phase, group delay, calibration application
// • calibration_store: binary .cal file with CRC-32, hard/soft mismatch rules
// • export_engine: JSON fingerprint + CSV export, incremental write (no heap)
// • insights_engine: MEASUREMENT/ADVISORY separation, quality gate, five
//   detectors
// • guitar_rig_analyzer: sticky abort, live-display gating, s/b/c/i/x commands
// =============================================================================


#include "config.h"
#include "audio_capture.h"     // v0.4: single acquisition layer — include before audio_engine
#include "audio_engine.h"
#include "display_engine.h"
#include "validation.h"      // Known-signal validation harness (v0.3.0)
#include "measurement_engine.h"     // precision measurement state machine
#include "calibration_store.h"      // calibration buffer and file I/O
#include "export_engine.h"           // JSON and CSV export to SD
#include "insights_engine.h"         // v0.5 advisory interpretation layer
#include "signal_generator.h"       // v0.4 block-aligned stimulus generator
#include <stdlib.h>


// =============================================================================
// EXPECTED TIMING CONSTANTS
// =============================================================================
// Computed from config.h for use in Serial diagnostics only.
// The actual measured rates are what matter — these are the targets.


static const float EXPECTED_BLOCK_MS =
    1000.0f * FFT_AVERAGE_COUNT * FFT_SIZE / (float)SAMPLE_RATE;
    // = 1000 × 4 × 1024 / 44100 ≈ 92.9 ms


static const float EXPECTED_DISPLAY_MS =
    EXPECTED_BLOCK_MS * DISPLAY_UPDATE_EVERY_N_FRAMES;


// =============================================================================
// PROGRAM STATE
// =============================================================================


// Current analysis frame — global to avoid ~4 KB stack allocation per loop.
// Written by audioEngine_update(), read by displayEngine_update() and the
// Serial diagnostics in this file.
static AudioFrame s_frame;


// Performance counters
static uint32_t s_total_blocks          = 0;
static uint32_t s_total_displays        = 0;
static uint32_t s_loop_iterations       = 0;
static uint32_t s_last_diag_ms          = 0;
static uint32_t s_diag_blocks_prev      = 0;
static uint32_t s_diag_displays_prev = 0;


// Previous status state — write status message only on state change
static bool s_was_clipping          = false;


// Keep the audio pipeline moving while waiting for a numeric Serial response.
// Used only in bench/validation prompts, not the normal live path.
static float readSerialFloatWithAudioPump(float default_value) {
    char buf[24];
    uint8_t len = 0;
    AudioFrame discard;

    while (!Serial.available()) {
        audioCap_update();
        if (audioCap_isBlockFresh(AudioConsumer::LIVE)) {
            audioEngine_update(&discard);
        }
        delay(5);
    }

    bool done = false;
    while (!done) {
        if (Serial.available()) {
            char c = (char)Serial.read();
            if (c == '\r') continue;
            if (c == '\n') {
                done = true;
            } else if (len < sizeof(buf) - 1) {
                buf[len++] = c;
            }
        } else {
            audioCap_update();
            if (audioCap_isBlockFresh(AudioConsumer::LIVE)) {
                audioEngine_update(&discard);
            }
            delay(5);
        }
    }
    buf[len] = '\0';
    return (len > 0) ? atof(buf) : default_value;
}


// =============================================================================
// SETUP
// =============================================================================


void setup() {


    Serial.begin(115200);
    delay(500);


    Serial.println("================================================");
    Serial.println("     Guitar Rig Analyzer   v" FIRMWARE_VERSION);
    Serial.println("================================================");
    Serial.printf ("[Main] Expected block period:       %.1f ms\n",
EXPECTED_BLOCK_MS);
    Serial.printf ("[Main] Expected display period: %.1f ms (~%.1f fps)\n",
                      EXPECTED_DISPLAY_MS, 1000.0f / EXPECTED_DISPLAY_MS);
    Serial.printf ("[Main] SOURCE_NODE bench channel: %d     |   RETURN_NODE bench" " " "channel: %d\n",
                      SOURCE_NODE_PHYSICAL_CH, RETURN_NODE_PHYSICAL_CH);


    // --- Display first ---
    // Gives visual feedback during audio init and allows error messages
    // if codec init fails.
    Serial.println("[Main] Initialising display...");
    if (!displayEngine_init()) {
           Serial.println("[Main] WARNING: Display init failed. Continuing without display.");
    }
    displayEngine_drawStatusMessage("Initialising audio...");


    // --- Audio capture layer (v0.4: must init before audio_engine) ---
    // audioCap_init() owns codec init, AudioMemory, I2S, and FFT objects.
    // audio_engine depends on audio_capture being initialised first.
    Serial.println("[Main] Initialising audio capture layer...");
    if (!audioCap_init()) {
           displayEngine_drawStatusMessage("ERROR: Codec not found — check shield");
           Serial.println("[Main] FATAL: audioCap_init() failed. Halting.");
           while (true) { delay(500); }
    }


    // --- Audio engine (live analysis consumer) ---
    Serial.println("[Main] Initialising audio engine...");
    if (!audioEngine_init()) {
           displayEngine_drawStatusMessage("ERROR: Audio engine init failed");
           Serial.println("[Main] FATAL: audioEngine_init() failed. Halting.");
           while (true) { delay(500); }
    }


    // Confirm the active route in the display
    const SignalRoute& route = audioEngine_getRoute();
    Serial.printf("[Main] Active route: %s\n", route.description);
    // Initialise validation harness.
    // Tests are NOT run automatically — they require explicit user invocation.
    // See Serial command handler in loop() for how to trigger them.
    // Tests block the main loop while running (by design — they need controlled
    // timing).
    validation_init();


    // --- Calibration store (v0.5: load default cal from SD if present) ---
    calStore_init();
    exportEngine_init();     // check SD and create exports/ directory


    // --- Measurement engine and signal generator ---
    signalGen_init();
    measurementEngine_init();      // arms self-test; runs during first update() calls


    displayEngine_drawStatusMessage("Ready — play to begin");
    Serial.println("[Main] Serial commands:");
    Serial.println("[Main]      v = run all validation tests");
    Serial.println("[Main]      1-4 = run individual validation test");
    Serial.println("[Main]      m = arm rig analysis measurement");
    Serial.println("[Main]          (external stimulus required — generator DUT" " " "injection pending signal_router)");
    Serial.println("[Main]      s = save current RESULT as JSON fingerprint");
    Serial.println("[Main]      b = save current RESULT as baseline CSV");
    Serial.println("[Main]      i = re-print insights from last result");
    Serial.println("[Main]      c = save current RESULT as system calibration");
    Serial.println("[Main]      x = cancel active measurement");
    Serial.println("[Main]      r = reset EMA smoothing");


    s_last_diag_ms = millis();
    Serial.println("[Main] Setup complete. Entering main loop.");
    Serial.println("--------------------------------------------------");
}


// =============================================================================
// LOOP
// =============================================================================


void loop() {


    s_loop_iterations++;


    // -------------------------------------------------------------------------
    // Serial command handler
    // Allows triggering validation tests and other actions from the Serial
    // monitor without recompiling. Characters are checked non-blockingly;
    // only validation test invocations block the loop (intentionally).
    //
    // Commands:
    //    'v' — run all four validation tests in sequence
    //    '1' — run Test 1: Flat Loopback only
    //    '2' — run Test 2: Channel Swap Symmetry only
    //    '3' — run Test 3: Known Gain Offset (prompts for expected value)
    //    '4' — run Test 4: Known Filter (prompts for corner frequency)
    //      'r' — reset EMA smoothing and accumulators
    // -------------------------------------------------------------------------
    if (Serial.available()) {
         char cmd = Serial.read();
         while (Serial.available()) Serial.read();        // Flush remainder of line


         switch (cmd) {
               case 'v': case 'V':
                   validation_runAll();
                   break;
               case '1':
                   validation_waitForUser("Test 1: Connect Y-split loopback, then" " " "press Enter.");
                   validation_runFlatLoopback();
                   break;
               case '2':
                   validation_waitForUser("Test 2: Keep Y-split loopback, press" " " "Enter.");
                   validation_runChannelSwapSymmetry();
                   break;
               case '3': {
                   validation_waitForUser("Test 3: Insert resistive pad in" " " "RETURN_NODE path.\n"
                                          "Enter expected attenuation (e.g. -6.0)" " " "then press Enter.");
                   Serial.print("Expected offset dB: ");
                   float off = readSerialFloatWithAudioPump(-6.0f);
                   validation_runKnownGainOffset(off);
                   break;
               }
               case '4': {
                   validation_waitForUser("Test 4: Insert RC low-pass filter in" " " "RETURN_NODE path.\n"
                                          "Enter corner frequency Hz then press" " " "Enter.");
                   Serial.print("Corner Hz: ");
                   float fc = readSerialFloatWithAudioPump(1989.0f);
                   validation_runKnownFilter(fc, -6.0f);
                   break;
               }
               case 'r': case 'R':
                   audioEngine_resetSmoothing();
                   displayEngine_drawStatusMessage("Smoothing reset.");
                   Serial.println("[Main] EMA and accumulators reset.");
                   break;
               case 'm': case 'M': {
                   // Rig analysis measurement (MODE_PRECISION, 32 averages).
                   // NOTE: requires external stimulus (guitar or signal generator on
                   // SOURCE_NODE).
                   // The internal generator does not yet reach the RIG SEND jack.
                   MeasurementParams mp = measureParams_rigAnalysis();
                   if (measurementEngine_arm(mp)) {
                       displayEngine_drawStatusMessage("Measuring — external" " " "stimulus");
                       Serial.println("[Main] Rig analysis measurement armed.");
                   } else {
                       Serial.println("[Main] Could not arm measurement.");
                   }
                   break;
               }
               case 'i': case 'I':
                   insightsEngine_printToSerial();
                   break;
               case 'x': case 'X':
                   // Cancel an active measurement, OR acknowledge a sticky abort.
                   if (measurementEngine_getState() == MeasurementState::ABORTED) {
                       measurementEngine_acknowledgeAbort();
                       displayEngine_restoreLive();
                       Serial.println("[Main] Abort acknowledged. Returned to live" " " "view.");
                   } else if (measurementEngine_getState() ==
MeasurementState::RESULT) {
                       // Return from result view to live view without a new
                       // measurement.
                       // returnToLive() transitions RESULT → IDLE so the live
                       // display gate (IDLE or ARMED only) unblocks on the
                       // next loop iteration.
                       measurementEngine_returnToLive();
                       displayEngine_restoreLive();
                       Serial.println("[Main] Returned to live view.");
                   } else {
                       measurementEngine_cancel();
                       Serial.println("[Main] Measurement cancelled.");
                   }
                   break;
               case 's': case 'S':
                   // Save the current MeasurementResult as a JSON fingerprint.
                   if (measurementEngine_getState() == MeasurementState::RESULT) {
                       measurementEngine_exportToSD(nullptr);   // auto-generate filename
                   } else {
                       Serial.println("[Main] 's' ignored: no RESULT state" " " "measurement.");
                  }
                  break;
            case 'b': case 'B':
                  // Save the current result as a baseline TF CSV.
                  if (measurementEngine_getState() == MeasurementState::RESULT) {
                       if (exportEngine_saveBaselineCSV(measurementEngine_getResult(), nullptr)) {
                             displayEngine_drawStatusMessage("Baseline CSV saved.");
                       } else {
                             displayEngine_drawStatusMessage("CSV save FAILED — check" " " "SD");
                       }
                  } else {
                       Serial.println("[Main] 'b' ignored: no RESULT state" " " "measurement.");
                  }
                  break;
            case 'c': case 'C':
                  // Save the current MeasurementResult as the system calibration.
                  // Requires a flat loopback measurement to be completed first
                  // (measurement state must be RESULT).
                  if (measurementEngine_getState() == MeasurementState::RESULT) {
                       if (calStore_saveFromResult(measurementEngine_getResult(),
                                                    CAL_FILE_DEFAULT,
                                                    "bench loopback")) {
                             displayEngine_drawStatusMessage("Calibration saved.");
                             Serial.println("[Main] Calibration saved to SD.");
                       } else {
                             displayEngine_drawStatusMessage("Cal save FAILED — check" " " "SD");
                             Serial.println("[Main] ERROR: calibration save failed.");
                       }
                  } else {
                       Serial.println("[Main] 'c' ignored: need a RESULT state" " " "measurement first.");
                       Serial.println("[Main] Run a flat loopback measurement, then" " " "press 'c'.");
                  }
                  break;
            default:
                  Serial.printf("[Main] Unknown command: '%c'.\n", cmd);
                  Serial.println("[Main] Commands: v=validate     1-4=individual" " " "test");
                  Serial.println("[Main]              m=measure   s=save JSON" " " "b=baseline CSV");
                  Serial.println("[Main]              c=calibrate i=insights" " " "x=cancel/ack");
                  Serial.println("[Main]              r=reset EMA");
                  break;
        }
    }


    // Poll audio engine. Returns true once per averaged output block (~92.9 ms).
    // Returns false the vast majority of the time — caller spins freely.
    // v0.4 acquisition model:
    // Per-iteration order:
    // 1. audioCap_update() drives the capture pipeline and returns an event.
    // 2. The main loop handles events (clip, route change) before consumers run.
    // 3. audioEngine_update() consumes CONSUMER_LIVE and updates the live frame.
    AudioCaptureEvent cap_event = audioCap_update();


    // Handle capture-layer events before running consumers.
    if (cap_event == AudioCaptureEvent::CLIP_SOURCE) {
        Serial.println("[Main] audioCap: CLIP_SOURCE detected");
    } else if (cap_event == AudioCaptureEvent::CLIP_RETURN) {
        Serial.println("[Main] audioCap: CLIP_RETURN detected");
    } else if (cap_event == AudioCaptureEvent::ROUTE_CHANGED) {
        Serial.println("[Main] audioCap: ROUTE_CHANGED");
        // Abort any in-progress measurement with ROUTE_CHANGED reason.
        // notifyRouteChanged() (not cancel()) preserves the correct abort cause
        // so diagnostics and the user display show topology invalidation,
        // not a spurious user cancel.
        measurementEngine_notifyRouteChanged();
    }


    // --- Precision measurement engine update (v0.4) ---
    // Drives state machine; returns event if state changed.
    MeasurementEvent meas_ev = measurementEngine_update();
    if (meas_ev == MeasurementEvent::RESULT_READY) {
        Serial.println("[Main] Measurement result ready.");
        const MeasurementResult& r = measurementEngine_getResult();
        Serial.printf("[Main] Quality: %s, coherence: %.2f, valid bins: %.0f%%\n",
                           (r.result_quality == ResultQuality::EXCELLENT) ? "EXCELLENT"
:
                           (r.result_quality == ResultQuality::GOOD)       ? "GOOD" :
                           (r.result_quality == ResultQuality::MARGINAL)   ? "MARGINAL"
:
                           (r.result_quality == ResultQuality::POOR)       ? "POOR" :
"INVALID",
                           r.mean_coherence, r.valid_bin_fraction * 100.0f);
        // Analyse insights then render result screen
        insightsEngine_analyse(r);
           insightsEngine_printToSerial();
           displayEngine_showResult(r, insightsEngine_getInsights());
    } else if (meas_ev == MeasurementEvent::EXPORT_COMPLETE) {
           Serial.println("[Main] Export complete.");
           // Result view stays on screen — update only the provenance line
           displayEngine_drawStatusMessage("Saved — press x to return");
    } else if (meas_ev == MeasurementEvent::EXPORT_FAILED) {
           Serial.println("[Main] Export FAILED.");
           displayEngine_drawStatusMessage("Export FAILED — check SD");
    } else if (meas_ev == MeasurementEvent::ABORTED) {
           // Sticky abort: leave latched until user presses x.
           Serial.printf("[Main] MEASUREMENT ABORTED: %s\n",
                         measurementEngine_getAbortDescription());
           Serial.println("[Main] Press 'x' to acknowledge and return to live" " " "view.");
           displayEngine_showAborted(measurementEngine_getAbortDescription());
    } else if (meas_ev == MeasurementEvent::SELF_TEST_PASSED) {
           Serial.println("[Main] Self-test passed.");
           displayEngine_drawStatusMessage("Pipeline alive — ready");
    } else if (meas_ev == MeasurementEvent::SELF_TEST_FAILED) {
           Serial.println("[Main] WARNING: Self-test FAILED — see Serial.");
           displayEngine_drawStatusMessage("PIPELINE CHECK FAILED — see Serial");
    }


    bool new_block = audioEngine_update(&s_frame);


    if (new_block) {


           s_total_blocks++;


           // FIX [display-gate]: Only run the live display update when the
           // measurement
           // state is IDLE or ARMED. In RESULT, EXPORTING, and ABORTED states, the
           // display is showing a measurement result or status screen that must not
           // be overwritten by live spectrum updates.
           // CAPTURE and PROCESSING are brief — suppressing live updates there is
           // fine.
           // When the full display engine is implemented, it will own this gating
           // internally. For now, the main loop guards it.
           MeasurementState mstate = measurementEngine_getState();
           bool live_display_active = (mstate == MeasurementState::IDLE ||
                                        mstate == MeasurementState::ARMED);


           if (live_display_active &&
               s_total_blocks % DISPLAY_UPDATE_EVERY_N_FRAMES == 0) {
               displayEngine_update(&s_frame);
               s_total_displays++;
          }


          // Clipping status message — write only on state transitions
          bool clipping = s_frame.source_clipping || s_frame.return_clipping;
          if (clipping && !s_was_clipping) {
              if (s_frame.source_clipping && s_frame.return_clipping)
                     displayEngine_drawStatusMessage("!! CLIP: SOURCE + RETURN — reduce" " " "gain");
              else if (s_frame.source_clipping)
                     displayEngine_drawStatusMessage("!! CLIP: SOURCE_NODE — reduce" " " "input gain");
              else
                     displayEngine_drawStatusMessage("!! CLIP: RETURN_NODE — check rig" " " "output level");
          } else if (!clipping && s_was_clipping) {
              displayEngine_drawStatusMessage("Ready");
          }
          s_was_clipping = clipping;
    }


    // -------------------------------------------------------------------------
    // Serial diagnostics — every 5 seconds
    // -------------------------------------------------------------------------
    uint32_t now = millis();
    if (now - s_last_diag_ms >= 5000) {


          uint32_t elapsed          = now - s_last_diag_ms;
          uint32_t blocks_win       = s_total_blocks   - s_diag_blocks_prev;
          uint32_t displays_win     = s_total_displays - s_diag_displays_prev;


          float meas_block_ms      = blocks_win   > 0 ? (float)elapsed / blocks_win      :
0.0f;
          float meas_display_ms = displays_win > 0 ? (float)elapsed / displays_win :
0.0f;


          Serial.printf("\n[Main] --- 5s diagnostics (uptime %lus) ---\n", now /
1000);


          // Timing: compare measured to expected.
          // Large deviation (>5 ms) indicates the audio ISR may be missing frames —
          // check AudioMemory() count, CPU load, or SPI bus contention.
          Serial.printf("[Main] Block:      %u in %lums = %.1f ms/block "
                           "(expected %.1f ms, delta %+.1f ms)\n",
                           blocks_win, elapsed, meas_block_ms,
                           EXPECTED_BLOCK_MS, meas_block_ms - EXPECTED_BLOCK_MS);


          Serial.printf("[Main] Display: %u updates = %.1f ms/update "
                          "(expected %.1f ms)\n",
                          displays_win, meas_display_ms, EXPECTED_DISPLAY_MS);


        Serial.printf("[Main] Loop:         %lu iterations/5s = ~%.0f/sec\n",
                          s_loop_iterations, (float)s_loop_iterations / 5.0f);


        // Levels
        Serial.printf("[Main] SOURCE_NODE peak: %+.1f dBFS          |   "
                          "RETURN_NODE peak: %+.1f dBFS\n",
                          s_frame.peak_source_dbfs, s_frame.peak_return_dbfs);


        // Confidence and TF persistence state.
        // tf_persistence_active = true means at least one bin in the last block
        // was unenergised and is carrying preserved EMA history, not live data.
        // This is expected during normal single-note playing; it becomes a
        // concern if it's true continuously while confidence stays near 0.
        Serial.printf("[Main] TF confidence: %.0f%%          (threshold %.0f%%)   "
                          "persistence: %s\n",
                          s_frame.tf_confidence * 100.0f,
                          TF_CONFIDENCE_THRESHOLD * 100.0f,
                          s_frame.tf_persistence_active ? "ACTIVE (some bins carrying" " " "history)"
                                                         : "none (all bins live)");


        // Spot-check TF at five musically significant frequencies.
        // These map to the tonal regions a guitarist would describe:
        //    Bass body | Low-mid clarity | Presence | Upper bite | Air
        static const float freqs[]       = { 120.0f, 500.0f, 1000.0f, 5000.0f, 10000.0f
};
        static const char* labels[] = { "120Hz", "500Hz", "1kHz",           "5kHz",
"10kHz" };
        Serial.print("[Main] TF spot-check:");
        for (int i = 0; i < 5; i++) {
             int      bin = audioEngine_hzToBin(freqs[i]);
             float tf     = s_frame.tf_db[bin];
             if (isnan(tf))
                    Serial.printf("   %s=---", labels[i]);
             else
                    Serial.printf("   %s=%+.1fdB", labels[i], tf);
        }
        Serial.println();


        // Active route snapshot from frame metadata
        Serial.printf("[Main] Route: %s\n", s_frame.active_route.description);


        // Reset window counters
        s_diag_blocks_prev       = s_total_blocks;
            s_diag_displays_prev = s_total_displays;
            s_loop_iterations    = 0;
            s_last_diag_ms       = now;
       }
}


// =============================================================================
// CALIBRATION / ROUTING EXAMPLES
// (Uncomment and call from setup() as needed during bench testing)
// =============================================================================


/*
// Swap SOURCE_NODE and RETURN_NODE physical bindings.
// Useful for symmetry check: feed identical signals to both jacks and verify
// both channels read the same level. Any difference reveals channel imbalance.
void calibrationSwapNodes() {
       SignalRoute swapped = {
            RETURN_NODE_PHYSICAL_CH,          // Physical ch now carrying SOURCE_NODE
role
            SOURCE_NODE_PHYSICAL_CH,          // Physical ch now carrying RETURN_NODE
role
            "CALIBRATION: SOURCE/RETURN nodes swapped"
       };
       audioEngine_setRoute(swapped);
       displayEngine_drawStatusMessage("CAL: nodes swapped");
}


// Restore the default bench route
void calibrationRestoreDefault() {
       SignalRoute normal = {
            SOURCE_NODE_PHYSICAL_CH,
            RETURN_NODE_PHYSICAL_CH,
            "Default bench: SOURCE_NODE=L, RETURN_NODE=R"
       };
       audioEngine_setRoute(normal);
       displayEngine_drawStatusMessage("Ready");
}
*/


// =============================================================================
// DEVELOPMENT ROADMAP — STATUS AS OF v0.5.0
// =============================================================================
//
// COMPLETED
// ---------
// v0.4 — Signal generator
//             AudioSynthWaveformSine + AudioSynthNoise in the audio graph.
//         Block-aligned DDS stimulus generator with sweep support.
//         Generator output is audible on the monitoring path but does NOT
//         yet reach the physical RIG SEND jack (pending signal_router).
//
// v0.5 — Measurement engine + calibration + export + insights + result display
//         Precision measurement state machine with complex FFT accumulation.
//         Binary .cal calibration with CRC-32. JSON fingerprint + CSV export.
//         MEASUREMENT/ADVISORY insight separation. Result view + insight panel.
//
// NEXT MILESTONES
// ---------------
// v0.6 — Signal router / DUT injection
//         Hardware jack detection + relay control.
//         Internal generator stimulus reaches RIG SEND jack.
//         Runtime node binding without recompile.
//
// v0.7 — Precision FFT rebinning
//         OCRAM large-FFT accumulator for MODE_PRECISION (4096pt) and
//         MODE_LF (8192pt). Rebin to 512-bin canonical grid.
//
// v0.8 — Touch UI
//         RA8875 touch interrupt. Tap-to-read Hz/dB on graphs.
//         On-screen gain, monitor source, and route selection.
//
// v0.9 — Result UX refinement
//         Comparison overlay (current vs baseline).
//         Enhanced insight thresholds tuned against real hardware data.
//
// v1.0 — Self-calibration and loopback test
//         Loopback cable connects Rig Send to Rig Return directly.
//         Signal generator sweeps the full frequency range.
//         Deviation from flat 0 dB stored as correction offset.
// =============================================================================
