#!/usr/bin/env python3
"""Diff the four T1 acceptance reports mechanically instead of by eye.

    python3 pi/tools/t1_diff.py run1_none.txt run2_pi.txt run3_stalled.txt run4_pulled.txt
    python3 pi/tools/t1_diff.py --json run1.txt run2.txt ...

Feed it the verbatim USB console text of each run's `T` output (the whole paste
is fine — surrounding boot banners and 5 s diagnostic blocks are ignored). The
FIRST file is always the control.

*** WHAT THIS TOOL DECIDES, AND WHAT IT REFUSES TO DECIDE ***

It enforces ONLY the criteria the project already states absolutely:

  blocks_skipped / skip_events / largest_block_gap  == 0 in EVERY run
      docs/breadboard_bringup_v3.md Phase 10 step 11: "0 in every run, no
      exceptions". TODO-35 repeats it. An absolute rule, so it is checkable.

  the four runs must share window length, firmware and protocol
      step 11: "Run all four under identical window length and identical signal
      conditions." A mismatch is a PROCEDURAL finding about the experiment, not
      a verdict on the instrument, and it is reported as such.

It REFUSES to decide the comparative criteria:

  block_ms_mean / block_ms_max / block_ms_spread   "indistinguishable from run 1"
  loop_us_max / audio_blocks_high_water            "comparable to run 1"

*** No numeric threshold for "indistinguishable" exists anywhere in this
project's authority, and this tool does not invent one. *** timing_probe.h is
explicit that "there is no threshold to argue about — the control run is the
threshold", and step 11 adds "DO NOT PASS THIS STEP ON A SMALL CALL TIME". A
tool that quietly picked, say, 5 % would be manufacturing an acceptance
criterion and handing back a green tick nobody authorised. So these are printed
as side-by-side values with absolute and relative deltas, flagged for the
operator, and the verdict line says outright that the comparative judgment is
not automated.

Transport figures are reported and NEVER judged. Step 11: "Transport is ALLOWED
to degrade." Drops in runs 3/4 are the policy working; `TX room min` 0 in runs
3/4 is backpressure correctly absorbed; non-zero abandoned result bytes in run 4
is correct. The tool annotates which of those expectations each run met, because
an UNMET expectation in run 3 or 4 means the run did not exercise what it was
supposed to exercise — a procedural finding again, not a failure.

*** A KNOWN ASYMMETRY IT CANNOT REMOVE, STATED SO NOBODY DISCOVERS IT LATER ***

The 5 s diagnostic block in loop() calls presentation_printDiagnostics()
unconditionally. Under DISPLAY_TARGET_NONE that is ONE line; under
DISPLAY_TARGET_PI it is about fourteen. So the control run does measurably less
USB printing than runs 2-4, and no amount of care in the procedure changes that
without a firmware change. The bias runs AGAINST runs 2-4 (they carry the extra
print load), so if they still match the control the conclusion is safe. It would
only matter if a run FAILED marginally, and then it is a reason to investigate
rather than to excuse.

*** THE OTHER THING TO KNOW BEFORE READING A TRANSPORT COLUMN ***

The [T1] acquisition block is window-scoped: `t` / timingProbe_reset() clears it.
The [Link] transport block is BOOT-scoped — dataSender_resetStats() runs only
from dataSender_init(). So transport figures accumulate across every window since
power-on, and `TX room min` is a min-since-boot high-water mark. Comparing them
between runs is only meaningful if each run had its own boot. The run sheet
requires exactly that; this tool warns when the session id repeats across runs,
which is the observable symptom of two runs sharing one boot.
"""

from __future__ import annotations

import json
import pathlib
import re
import sys

# --- the [T1] block: strict key=value ---------------------------------------

_T1 = re.compile(r"^\[T1\]\s+([A-Za-z_][A-Za-z0-9_]*)=(.*)$")

# Acquisition keys that MUST read zero in every run (stated absolutely).
MUST_BE_ZERO = ("blocks_skipped", "skip_events", "largest_block_gap")

# Acquisition keys compared against the control. NOT auto-judged: see the
# module docstring.
COMPARED = ("block_ms_mean", "block_ms_max", "block_ms_min", "block_ms_spread",
            "loop_us_max", "loop_us_mean", "audio_blocks_high_water",
            "audio_blocks_used")

# Keys that must agree exactly or the experiment was not controlled.
MUST_MATCH = ("firmware", "protocol")

