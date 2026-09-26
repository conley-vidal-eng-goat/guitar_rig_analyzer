"""Receiver state model: session lifecycle, sticky ABORTED, UNKNOWN, staleness.

Every test drives the model the way the link does — real framed bytes through
FrameScanner, then into ReceiverState — so nothing here is proven against a
shortcut the live path would not take.
"""

import unittest

from analyzer_link import protocol, packets
from analyzer_link.framing import FrameScanner
from analyzer_link.state import ReceiverState, View, UNKNOWN, SessionEnd

from . import vectors

GEO = protocol.Geometry()


class StateHarness(unittest.TestCase):
    """Feeds framed bytes in, exactly as a serial reader would."""

    def setUp(self):
        self.scanner = FrameScanner()
        self.state = ReceiverState()
        self.now = 0

    def feed(self, *streams, advance_ms=10):
        out = []
        for stream in streams:
            self.now += advance_ms
            for frame in self.scanner.feed(stream):
                out.append(self.state.on_frame(frame, now_ms=self.now))
        return out

    def establish(self, session_id=1):
        self.feed(vectors.hello(session_id=session_id))

    def live(self, state_value, **kwargs):
        return vectors.live_frame(GEO, state=int(state_value), **kwargs)


# =============================================================================
# D4 — nothing is promoted before a session exists
# =============================================================================

class TestPreHelloIsNotPromoted(StateHarness):

    def test_state_starts_unknown_and_unestablished(self):
        self.assertFalse(self.state.session_established)
        self.assertIs(self.state.measurement_state, UNKNOWN)
        self.assertFalse(self.state.state_known)
        self.assertIs(self.state.view, View.NONE)
        self.assertIsNone(self.state.geometry)

    def test_live_frame_before_hello_is_not_promoted(self):
        self.feed(self.live(protocol.MeasurementState.IDLE))
        self.assertIsNone(self.state.latest_live)
        self.assertIs(self.state.measurement_state, UNKNOWN)
        self.assertIs(self.state.view, View.NONE)

    def test_geometry_independent_packets_are_decoded_and_counted_pre_hello(self):
        # D4 refuses PROMOTION; it does not throw away link evidence. A packet
        # that needs no geometry still decodes, so the operator can see traffic
        # is flowing before the session is identified.
        self.feed(vectors.status("hello there"), vectors.view(),
                  vectors.router_status())
        self.assertEqual(self.state.health.packets_decoded, 3)
        self.assertEqual(self.state.health.not_promoted_pre_hello, 3)
        self.assertEqual(self.state.health.decode_errors, 0)
        # Promotion refused: none of it reached instrument state.
        self.assertIsNone(self.state.router)
        self.assertIs(self.state.view, View.NONE)
        self.assertEqual(len(self.state.status_log), 0)

    def test_live_frame_before_hello_cannot_be_decoded_at_all(self):
        # Worth pinning, because it looks like it should work: a LIVE_FRAME's
        # array lengths ARE self-describing from payload_length. But
        # decim_ratio is NOT, and without it the per-bin coverage nibbles
        # cannot be interpreted — "2 of ? source bins clamped" is not a
        # renderable fact. Deriving a ratio here would be assuming geometry,
        # which D4 forbids. So it is counted, not guessed.
        self.feed(self.live(protocol.MeasurementState.IDLE))
        self.assertEqual(self.state.health.geometry_unavailable, 1)
        self.assertEqual(self.state.health.decode_errors, 0)
        self.assertIsNone(self.state.latest_live)
        self.assertIs(self.state.measurement_state, UNKNOWN)

    def test_result_before_hello_is_counted_as_geometry_unavailable(self):
        # Expected on a mid-session attach — not a stream error.
        self.feed(vectors.result(GEO))
        self.assertEqual(self.state.health.geometry_unavailable, 1)
        self.assertEqual(self.state.health.decode_errors, 0)
        self.assertIsNone(self.state.latest_result)

    def test_connection_alone_never_implies_idle(self):
        self.feed(vectors.status("Ready"), vectors.view(),
                  self.live(protocol.MeasurementState.IDLE))
        self.assertIs(self.state.measurement_state, UNKNOWN)

    def test_hello_establishes_the_session_but_not_a_state(self):
        self.establish()
        self.assertTrue(self.state.session_established)
        self.assertEqual(self.state.geometry, GEO)
        # HELLO identifies the instrument. It says nothing about measurement.
        self.assertIs(self.state.measurement_state, UNKNOWN)
        self.assertIs(self.state.view, View.NONE)

    def test_telemetry_is_promoted_once_the_session_exists(self):
        self.establish()
        self.feed(self.live(protocol.MeasurementState.IDLE))
        self.assertIsNotNone(self.state.latest_live)
        self.assertIs(self.state.measurement_state,
                      protocol.MeasurementState.IDLE)


