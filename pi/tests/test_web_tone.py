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
        flat when a bin faces away from the key light."""
        self.assertRegex(self.src, r"returnMat\s*=.*emissive:", "return bars not emissive")
        self.assertRegex(self.src, r"inputMat\s*=.*emissive:", "input bars not emissive")

    def test_the_bar_material_does_not_square_the_instance_colour(self):
        """three.js multiplies material colour by instance colour. A coloured
        material under a coloured instance drew cyan-squared (dark teal) and
        orange-squared (brown) -- every TONE capture before 2026-10-16."""
        for mat in ("returnMat", "inputMat"):
            m = re.search(rf"{mat}\s*=\s*new THREE\.MeshLambertMaterial\(\{{([^}}]*)\}}", self.src)
            self.assertIsNotNone(m, f"{mat} not found")
            self.assertIn("color: 0xffffff", m.group(1),
                          f"{mat} has a non-white colour; the instance colour will be squared")

    def test_height_eases_and_an_unmeasured_channel_snaps(self):
        """§1c height easing at 0.16. An UNMEASURED channel must not ease: it
        would animate through levels the instrument never reported."""
        self.assertAlmostEqual(_const(self.src, "EASE_HEIGHT"), 0.16, places=4)
        self.assertRegex(self.src, r"easedIn\[i\] = inMeasured \? lerp\(easedIn\[i\], inp\.h, EASE_HEIGHT\) : 0;")
        self.assertRegex(self.src, r"easedRet\[i\] = retMeasured \? lerp\(easedRet\[i\], ret\.h, EASE_HEIGHT\) : 0;")

    def test_the_tf_only_elements_are_gone(self):
        """Markers (INDETERMINATE/CLAMPED), coverage-driven thickness and the
        loss/gain divider were tf_db properties. A magnitude spectrum has no
        clamp and no coverage nibble (`classify_spectrum`), so drawing them on
        the input/return ring would show classes that cannot occur.

        The markers' old guard said deleting them "would turn absence into
        asserted measurement". That held for tf_db, which TONE no longer draws.
        `segments` still carries those classes for any renderer that reads it.
        """
        code = "\n".join(l for l in self.src.splitlines()
                         if not l.strip().startswith("//"))
        for gone in ("INDETERMINATE", "CLAMPED", "EASE_COVERAGE", "divider",
                     "coverage"):
            self.assertNotIn(gone, code, f"{gone} is back in the renderer")

    def test_unmeasured_still_draws_nothing(self):
        """The invariant the whole view rests on: no number, no bar."""
        self.assertIn('b.src_cls === "MEASURED"', self.src)
        self.assertIn('b.ret_cls === "MEASURED"', self.src)
        self.assertIn("HIDDEN", self.src)

    def test_whether_a_bar_exists_is_the_pis_decision(self):
        """`src_on` / `ret_on` are classified in payload.py. The first render
        drew a return bar on every section while the census said "return 0",
        because the renderer re-derived presence from the level."""
        self.assertRegex(self.src, r"inMeasured && b\.src_on \? b\.src_db : null")
        self.assertRegex(self.src, r"retMeasured && b\.ret_on \? b\.ret_matched_db : null")

    def test_the_seats_are_tilted_the_same_way_as_the_bars(self):
        """Bars and labels sit at (cos a, ·, −sin a). A +90° tilt put the seats
        at (cos a, ·, +sin a), so a lit seat sat at the mirror of its own bar."""
        self.assertRegex(self.src, r"FLAT_Q = new THREE\.Quaternion\(\)\.setFromAxisAngle\(AXIS_X, -Math\.PI / 2\)")


class TestBarsAreNotTallerThanTheCameraIsToldToExpect(unittest.TestCase):
    """TODO-88, **CLOSED 2026-10-15**. The arithmetic, kept as a live assertion.

    🔺 THIS TEST USED TO DOCUMENT THE DEFECT. It now prevents it. Two changes
    made the bound real: `magnitude` is clamped to `MAX_DB` before scaling, so
    the firmware's ±24 dB rail can no longer ask for a taller bar than the
    scale's own maximum; and `MAX_BAR_HEIGHT` was sized so the bar TIP sits
    inside the orbit-invariant bounding sphere the camera contains.

    The ring was **not** shrunk to achieve it — that was the alternative the
    2026-10-13 analysis rejected, because it works against the complaint that
    prompted the work.
    """

    @classmethod
    def setUpClass(cls):
        cls.src = FINGERPRINT.read_text()

    def test_bar_height_is_clamped_to_the_scale(self):
        """The wire can carry ±24 dB; the scale is MAX_DB. Without a clamp the
        renderer draws a bar for a magnitude its own scale does not define, and
        the reader has no way to know the bar is off-scale.

        Clamped **and** marked: an over-range bar carries a cap, so a bar pinned
        at full length is never mistaken for a value of exactly MAX_DB.
        """
        src = self.src
        self.assertRegex(
            src, r"Math\.min\(1, \(db - FLOOR_DB\) / \(FULL_DB - FLOOR_DB\)\)",
            "level is no longer clamped to the scale — TODO-88 has reopened")
        self.assertIn("OVER_RANGE_MARK", src,
                      "a clamped bar must be marked, or it asserts a wrong value")
        self.assertLess(_const(src, "FLOOR_DB"), _const(src, "FULL_DB"))

        max_bar = _const(src, "MAX_BAR_HEIGHT")
        over = _const(src, "OVER_RANGE_MARK")
        # However tall the wire asks for, the drawn tip is bounded by this:
        self.assertAlmostEqual(max_bar + over, 2.41, places=2)

    def test_the_fit_contains_the_tallest_drawable_bar_at_every_orbit_position(self):
        """The containment assertion the previous version was standing in for.

        A sphere about the origin is the only bound invariant under orbit — yaw
        is unrestricted, so any bar can be carried to any bearing — and a sphere
        of radius R sits inside a frustum only when R <= d·sin(halfAngle), using
        the NARROW half-angle on a 720x1280 portrait panel.

        If this fails, a bar can leave the frame at some orbit position. Do not
        loosen it: either lower MAX_BAR_HEIGHT or raise FIT_RADIUS, and say in
        the constant's comment which was chosen and why.
        """
        src = self.src
        disc = _const(src, "DISC_RADIUS")
        max_bar = _const(src, "MAX_BAR_HEIGHT")
        over = _const(src, "OVER_RANGE_MARK")
        fov = _const(src, "CAMERA_FOV")
        width = _const(src, "BAR_WIDTH")
        depth = _const(src, "BAR_DEPTH")

        # Height is clamped to the scale now, so the tallest tip is the bar at
        # full scale plus its over-range cap -- NOT a function of the wire rail.
        tallest = max_bar + over
        bar_ring = disc * 0.92                  # placeBar() radius
        # A block's farthest point is its outer corner: half the depth out
        # from the bar ring, half the width along the tangent.
        bound = math.hypot(math.hypot(bar_ring + depth / 2, width / 2), tallest)

        half_fov = math.radians(fov) / 2.0
        aspect = 720.0 / 1280.0                 # the only supported panel
        fit_radius = disc * 1.28                # the shipping FIT_RADIUS
        distance = fit_radius / (math.tan(half_fov) * aspect)

        half_narrow = math.atan(math.tan(half_fov) * aspect)
        contained = distance * math.sin(half_narrow)

        self.assertLessEqual(
            bound, contained,
            f"a full-scale bar (bound {bound:.3f}) leaves the frame "
            f"(contains {contained:.3f}) at some orbit position")

    def test_the_range_is_fixed_and_agrees_with_the_payload(self):
        """One section per transmitted bin, bins 1..16 (151 Hz – 2.9 kHz): the
        range a guitar plays in (operator, 2026-10-16).

        🛑 An auto-zoom that followed the data would change what a position on
        the ring MEANS between two frames, so two moments could not be compared.
        The range is constants, never computed from the frame -- and the two
        sides of the boundary must agree on them.
        """
        from web import payload
        src = FINGERPRINT.read_text()
        self.assertEqual(_const(src, "FIRST_BIN"), payload.TONE_FIRST_BIN)
        self.assertEqual(_const(src, "LAST_BIN"), payload.TONE_LAST_BIN)
        self.assertEqual(_const(src, "FLOOR_DB"), payload.TONE_FLOOR_DB)
        self.assertEqual(payload.TONE_FIRST_BIN, 1, "bin 0 spans DC and must stay off")
        self.assertNotRegex(src, r"(FIRST_BIN|LAST_BIN)\s*=\s*[^;]*(tone|bins)",
                            "the range is being derived from the data")

    def test_the_circle_is_not_mirrored_and_direction_is_the_axis(self):
        """Angle means ONE thing: frequency. Above the ring is the input, below
        it the return. No mirrored half-rings."""
        src = FINGERPRINT.read_text()
        for gone in ("LEFT_START", "RIGHT_START", "leftAngles", "rightAngles"):
            self.assertNotIn(gone, src,
                             f"{gone} is back — the mirrored arcs have returned")
        self.assertIn("sectionAngle", src)

    def test_labels_are_hz_and_come_from_the_bin_geometry(self):
        """Hz below 1 kHz, kHz above (operator, 2026-10-16), at each bin's
        centre as the instrument sent it. Note names are gone: a 172 Hz bin
        cannot name a note anywhere in this range (TODO-92)."""
        src = FINGERPRINT.read_text()
        code = "\n".join(l for l in src.splitlines() if not l.strip().startswith("//"))
        self.assertIn("export function fmtHz(hz)", src)
        self.assertIn("kHz", code)
        self.assertIn("makeLabelSprite(fmtHz(b.hz))", code)
        for gone in ("NOTE_NAMES", "noteName", "NOTE_SECTIONS"):
            self.assertNotIn(gone, code, f"{gone}: note labels are back")

    def test_each_section_is_one_transmitted_bin(self):
        """No resampling onto a finer axis: a section is a bin, so a lit
        section cannot claim more resolution than the wire carried."""
        src = FINGERPRINT.read_text()
        self.assertIn("byBin.get(FIRST_BIN + i)", src)
        self.assertNotIn("bandForSection", src)

    def test_there_is_no_decay_trail(self):
        """Removed 2026-10-15 at the operator's request: live notes only.

        Recorded as a test so it is not reintroduced as an improvement — the
        objection was clutter, not honesty.
        """
        src = FINGERPRINT.read_text()
        for gone in ("TRAIL_MS", "trailH", "coldTrail", "TRAIL_SLOTS"):
            self.assertNotIn(gone, src, f"the decay trail is back ({gone})")

    def test_a_drag_does_not_permanently_stop_the_orbit(self):
        """`spin` was set false on pointer-down and never restored, so one
        accidental touch stopped the orbit for the rest of the session.
        Releasing resumes it from the current yaw and pitch.
        """
        src = FINGERPRINT.read_text()
        self.assertRegex(src, r"spin = true;\s*//",
                         "release no longer resumes the spin")
        self.assertIn("touchcancel", src,
                      "a cancelled touch would leave the orbit stopped")


class TestLivePollCadence(unittest.TestCase):

    def test_poll_interval_matches_the_measured_decision(self):
        """50 ms = 20 Hz, matching the Tk UI this replaced.

        500 ms gave 2 Hz and 200 ms gave 5 Hz; the operator's "the new UI is
        laggy" was that difference and nothing else. Measured on the Pi
        2026-10-15 before the change: 5.09 req/s observed, server 6.4 ms p50,
        whole kiosk 24.6 % of ONE of four cores, no throttling. The server was
        never the constraint.

        MILLISECONDS, NOT HERTZ -- 20 here would be 50 Hz, and the renderer
        costs ~24.5 ms per poll, which exceeds a 20 ms period.
        """
        src = MAIN.read_text()
        m = re.search(r"^const POLL_MS = (\d+);", src, re.M)
        self.assertIsNotNone(m, "POLL_MS is no longer a plain constant")
        self.assertEqual(int(m.group(1)), 50)

    def test_a_poll_cannot_overlap_the_one_before_it(self):
        """`setInterval` does not wait for an async callback.

        At 200 ms an overlap was unreachable. At 50 ms the margin is ~2x against
        a measured ~24.5 ms renderer cost per poll, so it is reachable -- and an
        overlap is not merely slow, it is WRONG: two in-flight requests can
        resolve out of order and `frame = f` is a bare assignment, so the older
        response wins and the panel shows a stale measurement with nothing
        saying so.

        This pins the guard, not its wording: raising the rate again must not
        quietly remove it.
        """
        src = MAIN.read_text()
        self.assertIn("inFlight", src, "the in-flight guard is gone")
        self.assertRegex(
            src, r"if \(inFlight\)",
            "poll() no longer refuses to start while one is already running")
        self.assertIn("finally", src,
                      "inFlight must be cleared in a finally, or one thrown "
                      "error wedges polling permanently")

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
