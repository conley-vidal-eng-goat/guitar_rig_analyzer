"""Packet decoders — verified frames in, typed Teensy-authored records out.

*** THE GOVERNING INVARIANT (ADR-001) ***

    The Teensy determines truth. The renderer presents truth.

Nothing here computes a measurement value, a validity verdict, a quality grade
or a confidence figure. Every such field is read off the wire and carried
through unchanged. ``result_valid``, ``result_quality``, ``mean_coherence``,
``tf_confidence`` and the per-bin coverage nibbles are Teensy verdicts; this
module's only job is to not lose them.

The one thing decoded values are turned into is ``BinCoverage``, and that is
rendering policy over Teensy-authored coverage bytes — deciding whether to
draw a point, not deciding whether it is valid. The distinction matters: the
Teensy says "3 of 4 source bins were clamped"; the renderer decides that means
a saturation marker. It never decides that a clamped bin was really fine.

Unknown packet types decode to ``UnknownPacket``. A v2 receiver that dies on
an unfamiliar type id is the thing that makes the next additive packet a
breaking change (runbook Phase 10 step 9).
"""

from __future__ import annotations

import struct
from dataclasses import dataclass

from . import protocol
from .framing import Frame


class DecodeError(ValueError):
    """A frame passed CRC but its payload does not match protocol v2.

    This is a different failure from a CRC error and must be counted
    separately: CRC failures mean the wire is damaged, decode errors mean the
    two sides disagree about the format.
    """


class GeometryUnknown(DecodeError):
    """A RESULT arrived before HELLO, so its arrays cannot be located.

    Not an error in the stream — a receiver that connected mid-session will
    see exactly this. The caller should hold the frame, or wait for the Teensy
    to resend HELLO.
    """


# *** TEENSY-AUTHORED TEXT IS UTF-8, NOT ASCII. ***
#
# Found on real hardware bytes 2026-09-27, not by reading the header: the STATUS
# packet for `m` carries "Measuring \xe2\x80\x94 external stimulus" -- a UTF-8 EM
# DASH, because guitar_rig_analyzer.ino:560 has a literal em dash in the source
# string, as do ~20 other presentation_status() call sites. Decoding as ASCII
# turned every one of them into three U+FFFD replacement characters, so the Pi
# was corrupting a human-readable string the Teensy authored correctly.
#
# The synthesised test vectors could never have caught it: vectors.py wrote
# "Measuring - external stimulus" with an ASCII hyphen. Exactly the shared-author
# blind spot the hardware capture exists to break.
#
# errors="replace" is kept deliberately. A fixed-width field can truncate mid
# sequence, and a damaged byte must degrade to a visible replacement character
# rather than raise -- a status string is presentation, and it must never be able
# to take down a receiver that is tracking measurement state.
_TEXT_ENCODING = "utf-8"


def _text(raw: bytes) -> str:
    """Decode a Teensy-authored text field off the wire."""
    return raw.decode(_TEXT_ENCODING, errors="replace")


def _fixed_string(raw: bytes) -> str:
    """Decode a NUL-padded fixed-width wire field."""
    return _text(raw.split(b"\x00", 1)[0])


# =============================================================================
# COVERAGE — the clamp/validity contract from data_sender.h
# =============================================================================

@dataclass(frozen=True)
class BinCoverage:
    """How much of one transmitted live bin is real measurement.

    Packed on the wire as one byte per bin: high nibble = source bins CLAMPED,
    low nibble = source bins VALID, each 0..decim_ratio.

    *** WHY THIS IS NOT OPTIONAL ***
    A clamped bin is a SATURATION RAIL, not a measurement. On 2026-09-07 with
    nothing connected to RETURN_NODE the true transfer function sat ~23 dB
    below the -24.0 dB rail, and a consumer that ignored clamp state reported
    "1kHz=-24.0dB" in 33 of 33 consecutive windows as though it were data.
    Protocol v2 exists largely to stop the Pi repeating that (audit L1).
    """
    clamped: int
    valid: int
    ratio: int

    @property
    def saturated(self) -> bool:
        """Every source bin railed. Draw a saturation indicator, NOT the value."""
        return self.clamped >= self.ratio

    @property
    def pen_lift(self) -> bool:
        """No energised source bins — draw nothing. NaN in tf_db means the
        source fell below TF_SOURCE_GATE (audit L3)."""
        return self.valid == 0

    @property
    def partially_saturated(self) -> bool:
        return 0 < self.clamped < self.ratio

    @property
    def partial_coverage(self) -> bool:
        """Averaged over fewer source bins than its neighbours."""
        return 0 < self.valid < self.ratio

    @property
    def plottable(self) -> bool:
        """False means the value must not reach the curve as a measurement."""
        return not self.saturated and not self.pen_lift


