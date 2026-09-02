// =============================================================================
// data_sender.cpp  —  Guitar Rig Analyzer  v0.6.1
// =============================================================================
// Binary UART data sender. See data_sender.h for protocol documentation.
// =============================================================================

#include "data_sender.h"
#include "measurement_engine.h"   // for measurementEngine_getState()
#include "signal_router.h"

// =============================================================================
// CRC-16/CCITT (same polynomial as export_engine, different from CRC-32)
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
    for (size_t i = 0; i < len; i++) {
        crc = crc16_update(crc, buf[i]);
    }
    return crc;
}

// =============================================================================
// PRIVATE: Packet framing helpers
// =============================================================================

// Write the 5-byte packet header: SYNC(2) + type(1) + payload_length(2)
static void writeHeader(uint8_t packet_type, uint16_t payload_length) {
    uint8_t hdr[5];
    hdr[0] = DS_SYNC_WORD & 0xFF;         // 0x55
    hdr[1] = (DS_SYNC_WORD >> 8) & 0xFF;  // 0xAA
    hdr[2] = packet_type;
    hdr[3] = payload_length & 0xFF;
    hdr[4] = (payload_length >> 8) & 0xFF;
    DS_UART_PORT.write(hdr, 5);
}

// Write the 2-byte CRC trailer
static void writeCRC(uint16_t crc) {
    uint8_t tail[2];
    tail[0] = crc & 0xFF;
    tail[1] = (crc >> 8) & 0xFF;
    DS_UART_PORT.write(tail, 2);
}

// Send a complete packet: header + payload + CRC
static void sendPacket(uint8_t packet_type, const uint8_t* payload, uint16_t len) {
    writeHeader(packet_type, len);
    DS_UART_PORT.write(payload, len);
    writeCRC(crc16_block(payload, len));
}

// =============================================================================
// PRIVATE: Bin decimation
// =============================================================================
// Decimates FFT_BINS (512) source bins into DS_LIVE_BINS output bins by
// simple block averaging. Each output bin is the mean of (FFT_BINS / DS_LIVE_BINS)
// consecutive source bins. NaN bins in the source are skipped.

static void decimateBins(const float* src, float* dst, uint16_t src_bins, uint16_t dst_bins) {
    const uint16_t ratio = src_bins / dst_bins;
    for (uint16_t d = 0; d < dst_bins; d++) {
        float sum = 0.0f;
        uint16_t count = 0;
        for (uint16_t j = 0; j < ratio; j++) {
            uint16_t idx = d * ratio + j;
            if (idx < src_bins && !isnan(src[idx])) {
                sum += src[idx];
                count++;
            }
        }
        dst[d] = (count > 0) ? (sum / count) : NAN;
    }
}

// =============================================================================
// PUBLIC API
// =============================================================================

// -----------------------------------------------------------------------------
// dataSender_init()
// -----------------------------------------------------------------------------
bool dataSender_init() {
    DS_UART_PORT.begin(DS_BAUD_RATE);

    // Wait for UART to be ready
    delay(10);

    // Send identification packet as a status message so the receiver
    // knows what to expect.
    char id_msg[128];
    snprintf(id_msg, sizeof(id_msg),
             "GRA v%s | protocol=1 | live_bins=%d | baud=%ld | full_bins=%d",
             FIRMWARE_VERSION, DS_LIVE_BINS, (long)DS_BAUD_RATE, FFT_BINS);

    dataSender_sendStatus(id_msg);

    Serial.printf("[DataSender] Initialised: %ld baud, %d live bins, UART %s\n",
                  (long)DS_BAUD_RATE, DS_LIVE_BINS, "Serial1");
    return true;
}

// -----------------------------------------------------------------------------
// dataSender_sendLiveFrame(frame)
// -----------------------------------------------------------------------------
// Live frame payload layout (all little-endian):
//   [0]       uint8   measurement_state
//   [1]       uint8   flags (bit 0: source_clip, bit 1: return_clip,
//                             bit 2: tf_persistence, bit 3..7: reserved)
//   [2-3]     uint16  output_block_number (lower 16 bits)
//   [4-7]     float   peak_source_dbfs
//   [8-11]    float   peak_return_dbfs
//   [12-15]   float   tf_confidence
//   [16..X]   float[DS_LIVE_BINS]   fft_source (decimated)
//   [X..Y]    float[DS_LIVE_BINS]   fft_return (decimated)
//   [Y..Z]    float[DS_LIVE_BINS]   tf_db      (decimated)
// Total: 16 + DS_LIVE_BINS * 3 * 4

