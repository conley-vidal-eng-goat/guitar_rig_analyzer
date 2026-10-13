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
        self.assertIn('if (cls !== "MEASURED")', js)
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


if __name__ == "__main__":
    unittest.main()
