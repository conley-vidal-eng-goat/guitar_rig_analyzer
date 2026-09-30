"""UI tests. No display required — app.py is never imported here.

Two things are worth testing and they are different:

  1. THE GAP RULE. plotting.segments() must break a curve at every bin the
     instrument did not measure, and must never join across one. This is the
     defect protocol v2 exists to prevent (TODO-29: a flat, confident -24.0 dB
     curve that was entirely a clamp rail), so it gets adversarial tests and a
     test against the real 2026-09-27 RESULT, whose four finite bins of 512 are
     CONTIGUOUS (indices 22-25) and must come back as one four-point span.

  2. THE AUTHORITY RULE. model.Snapshot must pass Teensy verdicts through
     verbatim and must never manufacture one. Includes a test that UNKNOWN never
     degrades into a number, which is the failure mode the whole protocol is
     shaped around.
"""

from __future__ import annotations

import math
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from analyzer_link import protocol
from analyzer_link.state import View
from analyzer_ui import plotting
from analyzer_ui.engine import Engine
from analyzer_ui.model import UNKNOWN_TEXT
from analyzer_ui.sources import FixtureSource

REPO = pathlib.Path(__file__).resolve().parents[2]
RESULT_BIN = REPO / "ai" / "evidence" / "phase10-result-1khz.bin"
NAN = float("nan")


def ident(i):
    return float(i)


class TestAxes(unittest.TestCase):

    def test_linear_axis_maps_endpoints(self):
        a = plotting.LinearAxis(-90.0, 0.0, 100.0, 500.0)
        self.assertAlmostEqual(a.to_px(-90.0), 100.0)
        self.assertAlmostEqual(a.to_px(0.0), 500.0)
        self.assertAlmostEqual(a.to_px(-45.0), 300.0)

    def test_inverted_pixel_range_is_supported(self):
        """A dB axis is drawn with larger values HIGHER, i.e. smaller y."""
        a = plotting.LinearAxis(-42.0, 12.0, 400.0, 100.0)
        self.assertGreater(a.to_px(-42.0), a.to_px(12.0))

    def test_clamp_px_holds_inside_the_box_either_way_round(self):
        a = plotting.LinearAxis(-42.0, 12.0, 400.0, 100.0)
        self.assertEqual(a.clamp_px(-999.0), 400.0)
        self.assertEqual(a.clamp_px(+999.0), 100.0)

    def test_log_freq_axis_is_monotonic_and_decade_spaced(self):
        f = plotting.LogFreqAxis(20.0, 20000.0, 0.0, 300.0)
        self.assertAlmostEqual(f.to_px(20.0), 0.0)
        self.assertAlmostEqual(f.to_px(20000.0), 300.0)
        d1 = f.to_px(200.0) - f.to_px(20.0)
        d2 = f.to_px(2000.0) - f.to_px(200.0)
        self.assertAlmostEqual(d1, d2, places=6)

    def test_dc_and_out_of_range_are_reported_not_drawn(self):
        f = plotting.LogFreqAxis(20.0, 20000.0, 0.0, 300.0)
        self.assertFalse(f.in_range(0.0))
        self.assertFalse(f.in_range(21000.0))
        self.assertTrue(f.in_range(1000.0))