# --- the [Link] block: prose, not key=value ---------------------------------
#
# data_sender.cpp prints these as sentences. Parsed with explicit patterns
# rather than a generic splitter, so a format change breaks loudly here instead
# of silently yielding None and reading as "no drops".
_LINK = {
    "atomicity_blocked_by_result":
        r"^\[Link\] Atomicity:\s+(\d+) best-effort packets refused",
    "router_sent":   r"^\[Link\] Router:\s+(\d+) sent,",
    "router_dropped": r"^\[Link\] Router:\s+\d+ sent, (\d+) dropped",
    "state_sent":    r"^\[Link\] State:\s+(\d+) sent,",
    "state_dropped": r"^\[Link\] State:\s+\d+ sent, (\d+) dropped",
    "session_id":    r"^\[Link\] Session id:\s+(\d+)",
    "hello_sent":    r"^\[Link\] Session id:.*HELLO (\d+) sent",
    "hello_dropped": r"^\[Link\] Session id:.*HELLO \d+ sent, (\d+) dropped",
    "live_sent":     r"^\[Link\] Live frames:\s+(\d+) sent,",
    "live_dropped":  r"^\[Link\] Live frames:\s+\d+ sent, (\d+) dropped",
    "live_dropped_streak_max":
        r"^\[Link\] Live frames:.*longest drop streak (\d+)",
    "results_queued":     r"^\[Link\] Results:\s+(\d+) queued,",
    "results_delivered":  r"^\[Link\] Results:\s+\d+ queued, (\d+) delivered",
    "results_superseded": r"^\[Link\] Results:.*?(\d+) superseded",
    "result_bytes_abandoned": r"^\[Link\] Results:.*?\((\d+) B abandoned\)",
    "result_drain_ms_max":    r"^\[Link\] Results:.*max drain (\d+) ms",
    "events_sent":    r"^\[Link\] Events:\s+(\d+) sent,",
    "events_dropped": r"^\[Link\] Events:\s+\d+ sent, (\d+) dropped",
    "call_us_max":    r"^\[Link\] Call time:\s+max (\d+) us",
    "call_us_last":   r"^\[Link\] Call time:.*last (\d+) us",
    "send_calls":     r"^\[Link\] Call time:.*\((\d+) calls\)",
    "tx_room_min":    r"^\[Link\] TX room min:\s+(\d+) B",
}
_LINK_RE = {k: re.compile(v) for k, v in _LINK.items()}

_NO_BACKEND = "No display backend compiled in"


def _num(text: str):
    """int, float, or the raw string — never a silent zero."""
    t = text.strip()
    try:
        return int(t)
    except ValueError:
        pass
    try:
        return float(t)
    except ValueError:
        return t


def parse_report(text: str) -> dict:
    """Pull the LAST [T1] report out of a console paste, plus its [Link] block.

    The last one, deliberately: an operator may press `T` more than once, and
    the final report is the one covering the completed window.
    """
    t1: dict = {}
    link: dict = {}
    transport_present = False
    backend_absent = False

    for line in text.splitlines():
        line = line.rstrip()
        m = _T1.match(line)
        if m:
            key, raw = m.group(1), m.group(2)
            if key == "display_target" and t1.get("display_target") is not None:
                # A second report started: keep the later one.
                t1, link = {}, {}
                transport_present = False
                backend_absent = False
            t1[key] = _num(raw)
            continue
        if _NO_BACKEND in line:
            backend_absent = True
            continue
        for key, rx in _LINK_RE.items():
            mm = rx.match(line)
            if mm:
                link[key] = _num(mm.group(1))
                transport_present = True

    if not t1:
        raise ValueError("no [T1] report found — is this the right paste?")
    return {
        "acquisition": t1,
        "transport": link,
        "transport_present": transport_present,
        "backend_absent": backend_absent,
    }


# --- expectations per run role ---------------------------------------------
#
# These are NOT pass criteria. They record what each run was designed to
# exercise, so a run that failed to exercise it is caught as a procedural
# finding. Step 11 states each of them as an expectation, not a threshold.
ROLE_EXPECTATIONS = {
    2: [],
    3: [("live_dropped", "gt0",
         "sustained backpressure should drop live frames"),
        ("tx_room_min", "eq0",
         "a suspended reader should drive TX room min to 0")],
    4: [("result_bytes_abandoned", "gt0",
         "pulling TX mid-drain should abandon result bytes — if this is 0 the "
         "pull missed the drain window and run 4 did not happen")],
}


