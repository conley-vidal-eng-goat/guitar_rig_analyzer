"""Failure-behaviour tests against the REAL 30 s hardware capture.

Runbook Phase 10 steps 8 (CRC rejection) and 9 (unknown-packet tolerance),
exercised offline against bytes a flashed Teensy actually produced rather than
against synthetic vectors. That distinction is the whole value: the framing,
the timing jitter, the mid-stream start and the packet interleaving are all
real, so a parser that only copes with tidy synthetic streams fails here.

*** THE FIXTURE IS EVIDENCE AND IS NEVER MODIFIED. ***
Every mutation is derived in memory from a copy. A test that edited
phase10-teensy-pi-idle-30s.bin would destroy the artifact its own credibility
rests on, so `test_fixture_is_unmodified` asserts the hash on every run.
"""

from __future__ import annotations

import hashlib
import pathlib
import struct
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "tools"))

from analyzer_link import protocol
from analyzer_link.crc import crc16
from replay import replay

REPO = pathlib.Path(__file__).resolve().parents[2]
FIXTURE = REPO / "ai" / "evidence" / "phase10-teensy-pi-idle-30s.bin"
FIXTURE_SHA = "e26646cbb8df1714ae721ac45e33ad1f25486bf3af31eb9b36079e5c56ddb488"

# Offsets established by walking the real stream (see the journal entry for
# 2026-09-26). Asserted below rather than trusted, so a different fixture or a
# corrupted one fails loudly instead of silently testing the wrong bytes.
FIRST_HELLO_OFFSET = 25377
SESSION_ID_BYTE = 25400          # first HELLO, payload[18] = session_id low byte
FRAME_BOUNDARY = 61007           # end of the second HELLO


def framed(packet_type: int, payload: bytes) -> bytes:
    return (struct.pack("<HBH", protocol.SYNC_WORD, packet_type, len(payload))
            + payload + struct.pack("<H", crc16(payload)))