class TestFrequencyMapping(unittest.TestCase):
    """Geometry comes from HELLO. Hard-coding it is the fragility TODO-36 warns
    about, so the helpers derive everything from the reported values."""

    def test_bin_width_is_derived_from_reported_geometry(self):
        # 512 usable bins => 1024-point transform => 43.066 Hz per bin.
        self.assertAlmostEqual(plotting.bin_width_hz(44100, 512),
                               44100 / 1024, places=9)

    def test_bin_width_rejects_nonsense_geometry(self):
        with self.assertRaises(ValueError):
            plotting.bin_width_hz(44100, 0)

    def test_result_bin_zero_is_dc(self):
        self.assertEqual(plotting.result_bin_hz(0, 44100, 512), 0.0)

    def test_a_1khz_tone_lands_near_bin_23(self):
        w = plotting.bin_width_hz(44100, 512)
        self.assertEqual(round(1000.0 / w), 23)
        self.assertAlmostEqual(plotting.result_bin_hz(23, 44100, 512),
                               990.5, places=1)

    def test_live_bin_uses_the_centre_of_its_decimated_group(self):
        """Using the group's FIRST source bin would shift the curve left."""
        w = plotting.bin_width_hz(44100, 512)
        self.assertAlmostEqual(plotting.live_bin_hz(0, 44100, 512, 4),
                               1.5 * w, places=9)
        self.assertAlmostEqual(plotting.live_bin_hz(10, 44100, 512, 4),
                               41.5 * w, places=9)

    def test_live_and_result_agree_at_the_top_of_the_band(self):
        last_live = plotting.live_bin_hz(127, 44100, 512, 4)
        last_res = plotting.result_bin_hz(511, 44100, 512)
        self.assertLess(abs(last_live - last_res), 2 * plotting.bin_width_hz(44100, 512))


class TestPlottability(unittest.TestCase):

    def test_nan_and_infinities_are_not_plottable(self):
        self.assertFalse(plotting.is_plottable(NAN))
        self.assertFalse(plotting.is_plottable(float("inf")))
        self.assertFalse(plotting.is_plottable(float("-inf")))

    def test_ordinary_and_negative_values_are_plottable(self):
        self.assertTrue(plotting.is_plottable(-24.0))
        self.assertTrue(plotting.is_plottable(0.0))


class TestTheGapRule(unittest.TestCase):
    """*** The rule the whole module exists for. ***"""

    def test_a_clean_run_is_one_polyline(self):
        segs = plotting.segments([1.0, 2.0, 3.0], ident, lambda v: v)
        self.assertEqual(len(segs), 1)
        self.assertEqual(len(segs[0]), 3)

    def test_a_nan_splits_the_curve_and_is_never_bridged(self):
        segs = plotting.segments([1.0, 2.0, NAN, 4.0, 5.0], ident, lambda v: v)
        self.assertEqual(len(segs), 2)
        self.assertEqual([p[0] for p in segs[0]], [0.0, 1.0])
        self.assertEqual([p[0] for p in segs[1]], [3.0, 4.0])
        # The bridging failure, stated as an assertion: no polyline may contain
        # both sides of the gap.
        for seg in segs:
            xs = [p[0] for p in seg]
            self.assertFalse(1.0 in xs and 3.0 in xs)

    def test_an_isolated_valid_bin_is_a_one_point_span_not_a_line(self):
        segs = plotting.segments([NAN, 5.0, NAN], ident, lambda v: v)
        self.assertEqual(len(segs), 1)
        self.assertEqual(len(segs[0]), 1)

    def test_all_nan_yields_nothing_rather_than_a_flat_line_at_zero(self):
        """The failure this guards against is drawing zeros for 'no data'."""
        self.assertEqual(plotting.segments([NAN] * 8, ident, lambda v: v), [])

    def test_infinities_break_the_curve_too(self):
        segs = plotting.segments([1.0, float("inf"), 3.0], ident, lambda v: v)
        self.assertEqual(len(segs), 2)

    def test_leading_and_trailing_nans_do_not_create_empty_spans(self):
        segs = plotting.segments([NAN, NAN, 1.0, 2.0, NAN], ident, lambda v: v)
        self.assertEqual(len(segs), 1)
        self.assertEqual(len(segs[0]), 2)

    def test_x_of_index_returning_none_also_breaks_the_curve(self):
        """Used to drop DC, which has no place on a log-frequency axis."""
        def x_of(i):
            return None if i == 2 else float(i)
        segs = plotting.segments([1.0] * 5, x_of, lambda v: v)
        self.assertEqual(len(segs), 2)

    def test_the_plottable_veto_breaks_the_curve(self):
        """Clamped and pen-lift bins are vetoed even though the value is finite."""
        segs = plotting.segments([1.0] * 5, ident, lambda v: v,
                                 plottable=lambda i, _v: i != 2)
        self.assertEqual(len(segs), 2)

    def test_y_of_value_is_never_called_for_an_invalid_bin(self):
        """A y-mapper that cannot cope with NaN must never see one."""
        def strict_y(v):
            if not math.isfinite(v):
                raise AssertionError("y_of_value called with a non-finite value")
            return v
        plotting.segments([1.0, NAN, float("inf"), 4.0], ident, strict_y)


