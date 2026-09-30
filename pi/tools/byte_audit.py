#!/usr/bin/env python3
"""Close the byte accounting on a raw capture. Answers WHERE, not just how many.

    python3 pi/tools/byte_audit.py <capture.bin> [more.bin ...]

`replay.py` reports the link's health. This reports whether every byte in the
file is accounted for, and if any went missing, where. It exists because on
2026-09-27 a real capture reported 1 598 discarded bytes alongside zero CRC
failures, zero decode errors and a complete RESULT, and "probably the capture
started mid-frame" was a story rather than a measurement. It was in fact exactly
that, and this tool is what established it.

*** WHAT IT CHECKS ***

  1. Every discard event, with its absolute offset and its position class.
     LEADING  — before the first verified frame. A capture attaches to a running
                stream, so it opens inside a packet and loses that packet's
                remainder. Bounded by ONE FRAMED PACKET. Not a defect.
     INTERIOR — after the first verified frame. Bytes that should have been the
                next sync word were not. This is real loss and it is a finding.
  2. Inter-frame contiguity: does each frame's sync word sit exactly where the
     previous frame ended? A gap here is loss that a plausible-looking discard
     total can otherwise hide.
  3. The closing identity: consumed + buffered == file length, residual zero.

Uses the production FrameScanner deliberately. An audit that reimplemented the
framing could agree with itself while disagreeing with the receiver, which is the
shared-author trap this project keeps running into.
"""

from __future__ import annotations

import collections
import hashlib
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from analyzer_link import framing, protocol

CHUNK = 4096            # same chunking as replay.py, so splits are exercised


def audit(path: pathlib.Path) -> bool:
    raw = path.read_bytes()
    scanner = framing.FrameScanner()

    sizes = collections.Counter()
    gaps = []
    expected_next = None
    first_frame = None
    consumed = 0

    for i in range(0, len(raw), CHUNK):
        for fr in scanner.feed(raw[i:i + CHUNK]):
            total = (protocol.HEADER_BYTES + len(fr.payload)
                     + protocol.CRC_BYTES)
            if first_frame is None:
                first_frame = (fr.offset, fr.packet_type, total)
            elif fr.offset != expected_next:
                gaps.append((expected_next, fr.offset - expected_next,
                             fr.packet_type))
            expected_next = fr.offset + total
            consumed = expected_next
            sizes[(fr.packet_type, total)] += 1

    st = scanner.stats
    residual = len(raw) - (consumed + scanner.buffered_bytes)
    lead_bound = protocol.max_framed_bytes()

    print(f"=== {path}")
    print(f"  sha256            {hashlib.sha256(raw).hexdigest()}")
    print(f"  bytes             {len(raw)}")
    print(f"  frames ok         {st.frames_ok}")
    print(f"  CRC failures      {st.crc_failures}")
    print(f"  oversize rejects  {st.oversize_rejects}")
    print(f"  discarded total   {st.bytes_discarded}")
    print(f"    leading         {st.bytes_discarded_leading}"
          f"   (bound {lead_bound} B = one maximum framed packet)")
    print(f"    interior        {st.bytes_discarded_interior}"
          f"   in {st.interior_discard_events} event(s)")
    print(f"  buffered at end   {scanner.buffered_bytes}")
    print(f"  residual          {residual}   (must be 0)")

    if first_frame is not None:
        off, ptype, total = first_frame
        print(f"  first frame       @{off} type 0x{ptype:02x} ({total} B framed)")
        if off:
            print(f"  leading loss      {off} B, i.e. the tail of the packet the "
                  f"reader attached inside. If that packet was the same size as "
                  f"the first good one ({total} B), the capture opened "
                  f"{total - off} byte(s) into it.")
        print(f"  last frame ends   {expected_next}"
              f"   trailing {len(raw) - expected_next} B")
    print("  frame sizes (type, framed bytes): count")
    for (ptype, total), count in sorted(sizes.items()):
        print(f"    0x{ptype:02x}  {total:>6} B  x{count}")

    problems = []
    if residual:
        problems.append(f"byte accounting does not close: residual {residual}")
    if gaps:
        problems.append(f"{len(gaps)} inter-frame gap(s), "
                        f"{sum(g[1] for g in gaps)} B")
        for at, n, nxt in gaps[:20]:
            print(f"    GAP @{at} of {n} B before type 0x{nxt:02x}")
    if st.interior_discard_events:
        problems.append(f"{st.bytes_discarded_interior} B discarded INSIDE the "
                        f"stream across {st.interior_discard_events} event(s)")
    if st.bytes_discarded_leading >= lead_bound:
        problems.append(f"{st.bytes_discarded_leading} leading B exceeds one "
                        f"maximum framed packet ({lead_bound} B)")

    if problems:
        print("  ACCOUNTING: PROBLEM")
        for p in problems:
            print(f"    - {p}")
    else:
        print("  ACCOUNTING: CLOSED — all loss is at the capture boundary")
    print()
    return not problems


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 2
    ok = True
    for arg in argv[1:]:
        ok = audit(pathlib.Path(arg)) and ok
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
