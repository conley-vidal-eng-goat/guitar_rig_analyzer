// =============================================================================
// data_sender.h  —  Guitar Rig Analyzer
// =============================================================================
// Binary UART measurement interface to the Raspberry Pi 5 display processor.
//
// Authority: docs/adr/ADR-001-display-architecture.md
// Audit that produced protocol v2: docs/pi_link_protocol_audit.md
//
// This module is the DISPLAY_TARGET_PI backend of the presentation boundary.
// Nothing calls it directly — the application and the validation harness both
// call presentation_* (presentation.h). See that header for the contract.
//
// This file carries no product version of its own. The single authoritative
// firmware version is FIRMWARE_VERSION in config.h; the wire format carries its
// own independent PI_PROTOCOL_VERSION, also in config.h. They are different
// compatibility concepts and must not be conflated — a firmware bump that does
// not change the wire format must not invalidate a working receiver.
//
// =============================================================================
// THE GOVERNING INVARIANT
// =============================================================================
//   *** The Teensy determines truth. The Pi presents truth. ***
//
// Applied to this protocol as a test, which is the form that is actually useful:
//
//   For every field the Pi displays, ask: is this a FACT the Teensy knows, or a
//   JUDGEMENT the Pi is reconstructing? If it is a judgement — valid/invalid,
//   clipped, clamped, quality grade, calibration state, confidence — the answer
//   is send it.
//
// Protocol v1 failed that test in four places. Every one is now closed, and the
// acceptance tests in docs/pi_link_protocol_audit.md exist to keep them closed:
//
//   v1 defect                                        v2 resolution
//   -----------------------------------------------  -------------------------
//   TF clamp state not transmitted (L1)              per-bin clamp counts +
//                                                    frame total, LIVE_FRAME
//   result_valid not transmitted (R1)                byte 0 of RESULT
//   calibration_provenance not transmitted (R2)      char[96] in RESULT
//   calibration_type/_warnings not transmitted (R3)  type byte + warning bits
//
// =============================================================================
// DELIVERY POLICY  —  presentation transport must be lossy before measurement is
// =============================================================================
// Dropping a live visualization frame is acceptable. Delaying acquisition or DSP
// because the Pi cannot keep up is NOT. A dead, slow, or disconnected Pi must
// never become a measurement failure.
//
// Every write in this module is therefore gated on Serial availableForWrite().
// *** THERE ARE NO BLOCKING WRITES. *** Do not add one.
//
//   PACKET         DELIVERY      ON NO ROOM              RATIONALE
//   -------------  ------------  ----------------------  ---------------------
//   LIVE_FRAME     best effort   dropped, counted        latest-wins; a stale
//                                                        frame has no value
//   RESULT         reliable      staged, drained across  a completed
//                                loop iterations          measurement matters
//   STATUS         best effort   dropped, counted        notification only
//   ABORTED        best effort   dropped, counted        see safety net below
//   ROUTER_STATUS  best effort   dropped, counted        snapshot, resendable
//   HELLO          best effort   dropped, counted        retried by the Pi
//
// SAFETY NET FOR DROPPED EVENTS: measurement_state travels in EVERY live frame.
// A dropped ABORTED packet therefore costs the reason string, not the fact —
// the Pi still observes state == ABORTED on the next frame and can render a
// generic abort. Event loss degrades gracefully rather than desynchronising the
// Pi's state model. This is deliberate and receivers should rely on it: treat
// the live frame's state byte as authoritative, and event packets as enrichment.
//
// RELIABLE PATH: dataSender_sendResult() serialises into a staging buffer and
// returns immediately. dataSender_service() — which MUST be called every loop
// iteration — drains it as UART room appears.
//
// If a second result arrives while one is still draining, the new one replaces it
// (latest-wins) and the supersession is counted. Note precisely what a receiver
// then sees: the truncated head of the superseded packet, immediately followed by
// a complete new packet starting with a fresh SYNC_WORD. That is safe because the
// receiver's CRC check rejects the truncated fragment and its scan resynchronises
// on the next SYNC_WORD — which is exactly what step 1 of the receiver algorithm
// is for. It is NOT safe for a receiver that assumes byte-stream continuity
// between packets, so do not write one that does.
//
// =============================================================================
// WIRE FORMAT (all packets, little-endian)
// =============================================================================
//   [0-1]      uint16  SYNC_WORD = 0xAA55
//   [2]        uint8   packet_type
//   [3-4]      uint16  payload_length (bytes; excludes header and CRC)
//   [5..N]     payload
//   [N+1..N+2] uint16  CRC-16/CCITT over payload only
//
// PACKET TYPES
//   0x01  LIVE_FRAME     periodic live data (~11 Hz)
//   0x02  RESULT         full measurement result (on RESULT_READY)
//   0x03  STATUS         status/event message string
//   0x04  ABORTED        abort reason string
//   0x05  ROUTER_STATUS  jack/route/monitor state snapshot
//   0x06  HELLO          structured identification — REPLACES v1's parsed string
//   0x07  VIEW           explicit view transition (audit T3)
//
// RECEIVER ALGORITHM
//   1. Scan for SYNC_WORD
//   2. Read packet_type and payload_length
//   3. Read payload + CRC
//   4. Verify CRC, discard on mismatch and resume scanning at step 1
//   5. Parse payload based on packet_type
//   6. Ignore unknown packet types by skipping payload_length bytes — this is
//      how a v2 receiver stays alive across a future additive packet type.
//
// BAUD RATE AND BIN RESOLUTION
//   Baud     Live bins   Frame size   Average bandwidth @ 11 Hz
//   115200   64 bins     ~0.8 KB      ~9 KB/s   (of 11.5 KB/s)
//   230400   128 bins    ~1.7 KB      ~19 KB/s  (of 23 KB/s)
//   460800   256 bins    ~3.4 KB      ~37 KB/s  (of 46 KB/s)
//   921600   512 bins    ~6.7 KB      ~74 KB/s  (of 92 KB/s)
//
//   *** THIS TABLE MODELS AVERAGE THROUGHPUT AND THAT IS NOT THE BINDING
//   CONSTRAINT. *** The binding constraint is burst occupancy inside one audio
//   block period: at 460800 baud a 128-bin live frame is ~37 ms of wire time
//   against a measured ~46.3 ms block period. The delivery policy above is what
//   makes that safe — the frame is dropped rather than blocking the loop. See
//   docs/pi_link_protocol_audit.md finding T1, whose predicted figures have NOT
//   yet been measured on hardware.
//
//   Default: 460800 baud, 128 live bins.
//   Result packets always send the full FFT_BINS canonical grid.
// =============================================================================