class _Cov:
    def __init__(self, clamped, valid, ratio):
        self.clamped, self.valid, self.ratio = clamped, valid, ratio


class TestCoverageContract(unittest.TestCase):
    """data_sender.h: clamped == ratio => draw a saturation marker, NOT the
    rail value. valid == 0 => pen-lift."""

    def test_a_fully_clamped_bin_is_reported_as_a_mark(self):
        cov = [_Cov(0, 4, 4), _Cov(4, 4, 4), _Cov(0, 4, 4)]
        marks = plotting.clamped_marks([-24.0] * 3, cov, ident, lambda v: v)
        self.assertEqual(marks, [(1.0, -24.0)])

    def test_a_partially_clamped_bin_is_not_marked(self):
        cov = [_Cov(2, 4, 4)]
        self.assertEqual(
            plotting.clamped_marks([-24.0], cov, ident, lambda v: v), [])

    def test_pen_lift_indices_are_the_zero_valid_bins(self):
        cov = [_Cov(0, 4, 4), _Cov(0, 0, 4), _Cov(0, 1, 4)]
        self.assertEqual(plotting.pen_lift_indices(cov), [1])

    def test_a_ratio_of_zero_never_counts_as_clamped(self):
        """Guards a divide-by-nothing reading 0 >= 0 as saturation."""
        cov = [_Cov(0, 0, 0)]
        self.assertEqual(
            plotting.clamped_marks([-24.0], cov, ident, lambda v: v), [])


class TestCensus(unittest.TestCase):

    def test_counts_match_replay_conventions(self):
        c = plotting.census([1.0, NAN, NAN, float("inf"), float("-inf")])
        self.assertEqual(c, {"elements": 5, "finite": 1, "nan": 2,
                             "pos_inf": 1, "neg_inf": 1})


class TestFixtureSource(unittest.TestCase):

    @unittest.skipUnless(RESULT_BIN.is_file(), "RESULT fixture not present")
    def test_non_realtime_delivers_everything_once(self):
        src = FixtureSource(RESULT_BIN, realtime=False)
        data = src.read()
        self.assertEqual(len(data), src.total_bytes)
        self.assertEqual(src.read(), b"")
        self.assertTrue(src.exhausted)

    @unittest.skipUnless(RESULT_BIN.is_file(), "RESULT fixture not present")
    def test_realtime_paces_and_does_not_overrun(self):
        src = FixtureSource(RESULT_BIN, realtime=True, bytes_per_sec=1000)
        first = src.read()
        self.assertLess(len(first), src.total_bytes)
        self.assertFalse(src.exhausted)


