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

*** --timeline AND ITS TIME BASIS ***

With --timeline the report also lists state transitions in the order the
capture contains them. Ordinary output is unchanged without the flag.

Two time references appear and they are NOT equivalent:

  t=       TEENSY AUDIO TIME. Derived from the audio_block_counter carried in
           every STATE packet, at AUDIO_BLOCK_SAMPLES/SAMPLE_RATE per tick.
           Measured against this project's own 30 s hardware fixture as
           2.9027 ms/tick versus 2.9025 ms theoretical, monotonic throughout.
           This is an instrument observation, not an inference, and it advances
           at a constant rate NO MATTER HOW MUCH DATA IS FLOWING.

  ~b=      INFERRED from byte position: offset / total bytes x duration.
           *** IT DISTORTS BADLY WHENEVER THE BYTE RATE CHANGES. *** When live
           frames stop -- which is exactly what happens during ABORTED, since
           presentation_updateLive() is gated to IDLE|ARMED -- the byte rate
           collapses by ~97 % and this axis nearly stops advancing while real
           time keeps passing. It is shown only as a cross-check and must never
           be read as elapsed time on a capture whose traffic volume varies.

Byte position was the original axis here and was wrong for precisely the
capture this feature exists to analyse. Kept, labelled, and demoted.

WRAP: audio_block_counter comes from micros(), so it returns to zero roughly
every 71.6 minutes and never exceeds ~1.48e6 -- it is NOT a full 32-bit range.
A negative delta means a wrap, and audio time is then withdrawn rather than
reported wrongly. No arithmetic is attempted across a wrap.

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


# Threshold for declaring live telemetry absent.
#
# MUST stay well clear of the audio clock's own resolution. That clock only
# advances when a STATE packet arrives, i.e. every 500 ms, so it moves in 500 ms
# steps. A 0.5 s threshold therefore fired constantly on a perfectly healthy
# idle capture -- normal quantisation read as a gap. 2 s is 4x the resolution,
# and the case this exists to catch (live frames suppressed during ABORTED) runs
# for many seconds.
LIVE_GAP_SECONDS = 2.0

# One audio_block_counter tick. Measured 2.9027 ms/tick on this project's 30 s
# hardware fixture against 2.9025 ms theoretical.
AUDIO_BLOCK_SECONDS = 128 / 44100.0


