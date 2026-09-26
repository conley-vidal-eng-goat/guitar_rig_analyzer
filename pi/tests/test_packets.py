"""Packet decoding: every field, the clamp contract, and forward compatibility.

Covers runbook Phase 10 step 9 (unknown-packet tolerance) at the offline
layer, and the step 7 clamp contract at the data level — step 7 itself is a
rendering check on real hardware.
"""

import math
import unittest

from analyzer_link import protocol, packets
from analyzer_link.framing import FrameScanner

from . import vectors


def decode_one(stream: bytes, geometry=None):
    scanner = FrameScanner()
    frames = scanner.feed(stream)
    assert len(frames) == 1, f"expected 1 frame, got {len(frames)}"
    return packets.decode(frames[0], geometry)


class TestHello(unittest.TestCase):

    def test_all_fields_round_trip(self):
        h = decode_one(vectors.hello(capabilities=0x03, firmware="0.6.0"))
        self.assertIsInstance(h, packets.Hello)
        self.assertEqual(h.protocol_version, 2)
        self.assertEqual(h.live_bins, 128)
        self.assertEqual(h.fft_bins, 512)
        self.assertEqual(h.decim_ratio, 4)
        self.assertEqual(h.baud_rate, 460800)
        self.assertEqual(h.sample_rate, 44100)
        self.assertEqual(h.insights_max, 12)
        self.assertEqual(h.firmware_version, "0.6.0")
        self.assertTrue(h.compatible)

    def test_capability_bitmap_distinguishes_off_from_absent(self):
        # Audit T4. A receiver must not render a control for a capability the
        # build does not contain.
        none = decode_one(vectors.hello(capabilities=0x00))
        self.assertNotIn(protocol.Capability.MONITOR_MODE, none.capabilities)
        self.assertNotIn(protocol.Capability.MODE_PRECISION, none.capabilities)

        both = decode_one(vectors.hello(capabilities=0x03))
        self.assertIn(protocol.Capability.DUT_INJECTION, both.capabilities)
        self.assertIn(protocol.Capability.MONITOR_MODE, both.capabilities)

    def test_geometry_comes_from_the_packet_not_from_a_constant(self):
        # TODO-36: "a receiver that takes its geometry from HELLO is immune"
        # to the cadence/bin-count lever being pulled by T1.
        h = decode_one(vectors.hello(live_bins=256, fft_bins=512))
        self.assertEqual(h.geometry.live_bins, 256)
        self.assertEqual(h.geometry.decim_ratio, 2)

    def test_incompatible_version_is_reported_not_guessed(self):
        h = decode_one(vectors.hello(protocol_version=3))
        self.assertFalse(h.compatible)

    def test_inconsistent_geometry_is_rejected(self):
        payload = vectors.hello_payload(live_bins=128, fft_bins=512)
        bad = bytearray(payload)
        bad[6:8] = (7).to_bytes(2, "little")            # decim_ratio lies
        with self.assertRaises(packets.DecodeError):
            packets.decode_hello(bytes(bad))

    def test_zero_geometry_is_rejected(self):
        payload = bytearray(vectors.hello_payload())
        payload[2:4] = (0).to_bytes(2, "little")        # live_bins = 0
        with self.assertRaises(packets.DecodeError):
            packets.decode_hello(bytes(payload))


