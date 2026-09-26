"""Drift guard: every mirrored constant and enum must still match the firmware.

This is the Pi-side half of the protocol audit's acceptance Test C — "layout
drift cannot be silent". The firmware enforces its own layout with
``static_assert``; nothing enforced the Python mirror, so a firmware edit could
silently desynchronise the receiver and the first symptom would be a
misrendered measurement.

These tests read the actual Teensy headers in this repository and fail if any
value in ``analyzer_link.protocol`` has drifted from them.

*** WHAT THIS DOES NOT PROVE ***
It proves the mirror matches the HEADERS. It does not prove the parser matches
the compiled firmware's behaviour on the wire — a captured real byte stream is
what establishes that (runbook Phase 10 step 4 onward, hardware required).
"""

from __future__ import annotations

import pathlib
import re
import unittest

from analyzer_link import protocol

REPO = pathlib.Path(__file__).resolve().parents[2]

_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.S)
_LINE_COMMENT = re.compile(r"//[^\n]*")


def _strip_comments(text: str) -> str:
    return _LINE_COMMENT.sub("", _BLOCK_COMMENT.sub("", text))


def _read(name: str) -> str:
    path = REPO / name
    if not path.is_file():
        raise AssertionError(
            f"{name} is missing from {REPO}. This test is a mirror of the "
            f"firmware headers and cannot run without them.")
    return _strip_comments(path.read_text())


def defines(name: str) -> dict[str, str]:
    """Every ``#define NAME value`` in a header, comments removed."""
    out: dict[str, str] = {}
    for m in re.finditer(r"^\s*#define\s+(\w+)\s+(.+)$",
                         _read(name), re.M):
        out.setdefault(m.group(1), m.group(2).strip())
    return out


def enum_members(name: str, enum_name: str) -> dict[str, int]:
    """Members of a ``enum class X : uint8_t { ... }`` declaration."""
    text = _read(name)
    m = re.search(rf"enum\s+class\s+{enum_name}\s*:\s*\w+\s*\{{(.*?)\}}",
                  text, re.S)
    if m is None:
        raise AssertionError(f"enum class {enum_name} not found in {name}")
    return {k: int(v) for k, v in
            re.findall(r"(\w+)\s*=\s*(\d+)", m.group(1))}