#ifndef DATA_SENDER_H
#define DATA_SENDER_H

#include <Arduino.h>
#include "config.h"
#include "audio_engine.h"
#include "measurement_core.h"
#include "insights_engine.h"
#include "signal_router.h"

// =============================================================================
// PROTOCOL CONSTANTS
// =============================================================================

#define DS_SYNC_WORD          0xAA55
#define DS_PACKET_LIVE_FRAME  0x01
#define DS_PACKET_RESULT      0x02
#define DS_PACKET_STATUS      0x03
#define DS_PACKET_ABORTED     0x04
#define DS_PACKET_ROUTER      0x05
#define DS_PACKET_HELLO       0x06
#define DS_PACKET_VIEW        0x07

// View ids for DS_PACKET_VIEW. RESULT and ABORTED transitions are implied by
// their own packets arriving; this type exists for transitions that carry no
// other data — principally the return to live after an acknowledgement.
#define DS_VIEW_LIVE          0x00

#define DS_FRAMING_BYTES      7      // 5-byte header + 2-byte CRC
#define DS_MAX_STRING_PAYLOAD 200    // STATUS / ABORTED string cap

// =============================================================================
// CONFIGURATION
// =============================================================================
// Overridable in config.h before including this header.

#ifndef DS_BAUD_RATE
#define DS_BAUD_RATE          460800
#endif

#ifndef DS_LIVE_BINS
#define DS_LIVE_BINS          128    // Bins per spectrum in live frame packets
#endif

#ifndef DS_UART_PORT
#define DS_UART_PORT          Serial1  // Teensy hardware UART — pins 0 (RX) / 1 (TX)
#endif

// TX buffer added to the UART at init via addMemoryForWrite(). It MUST exceed
// one whole framed live frame, otherwise availableForWrite() can never report
// room for one and every frame would be dropped — a silent total failure of the
// live path. Sized for ~2 live frames at the default 128-bin configuration.
#ifndef DS_TX_BUFFER_BYTES
#define DS_TX_BUFFER_BYTES    4096
#endif

