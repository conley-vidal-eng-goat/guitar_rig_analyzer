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


class TestCaptureScriptGuards(unittest.TestCase):
    """Regression guards for the two integration defects found on 2026-09-26.

    Both cost bench time and neither was a code bug in the usual sense: one was
    a terminal-settings default that made a failed capture look like a link
    result, the other a Pi 5 device-naming change. Structural tests are the
    only thing that keeps either from being quietly reintroduced.
    """

    def setUp(self):
        self.src = (pathlib.Path(__file__).resolve().parents[1]
                    / "tools" / "capture.sh").read_text()
        # Join shell line-continuations, so a command split across lines is
        # matched as the single command the shell actually runs.
        self.joined = self.src.replace("\\\n", " ")

    def test_stty_blocks_until_data_arrives(self):
        # `min 0 time 1` lets a no-data read return immediately, so cat exits
        # and a 30 s request finishes in ~1 s reporting 0 bytes -- which is
        # indistinguishable from a dead link unless you check the clock.
        self.assertRegex(self.joined, r"stty[^\n]*min 1 time 0")

    def test_the_broken_setting_is_not_used_in_any_stty_invocation(self):
        import re
        self.assertEqual(
            re.findall(r"stty[^\n]*min 0 time 1", self.joined), [],
            "capture.sh must not configure `min 0 time 1` -- see the comment "
            "block above the stty line.")

    def test_capture_verifies_it_actually_ran_for_the_requested_duration(self):
        # The defect produced a plausible-looking failure report from a capture
        # that never ran. A short capture is a tooling fault and must fail
        # loudly rather than be read as a link measurement.
        #
        # This asserts the CONDITIONAL, not prose: an earlier version of this
        # test only looked for the words "TOOLING fault", which a comment
        # satisfied -- so deleting the actual check left the test green. A
        # structural test that a comment can satisfy is not a structural test.
        self.assertRegex(
            self.joined,
            r'if\s*\[\s*"\$ELAPSED"\s*-lt[^\]]*\]',
            "capture.sh must compare elapsed time against the requested "
            "duration and fail when short.")
        self.assertRegex(self.joined, r"exit 2",
                         "a short capture must exit non-zero")

    def test_zero_bytes_after_a_full_run_exits_non_zero(self):
        # Distinct from the short-capture case: this one DID run to completion,
        # so it is a real observation -- but it still must not be mistaken for
        # a successful capture by a caller checking only the exit status.
        self.assertRegex(self.joined, r'if\s*\[\s*"\$BYTES"\s*-eq 0\s*\]')
        self.assertRegex(self.joined, r"exit 3")

    def test_zero_bytes_points_at_the_device_trap_before_the_wiring(self):
        # On this hardware /dev/serial0 -> ttyAMA10 received nothing while the
        # header UART was /dev/ttyAMA0, with a healthy 3.3 V waveform visible
        # on the scope at the Pi pin. Diagnosis went to the wiring first.
        self.assertIn("ttyAMA0", self.src)
        self.assertIn("raspi-gpio get 14,15", self.src)

    def test_refuses_to_overwrite_an_existing_capture(self):
        self.assertIn("refusing to overwrite", self.src)
