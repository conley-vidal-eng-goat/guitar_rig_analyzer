"""--timeline: intermediate states must survive a return to the starting state.

The motivating problem is specific. Step A of the Phase 10 plan drives
IDLE -> ARMED -> ABORTED(TIMEOUT) -> acknowledge -> IDLE, and every interesting
thing about it happens in the middle. The default report shows only the final
receiver state, which for that sequence is indistinguishable from an idle
capture: IDLE, no latch, view live. Taking a carefully staged transition
capture and then reducing it to "IDLE" would discard the entire result.

These tests build that sequence synthetically and assert the timeline recovers
it, WITHOUT asserting the ordering the hardware has yet to demonstrate.
"""

from __future__ import annotations

import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "tools"))

from analyzer_link import protocol
from analyzer_link.framing import FrameScanner
from replay import replay

from . import vectors

GEO = protocol.Geometry()
FIXTURE = (pathlib.Path(__file__).resolve().parents[2]
           / "ai" / "evidence" / "phase10-teensy-pi-idle-30s.bin")


def abort_sequence() -> bytes:
    """A synthetic stand-in for Step A, at the measured idle cadences.

    Structure: baseline IDLE -> ARMED (live frames continue, per the firmware's
    IDLE|ARMED display gate) -> ABORTED with live frames ABSENT -> acknowledge
    -> IDLE with live frames resumed.
    """
    out = bytearray()
    # The block counter must advance or the audio clock never moves and gap
    # detection cannot be exercised. 172 ticks per 500 ms STATE interval, which
    # is what the real hardware produces at 2.9025 ms/tick.
    blk = [500_000]

    def second(state_value, with_live=True, extras=b""):
        nonlocal out
        for half in range(2):
            if with_live:
                for _ in range(11):
                    out += vectors.live_frame(GEO, state=int(state_value))
            out += vectors.state(measurement_state=int(state_value),
                                 abort_reason=int(
                                     protocol.AbortReason.TIMEOUT
                                     if state_value ==
                                     protocol.MeasurementState.ABORTED
                                     else protocol.AbortReason.NONE),
                                 audio_block_counter=blk[0])
            blk[0] += 172
            if half == 0:
                out += extras
        out += vectors.hello(session_id=7)
        out += vectors.router_status()

    second(protocol.MeasurementState.IDLE)                      # baseline
    second(protocol.MeasurementState.IDLE,
           extras=vectors.status("Measuring - external stimulus"))
    second(protocol.MeasurementState.ARMED)                     # armed, live on
    # Abort: the event, then a dwell with NO live frames at all.
    out += vectors.aborted("armed timeout")
    for _ in range(5):                      # ~5 s with no live frames
        second(protocol.MeasurementState.ABORTED, with_live=False)
    # Acknowledge, then recovery with live frames back.
    out += vectors.view()
    second(protocol.MeasurementState.IDLE)
    second(protocol.MeasurementState.IDLE)
    return bytes(out)


