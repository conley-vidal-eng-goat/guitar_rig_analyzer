"""LAB diagnostics (pi/web/lab.py and static/lab_dash.js).

Two halves, as elsewhere in this suite:

  * ARITHMETIC. Each statistic is checked against a signal whose answer is
    known exactly: a flat gain must read as no EQ and no brightness shift, a
    tilt must read as that tilt, a 2:1 peak relationship must fit slope 0.5.
    A statistic that cannot recover a planted answer says nothing about a rig.

  * BOUNDARY. The browser half draws only. It may not take a logarithm, sum,
    fit or fetch, because then "the Pi computed this" stops being checkable.
"""

from __future__ import annotations

import math
import pathlib
import re
import unittest

from analyzer_link import presentation_semantics as ps
from analyzer_link import protocol
from web import lab

STATIC = pathlib.Path(__file__).resolve().parents[1] / "web" / "static"
GEO = protocol.Geometry()
N = GEO.live_bins


def _guitarish(scale: float = 1.0):
    """A falling spectrum: loud low bins, quiet top, all above the gate up to bin 40."""
    return [scale * 0.1 / (i + 1) if i <= 40 else 1e-5 for i in range(N)]


def _spec(vals):
    return ps.classify_spectrum(vals)


def _auth(block, pin=-12.0, pout=-12.0, **kw):
    a = {"output_block_number": block, "peak_source_dbfs": pin,
         "peak_return_dbfs": pout, "source_clip": False, "return_clip": False}
    a.update(kw)
    return a


class TestOneFrame(unittest.TestCase):

    def test_a_flat_gain_is_no_eq_and_no_brightness_change(self):
        src = _guitarish()
        ret = [v * 2.0 for v in src]                     # +6.02 dB, flat
        fr = lab.frame_lab(_spec(src), _spec(ret), GEO, shift=20 * math.log10(2.0))
        both = [d for c, d in zip(fr["cells"], fr["delta_db"]) if c == "B"]
        self.assertGreater(len(both), 10)
        for d in both:
            self.assertAlmostEqual(d, 0.0, places=1)
        self.assertAlmostEqual(fr["delta"]["centroid_cents"], 0.0, places=0)
        self.assertAlmostEqual(fr["delta"]["tilt_db_oct"], 0.0, places=1)

    def test_a_planted_tilt_is_recovered(self):
        """Return = input x (f/f0)^(t/6.02): exactly t dB per octave more."""
        src = _guitarish()
        hz = [lab.payload.spectrum_geometry(GEO, N)[i]["hz"] for i in range(N)]
        t = 3.0
        ret = [v * (max(hz[i], 1.0) / 1000.0) ** (t / 20.0 / math.log10(2.0))
               for i, v in enumerate(src)]
        fr = lab.frame_lab(_spec(src), _spec(ret), GEO, shift=0.0)
        self.assertAlmostEqual(fr["delta"]["tilt_db_oct"], t, delta=0.3)
        self.assertGreater(fr["delta"]["centroid_cents"], 0.0)

    def test_silence_establishes_nothing(self):
        quiet = [1e-5] * N
        fr = lab.frame_lab(_spec(quiet), _spec(quiet), GEO, shift=0.0)
        self.assertIsNone(fr["input"])
        self.assertIsNone(fr["return"])
        self.assertEqual(fr["delta"], {})
        self.assertIsNone(fr["added_pct"])
        self.assertEqual(set(fr["cells"]), {"q"})

    def test_rig_only_energy_is_counted_as_added(self):
        src = _guitarish()
        ret = list(src)
        ret[80] = 0.01                                   # input has nothing there
        fr = lab.frame_lab(_spec(src), _spec(ret), GEO, shift=0.0)
        self.assertEqual(fr["cells"][80 - lab.FIRST_BIN], "R")
        self.assertGreater(fr["added_pct"], 0.0)

    def test_an_unmeasured_bin_is_never_given_a_difference(self):
        src = _guitarish()
        ret = list(src)
        ret[5] = float("nan")
        fr = lab.frame_lab(_spec(src), _spec(ret), GEO, shift=0.0)
        k = 5 - lab.FIRST_BIN
        self.assertEqual(fr["cells"][k], "u")
        self.assertIsNone(fr["delta_db"][k])

    def test_dc_is_not_on_the_lab_axis(self):
        ax = lab.axis(GEO, N)
        self.assertEqual(ax["bins"][0]["i"], lab.FIRST_BIN)
        self.assertTrue(all(0.0 <= b["x0"] <= b["x1"] <= 1.0 for b in ax["bins"]))


