"""Render-ready snapshot of the receiver. Pure — no Tk, no I/O.

*** THE ARCHITECTURAL INVARIANT, RESTATED WHERE IT IS EASIEST TO BREAK ***

ADR-001: the Teensy determines truth. This module FORMATS Teensy-authored values
and does not derive any. In particular it must never:

  - grade measurement quality (the Teensy sends ``result_quality``)
  - decide validity (the Teensy sends ``result_valid``)
  - author, rank or filter advisories (the Teensy sends ``insights``)
  - infer which return is active from jack presence (ADR-004 forbids it;
    ``return_source`` is the sole authority)
  - turn an unknown into a number

If this module ever needs to compute a judgement the Teensy already made, the
protocol boundary is wrong and the fix belongs on the wire, not here.

Formatting IS allowed: turning -23.8 into a bar length, or an enum into a label,
presents an authoritative value rather than deriving a new one.

*** UNKNOWN IS A FIRST-CLASS VALUE ***

Before HELLO the Pi does not know the geometry, so it cannot locate any array and
must not guess. ``ReceiverState`` already models this; the snapshot carries it
through as ``session_established == False`` and every derived field ``None``.
``None`` here always means "not known", never "zero".
"""

from __future__ import annotations

from dataclasses import dataclass, field

from analyzer_link import packets, protocol
from analyzer_link.state import ReceiverState, View

UNKNOWN_TEXT = "UNKNOWN"


@dataclass(frozen=True)
class LevelReading:
    """One node's level. ``dbfs is None`` means no live frame has arrived."""
    dbfs: float | None
    clipping: bool

    @property
    def text(self) -> str:
        if self.dbfs is None:
            return UNKNOWN_TEXT
        return f"{self.dbfs:+.1f} dBFS"


@dataclass(frozen=True)
class Snapshot:
    """Everything the renderer needs, and nothing it has to interpret."""

    # --- link / session ---
    session_established: bool
    session_id: int | None
    firmware_version: str | None
    protocol_version: int | None
    geometry: protocol.Geometry | None
    link_stale: bool
    frames_in: int
    decode_errors: int
    unknown_packets: int
    geometry_unavailable: int

    # --- authoritative measurement state ---
    state_known: bool
    measurement_state: protocol.MeasurementState | None
    abort_latched: bool
    abort_reason_text: str | None
    abort_reason_code: protocol.AbortReason
    view: View

    # --- live telemetry ---
    source: LevelReading
    returns: LevelReading
    tf_confidence: float | None
    tf_clamped_count: int | None
    live: packets.LiveFrame | None

    # --- result ---
    result: packets.Result | None

    # --- router ---
    return_source: protocol.ReturnSource | None
    router_description: str | None
    detectors_available: bool

    warnings: tuple[str, ...] = field(default=())

    # -- convenience for the renderer, all pass-through --------------------

    @property
    def state_text(self) -> str:
        if not self.state_known or self.measurement_state is None:
            return UNKNOWN_TEXT
        return self.measurement_state.name

    @property
    def session_text(self) -> str:
        if not self.session_established or self.session_id is None:
            return UNKNOWN_TEXT
        return str(self.session_id)

    @property
    def firmware_text(self) -> str:
        return self.firmware_version or UNKNOWN_TEXT

    @property
    def quality_text(self) -> str:
        """The Teensy's grade, verbatim. Never recomputed here."""
        if self.result is None:
            return UNKNOWN_TEXT
        return self.result.result_quality.name

    @property
    def calibration_text(self) -> str:
        if self.result is None:
            return UNKNOWN_TEXT
        r = self.result
        applied = "applied" if r.calibration_applied else "NOT applied"
        return f"{r.calibration_type.name} — {applied}"

    @property
    def calibration_warning_names(self) -> tuple[str, ...]:
        if self.result is None:
            return ()
        bits = int(self.result.calibration_warnings)
        return tuple(w.name for w in protocol.CalibrationWarning if bits & int(w))


def _level(dbfs: float | None, clipping: bool) -> LevelReading:
    return LevelReading(dbfs=dbfs, clipping=clipping)


def snapshot(state: ReceiverState, *, now_ms: int) -> Snapshot:
    """Build a Snapshot from the receiver. Reads only; never mutates state."""
    hello = state.hello
    live = state.latest_live
    result = state.latest_result
    router = state.router
    health = getattr(state, "health", None)

    warnings: list[str] = []

    # Jack presence must never be read without availability (TODO-58). The Pi
    # surfaces "no detector" rather than "not present".
    detectors_available = False
    if router is not None:
        detectors_available = int(router.available_bits) != 0
        if int(router.presence_bits) and not detectors_available:
            # Should be impossible: the firmware masks presence by availability
            # before transmitting. If it ever happens, say so loudly.
            warnings.append("ROUTER: presence bits set with no detector "
                            "available — firmware masking failed")

    return Snapshot(
        session_established=state.session_established,
        session_id=state.session_id,
        firmware_version=(hello.firmware_version if hello else None),
        protocol_version=(hello.protocol_version if hello else None),
        geometry=state.geometry,
        link_stale=state.is_stale(now_ms),
        frames_in=getattr(health, "frames_in", 0) if health else 0,
        decode_errors=getattr(health, "decode_errors", 0) if health else 0,
        unknown_packets=getattr(health, "unknown_packets", 0) if health else 0,
        geometry_unavailable=(getattr(health, "geometry_unavailable", 0)
                              if health else 0),
        state_known=state.state_known,
        measurement_state=(state.measurement_state
                           if state.state_known else None),
        abort_latched=state.abort_latched,
        abort_reason_text=state.abort_reason,
        abort_reason_code=state.abort_reason_code,
        view=state.view,
        source=_level(live.peak_source_dbfs if live else None,
                      bool(live.source_clip) if live else False),
        returns=_level(live.peak_return_dbfs if live else None,
                       bool(live.return_clip) if live else False),
        tf_confidence=(live.tf_confidence if live else None),
        tf_clamped_count=(live.tf_clamped_count if live else None),
        live=live,
        result=result,
        return_source=(router.return_source if router else None),
        router_description=(router.description if router else None),
        detectors_available=detectors_available,
        warnings=tuple(warnings),
    )