def _check(value, kind: str) -> bool | None:
    if value is None:
        return None
    if kind == "gt0":
        return value > 0
    if kind == "eq0":
        return value == 0
    raise AssertionError(kind)


def compare(reports: list[dict], labels: list[str]) -> dict:
    control, *others = reports
    ca = control["acquisition"]

    hard_failures: list[str] = []
    procedural: list[str] = []
    rows: list[dict] = []

    # --- the absolute rule, applied to every run including the control ------
    for label, rep in zip(labels, reports):
        for key in MUST_BE_ZERO:
            v = rep["acquisition"].get(key)
            if v is None:
                procedural.append(f"{label}: {key} missing from the report")
            elif v != 0:
                hard_failures.append(
                    f"{label}: {key}={v}, and step 11 requires 0 in every run "
                    f"with no exceptions")

    # --- the experiment must have been controlled ---------------------------
    cw = ca.get("window_ms")
    for label, rep in zip(labels[1:], others):
        a = rep["acquisition"]
        for key in MUST_MATCH:
            if a.get(key) != ca.get(key):
                procedural.append(
                    f"{label}: {key}={a.get(key)!r} but the control has "
                    f"{ca.get(key)!r} — the runs are not the same build family")
        w = a.get("window_ms")
        if isinstance(cw, (int, float)) and isinstance(w, (int, float)) and cw:
            drift = abs(w - cw) / cw
            if drift > 0.10:
                procedural.append(
                    f"{label}: window_ms={w} against the control's {cw} "
                    f"({drift:.0%} apart). Step 11 requires identical window "
                    f"length; max figures are not comparable across unequal "
                    f"windows")

    # --- the control must actually be the control --------------------------
    if control["acquisition"].get("display_target") != "none":
        procedural.append(
            f"control run reports display_target="
            f"{control['acquisition'].get('display_target')!r}, expected "
            f"'none'. Run 1 must be DISPLAY_TARGET_NONE or there is no control")
    if control["transport_present"]:
        procedural.append(
            "control run carries a [Link] transport block, so it was not built "
            "with DISPLAY_TARGET_NONE")

    # --- per-boot check: transport figures are boot-scoped, not windowed ----
    sessions = [(l, r["transport"].get("session_id"))
                for l, r in zip(labels, reports) if r["transport_present"]]
    seen: dict = {}
    for label, sid in sessions:
        if sid is None:
            continue
        if sid in seen:
            procedural.append(
                f"{label} and {seen[sid]} both report session id {sid}, so they "
                f"share one boot. [Link] figures are cumulative since boot "
                f"(dataSender_resetStats() runs only in dataSender_init()), so "
                f"their transport columns overlap and TX room min carries over")
        else:
            seen[sid] = label

    # --- comparative metrics: reported, never judged -----------------------
    for key in COMPARED:
        row = {"metric": key, "control": ca.get(key), "runs": []}
        for label, rep in zip(labels[1:], others):
            v = rep["acquisition"].get(key)
            delta = rel = None
            c = ca.get(key)
            if isinstance(v, (int, float)) and isinstance(c, (int, float)):
                delta = v - c
                rel = (delta / c) if c else None
            row["runs"].append({"label": label, "value": v,
                                "delta": delta, "rel": rel})
        rows.append(row)

    # --- did each run exercise what it was for? ---------------------------
    exercised: list[dict] = []
    for idx, (label, rep) in enumerate(zip(labels[1:], others), start=2):
        for key, kind, why in ROLE_EXPECTATIONS.get(idx, []):
            v = rep["transport"].get(key)
            ok = _check(v, kind)
            exercised.append({"run": label, "metric": key, "value": v,
                              "met": ok, "why": why})
            if ok is False:
                procedural.append(f"{label}: {key}={v} — {why}")
            elif ok is None:
                procedural.append(
                    f"{label}: {key} missing from the report, cannot confirm "
                    f"the run exercised its condition ({why})")

    return {
        "labels": labels,
        "hard_failures": hard_failures,
        "procedural_findings": procedural,
        "comparison": rows,
        "exercised": exercised,
        "transport": [{"label": l,
                       "present": r["transport_present"],
                       **r["transport"]}
                      for l, r in zip(labels, reports)],
    }