def _unpack_coverage(raw: bytes, ratio: int) -> list[BinCoverage]:
    return [BinCoverage(clamped=b >> 4, valid=b & 0x0F, ratio=ratio)
            for b in raw]


# =============================================================================
# PACKETS
# =============================================================================

@dataclass(frozen=True)
class UnknownPacket:
    """Forward compatibility: skipped by length, carried, never rendered."""
    packet_type: int
    payload: bytes


@dataclass(frozen=True)
class Hello:
    """0x06 — the geometry and capability contract. Read before anything else.

    Structured rather than a parsed string (audit T2), so the receiver's
    compatibility check is a comparison, not a regex.

    *** HELLO ARRIVES REPEATEDLY, NOT ONCE. ***
    The Teensy re-announces every HELLO_REANNOUNCE_MS while no RESULT is
    staged (TODO-56), so a receiver that attaches late or misses one is not
    locked out. Handle repeats idempotently.

    ``session_id`` is what makes a repeat distinguishable from a restart:
    constant for one Teensy boot/session, different after a reboot. A CHANGED
    session_id is authoritative evidence that prior session state is stale —
    invalidate it and rebuild from current telemetry rather than assuming
    continuity. It is not a security nonce, not a measurement identity, and
    not unique across devices.
    """
    protocol_version: int
    live_bins: int
    fft_bins: int
    decim_ratio: int
    baud_rate: int
    sample_rate: int
    insights_max: int
    session_id: int
    capabilities: protocol.Capability
    firmware_version: str

    @property
    def geometry(self) -> protocol.Geometry:
        return protocol.Geometry(
            live_bins=self.live_bins,
            fft_bins=self.fft_bins,
            decim_ratio=self.decim_ratio,
            insights_max=self.insights_max,
            sample_rate=self.sample_rate,
        )

    @property
    def compatible(self) -> bool:
        return self.protocol_version == protocol.PROTOCOL_VERSION


@dataclass(frozen=True)
class LiveFrame:
    """0x01 — the live view, ~11 Hz, best-effort and droppable.

    ``output_block_number`` is the lower 16 bits of the audio block counter —
    the canonical timebase, and the only freshness signal on the wire. Gaps in
    it are dropped frames, which is expected and correct: presentation
    transport is lossy before measurement becomes lossy. Do not treat a gap as
    an error, and do not use Pi wall-clock time in its place.

    Decimation semantics, stated so a renderer knows what it is plotting:
      fft_source / fft_return  MAXIMUM over the source bins (peak-preserving)
      tf_db                    arithmetic MEAN in dB over the VALID source bins
    """
    measurement_state: protocol.MeasurementState
    flags: protocol.LiveFlags
    output_block_number: int
    peak_source_dbfs: float
    peak_return_dbfs: float
    tf_confidence: float
    tf_clamped_count: int
    fft_source: tuple[float, ...]
    fft_return: tuple[float, ...]
    tf_db: tuple[float, ...]
    coverage: tuple[BinCoverage, ...]

    @property
    def source_clip(self) -> bool:
        return bool(self.flags & protocol.LiveFlags.SOURCE_CLIP)

    @property
    def return_clip(self) -> bool:
        return bool(self.flags & protocol.LiveFlags.RETURN_CLIP)

    @property
    def tf_persistence_active(self) -> bool:
        return bool(self.flags & protocol.LiveFlags.TF_PERSISTENCE_ACTIVE)


@dataclass(frozen=True)
class Insight:
    """One Teensy-authored insight.

    ``mode`` separates MEASUREMENT (a measured fact) from ADVISORY
    (interpretation). They must stay visually distinguishable. The Pi never
    generates either from the arrays — if the Teensy did not say it, it is not
    shown.
    """
    mode: protocol.InsightMode
    severity: protocol.InsightSeverity
    frequency_hz: float
    magnitude_db: float
    title: str
    detail: str


