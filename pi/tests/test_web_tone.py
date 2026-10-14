"""TONE fidelity guards — the 2026-10-13 visual-finish pass (TODO-90), and the
geometry arithmetic behind TODO-88.

*** WHY THESE ARE SOURCE-LEVEL AND ARITHMETIC, NOT RENDERED-PIXEL, TESTS. ***

Nothing here can run three.js: there is no browser in the suite and no GPU. What
these tests CAN do is two things that matter and that a panel screenshot cannot:

  1. Pin the specified visual elements so a later contributor does not remove a
     "redundant" glow mesh or a pulse that looks like decoration. Every one of
     them was specified in `docs/visual_design_document.md` §1c, was absent from
     the shipping port for a fortnight, and was only noticed because an operator
     said the screen looked wrong.

  2. Do the containment arithmetic that the eye cannot. Whether a bar fits in
     frame at every orbit angle is a geometry question with an exact answer, and
     "it looked fine in the screenshot I took" is not that answer.

The numbers are parsed out of the renderer rather than duplicated here. A test
that restates a constant passes happily while the constant it was protecting
moves underneath it.
"""

from __future__ import annotations

import math
import pathlib
import re
import unittest

STATIC = pathlib.Path(__file__).resolve().parents[1] / "web" / "static"
FINGERPRINT = STATIC / "fingerprint_split.js"
MAIN = STATIC / "main.js"
SHELL_CSS = STATIC / "shell.css"


def _const(src: str, name: str) -> float:
    """The numeric value of a `const NAME = <number>;` in the renderer."""
    m = re.search(rf"^const {name}\s*=\s*([-\d.]+)\s*;", src, re.M)
    if not m:
        raise AssertionError(f"{name} not found as a numeric const")
    return float(m.group(1))


class TestToneVisualFinish(unittest.TestCase):
    """The elements §1c specifies, each absent from the port until 2026-10-13."""

    @classmethod
    def setUpClass(cls):
        cls.src = FINGERPRINT.read_text()

    def test_the_baseline_ring_pulses(self):
        """§1c: "thin white PULSING torus (same heartbeat as other versions)"."""
        self.assertRegex(self.src, r"ring\.material\.opacity\s*=\s*pulse",
                         "the baseline ring no longer pulses")

    def test_the_pulse_is_driven_by_the_clock_and_not_by_data(self):
        """A heartbeat driven by a measurement would be a measurement nobody can
        read, displayed as if it were ambience. It must come from the wall clock."""
        m = re.search(r"const pulse\s*=\s*([^;]+);", self.src)
        self.assertIsNotNone(m, "no pulse expression")
        expr = m.group(1)
        self.assertIn("performance.now()", expr)
        for forbidden in ("seg", "segments", "eased", "db", "magnitude", "coverage"):
            self.assertNotIn(forbidden, expr,
                             f"the pulse reads `{forbidden}` — it is data-driven")

    def test_the_ring_has_its_glow(self):
        self.assertIn("ringGlow", self.src, "the §1c ring glow is missing")
        self.assertRegex(self.src, r"ringGlow\.material\.opacity\s*=",
                         "the glow does not track the pulse")

    def test_the_bars_are_emissive(self):
        """Without emissive the bars are lit only by the two scene lights and go
        flat when a band faces away from the key light."""
        self.assertRegex(self.src, r"coldMat\s*=.*emissive:", "cold bars not emissive")
        self.assertRegex(self.src, r"warmMat\s*=.*emissive:", "warm bars not emissive")

    def test_both_easing_channels_exist(self):
        """§1c specifies height at 0.16 AND thickness at 0.14."""
        self.assertAlmostEqual(_const(self.src, "EASE_HEIGHT"), 0.16, places=4)
        self.assertAlmostEqual(_const(self.src, "EASE_COVERAGE"), 0.14, places=4)
        self.assertRegex(self.src, r"lerp\(easedCov\[i\], cov, EASE_COVERAGE\)",
                         "bar thickness is not eased")

    def test_the_amber_markers_survive_the_fidelity_pass(self):
        """*** THE ONE THING THE REFERENCE IMPLEMENTATION DOES NOT HAVE. ***

        The concept predates `presentation_semantics`. Markers exist because the
        instrument can report a band whose direction is not established, and
        "restoring" the concept by deleting them would turn absence into asserted
        measurement — the exact transformation ADR-005's governing invariant
        forbids. This test exists to make that deletion fail loudly.
        """
        self.assertIn("markers", self.src)
        self.assertRegex(self.src, r'cls === "INDETERMINATE" \|\| cls === "CLAMPED"')

    def test_unmeasured_still_draws_nothing(self):
        """The invariant the whole view rests on."""
        self.assertRegex(self.src, r'if \(cls !== "MEASURED"\)')


