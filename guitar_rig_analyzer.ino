// =============================================================================
// guitar_rig_analyzer.ino     —     Guitar Rig Analyzer
// (no module-local version — FIRMWARE_VERSION in config.h is authoritative)
// =============================================================================
//
// TARGET HARDWARE
//   • Teensy 4.1    (600 MHz ARM Cortex-M7, 1 MB DTCM + 1 MB OCRAM)
//   • Teensy Audio Shield     (SGTL5000 via I2S audio + I2C control — not SPI)
//   • OPA1642 ultra-high-impedance input buffer           (analogue, pre-codec)
//   • DISPLAY: selected by DISPLAY_TARGET in config.h —
//       DISPLAY_TARGET_PI      Raspberry Pi 5 + 7" Touch Display 2, binary UART
//                              on Serial1 (pins 0/1).  *** PRODUCTION ***
//       DISPLAY_TARGET_RA8875 Adafruit RA8875 + 800×480 5" IPS, SPI. Debug only.
//       DISPLAY_TARGET_NONE    No display hardware. Bench DSP work.
//     See docs/adr/ADR-001-display-architecture.md.
//
// REQUIRED LIBRARIES
//   • Teensy Audio Library        (bundled with Teensyduino)
//   • Adafruit RA8875             v1.4.x or later   (Library Manager)
//   • Adafruit BusIO              (auto-installed with RA8875)
//     — the two Adafruit libraries are needed ONLY for DISPLAY_TARGET_RA8875.
//       The PI and NONE builds do not include display_engine.h at all.
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
// ACTIVE MODULES
// --------------
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
//   presentation            — THE PRESENTATION BOUNDARY. The only display-facing
//                             API this file may call. Dispatches at compile time
//                             to data_sender (Pi), display_engine (RA8875), or a
//                             null backend, per DISPLAY_TARGET in config.h.
//   data_sender             — binary UART protocol to the Pi 5 renderer
//                             (DISPLAY_TARGET_PI backend)
//   display_engine          — RA8875 live display + result view + insight panel
//                             (DISPLAY_TARGET_RA8875 backend, debug only)
//
// THE GOVERNING INVARIANT   (docs/adr/ADR-001-display-architecture.md)
// -------------------------
//   *** The Teensy determines truth. The renderer presents truth. ***
// Nothing in this file asks which renderer exists, and no renderer returns a
// measurement value, validity verdict or quality grade back into this path.
//
// STILL TO ADD (future milestones)
// ---------------------------------
//   signal_router           — hardware jack detection + relay control
//   Pi-side receiver/UI     — parser, state model, plots, touch navigation,
//                             fingerprint visualization          (TODO-36)
//   wire-format freeze      — packet protocol audit against the canonical
//                             512-bin result model               (TODO-34)
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
#include "presentation.h"
#include "timing_probe.h"   // T1 acceptance harness (Phase 10)
#include "validation.h"      // Known-signal validation harness (v0.3.0)
#include "measurement_engine.h"     // precision measurement state machine
#include "calibration_store.h"      // calibration buffer and file I/O
#include "export_engine.h"           // JSON and CSV export to SD
#include "insights_engine.h"         // v0.5 advisory interpretation layer
#include "signal_generator.h"       // v0.4 block-aligned stimulus generator
#include "signal_router.h"          // Phase 5: jack detect only — NO injection
#include <stdlib.h>


// =============================================================================
// EXPECTED TIMING CONSTANTS
// =============================================================================
// Computed from config.h for use in Serial diagnostics only.
// The actual measured rates are what matter — these are the targets.


// CHANGED [todo-27]: was FFT_SIZE, giving 92.9 ms — wrong by exactly 2×.
// AudioAnalyzeFFT1024 runs 50 % overlap, so a result arrives every HOP
// (512 samples), not every window (1024). See FFT_HOP_SAMPLES in config.h.
// Diagnostic-only: no measured value depends on this constant. But left
// uncorrected, every diagnostic line forever reported a phantom -46.6 ms
// anomaly against healthy hardware — exactly the kind of false signal that
// has already cost this project days of debugging.
static const float EXPECTED_BLOCK_MS =
    1000.0f * FFT_AVERAGE_COUNT * FFT_HOP_SAMPLES / (float)SAMPLE_RATE;
    // = 1000 × 4 × 512 / 44100 ≈ 46.4 ms   (measured on hardware: 46.3 ms)


