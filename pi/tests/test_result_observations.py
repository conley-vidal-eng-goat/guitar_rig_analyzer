"""RESULT array reporting — analog observation, never a transport verdict.

The point of this reporting is that a one-shot hardware RESULT capture must not
arrive and then be under-analysed. A RESULT carries four float[512] arrays, and
before this existed the report touched none of them.

The governing rule every test here defends: **a structurally valid RESULT is a
successful transport result even when the numbers are worthless.** Quality
INVALID, every warning bit set, every applicable bin NaN -- still OK. The
question is whether the Teensy's authoritative result arrived intact.
"""

from __future__ import annotations

import json
import math
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "tools"))

from analyzer_link import protocol, packets
from analyzer_link.framing import FrameScanner
from replay import replay, _array_stats, _warning_names

from . import vectors

GEO = protocol.Geometry()
N = GEO.fft_bins


def stream_with_result(**kw) -> bytes:
    """A minimal stream that establishes a session then delivers one RESULT."""
    return (vectors.hello(session_id=9)
            + vectors.state(measurement_state=int(protocol.MeasurementState.RESULT))
            + vectors.result(GEO, **kw))


def obs(**kw) -> dict:
    r = replay(stream_with_result(**kw), seconds=2)
    assert r["transport_ok"], r["transport_problems"]
    return r["result_observations_not_a_verdict"]


class TestArrayCensus(unittest.TestCase):

    def test_all_four_arrays_are_512_elements(self):
        for a in obs()["arrays"]:
            with self.subTest(array=a["array"]):
                self.assertEqual(a["elements"], N)

    def test_array_length_is_not_fft_size(self):
        # MODE_PRECISION raises fft_size to 4096 while the result stays on the
        # canonical 512-bin grid. Conflating them mis-slices every array.
        o = obs(fft_size=4096)
        self.assertEqual(o["fft_size"], 4096)
        for a in o["arrays"]:
            self.assertEqual(a["elements"], 512)

    def test_finite_and_nan_counts_partition_the_array(self):
        for a in obs()["arrays"]:
            with self.subTest(array=a["array"]):
                self.assertEqual(
                    a["finite"] + a["nan"] + a["pos_inf"] + a["neg_inf"],
                    a["elements"],
                    "every element must fall in exactly one category")

    def test_the_firmware_nan_conventions_are_visible_and_differ(self):
        # Reading the four arrays as though they shared one policy would be
        # wrong. group_delay_ms is NaN at both edges by design; coherence uses
        # 0.0 rather than NaN for an unenergised bin.
        by = {a["array"]: a for a in obs()["arrays"]}
        self.assertGreaterEqual(by["group_delay_ms"]["nan"], 2,
                                "edge bins 0 and 511 are always NaN")
        self.assertEqual(by["coherence"]["nan"], 0,
                         "coherence uses 0.0, not NaN, for unenergised bins")
        self.assertEqual(by["tf_cal_mag_db"]["nan"], 1)
        self.assertEqual(by["tf_cal_phase_rad"]["nan"], 1)

    def test_min_max_never_incorporate_nan(self):
        mags = [1.0] * N
        mags[0] = math.nan
        mags[1] = -50.0
        mags[2] = 10.0
        by = {a["array"]: a for a in obs(tf_cal_mag_db=mags)["arrays"]}
        st = by["tf_cal_mag_db"]
        self.assertEqual(st["min"], -50.0)
        self.assertEqual(st["max"], 10.0)
        self.assertFalse(math.isnan(st["min"]))
        self.assertFalse(math.isnan(st["max"]))

    def test_an_all_nan_array_reports_no_finite_range(self):
        # A real possibility with no energised bins. min/max are None meaning
        # "no finite value exists", which is not the same as a value of zero.
        by = {a["array"]: a for a in
              obs(tf_cal_mag_db=[math.nan] * N)["arrays"]}
        st = by["tf_cal_mag_db"]
        self.assertEqual(st["nan"], N)
        self.assertEqual(st["finite"], 0)
        self.assertIsNone(st["min"])
        self.assertIsNone(st["max"])

    def test_infinities_are_counted_separately_from_finite(self):
        # The firmware guards every log10 and constrains H1_dB, so an Inf is
        # not expected to be producible. Counting it separately is precisely so
        # that if one ever appears it surfaces instead of hiding in "finite".
        vals = [1.0] * N
        vals[0] = math.inf
        vals[1] = -math.inf
        vals[2] = math.nan
        st = _array_stats("probe", vals)
        self.assertEqual(st["pos_inf"], 1)
        self.assertEqual(st["neg_inf"], 1)
        self.assertEqual(st["nan"], 1)
        self.assertEqual(st["finite"], N - 3)
        self.assertEqual(st["max"], 1.0, "min/max must exclude infinities")
        self.assertEqual(st["min"], 1.0)


