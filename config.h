// =============================================================================
// config.h   —    Guitar Rig Analyzer
// (no module-local version — see FIRMWARE_VERSION below)
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


// =============================================================================
// VERSIONS  —  two independent compatibility concepts. Do not conflate them.
// =============================================================================
// FIRMWARE_VERSION is the ONE authoritative product version for this repository.
// It is stamped into every MeasurementResult, every export, the Serial banner and
// the Pi HELLO packet. No module carries a product version of its own — if you
// find one in a file header comment, it is stale and should reference this.
//
// PI_PROTOCOL_VERSION versions the Teensy<->Pi wire format ONLY
// (data_sender.h). A firmware bump that does not change the wire format must not
// invalidate a working receiver, and a wire-format change must be visible to a
// receiver even if the firmware version is untouched. Hence two numbers.
//
// 0.6.0 — first firmware baseline implementing the Pi 5 production display
//         architecture: presentation boundary, three DISPLAY_TARGETs, backend
//         exclusion, validation harness migrated off the renderer, and Pi link
//         protocol v2 with the four truth-invariant defects closed.
//         See docs/adr/ADR-001-display-architecture.md.
//
// PI_PROTOCOL_VERSION 2 — v1 was the pre-audit layout. It never had a receiver
//         and was never frozen, but the literal string "protocol=1" did exist in
//         committed source, and v2 changes the payload shape of both LIVE_FRAME
//         and RESULT. A version number that ever appeared in the tree is not
//         reused for a different layout: an old log saying "protocol=1" must not
//         be ambiguous about which layout produced it.
//         Changes: see docs/pi_link_protocol_audit.md.
// -----------------------------------------------------------------------------
#define FIRMWARE_VERSION "0.6.0"
#define PI_PROTOCOL_VERSION 2


// =============================================================================
// DISPLAY ARCHITECTURE — RENDERER SELECTION
// =============================================================================
// Authority: docs/adr/ADR-001-display-architecture.md (ACCEPTED 2026-09-11).
//
// The Raspberry Pi 5 + 7" Touch Display 2 is the PRODUCTION renderer. The
// RA8875 is retained as bring-up/debug hardware only.
//
// The application never calls a renderer directly — it calls presentation_*
// (presentation.h), and this constant decides which backend those calls reach
// at compile time. Changing renderers is a one-line change here; no measurement
// or DSP code knows which display exists.
//
//   DISPLAY_TARGET_PI      → presentation_* dispatches to data_sender
//                            (binary UART → Pi 5, Serial1 pins 0/1).
//                            THE PRODUCTION CONFIGURATION.
//
//   DISPLAY_TARGET_RA8875 → presentation_* dispatches to display_engine
//                            (SPI RA8875 800x480). Debug/fallback only.
//                            Panel geometry is written for this panel and is
//                            NOT retargeted to the Pi's 7" display.
//
//   DISPLAY_TARGET_NONE    → presentation_* becomes no-ops. Use this for bench
//                            DSP work with NO display hardware attached: it is
//                            the cheapest configuration and removes the
//                            renderer from the timing budget entirely. This is
//                            the honest setting for most of Phases 5-9.
//
// WHY A TRI-STATE AND NOT A BOOLEAN: the runbook once promised a
// `USE_PI_DISPLAY` flag that was never implemented anywhere in the code
// (see ADR-001 "Context"). A boolean also cannot express "no display", which
// is the configuration the bench actually runs in today. Making hardware
// selection explicit prevents a repeat of that drift.
// -----------------------------------------------------------------------------
#define DISPLAY_TARGET_PI       1
#define DISPLAY_TARGET_RA8875   2
#define DISPLAY_TARGET_NONE     3

#define DISPLAY_TARGET DISPLAY_TARGET_PI

#if DISPLAY_TARGET != DISPLAY_TARGET_PI     && \
    DISPLAY_TARGET != DISPLAY_TARGET_RA8875 && \
    DISPLAY_TARGET != DISPLAY_TARGET_NONE
  #error "DISPLAY_TARGET must be DISPLAY_TARGET_PI, _RA8875, or _NONE. See docs/adr/ADR-001-display-architecture.md"
#endif


