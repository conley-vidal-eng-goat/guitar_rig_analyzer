"""The replay harness: what it counts, and what it refuses to fail on."""

import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "tools"))

from analyzer_link import protocol
from replay import replay

from . import vectors

GEO = protocol.Geometry()


def idle_stream(seconds=2, session_id=1):
    out = bytearray()
    for tick in range(seconds * 2):
        for _ in range(11):
            out += vectors.live_frame(GEO, state=0, block=tick)
        out += vectors.state(measurement_state=0)
        if tick % 2 == 0:
            out += vectors.hello(session_id=session_id)
            out += vectors.router_status()
    return bytes(out)


class TestReplay(unittest.TestCase):

    def test_clean_idle_capture_passes(self):
        r = replay(idle_stream(), seconds=2)
        self.assertTrue(r["transport_ok"], r["transport_problems"])
        self.assertEqual(r["framing"]["crc_failures"], 0)
        self.assertEqual(r["receiver"]["measurement_state"], "IDLE")
        self.assertEqual(r["receiver"]["hello_session_ids"], [1])

    def test_all_four_detectors_report_unknown(self):
        r = replay(idle_stream(), seconds=2)
        self.assertEqual(
            r["router"]["detectors"],
            {"INSTRUMENT_IN": "unknown", "RIG_SEND": "unknown",
             "RETURN_TS": "unknown", "RETURN_XLR": "unknown"})
        self.assertFalse(r["router"]["any_detector_available"])

    def test_session_id_zero_is_handled_normally(self):
        # The first hardware boot produced session 0. A receiver that treated
        # it as "absent" would report no session established.
        r = replay(idle_stream(session_id=0), seconds=2)
        self.assertTrue(r["receiver"]["session_established"])
        self.assertEqual(r["receiver"]["hello_session_ids"], [0])
        self.assertTrue(r["transport_ok"])

    def test_mid_stream_start_is_not_a_problem(self):
        r = replay(idle_stream()[900:], seconds=2)
        self.assertTrue(r["transport_ok"], r["transport_problems"])
        self.assertGreater(r["receiver"]["geometry_unavailable"], 0)

    def test_corruption_is_reported_as_a_transport_problem(self):
        raw = bytearray(idle_stream())
        raw[5000] ^= 0xFF
        r = replay(bytes(raw), seconds=2)
        self.assertFalse(r["transport_ok"])
        self.assertTrue(any("CRC" in p for p in r["transport_problems"]))

    def test_unknown_packet_type_is_flagged(self):
        r = replay(idle_stream() + vectors.unknown(0xFE, b"x" * 8), seconds=2)
        self.assertFalse(r["transport_ok"])
        self.assertIn("0xfe", r["unknown_types"])

    def test_a_capture_with_no_hello_fails(self):
        raw = b"".join(vectors.live_frame(GEO, state=0) for _ in range(5))
        r = replay(raw, seconds=1)
        self.assertFalse(r["transport_ok"])
        self.assertTrue(any("no HELLO" in p for p in r["transport_problems"]))

    def test_analog_content_never_fails_the_transport(self):
        # The 2026-09-26 lesson: a prediction of near-full TF clamping was
        # wrong by 512 bins on a completely healthy link. Analog observations
        # are reported, never judged.
        r = replay(idle_stream(), seconds=2)
        self.assertIn("tf_clamped_count", r["analog_observations_not_a_verdict"])
        self.assertTrue(r["transport_ok"])

    def test_session_change_mid_capture_is_flagged(self):
        r = replay(idle_stream(session_id=1) + idle_stream(session_id=2),
                   seconds=4)
        self.assertFalse(r["transport_ok"])
        self.assertTrue(any("session id changed" in p
                            for p in r["transport_problems"]))


if __name__ == "__main__":
    unittest.main()
