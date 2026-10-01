"""Drift guard: the Tk renderer consumes the shared contract (ADR-005 §4, TODO-68).

Separate from `test_presentation_semantics.py` on purpose. That file tests the
contract and must pass on its own commit, before any renderer consumes it. This
file tests a RENDERER against the contract, so it only becomes true once the
refactor lands.
"""

from __future__ import annotations

import pathlib
import re
import unittest


# =============================================================================
# DRIFT GUARD — the renderer consumes the contract rather than re-deriving it
# =============================================================================

class TestTkRendererConsumesTheContract(unittest.TestCase):
    """*** WHY A SOURCE-LEVEL TEST. ***

    `app.py` imports tkinter and needs a display, so it is deliberately never
    imported by the suite — which means nothing else here can catch the renderer
    quietly going back to reading coverage nibbles itself. With two renderers
    live (ADR-005 §2), a renderer that re-derives classification makes "reference
    renderer" a label with nothing behind it. This guard is the cheap half of
    that contract; the Pi bench run is the other half.
    """

    @classmethod
    def setUpClass(cls):
        cls.src = (pathlib.Path(__file__).resolve().parents[1]
                   / "analyzer_ui" / "app.py").read_text()

    def test_it_imports_the_shared_layer(self):
        self.assertIn("presentation_semantics as ps", self.src)

    def test_it_does_not_re_derive_classification_from_coverage(self):
        """These are the exact expressions the refactor removed. Each one is a
        renderer deciding for itself what a bin means."""
        for banned in ("cov.clamped", "cov.ratio", "cov.valid",
                       "pen_lift_indices", "clamped_marks",
                       "plotting.census"):
            self.assertNotIn(banned, self.src,
                             f"app.py re-derives semantics via {banned!r}")

    def test_it_never_compares_a_value_against_a_rail_to_classify(self):
        """The -24.0 comparison survives ONLY as operator context in the warning
        text (TODO-65 requires it deleted when the protocol closes). It must
        never reach a plottability DECISION.

        The distinction this test draws, and why it is not cosmetic: counting
        how many already-classified bins happen to sit at the rail is reporting.
        Letting that comparison decide whether a bin is drawable is TODO-29.
        """
        for line in self.src.splitlines():
            if "24.0" not in line:
                continue
            self.assertNotIn("plottable=", line)
            self.assertNotIn("is_drawable_as_measurement", line)

    def test_the_plottability_predicates_consult_only_the_contract(self):
        """Each `plottable=` predicate must resolve through `sem[...]`, so no
        predicate can grow a value test without this failing."""
        bodies = re.findall(r"def (?:drawable|indeterminate|ok)\(i, _v\):\n(.*?)\n\n",
                            self.src, re.S)
        self.assertGreaterEqual(len(bodies), 3, "predicates not found")
        for body in bodies:
            self.assertIn("sem[i]", body)
            self.assertNotIn("24.0", body)

    def test_it_asks_the_contract_whether_a_bin_is_drawable(self):
        self.assertIn("is_drawable_as_measurement", self.src)



if __name__ == "__main__":
    unittest.main()