void dataSender_sendLiveFrame(const AudioFrame* frame) {
    const uint16_t float_block_size = DS_LIVE_BINS * sizeof(float);
    const uint16_t payload_size = 16 + float_block_size * 3;

    // Use a stack buffer for the payload. At 128 bins this is 1552 bytes.
    // At 256 bins this is 3088 bytes. Both fit comfortably in the Teensy's
    // 1 MB RAM, but not in the 8 KB default stack on some platforms.
    // Teensy 4.1 has ample stack space.
    uint8_t payload[16 + 512 * 3 * sizeof(float)]; // max possible size
    uint16_t pos = 0;

    // State
    payload[pos++] = (uint8_t)measurementEngine_getState();

    // Flags
    uint8_t flags = 0;
    if (frame->source_clipping)     flags |= 0x01;
    if (frame->return_clipping)     flags |= 0x02;
    if (frame->tf_persistence_active) flags |= 0x04;
    payload[pos++] = flags;

    // Block number (lower 16 bits)
    uint16_t block_lo = (uint16_t)(frame->output_block_number & 0xFFFF);
    memcpy(&payload[pos], &block_lo, 2); pos += 2;

    // Peak levels
    memcpy(&payload[pos], &frame->peak_source_dbfs, 4); pos += 4;
    memcpy(&payload[pos], &frame->peak_return_dbfs, 4); pos += 4;

    // TF confidence
    memcpy(&payload[pos], &frame->tf_confidence, 4); pos += 4;

    // Decimated spectra
    float dec_buf[512]; // reusable decimation buffer

    decimateBins(frame->fft_source, dec_buf, FFT_BINS, DS_LIVE_BINS);
    memcpy(&payload[pos], dec_buf, float_block_size); pos += float_block_size;

    decimateBins(frame->fft_return, dec_buf, FFT_BINS, DS_LIVE_BINS);
    memcpy(&payload[pos], dec_buf, float_block_size); pos += float_block_size;

    decimateBins(frame->tf_db, dec_buf, FFT_BINS, DS_LIVE_BINS);
    memcpy(&payload[pos], dec_buf, float_block_size); pos += float_block_size;

    sendPacket(DS_PACKET_LIVE_FRAME, payload, pos);
}

// -----------------------------------------------------------------------------
// dataSender_sendResult(result, insights)
// -----------------------------------------------------------------------------
// Result payload is large — sent at full 512-bin resolution.
// Layout:
//   [0]       uint8   result_quality
//   [1]       uint8   flags (bit 0: clip_detected, bit 1: cal_applied,
//                             bit 2: generator_active)
//   [2-3]     uint16  n_averages_completed
//   [4-7]     float   mean_coherence
//   [8-11]    float   valid_bin_fraction
//   [12-15]   uint32  timestamp_ms
//   [16-19]   uint8[4] estimator, stimulus, fft_mode, window_function
//   [20-2067] float[512]  tf_cal_mag_db
//   [2068-4115] float[512] tf_cal_phase_rad
//   [4116-6163] float[512] group_delay_ms
//   [6164-8211] float[512] coherence
//   [8212-8215] uint16 clip_source_count, uint16 clip_return_count
//   [8216]      uint8  insight_count
//   [8217..]    insight entries (variable)
//
// Each insight entry:
//   [0]       uint8   mode
//   [1]       uint8   severity
//   [2-5]     float   frequency_hz
//   [6-9]     float   magnitude_db
//   [10-73]   char[64] title (null-terminated, padded)
//   [74-137]  char[64] detail (null-terminated, padded)
//   = 138 bytes per insight

