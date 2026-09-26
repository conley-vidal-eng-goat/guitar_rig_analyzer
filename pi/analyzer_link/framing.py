"""Frame scanner — raw UART bytes in, verified frames out.

Implements the receiver algorithm stated in ``data_sender.h``:

    1. Scan for SYNC_WORD
    2. Read packet_type and payload_length
    3. Read payload + CRC
    4. Verify CRC, discard on mismatch and resume scanning at step 1
    5. Parse payload based on packet_type
    6. Ignore unknown packet types by skipping payload_length bytes

Steps 1-4 live here. Steps 5-6 live in ``packets.py``.

Two deliberate choices, both about not trusting a corrupted header:

RESYNC POSITION. On a CRC failure the scanner resumes at ``start + 1``, NOT
past the declared payload. A packet that failed CRC has a length field that
failed CRC too, so skipping by it would be trusting the corruption to tell the
truth about its own size. One byte forward is the only position that cannot be
led astray. The cost is rescanning a few KB; the benefit is that a burst of
line noise cannot walk the scanner into the middle of the next good packet.

BOUNDED LENGTH. ``0x55 0xAA`` occurs inside float payload data regularly, so
false syncs are normal, not exceptional. A length field above
``max_payload_bytes()`` is therefore treated as a false sync and rejected
immediately rather than buffered. Without that bound, two noise bytes could
make the receiver wait on 64 KB that will never arrive.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field

from . import protocol
from .crc import crc16

_HEADER = struct.Struct("<HBH")     # sync, type, payload_length


@dataclass(frozen=True)
class Frame:
    """One CRC-verified frame. ``packet_type`` may be unknown — that is the
    caller's problem to tolerate, not the scanner's to reject."""
    packet_type: int
    payload: bytes


@dataclass
class ScannerStats:
    """Everything the link's health can be judged from.

    ``crc_failures`` is the figure runbook step 8 asks for. ``bytes_discarded``
    rising without ``frames_ok`` rising is a physical-layer fault (baud, wiring,
    or — the classic — no common ground), not a protocol fault.
    """
    frames_ok: int = 0
    crc_failures: int = 0
    oversize_rejects: int = 0
    bytes_discarded: int = 0
    bytes_in: int = 0


class FrameScanner:
    """Incremental, restartable byte-stream framer.

    Feed it whatever arrives — one byte or four kilobytes, split anywhere,
    including mid-header. It holds partial frames across calls, so a serial
    read that lands in the middle of a packet costs nothing.
    """

    def __init__(self, max_payload: int | None = None) -> None:
        self._buf = bytearray()
        self._max_payload = (max_payload if max_payload is not None
                             else protocol.max_payload_bytes())
        self.stats = ScannerStats()

    # -- geometry -----------------------------------------------------------

    def set_max_payload(self, max_payload: int) -> None:
        """Re-bound the scanner once HELLO reports the real geometry."""
        self._max_payload = max_payload

    # -- the scanner --------------------------------------------------------

    def feed(self, data: bytes) -> list[Frame]:
        """Absorb bytes; return every complete, CRC-verified frame found."""
        self.stats.bytes_in += len(data)
        self._buf.extend(data)
        return self._drain()

    def _drain(self) -> list[Frame]:
        out: list[Frame] = []
        buf = self._buf

        while True:
            start = buf.find(protocol.SYNC_BYTES)
            if start < 0:
                # No sync at all. Keep the last byte: a 0x55 at the very end
                # may be the first half of a sync word split across reads.
                keep = 1 if buf and buf[-1] == protocol.SYNC_BYTES[0] else 0
                drop = len(buf) - keep
                if drop > 0:
                    self.stats.bytes_discarded += drop
                    del buf[:drop]
                return out

            if start > 0:
                self.stats.bytes_discarded += start
                del buf[:start]

            if len(buf) < protocol.HEADER_BYTES:
                return out                      # header still incomplete

            _sync, packet_type, payload_len = _HEADER.unpack_from(buf, 0)

            if payload_len > self._max_payload:
                # A false sync inside payload data, or a corrupted header.
                # Either way this is not a packet. Step over the sync word's
                # first byte and keep scanning.
                self.stats.oversize_rejects += 1
                self.stats.bytes_discarded += 1
                del buf[:1]
                continue

            total = protocol.HEADER_BYTES + payload_len + protocol.CRC_BYTES
            if len(buf) < total:
                return out                      # payload/CRC still arriving

            payload = bytes(buf[protocol.HEADER_BYTES:
                                protocol.HEADER_BYTES + payload_len])
            (wire_crc,) = struct.unpack_from(
                "<H", buf, protocol.HEADER_BYTES + payload_len)

            if wire_crc != crc16(payload):
                # See RESYNC POSITION in the module docstring: one byte, not
                # one packet.
                self.stats.crc_failures += 1
                self.stats.bytes_discarded += 1
                del buf[:1]
                continue

            self.stats.frames_ok += 1
            out.append(Frame(packet_type=packet_type, payload=payload))
            del buf[:total]

    # -- reconnect ----------------------------------------------------------

    def reset(self) -> None:
        """Drop buffered bytes without clearing statistics.

        Call on a link drop. A half-received frame from before the drop cannot
        be completed by bytes from after it, and leaving it in place would let
        a stale prefix corrupt the first frame of the new session.
        """
        self._buf.clear()

    @property
    def buffered_bytes(self) -> int:
        return len(self._buf)