@unittest.skipUnless(RESULT_BIN.is_file(), "RESULT fixture not present")
class TestAgainstTheRealResult(unittest.TestCase):
    """End to end over the bytes a Teensy actually produced on 2026-09-27."""

    @classmethod
    def setUpClass(cls):
        cls.engine = Engine(FixtureSource(RESULT_BIN, realtime=False))
        cls.engine.pump()
        cls.snap = cls.engine.snapshot()

    def test_the_stack_decodes_the_capture_without_errors(self):
        self.assertEqual(self.engine.decode_failures, 0)
        self.assertEqual(self.engine.framing_stats.crc_failures, 0)
        self.assertEqual(self.engine.framing_stats.bytes_discarded_interior, 0)

    def test_teensy_authority_is_passed_through_verbatim(self):
        s = self.snap
        self.assertEqual(s.quality_text, "POOR")
        self.assertTrue(s.result.result_valid)
        self.assertEqual(s.result.n_averages_completed, 32)
        self.assertAlmostEqual(s.result.mean_coherence, 0.798961, places=5)
        self.assertEqual(len(s.result.insights), 4)
        self.assertFalse(s.result.calibration_applied)
        self.assertIn("CALIBRATION_MISSING", s.calibration_warning_names)
        self.assertEqual(s.session_text, "7")
        self.assertEqual(s.firmware_text, "0.6.0")
        self.assertEqual(s.state_text, "RESULT")
        self.assertIs(s.view, View.RESULT)

    def test_the_pi_reports_the_route_it_was_told_and_no_detectors(self):
        s = self.snap
        self.assertIs(s.return_source, protocol.ReturnSource.TS)
        self.assertFalse(s.detectors_available)
        self.assertEqual(s.warnings, ())

    def test_the_four_finite_bins_render_as_one_contiguous_span(self):
        """*** The headline case, and the fixture corrected my expectation. ***

        The real RESULT has FOUR finite magnitude bins of 512, and they are
        CONTIGUOUS: indices 22-25, 947.5-1076.7 Hz, straddling the 1 kHz
        stimulus. So the honest plot is ONE four-point span sitting on the tone
        — not four scattered dots, which is what this test first asserted, and
        not a 512-point line, which would be a fabrication.
        """
        s = self.snap
        geo = s.geometry
        cen = plotting.census(s.result.tf_cal_mag_db)
        self.assertEqual(cen["elements"], 512)
        self.assertEqual(cen["finite"], 4)
        self.assertEqual(cen["nan"], 508)

        fx = plotting.LogFreqAxis(20.0, 20000.0, 0.0, 600.0)

        def x_of(i):
            hz = plotting.result_bin_hz(i, geo.sample_rate, geo.fft_bins)
            return fx.to_px(hz) if fx.in_range(hz) else None

        segs = plotting.segments(s.result.tf_cal_mag_db, x_of, lambda v: v)
        self.assertEqual(len(segs), 1)
        self.assertEqual(len(segs[0]), 4)
        # It sits on the stimulus, not somewhere arbitrary.
        xs = [p[0] for p in segs[0]]
        self.assertTrue(all(fx.to_px(500.0) < x < fx.to_px(2000.0)
                            for x in xs), xs)
        # Pin the bins themselves, so a frequency-mapping regression is caught
        # rather than absorbed by a loose range check.
        finite_ix = [i for i, v in enumerate(s.result.tf_cal_mag_db)
                     if math.isfinite(v)]
        self.assertEqual(finite_ix, [22, 23, 24, 25])
        self.assertAlmostEqual(
            plotting.result_bin_hz(22, geo.sample_rate, geo.fft_bins),
            947.5, places=1)

    def test_every_finite_result_magnitude_is_sitting_on_the_clamp_rail(self):
        """All four are exactly -24.0 dB — the firmware's clamp rail.

        Recorded because it is the premise of the RESULT clamp gap below: these
        are rail values, and the RESULT packet carries nothing that says so.
        """
        vals = [v for v in self.snap.result.tf_cal_mag_db if math.isfinite(v)]
        self.assertEqual(vals, [-24.0, -24.0, -24.0, -24.0])

    def test_result_carries_no_per_bin_clamp_mask(self):
        """*** PROTOCOL GAP found by building this UI. ***

        LIVE_FRAME carries per-bin coverage nibbles and a frame-level
        tf_clamped_count (protocol v2, audit finding L1). RESULT carries
        NEITHER, so a receiver cannot tell a measured -24.0 dB from a railed
        one in a RESULT. That is TODO-29's defect class on the RESULT surface.
        Asserted here so the gap is a checked fact, and so this test fails —
        loudly and in the right place — if a future protocol revision closes it.
        """
        res = self.snap.result
        self.assertFalse(hasattr(res, "tf_clamped_count"))
        self.assertFalse(hasattr(res, "coverage"))
        # The live frame, by contrast, has both.
        self.assertTrue(hasattr(self.snap.live, "tf_clamped_count"))
        self.assertEqual(len(self.snap.live.coverage), 128)

    def test_group_delay_edges_stay_absent(self):
        """NaN at bins 0 and 511 is by design; they must not be plotted."""
        gd = self.snap.result.group_delay_ms
        self.assertTrue(math.isnan(gd[0]))
        self.assertTrue(math.isnan(gd[511]))
        segs = plotting.segments(gd, ident, lambda v: v)
        drawn = {p[0] for sg in segs for p in sg}
        self.assertNotIn(0.0, drawn)
        self.assertNotIn(511.0, drawn)

    def test_coherence_has_no_gaps_because_it_uses_zero_not_nan(self):
        """Per-array conventions are NOT uniform. Coherence is 0.0 for an
        unenergised bin, so its curve is continuous — and a receiver that
        'helpfully' treated 0.0 as missing would be wrong."""
        coh = self.snap.result.coherence
        self.assertEqual(plotting.census(coh)["nan"], 0)
        segs = plotting.segments(coh, ident, lambda v: v)
        self.assertEqual(len(segs), 1)
        self.assertEqual(len(segs[0]), 512)

    def test_live_tf_is_renderable_with_clamped_bins_marked_separately(self):
        live = self.snap.live
        self.assertIsNotNone(live)
        self.assertEqual(len(live.tf_db), 128)
        self.assertEqual(len(live.coverage), 128)
        clamped = [i for i, c in enumerate(live.coverage)
                   if c.ratio and c.clamped >= c.ratio]
        lifted = set(plotting.pen_lift_indices(live.coverage))
        # Measured on this fixture: 2 finite of 128, 126 pen-lift, 0 clamped.
        # A narrowband tone into a noise return really does leave almost the
        # whole live curve absent, and that is the correct picture.
        self.assertEqual(plotting.census(live.tf_db)["finite"], 2)
        self.assertEqual(len(lifted), 126)
        segs = plotting.segments(live.tf_db, ident, lambda v: v,
                                 plottable=lambda i, _v: (i not in lifted
                                                          and i not in clamped))
        # Whatever the counts, no span may contain a clamped or lifted bin.
        drawn = {int(p[0]) for sg in segs for p in sg}
        self.assertFalse(drawn & set(clamped))
        self.assertFalse(drawn & lifted)


