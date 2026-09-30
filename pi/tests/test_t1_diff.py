"""Tests for the T1 report differ.

The fixtures below reproduce the EXACT print formats of `timing_probe.cpp`
(`[T1] key=value`) and `data_sender.cpp` (`[Link] Label: prose`). They are
transcribed from those sources, and the real post-`x` diagnostics observed on
hardware 2026-09-27 are used for the numbers wherever possible, so the parser is
exercised against the shapes it will actually meet.

*** WHAT IS DELIBERATELY NOT TESTED ***

There is no test asserting that some delta passes or fails, because the tool does
not decide that. No project authority defines "indistinguishable from run 1", and
inventing a threshold here would smuggle an acceptance criterion into a test file.
`test_comparative_metrics_are_never_a_failure` pins that refusal, so a future
change that adds an automatic comparative verdict fails loudly and has to be
argued for rather than slipped in.
"""

from __future__ import annotations

import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "tools"))

from t1_diff import compare, parse_report


def t1_block(display_target="Pi 5 (UART)", window_ms=60000, block_n=1293,
             mean=46.400, mx=46.700, mn=46.100, skipped=0, skip_events=0,
             gap=0, loop_us_max=1200, loop_us_mean=210.0, high_water=18,
             used=12, firmware="0.6.0", protocol=2):
    spread = mx - mn
    return "\n".join([
        "[T1] ================ T1 ACCEPTANCE REPORT ================",
        f"[T1] display_target={display_target}",
        f"[T1] firmware={firmware} protocol={protocol}",
        f"[T1] window_ms={window_ms}",
        "[T1] --- acquisition (must be indistinguishable across runs) ---",
        f"[T1] block_n={block_n}",
        f"[T1] block_ms_mean={mean:.3f}",
        f"[T1] block_ms_max={mx:.3f}",
        f"[T1] block_ms_min={mn:.3f}",
        f"[T1] block_ms_spread={spread:.3f}",
        f"[T1] blocks_skipped={skipped}",
        f"[T1] skip_events={skip_events}",
        f"[T1] largest_block_gap={gap}",
        f"[T1] loop_iters=86861",
        f"[T1] loop_us_max={loop_us_max}",
        f"[T1] loop_us_mean={loop_us_mean:.1f}",
        f"[T1] audio_blocks_used={used}",
        f"[T1] audio_blocks_high_water={high_water}",
        "[T1] --- transport (allowed to lose data; must not block) ---",
    ])


def link_block(session=7, live_sent=4846, live_dropped=0, streak=0,
               blocked=0, tx_room_min=0, call_max=449, calls=86861,
               results_queued=1, results_delivered=1, superseded=0,
               abandoned=0, drain_max=102, state_dropped=0, hello_dropped=0,
               router_dropped=0, events_dropped=0):
    pct = (100.0 * live_dropped / (live_sent + live_dropped)
           if (live_sent + live_dropped) else 0.0)
    return "\n".join([
        "[Link] --- Pi link transport (measured) ---",
        f"[Link] Atomicity:   {blocked} best-effort packets refused while a "
        "RESULT was draining (expected, not a fault)",
        f"[Link] Router:      385 sent, {router_dropped} dropped | repair every "
        "1000 ms + on change",
        f"[Link] State:       770 sent, {state_dropped} dropped (drops include "
        "atomicity refusals), every 500 ms",
        f"[Link] Session id:  {session} (constant for this boot) | HELLO "
        f"386 sent, {hello_dropped} dropped, every 1000 ms",
        f"[Link] Live frames:  {live_sent} sent, {live_dropped} dropped "
        f"({pct:.1f}%), longest drop streak {streak}",
        f"[Link] Results:      {results_queued} queued, {results_delivered} "
        f"delivered, {superseded} superseded ({abandoned} B abandoned), "
        f"max drain {drain_max} ms",
        f"[Link] Events:       7 sent, {events_dropped} dropped",
        f"[Link] Call time:    max {call_max} us, mean 15.9 us, last 282 us "
        f"({calls} calls)",
        f"[Link] TX room min:  {tx_room_min} B of 4096 B buffer   "
        "(0 = the Pi is not draining)",
        "[Link] Frame size:   1689 B framed, 4:1 decimation, 128 live bins, "
        "protocol v2",
    ])