class TestHelloSession(unittest.TestCase):
    """session_id semantics (TODO-56).

    HELLO is now re-announced ~1 Hz instead of being sent once at boot, so a
    receiver sees many of them. These tests pin down the one thing that makes
    a repeat distinguishable from a restart.
    """

    def test_session_id_round_trips(self):
        h = decode_one(vectors.hello(session_id=0xBEEF))
        self.assertEqual(h.session_id, 0xBEEF)

    def test_repeated_hello_with_the_same_session_is_the_same_session(self):
        first = decode_one(vectors.hello(session_id=7))
        again = decode_one(vectors.hello(session_id=7))
        self.assertEqual(first.session_id, again.session_id)
        # A routine re-announcement must not look like anything changed.
        self.assertEqual(first, again)

    def test_a_changed_session_id_is_detectable(self):
        before = decode_one(vectors.hello(session_id=7))
        after = decode_one(vectors.hello(session_id=8))
        self.assertNotEqual(before.session_id, after.session_id)

    def test_session_id_is_independent_of_every_other_field(self):
        # A reboot that changes nothing else must still be detectable: same
        # firmware, same geometry, same capabilities, different session.
        before = decode_one(vectors.hello(session_id=41))
        after = decode_one(vectors.hello(session_id=42))
        self.assertEqual(before.geometry, after.geometry)
        self.assertEqual(before.firmware_version, after.firmware_version)
        self.assertEqual(before.capabilities, after.capabilities)
        self.assertNotEqual(before.session_id, after.session_id)

    def test_session_id_zero_is_a_legitimate_value(self):
        # The firmware counter wraps 0xFFFF -> 0, and a blank EEPROM's first
        # boot lands on 0. A receiver must not treat 0 as "absent".
        h = decode_one(vectors.hello(session_id=0))
        self.assertEqual(h.session_id, 0)

    def test_session_id_occupies_bytes_18_19_little_endian(self):
        # Pins the wire position, not just the round trip. If this field ever
        # moved, the capability bitmap after it would decode as garbage.
        payload = vectors.hello_payload(session_id=0x1234)
        self.assertEqual(payload[18], 0x34)
        self.assertEqual(payload[19], 0x12)


class TestLiveFrame(unittest.TestCase):

    def setUp(self):
        self.geo = protocol.Geometry()

    def test_scalar_fields_round_trip(self):
        f = decode_one(
            vectors.live_frame(self.geo, state=2, flags=0x05, block=1234,
                               peak_source=-9.5, peak_return=-14.25,
                               confidence=0.73, clamped_count=17),
            self.geo)
        self.assertEqual(f.measurement_state, protocol.MeasurementState.CAPTURE)
        self.assertTrue(f.source_clip)
        self.assertFalse(f.return_clip)
        self.assertTrue(f.tf_persistence_active)
        self.assertEqual(f.output_block_number, 1234)
        self.assertAlmostEqual(f.peak_source_dbfs, -9.5, places=5)
        self.assertAlmostEqual(f.peak_return_dbfs, -14.25, places=5)
        self.assertAlmostEqual(f.tf_confidence, 0.73, places=5)
        self.assertEqual(f.tf_clamped_count, 17)

    def test_array_lengths_follow_hello_geometry(self):
        geo = protocol.Geometry(live_bins=64, fft_bins=512, decim_ratio=8)
        f = decode_one(vectors.live_frame(geo), geo)
        self.assertEqual(len(f.fft_source), 64)
        self.assertEqual(len(f.tf_db), 64)
        self.assertEqual(len(f.coverage), 64)

    def test_wrong_length_for_declared_geometry_is_rejected(self):
        # A live frame sized for 128 bins decoded as 64 must fail loudly, not
        # silently plot the first half of the array.
        wrong = protocol.Geometry(live_bins=64, fft_bins=512, decim_ratio=8)
        with self.assertRaises(packets.DecodeError):
            decode_one(vectors.live_frame(self.geo), wrong)

    def test_live_frame_before_hello_is_refused(self):
        with self.assertRaises(packets.GeometryUnknown):
            decode_one(vectors.live_frame(self.geo), None)

    def test_nan_in_tf_db_survives_decoding(self):
        tf = [-3.0] * self.geo.live_bins
        tf[5] = math.nan
        f = decode_one(vectors.live_frame(self.geo, tf_db=tf), self.geo)
        self.assertTrue(math.isnan(f.tf_db[5]))
        self.assertFalse(math.isnan(f.tf_db[4]))


