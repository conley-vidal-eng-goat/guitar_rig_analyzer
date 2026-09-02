// =============================================================================
// data_sender.h  —  Guitar Rig Analyzer  v0.6.1
// =============================================================================
// Binary UART data sender — streams live measurement data to an external
// display processor (Raspberry Pi 5 or similar).
//
// This module replaces display_engine for configurations where the Teensy
// focuses on audio capture and DSP while an external board handles all
// rendering. The data contract is a compact binary packet protocol over UART.
//
// PACKET TYPES:
//   0x01  LIVE_FRAME     Periodic live data (~11 Hz)
//   0x02  RESULT         Full measurement result (on RESULT_READY)
//   0x03  STATUS         Status/event message string
//   0x04  ABORTED        Abort reason string
//   0x05  ROUTER_STATUS  Jack/route/monitor state snapshot
//
// WIRE FORMAT (all packets):
//   [0-1]    uint16  SYNC_WORD = 0xAA55 (little-endian)
//   [2]      uint8   packet_type
//   [3-4]    uint16  payload_length (bytes, excludes header and CRC)
//   [5..N]   payload (type-specific, little-endian)
//   [N+1..N+2] uint16 CRC-16/CCITT over payload only
//
// BAUD RATE AND BIN RESOLUTION:
//   The live frame can be sent at different bin resolutions depending
//   on baud rate. Higher baud = more bins = finer spectral detail.
//
//   Baud     Live bins   Frame size   Bandwidth @ 11 Hz
//   115200   64 bins     ~880 B       ~9.7 KB/s  (fits in 11.5 KB/s)
//   230400   128 bins    ~1.6 KB      ~18 KB/s   (fits in 23 KB/s)
//   460800   256 bins    ~3.2 KB      ~35 KB/s   (fits in 46 KB/s)
//   921600   512 bins    ~6.3 KB      ~69 KB/s   (fits in 92 KB/s)
//
//   Result packets always send the full 512-bin canonical grid regardless
//   of baud rate — they are one-shot and not time-critical.
//
//   The default configuration is 460800 baud with 128 live bins. This
//   provides good spectral resolution for all visualizations including
//   the Radial Tone Fingerprint (48 bands derived from 128 bins) while
//   leaving comfortable bandwidth headroom.
//
// The receiver (Pi-side) should:
//   1. Scan for SYNC_WORD
//   2. Read packet_type and payload_length
//   3. Read payload + CRC
//   4. Verify CRC, discard on mismatch
//   5. Parse payload based on packet_type
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

// =============================================================================
// CONFIGURATION
// =============================================================================
// These can be overridden in config.h before including this header.

#ifndef DS_BAUD_RATE
#define DS_BAUD_RATE          460800
#endif

#ifndef DS_LIVE_BINS
#define DS_LIVE_BINS          128     // Bins per spectrum in live frame packets
#endif

#ifndef DS_UART_PORT
#define DS_UART_PORT          Serial1  // Teensy hardware UART — pins 0 (RX) / 1 (TX)
#endif

// =============================================================================
// PUBLIC API
// =============================================================================

// -----------------------------------------------------------------------------
// dataSender_init()
// Configures the UART port and sends an initial handshake/identification
// packet so the receiver knows the protocol version and bin configuration.
// Call from setup() in place of displayEngine_init().
// Returns true always (UART init cannot fail).
// -----------------------------------------------------------------------------
bool dataSender_init();

// -----------------------------------------------------------------------------
// dataSender_sendLiveFrame(frame)
// Sends a decimated live data packet containing:
//   - Peak levels and clipping flags
//   - FFT source spectrum (DS_LIVE_BINS bins, decimated from FFT_BINS)
//   - FFT return spectrum (DS_LIVE_BINS bins)
//   - Transfer function dB (DS_LIVE_BINS bins)
//   - TF confidence and persistence flag
//   - Measurement state
//   - Frame counter and timestamp
//
// Call at the same rate as the old displayEngine_update() — typically
// every DISPLAY_UPDATE_EVERY_N_FRAMES audio blocks (~11 Hz).
// -----------------------------------------------------------------------------
void dataSender_sendLiveFrame(const AudioFrame* frame);

// -----------------------------------------------------------------------------
// dataSender_sendResult(result, insights)
// Sends the full 512-bin measurement result plus insight list.
// This is a large packet (~14 KB) sent once on RESULT_READY.
// At 460800 baud this takes ~300ms to transmit, which is fine —
// the user is looking at the result screen, not expecting frame updates.
// -----------------------------------------------------------------------------
void dataSender_sendResult(const MeasurementResult& result,
                           const InsightList& insights);

// -----------------------------------------------------------------------------
// dataSender_sendAborted(reason)
// Sends a short packet with the abort reason string.
// Call on MeasurementEvent::ABORTED.
// -----------------------------------------------------------------------------
void dataSender_sendAborted(const char* reason);

// -----------------------------------------------------------------------------
// dataSender_sendStatus(message)
// Sends a short status/event message string.
// Replaces displayEngine_drawStatusMessage().
// The receiver can display this as a toast/banner or log it.
// -----------------------------------------------------------------------------
void dataSender_sendStatus(const char* message);

// -----------------------------------------------------------------------------
// dataSender_sendRouterStatus()
// Sends the current signal router state snapshot (jack states, return source,
// injection active, monitor mode, route description).
// Call when router events occur or on demand.
// -----------------------------------------------------------------------------
void dataSender_sendRouterStatus();

#endif // DATA_SENDER_H
