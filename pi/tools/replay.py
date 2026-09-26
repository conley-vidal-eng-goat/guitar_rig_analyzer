#!/usr/bin/env python3
"""Replay a raw Serial1 capture through the receiver and report on it.

    python3 pi/tools/replay.py <capture.bin> [--seconds N] [--json]

The capture MUST be raw bytes written during acquisition with no decoding —
that is the whole point. A decoded log only proves the decoder agreed with
itself; raw bytes from a flashed Teensy are what breaks the shared-author
evidence loop.

*** WHAT FAILS THIS AND WHAT DOES NOT ***

Exit code is about the TRANSPORT only:
  - CRC failures, framing/resync loss, decode errors, unknown packet types,
    a missing or inconsistent HELLO, presence bits set without availability.

Analog content NEVER fails a replay. tf_clamped_count, peak levels and
confidence describe the instrument's analog state, not the link. They are
reported under "analog observations" and are excluded from the verdict. On
2026-09-26 a prediction of near-full TF clamping was wrong by 512 bins on a
completely healthy link; that is a finding about signal conditions, not a
transport fault.
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from analyzer_link import protocol, packets                       # noqa: E402
from analyzer_link.framing import FrameScanner                    # noqa: E402
from analyzer_link.state import ReceiverState, View, UNKNOWN      # noqa: E402

CHUNK = 4096


def replay(raw: bytes, seconds: float | None) -> dict:
    scanner = FrameScanner()
    state = ReceiverState()
    counts: collections.Counter = collections.Counter()
    unknown_types: collections.Counter = collections.Counter()
    hello_sessions: list[int] = []
    decode_errors_before = 0
    now = 0

    # Feed in chunks, as a serial reader would — a capture replayed in one
    # block would not exercise split-frame handling at all.
    for i in range(0, len(raw), CHUNK):
        now += 1
        for frame in scanner.feed(raw[i:i + CHUNK]):
            pkt = state.on_frame(frame, now_ms=now)
            if pkt is None:
                continue
            if isinstance(pkt, packets.UnknownPacket):
                counts["UNKNOWN"] += 1
                unknown_types[hex(pkt.packet_type)] += 1
            else:
                counts[type(pkt).__name__] += 1
            if isinstance(pkt, packets.Hello):
                hello_sessions.append(pkt.session_id)

    st = scanner.stats
    h = state.health
    del decode_errors_before

    router = state.router
    detectors = {}
    if router is not None:
        detectors = {j.name: router.detect(j).value for j in protocol.Jack}

    rates = {}
    if seconds:
        for name, n in counts.items():
            rates[name] = round(n / seconds, 2)

    problems = []
    if st.crc_failures:
        problems.append(f"{st.crc_failures} CRC failure(s)")
    if h.decode_errors:
        problems.append(f"{h.decode_errors} decode error(s)")
    if counts["UNKNOWN"]:
        problems.append(f"{counts['UNKNOWN']} unknown packet type(s)")
    if not hello_sessions:
        problems.append("no HELLO decoded — geometry never established")
    if len(set(hello_sessions)) > 1:
        problems.append(f"session id changed mid-capture: {sorted(set(hello_sessions))}")
    if st.oversize_rejects:
        problems.append(f"{st.oversize_rejects} oversize length reject(s)")

    # Bytes discarded before the first sync are normal (the capture starts
    # mid-stream). Anything beyond roughly one maximum packet is not.
    slack = protocol.max_payload_bytes()
    if st.bytes_discarded > slack:
        problems.append(
            f"{st.bytes_discarded} bytes discarded, above the {slack} B "
            f"explainable by a mid-stream start")

    live = state.latest_live
    analog = {}
    if live is not None:
        analog = {
            "peak_source_dbfs": round(live.peak_source_dbfs, 1),
            "peak_return_dbfs": round(live.peak_return_dbfs, 1),
            "tf_confidence": round(live.tf_confidence, 3),
            "tf_clamped_count": live.tf_clamped_count,
            "source_clip": live.source_clip,
            "return_clip": live.return_clip,
        }

    return {
        "bytes": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "packets": dict(counts),
        "rates_per_s": rates,
        "unknown_types": dict(unknown_types),
        "framing": {
            "frames_ok": st.frames_ok,
            "crc_failures": st.crc_failures,
            "oversize_rejects": st.oversize_rejects,
            "bytes_discarded": st.bytes_discarded,
            "buffered_at_end": scanner.buffered_bytes,
        },
        "receiver": {
            "session_established": state.session_established,
            "hello_session_ids": sorted(set(hello_sessions)),
            "geometry": (None if state.geometry is None else {
                "live_bins": state.geometry.live_bins,
                "fft_bins": state.geometry.fft_bins,
                "decim_ratio": state.geometry.decim_ratio,
                "sample_rate": state.geometry.sample_rate,
            }),
            "firmware_version": (state.hello.firmware_version
                                 if state.hello else None),
            "measurement_state": ("UNKNOWN" if state.measurement_state is UNKNOWN
                                  else state.measurement_state.name),
            "abort_latched": state.abort_latched,
            "abort_reason_code": state.abort_reason_code.name,
            "view": state.view.value,
            "decode_errors": h.decode_errors,
            "geometry_unavailable": h.geometry_unavailable,
            "not_promoted_pre_hello": h.not_promoted_pre_hello,
        },
        "router": (None if router is None else {
            "return_source": router.return_source.name,
            "detectors": detectors,
            "any_detector_available": router.any_detector_available,
            "injection_active": router.injection_active,
            "monitor_mode": router.monitor_mode.name,
            "description": router.description,
        }),
        "analog_observations_not_a_verdict": analog,
        "transport_problems": problems,
        "transport_ok": not problems,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("capture", type=pathlib.Path)
    ap.add_argument("--seconds", type=float, default=None,
                    help="capture duration, for rate calculation")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    raw = args.capture.read_bytes()
    report = replay(raw, args.seconds)

    if args.json:
        print(json.dumps(report, indent=2))
        return 0 if report["transport_ok"] else 1

    r = report
    print(f"capture   {args.capture}")
    print(f"bytes     {r['bytes']}")
    print(f"sha256    {r['sha256']}")
    print()
    print("packets decoded")
    for name, n in sorted(r["packets"].items(), key=lambda kv: -kv[1]):
        rate = r["rates_per_s"].get(name)
        print(f"  {name:16s} {n:7d}" + (f"   {rate}/s" if rate else ""))
    if r["unknown_types"]:
        print(f"  unknown types: {r['unknown_types']}")
    print()
    f = r["framing"]
    print("framing")
    print(f"  frames ok        {f['frames_ok']}")
    print(f"  CRC failures     {f['crc_failures']}")
    print(f"  oversize rejects {f['oversize_rejects']}")
    print(f"  bytes discarded  {f['bytes_discarded']}")
    print(f"  buffered at end  {f['buffered_at_end']}")
    print()
    rc = r["receiver"]
    print("receiver state")
    for k in ("session_established", "hello_session_ids", "firmware_version",
              "geometry", "measurement_state", "abort_latched",
              "abort_reason_code", "view", "decode_errors",
              "geometry_unavailable", "not_promoted_pre_hello"):
        print(f"  {k:24s} {rc[k]}")
    print()
    if r["router"]:
        print("router status")
        for k, v in r["router"].items():
            print(f"  {k:24s} {v}")
    else:
        print("router status    NONE RECEIVED")
    print()
    if rc["geometry_unavailable"] or rc["not_promoted_pre_hello"]:
        print("note: packets before the first HELLO are counted, not promoted.")
        print("      Expected on any capture that starts mid-stream — HELLO is")
        print("      announced ~1/s, so up to ~1 s of telemetry precedes it.")
        print()
    if r["analog_observations_not_a_verdict"]:
        print("analog observations (NOT part of the verdict)")
        for k, v in r["analog_observations_not_a_verdict"].items():
            print(f"  {k:24s} {v}")
        print()
    if r["transport_ok"]:
        print("TRANSPORT: OK")
    else:
        print("TRANSPORT: PROBLEMS")
        for p in r["transport_problems"]:
            print(f"  - {p}")
    return 0 if r["transport_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