// =============================================================================
// HARDWARE — SPI BUS    (RA8875 display + optional SD)
// =============================================================================
// The Teensy Audio Shield uses I2S (audio data) and I2C (codec control).
//
// CORRECTED 2026-09-12: an earlier version of this comment said the shield
// "does NOT use SPI", and that is false for a STACKED Rev D. The Rev D shield
// carries its own microSD socket on the SPI bus (CS = pin 10, plus the shared
// 11/12/13) and an optional flash on pin 6. While the shield was connected by
// selective flying wires, only the pins we chose were live and the claim was
// harmlessly true in practice. Once the shield is stacked, EVERY populated
// header position becomes electrically connected — including pin 10.
//
// That is the assumption the RA8875 pin-10 conflict hides behind, so it is
// stated plainly here and enforced by AUDIO_SHIELD_STACKED below.
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
#define RA8875_RESET_PIN     5   // RA8875 hardware reset (active LOW)

                                 // MOVED 8 -> 5 (2026-09-05): pin 8 is I2S
                                 // RX_DATA0 on Teensy 4.x (Audio library
                                 // input_i2s.cpp, __IMXRT1062__ branch) and
                                 // carries Audio Shield line-in INTO the
                                 // Teensy. Display reset and I2S RX cannot
                                 // share it. Do NOT move this back to 8.
                                 //
                                 // SCOPE (ADR-001): these three pins are only
                                 // claimed when DISPLAY_TARGET ==
                                 // DISPLAY_TARGET_RA8875. In the production PI
                                 // build and in NONE they are free. The 8->5
                                 // rewire is therefore no longer a product
                                 // blocker — it is only required if you select
                                 // the RA8875 debug backend with the panel
                                 // physically mounted. See TODO-24.


// =============================================================================
// HARDWARE — PI 5 DISPLAY LINK    (UART, DISPLAY_TARGET_PI)
// =============================================================================
// Authority: docs/adr/ADR-001-display-architecture.md.
//
// The production renderer is a Raspberry Pi 5 reached over a binary UART link.
// Teensy Serial1 = pin 0 (RX) / pin 1 (TX), wired to the Pi's UART through the
// Freenove GPIO breakout HAT.
//
// *** PINS 0 AND 1 ARE RESERVED FOR THIS LINK. DO NOT REASSIGN THEM. ***
//
// This reservation predates ADR-001 (TODO-24 already rejected pins 0/1 as
// display-reset candidates on these grounds) but was previously protecting an
// interface no build could select. It is now load-bearing.
//
// The wire format, baud/bin budget and receiver algorithm are documented in
// data_sender.h. The DS_* constants there (DS_BAUD_RATE, DS_LIVE_BINS,
// DS_UART_PORT) are the tunables; they are deliberately left at their
// data_sender.h defaults rather than duplicated here, so there is exactly one
// definition of the protocol's parameters.
//
// *** THE WIRE FORMAT IS NOT YET FROZEN. *** An audit against the canonical
// 512-bin MeasurementResult model found five gaps, one of which drops the TF
// clamp mask and would let the Pi render a saturation rail as a measurement.
// SUPERSEDED 2026-09-26: that audit produced protocol v2, which closed all five
// gaps, and TODO-34's schema is frozen. A Pi-side parser, receiver state model
// and test suite now exist under pi/. What remains open in TODO-34 is T1 — the
// measured proof that transmission cannot perturb acquisition — not the layout.
// -----------------------------------------------------------------------------
#define PI_LINK_UART_RX_PIN  0   // Teensy Serial1 RX — RESERVED, do not reassign
#define PI_LINK_UART_TX_PIN  1   // Teensy Serial1 TX — RESERVED, do not reassign


// =============================================================================
// SIGNAL ROUTER — BREADBOARD GPIO ASSIGNMENTS
// =============================================================================
// Teensy 4.1 assignments for docs/breadboard_bringup_v3.md.
// These are breadboard bring-up assignments and are not necessarily the
// permanent production-PCB pin assignments.

// -----------------------------------------------------------------------------
// AUDIO_SHIELD_STACKED — hardware topology fact, not a preference.
//
// 1 = the Rev D Audio Shield is mounted on the Teensy via stacking headers, so
//     all of its populated header positions are electrically connected.
// 0 = the shield is connected by selective flying wires (the pre-2026-09-12
//     bring-up topology); only deliberately wired pins are live.
//
// When stacked, the shield's microSD chip-select occupies pin 10, which is also
// RA8875_CS_PIN. Two devices cannot hold the same active-LOW CS. The #error
// below makes that combination a build failure rather than a bench mystery.
//
// The analyzer's own calibration storage is unaffected either way: it uses
// SD.begin(BUILTIN_SDCARD) — the Teensy 4.1's SDIO socket, not SPI.
// -----------------------------------------------------------------------------
#define AUDIO_SHIELD_STACKED 1

#if (DISPLAY_TARGET == DISPLAY_TARGET_RA8875) && AUDIO_SHIELD_STACKED
#error "RA8875_CS_PIN (10) collides with the stacked Audio Shield's microSD CS. \
Either select DISPLAY_TARGET_PI/_NONE, or move RA8875_CS_PIN to a free pin and \
set AUDIO_SHIELD_STACKED to match the actual hardware. Do not silence this."
#endif