class TestBarsAreNotTallerThanTheCameraIsToldToExpect(unittest.TestCase):
    """TODO-88. The arithmetic behind the clipping, kept as a live assertion.

    🔺 THIS TEST CURRENTLY DOCUMENTS A KNOWN DEFECT rather than preventing one.
    The camera fit is deliberately unchanged pending a design decision (journal
    2026-10-13 (13)): the honest fix shrinks the ring by about 39 %, which works
    against the complaint that prompted the work. What this does is make the
    inequality explicit and keep it from drifting further.
    """

    @classmethod
    def setUpClass(cls):
        cls.src = FINGERPRINT.read_text()

    def test_max_bar_height_is_a_scale_factor_and_not_a_maximum(self):
        """`MAX_BAR_HEIGHT` is the height of a MAX_DB deviation, and `target` has
        no upper clamp — so the name promises a bound the code does not provide.

        The firmware clamps each TF bin into [TF_DB_MIN-6, TF_DB_MAX+6] = ±24 dB
        (`config.h:667`, `data_sender.h:284`), so the tallest bar the renderer can
        be asked to draw is (24/18)·4.2 = 5.6 — a third beyond the constant.
        """
        src = self.src
        self.assertRegex(src, r"target\s*=\s*Math\.max\(0\.03,\s*\(magnitude / MAX_DB\)",
                         "the height mapping changed; re-derive the bound below")
        self.assertNotRegex(src, r"Math\.min\([^)]*MAX_BAR_HEIGHT",
                            "height is now clamped — update this test and TODO-88")

        max_db = _const(src, "MAX_DB")
        max_bar = _const(src, "MAX_BAR_HEIGHT")
        wire_db_max = 24.0                      # config.h TF_DB_MIN/MAX plus the 6 dB rail
        tallest = (wire_db_max / max_db) * max_bar
        self.assertGreater(tallest, max_bar,
                           "the wire can no longer exceed MAX_DB; TODO-88 may be closeable")
        self.assertAlmostEqual(tallest, 5.6, places=2)

    def test_the_current_fit_does_not_contain_the_tallest_drawable_bar(self):
        """A sphere about the origin is the only bound invariant under orbit, and
        a sphere of radius R is inside a frustum only when R/d <= sin(halfAngle).
        The shipping fit uses tan and a radius derived from the ring alone.

        When this test starts FAILING, the defect has been fixed — update it then,
        rather than loosening it now.
        """
        src = self.src
        disc = _const(src, "DISC_RADIUS")
        max_db = _const(src, "MAX_DB")
        max_bar = _const(src, "MAX_BAR_HEIGHT")
        fov = _const(src, "CAMERA_FOV")
        base = _const(src, "BAR_RADIUS_BASE")
        gain = _const(src, "BAR_RADIUS_GAIN")

        tallest = (24.0 / max_db) * max_bar
        bar_ring = disc * 0.92                  # placeBar() radius
        bound = math.hypot(bar_ring + base + gain, tallest)

        half_fov = math.radians(fov) / 2.0
        aspect = 720.0 / 1280.0                 # the only supported panel
        fit_radius = disc * 1.28                # the shipping FIT_RADIUS
        distance = fit_radius / (math.tan(half_fov) * aspect)

        half_narrow = math.atan(math.tan(half_fov) * aspect)
        contained = distance * math.sin(half_narrow)

        self.assertLess(
            contained, bound,
            "the camera now contains the tallest drawable bar — TODO-88 is fixed, "
            "so replace this test with the containment assertion it was standing in for")


class TestLivePollCadence(unittest.TestCase):

    def test_poll_interval_matches_the_measured_decision(self):
        """500 ms gave 2 Hz against the Tk UI's 20 Hz, which is what "the web UI
        feels slower" was. 200 ms was chosen from measurement: 11.1 ms mean
        response, ~5.5 % of one core at 5 Hz (journal 2026-10-13 (12))."""
        src = MAIN.read_text()
        m = re.search(r"^const POLL_MS = (\d+);", src, re.M)
        self.assertIsNotNone(m, "POLL_MS is no longer a plain constant")
        self.assertEqual(int(m.group(1)), 200)

    def test_polling_still_stops_when_the_page_is_hidden(self):
        """Acquisition IS polling (TODO-86). Raising the rate must not quietly
        turn this into a loop that runs forever in a backgrounded tab."""
        src = MAIN.read_text()
        self.assertIn("visibilitychange", src)
        self.assertIn("stopPolling", src)


class TestTouchSelectionIsSuppressed(unittest.TestCase):
    """TODO-87."""

    @classmethod
    def setUpClass(cls):
        cls.css = SHELL_CSS.read_text()

    def test_selection_is_suppressed_across_the_shell_not_just_the_tabs(self):
        block = re.search(r"#shell, #shell \*\s*\{[^}]*\}", self.css, re.S)
        self.assertIsNotNone(block, "no shell-wide selection rule")
        body = block.group(0)
        self.assertIn("user-select: none", body)
        self.assertIn("-webkit-user-select: none", body)
        self.assertIn("-webkit-touch-callout: none", body)

    def test_it_does_not_disable_touch_gestures_wholesale(self):
        """`touch-action: none` on the shell would kill scrolling and the TONE
        drag. The nav buttons set `manipulation` on themselves; the shell must
        not override the defaults everything else depends on."""
        block = re.search(r"#shell, #shell \*\s*\{[^}]*\}", self.css, re.S)
        self.assertNotIn("touch-action", block.group(0))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