// HELLO re-announcement period. HELLO is 47 B framed — about 1.02 ms of wire
// time at 460800 baud, so at 1 Hz it costs ~0.1 % of the link against the
// ~40 % the live frames already occupy. Cheap enough that a shorter reconnect
// wait is not worth buying with more traffic.
#ifndef DS_HELLO_REANNOUNCE_MS
#define DS_HELLO_REANNOUNCE_MS  1000
#endif

// =============================================================================
// DERIVED SIZES  —  compile-time checked
// =============================================================================

// Source bins collapsed into each transmitted live bin.
#define DS_DECIM_RATIO        (FFT_BINS / DS_LIVE_BINS)

// Live frame payload: 18-byte header + 3 float spectra + 1 packed-nibble
// coverage byte per transmitted bin.
#define DS_LIVE_PAYLOAD_BYTES (18 + (DS_LIVE_BINS * 3 * 4) + DS_LIVE_BINS)

// Worst-case RESULT payload: fixed block + 4 canonical spectra + max insights.
#define DS_RESULT_FIXED_BYTES 156
#define DS_INSIGHT_ENTRY_BYTES 138
#define DS_RESULT_PAYLOAD_MAX (DS_RESULT_FIXED_BYTES \
                               + (FFT_BINS * 4 * 4)  \
                               + 1                   \
                               + (INSIGHTS_MAX_COUNT * DS_INSIGHT_ENTRY_BYTES))

// Staging buffer for the reliable RESULT path, framing included.
#define DS_RESULT_STAGE_BYTES (DS_RESULT_PAYLOAD_MAX + DS_FRAMING_BYTES)

static_assert(FFT_BINS % DS_LIVE_BINS == 0,
              "DS_LIVE_BINS must divide FFT_BINS evenly");
static_assert(DS_DECIM_RATIO <= 15,
              "DS_DECIM_RATIO must fit in a nibble — the live frame packs the "
              "per-bin clamped and valid source-bin counts into one byte each "
              "(high nibble = clamped, low nibble = valid). Raise DS_LIVE_BINS.");
static_assert(DS_LIVE_PAYLOAD_BYTES + DS_FRAMING_BYTES < DS_TX_BUFFER_BYTES,
              "DS_TX_BUFFER_BYTES must exceed one framed live frame, or "
              "availableForWrite() can never report room and every live frame "
              "would be dropped");