// -----------------------------------------------------------------------------
// EEPROM ALLOCATION  —  board-level resource, reserved here even when unused
// -----------------------------------------------------------------------------
// The Teensy 4.1 emulates 4284 bytes of EEPROM in flash. This firmware uses
// exactly one location, and it is declared HERE rather than inside
// data_sender.h so the reservation is visible in every build.
//
// data_sender.cpp is compiled only for DISPLAY_TARGET_PI, so a _NONE or
// _RA8875 build never touches EEPROM at all. That is precisely why the address
// must be reserved globally: without this declaration, a future EEPROM user
// added under a different DISPLAY_TARGET would silently collide with the link
// session counter, and the symptom would be a Pi that believes the Teensy
// rebooted whenever some unrelated subsystem wrote its own state.
//
// EEPROM_ADDR_LINK_SESSION — uint16_t, the Pi-link boot/session counter.
// See TODO-56 and data_sender.cpp nextSessionId().
#define EEPROM_ADDR_LINK_SESSION   0   // uint16_t — occupies bytes 0..1

#define RELAY_SEND_PIN      14
#define RELAY_RETURN_PIN    15

#define JACK_INSTRUMENT_PIN 16
#define JACK_RIG_SEND_PIN   17
#define JACK_RETURN_TS_PIN  22
#define JACK_RETURN_XLR_PIN 24

#define JACK_DEBOUNCE_MS    50

// -----------------------------------------------------------------------------
// Jack-detect polarity — PER CONNECTOR, not global.
//
// The router's un-inverted convention is "LOW = inserted": a switch that closes
// to ground when a plug goes in. The installed Switchcraft #11 does the
// OPPOSITE. Its switch lug is shorted to the tip contact when the jack is
// EMPTY and opens when a plug is inserted, so with INPUT_PULLUP it reads:
//
//     empty    -> switch closed to the (grounded) tip -> pin LOW
//     inserted -> switch open -> pull-up wins         -> pin HIGH
//
// which is backwards from the router's convention. Hence the invert on pin 16.
//
// These are DELIBERATELY four separate defines rather than one global flag.
// Only the instrument jack is physically installed (Phase 5, 2026-09-08). Rig
// Send, Return TS and Return XLR are Phase 7/8 hardware that does not exist on
// the bench yet, so this file must not assert a sense convention for them. The
// runbook PLANS for all four to end up speaking the same convention -- Jacks #2
// and #3 are also Switchcraft #11s, and the XLR microswitch is to be wired
// COM-NC so it matches -- but a plan is not a built connector. Set each one to
// 1 when that connector is actually wired and its sense is verified at the
// bench, not before.
//
// Applied in signal_router.cpp as: present = raw_present ^ inverted
// -----------------------------------------------------------------------------
// -----------------------------------------------------------------------------
// JACK DETECT AVAILABILITY  —  a HARDWARE/BUILD fact, not a runtime reading
// -----------------------------------------------------------------------------
// 1 = a detect conductor exists for this jack and its GPIO reading is
//     authoritative evidence of plug presence.
// 0 = NO detect hardware. The GPIO still reads something — every detect pin is
//     INPUT_PULLUP (signal_router.cpp:208-211) — but that reading is a pullup
//     artefact, NOT an observation of a plug.
//
// *** ALL FOUR ARE 0 TODAY. That is the as-built truth, not a placeholder. ***
//   instrument  J4 was continuity-identified as a TWO-TERMINAL jack with NO
//               switch terminal (TODO-44). Pin 16 feeds nothing (TODO-5).
//   rig_send    Phase 7 — not built (see the INVERTED comment below).
//   return_ts   Phase 7 — not built.
//   return_xlr  Phase 8 — the D2F-01L microswitch is deliberately not built
//               (TODO-8), and the parts gate in TODO-5 records zero on hand.
//
// These drive ROUTER_STATUS byte [1]. Where a bit is 0 the presentation
// boundary forces the matching presence bit to 0 and the receiver renders
// UNKNOWN — never ABSENT. A Boolean cannot carry "we have no detector", and
// transmitting a pullup artefact as a physical claim is the defect this exists
// to prevent. Raise a flag to 1 ONLY with as-built evidence that the detect
// conductor is fitted AND its sense verified.
#define JACK_INSTRUMENT_DETECT_AVAILABLE 0
#define JACK_RIG_SEND_DETECT_AVAILABLE   0
#define JACK_RETURN_TS_DETECT_AVAILABLE  0
#define JACK_RETURN_XLR_DETECT_AVAILABLE 0

