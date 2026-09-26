"""Synthetic protocol v2 packet builder — the test stimulus.

*** WHAT THESE VECTORS DO AND DO NOT PROVE ***

These bytes are built from this repository's reading of ``data_sender.h``.
A passing test proves the parser is self-consistent with that reading and that
its CRC, framing, resync and tolerance behaviour are correct.

It does NOT prove the parser agrees with the FIRMWARE. Encoder and decoder
here share one author and one interpretation, so a misreading of the header
would be reproduced identically on both sides and every test would still pass.

Firmware agreement is established by capturing a real Teensy byte stream and
replaying it through the same parser — runbook Phase 10 step 4 onward, which
needs hardware. Until that capture exists, no Phase 10 step may be recorded as
passed on the strength of this file.
"""

from __future__ import annotations

import math
import struct

from analyzer_link import protocol
from analyzer_link.crc import crc16


def frame(packet_type: int, payload: bytes) -> bytes:
    """Wrap a payload in protocol v2 framing."""
    header = struct.pack("<HBH", protocol.SYNC_WORD, packet_type, len(payload))
    return header + payload + struct.pack("<H", crc16(payload))


def hello_payload(protocol_version: int = protocol.PROTOCOL_VERSION,
                  live_bins: int = protocol.DEFAULT_LIVE_BINS,
                  fft_bins: int = protocol.DEFAULT_FFT_BINS,
                  baud: int = protocol.BAUD_RATE,
                  sample_rate: int = protocol.DEFAULT_SAMPLE_RATE,
                  insights_max: int = protocol.DEFAULT_INSIGHTS_MAX,
                  session_id: int = 1,
                  capabilities: int = 0,
                  firmware: str = "0.6.0") -> bytes:
    decim = fft_bins // live_bins if live_bins else 0
    p = bytearray(protocol.HELLO_PAYLOAD_BYTES)
    struct.pack_into("<HHHHIIHHI", p, 0,
                     protocol_version, live_bins, fft_bins, decim,
                     baud, sample_rate, insights_max, session_id, capabilities)
    p[24:24 + len(firmware.encode())] = firmware.encode()
    return bytes(p)


def hello(**kwargs) -> bytes:
    return frame(protocol.PacketType.HELLO, hello_payload(**kwargs))


def live_payload(geometry: protocol.Geometry,
                 state: int = int(protocol.MeasurementState.IDLE),
                 flags: int = 0,
                 block: int = 0,
                 peak_source: float = -12.0,
                 peak_return: float = -18.0,
                 confidence: float = 0.42,
                 clamped_count: int = 0,
                 coverage: list[int] | None = None,
                 tf_db: list[float] | None = None) -> bytes:
    n = geometry.live_bins
    ratio = geometry.decim_ratio

    if coverage is None:
        coverage = [(0 << 4) | ratio] * n            # all clean, full coverage
    if tf_db is None:
        tf_db = [-3.0 + 0.01 * i for i in range(n)]

    src = [0.5 / (i + 1) for i in range(n)]
    ret = [0.4 / (i + 1) for i in range(n)]

    p = bytearray()
    p += struct.pack("<BBHfffH", state, flags, block & 0xFFFF,
                     peak_source, peak_return, confidence, clamped_count)
    p += struct.pack(f"<{n}f", *src)
    p += struct.pack(f"<{n}f", *ret)
    p += struct.pack(f"<{n}f", *tf_db)
    p += bytes(coverage)
    return bytes(p)


def live_frame(geometry: protocol.Geometry, **kwargs) -> bytes:
    return frame(protocol.PacketType.LIVE_FRAME,
                 live_payload(geometry, **kwargs))


def insight_entry(mode: int, severity: int, freq: float, mag: float,
                  title: str, detail: str) -> bytes:
    e = bytearray(protocol.INSIGHT_ENTRY_BYTES)
    struct.pack_into("<BBff", e, 0, mode, severity, freq, mag)
    e[10:10 + len(title.encode())] = title.encode()
    e[74:74 + len(detail.encode())] = detail.encode()
    return bytes(e)