@dataclass(frozen=True)
class Result:
    """0x02 — a completed measurement on the canonical grid. Reliable delivery.

    ``fft_size`` is the FFT length actually used and is NOT the array length:
    the four spectra are always ``fft_bins`` long (the canonical 512-bin grid),
    with MODE_PRECISION resampled onto it by the Teensy.

    ``line_in_level`` is present so Compare/Recall is honest — without it a
    receiver will cheerfully A/B two measurements taken at different input
    gains and present the difference as a rig difference (audit R6).
    """
    result_valid: bool
    result_quality: protocol.ResultQuality
    flags: protocol.ResultFlags
    calibration_type: protocol.CalibrationType
    calibration_warnings: protocol.CalibrationWarning
    n_averages_completed: int
    mean_coherence: float
    valid_bin_fraction: float
    timestamp_ms: int
    estimator: protocol.TfEstimator
    stimulus: protocol.StimulusType
    fft_mode: protocol.FftMode
    window_function: protocol.WindowFunction
    fft_size: int
    capture_start_block: int
    capture_end_block: int
    source_node_ch: int
    return_node_ch: int
    line_in_level: int
    clip_source_count: int
    clip_return_count: int
    firmware_version: str
    calibration_provenance: str
    tf_cal_mag_db: tuple[float, ...]
    tf_cal_phase_rad: tuple[float, ...]
    group_delay_ms: tuple[float, ...]
    coherence: tuple[float, ...]
    insights: tuple[Insight, ...]

    @property
    def clip_detected(self) -> bool:
        return bool(self.flags & protocol.ResultFlags.CLIP_DETECTED)

    @property
    def calibration_applied(self) -> bool:
        return bool(self.flags & protocol.ResultFlags.CALIBRATION_APPLIED)

    @property
    def generator_active(self) -> bool:
        return bool(self.flags & protocol.ResultFlags.GENERATOR_ACTIVE)


@dataclass(frozen=True)
class Status:
    """0x03 — a status string for display. Never sniffed for magic prefixes:
    view transitions come from VIEW / RESULT / ABORTED (audit T3)."""
    message: str


@dataclass(frozen=True)
class Aborted:
    """0x04 — the abort reason.

    ABORTED is sticky until the operator acknowledges it. The fact of the abort
    also rides in every live frame's ``measurement_state``, so a dropped
    ABORTED costs the reason string, not the fact.
    """
    reason: str


@dataclass(frozen=True)
class RouterStatus:
    """0x05 — jack/route snapshot (schema corrected 2026-09-26, TODO-58).

    *** jack_present IS MEANINGLESS WITHOUT jack_detect_available. ***
    Do not read ``presence_bits`` directly; call ``detect()``. For each jack:

        available = 0              -> UNKNOWN
        available = 1, present = 0 -> ABSENT
        available = 1, present = 1 -> PRESENT

    A Boolean cannot carry "we have no detector", which is why two masks exist
    rather than one overloaded flag. All four detectors are unavailable in the
    current hardware, so UNKNOWN is the expected answer today.

    *** ADR-004: return_source IS THE ONLY AUTHORITY ON THE SELECTED RETURN. ***
    It is operator-selected. NEVER infer it from presence — "XLR plug detected
    therefore XLR is active" is exactly what ADR-004 Decision 3 forbids, and
    with no detectors fitted it would be inferred from a pullup artefact.

    ``route_valid`` and ``can_inject`` were removed from the wire: the first
    was a tautology recomputable from ``return_source``, the second depended on
    an unavailable detector so its honest value was UNKNOWN. The Pi must not
    reconstruct either.

    Whether injection and monitor mode EXIST in this build comes from HELLO's
    capability bitmap, never inferred from these bytes (audit T4).
    ``injection_active`` answers a different question — is injection active
    *right now* — and both are needed.
    """
    presence_bits: protocol.Jack
    available_bits: protocol.Jack
    return_source: protocol.ReturnSource
    injection_active: bool
    monitor_mode: protocol.MonitorMode
    description: str

    def detect(self, jack: protocol.Jack) -> protocol.Detect:
        """Three-valued detection for one jack. The only correct way to ask."""
        if not (self.available_bits & jack):
            return protocol.Detect.UNKNOWN
        return (protocol.Detect.PRESENT if (self.presence_bits & jack)
                else protocol.Detect.ABSENT)

    @property
    def any_detector_available(self) -> bool:
        """False on the current hardware: no jack has a detect conductor."""
        return bool(self.available_bits)