class TestTimelineRecoversIntermediateStates(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.raw = abort_sequence()
        cls.r = replay(cls.raw, seconds=9, timeline=True)
        cls.kinds = [e["kind"] for e in cls.r["timeline"]]
        cls.details = {e["kind"]: e["detail"] for e in cls.r["timeline"]}

    def test_the_final_state_alone_would_hide_everything(self):
        """The premise. Without a timeline this capture reads as idle."""
        self.assertEqual(self.r["receiver"]["measurement_state"], "IDLE")
        self.assertFalse(self.r["receiver"]["abort_latched"])
        self.assertEqual(self.r["receiver"]["abort_reason_code"], "NONE")
        self.assertEqual(self.r["receiver"]["view"], "live")

    def test_every_intermediate_state_appears(self):
        states = [e["detail"] for e in self.r["timeline"]
                  if e["kind"] == "STATE"]
        joined = " | ".join(states)
        for expected in ("-> IDLE", "-> ARMED", "-> ABORTED"):
            self.assertIn(expected, joined,
                          f"{expected} missing from {joined}")

    def test_the_aborted_packet_and_its_reason_string_are_recorded(self):
        self.assertIn("ABORTED pkt", self.kinds)
        self.assertIn("armed timeout", self.details["ABORTED pkt"])

    def test_the_abort_latch_is_shown_setting_and_clearing(self):
        latch = [e["detail"] for e in self.r["timeline"]
                 if e["kind"] == "ABORT LATCH"]
        self.assertGreaterEqual(len(latch), 2,
                                "latch must be seen both set and cleared")
        self.assertTrue(latch[0].startswith("SET"))
        self.assertEqual(latch[-1], "CLEARED")

    def test_the_latch_sets_before_the_reason_code_is_known(self):
        """A real ordering the timeline exposes, and one I had wrong.

        My first assertion was that the latch would set WITH the reason code.
        It does not: the ABORTED packet carries the human-readable prose and
        sets the latch, while the machine-readable abort_reason_code only
        arrives with the next STATE snapshot -- up to one announcement period
        later. So there is a real interval in which the receiver knows THAT an
        abort happened and not yet WHY, in codeable form.

        Recorded as an observation of the design, not a defect: the prose is
        available immediately, so nothing is unreportable during that interval.
        """
        seq = [(e["kind"], e["detail"]) for e in self.r["timeline"]]
        latch_i = next(i for i, (k, d) in enumerate(seq)
                       if k == "ABORT LATCH" and d.startswith("SET"))
        code_i = next(i for i, (k, d) in enumerate(seq)
                      if k == "REASON CODE" and "-> TIMEOUT" in d)
        self.assertLess(latch_i, code_i,
                        "the latch is expected to set before the code is known")
        self.assertIn("reason_code NONE", seq[latch_i][1])

    def test_live_telemetry_disappearance_is_summarised_not_enumerated(self):
        # The point of summarising: this capture holds hundreds of live frames
        # and the timeline must stay readable.
        self.assertIn("LIVE STOPPED", self.kinds)
        self.assertIn("LIVE RESUMED", self.kinds)
        self.assertLess(len(self.r["timeline"]), 30,
                        "timeline should summarise, not dump every frame")
        # The point stands at any scale: dozens of live frames, one pair of
        # events describing their absence.
        self.assertGreater(self.r["packets"]["LiveFrame"], 50)
        self.assertLessEqual(
            len([e for e in self.r["timeline"] if e["kind"].startswith("LIVE")]),
            2, "one STOPPED and one RESUMED, not one event per frame")

    def test_the_view_packet_is_recorded(self):
        self.assertIn("VIEW pkt", self.kinds)
        self.assertIn("LIVE", self.details["VIEW pkt"])

    def test_ordering_is_capture_order_not_wall_clock(self):
        offsets = [e["offset"] for e in self.r["timeline"]]
        self.assertEqual(offsets, sorted(offsets),
                         "events must be emitted in byte order")

    def test_both_time_fields_are_named_to_show_their_provenance(self):
        for e in self.r["timeline"]:
            self.assertIn("t_audio", e)
            self.assertIn("t_bytes_inferred", e)
        self.assertEqual([e["t_audio"] for e in self.r["timeline"]],
                         sorted(e["t_audio"] for e in self.r["timeline"]))

    def test_every_event_carries_the_teensy_block_counter(self):
        # Attached to all events, not only STATE-triggered ones: the counter is
        # the time axis, so an event without it cannot be placed.
        for e in self.r["timeline"]:
            self.assertIsNotNone(e["block_counter"], e)
            self.assertIsNotNone(e["t_audio"], e)

    def test_audio_time_advances_while_byte_time_stalls(self):
        """The reason byte position was demoted.

        During the ABORTED dwell no live frames are sent, so the byte rate
        collapses. Audio time must keep advancing at its true rate while
        inferred byte time nearly stops.
        """
        tl = self.r["timeline"]
        stop = next(e for e in tl if e["kind"] == "LIVE STOPPED")
        resume = next(e for e in tl if e["kind"] == "LIVE RESUMED")
        d_audio = resume["t_audio"] - stop["t_audio"]
        d_bytes = resume["t_bytes_inferred"] - stop["t_bytes_inferred"]
        self.assertGreater(d_audio, 1.0,
                           "audio time must show the real dwell")
        self.assertLess(d_bytes, d_audio / 2,
                        "byte-inferred time must visibly understate it")


class TestTimelineDoesNotDisturbTheDefaultPath(unittest.TestCase):

    def test_reports_are_identical_apart_from_the_timeline_key(self):
        raw = abort_sequence()
        plain = replay(raw, seconds=9)
        with_tl = replay(raw, seconds=9, timeline=True)
        self.assertNotIn("timeline", plain)
        self.assertIn("timeline", with_tl)
        del with_tl["timeline"]
        self.assertEqual(plain, with_tl)

    @unittest.skipUnless(FIXTURE.is_file(), "hardware fixture not present")
    def test_the_hardware_fixture_report_is_unchanged(self):
        raw = FIXTURE.read_bytes()
        plain = replay(raw, seconds=30)
        with_tl = replay(raw, seconds=30, timeline=True)
        del with_tl["timeline"]
        self.assertEqual(plain, with_tl)
        self.assertTrue(plain["transport_ok"])

    @unittest.skipUnless(FIXTURE.is_file(), "hardware fixture not present")
    def test_the_idle_fixture_timeline_shows_only_the_attach(self):
        # A steady-state capture should produce a short timeline: the
        # mid-stream attach and nothing else. If this grows, something is
        # emitting events for non-events.
        r = replay(FIXTURE.read_bytes(), seconds=30, timeline=True)
        kinds = [e["kind"] for e in r["timeline"]]
        self.assertEqual(kinds, ["SESSION", "STATE", "ROUTE"])
        self.assertIn("-> 4", r["timeline"][0]["detail"])
        self.assertIn("UNKNOWN -> IDLE", r["timeline"][1]["detail"])


class TestFrameOffsets(unittest.TestCase):

    def test_offsets_are_absolute_and_account_for_discarded_bytes(self):
        pad = b"\x00" * 137
        stream = pad + vectors.hello(session_id=1) + vectors.view()
        frames = FrameScanner().feed(stream)
        self.assertEqual(len(frames), 2)
        self.assertEqual(frames[0].offset, 137)
        self.assertEqual(frames[1].offset, 137 + 47)

    def test_offsets_survive_being_fed_in_arbitrary_chunks(self):
        stream = vectors.hello(session_id=1) + vectors.view() + vectors.state()
        for chunk in (1, 3, 17, 1000):
            with self.subTest(chunk=chunk):
                sc, got = FrameScanner(), []
                for i in range(0, len(stream), chunk):
                    got += sc.feed(stream[i:i + chunk])
                self.assertEqual([f.offset for f in got], [0, 47, 55])

    @unittest.skipUnless(FIXTURE.is_file(), "hardware fixture not present")
    def test_offsets_match_the_real_fixture(self):
        # Independently established by walking the stream: the first frame
        # begins at 1664 and the first HELLO at 25377.
        frames = FrameScanner().feed(FIXTURE.read_bytes())
        self.assertEqual(frames[0].offset, 1664)
        hello = next(f for f in frames
                     if f.packet_type == protocol.PacketType.HELLO)
        self.assertEqual(hello.offset, 25377)


if __name__ == "__main__":
    unittest.main()
