"""Tests against the REAL hardware RESULT capture and the timeout capture.

Two artifacts from 2026-09-27, both produced by flashed firmware `dcfbffa` over
the physical Teensy pin 1 → Pi GPIO15 link:

  phase10-result-1khz.bin         a completed measurement. The FIRST RESULT
                                  packet ever received off the wire.
  phase10-result-no-stimulus.bin  the negative control: `m` with no stimulus,
                                  so ARMED → ABORTED(TIMEOUT).

*** WHAT THESE TESTS ARE FOR ***

They are REGRESSION GUARDS on the receiver, pinned to bytes a Teensy actually
produced. They are not a measurement result and they cannot become one. Every
analog figure below (quality POOR, 4 finite bins of 512, coherence 0.80) is
recorded because it is what the artifact contains, NOT because it is good — the
stimulus was a single 1 kHz tone into a return path carrying noise, so a sparse
result is the expected shape. A test here failing means the PARSER changed
behaviour against real bytes; it never means the instrument got worse.

*** THE FIXTURES ARE EVIDENCE AND ARE NEVER MODIFIED. ***
Hashes are asserted on every run, as in test_hardware_fixture.py.
"""

from __future__ import annotations

import hashlib
import math
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "tools"))

from analyzer_link import framing, packets, protocol
from replay import replay

REPO = pathlib.Path(__file__).resolve().parents[2]
EVIDENCE = REPO / "ai" / "evidence"

RESULT_BIN = EVIDENCE / "phase10-result-1khz.bin"
RESULT_SHA = "e8b57d6f62af1367b654dd6d13270a94d73f06868ac785edf353f20179dd14a1"
RESULT_BYTES = 125480

# replay.py names the key this way on purpose: the section is analog
# observation and can never be part of the transport verdict.
_OBS = "result_observations_not_a_verdict"

TIMEOUT_BIN = EVIDENCE / "phase10-result-no-stimulus.bin"
TIMEOUT_SHA = "f4095604a85ee47e6cf3c8efc48297f43614d575cca54162216fbe5f2934b4c8"
TIMEOUT_BYTES = 588218

# One framed LIVE_FRAME at the geometry these captures report (128 live bins).
# A capture that attaches mid-stream cannot discard more than this, because it
# lands inside exactly one packet and loses that packet's remainder.
FRAMED_LIVE = (protocol.HEADER_BYTES
               + protocol.live_payload_bytes(128)
               + protocol.CRC_BYTES)