// =============================================================================
// LIVE_FRAME (0x01) PAYLOAD LAYOUT
// =============================================================================
//   [0]       uint8   measurement_state
//   [1]       uint8   flags: bit0 source_clip, bit1 return_clip,
//                            bit2 tf_persistence_active, bit3..7 reserved
//   [2-3]     uint16  output_block_number (lower 16 bits)
//   [4-7]     float   peak_source_dbfs
//   [8-11]    float   peak_return_dbfs
//   [12-15]   float   tf_confidence
//   [16-17]   uint16  tf_clamped_count — clamped bins over all FFT_BINS source
//                     bins, NOT over the transmitted bins. A cheap whole-curve
//                     summary for the renderer and for logs.
//   [18..]    float[DS_LIVE_BINS]  fft_source   (decimated, linear magnitude)
//   [..]      float[DS_LIVE_BINS]  fft_return   (decimated, linear magnitude)
//   [..]      float[DS_LIVE_BINS]  tf_db        (decimated, dB)
//   [..]      uint8[DS_LIVE_BINS]  coverage — per transmitted bin:
//                     high nibble = number of source bins CLAMPED  (0..ratio)
//                     low  nibble = number of source bins VALID    (0..ratio)
//
// *** HOW A RECEIVER MUST RENDER tf_db — THIS IS NOT OPTIONAL. ***
//
// A clamped bin is a SATURATION RAIL, not a measurement. audio_engine clamps
// each bin into [TF_DB_MIN-6, TF_DB_MAX+6] before the EMA so a boundary outlier
// cannot poison the smoothing history; the railed value then sits in tf_db[]
// indistinguishably from real data unless the clamp state is consulted
// (audio_engine.h "TF clamp markers").
//
// Observed 2026-09-07 with nothing connected to RETURN_NODE: the true TF was
// ~-47 dB, 23 dB below the -24.0 dB rail, and a consumer that ignored the clamp
// state reported "1kHz=-24.0dB" in 33 of 33 consecutive windows as though it
// were data.
//
//   clamped nibble == 0        → plot normally
//   0 < clamped < valid        → plot, but mark the bin as partially saturated
//   clamped == ratio           → DO NOT plot the value as a measurement. Draw a
//                                saturation indicator at the rail instead.
//   valid nibble == 0          → no energised source bins: PEN LIFT, draw nothing
//   0 < valid < ratio          → partial coverage; the value is a mean over
//                                fewer source bins than the others
//
// The valid nibble exists because decimation otherwise destroys NaN semantics:
// a block averaging one valid bin and three NaN would arrive indistinguishable
// from one averaging four valid bins (audit finding L3). NaN in tf_db means the
// source bin fell below TF_SOURCE_GATE — the pen-lift signal.
//
// DECIMATION SEMANTICS — stated so the Pi knows what it is plotting:
//   fft_source / fft_return : MAXIMUM of the source bins (peak-preserving).
//                             An arithmetic mean buries narrow peaks — one bin
//                             at 0.5 among three at 0.001 means 0.126, a 12 dB
//                             under-report, which for a spectrum display is the
//                             wrong default (audit finding L2).
//   tf_db                   : arithmetic MEAN in dB over the valid source bins,
//                             which is a geometric mean of power. Appropriate
//                             for a transfer-function curve; the valid/clamped
//                             nibbles say how much to trust each point.
//
// =============================================================================
// RESULT (0x02) PAYLOAD LAYOUT
// =============================================================================
//   [0]       uint8   result_valid               <-- v1 omitted this entirely
//   [1]       uint8   result_quality
//   [2]       uint8   flags: bit0 clip_detected, bit1 calibration_applied,
//                            bit2 generator_active
//   [3]       uint8   calibration_type
//   [4]       uint8   calibration_warning_bits:
//                       bit0 calibration_missing
//                       bit1 line_in_level_mismatch
//                       bit2 partial_calibration_applied
//                       bit3 calibration_from_import
//                       bit4 hard_parameter_mismatch
//   [5]       uint8   reserved (0)
//   [6-7]     uint16  n_averages_completed
//   [8-11]    float   mean_coherence
//   [12-15]   float   valid_bin_fraction
//   [16-19]   uint32  timestamp_ms
//   [20]      uint8   estimator
//   [21]      uint8   stimulus
//   [22]      uint8   fft_mode
//   [23]      uint8   window_function
//   [24-25]   uint16  fft_size
//   [26-29]   uint32  capture_start_block
//   [30-33]   uint32  capture_end_block
//   [34]      uint8   source_node_ch
//   [35]      uint8   return_node_ch
//   [36]      uint8   line_in_level
//   [37]      uint8   reserved (0)
//   [38-39]   uint16  clip_source_count
//   [40-41]   uint16  clip_return_count
//   [42-57]   char[16] firmware_version          (NUL-padded)
//   [58-153]  char[96] calibration_provenance    (NUL-padded)
//   [154-155] uint16  reserved (0)
//   [156..]   float[FFT_BINS]  tf_cal_mag_db
//   [..]      float[FFT_BINS]  tf_cal_phase_rad
//   [..]      float[FFT_BINS]  group_delay_ms
//   [..]      float[FFT_BINS]  coherence
//   [..]      uint8   insight_count
//   [..]      insight entries, DS_INSIGHT_ENTRY_BYTES each:
//               [0]      uint8   mode (MEASUREMENT vs ADVISORY)
//               [1]      uint8   severity
//               [2-5]    float   frequency_hz
//               [6-9]    float   magnitude_db
//               [10-73]  char[64] title  (NUL-padded)
//               [74-137] char[64] detail (NUL-padded)
//
// Hardware context (fft_size, capture blocks, node channels, line_in_level) is
// present so Compare/Recall is meaningful: without line_in_level a receiver will
// happily A/B two measurements taken at different input gains and present the
// difference as a rig difference (audit finding R6).
//
// NOT SENT, deliberately: S_xx_db / S_yy_db (audit R4 — would add 4 KB per
// packet; revisit once T1 is measured), phase_unwrapped and tf_raw_mag_db
// (audit R7 — group delay is sent and raw magnitude needs the cal curve anyway).
//
// =============================================================================
// HELLO (0x06) PAYLOAD LAYOUT
// =============================================================================
//   [0-1]     uint16  protocol_version   (PI_PROTOCOL_VERSION)
//   [2-3]     uint16  live_bins          (DS_LIVE_BINS)
//   [4-5]     uint16  fft_bins           (FFT_BINS)
//   [6-7]     uint16  decim_ratio        (DS_DECIM_RATIO)
//   [8-11]    uint32  baud_rate
//   [12-15]   uint32  sample_rate
//   [16-17]   uint16  insights_max       (INSIGHTS_MAX_COUNT)
//   [18-19]   uint16  session_id         <-- was "reserved (0)" before v2.1
//   [20-23]   uint32  capability_bits:
//                       bit0 DUT injection compiled in (ENABLE_DUT_INJECTION)
//                       bit1 monitor mode compiled in  (ENABLE_MONITOR_MODE)
//                       bit2 MODE_PRECISION available
//                       bit3 MODE_LF available
//   [24-39]   char[16] firmware_version  (NUL-padded)
//
// v1 sent this as a human-readable STATUS string the receiver had to parse to
// establish its own compatibility contract (audit finding T2). A capability
// bitmap also lets the Pi distinguish "monitor mode is off" from "monitor mode
// does not exist in this build", which v1's ROUTER_STATUS could not (T4) — so a
// receiver does not render a control for a capability that cannot respond.
//
// *** HELLO IS RE-ANNOUNCED PERIODICALLY. IT IS NOT A ONE-TIME GREETING. ***
//
// HELLO is the ONLY carrier of fft_bins, and a RESULT's four float[FFT_BINS]
// arrays cannot be located without it — the insight_count that would let a
// receiver solve for the length sits AFTER the arrays. So a receiver that
// never saw HELLO can never decode a RESULT.
//
// Until 2026-09-26 HELLO was sent exactly once, from dataSender_init(), on the
// best-effort path — so it could also simply be DROPPED into a full TX buffer.
// A Pi that attached late, restarted, or lost that one frame was permanently
// unable to decode a result until the Teensy rebooted (TODO-56).
//
// It is now re-announced every DS_HELLO_REANNOUNCE_MS from dataSender_service(),
// gated only on no RESULT being staged. Deliberately NOT gated on measurement
// state: HELLO describes the instrument and protocol session, not the
// measurement. A Pi reconnecting during ARMED, CAPTURE, PROCESSING, RESULT,
// EXPORTING — or during a sticky ABORTED — must be able to obtain geometry and
// reconstruct that state, not sit geometry-blind waiting for IDLE.
//
// *** session_id — WHAT IT IS AND WHAT IT IS NOT ***
//
// Periodic announcement alone creates an ambiguity it does not solve: a
// receiver seeing repeated HELLOs cannot tell a routine re-announcement from a
// NEW Teensy session. session_id resolves it.
//
//   Contract:  constant for the whole of one Teensy boot/session, and changes
//              across a Teensy restart.
//   Receiver:  a CHANGED session_id is authoritative evidence that prior
//              session state is stale. Invalidate it and rebuild from current
//              telemetry — do not assume continuity.
//
// It is NOT a security nonce (it is deliberately predictable), NOT a
// measurement or result identifier, and NOT a device identity — two different
// Teensy boards can both be at boot 42. If device identity is ever needed,
// HW_OCOTP_MAC0 is the chip serial and would be a NEW field, not this one.
//
// The block counter cannot substitute for this: output_block_number is 16 bits
// and wraps roughly every 50 minutes on its own, so "it went backwards" is not
// sound evidence of a reboot.
//
// Generation, and why: see nextSessionId() in data_sender.cpp.
// =============================================================================

