"""Tests for the shared presentation-semantics contract (ADR-005, TODO-68).

*** THESE RUN AGAINST BYTES A TEENSY PRODUCED, NOT AGAINST SYNTHESISED VECTORS. ***

The acceptance fixture is the pinned 2026-09-27 hardware RESULT: `tf_cal_mag_db`
has **4 finite bins of 512**, contiguous at indices 22-25 (~948-1077 Hz), and all
four read exactly -24.0 dB -- the firmware's clamp rail. That is the pathological
case the contract exists for, and it is proven here BEFORE any GPU work begins.

The shared-author evidence bound that applies to `tests/vectors.py` does not apply
to this file: these bytes were not authored by this repository.
"""

from __future__ import annotations

import math
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from analyzer_link import presentation_semantics as ps
from analyzer_link import protocol
from analyzer_link.packets import BinCoverage
from analyzer_ui.engine import Engine
from analyzer_ui.sources import FixtureSource

REPO = pathlib.Path(__file__).resolve().parents[2]
RESULT_BIN = REPO / "ai" / "evidence" / "phase10-result-1khz.bin"
IDLE_BIN = REPO / "ai" / "evidence" / "phase10-teensy-pi-idle-30s.bin"

BC = ps.BinClass


# =============================================================================
# THE CONTRACT, ON SYNTHETIC INPUT — rules stated in isolation
# =============================================================================

class TestClassificationRules(unittest.TestCase):

    def test_live_nan_is_unmeasured_never_zero(self):
        cov = [BinCoverage(clamped=0, valid=4, ratio=4)]
        b = ps.classify_live([float("nan")], cov)[0]
        self.assertIs(b.cls, BC.UNMEASURED)
        self.assertIs(b.reason, ps.Reason.NOT_FINITE)

    def test_live_pen_lift_outranks_a_finite_value(self):
        """valid == 0 means no energised source bin. Whatever number came with
        it is not a measurement, however finite it looks."""
        cov = [BinCoverage(clamped=0, valid=0, ratio=4)]
        b = ps.classify_live([-12.5], cov)[0]
        self.assertIs(b.cls, BC.UNMEASURED)
        self.assertIs(b.reason, ps.Reason.PEN_LIFT)

    def test_live_fully_clamped_is_clamped_and_keeps_its_value(self):
        cov = [BinCoverage(clamped=4, valid=4, ratio=4)]
        b = ps.classify_live([-24.0], cov)[0]
        self.assertIs(b.cls, BC.CLAMPED)
        self.assertEqual(b.value, -24.0)      # carried, not discarded
        self.assertFalse(b.cls.is_drawable_as_measurement)

    def test_live_half_clamped_group_is_measured_per_the_wire_contract(self):
        """*** The recorded decimation case (TODO-36, 2026-09-30). ***

        Source bins 22-25 are clamped; at 4:1 they land in live bins 5 and 6 as
        clamped=2, ratio=4. `data_sender.h` marks saturation only at
        clamped == ratio, so the firmware transmits these as data. This module
        reports what the wire says rather than second-guessing it -- but
        `partially_saturated` remains available so a renderer can show it.
        """
        cov = [BinCoverage(clamped=2, valid=4, ratio=4)]
        b = ps.classify_live([-24.0], cov)[0]
        self.assertIs(b.cls, BC.MEASURED)
        self.assertTrue(cov[0].partially_saturated)

    def test_result_finite_is_indeterminate_not_measured(self):
        b = ps.classify_result([-11.3])[0]
        self.assertIs(b.cls, BC.INDETERMINATE)
        self.assertIs(b.reason, ps.Reason.NO_CLAMP_METADATA)

    def test_indeterminate_is_never_inferred_from_the_value(self):
        """*** THE RULE THIS MODULE EXISTS TO HOLD. ***

        -24.0 (the rail) and -11.3 (not the rail) must classify IDENTICALLY.
        A value-sniffing implementation passes every other test in this file and
        fails this one. Classification reads metadata; it never reads magnitude.
        """
        rail = ps.classify_result([-24.0])[0]
        notrail = ps.classify_result([-11.3])[0]
        self.assertIs(rail.cls, notrail.cls)
        self.assertIs(rail.reason, notrail.reason)

    def test_closing_todo65_changes_evidence_not_contract(self):
        """When RESULT carries a clamp mask, the same bins classify concretely
        with no change to BinClass or to any renderer."""
        cov = [BinCoverage(clamped=4, valid=4, ratio=4),
               BinCoverage(clamped=0, valid=4, ratio=4)]
        got = ps.classify_result_with_coverage([-24.0, -6.0], cov)
        self.assertEqual([b.cls for b in got], [BC.CLAMPED, BC.MEASURED])


