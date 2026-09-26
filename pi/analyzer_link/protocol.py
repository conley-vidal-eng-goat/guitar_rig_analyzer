"""Protocol v2 constants, enums and link geometry.

*** SOURCE OF TRUTH ***
The firmware headers are authoritative. Every constant and every enum member
below is a MIRROR of a value defined in the Teensy tree:

    data_sender.h      framing, packet types, sizes, baud, live bins
    config.h           PI_PROTOCOL_VERSION, FFT_SIZE, SAMPLE_RATE
    insights_engine.h  INSIGHTS_MAX_COUNT, InsightMode, InsightSeverity
    measurement_core.h ResultQuality, CalibrationType, FftMode, TfEstimator,
                       StimulusType, WindowFunction
    measurement_engine.h  MeasurementState
    signal_router.h    ReturnSource, MonitorMode

``tests/test_firmware_header_sync.py`` parses those headers and fails if any
value here has drifted. That is the Pi-side half of the protocol audit's
acceptance Test C — "layout drift cannot be silent". Do not edit a constant
here to make a test pass; fix whichever side is actually wrong.

ADR-001 boundary note: nothing in this module, or anywhere under
``analyzer_link``, may compute a measurement value, a validity verdict, a
quality grade or a confidence figure. Those arrive as Teensy-authored fields
and are carried through unchanged.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass

# =============================================================================
# FRAMING  (data_sender.h)
# =============================================================================
# Wire layout:
#   [0-1]      uint16  SYNC_WORD = 0xAA55, little-endian -> bytes 55 AA
#   [2]        uint8   packet_type
#   [3-4]      uint16  payload_length  (little-endian; excludes header and CRC)
#   [5..N]     payload
#   [N+1..N+2] uint16  CRC-16/CCITT over payload only (little-endian)

SYNC_WORD = 0xAA55
SYNC_BYTES = b"\x55\xaa"

HEADER_BYTES = 5
CRC_BYTES = 2
FRAMING_BYTES = HEADER_BYTES + CRC_BYTES      # DS_FRAMING_BYTES

PROTOCOL_VERSION = 2                          # PI_PROTOCOL_VERSION
BAUD_RATE = 460800                            # DS_BAUD_RATE
MAX_STRING_PAYLOAD = 200                      # DS_MAX_STRING_PAYLOAD

# HELLO is re-announced on this period (DS_HELLO_REANNOUNCE_MS). A receiver
# that has not seen a HELLO yet needs only to wait this long, not for a Teensy
# reboot. Treat it as the expected announcement cadence, NOT as a timeout to
# enforce: announcements are best-effort and are dropped under backpressure by
# design, so a missed one is normal and means nothing on its own.
HELLO_REANNOUNCE_MS = 1000

# =============================================================================
# GEOMETRY DEFAULTS  —  DEFAULTS ONLY. Read the real values from HELLO.
# =============================================================================
# TODO-36: "Read live_bins and decim_ratio from the HELLO packet rather than
# hardcoding them. Cadence, bin count, TX buffering, chunking and baud are
# explicitly NOT frozen — Phase 10's T1 measurement may change any of them."
# These exist so tests and offline tooling have something to build vectors
# from; a live receiver must take its geometry from HELLO.

DEFAULT_LIVE_BINS = 128                       # DS_LIVE_BINS
DEFAULT_FFT_SIZE = 1024                       # FFT_SIZE
DEFAULT_FFT_BINS = DEFAULT_FFT_SIZE // 2      # FFT_BINS  (the canonical grid)
DEFAULT_SAMPLE_RATE = 44100                   # SAMPLE_RATE
DEFAULT_INSIGHTS_MAX = 12                     # INSIGHTS_MAX_COUNT

# =============================================================================
# PAYLOAD SIZES  (data_sender.h "DERIVED SIZES")
# =============================================================================

LIVE_HEADER_BYTES = 18          # fixed block before the arrays
LIVE_BYTES_PER_BIN = 3 * 4 + 1  # 3 floats + 1 packed coverage byte

RESULT_FIXED_BYTES = 156        # DS_RESULT_FIXED_BYTES
RESULT_ARRAYS = 4               # tf_cal_mag_db, tf_cal_phase_rad,
                                # group_delay_ms, coherence
INSIGHT_ENTRY_BYTES = 138       # DS_INSIGHT_ENTRY_BYTES

HELLO_PAYLOAD_BYTES = 40
VIEW_PAYLOAD_BYTES = 1
ROUTER_FIXED_BYTES = 7
ROUTER_MAX_DESC = 100


def live_payload_bytes(live_bins: int) -> int:
    """DS_LIVE_PAYLOAD_BYTES for a given bin count."""
    return LIVE_HEADER_BYTES + live_bins * LIVE_BYTES_PER_BIN


def result_payload_bytes(fft_bins: int, insight_count: int) -> int:
    """Exact RESULT payload length for a given geometry and insight count."""
    return (RESULT_FIXED_BYTES
            + fft_bins * RESULT_ARRAYS * 4
            + 1
            + insight_count * INSIGHT_ENTRY_BYTES)


def max_payload_bytes(fft_bins: int = DEFAULT_FFT_BINS,
                      insights_max: int = DEFAULT_INSIGHTS_MAX) -> int:
    """Largest payload any v2 packet can legitimately carry.

    The scanner uses this as a hard bound: a declared payload_length above it
    is a false sync or a corrupted header, never a packet worth buffering.
    Unbounded trust in a length field is how a receiver is made to allocate
    64 KB from two noise bytes.
    """
    return result_payload_bytes(fft_bins, insights_max)


# =============================================================================
# PACKET TYPES  (data_sender.h)
# =============================================================================

class PacketType(enum.IntEnum):
    LIVE_FRAME = 0x01
    RESULT = 0x02
    STATUS = 0x03
    ABORTED = 0x04
    ROUTER_STATUS = 0x05
    HELLO = 0x06
    VIEW = 0x07


VIEW_LIVE = 0x00                              # DS_VIEW_LIVE


# =============================================================================
# TEENSY-AUTHORED ENUMS  —  mirrored, never reinterpreted
# =============================================================================

class MeasurementState(enum.IntEnum):
    IDLE = 0
    ARMED = 1
    CAPTURE = 2
    PROCESSING = 3
    RESULT = 4
    EXPORTING = 5
    ABORTED = 6
    SELF_TEST = 7


class ResultQuality(enum.IntEnum):
    INVALID = 0
    POOR = 1
    MARGINAL = 2
    GOOD = 3
    EXCELLENT = 4


class InsightMode(enum.IntEnum):
    """MEASUREMENT and ADVISORY are semantically different and MUST remain
    visually distinguishable in any renderer (ADR-001, TODO-36).

    MEASUREMENT is a direct measured fact. ADVISORY is interpretation. A UI
    that styles them identically has erased the distinction the Teensy went to
    the trouble of authoring.
    """
    MEASUREMENT = 0
    ADVISORY = 1


class InsightSeverity(enum.IntEnum):
    INFO = 0
    WARNING = 1
    ALERT = 2


class CalibrationType(enum.IntEnum):
    INTERNAL_LOOPBACK = 0
    EXTERNAL_LOOPBACK = 1
    MICROPHONE = 2
    USER_IMPORTED = 3


class FftMode(enum.IntEnum):
    MODE_LIVE = 0
    MODE_PRECISION = 1
    MODE_LF = 2


class TfEstimator(enum.IntEnum):
    H1 = 0
    H2 = 1
    HV = 2


class StimulusType(enum.IntEnum):
    EXTERNAL = 0
    INTERNAL_SINE = 1
    INTERNAL_PINK = 2
    INTERNAL_WHITE = 3
    INTERNAL_LOG_SWEEP = 4


class WindowFunction(enum.IntEnum):
    HANN = 0
    BLACKMAN = 1
    FLAT_TOP = 2


class ReturnSource(enum.IntEnum):
    NONE = 0
    TS = 1
    XLR = 2


class MonitorMode(enum.IntEnum):
    SOURCE_RETURN = 0
    RETURN_ONLY = 1
    BLEND = 2


# =============================================================================
# BIT FIELDS
# =============================================================================

class LiveFlags(enum.IntFlag):
    SOURCE_CLIP = 0x01
    RETURN_CLIP = 0x02
    TF_PERSISTENCE_ACTIVE = 0x04


class ResultFlags(enum.IntFlag):
    CLIP_DETECTED = 0x01
    CALIBRATION_APPLIED = 0x02
    GENERATOR_ACTIVE = 0x04


class CalibrationWarning(enum.IntFlag):
    CALIBRATION_MISSING = 0x01
    LINE_IN_LEVEL_MISMATCH = 0x02
    PARTIAL_CALIBRATION_APPLIED = 0x04
    CALIBRATION_FROM_IMPORT = 0x08
    HARD_PARAMETER_MISMATCH = 0x10


class Capability(enum.IntFlag):
    """HELLO capability bitmap.

    Audit finding T4: this is what lets the Pi tell "monitor mode is off" from
    "monitor mode does not exist in this build", so it does not render a
    control that cannot respond.
    """
    DUT_INJECTION = 0x01
    MONITOR_MODE = 0x02
    MODE_PRECISION = 0x04
    MODE_LF = 0x08


class JackPresence(enum.IntFlag):
    INSTRUMENT_IN = 0x01
    RIG_SEND = 0x02
    RETURN_TS = 0x04
    RETURN_XLR = 0x08


# =============================================================================
# LINK GEOMETRY
# =============================================================================

@dataclass(frozen=True)
class Geometry:
    """Packet geometry, as reported by the Teensy in HELLO.

    A RESULT packet's four arrays are ``float[fft_bins]`` each, and fft_bins
    is NOT derivable from the packet itself — the insight count that would let
    you solve for it sits AFTER the arrays. So RESULT cannot be decoded before
    a HELLO has been seen. That is a property of the wire format, not a
    limitation of this parser.

    Note ``fft_bins`` (the canonical 512-bin result grid) is a different thing
    from a RESULT's ``fft_size`` field (the FFT length actually used, which
    MODE_PRECISION raises). Do not substitute one for the other.
    """
    live_bins: int = DEFAULT_LIVE_BINS
    fft_bins: int = DEFAULT_FFT_BINS
    decim_ratio: int = DEFAULT_FFT_BINS // DEFAULT_LIVE_BINS
    insights_max: int = DEFAULT_INSIGHTS_MAX
    sample_rate: int = DEFAULT_SAMPLE_RATE

    def bin_frequency_hz(self, transmitted_bin: int, fft_size: int) -> float:
        """Centre frequency of a transmitted live bin.

        Presentation arithmetic over Teensy-authored geometry — an axis label,
        not a measurement. ``fft_size`` comes from HELLO or from the RESULT.
        """
        first_source_bin = transmitted_bin * self.decim_ratio
        centre = first_source_bin + (self.decim_ratio - 1) / 2.0
        return centre * self.sample_rate / fft_size
