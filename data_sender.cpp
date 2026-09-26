// =============================================================================
// CONDITIONAL COMPILATION — Pi 5 (UART) backend
// =============================================================================
// This entire translation unit is compiled ONLY when DISPLAY_TARGET selects this
// backend. Authority: docs/adr/ADR-001-display-architecture.md.
//
// WHY THE GUARD IS HERE AND NOT JUST IN presentation.cpp: an Arduino/arduino-cli
// build compiles EVERY .cpp in the sketch folder, whether or not anything
// includes its header. Without this guard, selecting a different DISPLAY_TARGET
// would still compile and link the UART packet protocol, so DISPLAY_TARGET_NONE
// would not actually be free and the unselected backend would remain a build
// dependency. Verified by compile, not assumed.
//
// The guard deliberately wraps the #includes too — the include itself is the
// dependency being removed.
//
// Nothing else in the firmware calls into this file directly. The application
// and the validation harness both go through presentation_* (data_sender.h is
// reached only by presentation.cpp's matching arm).
// =============================================================================

#include "config.h"

#if DISPLAY_TARGET == DISPLAY_TARGET_PI

// =============================================================================
// data_sender.cpp  —  Guitar Rig Analyzer
// =============================================================================
// Wire format, packet layouts and delivery policy: see data_sender.h.
//
// *** THE CENTRAL RULE OF THIS FILE: NO BLOCKING WRITES. ***
//
// *** AND ITS COMPANION (TODO-59): TRANSPORT ATOMICITY. ***
//   While a staged RESULT is draining, no independently framed best-effort
//   packet may write bytes to this stream.
// Enforced centrally in trySendBestEffort(), which every best-effort packet
// type passes through. See the comment there for why the SMALL packets are the
// dangerous ones, and why this is not left to individual producers to
// remember.
//
// Presentation transport must be lossy before measurement becomes lossy. A dead,
// slow or disconnected Pi must never perturb acquisition timing. Every byte
// written here is gated on availableForWrite(); a packet that does not fit is
// dropped whole and counted, never partially emitted.
//
// If you add a code path that calls DS_UART_PORT.write() without first checking
// room for the ENTIRE packet, you have reintroduced the failure this
// architecture exists to prevent — the same shape as the RA8875 waitPoll() spin
// that stretched the audio block period from 46 ms to 2194 ms.
// =============================================================================

#include "data_sender.h"
#include "measurement_engine.h"   // measurementEngine_getState()
#include "signal_router.h"
#include <math.h>
#include <EEPROM.h>               // session id — see nextSessionId()
#include "audio_capture.h"        // audioCap_getBlockCounter() — STATE timestamp

// =============================================================================
// STATE
// =============================================================================

static DataSenderStats s_stats;
static uint32_t s_live_drop_streak = 0;

// DEFINED HERE, ahead of its siblings, because the transport atomicity
// invariant (TODO-59) inside trySendBestEffort() reads it and that function is
// declared above the rest of the reliable path's state.
static uint32_t s_result_len = 0;   // total framed bytes staged

// Session identity and re-announcement cadence. Deliberately NOT part of
// DataSenderStats: resetStats() is called at the start of every T1 measurement
// window, and neither the session id nor the announcement phase may be
// disturbed by an operator pressing 't'.
static uint16_t s_session_id    = 0;
static uint32_t s_last_hello_ms = 0;
static uint32_t s_last_state_ms  = 0;
static uint32_t s_last_router_ms = 0;

// Extended UART TX buffer. Without this the default Serial1 TX buffer is far
// smaller than one live frame, availableForWrite() could never report room, and
// every single live frame would be dropped — a silent total failure of the live
// path that would look like a Pi-side bug. DMAMEM keeps it out of the tight
// RAM1 budget.
DMAMEM static uint8_t s_tx_buffer[DS_TX_BUFFER_BYTES];

// Staging buffer for the reliable RESULT path, holding one fully framed packet
// (header + payload + CRC) drained across loop iterations.
DMAMEM static uint8_t s_result_stage[DS_RESULT_STAGE_BYTES];
// s_result_len is defined near the top of this file — see the note there.
static uint32_t s_result_sent = 0;   // bytes already on the wire
static uint32_t s_result_queued_ms = 0;

// Scratch for live frame assembly. Static rather than stack: the worst-case
// live payload at 512 bins is ~6.7 KB, which has no business on the loop stack.
DMAMEM static uint8_t s_live_payload[DS_LIVE_PAYLOAD_BYTES];

// =============================================================================
// CRC-16/CCITT  (same polynomial as export_engine's, distinct from its CRC-32)
// =============================================================================

static uint16_t crc16_update(uint16_t crc, uint8_t data) {
    crc ^= (uint16_t)data << 8;
    for (uint8_t i = 0; i < 8; i++) {
        if (crc & 0x8000) crc = (crc << 1) ^ 0x1021;
        else              crc = crc << 1;
    }
    return crc;
}

static uint16_t crc16_block(const uint8_t* buf, size_t len) {
    uint16_t crc = 0xFFFF;
    for (size_t i = 0; i < len; i++) crc = crc16_update(crc, buf[i]);
    return crc;
}

// =============================================================================
// PRIVATE: UART pressure and non-blocking emission
// =============================================================================
// Framing decisions are always made against the WHOLE packet length before any
// byte is emitted. The two paths frame differently by necessity — the live path
// writes header/payload/CRC as three writes after one room check, the reliable
// path frames into its staging buffer so it can be drained in chunks — so there
// is deliberately no shared frame() helper to tempt a partial write.

// Copy a C string into a fixed-width NUL-padded wire field.
// Uses memset + bounded memcpy rather than strncpy: strncpy on a source exactly
// as long as the limit does not NUL-terminate, which is safe here only because
// of the memset, and compilers correctly warn about the pattern. Being explicit
// is clearer than silencing it.
static void writeFixedString(uint8_t* dst, size_t field_bytes, const char* src) {
    memset(dst, 0, field_bytes);
    if (src == nullptr) return;
    const size_t n = strnlen(src, field_bytes - 1);   // always leave a NUL
    memcpy(dst, src, n);
}

