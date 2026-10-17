"""The UI transport payload (TODO-67 slice 1), against real recorded bytes.

The browser renders whatever this produces, so the boundary is only as good as
these assertions. The central one is `test_no_band_carries_a_value_it_may_not_draw`:
if a value reaches the browser for a band that is not MEASURED, the renderer has
something to draw a bar from, and the contract has a hole in it.
"""

from __future__ import annotations

import json
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from analyzer_ui.engine import Engine
from analyzer_ui.sources import FixtureSource
from web import payload

REPO = pathlib.Path(__file__).resolve().parents[2]
RESULT_BIN = REPO / "ai" / "evidence" / "phase10-result-1khz.bin"
IDLE_BIN = REPO / "ai" / "evidence" / "phase10-teensy-pi-idle-30s.bin"
STATIC = pathlib.Path(__file__).resolve().parents[1] / "web" / "static"


def _snap(path):
    eng = Engine(FixtureSource(path, realtime=False))
    eng.pump()
    return eng.snapshot()


class TestBandMapping(unittest.TestCase):

    def test_dc_has_no_place_on_a_log_ring(self):
        """Folding DC into the lowest band would file a 0 Hz value under 20 Hz."""
        self.assertIsNone(payload.band_of_hz(0.0))

    def test_out_of_range_is_dropped_not_clamped_to_an_edge_band(self):
        self.assertIsNone(payload.band_of_hz(10.0))
        self.assertIsNone(payload.band_of_hz(24000.0))

    def test_the_ring_spans_20hz_to_20khz(self):
        self.assertEqual(payload.band_of_hz(20.0), 0)
        self.assertEqual(payload.band_of_hz(20000.0), 47)

    def test_a_1khz_tone_lands_just_below_the_middle_of_the_ring(self):
        self.assertEqual(payload.band_of_hz(947.5), 26)