NONE_TAIL = "[Link] No display backend compiled in (DISPLAY_TARGET_NONE)."

PASS_TAIL = "\n".join([
    "[T1] --- PASS CONDITION ---",
    "[T1] PASS requires block_ms_mean/max/spread and blocks_skipped",
    "[T1] =====================================================",
])


def run1() -> str:
    return "\n".join([t1_block(display_target="none"), NONE_TAIL, PASS_TAIL])


def run_pi(**kw) -> str:
    link_kw = {k: kw.pop(k) for k in list(kw)
               if k in link_block.__code__.co_varnames}
    return "\n".join([t1_block(**kw), link_block(**link_kw), PASS_TAIL])


class TestParsing(unittest.TestCase):

    def test_t1_keys_are_typed_not_strings(self):
        r = parse_report(run1())
        a = r["acquisition"]
        self.assertEqual(a["window_ms"], 60000)
        self.assertIsInstance(a["block_ms_mean"], float)
        self.assertEqual(a["blocks_skipped"], 0)
        self.assertEqual(a["display_target"], "none")
        self.assertEqual(a["firmware"], "0.6.0 protocol=2")

    def test_the_none_backend_has_no_transport_block(self):
        r = parse_report(run1())
        self.assertFalse(r["transport_present"])
        self.assertTrue(r["backend_absent"])
        self.assertEqual(r["transport"], {})

    def test_link_prose_is_parsed_field_by_field(self):
        r = parse_report(run_pi())
        t = r["transport"]
        self.assertEqual(t["session_id"], 7)
        self.assertEqual(t["live_sent"], 4846)
        self.assertEqual(t["live_dropped"], 0)
        self.assertEqual(t["call_us_max"], 449)
        self.assertEqual(t["send_calls"], 86861)
        self.assertEqual(t["tx_room_min"], 0)
        self.assertEqual(t["atomicity_blocked_by_result"], 0)
        self.assertEqual(t["result_drain_ms_max"], 102)
        self.assertEqual(t["result_bytes_abandoned"], 0)

    def test_dropped_counts_are_distinguished_from_sent_counts(self):
        """The prose puts both on one line. Confusing them would read a
        healthy run as a lossy one, or worse, the reverse."""
        r = parse_report(run_pi(live_sent=3000, live_dropped=412, streak=9))
        t = r["transport"]
        self.assertEqual(t["live_sent"], 3000)
        self.assertEqual(t["live_dropped"], 412)
        self.assertEqual(t["live_dropped_streak_max"], 9)

    def test_surrounding_console_noise_is_ignored(self):
        noisy = "\n".join([
            "================================================",
            "     Guitar Rig Analyzer   v0.6.0",
            "Build: Sep 26 2026 16:36:53   v0.6.0",
            "[Main] --- 5s diagnostics (uptime 65s) ---",
            "[Main] Block:      107 in 5000ms = 46.7 ms/block",
            run_pi(),
            "[Main] SOURCE_NODE peak: -21.8 dBFS",
        ])
        r = parse_report(noisy)
        self.assertEqual(r["acquisition"]["window_ms"], 60000)
        self.assertEqual(r["transport"]["session_id"], 7)

    def test_the_last_report_wins_when_T_is_pressed_twice(self):
        both = run_pi(window_ms=30000) + "\n" + run_pi(window_ms=61000)
        r = parse_report(both)
        self.assertEqual(r["acquisition"]["window_ms"], 61000)

    def test_a_paste_with_no_report_is_refused_not_guessed(self):
        with self.assertRaises(ValueError):
            parse_report("[Main] Setup complete. Entering main loop.")