@dataclass(frozen=True)
class StatePacket:
    """0x08 — the authoritative measurement-state snapshot (TODO-57).

    Means exactly one thing: *this was the Teensy's state when the snapshot was
    constructed.* Sent periodically rather than on transition, so a Pi that
    attaches mid-CAPTURE or during a sticky ABORTED learns the state without
    waiting for a new transition, and a dropped ABORTED event self-heals.

    ``measurement_state`` and ``abort_reason`` are a coherent pair: the
    firmware sets the reason before entering ABORTED and clears it before
    leaving, so a combination like IDLE-with-a-CLIP-reason cannot occur.

    *** audio_block_counter IS A TIMESTAMP, NOT A SEQUENCE NUMBER. ***
    It is canonical audio-time evidence of when the snapshot was taken. Do NOT
    compare two of them to decide which observation is newer: the firmware
    derives it from micros(), so it wraps to zero roughly every 71.6 minutes
    and never exceeds ~1.48e6. Ordering is already guaranteed by the transport,
    which writes whole packets in FIFO order.
    """
    measurement_state: protocol.MeasurementState
    abort_reason: protocol.AbortReason
    audio_block_counter: int

    @property
    def is_aborted(self) -> bool:
        return self.measurement_state is protocol.MeasurementState.ABORTED


@dataclass(frozen=True)
class ViewChange:
    """0x07 — an explicit view transition carrying no other data."""
    view_id: int

    @property
    def is_live(self) -> bool:
        return self.view_id == protocol.VIEW_LIVE


# =============================================================================
# DECODERS
# =============================================================================

_LIVE_HEADER = struct.Struct("<BBHfffH")
_HELLO = struct.Struct("<HHHHIIHHI")
_STATE = struct.Struct("<BBHI")
_RESULT_HEAD = struct.Struct("<BBBBBBHffIBBBBHIIBBBBHH")


def _enum(cls, raw: int, what: str):
    try:
        return cls(raw)
    except ValueError as exc:
        raise DecodeError(f"{what}: no such value {raw}") from exc


def decode_hello(payload: bytes) -> Hello:
    if len(payload) != protocol.HELLO_PAYLOAD_BYTES:
        raise DecodeError(
            f"HELLO is {len(payload)} B, expected "
            f"{protocol.HELLO_PAYLOAD_BYTES}")
    (version, live_bins, fft_bins, decim, baud, rate,
     insights_max, session_id, caps) = _HELLO.unpack_from(payload, 0)

    if live_bins == 0 or fft_bins == 0 or decim == 0:
        raise DecodeError("HELLO declares a zero geometry")
    if fft_bins != live_bins * decim:
        raise DecodeError(
            f"HELLO geometry is inconsistent: fft_bins={fft_bins} but "
            f"live_bins*decim_ratio={live_bins * decim}")

    return Hello(
        protocol_version=version,
        live_bins=live_bins,
        fft_bins=fft_bins,
        decim_ratio=decim,
        baud_rate=baud,
        sample_rate=rate,
        insights_max=insights_max,
        session_id=session_id,
        capabilities=protocol.Capability(caps & 0x0F),
        firmware_version=_fixed_string(payload[24:40]),
    )


def decode_live_frame(payload: bytes,
                      geometry: protocol.Geometry) -> LiveFrame:
    expected = protocol.live_payload_bytes(geometry.live_bins)
    if len(payload) != expected:
        raise DecodeError(
            f"LIVE_FRAME is {len(payload)} B, expected {expected} for "
            f"live_bins={geometry.live_bins}")

    (state, flags, block, peak_src, peak_ret,
     confidence, clamped_count) = _LIVE_HEADER.unpack_from(payload, 0)

    n = geometry.live_bins
    arrays = struct.Struct(f"<{n}f")
    pos = protocol.LIVE_HEADER_BYTES

    fft_source = arrays.unpack_from(payload, pos); pos += arrays.size
    fft_return = arrays.unpack_from(payload, pos); pos += arrays.size
    tf_db = arrays.unpack_from(payload, pos); pos += arrays.size
    coverage = _unpack_coverage(payload[pos:pos + n], geometry.decim_ratio)

    return LiveFrame(
        measurement_state=_enum(protocol.MeasurementState, state,
                                "LIVE_FRAME measurement_state"),
        flags=protocol.LiveFlags(flags & 0x07),
        output_block_number=block,
        peak_source_dbfs=peak_src,
        peak_return_dbfs=peak_ret,
        tf_confidence=confidence,
        tf_clamped_count=clamped_count,
        fft_source=fft_source,
        fft_return=fft_return,
        tf_db=tf_db,
        coverage=tuple(coverage),
    )