// Record UART pressure on every decision point.
static inline uint32_t txRoom() {
    const int room = DS_UART_PORT.availableForWrite();
    const uint32_t r = (room > 0) ? (uint32_t)room : 0u;
    if (r < s_stats.tx_room_min) s_stats.tx_room_min = r;
    return r;
}

// -----------------------------------------------------------------------------
// trySendBestEffort()
// Frames into a scratch buffer and emits only if the WHOLE packet fits.
// Returns true if sent. Never blocks, never partially writes.
// -----------------------------------------------------------------------------
static bool trySendBestEffort(uint8_t packet_type,
                              const uint8_t* payload, uint16_t len) {
    // -------------------------------------------------------------------------
    // TRANSPORT ATOMICITY INVARIANT (TODO-59)
    //
    //   While a staged RESULT is draining, NO independently framed best-effort
    //   packet may write bytes to this stream.
    //
    // dataSender_service() drains the staged RESULT in chunks across loop
    // iterations, writing straight into the UART ring. Anything else written
    // between two of those chunks lands INSIDE the RESULT's byte stream. The
    // receiver then reads the interleaved packet as RESULT payload, fails the
    // CRC, and the whole result is lost — while s_stats.results_sent still
    // counts it as sent. A silent data-loss defect on the path that exists
    // precisely to be reliable.
    //
    // *** THE DANGEROUS PACKET IS THE SMALL ONE — this is counter-intuitive. ***
    // After service() returns, either the result is complete or txRoom() is 0,
    // so a big packet is refused by the room check below. But the UART keeps
    // draining (~46 B/ms at 460800), so by the time the loop reaches another
    // producer a few dozen bytes are free. A 12-byte STATUS ("Ready") fits; a
    // 1689-byte live frame does not. Size is not the protection.
    //
    // Reachability is not theoretical: the clip-status messages at
    // guitar_rig_analyzer.ino:759-771 sit OUTSIDE the live-display gate, so
    // presentation_status() fires during a RESULT drain whenever the player is
    // still making noise.
    //
    // *** ENFORCED HERE, CENTRALLY, ON PURPOSE. ***
    // Every best-effort packet type — LIVE_FRAME, STATUS, ABORTED, VIEW,
    // ROUTER_STATUS, HELLO — reaches the wire through this one function.
    // Gating the individual producers instead would work until the next packet
    // type is added by someone who does not know to do it, and that packet
    // would rediscover this bug. An invariant that can be forgotten is not an
    // invariant.
    //
    // Dropping here is CORRECT, not a compromise: every caller is best-effort
    // by documented contract, and the drain is bounded (~217 ms worst case, and
    // the UART drains whether or not a Pi is listening, so it cannot stall).
    // The reliable path stays reliable; the lossy path stays lossy. That is the
    // architecture's stated ordering — presentation transport must be lossy
    // before measurement becomes lossy.
    // -------------------------------------------------------------------------
    if (s_result_len != 0) {
        s_stats.blocked_by_result++;
        return false;
    }

    const uint32_t total = (uint32_t)len + DS_FRAMING_BYTES;
    if (txRoom() < total) return false;

    // Small packets frame into a local buffer; the live frame is pre-framed by
    // its caller because its payload is already in a static buffer.
    uint8_t hdr[5];
    hdr[0] = DS_SYNC_WORD & 0xFF;
    hdr[1] = (DS_SYNC_WORD >> 8) & 0xFF;
    hdr[2] = packet_type;
    hdr[3] = len & 0xFF;
    hdr[4] = (len >> 8) & 0xFF;
    const uint16_t crc = crc16_block(payload, len);
    uint8_t tail[2] = { (uint8_t)(crc & 0xFF), (uint8_t)((crc >> 8) & 0xFF) };

    // Room was confirmed for the whole packet above, so these three writes
    // cannot block.
    DS_UART_PORT.write(hdr, 5);
    DS_UART_PORT.write(payload, len);
    DS_UART_PORT.write(tail, 2);
    return true;
}

// Wrap a best-effort send with call-duration instrumentation.
static bool timedBestEffort(uint8_t type, const uint8_t* payload, uint16_t len) {
    const uint32_t t0 = micros();
    const bool ok = trySendBestEffort(type, payload, len);
    const uint32_t dt = micros() - t0;

    s_stats.send_calls++;
    s_stats.send_us_last = dt;
    s_stats.send_us_total += dt;
    if (dt > s_stats.send_us_max) s_stats.send_us_max = dt;
    return ok;
}

// =============================================================================
// PRIVATE: decimation with coverage accounting
// =============================================================================
// One pass produces the transmitted value AND the per-bin coverage nibbles, so
// the value and the statement of how much to trust it cannot drift apart.
//
// Protocol v1 used a single arithmetic mean for all three arrays and discarded
// both the clamp state and the NaN coverage (audit L1/L2/L3). Those are not
// independent bugs: they are all "the Teensy knew something and did not say so."

// Peak-preserving decimation for the linear magnitude spectra. An arithmetic
// mean buries narrow peaks — exactly the features a spectrum display exists to
// show — so take the maximum instead. NaN inputs are ignored.
static void decimateMax(const float* src, float* dst) {
    for (uint16_t d = 0; d < DS_LIVE_BINS; d++) {
        float peak = NAN;
        for (uint16_t j = 0; j < DS_DECIM_RATIO; j++) {
            const float v = src[d * DS_DECIM_RATIO + j];
            if (isnan(v)) continue;
            if (isnan(peak) || v > peak) peak = v;
        }
        dst[d] = peak;
    }
}

