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


class TestFftScopeFence(unittest.TestCase):
    """fft_source[] and fft_return[] carry NO coverage nibbles -- the coverage
    array belongs to tf_db[]. So there is no rule yet for what UNMEASURED means
    in a magnitude spectrum, and a renderer inventing one is the drift ADR-005 §4
    exists to stop.

    This test fails the moment a spectrum is drawn before that rule is reviewed.
    Delete it in the same commit that adds the rule to presentation_semantics.py,
    not before.
    """

    def test_the_transport_does_not_carry_the_fft_arrays_yet(self):
        payload_src = (STATIC.parents[0] / "payload.py").read_text()
        for field in ("fft_source", "fft_return"):
            self.assertNotIn(f'"{field}"', payload_src,
                             f"{field} is now on the wire; the fence needs review")

    def test_no_client_code_references_the_fft_arrays(self):
        for p in _client_js():
            code = _strip_comments(p.read_text())
            for field in ("fft_source", "fft_return"):
                self.assertNotIn(field, code, f"{p.name} reads {field}")

    def test_live_states_the_gap_rather_than_drawing_an_empty_axis(self):
        """An axis labelled 'spectrum' with nothing on it implies the instrument
        measured a flat response. Saying why it is absent does not."""
        src = (STATIC / "view_live.js").read_text()
        self.assertIn("PENDING_SPECTRUM", src)
        self.assertIn("no per-bin coverage", src)


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


if __name__ == "__main__":
    unittest.main()