def decode_result(payload: bytes,
                  geometry: protocol.Geometry | None) -> Result:
    if geometry is None:
        raise GeometryUnknown(
            "RESULT cannot be decoded before HELLO: the array length is "
            "fft_bins, and the insight count that would let you solve for it "
            "sits after the arrays")

    n = geometry.fft_bins
    if len(payload) < protocol.RESULT_FIXED_BYTES + n * 4 * 4 + 1:
        raise DecodeError(
            f"RESULT is {len(payload)} B, too short for fft_bins={n}")

    (valid, quality, flags, cal_type, cal_warn, _r0,
     n_avg, coh, vbf, ts, estimator, stimulus, fft_mode, window,
     fft_size, cap_start, cap_end, src_ch, ret_ch, line_in, _r1,
     clip_src, clip_ret) = _RESULT_HEAD.unpack_from(payload, 0)

    firmware = _fixed_string(payload[42:58])
    provenance = _fixed_string(payload[58:154])

    arrays = struct.Struct(f"<{n}f")
    pos = protocol.RESULT_FIXED_BYTES
    tf_mag = arrays.unpack_from(payload, pos); pos += arrays.size
    tf_phase = arrays.unpack_from(payload, pos); pos += arrays.size
    gdelay = arrays.unpack_from(payload, pos); pos += arrays.size
    coherence = arrays.unpack_from(payload, pos); pos += arrays.size

    insight_count = payload[pos]; pos += 1
    if insight_count > geometry.insights_max:
        raise DecodeError(
            f"RESULT declares {insight_count} insights, above the "
            f"{geometry.insights_max} this firmware can produce")

    expected = protocol.result_payload_bytes(n, insight_count)
    if len(payload) != expected:
        raise DecodeError(
            f"RESULT is {len(payload)} B, expected {expected} for "
            f"fft_bins={n} and {insight_count} insights")

    insights = []
    for _ in range(insight_count):
        entry = payload[pos:pos + protocol.INSIGHT_ENTRY_BYTES]
        pos += protocol.INSIGHT_ENTRY_BYTES
        mode, severity, freq, mag = struct.unpack_from("<BBff", entry, 0)
        insights.append(Insight(
            mode=_enum(protocol.InsightMode, mode, "insight mode"),
            severity=_enum(protocol.InsightSeverity, severity,
                           "insight severity"),
            frequency_hz=freq,
            magnitude_db=mag,
            title=_fixed_string(entry[10:74]),
            detail=_fixed_string(entry[74:138]),
        ))

    return Result(
        result_valid=bool(valid),
        result_quality=_enum(protocol.ResultQuality, quality,
                             "result_quality"),
        flags=protocol.ResultFlags(flags & 0x07),
        calibration_type=_enum(protocol.CalibrationType, cal_type,
                               "calibration_type"),
        calibration_warnings=protocol.CalibrationWarning(cal_warn & 0x1F),
        n_averages_completed=n_avg,
        mean_coherence=coh,
        valid_bin_fraction=vbf,
        timestamp_ms=ts,
        estimator=_enum(protocol.TfEstimator, estimator, "estimator"),
        stimulus=_enum(protocol.StimulusType, stimulus, "stimulus"),
        fft_mode=_enum(protocol.FftMode, fft_mode, "fft_mode"),
        window_function=_enum(protocol.WindowFunction, window,
                              "window_function"),
        fft_size=fft_size,
        capture_start_block=cap_start,
        capture_end_block=cap_end,
        source_node_ch=src_ch,
        return_node_ch=ret_ch,
        line_in_level=line_in,
        clip_source_count=clip_src,
        clip_return_count=clip_ret,
        firmware_version=firmware,
        calibration_provenance=provenance,
        tf_cal_mag_db=tf_mag,
        tf_cal_phase_rad=tf_phase,
        group_delay_ms=gdelay,
        coherence=coherence,
        insights=tuple(insights),
    )


