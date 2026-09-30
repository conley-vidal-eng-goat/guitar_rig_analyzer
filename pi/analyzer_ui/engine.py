"""Acquisition side of the UI: bytes in, Snapshot out. No Tk, no rendering.

This is the seam the architecture needs. The renderer talks only to ``Engine``,
and ``Engine`` talks only to a ``ByteSource`` — so replaying
``ai/evidence/phase10-result-1khz.bin`` during development exercises *exactly*
the code path that live UART input will, framing and receiver state included.
A UI wired straight to a fixture parser would prove nothing about the live path.

``Engine`` owns the existing ``FrameScanner`` and ``ReceiverState`` unchanged.
It adds no decoding and no interpretation of its own; if something here starts
deciding what a packet means, it belongs in ``analyzer_link`` where it is tested
against real hardware bytes.
"""

from __future__ import annotations

import time

from analyzer_link import framing, packets
from analyzer_link.state import ReceiverState

from .model import Snapshot, snapshot
from .sources import ByteSource


class Engine:
    """Pumps a ByteSource through the production framing + receiver stack."""

    def __init__(self, source: ByteSource, *,
                 stale_after_ms: int | None = 1500) -> None:
        self.source = source
        self.scanner = framing.FrameScanner()
        # A live view is stale if telemetry stops. 1500 ms is three STATE
        # periods: long enough not to flicker, short enough that an operator
        # notices the link died rather than trusting a frozen number.
        self.state = ReceiverState(stale_after_ms=stale_after_ms)
        self._t0 = time.monotonic()
        self.bytes_fed = 0
        self.frames_seen = 0
        self.decode_failures = 0
        self.last_error: str | None = None

    # -- clock ---------------------------------------------------------------

    def now_ms(self) -> int:
        """Monotonic milliseconds since the engine started.

        Deliberately the host clock, not Teensy audio time. This drives only
        staleness and repaint decisions — presentation concerns. Anything that
        must be placed on the instrument's timebase uses the Teensy's own
        ``audio_block_counter``, as ``replay.py --timeline`` does.
        """
        return int((time.monotonic() - self._t0) * 1000)

    # -- the pump ------------------------------------------------------------

    def pump(self) -> int:
        """Read whatever is available and feed it through. Returns bytes fed."""
        data = self.source.read()
        if not data:
            return 0
        self.bytes_fed += len(data)
        now = self.now_ms()
        for frame in self.scanner.feed(data):
            self.frames_seen += 1
            try:
                self.state.on_frame(frame, now_ms=now)
            except packets.DecodeError as exc:
                # Counted, surfaced, never fatal. A malformed packet must not be
                # able to take down a display that is tracking measurement state.
                self.decode_failures += 1
                self.last_error = str(exc)
        return len(data)

    def snapshot(self) -> Snapshot:
        return snapshot(self.state, now_ms=self.now_ms())

    # -- framing health, for the status line --------------------------------

    @property
    def framing_stats(self):
        return self.scanner.stats

    def close(self) -> None:
        self.source.close()