# =============================================================================
# Same-session HELLO idempotence
# =============================================================================

class TestHelloIdempotence(StateHarness):

    def test_repeated_same_session_hello_changes_nothing(self):
        self.establish(session_id=5)
        self.feed(vectors.result(GEO), vectors.aborted("TIMEOUT"))
        before = (self.state.view, self.state.abort_latched,
                  self.state.abort_reason, self.state.latest_result)

        for _ in range(5):
            self.feed(vectors.hello(session_id=5))

        self.assertEqual(self.state.view, before[0])
        self.assertEqual(self.state.abort_latched, before[1])
        self.assertEqual(self.state.abort_reason, before[2])
        self.assertIs(self.state.latest_result, before[3])
        self.assertEqual(self.state.health.session_changes, 0)
        self.assertEqual(self.state.health.hello_count, 6)

    def test_reannouncement_does_not_clear_a_sticky_abort(self):
        # The exact reconnect case: announcements keep arriving at 1 Hz while
        # the abort is still latched and unacknowledged.
        self.establish(session_id=5)
        self.feed(vectors.aborted("CLIP"))
        for _ in range(10):
            self.feed(vectors.hello(session_id=5), advance_ms=1000)
        self.assertTrue(self.state.abort_latched)
        self.assertEqual(self.state.abort_reason, "CLIP")
        self.assertIs(self.state.measurement_state,
                      protocol.MeasurementState.ABORTED)


# =============================================================================
# D2 — sticky ABORTED, and what may clear it
# =============================================================================

class TestStickyAbort(StateHarness):

    def setUp(self):
        super().setUp()
        self.establish()
        self.feed(vectors.aborted("ROUTE_CHANGED"))

    def test_abort_latches(self):
        self.assertTrue(self.state.abort_latched)
        self.assertEqual(self.state.abort_reason, "ROUTE_CHANGED")
        self.assertIs(self.state.measurement_state,
                      protocol.MeasurementState.ABORTED)
        self.assertIs(self.state.view, View.ABORTED)

    def test_silence_does_not_clear_it(self):
        self.now += 60_000
        self.assertTrue(self.state.is_stale(self.now))
        self.assertTrue(self.state.abort_latched)
        self.assertIs(self.state.measurement_state,
                      protocol.MeasurementState.ABORTED)

    def test_status_messages_do_not_clear_it(self):
        self.feed(vectors.status("Ready"), vectors.status("VIEW:LIVE"))
        self.assertTrue(self.state.abort_latched)

    def test_view_live_moves_the_view_but_does_NOT_clear_the_abort(self):
        # presentation_restoreLive() fires on BOTH the abort-acknowledge path
        # (.ino:590) and the return-from-RESULT path (.ino:600). "Show the
        # live view" is not "the engine is no longer ABORTED".
        self.feed(vectors.view())
        self.assertIs(self.state.view, View.LIVE)
        self.assertTrue(self.state.abort_latched)
        self.assertIs(self.state.measurement_state,
                      protocol.MeasurementState.ABORTED)

    def test_authoritative_idle_observation_clears_it(self):
        # The firmware leaves ABORTED only via acknowledgeAbort() -> IDLE, so
        # an authoritative IDLE observation IS evidence of acknowledgement.
        self.feed(self.live(protocol.MeasurementState.IDLE))
        self.assertFalse(self.state.abort_latched)
        self.assertIsNone(self.state.abort_reason)
        self.assertIs(self.state.measurement_state,
                      protocol.MeasurementState.IDLE)

    def test_armed_alone_does_not_clear_it(self):
        # Deliberate: the ruling named IDLE specifically. ARMED is logically
        # incompatible with ABORTED too, but that is a second inference and is
        # not taken here.
        self.feed(self.live(protocol.MeasurementState.ARMED))
        self.assertTrue(self.state.abort_latched)

    def test_a_new_abort_replaces_the_reason(self):
        self.feed(vectors.aborted("TIMEOUT"))
        self.assertEqual(self.state.abort_reason, "TIMEOUT")
        self.assertTrue(self.state.abort_latched)