def replay(raw: bytes, seconds: float | None,
           timeline: bool = False) -> dict:
    scanner = FrameScanner()
    state = ReceiverState()
    counts: collections.Counter = collections.Counter()
    unknown_types: collections.Counter = collections.Counter()
    hello_sessions: list[int] = []
    decode_errors_before = 0
    now = 0

    # Timeline bookkeeping. Nothing here runs unless asked for, so the default
    # path is untouched.
    events: list[dict] = []
    # Seeded with the model's actual initial values, so the first entry is a
    # real transition rather than "None -> UNKNOWN", which is just the receiver
    # starting up and would read as an event that never happened.
    prev_state = "UNKNOWN"
    prev_latched = False
    prev_reason = "NONE"
    prev_session = None
    prev_return = None
    first_blk: int | None = None
    last_blk: int | None = None
    blk_wrapped = False
    last_live_audio: float | None = None
    live_absent = False

    def byte_time(offset: int) -> float:
        """INFERRED, and distorted whenever the byte rate changes."""
        if not seconds or not raw:
            return 0.0
        return offset / len(raw) * seconds

    def audio_time() -> float | None:
        """Teensy audio time in seconds since the first STATE packet, or None
        if no STATE has been seen yet or the counter has wrapped."""
        if first_blk is None or last_blk is None or blk_wrapped:
            return None
        return (last_blk - first_blk) * AUDIO_BLOCK_SECONDS

    def note(offset: int, kind: str, detail: str) -> None:
        events.append({
            "t_audio": (None if audio_time() is None
                        else round(audio_time(), 3)),
            "t_bytes_inferred": round(byte_time(offset), 3),
            "offset": offset,
            "block_counter": last_blk,
            "kind": kind,
            "detail": detail,
        })

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

            if not timeline:
                continue

            off = frame.offset

            # Advance the audio clock BEFORE emitting anything, so every event
            # carries the most recent instrument observation.
            if isinstance(pkt, packets.StatePacket):
                blk = pkt.audio_block_counter
                if first_blk is None:
                    first_blk = blk
                elif last_blk is not None and blk < last_blk:
                    blk_wrapped = True       # withdraw audio time, do not guess
                last_blk = blk

            # --- live telemetry presence, summarised not enumerated ---------
            # Judged on AUDIO time, not byte position: when live frames stop the
            # byte rate collapses, so a byte-based gap would never be detected.
            nowa = audio_time()
            if isinstance(pkt, packets.LiveFrame):
                if live_absent and nowa is not None and last_live_audio is not None:
                    note(off, "LIVE RESUMED",
                         f"first live frame after {nowa - last_live_audio:.2f} s "
                         f"with none")
                    live_absent = False
                if nowa is not None:
                    last_live_audio = nowa
            elif (not live_absent and nowa is not None
                    and last_live_audio is not None
                    and nowa - last_live_audio > LIVE_GAP_SECONDS):
                note(off, "LIVE STOPPED",
                     f"no live frame for {nowa - last_live_audio:.2f} s")
                live_absent = True

            # --- discrete protocol events ----------------------------------
            if isinstance(pkt, packets.Hello) and pkt.session_id != prev_session:
                note(off, "SESSION",
                     f"established/changed -> {pkt.session_id}")
                prev_session = pkt.session_id
            elif isinstance(pkt, packets.Aborted):
                note(off, "ABORTED pkt", f'reason string "{pkt.reason}"')
            elif isinstance(pkt, packets.ViewChange):
                note(off, "VIEW pkt",
                     f"view_id {pkt.view_id}"
                     f"{' (LIVE)' if pkt.is_live else ''}")
            elif isinstance(pkt, packets.Status):
                note(off, "STATUS pkt", f'"{pkt.message}"')
            elif isinstance(pkt, packets.Result):
                note(off, "RESULT pkt",
                     f"quality {pkt.result_quality.name}, "
                     f"valid {pkt.result_valid}")

            # --- receiver state, after the packet was applied --------------
            cur = ("UNKNOWN" if state.measurement_state is UNKNOWN
                   else state.measurement_state.name)
            if cur != prev_state:
                note(off, "STATE", f"{prev_state} -> {cur}")
                prev_state = cur
            if state.abort_latched != prev_latched:
                note(off, "ABORT LATCH",
                     (f"SET (reason_code {state.abort_reason_code.name})"
                      if state.abort_latched else "CLEARED"))
                prev_latched = state.abort_latched
            # Tracked separately because it moves independently: the ABORTED
            # packet carries the prose and sets the latch, while the machine
            # readable code only arrives with the next STATE snapshot -- up to
            # one announcement period later. That interval is worth seeing.
            if state.abort_reason_code.name != prev_reason:
                note(off, "REASON CODE",
                     f"{prev_reason} -> {state.abort_reason_code.name}")
                prev_reason = state.abort_reason_code.name
            if state.router is not None:
                rs = state.router.return_source.name
                if rs != prev_return:
                    note(off, "ROUTE", f"return_source {rs}")
                    prev_return = rs

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
        **({"timeline": events} if timeline else {}),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("capture", type=pathlib.Path)
    ap.add_argument("--seconds", type=float, default=None,
                    help="capture duration, for rate calculation")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--timeline", action="store_true",
                    help="also list state transitions in capture order")
    args = ap.parse_args()

    raw = args.capture.read_bytes()
    report = replay(raw, args.seconds, timeline=args.timeline)

    if args.json:
        print(json.dumps(report, indent=2))
        return 0 if report["transport_ok"] else 1

    r = report
    if args.timeline:
        print("timeline")
        print("  t=   Teensy AUDIO time, from the STATE packet block counter")
        print("       (2.9025 ms/tick). An instrument observation; constant")
        print("       rate regardless of traffic volume.")
        print("  ~b=  INFERRED from byte position. DISTORTS when the byte rate")
        print("       changes -- e.g. it nearly stops while live frames are")
        print("       suppressed. Cross-check only.")
        print()
        if not r["timeline"]:
            print("  (no transitions -- the capture is a single steady state)")
        for e in r["timeline"]:
            ta = ("    --   " if e["t_audio"] is None
                  else f"{e['t_audio']:8.3f}")
            print(f"  t={ta}s  ~b={e['t_bytes_inferred']:7.3f}s  "
                  f"@{e['offset']:>9d}  {e['kind']:<13s} {e['detail']}")
        print()

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