static const float EXPECTED_DISPLAY_MS =
    EXPECTED_BLOCK_MS * DISPLAY_UPDATE_EVERY_N_FRAMES;


// =============================================================================
// PROGRAM STATE
// =============================================================================


// Current analysis frame — global to avoid ~4 KB stack allocation per loop.
// Written by audioEngine_update(), read by presentation_updateLive() and the
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
// BUILD IDENTITY — single formatter, two callers.
//
// Deliberately ONE format string. The startup banner and the periodic
// diagnostics must never drift apart: two hand-written copies of an identity
// line is how a log ends up asserting two different things about the same
// binary.
//
// `prefix` is the only difference between the call sites — banner indentation
// vs the "[Main] " tag the 5 s block uses.
// =============================================================================
static void printBuildIdentity(const char* prefix) {
    Serial.printf("%sBuild: %s %s   v%s\n",
                  prefix, __DATE__, __TIME__, FIRMWARE_VERSION);
}


// =============================================================================
// SETUP
// =============================================================================


void setup() {


    Serial.begin(115200);

    // =====================================================================
    // Bounded wait for a USB host to attach before anything is printed.
    //
    // WHY: on this board Serial is USB CDC. Teensy DISCARDS everything written
    // before a host asserts DTR — and enumeration takes ~1–2 s, which is longer
    // than it takes setup() to reach the banner. Without this wait the startup
    // identity is emitted into a void on every cold boot, and no amount of
    // care on the host side can recover it (established 2026-09-21: four
    // different capture strategies all lost the first ~1.5 KB).
    //
    // The deadline is measured FROM THE MOMENT WE START WAITING, not from MCU
    // boot — otherwise time already spent in earlier init silently shortens
    // the window, and the wait gets less useful the more the firmware grows.
    //
    // Bounded, so an unattended board (no host, bench-only operation) still
    // boots normally after 3 s rather than hanging forever.
    // =====================================================================
    const uint32_t serialWaitStart = millis();
    while (!Serial && (millis() - serialWaitStart) < 3000) {
        yield();
    }

    delay(500);


    // =====================================================================
    // PERMANENT BUILD IDENTITY — do NOT remove.
    //
    // This is infrastructure for trustworthy bench evidence, not a diagnostic.
    // Every measurement recorded in ai/journal.md must be attributable to a
    // specific source revision, and identity must be a POSITIVE statement the
    // firmware makes about itself — never inferred from something being absent.
    //
    // Earned on 2026-09-19: three uploads appeared to succeed while the board
    // kept running an older binary, and the only clue was a help menu one line
    // short. A bench result was nearly attributed to the wrong firmware.
    //
    // Printed here — immediately after Serial.begin(), before presentation_init()
    // and before any audio bring-up — so it cannot be lost behind a renderer
    // failure or a slow display init. (Phase 2 lesson, journal 2026-09-01: a
    // block placed after display init was never reached on this bench.)
    //
    // FIRMWARE_VERSION identifies the intended release; __DATE__/__TIME__
    // identify the actual compile, which is what distinguishes two builds of
    // the same version. Both are needed: the version alone cannot tell you
    // whether the binary in front of you is the one you just built.
    //
    // NOTE: the stamp identifies the COMPILE, not the commit. It does not make
    // a build bit-reproducible — recompiling the same source yields a new
    // stamp. To tie a run to a revision, record this line together with the
    // git hash in the journal.
    // =====================================================================
    Serial.println("================================================");
    Serial.println("     Guitar Rig Analyzer   v" FIRMWARE_VERSION);
    printBuildIdentity("     ");
    Serial.println("================================================");
    // Record the renderer in the banner, not just at init: every serial log
    // pasted into ai/journal.md should state which display architecture the
    // firmware was built against, so a bench observation can never be
    // misattributed to the wrong backend later.
    Serial.printf ("[Main] Display target:               %s\n",
                      presentation_backendName());
    Serial.printf ("[Main] Expected block period:       %.1f ms\n",
EXPECTED_BLOCK_MS);
    Serial.printf ("[Main] Expected display period: %.1f ms (~%.1f fps)\n",
                      EXPECTED_DISPLAY_MS, 1000.0f / EXPECTED_DISPLAY_MS);
    Serial.printf ("[Main] SOURCE_NODE bench channel: %d     |   RETURN_NODE bench" " " "channel: %d\n",
                      SOURCE_NODE_PHYSICAL_CH, RETURN_NODE_PHYSICAL_CH);


    // --- Presentation boundary first ---
    // Brought up before audio so the operator gets feedback during audio init
    // and so codec failures can be reported somewhere visible.
    //
    // NON-FATAL BY CONTRACT (ADR-001): a renderer failure must never prevent
    // acquisition or DSP from starting. With the RA8875 absent, the Adafruit
    // library's waitPoll() spin once stretched the audio block period from
    // 46 ms to 2194 ms — a display defect that destroyed acquisition
    // (journal 2026-09-05 (10), TODO-25). Warn and continue; every
    // presentation_* call stays safe after a failed init.
    Serial.printf("[Main] Initialising presentation backend: %s\n",
                      presentation_backendName());
    if (!presentation_init()) {
           Serial.printf("[Main] WARNING: %s init failed. Continuing without a"
                             " renderer — acquisition and DSP are unaffected.\n",
                             presentation_backendName());
    }
    presentation_status("Initialising audio...");


    // --- Audio capture layer (v0.4: must init before audio_engine) ---
    // audioCap_init() owns codec init, AudioMemory, I2S, and FFT objects.
    // audio_engine depends on audio_capture being initialised first.
    Serial.println("[Main] Initialising audio capture layer...");
    if (!audioCap_init()) {
           presentation_status("ERROR: Codec not found — check shield");
           Serial.println("[Main] FATAL: audioCap_init() failed. Halting.");
           while (true) { delay(500); }
    }


    // --- Audio engine (live analysis consumer) ---
    Serial.println("[Main] Initialising audio engine...");
    if (!audioEngine_init()) {
           presentation_status("ERROR: Audio engine init failed");
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


    // Start a T1 measurement window at boot so a run is always measurable even if
    // the operator forgets to press 't'. Done AFTER all init so boot-time audio
    // spikes do not contaminate the high-water figure.
    timingProbe_reset();

    presentation_status("Ready — play to begin");
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
    Serial.println("[Main]      j = select TS return    k = select XLR return");


    // -------------------------------------------------------------------------
    // Signal router — JACK DETECT ONLY (Phase 5, TODO-5 detect half).
    //
    // This puts signalRouter_init()/update() into the live path for the first
    // time. Scope is deliberately the detect half and nothing else: injection
    // stays off (ENABLE_DUT_INJECTION is 0), s_mixer_send is not added, and
    // measurement_engine still does not consult signalRouter_canInject().
    // Those are Phase 6/7 work, gated by TODO-11 on hardware that is not on the
    // bench. Do not merge them here just because the router is now running.
    //
    // NOTE: signalRouter_init() also configures RELAY_SEND_PIN/RELAY_RETURN_PIN
    // as outputs and drives them LOW. Pin 14 now drives the Phase 6 RELAY_SEND
    // driver (bench-verified 2026-09-16), so LOW here holds that relay
    // de-energised at boot; its contacts are not yet in the signal path
    // (Phase 7). Pin 15 is still unconnected.
    //
    // ADR-004: return source is operator-selected ('j' TS / 'k' XLR) and starts
    // at TS here on every boot. Before this call pin 15 is in reset state, so
    // physical TS-at-power-on depends on the RELAY_RETURN driver's pulldown
    // (Phase 7 hardware, not yet built).
    // -------------------------------------------------------------------------
    Serial.println("[Main] Initialising signal router (jack detect only)...");
    signalRouter_init();


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
    // Jack detect — every iteration, unconditionally.
    //
    // Debounce is time-based (JACK_DEBOUNCE_MS), so this must be polled
    // continuously rather than gated on audio-block availability. It is cheap:
    // four digitalRead() calls and a comparison when nothing changes.
    //
    // The return value is intentionally not consumed yet. Phase 5's sign-off
    // only requires that detect events FIRE and are observable on serial, which
    // signalRouter_update() prints itself. Wiring RouterEvent into
    // measurement_engine invalidation is Phase 7 work -- see TODO-11.
    // -------------------------------------------------------------------------
    (void)signalRouter_update();

    // T1 harness: time the WHOLE loop body. Catches anything that blocks,
    // wherever it lives — not just presentation calls. A transport layer that is
    // individually fast but collectively starves the loop shows up only here.
    const uint32_t loop_t0 = micros();


    // -------------------------------------------------------------------------
    // Presentation transport service — EVERY iteration, unconditionally.
    //
    // Deliberately OUTSIDE the `if (new_block)` guard below. The Pi backend's
    // reliable RESULT path drains across loop iterations, and a result queued
    // just as the signal goes quiet must still finish sending — so transport
    // progress must not depend on audio activity.
    //
    // Non-blocking by contract, and a no-op for the RA8875 and NONE backends.
    // See presentation.h.
    // -------------------------------------------------------------------------
    presentation_service();


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
    //    'u' — print presentation/link transport diagnostics
    //    't' — start a fresh T1 measurement window
    //    'T' — print the T1 acceptance report (Phase 10)
    //    'j' — select TS return   (ADR-004; direct selection, not a toggle)
    //    'k' — select XLR return  (ADR-004). A real change aborts any
    //          in-progress measurement via ROUTE_CHANGED; it is not refused.
    // -------------------------------------------------------------------------
    if (Serial.available()) {
         char cmd = Serial.read();
         while (Serial.available()) Serial.read();        // Flush remainder of line


         switch (cmd) {
               case 'v': case 'V':
                   validation_runAll();
                   break;
               // CHANGED [todo-48]: the single-test commands used to call
               // validation_waitForUser() and then run the test directly,
               // bypassing the preflight level check that only 'v' performed.
               // A dead SOURCE therefore surfaced as a NaN table inside a
               // result report instead of a clear preflight failure. Each
               // path now gates on validation_preflightGate().
               //
               // The gate's argument states whether the test's OWN fixture
               // attenuates RETURN: tests 3 and 4 do so deliberately (pad, RC
               // filter), and gating those on preflight's RETURN level window
               // would fail a correct fixture. See validation.h.
               case '1':
                   if (!validation_waitForUser("Test 1: Connect Y-split loopback, then" " " "press Enter.")) break;
                   if (!validation_preflightGate(false)) break;
                   validation_runFlatLoopback();
                   break;
               case '2':
                   if (!validation_waitForUser("Test 2: Keep Y-split loopback, press" " " "Enter.")) break;
                   if (!validation_preflightGate(false)) break;
                   validation_runChannelSwapSymmetry();
                   break;
               case '3': {
                   if (!validation_waitForUser("Test 3: Insert resistive pad in" " " "RETURN_NODE path.\n"
                                               "Enter expected attenuation (e.g. -6.0)" " " "then press Enter.")) break;
                   if (!validation_preflightGate(true)) break;
                   Serial.print("Expected offset dB: ");
                   float off = readSerialFloatWithAudioPump(-6.0f);
                   validation_runKnownGainOffset(off);
                   break;
               }
               case '4': {
                   if (!validation_waitForUser("Test 4: Insert RC low-pass filter in" " " "RETURN_NODE path.\n"
                                               "Enter corner frequency Hz then press" " " "Enter.")) break;
                   if (!validation_preflightGate(true)) break;
                   Serial.print("Corner Hz: ");
                   float fc = readSerialFloatWithAudioPump(1989.0f);
                   validation_runKnownFilter(fc, -6.0f);
                   break;
               }
               case 'r': case 'R':
                   audioEngine_resetSmoothing();
                   presentation_status("Smoothing reset.");
                   Serial.println("[Main] EMA and accumulators reset.");
                   break;
               case 'm': case 'M': {
                   // Rig analysis measurement (MODE_PRECISION, 32 averages).
                   // NOTE: requires external stimulus (guitar or signal generator on
                   // SOURCE_NODE).
                   // The internal generator does not yet reach the RIG SEND jack.
                   MeasurementParams mp = measureParams_rigAnalysis();
                   if (measurementEngine_arm(mp)) {
                       presentation_status("Measuring — external" " " "stimulus");
                       Serial.println("[Main] Rig analysis measurement armed.");
                   } else {
                       Serial.println("[Main] Could not arm measurement.");
                   }
                   break;
               }
               case 'j': case 'J':
               case 'k': case 'K': {
                   // Direct return selection (ADR-004), not a toggle.
                   const ReturnSource want = (cmd == 'j' || cmd == 'J')
                                                 ? ReturnSource::TS
                                                 : ReturnSource::XLR;
                   if (signalRouter_setReturnSource(want)) {
                       Serial.printf("[Main] Return source selected: %s\n",
                                     want == ReturnSource::TS ? "TS" : "XLR");
                   } else {
                       Serial.println("[Main] Return source selection rejected.");
                   }
                   break;
               }
               case 'T':
                   // T1 acceptance report (Phase 10 steps 11-12). Fixed-format
                   // key=value output so the four required runs can be diffed
                   // mechanically rather than eyeballed.
                   timingProbe_report();
                   break;
               case 't':
                   // Start a fresh T1 measurement window. Press 't' at the start
                   // of each run so the four windows are comparable, then 'T' at
                   // the end. Also resets the audio high-water, which would
                   // otherwise carry a boot-time spike into every run.
                   timingProbe_reset();
                   Serial.println("[T1] Measurement window reset — press 'T' to report.");
                   break;
               case 'u': case 'U':
                   // Transport health. Printed next to the 5 s block-timing
                   // window below so the two can be compared — the question is
                   // never "how many frames dropped" alone, it is "did
                   // transmission perturb acquisition".
                   presentation_printDiagnostics();
                   break;
               case 'i': case 'I':
                   insightsEngine_printToSerial();
                   break;
               case 'x': case 'X':
                   // Cancel an active measurement, OR acknowledge a sticky abort.
                   if (measurementEngine_getState() == MeasurementState::ABORTED) {
                       measurementEngine_acknowledgeAbort();
                       presentation_restoreLive();
                       Serial.println("[Main] Abort acknowledged. Returned to live" " " "view.");
                   } else if (measurementEngine_getState() ==
MeasurementState::RESULT) {
                       // Return from result view to live view without a new
                       // measurement.
                       // returnToLive() transitions RESULT → IDLE so the live
                       // display gate (IDLE or ARMED only) unblocks on the
                       // next loop iteration.
                       measurementEngine_returnToLive();
                       presentation_restoreLive();
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
                             presentation_status("Baseline CSV saved.");
                       } else {
                             presentation_status("CSV save FAILED — check" " " "SD");
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
                             presentation_status("Calibration saved.");
                             Serial.println("[Main] Calibration saved to SD.");
                       } else {
                             presentation_status("Cal save FAILED — check" " " "SD");
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
                  Serial.println("[Main]              j=return TS  k=return XLR");
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
           presentation_showResult(r, insightsEngine_getInsights());
    } else if (meas_ev == MeasurementEvent::EXPORT_COMPLETE) {
           Serial.println("[Main] Export complete.");
           // Result view stays on screen — update only the provenance line
           presentation_status("Saved — press x to return");
    } else if (meas_ev == MeasurementEvent::EXPORT_FAILED) {
           Serial.println("[Main] Export FAILED.");
           presentation_status("Export FAILED — check SD");
    } else if (meas_ev == MeasurementEvent::ABORTED) {
           // Sticky abort: leave latched until user presses x.
           Serial.printf("[Main] MEASUREMENT ABORTED: %s\n",
                         measurementEngine_getAbortDescription());
           Serial.println("[Main] Press 'x' to acknowledge and return to live" " " "view.");
           presentation_showAborted(measurementEngine_getAbortDescription());
    } else if (meas_ev == MeasurementEvent::SELF_TEST_PASSED) {
           Serial.println("[Main] Self-test passed.");
           presentation_status("Pipeline alive — ready");
    } else if (meas_ev == MeasurementEvent::SELF_TEST_FAILED) {
           Serial.println("[Main] WARNING: Self-test FAILED — see Serial.");
           presentation_status("PIPELINE CHECK FAILED — see Serial");
    }


    bool new_block = audioEngine_update(&s_frame);


    if (new_block) {


           s_total_blocks++;

           // T1 harness: record block period and detect skipped analysis blocks.
           // Called as early as possible after the block is recognised so the
           // measured period is the acquisition cadence, not the cadence plus
           // whatever this iteration goes on to do.
           timingProbe_noteBlock(s_frame.output_block_number);


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
               presentation_updateLive(&s_frame);
               s_total_displays++;
          }


          // Clipping status message — write only on state transitions
          bool clipping = s_frame.source_clipping || s_frame.return_clipping;
          if (clipping && !s_was_clipping) {
              if (s_frame.source_clipping && s_frame.return_clipping)
                     presentation_status("!! CLIP: SOURCE + RETURN — reduce" " " "gain");
              else if (s_frame.source_clipping)
                     presentation_status("!! CLIP: SOURCE_NODE — reduce" " " "input gain");
              else
                     presentation_status("!! CLIP: RETURN_NODE — check rig" " " "output level");
          } else if (!clipping && s_was_clipping) {
              presentation_status("Ready");
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


          // CHANGED [todo-53]: repeat the build identity EVERY interval, not
          // only at boot. A banner printed once is unrecoverable if the host
          // attached late, and on USB CDC the host usually does. Emitting it
          // here means any captured diagnostic interval carries its own
          // compile provenance, instead of having to be correlated with a
          // boot event that may never have been captured.
          printBuildIdentity("[Main] ");


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


        // Transport health, printed HERE so it sits directly beneath the block
        // timing above. Audit finding T1 predicts presentation transmission
        // could consume ~73% of an audio block period; the only way to know is
        // to read these two together. A rising drop count with unchanged
        // ms/block is the delivery policy working as designed.
        presentation_printDiagnostics();


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


        // TODO-29: the spot-check below samples only five bins. This says how
        // much of the whole curve is pinned to a clamp rail. A high count with
        // nothing connected to RETURN_NODE is expected, not a fault — it means
        // the true TF is below the representable range.
        Serial.printf("[Main] TF clamped bins: %u of %d\n",
                          (unsigned)s_frame.tf_clamped_count, FFT_BINS);


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
             // TODO-29: a clamped bin is NOT a measurement — its raw TF fell
             // outside [TF_DB_MIN-6, TF_DB_MAX+6] and tf_db carries the rail.
             // Printing it bare made "1kHz=-24.0dB" look like data when the
             // true TF was ~-47 dB. RAIL[] marks the number as the boundary
             // the value was pinned to, not the transfer function.
             if (isnan(tf))
                    Serial.printf("   %s=---", labels[i]);
             else if (audioEngine_tfBinClamped(&s_frame, bin))
                    Serial.printf("   %s=RAIL[%+.1fdB]", labels[i], tf);
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


    // T1 harness: close the loop-body timing. Must be the LAST statement in
    // loop() so the measured duration covers everything above it, including the
    // 5 s diagnostic print on the iterations where that fires.
    timingProbe_noteLoopIteration(micros() - loop_t0);
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
       presentation_status("CAL: nodes swapped");
}


// Restore the default bench route
void calibrationRestoreDefault() {
       SignalRoute normal = {
            SOURCE_NODE_PHYSICAL_CH,
            RETURN_NODE_PHYSICAL_CH,
            "Default bench: SOURCE_NODE=L, RETURN_NODE=R"
       };
       audioEngine_setRoute(normal);
       presentation_status("Ready");
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