class TestAbsoluteRule(unittest.TestCase):
    """blocks_skipped / skip_events / largest_block_gap == 0 in EVERY run.

    The one criterion the project states absolutely, so the one the tool is
    entitled to enforce.
    """

    def _four(self, **run3):
        return [parse_report(x) for x in
                (run1(), run_pi(), run_pi(**run3), run_pi(abandoned=4096))]

    def test_all_zero_is_no_failure(self):
        res = compare(self._four(live_dropped=500, tx_room_min=0),
                      ["run1", "run2", "run3", "run4"])
        self.assertEqual(res["hard_failures"], [])

    def test_a_skipped_block_in_any_run_is_a_hard_failure(self):
        res = compare(self._four(live_dropped=500, tx_room_min=0, skipped=1),
                      ["run1", "run2", "run3", "run4"])
        self.assertEqual(len(res["hard_failures"]), 1)
        self.assertIn("blocks_skipped=1", res["hard_failures"][0])

    def test_the_rule_applies_to_the_control_too(self):
        """A control run that skipped a block is not a valid control."""
        reports = [parse_report(run1().replace("blocks_skipped=0",
                                               "blocks_skipped=3")),
                   parse_report(run_pi()),
                   parse_report(run_pi(live_dropped=500)),
                   parse_report(run_pi(abandoned=4096))]
        res = compare(reports, ["run1", "run2", "run3", "run4"])
        self.assertTrue(any("run1" in f for f in res["hard_failures"]))

    def test_largest_block_gap_is_covered_not_just_blocks_skipped(self):
        res = compare(self._four(live_dropped=500, tx_room_min=0, gap=2),
                      ["run1", "run2", "run3", "run4"])
        self.assertTrue(any("largest_block_gap=2" in f
                            for f in res["hard_failures"]))


class TestExperimentControl(unittest.TestCase):

    def test_a_pi_built_control_is_a_procedural_finding(self):
        res = compare([parse_report(run_pi()), parse_report(run_pi())],
                      ["run1", "run2"])
        self.assertTrue(any("expected 'none'" in f
                            for f in res["procedural_findings"]))
        self.assertTrue(any("[Link] transport block" in f
                            for f in res["procedural_findings"]))

    def test_unequal_windows_are_flagged(self):
        res = compare([parse_report(run1()),
                       parse_report(run_pi(window_ms=20000))],
                      ["run1", "run2"])
        self.assertTrue(any("window_ms" in f
                            for f in res["procedural_findings"]))

    def test_a_small_window_difference_is_tolerated(self):
        """Hand-timed windows will never match to the millisecond."""
        res = compare([parse_report(run1()),
                       parse_report(run_pi(window_ms=61500))],
                      ["run1", "run2"])
        self.assertFalse(any("window_ms" in f
                             for f in res["procedural_findings"]))

    def test_a_firmware_mismatch_is_flagged(self):
        res = compare([parse_report(run1()),
                       parse_report(run_pi(firmware="0.6.1"))],
                      ["run1", "run2"])
        self.assertTrue(any("not the same build family" in f
                            for f in res["procedural_findings"]))

    def test_two_runs_sharing_one_boot_are_flagged(self):
        """[Link] figures are boot-scoped, so a shared session id means the
        transport columns overlap and TX room min carries over."""
        res = compare([parse_report(run1()),
                       parse_report(run_pi(session=9, live_dropped=500)),
                       parse_report(run_pi(session=9, abandoned=4096))],
                      ["run1", "run3", "run4"])
        self.assertTrue(any("share one boot" in f
                            for f in res["procedural_findings"]))

    def test_distinct_sessions_are_not_flagged(self):
        res = compare([parse_report(run1()),
                       parse_report(run_pi(session=8)),
                       parse_report(run_pi(session=9, live_dropped=500,
                                           tx_room_min=0)),
                       parse_report(run_pi(session=10, abandoned=4096))],
                      ["run1", "run2", "run3", "run4"])
        self.assertFalse(any("share one boot" in f
                             for f in res["procedural_findings"]))