class TestClampContract(unittest.TestCase):
    """The rendering contract from data_sender.h, exercised bin by bin.

    This is the defect protocol v2 exists to prevent: on 2026-09-07 a consumer
    that ignored clamp state reported "1kHz=-24.0dB" in 33 of 33 windows as
    though the saturation rail were a measurement.
    """

    def setUp(self):
        self.geo = protocol.Geometry()                  # ratio 4
        ratio = self.geo.decim_ratio
        cov = [(0 << 4) | ratio] * self.geo.live_bins   # clean, full coverage
        cov[10] = (ratio << 4) | ratio                  # fully clamped
        cov[11] = (0 << 4) | 0                          # no valid source bins
        cov[12] = (2 << 4) | 3                          # partially saturated
        cov[13] = (0 << 4) | 2                          # partial coverage
        self.frame = decode_one(
            vectors.live_frame(self.geo, coverage=cov), self.geo)

    def test_clean_bin_plots_normally(self):
        c = self.frame.coverage[0]
        self.assertTrue(c.plottable)
        self.assertFalse(c.saturated)
        self.assertFalse(c.pen_lift)
        self.assertFalse(c.partial_coverage)

    def test_fully_clamped_bin_must_not_be_plotted_as_a_measurement(self):
        c = self.frame.coverage[10]
        self.assertTrue(c.saturated)
        self.assertFalse(c.plottable)

    def test_zero_valid_bin_is_a_pen_lift(self):
        c = self.frame.coverage[11]
        self.assertTrue(c.pen_lift)
        self.assertFalse(c.plottable)

    def test_partially_saturated_bin_is_plotted_but_marked(self):
        c = self.frame.coverage[12]
        self.assertTrue(c.partially_saturated)
        self.assertTrue(c.plottable)
        self.assertFalse(c.saturated)

    def test_partial_coverage_is_plotted_but_marked(self):
        c = self.frame.coverage[13]
        self.assertTrue(c.partial_coverage)
        self.assertTrue(c.plottable)
        self.assertFalse(c.pen_lift)

    def test_nibbles_are_not_transposed(self):
        # high = clamped, low = valid. Transposing them would turn every
        # railed bin into a plottable one, which is the original defect.
        c = self.frame.coverage[12]
        self.assertEqual(c.clamped, 2)
        self.assertEqual(c.valid, 3)


class TestResult(unittest.TestCase):

    def setUp(self):
        self.geo = protocol.Geometry()

    def test_teensy_verdicts_round_trip_unchanged(self):
        r = decode_one(vectors.result(self.geo, result_valid=True,
                                      quality=int(protocol.ResultQuality.GOOD),
                                      flags=0x03,
                                      calibration_warnings=0x12),
                       self.geo)
        self.assertTrue(r.result_valid)
        self.assertEqual(r.result_quality, protocol.ResultQuality.GOOD)
        self.assertTrue(r.clip_detected)
        self.assertTrue(r.calibration_applied)
        self.assertFalse(r.generator_active)
        self.assertIn(protocol.CalibrationWarning.LINE_IN_LEVEL_MISMATCH,
                      r.calibration_warnings)
        self.assertIn(protocol.CalibrationWarning.HARD_PARAMETER_MISMATCH,
                      r.calibration_warnings)

    def test_result_valid_is_read_not_derived_from_quality(self):
        # Audit R1. The Pi must never re-derive validity from the quality enum.
        r = decode_one(vectors.result(
            self.geo, result_valid=False,
            quality=int(protocol.ResultQuality.EXCELLENT)), self.geo)
        self.assertFalse(r.result_valid)
        self.assertEqual(r.result_quality, protocol.ResultQuality.EXCELLENT)

    def test_provenance_and_context_are_present(self):
        # Audit R2/R6: a calibrated result must not display with its own
        # provenance silently dropped, and Compare/Recall needs line_in_level.
        r = decode_one(vectors.result(
            self.geo, provenance="external loopback 2026-09-26",
            line_in_level=7, fft_size=4096), self.geo)
        self.assertEqual(r.calibration_provenance,
                         "external loopback 2026-09-26")
        self.assertEqual(r.line_in_level, 7)
        self.assertEqual(r.fft_size, 4096)

    def test_arrays_are_the_canonical_grid_not_fft_size(self):
        # MODE_PRECISION raises fft_size to 4096 but the result stays on the
        # 512-bin canonical grid. Confusing the two mis-slices every array.
        r = decode_one(vectors.result(self.geo, fft_size=4096), self.geo)
        self.assertEqual(r.fft_size, 4096)
        for arr in (r.tf_cal_mag_db, r.tf_cal_phase_rad,
                    r.group_delay_ms, r.coherence):
            self.assertEqual(len(arr), 512)

    def test_nan_survives_in_the_result_arrays(self):
        r = decode_one(vectors.result(self.geo), self.geo)
        self.assertTrue(math.isnan(r.tf_cal_mag_db[3]))
        self.assertFalse(math.isnan(r.tf_cal_mag_db[4]))

    def test_insight_mode_distinction_is_preserved(self):
        entries = [
            vectors.insight_entry(0, 0, 1000.0, -3.0, "Latency", "2.1 ms"),
            vectors.insight_entry(1, 2, 250.0, -8.0, "Treble loss",
                                  "Consider a shorter cable"),
        ]
        r = decode_one(vectors.result(self.geo, insights=entries), self.geo)
        self.assertEqual(len(r.insights), 2)
        self.assertEqual(r.insights[0].mode, protocol.InsightMode.MEASUREMENT)
        self.assertEqual(r.insights[0].severity, protocol.InsightSeverity.INFO)
        self.assertEqual(r.insights[0].title, "Latency")
        self.assertEqual(r.insights[1].mode, protocol.InsightMode.ADVISORY)
        self.assertEqual(r.insights[1].severity, protocol.InsightSeverity.ALERT)
        self.assertEqual(r.insights[1].detail, "Consider a shorter cable")

    def test_result_before_hello_is_refused_with_a_specific_error(self):
        # Not a stream error: a receiver that connects mid-session sees this.
        with self.assertRaises(packets.GeometryUnknown):
            decode_one(vectors.result(self.geo), None)

    def test_insight_count_above_the_firmware_maximum_is_rejected(self):
        payload = bytearray(vectors.result_payload(self.geo))
        payload[protocol.RESULT_FIXED_BYTES + 512 * 16] = 99
        with self.assertRaises(packets.DecodeError):
            packets.decode_result(bytes(payload), self.geo)