void dataSender_sendResult(const MeasurementResult& result,
                           const InsightList& insights) {
    const uint16_t spec_block = FFT_BINS * sizeof(float);  // 2048
    const uint16_t header_size = 20;
    const uint16_t insight_entry_size = 138;
    const uint16_t payload_size = header_size
                                + spec_block * 4        // 4 spectra × 2048
                                + 4                     // clip counts
                                + 1                     // insight_count
                                + insights.count * insight_entry_size;

    // This is a large payload (~8–10 KB). We stream it in sections rather
    // than building the entire buffer in RAM.

    // Start the packet manually — write header, accumulate CRC as we go.
    writeHeader(DS_PACKET_RESULT, payload_size);

    uint16_t crc = 0xFFFF;

    // Helper: write a block and update CRC
    auto writeAndCRC = [&](const uint8_t* data, uint16_t len) {
        DS_UART_PORT.write(data, len);
        for (uint16_t i = 0; i < len; i++) {
            crc = crc16_update(crc, data[i]);
        }
    };

    // Header fields
    uint8_t hdr[20];
    hdr[0] = (uint8_t)result.result_quality;
    hdr[1] = (result.clip_detected ? 0x01 : 0)
           | (result.calibration_applied ? 0x02 : 0)
           | (result.generator_active ? 0x04 : 0);
    memcpy(&hdr[2], &result.n_averages_completed, 2);
    memcpy(&hdr[4], &result.mean_coherence, 4);
    memcpy(&hdr[8], &result.valid_bin_fraction, 4);
    memcpy(&hdr[12], &result.timestamp_ms, 4);
    hdr[16] = (uint8_t)result.estimator;
    hdr[17] = (uint8_t)result.stimulus;
    hdr[18] = (uint8_t)result.fft_mode;
    hdr[19] = (uint8_t)result.window_function;
    writeAndCRC(hdr, 20);

    // Four full-resolution spectral arrays
    writeAndCRC((const uint8_t*)result.tf_cal_mag_db,    spec_block);
    writeAndCRC((const uint8_t*)result.tf_cal_phase_rad, spec_block);
    writeAndCRC((const uint8_t*)result.group_delay_ms,   spec_block);
    writeAndCRC((const uint8_t*)result.coherence,        spec_block);

    // Clip counts
    uint8_t clips[4];
    memcpy(&clips[0], &result.clip_source_count, 2);
    memcpy(&clips[2], &result.clip_return_count, 2);
    writeAndCRC(clips, 4);

    // Insights
    uint8_t ic = insights.count;
    writeAndCRC(&ic, 1);

    for (uint8_t i = 0; i < insights.count; i++) {
        const Insight& ins = insights.items[i];
        uint8_t entry[138];
        memset(entry, 0, sizeof(entry));
        entry[0] = (uint8_t)ins.mode;
        entry[1] = (uint8_t)ins.severity;
        memcpy(&entry[2], &ins.frequency_hz, 4);
        memcpy(&entry[6], &ins.magnitude_db, 4);
        strncpy((char*)&entry[10], ins.title, 63);
        strncpy((char*)&entry[74], ins.detail, 63);
        writeAndCRC(entry, insight_entry_size);
    }

    // CRC trailer
    writeCRC(crc);
}

// -----------------------------------------------------------------------------
// dataSender_sendAborted(reason)
// -----------------------------------------------------------------------------
void dataSender_sendAborted(const char* reason) {
    uint16_t len = strlen(reason);
    if (len > 200) len = 200;
    sendPacket(DS_PACKET_ABORTED, (const uint8_t*)reason, len);
}

// -----------------------------------------------------------------------------
// dataSender_sendStatus(message)
// -----------------------------------------------------------------------------
void dataSender_sendStatus(const char* message) {
    uint16_t len = strlen(message);
    if (len > 200) len = 200;
    sendPacket(DS_PACKET_STATUS, (const uint8_t*)message, len);
}

// -----------------------------------------------------------------------------
// dataSender_sendRouterStatus()
// -----------------------------------------------------------------------------
// Router status payload:
//   [0]     uint8   jack_states (packed: bit 0=instrument, 1=send, 2=ts, 3=xlr)
//   [1]     uint8   return_source
//   [2]     uint8   injection_active
//   [3]     uint8   monitor_mode
//   [4]     uint8   route_valid
//   [5]     uint8   can_inject
//   [6]     uint8   description_length
//   [7..N]  char[]  description string

void dataSender_sendRouterStatus() {
    const RouterStatus& rs = signalRouter_getStatus();
    uint8_t desc_len = strlen(rs.description);
    if (desc_len > 100) desc_len = 100;
    uint16_t payload_len = 7 + desc_len;

    uint8_t payload[128];
    uint8_t jacks = 0;
    if (rs.jacks.instrument_in) jacks |= 0x01;
    if (rs.jacks.rig_send)      jacks |= 0x02;
    if (rs.jacks.return_ts)     jacks |= 0x04;
    if (rs.jacks.return_xlr)    jacks |= 0x08;

    payload[0] = jacks;
    payload[1] = (uint8_t)rs.return_source;
    payload[2] = rs.injection_active ? 1 : 0;
    #if ENABLE_MONITOR_MODE
payload[3] = (uint8_t)rs.monitor_mode;
#else
payload[3] = 0;
#endif
    payload[4] = rs.route_valid ? 1 : 0;
    payload[5] = rs.can_inject ? 1 : 0;
    payload[6] = desc_len;
    memcpy(&payload[7], rs.description, desc_len);

    sendPacket(DS_PACKET_ROUTER, payload, payload_len);
}
