"""The four-tab shell: navigation wiring, the viewport rule, and the scope fence.

Source-level assertions, like `test_renderer_contract_guard.py` and for the same
reason: this code only ever runs inside a browser, so nothing else in the suite
can see it drift. These are the cheap half of the contract; the Pi bench run is
the other half.

Three of these guard decisions that were expensive to reach:

  * TODO-80. The camera must not be sized from a one-shot viewport read. That
    defect was invisible for the entire life of the renderer because a macOS
    window is sized before first paint, and it took a browser on the Pi to find.
    A test is what stops it being reintroduced by someone tidying a `let` back
    into a `const`.

  * One data source. If a view can fetch, the claim "the browser is given nothing
    to reinterpret" stops being checkable.

  * The FFT scope fence. fft_source[]/fft_return[] carry no coverage nibbles, so
    there is no agreed rule yet for what UNMEASURED means in a magnitude
    spectrum. Until that rule exists in presentation_semantics.py, no client code
    may touch those arrays.
"""

from __future__ import annotations

import pathlib
import re
import unittest

STATIC = pathlib.Path(__file__).resolve().parents[1] / "web" / "static"

TABS = ("live", "tone", "lab", "info")


def _client_js():
    """Every client module, excluding the vendored library.

    three.module.js is not ours and is never read as a statement of intent; it
    also contains audio identifiers it never uses, which is exactly why the
    vendored file is excluded here and in the acquisition guard.
    """
    return sorted(p for p in STATIC.glob("*.js"))


def _strip_comments(src: str) -> str:
    """Drop `//` lines and /* */ blocks, so prose about a thing is never mistaken
    for a use of it. These files describe what they must not do, at length."""
    src = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    return "\n".join(l for l in src.splitlines() if not l.strip().startswith("//"))


# =============================================================================
# NAVIGATION
# =============================================================================