@unittest.skipUnless(RESULT_BIN.is_file(), "RESULT fixture not present")
class TestRealResultPayload(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        s = _snap(RESULT_BIN)
        cls.p = payload.result_payload(s.result, s.geometry)

    def test_the_source_census_is_preserved_exactly(self):
        """*** THE ACCEPTANCE TARGET. *** The reduction to 48 bands is a
        presentation step; it must not restate what the instrument measured."""
        c = self.p["census_source"]
        self.assertEqual((c["elements"], c["measured"], c["clamped"],
                          c["indeterminate"], c["unmeasured"]),
                         (512, 0, 0, 4, 508))

    def test_the_ring_aggregates_without_promoting_anything(self):
        c = self.p["census_bands"]
        self.assertEqual(c["elements"], 48)
        self.assertEqual(c["measured"], 0)
        self.assertEqual(c["clamped"], 0)
        self.assertEqual(c["indeterminate"], 2)
        self.assertEqual(c["unmeasured"], 46)

    def test_no_band_carries_a_value_it_may_not_draw(self):
        """*** THE BOUNDARY. *** Only MEASURED may carry a number. Anything else
        hands the renderer something to build a bar from."""
        for seg in self.p["segments"]:
            if seg["cls"] != "MEASURED":
                self.assertIsNone(seg["value"], f"band {seg['i']} leaked a value")

    def test_the_rail_value_never_reaches_the_browser(self):
        """-24.0 appears nowhere in the payload. The four bins hold it; the
        contract says they are not establishable, so the number is withheld."""
        self.assertNotIn("-24.0", str(self.p["segments"]))

    def test_the_two_live_bands_straddle_1khz(self):
        live = [s for s in self.p["segments"] if s["cls"] != "UNMEASURED"]
        self.assertEqual([s["i"] for s in live], [26, 27])
        self.assertTrue(all(s["cls"] == "INDETERMINATE" for s in live))
        self.assertLess(live[0]["hz"], 1000.0)
        self.assertGreater(live[1]["hz"], 1000.0)

    def test_each_of_the_four_source_bins_pins_to_an_exact_band(self):
        """*** THE EVIDENCE ANCHOR. ***

        The four finite RESULT bins are 22-25, and the log ring splits them 1/3
        across bands 26 and 27. That is why the screenshot shows TWO markers
        where a naive linear 512->48 grouping would show one.

        It is also FRAGILE and that is the point of pinning it. The 26/27
        boundary is 973.94 Hz: bin 22 sits 25.5 Hz below it and bin 23 sits
        17.5 Hz above. Any change to F_LO, F_HI or the band count moves the
        boundary across those bins and silently relabels the evidence that a
        committed screenshot shows. This test makes that change loud.
        """
        sr, fft = 44100, 512
        expected = {22: 26, 23: 27, 24: 27, 25: 27}
        for b, band in expected.items():
            hz = b * (sr / (2.0 * fft))
            self.assertEqual(payload.band_of_hz(hz), band,
                             f"source bin {b} ({hz:.2f} Hz) moved off band {band}")
        self.assertAlmostEqual(
            payload.F_LO * 10 ** (payload._LOG_SPAN * 27 / 48), 973.9351, places=3)

    def test_the_four_source_bins_are_accounted_for_across_those_bands(self):
        live = [s for s in self.p["segments"] if s["cls"] != "UNMEASURED"]
        self.assertEqual(sum(s["counts"]["indeterminate"] for s in live), 4)

    def test_teensy_authority_is_carried_verbatim(self):
        a = self.p["authority"]
        self.assertEqual(a["result_quality"], "POOR")
        self.assertEqual(a["n_averages_completed"], 32)
        self.assertTrue(a["result_valid"])
        self.assertFalse(a["calibration_applied"])

    def test_the_payload_exposes_no_raw_arrays_to_classify_from(self):
        """A browser cannot re-derive a class it was never given the evidence
        for: no coverage nibbles, no raw TF array, no NaN.

        Teensy-authored verdicts like `result_valid` ARE carried -- verbatim,
        for printing. Carrying a verdict is the contract working; carrying the
        raw material to recompute one is the hole.
        """
        import json
        blob = json.dumps(self.p)
        for leaked in ("tf_cal_mag_db", "tf_db", "coverage_nibble",
                       "NaN", "Infinity"):
            self.assertNotIn(leaked, blob)
        # Nothing in the payload is a 512-element array.
        def arrays(o):
            if isinstance(o, list):
                yield o
                for v in o:
                    yield from arrays(v)
            elif isinstance(o, dict):
                for v in o.values():
                    yield from arrays(v)
        self.assertTrue(all(len(a) <= 48 for a in arrays(self.p)))

    def test_the_payload_is_strict_json(self):
        """NaN would serialise as a bare `NaN` literal, which JSON.parse rejects
        -- and a renderer coping with it would be coping with absence as a
        number. Absence is carried as null, by class, never as a value."""
        import json
        json.loads(json.dumps(self.p, allow_nan=False))


@unittest.skipUnless(IDLE_BIN.is_file(), "idle fixture not present")
class TestRealLivePayload(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        s = _snap(IDLE_BIN)
        cls.p = payload.live_payload(s.live, s.geometry)

    def test_an_idle_rig_renders_as_a_completely_empty_ring(self):
        c = self.p["census_bands"]
        self.assertEqual(c["measured"], 0)
        self.assertEqual(c["indeterminate"], 0)
        self.assertEqual(c["unmeasured"], 48)

    def test_not_one_band_carries_a_value(self):
        self.assertTrue(all(s["value"] is None for s in self.p["segments"]))

    def test_live_frames_never_produce_indeterminate(self):
        """LIVE_FRAME carries full per-bin coverage, so every band resolves."""
        self.assertFalse(any(s["cls"] == "INDETERMINATE"
                             for s in self.p["segments"]))


class TestNoBrowserMeasurementPath(unittest.TestCase):
    """Guards the boundary at its weakest point: a future contributor adding
    'just a quick mic input' to make the demo livelier. VortexTunnel.jsx is
    excluded from production for exactly this reason (ADR-005 §9)."""

    BANNED = ("getUserMedia", "AudioContext", "webkitAudioContext",
              "createAnalyser", "AnalyserNode", "mediaDevices",
              "getFloatFrequencyData", "getByteFrequencyData")

    def test_no_audio_acquisition_api_appears_in_the_client(self):
        for f in sorted(STATIC.glob("*.js")) + sorted(STATIC.glob("*.html")):
            src = f.read_text()
            code = "\n".join(l for l in src.splitlines()
                             if not l.strip().startswith("//"))
            for banned in self.BANNED:
                self.assertNotIn(banned, code, f"{f.name} references {banned}")

    def test_the_client_has_exactly_one_data_source(self):
        main = (STATIC / "main.js").read_text()
        self.assertEqual(main.count("fetch("), 1)
        self.assertIn('fetch("/api/frame"', main)

    def test_the_renderer_draws_nothing_for_unmeasured(self):
        js = (STATIC / "fingerprint_split.js").read_text()
        self.assertIn('b.src_cls === "MEASURED"', js)
        self.assertIn("HIDDEN", js)


class TestSpectraOnTheWire(unittest.TestCase):
    """The reviewed FFT contract, at the payload boundary, on real idle bytes."""

    @classmethod
    def setUpClass(cls):
        snap = _snap(IDLE_BIN)
        cls.live_raw = snap.live
        cls.out = payload.live_payload(snap.live, snap.geometry)
        cls.sp = cls.out["spectra"]
        cls.result = payload.result_payload(*(lambda s: (s.result, s.geometry))(_snap(RESULT_BIN)))

    def test_a_result_carries_no_spectrum(self):
        """RESULT has no fft arrays. Inventing an empty one would imply it does."""
        self.assertNotIn("spectra", self.result)

    def test_the_unit_and_reference_are_stated_not_assumed(self):
        self.assertEqual(self.sp["unit"], "linear_magnitude")
        self.assertEqual(self.sp["reference"], 1.0)
        self.assertIn("NOT dBFS", self.sp["reference_note"])
        self.assertIn("NOT been calibrated", self.sp["reference_note"])

    def test_the_payload_never_claims_dbfs_for_a_spectrum(self):
        """peak_source_dbfs is a time-domain peak and lives elsewhere; the
        spectrum must not borrow its unit."""
        blob = json.dumps(self.sp)
        self.assertNotIn("dbfs", blob.lower().replace("not dbfs", ""))

    def test_there_is_no_second_resample(self):
        """One point per transmitted bin. The firmware already decimated by
        MAXIMUM to preserve narrow peaks."""
        n = len(self.live_raw.fft_source)
        self.assertEqual(len(self.sp["src"]), n)
        self.assertEqual(len(self.sp["ret"]), n)
        self.assertEqual(len(self.sp["geometry"]), n)

    def test_bin_zero_spans_dc_and_says_so(self):
        g = self.sp["geometry"]
        self.assertTrue(g[0]["dc"])
        self.assertEqual(g[0]["lo_hz"], 0.0)
        self.assertEqual([x["i"] for x in g if x["dc"]], [0],
                         "exactly one bin spans DC")

    def test_the_spans_are_the_real_transmitted_bin_edges(self):
        """44100 Hz, 512 bins -> 43.0664 Hz per source bin, decimated 4:1."""
        g = self.sp["geometry"]
        self.assertAlmostEqual(g[0]["hi_hz"], 150.73, places=1)
        self.assertAlmostEqual(g[1]["lo_hz"], 150.73, places=1)
        self.assertAlmostEqual(g[1]["hi_hz"], 323.0, places=1)
        self.assertAlmostEqual(g[-1]["hi_hz"], 22028.47, places=1)
        for a, b in zip(g, g[1:]):
            self.assertAlmostEqual(a["hi_hz"], b["lo_hz"], places=2,
                                   msg="spans must tile without gaps or overlap")

    def test_nothing_is_measured_below_the_first_usable_bin(self):
        """Coverage starts above 150 Hz -- ABOVE a low-E fundamental at 82 Hz.
        The payload must not imply otherwise."""
        first = next(x for x in self.sp["geometry"] if not x["dc"])
        self.assertGreater(first["lo_hz"], 82.41)

    def test_an_exact_zero_is_forwarded_as_a_measurement(self):
        """The real idle capture holds three. Zero magnitude is a measurement of
        silence, so it must arrive as 0.0 and not as null."""
        zeros = [pt for pt in self.sp["src"] if pt["value"] == 0.0]
        self.assertEqual(len(zeros), 3)
        for pt in zeros:
            self.assertEqual(pt["cls"], "MEASURED")

    def test_every_idle_bin_is_measured(self):
        self.assertEqual(self.sp["census_src"]["measured"], 128)
        self.assertEqual(self.sp["census_src"]["unmeasured"], 0)

    def test_the_transfer_function_in_the_same_frame_is_total_absence(self):
        """The contrast is the point, and it is in one payload."""
        self.assertEqual(self.out["census_source"]["measured"], 0)
        self.assertEqual(self.out["census_source"]["unmeasured"], 128)

    def test_the_payload_is_strict_json(self):
        """allow_nan=False: absence can never arrive as NaN."""
        json.dumps(self.out, allow_nan=False)


# =============================================================================
# TEENSY-AUTHORED DETAIL: insights, capture provenance, calibration state
# =============================================================================
#
# These assertions exist because the browser is now the surface an operator
# reads this instrument through. Every value below was authored on the Teensy;
# the only thing being tested is that the transport did not change it, lose it,
# invent it, or attach a unit to it that the wire never carried.


@unittest.skipUnless(RESULT_BIN.is_file(), "RESULT fixture not present")
class TestInsightsAreForwardedNotAuthored(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        s = _snap(RESULT_BIN)
        cls.result = s.result
        cls.p = payload.result_payload(s.result, s.geometry)

    def test_every_authored_insight_reaches_the_browser(self):
        """Four on the pinned capture. None dropped, none added, same order."""
        self.assertEqual(len(self.p["insights"]), 4)
        self.assertEqual(len(self.p["insights"]), len(self.result.insights))

    def test_title_and_detail_are_byte_for_byte_what_the_teensy_wrote(self):
        for sent, got in zip(self.result.insights, self.p["insights"]):
            self.assertEqual(got["title"], sent.title)
            self.assertEqual(got["detail"], sent.detail)

    def test_a_detail_truncated_by_the_sender_is_not_repaired(self):
        """`data_sender` cuts detail to char[64] mid-word. Completing it here
        would make this file a co-author of a measurement statement."""
        detail = self.p["insights"][1]["detail"]
        self.assertEqual(detail, "Results show raw hardware TF \u2014 channel "
                                 "asymmetry is not remov")
        self.assertFalse(detail.endswith("removed."))

    def test_mode_and_severity_are_carried_by_name_not_by_number(self):
        """MEASUREMENT vs ADVISORY must stay distinguishable in any renderer
        (protocol.InsightMode). An integer would invite a renderer to compare
        or sort it; a name can only be printed or matched."""
        for got in self.p["insights"]:
            self.assertIn(got["mode"], ("MEASUREMENT", "ADVISORY"))
            self.assertIn(got["severity"], ("INFO", "WARNING", "ALERT"))

    def test_severity_is_the_teensys_grade_and_is_not_re_derived(self):
        """The ALERT belongs to 'Measurement quality' because the firmware
        graded it from result_quality, not because its magnitude is largest."""
        got = self.p["insights"]
        self.assertEqual([g["severity"] for g in got],
                         [i.severity.name for i in self.result.insights])
        self.assertEqual(got[0]["severity"], "ALERT")
        self.assertEqual(got[0]["title"], "Measurement quality")

    def test_a_broadband_insight_is_not_given_a_frequency_of_zero_hz(self):
        """insights_engine.h:115 -- "Relevant frequency, or 0 if broadband".
        All four on this capture are broadband. '@ 0 Hz' is a location the
        instrument never claimed."""
        for got in self.p["insights"]:
            self.assertIsNone(got["frequency_hz"])

    def test_the_not_applicable_magnitude_sentinel_becomes_absence(self):
        """0.0 is overloaded (insights_engine.h:116). The two insights that
        carry no magnitude must not read as a measured zero."""
        got = self.p["insights"]
        self.assertIsNone(got[1]["magnitude"])      # No calibration applied
        self.assertIsNone(got[2]["magnitude"])      # Advisory unavailable

    def test_a_real_magnitude_survives(self):
        self.assertAlmostEqual(self.p["insights"][3]["magnitude"], -24.0)

    def test_the_magnitude_slot_is_not_always_db(self):
        """*** THE REASON THE PAYLOAD KEY IS NOT `magnitude_db`. ***

        insights_engine.cpp:170 passes `r.mean_coherence` into the struct's
        `magnitude_db` field for the quality insight. The value below is a
        dimensionless coherence, and a renderer printing it as "0.80 dB" would
        be asserting a unit that was never transmitted.
        """
        got = self.p["insights"][0]
        self.assertEqual(got["title"], "Measurement quality")
        self.assertAlmostEqual(got["magnitude"], self.result.mean_coherence)
        self.assertAlmostEqual(got["magnitude"], 0.79896, places=5)
        self.assertNotIn("magnitude_db", got)

    def test_the_unit_is_only_ever_stated_in_the_teensys_own_prose(self):
        """Both numbers are restated, with their correct units, inside the
        authored detail strings -- which is why withholding an ambiguous
        numeric field loses nothing."""
        self.assertIn("Coherence: 0.80", self.p["insights"][0]["detail"])
        self.assertIn("-24.0 dB", self.p["insights"][3]["detail"])

    def test_an_empty_insight_list_is_a_statement_not_a_missing_field(self):
        """`insight_count` is an explicit wire byte and packets.py validates it
        against the payload length, so a Result with no insights means the
        instrument authored none. The key is always present; a renderer may
        therefore say "none authored" and can never say it for missing data."""
        import dataclasses
        none_authored = dataclasses.replace(self.result, insights=())
        s = _snap(RESULT_BIN)
        p = payload.result_payload(none_authored, s.geometry)
        self.assertIn("insights", p)
        self.assertEqual(p["insights"], [])

    def test_nothing_in_the_browser_payload_can_author_an_insight(self):
        """The PER-BIN arrays an insight would have to be computed from are
        still absent, so the browser cannot synthesise one even if asked to.

        Checked as keys, not as substrings. "coherence" legitimately occurs
        twice in this payload -- as `mean_coherence`, a scalar verdict the
        Teensy graded and the transport has always carried, and inside the
        authored prose "Coherence: 0.80". Neither lets anything be recomputed.
        Step C will add classified coherence; until then these stay absent.
        """
        def keys(o):
            if isinstance(o, dict):
                for k, v in o.items():
                    yield k
                    yield from keys(v)
            elif isinstance(o, list):
                for v in o:
                    yield from keys(v)

        present = set(keys(self.p))
        for leaked in ("coherence", "group_delay_ms", "tf_cal_phase_rad",
                       "tf_cal_mag_db", "S_xx_db", "S_yy_db"):
            self.assertNotIn(leaked, present)
        self.assertIn("mean_coherence", present)


@unittest.skipUnless(RESULT_BIN.is_file(), "RESULT fixture not present")
class TestCaptureProvenance(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        s = _snap(RESULT_BIN)
        cls.result = s.result
        cls.p = payload.result_payload(s.result, s.geometry)

    def test_the_conditions_of_the_capture_are_carried_verbatim(self):
        c = self.p["capture"]
        self.assertEqual(c["estimator"], "H1")
        self.assertEqual(c["stimulus"], "EXTERNAL")
        self.assertEqual(c["fft_mode"], "MODE_LIVE")
        self.assertEqual(c["window_function"], "HANN")
        self.assertEqual(c["fft_size"], 1024)
        self.assertEqual(c["timestamp_ms"], 225178)
        self.assertEqual((c["capture_start_block"], c["capture_end_block"]),
                         (77308, 77580))
        self.assertEqual((c["source_node_ch"], c["return_node_ch"]), (0, 1))
        self.assertEqual(c["line_in_level"], 5)

    def test_fft_size_is_not_the_array_length(self):
        """packets.py: fft_size is the FFT length actually used; the spectra are
        always fft_bins long. Confusing them misreports the resolution."""
        self.assertEqual(self.p["capture"]["fft_size"], 1024)
        self.assertEqual(self.p["source_bins"], 512)

    def test_line_in_level_is_present_because_audit_R6_requires_it(self):
        """Without it a receiver A/Bs two captures taken at different input
        gains and presents the difference as a rig difference."""
        self.assertIn("line_in_level", self.p["capture"])

    def test_clipping_is_reported_as_counts_and_as_the_teensys_own_flag(self):
        c = self.p["capture"]
        self.assertEqual((c["clip_source_count"], c["clip_return_count"]), (0, 0))
        self.assertIs(c["clip_detected"], False)
        self.assertIs(c["clip_detected"], bool(self.result.clip_detected))

    def test_enums_are_names_so_a_renderer_cannot_do_arithmetic_on_them(self):
        c = self.p["capture"]
        for key in ("estimator", "stimulus", "fft_mode", "window_function"):
            self.assertIsInstance(c[key], str)

    def test_the_instruments_own_coverage_grade_is_carried(self):
        """valid_bin_fraction is the Teensy saying it established 2% of the
        analysis band. The Pi must never recompute it from the ring census."""
        self.assertAlmostEqual(self.p["authority"]["valid_bin_fraction"],
                               self.result.valid_bin_fraction)
        self.assertAlmostEqual(self.p["authority"]["valid_bin_fraction"],
                               0.017467, places=6)


@unittest.skipUnless(RESULT_BIN.is_file(), "RESULT fixture not present")
class TestCalibrationState(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        s = _snap(RESULT_BIN)
        cls.p = payload.result_payload(s.result, s.geometry)

    def test_the_warning_bits_are_expanded_to_names(self):
        self.assertEqual(self.p["calibration"]["warnings"],
                         ["CALIBRATION_MISSING"])

    def test_the_provenance_string_is_the_firmwares_own_words(self):
        self.assertEqual(self.p["calibration"]["provenance"],
                         "none \u2014 no calibration loaded")

    def test_the_calibration_type_is_carried_even_when_none_was_applied(self):
        """INTERNAL_LOOPBACK names the slot, not a calibration that ran. The
        renderer needs both this and authority.calibration_applied to say
        anything true, which is why neither is dropped."""
        self.assertEqual(self.p["calibration"]["type"], "INTERNAL_LOOPBACK")
        self.assertFalse(self.p["authority"]["calibration_applied"])

    def test_calibration_applied_is_not_duplicated_into_the_new_block(self):
        """One field, one home: two copies can desync under a later edit."""
        self.assertNotIn("applied", self.p["calibration"])


@unittest.skipUnless(IDLE_BIN.is_file(), "idle fixture not present")
class TestLiveFlagsReachTheBrowser(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        s = _snap(IDLE_BIN)
        cls.live = s.live
        cls.p = payload.live_payload(s.live, s.geometry)

    def test_the_clip_flags_are_carried(self):
        """A clip invalidates a reading while the reading still looks
        plausible, so it must travel beside the peaks it qualifies."""
        a = self.p["authority"]
        self.assertIs(a["source_clip"], False)
        self.assertIs(a["return_clip"], False)
        self.assertIs(a["source_clip"], bool(self.live.source_clip))
        self.assertIs(a["return_clip"], bool(self.live.return_clip))

    def test_a_false_clip_flag_is_a_statement_not_an_absence(self):
        """False means the instrument reported no clipping. It must be a
        boolean, never null and never missing, or a renderer cannot tell
        "no clip" from "not reported"."""
        for key in ("source_clip", "return_clip", "tf_persistence_active"):
            self.assertIsInstance(self.p["authority"][key], bool)

    def test_tf_persistence_is_carried_because_it_qualifies_the_tf(self):
        self.assertIs(self.p["authority"]["tf_persistence_active"], True)

    def test_the_block_counter_is_carried_as_the_only_freshness_signal(self):
        self.assertEqual(self.p["authority"]["output_block_number"],
                         self.live.output_block_number)

    def test_a_result_payload_carries_no_live_flags(self):
        """Peak levels and clip flags are LIVE_FRAME fields. A RESULT has none,
        and the last live value must not be shown as if it were part of it."""
        s = _snap(RESULT_BIN)
        rp = payload.result_payload(s.result, s.geometry)
        for key in ("source_clip", "return_clip", "peak_source_dbfs",
                    "output_block_number"):
            self.assertNotIn(key, rp["authority"])


@unittest.skipUnless(RESULT_BIN.is_file(), "RESULT fixture not present")
class TestBackwardCompatibility(unittest.TestCase):
    """*** THE EXISTING RENDERERS MUST NOT NOTICE THIS COMMIT. ***

    LIVE, TONE and the fingerprint read the payload by key name. Every key that
    shipped before the insight/provenance work is pinned here by name and by
    type, so a later tidy-up cannot rename or re-type one without failing.
    """

    @classmethod
    def setUpClass(cls):
        rs = _snap(RESULT_BIN)
        cls.rp = payload.result_payload(rs.result, rs.geometry)
        ls = _snap(IDLE_BIN)
        cls.lp = payload.live_payload(ls.live, ls.geometry)

    def test_the_result_top_level_keys_are_a_superset_of_what_shipped(self):
        for key in ("kind", "bands", "source_bins", "census_source",
                    "census_bands", "segments", "authority"):
            self.assertIn(key, self.rp)
        self.assertEqual(self.rp["kind"], "result")

    def test_the_live_top_level_keys_are_a_superset_of_what_shipped(self):
        for key in ("kind", "spectra", "bands", "source_bins", "census_source",
                    "census_bands", "segments", "authority"):
            self.assertIn(key, self.lp)
        self.assertEqual(self.lp["kind"], "live")

    def test_the_original_result_authority_fields_are_unchanged(self):
        a = self.rp["authority"]
        self.assertEqual(a["firmware_version"], "0.6.0")
        self.assertIs(a["result_valid"], True)
        self.assertEqual(a["result_quality"], "POOR")
        self.assertEqual(a["n_averages_completed"], 32)
        self.assertIsInstance(a["mean_coherence"], float)
        self.assertIs(a["calibration_applied"], False)

    def test_the_original_live_authority_fields_are_unchanged(self):
        a = self.lp["authority"]
        self.assertIsInstance(a["peak_source_dbfs"], float)
        self.assertIsInstance(a["peak_return_dbfs"], float)
        self.assertIsInstance(a["tf_confidence"], float)
        self.assertIsInstance(a["tf_clamped_count"], int)
        self.assertEqual(a["measurement_state"], "IDLE")

    def test_the_ring_the_fingerprint_draws_is_untouched(self):
        """TONE reads segments[] and the two censuses. Byte-identical shape."""
        self.assertEqual(len(self.rp["segments"]), 48)
        self.assertEqual(len(self.lp["segments"]), 48)
        for seg in self.rp["segments"] + self.lp["segments"]:
            self.assertEqual(set(seg), {"i", "hz", "cls", "value",
                                        "coverage", "sources", "counts"})

    def test_the_spectra_live_reads_are_untouched(self):
        sp = self.lp["spectra"]
        self.assertEqual(set(sp), {"unit", "reference", "reference_note",
                                   "nyquist_hz", "geometry", "src", "ret",
                                   "census_src", "census_ret"})
        self.assertEqual(len(sp["src"]), 128)

    def test_a_result_still_carries_no_spectrum(self):
        self.assertNotIn("spectra", self.rp)

    def test_both_payloads_are_still_strict_json(self):
        json.loads(json.dumps(self.rp, allow_nan=False))
        json.loads(json.dumps(self.lp, allow_nan=False))

    def test_no_new_field_is_a_512_element_array(self):
        """The no-raw-arrays guard, restated over the enlarged payload: the
        browser still cannot reconstruct a per-bin class from what it is sent.
        insights is bounded by insights_max (12)."""
        def arrays(o):
            if isinstance(o, list):
                yield o
                for v in o:
                    yield from arrays(v)
            elif isinstance(o, dict):
                for v in o.values():
                    yield from arrays(v)
        self.assertTrue(all(len(a) <= 48 for a in arrays(self.rp)))
        self.assertTrue(all(len(a) <= 128 for a in arrays(self.lp)))



if __name__ == "__main__":
    unittest.main()


# =============================================================================
# TONE — input over level-matched return (2026-10-16)
# =============================================================================

import math as _math
import re as _re
import types as _types

from analyzer_link import presentation_semantics as _ps

_GEO = _types.SimpleNamespace(sample_rate=44100, fft_bins=512, decim_ratio=4)


def _spec(levels_db, n=128, rest_db=-80.0):
    """A classified spectrum: {bin: dB}, every other bin at rest_db."""
    vals = [10 ** (rest_db / 20.0)] * n
    for i, db in levels_db.items():
        vals[i] = 10 ** (db / 20.0)
    return _ps.classify_spectrum(vals)


def _tone(src, ret, matcher=None, block=1):
    est = payload.frame_gain_db(src, ret)
    m = matcher or payload.GainMatcher()
    g, st = m.update(est, block)
    return payload.tone_block(src, ret, _GEO, gain_db=g, gain_state=st,
                              gain_bins=est.bins, gain_bound_db=est.bound_db)


class TestToneFloor(unittest.TestCase):

    def test_the_tone_floor_is_the_firmware_gate(self):
        """The floor is the Teensy's own "energised" level, not a number chosen
        on the Pi. If TF_SOURCE_GATE moves, this must fail."""
        cfg = (REPO / "config.h").read_text()
        m = _re.search(r"#define\s+TF_SOURCE_GATE\s+([\d.]+)f?", cfg)
        self.assertIsNotNone(m)
        self.assertAlmostEqual(payload.TONE_FLOOR_DB,
                               20 * _math.log10(float(m.group(1))), places=6)

    def test_bin_zero_is_never_on_the_tone_ring(self):
        """It spans DC; it read -53 dB with the strings muted on 2026-10-16."""
        self.assertEqual(payload.TONE_FIRST_BIN, 1)
        t = _tone(_spec({0: -20.0}), _spec({0: -20.0}))
        self.assertNotIn(0, [b["i"] for b in t["bins"]])
        self.assertEqual(t["census"]["input_on"], 0)

    def test_the_ring_ends_in_the_guitar_range(self):
        t = _tone(_spec({}), _spec({}))
        self.assertEqual(len(t["bins"]), 16)
        self.assertLess(t["bins"][-1]["hi_hz"], 3000.0)


class TestToneOnRealBytes(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        s = _snap(IDLE_BIN)
        cls.p = payload.live_payload(s.live, s.geometry)

    def test_an_idle_rig_lights_nothing(self):
        c = self.p["tone"]["census"]
        self.assertEqual((c["input_on"], c["return_on"], c["rig_only"]), (0, 0, 0))
        self.assertEqual(self.p["tone"]["gain_state"], "none")
        self.assertIsNone(self.p["tone"]["gain_db"])

    def test_the_tone_block_is_strict_json(self):
        json.dumps(self.p["tone"], allow_nan=False)


class TestToneGainMatch(unittest.TestCase):

    def test_a_flat_6db_loss_reads_minus_6_and_matches_exactly(self):
        lv = {1: -38.0, 2: -40.0, 3: -45.0, 4: -50.0}
        src = _spec(lv)
        ret = _spec({i: db - 6.0 for i, db in lv.items()})
        t = _tone(src, ret)
        self.assertEqual(t["gain_state"], "live")
        self.assertAlmostEqual(t["gain_db"], -6.0, places=2)
        for b in t["bins"][:4]:
            self.assertAlmostEqual(b["ret_matched_db"], b["src_db"], places=2)
            self.assertTrue(b["ret_on"])

    def test_matching_never_lifts_the_analysers_own_floor_into_view(self):
        """2026-10-16, replayed: input -38..-58 dB, return -65..-78 dB in every
        bin. The first version reported a confident -28 dB 'gain' and drew a
        return bar on all 46 sections. The return was not energised."""
        src = _spec({1: -38.0, 2: -38.4, 3: -44.3, 4: -50.0, 5: -57.6})
        ret = _spec({}, rest_db=-72.0)
        t = _tone(src, ret)
        self.assertEqual(t["gain_state"], "below_floor")
        self.assertIsNone(t["gain_db"])
        self.assertLess(t["gain_bound_db"], 0.0)
        self.assertEqual(t["census"]["return_on"], 0)
        self.assertEqual(t["census"]["rig_only"], 0)

    def test_the_bound_is_strict(self):
        """Every return bin is under the floor F, so the power ratio is under
        k·F²/Σsrc². Check against the actual ratio of what was sent."""
        lv = {1: -38.0, 2: -41.0, 3: -47.0}
        src = _spec(lv)
        ret = _spec({}, rest_db=-61.0)
        est = payload.frame_gain_db(src, ret)
        actual = 10 * _math.log10(sum(10 ** (-61.0 / 10) for _ in lv)
                                  / sum(10 ** (db / 10) for db in lv.values()))
        self.assertGreater(est.bound_db, actual)

    def test_rig_only_is_return_energy_with_no_input_under_it(self):
        lv = {1: -38.0, 2: -40.0, 3: -45.0}
        src = _spec(lv)
        ret = _spec({**lv, 12: -45.0})
        t = _tone(src, ret)
        rig = [b["i"] for b in t["bins"] if b["rig_only"]]
        self.assertEqual(rig, [12])

    def test_silence_holds_the_last_gain_and_says_so(self):
        lv = {1: -38.0, 2: -40.0, 3: -45.0}
        m = payload.GainMatcher()
        _tone(_spec(lv), _spec({i: d - 10 for i, d in lv.items()}), m, block=1)
        t = _tone(_spec({}), _spec({}), m, block=2)
        self.assertEqual(t["gain_state"], "held")
        self.assertAlmostEqual(t["gain_db"], -10.0, places=2)

    def test_the_gain_advances_per_instrument_frame_not_per_poll(self):
        """Two polls of the same block must not smooth twice."""
        m = payload.GainMatcher()
        a = _spec({1: -38.0, 2: -40.0, 3: -45.0})
        _tone(a, _spec({1: -48.0, 2: -50.0, 3: -55.0}), m, block=1)   # -10
        once = _tone(a, _spec({1: -38.0, 2: -40.0, 3: -45.0}), m, block=2)["gain_db"]
        again = _tone(a, _spec({1: -38.0, 2: -40.0, 3: -45.0}), m, block=2)["gain_db"]
        self.assertAlmostEqual(once, again, places=6)
        self.assertAlmostEqual(once, -8.0, places=2)                   # 0.2 of the way

    def test_a_bound_neither_holds_nor_overwrites_an_established_gain(self):
        m = payload.GainMatcher()
        lv = {1: -38.0, 2: -40.0, 3: -45.0}
        _tone(_spec(lv), _spec({i: d - 3 for i, d in lv.items()}), m, block=1)
        t = _tone(_spec(lv), _spec({}, rest_db=-75.0), m, block=2)
        self.assertEqual(t["gain_state"], "below_floor")
        self.assertIsNone(t["gain_db"])
        self.assertAlmostEqual(m.gain_db, -3.0, places=2)


class TestToneIsAdditive(unittest.TestCase):

    def test_the_tf_ring_is_still_there_for_anything_that_reads_it(self):
        s = _snap(IDLE_BIN)
        p = payload.live_payload(s.live, s.geometry)
        self.assertIn("segments", p)
        self.assertIn("tone", p)

    def test_a_result_has_no_tone_block(self):
        """RESULT carries no spectra, so there is no input or return to draw."""
        rs = _snap(RESULT_BIN)
        self.assertNotIn("tone", payload.result_payload(rs.result, rs.geometry))