@unittest.skipUnless(RESULT_BIN.is_file(), "RESULT fixture not present")
class TestRealResultTransport(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.raw = RESULT_BIN.read_bytes()
        cls.r = replay(cls.raw, seconds=60)

    def test_fixture_is_unmodified(self):
        self.assertEqual(hashlib.sha256(self.raw).hexdigest(), RESULT_SHA)
        self.assertEqual(len(self.raw), RESULT_BYTES)

    def test_transport_is_clean(self):
        f = self.r["framing"]
        self.assertTrue(self.r["transport_ok"], self.r["transport_problems"])
        self.assertEqual(f["crc_failures"], 0)
        self.assertEqual(f["oversize_rejects"], 0)
        self.assertEqual(f["buffered_at_end"], 0)
        self.assertEqual(self.r["receiver"]["decode_errors"], 0)

    def test_exactly_one_result_arrived_and_it_is_the_teensy_s(self):
        self.assertEqual(self.r["packets"]["Result"], 1)
        obs = self.r[_OBS]
        self.assertIsNotNone(obs)
        # Authored by the Teensy and carried verbatim. The Pi must never
        # recompute any of these.
        self.assertTrue(obs["result_valid"])
        self.assertEqual(obs["quality_grade"], "POOR")
        self.assertEqual(obs["n_averages_completed"], 32)
        self.assertEqual(obs["insight_count"], 4)
        self.assertEqual(obs["calibration_applied"], False)
        self.assertIn("CALIBRATION_MISSING", obs["calibration_warnings"])

    def test_all_four_canonical_arrays_are_512_bins(self):
        """The completed RESULT grid is 512, whatever fft_size says."""
        arrays = {a["array"]: a
                  for a in self.r[_OBS]["arrays"]}
        self.assertEqual(set(arrays), {"tf_cal_mag_db", "tf_cal_phase_rad",
                                       "group_delay_ms", "coherence"})
        for name, a in arrays.items():
            self.assertEqual(a["elements"], 512, name)
            self.assertEqual(a["pos_inf"], 0, name)
            self.assertEqual(a["neg_inf"], 0, name)

    def test_the_nan_conventions_survived_the_wire(self):
        """Per-array, and they are NOT uniform. See measurement_engine.cpp.

        This is the test that would catch a receiver quietly turning an
        unknown bin into 0.0 — the failure mode the protocol exists to stop.
        """
        arrays = {a["array"]: a
                  for a in self.r[_OBS]["arrays"]}
        # Unenergised bins are NaN in magnitude and phase, and this capture is
        # a single tone, so almost every bin is unenergised.
        self.assertGreater(arrays["tf_cal_mag_db"]["nan"], 0)
        self.assertGreater(arrays["tf_cal_phase_rad"]["nan"], 0)
        # group_delay is NaN at bins 0 and 511 by design, so >= 2 always.
        self.assertGreaterEqual(arrays["group_delay_ms"]["nan"], 2)
        # coherence uses 0.0 for an unenergised bin, never NaN.
        self.assertEqual(arrays["coherence"]["nan"], 0)
        self.assertEqual(arrays["coherence"]["finite"], 512)

    def test_no_array_was_silently_zero_filled(self):
        """Decode the RESULT directly and check the NaN is really NaN.

        The report counts NaN, so a receiver that replaced NaN with 0.0 would
        still be caught by the count — but only if the count is read. Asserting
        on the decoded float closes the gap at the source.
        """
        geo, res = _decode_the_result(self.raw)
        self.assertEqual(geo.fft_bins, 512)
        self.assertEqual(len(res.tf_cal_mag_db), 512)
        self.assertTrue(any(math.isnan(v) for v in res.tf_cal_mag_db))
        self.assertTrue(math.isnan(res.group_delay_ms[0]))
        self.assertTrue(math.isnan(res.group_delay_ms[511]))
        self.assertFalse(any(math.isnan(v) for v in res.coherence))

    def test_session_is_single_and_geometry_was_established(self):
        rec = self.r["receiver"]
        self.assertEqual(rec["hello_session_ids"], [7])
        self.assertEqual(rec["geometry"]["fft_bins"], 512)
        self.assertEqual(rec["geometry"]["live_bins"], 128)
        self.assertEqual(rec["measurement_state"], "RESULT")
        self.assertFalse(rec["abort_latched"])

    def test_the_link_carried_no_view_packet(self):
        """`x` was pressed over USB AFTER the capture closed.

        Recorded as a test so the absence stays a fact rather than becoming an
        assumption. RESULT → IDLE recovery is proven on the USB console only;
        nothing here shows the Pi being told about it, because no VIEW packet
        (0x07) is in these bytes.
        """
        self.assertEqual(self.r["packets"].get("ViewChange", 0), 0)

    def test_discarded_bytes_are_all_at_the_capture_boundary(self):
        """The whole discarded-bytes question, pinned.

        1 598 B are discarded and every one of them is the tail of the live
        frame the capture opened inside: one event, at offset 0, and less than
        one framed live frame. Zero bytes are lost anywhere inside the stream.
        """
        f = self.r["framing"]
        self.assertEqual(f["bytes_discarded"], 1598)
        self.assertEqual(f["bytes_discarded_leading"], 1598)
        self.assertEqual(f["bytes_discarded_interior"], 0)
        self.assertEqual(f["interior_discard_events"], 0)
        self.assertLess(f["bytes_discarded_leading"], FRAMED_LIVE)

    def test_every_byte_is_accounted_for(self):
        """frames + discards + buffered == the file. No residual.

        Walked over the frames rather than inferred from packet counts, so a
        gap between two frames cannot hide inside a plausible total.
        """
        scanner = framing.FrameScanner()
        consumed = None
        gaps = 0
        for i in range(0, len(self.raw), 4096):
            for fr in scanner.feed(self.raw[i:i + 4096]):
                # The first frame starts after the leading attach loss, which
                # is expected; every later frame must butt against its
                # predecessor or a byte went missing between them.
                if consumed is not None and fr.offset != consumed:
                    gaps += 1
                consumed = fr.offset + (protocol.HEADER_BYTES
                                        + len(fr.payload)
                                        + protocol.CRC_BYTES)
        st = scanner.stats
        self.assertEqual(gaps, 0)
        # consumed is an absolute offset, so it already contains the leading
        # discard. Residual must be exactly zero.
        self.assertEqual(consumed + scanner.buffered_bytes, len(self.raw))
        self.assertEqual(st.bytes_discarded_interior, 0)

    def test_the_status_string_is_utf8_and_is_not_mangled(self):
        """Regression guard for the em-dash defect found in these bytes.

        The firmware writes a UTF-8 EM DASH (guitar_rig_analyzer.ino:560). The
        receiver decoded ASCII and produced three U+FFFD characters. Synthetic
        vectors used an ASCII hyphen and could never have caught it.
        """
        statuses = [pkt.message for pkt in
                    _decode_all_of_type(self.raw,
                                        protocol.PacketType.STATUS)]
        self.assertEqual(statuses, ["Measuring — external stimulus"])
        self.assertNotIn("�", statuses[0])


@unittest.skipUnless(TIMEOUT_BIN.is_file(), "timeout fixture not present")
class TestRealArmedTimeout(unittest.TestCase):
    """The negative control. No stimulus was playing, so `m` must time out.

    This is NOT a failed measurement and must never be recorded as one: the
    arm threshold refusing to arm on noise is the instrument working.
    """

    @classmethod
    def setUpClass(cls):
        cls.raw = TIMEOUT_BIN.read_bytes()
        cls.r = replay(cls.raw, seconds=60)

    def test_fixture_is_unmodified(self):
        self.assertEqual(hashlib.sha256(self.raw).hexdigest(), TIMEOUT_SHA)
        self.assertEqual(len(self.raw), TIMEOUT_BYTES)

    def test_transport_is_clean_and_no_result_was_produced(self):
        self.assertTrue(self.r["transport_ok"], self.r["transport_problems"])
        self.assertEqual(self.r["framing"]["crc_failures"], 0)
        self.assertEqual(self.r["packets"].get("Result", 0), 0)
        self.assertEqual(self.r["packets"]["Aborted"], 1)

    def test_the_abort_latched_and_the_machine_readable_reason_followed(self):
        """The prose reason arrives with the ABORTED packet; the enum arrives
        with the next periodic STATE, one 500 ms period later. Both matter, and
        a receiver must not require them to be simultaneous."""
        rec = self.r["receiver"]
        self.assertEqual(rec["measurement_state"], "ABORTED")
        self.assertTrue(rec["abort_latched"])
        self.assertEqual(rec["abort_reason_code"], "TIMEOUT")

    def test_discarded_bytes_are_all_at_the_capture_boundary(self):
        f = self.r["framing"]
        self.assertEqual(f["bytes_discarded"], 304)
        self.assertEqual(f["bytes_discarded_leading"], 304)
        self.assertEqual(f["bytes_discarded_interior"], 0)
        self.assertLess(f["bytes_discarded_leading"], FRAMED_LIVE)

    def test_the_session_differs_from_the_result_capture(self):
        """Session 6 here, 7 in the RESULT capture — a real power cycle between
        them. Evidence for the session counter, not proof of reconnect
        recovery: no receiver was running across the reboot."""
        self.assertEqual(self.r["receiver"]["hello_session_ids"], [6])


# -- helpers ----------------------------------------------------------------

def _decode_all_of_type(raw: bytes, packet_type: int) -> list:
    """Every payload of one type, decoded, geometry resolved from HELLO."""
    scanner = framing.FrameScanner()
    geo = None
    out = []
    for i in range(0, len(raw), 4096):
        for fr in scanner.feed(raw[i:i + 4096]):
            if fr.packet_type == protocol.PacketType.HELLO:
                hello = packets.decode_hello(fr.payload)
                geo = protocol.Geometry(live_bins=hello.live_bins,
                                        fft_bins=hello.fft_bins,
                                        decim_ratio=hello.decim_ratio,
                                        sample_rate=hello.sample_rate)
            if fr.packet_type == packet_type:
                out.append(packets.decode(fr, geo))
    return out


def _decode_the_result(raw: bytes):
    """The single RESULT in a capture, plus the geometry that located it."""
    scanner = framing.FrameScanner()
    geo = None
    for i in range(0, len(raw), 4096):
        for fr in scanner.feed(raw[i:i + 4096]):
            if fr.packet_type == protocol.PacketType.HELLO:
                hello = packets.decode_hello(fr.payload)
                geo = protocol.Geometry(live_bins=hello.live_bins,
                                        fft_bins=hello.fft_bins,
                                        decim_ratio=hello.decim_ratio,
                                        sample_rate=hello.sample_rate)
            elif fr.packet_type == protocol.PacketType.RESULT:
                return geo, packets.decode_result(fr.payload, geo)
    raise AssertionError("no RESULT in the capture")


if __name__ == "__main__":
    unittest.main()