// =============================================================================
// VIEW (0x07) PAYLOAD LAYOUT
// =============================================================================
//   [0]  uint8  view_id   (DS_VIEW_LIVE)
//
// v1 had no view-change packet, so a return-to-live had to be signalled as a
// STATUS string the Pi would have to sniff for a magic prefix — a view
// transition indistinguishable from ordinary status text (audit finding T3).
// A receiver drives its view state machine from this packet plus the arrival of
// RESULT / ABORTED, never from status text.
// =============================================================================

// =============================================================================
// TRANSPORT STATISTICS
// =============================================================================
// Instrumentation for audit finding T1. Every figure here is MEASURED at
// runtime, not predicted. Phase 10 acceptance requires these to show that a
// disconnected or slow Pi cannot perturb measurement timing.

struct DataSenderStats {
    // Live path — best effort
    uint32_t live_sent;
    uint32_t live_dropped;            // no UART room; the safe outcome
    uint32_t live_dropped_streak_max; // longest consecutive drop run

    // Reliable path
    uint32_t results_queued;
    uint32_t results_sent;            // fully drained onto the wire
    uint32_t results_superseded;      // replaced mid-drain by a newer result
    uint32_t result_bytes_abandoned;  // bytes of superseded results never sent
    uint32_t result_drain_ms_max;     // longest queue-to-wire completion

