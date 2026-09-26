"""CRC-16/CCITT-FALSE conformance."""

import unittest

from analyzer_link.crc import crc16


class TestCrc16(unittest.TestCase):

    def test_published_check_vector(self):
        # The standard CRC-16/CCITT-FALSE check value for "123456789".
        # This is the one value that pins the parameter set down: init 0xFFFF,
        # poly 0x1021, MSB-first, no reflection, no final XOR. If the firmware
        # ever drifts to XMODEM (init 0x0000) or KERMIT (reflected), this fails.
        self.assertEqual(crc16(b"123456789"), 0x29B1)

    def test_empty_payload_is_the_init_value(self):
        self.assertEqual(crc16(b""), 0xFFFF)

    def test_single_bit_flip_changes_the_crc(self):
        base = bytes(range(64))
        flipped = bytearray(base)
        flipped[17] ^= 0x01
        self.assertNotEqual(crc16(base), crc16(bytes(flipped)))

    def test_result_is_always_16_bit(self):
        # The shift-and-mask loop must not let the register grow past 16 bits;
        # Python ints would happily do so and the CRC would silently diverge
        # from the firmware's uint16_t.
        for n in range(0, 300, 7):
            self.assertTrue(0 <= crc16(bytes([n % 256]) * n) <= 0xFFFF)
        self.assertTrue(0 <= crc16(bytes(range(256)) * 40) <= 0xFFFF)


if __name__ == "__main__":
    unittest.main()
