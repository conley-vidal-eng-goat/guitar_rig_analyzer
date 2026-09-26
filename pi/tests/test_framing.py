"""Frame scanner: sync, split reads, CRC rejection, resync, bounded length.

These cover runbook Phase 10 step 8 ("demonstrate CRC rejection") at the
offline layer. Step 8 itself is a bench step against a real stream; what is
proven here is that the receiver behaves correctly when given corrupted bytes.
"""

import struct
import unittest

from analyzer_link import protocol
from analyzer_link.framing import FrameScanner

from . import vectors

GEO = protocol.Geometry()


class TestFrameScanner(unittest.TestCase):

    def setUp(self):
        self.scanner = FrameScanner()

    def test_single_clean_frame(self):
        frames = self.scanner.feed(vectors.hello())
        self.assertEqual(len(frames), 1)
        self.assertEqual(frames[0].packet_type, protocol.PacketType.HELLO)
        self.assertEqual(self.scanner.stats.crc_failures, 0)
        self.assertEqual(self.scanner.stats.bytes_discarded, 0)

    def test_back_to_back_frames_in_one_read(self):
        stream = vectors.hello() + vectors.view() + vectors.status("ready")
        frames = self.scanner.feed(stream)
        self.assertEqual([f.packet_type for f in frames],
                         [protocol.PacketType.HELLO,
                          protocol.PacketType.VIEW,
                          protocol.PacketType.STATUS])

    def test_stream_split_one_byte_at_a_time(self):
        # A UART read can land anywhere, including mid-header and mid-CRC.
        stream = vectors.hello() + vectors.live_frame(GEO)
        got = []
        for b in stream:
            got.extend(self.scanner.feed(bytes([b])))
        self.assertEqual([f.packet_type for f in got],
                         [protocol.PacketType.HELLO,
                          protocol.PacketType.LIVE_FRAME])

    def test_leading_garbage_is_discarded_then_frame_is_found(self):
        noise = b"\x00\xff\x13\x55\x37" * 4
        frames = self.scanner.feed(noise + vectors.hello())
        self.assertEqual(len(frames), 1)
        self.assertEqual(self.scanner.stats.bytes_discarded, len(noise))

    def test_sync_word_split_across_two_reads(self):
        stream = vectors.view()
        self.assertEqual(self.scanner.feed(stream[:1]), [])   # just 0x55
        frames = self.scanner.feed(stream[1:])
        self.assertEqual(len(frames), 1)

    # -- corruption ---------------------------------------------------------

    def test_corrupted_payload_is_rejected_not_rendered(self):
        good = bytearray(vectors.hello())
        good[protocol.HEADER_BYTES + 2] ^= 0xFF          # flip a payload byte
        frames = self.scanner.feed(bytes(good))
        self.assertEqual(frames, [])
        self.assertEqual(self.scanner.stats.crc_failures, 1)
        self.assertEqual(self.scanner.stats.frames_ok, 0)

    def test_corrupted_crc_byte_is_rejected(self):
        good = bytearray(vectors.status("hello"))
        good[-1] ^= 0x01
        self.assertEqual(self.scanner.feed(bytes(good)), [])
        self.assertEqual(self.scanner.stats.crc_failures, 1)

    def test_stream_resynchronises_after_a_corrupted_packet(self):
        # This is the behaviour runbook step 8 requires: discard the bad
        # packet, do not wedge, pick the next one up.
        bad = bytearray(vectors.live_frame(GEO))
        bad[protocol.HEADER_BYTES + 40] ^= 0xFF
        frames = self.scanner.feed(bytes(bad) + vectors.hello())
        self.assertEqual(len(frames), 1)
        self.assertEqual(frames[0].packet_type, protocol.PacketType.HELLO)
        self.assertGreaterEqual(self.scanner.stats.crc_failures, 1)

    def test_corrupted_length_field_does_not_swallow_the_next_packet(self):
        # Resyncing by the DECLARED length would step over the good frame that
        # follows. Resyncing one byte at a time cannot.
        bad = bytearray(vectors.status("x" * 32))
        struct.pack_into("<H", bad, 3, 100)              # lie about the length
        frames = self.scanner.feed(bytes(bad) + vectors.hello()
                                   + vectors.view() + vectors.hello())
        # The good frames are all still recovered, in order, once enough bytes
        # exist to disprove the inflated length.
        self.assertEqual([f.packet_type for f in frames],
                         [protocol.PacketType.HELLO,
                          protocol.PacketType.VIEW,
                          protocol.PacketType.HELLO])
        self.assertEqual(self.scanner.stats.crc_failures, 1)

    def test_an_inflated_length_stalls_only_until_the_bytes_arrive(self):
        # HEAD-OF-LINE STALL, documented because it is real and bounded.
        #
        # A length field cannot be disproved without checking the CRC, and the
        # CRC cannot be checked until payload_length bytes have arrived. So a
        # corrupted length makes the scanner wait. The wait is bounded by
        # max_payload_bytes() - about 10 kB, ~217 ms at 460800 baud - and a
        # live link delivers that in a few frame periods. It self-heals; it
        # does not wedge. What must never happen is losing the good frames.
        bad = bytearray(vectors.status("x" * 16))
        struct.pack_into("<H", bad, 3, 4000)
        self.assertEqual(self.scanner.feed(bytes(bad)), [])      # stalled
        self.assertEqual(self.scanner.feed(vectors.hello()), []) # still short

        # Enough further traffic to exceed the phantom length, then recovery.
        recovered = self.scanner.feed(b"\x00" * 4000 + vectors.view())
        self.assertIn(protocol.PacketType.HELLO,
                      [f.packet_type for f in recovered])
        self.assertIn(protocol.PacketType.VIEW,
                      [f.packet_type for f in recovered])

    def test_absurd_length_is_rejected_without_buffering(self):
        absurd = struct.pack("<HBH", protocol.SYNC_WORD, 0x01, 0xFFFF)
        frames = self.scanner.feed(absurd + vectors.hello())
        self.assertEqual(len(frames), 1)
        self.assertEqual(frames[0].packet_type, protocol.PacketType.HELLO)
        self.assertEqual(self.scanner.stats.oversize_rejects, 1)

    def test_buffer_does_not_grow_without_bound_on_pure_noise(self):
        # 0x55 0xAA appears in float data all the time. A scanner that kept
        # every false sync alive would grow forever on a noisy line.
        for _ in range(200):
            self.scanner.feed(bytes([0x55, 0xAA, 0x01, 0xFF, 0xFF]))
        self.assertLess(self.scanner.buffered_bytes, 1024)

    # -- reconnect ----------------------------------------------------------

    def test_reset_drops_a_partial_frame_but_keeps_stats(self):
        stream = vectors.live_frame(GEO)
        self.scanner.feed(stream[:100])
        self.assertGreater(self.scanner.buffered_bytes, 0)

        self.scanner.reset()                              # link dropped
        self.assertEqual(self.scanner.buffered_bytes, 0)

        # The tail of the pre-drop frame must NOT combine with post-drop bytes.
        frames = self.scanner.feed(stream[100:] + vectors.hello())
        self.assertEqual([f.packet_type for f in frames],
                         [protocol.PacketType.HELLO])
        self.assertEqual(self.scanner.stats.frames_ok, 1)


if __name__ == "__main__":
    unittest.main()