def result_payload(geometry: protocol.Geometry,
                   result_valid: bool = True,
                   quality: int = int(protocol.ResultQuality.GOOD),
                   flags: int = 0,
                   calibration_type: int = 1,
                   calibration_warnings: int = 0,
                   n_averages: int = 8,
                   mean_coherence: float = 0.91,
                   valid_bin_fraction: float = 0.87,
                   timestamp_ms: int = 123456,
                   estimator: int = 0,
                   stimulus: int = 0,
                   fft_mode: int = 0,
                   window: int = 0,
                   fft_size: int = protocol.DEFAULT_FFT_SIZE,
                   capture_start: int = 1000,
                   capture_end: int = 2000,
                   source_ch: int = 0,
                   return_ch: int = 1,
                   line_in_level: int = 5,
                   clip_source: int = 0,
                   clip_return: int = 0,
                   firmware: str = "0.6.0",
                   provenance: str = "external loopback 2026-09-26",
                   insights: list[bytes] | None = None) -> bytes:
    n = geometry.fft_bins
    insights = insights or []

    p = bytearray(protocol.RESULT_FIXED_BYTES)
    struct.pack_into("<BBBBBBHffIBBBBHIIBBBBHH", p, 0,
                     1 if result_valid else 0, quality, flags,
                     calibration_type, calibration_warnings, 0,
                     n_averages, mean_coherence, valid_bin_fraction,
                     timestamp_ms, estimator, stimulus, fft_mode, window,
                     fft_size, capture_start, capture_end,
                     source_ch, return_ch, line_in_level, 0,
                     clip_source, clip_return)
    p[42:42 + len(firmware.encode())] = firmware.encode()
    p[58:58 + len(provenance.encode())] = provenance.encode()

    # tf_cal_mag_db carries a NaN at bin 3 so pen-lift survives a round trip.
    mag = [-6.0 + 0.001 * i for i in range(n)]
    mag[3] = math.nan
    p += struct.pack(f"<{n}f", *mag)
    p += struct.pack(f"<{n}f", *[0.1 * i for i in range(n)])
    p += struct.pack(f"<{n}f", *[2.5] * n)
    p += struct.pack(f"<{n}f", *[0.9] * n)

    p += bytes([len(insights)])
    for entry in insights:
        p += entry
    return bytes(p)


def result(geometry: protocol.Geometry, **kwargs) -> bytes:
    return frame(protocol.PacketType.RESULT, result_payload(geometry, **kwargs))


def status(message: str) -> bytes:
    return frame(protocol.PacketType.STATUS, message.encode())


def aborted(reason: str) -> bytes:
    return frame(protocol.PacketType.ABORTED, reason.encode())


def router_payload(presence: int = 0x00, available: int = 0x00,
                   return_source: int = 1, injection: int = 0,
                   monitor: int = 0,
                   description: str = "TS return, no injection") -> bytes:
    """Corrected TODO-58 layout. Defaults mirror the current hardware: no
    detector is available, so no presence bit may be set."""
    desc = description.encode()[:protocol.ROUTER_MAX_DESC]
    return (bytes([presence, available, return_source, injection, monitor,
                   0, len(desc)]) + desc)


def router_status(**kwargs) -> bytes:
    return frame(protocol.PacketType.ROUTER_STATUS, router_payload(**kwargs))


def view(view_id: int = protocol.VIEW_LIVE) -> bytes:
    return frame(protocol.PacketType.VIEW, bytes([view_id]))


def state_payload(measurement_state: int = 0,
                  abort_reason: int = 0,
                  audio_block_counter: int = 123456) -> bytes:
    return struct.pack("<BBHI", measurement_state, abort_reason, 0,
                       audio_block_counter)


def state(**kwargs) -> bytes:
    return frame(protocol.PacketType.STATE, state_payload(**kwargs))


def unknown(packet_type: int = 0xFE, payload: bytes = b"future") -> bytes:
    """A well-formed packet of a type this receiver has never heard of.

    Runbook Phase 10 step 9 uses exactly this: type 0xFE with a valid length
    and CRC.
    """
    return frame(packet_type, payload)
