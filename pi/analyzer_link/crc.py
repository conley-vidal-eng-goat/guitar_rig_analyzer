"""CRC-16/CCITT-FALSE — the integrity check protocol v2 puts on every packet.

Mirrors ``crc16_update`` / ``crc16_block`` in ``data_sender.cpp`` exactly:
init 0xFFFF, polynomial 0x1021, MSB-first, no input/output reflection, no
final XOR. Computed over the PAYLOAD ONLY — not the 5-byte header.

On the wire the two CRC bytes are little-endian (low byte first), matching
``trySendBestEffort()``'s ``tail[]``.
"""

from __future__ import annotations

_POLY = 0x1021
_INIT = 0xFFFF


def crc16(data: bytes) -> int:
    """CRC-16/CCITT-FALSE over ``data``."""
    crc = _INIT
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ _POLY) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
    return crc