#define JACK_INSTRUMENT_DETECT_INVERTED 1   // Switchcraft #11, INSTALLED 2026-09-08
#define JACK_RIG_SEND_DETECT_INVERTED   0   // Phase 7 — not built, sense unverified
#define JACK_RETURN_TS_DETECT_INVERTED  0   // Phase 7 — not built, sense unverified
#define JACK_RETURN_XLR_DETECT_INVERTED 0   // Phase 8 — not built, sense unverified

// =============================================================================
// FEATURE PROMOTION STATE
// =============================================================================
// These features are present in future/staged routing work but are NOT yet
// promoted into the active breadboard firmware.

// -----------------------------------------------------------------------------
// ENABLE_SGTL_REGISTER_DUMP — read-only codec state diagnostic (TODO-43)
//
// 1 = at the end of audioCap_init(), after the codec has been enabled and
//     configured, print the REQUESTED configuration alongside the ACTUAL
//     contents of five SGTL5000 registers, raw hex plus decoded fields.
// 0 = compiled out entirely.
//
// Added to investigate TODO-43: ~0.123 Vrms measured at the LINE-IN-L pad
// yields SOURCE ~-29.9 dBFS, which implies a full-scale input of ~10.85 Vpp.
// lineInLevel() spans only 3.12 Vpp (level 0) to 0.24 Vpp (level 15), so no
// value of that register can produce the observed result. This reads back what
// the codec actually holds rather than what the firmware asked for.
//
// STRICTLY READ-ONLY. It performs no register writes and does not touch audio
// routing. Remove cleanly by setting to 0.
// -----------------------------------------------------------------------------
#define ENABLE_SGTL_REGISTER_DUMP 1

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
// Window duration = 1024 / 44100 ≈ 23.2 ms of signal per transform.
// Bin width       = 44100 / 1024 ≈ 43.1 Hz per bin.
// Usable bins     = 512 (indices 0–511, covering 0 to 22,050 Hz).
#define FFT_SIZE      1024
#define SAMPLE_RATE   44100
#define FFT_BINS      (FFT_SIZE / 2)


// CHANGED [todo-27]: AudioAnalyzeFFT1024 runs 50 % OVERLAP — it does NOT
// consume 1024 fresh samples per result. Verified in the Audio library source
// (analyze_fft1024.cpp): after setting outputflag = true it resets state = 4,
// keeping the last 4 blocks (512 samples) and needing only 512 NEW ones.
//
// So the RESULT RATE is set by the hop, not by the window:
//      window = 1024 samples ≈ 23.2 ms of signal
//      hop    =  512 samples ≈ 11.6 ms between successive results
//
// Anything computing a RATE or a PERIOD must use the hop. Anything describing
// how much signal a transform sees uses the window. Conflating the two is what
// produced a permanent phantom -46.6 ms timing anomaly in the diagnostics.
#define FFT_HOP_SAMPLES   (FFT_SIZE / 2)


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
// Timing (CHANGED [todo-27] — this arithmetic was wrong by 2×):
//   FFT results arrive every HOP, not every window: 512 / 44100 ≈ 11.6 ms.
//   4 results × 11.6 ms ≈ 46.4 ms per averaged output block ≈ 21.6 blocks/sec.
//   Measured on hardware: 46.3 ms — agreement to 0.3 %.
//   The previous note read "4 frames × 23.2 ms = 92.8 ms ≈ 10.8 blocks/sec",
//   which used the window duration in place of the hop. The HARDWARE was
//   always running at the correct rate; only the expectation was wrong.
//   Display updates every DISPLAY_UPDATE_EVERY_N_FRAMES blocks.
#define FFT_AVERAGE_COUNT     4


// How many averaged output blocks to skip between display redraws.
// 1 → update every block (~46.4 ms, ~21.6 fps) — start here.
// 2 → update every other block (~92.9 ms, ~10.8 fps) — if display stalls audio.
// CHANGED [todo-27]: read "~92.8 ms, ~10.8 fps" and "~185 ms, ~5.4 fps", both
// derived from the window instead of the hop. **This block sat four lines below
// the todo-27 correction above and was missed by it** — that correction was
// scoped to the paragraph being edited and to the EXPECTED_BLOCK_MS identifier,
// and this comment matched neither. Same failure shape as the runbook C1-01
// defect (journal 2026-09-20 (1)): fix every representation, not the one in front
// of you.
// Note the collision: "~92.9 ms" is now CORRECT on the N=2 line (2 × 46.44 ms).
// It is the same number that was wrong on the N=1 line. Check the multiplier
// before assuming either is a defect.
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