// Mean-in-dB decimation for the TF curve, plus the coverage nibbles.
//   high nibble = number of source bins CLAMPED (saturation rails)
//   low  nibble = number of source bins VALID   (non-NaN)
// A bin whose valid count is 0 emits NaN so the receiver pen-lifts.
static void decimateTf(const AudioFrame* frame, float* dst, uint8_t* coverage) {
    for (uint16_t d = 0; d < DS_LIVE_BINS; d++) {
        float sum = 0.0f;
        uint8_t valid = 0;
        uint8_t clamped = 0;

        for (uint16_t j = 0; j < DS_DECIM_RATIO; j++) {
            const int bin = (int)(d * DS_DECIM_RATIO + j);
            const float v = frame->tf_db[bin];

            // Clamp state is counted over every source bin in the group,
            // independently of whether the value is NaN — a railed bin is a
            // fact about the bin, not about its arithmetic contribution.
            if (audioEngine_tfBinClamped(frame, bin)) clamped++;

            if (!isnan(v)) { sum += v; valid++; }
        }

        dst[d]      = (valid > 0) ? (sum / (float)valid) : NAN;
        coverage[d] = (uint8_t)((clamped << 4) | (valid & 0x0F));
    }
}

// =============================================================================
// SESSION IDENTITY
// =============================================================================
// nextSessionId()
//
// Requirement (TODO-56): a value that is CONSTANT for one Teensy boot/session
// and CHANGES across a reboot, so a Pi receiving repeated HELLOs can tell a
// routine re-announcement from a new Teensy session. Explicitly NOT security,
// NOT measurement identity.
//
// *** WHY A FLASH-BACKED COUNTER, AND NOT SOMETHING FREE ***
//
// Four platform facilities were checked against that requirement before this
// was written, and the reason for rejecting each is recorded so nobody
// "simplifies" this back into a broken one:
//
//   SNVS_LPGPR0..3   Always-on general-purpose registers. Survive a WARM reset
//                    while VDD_SNVS holds, so a counter here increments across
//                    a reset-button or software reset. But Teensy 4.1 has no
//                    coin cell fitted here, so a POWER CYCLE clears them — and
//                    then two consecutive cold boots both report the same
//                    value. That is exactly the case the Pi must not miss.
//   rtc_get()        Same power domain, same weakness: without a VBAT cell the
//                    RTC does not survive power loss.
//   ARM_DWT_CYCCNT / micros() at init
//                    Read at a fixed point in a fixed boot sequence, so these
//                    are very nearly deterministic. Using them would be the
//                    "weak random mechanism" this design was told to avoid;
//                    worse, it would LOOK random while colliding often.
//   HW_OCOTP_MAC0    The chip's unique serial. Constant across reboots by
//                    definition — it identifies the BOARD, not the session, so
//                    it cannot discriminate a reboot at all.
//
// A monotonic counter in the Teensy 4.1's flash-emulated EEPROM is the only
// candidate that satisfies the contract in EVERY reboot mode, including a cold
// power cycle. It is also deterministic, which is what makes runbook Phase 10
// step 10 a real test rather than an observation: the value is predictable and
// can be read back.
//
// Cost and placement: this is PERSISTENT STATE, WRITTEN EXACTLY ONCE PER _PI
// INITIALISATION — one 2-byte EEPROM write, never in the loop, never per
// measurement. dataSender_init() is called from presentation_init() at
// .ino:311, BEFORE audioCap_init() at :323, so no audio is running and no
// acquisition timing exists to perturb. It is the firmware's only flash write.
//
// Endurance is therefore a non-issue at this write rate and NO wear-levelling
// scheme is implemented or relied upon here. If this ever stops being a
// once-per-boot write — a re-key on reconnect, say, or an id bumped per
// session rather than per boot — endurance becomes a real design constraint
// and must be reconsidered before that change lands, not after.
//
// *** DOCUMENTED LIMITATIONS — read before relying on this for anything else ***
//
//   • 16-bit, so it wraps after 65535 boots. The receiver contract is
//     "changed => stale", not "ordered", so a wrap is harmless. Do not build
//     anything that treats the value as monotonic forever.
//   • NOT unique across devices. Two Teensys can both be at boot 42. Device
//     identity would be HW_OCOTP_MAC0 in a NEW field, not this one.
//   • Predictable by design. Never use it as a security nonce or a token.
//   • It counts boots of THIS build target only. data_sender.cpp compiles
//     solely for DISPLAY_TARGET_PI, so _NONE and _RA8875 boots do not
//     increment it. That is correct — they have no link and no session — but
//     it means the counter is not a boot count for the instrument as a whole.
//   • A first-ever boot on a blank EEPROM reads 0xFFFF and becomes 0. No
//     special case is needed: the value only has to CHANGE, and it does.
// -----------------------------------------------------------------------------
static uint16_t nextSessionId() {
    uint16_t stored = 0;
    EEPROM.get(EEPROM_ADDR_LINK_SESSION, stored);
    const uint16_t next = (uint16_t)(stored + 1);   // 0xFFFF -> 0 is fine
    EEPROM.put(EEPROM_ADDR_LINK_SESSION, next);
    return next;
}

// -----------------------------------------------------------------------------
// sendHello()
// Builds and emits one HELLO. Shared by init() and the periodic re-announce so
// the two can never describe the instrument differently — a re-announcement
// that disagreed with the original would be worse than no re-announcement.
//
// Best effort, like every other event packet: if the whole 47-byte frame does
// not fit, it is dropped and counted. It is NEVER partially written and never
// waits for room. Under sustained backpressure (T1 run 3) this is expected to
// drop repeatedly — hence the dedicated counter.
// -----------------------------------------------------------------------------
static void sendHello() {
    uint8_t p[40];
    memset(p, 0, sizeof(p));
    uint16_t u16;
    uint32_t u32;

    u16 = (uint16_t)PI_PROTOCOL_VERSION; memcpy(&p[0],  &u16, 2);
    u16 = (uint16_t)DS_LIVE_BINS;        memcpy(&p[2],  &u16, 2);
    u16 = (uint16_t)FFT_BINS;            memcpy(&p[4],  &u16, 2);
    u16 = (uint16_t)DS_DECIM_RATIO;      memcpy(&p[6],  &u16, 2);
    u32 = (uint32_t)DS_BAUD_RATE;        memcpy(&p[8],  &u32, 4);
    u32 = (uint32_t)SAMPLE_RATE;         memcpy(&p[12], &u32, 4);
    u16 = (uint16_t)INSIGHTS_MAX_COUNT;  memcpy(&p[16], &u16, 2);
    u16 = s_session_id;                  memcpy(&p[18], &u16, 2);

    // Capability bitmap: lets the Pi distinguish "feature off" from "feature not
    // compiled in", which v1's ROUTER_STATUS could not express (audit T4). A
    // receiver must not render a control for a capability that cannot respond.
    u32 = 0;
#if ENABLE_DUT_INJECTION
    u32 |= 0x01;
#endif
#if ENABLE_MONITOR_MODE
    u32 |= 0x02;
#endif
    // bits 2/3 (MODE_PRECISION / MODE_LF) stay clear: measurementEngine_arm()
    // still rejects both. Advertising them would be a lie the Pi would act on.
    memcpy(&p[20], &u32, 4);

    writeFixedString(&p[24], 16, FIRMWARE_VERSION);

    if (timedBestEffort(DS_PACKET_HELLO, p, sizeof(p))) s_stats.hello_sent++;
    else                                                s_stats.hello_dropped++;

    s_last_hello_ms = millis();
}