class TestFramingConstants(unittest.TestCase):

    def setUp(self):
        self.ds = defines("data_sender.h")
        self.cfg = defines("config.h")

    def test_sync_word(self):
        self.assertEqual(int(self.ds["DS_SYNC_WORD"], 16), protocol.SYNC_WORD)
        # Little-endian on the wire: the runbook tells the operator to look
        # for "55 AA" with xxd at step 4.
        self.assertEqual(
            protocol.SYNC_WORD.to_bytes(2, "little"), protocol.SYNC_BYTES)

    def test_framing_size(self):
        self.assertEqual(int(self.ds["DS_FRAMING_BYTES"]),
                         protocol.FRAMING_BYTES)

    def test_protocol_version(self):
        self.assertEqual(int(self.cfg["PI_PROTOCOL_VERSION"]),
                         protocol.PROTOCOL_VERSION)

    def test_hello_reannounce_period(self):
        self.assertEqual(int(self.ds["DS_HELLO_REANNOUNCE_MS"]),
                         protocol.HELLO_REANNOUNCE_MS)

    def test_hello_18_19_is_session_id_not_reserved(self):
        # TODO-56 gave meaning to two bytes the v2 schema documented as
        # "reserved (0)". If anyone re-reserves them, or adds a second user of
        # the same offset, the Pi would read a constant 0 and silently lose
        # the ability to detect a Teensy reboot — a failure with no symptom
        # until reconnect behaviour is wrong.
        raw = (REPO / "data_sender.h").read_text()
        self.assertIn("[18-19]   uint16  session_id", raw)
        self.assertNotIn("[18-19]   uint16  reserved", raw)

    def test_baud_and_string_cap(self):
        self.assertEqual(int(self.ds["DS_BAUD_RATE"]), protocol.BAUD_RATE)
        self.assertEqual(int(self.ds["DS_MAX_STRING_PAYLOAD"]),
                         protocol.MAX_STRING_PAYLOAD)

    # The firmware's #define names are not all identical to the Python member
    # names, so the mapping is explicit rather than derived. 0x05 is
    # DS_PACKET_ROUTER in the #define but ROUTER_STATUS in the header's own
    # packet-type table and in its function name; the Python side follows the
    # documented name and this table records the difference instead of hiding
    # it behind string munging.
    PACKET_DEFINES = {
        protocol.PacketType.LIVE_FRAME:    "DS_PACKET_LIVE_FRAME",
        protocol.PacketType.RESULT:        "DS_PACKET_RESULT",
        protocol.PacketType.STATUS:        "DS_PACKET_STATUS",
        protocol.PacketType.ABORTED:       "DS_PACKET_ABORTED",
        protocol.PacketType.ROUTER_STATUS: "DS_PACKET_ROUTER",
        protocol.PacketType.HELLO:         "DS_PACKET_HELLO",
        protocol.PacketType.VIEW:          "DS_PACKET_VIEW",
    }

    def test_packet_type_ids(self):
        for member, key in self.PACKET_DEFINES.items():
            with self.subTest(packet=member.name):
                self.assertIn(key, self.ds, f"{key} missing from data_sender.h")
                self.assertEqual(int(self.ds[key], 16), int(member),
                                 f"{key} has drifted")

    def test_every_packet_type_is_covered_by_the_mapping(self):
        # Guards the table above: a new PacketType member with no #define
        # mapping would otherwise go unchecked forever.
        self.assertEqual(set(self.PACKET_DEFINES), set(protocol.PacketType))

    def test_no_firmware_packet_type_is_missing_from_the_mirror(self):
        # The other direction: a packet type added to the firmware that the
        # Pi has never heard of. Tolerated at runtime as UnknownPacket, but it
        # should be a deliberate decision, not a surprise.
        firmware = {k for k in self.ds if k.startswith("DS_PACKET_")}
        self.assertEqual(firmware, set(self.PACKET_DEFINES.values()))

    def test_view_id(self):
        self.assertEqual(int(self.ds["DS_VIEW_LIVE"], 16), protocol.VIEW_LIVE)