    // Event path — best effort
    uint32_t events_sent;
    uint32_t events_dropped;

    // HELLO announcement path — best effort, and COUNTED SEPARATELY ON PURPOSE.
    // Re-announcement is expected to be dropped under sustained backpressure;
    // that is the policy working, not a fault. Folding those drops into
    // events_dropped would make it impossible to read T1 run 3, where a
    // suspended reader keeps the UART full by design — every second would add
    // a HELLO drop and the event figure would stop meaning anything.
    uint32_t hello_sent;
    uint32_t hello_dropped;

    // Timing of the calls themselves: this is the number that matters for T1.
    uint32_t send_calls;
    uint32_t send_us_max;             // worst single presentation-facing call
    uint32_t send_us_last;
    uint64_t send_us_total;           // for the mean

    // UART pressure
    uint32_t tx_room_min;             // lowest availableForWrite() observed
    uint32_t service_calls;
    bool     result_pending;
    uint32_t result_pending_bytes;
};

// =============================================================================
// PUBLIC API
// =============================================================================
// Reached only through presentation.cpp's DISPLAY_TARGET_PI arm.

// -----------------------------------------------------------------------------
// dataSender_init()
// Configures the UART, installs the extended TX buffer, establishes the session
// id, and sends the first HELLO.
// Returns true; UART init cannot fail. A Pi that is absent or not listening is
// indistinguishable from one that is, and is equally harmless — which is
// exactly why HELLO must not depend on anyone having been there to hear it.
// -----------------------------------------------------------------------------
bool dataSender_init();

// -----------------------------------------------------------------------------
// dataSender_service()
// *** MUST be called every loop iteration. *** Drains any pending RESULT onto
// the UART as room appears. Without it the reliable path never completes.
// Cheap and non-blocking when nothing is pending.
//
// Also re-announces HELLO every DS_HELLO_REANNOUNCE_MS, but ONLY while no
// RESULT is staged — the reliable path is never made to compete with an
// announcement. Both remain best-effort and non-blocking; neither may ever
// become a blocking write.
// -----------------------------------------------------------------------------
void dataSender_service();

// -----------------------------------------------------------------------------
// dataSender_sendLiveFrame(frame)
// Best effort. Sends a decimated live frame with per-bin clamp and validity
// coverage. Dropped and counted if the UART lacks room for the whole packet —
// never partially written, never blocking.
// -----------------------------------------------------------------------------
void dataSender_sendLiveFrame(const AudioFrame* frame);

// -----------------------------------------------------------------------------
// dataSender_sendResult(result, insights)
// Reliable. Serialises into the staging buffer and returns immediately; the
// packet reaches the wire over subsequent dataSender_service() calls. A result
// arriving while another is draining supersedes it (latest-wins, counted).
// -----------------------------------------------------------------------------
void dataSender_sendResult(const MeasurementResult& result,
                           const InsightList& insights);

// -----------------------------------------------------------------------------
// dataSender_sendAborted(reason) / dataSender_sendStatus(message)
// Best effort, dropped and counted if there is no room. A dropped ABORTED costs
// the reason string only — measurement_state in every live frame still tells the
// Pi the measurement aborted.
// -----------------------------------------------------------------------------
void dataSender_sendAborted(const char* reason);
void dataSender_sendStatus(const char* message);

// -----------------------------------------------------------------------------
// dataSender_sendRouterStatus()
// Best effort snapshot of jack/route/monitor state.
// -----------------------------------------------------------------------------
void dataSender_sendRouterStatus();

// -----------------------------------------------------------------------------
// dataSender_sendView(view_id)
// Best effort explicit view transition. See DS_PACKET_VIEW.
// -----------------------------------------------------------------------------
void dataSender_sendView(uint8_t view_id);

// -----------------------------------------------------------------------------
// dataSender_getStats() / dataSender_resetStats()
// Measured transport health. See DataSenderStats.
// -----------------------------------------------------------------------------
const DataSenderStats& dataSender_getStats();
void dataSender_resetStats();

// -----------------------------------------------------------------------------
// dataSender_printDiagnostics()
// Human-readable transport report to USB Serial, including the measured
// worst-case blocking figure that audit finding T1 predicts but has not
// confirmed. Print it alongside audio block timing, never alone — the question
// is whether transmission perturbed acquisition.
// -----------------------------------------------------------------------------
void dataSender_printDiagnostics();

#endif // DATA_SENDER_H