# --- reporting -------------------------------------------------------------

def _fmt(v) -> str:
    if v is None:
        return "—"
    if isinstance(v, float):
        return f"{v:.3f}"
    return str(v)


def print_report(res: dict) -> None:
    labels = res["labels"]
    print()
    print("================ T1 MECHANICAL DIFF ================")
    print(f"control : {labels[0]}")
    for l in labels[1:]:
        print(f"compared: {l}")
    print()

    print("--- ABSOLUTE RULE (checked): blocks_skipped / skip_events /")
    print("    largest_block_gap must be 0 in EVERY run ---")
    if res["hard_failures"]:
        for f in res["hard_failures"]:
            print(f"  FAIL  {f}")
    else:
        print("  all zero in every run")
    print()

    print("--- COMPARATIVE METRICS (reported, NOT auto-judged) ---")
    print("    No project authority defines 'indistinguishable'. These are")
    print("    yours to read. timing_probe.h: the control run IS the threshold.")
    head = f"  {'metric':<26}{'control':>12}"
    for l in labels[1:]:
        head += f"{l[:14]:>16}"
    print(head)
    for row in res["comparison"]:
        line = f"  {row['metric']:<26}{_fmt(row['control']):>12}"
        for r in row["runs"]:
            cell = _fmt(r["value"])
            if r["rel"] is not None:
                cell += f" ({r['rel']:+.1%})"
            elif r["delta"] is not None:
                cell += f" ({r['delta']:+})"
            line += f"{cell:>16}"
        print(line)
    print()

    print("--- TRANSPORT (reported, NEVER judged: allowed to degrade) ---")
    for t in res["transport"]:
        if not t["present"]:
            print(f"  {t['label']}: no transport block "
                  f"(DISPLAY_TARGET_NONE — expected for the control)")
            continue
        print(f"  {t['label']}:")
        for key in ("session_id", "live_sent", "live_dropped",
                    "live_dropped_streak_max", "call_us_max", "tx_room_min",
                    "atomicity_blocked_by_result", "results_queued",
                    "results_delivered", "result_bytes_abandoned",
                    "result_drain_ms_max", "state_dropped", "hello_dropped",
                    "router_dropped", "events_dropped"):
            if key in t:
                print(f"      {key:<28}{t[key]}")
    print()

    if res["exercised"]:
        print("--- DID EACH RUN EXERCISE ITS CONDITION? ---")
        for e in res["exercised"]:
            mark = {True: "yes", False: "NO ", None: "?? "}[e["met"]]
            print(f"  {mark}  {e['run']}: {e['metric']}={_fmt(e['value'])}")
            if e["met"] is not True:
                print(f"         {e['why']}")
        print()

    if res["procedural_findings"]:
        print("--- PROCEDURAL FINDINGS (about the experiment, not the "
              "instrument) ---")
        for f in res["procedural_findings"]:
            print(f"  - {f}")
        print()

    print("--- VERDICT ---")
    if res["hard_failures"]:
        print("  ABSOLUTE RULE VIOLATED. Step 11: stop. The non-blocking policy")
        print("  has been broken somewhere and no Pi-side work will fix it.")
    else:
        print("  Absolute rule holds: zero skipped blocks in every run.")
    if res["procedural_findings"]:
        print("  Procedural findings above must be resolved before the numbers")
        print("  are citable — an uncontrolled experiment cannot pass or fail.")
    print("  T1 ITSELF IS NOT DECIDED HERE. The comparative judgment against")
    print("  the control is the operator's, and a small call time is not a pass.")
    print("====================================================")
    print()


def main(argv: list[str]) -> int:
    args = [a for a in argv[1:] if not a.startswith("--")]
    as_json = "--json" in argv
    if len(args) < 2:
        print(__doc__)
        return 2

    reports, labels = [], []
    for path in args:
        p = pathlib.Path(path)
        try:
            reports.append(parse_report(p.read_text(errors="replace")))
        except ValueError as exc:
            print(f"{path}: {exc}", file=sys.stderr)
            return 2
        labels.append(p.stem)

    res = compare(reports, labels)
    if as_json:
        print(json.dumps(res, indent=2))
    else:
        print_report(res)

    # Exit code covers ONLY the absolute rule and experiment control. It is
    # deliberately not a T1 verdict.
    if res["hard_failures"]:
        return 1
    if res["procedural_findings"]:
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