class TestGeometryConstants(unittest.TestCase):

    def setUp(self):
        self.ds = defines("data_sender.h")
        self.cfg = defines("config.h")
        self.ins = defines("insights_engine.h")

    def test_live_bins_default(self):
        self.assertEqual(int(self.ds["DS_LIVE_BINS"]),
                         protocol.DEFAULT_LIVE_BINS)

    def test_fft_geometry(self):
        fft_size = int(self.cfg["FFT_SIZE"])
        self.assertEqual(fft_size, protocol.DEFAULT_FFT_SIZE)
        self.assertEqual(fft_size // 2, protocol.DEFAULT_FFT_BINS)

    def test_sample_rate(self):
        self.assertEqual(int(self.cfg["SAMPLE_RATE"]),
                         protocol.DEFAULT_SAMPLE_RATE)

    def test_eeprom_session_address_is_reserved_in_config(self):
        # The session counter lives in EEPROM, and data_sender.cpp compiles
        # only for DISPLAY_TARGET_PI — so the address must be reserved in
        # config.h, where every build can see it. A second EEPROM user landing
        # on the same address would make the Pi think the Teensy rebooted
        # whenever that unrelated subsystem wrote its state.
        self.assertIn("EEPROM_ADDR_LINK_SESSION", defines("config.h"))

    def test_insights_max(self):
        self.assertEqual(int(self.ins["INSIGHTS_MAX_COUNT"]),
                         protocol.DEFAULT_INSIGHTS_MAX)

    def test_result_fixed_and_insight_entry_sizes(self):
        self.assertEqual(int(self.ds["DS_RESULT_FIXED_BYTES"]),
                         protocol.RESULT_FIXED_BYTES)
        self.assertEqual(int(self.ds["DS_INSIGHT_ENTRY_BYTES"]),
                         protocol.INSIGHT_ENTRY_BYTES)

    def test_live_payload_formula_matches_the_firmware_expression(self):
        # data_sender.h:
        #   #define DS_LIVE_PAYLOAD_BYTES (18 + (DS_LIVE_BINS*3*4) + DS_LIVE_BINS)
        expr = self.ds["DS_LIVE_PAYLOAD_BYTES"]
        n = protocol.DEFAULT_LIVE_BINS
        firmware_value = eval(expr.replace("DS_LIVE_BINS", str(n)))
        self.assertEqual(firmware_value, protocol.live_payload_bytes(n))

    def test_decim_ratio_fits_in_a_nibble(self):
        # The firmware static_asserts this because the coverage byte packs
        # clamped and valid counts into 4 bits each.
        ratio = protocol.DEFAULT_FFT_BINS // protocol.DEFAULT_LIVE_BINS
        self.assertLessEqual(ratio, 15)
        self.assertEqual(protocol.Geometry().decim_ratio, ratio)

    def test_worst_case_payload_bound_matches_the_firmware(self):
        # DS_RESULT_PAYLOAD_MAX = fixed + FFT_BINS*4*4 + 1 + INSIGHTS*ENTRY
        expected = (protocol.RESULT_FIXED_BYTES
                    + protocol.DEFAULT_FFT_BINS * 4 * 4
                    + 1
                    + protocol.DEFAULT_INSIGHTS_MAX
                    * protocol.INSIGHT_ENTRY_BYTES)
        self.assertEqual(protocol.max_payload_bytes(), expected)


class TestEnumsMatchFirmware(unittest.TestCase):
    """Every Teensy-authored enum, member by member.

    A renumbered enum is the quietest possible protocol break: the packet
    still parses, the CRC still passes, and the Pi displays the wrong verdict.
    """

    CASES = [
        ("measurement_engine.h", "MeasurementState", protocol.MeasurementState),
        ("measurement_core.h", "ResultQuality", protocol.ResultQuality),
        ("measurement_core.h", "CalibrationType", protocol.CalibrationType),
        ("measurement_core.h", "FftMode", protocol.FftMode),
        ("measurement_core.h", "TfEstimator", protocol.TfEstimator),
        ("measurement_core.h", "StimulusType", protocol.StimulusType),
        ("measurement_core.h", "WindowFunction", protocol.WindowFunction),
        ("insights_engine.h", "InsightMode", protocol.InsightMode),
        ("insights_engine.h", "InsightSeverity", protocol.InsightSeverity),
        ("signal_router.h", "ReturnSource", protocol.ReturnSource),
        ("signal_router.h", "MonitorMode", protocol.MonitorMode),
    ]

    def test_every_mirrored_enum_matches(self):
        for header, cpp_name, py_enum in self.CASES:
            with self.subTest(enum=cpp_name):
                firmware = enum_members(header, cpp_name)
                mirror = {m.name: int(m) for m in py_enum}
                self.assertEqual(firmware, mirror,
                                 f"{cpp_name} has drifted from {header}")

    def test_result_quality_ordering_is_preserved(self):
        # measurement_core.h documents INVALID(0) < POOR(1) < MARGINAL(2)
        # < GOOD(3) < EXCELLENT(4), and insights_engine.h relies on ordinal
        # comparison. A renumber that inverted this would silently invert
        # every quality gate.
        q = protocol.ResultQuality
        self.assertLess(q.INVALID, q.POOR)
        self.assertLess(q.POOR, q.MARGINAL)
        self.assertLess(q.MARGINAL, q.GOOD)
        self.assertLess(q.GOOD, q.EXCELLENT)


class TestBoundaryInvariant(unittest.TestCase):
    """ADR-001: the Pi presents truth, it does not determine it."""

    FORBIDDEN = ("numpy", "scipy", "math.fft")

    def test_receiver_does_no_dsp(self):
        # Not a style check. A receiver that imports an FFT is one commit away
        # from recomputing a transfer function the Teensy already authored.
        for module in ("protocol", "framing", "packets", "crc", "state"):
            src = (REPO / "pi" / "analyzer_link" / f"{module}.py").read_text()
            for banned in self.FORBIDDEN:
                self.assertNotIn(
                    f"import {banned}", src,
                    f"{module}.py imports {banned}; ADR-001 forbids the Pi "
                    f"deriving measurement values")


if __name__ == "__main__":
    unittest.main()