class TestNoSilentConversion(unittest.TestCase):
    """The decoded values must stay exactly what the wire carried."""

    def test_decoded_result_keeps_real_nan_not_zero_or_none(self):
        scanner = FrameScanner()
        state_seen = None
        geo = None
        for f in scanner.feed(stream_with_result()):
            pkt = packets.decode(f, geo)
            if isinstance(pkt, packets.Hello):
                geo = pkt.geometry
            if isinstance(pkt, packets.Result):
                state_seen = pkt
        self.assertIsNotNone(state_seen)
        v = state_seen.tf_cal_mag_db[3]
        self.assertTrue(math.isnan(v), f"expected NaN, got {v!r}")
        self.assertIsNotNone(v, "NaN must not become None")
        self.assertNotEqual(v, 0.0, "NaN must not become 0.0")

    def test_coherence_zero_is_a_real_zero_not_a_missing_value(self):
        scanner, geo, res = FrameScanner(), None, None
        for f in scanner.feed(stream_with_result()):
            pkt = packets.decode(f, geo)
            if isinstance(pkt, packets.Hello):
                geo = pkt.geometry
            if isinstance(pkt, packets.Result):
                res = pkt
        self.assertEqual(res.coherence[3], 0.0)
        self.assertFalse(math.isnan(res.coherence[3]))

    def test_the_json_report_is_standards_compliant(self):
        # The authoritative decoded values contain NaN; the SERIALISED report
        # must not, because bare NaN is not legal JSON. The report carries
        # counts and finite extrema only, so this holds by construction --
        # asserted rather than assumed.
        r = replay(stream_with_result(), seconds=2)
        text = json.dumps(r, allow_nan=False)      # raises if NaN/Inf present
        self.assertNotIn("NaN", text)
        self.assertNotIn("Infinity", text)


class TestWarningBits(unittest.TestCase):

    def test_no_warnings(self):
        o = obs(calibration_warnings=0x00)
        self.assertEqual(o["calibration_warning_bits"], 0)
        self.assertEqual(o["calibration_warnings"], [])

    def test_single_warning_decodes_by_name(self):
        o = obs(calibration_warnings=0x01)
        self.assertEqual(o["calibration_warnings"], ["CALIBRATION_MISSING"])

    def test_multiple_warnings_all_decode(self):
        bits = (int(protocol.CalibrationWarning.CALIBRATION_MISSING)
                | int(protocol.CalibrationWarning.LINE_IN_LEVEL_MISMATCH)
                | int(protocol.CalibrationWarning.HARD_PARAMETER_MISMATCH))
        o = obs(calibration_warnings=bits)
        self.assertEqual(o["calibration_warning_bits"], bits)
        self.assertEqual(set(o["calibration_warnings"]),
                         {"CALIBRATION_MISSING", "LINE_IN_LEVEL_MISMATCH",
                          "HARD_PARAMETER_MISMATCH"})

    def test_all_five_warnings(self):
        bits = 0x1F
        self.assertEqual(len(_warning_names(bits)), 5)

    def test_raw_bits_are_reported_alongside_the_names(self):
        # The raw value is the wire fact; the names are a convenience. Both.
        o = obs(calibration_warnings=0x12)
        self.assertEqual(o["calibration_warning_bits"], 0x12)


class TestQualityNeverFailsTransport(unittest.TestCase):

    def test_invalid_quality_is_still_transport_ok(self):
        r = replay(stream_with_result(
            quality=int(protocol.ResultQuality.INVALID),
            result_valid=False), seconds=2)
        self.assertTrue(r["transport_ok"], r["transport_problems"])
        o = r["result_observations_not_a_verdict"]
        self.assertEqual(o["quality_grade"], "INVALID")
        self.assertFalse(o["result_valid"])

    def test_every_warning_set_and_every_array_nan_is_still_transport_ok(self):
        # The worst possible measurement that is nonetheless a structurally
        # complete RESULT. This is the case the RESULT experiment is most
        # likely to produce, with the jack loop disconnected.
        allnan = [math.nan] * N
        r = replay(stream_with_result(
            quality=int(protocol.ResultQuality.INVALID),
            result_valid=False, calibration_warnings=0x1F,
            tf_cal_mag_db=allnan, tf_cal_phase_rad=allnan,
            group_delay_ms=allnan), seconds=2)
        self.assertTrue(r["transport_ok"], r["transport_problems"])
        o = r["result_observations_not_a_verdict"]
        self.assertEqual(len(o["calibration_warnings"]), 5)
        for a in o["arrays"][:3]:
            self.assertEqual(a["nan"], N)
            self.assertIsNone(a["min"])

    def test_clipping_is_reported_not_judged(self):
        r = replay(stream_with_result(flags=0x01), seconds=2)
        self.assertTrue(r["transport_ok"])
        self.assertTrue(r["result_observations_not_a_verdict"]["clip_detected"])


class TestSizesAndStructure(unittest.TestCase):

    def test_payload_and_framed_sizes_are_reported(self):
        o = obs()
        expected = protocol.result_payload_bytes(N, 0)
        self.assertEqual(o["payload_bytes"], expected)
        self.assertEqual(o["framed_bytes"], expected + protocol.FRAMING_BYTES)
        self.assertEqual(o["framed_bytes"], 8356)

    def test_insights_change_the_size_and_the_count(self):
        entries = [vectors.insight_entry(0, 0, 1000.0, -3.0, "t", "d")] * 3
        o = obs(insights=entries)
        self.assertEqual(o["insight_count"], 3)
        self.assertEqual(o["payload_bytes"],
                         protocol.result_payload_bytes(N, 3))

    def test_a_malformed_result_length_is_still_rejected(self):
        # The existing decoder guard must not be weakened by the new reporting.
        payload = bytearray(vectors.result_payload(GEO))
        bad = bytes(payload[:-10])
        with self.assertRaises(packets.DecodeError):
            packets.decode_result(bad, GEO)

    def test_no_result_means_no_result_section(self):
        r = replay(vectors.hello(session_id=1) + vectors.state(), seconds=1)
        self.assertNotIn("result_observations_not_a_verdict", r)


if __name__ == "__main__":
    unittest.main()