// -----------------------------------------------------------------------------
// sendState()
// One authoritative measurement-state snapshot (TODO-57). Layout and rationale
// are documented in data_sender.h.
//
// NO RESULT-PENDING GUARD HERE, DELIBERATELY. Transport atomicity is owned in
// one place — trySendBestEffort() (TODO-59) — and duplicating the check in
// every producer is what made that defect possible. A refusal during a drain
// is counted, and blocked_by_result explains it.
// -----------------------------------------------------------------------------
static void sendState() {
    // COHERENT PAIR. These two getters are read adjacently and nothing may run
    // between them. The engine also maintains the pairing itself — the reason
    // is set before entering ABORTED and cleared before leaving it — so an
    // impossible combination such as IDLE-with-a-CLIP-reason cannot be built.
    // See the STATE layout note in data_sender.h before changing this.
    const uint8_t state  = (uint8_t)measurementEngine_getState();
    const uint8_t reason = (uint8_t)measurementEngine_getAbortReason();

    // Timestamp, not a sequence number. See data_sender.h — this value wraps
    // roughly every 71.6 minutes and must never drive a newer-than comparison.
    const uint32_t blocks = audioCap_getBlockCounter();

    uint8_t p[8];
    p[0] = state;
    p[1] = reason;
    p[2] = 0;                       // reserved
    p[3] = 0;                       // reserved
    memcpy(&p[4], &blocks, 4);

    if (timedBestEffort(DS_PACKET_STATE, p, sizeof(p))) s_stats.state_sent++;
    else                                                s_stats.state_dropped++;

    s_last_state_ms = millis();
}

// =============================================================================
// PUBLIC API
// =============================================================================

bool dataSender_init() {
    DS_UART_PORT.begin(DS_BAUD_RATE);

    // Install the extended TX buffer BEFORE any write. This is what makes the
    // non-blocking policy possible at all — see the s_tx_buffer comment.
    DS_UART_PORT.addMemoryForWrite(s_tx_buffer, sizeof(s_tx_buffer));

    dataSender_resetStats();
    s_result_len = s_result_sent = 0;

    delay(10);   // let the UART settle before the first frame

    // Establish session identity BEFORE the first HELLO — the first
    // announcement must carry the same id as every re-announcement after it.
    s_session_id = nextSessionId();

    // First HELLO. It is no longer the only one: dataSender_service()
    // re-announces, so a Pi that is absent, late or unlucky here is not
    // permanently locked out of decoding results (TODO-56).
    sendHello();

    Serial.printf("[DataSender] Protocol v%d | %ld baud | %d live bins "
                  "(%d:1) | TX buffer %d B | firmware %s\n",
                  PI_PROTOCOL_VERSION, (long)DS_BAUD_RATE, DS_LIVE_BINS,
                  DS_DECIM_RATIO, DS_TX_BUFFER_BYTES, FIRMWARE_VERSION);
    // Printed so a bench operator can confirm the id the Pi reports is the id
    // this boot actually issued, without inferring it from Pi-side output.
    Serial.printf("[DataSender] Session id %u | HELLO re-announced every %d ms "
                  "| STATE every %d ms\n",
                  (unsigned)s_session_id, DS_HELLO_REANNOUNCE_MS,
                  DS_STATE_ANNOUNCE_MS);
    Serial.printf("[DataSender] Live frame %d B framed; RESULT up to %d B "
                  "(reliable, drained across loop iterations)\n",
                  DS_LIVE_PAYLOAD_BYTES + DS_FRAMING_BYTES,
                  DS_RESULT_STAGE_BYTES);
    return true;
}

