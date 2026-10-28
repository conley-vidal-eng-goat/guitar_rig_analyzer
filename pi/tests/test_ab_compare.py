"""ab_compare must find a known change, find nothing where nothing changed, and
refuse to claim anything from a run that breaks its validity rules."""

import json
import pathlib
import random
import subprocess
import sys
import tempfile
import unittest

TOOLS = pathlib.Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS))

import ab_compare  # noqa: E402

NB = 48
HZ = [100 * 1.12 ** i for i in range(NB)]


def frame(tf, session=7, clip=False, stale=False, errors=0, unmeasured=(), kind="live",
          rng=None):
    rng = rng or random.Random(0)
    segs = []
    for i in range(NB):
        off = i in unmeasured
        segs.append({"i": i, "hz": round(HZ[i], 1),
                     "cls": "UNMEASURED" if off else "MEASURED",
                     "value": None if off else tf[i] + rng.gauss(0, 0.05)})
    src = [{"cls": "MEASURED", "value": 0.02} for _ in range(128)]
    f = {"kind": kind, "segments": segs, "spectra": {"src": src},
         "authority": {"peak_source_dbfs": -12.0, "peak_return_dbfs": -14.0,
                       "source_clip": clip, "return_clip": False},
         "link": {"session": session, "stale": stale, "decode_errors": errors}}
    if kind == "result":
        f["authority"].update(result_valid=True, result_quality="GOOD",
                              mean_coherence=0.9, valid_bin_fraction=0.8,
                              n_averages_completed=32)
    return f


def write(run, label, frames):
    (run / f"{label}.jsonl").write_text("\n".join(json.dumps(f) for f in frames) + "\n")


FLAT = [0.0] * NB
BOOST = [6.0 if 20 <= i <= 25 else 0.0 for i in range(NB)]


class ABCompareTest(unittest.TestCase):
    def run_ab(self, a, b, **over):
        with tempfile.TemporaryDirectory() as t:
            run = pathlib.Path(t)
            rng = random.Random(1)
            for label, tf in (("A1", a), ("B1", b), ("A2", a), ("B2", b)):
                kw = over.get(label, {})
                write(run, label, [frame(tf, rng=rng, **kw) for _ in range(40)])
            out = subprocess.run([sys.executable, str(TOOLS / "ab_compare.py"), str(run)],
                                 capture_output=True, text=True, check=True).stdout
            return out, (run / "report.md").read_text(), (run / "delta.svg").exists()

    def test_a_known_boost_is_found_in_exactly_the_boosted_bands(self):
        out, report, has_svg = self.run_ab(FLAT, BOOST)
        self.assertIn("CHANGE DETECTED in 6 of 48 bands", out)
        self.assertIn("+6.0 dB", out)
        self.assertEqual(report.count("| ✔ |"), 6)
        self.assertTrue(has_svg)

    def test_no_change_is_reported_as_no_change(self):
        out, _, _ = self.run_ab(FLAT, FLAT)
        self.assertIn("NO CHANGE DETECTED in 48 bands", out)

    def test_a_teensy_restart_invalidates_the_run(self):
        out, _, _ = self.run_ab(FLAT, BOOST, B2={"session": 8})
        self.assertTrue(out.startswith("INVALID"))
        self.assertIn("2 Teensy sessions", out)

    def test_clipping_invalidates_the_run(self):
        out, _, _ = self.run_ab(FLAT, BOOST, B1={"clip": True})
        self.assertTrue(out.startswith("INVALID"))
        self.assertIn("clipped", out)

    def test_rising_decode_errors_invalidate_the_run(self):
        out, _, _ = self.run_ab(FLAT, BOOST, A2={"errors": 3})
        self.assertTrue(out.startswith("INVALID"))

    def test_a_band_missing_from_one_state_is_left_out_not_counted_as_flat(self):
        out, report, _ = self.run_ab(FLAT, BOOST, A2={"unmeasured": (22,)})
        self.assertIn("of 47 bands", out)
        self.assertEqual(report.count("| ✔ |"), 5)

    def test_a_change_that_does_not_repeat_is_not_counted(self):
        # B2 equals A: the first cycle shows a boost the second does not.
        with tempfile.TemporaryDirectory() as t:
            run = pathlib.Path(t)
            rng = random.Random(2)
            for label, tf in (("A1", FLAT), ("B1", BOOST), ("A2", FLAT), ("B2", FLAT)):
                write(run, label, [frame(tf, rng=rng) for _ in range(40)])
            out = subprocess.run([sys.executable, str(TOOLS / "ab_compare.py"), str(run)],
                                 capture_output=True, text=True, check=True).stdout
        self.assertIn("NO CHANGE DETECTED", out)

    def test_result_frames_are_tabulated(self):
        with tempfile.TemporaryDirectory() as t:
            run = pathlib.Path(t)
            rng = random.Random(3)
            for label, tf in (("A1", FLAT), ("B1", BOOST), ("A2", FLAT), ("B2", BOOST)):
                write(run, label, [frame(tf, rng=rng) for _ in range(40)]
                      + [frame(tf, rng=rng, kind="result")])
            subprocess.run([sys.executable, str(TOOLS / "ab_compare.py"), str(run)],
                           capture_output=True, text=True, check=True)
            report = (run / "report.md").read_text()
        self.assertIn("## Teensy RESULTs", report)
        self.assertIn("| A1 | True | GOOD | 0.900 |", report)


if __name__ == "__main__":
    unittest.main()
