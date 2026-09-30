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

*** RESULT ARRAY REPORTING ***

When a RESULT is decoded, the report adds a result_observations section: per
array element counts, NaN/Inf census, finite min/max, plus quality, validity,
valid_bin_fraction and decoded calibration warnings.

ALL OF IT IS ANALOG OBSERVATION. None of it can fail a replay. A RESULT graded
INVALID, with every warning bit set and every applicable bin NaN, is a perfectly
successful transport result -- the question is whether the Teensy's authoritative
result arrived intact, not whether the numbers are good.

Per-array NaN conventions differ, and reading them as uniform would be wrong
(measurement_engine.cpp:425-436, 513-523):

  tf_cal_mag_db     NaN for an unenergised bin
  tf_cal_phase_rad  NaN for an unenergised bin
  group_delay_ms    NaN for an unenergised bin, AND ALWAYS NaN at bins 0 and
                    511 -- the central difference is undefined at the edges, so
                    >=2 NaN is expected even in a perfect measurement
  coherence         0.0f for an unenergised bin, NOT NaN. Zero coherence is
                    itself meaningful, so this array should show NO NaN at all

+Inf/-Inf are counted separately rather than lumped into "finite". The firmware
guards every log10 and constrains H1_dB, so infinities are not expected to be
producible -- which is exactly why an Inf appearing should surface as a finding
instead of hiding inside a finite count.

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


def _array_stats(name: str, values) -> dict:
    """Census an array WITHOUT converting anything.

    The decoded values keep whatever the wire carried -- NaN stays NaN. This
    only counts and summarises; min/max are computed over finite values only,
    and are None when the array holds no finite value at all (which is a real
    possibility for a measurement with no energised bins, not an error).
    """
    finite, nan, pos_inf, neg_inf = [], 0, 0, 0
    for v in values:
        if v != v:                      # NaN: the only value unequal to itself
            nan += 1
        elif v == float("inf"):
            pos_inf += 1
        elif v == float("-inf"):
            neg_inf += 1
        else:
            finite.append(v)
    return {
        "array": name,
        "elements": len(values),
        "finite": len(finite),
        "nan": nan,
        "pos_inf": pos_inf,
        "neg_inf": neg_inf,
        "min": (min(finite) if finite else None),
        "max": (max(finite) if finite else None),
    }


def _warning_names(bits: int) -> list[str]:
    return [w.name for w in protocol.CalibrationWarning if bits & int(w)]