// -----------------------------------------------------------------------------
// dataSender_service()
// -----------------------------------------------------------------------------
void dataSender_service() {
    s_stats.service_calls++;

    // -------------------------------------------------------------------------
    // STATE announcement (TODO-57) — attempted on cadence REGARDLESS of whether
    // a RESULT is draining. That is not an oversight: trySendBestEffort() owns
    // transport atomicity (TODO-59) and will refuse this packet if a result is
    // staged. Adding a second gate here would re-create the scattered-guard
    // pattern that produced TODO-59 in the first place.
    //
    // Subtraction is wrap-safe on uint32_t, so a millis() rollover at ~49.7
    // days does not stall announcements.
    // -------------------------------------------------------------------------
    if ((uint32_t)(millis() - s_last_state_ms) >= DS_STATE_ANNOUNCE_MS) {
        sendState();
    }

    // -------------------------------------------------------------------------
    // ROUTER_STATUS periodic repair (TODO-58). The two immediate emissions are
    // orchestrated from the .ino for responsiveness; THIS path is what makes
    // the packet obtainable at all. It must be independently sufficient: if
    // every on-change emission were lost, a Pi attaching at an arbitrary moment
    // still converges within one period.
    //
    // 1 Hz, not STATE's 500 ms. Route state is slowly-changing CONFIGURATION —
    // an operator selection and a set of build-time detector facts — so it
    // belongs in HELLO's cadence tier rather than the operational one.
    // -------------------------------------------------------------------------
    if ((uint32_t)(millis() - s_last_router_ms) >= DS_ROUTER_REPAIR_MS) {
        dataSender_sendRouterStatus();
    }

    if (s_result_len == 0) {
        s_stats.result_pending = false;
        s_stats.result_pending_bytes = 0;

        // ---------------------------------------------------------------
        // HELLO re-announcement (TODO-56).
        //
        // Reached only when NO RESULT is staged, which is the whole of the
        // gate: the reliable path is never made to compete with an
        // announcement. Deliberately NOT gated on measurement state — HELLO
        // describes the instrument and protocol session, not the measurement.
        // A Pi reconnecting during ARMED, CAPTURE, PROCESSING, RESULT,
        // EXPORTING or a sticky ABORTED must be able to obtain geometry and
        // reconstruct that state rather than sit blind until IDLE.
        //
        // sendHello() is best-effort and cannot block: under backpressure it
        // drops and counts. Subtraction is wrap-safe on uint32_t, so a
        // millis() rollover at ~49.7 days does not stall announcements.
        //
        // NOTE (TODO-59): this placement is no longer what makes the
        // announcement SAFE — the transport atomicity invariant inside
        // trySendBestEffort() is. It is kept here for two documented reasons,
        // not as a duplicate guard: it avoids building a 40-byte payload and
        // its CRC only to have them refused, and it keeps hello_dropped
        // meaning "backpressure" rather than accumulating a drop every second
        // of every RESULT drain, which is a structural condition and not a
        // link problem.
        // ---------------------------------------------------------------
        if ((uint32_t)(millis() - s_last_hello_ms) >= DS_HELLO_REANNOUNCE_MS) {
            sendHello();
        }
        return;
    }

    s_stats.result_pending = true;

    const uint32_t t0 = micros();
    uint32_t room = txRoom();

    while (room > 0 && s_result_sent < s_result_len) {
        uint32_t chunk = s_result_len - s_result_sent;
        if (chunk > room) chunk = room;

        // Room was just measured, so this write cannot block.
        DS_UART_PORT.write(&s_result_stage[s_result_sent], chunk);
        s_result_sent += chunk;
        room -= chunk;
    }

    const uint32_t dt = micros() - t0;
    s_stats.send_calls++;
    s_stats.send_us_last = dt;
    s_stats.send_us_total += dt;
    if (dt > s_stats.send_us_max) s_stats.send_us_max = dt;

    s_stats.result_pending_bytes = s_result_len - s_result_sent;

    if (s_result_sent >= s_result_len) {
        const uint32_t drain_ms = millis() - s_result_queued_ms;
        if (drain_ms > s_stats.result_drain_ms_max) {
            s_stats.result_drain_ms_max = drain_ms;
        }
        s_stats.results_sent++;
        s_result_len = s_result_sent = 0;
        s_stats.result_pending = false;
        s_stats.result_pending_bytes = 0;
    }
}

// -----------------------------------------------------------------------------
// dataSender_sendLiveFrame()  —  best effort, droppable, latest-wins
// -----------------------------------------------------------------------------
void dataSender_sendLiveFrame(const AudioFrame* frame) {
    if (frame == nullptr) return;

    const uint32_t t0 = micros();

    // Drop before doing the decimation work if there is no room for the packet.
    // Checking first is not just an optimisation: when the Pi is gone, this path
    // runs every block forever, and the decimation is the expensive part.
    const uint32_t total = (uint32_t)DS_LIVE_PAYLOAD_BYTES + DS_FRAMING_BYTES;
    if (txRoom() < total) {
        s_stats.live_dropped++;
        s_live_drop_streak++;
        if (s_live_drop_streak > s_stats.live_dropped_streak_max) {
            s_stats.live_dropped_streak_max = s_live_drop_streak;
        }
        const uint32_t dt = micros() - t0;
        s_stats.send_calls++;
        s_stats.send_us_last = dt;
        s_stats.send_us_total += dt;
        if (dt > s_stats.send_us_max) s_stats.send_us_max = dt;
        return;
    }

    uint8_t* p = s_live_payload;
    uint16_t pos = 0;

    p[pos++] = (uint8_t)measurementEngine_getState();

    uint8_t flags = 0;
    if (frame->source_clipping)        flags |= 0x01;
    if (frame->return_clipping)        flags |= 0x02;
    if (frame->tf_persistence_active)  flags |= 0x04;
    p[pos++] = flags;

    const uint16_t block_lo = (uint16_t)(frame->output_block_number & 0xFFFF);
    memcpy(&p[pos], &block_lo, 2);                 pos += 2;
    memcpy(&p[pos], &frame->peak_source_dbfs, 4);  pos += 4;
    memcpy(&p[pos], &frame->peak_return_dbfs, 4);  pos += 4;
    memcpy(&p[pos], &frame->tf_confidence, 4);     pos += 4;

    // Whole-curve clamp summary over all FFT_BINS source bins — a cheap figure
    // for the renderer and for logs, independent of the per-bin nibbles below.
    memcpy(&p[pos], &frame->tf_clamped_count, 2);  pos += 2;

    const uint16_t fblock = DS_LIVE_BINS * sizeof(float);

    decimateMax(frame->fft_source, (float*)&p[pos]);  pos += fblock;
    decimateMax(frame->fft_return, (float*)&p[pos]);  pos += fblock;

    // TF value and its coverage nibbles are produced together, so a receiver can
    // never be handed a number without the statement of how much of it is real.
    float*   tf_dst    = (float*)&p[pos];            pos += fblock;
    uint8_t* cov_dst   = &p[pos];                    pos += DS_LIVE_BINS;
    decimateTf(frame, tf_dst, cov_dst);

    const bool ok = trySendBestEffort(DS_PACKET_LIVE_FRAME, p, pos);

    const uint32_t dt = micros() - t0;
    s_stats.send_calls++;
    s_stats.send_us_last = dt;
    s_stats.send_us_total += dt;
    if (dt > s_stats.send_us_max) s_stats.send_us_max = dt;

    if (ok) {
        s_stats.live_sent++;
        s_live_drop_streak = 0;
    } else {
        // Room was checked above, so reaching here means the buffer drained
        // differently than measured. Counted the same way; still never blocks.
        s_stats.live_dropped++;
        s_live_drop_streak++;
        if (s_live_drop_streak > s_stats.live_dropped_streak_max) {
            s_stats.live_dropped_streak_max = s_live_drop_streak;
        }
    }
}