# =============================================================================
# RESAMPLING
# =============================================================================

class TestResamplingDoesNotManufactureCoverage(unittest.TestCase):

    def _live(self, specs):
        vals, cov = [], []
        for v, c, valid in specs:
            vals.append(v)
            cov.append(BinCoverage(clamped=c, valid=valid, ratio=4))
        return ps.classify_live(vals, cov)

    def test_all_unmeasured_sources_stay_unmeasured(self):
        bins = self._live([(float("nan"), 0, 0)] * 8)
        out = ps.resample(bins, 2, group_of=lambda i: i // 4)
        self.assertTrue(all(b.cls is BC.UNMEASURED for b in out))
        self.assertTrue(all(math.isnan(b.value) for b in out))

    def test_one_measured_among_three_absent_keeps_its_coverage(self):
        """It is MEASURED -- there IS a measurement here -- but a renderer is
        told it rests on 1 of 4 sources, so it cannot be drawn as confidently
        as a fully covered location."""
        bins = self._live([(-6.0, 0, 4), (float("nan"), 0, 0),
                           (float("nan"), 0, 0), (float("nan"), 0, 0)])
        out = ps.resample(bins, 1, group_of=lambda i: 0)[0]
        self.assertIs(out.cls, BC.MEASURED)
        self.assertEqual(out.coverage, 0.25)
        self.assertTrue(out.partial)
        self.assertEqual(out.value, -6.0)     # mean of MEASURED members only

    def test_clamped_sources_never_average_into_the_value(self):
        """A mean including a rail would be a fabricated number."""
        bins = self._live([(-6.0, 0, 4), (-24.0, 4, 4)])
        out = ps.resample(bins, 1, group_of=lambda i: 0)[0]
        self.assertIs(out.cls, BC.MEASURED)
        self.assertEqual(out.value, -6.0)
        self.assertEqual(out.clamped_count, 1)

    def test_clamped_only_group_is_clamped_not_measured(self):
        bins = self._live([(-24.0, 4, 4), (-24.0, 4, 4)])
        out = ps.resample(bins, 1, group_of=lambda i: 0)[0]
        self.assertIs(out.cls, BC.CLAMPED)

    def test_indeterminate_dominates_absence(self):
        """A group holding a present-but-unclassifiable value is unclassifiable.
        Reporting it as simple absence would hide that a value exists."""
        bins = ps.classify_result([float("nan"), -24.0, float("nan")])
        out = ps.resample(bins, 1, group_of=lambda i: 0)[0]
        self.assertIs(out.cls, BC.INDETERMINATE)

    def test_a_target_with_no_sources_is_unmeasured(self):
        bins = ps.classify_result([-1.0])
        out = ps.resample(bins, 3, group_of=lambda i: 0)
        self.assertIs(out[1].cls, BC.UNMEASURED)
        self.assertIs(out[1].reason, ps.Reason.NO_SOURCES)
        self.assertEqual(out[1].source_count, 0)


# =============================================================================
# ESTABLISHMENT (ADR-005 §5) — the same principle away from FFT bins
# =============================================================================

class TestEstablishment(unittest.TestCase):

    def test_a_selected_return_source_is_defined_never_established(self):
        """ADR-004: a return source is ALWAYS selected, so routing is always
        defined. Nothing in the packet observes the far end of the cable."""
        e = ps.route_establishment(protocol.ReturnSource.TS)
        self.assertIs(e, ps.Establishment.DEFINED)
        self.assertFalse(e.asserts_connection)

    def test_no_detector_is_unobservable_not_absent(self):
        """TODO-58: 'not present' is the wrong answer to 'is there a detector'."""
        e = ps.jack_establishment(protocol.Jack.RETURN_TS,
                                  presence_bits=0, available_bits=0)
        self.assertIs(e, ps.Establishment.UNOBSERVABLE)

    def test_availability_is_checked_before_presence(self):
        """A presence bit set with no detector fitted must not read ESTABLISHED;
        the firmware masks it, and the Pi must not undo that."""
        e = ps.jack_establishment(protocol.Jack.RETURN_TS,
                                  presence_bits=protocol.Jack.RETURN_TS,
                                  available_bits=0)
        self.assertIs(e, ps.Establishment.UNOBSERVABLE)

    def test_a_fitted_detector_reports_both_ways(self):
        j = protocol.Jack.RETURN_TS
        self.assertIs(ps.jack_establishment(j, presence_bits=j, available_bits=j),
                      ps.Establishment.ESTABLISHED)
        self.assertIs(ps.jack_establishment(j, presence_bits=0, available_bits=j),
                      ps.Establishment.ABSENT)


# =============================================================================
# THE REAL HARDWARE RESULT — the acceptance fixture
# =============================================================================

@unittest.skipUnless(RESULT_BIN.is_file(), "RESULT fixture not present")
class TestAgainstTheRealResult(unittest.TestCase):
    """2026-09-27, firmware 26f2bee, over the physical Teensy pin 1 -> Pi GPIO15."""

    @classmethod
    def setUpClass(cls):
        eng = Engine(FixtureSource(RESULT_BIN, realtime=False))
        eng.pump()
        cls.snap = eng.snapshot()
        cls.bins = ps.classify_result(cls.snap.result.tf_cal_mag_db)

    def test_the_pathological_shape_is_what_the_fixture_contains(self):
        c = ps.census(self.bins)
        self.assertEqual(c.elements, 512)
        self.assertEqual(c.indeterminate, 4)
        self.assertEqual(c.unmeasured, 508)
        self.assertEqual(c.measured, 0)
        self.assertEqual(c.clamped, 0)

    def test_not_one_of_512_bins_is_drawable_as_a_measurement(self):
        """*** THE HEADLINE. ***

        Four finite numbers exist. None may be drawn as data, because RESULT
        carries no clamp mask (TODO-65). A renderer that draws four confident
        points has asserted something the instrument never said.
        """
        self.assertEqual(sum(1 for b in self.bins
                             if b.cls.is_drawable_as_measurement), 0)

    def test_the_four_are_contiguous_at_22_to_25(self):
        ix = [b.index for b in self.bins if b.cls is BC.INDETERMINATE]
        self.assertEqual(ix, [22, 23, 24, 25])

    def test_all_four_sit_on_the_rail_and_that_changed_no_classification(self):
        """The -24.0 dB coincidence is reportable context for the operator. It
        is NOT a classification input -- every one of these was classified by
        the absence of a clamp mask, which is true of all 512."""
        vals = [b.value for b in self.bins if b.cls is BC.INDETERMINATE]
        self.assertEqual(vals, [-24.0] * 4)
        for b in self.bins:
            if b.cls is BC.INDETERMINATE:
                self.assertIs(b.reason, ps.Reason.NO_CLAMP_METADATA)

    def test_onto_a_48_segment_ring_nothing_becomes_measured(self):
        """The committed radial visuals resample 512 bins onto 48 segments. The
        ring must stay almost entirely dark. A surface mesh that interpolated
        across them would render 508 undefined locations as smooth terrain --
        which is what §4 of the ADR is about.

        NOTE: the grouping here is a deliberately naive linear one, because this
        test is about the RULE -- that nothing is promoted to MEASURED -- and a
        simple mapping keeps the rule legible. The production mapping is
        log-frequency and lives in `web/payload.py`; under it these same four
        bins straddle a band boundary and land on TWO bands, pinned by
        test_web_payload.test_each_of_the_four_source_bins_pins_to_an_exact_band.
        The counts differ; the rule does not.
        """
        ring = ps.resample(self.bins, 48, group_of=lambda i: min(i * 48 // 512, 47))
        c = ps.census(ring)
        self.assertEqual(c.measured, 0)
        self.assertEqual(c.indeterminate, 1)
        self.assertEqual(c.unmeasured, 47)

    def test_the_census_line_says_so_in_words(self):
        self.assertEqual(ps.census(self.bins).text(),
                         "512 bins · 0 measured · 4 indeterminate · 508 unmeasured")

    def test_coherence_has_no_nan_so_it_classifies_entirely_as_present(self):
        """Guard inherited from test_result_fixture: a receiver turning an
        unknown bin into 0.0 would show up as 512 non-NaN here AND as a
        suspiciously clean census elsewhere."""
        c = ps.census(ps.classify_result(self.snap.result.coherence))
        self.assertEqual(c.unmeasured, 0)
        self.assertEqual(c.indeterminate, 512)


@unittest.skipUnless(IDLE_BIN.is_file(), "idle fixture not present")
class TestAgainstTheRealLiveFrames(unittest.TestCase):
    """30 s of idle LIVE_FRAMEs, 2026-09-26. Nothing connected, so the honest
    classification of a live TF is near-total absence."""

    @classmethod
    def setUpClass(cls):
        eng = Engine(FixtureSource(IDLE_BIN, realtime=False))
        eng.pump()
        cls.snap = eng.snapshot()

    def test_a_live_frame_arrived_with_coverage_metadata(self):
        self.assertIsNotNone(self.snap.live)
        self.assertEqual(len(self.snap.live.coverage), 128)

    def test_idle_live_tf_classifies_as_absence_not_as_a_flat_curve(self):
        bins = ps.classify_live(self.snap.live.tf_db, self.snap.live.coverage)
        c = ps.census(bins)
        self.assertEqual(c.elements, 128)
        self.assertEqual(c.measured, 0)
        self.assertEqual(c.unmeasured, 128)

    def test_every_absence_is_attributed_to_a_metadata_rule(self):
        """Not merely 'unmeasured' -- each one names WHICH rule fired, so a
        regression that reclassified them would be visible, not silent."""
        bins = ps.classify_live(self.snap.live.tf_db, self.snap.live.coverage)
        reasons = {b.reason for b in bins}
        self.assertTrue(reasons <= {ps.Reason.PEN_LIFT, ps.Reason.NOT_FINITE})


# =============================================================================
# MAGNITUDE SPECTRA — fft_source[] / fft_return[]
# =============================================================================

class TestSpectrumClassification(unittest.TestCase):
    """A spectrum is NOT a transfer function, and the contract must not treat it
    like one.

    `tf_db` divides by the source, so it has a real pen-lift: below
    TF_SOURCE_GATE there is nothing to divide by. A magnitude has no denominator
    and no gate, so a quiet bin is a measurement of quietness. Blanking it would
    turn a measurement into absence -- the governing invariant broken in the
    direction that looks conservative and is not.
    """

    def test_a_finite_magnitude_is_measured(self):
        bins = ps.classify_spectrum([0.5, 0.001, 0.25])
        self.assertTrue(all(b.cls is ps.BinClass.MEASURED for b in bins))

    def test_zero_is_a_measurement_of_silence_not_an_absence(self):
        """The one that matters. Digital silence is a real reading."""
        bins = ps.classify_spectrum([0.0])
        self.assertIs(bins[0].cls, ps.BinClass.MEASURED)
        self.assertEqual(bins[0].value, 0.0)
        self.assertTrue(bins[0].cls.is_drawable_as_measurement)

    def test_nan_is_unmeasured(self):
        bins = ps.classify_spectrum([float("nan")])
        self.assertIs(bins[0].cls, ps.BinClass.UNMEASURED)
        self.assertIs(bins[0].reason, ps.Reason.NOT_FINITE)

    def test_a_spectrum_is_never_clamped_or_indeterminate(self):
        """No rail is applied to these arrays -- the clamp is on the TF. And a
        magnitude needs no metadata to be interpretable, so INDETERMINATE here
        would be the generic uncertainty bucket ADR-005 §6 forbids."""
        bins = ps.classify_spectrum([0.0, 1.0, 0.5, float("nan"), -0.0, 1e-30])
        for b in bins:
            self.assertNotIn(b.cls, (ps.BinClass.CLAMPED, ps.BinClass.INDETERMINATE))

    def test_the_sign_is_not_inspected(self):
        """A negative magnitude is physically impossible, and classification
        still must not judge it: reading the value to decide the class is
        TODO-29 wearing a new label. A decode fault is an error, not a class."""
        bins = ps.classify_spectrum([-0.3])
        self.assertIs(bins[0].cls, ps.BinClass.MEASURED)

    def test_it_takes_no_coverage_argument_at_all(self):
        """The nibbles are documented against tf_db alone. Making them
        unpassable is stronger than documenting that they must not be passed."""
        import inspect
        params = list(inspect.signature(ps.classify_spectrum).parameters)
        self.assertEqual(params, ["values"])


class TestPeakPreservingResample(unittest.TestCase):
    """The firmware decimates the live FFT by MAXIMUM and recorded why. The Pi
    reduces a SECOND time, and must not undo that at the display."""

    def test_the_firmwares_own_counterexample(self):
        """data_sender.h: 'one bin at 0.5 among three at 0.001 means 0.126, a
        12 dB under-report, which for a spectrum display is the wrong default'."""
        bins = ps.classify_spectrum([0.5, 0.001, 0.001, 0.001])
        peak = ps.resample_peak(bins, 1, group_of=lambda i: 0)
        self.assertAlmostEqual(peak[0].value, 0.5)

        mean = ps.resample(bins, 1, group_of=lambda i: 0)
        self.assertAlmostEqual(mean[0].value, 0.12575)
        self.assertGreater(
            20 * math.log10(peak[0].value / mean[0].value), 11.9,
            "the mean buries the peak by about 12 dB, as the firmware recorded")

    def test_resample_still_defaults_to_the_mean(self):
        """Changing the default would silently alter the transfer-function ring."""
        bins = ps.classify_spectrum([1.0, 3.0])
        self.assertAlmostEqual(
            ps.resample(bins, 1, group_of=lambda i: 0)[0].value, 2.0)

    def test_the_combining_rule_cannot_change_a_class(self):
        """combine() owns the class. No choice of value_of may manufacture
        coverage -- that separation is what makes the peak rule safe."""
        bins = ps.classify_spectrum([float("nan"), 0.4])
        for fn in (ps.resample, ps.resample_peak):
            out = fn(bins, 1, group_of=lambda i: 0)
            self.assertIs(out[0].cls, ps.BinClass.MEASURED)
            self.assertEqual(out[0].source_count, 2)
            self.assertEqual(out[0].measured_count, 1)
            self.assertAlmostEqual(out[0].coverage, 0.5)

    def test_a_group_with_nothing_measured_is_unmeasured_and_nan(self):
        bins = ps.classify_spectrum([float("nan"), float("nan")])
        out = ps.resample_peak(bins, 1, group_of=lambda i: 0)
        self.assertIs(out[0].cls, ps.BinClass.UNMEASURED)
        self.assertTrue(math.isnan(out[0].value))

    def test_a_target_with_no_sources_is_unmeasured(self):
        bins = ps.classify_spectrum([0.2])
        out = ps.resample_peak(bins, 2, group_of=lambda i: 0)
        self.assertIs(out[1].cls, ps.BinClass.UNMEASURED)
        self.assertIs(out[1].reason, ps.Reason.NO_SOURCES)


class TestSpectrumAgainstTheRealIdleCapture(unittest.TestCase):
    """Real bytes, 30 s idle, 2026-09-26. The contrast with the TF is the point:
    the same frame is 128/128 UNMEASURED as a transfer function and fully
    MEASURED as a spectrum, and both statements are correct."""

    @classmethod
    def setUpClass(cls):
        eng = Engine(FixtureSource(IDLE_BIN, realtime=False))
        eng.pump()
        cls.live = eng.snapshot().live

    def test_the_idle_spectrum_is_entirely_measured(self):
        c = ps.census(ps.classify_spectrum(self.live.fft_source))
        self.assertEqual(c.elements, 128)
        self.assertEqual(c.measured, 128)
        self.assertEqual(c.unmeasured, 0)

    def test_the_same_frame_is_total_absence_as_a_transfer_function(self):
        tf = ps.census(ps.classify_live(self.live.tf_db, self.live.coverage))
        self.assertEqual(tf.measured, 0)
        self.assertEqual(tf.unmeasured, 128)

    def test_no_bin_of_the_real_capture_is_nan(self):
        """Confirms the firmware reading: inv is a compile-time constant and the
        block only emits once the accumulator is full, so NaN is unreachable
        here. decimateMax's NaN handling is defensive, not a live signal."""
        for arr in (self.live.fft_source, self.live.fft_return):
            self.assertTrue(all(math.isfinite(v) for v in arr))

    def test_the_idle_spectrum_is_quiet_but_not_silent(self):
        """Reported, not asserted as a threshold: these are the real numbers a
        renderer has to put on an axis."""
        lo = min(self.live.fft_source)
        hi = max(self.live.fft_source)
        self.assertGreaterEqual(lo, 0.0)
        self.assertLess(hi, 1.0)


if __name__ == "__main__":
    unittest.main()