def decode_router_status(payload: bytes) -> RouterStatus:
    if len(payload) < protocol.ROUTER_FIXED_BYTES:
        raise DecodeError(f"ROUTER_STATUS is only {len(payload)} B")
    desc_len = payload[6]
    if desc_len > protocol.ROUTER_MAX_DESC:
        raise DecodeError(
            f"ROUTER_STATUS declares a {desc_len} B description, above the "
            f"{protocol.ROUTER_MAX_DESC} B the firmware can send")
    if len(payload) != protocol.ROUTER_FIXED_BYTES + desc_len:
        raise DecodeError(
            f"ROUTER_STATUS declares a {desc_len} B description but carries "
            f"{len(payload) - protocol.ROUTER_FIXED_BYTES} B")

    presence = protocol.Jack(payload[0] & 0x0F)
    available = protocol.Jack(payload[1] & 0x0F)

    # The producer masks presence by availability before transmitting. A bit
    # set here without its availability bit means the two sides disagree about
    # the contract -- fail loudly rather than render a presence claim no
    # detector can support.
    if presence & ~available:
        raise DecodeError(
            "ROUTER_STATUS reports jack presence for a detector it also "
            "reports as unavailable; the producer must mask these")

    return RouterStatus(
        presence_bits=presence,
        available_bits=available,
        return_source=_enum(protocol.ReturnSource, payload[2],
                            "return_source"),
        injection_active=bool(payload[3]),
        monitor_mode=_enum(protocol.MonitorMode, payload[4], "monitor_mode"),
        description=_text(payload[protocol.ROUTER_FIXED_BYTES:
                                  protocol.ROUTER_FIXED_BYTES + desc_len]),
    )


def decode_state(payload: bytes) -> StatePacket:
    if len(payload) != protocol.STATE_PAYLOAD_BYTES:
        raise DecodeError(
            f"STATE is {len(payload)} B, expected "
            f"{protocol.STATE_PAYLOAD_BYTES}")
    state, reason, _reserved, blocks = _STATE.unpack_from(payload, 0)
    return StatePacket(
        measurement_state=_enum(protocol.MeasurementState, state,
                                "STATE measurement_state"),
        abort_reason=_enum(protocol.AbortReason, reason, "STATE abort_reason"),
        audio_block_counter=blocks,
    )


def decode_view(payload: bytes) -> ViewChange:
    if len(payload) != protocol.VIEW_PAYLOAD_BYTES:
        raise DecodeError(f"VIEW is {len(payload)} B, expected 1")
    return ViewChange(view_id=payload[0])


def decode_string_payload(payload: bytes) -> str:
    if len(payload) > protocol.MAX_STRING_PAYLOAD:
        raise DecodeError(
            f"string payload is {len(payload)} B, above the "
            f"{protocol.MAX_STRING_PAYLOAD} B the firmware can send")
    return _text(payload)


def decode(frame: Frame, geometry: protocol.Geometry | None = None):
    """Dispatch one verified frame to its decoder.

    An unrecognised ``packet_type`` returns ``UnknownPacket`` rather than
    raising. That is what lets a future additive packet type ship without
    breaking this receiver (runbook Phase 10 step 9).
    """
    t = frame.packet_type
    p = frame.payload

    if t == protocol.PacketType.HELLO:
        return decode_hello(p)
    if t == protocol.PacketType.LIVE_FRAME:
        if geometry is None:
            raise GeometryUnknown("LIVE_FRAME decoded before HELLO")
        return decode_live_frame(p, geometry)
    if t == protocol.PacketType.RESULT:
        return decode_result(p, geometry)
    if t == protocol.PacketType.STATUS:
        return Status(message=decode_string_payload(p))
    if t == protocol.PacketType.ABORTED:
        return Aborted(reason=decode_string_payload(p))
    if t == protocol.PacketType.ROUTER_STATUS:
        return decode_router_status(p)
    if t == protocol.PacketType.VIEW:
        return decode_view(p)
    if t == protocol.PacketType.STATE:
        return decode_state(p)
    return UnknownPacket(packet_type=t, payload=p)