@unittest.skipUnless(FIXTURE.is_file(), "hardware fixture not present")
class TestHardwareFixture(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.raw = FIXTURE.read_bytes()
        cls.clean = replay(cls.raw, seconds=30)

    def test_fixture_is_unmodified(self):
        """Guards the evidence. Runs on every invocation, deliberately."""
        self.assertEqual(hashlib.sha256(self.raw).hexdigest(), FIXTURE_SHA)
        self.assertEqual(len(self.raw), 1094489)

    def test_clean_replay_is_the_baseline(self):
        r = self.clean
        self.assertTrue(r["transport_ok"], r["transport_problems"])
        self.assertEqual(r["framing"]["frames_ok"], 765)
        self.assertEqual(r["framing"]["crc_failures"], 0)
        self.assertEqual(r["receiver"]["hello_session_ids"], [4])
        self.assertEqual(r["receiver"]["measurement_state"], "IDLE")

    def test_the_targeted_offsets_are_what_we_think_they_are(self):
        # A mutation test that hits the wrong bytes proves nothing.
        self.assertEqual(self.raw[FIRST_HELLO_OFFSET:FIRST_HELLO_OFFSET + 2],
                         protocol.SYNC_BYTES)
        self.assertEqual(self.raw[FIRST_HELLO_OFFSET + 2],
                         int(protocol.PacketType.HELLO))
        self.assertEqual(
            struct.unpack_from("<H", self.raw, SESSION_ID_BYTE)[0], 4,
            "SESSION_ID_BYTE must point at the session_id field reading 4")
        self.assertEqual(self.raw[FRAME_BOUNDARY:FRAME_BOUNDARY + 2],
                         protocol.SYNC_BYTES)

    # -- runbook step 8: CRC rejection ------------------------------------

    def test_crc_rejects_a_corrupted_session_id(self):
        """The mutation is chosen to matter, not to be arbitrary.

        Flipping session_id from 4 to 99 inside a real HELLO is the most
        damaging single-byte corruption available: had CRC not caught it, the
        receiver would conclude the Teensy had rebooted, discard the whole
        session and restart at UNKNOWN. This proves CRC protecting a field
        whose corruption has consequences, not merely that the scanner can
        resynchronise after garbage.
        """
        mutated = bytearray(self.raw)
        self.assertEqual(mutated[SESSION_ID_BYTE], 0x04)
        mutated[SESSION_ID_BYTE] = 0x63                  # 4 -> 99
        r = replay(bytes(mutated), seconds=30)

        # Rejected, not rendered. Exactly one frame lost.
        self.assertGreaterEqual(r["framing"]["crc_failures"], 1)
        self.assertEqual(r["framing"]["frames_ok"], 764)
        self.assertEqual(r["packets"]["Hello"], 29)
        self.assertFalse(r["transport_ok"])

        # The damage is contained: session 99 never reaches the model.
        self.assertEqual(r["receiver"]["hello_session_ids"], [4])
        self.assertNotIn(99, r["receiver"]["hello_session_ids"])

        # Authoritative state survives.
        self.assertEqual(r["receiver"]["measurement_state"], "IDLE")
        self.assertEqual(r["router"]["return_source"], "TS")

    def test_the_measured_cost_of_one_lost_hello_is_one_reannounce_period(self):
        """What a dropped HELLO actually costs, measured on real bytes.

        The corrupted HELLO is the FIRST one, so geometry is unavailable until
        the next announcement a second later. The effect is precise:

          promoted LiveFrame     631 -> 610   (-21)
          geometry_unavailable    14 ->  35   (+21)
          total live frames      645 -> 645   (unchanged)

        21 frames at 21.5/s is 0.98 s, against a 1.0 s re-announce period. So
        nothing is LOST from the stream -- promotion is DEFERRED by exactly one
        HELLO interval and then self-heals.

        This is TODO-56's value proposition measured rather than argued. Before
        that fix HELLO was sent once, and losing it meant the Pi could never
        decode a RESULT until the Teensy rebooted. It now costs one second.

        My first version of this test asserted the LiveFrame count was
        unchanged, on the assumption that a dropped HELLO costs nothing. It
        failed, and the failure was more informative than the assertion.
        """
        mutated = bytearray(self.raw)
        mutated[SESSION_ID_BYTE] = 0x63
        r = replay(bytes(mutated), seconds=30)

        promoted_before = self.clean["packets"]["LiveFrame"]
        blocked_before = self.clean["receiver"]["geometry_unavailable"]
        promoted_after = r["packets"]["LiveFrame"]
        blocked_after = r["receiver"]["geometry_unavailable"]

        deferred = promoted_before - promoted_after
        self.assertEqual(deferred, blocked_after - blocked_before,
                         "frames must move from promoted to blocked, not vanish")
        self.assertEqual(promoted_after + blocked_after,
                         promoted_before + blocked_before,
                         "total live frames in the stream must not change")

        # One re-announce period at the measured cadence, within a frame.
        self.assertAlmostEqual(deferred / 21.5, 1.0, delta=0.15)

    def test_packets_that_need_no_geometry_are_unaffected(self):
        # STATE and ROUTER_STATUS decode without geometry, so losing a HELLO
        # cannot defer them -- which is why STATE could repair a measurement
        # state even while live frames were still undecodable.
        mutated = bytearray(self.raw)
        mutated[SESSION_ID_BYTE] = 0x63
        r = replay(bytes(mutated), seconds=30)
        self.assertEqual(r["packets"]["StatePacket"],
                         self.clean["packets"]["StatePacket"])
        self.assertEqual(r["packets"]["RouterStatus"],
                         self.clean["packets"]["RouterStatus"])

    def test_a_corrupted_live_frame_is_rejected_without_collateral(self):
        """Corruption in the largest packet type, after geometry exists.

        A 1689-byte frame is 36x a HELLO, and resync scans the whole rejected
        payload -- so this is where a resync bug would swallow a neighbour.
        Exactly one live frame is lost and nothing else moves.
        """
        target = self._first_post_hello_live_payload_byte()
        mutated = bytearray(self.raw)
        mutated[target] ^= 0xFF
        r = replay(bytes(mutated), seconds=30)

        self.assertGreaterEqual(r["framing"]["crc_failures"], 1)
        self.assertEqual(r["framing"]["frames_ok"], 764)
        self.assertEqual(r["packets"]["LiveFrame"],
                         self.clean["packets"]["LiveFrame"] - 1,
                         "exactly one live frame lost")
        # No neighbour taken with it.
        for kind in ("Hello", "StatePacket", "RouterStatus"):
            self.assertEqual(r["packets"][kind], self.clean["packets"][kind])
        self.assertEqual(r["receiver"]["hello_session_ids"], [4])
        self.assertEqual(r["receiver"]["measurement_state"], "IDLE")

    def _first_post_hello_live_payload_byte(self) -> int:
        """Offset of a payload byte in the first LIVE_FRAME after the first
        HELLO, so geometry already exists when it is rejected."""
        pos = FIRST_HELLO_OFFSET
        while True:
            pos = self.raw.find(protocol.SYNC_BYTES, pos + 2)
            self.assertGreater(pos, 0, "no live frame found after the HELLO")
            ptype = self.raw[pos + 2]
            plen = struct.unpack_from("<H", self.raw, pos + 3)[0]
            if ptype == int(protocol.PacketType.LIVE_FRAME):
                payload = self.raw[pos + 5:pos + 5 + plen]
                (wire,) = struct.unpack_from("<H", self.raw, pos + 5 + plen)
                if wire == crc16(payload):
                    return pos + 5 + (plen // 2)

    # -- runbook step 9: unknown packet type ------------------------------

    def test_unknown_packet_type_is_tolerated_and_state_survives(self):
        """A WELL-FORMED packet of an unknown type: valid sync, valid length,
        valid CRC. This is forward compatibility, not error handling — the
        receiver must skip it by length and carry on."""
        unknown = framed(0xFE, bytes(range(32)))
        mutated = (self.raw[:FRAME_BOUNDARY] + unknown
                   + self.raw[FRAME_BOUNDARY:])
        r = replay(mutated, seconds=30)

        # It was seen, understood to be unknown, and skipped cleanly.
        self.assertIn("0xfe", r["unknown_types"])
        self.assertEqual(r["unknown_types"]["0xfe"], 1)
        self.assertEqual(r["framing"]["frames_ok"], 766, "one extra frame")
        self.assertEqual(r["framing"]["crc_failures"], 0,
                         "a valid-CRC unknown type must not read as corruption")

        # Every known packet still arrived, unchanged.
        for kind in ("LiveFrame", "StatePacket", "RouterStatus", "Hello"):
            self.assertEqual(r["packets"][kind], self.clean["packets"][kind])

        # Authoritative state is untouched.
        self.assertEqual(r["receiver"]["hello_session_ids"], [4])
        self.assertEqual(r["receiver"]["measurement_state"], "IDLE")
        self.assertEqual(r["receiver"]["geometry"],
                         self.clean["receiver"]["geometry"])
        self.assertEqual(r["router"], self.clean["router"])

    def test_unknown_type_is_flagged_even_though_it_is_tolerated(self):
        """Tolerated and unremarkable are different things.

        The PARSER skips it; the REPORT still flags it, because in a capture
        from our own firmware an unknown type means producer and consumer
        disagree about the protocol. Both layers are behaving correctly.
        """
        unknown = framed(0xFE, b"\x00" * 8)
        r = replay(self.raw[:FRAME_BOUNDARY] + unknown
                   + self.raw[FRAME_BOUNDARY:], seconds=30)
        self.assertFalse(r["transport_ok"])
        self.assertTrue(any("unknown packet" in p
                            for p in r["transport_problems"]))

    def test_a_zero_length_unknown_packet_is_handled(self):
        # Degenerate but legal: type 0xFD, no payload, CRC over nothing.
        unknown = framed(0xFD, b"")
        r = replay(self.raw[:FRAME_BOUNDARY] + unknown
                   + self.raw[FRAME_BOUNDARY:], seconds=30)
        self.assertIn("0xfd", r["unknown_types"])
        self.assertEqual(r["framing"]["crc_failures"], 0)
        self.assertEqual(r["receiver"]["measurement_state"], "IDLE")


if __name__ == "__main__":
    unittest.main()