# =============================================================================
# D3 — session rollover
# =============================================================================

class TestSessionRollover(StateHarness):

    def test_changed_session_resets_to_unknown_not_idle(self):
        self.establish(session_id=1)
        self.feed(self.live(protocol.MeasurementState.IDLE))
        self.assertIs(self.state.measurement_state,
                      protocol.MeasurementState.IDLE)

        self.feed(vectors.hello(session_id=2))
        self.assertIs(self.state.measurement_state, UNKNOWN)
        self.assertFalse(self.state.state_known)
        self.assertIs(self.state.view, View.NONE)

    def test_session_dependent_state_is_invalidated(self):
        self.establish(session_id=1)
        self.feed(vectors.result(GEO), vectors.router_status(),
                  vectors.status("Calibration loaded"))
        self.assertIsNotNone(self.state.latest_result)
        self.assertIsNotNone(self.state.router)
        self.assertEqual(len(self.state.status_log), 1)

        self.feed(vectors.hello(session_id=2))
        self.assertIsNone(self.state.latest_result)
        self.assertIsNone(self.state.latest_live)
        self.assertIsNone(self.state.router)
        self.assertEqual(len(self.state.status_log), 0)

    def test_new_geometry_is_adopted_from_the_new_hello(self):
        self.establish(session_id=1)
        self.feed(vectors.hello(session_id=2, live_bins=256, fft_bins=512))
        self.assertEqual(self.state.geometry.live_bins, 256)
        self.assertEqual(self.state.geometry.decim_ratio, 2)

    def test_session_ending_while_aborted_is_recorded_not_lost(self):
        self.establish(session_id=1)
        self.feed(vectors.aborted("CLIP"))
        self.feed(vectors.hello(session_id=2))

        # Current state: the old abort is gone, because it described a Teensy
        # that no longer exists.
        self.assertFalse(self.state.abort_latched)
        self.assertIsNone(self.state.abort_reason)

        # History: what is actually known is that the session ended before an
        # acknowledgement was observed.
        self.assertEqual(len(self.state.session_history), 1)
        record = self.state.session_history[-1]
        self.assertIsInstance(record, SessionEnd)
        self.assertEqual(record.session_id, 1)
        self.assertTrue(record.ended_with_abort_latched)
        self.assertEqual(record.abort_reason, "CLIP")
        self.assertIs(record.measurement_state_at_end,
                      protocol.MeasurementState.ABORTED)

    def test_clean_session_end_is_recorded_without_an_abort_flag(self):
        self.establish(session_id=1)
        self.feed(self.live(protocol.MeasurementState.IDLE))
        self.feed(vectors.hello(session_id=2))
        record = self.state.session_history[-1]
        self.assertFalse(record.ended_with_abort_latched)
        self.assertIsNone(record.abort_reason)

    def test_history_is_bounded(self):
        self.establish(session_id=0)
        for sid in range(1, 30):
            self.feed(vectors.hello(session_id=sid))
        self.assertLessEqual(len(self.state.session_history), 8)
        self.assertEqual(self.state.health.session_changes, 29)

    def test_session_id_zero_is_a_real_session(self):
        # The firmware counter wraps 0xFFFF -> 0 and a blank EEPROM's first
        # boot lands on 0. Treating 0 as "absent" would miss a reboot.
        self.establish(session_id=0xFFFF)
        self.feed(self.live(protocol.MeasurementState.IDLE))
        self.feed(vectors.hello(session_id=0))
        self.assertEqual(self.state.session_id, 0)
        self.assertEqual(self.state.health.session_changes, 1)
        self.assertIs(self.state.measurement_state, UNKNOWN)


# =============================================================================
# Link staleness is a link fact
# =============================================================================