// -----------------------------------------------------------------------------
// dataSender_sendResult()  —  reliable, staged, latest-wins on supersession
// -----------------------------------------------------------------------------
void dataSender_sendResult(const MeasurementResult& result,
                           const InsightList& insights) {
    const uint32_t t0 = micros();

    if (s_result_len != 0) {
        // A previous result had not finished draining. Replace it: a stale
        // result is worth less than the current one, and interleaving two
        // packets would corrupt both.
        s_stats.results_superseded++;
        s_stats.result_bytes_abandoned += (s_result_len - s_result_sent);
    }

    // Build the payload directly inside the staging buffer, after the 5-byte
    // header, so the whole thing is framed in place with no second copy.
    uint8_t* payload = &s_result_stage[5];
    uint32_t pos = 0;

    // --- Verdicts the Teensy owns. v1 omitted the first four entirely. ---
    payload[pos++] = result.result_valid ? 1 : 0;              // audit R1
    payload[pos++] = (uint8_t)result.result_quality;

    uint8_t flags = 0;
    if (result.clip_detected)        flags |= 0x01;
    if (result.calibration_applied)  flags |= 0x02;
    if (result.generator_active)     flags |= 0x04;
    payload[pos++] = flags;

    payload[pos++] = (uint8_t)result.calibration_type;         // audit R3

    const CalibrationWarnings& w = result.calibration_warnings;
    uint8_t wbits = 0;
    if (w.calibration_missing)           wbits |= 0x01;
    if (w.line_in_level_mismatch)        wbits |= 0x02;
    if (w.partial_calibration_applied)   wbits |= 0x04;
    if (w.calibration_from_import)       wbits |= 0x08;
    if (w.hard_parameter_mismatch)       wbits |= 0x10;
    payload[pos++] = wbits;                                    // audit R3

    payload[pos++] = 0;                                        // reserved

    memcpy(&payload[pos], &result.n_averages_completed, 2);  pos += 2;
    memcpy(&payload[pos], &result.mean_coherence, 4);        pos += 4;
    memcpy(&payload[pos], &result.valid_bin_fraction, 4);    pos += 4;
    memcpy(&payload[pos], &result.timestamp_ms, 4);          pos += 4;

    payload[pos++] = (uint8_t)result.estimator;
    payload[pos++] = (uint8_t)result.stimulus;
    payload[pos++] = (uint8_t)result.fft_mode;
    payload[pos++] = (uint8_t)result.window_function;

    // --- Hardware and capture context (audit R6) ---
    memcpy(&payload[pos], &result.fft_size, 2);             pos += 2;
    memcpy(&payload[pos], &result.capture_start_block, 4);  pos += 4;
    memcpy(&payload[pos], &result.capture_end_block, 4);    pos += 4;
    payload[pos++] = result.source_node_ch;
    payload[pos++] = result.return_node_ch;
    payload[pos++] = result.line_in_level;
    payload[pos++] = 0;                                     // reserved

    memcpy(&payload[pos], &result.clip_source_count, 2);    pos += 2;
    memcpy(&payload[pos], &result.clip_return_count, 2);    pos += 2;

    // --- Provenance (audit R2/R5) ---
    writeFixedString(&payload[pos], 16, result.firmware_version);   pos += 16;
    writeFixedString(&payload[pos], 96, result.calibration_provenance);
    pos += 96;

    payload[pos++] = 0;   // reserved
    payload[pos++] = 0;

    // ---- LAYOUT SELF-CHECK ----------------------------------------------
    // pos must now equal the fixed-block size documented in data_sender.h. If a
    // future edit adds or removes a field without updating the layout comment,
    // every subsequent offset in the Pi's parser silently shifts and the symptom
    // is garbage floats, not an error. Cheap to check, expensive to debug.
    //
    // The static_assert pins the constant; the runtime check pins the code that
    // is supposed to fill it. Both are needed — they fail for different reasons.
    static_assert(DS_RESULT_FIXED_BYTES == 156,
                  "RESULT fixed-block size changed — update the layout comment "
                  "in data_sender.h and bump PI_PROTOCOL_VERSION");
    if (pos != DS_RESULT_FIXED_BYTES) {
        // Report once per occurrence and abandon the packet rather than sending
        // a result the Pi will misparse into plausible-looking wrong numbers.
        Serial.printf("[DataSender] FATAL LAYOUT DRIFT: RESULT fixed block filled "
                      "%lu bytes, header documents %d. Packet NOT sent — fix the "
                      "layout and bump PI_PROTOCOL_VERSION.\n",
                      (unsigned long)pos, DS_RESULT_FIXED_BYTES);
        s_result_len = s_result_sent = 0;
        return;
    }

    // --- Canonical 512-bin arrays ---
    const uint16_t spec = FFT_BINS * sizeof(float);
    memcpy(&payload[pos], result.tf_cal_mag_db,    spec);  pos += spec;
    memcpy(&payload[pos], result.tf_cal_phase_rad, spec);  pos += spec;
    memcpy(&payload[pos], result.group_delay_ms,   spec);  pos += spec;
    memcpy(&payload[pos], result.coherence,        spec);  pos += spec;

    // --- Insights ---
    uint8_t count = insights.count;
    if (count > INSIGHTS_MAX_COUNT) count = INSIGHTS_MAX_COUNT;
    payload[pos++] = count;

    for (uint8_t i = 0; i < count; i++) {
        const Insight& ins = insights.items[i];
        uint8_t* e = &payload[pos];
        memset(e, 0, DS_INSIGHT_ENTRY_BYTES);
        e[0] = (uint8_t)ins.mode;
        e[1] = (uint8_t)ins.severity;
        memcpy(&e[2], &ins.frequency_hz, 4);
        memcpy(&e[6], &ins.magnitude_db, 4);
        writeFixedString(&e[10], 64, ins.title);
        writeFixedString(&e[74], 64, ins.detail);
        pos += DS_INSIGHT_ENTRY_BYTES;
    }

    // Frame in place around the payload already sitting at offset 5.
    s_result_stage[0] = DS_SYNC_WORD & 0xFF;
    s_result_stage[1] = (DS_SYNC_WORD >> 8) & 0xFF;
    s_result_stage[2] = DS_PACKET_RESULT;
    s_result_stage[3] = (uint8_t)(pos & 0xFF);
    s_result_stage[4] = (uint8_t)((pos >> 8) & 0xFF);
    const uint16_t crc = crc16_block(payload, (size_t)pos);
    s_result_stage[5 + pos]     = crc & 0xFF;
    s_result_stage[5 + pos + 1] = (crc >> 8) & 0xFF;

    s_result_len       = pos + DS_FRAMING_BYTES;
    s_result_sent      = 0;
    s_result_queued_ms = millis();
    s_stats.results_queued++;
    s_stats.result_pending = true;
    s_stats.result_pending_bytes = s_result_len;

    const uint32_t dt = micros() - t0;
    s_stats.send_calls++;
    s_stats.send_us_last = dt;
    s_stats.send_us_total += dt;
    if (dt > s_stats.send_us_max) s_stats.send_us_max = dt;

    // Opportunistically push the first chunk now rather than waiting a loop.
    dataSender_service();
}

