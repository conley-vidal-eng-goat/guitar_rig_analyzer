"""TODO-59 — a best-effort packet interleaved into a draining RESULT.

*** WHAT THESE TESTS PROVE, AND WHAT THEY DO NOT ***

They prove the CONSUMER is safe: an interleaved stream corrupts the RESULT,
the receiver rejects it rather than rendering it, and the stream recovers.
That is a real regression test, and it encodes the exact hazard found on
2026-09-26 so the shape cannot be forgotten.

They do NOT prove the firmware guard works. The invariant lives in
trySendBestEffort() in data_sender.cpp and can only be exercised by running
that code. ``test_source_invariant`` below checks the guard is PRESENT in
source — a structural regression test, not an execution one. Proving it
executes correctly needs a captured Teensy stream with a RESULT delivered
while the signal is live, which is bench work.
"""

import pathlib
import re
import unittest

from analyzer_link import protocol, packets
from analyzer_link.framing import FrameScanner
from analyzer_link.state import ReceiverState, UNKNOWN

from . import vectors

REPO = pathlib.Path(__file__).resolve().parents[2]
FIRMWARE = REPO / "firmware" / "guitar_rig_analyzer"
GEO = protocol.Geometry()

_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.S)
_LINE_COMMENT = re.compile(r"//[^\n]*")


def _strip_comments(text: str) -> str:
    """Blank out comments while preserving newlines, so source offsets still
    line up with the original structure."""
    text = _BLOCK_COMMENT.sub(lambda m: "\n" * m.group(0).count("\n"), text)
    return _LINE_COMMENT.sub("", text)


def interleave(host: bytes, guest: bytes, at: int) -> bytes:
    """Splice ``guest`` into the middle of ``host`` — what the UART ring does
    when a producer writes between two drain passes of a staged RESULT."""
    return host[:at] + guest + host[at:]