class TestStaleness(StateHarness):

    def test_stale_before_anything_arrives(self):
        self.assertTrue(self.state.is_stale(0))

    def test_not_stale_while_announcements_keep_arriving(self):
        self.establish()
        for _ in range(5):
            self.feed(vectors.hello(session_id=1), advance_ms=1000)
        self.assertFalse(self.state.is_stale(self.now))

    def test_one_missed_announcement_is_not_stale(self):
        # Announcements are best-effort and drop under backpressure by design.
        self.establish()
        self.assertFalse(
            self.state.is_stale(self.now + protocol.HELLO_REANNOUNCE_MS + 50))

    def test_goes_stale_after_sustained_silence(self):
        self.establish()
        self.assertTrue(self.state.is_stale(self.now + 10_000))

    def test_staleness_does_not_alter_measurement_state(self):
        self.establish()
        self.feed(self.live(protocol.MeasurementState.CAPTURE))
        captured = self.state.measurement_state
        self.assertTrue(self.state.is_stale(self.now + 60_000))
        self.assertIs(self.state.measurement_state, captured)
        self.assertIsNot(self.state.measurement_state, UNKNOWN)

    def test_staleness_does_not_clear_an_abort(self):
        self.establish()
        self.feed(vectors.aborted("TIMEOUT"))
        self.assertTrue(self.state.is_stale(self.now + 60_000))
        self.assertTrue(self.state.abort_latched)


# =============================================================================
# Robustness — a receiver that dies stops rendering
# =============================================================================

class TestRobustness(StateHarness):

    def test_unknown_packet_is_counted_and_never_promoted(self):
        self.establish()
        self.feed(vectors.unknown(0xFE, b"future"))
        self.assertEqual(self.state.health.unknown_packets, 1)
        self.assertIsNone(self.state.latest_live)
        self.assertIsNone(self.state.latest_result)

    def test_malformed_payload_is_counted_not_raised(self):
        # CRC-valid but self-inconsistent: a decode error, not a wire error.
        bad = vectors.frame(protocol.PacketType.ROUTER_STATUS,
                            bytes([0x01, 1, 0, 0, 1, 0, 90]) + b"abc")
        self.establish()
        self.feed(bad)
        self.assertEqual(self.state.health.decode_errors, 1)
        self.assertIsNone(self.state.router)

    def test_inconsistent_hello_does_not_establish_a_session(self):
        payload = bytearray(vectors.hello_payload())
        payload[6:8] = (7).to_bytes(2, "little")      # decim_ratio lies
        self.feed(vectors.frame(protocol.PacketType.HELLO, bytes(payload)))
        self.assertFalse(self.state.session_established)
        self.assertEqual(self.state.health.decode_errors, 1)

    def test_result_view_does_not_claim_a_measurement_state(self):
        # By the time a RESULT is parsed the Teensy may have moved on, so
        # receiving one is not an observation of the current state.
        self.establish()
        self.feed(vectors.result(GEO))
        self.assertIs(self.state.view, View.RESULT)
        self.assertIs(self.state.measurement_state, UNKNOWN)


if __name__ == "__main__":
    unittest.main()


# =============================================================================
# TODO-57 — the authoritative STATE snapshot
# =============================================================================