class TestUnknownNeverBecomesZero(unittest.TestCase):
    """Before HELLO the Pi knows nothing and must say so."""

    def setUp(self):
        self.engine = Engine(FixtureSource.__new__(FixtureSource))
        # Build an engine with no source activity at all.
        from analyzer_ui.sources import ByteSource

        class Silent(ByteSource):
            name = "silent"

            def read(self):
                return b""

        self.engine = Engine(Silent())
        self.snap = self.engine.snapshot()

    def test_pre_hello_everything_reads_unknown_not_zero(self):
        s = self.snap
        self.assertFalse(s.session_established)
        self.assertIsNone(s.geometry)
        self.assertIsNone(s.session_id)
        self.assertEqual(s.session_text, UNKNOWN_TEXT)
        self.assertEqual(s.firmware_text, UNKNOWN_TEXT)
        self.assertEqual(s.state_text, UNKNOWN_TEXT)
        self.assertEqual(s.quality_text, UNKNOWN_TEXT)
        self.assertEqual(s.calibration_text, UNKNOWN_TEXT)

    def test_a_missing_level_is_none_and_renders_as_unknown(self):
        s = self.snap
        self.assertIsNone(s.source.dbfs)
        self.assertIsNone(s.returns.dbfs)
        self.assertEqual(s.source.text, UNKNOWN_TEXT)
        self.assertNotIn("0.0", s.source.text)

    def test_an_absent_link_is_reported_stale(self):
        self.assertTrue(self.snap.link_stale)


if __name__ == "__main__":
    unittest.main()