def replay(raw: bytes, seconds: float | None,
           timeline: bool = False) -> dict:
    scanner = FrameScanner()
    state = ReceiverState()
    counts: collections.Counter = collections.Counter()
    unknown_types: collections.Counter = collections.Counter()
    hello_sessions: list[int] = []
    result_payload_len: int | None = None
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
            if isinstance(pkt, packets.Result):
                result_payload_len = len(frame.payload)

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

    # --- discarded bytes: judged by POSITION, not by a size bound -----------
    #
    # This used to allow any total up to max_payload_bytes() (10 005 B) as
    # "explainable by a mid-stream start". Two things were wrong with that.
    # It was far looser than a mid-stream start can actually explain -- the
    # capture lands inside ONE frame, so at most one framed packet minus a byte
    # can be attributed to attaching -- and, worse, it said nothing about WHERE
    # the loss happened, so interior resync loss could hide underneath it.
    #
    # Established against five real hardware captures on 2026-09-27: each had
    # exactly ONE discard event, at absolute offset 0, of 0-1664 B, with zero
    # inter-frame gaps thereafter. So the invariant to enforce is positional.
    if st.interior_discard_events:
        problems.append(
            f"{st.bytes_discarded_interior} byte(s) discarded INSIDE the stream "
            f"across {st.interior_discard_events} event(s) — loss after the "
            f"first good frame is a transport finding, not a mid-stream start")
    lead_slack = protocol.max_framed_bytes()
    if st.bytes_discarded_leading >= lead_slack:
        problems.append(
            f"{st.bytes_discarded_leading} leading bytes discarded, which is "
            f"more than the {lead_slack} B of one maximum framed packet — a "
            f"mid-stream start cannot account for that")

    res = state.latest_result
    result_obs = None
    if res is not None:
        result_obs = {
            "result_valid": res.result_valid,
            "quality_grade": res.result_quality.name,
            "fft_size": res.fft_size,
            "n_averages_completed": res.n_averages_completed,
            "mean_coherence": round(res.mean_coherence, 6),
            "valid_bin_fraction": round(res.valid_bin_fraction, 6),
            "insight_count": len(res.insights),
            "calibration_type": res.calibration_type.name,
            "calibration_warning_bits": int(res.calibration_warnings),
            "calibration_warnings": _warning_names(int(res.calibration_warnings)),
            "clip_detected": res.clip_detected,
            "calibration_applied": res.calibration_applied,
            "payload_bytes": result_payload_len,
            "framed_bytes": (None if result_payload_len is None
                             else result_payload_len + protocol.FRAMING_BYTES),
            "arrays": [
                _array_stats("tf_cal_mag_db", res.tf_cal_mag_db),
                _array_stats("tf_cal_phase_rad", res.tf_cal_phase_rad),
                _array_stats("group_delay_ms", res.group_delay_ms),
                _array_stats("coherence", res.coherence),
            ],
        }

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
            "bytes_discarded_leading": st.bytes_discarded_leading,
            "bytes_discarded_interior": st.bytes_discarded_interior,
            "interior_discard_events": st.interior_discard_events,
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
        **({"result_observations_not_a_verdict": result_obs}
           if result_obs is not None else {}),
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
    print(f"  bytes discarded  {f['bytes_discarded']}"
          f"  (leading {f['bytes_discarded_leading']}, "
          f"interior {f['bytes_discarded_interior']} in "
          f"{f['interior_discard_events']} event(s))")
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
    ro = r.get("result_observations_not_a_verdict")
    if ro:
        print("RESULT observations (ANALOG -- NOT part of the verdict)")
        print(f"  result_valid             {ro['result_valid']}   "
              f"quality {ro['quality_grade']}")
        print(f"  fft_size                 {ro['fft_size']}   "
              f"(array length is the canonical grid, not this)")
        print(f"  n_averages_completed     {ro['n_averages_completed']}")
        print(f"  mean_coherence           {ro['mean_coherence']}")
        print(f"  valid_bin_fraction       {ro['valid_bin_fraction']}")
        print(f"  insight_count            {ro['insight_count']}")
        print(f"  calibration_type         {ro['calibration_type']}   "
              f"applied {ro['calibration_applied']}")
        print(f"  calibration_warning_bits 0x{ro['calibration_warning_bits']:02X}"
              f"  {ro['calibration_warnings'] or '(none set)'}")
        print(f"  clip_detected            {ro['clip_detected']}")
        print(f"  payload / framed         {ro['payload_bytes']} / "
              f"{ro['framed_bytes']} B")
        print()
        print("  array              elems  finite    NaN  +Inf  -Inf"
              "        min         max")
        for a in ro["arrays"]:
            mn = "        --" if a["min"] is None else f"{a['min']:10.4g}"
            mx = "        --" if a["max"] is None else f"{a['max']:10.4g}"
            print(f"  {a['array']:<17s} {a['elements']:5d} {a['finite']:7d} "
                  f"{a['nan']:6d} {a['pos_inf']:5d} {a['neg_inf']:5d}  "
                  f"{mn}  {mx}")
        print("  note: group_delay_ms is NaN at bins 0 and 511 BY DESIGN "
              "(central difference);")
        print("        coherence uses 0.0 rather than NaN for an unenergised "
              "bin, so it")
        print("        should show no NaN at all. See measurement_engine.cpp"
              ":425-436, 513-523.")
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
