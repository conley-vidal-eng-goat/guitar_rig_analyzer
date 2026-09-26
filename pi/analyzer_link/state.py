"""Receiver state model — decoded packets in, renderable instrument state out.

Pure and offline. No serial I/O, no UI framework, no timers of its own: every
call that needs a clock takes ``now_ms`` explicitly, so behaviour is
deterministic and testable.

*** THE GOVERNING INVARIANT (ADR-001) ***

    The Teensy determines truth. The renderer presents truth.

This module holds the Pi's belief about the instrument. It is the layer most
likely to erode that invariant, because "the UI needs to show something" is a
constant pressure to fill gaps with assumptions. It does not fill them. Where
the Teensy has not said, the answer is UNKNOWN.

FOUR RULINGS THIS MODULE IMPLEMENTS  (decided 2026-09-26, design gate)
---------------------------------------------------------------------
D1  UNKNOWN is a first-class state. Silence, HELLO, connection and session
    establishment are NEVER mapped to IDLE. The producer-side gap that makes
    UNKNOWN necessary is TODO-57; this models it honestly, it does not fix it.

D2  A valid Teensy-authored observation explicitly reporting MeasurementState
    .IDLE may clear the latched ABORTED. That is not the Pi deciding an abort
    was acknowledged: the firmware defines ABORTED as leaving only through
    measurementEngine_acknowledgeAbort() -> IDLE, so an authoritative IDLE
    observation IS evidence of acknowledgement. The rule is written against
    "any packet carrying an authoritative measurement_state", not against
    LIVE_FRAME specifically, so TODO-57's state packet plugs in unchanged.

D3  A changed session_id ends the previous session. Its abort latch cannot
    remain the CURRENT instrument state — it belonged to a Teensy that is
    gone. It is cleared, and a bounded historical record notes that the
    session ended while ABORTED was latched. The new session starts UNKNOWN.

D4  Telemetry is not promoted into renderable state before a valid HELLO has
    established the session. Pre-HELLO packets are still decoded and counted
    for link diagnostics — refusing to promote them is not a reason to discard
    the evidence that they arrived.

WHY VIEW(LIVE) DOES NOT CLEAR AN ABORT
--------------------------------------
It would be convenient and it is wrong. presentation_restoreLive() is called
from TWO places in the firmware (guitar_rig_analyzer.ino:590 and :600): after
measurementEngine_acknowledgeAbort(), and after measurementEngine_returnToLive()
from a RESULT view. presentation.h documents it as "returns the renderer from a
result/abort view to the live view" — a VIEW fact. "The Teensy asked for the
live view" and "the measurement engine is no longer ABORTED" are different
claims, and the protocol does not make the first imply the second. So VIEW
moves the view and leaves the latch alone.

WHAT LOCAL TIME IS AND IS NOT USED FOR
--------------------------------------
``now_ms`` is a local monotonic clock and is used for ONE thing: deciding that
the link has gone quiet. It is never a measurement timebase. The canonical
timing source for anything about the measurement is the Teensy's audio block
counter, which arrives in LIVE_FRAME as ``output_block_number``. Link staleness
never alters measurement state — a quiet link is a fact about the link.
"""

from __future__ import annotations

import enum
from collections import deque
from dataclasses import dataclass, field

from . import protocol, packets
from .framing import Frame


# =============================================================================
# UNKNOWN
# =============================================================================
# Deliberately NOT a member of protocol.MeasurementState. That enum is a MIRROR
# of the firmware's, and tests/test_firmware_header_sync.py fails if it gains a
# member the Teensy does not have. UNKNOWN is a receiver concept — the Teensy
# always knows its own state — so it lives here, in the receiver's vocabulary.

class _Unknown(enum.Enum):
    UNKNOWN = "UNKNOWN"

    def __repr__(self) -> str:      # pragma: no cover - cosmetic
        return "UNKNOWN"


UNKNOWN = _Unknown.UNKNOWN

ObservedState = protocol.MeasurementState | _Unknown


class View(enum.Enum):
    """What the Teensy last asked the renderer to show.

    NONE is the pre-session value: no view has been established because no
    session has. It is not "live".
    """
    NONE = "none"
    LIVE = "live"
    RESULT = "result"
    ABORTED = "aborted"


# =============================================================================
# RECORDS
# =============================================================================