class TestInterleavedResultIsRejected(unittest.TestCase):

    def setUp(self):
        self.scanner = FrameScanner()
        self.state = ReceiverState()
        for frame in self.scanner.feed(vectors.hello(session_id=1)):
            self.state.on_frame(frame, now_ms=0)
        self.assertTrue(self.state.session_established)

    def test_small_status_spliced_into_a_result_destroys_that_result(self):
        # THE DISCOVERED CASE: a 12-byte STATUS ("Ready" + 7 framing) fits in
        # the room that reappears between drain passes. Size is not protection
        # — the small packet is the dangerous one.
        result = vectors.result(GEO)
        status = vectors.status("Ready")
        self.assertEqual(len(status), 12)

        stream = interleave(result, status, at=len(result) // 2)
        for frame in self.scanner.feed(stream):
            self.state.on_frame(frame, now_ms=10)

        # The result is gone. It must NOT have been rendered as data.
        self.assertIsNone(self.state.latest_result)
        self.assertGreaterEqual(self.scanner.stats.crc_failures, 1)

    def test_the_interleaved_packet_itself_may_still_arrive(self):
        # Worth pinning because it is how this defect would present on a bench:
        # the small packet gets through and only the RESULT vanishes. An
        # operator sees status text updating normally and measurements
        # silently failing to appear.
        result = vectors.result(GEO)
        status = vectors.status("Ready")
        stream = interleave(result, status, at=len(result) // 2)
        for frame in self.scanner.feed(stream):
            self.state.on_frame(frame, now_ms=10)
        self.assertIn("Ready", list(self.state.status_log))
        self.assertIsNone(self.state.latest_result)

    def test_view_and_aborted_splices_are_equally_destructive(self):
        for guest, label in ((vectors.view(), "VIEW"),
                             (vectors.aborted("CLIP"), "ABORTED")):
            with self.subTest(packet=label):
                scanner = FrameScanner()
                state = ReceiverState()
                for f in scanner.feed(vectors.hello(session_id=1)):
                    state.on_frame(f, now_ms=0)

                stream = interleave(vectors.result(GEO), guest, at=2000)
                for f in scanner.feed(stream):
                    state.on_frame(f, now_ms=10)

                self.assertIsNone(state.latest_result)
                self.assertGreaterEqual(scanner.stats.crc_failures, 1)

    def test_the_stream_recovers_after_a_corrupted_result(self):
        # A corrupted RESULT must cost that result and nothing more.
        stream = interleave(vectors.result(GEO), vectors.status("Ready"),
                            at=3000)
        for frame in self.scanner.feed(stream + vectors.result(GEO)
                                       + vectors.view()):
            self.state.on_frame(frame, now_ms=20)
        self.assertIsNotNone(self.state.latest_result)

    def test_splice_at_the_very_first_payload_byte(self):
        stream = interleave(vectors.result(GEO), vectors.view(),
                            at=protocol.HEADER_BYTES)
        for frame in self.scanner.feed(stream):
            self.state.on_frame(frame, now_ms=10)
        self.assertIsNone(self.state.latest_result)

    def test_a_clean_result_still_decodes(self):
        # The control. Without it, the tests above could pass for the wrong
        # reason — a receiver that never decodes any result at all.
        for frame in self.scanner.feed(vectors.result(GEO)):
            self.state.on_frame(frame, now_ms=10)
        self.assertIsNotNone(self.state.latest_result)
        self.assertEqual(self.scanner.stats.crc_failures, 0)


class TestSourceInvariant(unittest.TestCase):
    """Structural guard: the firmware invariant must stay in the source.

    This is not an execution test. It fails if someone removes or relocates
    the check, which is the realistic regression — the defect existed for
    months precisely because nothing said the guard had to be there.
    """

    def _try_send_body(self) -> str:
        src = (FIRMWARE / "data_sender.cpp").read_text()
        start = src.index("static bool trySendBestEffort(")
        end = src.index("\n}", start)
        return src[start:end]

    def test_trysendbesteffort_refuses_while_a_result_is_staged(self):
        body = self._try_send_body()
        self.assertRegex(
            body, r"if\s*\(\s*s_result_len\s*!=\s*0\s*\)",
            "The transport atomicity invariant (TODO-59) is missing from "
            "trySendBestEffort(). Without it, any best-effort packet written "
            "while a staged RESULT is draining lands inside that RESULT's "
            "byte stream and destroys it.")

    def test_the_guard_precedes_any_uart_write(self):
        body = self._try_send_body()
        guard = body.index("s_result_len")
        first_write = body.index("DS_UART_PORT.write")
        self.assertLess(guard, first_write,
                        "The result-pending guard must come before any write.")

    def test_the_refusal_is_counted(self):
        self.assertIn("blocked_by_result", self._try_send_body())
        self.assertIn("uint32_t blocked_by_result;",
                      (FIRMWARE / "data_sender.h").read_text())

    def test_only_two_functions_write_to_the_uart(self):
        # The invariant is only as good as its coverage: a future packet type
        # that writes to DS_UART_PORT directly bypasses the choke point
        # entirely. Only two functions may touch the wire — the best-effort
        # choke point, and the reliable drain itself.
        #
        # Function definitions in this file start at column 0, which is what
        # separates them from the `while (...)` inside the drain loop.
        # Comments must be stripped first: this file's own banner warns
        # "If you add a code path that calls DS_UART_PORT.write() without
        # first checking room", and that prose is not a writer.
        src = _strip_comments((FIRMWARE / "data_sender.cpp").read_text())
        starts = [(m.start(), m.group(1)) for m in re.finditer(
            r"^(?:static\s+)?[\w:<>*&]+[\w\s:<>*&]*?\b(\w+)\s*\([^;{]*\)\s*\{",
            src, re.M)]
        self.assertTrue(starts, "no top-level functions found — regex is wrong")

        writers = set()
        for m in re.finditer(r"DS_UART_PORT\.write", src):
            enclosing = [name for pos, name in starts if pos < m.start()]
            writers.add(enclosing[-1] if enclosing else "<file scope>")

        allowed = {"trySendBestEffort", "dataSender_service"}
        self.assertEqual(
            writers, allowed,
            f"UART writers changed. Expected exactly {sorted(allowed)}, got "
            f"{sorted(writers)}. A new direct writer bypasses the TODO-59 "
            f"transport atomicity invariant.")


if __name__ == "__main__":
    unittest.main()