class TestRunRoleExpectations(unittest.TestCase):
    """Each run must exercise what it exists to exercise.

    Not pass criteria — step 11 states these as expectations. A run 4 with zero
    abandoned bytes did not happen, which is a fact about the procedure.
    """

    def _four(self, r3=None, r4=None):
        # Distinct session ids: the run sheet requires a reboot between runs,
        # because [Link] figures are boot-scoped. Reusing one id here would trip
        # the shared-boot check and mask what these tests are actually about.
        r3 = {"live_dropped": 500, "tx_room_min": 0, "session": 9,
              **(r3 or {})}
        r4 = {"abandoned": 4096, "session": 10, **(r4 or {})}
        return [parse_report(x) for x in
                (run1(), run_pi(session=8), run_pi(**r3), run_pi(**r4))]

    def test_a_run4_that_missed_the_drain_window_is_flagged(self):
        res = compare(self._four(r4={'abandoned': 0}),
                      ["run1", "run2", "run3", "run4"])
        self.assertTrue(any("the pull missed the drain window" in f
                            for f in res["procedural_findings"]))

    def test_a_run3_with_no_drops_did_not_apply_backpressure(self):
        res = compare(self._four(r3={'live_dropped': 0, 'tx_room_min': 2048}),
                      ["run1", "run2", "run3", "run4"])
        self.assertTrue(any("should drop live frames" in f
                            for f in res["procedural_findings"]))

    def test_expectations_met_produce_no_findings(self):
        res = compare(self._four(), ["run1", "run2", "run3", "run4"])
        self.assertEqual(res["procedural_findings"], [])
        self.assertTrue(all(e["met"] for e in res["exercised"]))

    def test_run2_has_no_role_expectations(self):
        """Normal operation is not required to drop anything."""
        res = compare(self._four(), ["run1", "run2", "run3", "run4"])
        self.assertFalse(any(e["run"] == "run2" for e in res["exercised"]))


class TestItRefusesToJudgeTheComparison(unittest.TestCase):

    def test_comparative_metrics_are_never_a_failure(self):
        """Pins the refusal. A wildly different block_ms_max is reported with
        its delta and is NOT a hard failure, because no authority in this
        project defines the threshold. If someone adds an automatic comparative
        verdict, this test fails and they have to justify the number."""
        reports = [parse_report(run1()),
                   parse_report(run_pi(mean=92.0, mx=310.0, mn=46.0,
                                       loop_us_max=250000))]
        res = compare(reports, ["run1", "run2"])
        self.assertEqual(res["hard_failures"], [])

    def test_deltas_are_computed_for_the_operator(self):
        reports = [parse_report(run1()),
                   parse_report(run_pi(mx=93.400))]
        res = compare(reports, ["run1", "run2"])
        row = next(r for r in res["comparison"]
                   if r["metric"] == "block_ms_max")
        self.assertAlmostEqual(row["control"], 46.700, places=3)
        self.assertAlmostEqual(row["runs"][0]["delta"], 46.700, places=3)
        self.assertAlmostEqual(row["runs"][0]["rel"], 1.0, places=3)

    def test_transport_degradation_is_never_a_failure(self):
        """Step 11: transport is ALLOWED to degrade."""
        reports = [parse_report(run1()),
                   parse_report(run_pi(live_sent=10, live_dropped=4000,
                                       streak=3000, tx_room_min=0,
                                       hello_dropped=60, state_dropped=120))]
        res = compare(reports, ["run1", "run2"])
        self.assertEqual(res["hard_failures"], [])


if __name__ == "__main__":
    unittest.main()