class TestFourTabs(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.html = (STATIC / "index.html").read_text()
        cls.main = (STATIC / "main.js").read_text()

    def test_exactly_four_tabs_exist(self):
        found = re.findall(r'class="tab"[^>]*data-tab="([a-z]+)"', self.html)
        self.assertEqual(tuple(found), TABS)

    def test_every_tab_has_a_view_host(self):
        hosts = re.findall(r'class="view[^"]*" data-view="([a-z]+)"', self.html)
        self.assertEqual(tuple(hosts), TABS)

    def test_the_shell_registers_a_view_for_every_tab(self):
        """A tab with no view behind it is a dead end, which the brief forbids."""
        order = re.search(r"const TABS = \[(.*?)\]", self.main, re.S).group(1)
        self.assertEqual(tuple(re.findall(r'"([a-z]+)"', order)), TABS)
        for tab in TABS:
            self.assertRegex(self.main, rf"\b{tab}:\s*create\w+View\(")

    def test_navigation_is_one_level_deep(self):
        """No history stack, no nested router: every tab is reachable from every
        other tab in one tap, so there is never a back button to forget."""
        self.assertNotIn("history.pushState", self.main)
        self.assertNotIn("hashchange", self.main)

    def test_tabs_respond_to_click_not_touchstart(self):
        """`click` is delivered for touch, mouse and keyboard alike, and is not
        fired when a finger lands on a tab and slides off — a cancelled tap is
        not a choice."""
        self.assertIn('addEventListener("click"', self.main)
        self.assertNotIn('addEventListener("touchstart"', self.main)


class TestInactiveViewsStopRendering(unittest.TestCase):
    """An idle rAF 60 times a second is still the GPU being woken up."""

    @classmethod
    def setUpClass(cls):
        cls.main = (STATIC / "main.js").read_text()
        cls.tone = (STATIC / "view_tone.js").read_text()
        cls.fp = (STATIC / "fingerprint_split.js").read_text()

    def test_the_shell_deactivates_the_view_it_hides(self):
        self.assertIn("deactivate?.()", self.main)
        self.assertIn("activate?.()", self.main)

    def test_the_renderer_can_be_paused_and_resumed(self):
        for name in ("pause()", "resume()", "resize,"):
            self.assertIn(name, self.fp, f"fingerprint_split.js exports no {name}")

    def test_pausing_cancels_the_frame_request(self):
        """Pausing must stop scheduling, not merely return early inside the loop."""
        self.assertIn("cancelAnimationFrame(rafId)", self.fp)

    def test_tone_builds_the_scene_lazily(self):
        """Nothing GPU-shaped may be constructed until the view is first shown."""
        body = _strip_comments(self.tone)
        self.assertNotRegex(body, r"^\s*const scene = createFingerprint",
                            "the scene is built eagerly")
        self.assertIn("function build()", body)

    def test_a_webgl_failure_cannot_take_down_the_other_views(self):
        """Found 2026-10-13: three.js throws when it cannot create a context, and
        an eager construction propagated that out of view creation -- so LIVE,
        LAB and INFO went blank too, though none of them needs a GPU."""
        body = _strip_comments(self.tone)
        self.assertRegex(body, r"try \{\s*\n\s*scene = createFingerprint")
        self.assertIn("catch (e)", body)
        self.assertIn("tone-unavailable", body)

    def test_tone_pauses_when_hidden(self):
        self.assertRegex(self.tone, r"deactivate\(\)\s*\{[^}]*scene\.pause\(\)")

    def test_polling_stops_when_the_page_is_hidden(self):
        self.assertIn("visibilitychange", self.main)


# =============================================================================
# TODO-80 — THE VIEWPORT IS NOT KNOWN AT CONSTRUCTION TIME
# =============================================================================

class TestViewportIsNeverSampledOnce(unittest.TestCase):
    """Measured on the panel 2026-10-12: at load 668x392, on resize 720x1280.

    A kiosk surface is created at a provisional size and resized when the
    compositor assigns the output. Anything derived from a single early
    measurement is derived from a viewport that never existed.
    """

    @classmethod
    def setUpClass(cls):
        cls.fp = _strip_comments((STATIC / "fingerprint_split.js").read_text())
        cls.tone = _strip_comments((STATIC / "view_tone.js").read_text())

    def test_size_is_a_function_not_a_construction_time_constant(self):
        self.assertIn("function resize()", self.fp)
        for banned in ("const width = container.clientWidth",
                       "const height = container.clientHeight"):
            self.assertNotIn(banned, self.fp,
                             "the viewport is being captured once at construction")

    def test_camera_distance_is_reassignable(self):
        """It is recomputed on every resize, so it cannot be a const."""
        self.assertIn("let cameraDistance", self.fp)
        self.assertNotIn("const cameraDistance", self.fp)

    def test_the_container_is_observed_for_resize(self):
        self.assertIn("ResizeObserver", self.fp)
        self.assertIn('window.addEventListener("resize"', self.fp)

    def test_a_zero_sized_container_is_refused(self):
        """A display:none container measures 0x0. Fitting to that bakes a NaN
        into the camera matrix, so the only safe action is to wait."""
        self.assertIn("if (w <= 0 || h <= 0) return false;", self.fp)

    def test_tone_remeasures_before_resuming(self):
        """While hidden the container was display:none, so any size taken then is
        meaningless. Re-measure BEFORE resuming, or the first visible frames
        render against a dead layout."""
        body = re.search(r"activate\(\)\s*\{(.*?)\n    \},", self.tone, re.S).group(1)
        self.assertLess(body.index("scene.resize()"), body.index("scene.resume()"),
                        "resume() runs before resize(); the first frames will be wrong")

    def test_the_stylesheet_fixes_no_panel_dimension(self):
        """720 or 1280 appearing as a layout size would hard-code the provisional
        viewport problem into CSS instead of fixing it."""
        css = re.sub(r"/\*.*?\*/", "", (STATIC / "shell.css").read_text(), flags=re.S)
        self.assertNotRegex(css, r":\s*720px")
        self.assertNotRegex(css, r":\s*1280px")


# =============================================================================
# THE BOUNDARY, RESTATED FOR A CLIENT THAT NOW HAS FOUR SCREENS
# =============================================================================

class TestOneDataSource(unittest.TestCase):

    def test_only_main_js_reaches_the_network(self):
        for p in _client_js():
            code = _strip_comments(p.read_text())
            n = code.count("fetch(")
            if p.name == "main.js":
                self.assertEqual(n, 1, "main.js must hold exactly one fetch")
            else:
                self.assertEqual(n, 0, f"{p.name} fetches; views receive frames")

    def test_no_view_opens_a_socket_or_a_worker(self):
        for p in _client_js():
            code = _strip_comments(p.read_text())
            for banned in ("WebSocket", "EventSource", "new Worker", "XMLHttpRequest"):
                self.assertNotIn(banned, code, f"{p.name} references {banned}")


class TestSpectrumIsRenderedUnderTheReviewedContract(unittest.TestCase):
    """Replaces the temporary FFT scope fence, which fired as designed when the
    spectrum landed.

    The fence said "nothing may touch these arrays yet". These say what the
    reviewed contract actually requires, which is the stronger statement: simply
    deleting the guard would have left the rules it protected unenforced.
    """

    @classmethod
    def setUpClass(cls):
        cls.spec = (STATIC / "spectrum.js").read_text()
        cls.live = (STATIC / "view_live.js").read_text()
        cls.payload = (STATIC.parents[0] / "payload.py").read_text()

    # --- units -----------------------------------------------------------

    def test_the_axis_is_never_labelled_dbfs(self):
        """linearToDbfs() exists in the firmware, floors at -120 and HAS NO
        CALLERS. Its name is an unverified claim. A Hann window has 0.5 coherent
        gain, so a full-scale sine does not read 1.0, and the reference has never
        been calibrated on this instrument."""
        allowed = re.compile(r"not\s+(<b>)?dBFS|time-domain|TIME-DOMAIN|peak_\w+_dbfs")
        for name, src in (("spectrum.js", self.spec), ("view_live.js", self.live)):
            code = _strip_comments(src)
            for m in re.finditer(r"dBFS", code):
                ctx = code[max(0, m.start() - 120):m.end() + 40]
                self.assertRegex(
                    ctx, allowed,
                    f"{name} says dBFS without either denying it applies to the "
                    f"spectrum or tying it to the time-domain peak")

    def test_the_payload_states_the_reference_rather_than_assuming_one(self):
        for token in ("SPECTRUM_UNIT", "SPECTRUM_REFERENCE",
                      "SPECTRUM_REFERENCE_NOTE", "linear_magnitude"):
            self.assertIn(token, self.payload)
        self.assertIn("NOT dBFS", self.payload)

    def test_the_two_quantities_are_kept_apart(self):
        """A per-bin averaged magnitude and a time-domain peak are different
        measurements. On the idle capture they differ by ~7 dB, and a shared
        axis would invite a reader to treat that as a finding."""
        self.assertIn("time-domain peak", self.live)
        self.assertIn("do not compare", self.live.lower())

    # --- the display floor is a drawing choice ---------------------------

    def test_the_floor_is_a_named_constant_and_is_exported(self):
        self.assertRegex(self.spec, r"const FLOOR_DB = -\d+;")
        self.assertIn("export { FLOOR_DB", self.spec)

    def test_the_floor_is_never_called_a_noise_floor(self):
        found = 0
        for name, src in (("spectrum.js", self.spec), ("view_live.js", self.live)):
            code = _strip_comments(src)
            for m in re.finditer(r"noise floor", code):
                found += 1
                ctx = code[max(0, m.start() - 40):m.end()]
                self.assertRegex(
                    ctx, r"not a noise floor|never a noise floor",
                    f"{name} calls the display floor a noise floor")
        # The phrase is allowed ONLY as a denial, and the denial must be present:
        # a floor shown without that disclaimer is the failure this guards.
        self.assertGreater(found, 0, "the display floor is not disclaimed anywhere")

    def test_clipped_points_are_counted_and_surfaced(self):
        """Graphical clipping must be distinguishable from a measured level."""
        self.assertIn("clippedCount", self.spec)
        self.assertIn("clippedCount", self.live)
        self.assertIn("display floor", self.live)

    def test_an_exact_zero_is_drawn_at_the_floor_not_discarded(self):
        """A magnitude of exactly 0.0 is a measurement of silence. The real idle
        capture contains three of them."""
        self.assertIn("pt.value > 0 ? 20 * Math.log10(pt.value) : -Infinity",
                      self.spec)

    # --- the axis uses real bins -----------------------------------------

    def test_there_is_no_second_resample_in_the_client(self):
        """The firmware already decimated 512 -> 128 by MAXIMUM. Reducing again
        would flatten exactly what it preserved."""
        code = _strip_comments(self.spec)
        for banned in ("resample", "bucket", "binTo", "groupOf"):
            self.assertNotIn(banned, code, f"spectrum.js appears to {banned}")

    def test_each_point_is_plotted_at_its_own_transmitted_frequency(self):
        self.assertIn("xOf(g.hz)", self.spec)

    def test_the_dc_bin_is_excluded_from_the_log_axis(self):
        self.assertIn("g.dc", self.spec)
        self.assertIn('"dc"', self.payload)

    def test_the_unrepresented_low_end_is_drawn_rather_than_cropped(self):
        """Coverage starts above 150 Hz, which is ABOVE a low-E fundamental at
        82 Hz. Cropping the axis to the data would hide that."""
        self.assertIn("not transmitted", self.spec)
        self.assertIn("firstUsable", self.spec)
        self.assertIn("82 Hz", self.live)

    def test_an_unmeasured_bin_lifts_the_pen(self):
        self.assertIn('pt.cls !== "MEASURED"', self.spec)
        self.assertIn("open = false", self.spec)

    # --- the sizing rule applies here too --------------------------------

    def test_the_canvas_is_never_sized_from_a_one_shot_read(self):
        self.assertIn("function resize()", self.spec)
        self.assertIn("ResizeObserver", self.spec)
        self.assertIn("if (cw <= 0 || ch <= 0) return false;", self.spec)


class TestAbsenceIsNeverFormattedAsANumber(unittest.TestCase):
    """The formatter is where the governing invariant is easiest to break by
    accident: `(v ?? 0)` turns "the instrument did not say" into a reading."""

    @classmethod
    def setUpClass(cls):
        cls.ui = (STATIC / "ui.js").read_text()

    def test_the_number_formatter_refuses_non_finite_values(self):
        self.assertIn("Number.isFinite(v)", self.ui)
        self.assertIn("return gap(", self.ui)

    def test_absence_has_no_default_value_anywhere_in_the_client(self):
        """`?? 0` and `|| 0` are how a missing measurement becomes a zero."""
        for p in _client_js():
            code = _strip_comments(p.read_text())
            self.assertNotRegex(code, r"\?\?\s*0\b", f"{p.name} defaults absence to 0")
            self.assertNotRegex(code, r"\|\|\s*0\b", f"{p.name} defaults absence to 0")

    def test_a_meter_with_no_value_draws_no_bar(self):
        """An empty bar reads as silence, and absence is not silence."""
        self.assertRegex(self.ui, r"if \(typeof dbfs !== \"number\".*\n.*meter\"")

    def test_every_value_reaching_innerhtml_is_escaped(self):
        self.assertIn("function esc(", self.ui)
        self.assertIn('replace(/[&<>"\']/g', self.ui)


# =============================================================================
# LAB — A PRINTER WITH NO OPINIONS
# =============================================================================
#
# LAB is the screen that shows the instrument's own words. The risk is not that
# it renders badly; it is that it quietly becomes a second author — inferring a
# severity, appending a unit, completing a truncated sentence, or turning an
# absent field into a clean-looking result. These are source-level guards in the
# style of the rest of this file, because this code only runs in a browser.


class TestLabAuthorsNothing(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.src = (STATIC / "view_lab.js").read_text()
        cls.code = _strip_comments(cls.src)

    def test_severity_is_read_from_the_field_not_derived(self):
        """*** THE CENTRAL GUARD. *** Severity is the Teensy's grade. A renderer
        that chose it from how large `magnitude` is would be re-grading a
        measurement, which is the authority boundary broken in the direction
        that looks most reasonable at the time."""
        self.assertIn("SEVERITY[ins.severity]", self.code)
        self.assertNotRegex(self.code, r"magnitude\s*[<>]")
        self.assertNotRegex(self.code, r"Math\.abs\s*\(\s*\w*\.?magnitude")

    def test_no_threshold_is_compared_against_a_measured_value(self):
        """Any `value > number` in this file would be a judgement. The only
        comparisons permitted are against a length or an array index."""
        for m in re.finditer(r"[<>]=?\s*-?\d+(\.\d+)?", self.code):
            ctx = self.code[max(0, m.start() - 40):m.end()]
            self.assertRegex(
                ctx, r"length|\.length\s*[<>=]|index|i\s*[<>]",
                f"view_lab.js compares a value against a literal: {ctx!r}")

    def test_the_mode_distinction_survives_in_the_renderer(self):
        """MEASUREMENT vs ADVISORY is a distinction the Teensy went to the
        trouble of authoring (protocol.InsightMode). Styling them identically
        erases it."""
        self.assertIn("MEASUREMENT", self.code)
        self.assertIn("ADVISORY", self.code)
        css = (STATIC / "shell.css").read_text()
        self.assertIn(".badge.mode-measurement", css)
        self.assertIn(".badge.mode-advisory", css)

    def test_severity_is_not_carried_by_colour_alone(self):
        """The brief forbids it and a 7-inch panel at arm's length is where hue
        fails first. Every severity carries a glyph and a word as well."""
        for sev in ("ALERT", "WARNING", "INFO"):
            self.assertRegex(self.code, rf"{sev}:\s*{{[^}}]*glyph[^}}]*word")
        self.assertIn("badge-glyph", self.code)

    def test_an_unknown_enum_is_not_coerced_to_a_default(self):
        """A newer firmware's severity must not be shown as INFO. Downgrading an
        unrecognised warning to a pleasantry is the worst available failure."""
        self.assertIn("unknown severity", self.code)
        self.assertIn("unknown mode", self.code)

    def test_no_unit_is_appended_to_the_magnitude(self):
        """insights_engine.cpp:170 puts a dimensionless coherence in the same
        slot that elsewhere holds dB. The unit is not on the wire."""
        self.assertNotRegex(self.code, r"magnitude[^\n]*unit:\s*[\"']dB")
        self.assertIn("unit not transmitted", self.code)

    def test_a_broadband_insight_is_never_captioned_zero_hz(self):
        self.assertIn("broadband", self.code)
        self.assertNotRegex(self.code, r"frequency_hz[^\n]*\?\?\s*0")

    def test_the_renderer_does_not_complete_a_truncated_detail(self):
        """The sender cuts detail to 64 bytes mid-word. Repairing it here would
        make this file a co-author of a measurement statement."""
        self.assertNotIn("…", _strip_comments(self.src).replace("—", ""))
        self.assertNotRegex(self.code, r"\.detail[^\n]*(slice|substring|trim)\(")

    def test_insight_strings_reach_innerhtml_only_through_esc(self):
        """Firmware-supplied text. Every one of them is escaped."""
        for field in ("ins.title", "ins.detail"):
            self.assertRegex(self.code, rf"esc\({re.escape(field)}\)")
        self.assertNotRegex(self.code, r"\$\{ins\.(title|detail)\}")

    def test_the_provenance_and_warning_strings_are_escaped_too(self):
        self.assertRegex(self.code, r"esc\(w\)")
        self.assertRegex(self.code, r"text\(cal\.provenance")

    def test_empty_insights_and_missing_insights_say_different_things(self):
        """*** REQUIREMENT 4. *** An empty list is the instrument stating it
        authored none. A missing key is a transport that did not carry the
        field, which is not a statement about the measurement."""
        self.assertIn("Array.isArray(insights)", self.code)
        self.assertIn("insights.length === 0", self.code)
        self.assertIn("None authored", self.src)
        self.assertIn("not carried by this transport", self.src)

    def test_a_missing_block_renders_as_unavailable_not_as_a_clean_result(self):
        for guard in ("if (!c)", "if (!cal)"):
            self.assertIn(guard, self.code)

    def test_calibration_missing_is_visible_and_does_not_imply_a_procedure_ran(self):
        """*** REQUIREMENT 3. *** `type` names a SLOT. Printing INTERNAL_LOOPBACK
        without saying nothing was loaded reads as a calibration that happened."""
        self.assertIn("CALIBRATION_MISSING", self.code)
        self.assertIn("names an empty slot", self.src)
        self.assertRegex(self.src, r"type \(slot\)")

    def test_the_warning_bits_are_shown_by_name_not_as_a_count(self):
        self.assertIn("warn-chip", self.code)
        self.assertNotRegex(self.code, r"warnings\.length\s*\+")

    def test_lab_never_fetches(self):
        """The one-data-source rule, restated for the enlarged view."""
        for token in ("fetch(", "XMLHttpRequest", "WebSocket", "EventSource"):
            self.assertNotIn(token, self.code)

    def test_lab_computes_no_measurement(self):
        """No FFT, no averaging, no re-derivation of a Teensy verdict. The one
        arithmetic operation permitted is a fraction to a percentage, which is
        a presentation transform of a single authored scalar (ADR-005 section 7)."""
        for token in ("AudioContext", "AnalyserNode", "getUserMedia",
                      "Math.log10", "Math.sqrt", "reduce("):
            self.assertNotIn(token, self.code)

    def test_the_two_kinds_of_gap_are_distinguished(self):
        """A transport gap is Pi work. A firmware gap needs a protocol version:
        the 138-byte insight entry is fully spent, so action[] and data_quality
        have no room. Listing them together would misdirect the fix."""
        self.assertIn("firmware", self.code)
        self.assertIn("transport", self.code)
        self.assertIn("action[]", self.src)
        self.assertIn("data_quality", self.src)
        self.assertIn("138", self.src)


class TestLabPreservesTheOtherScreens(unittest.TestCase):
    """Step B touches LAB and the stylesheet. Nothing else may move."""

    def test_live_tone_and_the_fingerprint_are_untouched_by_lab(self):
        lab = _strip_comments((STATIC / "view_lab.js").read_text())
        for foreign in ("createSpectrum", "createFingerprint", "THREE",
                        "spectrum-host", "tone-stage"):
            self.assertNotIn(foreign, lab)

    def test_lab_still_exports_the_factory_the_shell_imports(self):
        lab = (STATIC / "view_lab.js").read_text()
        main = (STATIC / "main.js").read_text()
        self.assertIn("export function createLabView(root)", lab)
        self.assertIn("createLabView", main)

    def test_lab_declares_no_lifecycle_it_does_not_need(self):
        """LAB holds no GPU context and no timer, so it must not claim an
        activate/deactivate contract that would imply it does."""
        lab = _strip_comments((STATIC / "view_lab.js").read_text())
        self.assertNotIn("activate()", lab)
        self.assertNotIn("requestAnimationFrame", lab)



if __name__ == "__main__":
    unittest.main()