class TestEventPackets(unittest.TestCase):

    def test_status(self):
        s = decode_one(vectors.status("Calibration loaded"))
        self.assertEqual(s.message, "Calibration loaded")

    def test_aborted_carries_the_reason(self):
        a = decode_one(vectors.aborted("ROUTE_CHANGED"))
        self.assertIsInstance(a, packets.Aborted)
        self.assertEqual(a.reason, "ROUTE_CHANGED")

    def test_view_change(self):
        v = decode_one(vectors.view())
        self.assertTrue(v.is_live)

    def test_router_status_current_hardware_is_all_unknown(self):
        # The default vector mirrors the real instrument: no detect conductor
        # on any jack, so every jack must read UNKNOWN -- never ABSENT.
        r = decode_one(vectors.router_status(return_source=2,
                                             description="XLR return"))
        for jack in protocol.Jack:
            self.assertIs(r.detect(jack), protocol.Detect.UNKNOWN)
        self.assertFalse(r.any_detector_available)
        self.assertEqual(r.return_source, protocol.ReturnSource.XLR)
        self.assertEqual(r.description, "XLR return")

    def test_detection_is_three_valued(self):
        # instrument + return_ts have detectors; only instrument has a plug.
        r = decode_one(vectors.router_status(presence=0x01, available=0x05))
        self.assertIs(r.detect(protocol.Jack.INSTRUMENT_IN),
                      protocol.Detect.PRESENT)
        self.assertIs(r.detect(protocol.Jack.RETURN_TS),
                      protocol.Detect.ABSENT)
        self.assertIs(r.detect(protocol.Jack.RIG_SEND),
                      protocol.Detect.UNKNOWN)
        self.assertIs(r.detect(protocol.Jack.RETURN_XLR),
                      protocol.Detect.UNKNOWN)

    def test_absent_and_unknown_are_never_conflated(self):
        # The whole reason two masks exist. Same presence byte, different
        # availability, different meaning.
        no_detector = decode_one(vectors.router_status(presence=0x00,
                                                       available=0x00))
        detector_no_plug = decode_one(vectors.router_status(presence=0x00,
                                                            available=0x0F))
        self.assertIs(no_detector.detect(protocol.Jack.RIG_SEND),
                      protocol.Detect.UNKNOWN)
        self.assertIs(detector_no_plug.detect(protocol.Jack.RIG_SEND),
                      protocol.Detect.ABSENT)

    def test_presence_without_availability_is_rejected(self):
        # The producer masks before sending. A bit set without its availability
        # bit means the two sides disagree about the contract.
        with self.assertRaises(packets.DecodeError):
            packets.decode_router_status(
                vectors.router_payload(presence=0x02, available=0x00))

    def test_return_source_is_independent_of_presence(self):
        # ADR-004: presence must never determine the selected return. An XLR
        # plug detected while TS is selected is a legitimate, renderable state.
        r = decode_one(vectors.router_status(presence=0x08, available=0x08,
                                             return_source=1))
        self.assertIs(r.detect(protocol.Jack.RETURN_XLR),
                      protocol.Detect.PRESENT)
        self.assertEqual(r.return_source, protocol.ReturnSource.TS)

    def test_removed_fields_are_not_reconstructed(self):
        r = decode_one(vectors.router_status())
        self.assertFalse(hasattr(r, "route_valid"))
        self.assertFalse(hasattr(r, "can_inject"))

    def test_router_description_length_mismatch_is_rejected(self):
        # A self-inconsistent payload that is nonetheless CRC-valid: the
        # description length byte says 90, only 3 bytes follow. Built directly
        # rather than by corrupting a frame, because corrupting one would fail
        # at the CRC and never reach the decoder under test.
        payload = bytes([0x00, 0x00, 1, 0, 0, 0, 90]) + b"abc"
        with self.assertRaises(packets.DecodeError):
            packets.decode_router_status(payload)

    def test_oversized_description_length_is_rejected(self):
        payload = bytes([0x00, 0x00, 1, 0, 0, 0, 200]) + b"x" * 200
        with self.assertRaises(packets.DecodeError):
            packets.decode_router_status(payload)

    def test_oversized_string_payload_is_rejected(self):
        with self.assertRaises(packets.DecodeError):
            packets.decode_string_payload(b"x" * 201)