// -----------------------------------------------------------------------------
// Event packets — best effort. A dropped ABORTED costs the reason STRING only;
// the machine-readable fact is repaired within DS_STATE_ANNOUNCE_MS by the
// periodic STATE packet, which carries both measurement_state and abort_reason.
//
// CORRECTED 2026-09-26 (TODO-57). This comment used to read "measurement_state
// rides in every live frame, so the Pi still learns the fact", and TODO-34
// cited that as the mitigation for a dropped ABORTED. IT WAS FALSE:
// presentation_updateLive() is gated to IDLE|ARMED
// (guitar_rig_analyzer.ino:748-756), so during ABORTED no live frame is sent at
// all and a dropped ABORTED was simply never learned. The safety net is the
// STATE packet; it was never the live frame.
// -----------------------------------------------------------------------------
void dataSender_sendAborted(const char* reason) {
    if (reason == nullptr) return;
    uint16_t len = (uint16_t)strlen(reason);
    if (len > DS_MAX_STRING_PAYLOAD) len = DS_MAX_STRING_PAYLOAD;
    if (timedBestEffort(DS_PACKET_ABORTED, (const uint8_t*)reason, len))
         s_stats.events_sent++;
    else s_stats.events_dropped++;
}

void dataSender_sendStatus(const char* message) {
    if (message == nullptr) return;
    uint16_t len = (uint16_t)strlen(message);
    if (len > DS_MAX_STRING_PAYLOAD) len = DS_MAX_STRING_PAYLOAD;
    if (timedBestEffort(DS_PACKET_STATUS, (const uint8_t*)message, len))
         s_stats.events_sent++;
    else s_stats.events_dropped++;
}

// -----------------------------------------------------------------------------
// dataSender_sendView()
// Best effort. A dropped view packet is recoverable: the periodic STATE packet
// re-establishes the authoritative measurement state within
// DS_STATE_ANNOUNCE_MS, and a receiver reconciles its view from that.
//
// CORRECTED 2026-09-26 (TODO-57): this said "measurement_state rides in every
// live frame", which was false for the same reason as the ABORTED note above —
// live frames stop entirely outside IDLE|ARMED.
// -----------------------------------------------------------------------------
void dataSender_sendView(uint8_t view_id) {
    const uint8_t payload[1] = { view_id };
    if (timedBestEffort(DS_PACKET_VIEW, payload, 1)) s_stats.events_sent++;
    else                                             s_stats.events_dropped++;
}

// -----------------------------------------------------------------------------
// dataSender_sendRouterStatus()
// ONE builder, used by all three triggers (TODO-58): the two immediate
// emissions orchestrated from the .ino, and the periodic repair below. They
// must emit identical bytes — a repair packet that disagreed with the
// immediate one would be worse than no repair at all.
//
// Layout and the receiver invariant: see data_sender.h.
//
// No RESULT-pending guard here. TODO-59 owns transport atomicity centrally in
// trySendBestEffort(); adding a second gate per producer is what made that
// defect possible.
// -----------------------------------------------------------------------------
void dataSender_sendRouterStatus() {
    const RouterStatus& rs = signalRouter_getStatus();
    uint8_t desc_len = (uint8_t)strlen(rs.description);
    if (desc_len > DS_ROUTER_MAX_DESC) desc_len = DS_ROUTER_MAX_DESC;

    uint8_t payload[DS_ROUTER_FIXED_BYTES + DS_ROUTER_MAX_DESC];
    memset(payload, 0, sizeof(payload));

    // [1] Which detectors exist. A build fact, and the authoritative
    // qualification on byte [0].
    const uint8_t available =
        (uint8_t)((rs.detect_available.instrument_in ? 0x01 : 0)
                | (rs.detect_available.rig_send      ? 0x02 : 0)
                | (rs.detect_available.return_ts     ? 0x04 : 0)
                | (rs.detect_available.return_xlr    ? 0x08 : 0));

    // [0] Raw observations, MASKED BY AVAILABILITY. Every detect pin is
    // INPUT_PULLUP, so an unmasked bit from a jack with no detect conductor
    // would put a pullup artefact on the wire as a physical claim. Masking is
    // a wire-contract obligation discharged here, at the presentation
    // boundary — signal_router deliberately keeps the raw readings so bench
    // diagnostics still see real pin state.
    const uint8_t observed =
        (uint8_t)((rs.jacks.instrument_in ? 0x01 : 0)
                | (rs.jacks.rig_send      ? 0x02 : 0)
                | (rs.jacks.return_ts     ? 0x04 : 0)
                | (rs.jacks.return_xlr    ? 0x08 : 0));

    payload[0] = (uint8_t)(observed & available);
    payload[1] = available;

    // [2] ADR-004: operator-selected, and the ONLY authority on the selected
    // return. Never derived from presence, in either direction.
    payload[2] = (uint8_t)rs.return_source;

    // [3] Current injection state — a primitive fact, distinct from HELLO's
    // capability bit. HELLO answers "can this build inject?"; this answers
    // "is injection active right now?". Both are needed.
#if ENABLE_DUT_INJECTION
    payload[3] = rs.injection_active ? 1 : 0;
#else
    payload[3] = 0;
#endif

    // [4] Current monitor mode. 0 (SOURCE_RETURN) in this build, which is the
    // router's actual state and not a placeholder. TODO-60 covers the latent
    // build failure when ENABLE_MONITOR_MODE is 1; it is not repaired here.
    payload[4] = 0;

    payload[5] = 0;                    // reserved
    payload[6] = desc_len;
    memcpy(&payload[DS_ROUTER_FIXED_BYTES], rs.description, desc_len);

    if (timedBestEffort(DS_PACKET_ROUTER, payload,
                        (uint16_t)(DS_ROUTER_FIXED_BYTES + desc_len)))
         s_stats.router_sent++;
    else s_stats.router_dropped++;

    s_last_router_ms = millis();
}