@dataclass(frozen=True)
class SessionEnd:
    """A previous Teensy session, closed out when session_id changed.

    ``ended_with_abort_latched`` is phrased as what is actually known: the
    session ended before this receiver observed an acknowledgement. It does not
    claim anything was lost in transit — the Teensy may well have been
    acknowledged and reset by an operator standing in front of it.
    """
    session_id: int
    ended_with_abort_latched: bool
    abort_reason: str | None
    measurement_state_at_end: ObservedState


@dataclass
class LinkHealth:
    """Link-level diagnostics. Deliberately separate from instrument state:
    these count what arrived, not what is true of the instrument."""
    frames_in: int = 0
    packets_decoded: int = 0
    decode_errors: int = 0
    unknown_packets: int = 0
    geometry_unavailable: int = 0     # RESULT seen before HELLO
    not_promoted_pre_hello: int = 0   # D4: decoded, counted, not promoted
    hello_count: int = 0
    session_changes: int = 0
    last_packet_ms: int | None = None
    last_hello_ms: int | None = None


# =============================================================================
# THE MODEL
# =============================================================================

class ReceiverState:
    """The Pi's belief about the instrument, derived only from Teensy packets.

    Entry point is ``on_frame()`` rather than ``on_packet()`` because geometry
    ownership and the D4 pre-HELLO rule both live here: a RESULT cannot be
    decoded without the geometry this object holds, so decoding has to happen
    where that geometry is known.
    """

    def __init__(self, *, stale_after_ms: int | None = None,
                 history_limit: int = 8, status_limit: int = 16) -> None:
        # Three missed announcements before calling the link quiet. One missed
        # HELLO is normal: announcements are best-effort and are dropped under
        # backpressure by design (TODO-56).
        self.stale_after_ms = (stale_after_ms if stale_after_ms is not None
                               else protocol.HELLO_REANNOUNCE_MS * 3)
        self.health = LinkHealth()
        self.session_history: deque[SessionEnd] = deque(maxlen=history_limit)
        self.status_log: deque[str] = deque(maxlen=status_limit)

        self._geometry: protocol.Geometry | None = None
        self._hello: packets.Hello | None = None
        self._session_id: int | None = None

        self._measurement_state: ObservedState = UNKNOWN
        self._abort_latched = False
        self._abort_reason: str | None = None
        self._view = View.NONE

        self._latest_live: packets.LiveFrame | None = None
        self._latest_result: packets.Result | None = None
        self._router: packets.RouterStatus | None = None

    # -- queries ------------------------------------------------------------

    @property
    def session_established(self) -> bool:
        """True once a valid HELLO has identified the instrument. Until then
        nothing is promoted into renderable state (D4)."""
        return self._hello is not None

    @property
    def geometry(self) -> protocol.Geometry | None:
        return self._geometry

    @property
    def hello(self) -> packets.Hello | None:
        return self._hello

    @property
    def session_id(self) -> int | None:
        return self._session_id

    @property
    def measurement_state(self) -> ObservedState:
        """The Teensy's measurement state, or UNKNOWN if it has not said.

        UNKNOWN is not a synonym for IDLE and must never be rendered as one.
        """
        return self._measurement_state

    @property
    def state_known(self) -> bool:
        return self._measurement_state is not UNKNOWN

    @property
    def abort_latched(self) -> bool:
        """Sticky. Cleared only by an authoritative IDLE observation (D2) or by
        the session ending (D3). Never by silence, reconnect or a view change.
        """
        return self._abort_latched

    @property
    def abort_reason(self) -> str | None:
        return self._abort_reason

    @property
    def view(self) -> View:
        return self._view

    @property
    def latest_live(self) -> packets.LiveFrame | None:
        return self._latest_live

    @property
    def latest_result(self) -> packets.Result | None:
        return self._latest_result

    @property
    def router(self) -> packets.RouterStatus | None:
        """Route/jack snapshot — None until a ROUTER_STATUS arrives.

        Expect None indefinitely against current firmware: the packet is built
        and documented but has zero callers (TODO-58), so it is never sent.
        """
        return self._router

    def is_stale(self, now_ms: int) -> bool:
        """Has the link gone quiet? A LINK fact only — it does not and must not
        change measurement state."""
        last = self.health.last_packet_ms
        if last is None:
            return True
        return (now_ms - last) > self.stale_after_ms

    # -- ingest -------------------------------------------------------------

    def on_frame(self, frame: Frame, *, now_ms: int) -> object | None:
        """Absorb one CRC-verified frame. Returns the decoded packet, or None
        if it could not be decoded. Never raises on bad input: a receiver that
        dies on a malformed packet is a receiver that stops rendering."""
        self.health.frames_in += 1
        self.health.last_packet_ms = now_ms

        try:
            packet = packets.decode(frame, self._geometry)
        except packets.GeometryUnknown:
            # RESULT before HELLO. Expected on a mid-session attach, not an
            # error in the stream.
            self.health.geometry_unavailable += 1
            return None
        except packets.DecodeError:
            self.health.decode_errors += 1
            return None

        self.health.packets_decoded += 1

        if isinstance(packet, packets.UnknownPacket):
            # Forward compatibility: counted, never promoted, never rendered.
            self.health.unknown_packets += 1
            return packet

        if isinstance(packet, packets.Hello):
            self._apply_hello(packet, now_ms)
            return packet

        # D4 — everything below this line is session telemetry, and a session
        # that has not been identified cannot have telemetry promoted into it.
        # The packet was still decoded and counted above; that evidence is
        # useful for link debugging and is not thrown away.
        if not self.session_established:
            self.health.not_promoted_pre_hello += 1
            return packet

        self._promote(packet)
        return packet

    # -- internals ----------------------------------------------------------

    def _apply_hello(self, hello: packets.Hello, now_ms: int) -> None:
        self.health.hello_count += 1
        self.health.last_hello_ms = now_ms

        if self._session_id is not None and hello.session_id != self._session_id:
            self._end_session()
            self.health.session_changes += 1

        # Same session: idempotent. Geometry and capabilities are re-affirmed,
        # nothing else moves — not the view, not the abort latch, not the
        # cached result.
        self._hello = hello
        self._geometry = hello.geometry
        self._session_id = hello.session_id

    def _end_session(self) -> None:
        """D3 — close out the previous Teensy session."""
        self.session_history.append(SessionEnd(
            session_id=self._session_id,
            ended_with_abort_latched=self._abort_latched,
            abort_reason=self._abort_reason,
            measurement_state_at_end=self._measurement_state,
        ))

        # The previous session's state cannot describe the new one. In
        # particular the new Teensy is NOT assumed to be IDLE.
        self._measurement_state = UNKNOWN
        self._abort_latched = False
        self._abort_reason = None
        self._view = View.NONE
        self._latest_live = None
        self._latest_result = None
        self._router = None
        self.status_log.clear()

    def _promote(self, packet: object) -> None:
        if isinstance(packet, packets.LiveFrame):
            self._latest_live = packet
            self._observe_state(packet.measurement_state)
            if self._view is View.NONE:
                self._view = View.LIVE

        elif isinstance(packet, packets.Result):
            self._latest_result = packet
            self._view = View.RESULT
            # RESULT arriving does not tell us the engine's CURRENT state: by
            # the time it is parsed the Teensy may have moved on. No state
            # observation is made here.

        elif isinstance(packet, packets.Aborted):
            self._abort_latched = True
            self._abort_reason = packet.reason
            self._measurement_state = protocol.MeasurementState.ABORTED
            self._view = View.ABORTED

        elif isinstance(packet, packets.ViewChange):
            # Moves the view ONLY. See the module docstring: VIEW(LIVE) is not
            # an acknowledgement, and clearing the latch here would invent a
            # fact the protocol does not carry.
            if packet.is_live:
                self._view = View.LIVE

        elif isinstance(packet, packets.RouterStatus):
            self._router = packet

        elif isinstance(packet, packets.Status):
            self.status_log.append(packet.message)

    def _observe_state(self, observed: protocol.MeasurementState) -> None:
        """Apply an authoritative measurement-state observation (D2).

        Written against "a packet carried a measurement_state", not against
        LIVE_FRAME, so TODO-57's authoritative state packet plugs in here
        unchanged.

        Only IDLE clears the latch, per the design ruling. ARMED is also
        logically incompatible with ABORTED — the engine reaches ARMED from
        IDLE via arm() — but that is a second inference and the ruling was
        specific, so it is not taken. In practice an IDLE observation precedes
        ARMED, because live frames flow at ~11 Hz in IDLE.
        """
        self._measurement_state = observed
        if observed is protocol.MeasurementState.IDLE:
            self._abort_latched = False
            self._abort_reason = None