class TestStateDecoding(unittest.TestCase):

    def test_fields_round_trip(self):
        p = decode_one(vectors.state(
            measurement_state=int(protocol.MeasurementState.PROCESSING),
            abort_reason=int(protocol.AbortReason.NONE),
            audio_block_counter=987654))
        self.assertIsInstance(p, packets.StatePacket)
        self.assertIs(p.measurement_state,
                      protocol.MeasurementState.PROCESSING)
        self.assertIs(p.abort_reason, protocol.AbortReason.NONE)
        self.assertEqual(p.audio_block_counter, 987654)
        self.assertFalse(p.is_aborted)

    def test_wire_positions(self):
        # Pins the layout, not just the round trip. If the reserved bytes were
        # ever dropped, the block counter would decode as garbage.
        payload = vectors.state_payload(measurement_state=6, abort_reason=3,
                                        audio_block_counter=0x01020304)
        self.assertEqual(len(payload), protocol.STATE_PAYLOAD_BYTES)
        self.assertEqual(payload[0], 6)
        self.assertEqual(payload[1], 3)
        self.assertEqual(payload[2:4], b"\x00\x00")
        self.assertEqual(payload[4:8], b"\x04\x03\x02\x01")

    def test_aborted_snapshot_reports_its_reason(self):
        p = decode_one(vectors.state(
            measurement_state=int(protocol.MeasurementState.ABORTED),
            abort_reason=int(protocol.AbortReason.HARDWARE_FAULT)))
        self.assertTrue(p.is_aborted)
        self.assertIs(p.abort_reason, protocol.AbortReason.HARDWARE_FAULT)

    def test_wrong_length_is_rejected(self):
        with self.assertRaises(packets.DecodeError):
            packets.decode_state(b"\x00" * 7)


class TestForwardCompatibility(unittest.TestCase):
    """Runbook Phase 10 step 9. This is what lets a future packet type ship
    without a version break."""

    def test_unknown_type_is_returned_not_raised(self):
        p = decode_one(vectors.unknown(0xFE, b"future"))
        self.assertIsInstance(p, packets.UnknownPacket)
        self.assertEqual(p.packet_type, 0xFE)
        self.assertEqual(p.payload, b"future")

    def test_unknown_packet_is_skipped_by_length_and_the_stream_continues(self):
        geo = protocol.Geometry()
        stream = (vectors.hello()
                  + vectors.unknown(0xFE, bytes(range(64)))
                  + vectors.live_frame(geo)
                  + vectors.unknown(0x42, b"")
                  + vectors.view())
        scanner = FrameScanner()
        decoded = [packets.decode(f, geo) for f in scanner.feed(stream)]
        self.assertEqual(
            [type(d).__name__ for d in decoded],
            ["Hello", "UnknownPacket", "LiveFrame", "UnknownPacket",
             "ViewChange"])
        self.assertEqual(scanner.stats.crc_failures, 0)

    def test_an_unknown_type_never_reaches_a_renderer_as_data(self):
        p = decode_one(vectors.unknown(0x7F, b"\x00" * 8))
        self.assertNotIsInstance(p, packets.LiveFrame)
        self.assertNotIsInstance(p, packets.Result)


if __name__ == "__main__":
    unittest.main()