class TestStatePacket(StateHarness):
    """STATE is what makes measurement state observable at all outside
    IDLE|ARMED, and what repairs a dropped ABORTED."""

    def setUp(self):
        super().setUp()
        self.establish()

    def test_state_is_observable_where_live_frames_never_flow(self):
        # The whole point. LIVE_FRAME is gated to IDLE|ARMED, so before STATE
        # these four were unobservable to a Pi.
        for value in (protocol.MeasurementState.CAPTURE,
                      protocol.MeasurementState.PROCESSING,
                      protocol.MeasurementState.RESULT,
                      protocol.MeasurementState.EXPORTING):
            with self.subTest(state=value.name):
                self.feed(vectors.state(measurement_state=int(value)))
                self.assertIs(self.state.measurement_state, value)

    def test_a_late_attach_learns_a_sticky_abort_without_the_event(self):
        # The reconnect case. No ABORTED packet is ever seen — only the
        # periodic snapshot — and the Pi still learns the instrument is
        # latched, and why.
        fresh = ReceiverState()
        scanner = FrameScanner()
        for f in scanner.feed(vectors.hello(session_id=1)
                              + vectors.state(
                                  measurement_state=int(
                                      protocol.MeasurementState.ABORTED),
                                  abort_reason=int(
                                      protocol.AbortReason.CLIP_SOURCE))):
            fresh.on_frame(f, now_ms=0)

        self.assertIs(fresh.measurement_state,
                      protocol.MeasurementState.ABORTED)
        self.assertTrue(fresh.abort_latched)
        self.assertIs(fresh.abort_reason_code, protocol.AbortReason.CLIP_SOURCE)
        # It knows WHY but was never told the wording. That is honest, not a bug.
        self.assertIsNone(fresh.abort_reason)
        self.assertIs(fresh.view, View.ABORTED)

    def test_a_dropped_aborted_event_self_heals(self):
        self.feed(vectors.state(
            measurement_state=int(protocol.MeasurementState.ABORTED),
            abort_reason=int(protocol.AbortReason.ROUTE_CHANGED)))
        self.assertTrue(self.state.abort_latched)
        self.assertIs(self.state.abort_reason_code,
                      protocol.AbortReason.ROUTE_CHANGED)

    def test_the_aborted_event_supplies_prose_the_snapshot_cannot(self):
        self.feed(vectors.aborted("Route changed mid-capture"),
                  vectors.state(
                      measurement_state=int(protocol.MeasurementState.ABORTED),
                      abort_reason=int(protocol.AbortReason.ROUTE_CHANGED)))
        self.assertEqual(self.state.abort_reason, "Route changed mid-capture")
        self.assertIs(self.state.abort_reason_code,
                      protocol.AbortReason.ROUTE_CHANGED)

    def test_an_idle_snapshot_clears_the_latch_and_the_code(self):
        self.feed(vectors.aborted("CLIP"))
        self.assertTrue(self.state.abort_latched)
        self.feed(vectors.state(
            measurement_state=int(protocol.MeasurementState.IDLE)))
        self.assertFalse(self.state.abort_latched)
        self.assertIsNone(self.state.abort_reason)
        self.assertIs(self.state.abort_reason_code, protocol.AbortReason.NONE)

    def test_a_capture_snapshot_does_not_clear_a_latch(self):
        # Only IDLE clears. Ruled that way deliberately.
        self.feed(vectors.aborted("CLIP"))
        self.feed(vectors.state(
            measurement_state=int(protocol.MeasurementState.CAPTURE)))
        self.assertTrue(self.state.abort_latched)

    def test_state_is_not_promoted_before_hello(self):
        fresh = ReceiverState()
        scanner = FrameScanner()
        for f in scanner.feed(vectors.state(
                measurement_state=int(protocol.MeasurementState.CAPTURE))):
            fresh.on_frame(f, now_ms=0)
        self.assertIs(fresh.measurement_state, UNKNOWN)
        self.assertEqual(fresh.health.not_promoted_pre_hello, 1)

    def test_session_change_clears_the_code_as_well_as_the_latch(self):
        self.feed(vectors.state(
            measurement_state=int(protocol.MeasurementState.ABORTED),
            abort_reason=int(protocol.AbortReason.TIMEOUT)))
        self.feed(vectors.hello(session_id=2))
        self.assertIs(self.state.abort_reason_code, protocol.AbortReason.NONE)
        self.assertIs(self.state.measurement_state, UNKNOWN)
        record = self.state.session_history[-1]
        self.assertIs(record.abort_reason_code, protocol.AbortReason.TIMEOUT)

    def test_block_counter_is_carried_but_never_compared(self):
        # It is a timestamp, not a sequence number: the firmware derives it
        # from micros(), so it wraps roughly every 71.6 minutes. The model
        # records it and deliberately implements no newer-than logic.
        self.feed(vectors.state(audio_block_counter=1_400_000))
        self.feed(vectors.state(audio_block_counter=7))   # wrapped
        # The later observation wins on arrival order, not on the counter.
        self.assertIs(self.state.measurement_state,
                      protocol.MeasurementState.IDLE)

    def test_an_unknown_abort_reason_is_a_decode_error_not_a_guess(self):
        bad = vectors.frame(protocol.PacketType.STATE,
                            vectors.state_payload(abort_reason=99))
        self.feed(bad)
        self.assertEqual(self.state.health.decode_errors, 1)