// =============================================================================
// DIAGNOSTICS
// =============================================================================

const DataSenderStats& dataSender_getStats() { return s_stats; }

void dataSender_resetStats() {
    memset(&s_stats, 0, sizeof(s_stats));
    s_stats.tx_room_min = 0xFFFFFFFFu;
    s_live_drop_streak = 0;
}

void dataSender_printDiagnostics() {
    const DataSenderStats& s = s_stats;
    const uint32_t live_total = s.live_sent + s.live_dropped;
    const float drop_pct = live_total ? (100.0f * s.live_dropped / live_total) : 0.0f;
    const float mean_us  = s.send_calls ? ((float)s.send_us_total / s.send_calls) : 0.0f;

    Serial.println("[Link] --- Pi link transport (measured) ---");
    Serial.printf("[Link] Atomicity:   %lu best-effort packets refused while a "
                  "RESULT was draining (expected, not a fault)\n",
                  (unsigned long)s.blocked_by_result);
    Serial.printf("[Link] Router:      %lu sent, %lu dropped | repair every "
                  "%d ms + on change\n",
                  (unsigned long)s.router_sent, (unsigned long)s.router_dropped,
                  DS_ROUTER_REPAIR_MS);
    Serial.printf("[Link] State:       %lu sent, %lu dropped (drops include "
                  "atomicity refusals), every %d ms\n",
                  (unsigned long)s.state_sent, (unsigned long)s.state_dropped,
                  DS_STATE_ANNOUNCE_MS);
    Serial.printf("[Link] Session id:  %u (constant for this boot) | HELLO "
                  "%lu sent, %lu dropped, every %d ms\n",
                  (unsigned)s_session_id,
                  (unsigned long)s.hello_sent, (unsigned long)s.hello_dropped,
                  DS_HELLO_REANNOUNCE_MS);
    Serial.printf("[Link] Live frames:  %lu sent, %lu dropped (%.1f%%), "
                  "longest drop streak %lu\n",
                  (unsigned long)s.live_sent, (unsigned long)s.live_dropped,
                  drop_pct, (unsigned long)s.live_dropped_streak_max);
    Serial.printf("[Link] Results:      %lu queued, %lu delivered, %lu superseded "
                  "(%lu B abandoned), max drain %lu ms%s\n",
                  (unsigned long)s.results_queued, (unsigned long)s.results_sent,
                  (unsigned long)s.results_superseded,
                  (unsigned long)s.result_bytes_abandoned,
                  (unsigned long)s.result_drain_ms_max,
                  s.result_pending ? "  [one pending now]" : "");
    if (s.result_pending) {
        Serial.printf("[Link]               pending bytes: %lu\n",
                      (unsigned long)s.result_pending_bytes);
    }
    Serial.printf("[Link] Events:       %lu sent, %lu dropped\n",
                  (unsigned long)s.events_sent, (unsigned long)s.events_dropped);

    // THE T1 NUMBER. The audit predicts ~33.8 ms of blocking write time per live
    // frame from baud rate and packet size. With the non-blocking policy the
    // real figure should be MICROSECONDS, because a frame that does not fit is
    // dropped rather than waited on. A max approaching a millisecond means
    // something is blocking and the policy has been violated somewhere.
    Serial.printf("[Link] Call time:    max %lu us, mean %.1f us, last %lu us "
                  "(%lu calls)\n",
                  (unsigned long)s.send_us_max, mean_us,
                  (unsigned long)s.send_us_last, (unsigned long)s.send_calls);
    Serial.printf("[Link] TX room min:  %lu B of %d B buffer   "
                  "(0 = the Pi is not draining)\n",
                  (s.tx_room_min == 0xFFFFFFFFu) ? 0UL : (unsigned long)s.tx_room_min,
                  DS_TX_BUFFER_BYTES);
    Serial.printf("[Link] Frame size:   %d B framed, %d:1 decimation, "
                  "%d live bins, protocol v%d\n",
                  DS_LIVE_PAYLOAD_BYTES + DS_FRAMING_BYTES, DS_DECIM_RATIO,
                  DS_LIVE_BINS, PI_PROTOCOL_VERSION);
    Serial.println("[Link] Interpretation: a high drop count with a LOW max call "
                   "time is the policy working correctly —");
    Serial.println("[Link] the Pi is absent or slow and measurement timing is "
                   "unaffected. Compare against block timing above.");
}

#endif // DISPLAY_TARGET == DISPLAY_TARGET_PI