class TestRunning(unittest.TestCase):

    def _feed(self, t, block, src, ret, *, energised=True, **auth):
        fr = lab.frame_lab(_spec(src), _spec(ret), GEO, shift=0.0)
        t.feed(fr, _spec(src), _spec(ret), _auth(block, **auth), energised=energised)

    def test_a_repeated_block_is_not_counted_twice(self):
        t = lab.LabTracker()
        src = _guitarish()
        for _ in range(4):
            self._feed(t, 7, src, src)
        self.assertEqual(t.frames_seen, 1)

    def test_clipped_frames_are_excluded_from_every_statistic(self):
        t = lab.LabTracker()
        src = _guitarish()
        for b in range(30):
            self._feed(t, b, src, src, pin=-10.0 - b * 0.5, pout=-1.0, return_clip=True)
        self.assertEqual(t.frames_clipped, 30)
        self.assertEqual(t.eq(N - 1)["frames"], 0)
        self.assertEqual(t.dynamics()["n"], 0)
        self.assertEqual(t.smooth, {})

    def test_the_eq_signature_recovers_a_planted_boost(self):
        t = lab.LabTracker()
        src = _guitarish()
        ret = list(src)
        ret[10] *= 10 ** (6.0 / 20.0)                    # +6 dB in one band
        for b in range(20):
            self._feed(t, b, src, ret)
        eq = t.eq(N - 1)
        k = 10 - lab.FIRST_BIN
        others = [v for i, v in enumerate(eq["db"]) if v is not None and i != k]
        # Matched: the boost minus the overall change it caused.
        self.assertGreater(eq["db"][k] - max(others), 5.0)

    def test_dynamics_fits_a_planted_two_to_one(self):
        t = lab.LabTracker()
        src = _guitarish()
        for b in range(40):
            pin = -40.0 + b
            self._feed(t, b, src, src, pin=pin, pout=-20.0 + 0.5 * (pin + 40.0))
        d = t.dynamics()
        self.assertAlmostEqual(d["slope"], 0.5, places=3)
        self.assertAlmostEqual(d["r2"], 1.0, places=3)

    def test_dynamics_refuses_a_narrow_span(self):
        t = lab.LabTracker()
        src = _guitarish()
        for b in range(40):
            self._feed(t, b, src, src, pin=-20.0 + (b % 3) * 0.5, pout=-20.0)
        d = t.dynamics()
        self.assertIsNone(d["slope"])
        self.assertIn("span", d["why"])

    def test_unplayed_frames_do_not_move_the_headline_numbers(self):
        t = lab.LabTracker()
        src = _guitarish()
        self._feed(t, 1, src, src, energised=False)
        self.assertEqual(t.smooth, {})

    def test_idle_noise_is_measured_only_with_the_strings_silent(self):
        t = lab.LabTracker()
        quiet_in = [1e-5] * N
        noisy_out = [1e-4] * N                           # +20 dB over the input
        for b in range(lab.IDLE_SETTLE + 10):
            self._feed(t, b, quiet_in, noisy_out, energised=False)
        idle = t.idle()
        self.assertAlmostEqual(idle["excess_db"], 20.0, places=1)
        self.assertEqual(idle["frames"], 10)        # the first IDLE_SETTLE are not counted

    def test_a_decay_tail_is_not_counted_as_self_noise(self):
        """Pi, 2026-10-18: a rig's gain lifts a fading note back over the gate,
        and those frames read +30 dB of 'noise'. Only settled silence counts."""
        t = lab.LabTracker()
        quiet_in = [1e-5] * N
        noisy_out = [1e-4] * N
        b = 0
        for _ in range(5):                               # play, then a short gap
            self._feed(t, b, _guitarish(), _guitarish()); b += 1
            for _ in range(lab.IDLE_SETTLE):
                self._feed(t, b, quiet_in, noisy_out, energised=False); b += 1
        self.assertIsNone(t.idle()["excess_db"])

    def test_a_return_at_full_scale_is_not_fitted_as_compression(self):
        """Pi, 2026-10-18: return peaks at -0.1 dBFS fitted as slope 0.00."""
        t = lab.LabTracker()
        src = _guitarish()
        for b in range(60):
            self._feed(t, b, src, src, pin=-40.0 + b * 0.5, pout=-0.1)
        d = t.dynamics()
        self.assertIsNone(d["slope"])
        self.assertIn("full scale", d["why"])
        self.assertEqual(d["near_fs_pct"], 100.0)


class TestDashboardDrawsOnly(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        src = (STATIC / "lab_dash.js").read_text()
        src = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
        cls.code = "\n".join(l for l in src.splitlines() if not l.strip().startswith("//"))

    def test_no_measurement_arithmetic_in_the_browser(self):
        for token in ("Math.log", "Math.sqrt", "Math.exp", "reduce(",
                      "AudioContext", "AnalyserNode", "getUserMedia"):
            self.assertNotIn(token, self.code, token)

    def test_the_dashboard_never_fetches(self):
        for token in ("fetch(", "XMLHttpRequest", "WebSocket", "EventSource"):
            self.assertNotIn(token, self.code)

    def test_it_never_calls_a_result_good_or_bad(self):
        """Grades are the Teensy's (ADR-005). Descriptions of direction are not grades."""
        for word in ("GOOD", "POOR", "health", "Health", "recommend", "Recommend"):
            self.assertNotIn(word, self.code)

    def test_the_spectrum_axis_is_never_called_dbfs(self):
        self.assertIn("not dBFS", self.code)


if __name__ == "__main__":
    unittest.main()
